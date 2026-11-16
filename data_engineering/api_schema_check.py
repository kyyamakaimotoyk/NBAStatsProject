"""nba_api schema check: what the API sends vs what we store and what we use.

Why this exists: on the nba_api 1.11.3 -> 1.12.0 upgrade (2026-11-16), every
box-score frame gained two columns and every INSERT failed for days before
anyone noticed. Endpoints and library versions will keep changing, so the home
ingest runs this check on every nightly run.

For every endpoint frame the importer stores (plus LeagueGameFinder -> game_list
and the ScheduleLeagueV2 contract), the check:
  1. fetches one recent finished game and records the column list the API sends;
  2. compares it with the MySQL table (new columns are dropped at insert,
     columns that went missing arrive as NULL from now on);
  3. compares it with the ACCEPTED BASELINE (data_engineering/api_schema_baseline.json),
     so a change alerts until someone looks at it and runs --accept;
  4. finds which stored columns the pipeline actually reads (SQL in the team
     feature, player model, serving and site/API code) and which of those end
     up in the production team model's features (core/e22 keep-list);
  5. measures how full those columns are over the last 14 days vs the 60 days
     before, so data that silently stops arriving (column present, values NULL)
     is caught too.

Alerts (`alerts`) are the things that need a person:
  * any difference from the accepted baseline (columns added/removed, a frame
    or endpoint missing);
  * a column the pipeline reads stopped filling, or a table the pipeline reads
    got no rows in 14 days while games were played.
The home ingest writes the result into the drop's manifest; the cloud S3 loader
prints each alert as an `ERROR: API_SCHEMA_...` line, which emails through the
existing CloudWatch ERROR filter. A full markdown report goes to
docs/api_schema_report.md with --write-doc.

Usage (home PC, residential IP; stats.nba.com blocks AWS):
    python data_engineering/api_schema_check.py                 # check + print summary
    python data_engineering/api_schema_check.py --write-doc     # also regenerate docs/api_schema_report.md
    python data_engineering/api_schema_check.py --accept        # after reviewing: make today's API shape the baseline
    python data_engineering/api_schema_check.py --game-id 0022600236
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data_engineering import raw_api_archive  # noqa: E402

BASELINE_PATH = ROOT / "data_engineering" / "api_schema_baseline.json"
DOC_PATH = ROOT / "docs" / "api_schema_report.md"
KEEP_LIST_PATH = ROOT / "core" / "e22_keep_columns_top250.json"

# (endpoint module, class, {frame index: table}). Mirrors the importer's endpoint
# dicts in main_refactored.process_single_game; check_importer_coverage() fails
# loudly if the importer gains a table this list doesn't cover.
ENDPOINT_FRAMES = [
    ("boxscoreadvancedv3", "BoxScoreAdvancedV3", {0: "boxscoreadvancedv3_player", 1: "boxscoreadvancedv3_team"}),
    ("boxscoredefensivev2", "BoxScoreDefensiveV2", {0: "boxscoredefensivev2_player", 1: "boxscoredefensivev2_team"}),
    ("boxscorefourfactorsv3", "BoxScoreFourFactorsV3", {0: "boxscorefourfactorsv3_player", 1: "boxscorefourfactorsv3_team"}),
    ("boxscorehustlev2", "BoxScoreHustleV2", {0: "boxscorehustlev2_player", 1: "boxscorehustlev2_team"}),
    ("boxscoremiscv3", "BoxScoreMiscV3", {0: "boxscoremiscv3_player", 1: "boxscoremiscv3_team"}),
    ("boxscoreplayertrackv3", "BoxScorePlayerTrackV3", {0: "boxscoreplayertrackv3_player", 1: "boxscoreplayertrackv3_team"}),
    ("boxscorescoringv3", "BoxScoreScoringV3", {0: "boxscorescoringv3_player", 1: "boxscorescoringv3_team"}),
    ("boxscoretraditionalv3", "BoxScoreTraditionalV3", {0: "boxscoretraditionalv3_player", 1: "boxscoretraditionalv3_bench", 2: "boxscoretraditionalv3_team"}),
    ("boxscoreusagev3", "BoxScoreUsageV3", {0: "boxscoreusagev3_player", 1: "boxscoreusagev3_team"}),
    ("boxscoresummaryv2", "BoxScoreSummaryV2", {1: "boxscoresummaryv2_summary", 2: "boxscoresummaryv2_referee", 3: "boxscoresummaryv2_inactive_players", 6: "boxscoresummaryv2_other_stats", 7: "boxscoresummaryv2_game_info"}),
    ("boxscoresummaryv3", "BoxScoreSummaryV3", {0: "boxscoresummaryv3_game_summary", 1: "boxscoresummaryv3_game_info", 2: "boxscoresummaryv3_arena_info", 3: "boxscoresummaryv3_officials", 4: "boxscoresummaryv3_line_score", 5: "boxscoresummaryv3_inactive_players", 6: "boxscoresummaryv3_last_five_meetings", 7: "boxscoresummaryv3_other_stats"}),
]
# The importer stops calling BoxScoreSummaryV2 for games after this date (they
# return no data); its tables are reported but never alert on missing rows.
SKIPPED_FOR_NEW_GAMES = {t for m, c, f in ENDPOINT_FRAMES if m == "boxscoresummaryv2" for t in f.values()}
# Columns the importer adds itself (add_game_id=True), so the API never sends them.
ADDED_BY_IMPORTER = {"boxscoresummaryv2_summary": ["GAME_ID"], "boxscoresummaryv2_referee": ["GAME_ID"],
                     "boxscoresummaryv2_inactive_players": ["GAME_ID"],
                     "gravity_leaders_daily": ["snapshot_date", "season", "season_type", "fetched_at_utc"]}
# Season-level endpoints that legitimately return nothing in the offseason: a
# failure there is a note, not an alert, unless games were played recently.
SEASONAL = {"gravity_leaders_daily"}

# Code whose SQL reads the stored tables, by consumer.
CONSUMERS = {
    "team": ["data_engineering/feature_engineering.py", "data_engineering/compute_elo.py"],
    # player impact -> the team model's slot / availability / impact features
    "impact": ["data_engineering/player_impact.py"],
    "player": ["data_engineering/player_dataset.py", "data_engineering/player_projections.py",
               "modeling/player_predict.py"],
    "serving": ["modeling/predict_games.py", "modeling/batch_predict_today.py",
                "modeling/serving_features.py"],
    "site": ["api/queries.py"],
}

RECENT_DAYS = 14
PRIOR_DAYS = 60
FILL_DROP_PRIOR_MIN = 0.80   # a column this full before ...
FILL_DROP_RATIO = 0.5        # ... that falls below half of it recently -> alert
MIN_RECENT_GAMES = 20        # below this (offseason, outage) the data checks are skipped
# Game coverage: every regular-season/play-in/playoff game in game_list from the
# last COVERAGE_DAYS that is more than COVERAGE_GRACE_DAYS old must have rows in
# each box-score table. Fill rates alone can't see a game with no rows at all
# (2026-11-16: 6 games lost their player box scores without an alert).
COVERAGE_DAYS = 30
COVERAGE_GRACE_DAYS = 3
COVERAGE_SEASON_PREFIXES = ("2", "4", "5")   # SEASON_ID / GAME_ID[2]: regular, playoffs, play-in
# Empty for some games by nature (no inactive players, no prior meetings).
OFTEN_EMPTY = {"boxscoresummaryv3_inactive_players", "boxscoresummaryv3_last_five_meetings"}


# ---------------------------------------------------------------------------
# 1. What the API sends
# ---------------------------------------------------------------------------
def pick_probe_game(engine) -> str:
    """Latest game_list game at least 3 days old (box scores fully posted)."""
    import pandas as pd
    cutoff = (date.today() - timedelta(days=3)).isoformat()
    row = pd.read_sql(
        f"SELECT GAME_ID FROM game_list WHERE GAME_DATE <= '{cutoff}' "
        f"AND WL IS NOT NULL ORDER BY GAME_DATE DESC, GAME_ID DESC LIMIT 1", engine)
    return str(int(row.iloc[0, 0])).zfill(10)


def fetch_api_columns(game_id: str, game_date: str | None) -> dict:
    """{table: {"columns": [...], "rows": n} | {"error": str}} for every stored frame."""
    import importlib
    out: dict = {}
    for mod, cls_name, frames in ENDPOINT_FRAMES:
        cls = getattr(importlib.import_module(f"nba_api.stats.endpoints.{mod}"), cls_name)
        try:
            dfs = cls(game_id=game_id, timeout=60).get_data_frames()
            for i, table in frames.items():
                if i >= len(dfs):
                    out[table] = {"error": f"{cls_name} returned {len(dfs)} frames, no index {i}"}
                else:
                    out[table] = {"columns": list(dfs[i].columns), "rows": len(dfs[i])}
        except Exception as e:  # noqa: BLE001 - every failure is a finding here
            for table in frames.values():
                out[table] = {"error": f"{cls_name}: {type(e).__name__}: {str(e)[:150]}"}
        time.sleep(0.6)

    from nba_api.stats.endpoints import leaguegamefinder, ScheduleLeagueV2
    try:
        d = datetime.strptime(game_date, "%Y-%m-%d").strftime("%m/%d/%Y") if game_date else None
        df = leaguegamefinder.LeagueGameFinder(league_id_nullable="00", date_from_nullable=d,
                                               date_to_nullable=d, timeout=60).get_data_frames()[0]
        out["game_list"] = {"columns": list(df.columns), "rows": len(df)}
    except Exception as e:  # noqa: BLE001
        out["game_list"] = {"error": f"LeagueGameFinder: {type(e).__name__}: {str(e)[:150]}"}
    time.sleep(0.6)
    try:
        df = ScheduleLeagueV2(timeout=60).get_data_frames()[0]
        out["schedule (ScheduleLeagueV2)"] = {"columns": list(df.columns), "rows": len(df)}
    except Exception as e:  # noqa: BLE001
        out["schedule (ScheduleLeagueV2)"] = {"error": f"ScheduleLeagueV2: {type(e).__name__}: {str(e)[:150]}"}
    time.sleep(0.6)
    from nba_api.stats.endpoints import GravityLeaders
    from data_engineering.gravity_snapshot import season_for, TABLE as GRAVITY_TABLE
    try:
        df = GravityLeaders(season=season_for(date.today()), timeout=60).get_data_frames()[0]
        out[GRAVITY_TABLE] = {"columns": list(df.columns), "rows": len(df)}
    except Exception as e:  # noqa: BLE001
        out[GRAVITY_TABLE] = {"error": f"GravityLeaders: {type(e).__name__}: {str(e)[:150]}"}
    return out


USE_SCAN_DIRS = ["data_engineering", "modeling", "orchestration", "api", "scripts", "visualization", "core"]


def endpoint_inventory() -> tuple[list[str], list[str]]:
    """(every endpoint module in the installed nba_api, the ones its source marks
    deprecated). nba_api flags deprecation with warnings.warn(..., DeprecationWarning)
    in the endpoint's module, so a text scan finds them without calling anything."""
    import pkgutil
    import nba_api.stats.endpoints as eps
    pkg = Path(eps.__path__[0])
    mods = sorted(m.name for m in pkgutil.iter_modules(eps.__path__) if not m.name.startswith("_"))
    dep = sorted(m for m in mods
                 if "DeprecationWarning" in (pkg / f"{m}.py").read_text(encoding="utf-8", errors="ignore"))
    return mods, dep


