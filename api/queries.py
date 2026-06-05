"""SQL read functions for the public API.

Plain SQLAlchemy Core (no pandas) so the API image carries no numpy/pandas.
Every function returns built-in types (lists of dicts, dicts) ready to serialize.

PUBLIC-SAFE COLUMN POLICY
-------------------------
The website is public, so we never expose model internals. These columns are
deliberately NOT selected:
  * features_used      — JSON snapshot of feature values (model internals)
  * feature_count      — model internals
  * model_version      — internal naming scheme / training provenance
  * home_win_probability_raw — pre-calibration A/B value (internal diagnostic)
Only fan-facing fields (teams, pick, probability, margin, actual result) ship.
"""
from __future__ import annotations

from typing import Optional
import sqlalchemy as sa

from api.db import get_engine

# Columns safe to return for a prediction row.
_PUBLIC_PREDICTION_COLS = """
    game_id,
    game_date,
    model_type,
    home_team,
    away_team,
    predicted_winner,
    predicted_margin,
    home_win_probability,
    margin_uncertainty,
    actual_winner,
    actual_margin,
    is_correct
"""


def _rows(result) -> list[dict]:
    return [dict(r) for r in result.mappings().all()]


def latest_prediction_date(model_type: Optional[str] = None) -> Optional[str]:
    """Most recent game_date that has any prediction rows. None if table empty."""
    q = "SELECT MAX(game_date) AS d FROM model_predictions"
    params: dict = {}
    if model_type:
        q += " WHERE model_type = :mt"
        params['mt'] = model_type
    with get_engine().connect() as conn:
        d = conn.execute(sa.text(q), params).scalar()
    return d.isoformat() if d is not None else None


def predictions_for_date(game_date: str, model_type: Optional[str] = None) -> list[dict]:
    """Predictions for a date — ONE row per (game, model): the most recent.

    The table can hold several model_versions for the same game (e.g. a retrain
    re-logged a backfill date). A public "today's games" view must show each
    matchup once per model, so we keep only the latest prediction_timestamp per
    (game_id, model_type) via a window function.
    """
    q = f"""
    SELECT {_PUBLIC_PREDICTION_COLS}
    FROM (
        SELECT *,
               ROW_NUMBER() OVER (
                   PARTITION BY game_id, model_type
                   ORDER BY prediction_timestamp DESC
               ) AS _rn
        FROM model_predictions
        WHERE game_date = :d
    ) ranked
    WHERE _rn = 1
    """
    params: dict = {'d': game_date}
    if model_type:
        q += " AND model_type = :mt"
        params['mt'] = model_type
    q += " ORDER BY game_id, model_type"
    with get_engine().connect() as conn:
        return _rows(conn.execute(sa.text(q), params))


def accuracy_summary(days: int = 30, model_type: Optional[str] = None) -> list[dict]:
    """Aggregate accuracy over the last ``days`` of completed games, per model.

    Mirrors modeling/prediction_tracker.get_prediction_accuracy so the public
    numbers match the internal dashboard. Only games with actual_winner set
    (i.e. already played and backfilled) count.
    """
    q = """
    SELECT
        model_type,
        COUNT(*)                                            AS total_predictions,
        SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END)     AS correct_predictions,
        AVG(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END)     AS accuracy,
        AVG(margin_error)                                   AS mae,
        SQRT(AVG(margin_error * margin_error))              AS rmse,
        AVG(ABS(home_win_probability
            - (CASE WHEN actual_winner = home_team THEN 1 ELSE 0 END))) AS calibration_error
    FROM model_predictions
    WHERE actual_winner IS NOT NULL
      AND game_date >= DATE_SUB(CURDATE(), INTERVAL :days DAY)
    """
    params: dict = {'days': days}
    if model_type:
        q += " AND model_type = :mt"
        params['mt'] = model_type
    q += " GROUP BY model_type ORDER BY model_type"
    with get_engine().connect() as conn:
        return _rows(conn.execute(sa.text(q), params))


def accuracy_rolling(days: int = 90, model_type: Optional[str] = None) -> list[dict]:
    """Per-day accuracy + MAE timeseries for the historical-accuracy chart.

    One row per (game_date, model_type) with that day's hit rate and mean margin
    error. The frontend can plot these directly or compute a rolling average.
    """
    q = """
    SELECT
        game_date,
        model_type,
        COUNT(*)                                        AS n_games,
        AVG(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) AS accuracy,
        AVG(margin_error)                               AS mae
    FROM model_predictions
    WHERE actual_winner IS NOT NULL
      AND game_date >= DATE_SUB(CURDATE(), INTERVAL :days DAY)
    """
    params: dict = {'days': days}
    if model_type:
        q += " AND model_type = :mt"
        params['mt'] = model_type
    q += " GROUP BY game_date, model_type ORDER BY game_date ASC, model_type"
    with get_engine().connect() as conn:
        return _rows(conn.execute(sa.text(q), params))
