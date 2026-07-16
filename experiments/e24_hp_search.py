"""E24: first-ever hyperparameter search (Optuna), walk-forward objective.

The July 2026 assessment (section 2.4 gap #1): hyperparameters were hand-set
once in E1 (2026-05-18) and never searched. This script runs an Optuna TPE
study per (family, task) with:

  objective = mean out-of-sample loss across the W1..W4 walk-forward windows
              (x N seeds); logloss for the classifier, MAE for the regressor.

W5 is deliberately EXCLUDED from the objective — it stays reserved for the
E12-protocol A/B gate (experiments/loop_ab.py with an ``hp`` arm), so the
selection window and the confirmation window never overlap.

Studies persist to SQLite (``outputs/e24_optuna.db``) so an interrupted or
budget-trimmed search resumes with no lost trials. The incumbent (E1) HPs are
enqueued as trial 0 so the sampler always knows the current config's
neighborhood, and the incumbent objective is reported alongside the best.

Usage:
  python experiments/e24_hp_search.py --family XGB --trials 60 --seeds 2
  --quick: 4 trials, 1 seed, W3-W4 only (smoke).
"""
from __future__ import annotations

import sys as _sys
import os as _os
_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)

from experiments.harness import (
    XGBOOST_AVAILABLE, SEEDS, FIXED_WINDOWS, load_frozen_csv, prepare_xy,
    RF_CLF_HP, RF_REG_HP, XGB_CLF_HP, XGB_REG_HP,
)

import argparse
import json
import time
from datetime import datetime

import numpy as np
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import mean_absolute_error

if XGBOOST_AVAILABLE:
    import xgboost as xgb

import optuna

SEARCH_WINDOWS = ('W1', 'W2', 'W3', 'W4')   # W5 reserved for the gate