def endpoints_we_use() -> dict[str, list[str]]:
    """{endpoint module: [files importing it]} across production code (deprecated/ and
    experiments/ excluded)."""
    out: dict[str, set] = {}
    pat = re.compile(r"from\s+nba_api\.stats\.endpoints(?:\.(\w+))?\s+import\s+(\([^)]*\)|[^\n]+)")
    for d in USE_SCAN_DIRS:
        for f in (ROOT / d).rglob("*.py"):
            if f.name == "api_schema_check.py":  # the checker's own probes don't count as use
                continue
            src = f.read_text(encoding="utf-8", errors="ignore")
            for mod, names in pat.findall(src):
                found = [mod] if mod else re.findall(r"\b(\w+)\b", names.replace("as ", " "))
                for n in found:
                    n = n.lower()
                    if n and n not in {"import"}:
                        out.setdefault(n, set()).add(str(f.relative_to(ROOT)).replace("\\", "/"))
    return {k: sorted(v) for k, v in out.items()}


def check_importer_coverage() -> list[str]:
    """Tables the importer tracks that ENDPOINT_FRAMES doesn't cover."""
    covered = {t for _, _, f in ENDPOINT_FRAMES for t in f.values()}
    src = (ROOT / "data_engineering" / "main_refactored.py").read_text(encoding="utf-8")
    tracked = set(re.findall(r"'nba_data\.(boxscore\w+)'", src))
    return sorted(tracked - covered)


