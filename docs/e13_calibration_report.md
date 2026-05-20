# E13 — Probability calibration, explained with real games

_2026-05-19. Phase 2a of the uncertainty work._

This doc explains three things in plain language — **Brier score**, **ECE**, and **isotonic recalibration** — using actual model predictions from the walk-forward W5 window (test games 2026-03-15 → 2026-04-15, which the model never trained on). Then it records what we changed in the pipeline.

---

## The problem in one sentence

When the Random Forest says *"home team has a 70% chance to win,"* those games actually win about **87%** of the time. The model's probabilities are **underconfident** — it hedges toward 50/50 when it should commit.

Here's the model's own output on five real games (RF, out-of-sample):

| Game | Date | RF raw prob (home win) | What actually happened |
|---|---|---|---|
| OKC vs. MIN | 03-15 | 0.705 | OKC **won** ✓ |
| BKN vs. OKC | 03-18 | 0.212 | BKN lost (OKC won) ✓ |
| LAC vs. SAS | 03-16 | 0.507 | LAC lost (SAS won) ✗ |
| SAS vs. IND | 03-21 | 0.811 | SAS **won** ✓ |
| OKC vs. PHX | 04-12 | 0.771 | OKC **lost** ✗ |

The model is usually directionally right. The question calibration asks is narrower: **when it says 70%, does it mean 70%?**

---

## 1. Brier score — "how wrong was this probability?"

The Brier score is just **squared error, but for probabilities**. For a single game:

```
brier = (predicted_probability − actual_outcome)²
```

where `actual_outcome` is 1 if the home team won, 0 if it lost.

Take **OKC vs. MIN** (RF said 0.705, OKC won so actual = 1):

```
brier = (0.705 − 1)² = (−0.295)² = 0.087
```

A perfect 1.0 prediction would have scored 0. A wrong-and-confident 0.0 would have scored 1.0 (the worst possible). So 0.087 is "pretty good, but it should have been more confident."

The **Brier score of the model** is just the average of this over all games. Lower is better. It rewards two things at once: being *right* (correct direction) and being *appropriately confident* (not hedging, not overcommitting). On W5: RF raw Brier = **0.176**.

**Why it matters:** a model can have good accuracy but a bad Brier score if its probabilities are dishonest — and the probability is what you'd use to decide *how much to trust* a given pick.

---

## 2. ECE (Expected Calibration Error) — "across all games, how far off are the probabilities?"

Brier mixes "right/wrong" with "confidence." ECE isolates **just the calibration** — the gap between stated probability and reality.

How it's computed:
1. **Bin** the games by predicted probability: the 0.2–0.3 bin, the 0.3–0.4 bin, etc.
2. In each bin, compare the **average predicted probability** to the **actual win rate**.
3. ECE = the average of those gaps, weighted by how many games fall in each bin.

Here's the RF's actual reliability table on W5 (this is the evidence behind "underconfident"):

| Predicted bin | # games | avg predicted | actual win rate | gap |
|---|---|---|---|---|
| 0.2–0.3 | 22 | 0.264 | 0.045 | **+0.218** (overconfident) |
| 0.3–0.4 | 21 | 0.344 | 0.095 | **+0.249** (overconfident) |
| 0.4–0.5 | 44 | 0.457 | 0.432 | +0.026 (good) |
| 0.5–0.6 | 40 | 0.553 | 0.700 | **−0.147** (underconfident) |
| 0.6–0.7 | 47 | 0.647 | 0.787 | **−0.140** (underconfident) |
| 0.7–0.8 | 46 | 0.749 | 0.870 | **−0.120** (underconfident) |
| 0.8–0.9 | 10 | 0.808 | 0.900 | −0.092 (underconfident) |

Read the 0.7–0.8 row: the model said ~0.75 on 46 games, but 87% of them actually won. It was under-selling its own picks by 12 points. Meanwhile in the 0.2–0.4 range it was *over*-confident — saying "30%" on games that only won 9% of the time.

ECE rolls all those gaps into one number: **RF ECE = 0.131**. Loosely, "the model's stated probabilities are off by ~13 percentage points on average." For comparison, XGB's ECE was 0.092 — milder, but the same underconfident-in-the-middle shape.

