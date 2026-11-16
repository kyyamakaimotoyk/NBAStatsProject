-- Recovery for box scores the importer skipped (found 2026-11-16).
--
-- Root cause: the importer's re-import pass asked the NBA for the game id as a
-- bigint (22400129, no leading zeros). For that id the NBA returns no player
-- rows and all-NULL team rows. So any game whose first fetch failed or came
-- back early never recovered: its player tables were recorded as "no data",
-- its team tables got NULL rows marked as success. That's ~0.5% of games in
-- 2012-13, 2024-25 and 2025-26, plus 2026-27 games fetched before publication.
-- Fixed in main_refactored.py on 2026-11-16: ids are always zero-padded, rows
-- without ids are dropped, and "no data" is retried until the game is 10 days old.
--
-- Safe to run more than once. The first run (2026-11-16, before the padding
-- fix) re-fetched with the unpadded id and recovered nothing, so run it again.
--
-- What this does:
--   A. Deletes the all-NULL rows (they join to nothing; no feature reads them).
--   B. For every regular-season / play-in / playoff game with no rows in a
--      table, sets that table's status in importedgamesmemory to 0 (failed),
--      so the next ingest re-fetches it. Seasons before an endpoint has data
--      are left alone (hustle: from 2016-17, defensive: from 2017-18, the rest
--      from 1996-97). If the NBA still has nothing, the new importer records
--      status 2 and gives up (game older than 10 days).
--
-- Run ONLY with the importer from commit "Ingest: re-import with zero-padded
-- game ids" or later in place; older code fetches the wrong id again.
--
--   mysql -u <your_user> -p nba_data < sql/recover_2026_11_missing_boxscores.sql
--   .venv\Scripts\python data_engineering\home_ingest_push.py --window-days 30
--
-- Expect ~515 games / ~2,100 API calls (30-45 min extra in that run). Then
-- `python data_engineering/api_schema_check.py` should show no API_DATA_GAP
-- lines except games the NBA genuinely never published.

-- Preview (read-only)

SELECT 'boxscoreadvancedv3_player' AS tbl, COUNT(*) AS null_rows FROM `boxscoreadvancedv3_player` WHERE gameId IS NULL;
SELECT 'boxscoreadvancedv3_team' AS tbl, COUNT(*) AS null_rows FROM `boxscoreadvancedv3_team` WHERE gameId IS NULL;
SELECT 'boxscoredefensivev2_player' AS tbl, COUNT(*) AS null_rows FROM `boxscoredefensivev2_player` WHERE gameId IS NULL;
SELECT 'boxscoredefensivev2_team' AS tbl, COUNT(*) AS null_rows FROM `boxscoredefensivev2_team` WHERE gameId IS NULL;
SELECT 'boxscorefourfactorsv3_player' AS tbl, COUNT(*) AS null_rows FROM `boxscorefourfactorsv3_player` WHERE gameId IS NULL;
SELECT 'boxscorefourfactorsv3_team' AS tbl, COUNT(*) AS null_rows FROM `boxscorefourfactorsv3_team` WHERE gameId IS NULL;
SELECT 'boxscorehustlev2_player' AS tbl, COUNT(*) AS null_rows FROM `boxscorehustlev2_player` WHERE gameId IS NULL;
SELECT 'boxscorehustlev2_team' AS tbl, COUNT(*) AS null_rows FROM `boxscorehustlev2_team` WHERE gameId IS NULL;
SELECT 'boxscoremiscv3_player' AS tbl, COUNT(*) AS null_rows FROM `boxscoremiscv3_player` WHERE gameId IS NULL;
SELECT 'boxscoremiscv3_team' AS tbl, COUNT(*) AS null_rows FROM `boxscoremiscv3_team` WHERE gameId IS NULL;
SELECT 'boxscoreplayertrackv3_player' AS tbl, COUNT(*) AS null_rows FROM `boxscoreplayertrackv3_player` WHERE gameId IS NULL;
SELECT 'boxscoreplayertrackv3_team' AS tbl, COUNT(*) AS null_rows FROM `boxscoreplayertrackv3_team` WHERE gameId IS NULL;
SELECT 'boxscorescoringv3_player' AS tbl, COUNT(*) AS null_rows FROM `boxscorescoringv3_player` WHERE gameId IS NULL;
SELECT 'boxscorescoringv3_team' AS tbl, COUNT(*) AS null_rows FROM `boxscorescoringv3_team` WHERE gameId IS NULL;
SELECT 'boxscoretraditionalv3_player' AS tbl, COUNT(*) AS null_rows FROM `boxscoretraditionalv3_player` WHERE gameId IS NULL;
SELECT 'boxscoretraditionalv3_bench' AS tbl, COUNT(*) AS null_rows FROM `boxscoretraditionalv3_bench` WHERE gameId IS NULL;
SELECT 'boxscoretraditionalv3_team' AS tbl, COUNT(*) AS null_rows FROM `boxscoretraditionalv3_team` WHERE gameId IS NULL;
SELECT 'boxscoreusagev3_player' AS tbl, COUNT(*) AS null_rows FROM `boxscoreusagev3_player` WHERE gameId IS NULL;
SELECT 'boxscoreusagev3_team' AS tbl, COUNT(*) AS null_rows FROM `boxscoreusagev3_team` WHERE gameId IS NULL;

