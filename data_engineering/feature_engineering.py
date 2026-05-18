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

# Project-root bootstrap so cross-folder imports (core.db, data_engineering.*) work regardless of CWD.
import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

import sqlalchemy as sql
from sqlalchemy import text
import pandas as pd
import numpy as np
from typing import Tuple

# ============================================================================
# DATABASE CONNECTION
# ============================================================================

def create_engine():
    """Create database connection engine. Reads MySQL config from environment via db.get_engine()."""
    from core.db import get_engine
    return get_engine()


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


def _process_single_game(args):
    """
    Process a single game for player projections (used by parallel executor).

    This is a module-level function to work with multiprocessing.
    """
    game_id, game_date, team_id, opponent_id, connection_string = args

    default_features = {
        'PROJ_PTS_FROM_PLAYERS': 110.0,
        'PROJ_REB_FROM_PLAYERS': 44.0,
        'PROJ_AST_FROM_PLAYERS': 25.0,
        'WEIGHTED_AVG_USAGE': 20.0,
        'WEIGHTED_AVG_TS_PCT': 0.55,
        'WEIGHTED_AVG_PIE': 0.1,
        'ROSTER_DEPTH_SCORE': 8,
        'STAR_PLAYER_IMPACT': 20.0,
        'TOP_3_SCORER_SHARE': 0.5,
        'PLAYER_DATA_QUALITY': 0.0
    }

    try:
        # Each worker needs its own database connection
        import sqlalchemy as sql
        engine = sql.create_engine(connection_string)

        from data_engineering.player_projections import get_player_projection_features
        features = get_player_projection_features(engine, team_id, opponent_id, game_date)

        engine.dispose()
        return (game_id, team_id, features, None)  # None = no error
    except Exception as e:
        # Return default values on error, but include error message
        return (game_id, team_id, default_features, str(e))


def calculate_player_projection_features(engine, df: pd.DataFrame, n_jobs: int = -1) -> pd.DataFrame:
    """
    Calculate player-level projection features for historical games.

    This adds features based on player-level data aggregated to team level,
    with opponent adjustments for pace and defensive rating.

    Uses parallel processing for speed (joblib).

    Parameters:
    -----------
    engine : SQLAlchemy engine
    df : DataFrame with game data
    n_jobs : Number of parallel jobs (-1 = all cores, -2 = all but one)
    """
    try:
        from data_engineering.player_projections import get_player_projection_features
        from joblib import Parallel, delayed
    except ImportError as e:
        print(f"  Warning: Required module not available ({e}), skipping player features")
        return df

    print("  Calculating player projection features (parallelized)...")

    # We need to calculate features for each team-game row
    df = df.sort_values(['GAME_DATE', 'GAME_ID', 'TEAM_ID'])

    # Initialize new columns
    player_feature_cols = [
        'PROJ_PTS_FROM_PLAYERS', 'PROJ_REB_FROM_PLAYERS', 'PROJ_AST_FROM_PLAYERS',
        'WEIGHTED_AVG_USAGE', 'WEIGHTED_AVG_TS_PCT', 'WEIGHTED_AVG_PIE',
        'ROSTER_DEPTH_SCORE', 'STAR_PLAYER_IMPACT', 'TOP_3_SCORER_SHARE',
        'PLAYER_DATA_QUALITY'
    ]

    for col in player_feature_cols:
        df[col] = np.nan

    # Build list of tasks (game_id, game_date, team_id, opponent_id)
    # First, create a mapping of game_id -> [team_ids]
    game_teams = df.groupby('GAME_ID')['TEAM_ID'].apply(list).to_dict()

    # Get connection string for workers (must include password!)
    # str(engine.url) hides password with ***, so we use render_as_string
    connection_string = engine.url.render_as_string(hide_password=False)

    # Build task list
    tasks = []
    unique_games = df[['GAME_ID', 'GAME_DATE', 'TEAM_ID']].drop_duplicates()

    for _, row in unique_games.iterrows():
        game_id = row['GAME_ID']
        game_date = row['GAME_DATE']
        if hasattr(game_date, 'strftime'):
            game_date = game_date.strftime('%Y-%m-%d')
        else:
            game_date = str(game_date)[:10]
        team_id = row['TEAM_ID']

        # Find opponent
        teams_in_game = game_teams.get(game_id, [])
        opponent_ids = [t for t in teams_in_game if t != team_id]
        if not opponent_ids:
            continue
        opponent_id = opponent_ids[0]

        tasks.append((game_id, game_date, team_id, opponent_id, connection_string))

    total_tasks = len(tasks)
    print(f"    Processing {total_tasks} team-games using parallel workers...")

    # Determine number of jobs
    import os
    if n_jobs == -1:
        n_jobs = os.cpu_count() or 4
    elif n_jobs == -2:
        n_jobs = max(1, (os.cpu_count() or 4) - 1)

    print(f"    Using {n_jobs} parallel workers...")

    # Process in parallel with progress updates
    # Use batching for progress reporting
    batch_size = 500
    results = []

    for i in range(0, len(tasks), batch_size):
        batch = tasks[i:i + batch_size]
        batch_results = Parallel(n_jobs=n_jobs, prefer="threads")(
            delayed(_process_single_game)(task) for task in batch
        )
        results.extend(batch_results)
        print(f"    Processed {min(i + batch_size, total_tasks)}/{total_tasks} team-games...")

    # Apply results to dataframe and collect errors
    print("    Applying results to dataframe...")
    results_dict = {(r[0], r[1]): (r[2], r[3]) for r in results}  # (features, error)

    error_count = 0
    error_samples = []

    for (game_id, team_id), (features, error) in results_dict.items():
        mask = (df['GAME_ID'] == game_id) & (df['TEAM_ID'] == team_id)
        for col in player_feature_cols:
            if col in features:
                df.loc[mask, col] = features[col]

        if error is not None:
            error_count += 1
            if len(error_samples) < 5:  # Collect first 5 unique errors
                if error not in [e[1] for e in error_samples]:
                    error_samples.append((game_id, error))

    # Report results
    success_count = len(results) - error_count
    print(f"  Player projection features calculated: {success_count} succeeded, {error_count} failed")

    if error_samples:
        print(f"\n  Sample errors (showing up to 5 unique):")
        for game_id, error in error_samples:
            print(f"    - Game {game_id}: {error[:100]}...")

    return df


