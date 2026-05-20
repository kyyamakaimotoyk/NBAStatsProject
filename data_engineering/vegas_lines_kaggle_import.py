"""
Kaggle NBA betting dataset importer.

Loads `outputs/nba_2008-2025.csv` (manually downloaded by user from
https://www.kaggle.com/datasets/cviaxmiwnptr/nba-betting-data-october-2007-to-june-2024)
and inserts the rows into the `vegas_lines` MySQL table with source='kaggle_sbr'.

This is the **historical baseline** half of E5. ESPN fetcher (vegas_lines_espn.py)
covers current/future dates with DraftKings lines; the two coexist in the same table
keyed by (game_date, home_team_abbrev, away_team_abbrev, source, line_type) so they
never collide.

E5 design note: Vegas line is a **supplementary baseline for comparison**, NOT a model
feature. The dashboard's Game Predictions tab will overlay it on the margin histogram;
the Model Performance tab will compare model_margin vs vegas_spread vs actual_margin.

Schema:
  vegas_lines.home_spread: negative = home favored (matches our model's predicted_margin
                            convention where positive = home favored). I.e., a Vegas
                            home_spread of -7.5 means "Vegas thinks home wins by 7.5";
                            our model predicting +7.5 would agree.

Usage:
    python data_engineering/vegas_lines_kaggle_import.py             # 2022-01-01+ (default window)
    python data_engineering/vegas_lines_kaggle_import.py --all       # entire CSV
    python data_engineering/vegas_lines_kaggle_import.py --csv path/to/other.csv
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
import pandas as pd
from sqlalchemy import text

from core.db import get_engine


# ============================================================================
# SCHEMA
# ============================================================================

ENSURE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS vegas_lines (
    id INT AUTO_INCREMENT PRIMARY KEY,
    game_date DATE NOT NULL,
    home_team_id BIGINT NULL,
    away_team_id BIGINT NULL,
    home_team_abbrev VARCHAR(10) NOT NULL,
    away_team_abbrev VARCHAR(10) NOT NULL,
    game_id BIGINT NULL COMMENT 'Resolved against game_list.GAME_ID if a match exists',
    source VARCHAR(50) NOT NULL COMMENT 'kaggle_sbr | espn_draftkings | espn_consensus | ...',
    bookmaker VARCHAR(50) NULL COMMENT 'Pinnacle/SBR consensus, Draft Kings, etc.',
    line_type VARCHAR(20) NOT NULL DEFAULT 'pregame' COMMENT 'pregame | closing | opening',
    home_spread FLOAT NULL COMMENT 'Negative = home favored (matches predicted_margin convention)',
    total FLOAT NULL,
    home_moneyline INT NULL,
    away_moneyline INT NULL,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes TEXT NULL,
    INDEX idx_game_date (game_date),
    INDEX idx_teams (home_team_id, away_team_id),
    INDEX idx_source (source),
    UNIQUE KEY unique_line (game_date, home_team_abbrev, away_team_abbrev, source, line_type)
)
"""


# ============================================================================
# TEAM CODE MAPPING (Kaggle CSV uses non-standard codes)
# ============================================================================
# Kaggle dataset uses these abbreviations — map to our project's standard
# 3-letter convention used in nba_teams.abbreviation.
KAGGLE_TO_STANDARD_ABBREV = {
    'atl': 'ATL', 'bkn': 'BKN', 'bos': 'BOS', 'cha': 'CHA', 'chi': 'CHI',
    'cle': 'CLE', 'dal': 'DAL', 'den': 'DEN', 'det': 'DET', 'gs': 'GSW',
    'hou': 'HOU', 'ind': 'IND', 'lac': 'LAC', 'lal': 'LAL', 'mem': 'MEM',
    'mia': 'MIA', 'mil': 'MIL', 'min': 'MIN', 'no': 'NOP', 'ny': 'NYK',
    'okc': 'OKC', 'orl': 'ORL', 'phi': 'PHI', 'phx': 'PHX', 'por': 'POR',
    'sa': 'SAS', 'sac': 'SAC', 'tor': 'TOR', 'utah': 'UTA', 'wsh': 'WAS',
}


def build_team_id_resolver(engine) -> dict:
    """Return {abbreviation: team_id} from nba_teams."""
    with engine.connect() as c:
        rows = c.execute(text("SELECT id, abbreviation FROM nba_teams")).fetchall()
    return {r[1]: r[0] for r in rows}


def build_game_id_resolver(engine, start_date: str, end_date: str) -> dict:
    """Return {(game_date, home_team_id, away_team_id): GAME_ID} for fast join-back.

    Uses game_list. A "home" team for a game is one whose MATCHUP contains 'vs.';
    'away' uses '@'. We collapse the two-rows-per-game representation here.
    """
    with engine.connect() as c:
        rows = c.execute(text("""
            SELECT GAME_ID, GAME_DATE, TEAM_ID, MATCHUP
            FROM game_list
            WHERE GAME_DATE >= :start AND GAME_DATE <= :end
        """), {'start': start_date, 'end': end_date}).fetchall()

    # Build (game_id -> {'home': tid, 'away': tid, 'date': d})
    games = {}
    for game_id, game_date, team_id, matchup in rows:
        if game_id not in games:
            games[game_id] = {'date': game_date.date() if hasattr(game_date, 'date') else game_date}
        if matchup and 'vs.' in str(matchup):
            games[game_id]['home'] = int(team_id)
        elif matchup and '@' in str(matchup):
            games[game_id]['away'] = int(team_id)

    resolver = {}
    for gid, g in games.items():
        if 'home' in g and 'away' in g:
            resolver[(g['date'], g['home'], g['away'])] = gid
    return resolver


