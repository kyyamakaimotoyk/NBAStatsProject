"""
E14 (Phase 2b) - Prediction intervals for the point margin.

The regressor currently emits a single number ("home by 6.2"). This adds an
honest *range* around it ("home by 6.2, 80% interval [-7, +19]") with a
validated coverage guarantee, so the dashboard can show a margin distribution
vs the Vegas line instead of a bare point estimate.

Two methods, simplest first (per the noise-aware ethos - measure what adaptivity buys):

  1. SPLIT CONFORMAL (constant width)
     - Train point regressor f on the train set.
     - On a held-out calibration set, residuals r_i = |y_i - f(x_i)|.
     - q = the (1-alpha) empirical quantile of {r_i} (finite-sample corrected).
     - Interval for a new game: [f(x) - q, f(x) + q]. Same half-width q for every game.
     - Guarantee: P(y in interval) >= 1-alpha under exchangeability.

  2. CQR (Conformalized Quantile Regression, adaptive width)
     - Train quantile regressors q_lo (alpha/2) and q_hi (1-alpha/2).
     - Calibration conformity score E_i = max(q_lo(x_i) - y_i, y_i - q_hi(x_i)).
     - Q = (1-alpha) quantile of {E_i}.
     - Interval: [q_lo(x) - Q, q_hi(x) + Q]. Width varies per game (wider for
       uncertain games), still with the coverage guarantee.

We validate EMPIRICAL coverage on the W5 test set (does the 80% interval really
contain ~80% of actual margins?) - because the exchangeability assumption is only
approximately true for time series, we trust the measured coverage, not the theorem.

Split: train < 2026-01-01 | calibrate 2026-01-01..2026-03-15 | test W5 (03-15..04-15).
Models: RF + XGB point regressors (split conformal); XGB quantile heads (CQR).

Usage:
    python experiments/e14_intervals.py --seeds 5
"""
from __future__ import annotations

try:
    import torch  # noqa: F401  (import-order parity on Windows)
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
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

import xgboost as xgb

from core.features import select_features

TRAIN_END = '2026-01-01'
CALIB_START = '2026-01-01'
CALIB_END = '2026-03-15'
TEST_START = '2026-03-15'
TEST_END = '2026-04-15'
SEEDS = [42, 123, 456, 789, 1000, 2024, 31337, 65535, 8675309, 99999]
LEVELS = [0.80, 0.90]  # nominal coverage levels

RF_REG_HP = {'n_estimators': 100, 'max_depth': 5, 'min_samples_leaf': 20}
XGB_REG_HP = {'n_estimators': 200, 'max_depth': 4, 'learning_rate': 0.1,
              'min_child_weight': 10, 'subsample': 0.8, 'colsample_bytree': 0.8,
              'reg_lambda': 1.0}


def conformal_quantile(scores: np.ndarray, alpha: float) -> float:
    """Finite-sample-corrected (1-alpha) quantile of conformity scores."""
    n = len(scores)
    # rank = ceil((n+1)(1-alpha)); use that order statistic
    k = int(np.ceil((n + 1) * (1 - alpha)))
    k = min(k, n)  # clip; if k>n the interval is unbounded -> use max
    return float(np.sort(scores)[k - 1])


def split_conformal(point_pred_cal, y_cal, point_pred_test, alpha):
    """Returns (lo, hi, halfwidth) arrays for the test set."""
    resid = np.abs(y_cal - point_pred_cal)
    q = conformal_quantile(resid, alpha)
    lo = point_pred_test - q
    hi = point_pred_test + q
    return lo, hi, np.full_like(point_pred_test, q)


def cqr(qlo_cal, qhi_cal, y_cal, qlo_test, qhi_test, alpha):
    """Conformalized quantile regression intervals for the test set."""
    E = np.maximum(qlo_cal - y_cal, y_cal - qhi_cal)
    Q = conformal_quantile(E, alpha)
    lo = qlo_test - Q
    hi = qhi_test + Q
    return lo, hi