START TRANSACTION;

-- A. All-NULL rows
DELETE FROM `boxscoreadvancedv3_player` WHERE gameId IS NULL;
DELETE FROM `boxscoreadvancedv3_team` WHERE gameId IS NULL;
DELETE FROM `boxscoredefensivev2_player` WHERE gameId IS NULL;
DELETE FROM `boxscoredefensivev2_team` WHERE gameId IS NULL;
DELETE FROM `boxscorefourfactorsv3_player` WHERE gameId IS NULL;
DELETE FROM `boxscorefourfactorsv3_team` WHERE gameId IS NULL;
DELETE FROM `boxscorehustlev2_player` WHERE gameId IS NULL;
DELETE FROM `boxscorehustlev2_team` WHERE gameId IS NULL;
DELETE FROM `boxscoremiscv3_player` WHERE gameId IS NULL;
DELETE FROM `boxscoremiscv3_team` WHERE gameId IS NULL;
DELETE FROM `boxscoreplayertrackv3_player` WHERE gameId IS NULL;
DELETE FROM `boxscoreplayertrackv3_team` WHERE gameId IS NULL;
DELETE FROM `boxscorescoringv3_player` WHERE gameId IS NULL;
DELETE FROM `boxscorescoringv3_team` WHERE gameId IS NULL;
DELETE FROM `boxscoretraditionalv3_player` WHERE gameId IS NULL;
DELETE FROM `boxscoretraditionalv3_bench` WHERE gameId IS NULL;
DELETE FROM `boxscoretraditionalv3_team` WHERE gameId IS NULL;
DELETE FROM `boxscoreusagev3_player` WHERE gameId IS NULL;
DELETE FROM `boxscoreusagev3_team` WHERE gameId IS NULL;

-- B. Re-queue games with no rows
UPDATE importedgamesmemory m
  JOIN (SELECT DISTINCT GAME_ID, SEASON_ID FROM game_list) g ON g.GAME_ID = m.gameId
   SET m.`nba_data.boxscoreadvancedv3_player` = 0
 WHERE LEFT(g.SEASON_ID, 1) IN ('2', '4', '5')
   AND CAST(SUBSTRING(g.SEASON_ID, 2) AS UNSIGNED) >= 1996
   AND m.`nba_data.boxscoreadvancedv3_player` <> 0
   AND NOT EXISTS (SELECT 1 FROM `boxscoreadvancedv3_player` x WHERE x.gameId = m.gameId);
UPDATE importedgamesmemory m
  JOIN (SELECT DISTINCT GAME_ID, SEASON_ID FROM game_list) g ON g.GAME_ID = m.gameId
   SET m.`nba_data.boxscoreadvancedv3_team` = 0
 WHERE LEFT(g.SEASON_ID, 1) IN ('2', '4', '5')
   AND CAST(SUBSTRING(g.SEASON_ID, 2) AS UNSIGNED) >= 1996
   AND m.`nba_data.boxscoreadvancedv3_team` <> 0
   AND NOT EXISTS (SELECT 1 FROM `boxscoreadvancedv3_team` x WHERE x.gameId = m.gameId);
