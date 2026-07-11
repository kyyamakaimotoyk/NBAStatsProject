"""P3 — Do RAPTOR-class impact metrics improve player counting-stat projections?

Context: the P1/P2 player model's only "impact" inputs are PIE_L10 and USG_PCT_L10
(box-score shares). RAPM-family all-in-one metrics (RAPTOR / LEBRON / DARKO / EPM)
claim to measure per-possession impact better. Real RAPTOR died with FiveThirtyEight
(data ends 2021-22) and LEBRON has no free export, so this experiment uses
**Neil Paine's Estimated RAPTOR** (0.89 corr with real RAPTOR; seasons through
2024-25; CC-BY-style public GitHub CSV, cached at outputs/nba_estimated_RAPTOR.csv).

Leakage stance: each player-game row gets his **previous season's** rating
(PREV_ERAPTOR_*). No same-season aggregate is ever joined, so nothing about the
season being predicted leaks in. Rookies/unmatched rows are NaN (XGBoost native).

Protocol per `feedback: noise-aware eval`: 3 seeds x the 3 P2 walk-forward folds,
two arms per (fold, seed) — baseline (current feature set) vs +eRAPTOR — paired
t-test on per-row |error| between arms. A stat "keeps" the feature only if
delta MAE < 0 with p < 0.05 in all folds for a majority of seeds.

Run: python experiments/p3_impact_metrics.py
Outputs: outputs/p3_impact_metrics.json (incremental), docs/p3_impact_metrics_report.md
"""
import json
import os
import re
import sys
import time
import unicodedata

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import modeling.player_projection_models as ppm  # noqa: E402
from data_engineering.player_dataset import OUT_PATH as DATASET_PATH  # noqa: E402
from modeling.player_projection_models import TARGETS, TwoStageXGB  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ERAPTOR_CSV = os.path.join(ROOT, 'outputs', 'nba_estimated_RAPTOR.csv')
JSON_OUT = os.path.join(ROOT, 'outputs', 'p3_impact_metrics.json')
REPORT_OUT = os.path.join(ROOT, 'docs', 'p3_impact_metrics_report.md')

SEEDS = [42, 7, 202]
FOLDS = [
    {'name': 'F1_train2223_test2324', 'train': ['22022'], 'test': '22023'},
    {'name': 'F2_train2224_test2425', 'train': ['22022', '22023'], 'test': '22024'},
    {'name': 'F3_train2225_test2526', 'train': ['22022', '22023', '22024'], 'test': '22025'},
]
NEW_COLS = ['PREV_ERAPTOR_OFF', 'PREV_ERAPTOR_DEF', 'PREV_ERAPTOR_TOT',
            'PREV_ERAPTOR_WAR82']

# Make the new columns visible to feature_columns() — arm control happens by
# including/dropping the columns from the DataFrame itself.
for _c in NEW_COLS:
    if _c not in ppm._EXPLICIT_FEATURES:
        ppm._EXPLICIT_FEATURES.append(_c)

_SUFFIX_RE = re.compile(r'\s+(jr|sr|ii|iii|iv|v)\.?$')


