"""
Held-out validation runner.

Re-runs the currently-saved RF and NN models against a slice of nba_ml_features.csv
(default: last 60 days of available data) and reports MAE / accuracy / AUC /
calibration. Optionally writes results into model_registry so the dashboard's
training-metrics view can show training-claim vs recent-window numbers side by side.

Usage:
    python validate_models.py                              # last 60 days, both models, register
    python validate_models.py --days 30                    # last 30 days
    python validate_models.py --start 2025-12-01 --end 2026-01-15
    python validate_models.py --model rf                   # rf only
    python validate_models.py --no-register                # don't write to model_registry

Validation rows in model_registry use model_version like
`rf_classifier_validation_YYYYMMDD_<startdate>_<enddate>` and is_current=False so
they never displace the production model.
"""

# Project-root bootstrap so cross-folder imports (core.*, modeling.*) work regardless of CWD.
import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

# PyTorch must be imported before numpy/pandas on Windows (see README troubleshooting)
try:
    import torch
    import torch.nn as nn  # noqa: F401  (used indirectly via predict_games NN classes)
    PYTORCH_AVAILABLE = True
except (ImportError, OSError) as _e:
    PYTORCH_AVAILABLE = False
    print(f"PyTorch not available ({type(_e).__name__}); will skip NN validation.")

import os
import argparse
from datetime import datetime, timedelta, date
import json

import numpy as np
import pandas as pd
import joblib
from sqlalchemy import text
from sklearn.metrics import accuracy_score, roc_auc_score, mean_absolute_error, r2_score, mean_squared_error

from core.db import get_engine


# ============================================================================
# DATA PREPARATION
# ============================================================================

def load_features_and_window(features_path, start_date, end_date):
    """Load nba_ml_features.csv and slice to [start_date, end_date]."""
    df = pd.read_csv(features_path)
    df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])
    mask = (df['GAME_DATE'] >= pd.Timestamp(start_date)) & (df['GAME_DATE'] <= pd.Timestamp(end_date))
    sub = df.loc[mask].copy()
    return sub


def prepare_X_y(df, feature_names, scaler_tuple):
    """Apply the saved imputer + scaler to produce X, return X plus targets."""
    imputer, scaler = scaler_tuple
    missing_cols = [c for c in feature_names if c not in df.columns]
    if missing_cols:
        raise RuntimeError(
            f"{len(missing_cols)} feature columns expected by saved model are missing from features CSV. "
            f"First few: {missing_cols[:5]}. Regenerate features with feature_engineering.py."
        )
    X_raw = df[feature_names].values
    X_imputed = imputer.transform(X_raw)
    X_scaled = scaler.transform(X_imputed)

    y_clf = df['TARGET_WIN'].astype(int).values
    y_reg = df['TARGET_MARGIN'].astype(float).values
    return X_scaled, y_clf, y_reg


# ============================================================================
# MODEL VALIDATION - RANDOM FOREST
# ============================================================================

def validate_rf(df, models_dir='models'):
    clf_path = os.path.join(models_dir, 'rf_classifier.joblib')
    reg_path = os.path.join(models_dir, 'rf_regressor.joblib')
    scaler_path = os.path.join(models_dir, 'scaler.joblib')
    features_path = os.path.join(models_dir, 'feature_names.joblib')
    for p in (clf_path, reg_path, scaler_path, features_path):
        if not os.path.exists(p):
            raise FileNotFoundError(f"Missing model artifact: {p}")

    clf = joblib.load(clf_path)
    reg = joblib.load(reg_path)
    scaler_tuple = joblib.load(scaler_path)
    feature_names = joblib.load(features_path)

    X, y_clf, y_reg = prepare_X_y(df, feature_names, scaler_tuple)

    clf_prob = clf.predict_proba(X)[:, 1]
    clf_pred = (clf_prob >= 0.5).astype(int)
    reg_pred = reg.predict(X)

    return _summarize_predictions('rf', clf_pred, clf_prob, reg_pred, y_clf, y_reg, len(feature_names))


# ============================================================================
# MODEL VALIDATION - NEURAL NETWORK
# ============================================================================

