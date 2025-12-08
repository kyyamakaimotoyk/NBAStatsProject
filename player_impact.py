"""
Player Impact Model
===================

Estimates the impact of player availability on team performance.

Primary Approach: Historical WITH/WITHOUT
- Compare team margin when player plays (20+ min) vs when OUT (DNP/DND/NWT)
- OUT status determined by comment field in boxscoreplayertrackv3_player:
  - DNP = Did Not Play (Coach's Decision, Injury/Illness, Rest)
  - DND = Did Not Dress (Injury/Illness, specific injuries, Rest)
  - NWT = Not With Team (Personal Reasons, Suspension, Illness)
- Based on empirical evaluation showing this outperforms advanced metrics

Fallback Approach: Advanced Metrics (netRating)
- Used when insufficient historical data (<3 games without player)
- Estimates impact as netRating × minutes_share

Validated on 8,823 games (2015-2025):
- Historical MAE: 11.10 pts
- Advanced MAE: 11.88 pts
- Historical correlation: 0.350 (vs 0.138 for Advanced)
"""

import sqlalchemy as sql
from sqlalchemy import text
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import re
from scipy.special import expit  # Logistic function

# Cache for margin-to-probability calibration
_MARGIN_TO_PROB_COEFFICIENT = None


def create_engine():
    """Create database connection."""
    return sql.create_engine('mysql://kaiyamamoto:KN!yoWMhiH8cBvD@localhost:3306/nba_data')


def parse_minutes(minutes_str) -> float:
    """Parse minutes from various formats (PT00M00.00S, MM:SS, or numeric)."""
    if minutes_str is None or pd.isna(minutes_str):
        return 0.0
    if isinstance(minutes_str, (int, float)):
        return float(minutes_str)
    minutes_str = str(minutes_str)
    if minutes_str.startswith('PT'):
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


def get_player_historical_impact(engine, player_id, team_id, as_of_date=None, lookback_days=365):
    """
    Calculate player impact using Historical WITH/WITHOUT approach.

    Args:
        engine: SQLAlchemy engine
        player_id: NBA player ID
        team_id: NBA team ID
        as_of_date: Calculate impact as of this date (for backtesting)
        lookback_days: How far back to look for games

    Returns:
        dict with impact metrics:
        {
            'impact': float,           # Expected margin swing when player is OUT
            'margin_with': float,      # Team margin when player plays
            'margin_without': float,   # Team margin when player is OUT
            'games_with': int,         # Sample size (with player)
            'games_without': int,      # Sample size (without player)
            'confidence': str,         # HIGH/MEDIUM/LOW/INSUFFICIENT
            'method': str              # 'historical' or 'advanced'
        }
    """
    if as_of_date is None:
        as_of_date = datetime.now().strftime('%Y-%m-%d')

    start_date = (datetime.strptime(as_of_date, '%Y-%m-%d') - timedelta(days=lookback_days)).strftime('%Y-%m-%d')

    # Query includes comment field from boxscoreplayertrackv3_player to identify DNP/DND/NWT
    query = f"""
        SELECT
            gl.GAME_ID,
            gl.GAME_DATE,
            gl.PLUS_MINUS as team_margin,
            COALESCE(p.minutes, '0:00') as player_minutes,
            COALESCE(adv.netRating, 0) as player_net_rating,
            COALESCE(adv.PIE, 0) as player_pie,
            track.comment as player_comment
        FROM game_list gl
        LEFT JOIN boxscoretraditionalv3_player p
            ON gl.GAME_ID = p.gameId AND gl.TEAM_ID = p.teamId AND p.personId = {player_id}
        LEFT JOIN boxscoreadvancedv3_player adv
            ON gl.GAME_ID = adv.gameId AND p.personId = adv.personId
        LEFT JOIN boxscoreplayertrackv3_player track
            ON gl.GAME_ID = track.gameId AND p.personId = track.personId
        WHERE gl.TEAM_ID = {team_id}
          AND gl.GAME_DATE >= '{start_date}'
          AND gl.GAME_DATE < '{as_of_date}'
          AND gl.WL IS NOT NULL
        ORDER BY gl.GAME_DATE
    """

    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)

    if len(df) == 0:
        return {
            'impact': 0.0,
            'margin_with': 0.0,
            'margin_without': 0.0,
            'games_with': 0,
            'games_without': 0,
            'confidence': 'INSUFFICIENT',
            'method': 'none'
        }

    # Parse minutes
    df['minutes_float'] = df['player_minutes'].apply(parse_minutes)

    # Identify OUT games using comment field (DNP/DND/NWT)
    def is_out(row):
        comment = row.get('player_comment', '')
        if comment and isinstance(comment, str):
            return comment.startswith('DNP') or comment.startswith('DND') or comment.startswith('NWT')
        return False

    df['is_out'] = df.apply(is_out, axis=1)

    # Split into WITH (20+ min, not OUT) and WITHOUT (OUT via comment)
    games_with = df[(df['minutes_float'] >= 20) & (~df['is_out'])]
    games_without = df[df['is_out']]

    n_with = len(games_with)
    n_without = len(games_without)

    # Calculate margins
    margin_with = games_with['team_margin'].mean() if n_with > 0 else 0.0
    margin_without = games_without['team_margin'].mean() if n_without > 0 else None

    # If we have enough "WITHOUT" games, use Historical approach
    if n_without >= 3:
        impact = margin_with - margin_without
        confidence = 'HIGH' if n_without >= 10 else ('MEDIUM' if n_without >= 5 else 'LOW')
        return {
            'impact': impact,
            'margin_with': margin_with,
            'margin_without': margin_without,
            'games_with': n_with,
            'games_without': n_without,
            'confidence': confidence,
            'method': 'historical'
        }

    # Fallback to Advanced Metrics approach
    games_played = df[df['minutes_float'] >= 15]
    if len(games_played) >= 5:
        avg_net_rating = games_played['player_net_rating'].mean()
        avg_minutes = games_played['minutes_float'].mean()
        minutes_share = avg_minutes / 48.0

        # Estimated impact = netRating * minutes_share
        impact = avg_net_rating * minutes_share

        return {
            'impact': impact,
            'margin_with': margin_with,
            'margin_without': None,
            'games_with': n_with,
            'games_without': n_without,
            'avg_net_rating': avg_net_rating,
            'avg_minutes': avg_minutes,
            'confidence': 'LOW',  # Advanced metrics are less reliable
            'method': 'advanced'
        }

    # Not enough data for either approach
    return {
        'impact': 0.0,
        'margin_with': margin_with,
        'margin_without': None,
        'games_with': n_with,
        'games_without': n_without,
        'confidence': 'INSUFFICIENT',
        'method': 'none'
    }


