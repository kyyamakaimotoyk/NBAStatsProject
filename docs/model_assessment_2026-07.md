# Model & Methodology Assessment — 2026-07-10

A critical review of (1) the team win-probability + margin models and (2) the P1/P2
player counting-stat models, answering four standing questions, plus a prioritized
roadmap for closing the gap to the Vegas lines. Companion artifacts produced with
this review:

- **New "Model Evolution" tab** in `visualization/dataExploration.py` (Tab 8) —
  iteration-over-iteration registry trajectories, overfit gaps, feature-count
  scatter, and live monthly accuracy/MAE vs Vegas.
- **P3 experiment** (`experiments/p3_impact_metrics.py`) — prior-season Estimated
  RAPTOR as player-projection features; results in
  `docs/p3_impact_metrics_report.md` / `outputs/p3_impact_metrics.json`.
- Impact-metric sourcing research (RAPTOR/LEBRON/DARKO/EPM/BPM) — §5.

---

## 1. Executive summary

1. **The premise "RF is much worse than XGB/NN" is wrong** — it is an artifact of
   one noisy 230-game window. Across every multi-seed, multi-window measurement in
   this repo, RF *wins* winner accuracy and AUC. RF's real, documented weaknesses
   are timid probabilities (a direct side effect of the E1 regularization) and no
   edge on margin MAE. Details in §2.3.
2. **You are not catastrophically overfitting anymore, but you are feature-saturated.**
   The E1 fix cut the RF train-test gap from 24pp to ~5pp, and the E12 noise-aware
   protocol has been correctly killing weak features (E10, E11, series context).
   But 573 features on ~1k-6k games is past the point of diminishing returns: the
   E15 learning curve is flat past one season, and the only feature since E7 to
   clear paired significance is Elo (4 columns). The marginal cost of the feature
   count is now variance and iteration speed, not test-set damage. §2.1.
3. **The player model does NOT capture per-game swings — by design — and its own
   reports prove ~85% of scoring error is irreducible rate variance.** Decile
   calibration shows no regression-to-the-mean compression (good), conformal
   coverage is honest, but point estimates plus Poisson tails are the only
   distributional output, and the STL/BLK 2+ tail is over-forecast above λ≈2. If
   "capturing swings" matters (fantasy ceilings/floors), the missing piece is a
   distributional head, not more features. §3.
4. **The realistic Vegas target is the margin-MAE gap (~1 point), not winner
   accuracy.** Model MAE sits at 11.6–11.9 vs the Vegas closing-line floor of
   ~10–11. The levers that plausibly move it, in order: availability/minutes
   signal, talent-aggregate features (DARKO-class), ensembling the three model
   families, and betting-relevant evaluation (ATS/CLV) instead of raw accuracy. §6.
5. **RAPTOR is dead and LEBRON is not exportable; DARKO DPM is the right
   impact metric to adopt** (free, daily, point-in-time-safe, 2013→today).
   Neil Paine's Estimated RAPTOR (through 2024-25) is the right *backtest* source,
   and is what P3 uses with a leakage-safe prior-season join. §5.

---

## 2. Team model (win probability + margin)

**Framework recap.** Three families (RF / XGB / NN), each a classifier+regressor
pair sharing one scaler and feature list (`modeling/predict_games.py`); features
selected by `core/features.py` (prod: E9 Elo on, E10/E11 off → 573 columns);
temporal 80/20 in-file eval, isotonic calibration (XGB only since E21b), split
conformal intervals; honest evaluation via the E2/E21 walk-forward harnesses with
the E12 multi-seed + paired-test protocol.

### 2.1 Are you overfitting to too many features? — *Contained, but saturated*

Evidence for concern:

- The **in-sample memorization is still extreme** for the boosted/tree models:
  the 2026-07-03 registry rows show XGB train MAE **1.78 vs test 13.05** and train
  accuracy **99.8% vs test 66%** (987-row single-season CSV). RF: train MAE 9.23
  vs test 12.60. The new Model Evolution tab charts this gap per iteration.
- **573 features : ~1,000 training games** (single-season CSV) is a ~0.6:1
  column-to-row ratio; even the 4-season file only gives ~11 rows per feature.
