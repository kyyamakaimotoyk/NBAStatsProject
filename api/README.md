# Public API (`api/`)

Read-only FastAPI service that powers the public website. It is the **serve**
half of the batch/serve split: the nightly batch job
(`modeling/batch_predict_today.py`) computes predictions and writes them to the
`model_predictions` table; this API only reads that table and returns JSON.

**It never loads a model, imports torch/sklearn, or runs inference.** That keeps
its dependency surface (`api/requirements.txt`) and Docker image small.

## Run locally

```bash
# from the project root, with the same .env the rest of the project uses
pip install -r api/requirements.txt
uvicorn api.main:app --reload --port 8000
# interactive docs: http://127.0.0.1:8000/docs
```

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Liveness + DB connectivity |
| GET | `/api/predictions/latest` | Predictions for the most recent date that has any |
| GET | `/api/predictions?date=YYYY-MM-DD` | Predictions for a specific date |
| GET | `/api/accuracy/summary?days=30` | Aggregate accuracy per model over a window |
| GET | `/api/accuracy/rolling?days=90` | Per-day accuracy + MAE timeseries (for the chart) |

All endpoints accept an optional `?model=rf|nn|xgb` filter.

## What is intentionally NOT exposed

Public-safe columns only. These are never returned (model internals):
`features_used`, `feature_count`, `model_version`, `home_win_probability_raw`.
The `model_registry` table (hyperparameters, training metrics) is **not** read by
this API at all — that stays in the internal dashboard.

## Configuration (env vars)

- `NBA_DB_*` — same MySQL/RDS connection vars as the rest of the project
- `ALLOWED_ORIGINS` — comma-separated CORS allow-list (default: localhost:3000).
  Set to the website's domain(s) in production.

## Notes

- Uses the pure-Python `pymysql` driver (`mysql+pymysql://`) so the image needs
  no C build tools, unlike the `mysqlclient` driver used by `core/db.py`.
- Connection pool has `pool_pre_ping` enabled to survive RDS idle-timeout drops.
