"""
Feature Engineering for NBA Game Prediction
============================================

This script builds a dataset for predicting:
1. Win/Loss (classification)
2. Point margin (regression)

KEY CONCEPT: Data Leakage Prevention
------------------------------------
We can ONLY use information available BEFORE each game.
This means computing rolling/historical statistics, not using
stats from the game we're predicting.

Learning objectives:
- Understanding data leakage
- Rolling window calculations with pandas
- Feature engineering strategies
- Pythonic patterns (groupby, apply, lambda)
"""

import sqlalchemy as sql
from sqlalchemy import text
import pandas as pd
import numpy as np
from typing import Tuple

# ============================================================================
# DATABASE CONNECTION
# ============================================================================

def create_engine():
    """Create database connection engine."""
    host = 'localhost'
    user = 'kaiyamamoto'
    password = 'KN!yoWMhiH8cBvD'
    port = '3306'
    database = 'nba_data'
    connection_string = f'mysql://{user}:{password}@{host}:{port}/{database}'
    return sql.create_engine(connection_string)


# ============================================================================
# DATA LOADING
# ============================================================================

def load_game_data(engine) -> pd.DataFrame:
    """
    Load game-level data from game_list table.

    This table has one row per team per game (so 2 rows per game).
    Contains: game outcome (WL), basic stats (PTS, REB, AST, etc.), and PLUS_MINUS.
    """
    query = """
        SELECT
            GAME_ID,
            GAME_DATE,
            TEAM_ID,
            TEAM_ABBREVIATION,
            TEAM_NAME,
            MATCHUP,
            WL,
            PTS,
            FGM, FGA, FG_PCT,
            FG3M, FG3A, FG3_PCT,
            FTM, FTA, FT_PCT,
            OREB, DREB, REB,
            AST, STL, BLK, TOV, PF,
            PLUS_MINUS
        FROM game_list
        ORDER BY GAME_DATE, GAME_ID
    """
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)

    # Convert GAME_DATE to datetime
    df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])

    # Create binary win column (1 = win, 0 = loss)
    # Note: Some games have NULL WL (possibly in-progress or data issues)
    df['WIN'] = (df['WL'] == 'W').astype(int)

    # Determine home/away from MATCHUP column
    # Home games: "LAL vs. BOS" (contains "vs.")
    # Away games: "LAL @ BOS" (contains "@")
    df['IS_HOME'] = df['MATCHUP'].str.contains('vs.').astype(int)

    print(f"Loaded {len(df)} team-game records")
    print(f"Date range: {df['GAME_DATE'].min()} to {df['GAME_DATE'].max()}")
    print(f"Unique games: {df['GAME_ID'].nunique()}")

    return df


def load_advanced_stats(engine) -> pd.DataFrame:
    """
    Load advanced team stats (offensive/defensive ratings, pace, etc.)
    """
    query = """
        SELECT
            gameId as GAME_ID,
            teamId as TEAM_ID,
            offensiveRating,
            defensiveRating,
            netRating,
            pace,
            possessions,
            effectiveFieldGoalPercentage as EFG_PCT,
            trueShootingPercentage as TS_PCT,
            assistPercentage,
            assistToTurnover,
            offensiveReboundPercentage as ADV_OREB_PCT,
            defensiveReboundPercentage as ADV_DREB_PCT,
            turnoverRatio,
            PIE
        FROM boxscoreadvancedv3_team
    """
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)

    print(f"Loaded {len(df)} advanced stat records")
    return df


