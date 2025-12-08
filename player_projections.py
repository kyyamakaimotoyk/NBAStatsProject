"""
Player-Level Projections with Opponent Adjustments
===================================================

This module implements "Full Roster Aggregation" for NBA game predictions:
1. Get expected roster for each team (based on recent playing time)
2. Get each player's season averages
3. Adjust player projections based on opponent's defensive profile:
   - Pace adjustment (fast vs slow teams)
   - Defensive rating adjustment (good vs bad defense)
   - Rebounding adjustment
4. Aggregate adjusted player stats to team-level features

The Chicken-Egg Solution:
-------------------------
We use SEASON-TO-DATE stats (excluding the current game) for all calculations.
This means:
- Player stats: Calculated from games BEFORE the prediction date
- Opponent defensive stats: Calculated from games BEFORE the prediction date
- No circularity because we never use future data

Usage:
    from player_projections import get_player_projection_features

    features = get_player_projection_features(
        engine=engine,
        team_id=1610612738,  # Boston Celtics
        opponent_id=1610612747,  # Los Angeles Lakers
        as_of_date='2024-12-15'
    )
"""

import pandas as pd
import numpy as np
from sqlalchemy import text
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta


# ============================================================================
# CONSTANTS
# ============================================================================

# Minimum games for player to be considered active
MIN_GAMES_FOR_ROSTER = 3

# Minimum minutes per game to be considered a rotation player
MIN_MPG_ROTATION = 10.0

# Number of days to look back for "recent" activity
RECENT_DAYS = 14

# Rolling window for player averages
PLAYER_WINDOW_GAMES = 10

# Rolling window for team defensive stats
TEAM_WINDOW_GAMES = 10


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def parse_minutes(minutes_str) -> float:
    """
    Parse minutes from various formats to float.

    Handles:
    - "MM:SS" format (e.g., "32:45")
    - "PT32M45S" ISO format
    - Numeric values
    - None/empty values
    """
    if minutes_str is None or minutes_str == '' or pd.isna(minutes_str):
        return 0.0

    if isinstance(minutes_str, (int, float)):
        return float(minutes_str)

    minutes_str = str(minutes_str)

    # Handle "PT32M45S" format
    if minutes_str.startswith('PT'):
        try:
            import re
            match = re.match(r'PT(\d+)M(\d+(?:\.\d+)?)S', minutes_str)
            if match:
                return float(match.group(1)) + float(match.group(2)) / 60
        except:
            pass
        return 0.0

    # Handle "MM:SS" format
    if ':' in minutes_str:
        try:
            parts = minutes_str.split(':')
            return float(parts[0]) + float(parts[1]) / 60
        except:
            return 0.0

    # Try direct conversion
    try:
        return float(minutes_str)
    except:
        return 0.0


# ============================================================================
# LEAGUE AVERAGES (for normalization)
# ============================================================================

