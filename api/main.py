"""FastAPI app for the public NBA-predictions website.

Read-only. Serves predictions + accuracy from model_predictions (RDS in prod).
No model code, no torch, no inference — see api/__init__.py for the rationale.

Run locally (from project root):
    uvicorn api.main:app --reload --port 8000
    # then open http://127.0.0.1:8000/docs

Endpoints:
    GET /api/health                         liveness + DB connectivity
    GET /api/predictions/latest             predictions for the most recent date
    GET /api/predictions?date=YYYY-MM-DD    predictions for a specific date
    GET /api/accuracy/summary?days=30       aggregate accuracy per model
    GET /api/accuracy/rolling?days=90       per-day accuracy/MAE timeseries
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from api import queries
from api.db import db_healthy
from api.schemas import (
    PredictionsResponse,
    AccuracySummaryResponse,
    RollingResponse,
    HealthResponse,
)

app = FastAPI(
    title="NBA Predictions API",
    version="0.1.0",
    description="Public read-only API serving nightly NBA game predictions and "
                "historical accuracy. Data is produced by a batch job; this API "
                "only reads it.",
)

# CORS: the Next.js static site calls this API cross-origin. Allowed origins come
# from ALLOWED_ORIGINS (comma-separated) so prod domains are configured per-env.
# Defaults to localhost dev ports.
_origins = os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins if o.strip()],
    allow_methods=["GET"],
    allow_headers=["*"],
)

_VALID_MODELS = {"rf", "nn", "xgb"}


def _check_model(model: Optional[str]) -> Optional[str]:
    if model is not None and model not in _VALID_MODELS:
        raise HTTPException(status_code=400,
                            detail=f"unknown model '{model}'; valid: {sorted(_VALID_MODELS)}")
    return model


@app.get("/api/health", response_model=HealthResponse, tags=["meta"])
def health():
    ok = db_healthy()
    # Liveness is always 200 (the process is up); DB state is reported in body so
    # a load balancer can health-check the process while monitoring DB separately.
    return HealthResponse(status="ok", database="up" if ok else "down")


@app.get("/api/predictions/latest", response_model=PredictionsResponse, tags=["predictions"])
def predictions_latest(model: Optional[str] = Query(default=None)):
    """Predictions for the most recent game_date that has any."""
    _check_model(model)
    date_iso = queries.latest_prediction_date(model)
    if date_iso is None:
        return PredictionsResponse(game_date=None, count=0, predictions=[])
    rows = queries.predictions_for_date(date_iso, model)
    return PredictionsResponse(game_date=date_iso, count=len(rows), predictions=rows)


@app.get("/api/predictions", response_model=PredictionsResponse, tags=["predictions"])
def predictions_by_date(
    date: str = Query(..., description="Game date YYYY-MM-DD"),
    model: Optional[str] = Query(default=None),
):
    """Predictions for a specific date."""
    _check_model(model)
    rows = queries.predictions_for_date(date, model)
    return PredictionsResponse(game_date=date, count=len(rows), predictions=rows)


@app.get("/api/accuracy/summary", response_model=AccuracySummaryResponse, tags=["accuracy"])
def accuracy_summary(
    days: int = Query(default=30, ge=1, le=365),
    model: Optional[str] = Query(default=None),
):
    """Aggregate accuracy over the last N days of completed games, per model."""
    _check_model(model)
    rows = queries.accuracy_summary(days, model)
    return AccuracySummaryResponse(days=days, models=rows)


@app.get("/api/accuracy/rolling", response_model=RollingResponse, tags=["accuracy"])
def accuracy_rolling(
    days: int = Query(default=90, ge=1, le=365),
    model: Optional[str] = Query(default=None),
):
    """Per-day accuracy + MAE timeseries for the historical-accuracy chart."""
    _check_model(model)
    rows = queries.accuracy_rolling(days, model)
    return RollingResponse(days=days, points=rows)
