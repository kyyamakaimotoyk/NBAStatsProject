# NBA Game Prediction Project

A machine learning project that predicts NBA game outcomes (winner and point margin) using historical game data. Built as a learning project for PyTorch and ML fundamentals.

## Project Overview

This project:
- Fetches NBA game data via the NBA API and stores it in MySQL
- Engineers 480+ features from rolling statistics including fatigue metrics
- Trains both scikit-learn (Random Forest) and PyTorch (Neural Network) models
- Predicts game outcomes with uncertainty estimates
- Compares model predictions side-by-side

## Quick Start

### Prerequisites

```bash
# Install dependencies
pip install sqlalchemy pandas numpy scikit-learn matplotlib joblib
pip install torch torchvision  # For PyTorch models
pip install nba_api  # For fetching live schedules
pip install dash dash-bootstrap-components plotly  # For visualization app
```

**Windows Note**: PyTorch must be imported before NumPy/Pandas due to DLL conflicts. This is handled automatically in `predict_games.py`. If you encounter `OSError: [WinError 1114] DLL initialization failed`, ensure PyTorch is imported first in your scripts.

### Predict Today's Games

```bash
python predict_games.py                    # Today's games (Random Forest)
python predict_games.py --model nn         # Today's games (Neural Network)
python predict_games.py --model both       # Compare both models side-by-side
python predict_games.py --tomorrow         # Tomorrow's games
python predict_games.py --date 2024-12-25  # Specific date
python predict_games.py --no-plot          # Skip histogram visualization
python predict_games.py --no-shap          # Skip SHAP calculations (faster)

# With injury adjustments
python predict_games.py --injuries "LeBron James" "Anthony Davis"
python predict_games.py --show-impacts     # Show player impact reports
```

---

## Script Execution Order

