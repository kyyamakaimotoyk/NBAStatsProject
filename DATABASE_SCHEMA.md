# NBA Database Schema Documentation

This document describes the MySQL database schema for the NBA Stats Project. The database contains 36 tables with game-level and player-level statistics dating from 1995 to present.

## Database Connection

- **Host**: localhost
- **Port**: 3306
- **Database**: nba_data

---

## Table Categories

| Category | Tables | Description |
|----------|--------|-------------|
| Core | 3 | Games list, teams, players |
| Boxscore - Team | 8 | Team-level game stats |
| Boxscore - Player | 9 | Player-level game stats |
| Game Summary | 14 | Game metadata, officials, arena info |
| System | 1 | Import tracking |

---

## Core Tables

### `game_list` (80,772 rows)
Primary table for all games. **One row per team per game** (2 rows per game).

| Column | Type | Description |
|--------|------|-------------|
| GAME_ID | BIGINT | Unique game identifier (e.g., 0022400001) |
| GAME_DATE | DATE | Date of the game |
| TEAM_ID | BIGINT | Team identifier |
| TEAM_ABBREVIATION | VARCHAR | 3-letter team code (LAL, BOS, etc.) |
| TEAM_NAME | VARCHAR | Full team name |
| MATCHUP | VARCHAR | Game matchup (e.g., "LAL vs. BOS" or "LAL @ BOS") |
| WL | CHAR(1) | Win/Loss result (W or L) |
| PTS | INT | Points scored |
| FGM | INT | Field goals made |
| FGA | INT | Field goals attempted |
| FG_PCT | FLOAT | Field goal percentage |
| FG3M | INT | 3-point field goals made |
| FG3A | INT | 3-point field goals attempted |
| FG3_PCT | FLOAT | 3-point percentage |
| FTM | INT | Free throws made |
| FTA | INT | Free throws attempted |
| FT_PCT | FLOAT | Free throw percentage |
| OREB | INT | Offensive rebounds |
| DREB | INT | Defensive rebounds |
| REB | INT | Total rebounds |
| AST | INT | Assists |
| STL | INT | Steals |
| BLK | INT | Blocks |
| TOV | INT | Turnovers |
| PF | INT | Personal fouls |
| PLUS_MINUS | INT | Point differential |

**Key insight**: `MATCHUP` contains "vs." for home games and "@" for away games.

---

### `nba_teams` (30 rows)
Reference table for all NBA teams.

| Column | Type | Description |
|--------|------|-------------|
| id | BIGINT | Team ID |
| full_name | VARCHAR | Full team name |
| abbreviation | VARCHAR | 3-letter code |
| nickname | VARCHAR | Team nickname |
| city | VARCHAR | Team city |
| state | VARCHAR | Team state |
| year_founded | INT | Year franchise founded |

---

### `nba_players` (5,125 rows)
Reference table for all NBA players.

| Column | Type | Description |
|--------|------|-------------|
| id | BIGINT | Player ID |
| full_name | VARCHAR | Player full name |
| first_name | VARCHAR | First name |
| last_name | VARCHAR | Last name |
| is_active | BOOLEAN | Currently active |

---

## Team Boxscore Tables

All team boxscore tables have **~79,000 rows** (one per team per game).

### `boxscoreadvancedv3_team`
Advanced efficiency metrics.

| Column | Type | Description |
|--------|------|-------------|
| gameId | BIGINT | Game identifier |
| teamId | BIGINT | Team identifier |
| offensiveRating | FLOAT | Points scored per 100 possessions |
| defensiveRating | FLOAT | Points allowed per 100 possessions |
| netRating | FLOAT | Offensive - Defensive rating |
| pace | FLOAT | Possessions per 48 minutes |
| possessions | FLOAT | Total possessions |
| effectiveFieldGoalPercentage | FLOAT | FG% weighted for 3-pointers |
| trueShootingPercentage | FLOAT | Points per shot attempt |
| assistPercentage | FLOAT | % of FGs that were assisted |
| assistToTurnover | FLOAT | Assist to turnover ratio |
| offensiveReboundPercentage | FLOAT | % of available offensive rebounds |
| defensiveReboundPercentage | FLOAT | % of available defensive rebounds |
| turnoverRatio | FLOAT | Turnovers per 100 possessions |
| PIE | FLOAT | Player Impact Estimate (team aggregate) |