def load_four_factors(engine) -> pd.DataFrame:
    """
    Load four factors stats - the key efficiency metrics in basketball:
    1. Effective FG% (shooting efficiency)
    2. Turnover rate (ball security)
    3. Offensive rebound rate (second chances)
    4. Free throw rate (getting to the line)

    Also includes opponent versions for defensive analysis.
    """
    query = """
        SELECT
            gameId as GAME_ID,
            teamId as TEAM_ID,
            freeThrowAttemptRate as FT_RATE,
            teamTurnoverPercentage as TOV_PCT,
            offensiveReboundPercentage as OREB_PCT,
            oppEffectiveFieldGoalPercentage as OPP_EFG_PCT,
            oppFreeThrowAttemptRate as OPP_FT_RATE,
            oppTeamTurnoverPercentage as OPP_TOV_PCT,
            oppOffensiveReboundPercentage as OPP_OREB_PCT
        FROM boxscorefourfactorsv3_team
    """
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)

    print(f"Loaded {len(df)} four factors records")
    return df


def load_hustle_stats(engine) -> pd.DataFrame:
    """
    Load hustle stats - effort metrics that don't show in traditional box scores.
    """
    query = """
        SELECT
            gameId as GAME_ID,
            teamId as TEAM_ID,
            contestedShots,
            contestedShots2pt,
            contestedShots3pt,
            deflections,
            chargesDrawn,
            screenAssists,
            looseBallsRecoveredTotal as looseBallsRecovered,
            boxOuts
        FROM boxscorehustlev2_team
    """
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)

    print(f"Loaded {len(df)} hustle stat records")
    return df


def load_player_tracking(engine) -> pd.DataFrame:
    """
    Load player tracking stats - movement and ball handling metrics.
    """
    query = """
        SELECT
            gameId as GAME_ID,
            teamId as TEAM_ID,
            speed,
            distance,
            reboundChancesTotal,
            touches,
            passes,
            secondaryAssists,
            contestedFieldGoalsMade,
            contestedFieldGoalsAttempted,
            uncontestedFieldGoalsMade,
            uncontestedFieldGoalsAttempted,
            defendedAtRimFieldGoalsMade,
            defendedAtRimFieldGoalsAttempted
        FROM boxscoreplayertrackv3_team
    """
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)

    print(f"Loaded {len(df)} player tracking records")
    return df


def load_misc_stats(engine) -> pd.DataFrame:
    """
    Load miscellaneous stats - points by situation and foul stats.
    """
    query = """
        SELECT
            gameId as GAME_ID,
            teamId as TEAM_ID,
            pointsOffTurnovers,
            pointsSecondChance,
            pointsFastBreak,
            pointsPaint,
            oppPointsOffTurnovers,
            oppPointsSecondChance,
            oppPointsFastBreak,
            oppPointsPaint,
            foulsDrawn
        FROM boxscoremiscv3_team
    """
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)

    print(f"Loaded {len(df)} misc stat records")
    return df


def load_scoring_stats(engine) -> pd.DataFrame:
    """
    Load scoring breakdown stats - how teams score their points.
    """
    query = """
        SELECT
            gameId as GAME_ID,
            teamId as TEAM_ID,
            percentageFieldGoalsAttempted2pt as pctFGA_2pt,
            percentageFieldGoalsAttempted3pt as pctFGA_3pt,
            percentagePoints2pt as pctPTS_2pt,
            percentagePoints3pt as pctPTS_3pt,
            percentagePointsPaint as pctPTS_paint,
            percentagePointsFastBreak as pctPTS_fastBreak,
            percentageAssistedFGM as pctAssisted,
            percentageUnassistedFGM as pctUnassisted
        FROM boxscorescoringv3_team
    """
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)

    print(f"Loaded {len(df)} scoring stat records")
    return df


# ============================================================================
# FEATURE ENGINEERING
# ============================================================================

