"""
Playoff series-context features (Track A of the playoff-improvement plan).

The model currently treats every playoff game as an isolated regular-season game.
But Game 5 of a 2-2 series is nothing like Game 1 — there are series standings,
elimination pressure, home-court advantage from seeding, and in-series adjustments.
Vegas implicitly prices all of this; our model is blind to it. These features add
that awareness.

All features are computed PER GAME from only the PRIOR games in the same series
(no leakage), from the current game's HOME-team perspective (matching how
create_matchup_features defines home/away via the 'vs.' MATCHUP token):

  SERIES_GAME_NO          1..7 — which game of the series this is
  HOME_SERIES_WINS        games the current home team has already won in the series
  AWAY_SERIES_WINS        games the current away team has already won
  SERIES_WIN_DIFF         HOME_SERIES_WINS - AWAY_SERIES_WINS (signed, home perspective)
  HOME_FACES_ELIM         1 if the home team is one loss from elimination (away has 3 wins)
  AWAY_FACES_ELIM         1 if the away team is one loss from elimination (home has 3 wins)
  HOME_HAS_HCA            1 if the home team has series home-court advantage
                          (hosted game 1 of the series), else 0
  SERIES_PRIOR_MARGIN_HOME  avg point margin (home-team perspective) over prior
                          series games — captures who's been controlling the series

Regular-season and play-in games get all-zero values (no series). For the model to
*learn* from these, training must include prior playoffs — the production pipeline
already trains on all games; the Track-A evaluation harness trains on all games
before each test season's playoffs.

Series identified by (SEASON_ID, unordered team pair). Only true playoffs
(SEASON_ID prefix '4') form series; play-in ('5') games are single-elimination and
are left at zero.

Storage: table `playoff_series_context` keyed by game_id, joined by GAME_ID into the
feature CSV at build time (mirrors compute_elo / team_elo_pregame).

Usage:
    python data_engineering/series_context.py            # rebuild the table
"""
from __future__ import annotations

import sys as _sys, os as _os
_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _PROJECT_ROOT)
if _os.getcwd() != _PROJECT_ROOT:
    _os.chdir(_PROJECT_ROOT)

from collections import defaultdict
import pandas as pd
from sqlalchemy import text
from core.db import get_engine


ENSURE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS playoff_series_context (
    game_id BIGINT PRIMARY KEY,
    game_date DATE,
    season_id VARCHAR(12),
    series_game_no INT,
    home_series_wins INT,
    away_series_wins INT,
    series_win_diff INT,
    home_faces_elim TINYINT,
    away_faces_elim TINYINT,
    home_has_hca TINYINT,
    series_prior_margin_home FLOAT,
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""


def load_playoff_games(engine) -> pd.DataFrame:
    """One row per playoff game: home/away team + points + date + season."""
    df = pd.read_sql(text("""
        SELECT GAME_ID, SEASON_ID, GAME_DATE, TEAM_ID, MATCHUP, PTS
        FROM game_list
        WHERE LEFT(CAST(SEASON_ID AS CHAR), 1) = '4'
    """), engine)
    df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])
    home = df[df['MATCHUP'].str.contains('vs.', regex=False, na=False)].copy()
    away = df[df['MATCHUP'].str.contains('@', regex=False, na=False)].copy()
    home = home.sort_values('PTS', ascending=False).drop_duplicates('GAME_ID', keep='first')
    away = away.sort_values('PTS', ascending=False).drop_duplicates('GAME_ID', keep='first')
    home = home.rename(columns={'TEAM_ID': 'home_id', 'PTS': 'home_pts'})
    away = away.rename(columns={'TEAM_ID': 'away_id', 'PTS': 'away_pts'})
    g = home[['GAME_ID', 'SEASON_ID', 'GAME_DATE', 'home_id', 'home_pts']].merge(
        away[['GAME_ID', 'away_id', 'away_pts']], on='GAME_ID', how='inner')
    return g.sort_values(['GAME_DATE', 'GAME_ID']).reset_index(drop=True)


def compute_series_context(games: pd.DataFrame) -> pd.DataFrame:
    """Walk each series chronologically, emit per-game pre-game series state."""
    # Group by (season, unordered pair)
    def pair_key(r):
        a, b = int(r['home_id']), int(r['away_id'])
        return (r['SEASON_ID'], min(a, b), max(a, b))

    games = games.copy()
    games['pair'] = games.apply(pair_key, axis=1)
    out = []
    for _, series in games.groupby('pair'):
        series = series.sort_values(['GAME_DATE', 'GAME_ID'])
        wins = defaultdict(int)              # team_id -> wins so far in series
        margins_by_team = defaultdict(list)  # team_id -> list of its margins so far
        hca_team = int(series.iloc[0]['home_id'])  # game-1 host = series HCA
        for k, (_, gm) in enumerate(series.iterrows(), start=1):
            h, a = int(gm['home_id']), int(gm['away_id'])
            home_w, away_w = wins[h], wins[a]
            prior = margins_by_team[h]
            out.append({
                'game_id': int(gm['GAME_ID']),
                'game_date': gm['GAME_DATE'].date(),
                'season_id': str(gm['SEASON_ID']),
                'series_game_no': k,
                'home_series_wins': home_w,
                'away_series_wins': away_w,
                'series_win_diff': home_w - away_w,
                'home_faces_elim': 1 if away_w == 3 else 0,
                'away_faces_elim': 1 if home_w == 3 else 0,
                'home_has_hca': 1 if h == hca_team else 0,
                'series_prior_margin_home': float(sum(prior) / len(prior)) if prior else 0.0,
            })
            # advance state with this game's result
            hp, ap = gm['home_pts'], gm['away_pts']
            if pd.notna(hp) and pd.notna(ap):
                margin = float(hp) - float(ap)
                margins_by_team[h].append(margin)
                margins_by_team[a].append(-margin)
                if margin > 0:
                    wins[h] += 1
                elif margin < 0:
                    wins[a] += 1
    return pd.DataFrame(out)


def write_table(engine, rows: pd.DataFrame) -> int:
    with engine.connect() as c:
        c.execute(text(ENSURE_TABLE_SQL)); c.commit()
        c.execute(text("DELETE FROM playoff_series_context")); c.commit()
        if len(rows) == 0:
            return 0
        c.execute(text("""
            INSERT INTO playoff_series_context
              (game_id, game_date, season_id, series_game_no, home_series_wins, away_series_wins,
               series_win_diff, home_faces_elim, away_faces_elim, home_has_hca, series_prior_margin_home)
            VALUES (:game_id, :game_date, :season_id, :series_game_no, :home_series_wins, :away_series_wins,
               :series_win_diff, :home_faces_elim, :away_faces_elim, :home_has_hca, :series_prior_margin_home)
        """), rows.to_dict('records'))
        c.commit()
        return len(rows)


def main():
    eng = get_engine()
    print('[load] playoff games from game_list...')
    g = load_playoff_games(eng)
    print(f'  {len(g)} playoff games')
    print('[compute] series context...')
    ctx = compute_series_context(g)
    print(f'  {len(ctx)} rows; series up to game {ctx["series_game_no"].max()}; '
          f'elim games: {int((ctx.home_faces_elim | ctx.away_faces_elim).sum())}')
    n = write_table(eng, ctx)
    print(f'[insert] {n} rows into playoff_series_context.')


if __name__ == '__main__':
    main()