---

### `boxscorefourfactorsv3_team`
Dean Oliver's Four Factors of basketball success.

| Column | Type | Description |
|--------|------|-------------|
| gameId | BIGINT | Game identifier |
| teamId | BIGINT | Team identifier |
| effectiveFieldGoalPercentage | FLOAT | Shooting efficiency |
| freeThrowAttemptRate | FLOAT | FTA / FGA (getting to the line) |
| teamTurnoverPercentage | FLOAT | Turnover rate |
| offensiveReboundPercentage | FLOAT | Second chance opportunities |
| oppEffectiveFieldGoalPercentage | FLOAT | Opponent shooting efficiency |
| oppFreeThrowAttemptRate | FLOAT | Opponent FTA / FGA |
| oppTeamTurnoverPercentage | FLOAT | Opponent turnover rate |
| oppOffensiveReboundPercentage | FLOAT | Opponent second chances |

---

### `boxscorehustlev2_team`
Effort and hustle statistics (available from ~2016).

| Column | Type | Description |
|--------|------|-------------|
| gameId | BIGINT | Game identifier |
| teamId | BIGINT | Team identifier |
| contestedShots | INT | Total shots contested |
| contestedShots2pt | INT | 2-point shots contested |
| contestedShots3pt | INT | 3-point shots contested |
| deflections | INT | Passes deflected |
| chargesDrawn | INT | Offensive fouls drawn |
| screenAssists | INT | Screens leading to scores |
| looseBallsRecoveredTotal | INT | Loose balls recovered |
| boxOuts | INT | Box outs |

---

### `boxscoreplayertrackv3_team`
Player tracking data from cameras (available from ~2014).

| Column | Type | Description |
|--------|------|-------------|
| gameId | BIGINT | Game identifier |
| teamId | BIGINT | Team identifier |
| speed | FLOAT | Average speed (mph) |
| distance | FLOAT | Total distance traveled (miles) |
| reboundChancesTotal | INT | Rebound opportunities |
| touches | INT | Ball touches |
| passes | INT | Passes made |
| secondaryAssists | INT | Hockey assists |
| contestedFieldGoalsMade | INT | Contested shot makes |
| contestedFieldGoalsAttempted | INT | Contested shot attempts |
| uncontestedFieldGoalsMade | INT | Open shot makes |
| uncontestedFieldGoalsAttempted | INT | Open shot attempts |
| defendedAtRimFieldGoalsMade | INT | Rim FGM allowed |
| defendedAtRimFieldGoalsAttempted | INT | Rim FGA faced |

---

### `boxscoremiscv3_team`
Miscellaneous situational scoring.

| Column | Type | Description |
|--------|------|-------------|
| gameId | BIGINT | Game identifier |
| teamId | BIGINT | Team identifier |
| pointsOffTurnovers | INT | Points scored off turnovers |
| pointsSecondChance | INT | Second chance points |
| pointsFastBreak | INT | Fast break points |
| pointsPaint | INT | Points in the paint |
| oppPointsOffTurnovers | INT | Opponent points off turnovers |
| oppPointsSecondChance | INT | Opponent second chance points |
| oppPointsFastBreak | INT | Opponent fast break points |
| oppPointsPaint | INT | Opponent paint points |
| foulsDrawn | INT | Fouls drawn |

---

### `boxscorescoringv3_team`
Scoring breakdown and shot distribution.

| Column | Type | Description |
|--------|------|-------------|
| gameId | BIGINT | Game identifier |
| teamId | BIGINT | Team identifier |
| percentageFieldGoalsAttempted2pt | FLOAT | % of shots that are 2-pointers |
| percentageFieldGoalsAttempted3pt | FLOAT | % of shots that are 3-pointers |
| percentagePoints2pt | FLOAT | % of points from 2-pointers |
| percentagePoints3pt | FLOAT | % of points from 3-pointers |
| percentagePointsPaint | FLOAT | % of points in paint |
| percentagePointsFastBreak | FLOAT | % of points from fast breaks |
| percentageAssistedFGM | FLOAT | % of makes that were assisted |
| percentageUnassistedFGM | FLOAT | % of makes that were unassisted |

