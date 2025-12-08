"""
Evaluate Player Impact Approaches
=================================

Compare two approaches for estimating player impact:
  A: Historical WITH/WITHOUT (team-specific)
  B: Advanced Metrics (netRating, PIE - player-specific)

Methodology:
1. Find games where a "significant player" was OUT (played <10 min)
2. For each such game, predict the team's margin using both approaches
3. Compare predictions to actual margin
4. Calculate MAE and RMSE for each approach
"""

import sqlalchemy as sql
from sqlalchemy import text
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from joblib import Parallel, delayed
import os


def create_engine():
    """Create database connection."""
    return sql.create_engine('mysql://kaiyamamoto:KN!yoWMhiH8cBvD@localhost:3306/nba_data')


def parse_minutes(minutes_str) -> float:
    """Parse minutes from various formats."""
    if minutes_str is None or pd.isna(minutes_str):
        return 0.0
    if isinstance(minutes_str, (int, float)):
        return float(minutes_str)
    minutes_str = str(minutes_str)
    if minutes_str.startswith('PT'):
        import re
        match = re.match(r'PT(\d+)M(\d+(?:\.\d+)?)S', minutes_str)
        if match:
            return float(match.group(1)) + float(match.group(2)) / 60
        return 0.0
    if ':' in minutes_str:
        try:
            parts = minutes_str.split(':')
            return float(parts[0]) + float(parts[1]) / 60
        except:
            return 0.0
    try:
        return float(minutes_str)
    except:
        return 0.0


def get_significant_players(engine, min_games=20, min_mpg=25.0, season_start='2023-10-01'):
    """
    Get players who are 'significant' (starters with high minutes).
    These are players whose absence would meaningfully impact the team.
    """
    # Step 1: Get raw player data (faster query without string parsing in SQL)
    query = f"""
        SELECT
            p.personId,
            p.teamId,
            p.firstName,
            p.familyName,
            p.minutes,
            p.points,
            adv.netRating,
            adv.PIE
        FROM boxscoretraditionalv3_player p
        JOIN boxscoreadvancedv3_player adv
            ON p.gameId = adv.gameId AND p.personId = adv.personId
        JOIN game_list gl
            ON p.gameId = gl.GAME_ID AND p.teamId = gl.TEAM_ID
        WHERE gl.GAME_DATE >= '{season_start}'
          AND p.minutes IS NOT NULL
          AND p.minutes != ''
          AND p.minutes != 'PT00M00.00S'
    """

    print("  Loading player data...")
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)

    print(f"  Loaded {len(df)} player-game records")

    # Step 2: Parse minutes in pandas (faster than SQL)
    df['minutes_float'] = df['minutes'].apply(parse_minutes)

    # Step 3: Aggregate by player
    print("  Aggregating by player...")
    agg = df.groupby(['personId', 'teamId', 'firstName', 'familyName']).agg({
        'minutes_float': ['count', 'mean'],
        'points': 'mean',
        'netRating': 'mean',
        'PIE': 'mean'
    }).reset_index()

    agg.columns = ['personId', 'teamId', 'firstName', 'familyName',
                   'games_played', 'avg_minutes', 'avg_points', 'avg_net_rating', 'avg_pie']

    # Filter for significant players
    agg = agg[(agg['games_played'] >= min_games) & (agg['avg_minutes'] >= min_mpg)]
    agg = agg.sort_values('avg_minutes', ascending=False)

    print(f"  Found {len(agg)} significant players")
    return agg


def get_player_games(engine, player_id, team_id, season_start='2023-10-01'):
    """
    Get all games for a player, including games where they didn't play.
    """
    query = f"""
        SELECT
            gl.GAME_ID,
            gl.GAME_DATE,
            gl.TEAM_ID,
            gl.PLUS_MINUS as team_margin,
            gl.PTS as team_pts,
            gl.WL,
            COALESCE(p.minutes, '0:00') as player_minutes,
            COALESCE(p.points, 0) as player_points,
            COALESCE(adv.netRating, 0) as player_net_rating,
            COALESCE(adv.PIE, 0) as player_pie
        FROM game_list gl
        LEFT JOIN boxscoretraditionalv3_player p
            ON gl.GAME_ID = p.gameId AND gl.TEAM_ID = p.teamId AND p.personId = {player_id}
        LEFT JOIN boxscoreadvancedv3_player adv
            ON gl.GAME_ID = adv.gameId AND p.personId = adv.personId
        WHERE gl.TEAM_ID = {team_id}
          AND gl.GAME_DATE >= '{season_start}'
          AND gl.WL IS NOT NULL
        ORDER BY gl.GAME_DATE
    """

    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)

    df['player_minutes_float'] = df['player_minutes'].apply(parse_minutes)

    return df


