# Plan: improving playoff predictions

_2026-05-19. Follows the E15 cross-context finding that a regular-season-trained
model drops from ~71% → ~63% accuracy and AUC 0.79 → 0.64 on playoff games, while
its margin intervals and probability calibration still transfer (~90% coverage)._

---

## What we're actually fighting

E15 diagnosed *why* playoffs are harder, and it's mostly structural, not a bug:

1. **ELO-compressed field** — only strong, evenly-matched teams remain (KS test on
   `DIFF_ELO`, regular vs playoff, p=0.029). Less talent gap to exploit → lower AUC.
2. **Slower, grind-it-out pace** (KS on `HOME_pace_L10`, borderline) — different game.
3. **Series dynamics** — repeated matchups, in-series adjustments, must-win games.
   The model has *zero* awareness it's in a series; every playoff game looks like an
   isolated regular-season game to it.
4. **Shorter rotations** — stars play more, benches shrink. (This is exactly where the
   dropped E11 lineup features *might* matter — see Track B.)

**A blunt truth up front:** some of the AUC drop is irreducible. Closer games are
inherently less predictable — even Vegas does worse on playoffs. So **Step 0 is to
measure the ceiling** before investing, and set a realistic target (likely AUC
~0.68–0.70, not back to 0.79).

**Hard constraint:** only ~400 playoff games total (~80/season × 5). Too few to train
a 567-feature playoff-only model without severe overfitting. So the strategy favors
*conditioning the shared model on playoff context* over *building a separate model*.

---

## Step 0 — Establish the ceiling (DONE 2026-05-19, `experiments/e16_playoff_ceiling.py`)

Head-to-head, model vs Vegas closing line, on the **same 337 playoff games** that have
a Vegas line (of 403; per-season temporal training as in E15, 5 seeds, calibrated):

| | Accuracy | AUC | MAE |
|---|---|---|---|
| RF model | 0.620 | 0.614 | 12.01 |
| XGB model | 0.611 | 0.607 | 12.15 |
| **Vegas (closing line)** | **0.647** | **0.648** | **11.78** |

Bootstrap deltas (model − Vegas), 2000 resamples:
- RF: AUC −0.034 (95% CI [−0.086, +0.016]), MAE +0.23 ([−0.14, +0.58]), acc −0.027 ([−0.074, +0.018])
- XGB: AUC −0.040 ([−0.104, +0.025]), MAE +0.38 ([−0.09, +0.87]), acc −0.035 ([−0.089, +0.021])

**The decisive findings:**

1. **Vegas itself only manages ~0.648 AUC / 64.7% accuracy on playoff games.** The
   sharpest predictor available — with insider injury news and market money — drops to
   ~65% in the playoffs. **Playoff outcomes are irreducibly hard.** The ceiling is ~0.65,
   not 0.79.
2. **Our model is within statistical noise of Vegas on playoffs.** Every model−Vegas
   delta has a 95% CI that crosses zero. We trail by a consistent ~3-4pp AUC, but it is
   *not* significant. We are essentially matching the market on the postseason.