def norm_name(name):
    """Accent/punctuation/suffix-insensitive join key."""
    s = unicodedata.normalize('NFKD', str(name))
    s = ''.join(ch for ch in s if not unicodedata.combining(ch)).lower()
    s = re.sub(r"[.'\-]", '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return _SUFFIX_RE.sub('', s)


def load_eraptor():
    """Minutes-weighted per-(player, season) Estimated RAPTOR, RS rows only."""
    er = pd.read_csv(ERAPTOR_CSV, encoding='latin-1')
    er = er[er['Type'] == 'RS'].copy()
    er['name_key'] = er['Player'].map(norm_name)
    er['MP'] = er['MP'].fillna(0)

    def agg(g):
        w = g['MP'].to_numpy(dtype=float)
        if w.sum() <= 0:
            w = np.ones(len(g))
        return pd.Series({
            'PREV_ERAPTOR_OFF': float(np.average(g['eRO'], weights=w)),
            'PREV_ERAPTOR_DEF': float(np.average(g['eRD'], weights=w)),
            'PREV_ERAPTOR_TOT': float(np.average(g['eRT'], weights=w)),
            'PREV_ERAPTOR_WAR82': float(np.average(g['WAR/82'], weights=w)),
        })

    out = er.groupby(['name_key', 'Year']).apply(agg).reset_index()
    print(f'eRAPTOR: {len(out):,} player-seasons, years '
          f'{int(out["Year"].min())}-{int(out["Year"].max())}')
    return out


def attach_prev_season_eraptor(ds, er):
    """SEASON_YEAR '22022' = the 2022-23 season, whose prior season ENDS in 2022 —
    which is exactly Paine's Year convention, so prior year = int(sy[1:])."""
    ds = ds.copy()
    ds['name_key'] = ds['PLAYER_NAME'].map(norm_name)
    ds['prior_year'] = ds['SEASON_YEAR'].str[1:].astype(int)
    merged = ds.merge(er, how='left',
                      left_on=['name_key', 'prior_year'],
                      right_on=['name_key', 'Year'])
    merged = merged.drop(columns=['Year'])
    match = merged.groupby('SEASON_YEAR')['PREV_ERAPTOR_TOT'].apply(
        lambda s: float(s.notna().mean()))
    print('match rate by season:', {k: round(v, 3) for k, v in match.items()})
    return merged, {k: round(v, 4) for k, v in match.items()}


def run_arm(train, test, seed, drop_new):
    """Fit TwoStageXGB with the given seed; return per-stat prediction frame."""
    ppm.SEED = seed
    if drop_new:
        train = train.drop(columns=[c for c in NEW_COLS if c in train.columns])
        test = test.drop(columns=[c for c in NEW_COLS if c in test.columns])
    model = TwoStageXGB().fit(train)
    return model.predict(test), model


def main():
    ds = pd.read_pickle(DATASET_PATH)
    print(f'dataset: {len(ds):,} rows')
    er = load_eraptor()
    ds, match_rates = attach_prev_season_eraptor(ds, er)

    payload = {'protocol': {'seeds': SEEDS, 'folds': [f['name'] for f in FOLDS],
                            'new_features': NEW_COLS,
                            'join': 'prev-season Estimated RAPTOR by normalized name',
                            'match_rate_by_season': match_rates},
               'runs': []}

    for fold in FOLDS:
        train = ds[ds['SEASON_YEAR'].isin(fold['train'])]
        test = ds[ds['SEASON_YEAR'] == fold['test']]
        for seed in SEEDS:
            t0 = time.time()
            pred_base, _ = run_arm(train, test, seed, drop_new=True)
            pred_aug, model_aug = run_arm(train, test, seed, drop_new=False)
            run = {'fold': fold['name'], 'seed': seed,
                   'n_train': len(train), 'n_test': len(test), 'stats': {}}
            for s in TARGETS:
                mask = (pred_base[f'pred_{s}'].notna() & pred_aug[f'pred_{s}'].notna()
                        & test[s].notna())
                a = np.abs(pred_aug.loc[mask, f'pred_{s}'] - test.loc[mask, s])
                b = np.abs(pred_base.loc[mask, f'pred_{s}'] - test.loc[mask, s])
                t, p = stats.ttest_rel(a, b)
                run['stats'][s] = {
                    'mae_base': round(float(b.mean()), 4),
                    'mae_aug': round(float(a.mean()), 4),
                    'delta_mae': round(float((a - b).mean()), 4),
                    't': round(float(t), 3), 'p': float(p), 'n': int(mask.sum())}
            # where do the new features rank by gain in the augmented minutes/PTS models?
            run['new_feature_gain_rank'] = {}
            for name, mdl in {'MIN': model_aug.min_model,
                              'PTS': model_aug.rate_models['PTS']}.items():
                imp = pd.Series(mdl.feature_importances_, index=model_aug.features)
                ranks = imp.rank(ascending=False, method='min')
                run['new_feature_gain_rank'][name] = {
                    c: {'rank': int(ranks[c]), 'gain': round(float(imp[c]), 5)}
                    for c in NEW_COLS}
            payload['runs'].append(run)
            with open(JSON_OUT, 'w') as f:
                json.dump(payload, f, indent=1)
            print(f"{fold['name']} seed={seed} done in {time.time()-t0:.0f}s "
                  f"(PTS dMAE {run['stats']['PTS']['delta_mae']:+.4f} "
                  f"p={run['stats']['PTS']['p']:.2e})")

    # ---- verdict per stat: negative + significant in all folds, majority of seeds ----
    verdicts = {}
    for s in TARGETS:
        per_seed = []
        for seed in SEEDS:
            runs = [r for r in payload['runs'] if r['seed'] == seed]
            ok = all(r['stats'][s]['delta_mae'] < 0 and r['stats'][s]['p'] < 0.05
                     for r in runs)
            per_seed.append(ok)
        deltas = [r['stats'][s]['delta_mae'] for r in payload['runs']]
        verdicts[s] = {
            'mean_delta_mae': round(float(np.mean(deltas)), 4),
            'seeds_passing_all_folds': int(sum(per_seed)),
            'keep': bool(sum(per_seed) >= 2)}
    payload['verdicts'] = verdicts
    with open(JSON_OUT, 'w') as f:
        json.dump(payload, f, indent=1)

    lines = ['# P3 — Prior-season Estimated RAPTOR as a player-projection feature', '',
             'Arms: baseline (current P2 features, incl. PIE_L10/USG_PCT_L10) vs '
             '+PREV_ERAPTOR_{OFF,DEF,TOT,WAR82} (previous-season Estimated RAPTOR, '
             'minutes-weighted across stints, matched by normalized name — '
             'point-in-time safe by construction).', '',
             f"Match rate by season: {payload['protocol']['match_rate_by_season']}", '',
             '| Stat | mean ΔMAE (aug−base) | seeds passing all folds (of 3) | keep? |',
             '|---|---|---|---|']
    for s in TARGETS:
        v = verdicts[s]
        lines.append(f"| {s} | {v['mean_delta_mae']:+.4f} | "
                     f"{v['seeds_passing_all_folds']} | "
                     f"{'**YES**' if v['keep'] else 'no'} |")
    lines += ['', 'Negative ΔMAE = the eRAPTOR features improved that stat. Gate: '
              'delta < 0 AND p < 0.05 in all three folds, for ≥2 of 3 seeds '
              '(per the noise-aware eval policy).', '',
              'Per-run detail in `outputs/p3_impact_metrics.json` (per fold/seed: '
              'MAE both arms, paired-t, and the gain-rank of each new feature in the '
              'augmented MIN and PTS models).']
    with open(REPORT_OUT, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f'wrote {JSON_OUT}\nwrote {REPORT_OUT}')
    print('verdicts:', json.dumps(verdicts, indent=1))


if __name__ == '__main__':
    main()
