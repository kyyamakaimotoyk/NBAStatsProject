"""P5: isotonic tail-calibration for the STL/BLK Poisson heads.

Documented problem (P1/P2 reports, assessment section 3 gap #1): decile MEAN
calibration is tight, but above lambda~2 the Poisson head over-forecasts the
2+ tail (e.g. BLK bin [2,3): implied P(2+) .666 vs empirical .632) — the
conditional mean is right, the Poisson SHAPE assumption is wrong (empirically
underdispersed for elite defensive-event games). XGBoost has no NB objective;
changing the objective attacks the wrong lever and risks the mean calibration.

Fix under test: post-hoc isotonic maps, fit on a held-out calibration slice of
train, leaving point predictions BYTE-IDENTICAL (MAE non-regression holds by
construction):
    iso0: lambda -> P(y = 0)    (decreasing)
    iso2: lambda -> P(y >= 2)   (increasing)
    P(1) = 1 - P0 - P2plus      (clipped, renormalized)

Protocol: P3 folds x seeds [42, 7, 202]. Per (fold, seed): chronological 85/15
split of the fold's train -> fit TwoStageXGB on the 85% -> its lambdas on the
15% fit the maps -> evaluate on the fold's TEST season with the same model's
lambdas, comparing Poisson-implied vs isotonic-implied against empirical in
the P1 lambda-bin table, plus a 3-bucket {0,1,2+} Brier score.

Gate (pre-registered in outputs/player_loop_state.json): KEEP iff in ALL 3
folds, for BOTH stats, isotonic mean |implied-empirical| P(2+) over
lambda>=1 bins (n>=30) < Poisson's AND Brier no worse in any fold.

Usage: python experiments/p5_tail_calibration.py --out outputs/p5_tail_calibration.json
  --quick: 1 seed, F1 only.
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
from sklearn.isotonic import IsotonicRegression

import modeling.player_projection_models as ppm
from data_engineering.player_dataset import OUT_PATH as DATASET_PATH
from modeling.player_projection_models import TwoStageXGB

FOLDS = [
    {'name': 'F1_train2223_test2324', 'train': ['22022'], 'test': '22023'},
    {'name': 'F2_train2224_test2425', 'train': ['22022', '22023'], 'test': '22024'},
    {'name': 'F3_train2225_test2526', 'train': ['22022', '22023', '22024'], 'test': '22025'},
]
SEEDS = [42, 7, 202]
STATS = ['STL', 'BLK']
BINS = [0.0, 0.5, 1.0, 1.5, 2.0, 3.0, np.inf]
MIN_BIN_N = 30
CAL_FRACTION = 0.15


def poisson_probs(lam: np.ndarray):
    p0 = np.exp(-lam)
    p1 = lam * np.exp(-lam)
    p2 = np.clip(1.0 - p0 - p1, 0.0, 1.0)
    return p0, p1, p2


def iso_probs(lam, iso0, iso2):
    p0 = np.clip(iso0.predict(lam), 0.0, 1.0)
    p2 = np.clip(iso2.predict(lam), 0.0, 1.0)
    p1 = np.clip(1.0 - p0 - p2, 0.0, 1.0)
    tot = p0 + p1 + p2
    return p0 / tot, p1 / tot, p2 / tot


def bin_table(lam, y, probs):
    p0, p1, p2 = probs
    idx = np.digitize(lam, BINS) - 1
    rows = []
    for b in range(len(BINS) - 1):
        m = idx == b
        if m.sum() < MIN_BIN_N:
            continue
        rows.append({
            'bin': f'[{BINS[b]},{BINS[b+1]})', 'lo': float(BINS[b]),
            'n': int(m.sum()), 'mean_lambda': float(lam[m].mean()),
            'emp_p0': float((y[m] == 0).mean()),
            'emp_p2plus': float((y[m] >= 2).mean()),
            'imp_p0': float(p0[m].mean()),
            'imp_p2plus': float(p2[m].mean()),
        })
    return rows


def headline(table):
    """Mean |implied-empirical| P(2+) over bins with lower edge >= 1."""
    gaps = [abs(r['imp_p2plus'] - r['emp_p2plus']) for r in table if r['lo'] >= 1.0]
    return float(np.mean(gaps)) if gaps else None


def brier3(lam_or_probs, y):
    p0, p1, p2 = lam_or_probs
    i0 = (y == 0).astype(float)
    i1 = (y == 1).astype(float)
    i2 = (y >= 2).astype(float)
    return float(np.mean((p0 - i0) ** 2 + (p1 - i1) ** 2 + (p2 - i2) ** 2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dataset', default=DATASET_PATH)
    ap.add_argument('--out', default='outputs/p5_tail_calibration.json')
    ap.add_argument('--seeds', type=int, default=3)
    ap.add_argument('--quick', action='store_true')
    args = ap.parse_args()
    seeds = SEEDS[:args.seeds]
    folds = FOLDS
    if args.quick:
        seeds, folds = seeds[:1], FOLDS[:1]

    ds = pd.read_pickle(args.dataset)
    ds['GAME_DATE'] = pd.to_datetime(ds['GAME_DATE'])

    out = {'stats': STATS, 'seeds': seeds, 'folds': [f['name'] for f in folds],
           'cal_fraction': CAL_FRACTION, 'runs': [], 'status': 'partial',
           'run_at': datetime.now().isoformat(timespec='seconds')}
    _os.makedirs('outputs', exist_ok=True)
    t_start = time.time()

    for fold in folds:
        train_all = ds[ds['SEASON_YEAR'].isin(fold['train'])].sort_values('GAME_DATE')
        test = ds[ds['SEASON_YEAR'] == fold['test']]
        cut = int(len(train_all) * (1 - CAL_FRACTION))
        fit_df, cal_df = train_all.iloc[:cut], train_all.iloc[cut:]
        # calibration truth uses played rows (predict-time lambda is conditional
        # on playing; DNP handling is a production concern, not a shape one)
        cal_played = cal_df[cal_df['MIN'] >= 4]
        test_played = test[test['MIN'] >= 4]
        print(f'[{fold["name"]}] fit={len(fit_df)} cal={len(cal_played)} '
              f'test={len(test_played)}', flush=True)

        for seed in seeds:
            ppm.SEED = seed
            t0 = time.time()
            model = TwoStageXGB().fit(fit_df)
            cal_preds = model.predict(cal_played)
            test_preds = model.predict(test_played)
            rec = {'fold': fold['name'], 'seed': seed, 'stats': {}}
            for s in STATS:
                lam_cal = cal_preds[f'pred_{s}'].to_numpy(dtype=float)
                y_cal = cal_played[s].to_numpy(dtype=float)
                iso0 = IsotonicRegression(increasing=False, out_of_bounds='clip')
                iso0.fit(lam_cal, (y_cal == 0).astype(float))
                iso2 = IsotonicRegression(increasing=True, out_of_bounds='clip')
                iso2.fit(lam_cal, (y_cal >= 2).astype(float))

                lam_t = test_preds[f'pred_{s}'].to_numpy(dtype=float)
                y_t = test_played[s].to_numpy(dtype=float)
                pois = poisson_probs(lam_t)
                iso = iso_probs(lam_t, iso0, iso2)
                tab_p = bin_table(lam_t, y_t, pois)
                tab_i = bin_table(lam_t, y_t, iso)
                rec['stats'][s] = {
                    'poisson_bins': tab_p, 'isotonic_bins': tab_i,
                    'poisson_p2plus_gap': headline(tab_p),
                    'isotonic_p2plus_gap': headline(tab_i),
                    'poisson_brier3': brier3(pois, y_t),
                    'isotonic_brier3': brier3(iso, y_t),
                }
            out['runs'].append(rec)
            print(f'  seed={seed} {time.time()-t0:.1f}s '
                  + ' '.join(f'{s}: gap {rec["stats"][s]["poisson_p2plus_gap"]:.4f}'
                             f'->{rec["stats"][s]["isotonic_p2plus_gap"]:.4f}'
                             for s in STATS), flush=True)
            with open(args.out + '.tmp', 'w') as f:
                json.dump(out, f, indent=1, default=str)
            _os.replace(args.out + '.tmp', args.out)

    # gate evaluation: per (fold, stat), majority of seeds must show iso < poisson
    verdict = {'per_fold_stat': {}, 'keep': True}
    for fold in [f['name'] for f in folds]:
        for s in STATS:
            recs = [r['stats'][s] for r in out['runs'] if r['fold'] == fold]
            gap_wins = sum(1 for r in recs
                           if r['isotonic_p2plus_gap'] is not None
                           and r['poisson_p2plus_gap'] is not None
                           and r['isotonic_p2plus_gap'] < r['poisson_p2plus_gap'])
            brier_ok = sum(1 for r in recs
                           if r['isotonic_brier3'] <= r['poisson_brier3'] + 1e-9)
            ok = gap_wins >= max(2, len(recs) // 2 + 1) if len(recs) > 1 else gap_wins == 1
            ok = ok and brier_ok == len(recs)
            verdict['per_fold_stat'][f'{fold}|{s}'] = {
                'seeds_gap_better': gap_wins, 'seeds_brier_ok': brier_ok,
                'n_seeds': len(recs), 'pass': bool(ok)}
            if not ok:
                verdict['keep'] = False
    out['verdict'] = verdict
    out['mae_delta_note'] = 'point predictions untouched by construction (maps are display-probability only)'
    out['status'] = 'complete'
    out['elapsed_min'] = round((time.time() - t_start) / 60.0, 1)
    with open(args.out + '.tmp', 'w') as f:
        json.dump(out, f, indent=1, default=str)
    _os.replace(args.out + '.tmp', args.out)
    print(f'Done in {out["elapsed_min"]} min -> {args.out}; '
          f'KEEP={verdict["keep"]}', flush=True)


if __name__ == '__main__':
    main()
