"""Walk-forward retrospective backfill: honestly-graded history for all models.

For each calendar-month window: train each model's classifier + regressor ONLY on
feature-snapshot games strictly BEFORE the window, predict the window's games, and
log rows tagged ``model_version = wf_<YYYY-MM>``. Honesty guarantees:

  * Out-of-sample by construction (train < window start) — the same walk-forward
    discipline as experiments/e21_calibration_backtest.py, producing production
    `model_predictions` rows instead of research JSON.
  * NEVER touches the live record: (game_id, model_type) pairs that already have
    ANY logged row are skipped, so a wf_ row can't supersede a live prediction in
    the API's latest-timestamp dedup.
  * E21 policies: picks derive from the RAW classifier probability; displayed
    `home_win_probability` is raw for rf/nn and eval-slice isotonic for xgb
    (mirrors per-model production display semantics). `margin_uncertainty` is
    NULL for wf rows (no MC/conformal machinery here).

These rows are retrospective (not logged before tip-off). Per user decision
2026-07-03 they are NOT badged on the site; the wf_ version prefix in the DB is
the only provenance marker.

``--supersede-non-wf`` (P-2, 2026-10-30): the skip rule above left RF/NN 2025-26
on retrospective rows from a preseason-trained bundle while XGB got wf_ rows,
so the public record compared two different processes. With the flag, a pair
is (re)logged whenever the row the API serves (latest prediction_timestamp) is
not a wf_ row. Old rows stay in the table for audit; the new wf_ row wins the
dedup because it is newer. Pairs already served from a wf_ row are untouched.
Use it only for a closed season: Kai's decision is all walk-forward for 2025-26.

Usage (Phase B, gaps in 2025-26; xgb stops at March because Apr-Jun came from the
live-era bundle on the cloud):
    python modeling/walkforward_backfill.py --models rf,nn --start 2025-10 --end 2026-06
    python modeling/walkforward_backfill.py --models xgb --start 2025-10 --end 2026-03
Phase C (prior seasons):
    python modeling/walkforward_backfill.py --models rf,nn,xgb --start 2023-10 --end 2025-06
P-2 (2025-26 all walk-forward; dry-run first, it lists what would be superseded):
    python modeling/walkforward_backfill.py --models rf,nn,xgb --start 2025-10 --end 2026-06 --supersede-non-wf --dry-run
"""
from __future__ import annotations

# torch first (Windows MKL import order)
try:
    import torch
    TORCH_AVAILABLE = True
except Exception:
    TORCH_AVAILABLE = False

import sys as _sys
import os as _os
_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _PROJECT_ROOT)
if _os.getcwd() != _PROJECT_ROOT:
    _os.chdir(_PROJECT_ROOT)

import argparse

import numpy as np
import pandas as pd
import sqlalchemy as sa
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.isotonic import IsotonicRegression

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False

from core.db import get_engine
from core.features import select_features
from core.features_io import load_features
from modeling.prediction_tracker import log_prediction, ensure_table_exists, backfill_actuals

if TORCH_AVAILABLE:
    from modeling.predict_games import NBAClassifier, NBARegressor, _train_pytorch_model

SEED = 42
MIN_TRAIN = 800
RF_CLF_HP = dict(n_estimators=100, max_depth=5, min_samples_leaf=20)
XGB_HP = dict(n_estimators=200, max_depth=4, learning_rate=0.1, min_child_weight=10,
              subsample=0.8, colsample_bytree=0.8, reg_lambda=1.0)
NN_HP = dict(dropout=0.5, epochs=100, lr=0.001, weight_decay=1e-4)


def _game_meta(engine) -> dict:
    """game_id -> (game_date_iso, home_abbrev, away_abbrev) from game_list."""
    q = """
        SELECT GAME_ID, GAME_DATE, TEAM_ABBREVIATION, MATCHUP
        FROM game_list WHERE MATCHUP LIKE '%vs.%'
    """
    meta = {}
    with engine.connect() as conn:
        for gid, gd, team, matchup in conn.execute(sa.text(q)):
            away = matchup.split(' vs. ', 1)[1].strip() if ' vs. ' in matchup else None
            meta[int(gid)] = (pd.Timestamp(gd).strftime('%Y-%m-%d'), team, away)
    return meta


def _served_versions(engine) -> dict:
    """(game_id, model_type) -> model_version of the row the API serves (latest
    prediction_timestamp, the same dedup as api/queries.py)."""
    q = """
        SELECT game_id, model_type, model_version FROM (
            SELECT game_id, model_type, model_version,
                   ROW_NUMBER() OVER (PARTITION BY game_id, model_type
                                      ORDER BY prediction_timestamp DESC) AS rn
            FROM model_predictions) x
        WHERE rn = 1
    """
    with engine.connect() as conn:
        return {(int(g), m): v for g, m, v in conn.execute(sa.text(q))}


