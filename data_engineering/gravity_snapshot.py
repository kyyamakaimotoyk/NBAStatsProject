"""Daily snapshot of nba_api GravityLeaders into gravity_leaders_daily (home side).

GravityLeaders (nba_api 1.11.4+) is the NBA's tracking "gravity" metric per
player: how much a player pulls defenders, split on/off ball and
perimeter/interior. It returns season-to-date totals only, with no date filter,
so the history needed for honest pre-game features exists only if it is saved
day by day. That is all this module does; hypotheses that use it are in
docs/experiment_backlog.md.

Runs inside the nightly home ingest (home_ingest_push.py, `--skip-gravity` to
skip). Also stands alone:
    python data_engineering/gravity_snapshot.py            # today's snapshot (ET date)
    python data_engineering/gravity_snapshot.py --dry-run  # fetch + show, no DB write

The table comes from sql/create_gravity_leaders_daily.sql (Kai runs it once).
Re-running on the same date replaces that date's rows. The raw response is also
kept in the raw archive (raw_api_archive.py).
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data_engineering import raw_api_archive as raw  # noqa: E402

TABLE = "gravity_leaders_daily"
META_COLS = ["snapshot_date", "season", "season_type", "fetched_at_utc"]
# Playoffs/PlayIn return empty outside their window; cheap to ask every day.
SEASON_TYPES = ["Regular Season", "PlayIn", "Playoffs"]


def season_for(d: date) -> str:
    """NBA season label for a date; seasons roll over on Aug 1 (same rule as the importer)."""
    start = d.year if d.month >= 8 else d.year - 1
    return f"{start}-{(start + 1) % 100:02d}"


def fetch(snapshot_date: date) -> pd.DataFrame:
    import time
    from nba_api.stats.endpoints import GravityLeaders
    season = season_for(snapshot_date)
    fetched = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    frames = []
    for st in SEASON_TYPES:
        try:
            ep = GravityLeaders(season=season, season_type_all_star=st, timeout=60)
            df = ep.get_data_frames()[0]
        except Exception as e:  # noqa: BLE001 - an empty/odd season type must not lose the others
            if st == "Regular Season":  # PlayIn/Playoffs are empty JSON outside their window
                print(f"gravity: {st} fetch failed ({type(e).__name__}: {str(e)[:80]}); continuing")
            time.sleep(0.6)
            continue
        if len(df):
            raw.save_endpoint(ep, f"{snapshot_date.isoformat()}_{st.replace(' ', '')}",
                              season=season)
            df.insert(0, "snapshot_date", snapshot_date)
            df.insert(1, "season", season)
            df.insert(2, "season_type", st)
            df.insert(3, "fetched_at_utc", fetched)
            frames.append(df)
        time.sleep(0.6)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def snapshot(engine, snapshot_date: date, dry_run: bool = False, log=print) -> int:
    """Fetch and store one day's snapshot. Returns rows written (or that would be)."""
    insp = sa.inspect(engine)
    has_table = insp.has_table(TABLE)
    if not has_table and not dry_run:
        log(f"gravity: table {TABLE} missing - run sql/create_gravity_leaders_daily.sql once; skipping")
        return 0
    df = fetch(snapshot_date)
    if df.empty:
        log(f"gravity: no rows for {season_for(snapshot_date)} (offseason?)")
        return 0
    tcols = [c["name"] for c in insp.get_columns(TABLE)] if has_table else list(df.columns)
    extra = [c for c in df.columns if c not in tcols]
    if extra:  # the schema check alerts on this too; never fail the insert over it
        log(f"gravity: dropping API columns not in the table: {extra}")
    df = df[[c for c in df.columns if c in tcols]]
    if dry_run:
        log(f"gravity: dry-run, {len(df)} rows for {snapshot_date} "
            f"({df.season_type.value_counts().to_dict()})")
        return len(df)
    with engine.begin() as conn:
        conn.execute(sa.text(f"DELETE FROM {TABLE} WHERE snapshot_date = :d"), {"d": snapshot_date})
        df.to_sql(TABLE, conn, if_exists="append", index=False)
    log(f"gravity: {len(df)} rows stored for {snapshot_date} "
        f"({df.season_type.value_counts().to_dict()})")
    return len(df)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--date", help="Snapshot date label (default: today, US Eastern).")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    from core.db import get_engine
    from data_engineering.home_ingest_push import et_today
    d = date.fromisoformat(args.date) if args.date else et_today()
    snapshot(get_engine(), d, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
