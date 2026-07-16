"""Generic multi-arm A/B harness for the 2026-07 experiment loop.

One validated instrument reused by every eval stage instead of fresh bespoke
scripts per experiment (this repo's own lesson: measurement bugs cost weeks).
Arms are declared in a small JSON spec; the harness runs
(window x arm x seed x model family), computes e3-protocol statistics, and
writes a result JSON incrementally so partial progress survives interruption.

Stages:
  w5       E12 protocol: the single frozen W5 window (train < 2026-03-15,
           test 2026-03-15..2026-04-15), default 10 seeds, pooled bootstrap +
           paired tests vs the baseline arm.
  windows  E21 meta-rule confirmation: calendar-month windows across seasons
           (gated >=50 test / >=800 train games), default 3 seeds, per-window
           paired stats plus pooled-across-windows tests and per-window delta
           sign tests.

Spec schema (experiments/specs/<exp>.json):
    {
      "experiment_id": "E22",
      "baseline_arm": "full_573",
      "arms": {
        "full_573": {},
        "top250":    {"columns_file": "outputs/e22_keep_columns_top250.json"},
        "aug_raptor":{"add_columns_file": "outputs/e25_eraptor_team_cols.csv"},
        "xgb_tuned": {"hp": {"XGB_CLF": {...}, "XGB_REG": {...}}},
        "ens_rf_xgb":{"ensemble": ["RF", "XGB"]}
      },
      "comparisons": [["top250", "full_573"]]   // default: every arm vs baseline
    }

Arm kinds:
  {}                 incumbent feature set (core.features.select_features).
  columns_file       JSON list of column names; arm uses select_features
                     INTERSECT list (drop-at-caller, the P3 idiom).
  add_columns_file   CSV keyed GAME_ID with NEW feature columns; merged onto
                     the frozen frame, arm uses select_features UNION new cols.
  hp                 hyperparameter overrides per estimator (RF_CLF, RF_REG,
                     XGB_CLF, XGB_REG). NN overrides unsupported.
  ensemble           average member families' seed-matched probabilities and
                     margins; reported under model key 'ENS'. Compared against
                     the baseline arm's single families.

Usage:
  python experiments/loop_ab.py --spec experiments/specs/e22_prune.json \
      --csv nba_ml_features_frozen.csv --stage w5 --seeds 10 \
      --models RF XGB --out outputs/e22_w5.json
"""
from __future__ import annotations

import sys as _sys
import os as _os
_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)

# harness import MUST come first: torch-before-pandas + chdir to project root.
from experiments.harness import (
    PYTORCH_AVAILABLE, XGBOOST_AVAILABLE, SEEDS, N_BOOTSTRAP,
    FIXED_WINDOWS, month_windows, load_frozen_csv, prepare_xy,
    RF_CLF_HP, RF_REG_HP, XGB_CLF_HP, XGB_REG_HP,
    bootstrap_metrics, mcnemar_test, paired_t_on_abs_err, bootstrap_auc_diff,
    bootstrap_acc_diff, bootstrap_mae_diff, train_and_predict,
)

import argparse
import json
import os
import time
from datetime import datetime

import numpy as np
import pandas as pd
from scipy import stats as scistats
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import accuracy_score, roc_auc_score, mean_absolute_error

if XGBOOST_AVAILABLE:
    import xgboost as xgb

from core.features import select_features


# ----------------------------------------------------------------------------
# Metrics
# ----------------------------------------------------------------------------

def _point_metrics(proba: np.ndarray, reg: np.ndarray,
                   y_clf: np.ndarray, y_reg: np.ndarray) -> dict:
    pred = (proba >= 0.5).astype(int)
    p = np.clip(proba, 1e-6, 1 - 1e-6)
    ece = 0.0
    edges = np.linspace(0.0, 1.0, 11)
    bin_idx = np.clip(np.digitize(proba, edges) - 1, 0, 9)
    for b in range(10):
        mask = bin_idx == b
        if mask.any():
            ece += mask.mean() * abs(float(proba[mask].mean()) - float(y_clf[mask].mean()))
    return {
        'acc': float(accuracy_score(y_clf, pred)),
        'auc': float(roc_auc_score(y_clf, proba)),
        'mae': float(mean_absolute_error(y_reg, reg)),
        'logloss': float(-np.mean(y_clf * np.log(p) + (1 - y_clf) * np.log(1 - p))),
        'brier': float(np.mean((proba - y_clf) ** 2)),
        'ece': float(ece),
    }