def calculate_historical_impact(games_df, min_games_without=3):
    """
    Approach A: Calculate impact from historical WITH vs WITHOUT games.

    Returns:
        dict with 'impact', 'games_with', 'games_without', 'confidence'
    """
    games_with = games_df[games_df['player_minutes_float'] >= 20]
    games_without = games_df[games_df['player_minutes_float'] < 10]

    if len(games_without) < min_games_without:
        return {
            'impact': None,
            'games_with': len(games_with),
            'games_without': len(games_without),
            'margin_with': games_with['team_margin'].mean() if len(games_with) > 0 else 0,
            'margin_without': None,
            'confidence': 'INSUFFICIENT_DATA'
        }

    margin_with = games_with['team_margin'].mean()
    margin_without = games_without['team_margin'].mean()
    impact = margin_with - margin_without

    return {
        'impact': impact,
        'games_with': len(games_with),
        'games_without': len(games_without),
        'margin_with': margin_with,
        'margin_without': margin_without,
        'confidence': 'HIGH' if len(games_without) >= 5 else 'MEDIUM'
    }


def calculate_advanced_metric_impact(games_df):
    """
    Approach B: Estimate impact from advanced metrics (netRating).

    netRating = team's point differential per 100 possessions while player is on court
    This is a proxy for the player's impact.

    Returns:
        dict with 'impact', 'avg_net_rating', 'avg_pie'
    """
    # Only use games where player actually played significant minutes
    games_with_player = games_df[games_df['player_minutes_float'] >= 15]

    if len(games_with_player) < 5:
        return {
            'impact': None,
            'avg_net_rating': None,
            'avg_pie': None,
            'confidence': 'INSUFFICIENT_DATA'
        }

    avg_net_rating = games_with_player['player_net_rating'].mean()
    avg_pie = games_with_player['player_pie'].mean()

    # Convert netRating to expected margin impact
    # netRating is per 100 possessions, a game has ~100 possessions
    # so netRating ≈ expected point differential when on court
    # But player only plays ~35 of 48 minutes, so scale by minutes share
    avg_minutes = games_with_player['player_minutes_float'].mean()
    minutes_share = avg_minutes / 48.0

    # Estimated impact = netRating * minutes_share
    # This estimates how many points the player adds to team margin per game
    impact = avg_net_rating * minutes_share

    return {
        'impact': impact,
        'avg_net_rating': avg_net_rating,
        'avg_pie': avg_pie,
        'avg_minutes': avg_minutes,
        'minutes_share': minutes_share,
        'confidence': 'HIGH' if len(games_with_player) >= 20 else 'MEDIUM'
    }


def load_all_game_data(engine, player_ids, team_ids, season_start='2023-10-01'):
    """
    Load all game data for all players in a single query.
    Much faster than querying per-player.
    """
    # Build list of (player_id, team_id) tuples for query
    player_team_pairs = list(zip(player_ids, team_ids))

    # Create a temp table approach or use IN clause
    player_ids_str = ','.join(str(int(p)) for p in player_ids)
    team_ids_str = ','.join(str(int(t)) for t in team_ids)

    query = f"""
        SELECT
            gl.GAME_ID,
            gl.GAME_DATE,
            gl.TEAM_ID,
            gl.PLUS_MINUS as team_margin,
            gl.PTS as team_pts,
            gl.WL,
            p.personId as player_id,
            COALESCE(p.minutes, '0:00') as player_minutes,
            COALESCE(p.points, 0) as player_points,
            COALESCE(adv.netRating, 0) as player_net_rating,
            COALESCE(adv.PIE, 0) as player_pie
        FROM game_list gl
        CROSS JOIN (
            SELECT DISTINCT personId, teamId
            FROM boxscoretraditionalv3_player
            WHERE personId IN ({player_ids_str})
        ) players
        LEFT JOIN boxscoretraditionalv3_player p
            ON gl.GAME_ID = p.gameId AND gl.TEAM_ID = p.teamId AND p.personId = players.personId
        LEFT JOIN boxscoreadvancedv3_player adv
            ON gl.GAME_ID = adv.gameId AND p.personId = adv.personId
        WHERE gl.TEAM_ID = players.teamId
          AND gl.GAME_DATE >= '{season_start}'
          AND gl.WL IS NOT NULL
        ORDER BY players.personId, gl.GAME_DATE
    """

    print("  Loading all game data in single query...", flush=True)
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)

    print(f"  Loaded {len(df)} total game records", flush=True)

    # Parse minutes
    df['player_minutes_float'] = df['player_minutes'].apply(parse_minutes)

    return df


