"""
NBA Data Exploration Tutorial
==============================
This script teaches SQLAlchemy and Pythonic patterns while exploring your NBA database.

Learning objectives:
1. SQLAlchemy connection patterns (Engine, Connection, Session)
2. Reflection - inspecting existing database schemas
3. Pythonic syntax: list comprehensions, f-strings, walrus operator
4. Pandas integration with SQLAlchemy
"""

# Project-root bootstrap so cross-folder imports (core.db, ...) work regardless of CWD.
import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

import sqlalchemy as sql
from sqlalchemy import inspect, text
import pandas as pd

# ============================================================================
# SECTION 1: Database Connection Fundamentals
# ============================================================================

def create_connection():
    """
    SQLAlchemy uses a layered architecture:

    1. Engine - The starting point. Manages connection pool and dialect (MySQL, PostgreSQL, etc.)
    2. Connection - A single database connection from the pool
    3. Session - Higher-level ORM interface (we'll cover this later)

    Connection string format: 'dialect://user:password@host:port/database'
    """
    # MySQL config now lives in environment variables (see db.py / .env.example)
    from core.db import get_engine
    return get_engine()


def explore_schema(engine):
    """
    SQLAlchemy's Inspector allows us to reflect (discover) the database schema
    without writing SQL queries.

    This is useful when:
    - Working with existing databases you didn't create
    - Building dynamic queries based on table structure
    - Documentation and data discovery
    """
    # Inspector is the reflection API
    inspector = inspect(engine)

    # Get all table names
    tables = inspector.get_table_names()

    print(f"\n{'='*60}")
    print(f"DATABASE SCHEMA: {len(tables)} tables found")
    print(f"{'='*60}\n")

    # -------------------------------------------------------------------------
    # PYTHONIC PATTERN: List comprehension with conditional filtering
    # -------------------------------------------------------------------------
    # Traditional loop approach:
    # player_tables = []
    # for table in tables:
    #     if 'player' in table:
    #         player_tables.append(table)

    # Pythonic approach - list comprehension:
    player_tables = [t for t in tables if 'player' in t]
    team_tables = [t for t in tables if 'team' in t and 'player' not in t]
    other_tables = [t for t in tables if t not in player_tables and t not in team_tables]

    print("PLAYER-LEVEL TABLES:")
    for table in sorted(player_tables):
        print(f"  - {table}")

    print(f"\nTEAM-LEVEL TABLES:")
    for table in sorted(team_tables):
        print(f"  - {table}")

    print(f"\nOTHER TABLES:")
    for table in sorted(other_tables):
        print(f"  - {table}")

    return tables


def explore_table_structure(engine, table_name: str):
    """
    Inspect a single table's columns, types, and constraints.

    Learning: Type hints (table_name: str) make code self-documenting
    and enable IDE autocomplete.
    """
    inspector = inspect(engine)

    print(f"\n{'='*60}")
    print(f"TABLE STRUCTURE: {table_name}")
    print(f"{'='*60}\n")

    # Get columns
    columns = inspector.get_columns(table_name)

    # -------------------------------------------------------------------------
    # PYTHONIC PATTERN: Dictionary comprehension
    # -------------------------------------------------------------------------
    # Extract column names and types into a dict
    # Traditional:
    # column_types = {}
    # for col in columns:
    #     column_types[col['name']] = str(col['type'])

    # Pythonic:
    column_types = {col['name']: str(col['type']) for col in columns}

    print(f"Columns ({len(columns)}):")
    for name, dtype in column_types.items():
        print(f"  {name:<30} {dtype}")

    # Get primary keys
    pk = inspector.get_pk_constraint(table_name)
    if pk['constrained_columns']:
        print(f"\nPrimary Key: {pk['constrained_columns']}")

    # Get foreign keys
    fks = inspector.get_foreign_keys(table_name)
    if fks:
        print(f"\nForeign Keys:")
        for fk in fks:
            print(f"  {fk['constrained_columns']} -> {fk['referred_table']}.{fk['referred_columns']}")

    return column_types


def query_with_pandas(engine, query: str) -> pd.DataFrame:
    """
    Pandas + SQLAlchemy integration.

    pd.read_sql() is the easiest way to get SQL results into a DataFrame.
    It handles type conversion automatically.
    """
    # Using context manager ensures connection is properly closed
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)
    return df


