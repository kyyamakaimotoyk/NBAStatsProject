"""
Compute 538-style ELO ratings for every NBA team at every point in history.

Approach
--------
Single pass over `game_list` ordered by GAME_DATE. For each completed game:
  1. Read pre-game home_elo + away_elo from in-memory dict (defaults to 1500 for new teams)
  2. Record (home_elo, away_elo, elo_diff, elo_p_home) at the PRE-GAME moment — that's
     the point-in-time value any predictive model is allowed to see for this game
  3. Apply 538 update formula using actual margin to advance both teams' ratings
  4. At season rollover (when a team's previous season changes), regress 25% toward 1505

Formula (Silver 2015, FiveThirtyEight)
--------------------------------------
  E_home = 1 / (1 + 10 ** (-(home_elo + HCA - away_elo) / 400))         # expected win prob
  mov_mult = ((|winning_margin| + 3) ** 0.8) / (7.5 + 0.006 * winner_elo_diff)
  delta = K * mov_mult * (actual_home_win - E_home)
  home_elo += delta;  away_elo -= delta
  # End of season: new_elo = 0.75 * end_elo + 0.25 * 1505

Constants K=20, HCA=100, mean=1505, carryover=0.75 are 538's published defaults.

Storage
-------
Table `team_elo_pregame (game_id, game_date, home_team_id, away_team_id,
home_elo, away_elo, elo_diff, elo_p_home, computed_at)` — joined by game_id into
nba_ml_features.csv at feature-build time. 4 model features: HOME_ELO, AWAY_ELO,
DIFF_ELO, ELO_P_HOME.

Usage
-----
    python data_engineering/compute_elo.py                 # rebuild from earliest game in game_list
    python data_engineering/compute_elo.py --since 1996-01-01
"""
from __future__ import annotations

# Project-root bootstrap
import sys as _sys
import os as _os
_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _PROJECT_ROOT)
if _os.getcwd() != _PROJECT_ROOT:
    _os.chdir(_PROJECT_ROOT)

import argparse
from collections import defaultdict
from datetime import datetime

import pandas as pd
from sqlalchemy import text

from core.db import get_engine


# ============================================================================
# CONSTANTS (538 defaults)
# ============================================================================
K_BASE = 20.0
HCA = 100.0
MEAN_ELO = 1505.0
CARRYOVER = 0.75


def nba_season_of(game_date) -> int:
    """Return the SEASON-ENDING year for a given game_date. NBA seasons span Oct-June.
    Game on 2024-11-15 → season 2025 (the '24-25 season ends in 2025).
    Game on 2025-04-10 → season 2025."""
    if hasattr(game_date, 'year'):
        y, m = game_date.year, game_date.month
    else:
        d = pd.to_datetime(game_date)
        y, m = d.year, d.month
    return y if m < 8 else y + 1


# ============================================================================
# SCHEMA
# ============================================================================