def evaluate_single_player(player_data, all_games_df):
    """
    Evaluate a single player (designed for parallel execution).
    Returns list of result dicts.
    """
    player_id = player_data['personId']
    team_id = player_data['teamId']
    player_name = f"{player_data['firstName']} {player_data['familyName']}"

    # Filter games for this player/team
    games_df = all_games_df[
        (all_games_df['player_id'] == player_id) &
        (all_games_df['TEAM_ID'] == team_id)
    ].copy()

    if len(games_df) < 10:
        return []

    # Calculate impacts using both approaches
    historical = calculate_historical_impact(games_df)
    advanced = calculate_advanced_metric_impact(games_df)

    # Skip if we don't have enough "OUT" games to evaluate
    games_out = games_df[games_df['player_minutes_float'] < 10]
    if len(games_out) < 3:
        return []

    # Get baseline (team margin when player plays)
    games_in = games_df[games_df['player_minutes_float'] >= 20]
    baseline_margin = games_in['team_margin'].mean() if len(games_in) > 0 else 0

    results = []
    # For each "OUT" game, predict margin and compare to actual
    for _, game in games_out.iterrows():
        actual_margin = game['team_margin']

        # Approach A: Historical - predict margin = baseline - historical_impact
        if historical['impact'] is not None:
            pred_a = baseline_margin - historical['impact']
            error_a = abs(pred_a - actual_margin)
        else:
            pred_a = None
            error_a = None

        # Approach B: Advanced metrics - predict margin = baseline - advanced_impact
        if advanced['impact'] is not None:
            pred_b = baseline_margin - advanced['impact']
            error_b = abs(pred_b - actual_margin)
        else:
            pred_b = None
            error_b = None

        results.append({
            'player_name': player_name,
            'player_id': player_id,
            'team_id': team_id,
            'game_id': game['GAME_ID'],
            'game_date': game['GAME_DATE'],
            'actual_margin': actual_margin,
            'baseline_margin': baseline_margin,
            'historical_impact': historical['impact'],
            'historical_games_without': historical['games_without'],
            'advanced_impact': advanced['impact'],
            'advanced_net_rating': advanced.get('avg_net_rating'),
            'pred_historical': pred_a,
            'pred_advanced': pred_b,
            'error_historical': error_a,
            'error_advanced': error_b,
        })

    return results


def evaluate_approaches(engine, players_df, season_start='2023-10-01'):
    """
    Main evaluation function (parallelized).

    For each significant player with enough "OUT" games:
    1. Calculate impact using both approaches
    2. For each "OUT" game, predict team margin
    3. Compare to actual margin
    """
    # Load all game data at once
    player_ids = players_df['personId'].tolist()
    team_ids = players_df['teamId'].tolist()
    all_games_df = load_all_game_data(engine, player_ids, team_ids, season_start)

    # Convert players to list of dicts for parallel processing
    players_list = players_df.to_dict('records')

    # Determine number of workers
    n_jobs = min(os.cpu_count() or 4, len(players_list))
    print(f"  Processing {len(players_list)} players with {n_jobs} workers...", flush=True)

    # Process players in parallel
    all_results = Parallel(n_jobs=n_jobs, prefer="threads")(
        delayed(evaluate_single_player)(player, all_games_df)
        for player in players_list
    )

    # Flatten results
    results = [r for player_results in all_results for r in player_results]

    return pd.DataFrame(results)


