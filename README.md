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
pip install python-dotenv  # For environment-variable config (see Database Setup below)
```

**Windows Note**: PyTorch must be imported before NumPy/Pandas due to DLL conflicts. This is handled automatically in `predict_games.py`. If you encounter `OSError: [WinError 1114] DLL initialization failed`, ensure PyTorch is imported first in your scripts.

### Database Setup (env vars)

MySQL credentials live in environment variables — never in source. To set up:

1. **Copy the template**:
   ```bash
   cp .env.example .env   # or `copy` on Windows
   ```

2. **Fill in `.env`** with your MySQL credentials. The required variables are:
   ```
   NBA_DB_HOST=localhost
   NBA_DB_PORT=3306
   NBA_DB_USER=your_mysql_username
   NBA_DB_PASSWORD=your_mysql_password
   NBA_DB_NAME=nba_data
   ```

3. **`.env` is gitignored** (see `.gitignore`). `.env.example` is committed as the template; never put real credentials in `.env.example`.

4. All scripts read these vars via `db.get_engine()`. `python-dotenv` auto-loads `.env` on import — no manual `set` / `export` needed.

> ⚠️ **If you forked this repo from a public commit history**: rotate your MySQL user's password. Earlier commits in this repo's history contained credentials in plain text. Removing them from current files does **not** remove them from git history.

### Predict Today's Games

```bash
python modeling/predict_games.py                    # Today's games (Random Forest)
python modeling/predict_games.py --model nn         # Today's games (Neural Network)
python modeling/predict_games.py --model nn-embed   # Today's games (NN with player embeddings)
python modeling/predict_games.py --model both       # Compare both models side-by-side
python modeling/predict_games.py --tomorrow         # Tomorrow's games
python modeling/predict_games.py --date 2024-12-25  # Specific date
python modeling/predict_games.py --no-plot          # Skip histogram visualization
python modeling/predict_games.py --no-shap          # Skip SHAP calculations (faster)

# With injury adjustments
python modeling/predict_games.py --injuries "LeBron James" "Anthony Davis"
python modeling/predict_games.py --show-impacts     # Show player impact reports
```

---

## Script Execution Order

Run scripts in this order for a complete pipeline:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  1. schema_exploration.py     (Optional) Explore database structure         │
│         ↓                                                                   │
│  2. player_impact.py          Populate player impact cache (for slot features)│
│         ↓                                                                   │
│  3. feature_engineering.py    Generate ML features → nba_ml_features.csv   │
│         ↓                                                                   │
│  4. baseline_models.py        Train scikit-learn models → models/*.joblib  │
│         ↓                                                                   │
│  5. pytorch_nba_models.py     Train PyTorch models → models/*.pt           │
│         ↓                                                                   │
│  6. predict_games.py          Make predictions (requires trained models)   │
│         ↓                                                                   │
│  7. validate_models.py        (Optional) Held-out validation of saved models│
│         ↓                                                                   │
│  8. dataExploration.py        Launch dashboard (with Model Performance tab) │
└─────────────────────────────────────────────────────────────────────────────┘
```

### First-Time Setup

```bash
# Step 1: (Optional) Explore your database
python data_engineering/schema_exploration.py

# Step 2: Populate player impact cache for historical dates
# This is REQUIRED for player slot features to have non-zero values
# Takes ~2 minutes per date
python -c "
from player_impact import create_engine, populate_player_impact_table
engine = create_engine()
for date in ['2022-01-01', '2022-07-01', '2023-01-01', '2023-07-01', '2024-01-01', '2024-07-01']:
    print(f'Populating {date}...')
    populate_player_impact_table(engine, as_of_date=date)
"
# Creates: rows in player_impact MySQL table

# Step 3: Generate features from raw game data
python data_engineering/feature_engineering.py
# Creates: nba_ml_features.csv

# Step 4: Train scikit-learn models
python modeling/baseline_models.py
# Creates: models/rf_classifier.joblib, models/rf_regressor.joblib, models/scaler.joblib

# Step 5: Train PyTorch models
python modeling/pytorch_nba_models.py
# Creates: models/nn_classifier.pt, models/nn_regressor.pt, models/nn_config.joblib
```

### Daily Usage (after models are trained)

```bash
# Predict today's games
python modeling/predict_games.py --model both

# Or launch the dashboard
python visualization/dataExploration.py
```

### When to Re-run Scripts

| Scenario | Scripts to Re-run |
|----------|-------------------|
| New games added to database | `player_impact.py` (for new date) → `feature_engineering.py` → `baseline_models.py` → `pytorch_nba_models.py` |
| Changed feature engineering logic | `feature_engineering.py` → `baseline_models.py` → `pytorch_nba_models.py` |
| Want to tune model hyperparameters | `baseline_models.py` and/or `pytorch_nba_models.py` |
| Just making predictions | `predict_games.py` only (uses saved models) |
| Weekly/monthly refresh | `player_impact.py` (for current date) - keeps player impacts current |

---

## Scripts Overview

| Script | Purpose |
|--------|---------|
| `predict_games.py` | **Main prediction script** - Predicts winners and margins using RF or NN |
| `feature_engineering.py` | Builds 550+ ML features including player slot features |
| `player_projections.py` | Player-level projections with opponent adjustments |
| `player_impact.py` | **Cache management** - Populates player impact table (run BEFORE feature_engineering.py) |
| `prediction_tracker.py` | Logs predictions and tracks accuracy over time |
| `evaluate_impact_approaches.py` | Validates impact estimation approaches |
| `baseline_models.py` | Trains and evaluates scikit-learn models |
| `pytorch_nba_models.py` | PyTorch neural network implementation (educational) |
| `dataExploration.py` | Interactive Dash app with 7 tabs (incl. Model Performance) |
| `validate_models.py` | Held-out validation runner: re-runs saved models on a date window, logs results to `model_registry` |
| `schema_exploration.py` | Utility to explore database structure |
| `db.py` | Shared MySQL helper — `get_engine()` reads config from environment variables |

### player_impact.py CLI

