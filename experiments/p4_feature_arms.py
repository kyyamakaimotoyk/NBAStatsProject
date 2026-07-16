"""P4: build the parked Tier-2 candidate feature columns as add-columns files.

Each group from docs/player_projections_plan.md ("D2/E2/F2/H2 stay parked for
a later ablation round") becomes a parquet consumed by loop_player_ab.py's
``add_columns_file`` arms — the production dataset builder is untouched until
a group KEEPs (then its computation moves into player_dataset.py).

Groups:
  d2   schedule/fatigue: MIN_PREV_GAME, CUM_MIN_LAST3          (pickle math)
  e2   team environment: TEAM_ELO, OPP_ELO, TEAM_ELO_DIFF      (team_elo_pregame)
  f2a  opponent allowed counting stats: OPP_{REB,AST,STL,BLK,3PM}_ALLOWED_L10
  f2b  opponent matchup-defense FG%: OPP_{DFG,D3P,D2P}_PCT_L10 (boxscoredefensivev2_player)
  f2c  opponent hustle: OPP_DEFLECTIONS_L10, OPP_CONTESTED_SHOTS_L10
  h2   matchup interactions: X_3PA_MATCHUP, X_FTA_MATCHUP, X_REB_MATCHUP, X_PTS_PACE

Leakage safety: every rolling value is shift(1) per *defending* team (or per
player for d2) — nothing from the current game; warm-up season 2021-22 is
included in the SQL so L10 windows are warm at the 2022-23 start. Team-keyed
groups are pre-mirrored to the opponent side, so the harness always joins on
the player's own (GAME_ID, TEAM_ID).

Usage: python experiments/p4_feature_arms.py --group all
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

import numpy as np
import pandas as pd

from core.db import get_engine
from data_engineering.player_dataset import ALL_SEASONS, OUT_PATH as DATASET_PATH


def _season_filter() -> str:
    """SEASON_ID IN-list covering warm-up + train season-years, all game types."""
    from data_engineering.player_dataset import _expand_season_ids
    ids = _expand_season_ids(ALL_SEASONS)
    return ','.join(f"'{s}'" for s in ids)


def _roll10(g: pd.Series) -> pd.Series:
    return g.shift(1).rolling(10, min_periods=1).mean()


def _team_games(engine, extra_cols: str = '') -> pd.DataFrame:
    q = f"""
        SELECT GAME_ID, TEAM_ID, GAME_DATE{extra_cols}
        FROM game_list
        WHERE SEASON_ID IN ({_season_filter()})
    """
    df = pd.read_sql(q, engine)
    df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])
    return df.sort_values(['TEAM_ID', 'GAME_DATE'])


def _mirror_to_opponent(df: pd.DataFrame, value_cols: list) -> pd.DataFrame:
    """(GAME_ID, TEAM_ID, values) -> the OTHER team's values on my row."""
    right = df[['GAME_ID', 'TEAM_ID'] + value_cols].rename(
        columns={'TEAM_ID': 'OTHER_TEAM_ID'})
    merged = df[['GAME_ID', 'TEAM_ID']].merge(right, on='GAME_ID')
    merged = merged[merged['TEAM_ID'] != merged['OTHER_TEAM_ID']]
    return merged[['GAME_ID', 'TEAM_ID'] + value_cols]


# ----------------------------------------------------------------------------
# Groups
# ----------------------------------------------------------------------------

def build_d2(pickle_df: pd.DataFrame) -> pd.DataFrame:
    out = pickle_df[['GAME_ID', 'personId', 'GAME_DATE', 'MIN']].copy()
    out = out.sort_values(['personId', 'GAME_DATE'])
    g = out.groupby('personId')['MIN']
    out['MIN_PREV_GAME'] = g.shift(1)
    out['CUM_MIN_LAST3'] = g.transform(
        lambda s: s.shift(1).rolling(3, min_periods=1).sum())
    return out[['GAME_ID', 'personId', 'MIN_PREV_GAME', 'CUM_MIN_LAST3']]