def get_league_averages(engine, as_of_date: str, season_start: str = None) -> Dict[str, float]:
    """
    Get league-wide averages for pace, defensive rating, rebounding, and efficiency.

    These are used as the baseline for opponent adjustments.
    If Team X has a defensive rating of 110 and league average is 112,
    then Team X is a better-than-average defense.

    Returns percentages as decimals (0.28 = 28%).
    """
    if season_start is None:
        # Infer season start from date
        dt = datetime.strptime(as_of_date, '%Y-%m-%d')
        if dt.month >= 10:  # Oct-Dec = current season
            season_start = f"{dt.year}-10-01"
        else:  # Jan-Sep = previous year's season
            season_start = f"{dt.year - 1}-10-01"

    query = f"""
        SELECT
            AVG(adv.pace) as avg_pace,
            AVG(adv.defensiveRating) as avg_defensive_rating,
            AVG(adv.offensiveRating) as avg_offensive_rating,
            AVG(adv.offensiveReboundPercentage) as avg_own_oreb_pct,
            AVG(adv.effectiveFieldGoalPercentage) as avg_own_efg_pct,
            AVG(ff.oppOffensiveReboundPercentage) as avg_opp_oreb_pct,
            AVG(ff.oppEffectiveFieldGoalPercentage) as avg_opp_efg_pct
        FROM boxscoreadvancedv3_team adv
        JOIN game_list gl ON adv.gameId = gl.GAME_ID AND adv.teamId = gl.TEAM_ID
        LEFT JOIN boxscorefourfactorsv3_team ff ON adv.gameId = ff.gameId AND adv.teamId = ff.teamId
        WHERE gl.GAME_DATE >= '{season_start}'
          AND gl.GAME_DATE < '{as_of_date}'
    """

    with engine.connect() as conn:
        result = pd.read_sql(text(query), conn)

    # Fallback values based on 2022-2024 NBA seasons (9,133 games analyzed 2024-12-08)
    # Source: nba_data database query across 3 full seasons
    FALLBACK_AVERAGES = {
        'pace': 99.2,              # Possessions per 48 min
        'defensive_rating': 112.9, # Points allowed per 100 poss
        'offensive_rating': 112.9, # Points scored per 100 poss
        'own_oreb_pct': 0.28,      # 28% of available offensive rebounds
        'own_efg_pct': 0.54,       # 54% effective field goal percentage
        'opp_oreb_pct': 0.28,      # 28% opponent offensive rebound rate allowed
        'opp_efg_pct': 0.54        # 54% opponent effective FG% allowed
    }

    if len(result) == 0 or result['avg_pace'].iloc[0] is None:
        return FALLBACK_AVERAGES

    return {
        'pace': float(result['avg_pace'].iloc[0] or FALLBACK_AVERAGES['pace']),
        'defensive_rating': float(result['avg_defensive_rating'].iloc[0] or FALLBACK_AVERAGES['defensive_rating']),
        'offensive_rating': float(result['avg_offensive_rating'].iloc[0] or FALLBACK_AVERAGES['offensive_rating']),
        'own_oreb_pct': float(result['avg_own_oreb_pct'].iloc[0] or FALLBACK_AVERAGES['own_oreb_pct']),
        'own_efg_pct': float(result['avg_own_efg_pct'].iloc[0] or FALLBACK_AVERAGES['own_efg_pct']),
        'opp_oreb_pct': float(result['avg_opp_oreb_pct'].iloc[0] or FALLBACK_AVERAGES['opp_oreb_pct']),
        'opp_efg_pct': float(result['avg_opp_efg_pct'].iloc[0] or FALLBACK_AVERAGES['opp_efg_pct'])
    }


# ============================================================================
# TEAM DEFENSIVE STATS
# ============================================================================

def get_team_defensive_stats(engine, team_id: int, as_of_date: str,
                              window_games: int = TEAM_WINDOW_GAMES) -> Dict[str, float]:
    """
    Get a team's recent defensive profile (what opponents score against them).

    This is used to adjust player projections:
    - If Team X has a good defense (low defensive rating), we lower opponent projections
    - If Team X plays slow (low pace), we lower opponent possession-based stats
    - If Team X is good at offensive rebounding, they limit opponent DREB opportunities

    Returns:
        dict with defensive metrics (averaged over last N games)
        Percentages are stored as decimals (0.28 = 28%)
    """
    query = f"""
        SELECT
            adv.pace,
            adv.defensiveRating,
            adv.offensiveRating,
            adv.offensiveReboundPercentage as own_oreb_pct,
            adv.effectiveFieldGoalPercentage as own_efg_pct,
            ff.oppOffensiveReboundPercentage as opp_oreb_pct,
            ff.oppEffectiveFieldGoalPercentage as opp_efg_pct,
            ff.oppFreeThrowAttemptRate as opp_ft_rate
        FROM boxscoreadvancedv3_team adv
        JOIN game_list gl ON adv.gameId = gl.GAME_ID AND adv.teamId = gl.TEAM_ID
        LEFT JOIN boxscorefourfactorsv3_team ff ON adv.gameId = ff.gameId AND adv.teamId = ff.teamId
        WHERE gl.TEAM_ID = {team_id}
          AND gl.GAME_DATE < '{as_of_date}'
          AND gl.WL IS NOT NULL
        ORDER BY gl.GAME_DATE DESC
        LIMIT {window_games}
    """

    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)

    # Fallback values based on 2022-2024 NBA seasons (analyzed 2024-12-08)
    FALLBACK_STATS = {
        'pace': 99.2,
        'defensive_rating': 112.9,
        'offensive_rating': 112.9,
        'own_oreb_pct': 0.28,
        'own_efg_pct': 0.54,
        'opp_oreb_pct': 0.28,
        'opp_efg_pct': 0.54,
        'opp_ft_rate': 0.25
    }

    if len(df) == 0:
        return FALLBACK_STATS

    return {
        'pace': df['pace'].mean() if df['pace'].notna().any() else FALLBACK_STATS['pace'],
        'defensive_rating': df['defensiveRating'].mean() if df['defensiveRating'].notna().any() else FALLBACK_STATS['defensive_rating'],
        'offensive_rating': df['offensiveRating'].mean() if df['offensiveRating'].notna().any() else FALLBACK_STATS['offensive_rating'],
        'own_oreb_pct': df['own_oreb_pct'].mean() if df['own_oreb_pct'].notna().any() else FALLBACK_STATS['own_oreb_pct'],
        'own_efg_pct': df['own_efg_pct'].mean() if df['own_efg_pct'].notna().any() else FALLBACK_STATS['own_efg_pct'],
        'opp_oreb_pct': df['opp_oreb_pct'].mean() if df['opp_oreb_pct'].notna().any() else FALLBACK_STATS['opp_oreb_pct'],
        'opp_efg_pct': df['opp_efg_pct'].mean() if df['opp_efg_pct'].notna().any() else FALLBACK_STATS['opp_efg_pct'],
        'opp_ft_rate': df['opp_ft_rate'].mean() if df['opp_ft_rate'].notna().any() else FALLBACK_STATS['opp_ft_rate']
    }