---

### `boxscoretraditionalv3_team`
Traditional box score statistics.

| Column | Type | Description |
|--------|------|-------------|
| gameId | BIGINT | Game identifier |
| teamId | BIGINT | Team identifier |
| minutes | VARCHAR | Minutes played |
| fieldGoalsMade | INT | Field goals made |
| fieldGoalsAttempted | INT | Field goals attempted |
| fieldGoalsPercentage | FLOAT | Field goal % |
| threePointersMade | INT | 3-pointers made |
| threePointersAttempted | INT | 3-pointers attempted |
| threePointersPercentage | FLOAT | 3-point % |
| freeThrowsMade | INT | Free throws made |
| freeThrowsAttempted | INT | Free throws attempted |
| freeThrowsPercentage | FLOAT | Free throw % |
| reboundsOffensive | INT | Offensive rebounds |
| reboundsDefensive | INT | Defensive rebounds |
| reboundsTotal | INT | Total rebounds |
| assists | INT | Assists |
| steals | INT | Steals |
| blocks | INT | Blocks |
| turnovers | INT | Turnovers |
| foulsPersonal | INT | Personal fouls |
| points | INT | Points |
| plusMinusPoints | INT | Plus/minus |

---

### `boxscoreusagev3_team`
Usage statistics (how team distributes shots/possessions).

| Column | Type | Description |
|--------|------|-------------|
| gameId | BIGINT | Game identifier |
| teamId | BIGINT | Team identifier |
| usagePercentage | FLOAT | Usage rate |
| percentageFieldGoalsMade | FLOAT | FG% contribution |
| percentageFieldGoalsAttempted | FLOAT | FGA share |
| percentageThreePointersMade | FLOAT | 3PM contribution |
| percentageThreePointersAttempted | FLOAT | 3PA share |
| percentageFreeThrowsMade | FLOAT | FTM contribution |
| percentageFreeThrowsAttempted | FLOAT | FTA share |
| percentageReboundsOffensive | FLOAT | OREB share |
| percentageReboundsDefensive | FLOAT | DREB share |
| percentageReboundsTotal | FLOAT | REB share |
| percentageAssists | FLOAT | AST share |
| percentageTurnovers | FLOAT | TOV share |
| percentageSteals | FLOAT | STL share |
| percentageBlocks | FLOAT | BLK share |
| percentagePoints | FLOAT | PTS share |

---

## Player Boxscore Tables

Player-level tables mirror team tables with **~950,000 rows** each. Additional columns include:

| Column | Type | Description |
|--------|------|-------------|
| personId | BIGINT | Player identifier |
| firstName | VARCHAR | Player first name |
| familyName | VARCHAR | Player last name |
| position | VARCHAR | Position played |
| jerseyNum | VARCHAR | Jersey number |
| comment | VARCHAR | Injury/scratch status |

Tables:
- `boxscoreadvancedv3_player`
- `boxscorefourfactorsv3_player`
- `boxscorehustlev2_player`
- `boxscoreplayertrackv3_player`
- `boxscoremiscv3_player`
- `boxscorescoringv3_player`
- `boxscoretraditionalv3_player`
- `boxscoreusagev3_player`
- `boxscoredefensivev2_player` (matchup defensive stats)

---

## Game Summary Tables

### `boxscoresummaryv2_game_info` / `boxscoresummaryv3_game_info`
Game metadata including attendance and duration.

### `boxscoresummaryv2_referee` / `boxscoresummaryv3_officials`
Officials assigned to each game.

### `boxscoresummaryv3_arena_info`
Arena details for each game.

### `boxscoresummaryv3_line_score`
Quarter-by-quarter scores.

### `boxscoresummaryv3_last_five_meetings`
Results of last 5 meetings between teams.

---

## System Tables

### `importedgamesmemory` (40,309 rows)
Tracks which games have been imported to prevent duplicates.

| Column | Type | Description |
|--------|------|-------------|
| GAME_ID | VARCHAR | Game identifier |
| import_date | DATETIME | When the game was imported |

---

