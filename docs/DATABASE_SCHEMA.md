# NBA database schema

The MySQL database behind the project: local `nba_data` on the home PC (the
research bench and the source of every ingest), and its cloud copy on RDS.

**How this doc is built.** This top part is hand-written: conventions,
relationships, queries. Everything below the GENERATED marker is rebuilt from
the live local database by `python scripts/gen_db_schema_doc.py` (read-only, about a
minute). It covers every table, where it lives, row counts, coverage, purpose, the
code that references it, columns and indexes. Regenerate after adding or changing
a table. A table without a description shows up under "Needs attention", and
`--check` exits 1. Give a new table one line in `TABLE_INFO` in the script.

Related: `docs/api_schema_report.md` shows, for the box-score tables, which code and
features read each column and whether nba_api still sends it. Feature selection lives in
`core/features.py`, not in any table.

## Where tables live

- **local → RDS (home ingest):** stats.nba.com blocks AWS, so the home PC fetches
  into local MySQL and `home_ingest_push.py` ships a trailing window as parquet to S3.
  The cloud's `s3_ingest_loader.py` upserts it into RDS. That covers game_list, the
  box-score and summary tables, nba_teams / nba_players, lineup snapshots, the official
  injury report and the schedule.
- **local + RDS (computed):** features, ELO, player impact, model registry and
  predictions are computed by pipeline stages in both places. RDS is the public record.
- **RDS only:** `live_scores` (ESPN poller) and `league_schedule`.
- **local only:** import bookkeeping, experiment-loop tables, gravity snapshots.

## Conventions

1. **Game ids:** `00TYYNNNNN`: T = season type (1 preseason, 2 regular season, 4
   playoffs, 5 play-in, 6 NBA Cup final), YY = season start year (26 = 2026-27),
   NNNNN = game number. Box-score tables store `gameId` as the zero-padded string;
   `game_list.GAME_ID` is a BIGINT without the leading zeros, so join on the value
   or `LPAD(GAME_ID, 10, '0')`.
2. **Seasons** roll over on Aug 1 everywhere in the code. `game_list.SEASON_ID` is
   `<T><YYYY>` (e.g. `22026` = 2026-27 regular season).
3. **Home / away:** `game_list.MATCHUP` contains `vs.` for the home team, `@` for the away team.
4. **Dates** are US Eastern game dates (`et_today()` in the ingest); the home PC runs on JST.
5. **Did not play:** `comment` in the player box scores (traditional, player tracking)
   carries `DNP` (coach's decision, injury, rest), `DND` (did not dress) or `NWT` (not
   with team). This is post-game information; pre-game availability comes from
   `historical_injury_report` (E7, E28).
6. **Raw API responses** are not in the database: they are archived as files under
   `data/raw_api/` (README "When nba_api or an endpoint changes").

## Key relationships

```
game_list (GAME_ID, TEAM_ID)  <->  boxscore*_team (gameId, teamId)
game_list.TEAM_ID             <->  nba_teams.id
boxscore*_player.personId     <->  nba_players.id  <->  historical_injury_report.player_id
game_list.GAME_ID             <->  features.GAME_ID (one row per game, home perspective)
                              <->  team_elo_pregame.game_id
                              <->  model_predictions.game_id
features.feature_set_version  ->   feature_set_current.version (the live snapshot)
```

## Common queries

All games for a team in a season:
```sql
SELECT * FROM game_list
WHERE TEAM_ABBREVIATION = 'LAL' AND SEASON_ID = '22026'
ORDER BY GAME_DATE;
```

Team box score with advanced metrics for one game:
```sql
SELECT gl.*, adv.*
FROM game_list gl
JOIN boxscoreadvancedv3_team adv
  ON adv.gameId = LPAD(gl.GAME_ID, 10, '0') AND adv.teamId = gl.TEAM_ID
WHERE gl.GAME_ID = 22600236;
```

The live feature snapshot:
```sql
SELECT f.* FROM features f
JOIN feature_set_current c ON f.feature_set_version = c.version;
```

## Performance indexes (added 2025-12-06)

Player-impact and feature queries depend on these: player historical impact went
from 6.0 s to 0.09 s. Recreate them after rebuilding a table:

```sql
CREATE INDEX idx_game_list_team_date ON game_list (TEAM_ID, GAME_DATE);
CREATE INDEX idx_game_list_game_id ON game_list (GAME_ID);
CREATE INDEX idx_trad_game_team_person ON boxscoretraditionalv3_player (gameId, teamId, personId);
CREATE INDEX idx_adv_game_person ON boxscoreadvancedv3_player (gameId, personId);
CREATE INDEX idx_track_game_person ON boxscoreplayertrackv3_player (gameId, personId);
```

The generated section lists every index that exists today.

<!-- BEGIN GENERATED: scripts/gen_db_schema_doc.py - do not edit by hand -->

*Generated 2026-11-16 from local MySQL `nba_data`: 51 tables, ~7.2M rows, 2.1 GB. RDS-only tables are listed without columns.*

**Needs attention**

- Not created yet (CREATE TABLE in sql/): `gravity_leaders_daily`

## Table index

