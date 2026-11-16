"""Fill MySQL box-score tables from the raw nba_api archive, offline (no API calls).

Two jobs:
  * --columns: a column the API sends but the table didn't have (the schema check
    reports these as "New in API") was added to the table with ALTER TABLE; fill it
    for every archived game.
  * --insert-missing: games that are in the archive but have no rows in the table
    (an import that failed after the fetch, like the 2026-11 "Unknown column"
    outage) get their rows inserted from the archive.

DB writes are Kai's to run. Always --dry-run first:
    python data_engineering/backfill_from_raw.py --table boxscorehustlev2_team --columns screenAssistPoints --dry-run
    python data_engineering/backfill_from_raw.py --table boxscorehustlev2_team --columns screenAssistPoints
    python data_engineering/backfill_from_raw.py --table boxscoremiscv3_team --insert-missing --season 2026-27 --dry-run

If a --columns name is not in the table yet, the script prints a suggested
ALTER TABLE and stops. RDS gets the column the same way (ALTER on RDS), then a
wide re-ship: `home_ingest_push.py --skip-fetch --window-days N` (the loader
upserts whole rows).
"""
from __future__ import annotations

import argparse
import importlib
import re
import sys
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data_engineering import raw_api_archive as raw  # noqa: E402
from data_engineering.api_schema_check import ENDPOINT_FRAMES, ADDED_BY_IMPORTER  # noqa: E402

TMP_TABLE = "_backfill_from_raw_tmp"


def table_spec(table: str) -> tuple[str, str, int]:
    """(module, class name, frame index) for a stored table."""
    for mod, cls, frames in ENDPOINT_FRAMES:
        for i, t in frames.items():
            if t == table:
                return mod, cls, i
    raise SystemExit(f"{table} is not an archived box-score table "
                     f"(see ENDPOINT_FRAMES in api_schema_check.py)")


def key_columns(table: str, frame_cols) -> list[str]:
    """Row key = the importer's (game id col, unique id col), plus startersBench
    for the bench table (two rows per team)."""
    src = (ROOT / "data_engineering" / "main_refactored.py").read_text(encoding="utf-8")
    m = re.search(rf"'nba_data\.{table}':\s*\['(\w+)',\s*'(\w+)'", src)
    if not m:
        raise SystemExit(f"no key config for {table} in main_refactored._get_table_config")
    keys = [m.group(1), m.group(2)]
    if "startersBench" in frame_cols and "startersBench" not in keys:
        keys.append("startersBench")
    return keys


def load_archive(table: str, season: str | None) -> pd.DataFrame:
    mod, cls_name, idx = table_spec(table)
    cls = getattr(importlib.import_module(f"nba_api.stats.endpoints.{mod}"), cls_name)
    frames, bad = [], 0
    for path in raw.iter_files(cls_name, season):
        try:
            body = raw.read(path)
            ep = raw.replay(cls, body, game_id=body["params"].get("GameID", path.stem.split(".")[0]))
            df = ep.get_data_frames()[idx]
            if table in ADDED_BY_IMPORTER and "GAME_ID" in ADDED_BY_IMPORTER[table]:
                df["GAME_ID"] = body["params"].get("GameID")
            frames.append(df)
        except Exception as e:  # noqa: BLE001
            bad += 1
            print(f"  skip {path.name}: {type(e).__name__}: {e}")
    print(f"archive: {len(frames)} {cls_name} files for {table}"
          + (f" ({season})" if season else "") + (f", {bad} unreadable" if bad else ""))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def sql_type(s: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(s):
        return "TINYINT(1)"
    if pd.api.types.is_integer_dtype(s):
        return "BIGINT"
    if pd.api.types.is_float_dtype(s):
        return "DOUBLE"
    return "TEXT"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--table", required=True)
    ap.add_argument("--columns", help="Comma-separated columns to fill from the archive.")
    ap.add_argument("--insert-missing", action="store_true",
                    help="Insert full rows for archived games that have no rows in the table.")
    ap.add_argument("--season", help='Limit to one season folder, e.g. "2026-27".')
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not args.columns and not args.insert_missing:
        ap.error("give --columns and/or --insert-missing")

    from core.db import get_engine
    engine = get_engine()
    df = load_archive(args.table, args.season)
    if df.empty:
        print("nothing archived for this table yet")
        return 0
    insp = sa.inspect(engine)
    tcols = [c["name"] for c in insp.get_columns(args.table)]
    keys = key_columns(args.table, df.columns)
    gid = keys[0]

    if args.columns:
        cols = [c.strip() for c in args.columns.split(",") if c.strip()]
        not_in_api = [c for c in cols if c not in df.columns]
        if not_in_api:
            print(f"ERROR: not in the archived responses: {not_in_api}")
            return 2
        missing = [c for c in cols if c not in tcols]
        if missing:
            print(f"ERROR: add the column(s) to the table first (local MySQL; same on RDS):")
            for c in missing:
                print(f"  ALTER TABLE `{args.table}` ADD COLUMN `{c}` {sql_type(df[c])} NULL;")
            return 2
        sub = df[keys + cols].drop_duplicates(subset=keys, keep="last")
        nn = {c: f"{sub[c].notna().mean():.0%}" for c in cols}
        print(f"fill: {len(sub)} rows from {sub[gid].nunique()} games; non-null in archive: {nn}")
        if args.dry_run:
            print("dry-run: no writes")
        else:
            with engine.begin() as conn:
                sub.to_sql(TMP_TABLE, conn, if_exists="replace", index=False)
                on = " AND ".join(f"t.`{k}` = s.`{k}`" for k in keys)
                sets = ", ".join(f"t.`{c}` = s.`{c}`" for c in cols)
                n = conn.execute(sa.text(f"UPDATE `{args.table}` t JOIN `{TMP_TABLE}` s ON {on} SET {sets}")).rowcount
                conn.execute(sa.text(f"DROP TABLE `{TMP_TABLE}`"))
            print(f"fill: {n} rows updated in {args.table}")

    if args.insert_missing:
        have = pd.read_sql(f"SELECT DISTINCT `{gid}` FROM `{args.table}`", engine)[gid].astype(str).str.zfill(10)
        todo = df[~df[gid].astype(str).str.zfill(10).isin(set(have))]
        todo = todo[[c for c in todo.columns if c in tcols]]
        print(f"insert-missing: {todo[gid].nunique()} games, {len(todo)} rows not in {args.table}")
        if len(todo) and not args.dry_run:
            ids = sorted({int(g) for g in todo[gid]})
            with engine.begin() as conn:
                todo.to_sql(args.table, conn, if_exists="append", index=False)
                # mark them done so the importer's re-import pass doesn't fetch them again
                conn.execute(sa.text(
                    f"UPDATE importedgamesmemory SET `nba_data.{args.table}` = 1 "
                    f"WHERE gameId IN ({','.join(map(str, ids))})"))
            print(f"insert-missing: inserted {len(todo)} rows, {len(ids)} games marked done "
                  f"in importedgamesmemory")
        elif args.dry_run:
            print("dry-run: no writes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