def explore_data_overview(engine):
    """
    Get a high-level view of the data we have.

    Learning: Using raw SQL with SQLAlchemy's text() function
    """
    print(f"\n{'='*60}")
    print("DATA OVERVIEW")
    print(f"{'='*60}\n")

    # Count games
    games_df = query_with_pandas(engine, "SELECT COUNT(DISTINCT GAME_ID) as game_count FROM game_list")
    print(f"Total games in game_list: {games_df['game_count'].iloc[0]}")

    # Date range
    date_df = query_with_pandas(engine, """
        SELECT MIN(GAME_DATE) as earliest, MAX(GAME_DATE) as latest
        FROM game_list
    """)
    print(f"Date range: {date_df['earliest'].iloc[0]} to {date_df['latest'].iloc[0]}")

    # Teams
    teams_df = query_with_pandas(engine, "SELECT COUNT(*) as team_count FROM nba_teams")
    print(f"Teams in database: {teams_df['team_count'].iloc[0]}")

    # Players
    players_df = query_with_pandas(engine, "SELECT COUNT(*) as player_count FROM nba_players")
    print(f"Players in database: {players_df['player_count'].iloc[0]}")

    # Win/Loss distribution
    wl_df = query_with_pandas(engine, """
        SELECT WL, COUNT(*) as count
        FROM game_list
        GROUP BY WL
    """)
    print(f"\nWin/Loss distribution:")
    print(wl_df.to_string(index=False))


def explore_sample_game(engine):
    """
    Deep dive into a single game to understand the data structure.

    Learning: JOINs and multi-table queries
    """
    print(f"\n{'='*60}")
    print("SAMPLE GAME ANALYSIS")
    print(f"{'='*60}\n")

    # Get a recent game
    game_df = query_with_pandas(engine, """
        SELECT DISTINCT GAME_ID, GAME_DATE, MATCHUP
        FROM game_list
        ORDER BY GAME_DATE DESC
        LIMIT 1
    """)

    if game_df.empty:
        print("No games found in database")
        return

    game_id = game_df['GAME_ID'].iloc[0]
    print(f"Analyzing game: {game_df['MATCHUP'].iloc[0]} on {game_df['GAME_DATE'].iloc[0]}")
    print(f"Game ID: {game_id}\n")

    # Get traditional stats for this game
    # -------------------------------------------------------------------------
    # PYTHONIC PATTERN: Parameterized queries prevent SQL injection
    # -------------------------------------------------------------------------
    trad_df = query_with_pandas(engine, f"""
        SELECT
            t.personId,
            p.full_name,
            t.teamId,
            tm.abbreviation as team,
            t.minutes,
            t.points,
            t.reboundsTotal as rebounds,
            t.assists,
            t.steals,
            t.blocks,
            t.turnovers,
            t.plusMinusPoints as plus_minus
        FROM boxscoretraditionalv3_player t
        LEFT JOIN nba_players p ON t.personId = p.id
        LEFT JOIN nba_teams tm ON t.teamId = tm.id
        WHERE t.gameId = {game_id}
        ORDER BY t.points DESC
    """)

    if not trad_df.empty:
        print("Player Stats (Traditional):")
        print(trad_df.to_string(index=False))
    else:
        print("No traditional stats found for this game")

    return game_id


def explore_team_performance(engine):
    """
    Aggregate team performance - this is the data you'll use for ML!

    Learning: Complex aggregations and window functions
    """
    print(f"\n{'='*60}")
    print("TEAM PERFORMANCE SUMMARY")
    print(f"{'='*60}\n")

    # Get team records from game_list
    team_records = query_with_pandas(engine, """
        SELECT
            t.abbreviation,
            t.full_name,
            COUNT(*) as games_played,
            SUM(CASE WHEN g.WL = 'W' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN g.WL = 'L' THEN 1 ELSE 0 END) as losses,
            ROUND(AVG(g.PTS), 1) as avg_points,
            ROUND(AVG(g.PLUS_MINUS), 1) as avg_margin
        FROM game_list g
        JOIN nba_teams t ON g.TEAM_ID = t.id
        GROUP BY t.id, t.abbreviation, t.full_name
        ORDER BY wins DESC
    """)

    if not team_records.empty:
        # -------------------------------------------------------------------------
        # PYTHONIC PATTERN: Chained pandas operations
        # -------------------------------------------------------------------------
        # Calculate win percentage using pandas (could also do in SQL)
        team_records['win_pct'] = (team_records['wins'] / team_records['games_played']).round(3)

        print(team_records.to_string(index=False))
    else:
        print("No team performance data found")

    return team_records


# ============================================================================
# SECTION 2: Pythonic Patterns Practice
# ============================================================================