```bash
# Check cache status (default if no args)
python data_engineering/player_impact.py
python data_engineering/player_impact.py --status

# Populate cache for today
python data_engineering/player_impact.py --populate

# Populate for a specific date
python data_engineering/player_impact.py --populate --date 2024-01-15

# Populate for multiple dates
python data_engineering/player_impact.py -p -d 2023-01-01 -d 2023-07-01 -d 2024-01-01

# Show team impact report
python data_engineering/player_impact.py --report --team 1610612747
```

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

### Player Slot Features (58 features) ⬅️ NEW

**Integrated roster model** that embeds player availability directly into the model, replacing the 2-tier injury adjustment approach:

| Feature Pattern | Count | Description |
|-----------------|-------|-------------|
| `{HOME/AWAY}_SLOT_{1-8}_IMPACT` | 16 | Historical impact score for top 8 players by impact |
| `{HOME/AWAY}_SLOT_{1-8}_AVAILABLE` | 16 | 1 if playing, 0 if OUT (DNP/DND/NWT) |
| `{HOME/AWAY}_TOTAL_AVAILABLE_IMPACT` | 2 | Sum of impacts for available players |
| `{HOME/AWAY}_TOTAL_MISSING_IMPACT` | 2 | Sum of impacts for OUT players |
| `{HOME/AWAY}_PLAYERS_OUT` | 2 | Count of top-8 players missing |
| `DIFF_AVAILABLE_IMPACT` | 1 | Home - Away available impact differential |
| `DIFF_MISSING_IMPACT` | 1 | Home - Away missing impact differential |

**Key Benefits**:
1. **SHAP-friendly**: Model learns player availability effects; SHAP shows "LeBron James OUT: -6.9 pts"
2. **Learned interactions**: Model discovers how absences interact with matchups, pace, depth
3. **Non-linear effects**: Losing 2nd-best player when star is out has different impact
4. **No post-hoc adjustment**: Roster is integrated into prediction, not bolted on after

**⚠️ IMPORTANT: Player Impact Cache Dependency**

Player slot features require a **pre-populated cache** in the `player_impact` MySQL table. Without this cache, all slot features will be zeros and model performance will suffer.

```
┌─────────────────────────────────────────────────────────────────────────┐
│  player_impact.py                                                        │
│  populate_player_impact_table() ───WRITES───► player_impact table       │
│                                                     │                    │
│  (Run FIRST, for multiple historical dates)         │                    │
└─────────────────────────────────────────────────────│────────────────────┘
                                                      │
                                                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  feature_engineering.py                                                  │
│  bulk_fetch_player_impacts() ◄───READS──── player_impact table          │
│           │                                                              │
│           ▼                                                              │
│  calculate_player_slot_features() → SLOT features in nba_ml_features.csv│
└─────────────────────────────────────────────────────────────────────────┘
```

**How the Cache Works**:

1. **Computing impacts is expensive** (~2 min per date): For each player, it compares team performance WITH vs WITHOUT them across their game history.

2. **Cache uses "compute dates"**: You populate the cache for specific dates (e.g., 2023-01-01, 2023-07-01). Each record stores a player's impact *as of* that date.

3. **Lookup finds most recent date**: When processing a game on 2023-05-15, the system finds the most recent compute_date ≤ 2023-05-15 (in this case, 2023-01-01).

4. **Player impacts are stable**: A player's historical WITH/WITHOUT impact doesn't change dramatically week-to-week, so caching every 6 months is usually sufficient.

**Recommended Cache Dates** (covers typical training data):
```python
dates = ['2022-01-01', '2022-07-01',   # 2021-22 season
         '2023-01-01', '2023-07-01',   # 2022-23 season
         '2024-01-01', '2024-07-01',   # 2023-24 season
         '2024-12-11']                  # Current
```

**Symptoms of Empty/Missing Cache**:
- Warning: `"No player impacts found in cache!"`
- All `SLOT_*_IMPACT` features are 0.0
- Model performance is worse than expected (check the Model Performance tab — if test MAE has crept up vs the prior registered version, the cache is likely the cause)

**Player Impact Table Schema** (`player_impact` in MySQL):
```sql
CREATE TABLE player_impact (
    player_id BIGINT NOT NULL,
    team_id BIGINT NOT NULL,
    compute_date DATE NOT NULL,
    player_name VARCHAR(100),
    impact FLOAT,              -- Weighted impact score
    raw_impact FLOAT,          -- Unweighted historical impact
    confidence VARCHAR(20),    -- HIGH/MEDIUM/LOW/INSUFFICIENT
    method VARCHAR(20),        -- 'historical' or 'advanced'
    avg_minutes FLOAT,
    avg_usage FLOAT,
    importance_multiplier FLOAT,
    PRIMARY KEY (player_id, team_id, compute_date)
);
```

### Pre-Game Injury Report Source (E7, 2026-05-19) ⬅️ NEW

**Why this matters**: Before E7, the `*_SLOT_X_AVAILABLE` features were derived from `boxscoretraditionalv3_player` — the **post-game** boxscore. For a 2022 training row, the model effectively "knew" pre-game whether each star player ended up showing up, which is post-hoc information it wouldn't have at real prediction time. Literature flags this pattern as commonly inflating training accuracy 2–5pp.

**Data source**: NBA's official mandated **pre-game injury report PDFs**, hosted at `https://ak-static.cms.nba.com/referee/injury/`. These are released by the league at scheduled intervals before each game day (5 PM ET day-before, then hourly through game day, then a "final" report ~30 min before tipoff). We pull the latest report available on each game date — the one closest to "what the world knew right before tipoff."