# ============================================================================
# EXPECTED ROSTER
# ============================================================================

def get_expected_roster(engine, team_id: int, as_of_date: str,
                        min_games: int = MIN_GAMES_FOR_ROSTER,
                        min_mpg: float = MIN_MPG_ROTATION,
                        recent_days: int = RECENT_DAYS,
                        excluded_players: List[str] = None) -> List[Dict]:
    """
    Determine which players are expected to play based on recent activity.

    Strategy:
    1. Look at players who played in the last N days
    2. Require minimum games played
    3. Require minimum minutes per game
    4. Weight by recent minutes to estimate expected playing time
    5. Exclude players who are known to be injured/out

    Args:
        engine: SQLAlchemy database engine
        team_id: NBA team ID
        as_of_date: Date to calculate roster as of (YYYY-MM-DD)
        min_games: Minimum games played to be included
        min_mpg: Minimum minutes per game to be included
        recent_days: Number of days to look back for recent activity
        excluded_players: List of player names to exclude (e.g., injured players)

    Returns:
        list of dicts with player info and expected minutes share
    """
    if excluded_players is None:
        excluded_players = []

    # Normalize excluded player names for matching
    excluded_lower = [name.lower().strip() for name in excluded_players]
    # Calculate date range
    recent_start = (datetime.strptime(as_of_date, '%Y-%m-%d') -
                   timedelta(days=recent_days)).strftime('%Y-%m-%d')

    query = f"""
        SELECT
            p.personId as player_id,
            p.firstName,
            p.familyName,
            p.minutes,
            gl.GAME_DATE,
            p.points,
            p.reboundsTotal as rebounds,
            p.assists
        FROM boxscoretraditionalv3_player p
        JOIN game_list gl ON p.gameId = gl.GAME_ID AND p.teamId = gl.TEAM_ID
        WHERE p.teamId = {team_id}
          AND gl.GAME_DATE >= '{recent_start}'
          AND gl.GAME_DATE < '{as_of_date}'
          AND gl.WL IS NOT NULL
        ORDER BY gl.GAME_DATE DESC, p.personId
    """

    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)

    if len(df) == 0:
        return []

    # Parse minutes
    df['minutes_float'] = df['minutes'].apply(parse_minutes)

    # Aggregate by player
    player_stats = df.groupby(['player_id', 'firstName', 'familyName']).agg({
        'GAME_DATE': 'count',  # games played
        'minutes_float': 'mean',  # average minutes
        'points': 'mean',
        'rebounds': 'mean',
        'assists': 'mean'
    }).reset_index()

    player_stats.columns = ['player_id', 'first_name', 'last_name',
                           'games_played', 'avg_minutes', 'avg_pts', 'avg_reb', 'avg_ast']

    # Filter by minimum criteria
    roster = player_stats[
        (player_stats['games_played'] >= min_games) &
        (player_stats['avg_minutes'] >= min_mpg)
    ].copy()

    if len(roster) == 0:
        # Fallback: take any player with at least 1 game
        roster = player_stats[player_stats['games_played'] >= 1].copy()

    # Exclude injured/unavailable players
    if excluded_lower:
        def is_excluded(row):
            full_name = f"{row['first_name']} {row['last_name']}".lower().strip()
            # Check exact match
            if full_name in excluded_lower:
                return True
            # Check partial match (first + last name separately)
            for excl in excluded_lower:
                excl_parts = excl.split()
                if len(excl_parts) >= 2:
                    if (excl_parts[0] in full_name.lower() and
                        excl_parts[-1] in full_name.lower()):
                        return True
            return False

        roster = roster[~roster.apply(is_excluded, axis=1)]

        if len(excluded_lower) > 0 and len(roster) < len(player_stats):
            excluded_count = len(player_stats) - len(roster)
            # This is expected behavior - don't print unless debugging

    # Calculate minutes share (proportion of 240 total team minutes = 48 min x 5 players)
    total_minutes = roster['avg_minutes'].sum()
    roster['minutes_share'] = roster['avg_minutes'] / total_minutes if total_minutes > 0 else 0

    # Sort by minutes (starters first)
    roster = roster.sort_values('avg_minutes', ascending=False)

    return roster.to_dict('records')


