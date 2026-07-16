"""Shared surface for the 2026-07 experiment loop.

One import point for the loop's harnesses (loop_ab, e22_perm_importance,
e24_hp_search):

  - Re-exports the validated E12-protocol pieces from ``e3_noise_ablation``
    (which stays byte-for-byte untouched — it is the instrument whose numbers
    anchor the tuning log). Cross-import is the repo idiom (e21 <- e20/e13).
  - Adds the primitives the loop needs beyond e3: the fixed W1-W5 windows,
    e21-style calendar-month windows with gating, frozen-CSV loading with
    provenance checks, train-only preprocessing, paired bootstrap CIs for
    accuracy/MAE deltas (non-inferiority needs CIs, not just p-values), and
    base-feature grouping for pruning.

Import this module FIRST in new experiment scripts: pulling in e3 triggers its
torch-before-pandas header and its chdir-to-project-root, both of which the
loop scripts rely on.
"""
from __future__ import annotations

import sys as _sys
import os as _os
_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)

# e3's module header imports torch before pandas (Windows MKL ordering) and
# chdirs to the project root. Do NOT import pandas/numpy before this line.
from experiments.e3_noise_ablation import (  # noqa: F401  (re-exports)
    PYTORCH_AVAILABLE,
    XGBOOST_AVAILABLE,
    SEEDS,
    N_BOOTSTRAP,
    TEST_START,
    TEST_END,
    RF_CLF_HP,
    RF_REG_HP,
    XGB_CLF_HP,
    XGB_REG_HP,
    NN_HP,
    bootstrap_metrics,
    mcnemar_test,
    paired_t_on_abs_err,
    bootstrap_auc_diff,
    train_and_predict,
)

import json
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler


# The e2 walk-forward windows, duplicated as data (e2 defines them inline with
# display names; these are the same five windows).
FIXED_WINDOWS = [
    {'name': 'W1', 'start': '2025-12-01', 'end': '2025-12-31'},
    {'name': 'W2', 'start': '2026-01-01', 'end': '2026-01-31'},
    {'name': 'W3', 'start': '2026-02-01', 'end': '2026-02-28'},
    {'name': 'W4', 'start': '2026-03-01', 'end': '2026-03-15'},
    {'name': 'W5', 'start': TEST_START, 'end': TEST_END},
]

MIN_TEST_GAMES = 50    # e21 gates
MIN_TRAIN_GAMES = 800


def month_windows(dates: pd.Series, min_test: int = MIN_TEST_GAMES,
                  min_train: int = MIN_TRAIN_GAMES,
                  start: str | None = None) -> list[dict]:
    """e21-style calendar-month test windows with gating, oldest first.

    Returns dicts {name, start, end, n_train, n_test}; a window qualifies when
    it has >= min_test games and >= min_train strictly-earlier games.
    ``start`` (e.g. '2023-10') drops windows before that month.
    """
    dates = pd.to_datetime(dates)
    months = sorted({(d.year, d.month) for d in dates})
    out = []
    for y, m in months:
        w_start = pd.Timestamp(y, m, 1)
        w_end = w_start + pd.offsets.MonthEnd(1)
        if start is not None and w_start < pd.Timestamp(start + '-01'):
            continue
        n_test = int(((dates >= w_start) & (dates <= w_end)).sum())
        n_train = int((dates < w_start).sum())
        if n_test < min_test or n_train < min_train:
            continue
        out.append({'name': f'{y:04d}-{m:02d}', 'start': str(w_start.date()),
                    'end': str(w_end.date()), 'n_train': n_train, 'n_test': n_test})
    return out


def load_frozen_csv(path: str) -> tuple[pd.DataFrame, dict]:
    """Load an exported feature snapshot + its provenance sidecar.

    Asserts the row count matches the sidecar (guards against a stale or
    half-written export). Returns (df sorted by GAME_DATE, meta dict).
    """
    df = pd.read_csv(path)
    df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])
    df = df.sort_values(['GAME_DATE', 'GAME_ID']).reset_index(drop=True)
    meta_path = path + '.meta.json'
    meta = {}
    if _os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
        if meta.get('n_rows') is not None and int(meta['n_rows']) != len(df):
            raise RuntimeError(
                f'{path}: row count {len(df)} != sidecar n_rows {meta["n_rows"]} '
                '- re-export the snapshot')
    return df, meta


