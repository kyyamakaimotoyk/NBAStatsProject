"""
NBA Prediction Tracker
======================

Tracks model predictions and actual results for NBA games in a MySQL database.

Functions:
- log_prediction() - Save predictions to database
- update_actual_result() - Update with actual game outcomes
- get_prediction_accuracy() - Calculate accuracy metrics
- get_predictions_for_date() - Retrieve predictions for a date
- backfill_actuals() - Auto-update past predictions with results

Database Schema:
- model_predictions table stores predictions and outcomes
- Tracks both Random Forest and Neural Network model predictions
- Supports model versioning and feature tracking
"""

# Project-root bootstrap so cross-folder imports (core.db, ...) work regardless of CWD.
import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

import sqlalchemy as sql
from sqlalchemy import text, inspect
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
from typing import Optional, Dict, List, Tuple


# ============================================================================
# DATABASE CONNECTION
# ============================================================================

def create_engine():
    """Create database connection engine. Reads MySQL config from environment via db.get_engine()."""
    from core.db import get_engine
    return get_engine()


# ============================================================================
# TABLE CREATION
# ============================================================================

def create_predictions_table(engine):
    """
    Create the model_predictions table if it doesn't exist.

    Schema includes:
    - Prediction metadata (game, model, timestamp)
    - Predicted values (winner, margin, probability)
    - Feature snapshot (for reproducibility)
    - Actual results (filled after game completes)
    - Accuracy metrics
    """
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS model_predictions (
        prediction_id INT AUTO_INCREMENT PRIMARY KEY,
        game_id VARCHAR(50) NOT NULL,
        prediction_timestamp DATETIME NOT NULL,
        game_date DATE NOT NULL,

        -- Model information
        model_type VARCHAR(20) NOT NULL COMMENT 'rf or nn',
        model_version VARCHAR(100) NOT NULL COMMENT 'e.g., v1.0_480features',

        -- Teams
        home_team VARCHAR(50) NOT NULL,
        away_team VARCHAR(50) NOT NULL,

        -- Predictions
        predicted_winner VARCHAR(50) NOT NULL,
        predicted_margin FLOAT NOT NULL COMMENT 'Positive = home team wins',
        home_win_probability FLOAT NOT NULL COMMENT '0.0 to 1.0 - ISOTONIC-CALIBRATED (E13) P(home wins). Authoritative signal driving predicted_winner.',
        home_win_probability_raw FLOAT NULL COMMENT 'Pre-isotonic P(home wins) from the base classifier. Logged alongside the calibrated one so the dashboard can A/B them. NULL for legacy rows + for NN (no calibrator).',
        margin_uncertainty FLOAT NULL COMMENT 'Standard deviation of margin predictions',

        -- Feature information
        features_used TEXT NULL COMMENT 'JSON snapshot of key features',
        feature_count INT NOT NULL COMMENT 'Number of features in model',

        -- Actual results (NULL until game completes)
        actual_winner VARCHAR(50) NULL,
        actual_margin FLOAT NULL COMMENT 'Positive = home team won',
        is_correct BOOLEAN NULL COMMENT 'Was predicted winner correct?',
        margin_error FLOAT NULL COMMENT 'ABS(predicted_margin - actual_margin)',

        -- Metadata
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

        -- Indexes for fast queries
        INDEX idx_game_date (game_date),
        INDEX idx_game_id (game_id),
        INDEX idx_model_type (model_type),
        INDEX idx_model_version (model_version),
        INDEX idx_prediction_timestamp (prediction_timestamp),

        -- Unique constraint: one prediction per game per model type
        UNIQUE KEY unique_prediction (game_id, model_type, model_version)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """

    with engine.connect() as conn:
        conn.execute(text(create_table_sql))
        conn.commit()

    print("Table 'model_predictions' created or already exists")


def table_exists(engine) -> bool:
    """Check if model_predictions table exists."""
    inspector = inspect(engine)
    return 'model_predictions' in inspector.get_table_names()


def ensure_table_exists(engine):
    """Ensure the predictions table exists, create if not. Also runs the small
    schema migrations the project has accumulated, since they're cheap and
    idempotent (information_schema check before each ALTER)."""
    if not table_exists(engine):
        create_predictions_table(engine)
        return
    # E13 audit migration (2026-05-26): add home_win_probability_raw if missing.
    with engine.connect() as conn:
        has_raw = conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = 'model_predictions' "
            "AND column_name = 'home_win_probability_raw'"
        )).scalar()
        if not has_raw:
            conn.execute(text(
                "ALTER TABLE model_predictions ADD COLUMN home_win_probability_raw FLOAT NULL "
                "COMMENT 'Pre-isotonic P(home wins). NULL for legacy rows + for models without a calibrator.' "
                "AFTER home_win_probability"
            ))
            conn.commit()
            print("Added column model_predictions.home_win_probability_raw")


# ============================================================================
# LOG PREDICTIONS
# ============================================================================

def log_prediction(
    engine,
    game_id: str,
    game_date: str,
    home_team: str,
    away_team: str,
    model_type: str,
    model_version: str,
    predicted_winner: str,
    predicted_margin: float,
    home_win_probability: float,
    margin_uncertainty: Optional[float] = None,
    features_used: Optional[Dict] = None,
    feature_count: int = 0,
    home_win_probability_raw: Optional[float] = None
) -> int:
    """
    Log a prediction to the database.

    Args:
        engine: SQLAlchemy engine
        game_id: NBA API game ID
        game_date: Date of the game (YYYY-MM-DD)
        home_team: Home team abbreviation
        away_team: Away team abbreviation
        model_type: 'rf' or 'nn'
        model_version: Version string (e.g., 'v1.0_480features')
        predicted_winner: Team abbreviation of predicted winner
        predicted_margin: Predicted point margin (positive = home wins)
        home_win_probability: Probability home team wins (0.0-1.0)
        margin_uncertainty: Standard deviation of margin predictions
        features_used: Dict of key features used (will be JSON serialized)
        feature_count: Number of features in the model

    Returns:
        prediction_id: ID of the inserted/updated prediction
    """
    ensure_table_exists(engine)

    # Serialize features to JSON
    features_json = json.dumps(features_used) if features_used else None

    insert_sql = """
    INSERT INTO model_predictions (
        game_id, prediction_timestamp, game_date,
        model_type, model_version,
        home_team, away_team,
        predicted_winner, predicted_margin, home_win_probability, home_win_probability_raw, margin_uncertainty,
        features_used, feature_count
    ) VALUES (
        :game_id, :prediction_timestamp, :game_date,
        :model_type, :model_version,
        :home_team, :away_team,
        :predicted_winner, :predicted_margin, :home_win_probability, :home_win_probability_raw, :margin_uncertainty,
        :features_used, :feature_count
    )
    ON DUPLICATE KEY UPDATE
        prediction_timestamp = VALUES(prediction_timestamp),
        predicted_winner = VALUES(predicted_winner),
        predicted_margin = VALUES(predicted_margin),
        home_win_probability = VALUES(home_win_probability),
        home_win_probability_raw = VALUES(home_win_probability_raw),
        margin_uncertainty = VALUES(margin_uncertainty),
        features_used = VALUES(features_used),
        feature_count = VALUES(feature_count)
    """

    with engine.connect() as conn:
        result = conn.execute(text(insert_sql), {
            'game_id': game_id,
            'prediction_timestamp': datetime.now(),
            'game_date': game_date,
            'model_type': model_type,
            'model_version': model_version,
            'home_team': home_team,
            'away_team': away_team,
            'predicted_winner': predicted_winner,
            'predicted_margin': predicted_margin,
            'home_win_probability': home_win_probability,
            'home_win_probability_raw': home_win_probability_raw,
            'margin_uncertainty': margin_uncertainty,
            'features_used': features_json,
            'feature_count': feature_count
        })
        conn.commit()

        # Get the inserted ID
        pred_id = result.lastrowid

    return pred_id


# ============================================================================
# UPDATE ACTUAL RESULTS
# ============================================================================

def update_actual_result(
    engine,
    game_id: str,
    model_type: str,
    actual_winner: str,
    actual_margin: float
):
    """
    Update a prediction with actual game results.

    Args:
        engine: SQLAlchemy engine
        game_id: NBA API game ID
        model_type: 'rf' or 'nn'
        actual_winner: Team abbreviation of actual winner
        actual_margin: Actual point margin (positive = home won)
    """
    update_sql = """
    UPDATE model_predictions
    SET
        actual_winner = :actual_winner,
        actual_margin = :actual_margin,
        is_correct = (predicted_winner = :actual_winner),
        margin_error = ABS(predicted_margin - :actual_margin)
    WHERE game_id = :game_id AND model_type = :model_type
    """

    with engine.connect() as conn:
        result = conn.execute(text(update_sql), {
            'game_id': game_id,
            'model_type': model_type,
            'actual_winner': actual_winner,
            'actual_margin': actual_margin
        })
        conn.commit()

    return result.rowcount


# ============================================================================
# BACKFILL ACTUAL RESULTS
# ============================================================================

def backfill_actuals(engine, lookback_days: int = 30, verbose: bool = True) -> Dict[str, int]:
    """
    Scan for completed games and update predictions with actual results.

    Args:
        engine: SQLAlchemy engine
        lookback_days: How many days back to check (default 30)
        verbose: Print progress messages

    Returns:
        Dict with counts of updated predictions
    """
    ensure_table_exists(engine)

    # Get predictions that don't have actual results yet
    query = """
    SELECT DISTINCT p.game_id, p.game_date, p.home_team, p.away_team
    FROM model_predictions p
    WHERE p.actual_winner IS NULL
      AND p.game_date >= DATE_SUB(CURDATE(), INTERVAL :lookback_days DAY)
      AND p.game_date < CURDATE()
    ORDER BY p.game_date DESC
    """

    with engine.connect() as conn:
        pending = pd.read_sql(text(query), conn, params={'lookback_days': lookback_days})

    if len(pending) == 0:
        if verbose:
            print("No pending predictions to backfill")
        return {'updated': 0, 'not_found': 0, 'errors': 0}

    if verbose:
        print(f"Found {len(pending)} games with predictions pending actual results")

    updated_count = 0
    not_found_count = 0
    error_count = 0

    # For each game, look up actual results from game_list table
    for _, game in pending.iterrows():
        game_id = game['game_id']
        home_team = game['home_team']
        away_team = game['away_team']

        try:
            # Get actual results from game_list
            results_query = """
            SELECT
                TEAM_ABBREVIATION,
                WL,
                PTS
            FROM game_list
            WHERE GAME_ID = :game_id
            """

            with engine.connect() as conn:
                results = pd.read_sql(text(results_query), conn, params={'game_id': game_id})

            if len(results) == 0:
                not_found_count += 1
                if verbose:
                    print(f"  No results found for game {game_id}")
                continue

            # Find home and away team results
            home_result = results[results['TEAM_ABBREVIATION'] == home_team]
            away_result = results[results['TEAM_ABBREVIATION'] == away_team]

            if len(home_result) == 0 or len(away_result) == 0:
                not_found_count += 1
                if verbose:
                    print(f"  Incomplete results for game {game_id}")
                continue

            # WL=NULL means the game wasn't final when game_list captured it
            # (mid-game leaguegamefinder snapshot). Don't derive a bogus
            # actual_margin from those partial PTS — wait for the next pipeline
            # run to refresh the game_list row via _update_game_list_table.
            if (pd.isna(home_result['WL'].iloc[0]) or pd.isna(away_result['WL'].iloc[0])):
                not_found_count += 1
                if verbose:
                    print(f"  Game {game_id} not final (WL is NULL); skipping until game_list is refreshed")
                continue

            home_pts = home_result['PTS'].iloc[0]
            away_pts = away_result['PTS'].iloc[0]
            actual_margin = home_pts - away_pts
            actual_winner = home_team if actual_margin > 0 else away_team

            # Update both RF and NN predictions for this game
            for model_type in ['rf', 'nn']:
                rows_updated = update_actual_result(
                    engine, game_id, model_type, actual_winner, actual_margin
                )
                if rows_updated > 0:
                    updated_count += 1

            if verbose:
                print(f"  Updated game {game_id}: {away_team} @ {home_team}, Winner: {actual_winner}, Margin: {actual_margin:+.1f}")

        except Exception as e:
            error_count += 1
            if verbose:
                print(f"  Error processing game {game_id}: {e}")

    if verbose:
        print(f"\nBackfill complete: {updated_count} predictions updated, {not_found_count} games not found, {error_count} errors")

    return {
        'updated': updated_count,
        'not_found': not_found_count,
        'errors': error_count
    }


# ============================================================================
# QUERY PREDICTIONS
# ============================================================================

def get_predictions_for_date(engine, game_date: str, model_type: Optional[str] = None) -> pd.DataFrame:
    """
    Retrieve all predictions for a specific date.

    Args:
        engine: SQLAlchemy engine
        game_date: Date string (YYYY-MM-DD)
        model_type: Optional filter for 'rf' or 'nn' (None = both)

    Returns:
        DataFrame of predictions
    """
    query = """
    SELECT *
    FROM model_predictions
    WHERE game_date = :game_date
    """

    params = {'game_date': game_date}

    if model_type:
        query += " AND model_type = :model_type"
        params['model_type'] = model_type

    query += " ORDER BY prediction_timestamp DESC"

    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn, params=params)

    return df


def get_all_predictions_with_results(engine, model_type: Optional[str] = None,
                                     start_date: Optional[str] = None,
                                     end_date: Optional[str] = None) -> pd.DataFrame:
    """
    Get all predictions that have actual results (for accuracy analysis).

    Args:
        engine: SQLAlchemy engine
        model_type: Optional filter for 'rf' or 'nn'
        start_date: Optional start date filter (YYYY-MM-DD)
        end_date: Optional end date filter (YYYY-MM-DD)

    Returns:
        DataFrame of predictions with actual results
    """
    query = """
    SELECT *
    FROM model_predictions
    WHERE actual_winner IS NOT NULL
    """

    params = {}

    if model_type:
        query += " AND model_type = :model_type"
        params['model_type'] = model_type

    if start_date:
        query += " AND game_date >= :start_date"
        params['start_date'] = start_date

    if end_date:
        query += " AND game_date <= :end_date"
        params['end_date'] = end_date

    query += " ORDER BY game_date ASC, prediction_timestamp ASC"

    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn, params=params)

    return df


# ============================================================================
# ACCURACY METRICS
# ============================================================================

def get_prediction_accuracy(engine, model_type: Optional[str] = None,
                           lookback_days: Optional[int] = None) -> Dict:
    """
    Calculate accuracy metrics for predictions.

    Args:
        engine: SQLAlchemy engine
        model_type: Optional filter for 'rf' or 'nn' (None = both)
        lookback_days: Optional number of days to look back (None = all time)

    Returns:
        Dict with accuracy metrics
    """
    query = """
    SELECT
        model_type,
        COUNT(*) as total_predictions,
        SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) as correct_predictions,
        AVG(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) as accuracy,
        AVG(margin_error) as mean_absolute_error,
        STDDEV(margin_error) as std_margin_error,
        AVG(ABS(home_win_probability - (CASE WHEN actual_winner = home_team THEN 1 ELSE 0 END))) as calibration_error
    FROM model_predictions
    WHERE actual_winner IS NOT NULL
    """

    params = {}

    if model_type:
        query += " AND model_type = :model_type"
        params['model_type'] = model_type

    if lookback_days:
        query += " AND game_date >= DATE_SUB(CURDATE(), INTERVAL :lookback_days DAY)"
        params['lookback_days'] = lookback_days

    query += " GROUP BY model_type"

    with engine.connect() as conn:
        results = pd.read_sql(text(query), conn, params=params)

    if len(results) == 0:
        return {
            'total_predictions': 0,
            'accuracy': None,
            'mean_absolute_error': None,
            'calibration_error': None
        }

    # Convert to dict format
    metrics = {}
    for _, row in results.iterrows():
        metrics[row['model_type']] = {
            'total_predictions': int(row['total_predictions']),
            'correct_predictions': int(row['correct_predictions']),
            'accuracy': float(row['accuracy']) if row['accuracy'] is not None else None,
            'mean_absolute_error': float(row['mean_absolute_error']) if row['mean_absolute_error'] is not None else None,
            'std_margin_error': float(row['std_margin_error']) if row['std_margin_error'] is not None else None,
            'calibration_error': float(row['calibration_error']) if row['calibration_error'] is not None else None
        }

    return metrics


def get_accuracy_over_time(engine, model_type: str = 'rf', window_size: int = 10) -> pd.DataFrame:
    """
    Calculate rolling accuracy over time.

    Args:
        engine: SQLAlchemy engine
        model_type: 'rf' or 'nn'
        window_size: Number of games for rolling window

    Returns:
        DataFrame with date and rolling accuracy
    """
    df = get_all_predictions_with_results(engine, model_type=model_type)

    if len(df) == 0:
        return pd.DataFrame(columns=['game_date', 'rolling_accuracy', 'rolling_mae', 'count'])

    # Sort by game date
    df = df.sort_values('game_date')

    # Calculate rolling metrics
    df['is_correct_num'] = df['is_correct'].astype(int)
    df['rolling_accuracy'] = df['is_correct_num'].rolling(window=window_size, min_periods=1).mean()
    df['rolling_mae'] = df['margin_error'].rolling(window=window_size, min_periods=1).mean()
    df['count'] = range(1, len(df) + 1)

    return df[['game_date', 'rolling_accuracy', 'rolling_mae', 'count']]


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def get_model_version(feature_count: int) -> str:
    """Generate a model version string based on feature count and date."""
    date_str = datetime.now().strftime('%Y%m%d')
    return f'v1.0_{feature_count}features_{date_str}'


def print_accuracy_report(engine, lookback_days: Optional[int] = None):
    """Print a formatted accuracy report."""
    metrics = get_prediction_accuracy(engine, lookback_days=lookback_days)

    print("\n" + "=" * 80)
    print("PREDICTION ACCURACY REPORT")
    if lookback_days:
        print(f"Last {lookback_days} days")
    else:
        print("All time")
    print("=" * 80)

    if not metrics:
        print("No predictions with actual results found")
        return

    for model_type, stats in metrics.items():
        model_name = "Random Forest" if model_type == 'rf' else "Neural Network"
        print(f"\n{model_name} ({model_type}):")
        print(f"  Total predictions: {stats['total_predictions']}")
        print(f"  Correct predictions: {stats['correct_predictions']}")
        print(f"  Accuracy: {stats['accuracy']:.1%}" if stats['accuracy'] else "  Accuracy: N/A")
        print(f"  Mean Absolute Error: {stats['mean_absolute_error']:.2f} points" if stats['mean_absolute_error'] else "  MAE: N/A")
        print(f"  Std Margin Error: {stats['std_margin_error']:.2f} points" if stats['std_margin_error'] else "  Std: N/A")
        print(f"  Calibration Error: {stats['calibration_error']:.3f}" if stats['calibration_error'] else "  Calibration: N/A")

    print("=" * 80 + "\n")


# ============================================================================
# MAIN (for testing)
# ============================================================================

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='NBA Prediction Tracker')
    parser.add_argument('--create-table', action='store_true', help='Create the predictions table')
    parser.add_argument('--backfill', action='store_true', help='Backfill actual results')
    parser.add_argument('--report', action='store_true', help='Show accuracy report')
    parser.add_argument('--date', type=str, help='Show predictions for date (YYYY-MM-DD)')
    parser.add_argument('--lookback', type=int, default=30, help='Days to look back for backfill')
    args = parser.parse_args()

    engine = create_engine()

    if args.create_table:
        create_predictions_table(engine)

    if args.backfill:
        print(f"Backfilling actual results (last {args.lookback} days)...")
        results = backfill_actuals(engine, lookback_days=args.lookback)
        print(f"\nResults: {results}")

    if args.report:
        print_accuracy_report(engine)

    if args.date:
        predictions = get_predictions_for_date(engine, args.date)
        print(f"\nPredictions for {args.date}:")
        print(predictions.to_string(index=False))

    engine.dispose()
