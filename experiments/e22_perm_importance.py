"""E22 step 1: multi-seed permutation importance for feature pruning.

Implements the July 2026 assessment's pruning recipe (section 2.1): permutation
importance on the walk-forward harness -> keep top ~150-250 columns -> re-run
the A/B protocol. This script produces the RANKING and the keep-columns files;
the eval arms run through experiments/loop_ab.py.

Protocol:
  - RF + XGB, classifier + regressor, at production hyperparameters.
  - The 5 fixed walk-forward windows (W1..W5), train strictly before each
    window, preprocessing fit on train only.
  - Importance computed on each window's TEST slice (out-of-sample importance
    is the honest pruning signal), scoring neg-log-loss (clf) / neg-MAE (reg).
  - Aggregation is at BASE-FEATURE-GROUP level (HOME_/AWAY_/DIFF_ triplets stay
    together — column-level permutation splits credit across the correlated
    triplet and would prune "individually weak, collectively load-bearing"
    members). Top-K arms take whole groups by mean normalized rank until the
    expanded column count reaches K.

Outputs:
  outputs/e22_perm_importance.json          per-run records (incremental)
  outputs/e22_feature_ranks_columns.csv     column-level table
  outputs/e22_feature_ranks_groups.csv      group-level table
  outputs/e22_keep_columns_top<K>.json      exact column lists for loop_ab

Usage:
  python experiments/e22_perm_importance.py --seeds 3 --n-repeats 5 \
      --csv nba_ml_features_frozen.csv --topk 250 150
  --quick: 1 seed, W5 only, n_repeats=2 (smoke).
"""
from __future__ import annotations

import sys as _sys
import os as _os
_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)

from experiments.harness import (
    XGBOOST_AVAILABLE, SEEDS, FIXED_WINDOWS, load_frozen_csv, prepare_xy,
    RF_CLF_HP, RF_REG_HP, XGB_CLF_HP, XGB_REG_HP, feature_group,
)

import argparse
import json
import time
from datetime import datetime

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.inspection import permutation_importance

if XGBOOST_AVAILABLE:
    import xgboost as xgb

from core.features import select_features


def _make_estimator(family: str, task: str, seed: int):
    if family == 'RF':
        if task == 'clf':
            return RandomForestClassifier(**RF_CLF_HP, random_state=seed, n_jobs=-1)
        return RandomForestRegressor(**RF_REG_HP, random_state=seed, n_jobs=-1)
    if family == 'XGB':
        if task == 'clf':
            return xgb.XGBClassifier(**XGB_CLF_HP, random_state=seed, n_jobs=-1)
        return xgb.XGBRegressor(**XGB_REG_HP, random_state=seed, n_jobs=-1)
    raise ValueError(family)