# ---------------------------------------------------------------------------
# 2. What the pipeline reads (static scan of SQL strings)
# ---------------------------------------------------------------------------
_TABLE_REF = re.compile(r"\b(?:FROM|JOIN)\s+(?:nba_data\.)?(\w+)(?:\s+(?:AS\s+)?(\w+))?", re.I)
_SQL_WORDS = {"on", "where", "join", "left", "inner", "group", "order", "limit", "using",
              "union", "natural", "cross", "right", "outer", "and", "set"}


def _string_literals(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docstrings.add(id(first.value))
    out = []
    for node in ast.walk(tree):
        if id(node) in docstrings:
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.append(node.value)
        elif isinstance(node, ast.JoinedStr):
            out.append("".join(v.value if isinstance(v, ast.Constant) else " {x} " for v in node.values))
    return out


def scan_usage(db_cols: dict[str, list[str]]) -> tuple[dict, dict]:
    """Returns (usage, aliases):
    usage[table][column] = {consumer, ...}; aliases[table][column] = {sql alias, ...}."""
    usage: dict = {t: {} for t in db_cols}
    aliases: dict = {t: {} for t in db_cols}
    for consumer, files in CONSUMERS.items():
        for rel in files:
            path = ROOT / rel
            if not path.exists():
                continue
            strings = _string_literals(path)
            file_alias: dict[str, str] = {}
            for s in strings:
                refs = [(t, a) for t, a in _TABLE_REF.findall(s) if t in db_cols]
                if not refs:
                    continue
                tables_here = []
                for t, a in refs:
                    tables_here.append(t)
                    if a and a.lower() not in _SQL_WORDS:
                        file_alias[a] = t
                single = len(set(tables_here)) == 1
                for t in set(tables_here):
                    my_aliases = [a for a, tt in file_alias.items() if tt == t]
                    if re.search(r"SELECT\s+\*", s, re.I) or any(re.search(rf"\b{a}\.\*", s) for a in my_aliases):
                        for c in db_cols[t]:
                            usage[t].setdefault(c, set()).add(consumer)
                        continue
                    for c in db_cols[t]:
                        # bare names count only when the statement reads one table;
                        # with joins, only alias-qualified references do
                        if (single and re.search(rf"(?<![\w.]){re.escape(c)}\b", s)) or any(
                                re.search(rf"\b{a}\.{re.escape(c)}\b", s) for a in my_aliases):
                            usage[t].setdefault(c, set()).add(consumer)
                            for al in re.findall(rf"\b{re.escape(c)}\s+as\s+(\w+)", s, re.I):
                                aliases[t].setdefault(c, set()).add(al)
            # alias-qualified references in strings without FROM (e.g. api/queries.py's
            # column map "bsm.pointsPaint")
            for s in strings:
                for a, c in re.findall(r"\b(\w+)\.(\w+)\b", s):
                    t = file_alias.get(a)
                    if t and c in db_cols[t]:
                        usage[t].setdefault(c, set()).add(consumer)
    return usage, aliases


def team_feature_map(db_cols, usage, aliases) -> dict:
    """{table: {column: n production team features built from it}} (direct rolling
    features only; ELO, availability and player-impact features are indirect)."""
    keep = json.loads(KEEP_LIST_PATH.read_text())
    base_counts: dict[str, int] = {}
    for f in keep:
        m = re.match(r"^(?:HOME|AWAY|DIFF)_(.+?)_(?:L5|L10)$", f)
        if m:
            base_counts[m.group(1)] = base_counts.get(m.group(1), 0) + 1
    out: dict = {}
    for t, cols in usage.items():
        for c, cons in cols.items():
            if "team" not in cons:
                continue
            names = {c} | aliases.get(t, {}).get(c, set())
            n = sum(base_counts.get(nm, 0) for nm in names)
            if n:
                out.setdefault(t, {})[c] = n
    return out


# ---------------------------------------------------------------------------
# 3. Is the data still arriving? (fill rates in MySQL)
# ---------------------------------------------------------------------------
def fill_rates(engine, db_cols, usage) -> tuple[dict, dict]:
    """fill[table][col] = (prior_share, recent_share); rows[table] = (prior_rows, recent_rows).
    Empty when fewer than MIN_RECENT_GAMES were played in the recent window."""
    import pandas as pd
    import sqlalchemy as sa
    today = date.today()
    recent_from = today - timedelta(days=RECENT_DAYS)
    prior_from = recent_from - timedelta(days=PRIOR_DAYS)
    games = pd.read_sql(
        f"SELECT DISTINCT GAME_ID, GAME_DATE FROM game_list WHERE GAME_DATE >= '{prior_from}'", engine)
    games["GAME_DATE"] = pd.to_datetime(games["GAME_DATE"]).dt.date
    recent_ids = games.loc[games.GAME_DATE >= recent_from, "GAME_ID"].astype(int)
    prior_ids = games.loc[games.GAME_DATE < recent_from, "GAME_ID"].astype(int)
    if len(recent_ids) < MIN_RECENT_GAMES:
        return {}, {}
    insp = sa.inspect(engine)
    fill, rows = {}, {}
    for t, cols in usage.items():
        used = [c for c in cols if c in db_cols.get(t, [])]
        if not used:
            continue
        tcols = {c["name"]: c for c in insp.get_columns(t)}
        gid = "gameId" if "gameId" in tcols else "GAME_ID"
        is_text = "CHAR" in str(tcols[gid]["type"]).upper() or "TEXT" in str(tcols[gid]["type"]).upper()
        fmt = (lambda i: f"'{str(i).zfill(10)}'") if is_text else str
        fills = ", ".join(f"SUM(`{c}` IS NOT NULL) AS `{c}`" for c in used)
        res = {}
        for label, ids in (("prior", prior_ids), ("recent", recent_ids)):
            if len(ids) == 0:
                res[label] = None
                continue
            q = f"SELECT COUNT(*) AS n_rows, {fills} FROM `{t}` WHERE `{gid}` IN ({','.join(fmt(i) for i in ids)})"
            res[label] = pd.read_sql(q, engine).iloc[0]
        p, r = res["prior"], res["recent"]
        rows[t] = (int(p["n_rows"]) if p is not None else 0, int(r["n_rows"]))
        fill[t] = {}
        for c in used:
            ps = float(p[c]) / p["n_rows"] if p is not None and p["n_rows"] else None
            rs = float(r[c]) / r["n_rows"] if r["n_rows"] else None
            fill[t][c] = (ps, rs)
    return fill, rows


def _game_id_sql(insp, table):
    """(game id column, formatter for ids in SQL) for a box-score table."""
    tcols = {c["name"]: c for c in insp.get_columns(table)}
    gid = "gameId" if "gameId" in tcols else "GAME_ID"
    typ = str(tcols[gid]["type"]).upper()
    is_text = "CHAR" in typ or "TEXT" in typ
    return gid, ((lambda i: f"'{str(i).zfill(10)}'") if is_text else (lambda i: str(int(i))))


def game_coverage(engine, tables) -> dict:
    """cov[table] = {"checked": n_games, "missing": [game ids], "null_id_rows": n}.
    Games: regular season, play-in and playoffs from the last COVERAGE_DAYS,
    at least COVERAGE_GRACE_DAYS old."""
    import pandas as pd
    import sqlalchemy as sa
    today = date.today()
    games = pd.read_sql(
        f"SELECT DISTINCT GAME_ID, SEASON_ID FROM game_list WHERE GAME_DATE >= '{today - timedelta(days=COVERAGE_DAYS)}' "
        f"AND GAME_DATE <= '{today - timedelta(days=COVERAGE_GRACE_DAYS)}'", engine)
    ids = sorted({int(g) for g, s in zip(games.GAME_ID, games.SEASON_ID)
                  if str(s)[:1] in COVERAGE_SEASON_PREFIXES})
    insp = sa.inspect(engine)
    cov = {}
    for t in tables:
        try:
            gid, fmt = _game_id_sql(insp, t)
        except Exception:  # noqa: BLE001 - table missing; reported elsewhere
            continue
        nulls = int(pd.read_sql(f"SELECT COUNT(*) FROM `{t}` WHERE `{gid}` IS NULL", engine).iloc[0, 0])
        have = set()
        if ids:
            got = pd.read_sql(f"SELECT DISTINCT `{gid}` AS g FROM `{t}` WHERE `{gid}` IN "
                              f"({','.join(fmt(i) for i in ids)})", engine).g
            have = {int(g) for g in got}
        cov[t] = {"checked": len(ids), "missing": [i for i in ids if i not in have], "null_id_rows": nulls}
    return cov


# ---------------------------------------------------------------------------
# Run + compare
# ---------------------------------------------------------------------------
def run_check(engine=None, game_id: str | None = None) -> dict:
    import nba_api
    import pandas as pd
    import sqlalchemy as sa
    if engine is None:
        from core.db import get_engine
        engine = get_engine()

    game_id = game_id or pick_probe_game(engine)
    gd = pd.read_sql(f"SELECT MIN(GAME_DATE) FROM game_list WHERE GAME_ID = {int(game_id)}", engine).iloc[0, 0]
    game_date = str(gd)[:10] if gd is not None else None

    api = fetch_api_columns(game_id, game_date)
    insp = sa.inspect(engine)
    db_cols = {}
    for t in api:
        try:
            db_cols[t] = [c["name"] for c in insp.get_columns(t)]
        except sa.exc.NoSuchTableError:
            pass
    usage, aliases = scan_usage(db_cols)
    feats = team_feature_map(db_cols, usage, aliases)
    fill, rows = fill_rates(engine, db_cols, usage)
    baseline = json.loads(BASELINE_PATH.read_text()) if BASELINE_PATH.exists() else None
    recent_games = int(pd.read_sql(
        f"SELECT COUNT(DISTINCT GAME_ID) FROM game_list WHERE GAME_DATE >= "
        f"'{date.today() - timedelta(days=RECENT_DAYS)}'", engine).iloc[0, 0])
    in_season = recent_games >= MIN_RECENT_GAMES

    from data_engineering.home_ingest_push import SCHEDULE_COLS
    alerts, notes, tables = [], [], {}
    for t, a in api.items():
        entry: dict = {"used": {c: sorted(s) for c, s in usage.get(t, {}).items()},
                       "team_features": feats.get(t, {})}
        api_cols = a.get("columns")
        if t.startswith("schedule"):
            db = SCHEDULE_COLS  # contract, not a table
        else:
            db = db_cols.get(t)
        entry["error"] = a.get("error")
        entry["rows"] = a.get("rows")
        if api_cols is not None and db is not None:
            entry["new_in_api"] = [c for c in api_cols if c not in db] if not t.startswith("schedule") else []
            entry["gone_from_api"] = [c for c in db if c not in api_cols
                                      and c not in ADDED_BY_IMPORTER.get(t, [])]
        base = (baseline or {}).get("tables", {}).get(t)
        if api_cols is not None and base is not None:
            entry["added_since_baseline"] = [c for c in api_cols if c not in base]
            entry["removed_since_baseline"] = [c for c in base if c not in api_cols]
        tables[t] = entry

        used = set(entry["used"]) if not t.startswith("schedule") else set(SCHEDULE_COLS)
        if t not in db_cols and not t.startswith("schedule"):
            notes.append(f"{t}: table not created yet (sql/ has its CREATE TABLE)")
        if a.get("error"):
            if t in SEASONAL and not in_season:
                notes.append(f"{t}: no data ({a['error'][:60]}); offseason, not alerting")
            elif base is not None or baseline is None:
                alerts.append(f"API_SCHEMA_CHANGED {t}: endpoint failed for {game_id} ({a['error']})")
            continue
        if a.get("rows") == 0 and t not in SKIPPED_FOR_NEW_GAMES:
            notes.append(f"{t}: 0 rows for probe game {game_id}")
        if baseline is not None and base is None:
            alerts.append(f"API_SCHEMA_CHANGED {t}: not in baseline ({len(api_cols)} columns)")
        add, rem = entry.get("added_since_baseline", []), entry.get("removed_since_baseline", [])
        if rem:
            hit = sorted(set(rem) & used)
            alerts.append(f"API_SCHEMA_CHANGED {t}: removed {rem}"
                          + (f" - USED by the pipeline: {hit}" if hit else ""))
        if add:
            alerts.append(f"API_SCHEMA_CHANGED {t}: new columns {add} (archived raw, dropped at "
                          f"insert; to keep: ALTER TABLE + backfill_from_raw.py --columns)")

    for t, cols in fill.items():
        if t in SKIPPED_FOR_NEW_GAMES:
            continue
        prior_rows, recent_rows = rows[t]
        if prior_rows and not recent_rows:
            alerts.append(f"API_DATA_GAP {t}: 0 rows for games in the last {RECENT_DAYS} days "
                          f"(read by: {', '.join(sorted({x for s in usage[t].values() for x in s}))})")
            continue
        stopped = [c for c, (ps, rs) in cols.items()
                   if ps is not None and rs is not None and ps >= FILL_DROP_PRIOR_MIN and rs < ps * FILL_DROP_RATIO]
        if stopped:
            alerts.append(f"API_DATA_GAP {t}: columns stopped filling in the last {RECENT_DAYS} days: {stopped}")

    # --- game coverage: whole games missing from a table, rows without a game id ---
    box_tables = [t for t in api if t in db_cols and not t.startswith("schedule")
                  and t not in SEASONAL and t not in SKIPPED_FOR_NEW_GAMES and t != "game_list"]
    coverage = game_coverage(engine, box_tables)
    gap_notes = []
    for t, c in coverage.items():
        read = t in usage and bool(usage[t])
        if c["missing"] and t not in OFTEN_EMPTY:
            shown = ", ".join(str(g) for g in c["missing"][:8]) + (" ..." if len(c["missing"]) > 8 else "")
            msg = (f"{t}: {len(c['missing'])} of {c['checked']} games from the last {COVERAGE_DAYS} days "
                   f"have no rows ({shown})")
            if read:
                alerts.append(f"API_DATA_GAP {msg} - fix: README runbook, \"Games missing from a table\"")
            else:
                gap_notes.append(f"{t}: {len(c['missing'])}")
        if c["null_id_rows"]:
            (alerts.append if read else notes.append)(
                f"API_DATA_GAP {t}: {c['null_id_rows']} rows with NULL game id (unpublished box scores "
                f"stored as empty rows; delete them and reset the games' status)")
    if gap_notes:
        notes.append(f"games missing from tables the pipeline doesn't read (last {COVERAGE_DAYS} days): "
                     + ", ".join(gap_notes))

    # --- endpoint inventory: new / removed / deprecated endpoints in the library ---
    installed, deprecated = endpoint_inventory()
    used = {m: f for m, f in endpoints_we_use().items() if m in installed or m in (baseline or {}).get("endpoints", [])}
    for m, files in sorted(used.items()):
        if m not in installed:
            alerts.append(f"API_SCHEMA_CHANGED endpoint {m} removed from nba_api {nba_api.__version__} "
                          f"(imported by {', '.join(files)})")
        elif m in deprecated:
            alerts.append(f"API_SCHEMA_CHANGED endpoint {m} is marked deprecated in nba_api "
                          f"{nba_api.__version__} (imported by {', '.join(files)})")
    if baseline and baseline.get("endpoints"):
        new_eps = sorted(set(installed) - set(baseline["endpoints"]))
        gone_eps = sorted(set(baseline["endpoints"]) - set(installed) - set(used))
        newly_dep = sorted(set(deprecated) - set(baseline.get("deprecated", [])) - set(used))
        if new_eps:
            notes.append(f"new nba_api endpoints available: {new_eps} (candidates: docs/model_tuning_log.md, proposed rows)")
        if gone_eps:
            notes.append(f"endpoints removed from nba_api (unused by us): {gone_eps}")
        if newly_dep:
            notes.append(f"endpoints newly deprecated (unused by us): {newly_dep}")

    # Tables with no description in the schema-doc generator (docs/DATABASE_SCHEMA.md)
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("gen_db_schema_doc", ROOT / "scripts" / "gen_db_schema_doc.py")
        gen = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gen)
        undocumented = [t for t in sa.inspect(engine).get_table_names()
                        if t not in gen.TABLE_INFO and gen.auto_info(t) is None]
        if undocumented:
            notes.append(f"tables without a description in scripts/gen_db_schema_doc.py: {undocumented} "
                         f"(add to TABLE_INFO, then regenerate docs/DATABASE_SCHEMA.md)")
    except Exception as e:  # noqa: BLE001 - doc hygiene must never fail the check
        notes.append(f"schema-doc coverage not checked ({type(e).__name__}: {e})")

    missing_cov = check_importer_coverage()
    if missing_cov:
        alerts.append(f"API_SCHEMA_CHANGED checker: importer tables not covered by ENDPOINT_FRAMES: {missing_cov}")

    return {
        "checked_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "nba_api": nba_api.__version__,
        "probe_game": game_id, "probe_game_date": game_date,
        "baseline": ({"nba_api": baseline.get("nba_api"), "accepted_at": baseline.get("accepted_at")}
                     if baseline else None),
        "status": "changed" if alerts else "ok",
        "alerts": alerts, "notes": notes,
        "tables": tables, "fill": {t: {c: list(v) for c, v in cs.items()} for t, cs in fill.items()},
        "rows": rows, "api": api, "coverage": coverage,
        "endpoints": {"installed": installed, "deprecated": deprecated, "used": used},
        "archive": raw_api_archive.inventory(), "archive_dir": (str(raw_api_archive.raw_dir().relative_to(ROOT)).replace("\\", "/")
                        if raw_api_archive.raw_dir().is_relative_to(ROOT) else "$NBA_RAW_API_DIR"),
    }