# ============================================================================
# PLAYER SEASON AVERAGES
# ============================================================================

def get_player_season_averages(engine, player_id: int, as_of_date: str,
                                window_games: int = PLAYER_WINDOW_GAMES) -> Dict[str, float]:
    """
    Get a player's rolling averages (last N games).

    Includes:
    - Traditional stats: PPG, OREB, DREB, RPG, APG, SPG, BPG, MPG
    - Efficiency: FG%, 3P%, FT%, TS%
    - Advanced: Usage%, PIE
    """
    query = f"""
        SELECT
            trad.minutes,
            trad.points,
            trad.reboundsOffensive as oreb,
            trad.reboundsDefensive as dreb,
            trad.reboundsTotal as rebounds,
            trad.assists,
            trad.steals,
            trad.blocks,
            trad.turnovers,
            trad.fieldGoalsMade as fgm,
            trad.fieldGoalsAttempted as fga,
            trad.threePointersMade as fg3m,
            trad.threePointersAttempted as fg3a,
            trad.freeThrowsMade as ftm,
            trad.freeThrowsAttempted as fta,
            adv.usagePercentage,
            adv.trueShootingPercentage as ts_pct,
            adv.effectiveFieldGoalPercentage as efg_pct,
            adv.PIE
        FROM boxscoretraditionalv3_player trad
        JOIN game_list gl ON trad.gameId = gl.GAME_ID AND trad.teamId = gl.TEAM_ID
        LEFT JOIN boxscoreadvancedv3_player adv ON trad.gameId = adv.gameId AND trad.personId = adv.personId
        WHERE trad.personId = {player_id}
          AND gl.GAME_DATE < '{as_of_date}'
          AND gl.WL IS NOT NULL
        ORDER BY gl.GAME_DATE DESC
        LIMIT {window_games}
    """

    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)

    if len(df) == 0:
        return None

    # Parse minutes
    df['minutes_float'] = df['minutes'].apply(parse_minutes)

    # Calculate averages
    stats = {
        'mpg': df['minutes_float'].mean(),
        'ppg': df['points'].mean(),
        'oreb_pg': df['oreb'].mean() if df['oreb'].notna().any() else 0.0,
        'dreb_pg': df['dreb'].mean() if df['dreb'].notna().any() else 0.0,
        'rpg': df['rebounds'].mean(),
        'apg': df['assists'].mean(),
        'spg': df['steals'].mean(),
        'bpg': df['blocks'].mean(),
        'topg': df['turnovers'].mean(),
        'fgm': df['fgm'].mean(),
        'fga': df['fga'].mean(),
        'fg3m': df['fg3m'].mean(),
        'fg3a': df['fg3a'].mean(),
        'ftm': df['ftm'].mean(),
        'fta': df['fta'].mean(),
        'fg_pct': df['fgm'].sum() / df['fga'].sum() if df['fga'].sum() > 0 else 0,
        'fg3_pct': df['fg3m'].sum() / df['fg3a'].sum() if df['fg3a'].sum() > 0 else 0,
        'ft_pct': df['ftm'].sum() / df['fta'].sum() if df['fta'].sum() > 0 else 0,
        'usage_pct': df['usagePercentage'].mean() if 'usagePercentage' in df else 20.0,
        'ts_pct': df['ts_pct'].mean() if 'ts_pct' in df else 0.5,
        'efg_pct': df['efg_pct'].mean() if 'efg_pct' in df else 0.5,
        'pie': df['PIE'].mean() if 'PIE' in df else 0.1,
        'games_played': len(df)
    }

    return stats


# ============================================================================
# OPPONENT ADJUSTMENT
# ============================================================================

