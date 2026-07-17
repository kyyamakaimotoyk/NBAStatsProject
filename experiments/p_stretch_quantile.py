"""Stretch prototype (NO GATE): quantile-XGB heads for PTS.

Phase D reconnaissance (assessment section 3 gap #2: rate stats emit a single
number; "P(30+ points)" questions are unanswerable; "un-park before advisor
work"). This is an EXPLORATORY prototype per Kai's scope decision — report
pinball loss + interval coverage/width, no KEEP verdict; it informs the
Phase D go/no-go only.

Design: five XGB quantile regressors (reg:quantileerror, xgboost>=2.0) on the
same 137 features, predicting per-game PTS directly at q10/q25/q50/q75/q90;
per-row quantile crossing fixed by sorting. Evaluated on fold F3 (largest
train) x seeds [42, 7]:
  - pinball loss per quantile
  - q10-q90 empirical coverage (nominal 80%) + mean width, vs the published
    P2 split-conformal reference (PTS 80%: +/-7.87, coverage .809)
  - q50 MAE vs the two-stage point model's PTS MAE (sanity: the median head
    should not be far off the production point estimate)

Usage: python experiments/p_stretch_quantile.py
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
import xgboost as xgb

import modeling.player_projection_models as ppm
from data_engineering.player_dataset import OUT_PATH as DATASET_PATH
from modeling.player_projection_models import TwoStageXGB, feature_columns

FOLD = {'name': 'F3_train2225_test2526',
        'train': ['22022', '22023', '22024'], 'test': '22025'}
SEEDS = [42, 7]
QUANTILES = [0.10, 0.25, 0.50, 0.75, 0.90]
P2_CONFORMAL_REF = {'width_80': 2 * 7.87, 'coverage_80': 0.809}


def pinball(y, pred, q):
    diff = y - pred
    return float(np.mean(np.maximum(q * diff, (q - 1) * diff)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dataset', default=DATASET_PATH)
    ap.add_argument('--out', default='outputs/p_stretch_quantile.json')
    args = ap.parse_args()

    ds = pd.read_pickle(args.dataset)
    ds['GAME_DATE'] = pd.to_datetime(ds['GAME_DATE'])
    train = ds[ds['SEASON_YEAR'].isin(FOLD['train'])]
    test = ds[ds['SEASON_YEAR'] == FOLD['test']]
    feats = feature_columns(train)
    X_tr = train[feats].astype(float)
    X_te = test[feats].astype(float)
    y_tr = train['PTS'].astype(float)
    y_te = test['PTS'].to_numpy(dtype=float)
    print(f'{FOLD["name"]}: train={len(train)} test={len(test)} '
          f'features={len(feats)}', flush=True)

    out = {'fold': FOLD['name'], 'seeds': SEEDS, 'quantiles': QUANTILES,
           'p2_conformal_ref': P2_CONFORMAL_REF, 'runs': [],
           'run_at': datetime.now().isoformat(timespec='seconds')}

    for seed in SEEDS:
        t0 = time.time()
        preds = {}
        for q in QUANTILES:
            model = xgb.XGBRegressor(
                objective='reg:quantileerror', quantile_alpha=q,
                n_estimators=300, max_depth=5, learning_rate=0.05,
                min_child_weight=20, subsample=0.8, colsample_bytree=0.8,
                reg_lambda=1.0, random_state=seed, n_jobs=-1,
                tree_method='hist')
            model.fit(X_tr, y_tr)
            preds[q] = np.clip(model.predict(X_te), 0, None)
        # fix quantile crossing per row
        mat = np.sort(np.stack([preds[q] for q in QUANTILES], axis=1), axis=1)
        preds = {q: mat[:, i] for i, q in enumerate(QUANTILES)}

        ppm.SEED = seed
        two_stage = TwoStageXGB().fit(train)
        pts_point = two_stage.predict(test)['pred_PTS'].to_numpy(dtype=float)

        lo, hi = preds[0.10], preds[0.90]
        rec = {
            'seed': seed,
            'pinball': {str(q): pinball(y_te, preds[q], q) for q in QUANTILES},
            'q10_q90_coverage': float(np.mean((y_te >= lo) & (y_te <= hi))),
            'q10_q90_mean_width': float(np.mean(hi - lo)),
            'q50_mae': float(np.mean(np.abs(preds[0.50] - y_te))),
            'two_stage_pts_mae': float(np.mean(np.abs(pts_point - y_te))),
            'p30plus_note': {
                'n_actual_30plus': int((y_te >= 30).sum()),
                'n_q90_above_30': int((preds[0.90] >= 30).sum()),
            },
            'elapsed_s': round(time.time() - t0, 1),
        }
        out['runs'].append(rec)
        print(f'seed={seed}: cov80={rec["q10_q90_coverage"]:.3f} '
              f'width={rec["q10_q90_mean_width"]:.2f} '
              f'(conformal ref: cov {P2_CONFORMAL_REF["coverage_80"]}, '
              f'width {P2_CONFORMAL_REF["width_80"]:.2f}) '
              f'q50_mae={rec["q50_mae"]:.3f} vs two-stage '
              f'{rec["two_stage_pts_mae"]:.3f} [{rec["elapsed_s"]}s]', flush=True)

    _os.makedirs('outputs', exist_ok=True)
    with open(args.out, 'w') as f:
        json.dump(out, f, indent=1, default=str)
    print(f'-> {args.out}', flush=True)


if __name__ == '__main__':
    main()
