"""
E28 step 1 — serving-path audit: what do the production models actually see?

For a set of real games, build the feature vector exactly as the nightly job
does (get_team_rolling_stats -> build_matchup_features; injuries omitted) and
compare it with what the model was trained on:
  * which bundle features the live builder never produces (-> NaN -> training
    median), grouped by feature family;
  * for games that ALSO exist in the training feature table, the per-column
    difference between the live value and the training value (train/serve skew);
  * the spread of each model's margin and win probability with live features vs
    with training-table features for the same games.

Read-only: SELECTs against the local MySQL + local bundles. Writes only
outputs/e28_serving_audit.json.

Usage:
    python experiments/e28_serving_audit.py --dates 2026-01-15 2026-03-02 --version 20260703T072718Z
    python experiments/e28_serving_audit.py --dates 2026-10-24 2026-10-26     # live season, no table rows
"""
from __future__ import annotations

try:
    import torch  # noqa: F401  (Windows import order)
except Exception:
    pass

import sys as _sys
import os as _os
_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _PROJECT_ROOT)
if _os.getcwd() != _PROJECT_ROOT:
    _os.chdir(_PROJECT_ROOT)

import argparse
import json
import re
from collections import Counter

import numpy as np
import pandas as pd
import sqlalchemy as sa

from core.db import get_engine
from core.features_io import load_features
try:
    from modeling.predict_games import (
        get_team_rolling_stats, build_matchup_features, load_model_bundle,
    )
except ImportError:
    raise SystemExit(
        'e28_serving_audit audits the OLD live feature builder, removed on 2026-11-13 '
        '(E28 fix). Its results are in outputs/e28_audit_*.json and tuning log §E28. '
        'To re-run it, check out the pre-fix code: git worktree add ../pre-e28 d7c717a. '
        'For the fixed path use scripts/check_serving_parity.py and '
        'experiments/e28_fixed_replay.py.')


def family(col: str) -> str:
    """Coarse feature family for reporting."""
    c = re.sub(r'^(HOME_|AWAY_|DIFF_)', '', col)
    for key, fam in (('ELO', 'elo'), ('SLOT_', 'player_slots'), ('IMPACT', 'player_impact'),
                     ('PLAYERS_OUT', 'player_impact'), ('PROJ', 'player_projection'),
                     ('SERIES', 'series'), ('PLAYOFF', 'series'), ('STREAK', 'streak'),
                     ('REST', 'rest_fatigue'), ('BACK_TO_BACK', 'rest_fatigue'),
                     ('GAMES_LAST', 'rest_fatigue'), ('3_IN_4', 'rest_fatigue'),
                     ('WIN_PCT', 'win_pct'), ('SEASON', 'season_to_date'),
                     ('_L5', 'rolling_L5'), ('_L10', 'rolling_L10')):
        if key in c:
            return fam
    return 'other'


def games_on(engine, date: str) -> pd.DataFrame:
    """Home/away pairs for a date from game_list (MATCHUP 'vs.' = home row)."""
    q = sa.text("""SELECT GAME_ID, TEAM_ID, TEAM_ABBREVIATION, MATCHUP
                   FROM game_list WHERE GAME_DATE = :d AND SEASON_ID LIKE '2%'""")
    with engine.connect() as c:
        df = pd.read_sql(q, c, params={'d': date})
    home = df[df['MATCHUP'].str.contains('vs.')]
    away = df[df['MATCHUP'].str.contains('@')]
    return home.merge(away, on='GAME_ID', suffixes=('_H', '_A'))