def calculate_rebounding_factors(opponent_def_stats: Dict[str, float],
                                   league_averages: Dict[str, float]) -> Dict[str, float]:
    """
    Calculate separate OREB and DREB adjustment factors.

    OREB opportunities depend on:
      - Opponent's defensive rebounding (opp_oreb_pct = what they ALLOW us to get)

    DREB opportunities depend on:
      - Opponent's offensive rebounding ability (own_oreb_pct = what they GET)
        -> If opponent is good at OREB, fewer DREB opportunities for us
      - Opponent's miss rate (1 - EFG%)
        -> More misses = more total rebound opportunities

    Returns:
        dict with 'oreb_factor' and 'dreb_factor'
    """
    # OFFENSIVE REBOUNDING FACTOR
    # Higher opp_oreb_pct = opponent allows more OREBs = more OREB opportunities for us
    oreb_factor = (
        opponent_def_stats.get('opp_oreb_pct', league_averages['opp_oreb_pct']) /
        league_averages['opp_oreb_pct']
    )

    # DEFENSIVE REBOUNDING FACTOR - Two components:

    # 1. Opponent's OREB ability - if they're good at OREB, fewer DREBs for us
    #    Inverse relationship: high opponent OREB% = lower DREB factor
    opponent_oreb_pct = opponent_def_stats.get('own_oreb_pct', league_averages['own_oreb_pct'])
    oreb_competition_factor = (
        (1 - opponent_oreb_pct) /
        (1 - league_averages['own_oreb_pct'])
    )
    # Example: Opponent OREB% = 30%, League avg = 28%
    # Factor = (1 - 0.30) / (1 - 0.28) = 0.70 / 0.72 = 0.972 (fewer DREBs for us)

    # 2. Opponent's miss rate - more misses = more total rebound opportunities
    #    Using (1 - EFG%) as proxy for miss rate
    opponent_efg = opponent_def_stats.get('own_efg_pct', league_averages['own_efg_pct'])
    miss_rate_factor = (
        (1 - opponent_efg) /
        (1 - league_averages['own_efg_pct'])
    )
    # Example: Opponent EFG% = 52%, League avg = 54%
    # Factor = (1 - 0.52) / (1 - 0.54) = 0.48 / 0.46 = 1.043 (more misses = more DREBs)

    # Combined DREB factor
    dreb_factor = oreb_competition_factor * miss_rate_factor

    return {
        'oreb_factor': oreb_factor,
        'dreb_factor': dreb_factor,
        'oreb_competition_factor': oreb_competition_factor,
        'miss_rate_factor': miss_rate_factor
    }


def adjust_player_stats_for_opponent(player_stats: Dict[str, float],
                                      opponent_def_stats: Dict[str, float],
                                      league_averages: Dict[str, float]) -> Dict[str, float]:
    """
    Adjust a player's expected stats based on the opponent's defensive profile.

    Adjustments:
    1. PACE ADJUSTMENT: If opponent plays faster, more possessions = more stats
       - All counting stats (pts, reb, ast) scale with pace

    2. DEFENSIVE RATING ADJUSTMENT: If opponent has worse defense, player scores more
       - Points are adjusted based on opponent's defensive rating

    3. SPLIT REBOUNDING ADJUSTMENT:
       - OREB: Based on what opponent ALLOWS (opp_oreb_pct)
       - DREB: Based on opponent's own OREB ability AND their miss rate

    Formula:
        adjusted_stat = raw_stat * (opponent_factor / league_avg_factor)

    Example:
        Player: 20 PPG
        Opponent DRtg: 115 (bad defense, allows 115 pts/100 poss)
        League avg DRtg: 112

        Adjustment factor = 115 / 112 = 1.027
        Expected PPG vs this opponent = 20 * 1.027 = 20.54 PPG
    """
    if player_stats is None:
        return None

    adjusted = player_stats.copy()

    # 1. Pace adjustment
    # More possessions = more opportunities for all stats
    pace_factor = opponent_def_stats['pace'] / league_averages['pace']

    # 2. Defensive rating adjustment for scoring
    # Higher DRtg = worse defense = more points allowed
    drtg_factor = opponent_def_stats['defensive_rating'] / league_averages['defensive_rating']

    # 3. Split rebounding adjustment
    reb_factors = calculate_rebounding_factors(opponent_def_stats, league_averages)

    # Apply adjustments
    # Points: affected by both pace and defense
    adjusted['proj_ppg'] = player_stats['ppg'] * pace_factor * drtg_factor

    # SPLIT REBOUNDING: Apply different factors to OREB and DREB
    adjusted['proj_oreb'] = player_stats.get('oreb_pg', 0) * pace_factor * reb_factors['oreb_factor']
    adjusted['proj_dreb'] = player_stats.get('dreb_pg', 0) * pace_factor * reb_factors['dreb_factor']
    adjusted['proj_rpg'] = adjusted['proj_oreb'] + adjusted['proj_dreb']

    # Assists: affected mainly by pace (more possessions = more assist opportunities)
    adjusted['proj_apg'] = player_stats['apg'] * pace_factor

    # Other counting stats: pace adjustment only
    adjusted['proj_spg'] = player_stats['spg'] * pace_factor
    adjusted['proj_bpg'] = player_stats['bpg'] * pace_factor
    adjusted['proj_topg'] = player_stats['topg'] * pace_factor

    # Shooting: affected by defensive pressure (better defense = lower FG%)
    # We use opponent's opp_efg_pct as a proxy for defensive quality
    efg_factor = opponent_def_stats.get('opp_efg_pct', league_averages['opp_efg_pct']) / league_averages['opp_efg_pct']
    adjusted['proj_fg_pct'] = player_stats['fg_pct'] * efg_factor

    # Store adjustment factors for transparency
    adjusted['adj_pace_factor'] = pace_factor
    adjusted['adj_drtg_factor'] = drtg_factor
    adjusted['adj_oreb_factor'] = reb_factors['oreb_factor']
    adjusted['adj_dreb_factor'] = reb_factors['dreb_factor']

    return adjusted


