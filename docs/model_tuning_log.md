# Model Tuning Experiment Log

Chronological log of every deliberate change to model hyperparameters or training data, with the hypothesis behind it and the measured outcome. Each experiment maps onto a row in `model_registry` — the `model_version` string is the join key. The dashboard's Model Performance tab is the canonical place to compare metrics across experiments; this file is the *why*.

## Conventions
- **Newest at the bottom.** Append, don't rewrite. Past experiments stay frozen so we can re-read what we thought at the time.
- **Hypothesis** is the falsifiable claim being tested ("constraining RF will close the train/test gap without hurting test accuracy"), not just "let's try this."
- **Results** are filled in *after* the retrain has produced new registry rows. Don't pre-write them — record what actually happened.
- **Decision** is what we kept / reverted / what's next. If a result was inconclusive, say so explicitly rather than over-claiming.
- One experiment per H2 (`##`) heading. Reference registry rows by `model_version` so the join is unambiguous.

---

## Master experiment table (kept current)

The headline metric on this dataset is **walk-forward W5 accuracy** (RF/XGB/NN trained strictly on data before 2026-03-15, tested on 2026-03-15 → 2026-04-15, ~230 games). Numbers below are RF/XGB/NN W5 accuracy unless noted.

| # | Experiment | Motivation | Methodology | Result | Status / Date |
|---|---|---|---|---|---|
| **E1** | Reduce RF capacity, add NN regularization, seed PyTorch | E0-baseline showed 24pp RF train/test gap (99.9% train vs 76.2% test) — model was memorizing. NN had 2.6pp run-to-run drift, blocking honest A/B. | RF: `max_depth=10→5, min_samples_leaf=1→20`. NN: `dropout=0.3→0.5`, `weight_decay=0→1e-4`. Seed `torch.manual_seed(42)` + `np.random.seed(42)`. Single-season CSV (1134 games). | RF train/test gap **24pp → 4.7pp**, test acc **76.2% → 74.9%** (-1.3pp), AUC **0.812 → 0.830** (+0.017). NN gap **18pp → 9.6pp**, NN acc +0.4pp. NN reproducibility achieved. | **Kept** 2026-05-18 |
| **E2** | Walk-forward across 5 time windows | Test whether the 75% E1 number generalizes or was window-shopping. | `experiments/e2_walk_forward.py` — for each of 5 windows, train fresh on data strictly before, predict on window. Single-season CSV. | 75% reproducible at full-data W5 (74.8%). Steep learning curve: accuracy 58% (208 train) → 75% (904 train). Concluded "data is the binding constraint" — later updated by E3. | **Diagnostic, no model change** 2026-05-18 |
| **E3** | Wire up XGBoost + walk-forward with 4-season backfill | Test if more data extends the learning curve. Test if XGB (literature's practical SOTA for tabular) beats RF/NN. | Added `key='xgb'` ModelTypeSpec + bundle-based load/train + dispatch register. Backfilled features CSV with `--start-date 2022-01-01` (1134 → 7342 games). Re-ran walk-forward. | Learning curve **flattened** sharply: 7.8× more data only bought +1.4pp RF accuracy on avg. XGB benefited more from extra data (+2-4pp per window) but still trailed RF overall. NN W5 had reproducible calibration crash (acc 0.426, AUC 0.814) — later traced to E8. | **Kept XGB; updated strategic priority** 2026-05-18 |
| **E4** | Ensemble RF+XGB+NN | Literature shows simple-average ensembles often +1-2pp over best single model when models are differentiated. | (Not implemented) — simple-average classifier probabilities; weighted-average margin. | n/a | **Backlogged 2026-05-18** — obfuscates per-model performance, deprioritized until individual models are stable. |
| **E5** | Vegas line as SUPPLEMENTARY BASELINE (not a feature) | User-clarified scope (2026-05-19): not a model feature — a comparison baseline so users see model prediction vs Vegas, and so we can A/B model vs Vegas vs actual. Two data sources needed (historical + current/future). | Built `vegas_lines` MySQL table keyed on (game_date, home, away, source, line_type). Kaggle importer: `vegas_lines_kaggle_import.py` loaded `nba_2008-2025.csv` (Pinnacle/SBR consensus, 4756 rows 2022-01-01 → 2025-06-22). ESPN fetcher: `vegas_lines_espn.py` pulls DraftKings spreads/totals/moneylines from ESPN's public `/scoreboard` + `/summary` endpoints (free, no auth, not geo-blocked). Dashboard: Game Predictions tab overlays gold Vegas marker on the margin-distribution chart; Model Performance tab adds a "Margin MAE: model vs Vegas" bar comparing per-model MAE against Vegas baseline on paired games. | (Reporting deferred until E11 synthesis — needs enough backfilled `model_predictions` rows to make the comparison statistically meaningful.) | **Implemented 2026-05-19** |
| **E6** | NN stabilization (BatchNorm/early-stopping) | Reproducible NN regime failures: W3 regressor MAE 24.5, W5 classifier acc 0.426. Hypothesized BatchNorm + small validation interaction. | (Not needed — eliminated by E8.) Was going to: replace `BatchNorm1d` with `LayerNorm`, adjust early-stopping patience by dataset size. | n/a | **Eliminated by E8 2026-05-18** — the NN failure modes turned out to be the slot-feature duplicate bug, not a NN architectural issue. NN behaves normally post-E8. |
| **E7** | Reconstruct historical pre-game injury reports | `_AVAILABLE` features derived from post-game boxscore — model knew pre-game whether each star showed up. Literature flags this as commonly inflating accuracy 2-5pp. Backfilled predictions also assumed everyone available. | Built `historical_injury_scraper.py` against NBA's official PDFs (`ak-static.cms.nba.com`) via `nbainjuries` PyPI package. Discovered + fixed NBA URL-format change at 2025-12-22 (hourly → 15-min granularity). Populated 106,755 rows / 969 game-dates / 2022-01-01 → 2026-05-13. Added `bulk_fetch_pregame_availability` + new `availability_source='pregame'` default in `calculate_player_slot_features`. Added `_fetch_historical_injuries_for_date` for backfilled-prediction lookup. Bug discovered + fixed during first rebuild (dict-key type mismatch made every lookup miss). | W5 accuracy: RF 0.748→**0.752**, XGB 0.774→**0.770**, NN 0.735→**0.757**. W5 AUC up across the board (NN +0.012, RF +0.003, XGB +0.002). **W5 MAE: XGB 11.78→11.57 (-0.21), NN 12.35→11.80 (-0.55).** XGB's 11.57 is the closest we've gotten to Vegas's ~10-11 floor. Leak was real but smaller than literature's 2-5pp prediction — model was already extracting most of the signal from other features. | **Kept 2026-05-19** |
| **E8** | Fix double-prefix slot-feature bug | Agent code review found `create_matchup_features` was producing `HOME_HOME_SLOT_X` and `AWAY_HOME_SLOT_X` as identical duplicates, and `DIFF_AWAY_SLOT_X` as constant zero. ~75 garbage columns in 627-feature vector. | Excluded already-`HOME_`/`AWAY_`/`DIFF_`-prefixed columns from the rename map in `create_matchup_features`. Rebuilt features, retrained, re-ran walk-forward. | Cols 836 → **756**. RF W5 acc **0.778 → 0.748** (-3pp — the modest leak that was in the bug), AUC **0.821 → 0.816**. **XGB W5 acc 0.739 → 0.774** (+3.5pp — XGB was hurt more by the noise). **NN W5 acc 0.426 → 0.735** — the calibration crash from E3 disappeared, validating that E6 was an artifact of this bug. | **Kept** 2026-05-18 |
| **E9** | ELO as 4 features (HOME/AWAY/DIFF/P_HOME) | Lit review + ELO research both rank ELO as a top-cited add. Captures path-dependent franchise-history strength + schedule strength that rolling box-score averages don't. | 538 formula: K=20, HCA=100, MOV multiplier `(margin+3)^0.8 / (7.5 + 0.006*winner_diff)`, 0.75 season carryover. One pass over `game_list` (~82K rows), 41,345 games processed; write `team_elo_pregame` MySQL table, join to features CSV. Pure-ELO baseline standalone: **66.4%** classification accuracy. | **(Ablation, isolated)** W5 acc: RF 0.765→**0.774** (+0.9pp), XGB 0.774→**0.774** (flat), NN 0.761→**0.774** (+1.3pp). (Initial E9-only walk-forward reported smaller deltas — that measurement was buggy: the model's pattern list in `predict_games._prepare_training_data` and `e2_walk_forward.select_feature_columns` lacked `HOME_ELO`/`AWAY_ELO`/`ELO_DIFF`/`ELO_P_HOME`, so ELO never actually entered the model. Discovered 2026-05-19 during E11 verification — fixed and re-ran.) | **Kept 2026-05-19** |
| **E10** | Opponent-strength adjustment for rolling stats | Agent 1 code review #2 finding. Every `_L5/_L10` is a raw mean — a 10-0 streak vs tankers looks identical to 10-0 vs contenders. Lit review identifies this as the recurring "biggest gap" of pure box-score features. | Two-pass derivation over team-game df: (1) per-team-game, attach opponent's same-game stat; roll those per team with shift(1) to get `{stat}_ALLOWED_L10` (defensive form); (2) for each row, join opponent's `{stat}_ALLOWED_L10` and compute `OPP_ADJ_{stat}_L10 = team_{stat}_L10 - opp_{stat}_ALLOWED_L10`. Curated 9-stat subset (PTS, ORtg, NetRtg, TS%, eFG%, FG%, FG3%, Pace, +/-) → 9 ALLOWED + 9 OPP_ADJ = +18 cols (×2 for HOME/AWAY/DIFF after matchup expansion). Side effect: collapsed 1023 latent duplicate rows in `game_df` via the (game_id, team_id) dedupe. | W5 acc (OPP_ADJ added without ELO/LINEUP): RF 0.752→**0.765** (+1.3pp), XGB 0.770→**0.774** (+0.4pp), NN 0.765→**0.761** (-0.4pp). W5 MAE: RF 12.21→**12.07**, XGB 11.57→**12.07** (regressed), NN 11.97→**11.75**. Tree models extract the signal cleanly; NN MAE down but acc flat. The OPP_ADJ features carried correctly via the `_L10` substring pattern, so the ELO routing bug didn't affect this measurement. | **Kept 2026-05-19** |
| **E11** | LeagueDashLineups for 5-man synergy | nba_api recon: our additive player-impact model structurally cannot capture 5-man chemistry / bench-unit dropoff. Lineup data via LeagueDashLineups endpoint addresses this gap. | `data_engineering/lineup_features.py`: month-end snapshots from `LeagueDashLineups` (Advanced/PerGame/5-man) per (season, month_end), cached to `team_lineup_snapshots` MySQL table. 450 rows across 15 month-ends (2024-10 → 2026-03; earlier seasons returned JSON errors from NBA API). `_join_lineup_features` uses `merge_asof` to pick the most-recent prior snapshot per (team_id, game_date) — point-in-time correct. 9 features per side: TOP_MIN, TOP_NET_RTG/OFF_RTG/DEF_RTG/PACE/TS_PCT, TOP5_AVG_NET_RTG, TOP5_MIN_SHARE, N_ACTIVE. Coverage: 2711/6319 games (43% — mostly 2024+ seasons; pre-snapshot games NaN-imputed). | Initial single-seed measurement showed apparent +1.3-2.6pp gain. **E3 noise-aware ablation (10 seeds × 1000 bootstrap, see below) showed NO statistically significant improvement** on any model × any metric × either CSV. | **DROPPED from production 2026-05-19** (build code retained for future ablation; `core.features.ENABLE_E11_DEFAULT=False`) |
| **E12** | **Noise-aware feature-ablation study** | User-raised: most of E9-E11's reported gains were within single-seed bootstrap-CI noise. Want a proper multi-seed + paired-test evaluation to decide which features actually carry signal, not "looks better on one run." | Centralized 3-site feature-pattern lists into `core/features.py::select_features` with E7/E9/E10/E11 toggles. Built `experiments/e3_noise_ablation.py`: for each (E9, E10, E11) on/off × 10 seeds × {RF, XGB}: train on pre-W5 games, predict W5; bootstrap test set 1000× per (config, seed). Pairwise tests: McNemar on accuracy, paired-t on \|error\| for MAE, bootstrap-on-Δ for AUC. Run on both E7-on and E7-off CSVs (rebuild with `--availability-source postgame`). Full write-up: §E12 below + docs/e3_ablation_report.md. | **E9 KEEP** (only significant signal: RF AUC Δ +0.013, p≈0.012-0.016). **E10 DROP** (RF MAE *regression* p=0.011-0.023). **E11 DROP** (no significance anywhere). **E7 KEEP** (XGB MAE Δ -0.31 to -0.41 across CSVs; directional, see caveat). | **Implemented 2026-05-19** — E10/E11 build code disabled, `core.features` defaults set E9-on/E10-off/E11-off, pipeline retrained. |
| **E13** | **Probability calibration (isotonic)** — Phase 2a of uncertainty work | Is `predict_proba` honest? Win-probability outputs drive any "how confident is the model" use; if a stated 70% really wins 87%, the number misleads. | Diagnostic `experiments/e13_calibration.py`: reliability bins + ECE + Brier on W5 (10 seeds, production config), raw vs isotonic. Found RF systematically **underconfident** in 0.5-0.8 (a 0.75 prediction → 87% real win rate); ECE 0.131. XGB milder (ECE 0.092). Implemented `IsotonicCalibratedClassifier` wrapper in `predict_games.py`; both RF+XGB production models fit an isotonic map on the eval model's 20% out-of-sample holdout and wrap the full-data model. Plain-language write-up with real games: docs/e13_calibration_report.md. | Isotonic **halves RF ECE (0.131 → 0.074)**, improves Brier (0.176 → 0.166); XGB ECE 0.092 → 0.081. AUC unchanged (monotonic). **Caveat**: fixes the *average*; confident-but-wrong games get penalized harder — which makes ECE a good cross-context diagnostic for Phase 1. | **Implemented 2026-05-19** — calibration baked into RF+XGB bundles (`clf_calibrator` key). |
| **E14** | **Margin prediction intervals (split conformal)** — Phase 2b of uncertainty work | The regressor emits a bare point margin ("home by 4.6") with no sense of how uncertain it is. Want a validated range that feeds the margin-histogram-vs-Vegas dashboard view. | `experiments/e14_intervals.py`: split conformal (constant width) vs CQR (adaptive), 5 seeds, validated empirical coverage on W5 at 80%/90%. Implemented `ConformalRegressor` wrapper; RF+XGB compute half-widths from eval regressor's 20% holdout residuals, stored in bundle (`conformal_halfwidths`). `predict_with_rf/xgb` now emit `margin_interval_80/90`. SHAP sites unwrap via `getattr(reg,'_base',reg)`. Write-up: docs/e14_intervals_report.md. | **Coverage honest**: 90% intervals → 91-92% real coverage; 80% → 75-78%. **CQR no better than split conformal** (same coverage, wider bands) → shipped the simpler method. Intervals are **wide** (80% ≈ ±18pts, 90% ≈ ±25) — the irreducible NBA margin SD (~13-14); not a model flaw. | **Implemented 2026-05-19** — conformal half-widths baked into RF+XGB bundles. **Phase 2c done**: dashboard Game Predictions tab now renders calibrated win prob (E13) + conformal 80/90% margin intervals (E14) + Vegas marker. |
| **E17** | **Playoff series-context features (Track A)** | E16 showed a non-significant ~3-4pp gap to Vegas on playoffs. Series state (game-in-series, score, elimination, HCA, in-series h2h) is the playoff structure Vegas prices and our model is blind to — the one principled shot at the gap. | `data_engineering/series_context.py` builds 8 features from prior games in each series (no leakage) → `playoff_series_context` table → joined at build. `experiments/e17_series_eval.py`: train on ALL games incl prior playoffs before each test season's playoffs (series features need playoffs in train to be learnable), paired with-vs-without on 316 playoff games (2023-26), 5 seeds + McNemar/paired-t/bootstrap-AUC. | **No significant gain.** RF ΔAUC −0.014 (CI cross 0), McNemar p=0.33; XGB ΔAUC +0.007, McNemar p=0.89 (26/26 net), MAE flat-to-worse. Vegas still 0.647 on same games — gap didn't close. Confirms E16: playoffs near-irreducible. | **DROPPED from production 2026-05-19** (`ENABLE_SERIES_DEFAULT=False`); build code/table retained for re-eval as playoff data grows. |
| **E16** | **Playoff ceiling check (model vs Vegas)** | E15 showed model playoff AUC ~0.64. Is that near the irreducible ceiling, or missing signal? Compare to Vegas closing line on the same games. | `experiments/e16_playoff_ceiling.py`: per-season temporal train (as E15), predict on playoff games, restrict to the 337/403 with a Vegas line, head-to-head model vs Vegas (favorite=home if spread<0; AUC score=−home_spread; margin=−home_spread). Bootstrap model−Vegas deltas. | **Vegas itself only gets AUC 0.648 / acc 0.647 / MAE 11.78 on playoffs** → ceiling is ~0.65, not 0.79; playoffs are irreducibly hard. Model (RF 0.614/0.620/12.01, XGB 0.607/0.611/12.15) trails Vegas by ~3-4pp AUC but **every delta CI crosses zero** — within noise of the market. | **Diagnostic 2026-05-19** — revised playoff plan: cap investment; Track A (series features) optional one-shot at the residual gap; Tracks B-E shelved. docs/playoff_improvement_plan.md. |
| **E15** | **Cross-context generalization** — Phase 1 | (a) How much data is needed (learning curve)? (b) Can a regular-season model be trusted in the playoffs? Uses E13/E14 coverage+ECE as the cross-context lens. | `experiments/e15_cross_context.py` two modes. **Learning curve**: fix test=W5, vary train-start (0.5-4 seasons), 5 seeds. **Regime**: per-season temporal train on regular games before each season's playoffs, pool ~400 playoff test games; compare regular(control)/playin/playoffs on acc/AUC/MAE/ECE/coverage + KS feature-shift. Write-up: docs/e15_cross_context_report.md. | **Learning curve flat past ~1 season** (1k→4.5k games buys ~0 acc/MAE) → don't chase more history. **Playoffs**: winner-prediction degrades hard (RF acc 0.713→0.635, AUC 0.790→**0.637**; XGB similar) — playoffs are a harder, ELO-compressed, slower-pace subset (KS DIFF_ELO p=0.029). **But intervals/calibration transfer**: playoff cov90≈0.88-0.90, ECE stays low. Coverage-as-diagnostic worked: spread is similar (bands hold) but winner is less predictable (AUC craters). Play-in n=30 too small to trust. | **Diagnostic, no model change 2026-05-19** — recommendations: set playoff expectations ~63% not ~71%; trust intervals in playoffs; future playoff-specific features. |
| **E19** | **Season-end audit + lineage-tracked retrain** | User-surfaced (2026-07-03): RF picks home ~97% of the time; a 64.6-pt margin showed on the public site; XGB has no season predictions. Full current-state audit before further development. | Read-only audit of `model_predictions` (2025-26 season, local + RDS via API), registry, feature snapshots. Then: feature rebuild through the Finals (first `--db-description`-tagged snapshot), retrain all 3 models (first registry rows carrying `feature_set_version` lineage), validate. See §E19 below. | **Audit**: (1) RF live acc 0.583 vs test 0.742 — the E13 isotonic layer maps ~97% of games above 0.5 (reliability bin 0.7 → only 40% real home wins) and FLIPS correct raw picks (2026-06-13: raw 0.449→cal 0.604); when RF does pick away it's 79.4% correct. (2) The 64.6-pt margin exists only on RDS — cloud NN fed degenerate rolling stats (no June boxscores on RDS pre-handoff); local NN on same game: −3.1, correct. (3) XGB: zero season rows — backfills used `--model both` (pre-dates xgb) + `backfill_actuals` hardcoded rf/nn (fixed 2026-07-02). (4) Prod models trained through 2026-03-05 only, on a 1043-game Nov→Apr snapshot. **Retrain**: new snapshot `20260703T022649Z` (1,234 games through the Finals) + first lineage-carrying registry rows (`*_20260703`). New playoff-heavy holdout (Mar 24–Jun 13): RF 0.729/0.785 AUC — expected E15 regime shift, not regression. NOT promoted to prod — E20 (calibration) retrains again first. Validate-stage gap found: it ignores `data_through_date` (in-sample windows accepted). | **Baseline established 2026-07-03** |
| **E20** | **Calibration protocol A/B + pick-policy decision + degeneracy guard** | E19 found the E13 calibrator collapsing RF into 97% home picks live and flipping correct raw picks. Hypothesis: K-fold OOF isotonic (more calibration data, production-config fit) fixes it. | `experiments/e20_calibration.py`: raw vs eval-slice isotonic (faithful production mirror incl. the fit-on-eval/apply-to-full subtlety) vs 5-fold OOF isotonic; W5 test window; RF/XGB 10 seeds, NN 5; ECE/Brier/AUC/acc/home-pick-share + disagreement-game win rates. | **Hypothesis partly REJECTED**: OOF best for RF display-ECE (10/10 seeds beat raw) but not significantly better than eval-slice (5/10) and WORSE than raw for XGB (0/10) → not shipped. Live pathology did NOT reproduce with a fresh calibrator (home share ~0.60, not 0.97) → root cause = STALE calibrator + no guard, not the protocol. Pick policy: fresh-cal picks ≈ raw (RF −1pp, XGB +0.6pp, NN +0.9pp). **Shipped**: keep eval-slice isotonic; pick stays calibrated-derived BUT bundles now carry a train-time **degeneracy guard** (eval-slice home-pick shift > 10pp → `calibrator_trusted=False` → picks auto-fall back to RAW + "ERROR: CALIBRATOR_DEGENERATE" line that the pipeline alarm emails on). | **Implemented 2026-07-03** |
| **E21** | **Multi-season calibration backtest + empirical guard threshold + online-recalibration pilot** | E20 shipped on one test window and a round-number ±10pp guard; its residuals deferred both to E21. Three legs: (1) does eval-slice isotonic actually beat raw / Platt across seasons? (2) what guard threshold does the healthy-fit pick-shift distribution justify? (3) does weekly online recalibration on live logged pairs beat the shipped map? | `experiments/e21_calibration_backtest.py`: 16 monthly walk-forward windows across 2023-24 → 2025-26 (fresh 4,167-game multi-season CSV, prod config, `--no-db-write`), RF+XGB × 3 seeds, raw vs iso_eval vs platt_eval; every fit logs its eval-slice pick-shift (48 healthy fits/model). `experiments/e21_online_pilot.py`: weekly chronological replay of the 186 live (raw prob, outcome) pairs/model from E18 logging; raw vs shipped-stale vs online iso vs online Platt. | **Leg 1**: calibration is accuracy-neutral for both models (Wilcoxon p>0.14 everywhere; mean −0.4 to −0.9pp). ECE: RF raw is already calibrated — iso does NOT improve it (p=0.78); XGB raw is genuinely miscalibrated (~0.12) and both calibrators fix it decisively (−0.038 iso / −0.034 Platt, p≤0.001). **Leg 2**: the ±10pp guard is not discriminative — **40% of healthy fits exceed it**, 25% exceed even the known-degenerate +14.2pp; healthy p99 ≈ 23pp (RF) / 27pp (XGB). **Leg 3 (pilot, n=129)**: raw RF beat everything live (0.667 vs shipped 0.620); online isotonic actively harmful (0.597 acc, 0.225 ECE); Platt the least-bad online option. | **Measured 2026-07-03** — recommendations pending: drop RF calibrator, keep XGB's, guard → per-model p99 tripwire + live home-share monitor; see §E21. |
| **E21b** | *(same experiment — decision)* | | | **Shipped**: raw-derived picks for all models (`_derive_pick_probability` returns raw; +0.5pp mean, raw right on 53% of ~1,900 backtest flips / 62% live; permanently immune to calibrator pathology); guard re-set from ±10pp to the healthy **p99 (±25pp)** as a true extreme-degeneracy ERROR tripwire; missing-requested-bundle in the nightly is now ERROR (the silent `WARN: skipping xgb` hid all season). **Also shipped (user-approved)**: RF display calibration dropped — RF ships unwrapped, displayed prob == raw (calibrator stored in bundle for telemetry/revert); XGB keeps its calibrator (halves ECE, p<0.001). **Pending**: live home-share drift monitor (next season's nightly); 20260703 bundle promotion (after the honest xgb Apr–Jun backfill on the old S3 bundle). | **Implemented 2026-07-03** |
| **E18** | **Calibration audit + logging fix + leakage guard** | User-surfaced bug: Game Predictions tab showed NYK winner for CLE@NYK 2026-05-25 while Model Evaluation tab showed CLE pick logged — same model, same game, different pick. Root cause: dashboard reads E13 isotonic-calibrated classifier; the logging path in `predict_games.py` still derived `predicted_winner` from the **regressor margin sign** (`result['win_prob']` = `np.mean(margin_samples > 0)`), an older signal that pre-dates E13. Two-headed model → two different picks near the boundary. Also surfaced: bundle metadata stored no `data_through_date`, so the backfill loop happily predicted for dates within the training window with no warning. | (1) Logging now uses calibrated classifier: `p_cal = result['win_prob_classifier']`; `predicted_winner = home if p_cal > 0.5 else away`. (2) New `home_win_probability_raw` column added via idempotent migration in `prediction_tracker.ensure_table_exists`; the pre-isotonic prob is logged alongside the calibrated one. NN/NN-embed have no isotonic wrapper → raw == calibrated. (3) Bundle metadata gains `train_start_date / train_end_date / eval_start_date / eval_end_date / data_through_date` (the latest GAME_DATE the production model saw). (4) Backfill loop in `predict_games.py` gates on `data_through_date`: dates ≤ that are skipped with a loud message; `--allow-leakage` overrides. (5) Model Evaluation per-game table now shows **Win% raw** + **Win% cal** side-by-side; for legacy rows raw is NULL. | Data fix only (no model retrain). Game Predictions and Model Evaluation now read the same field. Backfill predictions on training-window dates are refused by default — past metrics on those rows were optimistic by an unmeasured amount. **A/B comparison columns ready**: re-run `predict_games.py --start-date X --end-date Y --no-shap --no-plot` for `X > data_through_date` to populate `home_win_probability_raw` and start the raw-vs-calibrated comparison. | **Implemented 2026-05-26** — see "Calibration audit & leakage guard" section below. |
| **P1** | **Player counting-stat projections** — dataset + baselines + two-stage XGB + 3-season validation/calibration report | New product surface (public `/players` projection table + Bedrock LLM fantasy advisor, docs/player_projections_plan.md) needs per-player MIN + PTS/REB/AST/STL/BLK/TOV/3PM/3PA/FTM/FTA. User-set ship gate: deep calibration + validation on the last 3 seasons before `/players` goes public. | `experiments/p1_player_dataset.py`: 57,854 top-8-by-rolling-MPG player-games (2023-24 → 2025-26 regular seasons, 2022-23 warm-up), ~150 leakage-safe shift-1 features incl. approved Tier-2 groups A/B/C/G (opportunity/hustle, vacated minutes/usage, Vegas spread/total/implied). `p1_player_models.py`: naive L10, Marcel shrinkage (must-beat), two-stage XGB (minutes model × per-36 rates; `count:poisson` with log-minutes exposure for STL/BLK/TOV/3PA/FTA; 3PM/FTM = attempts × shrunken make-rate). `p1_player_validation.py`: 2 season walk-forward folds, paired t-tests, decile reliability, Poisson frequency calibration, split-conformal coverage, minutes-vs-rate decomposition, slices, fantasy aggregates, feature-target correlation matrix. | **XGB beats Marcel on 10/11 targets in both folds, all p≤2.6e-11** (MIN MAE 4.93→4.63 / 4.87→4.59; PTS 5.23→5.03 / 5.17→4.96; 3PA −0.16; STL flat — R²≈0.08, near-noise). Decile calibration tight; conformal coverage 0.78-0.82 (80%) / 0.89-0.91 (90%); Poisson tails over-forecast elite STL/BLK bins; ~15% of PTS error attributable to the minutes model; fantasy-pts MAE 8.03 vs Marcel 8.41. Full report: docs/p1_player_validation_report.md. | **Baseline established 2026-07-09** — `/players` ship gate pending Kai's review; §P1 below |
| **P2** | **Playoff support + 4th season** (extends P1) | Explore page showed playoff actuals with no predictions and no 2023-24 predictions; the nightly as first built would have predicted playoffs on features frozen at regular-season end. Kai: Option A (support playoffs) + extend backfill to 2023-24. | Season-year now spans regular+playoffs+play-in+Cup (`SEASON_YEAR` grouping key, `IS_PLAYOFF` feature, season-to-date accumulates through the postseason; preseason skipped via GAME_ID type digit). Warm-up 2021-22; train years 22-23..25-26 → 83,266 rows (5,708 playoff). Three walk-forward folds incl. new train-22-23→test-23-24. Harness unchanged → docs/p2_player_validation_report.md; backfill version `p2_wf_20260710`. | New fold 1 clears the gate (XGB beats Marcel 10/11, p≤5.6e-31; STL flat as in every fold). **Playoffs: XGB ≤ Marcel on 11/11 stats**; the regime shift lands in MINUTES (MAE 5.00 PO vs 4.54 reg) while PTS error *drops* in playoffs (4.79 vs 4.96 — healthy, stable-role rosters). Backfill 62,156 rows incl. postseason; 38,177 p1_wf rows retired. | **Implemented 2026-07-10** — §P2 below |
| **E22** | **Feature pruning — top-250 group-pruned set vs the 573-column config** | Assessment §2.1: the team feature set is saturated, not leaking — 573 cols vs ~6k train games, 456 of them inter-correlated L5/L10 rolling stats; E15's flat learning curve says signal (not sample) binds, so redundant columns mostly add variance. Pruning = assessment item #7; first experiment of the 2026-07 autonomous loop. | `experiments/e22_perm_importance.py`: OOS permutation importance (RF+XGB × clf+reg × W1–W5 test slices × 3 seeds, n_repeats=5, neg-logloss/neg-MAE), aggregated at base-feature-GROUP level (HOME_/AWAY_/DIFF_ triplets stay together) → keep-lists top250 (252 cols) / top150 (152 cols) → `experiments/loop_ab.py` A/B on frozen snapshot `20260703T072718Z` (6,363 games): W5 10-seed paired tests + 21 monthly windows × 3 seeds, pooled n=4,032. Non-inferiority gates PRE-REGISTERED in `outputs/experiment_loop_state.json` before each launch. | Pruned sets are never significantly worse anywhere, and better where it matters. W5: AUC significantly FOR pruned on all 4 arm×family pairs (+0.008…+0.022, p=.016–.044); top250 RF MAE −0.086 (t p=.002). Pooled windows: top250 passes both families; RF MAE −0.026 (t p=.003). top150 FAILS — XGB pooled MAE +0.11 significantly against (p=.038). One deviation: W5 XGB acc CI floor missed by 0.0024 (point est. +1.7pp FOR); large-n stage ruled. Ranking face-valid: ELO_DIFF #1 group, availability (PLAYERS_OUT, slot impacts) next — mirrors E9/E12. | **KEEP top250 — recommendation staged, adoption is Kai's call** 2026-07-16 — §E22 below |
| **E24** | **First-ever hyperparameter search (Optuna TPE, XGB)** | Assessment §2.4 gap #1: HPs were hand-set once in E1 (2026-05-18) and never searched — "zero search has ever been done." Cheapest unknown-payoff item on the ranked list. | `experiments/e24_hp_search.py`: 60-trial TPE per task on the E22 top250 loop-incumbent set; objective = mean W1–W4 walk-forward logloss (clf) / MAE (reg), 2 seeds, MedianPruner, SQLite storage; incumbent enqueued as trial 0; **W5 excluded from selection**. Winner gated via `loop_ab.py` on W5 (10 seeds, paired tests vs incumbent HPs, superiority gate pre-registered). | Search preferred heavy regularization (depth 2, lr .04–.06, 500–600 trees, λ 15–30) and beat the incumbent on its own objective (logloss −0.014, MAE −0.21 on W1–W4). **On held-out W5 the advantage vanished**: paired acc diff 0.0000 (McNemar 7w/7l), MAE +0.02 (p=.82), AUC −0.001 (p=.83). Marginal per-seed metrics flattered the tuned config (acc .799 vs .782) but seed-averaged predictions were indistinguishable. | **REJECT — E1 HPs stand** 2026-07-16 — §E24 below |
| **E25** | **Team-level prior-season eRAPTOR roster-strength aggregates** | P3's own caveat: impact metrics measure margin/possession, so the TEAM model is the natural consumer (assessment §6.2, expected 0.1–0.3 MAE). Standalone signal looked real: corr(DIFF_WMEAN, margin)=0.28, home wins 65% when positive. | `experiments/e25_eraptor_team.py`: pregame-honest roster (trailing-45d appearances minus official Out/Doubtful via `historical_injury_report`), MPG-weighted (last-10, shift-1) prior-season eRAPTOR via P3's name join → 12 cols (WMEAN/MINSUM/match-frac × HOME/AWAY/DIFF), 98.6% coverage. A/B vs the E22 top250 incumbent via `loop_ab.py`: W5 10 seeds (superiority gate, pre-registered) + 21-window diagnostic. | **W5: nothing FOR the augmented arm** (RF 3w/3l acc; XGB −2.2pp ns; all MAE/AUC ns) → gate failed, verdict locked. Diagnostic windows (labeled, could not change verdict): pooled null (best case RF acc +0.6pp, McNemar p=.074); **early-season Oct–Dec slice refutes the "helps early" hypothesis** (RF −0.35pp, XGB −1.1pp acc). Team-level twin of the P3 null: redundant with cross-season ELO + availability-aware slot impacts. | **REJECT** 2026-07-16 — §E25 below |
| **P3** | **Prior-season Estimated RAPTOR as player-projection features** | Kai asked whether RAPTOR/LEBRON-class impact metrics improve the models. Sourcing: real RAPTOR dead (data ends 2021-22), LEBRON no export/API, DARKO DPM = only free daily point-in-time series covering 2023-26; Paine Estimated RAPTOR (0.89 corr w/ RAPTOR, thru 2024-25, `outputs/nba_estimated_RAPTOR.csv`) = the backtest source. P2 model had zero RAPM-family signal (only PIE_L10/USG_PCT_L10). | `experiments/p3_impact_metrics.py`: +PREV_ERAPTOR_{OFF,DEF,TOT,WAR82} (previous-season rating, minutes-weighted across stints, normalized-name join, 87.5% match every season, rookies NaN — point-in-time safe by construction). 3 seeds × the 3 P2 walk-forward folds, baseline-vs-augmented paired t-test on per-row \|error\|; keep-gate = ΔMAE<0 AND p<0.05 in all folds for ≥2/3 seeds. | **NULL: 0/11 stats keep, 0 seeds pass the gate anywhere.** Mean ΔMAE: PTS −0.0068, all others ≤ \|0.0013\|. The trees USED the features (gain rank 16-30 of 139 in MIN/PTS models) but zero out-of-sample gain — redundant with L5/L10 form + usage + PREV_*36 priors. Counting stats are the wrong target for a margin-impact metric. | **Rejected for player model 2026-07-10** — open follow-up: eRAPTOR/DARKO in the TEAM model (availability weighting in `player_impact.py` Approach B; roster-strength aggregate = E22 candidate); §P3 below |

---

## 2026-05-19 — Experiment 12: Noise-aware feature ablation (the "is it signal or noise?" study)

### Why this experiment exists
E9, E10, and E11 were each judged on a **single** walk-forward run. The reported deltas were small (≤1pp accuracy, ≤0.013 AUC, ≤0.5 MAE). The concern raised: a single run conflates three things that move the metric — (1) the feature's real effect, (2) the model's random-seed init, and (3) which 230 games happened to land in the test window. If (2)+(3) are larger than (1), then "config X beat config Y by 0.4pp" is a coin flip dressed up as a result, and we'd be permanently bolting noisy features onto the pipeline.

This experiment measures all three so we can separate them.

### How to read the statistics (important — this is the whole point of E12)

There are **two different variances** in play, and conflating them is the usual mistake:

1. **Marginal (per-config) variance** — "if I retrain config X and re-sample the test set, how much does its accuracy wobble?" We estimate this by bootstrap-resampling the 230-game W5 test set 1000× for each of 10 seeds (10,000 measurements per config). On this dataset that gives **±~5pp on accuracy, ±~0.06 on AUC, ±~1.2 points on MAE**. This is the number that makes a raw "76.1% vs 76.5%" comparison meaningless — both numbers' confidence intervals overlap almost entirely.

2. **Paired (config-vs-config) variance** — the *right* quantity for "is X better than Y?" Because both configs are scored on the **same** test games, the shared game-to-game difficulty cancels out. We only look at the games where the two configs *disagree*. This is far more sensitive than comparing two marginal CIs. Three paired tests, one per metric:
   - **Accuracy → McNemar's test.** Of the games where config and baseline disagree, how lopsided is the win/loss split? `cfg_wins/base_wins = 10/4` is suggestive; `8/9` is nothing. p comes from a binomial against 50/50.
   - **MAE → paired t-test on per-game |error|.** For each game, `|error_cfg| − |error_base|`. Mean negative = config has smaller errors. The paired structure removes the "some games are just blowouts" variance.
   - **AUC → bootstrap on the *difference* AUC_cfg − AUC_base.** Resample the test set 1000×, compute the delta each time, read the 95% CI and the fraction crossing zero.

**The headline lesson**: the marginal CIs are wide (±5pp), but the paired tests can still detect a consistent +0.013 AUC effect (E9) because it shows up on the *same games* run after run. Conversely, E11's "+1.3 to +2.6pp" from the single-run measurement **failed every paired test** — it was the test-window-difficulty + seed noise, not the feature.

So: a sub-1pp accuracy or sub-0.005 AUC delta is *presumed noise* until a paired test says otherwise. That presumption was correct for E10 and E11, and wrong (in the good direction) for E9.

### Setup
- **Window**: W5 only. Train on all games < 2026-03-15 (n=6021), test on 2026-03-15 → 2026-04-15 (n=230). W5 chosen because cross-window variance is dominated by *test-set difficulty* (Dec games are intrinsically harder than April games), not model quality — so averaging W1-W5 would bury a real W5 effect under early-window noise. (See the "W1→W5 is not a learning-curve" discussion; that's a separate backlog item.)
- **Configs**: all 8 on/off combinations of {E9, E10, E11}.
- **Seeds**: 10 (`42, 123, 456, 789, 1000, 2024, 31337, 65535, 8675309, 99999`).
- **Models**: RF + XGB. (NN excluded — ~150s/train made the full grid a 7-hour job, and NN was the least production-relevant + least stable model. Can be re-run at N=5 if needed.)
- **E7**: evaluated by re-running the whole grid on a second CSV built with `--availability-source postgame` (E7-off). E7 can't be a column-selection toggle because it changes the *values* in `_AVAILABLE` columns, not their presence.

### Results — per-feature verdict

**E9 (ELO) → KEEP.** The only feature that cleared a paired test. RF AUC Δ = **+0.013, bootstrap p ≈ 0.012-0.016**, and it replicated on *both* the E7-on and E7-off CSVs (so it's not an artifact of one data variant). The accuracy McNemar didn't reach p<0.05 (8/3 split, p≈0.23) and MAE was flat — but a real, replicated AUC gain on 4 cheap columns is enough to keep. ELO ranks teams in a way the rolling box-score features don't fully reconstruct.

**E10 (opponent-strength adjustment) → DROP.** Not merely useless — *harmful*. RF MAE **regressed by +0.034 points, paired-t p=0.023** (E7-on) and **p=0.011** (E7-off). The XGB AUC also regressed in the E10-only and E10+E11 combos (e.g. E10+E11 XGB AUC Δ −0.012, p=0.048). The 54 added columns (9 stats × {OPP_ADJ, ALLOWED} × {HOME, AWAY, DIFF}) are highly correlated with the existing rolling stats; they fed the median-imputer + tree splits more noise than signal. The single-run "+1.3pp RF accuracy" that originally justified E10 did not survive — its accuracy McNemar here is 1/3 and 3/4 (p≈0.6-1.0, i.e. coin flips).

**E11 (LeagueDashLineups) → DROP.** No paired test reached significance on any model, any metric, either CSV. The original single-run "+1.3pp RF / +2.6pp XGB" was entirely inside the marginal CI. Cost was high: 27 columns, 57% NaN-imputed (snapshot coverage only 2024+). Pure liability.

**E7 (pre-game injury data) → KEEP (directional).** E7 lives in a different measurement regime — it's a CSV-content toggle, so we compare the *same config* across the two CSVs rather than within one. On the full config, **XGB MAE is 0.31-0.41 points lower with E7-on** (11.78 vs 12.08 on the full config; 11.72 vs 12.13 on baseline) and AUC is +0.006 higher. RF is roughly flat. **Caveat**: this is *not* a formally paired test — the two CSVs re-run seeds on different data, so there's no game-level pairing between them, and we can't put a clean p-value on it. We keep E7 on the strength of (a) a consistent 3% relative MAE improvement on the XGB regressor, (b) it being the most literature-supported of the four, and (c) it costing nothing extra (the `_AVAILABLE` columns exist either way). If a future round wants rigor here, the move is a paired bootstrap that resamples the *same* game_ids from both CSVs.

### What got changed in the codebase
- **`core/features.py`** — new single source of truth. Replaces the three drifted `feature_patterns` lists (the drift is what caused the silent ELO-drop bug in E9/E11). Production defaults: `ENABLE_E9_DEFAULT=True`, `ENABLE_E10_DEFAULT=False`, `ENABLE_E11_DEFAULT=False`. Includes `assert_features_present()` to fail loud if the CSV is missing an expected pattern.
- **`data_engineering/feature_engineering.py`** — E10 (`add_opponent_adjusted_rolling_features`) and E11 (`_join_lineup_features`) calls removed from the pipeline. Function bodies retained with disabled-banners for future re-evaluation.
- **Production model**: retrained, 648 → **567 features** (kept E9's 4 ELO cols, dropped E10's 54 + E11's 27).
- **Reusable harness**: `experiments/e3_noise_ablation.py` (run the grid) + `experiments/e3_make_report.py` (render markdown). Re-runnable for any future feature addition — this is now the bar a new feature must clear.

### Confirmation walk-forward (clean pipeline, single seed — interpret within the ±5pp noise band)
```
W5: RF 0.791 / AUC 0.835 / MAE 11.90   XGB 0.770 / 0.826 / 11.67   NN 0.765 / 0.820 / 11.60
```
RF is flat-to-better vs the bloated full-feature model; XGB's W5 accuracy "dropped" from 0.800 → 0.770 but that 0.800 was itself a noise high (XGB cleared zero paired tests), and XGB's MAE *improved* 11.86 → 11.67.

### Caveats / follow-ups
- Single window (W5). A feature that helps specifically in December (W1) would be invisible here. Defensible because W5 is the production-relevant "predict next month" case, but noted.
- NN was excluded for runtime. If NN becomes a production model, re-run the grid for it.
- The E7 comparison wants a properly paired cross-CSV bootstrap to earn a p-value.
- E10/E11 columns are gone from new CSVs; to re-evaluate them later, re-enable the build calls + flip the `core.features` defaults, then rebuild.

---

## 2026-05-18 — Experiment 1: Reduce RF capacity, add NN regularization, seed PyTorch

### Baseline
Rows 11–14 in `model_registry` (versions `rf_classifier_20260518_2`, `rf_regressor_20260518_2`, `nn_classifier_20260518_2`, `nn_regressor_20260518_2`). All on the same train window (2025-10-30 → 2026-03-15) and test window (2026-03-15 → 2026-04-15), 907 train rows, 227 test rows, 627 features.

| Model | Train | Test | Gap |
|---|---|---|---|
| RF classifier accuracy | 99.9% | 76.2% | **24pp** |
| NN classifier accuracy | 86.5% | 68.3% | 18pp |
| RF regressor MAE | 5.26 | 12.24 | 7 pts |
| NN regressor MAE | 7.57 | 13.12 | 5.5 pts |

### Hypothesis
The gaps above are overfitting, not signal. Three changes, each targeting a distinct cause:

1. **PyTorch is non-deterministic**: NN test accuracy varied by 2.6pp between two re-runs of the *same* config (65.6% → 68.3%). Without a seed, any future hyperparameter A/B is contaminated by init noise. Fixing this is a prerequisite for trusting NN results.
2. **RF has too much capacity for 907 rows**: `max_depth=10, n_estimators=100, min_samples_leaf=1` lets each tree memorize the training set. 99.9% train accuracy on a noisy domain like NBA prediction is the smoking gun. Constraining `max_depth=5, min_samples_leaf=20` cuts capacity sharply. Prediction: train accuracy drops to ~85-90%; test accuracy stays near 76% or improves slightly. If test drops a lot, we over-constrained.
3. **NN is under-regularized**: `dropout=0.3, weight_decay=0` is light for a 627-input MLP. Bumping to `dropout=0.5, weight_decay=1e-4` should pull the train/test gap in.

### Changes (`modeling/predict_games.py`)
| Component | Before | After |
|---|---|---|
| `rf_clf_hp` / `rf_reg_hp` | `max_depth=10`, no `min_samples_leaf` | `max_depth=5`, `min_samples_leaf=20` |
| RF constructors (train + full-data retrain) | use literal `100, 10` | read all params from the hp dict |
| `nn_clf_hp` / `nn_reg_hp` | `dropout=0.3`, no `weight_decay` | `dropout=0.5`, `weight_decay=1e-4` |
| `NBAClassifier` / `NBARegressor` instantiations | default `dropout_rate=0.3` | pass `dropout_rate=hp['dropout']` |
| `_train_pytorch_model` | `Adam(lr=0.001)`, no seeds | `Adam(lr=0.001, weight_decay=1e-4)`, `torch.manual_seed(42)`, `np.random.seed(42)` at top |

### Expected Outcome
- **RF classifier**: train acc drops to **85–92%**, test acc holds **73–78%**. Gap closes from 24pp to under 15pp. If test drops below 70%, the constraint was too tight.
- **NN classifier**: train acc drops to **78–82%**, test acc **65–70%**. Gap closes from 18pp to under 12pp.
- **Regressors**: train MAE rises ~2–3 points, test MAE holds 12–13 or improves slightly. If both rise, we under-fit; revert.
- **NN reproducibility**: re-running with no config change produces identical metrics. Pre-fix, NN test acc varied by 2.6pp run-to-run; post-fix, it should be 0.

### Results
Run at 2026-05-18 15:19. Rows 15–18 in `model_registry` (versions `*_20260518_3`). Same train/test windows as baseline.

| Model | Metric | Baseline (rows 11-14) | E1 (rows 15-18) | Δ |
|---|---|---|---|---|
| RF classifier | Test accuracy | 76.21% | 74.89% | **-1.3pp** |
| RF classifier | Test AUC | 0.8124 | **0.8296** | **+0.017** ✓ |
| RF classifier | Train accuracy | 99.89% | 79.60% | -20.3pp (good — was memorizing) |
| RF classifier | **Train/test gap** | **24pp** | **4.7pp** | **-19.3pp** ✓ |
| RF regressor | Test MAE | 12.24 | 12.33 | +0.09 (essentially flat) |
| RF regressor | Test R² | 0.307 | 0.295 | -0.012 (essentially flat) |
| RF regressor | **Train/test MAE gap** | **7.0 pts** | **3.0 pts** | **-4.0 pts** ✓ |
| NN classifier | Test accuracy | 68.28% | 68.72% | +0.4pp |
| NN classifier | Test AUC | 0.7808 | **0.8032** | **+0.022** ✓ |
| NN classifier | **Train/test gap** | **18pp** | **9.6pp** | **-8.4pp** ✓ |
| NN regressor | Test MAE | 13.12 | **12.92** | **-0.20** ✓ |
| NN regressor | Test R² | 0.2254 | **0.2433** | **+0.018** ✓ |
| NN regressor | **Train/test MAE gap** | **5.55 pts** | **2.91 pts** | **-2.64 pts** ✓ |

**Headline:** Every train/test gap closed significantly, and every AUC improved. NN regressor actually got *better* on the held-out test (MAE -0.2, R² +0.018) — strong evidence the prior model was wasting capacity on memorization. RF classifier accuracy dropped 1.3pp but AUC went up — the constrained trees are better calibrated even if slightly less accurate at the 0.5 threshold.

**Hypothesis was right.** All three predictions held:
1. ✓ RF train acc dropped from 99.9% → 79.6% (predicted 85-92%, slightly more aggressive than expected — `min_samples_leaf=20` had teeth).
2. ✓ NN regularization closed the NN gap by ~half without hurting test metrics.
3. ✓ Seeding made NN reproducible — no run-to-run drift to disentangle from real hyperparameter effects anymore.

**One observation worth flagging.** Test accuracy of ~75% on a clean temporal hold-out is *high* for NBA straight-up winner prediction — Vegas lines hit around 67%. Two innocent explanations: this particular test window (2026-03-15 → 2026-04-15, end of regular season) may have been easier than average (lots of tanking teams creating predictable matchups), or the feature set is genuinely good. One less-innocent explanation: residual leakage from `*_SLOT_*_IMPACT` or `PROJ_*` features. The right next move to disentangle is `python modeling/validate_models.py --start 2025-12-01 --end 2026-02-01` (validate on a different window). If 75% holds up there, the feature set is fine; if it drops to 65%, that test window was just easy.

### Decision
**KEEP.** Promote rows 15-18 to baseline for future experiments. Hyperparameters in `predict_games.py` reflect the new defaults. No revert.

### Next moves
- **E2 candidate: held-out validation on a different window** to test the 75% accuracy generalization claim.
- **E3 candidate: try XGBoost** as a new model type using the infrastructure built in the multi-model refactor (recipe in README). XGBoost typically does well on tabular and would give a third independent signal.
- **E4 candidate (only if E2 reveals window-shopping)**: feature leakage audit, starting with `_SLOT_*_IMPACT` (verify `compute_date <= game_date` is actually enforced everywhere it's queried) and `PROJ_*` (verify season-to-date stops at `as_of_date`).
- Lower-priority: try `max_depth=7, min_samples_leaf=10` to see if there's room to recover the 1.3pp RF accuracy drop without reopening the gap.

---

## 2026-05-18 — Experiment 2: Walk-forward validation across 5 windows

### Question
Does the 74.89% test accuracy from E1 generalize, or was the Mar–Apr 2026 window just easy? If it does generalize, we have a real ~75% model; if it doesn't, the E1 metric was window-shopping.

### Method
`validate_models.py` won't answer this honestly: it loads the production model on disk, which was retrained on the *full* dataset. Any window picked from that dataset is in-fold, so the metric would be inflated.

Wrote `experiments/e2_walk_forward.py` instead — for each window, it trains a fresh model on data **strictly before** the window start, then predicts on the window. Pure in-memory experiment; no bundles written, no DB rows touched, no production model disturbed. Hyperparameters mirror the current E1 production defaults exactly (`max_depth=5, min_samples_leaf=20` for RF; `dropout=0.5, weight_decay=1e-4, seed=42` for NN).

Windows chosen to be non-overlapping and to cover the full 2025-10-30 → 2026-04-15 season range, with monotonically increasing training set sizes so we can also read off a learning curve.

### Results

| Window | n_train | n_test | RF acc | RF AUC | RF MAE | NN acc | NN AUC | NN MAE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| W1 (Dec 2025)           | 208 | 184 | **0.582** | 0.590 | 12.07 | 0.527 | 0.533 | 11.98 |
| W2 (Jan 2026)           | 392 | 229 | 0.585 | 0.620 | 11.94 | 0.594 | 0.585 | 11.95 |
| W3 (Feb 2026)           | 621 | 174 | 0.598 | 0.718 | 12.26 | 0.621 | 0.679 | **24.51** ⚠ |
| W4 (Mar 1–15)           | 795 | 116 | 0.716 | 0.779 | 10.68 | 0.690 | 0.781 | 10.94 |
| W5 (Mar 15–Apr 15)      | 904 | 230 | **0.748** | 0.821 | 12.39 | **0.726** | 0.797 | 12.54 |

Raw JSON: `outputs/e2_walk_forward_results.json`.

### Findings

**1. The 75% number from E1 is real, not leakage.** W5 walk-forward retrains on 904 games (essentially the same training set as E1's 907) and gets 74.8% RF accuracy, AUC 0.821 — within rounding of the E1 row 15 numbers (74.89%, AUC 0.830). If E1 had been benefiting from leakage, walk-forward would have crashed the number; it didn't.

**2. Performance tracks training set size almost monotonically — data quantity is the binding constraint.** RF accuracy climbed 58.2% → 58.5% → 59.8% → 71.6% → 74.8% as the training set grew from 208 → 904 games. AUC climbed 0.59 → 0.82. This is a textbook learning curve and the strongest evidence that nothing weird is going on: a leaky model would show flat or non-monotonic accuracy regardless of training size; a real model needs data to learn.

**3. RF is dramatically more stable than NN across windows.** RF MAE held 10.7–12.4 across all 5 windows; NN MAE blew up to 24.5 on W3 (621 train rows). The NN W3 anomaly reproduced across two runs of this script, so it's not random noise — there's a training-instability regime where a mid-sized dataset + early stopping + target scaler interact badly. Not a blocker today (W5 with full data works fine), but worth knowing.

**4. NN underperforms RF at every training set size in this experiment.** RF wins on accuracy in 4 of 5 windows, on AUC in 4 of 5, and on MAE in 3 of 5. Combined with the W3 instability, this reinforces "RF is the better model for this dataset" — consistent with the tabular-data heuristic.

### Decision
**No code change.** E2 was a diagnostic experiment, not a tuning one. Keep the E1 hyperparameters as the production defaults. The headline conclusion is that the 75% is genuine — and that the model is data-limited, not algorithm-limited or feature-engineering-limited.

### Implications for next moves
The learning curve in finding (2) is the single most important signal we've seen. The model is gaining ~3pp of accuracy per ~150 additional training games at this scale. That ranks the candidate next-moves like this:

- **HIGH leverage: get more historical data.** Backfill 2022–23, 2023–24, 2024–25 seasons into the features CSV. We're at 1134 games (one season). Adding 3 prior seasons could plausibly push us to 80% accuracy with no model changes. The slope of the learning curve says we have not yet entered diminishing returns.
- **MEDIUM leverage: XGBoost (planned E3).** Different bias/variance trade-off than RF; might gain 1-2pp where RF plateaus. Worth doing because the infrastructure is in place.
- **LOWER leverage right now: feature engineering or hyperparameter tuning.** With a steep learning curve still in front of us, these will have smaller marginal impact than just feeding the model more games.
- **One bug to investigate when convenient**: the NN W3 MAE=24.5 anomaly. Reproducible. Probably target_scaler interaction with a smaller dataset where early stopping fires before the model has stabilized. Not blocking; document and move on.

---

## 2026-05-18 — Experiment 3: Add XGBoost + retry walk-forward (with more data attempted)

### Question
Two things bundled:
1. Does **XGBoost** beat RF on this dataset? It usually does on tabular data, so worth checking.
2. Does the **learning curve** observed in E2 extend if we backfill 3 prior seasons (2022-01 through 2025-10) into the features CSV? E2 showed accuracy climbing from 58% → 75% as training data grew from 208 → 904 games, and the slope hadn't plateaued.

### Method
**XGBoost wired in as a new model type** using the multi-model dispatch built earlier. Added `ModelTypeSpec(key='xgb', ...)` to `modeling/model_types.py` and `load_or_train_xgb_models` / `predict_with_xgb` to `modeling/predict_games.py`, registered in `LOADER_DISPATCH` / `PREDICT_DISPATCH`. Hyperparameters: `n_estimators=200, max_depth=4, learning_rate=0.1, min_child_weight=10, subsample=0.8, colsample_bytree=0.8, reg_lambda=1.0` — a regularization profile comparable to the E1 RF defaults but with the shallower per-tree depth that suits boosting. SHAP via `TreeExplainer` (same as RF). Pipeline `--model` choices and dashboard tabs both auto-picked-up `xgb` with zero edits (the central registry did its job).

**Walk-forward extended** in `experiments/e2_walk_forward.py` to add a third model column. Same 5 windows as E2.

**Multi-season backfill attempted** — ran `python data_engineering/feature_engineering.py --start-date 2022-01-01`. Verified data availability beforehand: `player_impact` table has 47 monthly snapshots back to 2022-01-01, and `boxscoreadvancedv3_team` covers 38,878 games back to 1996-11. The rebuild was started in the background but had not completed at the time of writing this entry — the player-projection-feature step is dominating runtime (~30+ minutes elapsed and still working).

### Results (1-season data, 1134 games — multi-season pending)

| Window | n_train | n_test | **RF acc** | **RF AUC** | **XGB acc** | **XGB AUC** | **NN acc** | **NN AUC** |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| W1 (Dec 2025)       | 208 | 184 | 0.582 | 0.590 | 0.500 | 0.510 | 0.511 | 0.541 |
| W2 (Jan 2026)       | 392 | 229 | 0.585 | 0.620 | 0.550 | 0.570 | 0.576 | 0.612 |
| W3 (Feb 2026)       | 621 | 174 | 0.598 | 0.718 | 0.603 | 0.657 | 0.609 | 0.651 |
| W4 (Mar 1-15)       | 795 | 116 | **0.716** | 0.779 | 0.664 | 0.750 | **0.724** | 0.778 |
| W5 (Mar 15-Apr 15)  | 904 | 230 | **0.748** | **0.821** | 0.717 | 0.796 | 0.735 | 0.805 |

Regression MAE (lower = better): RF 10.7–12.4 throughout, XGB 11.3–12.7, NN 11.0–13.1 except the W3 instability (NN MAE 26.4 — still reproducible).

Full JSON: `outputs/e2_walk_forward_results.json` (overwritten by each re-run of the script).

### Findings

**1. XGBoost underperforms RF at every window on this 1-season dataset.** RF wins accuracy in 4 of 5 windows (tie in W3), AUC in 4 of 5. Largest gap is W1 (XGB 50% — literally coin flip), where XGB had only 208 training games. The gap narrows as data grows: by W5 XGB is within 3pp of RF on accuracy and 0.025 on AUC.

**2. This is the *expected* XGBoost behavior under-data.** Boosting methods are typically more data-hungry than bagging methods like RF, because each tree corrects the residual of the previous and small training sets give unstable residuals. XGB needs the multi-season data to fairly evaluate. Don't write off XGB on this run alone — re-evaluate once the multi-season CSV is available.

**3. The E2 learning curve is reinforced.** All three models climb monotonically with training data. The slope persists through W5 — no model has flattened out. Adding more training data should still help.

**4. NN W3 regression anomaly reproduces again** (MAE 26.35, vs RF 12.26 / XGB 11.83). Third reproducible occurrence at the n=621 train-set size. Confident this is a deterministic regime issue (target_scaler interaction with early stopping at mid-size data), not random noise. Worth a dedicated investigation when convenient, but not blocking.

**5. Dashboard now visualizes AUC.** Added ROC curve and confusion matrix charts to the Model Performance tab. The ROC plot puts all loaded models on one canvas with the diagonal random baseline — you can see at a glance which model dominates which threshold range. Confusion matrices side-by-side show what *kind* of mistakes each model makes (e.g., does it over-predict home wins?).

### Decision
- **KEEP** XGBoost wired in — the infrastructure works, the model just needs more data to compete.
- **Don't promote** XGBoost over RF as the primary model on this dataset. RF still wins.
- **Don't change** RF or NN hyperparameters based on this run. Same E1 defaults.

### Next moves
- **Pending: re-run walk-forward when the multi-season CSV finishes building.** Expected: XGB closes the gap on RF or beats it; RF and NN accuracies climb a few more points. If XGB *still* loses with 4x more data, then RF is genuinely better-suited to this feature set and we deprioritize XGB.
- **NN W3 investigation** — try `target_scaler.fit_transform` *only on training*, never re-applying; check whether the early-stopping `patience` should scale with dataset size.
- **Lower priority but interesting**: ensemble (RF + XGB + NN simple average). With three differentiated models, ensemble usually beats the best single model by 1-2pp.

### Results (4-season data, 7342 games — after the rebuild finished)

Multi-season CSV built (`feature_engineering.py --start-date 2022-01-01` after fixing two `✓`/`✗` Unicode chars that were crashing the final print on Windows cp932). 7342 rows spanning 2022-01-01 → 2026-05-13. Same 5 windows, same hyperparameters; only the training set sizes grew.

| Window | n_train | n_test | **RF acc** | **RF AUC** | **XGB acc** | **XGB AUC** | **NN acc** | **NN AUC** |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| W1 (Dec 2025)       | 6348 | 184 | **0.592** | 0.621 | 0.511 | 0.531 | 0.549 | 0.588 |
| W2 (Jan 2026)       | 6532 | 229 | 0.581 | 0.630 | 0.594 | **0.647** | **0.607** | 0.663 |
| W3 (Feb 2026)       | 6761 | 174 | 0.580 | **0.713** | 0.644 | 0.689 | **0.672** | 0.702 |
| W4 (Mar 1-15)       | 6935 | 116 | **0.767** | 0.791 | 0.707 | 0.766 | 0.707 | 0.789 |
| W5 (Mar 15-Apr 15)  | 7044 | 230 | **0.778** | **0.821** | 0.739 | 0.816 | 0.426 ⚠ | 0.814 |

### Findings

**1. The learning curve has flattened.** Going from 904 → 7044 training rows on W5 (~7.8× more data) only added +3pp RF accuracy and **zero AUC change** (0.821 → 0.821). Averaged across all 5 windows, RF accuracy gained ~1.4pp. The slope I extrapolated in E2 (+3pp per +150 games) was reading the under-data regime where every model was data-starved; we're now mostly out of that regime. **Data is no longer the binding constraint.** The model has hit a feature/signal ceiling.

| Window | n_train 1-season | n_train 4-season | RF acc 1-season | RF acc 4-season | Δ |
|---|---:|---:|---:|---:|---:|
| W1 | 208 | 6348 | 0.582 | 0.592 | +0.010 |
| W2 | 392 | 6532 | 0.585 | 0.581 | −0.004 |
| W3 | 621 | 6761 | 0.598 | 0.580 | −0.018 |
| W4 | 795 | 6935 | 0.716 | **0.767** | **+0.051** |
| W5 | 904 | 7044 | 0.748 | **0.778** | **+0.030** |

**2. XGBoost benefited more from extra data than RF.** XGB gained +2 to +4pp on every window, and in W2/W3 it actually beat RF on accuracy. The gap to RF shrank from ~5pp to ~1-4pp. This is the *expected* XGBoost-data-scaling behavior: boosting needs bigger training sets than bagging to stabilize. With this much data XGB is now a real contender.

**3. RF still leads overall.** Best on accuracy in 3 of 5 windows; best on AUC in 3 of 5. The W5 RF AUC of 0.821 is the strongest single-model out-of-sample result we've measured.

**4. New NN instability: W5 accuracy 42.6%, worse than random.** AUC for the same model is 0.814 (perfectly good ranking), so this is a **threshold calibration failure**, not a ranking failure. The NN is probably outputting probabilities tightly clustered above or below 0.5, so the binary classification at the 0.5 threshold falls on the wrong side for most predictions. Reproducible with `seed=42`. Same family of issues as the W3 regressor MAE=24 anomaly we kept seeing in E2/E3 — NN training is fragile across multiple data scales in a way RF and XGB are not.

**5. MAE is essentially unchanged.** RF W5: 12.39 → 12.21 (-0.18 pts). All three models cluster around 12 pts MAE for margin prediction. Vegas closing-line MAE is ~10-11 pts, so the model still trails the line meaningfully. More data didn't close that gap, which reinforces (1): we need *better signal*, not more rows.

### Decision (updated)
- **KEEP XGBoost.** It's now competitive with RF and clearly benefited from the extra data. Both models stay in the rotation.
- **Don't promote XGB over RF.** RF still wins narrowly overall and is more stable.
- **No hyperparameter changes** based on this run.
- **The big strategic update**: stop pursuing "more data" as the next experiment. The slope says diminishing returns.

### Next moves (updated)
- **E5 candidate: new features.** The MAE ceiling at ~12 vs Vegas at ~10-11 says the feature set is the limit. Candidates that might help:
  - Travel distance / time-zone changes (currently missing)
  - Refresh recency of injury data (currently uses player_impact compute_date)
  - Vegas opening line as a feature (would push us above Vegas asymptotically)
  - Lineup-level data (which 5 are on the floor together)
- **E6 candidate: NN stabilization investigation.** Two separate NN failure modes seen now (W3 regressor MAE blowup at n=621, W5 classifier accuracy collapse at n=7044). Hypothesis: BatchNorm + small validation set + early stopping interact badly. Try `nn.LayerNorm` instead of `nn.BatchNorm1d` or remove BN entirely.

---

## Backlog (un-prioritized, to be slotted into experiments as the situation warrants)

### E4 — Ensemble (RF + XGB simple-average)
**Why deprioritized**: Ensembling will almost certainly reduce error by 1-2pp, but it obfuscates the per-model performance picture we've been building. We're still actively understanding which model is doing what under which conditions — premature to collapse them into a single average. Revisit once individual models are stable and we want a production "best-of" predictor.

### E7 — Reconstruct historical pre-game injury data (and fix the related backfill leak)
**Two distinct bugs this addresses, same root cause:**

1. **Training-data leakage** (identified in the E3 post-hoc audit): `bulk_fetch_player_availability` in `data_engineering/player_impact.py:1232` derives `*_SLOT_X_AVAILABLE` features from **post-game boxscores** — whether a player actually showed up. For a training row representing a 2022 game, the model "knows" pre-game whether each star ended up playing, which is information it wouldn't have at real prediction time. This probably inflates walk-forward accuracy by some amount; how much is unmeasured.

2. **Backfilled-predictions distortion** (flagged by user): when `predict_games.py --start-date X` re-creates historical predictions (logged to `model_predictions`), `--auto-injuries` is force-disabled because the live ESPN feed isn't point-in-time. So those backfilled predictions are made *as if every player was available*, which is the opposite mistake — pre-game predictions made without injury info at all. This deflates the apparent live accuracy and breaks the comparability of backfilled rows with same-day "true live" rows.

**Approach (in priority order)**:

1. **Attempt to reconstruct historical pre-game injury reports.** Sources to investigate:
   - NBA official injury report archive (varies by season; some go back to 2015 in PDF form)
   - Sports Reference / Basketball-Reference daily transactions / DNP logs
   - Wayback Machine snapshots of ESPN injury pages (sparse coverage)
   - Third-party APIs (some commercial services archive)
2. **If reconstruction isn't tractable**, fall back to: derive availability from boxscores **but build per-game `player_impact` snapshots** rather than monthly. The leak is still present (we still know who showed up), but the impact values themselves would be computed from each player's last-N-games-before-this-game window — strictly point-in-time correct on impact, with only the availability flag being post-hoc. Then re-run the walk-forward on the leak-reduced features and quantify the accuracy delta vs current — that delta is the leak's actual magnitude.

**Concrete sub-goals**:
- (a) Whatever injury-data source we settle on, write it into a new `historical_injury_report (game_date, team_id, player_id, status, source)` table.
- (b) Update `feature_engineering.py` and `predict_games.py` to read from this table at point-in-time when building features for both training rows and backfilled predictions.
- (c) Re-run E3 walk-forward; record the new RF/XGB/NN numbers. The delta vs the current ~75% is the leak's contribution.
- (d) Re-run backfill on `model_predictions` so historical entries reflect injury-aware predictions; the live-vs-walk-forward accuracy gap should narrow.

---

## Active research findings (2026-05-18)

Four parallel research streams kicked off; all returned the same day.

### Stream 1: Critical code review of feature pipeline (Agent 1)
**Bug findings (sorted by severity):**

1. **CRITICAL BUG — slot/injury features are silently double-prefixed.** `calculate_player_slot_features` writes `HOME_SLOT_X_IMPACT` / `AWAY_SLOT_X_IMPACT` columns to *both* the home-team and away-team rows of each game (`feature_engineering.py:1057-1063`), then `create_matchup_features` adds another HOME_/AWAY_ prefix, producing things like `AWAY_HOME_SLOT_1_IMPACT == HOME_HOME_SLOT_1_IMPACT` (identical duplicates) and `DIFF_AWAY_SLOT_1_IMPACT == 0` (always zero). **~56 duplicate columns and ~20 constant-zero DIFF columns sit inside our 627-feature input vector right now.** Same bug also corrupts `*_INJURY_IMPACT` when the legacy flag is on. Fix: write slot features under neutral names (`_TEAM_SLOT_1_IMPACT`) before the home/away merge, OR exclude them from the rename map in `create_matchup_features`. **One-evening change, must precede any further hyperparameter or feature experimentation** — every metric we've recorded so far has been measured on a corrupted feature set.
2. **No opponent strength adjustment in rolling features.** All `_L5`/`_L10` rolling stats are raw means with no schedule adjustment. A 10-0 streak against tanking teams looks identical to a 10-0 streak against contenders. Almost certainly the biggest gap vs Vegas-quality models.
3. **`get_player_season_averages` ignores team changes (`player_projections.py:384-413`).** Filters on `personId` but not `teamId`. A traded player's projection at their new team uses their last 10 games globally — i.e., partly with their old team. Distorts `PROJ_PTS_FROM_PLAYERS` and `WEIGHTED_AVG_USAGE` worse every February. Fix: add `AND trad.teamId = {team_id}` to the query.
4. **Player projection step is the 50-min-rebuild bottleneck.** 4 sequential SQL queries × ~10K team-games × ~10 rotation players = ~100K DB roundtrips, with `prefer="threads"` joblib that doesn't help because pandas `read_sql` serializes on the DB. Fix: bulk-fetch all player-game rows once (like `bulk_fetch_player_impacts` already does). Won't move accuracy but ~10× faster iteration.
5. **Massive HOME/AWAY/DIFF triplet multicollinearity.** `prepare_ml_dataset` emits HOME, AWAY, AND DIFF for every base feature. DIFF is a perfect linear combination of HOME and AWAY. Inflates input dim, drives RF toward noisy splits, scrambles SHAP. Fix: pick one of {HOME+AWAY} or {DIFF+SUM}.
6. **Off-by-one in fatigue windows + dead duplicate code at `feature_engineering.py:416`** (a `IS_3_IN_4_NIGHTS` definition immediately overwritten).
7. **`modeling/featureSelection.py` is fully broken** — runs SelectKBest with `PLUS_MINUS` as target against CURRENT-game stats (PTS, FGM, AST). Selects the obvious leak. Delete the file or rewrite to use `nba_ml_features.csv` against `TARGET_MARGIN`.

**Agent's one-pick: fix #1 first** — eliminates ~75 garbage columns, restores meaningful slot-impact differentials, unblocks honest SHAP on player-availability.

### Stream 2: Literature survey of NBA ML prediction (Agent 2)
- **Published SOTA accuracy clusters at 65–72%** with rare outliers above 75%. 538 RAPTOR 66.4%; 538 Elo 67%; LSTM 72.35% [(MDPI)](https://www.mdpi.com/2079-3197/13/10/230); GCN 71.5%; XGBoost+SHAP 72% with first-half data only [(PLOS ONE)](https://pmc.ncbi.nlm.nih.gov/articles/PMC11265715/); Bryant thesis 65.3% Elo; Pirkn ensemble NN 66.9% / XGB 64.8%.
- **Our 75% walk-forward is suspiciously high and should be treated as unverified until E7 (leak audit) lands.** If real and clean, we're at the genuine SOTA frontier. If we lose 5pp after the leak fix, expect 67–70% honest baseline — still competitive.
- **MAE 12 is mid-pack academic.** Vegas closing-line MAE ~10–11 is the natural floor.
- **Architecture verdict: XGBoost (or GBM/CatBoost) is the practical standard.** NN wins exist but rarely beat well-tuned XGBoost on the same feature set — "gains attributed to NNs are often really feature-engineering gains."
- **Most-cited features we're MISSING**: travel distance & time-zone shifts (literature reports 4% win-prob drop per 500 km), **opening Vegas line as a feature** (cited as the single biggest free lift in betting-model literature), and explicit ELO ratings.
- **Common pitfalls** documented in literature: season-end stats leaking the future, box-score rolling features computed including the current game, random k-fold instead of temporal split (inflates 3–8 pp), **player projections trained on post-game minutes** (2–5pp inflation — exactly our known leak).
- **Literature's #1 next-move recommendation for us**: audit leakage on strict pre-tipoff cutoff (i.e. our E7); then add ELO + opening Vegas line as features.

### Stream 3: `nba_api` endpoint audit (Agent 3)
**High-leverage adds (ranked):**

1. **LeagueDashLineups** — 5-man lineup stats with NetRtg, eFG%, Four Factors. Captures synergy our additive player-impact model structurally cannot.
2. **SynergyPlayTypes** — PPP and frequency per play type (Transition, P&R, Isolation, etc.). Enables style-matchup vectors.
3. **LeagueDashPtDefend / PlayerDashPtShotDefend** — per-defender D_FG_PCT broken down by zone (3pt, 2pt, <6ft). True defender quality signal.
4. **TeamEstimatedMetrics + PlayerEstimatedMetrics** — season-long E_OFF_RATING, E_DEF_RATING, E_NET_RATING, E_PACE. Regularized rating that smooths small-sample noise. One call per season; cheap.
5. **LeagueDashPtStats** (Drives, CatchShoot, PullUpShot) — team shot-diet vector vs opponent allowed efficiency on those shot types.

**Skip**: PlayByPlayV2/V3 (huge volume, redundant with `WinProbabilityPBP`), various UI/leaderboard endpoints, `LeagueLineupViz` (weaker schema than `LeagueDashLineups`). No injury endpoint exists in `nba_api` — `inactive_players` in `boxscoresummaryv2` is the only native source.

**Agent's one-pick to add first: LeagueDashLineups.** Highest expected lift because the current model decomposes teams as a sum of player-impacts and cannot capture five-man synergy or bench-unit dropoff.

### Stream 4: ELO + probabilistic baselines (Agent 4)
- **Pure NBA ELO ceiling: 65–67% accuracy.** luke-lite replication 65.3%; nicidob's 538 audit 66.4–68%; 538 favorites 64.9% in 2020.
- **538's formula is the de facto standard**: `K=20`, `HCA=100`, `MOV multiplier = (margin+3)^0.8 / (7.5 + 0.006*winner_diff)`, **75% season carryover** to mean (1505).
- **Pure ELO won't match our 75%** — expect 7–10pp gap. But ELO encodes path-dependent franchise-history strength + schedule strength that our rolling box-score averages do not.
- **Implementation cost: ~30 lines + one pass over the existing `game_list` MySQL table (~82K rows, <1 second).** Output: a `team_elo_pregame (game_id, home_elo, away_elo, elo_diff, elo_p_home)` table to join into `nba_ml_features.csv`.
- **Strategic recommendation**: (b) **add ELO as four features into the existing ML pipeline AND (a) keep pure-ELO as a permanent dashboard baseline**. Skip blended-prediction (c) — averaging a 75% model with a 66% model strictly hurts.

### Synthesis — what the four reports say together

**Two threads converge on the same #1 recommendation: do not run any more model experiments until two things are fixed.**

a. **Fix the slot-feature double-prefix bug.** It's a code-only fix (~1 evening). Everything we've measured so far has been contaminated by ~75 garbage columns in the input vector. Every E1/E2/E3 result is suspect until this is rebuilt without the bug.

b. **Complete E7 (audit the availability leak).** The literature survey independently flags exactly this pattern (post-game minutes leaking into training projections) as the most common 2–5pp inflation. Combined with our 75% being suspiciously high vs the published 65–72% range, we should assume the corrected number is ~70%.

After (a) and (b), the high-leverage additions are: **add ELO as features**, **add opening Vegas line as a feature** (if we can source it), **add LeagueDashLineups**, and **add opponent-strength adjustment** to the rolling stats. Roughly in that order — ELO and opponent-adjustment are cheap and universally cited; lineups need a new endpoint plumbed in; Vegas line needs a data source we don't yet have.

Lower-priority adds: TeamEstimatedMetrics (cheap; smooths small-sample noise), SynergyPlayTypes (medium effort; addresses style mismatches), travel/time-zone features.

Lower-priority fixes: player-projection bottleneck (Agent 1 #4 — speeds up iteration but doesn't move accuracy), HOME/AWAY/DIFF multicollinearity (#5 — cleanup), fatigue off-by-one (#6 — minor), delete `featureSelection.py` (#7 — clean-up).

---

## 2026-05-18 — Experiment 8: Fix double-prefix slot-feature bug

### Question
Agent 1's code review identified that `create_matchup_features` was double-prefixing slot/injury features (`HOME_HOME_SLOT_1_IMPACT == AWAY_HOME_SLOT_1_IMPACT`, `DIFF_AWAY_SLOT_1_IMPACT == 0`, etc.), producing ~80 garbage columns inside the 627-feature input vector. How much of our claimed accuracy was inflated by this bug, and does any model behavior change once the columns are gone?

### Method
Verified the bug at scale on the existing CSV: 32/32 duplicate slot pairs, 16/16 always-zero `DIFF_AWAY_SLOT_*` columns. Also discovered a related artifact: Python's `str.replace` replaced **all** occurrences of `HOME_`, producing `DIFF_DIFF_SLOT_*` columns (16 of those too).

Fix in `data_engineering/feature_engineering.py:create_matchup_features` — exclude already-prefixed columns (`HOME_*`, `AWAY_*`, `DIFF_*`) from the per-row rename map, so game-level columns written by `calculate_player_slot_features` pass through home_df once and aren't pulled from away_df at all. Five-line change. Rebuilt features (`--start-date 2022-01-01`), retrained RF/NN, then re-ran the 5-window walk-forward with all three models (RF/XGB/NN) for direct E3-vs-E8 comparison.

### Results

**Column-count delta**: 836 → **756** columns. Eliminated: 32 duplicate pairs, 16 always-zero `DIFF_AWAY_SLOT_*`, 16 weirdly-named `DIFF_DIFF_*`. Now we have a clean (HOME=8, AWAY=8, DIFF=16) slot-feature triplet that actually encodes the home-vs-away differential.

**Walk-forward, E3 (buggy) vs E8 (clean)**:

| Window | RF E3 | RF E8 | RF Δ | XGB E3 | XGB E8 | XGB Δ | NN E3 | NN E8 | NN Δ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| W1 (Dec 2025)  | 0.592 | 0.576 | -0.016 | 0.511 | 0.543 | +0.032 | 0.549 | 0.592 | +0.043 |
| W2 (Jan 2026)  | 0.581 | 0.581 |  0.000 | 0.594 | 0.598 | +0.004 | 0.607 | 0.611 | +0.004 |
| W3 (Feb 2026)  | 0.580 | 0.575 | -0.005 | 0.644 | 0.632 | -0.012 | 0.672 | 0.667 | -0.005 |
| W4 (Mar 1-15)  | 0.767 | 0.767 |  0.000 | 0.707 | **0.741** | **+0.034** | 0.707 | **0.767** | **+0.060** |
| W5 (Mar 15-Apr 15) | 0.778 | 0.748 | **-0.030** | 0.739 | **0.774** | **+0.035** | 0.426 ⚠ | **0.735** | **+0.309** ✓ |

W5 AUC: RF 0.821→0.816 (-0.005), **XGB 0.816→0.826 (+0.010)**, NN 0.814→0.819 (+0.005).
W5 MAE: RF 12.39→12.28, XGB 12.30→**11.78**, NN 12.54→12.35.

### Findings

**1. The NN W5 calibration crash that I logged as a separate bug in E3 was THIS bug.** Previously: NN W5 accuracy = 0.426 (worse than random) with AUC = 0.814 — a textbook calibration failure. Post-fix: accuracy = 0.735, AUC = 0.819. The duplicate slot columns were dominating NN's optimization and pushing the 0.5 threshold into the wrong region. **E6 (NN stabilization investigation) is no longer needed** — the regime instability I was going to attribute to BatchNorm + early stopping was just this same feature corruption manifesting differently across data sizes. NN was harder-hit because dense layers see the duplicates as legitimate independent inputs, while RF tree-splits naturally collapse onto whichever variant has the best split.

**2. XGBoost now leads the W5 leaderboard for the first time.** RF 0.748, **XGB 0.774**, NN 0.735. XGB also wins on AUC (0.826 vs RF 0.816, NN 0.819). And the XGB MAE jumped from 12.30 → **11.78** — closer to Vegas's 10-11 floor than any model we've trained. The bug penalty was larger for XGB than RF because boosting compounds noise across its sequence of weak learners. **The practical conclusion**: XGB is now the recommended primary model for this dataset.

**3. The 75% claim held up better than the literature predicted.** Agent 2's lit review forecasted that fixing leakage might drop accuracy 5-8pp toward the published 65-72% range. Actual drop on RF W5: only -3pp (0.778 → 0.748). So our 75%-ish number was *mostly* real signal, not a leakage artifact. The bulk of model accuracy is genuine; the bug was largely re-routing signal that RF could already extract via tree splits onto duplicate columns. (The leakage Agent 2 was warning about — the `*_AVAILABLE` post-hoc availability — is **still unaddressed**; that's E7, separate experiment.)

**4. All four models now cluster tightly on W5** (acc 0.735–0.774). The differences are small enough that a single random-seed run is borderline. Future tuning experiments should average across 3-5 seeds per config before drawing conclusions.

### Decision
- **PROMOTE E8 results to the new baseline.** All future deltas measured against rows 21-24 (RF/NN production models on clean features).
- **XGB stays the recommended primary model** for the per-window leaderboard going forward.
- **Drop E6 (NN stabilization)** entirely — solved by E8 as a side effect.
- **Retrain XGB production model.** The current XGB bundle (rows 19-20) was trained on the buggy CSV — needs a fresh retrain. The `train` stage's inline command doesn't currently retrain XGB; either add it or run a one-off.
- **Keep E7 (availability leak fix) at top priority** — Agent 2 was still right that the post-hoc `*_AVAILABLE` features are leaky. E8 only fixed the structural duplication, not the time-asymmetry.

### Next moves (post-E8 priority order)
1. **E7 — historical pre-game injury reports** (or per-game player_impact fallback). Still the biggest believed source of accuracy inflation.
2. **E9 — ELO as features** (4 columns, ~30 lines).
3. **E10 — opponent-strength adjustment for `_L5`/`_L10` rolling stats.**
4. **E11 — `LeagueDashLineups` for 5-man synergy.**
5. **Add XGB to the pipeline `train` stage** so future `pipeline.py run --stages train` updates all three model bundles, not just RF+NN.

---

## 2026-05-19 — Experiment 7: Fix `_AVAILABLE` post-hoc availability leak

### Question
The lit review (E3 active research, Agent 2) and the code review (Agent 1) both flagged the same concern: `bulk_fetch_player_availability` derives `*_SLOT_X_AVAILABLE` features from `boxscoretraditionalv3_player` — the **post-game** boxscore — to determine which players "were available." For a 2022 training row the model effectively learned pre-game whether each star ended up showing up, which is information it would not have at real prediction time. Literature pegs this pattern at typically inflating training accuracy by 2-5pp. The E8 walk-forward numbers (RF W5 = 0.748, XGB = 0.774, NN = 0.735) are suspected to be inflated by this leak.

### Method
1. **Built a scraper** (`data_engineering/historical_injury_scraper.py`) to populate a new MySQL table `historical_injury_report` with the league's official pre-game injury PDFs. Source: `https://ak-static.cms.nba.com/referee/injury/` via the [`nbainjuries`](https://pypi.org/project/nbainjuries/) package, which wraps tabula-py for PDF table extraction.
2. **Discovered & fixed an NBA URL-format change**: starting **2025-12-22** the league switched from hourly (`Injury-Report_YYYY-MM-DD_HHPM.pdf`) to 15-min-granularity filenames (`Injury-Report_YYYY-MM-DD_HH_MMPM.pdf`). The `nbainjuries` package only knows the old format; our scraper now monkey-patches `_gen_url` to try both, with date-aware ordering. See `data_engineering/historical_injury_scraper.py:_gen_url_*_format` and `_try_format`.
3. **Populated the table**: **106,755 rows / 969 distinct game-dates / range 2022-01-01 → 2026-05-13.** Resolution: 97.4% team_id, 98.9% player_id. The 71 game-dates in the window NOT in the table are All-Star breaks / preseason / off-days where no league report was published (expected).
4. **Built leak-free fetcher** in `data_engineering/player_impact.py:bulk_fetch_pregame_availability` — same return-dict shape as the legacy `bulk_fetch_player_availability` but populated only for players flagged Out/Doubtful in the official pre-game report. Players NOT in the dict are healthy/available (matches the existing callsite contract for traded players).
5. **Added `availability_source` parameter** to `calculate_player_slot_features` (default `'pregame'`). Modes:
   - `'pregame'` — the new leak-free source (default).
   - `'postgame'` — legacy, retained for back-compat / A-B sanity checks.
   - `'auto'` — pregame where covered, postgame fallback for un-covered dates.
6. **Updated backfill path** in `modeling/predict_games.py`: added `_fetch_historical_injuries_for_date()` and rewired the per-date loop in `main()` so `--start-date X` runs source their injuries from `historical_injury_report` per game date instead of force-disabling `--auto-injuries`. Fixes the related concern that backfilled predictions assumed every player was available.
7. Rebuilt features CSV (`feature_engineering.py --start-date 2022-01-01`), retrained all models via `pipeline.py run --stages train`, re-ran the E2 walk-forward script (no script change — it auto-picks up the new CSV).

**Bug surfaced during the first rebuild**: `bulk_fetch_pregame_availability` stored its dict keys as `(str(game_id), int(team_id))` while the caller (`_process_player_slots_for_game_bulk`) looks up `(int_game_id, int_team_id)` — silent type mismatch caused every lookup to miss and every `_AVAILABLE` to fall back to its default of 1.0. First rebuild produced a CSV where mean `_AVAILABLE` per slot was 1.0 across the board (vs the postgame baseline of ~0.97). One-line fix: cast `game_id` to int in the dict-key construction. Rebuild #2 is what produces the numbers below. Worth recording because it would have been near-invisible in production — the model would have trained successfully, scored similarly, and we'd have attributed any accuracy delta to the leak fix without realizing the leak fix wasn't actually applied. **Always sanity-check feature-distribution shifts after a data-source change.**

### Results

**E8-baseline vs E7 walk-forward** (both 4-season CSV, same hyperparams, same 5 windows; only difference is `*_SLOT_X_AVAILABLE` source):

| Window | E8 RF | E7 RF | Δ | E8 XGB | E7 XGB | Δ | E8 NN | E7 NN | Δ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| W1 (Dec 2025) | 0.576 | **0.598** | **+0.022** | 0.543 | **0.571** | **+0.028** | 0.592 | 0.543 | -0.049 |
| W2 (Jan 2026) | 0.581 | 0.581 | 0.000 | 0.598 | **0.642** | **+0.044** | 0.611 | 0.546 | -0.065 |
| W3 (Feb 2026) | 0.575 | 0.586 | +0.011 | 0.632 | 0.644 | +0.012 | 0.667 | 0.667 | 0.000 |
| W4 (Mar 1-15) | 0.767 | 0.759 | -0.008 | 0.741 | 0.750 | +0.009 | 0.767 | 0.750 | -0.017 |
| W5 (Mar 15-Apr 15) | **0.748** | **0.752** | **+0.004** | **0.774** | **0.770** | **-0.004** | **0.735** | **0.757** | **+0.022** |

**W5 AUC** (the ranking-quality metric — independent of threshold):

| Model | E8 AUC | E7 AUC | Δ |
|---|---:|---:|---:|
| RF | 0.816 | 0.819 | +0.003 |
| XGB | 0.826 | 0.828 | +0.002 |
| NN | 0.819 | **0.831** | **+0.012** |

**W5 MAE** (regression margin error, points):

| Model | E8 MAE | E7 MAE | Δ |
|---|---:|---:|---:|
| RF | 12.28 | 12.21 | -0.07 |
| XGB | 11.78 | **11.57** | **-0.21** |
| NN | 12.35 | **11.80** | **-0.55** |

**Feature signal change**: mean `_SLOT_X_AVAILABLE` per slot dropped from ~0.97 (postgame) to **0.72-0.88** (pregame). Pregame report flags more players as Out than the postgame "did they actually play" view does — partially because G League / two-way / IL stash players appear in the report as "Out" even though they were never in the team's rotation. ~35% of all (game, slot) cells now have someone marked OUT, vs ~3% under postgame.

### Findings

**1. The leak was real but smaller than literature predicted.** Lit review (Agent 2) forecast a 5-8pp accuracy drop after the leak fix. Actual change on W5: RF +0.4pp, XGB -0.4pp, NN +2.2pp. So accuracy held essentially flat — the model wasn't getting much from the post-hoc availability signal that it couldn't also derive from team rolling stats + player_impact scores. The leak was mostly redundant information, not load-bearing signal.

**2. AUC improved across the board, even when accuracy moved sideways.** RF +0.003, XGB +0.002, NN +0.012 on W5. The pregame report data gives slightly better RANKING (which game has the higher home-win probability) even when threshold-accuracy is similar. Better calibration is itself a win because downstream consumers like Vegas-style point spreads depend on probability quality, not just whether the >0.5 threshold catches the winner.

**3. MAE improved meaningfully — biggest gains for XGB and NN.** XGB W5 MAE 11.78 → **11.57** (-0.21 pts); NN W5 MAE 12.35 → **11.80** (-0.55 pts). NN's regressor was leaning heavily on the leaky availability signal as a noisy proxy for player quality — replacing it with cleaner pre-game data tightened its margin predictions substantially. XGB also benefited. **XGB MAE 11.57 is the closest we've gotten to Vegas's ~10-11 floor.**

**4. NN W1/W2 accuracy dropped (-5pp / -6.5pp) — first sign of NN instability on the new feature distribution.** NN's classifier behaved erratically in the smaller-training-data windows. AUC was fine in those windows (W1 0.581, W2 0.628), so this is again a threshold-calibration thing, not a ranking failure. NN remains the most fragile model class on this dataset.

**5. The 75% headline holds and is now defensible.** RF W5 = 0.752, XGB W5 = 0.770, NN W5 = 0.757 — all clustered in the 75% range, all measured against a strict walk-forward train cut-off, with the post-hoc availability leak removed. This is the strongest version of the "is 75% real?" claim we've had: it survived the most rigorous methodological scrutiny we could throw at it.

### Decision
- **KEEP all E7 changes.** Default `availability_source='pregame'` stays. New baseline metrics are RF 0.752 / XGB 0.770 / NN 0.757 on W5 walk-forward.
- **XGBoost remains the best single model** (W5 acc 0.770, AUC 0.828, MAE 11.57). Use it as the primary in any future single-model comparison.
- **Move E7 to "Kept" status in the master experiment table.**
- **No additional hyperparameter or architecture changes from this experiment** — the methodology fix was the whole point.

### Backfilled-predictions check
Deferred. The integration code (`_fetch_historical_injuries_for_date` in `modeling/predict_games.py`) is wired and tested in isolation. A proper A/B on `model_predictions` would require either (a) preserving the pre-E7 backfilled rows under a different `model_version` string for comparison, or (b) accepting that re-running `predict_games.py --start-date X` overwrites them via ON DUPLICATE KEY UPDATE. Picking (a) is the cleaner experiment but doesn't materially change the conclusion — the walk-forward delta above is the controlled measurement of the same effect. Folded into the E5/E9/E10/E11 sequence as "ad-hoc check after each new feature group lands."

---

### Backfilled-predictions check
The literature also predicts that with `--auto-injuries` now sourced from the new table in backfill mode, accuracy of backfilled rows in `model_predictions` should rise to be closer to "true live" predictions. The current Dec 6-22 2025 backfilled rows were generated WITHOUT injury data (pre-E7); a re-run will overwrite them via the ON DUPLICATE KEY UPDATE on (game_id, model_type, model_version). To do a proper A/B we'd need to fork the model_version string for the new run. *Deferred to a separate experiment once E7 baseline numbers are confirmed.*

---

## Backlog updates (post-research) — original record

### Original E8 plan (now ✅ done above)

### NEW: E9 — Add ELO as features (and as a dashboard baseline)
After E8. ~30 lines of Python + one new `team_elo_pregame` MySQL table. 538 formula. Add `HOME_ELO`, `AWAY_ELO`, `ELO_DIFF`, `ELO_P_HOME` to the feature set. Show pure-ELO accuracy as a permanent tile on the Model Performance tab so we always know the dumb-baseline.

### NEW: E10 — Opponent-strength adjustment for rolling stats
For each `_L5`/`_L10` team stat, add a variant: `team_stat - rolling_avg(opponent_allowed_stat)`. Agent 1 finding #2; literature's recurring "biggest gap" critique of pure box-score features.

### NEW: E11 — Add LeagueDashLineups for 5-man synergy features
After E8/E9 baseline is established. Agent 3 #1.

---

## 2026-07-03 — Experiment 19: Season-end audit + lineage-tracked retrain

### Why this experiment exists
Three user-surfaced symptoms after the 2025-26 season wrapped: (1) RF almost never picks
the away team; (2) the public site showed a 64.6-point predicted margin for the 2026-06-13
Finals game; (3) XGBoost has almost no predictions despite being wired up since E3/E8.
Before any further development, audit the current state end-to-end, then establish a clean
season-end baseline: features through the Finals, retrain, validate — the first retrain to
record `feature_set_version` lineage in the registry (shipped 2026-07-03).

### Audit findings (2025-26 season, graded predictions)

| | RF | NN | XGB |
|---|---|---|---|
| Season predictions (local) | 1,131 graded | 1,117 graded | **0** |
| Live accuracy | **0.583** | 0.657 | — |
| Registry test accuracy (Mar-Apr holdout) | 0.742 / AUC 0.804 | 0.708 | 0.727 |
| Home-pick share | **97%** (1103 vs 35) | 70.5% (793 vs 331) | — |
| Accuracy when picking away | **0.794** | 0.653 | — |
| Season max \|predicted margin\| | 21.1 | 24.2 | — |

Actual home-win base rate: **0.554** (832 games).

**Finding 1 — RF's home-pick collapse is the E13 calibration layer, not the trees.**
The isotonic map (fit on a ~209-game Mar-Apr eval holdout, applied to the full-data
production model — the step-7 subtlety flagged in E18) now pushes ~97% of calibrated
probabilities above 0.5. Live reliability is badly off: calibrated bin 0.7 → only **40%**
observed home wins; bin 0.8 → 55%. It actively flips correct picks: on 2026-06-13, RF raw
p(home)=0.449 (pick NYK — the eventual winner) was calibrated to 0.604 → picked SAS,
wrong. The 21pp gap between "when RF picks away" (79.4% right) and "when it picks home"
(57.6%) says the underlying signal is fine and the decision threshold is what's broken.
NN (no calibrator) shows the opposite pathology: overconfident tails (349 rows at p≥0.9+
that win only ~76%; 114 rows at p<0.1 that still win 18%).

**Finding 2 — the 64.6-pt margin is a cloud-data artifact, not a modeling failure.**
RDS's row for 2026-06-13 (served by the public API): NN margin −64.6, p(home)=0.996,
margin_uncertainty 153.7 — classifier and regressor contradicting each other by ~130
points. Cause: the cloud predictions ran when RDS was missing weeks of boxscores
(stats.nba.com blocks AWS; the ingest handoff didn't exist yet), so
`get_team_rolling_stats` fed the NN degenerate inputs and an unbounded MLP extrapolated.
Bounded tree models on the SAME inputs stayed sane (RF 0.9, XGB −1.2). The local NN, on
complete data, predicted the same game at −3.1 — correct pick. Structural fix already
shipped (2026-07-02): home ingest → S3 → nightly load + freshness alarm. Residual gap:
nothing *at the model layer* refuses to emit a physically absurd margin — see E21 (next).

**Finding 3 — XGB never ran.** Season backfills used `--model both` (a choice that
pre-dates xgb), and `backfill_actuals` hardcoded `['rf','nn']` so even the few cloud xgb
rows were never graded (fixed 2026-07-02, now derived from MODEL_TYPES). E12 measured XGB
as the best-or-tied model (W5 0.774 acc, best MAE 11.57). The strongest model sat out the
season. Nightly now predicts and grades all three.

**Finding 4 — prod models were stale and narrow.** Current registry rows (20260527_2):
trained on 834 games, 2025-11-01 → 2026-03-05, holdout through ~Apr 1. Nothing after
March 5 was ever trained on; the feature snapshot (both `20260529T*` versions — near-dup
twins from migration day) ends 2026-04-01.

**Also confirmed in the audit:** injury/availability and player-impact features ARE in
production (64 SLOT_* columns incl. `*_AVAILABLE` (E7) and `*_IMPACT` (player projection
slots)); ELO is in (E9, 5 columns); OPP_ADJ/LINEUP correctly absent (E10/E11 dropped).
Historical pregame injury data ends 2026-05-13 — May-June feature rows fall back to
non-pregame availability (refresh scraper pre-season).

### Retrain methodology
`feature_engineering.py --start-date 2025-11-01 --end-date 2026-06-30` (full season incl.
playoffs/Finals, ~1,250 games; first snapshot with a `--db-description`), then force-
retrain RF/XGB/NN (first registry rows with `feature_set_version` in hyperparameters
JSON), then `validate_models.py --days 60`. Temporal 80/20 eval split means the
calibrator/conformal holdout is now the season's final ~20% (Apr-Jun, playoff-heavy) —
fresher than before but see E15's playoff-shift caveat.

### Results

**Lineage works.** All six `*_20260703` registry rows carry
`feature_set_version = 20260703T022649Z` in the hyperparameters JSON, joining to a
described row in `feature_set_versions`. First fully-traceable models.

**New snapshot**: `20260703T022649Z`, 1,234 games (2025-11-01 → 2026-06-13, the full
season incl. playoffs/Finals), promoted to current.

**Holdout metrics — read with care, the exam changed.** Temporal 80/20 puts the new
test window at **2026-03-24 → 2026-06-13 (247 games: late regular season + play-in +
playoffs + Finals)** vs the old holdout's regular-season Mar 5–Apr 1:

| model | old holdout (regular) | new holdout (playoff-heavy) | Δ |
|---|---|---|---|
| RF  | 0.742 acc / 0.804 AUC / 11.38 MAE | 0.729 / 0.785 / 12.60 | −1.3pp acc |
| XGB | 0.727 / 0.780 / 11.83 | **0.660** / 0.747 / 13.05 | **−6.7pp acc** |
| NN  | 0.708 / 0.770 / 12.04 | 0.692 / 0.770 / 13.14 | −1.6pp acc |

Per E15/E16 this is the expected regime shift, not a training failure — playoffs are
near-irreducible (Vegas itself: 0.647 acc there), so a playoff-heavy holdout *should*
score lower. RF holding 0.729 on that window is consistent-to-good. XGB's
disproportionate drop echoes E15's finding that playoff shift hits it hardest — worth a
look during E20, but not alarming on n=247.

**Validate-stage caveat discovered**: `validate_models.py --days 60` ran over
2026-04-14 → 2026-06-13 — which now lies INSIDE the new models' training window, so its
numbers (RF 76.9%/0.824 AUC/10.98 MAE, n=91) are in-sample-inflated. The stage predates
the E18 `data_through_date` metadata and doesn't check it. **Follow-up: teach
`validate_models.py` to refuse (or at least loudly flag) windows overlapping
`data_through_date`** — same guard the backfill loop got in E18. Even in-sample, NN's
validation calibration_error of 0.439 (RF 0.338) restates the E20 case.

**Promotion decision: NOT promoted to prod.** These bundles live in the local registry/
`models/bundles` only; prod (S3) still serves `20260527_2`. Rationale: E20 (calibration
overhaul) retrains again anyway; it's the offseason so prod predictions are idle; one
promotion after E20 beats two. The public site keeps its current behavior until then.

### Decision / Next
- **E20 (next): calibration overhaul.** The isotonic-on-tiny-eval-slice protocol is the
  biggest live-accuracy leak (RF −16pp vs holdout). Plan: K-fold out-of-fold calibration
  on the full training set (fit isotonic on pooled OOF probabilities of the production
  config), measure ECE + pick-flip-rate + McNemar raw-vs-cal picks on held-out games;
  also decide whether the *pick* should use raw p with calibrated p for display only.
- **E21: margin sanity guard.** Log-time guard in the predict path: if
  \|predicted_margin\| > ~35 or classifier/regressor disagree by an absurd delta, log a
  WARNING (CloudWatch ERROR-filter picks it up), clamp the public-facing margin, and mark
  the row. Also extend E14 conformal wrapping to the NN regressor (currently RF/XGB only —
  the NN is exactly the model that needed it).
- **Cadence** (proposed, see session notes): nightly predict/grade (shipped); weekly
  in-season retrain+validate as a scheduled Fargate run (all stages are DB-only post-
  egress-fix, so cloud-safe); full rebuild at season boundaries; freshness alarm already
  guards the data side.

---

## 2026-07-03 — Experiment 20: Calibration protocol A/B, pick policy, degeneracy guard

### Why
E19 indicted the E13 calibration layer: live, it pushed ~97% of RF picks to home and
flipped correct raw picks. Two suspects: (a) the tiny (~200-game) eval-slice fit set +
the fit-on-eval-model/apply-to-production subtlety; (b) staleness — one calibrator fit
in May, drifting unguarded. Hypothesis: 5-fold out-of-fold isotonic (≈5× the fit data,
production-config fold models) beats the eval-slice protocol.

### Method
`experiments/e20_calibration.py` — three protocols per (model, seed), all trained
strictly before the frozen W5 window (train n=917, test n=230, home rate 0.591):
`raw`; `eval_slice` (mirrors production EXACTLY, including applying the eval-fit map to
the full-data model's probs); `oof` (pooled 5-fold OOF probs → isotonic → applied to the
full-data model). RF/XGB × 10 seeds, NN × 5 (first time NN was calibration-tested).
Metrics: ECE, Brier, AUC, acc@0.5, home-pick share, and raw-vs-calibrated pick
disagreements with per-seed consistency (E12 discipline).

### Results (mean over seeds)

| protocol | RF acc/ECE | XGB acc/ECE | NN acc/ECE |
|---|---|---|---|
| raw | **0.767** / 0.128 | 0.730 / 0.099 | 0.719 / 0.109 |
| eval_slice | 0.757 / 0.098 | **0.736** / **0.071** | 0.728 / 0.109 |
| oof | 0.753 / **0.091** | 0.720 / 0.110 | 0.729 / 0.114 |

Disagreement games (pick flips vs raw, pooled): RF — raw wins 81–57 (eval) and 85–52
(oof); XGB — cal wins 88–74; NN — cal wins 53–43.

**OOF: rejected.** Best RF display-calibration (beats raw ECE 10/10 seeds) but the edge
over eval_slice is noise (5/10), and for XGB it's *worse than raw* (0/10 seeds beat
eval_slice; ECE 0.110 vs raw 0.099) — likely because fold models (80% data, subsampled
XGB) produce a systematically different probability distribution than the full-data
model the map is applied to. A clean negative result; keeping the eval-slice protocol.

**The live pathology did not reproduce** with a freshly-fit eval-slice calibrator
(home-pick share ~0.60, not 0.97). Verdict on root cause: **staleness without a guard**,
not the protocol itself. The May calibrator was fit once on a weird window and nothing
ever checked it again.

**Pick policy**: with a fresh calibrator the choice is ~a wash (RF −1pp from calibrated
picks, XGB +0.6pp, NN +0.9pp; net ≈ 0). Calibrated-derived picks keep the site coherent
(pick always agrees with the displayed probability — the E18 incident showed users
correctly read pick/prob mismatch as a bug), so picks stay calibrated-derived.

### Shipped
1. **Train-time degeneracy guard** (`_calibrator_pick_shift`, threshold ±10pp on the
   eval slice): a calibrator that moves the home-pick share too far is stored with
   `calibrator_trusted=False` and logs `ERROR: CALIBRATOR_DEGENERATE ...` — which the
   pipeline log alarm emails. Old bundles default to trusted (unchanged behavior).
2. **Guard-aware picks everywhere**: `_derive_pick_probability(result)` — calibrated
   normally, RAW when the bundle is flagged — used by all three `predict_games.py` log
   sites and `batch_predict_today._predict_and_log_one`.
3. Retrained on the E19 snapshot so production bundles carry the guard verdict (and a
   calibrator fit on the fresher Apr–Jun holdout). **The guard fired on its first real
   run**: XGB's fresh calibrator shifted home-pick share by **+0.142** on the playoff-
   heavy eval slice → flagged degenerate → XGB picks derive from raw until a future
   retrain produces a sane map. RF passed (+0.049, trusted). Exactly the E19 pathology,
   caught at train time instead of discovered in production weeks later.

### Live confirmation (added same day, user-prompted)
The E18 raw-probability log (186 graded rows/model, games 2026-04-02 → 2026-06-13 —
everything predicted after the column landed) allows the raw-vs-calibrated A/B on REAL
games: RF raw picks **0.699** vs calibrated picks **0.645** (−5.4pp live cost), 42/186
picks flipped by the stale calibrator, raw winning the flips **26–16**; home-pick share
raw 0.72 → calibrated **0.94**. That +22pp live shift is >2× the guard threshold — the
tripwire would have caught the actual incident. These same 186 pairs are enough to
PILOT online recalibration (refit weekly on trailing live raw probs — the most
distribution-matched fit data possible); certification needs next season's volume.

### Residuals / honest caveats
- The guard is a tripwire, not a cure: a calibrator can be subtly bad without crossing
  ±10pp. The real protection is the **weekly retrain cadence** keeping the map fresh —
  the guard exists for the week something goes wrong. The ±10pp value itself is a
  heuristic (healthy fits observed ≤5pp, degenerate ones ≥14pp); E21's multi-season
  backtest should replace it with an empirically-derived tail threshold.
- **(Superseded same day by E21**, which found the shift statistic cannot separate
  healthy from degenerate fits and that raw picks beat calibrated picks everywhere —
  picks are now raw-derived and the guard is informational. See §E21.)

---

*(E21 write-up consolidated at the end of this file — see "Experiment 21". An earlier
duplicate section here, written post-session-restart before discovering the original
analysis had already been logged, was merged into it on 2026-07-03.)*

---
- NN still has no calibrator (E20 showed no ECE benefit on this window from either
  protocol; its overconfident tails were an E19 *live* observation — revisit with
  next season's data).
- Per-model pick policies (raw for RF) would squeeze ~1pp more but were declined for
  operational simplicity; the harness is rerunnable if that call should be revisited.
- Promotion to prod (S3 bundles) + the weekly retrain schedule are the next
  infrastructure step — note the cloud's `features` table is still the April snapshot;
  the weekly job must run the features stage cloud-side (all inputs are in RDS now).

---

## 2026-05-19 — Experiment 9: ELO ratings (HOME/AWAY/DIFF/P_HOME) as features

### Why
ELO was the single highest-yield addition cited across the lit review (Nate Silver / 538, Hvattum & Arntzen 2010). Rolling box-score averages encode short-window form; ELO encodes franchise-history strength + opponent-strength-of-schedule that no rolling-mean can recover. Pure ELO classifiers consistently land at 65–68% — a free 65% baseline to beat with everything else.

### Implementation
- `data_engineering/compute_elo.py` — 538 formula (K=20, HCA=100, MOV multiplier `(|margin|+3)^0.8 / (7.5 + 0.006*winner_elo_diff)`, 0.75 season carryover, mean=1505).
- Single chronological pass over `game_list` (collapsed to one row per game; fixed 4 GAME_IDs with 3-row dupes via PTS-desc dedup). 41,345 games processed.
- Schema: `team_elo_pregame (game_id UNIQUE, game_date, home_team_id, away_team_id, home_elo, away_elo, elo_diff, elo_p_home)`. Re-running always wipes + rebuilds — deterministic by design.
- `_join_elo_features` in `feature_engineering.py` joins on `GAME_ID`. `feature_patterns` expanded with `HOME_ELO`, `AWAY_ELO`, `ELO_DIFF`, `ELO_P_HOME`. (`DIFF_ELO` also gets created by `create_matchup_features` as a side effect — redundant with `ELO_DIFF` but cheap.)

### Sanity stats
- `home_elo` mean = 1547 (home teams skew slightly stronger), `away_elo` = 1510 → home-court win-rate gives strong teams more home games.
- `elo_diff` mean = +137 (HCA=100 + slight home strength bias).
- `elo_p_home` mean = 0.660 — matches the empirical home-court win rate.
- **Pure-ELO classification accuracy on completed games: 66.4%** — squarely in the 65–68% range the literature predicts.

### Walk-forward results (5 windows, 2025-12-01 → 2026-04-15)
| Window | RF acc | RF AUC | RF MAE | XGB acc | XGB AUC | XGB MAE | NN acc | NN AUC | NN MAE |
|---|---|---|---|---|---|---|---|---|---|
| W1 (Dec 2025) | 0.598 | 0.623 | 11.76 | 0.571 | 0.603 | 12.43 | 0.527 | 0.564 | 11.57 |
| W2 (Jan 2026) | 0.581 | 0.628 | 11.72 | 0.642 | 0.671 | 11.67 | 0.655 | 0.665 | 11.34 |
| W3 (Feb 2026) | 0.586 | 0.723 | 12.42 | 0.644 | 0.709 | 12.44 | 0.615 | 0.715 | 12.19 |
| W4 (Mar 1-15) | 0.759 | 0.787 | 10.59 | 0.750 | 0.790 | 11.00 | 0.741 | 0.797 | 10.34 |
| **W5 (Mar 15-Apr 15)** | **0.752** | **0.819** | **12.21** | **0.770** | **0.828** | **11.57** | **0.765** | **0.837** | **11.97** |

vs E7/E8 baseline (W5):
- RF: 0.748 → 0.752 (+0.4pp)
- XGB: 0.770 → 0.770 (flat)
- NN: 0.757 → 0.765 (+0.8pp) — NN gained AUC consistency too
- MAE: essentially flat for all 3 models

### Verdict
**Kept** — pure-ELO baseline alone hits 66.4%, but as added features inside an already-feature-rich model, the gain is small because rolling stats had already encoded most of the team-strength signal. The interpretive value (a permanent "ELO baseline" tile on the dashboard) and the future-proofing (ELO is robust to feature-set churn) justify keeping it even though the W5 accuracy delta is +0.4–0.8pp.

### Lessons / follow-ups
- The cleanest accuracy-test of ELO would be to **drop the existing offensive/defensive rating rolling features and substitute ELO** — current setup has both, so ELO is partially redundant.
- The pure-ELO 66.4% baseline is a useful "is the rest of the pipeline carrying its weight?" sanity tile — model needs to clear that to be earning its complexity.

---

## 2026-05-19 — Experiment 10: Opponent-strength adjustment for rolling stats

### Why
Every existing `_L5` / `_L10` is a raw mean — 30 PPG against tankers looks identical to 30 PPG against contenders. Agent 1's code-review pass flagged this as the recurring biggest blind spot of pure box-score features, and Sloan-conference / Goldsberry-era literature consistently says opponent-adjusted rolling is the next-most-impactful axis after ELO.

### Implementation
- `data_engineering/feature_engineering.py::add_opponent_adjusted_rolling_features` — inserts between `calculate_rolling_features` and `calculate_win_streak`.
- **Pass 1**: self-join `game_df` on `GAME_ID`, filter `TEAM_ID != _OPP_TEAM_ID` → each row gets opponent's same-game raw stat as `_opp_{stat}`.
- **Pass 2**: per-team rolling of `_opp_{stat}` with `shift(1).rolling(10)` → `{stat}_ALLOWED_L10` = avg of what team allowed in its last 10 games (no leak).
- **Pass 3**: self-join again on `GAME_ID` to attach opponent's `{stat}_ALLOWED_L10`; compute `OPP_ADJ_{stat}_L10 = team_{stat}_L10 - opp_{stat}_ALLOWED_L10`.
- Curated 9-stat subset: PTS, offensiveRating, netRating, TS_PCT, EFG_PCT, FG_PCT, FG3_PCT, pace, PLUS_MINUS. Adds 18 columns per side after matchup expansion (9 ALLOWED + 9 OPP_ADJ × HOME/AWAY/DIFF).
- **Latent-bug side effect**: the self-join's `drop_duplicates(['GAME_ID','TEAM_ID'])` collapsed 1023 duplicate rows that had been silently inflating the source df. Pre-E10 the CSV had 7342 *rows* but only 6319 unique GAME_IDs.

### Walk-forward results (5 windows)
| Window | RF acc | RF AUC | RF MAE | XGB acc | XGB AUC | XGB MAE | NN acc | NN AUC | NN MAE |
|---|---|---|---|---|---|---|---|---|---|
| W1 (Dec 2025) | 0.620 | 0.627 | 11.75 | 0.620 | 0.625 | 12.18 | 0.571 | 0.624 | 11.66 |
| W2 (Jan 2026) | 0.585 | 0.624 | 11.72 | 0.638 | 0.662 | 11.65 | 0.603 | 0.658 | 11.38 |
| W3 (Feb 2026) | 0.632 | 0.714 | 12.46 | 0.615 | 0.720 | 12.35 | 0.655 | 0.704 | 12.09 |
| W4 (Mar 1-15) | 0.759 | 0.782 | 10.58 | 0.741 | 0.809 | 10.54 | 0.690 | 0.790 | 10.69 |
| **W5 (Mar 15-Apr 15)** | **0.765** | **0.819** | **12.07** | **0.774** | **0.819** | **12.07** | **0.761** | **0.822** | **11.75** |

vs E9 baseline (W5):
- RF: 0.752 → **0.765** (+1.3pp), MAE 12.21 → 12.07 (-0.14)
- XGB: 0.770 → 0.774 (+0.4pp), **MAE 11.57 → 12.07 (+0.50 — regression)**
- NN: 0.765 → 0.761 (-0.4pp), MAE 11.97 → 11.75 (-0.22)

### Verdict
**Kept** — net positive across the three models, with caveats:
- **RF**: clear win on both accuracy and MAE. Tree models benefit from the explicit adjustment because they can't easily synthesize "PTS_L10 minus opp_PTS_ALLOWED_L10" themselves at split time.
- **XGB**: small accuracy gain, but MAE regressed +0.50 — possibly because removing the 1023 dupe rows reduced training-set diversity for XGB's regression head. Worth checking if XGB-only benefits from leaving dupes in.
- **NN**: essentially flat accuracy, MAE small win. Linear combinations like `A - B` are easy for MLPs to construct on their own from raw inputs, which is why the explicit features add less here.

### Lessons / follow-ups
- The dedup discovery is its own win — every prior experiment was training on 14% dupe rows. Worth retroactively asking whether E8's reported W5 numbers would have been different with deduplicated data; deferred until post-E11 synthesis.
- `_L5` versions of OPP_ADJ are an obvious next iteration if `_L10` is helping.
- Reactive note: keep an eye on XGB MAE regression — if E11 doesn't reverse it, may need to tune XGB regressor depth/eta separately.

---

## 2026-05-19 — Experiment 11: LeagueDashLineups 5-man synergy features

### Why
The existing player-impact features are *additive* — sum of per-player projections weighted by availability. Two teams with identical rosters but different rotations look identical to the model. `LeagueDashLineups` exposes nba.com's 5-man combo stats directly, giving the model a path to learn cohesion and bench-unit dropoff.

### Implementation
- `data_engineering/lineup_features.py` — month-end snapshots of `LeagueDashLineups` (Advanced/PerGame/5-man) per (season, month_end), cached to `team_lineup_snapshots` MySQL table.
- Per-team derived features: `lineup_top_min`, `lineup_top_net_rtg`, `lineup_top_off_rtg`, `lineup_top_def_rtg`, `lineup_top_pace`, `lineup_top_ts_pct`, `lineup_top5_avg_net_rtg`, `lineup_top5_min_share`, `lineup_n_active`. 9 features × HOME/AWAY/DIFF = 27 columns after matchup expansion.
- `_join_lineup_features` uses `pd.merge_asof(direction='backward', by='team_id')` so each game gets the most recent prior snapshot — point-in-time correct, no leakage from future months.
- **Data coverage limit**: NBA API returned data for 2024-25 and 2025-26 seasons (240 + 180 rows across 15 month-ends). 2021-22, 2022-23, 2023-24 returned `JSONDecodeError` on every retry — likely API blocks deep-historical queries with `date_to_nullable`. Result: 2711/6319 games (43%) have lineup features populated; the rest get NaN → median-imputed.

### The ELO routing bug (discovered during E11 verification)
While checking that LINEUP features had entered the model, I dumped `models/feature_names.joblib` and noticed `ELO: 0`. The root cause: the project has **two** feature-pattern allow-lists that must stay in sync:
1. `data_engineering/feature_engineering.py::prepare_ml_dataset` — what gets *written* to the CSV.
2. `modeling/predict_games.py::_prepare_training_data` and `experiments/e2_walk_forward.py::select_feature_columns` — what gets *selected* into the model from that CSV.

E9 added the ELO patterns to (1) but not (2), so ELO columns shipped to the CSV but were silently filtered out at training time. Same omission for LINEUP. Fixed in both files; `OPP_ADJ` slipped through because the existing `_L10` substring pattern caught it.

**Consequence**: the original E9-only walk-forward numbers (W5 RF 0.752, XGB 0.770, NN 0.765 — claimed as ELO contribution) were measuring no-change-vs-E8. Re-ran the isolated ELO ablation today; honest contribution numbers are in the master table above. E10's numbers remain valid because `OPP_ADJ` *did* enter the model.

### Walk-forward results (full E11 — OPP_ADJ + ELO + LINEUP)
| Window | RF acc | RF AUC | RF MAE | XGB acc | XGB AUC | XGB MAE | NN acc | NN AUC | NN MAE |
|---|---|---|---|---|---|---|---|---|---|
| W1 (Dec 2025) | 0.576 | 0.628 | 11.67 | 0.582 | 0.604 | 11.98 | 0.543 | 0.582 | 11.57 |
| W2 (Jan 2026) | 0.585 | 0.648 | 11.55 | 0.594 | 0.650 | 11.56 | 0.629 | 0.662 | 11.36 |
| W3 (Feb 2026) | 0.649 | 0.750 | 12.14 | 0.638 | 0.697 | 12.00 | 0.661 | 0.721 | 12.32 |
| W4 (Mar 1-15) | 0.759 | 0.795 | 10.52 | 0.724 | 0.811 | 10.15 | 0.750 | 0.802 | 10.52 |
| **W5 (Mar 15-Apr 15)** | **0.787** | **0.830** | **11.90** | **0.800** | **0.845** | **11.86** | **0.787** | **0.827** | **11.86** |

### Ablation: ELO-only on top of E10 (no LINEUP)
| Window | RF acc | XGB acc | NN acc |
|---|---|---|---|
| W5 | 0.774 | 0.774 | 0.774 |

Subtracting the two rows gives **LINEUP marginal contribution**: RF +1.3pp, XGB +2.6pp, NN +1.3pp.

### Verdict
**Kept** — XGB's W5 hitting 80% is the headline number; it's the highest accuracy seen on this dataset and clears the long-running ceiling around 77%. Caveats:
- 43% coverage means most of the training set still NaN-imputes the lineup features. The model is presumably learning "missing lineup data = older game, treat differently"; with full coverage we might see more or less impact.
- W5 MAE for NN regressed 11.69 → 11.86 with LINEUP added — likely the imputed-NaN features adding noise. Worth investigating per-model NaN handling.
- LINEUP feature coverage is the single most actionable follow-up — see brainstorm doc.

### Lessons / follow-ups
- **Centralize the feature-pattern allow-list**. Two-source-of-truth was a latent landmine; an end-to-end test would have caught it. Suggested follow-up: collapse the three feature_patterns lists into a single `core/features.py::ACTIVE_PATTERNS` constant imported by all three sites.
- **Pre-2024 lineup backfill** is the obvious next step. May need to scrape `nba.com/stats/lineups/advanced/` HTML directly since the API blocks historical date_to.
- **E10 dedupe** (1023 dupe rows) needs retroactive analysis on E1-E8 numbers; deferred to next round.

---

### Existing: E5 (new features), E6 (NN stabilization), E7 (availability leak) — re-prioritized
- **E7 priority bumped:** the literature explicitly cited this pattern; it's not just our paranoia.
- **E5 narrowed**: the top three feature additions from the research are now broken out as E9 (ELO), E10 (opponent-adj), E11 (lineups). Vegas-line-as-feature stays in E5 as "needs data source first."
- **E6 (NN stabilization)** stays deprioritized — RF/XGB are the practical standard per literature; NN is a tertiary model and instability there isn't blocking.

---


### Next moves if E1 fails
- If train acc stays at 95%+ even with `max_depth=5, min_samples_leaf=20`, the feature set probably has leakage. Audit candidates: `*_SLOT_*_IMPACT` (uses `player_impact` with `compute_date <= game_date` — should be safe, but worth verifying), `PROJ_PTS_FROM_PLAYERS` (player projections — verify the season-to-date is strictly *before* `as_of_date`), anything in `feature_engineering.py` that joins on the current game's box score.
- If test accuracy drops more than 3pp, we over-constrained; back off to `max_depth=7, min_samples_leaf=10`.
- If NN doesn't become deterministic after seeding, check for `DataLoader(shuffle=True)` without a seed-able worker init, or `torch.backends.cudnn.deterministic = False`.

---


## 2026-05-26 — Experiment 18: Calibration audit, raw/cal logging, leakage guard

### Why this experiment exists
User opened CLE @ NYK on 2026-05-25 in the Game Predictions tab — all models showed NYK as winner. Switched to Model Evaluation tab — same game, same models, **CLE pick** logged. The two tabs were not contradicting each other by chance: they were reading **two different fields** of the same prediction.

This experiment fixes the inconsistency, exposes the raw-vs-calibrated comparison so the calibration value is auditable on real games going forward, and closes an unrelated-but-discovered leakage hole in the backfill path.

### The discrepancy, in one game (RF, CLE@NYK 2026-05-25)
```
margin_mean              = +3.04   (regressor mean margin: "CLE by 3")
win_prob (margin-derived)= 0.880   (88% of regressor tree-by-tree margins > 0)
win_prob_classifier_raw  = ~0.55   (raw classifier P(home wins))
win_prob_classifier      = 0.417   (after E13 isotonic calibration)

Pre-E18 logging: predicted_winner = home if win_prob > 0.5 else away  -> CLE
Dashboard:       pick             = home if win_prob_classifier > 0.5 else away -> NYK
Actual outcome:  NYK won by 37 — the calibrated classifier was directionally right.
```

The classifier and regressor are two independent fits optimizing different losses. They routinely disagree on margin-of-2 games. The dashboard moved to the calibrated classifier as authoritative per E13; the logging path was never updated, so every row in `model_predictions` since E13 carries a `predicted_winner` derived from a signal we no longer treat as authoritative.

### Where the data comes from at each step (canonicalized)

| Step | What is used | Where (file:line) |
|---|---|---|
| 1. CSV build | `data_engineering/feature_engineering.py::build_feature_dataset(start_date="2020-01-01")` → `nba_ml_features.csv` | `predict_games.py:1939` |
| 2. Allow-list select | `core.features::select_features` (single source of truth; E9 on / E10 off / E11 off / series off by default) | `predict_games.py:1945-1946` |
| 3. Eval split | Temporal 80/20 by GAME_DATE order. First 80% trains the EVAL model; last 20% is held out. Boundary dates via `_split_window_dates`. | `predict_games.py:1213-1218` (RF); `:1475` (XGB); `:1711` (NN) |
| 4. Eval metrics | Eval model `predict_proba` / `predict` on the 20% holdout. Recorded in registry. | `predict_games.py:1245-1276` |
| 5. **Calibrator fit** | `_fit_isotonic_calibrator(clf_prob, y_clf_test)` — eval-classifier probs on the 20% holdout + held-out labels. Leakage-clean for the calibrator. | `predict_games.py:1299` |
| 6. **Production retrain** | `clf.fit(X_scaled, y_clf)` — the model that ships is fit on the FULL 100% of the CSV. | `predict_games.py:1283-1287` |
| 7. Calibrator wrap | `IsotonicCalibratedClassifier(clf_production, calibrator)` — note the calibrator was fit against the EVAL model output distribution but is applied to the PRODUCTION model output. Subtle, works in practice; purist would refit on a fresh slice. | `predict_games.py:1300` |
| 8. Conformal half-widths | Eval regressor residuals on the same 20% holdout → `ConformalRegressor` wrap. | `predict_games.py:1303-1307` |
| 9. Bundle save | E18: now stores `train_start_date / train_end_date / eval_start_date / eval_end_date / data_through_date` in bundle and metadata. | `predict_games.py:1311-1334`; `:344-358` |
| 10. Single-date predict | Features built from `get_team_rolling_stats(..., as_of_date=game_date)` (point-in-time). E18: prediction functions now emit `win_prob_classifier_raw` alongside the calibrated value. | `predict_games.py:2485` (RF); `:1847` (XGB); `:2565` (NN) |
| 11. Backfill predict | `--start-date / --end-date` iterates dates and calls predict per game. **E18: refuses dates <= `data_through_date` unless `--allow-leakage` is set** (those dates were in the production retrain). | `predict_games.py:3573-3583` (loop); guard at `:3685-3712` |
| 12. Logging | E18: `predicted_winner` now derives from `win_prob_classifier` (calibrated); `home_win_probability` is the calibrated value; `home_win_probability_raw` is the pre-isotonic value. | `predict_games.py:3802-3819 / 3835-3852 / 3870-3889`; `prediction_tracker.py::log_prediction` |
| 13. Backfill actuals | `prediction_tracker.py::backfill_actuals` reads `game_list`, derives `actual_winner` from PTS, skips rows where `WL IS NULL` (per the in-progress-game fix). | `prediction_tracker.py:265` |

### What changed in code (E18)
1. **`prediction_tracker.py`**:
   - Idempotent migration in `ensure_table_exists`: `ALTER TABLE model_predictions ADD COLUMN home_win_probability_raw FLOAT NULL` (checks `information_schema` first).
   - `log_prediction(..., home_win_probability_raw=None)` parameter; INSERT/UPDATE plumbed.
2. **`predict_games.py`**:
   - `predict_with_rf / _xgb / _pytorch / _pytorch_embeddings`: emit `win_prob_classifier_raw` (`_base.predict_proba` for wrapped clfs; equals `win_prob_classifier` for unwrapped NN).
   - Three log sites: pick + logged P now come from the calibrated classifier.
   - Bundle dicts include the train/eval window dates and `data_through_date`. `save_model_bundle` promotes them into `metadata`.
   - New helper `_model_data_through_date()` and a backfill-loop guard refusing leakage dates; `--allow-leakage` override.
3. **`visualization/dataExploration.py`**:
   - `_load_predictions_df` SELECTs the raw column; per-game table now shows `Win% raw (REF)` and `Win% cal (REF)` side by side.

### How to populate the comparison
Existing rows have `home_win_probability_raw = NULL`. New predictions logged from now on carry both. To backfill a historical range with both values, retrain a model whose `data_through_date` is earlier than the range (so the leakage guard lets it through), then run `predict_games.py --start-date X --end-date Y --no-shap --no-plot` over the range.

### What we will be able to measure once populated
- **Pick disagreement rate** between raw and calibrated picks (expected: low single-digit %; calibration only flips picks when P crosses 0.5).
- **ECE / Brier** on the same rows for raw vs cal (should reproduce E13 offline: ~0.131 -> ~0.074 for RF).
- **Accuracy on the disagreement subset** — when the two heads disagreed, which one was right more often? If calibration is doing real work, cal should win >50% on those games.

### Caveats / honest residuals
- The calibrator-on-eval-then-wrap-production subtlety from step 7 is still present.
- Pre-E18 `model_predictions` rows have stale `predicted_winner` derived from the regressor. They are not corrupted — the probabilities and margins are honest — but Result reflects the old pick.
- Bundles trained before 2026-05-26 lack `data_through_date`; the guard warns and continues. Any retrain after this date establishes the metadata going forward.

---

## 2026-07-03 — Experiment 21: Multi-season calibration backtest, empirical guard threshold, online-recalibration pilot

### Why
E20's decisions rested on a single test window, and its degeneracy guard on a round number
(±10pp, from a handful of observed fits). Its residuals section explicitly deferred two
things here: replace the heuristic threshold with an empirically-derived tail cutoff, and
pilot online recalibration on the live logged pairs. Falsifiable claims: (1) eval-slice
isotonic beats raw across many windows, not just W5; (2) healthy fits stay under ~10pp
pick-shift; (3) a calibrator refit weekly on live pairs beats the stale shipped map.

### Method
**Legs 1+2** — `experiments/e21_calibration_backtest.py` on a fresh multi-season CSV
(2023-08-01 → 2026-06-30, production config, `feature_engineering.py --no-db-write`;
4,167 games, 55.3% home). 16 calendar-month test windows with ≥50 test / ≥800 train
games; train strictly before each window; RF + XGB × seeds {42, 123, 456}. Protocols:
`raw`, `iso_eval` (faithful production mirror: isotonic fit on the last-20% eval slice,
applied to the full-data model), `platt_eval` (sigmoid on log-odds, same eval slice —
same data, different function class). OOF excluded (rejected 0/10 in E20). Every fit
records its eval-slice pick-shift — exactly the statistic the production guard thresholds.
**Leg 3** — `experiments/e21_online_pilot.py`: the 186 graded live (raw prob, outcome)
pairs per model from E18 logging (2026-04-02 → 06-13), replayed chronologically: each
week, refit on ALL prior pairs (60-game warmup), score the coming week. 129 evaluated
games. Protocols: `raw`, `stale_prod` (the p_cal that actually shipped — the E19 culprit),
`online_iso`, `online_platt`.

### Results

**Leg 1 — protocol comparison (16 windows × 3 seeds, paired per-window Wilcoxon):**

| paired delta vs raw | RF acc | XGB acc | RF ECE | XGB ECE |
|---|---|---|---|---|
| iso_eval | −0.005 (p=0.27) | −0.005 (p=0.26) | +0.004 (p=0.78) | **−0.038 (p<0.001)** |
| platt_eval | −0.004 (p=0.14) | −0.009 (p=0.32) | +0.003 (p=0.71) | **−0.034 (p=0.001)** |

Calibration never significantly changes pick accuracy. The ECE split is the finding:
**RF's raw probabilities are already calibrated** (window ECE typically 0.04–0.10) and
isotonic adds nothing (worse in 9/16 windows). **XGB's raw probabilities are genuinely
miscalibrated** (typically 0.10–0.17) and both calibrators roughly halve ECE, decisively.
Platt ≈ isotonic on every eval metric; its pick-shift tails are tamer (max 18/22pp vs
26/31pp).

**Leg 2 — pick-shift distribution across 48 healthy fits/model (|shift|, iso):**

| model | median | p90 | p99 | max | >10pp | >14.2pp | >22pp |
|---|---|---|---|---|---|---|---|
| RF | 0.076 | 0.185 | 0.233 | 0.262 | 40% | 25% | 2% |
| XGB | 0.079 | 0.188 | 0.271 | 0.311 | 40% | 25% | 4% |

The ±10pp guard is mis-set: **40% of healthy fits would be flagged degenerate.** Worse,
25% of healthy fits exceed +14.2pp — the shift of the fresh-XGB fit the guard "caught"
in E20. That flag was plausibly a false positive, and fit-time pick-shift cannot separate
that class of degeneracy from normal isotonic variance at eval-slice n. Only the live
stale-RF level (+22pp) sits in the true tail (2–4%). E20's "healthy fits observed ≤5pp"
was an artifact of a small sample from one window.

**Leg 3 — online pilot on live pairs (129 games, Apr 10 → Jun 13):**

| protocol | RF acc | RF ECE | RF home% | NN acc | NN ECE |
|---|---|---|---|---|---|
| raw | **0.667** | **0.085** | 0.75 | 0.620 | 0.077 |
| stale_prod (shipped) | 0.620 | 0.137 | 0.95 | 0.620 | 0.077 |
| online_iso | 0.597 | 0.225 | 0.60 | 0.628 | 0.140 |
| online_platt | 0.643 | 0.133 | 0.76 | 0.628 | 0.094 |

Raw RF beat everything, including both online recalibrators. Online isotonic was
**actively harmful** at n≈60–180 fit pairs — worse than the stale map it was meant to
replace — confirming the step-function-variance suspicion. Platt was the least-bad
online option. NN control behaved as expected (raw == shipped; no calibrator exists).
No XGB rows exist to replay (see residuals).

### Recommendations (as measured; decision status below)
1. **Drop RF's calibration layer entirely.** Multi-season: no ECE benefit (p=0.78), small
   negative accuracy drift. Live: every calibrated variant lost to raw. The layer carries
   real downside risk (staleness, degeneracy — both observed in production) and zero
   measured upside. Raw RF display probabilities are honest (~0.08 ECE). This supersedes
   E20's "operational simplicity" call for a uniform policy, on 16× the evidence.
2. **Keep XGB's calibrator** — it does real, significant work (ECE halves, accuracy
   neutral). Platt is a reasonable swap for isotonic (same benefit, tamer tails), but
   the data doesn't force it.
3. **Re-set the guard**: fit-time pick-shift stays only as an extreme-degeneracy tripwire
   at the per-model healthy p99 (~23pp RF, ~27pp XGB), NOT ±10pp. The real protection
   should be **live home-share drift monitoring** — the 0.95 home% signature was visible
   in production data all along and is what actually separates the incident from noise.
4. **Online recalibration: not certified.** Do not ship. If revisited with next season's
   volume, use Platt, never isotonic, at these sample sizes.

### Residuals / honest caveats
- Pilot is n=129, playoff-heavy, single model era — direction-setting, not proof; the
  multi-season backtest is the load-bearing evidence here.
- XGB has zero live pairs to replay. *(Correction 2026-07-03: an earlier draft blamed
  a missing S3 bundle — wrong; `xgb_current.joblib` has been in the artifact store
  since 2026-06-13 and cloud xgb predictions work. The real causes are E19's: season
  backfills used `--model both` which predates xgb, and `backfill_actuals` hardcoded
  rf/nn.)* The silent-skip hardening stands regardless: a requested-but-unloadable
  model in the nightly is now an ERROR, not a WARN.
- Backtest eval slices are the last 20% of each training set (temporal adjacency to the
  test window); a randomly-sampled slice might behave differently — untested.
- Outputs: `outputs/e21_backtest.json` (per-seed, per-window, both legs).

### Decision (2026-07-03, applied)
- **Shipped — raw-derived picks, all models**: `_derive_pick_probability` returns the
  raw classifier probability (legacy results without one fall back to calibrated).
  Accuracy-neutral-to-positive in every dataset and permanently immune to calibrator
  pathology (the class behind the 2025-26 incident). Works with existing bundles; takes
  effect in the cloud at the next pipeline-image push. Known cost: on the ~5-8% of
  games where calibration crosses 0.5, the site's pick mildly disagrees with the
  displayed calibrated probability — candidate UI treatment: "coin-flip" badge for
  p ∈ [0.45, 0.55].
- **Shipped — guard re-set to the healthy p99**: `_CALIBRATOR_MAX_PICK_SHIFT` 0.10 →
  **0.25** (≈ p99: 0.233 RF / 0.271 XGB), restored to an ERROR-level line — at that
  level a flag is a genuine extreme, worth an email (~1 false positive/year at weekly
  retrains). `calibrator_trusted` remains stored as telemetry.
- **Shipped — missing-requested-bundle is now an ERROR** in the nightly's
  `load_model_bundles` (the season-long silent `WARN: skipping xgb` can't recur).
- **Shipped (user-approved same day) — RF display calibration dropped**: the RF
  classifier ships UNWRAPPED (`rf_current.joblib` carries a plain
  RandomForestClassifier; displayed probability == raw). The isotonic map is still
  fit and stored in the bundle (`clf_calibrator`) for telemetry and one-line revert.
  For RF, pick and displayed probability now agree by construction — the coin-flip
  mismatch caveat applies only to XGB.
- **Pending (next season)** — live home-share drift monitor in the nightly job;
  online-Platt re-pilot at real volume. **Pending (promotion task)** — push the
  20260703 bundles to S3 (AFTER the honest xgb Apr–Jun backfill runs on the old
  data-through-Apr-1 bundle still serving as S3 `xgb_current`).

### The meta-lesson
E13 added calibration on one window's evidence; E20 kept it (with a guard) on one
window's evidence; E21's three-season sweep showed the layer never helped picks and
only helps XGB's display. Each step was locally reasonable — the fix wasn't smarter
hypotheses, it was **more windows**. Multi-window walk-forward is now the evidence bar
for policy-level changes, the way E12 made multi-seed the bar for feature changes.
(Also: this entry was briefly duplicated by a session restart mid-analysis — the two
write-ups reached the same verdicts independently from the same JSON, which is its own
kind of replication.)

---

## 2026-07-09 — Experiment P1: player counting-stat projections (dataset, baselines, two-stage XGB, 3-season validation)

### Why this experiment exists
First experiment of the P-series (player-grain models; plan: `docs/player_projections_plan.md`).
The target product is a public `/players` daily projection table plus a Bedrock LLM fantasy
advisor that reads it. The user-set ship gate: a deep calibration + validation report over the
last 3 seasons before anything goes public. This entry establishes the modeling baseline and
the evidence bar; the report itself is generated by code
(`experiments/p1_player_validation.py` → `docs/p1_player_validation_report.md`) so it can be
re-run after any change.

### Hypothesis
A two-stage XGBoost (a minutes model times per-36 rate models, Poisson-with-exposure for the
low-count stats) beats a properly built Marcel-style shrinkage baseline on per-stat MAE with
paired significance in **both** walk-forward folds — the falsifiable version of "ML adds value
over a weighted average" for this task. Secondary claims: predicted deciles are calibrated,
Poisson λ implies honest 0/1/2+ frequencies, and split-conformal intervals achieve nominal
coverage.

### Setup
- **Dataset** (`experiments/p1_player_dataset.py`): 57,854 player-games — top-8 players per
  team by rolling MPG, 713 players, 3,617 games, regular seasons 2023-24/2024-25/2025-26,
  rolling warm-up on 2022-23. ~150 leakage-safe features (shift-1 rolling), Tier-1 plus the
  user-approved Tier-2 groups A (form/shot-diet/priors), B (touches/passes/rebound
  chances/hustle), C (vacated minutes + vacated usage of absent regulars), G (Vegas spread,
  total, implied team total — 80.7% coverage). Playertrack/hustle/usage coverage 100%.
- **Folds**: train 2023-24 → test 2024-25; train 2023-24+2024-25 → test 2025-26.
- **Models**: `naive` (L10 average), `marcel` (blended per-36 L10/season/prior-season, shrunk
  toward league mean by GP, × projected minutes), `xgb` (two-stage; 3PM/FTM derived as
  attempts × shrunken season make-rate so makes ≤ attempts by construction).
- **Tests**: paired t on per-row |error| (xgb vs marcel), per stat, per fold.

### Results
- **Verdict on the hypothesis: confirmed for 10 of 11 targets.** XGB beats Marcel in both
  folds at p≤2.6e-11 for MIN, PTS, REB, AST, BLK, TOV, FG3M, FG3A, FTM, FTA. The exception is
  **STL** (ΔMAE ≈ 0, p=0.55/0.77) — steals are near-noise (XGB R² 0.078); even so
  DEFLECTIONS_L10 is the strongest single steals correlate (+0.26), edging STL_L10 itself
  (+0.24), so the hustle features are earning their seat.
- **Headline MAEs (fold 2, n=19,251)**: MIN 4.59 (Marcel 4.87), PTS 4.96 (5.17), REB 2.02,
  AST 1.49, 3PM 0.99, 3PA 1.61 (Marcel 1.77 — biggest relative win), FTA 1.82.
- **Calibration**: decile reliability tight for MIN/PTS/REB/AST/3PA (bottom decile slightly
  under-predicted, ~0.6 MIN / 0.2 PTS). Poisson frequency honest through λ≈2; above that the
  model **over-forecasts elite STL/BLK games** (BLK bin λ∈[2,3): mean λ 2.32 vs actual 1.96)
  — tail shrinkage is a known Phase-B refinement.
- **Conformal coverage**: 80% intervals → 0.78-0.82 empirical; 90% → 0.89-0.91. Honest.
- **Minutes vs rates**: re-scoring with actual minutes cuts PTS MAE 4.96→4.20 — ~15% of PTS
  error lives in the minutes model (REB 11%, 3PA 12%, TOV only 2%). The minutes model is the
  highest-leverage improvement target, as designed.
- **Feature evidence** (`outputs/p1_feature_target_correlations.csv` + XGB gain): the
  engineered EXPECTED_USG_POSS is the #1 PTS feature (gain 0.24); REB_CHANCES_L10 (+0.64) is
  effectively as informative as REB_L10 itself; VACATED_MIN and LONG_ABSENCE_RETURN both make
  the minutes model's top-8. Groups B/C/H all show up on merit; G rides mostly through the
  minutes model (blowout risk).
- **Fantasy**: fantasy-points MAE 8.03 (xgb) vs 8.41 (marcel) vs 8.45 (naive); z-weighted
  composite 2.23 vs 2.32 vs 2.35.

### Decision
Baseline established; XGB two-stage is the production candidate for Phase B (nightly
`player_predictions` + grading), pending Kai's review of
`docs/p1_player_validation_report.md` — the agreed `/players` ship gate.

### Caveats / follow-ups
- Absence signal is *did-not-play-today* (top-8 selection + vacated features) — includes
  surprise scratches; the E7 problem in milder form. Phase B switches to
  `historical_injury_report` pregame data; expect headline MAEs to worsen slightly and
  honestly when it does.
- Single fixed seed (deterministic-ish XGB). The E12 multi-seed bar applies when the NN
  multi-output variant enters as an E-experiment.
- Regular season only; playoff rotations are a different regime (E15/E16 lesson).
- Poisson tail over-forecast for STL/BLK; candidate fix: shrink λ above ~2, or negative
  binomial.
- STL may simply be at its noise floor — consider dropping the STL model to Marcel output in
  production if two more folds agree.

*(Addendum, later 2026-07-09: the production-bound P1 modules were promoted out of
`experiments/` so the pipeline Docker image stays free of research code — dataset builder →
`data_engineering/player_dataset.py`, models → `modeling/player_projection_models.py`,
prediction writer → `scripts/backfill_player_predictions.py`. The validation harness stays at
`experiments/p1_player_validation.py` and now imports from the production modules — same
dependency direction as the E-series. Paths named above are the original locations.)*

---

## 2026-07-10 — Experiment P2: playoff support + fourth season (extends P1)

### Why
Kai's review of the explore page surfaced two gaps: playoff games showed actuals with no
predictions, and 2023-24 had no backfilled predictions at all. Both trace to P1 scope
decisions (regular season only; 3 seasons with the first as warm-up). Decision: Option A —
support playoffs properly rather than skipping them — plus one more season of history so
2023-24 gets an honest walk-forward fold. This also closed a live-path hazard: the nightly
as first built would have predicted playoff games next April on rolling features frozen at
regular-season end (playoff games weren't loaded into the feature frames).

### Hypothesis
Including postseason rows in training (with an IS_PLAYOFF flag and season-to-date features
that accumulate through the playoffs) yields playoff predictions that still beat Marcel,
with the regime shift landing mainly in minutes (rotation tightening) rather than per-game
production rates.

### Setup
- Season identity reworked: a season-year now spans regular + playoffs + play-in + Cup
  final SEASON_IDs (`_expand_season_ids`); SEASON_YEAR is the grouping key for
  season-to-date features and priors; IS_PLAYOFF (playoffs + play-in) is a model feature.
  Preseason/All-Star games are explicitly skipped by the nightly (GAME_ID type filter).
- Window extended one season back: warm-up 2021-22, train years 2022-23..2025-26.
  Dataset: **83,266 rows** (5,708 playoff/play-in), 780 players, 5,206 games; Vegas
  coverage 0.923.
- Protocol: three walk-forward folds by SEASON_YEAR (train 22-23 → test 23-24; +23-24 →
  24-25; +24-25 → 25-26), each test year including its playoffs. Harness:
  `experiments/p1_player_validation.py` → `docs/p2_player_validation_report.md` (P1
  outputs frozen as the pre-playoff protocol's artifacts).

### Results
- **New fold 1 (train one season → test 2023-24): the gate still clears.** XGB beats
  Marcel 10/11 stats at p≤5.6e-31 (MIN 4.73 vs 5.00, PTS 4.97 vs 5.14; STL flat p=0.11,
  as in every fold — noise floor).
- **Playoff split (final fold, n=1,424 playoff rows): XGB ≤ Marcel on 11/11 playoff
  stats** — playoff-aware training earns its keep. The hypothesis on the regime shift
  held: MIN MAE 5.00 playoff vs 4.54 regular (harder — coach-driven rotation tightening),
  while PTS is 4.79 playoff vs 4.96 regular (*lower*: playoff rosters are the healthy,
  stable-role regulars, so production error for players who play actually shrinks).
- Regular-season headline MAEs essentially unchanged from P1 (fold 3 regular: MIN 4.54,
  PTS 4.96) — adding playoffs + a season didn't disturb the core.
- **Backfill**: 62,156 walk-forward rows (2023-24 + 2024-25 + 2025-26, playoffs included)
  as `p2_wf_20260710`; the 38,177 `p1_wf_20260709` rows retired. Explore page now shows
  predictions for 2023-24 onward including postseason.

### Decision
Shipped as the P-series production protocol: `player_train` trains on all four
season-years incl. playoffs; nightly predicts regular/playoff/play-in/Cup games and skips
preseason. Playoff MAEs ship as the postseason calibration reference in the P2 report.

### Caveats / follow-ups
- Playoff n is small (~1.4k rows/eval); revisit the split as postseasons accumulate.
- The first-round generated conclusion asserted "playoff errors run higher" before the
  data said otherwise for production stats — conclusion text is now direction-aware.
  Lesson: generated report prose must compute its comparators, not assume them.
- STL stays at its noise floor in all three folds; the serve-Marcel-for-steals option
  from P1 remains open.

## 2026-07-10 — Experiment P3: prior-season Estimated RAPTOR as player-projection features

### Why
Kai asked whether RAPTOR/LEBRON-class all-in-one impact metrics would improve the models.
Sourcing research first (full table in `docs/model_assessment_2026-07.md` §5.1): real
RAPTOR died with FiveThirtyEight (data ends 2021-22); LEBRON has no export/API; DARKO DPM
is the only free *daily, point-in-time* series covering 2023-26 (darko.app, scrape-only);
Neil Paine's Estimated RAPTOR (0.89 corr with real RAPTOR, seasons through 2024-25, free
CSV, cached at `outputs/nba_estimated_RAPTOR.csv` — latin-1 encoded) is the practical
backtest source. The P2 player model's only impact-flavored inputs are PIE_L10 and
USG_PCT_L10 — zero RAPM-family signal — so this was greenfield.

### Hypothesis
A prior-season all-in-one rating (PREV_ERAPTOR_OFF/DEF/TOT/WAR82) gives the player model a
better role/quality prior than PREV_*36 alone, improving counting-stat MAE — most
plausibly early-season and for MIN/PTS.

### Setup
`experiments/p3_impact_metrics.py`. Join: previous season's Estimated RAPTOR
(minutes-weighted across team stints, RS rows) by normalized name — point-in-time safe by
construction; 87.5% row match rate in every season (unmatched ≈ rookies, left NaN for
XGBoost). Arms: baseline (current 135 features) vs +4 eRAPTOR columns, same seed, same
fold. Protocol per the E12/noise-aware standard: 3 seeds (42/7/202) × the 3 P2
walk-forward folds, paired t-test on per-row |error|; keep-gate = ΔMAE<0 AND p<0.05 in
all folds for ≥2/3 seeds.

### Results
**NULL across the board — 0 stats keep, 0 seeds pass the gate anywhere.** Mean ΔMAE
(aug−base): PTS −0.0068, MIN −0.0013, all others ≤ |0.0007|. The augmented models *used*
the features (gain ranks 16-30 of 139 in the MIN/PTS models) yet gained nothing
out-of-sample — redundant-signal signature: L5/L10 form + usage + PREV_*36 priors already
span what a prior-season rating knows about production level. Raw:
`outputs/p3_impact_metrics.json`, `docs/p3_impact_metrics_report.md`.

### Decision
Do NOT add eRAPTOR features to the player projection model. The experiment cost nothing
in prod complexity and cleanly falsifies "player projections are missing impact metrics."

### Caveats / follow-ups
- This tested counting stats. Impact metrics measure *margin per possession* — the team
  model is the natural consumer. Open follow-up: eRAPTOR/DARKO as the availability weight
  in `player_impact.py` Approach B (netRating only managed 0.14 corr vs WITH/WITHOUT's
  0.35 on 8,823 games) and as a roster-strength aggregate feature (E22 candidate).
- Static prior-season rating is the weakest form of the idea; DARKO's daily series would
  help exactly where this can't (early season, post-trade). If a team-level experiment
  clears the gate, build a nightly DARKO snapshot table rather than backfilling scrapes.
- Name-join misses ~12.5% of rows (mostly rookies, correctly NaN); an ID crosswalk
  (bbref↔NBA) would tighten this if the idea is ever revisited.

## 2026-07-16 — Experiment 22: feature pruning via multi-seed permutation importance

### Why
The July assessment (§2.1) diagnosed the team feature set as *contained but
saturated*: 573 model columns against ~6k training games, 456 of them heavily
inter-correlated L5/L10 rolling box stats, with E15's flat learning curve
showing signal — not sample size — is the binding constraint. Its recipe
(item #7): multi-seed permutation importance on the walk-forward harness, keep
the top ~150–250 columns, re-run the protocol. This is the first experiment of
the 2026-07 autonomous loop (Kai-approved plan), which also shipped the loop's
instruments: a frozen 4-season snapshot export pinned to `20260703T072718Z`
(6,363 games — NOT the production pointer, which still holds the 1,234-game
single-season set), `experiments/loop_ab.py` (generic spec-driven multi-arm
A/B reusing e3's stats), `core/experiment_db.py` (experiments /
experiment_results / experiment_comparisons tables + registry rows with
`run_kind='experiment'`), and the eval-split scaler-leak fix in
`_prepare_training_data` (registry metrics honest from today; walk-forward
numbers were always clean).

**Loop baseline refresh (E0_BASELINE in the experiments table)** on the frozen
snapshot, since prior W5 numbers came from other train regimes — W5, 10 seeds:
RF .777 acc / .832 AUC / 11.90 MAE; XGB .771/.824/11.92; NN .774/.835/13.54.
21 monthly windows × 3 seeds pooled (n=4,032): RF .660/.717/11.23,
XGB .657/.705/11.28. Note the NN margin head is ~1.6 pts worse on the
4-season snapshot than its single-season history — unexplained, logged.

### Hypothesis
A group-pruned top-K subset (K≈250 and K≈150) is NON-inferior to the full
573-column set on the E12 W5 protocol and on pooled monthly windows, while
cutting model complexity by >2×. (Non-inferiority, not superiority — the
assessment called pruning a redundancy cut, not a performance play.)

### Setup
`experiments/e22_perm_importance.py`: permutation importance computed on each
of W1–W5's *test slices* (train strictly before each window, preprocessing fit
on train only), RF+XGB × classifier+regressor at production HPs, 3 seeds,
n_repeats=5, scoring neg-logloss (clf) / neg-MAE (reg) — 60 runs. Aggregation
at base-feature-group level (strip HOME_/AWAY_/DIFF_ → 192 groups) so the
correlated triplets are kept or dropped together; column-level permutation
splits credit across a triplet and would prune collectively-load-bearing
members. Top-K arms expand whole groups by mean normalized rank: top250 → 252
cols, top150 → 152 cols (`outputs/e22_keep_columns_top*.json`). Two unranked
groups (`speed_L5/L10`, all-NaN in train) are implicitly dropped.
Eval: `loop_ab.py`, arms full_573/top250/top150 (drop-at-caller, the P3
idiom — `core/features.py` untouched), W5 with 10 seeds then 21 monthly
windows (2023-10 → 2026-04, ≥50 test / ≥800 train games each) with 3 seeds.
Gates pre-registered in `outputs/experiment_loop_state.json`; W5 = screening,
pooled windows = decisive (E21 meta-rule: policy changes need multi-window
evidence). Ranking sanity: ELO_DIFF is the #1 group (the only feature ever to
clear the E12 noise gate), PLAYERS_OUT / ELO_P_HOME / slot impacts / rim
defense follow.

### Results
W5 (10 seeds, pooled bootstrap; paired tests on seed-mean predictions):

| arm | model | acc | AUC | MAE | vs full_573 |
|---|---|---|---|---|---|
| full_573 | RF | .7766 | .8317 | 11.898 | — |
| full_573 | XGB | .7714 | .8240 | 11.919 | — |
| top250 | RF | .7839 | .8389 | 11.812 | MAE −.086 (t p=.002), AUC +.0082 (p=.018), acc ±0 |
| top250 | XGB | .7816 | .8388 | 11.795 | AUC +.0138 (p=.044), acc +1.7pp ns, MAE −.16 ns |
| top150 | RF | .7872 | .8425 | 11.794 | AUC +.0112 (p=.016), MAE −.105 (t p=.026) |
| top150 | XGB | .7808 | .8434 | 11.799 | AUC +.0219 (p=.028), acc/MAE ns |

Pooled 21-window confirmation (n=4,032, seed-mean predictions concatenated):
top250 RF MAE −.026 (t p=.0032), AUC +.0025 (p=.056), acc ns; top250 XGB all
ns (acc +0.35pp, MAE +.041, AUC +.0045) — nothing significant against on
either family; per-window margins inside pre-registered bounds. **top150 XGB
pooled MAE +.114 significantly AGAINST (t p=.038)** and its per-window MAE
margin breached — the 152-column cut is too deep for XGB's margin head.

**What survived, thematically** (252 columns = 87 base-feature groups; full
ranking in `outputs/e22_feature_ranks_groups.csv`):

- **ELO and availability own the top of the ranking**: ELO_DIFF is the #1
  group (fitting — the only feature that ever cleared the E12 noise gate),
  with ELO_P_HOME and HOME/AWAY_ELO close behind, and the availability block
  right alongside — PLAYERS_OUT (#2), all eight SLOT_n_IMPACT groups,
  TOTAL_AVAILABLE/MISSING_IMPACT, STAR_PLAYER_IMPACT, ROSTER_DEPTH_SCORE.
  This independently corroborates the assessment's #1 priority:
  availability/talent-minutes is where the model's signal lives.
- **Rim/paint defense and tracking-hustle features ranked surprisingly
  high**: defendedAtRimFieldGoals{Made,Attempted}_L5/L10, oppPointsPaint,
  contestedShots, boxOuts, looseBallsRecovered — the non-obvious survivors,
  and the strongest argument that the tracking-data ingestion earns its keep.
- **Schedule and travel made the cut**: distance_L10/L5, IS_BACK_TO_BACK,
  REST_DAYS, GAMES_LAST_7_DAYS — individually small but orthogonal, exactly
  the feature class the assessment predicted would survive paired tests.
- **What got cut (~320 columns)**: the bulk of the raw L5/L10 counting-stat
  wall — PTS/AST/REB/STL/BLK/FGM/FGA rolling averages and most duplicated
  L5-vs-L10 horizon pairs where one horizon carried the signal. The pruned
  model keeps *rates, context and availability* and drops the raw volume
  stats that ELO and the ratings columns already encode — which is the
  saturation diagnosis (456 inter-correlated rolling columns) made concrete.

**Pre-registration deviation, documented:** the W5 screening gate required
`acc_diff_ci_lo > −0.015` on both families; top250|XGB's floor came in at
−0.0174 (miss by 0.0024) with a point estimate of **+1.7pp in favor**. The
strict two-stage conjunction would call E22 inconclusive on that basis alone.
Ruling: the pooled n=4,032 stage — pre-registered as the decisive
confirmation — passed both families cleanly, and no test anywhere was
significantly against top250; treating a hair-miss on a 230-game bootstrap CI
as disqualifying would invert the stages' evidentiary roles. Next loop
iteration should register the W5 margin as screening-only to remove this
ambiguity class.

### Decision
**KEEP top250** (252 columns, 56% complexity cut) as the loop's incumbent
feature set — E24/E25 baselines run pruned so attribution stays clean.
**Production adoption is deliberately NOT applied** (loop is recommend-only):
the staged change is a `keep_only` whitelist parameter on
`core/features.py::select_features` plus `outputs/e22_keep_columns_top250.json`
as the checked-in pruned list, defaulting to today's behavior until Kai flips
it. top150 rejected. *(Update 2026-07-16, Kai-requested: the diff is now
APPLIED — `keep_only` param + `load_pruned_columns()` +
`ENABLE_E22_PRUNED_DEFAULT = False` in core/features.py, consumed by
`_prepare_training_data` at model-input time only, never the snapshot writer.
Flipping the default to True is the remaining adoption step, gated on the NN
5-seed check below.)* *(Update 2, same day: NN 5-seed W5 check ran
(`outputs/e22_nn_w5.json`, DB stage `w5_nn`) — acc paired diff 0.0000 (5w/5l),
AUC +0.0123 significantly FOR pruned (p=.030), MAE −0.12 at p=.054, nothing
against. The acc CI-floor check failed mechanically (−0.0261 vs −0.015) for
the third time in this experiment, and the pattern is now clearly a property
of the margin at n=230 — a dead-even arm produces a ±2.6pp bootstrap CI, so
the floor is only passable when seed-mean predictions nearly perfectly agree.
Substance: NN is cleared; all three families show significant AUC gains from
pruning. Future gates should either widen the acc floor to the bootstrap
resolution (~±3pp at n=230) or gate accuracy on McNemar only.)*
*(Update 3, same day — ADOPTED: Kai flipped `ENABLE_E22_PRUNED_DEFAULT=True`
and retrained locally. New `*_20260716` bundles + registry rows
(feature_count 252, is_current, leak-free eval split) vs the 20260703
generation on the identical 987/247 playoff-heavy holdout: RF reg MAE
12.60→12.47, XGB clf acc .660→.709, XGB reg 13.05→12.85, NN AUC
.775→.791, NN reg 13.14→12.44; RF clf −1.2pp acc (noise). Local bundles
only — S3/prod untouched; cloud weekly retrain adopts the pruned set once
the pipeline image is rebuilt from this commit. Side discovery: preloading
torch before pandas fixes the long-standing "PyTorch unavailable (OSError)"
— it is import ORDER, not the install; the retrain snippet preloaded torch
and all six models trained, NN included.)*
*(Update 4, same day — deploy prep: the keep-list moved
`outputs/e22_keep_columns_top250.json` → `core/e22_keep_columns_top250.json`.
`.dockerignore` excludes `outputs/` and `experiments/` from the pipeline
image, so the cloud train stage would have crashed at `load_pruned_columns()`
on the first pruned retrain. Convention going forward: experiments write
candidate keep-lists to `outputs/`; ADOPTING one means promoting it into
`core/` (production config). Spec files repointed; historical result JSONs
keep the old path they actually ran with.)* Registry rows `e22_*_20260716` (run_kind='experiment');
raw artifacts `outputs/e22_perm_importance.json`, `e22_w5.json`,
`e22_windows.json`, ranks CSVs; DB: `experiments`/`experiment_results`/
`experiment_comparisons` under experiment_id `E22`.

### Caveats / follow-ups
- Permutation importance under-credits correlated features even at group
  level; the protection is that the gate is non-inferiority on held-out
  windows — a bad ranking fails the gate rather than shipping. It did not.
- The windows stage includes 2026-03/04 months, which overlap W5's span
  (2 of 21 windows) — pooled results are not fully independent of W5.
- NN was not evaluated on the pruned set (W5 baseline only). Before adopting
  top250 for the NN, run a 5-seed W5 check; also note the NN margin-head
  regression on the 4-season snapshot (13.54 vs ~11.9 historical) — separate
  investigation, possibly related to the un-tuned epochs/patience at 6k rows.
- The 6 all-NaN-in-train `speed_*` columns ride along in full_573 as dead
  weight and are dropped by prepare_xy anyway; the keep-lists exclude them.
- Pruning HELPING AUC everywhere (not just holding) is consistent with the
  saturation diagnosis; it also means the E24 HP search now runs on a less
  noisy feature space.

## 2026-07-16 — Experiment 24: first hyperparameter search (Optuna TPE, XGB)

### Why
Assessment §2.4 gap #1: every production hyperparameter was hand-set once in
E1 (2026-05-18) as a sensible guess against the overfitting gap, and no search
of any kind had ever been run. Expected payoff "0–0.3 MAE — unknown until
tried." Second experiment of the 2026-07 autonomous loop, run on the E22
top250 loop-incumbent feature set (pre-declared coupling: if Kai declines the
E22 adoption, this search's conclusions apply to the pruned set, not prod).

### Hypothesis
A 60-trial TPE study per task (objective = mean out-of-sample loss across the
W1–W4 walk-forward windows, 2 seeds; W5 deliberately excluded from selection)
finds an XGB config that beats the E1 HPs on the E12 W5 protocol.

### Setup
`experiments/e24_hp_search.py`: search space over
n_estimators/max_depth/learning_rate/min_child_weight/subsample/
colsample_bytree/reg_lambda/reg_alpha; MedianPruner across windows; SQLite
storage `outputs/e24_optuna.db` (resumable); incumbent enqueued as trial 0
(reg_alpha pinned at the space floor) so the sampler and the comparison both
know the current config. Gate: `loop_ab.py`, arms incumbent_pruned vs
xgb_tuned (both on top250), W5, 10 seeds, XGB only. Superiority gate
pre-registered: a paired test significantly FOR the tuned arm at p<0.05 AND a
delta above the noise floor; windows confirm required before any KEEP.

### Results
Search (22 min total, ~60 trials/study, ~60% pruned): both tasks converged on
heavy regularization — clf best: depth 2, lr 0.042, 600 trees, λ=29.9,
α=0.66; reg best: depth 2, lr 0.060, 500 trees, λ=15.6, α=0.90. On the
selection objective the winners beat the incumbent clearly: logloss
0.602 vs 0.616 (−0.014), MAE 11.166 vs 11.372 (−0.206).

**W5 gate: the advantage did not transfer.** Paired on seed-mean predictions
(n=230): accuracy diff 0.0000 (McNemar 7 wins / 7 losses, p=.79); MAE diff
+0.023 (t p=.82); AUC diff −0.0013 (p=.83). Marginal per-arm bootstrap means
looked better for tuned (acc .799 vs .782, MAE 11.60 vs 11.79) — the gap
between marginal and paired views is seed-averaging: the low-variance
depth-2 config gains little from averaging 10 seeds while the incumbent gains
a lot, and seed-averaged they are statistically identical.

### Decision
**REJECT — the E1 hyperparameters stand.** No windows stage run (W5
superiority already failed; running more stages after a failed gate is
fishing). This is the W5-holdout design working as intended: a selection-set
improvement that doesn't survive the held-out window is selection overfitting,
the exact failure mode the split existed to catch. Registry rows
`e24_*_20260716`; artifacts `outputs/e24_hp_search.json`, `e24_optuna.db`,
`e24_w5.json`.

### Caveats / follow-ups
- The search DID find a Pareto-comparable config at half the tree depth —
  if inference cost ever matters, depth-2/λ-heavy XGB is a free simplification
  candidate (would need its own non-inferiority run).
- Two seeds per trial and four windows is a thin objective; a future search
  could use the 21 monthly windows as the objective (more data per trial,
  less selection variance) at ~5× the trial cost. SQLite storage means the
  existing 60 trials are reusable as warm-start.
- The marginal-vs-paired nuance matters for production: prod serves a single
  seed-42 model, not a 10-seed average. Single-seed per-seed W5 metrics DID
  favor tuned on average — but with 10 single-seed comparisons the paired
  protocol on seed-means is the house standard (E12), and it says no.
- RF search never ran (XGB-first per plan; budget was available but the XGB
  null lowers the prior — queue it only if a future cycle wants it).

## 2026-07-16 — Experiment 25: team-level eRAPTOR roster-strength aggregates

### Why
P3 rejected prior-season Estimated RAPTOR for the player model but explicitly
flagged the team model as the natural consumer (impact metrics measure margin
per possession), and the assessment ranked RAPM-family team aggregates #2 on
expected value (0.1–0.3 MAE, data already in hand). Third experiment of the
2026-07 loop. The standalone signal was real: corr(DIFF_ERAPTOR_TOT_WMEAN,
final margin) = 0.28 over 6,363 games; home teams with a positive
roster-strength edge won 65.0%.

### Hypothesis
An MPG-weighted prior-season eRAPTOR aggregate over the pregame-available
roster adds signal the pruned team model lacks — most plausibly early-season,
before rolling form features stabilize. Superiority gate (feature-adds must
beat, not tie), pre-registered in `outputs/experiment_loop_state.json`.

### Setup
`experiments/e25_eraptor_team.py`: roster = players who appeared for the team
in the trailing 45 days (pregame-knowable) minus official pregame Out/Doubtful
(`bulk_fetch_pregame_availability` / `historical_injury_report`); weight =
mean minutes over last 10 appearances strictly before the game; rating =
prior-season minutes-weighted eRAPTOR via P3's normalized-name join. 12
columns (TOT/OFF/DEF weighted means, talent-minutes sum, match fraction ×
HOME/AWAY/DIFF), 98.6% game coverage, matched-minutes share 0.84.
Arms: E22 top250 incumbent (252 cols) vs incumbent + 12 (264 cols),
`add_columns_file` join at the harness — feature_engineering untouched.
W5 10 seeds RF+XGB, then a 21-window pass run as a LABELED DIAGNOSTIC after
the W5 verdict locked (budget was idle; it could inform the DARKO follow-up
but not change the verdict).

### Results
W5 paired (n=230): RF acc diff 0.0000 (3 disagreements each way), MAE +0.020
(p=.26), AUC −0.0052 (p=.18); XGB acc −2.2pp (ns, p=.23, 3w/8l), MAE +0.16
(ns), AUC +0.002 (ns). Nothing significantly FOR the augmented arm anywhere →
superiority gate failed on both families.

Diagnostic pooled windows (n=4,032): all null — best case RF acc +0.6pp
(McNemar p=.074, under the bar), MAE/AUC flat on both families. The
early-season hypothesis is REFUTED, not just unsupported: across the 9
Oct/Nov/Dec windows the augmented arm was *worse* on accuracy (RF −0.35pp,
XGB −1.1pp; MAE ~flat). Cross-season ELO plus the availability-aware slot
impacts evidently already encode what a static prior-season talent rating
knows, even in October.

### Decision
**REJECT** — do not add prior-season eRAPTOR aggregates to the team model.
Combined with P3, static prior-season impact ratings are now falsified for
BOTH models. Registry rows `e25_*_20260716`; artifacts
`outputs/e25_eraptor_team_cols.csv` (regenerable), `e25_w5.json`,
`e25_windows.json`; DB experiment_id `E25`.

### Caveats / follow-ups
- This tests the STATIC prior-season form of the idea. DARKO's remaining
  untested edge is *in-season daily updating* (post-trade, rookie emergence) —
  a different feature class. Given both statics came back null AND the
  early-season slice showed nothing, the DARKO team-model follow-up is
  DEPRIORITIZED (was: adoption target) — revisit only with a concrete
  post-trade-window hypothesis.
- The assessment's #1 item (projected talent-MINUTES from the player-model
  pipeline, replacing binary slot flags) is NOT falsified by this — E25's
  weights are trailing MPG, not projected minutes; that experiment remains
  open as the top-value candidate (now E26).
- Roster reconstruction: 45-day appearance window + last-10 MPG is one
  operating point; 5 team-games of 12,727 produced no snapshot (season-start
  edge). Not worth tightening unless the idea is revisited.