**Acquisition**: `data_engineering/historical_injury_scraper.py` wraps the [`nbainjuries`](https://pypi.org/project/nbainjuries/) PyPI package and inserts the parsed rows into a new MySQL table `historical_injury_report`. The scraper handles BOTH historical URL formats (NBA changed convention on 2025-12-22 from hourly `Injury-Report_YYYY-MM-DD_HHPM.pdf` to 15-min granularity `Injury-Report_YYYY-MM-DD_HH_MMPM.pdf` — see `historical_injury_scraper.py:_gen_url_*_format`).

```bash
# First-time population (one-shot, ~30 min for full 2022-2026 window)
python data_engineering/historical_injury_scraper.py --start-date 2022-01-01

# Re-runnable / idempotent (uses INSERT IGNORE on the unique (game_date, team_name, player_name) key)
python data_engineering/historical_injury_scraper.py --start-date 2025-12-22
```

**Schema** (`historical_injury_report` in MySQL):
```sql
CREATE TABLE historical_injury_report (
    id INT AUTO_INCREMENT PRIMARY KEY,
    game_date DATE NOT NULL,
    report_timestamp DATETIME NOT NULL,        -- when the report was published (closest to tipoff)
    team_name VARCHAR(50) NOT NULL,            -- as printed in the PDF (e.g., 'Los Angeles Lakers')
    team_id BIGINT NULL,                       -- resolved against nba_teams.id (may be NULL if unresolved)
    matchup VARCHAR(20) NULL,                  -- e.g., 'SAC@IND'
    player_name VARCHAR(100) NOT NULL,         -- as printed: 'Last, First' format
    player_id BIGINT NULL,                     -- resolved against nba_players.id
    status VARCHAR(20) NOT NULL,               -- Out / Doubtful / Questionable / Probable / Available
    reason TEXT NULL,                          -- 'Injury/Illness - Right Knee; Soreness', etc.
    source VARCHAR(50) NOT NULL DEFAULT 'nba_official_pdf',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_game_date (game_date),
    INDEX idx_team_player (team_id, player_id),
    INDEX idx_status (status),
    UNIQUE KEY unique_player_game (game_date, team_name, player_name)
);
```

**Example row** (game on 2025-12-08, Pacers vs Kings):
| game_date | report_timestamp | team_name | player_name | status | reason |
|---|---|---|---|---|---|
| 2025-12-08 | 2025-12-08 20:30 | Indiana Pacers | Haliburton, Tyrese | Out | Injury/Illness - Right Achilles Tendon; Strain |
| 2025-12-08 | 2025-12-08 20:30 | Sacramento Kings | Sabonis, Domantas | Out | Injury/Illness - Left Knee; Partial Meniscus Tear |
| 2025-12-08 | 2025-12-08 20:30 | Sacramento Kings | Murray, Keegan | Questionable | Injury/Illness - Right Trapezius; Soreness |

**How features consume this**: `data_engineering/player_impact.py:bulk_fetch_pregame_availability()` is the leak-free replacement for the older `bulk_fetch_player_availability()` (which still reads post-game boxscore data and is retained as a legacy path). `calculate_player_slot_features` takes an `availability_source` parameter (default `'pregame'`); modes:
- `'pregame'` — `*_SLOT_X_AVAILABLE = 0` if the player appears in `historical_injury_report` with status Out or Doubtful, else 1. **Point-in-time correct for training.** (default)
- `'postgame'` — legacy boxscore-derived. Retained for A/B comparison only.
- `'auto'` — `'pregame'` for dates the table covers, `'postgame'` fallback for dates it doesn't. Useful if extending to seasons before 2022 (which the official PDF archive doesn't cover).

**Backfilled-prediction flow**: When `modeling/predict_games.py --start-date X` regenerates historical predictions, `_fetch_historical_injuries_for_date()` queries `historical_injury_report` per game date instead of calling the live ESPN feed (`--auto-injuries` is automatically sourced from history in backfill mode). This makes backfilled `model_predictions` rows comparable to "true live" rows from the same era.

**Coverage as of 2026-05-19**: 106,755 rows, 969 distinct game-dates spanning 2022-01-01 → 2026-05-13. The ~71 game-dates in this window NOT in the table are All-Star breaks, preseason, and other off-days where no league injury report was published (expected gaps). Player-name resolution rate ≈ 97%; team-name resolution rate ≈ 97%. Unresolved names are typically current-season rookies missing from `nba_players` (refresh that table to pick them up).

---

### Player Projection Features (9 features per team)

Aggregates individual player stats with opponent adjustments:

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

**Total: ~550 features** (rolling stats + fatigue + player slots + projections + differentials)

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
5. Calculates player projection features (opponent-adjusted)
6. Calculates injury impact features (legacy aggregate)
7. **NEW**: Calculates player slot features (top 8 players per team with availability)
8. Creates matchup features (HOME_, AWAY_, DIFF_ prefixes)
9. Exports ML-ready dataset to CSV

**Pipeline Steps:**
```
[1/8]  Loading game data
[2-7]  Loading advanced/four factors/hustle/tracking/misc/scoring stats
[8/8]  Calculating rolling features (76 stats × 2 windows = 152 features)
[9/11] Player projection features
[10/11] Injury impact features (legacy)
[11/11] Player slot features (NEW - integrated roster model)
```

**Key concepts:**
- **Data leakage prevention**: Uses `shift(1)` to exclude current game from rolling calculations
- **Fatigue tracking**: Counts games in rolling windows to measure schedule density
- **Integrated roster model**: Player availability embedded as features, not post-hoc adjustment

**Output:** `nba_ml_features.csv` (~8,800 games, ~700 columns)

```bash
python data_engineering/feature_engineering.py
python data_engineering/feature_engineering.py --no-player-features  # Skip player features (faster)
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
Random Forest wins both classification and regression on this baseline. Current numeric metrics are not hardcoded here — they live in the `model_registry` table and are surfaced in the **Model Performance** tab of `dataExploration.py`. Run `python core/model_registry.py` for a one-shot console dump.

**Top predictive features:**
1. DIFF_netRating_L10 (net rating differential)
2. DIFF_PIE_L10 (Player Impact Estimate differential)
3. DIFF_PLUS_MINUS_L10 (plus/minus differential)

```bash
python modeling/baseline_models.py
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
Random Forest has consistently outperformed the PyTorch MLP on this tabular dataset across our training runs — tree-based models often win on structured data. Specific AUC/MAE numbers are not pinned here because they shift each retrain; see the **Model Performance** tab for the current registry values per model version.

```bash
python modeling/pytorch_nba_models.py
```

---

### 5. `dataExploration.py` - Visualization Dashboard