# ============================================================================
# TEAM AGGREGATION
# ============================================================================

def aggregate_roster_projections(roster_projections: List[Dict[str, float]]) -> Dict[str, float]:
    """
    Aggregate individual player projections into team-level features.

    Aggregation methods:
    - SUM: Points, rebounds, assists (direct sum - PPG is already per-game contribution)
    - WEIGHTED AVG: Usage%, TS%, PIE (weighted by minutes)
    - COUNT: Roster depth (players with 15+ min)
    - MAX: Star player impact (highest scorer)
    - TOP3: Concentration (% of points from top 3 scorers)
    """
    if not roster_projections:
        return {
            'proj_team_pts': 110.0,  # League average fallback
            'proj_team_reb': 44.0,
            'proj_team_ast': 25.0,
            'weighted_usage': 20.0,
            'weighted_ts_pct': 0.55,
            'weighted_pie': 0.1,
            'roster_depth': 8,
            'star_player_ppg': 20.0,
            'top3_scorer_share': 0.5
        }

    # Sum projected stats DIRECTLY (PPG is already each player's per-game contribution)
    # No need for minutes_share weighting - a player averaging 20 PPG contributes 20 pts/game
    total_pts = sum(p.get('proj_ppg', 0) for p in roster_projections)
    total_reb = sum(p.get('proj_rpg', 0) for p in roster_projections)
    total_ast = sum(p.get('proj_apg', 0) for p in roster_projections)

    # Weighted averages for efficiency stats (weight by minutes played)
    total_minutes = sum(p.get('mpg', 0) for p in roster_projections)
    if total_minutes > 0:
        weighted_usage = sum(p.get('usage_pct', 20) * p.get('mpg', 0) for p in roster_projections) / total_minutes
        weighted_ts = sum(p.get('ts_pct', 0.55) * p.get('mpg', 0) for p in roster_projections) / total_minutes
        weighted_pie = sum(p.get('pie', 0.1) * p.get('mpg', 0) for p in roster_projections) / total_minutes
    else:
        weighted_usage = 20.0
        weighted_ts = 0.55
        weighted_pie = 0.1

    # Roster depth: players with 15+ minutes
    roster_depth = sum(1 for p in roster_projections if p.get('mpg', 0) >= 15)

    # Star player impact (use original PPG, not adjusted)
    star_ppg = max((p.get('ppg', 0) for p in roster_projections), default=0)

    # Top 3 scorer concentration
    sorted_by_pts = sorted(roster_projections, key=lambda x: x.get('ppg', 0), reverse=True)
    top3_pts = sum(p.get('ppg', 0) for p in sorted_by_pts[:3])
    total_raw_pts = sum(p.get('ppg', 0) for p in roster_projections)
    top3_share = top3_pts / total_raw_pts if total_raw_pts > 0 else 0.5

    return {
        'proj_team_pts': total_pts,  # Direct sum of player PPGs
        'proj_team_reb': total_reb,  # Direct sum of player RPGs
        'proj_team_ast': total_ast,  # Direct sum of player APGs
        'weighted_usage': weighted_usage,
        'weighted_ts_pct': weighted_ts,
        'weighted_pie': weighted_pie,
        'roster_depth': roster_depth,
        'star_player_ppg': star_ppg,
        'top3_scorer_share': top3_share
    }