def calculate_rolling_features(df: pd.DataFrame,
                                stats_columns: list,
                                windows: list = [5, 10]) -> pd.DataFrame:
    """
    Calculate rolling averages for specified columns.

    CRITICAL: We use shift(1) to exclude the current game!
    This prevents data leakage - we only use past information.

    Parameters:
    -----------
    df : DataFrame with TEAM_ID, GAME_DATE, and stats columns
    stats_columns : List of column names to calculate rolling stats for
    windows : List of window sizes (e.g., [5, 10] for last 5 and 10 games)

    Returns:
    --------
    DataFrame with new rolling average columns

    PYTHONIC PATTERN: Using f-strings in list comprehension for dynamic column names
    """
    # Sort by team and date to ensure correct rolling calculation
    df = df.sort_values(['TEAM_ID', 'GAME_DATE']).copy()

    total_features = len(stats_columns) * len(windows)
    print(f"  Calculating {total_features} rolling features ({len(stats_columns)} stats x {len(windows)} windows)...")

    for window in windows:
        for col in stats_columns:
            new_col_name = f'{col}_L{window}'  # e.g., PTS_L5 for last 5 games avg

            # Group by team, shift to exclude current game, then rolling mean
            # ---------------------------------------------------------------
            # PYTHONIC PATTERN: Method chaining
            # Instead of:
            #   grouped = df.groupby('TEAM_ID')[col]
            #   shifted = grouped.shift(1)
            #   rolled = shifted.rolling(window, min_periods=1).mean()
            # We chain it all together:
            df[new_col_name] = (
                df.groupby('TEAM_ID')[col]
                .transform(lambda x: x.shift(1).rolling(window, min_periods=1).mean())
            )

    return df


