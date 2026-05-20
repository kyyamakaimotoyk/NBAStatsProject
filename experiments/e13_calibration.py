"""
E13 (Phase 2a) — Classifier calibration diagnostic.

Question: is `predict_proba` honest? When RF/XGB say "70% home win", do those
games actually win ~70% of the time? If not, the win-probability outputs (and
any downstream betting/decision logic) are systematically over- or under-confident.

Method:
  - Train RF + XGB on games before W5 (2026-03-15), production feature config
    (E9 on, E10/E11 off via core.features defaults), N seeds.
  - Predict on the W5 test set (2026-03-15 -> 2026-04-15).
  - Average predicted probabilities across seeds.
  - Reliability curve: bin predictions into deciles, plot mean(predicted) vs
    observed win-rate per bin.
  - Expected Calibration Error (ECE): sum over bins of
        (bin_count / N) * |mean_pred_bin - obs_rate_bin|
  - Brier score: mean((pred - actual)^2). Lower = better; combines calibration
    + sharpness.
  - Compare raw vs isotonic-recalibrated (fit isotonic on a temporal calibration
    slice, the month before W5, to avoid fitting on the test set).

Output: JSON with per-model reliability bins + ECE + Brier (raw and isotonic),
plus a text summary. No plotting dependency — bins are emitted as a table the
caller can render.

Usage:
    python experiments/e13_calibration.py --seeds 10
"""
from __future__ import annotations

# torch first (Windows MKL order) — not used here but keeps import parity
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
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False

from core.features import select_features

TEST_START = '2026-03-15'
TEST_END = '2026-04-15'
# Calibration slice: the month before the test window, held out of training for
# isotonic fitting (so we never fit the recalibrator on the test set).
CALIB_START = '2026-02-15'
CALIB_END = '2026-03-15'
SEEDS = [42, 123, 456, 789, 1000, 2024, 31337, 65535, 8675309, 99999]

RF_CLF_HP = {'n_estimators': 100, 'max_depth': 5, 'min_samples_leaf': 20}
XGB_CLF_HP = {'n_estimators': 200, 'max_depth': 4, 'learning_rate': 0.1,
              'min_child_weight': 10, 'subsample': 0.8, 'colsample_bytree': 0.8,
              'reg_lambda': 1.0, 'eval_metric': 'logloss'}


def reliability_bins(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10):
    """Equal-width bins on [0,1]. Returns list of dicts per non-empty bin."""
    edges = np.linspace(0, 1, n_bins + 1)
    out = []
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (y_prob >= lo) & (y_prob < hi if i < n_bins - 1 else y_prob <= hi)
        n = int(mask.sum())
        if n == 0:
            continue
        out.append({
            'bin_lo': float(lo), 'bin_hi': float(hi), 'n': n,
            'mean_pred': float(y_prob[mask].mean()),
            'obs_rate': float(y_true[mask].mean()),
        })
    return out


def expected_calibration_error(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10):
    bins = reliability_bins(y_true, y_prob, n_bins)
    n_total = len(y_true)
    ece = sum((b['n'] / n_total) * abs(b['mean_pred'] - b['obs_rate']) for b in bins)
    return float(ece)


def train_proba(model_type, X_train, y_train, X_eval, seed):
    if model_type == 'RF':
        m = RandomForestClassifier(**RF_CLF_HP, random_state=seed, n_jobs=-1)
    elif model_type == 'XGB':
        m = xgb.XGBClassifier(**XGB_CLF_HP, random_state=seed, n_jobs=-1)
    else:
        raise ValueError(model_type)
    m.fit(X_train, y_train)
    return m.predict_proba(X_eval)[:, 1]


