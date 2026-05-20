# Post-E11 synthesis: where we are, what's next, why MAE=5 is a wall

**Date**: 2026-05-19
**Status**: End of E1–E11 sprint. E5 (Vegas baseline) implemented but reporting deferred. All models retrained on the full E11 feature set.

---

## Headline numbers (W5: 2026-03-15 → 2026-04-15, 230 games)

| Model | Accuracy | AUC | MAE | RMSE |
|---|---|---|---|---|
| **XGB** | **80.0%** | **0.845** | **11.86** | (computed in JSON) |
| RF | 78.7% | 0.830 | 11.90 | |
| NN | 78.7% | 0.827 | 11.86 | |
| Pure-ELO baseline | ~66.4% | — | — | |
| Vegas (closing-line implied prob ≥ 50%) | ~70% | ~0.75 | ~10–11 | |

XGB hitting **80% W5 accuracy** is the highest the project has ever measured and clears the long-standing ~77% ceiling.

MAE at ~11.9 points is **~1–2 points worse than Vegas** and **~7 points worse than the target**.

---

## E1–E11 trajectory at a glance

| Experiment | Headline change | W5 RF acc | W5 XGB acc | W5 NN acc |
|---|---|---|---|---|
| E0 (baseline, pre-E1) | 1-season CSV, no XGB | 76.2% | n/a | 68.3% |
| E1 (regularize) | RF capacity ↓, NN dropout ↑, seed | 74.9% | n/a | ~68% |
| E2 (walk-forward) | (diagnostic; no model change) | 74.8% | n/a | varied |
| E3 (XGB + 4-season backfill) | +xgb model, 7342 games | ~74% | ~77% | 0.426* |
| E4 (ensemble) | (backlogged) | — | — | — |
| E5 (Vegas baseline) | NOT a feature; dashboard tile | — | — | — |
| E6 (NN stabilization) | Eliminated by E8 | — | — | — |
| E7 (pre-game injury data) | `historical_injury_report` table | 75.2% | 77.0% | 75.7% |
| E8 (slot-feature dedup) | -75 garbage cols → cleaner vec | 74.8% | 77.4% | 73.5% |
| E9 (ELO) | +4 features | (no effect — routing bug) | — | — |
| E10 (opp-strength adj.) | +18 features (OPP_ADJ, ALLOWED) | 76.5% | 77.4% | 76.1% |
| **E11** (LINEUP + ELO-fixed) | +27 LINEUP cols, +4 ELO cols | **78.7%** | **80.0%** | **78.7%** |

*E3 NN crash was the slot-feature bug; not real.

**Net E0 → E11**: +2.5pp to +12pp accuracy depending on model; MAE held roughly flat (~12 → ~11.9), which is concerning — see below.

---

## What didn't move much: MAE

Accuracy went up; MAE barely budged. This is the central diagnostic finding of the sprint.

- E0: ~12 (single-season, smaller train)
- E7: 11.57 (XGB W5; best in the table)
- E11: 11.86 (XGB W5)

Why is MAE stuck around 11.5–12 while accuracy climbs?

1. **The features improving accuracy don't reduce variance**. ELO, LINEUP, and OPP_ADJ help the model pick winners but don't sharpen point-margin estimates much. A model that confidently picks the right team but is consistently 12 points off on the margin will have great AUC and middling MAE.
2. **The NN regressor has been the MAE leader most of the sprint** (E7 had it at 11.5–11.8). At E11 it regressed to 11.86 with LINEUP added — likely the 57% NaN-imputed lineup columns adding noise to the regressor head specifically. Tree models clip outliers better.
3. **Vegas hangs around 10.5–11 MAE** on the same data per the Kaggle dataset. That's the practical floor for box-score-informed models.

---

## Why MAE = 5 is a wall (and what it would actually require)

The user's "way too optimistic" instinct was correct. Some context on the irreducible-variance floor for NBA point-margin prediction:

### The arithmetic of the wall

- **NBA game point-margin standard deviation**: ~13 points (empirical, all games 2022–2026 in our `game_list`).
- **Vegas closing-line MAE**: ~10–11 points. Vegas has access to insider info we *cannot* get (final inactives 60 min pre-tip, day-of weather and travel disruptions, betting market signal itself).
- **Theoretical floor for tabular models on box-score + roster data**: ~9.5–10 MAE. Below that, you're trying to predict noise (refs, bounces, late-game variance, shot luck on a 100-possession sample).
- **MAE = 5 means**: predicting the final margin within 5 points on 50% of games. That's roughly the accuracy of *announcers' second-quarter calls when they can already see how the game is going* — i.e., it's not a pre-game prediction problem at all.

### What it would take to even approach MAE = 8 (still very ambitious)