def build_e2(engine) -> pd.DataFrame:
    elo = pd.read_sql(
        'SELECT game_id, home_team_id, away_team_id, home_elo, away_elo '
        'FROM team_elo_pregame', engine)
    home = pd.DataFrame({'GAME_ID': elo['game_id'], 'TEAM_ID': elo['home_team_id'],
                         'TEAM_ELO': elo['home_elo'], 'OPP_ELO': elo['away_elo']})
    away = pd.DataFrame({'GAME_ID': elo['game_id'], 'TEAM_ID': elo['away_team_id'],
                         'TEAM_ELO': elo['away_elo'], 'OPP_ELO': elo['home_elo']})
    out = pd.concat([home, away], ignore_index=True)
    out['TEAM_ELO_DIFF'] = out['TEAM_ELO'] - out['OPP_ELO']
    out['GAME_ID'] = out['GAME_ID'].astype(np.int64)
    return out


def build_f2a(engine) -> pd.DataFrame:
    tg = _team_games(engine, ', REB, AST, STL, BLK, FG3M')
    stats = ['REB', 'AST', 'STL', 'BLK', 'FG3M']
    # what each team ALLOWED in a game = the opponent's same-game stats
    allowed = _mirror_to_opponent(tg, stats).rename(
        columns={s: f'{s}_ALLOWED_RAW' for s in stats})
    tg = tg.merge(allowed, on=['GAME_ID', 'TEAM_ID'], how='left')
    tg = tg.sort_values(['TEAM_ID', 'GAME_DATE'])
    cols = []
    for s in stats:
        name = f"{'3PM' if s == 'FG3M' else s}_ALLOWED_L10_TMP"
        tg[name] = tg.groupby('TEAM_ID')[f'{s}_ALLOWED_RAW'].transform(_roll10)
        cols.append(name)
    # the player's row needs his OPPONENT's allowed-rolling values
    out = _mirror_to_opponent(tg, cols)
    out = out.rename(columns={c: 'OPP_' + c.replace('_TMP', '') for c in cols})
    return out


def build_f2b(engine) -> pd.DataFrame:
    q = f"""
        SELECT d.gameId AS GAME_ID, d.teamId AS TEAM_ID, g.GAME_DATE,
               SUM(d.matchupFieldGoalsMade) AS dfgm,
               SUM(d.matchupFieldGoalsAttempted) AS dfga,
               SUM(d.matchupThreePointersMade) AS d3pm,
               SUM(d.matchupThreePointersAttempted) AS d3pa
        FROM boxscoredefensivev2_player d
        JOIN game_list g ON g.GAME_ID = d.gameId AND g.TEAM_ID = d.teamId
        WHERE g.SEASON_ID IN ({_season_filter()})
        GROUP BY d.gameId, d.teamId, g.GAME_DATE
    """
    df = pd.read_sql(q, engine)
    df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])
    for num, den, name in (('dfgm', 'dfga', 'DFG_PCT'),
                           ('d3pm', 'd3pa', 'D3P_PCT')):
        df[name] = df[num].astype(float) / df[den].replace(0, np.nan).astype(float)
    df['D2P_PCT'] = ((df['dfgm'] - df['d3pm']).astype(float)
                     / (df['dfga'] - df['d3pa']).replace(0, np.nan).astype(float))
    df = df.sort_values(['TEAM_ID', 'GAME_DATE'])
    cols = []
    for pct in ('DFG_PCT', 'D3P_PCT', 'D2P_PCT'):
        name = f'{pct}_L10_TMP'
        df[name] = df.groupby('TEAM_ID')[pct].transform(_roll10)
        cols.append(name)
    out = _mirror_to_opponent(df, cols)
    out = out.rename(columns={c: 'OPP_' + c.replace('_TMP', '') for c in cols})
    out['GAME_ID'] = out['GAME_ID'].astype(np.int64)
    return out


