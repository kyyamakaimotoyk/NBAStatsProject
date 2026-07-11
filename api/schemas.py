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
    # Final score from game_list (null until the game is final).
    home_score: Optional[int] = None
    away_score: Optional[int] = None


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


class InjuryItem(BaseModel):
    team_name: str
    player_name: str
    status: str
    reason: Optional[str] = None


class InjuryReportResponse(BaseModel):
    """Pre-game injury report for one date (NBA-published, public info)."""
    game_date: date
    count: int
    injuries: list[InjuryItem]


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


# --- Player explore -----------------------------------------------------------


class PlayerDirEntry(BaseModel):
    person_id: int
    player_name: Optional[str] = None
    team_id: Optional[int] = None
    team_abbrev: Optional[str] = None


class PlayerDirectoryResponse(BaseModel):
    count: int
    players: list[PlayerDirEntry]


class PlayerGameRow(BaseModel):
    """One played game: actual counting stats + the model's out-of-sample
    prediction where one exists (pred_* are null for games the projection
    model did not cover)."""
    game_date: date
    opp: Optional[str] = None
    is_home: int
    min: Optional[float] = None
    pts: Optional[float] = None
    reb: Optional[float] = None
    ast: Optional[float] = None
    stl: Optional[float] = None
    blk: Optional[float] = None
    tov: Optional[float] = None
    fg3m: Optional[float] = None
    fg3a: Optional[float] = None
    ftm: Optional[float] = None
    fta: Optional[float] = None
    pred_min: Optional[float] = None
    pred_pts: Optional[float] = None
    pred_reb: Optional[float] = None
    pred_ast: Optional[float] = None
    pred_stl: Optional[float] = None
    pred_blk: Optional[float] = None
    pred_tov: Optional[float] = None
    pred_fg3m: Optional[float] = None
    pred_fg3a: Optional[float] = None
    pred_ftm: Optional[float] = None
    pred_fta: Optional[float] = None


class PlayerGamelogResponse(BaseModel):
    person_id: int
    player_name: Optional[str] = None
    count: int
    rows: list[PlayerGameRow]


class TeamProfile(BaseModel):
    """Rolling last-10-games team profile (public aggregates only)."""
    team_id: int
    team_abbrev: Optional[str] = None
    pace: Optional[float] = None
    off_rtg: Optional[float] = None
    def_rtg: Optional[float] = None
    oreb_pct: Optional[float] = None
    dreb_pct: Optional[float] = None
    efg_pct: Optional[float] = None
    ast_pct: Optional[float] = None
    fg3a_pg: Optional[float] = None
    fta_pg: Optional[float] = None
    pts_pg: Optional[float] = None


class NextGameInfo(BaseModel):
    game_date: str
    is_home: bool
    opp_team_id: int
    opp_abbrev: Optional[str] = None


class TeamContextResponse(BaseModel):
    team: TeamProfile
    next_game: Optional[NextGameInfo] = None  # null in the offseason
    opponent: Optional[TeamProfile] = None


class PlayerDailyRow(BaseModel):
    """One player's projection for one game on the daily /players table,
    with own/opponent L10 context (as of the prediction date) and actuals
    once the game is graded."""
    game_date: date
    person_id: int
    player_name: Optional[str] = None
    team_abbrev: Optional[str] = None
    opp_abbrev: Optional[str] = None
    is_home: int
    team_pace_l10: Optional[float] = None
    opp_pace_l10: Optional[float] = None
    opp_drtg_l10: Optional[float] = None
    opp_3pa_allowed_l10: Optional[float] = None
    pred_min: Optional[float] = None
    pred_pts: Optional[float] = None
    pred_reb: Optional[float] = None
    pred_ast: Optional[float] = None
    pred_stl: Optional[float] = None
    pred_blk: Optional[float] = None
    pred_tov: Optional[float] = None
    pred_fg3m: Optional[float] = None
    pred_fg3a: Optional[float] = None
    pred_ftm: Optional[float] = None
    pred_fta: Optional[float] = None
    actual_min: Optional[float] = None
    actual_pts: Optional[float] = None
    actual_reb: Optional[float] = None
    actual_ast: Optional[float] = None
    actual_stl: Optional[float] = None
    actual_blk: Optional[float] = None
    actual_tov: Optional[float] = None
    actual_fg3m: Optional[float] = None
    actual_fg3a: Optional[float] = None
    actual_ftm: Optional[float] = None
    actual_fta: Optional[float] = None


class PlayerDailyResponse(BaseModel):
    game_date: Optional[str]
    count: int
    rows: list[PlayerDailyRow]
