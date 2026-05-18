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

# Project-root bootstrap so cross-folder imports (core.db, ...) work regardless of CWD.
import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

import sqlalchemy as sql
from sqlalchemy import text
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import re
from scipy.special import expit  # Logistic function

# Cache for margin-to-probability calibration
_MARGIN_TO_PROB_COEFFICIENT = None

# =============================================================================
# CONFIGURABLE WEIGHTS FOR PLAYER IMPACT MODEL
# These can be tuned through empirical testing/backtesting
# =============================================================================

# Player importance weighting (addresses selection bias for role players)
MINUTES_WEIGHT = 0.5          # Weight for minutes share in importance calculation
USAGE_WEIGHT = 0.5            # Weight for usage rate in importance calculation
MAX_USAGE_RATE = 0.35         # Maximum realistic usage rate for normalization
BASELINE_IMPORTANCE = 0.35    # Normalization baseline (typical rotation player)

# Time decay for consecutive games without player (team adaptation)
TIME_DECAY_FACTOR = 0.85      # Decay multiplier per consecutive game out

# Confidence level weights
CONFIDENCE_WEIGHTS = {
    'HIGH': 1.0,              # 10+ games without player
    'MEDIUM': 0.7,            # 5-9 games without player
    'LOW': 0.4,               # 3-4 games without player (or advanced method)
    'INSUFFICIENT': 0.0       # Not enough data
}

# Minimum sample sizes to avoid garbage-time bias
MIN_GAMES_WITH = 5            # Minimum games with 20+ min to use historical method


def create_engine():
    """Create database connection. Reads MySQL config from environment via db.get_engine()."""
    from core.db import get_engine
    return get_engine()


def _calculate_streak_positions(df, is_out_column='is_out'):
    """
    Calculate position within consecutive OUT streaks for time decay.

    For each OUT game, determines its position in the current streak:
    - First game out: position = 1
    - Second consecutive game out: position = 2
    - etc.

    Resets when player returns (plays a game).

    Args:
        df: DataFrame with games sorted by date, containing is_out column
        is_out_column: Name of boolean column indicating OUT status

    Returns:
        Series with streak position for each row (0 for non-OUT games)
    """
    positions = []
    current_streak = 0

    for is_out in df[is_out_column]:
        if is_out:
            current_streak += 1
            positions.append(current_streak)
        else:
            current_streak = 0
            positions.append(0)

    return pd.Series(positions, index=df.index)


