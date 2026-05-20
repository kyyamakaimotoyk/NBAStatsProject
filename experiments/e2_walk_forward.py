"""
Experiment 2: Walk-forward validation across 5 time windows.

Question being answered: does the 74.89% test accuracy from E1 generalize, or was that
Mar-Apr 2026 window just easy?

Why this can't be done with validate_models.py: validate_models.py loads the production
model on disk, which was retrained on the FULL dataset (every game through 2026-04-15).
So any window picked from that dataset is in-fold — the model has memorized portions of
the test set during its production retrain. The result would be misleadingly high.

What this script does instead:
  for each window W:
      train_slice = rows where GAME_DATE < W.start    (strict temporal causality)
      test_slice  = rows where W.start <= GAME_DATE <= W.end
      fit a fresh imputer + scaler on train_slice
      train fresh RF + NN models on train_slice
      predict on test_slice
      record metrics

Models are trained IN-MEMORY ONLY. No bundles written, no DB rows written, no production
model touched. This is a pure measurement experiment — re-runnable, side-effect-free.

Hyperparameters mirror the current E1 defaults exactly (max_depth=5, min_samples_leaf=20
for RF; dropout=0.5, weight_decay=1e-4, seed=42 for NN). If a hyperparam changes in
predict_games.py, update the dicts below to match.

Usage:
    python experiments/e2_walk_forward.py
"""
from __future__ import annotations

# Project-root bootstrap (this script lives in experiments/, one level deep)
import sys as _sys
import os as _os
_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _PROJECT_ROOT)
if _os.getcwd() != _PROJECT_ROOT:
    _os.chdir(_PROJECT_ROOT)

# PyTorch must be imported before numpy/pandas on Windows
try:
    import torch
    PYTORCH_AVAILABLE = True
except (ImportError, OSError):
    PYTORCH_AVAILABLE = False
    print("[E2] PyTorch unavailable — NN windows will be skipped.")

import json
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.metrics import (accuracy_score, roc_auc_score, precision_score, recall_score,
                             f1_score, mean_absolute_error, r2_score)

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False
    print("[E2] xgboost unavailable - XGB columns will be skipped.")


# ============================================================================
# WINDOW DEFINITIONS
# ============================================================================
# 5 non-overlapping windows spanning the available 2025-26 season data
# (CSV is 2025-10-30 -> 2026-04-15, 1134 games). Each test window is preceded by enough
# training data for a meaningful model — the first window has the smallest train set and
# is expected to be the noisiest.

WINDOWS = [
    {'name': 'W1 (Dec 2025)',   'start': '2025-12-01', 'end': '2025-12-31'},
    {'name': 'W2 (Jan 2026)',   'start': '2026-01-01', 'end': '2026-01-31'},
    {'name': 'W3 (Feb 2026)',   'start': '2026-02-01', 'end': '2026-02-28'},
    {'name': 'W4 (Mar 1-15)',   'start': '2026-03-01', 'end': '2026-03-15'},
    {'name': 'W5 (Mar 15-Apr 15)', 'start': '2026-03-15', 'end': '2026-04-15'},
]

# Mirror the current production hyperparameters (set in predict_games.py E1/E3 defaults).
RF_CLF_HP = {'n_estimators': 100, 'max_depth': 5, 'min_samples_leaf': 20, 'random_state': 42}
RF_REG_HP = {'n_estimators': 100, 'max_depth': 5, 'min_samples_leaf': 20, 'random_state': 42}
NN_HP = {'hidden_dims': [128, 64, 32], 'dropout': 0.5, 'lr': 0.001,
         'weight_decay': 1e-4, 'epochs': 100, 'patience': 15, 'seed': 42}
XGB_HP = {'n_estimators': 200, 'max_depth': 4, 'learning_rate': 0.1,
          'min_child_weight': 10, 'subsample': 0.8, 'colsample_bytree': 0.8,
          'reg_lambda': 1.0, 'random_state': 42}


# ============================================================================
# FEATURE SELECTION (must match predict_games._prepare_training_data)
# ============================================================================

def select_feature_columns(df: pd.DataFrame) -> list:
    """Select model feature columns from the raw feature CSV.
    Uses the centralized allow-list in core.features (single source of truth)."""
    from core.features import select_features
    return select_features(df.columns)


