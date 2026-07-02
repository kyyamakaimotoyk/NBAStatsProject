"""Pydantic response models — the public API contract.

These types are the documented shape of every response. FastAPI uses them to
validate output, generate the OpenAPI schema, and render the /docs page. Keeping
them explicit (rather than returning raw dicts) means the frontend has a stable
contract and breaking changes are visible in code review.
"""
from __future__ import annotations

from datetime import date
from typing import Optional
from pydantic import BaseModel


class Prediction(BaseModel):
    game_id: str
    game_date: date
    model_type: str
    home_team: str
    away_team: str
    predicted_winner: str
    predicted_margin: float
    home_win_probability: float
    margin_uncertainty: Optional[float] = None
    # Present only for games already played + backfilled:
    actual_winner: Optional[str] = None
    actual_margin: Optional[float] = None
    is_correct: Optional[bool] = None
    # The betting market's closing-line implied home margin — a public benchmark,
    # not model output. Populated by /api/performance/results; null elsewhere.
    market_margin: Optional[float] = None


class PredictionsResponse(BaseModel):
    game_date: Optional[str]
    count: int
    predictions: list[Prediction]


class PerformanceResultsResponse(BaseModel):
    """Predicted-vs-actual rows over a date window. The public Model Performance page
    computes all its charts client-side from these (reuses the Prediction shape)."""
    days: int
    count: int
    results: list[Prediction]


class FeatureTimeseriesRow(BaseModel):
    game_date: date
    home_team: Optional[str] = None
    away_team: Optional[str] = None
    home_value: Optional[float] = None
    away_value: Optional[float] = None


class FeatureTimeseriesResponse(BaseModel):
    """Rolling-feature time series for the data-exploration page (one row per game;
    the browser builds per-team series from the home/away values)."""
    feature: str
    window: str
    days: int
    count: int
    rows: list[FeatureTimeseriesRow]


class ScatterPoint(BaseModel):
    game_date: date
    team: Optional[str] = None
    wl: Optional[str] = None
    x: Optional[float] = None
    y: Optional[float] = None
    home_team: Optional[str] = None  # abbreviations, derived from MATCHUP
    away_team: Optional[str] = None
    winner: Optional[str] = None


class ScatterResponse(BaseModel):
    """Per-team-game points for the scatter explorer (browser colors by W/L,
    filters by team, and fits the trendline)."""
    x: str
    y: str
    days: int
    count: int
    points: list[ScatterPoint]


class MarginCorrItem(BaseModel):
    feature: str
    column: str
    correlation: float


class MarginCorrResponse(BaseModel):
    """Curated rolling features ranked by |correlation| with winning margin."""
    kind: str
    window: str
    count: int
    correlations: list[MarginCorrItem]


class AccuracySummary(BaseModel):
    model_type: str
    total_predictions: int
    correct_predictions: int
    accuracy: Optional[float] = None
    mae: Optional[float] = None
    rmse: Optional[float] = None
    calibration_error: Optional[float] = None


class AccuracySummaryResponse(BaseModel):
    days: int
    models: list[AccuracySummary]


class RollingPoint(BaseModel):
    game_date: date
    model_type: str
    n_games: int
    accuracy: Optional[float] = None
    mae: Optional[float] = None


class RollingResponse(BaseModel):
    days: int
    points: list[RollingPoint]


class HealthResponse(BaseModel):
    status: str
    database: str
