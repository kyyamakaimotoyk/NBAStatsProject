-- importedgamesmemory: remove duplicate rows and add a primary key (2026-11-17).
--
-- 791 games have two rows each (1,582 rows), mostly 2022-23 games: an old
-- double insert. The table had no primary key or index, so nothing stopped it.
-- Both copies of every pair are identical (same statuses, same timestamp:
-- updates match on gameId and rewrite both), so keeping either one loses nothing.
-- The primary key also turns the importer's per-game lookups from a full scan
-- into an index lookup.
--
-- Run with no ingest running (Task Scheduler "NBA Home Ingest" not mid-run):
--   cmd:        mysql -u <your_user> -p nba_data < sql\dedupe_importedgamesmemory.sql
--   PowerShell: Get-Content sql\dedupe_importedgamesmemory.sql -Raw | mysql -u <your_user> -p nba_data
--
-- The old table is kept as importedgamesmemory_backup_20261117. Drop it once a
-- nightly ingest has run cleanly:  DROP TABLE importedgamesmemory_backup_20261117;

-- Before: expect 791 duplicated games
SELECT COUNT(*) AS total_rows, COUNT(DISTINCT gameId) AS games,
       COUNT(*) - COUNT(DISTINCT gameId) AS extra_rows
  FROM importedgamesmemory;

-- Copies that disagree on anything (expect 0; if not 0, stop and investigate)
SELECT COUNT(*) AS games_with_differing_copies FROM (
  SELECT gameId FROM (SELECT DISTINCT * FROM importedgamesmemory) d
   GROUP BY gameId HAVING COUNT(*) > 1) x;

CREATE TABLE importedgamesmemory_new LIKE importedgamesmemory;
ALTER TABLE importedgamesmemory_new ADD PRIMARY KEY (gameId);
-- INSERT IGNORE keeps the first copy of each gameId and skips the identical second one.
INSERT IGNORE INTO importedgamesmemory_new SELECT * FROM importedgamesmemory;

-- After (new table): total_rows = games, extra_rows = 0
SELECT COUNT(*) AS total_rows, COUNT(DISTINCT gameId) AS games,
       COUNT(*) - COUNT(DISTINCT gameId) AS extra_rows
  FROM importedgamesmemory_new;

-- Swap (atomic)
RENAME TABLE importedgamesmemory TO importedgamesmemory_backup_20261117,
             importedgamesmemory_new TO importedgamesmemory;