**What it does:**
Launches an interactive Dash web application with 8 tabs:

1. **Operations** ⬅️ NEW — Pipeline orchestrator: see what's stale, run any subset of stages (fetch_data → player_impact → features → train → predict → backfill → validate), tail the log live.
2. **Overall League Data — Scatter**: Plot any pair of league-level stats
3. **Pearson Correlation Matrix**: Identify correlated stats with reduced matrix view
4. **Team-by-team Data — Scatter**: Same as #2 but filterable by team
5. **Rolling Feature Tracker**: Track any feature over the season for each team
6. **Margin Correlation Analysis**: Pearson correlations with winning margin
7. **Game Predictions**: Compare Random Forest vs Neural Network predictions
8. **Model Performance** — Training claims vs live prediction performance, with hyperparameters and training-window metadata per registry row.

**Game Predictions Tab Features:**
- Date picker with Today/Tomorrow quick-select
- Side-by-side comparison table (RF vs NN)
- AGREE/DISAGREE badges showing model consensus
- Win probability bar chart comparing both models
- Margin distribution violin plots showing uncertainty
- Model explanation cards

```bash
python visualization/dataExploration.py
# Open http://127.0.0.1:5000 in browser
```

---

**Model Performance Tab (NEW)**

Surfaces the gap between what models claimed at training time and how they're actually doing on live predictions. Reads from two MySQL tables:

- `model_registry` — training-time metrics (accuracy, AUC, MAE, R²) per model version, populated by `predict_games.py` retraining and by `validate_models.py`.
- `model_predictions` — daily predictions logged by `predict_games.py`, backfilled with actual results via `python modeling/prediction_tracker.py --backfill --lookback 200`.

What you'll see:
- **Headline cards** per model: live accuracy, MAE, RMSE, calibration error over your selected date range
- **Rolling charts**: 10-game rolling accuracy and MAE over time
- **Reliability diagram**: predicted win-prob deciles vs actual win rate (the real test of "is 70% really 70%?")
- **Residual plot**: predicted margin vs (actual − predicted) — spot bias regions
- **Margin error histogram**: distribution of |actual − predicted|
- **Registry table**: every training run + every validation row, with the active version highlighted

To make this tab useful on first load, run the backfill once so historical predictions have actuals:
```bash
python modeling/prediction_tracker.py --backfill --lookback 200
```

**Registry schema (extended 2026-05)** — every row in `model_registry` now also stores:
- `train_start_date` / `train_end_date` — temporal window the model was trained on
- `test_start_date` / `test_end_date` — temporal window the test metrics were measured on
- `hyperparameters` (JSON) — n_estimators, max_depth, lr, dropout, hidden_dims, etc.
- `train_metrics` (JSON) — same metrics computed on the training set, so the overfit gap is visible
- `notes` (TEXT), `run_kind` ('train' | 'validation') — provenance

These are all surfaced in the Model Performance tab's registry table (filterable / sortable / hover-for-full-value tooltips).

---

### 6. `pipeline.py` - One-Shot Orchestrator

Sequences every script in this project from a single entry point and decides what stages need to run based on the freshness of various DB tables.

```bash
python pipeline.py status        # JSON freshness report — every input layer, last-known date, days-ago
python pipeline.py recommend     # which stages should run, with reasons
python pipeline.py run --stages all
python pipeline.py run --stages features,train,predict
python pipeline.py run --stages predict --predict-date 2026-05-18
```

Stages, in canonical order: `fetch_data → player_impact → features → train → predict → backfill → validate`. Each stage maps 1:1 to running the underlying script — pipeline.py doesn't replace any existing CLI, it just sequences them and logs to `logs/pipeline_<run_id>.log`.

The dashboard's **Operations** tab uses the same orchestrator under the hood: tick stages, fill in any args, hit Run, and watch the log tail update every 3 seconds.

---

### 7. `validate_models.py` - Held-Out Validation Runner

**What it does:**
Re-runs the currently-saved RF and NN models against a date window from `nba_ml_features.csv`, computes accuracy / AUC / MAE / RMSE / R² / calibration, and (by default) writes the results into `model_registry` as validation rows so the dashboard can show training-vs-recent metrics side by side.

Validation rows have `is_current = FALSE` and a model_version like `rf_classifier_validation_<timestamp>_<startdate>_<enddate>` so they never displace the production model.

```bash
# Default: last 60 days of available data, both models, write to registry
python modeling/validate_models.py

# Custom window
python modeling/validate_models.py --start 2025-12-13 --end 2026-01-07

# RF only
python modeling/validate_models.py --model rf

# Don't touch the registry (dry run)
python modeling/validate_models.py --no-register
```