- **E15's learning curve is flat**: 7.8× more data bought +1.4pp accuracy. Signal,
  not sample size, is the binding constraint — which means extra features mostly
  add variance.
- Every feature batch since Elo failed the noise gate: E10's 54 columns
  *significantly regressed* RF MAE (p=0.011–0.023), E11's 27 lineup columns (57%
  NaN) did nothing, series context did nothing (E17).

Evidence against panic:

- The walk-forward numbers (the honest ones) are stable across windows and seeds;
  the E1 regularization (max_depth=5, min_samples_leaf=20 / dropout 0.5 + weight
  decay) already cut the RF gap 24pp→4.7pp and NN 18pp→9.6pp.
- The E12 protocol (10 seeds × 1000 bootstraps, McNemar/paired-t) is exactly the
  right control and has been enforced.

**Verdict:** the *protocol* protects you from shipping overfit gains, but the
*feature set* is bloated relative to its information content: 456 of 573 columns
are L5/L10 rolling box-score stats that are heavily inter-correlated. Two cheap
wins:

- **Prune**: multi-seed permutation importance on the walk-forward harness, keep
  the top ~150–250 columns, re-run E2. Expect equal-or-better metrics with faster
  iteration and less variance. (A redundancy cut, not a performance play.)
- **Fix the eval-split scaler leak**: `_prepare_training_data` fits the imputer +
  scaler on the full X before the 80/20 split (`predict_games.py:2252-2256`).
  Walk-forward harnesses are clean, but the registry metrics are mildly inflated;
  fitting the scaler on the train split only makes the registry trustworthy.

### 2.2 Are you missing features? — *A few classes, yes*

Present and well-covered: rolling box stats (L5/L10), rest/schedule density,
streaks, Elo, injury-driven availability slots, per-player projection aggregates,
usage/TS/PIE aggregates. Genuinely missing classes, in rough order of expected
value:

1. **All-in-one talent aggregates (RAPM-family).** Current player-impact features
   are WITH/WITHOUT margins and PIE/usage sums — noisy and box-score-bound. A
   team-sum of minutes-weighted DARKO DPM (or eRAPTOR for backtests) for the
   *expected available roster* is the single most promising untried feature class;
   it directly upgrades `STAR_PLAYER_IMPACT` / `*_TOTAL_AVAILABLE_IMPACT`. (The
   old `impact_evaluation_results.csv` experiment showed netRating-style advanced
   metrics *underperform* WITH/WITHOUT — but netRating is not a RAPM-family
   metric; that conclusion should not be read as "impact metrics don't work.")
2. **Projected starting-minutes at the team level.** You already have a P2 minutes
   model per player; the team model never sees its output. "Sum of projected
   minutes × talent for tonight's roster" beats slot-availability flags.
3. **Travel micro-features**: time-zone changes, miles traveled last 7 days,
   altitude (DEN/UTA). Rest is in; travel is not. Small but free.
4. **Shooting-luck regression**: opponent 3P% allowed and own 3P% over L10 carry
   luck; features like "3P% minus xFG3%" (or just 3PA rate vs makes decomposition)
   let the model fade hot streaks. Public research consistently shows 3P variance
   is the biggest single noise source in game outcomes.
5. **Garbage-time-filtered ratings** (or luck-adjusted net rating): close-game
   performance predicts differently than blowout stat-padding.
6. **Market-derived features are deliberately excluded** (E5 decision) so Vegas
   stays a clean benchmark — keep that stance for the public accuracy page, but
   note that if the goal ever becomes *betting*, an opening-line feature with
   closing-line evaluation is the standard playbook.

Not worth it (already falsified here): more seasons of the same features (E15),
opponent-strength re-weighted rolling stats (E10), raw 5-man lineup stats at
current NaN rates (E11), series context (E17).

### 2.3 Why is RF "much worse" than XGB and NN? — *It isn't; fix the question*

What the multi-run evidence actually says (production config, E9-on/E10-off/E11-off):