def get_team_player_impacts(engine, team_id, as_of_date=None, min_minutes=20, min_games=10):
    """
    Get impact estimates for all significant players on a team.

    Args:
        engine: SQLAlchemy engine
        team_id: NBA team ID
        as_of_date: Calculate impacts as of this date
        min_minutes: Minimum average minutes to be considered significant
        min_games: Minimum games played to be considered

    Returns:
        list of dicts with player info and impact:
        [
            {
                'player_id': int,
                'player_name': str,
                'avg_minutes': float,
                'avg_points': float,
                'impact': float,
                'confidence': str,
                'method': str
            },
            ...
        ]
    """
    if as_of_date is None:
        as_of_date = datetime.now().strftime('%Y-%m-%d')

    start_date = (datetime.strptime(as_of_date, '%Y-%m-%d') - timedelta(days=365)).strftime('%Y-%m-%d')

    # Get all players on the team with their stats
    query = f"""
        SELECT
            p.personId,
            p.firstName,
            p.familyName,
            p.minutes,
            p.points
        FROM boxscoretraditionalv3_player p
        JOIN game_list gl ON p.gameId = gl.GAME_ID AND p.teamId = gl.TEAM_ID
        WHERE p.teamId = {team_id}
          AND gl.GAME_DATE >= '{start_date}'
          AND gl.GAME_DATE < '{as_of_date}'
          AND p.minutes IS NOT NULL
          AND p.minutes != ''
    """

    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)

    if len(df) == 0:
        return []

    # Parse minutes
    df['minutes_float'] = df['minutes'].apply(parse_minutes)

    # Aggregate by player
    player_stats = df.groupby(['personId', 'firstName', 'familyName']).agg({
        'minutes_float': ['count', 'mean'],
        'points': 'mean'
    }).reset_index()

    player_stats.columns = ['personId', 'firstName', 'familyName', 'games', 'avg_minutes', 'avg_points']

    # Filter for significant players
    player_stats = player_stats[
        (player_stats['games'] >= min_games) &
        (player_stats['avg_minutes'] >= min_minutes)
    ]

    results = []
    for _, player in player_stats.iterrows():
        impact_data = get_player_historical_impact(
            engine,
            int(player['personId']),
            team_id,
            as_of_date
        )

        results.append({
            'player_id': int(player['personId']),
            'player_name': f"{player['firstName']} {player['familyName']}",
            'avg_minutes': player['avg_minutes'],
            'avg_points': player['avg_points'],
            'games_played': int(player['games']),
            'impact': impact_data['impact'],
            'games_without': impact_data['games_without'],
            'confidence': impact_data['confidence'],
            'method': impact_data['method']
        })

    # Sort by impact (highest first)
    results.sort(key=lambda x: abs(x['impact']), reverse=True)

    return results


