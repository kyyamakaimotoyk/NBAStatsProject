"""
E15 (Phase 1) — Cross-context generalization study.

Two questions, one instrument (the E13/E14 calibration + coverage machinery):

  MODE learning_curve  — "How much data do we need?"
     Fix the test set (W5 regular season). Vary how far back training starts
     (last 0.5 / 1 / 2 / 3 / 4 seasons). Plot accuracy / MAE / ECE / coverage vs
     n_train. If the curve is flat past ~1 season, more history doesn't help.

  MODE regime          — "Can a regular-season model be trusted in the playoffs?"
     For each season with playoffs in our data, train on REGULAR-season games
     strictly before that season's playoffs, fit the isotonic calibrator + the
     split-conformal interval on a held-out tail, then score three test sets that
     all occur AFTER training:
        (a) held-out REGULAR games from the same late-season weeks  [control]
        (b) PLAY-IN games
        (c) PLAYOFF games
     Pool predictions across seasons -> ~400 playoff test games.
     The headline cross-context metric is COVERAGE: does the regular-season
     90% interval still contain ~90% of PLAYOFF margins, or does it break? And
     does ECE (probability calibration) inflate out of context?
     Plus a feature distribution-shift check (KS test, regular vs playoff).

Usage:
    python experiments/e15_cross_context.py --mode learning_curve --seeds 5
    python experiments/e15_cross_context.py --mode regime --seeds 5
"""
from __future__ import annotations

try:
    import torch  # noqa: F401
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
from datetime import datetime

import numpy as np
import pandas as pd
from scipy import stats as scistats
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import roc_auc_score, brier_score_loss

import xgboost as xgb
from sqlalchemy import text

from core.db import get_engine
from core.features import select_features

SEEDS = [42, 123, 456, 789, 1000, 2024, 31337, 65535, 8675309, 99999]
W5_START, W5_END = '2026-03-15', '2026-04-15'

RF_CLF_HP = {'n_estimators': 100, 'max_depth': 5, 'min_samples_leaf': 20}
RF_REG_HP = {'n_estimators': 100, 'max_depth': 5, 'min_samples_leaf': 20}
XGB_CLF_HP = {'n_estimators': 200, 'max_depth': 4, 'learning_rate': 0.1, 'min_child_weight': 10,
              'subsample': 0.8, 'colsample_bytree': 0.8, 'reg_lambda': 1.0, 'eval_metric': 'logloss'}
XGB_REG_HP = {'n_estimators': 200, 'max_depth': 4, 'learning_rate': 0.1, 'min_child_weight': 10,
              'subsample': 0.8, 'colsample_bytree': 0.8, 'reg_lambda': 1.0}


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def load_labeled():
    """Load the feature CSV with a `regime` column derived from game_list.SEASON_ID."""
    df = pd.read_csv('nba_ml_features.csv')
    df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])
    df['GAME_ID'] = df['GAME_ID'].astype('int64')
    eng = get_engine()
    gl = pd.read_sql(text('SELECT DISTINCT GAME_ID, SEASON_ID FROM game_list'), eng)
    gl['GAME_ID'] = gl['GAME_ID'].astype('int64')
    stype = gl['SEASON_ID'].astype(str).str[0]
    gl['regime'] = stype.map({'2': 'regular', '4': 'playoffs', '5': 'playin',
                              '3': 'allstar', '1': 'preseason', '6': 'cup'})
    return df.merge(gl[['GAME_ID', 'regime']], on='GAME_ID', how='left')


def ece(y_true, y_prob, n_bins=10):
    edges = np.linspace(0, 1, n_bins + 1)
    n = len(y_true); tot = 0.0
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        m = (y_prob >= lo) & (y_prob < hi if i < n_bins - 1 else y_prob <= hi)
        if m.sum() == 0:
            continue
        tot += (m.sum() / n) * abs(y_prob[m].mean() - y_true[m].mean())
    return float(tot)


def conformal_q(resid, level):
    n = len(resid); k = min(int(np.ceil((n + 1) * level)), n)
    return float(np.sort(resid)[k - 1])


# ---------------------------------------------------------------------------
# Train + evaluate one (model, seed) on a train/calib split, score a test set
# ---------------------------------------------------------------------------

