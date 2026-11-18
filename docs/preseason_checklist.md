# Pre-season checklist — 2026-27 (work through this in September/October)

The offseason build (July 2026) left the system fully automated: nightly home
ingest → S3 → cloud load/grade/predict, weekly cloud retrain, freshness +
heartbeat + drift alarms. This checklist is what CAN'T be done until the season
approaches. Check items off in order; most are 5-minute verifications.

## August — when the NBA publishes the 2026-27 schedule
- [ ] Confirm the home ingest ships schedule rows: `logs\home_ingest.log` should
      show `schedule: N games` with N > 0.
- [ ] Confirm the cloud flips to the DB schedule source: the nightly task log
      shows `schedule: using league_schedule table (DB)` (not the CDN/stats
      fallback chain).

## Late September — data refresh
- [ ] Injury scraper catch-up for any summer format changes:
      `python data_engineering/historical_injury_scraper.py --start-date 2026-06-14`
- [ ] Lineup snapshots (home-only, nba_api):
      `python data_engineering/lineup_features.py --season 2026-27`
      (E11 features are off in prod — this is for research continuity only.)
- [ ] Verify Task Scheduler still runs `NBA Home Ingest` daily at **15:00 JST**
      (`schtasks /Query /TN "NBA Home Ingest"`), and that drops land in S3.

## Opening week — verify the loops with real games
- [ ] Morning after the first slate: site shows graded picks + injury report;
      nightly log shows `freshness: OK`, `backfill: {...updated...}`,
      `drift check ... (OK)` (drift check activates at >=60 graded games in 21
      days — roughly two weeks into the season), `NIGHTLY_RUN_OK`.
- [ ] First Monday: weekly retrain ran (new `*_current` bundles in S3, new
      lineage-tagged registry rows, `[E20]`-era calibrator shift NOTE within
      healthy range). Spot-check validate output in the task log.
- [ ] Alarm live-test (ops_lab lesson: untested monitoring is hope): disable the
      home task for 2 days → expect the stale-data email on day 2 → re-enable →
      expect recovery email.

## Two-plus weeks in — model follow-ups (from E21)
- [ ] Online-Platt re-pilot once ~200 live (raw, outcome) pairs accumulate:
      `python experiments/e21_online_pilot.py` — decide whether weekly-refit
      Platt display calibration beats the per-retrain eval-slice isotonic.
- [ ] Review XGB's playoff-window sensitivity from E19/E21 before the first
      long road trips (it drops hardest on regime shift).
- [ ] Check the drift monitor fired 0 times; if it fired, the runbook is:
      inspect `[E20]` shift telemetry in the last retrain, compare
      raw-vs-displayed on recent rows, force a retrain (fresh calibrator).

## P-2 / E26 — common retrain + walk-forward track record (added 2026-10-30)
Code shipped 2026-10-30 (tuning log §E26). These steps write to the DBs, so Kai
runs them, in order:
- [x] **Verify the weekly retrain on RDS** (2026-11-02): trained every week, but
      no bundle ever reached S3 (missing `s3:PutObject`), see §E26 Addendum.
- [x] **Fix the push, in this order** (done 2026-11-04/05: apply, push, retrain,
      player-only retrain after CI; check task shows all four bundles through
      2026-10-27, sync + freshness OK) (apply BEFORE pushing the code, or the new
      `NIGHTLY_RETRAINED` alarm emails three times a day until a bundle lands):
      1. `cd infra && terraform plan` → expect one in-place update to
         `aws_iam_role_policy.ecs_task_s3` (a `s3:PutObject` statement), then
         `terraform apply`.
      2. `git push` (CI rebuilds the pipeline image).
      3. Store fresh bundles now instead of waiting for Monday:
         `aws ecs run-task --cli-input-json file://tmp/run_weekly_retrain_task.json`
         (~15-20 min). Its log should end with `[retrain] artifact store: OK`.
      4. Re-run `aws ecs run-task --cli-input-json file://tmp/run_check_track_record_task.json`:
         section 2 should show 252 features, `freshness: OK` for rf/xgb/nn and
         player_xgb.
      5. The next nightly prints `bundle sync: OK`, `bundle freshness: OK`, and
         no `Feature count changed` / `NIGHTLY_RETRAINED`.
      Reading logs in Git Bash: prefix `MSYS_NO_PATHCONV=1` (otherwise
      `/ecs/...` becomes a Windows path).
