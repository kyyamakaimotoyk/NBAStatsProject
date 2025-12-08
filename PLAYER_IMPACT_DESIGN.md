# Player Impact Model: Design Document

> **Status**: ✅ IMPLEMENTED (2025-12-06)
>
> Core functionality complete. See `player_impact.py` for implementation.

## Problem Statement

When predicting NBA game outcomes, we need to account for player availability (injuries, rest).
Simply adding/removing a player's PPG from team totals is **incorrect** because:

1. **The 240-minute constraint**: A team plays exactly 240 player-minutes per game (48 min × 5 positions)
2. **Minutes redistribution**: When a star is out, their minutes go to other players
3. **Usage redistribution**: Other players get more shots/touches
4. **Efficiency changes**: Players may be less efficient with increased workload
5. **Intangibles**: Playmaking, spacing, defensive attention are hard to quantify

## Proposed Solution: Per-Minute Stats + Historical Impact Analysis

### Data Model

```
Player Game Stats (per-minute basis):
├── PTS_PER_MIN      # Points per minute played
├── REB_PER_MIN      # Rebounds per minute played
├── AST_PER_MIN      # Assists per minute played
├── USAGE_RATE       # % of team possessions used while on court
├── NET_RATING       # Team point differential per 100 poss while on court
└── MINUTES          # Minutes played

Player Impact (calculated from historical games):
├── ON_COURT_NET_RTG     # Team net rating with player on court
├── OFF_COURT_NET_RTG    # Team net rating with player off court
├── ON_OFF_DIFF          # Difference (player's "impact")
├── GAMES_MISSED_MARGIN  # Team margin in games player missed
├── GAMES_PLAYED_MARGIN  # Team margin in games player played
└── AVAILABILITY_IMPACT  # Difference in team margin (WITH - WITHOUT)

Minutes Redistribution (per player pair):
├── WHEN_X_OUT           # Player X who is absent
├── MINUTES_ABSORBED_BY  # Player Y who absorbs minutes
├── AVG_MINUTES_INCREASE # How many extra minutes Y plays when X is out
└── EFFICIENCY_CHANGE    # How Y's efficiency changes with more minutes
```

### Algorithm

#### Step 1: Calculate Per-Minute Stats

```python
def get_player_per_minute_stats(engine, player_id, as_of_date):
    """
    Get player's per-minute production rates.

    Returns:
        {
            'pts_per_min': 0.65,    # e.g., 24 PPG / 37 MPG = 0.65
            'reb_per_min': 0.22,
            'ast_per_min': 0.19,
            'avg_minutes': 37.0,
            'usage_rate': 28.5,
            'true_shooting': 0.58
        }
    """
```

#### Step 2: Calculate Historical Player Impact

```python
def get_player_availability_impact(engine, player_id, team_id, as_of_date):
    """
    Compare team performance WITH vs WITHOUT this player.

    Query games where player:
    - Played 20+ minutes (WITH)
    - Was OUT based on comment field (WITHOUT):
      - DNP = Did Not Play (Coach's Decision, Injury/Illness, Rest)
      - DND = Did Not Dress (Injury/Illness, specific injuries, Rest)
      - NWT = Not With Team (Personal Reasons, Suspension, Illness)

    Returns:
        {
            'games_with': 45,
            'games_without': 8,
            'margin_with': +5.2,      # Team wins by 5.2 avg when player plays
            'margin_without': -3.1,   # Team loses by 3.1 avg when player out
            'availability_impact': +8.3,  # The difference
            'pts_with': 118.5,
            'pts_without': 109.2,
            'pts_impact': +9.3
        }
    """
```

#### Step 3: Calculate Minutes Redistribution Pattern

```python
def get_minutes_redistribution(engine, player_id, team_id, as_of_date):
    """
    When player X is out, who absorbs their minutes?

    Returns:
        [
            {'player_id': 123, 'name': 'Austin Reaves', 'minutes_increase': +8.2},
            {'player_id': 456, 'name': 'D\'Angelo Russell', 'minutes_increase': +6.5},
            ...
        ]
    """
```

#### Step 4: Apply Efficiency Adjustment

```python
def adjust_for_increased_usage(player_stats, minutes_increase, historical_efficiency_curve):
    """
    When a player's minutes increase, their efficiency typically drops.

    Based on historical analysis:
    - +5 minutes → ~1% drop in TS%
    - +10 minutes → ~2.5% drop in TS%

    Returns adjusted stats.
    """
```

#### Step 5: Calculate Team Projection

