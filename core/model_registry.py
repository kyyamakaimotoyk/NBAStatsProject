"""
NBA Model Registry
==================

Tracks model versions, performance metrics, and enables comparison between models.
Supports date-based versioning and automatic retraining when features change.

Functions:
- ensure_registry_table() - Create model_registry table if needed
- register_model() - Save model metadata and performance metrics
- get_current_model() - Get the currently active model for a type
- compare_models() - Compare performance between two model versions
- should_retrain() - Check if retraining is needed (feature count changed)
"""

# Project-root bootstrap so this module can be run/imported regardless of CWD or package depth.
import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

import os
import json
import joblib
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any
import sqlalchemy as sql
from sqlalchemy import text
import pandas as pd
import numpy as np


# ============================================================================
# DATABASE TABLE CREATION
# ============================================================================

def ensure_registry_table(engine):
    """Create the model_registry table if it doesn't exist, and add any newer columns
    that may be missing from a pre-existing table.

    Columns added incrementally (training window, hyperparameters, train-set metrics,
    notes) are layered on via ALTER TABLE so old installs upgrade in place. Each ALTER
    is wrapped in its own try/except — MySQL errors on a duplicate ADD COLUMN, and we
    want each column to be independent so a partial upgrade can still finish.
    """
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS model_registry (
        registry_id INT AUTO_INCREMENT PRIMARY KEY,

        -- Model identification
        model_type VARCHAR(50) NOT NULL COMMENT 'rf_classifier, rf_regressor, nn_classifier, nn_regressor',
        model_version VARCHAR(100) NOT NULL COMMENT 'e.g., rf_classifier_20251213',

        -- Training metadata
        training_date DATE NOT NULL,
        feature_count INT NOT NULL,
        training_samples INT NOT NULL,
        test_samples INT NOT NULL,

        -- Classification metrics (NULL for regressors)
        test_accuracy FLOAT NULL,
        test_auc FLOAT NULL,
        test_precision FLOAT NULL,
        test_recall FLOAT NULL,
        test_f1 FLOAT NULL,

        -- Regression metrics (NULL for classifiers)
        test_mae FLOAT NULL,
        test_rmse FLOAT NULL,
        test_r2 FLOAT NULL,

        -- Model status
        is_current BOOLEAN DEFAULT FALSE COMMENT 'Is this the active model?',
        file_path VARCHAR(255) NOT NULL,

        -- Feature information
        feature_names JSON NULL COMMENT 'List of feature names used',

        -- Training-data window (added 2026-05)
        train_start_date DATE NULL COMMENT 'First game_date in the training set',
        train_end_date DATE NULL COMMENT 'Last game_date in the training set',
        test_start_date DATE NULL COMMENT 'First game_date in the held-out test set',
        test_end_date DATE NULL COMMENT 'Last game_date in the held-out test set',

        -- Training configuration & train-set metrics (added 2026-05)
        hyperparameters JSON NULL COMMENT 'Model-specific hyperparams (n_estimators, lr, dropout, etc.)',
        train_metrics JSON NULL COMMENT 'Metrics on the training set itself, for overfit gap detection',
        notes TEXT NULL COMMENT 'Free-form notes: what changed this run, why retrained, etc.',
        run_kind VARCHAR(20) NULL COMMENT 'train | validation | backfill — distinguishes registry-write origin',

        -- Timestamps
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        -- Indexes
        INDEX idx_model_type (model_type),
        INDEX idx_is_current (is_current),
        INDEX idx_training_date (training_date),
        UNIQUE KEY unique_version (model_type, model_version)
    )
    """

    # Each upgrade is its own statement so a duplicate-column error doesn't kill the others.
    upgrades = [
        "ALTER TABLE model_registry ADD COLUMN train_start_date DATE NULL",
        "ALTER TABLE model_registry ADD COLUMN train_end_date DATE NULL",
        "ALTER TABLE model_registry ADD COLUMN test_start_date DATE NULL",
        "ALTER TABLE model_registry ADD COLUMN test_end_date DATE NULL",
        "ALTER TABLE model_registry ADD COLUMN hyperparameters JSON NULL",
        "ALTER TABLE model_registry ADD COLUMN train_metrics JSON NULL",
        "ALTER TABLE model_registry ADD COLUMN notes TEXT NULL",
        "ALTER TABLE model_registry ADD COLUMN run_kind VARCHAR(20) NULL",
    ]

    with engine.connect() as conn:
        conn.execute(text(create_table_sql))
        conn.commit()
        for stmt in upgrades:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                # column already exists — that's fine
                conn.rollback()


# ============================================================================
# MODEL REGISTRATION
# ============================================================================

def register_model(
    engine,
    model_type: str,
    feature_count: int,
    training_samples: int,
    test_samples: int,
    file_path: str,
    feature_names: List[str],
    # Classification metrics (test set)
    accuracy: float = None,
    auc: float = None,
    precision: float = None,
    recall: float = None,
    f1: float = None,
    # Regression metrics (test set)
    mae: float = None,
    rmse: float = None,
    r2: float = None,
    set_as_current: bool = True,
    # Training-window metadata (added 2026-05)
    train_start_date=None,
    train_end_date=None,
    test_start_date=None,
    test_end_date=None,
    # Training configuration & extra info (added 2026-05)
    hyperparameters: Optional[Dict[str, Any]] = None,
    train_metrics: Optional[Dict[str, Any]] = None,
    notes: Optional[str] = None,
    run_kind: str = 'train',
    version_override: Optional[str] = None,
) -> str:
    """
    Register a new model version in the database.

    Args:
        engine: SQLAlchemy database engine
        model_type: One of 'rf_classifier', 'rf_regressor', 'nn_classifier', 'nn_regressor'
        feature_count: Number of features used
        training_samples: Number of training samples
        test_samples: Number of test samples
        file_path: Path to saved model file
        feature_names: List of feature column names
        accuracy, auc, precision, recall, f1: Classification metrics
        mae, rmse, r2: Regression metrics
        set_as_current: Whether to set this as the current active model

    Returns:
        model_version string (e.g., 'rf_classifier_20251213')
    """
    ensure_registry_table(engine)

    today = datetime.now()
    if version_override:
        model_version = version_override
    else:
        model_version = f"{model_type}_{today.strftime('%Y%m%d')}"

        # Check if version already exists today - add suffix if needed
        with engine.connect() as conn:
            existing = conn.execute(text(
                "SELECT COUNT(*) as cnt FROM model_registry WHERE model_version LIKE :prefix"
            ), {'prefix': f"{model_version}%"}).fetchone()

            if existing and existing[0] > 0:
                model_version = f"{model_version}_{existing[0] + 1}"

    # If setting as current, unset previous current model
    if set_as_current:
        with engine.connect() as conn:
            conn.execute(text(
                "UPDATE model_registry SET is_current = FALSE WHERE model_type = :model_type"
            ), {'model_type': model_type})
            conn.commit()

    # Insert new model record
    insert_sql = """
    INSERT INTO model_registry (
        model_type, model_version, training_date, feature_count,
        training_samples, test_samples,
        test_accuracy, test_auc, test_precision, test_recall, test_f1,
        test_mae, test_rmse, test_r2,
        is_current, file_path, feature_names,
        train_start_date, train_end_date, test_start_date, test_end_date,
        hyperparameters, train_metrics, notes, run_kind
    ) VALUES (
        :model_type, :model_version, :training_date, :feature_count,
        :training_samples, :test_samples,
        :accuracy, :auc, :precision, :recall, :f1,
        :mae, :rmse, :r2,
        :is_current, :file_path, :feature_names,
        :train_start_date, :train_end_date, :test_start_date, :test_end_date,
        :hyperparameters, :train_metrics, :notes, :run_kind
    )
    """

    with engine.connect() as conn:
        conn.execute(text(insert_sql), {
            'model_type': model_type,
            'model_version': model_version,
            'training_date': today.date(),
            'feature_count': feature_count,
            'training_samples': training_samples,
            'test_samples': test_samples,
            'accuracy': accuracy,
            'auc': auc,
            'precision': precision,
            'recall': recall,
            'f1': f1,
            'mae': mae,
            'rmse': rmse,
            'r2': r2,
            'is_current': set_as_current,
            'file_path': file_path,
            'feature_names': json.dumps(feature_names[:100]),  # Truncate for storage
            'train_start_date': train_start_date,
            'train_end_date': train_end_date,
            'test_start_date': test_start_date,
            'test_end_date': test_end_date,
            'hyperparameters': json.dumps(hyperparameters) if hyperparameters is not None else None,
            'train_metrics': json.dumps(train_metrics) if train_metrics is not None else None,
            'notes': notes,
            'run_kind': run_kind,
        })
        conn.commit()

    return model_version


# ============================================================================
# MODEL QUERIES
# ============================================================================

def get_current_model(engine, model_type: str) -> Optional[Dict]:
    """Get the currently active model for a given type."""
    ensure_registry_table(engine)

    query = """
    SELECT * FROM model_registry
    WHERE model_type = :model_type AND is_current = TRUE
    ORDER BY training_date DESC LIMIT 1
    """

    with engine.connect() as conn:
        result = conn.execute(text(query), {'model_type': model_type}).fetchone()

    if result is None:
        return None

    return dict(result._mapping)


def get_model_history(engine, model_type: str, limit: int = 10) -> pd.DataFrame:
    """Get historical model versions for a given type."""
    ensure_registry_table(engine)

    query = """
    SELECT model_version, training_date, feature_count,
           test_accuracy, test_auc, test_mae, test_r2, is_current
    FROM model_registry
    WHERE model_type = :model_type
    ORDER BY training_date DESC
    LIMIT :limit
    """

    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn, params={'model_type': model_type, 'limit': limit})

    return df


# ============================================================================
# MODEL COMPARISON
# ============================================================================

def compare_models(
    engine,
    model_type: str,
    new_metrics: Dict[str, float],
    feature_count: int
) -> Tuple[bool, str]:
    """
    Compare new model metrics against the current model.

    Args:
        engine: SQLAlchemy database engine
        model_type: Model type to compare
        new_metrics: Dict with metrics (accuracy/auc for classifiers, mae/r2 for regressors)
        feature_count: Feature count for the new model

    Returns:
        Tuple of (is_better: bool, comparison_report: str)
    """
    current = get_current_model(engine, model_type)

    is_classifier = 'classifier' in model_type

    report_lines = []
    report_lines.append(f"\n{'='*60}")
    report_lines.append(f"MODEL COMPARISON: {model_type.upper()}")
    report_lines.append(f"{'='*60}")

    if current is None:
        report_lines.append("No previous model found. New model will be set as current.")
        return True, '\n'.join(report_lines)

    report_lines.append(f"\n{'Metric':<25} {'Previous':>12} {'New':>12} {'Change':>12}")
    report_lines.append("-" * 60)

    # Feature count comparison
    old_features = current.get('feature_count', 0)
    report_lines.append(f"{'Feature Count':<25} {old_features:>12} {feature_count:>12} {feature_count - old_features:>+12}")

    is_better = False

    if is_classifier:
        # Compare classification metrics
        old_acc = current.get('test_accuracy') or 0
        old_auc = current.get('test_auc') or 0
        new_acc = new_metrics.get('accuracy', 0)
        new_auc = new_metrics.get('auc', 0)

        acc_change = new_acc - old_acc
        auc_change = new_auc - old_auc

        report_lines.append(f"{'Accuracy':<25} {old_acc:>12.4f} {new_acc:>12.4f} {acc_change:>+12.4f}")
        report_lines.append(f"{'AUC':<25} {old_auc:>12.4f} {new_auc:>12.4f} {auc_change:>+12.4f}")

        # Better if AUC improved (primary metric)
        is_better = new_auc >= old_auc

        if is_better:
            report_lines.append(f"\n[IMPROVED] New model has equal or better AUC")
        else:
            report_lines.append(f"\n[REGRESSION] New model has worse AUC (-{-auc_change:.4f})")
    else:
        # Compare regression metrics
        old_mae = current.get('test_mae') or float('inf')
        old_r2 = current.get('test_r2') or 0
        new_mae = new_metrics.get('mae', float('inf'))
        new_r2 = new_metrics.get('r2', 0)

        mae_change = new_mae - old_mae
        r2_change = new_r2 - old_r2

        report_lines.append(f"{'MAE':<25} {old_mae:>12.4f} {new_mae:>12.4f} {mae_change:>+12.4f}")
        report_lines.append(f"{'R2':<25} {old_r2:>12.4f} {new_r2:>12.4f} {r2_change:>+12.4f}")

        # Better if MAE decreased (primary metric for regression)
        is_better = new_mae <= old_mae

        if is_better:
            report_lines.append(f"\n[IMPROVED] New model has equal or better MAE")
        else:
            report_lines.append(f"\n[REGRESSION] New model has worse MAE (+{mae_change:.4f} points)")

    report_lines.append("=" * 60)

    return is_better, '\n'.join(report_lines)


# ============================================================================
# RETRAINING LOGIC
# ============================================================================

def should_retrain(engine, model_type: str, current_feature_count: int) -> Tuple[bool, str]:
    """
    Check if model should be retrained based on feature count change.

    Returns:
        Tuple of (should_retrain: bool, reason: str)
    """
    current = get_current_model(engine, model_type)

    if current is None:
        return True, "No existing model found"

    saved_feature_count = current.get('feature_count', 0)

    if current_feature_count != saved_feature_count:
        return True, f"Feature count changed: {saved_feature_count} -> {current_feature_count}"

    return False, "Feature count unchanged"


def get_versioned_model_path(model_type: str, extension: str = 'joblib') -> str:
    """Generate a versioned file path for a model."""
    today = datetime.now().strftime('%Y%m%d')
    return f"models/{model_type}_{today}.{extension}"


# ============================================================================
# MODEL FILE MANAGEMENT
# ============================================================================

def save_model_with_version(
    model,
    model_type: str,
    feature_names: List[str],
    extension: str = 'joblib'
) -> str:
    """
    Save model to versioned file path.

    Args:
        model: The model object to save
        model_type: Type of model (rf_classifier, nn_classifier, etc.)
        feature_names: List of feature names
        extension: File extension (joblib for sklearn, pt for pytorch)

    Returns:
        Path where model was saved
    """
    os.makedirs('models', exist_ok=True)

    file_path = get_versioned_model_path(model_type, extension)

    # Handle duplicate versions on same day
    base_path = file_path
    counter = 1
    while os.path.exists(file_path):
        name, ext = os.path.splitext(base_path)
        file_path = f"{name}_{counter}{ext}"
        counter += 1

    if extension == 'joblib':
        joblib.dump(model, file_path)
    elif extension == 'pt':
        import torch
        torch.save(model.state_dict(), file_path)

    return file_path


def print_model_registry(engine, model_types: List[str] = None):
    """Print current model registry status."""
    if model_types is None:
        model_types = ['rf_classifier', 'rf_regressor', 'nn_classifier', 'nn_regressor']

    print("\n" + "=" * 70)
    print("MODEL REGISTRY STATUS")
    print("=" * 70)

    for model_type in model_types:
        current = get_current_model(engine, model_type)

        print(f"\n{model_type.upper()}")
        print("-" * 40)

        if current:
            print(f"  Version:    {current['model_version']}")
            print(f"  Trained:    {current['training_date']}")
            print(f"  Features:   {current['feature_count']}")

            if 'classifier' in model_type:
                print(f"  Accuracy:   {current.get('test_accuracy', 'N/A')}")
                print(f"  AUC:        {current.get('test_auc', 'N/A')}")
            else:
                print(f"  MAE:        {current.get('test_mae', 'N/A')}")
                print(f"  R2:         {current.get('test_r2', 'N/A')}")
        else:
            print("  No model registered")

    print("\n" + "=" * 70)


if __name__ == '__main__':
    # Test the registry
    from modeling.prediction_tracker import create_engine
    engine = create_engine()
    ensure_registry_table(engine)
    print_model_registry(engine)
