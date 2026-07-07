"""One-off: ship a features version from the local DB to RDS via the S3 handoff.

Built to publish the frozen 3-season walk-forward feature build (E21,
version 20260703T072718Z) so the public Explore page can chart rolling
features beyond the current season. The drop uses the loader's existing
``version_window`` mode: DELETE WHERE feature_set_version LIKE '<version>%',
then insert - idempotent, and it can never touch any other version or the
feature_set_current pointer.

The cloud side needs NO changes: the nightly batch's load stage (or a one-off
run of s3_ingest_loader.py) consumes the drop like any other.

Usage:
    python scripts/ship_features_version.py --dry-run   # export only
    python scripts/ship_features_version.py             # export + upload
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

DEFAULT_VERSION = "20260703T072718Z"
DEFAULT_BUCKET = "nba-game-predictor-ingest-583686634997"
DEFAULT_PROFILE = "home-ingest"


def log(msg: str) -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--version", default=DEFAULT_VERSION)
    ap.add_argument("--bucket", default=DEFAULT_BUCKET)
    ap.add_argument("--profile", default=DEFAULT_PROFILE)
    ap.add_argument("--dry-run", action="store_true", help="Export locally, don't upload.")
    args = ap.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-features"
    out_dir = Path(tempfile.mkdtemp(prefix="features_ship_"))

    log(f"export: features version {args.version} from local DB")
    eng = get_engine()
    with eng.connect() as conn:
        df = pd.read_sql(
            sa.text("SELECT * FROM features WHERE feature_set_version = :v"),
            conn, params={"v": args.version},
        )
    if df.empty:
        log(f"ERROR: no rows for version {args.version} - nothing to ship")
        return 1
    df.to_parquet(out_dir / "features.parquet", index=False)
    size_mb = (out_dir / "features.parquet").stat().st_size / 1e6
    log(f"export: {len(df)} rows x {len(df.columns)} cols -> features.parquet ({size_mb:.1f} MB)")

    manifest = {
        "schema_version": 1,
        "generated_at_utc": stamp,
        "note": f"one-off features version ship ({args.version})",
        "tables": {
            "features": {
                "rows": len(df),
                "mode": "version_window",
                "version_col": "feature_set_version",
                "version_prefix": args.version,
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
    s3.upload_file(str(out_dir / "features.parquet"), args.bucket, f"{prefix}/features.parquet")
    log(f"upload: s3://{args.bucket}/{prefix}/features.parquet")
    # Manifest LAST - its presence marks the drop complete for the loader.
    s3.upload_file(str(out_dir / "manifest.json"), args.bucket, f"{prefix}/manifest.json")
    log(f"upload: s3://{args.bucket}/{prefix}/manifest.json (drop complete)")
    log("done - the nightly load stage will pick it up, or run the loader one-off now")
    return 0


if __name__ == "__main__":
    sys.exit(main())