def _process_injury_impact_for_game(args):
    """
    Calculate injury impact for a single game (used by parallel executor).

    For each team in the game, identifies players who were OUT (DNP/DND/NWT)
    using the comment field from boxscoreplayertrackv3_player table and
    calculates the sum of their historical impacts.
    """
    game_id, game_date, home_team_id, away_team_id, connection_string = args

    default_result = {
        'home_injury_impact': 0.0,
        'away_injury_impact': 0.0,
        'home_players_out': [],
        'away_players_out': []
    }

    try:
        import sqlalchemy as sql
        from sqlalchemy import text
        import pandas as pd

        engine = sql.create_engine(connection_string)

        # Get players who were OUT using the comment field from boxscoreplayertrackv3_player
        # DNP = Did Not Play, DND = Did Not Dress, NWT = Not With Team
        query = f"""
            SELECT p.personId, p.teamId, p.firstName, p.familyName, p.comment
            FROM boxscoreplayertrackv3_player p
            WHERE p.gameId = '{game_id}'
              AND p.comment IS NOT NULL
              AND p.comment != ''
              AND (p.comment LIKE 'DNP%' OR p.comment LIKE 'DND%' OR p.comment LIKE 'NWT%')
        """
        with engine.connect() as conn:
            out_players = pd.read_sql(text(query), conn)

        if len(out_players) == 0:
            engine.dispose()
            return (game_id, default_result, None)

        home_impact = 0.0
        away_impact = 0.0
        home_players_out = []
        away_players_out = []

        # Import player impact function
        try:
            from data_engineering.player_impact import get_player_historical_impact
        except ImportError:
            engine.dispose()
            return (game_id, default_result, "player_impact module not available")

        for _, player in out_players.iterrows():
            player_id = int(player['personId'])
            team_id = int(player['teamId'])
            player_name = f"{player['firstName']} {player['familyName']}"

            # Get impact for this player (using data before this game)
            impact_data = get_player_historical_impact(
                engine, player_id, team_id, game_date
            )

            if impact_data['confidence'] != 'INSUFFICIENT':
                impact_value = impact_data['impact']
                reason = player.get('comment', 'Unknown')

                if team_id == home_team_id:
                    home_impact += impact_value
                    home_players_out.append({
                        'name': player_name,
                        'impact': impact_value,
                        'confidence': impact_data['confidence'],
                        'reason': reason
                    })
                elif team_id == away_team_id:
                    away_impact += impact_value
                    away_players_out.append({
                        'name': player_name,
                        'impact': impact_value,
                        'confidence': impact_data['confidence'],
                        'reason': reason
                    })

        engine.dispose()

        result = {
            'home_injury_impact': home_impact,
            'away_injury_impact': away_impact,
            'home_players_out': home_players_out,
            'away_players_out': away_players_out
        }

        return (game_id, result, None)

    except Exception as e:
        return (game_id, default_result, str(e))