Run scripts in this order for a complete pipeline:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  1. schema_exploration.py     (Optional) Explore database structure         │
│         ↓                                                                   │
│  2. feature_engineering.py    Generate ML features → nba_ml_features.csv   │
│         ↓                                                                   │
│  3. baseline_models.py        Train scikit-learn models → models/*.joblib  │
│         ↓                                                                   │
│  4. pytorch_nba_models.py     Train PyTorch models → models/*.pt           │
│         ↓                                                                   │
│  5. predict_games.py          Make predictions (requires trained models)   │
│         ↓                                                                   │
│  6. dataExploration.py        Launch dashboard (requires trained models)   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### First-Time Setup

```bash
# Step 1: (Optional) Explore your database
python schema_exploration.py

# Step 2: Generate features from raw game data
python feature_engineering.py
# Creates: nba_ml_features.csv

# Step 3: Train scikit-learn models
python baseline_models.py
# Creates: models/rf_classifier.joblib, models/rf_regressor.joblib, models/scaler.joblib

# Step 4: Train PyTorch models
python pytorch_nba_models.py
# Creates: models/nn_classifier.pt, models/nn_regressor.pt, models/nn_config.joblib
```

### Daily Usage (after models are trained)

```bash
# Predict today's games
python predict_games.py --model both

# Or launch the dashboard
python dataExploration.py
```

### When to Re-run Scripts

| Scenario | Scripts to Re-run |
|----------|-------------------|
| New games added to database | `feature_engineering.py` → `baseline_models.py` → `pytorch_nba_models.py` |
| Changed feature engineering logic | `feature_engineering.py` → `baseline_models.py` → `pytorch_nba_models.py` |
| Want to tune model hyperparameters | `baseline_models.py` and/or `pytorch_nba_models.py` |
| Just making predictions | `predict_games.py` only (uses saved models) |

---

## Scripts Overview

| Script | Purpose |
|--------|---------|
| `predict_games.py` | **Main prediction script** - Predicts winners and margins using RF or NN |
| `feature_engineering.py` | Builds 507+ ML features from raw game data |
| `player_projections.py` | Player-level projections with opponent adjustments |
| `player_impact.py` | **NEW** - Historical player impact estimation for injury adjustments |
| `prediction_tracker.py` | Logs predictions and tracks accuracy over time |
| `evaluate_impact_approaches.py` | **NEW** - Validates impact estimation approaches |
| `baseline_models.py` | Trains and evaluates scikit-learn models |
| `pytorch_nba_models.py` | PyTorch neural network implementation (educational) |
| `dataExploration.py` | Interactive Dash app with 6 tabs including predictions |
| `schema_exploration.py` | Utility to explore database structure |

---

## Feature Engineering

### Rolling Statistics (76 stats x 2 windows = 152 features)

Statistics are calculated as rolling averages over the **last 5 games (L5)** and **last 10 games (L10)**:

- **Traditional**: PTS, FGM, FGA, FG_PCT, FG3M, FG3A, FG3_PCT, FTM, FTA, REB, AST, STL, BLK, TOV
- **Advanced**: offensiveRating, defensiveRating, netRating, pace, PIE, TS_PCT, EFG_PCT
- **Four Factors**: FT_RATE, TOV_PCT, OREB_PCT, OPP_EFG_PCT
- **Hustle**: contestedShots, deflections, looseBallsRecovered, boxOuts
- **Tracking**: speed, distance, touches, passes, secondaryAssists
- **Scoring**: pctFGA_2pt, pctFGA_3pt, pctPTS_paint, pctAssisted

### Fatigue Features (6 features)

Captures the impact of schedule density on performance:

| Feature | Description |
|---------|-------------|
| `IS_BACK_TO_BACK` | Binary: 1 if team has 0-1 days rest |
| `IS_3_IN_4_NIGHTS` | Binary: 1 if this is 3rd game in 4 days |
| `GAMES_LAST_7_DAYS` | Count of games played in last 7 days |
| `GAMES_LAST_14_DAYS` | Count of games played in last 14 days |
| `AVG_REST_LAST_5` | Average days of rest between last 5 games |
| `ROAD_TRIP_LENGTH` | Consecutive away games (travel fatigue) |

**Hypothesis**: Teams with more games in fewer days experience fatigue, leading to decreased performance.

### Player Projection Features (9 features per team)

**NEW**: Aggregates individual player stats with opponent adjustments:

| Feature | Description |
|---------|-------------|
| `PROJ_PTS_FROM_PLAYERS` | Sum of all players' opponent-adjusted PPG projections |
| `PROJ_REB_FROM_PLAYERS` | Sum of all players' opponent-adjusted RPG projections |
| `PROJ_AST_FROM_PLAYERS` | Sum of all players' opponent-adjusted APG projections |
| `WEIGHTED_AVG_USAGE` | Minutes-weighted average usage% of rotation |
| `WEIGHTED_AVG_TS_PCT` | Minutes-weighted average true shooting% |
| `WEIGHTED_AVG_PIE` | Minutes-weighted average Player Impact Estimate |
| `ROSTER_DEPTH_SCORE` | Count of players averaging 15+ min/game |
| `STAR_PLAYER_IMPACT` | Max player PPG on roster (star player) |
| `TOP_3_SCORER_SHARE` | % of team points from top 3 scorers (concentration) |

**Opponent Adjustments Applied**:
- **Pace factor**: If opponent plays faster (more possessions), player stats are scaled up
- **Defensive rating factor**: If opponent has poor defense, player scoring is scaled up
- **Rebounding factor**: Adjusts rebounding based on opponent's allowed offensive rebound rate

**Example**: LeBron James averages 25 PPG. Against a fast team with bad defense:
- Pace factor: 105/100 = 1.05
- Defensive factor: 118/112 = 1.05
- Projected vs this opponent: 25 × 1.05 × 1.05 = **27.6 PPG**

### Matchup Features

For each game, features are computed three ways:
- `HOME_*` - Home team's statistics
- `AWAY_*` - Away team's statistics
- `DIFF_*` - Differential (HOME - AWAY)

**Total: 507 features** (169 home + 169 away + 169 differential)

---

## Detailed Script Documentation

### 1. `predict_games.py` - Game Predictions

**What it does:**
1. Fetches scheduled games from NBA API for the specified date
2. Queries database for each team's recent performance (last 5-15 games)
3. Calculates rolling averages and fatigue metrics
4. Runs predictions through Random Forest and/or Neural Network
5. Outputs win probabilities and point margins with uncertainty estimates

**Model options:**
- `--model rf` - Random Forest (default, better accuracy)
- `--model nn` - Neural Network with Monte Carlo Dropout
- `--model both` - Compare both models side-by-side

**Example output:**
```
MODEL COMPARISON FOR 2025-12-05
====================================================================================================

Matchup              | --- Random Forest ---          | --- Neural Network ---
                     | Pick     Win%      Margin      | Pick     Win%      Margin
----------------------------------------------------------------------------------------------------
LAL @ BOS            | BOS      61.3%       +8.7      | BOS      58.2%       +6.1
DEN @ ATL            | DEN      43.9%       -2.7      | ATL      51.2%       +1.3  *
----------------------------------------------------------------------------------------------------
* = Models disagree on winner
```

---

### 2. `feature_engineering.py` - Feature Pipeline

**What it does:**
1. Loads data from 7 database tables (game_list + 6 boxscore tables)
2. Calculates rolling averages (L5, L10) for 76 statistics
3. Calculates fatigue features (back-to-back, games in last 7 days, etc.)
4. Adds derived features (win streak, rest days, home/away splits)
5. Creates matchup features (HOME_, AWAY_, DIFF_ prefixes)
6. Exports ML-ready dataset to CSV

**Key concepts:**
- **Data leakage prevention**: Uses `shift(1)` to exclude current game from rolling calculations
- **Fatigue tracking**: Counts games in rolling windows to measure schedule density
- **Differential features**: Captures relative strength between teams

**Output:** `nba_ml_features.csv` (~8,800 games, 655 columns)

```bash
python feature_engineering.py
```

---

### 3. `baseline_models.py` - Scikit-learn Models

**What it does:**
1. Loads feature dataset
2. Performs temporal train/test split (train on past, test on future)
3. Trains multiple models:
   - Logistic Regression, Random Forest, Gradient Boosting (classification)
   - Linear Regression, Random Forest, Gradient Boosting (regression)
4. Evaluates and compares performance
5. Shows feature importance

**Results:**
| Task | Best Model | Performance |
|------|-----------|-------------|
| Classification | Random Forest | 70% accuracy, 0.79 AUC |
| Regression | Random Forest | 9.3 MAE, 0.20 R² |

**Top predictive features:**
1. DIFF_netRating_L10 (net rating differential)
2. DIFF_PIE_L10 (Player Impact Estimate differential)
3. DIFF_PLUS_MINUS_L10 (plus/minus differential)

```bash
python baseline_models.py
```

---

### 4. `pytorch_nba_models.py` - Neural Networks

**What it does:**
1. **Phase 3 Tutorial**: Explains PyTorch fundamentals
   - Tensors and GPU acceleration
   - Autograd (automatic differentiation)
   - nn.Module for defining networks
   - Loss functions (BCE, MSE)
   - Optimizers (Adam, SGD)
2. **Phase 4 Implementation**: Trains neural networks
   - 3-layer MLP (128→64→32→1) with BatchNorm and Dropout
   - Early stopping to prevent overfitting
   - Monte Carlo Dropout for uncertainty estimation

**Results:**
| Model | Classification AUC | Regression MAE |
|-------|-------------------|----------------|
| Random Forest | **0.792** | **9.33** |
| Neural Network | 0.776 | 9.94 |

Neural networks perform slightly worse on this tabular data, which is typical. Tree-based models often win on structured data.

```bash
python pytorch_nba_models.py
```

---

### 5. `dataExploration.py` - Visualization Dashboard

**What it does:**
Launches an interactive Dash web application with 6 tabs:

1. **Score Distribution**: Histogram of game scores
2. **Trends Over Time**: Points scored by season
3. **Team Performance**: Team-by-team statistics
4. **Rolling Feature Tracker**: Track any feature over the season for each team
5. **Margin Correlation Analysis**: Pearson correlations with winning margin
6. **Game Predictions**: Compare Random Forest vs Neural Network predictions

**Game Predictions Tab Features:**
- Date picker with Today/Tomorrow quick-select
- Side-by-side comparison table (RF vs NN)
- AGREE/DISAGREE badges showing model consensus
- Win probability bar chart comparing both models
- Margin distribution violin plots showing uncertainty
- Model explanation cards

```bash
python dataExploration.py
# Open http://127.0.0.1:5000 in browser
```

---

### 6. `schema_exploration.py` - Database Utility

**What it does:**
- Lists all 36 tables in the database
- Shows row counts for each table
- Displays column schemas
- Shows date range and sample data

```bash
python schema_exploration.py
```

---

## Model Comparison

### Random Forest (scikit-learn)
- **Algorithm**: Ensemble of 100 decision trees
- **Uncertainty**: Each tree votes independently; distribution shows agreement
- **Strengths**: Great for tabular data, handles missing values, fast training
- **Performance**: AUC 0.792, MAE 9.33 points

### Neural Network (PyTorch)
- **Algorithm**: 3-layer MLP (128→64→32→1) with BatchNorm & Dropout (0.3)
- **Uncertainty**: Monte Carlo Dropout (100 forward passes with dropout enabled)
- **Target Scaling**: Regression targets normalized to mean=0, std=1 during training (see Experiments section)
- **Strengths**: Learns complex patterns, scales to large data, GPU acceleration
- **Performance**: AUC 0.776, MAE ~9.5 points (after target scaling fix)

### Why Random Forest Wins on Tabular Data
1. Decision trees naturally capture feature interactions
2. Handles heterogeneous features well (counts, percentages, binary)
3. Less tuning required than neural networks
4. Sample size (~8,000 games) favors simpler models

---

## Directory Structure

```
NBAStatsProject/
├── predict_games.py          # Main prediction script (RF + NN + SHAP)
├── feature_engineering.py    # Feature pipeline (507 features)
├── player_projections.py     # Player-level projections with opponent adjustments
├── prediction_tracker.py     # Prediction logging and accuracy tracking
├── prediction_visualizations.py  # Accuracy charts and analysis
├── baseline_models.py        # Sklearn model training
├── pytorch_nba_models.py     # PyTorch model training
├── dataExploration.py        # Dash visualization app (6 tabs)
├── schema_exploration.py     # Database utility
├── nba_ml_features.csv       # Generated feature dataset
├── models/                   # Saved trained models
│   ├── rf_classifier.joblib  # Random Forest classifier
│   ├── rf_regressor.joblib   # Random Forest regressor
│   ├── nn_classifier.pt      # PyTorch classifier weights
│   ├── nn_regressor.pt       # PyTorch regressor weights
│   ├── scaler.joblib         # Imputer + StandardScaler for features
│   ├── feature_names.joblib  # List of 507 feature names
│   └── nn_config.joblib      # Neural network config (input_dim, target_scaler)
├── DATABASE_SCHEMA.md        # Database documentation
└── README.md                 # This file
```

---

## Database Connection

The project connects to a local MySQL database:
- Host: localhost
- Port: 3306
- Database: nba_data
- Prediction tracking table: `model_predictions`

Connection details are in each script's `create_engine()` function.

---

## Recent Enhancements

### SHAP Feature Importance
- See which features drive each prediction (top 10)
- TreeExplainer for Random Forest (fast, exact)
- GradientExplainer for Neural Network

### Prediction Tracking
```bash
python predict_games.py --backfill      # Update past predictions with actual results
python predict_games.py --accuracy-report  # Show accuracy metrics
```

### Player Projections (Option B: Full Roster Aggregation)
- Aggregates individual player stats weighted by minutes
- Adjusts for opponent's pace, defensive rating, rebounding
- Solves chicken-egg problem using season-to-date stats

---

## Experiments & Research

### Neural Network Target Scaling Fix (2025-12-08)

**Problem**: The Neural Network regressor was producing collapsed predictions (~±1 pt) instead of realistic point margins (~±15 pts), with extreme win probabilities (0%, 2%, 100%).

**Root Cause Analysis**:

The issue was a **~14x scale mismatch** between features and targets during training:

| Data | Mean | Std Dev | Range |
|------|------|---------|-------|
| **Features (X)** | 0 | 1 | ~[-3, +3] (StandardScaler applied) |
| **Targets (y)** | 2.92 | 14.34 | [-68, +73] (raw point margins) |

This mismatch caused:
1. Very large initial MSE loss (~200+) creating unstable gradients
2. Model learned to predict near-zero to minimize loss quickly
3. Gradient updates dominated by outliers (blowout games)
4. Final predictions collapsed to narrow range (~±1 instead of ±15)

**Diagnosis Output (before fix)**:
```
Random Forest (100 trees):
  Mean: 6.57, Std: 15.46, Range: [-27, +59]

Neural Network (100 MC Dropout samples):
  Mean: 0.11, Std: 0.27, Range: [-0.63, +0.73]  ← COLLAPSED!
```

**Solution**: Scale regression targets to mean=0, std=1 during training, then inverse-transform predictions:

```python
# Training: Scale targets
target_scaler = StandardScaler()
y_scaled = target_scaler.fit_transform(y_margins.reshape(-1, 1))
# Train model on scaled targets (now mean=0, std=1)

# Inference: Inverse-transform predictions
margin_samples_raw = [model(X) for _ in range(100)]  # MC Dropout
margin_samples = target_scaler.inverse_transform(margin_samples_raw)
```

**Results After Fix**:

| Metric | Before Fix | After Fix |
|--------|-----------|-----------|
| Margin range | ±1 pt | ±8 pts |
| Uncertainty | ±0.6-0.8 pts | ±2.8-3.1 pts |
| Win prob distribution | 0%, 2%, 100% (extreme) | 31%, 91%, 100% (reasonable) |
| Agreement with RF | Partial | All 3 picks agree |

**Training Logs (after fix)**:
```
Training NN classifier...
  Early stopping at epoch 59 (best val_loss: 0.4419)
Training NN regressor (with target scaling)...
  Early stopping at epoch 47 (best val_loss: 0.6960)
```

**Files Modified**:
- `predict_games.py`: `_train_pytorch_model()`, `load_or_train_pytorch_models()`, `predict_with_pytorch()`
- `models/nn_config.joblib`: Now stores `target_scaler` for inference

**Key Lesson**: When training neural networks for regression, ensure feature and target scales are comparable. StandardScaler on targets is essential when features are also standardized.

---

### Split Rebounding Adjustment Model (2025-12-08)

**Problem**: The player projection rebounding adjustment only considered offensive rebounding opportunities (what opponent allows), ignoring defensive rebounding factors.

**Previous Implementation**:
```python
# Only adjusted for OREB opportunities
oreb_factor = opponent_opp_oreb_pct / league_avg_opp_oreb_pct
proj_rpg = player_rpg * pace_factor * oreb_factor  # Same factor for all rebounds
```

**Issue**: ~70% of rebounds are defensive. The single factor over-projected DREB when opponent allowed many OREBs.

**New Split Model**:

| Factor | Formula | What It Captures |
|--------|---------|------------------|
| **OREB Factor** | `opp_oreb_pct / league_avg` | Opponent allows more OREBs → more OREB opportunities |
| **DREB Factor** | `oreb_competition × miss_rate` | Opponent bad at OREB + shoots poorly → more DREB |

Where:
- `oreb_competition = (1 - opponent_own_oreb_pct) / (1 - league_avg_own_oreb_pct)`
- `miss_rate = (1 - opponent_efg_pct) / (1 - league_avg_efg_pct)`

**Example (vs Lakers)**:
```
Lakers Profile:
  Own OREB%: 23.5% (bad at offensive rebounding)
  Own EFG%: 53.5% (slightly above average shooting)
  Opp OREB%: 30.4% (allows many offensive rebounds)

Factors Calculated:
  OREB factor: 1.068 (Lakers allow 30.4% vs 28.5% league avg)
  DREB factor: 1.054 (Lakers bad at OREB, but shoot well)

Jayson Tatum Adjustment:
  Raw: 0.6 OREB, 6.9 DREB, 7.5 RPG
  Adjusted: 0.64 OREB, 7.25 DREB, 7.89 RPG
```

**Files Modified**: `player_projections.py` - Added `calculate_rebounding_factors()`, updated `adjust_player_stats_for_opponent()`

---

### PyTorch Import Order on Windows (2025-12-08)

**Problem**: `OSError: [WinError 1114] DLL initialization routine failed` when importing PyTorch after NumPy/Pandas on Windows.

**Root Cause**: NumPy's OpenMP DLL loading conflicts with PyTorch's bundled libraries on Windows.

**Diagnosis**:
```python
# This works:
import torch  # First!
import numpy as np
import pandas as pd

# This fails on Windows:
import numpy as np
import pandas as pd
import torch  # OSError: DLL initialization failed
```

**Solution**: Import PyTorch at the very top of the file, before any other libraries:

```python
# predict_games.py (line 23-49)
# PyTorch - MUST be imported FIRST before numpy/pandas on Windows
try:
    import torch
    import torch.nn as nn
    PYTORCH_AVAILABLE = True
except (ImportError, OSError) as e:
    PYTORCH_AVAILABLE = False
    # ... fallback handling

# Now safe to import numpy, pandas, matplotlib, etc.
import numpy as np
import pandas as pd
```

**Files Modified**: `predict_games.py` - Moved PyTorch import to top of file

---

### Player Impact Estimation: Historical vs Advanced Metrics (2025-12-06)

**Question**: When a player is OUT, how should we estimate their impact on the team's margin?

**OUT Detection**: Uses the `comment` field in `boxscoreplayertrackv3_player` table:
- **DNP** = Did Not Play (Coach's Decision, Injury/Illness, Rest)
- **DND** = Did Not Dress (Injury/Illness, specific injuries, Rest)
- **NWT** = Not With Team (Personal Reasons, Suspension, Illness)

**Approaches Tested**:
- **Approach A (Historical)**: Compare team's margin WITH player (20+ min) vs WITHOUT player (DNP/DND/NWT)
- **Approach B (Advanced Metrics)**: Use player's netRating × minutes_share as impact estimate

**Results** (8,823 evaluation samples):

| Metric | Historical (WITH/WITHOUT) | Advanced (netRating) | Winner |
|--------|---------------------------|----------------------|--------|
| **MAE** | **11.10 pts** | 11.88 pts | Historical |
| **Correlation** | **0.350** | 0.138 | Historical |

**Recommendation**: Use Historical WITH/WITHOUT as primary method, Advanced metrics as fallback when <3 historical games available.

**Script**: `evaluate_impact_approaches.py` | **Data**: `impact_evaluation_results.csv`

---

### Enhanced Player Impact Weighting (2025-12-10)

**Problem**: The raw historical impact had issues:
1. **Selection bias** - Role players showed extreme impacts from garbage-time games only
2. **No confidence weighting** - All confidence levels contributed equally
3. **No time decay** - Teams adapt when players are out for extended periods

**Solution**: Three-layer weighting system in `player_impact.py`:

#### 1. Player Importance Weighting
Combines minutes share and usage rate (50/50) to weight raw impact:

```
minutes_share = avg_minutes / 48
normalized_usage = avg_usage / 0.35
importance_weight = (minutes_share × 0.5) + (normalized_usage × 0.5)
importance_multiplier = importance_weight / 0.35  # baseline
weighted_impact = raw_impact × importance_multiplier
```

**Example Results**:
| Player | MPG | Usage | Multiplier | Effect |
|--------|-----|-------|------------|--------|
| Victor Wembanyama | 33 | 30% | **2.20x** | Stars amplified |
| LeBron James | 35 | 28% | **2.21x** | Stars amplified |
| Jordan McLaughlin | 20 | 10% | **1.02x** | Role players dampened |

#### 2. Confidence Level Weighting
Applied when summing impacts:
- **HIGH** (10+ games): 100% weight
- **MEDIUM** (5-9 games): 70% weight
- **LOW** (3-4 games or advanced method): 40% weight

#### 3. Time Decay for Consecutive Absences
Teams adapt over consecutive games without a player:
```
decay_weight = 0.85^(position_in_streak - 1)
# Game 1: 100%, Game 2: 85%, Game 3: 72%, Game 4: 61%...
```

#### 4. Minimum Games Threshold
Require 5+ games with 20+ minutes to use historical method (avoids garbage-time bias).

**Configuration** (all tunable in `player_impact.py`):
```python
MINUTES_WEIGHT = 0.5
USAGE_WEIGHT = 0.5
TIME_DECAY_FACTOR = 0.85
CONFIDENCE_WEIGHTS = {'HIGH': 1.0, 'MEDIUM': 0.7, 'LOW': 0.4}
MIN_GAMES_WITH = 5
```

**Sample Output**:
```
Player                   MPG  USG%     Raw  Mult     Wtd   Conf   Method
------------------------------------------------------------------------------------------
LeBron James            35.2  28.4   +20.5  2.21   +45.2    LOW historical*
Gabe Vincent            22.1  13.0   +11.1  1.21   +13.4 MEDIUM historical*
Anthony Davis           33.0  29.9    +4.2  2.29    +9.5    LOW advanced
```
`*` = time decay applied for consecutive games out

---

### Unified Monte Carlo Win Probability (2024-12-06)

**Problem**: Having separate classifier (win probability) and regressor (margin) models can lead to inconsistent predictions. For example: predicted margin of -2 points but 55% win probability.

**Solution**: Derive win probability directly from margin samples using Monte Carlo simulation.

**Implementation**:
```python
# Both RF (100 trees) and NN (100 MC Dropout passes) return margin_samples
margin_samples = [tree.predict(X) for tree in forest.estimators_]  # 100 samples

# Primary win probability = P(margin > 0)
win_prob = np.mean(margin_samples > 0)  # e.g., 62/100 = 62%

# Classifier probability kept as reference for comparison
win_prob_classifier = clf.predict_proba(X)[0][1]  # e.g., 58%
```

**Benefits**:
1. **Consistency**: Margin and probability always agree (can't have negative margin with >50% win)
2. **Unified injury adjustment**: Shifting margin samples automatically updates probability
3. **Transparency**: Both probabilities shown for comparison
4. **Empirically grounded**: Uses validated margin predictions

**Injury Adjustment Flow**:
```python
# Shift ALL margin samples by injury impact
adjusted_samples = margin_samples + injury_adjustment

# Recompute BOTH from adjusted samples
adjusted_margin = np.mean(adjusted_samples)
adjusted_win_prob = np.mean(adjusted_samples > 0)  # Consistent!
```

**Example Output**:
```
Matchup                   Pick       P(Win)    Clf Ref     Margin     Uncert
-----------------------------------------------------------------------------------------------
LAL @ BOS                 BOS         62.0%     58.2%     +3.5 pts   +/-8.2
  >> Injury adjusted: margin +8.2 -> +3.5 (-4.7), P(win) 71.0% -> 62.0%
```

---

## Future Improvements

1. ~~**Player-level features**: Incorporate individual player stats~~ ✅ DONE
2. ~~**Historical accuracy tracking**: Log predictions and measure calibration~~ ✅ DONE
3. ~~**Player impact estimation**: Historical WITH/WITHOUT approach for injury adjustments~~ ✅ DONE
4. ~~**Unified win probability**: Derive P(win) from P(margin > 0) via Monte Carlo~~ ✅ DONE
5. ~~**DNP/DND/NWT detection**: Use comment field for accurate OUT player identification~~ ✅ DONE (2025-12-06)
6. ~~**Database performance**: Add indexes for 66x query speedup~~ ✅ DONE (2025-12-06)
7. **Injury data integration**: Use `nbainjuries` package for real-time injury reports ⬅️ HIGH PRIORITY
   - Currently requires manual `--injuries` flag
   - Real injury data would automate player availability detection
8. **Injury impact features in training**: Include in model training for SHAP visibility ⬅️ NEXT
9. **Minutes redistribution modeling**: Model how minutes shift when a player is OUT
10. **Betting lines**: Compare predictions to Vegas spreads
11. **Ensemble methods**: Combine RF and NN predictions
12. **Travel distance**: Calculate miles traveled for road trips