def make_models(model, seed):
    if model == 'RF':
        return (RandomForestClassifier(**RF_CLF_HP, random_state=seed, n_jobs=-1),
                RandomForestRegressor(**RF_REG_HP, random_state=seed, n_jobs=-1))
    return (xgb.XGBClassifier(**XGB_CLF_HP, random_state=seed, n_jobs=-1),
            xgb.XGBRegressor(**XGB_REG_HP, random_state=seed, n_jobs=-1))


def fit_calibrated(Xtr, yclf_tr, yreg_tr, Xcal, yclf_cal, yreg_cal, model, seed):
    """Train clf+reg, fit isotonic calibrator + conformal half-widths on the calib slice."""
    clf, reg = make_models(model, seed)
    clf.fit(Xtr, yclf_tr); reg.fit(Xtr, yreg_tr)
    # isotonic on calib
    iso = IsotonicRegression(out_of_bounds='clip')
    iso.fit(clf.predict_proba(Xcal)[:, 1], yclf_cal)
    # conformal half-widths on calib
    resid = np.abs(yreg_cal - reg.predict(Xcal))
    hw = {80: conformal_q(resid, 0.80), 90: conformal_q(resid, 0.90)}
    return clf, reg, iso, hw


def eval_on(clf, reg, iso, hw, Xte, yclf_te, yreg_te):
    raw_p = clf.predict_proba(Xte)[:, 1]
    cal_p = np.clip(iso.predict(raw_p), 0, 1)
    margin = reg.predict(Xte)
    out = {
        'n': int(len(yclf_te)),
        'acc': float(((cal_p >= 0.5).astype(int) == yclf_te).mean()),
        'auc': float(roc_auc_score(yclf_te, cal_p)) if len(np.unique(yclf_te)) > 1 else float('nan'),
        'mae': float(np.abs(margin - yreg_te).mean()),
        'ece': ece(yclf_te, cal_p),
        'brier': float(brier_score_loss(yclf_te, cal_p)) if len(np.unique(yclf_te)) > 1 else float('nan'),
    }
    for lvl in (80, 90):
        inside = (yreg_te >= margin - hw[lvl]) & (yreg_te <= margin + hw[lvl])
        out[f'cov{lvl}'] = float(inside.mean())
    return out


def prep(train_df, calib_df, test_df, feature_cols):
    vc = train_df[feature_cols].columns[train_df[feature_cols].notna().any()].tolist()
    imp = SimpleImputer(strategy='median'); scl = StandardScaler()
    Xtr = scl.fit_transform(imp.fit_transform(train_df[vc]))
    Xcal = scl.transform(imp.transform(calib_df[vc]))
    Xte = scl.transform(imp.transform(test_df[vc]))
    return Xtr, Xcal, Xte


def agg(runs, keys):
    """Mean +/- std across seed runs for each metric key."""
    return {k: {'mean': float(np.nanmean([r[k] for r in runs])),
                'std': float(np.nanstd([r[k] for r in runs]))} for k in keys}


METRIC_KEYS = ['acc', 'auc', 'mae', 'ece', 'brier', 'cov80', 'cov90']


# ---------------------------------------------------------------------------
# MODE: learning_curve
# ---------------------------------------------------------------------------

def run_learning_curve(seeds, models):
    df = load_labeled()
    fc = select_features(df.columns)
    test = df[(df['GAME_DATE'] >= W5_START) & (df['GAME_DATE'] <= W5_END) & (df['regime'] == 'regular')]
    print(f'Test (W5 regular): {len(test)} games\n')

    # Train-start cutoffs counted back from W5 start
    cutoffs = {
        '~0.5 season (since 2025-10-01)': '2025-10-01',
        '~1 season (since 2025-03-15)': '2025-03-15',
        '~2 seasons (since 2024-03-15)': '2024-03-15',
        '~3 seasons (since 2023-03-15)': '2023-03-15',
        'all (since 2022-01-01)': '2022-01-01',
    }
    results = {'mode': 'learning_curve', 'n_test': len(test), 'seeds': seeds,
               'points': [], 'run_at': datetime.now().isoformat(timespec='seconds')}

    for label, start in cutoffs.items():
        pool = df[(df['GAME_DATE'] >= start) & (df['GAME_DATE'] < W5_START) & (df['regime'] == 'regular')]
        if len(pool) < 300:
            print(f'[skip] {label}: only {len(pool)} train games')
            continue
        # last 15% of the pool (by date) is the calibration slice
        pool = pool.sort_values('GAME_DATE')
        cut = int(len(pool) * 0.85)
        tr, cal = pool.iloc[:cut], pool.iloc[cut:]
        Xtr, Xcal, Xte = prep(tr, cal, test, fc)
        point = {'label': label, 'n_train': len(tr), 'models': {}}
        for model in models:
            runs = [eval_on(*fit_calibrated(
                Xtr, tr['TARGET_WIN'].values, tr['TARGET_MARGIN'].values,
                Xcal, cal['TARGET_WIN'].values, cal['TARGET_MARGIN'].values, model, s),
                Xte, test['TARGET_WIN'].values, test['TARGET_MARGIN'].values) for s in seeds]
            point['models'][model] = agg(runs, METRIC_KEYS)
        results['points'].append(point)
        print(f"{label:<34} n_train={len(tr):>5}  " +
              "  ".join(f"{m}:acc={point['models'][m]['acc']['mean']:.3f},"
                       f"mae={point['models'][m]['mae']['mean']:.2f},"
                       f"ece={point['models'][m]['ece']['mean']:.3f},"
                       f"cov90={point['models'][m]['cov90']['mean']:.2f}" for m in models))
    return results