def _paired_entry(arm_proba, base_proba, arm_reg, base_reg, y_clf, y_reg,
                  n_bootstrap: int) -> dict:
    arm_pred = (arm_proba >= 0.5).astype(int)
    base_pred = (base_proba >= 0.5).astype(int)
    mc_stat, mc_p, wins, losses = mcnemar_test(arm_pred, base_pred, y_clf)
    t_stat, t_p, mae_diff, mae_sd = paired_t_on_abs_err(arm_reg, base_reg, y_reg)
    auc_d, auc_lo, auc_hi, auc_p = bootstrap_auc_diff(
        arm_proba, base_proba, y_clf, n_bootstrap=n_bootstrap, seed=0)
    acc_d, acc_lo, acc_hi, acc_p = bootstrap_acc_diff(
        arm_pred, base_pred, y_clf, n_bootstrap=n_bootstrap, seed=0)
    mae_d, mae_lo, mae_hi, mae_p = bootstrap_mae_diff(
        arm_reg, base_reg, y_reg, n_bootstrap=n_bootstrap, seed=0)
    return {
        'mcnemar_stat': mc_stat, 'mcnemar_p': mc_p,
        'cfg_wins': wins, 'base_wins': losses,
        'paired_t_stat': t_stat, 'paired_t_p': t_p,
        'mae_diff_mean': mae_diff, 'mae_diff_sd': mae_sd,
        'mae_diff_ci_lo': mae_lo, 'mae_diff_ci_hi': mae_hi, 'mae_diff_p': mae_p,
        'auc_diff_mean': auc_d, 'auc_diff_ci_lo': auc_lo,
        'auc_diff_ci_hi': auc_hi, 'auc_diff_p': auc_p,
        'acc_diff_mean': acc_d, 'acc_diff_ci_lo': acc_lo,
        'acc_diff_ci_hi': acc_hi, 'acc_diff_p': acc_p,
    }


# ----------------------------------------------------------------------------
# Training
# ----------------------------------------------------------------------------

def train_predict(family: str, X_train, y_clf_train, y_reg_train, X_test,
                  seed: int, hp_overrides: dict | None = None):
    """(clf_proba, reg_pred) on X_test; hp_overrides merge over prod HPs."""
    hp = hp_overrides or {}
    if family == 'RF':
        clf_hp = {**RF_CLF_HP, **hp.get('RF_CLF', {})}
        reg_hp = {**RF_REG_HP, **hp.get('RF_REG', {})}
        clf = RandomForestClassifier(**clf_hp, random_state=seed, n_jobs=-1)
        reg = RandomForestRegressor(**reg_hp, random_state=seed, n_jobs=-1)
        clf.fit(X_train, y_clf_train)
        reg.fit(X_train, y_reg_train)
        return clf.predict_proba(X_test)[:, 1], reg.predict(X_test)
    if family == 'XGB':
        if not XGBOOST_AVAILABLE:
            raise RuntimeError('xgboost unavailable')
        clf_hp = {**XGB_CLF_HP, **hp.get('XGB_CLF', {})}
        reg_hp = {**XGB_REG_HP, **hp.get('XGB_REG', {})}
        clf = xgb.XGBClassifier(**clf_hp, random_state=seed, n_jobs=-1)
        reg = xgb.XGBRegressor(**reg_hp, random_state=seed, n_jobs=-1)
        clf.fit(X_train, y_clf_train)
        reg.fit(X_train, y_reg_train)
        return clf.predict_proba(X_test)[:, 1], reg.predict(X_test)
    if family == 'NN':
        if not PYTORCH_AVAILABLE:
            raise RuntimeError('pytorch unavailable')
        if any(k.startswith('NN') for k in hp):
            raise ValueError('NN hyperparameter overrides are not supported')
        return train_and_predict(X_train, y_clf_train, y_reg_train, X_test,
                                 'NN', seed)
    raise ValueError(f'Unknown family: {family}')


# ----------------------------------------------------------------------------
# Arm resolution
# ----------------------------------------------------------------------------