1. **Same-day starting lineup confirmation** (T-30 min): currently we have injury report data, but not "who is actually starting". Worth ~0.3 MAE.
2. **Same-day player-vs-player matchup awareness**: which star is being shut down by which defender? Requires lineup tracking + defender assignment data. ~0.3 MAE.
3. **In-game state**: not pre-game; can't help here unless we redefine the problem.
4. **Bayesian uncertainty per prediction**: not MAE-reducing per se, but lets us report 60% confidence intervals so the user can act on the *good* predictions (where the model is confident) and ignore the bad ones. **This is the highest-value next move and the user already has it on the backlog.**
5. **Ensemble + stacking** (E4, currently backlogged): empirically 0.1–0.3 MAE.
6. **Per-team / per-coach effects**: 30 teams × ~80 games/season is too sparse for full team-level modeling without overfitting; could add as random effects in a hierarchical model. ~0.2 MAE.

Add all of those up: 11.86 → ~10.5 MAE. Below Vegas — possible but at the boundary of what tabular box-score models can do.

### What gets you below 10 (research-grade territory)

- Real-time tracking data (player coordinates, second-by-second). Not available without paid feeds.
- Wearable / biometric data on fatigue. Not available.
- Betting-line itself as feature (you become a Vegas mirror, not a Vegas competitor).
- Game-state simulation (Monte Carlo over remaining possessions). Doesn't apply pre-game.

**Recommended target**: MAE ≤ 10.5 by end of next sprint. Treat MAE = 8 as a 2026-Q4 stretch goal. Treat MAE = 5 as a thought-experiment, not a target.

---

## Ranked next-experiment ideas

Ranked by expected lift × implementation cost. Confidence in parens.

### High-confidence, low-cost (do these next)
1. **Centralize feature-pattern allow-list** (1 hour). Collapse the 3 separate lists into one. Prevents another silent ELO-style bug. **(High)**
2. **Re-measure E1–E8 with the deduplicated dataset** (1 day). 14% of training rows were duplicates pre-E10. Some of the older "improvements" may have been dupe-driven. **(High)**
3. **Pre-2024 lineup backfill via stats.nba.com HTML scrape** (1–2 days). Would lift LINEUP coverage from 43% → ~95% and likely close XGB's accuracy gap further. **(High)**
4. **Per-model NaN handling investigation** (1 day). NN regressor MAE worsens when imputed-NaN features are added; tree models don't. Possible NN-only fix: use a NaN indicator column + zero-fill instead of median-imputing. **(Medium)**

### Medium-confidence, medium-cost (after the cleanup pass)
5. **E4 ensemble** (1 day). Simple-average classifier probabilities, weighted-average margin. Literature says +0.2–0.3 MAE consistently. **(Medium)**
6. **Bayesian / calibrated uncertainty per prediction** (1 week). Read out a confidence interval on each game. Highest *product* value of any item here — turns a single MAE number into a dashboard with action-aware predictions. **(High)**
7. **Hierarchical team / coach random effects** (1 week). Adds team-level shrinkage without making the model team-specific. ~0.2 MAE. **(Low–Medium)**

### Speculative, expensive
8. **Same-day starting lineup scrape from beat-writer Twitter/RSS feeds** (1–2 weeks). Frontier of what's possible without paid data. **(Low–Medium)**
9. **Defender-assignment matchup features** (1 month). Would require new ingestion of `LeaguePlayerTrackingPtShots` and similar. **(Low)**
10. **Switch the regressor head to a quantile loss** (1 day). Optimizes for median rather than mean — different MAE-vs-bias trade. Worth a side experiment. **(Low)**

---

## What we shipped (artifacts)

| Path | Purpose |
|---|---|
| `data_engineering/historical_injury_scraper.py` | E7 — pre-game injury PDF scraper, 106,755 rows |
| `data_engineering/player_impact.py::bulk_fetch_pregame_availability` | E7 — uses scraped data instead of post-game boxscore |
| `data_engineering/feature_engineering.py::add_opponent_adjusted_rolling_features` | E10 — opp-strength adjustment for L10 stats |
| `data_engineering/compute_elo.py` | E9 — 538 ELO with pre-game point-in-time correctness |
| `data_engineering/lineup_features.py` | E11 — month-end LeagueDashLineups snapshotter |
| `data_engineering/vegas_lines_kaggle_import.py` | E5 — historical Vegas backfill (Pinnacle/SBR consensus) |
| `data_engineering/vegas_lines_espn.py` | E5 — current Vegas lines (DraftKings via ESPN) |
| `visualization/dataExploration.py` | E5 — dashboard Vegas overlay + model-vs-Vegas MAE comparison |
| `experiments/e2_walk_forward.py` | E2 — 5-window walk-forward harness; updated for ELO + LINEUP |
| `docs/model_tuning_log.md` | Master experiment log with full E1–E11 table |

DB tables added: `historical_injury_report`, `team_elo_pregame`, `vegas_lines`, `team_lineup_snapshots`.

---

## Open questions for next session

1. **Is the 80% W5 number stable?** One walk-forward measurement on a 230-game window has noise on the order of 1–2pp. Worth re-running W5 a few times with different random seeds to bound the variance before declaring victory.
2. **Should we backport the E10 dedup to E1–E8 results?** The honest answer is yes, but it's a few hours of re-runs.
3. **What's the right primary metric?** The dashboard reports accuracy, AUC, MAE, RMSE. The user's stated goal is MAE-driven. If MAE is the north star, the model selection criterion in `_save_versioned_and_current` needs to weight it more heavily than it currently does.