def calculate_injury_impact_features(engine, df: pd.DataFrame, n_jobs: int = -1) -> pd.DataFrame:
    """
    Calculate injury impact features for historical games.

    For each game, identifies players who were OUT using the comment field from
    boxscoreplayertrackv3_player table (DNP/DND/NWT) and calculates the sum of
    their historical impacts. This allows the model to learn how player
    availability affects game outcomes.

    OUT status is determined by comment prefixes:
    - DNP = Did Not Play (Coach's Decision, Injury/Illness, Rest)
    - DND = Did Not Dress (Injury/Illness, specific injuries, Rest)
    - NWT = Not With Team (Personal Reasons, Suspension, Illness)

    Adds features:
    - HOME_INJURY_IMPACT: Sum of impacts for OUT home players
    - AWAY_INJURY_IMPACT: Sum of impacts for OUT away players
    - DIFF_INJURY_IMPACT: Differential (away - home, positive = home advantage)

    Uses parallel processing for speed.
    """
    try:
        from joblib import Parallel, delayed
        from player_impact import get_player_historical_impact
    except ImportError as e:
        print(f"  Warning: Required module not available ({e}), skipping injury features")
        return df

    print("  Calculating injury impact features (parallelized)...")

    # Initialize columns
    df['HOME_INJURY_IMPACT'] = 0.0
    df['AWAY_INJURY_IMPACT'] = 0.0

    # Get unique games with home/away team IDs
    # First, identify home and away teams for each game
    home_teams = df[df['IS_HOME'] == 1][['GAME_ID', 'GAME_DATE', 'TEAM_ID']].copy()
    home_teams = home_teams.rename(columns={'TEAM_ID': 'HOME_TEAM_ID'})

    away_teams = df[df['IS_HOME'] == 0][['GAME_ID', 'TEAM_ID']].copy()
    away_teams = away_teams.rename(columns={'TEAM_ID': 'AWAY_TEAM_ID'})

    games = home_teams.merge(away_teams, on='GAME_ID', how='inner')

    # Get connection string
    connection_string = engine.url.render_as_string(hide_password=False)

    # Build task list
    tasks = []
    for _, row in games.iterrows():
        game_id = row['GAME_ID']
        game_date = row['GAME_DATE']
        if hasattr(game_date, 'strftime'):
            game_date = game_date.strftime('%Y-%m-%d')
        else:
            game_date = str(game_date)[:10]

        tasks.append((
            game_id, game_date,
            int(row['HOME_TEAM_ID']), int(row['AWAY_TEAM_ID']),
            connection_string
        ))

    total_tasks = len(tasks)
    print(f"    Processing {total_tasks} games for injury impacts...")

    # Determine number of jobs
    import os
    if n_jobs == -1:
        n_jobs = os.cpu_count() or 24
    elif n_jobs == -2:
        n_jobs = max(1, (os.cpu_count() or 20) - 1)

    # Limit parallel jobs to avoid overwhelming the database
    n_jobs = min(n_jobs, 24)
    print(f"    Using {n_jobs} parallel workers...")

    # Process in batches
    batch_size = 200
    results = []

    for i in range(0, len(tasks), batch_size):
        batch = tasks[i:i + batch_size]
        batch_results = Parallel(n_jobs=n_jobs, prefer="threads")(
            delayed(_process_injury_impact_for_game)(task) for task in batch
        )
        results.extend(batch_results)
        print(f"    Processed {min(i + batch_size, total_tasks)}/{total_tasks} games...")

    # Apply results to dataframe
    print("    Applying injury impact results...")
    results_dict = {r[0]: (r[1], r[2]) for r in results}

    error_count = 0
    impact_count = 0

    for game_id, (result, error) in results_dict.items():
        if error:
            error_count += 1
            continue

        home_impact = result['home_injury_impact']
        away_impact = result['away_injury_impact']

        if home_impact != 0 or away_impact != 0:
            impact_count += 1

        # Set values for home team row
        mask_home = (df['GAME_ID'] == game_id) & (df['IS_HOME'] == 1)
        df.loc[mask_home, 'HOME_INJURY_IMPACT'] = home_impact
        df.loc[mask_home, 'AWAY_INJURY_IMPACT'] = away_impact

        # Set values for away team row
        mask_away = (df['GAME_ID'] == game_id) & (df['IS_HOME'] == 0)
        df.loc[mask_away, 'HOME_INJURY_IMPACT'] = home_impact
        df.loc[mask_away, 'AWAY_INJURY_IMPACT'] = away_impact

    print(f"  Injury impact features calculated: {impact_count} games had players OUT")
    if error_count > 0:
        print(f"    ({error_count} games had errors)")

    return df


