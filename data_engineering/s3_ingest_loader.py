"""Cloud-side half of the residential-ingest handoff: load S3 drops into MySQL.

The home box (home_ingest_push.py) fetches NBA data on a residential IP — the
only kind stats.nba.com still answers — and uploads parquet drops to
s3://<ingest bucket>/pending/<stamp>/, manifest.json last. This module runs in
the nightly Fargate task (called from batch_predict_today before predicting):

    for each pending/<stamp>/ that HAS a manifest (no manifest = still uploading):
        for each table, by the manifest's declared mode:
            game_window - delete the drop's game_ids, then insert  (boxscores)
            date_window - delete rows >= the drop's cutoff, insert (game_list)
            replace     - delete all rows, insert                  (schedule, teams)
        on success: move the drop to processed/<stamp>/ (kept ~30d by lifecycle)
        on failure: leave it in pending/ — next night retries; every step is an
                    upsert-by-delete so replays are harmless.

Standalone use:
    python data_engineering/s3_ingest_loader.py [--bucket ...] [--dry-run]
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_BUCKET_ENV = "INGEST_S3_BUCKET"


def _log(msg: str) -> None:
    print(f"[s3_ingest] {msg}", flush=True)


def _table_exists(conn, name: str) -> bool:
    q = sa.text(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = DATABASE() AND table_name = :t"
    )
    return bool(conn.execute(q, {"t": name}).scalar())


def _load_table(engine, table: str, df: pd.DataFrame, meta: dict) -> None:
    """Upsert one table from one drop, transactionally (delete window + insert)."""
    mode = meta.get("mode", "game_window")
    with engine.begin() as conn:
        exists = _table_exists(conn, table)
        if exists:
            if mode == "game_window":
                gid_col = meta["gid_col"]
                gids = sorted({int(g) for g in pd.to_numeric(df[gid_col]).tolist()})
                if gids:
                    id_list = ",".join(str(g) for g in gids)
                    conn.execute(sa.text(
                        f"DELETE FROM `{table}` "
                        f"WHERE CAST(`{gid_col}` AS UNSIGNED) IN ({id_list})"))
            elif mode == "date_window":
                conn.execute(sa.text(
                    f"DELETE FROM `{table}` WHERE `{meta['date_col']}` >= :c"),
                    {"c": meta["cutoff"]})
            elif mode == "version_window":
                # Walk-forward research rows (Phase B/C): replace only rows whose
                # version matches the prefix (e.g. model_version LIKE 'wf_%').
                # Live rows never match, so re-ships are idempotent and the live
                # record is untouchable by construction.
                vcol = meta["version_col"]
                conn.execute(sa.text(
                    f"DELETE FROM `{table}` WHERE `{vcol}` LIKE :p"),
                    {"p": meta["version_prefix"] + "%"})
            elif mode == "replace":
                conn.execute(sa.text(f"DELETE FROM `{table}`"))
            else:
                raise ValueError(f"unknown load mode {mode!r} for {table}")
        # to_sql creates the table on first sight (RDS may lack e.g. player
        # tables that were never queried by the API tier).
        df.to_sql(table, conn, if_exists="append", index=False)


def load_pending(engine=None, bucket: str | None = None, dry_run: bool = False) -> dict:
    """Process every complete drop under pending/. Returns a summary dict."""
    import boto3

    bucket = bucket or os.environ.get(DEFAULT_BUCKET_ENV)
    if not bucket:
        raise RuntimeError(f"no bucket given and {DEFAULT_BUCKET_ENV} is not set")
    if engine is None:
        from core.db import get_engine
        engine = get_engine()

    s3 = boto3.client("s3")
    resp = s3.list_objects_v2(Bucket=bucket, Prefix="pending/", Delimiter="/")
    stamps = sorted(
        p["Prefix"].split("/")[1] for p in resp.get("CommonPrefixes", [])
    )
    if not stamps:
        _log("no pending drops")
        return {"drops": 0, "tables": 0, "rows": 0, "failed": 0}

    totals = {"drops": 0, "tables": 0, "rows": 0, "failed": 0}
    for stamp in stamps:  # oldest first, so newer windows win on overlap
        prefix = f"pending/{stamp}/"
        try:
            manifest = json.loads(
                s3.get_object(Bucket=bucket, Key=prefix + "manifest.json")
                ["Body"].read())
        except s3.exceptions.NoSuchKey:
            _log(f"{stamp}: no manifest yet (upload in progress?) — skipping")
            continue

        _log(f"{stamp}: {len(manifest['tables'])} tables, window "
             f"{manifest.get('window_days')}d, fetch_ok={manifest.get('fetch_ok')}")
        if dry_run:
            continue

        try:
            drop_rows = 0
            for table, meta in manifest["tables"].items():
                body = s3.get_object(Bucket=bucket, Key=f"{prefix}{table}.parquet")["Body"].read()
                df = pd.read_parquet(io.BytesIO(body))
                _load_table(engine, table, df, meta)
                drop_rows += len(df)
                _log(f"{stamp}: {table} <- {len(df)} rows ({meta.get('mode')})")
            totals["drops"] += 1
            totals["tables"] += len(manifest["tables"])
            totals["rows"] += drop_rows
        except Exception as exc:
            # Leave the drop in pending/ — tomorrow's run retries it. The word
            # ERROR here is load-bearing: the CloudWatch metric filter alarms on it.
            _log(f"ERROR loading drop {stamp}: {exc} — left in pending/ for retry")
            totals["failed"] += 1
            continue

        # Success: move the whole drop to processed/ (S3 move = copy + delete).
        listed = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
        for obj in listed.get("Contents", []):
            dest = obj["Key"].replace("pending/", "processed/", 1)
            s3.copy_object(Bucket=bucket, Key=dest,
                           CopySource={"Bucket": bucket, "Key": obj["Key"]})
            s3.delete_object(Bucket=bucket, Key=obj["Key"])
        _log(f"{stamp}: loaded ({drop_rows} rows) and moved to processed/")

    _log(f"done: {totals['drops']} drops loaded, {totals['failed']} failed, "
         f"{totals['rows']} rows")
    return totals


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--bucket", default=None,
                    help=f"Ingest bucket (default: ${DEFAULT_BUCKET_ENV})")
    ap.add_argument("--dry-run", action="store_true",
                    help="List pending drops + manifests without loading")
    args = ap.parse_args()
    started = datetime.now().isoformat(timespec="seconds")
    _log(f"start {started}")
    totals = load_pending(bucket=args.bucket, dry_run=args.dry_run)
    return 1 if totals["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
