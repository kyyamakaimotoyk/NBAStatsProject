# SHAP Feature Importance - Example Outputs

## Console Output Example (predict_games.py)

### Command
```bash
python predict_games.py --date 2024-12-15
```

### Full Output for One Game

```
Processing: NOP @ IND

=====================================================================================
NBA GAME PREDICTIONS FOR 2024-12-15 (Random Forest)
=====================================================================================

Matchup                   Pick           Win Prob       Margin  Uncertainty
-------------------------------------------------------------------------------------
NOP @ IND                 IND              73.2%     +7.4 pts       +/-6.8

  Top 10 factors driving this prediction:
     1. + Home team advantage in netRating (L10) (+1.90 pts)
     2. + Home team advantage in PLUS_MINUS (L10) (+0.71 pts)
     3. + Home team advantage in PIE (L10) (+0.58 pts)
     4. - Away team advantage in AWAY_WIN_PCT (L10) (-0.48 pts)
     5. + Home team advantage in defendedAtRimFieldGoalsAttempted (L10) (+0.25 pts)
     6. + Home team advantage in WIN_PCT (L10) (+0.19 pts)
     7. - Away team advantage in defendedAtRimFieldGoalsMade (L5) (-0.19 pts)
     8. + Home team advantage in offensiveRating (L5) (+0.16 pts)
     9. + Away contestedShots (L10) (+0.16 pts)
    10. - Away team advantage in contestedFieldGoalsAttempted (L5) (-0.14 pts)
```

### Interpretation

**Prediction:** Indiana (IND) is predicted to beat New Orleans (NOP) by 7.4 points at home.

**Key Factors:**
1. **netRating advantage (+1.90 pts):** Indiana's superior net rating over the last 10 games is the biggest factor, adding ~1.9 points to the predicted margin.

2. **PLUS_MINUS advantage (+0.71 pts):** Indiana has been outscoring opponents more consistently, contributing another 0.7 points.

3. **PIE advantage (+0.58 pts):** Indiana's players have higher overall impact (Player Impact Estimate).

4. **NOP away struggles (-0.48 pts):** New Orleans has a poor road win percentage, hurting their chances.

**Total top 10 impact:** ~4.3 points of the 7.4 point margin comes from these features!

---

## Dashboard Example (dataExploration.py Tab 6)

### SHAP Visualization Card

For the same game (NOP @ IND), the dashboard displays:

**Card Header:**
```
Feature Importance: NOP @ IND
```

**Left Column (Random Forest):**
- Horizontal bar chart
- Top 10 features ranked by absolute SHAP value
- Green bars extending right (helps home team):
  - `netRating_L10`: +1.90
  - `PLUS_MINUS_L10`: +0.71
  - `PIE_L10`: +0.58
  - ...

- Red bars extending left (helps away team):
  - `AWAY_WIN_PCT_L10`: -0.48
  - `defendedAtRimFieldGoalsMade_L5`: -0.19
  - ...

**Right Column (Neural Network):**
- Similar chart if NN is available
- May show different feature rankings
- Useful for model comparison

**Interpretation Guide (bottom of card):**
```
How to read:
- Green bars = helps home team win. Red bars = helps away team win.
- Longer bars = stronger impact on the prediction.

Example:
If 'DIFF_netRating_L10' is +2.5 (green), the home team's better net rating
over last 10 games adds ~2.5 points to the predicted margin.
```

---

## Comparison: Strong vs Weak Prediction

### Strong Prediction (High Confidence)

**BOS @ WAS - BOS by 10.3 points**

```
Top factors:
  1. - Away team advantage in netRating (L10) (-5.48 pts)
  2. - Away team advantage in PLUS_MINUS (L10) (-2.91 pts)
  3. - Away team advantage in PIE (L10) (-1.30 pts)
  4. + Home team advantage in WIN_PCT (L10) (+0.41 pts)
  ...
```

