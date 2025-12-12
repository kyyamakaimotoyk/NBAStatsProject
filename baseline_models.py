"""
Baseline Models for NBA Game Prediction
========================================

This script builds baseline models using scikit-learn for:
1. Classification: Predict Win/Loss (TARGET_WIN)
2. Regression: Predict Point Margin (TARGET_MARGIN)

Learning objectives:
- Train/test splitting (temporal split for time series data)
- Handling missing values (imputation strategies)
- Feature scaling (StandardScaler, when to use it)
- Model training and evaluation
- Cross-validation
- Feature importance analysis
- Avoiding common pitfalls (data leakage in preprocessing)
"""

import pandas as pd
import numpy as np
import os
from datetime import datetime

# Scikit-learn imports
from sklearn.model_selection import train_test_split, TimeSeriesSplit, cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer

# Models
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor, GradientBoostingClassifier, GradientBoostingRegressor
from sklearn.dummy import DummyClassifier, DummyRegressor

# Metrics
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score, roc_auc_score,
    confusion_matrix, classification_report,
    mean_squared_error, mean_absolute_error, r2_score
)

import warnings
warnings.filterwarnings('ignore')

# ============================================================================
# DATA LOADING
# ============================================================================

def load_data(filepath: str = 'nba_ml_features.csv') -> pd.DataFrame:
    """Load the ML features dataset."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"{filepath} not found. Run feature_engineering.py first.")

    df = pd.read_csv(filepath)
    df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])

    print(f"Loaded {len(df)} games")
    print(f"Date range: {df['GAME_DATE'].min().date()} to {df['GAME_DATE'].max().date()}")
    print(f"Columns: {len(df.columns)}")

    return df


# ============================================================================
# DATA PREPARATION
# ============================================================================

def get_feature_columns(df: pd.DataFrame) -> list:
    """
    Get list of feature columns (exclude identifiers and targets).

    We only use rolling features (_L5, _L10) and derived features
    (STREAK, REST, WIN_PCT) to avoid data leakage.

    Also includes:
    - Fatigue features (IS_BACK_TO_BACK, GAMES_LAST, etc.)
    - Player projection features (PROJ_*, WEIGHTED_AVG_*, etc.)
    - Player slot features (SLOT_*_IMPACT, SLOT_*_AVAILABLE, etc.)
    """
    # Comprehensive feature patterns matching feature_engineering.py output
    feature_patterns = [
        # Rolling statistics
        '_L5', '_L10',
        # Basic derived features
        'STREAK', 'REST_DAYS', 'WIN_PCT',
        # Fatigue features
        'IS_BACK_TO_BACK', 'IS_3_IN_4_NIGHTS', 'GAMES_LAST',
        'AVG_REST_LAST', 'ROAD_TRIP_LENGTH',
        # Player projection features
        'PROJ_PTS_FROM_PLAYERS', 'PROJ_REB_FROM_PLAYERS', 'PROJ_AST_FROM_PLAYERS',
        'WEIGHTED_AVG_USAGE', 'WEIGHTED_AVG_TS_PCT', 'WEIGHTED_AVG_PIE',
        'ROSTER_DEPTH_SCORE', 'STAR_PLAYER_IMPACT', 'TOP_3_SCORER_SHARE',
        # Player slot features (integrated roster model)
        '_SLOT_', '_IMPACT', '_AVAILABLE',
        'TOTAL_AVAILABLE_IMPACT', 'TOTAL_MISSING_IMPACT', 'PLAYERS_OUT'
    ]

    feature_cols = [col for col in df.columns
                   if any(pattern in col for pattern in feature_patterns)]

    # Exclude any columns that might cause issues
    # PLAYER_ID columns are for lookup/embedding, not direct model features
    exclude_patterns = ['TEAM_ID', 'GAME_ID', 'TARGET', 'PLAYER_ID']
    feature_cols = [col for col in feature_cols
                   if not any(pattern in col for pattern in exclude_patterns)]

    return feature_cols


def temporal_train_test_split(df: pd.DataFrame,
                              test_size: float = 0.2) -> tuple:
    """
    Split data temporally - train on older games, test on newer games.

    WHY TEMPORAL SPLIT?
    -------------------
    In sports prediction, we can only use past data to predict future games.
    A random split would allow information from future games to "leak" into
    training data, giving unrealistically good results.

    Example: If a random split puts a Dec 2024 game in training and a
    Nov 2024 game in test, the model has seen the "future" during training.
    """
    # Sort by date
    df_sorted = df.sort_values('GAME_DATE').reset_index(drop=True)

    # Calculate split point
    split_idx = int(len(df_sorted) * (1 - test_size))

    train_df = df_sorted.iloc[:split_idx]
    test_df = df_sorted.iloc[split_idx:]

    print(f"\nTemporal Split:")
    print(f"  Train: {len(train_df)} games ({train_df['GAME_DATE'].min().date()} to {train_df['GAME_DATE'].max().date()})")
    print(f"  Test:  {len(test_df)} games ({test_df['GAME_DATE'].min().date()} to {test_df['GAME_DATE'].max().date()})")

    return train_df, test_df


def prepare_features(train_df: pd.DataFrame,
                     test_df: pd.DataFrame,
                     feature_cols: list) -> tuple:
    """
    Prepare features: handle missing values and scale.

    IMPORTANT: Fit preprocessing ONLY on training data!
    Otherwise you leak information from the test set.

    Returns: X_train, X_test, y_train_clf, y_test_clf, y_train_reg, y_test_reg, valid_feature_cols
    """
    # Extract features and targets
    X_train = train_df[feature_cols].copy()
    X_test = test_df[feature_cols].copy()

    y_train_clf = train_df['TARGET_WIN'].copy()
    y_test_clf = test_df['TARGET_WIN'].copy()

    y_train_reg = train_df['TARGET_MARGIN'].copy()
    y_test_reg = test_df['TARGET_MARGIN'].copy()

    # Remove columns that are all NaN in training data
    valid_cols = X_train.columns[X_train.notna().any()].tolist()
    dropped_cols = set(feature_cols) - set(valid_cols)
    if dropped_cols:
        print(f"\nDropped {len(dropped_cols)} columns with all NaN values")

    X_train = X_train[valid_cols]
    X_test = X_test[valid_cols]

    # Handle missing values
    # Strategy: Use median imputation (robust to outliers)
    print(f"\nMissing values in training features: {X_train.isnull().sum().sum()}")
    print(f"Missing values in test features: {X_test.isnull().sum().sum()}")

    imputer = SimpleImputer(strategy='median')
    X_train_imputed = pd.DataFrame(
        imputer.fit_transform(X_train),  # FIT on training only
        columns=valid_cols,
        index=X_train.index
    )
    X_test_imputed = pd.DataFrame(
        imputer.transform(X_test),  # TRANSFORM test (no fitting!)
        columns=valid_cols,
        index=X_test.index
    )

    # Scale features
    # For tree-based models (Random Forest), scaling isn't necessary
    # For linear models (Logistic Regression, Ridge), scaling helps
    scaler = StandardScaler()
    X_train_scaled = pd.DataFrame(
        scaler.fit_transform(X_train_imputed),  # FIT on training only
        columns=valid_cols,
        index=X_train.index
    )
    X_test_scaled = pd.DataFrame(
        scaler.transform(X_test_imputed),  # TRANSFORM test (no fitting!)
        columns=valid_cols,
        index=X_test.index
    )

    print(f"\nFeature preparation complete:")
    print(f"  X_train shape: {X_train_scaled.shape}")
    print(f"  X_test shape: {X_test_scaled.shape}")

    return (X_train_scaled, X_test_scaled,
            y_train_clf, y_test_clf,
            y_train_reg, y_test_reg,
            valid_cols)


# ============================================================================
# MODEL TRAINING - CLASSIFICATION
# ============================================================================

def train_classification_models(X_train, X_test, y_train, y_test) -> dict:
    """
    Train multiple classification models and compare performance.

    We start with a DUMMY classifier to establish a baseline.
    Any useful model should beat the dummy!
    """
    print("\n" + "="*60)
    print("CLASSIFICATION: Predicting Win/Loss")
    print("="*60)

    results = {}

    # Define models
    models = {
        'Dummy (Most Frequent)': DummyClassifier(strategy='most_frequent'),
        'Dummy (Stratified)': DummyClassifier(strategy='stratified'),
        'Logistic Regression': LogisticRegression(max_iter=1000, random_state=42),
        'Random Forest': RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42),
        'Gradient Boosting': GradientBoostingClassifier(n_estimators=100, max_depth=5, random_state=42)
    }

    print(f"\nTarget distribution:")
    print(f"  Train - Home wins: {y_train.mean()*100:.1f}%")
    print(f"  Test  - Home wins: {y_test.mean()*100:.1f}%")

    print("\n" + "-"*60)
    print(f"{'Model':<30} {'Accuracy':>10} {'Precision':>10} {'Recall':>10} {'F1':>10} {'AUC':>10}")
    print("-"*60)

    for name, model in models.items():
        # Train
        model.fit(X_train, y_train)

        # Predict
        y_pred = model.predict(X_test)
        y_prob = model.predict_proba(X_test)[:, 1] if hasattr(model, 'predict_proba') else y_pred

        # Metrics
        acc = accuracy_score(y_test, y_pred)
        prec = precision_score(y_test, y_pred, zero_division=0)
        rec = recall_score(y_test, y_pred, zero_division=0)
        f1 = f1_score(y_test, y_pred, zero_division=0)
        auc = roc_auc_score(y_test, y_prob)

        results[name] = {
            'model': model,
            'accuracy': acc,
            'precision': prec,
            'recall': rec,
            'f1': f1,
            'auc': auc,
            'predictions': y_pred
        }

        print(f"{name:<30} {acc:>10.3f} {prec:>10.3f} {rec:>10.3f} {f1:>10.3f} {auc:>10.3f}")

    # Best model
    best_model_name = max(results.keys(), key=lambda k: results[k]['auc'] if 'Dummy' not in k else 0)
    print(f"\nBest model: {best_model_name} (AUC: {results[best_model_name]['auc']:.3f})")

    # Detailed report for best model
    print(f"\nClassification Report for {best_model_name}:")
    print(classification_report(y_test, results[best_model_name]['predictions'],
                                target_names=['Away Win', 'Home Win']))

    return results


# ============================================================================
# MODEL TRAINING - REGRESSION
# ============================================================================

def train_regression_models(X_train, X_test, y_train, y_test) -> dict:
    """
    Train multiple regression models to predict point margin.

    METRICS EXPLAINED:
    - MAE (Mean Absolute Error): Average prediction error in points
    - RMSE (Root Mean Squared Error): Penalizes large errors more
    - R2: Proportion of variance explained (1.0 = perfect, 0 = mean baseline)
    """
    print("\n" + "="*60)
    print("REGRESSION: Predicting Point Margin")
    print("="*60)

    results = {}

    # Define models
    models = {
        'Dummy (Mean)': DummyRegressor(strategy='mean'),
        'Ridge Regression': Ridge(alpha=1.0, random_state=42),
        'Random Forest': RandomForestRegressor(n_estimators=100, max_depth=10, random_state=42),
        'Gradient Boosting': GradientBoostingRegressor(n_estimators=100, max_depth=5, random_state=42)
    }

    print(f"\nTarget statistics:")
    print(f"  Train - Mean margin: {y_train.mean():.1f}, Std: {y_train.std():.1f}")
    print(f"  Test  - Mean margin: {y_test.mean():.1f}, Std: {y_test.std():.1f}")

    print("\n" + "-"*60)
    print(f"{'Model':<30} {'MAE':>10} {'RMSE':>10} {'R2':>10}")
    print("-"*60)

    for name, model in models.items():
        # Train
        model.fit(X_train, y_train)

        # Predict
        y_pred = model.predict(X_test)

        # Metrics
        mae = mean_absolute_error(y_test, y_pred)
        rmse = np.sqrt(mean_squared_error(y_test, y_pred))
        r2 = r2_score(y_test, y_pred)

        results[name] = {
            'model': model,
            'mae': mae,
            'rmse': rmse,
            'r2': r2,
            'predictions': y_pred
        }

        print(f"{name:<30} {mae:>10.2f} {rmse:>10.2f} {r2:>10.3f}")

    # Best model
    best_model_name = max(results.keys(), key=lambda k: results[k]['r2'] if 'Dummy' not in k else -999)
    print(f"\nBest model: {best_model_name} (R2: {results[best_model_name]['r2']:.3f})")

    # Interpretation
    best_mae = results[best_model_name]['mae']
    print(f"\nInterpretation:")
    print(f"  On average, predictions are off by {best_mae:.1f} points")
    print(f"  For a predicted margin of +5, actual margin is typically between {5-best_mae:.1f} and {5+best_mae:.1f}")

    return results


# ============================================================================
# FEATURE IMPORTANCE
# ============================================================================

def analyze_feature_importance(model, feature_names: list, top_n: int = 20) -> pd.DataFrame:
    """
    Extract and display feature importance from tree-based models.
    """
    if hasattr(model, 'feature_importances_'):
        importance = model.feature_importances_
    elif hasattr(model, 'coef_'):
        importance = np.abs(model.coef_).flatten()
    else:
        print("Model doesn't have feature importance")
        return None

    # Create DataFrame
    importance_df = pd.DataFrame({
        'feature': feature_names,
        'importance': importance
    }).sort_values('importance', ascending=False)

    print(f"\nTop {top_n} Most Important Features:")
    print("-"*50)
    for i, row in importance_df.head(top_n).iterrows():
        print(f"  {row['feature']:<40} {row['importance']:.4f}")

    return importance_df


# ============================================================================
# CROSS-VALIDATION
# ============================================================================

def cross_validate_models(X, y, task: str = 'classification') -> dict:
    """
    Perform time-series cross-validation.

    TimeSeriesSplit ensures that:
    - Training data always comes BEFORE test data
    - No future information leaks into training

    This gives a more realistic estimate of model performance.
    """
    print(f"\n{'='*60}")
    print(f"CROSS-VALIDATION ({task.upper()})")
    print("="*60)

    # Use TimeSeriesSplit for temporal data
    tscv = TimeSeriesSplit(n_splits=5)

    if task == 'classification':
        models = {
            'Logistic Regression': LogisticRegression(max_iter=1000, random_state=42),
            'Random Forest': RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42),
        }
        scoring = 'roc_auc'
    else:
        models = {
            'Ridge Regression': Ridge(alpha=1.0, random_state=42),
            'Random Forest': RandomForestRegressor(n_estimators=100, max_depth=10, random_state=42),
        }
        scoring = 'neg_mean_absolute_error'

    results = {}

    print(f"\nUsing TimeSeriesSplit with 5 folds")
    print(f"Scoring metric: {scoring}")
    print("\n" + "-"*50)
    print(f"{'Model':<30} {'Mean Score':>12} {'Std':>10}")
    print("-"*50)

    for name, model in models.items():
        scores = cross_val_score(model, X, y, cv=tscv, scoring=scoring)

        # For MAE, sklearn returns negative values, so we negate
        if 'neg_' in scoring:
            scores = -scores

        results[name] = {
            'scores': scores,
            'mean': scores.mean(),
            'std': scores.std()
        }

        print(f"{name:<30} {scores.mean():>12.3f} {scores.std():>10.3f}")

    return results


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    print("\n" + "="*60)
    print("NBA GAME PREDICTION - BASELINE MODELS")
    print("="*60)

    # Load data
    df = load_data()

    # Get feature columns
    feature_cols = get_feature_columns(df)
    print(f"\nUsing {len(feature_cols)} features")

    # Temporal split
    train_df, test_df = temporal_train_test_split(df, test_size=0.2)

    # Prepare features
    (X_train, X_test,
     y_train_clf, y_test_clf,
     y_train_reg, y_test_reg,
     feature_cols) = prepare_features(train_df, test_df, feature_cols)

    # Train classification models
    clf_results = train_classification_models(X_train, X_test, y_train_clf, y_test_clf)

    # Train regression models
    reg_results = train_regression_models(X_train, X_test, y_train_reg, y_test_reg)

    # Feature importance (using best tree-based model)
    print("\n" + "="*60)
    print("FEATURE IMPORTANCE ANALYSIS")
    print("="*60)

    print("\nClassification (Random Forest):")
    clf_importance = analyze_feature_importance(
        clf_results['Random Forest']['model'],
        feature_cols
    )

    print("\nRegression (Random Forest):")
    reg_importance = analyze_feature_importance(
        reg_results['Random Forest']['model'],
        feature_cols
    )

    # Cross-validation
    # Combine train and test for CV (it will do its own splits)
    X_all = pd.concat([X_train, X_test])
    y_all_clf = pd.concat([y_train_clf, y_test_clf])
    y_all_reg = pd.concat([y_train_reg, y_test_reg])

    cv_clf_results = cross_validate_models(X_all, y_all_clf, 'classification')
    cv_reg_results = cross_validate_models(X_all, y_all_reg, 'regression')

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    print("\nClassification (Win/Loss):")
    best_clf = max(clf_results.keys(), key=lambda k: clf_results[k]['auc'] if 'Dummy' not in k else 0)
    print(f"  Best model: {best_clf}")
    print(f"  Test AUC: {clf_results[best_clf]['auc']:.3f}")
    print(f"  Test Accuracy: {clf_results[best_clf]['accuracy']:.3f}")

    print("\nRegression (Point Margin):")
    best_reg = max(reg_results.keys(), key=lambda k: reg_results[k]['r2'] if 'Dummy' not in k else -999)
    print(f"  Best model: {best_reg}")
    print(f"  Test MAE: {reg_results[best_reg]['mae']:.2f} points")
    print(f"  Test R2: {reg_results[best_reg]['r2']:.3f}")

    print("\nKey Insights:")
    print("  1. Home team wins ~60% of games (baseline to beat)")
    print("  2. Average margin is ~3 points for home team")
    print(f"  3. Our best model predicts within {reg_results[best_reg]['mae']:.1f} points on average")

    print("\nNext Steps:")
    print("  1. Try more features or feature selection")
    print("  2. Hyperparameter tuning (GridSearchCV)")
    print("  3. Build neural network with PyTorch")

    return clf_results, reg_results


if __name__ == '__main__':
    clf_results, reg_results = main()