# ---------------------------------------------------------------------------
# MODE: regime  (regular vs play-in vs playoffs)
# ---------------------------------------------------------------------------

def run_regime(seeds, models):
    df = load_labeled()
    fc = select_features(df.columns)

    # Identify each season's playoff period by year
    po = df[df['regime'] == 'playoffs'].copy()
    po['yr'] = po['GAME_DATE'].dt.year
    seasons = sorted(po['yr'].unique())

    # Per-season test predictions, pooled by regime
    pooled = {model: {'regular': [], 'playin': [], 'playoffs': []} for model in models}
    # store raw per-game predictions (cal_p, margin, y) per regime per model for pooled metrics
    pooled_raw = {model: {r: {'cal_p': [], 'margin': [], 'ywin': [], 'ymargin': [],
                              'hw80': [], 'hw90': []}
                          for r in ['regular', 'playin', 'playoffs']} for model in models}

    feat_shift = None
    for yr in seasons:
        po_start = po[po['yr'] == yr]['GAME_DATE'].min()
        # Train: regular games strictly before this season's playoffs
        train_pool = df[(df['regime'] == 'regular') & (df['GAME_DATE'] < po_start)].sort_values('GAME_DATE')
        if len(train_pool) < 500:
            print(f'[skip] {yr} playoffs: only {len(train_pool)} regular train games before {po_start.date()}')
            continue
        cut = int(len(train_pool) * 0.85)
        tr, cal = train_pool.iloc[:cut], train_pool.iloc[cut:]

        # Test sets (all on/after po_start, same season)
        season_end = po_start + pd.Timedelta(days=70)
        test_reg = df[(df['regime'] == 'regular') & (df['GAME_DATE'] >= po_start - pd.Timedelta(days=21))
                      & (df['GAME_DATE'] < po_start)]  # control: last 3 weeks of regular season
        test_pi = df[(df['regime'] == 'playin') & (df['GAME_DATE'] >= po_start - pd.Timedelta(days=7))
                     & (df['GAME_DATE'] <= season_end)]
        test_po = po[(po['yr'] == yr)]

        Xtr, Xcal, _ = prep(tr, cal, tr.iloc[:1], fc)  # fit imputer/scaler on train
        vc = tr[fc].columns[tr[fc].notna().any()].tolist()
        imp = SimpleImputer(strategy='median').fit(tr[vc])
        scl = StandardScaler().fit(imp.transform(tr[vc]))
        Xtr = scl.transform(imp.transform(tr[vc]))
        Xcal = scl.transform(imp.transform(cal[vc]))

        for model in models:
            for s in seeds:
                clf, reg, iso, hw = fit_calibrated(
                    Xtr, tr['TARGET_WIN'].values, tr['TARGET_MARGIN'].values,
                    Xcal, cal['TARGET_WIN'].values, cal['TARGET_MARGIN'].values, model, s)
                for rlabel, tdf in [('regular', test_reg), ('playin', test_pi), ('playoffs', test_po)]:
                    if len(tdf) == 0:
                        continue
                    Xte = scl.transform(imp.transform(tdf[vc]))
                    raw_p = clf.predict_proba(Xte)[:, 1]
                    cal_p = np.clip(iso.predict(raw_p), 0, 1)
                    margin = reg.predict(Xte)
                    # pool only first-seed predictions for the pooled metric set (avoid seed dup);
                    # use all seeds for the per-season aggregate below
                    if s == seeds[0]:
                        pr = pooled_raw[model][rlabel]
                        pr['cal_p'].append(cal_p); pr['margin'].append(margin)
                        pr['ywin'].append(tdf['TARGET_WIN'].values)
                        pr['ymargin'].append(tdf['TARGET_MARGIN'].values)
                        pr['hw80'].append(np.full(len(tdf), hw[80]))
                        pr['hw90'].append(np.full(len(tdf), hw[90]))
        print(f'{yr}: train={len(tr)} cal={len(cal)} | test reg={len(test_reg)} '
              f'playin={len(test_pi)} playoffs={len(test_po)} (po_start {po_start.date()})')

        # Feature shift: regular (control) vs playoffs, this season, a few key features
        if feat_shift is None:
            feat_shift = {}
        for feat in ['DIFF_ELO', 'HOME_pace_L10', 'DIFF_netRating_L10', 'DIFF_PTS_L10']:
            if feat in df.columns and len(test_reg) > 5 and len(test_po) > 5:
                ks = scistats.ks_2samp(test_reg[feat].dropna(), test_po[feat].dropna())
                feat_shift.setdefault(feat, []).append({'yr': int(yr), 'ks_stat': float(ks.statistic),
                                                        'ks_p': float(ks.pvalue)})

    # Pooled metrics per regime per model
    results = {'mode': 'regime', 'seeds': seeds, 'pooled': {},
               'feature_shift': feat_shift, 'run_at': datetime.now().isoformat(timespec='seconds')}
    print('\n=== Pooled cross-regime metrics (first-seed predictions, all seasons) ===')
    print(f"{'model':<5}{'regime':<10}{'n':>5}{'acc':>8}{'auc':>8}{'mae':>8}{'ece':>8}{'cov80':>8}{'cov90':>8}")
    for model in models:
        results['pooled'][model] = {}
        for rlabel in ['regular', 'playin', 'playoffs']:
            pr = pooled_raw[model][rlabel]
            if not pr['cal_p']:
                continue
            cal_p = np.concatenate(pr['cal_p']); margin = np.concatenate(pr['margin'])
            ywin = np.concatenate(pr['ywin']); ymargin = np.concatenate(pr['ymargin'])
            hw80 = np.concatenate(pr['hw80']); hw90 = np.concatenate(pr['hw90'])
            metrics = {
                'n': int(len(ywin)),
                'acc': float(((cal_p >= 0.5).astype(int) == ywin).mean()),
                'auc': float(roc_auc_score(ywin, cal_p)) if len(np.unique(ywin)) > 1 else float('nan'),
                'mae': float(np.abs(margin - ymargin).mean()),
                'ece': ece(ywin, cal_p),
                'cov80': float(((ymargin >= margin - hw80) & (ymargin <= margin + hw80)).mean()),
                'cov90': float(((ymargin >= margin - hw90) & (ymargin <= margin + hw90)).mean()),
            }
            results['pooled'][model][rlabel] = metrics
            print(f"{model:<5}{rlabel:<10}{metrics['n']:>5}{metrics['acc']:>8.3f}{metrics['auc']:>8.3f}"
                  f"{metrics['mae']:>8.2f}{metrics['ece']:>8.3f}{metrics['cov80']:>8.2f}{metrics['cov90']:>8.2f}")

    # Feature-shift summary
    print('\n=== Feature distribution shift (KS, regular control vs playoffs, mean over seasons) ===')
    if feat_shift:
        for feat, lst in feat_shift.items():
            mks = np.mean([d['ks_stat'] for d in lst]); mp = np.mean([d['ks_p'] for d in lst])
            print(f"  {feat:<22} KS={mks:.3f}  mean p={mp:.3f}")
    return results


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--mode', choices=['learning_curve', 'regime'], required=True)
    p.add_argument('--seeds', type=int, default=5)
    p.add_argument('--models', nargs='+', default=['RF', 'XGB'])
    p.add_argument('--out', default=None)
    args = p.parse_args()
    seeds = SEEDS[:args.seeds]
    if args.mode == 'learning_curve':
        res = run_learning_curve(seeds, args.models)
    else:
        res = run_regime(seeds, args.models)
    out = args.out or f'outputs/e15_{args.mode}.json'
    _os.makedirs('outputs', exist_ok=True)
    with open(out, 'w') as f:
        json.dump(res, f, indent=2)
    print(f'\nSaved -> {out}')


if __name__ == '__main__':
    main()