**Tip**: To get a true out-of-sample read, set `--start` to the day after your most recent training date (visible in the dashboard's registry table or in `model_registry.training_date`). Including pre-training games in the window will inflate the metrics.

---

### 7. `schema_exploration.py` - Database Utility

**What it does:**
- Lists all 36 tables in the database
- Shows row counts for each table
- Displays column schemas
- Shows date range and sample data

```bash
python data_engineering/schema_exploration.py
```

---

## Validation Methodology

Three layered evaluation paths, each answering a different question. Knowing which one is used for any given number matters more than the number itself.

### 1. Training-time 80/20 temporal split (what lands in `model_registry`)

When `pipeline.py run --stages train` (or `predict_games.py` triggering retrain) runs, the data flow inside each `load_or_train_*` function:

1. Read `nba_ml_features.csv`.
2. Sort by `GAME_DATE`, split: first 80% rows = train, last 20% = test. **No shuffling** — temporal order preserved.
3. Train on the 80% chunk, evaluate on the 20% chunk → these are the `test_*` columns in the new `model_registry` row (test_accuracy, test_auc, test_mae, test_rmse, test_r2, test_precision, test_recall, test_f1).
4. Also compute the same metrics on the 80% training chunk itself → stored in `train_metrics` JSON. The train-vs-test gap quantifies overfitting.
5. Retrain on the **full 100% dataset** for production; this is the model that gets saved to `models/bundles/<key>_<version>.joblib`.

This is what every E1–E8 baseline number above the master table refers to (except those tagged "walk-forward"). The metrics characterize the *production model*'s expected performance, even though the production model itself was trained on slightly more data than the model whose metrics were measured.

### 2. Walk-forward validation across multiple windows (`experiments/e2_walk_forward.py`)

The "is the 75% real?" check. For each of 5 windows (W1–W5):
1. Slice `nba_ml_features.csv` to rows with `GAME_DATE < window.start` → training set.
2. Slice to rows in `[window.start, window.end]` → test set.
3. Fit a **fresh** SimpleImputer + StandardScaler on the training slice (never sees the test slice).
4. Train fresh RF / NN / XGB models with the current production hyperparameters.
5. Predict on the test slice. Compute accuracy / AUC / precision / recall / F1 / MAE / R².

Crucial: each model is trained **strictly on data before** its test window. No memorization possible. This is what the master experiment table's W5 numbers refer to. Re-runnable any time hyperparameters change; output JSON at `outputs/e2_walk_forward_results.json`.

```bash
python experiments/e2_walk_forward.py
```

### 3. Live-prediction tracking (`model_predictions` table + Model Performance tab)

For predictions actually made via `predict_games.py` (either daily live, or backfilled via `--start-date`):
1. Every prediction logged to `model_predictions` table at prediction time (timestamp, model_version, win_probability, predicted_margin, etc.).
2. `prediction_tracker.py --backfill` joins each row against the now-completed boxscore and fills in `actual_winner`, `actual_margin`, `is_correct`, `margin_error`.
3. The dashboard's **Model Performance** tab reads from this table and renders rolling accuracy, MAE, ROC curve, confusion matrix, reliability diagram per model over any selected date range.

Live tracking is the only path that catches concept drift (the world changes; the model doesn't). The other two paths only tell you "how well does the model fit historical data."

### When to trust which number

| Question | Use |
|---|---|
| "Did my hyperparameter change move the needle?" | (2) walk-forward, multiple windows, average across seeds. The 80/20 temporal split is too noisy for this. |
| "How will this model do in production over the next month?" | (2) walk-forward W5 (most-recent window) as best proxy. |
| "How is the live model actually doing right now?" | (3) Model Performance tab, last 30 days. |
| "Quick sanity check during a retrain" | (1) `model_registry.test_*` values. Acknowledge the production model's metrics are not literally these numbers. |

### Caveats specific to this project

- **Pre-E7 (before 2026-05-19): every metric was inflated by a feature-engineering leak** (`_AVAILABLE` features derived from post-game boxscore). The leak fix (E7) re-measures everything; expect 2–5pp accuracy drop on apples-to-apples comparison.
- **The "actual home win" derivation** for the dashboard's reliability diagram / confusion matrix uses `(actual_winner == home_team)` — i.e., we treat home-team wins as the positive class. Flip the comparison if you want to evaluate "predicted away-team wins" as the positive class instead.
- **All single-seed runs of NN are noisy** at this dataset size; differences <2pp between two NN runs of the same config are usually within seed variance even after `torch.manual_seed(42)` (BatchNorm + DataLoader order interact in subtle ways).

---

## Model Comparison

### Random Forest (scikit-learn)
- **Algorithm**: Ensemble of 100 decision trees
- **Uncertainty**: Each tree votes independently; distribution shows agreement
- **Strengths**: Great for tabular data, handles missing values, fast training
- **Performance**: see Model Performance tab (current values from `model_registry`)

### Neural Network (PyTorch)
- **Algorithm**: 3-layer MLP (128→64→32→1) with BatchNorm & Dropout (0.3)
- **Uncertainty**: Monte Carlo Dropout (100 forward passes with dropout enabled)
- **Target Scaling**: Regression targets normalized to mean=0, std=1 during training (see Experiments section)
- **Strengths**: Learns complex patterns, scales to large data, GPU acceleration
- **Performance**: see Model Performance tab (current values from `model_registry`)

### Neural Network with Player Embeddings (PyTorch) ⬅️ NEW
- **Algorithm**: 4-layer MLP (256→128→64→1) with BatchNorm, Dropout, and player embedding layer
- **Embedding Layer**: Maps player IDs → 16-dimensional learned vectors
- **Input**: Team features + 16 player embeddings (8 per team) + availability masks
- **Architecture**:
  ```
  Player IDs (16) → Embedding(n_players, 16) → Flatten → Concat with team features
                                                              ↓
  Team Features (500+) ──────────────────────────────────→ Linear(256) → ... → Output
  ```
- **Key Advantage**: Learns player-specific effects beyond historical impact scores
  - Player synergies and conflicts
  - Matchup-specific patterns
  - Style interactions (pace, defensive schemes)
- **Availability Masking**: OUT players' embeddings are zeroed, teaching the model absence effects
- **Usage**: `python modeling/predict_games.py --model nn-embed`

### Why Random Forest Wins on Tabular Data
1. Decision trees naturally capture feature interactions
2. Handles heterogeneous features well (counts, percentages, binary)
3. Less tuning required than neural networks
4. Sample size (~8,000 games) favors simpler models

---

## Model Bundles & Rollback

Every training run writes a **single versioned bundle** to `models/bundles/<key>_<version>.joblib` containing the full artifact set needed to reproduce that model's predictions:

- For sklearn families (RF): `{classifier, regressor, scaler_tuple, feature_names, feature_count, hyperparameters_*, metadata}`
- For PyTorch families (NN, NN-embed): `{classifier_state_dict, regressor_state_dict, classifier_class, regressor_class, input_dim, target_scaler, scaler_tuple, feature_names, hyperparameters_*, metadata}`

Both the `<type>_classifier` and `<type>_regressor` rows in `model_registry` reference the same bundle file in their `file_path` column, so loading a specific historical version reconstructs the exact (classifier, regressor, scaler, features) tuple that produced those metrics.

A `models/bundles/<key>_current.joblib` pointer is updated on every retrain — `load_model_bundle(key)` with no `version` argument loads the latest. Atomicity is guaranteed by `os.replace` on a `.tmp` file, so a killed training process can't leave a half-written bundle.

Legacy fixed-name files (`models/rf_classifier.joblib` etc.) are also still written for any reader that hasn't been migrated; they're not the source of truth anymore.

---

## Adding a New Model Type

Models are dispatched through a central registry, so neither `pipeline.py` nor `dataExploration.py` needs to know that "xgboost" or "lightgbm" exists. To add one (replace `xgb` with your key):

**1. Append a spec to `modeling/model_types.py:MODEL_TYPES`:**
```python
ModelTypeSpec(
    key='xgb',
    display_name='XGBoost',
    classifier_registry_type='xgb_classifier',
    regressor_registry_type='xgb_regressor',
    color='#f1c40f',              # any hex color for charts
    description='Gradient-boosted trees with depth control',
    framework='xgboost',
),
```

**2. In `modeling/predict_games.py`, write `load_or_train_xgb_models(engine, force_retrain=False)`:**
- Mirror `load_or_train_rf_models`: try `load_model_bundle('xgb')` first, fall back to retraining.
- On save, build an `xgb_bundle = {classifier, regressor, scaler_tuple, feature_names, ...}` dict and call `save_model_bundle('xgb', xgb_bundle)`.
- Call `register_model()` twice (one for classifier, one for regressor), passing the bundle path as `file_path` and the hyperparameters dict including `player_impact_snapshot_date`.

**3. Write `predict_with_xgb(...)` returning the standard dict** (`win_prob`, `margin_mean`, `margin_std`, `margin_samples`, `shap_feature_importance`).

**4. Register both in the dispatch tables at the bottom of `modeling/predict_games.py`:**
```python
LOADER_DISPATCH['xgb'] = load_or_train_xgb_models
PREDICT_DISPATCH['xgb'] = lambda data, matchup, **kw: predict_with_xgb(*data, matchup, **kw)
```

Done. The Operations tab's `--model` dropdown gains an `xgb` option, the dashboard's Game Predictions tab loads + plots XGBoost predictions alongside RF/NN, the comparison table gains XGBoost columns, and `python orchestration/pipeline.py run --stages predict --predict-model xgb` works — all with zero edits to `orchestration/pipeline.py` or `visualization/dataExploration.py`.

---

## Directory Structure

Scripts are organized by concern. Each top-level folder is a Python package (has `__init__.py`); every script also has a sys.path bootstrap so it can be run directly (`python modeling/predict_games.py …`) from the project root. **Always run from project root** — relative paths to `models/`, `outputs/`, and `nba_ml_features.csv` assume CWD = repo root.

```
NBAStatsProject/
├── core/                              # Shared infrastructure
│   ├── db.py                          # get_engine() — reads MySQL config from .env
│   └── model_registry.py              # Versioned model registry helpers (training/validation rows)
│
├── data_engineering/                  # Raw data fetch → feature CSV pipeline
│   ├── main_refactored.py             # NBA API → MySQL ingest (boxscores)
│   ├── feature_engineering.py         # Builds nba_ml_features.csv (~500 features)
│   ├── player_impact.py               # Player impact cache (compute_date-snapshotted)
│   ├── player_projections.py          # Per-player projections with opponent adjustments
│   ├── injury_data.py                 # Live injury feed (NBA/ESPN scraper)
│   ├── schema_exploration.py          # Database introspection utility
│   ├── verify_imported_games.py       # Data-sanity script for importedgamesmemory
│   └── add_v3_columns.py              # One-shot schema migration helper
│
├── modeling/                          # Training, prediction, evaluation
│   ├── predict_games.py               # MAIN prediction CLI (RF + NN + SHAP + backfill range)
│   ├── prediction_tracker.py          # Prediction logging + actuals backfill
│   ├── validate_models.py             # Held-out validation runner
│   ├── baseline_models.py             # Sklearn baselines (tutorial-style)
│   ├── pytorch_nba_models.py          # PyTorch training script (tutorial-style)
│   ├── evaluate_impact_approaches.py  # Compares historical vs advanced impact methods
│   └── featureSelection.py            # SelectKBest experiment
│
├── visualization/                     # Dashboards + plotting
│   ├── dataExploration.py             # Dash app (8 tabs incl. Operations + Model Performance)
│   ├── data_exploration_tutorial.py   # SQLAlchemy + pandas tutorial script
│   └── prediction_visualizations.py   # One-off matplotlib charts
│
├── orchestration/                     # Top-level runners
│   └── pipeline.py                    # Status / recommend / run; backs the Operations tab
│
├── tests/
│   └── test_prediction_tracking.py
│
├── deprecated/                        # Superseded scripts kept for reference
│   ├── main.py                        # Old monolithic importer
│   ├── main2.py                       # Older variant
│   ├── NBADataImporter.py             # Old class (superseded by main_refactored.py; has a pre-existing syntax bug at L96)
│   └── importedgamesmemory_discrepancies_*.csv
│
├── sql/
│   └── create_predictions_table.sql   # model_predictions DDL
│
├── docs/
│   └── DATABASE_SCHEMA.md             # Database documentation
│
├── outputs/                           # Generated artifacts (gitignored)
│   ├── predictions_history/           # Per-day prediction PNGs (predictions_YYYYMMDD.png)
│   └── impact_evaluation_results.csv
│
├── models/                            # Saved trained model artifacts
│   ├── rf_classifier.joblib
│   ├── rf_regressor.joblib
│   ├── nn_classifier.pt
│   ├── nn_regressor.pt
│   ├── nn_embed_classifier.pt
│   ├── nn_embed_regressor.pt
│   ├── nn_embed_config.joblib
│   ├── scaler.joblib
│   ├── feature_names.joblib
│   └── nn_config.joblib
│
├── logs/                              # Pipeline run logs (gitignored)
│   └── pipeline_<run_id>.log
│
├── .env                               # MySQL credentials (gitignored)
├── .env.example                       # Template for .env (committed)
├── .gitignore
├── nba_ml_features.csv                # Generated feature CSV (stays at root for CWD-relative reads)
├── requirements.txt
└── README.md
```

### Where things live (TL;DR)

| You want to… | Folder |
|---|---|
| Pull new NBA games into MySQL | `data_engineering/` |
| Rebuild the feature CSV | `data_engineering/` |
| Train, predict, validate, log | `modeling/` |
| See the dashboard / Operations tab | `visualization/` |
| Run the end-to-end pipeline | `orchestration/` |
| Read shared DB / registry helpers | `core/` |
| Look at a generated chart | `outputs/predictions_history/` |
| Run a SQL DDL | `sql/` |
| See the schema docs | `docs/` |

### Common commands (run from project root)

```bash
# Status & orchestration
python orchestration/pipeline.py status                  # what's stale across every layer
python orchestration/pipeline.py recommend               # suggested stages
python orchestration/pipeline.py run --stages all        # full end-to-end
python orchestration/pipeline.py run --stages predict --predict-start 2026-04-01 --predict-no-shap

# Dashboard (Operations + Model Performance tabs)
python visualization/dataExploration.py

# Individual scripts (each still has its full CLI)
python data_engineering/main_refactored.py
python data_engineering/feature_engineering.py
python data_engineering/player_impact.py --populate --date 2026-05-01
python modeling/predict_games.py --date 2026-05-18
python modeling/predict_games.py --start-date 2026-04-01           # backfill range, point-in-time
python modeling/validate_models.py --days 60
python modeling/prediction_tracker.py --backfill --lookback 200
```

---

## Database Connection

The project connects to a local MySQL database. Configuration is **read from environment variables** (see [Database Setup](#database-setup-env-vars) above). Defaults expected:

- Host: `localhost`
- Port: `3306`
- Database: `nba_data`
- Prediction tracking table: `model_predictions`
- Model registry table: `model_registry`

All scripts call `db.get_engine()` from `core/db.py`, which reads the `NBA_DB_*` env vars and constructs a SQLAlchemy engine. Each script also exposes a thin `create_engine()` wrapper for backwards compatibility — that wrapper now just delegates to `core.db.get_engine()`.

---

## Recent Enhancements

### SHAP Feature Importance
- See which features drive each prediction (top 10)
- TreeExplainer for Random Forest (fast, exact)
- GradientExplainer for Neural Network

### Prediction Tracking
```bash
python modeling/predict_games.py --backfill      # Update past predictions with actual results
python modeling/predict_games.py --accuracy-report  # Show accuracy metrics
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

### Integrated Player Slot Model (2025-12-10)

**Problem**: The 2-tier approach (predict margin → adjust for injuries) had limitations:
1. Model couldn't learn interaction effects (player absence × opponent matchup)
2. SHAP couldn't attribute impact to specific players
3. Non-linear effects not captured (losing 2nd player when star already out)

**Solution**: Integrate roster availability directly into features:

```
Previous (2-tier):
  RF/NN → Base Margin → Ad-hoc Injury Adjustment → Final Margin

New (Integrated):
  RF/NN(team_stats + player_slots) → Final Margin
```

**Implementation**:

1. **Player Impact Table** (`player_impact` in MySQL):
   ```sql
   CREATE TABLE player_impact (
       player_id BIGINT NOT NULL,
       team_id BIGINT NOT NULL,
       compute_date DATE NOT NULL,
       player_name VARCHAR(100),
       impact FLOAT,              -- Weighted impact score
       raw_impact FLOAT,          -- Unweighted historical impact
       confidence VARCHAR(20),    -- HIGH/MEDIUM/LOW/INSUFFICIENT
       method VARCHAR(20),        -- 'historical' or 'advanced'
       avg_minutes FLOAT,
       avg_usage FLOAT,
       importance_multiplier FLOAT,
       PRIMARY KEY (player_id, team_id, compute_date)
   );
   ```

2. **Feature Engineering** (`calculate_player_slot_features()`):
   - For each historical game, get top 8 players by impact for each team
   - Check availability from `boxscoreplayertrackv3_player.comment`
   - Create slot features: `{HOME/AWAY}_SLOT_{1-8}_{IMPACT/AVAILABLE}`
   - Parallel processing with batches of 200 games

3. **Prediction Time** (`get_player_slot_features_for_prediction()`):
   - Get current top 8 players by impact
   - Match injury list against player names
   - Return slot features for model input

4. **SHAP Interpretation**:
   - Model outputs: `HOME_SLOT_1_AVAILABLE: -6.9`
   - Lookup: Slot 1 = LeBron James
   - Display: **"LeBron James OUT (-6.9 pts)"**

**New Features Added** (58 total):
| Feature | Count | Description |
|---------|-------|-------------|
| `SLOT_{1-8}_IMPACT` | 16 | Impact score per slot per team |
| `SLOT_{1-8}_AVAILABLE` | 16 | Availability flag per slot |
| `TOTAL_AVAILABLE_IMPACT` | 2 | Sum of available player impacts |
| `TOTAL_MISSING_IMPACT` | 2 | Sum of OUT player impacts |
| `PLAYERS_OUT` | 2 | Count of missing top-8 players |
| `DIFF_*` | 2 | Differentials for above |

**Usage**:
```bash
# Populate player impact table (run daily)
python -c "from player_impact import *; populate_player_impact_table(create_engine())"

# Regenerate training data with new features
python data_engineering/feature_engineering.py

# Retrain models to use new features
python modeling/baseline_models.py
python modeling/pytorch_nba_models.py
```

**Key Files Modified**:
- `player_impact.py`: Added SQL table management + `get_top_players_by_impact()`
- `feature_engineering.py`: Added `calculate_player_slot_features()` (step [11/11])
- `predict_games.py`: Added `get_player_slot_features_for_prediction()` + SHAP player name mapping

---

### Player Embeddings for Neural Network (2025-12-10)

**Motivation**: The integrated player slot model uses pre-computed impact scores, but these are static values that don't capture:
- Player synergies (how well players work together)
- Matchup-specific effects (player A dominates player B)
- Playing style interactions (pace, defensive schemes)

**Solution**: Add an embedding layer that learns player-specific 16-dimensional vectors during training.

**Architecture**:
```
┌─────────────────────────────────────────────────────────────────┐
│                    NBARegressorWithEmbeddings                    │
├─────────────────────────────────────────────────────────────────┤
│  Player IDs (16)    ─→  Embedding(n_players, 16)  ─→  Flatten   │
│        ↓                                                ↓       │
│  Availability (16)  ─→  Mask embeddings (zero OUT)      │       │
│                                                         ↓       │
│  Team Features (500+) ────────────────────────→  Concatenate    │
│                                                         ↓       │
│                                              Linear(256) + BN   │
│                                                         ↓       │
│                                              Linear(128) + BN   │
│                                                         ↓       │
│                                              Linear(64) + BN    │
│                                                         ↓       │
│                                              Linear(1) → Margin │
└─────────────────────────────────────────────────────────────────┘
```

**Key Implementation Details**:

1. **Player ID Mapping**: NBA player IDs (large integers like 1629029) are mapped to sequential indices (0, 1, 2, ...) for the embedding layer.

2. **Availability Masking**: When a player is OUT, their embedding is multiplied by 0, effectively removing them from the model input. This teaches the model absence effects.

3. **Padding Index**: Index 0 is reserved for "unknown/empty" players, initialized to zeros.

4. **Combined Input**:
   ```
   Team features: ~500 dimensions
   Player embeddings: 16 players × 16 dims = 256 dimensions
   Total input: ~756 dimensions
   ```

**Files Added/Modified**:
- `predict_games.py`:
  - `NBAClassifierWithEmbeddings` class
  - `NBARegressorWithEmbeddings` class
  - `create_player_id_mapping()` function
  - `load_or_train_pytorch_embedding_models()` function
  - `predict_with_pytorch_embeddings()` function
  - `--model nn-embed` CLI option

**Usage**:
```bash
# Train and predict with embedding model
python modeling/predict_games.py --model nn-embed

# Models saved to:
# - models/nn_embed_classifier.pt
# - models/nn_embed_regressor.pt
# - models/nn_embed_config.joblib (contains player_to_idx mapping)
```

**Potential Benefits** (to be validated):
- Learn that certain players have outsized effects in specific matchups
- Capture diminishing returns (losing 3rd player when 1st and 2nd are already out)
- Understand roster composition effects (spacing, defense, etc.)

**Limitations**:
- SHAP explanations not yet implemented (would need custom explainer)
- New players (not in training data) map to unknown embedding
- Requires more data to learn meaningful embeddings

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
7. ~~**Injury impact features in training**: Integrated roster model with SHAP visibility~~ ✅ DONE (2025-12-10)
8. ~~**Player embeddings for NN**: Embedding layer for player-specific learned representations~~ ✅ DONE (2025-12-10)
9. **Injury data integration**: Use `nbainjuries` package for real-time injury reports ⬅️ HIGH PRIORITY
   - Currently requires manual `--injuries` flag
   - Real injury data would automate player availability detection
10. **SHAP for embedding model**: Custom explainer for embedding inputs
11. **Minutes redistribution modeling**: Model how minutes shift when a player is OUT
12. **Betting lines**: Compare predictions to Vegas spreads
13. **Ensemble methods**: Combine RF and NN predictions
14. **Travel distance**: Calculate miles traveled for road trips
15. **LLM dashboard commentary**: On the Model Performance tab, call out to an LLM to read the current registry/predictions and write an independent, plain-English assessment of how the models are doing (calibration, drift, regression vs prior version) without me hand-curating numbers in markdown.
16. **Vegas spread benchmark**: Once a line-of-the-day data source is available, add a "vs Vegas" tab comparing our margin predictions to closing spreads — currently parked, no data source.

---

## Troubleshooting

### Player Slot Features All Zeros / Poor Model Performance

**Symptom**: Model MAE has regressed vs prior registered versions (compare in the Model Performance tab), or you see the warning:
```
WARNING: No player impacts found in cache!
Run `python data_engineering/player_impact.py` or `populate_player_impact_table()` to populate the cache.
```

**Cause**: The `player_impact` cache table is empty or doesn't have data for your training date range.

**Solution**: Populate the cache for historical dates before running feature_engineering.py:
```bash
python -c "
from player_impact import create_engine, populate_player_impact_table
engine = create_engine()
for date in ['2022-01-01', '2022-07-01', '2023-01-01', '2023-07-01', '2024-01-01', '2024-07-01']:
    print(f'Populating {date}...')
    populate_player_impact_table(engine, as_of_date=date)
"
# Then regenerate features and retrain
python data_engineering/feature_engineering.py
python modeling/baseline_models.py
python modeling/pytorch_nba_models.py
```

**Verify cache status**:
```bash
python -c "
from player_impact import create_engine
from sqlalchemy import text
engine = create_engine()
with engine.connect() as conn:
    result = conn.execute(text('SELECT compute_date, COUNT(*) FROM player_impact GROUP BY compute_date'))
    for row in result: print(f'{row[0]}: {row[1]} players')
"
```

### Feature Count Mismatch Error

**Symptom**: Error when loading saved model - expected X features but got Y.

**Cause**: You regenerated `nba_ml_features.csv` with different features than the saved model was trained on.

**Solution**: Retrain models after regenerating features:
```bash
python modeling/baseline_models.py
python modeling/pytorch_nba_models.py
```

### PyTorch DLL Error on Windows

**Symptom**: `OSError: [WinError 1114] DLL initialization routine failed`

**Cause**: NumPy loaded before PyTorch on Windows.

**Solution**: PyTorch must be imported first. This is handled automatically in `predict_games.py`. If writing your own script:
```python
# CORRECT - PyTorch first
import torch
import numpy as np
import pandas as pd

# WRONG - Will fail on Windows
import numpy as np
import torch  # OSError!
```

### Slow Feature Engineering

**Symptom**: `calculate_player_slot_features` takes hours instead of seconds.

**Cause**: You're using an old version that makes per-game database queries instead of bulk fetching.

**Solution**: Ensure you have the optimized `bulk_fetch_player_impacts()` function in `player_impact.py` and the corresponding changes in `feature_engineering.py`. The optimized version makes just 2 database queries regardless of game count.
