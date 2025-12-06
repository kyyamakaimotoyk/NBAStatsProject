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

### Predict Today's Games

```bash
python predict_games.py                    # Today's games (Random Forest)
python predict_games.py --model nn         # Today's games (Neural Network)
python predict_games.py --model both       # Compare both models side-by-side
python predict_games.py --tomorrow         # Tomorrow's games
python predict_games.py --date 2024-12-25  # Specific date
python predict_games.py --no-plot          # Skip histogram visualization
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
| `feature_engineering.py` | Builds 480+ ML features from raw game data |
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

### Matchup Features

For each game, features are computed three ways:
- `HOME_*` - Home team's statistics
- `AWAY_*` - Away team's statistics
- `DIFF_*` - Differential (HOME - AWAY)

**Total: 480 features** (160 home + 160 away + 160 differential)

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
- **Algorithm**: 3-layer MLP with BatchNorm & Dropout
- **Uncertainty**: Monte Carlo Dropout (100 forward passes with dropout enabled)
- **Strengths**: Learns complex patterns, scales to large data, GPU acceleration
- **Performance**: AUC 0.776, MAE 9.94 points

### Why Random Forest Wins on Tabular Data
1. Decision trees naturally capture feature interactions
2. Handles heterogeneous features well (counts, percentages, binary)
3. Less tuning required than neural networks
4. Sample size (~8,000 games) favors simpler models

---

## Directory Structure

```
NBAStatsProject/
├── predict_games.py          # Main prediction script (RF + NN)
├── feature_engineering.py    # Feature pipeline with fatigue metrics
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
│   ├── scaler.joblib         # Imputer + StandardScaler
│   ├── feature_names.joblib  # List of 480 feature names
│   └── nn_config.joblib      # Neural network config
├── DATABASE_SCHEMA.md        # Database documentation
└── README.md                 # This file
```

---

## Database Connection

The project connects to a local MySQL database:
- Host: localhost
- Port: 3306
- Database: nba_data

Connection details are in each script's `create_engine()` function.

---

## Future Improvements

1. **Player-level features**: Incorporate individual player stats and injuries
2. **Betting lines**: Compare predictions to Vegas spreads
3. **Ensemble methods**: Combine RF and NN predictions
4. **Real-time updates**: Auto-update after games complete
5. **Historical accuracy tracking**: Log predictions and measure calibration
6. **Travel distance**: Calculate miles traveled for road trips