ENSURE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS team_elo_pregame (
    id INT AUTO_INCREMENT PRIMARY KEY,
    game_id BIGINT NOT NULL,
    game_date DATE NOT NULL,
    home_team_id BIGINT NOT NULL,
    away_team_id BIGINT NOT NULL,
    home_elo FLOAT NOT NULL,
    away_elo FLOAT NOT NULL,
    elo_diff FLOAT NOT NULL COMMENT '(home + HCA) - away — positive = home favored by Elo',
    elo_p_home FLOAT NOT NULL COMMENT 'P(home wins) per Elo logistic',
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_game (game_id),
    INDEX idx_game_date (game_date),
    INDEX idx_home_team (home_team_id),
    INDEX idx_away_team (away_team_id)
)
"""


# ============================================================================
# CORE COMPUTATION
# ============================================================================

def load_games(engine, since: str = None) -> pd.DataFrame:
    """Return one row per (game_id, team) with side flag (home/away), date, points."""
    where = f"WHERE GAME_DATE >= '{since}'" if since else ''
    with engine.connect() as c:
        df = pd.read_sql(text(f"""
            SELECT GAME_ID, GAME_DATE, TEAM_ID, MATCHUP, PTS, WL
            FROM game_list
            {where}
            ORDER BY GAME_DATE, GAME_ID
        """), c)
    df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])
    return df


def collapse_to_one_row_per_game(df_team_rows: pd.DataFrame) -> pd.DataFrame:
    """Two-rows-per-game (team perspective) -> one-row-per-game with home_/away_ columns.

    `game_list` has a small number of GAME_IDs with 3 rows instead of 2 (data quality issue
    in the ingest, mostly 2005 preseason). For those, we dedupe by keeping the row with
    the highest PTS within each (GAME_ID, side) group — i.e., the row that looks like
    real game data vs the orphaned dupe.
    """
    home = df_team_rows[df_team_rows['MATCHUP'].str.contains('vs.', regex=False, na=False)].copy()
    away = df_team_rows[df_team_rows['MATCHUP'].str.contains('@', regex=False, na=False)].copy()
    home = home.sort_values('PTS', ascending=False).drop_duplicates(subset=['GAME_ID'], keep='first')
    away = away.sort_values('PTS', ascending=False).drop_duplicates(subset=['GAME_ID'], keep='first')

    home = home.rename(columns={'TEAM_ID': 'home_team_id', 'PTS': 'home_pts', 'WL': 'home_wl'})
    away = away.rename(columns={'TEAM_ID': 'away_team_id', 'PTS': 'away_pts', 'WL': 'away_wl'})

    games = home.merge(
        away[['GAME_ID', 'away_team_id', 'away_pts', 'away_wl']],
        on='GAME_ID', how='inner'
    )
    games = games[['GAME_ID', 'GAME_DATE', 'home_team_id', 'away_team_id',
                   'home_pts', 'away_pts', 'home_wl']]
    games = games.sort_values(['GAME_DATE', 'GAME_ID']).reset_index(drop=True)
    return games


def compute_elo(games: pd.DataFrame) -> list:
    """Single pass — yields pre-game ELO for each game and updates dict.

    Returns list of dicts ready for INSERT into team_elo_pregame.
    """
    elo = defaultdict(lambda: MEAN_ELO)
    last_season = {}
    out = []

    for _, g in games.iterrows():
        gid = int(g['GAME_ID'])
        gd = g['GAME_DATE']
        h = int(g['home_team_id'])
        a = int(g['away_team_id'])
        season = nba_season_of(gd)

        # Season-rollover carryover (regress toward mean)
        for tid in (h, a):
            prev_season = last_season.get(tid)
            if prev_season is not None and season != prev_season:
                elo[tid] = CARRYOVER * elo[tid] + (1.0 - CARRYOVER) * MEAN_ELO
            last_season[tid] = season

        # PRE-GAME state — record this for the model
        h_elo = elo[h]
        a_elo = elo[a]
        elo_diff = (h_elo + HCA) - a_elo
        e_home = 1.0 / (1.0 + 10 ** (-elo_diff / 400.0))

        out.append({
            'game_id': gid,
            'game_date': gd.date() if hasattr(gd, 'date') else gd,
            'home_team_id': h,
            'away_team_id': a,
            'home_elo': float(h_elo),
            'away_elo': float(a_elo),
            'elo_diff': float(elo_diff),
            'elo_p_home': float(e_home),
        })

        # Skip update if game has no result (scheduled / postponed)
        hp = g.get('home_pts')
        ap = g.get('away_pts')
        wl = g.get('home_wl')
        if pd.isna(hp) or pd.isna(ap) or wl not in ('W', 'L'):
            continue

        margin = float(hp) - float(ap)
        home_won = (wl == 'W')

        # MOV multiplier (winner perspective)
        winner_diff = elo_diff if home_won else -elo_diff
        mov = ((abs(margin) + 3.0) ** 0.8) / (7.5 + 0.006 * winner_diff)
        actual_home_win = 1.0 if home_won else 0.0
        delta = K_BASE * mov * (actual_home_win - e_home)

        elo[h] = h_elo + delta
        elo[a] = a_elo - delta

    return out


def write_to_db(engine, rows: list):
    """Bulk INSERT IGNORE — re-runnable: existing rows for the same game_id stay put."""
    if not rows:
        return 0
    with engine.connect() as c:
        c.execute(text(ENSURE_TABLE_SQL))
        c.commit()
        # Clear out any existing pre-game ELO rows so we get a clean rebuild
        # (re-running compute_elo always overwrites — that's the intended UX)
        c.execute(text("DELETE FROM team_elo_pregame"))
        c.commit()
        result = c.execute(text("""
            INSERT INTO team_elo_pregame
                (game_id, game_date, home_team_id, away_team_id, home_elo, away_elo, elo_diff, elo_p_home)
            VALUES (:game_id, :game_date, :home_team_id, :away_team_id,
                    :home_elo, :away_elo, :elo_diff, :elo_p_home)
        """), rows)
        c.commit()
        return result.rowcount


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--since', default=None,
                   help='Earliest game_date to consider (YYYY-MM-DD). Default: all of game_list.')
    args = p.parse_args()

    eng = get_engine()
    print(f'[load] Loading games from game_list (since={args.since or "<beginning>"})...')
    team_rows = load_games(eng, args.since)
    print(f'  {len(team_rows):,} team-game rows')

    print(f'[collapse] One row per game...')
    games = collapse_to_one_row_per_game(team_rows)
    print(f'  {len(games):,} games')

    print(f'[compute] Running ELO update over chronological games...')
    elo_rows = compute_elo(games)
    print(f'  {len(elo_rows):,} pre-game ELO rows computed')

    # Quick sanity stats
    elo_diffs = [r['elo_diff'] for r in elo_rows]
    p_homes = [r['elo_p_home'] for r in elo_rows]
    print(f'  elo_diff: mean={sum(elo_diffs)/len(elo_diffs):.1f}, '
          f'min={min(elo_diffs):.1f}, max={max(elo_diffs):.1f}')
    print(f'  elo_p_home: mean={sum(p_homes)/len(p_homes):.3f} (should be >0.5 = home advantage)')

    # Pure-ELO classification accuracy as a baseline check (only on games with known result)
    completed = [r for r, g in zip(elo_rows, games.itertuples()) if g.home_wl in ('W', 'L')]
    completed_actuals = [g.home_wl == 'W' for r, g in zip(elo_rows, games.itertuples()) if g.home_wl in ('W', 'L')]
    if completed:
        elo_preds = [r['elo_p_home'] > 0.5 for r in completed]
        elo_acc = sum(p == a for p, a in zip(elo_preds, completed_actuals)) / len(completed)
        print(f'  [BASELINE] pure-ELO accuracy on all completed games: {elo_acc:.4f}')

    print(f'[insert] Writing to team_elo_pregame...')
    inserted = write_to_db(eng, elo_rows)
    print(f'  {inserted:,} rows in team_elo_pregame.')


if __name__ == '__main__':
    main()
