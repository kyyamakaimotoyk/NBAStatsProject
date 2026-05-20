"""
E3 — Noise-aware feature-ablation study.

Question: of the E9 / E10 / E11 (and optionally E7) feature additions, which
survive a properly-noisy walk-forward measurement? Single-run W5 deltas of
<1pp are within seed + test-sample variance; we need multi-seed + bootstrap
test-set resampling to tell signal from noise.

What this script does:
  - For each toggle config (8 combinations of E9/E10/E11 on/off):
      For each of N=10 seeds:
          Train fresh RF, XGB, NN on games before W5 start (2026-03-15)
          Predict on the 230 W5 test games
          Cache (clf_proba, reg_pred) per (config, seed, model)
  - Bootstrap-resample the test set K=1000 times for each cached prediction.
    For each (config, model, metric): pool 10 seeds * 1000 bootstraps =
    10,000 metric measurements -> mean + 95% CI.
  - Paired comparisons baseline-vs-each-config:
      Accuracy: paired McNemar on game-level agreement (matched seed).
      MAE:      paired t-test on per-game |error| diffs (averaged over seeds).
      AUC:      bootstrap on the AUC delta.
  - Writes a JSON results file + a markdown summary table.

To run for the E7 ablation, point --csv at the alternate CSV:
  python experiments/e3_noise_ablation.py --csv nba_ml_features.csv      [E7-on]
  python experiments/e3_noise_ablation.py --csv nba_ml_features_no_e7.csv [E7-off]

Compute budget: ~20-25 min per CSV on a 24-core machine (8 configs * 10 seeds *
3 models ~= 240 quick model trainings on a 6000-row train set).
"""
from __future__ import annotations

import sys as _sys
import os as _os
_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _PROJECT_ROOT)
if _os.getcwd() != _PROJECT_ROOT:
    _os.chdir(_PROJECT_ROOT)

# PyTorch MUST be imported before numpy/pandas on Windows (MKL/Intel OMP order)
try:
    import torch
    import torch.nn as nn
    PYTORCH_AVAILABLE = True
except (ImportError, OSError):
    PYTORCH_AVAILABLE = False

import argparse
import json
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats as scistats
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, roc_auc_score, mean_absolute_error

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False

from core.features import select_features


# ============================================================================
# CONFIG
# ============================================================================

TEST_START = '2026-03-15'
TEST_END = '2026-04-15'
SEEDS = [42, 123, 456, 789, 1000, 2024, 31337, 65535, 8675309, 99999]
N_BOOTSTRAP = 1000

# Each tuple: (label, enable_e9, enable_e10, enable_e11)
ABLATION_CONFIGS = [
    ('baseline',         False, False, False),
    ('E9_only',          True,  False, False),
    ('E10_only',         False, True,  False),
    ('E11_only',         False, False, True),
    ('E9+E10',           True,  True,  False),
    ('E9+E11',           True,  False, True),
    ('E10+E11',          False, True,  True),
    ('E9+E10+E11_full',  True,  True,  True),
]

RF_CLF_HP = {'n_estimators': 100, 'max_depth': 5, 'min_samples_leaf': 20}
RF_REG_HP = {'n_estimators': 100, 'max_depth': 5, 'min_samples_leaf': 20}
XGB_CLF_HP = {'n_estimators': 200, 'max_depth': 4, 'learning_rate': 0.1,
              'min_child_weight': 10, 'subsample': 0.8, 'colsample_bytree': 0.8,
              'reg_lambda': 1.0, 'eval_metric': 'logloss'}
XGB_REG_HP = {'n_estimators': 200, 'max_depth': 4, 'learning_rate': 0.1,
              'min_child_weight': 10, 'subsample': 0.8, 'colsample_bytree': 0.8,
              'reg_lambda': 1.0}
NN_HP = {'hidden_dims': [128, 64, 32], 'dropout': 0.5, 'lr': 0.001,
         'weight_decay': 1e-4, 'epochs': 100, 'patience': 15}


# ============================================================================
# MODELS
# ============================================================================