| Evaluation | RF | XGB | NN |
|---|---|---|---|
| E2 W5 walk-forward (n=230) | **acc .791 / AUC .835** / MAE 11.90 | .770 / .826 / 11.67 | .765 / .820 / **11.60** |
| E20 single-season, 10 seeds | **acc .767 / AUC .828** | .730 / .801 | .719 / .810 |
| E21 3-season × 16 windows | **acc .657 / AUC .709 / Brier .215 / ECE .080** | .643 / .689 / .228 / .120 | — |
| E3 ablation CI (10 seeds × 1k boot) | acc 76.1 [70.4, 81.7] | 77.3 [71.3, 83.0] | — |

The "XGB 80.0% / RF 78.7%" that seeded the premise was the *full-E11-feature,
single-seed* W5 run, which the tuning log itself flags as a noise high ("cleared
zero paired tests"). The bootstrap CIs on a 230-game window are ±5pp — model
differences of 1–3pp in one window are unreadable.

RF's two *real* deficits, both documented and both already partially addressed:

1. **Timid probabilities.** max_depth=5 + min_samples_leaf=20 means every leaf
   averages ≥20 labels; the forest structurally cannot say "90%". That's the same
   regularization that fixed the 24pp overfit gap (E1) — a deliberate trade. Over
   multi-season walk-forward RF's raw ECE (0.080) is actually fine, and after the
   E19 isotonic pathology (calibrator collapsing to ~97% home picks) RF now ships
   raw — correct call. The residual cost is on log-loss-style metrics in sharp
   windows, not on picks.
2. **No margin edge.** RF regressor at depth 5 tops out around MAE 11.9 / R² 0.33;
   XGB/NN are ~0.2–0.3 points better on MAE. If one model family had to own the
   margin head, it would not be RF.

**Recommendation:** stop treating the three families as competitors to be ranked —
their disagreement is signal. A probability-average (or logistic-stack) ensemble
of RF+XGB+NN is the cheapest untried accuracy/Brier win in the repo (see §6.3);
per-family strengths (RF picks, XGB/NN margins) argue for a heterogeneous serving
policy if you don't ensemble.

### 2.4 Methodology critique (team)

Strong: temporal splits everywhere, walk-forward harnesses, multi-seed + paired
tests (E12), backfill leakage guards (E18), post-game-availability leak fixed
(E7), conformal intervals with honest coverage (E14), calibration measured and
acted on (E13/E19-21).

Gaps, in priority order:

1. **Hyperparameters were hand-set once (E1, 2026-05-18) and never searched.**
   There has been no systematic HP search for any family — no grid, no Optuna.
   Given the E12 harness exists, a small Optuna study (50–100 trials per family,
   objective = mean walk-forward log-loss across W1–W5) is cheap and would likely
   buy more than any feature work; RF depth 5 / XGB depth 4 were sensible guesses,
   not optima. (`optuna` is not yet in the venv.)
2. **The Vegas benchmark is not wired into the walk-forward harness** —
   e21_backtest.json has no Vegas fields; the only head-to-head is playoffs
   (E16). The new dashboard tab closes this for *live* months, but the backtest
   harness should log |vegas−actual| per window alongside model MAE so every
   experiment reports "gap to Vegas" as a first-class metric.
3. **The classifier and regressor are independent heads** that can disagree
   (margin +3 / P(win) 0.45). Deriving P(win) from the margin distribution
   (P(margin>0) given conformal width) — or at least reporting disagreement —
   would make the pair coherent.
4. Registry eval-split scaler leak (§2.1).

---

## 3. Player model (P1/P2 counting stats)

**Framework recap.** TwoStageXGB: a minutes regressor, per-36 rate models
(PTS/REB/AST, minutes-weighted), Poisson-with-exposure models (STL/BLK/TOV/3PA/FTA),
derived makes. 135 features across form/role/teammate-vacuum/schedule/team/opponent/
market groups. Walk-forward by season, Marcel as the must-beat gate with paired
t-tests. Beats Marcel on 10/11 stats in all folds (STL at its noise floor);
fantasy-point MAE 7.98 vs Marcel 8.41.

**This is the best-run part of the project.** The Marcel gate, the per-36
decomposition with exposure offsets, the minutes-vs-rate error decomposition, and
honest conformal bands are textbook. Critique focuses on what it *doesn't* do:

### 3.1 Is it capturing the swings? — *No, and mostly it can't — but three real gaps exist*

What the reports already establish:

- **No regression-to-the-mean compression**: decile means track actuals across the
  full range (worst gap 0.38 MIN in the bottom decile). Stars aren't shaved,
  role players aren't inflated. So the *point estimates* are unbiased across
  levels — the model is not "flattening" anyone.
- **The error is rate variance, not minutes**: with a perfect minutes oracle, PTS
  MAE falls only 4.94→4.18 (−16%). The remaining ~85% is single-game
  shooting/opportunity luck no pregame feature can see. A hard floor of ~4.2 PTS
  MAE exists for *any* point-estimate model on this task.
- **Conformal widths are the honest swing statement**: PTS 90% ≈ ±10.5. Coverage
  78–82% / 90–91% at nominal 80/90 — the bands are right, they're just wide
  because basketball is.

The three real gaps if swings are the product goal:

1. **The high tail is over-forecast for defensive events**: above λ≈2 the
   Poisson head over-predicts 2+ STL/BLK games (e.g. BLK bin [2,3): implied 66.6%
   vs empirical 63.2%). Queued fix is right: negative-binomial or tail shrinkage.
2. **Rate stats have no distribution at all.** PTS/REB/AST emit a single number;
   fantasy ceiling/floor questions ("P(30+ points)") are unanswerable. Phase D
   (quantile XGB / NGBoost) is parked — it should be un-parked before advisor
   work, because a fantasy advisor's real currency is tail probabilities.
3. **Minutes are a point estimate.** MIN_STD_L10 is an input, but there's no
   predictive minutes *distribution* (blowout truncation, foul trouble, coach
   volatility), and minutes error is the largest *reducible* term. A two-component
   minutes model (plays/doesn't-play-much × minutes-if-normal) or quantile minutes
   would propagate real uncertainty into every stat.

Also missing (cheap): a residual-vs-volatility slice (does error scale with a
player's own MIN_STD/USG_STD?) — one groupby away and would tell you *whose*
swings the model misses; and an explicit blowup/dud analysis (games >1.5× or
<0.5× season average) to quantify tail capture per player archetype.

### 3.2 Impact-stat coverage

The projection features contain **zero RAPM-family signal** — only PIE_L10 (a
box-score share) and USG_PCT_L10 qualify as "impact" stats. Whether that matters
for *counting stats* is exactly what P3 tests (§5): the mechanism would be better
opponent-quality and role priors, especially early-season when L10 windows are
noisy and PREV_*36 is the only history.

---

## 4. Model performance DB + the new dashboard tab

The performance store was already right for this job: `model_registry` (140 rows —
per-run test metrics, hyperparameters JSON, train_metrics JSON for overfit gaps,
run_kind train/validation/backfill, notes), `model_predictions` (12,926 rows,
12,920 graded, 2023-10→2026-06), `vegas_lines` (5,659 rows, kaggle_sbr +
espn_draftkings).

**New Tab 8 "Model Evolution"** (`visualization/dataExploration.py`, callback
`update_model_evolution`) — run `python visualization/dataExploration.py`, port
5000:

1. **Metric trajectory** — any registry metric across iterations per family;
   solid = training runs, dashed diamonds = validation runs; hover carries
   version, feature count, sample size, and the run's notes.
2. **Overfit gap** — train−test accuracy (classifier) and test−train MAE
   (regressor) per iteration; the E1 step-down and XGB's memorization are
   immediately visible.
3. **Feature count vs metric** — one point per run; answers "did adding columns
   ever pay?" at a glance.
4. **Live monthly winner accuracy + margin MAE vs Vegas** — gold star line = the
   book (implied favorite / implied margin, deduped to best-priority source per
   game, MAE computed on the same paired slate). The vertical distance to gold IS
   the Vegas gap, monthly.

Caveat printed on the tab: registry metrics come from the in-file 80/20 split —
trust *direction* there, *magnitude* in the walk-forward docs.

(Pre-existing quirk noticed while testing: the Dash app prints "PyTorch not
available (OSError)" at import although torch 2.9.1 is installed — the nn bundle
therefore doesn't load in the dashboard process. Likely a DLL/VC++ issue specific
to how the app imports torch; worth a look separately.)

---

## 5. Player impact metrics: research + P3 experiment

### 5.1 Sourcing landscape (verified 2026-07-10)

| Metric | Status | Point-in-time? | Use here |
|---|---|---|---|
| RAPTOR (538) | **Dead** — data ends 2021-22 (GitHub, CC BY 4.0) | Season-level only | No (can't cover 2023-26) |
| Estimated RAPTOR (Neil Paine) | Free CSV through **2024-25**; 0.89 corr with real RAPTOR; not updated for 2025-26 (successor "LAKER" is paid Substack) | Season-level → safe as *prior-season* join | **Backtests (P3 uses this)** |
| LEBRON (BBall Index) | Free dashboards only, no export/API; $5/mo data package unclear on bulk export | Daily dashboard, no history | No |
| **DARKO DPM** | **Free, nightly, darko.app**; per-player daily series 2013→now embedded in player pages | **Yes — Kalman-style, forward-only by design** | **Production adoption target** |
| EPM (dunksandthrees) | Paid; API has historical daily | Yes (paid) | Later, if budget |
| BPM (bbref) | Free, formula public | Recompute season-to-date yourself | Fallback/complement |
| NBA `playerestimatedmetrics` | Free via nba_api (verified working here) | **No** — completed seasons return full-season values (leakage) | Only if snapshotted nightly going forward |

### 5.2 P3 experiment — prior-season Estimated RAPTOR in the player model

Design: baseline (current 135 features) vs +`PREV_ERAPTOR_{OFF,DEF,TOT,WAR82}`
(previous season, minutes-weighted across stints, normalized-name join — 87.5%
match rate every season; unmatched ≈ rookies, left NaN). 3 seeds × 3 walk-forward
folds, paired t-tests on per-row |error|, keep-gate = negative and p<0.05 in all
folds for ≥2/3 seeds — same standard as every other feature decision in this repo.

**Result: NULL — do not add these features to the player model.** Across 9
runs (3 folds × 3 seeds), mean ΔMAE per stat sits within ±0.007 (PTS −0.0068,
everything else ≤ |0.0013|); **0 of 3 seeds pass the keep-gate on any of the 11
stats**. Notably the augmented models *used* the features (gain ranks 16–30 of
139 in the MIN/PTS models) yet gained nothing out-of-sample — the classic
signature of redundant signal: L5/L10 form + usage + PREV_*36 priors already
span what a prior-season all-in-one rating knows about a player's production
level. Full tables: `docs/p3_impact_metrics_report.md` /
`outputs/p3_impact_metrics.json`.

**Interpretation, and why this does NOT kill the impact-metric idea:** counting
stats are the wrong target for a plus-minus-family metric — eRAPTOR measures
*margin impact per possession*, which is nearly orthogonal to "how many points
will he score." The team model is where that signal type belongs
(availability-weighted talent, §5.3.2 below), and DARKO's *daily* update would
additionally help exactly where a prior-season static rating can't: early-season
and post-trade windows.

### 5.3 Recommended adoption path

1. If P3 shows a real gain on any stat: build a nightly **DARKO DPM snapshot**
   stage (leaderboard CSV download into a new `player_impact_daily` table keyed
   by date) so the live model gets what the backtest proxied with eRAPTOR — and
   as-of-date joins stay leakage-free forever.
2. Independently of P3's counting-stat verdict, test DARKO/eRAPTOR as the
   **team-model availability weight**: replace netRating in
   `player_impact.py`'s Approach-B fallback and re-run
   `evaluate_impact_approaches.py` (the WITH/WITHOUT baseline correlates 0.35
   with margin swing; netRating managed 0.14 — a RAPM-family metric should beat
   both).
3. Skip LEBRON (no pipeline), skip real RAPTOR (dead), consider EPM's API only
   when a paid tier is justified by a live betting use case.

---

## 6. Bridging the Vegas gap — prioritized

**Where the gap actually is.** Best model margin MAE ≈ 11.6–11.9 vs Vegas closing
≈ 10–11 (the only clean head-to-head, E16 playoffs: Vegas MAE 11.78 / AUC 0.648 vs
RF 12.01 / 0.614 — deltas within CI). On winner accuracy the walk-forward numbers
(76–79%) already look Vegas-competitive, but window selection flatters that
comparison; margin MAE is the honest scoreboard. The books' edge comes from (a)
information you don't have (real-time injury/lineup/market flow) and (b) the
wisdom of a liquid market aggregating thousands of models. Beating *closing* lines
consistently is near-impossible; the sane goals are: close most of the MAE gap,
and find *slices* where the model is closer than the book.

Priorities, ranked by expected MAE gain ÷ effort:

1. **Availability & minutes into the team model** (biggest documented lever).
   The P2 minutes model already exists; feed "projected available talent-minutes"
   (per-team sum of projected minutes × player rating) into the game features,
   replacing binary slot flags. Vegas's biggest intraday moves are minutes news —
   this is the information class where the gap lives. Effort: medium. Expected:
   0.2–0.5 MAE.
2. **RAPM-family talent aggregates** (P3's team-level sibling, §5.3.2). Upgrades
   both the availability weighting and the roster-strength prior. Effort: low
   (data now in hand). Expected: 0.1–0.3 MAE, plus better early-season.
3. **Ensemble the three families.** Simple probability averaging (or margin
   averaging) of RF+XGB+NN is a near-free Brier/MAE win given their documented
   complementarity (RF picks, XGB/NN margins). Log it to the registry as its own
   model_type ('ens') so the dashboard tracks it. Effort: low. Expected: 0.1–0.2
   MAE, +0.5–1pp accuracy, smoother calibration.
4. **Optuna HP search under the E12 harness** (§2.4.1). Effort: low (compute-bound).
   Expected: 0–0.3 MAE — unknown until tried, but currently zero search has ever
   been done.
5. **Betting-relevant evaluation, not more accuracy chasing**: add ATS record and
   per-window |model−Vegas| to the walk-forward harness; track "model closer than
   book %" (already on /accuracy) per slice — rest asymmetry, B2B, injury-news
   games, early season. An 11.7-MAE model can still be profitable in slices where
   it disagrees with the line for identifiable reasons. Effort: low.
6. **3P-luck regression features** (§2.2.4) and travel micro-features (§2.2.3).
   Effort: low each. Expected: small but they're the kind of orthogonal signal
   that survives paired tests.
7. **Feature pruning + registry-leak fix** (§2.1) — hygiene that makes every
   later experiment cheaper and more readable, not a direct MAE play.

Anti-priorities: more seasons of history (E15 falsified), more rolling-stat
variants (E10 falsified), lineup-synergy features at current data quality (E11
falsified), further single-window model-ranking debates (E12 falsified).

---

## 7. Concrete next steps

| # | Item | Where |
|---|---|---|
| 1 | Read P3 verdicts; if keep → nightly DARKO snapshot stage + P2 feature add | `docs/p3_impact_metrics_report.md` |
| 2 | eRAPTOR/DARKO as Approach-B impact weight; re-run impact evaluation | `modeling/evaluate_impact_approaches.py` |
| 3 | Projected talent-minutes feature into team model (E22 candidate) | `data_engineering/` + `core/features.py` |
| 4 | RF+XGB+NN ensemble as model_type 'ens', registry-tracked | `modeling/predict_games.py` |
| 5 | Optuna study (walk-forward log-loss objective); `pip install optuna` | new `experiments/e23_hp_search.py` |
| 6 | Vegas MAE per window inside walk-forward harness | `experiments/e2_walk_forward.py` |
| 7 | Fix scaler fit-before-split in `_prepare_training_data` | `modeling/predict_games.py:2252` |
| 8 | Player Phase D un-park: quantile/NB heads for tails; minutes distribution | `modeling/player_projection_models.py` |
| 9 | Residual-vs-volatility + blowup/dud slices in P-harness | `experiments/p1_player_validation.py` |
| 10 | Torch OSError in dashboard process | `visualization/dataExploration.py` import path |