def prepare_xy(train_df: pd.DataFrame, test_df: pd.DataFrame,
               feature_cols: list) -> tuple[np.ndarray, np.ndarray, list]:
    """e3's preprocessing semantics: drop all-NaN-in-train columns, median
    impute + standard scale FIT ON TRAIN ONLY. Returns (X_train, X_test,
    valid_cols)."""
    X_train_raw = train_df[feature_cols]
    valid_cols = X_train_raw.columns[X_train_raw.notna().any()].tolist()
    X_train_raw = X_train_raw[valid_cols]
    X_test_raw = test_df[valid_cols]
    imp = SimpleImputer(strategy='median')
    scl = StandardScaler()
    X_train = scl.fit_transform(imp.fit_transform(X_train_raw))
    X_test = scl.transform(imp.transform(X_test_raw))
    return X_train, X_test, valid_cols


def bootstrap_acc_diff(pred_a: np.ndarray, pred_b: np.ndarray,
                       y_clf: np.ndarray, n_bootstrap: int = N_BOOTSTRAP,
                       seed: int = 0):
    """Paired bootstrap on the accuracy delta (A - B), same games resampled.
    Returns (mean, ci_lo, ci_hi, p). pred_* are 0/1 labels."""
    correct_a = (pred_a == y_clf).astype(float)
    correct_b = (pred_b == y_clf).astype(float)
    delta = correct_a - correct_b
    n = len(delta)
    rng = np.random.default_rng(seed)
    means = np.empty(n_bootstrap)
    for b in range(n_bootstrap):
        idx = rng.integers(0, n, size=n)
        means[b] = delta[idx].mean()
    p = float(2 * min((means <= 0).mean(), (means >= 0).mean()))
    return (float(delta.mean()), float(np.percentile(means, 2.5)),
            float(np.percentile(means, 97.5)), p)


def bootstrap_mae_diff(reg_a: np.ndarray, reg_b: np.ndarray,
                       y_reg: np.ndarray, n_bootstrap: int = N_BOOTSTRAP,
                       seed: int = 0):
    """Paired bootstrap on the per-game |error| delta (A - B).
    Negative mean = A has smaller errors. Returns (mean, ci_lo, ci_hi, p)."""
    delta = np.abs(reg_a - y_reg) - np.abs(reg_b - y_reg)
    n = len(delta)
    rng = np.random.default_rng(seed)
    means = np.empty(n_bootstrap)
    for b in range(n_bootstrap):
        idx = rng.integers(0, n, size=n)
        means[b] = delta[idx].mean()
    p = float(2 * min((means <= 0).mean(), (means >= 0).mean()))
    return (float(delta.mean()), float(np.percentile(means, 2.5)),
            float(np.percentile(means, 97.5)), p)


def noninferiority_verdict(paired_entry: dict, margins: dict) -> dict:
    """Per-metric non-inferiority evaluation from a loop_ab paired entry.

    margins example: {'acc': -0.015, 'mae': 0.10} meaning: accuracy delta CI
    lower bound must stay above -1.5pp; MAE delta CI upper bound must stay
    below +0.10 points. AUC margin (if given) checks auc_diff_ci_lo.
    Also flags any paired test that is SIGNIFICANT AGAINST the arm.
    Returns {'pass': bool, 'checks': {...}}.
    """
    checks = {}
    if 'acc' in margins:
        lo = paired_entry.get('acc_diff_ci_lo')
        checks['acc_ci_above_margin'] = (lo is not None and lo > margins['acc'])
    if 'mae' in margins:
        hi = paired_entry.get('mae_diff_ci_hi')
        checks['mae_ci_below_margin'] = (hi is not None and hi < margins['mae'])
    if 'auc' in margins:
        lo = paired_entry.get('auc_diff_ci_lo')
        checks['auc_ci_above_margin'] = (lo is not None and lo > margins['auc'])
    # Significant regressions (tests pointing AGAINST the arm at p<0.05)
    mc_p = paired_entry.get('mcnemar_p')
    against_acc = (mc_p is not None and mc_p < 0.05
                   and (paired_entry.get('base_wins') or 0) > (paired_entry.get('cfg_wins') or 0))
    t_p = paired_entry.get('paired_t_p')
    against_mae = (t_p is not None and t_p < 0.05
                   and (paired_entry.get('mae_diff_mean') or 0) > 0)
    auc_hi = paired_entry.get('auc_diff_ci_hi')
    against_auc = (auc_hi is not None and auc_hi < 0)
    checks['no_significant_regression'] = not (against_acc or against_mae or against_auc)
    return {'pass': all(checks.values()), 'checks': checks}


def feature_group(col: str) -> str:
    """Base feature group: strip one leading HOME_/AWAY_/DIFF_ prefix.

    HOME_PTS_L10 / AWAY_PTS_L10 / DIFF_PTS_L10 -> PTS_L10 (one group), so
    pruning keeps or drops the correlated triplet together. Columns without
    a prefix (e.g. ELO_DIFF) are their own group.
    """
    for prefix in ('HOME_', 'AWAY_', 'DIFF_'):
        if col.startswith(prefix):
            return col[len(prefix):]
    return col