if PYTORCH_AVAILABLE:
    class NBAClassifier(nn.Module):
        def __init__(self, input_dim, hidden_dims, dropout):
            super().__init__()
            layers = []
            prev = input_dim
            for h in hidden_dims:
                layers += [nn.Linear(prev, h), nn.BatchNorm1d(h),
                           nn.ReLU(), nn.Dropout(dropout)]
                prev = h
            layers.append(nn.Linear(prev, 1))
            self.net = nn.Sequential(*layers)

        def forward(self, x):
            return self.net(x)

    class NBARegressor(nn.Module):
        def __init__(self, input_dim, hidden_dims, dropout):
            super().__init__()
            layers = []
            prev = input_dim
            for h in hidden_dims:
                layers += [nn.Linear(prev, h), nn.BatchNorm1d(h),
                           nn.ReLU(), nn.Dropout(dropout)]
                prev = h
            layers.append(nn.Linear(prev, 1))
            self.net = nn.Sequential(*layers)

        def forward(self, x):
            return self.net(x)


def _train_nn(X_train, y_train, X_test, seed, is_classifier=True):
    """Train NN on (X_train, y_train), return predictions on X_test.
    For classifier: returns prob of class 1. For regressor: returns predicted margin."""
    torch.manual_seed(seed)
    np.random.seed(seed)
    if torch.backends.cudnn.is_available():
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False

    n, d = X_train.shape

    # 80/20 train/val split for early stopping
    rng = np.random.default_rng(seed)
    idx = rng.permutation(n)
    cut = int(n * 0.8)
    tr_idx, va_idx = idx[:cut], idx[cut:]

    X_tr = torch.tensor(X_train[tr_idx], dtype=torch.float32)
    y_tr = torch.tensor(y_train[tr_idx], dtype=torch.float32).unsqueeze(1)
    X_va = torch.tensor(X_train[va_idx], dtype=torch.float32)
    y_va = torch.tensor(y_train[va_idx], dtype=torch.float32).unsqueeze(1)

    cls = NBAClassifier if is_classifier else NBARegressor
    model = cls(d, NN_HP['hidden_dims'], NN_HP['dropout'])
    opt = torch.optim.Adam(model.parameters(), lr=NN_HP['lr'], weight_decay=NN_HP['weight_decay'])
    loss_fn = nn.BCEWithLogitsLoss() if is_classifier else nn.MSELoss()

    best_va = float('inf'); patience = 0; best_state = None
    for epoch in range(NN_HP['epochs']):
        model.train()
        opt.zero_grad()
        out = model(X_tr)
        loss = loss_fn(out, y_tr)
        loss.backward(); opt.step()

        model.eval()
        with torch.no_grad():
            va_out = model(X_va)
            va_loss = loss_fn(va_out, y_va).item()
        if va_loss < best_va - 1e-5:
            best_va = va_loss; patience = 0
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
        else:
            patience += 1
            if patience >= NN_HP['patience']:
                break

    if best_state is not None:
        model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        out_test = model(torch.tensor(X_test, dtype=torch.float32))
        if is_classifier:
            return torch.sigmoid(out_test).numpy().flatten()
        return out_test.numpy().flatten()


def train_and_predict(X_train, y_clf_train, y_reg_train, X_test, model_type, seed):
    """Returns (clf_proba_on_test, reg_pred_on_test)."""
    if model_type == 'RF':
        clf = RandomForestClassifier(**RF_CLF_HP, random_state=seed, n_jobs=-1)
        reg = RandomForestRegressor(**RF_REG_HP, random_state=seed, n_jobs=-1)
        clf.fit(X_train, y_clf_train); reg.fit(X_train, y_reg_train)
        return clf.predict_proba(X_test)[:, 1], reg.predict(X_test)
    elif model_type == 'XGB':
        clf = xgb.XGBClassifier(**XGB_CLF_HP, random_state=seed, n_jobs=-1)
        reg = xgb.XGBRegressor(**XGB_REG_HP, random_state=seed, n_jobs=-1)
        clf.fit(X_train, y_clf_train); reg.fit(X_train, y_reg_train)
        return clf.predict_proba(X_test)[:, 1], reg.predict(X_test)
    elif model_type == 'NN':
        clf_proba = _train_nn(X_train, y_clf_train, X_test, seed, is_classifier=True)
        reg_pred = _train_nn(X_train, y_reg_train, X_test, seed, is_classifier=False)
        return clf_proba, reg_pred
    else:
        raise ValueError(f'Unknown model_type: {model_type}')


