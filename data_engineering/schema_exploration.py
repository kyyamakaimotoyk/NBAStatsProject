"""
Schema Exploration Script
=========================
Queries the NBA database to display all tables, their schemas, and row counts.
"""

# Project-root bootstrap so cross-folder imports (core.db, ...) work regardless of CWD.
import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

import sqlalchemy as sql
from sqlalchemy import inspect, text
import pandas as pd


def create_engine():
    """Create database connection engine. Reads MySQL config from environment via db.get_engine()."""
    from core.db import get_engine
    return get_engine()


def list_all_tables(engine):
    """List all tables in the database."""
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    print('=== ALL TABLES ===')
    for t in sorted(tables):
        print(t)
    print(f'\nTotal: {len(tables)} tables')

    return tables


def get_table_row_counts(engine):
    """Get row counts for all tables."""
    inspector = inspect(engine)
    tables = sorted(inspector.get_table_names())

    print('=== TABLE ROW COUNTS ===')
    with engine.connect() as conn:
        for t in tables:
            result = conn.execute(text(f'SELECT COUNT(*) FROM {t}')).scalar()
            print(f'{t}: {result} rows')


def get_all_table_schemas(engine):
    """Get column schemas for all tables."""
    inspector = inspect(engine)
    tables = sorted(inspector.get_table_names())

    for table in tables:
        print(f'\n=== {table.upper()} ===')
        cols = inspector.get_columns(table)
        for c in cols:
            print(f"  {c['name']}: {c['type']}")


def get_date_range_and_sample(engine):
    """Get date range and sample game data."""
    with engine.connect() as conn:
        # Date range
        dates = pd.read_sql(text('SELECT MIN(GAME_DATE) as earliest, MAX(GAME_DATE) as latest FROM game_list'), conn)
        print('=== DATE RANGE ===')
        print(f"Earliest: {dates['earliest'].iloc[0]}")
        print(f"Latest: {dates['latest'].iloc[0]}")

        # Unique games count
        games = pd.read_sql(text('SELECT COUNT(DISTINCT GAME_ID) as cnt FROM game_list'), conn)
        print(f"Unique games: {games['cnt'].iloc[0]}")

        # Sample game
        print('\n=== SAMPLE GAME (most recent) ===')
        sample = pd.read_sql(text('''
            SELECT GAME_ID, GAME_DATE, TEAM_ABBREVIATION, MATCHUP, WL, PTS, PLUS_MINUS
            FROM game_list
            ORDER BY GAME_DATE DESC
            LIMIT 4
        '''), conn)
        print(sample.to_string(index=False))


if __name__ == '__main__':
    engine = create_engine()

    print('\n' + '='*60)
    print('NBA DATABASE SCHEMA EXPLORATION')
    print('='*60 + '\n')

    # 1. List all tables
    list_all_tables(engine)

    print('\n' + '-'*60 + '\n')

    # 2. Get row counts
    get_table_row_counts(engine)

    print('\n' + '-'*60 + '\n')

    # 3. Get all table schemas
    get_all_table_schemas(engine)

    print('\n' + '-'*60 + '\n')

    # 4. Get date range and sample data
    get_date_range_and_sample(engine)

    # Cleanup
    engine.dispose()
    print('\n✓ Done')
