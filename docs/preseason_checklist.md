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

## Deferred decisions on record
- Retrospective `wf_` rows are deliberately unbadged on the site (user decision
  2026-07-03); provenance lives in `model_predictions.model_version`.
- The daily API restart schedule can be DELETED once the July 11 rotation
  passes cleanly with the rotation-aware connector (see
  memory/feedback_rds_secret_rotation) — `aws_scheduler_schedule.api_daily_restart`.