def _wf_feature_counts(engine, start: str, end: str) -> dict:
    """feature_count -> rows among existing wf_ rows in the window range. A
    superseding run must use the same model inputs as the wf_ rows it sits
    beside, or the record is still not like-for-like."""
    q = """
        SELECT feature_count, COUNT(*) FROM model_predictions
        WHERE model_version LIKE 'wf!_%' ESCAPE '!'
          AND game_date >= :s AND game_date < :e
        GROUP BY feature_count
    """
    s = pd.Period(start, freq='M').to_timestamp().date()
    e = (pd.Period(end, freq='M') + 1).to_timestamp().date()
    with engine.connect() as conn:
        return {(int(fc) if fc is not None else None): int(n)
                for fc, n in conn.execute(sa.text(q), {'s': s, 'e': e})}


def _predict_window(model_key, X_tr, y_clf_tr, y_reg_tr, X_te):
    """Train clf+reg on the window's past, return (p_raw, margins, p_display)."""
    if model_key == 'rf':
        clf = RandomForestClassifier(**RF_CLF_HP, random_state=SEED, n_jobs=-1)
        reg = RandomForestRegressor(**RF_CLF_HP, random_state=SEED, n_jobs=-1)
        clf.fit(X_tr, y_clf_tr)
        reg.fit(X_tr, y_reg_tr)
        p_raw = clf.predict_proba(X_te)[:, 1]
        return p_raw, reg.predict(X_te), p_raw  # E21: rf display == raw

    if model_key == 'xgb':
        clf = xgb.XGBClassifier(**XGB_HP, random_state=SEED, n_jobs=-1,
                                eval_metric='logloss', verbosity=0)
        reg = xgb.XGBRegressor(**XGB_HP, random_state=SEED, n_jobs=-1, verbosity=0)
        clf.fit(X_tr, y_clf_tr)
        reg.fit(X_tr, y_reg_tr)
        p_raw = clf.predict_proba(X_te)[:, 1]
        # Display prob mirrors production: isotonic fit on the last-20% eval
        # slice of THIS window's training past (same protocol as the prod path).
        split = int(0.8 * len(X_tr))
        eval_clf = xgb.XGBClassifier(**XGB_HP, random_state=SEED, n_jobs=-1,
                                     eval_metric='logloss', verbosity=0)
        eval_clf.fit(X_tr[:split], y_clf_tr[:split])
        iso = IsotonicRegression(out_of_bounds='clip').fit(
            eval_clf.predict_proba(X_tr[split:])[:, 1], y_clf_tr[split:])
        return p_raw, reg.predict(X_te), np.clip(iso.predict(p_raw), 0.0, 1.0)

    if model_key == 'nn':
        clf = NBAClassifier(input_dim=X_tr.shape[1], dropout_rate=NN_HP['dropout'])
        _train_pytorch_model(clf, X_tr, y_clf_tr.astype(np.float32), is_classifier=True,
                             epochs=NN_HP['epochs'], lr=NN_HP['lr'],
                             weight_decay=NN_HP['weight_decay'], seed=SEED)
        reg = NBARegressor(input_dim=X_tr.shape[1], dropout_rate=NN_HP['dropout'])
        tscaler = StandardScaler()
        tscaler = _train_pytorch_model(reg, X_tr, y_reg_tr.astype(np.float32),
                                       is_classifier=False, epochs=NN_HP['epochs'],
                                       lr=NN_HP['lr'], weight_decay=NN_HP['weight_decay'],
                                       target_scaler=tscaler, seed=SEED) or tscaler
        clf.eval()
        reg.eval()
        with torch.no_grad():
            p_raw = torch.sigmoid(clf(torch.FloatTensor(X_te))).numpy().flatten()
            m_scaled = reg(torch.FloatTensor(X_te)).numpy().reshape(-1, 1)
        margins = tscaler.inverse_transform(m_scaled).flatten()
        return p_raw, margins, p_raw  # NN has no calibrator: display == raw

    raise ValueError(model_key)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--snapshot-version', default='20260703T072718Z',
                    help='feature_set_version of the multi-season research snapshot')
    ap.add_argument('--models', default='rf,nn,xgb')
    ap.add_argument('--start', required=True, help='first window month, YYYY-MM')
    ap.add_argument('--end', required=True, help='last window month, YYYY-MM')
    ap.add_argument('--dry-run', action='store_true', help='no DB writes')
    ap.add_argument('--supersede-non-wf', action='store_true',
                    help='P-2: also log a wf_ row where the served row is not wf_ '
                         '(retrospective or live). Closed seasons only.')
    args = ap.parse_args()

    models = [m.strip() for m in args.models.split(',') if m.strip()]
    engine = get_engine()
    ensure_table_exists(engine)

    df = load_features(engine, version=args.snapshot_version)
    df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])
    df = df.sort_values('GAME_DATE').reset_index(drop=True)
    feat_cols = [c for c in select_features(df.columns)
                 if df[c].notna().any()]
    print(f"snapshot {args.snapshot_version}: {len(df)} games, {len(feat_cols)} features")

    meta = _game_meta(engine)
    served = _served_versions(engine)
    if args.supersede_non_wf:
        counts = _wf_feature_counts(engine, args.start, args.end)
        print(f"existing wf_ rows in range by feature_count: {counts}")
        if counts and set(counts) != {len(feat_cols)}:
            raise SystemExit(
                f"ABORT: this run uses {len(feat_cols)} features but the wf_ rows it would "
                f"sit beside used {sorted(counts, key=str)}. Superseded rows would not be "
                f"like-for-like; check --snapshot-version and core/features.py defaults.")
        print("mode: supersede - (re)log every pair whose served row is not wf_")
    else:
        print(f"existing (game, model) pairs to skip: {len(served)}")
    superseded = {}  # (model, superseded version) -> rows, for the summary

    months = pd.period_range(args.start, args.end, freq='M')
    total_logged = 0
    for period in months:
        w_start = period.to_timestamp()
        w_end = w_start + pd.offsets.MonthEnd(1)
        tr = df[df['GAME_DATE'] < w_start]
        te = df[(df['GAME_DATE'] >= w_start) & (df['GAME_DATE'] <= w_end)]
        if len(te) == 0 or len(tr) < MIN_TRAIN:
            print(f"{period}: skipped (test={len(te)}, train={len(tr)})")
            continue

        imp = SimpleImputer(strategy='median')
        scl = StandardScaler()
        X_tr = scl.fit_transform(imp.fit_transform(tr[feat_cols]))
        X_te = scl.transform(imp.transform(te[feat_cols]))
        y_clf = tr['TARGET_WIN'].values.astype(int)
        y_reg = tr['TARGET_MARGIN'].values.astype(float)
        wf_version = f"wf_{period}"

        for mk in models:
            # Which of this window's games still need a row for this model?
            # Default: only pairs with no row at all. Supersede mode: any pair whose
            # served row is not walk-forward.
            need_idx = []
            for i, gid in enumerate(te['GAME_ID'].values):
                cur = served.get((int(gid), mk))
                if cur is None:
                    need_idx.append(i)
                elif args.supersede_non_wf and not str(cur).startswith('wf_'):
                    need_idx.append(i)
                    superseded[(mk, cur)] = superseded.get((mk, cur), 0) + 1
            if not need_idx:
                print(f"{period} {mk}: 0 gaps")
                continue
            if args.dry_run:  # listing only: no training needed
                n_would = sum(int(te['GAME_ID'].values[i]) in meta for i in need_idx)
                total_logged += n_would
                print(f"{period} {mk}: would log {n_would} of {len(te)} window games")
                continue
            p_raw, margins, p_disp = _predict_window(mk, X_tr, y_clf, y_reg, X_te)
            n_logged = 0
            for i in need_idx:
                gid = int(te['GAME_ID'].values[i])
                if gid not in meta:
                    continue
                gd, home, away = meta[gid]
                pick = home if p_raw[i] > 0.5 else away  # E21 raw-pick policy
                if not args.dry_run:
                    log_prediction(
                        engine=engine, game_id=str(gid).zfill(10), game_date=gd,
                        home_team=home, away_team=away, model_type=mk,
                        model_version=wf_version, predicted_winner=pick,
                        predicted_margin=float(margins[i]),
                        home_win_probability=float(p_disp[i]),
                        home_win_probability_raw=float(p_raw[i]),
                        margin_uncertainty=None, feature_count=len(feat_cols),
                    )
                n_logged += 1
            total_logged += n_logged
            print(f"{period} {mk}: logged {n_logged} of {len(te)} window games "
                  f"({len(te) - len(need_idx)} already had rows)")

    if superseded:
        print("\nsuperseded served rows (model, old model_version, rows):")
        for (mk, ver), n in sorted(superseded.items()):
            print(f"  {mk:4s} {ver:40s} {n}")
    print(f"\ntotal wf rows {'that would be ' if args.dry_run else ''}logged: {total_logged}")
    if not args.dry_run and total_logged:
        print("grading...")
        res = backfill_actuals(engine, lookback_days=1100, verbose=False)
        print(f"backfill: {res}")


if __name__ == '__main__':
    main()