def calculate_injury_adjusted_margin(engine, team_id, opponent_id, baseline_margin,
                                      injuries_out=None, as_of_date=None):
    """
    Adjust predicted margin based on player availability.

    Args:
        engine: SQLAlchemy engine
        team_id: Team making prediction for
        opponent_id: Opponent team ID
        baseline_margin: Predicted margin without injury adjustments
        injuries_out: List of player_ids who are OUT
        as_of_date: Date for the game

    Returns:
        dict with:
        {
            'adjusted_margin': float,
            'total_impact': float,
            'player_impacts': list of dicts
        }
    """
    if injuries_out is None:
        injuries_out = []

    if as_of_date is None:
        as_of_date = datetime.now().strftime('%Y-%m-%d')

    player_impacts = []
    total_impact = 0.0

    for player_id in injuries_out:
        impact_data = get_player_historical_impact(engine, player_id, team_id, as_of_date)

        if impact_data['confidence'] != 'INSUFFICIENT':
            player_impacts.append({
                'player_id': player_id,
                'impact': impact_data['impact'],
                'confidence': impact_data['confidence'],
                'method': impact_data['method']
            })
            total_impact += impact_data['impact']

    # Adjusted margin = baseline - total_impact (positive impact means team is worse without player)
    adjusted_margin = baseline_margin - total_impact

    return {
        'adjusted_margin': adjusted_margin,
        'baseline_margin': baseline_margin,
        'total_impact': total_impact,
        'player_impacts': player_impacts
    }


def get_player_id_by_name(engine, player_name, team_id=None):
    """
    Look up player ID by name (fuzzy match).

    Args:
        engine: SQLAlchemy engine
        player_name: Full name or partial name
        team_id: Optional team ID to narrow search

    Returns:
        player_id or None if not found
    """
    # Split name into parts
    name_parts = player_name.strip().split()

    if len(name_parts) >= 2:
        first_name = name_parts[0]
        last_name = ' '.join(name_parts[1:])

        query = f"""
            SELECT DISTINCT personId, firstName, familyName, teamId
            FROM boxscoretraditionalv3_player
            WHERE (firstName LIKE '%{first_name}%' AND familyName LIKE '%{last_name}%')
               OR (firstName LIKE '%{last_name}%' AND familyName LIKE '%{first_name}%')
        """
    else:
        query = f"""
            SELECT DISTINCT personId, firstName, familyName, teamId
            FROM boxscoretraditionalv3_player
            WHERE firstName LIKE '%{player_name}%' OR familyName LIKE '%{player_name}%'
        """

    if team_id:
        query += f" AND teamId = {team_id}"

    query += " LIMIT 10"

    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)

    if len(df) == 0:
        return None

    # Return first match
    return int(df.iloc[0]['personId'])


def print_team_impact_report(engine, team_id, team_name=None, as_of_date=None):
    """
    Print a formatted report of player impacts for a team.
    """
    if as_of_date is None:
        as_of_date = datetime.now().strftime('%Y-%m-%d')

    impacts = get_team_player_impacts(engine, team_id, as_of_date)

    if team_name is None:
        team_name = f"Team {team_id}"

    print(f"\n{'='*70}")
    print(f"PLAYER IMPACT REPORT: {team_name}")
    print(f"As of: {as_of_date}")
    print(f"{'='*70}")

    if not impacts:
        print("No significant players found.")
        return

    print(f"\n{'Player':<25} {'MPG':>6} {'PPG':>6} {'Impact':>8} {'Conf':>8} {'Method':>10}")
    print("-" * 70)

    for p in impacts:
        # Handle non-ASCII characters in player names
        player_name = p['player_name'].encode('ascii', 'replace').decode('ascii')
        print(f"{player_name:<25} {p['avg_minutes']:>6.1f} {p['avg_points']:>6.1f} "
              f"{p['impact']:>+8.1f} {p['confidence']:>8} {p['method']:>10}")

    print("-" * 70)
    print(f"Impact = expected margin change if player is OUT")
    print(f"Positive impact means team performs WORSE without player")


# Example usage
if __name__ == '__main__':
    engine = create_engine()

    # Example: Lakers (team_id 1610612747)
    print_team_impact_report(engine, 1610612747, "Los Angeles Lakers")

    # Example: Get LeBron's impact
    lebron_id = get_player_id_by_name(engine, "LeBron James")
    if lebron_id:
        impact = get_player_historical_impact(engine, lebron_id, 1610612747)
        print(f"\nLeBron James Impact: {impact}")

    engine.dispose()