def pythonic_patterns_demo():
    """
    Demonstration of Pythonic patterns you'll use throughout this project.
    Run this to see examples with explanations.
    """
    print(f"\n{'='*60}")
    print("PYTHONIC PATTERNS DEMONSTRATION")
    print(f"{'='*60}\n")

    # -------------------------------------------------------------------------
    # 1. List Comprehension
    # -------------------------------------------------------------------------
    print("1. LIST COMPREHENSION")
    print("-" * 40)

    # Basic: [expression for item in iterable]
    squares = [x**2 for x in range(10)]
    print(f"   Squares: {squares}")

    # With condition: [expression for item in iterable if condition]
    even_squares = [x**2 for x in range(10) if x % 2 == 0]
    print(f"   Even squares: {even_squares}")

    # Nested: flatten a 2D list
    matrix = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
    flattened = [num for row in matrix for num in row]
    print(f"   Flattened matrix: {flattened}")

    # -------------------------------------------------------------------------
    # 2. Dictionary Comprehension
    # -------------------------------------------------------------------------
    print("\n2. DICTIONARY COMPREHENSION")
    print("-" * 40)

    # Basic: {key: value for item in iterable}
    word_lengths = {word: len(word) for word in ['NBA', 'basketball', 'stats']}
    print(f"   Word lengths: {word_lengths}")

    # From two lists using zip
    teams = ['LAL', 'BOS', 'GSW']
    wins = [25, 28, 22]
    team_wins = {team: w for team, w in zip(teams, wins)}
    print(f"   Team wins: {team_wins}")

    # -------------------------------------------------------------------------
    # 3. Lambda Functions
    # -------------------------------------------------------------------------
    print("\n3. LAMBDA FUNCTIONS")
    print("-" * 40)

    # Lambda is an anonymous function: lambda arguments: expression
    # Useful for short, one-time operations

    # Sorting with custom key
    players = [('LeBron', 28.5), ('Curry', 30.1), ('Giannis', 29.8)]

    # Sort by points (second element)
    sorted_by_pts = sorted(players, key=lambda x: x[1], reverse=True)
    print(f"   Sorted by points: {sorted_by_pts}")

    # With filter
    high_scorers = list(filter(lambda x: x[1] > 29, players))
    print(f"   High scorers (>29 pts): {high_scorers}")

    # -------------------------------------------------------------------------
    # 4. Walrus Operator (:=) - Python 3.8+
    # -------------------------------------------------------------------------
    print("\n4. WALRUS OPERATOR (:=)")
    print("-" * 40)

    # Assigns AND returns value in one expression
    # Useful to avoid computing something twice

    data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

    # Without walrus - compute len() twice or use temp variable:
    # n = len(data)
    # if n > 5:
    #     print(f"Length {n} is greater than 5")

    # With walrus - cleaner:
    if (n := len(data)) > 5:
        print(f"   Length {n} is greater than 5")

    # In list comprehension - filter and transform
    results = [y for x in data if (y := x * 2) > 10]
    print(f"   Doubled values > 10: {results}")

    # -------------------------------------------------------------------------
    # 5. Enumerate and Zip
    # -------------------------------------------------------------------------
    print("\n5. ENUMERATE AND ZIP")
    print("-" * 40)

    # enumerate() gives you index + value
    teams = ['Lakers', 'Celtics', 'Warriors']
    for i, team in enumerate(teams, start=1):  # start=1 makes it 1-indexed
        print(f"   {i}. {team}")

    # zip() combines iterables element-wise
    cities = ['Los Angeles', 'Boston', 'San Francisco']
    for team, city in zip(teams, cities):
        print(f"   {team} play in {city}")

    # -------------------------------------------------------------------------
    # 6. Unpacking
    # -------------------------------------------------------------------------
    print("\n6. UNPACKING")
    print("-" * 40)

    # Tuple unpacking
    game_result = ('LAL', 'BOS', 115, 108)
    home, away, home_pts, away_pts = game_result
    print(f"   {home} {home_pts} - {away} {away_pts}")

    # Star unpacking - get first/last and rest
    scores = [105, 98, 112, 99, 118, 103]
    first, *middle, last = scores
    print(f"   First: {first}, Middle: {middle}, Last: {last}")

    # Dictionary unpacking with **
    defaults = {'points': 0, 'rebounds': 0, 'assists': 0}
    player_stats = {'points': 25, 'assists': 8}
    combined = {**defaults, **player_stats}  # player_stats overwrites defaults
    print(f"   Combined stats: {combined}")


# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == '__main__':
    print("\n" + "="*60)
    print("NBA DATA EXPLORATION TUTORIAL")
    print("="*60)

    # Create database connection
    engine = create_connection()
    print("✓ Database engine created")

    # Test connection
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            print("✓ Database connection successful")
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        exit(1)

    # Run explorations
    print("\n" + "-"*60)
    print("Choose what to explore:")
    print("-"*60)
    print("1. Database schema (tables and structure)")
    print("2. Data overview (counts and date ranges)")
    print("3. Sample game analysis")
    print("4. Team performance summary")
    print("5. Pythonic patterns demo")
    print("6. Run all explorations")
    print("-"*60)

    choice = input("Enter choice (1-6): ").strip()

    if choice == '1':
        tables = explore_schema(engine)
        table_name = input("\nEnter table name to inspect (or press Enter to skip): ").strip()
        if table_name:
            explore_table_structure(engine, table_name)
    elif choice == '2':
        explore_data_overview(engine)
    elif choice == '3':
        explore_sample_game(engine)
    elif choice == '4':
        explore_team_performance(engine)
    elif choice == '5':
        pythonic_patterns_demo()
    elif choice == '6':
        tables = explore_schema(engine)
        explore_data_overview(engine)
        explore_sample_game(engine)
        explore_team_performance(engine)
        pythonic_patterns_demo()
    else:
        print("Invalid choice")

    # Cleanup
    engine.dispose()
    print("\n✓ Connection closed")
