"""Train/serve parity check: does the serving path reproduce the features table?

For each date, rebuild that date's games through build_serving_features (games
as placeholders, only earlier data visible) and compare every model column with
the same games' rows in a stored features-table version. Read-only.

    python scripts/check_serving_parity.py --version 20260703T072718Z \
        --dates 2025-11-05 2026-01-15 2026-03-02

Exit code 1 if any model column is missing from the serving rows or differs by
more than the tolerance on any game. tests/test_serving_parity.py runs the same
check (skipped when no database is reachable).

ELO is checked against a fresh full compute_elo() pass over the current game_list
(what the weekly compute_elo.py step writes), not against the stored snapshot:
ELO is path-dependent, so any game_list correction after the snapshot was built
legitimately moves every later rating (found 2026-11-13: local table computed
2026-05-19, up to 26 Elo points off today's game_list).
"""
from __future__ import annotations

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
from core.features import select_features, load_pruned_columns
from core.features_io import load_features
from data_engineering.feature_engineering import (
    build_serving_features, scheduled_games_from_game_list,
)

ABS_TOL = 1e-6
REL_TOL = 1e-6
ELO_COLS = {'HOME_ELO': 'home_elo', 'AWAY_ELO': 'away_elo',
            'ELO_DIFF': 'elo_diff', 'ELO_P_HOME': 'elo_p_home'}


def fresh_elo_reference(engine) -> pd.DataFrame:
    """Table-shaped ELO for every game_list game, computed now (training's source)."""
    from data_engineering.compute_elo import (
        load_games, collapse_to_one_row_per_game, compute_elo)
    ref = pd.DataFrame(compute_elo(collapse_to_one_row_per_game(load_games(engine))))
    ref = ref.rename(columns={v: k for k, v in ELO_COLS.items()}).rename(columns={'game_id': 'GAME_ID'})
    return ref[['GAME_ID'] + list(ELO_COLS)]


def compare(serving: pd.DataFrame, table: pd.DataFrame, cols: list) -> pd.DataFrame:
    """Per-column mismatch summary over games present in both frames."""
    s = serving.copy()
    t = table.copy()
    s['GAME_ID'] = s['GAME_ID'].astype('int64')
    t['GAME_ID'] = t['GAME_ID'].astype('int64')
    both = s.merge(t, on='GAME_ID', suffixes=('_srv', '_tbl'))
    out = []
    for c in cols:
        if f'{c}_srv' not in both:
            out.append({'feature': c, 'status': 'MISSING_IN_SERVING', 'n_diff': len(both)})
            continue
        a = pd.to_numeric(both[f'{c}_srv'], errors='coerce').to_numpy(float)
        b = pd.to_numeric(both[f'{c}_tbl'], errors='coerce').to_numpy(float)
        same = np.isclose(a, b, atol=ABS_TOL, rtol=REL_TOL) | (np.isnan(a) & np.isnan(b))
        n = int((~same).sum())
        out.append({'feature': c, 'status': 'OK' if n == 0 else 'DIFF', 'n_diff': n,
                    'max_abs_diff': float(np.nanmax(np.abs(a - b))) if n else 0.0,
                    'example_srv': float(a[~same][0]) if n else None,
                    'example_tbl': float(b[~same][0]) if n else None})
    return pd.DataFrame(out), len(both)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--version', required=True)
    ap.add_argument('--dates', nargs='+', required=True)
    ap.add_argument('--all-features', action='store_true',
                    help='check every select_features column, not just the pruned production set')
    ap.add_argument('--out', default='outputs/serving_parity.json')
    args = ap.parse_args()

    engine = get_engine()
    table = load_features(engine, version=args.version)
    table['GAME_DATE'] = pd.to_datetime(table['GAME_DATE'])
    cols = (select_features(table.columns) if args.all_features
            else select_features(table.columns, keep_only=load_pruned_columns()))

    elo_ref = fresh_elo_reference(engine)
    elo_ref['GAME_ID'] = elo_ref['GAME_ID'].astype('int64')

    report, failed = {}, False
    for d in args.dates:
        sched = scheduled_games_from_game_list(engine, d)
        srv = build_serving_features(engine, d, sched)
        tbl = table[table['GAME_DATE'] == pd.Timestamp(d)].copy()
        tbl['GAME_ID'] = tbl['GAME_ID'].astype('int64')
        tbl = tbl.drop(columns=[c for c in ELO_COLS if c in tbl]).merge(elo_ref, on='GAME_ID', how='left')
        res, n = compare(srv, tbl, cols)
        bad = res[res['status'] != 'OK']
        failed |= len(bad) > 0 or n == 0
        print(f'\n=== {d}: {n} games compared, {len(cols)} columns, '
              f'{len(bad)} columns differ or missing ===')
        if len(bad):
            print(bad.sort_values('n_diff', ascending=False).to_string(index=False))
        report[d] = {'n_games': n, 'n_cols': len(cols), 'bad': bad.to_dict('records')}

    _os.makedirs('outputs', exist_ok=True)
    with open(args.out, 'w') as f:
        json.dump(report, f, indent=2, default=float)
    print(f'\n{"FAIL" if failed else "PASS"} -> {args.out}')
    raise SystemExit(1 if failed else 0)


if __name__ == '__main__':
    main()