# ============================================================================
# PYTORCH MODELS (mirror NBAClassifier/NBARegressor from predict_games)
# ============================================================================

if PYTORCH_AVAILABLE:
    import torch.nn as nn

    class _NBAClf(nn.Module):
        def __init__(self, input_dim, dropout=0.5):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(input_dim, 128), nn.BatchNorm1d(128), nn.ReLU(), nn.Dropout(dropout),
                nn.Linear(128, 64),        nn.BatchNorm1d(64),  nn.ReLU(), nn.Dropout(dropout),
                nn.Linear(64, 32),         nn.BatchNorm1d(32),  nn.ReLU(), nn.Dropout(dropout),
                nn.Linear(32, 1),
            )

        def forward(self, x):
            return self.net(x)

    class _NBAReg(nn.Module):
        def __init__(self, input_dim, dropout=0.5):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(input_dim, 128), nn.BatchNorm1d(128), nn.ReLU(), nn.Dropout(dropout),
                nn.Linear(128, 64),        nn.BatchNorm1d(64),  nn.ReLU(), nn.Dropout(dropout),
                nn.Linear(64, 32),         nn.BatchNorm1d(32),  nn.ReLU(), nn.Dropout(dropout),
                nn.Linear(32, 1),
            )

        def forward(self, x):
            return self.net(x)


def _train_nn(model, X, y, is_classifier, hp, target_scaler=None):
    """Minimal PyTorch trainer matching predict_games._train_pytorch_model. Returns
    target_scaler (fitted) for regression, None for classification."""
    torch.manual_seed(hp['seed'])
    np.random.seed(hp['seed'])

    X_tensor = torch.FloatTensor(X)
    if not is_classifier and target_scaler is not None:
        y_scaled = target_scaler.fit_transform(y.reshape(-1, 1)).flatten()
        y_tensor = torch.FloatTensor(y_scaled).unsqueeze(1)
    else:
        y_tensor = torch.FloatTensor(y).unsqueeze(1)

    # Temporal 80/20 split for early stopping
    split = int(0.8 * len(X))
    X_tr, X_val = X_tensor[:split], X_tensor[split:]
    y_tr, y_val = y_tensor[:split], y_tensor[split:]

    criterion = nn.BCEWithLogitsLoss() if is_classifier else nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=hp['lr'], weight_decay=hp['weight_decay'])

    best_val_loss = float('inf')
    best_state = None
    patience_counter = 0
    model.train()
    for epoch in range(hp['epochs']):
        optimizer.zero_grad()
        out = model(X_tr)
        loss = criterion(out, y_tr)
        loss.backward()
        optimizer.step()

        model.eval()
        with torch.no_grad():
            val_loss = criterion(model(X_val), y_val).item()
        model.train()

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
            patience_counter = 0
        else:
            patience_counter += 1
            if patience_counter >= hp['patience']:
                break

    if best_state is not None:
        model.load_state_dict(best_state)
    model.eval()
    return target_scaler


# ============================================================================
# PER-WINDOW EVAL
# ============================================================================