def _calculate_importance_weight(avg_minutes, avg_usage):
    """
    Calculate player importance weight based on minutes and usage.

    Args:
        avg_minutes: Player's average minutes per game
        avg_usage: Player's average usage percentage (0.0 to ~0.35)

    Returns:
        importance_multiplier: Factor to scale raw impact (>1 for stars, <1 for role players)
    """
    # Normalize minutes to 0-1 scale (48 min = full game)
    minutes_share = min(avg_minutes / 48.0, 1.0)

    # Normalize usage to 0-1 scale (MAX_USAGE_RATE = realistic max)
    normalized_usage = min(avg_usage / MAX_USAGE_RATE, 1.0) if avg_usage else 0.0

    # Combine with configurable weights
    importance_weight = (minutes_share * MINUTES_WEIGHT) + (normalized_usage * USAGE_WEIGHT)

    # Scale relative to baseline (typical rotation player)
    importance_multiplier = importance_weight / BASELINE_IMPORTANCE if BASELINE_IMPORTANCE > 0 else 1.0

    return importance_multiplier


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
    Calculate player impact using Historical WITH/WITHOUT approach with importance weighting.

    Args:
        engine: SQLAlchemy engine
        player_id: NBA player ID
        team_id: NBA team ID
        as_of_date: Calculate impact as of this date (for backtesting)
        lookback_days: How far back to look for games

    Returns:
        dict with impact metrics:
        {
            'raw_impact': float,       # Raw margin swing before weighting
            'impact': float,           # Weighted impact (importance-adjusted)
            'margin_with': float,      # Team margin when player plays
            'margin_without': float,   # Team margin when player is OUT (with time decay)
            'games_with': int,         # Sample size (with player)
            'games_without': int,      # Sample size (without player)
            'confidence': str,         # HIGH/MEDIUM/LOW/INSUFFICIENT
            'method': str,             # 'historical' or 'advanced'
            'avg_minutes': float,      # Player's average minutes
            'avg_usage': float,        # Player's average usage rate
            'importance_multiplier': float,  # Importance weight applied
            'decay_applied': bool      # Whether time decay was applied
        }
    """
    if as_of_date is None:
        as_of_date = datetime.now().strftime('%Y-%m-%d')

    start_date = (datetime.strptime(as_of_date, '%Y-%m-%d') - timedelta(days=lookback_days)).strftime('%Y-%m-%d')

    # Query includes comment field and usage percentage
    # Note: 'usage' is a MySQL reserved word, so we alias the table as 'usg'
    query = f"""
        SELECT
            gl.GAME_ID,
            gl.GAME_DATE,
            gl.PLUS_MINUS as team_margin,
            COALESCE(p.minutes, '0:00') as player_minutes,
            COALESCE(adv.netRating, 0) as player_net_rating,
            COALESCE(adv.PIE, 0) as player_pie,
            track.comment as player_comment,
            usg.usagePercentage as player_usage
        FROM game_list gl
        LEFT JOIN boxscoretraditionalv3_player p
            ON gl.GAME_ID = p.gameId AND gl.TEAM_ID = p.teamId AND p.personId = {player_id}
        LEFT JOIN boxscoreadvancedv3_player adv
            ON gl.GAME_ID = adv.gameId AND p.personId = adv.personId
        LEFT JOIN boxscoreplayertrackv3_player track
            ON gl.GAME_ID = track.gameId AND track.personId = {player_id}
        LEFT JOIN boxscoreusagev3_player usg
            ON gl.GAME_ID = usg.gameId AND usg.personId = {player_id}
        WHERE gl.TEAM_ID = {team_id}
          AND gl.GAME_DATE >= '{start_date}'
          AND gl.GAME_DATE < '{as_of_date}'
          AND gl.WL IS NOT NULL
        ORDER BY gl.GAME_DATE
    """

    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)

    # Default return for no data
    default_return = {
        'raw_impact': 0.0,
        'impact': 0.0,
        'margin_with': 0.0,
        'margin_without': 0.0,
        'games_with': 0,
        'games_without': 0,
        'confidence': 'INSUFFICIENT',
        'method': 'none',
        'avg_minutes': 0.0,
        'avg_usage': 0.0,
        'importance_multiplier': 1.0,
        'decay_applied': False
    }

    if len(df) == 0:
        return default_return

    # Parse minutes
    df['minutes_float'] = df['player_minutes'].apply(parse_minutes)

    # Identify OUT games using comment field (DNP/DND/NWT)
    def is_out(row):
        comment = row.get('player_comment', '')
        if comment and isinstance(comment, str):
            return comment.startswith('DNP') or comment.startswith('DND') or comment.startswith('NWT')
        return False

    df['is_out'] = df.apply(is_out, axis=1)

    # Calculate streak positions for time decay
    df['streak_position'] = _calculate_streak_positions(df, 'is_out')

    # Split into WITH (20+ min, not OUT) and WITHOUT (OUT via comment)
    games_with = df[(df['minutes_float'] >= 20) & (~df['is_out'])]
    games_without = df[df['is_out']]

    n_with = len(games_with)
    n_without = len(games_without)

    # Calculate player's average minutes and usage (from games played)
    games_played = df[df['minutes_float'] >= 15]
    avg_minutes = games_played['minutes_float'].mean() if len(games_played) > 0 else 0.0
    avg_usage = games_played['player_usage'].mean() if len(games_played) > 0 else 0.0
    if pd.isna(avg_usage):
        avg_usage = 0.0

    # Calculate importance multiplier
    importance_multiplier = _calculate_importance_weight(avg_minutes, avg_usage)

    # Calculate margins
    margin_with = games_with['team_margin'].mean() if n_with > 0 else 0.0

    # Calculate margin_without with time decay
    decay_applied = False
    margin_without = None
    if n_without > 0:
        # Apply time decay: weight = TIME_DECAY_FACTOR^(position-1)
        # First game in streak: weight=1.0, second: 0.85, third: 0.72, etc.
        games_without = games_without.copy()
        games_without['decay_weight'] = games_without['streak_position'].apply(
            lambda pos: TIME_DECAY_FACTOR ** (pos - 1) if pos > 0 else 1.0
        )

        # Check if any decay was actually applied (i.e., any streak > 1)
        if (games_without['streak_position'] > 1).any():
            decay_applied = True

        # Weighted average
        total_weight = games_without['decay_weight'].sum()
        if total_weight > 0:
            margin_without = (games_without['team_margin'] * games_without['decay_weight']).sum() / total_weight
        else:
            margin_without = games_without['team_margin'].mean()

    # Determine if we can use Historical approach
    # Requires: n_without >= 3 AND n_with >= MIN_GAMES_WITH (to avoid garbage-time bias)
    if n_without >= 3 and n_with >= MIN_GAMES_WITH:
        raw_impact = margin_with - margin_without
        weighted_impact = raw_impact * importance_multiplier
        confidence = 'HIGH' if n_without >= 10 else ('MEDIUM' if n_without >= 5 else 'LOW')

        return {
            'raw_impact': raw_impact,
            'impact': weighted_impact,
            'margin_with': margin_with,
            'margin_without': margin_without,
            'games_with': n_with,
            'games_without': n_without,
            'confidence': confidence,
            'method': 'historical',
            'avg_minutes': avg_minutes,
            'avg_usage': avg_usage,
            'importance_multiplier': importance_multiplier,
            'decay_applied': decay_applied
        }

    # Fallback to Advanced Metrics approach
    if len(games_played) >= 5:
        avg_net_rating = games_played['player_net_rating'].mean()
        minutes_share = avg_minutes / 48.0

        # Estimated raw impact = netRating * minutes_share
        raw_impact = avg_net_rating * minutes_share
        weighted_impact = raw_impact * importance_multiplier

        return {
            'raw_impact': raw_impact,
            'impact': weighted_impact,
            'margin_with': margin_with,
            'margin_without': margin_without,
            'games_with': n_with,
            'games_without': n_without,
            'avg_net_rating': avg_net_rating,
            'confidence': 'LOW',  # Advanced metrics are less reliable
            'method': 'advanced',
            'avg_minutes': avg_minutes,
            'avg_usage': avg_usage,
            'importance_multiplier': importance_multiplier,
            'decay_applied': decay_applied
        }

    # Not enough data for either approach
    return {
        'raw_impact': 0.0,
        'impact': 0.0,
        'margin_with': margin_with,
        'margin_without': margin_without,
        'games_with': n_with,
        'games_without': n_without,
        'confidence': 'INSUFFICIENT',
        'method': 'none',
        'avg_minutes': avg_minutes,
        'avg_usage': avg_usage,
        'importance_multiplier': importance_multiplier,
        'decay_applied': False
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
            'avg_usage': impact_data.get('avg_usage', 0.0),
            'games_played': int(player['games']),
            'raw_impact': impact_data.get('raw_impact', impact_data['impact']),
            'impact': impact_data['impact'],  # Importance-weighted impact
            'importance_multiplier': impact_data.get('importance_multiplier', 1.0),
            'games_with': impact_data['games_with'],
            'games_without': impact_data['games_without'],
            'confidence': impact_data['confidence'],
            'method': impact_data['method'],
            'decay_applied': impact_data.get('decay_applied', False)
        })

    # Sort by weighted impact (highest first)
    results.sort(key=lambda x: abs(x['impact']), reverse=True)

    return results


def calculate_injury_adjusted_margin(engine, team_id, opponent_id, baseline_margin,
                                      injuries_out=None, as_of_date=None):
    """
    Adjust predicted margin based on player availability.

    Applies confidence weighting to player impacts:
    - HIGH confidence: 100% weight
    - MEDIUM confidence: 70% weight
    - LOW confidence: 40% weight
    - INSUFFICIENT: 0% weight (excluded)

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
            'total_impact': float,           # Sum of confidence-weighted impacts
            'total_raw_impact': float,       # Sum of raw (unweighted) impacts
            'player_impacts': list of dicts  # Details per player
        }
    """
    if injuries_out is None:
        injuries_out = []

    if as_of_date is None:
        as_of_date = datetime.now().strftime('%Y-%m-%d')

    player_impacts = []
    total_impact = 0.0
    total_raw_impact = 0.0

    for player_id in injuries_out:
        impact_data = get_player_historical_impact(engine, player_id, team_id, as_of_date)

        if impact_data['confidence'] != 'INSUFFICIENT':
            # Get confidence weight
            conf_weight = CONFIDENCE_WEIGHTS.get(impact_data['confidence'], 0.0)

            # The impact from get_player_historical_impact is already importance-weighted
            # Now apply confidence weight on top
            importance_weighted_impact = impact_data['impact']
            confidence_weighted_impact = importance_weighted_impact * conf_weight

            player_impacts.append({
                'player_id': player_id,
                'raw_impact': impact_data.get('raw_impact', impact_data['impact']),
                'importance_weighted_impact': importance_weighted_impact,
                'confidence_weighted_impact': confidence_weighted_impact,
                'impact': confidence_weighted_impact,  # Final impact used
                'confidence': impact_data['confidence'],
                'confidence_weight': conf_weight,
                'method': impact_data['method'],
                'avg_minutes': impact_data.get('avg_minutes', 0.0),
                'avg_usage': impact_data.get('avg_usage', 0.0),
                'importance_multiplier': impact_data.get('importance_multiplier', 1.0)
            })

            total_impact += confidence_weighted_impact
            total_raw_impact += impact_data.get('raw_impact', impact_data['impact'])

    # Adjusted margin = baseline - total_impact (positive impact means team is worse without player)
    adjusted_margin = baseline_margin - total_impact

    return {
        'adjusted_margin': adjusted_margin,
        'baseline_margin': baseline_margin,
        'total_impact': total_impact,
        'total_raw_impact': total_raw_impact,
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
    # Escape single quotes for SQL (e.g., "N'Faly" -> "N''Faly")
    def escape_sql(s):
        return s.replace("'", "''")

    # Split name into parts
    name_parts = player_name.strip().split()

    if len(name_parts) >= 2:
        first_name = escape_sql(name_parts[0])
        last_name = escape_sql(' '.join(name_parts[1:]))

        query = f"""
            SELECT DISTINCT personId, firstName, familyName, teamId
            FROM boxscoretraditionalv3_player
            WHERE (firstName LIKE '%{first_name}%' AND familyName LIKE '%{last_name}%')
               OR (firstName LIKE '%{last_name}%' AND familyName LIKE '%{first_name}%')
        """
    else:
        escaped_name = escape_sql(player_name)
        query = f"""
            SELECT DISTINCT personId, firstName, familyName, teamId
            FROM boxscoretraditionalv3_player
            WHERE firstName LIKE '%{escaped_name}%' OR familyName LIKE '%{escaped_name}%'
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