def _process_player_slots_for_game_bulk(game_id, game_date, home_team_id, away_team_id,
                                         impacts_by_team, sorted_dates, availability_lookup, n_slots=8):
    """
    Calculate player slot features for a single game using pre-fetched bulk data.

    This is the fast version that uses in-memory lookups instead of database queries.

    Args:
        game_id: Game ID
        game_date: Game date string (YYYY-MM-DD)
        home_team_id: Home team ID
        away_team_id: Away team ID
        impacts_by_team: Pre-fetched player impacts dict from bulk_fetch_player_impacts
        sorted_dates: Sorted list of compute dates
        availability_lookup: Pre-fetched availability dict from bulk_fetch_player_availability
        n_slots: Number of player slots per team

    Returns tuple: (game_id, features_dict, error)
    """
    from data_engineering.player_impact import get_top_players_for_team_date

    # Default features
    default_features = {}
    for side in ['HOME', 'AWAY']:
        for slot in range(1, n_slots + 1):
            default_features[f'{side}_SLOT_{slot}_IMPACT'] = 0.0
            default_features[f'{side}_SLOT_{slot}_AVAILABLE'] = 1.0  # Assume available
            default_features[f'{side}_SLOT_{slot}_PLAYER_ID'] = 0

    try:
        features = {}

        # Process each team
        for side, team_id in [('HOME', home_team_id), ('AWAY', away_team_id)]:
            # Get top players by impact using in-memory lookup
            top_players = get_top_players_for_team_date(
                impacts_by_team, sorted_dates, team_id, game_date, top_n=n_slots
            )

            # Get availability from pre-fetched data
            availability_key = (game_id, team_id)
            availability = availability_lookup.get(availability_key, {})

            # Fill slot features
            for player in top_players:
                slot = player['slot']
                player_id = player['player_id']

                features[f'{side}_SLOT_{slot}_IMPACT'] = player['impact']
                features[f'{side}_SLOT_{slot}_PLAYER_ID'] = player_id

                # Check if this player was available in this game
                if player_id in availability:
                    features[f'{side}_SLOT_{slot}_AVAILABLE'] = 1.0 if availability[player_id]['available'] else 0.0
                else:
                    # Player not in game data - might have been traded, etc.
                    # Default to available if not explicitly OUT
                    features[f'{side}_SLOT_{slot}_AVAILABLE'] = 1.0

        return (game_id, features, None)

    except Exception as e:
        return (game_id, default_features, str(e))


