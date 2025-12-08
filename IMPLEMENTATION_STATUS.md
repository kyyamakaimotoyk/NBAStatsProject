# Implementation Status & Checklist

> Last updated: 2025-12-06

## Summary

This NBA prediction system uses machine learning to predict game outcomes (winner and margin). The system includes:

- **Random Forest** and **Neural Network** models for prediction
- **507+ engineered features** from team rolling statistics
- **Player impact estimation** for injury adjustments
- **Unified Monte Carlo** win probability derived from margin samples
- **SHAP feature importance** for prediction explainability

---

## Implementation Checklist

### Core Prediction Pipeline

| Feature | Status | File(s) | Notes |
|---------|--------|---------|-------|
| Feature engineering (507 features) | ✅ Done | `feature_engineering.py` | Rolling stats, fatigue, matchups |
| Random Forest models | ✅ Done | `baseline_models.py` | 70% accuracy, 9.3 MAE |
| Neural Network models | ✅ Done | `pytorch_nba_models.py` | MC Dropout for uncertainty |
| Game prediction script | ✅ Done | `predict_games.py` | Main entry point |
| Interactive dashboard | ✅ Done | `dataExploration.py` | 6-tab Dash app |
| SHAP feature importance | ✅ Done | `predict_games.py` | TreeExplainer for RF |
| Prediction tracking | ✅ Done | `prediction_tracker.py` | Logs to database |

### Player Impact System

| Feature | Status | File(s) | Notes |
|---------|--------|---------|-------|
| Historical WITH/WITHOUT impact | ✅ Done | `player_impact.py` | Primary approach (MAE 11.1) |
| DNP/DND/NWT detection | ✅ Done | `player_impact.py` | Uses comment field for OUT status |
| Advanced metrics fallback | ✅ Done | `player_impact.py` | netRating when <3 games |
| Impact evaluation script | ✅ Done | `evaluate_impact_approaches.py` | Validated on 8,823 games |
| Injury adjustment integration | ✅ Done | `predict_games.py` | `--injuries` flag |
| Team player impact reports | ✅ Done | `predict_games.py` | `--show-impacts` flag |
| Injury impact features | ✅ Done | `feature_engineering.py` | HOME/AWAY/DIFF_INJURY_IMPACT |
| Minutes redistribution | ❌ Deferred | - | Nice-to-have |
| Efficiency curve | ❌ Deferred | - | Nice-to-have |
| Real-time injury data | ❌ Pending | - | Need `nbainjuries` package |

### Unified Monte Carlo Win Probability

| Feature | Status | File(s) | Notes |
|---------|--------|---------|-------|
| Derive P(win) from margin samples | ✅ Done | `predict_games.py` | `mean(samples > 0)` |
| Keep classifier as reference | ✅ Done | `predict_games.py` | `win_prob_classifier` field |
| Shift samples for injury adjustment | ✅ Done | `predict_games.py` | Consistent margin & prob |
| Display both probabilities | ✅ Done | `predict_games.py` | P(Win) and Clf Ref columns |

### Performance Optimization

| Feature | Status | Notes |
|---------|--------|-------|
| Database indexes | ✅ Done | 66x query speedup (5.99s → 0.09s) |
| `--no-shap` flag | ✅ Done | Skip SHAP for faster predictions |
| Parallel injury impact calc | ✅ Done | `feature_engineering.py` uses joblib |

**Database Indexes Added (2025-12-06)**:
- `game_list`: `idx_game_list_team_date`, `idx_game_list_game_id`
- `boxscoretraditionalv3_player`: `idx_trad_game_team_person`
- `boxscoreadvancedv3_player`: `idx_adv_game_person`
- `boxscoreplayertrackv3_player`: `idx_track_game_person`

---

## Key Files

| File | Purpose |
|------|---------|
| `predict_games.py` | Main prediction script with all features |
| `player_impact.py` | Player impact estimation module |
| `evaluate_impact_approaches.py` | Validation of impact approaches |
| `feature_engineering.py` | 507+ feature generation |
| `baseline_models.py` | Scikit-learn model training |
| `pytorch_nba_models.py` | PyTorch neural network training |
| `player_projections.py` | Player-level aggregations |
| `prediction_tracker.py` | Prediction logging and accuracy |
| `dataExploration.py` | Interactive Dash dashboard |