```python
def project_team_performance(engine, team_id, opponent_id, game_date, injuries=[]):
    """
    Main function to project team performance accounting for injuries.

    Args:
        injuries: List of player_ids who are OUT

    Algorithm:
        1. Get expected roster (all players who might play)
        2. Remove injured players
        3. Redistribute minutes from injured to available players
        4. Calculate per-minute stats × expected minutes for each player
        5. Apply efficiency adjustments for increased workload
        6. Apply opponent adjustments (pace, defense)
        7. Sum to get team projections

    Returns:
        {
            'proj_pts': 112.5,
            'proj_margin': -3.2,  # Expected to lose by 3.2 if star is out
            'confidence': 0.75,
            'key_absences': ['LeBron James'],
            'biggest_impact': -8.3  # LeBron's availability impact
        }
    """
```

### Database Queries

#### Query 1: Player Per-Minute Stats

```sql
SELECT
    p.personId,
    AVG(p.points / NULLIF(TIME_TO_SEC(p.minutes)/60, 0)) as pts_per_min,
    AVG(p.reboundsTotal / NULLIF(TIME_TO_SEC(p.minutes)/60, 0)) as reb_per_min,
    AVG(p.assists / NULLIF(TIME_TO_SEC(p.minutes)/60, 0)) as ast_per_min,
    AVG(TIME_TO_SEC(p.minutes)/60) as avg_minutes,
    AVG(adv.usagePercentage) as usage_rate,
    AVG(adv.trueShootingPercentage) as true_shooting
FROM boxscoretraditionalv3_player p
JOIN boxscoreadvancedv3_player adv ON p.gameId = adv.gameId AND p.personId = adv.personId
JOIN game_list gl ON p.gameId = gl.GAME_ID AND p.teamId = gl.TEAM_ID
WHERE p.personId = ?
  AND gl.GAME_DATE < ?
  AND gl.GAME_DATE >= DATE_SUB(?, INTERVAL 60 DAY)
  AND TIME_TO_SEC(p.minutes)/60 > 5  -- Only games with meaningful minutes
GROUP BY p.personId
```

#### Query 2: Player Availability Impact

```sql
-- Compare team performance WITH vs WITHOUT player
-- Uses comment field from boxscoreplayertrackv3_player to detect OUT status (DNP/DND/NWT)
SELECT
    gl.GAME_ID,
    gl.GAME_DATE,
    gl.PLUS_MINUS as team_margin,
    COALESCE(p.minutes, '0:00') as player_minutes,
    track.comment as player_comment
FROM game_list gl
LEFT JOIN boxscoretraditionalv3_player p
    ON gl.GAME_ID = p.gameId AND gl.TEAM_ID = p.teamId AND p.personId = ?
LEFT JOIN boxscoreplayertrackv3_player track
    ON gl.GAME_ID = track.gameId AND p.personId = track.personId
WHERE gl.TEAM_ID = ?
  AND gl.GAME_DATE < ?
  AND gl.GAME_DATE >= DATE_SUB(?, INTERVAL 365 DAY)
  AND gl.WL IS NOT NULL

-- In Python, classify games:
-- WITH: minutes >= 20 AND NOT is_out
-- WITHOUT: comment starts with 'DNP' or 'DND' or 'NWT'
```

#### Query 3: Minutes Redistribution Pattern

```sql
-- When player X is out, who plays more?
WITH games_without_x AS (
    SELECT gl.GAME_ID
    FROM game_list gl
    LEFT JOIN boxscoretraditionalv3_player p
        ON gl.GAME_ID = p.gameId AND gl.TEAM_ID = p.teamId AND p.personId = ?
    WHERE gl.TEAM_ID = ?
      AND (p.personId IS NULL OR TIME_TO_SEC(p.minutes)/60 < 10)
      AND gl.GAME_DATE < ?
      AND gl.GAME_DATE >= DATE_SUB(?, INTERVAL 365 DAY)
),
games_with_x AS (
    SELECT gl.GAME_ID
    FROM game_list gl
    JOIN boxscoretraditionalv3_player p
        ON gl.GAME_ID = p.gameId AND gl.TEAM_ID = p.teamId AND p.personId = ?
    WHERE gl.TEAM_ID = ?
      AND TIME_TO_SEC(p.minutes)/60 >= 20
      AND gl.GAME_DATE < ?
      AND gl.GAME_DATE >= DATE_SUB(?, INTERVAL 365 DAY)
)
SELECT
    p.personId,
    AVG(CASE WHEN g.GAME_ID IN (SELECT GAME_ID FROM games_without_x)
             THEN TIME_TO_SEC(p.minutes)/60 END) as mins_when_x_out,
    AVG(CASE WHEN g.GAME_ID IN (SELECT GAME_ID FROM games_with_x)
             THEN TIME_TO_SEC(p.minutes)/60 END) as mins_when_x_plays,
    AVG(CASE WHEN g.GAME_ID IN (SELECT GAME_ID FROM games_without_x)
             THEN TIME_TO_SEC(p.minutes)/60 END) -
    AVG(CASE WHEN g.GAME_ID IN (SELECT GAME_ID FROM games_with_x)
             THEN TIME_TO_SEC(p.minutes)/60 END) as minutes_increase
FROM boxscoretraditionalv3_player p
JOIN game_list g ON p.gameId = g.GAME_ID AND p.teamId = g.TEAM_ID
WHERE p.teamId = ?
  AND p.personId != ?  -- Not the player who is out
  AND g.GAME_DATE < ?
GROUP BY p.personId
HAVING minutes_increase IS NOT NULL
ORDER BY minutes_increase DESC
```