# ============================================================================
# IMPORT
# ============================================================================

def import_kaggle_csv(engine, csv_path: str, start_date: str = '2022-01-01',
                     end_date: str = '2030-12-31', source_label: str = 'kaggle_sbr',
                     bookmaker: str = 'Pinnacle/SBR consensus'):
    print(f'[setup] Ensuring vegas_lines table...')
    with engine.connect() as c:
        c.execute(text(ENSURE_TABLE_SQL))
        c.commit()

    print(f'[load] Reading {csv_path}...')
    df = pd.read_csv(csv_path)
    df['date'] = pd.to_datetime(df['date'])
    in_window = df[(df['date'] >= start_date) & (df['date'] <= end_date)].copy()
    print(f'  {len(in_window):,} rows in window {start_date}..{end_date} (of {len(df):,} total)')

    print(f'[resolve] Building team_id + game_id lookups...')
    team_resolver = build_team_id_resolver(engine)
    game_resolver = build_game_id_resolver(engine, start_date, end_date)
    print(f'  {len(team_resolver)} teams in nba_teams; {len(game_resolver)} (date,home,away) tuples in game_list window')

    # Transform CSV rows into our schema
    rows_to_insert = []
    n_team_unresolved = 0
    n_game_unresolved = 0
    n_spread_missing = 0

    for _, row in in_window.iterrows():
        kg_home = str(row['home']).strip().lower()
        kg_away = str(row['away']).strip().lower()

        std_home = KAGGLE_TO_STANDARD_ABBREV.get(kg_home)
        std_away = KAGGLE_TO_STANDARD_ABBREV.get(kg_away)
        if not std_home or not std_away:
            # Unknown team code — skip with note
            continue

        home_id = team_resolver.get(std_home)
        away_id = team_resolver.get(std_away)
        if home_id is None or away_id is None:
            n_team_unresolved += 1

        game_date = row['date'].date()
        game_id = game_resolver.get((game_date, home_id, away_id)) if (home_id and away_id) else None
        if game_id is None:
            n_game_unresolved += 1

        spread_mag = row.get('spread')
        whos_fav = str(row.get('whos_favored', '')).strip().lower()
        if pd.isna(spread_mag):
            n_spread_missing += 1
            home_spread = None
        else:
            # Kaggle: spread is magnitude, whos_favored tells side.
            # Our convention: home_spread negative = home favored.
            if whos_fav == 'home':
                home_spread = -float(spread_mag)
            elif whos_fav == 'away':
                home_spread = float(spread_mag)
            else:
                home_spread = None  # pickem or unknown

        total = row.get('total')
        total = float(total) if pd.notna(total) else None
        mlh = row.get('moneyline_home')
        mlh = int(mlh) if pd.notna(mlh) else None
        mla = row.get('moneyline_away')
        mla = int(mla) if pd.notna(mla) else None

        rows_to_insert.append({
            'game_date': game_date,
            'home_team_id': home_id,
            'away_team_id': away_id,
            'home_team_abbrev': std_home,
            'away_team_abbrev': std_away,
            'game_id': game_id,
            'source': source_label,
            'bookmaker': bookmaker,
            'line_type': 'pregame',
            'home_spread': home_spread,
            'total': total,
            'home_moneyline': mlh,
            'away_moneyline': mla,
            'notes': None,
        })

    print(f'[transform] {len(rows_to_insert):,} rows prepared')
    print(f'  Team unresolved: {n_team_unresolved}, Game unresolved: {n_game_unresolved}, '
          f'Spread missing: {n_spread_missing}')

    if not rows_to_insert:
        print('Nothing to insert.')
        return

    insert_sql = text("""
        INSERT IGNORE INTO vegas_lines (
            game_date, home_team_id, away_team_id, home_team_abbrev, away_team_abbrev,
            game_id, source, bookmaker, line_type, home_spread, total,
            home_moneyline, away_moneyline, notes
        ) VALUES (
            :game_date, :home_team_id, :away_team_id, :home_team_abbrev, :away_team_abbrev,
            :game_id, :source, :bookmaker, :line_type, :home_spread, :total,
            :home_moneyline, :away_moneyline, :notes
        )
    """)
    with engine.connect() as c:
        result = c.execute(insert_sql, rows_to_insert)
        c.commit()
        inserted = result.rowcount

    print(f'[insert] {inserted:,} new rows inserted (of {len(rows_to_insert):,} prepared; '
          f'duplicates skipped via INSERT IGNORE)')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--csv', default='outputs/nba_2008-2025.csv',
                   help='Path to the Kaggle CSV (default: outputs/nba_2008-2025.csv)')
    p.add_argument('--start-date', dest='start_date', default='2022-01-01')
    p.add_argument('--end-date', dest='end_date', default='2030-12-31')
    p.add_argument('--all', action='store_true',
                   help='Ignore start/end date filters — import every row in the CSV')
    args = p.parse_args()

    eng = get_engine()
    start = '1900-01-01' if args.all else args.start_date
    end = '2030-12-31' if args.all else args.end_date
    import_kaggle_csv(eng, args.csv, start, end)


if __name__ == '__main__':
    main()