# ============================================================================
# MAIN API
# ============================================================================

def get_player_projection_features(engine, team_id: int, opponent_id: int,
                                     as_of_date: str,
                                     excluded_players: List[str] = None) -> Dict[str, float]:
    """
    Main function to get player-based features for a team vs opponent matchup.

    This is the full pipeline:
    1. Get league averages (baseline for adjustments)
    2. Get opponent's defensive stats (for adjustments)
    3. Get expected roster for team (excluding injured players)
    4. Get each player's season averages
    5. Adjust each player's projections for opponent
    6. Aggregate to team-level features

    Args:
        engine: SQLAlchemy database engine
        team_id: ID of the team we're projecting
        opponent_id: ID of the opponent (for defensive adjustments)
        as_of_date: Date of the game (YYYY-MM-DD)
        excluded_players: List of player names to exclude (e.g., injured players)

    Returns:
        dict: Team-level features based on player projections
    """
    if excluded_players is None:
        excluded_players = []
    # Step 1: Get league averages
    league_avg = get_league_averages(engine, as_of_date)

    # Step 2: Get opponent's defensive profile
    opp_defense = get_team_defensive_stats(engine, opponent_id, as_of_date)

    # Step 3: Get expected roster (excluding injured players)
    roster = get_expected_roster(engine, team_id, as_of_date, excluded_players=excluded_players)

    if not roster:
        # Return default values if no roster data
        return {
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

    # Step 4 & 5: Get player stats and adjust for opponent
    roster_projections = []

    for player in roster:
        player_stats = get_player_season_averages(engine, player['player_id'], as_of_date)

        if player_stats is None:
            continue

        # Add roster info
        player_stats['minutes_share'] = player['minutes_share']
        player_stats['player_name'] = f"{player['first_name']} {player['last_name']}"

        # Adjust for opponent
        adjusted = adjust_player_stats_for_opponent(player_stats, opp_defense, league_avg)

        if adjusted:
            roster_projections.append(adjusted)

    # Step 6: Aggregate to team level
    team_features = aggregate_roster_projections(roster_projections)

    # Format output with consistent naming
    return {
        'PROJ_PTS_FROM_PLAYERS': team_features['proj_team_pts'],
        'PROJ_REB_FROM_PLAYERS': team_features['proj_team_reb'],
        'PROJ_AST_FROM_PLAYERS': team_features['proj_team_ast'],
        'WEIGHTED_AVG_USAGE': team_features['weighted_usage'],
        'WEIGHTED_AVG_TS_PCT': team_features['weighted_ts_pct'],
        'WEIGHTED_AVG_PIE': team_features['weighted_pie'],
        'ROSTER_DEPTH_SCORE': team_features['roster_depth'],
        'STAR_PLAYER_IMPACT': team_features['star_player_ppg'],
        'TOP_3_SCORER_SHARE': team_features['top3_scorer_share'],
        'PLAYER_DATA_QUALITY': 1.0 if len(roster_projections) >= 5 else 0.5
    }


def get_matchup_player_features(engine, home_team_id: int, away_team_id: int,
                                  as_of_date: str,
                                  home_excluded: List[str] = None,
                                  away_excluded: List[str] = None) -> Dict[str, float]:
    """
    Get player-based features for a full matchup (both teams).

    Args:
        engine: SQLAlchemy database engine
        home_team_id: Home team's NBA ID
        away_team_id: Away team's NBA ID
        as_of_date: Date of the game (YYYY-MM-DD)
        home_excluded: List of home team player names to exclude (injured)
        away_excluded: List of away team player names to exclude (injured)

    Returns:
        dict: HOME_, AWAY_, and DIFF_ prefixed features
    """
    if home_excluded is None:
        home_excluded = []
    if away_excluded is None:
        away_excluded = []

    # Get features for each team (adjusted for their opponent, excluding injured)
    home_features = get_player_projection_features(engine, home_team_id, away_team_id, as_of_date,
                                                    excluded_players=home_excluded)
    away_features = get_player_projection_features(engine, away_team_id, home_team_id, as_of_date,
                                                    excluded_players=away_excluded)

    matchup = {}

    # Add prefixed features
    for key, value in home_features.items():
        matchup[f'HOME_{key}'] = value

    for key, value in away_features.items():
        matchup[f'AWAY_{key}'] = value

    # Calculate differentials
    for key in home_features.keys():
        if key != 'PLAYER_DATA_QUALITY':  # Don't diff quality flag
            matchup[f'DIFF_{key}'] = home_features[key] - away_features[key]

    return matchup


# ============================================================================
# TESTING / DEBUG
# ============================================================================

def print_roster_projections(engine, team_id: int, opponent_id: int, as_of_date: str):
    """Debug function to print detailed player projections."""
    print(f"\n{'='*70}")
    print(f"PLAYER PROJECTIONS FOR TEAM {team_id} vs {opponent_id}")
    print(f"As of: {as_of_date}")
    print('='*70)

    # Get data
    league_avg = get_league_averages(engine, as_of_date)
    opp_defense = get_team_defensive_stats(engine, opponent_id, as_of_date)
    roster = get_expected_roster(engine, team_id, as_of_date)

    print(f"\nLeague Averages:")
    print(f"  Pace: {league_avg['pace']:.1f}")
    print(f"  Defensive Rating: {league_avg['defensive_rating']:.1f}")

    print(f"\nOpponent Defensive Profile:")
    print(f"  Pace: {opp_defense['pace']:.1f}")
    print(f"  Defensive Rating: {opp_defense['defensive_rating']:.1f}")

    pace_factor = opp_defense['pace'] / league_avg['pace']
    drtg_factor = opp_defense['defensive_rating'] / league_avg['defensive_rating']
    print(f"\nAdjustment Factors:")
    print(f"  Pace factor: {pace_factor:.3f}")
    print(f"  DRtg factor: {drtg_factor:.3f}")

    print(f"\n{'Player':<25} {'MPG':>6} {'PPG':>6} {'Adj PPG':>8} {'RPG':>6} {'APG':>6}")
    print('-'*70)

    for player in roster[:10]:  # Top 10 by minutes
        stats = get_player_season_averages(engine, player['player_id'], as_of_date)
        if stats is None:
            continue

        stats['minutes_share'] = player['minutes_share']
        adjusted = adjust_player_stats_for_opponent(stats, opp_defense, league_avg)

        name = f"{player['first_name']} {player['last_name']}"
        print(f"{name:<25} {stats['mpg']:>6.1f} {stats['ppg']:>6.1f} "
              f"{adjusted['proj_ppg']:>8.1f} {stats['rpg']:>6.1f} {stats['apg']:>6.1f}")

    # Final aggregation
    features = get_player_projection_features(engine, team_id, opponent_id, as_of_date)
    print(f"\nAggregated Team Projections:")
    for key, value in features.items():
        print(f"  {key}: {value:.2f}" if isinstance(value, float) else f"  {key}: {value}")


# ============================================================================
# MAIN (for testing)
# ============================================================================

if __name__ == '__main__':
    import sqlalchemy as sql

    def create_engine():
        host = 'localhost'
        user = 'kaiyamamoto'
        password = 'KN!yoWMhiH8cBvD'
        port = '3306'
        database = 'nba_data'
        connection_string = f'mysql://{user}:{password}@{host}:{port}/{database}'
        return sql.create_engine(connection_string)

    engine = create_engine()

    # Test with Boston Celtics vs Los Angeles Lakers
    # Team IDs: Celtics = 1610612738, Lakers = 1610612747
    CELTICS = 1610612738
    LAKERS = 1610612747

    print("\n" + "="*70)
    print("TESTING PLAYER PROJECTION MODULE")
    print("="*70)

    # Test individual functions
    print("\n1. Testing get_expected_roster...")
    roster = get_expected_roster(engine, CELTICS, '2024-12-15')
    print(f"   Found {len(roster)} players in rotation")

    print("\n2. Testing get_team_defensive_stats...")
    defense = get_team_defensive_stats(engine, LAKERS, '2024-12-15')
    print(f"   Lakers DRtg: {defense['defensive_rating']:.1f}, Pace: {defense['pace']:.1f}")

    print("\n3. Testing full projection pipeline...")
    features = get_player_projection_features(engine, CELTICS, LAKERS, '2024-12-15')
    print("   Features:")
    for k, v in features.items():
        print(f"     {k}: {v:.2f}" if isinstance(v, float) else f"     {k}: {v}")

    print("\n4. Testing matchup features...")
    matchup = get_matchup_player_features(engine, CELTICS, LAKERS, '2024-12-15')
    print(f"   Generated {len(matchup)} matchup features")

    print("\n5. Detailed roster breakdown...")
    print_roster_projections(engine, CELTICS, LAKERS, '2024-12-15')

    engine.dispose()
    print("\nDone!")