**Analysis:**
- **Dominant feature:** Boston's netRating advantage alone accounts for 5.5 points!
- **Consistent direction:** Top 3 features all favor away team (Boston)
- **Large magnitude:** Individual features have strong impact (>1 point)
- **Conclusion:** Model is very confident in this prediction

---

### Weak Prediction (Low Confidence)

**NYK @ ORL - NYK by 1.9 points**

```
Top factors:
  1. - Away team advantage in netRating (L10) (-1.98 pts)
  2. + Home team advantage in PIE (L10) (+0.54 pts)
  3. + Home team advantage in WIN_PCT (L10) (+0.37 pts)
  4. - Away team advantage in defendedAtRimFieldGoalsMade (L5) (-0.25 pts)
  ...
```

**Analysis:**
- **Close prediction:** Only 1.9 point margin
- **Mixed signals:** Features contradict each other (some favor NYK, some ORL)
- **Small magnitudes:** No single feature dominates (largest is 2.0 points)
- **Conclusion:** Toss-up game, high uncertainty

---

## Feature Categories by Importance

Based on multiple game predictions, here's how different feature categories rank:

### Tier 1: Strong Predictors (1-5 points per feature)
1. **netRating (L10)** - Overall efficiency differential
2. **PLUS_MINUS (L10)** - Point differential in recent games
3. **PIE (L10)** - Player Impact Estimate
4. **offensiveRating/defensiveRating (L10)** - Four factors efficiency

### Tier 2: Moderate Predictors (0.2-1 point per feature)
5. **WIN_PCT (L10)** - Recent win percentage
6. **defendedAtRimFieldGoalsMade** - Defensive impact
7. **AWAY_WIN_PCT (L10)** - Road performance
8. **turnoverRatio** - Ball security
9. **FG3A/FG3_PCT** - Three-point shooting

### Tier 3: Weak Predictors (<0.2 points per feature)
10. **contestedShots** - Hustle metrics
11. **pace** - Game tempo
12. **REST_DAYS** - Fatigue indicators
13. **IS_BACK_TO_BACK** - Schedule factors

---

## Model Comparison: RF vs NN

### Game: DAL @ GSW

**Random Forest Top 3:**
1. netRating (L10): +2.5 pts
2. PLUS_MINUS (L10): +1.2 pts
3. PIE (L10): +0.8 pts

**Neural Network Top 3:**
1. netRating (L10): +2.3 pts (similar!)
2. offensiveRating (L5): +1.5 pts (different!)
3. PLUS_MINUS (L10): +0.9 pts (similar!)

**Insight:**
- Both models agree on netRating as most important
- NN places more weight on offensiveRating
- RF favors longer-term stats (L10 vs L5)
- When models agree strongly → higher confidence prediction
- When models disagree → watch for upset potential

---

## PNG Visualization Layout

When you run `python predict_games.py`, a PNG is saved with this layout:

```
┌─────────────────────────────────────────────────────────────────┐
│  NBA Game Predictions for 2024-12-15 (RF)                      │
├──────────────────┬──────────────────┬─────────────────────────┤
│                  │                  │                         │
│   Win Prob       │   Margin Dist    │   SHAP Top 10          │
│                  │                  │                         │
│  NOP ▓░░░░░░     │      ▁▃▆▇▃▁      │  netRating ▓▓▓▓▓▓     │
│      27%         │       ││        │  PLUS_MIN  ▓▓▓        │
│                  │       ▼│         │  PIE       ▓▓         │
│  IND ▓▓▓▓▓▓▓░    │   Even│Pred     │  AWAY_WP   ░░░        │
│      73%         │       │ +7.4    │  ...                  │
│                  │                  │                         │
├──────────────────┼──────────────────┼─────────────────────────┤
│  [Next game...]  │  [Next game...]  │  [Next game...]        │
└──────────────────┴──────────────────┴─────────────────────────┘
```

**Column 1 (Win Probability):**
- Horizontal bars for each team
- Color-coded: green=favorite, red=underdog
- Percentages labeled