# ============================================================================
# BOOTSTRAP + STATISTICAL TESTS
# ============================================================================

def bootstrap_metrics(clf_proba: np.ndarray, reg_pred: np.ndarray,
                      y_clf: np.ndarray, y_reg: np.ndarray,
                      n_bootstrap: int = N_BOOTSTRAP, seed_offset: int = 0):
    """For one (config, model, seed) prediction set: bootstrap-resample test
    set N times, compute acc/auc/mae each time. Returns dict with arrays."""
    n = len(y_clf)
    rng = np.random.default_rng(seed_offset)
    accs = np.empty(n_bootstrap)
    aucs = np.empty(n_bootstrap)
    maes = np.empty(n_bootstrap)
    clf_pred_label = (clf_proba >= 0.5).astype(int)
    abs_err = np.abs(reg_pred - y_reg)
    for b in range(n_bootstrap):
        idx = rng.integers(0, n, size=n)
        accs[b] = (clf_pred_label[idx] == y_clf[idx]).mean()
        # AUC needs both classes present in resample
        try:
            aucs[b] = roc_auc_score(y_clf[idx], clf_proba[idx])
        except ValueError:
            aucs[b] = np.nan
        maes[b] = abs_err[idx].mean()
    return {'acc': accs, 'auc': aucs, 'mae': maes}


def mcnemar_test(pred_a: np.ndarray, pred_b: np.ndarray, y_true: np.ndarray):
    """Paired McNemar's test on classification correctness.
    pred_a/b are 0/1 predictions. Returns (statistic, p_value, b, c)
    where b = # games A right, B wrong; c = # games A wrong, B right."""
    a_correct = (pred_a == y_true)
    b_correct = (pred_b == y_true)
    b_count = int(np.sum(a_correct & ~b_correct))   # A right, B wrong
    c_count = int(np.sum(~a_correct & b_correct))   # A wrong, B right
    if b_count + c_count == 0:
        return 0.0, 1.0, b_count, c_count
    # Continuity-corrected McNemar
    stat = (abs(b_count - c_count) - 1) ** 2 / (b_count + c_count)
    p = scistats.chi2.sf(stat, 1)
    return stat, p, b_count, c_count


def paired_t_on_abs_err(reg_a: np.ndarray, reg_b: np.ndarray, y_reg: np.ndarray):
    """Paired t-test on per-game |error| diffs.
    Negative t / mean_diff = A has SMALLER errors than B."""
    err_a = np.abs(reg_a - y_reg)
    err_b = np.abs(reg_b - y_reg)
    diff = err_a - err_b
    t, p = scistats.ttest_rel(err_a, err_b)
    return float(t), float(p), float(diff.mean()), float(diff.std(ddof=1))


def bootstrap_auc_diff(proba_a: np.ndarray, proba_b: np.ndarray, y_clf: np.ndarray,
                       n_bootstrap: int = N_BOOTSTRAP, seed: int = 0):
    """Bootstrap the AUC_a - AUC_b difference and its 95% CI."""
    n = len(y_clf)
    rng = np.random.default_rng(seed)
    diffs = np.empty(n_bootstrap)
    for b in range(n_bootstrap):
        idx = rng.integers(0, n, size=n)
        try:
            auc_a = roc_auc_score(y_clf[idx], proba_a[idx])
            auc_b = roc_auc_score(y_clf[idx], proba_b[idx])
            diffs[b] = auc_a - auc_b
        except ValueError:
            diffs[b] = np.nan
    diffs = diffs[~np.isnan(diffs)]
    mean = float(diffs.mean())
    ci_lo = float(np.percentile(diffs, 2.5))
    ci_hi = float(np.percentile(diffs, 97.5))
    # Two-sided p-value via fraction crossing zero
    p = float(2 * min((diffs <= 0).mean(), (diffs >= 0).mean()))
    return mean, ci_lo, ci_hi, p


