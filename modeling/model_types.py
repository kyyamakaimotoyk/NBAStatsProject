"""
Central registry of model types for the NBA prediction system.

This is the single source of truth used by:
  - orchestration/pipeline.py        — PredictStage `--model` CLI choices
  - modeling/predict_games.py        — main() prediction loop, save/load dispatch
  - visualization/dataExploration.py — Game Predictions tab loading, chart traces,
                                        comparison table columns, info cards

To add a new model type (e.g. xgboost, lightgbm, ensemble):
  1) Append a ModelTypeSpec entry to MODEL_TYPES below.
  2) In modeling/predict_games.py, write `load_or_train_<key>_models(engine, force_retrain=False)`
     that returns a tuple compatible with the unpack pattern used by `bundle_to_loader_tuple`.
     The cleanest path is to write a `save_<key>_bundle`/`load_<key>_bundle` pair that uses
     `save_model_bundle`/`load_model_bundle` (so rollback fidelity comes for free).
  3) Write `predict_with_<key>(...)` returning a dict with at least the keys
     {'win_prob', 'margin_mean', 'margin_std', 'margin_samples', 'shap_feature_importance'}.
  4) Register both in modeling.predict_games.MODEL_LOADERS / MODEL_PREDICT_FNS.

No edits required to pipeline.py or dataExploration.py — they iterate MODEL_TYPES.
"""

from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import List, Dict, Any


@dataclass(frozen=True)
class ModelTypeSpec:
    """Describes one trainable model 'type'.

    Each type owns a (classifier, regressor) pair of model_registry rows that share a
    feature scaler and feature_names list (and a target_scaler for NN-family models).
    The bundle file for one training run holds the entire pair atomically, so both
    `classifier_registry_type` and `regressor_registry_type` point at the same file_path.
    """
    key: str                          # CLI / dashboard key: 'rf', 'nn', 'nn-embed', ...
    display_name: str                 # Human-readable name for UI surfaces
    classifier_registry_type: str     # model_registry.model_type for the classifier row
    regressor_registry_type: str      # model_registry.model_type for the regressor row
    color: str                        # Hex color used in dashboard charts
    description: str = ''             # One-line description shown in info cards
    framework: str = ''               # 'sklearn' | 'pytorch' | ... — informational only


# The active set of model types. Order matters: the dashboard renders cards/columns/charts
# in this order, and the comparison table assigns the first two as the "primary pair" for
# the AGREE/DISAGREE badge (since 2-way agreement is well-defined; with 3+ models we use
# a majority badge instead).
MODEL_TYPES: List[ModelTypeSpec] = [
    ModelTypeSpec(
        key='rf',
        display_name='Random Forest',
        classifier_registry_type='rf_classifier',
        regressor_registry_type='rf_regressor',
        color='#3498db',  # blue
        description='Ensemble of 100 decision trees; uncertainty from tree agreement',
        framework='sklearn',
    ),
    ModelTypeSpec(
        key='nn',
        display_name='Neural Network',
        classifier_registry_type='nn_classifier',
        regressor_registry_type='nn_regressor',
        color='#e74c3c',  # red
        description='3-layer MLP (128->64->32) with MC Dropout for uncertainty',
        framework='pytorch',
    ),
    ModelTypeSpec(
        key='nn-embed',
        display_name='NN with Embeddings',
        classifier_registry_type='nn_embed_classifier',
        regressor_registry_type='nn_embed_regressor',
        color='#9b59b6',  # purple
        description='MLP with learned player embeddings; encodes player synergies',
        framework='pytorch',
    ),
    ModelTypeSpec(
        key='xgb',
        display_name='XGBoost',
        classifier_registry_type='xgb_classifier',
        regressor_registry_type='xgb_regressor',
        color='#f39c12',  # amber
        description='Gradient-boosted trees with depth control; strong tabular baseline',
        framework='xgboost',
    ),
]


# ============================================================================
# CONVENIENCE LOOKUPS
# ============================================================================

def get_spec(key: str) -> ModelTypeSpec:
    """Look up a spec by key; raise if not found."""
    for spec in MODEL_TYPES:
        if spec.key == key:
            return spec
    raise KeyError(f"Unknown model type {key!r}. Registered keys: {[s.key for s in MODEL_TYPES]}")


def model_keys() -> List[str]:
    """All registered keys, in display order."""
    return [s.key for s in MODEL_TYPES]


def cli_choices() -> List[str]:
    """argparse `choices=` for --model flags: every key plus 'both' for backward-compat."""
    return model_keys() + ['both']


def color_map() -> Dict[str, str]:
    """{key: color} dict for charts. Falls back to gray for unknown keys."""
    return {s.key: s.color for s in MODEL_TYPES}


def display_map() -> Dict[str, str]:
    """{key: display_name} dict for UI labels."""
    return {s.key: s.display_name for s in MODEL_TYPES}


def specs_as_dicts() -> List[Dict[str, Any]]:
    """Serializable form for the dashboard (Dash callbacks can't capture dataclasses cleanly)."""
    return [asdict(s) for s in MODEL_TYPES]


def expand_cli_model_arg(value: str) -> List[str]:
    """Resolve a --model CLI value into a list of concrete keys.

    'both' is preserved for backward-compat and expands to every registered key.
    """
    if value == 'both':
        return model_keys()
    if value in model_keys():
        return [value]
    raise ValueError(f"Unknown --model value {value!r}. Valid: {cli_choices()}")
