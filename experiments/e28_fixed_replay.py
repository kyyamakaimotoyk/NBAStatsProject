"""
E28 step 2 — replay games through the FIXED serving path and compare with what
production logged (old live builder) for the same games.

For each date: build_game_features (training pipeline, games as placeholders),
score with the local RF/XGB bundles, and report margin spread, mean, win-prob
spread, classifier-vs-margin split rate and (for graded games) accuracy. The
logged production rows come from outputs/e27_live_rows.json (public API, frozen).

Offline comparison only: nothing is logged to model_predictions. The local
bundles (rf/xgb *_current, 20260716) are not the production 20261102 bundles, so
absolute accuracy is indicative; the spread/split comparison is the point.

    python experiments/e28_fixed_replay.py --start 2026-10-21 --end 2026-10-27
"""
from __future__ import annotations

try:
    import torch  # noqa: F401  (Windows import order)
except Exception:
    pass

import sys as _sys
import os as _os
_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _PROJECT_ROOT)
if _os.getcwd() != _PROJECT_ROOT:
    _os.chdir(_PROJECT_ROOT)

import argparse
import json

import numpy as np
import pandas as pd

from core.db import get_engine
from data_engineering.feature_engineering import scheduled_games_from_game_list
from modeling.predict_games import load_model_bundle
from modeling.serving_features import build_game_features, check_features


def score(bundle, rows: pd.DataFrame):
    imputer, scaler = bundle['scaler_tuple']
    X = scaler.transform(imputer.transform(rows.reindex(columns=bundle['feature_names'])))
    clf = getattr(bundle['classifier'], '_base', bundle['classifier'])
    reg = getattr(bundle['regressor'], '_base', bundle['regressor'])
    return clf.predict_proba(X)[:, 1], reg.predict(X)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--start', required=True)
    ap.add_argument('--end', required=True)
    ap.add_argument('--out', default='outputs/e28_fixed_replay.json')
    args = ap.parse_args()

    engine = get_engine()
    bundles = {k: load_model_bundle(k) for k in ('rf', 'xgb')}
    recs = []
    for d in pd.date_range(args.start, args.end).strftime('%Y-%m-%d'):
        sched = scheduled_games_from_game_list(engine, d)
        sched = sched[sched['GAME_ID'].astype(str).str[0] == '2']      # regular season
        if sched.empty:
            continue
        feats = build_game_features(engine, d, sched)
        rows = pd.DataFrame(list(feats.values()))
        for k, b in bundles.items():
            for _, r in rows.iterrows():
                check_features(r.to_dict(), b['feature_names'], k, f"{r['GAME_ID']} {d}")
            p, m = score(b, rows)
            for gid, pi, mi in zip(rows['GAME_ID'], p, m):
                recs.append({'game_id': int(gid), 'date': d, 'model': k, 'p_home': float(pi),
                             'margin': float(mi)})
    new = pd.DataFrame(recs)

    logged = pd.DataFrame(json.load(open('outputs/e27_live_rows.json'))['rows'])
    logged['gid'] = logged['game_id'].astype(int)
    logged = logged[logged['gid'].isin(new['game_id'])]
    res = {}
    for k in bundles:
        n = new[new['model'] == k].merge(
            logged[logged['model_type'] == k][['gid', 'predicted_margin', 'home_win_probability',
                                               'predicted_winner', 'home_team', 'actual_winner']],
            left_on='game_id', right_on='gid', how='left')
        y = (n['actual_winner'] == n['home_team']).astype(float).where(n['actual_winner'].notna())
        graded = y.notna()
        out = {
            'n_games': int(len(n)), 'n_graded': int(graded.sum()),
            'fixed_margin_sd': float(n['margin'].std()), 'fixed_margin_mean': float(n['margin'].mean()),
            'logged_margin_sd': float(n['predicted_margin'].std()),
            'logged_margin_mean': float(n['predicted_margin'].mean()),
            'fixed_prob_sd': float(n['p_home'].std()),
            'logged_prob_sd': float(n['home_win_probability'].std()),
            'fixed_split_rate': float(np.mean((n['p_home'] >= .5) != (n['margin'] > 0))),
            'logged_split_rate': float(np.mean((n['predicted_winner'] == n['home_team'])
                                               != (n['predicted_margin'] > 0))),
            'home_rate': float(y[graded].mean()),
            'fixed_pick_acc': float(((n['p_home'] >= .5) == (y == 1))[graded].mean()),
            'logged_pick_acc': float(((n['predicted_winner'] == n['home_team']) == (y == 1))[graded].mean()),
            'fixed_margin_sign_acc': float(((n['margin'] > 0) == (y == 1))[graded].mean()),
            'logged_margin_sign_acc': float(((n['predicted_margin'] > 0) == (y == 1))[graded].mean()),
        }
        res[k] = out
        print(f"\n{k.upper()}  n={out['n_games']} (graded {out['n_graded']}, home rate {out['home_rate']:.3f})")
        print(f"  margin SD   logged {out['logged_margin_sd']:.2f} (mean {out['logged_margin_mean']:+.2f})  ->  "
              f"fixed {out['fixed_margin_sd']:.2f} (mean {out['fixed_margin_mean']:+.2f})")
        print(f"  prob SD     logged {out['logged_prob_sd']:.3f}  ->  fixed {out['fixed_prob_sd']:.3f}")
        print(f"  split rate  logged {out['logged_split_rate']:.1%}  ->  fixed {out['fixed_split_rate']:.1%}")
        print(f"  pick acc    logged {out['logged_pick_acc']:.3f}  ->  fixed {out['fixed_pick_acc']:.3f}   "
              f"margin-sign acc logged {out['logged_margin_sign_acc']:.3f} -> fixed {out['fixed_margin_sign_acc']:.3f}")
    with open(args.out, 'w') as f:
        json.dump({'start': args.start, 'end': args.end, 'models': res}, f, indent=2)
    print(f'\nSaved -> {args.out}')


if __name__ == '__main__':
    main()