def accept(result: dict) -> None:
    tables = {t: a["columns"] for t, a in result["api"].items() if "columns" in a}
    if BASELINE_PATH.exists():  # keep the last good shape of endpoints that failed today
        old = json.loads(BASELINE_PATH.read_text()).get("tables", {})
        for t, cols in old.items():
            tables.setdefault(t, cols)
    BASELINE_PATH.write_text(json.dumps({
        "nba_api": result["nba_api"], "accepted_at": result["checked_at_utc"],
        "probe_game": result["probe_game"], "tables": tables,
        "endpoints": result["endpoints"]["installed"],
        "deprecated": result["endpoints"]["deprecated"]}, indent=1) + "\n")
    print(f"baseline written: {BASELINE_PATH.relative_to(ROOT)} ({len(tables)} frames, nba_api {result['nba_api']})")


def manifest_block(result: dict) -> dict:
    """The compact form shipped in the S3 drop manifest (the cloud loader reads it)."""
    return {k: result[k] for k in ("checked_at_utc", "nba_api", "probe_game", "status", "alerts", "notes")}


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------
def _pct(x):
    return "-" if x is None else f"{x:.0%}"


def write_doc(result: dict) -> None:
    L = []
    L.append("# nba_api schema report\n")
    L.append("*Generated by `python data_engineering/api_schema_check.py --write-doc`; do not edit by hand. "
             "What the API sends vs what MySQL stores vs what the pipeline reads. "
             "How to use it: README, \"When nba_api or an endpoint changes\".*\n")
    b = result["baseline"]
    L.append(f"- Checked: {result['checked_at_utc']} with nba_api **{result['nba_api']}**, "
             f"probe game `{result['probe_game']}` ({result['probe_game_date']})")
    L.append(f"- Baseline: " + (f"nba_api {b['nba_api']}, accepted {b['accepted_at']}" if b else "none yet (run `--accept`)"))
    L.append(f"- Status: **{result['status']}**\n")
    if result["alerts"]:
        L.append("**Alerts**\n")
        L += [f"- {a}" for a in result["alerts"]]
        L.append("")

    ep = result.get("endpoints") or {}
    if ep:
        L.append("## 0. Endpoints\n")
        L.append(f"nba_api {result['nba_api']} ships {len(ep['installed'])} stats endpoints; "
                 f"{len(ep['deprecated'])} are marked deprecated in its source. We import "
                 f"{len(ep['used'])}:\n")
        L.append("| Endpoint | Status | Imported by |")
        L.append("|---|---|---|")
        for m, files in sorted(ep["used"].items()):
            st = ("**REMOVED**" if m not in ep["installed"] else
                  "**DEPRECATED**" if m in ep["deprecated"] else "ok")
            L.append(f"| `{m}` | {st} | {', '.join(f'`{f}`' for f in files)} |")
        L.append("")
        L.append("Deprecated in this version (we use none unless marked above): "
                 + ", ".join(f"`{m}`" for m in ep["deprecated"]) + "\n")
        unused = [m for m in ep["installed"] if m not in ep["used"] and m not in ep["deprecated"]]
        L.append(f"<details><summary>{len(unused)} other endpoints available, not used</summary>\n\n"
                 + ", ".join(f"`{m}`" for m in unused) + "\n\n</details>\n")

    L.append("## 1. Schema differences (API now vs MySQL table)\n")
    L.append("New = the API sends it, the table has no column for it: dropped at insert but kept "
             "in the raw archive (§4), so `ALTER TABLE` + `backfill_from_raw.py --columns` "
             "recovers it for every archived game. Gone = the table has it, the API no longer "
             "sends it (NULL for new games). **Bold** = the pipeline reads it.\n")
    L.append("| Table | New in API | Gone from API | Endpoint status |")
    L.append("|---|---|---|---|")
    for t, e in result["tables"].items():
        used = set(e["used"])
        gone = ", ".join(f"**{c}**" if c in used else c for c in e.get("gone_from_api", [])) or "-"
        new = ", ".join(e.get("new_in_api", [])) or "-"
        status = f"FAILED: {e['error']}" if e.get("error") else f"ok, {e.get('rows')} rows"
        L.append(f"| `{t}` | {new} | {gone} | {status} |")
    L.append("")

    L.append("## 2. Columns the pipeline reads\n")
    L.append("Team = team-model feature code (rolling stats, ELO, availability); Impact = player "
             "impact code, which feeds the team model's slot / availability / impact features; "
             "Prod features = how many of the production team model's 252 features are built "
             "directly from the column (rolling L5/L10, HOME/AWAY/DIFF); Player = player "
             "projection model; Serving = nightly prediction code; Site = public API. "
             f"Fill = share of rows with a value, prior {PRIOR_DAYS} days -> last {RECENT_DAYS} days.\n")
    keep = json.loads(KEEP_LIST_PATH.read_text())
    per_table = {t: sum(e["team_features"].values()) for t, e in result["tables"].items() if e["team_features"]}
    direct = sum(per_table.values())
    L.append(f"Production team model: {len(keep)} features. {direct} are rolling box-score stats "
             f"traced to one column below; the other {len(keep) - direct} are built from several "
             "inputs (ELO and win % / streak from `game_list` results; rest and schedule from "
             "`game_list` dates; slot / availability / impact from player impact plus the official "
             "injury report).\n")
    L.append("| Source table | Prod features traced |")
    L.append("|---|---|")
    L += [f"| `{t}` | {n} |" for t, n in sorted(per_table.items(), key=lambda x: -x[1])]
    L.append("")
    L.append("| Table | Column | Team | Prod features | Impact | Player | Serving | Site | In API now | Fill prior -> recent |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for t, e in result["tables"].items():
        api_cols = set((result["api"].get(t) or {}).get("columns") or [])
        for c, cons in sorted(e["used"].items()):
            pf = e["team_features"].get(c, 0)
            ps, rs = result["fill"].get(t, {}).get(c, (None, None))
            inapi = "yes" if c in api_cols else ("?" if e.get("error") else "**NO**")
            L.append(f"| `{t}` | `{c}` | {'x' if 'team' in cons else ''} | {pf or ''} | "
                     f"{'x' if 'impact' in cons else ''} | "
                     f"{'x' if 'player' in cons else ''} | {'x' if 'serving' in cons else ''} | "
                     f"{'x' if 'site' in cons else ''} | {inapi} | {_pct(ps)} -> {_pct(rs)} |")
    L.append("")

    L.append("## 3. Stored but unused columns (available for experiments)\n")
    L.append("| Table | Columns nothing reads yet |")
    L.append("|---|---|")
    for t, e in result["tables"].items():
        api_cols = (result["api"].get(t) or {}).get("columns") or []
        unused = [c for c in api_cols if c not in e["used"]]
        if unused and not t.startswith("schedule"):
            L.append(f"| `{t}` | {', '.join(unused)} |")
    L.append("")
    L.append("## 4. Raw response archive\n")
    L.append(f"Every fetched response is saved as received under `{result.get('archive_dir', 'data/raw_api')}` "
             "(`raw_api_archive.py`, local only). Files per endpoint and season:\n")
    arch = result.get("archive") or {}
    if arch:
        L.append("| Endpoint | Files by season |")
        L.append("|---|---|")
        for e, seasons in sorted(arch.items()):
            L.append(f"| `{e}` | " + ", ".join(f"{s}: {n}" for s, n in sorted(seasons.items())) + " |")
    else:
        L.append("(empty: the archive starts with the first ingest after 2026-11-16)")
    L.append("")
    cov = result.get("coverage") or {}
    if cov:
        n = next(iter(cov.values()))["checked"]
        L.append("## 5. Game coverage\n")
        L.append(f"Regular-season, play-in and playoff games from the last {COVERAGE_DAYS} days that are at least "
                 f"{COVERAGE_GRACE_DAYS} days old ({n} games), and the ones a table has no rows for. "
                 "Rows with a NULL game id are unpublished box scores stored as empty rows. "
                 "A gap in a table the pipeline reads raises `API_DATA_GAP`.\n")
        L.append("| Table | Read by pipeline | Games missing | NULL game id rows |")
        L.append("|---|---|---|---|")
        for t, c in sorted(cov.items()):
            read = "yes" if result["tables"].get(t, {}).get("used") else "no"
            miss = (f"{len(c['missing'])}: " + ", ".join(str(g) for g in c["missing"][:6])
                    + (" ..." if len(c["missing"]) > 6 else "")) if c["missing"] else "0"
            if t in OFTEN_EMPTY and c["missing"]:
                miss += " (often empty by nature)"
            L.append(f"| `{t}` | {read} | {miss} | {c['null_id_rows'] or 0} |")
        L.append("")
    if result["notes"]:
        L.append("## Notes\n")
        L += [f"- {n}" for n in result["notes"]]
        L.append("")
    DOC_PATH.write_text("\n".join(L), encoding="utf-8")
    print(f"report written: {DOC_PATH.relative_to(ROOT)}")


def print_summary(result: dict) -> None:
    print(f"[api_schema] nba_api {result['nba_api']}, probe game {result['probe_game']} "
          f"({result['probe_game_date']}), baseline "
          + (f"{result['baseline']['nba_api']} @ {result['baseline']['accepted_at']}" if result["baseline"] else "NONE"))
    for a in result["alerts"]:
        print(f"[api_schema] ALERT {a}")
    for n in result["notes"]:
        print(f"[api_schema] note: {n}")
    print(f"[api_schema] status: {result['status'].upper()}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--game-id", help="Probe this game instead of the latest one >= 3 days old.")
    ap.add_argument("--write-doc", action="store_true", help=f"Write {DOC_PATH.relative_to(ROOT)}.")
    ap.add_argument("--accept", action="store_true",
                    help="Make today's API column lists the accepted baseline (after reviewing the alerts).")
    ap.add_argument("--json", help="Also write the full result to this path.")
    args = ap.parse_args()
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="backslashreplace")
        except Exception:  # noqa: BLE001
            pass
    result = run_check(game_id=args.game_id)
    print_summary(result)
    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=1, default=str))
    if args.write_doc:
        write_doc(result)
    if args.accept:
        accept(result)
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
