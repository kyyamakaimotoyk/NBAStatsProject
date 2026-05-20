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
| **E15** | **Cross-context generalization** — Phase 1 | (a) How much data is needed (learning curve)? (b) Can a regular-season model be trusted in the playoffs? Uses E13/E14 coverage+ECE as the cross-context lens. | `experiments/e15_cross_context.py` two modes. **Learning curve**: fix test=W5, vary train-start (0.5-4 seasons), 5 seeds. **Regime**: per-season temporal train on regular games before each season's playoffs, pool ~400 playoff test games; compare regular(control)/playin/playoffs on acc/AUC/MAE/ECE/coverage + KS feature-shift. Write-up: docs/e15_cross_context_report.md. | **Learning curve flat past ~1 season** (1k→4.5k games buys ~0 acc/MAE) → don't chase more history. **Playoffs**: winner-prediction degrades hard (RF acc 0.713→0.635, AUC 0.790→**0.637**; XGB similar) — playoffs are a harder, ELO-compressed, slower-pace subset (KS DIFF_ELO p=0.029). **But intervals/calibration transfer**: playoff cov90≈0.88-0.90, ECE stays low. Coverage-as-diagnostic worked: spread is similar (bands hold) but winner is less predictable (AUC craters). Play-in n=30 too small to trust. | **Diagnostic, no model change 2026-05-19** — recommendations: set playoff expectations ~63% not ~71%; trust intervals in playoffs; future playoff-specific features. |

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
