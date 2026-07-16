"""P7: first hyperparameter search for the player TwoStageXGB (Optuna TPE).

The shared _xgb_params dict (300 trees, depth 5, lr .05, mcw 20) was hand-set
in P1 and never searched — the player sibling of team-model E24 (whose lesson
is baked in: selection and confirmation windows must never overlap).

Objective (scale-free, minimized): mean over the 11 targets of
    MAE_xgb(stat) / MAE_marcel(stat)
averaged over folds F1+F2 x 2 seeds. F3 IS NEVER TOUCHED by the search — the
winner faces the P3 keep-gate on all three folds via loop_player_ab.py's `hp`
arm afterwards.

SQLite storage -> resumable; incumbent enqueued as trial 0 (reg_alpha pinned
at the space floor since xgboost's default is 0).

Usage: python experiments/p7_hp_search.py --trials 50
  --quick: 4 trials, 1 seed, F1 only.
"""
from __future__ import annotations

import sys as _sys
import os as _os
_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)
if _os.getcwd() != _PROJECT_ROOT:
    _os.chdir(_PROJECT_ROOT)

import argparse
import json
import time
from datetime import datetime

import numpy as np
import pandas as pd
import optuna

import modeling.player_projection_models as ppm
from data_engineering.player_dataset import OUT_PATH as DATASET_PATH
from modeling.player_projection_models import MarcelBaseline, TARGETS, TwoStageXGB

SEARCH_FOLDS = [
    {'name': 'F1_train2223_test2324', 'train': ['22022'], 'test': '22023'},
    {'name': 'F2_train2224_test2425', 'train': ['22022', '22023'], 'test': '22024'},
]
SEARCH_SEEDS = [42, 7]

INCUMBENT = {'n_estimators': 300, 'max_depth': 5, 'learning_rate': 0.05,
             'min_child_weight': 20, 'subsample': 0.8, 'colsample_bytree': 0.8,
             'reg_lambda': 1.0, 'reg_alpha': 1e-3}


def suggest(trial: optuna.Trial) -> dict:
    return {
        'n_estimators': trial.suggest_int('n_estimators', 150, 600, step=50),
        'max_depth': trial.suggest_int('max_depth', 3, 8),
        'learning_rate': trial.suggest_float('learning_rate', 0.02, 0.15, log=True),
        'min_child_weight': trial.suggest_int('min_child_weight', 5, 50, log=True),
        'subsample': trial.suggest_float('subsample', 0.5, 1.0),
        'colsample_bytree': trial.suggest_float('colsample_bytree', 0.5, 1.0),
        'reg_lambda': trial.suggest_float('reg_lambda', 0.1, 30.0, log=True),
        'reg_alpha': trial.suggest_float('reg_alpha', 1e-3, 10.0, log=True),
    }


def _mae_ratio(preds, marcel_preds, test) -> float:
    ratios = []
    for s in TARGETS:
        m = preds[f'pred_{s}'].notna() & marcel_preds[f'pred_{s}'].notna()
        a = test.loc[m, s].to_numpy(dtype=float)
        mae_x = float(np.mean(np.abs(preds.loc[m, f'pred_{s}'] - a)))
        mae_m = float(np.mean(np.abs(marcel_preds.loc[m, f'pred_{s}'] - a)))
        ratios.append(mae_x / mae_m if mae_m > 0 else 1.0)
    return float(np.mean(ratios))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dataset', default=DATASET_PATH)
    ap.add_argument('--trials', type=int, default=50)
    ap.add_argument('--storage', default='outputs/p7_optuna.db')
    ap.add_argument('--out', default='outputs/p7_hp_search.json')
    ap.add_argument('--quick', action='store_true')
    args = ap.parse_args()

    folds = SEARCH_FOLDS
    seeds = SEARCH_SEEDS
    trials = args.trials
    if args.quick:
        folds, seeds, trials = folds[:1], seeds[:1], min(trials, 4)

    ds = pd.read_pickle(args.dataset)
    ds['GAME_DATE'] = pd.to_datetime(ds['GAME_DATE'])

    # precompute fold slices + Marcel predictions (HP-independent)
    prepared = []
    for fold in folds:
        train = ds[ds['SEASON_YEAR'].isin(fold['train'])]
        test = ds[ds['SEASON_YEAR'] == fold['test']]
        marcel = MarcelBaseline().fit(train).predict(test)
        prepared.append((fold['name'], train, test, marcel))
        print(f'prepared {fold["name"]}: train={len(train)} test={len(test)}',
              flush=True)

    orig_params = ppm._xgb_params

    def objective(trial: optuna.Trial) -> float:
        hp = suggest(trial)
        ppm._xgb_params = lambda obj: {**orig_params(obj), **hp}
        try:
            vals = []
            for i, (name, train, test, marcel) in enumerate(prepared):
                for seed in seeds:
                    ppm.SEED = seed
                    model = TwoStageXGB().fit(train)
                    vals.append(_mae_ratio(model.predict(test), marcel, test))
                trial.report(float(np.mean(vals)), step=i)
                if trial.should_prune():
                    raise optuna.TrialPruned()
            return float(np.mean(vals))
        finally:
            ppm._xgb_params = orig_params

    _os.makedirs('outputs', exist_ok=True)
    study = optuna.create_study(
        study_name='p7_player_xgb', storage=f'sqlite:///{args.storage}',
        direction='minimize', sampler=optuna.samplers.TPESampler(seed=42),
        pruner=optuna.pruners.MedianPruner(n_startup_trials=8, n_warmup_steps=0),
        load_if_exists=True)
    if not any(t.state == optuna.trial.TrialState.COMPLETE for t in study.trials):
        study.enqueue_trial(INCUMBENT)

    done = len([t for t in study.trials
                if t.state in (optuna.trial.TrialState.COMPLETE,
                               optuna.trial.TrialState.PRUNED)])
    remaining = max(trials - done, 0)
    print(f'{done} prior trials, running {remaining} more', flush=True)
    t0 = time.time()
    if remaining:
        study.optimize(objective, n_trials=remaining, show_progress_bar=False)

    complete = [t for t in study.trials
                if t.state == optuna.trial.TrialState.COMPLETE]
    incumbent_trial = next(
        (t for t in complete
         if all(abs(t.params.get(k, -999) - v) < 1e-12 if isinstance(v, float)
                else t.params.get(k) == v for k, v in INCUMBENT.items())), None)
    results = {
        'best_value': study.best_value, 'best_params': study.best_params,
        'incumbent_params': INCUMBENT,
        'incumbent_value': incumbent_trial.value if incumbent_trial else None,
        'n_complete': len(complete),
        'n_pruned': len([t for t in study.trials
                         if t.state == optuna.trial.TrialState.PRUNED]),
        'search_folds': [f['name'] for f in folds], 'seeds': seeds,
        'objective': 'mean over 11 targets of MAE_xgb/MAE_marcel, F1+F2 only',
        'elapsed_min': round((time.time() - t0) / 60.0, 1),
        'run_at': datetime.now().isoformat(timespec='seconds'),
    }
    with open(args.out, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f'best={results["best_value"]:.5f} '
          f'incumbent={results["incumbent_value"]} '
          f'({len(complete)} complete, {results["n_pruned"]} pruned) '
          f'-> {args.out}', flush=True)


if __name__ == '__main__':
    main()