def resolve_arms(spec: dict, df: pd.DataFrame):
    """Returns (df possibly augmented, {arm: {'kind', 'cols'|'members'|'hp',
    'n_features'}})."""
    base_cols = select_features(df.columns)
    resolved = {}
    for arm, cfg in spec['arms'].items():
        if 'ensemble' in cfg:
            resolved[arm] = {'kind': 'ensemble', 'members': list(cfg['ensemble']),
                             'n_features': None}
            continue
        cols = list(base_cols)
        if 'columns_file' in cfg:
            with open(cfg['columns_file']) as f:
                keep = set(json.load(f))
            cols = [c for c in cols if c in keep]
            if not cols:
                raise RuntimeError(f'arm {arm}: columns_file matched 0 features')
        if 'add_columns_file' in cfg:
            aug = pd.read_csv(cfg['add_columns_file'])
            if 'GAME_ID' not in aug.columns:
                raise RuntimeError(f'arm {arm}: add_columns_file needs GAME_ID')
            new_cols = [c for c in aug.columns if c != 'GAME_ID']
            missing = [c for c in new_cols if c not in df.columns]
            if missing:
                df = df.merge(aug[['GAME_ID'] + missing], on='GAME_ID', how='left')
            cols = cols + new_cols
        resolved[arm] = {'kind': 'features', 'cols': cols,
                         'hp': cfg.get('hp'), 'n_features': len(cols),
                         'config': {k: v for k, v in cfg.items() if k != 'hp'}}
    return df, resolved


# ----------------------------------------------------------------------------
# Main run
# ----------------------------------------------------------------------------

def _atomic_dump(obj: dict, path: str):
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(obj, f, indent=2, default=str)
    os.replace(tmp, path)