def _logloss(y, proba):
    p = np.clip(proba, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


# ----------------------------------------------------------------------------
# Search spaces
# ----------------------------------------------------------------------------

def suggest_xgb(trial: optuna.Trial) -> dict:
    return {
        'n_estimators': trial.suggest_int('n_estimators', 100, 600, step=50),
        'max_depth': trial.suggest_int('max_depth', 2, 8),
        'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.3, log=True),
        'min_child_weight': trial.suggest_int('min_child_weight', 1, 40, log=True),
        'subsample': trial.suggest_float('subsample', 0.5, 1.0),
        'colsample_bytree': trial.suggest_float('colsample_bytree', 0.3, 1.0),
        'reg_lambda': trial.suggest_float('reg_lambda', 0.1, 30.0, log=True),
        'reg_alpha': trial.suggest_float('reg_alpha', 1e-3, 10.0, log=True),
    }


def suggest_rf(trial: optuna.Trial) -> dict:
    return {
        'n_estimators': trial.suggest_int('n_estimators', 100, 500, step=50),
        'max_depth': trial.suggest_int('max_depth', 3, 12),
        'min_samples_leaf': trial.suggest_int('min_samples_leaf', 2, 50, log=True),
        'max_features': trial.suggest_float('max_features', 0.1, 1.0),
    }


INCUMBENTS = {
    ('XGB', 'clf'): {k: v for k, v in XGB_CLF_HP.items() if k != 'eval_metric'},
    ('XGB', 'reg'): dict(XGB_REG_HP),
    ('RF', 'clf'): dict(RF_CLF_HP),
    ('RF', 'reg'): dict(RF_REG_HP),
}


def _make_estimator(family: str, task: str, params: dict, seed: int):
    if family == 'XGB':
        extra = {'eval_metric': 'logloss'} if task == 'clf' else {}
        cls = xgb.XGBClassifier if task == 'clf' else xgb.XGBRegressor
        return cls(**params, **extra, random_state=seed, n_jobs=-1, verbosity=0)
    cls = RandomForestClassifier if task == 'clf' else RandomForestRegressor
    return cls(**params, random_state=seed, n_jobs=-1)


# ----------------------------------------------------------------------------
# Objective
# ----------------------------------------------------------------------------

def make_objective(family: str, task: str, data: list, seeds: list):
    """data: list of (window_name, X_train, y_clf_tr, y_reg_tr, X_test,
    y_clf_te, y_reg_te), one per search window."""
    suggest = suggest_xgb if family == 'XGB' else suggest_rf

    def objective(trial: optuna.Trial) -> float:
        params = suggest(trial)
        losses = []
        for i, (w_name, X_tr, yc_tr, yr_tr, X_te, yc_te, yr_te) in enumerate(data):
            window_losses = []
            for seed in seeds:
                est = _make_estimator(family, task, params, seed)
                if task == 'clf':
                    est.fit(X_tr, yc_tr)
                    window_losses.append(_logloss(yc_te, est.predict_proba(X_te)[:, 1]))
                else:
                    est.fit(X_tr, yr_tr)
                    window_losses.append(float(mean_absolute_error(yr_te, est.predict(X_te))))
            losses.extend(window_losses)
            trial.report(float(np.mean(losses)), step=i)
            if trial.should_prune():
                raise optuna.TrialPruned()
        return float(np.mean(losses))

    return objective


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--csv', default='nba_ml_features_frozen.csv')
    p.add_argument('--family', default='XGB', choices=['XGB', 'RF'])
    p.add_argument('--tasks', nargs='+', default=['clf', 'reg'],
                   choices=['clf', 'reg'])
    p.add_argument('--trials', type=int, default=60)
    p.add_argument('--seeds', type=int, default=2)
    p.add_argument('--storage', default='outputs/e24_optuna.db')
    p.add_argument('--out', default='outputs/e24_hp_search.json')
    p.add_argument('--timeout-min', type=float, default=None,
                   help='per-study wall clock cap (budget trims)')
    p.add_argument('--quick', action='store_true')
    args = p.parse_args()

    if args.family == 'XGB' and not XGBOOST_AVAILABLE:
        raise SystemExit('xgboost unavailable')

    seeds = SEEDS[:args.seeds]
    windows = [w for w in FIXED_WINDOWS if w['name'] in SEARCH_WINDOWS]
    trials = args.trials
    if args.quick:
        seeds = seeds[:1]
        windows = windows[-2:]
        trials = min(trials, 4)

    df, meta = load_frozen_csv(args.csv)
    from core.features import select_features
    base_cols = select_features(df.columns)

    print(f'{args.csv}: {len(df)} games, {len(base_cols)} features; '
          f'family={args.family} tasks={args.tasks} trials={trials} '
          f'seeds={seeds} windows={[w["name"] for w in windows]}', flush=True)

    # Precompute matrices once: HPs never change preprocessing.
    data = []
    for win in windows:
        train_df = df[df['GAME_DATE'] < win['start']]
        test_df = df[(df['GAME_DATE'] >= win['start']) & (df['GAME_DATE'] <= win['end'])]
        X_tr, X_te, _ = prepare_xy(train_df, test_df, base_cols)
        data.append((win['name'], X_tr,
                     train_df['TARGET_WIN'].values.astype(int),
                     train_df['TARGET_MARGIN'].values.astype(float),
                     X_te,
                     test_df['TARGET_WIN'].values.astype(int),
                     test_df['TARGET_MARGIN'].values.astype(float)))
        print(f'  prepared {win["name"]}: train={X_tr.shape} test={X_te.shape}',
              flush=True)

    _os.makedirs('outputs', exist_ok=True)
    storage = f'sqlite:///{args.storage}'
    results = {'csv_path': args.csv, 'csv_meta': meta, 'family': args.family,
               'seeds': seeds, 'trials_requested': trials,
               'search_windows': [w['name'] for w in windows],
               'studies': {}, 'status': 'partial',
               'run_at': datetime.now().isoformat(timespec='seconds')}

    for task in args.tasks:
        study_name = f'e24_{args.family.lower()}_{task}'
        study = optuna.create_study(
            study_name=study_name, storage=storage, direction='minimize',
            sampler=optuna.samplers.TPESampler(seed=42),
            pruner=optuna.pruners.MedianPruner(n_startup_trials=8,
                                               n_warmup_steps=1),
            load_if_exists=True)
        incumbent = INCUMBENTS[(args.family, task)]
        enqueue = dict(incumbent)
        if args.family == 'XGB':
            # xgboost's default reg_alpha is 0; pin the search-space floor so
            # the enqueued trial 0 is the true incumbent, not incumbent+noise
            enqueue.setdefault('reg_alpha', 1e-3)
        if not any(t.state == optuna.trial.TrialState.COMPLETE
                   for t in study.trials):
            study.enqueue_trial(enqueue)

        objective = make_objective(args.family, task, data, seeds)
        done = len([t for t in study.trials
                    if t.state in (optuna.trial.TrialState.COMPLETE,
                                   optuna.trial.TrialState.PRUNED)])
        remaining = max(trials - done, 0)
        print(f'[{study_name}] {done} prior trials, running {remaining} more',
              flush=True)
        t0 = time.time()
        if remaining:
            study.optimize(objective, n_trials=remaining,
                           timeout=(args.timeout_min * 60
                                    if args.timeout_min else None),
                           show_progress_bar=False)

        complete = [t for t in study.trials
                    if t.state == optuna.trial.TrialState.COMPLETE]
        incumbent_trial = next(
            (t for t in complete
             if all(t.params.get(k) == v for k, v in incumbent.items())), None)
        results['studies'][study_name] = {
            'best_value': study.best_value,
            'best_params': study.best_params,
            'incumbent_params': incumbent,
            'incumbent_value': (incumbent_trial.value
                                if incumbent_trial else None),
            'n_complete': len(complete),
            'n_pruned': len([t for t in study.trials
                             if t.state == optuna.trial.TrialState.PRUNED]),
            'elapsed_min': round((time.time() - t0) / 60.0, 1),
        }
        print(f'[{study_name}] best={study.best_value:.5f} '
              f'incumbent={results["studies"][study_name]["incumbent_value"]} '
              f'({len(complete)} complete)', flush=True)
        with open(args.out, 'w') as f:
            json.dump(results, f, indent=2, default=str)

    results['status'] = 'complete'
    with open(args.out, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f'Done -> {args.out}', flush=True)


if __name__ == '__main__':
    main()
