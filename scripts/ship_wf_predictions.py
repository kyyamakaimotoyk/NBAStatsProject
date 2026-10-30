"""Ship the local walk-forward (wf_) model_predictions rows to RDS via the S3 handoff.

P-2 (2026-10-30): after `walkforward_backfill.py --supersede-non-wf` rebuilds
2025-26 locally, RDS needs the same wf_ rows. The drop uses the loader's
``version_window`` mode on model_version: DELETE WHERE model_version LIKE 'wf_%',
then insert every local wf_ row. Idempotent, and live / retrospective rows never
match the prefix, so they stay in RDS for audit; the API's latest-timestamp
dedup serves the newer wf_ rows instead.

Local is the source of truth for wf_ rows (they are only ever produced here).
Compare the printed per-season counts against `scripts/check_track_record.py`
on RDS before shipping if in doubt.

The cloud side needs NO changes: the nightly batch's load stage (or a one-off
run of s3_ingest_loader.py) consumes the drop like any other.

Usage:
    python scripts/ship_wf_predictions.py --dry-run   # export + counts only
    python scripts/ship_wf_predictions.py             # export + upload
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.db import get_engine  # noqa: E402

DEFAULT_BUCKET = "nba-game-predictor-ingest-583686634997"
DEFAULT_PROFILE = "home-ingest"
VERSION_PREFIX = "wf_"


def log(msg: str) -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--bucket", default=DEFAULT_BUCKET)
    ap.add_argument("--profile", default=DEFAULT_PROFILE)
    ap.add_argument("--dry-run", action="store_true", help="Export locally, don't upload.")
    args = ap.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-wf-predictions"
    out_dir = Path(tempfile.mkdtemp(prefix="wf_ship_"))

    log("export: wf_ rows from local model_predictions")
    with get_engine().connect() as conn:
        df = pd.read_sql(sa.text(
            "SELECT * FROM model_predictions WHERE model_version LIKE 'wf!_%' ESCAPE '!'"),
            conn)
    if df.empty:
        log("ERROR: no wf_ rows locally - nothing to ship")
        return 1
    # RDS assigns its own ids; shipping local ids could collide with live rows.
    df = df.drop(columns=["prediction_id"], errors="ignore")

    gd = pd.to_datetime(df["game_date"])
    season = (gd.dt.year - (gd.dt.month < 8)).astype(str) + "-" + \
        ((gd.dt.year - (gd.dt.month < 8) + 1) % 100).astype(str).str.zfill(2)
    counts = df.assign(season=season).groupby(["season", "model_type"]).size().unstack(fill_value=0)
    log(f"export: {len(df)} rows; per season x model:\n{counts.to_string()}")

    df.to_parquet(out_dir / "model_predictions.parquet", index=False)
    manifest = {
        "schema_version": 1,
        "generated_at_utc": stamp,
        "note": "P-2 walk-forward track record (wf_ model_predictions rows)",
        "tables": {
            "model_predictions": {
                "rows": len(df),
                "mode": "version_window",
                "version_col": "model_version",
                "version_prefix": VERSION_PREFIX,
            },
        },
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    if args.dry_run:
        log(f"dry-run: skipping upload; files left in {out_dir}")
        return 0

    import boto3

    s3 = boto3.Session(profile_name=args.profile).client("s3")
    prefix = f"pending/{stamp}"
    s3.upload_file(str(out_dir / "model_predictions.parquet"), args.bucket,
                   f"{prefix}/model_predictions.parquet")
    log(f"upload: s3://{args.bucket}/{prefix}/model_predictions.parquet")
    # Manifest LAST - its presence marks the drop complete for the loader.
    s3.upload_file(str(out_dir / "manifest.json"), args.bucket, f"{prefix}/manifest.json")
    log(f"upload: s3://{args.bucket}/{prefix}/manifest.json (drop complete)")
    log("done - the nightly load stage will pick it up, or run the loader one-off now")
    return 0


if __name__ == "__main__":
    sys.exit(main())