| Table | Where | Rows | Coverage | Purpose | Referenced in |
|---|---|---|---|---|---|
| **Core** | | | | | |
| [`game_list`](#game_list) | local → RDS (home ingest) | ~83k | 1995-11-03 → 2026-11-15 | One row per team per game (LeagueGameFinder): result, traditional box score, MATCHUP (`vs.` = home, `@` = away). Spine of every team feature, ELO, grading. | `api/queries.py`, `api/schemas.py`, `data_engineering/api_schema_check.py`, `data_engineering/compute_elo.py` +24 |
| [`nba_players`](#nba_players) | local → RDS (home ingest) | ~5k | - | Static nba_api player list (replaced each ingest). | `data_engineering/historical_injury_scraper.py`, `data_engineering/home_ingest_push.py`, `data_engineering/main_refactored.py`, `modeling/serving_features.py` +1 |
| [`nba_teams`](#nba_teams) | local → RDS (home ingest) | 30 | - | Static nba_api team list (replaced each ingest). | `api/queries.py`, `data_engineering/historical_injury_scraper.py`, `data_engineering/home_ingest_push.py`, `data_engineering/main_refactored.py` +5 |
| **Box score - team** | | | | | |
| [`boxscoreadvancedv3_team`](#boxscoreadvancedv3_team) | local → RDS (home ingest) | ~82k | 1996-97 → 2026-27 | `BoxScoreAdvancedV3` frame 1, per team per game. Column usage and fill rates: [api_schema_report.md](api_schema_report.md). | `api/queries.py`, `data_engineering/api_schema_check.py`, `data_engineering/feature_engineering.py`, `data_engineering/home_ingest_push.py` +3 |
| [`boxscoredefensivev2_team`](#boxscoredefensivev2_team) | local → RDS (home ingest) | ~82k | 2016-17 → 2026-27 | `BoxScoreDefensiveV2` frame 1, per team per game. Column usage and fill rates: [api_schema_report.md](api_schema_report.md). | `data_engineering/api_schema_check.py`, `data_engineering/home_ingest_push.py`, `data_engineering/main_refactored.py` |
| [`boxscorefourfactorsv3_team`](#boxscorefourfactorsv3_team) | local → RDS (home ingest) | ~82k | 1996-97 → 2026-27 | `BoxScoreFourFactorsV3` frame 1, per team per game. Column usage and fill rates: [api_schema_report.md](api_schema_report.md). | `api/queries.py`, `data_engineering/api_schema_check.py`, `data_engineering/feature_engineering.py`, `data_engineering/home_ingest_push.py` +5 |
| [`boxscorehustlev2_team`](#boxscorehustlev2_team) | local → RDS (home ingest) | ~82k | 1998-99 → 2026-27 | `BoxScoreHustleV2` frame 1, per team per game. Column usage and fill rates: [api_schema_report.md](api_schema_report.md). | `api/queries.py`, `data_engineering/api_schema_check.py`, `data_engineering/backfill_from_raw.py`, `data_engineering/feature_engineering.py` +4 |
| [`boxscoremiscv3_team`](#boxscoremiscv3_team) | local → RDS (home ingest) | ~82k | 1996-97 → 2026-27 | `BoxScoreMiscV3` frame 1, per team per game. Column usage and fill rates: [api_schema_report.md](api_schema_report.md). | `api/queries.py`, `data_engineering/api_schema_check.py`, `data_engineering/backfill_from_raw.py`, `data_engineering/feature_engineering.py` +4 |
| [`boxscoreplayertrackv3_team`](#boxscoreplayertrackv3_team) | local → RDS (home ingest) | ~82k | 1996-97 → 2026-27 | `BoxScorePlayerTrackV3` frame 1, per team per game. Column usage and fill rates: [api_schema_report.md](api_schema_report.md). | `api/queries.py`, `data_engineering/api_schema_check.py`, `data_engineering/feature_engineering.py`, `data_engineering/home_ingest_push.py` +3 |
| [`boxscorescoringv3_team`](#boxscorescoringv3_team) | local → RDS (home ingest) | ~82k | 1996-97 → 2026-27 | `BoxScoreScoringV3` frame 1, per team per game. Column usage and fill rates: [api_schema_report.md](api_schema_report.md). | `api/queries.py`, `data_engineering/api_schema_check.py`, `data_engineering/feature_engineering.py`, `data_engineering/home_ingest_push.py` +3 |
| [`boxscoretraditionalv3_bench`](#boxscoretraditionalv3_bench) | local → RDS (home ingest) | ~163k | 1996-97 → 2026-27 | `BoxScoreTraditionalV3` frame 1, starters/bench split per team per game. Column usage and fill rates: [api_schema_report.md](api_schema_report.md). | `data_engineering/api_schema_check.py`, `data_engineering/home_ingest_push.py`, `data_engineering/main_refactored.py` |
| [`boxscoretraditionalv3_team`](#boxscoretraditionalv3_team) | local → RDS (home ingest) | ~82k | 1996-97 → 2026-27 | `BoxScoreTraditionalV3` frame 2, per team per game. Column usage and fill rates: [api_schema_report.md](api_schema_report.md). | `api/queries.py`, `data_engineering/api_schema_check.py`, `data_engineering/home_ingest_push.py`, `data_engineering/main_refactored.py` +2 |
| [`boxscoreusagev3_team`](#boxscoreusagev3_team) | local → RDS (home ingest) | ~82k | 1996-97 → 2026-27 | `BoxScoreUsageV3` frame 1, per team per game. Column usage and fill rates: [api_schema_report.md](api_schema_report.md). | `data_engineering/api_schema_check.py`, `data_engineering/home_ingest_push.py`, `data_engineering/main_refactored.py` |
| **Box score - player** | | | | | |
| [`boxscoreadvancedv3_player`](#boxscoreadvancedv3_player) | local → RDS (home ingest) | ~986k | 1996-97 → 2026-27 | `BoxScoreAdvancedV3` frame 0, per player per game. Column usage and fill rates: [api_schema_report.md](api_schema_report.md). | `data_engineering/api_schema_check.py`, `data_engineering/home_ingest_push.py`, `data_engineering/main_refactored.py`, `data_engineering/player_dataset.py` +3 |
| [`boxscoredefensivev2_player`](#boxscoredefensivev2_player) | local → RDS (home ingest) | ~248k | 2016-17 → 2026-27 | `BoxScoreDefensiveV2` frame 0, per player per game. Column usage and fill rates: [api_schema_report.md](api_schema_report.md). | `data_engineering/api_schema_check.py`, `data_engineering/home_ingest_push.py`, `data_engineering/main_refactored.py` |
| [`boxscorefourfactorsv3_player`](#boxscorefourfactorsv3_player) | local → RDS (home ingest) | ~986k | 1996-97 → 2026-27 | `BoxScoreFourFactorsV3` frame 0, per player per game. Column usage and fill rates: [api_schema_report.md](api_schema_report.md). | `data_engineering/api_schema_check.py`, `data_engineering/home_ingest_push.py`, `data_engineering/main_refactored.py` |
| [`boxscorehustlev2_player`](#boxscorehustlev2_player) | local → RDS (home ingest) | ~303k | 1998-99 → 2026-27 | `BoxScoreHustleV2` frame 0, per player per game. Column usage and fill rates: [api_schema_report.md](api_schema_report.md). | `data_engineering/api_schema_check.py`, `data_engineering/home_ingest_push.py`, `data_engineering/main_refactored.py`, `data_engineering/player_dataset.py` |
| [`boxscoremiscv3_player`](#boxscoremiscv3_player) | local → RDS (home ingest) | ~986k | 1996-97 → 2026-27 | `BoxScoreMiscV3` frame 0, per player per game. Column usage and fill rates: [api_schema_report.md](api_schema_report.md). | `data_engineering/api_schema_check.py`, `data_engineering/home_ingest_push.py`, `data_engineering/main_refactored.py`, `data_engineering/player_dataset.py` |
| [`boxscoreplayertrackv3_player`](#boxscoreplayertrackv3_player) | local → RDS (home ingest) | ~1.1M | 1996-97 → 2026-27 | `BoxScorePlayerTrackV3` frame 0, per player per game. Column usage and fill rates: [api_schema_report.md](api_schema_report.md). | `data_engineering/api_schema_check.py`, `data_engineering/feature_engineering.py`, `data_engineering/home_ingest_push.py`, `data_engineering/main_refactored.py` +2 |
| [`boxscorescoringv3_player`](#boxscorescoringv3_player) | local → RDS (home ingest) | ~986k | 1996-97 → 2026-27 | `BoxScoreScoringV3` frame 0, per player per game. Column usage and fill rates: [api_schema_report.md](api_schema_report.md). | `data_engineering/api_schema_check.py`, `data_engineering/home_ingest_push.py`, `data_engineering/main_refactored.py` |
| [`boxscoretraditionalv3_player`](#boxscoretraditionalv3_player) | local → RDS (home ingest) | ~1.0M | 1996-97 → 2026-27 | `BoxScoreTraditionalV3` frame 0, per player per game. Column usage and fill rates: [api_schema_report.md](api_schema_report.md). | `api/queries.py`, `data_engineering/api_schema_check.py`, `data_engineering/home_ingest_push.py`, `data_engineering/main_refactored.py` +7 |
| [`boxscoreusagev3_player`](#boxscoreusagev3_player) | local → RDS (home ingest) | ~985k | 1996-97 → 2026-27 | `BoxScoreUsageV3` frame 0, per player per game. Column usage and fill rates: [api_schema_report.md](api_schema_report.md). | `data_engineering/api_schema_check.py`, `data_engineering/home_ingest_push.py`, `data_engineering/main_refactored.py`, `data_engineering/player_impact.py` |
| **Game summary** | | | | | |
| [`boxscoresummaryv2_game_info`](#boxscoresummaryv2_game_info) | local → RDS (home ingest) | ~39k | 1996-03-08 → 2025-10-21 | `BoxScoreSummaryV2` frame 7, per game. Column usage and fill rates: [api_schema_report.md](api_schema_report.md). | `data_engineering/api_schema_check.py`, `data_engineering/home_ingest_push.py`, `data_engineering/main_refactored.py`, `orchestration/pipeline.py` |
| [`boxscoresummaryv2_inactive_players`](#boxscoresummaryv2_inactive_players) | local → RDS (home ingest) | ~148k | 1996-97 → 2025-26 | `BoxScoreSummaryV2` frame 3, per game. Column usage and fill rates: [api_schema_report.md](api_schema_report.md). | `data_engineering/api_schema_check.py`, `data_engineering/home_ingest_push.py`, `data_engineering/main_refactored.py` |
| [`boxscoresummaryv2_other_stats`](#boxscoresummaryv2_other_stats) | local → RDS (home ingest) | ~37k | 1995-96 → 2025-26 | `BoxScoreSummaryV2` frame 6, per game. Column usage and fill rates: [api_schema_report.md](api_schema_report.md). | `data_engineering/api_schema_check.py`, `data_engineering/home_ingest_push.py`, `data_engineering/main_refactored.py` |
| [`boxscoresummaryv2_referee`](#boxscoresummaryv2_referee) | local → RDS (home ingest) | ~91k | 1996-97 → 2025-26 | `BoxScoreSummaryV2` frame 2, per game. Column usage and fill rates: [api_schema_report.md](api_schema_report.md). | `data_engineering/api_schema_check.py`, `data_engineering/home_ingest_push.py`, `data_engineering/main_refactored.py` |
| [`boxscoresummaryv2_summary`](#boxscoresummaryv2_summary) | local → RDS (home ingest) | ~76k | 1996-97 → 2025-26 | `BoxScoreSummaryV2` frame 1, per game. Column usage and fill rates: [api_schema_report.md](api_schema_report.md). | `data_engineering/api_schema_check.py`, `data_engineering/home_ingest_push.py`, `data_engineering/main_refactored.py` |
| [`boxscoresummaryv3_arena_info`](#boxscoresummaryv3_arena_info) | local → RDS (home ingest) | ~2k | 2025-26 → 2026-27 | `BoxScoreSummaryV3` frame 2, per game. Column usage and fill rates: [api_schema_report.md](api_schema_report.md). | `data_engineering/api_schema_check.py`, `data_engineering/home_ingest_push.py`, `data_engineering/main_refactored.py` |
| [`boxscoresummaryv3_game_info`](#boxscoresummaryv3_game_info) | local → RDS (home ingest) | ~2k | 2025-10-02 → 2026-11-15 | `BoxScoreSummaryV3` frame 1, per game. Column usage and fill rates: [api_schema_report.md](api_schema_report.md). | `data_engineering/api_schema_check.py`, `data_engineering/home_ingest_push.py`, `data_engineering/main_refactored.py`, `orchestration/pipeline.py` |
| [`boxscoresummaryv3_game_summary`](#boxscoresummaryv3_game_summary) | local → RDS (home ingest) | ~2k | 2025-26 → 2026-27 | `BoxScoreSummaryV3` frame 0, per game. Column usage and fill rates: [api_schema_report.md](api_schema_report.md). | `data_engineering/api_schema_check.py`, `data_engineering/home_ingest_push.py`, `data_engineering/main_refactored.py` |
| [`boxscoresummaryv3_inactive_players`](#boxscoresummaryv3_inactive_players) | local → RDS (home ingest) | ~13k | 2025-26 → 2026-27 | `BoxScoreSummaryV3` frame 5, per game. Column usage and fill rates: [api_schema_report.md](api_schema_report.md). | `data_engineering/api_schema_check.py`, `data_engineering/home_ingest_push.py`, `data_engineering/main_refactored.py` |
| [`boxscoresummaryv3_last_five_meetings`](#boxscoresummaryv3_last_five_meetings) | local → RDS (home ingest) | ~82k | 2022-23 → 2026-27 | `BoxScoreSummaryV3` frame 6, per game. Column usage and fill rates: [api_schema_report.md](api_schema_report.md). | `data_engineering/api_schema_check.py`, `data_engineering/home_ingest_push.py`, `data_engineering/main_refactored.py` |
| [`boxscoresummaryv3_line_score`](#boxscoresummaryv3_line_score) | local → RDS (home ingest) | ~3k | 2025-26 → 2026-27 | `BoxScoreSummaryV3` frame 4, per game. Column usage and fill rates: [api_schema_report.md](api_schema_report.md). | `data_engineering/api_schema_check.py`, `data_engineering/home_ingest_push.py`, `data_engineering/main_refactored.py` |
| [`boxscoresummaryv3_officials`](#boxscoresummaryv3_officials) | local → RDS (home ingest) | ~5k | 2025-26 → 2026-27 | `BoxScoreSummaryV3` frame 3, per game. Column usage and fill rates: [api_schema_report.md](api_schema_report.md). | `data_engineering/api_schema_check.py`, `data_engineering/home_ingest_push.py`, `data_engineering/main_refactored.py` |
| [`boxscoresummaryv3_other_stats`](#boxscoresummaryv3_other_stats) | local → RDS (home ingest) | ~3k | 2025-26 → 2026-27 | `BoxScoreSummaryV3` frame 7, per game. Column usage and fill rates: [api_schema_report.md](api_schema_report.md). | `data_engineering/api_schema_check.py`, `data_engineering/home_ingest_push.py`, `data_engineering/main_refactored.py` |
| **Availability & context** | | | | | |
| `gravity_leaders_daily` | local only (not created yet) | - | - | Daily snapshot of GravityLeaders season-to-date player gravity (`gravity_snapshot.py`). Proposals E31/E32/P8. | `data_engineering/api_schema_check.py`, `data_engineering/gravity_snapshot.py` |
| [`historical_injury_report`](#historical_injury_report) | local → RDS (home ingest) | ~108k | 2022-01-01 → 2026-11-15 | Official NBA pre-game injury report, one row per player per report date (PDF scrape, `historical_injury_report.py`). Training + serving availability source (E7, E28). | `api/queries.py`, `data_engineering/historical_injury_scraper.py`, `data_engineering/home_ingest_push.py`, `data_engineering/player_impact.py` +4 |
| `league_schedule` | RDS only | - | - | League schedule (ScheduleLeagueV2) shipped by the home ingest, replaced each drop; the cloud's schedule source. | `api/advisor.py`, `api/queries.py`, `data_engineering/home_ingest_push.py`, `modeling/batch_predict_today.py` +1 |
| `live_scores` | RDS only | - | - | ESPN final scores polled every 30 min (`espn_score_poller.py`); grading and the site before game_list arrives. | `api/queries.py`, `data_engineering/espn_score_poller.py`, `modeling/prediction_tracker.py` |
| [`playoff_series_context`](#playoff_series_context) | local + RDS (computed) | ~2k | 1996-04-25 → 2026-05-13 | Series state per played playoff game (`series_context.py`). Not in the production feature set. | `core/features.py`, `data_engineering/feature_engineering.py`, `data_engineering/series_context.py` |
| [`team_lineup_snapshots`](#team_lineup_snapshots) | local → RDS (home ingest) | 450 | 2024-06-30 → 2026-03-31 | Team lineup aggregates from LeagueDashLineups per snapshot date (`lineup_features.py`, home only). E11 features, off in production. | `core/features.py`, `data_engineering/feature_engineering.py`, `data_engineering/home_ingest_push.py`, `data_engineering/lineup_features.py` |
| [`vegas_lines`](#vegas_lines) | local + RDS (VegasLinesStage) | ~6k | 2022-01-01 → 2026-06-13 | Market spreads/totals/moneylines (ESPN odds + Kaggle history). /accuracy market benchmark and player-model group G. | `api/queries.py`, `data_engineering/player_dataset.py`, `data_engineering/vegas_lines_espn.py`, `data_engineering/vegas_lines_kaggle_import.py` +2 |
| **Features & models** | | | | | |
| [`feature_set_current`](#feature_set_current) | local + RDS | 1 | - | Single-row pointer to the live feature_set_version. | `api/queries.py`, `core/features_io.py`, `modeling/predict_games.py`, `scripts/export_features_snapshot.py` |
| [`feature_set_versions`](#feature_set_versions) | local + RDS | 3 | 2026-07-03 → 2026-07-03 | Metadata per feature snapshot. | `core/features_io.py` |
| [`features`](#features) | local + RDS (FeaturesStage) | ~10k | 2022-01-01 → 2026-06-13 | Versioned team-game feature snapshots, PK (feature_set_version, GAME_ID); written by `feature_engineering.py` via `core/features_io.py`. Columns auto-evolve; production selection is `core/features.py`. | `api/queries.py`, `core/features_io.py`, `modeling/baseline_models.py`, `modeling/predict_games.py` +4 |
| [`model_registry`](#model_registry) | local + RDS | 176 | 2026-05-18 → 2026-07-16 | One row per trained / validated / experiment model bundle: lineage, metrics, bundle path (`core/model_registry.py`). | `core/experiment_db.py`, `core/model_registry.py`, `modeling/pytorch_nba_models.py`, `modeling/validate_models.py` +3 |
| [`player_impact`](#player_impact) | local + RDS (PlayerImpactStage) | ~18k | 2022-01-01 → 2026-06-03 | Per player per compute_date impact estimates (with/without), feeding the slot / availability / impact features. | `data_engineering/feature_engineering.py`, `data_engineering/player_impact.py`, `modeling/predict_games.py`, `orchestration/pipeline.py` |
| [`team_elo_pregame`](#team_elo_pregame) | local + RDS (weekly) | ~41k | 1995-11-03 → 2026-05-13 | Pre-game ELO per game (`compute_elo.py`). Serving computes ELO in memory (E28); the local copy can be stale. | `core/features.py`, `data_engineering/compute_elo.py`, `data_engineering/feature_engineering.py` |
| **Predictions** | | | | | |
| [`model_predictions`](#model_predictions) | local + RDS (RDS = public record) | ~15k | 2023-10-05 → 2026-06-13 | Team game predictions per model plus graded outcomes (`modeling/prediction_tracker.py`); the public track record. | `api/main.py`, `api/queries.py`, `data_engineering/espn_score_poller.py`, `modeling/batch_predict_today.py` +6 |
| [`player_predictions`](#player_predictions) | local + RDS | ~62k | 2023-10-24 → 2026-06-13 | Nightly player projections (/players). | `api/queries.py`, `modeling/player_predict.py`, `scripts/backfill_player_predictions.py` |
| **Experiments** | | | | | |
| [`experiment_comparisons`](#experiment_comparisons) | local only | 701 | 2026-07-16 → 2026-07-17 | Paired-test rows arm vs baseline. | `core/experiment_db.py` |
| [`experiment_results`](#experiment_results) | local only | ~4k | 2026-07-16 → 2026-07-17 | Per (experiment, stage, arm, model, window, seed) metrics. | `core/experiment_db.py` |
| [`experiments`](#experiments) | local only | 10 | 2026-07-16 → 2026-07-17 | Experiment-loop header rows (`core/experiment_db.py`). | `core/experiment_db.py` |
| **Ingest bookkeeping** | | | | | |
| [`importedgamesmemory`](#importedgamesmemory) | local only | ~42k | 1995-96 → 2026-27 | Per-game import status per box-score table (1 ok, 2 API had no data, 0 failed) + number_reattempts; drives the importer's retries. | `data_engineering/add_v3_columns.py`, `data_engineering/backfill_from_raw.py`, `data_engineering/main_refactored.py`, `data_engineering/verify_imported_games.py` |

## Columns and indexes

<a id="boxscoreadvancedv3_player"></a>
<details><summary><code>boxscoreadvancedv3_player</code> - 37 columns, ~986k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `gameId` | bigint | yes | MUL |
| `teamId` | bigint | yes |  |
| `teamCity` | text | yes |  |
| `teamName` | text | yes |  |
| `teamTricode` | text | yes |  |
| `teamSlug` | text | yes |  |
| `personId` | bigint | yes |  |
| `firstName` | text | yes |  |
| `familyName` | text | yes |  |
| `nameI` | text | yes |  |
| `playerSlug` | text | yes |  |
| `position` | text | yes |  |
| `comment` | text | yes |  |
| `jerseyNum` | text | yes |  |
| `minutes` | text | yes |  |
| `estimatedOffensiveRating` | double | yes |  |
| `offensiveRating` | double | yes |  |
| `estimatedDefensiveRating` | double | yes |  |
| `defensiveRating` | double | yes |  |
| `estimatedNetRating` | double | yes |  |
| `netRating` | double | yes |  |
| `assistPercentage` | double | yes |  |
| `assistToTurnover` | double | yes |  |
| `assistRatio` | double | yes |  |
| `offensiveReboundPercentage` | double | yes |  |
| `defensiveReboundPercentage` | double | yes |  |
| `reboundPercentage` | double | yes |  |
| `turnoverRatio` | double | yes |  |
| `effectiveFieldGoalPercentage` | double | yes |  |
| `trueShootingPercentage` | double | yes |  |
| `usagePercentage` | double | yes |  |
| `estimatedUsagePercentage` | double | yes |  |
| `estimatedPace` | double | yes |  |
| `pace` | double | yes |  |
| `pacePer40` | double | yes |  |
| `possessions` | double | yes |  |
| `PIE` | double | yes |  |

Indexes: `idx_adv_game_person` (gameId,personId)

</details>

<a id="boxscoreadvancedv3_team"></a>
<details><summary><code>boxscoreadvancedv3_team</code> - 30 columns, ~82k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `gameId` | bigint | yes |  |
| `teamId` | bigint | yes |  |
| `teamCity` | text | yes |  |
| `teamName` | text | yes |  |
| `teamTricode` | text | yes |  |
| `teamSlug` | text | yes |  |
| `minutes` | text | yes |  |
| `estimatedOffensiveRating` | double | yes |  |
| `offensiveRating` | double | yes |  |
| `estimatedDefensiveRating` | double | yes |  |
| `defensiveRating` | double | yes |  |
| `estimatedNetRating` | double | yes |  |
| `netRating` | double | yes |  |
| `assistPercentage` | double | yes |  |
| `assistToTurnover` | double | yes |  |
| `assistRatio` | double | yes |  |
| `offensiveReboundPercentage` | double | yes |  |
| `defensiveReboundPercentage` | double | yes |  |
| `reboundPercentage` | double | yes |  |
| `estimatedTeamTurnoverPercentage` | double | yes |  |
| `turnoverRatio` | double | yes |  |
| `effectiveFieldGoalPercentage` | double | yes |  |
| `trueShootingPercentage` | double | yes |  |
| `usagePercentage` | double | yes |  |
| `estimatedUsagePercentage` | double | yes |  |
| `estimatedPace` | double | yes |  |
| `pace` | double | yes |  |
| `pacePer40` | double | yes |  |
| `possessions` | double | yes |  |
| `PIE` | double | yes |  |

</details>

<a id="boxscoredefensivev2_player"></a>
<details><summary><code>boxscoredefensivev2_player</code> - 29 columns, ~248k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `gameId` | bigint | yes |  |
| `teamId` | bigint | yes |  |
| `teamCity` | text | yes |  |
| `teamName` | text | yes |  |
| `teamTricode` | text | yes |  |
| `teamSlug` | text | yes |  |
| `personId` | bigint | yes |  |
| `firstName` | text | yes |  |
| `familyName` | text | yes |  |
| `nameI` | text | yes |  |
| `playerSlug` | text | yes |  |
| `position` | text | yes |  |
| `comment` | text | yes |  |
| `jerseyNum` | text | yes |  |
| `matchupMinutes` | text | yes |  |
| `partialPossessions` | double | yes |  |
| `switchesOn` | bigint | yes |  |
| `playerPoints` | bigint | yes |  |
| `defensiveRebounds` | bigint | yes |  |
| `matchupAssists` | bigint | yes |  |
| `matchupTurnovers` | bigint | yes |  |
| `steals` | bigint | yes |  |
| `blocks` | bigint | yes |  |
| `matchupFieldGoalsMade` | bigint | yes |  |
| `matchupFieldGoalsAttempted` | bigint | yes |  |
| `matchupFieldGoalPercentage` | double | yes |  |
| `matchupThreePointersMade` | bigint | yes |  |
| `matchupThreePointersAttempted` | bigint | yes |  |
| `matchupThreePointerPercentage` | double | yes |  |

</details>

<a id="boxscoredefensivev2_team"></a>
<details><summary><code>boxscoredefensivev2_team</code> - 7 columns, ~82k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `gameId` | bigint | yes |  |
| `teamId` | bigint | yes |  |
| `teamCity` | text | yes |  |
| `teamName` | text | yes |  |
| `teamTricode` | text | yes |  |
| `teamSlug` | text | yes |  |
| `minutes` | text | yes |  |

</details>

<a id="boxscorefourfactorsv3_player"></a>
<details><summary><code>boxscorefourfactorsv3_player</code> - 23 columns, ~986k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `gameId` | bigint | yes |  |
| `teamId` | bigint | yes |  |
| `teamCity` | text | yes |  |
| `teamName` | text | yes |  |
| `teamTricode` | text | yes |  |
| `teamSlug` | text | yes |  |
| `personId` | bigint | yes |  |
| `firstName` | text | yes |  |
| `familyName` | text | yes |  |
| `nameI` | text | yes |  |
| `playerSlug` | text | yes |  |
| `position` | text | yes |  |
| `comment` | text | yes |  |
| `jerseyNum` | text | yes |  |
| `minutes` | text | yes |  |
| `effectiveFieldGoalPercentage` | double | yes |  |
| `freeThrowAttemptRate` | double | yes |  |
| `teamTurnoverPercentage` | double | yes |  |
| `offensiveReboundPercentage` | double | yes |  |
| `oppEffectiveFieldGoalPercentage` | double | yes |  |
| `oppFreeThrowAttemptRate` | double | yes |  |
| `oppTeamTurnoverPercentage` | double | yes |  |
| `oppOffensiveReboundPercentage` | double | yes |  |

</details>

<a id="boxscorefourfactorsv3_team"></a>
<details><summary><code>boxscorefourfactorsv3_team</code> - 15 columns, ~82k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `gameId` | bigint | yes |  |
| `teamId` | bigint | yes |  |
| `teamCity` | text | yes |  |
| `teamName` | text | yes |  |
| `teamTricode` | text | yes |  |
| `teamSlug` | text | yes |  |
| `minutes` | text | yes |  |
| `effectiveFieldGoalPercentage` | double | yes |  |
| `freeThrowAttemptRate` | double | yes |  |
| `teamTurnoverPercentage` | double | yes |  |
| `offensiveReboundPercentage` | double | yes |  |
| `oppEffectiveFieldGoalPercentage` | double | yes |  |
| `oppFreeThrowAttemptRate` | double | yes |  |
| `oppTeamTurnoverPercentage` | double | yes |  |
| `oppOffensiveReboundPercentage` | double | yes |  |

</details>

<a id="boxscorehustlev2_player"></a>
<details><summary><code>boxscorehustlev2_player</code> - 31 columns, ~303k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `gameId` | bigint | yes |  |
| `teamId` | bigint | yes |  |
| `teamCity` | text | yes |  |
| `teamName` | text | yes |  |
| `teamTricode` | text | yes |  |
| `teamSlug` | text | yes |  |
| `personId` | bigint | yes |  |
| `firstName` | text | yes |  |
| `familyName` | text | yes |  |
| `nameI` | text | yes |  |
| `playerSlug` | text | yes |  |
| `position` | text | yes |  |
| `comment` | text | yes |  |
| `jerseyNum` | text | yes |  |
| `minutes` | text | yes |  |
| `points` | bigint | yes |  |
| `contestedShots` | bigint | yes |  |
| `contestedShots2pt` | bigint | yes |  |
| `contestedShots3pt` | bigint | yes |  |
| `deflections` | bigint | yes |  |
| `chargesDrawn` | bigint | yes |  |
| `screenAssists` | bigint | yes |  |
| `screenAssistPoints` | bigint | yes |  |
| `looseBallsRecoveredOffensive` | bigint | yes |  |
| `looseBallsRecoveredDefensive` | bigint | yes |  |
| `looseBallsRecoveredTotal` | bigint | yes |  |
| `offensiveBoxOuts` | bigint | yes |  |
| `defensiveBoxOuts` | bigint | yes |  |
| `boxOutPlayerTeamRebounds` | bigint | yes |  |
| `boxOutPlayerRebounds` | bigint | yes |  |
| `boxOuts` | bigint | yes |  |

</details>

<a id="boxscorehustlev2_team"></a>
<details><summary><code>boxscorehustlev2_team</code> - 23 columns, ~82k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `gameId` | bigint | yes |  |
| `teamId` | bigint | yes |  |
| `teamCity` | text | yes |  |
| `teamName` | text | yes |  |
| `teamTricode` | text | yes |  |
| `teamSlug` | text | yes |  |
| `minutes` | text | yes |  |
| `points` | bigint | yes |  |
| `contestedShots` | bigint | yes |  |
| `contestedShots2pt` | bigint | yes |  |
| `contestedShots3pt` | bigint | yes |  |
| `deflections` | bigint | yes |  |
| `chargesDrawn` | bigint | yes |  |
| `screenAssists` | bigint | yes |  |
| `screenAssistPoints` | bigint | yes |  |
| `looseBallsRecoveredOffensive` | bigint | yes |  |
| `looseBallsRecoveredDefensive` | bigint | yes |  |
| `looseBallsRecoveredTotal` | bigint | yes |  |
| `offensiveBoxOuts` | bigint | yes |  |
| `defensiveBoxOuts` | bigint | yes |  |
| `boxOutPlayerTeamRebounds` | bigint | yes |  |
| `boxOutPlayerRebounds` | bigint | yes |  |
| `boxOuts` | bigint | yes |  |

</details>

<a id="boxscoremiscv3_player"></a>
<details><summary><code>boxscoremiscv3_player</code> - 27 columns, ~986k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `gameId` | bigint | yes |  |
| `teamId` | bigint | yes |  |
| `teamCity` | text | yes |  |
| `teamName` | text | yes |  |
| `teamTricode` | text | yes |  |
| `teamSlug` | text | yes |  |
| `personId` | bigint | yes |  |
| `firstName` | text | yes |  |
| `familyName` | text | yes |  |
| `nameI` | text | yes |  |
| `playerSlug` | text | yes |  |
| `position` | text | yes |  |
| `comment` | text | yes |  |
| `jerseyNum` | text | yes |  |
| `minutes` | text | yes |  |
| `pointsOffTurnovers` | bigint | yes |  |
| `pointsSecondChance` | bigint | yes |  |
| `pointsFastBreak` | bigint | yes |  |
| `pointsPaint` | bigint | yes |  |
| `oppPointsOffTurnovers` | bigint | yes |  |
| `oppPointsSecondChance` | bigint | yes |  |
| `oppPointsFastBreak` | bigint | yes |  |
| `oppPointsPaint` | bigint | yes |  |
| `blocks` | bigint | yes |  |
| `blocksAgainst` | bigint | yes |  |
| `foulsPersonal` | bigint | yes |  |
| `foulsDrawn` | bigint | yes |  |

</details>

<a id="boxscoremiscv3_team"></a>
<details><summary><code>boxscoremiscv3_team</code> - 19 columns, ~82k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `gameId` | bigint | yes |  |
| `teamId` | bigint | yes |  |
| `teamCity` | text | yes |  |
| `teamName` | text | yes |  |
| `teamTricode` | text | yes |  |
| `teamSlug` | text | yes |  |
| `minutes` | text | yes |  |
| `pointsOffTurnovers` | bigint | yes |  |
| `pointsSecondChance` | bigint | yes |  |
| `pointsFastBreak` | bigint | yes |  |
| `pointsPaint` | bigint | yes |  |
| `oppPointsOffTurnovers` | bigint | yes |  |
| `oppPointsSecondChance` | bigint | yes |  |
| `oppPointsFastBreak` | bigint | yes |  |
| `oppPointsPaint` | bigint | yes |  |
| `blocks` | bigint | yes |  |
| `blocksAgainst` | bigint | yes |  |
| `foulsPersonal` | bigint | yes |  |
| `foulsDrawn` | bigint | yes |  |

</details>

<a id="boxscoreplayertrackv3_player"></a>
<details><summary><code>boxscoreplayertrackv3_player</code> - 35 columns, ~1.1M rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `gameId` | bigint | yes | MUL |
| `teamId` | bigint | yes |  |
| `teamCity` | text | yes |  |
| `teamName` | text | yes |  |
| `teamTricode` | text | yes |  |
| `teamSlug` | text | yes |  |
| `personId` | bigint | yes |  |
| `firstName` | text | yes |  |
| `familyName` | text | yes |  |
| `nameI` | text | yes |  |
| `playerSlug` | text | yes |  |
| `position` | text | yes |  |
| `comment` | text | yes |  |
| `jerseyNum` | text | yes |  |
| `minutes` | text | yes |  |
| `speed` | double | yes |  |
| `distance` | double | yes |  |
| `reboundChancesOffensive` | bigint | yes |  |
| `reboundChancesDefensive` | bigint | yes |  |
| `reboundChancesTotal` | bigint | yes |  |
| `touches` | bigint | yes |  |
| `secondaryAssists` | bigint | yes |  |
| `freeThrowAssists` | bigint | yes |  |
| `passes` | bigint | yes |  |
| `assists` | bigint | yes |  |
| `contestedFieldGoalsMade` | bigint | yes |  |
| `contestedFieldGoalsAttempted` | bigint | yes |  |
| `contestedFieldGoalPercentage` | double | yes |  |
| `uncontestedFieldGoalsMade` | bigint | yes |  |
| `uncontestedFieldGoalsAttempted` | bigint | yes |  |
| `uncontestedFieldGoalsPercentage` | double | yes |  |
| `fieldGoalPercentage` | double | yes |  |
| `defendedAtRimFieldGoalsMade` | bigint | yes |  |
| `defendedAtRimFieldGoalsAttempted` | bigint | yes |  |
| `defendedAtRimFieldGoalPercentage` | double | yes |  |

Indexes: `idx_track_game_person` (gameId,personId)

</details>

<a id="boxscoreplayertrackv3_team"></a>
<details><summary><code>boxscoreplayertrackv3_team</code> - 27 columns, ~82k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `gameId` | bigint | yes |  |
| `teamId` | bigint | yes |  |
| `teamCity` | text | yes |  |
| `teamName` | text | yes |  |
| `teamTricode` | text | yes |  |
| `teamSlug` | text | yes |  |
| `minutes` | text | yes |  |
| `speed` | float | yes |  |
| `distance` | double | yes |  |
| `reboundChancesOffensive` | bigint | yes |  |
| `reboundChancesDefensive` | bigint | yes |  |
| `reboundChancesTotal` | bigint | yes |  |
| `touches` | bigint | yes |  |
| `secondaryAssists` | bigint | yes |  |
| `freeThrowAssists` | bigint | yes |  |
| `passes` | bigint | yes |  |
| `assists` | bigint | yes |  |
| `contestedFieldGoalsMade` | bigint | yes |  |
| `contestedFieldGoalsAttempted` | bigint | yes |  |
| `contestedFieldGoalPercentage` | double | yes |  |
| `uncontestedFieldGoalsMade` | bigint | yes |  |
| `uncontestedFieldGoalsAttempted` | bigint | yes |  |
| `uncontestedFieldGoalsPercentage` | double | yes |  |
| `fieldGoalPercentage` | double | yes |  |
| `defendedAtRimFieldGoalsMade` | bigint | yes |  |
| `defendedAtRimFieldGoalsAttempted` | bigint | yes |  |
| `defendedAtRimFieldGoalPercentage` | double | yes |  |

</details>

<a id="boxscorescoringv3_player"></a>
<details><summary><code>boxscorescoringv3_player</code> - 30 columns, ~986k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `gameId` | bigint | yes |  |
| `teamId` | bigint | yes |  |
| `teamCity` | text | yes |  |
| `teamName` | text | yes |  |
| `teamTricode` | text | yes |  |
| `teamSlug` | text | yes |  |
| `personId` | bigint | yes |  |
| `firstName` | text | yes |  |
| `familyName` | text | yes |  |
| `nameI` | text | yes |  |
| `playerSlug` | text | yes |  |
| `position` | text | yes |  |
| `comment` | text | yes |  |
| `jerseyNum` | text | yes |  |
| `minutes` | text | yes |  |
| `percentageFieldGoalsAttempted2pt` | double | yes |  |
| `percentageFieldGoalsAttempted3pt` | double | yes |  |
| `percentagePoints2pt` | double | yes |  |
| `percentagePointsMidrange2pt` | double | yes |  |
| `percentagePoints3pt` | double | yes |  |
| `percentagePointsFastBreak` | double | yes |  |
| `percentagePointsFreeThrow` | double | yes |  |
| `percentagePointsOffTurnovers` | double | yes |  |
| `percentagePointsPaint` | double | yes |  |
| `percentageAssisted2pt` | double | yes |  |
| `percentageUnassisted2pt` | double | yes |  |
| `percentageAssisted3pt` | double | yes |  |
| `percentageUnassisted3pt` | double | yes |  |
| `percentageAssistedFGM` | double | yes |  |
| `percentageUnassistedFGM` | double | yes |  |

</details>

<a id="boxscorescoringv3_team"></a>
<details><summary><code>boxscorescoringv3_team</code> - 22 columns, ~82k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `gameId` | bigint | yes |  |
| `teamId` | bigint | yes |  |
| `teamCity` | text | yes |  |
| `teamName` | text | yes |  |
| `teamTricode` | text | yes |  |
| `teamSlug` | text | yes |  |
| `minutes` | text | yes |  |
| `percentageFieldGoalsAttempted2pt` | double | yes |  |
| `percentageFieldGoalsAttempted3pt` | double | yes |  |
| `percentagePoints2pt` | double | yes |  |
| `percentagePointsMidrange2pt` | double | yes |  |
| `percentagePoints3pt` | double | yes |  |
| `percentagePointsFastBreak` | double | yes |  |
| `percentagePointsFreeThrow` | double | yes |  |
| `percentagePointsOffTurnovers` | double | yes |  |
| `percentagePointsPaint` | double | yes |  |
| `percentageAssisted2pt` | double | yes |  |
| `percentageUnassisted2pt` | double | yes |  |
| `percentageAssisted3pt` | double | yes |  |
| `percentageUnassisted3pt` | double | yes |  |
| `percentageAssistedFGM` | double | yes |  |
| `percentageUnassistedFGM` | double | yes |  |

</details>

<a id="boxscoresummaryv2_game_info"></a>
<details><summary><code>boxscoresummaryv2_game_info</code> - 7 columns, ~39k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `GAME_ID` | bigint | yes |  |
| `HOME_TEAM_ID` | bigint | yes |  |
| `VISITOR_TEAM_ID` | bigint | yes |  |
| `GAME_DATE_EST` | text | yes |  |
| `HOME_TEAM_WINS` | bigint | yes |  |
| `HOME_TEAM_LOSSES` | bigint | yes |  |
| `SERIES_LEADER` | text | yes |  |

</details>

<a id="boxscoresummaryv2_inactive_players"></a>
<details><summary><code>boxscoresummaryv2_inactive_players</code> - 9 columns, ~148k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `PLAYER_ID` | bigint | yes |  |
| `FIRST_NAME` | text | yes |  |
| `LAST_NAME` | text | yes |  |
| `JERSEY_NUM` | text | yes |  |
| `TEAM_ID` | bigint | yes |  |
| `TEAM_CITY` | text | yes |  |
| `TEAM_NAME` | text | yes |  |
| `TEAM_ABBREVIATION` | text | yes |  |
| `GAME_ID` | bigint | yes |  |

</details>

<a id="boxscoresummaryv2_other_stats"></a>
<details><summary><code>boxscoresummaryv2_other_stats</code> - 13 columns, ~37k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `GAME_ID` | bigint | yes |  |
| `LAST_GAME_ID` | text | yes |  |
| `LAST_GAME_DATE_EST` | text | yes |  |
| `LAST_GAME_HOME_TEAM_ID` | bigint | yes |  |
| `LAST_GAME_HOME_TEAM_CITY` | text | yes |  |
| `LAST_GAME_HOME_TEAM_NAME` | text | yes |  |
| `LAST_GAME_HOME_TEAM_ABBREVIATION` | text | yes |  |
| `LAST_GAME_HOME_TEAM_POINTS` | bigint | yes |  |
| `LAST_GAME_VISITOR_TEAM_ID` | bigint | yes |  |
| `LAST_GAME_VISITOR_TEAM_CITY` | text | yes |  |
| `LAST_GAME_VISITOR_TEAM_NAME` | text | yes |  |
| `LAST_GAME_VISITOR_TEAM_CITY1` | text | yes |  |
| `LAST_GAME_VISITOR_TEAM_POINTS` | bigint | yes |  |

</details>

<a id="boxscoresummaryv2_referee"></a>
<details><summary><code>boxscoresummaryv2_referee</code> - 5 columns, ~91k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `OFFICIAL_ID` | bigint | yes |  |
| `FIRST_NAME` | text | yes |  |
| `LAST_NAME` | text | yes |  |
| `JERSEY_NUM` | text | yes |  |
| `GAME_ID` | text | yes |  |

</details>

<a id="boxscoresummaryv2_summary"></a>
<details><summary><code>boxscoresummaryv2_summary</code> - 15 columns, ~76k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `LEAGUE_ID` | text | yes |  |
| `TEAM_ID` | bigint | yes |  |
| `TEAM_ABBREVIATION` | text | yes |  |
| `TEAM_CITY` | text | yes |  |
| `PTS_PAINT` | bigint | yes |  |
| `PTS_2ND_CHANCE` | bigint | yes |  |
| `PTS_FB` | bigint | yes |  |
| `LARGEST_LEAD` | bigint | yes |  |
| `LEAD_CHANGES` | bigint | yes |  |
| `TIMES_TIED` | bigint | yes |  |
| `TEAM_TURNOVERS` | bigint | yes |  |
| `TOTAL_TURNOVERS` | bigint | yes |  |
| `TEAM_REBOUNDS` | bigint | yes |  |
| `PTS_OFF_TO` | bigint | yes |  |
| `GAME_ID` | bigint | yes |  |

</details>

<a id="boxscoresummaryv3_arena_info"></a>
<details><summary><code>boxscoresummaryv3_arena_info</code> - 7 columns, ~2k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `gameId` | text | yes |  |
| `arenaId` | bigint | yes |  |
| `arenaName` | text | yes |  |
| `arenaCity` | text | yes |  |
| `arenaState` | text | yes |  |
| `arenaCountry` | text | yes |  |
| `arenaTimezone` | text | yes |  |

</details>

<a id="boxscoresummaryv3_game_info"></a>
<details><summary><code>boxscoresummaryv3_game_info</code> - 4 columns, ~2k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `gameId` | text | yes |  |
| `gameDate` | text | yes |  |
| `attendance` | bigint | yes |  |
| `gameDuration` | text | yes |  |

</details>

<a id="boxscoresummaryv3_game_summary"></a>
<details><summary><code>boxscoresummaryv3_game_summary</code> - 13 columns, ~2k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `gameId` | text | yes |  |
| `gameCode` | text | yes |  |
| `gameStatus` | bigint | yes |  |
| `gameStatusText` | text | yes |  |
| `period` | bigint | yes |  |
| `gameClock` | text | yes |  |
| `gameTimeUTC` | text | yes |  |
| `gameEt` | text | yes |  |
| `awayTeamId` | bigint | yes |  |
| `homeTeamId` | bigint | yes |  |
| `duration` | text | yes |  |
| `attendance` | bigint | yes |  |
| `sellout` | bigint | yes |  |

</details>

<a id="boxscoresummaryv3_inactive_players"></a>
<details><summary><code>boxscoresummaryv3_inactive_players</code> - 6 columns, ~13k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `gameId` | text | yes |  |
| `teamId` | bigint | yes |  |
| `personId` | bigint | yes |  |
| `firstName` | text | yes |  |
| `familyName` | text | yes |  |
| `jerseyNum` | text | yes |  |

</details>

<a id="boxscoresummaryv3_last_five_meetings"></a>
<details><summary><code>boxscoresummaryv3_last_five_meetings</code> - 20 columns, ~82k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `recencyOrder` | bigint | yes |  |
| `gameId` | text | yes |  |
| `gameTimeUTC` | text | yes |  |
| `gameEt` | text | yes |  |
| `gameStatus` | bigint | yes |  |
| `gameStatusText` | text | yes |  |
| `awayTeamId` | bigint | yes |  |
| `awayTeamCity` | text | yes |  |
| `awayTeamName` | text | yes |  |
| `awayTeamTricode` | text | yes |  |
| `awayTeamScore` | bigint | yes |  |
| `awayTeamWins` | bigint | yes |  |
| `awayTeamLosses` | bigint | yes |  |
| `homeTeamId` | bigint | yes |  |
| `homeTeamCity` | text | yes |  |
| `homeTeamName` | text | yes |  |
| `homeTeamTricode` | text | yes |  |
| `homeTeamScore` | bigint | yes |  |
| `homeTeamWins` | bigint | yes |  |
| `homeTeamLosses` | bigint | yes |  |

</details>

<a id="boxscoresummaryv3_line_score"></a>
<details><summary><code>boxscoresummaryv3_line_score</code> - 13 columns, ~3k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `gameId` | text | yes |  |
| `teamId` | bigint | yes |  |
| `teamCity` | text | yes |  |
| `teamName` | text | yes |  |
| `teamTricode` | text | yes |  |
| `teamSlug` | text | yes |  |
| `teamWins` | bigint | yes |  |
| `teamLosses` | bigint | yes |  |
| `period1Score` | bigint | yes |  |
| `period2Score` | bigint | yes |  |
| `period3Score` | bigint | yes |  |
| `period4Score` | bigint | yes |  |
| `score` | bigint | yes |  |

</details>

<a id="boxscoresummaryv3_officials"></a>
<details><summary><code>boxscoresummaryv3_officials</code> - 7 columns, ~5k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `gameId` | text | yes |  |
| `personId` | bigint | yes |  |
| `name` | text | yes |  |
| `nameI` | text | yes |  |
| `firstName` | text | yes |  |
| `familyName` | text | yes |  |
| `jerseyNum` | text | yes |  |

</details>

<a id="boxscoresummaryv3_other_stats"></a>
<details><summary><code>boxscoresummaryv3_other_stats</code> - 26 columns, ~3k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `gameId` | text | yes |  |
| `teamId` | bigint | yes |  |
| `teamCity` | text | yes |  |
| `teamName` | text | yes |  |
| `teamTricode` | text | yes |  |
| `points` | double | yes |  |
| `reboundsTotal` | double | yes |  |
| `assists` | double | yes |  |
| `steals` | double | yes |  |
| `blocks` | double | yes |  |
| `turnovers` | double | yes |  |
| `fieldGoalsPercentage` | double | yes |  |
| `threePointersPercentage` | double | yes |  |
| `freeThrowsPercentage` | double | yes |  |
| `pointsInThePaint` | double | yes |  |
| `pointsSecondChance` | double | yes |  |
| `pointsFastBreak` | double | yes |  |
| `biggestLead` | double | yes |  |
| `leadChanges` | double | yes |  |
| `timesTied` | double | yes |  |
| `biggestScoringRun` | double | yes |  |
| `turnoversTeam` | double | yes |  |
| `turnoversTotal` | double | yes |  |
| `reboundsTeam` | double | yes |  |
| `pointsFromTurnovers` | double | yes |  |
| `benchPoints` | double | yes |  |

</details>

<a id="boxscoretraditionalv3_bench"></a>
<details><summary><code>boxscoretraditionalv3_bench</code> - 26 columns, ~163k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `gameId` | bigint | yes |  |
| `teamId` | bigint | yes |  |
| `teamCity` | text | yes |  |
| `teamName` | text | yes |  |
| `teamTricode` | text | yes |  |
| `teamSlug` | text | yes |  |
| `minutes` | text | yes |  |
| `fieldGoalsMade` | bigint | yes |  |
| `fieldGoalsAttempted` | bigint | yes |  |
| `fieldGoalsPercentage` | double | yes |  |
| `threePointersMade` | bigint | yes |  |
| `threePointersAttempted` | bigint | yes |  |
| `threePointersPercentage` | double | yes |  |
| `freeThrowsMade` | bigint | yes |  |
| `freeThrowsAttempted` | bigint | yes |  |
| `freeThrowsPercentage` | double | yes |  |
| `reboundsOffensive` | bigint | yes |  |
| `reboundsDefensive` | bigint | yes |  |
| `reboundsTotal` | bigint | yes |  |
| `assists` | bigint | yes |  |
| `steals` | bigint | yes |  |
| `blocks` | bigint | yes |  |
| `turnovers` | bigint | yes |  |
| `foulsPersonal` | bigint | yes |  |
| `points` | bigint | yes |  |
| `startersBench` | text | yes |  |

</details>

<a id="boxscoretraditionalv3_player"></a>
<details><summary><code>boxscoretraditionalv3_player</code> - 34 columns, ~1.0M rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `gameId` | bigint | yes | MUL |
| `teamId` | bigint | yes |  |
| `teamCity` | text | yes |  |
| `teamName` | text | yes |  |
| `teamTricode` | text | yes |  |
| `teamSlug` | text | yes |  |
| `personId` | bigint | yes |  |
| `firstName` | text | yes |  |
| `familyName` | text | yes |  |
| `nameI` | text | yes |  |
| `playerSlug` | text | yes |  |
| `position` | text | yes |  |
| `comment` | text | yes |  |
| `jerseyNum` | text | yes |  |
| `minutes` | text | yes |  |
| `fieldGoalsMade` | bigint | yes |  |
| `fieldGoalsAttempted` | bigint | yes |  |
| `fieldGoalsPercentage` | double | yes |  |
| `threePointersMade` | bigint | yes |  |
| `threePointersAttempted` | bigint | yes |  |
| `threePointersPercentage` | double | yes |  |
| `freeThrowsMade` | bigint | yes |  |
| `freeThrowsAttempted` | bigint | yes |  |
| `freeThrowsPercentage` | double | yes |  |
| `reboundsOffensive` | bigint | yes |  |
| `reboundsDefensive` | bigint | yes |  |
| `reboundsTotal` | bigint | yes |  |
| `assists` | bigint | yes |  |
| `steals` | bigint | yes |  |
| `blocks` | bigint | yes |  |
| `turnovers` | bigint | yes |  |
| `foulsPersonal` | bigint | yes |  |
| `points` | bigint | yes |  |
| `plusMinusPoints` | double | yes |  |

Indexes: `idx_trad_game_team_person` (gameId,teamId,personId)

</details>

<a id="boxscoretraditionalv3_team"></a>
<details><summary><code>boxscoretraditionalv3_team</code> - 26 columns, ~82k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `gameId` | bigint | yes |  |
| `teamId` | bigint | yes |  |
| `teamCity` | text | yes |  |
| `teamName` | text | yes |  |
| `teamTricode` | text | yes |  |
| `teamSlug` | text | yes |  |
| `minutes` | text | yes |  |
| `fieldGoalsMade` | bigint | yes |  |
| `fieldGoalsAttempted` | bigint | yes |  |
| `fieldGoalsPercentage` | double | yes |  |
| `threePointersMade` | bigint | yes |  |
| `threePointersAttempted` | bigint | yes |  |
| `threePointersPercentage` | double | yes |  |
| `freeThrowsMade` | bigint | yes |  |
| `freeThrowsAttempted` | bigint | yes |  |
| `freeThrowsPercentage` | double | yes |  |
| `reboundsOffensive` | bigint | yes |  |
| `reboundsDefensive` | bigint | yes |  |
| `reboundsTotal` | bigint | yes |  |
| `assists` | bigint | yes |  |
| `steals` | bigint | yes |  |
| `blocks` | bigint | yes |  |
| `turnovers` | bigint | yes |  |
| `foulsPersonal` | bigint | yes |  |
| `points` | bigint | yes |  |
| `plusMinusPoints` | double | yes |  |

</details>

<a id="boxscoreusagev3_player"></a>
<details><summary><code>boxscoreusagev3_player</code> - 33 columns, ~985k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `gameId` | bigint | yes |  |
| `teamId` | bigint | yes |  |
| `teamCity` | text | yes |  |
| `teamName` | text | yes |  |
| `teamTricode` | text | yes |  |
| `teamSlug` | text | yes |  |
| `personId` | bigint | yes |  |
| `firstName` | text | yes |  |
| `familyName` | text | yes |  |
| `nameI` | text | yes |  |
| `playerSlug` | text | yes |  |
| `position` | text | yes |  |
| `comment` | text | yes |  |
| `jerseyNum` | text | yes |  |
| `minutes` | text | yes |  |
| `usagePercentage` | double | yes |  |
| `percentageFieldGoalsMade` | double | yes |  |
| `percentageFieldGoalsAttempted` | double | yes |  |
| `percentageThreePointersMade` | double | yes |  |
| `percentageThreePointersAttempted` | double | yes |  |
| `percentageFreeThrowsMade` | double | yes |  |
| `percentageFreeThrowsAttempted` | double | yes |  |
| `percentageReboundsOffensive` | double | yes |  |
| `percentageReboundsDefensive` | double | yes |  |
| `percentageReboundsTotal` | double | yes |  |
| `percentageAssists` | double | yes |  |
| `percentageTurnovers` | double | yes |  |
| `percentageSteals` | double | yes |  |
| `percentageBlocks` | double | yes |  |
| `percentageBlocksAllowed` | double | yes |  |
| `percentagePersonalFouls` | double | yes |  |
| `percentagePersonalFoulsDrawn` | double | yes |  |
| `percentagePoints` | double | yes |  |

</details>

<a id="boxscoreusagev3_team"></a>
<details><summary><code>boxscoreusagev3_team</code> - 25 columns, ~82k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `gameId` | bigint | yes |  |
| `teamId` | bigint | yes |  |
| `teamCity` | text | yes |  |
| `teamName` | text | yes |  |
| `teamTricode` | text | yes |  |
| `teamSlug` | text | yes |  |
| `minutes` | text | yes |  |
| `usagePercentage` | double | yes |  |
| `percentageFieldGoalsMade` | double | yes |  |
| `percentageFieldGoalsAttempted` | double | yes |  |
| `percentageThreePointersMade` | double | yes |  |
| `percentageThreePointersAttempted` | double | yes |  |
| `percentageFreeThrowsMade` | double | yes |  |
| `percentageFreeThrowsAttempted` | double | yes |  |
| `percentageReboundsOffensive` | double | yes |  |
| `percentageReboundsDefensive` | double | yes |  |
| `percentageReboundsTotal` | double | yes |  |
| `percentageAssists` | double | yes |  |
| `percentageTurnovers` | double | yes |  |
| `percentageSteals` | double | yes |  |
| `percentageBlocks` | double | yes |  |
| `percentageBlocksAllowed` | double | yes |  |
| `percentagePersonalFouls` | double | yes |  |
| `percentagePersonalFoulsDrawn` | double | yes |  |
| `percentagePoints` | double | yes |  |

</details>

<a id="experiment_comparisons"></a>
<details><summary><code>experiment_comparisons</code> - 29 columns, 701 rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `comparison_id` | bigint | no | PRI |
| `experiment_id` | varchar(32) | no | MUL |
| `stage` | varchar(20) | no |  |
| `arm` | varchar(64) | no |  |
| `baseline_arm` | varchar(64) | no |  |
| `model_type` | varchar(16) | no |  |
| `window_name` | varchar(32) | no |  |
| `mcnemar_stat` | double | yes |  |
| `mcnemar_p` | double | yes |  |
| `arm_wins` | int | yes |  |
| `base_wins` | int | yes |  |
| `paired_t_stat` | double | yes |  |
| `paired_t_p` | double | yes |  |
| `mae_diff` | double | yes |  |
| `mae_diff_sd` | double | yes |  |
| `mae_diff_ci_lo` | double | yes |  |
| `mae_diff_ci_hi` | double | yes |  |
| `mae_diff_p` | double | yes |  |
| `auc_diff` | double | yes |  |
| `auc_diff_ci_lo` | double | yes |  |
| `auc_diff_ci_hi` | double | yes |  |
| `auc_diff_p` | double | yes |  |
| `acc_diff` | double | yes |  |
| `acc_diff_ci_lo` | double | yes |  |
| `acc_diff_ci_hi` | double | yes |  |
| `acc_diff_p` | double | yes |  |
| `gate` | varchar(20) | yes |  |
| `extra_json` | json | yes |  |
| `created_at` | timestamp | yes |  |

Indexes: `idx_exp_cmp` (experiment_id); `PRIMARY` (comparison_id) unique; `uq_cmp` (experiment_id,stage,arm,baseline_arm,model_type,window_name) unique

</details>

<a id="experiment_results"></a>
<details><summary><code>experiment_results</code> - 26 columns, ~4k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `result_id` | bigint | no | PRI |
| `experiment_id` | varchar(32) | no | MUL |
| `stage` | varchar(20) | no |  |
| `arm` | varchar(64) | no |  |
| `model_type` | varchar(16) | no |  |
| `window_name` | varchar(32) | no |  |
| `test_start` | date | yes |  |
| `test_end` | date | yes |  |
| `seed` | int | no |  |
| `n_train` | int | yes |  |
| `n_test` | int | yes |  |
| `n_features` | int | yes |  |
| `acc` | double | yes |  |
| `acc_ci_lo` | double | yes |  |
| `acc_ci_hi` | double | yes |  |
| `auc` | double | yes |  |
| `auc_ci_lo` | double | yes |  |
| `auc_ci_hi` | double | yes |  |
| `mae` | double | yes |  |
| `mae_ci_lo` | double | yes |  |
| `mae_ci_hi` | double | yes |  |
| `logloss` | double | yes |  |
| `brier` | double | yes |  |
| `ece` | double | yes |  |
| `extra_json` | json | yes |  |
| `created_at` | timestamp | yes |  |

Indexes: `idx_exp_res` (experiment_id); `PRIMARY` (result_id) unique; `uq_res` (experiment_id,stage,arm,model_type,window_name,seed) unique

</details>

<a id="experiments"></a>
<details><summary><code>experiments</code> - 12 columns, 10 rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `experiment_id` | varchar(32) | no | PRI |
| `title` | varchar(200) | no |  |
| `hypothesis` | text | yes |  |
| `spec_json` | json | yes |  |
| `feature_set_version` | varchar(40) | yes |  |
| `csv_path` | varchar(255) | yes |  |
| `status` | varchar(20) | no |  |
| `verdict` | varchar(20) | yes |  |
| `decision_notes` | text | yes |  |
| `tuning_log_anchor` | varchar(120) | yes |  |
| `started_at` | timestamp | yes |  |
| `finished_at` | timestamp | yes |  |

Indexes: `PRIMARY` (experiment_id) unique

</details>

<a id="feature_set_current"></a>
<details><summary><code>feature_set_current</code> - 3 columns, 1 rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `id` | tinyint | no | PRI |
| `version` | varchar(40) | no |  |
| `updated_at` | timestamp | no |  |

Indexes: `PRIMARY` (id) unique

</details>

<a id="feature_set_versions"></a>
<details><summary><code>feature_set_versions</code> - 5 columns, 3 rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `feature_set_version` | varchar(40) | no | PRI |
| `description` | text | yes |  |
| `n_games` | int | yes |  |
| `n_columns` | int | yes |  |
| `created_at` | timestamp | yes |  |

Indexes: `PRIMARY` (feature_set_version) unique

</details>

<a id="features"></a>
<details><summary><code>features</code> - 771 columns, ~10k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `feature_set_version` | varchar(40) | no | PRI |
| `GAME_ID` | bigint | no | PRI |
| `GAME_DATE` | datetime | yes | MUL |
| `HOME_TEAM_ID` | bigint | yes |  |
| `HOME_TEAM_ABBREVIATION` | text | yes |  |
| `HOME_TEAM_NAME` | text | yes |  |
| `MATCHUP` | text | yes |  |
| `HOME_WL` | text | yes |  |
| `HOME_PTS` | bigint | yes |  |
| `HOME_FGM` | bigint | yes |  |
| `HOME_FGA` | bigint | yes |  |
| `HOME_FG_PCT` | double | yes |  |
| `HOME_FG3M` | bigint | yes |  |
| `HOME_FG3A` | bigint | yes |  |
| `HOME_FG3_PCT` | double | yes |  |
| `HOME_FTM` | bigint | yes |  |
| `HOME_FTA` | bigint | yes |  |
| `HOME_FT_PCT` | double | yes |  |
| `HOME_OREB` | bigint | yes |  |
| `HOME_DREB` | bigint | yes |  |
| `HOME_REB` | bigint | yes |  |
| `HOME_AST` | bigint | yes |  |
| `HOME_STL` | bigint | yes |  |
| `HOME_BLK` | bigint | yes |  |
| `HOME_TOV` | bigint | yes |  |
| `HOME_PF` | bigint | yes |  |
| `HOME_PLUS_MINUS` | double | yes |  |
| `HOME_WIN` | bigint | yes |  |
| `HOME_IS_HOME` | bigint | yes |  |
| `HOME_offensiveRating` | double | yes |  |
| `HOME_defensiveRating` | double | yes |  |
| `HOME_netRating` | double | yes |  |
| `HOME_pace` | double | yes |  |
| `HOME_possessions` | double | yes |  |
| `HOME_EFG_PCT` | double | yes |  |
| `HOME_TS_PCT` | double | yes |  |
| `HOME_assistPercentage` | double | yes |  |
| `HOME_assistToTurnover` | double | yes |  |
| `HOME_ADV_OREB_PCT` | double | yes |  |
| `HOME_ADV_DREB_PCT` | double | yes |  |
| `HOME_turnoverRatio` | double | yes |  |
| `HOME_PIE` | double | yes |  |
| `HOME_FT_RATE` | double | yes |  |
| `HOME_TOV_PCT` | double | yes |  |
| `HOME_OREB_PCT` | double | yes |  |
| `HOME_OPP_EFG_PCT` | double | yes |  |
| `HOME_OPP_FT_RATE` | double | yes |  |
| `HOME_OPP_TOV_PCT` | double | yes |  |
| `HOME_OPP_OREB_PCT` | double | yes |  |
| `HOME_contestedShots` | double | yes |  |
| `HOME_contestedShots2pt` | double | yes |  |
| `HOME_contestedShots3pt` | double | yes |  |
| `HOME_deflections` | double | yes |  |
| `HOME_chargesDrawn` | double | yes |  |
| `HOME_screenAssists` | double | yes |  |
| `HOME_looseBallsRecovered` | double | yes |  |
| `HOME_boxOuts` | double | yes |  |
| `HOME_speed` | double | yes |  |
| `HOME_distance` | double | yes |  |
| `HOME_reboundChancesTotal` | double | yes |  |
| `HOME_touches` | double | yes |  |
| `HOME_passes` | double | yes |  |
| `HOME_secondaryAssists` | double | yes |  |
| `HOME_contestedFieldGoalsMade` | double | yes |  |
| `HOME_contestedFieldGoalsAttempted` | double | yes |  |
| `HOME_uncontestedFieldGoalsMade` | double | yes |  |
| `HOME_uncontestedFieldGoalsAttempted` | double | yes |  |
| `HOME_defendedAtRimFieldGoalsMade` | double | yes |  |
| `HOME_defendedAtRimFieldGoalsAttempted` | double | yes |  |
| `HOME_pointsOffTurnovers` | double | yes |  |
| `HOME_pointsSecondChance` | double | yes |  |
| `HOME_pointsFastBreak` | double | yes |  |
| `HOME_pointsPaint` | double | yes |  |
| `HOME_oppPointsOffTurnovers` | double | yes |  |
| `HOME_oppPointsSecondChance` | double | yes |  |
| `HOME_oppPointsFastBreak` | double | yes |  |
| `HOME_oppPointsPaint` | double | yes |  |
| `HOME_foulsDrawn` | double | yes |  |
| `HOME_pctFGA_2pt` | double | yes |  |
| `HOME_pctFGA_3pt` | double | yes |  |
| ... 691 more | | | |

Indexes: `idx_features_game_date` (GAME_DATE); `PRIMARY` (feature_set_version,GAME_ID) unique

</details>

<a id="game_list"></a>
<details><summary><code>game_list</code> - 28 columns, ~83k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `SEASON_ID` | text | yes |  |
| `TEAM_ID` | bigint | yes | MUL |
| `TEAM_ABBREVIATION` | text | yes |  |
| `TEAM_NAME` | text | yes |  |
| `GAME_ID` | bigint | yes | MUL |
| `GAME_DATE` | datetime | yes |  |
| `MATCHUP` | text | yes |  |
| `WL` | text | yes |  |
| `MIN` | bigint | yes |  |
| `PTS` | bigint | yes |  |
| `FGM` | bigint | yes |  |
| `FGA` | bigint | yes |  |
| `FG_PCT` | double | yes |  |
| `FG3M` | bigint | yes |  |
| `FG3A` | bigint | yes |  |
| `FG3_PCT` | double | yes |  |
| `FTM` | bigint | yes |  |
| `FTA` | bigint | yes |  |
| `FT_PCT` | double | yes |  |
| `OREB` | bigint | yes |  |
| `DREB` | bigint | yes |  |
| `REB` | bigint | yes |  |
| `AST` | bigint | yes |  |
| `STL` | bigint | yes |  |
| `BLK` | bigint | yes |  |
| `TOV` | bigint | yes |  |
| `PF` | bigint | yes |  |
| `PLUS_MINUS` | double | yes |  |

Indexes: `idx_game_list_game_id` (GAME_ID); `idx_game_list_team_date` (TEAM_ID,GAME_DATE)

</details>

<a id="historical_injury_report"></a>
<details><summary><code>historical_injury_report</code> - 12 columns, ~108k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `id` | int | no | PRI |
| `game_date` | date | no | MUL |
| `report_timestamp` | datetime | no |  |
| `team_name` | varchar(50) | no |  |
| `team_id` | bigint | yes | MUL |
| `matchup` | varchar(20) | yes |  |
| `player_name` | varchar(100) | no |  |
| `player_id` | bigint | yes |  |
| `status` | varchar(20) | no | MUL |
| `reason` | text | yes |  |
| `source` | varchar(50) | no |  |
| `created_at` | timestamp | yes |  |

Indexes: `idx_game_date` (game_date); `idx_status` (status); `idx_team_player` (team_id,player_id); `PRIMARY` (id) unique; `unique_player_game` (game_date,team_name,player_name) unique

</details>

<a id="importedgamesmemory"></a>
<details><summary><code>importedgamesmemory</code> - 35 columns, ~42k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `gameId` | bigint | yes |  |
| `nba_data.boxscoreadvancedv3_player` | bigint | yes |  |
| `nba_data.boxscoreadvancedv3_team` | bigint | yes |  |
| `nba_data.boxscoredefensivev2_player` | bigint | yes |  |
| `nba_data.boxscoredefensivev2_team` | bigint | yes |  |
| `nba_data.boxscorefourfactorsv3_player` | bigint | yes |  |
| `nba_data.boxscorefourfactorsv3_team` | bigint | yes |  |
| `nba_data.boxscorehustlev2_player` | bigint | yes |  |
| `nba_data.boxscorehustlev2_team` | bigint | yes |  |
| `nba_data.boxscoremiscv3_player` | bigint | yes |  |
| `nba_data.boxscoremiscv3_team` | bigint | yes |  |
| `nba_data.boxscoreplayertrackv3_player` | bigint | yes |  |
| `nba_data.boxscoreplayertrackv3_team` | bigint | yes |  |
| `nba_data.boxscorescoringv3_player` | bigint | yes |  |
| `nba_data.boxscorescoringv3_team` | bigint | yes |  |
| `nba_data.boxscoresummaryv2_game_info` | bigint | yes |  |
| `nba_data.boxscoresummaryv2_inactive_players` | bigint | yes |  |
| `nba_data.boxscoresummaryv2_other_stats` | bigint | yes |  |
| `nba_data.boxscoresummaryv2_referee` | bigint | yes |  |
| `nba_data.boxscoresummaryv2_summary` | bigint | yes |  |
| `nba_data.boxscoretraditionalv3_bench` | bigint | yes |  |
| `nba_data.boxscoretraditionalv3_player` | bigint | yes |  |
| `nba_data.boxscoretraditionalv3_team` | bigint | yes |  |
| `nba_data.boxscoreusagev3_player` | bigint | yes |  |
| `nba_data.boxscoreusagev3_team` | bigint | yes |  |
| `dateImportedToDB` | timestamp | yes |  |
| `number_reattempts` | int | yes |  |
| `nba_data.boxscoresummaryv3_game_summary` | tinyint | yes |  |
| `nba_data.boxscoresummaryv3_game_info` | tinyint | yes |  |
| `nba_data.boxscoresummaryv3_arena_info` | tinyint | yes |  |
| `nba_data.boxscoresummaryv3_officials` | tinyint | yes |  |
| `nba_data.boxscoresummaryv3_line_score` | tinyint | yes |  |
| `nba_data.boxscoresummaryv3_inactive_players` | tinyint | yes |  |
| `nba_data.boxscoresummaryv3_last_five_meetings` | tinyint | yes |  |
| `nba_data.boxscoresummaryv3_other_stats` | tinyint | yes |  |

</details>

<a id="model_predictions"></a>
<details><summary><code>model_predictions</code> - 21 columns, ~15k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `prediction_id` | int | no | PRI |
| `game_id` | varchar(50) | no | MUL |
| `prediction_timestamp` | datetime | no | MUL |
| `game_date` | date | no | MUL |
| `model_type` | varchar(20) | no | MUL |
| `model_version` | varchar(100) | no | MUL |
| `home_team` | varchar(50) | no |  |
| `away_team` | varchar(50) | no |  |
| `predicted_winner` | varchar(50) | no |  |
| `predicted_margin` | float | no |  |
| `home_win_probability` | float | no |  |
| `home_win_probability_raw` | float | yes |  |
| `margin_uncertainty` | float | yes |  |
| `features_used` | text | yes |  |
| `feature_count` | int | no |  |
| `actual_winner` | varchar(50) | yes |  |
| `actual_margin` | float | yes |  |
| `is_correct` | tinyint(1) | yes |  |
| `margin_error` | float | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |

Indexes: `idx_game_date` (game_date); `idx_game_id` (game_id); `idx_model_type` (model_type); `idx_model_version` (model_version); `idx_prediction_timestamp` (prediction_timestamp); `PRIMARY` (prediction_id) unique; `unique_prediction` (game_id,model_type,model_version) unique

</details>

<a id="model_registry"></a>
<details><summary><code>model_registry</code> - 27 columns, 176 rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `registry_id` | int | no | PRI |
| `model_type` | varchar(50) | no | MUL |
| `model_version` | varchar(100) | no |  |
| `training_date` | date | no | MUL |
| `feature_count` | int | no |  |
| `training_samples` | int | no |  |
| `test_samples` | int | no |  |
| `test_accuracy` | float | yes |  |
| `test_auc` | float | yes |  |
| `test_precision` | float | yes |  |
| `test_recall` | float | yes |  |
| `test_f1` | float | yes |  |
| `test_mae` | float | yes |  |
| `test_rmse` | float | yes |  |
| `test_r2` | float | yes |  |
| `is_current` | tinyint(1) | yes | MUL |
| `file_path` | varchar(255) | no |  |
| `feature_names` | json | yes |  |
| `created_at` | timestamp | yes |  |
| `train_start_date` | date | yes |  |
| `train_end_date` | date | yes |  |
| `test_start_date` | date | yes |  |
| `test_end_date` | date | yes |  |
| `hyperparameters` | json | yes |  |
| `train_metrics` | json | yes |  |
| `notes` | text | yes |  |
| `run_kind` | varchar(20) | yes |  |

Indexes: `idx_is_current` (is_current); `idx_model_type` (model_type); `idx_training_date` (training_date); `PRIMARY` (registry_id) unique; `unique_version` (model_type,model_version) unique

</details>

<a id="nba_players"></a>
<details><summary><code>nba_players</code> - 5 columns, ~5k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `id` | bigint | yes |  |
| `full_name` | text | yes |  |
| `first_name` | text | yes |  |
| `last_name` | text | yes |  |
| `is_active` | tinyint(1) | yes |  |

</details>

<a id="nba_teams"></a>
<details><summary><code>nba_teams</code> - 7 columns, 30 rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `id` | bigint | yes |  |
| `full_name` | text | yes |  |
| `abbreviation` | text | yes |  |
| `nickname` | text | yes |  |
| `city` | text | yes |  |
| `state` | text | yes |  |
| `year_founded` | bigint | yes |  |

</details>

<a id="player_impact"></a>
<details><summary><code>player_impact</code> - 14 columns, ~18k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `player_id` | bigint | no | PRI |
| `team_id` | bigint | no | PRI |
| `compute_date` | date | no | PRI |
| `player_name` | varchar(100) | yes |  |
| `impact` | float | yes |  |
| `raw_impact` | float | yes |  |
| `confidence` | varchar(20) | yes |  |
| `method` | varchar(20) | yes |  |
| `games_with` | int | yes |  |
| `games_without` | int | yes |  |
| `avg_minutes` | float | yes |  |
| `avg_usage` | float | yes |  |
| `importance_multiplier` | float | yes |  |
| `created_at` | timestamp | yes |  |

Indexes: `idx_player_impact_date` (compute_date); `idx_player_impact_player` (player_id); `idx_player_impact_team_date` (team_id,compute_date); `PRIMARY` (player_id,team_id,compute_date) unique

</details>

<a id="player_predictions"></a>
<details><summary><code>player_predictions</code> - 39 columns, ~62k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `id` | bigint | no | PRI |
| `game_id` | bigint | no | MUL |
| `game_date` | date | no | MUL |
| `person_id` | bigint | no | MUL |
| `player_name` | varchar(100) | yes |  |
| `team_id` | bigint | yes | MUL |
| `team_abbrev` | varchar(10) | yes |  |
| `opp_team_id` | bigint | yes |  |
| `opp_abbrev` | varchar(10) | yes |  |
| `is_home` | tinyint | yes |  |
| `model_type` | varchar(30) | no |  |
| `model_version` | varchar(50) | no |  |
| `pred_min` | float | yes |  |
| `pred_pts` | float | yes |  |
| `pred_reb` | float | yes |  |
| `pred_ast` | float | yes |  |
| `pred_stl` | float | yes |  |
| `pred_blk` | float | yes |  |
| `pred_tov` | float | yes |  |
| `pred_fg3m` | float | yes |  |
| `pred_fg3a` | float | yes |  |
| `pred_ftm` | float | yes |  |
| `pred_fta` | float | yes |  |
| `actual_min` | float | yes |  |
| `actual_pts` | float | yes |  |
| `actual_reb` | float | yes |  |
| `actual_ast` | float | yes |  |
| `actual_stl` | float | yes |  |
| `actual_blk` | float | yes |  |
| `actual_tov` | float | yes |  |
| `actual_fg3m` | float | yes |  |
| `actual_fg3a` | float | yes |  |
| `actual_ftm` | float | yes |  |
| `actual_fta` | float | yes |  |
| `prediction_timestamp` | timestamp | yes |  |
| `team_pace_l10` | float | yes |  |
| `opp_pace_l10` | float | yes |  |
| `opp_drtg_l10` | float | yes |  |
| `opp_3pa_allowed_l10` | float | yes |  |

Indexes: `idx_pp_date` (game_date); `idx_pp_person_date` (person_id,game_date); `idx_pp_team` (team_id,game_date); `PRIMARY` (id) unique; `uq_player_pred` (game_id,person_id,model_type,model_version) unique

</details>

<a id="playoff_series_context"></a>
<details><summary><code>playoff_series_context</code> - 12 columns, ~2k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `game_id` | bigint | no | PRI |
| `game_date` | date | yes |  |
| `season_id` | varchar(12) | yes |  |
| `series_game_no` | int | yes |  |
| `home_series_wins` | int | yes |  |
| `away_series_wins` | int | yes |  |
| `series_win_diff` | int | yes |  |
| `home_faces_elim` | tinyint | yes |  |
| `away_faces_elim` | tinyint | yes |  |
| `home_has_hca` | tinyint | yes |  |
| `series_prior_margin_home` | float | yes |  |
| `computed_at` | timestamp | yes |  |

Indexes: `PRIMARY` (game_id) unique

</details>

<a id="team_elo_pregame"></a>
<details><summary><code>team_elo_pregame</code> - 10 columns, ~41k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `id` | int | no | PRI |
| `game_id` | bigint | no | UNI |
| `game_date` | date | no | MUL |
| `home_team_id` | bigint | no | MUL |
| `away_team_id` | bigint | no | MUL |
| `home_elo` | float | no |  |
| `away_elo` | float | no |  |
| `elo_diff` | float | no |  |
| `elo_p_home` | float | no |  |
| `computed_at` | timestamp | yes |  |

Indexes: `idx_away_team` (away_team_id); `idx_game_date` (game_date); `idx_home_team` (home_team_id); `PRIMARY` (id) unique; `unique_game` (game_id) unique

</details>

<a id="team_lineup_snapshots"></a>
<details><summary><code>team_lineup_snapshots</code> - 15 columns, 450 rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `id` | int | no | PRI |
| `season` | varchar(10) | no | MUL |
| `snapshot_date` | date | no | MUL |
| `team_id` | bigint | no | MUL |
| `team_abbrev` | varchar(5) | yes |  |
| `lineup_top_min` | float | yes |  |
| `lineup_top_net_rtg` | float | yes |  |
| `lineup_top_off_rtg` | float | yes |  |
| `lineup_top_def_rtg` | float | yes |  |
| `lineup_top_pace` | float | yes |  |
| `lineup_top_ts_pct` | float | yes |  |
| `lineup_top5_avg_net_rtg` | float | yes |  |
| `lineup_top5_min_share` | float | yes |  |
| `lineup_n_active` | int | yes |  |
| `fetched_at` | timestamp | yes |  |

Indexes: `idx_snap` (snapshot_date); `idx_team` (team_id); `PRIMARY` (id) unique; `unique_snap` (season,snapshot_date,team_id) unique

</details>

<a id="vegas_lines"></a>
<details><summary><code>vegas_lines</code> - 16 columns, ~6k rows</summary>

| Column | Type | Null | Key |
|---|---|---|---|
| `id` | int | no | PRI |
| `game_date` | date | no | MUL |
| `home_team_id` | bigint | yes | MUL |
| `away_team_id` | bigint | yes |  |
| `home_team_abbrev` | varchar(10) | no |  |
| `away_team_abbrev` | varchar(10) | no |  |
| `game_id` | bigint | yes |  |
| `source` | varchar(50) | no | MUL |
| `bookmaker` | varchar(50) | yes |  |
| `line_type` | varchar(20) | no |  |
| `home_spread` | float | yes |  |
| `total` | float | yes |  |
| `home_moneyline` | int | yes |  |
| `away_moneyline` | int | yes |  |
| `fetched_at` | timestamp | yes |  |
| `notes` | text | yes |  |

Indexes: `idx_game_date` (game_date); `idx_source` (source); `idx_teams` (home_team_id,away_team_id); `PRIMARY` (id) unique; `unique_line` (game_date,home_team_abbrev,away_team_abbrev,source,line_type) unique

</details>

<!-- END GENERATED -->