### Integration with Injury Data

```python
def get_injury_report(game_date):
    """
    Fetch injury report from nbainjuries package or NBA API.

    Returns:
        [
            {
                'player_id': 2544,
                'player_name': 'LeBron James',
                'team': 'LAL',
                'status': 'OUT',  # OUT, DOUBTFUL, QUESTIONABLE, PROBABLE
                'injury': 'Left knee soreness'
            },
            ...
        ]
    """
    try:
        from nbainjuries import Injuries
        injuries = Injuries()
        return injuries.get_injuries(date=game_date)
    except ImportError:
        # Fallback: infer from recent playing time
        return infer_injuries_from_playing_time(game_date)
```

### Expected Outputs

For a game prediction with LeBron OUT:

```
=== LAKERS VS CELTICS PROJECTION ===

Injury Report:
  - LeBron James: OUT (left knee soreness)

Without LeBron:
  - Historical impact: -8.3 points (team wins by 5.2 with him, loses by 3.1 without)
  - Minutes redistributed:
    - Austin Reaves: 22 → 30 min (+8)
    - D'Angelo Russell: 28 → 34 min (+6)
    - Rui Hachimura: 24 → 30 min (+6)

Projected Team Stats:
  - Points: 109.2 (vs 118.5 with LeBron)
  - Margin: -5.5 (vs +2.8 with LeBron)

Confidence: MEDIUM (8 games sample without LeBron)
```

### Validation Plan

1. **Backtest on historical injuries**
   - Find games where stars were out
   - Compare predicted margin vs actual margin
   - Measure improvement over simple "subtract PPG" method

2. **Cross-validation**
   - Hold out 2024-25 season
   - Train impact models on 2021-2024 data
   - Test predictions on 2024-25 games with injuries

3. **Sanity checks**
   - Top players should have highest availability_impact
   - Minutes redistribution should sum to ~35 min (the star's minutes)
   - Projected team totals should still be ~100-120 points

## Implementation Priority

1. ~~**Phase 1**: Per-minute stats foundation (MUST HAVE)~~ ✅ DONE
2. ~~**Phase 2**: Historical availability impact (MUST HAVE)~~ ✅ DONE
3. **Phase 3**: Minutes redistribution (NICE TO HAVE) - Deferred
4. **Phase 4**: Usage-efficiency curve (NICE TO HAVE) - Deferred
5. ~~**Phase 5**: Injury data integration (MUST HAVE for real-time predictions)~~ ✅ DONE (manual via --injuries flag)

## Files Created/Modified

1. ✅ `player_impact.py` - Module with Historical WITH/WITHOUT impact calculations (DNP/DND/NWT detection)
2. ✅ `evaluate_impact_approaches.py` - Validation script comparing approaches
3. ✅ `predict_games.py` - Added `--injuries`, `--show-impacts`, `--no-shap` flags
4. ✅ `feature_engineering.py` - Added HOME/AWAY/DIFF_INJURY_IMPACT features (2025-12-06)

## Implementation Details (2025-12-06)

### Key Functions in `player_impact.py`:

```python
get_player_historical_impact(engine, player_id, team_id, as_of_date)
# Returns: impact, margin_with, margin_without, games_with, games_without, confidence, method

get_team_player_impacts(engine, team_id, as_of_date)
# Returns list of all significant players' impacts

calculate_injury_adjusted_margin(engine, team_id, opponent_id, baseline_margin, injuries_out)
# Returns adjusted margin after accounting for injuries
```

### Unified Monte Carlo Win Probability:

Instead of separate classifier, we derive P(win) from margin samples:
```python
# P(win) = proportion of margin samples > 0
win_prob = np.mean(margin_samples > 0)

# For injury adjustment - shift samples, recompute both
adjusted_samples = margin_samples + injury_adjustment
adjusted_margin = np.mean(adjusted_samples)
adjusted_win_prob = np.mean(adjusted_samples > 0)  # Consistent!
```

### Validation Results (8,823 games, 2015-2025):

| Approach | MAE | Correlation |
|----------|-----|-------------|
| Historical WITH/WITHOUT | **11.10** | **0.350** |
| Advanced (netRating) | 11.88 | 0.138 |

Historical approach wins by 0.78 points MAE and 2.5x better correlation.
