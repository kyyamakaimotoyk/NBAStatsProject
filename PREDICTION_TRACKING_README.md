# NBA Prediction Tracking System

A comprehensive system for tracking, evaluating, and visualizing NBA game prediction accuracy over time.

## Overview

This system automatically logs predictions to a MySQL database, tracks actual game outcomes, and provides detailed accuracy metrics and visualizations comparing Random Forest and Neural Network models.

## Components

### 1. Database Schema (`prediction_tracker.py`)

**Table: `model_predictions`**

Stores all predictions with the following structure:

```sql
CREATE TABLE model_predictions (
    prediction_id INT AUTO_INCREMENT PRIMARY KEY,
    game_id VARCHAR(50) NOT NULL,
    prediction_timestamp DATETIME NOT NULL,
    game_date DATE NOT NULL,

    -- Model information
    model_type VARCHAR(20) NOT NULL,  -- 'rf' or 'nn'
    model_version VARCHAR(100) NOT NULL,  -- e.g., 'v1.0_480features_20251206'

    -- Teams
    home_team VARCHAR(50) NOT NULL,
    away_team VARCHAR(50) NOT NULL,

    -- Predictions
    predicted_winner VARCHAR(50) NOT NULL,
    predicted_margin FLOAT NOT NULL,
    home_win_probability FLOAT NOT NULL,
    margin_uncertainty FLOAT NULL,

    -- Feature information
    features_used TEXT NULL,  -- JSON snapshot of key features
    feature_count INT NOT NULL,  -- Number of features (e.g., 480)

    -- Actual results (NULL until game completes)
    actual_winner VARCHAR(50) NULL,
    actual_margin FLOAT NULL,
    is_correct BOOLEAN NULL,
    margin_error FLOAT NULL,  -- ABS(predicted_margin - actual_margin)

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    -- Unique constraint: one prediction per game per model type
    UNIQUE KEY unique_prediction (game_id, model_type, model_version)
);
```

### 2. Core Functions (`prediction_tracker.py`)

#### `log_prediction()`
Saves a prediction to the database immediately after it's made.

```python
log_prediction(
    engine=engine,
    game_id="0022400123",
    game_date="2024-12-06",
    home_team="LAL",
    away_team="BOS",
    model_type="rf",  # or "nn"
    model_version="v1.0_480features_20241206",
    predicted_winner="LAL",
    predicted_margin=5.2,
    home_win_probability=0.68,
    margin_uncertainty=3.1,
    feature_count=480
)
```

#### `backfill_actuals()`
Scans for completed games and updates predictions with actual results.

```python
# Update predictions from last 30 days with actual results
results = backfill_actuals(engine, lookback_days=30, verbose=True)
# Returns: {'updated': 15, 'not_found': 2, 'errors': 0}
```

#### `get_prediction_accuracy()`
Calculate accuracy metrics for a model or time period.

```python
metrics = get_prediction_accuracy(engine, model_type='rf', lookback_days=30)
# Returns:
# {
#   'rf': {
#     'total_predictions': 150,
#     'correct_predictions': 112,
#     'accuracy': 0.747,
#     'mean_absolute_error': 9.33,
#     'std_margin_error': 7.21,
#     'calibration_error': 0.082
#   }
# }
```

#### `get_predictions_for_date()`
Retrieve all predictions for a specific date.

```python
predictions = get_predictions_for_date(engine, game_date="2024-12-06")
```

#### `get_all_predictions_with_results()`
Get all predictions that have actual results (for analysis).

```python
df = get_all_predictions_with_results(
    engine,
    model_type='both',  # or 'rf', 'nn'
    start_date='2024-11-01',
    end_date='2024-12-06'
)
```

### 3. Prediction Workflow (`predict_games.py`)

Enhanced with automatic prediction logging:

```bash
# Make predictions and log to database
python predict_games.py --model both

# Make predictions without logging
python predict_games.py --model rf --no-log

# Backfill actual results for past predictions
python predict_games.py --backfill --lookback 30

# Show accuracy report
python predict_games.py --accuracy-report
```

**New Command-Line Arguments:**
- `--no-log`: Skip logging predictions to database
- `--backfill`: Update past predictions with actual results
- `--accuracy-report`: Show accuracy metrics and exit
- `--lookback N`: Days to look back for backfill (default: 30)

