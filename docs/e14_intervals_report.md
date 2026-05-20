# E14 — Prediction intervals for the point margin (Phase 2b)

_2026-05-19. Companion to E13 (probability calibration). Where E13 made the
**win probability** honest, E14 puts an honest **range** around the predicted
**margin**._

---

## The problem

The regressor outputs one number: "home by 4.6." That hides how uncertain it
is. A 4.6 in a tight, predictable matchup is very different from a 4.6 in a
volatile one — but the bare point estimate looks identical. We want:

> "Home by 4.6 — 80% chance the actual margin lands in [−14, +23]."

…with that 80% being a *validated* 80%, not a guess.

---

## Method: split conformal (and why not CQR)

We tested two ways to build the interval, simplest first.

**Split conformal (constant width).** Train the regressor, then look at how
wrong it was on a held-out calibration set (games it didn't train on). The 80th
percentile of those absolute errors is the half-width `q`; the interval is
`[prediction − q, prediction + q]`. Under mild assumptions this covers ~80% of
real outcomes. Same width for every game.

**CQR (adaptive width).** Train extra models to predict the 10th and 90th
percentile of the margin directly, then conformally adjust them so the band is
*wider for genuinely uncertain games and narrower for predictable ones* — while
keeping the coverage guarantee.

We validated **empirical coverage** on the W5 test set (does the 80% interval
actually contain ~80% of real margins?), 5 seeds, production 567-feature config.

| Method | Nominal | Empirical coverage | Mean width (pts) |
|---|---|---|---|
| RF split-conformal | 80% | 74.7% ± 0.3 | 36.4 |
| RF split-conformal | 90% | 91.7% ± 0.4 | 50.3 |
| XGB split-conformal | 80% | 77.6% ± 1.4 | 37.6 |
| XGB split-conformal | 90% | 91.6% ± 0.8 | 49.9 |
| XGB **CQR** | 80% | 77.7% ± 0.8 | **39.3** |
| XGB **CQR** | 90% | 90.8% ± 0.9 | **52.9** |

Two findings:

1. **Coverage is honest.** The 90% intervals contain ~91–92% of actual margins
   (slightly conservative); the 80% intervals land at 75–78%. The mild
   under-coverage at 80% is the expected price of the time-series exchangeability
   assumption being only approximately true.
2. **CQR's adaptivity buys nothing here — it's actually a touch worse.** Same
   coverage, *wider* intervals than constant-width split conformal, plus two
   extra models to train. NBA margin variance is roughly the same game to game
   (homoscedastic), so there's little per-game width to exploit. Per the
   noise-aware ethos (don't add machinery that doesn't earn its keep), **we ship
   split conformal.**

---

## The sobering part: the intervals are wide

An 80% interval is about **±18 points**; a 90% interval about **±25**. Real
games (CQR 80%, margin = home − away):

| Game | 80% interval | actual | |
|---|---|---|---|
| OKC vs. MIN (03-15) | [−10, +26] | +13 | ✓ inside |
| LAC vs. SAS (03-16) | [−14, +22] | −4 | ✓ inside |
| ORL vs. OKC (03-17) | [−23, +15] | −5 | ✓ inside |
| SAC vs. SAS (03-17) | [−24, +16] | −28 | ✗ blowout, missed |
| BKN vs. OKC (03-18) | [−27, +11] | −29 | ✗ blowout, missed |
| SAS vs. PHX (03-19) | [−12, +26] | +1 | ✓ inside |

This isn't a modeling failure — it's the **irreducible variance of basketball.**
The standard deviation of NBA game margins is ~13–14 points; no pre-game model
(ours or Vegas) can shrink an 80% band below roughly ±17 without lying about its
coverage. The honest takeaway for the dashboard: *"we can tell you the favorite
and roughly by how much, but any single game can swing ~2 possessions in either
direction and still be 'normal.'"* The two misses above were blowouts that beat
even the 80% band — exactly the ~20% of games you'd expect to fall outside.

---

## What changed in the pipeline

- **`modeling/predict_games.py`**:
  - `ConformalRegressor` wrapper — `predict()` unchanged (point estimate),
    `predict_interval(X, level)` returns the conformal `[lo, hi]`. Other
    attributes (`estimators_`, `feature_importances_`) delegate to the base.
  - RF and XGB training compute the half-widths from the eval regressor's 20%
    out-of-sample holdout residuals and wrap the production regressor. Stored in
    the bundle under `conformal_halfwidths`.
  - `predict_with_rf` / `predict_with_xgb` now emit `margin_interval_80` and
    `margin_interval_90` in their output dicts (additive — nothing else changed).
  - SHAP runs on the *regressor*, so its two `TreeExplainer` call sites unwrap
    via `getattr(reg, '_base', reg)`.
- **`experiments/e14_intervals.py`** — the reusable coverage-validation harness
  (split conformal vs CQR, multiple seeds, 80%/90% levels).

### Caveats / follow-ups
- Half-widths are learned on the eval (80%-data) model and applied to the
  full-data production model. Since the full-data model fits slightly tighter,
  the intervals are marginally *conservative* — the safe direction for coverage.
- Coverage assumes the future resembles the calibration window. The Phase 1
  regular-vs-postseason study will test whether playoff margins blow past the
  regular-season intervals (almost certainly wider variance there).
- **Phase 2c (done 2026-05-19):** rendered on the dashboard's Game Predictions tab.
  The margin chart now shows, per matchup: the model's distribution (violin), the
  split-conformal 80% (thick) / 90% (dotted) intervals, and the gold Vegas marker —
  the "distribution vs Vegas" view from E5. The win-probability table/picks/bar chart
  now display the **E13 isotonic-calibrated** probability (hover shows the raw
  margin-derived value too). Notable: for RF the raw tree-vote win prob can sit ~25pp
  above the calibrated classifier prob (e.g. 86% raw → 60% calibrated) — the calibrated
  value is the validated one and is now the headline.