UPDATE importedgamesmemory m
  JOIN (SELECT DISTINCT GAME_ID, SEASON_ID FROM game_list) g ON g.GAME_ID = m.gameId
   SET m.`nba_data.boxscoredefensivev2_player` = 0
 WHERE LEFT(g.SEASON_ID, 1) IN ('2', '4', '5')
   AND CAST(SUBSTRING(g.SEASON_ID, 2) AS UNSIGNED) >= 2017
   AND m.`nba_data.boxscoredefensivev2_player` <> 0
   AND NOT EXISTS (SELECT 1 FROM `boxscoredefensivev2_player` x WHERE x.gameId = m.gameId);
UPDATE importedgamesmemory m
  JOIN (SELECT DISTINCT GAME_ID, SEASON_ID FROM game_list) g ON g.GAME_ID = m.gameId
   SET m.`nba_data.boxscoredefensivev2_team` = 0
 WHERE LEFT(g.SEASON_ID, 1) IN ('2', '4', '5')
   AND CAST(SUBSTRING(g.SEASON_ID, 2) AS UNSIGNED) >= 2017
   AND m.`nba_data.boxscoredefensivev2_team` <> 0
   AND NOT EXISTS (SELECT 1 FROM `boxscoredefensivev2_team` x WHERE x.gameId = m.gameId);
UPDATE importedgamesmemory m
  JOIN (SELECT DISTINCT GAME_ID, SEASON_ID FROM game_list) g ON g.GAME_ID = m.gameId
   SET m.`nba_data.boxscorefourfactorsv3_player` = 0
 WHERE LEFT(g.SEASON_ID, 1) IN ('2', '4', '5')
   AND CAST(SUBSTRING(g.SEASON_ID, 2) AS UNSIGNED) >= 1996
   AND m.`nba_data.boxscorefourfactorsv3_player` <> 0
   AND NOT EXISTS (SELECT 1 FROM `boxscorefourfactorsv3_player` x WHERE x.gameId = m.gameId);
UPDATE importedgamesmemory m
  JOIN (SELECT DISTINCT GAME_ID, SEASON_ID FROM game_list) g ON g.GAME_ID = m.gameId
   SET m.`nba_data.boxscorefourfactorsv3_team` = 0
 WHERE LEFT(g.SEASON_ID, 1) IN ('2', '4', '5')
   AND CAST(SUBSTRING(g.SEASON_ID, 2) AS UNSIGNED) >= 1996
   AND m.`nba_data.boxscorefourfactorsv3_team` <> 0
   AND NOT EXISTS (SELECT 1 FROM `boxscorefourfactorsv3_team` x WHERE x.gameId = m.gameId);
UPDATE importedgamesmemory m
  JOIN (SELECT DISTINCT GAME_ID, SEASON_ID FROM game_list) g ON g.GAME_ID = m.gameId
   SET m.`nba_data.boxscorehustlev2_player` = 0
 WHERE LEFT(g.SEASON_ID, 1) IN ('2', '4', '5')
   AND CAST(SUBSTRING(g.SEASON_ID, 2) AS UNSIGNED) >= 2016
   AND m.`nba_data.boxscorehustlev2_player` <> 0
   AND NOT EXISTS (SELECT 1 FROM `boxscorehustlev2_player` x WHERE x.gameId = m.gameId);
UPDATE importedgamesmemory m
  JOIN (SELECT DISTINCT GAME_ID, SEASON_ID FROM game_list) g ON g.GAME_ID = m.gameId
   SET m.`nba_data.boxscorehustlev2_team` = 0
 WHERE LEFT(g.SEASON_ID, 1) IN ('2', '4', '5')
   AND CAST(SUBSTRING(g.SEASON_ID, 2) AS UNSIGNED) >= 2016
   AND m.`nba_data.boxscorehustlev2_team` <> 0
   AND NOT EXISTS (SELECT 1 FROM `boxscorehustlev2_team` x WHERE x.gameId = m.gameId);
