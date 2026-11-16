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
- [ ] **nba_api schema check (added 2026-11-16).** The home side works as soon as the
      code is on the PC: the next home ingest log shows `[api_schema] ... status: OK/CHANGED`.
      Cloud email alerts need the image push. After the push and the catch-up rerun, the
      nightly loader log should show `api_schema OK` and no `ERROR: API_DATA_GAP` (those
      fire until the box scores since 2026-10-28 have landed). Runbook: README "When
      nba_api or an endpoint changes".
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

## Deferred decisions on record
- Retrospective `wf_` rows are deliberately unbadged on the site (user decision
  2026-07-03); provenance lives in `model_predictions.model_version`.
- The daily API restart schedule can be DELETED once the July 11 rotation
  passes cleanly with the rotation-aware connector (see
  memory/feedback_rds_secret_rotation) — `aws_scheduler_schedule.api_daily_restart`.