def summarize_results(results_df):
    """Calculate summary statistics for each approach."""

    # Filter to games where both approaches have predictions
    both_valid = results_df[
        results_df['error_historical'].notna() &
        results_df['error_advanced'].notna()
    ]

    print("=" * 70)
    print("EVALUATION RESULTS: Historical vs Advanced Metrics Approach")
    print("=" * 70)

    print(f"\nTotal 'OUT' games evaluated: {len(results_df)}")
    print(f"Games with both approaches valid: {len(both_valid)}")

    if len(both_valid) > 0:
        print("\n--- Approach A: Historical WITH/WITHOUT ---")
        mae_a = both_valid['error_historical'].mean()
        rmse_a = np.sqrt((both_valid['error_historical'] ** 2).mean())
        print(f"  MAE:  {mae_a:.2f} points")
        print(f"  RMSE: {rmse_a:.2f} points")

        print("\n--- Approach B: Advanced Metrics (netRating) ---")
        mae_b = both_valid['error_advanced'].mean()
        rmse_b = np.sqrt((both_valid['error_advanced'] ** 2).mean())
        print(f"  MAE:  {mae_b:.2f} points")
        print(f"  RMSE: {rmse_b:.2f} points")

        print("\n--- Comparison ---")
        if mae_a < mae_b:
            print(f"  Historical approach is better by {mae_b - mae_a:.2f} points MAE")
        else:
            print(f"  Advanced metrics approach is better by {mae_a - mae_b:.2f} points MAE")

        # Correlation with actual margin
        corr_a = both_valid['pred_historical'].corr(both_valid['actual_margin'])
        corr_b = both_valid['pred_advanced'].corr(both_valid['actual_margin'])
        print(f"\n  Correlation with actual margin:")
        print(f"    Historical: {corr_a:.3f}")
        print(f"    Advanced:   {corr_b:.3f}")

    # Breakdown by sample size
    print("\n--- Breakdown by Historical Sample Size ---")
    for min_games in [3, 5, 10]:
        subset = results_df[results_df['historical_games_without'] >= min_games]
        subset = subset[subset['error_historical'].notna() & subset['error_advanced'].notna()]
        if len(subset) > 0:
            mae_a = subset['error_historical'].mean()
            mae_b = subset['error_advanced'].mean()
            print(f"\n  With {min_games}+ 'WITHOUT' games ({len(subset)} samples):")
            print(f"    Historical MAE: {mae_a:.2f}")
            print(f"    Advanced MAE:   {mae_b:.2f}")
            winner = "Historical" if mae_a < mae_b else "Advanced"
            print(f"    Winner: {winner}")

    return both_valid


def main():
    print("Connecting to database...", flush=True)
    engine = create_engine()

    # Use data from 2015 to now for comprehensive evaluation
    season_start = '2015-10-01'  # ~10 seasons of data

    print(f"Finding significant players (since {season_start})...", flush=True)
    players = get_significant_players(engine, min_games=20, min_mpg=25.0, season_start=season_start)
    print(f"Found {len(players)} significant players", flush=True)

    print("\nEvaluating approaches (this may take a minute)...", flush=True)
    results = evaluate_approaches(engine, players, season_start=season_start)

    print(f"\nCollected {len(results)} evaluation samples")

    if len(results) > 0:
        summary = summarize_results(results)

        # Save detailed results
        results.to_csv('impact_evaluation_results.csv', index=False)
        print("\nDetailed results saved to: impact_evaluation_results.csv")

        # Show some example predictions
        print("\n" + "=" * 70)
        print("SAMPLE PREDICTIONS (first 10 games)")
        print("=" * 70)
        sample = results.head(10)
        for _, row in sample.iterrows():
            print(f"\n{row['player_name']} OUT on {row['game_date']}")
            print(f"  Actual margin: {row['actual_margin']:+.0f}")
            print(f"  Baseline (with player): {row['baseline_margin']:+.1f}")
            if row['pred_historical'] is not None:
                print(f"  Predicted (Historical): {row['pred_historical']:+.1f} (error: {row['error_historical']:.1f})")
            if row['pred_advanced'] is not None:
                print(f"  Predicted (Advanced):   {row['pred_advanced']:+.1f} (error: {row['error_advanced']:.1f})")

    engine.dispose()
    print("\nDone!")


if __name__ == '__main__':
    main()