def print_team_impact_report(engine, team_id, team_name=None, as_of_date=None, verbose=False):
    """
    Print a formatted report of player impacts for a team.

    Args:
        engine: SQLAlchemy engine
        team_id: NBA team ID
        team_name: Display name for team (optional)
        as_of_date: Calculate impacts as of this date
        verbose: If True, show detailed weighting information
    """
    if as_of_date is None:
        as_of_date = datetime.now().strftime('%Y-%m-%d')

    impacts = get_team_player_impacts(engine, team_id, as_of_date)

    if team_name is None:
        team_name = f"Team {team_id}"

    print(f"\n{'='*90}")
    print(f"PLAYER IMPACT REPORT: {team_name}")
    print(f"As of: {as_of_date}")
    print(f"{'='*90}")

    if not impacts:
        print("No significant players found.")
        return

    if verbose:
        # Detailed view with raw impact and weighting
        print(f"\n{'Player':<22} {'MPG':>5} {'USG%':>5} {'Raw':>7} {'Mult':>5} {'Wtd':>7} {'Conf':>6} {'Method':>8}")
        print("-" * 90)

        for p in impacts:
            player_name = p['player_name'].encode('ascii', 'replace').decode('ascii')[:21]
            usage_pct = p.get('avg_usage', 0) * 100
            raw_impact = p.get('raw_impact', p['impact'])
            mult = p.get('importance_multiplier', 1.0)
            decay_marker = '*' if p.get('decay_applied', False) else ''

            print(f"{player_name:<22} {p['avg_minutes']:>5.1f} {usage_pct:>5.1f} "
                  f"{raw_impact:>+7.1f} {mult:>5.2f} {p['impact']:>+7.1f} "
                  f"{p['confidence']:>6} {p['method']:>8}{decay_marker}")

        print("-" * 90)
        print("Raw = unweighted impact | Mult = importance multiplier | Wtd = weighted impact")
        print("* = time decay applied for consecutive games out")
    else:
        # Simple view
        print(f"\n{'Player':<25} {'MPG':>6} {'PPG':>6} {'Impact':>8} {'Conf':>8} {'Method':>10}")
        print("-" * 70)

        for p in impacts:
            player_name = p['player_name'].encode('ascii', 'replace').decode('ascii')
            print(f"{player_name:<25} {p['avg_minutes']:>6.1f} {p['avg_points']:>6.1f} "
                  f"{p['impact']:>+8.1f} {p['confidence']:>8} {p['method']:>10}")

        print("-" * 70)

    print(f"\nImpact = expected margin change if player is OUT (importance-weighted)")
    print(f"Positive impact means team performs WORSE without player")
    print(f"\nConfig: MIN_WEIGHT={MINUTES_WEIGHT}, USG_WEIGHT={USAGE_WEIGHT}, "
          f"DECAY={TIME_DECAY_FACTOR}, BASELINE={BASELINE_IMPORTANCE}")