- [ ] Optional cleanup: RDS `model_registry` has ~6 rows per scheduled run since
      2026-07-17 from in-process retrains whose bundles were never stored
      (`file_path` points nowhere). Harmless; delete only if the Model Evolution
      tab gets noisy.
- [x] **Rebuild 2025-26 locally** (2026-11-05: 1,837 rows, 0 errors): dry-run first, expect 1,837 rows (RF 832 /
      NN 818 superseded, XGB 187 new):
      `python modeling/walkforward_backfill.py --models rf,nn,xgb --start 2025-10 --end 2026-06 --supersede-non-wf --dry-run`
      then the same command without `--dry-run` (trains 9 months x 3 models; NN is
      the slow one).
- [x] `python scripts/check_track_record.py --skip-bundles`: 2025-26 should read
      all `wf` for every model. (1,215 per model; 4 games with no features-snapshot
      row keep old RF/NN rows and fall out of the paired set.)
- [x] **Ship to RDS** (2026-11-05: 12,494 rows loaded via one-off
      `tmp/run_s3_loader_task.json`; RDS check matches local exactly): `python scripts/ship_wf_predictions.py --dry-run`, check
      the per-season counts (2025-26 should read **1,379** wf_ rows for every
      model, all game types; the check script's 1,215 is regular season only; before the rebuild it was rf 547 / nn 561 / xgb 1,192), then
      without `--dry-run`. The next nightly loads it
      (or run the loader one-off). Re-run the check task against RDS.
- [ ] `/accuracy` 2025-26 per model after ~5 min edge cache; rebuild the web
      site if any page bakes the numbers.
- [ ] Then: re-run the #11 analysis; rework #5 Figure 2 (articles.md P-2).
- [ ] Each Monday from now: the weekly retrain log ends with
      `[retrain] all 3 models retrained and in sync`; the nightly prints
      `bundle sync: OK (rf, nn, xgb)`. `RETRAIN_FAILED` / `MODEL_BUNDLE_SYNC`
      arrive by email through the existing ERROR filter.

## E28 — single serving path (added 2026-11-13)
Code done 2026-11-13 (tuning log §E28 "Step 2"): nightly predictions now build
their inputs with the training pipeline. Nothing is deployed until the push.
Kai runs these, in order:
- [ ] **Home ingest down since 2026-10-28: fix built 2026-11-13.** Cause: NBA-side
      change; nba_api 1.11.3 times out on every stats.nba.com call (widely
      reported, swar/nba_api #728). nba_api **1.12.0** works for every endpoint the
      ingest uses (tested 2026-11-13 in an isolated folder). Second bug: on a failed
      fetch the job crashed on a cp932 `UnicodeEncodeError` before exporting, so
      nothing shipped at all; now fixed (`_console_safe`). Kai runs, in a normal
      Windows terminal from the project root:
      1. `.venv\Scripts\pip install nba_api==1.12.0` (requirements.txt already pinned).
      2. Recovery run with a wide window (local game_list stops 2026-10-27, so the
         default 14-day window would miss Oct 28-30, and injury rows go back to
         opening night): `python data_engineering\home_ingest_push.py --window-days 30`
         Expect: the fetch imports ~200+ games, `injuries:` lines scrape about 30
         report dates, `export: ... historical_injury_report` appears, and the drop
         uploads ending `manifest.json (drop complete)`.
      3. The next cloud nightly loads it (`[s3_ingest]` lines) and prints
         `freshness: OK`. Or load it now:
         `aws ecs run-task --cli-input-json file://tmp/run_s3_loader_task.json`
      4. The weekly retrain then rebuilds features with real 2026-27 box scores and
         availability (or run the retrain task now, see P-2 above).
- [ ] **Official injury reports (fix built 2026-11-13).** The scraper was never
      scheduled, so 2026-27 had no official-report rows: training rows showed
      everyone available while serving used the ESPN feed. Now the daily home
      ingest backfills missing report dates (45 days) and re-scrapes the last 2
      with `--replace`, then ships the table (date_window on game_date). For
      tonight's games, add the pre-tip task (scrapes today's report, ET date, and
      ships only that table before the cloud's 5:45 PM ET run):
      `schtasks /Create /TN "NBA Injuries PreTip" /TR "D:\Kai\PycharmProjects\NBAStatsProject\scripts\home_injuries.bat" /SC DAILY /ST 07:20`
      07:20 JST = 17:20 EST. **In US daylight time (from 2027-03-14) change it to
      06:20** (`schtasks /Change /TN "NBA Injuries PreTip" /ST 06:20`), and back to
      07:20 in November. Check `logs\home_injuries.log`; on the cloud the
      5:45 PM run should print `availability for <date>: N out/doubtful from the
      official report`. The PC must be awake at that time, like for the main ingest.
- [x] **Can the injury scrape move to the cloud? Probe first (added 2026-11-18).**
      **RESULT 2026-11-18: GO.** From Fargate both PDFs returned HTTP 200 + valid PDF in
      0.1s (same byte counts as from home), `stats_ctrl` timed out at 30s (confirms AWS
      egress), `java` missing (expected). **Move BUILT 2026-11-18** (next item).
      Nobody ever tested the PDF host (`ak-static.cms.nba.com`) from AWS; the
      "residential only" note was carried over from stats.nba.com. From home it
      answers as plain `AmazonS3`, with no browser headers needed. To check from AWS
      (~2 min, a few cents; uses the current image, no push needed):
      `aws ecs run-task --cli-input-json file://infra/injury-probe-runtask.json --query "tasks[0].taskArn"`
      then `aws logs tail /ecs/nba-game-predictor-pipeline --since 5m --format short`.
      Go = both `pdf_*` lines read `HTTP 200 ... pdf=True` (`stats_ctrl` should time
      out, which shows the task really is on an AWS IP; `java` reads `missing`, as
      expected). On a go, the move is: JRE + `nbainjuries` in the pipeline image,
      the scraper run against RDS inside `batch_predict_today` (before availability
      is built), and then retire `home_injuries.bat`. See CHANGELOG 2026-11-18.
- [ ] **Injury scrape now runs in the cloud (built 2026-11-18).** `Dockerfile.pipeline`
      adds a Java runtime, `requirements-pipeline.txt` adds `nbainjuries`, and
      `batch_predict_today` scrapes today's (ET) official report into RDS right after
      the S3 load, on every non-backfill run (`--skip-injury-scrape` turns it off).
      Checked locally: the image builds, and 434 report rows over 3 dates parse
      identically in the container (Java 21) and on the PC (Java 8).
      1. Commit and `git push`. CI rebuilds the pipeline image; no terraform change.
      2. The 11 AM ET run logs `injuries: scraping the official report for <date>`,
         and often `no report found` (normal: the first game-day report comes
         later). The 5:45 PM ET run should log `-> ts=17:xx rows=N` and then
         `availability for <date>: N out/doubtful from the official report`. An
         `ERROR: official injury scrape ...` line emails through the ERROR alarm.
      3. After one good 5:45 PM run, retire the home pre-tip task:
         `schtasks /Delete /TN "NBA Injuries PreTip" /F`
         Keep the nightly home ingest's injury backfill: it re-ships each finished
         date's final (latest) report, which is what training uses.
- [ ] **nba_api schema check (added 2026-11-16).** The home side works as soon as the
      code is on the PC: the next home ingest log shows `[api_schema] ... status: OK/CHANGED`.
      Cloud email alerts need the image push. After the push and the catch-up rerun, the
      nightly loader log should show `api_schema OK` and no `ERROR: API_DATA_GAP` (those
      fire until the box scores since 2026-10-28 have landed). Runbook: README "When
      nba_api or an endpoint changes".
- [x] **Recover skipped box scores (added 2026-11-16; done locally 2026-11-17).**
      Result: 3,082 of 3,379 missing (game, table) pairs recovered, all NULL-id rows
      deleted, 2012-13 and 2024-25 complete. Left: ~26 older games where the NBA has
      no defensive/tracking data (status 2, correct) and 22600189 tracking (never
      published). The 9 never-imported 2025-11-21 games were imported separately.
      `--skip-fetch --window-days 730` shipped 2024-11-17 onward (2,807 games,
      904,843 rows, drop `2026-11-17T034656Z`). Follow-ups are in "Ingest follow-ups
      (2026-11-17)" below. Original steps, for reference:
      The catch-up showed games
      the importer had given up on: empty rows stored for unpublished box scores
      (gameId NULL, game marked done) and a 2-try limit on "no data". 515 games are
      affected: ~230 in 2012-13, ~127 in 2024-25, 66 in 2026-27, a few elsewhere.
      Root cause, found after the first SQL run recovered 0 games: re-imports
      fetched the game id unpadded (22400129), and for that id the NBA returns
      empty box scores. The fix (zero-padded ids) is in the code. Run the SQL again
      in cmd (PowerShell can't use `<`; see the `source` alternative):
      1. `mysql -u <your_user> -p nba_data < sql/recover_2026_11_missing_boxscores.sql`
         (deletes the NULL-id rows, sets the missing tables' status to 0; the
         preview SELECTs at the top print the row counts first).
      2. `.venv\Scripts\python data_engineering\home_ingest_push.py --window-days 30`
         (re-fetches them: ~2,100 API calls, 30-45 min extra).
      3. `python data_engineering/api_schema_check.py`: the `API_DATA_GAP` lines for
         NULL game ids and missing games should be gone, except games the NBA never
         published (those get status 2 and stay listed only while < 30 days old).
      4. Decide on RDS: step 2 ships only the 30-day window, so the 2026-27 games
         reach RDS but the recovered 2012-13 / 2024-25 games stay local. The
         weekly features build reads RDS, so it still lacks them (~127 games of
         2024-25 in its training window). To ship them: `home_ingest_push.py
         --skip-fetch --window-days 700` (the loader replaces per game, so it's
         safe, but it's a large drop; check the loader log afterwards).
- [ ] **Gravity snapshots (added 2026-11-16).** Create the table once (local MySQL):
      `mysql -u <your_user> -p nba_data < sql/create_gravity_leaders_daily.sql`.
      Then store the final 2025-26 values once (needed for proposal E31):
      `python data_engineering/gravity_snapshot.py --date 2026-07-31`.
      From then on, the nightly home ingest logs `gravity: N rows stored for <date>`.
      Until the table exists it logs `table ... missing` and carries on.
- [ ] **Raw archive (added 2026-11-16).** After the next ingest, `data\raw_api\` fills
      with one folder per endpoint. Include it in PC backups (only copy). Optional: once
      the catch-up has run, `backfill_from_raw.py --table <t> --insert-missing --dry-run`
      shows any game whose insert failed after a successful fetch.
- [ ] Locally, before pushing: `python -m unittest tests.test_serving_parity -v`
      (2 tests, ~40 s, both must pass).
- [ ] `git push`. CI rebuilds the pipeline image; the new **Serving invariant**
      step must pass or the old `:latest` stays in ECR. The next scheduled
      nightly uses the new image.
- [ ] Verify the first nightly after the push:
      `MSYS_NO_PATHCONV=1 aws logs tail /ecs/nba-game-predictor-pipeline --since 2h --format short`
      Expect `availability for <date>: ...`, `[serving] <date>: N games as
      placeholders`, `[E9] Joined ELO features: N/N`, `NIGHTLY_RUN_OK`, and **no**
      `SERVING_FEATURES_MISSING` / `SERVING_FEATURES_FAILED`. Runtime grows by
      about a minute (it loads the full game history once per date).
- [ ] After ~1 week: on the home page's model breakdown, margins should spread out
      (RF no longer "home by ~3" for every game) and "pick vs margin" splits
      should drop to roughly 7% (RF) / 18% (XGB), the backtest levels.
- [ ] After ~3 weeks of fixed predictions: re-run the E27 live leg
      (`python experiments/e27_live_check.py`, filter to post-fix dates) and
      unblock articles.md #16.
- [ ] Decide how the public record presents the 2026-27 predictions made before
      the fix (keep as published + note on /accuracy, or relabel). Kai's call;
      no code changes until decided.
- [ ] Before the 2027 playoffs: series-context features are computed only for
      played games (`playoff_series_context`), so a scheduled playoff game would
      get zeros. They are not in the production column set today; build series
      context for scheduled games before any model uses them.

## Ingest follow-ups (2026-11-17)
Open items from the nba_api 1.12 / skipped-box-score session (CHANGELOG 2026-11-16,
README "When nba_api or an endpoint changes"). Kai runs the DB/AWS steps.
Closed by Kai on 2026-11-17 and not tracked: shipping 2012-13 and older recovered
games to RDS, the schema check's network-failure alerts (the outage was known and
scheduled), why the 2025-11-21 games were never imported, and 1995-96.
- [ ] **Verify the RDS load of the re-ship** (drop `2026-11-17T034656Z`):
      `aws logs filter-log-events --log-group-name /ecs/nba-game-predictor-pipeline --start-time 1763351000000 --filter-pattern "\"2026-11-17T034656Z\"" --query "events[].message" --output text`
      Expect one `<table> <- N rows` line per table and `loaded (904843 rows) and
      moved to processed/`. `ERROR loading drop` = still in `pending/`, retried.
      That drop also carries ~35 false `ERROR: API_SCHEMA_CHANGED ... endpoint
      failed` lines (DNS failure on the PC during its schema check): ignore.
- [ ] **RDS probably has the same NULL-gameId rows** (RDS was migrated from local;
      ~133k rows across the team tables locally). The re-ship doesn't remove them:
      the loader deletes `WHERE gameId IN (<shipped ids>)`, which never matches
      NULL. They join to nothing, so no feature is affected (optional cleanup).
      Check on RDS (`SELECT COUNT(*) FROM boxscorehustlev2_team WHERE gameId IS NULL`)
      and run section A of `sql/recover_2026_11_missing_boxscores.sql` there if so.
      The nightly schema check only looks at local MySQL.
- [ ] **Gravity table + 2025-26 snapshot** (see "Gravity snapshots" above), then
      `python scripts/gen_db_schema_doc.py` so the table is documented.
- [ ] **CI image build:** confirm the latest "Build pipeline image" run is green in
      GitHub Actions (pushes `865b7fd` → `a9a52d0` all touched `data_engineering/`).
      The loader's `ERROR:`/`NOTE:` schema-alert lines depend on it.
- [ ] **Clean up `importedgamesmemory` duplicates.** 791 games have two identical
      rows (mostly 2022-23, an old double insert; the table had no key at all). Run,
      with no ingest running:
      `mysql -u <your_user> -p nba_data < sql\dedupe_importedgamesmemory.sql` (cmd)
      It keeps one row per game, adds `PRIMARY KEY (gameId)`, and keeps the old
      table as `importedgamesmemory_backup_20261117`. Expect the last preview to show
      40,800 rows, 0 extra. After a clean nightly ingest:
      `DROP TABLE importedgamesmemory_backup_20261117;`
- [ ] **Local research DB is behind RDS** (found 2026-11-16): local
      `team_elo_pregame` stops at 2026-05-13; `features`, `model_predictions`,
      `vegas_lines` stop at 2026-06-13. Refresh before running the local
      experiments (E29-E32, P8-P9 in the tuning log).
- [ ] **Training data changed**: the next weekly retrain after the RDS load includes
      ~127 recovered 2024-25 games. Registry rows before and after are not strictly
      comparable; mention it if a metric shifts that week.

## Deferred decisions on record
- Retrospective `wf_` rows are deliberately unbadged on the site (user decision
  2026-07-03); provenance lives in `model_predictions.model_version`.
- The daily API restart schedule can be DELETED once the July 11 rotation
  passes cleanly with the rotation-aware connector (see
  memory/feedback_rds_secret_rotation) — `aws_scheduler_schedule.api_daily_restart`.