### 4. Visualizations (`prediction_visualizations.py`)

Comprehensive visualization suite for analyzing prediction accuracy.

#### Available Charts:

**1. Predicted vs Actual Margin Scatter Plot**
```bash
python prediction_visualizations.py --chart scatter --model both
```
- Visualizes how well predicted margins match actual margins
- Perfect predictions fall on the diagonal line
- Shows Mean Absolute Error (MAE)

**2. Accuracy Over Time**
```bash
python prediction_visualizations.py --chart time --model both
```
- Rolling accuracy window (default: 20 games)
- Shows if model performance is improving/degrading
- Includes both accuracy and MAE over time

**3. Model Comparison**
```bash
python prediction_visualizations.py --chart compare
```
- Side-by-side RF vs NN comparison
- Includes: accuracy, MAE, error distribution, calibration
- Identifies which model performs better in different scenarios

**4. Calibration Curve**
```bash
python prediction_visualizations.py --chart calibration --model both
```
- Predicted probability vs actual win rate
- Perfect calibration = points on diagonal
- Bubble size = number of predictions in that bin

**5. Comprehensive Dashboard**
```bash
python prediction_visualizations.py --chart dashboard --save accuracy_dashboard.png
```
- 6-panel dashboard with all key metrics
- Best for presentations and reports
- Includes: scatter, bars, time series, distributions

#### Visualization Options:
```bash
# Specific model only
python prediction_visualizations.py --chart scatter --model rf

# Save to file
python prediction_visualizations.py --chart dashboard --save dashboard.png

# Last 60 days only
python prediction_visualizations.py --chart time --days 60
```

## Usage Workflow

### Step 1: Make Predictions

```bash
# Predict today's games with both models
python predict_games.py --model both
```

Output:
```
NBA Game Predictor
==========================================
Prediction date: 2024-12-06
Model: both
Prediction tracking: ENABLED

Processing: BOS @ LAL
...

2 predictions logged to database (model_predictions table)
Model version: v1.0_480features_20241206
Feature count: 480

To backfill actual results later, run:
  python predict_games.py --backfill

To see accuracy report:
  python predict_games.py --accuracy-report
```

### Step 2: Wait for Games to Complete

Games are played and results stored in the `game_list` table by your data ingestion pipeline.

### Step 3: Backfill Actual Results

```bash
# Update predictions from last 30 days with actual results
python predict_games.py --backfill --lookback 30
```

Output:
```
Backfilling actual results (last 30 days)...
Found 10 games with predictions pending actual results
  Updated game 0022400123: BOS @ LAL, Winner: LAL, Margin: +6.0
  Updated game 0022400124: GSW @ MIA, Winner: MIA, Margin: -3.0
  ...

Backfill complete: 20 predictions updated, 0 games not found, 0 errors
```

### Step 4: View Accuracy Report

```bash
python predict_games.py --accuracy-report
```

Output:
```
================================================================================
PREDICTION ACCURACY REPORT
All time
================================================================================

Random Forest (rf):
  Total predictions: 150
  Correct predictions: 112
  Accuracy: 74.7%
  Mean Absolute Error: 9.33 points
  Std Margin Error: 7.21 points
  Calibration Error: 0.082

Neural Network (nn):
  Total predictions: 150
  Correct predictions: 108
  Accuracy: 72.0%
  Mean Absolute Error: 9.94 points
  Std Margin Error: 7.58 points
  Calibration Error: 0.095
================================================================================
```

### Step 5: Generate Visualizations

```bash
# Create comprehensive dashboard
python prediction_visualizations.py --chart dashboard --save accuracy_dashboard.png

# View accuracy trends over time
python prediction_visualizations.py --chart time --model both

# Check calibration
python prediction_visualizations.py --chart calibration --model both
```

## Model Versioning

The system automatically tracks model versions based on:
- Feature count (e.g., 480 features)
- Date of prediction

Version format: `v1.0_{feature_count}features_{YYYYMMDD}`

Example: `v1.0_480features_20241206`

This allows you to:
- Track performance changes when you add/remove features
- Compare different model iterations
- Ensure reproducibility

## Integration with Dashboard

The prediction tracking system can be integrated into your Dash dashboard (`dataExploration.py`).