**Revised conclusion:** the room to improve playoff *point* prediction is small (≤~3-4pp
AUC, to merely match Vegas, and that gap isn't significant). The headline value was the
honest *uncertainty* presentation (E13/E14, shipped) and the playoff flag (shipped).
**Cap the investment.** See the revised sequence below.

---

## Track A — Playoff-context features (primary lever)

Give the shared model awareness that it's in a series. All derivable from data we have
(GAME_ID prefix tags playoffs; series state from chronological ordering within a
team-pair inside a playoff period — robust, no GAME_ID-internal decoding needed).

| Feature | What it captures | Derivation |
|---|---|---|
| `SERIES_GAME_NO` (1–7) | Game 1 ≠ Game 5 dynamics | Nth chronological game between the pair in this playoff period |
| `SERIES_SCORE_DIFF` | who's ahead / desperation | running W−L in the series before this game |
| `IS_ELIMINATION` / `IS_MUST_WIN` | do-or-die intensity | series score == 3 losses for a side |
| `SERIES_HCA` | seeding home-court (≠ single-game home/away) | which team has more series home games remaining |
| `SERIES_H2H_MARGIN` | in-series adjustment signal | mean point margin in prior games of *this* series |
| `PLAYOFF_REST_DAYS` | irregular playoff rest (1–4 days) | days since each team's previous game |

These let the model learn playoff-specific behavior *without* a separate model. Add as
new feature columns (gated to playoff rows; NaN/0 for regular season so the regular
model is unaffected).

**Evaluation:** reuse the E15 `regime` harness as the test bed — add features, re-run,
paired-compare on the pooled ~400 playoff games (must clear the E12 noise bar). Effort:
~2–3 days incl. the feature engineering + a feature-build.

---

## Track B — Re-test E11 lineup features, playoff-restricted

E11 (LeagueDashLineups 5-man synergy) was dropped in E12 because it didn't help
*overall*. But rotations shorten in playoffs, so it may help *there specifically*.

- Re-run the E12-style ablation but **measure only on playoff test games**.
- If lineup features show a significant playoff AUC/MAE gain (paired test) → re-enable
  them gated to playoffs (or globally if it doesn't hurt regular season).
- This is a targeted re-test, not a blanket re-add. Reuses existing `team_lineup_snapshots`
  + the `core.features` toggle (`enable_e11=True`). Effort: ~1 day.

Caveat: lineup snapshot coverage was 43% and 2024+ only — playoff coverage may be thin.
Check coverage on playoff dates first.

---

## Track C — Playoff-aware uncertainty refinement (secondary)

E15 showed calibration/coverage already transfer well (playoff cov90 ~0.90, ECE ~0.05),
so the upside is small — but cheap to check:

- Fit a **playoff-specific conformal half-width** and isotonic calibrator on playoff
  holdout; compare coverage/ECE vs the regular-season one. Only adopt if it measurably
  tightens intervals or improves ECE.
- Effort: ~half a day. Low priority given current transfer is good.

---

## Track D — Domain-weighted training (experimental)

Upweight playoff + playoff-like (close-ELO, low-pace) regular-season games during
training so the shared model fits the hard regime better.

- Risk: trades regular-season accuracy for playoff accuracy. Measure both.
- Effort: ~1 day. Pursue only if Tracks A/B underdeliver.

---

## Track E — Dedicated playoff model (future / low priority)

A separate playoff-only model is **not advisable yet** — ~400 games can't support 567
features without overfitting. Revisit once more playoff seasons accumulate, or with an
aggressively reduced feature set (e.g., just ELO + series state + rest). Park it.

---

## Recommended sequence — REVISED after Step 0

Step 0 changed the picture: the ceiling is Vegas's ~0.65 AUC, and we're already within
noise of it. So the aggressive build is **not** justified. Revised plan:

1. **Step 0 — DONE.** Ceiling ≈ 0.65 AUC; model within noise of Vegas. *(complete)*
2. **Track A (series-context features) — DONE 2026-05-19, `experiments/e17_series_eval.py`.**
   Built 8 series features (`SERIES_GAME_NO`, `HOME/AWAY_SERIES_WINS`, `SERIES_WIN_DIFF`,
   `HOME/AWAY_FACES_ELIM`, `HOME_HAS_HCA`, `SERIES_PRIOR_MARGIN_HOME`) in
   `data_engineering/series_context.py` → `playoff_series_context` table → joined at build.
   Evaluated by training on ALL games (incl. prior playoffs) before each test season's
   playoffs, paired with-vs-without on the same 316 playoff games (2023-26; 2022 excluded
   for thin pre-playoff training), 5 seeds.

   **Result: no significant improvement.** RF ΔAUC −0.014 (CI [−0.042, +0.012]), McNemar
   p=0.33; XGB ΔAUC +0.007 (CI [−0.033, +0.049]), McNemar p=0.89 (26/26 net), MAE flat-to-
   worse. Vegas on the same games still 0.647 — the gap didn't close. **Dropped from
   production** (`ENABLE_SERIES_DEFAULT=False`); build code + table retained for re-eval as
   more playoff seasons accumulate. This confirms the E16 ceiling: even the most principled
   playoff-structure features can't beat the irreducible variance.
3. **Track B (lineup re-test), C, D, E — SHELVED.** Not worth it given the ceiling.
   Re-open only if Track A surprises to the upside.

**Realistic target (revised down):** playoff AUC ~0.65 (matching Vegas), from 0.61–0.64.
Anything beyond that is fighting irreducible variance. The real wins are already
shipped: honest intervals/calibration that *transfer* to playoffs (E13/E14) and the
playoff caveat banner (GUI distinct-ifier).

**Decision point:** given the gap to Vegas is non-significant, it is entirely defensible
to **stop here** and treat playoff prediction as "solved to the ceiling, presented
honestly." Track A is a nice-to-have, not a need.

All evaluation uses the E15 `regime` harness + E12 paired-test discipline. No feature
ships on a single-run delta.