def evaluate_window(df: pd.DataFrame, window: dict, feature_cols: list) -> dict:
    """Train on rows strictly before window.start, evaluate on window."""
    start = pd.Timestamp(window['start'])
    end = pd.Timestamp(window['end'])
    train_mask = df['GAME_DATE'] < start
    test_mask = (df['GAME_DATE'] >= start) & (df['GAME_DATE'] <= end)

    n_train = train_mask.sum()
    n_test = test_mask.sum()
    print(f"\n=== {window['name']} ===")
    print(f"  Train: {n_train} games (before {window['start']})")
    print(f"  Test:  {n_test} games ({window['start']} .. {window['end']})")

    if n_train < 200 or n_test < 20:
        print(f"  SKIP: insufficient data")
        return {'window': window['name'], 'n_train': int(n_train), 'n_test': int(n_test),
                'skipped': True}

    X_train_raw = df.loc[train_mask, feature_cols].values
    X_test_raw = df.loc[test_mask, feature_cols].values
    y_clf_train = df.loc[train_mask, 'TARGET_WIN'].astype(int).values
    y_clf_test = df.loc[test_mask, 'TARGET_WIN'].astype(int).values
    y_reg_train = df.loc[train_mask, 'TARGET_MARGIN'].astype(float).values
    y_reg_test = df.loc[test_mask, 'TARGET_MARGIN'].astype(float).values

    # Fit preprocessing on train only — critical for honest validation
    imputer = SimpleImputer(strategy='median')
    scaler = StandardScaler()
    X_train_imputed = imputer.fit_transform(X_train_raw)
    X_train_scaled = scaler.fit_transform(X_train_imputed)
    X_test_imputed = imputer.transform(X_test_raw)
    X_test_scaled = scaler.transform(X_test_imputed)

    results = {'window': window['name'], 'n_train': int(n_train), 'n_test': int(n_test),
               'train_start': df.loc[train_mask, 'GAME_DATE'].min().date().isoformat(),
               'train_end':   df.loc[train_mask, 'GAME_DATE'].max().date().isoformat(),
               'test_start':  window['start'],
               'test_end':    window['end'],
               'skipped': False}

    # ----- Random Forest -----
    print("  Training RF...")
    rf_clf = RandomForestClassifier(**RF_CLF_HP, n_jobs=-1)
    rf_clf.fit(X_train_scaled, y_clf_train)
    rf_pred = rf_clf.predict(X_test_scaled)
    rf_prob = rf_clf.predict_proba(X_test_scaled)[:, 1]

    rf_reg = RandomForestRegressor(**RF_REG_HP, n_jobs=-1)
    rf_reg.fit(X_train_scaled, y_reg_train)
    rf_reg_pred = rf_reg.predict(X_test_scaled)

    results['rf_test_accuracy'] = float(accuracy_score(y_clf_test, rf_pred))
    results['rf_test_auc'] = float(roc_auc_score(y_clf_test, rf_prob)) if len(set(y_clf_test)) > 1 else None
    results['rf_test_precision'] = float(precision_score(y_clf_test, rf_pred, zero_division=0))
    results['rf_test_recall'] = float(recall_score(y_clf_test, rf_pred, zero_division=0))
    results['rf_test_f1'] = float(f1_score(y_clf_test, rf_pred, zero_division=0))
    results['rf_test_mae'] = float(mean_absolute_error(y_reg_test, rf_reg_pred))
    results['rf_test_r2'] = float(r2_score(y_reg_test, rf_reg_pred))

    # ----- XGBoost -----
    if XGBOOST_AVAILABLE:
        print("  Training XGB...")
        xgb_clf = xgb.XGBClassifier(**XGB_HP, n_jobs=-1, verbosity=0, eval_metric='logloss')
        xgb_clf.fit(X_train_scaled, y_clf_train)
        xgb_pred = xgb_clf.predict(X_test_scaled)
        xgb_prob = xgb_clf.predict_proba(X_test_scaled)[:, 1]

        xgb_reg = xgb.XGBRegressor(**XGB_HP, n_jobs=-1, verbosity=0)
        xgb_reg.fit(X_train_scaled, y_reg_train)
        xgb_reg_pred = xgb_reg.predict(X_test_scaled)

        results['xgb_test_accuracy'] = float(accuracy_score(y_clf_test, xgb_pred))
        results['xgb_test_auc'] = float(roc_auc_score(y_clf_test, xgb_prob)) if len(set(y_clf_test)) > 1 else None
        results['xgb_test_precision'] = float(precision_score(y_clf_test, xgb_pred, zero_division=0))
        results['xgb_test_recall'] = float(recall_score(y_clf_test, xgb_pred, zero_division=0))
        results['xgb_test_f1'] = float(f1_score(y_clf_test, xgb_pred, zero_division=0))
        results['xgb_test_mae'] = float(mean_absolute_error(y_reg_test, xgb_reg_pred))
        results['xgb_test_r2'] = float(r2_score(y_reg_test, xgb_reg_pred))

    # ----- Neural Network -----
    if PYTORCH_AVAILABLE:
        print("  Training NN...")
        nn_clf = _NBAClf(X_train_scaled.shape[1], dropout=NN_HP['dropout'])
        _train_nn(nn_clf, X_train_scaled, y_clf_train, is_classifier=True, hp=NN_HP)
        nn_reg = _NBAReg(X_train_scaled.shape[1], dropout=NN_HP['dropout'])
        target_scaler = StandardScaler()
        _train_nn(nn_reg, X_train_scaled, y_reg_train, is_classifier=False, hp=NN_HP,
                  target_scaler=target_scaler)

        with torch.no_grad():
            X_test_tensor = torch.FloatTensor(X_test_scaled)
            nn_logits = nn_clf(X_test_tensor).numpy().flatten()
            nn_prob = 1.0 / (1.0 + np.exp(-nn_logits))
            nn_pred = (nn_prob > 0.5).astype(int)
            nn_reg_pred_scaled = nn_reg(X_test_tensor).numpy().flatten()
            nn_reg_pred = target_scaler.inverse_transform(nn_reg_pred_scaled.reshape(-1, 1)).flatten()

        results['nn_test_accuracy'] = float(accuracy_score(y_clf_test, nn_pred))
        results['nn_test_auc'] = float(roc_auc_score(y_clf_test, nn_prob)) if len(set(y_clf_test)) > 1 else None
        results['nn_test_precision'] = float(precision_score(y_clf_test, nn_pred, zero_division=0))
        results['nn_test_recall'] = float(recall_score(y_clf_test, nn_pred, zero_division=0))
        results['nn_test_f1'] = float(f1_score(y_clf_test, nn_pred, zero_division=0))
        results['nn_test_mae'] = float(mean_absolute_error(y_reg_test, nn_reg_pred))
        results['nn_test_r2'] = float(r2_score(y_reg_test, nn_reg_pred))

    return results