UPDATE importedgamesmemory m
  JOIN (SELECT DISTINCT GAME_ID, SEASON_ID FROM game_list) g ON g.GAME_ID = m.gameId
   SET m.`nba_data.boxscoremiscv3_player` = 0
 WHERE LEFT(g.SEASON_ID, 1) IN ('2', '4', '5')
   AND CAST(SUBSTRING(g.SEASON_ID, 2) AS UNSIGNED) >= 1996
   AND m.`nba_data.boxscoremiscv3_player` <> 0
   AND NOT EXISTS (SELECT 1 FROM `boxscoremiscv3_player` x WHERE x.gameId = m.gameId);
UPDATE importedgamesmemory m
  JOIN (SELECT DISTINCT GAME_ID, SEASON_ID FROM game_list) g ON g.GAME_ID = m.gameId
   SET m.`nba_data.boxscoremiscv3_team` = 0
 WHERE LEFT(g.SEASON_ID, 1) IN ('2', '4', '5')
   AND CAST(SUBSTRING(g.SEASON_ID, 2) AS UNSIGNED) >= 1996
   AND m.`nba_data.boxscoremiscv3_team` <> 0
   AND NOT EXISTS (SELECT 1 FROM `boxscoremiscv3_team` x WHERE x.gameId = m.gameId);
UPDATE importedgamesmemory m
  JOIN (SELECT DISTINCT GAME_ID, SEASON_ID FROM game_list) g ON g.GAME_ID = m.gameId
   SET m.`nba_data.boxscoreplayertrackv3_player` = 0
 WHERE LEFT(g.SEASON_ID, 1) IN ('2', '4', '5')
   AND CAST(SUBSTRING(g.SEASON_ID, 2) AS UNSIGNED) >= 1996
   AND m.`nba_data.boxscoreplayertrackv3_player` <> 0
   AND NOT EXISTS (SELECT 1 FROM `boxscoreplayertrackv3_player` x WHERE x.gameId = m.gameId);
UPDATE importedgamesmemory m
  JOIN (SELECT DISTINCT GAME_ID, SEASON_ID FROM game_list) g ON g.GAME_ID = m.gameId
   SET m.`nba_data.boxscoreplayertrackv3_team` = 0
 WHERE LEFT(g.SEASON_ID, 1) IN ('2', '4', '5')
   AND CAST(SUBSTRING(g.SEASON_ID, 2) AS UNSIGNED) >= 1996
   AND m.`nba_data.boxscoreplayertrackv3_team` <> 0
   AND NOT EXISTS (SELECT 1 FROM `boxscoreplayertrackv3_team` x WHERE x.gameId = m.gameId);
UPDATE importedgamesmemory m
  JOIN (SELECT DISTINCT GAME_ID, SEASON_ID FROM game_list) g ON g.GAME_ID = m.gameId
   SET m.`nba_data.boxscorescoringv3_player` = 0
 WHERE LEFT(g.SEASON_ID, 1) IN ('2', '4', '5')
   AND CAST(SUBSTRING(g.SEASON_ID, 2) AS UNSIGNED) >= 1996
   AND m.`nba_data.boxscorescoringv3_player` <> 0
   AND NOT EXISTS (SELECT 1 FROM `boxscorescoringv3_player` x WHERE x.gameId = m.gameId);
UPDATE importedgamesmemory m
  JOIN (SELECT DISTINCT GAME_ID, SEASON_ID FROM game_list) g ON g.GAME_ID = m.gameId
   SET m.`nba_data.boxscorescoringv3_team` = 0
 WHERE LEFT(g.SEASON_ID, 1) IN ('2', '4', '5')
   AND CAST(SUBSTRING(g.SEASON_ID, 2) AS UNSIGNED) >= 1996
   AND m.`nba_data.boxscorescoringv3_team` <> 0
   AND NOT EXISTS (SELECT 1 FROM `boxscorescoringv3_team` x WHERE x.gameId = m.gameId);
UPDATE importedgamesmemory m
  JOIN (SELECT DISTINCT GAME_ID, SEASON_ID FROM game_list) g ON g.GAME_ID = m.gameId
   SET m.`nba_data.boxscoretraditionalv3_player` = 0
 WHERE LEFT(g.SEASON_ID, 1) IN ('2', '4', '5')
   AND CAST(SUBSTRING(g.SEASON_ID, 2) AS UNSIGNED) >= 1996
   AND m.`nba_data.boxscoretraditionalv3_player` <> 0
   AND NOT EXISTS (SELECT 1 FROM `boxscoretraditionalv3_player` x WHERE x.gameId = m.gameId);