def calculate_player_slot_features(engine, df: pd.DataFrame, n_jobs: int = -1, n_slots: int = 8) -> pd.DataFrame:
    """
    Calculate player slot features for historical games.

    For each game, creates features for the top N players (by impact) on each team.
    Each player slot has:
    - SLOT_X_IMPACT: The player's historical impact score
    - SLOT_X_AVAILABLE: 1 if playing, 0 if OUT (DNP/DND/NWT)
    - SLOT_X_PLAYER_ID: The player's ID (for NN embedding, ignored by RF)

    The model learns how player availability affects outcomes, and SHAP can
    attribute impact to specific slots which map back to player names.

    OPTIMIZED: Uses bulk data fetching to avoid N+1 query problem.
    Previously made ~80,000+ DB queries, now makes just 2 bulk queries.

    Args:
        engine: SQLAlchemy engine
        df: DataFrame with game data (must have IS_HOME column)
        n_jobs: Number of parallel workers (not used in optimized version)
        n_slots: Number of player slots per team (default: 8)

    Returns:
        DataFrame with player slot features added
    """
    try:
        from data_engineering.player_impact import (
            ensure_player_impact_table,
            bulk_fetch_player_impacts,
            bulk_fetch_player_availability
        )
    except ImportError as e:
        print(f"  Warning: Required module not available ({e}), skipping player slot features")
        return df

    print("  Calculating player slot features (optimized bulk fetch)...")

    # Ensure player_impact table exists
    try:
        ensure_player_impact_table(engine)
    except Exception as e:
        print(f"  Warning: Could not ensure player_impact table: {e}")

    # Initialize new columns
    slot_feature_cols = []
    for side in ['HOME', 'AWAY']:
        for slot in range(1, n_slots + 1):
            slot_feature_cols.extend([
                f'{side}_SLOT_{slot}_IMPACT',
                f'{side}_SLOT_{slot}_AVAILABLE',
                f'{side}_SLOT_{slot}_PLAYER_ID'
            ])

    for col in slot_feature_cols:
        if 'AVAILABLE' in col:
            df[col] = 1.0  # Default: available
        elif 'PLAYER_ID' in col:
            df[col] = 0  # Default: no player
        else:
            df[col] = 0.0  # Default: zero impact

    # Get unique games with home/away team IDs
    home_teams = df[df['IS_HOME'] == 1][['GAME_ID', 'GAME_DATE', 'TEAM_ID']].copy()
    home_teams = home_teams.rename(columns={'TEAM_ID': 'HOME_TEAM_ID'})

    away_teams = df[df['IS_HOME'] == 0][['GAME_ID', 'TEAM_ID']].copy()
    away_teams = away_teams.rename(columns={'TEAM_ID': 'AWAY_TEAM_ID'})

    games = home_teams.merge(away_teams, on='GAME_ID', how='inner')

    if len(games) == 0:
        print("    No games to process")
        return df

    # Get date range and team IDs for bulk fetching
    min_date = df['GAME_DATE'].min()
    max_date = df['GAME_DATE'].max()
    if hasattr(min_date, 'strftime'):
        min_date_str = min_date.strftime('%Y-%m-%d')
        max_date_str = max_date.strftime('%Y-%m-%d')
    else:
        min_date_str = str(min_date)[:10]
        max_date_str = str(max_date)[:10]

    all_team_ids = list(set(games['HOME_TEAM_ID'].tolist() + games['AWAY_TEAM_ID'].tolist()))
    all_game_ids = games['GAME_ID'].unique().tolist()

    print(f"    Date range: {min_date_str} to {max_date_str}")
    print(f"    Teams: {len(all_team_ids)}, Games: {len(all_game_ids)}")

    # STEP 1: Bulk fetch all player impacts (single query)
    print("    Step 1/3: Bulk fetching player impacts...")
    impacts_by_team, sorted_dates = bulk_fetch_player_impacts(
        engine, all_team_ids, min_date_str, max_date_str
    )

    if not impacts_by_team:
        print("    WARNING: No player impacts found in cache!")
        print("    Run `python player_impact.py` or `populate_player_impact_table()` to populate the cache.")
        print("    Continuing with default values...")

    # STEP 2: Bulk fetch all player availability (single query)
    print("    Step 2/3: Bulk fetching player availability...")
    availability_lookup = bulk_fetch_player_availability(engine, all_game_ids)

    # STEP 3: Process all games using in-memory lookups (no DB queries)
    print("    Step 3/3: Processing games with in-memory lookups...")

    total_games = len(games)
    results = []
    error_count = 0

    for idx, row in games.iterrows():
        game_id = row['GAME_ID']
        game_date = row['GAME_DATE']
        if hasattr(game_date, 'strftime'):
            game_date_str = game_date.strftime('%Y-%m-%d')
        else:
            game_date_str = str(game_date)[:10]

        home_team_id = int(row['HOME_TEAM_ID'])
        away_team_id = int(row['AWAY_TEAM_ID'])

        # Process this game using bulk data (no DB queries!)
        game_id, features, error = _process_player_slots_for_game_bulk(
            game_id, game_date_str, home_team_id, away_team_id,
            impacts_by_team, sorted_dates, availability_lookup, n_slots
        )

        if error:
            error_count += 1
        else:
            results.append((game_id, features))

        # Progress update every 1000 games
        if (len(results) + error_count) % 1000 == 0:
            print(f"      Processed {len(results) + error_count}/{total_games} games...")

    # Apply results to dataframe
    print("    Applying player slot results...")

    for game_id, features in results:
        # Apply features to both home and away rows for this game
        mask = df['GAME_ID'] == game_id

        for col, value in features.items():
            if col in df.columns:
                df.loc[mask, col] = value

    success_count = len(results)
    print(f"  Player slot features calculated: {success_count} games succeeded, {error_count} errors")

    # Also create derived features
    print("  Creating derived slot features...")

    # Total available impact per team
    for side in ['HOME', 'AWAY']:
        impact_cols = [f'{side}_SLOT_{i}_IMPACT' for i in range(1, n_slots + 1)]
        avail_cols = [f'{side}_SLOT_{i}_AVAILABLE' for i in range(1, n_slots + 1)]

        # Effective impact = impact * available
        df[f'{side}_TOTAL_AVAILABLE_IMPACT'] = sum(
            df[impact_cols[i]] * df[avail_cols[i]] for i in range(n_slots)
        )

        # Total missing impact = sum of impacts for unavailable players
        df[f'{side}_TOTAL_MISSING_IMPACT'] = sum(
            df[impact_cols[i]] * (1 - df[avail_cols[i]]) for i in range(n_slots)
        )

        # Count of unavailable players
        df[f'{side}_PLAYERS_OUT'] = sum(
            (1 - df[avail_cols[i]]) for i in range(n_slots)
        )

    # Differential features
    df['DIFF_AVAILABLE_IMPACT'] = df['HOME_TOTAL_AVAILABLE_IMPACT'] - df['AWAY_TOTAL_AVAILABLE_IMPACT']
    df['DIFF_MISSING_IMPACT'] = df['HOME_TOTAL_MISSING_IMPACT'] - df['AWAY_TOTAL_MISSING_IMPACT']

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
                          start_date: str = '2022-01-01',
                          end_date: str = '2026-12-31',
                          include_player_features: bool = True,
                          include_legacy_injury_features: bool = False) -> pd.DataFrame:
    """
    Main function to build the complete feature dataset.

    Parameters:
    -----------
    engine : SQLAlchemy engine
    start_date : Filter games after this date
    end_date : Filter games before this date
    include_player_features : Whether to include player-level projection features
    include_legacy_injury_features : Whether to include legacy injury impact features (default False)
                                     The new player slot features provide better integrated roster modeling.

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

    # Early filter to avoid processing decades of old data
    # Add 6-month buffer before start_date for rolling feature context
    from datetime import datetime, timedelta
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    buffer_date = (start_dt - timedelta(days=180)).strftime('%Y-%m-%d')

    original_count = len(game_df)
    game_df = game_df[game_df['GAME_DATE'] >= buffer_date]
    filtered_count = len(game_df)

    print(f"\n  Early filter applied: {buffer_date} onwards")
    print(f"  Reduced from {original_count} to {filtered_count} records ({filtered_count/original_count*100:.1f}%)")

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

    # Step 8b: Calculate player projection features (optional, can be slow)
    if include_player_features:
        print("\n[9/11] Calculating player projection features...")
        try:
            game_df = calculate_player_projection_features(engine, game_df)
            # Verify features were added
            player_cols = [c for c in game_df.columns if 'PROJ_' in c or 'WEIGHTED_AVG' in c or 'ROSTER_DEPTH' in c]
            if player_cols:
                print(f"  ✓ Added {len(player_cols)} player projection columns")
            else:
                print("  ⚠ Warning: No player projection columns were added")
        except Exception as e:
            print(f"  ✗ Error calculating player features: {e}")
            print("    Continuing without player features...")

        # Step 8c: Calculate injury impact features (legacy - skipped by default)
        if include_legacy_injury_features:
            print("\n[10/11] Calculating injury impact features (legacy)...")
            try:
                game_df = calculate_injury_impact_features(engine, game_df)
                # Verify features were added
                injury_cols = [c for c in game_df.columns if 'INJURY_IMPACT' in c]
                if injury_cols:
                    print(f"  ✓ Added {len(injury_cols)} injury impact columns")
            except Exception as e:
                print(f"  ✗ Error calculating injury features: {e}")
                print("    Continuing without injury features...")
        else:
            print("\n[10/11] Skipping legacy injury impact features (use --include-legacy-injury to enable)")

        # Step 8d: Calculate player slot features (NEW - integrated roster model)
        print("\n[11/11] Calculating player slot features (integrated roster model)...")
        try:
            game_df = calculate_player_slot_features(engine, game_df)
            # Verify features were added
            slot_cols = [c for c in game_df.columns if '_SLOT_' in c]
            derived_cols = [c for c in game_df.columns if 'TOTAL_AVAILABLE_IMPACT' in c or 'TOTAL_MISSING_IMPACT' in c]
            if slot_cols:
                print(f"  ✓ Added {len(slot_cols)} player slot columns + {len(derived_cols)} derived columns")
            else:
                print("  ⚠ Warning: No player slot columns were added")
        except Exception as e:
            print(f"  ✗ Error calculating player slot features: {e}")
            print("    Continuing without player slot features...")
    else:
        print("\n[9/11] Skipping player projection features (--no-player-features flag)")
        print("[10/11] Skipping injury impact features (--no-player-features flag)")
        print("[11/11] Skipping player slot features (--no-player-features flag)")

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
    # Added player projection features: PROJ_*, WEIGHTED_*, ROSTER_*, STAR_*, TOP_3_*
    # Added injury impact features: INJURY_IMPACT
    # Added player slot features: SLOT_*_IMPACT, SLOT_*_AVAILABLE, TOTAL_*_IMPACT, PLAYERS_OUT
    feature_patterns = ['_L5', '_L10', 'STREAK', 'REST_DAYS', 'WIN_PCT',
                        'IS_BACK_TO_BACK', 'IS_3_IN_4_NIGHTS', 'GAMES_LAST',
                        'AVG_REST_LAST', 'ROAD_TRIP_LENGTH',
                        'PROJ_PTS_FROM_PLAYERS', 'PROJ_REB_FROM_PLAYERS', 'PROJ_AST_FROM_PLAYERS',
                        'WEIGHTED_AVG_USAGE', 'WEIGHTED_AVG_TS_PCT', 'WEIGHTED_AVG_PIE',
                        'ROSTER_DEPTH_SCORE', 'STAR_PLAYER_IMPACT', 'TOP_3_SCORER_SHARE',
                        'INJURY_IMPACT',
                        # Player slot features (integrated roster model)
                        '_SLOT_', '_AVAILABLE', '_IMPACT',
                        'TOTAL_AVAILABLE_IMPACT', 'TOTAL_MISSING_IMPACT', 'PLAYERS_OUT']

    # Exclude PLAYER_ID columns - they're for lookup/embedding, not direct features for RF
    # (NN will handle these separately via embedding layer)

    # Get all feature columns
    all_features = []
    for col in matchup_df.columns:
        # Skip PLAYER_ID columns - these are for SHAP interpretation, not model features
        if 'PLAYER_ID' in col:
            continue
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
    import argparse

    parser = argparse.ArgumentParser(description='Generate ML features from NBA game data')
    parser.add_argument('--no-player-features', action='store_true',
                       help='Skip player projection features (faster)')
    parser.add_argument('--include-legacy-injury', action='store_true',
                       help='Include legacy injury impact features (skipped by default)')
    parser.add_argument('--start-date', type=str, default='2022-01-01',
                       help='Start date for data (default: 2022-01-01)')
    parser.add_argument('--end-date', type=str, default='2026-12-31',
                       help='End date for data (default: 2026-12-31)')
    args = parser.parse_args()

    # Create database connection
    engine = create_engine()

    # Build feature dataset
    feature_df = build_feature_dataset(
        engine,
        start_date=args.start_date,
        end_date=args.end_date,
        include_player_features=not args.no_player_features,
        include_legacy_injury_features=args.include_legacy_injury
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
