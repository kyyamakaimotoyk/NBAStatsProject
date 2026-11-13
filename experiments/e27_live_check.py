"""
E27 live leg — Phi(margin / sigma) on the production models' logged 2026-27
predictions.

The backtest (e27_margin_prob.py) retrains on the frozen snapshot, which holds
no 2026-27 games. This leg uses what production actually logged before tip-off:
  fit   sigma per model (probit MLE) on graded 2025-26 walk-forward rows
  test  graded 2026-27 rows: Phi(predicted_margin / sigma) vs the logged
        home_win_probability (site display) and the logged pick.
No retraining. Source is the public read-only API; the fetched rows are frozen
to outputs/e27_live_rows.json so the numbers are reproducible
(--from-file reuses them).

Pre-registered in experiments/specs/e27_margin_prob.json ("live_leg").
"""
from __future__ import annotations

import sys as _sys
import os as _os
_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)

from experiments.e27_margin_prob import (  # noqa: E402  (harness header first)
    fit_sigma_mle, metrics, compare, gate,
)

import argparse  # noqa: E402
import json  # noqa: E402
import urllib.request  # noqa: E402
from datetime import datetime  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import norm  # noqa: E402

API = 'https://api.hoopmodel.com/api/performance/results?days={days}'
ROWS_PATH = 'outputs/e27_live_rows.json'
FIT = ('2025-10-01', '2026-07-01')
TEST = ('2026-10-01', '2027-07-01')


def fetch(days: int) -> list:
    req = urllib.request.Request(API.format(days=days),
                                 headers={'User-Agent': 'hoopmodel-e27-research'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)['results']


def frame(rows: list) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df = df[df['game_id'].str[2] == '2']                 # regular season only
    df = df[df['actual_winner'].notna() & df['actual_margin'].notna()]
    df['y'] = (df['actual_winner'] == df['home_team']).astype(int)
    df['pick_home'] = (df['predicted_winner'] == df['home_team']).astype(int)
    df['game_date'] = pd.to_datetime(df['game_date'])
    return df


def split_rate(d: pd.DataFrame) -> float:
    return float(np.mean(d['pick_home'] != (d['predicted_margin'] > 0).astype(int)))


def run(args):
    if args.from_file:
        with open(ROWS_PATH) as f:
            payload = json.load(f)
    else:
        payload = {'fetched_at': datetime.now().isoformat(timespec='seconds'),
                   'source': API.format(days=args.days), 'rows': fetch(args.days)}
        _os.makedirs('outputs', exist_ok=True)
        with open(ROWS_PATH, 'w') as f:
            json.dump(payload, f)
    df = frame(payload['rows'])
    print(f"rows fetched {payload['fetched_at']}: {len(df)} graded regular-season rows")

    out = {'experiment_id': 'E27-live', 'fetched_at': payload['fetched_at'],
           'n_bootstrap': args.n_bootstrap, 'models': {}}
    for mt in ('rf', 'xgb', 'nn'):
        d = df[df['model_type'] == mt]
        fit = d[(d['game_date'] >= FIT[0]) & (d['game_date'] < FIT[1])]
        test = d[(d['game_date'] >= TEST[0]) & (d['game_date'] < TEST[1])].sort_values('game_date')
        sigma = fit_sigma_mle(fit['predicted_margin'].values, fit['y'].values)
        y = test['y'].values
        p_logged = test['home_win_probability'].values.astype(float)
        p_pick = test['pick_home'].values.astype(float)           # logged pick as 0/1
        p_phi = norm.cdf(test['predicted_margin'].values / sigma)
        # pick comparison must use the LOGGED pick (raw classifier); the logged
        # probability is the display value (calibrated for XGB) and can sit on
        # the other side of 0.5.
        c = compare(y, p_phi, p_logged, p_pick, args.n_bootstrap)

        early = fit[fit['game_date'].dt.month.isin((10, 11))]
        rest = fit[~fit['game_date'].dt.month.isin((10, 11))]
        weeks = (test.assign(week=test['game_date'].dt.to_period('W-SUN').astype(str))
                 .groupby('week').apply(lambda g: {'n': len(g), 'split': split_rate(g)},
                                        include_groups=False).to_dict())
        res = {'sigma_mle_2025_26': sigma, 'n_fit': len(fit), 'n_test': len(test),
               'metrics_test': {'logged': metrics(y, p_logged), 'phi': metrics(y, p_phi)},
               'logged_pick_acc': float(np.mean(p_pick == y)),
               'comparison_phi_vs_logged': c, 'gate': gate(c),
               'split_rate': {'2025_26_oct_nov': split_rate(early), '2025_26_dec_on': split_rate(rest),
                              '2026_27': split_rate(test), '2026_27_by_week': weeks}}
        out['models'][mt] = res

        print(f'\n=== {mt.upper()}  sigma={sigma:.1f} (fit n={len(fit)})  test n={len(test)} ===')
        print(f'  pick acc logged {res["logged_pick_acc"]:.3f} -> margin sign {res["metrics_test"]["phi"]["acc"]:.3f}  '
              f'd={c["acc"]["mean"]:+.3f} [{c["acc"]["ci_lo"]:+.3f}, {c["acc"]["ci_hi"]:+.3f}] McNemar p={c["mcnemar_p"]:.3f}')
        print(f'  logloss logged {res["metrics_test"]["logged"]["logloss"]:.4f} -> phi {res["metrics_test"]["phi"]["logloss"]:.4f}  '
              f'd={c["logloss"]["mean"]:+.4f} [{c["logloss"]["ci_lo"]:+.4f}, {c["logloss"]["ci_hi"]:+.4f}] p={c["logloss"]["p"]:.3f}')
        print(f'  brier d={c["brier"]["mean"]:+.4f} p={c["brier"]["p"]:.3f} | AUC d={c["auc"]["mean"]:+.4f} '
              f'p={c["auc"]["p"]:.3f} | ECE {c["ece_base"]:.3f} -> {c["ece_arm"]:.3f}')
        sr = res['split_rate']
        print(f'  split rate: 2025-26 Oct-Nov {sr["2025_26_oct_nov"]:.1%}, Dec+ {sr["2025_26_dec_on"]:.1%}, '
              f'2026-27 {sr["2026_27"]:.1%}')
        print('  2026-27 by week: ' + ', '.join(f'{k[:10]} {v["split"]:.0%} (n={v["n"]})'
                                              for k, v in weeks.items()))
        print(f'  gate {res["gate"]}')

    with open(args.out, 'w') as f:
        json.dump(out, f, indent=2, default=float)
    print(f'\nSaved -> {args.out}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=420)
    ap.add_argument('--from-file', action='store_true')
    ap.add_argument('--n-bootstrap', type=int, default=2000)
    ap.add_argument('--out', default='outputs/e27_live.json')
    run(ap.parse_args())


if __name__ == '__main__':
    main()