def validate_nn(df, models_dir='models'):
    if not PYTORCH_AVAILABLE:
        raise RuntimeError("PyTorch not available; cannot validate NN.")

    # Imported lazily so non-torch installs can still validate RF.
    from modeling.predict_games import NBAClassifier, NBARegressor

    clf_path = os.path.join(models_dir, 'nn_classifier.pt')
    reg_path = os.path.join(models_dir, 'nn_regressor.pt')
    scaler_path = os.path.join(models_dir, 'scaler.joblib')
    features_path = os.path.join(models_dir, 'feature_names.joblib')
    config_path = os.path.join(models_dir, 'nn_config.joblib')
    for p in (clf_path, reg_path, scaler_path, features_path, config_path):
        if not os.path.exists(p):
            raise FileNotFoundError(f"Missing model artifact: {p}")

    scaler_tuple = joblib.load(scaler_path)
    feature_names = joblib.load(features_path)
    config = joblib.load(config_path)
    target_scaler = config.get('target_scaler')

    X, y_clf, y_reg = prepare_X_y(df, feature_names, scaler_tuple)

    clf = NBAClassifier(config['input_dim'])
    clf.load_state_dict(torch.load(clf_path, weights_only=True))
    clf.eval()

    reg = NBARegressor(config['input_dim'])
    reg.load_state_dict(torch.load(reg_path, weights_only=True))
    reg.eval()

    with torch.no_grad():
        X_t = torch.FloatTensor(X)
        clf_logits = clf(X_t).numpy().flatten()
        clf_prob = 1.0 / (1.0 + np.exp(-clf_logits))
        clf_pred = (clf_prob >= 0.5).astype(int)
        reg_scaled = reg(X_t).numpy().flatten()

    if target_scaler is not None:
        reg_pred = target_scaler.inverse_transform(reg_scaled.reshape(-1, 1)).flatten()
    else:
        reg_pred = reg_scaled

    return _summarize_predictions('nn', clf_pred, clf_prob, reg_pred, y_clf, y_reg, len(feature_names))


# ============================================================================
# METRICS
# ============================================================================

def _summarize_predictions(model_tag, clf_pred, clf_prob, reg_pred, y_clf, y_reg, feature_count):
    """Compute classifier + regressor metrics for one model."""
    n = len(y_clf)
    if n == 0:
        return {'model_tag': model_tag, 'n': 0}
    # Need >= 2 classes in y_clf to compute AUC
    if len(np.unique(y_clf)) >= 2:
        auc = float(roc_auc_score(y_clf, clf_prob))
    else:
        auc = None
    return {
        'model_tag': model_tag,
        'n': int(n),
        'feature_count': int(feature_count),
        'accuracy': float(accuracy_score(y_clf, clf_pred)),
        'auc': auc,
        'mae': float(mean_absolute_error(y_reg, reg_pred)),
        'rmse': float(np.sqrt(mean_squared_error(y_reg, reg_pred))),
        'r2': float(r2_score(y_reg, reg_pred)),
        'calibration_error': float(np.mean(np.abs(clf_prob - y_clf))),
    }


# ============================================================================
# REGISTRY WRITE
# ============================================================================

def write_validation_rows(engine, summary, start_date, end_date, models_dir='models'):
    """Write validation rows via model_registry.register_model().

    Each summary produces two rows (classifier + regressor) with run_kind='validation' and
    is_current=False so the production model is never displaced. Stores the validation
    window in test_start_date/test_end_date so the dashboard can show side-by-side
    "training-claim vs recent-window" performance for the same model artifact.
    """
    from core.model_registry import register_model

    today_tag = datetime.now().strftime('%Y%m%d_%H%M%S')
    classifier_type = f"{summary['model_tag']}_classifier"
    regressor_type = f"{summary['model_tag']}_regressor"
    rows_written = []
    notes = f"Held-out validation of saved model on {start_date}..{end_date} ({summary['n']} games)"

    clf_version = f"{classifier_type}_validation_{today_tag}_{start_date}_{end_date}"
    register_model(
        engine, classifier_type,
        feature_count=summary['feature_count'],
        training_samples=0, test_samples=summary['n'],
        file_path=os.path.join(models_dir, f"{summary['model_tag']}_classifier"),
        feature_names=[],
        accuracy=summary['accuracy'], auc=summary['auc'],
        set_as_current=False,
        test_start_date=start_date, test_end_date=end_date,
        notes=notes, run_kind='validation',
        version_override=clf_version,
    )
    rows_written.append(clf_version)

    reg_version = f"{regressor_type}_validation_{today_tag}_{start_date}_{end_date}"
    register_model(
        engine, regressor_type,
        feature_count=summary['feature_count'],
        training_samples=0, test_samples=summary['n'],
        file_path=os.path.join(models_dir, f"{summary['model_tag']}_regressor"),
        feature_names=[],
        mae=summary['mae'], rmse=summary['rmse'], r2=summary['r2'],
        set_as_current=False,
        test_start_date=start_date, test_end_date=end_date,
        notes=notes, run_kind='validation',
        version_override=reg_version,
    )
    rows_written.append(reg_version)

    return rows_written


