-- ============================================================================
-- NBA Prediction Tracking System - Database Schema
-- ============================================================================
--
-- This script creates the model_predictions table for tracking NBA game
-- predictions and their actual outcomes.
--
-- Usage:
--   mysql -u kaiyamamoto -p nba_data < create_predictions_table.sql
--
-- Or from Python:
--   python prediction_tracker.py --create-table
-- ============================================================================

CREATE TABLE IF NOT EXISTS model_predictions (
    -- Primary Key
    prediction_id INT AUTO_INCREMENT PRIMARY KEY,

    -- Game Identification
    game_id VARCHAR(50) NOT NULL COMMENT 'NBA API game ID (e.g., 0022400123)',
    prediction_timestamp DATETIME NOT NULL COMMENT 'When prediction was made',
    game_date DATE NOT NULL COMMENT 'Date of the game',

    -- Model Information
    model_type VARCHAR(20) NOT NULL COMMENT 'rf (Random Forest) or nn (Neural Network)',
    model_version VARCHAR(100) NOT NULL COMMENT 'Version identifier (e.g., v1.0_480features_20241206)',

    -- Teams
    home_team VARCHAR(50) NOT NULL COMMENT 'Home team abbreviation (e.g., LAL)',
    away_team VARCHAR(50) NOT NULL COMMENT 'Away team abbreviation (e.g., BOS)',

    -- Predictions
    predicted_winner VARCHAR(50) NOT NULL COMMENT 'Predicted winning team abbreviation',
    predicted_margin FLOAT NOT NULL COMMENT 'Predicted point margin (positive = home team wins)',
    home_win_probability FLOAT NOT NULL COMMENT 'Probability home team wins (0.0 to 1.0)',
    margin_uncertainty FLOAT NULL COMMENT 'Standard deviation of margin predictions',

    -- Feature Information
    features_used TEXT NULL COMMENT 'JSON snapshot of key features used in prediction',
    feature_count INT NOT NULL COMMENT 'Number of features in the model (e.g., 480)',

    -- Actual Results (NULL until game completes)
    actual_winner VARCHAR(50) NULL COMMENT 'Actual winning team (filled after game)',
    actual_margin FLOAT NULL COMMENT 'Actual point margin (positive = home team won)',
    is_correct BOOLEAN NULL COMMENT 'Was the predicted winner correct? (TRUE/FALSE)',
    margin_error FLOAT NULL COMMENT 'Absolute prediction error: |predicted_margin - actual_margin|',

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'When record was created',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'When record was last updated',

    -- Indexes for Query Performance
    INDEX idx_game_date (game_date),
    INDEX idx_game_id (game_id),
    INDEX idx_model_type (model_type),
    INDEX idx_model_version (model_version),
    INDEX idx_prediction_timestamp (prediction_timestamp),

    -- Unique Constraint
    -- Ensures one prediction per game per model type per version
    UNIQUE KEY unique_prediction (game_id, model_type, model_version)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Stores NBA game predictions and actual outcomes for accuracy tracking';

-- ============================================================================
-- Example Queries
-- ============================================================================

-- View recent predictions
-- SELECT
--     game_date, home_team, away_team, model_type,
--     predicted_winner, predicted_margin, home_win_probability,
--     actual_winner, is_correct, margin_error
-- FROM model_predictions
-- ORDER BY prediction_timestamp DESC
-- LIMIT 10;

-- Overall accuracy by model type
-- SELECT
--     model_type,
--     COUNT(*) as total_predictions,
--     SUM(is_correct) as correct_predictions,
--     AVG(is_correct) as accuracy,
--     AVG(margin_error) as mean_absolute_error
-- FROM model_predictions
-- WHERE actual_winner IS NOT NULL
-- GROUP BY model_type;

-- Predictions awaiting results
-- SELECT
--     game_date, home_team, away_team,
--     predicted_winner, home_win_probability
-- FROM model_predictions
-- WHERE actual_winner IS NULL
-- ORDER BY game_date ASC;

-- Best predictions (smallest error)
-- SELECT
--     game_date, home_team, away_team, model_type,
--     predicted_margin, actual_margin, margin_error
-- FROM model_predictions
-- WHERE actual_winner IS NOT NULL
-- ORDER BY margin_error ASC
-- LIMIT 10;

-- Worst predictions (largest error)
-- SELECT
--     game_date, home_team, away_team, model_type,
--     predicted_margin, actual_margin, margin_error
-- FROM model_predictions
-- WHERE actual_winner IS NOT NULL
-- ORDER BY margin_error DESC
-- LIMIT 10;

-- Accuracy by confidence level
-- SELECT
--     CASE
--         WHEN home_win_probability >= 0.8 THEN 'Very Confident (80%+)'
--         WHEN home_win_probability >= 0.65 THEN 'Confident (65-80%)'
--         WHEN home_win_probability >= 0.55 THEN 'Slight Edge (55-65%)'
--         ELSE 'Toss-up (50-55%)'
--     END as confidence_level,
--     COUNT(*) as num_predictions,
--     AVG(is_correct) as accuracy,
--     AVG(margin_error) as avg_error
-- FROM model_predictions
-- WHERE actual_winner IS NOT NULL
-- GROUP BY confidence_level
-- ORDER BY accuracy DESC;

-- Performance trend (last 30 days)
-- SELECT
--     DATE(game_date) as date,
--     model_type,
--     COUNT(*) as games,
--     AVG(is_correct) as accuracy,
--     AVG(margin_error) as mae
-- FROM model_predictions
-- WHERE actual_winner IS NOT NULL
--   AND game_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
-- GROUP BY DATE(game_date), model_type
-- ORDER BY date DESC;
