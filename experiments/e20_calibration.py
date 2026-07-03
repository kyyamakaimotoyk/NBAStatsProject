"""
E20 — Calibration protocol A/B: raw vs eval-slice isotonic (production's current
protocol) vs K-fold out-of-fold isotonic. Decides both the PROTOCOL and the
PICK POLICY (should the pick come from raw or calibrated probability?).

Why this experiment exists (E19 audit): the E13 calibrator — isotonic fit on a
~200-game eval slice, applied to the full-data production model — collapsed RF
into picking home 97% of the time and actively flipped correct raw picks
(2026-06-13: raw 0.449 -> cal 0.604). Live reliability: calibrated "70%" games
won only 40%. The suspected causes are (a) the tiny, temporally-narrow fit set
and (b) the eval-model-fit / production-model-apply mismatch. OOF calibration
attacks both: every training game gets a probability from a fold-model that
never saw it, giving ~5x the calibration data spanning the whole training era.

Protocols compared per (model, seed), all trained strictly before the test window:
  raw        - production model on 100% of train, no calibration.
  eval_slice - MIRRORS PRODUCTION EXACTLY, including its subtlety: eval model on
               first 80% of train -> isotonic fit on its probs over the last 20%
               -> applied to the FULL-data model's test probs.
  oof        - 5-fold stratified OOF probabilities over the full train set ->
               isotonic fit on pooled OOF -> applied to the full-data model's
               test probs.

Metrics on the held-out test window: ECE, Brier, AUC, accuracy@0.5, home-pick
share, and for each calibrated protocol vs raw: pick-flip count + who wins the
disagreement games (the McNemar question). Per-seed values, aggregated as
mean +/- std with seed-consistency counts (E12 discipline: consistency across
seeds beats one-run deltas).

Usage:
    python experiments/e20_calibration.py --seeds 10 --nn-seeds 5
    python experiments/e20_calibration.py --test-start 2026-04-15 --test-end 2026-06-13   # playoff window
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
import json
from datetime import datetime

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import brier_score_loss, roc_auc_score

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False

from core.features import select_features
from experiments.e13_calibration import (  # reuse, don't re-implement
    reliability_bins, expected_calibration_error,
)

if TORCH_AVAILABLE:
    from modeling.predict_games import NBAClassifier, _train_pytorch_model

TEST_START = '2026-03-15'   # frozen W5, comparable with E12/E13
TEST_END = '2026-04-15'
SEEDS = [42, 123, 456, 789, 1000, 2024, 31337, 65535, 8675309, 99999]

RF_CLF_HP = {'n_estimators': 100, 'max_depth': 5, 'min_samples_leaf': 20}
XGB_CLF_HP = {'n_estimators': 200, 'max_depth': 4, 'learning_rate': 0.1,
              'min_child_weight': 10, 'subsample': 0.8, 'colsample_bytree': 0.8,
              'reg_lambda': 1.0, 'eval_metric': 'logloss'}
NN_HP = {'dropout': 0.5, 'epochs': 100, 'lr': 0.001, 'weight_decay': 1e-4}
N_FOLDS = 5


def fit_predict(model_type: str, seed: int, X_tr, y_tr, X_te) -> np.ndarray:
    """Train one classifier, return P(home win) on X_te."""
    if model_type == 'RF':
        m = RandomForestClassifier(**RF_CLF_HP, random_state=seed, n_jobs=-1)
        m.fit(X_tr, y_tr)
        return m.predict_proba(X_te)[:, 1]
    if model_type == 'XGB':
        m = xgb.XGBClassifier(**XGB_CLF_HP, random_state=seed, n_jobs=-1)
        m.fit(X_tr, y_tr)
        return m.predict_proba(X_te)[:, 1]
    if model_type == 'NN':
        model = NBAClassifier(input_dim=X_tr.shape[1], dropout_rate=NN_HP['dropout'])
        _train_pytorch_model(model, X_tr, np.asarray(y_tr, dtype=np.float32),
                             is_classifier=True, epochs=NN_HP['epochs'],
                             lr=NN_HP['lr'], weight_decay=NN_HP['weight_decay'],
                             seed=seed)
        model.eval()
        with torch.no_grad():
            logits = model(torch.FloatTensor(X_te))
        return torch.sigmoid(logits).numpy().flatten()
    raise ValueError(model_type)


def pick_metrics(y: np.ndarray, p: np.ndarray) -> dict:
    picks = (p > 0.5).astype(int)
    return {
        'ece': expected_calibration_error(y, p),
        'brier': float(brier_score_loss(y, p)),
        'auc': float(roc_auc_score(y, p)),
        'acc': float((picks == y).mean()),
        'home_pick_share': float(picks.mean()),
    }


def flip_stats(y: np.ndarray, p_raw: np.ndarray, p_cal: np.ndarray) -> dict:
    """On games where raw and calibrated disagree about the pick, who is right?"""
    raw_pick = (p_raw > 0.5).astype(int)
    cal_pick = (p_cal > 0.5).astype(int)
    mask = raw_pick != cal_pick
    n = int(mask.sum())
    if n == 0:
        return {'n_flips': 0, 'raw_wins': 0, 'cal_wins': 0}
    raw_right = (raw_pick[mask] == y[mask])
    # binary disagreement: exactly one of the two picks is correct per game
    return {'n_flips': n,
            'raw_wins': int(raw_right.sum()),
            'cal_wins': int((~raw_right).sum())}


def run(csv_path, seeds_by_model, test_start, test_end, out_path):
    df = pd.read_csv(csv_path)
    df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])
    feature_cols = select_features(df.columns)  # production config

    train_df = df[df['GAME_DATE'] < test_start].copy()
    test_df = df[(df['GAME_DATE'] >= test_start) & (df['GAME_DATE'] <= test_end)].copy()
    valid_cols = train_df[feature_cols].columns[train_df[feature_cols].notna().any()].tolist()

    imp = SimpleImputer(strategy='median')
    scl = StandardScaler()
    X_train = scl.fit_transform(imp.fit_transform(train_df[valid_cols]))
    X_test = scl.transform(imp.transform(test_df[valid_cols]))
    y_train = train_df['TARGET_WIN'].values.astype(int)
    y_test = test_df['TARGET_WIN'].values.astype(int)

    print(f'Train(<{test_start}): {len(train_df)} | Test({test_start}..{test_end}): '
          f'{len(test_df)} | features: {len(valid_cols)}')
    print(f'Test-window actual home-win rate: {y_test.mean():.3f}\n')

    results = {'csv': csv_path, 'test_start': str(test_start), 'test_end': str(test_end),
               'n_train': len(train_df), 'n_test': len(test_df),
               'home_rate_test': float(y_test.mean()),
               'run_at': datetime.now().isoformat(timespec='seconds'), 'models': {}}

    for mt, seeds in seeds_by_model.items():
        print(f'=== {mt} ({len(seeds)} seeds) ===')
        per_seed = []
        for seed in seeds:
            # raw: full-train production model
            p_raw = fit_predict(mt, seed, X_train, y_train, X_test)

            # eval_slice: mirror production (80/20 temporal, iso on eval-model
            # probs, applied to full-model probs)
            split = int(0.8 * len(X_train))
            p_eval = fit_predict(mt, seed, X_train[:split], y_train[:split], X_train[split:])
            iso_eval = IsotonicRegression(out_of_bounds='clip').fit(p_eval, y_train[split:])
            p_evalcal = iso_eval.predict(p_raw)

            # oof: pooled out-of-fold probs over the full train set
            oof = np.zeros(len(X_train))
            skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed)
            for tr_idx, te_idx in skf.split(X_train, y_train):
                oof[te_idx] = fit_predict(mt, seed, X_train[tr_idx], y_train[tr_idx],
                                          X_train[te_idx])
            iso_oof = IsotonicRegression(out_of_bounds='clip').fit(oof, y_train)
            p_oofcal = iso_oof.predict(p_raw)

            row = {'seed': seed,
                   'raw': pick_metrics(y_test, p_raw),
                   'eval_slice': pick_metrics(y_test, p_evalcal),
                   'oof': pick_metrics(y_test, p_oofcal),
                   'flips_eval': flip_stats(y_test, p_raw, p_evalcal),
                   'flips_oof': flip_stats(y_test, p_raw, p_oofcal)}
            per_seed.append(row)
            print(f"  seed {seed}: raw acc={row['raw']['acc']:.3f} ece={row['raw']['ece']:.3f} | "
                  f"eval acc={row['eval_slice']['acc']:.3f} ece={row['eval_slice']['ece']:.3f} "
                  f"home%={row['eval_slice']['home_pick_share']:.2f} | "
                  f"oof acc={row['oof']['acc']:.3f} ece={row['oof']['ece']:.3f} "
                  f"home%={row['oof']['home_pick_share']:.2f}")

        # Aggregate: mean +/- std + seed-consistency counts
        agg = {}
        for proto in ('raw', 'eval_slice', 'oof'):
            agg[proto] = {k: {'mean': float(np.mean([r[proto][k] for r in per_seed])),
                              'std': float(np.std([r[proto][k] for r in per_seed]))}
                          for k in per_seed[0][proto]}
        consistency = {
            'oof_beats_raw_ece': sum(r['oof']['ece'] < r['raw']['ece'] for r in per_seed),
            'oof_beats_eval_ece': sum(r['oof']['ece'] < r['eval_slice']['ece'] for r in per_seed),
            'oof_acc_ge_raw': sum(r['oof']['acc'] >= r['raw']['acc'] for r in per_seed),
            'eval_acc_ge_raw': sum(r['eval_slice']['acc'] >= r['raw']['acc'] for r in per_seed),
        }
        flips = {k: {'n': sum(r[k]['n_flips'] for r in per_seed),
                     'raw_wins': sum(r[k]['raw_wins'] for r in per_seed),
                     'cal_wins': sum(r[k]['cal_wins'] for r in per_seed)}
                 for k in ('flips_eval', 'flips_oof')}

        results['models'][mt] = {'per_seed': per_seed, 'aggregate': agg,
                                 'consistency': consistency, 'flips': flips,
                                 'n_seeds': len(seeds)}

        print(f"\n  {'':12s}{'acc':>8s}{'ece':>8s}{'brier':>8s}{'auc':>8s}{'home%':>8s}")
        for proto in ('raw', 'eval_slice', 'oof'):
            a = agg[proto]
            print(f"  {proto:12s}{a['acc']['mean']:8.3f}{a['ece']['mean']:8.3f}"
                  f"{a['brier']['mean']:8.3f}{a['auc']['mean']:8.3f}"
                  f"{a['home_pick_share']['mean']:8.2f}")
        print(f"  consistency (of {len(seeds)} seeds): {consistency}")
        print(f"  disagreement games: eval_slice {flips['flips_eval']} | "
              f"oof {flips['flips_oof']}\n")

    _os.makedirs('outputs', exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f'Saved -> {out_path}')
    return results


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--csv', default='nba_ml_features.csv')
    p.add_argument('--seeds', type=int, default=10)
    p.add_argument('--nn-seeds', type=int, default=5,
                   help='NN trains 7x per seed (full + eval + 5 folds); cap it lower')
    p.add_argument('--models', nargs='+', default=None)
    p.add_argument('--test-start', default=TEST_START)
    p.add_argument('--test-end', default=TEST_END)
    p.add_argument('--out', default='outputs/e20_calibration.json')
    args = p.parse_args()

    models = args.models or (['RF'] + (['XGB'] if XGBOOST_AVAILABLE else [])
                             + (['NN'] if TORCH_AVAILABLE else []))
    seeds_by_model = {m: SEEDS[:(args.nn_seeds if m == 'NN' else args.seeds)]
                      for m in models}
    run(args.csv, seeds_by_model, args.test_start, args.test_end, args.out)


if __name__ == '__main__':
    main()