# ============================================================================
# MAIN
# ============================================================================

@dataclass
class CachedRun:
    config_label: str
    seed: int
    model_type: str
    clf_proba: np.ndarray
    reg_pred: np.ndarray
    n_features: int
    train_time_sec: float


def run_ablation(csv_path: str, configs: list, seeds: list, models: list,
                 baseline_label: str = 'baseline') -> dict:
    print(f'\n=== Ablation on {csv_path} ===')
    print(f'Configs: {[c[0] for c in configs]}')
    print(f'Seeds: {seeds}')
    print(f'Models: {models}\n')

    df = pd.read_csv(csv_path)
    df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])
    train_df = df[df['GAME_DATE'] < TEST_START].copy()
    test_df = df[(df['GAME_DATE'] >= TEST_START) & (df['GAME_DATE'] <= TEST_END)].copy()
    print(f'Train: {len(train_df)} games; Test (W5): {len(test_df)} games')

    y_clf_train = train_df['TARGET_WIN'].values.astype(int)
    y_reg_train = train_df['TARGET_MARGIN'].values.astype(float)
    y_clf_test = test_df['TARGET_WIN'].values.astype(int)
    y_reg_test = test_df['TARGET_MARGIN'].values.astype(float)

    # Cache: predictions per (config, seed, model)
    cache: list = []

    for cfg in configs:
        cfg_label, e9, e10, e11 = cfg
        feature_cols = select_features(df.columns, enable_e9=e9, enable_e10=e10, enable_e11=e11)

        X_train_raw = train_df[feature_cols].copy()
        X_test_raw = test_df[feature_cols].copy()

        # Drop columns that are all-NaN in train (matches existing training pipeline)
        valid_cols = X_train_raw.columns[X_train_raw.notna().any()].tolist()
        X_train_raw = X_train_raw[valid_cols]
        X_test_raw = X_test_raw[valid_cols]

        imp = SimpleImputer(strategy='median')
        scl = StandardScaler()
        X_train_imp = imp.fit_transform(X_train_raw)
        X_train = scl.fit_transform(X_train_imp)
        X_test = scl.transform(imp.transform(X_test_raw))

        print(f'[{cfg_label}] {len(valid_cols)} active features')

        for seed in seeds:
            for model_type in models:
                t0 = time.time()
                clf_proba, reg_pred = train_and_predict(
                    X_train, y_clf_train, y_reg_train, X_test, model_type, seed,
                )
                dt = time.time() - t0
                cache.append(CachedRun(
                    config_label=cfg_label, seed=seed, model_type=model_type,
                    clf_proba=clf_proba, reg_pred=reg_pred,
                    n_features=len(valid_cols), train_time_sec=dt,
                ))
            print(f'  seed={seed}: {len(models)} models trained in {sum(c.train_time_sec for c in cache[-len(models):]):.1f}s')

    # ---- Compute bootstrap CIs per (config, model) ----
    summary = {}
    for cfg in configs:
        cfg_label = cfg[0]
        for model_type in models:
            runs = [c for c in cache if c.config_label == cfg_label and c.model_type == model_type]
            # Pool all bootstrap metrics across all seeds
            pooled = {'acc': [], 'auc': [], 'mae': []}
            for r in runs:
                m = bootstrap_metrics(r.clf_proba, r.reg_pred, y_clf_test, y_reg_test,
                                      n_bootstrap=N_BOOTSTRAP, seed_offset=r.seed)
                for k in pooled:
                    pooled[k].append(m[k])
            for k in pooled:
                arr = np.concatenate(pooled[k])
                arr = arr[~np.isnan(arr)]
                summary[(cfg_label, model_type, k)] = {
                    'mean': float(arr.mean()),
                    'ci_lo': float(np.percentile(arr, 2.5)),
                    'ci_hi': float(np.percentile(arr, 97.5)),
                    'std': float(arr.std(ddof=1)),
                    'n_samples': int(len(arr)),
                }

    # ---- Paired tests: each non-baseline config vs baseline ----
    paired = {}
    for cfg in configs:
        cfg_label = cfg[0]
        if cfg_label == baseline_label:
            continue
        for model_type in models:
            # Average predictions across seeds for each config
            base_runs = [c for c in cache if c.config_label == baseline_label and c.model_type == model_type]
            cfg_runs = [c for c in cache if c.config_label == cfg_label and c.model_type == model_type]
            if not base_runs or not cfg_runs:
                continue

            base_proba = np.mean([r.clf_proba for r in base_runs], axis=0)
            cfg_proba = np.mean([r.clf_proba for r in cfg_runs], axis=0)
            base_reg = np.mean([r.reg_pred for r in base_runs], axis=0)
            cfg_reg = np.mean([r.reg_pred for r in cfg_runs], axis=0)

            base_label_pred = (base_proba >= 0.5).astype(int)
            cfg_label_pred = (cfg_proba >= 0.5).astype(int)

            mc_stat, mc_p, mc_b, mc_c = mcnemar_test(cfg_label_pred, base_label_pred, y_clf_test)
            t_stat, t_p, mae_diff, mae_diff_sd = paired_t_on_abs_err(cfg_reg, base_reg, y_reg_test)
            auc_diff, auc_ci_lo, auc_ci_hi, auc_p = bootstrap_auc_diff(
                cfg_proba, base_proba, y_clf_test, n_bootstrap=N_BOOTSTRAP, seed=0,
            )

            paired[(cfg_label, model_type)] = {
                'mcnemar_stat': mc_stat, 'mcnemar_p': mc_p,
                'cfg_wins': mc_b, 'base_wins': mc_c,
                'paired_t_stat': t_stat, 'paired_t_p': t_p,
                'mae_diff_mean': mae_diff, 'mae_diff_sd': mae_diff_sd,
                'auc_diff_mean': auc_diff, 'auc_diff_ci_lo': auc_ci_lo,
                'auc_diff_ci_hi': auc_ci_hi, 'auc_diff_p': auc_p,
            }

    return {
        'csv_path': csv_path, 'configs': [c[0] for c in configs],
        'seeds': seeds, 'models': models, 'n_test': len(test_df),
        'n_train': len(train_df), 'n_bootstrap': N_BOOTSTRAP,
        'summary': {f'{k[0]}|{k[1]}|{k[2]}': v for k, v in summary.items()},
        'paired': {f'{k[0]}|{k[1]}': v for k, v in paired.items()},
        'baseline_label': baseline_label,
        'run_at': datetime.now().isoformat(timespec='seconds'),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--csv', default='nba_ml_features.csv')
    p.add_argument('--out', default=None,
                   help='Output JSON path. Defaults to outputs/e3_ablation_<csv_stem>.json')
    p.add_argument('--seeds', type=int, default=10,
                   help='How many seeds (uses first N from the SEEDS list)')
    p.add_argument('--models', nargs='+', default=['RF', 'XGB', 'NN'],
                   choices=['RF', 'XGB', 'NN'])
    p.add_argument('--configs', nargs='*', default=None,
                   help='Subset of config labels to run; default = all 8')
    args = p.parse_args()

    seeds = SEEDS[:args.seeds]

    if args.configs:
        configs = [c for c in ABLATION_CONFIGS if c[0] in args.configs]
    else:
        configs = ABLATION_CONFIGS

    out_path = args.out or _os.path.join(
        'outputs', f'e3_ablation_{_os.path.splitext(_os.path.basename(args.csv))[0]}.json'
    )
    _os.makedirs('outputs', exist_ok=True)

    t0 = time.time()
    results = run_ablation(args.csv, configs, seeds, args.models)
    print(f'\nTotal runtime: {(time.time()-t0)/60:.1f} min')

    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f'Results saved -> {out_path}')


if __name__ == '__main__':
    main()