def calculate_win_streak(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate current win/loss streak for each team.

    A positive value means wins in a row, negative means losses.

    PYTHONIC PATTERN: Custom function with groupby apply
    """
    df = df.sort_values(['TEAM_ID', 'GAME_DATE']).copy()

    def streak_calculator(group):
        """Calculate streak for a single team's games."""
        streaks = []
        current_streak = 0

        for win in group['WIN']:
            # Before this game, what was the streak?
            streaks.append(current_streak)

            # Update streak after this game
            if win == 1:
                current_streak = current_streak + 1 if current_streak > 0 else 1
            else:
                current_streak = current_streak - 1 if current_streak < 0 else -1

        return pd.Series(streaks, index=group.index)

    df['WIN_STREAK'] = df.groupby('TEAM_ID', group_keys=False).apply(streak_calculator, include_groups=False)

    return df


def calculate_rest_days(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate days of rest since last game.

    Rest can impact performance - back-to-backs are tough!
    """
    df = df.sort_values(['TEAM_ID', 'GAME_DATE']).copy()

    # Calculate days since previous game for each team
    df['REST_DAYS'] = (
        df.groupby('TEAM_ID')['GAME_DATE']
        .transform(lambda x: x.diff().dt.days)
    )

    # Fill NaN (first game of season) with median rest
    df['REST_DAYS'] = df['REST_DAYS'].fillna(3)

    # Cap at reasonable max (long breaks like All-Star)
    df['REST_DAYS'] = df['REST_DAYS'].clip(upper=10)

    return df


def calculate_fatigue_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate comprehensive fatigue-related features.

    Features:
    - IS_BACK_TO_BACK: Binary flag for 2nd game in 2 days
    - IS_3_IN_4_NIGHTS: Binary flag for 3rd game in 4 nights
    - GAMES_LAST_7_DAYS: Count of games in last 7 days
    - GAMES_LAST_14_DAYS: Count of games in last 14 days
    - AVG_REST_LAST_5: Average rest days between last 5 games

    The hypothesis is that more games in fewer days leads to
    fatigue and decreased performance.
    """
    df = df.sort_values(['TEAM_ID', 'GAME_DATE']).copy()

    # Ensure GAME_DATE is datetime
    df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])

    # IS_BACK_TO_BACK: Playing with 0 or 1 day rest
    if 'REST_DAYS' not in df.columns:
        df['REST_DAYS'] = df.groupby('TEAM_ID')['GAME_DATE'].transform(
            lambda x: x.diff().dt.days
        ).fillna(3)

    df['IS_BACK_TO_BACK'] = (df['REST_DAYS'] <= 1).astype(int)

    # For each team-game, calculate games in last N days
    def games_in_last_n_days(group, n_days):
        """Count games played in the last n days (excluding current game)."""
        dates = group['GAME_DATE'].values
        counts = []
        for i, current_date in enumerate(dates):
            # Count games in window before current game
            window_start = current_date - pd.Timedelta(days=n_days)
            count = sum((dates[:i] > window_start) & (dates[:i] <= current_date))
            counts.append(count)
        return pd.Series(counts, index=group.index)

    print("  Calculating games in last 7 days...")
    df['GAMES_LAST_7_DAYS'] = df.groupby('TEAM_ID', group_keys=False).apply(
        lambda g: games_in_last_n_days(g, 7)
    )

    print("  Calculating games in last 14 days...")
    df['GAMES_LAST_14_DAYS'] = df.groupby('TEAM_ID', group_keys=False).apply(
        lambda g: games_in_last_n_days(g, 14)
    )

    # IS_3_IN_4_NIGHTS: 3 games in 4 days (current is 3rd)
    df['IS_3_IN_4_NIGHTS'] = (df['GAMES_LAST_7_DAYS'] >= 2).astype(int)
    # More precisely: 2+ games in last 3 days means this is 3rd in 4 nights

    def games_in_last_3_days(group):
        """Count games in last 3 days for 3-in-4 calculation."""
        dates = group['GAME_DATE'].values
        counts = []
        for i, current_date in enumerate(dates):
            window_start = current_date - pd.Timedelta(days=3)
            count = sum((dates[:i] > window_start) & (dates[:i] <= current_date))
            counts.append(count)
        return pd.Series(counts, index=group.index)

    df['IS_3_IN_4_NIGHTS'] = df.groupby('TEAM_ID', group_keys=False).apply(
        lambda g: games_in_last_3_days(g)
    )
    df['IS_3_IN_4_NIGHTS'] = (df['IS_3_IN_4_NIGHTS'] >= 2).astype(int)

    # AVG_REST_LAST_5: Average rest days between last 5 games
    print("  Calculating average rest over last 5 games...")
    df['AVG_REST_LAST_5'] = (
        df.groupby('TEAM_ID')['REST_DAYS']
        .transform(lambda x: x.shift(1).rolling(5, min_periods=1).mean())
    )
    df['AVG_REST_LAST_5'] = df['AVG_REST_LAST_5'].fillna(2.5)

    # ROAD_TRIP_LENGTH: Consecutive away games (travel fatigue)
    print("  Calculating road trip length...")
    def road_trip_length(group):
        """Count consecutive away games up to current game."""
        is_home = group['IS_HOME'].values
        lengths = []
        current_streak = 0
        for home in is_home:
            if home == 0:  # Away game
                current_streak += 1
            else:
                current_streak = 0
            lengths.append(current_streak)
        return pd.Series(lengths, index=group.index)

    if 'IS_HOME' in df.columns:
        df['ROAD_TRIP_LENGTH'] = df.groupby('TEAM_ID', group_keys=False).apply(road_trip_length)
    else:
        df['ROAD_TRIP_LENGTH'] = 0

    print(f"  Fatigue features added: IS_BACK_TO_BACK, IS_3_IN_4_NIGHTS, "
          f"GAMES_LAST_7_DAYS, GAMES_LAST_14_DAYS, AVG_REST_LAST_5, ROAD_TRIP_LENGTH")

    return df