def coverage_and_width(y, lo, hi):
    inside = (y >= lo) & (y <= hi)
    return float(inside.mean()), float(np.mean(hi - lo))


def fit_predict_rf(Xtr, ytr, Xcal, Xte, seed):
    m = RandomForestRegressor(**RF_REG_HP, random_state=seed, n_jobs=-1)
    m.fit(Xtr, ytr)
    return m.predict(Xcal), m.predict(Xte)


def fit_predict_xgb_point(Xtr, ytr, Xcal, Xte, seed):
    m = xgb.XGBRegressor(**XGB_REG_HP, random_state=seed, n_jobs=-1)
    m.fit(Xtr, ytr)
    return m.predict(Xcal), m.predict(Xte)


def fit_predict_xgb_quantile(Xtr, ytr, Xcal, Xte, q, seed):
    m = xgb.XGBRegressor(objective='reg:quantileerror', quantile_alpha=q,
                         **XGB_REG_HP, random_state=seed, n_jobs=-1)
    m.fit(Xtr, ytr)
    return m.predict(Xcal), m.predict(Xte)


def run(csv_path: str, seeds: list):
    df = pd.read_csv(csv_path)
    df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])
    fc = select_features(df.columns)

    tr = df[df['GAME_DATE'] < TRAIN_END]
    cal = df[(df['GAME_DATE'] >= CALIB_START) & (df['GAME_DATE'] < CALIB_END)]
    te = df[(df['GAME_DATE'] >= TEST_START) & (df['GAME_DATE'] <= TEST_END)]

    vc = tr[fc].columns[tr[fc].notna().any()].tolist()
    imp = SimpleImputer(strategy='median'); scl = StandardScaler()
    Xtr = scl.fit_transform(imp.fit_transform(tr[vc]))
    Xcal = scl.transform(imp.transform(cal[vc]))
    Xte = scl.transform(imp.transform(te[vc]))
    ytr = tr['TARGET_MARGIN'].values.astype(float)
    ycal = cal['TARGET_MARGIN'].values.astype(float)
    yte = te['TARGET_MARGIN'].values.astype(float)

    print(f'Train(<{TRAIN_END}): {len(tr)} | Calib({CALIB_START}..{CALIB_END}): {len(cal)} | Test(W5): {len(te)}')
    print(f'Features: {len(vc)}\n')

    results = {'csv': csv_path, 'n_train': len(tr), 'n_calib': len(cal), 'n_test': len(te),
               'levels': LEVELS, 'seeds': seeds, 'methods': {},
               'run_at': datetime.now().isoformat(timespec='seconds')}

    # ---- Split conformal on RF + XGB point regressors ----
    for model_name, fitfn in [('RF_splitconf', fit_predict_rf),
                              ('XGB_splitconf', fit_predict_xgb_point)]:
        per_level = {f'{int(l*100)}': {'coverage': [], 'width': []} for l in LEVELS}
        for seed in seeds:
            pc, pt = fitfn(Xtr, ytr, Xcal, Xte, seed)
            for l in LEVELS:
                lo, hi, _ = split_conformal(pc, ycal, pt, alpha=1 - l)
                cov, wid = coverage_and_width(yte, lo, hi)
                per_level[f'{int(l*100)}']['coverage'].append(cov)
                per_level[f'{int(l*100)}']['width'].append(wid)
        results['methods'][model_name] = {
            lvl: {'coverage_mean': float(np.mean(d['coverage'])),
                  'coverage_std': float(np.std(d['coverage'])),
                  'width_mean': float(np.mean(d['width'])),
                  'width_std': float(np.std(d['width']))}
            for lvl, d in per_level.items()
        }

    # ---- CQR with XGB quantile heads ----
    per_level = {f'{int(l*100)}': {'coverage': [], 'width': []} for l in LEVELS}
    cqr_example_intervals = None
    for seed in seeds:
        for l in LEVELS:
            a = 1 - l
            qlo_c, qlo_t = fit_predict_xgb_quantile(Xtr, ytr, Xcal, Xte, a / 2, seed)
            qhi_c, qhi_t = fit_predict_xgb_quantile(Xtr, ytr, Xcal, Xte, 1 - a / 2, seed)
            lo, hi = cqr(qlo_c, qhi_c, ycal, qlo_t, qhi_t, alpha=a)
            cov, wid = coverage_and_width(yte, lo, hi)
            per_level[f'{int(l*100)}']['coverage'].append(cov)
            per_level[f'{int(l*100)}']['width'].append(wid)
            if seed == seeds[0] and l == 0.80:
                cqr_example_intervals = (lo, hi)
    results['methods']['XGB_CQR'] = {
        lvl: {'coverage_mean': float(np.mean(d['coverage'])),
              'coverage_std': float(np.std(d['coverage'])),
              'width_mean': float(np.mean(d['width'])),
              'width_std': float(np.std(d['width']))}
        for lvl, d in per_level.items()
    }

    # ---- Console summary ----
    print(f"{'method':<16}{'level':>7}{'nominal':>9}{'empirical cov':>16}{'mean width':>13}")
    print('-' * 62)
    for method, levels_d in results['methods'].items():
        for lvl, m in sorted(levels_d.items()):
            print(f"{method:<16}{lvl+'%':>7}{'':>9}"
                  f"{m['coverage_mean']*100:>10.1f}+/-{m['coverage_std']*100:.1f}%"
                  f"{m['width_mean']:>11.1f}+/-{m['width_std']:.1f}")
    print()

    # ---- Real-game examples (CQR 80%, first seed) ----
    if cqr_example_intervals is not None:
        lo, hi = cqr_example_intervals
        from sqlalchemy import text
        from core.db import get_engine
        with get_engine().connect() as c:
            gl = pd.read_sql(text('SELECT GAME_ID, MATCHUP FROM game_list WHERE MATCHUP LIKE "%vs.%"'), c)
        gl['GAME_ID'] = gl['GAME_ID'].astype('int64')
        ex = te[['GAME_ID', 'GAME_DATE']].copy()
        ex['GAME_ID'] = ex['GAME_ID'].astype('int64')
        ex = ex.merge(gl, on='GAME_ID', how='left')
        ex['lo'] = lo; ex['hi'] = hi; ex['actual'] = yte
        ex['inside'] = (ex['actual'] >= ex['lo']) & (ex['actual'] <= ex['hi'])
        sasokc = ex[ex['MATCHUP'].str.contains('SAS|OKC', na=False)].head(6)
        print('CQR 80% intervals - real games (margin = home - away):')
        for _, r in sasokc.iterrows():
            mark = 'OK ' if r['inside'] else 'MISS'
            print(f"  {r['GAME_DATE'].date()} {r['MATCHUP']:<14} "
                  f"80% interval [{r['lo']:+.0f}, {r['hi']:+.0f}]  actual {r['actual']:+.0f}  {mark}")
        results['cqr_examples'] = [
            {'date': str(r['GAME_DATE'].date()), 'matchup': r['MATCHUP'],
             'lo': float(r['lo']), 'hi': float(r['hi']), 'actual': float(r['actual']),
             'inside': bool(r['inside'])}
            for _, r in sasokc.iterrows()
        ]

    return results


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--csv', default='nba_ml_features.csv')
    p.add_argument('--seeds', type=int, default=5)
    p.add_argument('--out', default='outputs/e14_intervals.json')
    args = p.parse_args()
    res = run(args.csv, SEEDS[:args.seeds])
    _os.makedirs('outputs', exist_ok=True)
    with open(args.out, 'w') as f:
        json.dump(res, f, indent=2)
    print(f'Saved -> {args.out}')


if __name__ == '__main__':
    main()
