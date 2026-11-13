"""Database-free check of the property serving relies on (E28).

build_serving_features predicts tonight's games by appending them as placeholder
rows (no result, no box score) and running the TRAINING feature steps. That is
only correct if no step reads a row's own result/stats or any later row. This
check proves it on synthetic data: for every cut date, the features of that
date's games must be identical whether the games are computed as played games
(full history, later games present) or as placeholders (stats blanked, later
games removed).

Runs in CI before the pipeline image is pushed (.github/workflows/pipeline.yml)
and locally via tests/test_serving_parity.py. Exit code 1 on any mismatch.

    python scripts/check_serving_invariants.py
"""
from __future__ import annotations

import sys as _sys
import os as _os
_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _PROJECT_ROOT)

import contextlib
import io

import numpy as np
import pandas as pd

from data_engineering.feature_engineering import compute_team_game_features

STATS = ['PTS', 'PLUS_MINUS', 'FG_PCT', 'offensiveRating', 'pace', 'PIE']
ID_COLS = {'GAME_ID', 'GAME_DATE', 'TEAM_ID', 'TEAM_ABBREVIATION', 'MATCHUP', 'WL', 'WIN', 'IS_HOME'}


def synthetic_season(seed: int = 7, n_teams: int = 6, n_days: int = 120) -> pd.DataFrame:
    """Random schedule with back-to-backs, road trips and a long mid-season gap."""
    rng = np.random.default_rng(seed)
    rows, gid = [], 1000
    day = pd.Timestamp('2025-10-21')
    for i in range(n_days):
        d = day + pd.Timedelta(days=i + (40 if i > 70 else 0))   # gap > REST_DAYS cap
        teams = rng.permutation(n_teams)
        for h, a in zip(teams[0::2], teams[1::2]):
            if rng.random() < 0.35:
                continue
            gid += 1
            margin = int(rng.normal(3, 12)) or 1
            for team, is_home, m in ((h, 1, margin), (a, 0, -margin)):
                opp = a if is_home else h
                rows.append({
                    'GAME_ID': gid, 'GAME_DATE': d, 'TEAM_ID': 100 + int(team),
                    'TEAM_ABBREVIATION': f'T{team}',
                    'MATCHUP': f'T{team} vs. T{opp}' if is_home else f'T{team} @ T{opp}',
                    'WL': 'W' if m > 0 else 'L', 'WIN': int(m > 0), 'IS_HOME': is_home,
                    'PTS': 110 + m / 2 + rng.normal(0, 5), 'PLUS_MINUS': m,
                    'FG_PCT': rng.uniform(.4, .55), 'offensiveRating': rng.normal(112, 6),
                    'pace': rng.normal(99, 3), 'PIE': rng.uniform(.4, .6)})
    return pd.DataFrame(rows)


def features(df: pd.DataFrame) -> pd.DataFrame:
    with contextlib.redirect_stdout(io.StringIO()):
        return compute_team_game_features(None, df.copy(), include_player_features=False)


def check(seed: int = 7) -> list:
    full = synthetic_season(seed)
    full_feat = features(full).set_index(['GAME_ID', 'TEAM_ID'])
    feat_cols = [c for c in full_feat.columns if c not in ID_COLS and c not in STATS]
    problems = []
    dates = sorted(full['GAME_DATE'].unique())
    for d in dates[1::7]:                                   # every 7th game date
        before = full[full['GAME_DATE'] < d]
        tonight = full[full['GAME_DATE'] == d].copy()
        tonight[STATS] = np.nan
        tonight['WL'] = None
        tonight['WIN'] = 0
        served = features(pd.concat([before, tonight], ignore_index=True))
        served = served[served['GAME_DATE'] == d].set_index(['GAME_ID', 'TEAM_ID'])
        ref = full_feat.loc[served.index]
        for c in feat_cols:
            a = pd.to_numeric(served[c], errors='coerce').to_numpy(float)
            b = pd.to_numeric(ref[c], errors='coerce').to_numpy(float)
            ok = np.isclose(a, b, atol=1e-9) | (np.isnan(a) & np.isnan(b))
            if not ok.all():
                problems.append(f'{pd.Timestamp(d).date()} {c}: placeholder {a[~ok][0]} '
                                f'vs played {b[~ok][0]}')
    if not feat_cols:
        problems.append('no feature columns produced')
    return problems, len(feat_cols), len(dates[1::7])


def main():
    problems, n_cols, n_dates = check()
    if problems:
        print(f'SERVING INVARIANT FAILED ({len(problems)} mismatches):')
        for p in problems[:20]:
            print('  ' + p)
        raise SystemExit(1)
    print(f'serving invariant OK: {n_cols} feature columns identical as placeholder vs played '
          f'on {n_dates} cut dates')


if __name__ == '__main__':
    main()
