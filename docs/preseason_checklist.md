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

## Deferred decisions on record
- Retrospective `wf_` rows are deliberately unbadged on the site (user decision
  2026-07-03); provenance lives in `model_predictions.model_version`.
- The daily API restart schedule can be DELETED once the July 11 rotation
  passes cleanly with the rotation-aware connector (see
  memory/feedback_rds_secret_rotation) — `aws_scheduler_schedule.api_daily_restart`.
