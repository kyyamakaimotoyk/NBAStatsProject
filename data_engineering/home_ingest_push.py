"""Home-side nightly job: fetch NBA data locally, hand it to the cloud via S3.

stats.nba.com (and lately cdn.nba.com) hard-block AWS IPs, so the raw-data fetch
runs HERE — on a residential IP — and the cloud consumes the result. This script
is the whole home side of that handoff:

    1. fetch   - run the existing ingest (main_refactored.py) into local MySQL.
    2. schedule- fetch the league schedule (works from home) for the next 2 weeks.
    3. export  - dump a trailing window of every ingest table to parquet.
    4. upload  - push the drop to s3://<bucket>/pending/<stamp>/, manifest LAST
                 (the manifest is the "drop is complete" marker the loader keys on).

The export is a trailing WINDOW (default 14 days), not a delta: the cloud loader
upserts, so re-shipping a game twice is free, and there's no bookkeeping to
corrupt. Idempotent on both sides.

Runs from Windows Task Scheduler every morning (see home_ingest.bat). Uses the
`home-ingest` AWS profile — an IAM user that can ONLY put objects in the ingest
bucket.

Usage:
    python data_engineering/home_ingest_push.py                 # normal nightly run
    python data_engineering/home_ingest_push.py --window-days 30  # wider re-ship
    python data_engineering/home_ingest_push.py --skip-fetch      # export+upload only
    python data_engineering/home_ingest_push.py --dry-run         # no upload
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.db import get_engine  # noqa: E402  (needs ROOT on sys.path)

DEFAULT_BUCKET = "nba-game-predictor-ingest-583686634997"
DEFAULT_PROFILE = "home-ingest"
DEFAULT_WINDOW_DAYS = 14

# The 8 flat columns predict_games' schedule contract expects (same shape whether
# the schedule came from ScheduleLeagueV2 or the CDN flattener).
SCHEDULE_COLS = [
    "gameId", "gameDate", "gameStatusText", "arenaName",
    "homeTeam_teamId", "awayTeam_teamId",
    "homeTeam_teamTricode", "awayTeam_teamTricode",
]

# Every table the ingest writes, keyed by its game-id column. Mirrors
# main_refactored.NBADataImporter._get_table_config (without the nba_data. prefix
# — we run against whatever schema the engine's NBA_DB_NAME points at).
GAME_TABLES: dict[str, str] = {
    "boxscoreadvancedv3_player": "gameId", "boxscoreadvancedv3_team": "gameId",
    "boxscoredefensivev2_player": "gameId", "boxscoredefensivev2_team": "gameId",
    "boxscorefourfactorsv3_player": "gameId", "boxscorefourfactorsv3_team": "gameId",
    "boxscorehustlev2_player": "gameId", "boxscorehustlev2_team": "gameId",
    "boxscoremiscv3_player": "gameId", "boxscoremiscv3_team": "gameId",
    "boxscoreplayertrackv3_player": "gameId", "boxscoreplayertrackv3_team": "gameId",
    "boxscorescoringv3_player": "gameId", "boxscorescoringv3_team": "gameId",
    "boxscoresummaryv2_game_info": "GAME_ID",
    "boxscoresummaryv2_inactive_players": "GAME_ID",
    "boxscoresummaryv2_other_stats": "GAME_ID",
    "boxscoresummaryv2_referee": "GAME_ID",
    "boxscoresummaryv2_summary": "GAME_ID",
    "boxscoresummaryv3_game_summary": "gameId",
    "boxscoresummaryv3_game_info": "gameId",
    "boxscoresummaryv3_arena_info": "gameId",
    "boxscoresummaryv3_officials": "gameId",
    "boxscoresummaryv3_line_score": "gameId",
    "boxscoresummaryv3_inactive_players": "gameId",
    "boxscoresummaryv3_last_five_meetings": "gameId",
    "boxscoresummaryv3_other_stats": "gameId",
    "boxscoretraditionalv3_bench": "gameId",
    "boxscoretraditionalv3_player": "gameId",
    "boxscoretraditionalv3_team": "gameId",
    "boxscoreusagev3_player": "gameId", "boxscoreusagev3_team": "gameId",
}

# Small reference tables shipped whole every run (loader mode: replace).
FULL_TABLES = ["nba_teams", "nba_players", "team_lineup_snapshots"]


def log(msg: str) -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def run_fetch() -> bool:
    """Run the existing nba_api ingest (same command the pipeline stage uses)."""
    cmd = [sys.executable, str(ROOT / "data_engineering" / "main_refactored.py")]
    log(f"fetch: {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=ROOT)
    if proc.returncode != 0:
        log(f"fetch: FAILED with exit code {proc.returncode} (continuing — "
            "we still ship the schedule and whatever data we have)")
        return False
    log("fetch: done")
    return True


def fetch_schedule(window_days: int) -> pd.DataFrame:
    """League schedule for [today-3, today+window] — works from a home IP."""
    from nba_api.stats.endpoints import ScheduleLeagueV2

    sched = ScheduleLeagueV2().get_data_frames()[0]
    missing = [c for c in SCHEDULE_COLS if c not in sched.columns]
    if missing:
        raise RuntimeError(f"ScheduleLeagueV2 shape changed — missing {missing}")
    sched = sched[SCHEDULE_COLS].copy()
    dates = pd.to_datetime(sched["gameDate"], errors="coerce").dt.normalize()
    lo = pd.Timestamp(date.today() - timedelta(days=3))
    hi = pd.Timestamp(date.today() + timedelta(days=window_days))
    sched = sched[(dates >= lo) & (dates <= hi)].copy()
    # Normalize gameDate to a plain ISO date string so the DB round-trip is exact.
    sched["gameDate"] = dates[(dates >= lo) & (dates <= hi)].dt.strftime("%Y-%m-%d")
    return sched


def table_exists(conn, name: str) -> bool:
    q = sa.text(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = DATABASE() AND table_name = :t"
    )
    return bool(conn.execute(q, {"t": name}).scalar())


def export_tables(window_days: int, out_dir: Path) -> dict:
    """Dump the trailing window of every ingest table to parquet. Returns the
    manifest 'tables' block: {table: {rows, mode, gid_col?}}."""
    cutoff = (date.today() - timedelta(days=window_days)).isoformat()
    tables: dict = {}
    eng = get_engine()
    with eng.connect() as conn:
        gids = [int(r[0]) for r in conn.execute(sa.text(
            "SELECT DISTINCT GAME_ID FROM game_list WHERE GAME_DATE >= :c"), {"c": cutoff})]
        log(f"export: {len(gids)} games in window (>= {cutoff})")

        # game_list itself — windowed by date, loader deletes+reinserts the window.
        gl = pd.read_sql(
            sa.text("SELECT * FROM game_list WHERE GAME_DATE >= :c"), conn, params={"c": cutoff})
        if len(gl) > 0:
            gl.to_parquet(out_dir / "game_list.parquet", index=False)
            tables["game_list"] = {"rows": len(gl), "mode": "date_window",
                                   "date_col": "GAME_DATE", "cutoff": cutoff}

        # Boxscore tables — windowed by game id. CAST handles the varchar
        # ('0022301195') vs bigint storage difference across v2/v3 tables.
        if gids:
            id_list = ",".join(str(g) for g in gids)  # ints from the DB, safe to inline
            for tbl, gid_col in GAME_TABLES.items():
                if not table_exists(conn, tbl):
                    continue
                df = pd.read_sql(sa.text(
                    f"SELECT * FROM `{tbl}` WHERE CAST(`{gid_col}` AS UNSIGNED) IN ({id_list})"
                ), conn)
                if len(df) == 0:
                    continue
                df.to_parquet(out_dir / f"{tbl}.parquet", index=False)
                tables[tbl] = {"rows": len(df), "mode": "game_window", "gid_col": gid_col}

        # Small reference tables — shipped whole, replaced whole.
        for tbl in FULL_TABLES:
            if not table_exists(conn, tbl):
                continue
            df = pd.read_sql(sa.text(f"SELECT * FROM `{tbl}`"), conn)
            if len(df) == 0:
                continue
            df.to_parquet(out_dir / f"{tbl}.parquet", index=False)
            tables[tbl] = {"rows": len(df), "mode": "replace"}
    return tables


def upload(out_dir: Path, bucket: str, profile: str, stamp: str) -> None:
    import boto3

    s3 = boto3.Session(profile_name=profile).client("s3")
    prefix = f"pending/{stamp}"
    files = sorted(p for p in out_dir.iterdir() if p.suffix == ".parquet")
    for p in files:
        s3.upload_file(str(p), bucket, f"{prefix}/{p.name}")
        log(f"upload: s3://{bucket}/{prefix}/{p.name}")
    # Manifest goes LAST: its presence tells the loader the drop is complete.
    s3.upload_file(str(out_dir / "manifest.json"), bucket, f"{prefix}/manifest.json")
    log(f"upload: s3://{bucket}/{prefix}/manifest.json (drop complete)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS)
    ap.add_argument("--bucket", default=DEFAULT_BUCKET)
    ap.add_argument("--profile", default=DEFAULT_PROFILE)
    ap.add_argument("--skip-fetch", action="store_true",
                    help="Skip the nba_api ingest; just export + upload current DB state.")
    ap.add_argument("--dry-run", action="store_true", help="Export locally, don't upload.")
    args = ap.parse_args()

    fetch_ok = True if args.skip_fetch else run_fetch()

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    out_dir = Path(tempfile.mkdtemp(prefix=f"nba_ingest_{stamp}_"))
    log(f"export: staging in {out_dir}")

    schedule_rows = 0
    tables: dict = {}
    try:
        sched = fetch_schedule(args.window_days)
        if len(sched) > 0:
            sched.to_parquet(out_dir / "league_schedule.parquet", index=False)
            tables["league_schedule"] = {"rows": len(sched), "mode": "replace"}
        schedule_rows = len(sched)
        log(f"schedule: {schedule_rows} games in [today-3, today+{args.window_days}]")
    except Exception as e:
        log(f"schedule: FAILED — {e} (continuing; predict falls back to its cache)")

    tables.update(export_tables(args.window_days, out_dir))

    manifest = {
        "schema_version": 1,
        "generated_at_utc": stamp,
        "window_days": args.window_days,
        "fetch_ok": fetch_ok,
        "schedule_rows": schedule_rows,
        "tables": tables,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    total_rows = sum(t["rows"] for t in tables.values())
    log(f"export: {len(tables)} tables, {total_rows} rows total")

    if args.dry_run:
        log(f"dry-run: skipping upload; files left in {out_dir}")
        return 0

    upload(out_dir, args.bucket, args.profile, stamp)
    log("done" + ("" if fetch_ok else " (WITH FETCH FAILURE — see above)"))
    return 0 if fetch_ok else 1


if __name__ == "__main__":
    sys.exit(main())