UPDATE importedgamesmemory m
  JOIN (SELECT DISTINCT GAME_ID, SEASON_ID FROM game_list) g ON g.GAME_ID = m.gameId
   SET m.`nba_data.boxscoretraditionalv3_bench` = 0
 WHERE LEFT(g.SEASON_ID, 1) IN ('2', '4', '5')
   AND CAST(SUBSTRING(g.SEASON_ID, 2) AS UNSIGNED) >= 1996
   AND m.`nba_data.boxscoretraditionalv3_bench` <> 0
   AND NOT EXISTS (SELECT 1 FROM `boxscoretraditionalv3_bench` x WHERE x.gameId = m.gameId);
UPDATE importedgamesmemory m
  JOIN (SELECT DISTINCT GAME_ID, SEASON_ID FROM game_list) g ON g.GAME_ID = m.gameId
   SET m.`nba_data.boxscoretraditionalv3_team` = 0
 WHERE LEFT(g.SEASON_ID, 1) IN ('2', '4', '5')
   AND CAST(SUBSTRING(g.SEASON_ID, 2) AS UNSIGNED) >= 1996
   AND m.`nba_data.boxscoretraditionalv3_team` <> 0
   AND NOT EXISTS (SELECT 1 FROM `boxscoretraditionalv3_team` x WHERE x.gameId = m.gameId);
UPDATE importedgamesmemory m
  JOIN (SELECT DISTINCT GAME_ID, SEASON_ID FROM game_list) g ON g.GAME_ID = m.gameId
   SET m.`nba_data.boxscoreusagev3_player` = 0
 WHERE LEFT(g.SEASON_ID, 1) IN ('2', '4', '5')
   AND CAST(SUBSTRING(g.SEASON_ID, 2) AS UNSIGNED) >= 1996
   AND m.`nba_data.boxscoreusagev3_player` <> 0
   AND NOT EXISTS (SELECT 1 FROM `boxscoreusagev3_player` x WHERE x.gameId = m.gameId);
UPDATE importedgamesmemory m
  JOIN (SELECT DISTINCT GAME_ID, SEASON_ID FROM game_list) g ON g.GAME_ID = m.gameId
   SET m.`nba_data.boxscoreusagev3_team` = 0
 WHERE LEFT(g.SEASON_ID, 1) IN ('2', '4', '5')
   AND CAST(SUBSTRING(g.SEASON_ID, 2) AS UNSIGNED) >= 1996
   AND m.`nba_data.boxscoreusagev3_team` <> 0
   AND NOT EXISTS (SELECT 1 FROM `boxscoreusagev3_team` x WHERE x.gameId = m.gameId);

COMMIT;

-- Check: games queued for re-fetch per table (expect ~515 distinct games overall)
SELECT COUNT(*) AS games_requeued FROM importedgamesmemory WHERE `nba_data.boxscoreadvancedv3_player` = 0
    OR `nba_data.boxscoreadvancedv3_team` = 0
    OR `nba_data.boxscoredefensivev2_player` = 0
    OR `nba_data.boxscoredefensivev2_team` = 0
    OR `nba_data.boxscorefourfactorsv3_player` = 0
    OR `nba_data.boxscorefourfactorsv3_team` = 0
    OR `nba_data.boxscorehustlev2_player` = 0
    OR `nba_data.boxscorehustlev2_team` = 0
    OR `nba_data.boxscoremiscv3_player` = 0
    OR `nba_data.boxscoremiscv3_team` = 0
    OR `nba_data.boxscoreplayertrackv3_player` = 0
    OR `nba_data.boxscoreplayertrackv3_team` = 0
    OR `nba_data.boxscorescoringv3_player` = 0
    OR `nba_data.boxscorescoringv3_team` = 0
    OR `nba_data.boxscoretraditionalv3_player` = 0
    OR `nba_data.boxscoretraditionalv3_bench` = 0
    OR `nba_data.boxscoretraditionalv3_team` = 0
    OR `nba_data.boxscoreusagev3_player` = 0
    OR `nba_data.boxscoreusagev3_team` = 0;