# ============================================================================
# MAIN
# ============================================================================

def main():
    print(f"Loading features from {_os.path.join(_PROJECT_ROOT, 'nba_ml_features.csv')}")
    df = pd.read_csv('nba_ml_features.csv')
    df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])
    feature_cols = select_feature_columns(df)
    print(f"Loaded {len(df)} games, {len(feature_cols)} features")
    print(f"Date range: {df.GAME_DATE.min().date()} -> {df.GAME_DATE.max().date()}")

    all_results = []
    for window in WINDOWS:
        results = evaluate_window(df, window, feature_cols)
        all_results.append(results)

    # ---- Summary table ----
    print("\n\n" + "=" * 100)
    print("WALK-FORWARD RESULTS SUMMARY")
    print("=" * 100)
    print(f"{'Window':<25} {'n_tr':>5} {'n_te':>5}   "
          f"{'RF acc':>7} {'RF AUC':>7} {'RF MAE':>7}   "
          f"{'XGB acc':>7} {'XGB AUC':>7} {'XGB MAE':>7}   "
          f"{'NN acc':>7} {'NN AUC':>7} {'NN MAE':>7}")
    print("-" * 130)
    for r in all_results:
        if r.get('skipped'):
            print(f"{r['window']:<25} {r['n_train']:>5} {r['n_test']:>5}   SKIPPED")
            continue
        def _fmt(prefix, fmt='6.3f', width=7):
            v = r.get(f'{prefix}', None)
            if v is None: return ' ' * width
            return f'{v:{fmt}}'.rjust(width)
        print(f"{r['window']:<25} {r['n_train']:>5} {r['n_test']:>5}   "
              f"{_fmt('rf_test_accuracy')} {_fmt('rf_test_auc')} {_fmt('rf_test_mae', '7.2f')}   "
              f"{_fmt('xgb_test_accuracy')} {_fmt('xgb_test_auc')} {_fmt('xgb_test_mae', '7.2f')}   "
              f"{_fmt('nn_test_accuracy')} {_fmt('nn_test_auc')} {_fmt('nn_test_mae', '7.2f')}")
    print()
    print("Note: each window's model was trained on data STRICTLY BEFORE its start date,")
    print("so these metrics are honest walk-forward out-of-sample numbers (not in-fold).")

    # Persist for the experiment log
    out_path = _os.path.join(_PROJECT_ROOT, 'outputs', 'e2_walk_forward_results.json')
    _os.makedirs(_os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as fp:
        json.dump(all_results, fp, indent=2, default=str)
    print(f"\nFull results JSON: {out_path}")


if __name__ == '__main__':
    main()
