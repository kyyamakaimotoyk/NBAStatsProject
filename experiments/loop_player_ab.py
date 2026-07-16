"""Generic multi-arm A/B harness for the PLAYER projection models (P4+ loop).

The player twin of experiments/loop_ab.py, built on the P1-P3 protocol rather
than experiments/harness.py (no torch, no frozen team CSV — importing harness
would drag in e3's team machinery; deviation deliberate). One validated
instrument reused by every player experiment, arms declared in a JSON spec.

Protocol (P3): 3 walk-forward season folds x seeds [42, 7, 202]; Marcel is the
always-computed must-beat baseline; paired scipy ttest_rel on per-row |error|
per stat; keep-gate = delta_mae < 0 AND p < 0.05 in ALL folds for >= 2 of 3
seeds (per stat). A regression flag (stat significantly WORSE in >= 2 folds
for >= 2 seeds) is also evaluated for the E10-style caution.

Spec schema (experiments/specs/p*.json):
    {
      "experiment_id": "P4",
      "baseline_arm": "baseline",
      "arms": {
        "baseline":   {},
        "d2_fatigue": {"add_columns_file": "outputs/p4_cols_d2.parquet"},
        "p6_mstl":    {"serve_marcel_for": ["STL"]},
        "hp_tuned":   {"hp": {"max_depth": 4}},
        "drop_x":     {"drop_columns": ["PIE_L10"]}
      },
      "diagnostics": true
    }

Arm kinds (all via DataFrame column control — feature_columns() recomputes
from df.columns at fit time, the P3 idiom):
  {}                incumbent feature set.
  add_columns_file  parquet keyed (GAME_ID, personId) or (GAME_ID, TEAM_ID);
                    the UNION of all arms' add-columns is merged once, then
                    every arm (baseline included) drops the added columns it
                    does not own — names ending _L5/_L10/_TREND/36_SEASON are
                    auto-captured by feature_columns() and would otherwise
                    contaminate other arms silently.
  drop_columns      dropped from train+test copies (refused for LOAD_BEARING).
  serve_marcel_for  baseline XGB predictions with the listed stats replaced by
                    the fold's Marcel predictions (zero extra fits).
  hp                dict merged over _xgb_params() output for this arm's fits.

Usage:
  python experiments/loop_player_ab.py --spec experiments/specs/p4_feature_groups.json \
      --out outputs/p4_ab.json
  --quick: 1 seed, fold F1 only.
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
import hashlib
import json
import time
from datetime import datetime

import numpy as np
import pandas as pd
from scipy import stats as scistats

import modeling.player_projection_models as ppm
from data_engineering.player_dataset import OUT_PATH as DATASET_PATH
from modeling.player_projection_models import (
    MarcelBaseline, NaiveBaseline, TARGETS, TwoStageXGB)

FOLDS = [
    {'name': 'F1_train2223_test2324', 'train': ['22022'], 'test': '22023'},
    {'name': 'F2_train2224_test2425', 'train': ['22022', '22023'], 'test': '22024'},
    {'name': 'F3_train2225_test2526', 'train': ['22022', '22023', '22024'], 'test': '22025'},
]
SEEDS = [42, 7, 202]
FP_WEIGHTS = {'PTS': 1.0, 'REB': 1.2, 'AST': 1.5, 'STL': 3.0, 'BLK': 3.0, 'TOV': -1.0}
EXPECTED_BASELINE_FEATURES = 137

# Never droppable: read directly in predict()/Marcel/rate targets beyond the
# feature list, or structural (IDs, dates, fold keys).
LOAD_BEARING = (
    {'MIN', 'MIN_L5', 'MIN_L10', 'MIN_SEASON_AVG', 'GP_SEASON',
     'SHRUNK_3P_PCT', 'SHRUNK_FT_PCT',
     'GAME_ID', 'GAME_DATE', 'SEASON_ID', 'SEASON_YEAR', 'personId',
     'TEAM_ID', 'OPP_TEAM_ID'}
    | {f'{s}_36G' for s in TARGETS[1:]}
    | {f'{s}36_L10' for s in TARGETS[1:]}
    | {f'{s}36_SEASON' for s in TARGETS[1:]}
    | {f'PREV_{s}36' for s in TARGETS[1:]}
)


def _atomic_dump(obj: dict, path: str):
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(obj, f, indent=1, default=str)
    _os.replace(tmp, path)


def _provenance(path: str, df: pd.DataFrame) -> dict:
    with open(path, 'rb') as f:
        sha = hashlib.sha1(f.read()).hexdigest()[:12]
    return {
        'dataset_path': path, 'sha1_12': sha,
        'mtime': datetime.fromtimestamp(_os.path.getmtime(path)).isoformat(timespec='seconds'),
        'n_rows': int(len(df)), 'n_cols': int(len(df.columns)),
        'rows_per_season': {str(k): int(v) for k, v in
                            df['SEASON_YEAR'].value_counts().sort_index().items()},
        'data_through': str(pd.to_datetime(df['GAME_DATE']).max().date()),
    }


def _fp(frame: pd.DataFrame, prefix: str = '') -> np.ndarray:
    """Fantasy-point composite from actual columns ('' prefix) or pred_ cols."""
    total = np.zeros(len(frame))
    for s, w in FP_WEIGHTS.items():
        total = total + w * frame[f'{prefix}{s}'].to_numpy(dtype=float)
    return total


def _mae_block(preds: pd.DataFrame, test: pd.DataFrame) -> dict:
    out = {}
    for s in TARGETS:
        mask = preds[f'pred_{s}'].notna()
        out[s] = float(np.mean(np.abs(
            preds.loc[mask, f'pred_{s}'].to_numpy(dtype=float)
            - test.loc[mask, s].to_numpy(dtype=float))))
    return out


def _paired(preds_a: pd.DataFrame, preds_b: pd.DataFrame,
            test: pd.DataFrame) -> dict:
    """Per-stat paired t on |error|: negative delta = A better than B."""
    out = {}
    for s in TARGETS:
        mask = preds_a[f'pred_{s}'].notna() & preds_b[f'pred_{s}'].notna()
        a = np.abs(preds_a.loc[mask, f'pred_{s}'].to_numpy(dtype=float)
                   - test.loc[mask, s].to_numpy(dtype=float))
        b = np.abs(preds_b.loc[mask, f'pred_{s}'].to_numpy(dtype=float)
                   - test.loc[mask, s].to_numpy(dtype=float))
        if np.allclose(a, b):
            out[s] = {'delta_mae': 0.0, 't': 0.0, 'p': 1.0}
            continue
        t, p = scistats.ttest_rel(a, b)
        out[s] = {'delta_mae': float((a - b).mean()), 't': float(t), 'p': float(p)}
    return out


# ----------------------------------------------------------------------------
# Arm resolution
# ----------------------------------------------------------------------------

def resolve_arms(spec: dict, ds: pd.DataFrame):
    """Merge the union of add-columns; return (ds, arm_info dict).

    arm_info[arm] = {'kind', 'owned_adds': [cols], 'drop': [cols],
                     'serve_marcel_for': [stats], 'hp': dict|None}
    """
    all_added: list[str] = []
    arm_info: dict = {}
    for arm, cfg in spec['arms'].items():
        info = {'kind': 'feature', 'owned_adds': [], 'drop': [],
                'serve_marcel_for': cfg.get('serve_marcel_for'),
                'hp': cfg.get('hp')}
        if cfg.get('serve_marcel_for'):
            info['kind'] = 'serve_marcel'
        if 'drop_columns' in cfg:
            bad = set(cfg['drop_columns']) & LOAD_BEARING
            if bad:
                raise RuntimeError(f'arm {arm}: refusing to drop LOAD_BEARING {sorted(bad)}')
            info['drop'] = list(cfg['drop_columns'])
        if 'add_columns_file' in cfg:
            add = pd.read_parquet(cfg['add_columns_file'])
            if 'personId' in add.columns:
                keys = ['GAME_ID', 'personId']
            elif 'TEAM_ID' in add.columns:
                keys = ['GAME_ID', 'TEAM_ID']
            else:
                raise RuntimeError(f'arm {arm}: add file needs personId or TEAM_ID key')
            new_cols = [c for c in add.columns if c not in keys]
            missing = [c for c in new_cols if c not in ds.columns]
            if missing:
                ds = ds.merge(add[keys + missing], on=keys, how='left')
            info['owned_adds'] = new_cols
            all_added.extend(new_cols)
        arm_info[arm] = info

    all_added = sorted(set(all_added))
    # register non-pattern names so feature_columns() can see them
    explicit_new = [c for c in all_added
                    if not (c.endswith(ppm._SUFFIXES) and not c.endswith('_36G'))
                    and not (c.startswith('PREV_') and c.endswith('36'))]
    return ds, arm_info, all_added, explicit_new


def arm_frames(ds_train: pd.DataFrame, ds_test: pd.DataFrame, info: dict,
               all_added: list):
    """Per-arm train/test views: drop every added column the arm does not own,
    plus its own drop_columns. Baseline owns nothing -> drops all adds."""
    not_owned = [c for c in all_added if c not in info['owned_adds']]
    drop = [c for c in not_owned + info['drop'] if c in ds_train.columns]
    return ds_train.drop(columns=drop), ds_test.drop(columns=drop)


# ----------------------------------------------------------------------------
# Diagnostics (report-only; assessment section 3 items)
# ----------------------------------------------------------------------------

def diagnostics_block(preds: pd.DataFrame, test: pd.DataFrame) -> dict:
    out = {}
    t = test.reset_index(drop=True)
    p = preds.reset_index(drop=True)

    # residual vs own volatility: MAE of MIN / PTS / FP by MIN_STD_L10 quartile
    vol = t['MIN_STD_L10']
    quart = pd.qcut(vol, 4, labels=['q1_stable', 'q2', 'q3', 'q4_volatile'],
                    duplicates='drop')
    rows = {}
    fp_actual = _fp(t)
    fp_pred = _fp(p, 'pred_')
    for q in quart.cat.categories:
        m = (quart == q).to_numpy()
        rows[str(q)] = {
            'n': int(m.sum()),
            'mae_MIN': float(np.mean(np.abs(p.loc[m, 'pred_MIN'] - t.loc[m, 'MIN']))),
            'mae_PTS': float(np.mean(np.abs(p.loc[m, 'pred_PTS'] - t.loc[m, 'PTS']))),
            'mae_FP': float(np.mean(np.abs(fp_pred[m] - fp_actual[m]))),
        }
    out['residual_vs_volatility'] = rows

    # blowup/dud: actual vs player's season-average per-game baseline
    blow = {}
    season_min = t['MIN_SEASON_AVG'].to_numpy(dtype=float)
    gp_ok = (t['GP_SEASON'].to_numpy(dtype=float) >= 10)
    starter = (t['STARTS_SHARE_L10'].to_numpy(dtype=float) >= 0.5)
    for s in ('PTS', 'REB', 'AST'):
        season_avg = t[f'{s}36_SEASON'].to_numpy(dtype=float) * season_min / 36.0
        valid = gp_ok & np.isfinite(season_avg) & (season_avg > 1.0)
        actual = t[s].to_numpy(dtype=float)
        pred = p[f'pred_{s}'].to_numpy(dtype=float)
        entry = {}
        for label, mask_rel in (
                ('blowup_gt_1p5x', actual > 1.5 * season_avg),
                ('dud_lt_0p5x', actual < 0.5 * season_avg)):
            m = valid & mask_rel
            sub = {'share': float(m.sum() / max(valid.sum(), 1)), 'n': int(m.sum())}
            for role, rm in (('all', m), ('starters', m & starter),
                             ('bench', m & ~starter)):
                if rm.sum() > 0:
                    sub[f'mae_{role}'] = float(np.mean(np.abs(pred[rm] - actual[rm])))
                    sub[f'signed_err_{role}'] = float(np.mean(pred[rm] - actual[rm]))
            entry[label] = sub
        blow[s] = entry
    out['blowup_dud'] = blow
    return out


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def run(args):
    with open(args.spec) as f:
        spec = json.load(f)
    ds = pd.read_pickle(args.dataset)
    ds['GAME_DATE'] = pd.to_datetime(ds['GAME_DATE'])
    prov = _provenance(args.dataset, ds)
    print(f'dataset: {prov["n_rows"]} x {prov["n_cols"]} sha1={prov["sha1_12"]} '
          f'through {prov["data_through"]}', flush=True)

    ds, arm_info, all_added, explicit_new = resolve_arms(spec, ds)
    baseline = spec['baseline_arm']
    seeds = SEEDS[:args.seeds]
    folds = [f for f in FOLDS if f['name'].split('_')[0] in args.folds]

    out = {
        'experiment_id': spec['experiment_id'], 'spec_path': args.spec,
        'spec': spec, 'provenance': prov,
        'seeds': seeds, 'folds': [f['name'] for f in folds],
        'arms_resolved': {}, 'runs': [], 'verdicts': {},
        'diagnostics': None, 'status': 'partial',
        'run_at': datetime.now().isoformat(timespec='seconds'),
    }

    orig_explicit = list(ppm._EXPLICIT_FEATURES)
    orig_params = ppm._xgb_params
    t_start = time.time()
    try:
        for c in explicit_new:
            if c not in ppm._EXPLICIT_FEATURES:
                ppm._EXPLICIT_FEATURES.append(c)

        for fold in folds:
            train_all = ds[ds['SEASON_YEAR'].isin(fold['train'])]
            test_all = ds[ds['SEASON_YEAR'] == fold['test']]
            print(f'[{fold["name"]}] train={len(train_all)} test={len(test_all)}',
                  flush=True)

            # deterministic baselines, once per fold (on the baseline view)
            b_train, b_test = arm_frames(train_all, test_all, arm_info[baseline],
                                         all_added)
            marcel_preds = MarcelBaseline().fit(b_train).predict(b_test)
            naive_preds = NaiveBaseline().fit(b_train).predict(b_test)

            for seed in seeds:
                ppm.SEED = seed
                run_rec = {'fold': fold['name'], 'seed': seed,
                           'n_train': int(len(train_all)), 'n_test': int(len(test_all)),
                           'arms': {},
                           'marcel': {'mae': _mae_block(marcel_preds, b_test),
                                      'fp_mae': float(np.mean(np.abs(
                                          _fp(marcel_preds, 'pred_') - _fp(b_test))))},
                           'naive': {'mae': _mae_block(naive_preds, b_test)}}

                arm_preds: dict = {}
                for arm, info in arm_info.items():
                    if info['kind'] == 'serve_marcel':
                        continue  # derived after baseline
                    a_train, a_test = arm_frames(train_all, test_all, info, all_added)
                    if info['hp']:
                        ppm._xgb_params = (lambda hp_over: lambda obj:
                                           {**orig_params(obj), **hp_over})(info['hp'])
                    t0 = time.time()
                    try:
                        model = TwoStageXGB().fit(a_train)
                        preds = model.predict(a_test)
                    finally:
                        ppm._xgb_params = orig_params
                    n_feats = len(model.features)
                    if arm == baseline and n_feats != args.expect_features:
                        raise RuntimeError(
                            f'baseline resolved to {n_feats} features, expected '
                            f'{args.expect_features} - arm contamination?')
                    out['arms_resolved'].setdefault(arm, {})['n_features'] = n_feats
                    arm_preds[arm] = preds
                    print(f'  [{fold["name"]}] {arm} seed={seed} '
                          f'({n_feats} feats) {time.time()-t0:.1f}s', flush=True)

                for arm, info in arm_info.items():
                    if info['kind'] != 'serve_marcel':
                        continue
                    preds = arm_preds[baseline].copy()
                    for s in info['serve_marcel_for']:
                        preds[f'pred_{s}'] = marcel_preds[f'pred_{s}'].to_numpy()
                    arm_preds[arm] = preds
                    out['arms_resolved'].setdefault(arm, {})['n_features'] = \
                        out['arms_resolved'][baseline]['n_features']

                for arm, preds in arm_preds.items():
                    _, a_test = arm_frames(train_all, test_all, arm_info[arm], all_added)
                    rec = {'mae': _mae_block(preds, a_test),
                           'fp_mae': float(np.mean(np.abs(
                               _fp(preds, 'pred_') - _fp(a_test))))}
                    if arm != baseline:
                        rec['vs_baseline'] = _paired(preds, arm_preds[baseline], a_test)
                    arm_rec = rec
                    run_rec['arms'][arm] = arm_rec
                run_rec['xgb_vs_marcel'] = _paired(arm_preds[baseline], marcel_preds,
                                                   b_test)
                out['runs'].append(run_rec)
                _atomic_dump(out, args.out)

            if (spec.get('diagnostics') and fold is folds[-1]):
                # diagnostics on the LAST seed's baseline predictions (single-seed,
                # report-only; noted in the JSON)
                out['diagnostics'] = {
                    'note': 'computed on final fold, last seed, baseline arm (report-only)',
                    'fold': fold['name'], 'seed': seeds[-1],
                    **diagnostics_block(arm_preds[baseline], b_test)}
                _atomic_dump(out, args.out)
    finally:
        ppm._EXPLICIT_FEATURES[:] = orig_explicit
        ppm._xgb_params = orig_params

    # ------------------------------------------------------------------
    # P3-gate verdicts per (arm, stat)
    # ------------------------------------------------------------------
    fold_names = [f['name'] for f in folds]
    for arm in spec['arms']:
        if arm == baseline:
            continue
        per_stat = {}
        keep_stats, regression_stats = [], []
        for s in TARGETS:
            passing = 0
            worse_seed_count = 0
            deltas = []
            for seed in seeds:
                runs = [r for r in out['runs'] if r['seed'] == seed
                        and arm in r['arms'] and 'vs_baseline' in r['arms'][arm]]
                if len(runs) != len(fold_names):
                    continue
                entries = [r['arms'][arm]['vs_baseline'][s] for r in runs]
                deltas.extend(e['delta_mae'] for e in entries)
                if all(e['delta_mae'] < 0 and e['p'] < 0.05 for e in entries):
                    passing += 1
                n_worse = sum(1 for e in entries
                              if e['delta_mae'] > 0 and e['p'] < 0.05)
                if n_worse >= 2:
                    worse_seed_count += 1
            keep = passing >= 2
            regress = worse_seed_count >= 2
            per_stat[s] = {'seeds_passing_all_folds': passing,
                           'seeds_worse_2plus_folds': worse_seed_count,
                           'mean_delta_mae': float(np.mean(deltas)) if deltas else None,
                           'keep': keep, 'regression_flag': regress}
            if keep:
                keep_stats.append(s)
            if regress:
                regression_stats.append(s)
        group_verdict = ('REJECT_REGRESSION' if regression_stats
                         else ('KEEP' if keep_stats else 'REJECT'))
        out['verdicts'][arm] = {'per_stat': per_stat, 'keep_stats': keep_stats,
                                'regression_stats': regression_stats,
                                'group_verdict': group_verdict}

    out['status'] = 'complete'
    out['elapsed_min'] = round((time.time() - t_start) / 60.0, 1)
    _atomic_dump(out, args.out)
    print(f'Done in {out["elapsed_min"]} min -> {args.out}', flush=True)
    for arm, v in out['verdicts'].items():
        print(f'  {arm}: {v["group_verdict"]} keep_stats={v["keep_stats"]} '
              f'regressions={v["regression_stats"]}', flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--spec', required=True)
    p.add_argument('--dataset', default=DATASET_PATH)
    p.add_argument('--out', required=True)
    p.add_argument('--seeds', type=int, default=3)
    p.add_argument('--folds', nargs='+', default=['F1', 'F2', 'F3'])
    p.add_argument('--expect-features', type=int, default=137)
    p.add_argument('--quick', action='store_true')
    args = p.parse_args()
    if args.quick:
        args.seeds = 1
        args.folds = ['F1']
    _os.makedirs(_os.path.dirname(args.out) or '.', exist_ok=True)
    run(args)


if __name__ == '__main__':
    main()