## Key Relationships

```
game_list.GAME_ID  <-->  boxscore*_team.gameId
game_list.TEAM_ID  <-->  boxscore*_team.teamId
game_list.TEAM_ID  <-->  nba_teams.id
boxscore*_player.personId  <-->  nba_players.id
```

---

## Data Coverage

| Statistic Type | Available From |
|---------------|----------------|
| Traditional box scores | 1995 |
| Advanced stats | 1996 |
| Four factors | 1996 |
| Player tracking | 2013-14 |
| Hustle stats | 2015-16 |

---

## Common Queries

### Get all games for a team in a season
```sql
SELECT * FROM game_list
WHERE TEAM_ABBREVIATION = 'LAL'
  AND GAME_DATE BETWEEN '2023-10-01' AND '2024-06-30'
ORDER BY GAME_DATE;
```

### Get team stats with advanced metrics for a game
```sql
SELECT gl.*, adv.*
FROM game_list gl
JOIN boxscoreadvancedv3_team adv
  ON gl.GAME_ID = adv.gameId AND gl.TEAM_ID = adv.teamId
WHERE gl.GAME_ID = '0022400001';
```

### Get a team's season averages
```sql
SELECT
  TEAM_ABBREVIATION,
  AVG(PTS) as avg_pts,
  AVG(offensiveRating) as avg_ortg,
  AVG(defensiveRating) as avg_drtg
FROM game_list gl
JOIN boxscoreadvancedv3_team adv
  ON gl.GAME_ID = adv.gameId AND gl.TEAM_ID = adv.teamId
WHERE GAME_DATE >= '2024-10-01'
GROUP BY TEAM_ABBREVIATION
ORDER BY avg_pts DESC;
```

---

## Database Indexes (Added 2025-12-06)

Performance indexes were added to dramatically improve query speed for player impact calculations and feature engineering.

### Indexes Created

| Table | Index Name | Columns | Purpose |
|-------|------------|---------|---------|
| `game_list` | `idx_game_list_team_date` | (TEAM_ID, GAME_DATE) | Fast team history lookups |
| `game_list` | `idx_game_list_game_id` | (GAME_ID) | Fast game joins |
| `boxscoretraditionalv3_player` | `idx_trad_game_team_person` | (gameId, teamId, personId) | Player stat queries |
| `boxscoreadvancedv3_player` | `idx_adv_game_person` | (gameId, personId) | Advanced stat joins |
| `boxscoreplayertrackv3_player` | `idx_track_game_person` | (gameId, personId) | DNP/DND/NWT lookups |

### Performance Impact

| Query Type | Before Indexes | After Indexes | Speedup |
|-----------|----------------|---------------|---------|
| Player historical impact | 5.99s | 0.09s | **66x** |
| Team game history | ~4s | ~0.1s | **40x** |

### SQL to Create Indexes

```sql
-- game_list indexes
CREATE INDEX idx_game_list_team_date ON game_list (TEAM_ID, GAME_DATE);
CREATE INDEX idx_game_list_game_id ON game_list (GAME_ID);

-- Player boxscore indexes
CREATE INDEX idx_trad_game_team_person ON boxscoretraditionalv3_player (gameId, teamId, personId);
CREATE INDEX idx_adv_game_person ON boxscoreadvancedv3_player (gameId, personId);
CREATE INDEX idx_track_game_person ON boxscoreplayertrackv3_player (gameId, personId);
```

---

## Notes

1. **Game IDs**: Format is `00XXYYZZZZ` where XX=season type (22=regular), YY=season year offset, ZZZZ=game number
2. **Date Range**: Database contains games from 1995-96 season to present
3. **Missing Data**: Some advanced stats (tracking, hustle) only available from 2013+
4. **Home/Away**: Determined from `MATCHUP` column - "vs." = home, "@" = away
5. **DNP/DND/NWT Detection**: The `comment` column in `boxscoreplayertrackv3_player` contains player status:
   - `DNP` = Did Not Play (Coach's Decision, Injury/Illness, Rest)
   - `DND` = Did Not Dress (Injury/Illness, specific injuries, Rest)
   - `NWT` = Not With Team (Personal Reasons, Suspension, Illness)