def bundle_predict(key: str, bundle: dict, X: pd.DataFrame):
    """(home win prob, margin) per row from a bundle on a feature frame."""
    imputer, scaler = bundle['scaler_tuple']
    Xs = scaler.transform(imputer.transform(X[bundle['feature_names']]))
    if key == 'nn':
        return None
    clf, reg = bundle['classifier'], bundle['regressor']
    base = getattr(clf, '_base', clf)
    return base.predict_proba(Xs)[:, 1], getattr(reg, '_base', reg).predict(Xs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dates', nargs='+', required=True)
    ap.add_argument('--version', default=None, help='feature_set_version for the training-table comparison')
    ap.add_argument('--out', default='outputs/e28_serving_audit.json')
    args = ap.parse_args()

    engine = get_engine()
    bundles = {k: load_model_bundle(k) for k in ('rf', 'xgb')}
    feats = bundles['rf']['feature_names']
    print(f"rf bundle {bundles['rf']['metadata'].get('version')} "
          f"data_through={bundles['rf']['metadata'].get('data_through_date')} features={len(feats)}")

    live_rows = []
    for d in args.dates:
        g = games_on(engine, d)
        for _, r in g.iterrows():
            hf = get_team_rolling_stats(engine, int(r['TEAM_ID_H']), d)
            af = get_team_rolling_stats(engine, int(r['TEAM_ID_A']), d)
            if hf is None or af is None:
                continue
            m = build_matchup_features(hf, af, engine=engine, home_team_id=int(r['TEAM_ID_H']),
                                       away_team_id=int(r['TEAM_ID_A']), game_date=d)
            m.pop('_slot_to_player', None)
            m['GAME_ID'] = r['GAME_ID']
            m['GAME_DATE'] = d
            live_rows.append(m)
    live = pd.DataFrame(live_rows)
    print(f'{len(live)} games built through the live path')
    for f in feats:
        if f not in live.columns:
            live[f] = np.nan

    produced = {f: bool(live[f].notna().any()) for f in feats}
    missing = [f for f, ok in produced.items() if not ok]
    fam_total = Counter(family(f) for f in feats)
    fam_missing = Counter(family(f) for f in missing)
    print(f'\nbundle features never produced live: {len(missing)}/{len(feats)}')
    for fam_name, n in fam_total.most_common():
        print(f'  {fam_name:18s} {fam_missing.get(fam_name, 0):3d}/{n:3d} missing')

    imp_rank = {}
    reg = getattr(bundles['rf']['regressor'], '_base', bundles['rf']['regressor'])
    if hasattr(reg, 'feature_importances_'):
        order = np.argsort(-reg.feature_importances_)
        imp_rank = {feats[i]: (rank + 1, float(reg.feature_importances_[i])) for rank, i in enumerate(order)}
        top = [feats[i] for i in order[:25]]
        print('\nRF regressor top-25 features and whether live produces them:')
        for f in top:
            print(f'  #{imp_rank[f][0]:2d} {imp_rank[f][1]:.3f} {"OK     " if produced[f] else "MISSING"} {f}')
        miss_share = sum(imp_rank[f][1] for f in missing)
        print(f'share of RF regressor importance on never-produced features: {miss_share:.1%}')

    out = {'dates': args.dates, 'n_games': len(live), 'n_features': len(feats),
           'missing': missing, 'missing_by_family': dict(fam_missing), 'total_by_family': dict(fam_total),
           'rf_reg_importance_missing_share': (sum(imp_rank[f][1] for f in missing) if imp_rank else None)}

    preds = {}
    for k, b in bundles.items():
        p, mg = bundle_predict(k, b, live)
        preds[k] = {'live_margin_sd': float(np.std(mg)), 'live_margin_mean': float(np.mean(mg)),
                    'live_prob_sd': float(np.std(p))}

    if args.version:
        table = load_features(engine, version=args.version)
        table['GAME_ID'] = table['GAME_ID'].astype(str).str.zfill(10)
        live['GAME_ID'] = live['GAME_ID'].astype(str).str.zfill(10)
        both = live.merge(table, on='GAME_ID', suffixes=('_live', '_tbl'))
        print(f'\n{len(both)} games also in training table {args.version}')
        if len(both):
            skew = []
            for f in feats:
                lv = pd.to_numeric(both[f + '_live'], errors='coerce')
                tv = pd.to_numeric(both[f + '_tbl'], errors='coerce') if f + '_tbl' in both else pd.Series(np.nan, index=both.index)
                sd = pd.to_numeric(table[f], errors='coerce').std() if f in table else np.nan
                diff = (lv - tv).abs()
                skew.append({'feature': f, 'family': family(f),
                             'live_nan_rate': float(lv.isna().mean()), 'tbl_nan_rate': float(tv.isna().mean()),
                             'mean_abs_diff_in_sd': float(diff.mean() / sd) if sd and sd > 0 else None,
                             'rf_reg_rank': imp_rank.get(f, (None,))[0]})
            skew_df = pd.DataFrame(skew).sort_values('mean_abs_diff_in_sd', ascending=False)
            print('\nlargest train/serve differences (mean |live - table| in training SDs), present-in-both columns:')
            print(skew_df[skew_df['live_nan_rate'] < 1].head(20).to_string(index=False))
            by_fam = skew_df.groupby('family')['mean_abs_diff_in_sd'].median()
            print('\nmedian skew by family (SDs):\n' + by_fam.round(3).to_string())
            out['skew_top'] = skew_df.head(60).to_dict('records')
            out['skew_by_family'] = by_fam.to_dict()

            tbl_X = both[[f + '_tbl' for f in feats]].copy()
            tbl_X.columns = feats
            live_X = both[[f + '_live' for f in feats]].copy()
            live_X.columns = feats
            for k, b in bundles.items():
                p_t, m_t = bundle_predict(k, b, tbl_X.apply(pd.to_numeric, errors='coerce'))
                p_l, m_l = bundle_predict(k, b, live_X.apply(pd.to_numeric, errors='coerce'))
                preds[k].update({'same_games_table_margin_sd': float(np.std(m_t)),
                                 'same_games_live_margin_sd': float(np.std(m_l)),
                                 'same_games_table_prob_sd': float(np.std(p_t)),
                                 'same_games_live_prob_sd': float(np.std(p_l)),
                                 'margin_corr_live_vs_table': float(np.corrcoef(m_t, m_l)[0, 1]),
                                 'pick_agreement_live_vs_table': float(np.mean((p_t >= .5) == (p_l >= .5)))})
    print('\nprediction spread:')
    for k, v in preds.items():
        print(f'  {k}: ' + ', '.join(f'{a}={b:.3f}' for a, b in v.items()))
    out['predictions'] = preds

    _os.makedirs('outputs', exist_ok=True)
    with open(args.out, 'w') as f:
        json.dump(out, f, indent=2, default=float)
    print(f'\nSaved -> {args.out}')


if __name__ == '__main__':
    main()
