# E15 — Cross-context generalization (Phase 1)

_2026-05-19. Uses the E13 (calibration / ECE) + E14 (conformal coverage) instruments
built in Phase 2 as the measuring tools. Two questions._

---

## Q1 — How much data does the model need? (learning curve)

Fix the test set (W5, 226 regular-season games, 2026-03-15 → 04-15). Vary how far
back training reaches. 5 seeds, RF + XGB, production 567-feature config.

| Train window | n_train | RF acc | RF MAE | RF ECE | RF cov90 | XGB acc | XGB MAE |
|---|---|---|---|---|---|---|---|
| ~0.5 season (since 2025-10) | 819 | 0.745 | 12.38 | 0.063 | 0.91 | 0.724 | 13.19 |
| ~1 season (since 2025-03) | 1,018 | **0.765** | **11.92** | 0.090 | 0.91 | 0.753 | 12.59 |
| ~2 seasons | 2,064 | 0.745 | 11.99 | 0.084 | 0.92 | 0.737 | 12.26 |
| ~3 seasons | 3,071 | 0.744 | 12.06 | 0.095 | 0.91 | 0.751 | 12.14 |
| all (~4 seasons) | 4,548 | 0.765 | 11.92 | 0.094 | 0.89 | 0.777 | 11.94 |

**Finding: the curve is flat past ~1 season.** Going from 1 season (~1,000 games)
to 4 seasons (~4,500) — 4.5× more data — buys essentially nothing for RF (acc
0.765 → 0.765, MAE 11.92 → 11.92). XGB inches up at full data but within the
noise band we measured in E12 (±5pp). Even half a season (~800 games, roughly the
first ~2 months of a new season across the league) already lands at acc ~0.745 /
MAE ~12.4.

**Why:** older seasons carry different rosters and league dynamics (concept
drift), so additional *old* data is roughly neutral — it neither helps nor hurts.
The model saturates on recent data.

**Answer to "how many months of a new season before the model is trustworthy?"**
Roughly **2-3 months / ~1 season-equivalent of games**. After that, more history
is not the binding constraint — feature quality is. (This rigorously confirms the
coarse E3 finding that the learning curve had flattened.) Coverage and ECE are
stable across all train sizes, so the uncertainty machinery is robust to how much
data you train on.

---

## Q2 — Can a regular-season model be trusted in the playoffs?

For each season (2022-2026), train on **regular-season games strictly before that
season's playoffs**, fit the isotonic calibrator + conformal intervals on a
held-out tail, then score three test sets that all occur *after* training:
- **regular** (control): the last 3 weeks of that season's regular games
- **play-in**
- **playoffs**

Predictions pooled across seasons (first seed). ~400 playoff test games.

| Model | Regime | n | Accuracy | AUC | MAE | ECE | cov80 | cov90 |
|---|---|---|---|---|---|---|---|---|
| **RF** | regular (control) | 631 | **0.713** | **0.790** | 11.93 | 0.024 | 0.79 | 0.90 |
| RF | play-in | 30 | 0.600 | 0.469 | 11.08 | 0.316 | 0.77 | 0.90 |
| RF | **playoffs** | 403 | **0.635** | **0.637** | 12.10 | 0.050 | 0.78 | 0.88 |
| **XGB** | regular (control) | 631 | 0.691 | 0.781 | 11.90 | 0.040 | 0.81 | 0.90 |
| XGB | play-in | 30 | 0.700 | 0.703 | 11.58 | 0.168 | 0.83 | 0.97 |
| XGB | **playoffs** | 403 | 0.620 | 0.600 | 12.23 | 0.077 | 0.81 | 0.90 |

### The headline: a split verdict

**Winner prediction degrades sharply in the playoffs.**
- Accuracy: RF 0.713 → **0.635** (−7.8pp); XGB 0.691 → **0.620** (−7.1pp).
- AUC (ranking ability) collapses: RF 0.790 → **0.637** (−0.15); XGB 0.781 → **0.600** (−0.18).

The model is meaningfully worse at picking playoff winners. A "71% regular-season
model" is really a ~63% model once the playoffs start.

**But uncertainty quantification holds up.**
- Coverage: playoff cov90 = 0.88 (RF) / 0.90 (XGB) — essentially nominal.
- MAE barely moves (11.93 → 12.10); ECE stays low (0.024 → 0.050).

So the **margin intervals remain honest in the playoffs** even though the
point/ranking accuracy drops. This is exactly the distinction the coverage
instrument was built to expose: the *spread* of playoff outcomes is similar to the
regular season (so the conformal bands still cover ~90%), but the *predictability
of the winner* drops (so AUC craters).

### Why playoffs are harder (feature distribution shift)

KS test, regular control vs playoffs, averaged over seasons:

| Feature | KS stat | mean p | shifted? |
|---|---|---|---|
| DIFF_ELO | 0.219 | 0.029 | **yes** (significant) |
| HOME_pace_L10 | 0.259 | 0.064 | borderline (slower playoff pace) |
| DIFF_netRating_L10 | 0.165 | 0.136 | mild |
| DIFF_PTS_L10 | 0.147 | 0.276 | no |

Playoffs are a **restricted, harder subset**: only the stronger teams, more evenly
matched (the significant ELO-gap shift), playing slower, grind-it-out basketball
(the pace shift), with series-specific adjustments the model has never seen. Less
talent disparity to exploit → lower AUC. The model isn't broken; it's being asked
to predict a genuinely less-predictable game.

### Play-in caveat

The play-in numbers (n=30, 6 games × 5 seasons) are **too small to trust** — RF's
AUC of 0.469 and ECE of 0.316 are within sampling noise for that sample size.
Directionally, single-elimination play-in looks even less predictable than
playoffs, which is plausible, but we can't claim it with this n.

---

## Recommendations

1. **Set playoff expectations explicitly.** When the dashboard predicts playoff
   games, the win-probability should be understood as ~63% reliable, not ~71%.
   Consider a "playoff mode" banner that widens displayed confidence or annotates
   the degraded discrimination.
2. **Trust the intervals in the playoffs.** The conformal margin bands and the
   calibrated probabilities transfer well (coverage ~90%, ECE low), so the
   *uncertainty* story remains honest even where the *point* prediction weakens.
3. **Don't chase more historical data.** The learning curve says ~1 season is
   enough; the next gains come from better features, not more rows.
4. **Future: playoff-specific signal.** Series state (game number, series score),
   playoff rest patterns, and matchup-repeat effects are the natural features to
   close the playoff AUC gap — and the (dropped) lineup features would plausibly
   matter more here, where rotations shorten. A playoff-specific calibrator/model
   is worth testing once those features exist.

Artifacts: `experiments/e15_cross_context.py` (both modes, reusable),
`outputs/e15_learning_curve.json`, `outputs/e15_regime.json`.