def run(csv_path: str, seeds: list, models: list, n_bins: int = 10):
    df = pd.read_csv(csv_path)
    df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])

    feature_cols = select_features(df.columns)  # production config

    train_df = df[df['GAME_DATE'] < CALIB_START].copy()
    calib_df = df[(df['GAME_DATE'] >= CALIB_START) & (df['GAME_DATE'] < CALIB_END)].copy()
    test_df = df[(df['GAME_DATE'] >= TEST_START) & (df['GAME_DATE'] <= TEST_END)].copy()

    valid_cols = train_df[feature_cols].columns[train_df[feature_cols].notna().any()].tolist()

    imp = SimpleImputer(strategy='median')
    scl = StandardScaler()
    X_train = scl.fit_transform(imp.fit_transform(train_df[valid_cols]))
    X_calib = scl.transform(imp.transform(calib_df[valid_cols]))
    X_test = scl.transform(imp.transform(test_df[valid_cols]))

    y_train = train_df['TARGET_WIN'].values.astype(int)
    y_calib = calib_df['TARGET_WIN'].values.astype(int)
    y_test = test_df['TARGET_WIN'].values.astype(int)

    print(f'Train(<{CALIB_START}): {len(train_df)} | Calib({CALIB_START}..{CALIB_END}): {len(calib_df)} | Test(W5): {len(test_df)}')
    print(f'Features: {len(valid_cols)} (production config)\n')

    results = {'csv': csv_path, 'n_train': len(train_df), 'n_calib': len(calib_df),
               'n_test': len(test_df), 'n_features': len(valid_cols),
               'seeds': seeds, 'models': {}, 'run_at': datetime.now().isoformat(timespec='seconds')}

    for mt in models:
        # Average probability across seeds for both calib and test
        calib_probs = np.mean([train_proba(mt, X_train, y_train, X_calib, s) for s in seeds], axis=0)
        test_probs = np.mean([train_proba(mt, X_train, y_train, X_test, s) for s in seeds], axis=0)

        # Raw metrics
        raw_ece = expected_calibration_error(y_test, test_probs, n_bins)
        raw_brier = float(brier_score_loss(y_test, test_probs))
        raw_bins = reliability_bins(y_test, test_probs, n_bins)

        # Isotonic recalibration: fit on calib slice, apply to test
        iso = IsotonicRegression(out_of_bounds='clip')
        iso.fit(calib_probs, y_calib)
        test_probs_iso = iso.predict(test_probs)
        iso_ece = expected_calibration_error(y_test, test_probs_iso, n_bins)
        iso_brier = float(brier_score_loss(y_test, test_probs_iso))
        iso_bins = reliability_bins(y_test, test_probs_iso, n_bins)

        results['models'][mt] = {
            'raw': {'ece': raw_ece, 'brier': raw_brier, 'bins': raw_bins},
            'isotonic': {'ece': iso_ece, 'brier': iso_brier, 'bins': iso_bins},
        }

        print(f'=== {mt} ===')
        print(f'  RAW:      ECE={raw_ece:.4f}  Brier={raw_brier:.4f}')
        print(f'  ISOTONIC: ECE={iso_ece:.4f}  Brier={iso_brier:.4f}')
        print(f'  Reliability (raw): predicted -> observed')
        for b in raw_bins:
            bar = '#' * int(b['n'] / max(1, len(y_test)) * 40)
            print(f'    [{b["bin_lo"]:.1f}-{b["bin_hi"]:.1f}] n={b["n"]:3d} '
                  f'pred={b["mean_pred"]:.3f} obs={b["obs_rate"]:.3f} '
                  f'gap={b["mean_pred"]-b["obs_rate"]:+.3f} {bar}')
        print()

    return results


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--csv', default='nba_ml_features.csv')
    p.add_argument('--seeds', type=int, default=10)
    p.add_argument('--models', nargs='+', default=['RF', 'XGB'])
    p.add_argument('--out', default='outputs/e13_calibration.json')
    args = p.parse_args()

    res = run(args.csv, SEEDS[:args.seeds], args.models)
    _os.makedirs('outputs', exist_ok=True)
    with open(args.out, 'w') as f:
        json.dump(res, f, indent=2)
    print(f'Saved -> {args.out}')


if __name__ == '__main__':
    main()