def run(args):
    with open(args.spec) as f:
        spec = json.load(f)
    df, meta = load_frozen_csv(args.csv)
    df, arms = resolve_arms(spec, df)

    seeds = SEEDS[:args.seeds]
    models = args.models
    n_bootstrap = args.n_bootstrap
    baseline = spec['baseline_arm']
    comparisons = spec.get('comparisons') or [
        [a, baseline] for a in spec['arms'] if a != baseline]

    if args.stage == 'w5':
        wins = [dict(FIXED_WINDOWS[-1])]
    else:
        wins = month_windows(df['GAME_DATE'], start=args.window_start)
        if args.limit_windows:
            wins = wins[:args.limit_windows]

    feature_arms = [a for a, r in arms.items() if r['kind'] == 'features']
    ens_arms = [a for a, r in arms.items() if r['kind'] == 'ensemble']

    out = {
        'experiment_id': spec['experiment_id'], 'stage': args.stage,
        'spec_path': args.spec, 'spec': spec,
        'csv_path': args.csv, 'csv_meta': meta,
        'models': models, 'seeds': seeds, 'n_bootstrap': n_bootstrap,
        'baseline_label': baseline,
        'arms_resolved': {a: {k: v for k, v in r.items() if k != 'cols'}
                          for a, r in arms.items()},
        'nn_available': bool(PYTORCH_AVAILABLE),
        'windows': {}, 'pooled': None,
        'status': 'partial', 'run_at': datetime.now().isoformat(timespec='seconds'),
    }

    # pooled accumulators (windows stage): seed-mean preds per (arm, family)
    pool_preds: dict = {}
    pool_y_clf: list = []
    pool_y_reg: list = []
    pool_window_names: list = []
    per_window_deltas: dict = {}

    t_start = time.time()
    for win in wins:
        w_name = win['name'] if args.stage == 'windows' else 'W5'
        w_start, w_end = win['start'], win['end']
        train_df = df[df['GAME_DATE'] < w_start]
        test_df = df[(df['GAME_DATE'] >= w_start) & (df['GAME_DATE'] <= w_end)]
        y_clf = test_df['TARGET_WIN'].values.astype(int)
        y_reg = test_df['TARGET_MARGIN'].values.astype(float)
        y_clf_train = train_df['TARGET_WIN'].values.astype(int)
        y_reg_train = train_df['TARGET_MARGIN'].values.astype(float)
        print(f'[{w_name}] train={len(train_df)} test={len(test_df)}', flush=True)

        preds: dict = {}      # (arm, family, seed) -> (proba, reg)
        window_out = {'test_start': w_start, 'test_end': w_end,
                      'n_train': int(len(train_df)), 'n_test': int(len(test_df)),
                      'summary': {}, 'per_seed': {}, 'paired': {}}

        for arm in feature_arms:
            info = arms[arm]
            X_train, X_test, valid = prepare_xy(train_df, test_df, info['cols'])
            for seed in seeds:
                for family in models:
                    if family == 'NN' and not PYTORCH_AVAILABLE:
                        continue
                    t0 = time.time()
                    proba, reg = train_predict(
                        family, X_train, y_clf_train, y_reg_train, X_test,
                        seed, info.get('hp'))
                    preds[(arm, family, seed)] = (proba, reg)
                    window_out['per_seed'][f'{arm}|{family}|{seed}'] = \
                        _point_metrics(proba, reg, y_clf, y_reg)
                    print(f'  [{w_name}] {arm} {family} seed={seed} '
                          f'{time.time()-t0:.1f}s', flush=True)

        for arm in ens_arms:
            members = arms[arm]['members']
            for seed in seeds:
                member_preds = [preds.get((baseline, m, seed)) for m in members]
                if any(p is None for p in member_preds):
                    continue
                proba = np.mean([p[0] for p in member_preds], axis=0)
                reg = np.mean([p[1] for p in member_preds], axis=0)
                preds[(arm, 'ENS', seed)] = (proba, reg)
                window_out['per_seed'][f'{arm}|ENS|{seed}'] = \
                    _point_metrics(proba, reg, y_clf, y_reg)

        # Pooled-bootstrap summary per (arm, family), e3 style
        for (arm, family) in sorted({(a, f) for (a, f, _s) in preds}):
            pooled = {'acc': [], 'auc': [], 'mae': []}
            for seed in seeds:
                if (arm, family, seed) not in preds:
                    continue
                proba, reg = preds[(arm, family, seed)]
                m = bootstrap_metrics(proba, reg, y_clf, y_reg,
                                      n_bootstrap=n_bootstrap, seed_offset=seed)
                for k in pooled:
                    pooled[k].append(m[k])
            for k in pooled:
                arr = np.concatenate(pooled[k])
                arr = arr[~np.isnan(arr)]
                window_out['summary'][f'{arm}|{family}|{k}'] = {
                    'mean': float(arr.mean()),
                    'ci_lo': float(np.percentile(arr, 2.5)),
                    'ci_hi': float(np.percentile(arr, 97.5)),
                    'std': float(arr.std(ddof=1)),
                    'n_samples': int(len(arr)),
                }

        # Seed-mean predictions per (arm, family) for paired tests + pooling
        seed_mean: dict = {}
        for (arm, family) in sorted({(a, f) for (a, f, _s) in preds}):
            probas = [preds[(arm, family, s)][0] for s in seeds
                      if (arm, family, s) in preds]
            regs = [preds[(arm, family, s)][1] for s in seeds
                    if (arm, family, s) in preds]
            seed_mean[(arm, family)] = (np.mean(probas, axis=0),
                                        np.mean(regs, axis=0))

        for arm, base in comparisons:
            arm_families = sorted({f for (a, f) in seed_mean if a == arm})
            for family in arm_families:
                base_family = family if (base, family) in seed_mean else None
                if base_family is None and family == 'ENS':
                    continue  # ENS-vs-single handled by explicit spec comparisons
                if base_family is None:
                    continue
                a_proba, a_reg = seed_mean[(arm, family)]
                b_proba, b_reg = seed_mean[(base, base_family)]
                window_out['paired'][f'{arm}|{family}'] = _paired_entry(
                    a_proba, b_proba, a_reg, b_reg, y_clf, y_reg, n_bootstrap)

        out['windows'][w_name] = window_out

        if args.stage == 'windows':
            pool_y_clf.append(y_clf)
            pool_y_reg.append(y_reg)
            pool_window_names.append(w_name)
            for key, (proba, reg) in seed_mean.items():
                pool_preds.setdefault(key, []).append((proba, reg))
            for arm, base in comparisons:
                for family in sorted({f for (a, f) in seed_mean if a == arm}):
                    if (base, family) not in seed_mean:
                        continue
                    a_p, a_r = seed_mean[(arm, family)]
                    b_p, b_r = seed_mean[(base, family)]
                    d = per_window_deltas.setdefault(
                        f'{arm}|{family}', {'windows': [], 'acc_delta': [],
                                            'mae_delta': []})
                    d['windows'].append(w_name)
                    d['acc_delta'].append(
                        float(((a_p >= 0.5).astype(int) == y_clf).mean()
                              - ((b_p >= 0.5).astype(int) == y_clf).mean()))
                    d['mae_delta'].append(
                        float(np.abs(a_r - y_reg).mean() - np.abs(b_r - y_reg).mean()))

        _atomic_dump(out, args.out)

    # Pooled-across-windows stats (windows stage)
    if args.stage == 'windows' and pool_y_clf:
        y_clf_all = np.concatenate(pool_y_clf)
        y_reg_all = np.concatenate(pool_y_reg)
        pooled_out = {'n_test': int(len(y_clf_all)),
                      'windows_used': pool_window_names,
                      'summary': {}, 'paired': {}, 'per_window': {}}
        cat = {key: (np.concatenate([p for p, _ in chunks]),
                     np.concatenate([r for _, r in chunks]))
               for key, chunks in pool_preds.items()
               if len(chunks) == len(pool_window_names)}
        for (arm, family), (proba, reg) in sorted(cat.items()):
            pm = _point_metrics(proba, reg, y_clf_all, y_reg_all)
            for k in ('acc', 'auc', 'mae'):
                pooled_out['summary'][f'{arm}|{family}|{k}'] = {'mean': pm[k]}
        baseline_arm = spec['baseline_arm']
        for arm, base in comparisons:
            for family in sorted({f for (a, f) in cat if a == arm}):
                if (base, family) not in cat:
                    continue
                a_p, a_r = cat[(arm, family)]
                b_p, b_r = cat[(base, family)]
                entry = _paired_entry(a_p, b_p, a_r, b_r,
                                      y_clf_all, y_reg_all, n_bootstrap)
                pooled_out['paired'][f'{arm}|{family}'] = entry
        for key, d in per_window_deltas.items():
            acc_pos = sum(1 for x in d['acc_delta'] if x > 0)
            acc_n = sum(1 for x in d['acc_delta'] if x != 0)
            mae_neg = sum(1 for x in d['mae_delta'] if x < 0)  # negative = arm better
            mae_n = sum(1 for x in d['mae_delta'] if x != 0)
            d['acc_sign_p'] = float(scistats.binomtest(acc_pos, acc_n).pvalue) if acc_n else 1.0
            d['mae_sign_p'] = float(scistats.binomtest(mae_neg, mae_n).pvalue) if mae_n else 1.0
            d['acc_delta_mean'] = float(np.mean(d['acc_delta']))
            d['mae_delta_mean'] = float(np.mean(d['mae_delta']))
            pooled_out['per_window'][key] = d
        out['pooled'] = pooled_out

    out['status'] = 'complete'
    out['elapsed_min'] = round((time.time() - t_start) / 60.0, 1)
    _atomic_dump(out, args.out)
    print(f'Done in {out["elapsed_min"]} min -> {args.out}', flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--spec', required=True)
    p.add_argument('--csv', default='nba_ml_features_frozen.csv')
    p.add_argument('--stage', required=True, choices=['w5', 'windows'])
    p.add_argument('--seeds', type=int, default=None,
                   help='first N of the canonical 10-seed list '
                        '(default: 10 for w5, 3 for windows)')
    p.add_argument('--models', nargs='+', default=['RF', 'XGB'],
                   choices=['RF', 'XGB', 'NN'])
    p.add_argument('--window-start', default='2023-10',
                   help='windows stage: drop months before this (YYYY-MM)')
    p.add_argument('--limit-windows', type=int, default=None)
    p.add_argument('--n-bootstrap', type=int, default=N_BOOTSTRAP)
    p.add_argument('--out', required=True)
    p.add_argument('--quick', action='store_true',
                   help='2 seeds, 200 bootstraps, limit windows to 2')
    args = p.parse_args()

    if args.seeds is None:
        args.seeds = 10 if args.stage == 'w5' else 3
    if args.quick:
        args.seeds = min(args.seeds, 2)
        args.n_bootstrap = min(args.n_bootstrap, 200)
        if args.stage == 'windows' and not args.limit_windows:
            args.limit_windows = 2

    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    run(args)


if __name__ == '__main__':
    main()