def calculate_home_away_splits(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate rolling home and away performance separately.

    Home court advantage is real in the NBA!
    """
    df = df.sort_values(['TEAM_ID', 'GAME_DATE']).copy()

    # Rolling win % at home (last 10 home games)
    df['HOME_WIN_PCT_L10'] = (
        df[df['IS_HOME'] == 1]
        .groupby('TEAM_ID')['WIN']
        .transform(lambda x: x.shift(1).rolling(10, min_periods=1).mean())
    )

    # Rolling win % on road (last 10 away games)
    df['AWAY_WIN_PCT_L10'] = (
        df[df['IS_HOME'] == 0]
        .groupby('TEAM_ID')['WIN']
        .transform(lambda x: x.shift(1).rolling(10, min_periods=1).mean())
    )

    # Forward fill to carry values to all games
    df['HOME_WIN_PCT_L10'] = df.groupby('TEAM_ID')['HOME_WIN_PCT_L10'].ffill()
    df['AWAY_WIN_PCT_L10'] = df.groupby('TEAM_ID')['AWAY_WIN_PCT_L10'].ffill()

    # Fill remaining NaN with 0.5 (neutral)
    df['HOME_WIN_PCT_L10'] = df['HOME_WIN_PCT_L10'].fillna(0.5)
    df['AWAY_WIN_PCT_L10'] = df['AWAY_WIN_PCT_L10'].fillna(0.5)

    return df


def create_matchup_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Create game-level features by combining both teams' stats.

    For each game, we want:
    - Team's features
    - Opponent's features
    - Differential features (team - opponent)

    This transforms from team-game rows to game rows.
    """
    # Get unique games
    games = df[['GAME_ID', 'GAME_DATE']].drop_duplicates()

    # Separate home and away teams
    home_df = df[df['IS_HOME'] == 1].copy()
    away_df = df[df['IS_HOME'] == 0].copy()

    # Rename columns to distinguish home vs away
    home_cols = {col: f'HOME_{col}' for col in home_df.columns
                 if col not in ['GAME_ID', 'GAME_DATE', 'MATCHUP']}
    away_cols = {col: f'AWAY_{col}' for col in away_df.columns
                 if col not in ['GAME_ID', 'GAME_DATE', 'MATCHUP']}

    home_df = home_df.rename(columns=home_cols)
    away_df = away_df.rename(columns=away_cols)

    # Merge home and away for each game
    matchup_df = home_df.merge(
        away_df[['GAME_ID'] + list(away_cols.values())],
        on='GAME_ID',
        how='inner'
    )

    return matchup_df


# ============================================================================
# MAIN PIPELINE
# ============================================================================

def build_feature_dataset(engine,
                          start_date: str = '2015-01-01',
                          end_date: str = '2025-12-31') -> pd.DataFrame:
    """
    Main function to build the complete feature dataset.

    Parameters:
    -----------
    engine : SQLAlchemy engine
    start_date : Filter games after this date
    end_date : Filter games before this date

    Returns:
    --------
    DataFrame ready for ML with features and target variables
    """
    print("="*60)
    print("BUILDING FEATURE DATASET")
    print("="*60)

    # Step 1: Load base game data
    print("\n[1/8] Loading game data...")
    game_df = load_game_data(engine)

    # Step 2: Load and merge additional stats
    print("\n[2/8] Loading advanced stats...")
    advanced_df = load_advanced_stats(engine)
    game_df = game_df.merge(advanced_df, on=['GAME_ID', 'TEAM_ID'], how='left')

    print("\n[3/8] Loading four factors...")
    four_factors_df = load_four_factors(engine)
    game_df = game_df.merge(four_factors_df, on=['GAME_ID', 'TEAM_ID'], how='left')

    print("\n[4/8] Loading hustle stats...")
    hustle_df = load_hustle_stats(engine)
    game_df = game_df.merge(hustle_df, on=['GAME_ID', 'TEAM_ID'], how='left')

    print("\n[5/8] Loading player tracking stats...")
    tracking_df = load_player_tracking(engine)
    game_df = game_df.merge(tracking_df, on=['GAME_ID', 'TEAM_ID'], how='left')

    print("\n[6/8] Loading misc stats...")
    misc_df = load_misc_stats(engine)
    game_df = game_df.merge(misc_df, on=['GAME_ID', 'TEAM_ID'], how='left')

    print("\n[7/8] Loading scoring stats...")
    scoring_df = load_scoring_stats(engine)
    game_df = game_df.merge(scoring_df, on=['GAME_ID', 'TEAM_ID'], how='left')

    # Step 3: Calculate rolling features
    print("\n[8/8] Calculating rolling features...")

    # =========================================================================
    # COMPREHENSIVE ROLLING STATS LIST
    # =========================================================================
    rolling_stats = [
        # --- Traditional Box Score (game_list) ---
        'PTS',              # Points scored
        'FGM',              # Field goals made
        'FGA',              # Field goals attempted
        'FG_PCT',           # Field goal percentage
        'FG3M',             # 3-pointers made
        'FG3A',             # 3-pointers attempted
        'FG3_PCT',          # 3-point percentage
        'FTM',              # Free throws made
        'FTA',              # Free throws attempted
        'FT_PCT',           # Free throw percentage
        'OREB',             # Offensive rebounds
        'DREB',             # Defensive rebounds
        'REB',              # Total rebounds
        'AST',              # Assists
        'STL',              # Steals
        'BLK',              # Blocks
        'TOV',              # Turnovers
        'PF',               # Personal fouls
        'PLUS_MINUS',       # Point differential

        # --- Advanced Stats (boxscoreadvancedv3_team) ---
        'offensiveRating',      # Points per 100 possessions
        'defensiveRating',      # Points allowed per 100 possessions
        'netRating',            # Offensive - Defensive rating
        'pace',                 # Possessions per 48 minutes
        'possessions',          # Total possessions
        'EFG_PCT',              # Effective FG% (weights 3s)
        'TS_PCT',               # True shooting % (includes FTs)
        'assistPercentage',     # % of FGs that were assisted
        'assistToTurnover',     # AST/TOV ratio
        'ADV_OREB_PCT',         # Offensive rebound %
        'ADV_DREB_PCT',         # Defensive rebound %
        'turnoverRatio',        # Turnovers per 100 possessions
        'PIE',                  # Player Impact Estimate

        # --- Four Factors (boxscorefourfactorsv3_team) ---
        'FT_RATE',              # FTA/FGA (getting to the line)
        'TOV_PCT',              # Turnover percentage
        'OREB_PCT',             # Offensive rebound percentage
        'OPP_EFG_PCT',          # Opponent effective FG%
        'OPP_FT_RATE',          # Opponent FTA/FGA
        'OPP_TOV_PCT',          # Opponent turnover %
        'OPP_OREB_PCT',         # Opponent offensive rebound %

        # --- Hustle Stats (boxscorehustlev2_team) ---
        'contestedShots',       # Total shots contested
        'contestedShots2pt',    # 2-point shots contested
        'contestedShots3pt',    # 3-point shots contested
        'deflections',          # Passes deflected
        'chargesDrawn',         # Charges drawn
        'screenAssists',        # Screens leading to scores
        'looseBallsRecovered',  # Loose balls recovered
        'boxOuts',              # Box outs

        # --- Player Tracking (boxscoreplayertrackv3_team) ---
        'speed',                # Average speed (mph)
        'distance',             # Distance traveled (miles)
        'reboundChancesTotal',  # Rebound opportunities
        'touches',              # Ball touches
        'passes',               # Passes made
        'secondaryAssists',     # Hockey assists
        'contestedFieldGoalsMade',      # Contested FGM
        'contestedFieldGoalsAttempted', # Contested FGA
        'uncontestedFieldGoalsMade',    # Open shot FGM
        'uncontestedFieldGoalsAttempted', # Open shot FGA
        'defendedAtRimFieldGoalsMade',  # Rim FGM allowed
        'defendedAtRimFieldGoalsAttempted', # Rim FGA faced

        # --- Miscellaneous (boxscoremiscv3_team) ---
        'pointsOffTurnovers',   # Points off turnovers
        'pointsSecondChance',   # Second chance points
        'pointsFastBreak',      # Fast break points
        'pointsPaint',          # Points in the paint
        'oppPointsOffTurnovers',    # Opponent pts off TOV
        'oppPointsSecondChance',    # Opponent 2nd chance pts
        'oppPointsFastBreak',       # Opponent fast break pts
        'oppPointsPaint',           # Opponent paint pts
        'foulsDrawn',           # Fouls drawn

        # --- Scoring Breakdown (boxscorescoringv3_team) ---
        'pctFGA_2pt',           # % of shots that are 2-pointers
        'pctFGA_3pt',           # % of shots that are 3-pointers
        'pctPTS_2pt',           # % of points from 2-pointers
        'pctPTS_3pt',           # % of points from 3-pointers
        'pctPTS_paint',         # % of points in the paint
        'pctPTS_fastBreak',     # % of points from fast breaks
        'pctAssisted',          # % of FGM that were assisted
        'pctUnassisted',        # % of FGM that were unassisted
    ]

    # Filter to columns that exist (some might be missing due to join issues)
    available_stats = [col for col in rolling_stats if col in game_df.columns]
    missing_stats = [col for col in rolling_stats if col not in game_df.columns]

    if missing_stats:
        print(f"  Note: {len(missing_stats)} stats not available (missing data for some games)")
        print(f"  Missing: {missing_stats[:5]}{'...' if len(missing_stats) > 5 else ''}")

    print(f"  Using {len(available_stats)} stats for rolling calculations")

    game_df = calculate_rolling_features(game_df, available_stats, windows=[5, 10])

    # Calculate other derived features
    print("  Calculating win streaks...")
    game_df = calculate_win_streak(game_df)
    print("  Calculating rest days...")
    game_df = calculate_rest_days(game_df)
    print("  Calculating fatigue features...")
    game_df = calculate_fatigue_features(game_df)
    print("  Calculating home/away splits...")
    game_df = calculate_home_away_splits(game_df)

    # Step 4: Filter date range
    print("\nFiltering date range and finalizing...")
    game_df = game_df[
        (game_df['GAME_DATE'] >= start_date) &
        (game_df['GAME_DATE'] <= end_date)
    ]

    # Remove games with no target variable
    game_df = game_df[game_df['WL'].notna()]

    print(f"\nFinal dataset: {len(game_df)} team-game records")
    print(f"Date range: {game_df['GAME_DATE'].min()} to {game_df['GAME_DATE'].max()}")
    print(f"Features created: {len(game_df.columns)} columns")

    return game_df


def prepare_ml_dataset(df: pd.DataFrame) -> Tuple[pd.DataFrame, list]:
    """
    Prepare the final dataset for ML by selecting features and creating
    differential features between home and away teams.

    Returns:
    --------
    Tuple of (DataFrame with features and targets, list of feature column names)
    """
    # Create matchup-level features (one row per game)
    matchup_df = create_matchup_features(df)

    # Define feature columns (rolling averages only - no current game stats!)
    # Added fatigue features: IS_BACK_TO_BACK, IS_3_IN_4, GAMES_LAST, AVG_REST, ROAD_TRIP
    feature_patterns = ['_L5', '_L10', 'STREAK', 'REST_DAYS', 'WIN_PCT',
                        'IS_BACK_TO_BACK', 'IS_3_IN_4_NIGHTS', 'GAMES_LAST',
                        'AVG_REST_LAST', 'ROAD_TRIP_LENGTH']

    # Get all feature columns
    all_features = []
    for col in matchup_df.columns:
        if any(pattern in col for pattern in feature_patterns):
            all_features.append(col)

    # Create differential features (home - away)
    diff_features = []
    home_features = [f for f in all_features if f.startswith('HOME_')]

    for home_feat in home_features:
        away_feat = home_feat.replace('HOME_', 'AWAY_')
        if away_feat in all_features:
            diff_name = home_feat.replace('HOME_', 'DIFF_')
            matchup_df[diff_name] = matchup_df[home_feat] - matchup_df[away_feat]
            diff_features.append(diff_name)

    # Final feature list: home features + away features + differentials
    final_features = all_features + diff_features

    # Target variables
    matchup_df['TARGET_WIN'] = matchup_df['HOME_WIN']  # 1 if home team won
    matchup_df['TARGET_MARGIN'] = matchup_df['HOME_PLUS_MINUS']  # Point differential

    print(f"\nML Dataset prepared:")
    print(f"  Games: {len(matchup_df)}")
    print(f"  Features: {len(final_features)}")
    print(f"  Home features: {len([f for f in final_features if f.startswith('HOME_')])}")
    print(f"  Away features: {len([f for f in final_features if f.startswith('AWAY_')])}")
    print(f"  Differential features: {len(diff_features)}")

    return matchup_df, final_features


# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == '__main__':
    # Create database connection
    engine = create_engine()

    # Build feature dataset
    # Using 2020+ for more recent, relevant data
    feature_df = build_feature_dataset(
        engine,
        start_date='2015-01-01',
        end_date='2025-12-31'
    )

    # Prepare ML-ready dataset
    ml_df, feature_cols = prepare_ml_dataset(feature_df)

    # Preview
    print("\n" + "="*60)
    print("DATASET PREVIEW")
    print("="*60)

    # Group features by category for display
    print("\nFeature columns by category:")

    categories = {
        'Traditional': ['PTS', 'FGM', 'FGA', 'FG_PCT', 'FG3M', 'FG3A', 'FG3_PCT',
                       'FTM', 'FTA', 'FT_PCT', 'OREB', 'DREB', 'REB', 'AST',
                       'STL', 'BLK', 'TOV', 'PF', 'PLUS_MINUS'],
        'Advanced': ['offensiveRating', 'defensiveRating', 'netRating', 'pace',
                    'possessions', 'EFG_PCT', 'TS_PCT', 'assistPercentage',
                    'assistToTurnover', 'ADV_OREB_PCT', 'ADV_DREB_PCT',
                    'turnoverRatio', 'PIE'],
        'Four Factors': ['FT_RATE', 'TOV_PCT', 'OREB_PCT', 'OPP_EFG_PCT',
                        'OPP_FT_RATE', 'OPP_TOV_PCT', 'OPP_OREB_PCT'],
        'Hustle': ['contestedShots', 'deflections', 'chargesDrawn',
                  'screenAssists', 'looseBallsRecovered', 'boxOuts'],
        'Tracking': ['speed', 'distance', 'touches', 'passes', 'secondaryAssists'],
        'Misc': ['pointsOffTurnovers', 'pointsSecondChance', 'pointsFastBreak',
                'pointsPaint', 'foulsDrawn'],
        'Scoring': ['pctFGA_2pt', 'pctFGA_3pt', 'pctPTS_2pt', 'pctPTS_3pt',
                   'pctAssisted', 'pctUnassisted'],
    }

    for cat_name, cat_stats in categories.items():
        cat_features = [f for f in feature_cols if any(s in f for s in cat_stats)]
        print(f"\n  {cat_name}: {len(cat_features)} features")

    print(f"\n  Other (streaks, rest, win%): {len([f for f in feature_cols if 'STREAK' in f or 'REST' in f or 'WIN_PCT' in f])} features")

    print("\nTarget distribution:")
    print(f"  Home wins: {ml_df['TARGET_WIN'].sum()} ({ml_df['TARGET_WIN'].mean()*100:.1f}%)")
    print(f"  Away wins: {len(ml_df) - ml_df['TARGET_WIN'].sum()} ({(1-ml_df['TARGET_WIN'].mean())*100:.1f}%)")
    print(f"  Avg margin: {ml_df['TARGET_MARGIN'].mean():.1f} points")

    # Save to CSV for later use
    output_file = 'nba_ml_features.csv'
    ml_df.to_csv(output_file, index=False)
    print(f"\nDataset saved to {output_file}")

    # Cleanup
    engine.dispose()