**Column 2 (Margin Distribution):**
- Histogram of 100 tree predictions
- Red dashed line at 0 (even game)
- Green line at predicted margin
- Shows uncertainty (width of distribution)

**Column 3 (SHAP Features):** ⭐ NEW!
- Top 10 features by importance
- Horizontal bars (green=home, red=away)
- Values labeled on bars
- Zero reference line

---

## Advanced: Feature Interaction Example

While not currently implemented, here's how feature interactions could look:

**Scenario:** Back-to-back game for road team

```
Individual effects:
- AWAY_IS_BACK_TO_BACK: -1.2 pts (fatigue)
- AWAY_WIN_PCT (L10): -0.8 pts (poor recent form)

Interaction effect:
- Back-to-back + poor form: -2.5 pts (more than sum!)
  → Cumulative fatigue hits struggling teams harder
```

**Scenario:** High-pace teams with good defense

```
Individual effects:
- DIFF_pace (L10): +0.3 pts (faster pace)
- DIFF_defensiveRating (L10): +1.5 pts (better defense)

Interaction effect:
- Fast pace + good defense: +2.3 pts (amplified!)
  → Good defensive teams thrive in transition
```

This could be added with `shap.TreeExplainer(..., feature_perturbation='interventional')`

---

## Real-World Usage Tips

### For Bettors
1. **Look for SHAP value concentration:**
   - If top 3 features account for >70% of margin → confident bet
   - If features spread evenly → avoid, too uncertain

2. **Check feature direction consistency:**
   - All top features favor one team → strong pick
   - Mixed signals → stay away or take underdog

3. **Compare SHAP to Vegas line:**
   - SHAP says +7.4, Vegas says +5 → value on favorite
   - SHAP says +2, Vegas says +7 → value on underdog

### For Analysts
1. **Feature engineering validation:**
   - netRating dominates → good composite metric
   - L10 > L5 → longer trends more predictive
   - Hustle stats weak → consider dropping

2. **Model debugging:**
   - Unexpected feature importance → investigate data quality
   - NN vs RF disagreement → examine those games post-hoc
   - Feature with wrong sign → check feature engineering logic

3. **Basketball insights:**
   - Defense (defendedAtRim) matters more than expected
   - Three-point volume less important than net rating
   - Back-to-backs have measurable but small impact

---

## Limitations & Caveats

### What SHAP Shows:
- **Feature importance for THIS prediction**
- **Marginal contribution** (holding other features constant)
- **Model reasoning** (not ground truth)

### What SHAP Doesn't Show:
- **Causality** (correlation ≠ causation)
- **Injuries/lineup changes** (not in our features)
- **Psychological factors** (rivalry games, playoffs, etc.)
- **Referee assignments** (can affect fouls, pace)

### Interpretation Warnings:
1. **Don't over-interpret small values** (<0.2 pts)
   - Within noise/uncertainty range
   - Could flip sign on re-training

2. **Context matters:**
   - +2.0 pts in a close game is huge
   - +2.0 pts in a blowout is negligible

3. **Feature correlations:**
   - netRating and PLUS_MINUS overlap conceptually
   - SHAP handles this, but values are "conditional"

---

## Next Steps

### Immediate Actions:
1. Run dashboard and test SHAP visualizations live
2. Make predictions for upcoming games
3. Compare SHAP explanations to actual game outcomes

### Future Enhancements:
1. Add SHAP summary plots (aggregate importance)
2. Add SHAP dependence plots (how feature values affect predictions)
3. Add SHAP interaction values (feature synergies)
4. Export SHAP values to CSV for deeper analysis
5. Create SHAP-based feature selection pipeline

### Learning Opportunities:
1. Study which features matter most for upsets
2. Identify feature importance differences by team strength
3. Track how feature importance changes over season
4. Compare early-season vs late-season SHAP patterns

---

**Congratulations!** You now have a fully interpretable NBA prediction system powered by SHAP!