**Why RF is the worse offender:** the E1 regularization (`max_depth=5, min_samples_leaf=20`) deliberately made each tree shallow to stop overfitting. A side effect: shallow trees produce probabilities bunched near 0.5, so the forest rarely says "90%." That helped generalization but made the probabilities timid.

---

## 3. Isotonic recalibration — "learn the correction and apply it"

If the model reliably says 0.70 when reality is 0.87, you can just **learn that correction from past games and apply it going forward.** That's isotonic recalibration.

"Isotonic" means **monotonic** — the correction is only allowed to be order-preserving: a higher raw probability always maps to a higher (or equal) calibrated probability. It can stretch and bend the scale, but it can never flip two games' ordering. That's the right constraint, because we trust the model's *ranking* of games (its AUC is fine); we only distrust the *numbers it attaches*.

Mechanically:
1. Take a **held-out calibration set** the model didn't train on (we use the most recent 20% of games — ~1,260 of them).
2. Learn a step function mapping `raw probability → observed win frequency`.
3. Store it, and pass every future prediction through it.

Here's the actual learned RF map now baked into production:

| RF raw says | calibrated to |
|---|---|
| 0.20 | 0.00 |
| 0.35 | 0.22 |
| 0.50 | 0.53 |
| 0.55 | 0.54 |
| 0.65 | **0.73** |
| 0.75 | **0.84** |
| 0.85 | 1.00 |

So **OKC vs. MIN** (raw 0.705) now reports **~0.84** instead of 0.70 — much closer to the 87% these games actually win. Re-scoring its Brier:

```
raw:        (0.705 − 1)² = 0.087
calibrated: (0.84  − 1)² = 0.026     ← better
```

Across all of W5, isotonic **roughly halves RF's ECE (0.131 → 0.074)** and improves its Brier (0.176 → 0.166). XGB improves more modestly (ECE 0.092 → 0.081).

### The honest caveat: confident misses get *worse*

Calibration fixes the *average*, not every individual game. Look at **OKC vs. PHX** (raw 0.771, but OKC **lost**):

```
raw:        (0.771 − 0)² = 0.594
calibrated: (0.84  − 0)² = 0.706     ← worse on this one
```

Because the recalibrator pushes confident predictions even more confident, the rare confident-but-wrong games are penalized harder. That's expected and correct: on average, across many games, you come out ahead — but recalibration is not a crystal ball, and a model that's *systematically* wrong in some context (e.g. playoffs) will have its errors *amplified*, not hidden. That property is exactly what makes calibration a good cross-context diagnostic for Phase 1.

---

## What changed in the pipeline

- **`modeling/predict_games.py`**:
  - New `IsotonicCalibratedClassifier` wrapper — holds the base model + an `IsotonicRegression` map, exposes the same `predict_proba` / `predict` interface so every existing call site gets calibrated probabilities with no signature change. Other attributes (`feature_importances_`, etc.) delegate to the base model; SHAP runs on the regressor so it's unaffected.
  - Both RF and XGB training now fit the calibrator on the eval model's out-of-sample 20% holdout, then wrap the production model. The calibrator is also stored in the bundle under `clf_calibrator` for inspection.
  - Pickle-safe: `__getattr__` guards against the unpickling recursion trap.
- **`experiments/e13_calibration.py`** — the reusable diagnostic (reliability bins + ECE + Brier, raw vs isotonic). Re-run after any model change to confirm calibration hasn't drifted.

### Caveats / follow-ups
- Calibration coverage assumes the future looks like the calibration window. The Phase 1 regular-vs-postseason study will test exactly that — if playoff ECE jumps, the regular-season calibrator is the wrong map for playoffs.
- AUC is unchanged by calibration (monotonic transform preserves ranking); accuracy can shift by a game or two because the 0.5 threshold lands at a different raw probability. This is expected.
- The classifier is now calibrated; the **regressor** (point margin) is next — Phase 2b adds prediction intervals so each margin comes with an honest range, not just a point estimate.