def _atomic_dump(obj, path):
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(obj, f, default=str)
    _os.replace(tmp, path)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--csv', default='nba_ml_features_frozen.csv')
    p.add_argument('--seeds', type=int, default=3)
    p.add_argument('--n-repeats', type=int, default=5)
    p.add_argument('--models', nargs='+', default=['RF', 'XGB'],
                   choices=['RF', 'XGB'])
    p.add_argument('--topk', type=int, nargs='+', default=[250, 150])
    p.add_argument('--out', default='outputs/e22_perm_importance.json')
    p.add_argument('--quick', action='store_true')
    args = p.parse_args()

    seeds = SEEDS[:args.seeds]
    windows = list(FIXED_WINDOWS)
    n_repeats = args.n_repeats
    if args.quick:
        seeds = seeds[:1]
        windows = windows[-1:]
        n_repeats = min(n_repeats, 2)

    df, meta = load_frozen_csv(args.csv)
    base_cols = select_features(df.columns)
    print(f'{args.csv}: {len(df)} games, {len(base_cols)} model features')
    print(f'windows={[w["name"] for w in windows]} seeds={seeds} '
          f'n_repeats={n_repeats} models={args.models}', flush=True)

    out = {'csv_path': args.csv, 'csv_meta': meta, 'seeds': seeds,
           'n_repeats': n_repeats, 'models': args.models,
           'windows': [w['name'] for w in windows],
           'runs': [], 'status': 'partial',
           'run_at': datetime.now().isoformat(timespec='seconds')}
    _os.makedirs('outputs', exist_ok=True)

    t_start = time.time()
    for win in windows:
        train_df = df[df['GAME_DATE'] < win['start']]
        test_df = df[(df['GAME_DATE'] >= win['start']) & (df['GAME_DATE'] <= win['end'])]
        X_train, X_test, valid_cols = prepare_xy(train_df, test_df, base_cols)
        y_clf_train = train_df['TARGET_WIN'].values.astype(int)
        y_reg_train = train_df['TARGET_MARGIN'].values.astype(float)
        y_clf_test = test_df['TARGET_WIN'].values.astype(int)
        y_reg_test = test_df['TARGET_MARGIN'].values.astype(float)
        print(f'[{win["name"]}] train={len(train_df)} test={len(test_df)} '
              f'valid_cols={len(valid_cols)}', flush=True)

        for seed in seeds:
            for family in args.models:
                if family == 'XGB' and not XGBOOST_AVAILABLE:
                    continue
                for task in ('clf', 'reg'):
                    t0 = time.time()
                    est = _make_estimator(family, task, seed)
                    if task == 'clf':
                        est.fit(X_train, y_clf_train)
                        y_t, scoring = y_clf_test, 'neg_log_loss'
                    else:
                        est.fit(X_train, y_reg_train)
                        y_t, scoring = y_reg_test, 'neg_mean_absolute_error'
                    # avoid nested parallelism: model predicts single-threaded
                    # while permutation_importance parallelizes over columns
                    try:
                        est.set_params(n_jobs=1)
                    except ValueError:
                        pass
                    imp = permutation_importance(
                        est, X_test, y_t, scoring=scoring,
                        n_repeats=n_repeats, random_state=seed, n_jobs=-1)
                    out['runs'].append({
                        'window': win['name'], 'seed': seed, 'family': family,
                        'task': task, 'columns': valid_cols,
                        'importances': [float(v) for v in imp.importances_mean],
                    })
                    print(f'  [{win["name"]}] {family}-{task} seed={seed} '
                          f'{time.time()-t0:.1f}s', flush=True)
                    _atomic_dump(out, args.out)

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------
    col_rank_sum: dict = {}
    col_runs: dict = {}
    col_nonpos: dict = {}
    grp_rank_sum: dict = {}
    grp_runs: dict = {}

    for run in out['runs']:
        cols = run['columns']
        imps = np.asarray(run['importances'])
        order = np.argsort(-imps)          # descending importance
        ranks = np.empty(len(cols))
        ranks[order] = np.arange(len(cols))
        norm = ranks / max(len(cols) - 1, 1)
        for c, r, v in zip(cols, norm, imps):
            col_rank_sum[c] = col_rank_sum.get(c, 0.0) + float(r)
            col_runs[c] = col_runs.get(c, 0) + 1
            col_nonpos[c] = col_nonpos.get(c, 0) + (1 if v <= 0 else 0)
        # group importance = sum of member importances within this run
        gimp: dict = {}
        for c, v in zip(cols, imps):
            g = feature_group(c)
            gimp[g] = gimp.get(g, 0.0) + float(v)
        gnames = list(gimp)
        gvals = np.asarray([gimp[g] for g in gnames])
        gorder = np.argsort(-gvals)
        granks = np.empty(len(gnames))
        granks[gorder] = np.arange(len(gnames))
        gnorm = granks / max(len(gnames) - 1, 1)
        for g, r in zip(gnames, gnorm):
            grp_rank_sum[g] = grp_rank_sum.get(g, 0.0) + float(r)
            grp_runs[g] = grp_runs.get(g, 0) + 1

    col_table = pd.DataFrame({
        'column': list(col_rank_sum),
        'mean_norm_rank': [col_rank_sum[c] / col_runs[c] for c in col_rank_sum],
        'n_runs': [col_runs[c] for c in col_rank_sum],
        'frac_nonpositive': [col_nonpos[c] / col_runs[c] for c in col_rank_sum],
    }).sort_values('mean_norm_rank').reset_index(drop=True)
    col_table['group'] = col_table['column'].map(feature_group)
    col_table.to_csv('outputs/e22_feature_ranks_columns.csv', index=False)

    grp_members: dict = {}
    for c in base_cols:
        grp_members.setdefault(feature_group(c), []).append(c)
    grp_table = pd.DataFrame({
        'group': list(grp_rank_sum),
        'mean_norm_rank': [grp_rank_sum[g] / grp_runs[g] for g in grp_rank_sum],
        'n_runs': [grp_runs[g] for g in grp_rank_sum],
        'n_member_columns': [len(grp_members.get(g, [])) for g in grp_rank_sum],
    }).sort_values('mean_norm_rank').reset_index(drop=True)
    grp_table.to_csv('outputs/e22_feature_ranks_groups.csv', index=False)
    covered = int(grp_table['n_member_columns'].sum())
    missing_groups = sorted(set(grp_members) - set(grp_table['group']))
    print(f'groups: {len(grp_table)} covering {covered}/{len(base_cols)} columns')
    if missing_groups:
        # groups whose every member was all-NaN in some train slice never got
        # an importance score; they are simply never selected into keep lists
        print(f'  unranked groups (all-NaN in train): {missing_groups}')
    assert covered >= len(base_cols) - 20, \
        'ranking lost too many columns - investigate before pruning'

    keep_files = {}
    for k in args.topk:
        keep: list = []
        for _, row in grp_table.iterrows():
            if len(keep) >= k:
                break
            keep.extend(grp_members.get(row['group'], []))
        path = f'outputs/e22_keep_columns_top{k}.json'
        with open(path, 'w') as f:
            json.dump(keep, f, indent=0)
        keep_files[k] = {'path': path, 'n_columns': len(keep)}
        print(f'top{k}: {len(keep)} columns -> {path}')

    out['keep_files'] = keep_files
    out['n_groups'] = int(len(grp_table))
    out['status'] = 'complete'
    out['elapsed_min'] = round((time.time() - t_start) / 60.0, 1)
    _atomic_dump(out, args.out)
    print(f'Done in {out["elapsed_min"]} min -> {args.out}', flush=True)


if __name__ == '__main__':
    main()