Key integration points:
1. **Prediction History Tab**: Show all past predictions with outcomes
2. **Accuracy Metrics**: Live accuracy stats for each model
3. **Performance Trends**: Charts showing accuracy over time
4. **Recent Predictions**: Table of upcoming games with predictions

Example code to add to dashboard:
```python
from prediction_tracker import get_all_predictions_with_results, get_prediction_accuracy

# In callback
@app.callback(...)
def update_accuracy_metrics():
    engine = create_engine()
    metrics = get_prediction_accuracy(engine)
    df = get_all_predictions_with_results(engine, lookback_days=30)

    # Create visualizations
    fig = px.scatter(df, x='predicted_margin', y='actual_margin', color='model_type')

    return fig, metrics
```

## Database Queries

Useful SQL queries for analysis:

```sql
-- Overall accuracy by model
SELECT
    model_type,
    COUNT(*) as total,
    SUM(is_correct) as correct,
    AVG(is_correct) as accuracy,
    AVG(margin_error) as mae
FROM model_predictions
WHERE actual_winner IS NOT NULL
GROUP BY model_type;

-- Recent predictions
SELECT
    game_date, home_team, away_team,
    predicted_winner, predicted_margin, home_win_probability,
    actual_winner, actual_margin, is_correct
FROM model_predictions
WHERE game_date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
ORDER BY game_date DESC;

-- Best and worst predictions
-- Best (smallest error)
SELECT game_date, home_team, away_team, model_type, margin_error
FROM model_predictions
WHERE actual_winner IS NOT NULL
ORDER BY margin_error ASC
LIMIT 10;

-- Worst (largest error)
SELECT game_date, home_team, away_team, model_type, margin_error
FROM model_predictions
WHERE actual_winner IS NOT NULL
ORDER BY margin_error DESC
LIMIT 10;

-- Accuracy by confidence level
SELECT
    CASE
        WHEN home_win_probability >= 0.8 THEN 'Very Confident (80%+)'
        WHEN home_win_probability >= 0.65 THEN 'Confident (65-80%)'
        WHEN home_win_probability >= 0.55 THEN 'Slight Edge (55-65%)'
        ELSE 'Toss-up (50-55%)'
    END as confidence_level,
    COUNT(*) as games,
    AVG(is_correct) as accuracy
FROM model_predictions
WHERE actual_winner IS NOT NULL
GROUP BY confidence_level;
```

## Performance Monitoring

Track these key metrics:

1. **Accuracy**: % of correct winner predictions
   - Target: >70% (Vegas typical: 66-68%)

2. **Mean Absolute Error (MAE)**: Average margin prediction error
   - Target: <10 points

3. **Calibration Error**: How well probabilities match actual win rates
   - Target: <0.1 (lower is better)

4. **Margin Std**: Consistency of margin predictions
   - Lower = more consistent predictions

## Troubleshooting

**Problem: Predictions not being logged**
```bash
# Check if table exists
python prediction_tracker.py --create-table

# Try logging with verbose output
python predict_games.py --model rf  # Should show "Prediction tracking: ENABLED"
```

**Problem: Backfill not finding games**
- Ensure games have been ingested into `game_list` table
- Check that `GAME_ID` matches between predictions and game_list
- Verify `WL` and `PTS` columns are populated

**Problem: Accuracy seems too low/high**
- Check calibration curve to see if probabilities are well-calibrated
- Review recent predictions to identify patterns
- Compare RF vs NN to see if one is consistently better

## Files

- `prediction_tracker.py` - Core tracking functionality
- `prediction_visualizations.py` - Visualization suite
- `predict_games.py` - Enhanced with logging integration
- `PREDICTION_TRACKING_README.md` - This file

## Future Enhancements

Potential improvements:
1. **Feature Importance Tracking**: Log which features most influenced each prediction
2. **Ensemble Predictions**: Average RF and NN for better accuracy
3. **Confidence Intervals**: Track prediction uncertainty better
4. **Alert System**: Email/SMS when high-confidence predictions are made
5. **Betting Simulation**: Track hypothetical betting returns
6. **Real-time Updates**: Auto-backfill when games complete
7. **Web Dashboard**: Real-time prediction tracker with live updates

## License & Credits

Part of the NBA Stats Project by Kai Yamamoto.
Uses nba_api, scikit-learn, PyTorch, and MySQL.