def build_f2c(engine) -> pd.DataFrame:
    q = f"""
        SELECT h.gameId AS GAME_ID, h.teamId AS TEAM_ID, g.GAME_DATE,
               h.deflections, h.contestedShots
        FROM boxscorehustlev2_team h
        JOIN game_list g ON g.GAME_ID = h.gameId AND g.TEAM_ID = h.teamId
        WHERE g.SEASON_ID IN ({_season_filter()})
    """
    df = pd.read_sql(q, engine)
    df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])
    df = df.sort_values(['TEAM_ID', 'GAME_DATE'])
    df['DEFLECTIONS_L10_TMP'] = df.groupby('TEAM_ID')['deflections'].transform(_roll10)
    df['CONTESTED_SHOTS_L10_TMP'] = df.groupby('TEAM_ID')['contestedShots'].transform(_roll10)
    cols = ['DEFLECTIONS_L10_TMP', 'CONTESTED_SHOTS_L10_TMP']
    out = _mirror_to_opponent(df, cols)
    out = out.rename(columns={c: 'OPP_' + c.replace('_TMP', '') for c in cols})
    out['GAME_ID'] = out['GAME_ID'].astype(np.int64)
    return out


def build_h2(pickle_df: pd.DataFrame) -> pd.DataFrame:
    need = ['FG3A36_L10', 'OPP_3PA_ALLOWED_L10', 'FTA36_L10',
            'OPP_FT_RATE_ALLOWED_L10', 'REB36_L10', 'OPP_EFG_L10',
            'PTS36_L10', 'EXPECTED_POSS']
    missing = [c for c in need if c not in pickle_df.columns]
    if missing:
        raise RuntimeError(f'h2: pickle is missing source columns {missing}')
    out = pickle_df[['GAME_ID', 'personId'] + need].copy()
    out['X_3PA_MATCHUP'] = out['FG3A36_L10'] * out['OPP_3PA_ALLOWED_L10']
    out['X_FTA_MATCHUP'] = out['FTA36_L10'] * out['OPP_FT_RATE_ALLOWED_L10']
    out['X_REB_MATCHUP'] = out['REB36_L10'] * (1.0 - out['OPP_EFG_L10'])
    out['X_PTS_PACE'] = out['PTS36_L10'] * out['EXPECTED_POSS']
    return out[['GAME_ID', 'personId',
                'X_3PA_MATCHUP', 'X_FTA_MATCHUP', 'X_REB_MATCHUP', 'X_PTS_PACE']]


GROUPS = {
    'd2': ('pickle', build_d2), 'e2': ('sql', build_e2),
    'f2a': ('sql', build_f2a), 'f2b': ('sql', build_f2b),
    'f2c': ('sql', build_f2c), 'h2': ('pickle', build_h2),
}


def coverage(pickle_df: pd.DataFrame, cols: pd.DataFrame) -> float:
    keys = ['GAME_ID', 'personId'] if 'personId' in cols.columns else ['GAME_ID', 'TEAM_ID']
    value_col = [c for c in cols.columns if c not in keys][0]
    j = pickle_df[['GAME_ID', 'TEAM_ID', 'personId']].merge(cols, on=keys, how='left')
    return float(j[value_col].notna().mean())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--group', default='all',
                    choices=['all'] + sorted(GROUPS))
    ap.add_argument('--dataset', default=DATASET_PATH)
    args = ap.parse_args()

    pickle_df = pd.read_pickle(args.dataset)
    pickle_df['GAME_DATE'] = pd.to_datetime(pickle_df['GAME_DATE'])
    engine = get_engine()
    _os.makedirs('outputs', exist_ok=True)

    groups = sorted(GROUPS) if args.group == 'all' else [args.group]
    for g in groups:
        kind, fn = GROUPS[g]
        cols = fn(pickle_df) if kind == 'pickle' else fn(engine)
        path = f'outputs/p4_cols_{g}.parquet'
        cols.to_parquet(path, index=False)
        cov = coverage(pickle_df, cols)
        value_cols = [c for c in cols.columns
                      if c not in ('GAME_ID', 'personId', 'TEAM_ID')]
        print(f'{g}: {len(cols):,} rows, cols={value_cols}, '
              f'pickle-row coverage={cov:.3f} -> {path}', flush=True)


if __name__ == '__main__':
    main()
