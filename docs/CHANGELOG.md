# Changelog

*Dated history of what changed and where it's written up. Newest first, one line
per change. Details stay in the linked doc; commit hashes are for `git show`.
TL = `docs/model_tuning_log.md` (search the section title).*

**Maintaining it:** add a line for every change that alters the model, the data, the
public site, or a decision on record. Format: `area — what changed → where it's
documented (commit)`. Areas: **model**, **eval**, **data**, **ops**, **infra**,
**web**, **llm**, **docs**.

## 2026-11

**2026-11-17**
- data — Skipped box scores recovered locally: 3,082 of 3,379 missing (game, table) pairs, NULL-id rows deleted, 9 never-imported 2025-11-21 games imported. 2024-11-17 onward re-shipped to RDS (drop `2026-11-17T034656Z`); 2012-13 and older recoveries stay local (Kai's call). The next weekly retrain sees ~127 more 2024-25 games. `sql/dedupe_importedgamesmemory.sql` removes 791 duplicate status rows and adds the table's first primary key (Kai runs). Open items → `docs/preseason_checklist.md` "Ingest follow-ups (2026-11-17)"

**2026-11-16**
- data — Root cause of the skipped box scores: the importer's re-import pass fetched the game id unpadded (`22400129`, the bigint from `importedgamesmemory`), and for that id the NBA returns no player rows and all-NULL team rows. So no re-import ever recovered a game. Ids are now always zero-padded. The first recovery run recovered 0 of 515 games; the SQL is idempotent and gets re-run → `docs/preseason_checklist.md`
- data — Importer no longer gives up on box scores the NBA posts late: all-NULL rows (unpublished box score, `gameId` NULL) are dropped instead of stored as success; nba_api's parser crash on null blocks is recorded as "not published yet" (warning, not ERROR); "no data" is retried until the game is 10 days old instead of twice. Schema check gains a game-coverage test (games missing from a table, NULL-id rows → `API_DATA_GAP`). Found: 515 games with skipped tables (mostly 2012-13, 2024-25, 2026-27); recovery in `sql/recover_2026_11_missing_boxscores.sql` (Kai runs) → README "When nba_api or an endpoint changes", `docs/preseason_checklist.md`
- docs — `DATABASE_SCHEMA.md` rebuilt (was May 2026; 23 of 51 tables missing, stale counts). Hand-written conventions / relationships / queries on top; table index (where it lives, exact rows, coverage, purpose, referencing code) and columns + indexes generated from local MySQL by `scripts/gen_db_schema_doc.py`. `--check` and a nightly schema-check note flag tables without a description
- data — Raw nba_api response archive: the importer saves every response as received (`data/raw_api/`, `raw_api_archive.py`, local), and `backfill_from_raw.py` replays it offline (`--columns` for a newly added column, `--insert-missing` for failed inserts). The importer's re-import pass no longer re-appends tables that already have rows → README "When nba_api or an endpoint changes"
- data — Daily `GravityLeaders` snapshot (`gravity_snapshot.py`, new table `gravity_leaders_daily`, local only; Kai creates it from `sql/create_gravity_leaders_daily.sql`). The endpoint is season-to-date with no date filter, so history exists only from the day we start saving → README
- data — Schema check now also covers endpoints: installed nba_api endpoints vs baseline (new ones as notes), alerts if an endpoint we import is marked deprecated or removed, GravityLeaders shape, raw-archive inventory; loader prints notes as `NOTE:` (no email). Baseline re-accepted → `docs/api_schema_report.md` §0/§4
- eval — Proposed (not run): E29 defensive-matchup aggregates, E30 unused stored columns, E31/E32 prior-season / in-season gravity (team), P8 gravity in the player model, P9 defender matchups → TL master table + §"Proposed experiments E29-E32, P8-P9"
- data — nba_api schema check: `data_engineering/api_schema_check.py` runs in every home ingest. It compares the API's columns with an accepted baseline (`api_schema_baseline.json`, accepted at 1.12.0) and with MySQL, and checks that the columns the pipeline reads are still filling. Alerts ride in the drop manifest; the S3 loader prints them as `ERROR: API_SCHEMA_CHANGED` / `API_DATA_GAP` (email via the existing ERROR alarm; needs the image push). Column-to-consumer/feature map generated into `docs/api_schema_report.md`; runbook + record of the 1.12.0 changes in README "When nba_api or an endpoint changes". Found: team `speed` has never been filled (always-empty rolling features, not in production). `game_list` inserts get the same column guard
- data — Box-score inserts fixed for nba_api 1.12.0: every V2/V3 frame gained `homeTeamId`/`awayTeamId`, so every box score since the upgrade failed with MySQL 1054 "Unknown column" (game_list itself loaded). The importer now keeps only columns the table already has, with no schema change. DB insert errors are no longer mislabelled "RATE LIMIT ERROR" (the INSERT parameters happened to contain "429") → `data_engineering/main_refactored.py` `_align_to_table`

**2026-11-13**
- data — Home ingest fix (built, Kai runs): nba_api 1.11.3 → 1.12.0 (NBA-side change made every stats.nba.com call time out since 2026-10-27; 1.12.0 works for all ingest endpoints); cp932 log crash that blocked every failed run from shipping anything fixed → `preseason_checklist.md` E28
- data — Official injury reports: daily home ingest now backfills/re-scrapes `historical_injury_report` and ships it (date_window); new `home_ingest_push.py --injuries-only` + `scripts/home_injuries.bat` pre-tip task ships today's report before the 5:45 PM ET run; scraper gains `--replace` / `--force-dates` → `preseason_checklist.md` E28
- model — E28 fix built (not deployed): nightly/interactive/dashboard predictions build inputs with the training pipeline (`feature_engineering.build_serving_features`, games as placeholders; `modeling/serving_features.py`); old live builder deleted. Parity identical on all 573 columns, 6 dates; early 2026-27 replay RF margin SD 1.3 → 6.1. Guard `SERVING_FEATURES_MISSING`; CI serving-invariant gate → TL §E28 Step 2, `preseason_checklist.md` E28
- data — Found: home ingest failing every run since 2026-10-28 (stats.nba.com timeouts), cloud box scores stop 2026-10-27; `historical_injury_report` has no 2026-27 rows (scraper unscheduled) → TL §E28 Step 2, `preseason_checklist.md` E28
- eval — E28 serving audit: live predictions never receive 21 of the model's features (all ELO, last-10 win %, DIFF slot/availability), filled with training medians since E9 (2026-05-20). Same games, same bundle: RF margin SD 8.9 (training features) → 4.0 (live). Explains the 2026-27 margin collapse and head disagreement. Fix not yet built → TL §E28
- eval — E27 win prob from margin, Φ(margin/σ): REJECTED. Backtest: RF passes, XGB/NN fail; live 2026-27 fails every gate because the live margins are degenerate (RF SD 1.1) → TL §E27
- docs — Dated E28 notes on TL E19/E21 (their "live" rows came through the degraded serving path); articles.md #16 rewritten around the serving bug (blocked until fix + 3 weeks)
- web — Home slate table redesigned for readability: one team per row (every number restated from the consensus pick's side, signed), columns cut to Matchup / Models' pick / Proj. margin (3-model average) / Market (same scale, raw line underneath); per-model win % + margin moved to an expandable row; margin-based green/red cell coloring removed (✓/✗ is the only result mark); "split" badge replaced by negative margins. EN + JA copy rewritten → `web/components/PredictionsTable.tsx`

**2026-11-05**
- eval — #11 re-run on the all-walk-forward record: pooled over 3 seasons (3,669 paired games) RF beats XGB and NN on accuracy (+1.4 / +1.6 pts) and MAE (-0.25 / -0.11), CIs clear of zero; RF probabilities are the narrowest and underconfident → `articles.md` #11
- eval — Local 2025-26 walk-forward rebuild done (1,837 rows). Like-for-like 2025-26: RF 0.676 / MAE 11.35, XGB 0.665 / 11.49, NN 0.663 / 11.38 (1,215 paired games); RF leads in all three seasons. Shipped to RDS the same day (12,494 wf_ rows; RDS check matches local); #11 unblocked → TL §E26 "Local backfill 2026-11-05", "Shipped to RDS 2026-11-05"
- ops — Verified: all four bundles (rf/xgb/nn/player_xgb) current through 2026-10-27, sync + freshness OK; player model now sees 2026-27. → TL §E26 "Verified 2026-11-05"

**2026-11-02**
- ops — Found: no cloud retrain since 2026-07-04 reached S3 (task role lacked `s3:PutObject`; push failure was a Warning). Every scheduled run retrained team models in-process on the 567 → 252 feature mismatch; player projections ran on a June-data bundle all season → TL §E26 "Addendum 2026-11-02"
- infra — `s3:PutObject` on the models bucket for the pipeline task role (`infra/ecs.tf`); applied 2026-11-04
- model — Player retrain now includes the current season (`player_dataset.production_seasons()`; was frozen through 2025-26, so the player model never saw 2026-27) → TL §E26 follow-up
- ops — `validate` stage: DB-first window (crashed weekly on the missing CSV) and held-out only (after `data_through_date`) → TL §E26 follow-up
- ops — New alarms: `ARTIFACT_PUSH_FAILED`, `NIGHTLY_RETRAINED`, `MODEL_BUNDLE_STALE`; retrain verifies the S3 copy → README "Model Bundles & Rollback", `preseason_checklist.md` P-2

## 2026-10

**2026-10-30**
- ops — Retrain as one unit: `train` stage → `modeling/retrain_models.py` (per-model isolation, missing library = failure, `ERROR: RETRAIN_FAILED`); `modeling/bundle_sync.py`; nightly `MODEL_BUNDLE_SYNC` alert → TL §E26, README "Model Bundles & Rollback"
- eval — 2025-26 track record found mixed (XGB walk-forward vs RF/NN retrospective rows from a preseason bundle); `walkforward_backfill.py --supersede-non-wf`, `scripts/ship_wf_predictions.py`, `scripts/check_track_record.py`. Decision: all walk-forward. Rebuild + RDS ship pending (Kai) → TL §E26, `preseason_checklist.md` P-2
- eval — Correction: E19-E21 "live" pairs were logged after the games (0 of 178 pre-game) → TL inline notes at E19/E20/E21
- docs — Assessment §2.3 "XGB/NN better on margins" withdrawn (single-window artifact; RF leads on MAE in every like-for-like season) → `model_assessment_2026-07.md` Addendum
- docs — `docs/INDEX.md`, this changelog, root `CLAUDE.md` for LLM-efficient navigation
- docs — P-2 logged as HIGH: common retrain + walk-forward record; #11 blocked on it → `articles.md` P-2, #11 (06da54b, c59f951, 7b5e143)
- web — Articles published: #5 win probability, #6 early season, #8 minutes, #9 player baselines, #10 count stats; real-data figures for #1-#4 + figures rule → `articles.md` (72a4baf, d76093f, 9eeda77, 6659800, 9342401, ab1a878)
- web — Margin-floor builder fix: `predicted_margin` is already home-signed (b216bbb); glued-word fix (abe7414)
- docs — P-1 (player 80/90% ranges) logged as low-priority study → `articles.md` P-1 (e7a43d5)

**2026-10-27**
- web — /articles section, four experiment write-ups, EN + JA → `articles.md` (d53a594, a2e4d3f)
- web — AdSense re-review prep: prerendered content, page guides, sitemap, /contact; Search Console TXT → `ad_monetization_plan.md` (27216fd, cfcc04a, 508b970)

**2026-10-26**
- web — Tonight: ET slate date, results above the fold, "split" badge when a model's win-probability and margin heads disagree (7966d3d). Root cause of early-season disagreement still open → `articles.md` #16
- web — Track record: margin scatter first, pick-vs-result 2x2 (7a79521)

**2026-10-21 / 22**
- data — Season rollover: ingest window was pinned to 2025-26, so the 2026-27 opener never ingested; now rolls on Aug 1. Same commit: Tonight UI and advisor/`advisor.tf` changes (2b3a21e)
- data — Hybrid ingest: cloud polls ESPN finals every 30 min (`data_engineering/espn_score_poller.py`, `infra/schedule.tf`) for grading + site; home still owns `game_list` (5bba9c1); CI update (e399cfe)

## 2026-08

**2026-08-10**
- infra — API perf: PriceClass_200, edge-cache all read routes, Cache-Control, gzip (a118d53)
- infra — Cost-allocation tags; RDS MySQL 8.0 → 8.4 (ebb91c5)

## 2026-07

**2026-07-28** — infra — Fargate tasks propagate Project tags (70a4763)

**2026-07-17 / 22**
- model — Adopt P7b per-submodel player HPs (all heads except BLK) + P4 d2 fatigue columns → TL §P7, §P4 (62514c5, 08ecd3b)
- model — P7 REJECT (mechanical, BLK veto); Phase D quantile prototype = GO signal → TL §P7 (0b51fa2, b7d8c87)
- ops — Ingest schedule retimed around game times (aa1d9fe)
- web — AdSense preparation, translations (01b9fc4, ce1ea41, 272a7cc, 98e9976, 7085803)

**2026-07-16**
- model — **E22 adopted**: top-250 pruned feature set in production (`ENABLE_E22_PRUNED_DEFAULT=True`, keep-list in `core/`) → TL §E22 (473421a, 8106e0b, ccb2b07, 793981f)
- model — E24 Optuna search REJECT (gains don't transfer to held-out W5); E25 team eRAPTOR REJECT → TL §E24, §E25 (2ae29cb, d6cfb24)
- model — P4 KEEP d2 fatigue; P5 REJECT tail isotonic; P6 REJECT Marcel for STL → TL §P4-P6 (01e2343, 8706016, cd341e6)
- eval — Eval-split preprocessing leak fixed in `_prepare_training_data` → README "Feature-level leakage audit" (4cfc823)
- eval — Experiment-loop infra: frozen snapshot, shared harness, A/B runners, permutation importance (5bcf638, 6ab98cd)
- web — Players deep-dive "clearing a line" panel + CDF (ab93e66, 1aab7e3); dashboard torch import fix (773840f)

**2026-07-13 / 15**
- llm — Fantasy advisor on Bedrock (Sonnet 4.6 legacy path), abuse safeguards, season-wide scope → README Part VI, `advisor_scope_plan.md` (2057df1, 875b0c7, 7069ecd, b752031, ffa49cf)
- docs — README restructured into parts with Key Documentation index (2a18255, 31bac76)

**2026-07-09 / 11**
- model — P1 player projections (two-stage XGB beats Marcel 10/11); P2 playoffs + 4th season; P3 eRAPTOR rejected → TL §P1-P3, `p2_player_validation_report.md` (b37171d, a230a98)
- web — Nightly player predictions, /players, /players/explore (735f1b6, 979325c, 0f3f89c)

**2026-07-02 / 08**
- model — E19 season-end audit (RF ~97% home picks = stale calibrator; XGB never ran in-season) → TL §E19
- model — E20/E21: picks from raw probability for all models; RF displays raw, XGB keeps its calibrator; degeneracy tripwire → TL §E20, §E21 (474ee2b, a7d86f8, 62abf79)
- eval — Walk-forward `wf_` backfill for 2023-24 → 2025-26; S3 `version_window` loader; 3-season API window → TL §E26 for the 2025-26 gap it left (2cf318a)
- ops — Weekly cloud retrain (Mon), live drift monitor, injury report on site (7614d68); nightly grading step, xgb grading fix (d8985ee)
- data — Residential ingest handoff: home fetch → S3 → cloud loader; freshness alarm (92976d4, 6936611)
- data — Feature-set lineage (`feature_set_version` in registry) (643c288); weekly features build covers full history (23374c1)
- infra — Rotation-aware API DB auth → `troubleshooting_lab.md` (40114ce)
- web — Track record rebuilt with market benchmark, dedup per game+model, ATS record (3b978e0, e0f7322, 85c79f0)

## 2026-06

- infra — AWS (Terraform): VPC, RDS, ECS, CloudFront; CloudWatch alarms, EventBridge, budgets → `aws_deployment_plan.md`, `terraform_lab.md` (4ce1d2f, 2d54158)
- web — Public site + API CI/CD; Explore page (66b2b69, 10b6e49, 297e1b6)
- ops — Week 1 cloud prep: features → DB, batch predictor, artifact store, containers (2257b97, 39d270c)

## 2026-05

- data — ETL: games in progress during a fetch were skipped on later runs (365d77f, 05-29)
- eval — E18 calibration audit: logging uses the classifier pick, raw prob column, backfill leakage guard → TL §E18 (05-26)
- model — E5-E17: Elo kept (E9), opponent-adjusted (E10) and lineup (E11) features dropped after the E12 noise-aware ablation; isotonic calibration (E13), conformal intervals (E14), cross-context (E15), playoff ceiling (E16), series features dropped (E17) → TL, `e3_ablation_report.md`, `e13`-`e15` reports (e5c9fda, 025bf97, 05-19/20)
- model — E1 RF regularized (train-test gap 24pp → <5pp), E2 walk-forward, E3 XGBoost, E7 pre-game injury reports (availability leak fixed), E8 slot-feature bug → TL (a26ff05, 05-18/19)

## 2025-11 / 12

- model — Initial RF/NN models; player impact features moved into training (66d6623, 2f0cf10); injury logic (89f4733, 01afcb8)