---

## Usage Examples

```bash
# Basic predictions
python predict_games.py --model rf          # Random Forest
python predict_games.py --model nn          # Neural Network
python predict_games.py --model both        # Compare both

# Performance options
python predict_games.py --no-shap           # Skip SHAP (faster)
python predict_games.py --no-plot --no-log  # Minimal output

# With injury adjustments
python predict_games.py --injuries "LeBron James" "Anthony Davis"

# Show player impacts
python predict_games.py --show-impacts

# Accuracy tracking
python predict_games.py --backfill          # Update past predictions
python predict_games.py --accuracy-report   # Show accuracy metrics
```

---

## Validation Results

### Player Impact Approaches (8,823 games, 2015-2025)

| Approach | MAE | RMSE | Correlation |
|----------|-----|------|-------------|
| Historical WITH/WITHOUT | **11.10** | **14.27** | **0.350** |
| Advanced (netRating) | 11.88 | 15.17 | 0.138 |

**Winner**: Historical approach by 0.78 pts MAE and 2.5x correlation.

### Model Performance

| Model | Classification AUC | Regression MAE |
|-------|-------------------|----------------|
| Random Forest | **0.792** | **9.33** |
| Neural Network | 0.776 | 9.94 |

**Winner**: Random Forest on tabular data.

---

## Pending Work

1. **Real-time injury data** - Integrate `nbainjuries` package for automatic injury detection
2. **Minutes redistribution** - Model who absorbs minutes when a player is out
3. **Vegas line comparison** - Compare predictions to betting spreads
4. **Ensemble methods** - Combine RF and NN predictions
5. **Travel distance** - Add miles traveled for fatigue modeling

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           NBA Game Prediction                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                  │
│  │   NBA API    │    │  MySQL DB    │    │ --injuries   │                  │
│  │  (schedule)  │    │ (game stats) │    │   (manual)   │                  │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘                  │
│         │                   │                    │                          │
│         ▼                   ▼                    ▼                          │
│  ┌─────────────────────────────────────────────────────┐                   │
│  │              Feature Engineering                     │                   │
│  │  - 507 rolling features (L5, L10)                   │                   │
│  │  - Fatigue metrics                                   │                   │
│  │  - Player projections                                │                   │
│  └──────────────────────────┬──────────────────────────┘                   │
│                             │                                               │
│                             ▼                                               │
│  ┌─────────────────────────────────────────────────────┐                   │
│  │              Model Prediction                        │                   │
│  │  ┌─────────────┐  ┌─────────────┐                   │                   │
│  │  │ RF (100     │  │ NN (MC      │                   │                   │
│  │  │   trees)    │  │  Dropout)   │                   │                   │
│  │  └──────┬──────┘  └──────┬──────┘                   │                   │
│  │         │                │                           │                   │
│  │         ▼                ▼                           │                   │
│  │     margin_samples (100 predictions)                 │                   │
│  └──────────────────────────┬──────────────────────────┘                   │
│                             │                                               │
│                             ▼                                               │
│  ┌─────────────────────────────────────────────────────┐                   │
│  │              Injury Adjustment                       │                   │
│  │  - Shift margin_samples by player impact            │                   │
│  │  - Recompute margin = mean(adjusted_samples)        │                   │
│  │  - Recompute P(win) = mean(adjusted_samples > 0)    │                   │
│  └──────────────────────────┬──────────────────────────┘                   │
│                             │                                               │
│                             ▼                                               │
│  ┌─────────────────────────────────────────────────────┐                   │
│  │              Output                                  │                   │
│  │  - Winner pick                                       │                   │
│  │  - P(win) from margin samples (primary)             │                   │
│  │  - P(win) from classifier (reference)               │                   │
│  │  - Margin with uncertainty                          │                   │
│  │  - SHAP feature importance                          │                   │
│  └─────────────────────────────────────────────────────┘                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```
