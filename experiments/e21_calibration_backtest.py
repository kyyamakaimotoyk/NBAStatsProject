"""
E21 legs 1+2 — Multi-season calibration backtest + empirical guard threshold.

Loops the E20 protocol comparison over many monthly walk-forward windows across
the 2023-24, 2024-25 and 2025-26 seasons (multi-season feature CSV, built with
the production config). For each window: train strictly on everything before it,
then compare
    raw         - no calibration
    iso_eval    - production protocol (eval-slice isotonic, faithful mirror)
    platt_eval  - Platt (sigmoid on log-odds) fit on the SAME eval slice —
                  same data, different function class; isotonic's low-n
                  step-function variance is the suspected weakness.
(OOF isotonic was already rejected in E20 — 0/10 seeds vs eval_slice for XGB.)

Leg 2: every fit also records the calibrator's PICK-SHIFT on its eval slice —
the statistic the E20 degeneracy guard thresholds at ±10pp. The empirical
distribution across ~dozens of healthy fits replaces that round number with a
tail-derived cutoff, sanity-checked against the known degenerates (+14.2 fresh
XGB, +22 live stale RF).

Usage:
    python experiments/e21_calibration_backtest.py --csv nba_ml_features_multiseason.csv
"""
from __future__ import annotations

try:
    import torch  # noqa: F401  (import-order parity)
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
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.isotonic import IsotonicRegression

from core.features import select_features
from experiments.e13_calibration import expected_calibration_error  # noqa: F401 (via pick_metrics)
from experiments.e20_calibration import fit_predict, pick_metrics, flip_stats
from experiments.e21_online_pilot import fit_platt

SEEDS = [42, 123, 456]
MIN_TEST_GAMES = 50
MIN_TRAIN_GAMES = 800


def month_windows(dates: pd.Series):
    """Calendar-month test windows with enough games, oldest first."""
    months = sorted({(d.year, d.month) for d in dates})
    out = []
    for y, m in months:
        start = pd.Timestamp(y, m, 1)
        end = start + pd.offsets.MonthEnd(1)
        out.append((start, end))
    return out


def run(csv_path, seeds, models, out_path):
    df = pd.read_csv(csv_path)
    df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])
    df = df.sort_values('GAME_DATE').reset_index(drop=True)
    feature_cols = select_features(df.columns)
    print(f'{csv_path}: {len(df)} games {df.GAME_DATE.min().date()} .. '
          f'{df.GAME_DATE.max().date()}, {len(feature_cols)} candidate features')

    results = {'csv': csv_path, 'seeds': seeds,
               'run_at': datetime.now().isoformat(timespec='seconds'), 'windows': []}

    for w_start, w_end in month_windows(df['GAME_DATE']):
        train_df = df[df['GAME_DATE'] < w_start]
        test_df = df[(df['GAME_DATE'] >= w_start) & (df['GAME_DATE'] <= w_end)]
        if len(test_df) < MIN_TEST_GAMES or len(train_df) < MIN_TRAIN_GAMES:
            continue

        valid_cols = train_df[feature_cols].columns[
            train_df[feature_cols].notna().any()].tolist()
        imp = SimpleImputer(strategy='median')
        scl = StandardScaler()
        X_tr = scl.fit_transform(imp.fit_transform(train_df[valid_cols]))
        X_te = scl.transform(imp.transform(test_df[valid_cols]))
        y_tr = train_df['TARGET_WIN'].values.astype(int)
        y_te = test_df['TARGET_WIN'].values.astype(int)

        w = {'window': str(w_start.date()), 'n_train': len(train_df),
             'n_test': len(test_df), 'home_rate': float(y_te.mean()), 'models': {}}
        for mt in models:
            rows = []
            for seed in seeds:
                p_raw = fit_predict(mt, seed, X_tr, y_tr, X_te)
                split = int(0.8 * len(X_tr))
                p_eval = fit_predict(mt, seed, X_tr[:split], y_tr[:split], X_tr[split:])
                y_eval = y_tr[split:]

                iso = IsotonicRegression(out_of_bounds='clip').fit(p_eval, y_eval)
                platt = fit_platt(p_eval, y_eval)
                p_iso, p_platt = iso.predict(p_raw), platt(p_raw)

                # Leg 2: pick-shift of each calibrator on ITS OWN eval slice
                # (exactly what the production guard measures at train time).
                shift_iso = float(np.mean(iso.predict(p_eval) > 0.5) - np.mean(p_eval > 0.5))
                shift_platt = float(np.mean(platt(p_eval) > 0.5) - np.mean(p_eval > 0.5))

                rows.append({'seed': seed,
                             'raw': pick_metrics(y_te, p_raw),
                             'iso_eval': pick_metrics(y_te, p_iso),
                             'platt_eval': pick_metrics(y_te, p_platt),
                             'flips_iso': flip_stats(y_te, p_raw, p_iso),
                             'flips_platt': flip_stats(y_te, p_raw, p_platt),
                             'shift_iso': shift_iso, 'shift_platt': shift_platt})
            w['models'][mt] = rows
            acc = {p: np.mean([r[p]['acc'] for r in rows])
                   for p in ('raw', 'iso_eval', 'platt_eval')}
            ece = {p: np.mean([r[p]['ece'] for r in rows])
                   for p in ('raw', 'iso_eval', 'platt_eval')}
            shifts = [r['shift_iso'] for r in rows]
            print(f"{w['window']} {mt}: n={len(test_df)} home={y_te.mean():.2f} | "
                  f"acc raw/iso/platt {acc['raw']:.3f}/{acc['iso_eval']:.3f}/{acc['platt_eval']:.3f} | "
                  f"ece {ece['raw']:.3f}/{ece['iso_eval']:.3f}/{ece['platt_eval']:.3f} | "
                  f"iso shift {np.mean(shifts):+.3f}")
        results['windows'].append(w)

    # ---- Leg 2 synthesis: empirical pick-shift distribution ----
    print('\n=== Pick-shift distribution across all healthy fits (leg 2) ===')
    for mt in models:
        for kind in ('shift_iso', 'shift_platt'):
            vals = np.array([abs(r[kind]) for w in results['windows']
                             for r in w['models'].get(mt, [])])
            if len(vals) == 0:
                continue
            print(f'{mt} {kind}: n={len(vals)} median={np.median(vals):.3f} '
                  f'p90={np.percentile(vals, 90):.3f} p99={np.percentile(vals, 99):.3f} '
                  f'max={vals.max():.3f}')

    _os.makedirs('outputs', exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f'\nSaved -> {out_path}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--csv', default='nba_ml_features_multiseason.csv')
    ap.add_argument('--models', nargs='+', default=['RF', 'XGB'])
    ap.add_argument('--seeds', type=int, default=3)
    ap.add_argument('--out', default='outputs/e21_backtest.json')
    args = ap.parse_args()
    run(args.csv, SEEDS[:args.seeds], args.models, args.out)


if __name__ == '__main__':
    main()