# =============================================================================
# PLAYER IMPACT LOOKUP TABLE (SQL)
# =============================================================================

def ensure_player_impact_table(engine):
    """
    Create the player_impact table if it doesn't exist.

    Schema:
        player_id: INT - NBA player ID (from personId)
        team_id: INT - Team ID the player is on
        compute_date: DATE - Date the impact was computed (for trend analysis)
        player_name: VARCHAR - Full player name for convenience
        impact: FLOAT - Weighted impact score (margin swing when OUT)
        raw_impact: FLOAT - Unweighted impact score
        confidence: VARCHAR - HIGH/MEDIUM/LOW/INSUFFICIENT
        method: VARCHAR - 'historical' or 'advanced'
        games_with: INT - Sample size (games with player)
        games_without: INT - Sample size (games without player)
        avg_minutes: FLOAT - Player's average minutes
        avg_usage: FLOAT - Player's average usage rate
        importance_multiplier: FLOAT - Importance weight applied

    Primary key: (player_id, team_id, compute_date)
    """
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS player_impact (
        player_id BIGINT NOT NULL,
        team_id BIGINT NOT NULL,
        compute_date DATE NOT NULL,
        player_name VARCHAR(100),
        impact FLOAT,
        raw_impact FLOAT,
        confidence VARCHAR(20),
        method VARCHAR(20),
        games_with INT,
        games_without INT,
        avg_minutes FLOAT,
        avg_usage FLOAT,
        importance_multiplier FLOAT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (player_id, team_id, compute_date),
        INDEX idx_player_impact_team_date (team_id, compute_date),
        INDEX idx_player_impact_date (compute_date),
        INDEX idx_player_impact_player (player_id)
    )
    """
    with engine.connect() as conn:
        conn.execute(text(create_table_sql))
        conn.commit()
    print("player_impact table ensured.")


def get_cached_player_impact(engine, player_id, team_id, as_of_date=None):
    """
    Get player impact from the cache table.

    Returns the most recent impact computed on or before as_of_date.
    Falls back to computing live if no cached value exists.

    Args:
        engine: SQLAlchemy engine
        player_id: NBA player ID
        team_id: NBA team ID
        as_of_date: Get impact as of this date (default: today)

    Returns:
        dict with impact data, or None if not found
    """
    if as_of_date is None:
        as_of_date = datetime.now().strftime('%Y-%m-%d')

    query = f"""
        SELECT * FROM player_impact
        WHERE player_id = {player_id}
          AND team_id = {team_id}
          AND compute_date <= '{as_of_date}'
        ORDER BY compute_date DESC
        LIMIT 1
    """

    try:
        with engine.connect() as conn:
            result = pd.read_sql(text(query), conn)

        if len(result) == 0:
            return None

        row = result.iloc[0]
        return {
            'player_id': int(row['player_id']),
            'team_id': int(row['team_id']),
            'player_name': row['player_name'],
            'impact': float(row['impact']) if pd.notna(row['impact']) else 0.0,
            'raw_impact': float(row['raw_impact']) if pd.notna(row['raw_impact']) else 0.0,
            'confidence': row['confidence'],
            'method': row['method'],
            'games_with': int(row['games_with']) if pd.notna(row['games_with']) else 0,
            'games_without': int(row['games_without']) if pd.notna(row['games_without']) else 0,
            'avg_minutes': float(row['avg_minutes']) if pd.notna(row['avg_minutes']) else 0.0,
            'avg_usage': float(row['avg_usage']) if pd.notna(row['avg_usage']) else 0.0,
            'importance_multiplier': float(row['importance_multiplier']) if pd.notna(row['importance_multiplier']) else 1.0,
            'compute_date': str(row['compute_date'])
        }
    except Exception as e:
        # Table might not exist yet
        return None


def _compute_impact_for_player(args):
    """
    Compute impact for a single player (used by parallel executor).

    Returns tuple: (player_id, team_id, player_name, impact_dict, error)
    """
    player_id, team_id, player_name, as_of_date, connection_string = args

    try:
        import sqlalchemy as sql
        engine = sql.create_engine(connection_string)

        impact_data = get_player_historical_impact(engine, player_id, team_id, as_of_date)

        engine.dispose()
        return (player_id, team_id, player_name, impact_data, None)
    except Exception as e:
        return (player_id, team_id, player_name, None, str(e))


def populate_player_impact_table(engine, as_of_date=None, min_minutes=15, min_games=5,
                                  n_jobs=-1, teams=None):
    """
    Populate the player_impact table with current impact scores for all significant players.

    This computes impact scores for all players meeting the criteria and stores them
    in the player_impact table. Run periodically (e.g., daily) to keep the cache fresh.

    Args:
        engine: SQLAlchemy engine
        as_of_date: Compute impacts as of this date (default: today)
        min_minutes: Minimum average minutes to be included
        min_games: Minimum games played to be included
        n_jobs: Number of parallel workers (-1 = all cores)
        teams: List of team_ids to process (default: all 30 teams)

    Returns:
        dict with statistics: {'players_processed': int, 'players_inserted': int, 'errors': int}
    """
    from joblib import Parallel, delayed
    import os

    if as_of_date is None:
        as_of_date = datetime.now().strftime('%Y-%m-%d')

    print(f"\n{'='*60}")
    print(f"POPULATING PLAYER IMPACT TABLE")
    print(f"As of date: {as_of_date}")
    print(f"{'='*60}")

    # Ensure table exists
    ensure_player_impact_table(engine)

    # Get all teams if not specified
    if teams is None:
        query = "SELECT DISTINCT id FROM nba_teams"
        with engine.connect() as conn:
            teams_df = pd.read_sql(text(query), conn)
        teams = teams_df['id'].tolist()

    print(f"Processing {len(teams)} teams...")

    # Get all significant players across all teams
    start_date = (datetime.strptime(as_of_date, '%Y-%m-%d') - timedelta(days=365)).strftime('%Y-%m-%d')

    query = f"""
        SELECT
            p.personId as player_id,
            p.teamId as team_id,
            CONCAT(p.firstName, ' ', p.familyName) as player_name,
            COUNT(*) as games,
            AVG(CASE
                WHEN p.minutes LIKE 'PT%%' THEN
                    CAST(SUBSTRING(p.minutes, 3, LOCATE('M', p.minutes) - 3) AS DECIMAL(10,2))
                WHEN p.minutes LIKE '%%:%%' THEN
                    CAST(SUBSTRING_INDEX(p.minutes, ':', 1) AS DECIMAL(10,2))
                ELSE 0
            END) as avg_minutes
        FROM boxscoretraditionalv3_player p
        JOIN game_list gl ON p.gameId = gl.GAME_ID AND p.teamId = gl.TEAM_ID
        WHERE gl.GAME_DATE >= '{start_date}'
          AND gl.GAME_DATE < '{as_of_date}'
          AND p.teamId IN ({','.join(map(str, teams))})
        GROUP BY p.personId, p.teamId, p.firstName, p.familyName
        HAVING games >= {min_games} AND avg_minutes >= {min_minutes}
        ORDER BY team_id, avg_minutes DESC
    """

    with engine.connect() as conn:
        players_df = pd.read_sql(text(query), conn)

    print(f"Found {len(players_df)} significant players to process")

    if len(players_df) == 0:
        return {'players_processed': 0, 'players_inserted': 0, 'errors': 0}

    # Build task list
    connection_string = engine.url.render_as_string(hide_password=False)
    tasks = []

    for _, row in players_df.iterrows():
        tasks.append((
            int(row['player_id']),
            int(row['team_id']),
            row['player_name'],
            as_of_date,
            connection_string
        ))

    # Determine number of jobs
    if n_jobs == -1:
        n_jobs = os.cpu_count() or 4
    elif n_jobs == -2:
        n_jobs = max(1, (os.cpu_count() or 4) - 1)

    # Limit to avoid DB connection issues
    n_jobs = min(n_jobs, 8)
    print(f"Using {n_jobs} parallel workers...")

    # Process in batches
    batch_size = 100
    all_results = []

    for i in range(0, len(tasks), batch_size):
        batch = tasks[i:i + batch_size]
        batch_results = Parallel(n_jobs=n_jobs, prefer="threads")(
            delayed(_compute_impact_for_player)(task) for task in batch
        )
        all_results.extend(batch_results)
        print(f"  Processed {min(i + batch_size, len(tasks))}/{len(tasks)} players...")

    # Insert results into database
    print("Inserting results into player_impact table...")

    inserted = 0
    errors = 0

    insert_sql = """
        INSERT INTO player_impact
            (player_id, team_id, compute_date, player_name, impact, raw_impact,
             confidence, method, games_with, games_without, avg_minutes, avg_usage,
             importance_multiplier)
        VALUES
            (:player_id, :team_id, :compute_date, :player_name, :impact, :raw_impact,
             :confidence, :method, :games_with, :games_without, :avg_minutes, :avg_usage,
             :importance_multiplier)
        ON DUPLICATE KEY UPDATE
            player_name = VALUES(player_name),
            impact = VALUES(impact),
            raw_impact = VALUES(raw_impact),
            confidence = VALUES(confidence),
            method = VALUES(method),
            games_with = VALUES(games_with),
            games_without = VALUES(games_without),
            avg_minutes = VALUES(avg_minutes),
            avg_usage = VALUES(avg_usage),
            importance_multiplier = VALUES(importance_multiplier)
    """

    with engine.connect() as conn:
        for player_id, team_id, player_name, impact_data, error in all_results:
            if error or impact_data is None:
                errors += 1
                continue

            try:
                conn.execute(text(insert_sql), {
                    'player_id': player_id,
                    'team_id': team_id,
                    'compute_date': as_of_date,
                    'player_name': player_name,
                    'impact': impact_data.get('impact', 0.0),
                    'raw_impact': impact_data.get('raw_impact', 0.0),
                    'confidence': impact_data.get('confidence', 'INSUFFICIENT'),
                    'method': impact_data.get('method', 'none'),
                    'games_with': impact_data.get('games_with', 0),
                    'games_without': impact_data.get('games_without', 0),
                    'avg_minutes': impact_data.get('avg_minutes', 0.0),
                    'avg_usage': impact_data.get('avg_usage', 0.0),
                    'importance_multiplier': impact_data.get('importance_multiplier', 1.0)
                })
                inserted += 1
            except Exception as e:
                errors += 1
                if errors <= 5:
                    print(f"  Error inserting {player_name}: {e}")

        conn.commit()

    print(f"\nDone! Processed: {len(all_results)}, Inserted: {inserted}, Errors: {errors}")

    return {
        'players_processed': len(all_results),
        'players_inserted': inserted,
        'errors': errors
    }


def get_top_players_by_impact(engine, team_id, as_of_date=None, top_n=8):
    """
    Get the top N players by impact score for a team.

    Uses cached values from player_impact table if available,
    otherwise computes live.

    Args:
        engine: SQLAlchemy engine
        team_id: NBA team ID
        as_of_date: Get impacts as of this date
        top_n: Number of top players to return (default: 8)

    Returns:
        List of dicts with player info and impact, sorted by abs(impact) descending:
        [
            {
                'player_id': int,
                'player_name': str,
                'impact': float,
                'confidence': str,
                'avg_minutes': float,
                'slot': int  # 1-8 indicating their rank
            },
            ...
        ]
    """
    if as_of_date is None:
        as_of_date = datetime.now().strftime('%Y-%m-%d')

    # Try to get from cache first
    query = f"""
        SELECT
            player_id, player_name, impact, raw_impact, confidence, method,
            games_with, games_without, avg_minutes, avg_usage, importance_multiplier
        FROM player_impact
        WHERE team_id = {team_id}
          AND compute_date = (
              SELECT MAX(compute_date)
              FROM player_impact
              WHERE team_id = {team_id} AND compute_date <= '{as_of_date}'
          )
        ORDER BY ABS(impact) DESC
        LIMIT {top_n}
    """

    try:
        with engine.connect() as conn:
            df = pd.read_sql(text(query), conn)

        if len(df) >= top_n // 2:  # Use cache if we have at least half the players
            results = []
            for i, row in df.iterrows():
                results.append({
                    'player_id': int(row['player_id']),
                    'player_name': row['player_name'],
                    'impact': float(row['impact']) if pd.notna(row['impact']) else 0.0,
                    'raw_impact': float(row['raw_impact']) if pd.notna(row['raw_impact']) else 0.0,
                    'confidence': row['confidence'],
                    'method': row['method'],
                    'avg_minutes': float(row['avg_minutes']) if pd.notna(row['avg_minutes']) else 0.0,
                    'slot': i + 1
                })

            # Pad with empty slots if needed
            while len(results) < top_n:
                results.append({
                    'player_id': 0,
                    'player_name': '',
                    'impact': 0.0,
                    'raw_impact': 0.0,
                    'confidence': 'INSUFFICIENT',
                    'method': 'none',
                    'avg_minutes': 0.0,
                    'slot': len(results) + 1
                })

            return results
    except Exception:
        pass  # Fall through to live computation

    # Fallback: compute live using get_team_player_impacts
    impacts = get_team_player_impacts(engine, team_id, as_of_date, min_minutes=15, min_games=5)

    results = []
    for i, p in enumerate(impacts[:top_n]):
        results.append({
            'player_id': p['player_id'],
            'player_name': p['player_name'],
            'impact': p['impact'],
            'raw_impact': p.get('raw_impact', p['impact']),
            'confidence': p['confidence'],
            'method': p['method'],
            'avg_minutes': p['avg_minutes'],
            'slot': i + 1
        })

    # Pad with empty slots if needed
    while len(results) < top_n:
        results.append({
            'player_id': 0,
            'player_name': '',
            'impact': 0.0,
            'raw_impact': 0.0,
            'confidence': 'INSUFFICIENT',
            'method': 'none',
            'avg_minutes': 0.0,
            'slot': len(results) + 1
        })

    return results


def get_player_availability_for_game(engine, game_id, team_id):
    """
    Get player availability status for a specific historical game.

    Uses the comment field from boxscoreplayertrackv3_player to determine
    if a player was OUT (DNP/DND/NWT) or AVAILABLE.

    Args:
        engine: SQLAlchemy engine
        game_id: NBA game ID
        team_id: NBA team ID

    Returns:
        Dict mapping player_id -> {'available': bool, 'comment': str, 'minutes': float}
    """
    query = f"""
        SELECT
            p.personId as player_id,
            CONCAT(p.firstName, ' ', p.familyName) as player_name,
            p.minutes,
            COALESCE(track.comment, '') as comment
        FROM boxscoretraditionalv3_player p
        LEFT JOIN boxscoreplayertrackv3_player track
            ON p.gameId = track.gameId AND p.personId = track.personId
        WHERE p.gameId = '{game_id}' AND p.teamId = {team_id}
    """

    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)

    result = {}
    for _, row in df.iterrows():
        player_id = int(row['player_id'])
        comment = row['comment'] or ''

        # Determine if player was OUT
        is_out = (
            comment.startswith('DNP') or
            comment.startswith('DND') or
            comment.startswith('NWT')
        )

        # Parse minutes
        minutes = parse_minutes(row['minutes'])

        result[player_id] = {
            'available': not is_out,
            'comment': comment,
            'minutes': minutes,
            'player_name': row['player_name']
        }

    return result


# =============================================================================
# BULK DATA FETCHING FOR PERFORMANCE
# =============================================================================

def bulk_fetch_player_impacts(engine, team_ids, start_date, end_date):
    """
    Bulk fetch all player impacts for multiple teams across a date range.

    This fetches all cached impacts from the player_impact table in a single query,
    avoiding the N+1 query problem when processing many games.

    IMPORTANT: We fetch compute_dates UP TO end_date (not restricted by start_date)
    because games need to look up the most recent compute_date BEFORE the game date.
    A game on 2024-01-20 should use impacts computed on 2024-01-15, not impacts
    from within the game date range.

    Args:
        engine: SQLAlchemy engine
        team_ids: List of team IDs to fetch impacts for
        start_date: Start of game date range (for logging only)
        end_date: End of game date range (YYYY-MM-DD) - fetch impacts up to this date

    Returns:
        Dict structure for fast lookups:
        {
            team_id: {
                'YYYY-MM-DD': [  # compute_date
                    {'player_id': int, 'player_name': str, 'impact': float, ...},
                    ...
                ],
                ...
            },
            ...
        }

        Also returns a sorted list of all compute_dates for efficient "most recent" lookups.
    """
    if not team_ids:
        return {}, []

    team_ids_str = ','.join(map(str, team_ids))

    # Fetch ALL compute_dates up to end_date so we can find the most recent
    # compute_date before any game date in the range
    query = f"""
        SELECT
            player_id, team_id, compute_date, player_name,
            impact, raw_impact, confidence, method,
            games_with, games_without, avg_minutes, avg_usage,
            importance_multiplier
        FROM player_impact
        WHERE team_id IN ({team_ids_str})
          AND compute_date <= '{end_date}'
        ORDER BY team_id, compute_date, ABS(impact) DESC
    """

    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)

    if len(df) == 0:
        return {}, []

    # Build nested dict structure
    impacts_by_team = {}
    all_compute_dates = set()

    for team_id in df['team_id'].unique():
        team_df = df[df['team_id'] == team_id]
        impacts_by_team[int(team_id)] = {}

        for compute_date in team_df['compute_date'].unique():
            date_str = str(compute_date)[:10]
            all_compute_dates.add(date_str)

            date_df = team_df[team_df['compute_date'] == compute_date]
            players = []

            for i, row in date_df.iterrows():
                players.append({
                    'player_id': int(row['player_id']),
                    'player_name': row['player_name'],
                    'impact': float(row['impact']) if pd.notna(row['impact']) else 0.0,
                    'raw_impact': float(row['raw_impact']) if pd.notna(row['raw_impact']) else 0.0,
                    'confidence': row['confidence'],
                    'method': row['method'],
                    'avg_minutes': float(row['avg_minutes']) if pd.notna(row['avg_minutes']) else 0.0,
                })

            impacts_by_team[int(team_id)][date_str] = players

    # Sort compute dates for binary search
    sorted_dates = sorted(all_compute_dates)

    print(f"    Bulk loaded {len(df)} player impact records for {len(impacts_by_team)} teams")
    print(f"    Date range in cache: {sorted_dates[0] if sorted_dates else 'N/A'} to {sorted_dates[-1] if sorted_dates else 'N/A'}")

    return impacts_by_team, sorted_dates


def bulk_fetch_player_availability(engine, game_ids):
    """
    Bulk fetch player availability for all games in a single query.

    Args:
        engine: SQLAlchemy engine
        game_ids: List of game IDs to fetch availability for

    Returns:
        Dict structure for fast lookups:
        {
            (game_id, team_id): {
                player_id: {'available': bool, 'comment': str, 'minutes': float},
                ...
            },
            ...
        }
    """
    if not game_ids:
        return {}

    # Convert to strings and create IN clause
    game_ids_str = ','.join(f"'{gid}'" for gid in game_ids)

    query = f"""
        SELECT
            p.gameId as game_id,
            p.teamId as team_id,
            p.personId as player_id,
            CONCAT(p.firstName, ' ', p.familyName) as player_name,
            p.minutes,
            COALESCE(track.comment, '') as comment
        FROM boxscoretraditionalv3_player p
        LEFT JOIN boxscoreplayertrackv3_player track
            ON p.gameId = track.gameId AND p.personId = track.personId
        WHERE p.gameId IN ({game_ids_str})
    """

    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)

    if len(df) == 0:
        return {}

    # Build nested dict structure
    availability = {}

    for _, row in df.iterrows():
        game_id = row['game_id']
        team_id = int(row['team_id'])
        player_id = int(row['player_id'])
        comment = row['comment'] or ''

        key = (game_id, team_id)
        if key not in availability:
            availability[key] = {}

        # Determine if player was OUT
        is_out = (
            comment.startswith('DNP') or
            comment.startswith('DND') or
            comment.startswith('NWT')
        )

        # Parse minutes
        minutes = parse_minutes(row['minutes'])

        availability[key][player_id] = {
            'available': not is_out,
            'comment': comment,
            'minutes': minutes,
            'player_name': row['player_name']
        }

    print(f"    Bulk loaded availability for {len(availability)} team-games ({len(df)} player records)")

    return availability


def get_top_players_for_team_date(impacts_by_team, sorted_dates, team_id, game_date, top_n=8):
    """
    Get top N players by impact for a team as of a specific date.

    Uses the pre-fetched bulk data for fast in-memory lookup.
    Finds the most recent compute_date on or before game_date.

    Args:
        impacts_by_team: Dict from bulk_fetch_player_impacts
        sorted_dates: Sorted list of compute dates
        team_id: Team ID to look up
        game_date: Game date (YYYY-MM-DD string)
        top_n: Number of players to return

    Returns:
        List of player dicts with 'slot' field added, or empty slots if not found
    """
    # Default empty result
    empty_result = [
        {
            'player_id': 0,
            'player_name': '',
            'impact': 0.0,
            'raw_impact': 0.0,
            'confidence': 'INSUFFICIENT',
            'method': 'none',
            'avg_minutes': 0.0,
            'slot': i + 1
        }
        for i in range(top_n)
    ]

    if team_id not in impacts_by_team:
        return empty_result

    team_data = impacts_by_team[team_id]
    if not team_data:
        return empty_result

    # Find most recent compute_date <= game_date using binary search
    import bisect
    game_date_str = str(game_date)[:10]

    # Get dates available for this team
    team_dates = sorted(team_data.keys())
    if not team_dates:
        return empty_result

    # Find position where game_date would be inserted
    pos = bisect.bisect_right(team_dates, game_date_str)

    if pos == 0:
        # No compute_date before game_date
        return empty_result

    # Use the date just before the insertion point
    best_date = team_dates[pos - 1]
    players = team_data[best_date]

    # Take top N and add slot numbers
    result = []
    for i, p in enumerate(players[:top_n]):
        result.append({
            **p,
            'slot': i + 1
        })

    # Pad with empty slots if needed
    while len(result) < top_n:
        result.append({
            'player_id': 0,
            'player_name': '',
            'impact': 0.0,
            'raw_impact': 0.0,
            'confidence': 'INSUFFICIENT',
            'method': 'none',
            'avg_minutes': 0.0,
            'slot': len(result) + 1
        })

    return result


# CLI interface
if __name__ == '__main__':
    import argparse
    from datetime import datetime

    parser = argparse.ArgumentParser(
        description='Player Impact Cache Management',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Populate cache for today's date
  python data_engineering/player_impact.py --populate

  # Populate cache for a specific date
  python data_engineering/player_impact.py --populate --date 2024-01-15

  # Populate cache for multiple dates
  python data_engineering/player_impact.py --populate --date 2023-01-01 --date 2023-07-01 --date 2024-01-01
  python data_engineering/player_impact.py -p -d 2025-01-01 -d 2025-06-01 --d 2025-12-09

  # Show team impact report
  python data_engineering/player_impact.py --report --team 1610612759

  # Check cache status
  python data_engineering/player_impact.py --status
        """
    )

    parser.add_argument('--populate', '-p', action='store_true',
                        help='Populate the player_impact cache table')
    parser.add_argument('--date', '-d', action='append', dest='dates',
                        help='Date(s) to populate (YYYY-MM-DD). Can be specified multiple times. Default: today')
    parser.add_argument('--report', '-r', action='store_true',
                        help='Show team impact report')
    parser.add_argument('--team', '-t', type=int, default=1610612759,
                        help='Team ID for report (default: 1610612759 = Spurs)')
    parser.add_argument('--status', '-s', action='store_true',
                        help='Show cache status (dates and record counts)')

    args = parser.parse_args()

    engine = create_engine()

    # Default action: show status if no action specified
    if not args.populate and not args.report and not args.status:
        args.status = True

    if args.status:
        print("=" * 60)
        print("PLAYER IMPACT CACHE STATUS")
        print("=" * 60)
        try:
            with engine.connect() as conn:
                result = conn.execute(text(
                    'SELECT COUNT(*) as cnt, COUNT(DISTINCT compute_date) as dates, '
                    'MIN(compute_date) as min_date, MAX(compute_date) as max_date '
                    'FROM player_impact'
                ))
                row = result.fetchone()
                print(f"Total records: {row[0]:,}")
                print(f"Unique dates: {row[1]}")
                print(f"Date range: {row[2]} to {row[3]}")

                print("\nRecords by compute date:")
                result = conn.execute(text(
                    'SELECT compute_date, COUNT(*) as players '
                    'FROM player_impact GROUP BY compute_date ORDER BY compute_date'
                ))
                for row in result:
                    print(f"  {row[0]}: {row[1]} players")
        except Exception as e:
            print(f"Error checking status: {e}")
            print("The player_impact table may not exist yet.")

    if args.populate:
        # Use provided dates or default to today
        dates = args.dates if args.dates else [datetime.now().strftime('%Y-%m-%d')]

        for date in dates:
            print(f"\n>>> Populating cache for {date}...")
            result = populate_player_impact_table(engine, as_of_date=date)
            print(f"    Result: {result}")

    if args.report:
        print_team_impact_report(engine, args.team, f"Team {args.team}", verbose=True)

    engine.dispose()