# ============================================================================
# CLI
# ============================================================================

def parse_args():
    p = argparse.ArgumentParser(description='Held-out validation of saved RF/NN models.')
    p.add_argument('--features', default='nba_ml_features.csv',
                   help='Path to feature CSV (default: nba_ml_features.csv)')
    p.add_argument('--start', dest='start_date', default=None,
                   help='Window start (YYYY-MM-DD). Defaults to --days back from --end.')
    p.add_argument('--end', dest='end_date', default=None,
                   help='Window end (YYYY-MM-DD). Defaults to max date in features CSV.')
    p.add_argument('--days', type=int, default=60,
                   help='If --start not given, use this many days back from --end (default 60).')
    p.add_argument('--model', choices=['rf', 'nn', 'both'], default='both',
                   help='Which model(s) to validate.')
    p.add_argument('--no-register', action='store_true',
                   help='Skip writing validation rows to model_registry.')
    p.add_argument('--models-dir', default='models',
                   help='Directory containing saved model artifacts.')
    return p.parse_args()


def main():
    args = parse_args()

    # Resolve date window
    df_full = pd.read_csv(args.features, usecols=['GAME_DATE'])
    df_full['GAME_DATE'] = pd.to_datetime(df_full['GAME_DATE'])
    csv_max_date = df_full['GAME_DATE'].max().date()

    if args.end_date:
        end_date = pd.to_datetime(args.end_date).date()
    else:
        end_date = csv_max_date

    if args.start_date:
        start_date = pd.to_datetime(args.start_date).date()
    else:
        start_date = end_date - timedelta(days=args.days)

    print(f"\n{'='*70}")
    print(f"HELD-OUT MODEL VALIDATION")
    print(f"{'='*70}")
    print(f"Window: {start_date} to {end_date}")
    print(f"Features CSV max date: {csv_max_date}")
    print(f"Models: {args.model}")

    df_window = load_features_and_window(args.features, start_date, end_date)
    print(f"Games in window: {len(df_window)}")

    if len(df_window) == 0:
        print("\nNo games in window. Nothing to validate.")
        return

    summaries = []

    if args.model in ('rf', 'both'):
        print("\n--- Validating Random Forest ---")
        try:
            rf_summary = validate_rf(df_window, models_dir=args.models_dir)
            summaries.append(rf_summary)
            _print_summary(rf_summary)
        except Exception as e:
            print(f"  RF validation failed: {type(e).__name__}: {e}")

    if args.model in ('nn', 'both'):
        if not PYTORCH_AVAILABLE:
            print("\n--- Skipping NN validation (PyTorch unavailable) ---")
        else:
            print("\n--- Validating Neural Network ---")
            try:
                nn_summary = validate_nn(df_window, models_dir=args.models_dir)
                summaries.append(nn_summary)
                _print_summary(nn_summary)
            except Exception as e:
                print(f"  NN validation failed: {type(e).__name__}: {e}")

    if not args.no_register and summaries:
        print("\n--- Writing validation rows to model_registry ---")
        engine = get_engine()
        try:
            for s in summaries:
                versions = write_validation_rows(engine, s, start_date.isoformat(), end_date.isoformat(),
                                                  models_dir=args.models_dir)
                for v in versions:
                    print(f"  + {v}")
        finally:
            engine.dispose()
        print("Dashboard's Model Performance tab will show these in the registry table on next refresh.")
    elif args.no_register:
        print("\nSkipping registry write (--no-register).")


def _print_summary(s):
    if s.get('n', 0) == 0:
        print(f"  {s['model_tag']}: empty window")
        return
    auc_str = f"{s['auc']:.4f}" if s.get('auc') is not None else 'N/A'
    print(f"  {s['model_tag'].upper()}: n={s['n']}, "
          f"accuracy={s['accuracy']*100:.1f}%, AUC={auc_str}, "
          f"MAE={s['mae']:.2f} pts, RMSE={s['rmse']:.2f}, R2={s['r2']:.3f}, "
          f"calibration_error={s['calibration_error']:.3f}")


if __name__ == '__main__':
    main()
