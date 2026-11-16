"""Regenerate the generated half of docs/DATABASE_SCHEMA.md from the live local MySQL.

The hand-written part of the doc (conventions, relationships, common queries)
stays as written; everything between the GENERATED markers is rebuilt from
information_schema each run:
  * table index: category, where the table lives (local / RDS), approximate
    rows, date or season coverage, purpose, code that references it;
  * per table: columns (type, null, key) and indexes.

Purposes live in TABLE_INFO below (box-score tables are described automatically
from the importer's endpoint map). A table in the DB without a description, or
a description for a table that no longer exists, is listed under "Needs
attention" and makes `--check` exit 1. A new table gets one line here.

Usage (home PC, local MySQL; read-only):
    python scripts/gen_db_schema_doc.py            # rewrite the generated block
    python scripts/gen_db_schema_doc.py --check    # exit 1 if any table is undocumented / stale
    python scripts/gen_db_schema_doc.py --no-coverage   # skip the slower coverage queries
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DOC = ROOT / "docs" / "DATABASE_SCHEMA.md"
BEGIN = "<!-- BEGIN GENERATED: scripts/gen_db_schema_doc.py - do not edit by hand -->"
END = "<!-- END GENERATED -->"
REF_DIRS = ["data_engineering", "modeling", "orchestration", "api", "scripts", "visualization",
            "core", "web/app", "web/lib", "web/components"]
MAX_COLS_LISTED = 80

# table -> (category, where, purpose). "where" is free text; tables the home ingest
# ships to RDS are detected from home_ingest_push.py and tagged automatically.
TABLE_INFO: dict[str, tuple[str, str, str]] = {
    # --- core ---
    "game_list": ("Core", "",
                  "One row per team per game (LeagueGameFinder): result, traditional box score, "
                  "MATCHUP (`vs.` = home, `@` = away). Spine of every team feature, ELO, grading."),
    "nba_teams": ("Core", "", "Static nba_api team list (replaced each ingest)."),
    "nba_players": ("Core", "", "Static nba_api player list (replaced each ingest)."),
    # --- availability & context ---
    "historical_injury_report": ("Availability & context", "",
                                 "Official NBA pre-game injury report, one row per player per report "
                                 "date (PDF scrape, `historical_injury_report.py`). Training + serving "
                                 "availability source (E7, E28)."),
    "team_lineup_snapshots": ("Availability & context", "",
                              "Team lineup aggregates from LeagueDashLineups per snapshot date "
                              "(`lineup_features.py`, home only). E11 features, off in production."),
    "playoff_series_context": ("Availability & context", "local + RDS (computed)",
                               "Series state per played playoff game (`series_context.py`). Not in "
                               "the production feature set."),
    "vegas_lines": ("Availability & context", "local + RDS (VegasLinesStage)",
                    "Market spreads/totals/moneylines (ESPN odds + Kaggle history). /accuracy "
                    "market benchmark and player-model group G."),
    "gravity_leaders_daily": ("Availability & context", "local only",
                              "Daily snapshot of GravityLeaders season-to-date player gravity "
                              "(`gravity_snapshot.py`). Proposals E31/E32/P8."),
    "league_schedule": ("Availability & context", "RDS only",
                        "League schedule (ScheduleLeagueV2) shipped by the home ingest, replaced "
                        "each drop; the cloud's schedule source."),
    "live_scores": ("Availability & context", "RDS only",
                    "ESPN final scores polled every 30 min (`espn_score_poller.py`); grading and "
                    "the site before game_list arrives."),
    # --- features & models ---
    "features": ("Features & models", "local + RDS (FeaturesStage)",
                 "Versioned team-game feature snapshots, PK (feature_set_version, GAME_ID); "
                 "written by `feature_engineering.py` via `core/features_io.py`. Columns "
                 "auto-evolve; production selection is `core/features.py`."),
    "feature_set_versions": ("Features & models", "local + RDS", "Metadata per feature snapshot."),
    "feature_set_current": ("Features & models", "local + RDS",
                            "Single-row pointer to the live feature_set_version."),
    "team_elo_pregame": ("Features & models", "local + RDS (weekly)",
                         "Pre-game ELO per game (`compute_elo.py`). Serving computes ELO in memory "
                         "(E28); the local copy can be stale."),
    "player_impact": ("Features & models", "local + RDS (PlayerImpactStage)",
                      "Per player per compute_date impact estimates (with/without), feeding the "
                      "slot / availability / impact features."),
    "model_registry": ("Features & models", "local + RDS",
                       "One row per trained / validated / experiment model bundle: lineage, "
                       "metrics, bundle path (`core/model_registry.py`)."),
    # --- predictions ---
    "model_predictions": ("Predictions", "local + RDS (RDS = public record)",
                          "Team game predictions per model plus graded outcomes "
                          "(`modeling/prediction_tracker.py`); the public track record."),
    "player_predictions": ("Predictions", "local + RDS", "Nightly player projections (/players)."),
    # --- experiments & bookkeeping ---
    "experiments": ("Experiments", "local only",
                    "Experiment-loop header rows (`core/experiment_db.py`)."),
    "experiment_results": ("Experiments", "local only",
                           "Per (experiment, stage, arm, model, window, seed) metrics."),
    "experiment_comparisons": ("Experiments", "local only", "Paired-test rows arm vs baseline."),
    "importedgamesmemory": ("Ingest bookkeeping", "local only",
                            "Per-game import status per box-score table (1 ok, 2 API had no data, "
                            "0 failed) + number_reattempts; drives the importer's retries."),
}
CATEGORY_ORDER = ["Core", "Box score - team", "Box score - player", "Game summary",
                  "Availability & context", "Features & models", "Predictions", "Experiments",
                  "Ingest bookkeeping", "Undocumented"]
DATE_COLS = ["GAME_DATE", "game_date", "snapshot_date", "compute_date", "gameDate",
             "GAME_DATE_EST", "prediction_timestamp", "created_at", "trained_at", "started_at"]


def auto_info(table: str) -> tuple[str, str, str] | None:
    """Descriptions for the box-score tables, from the importer's endpoint map."""
    from data_engineering.api_schema_check import ENDPOINT_FRAMES
    for _, cls, frames in ENDPOINT_FRAMES:
        for i, t in frames.items():
            if t == table:
                if "summary" in t:
                    cat = "Game summary"
                elif t.endswith("_player"):
                    cat = "Box score - player"
                else:
                    cat = "Box score - team"
                what = {"_player": "per player per game", "_team": "per team per game",
                        "_bench": "starters/bench split per team per game"}.get(
                    "_" + t.rsplit("_", 1)[-1], "per game")
                return cat, "", (f"`{cls}` frame {i}, {what}. Column usage and fill rates: "
                                 f"[api_schema_report.md](api_schema_report.md).")
    return None


def shipped_tables() -> set[str]:
    from data_engineering import home_ingest_push as h
    return set(h.GAME_TABLES) | set(h.FULL_TABLES) | {h.INJURY_TABLE, "game_list", "league_schedule"}


def references(tables: list[str]) -> dict[str, list[str]]:
    files = []
    for d in REF_DIRS:
        base = ROOT / d
        if base.exists():
            files += [p for p in base.rglob("*") if p.suffix in (".py", ".ts", ".tsx", ".sql")
                      and "node_modules" not in p.parts and p.name != "gen_db_schema_doc.py"]
    texts = {str(p.relative_to(ROOT)).replace("\\", "/"): p.read_text(encoding="utf-8", errors="ignore")
             for p in files}
    # SQL-style references only (FROM/JOIN/INTO/UPDATE/TABLE t, or the name quoted),
    # so tables with plain-English names ("features", "experiments") don't match prose.
    out = {}
    for t in tables:
        pat = re.compile(rf"(?:FROM|JOIN|INTO|UPDATE|TABLE)\s+(?:nba_data\.)?`?{re.escape(t)}\b"
                         rf"|['\"`]{re.escape(t)}['\"`]", re.I)
        out[t] = sorted(f for f, s in texts.items() if pat.search(s))
    return out


def approx(n) -> str:
    if n is None:
        return "-"
    n = int(n)
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        return f"~{n / 1000:.0f}k"
    return f"~{n / 1_000_000:.1f}M"


def season_label(yy: int) -> str:
    y = 1900 + yy if yy >= 50 else 2000 + yy
    return f"{y}-{(y + 1) % 100:02d}"


def coverage(engine, table: str, cols: list[str]) -> str:
    """Date range, or season range from the game id for box-score tables."""
    with engine.connect() as c:
        for dc in DATE_COLS:
            if dc in cols:
                lo, hi = c.execute(sa.text(f"SELECT MIN(`{dc}`), MAX(`{dc}`) FROM `{table}`")).one()
                if lo is not None:
                    return f"{str(lo)[:10]} → {str(hi)[:10]}"
        gid = next((g for g in ("gameId", "GAME_ID", "game_id") if g in cols), None)
        if gid:
            yys = [int(r[0]) for r in c.execute(sa.text(
                f"SELECT DISTINCT SUBSTRING(LPAD(`{gid}`, 10, '0'), 4, 2) FROM `{table}`")) if r[0] and r[0].isdigit()]
            if yys:
                ordered = sorted(yys, key=lambda y: y + (1900 if y >= 50 else 2000))
                return f"{season_label(ordered[0])} → {season_label(ordered[-1])}"
    return "-"


def build(engine, with_coverage: bool) -> tuple[str, list[str]]:
    db = engine.url.database
    with engine.connect() as c:
        tables = pd.read_sql(sa.text(
            "SELECT TABLE_NAME, TABLE_ROWS, DATA_LENGTH + INDEX_LENGTH AS bytes FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = :d AND TABLE_TYPE = 'BASE TABLE' ORDER BY TABLE_NAME"), c, params={"d": db})
        cols = pd.read_sql(sa.text(
            "SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_KEY FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = :d ORDER BY TABLE_NAME, ORDINAL_POSITION"), c, params={"d": db})
        idx = pd.read_sql(sa.text(
            "SELECT TABLE_NAME, INDEX_NAME, GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS cols, "
            "MIN(NON_UNIQUE) AS non_unique FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = :d "
            "GROUP BY TABLE_NAME, INDEX_NAME ORDER BY TABLE_NAME, INDEX_NAME"), c, params={"d": db})
    names = list(tables.TABLE_NAME)
    shipped = shipped_tables()
    refs = references(names + [t for t in TABLE_INFO if t not in names])

    info, undocumented = {}, []
    for t in names:
        i = TABLE_INFO.get(t) or auto_info(t)
        if i is None:
            undocumented.append(t)
            i = ("Undocumented", "", "**No description: add one to TABLE_INFO in scripts/gen_db_schema_doc.py.**")
        cat, where, purpose = i
        if not where:
            where = "local → RDS (home ingest)" if t in shipped else "local only"
        info[t] = (cat, where, purpose)
    remote_only = [t for t, (_, w, _) in TABLE_INFO.items() if t not in names and "RDS only" in w]
    stale = [t for t in TABLE_INFO if t not in names and t not in remote_only]
    # tables created by a pending SQL script are expected to be missing for a while
    pending = [t for t in stale if (ROOT / "sql" / f"create_{t}.sql").exists()]
    stale = [t for t in stale if t not in pending]

    L = [BEGIN, ""]
    L.append(f"*Generated {date.today().isoformat()} from local MySQL `{db}`: {len(names)} tables, "
             f"{approx(tables.TABLE_ROWS.sum())} rows, "
             f"{tables.bytes.sum() / 1e9:.1f} GB. RDS-only tables are listed without columns.*\n")
    problems = []
    if undocumented:
        problems.append(f"Tables without a description: {', '.join(f'`{t}`' for t in undocumented)}")
    if stale:
        problems.append(f"Described but not in the DB (dropped or renamed?): {', '.join(f'`{t}`' for t in stale)}")
    if pending:
        problems.append(f"Not created yet (CREATE TABLE in sql/): {', '.join(f'`{t}`' for t in pending)}")
    if problems:
        L.append("**Needs attention**\n")
        L += [f"- {p}" for p in problems]
        L.append("")

    with engine.connect() as c:  # exact counts (InnoDB TABLE_ROWS estimates can be off by 25%+)
        tables["TABLE_ROWS"] = [c.execute(sa.text(f"SELECT COUNT(*) FROM `{t}`")).scalar() for t in names]
    rows = tables.set_index("TABLE_NAME")
    L.append("## Table index\n")
    L.append("| Table | Where | Rows | Coverage | Purpose | Referenced in |")
    L.append("|---|---|---|---|---|---|")
    covs = {}
    for cat in CATEGORY_ORDER:
        members = sorted([t for t in names if info[t][0] == cat] +
                         [t for t in remote_only + pending if TABLE_INFO[t][0] == cat])
        if not members:
            continue
        L.append(f"| **{cat}** | | | | | |")
        for t in members:
            if t in names:
                tcols = list(cols.loc[cols.TABLE_NAME == t, "COLUMN_NAME"])
                covs[t] = coverage(engine, t, tcols) if with_coverage else "-"
                where, purpose = info[t][1], info[t][2]
                n = approx(rows.loc[t, "TABLE_ROWS"])
            else:
                where, purpose, n = TABLE_INFO[t][1], TABLE_INFO[t][2], "-"
                covs[t] = "-"
                if t in pending:
                    where += " (not created yet)"
            r = refs.get(t, [])
            ref = (", ".join(f"`{f}`" for f in r[:4]) + (f" +{len(r) - 4}" if len(r) > 4 else "")) if r else "-"
            name = f"[`{t}`](#{t})" if t in names else f"`{t}`"
            L.append(f"| {name} | {where} | {n} | {covs[t]} | {purpose} | {ref} |")
    L.append("")

    L.append("## Columns and indexes\n")
    for t in names:
        tc = cols[cols.TABLE_NAME == t]
        L.append(f'<a id="{t}"></a>\n<details><summary><code>{t}</code> - {len(tc)} columns, '
                 f'{approx(rows.loc[t, "TABLE_ROWS"])} rows</summary>\n')
        L.append("| Column | Type | Null | Key |")
        L.append("|---|---|---|---|")
        for _, c in tc.head(MAX_COLS_LISTED).iterrows():
            L.append(f"| `{c.COLUMN_NAME}` | {c.COLUMN_TYPE} | {'yes' if c.IS_NULLABLE == 'YES' else 'no'} | {c.COLUMN_KEY or ''} |")
        if len(tc) > MAX_COLS_LISTED:
            L.append(f"| ... {len(tc) - MAX_COLS_LISTED} more | | | |")
        ti = idx[idx.TABLE_NAME == t]
        if len(ti):
            L.append("")
            L.append("Indexes: " + "; ".join(
                f"`{r.INDEX_NAME}` ({r.cols}){' unique' if not int(r.non_unique) else ''}" for r in ti.itertuples()))
        L.append("\n</details>\n")
    L.append(END)
    return "\n".join(L), problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="Don't write; exit 1 if anything needs attention.")
    ap.add_argument("--no-coverage", action="store_true", help="Skip date/season coverage queries.")
    args = ap.parse_args()
    from core.db import get_engine
    block, problems = build(get_engine(), with_coverage=not args.no_coverage)
    hard = [p for p in problems if not p.startswith("Not created yet")]
    if args.check:
        for p in problems:
            print(p)
        return 1 if hard else 0
    text = DOC.read_text(encoding="utf-8")
    if BEGIN in text and END in text:
        text = text[:text.index(BEGIN)] + block + text[text.index(END) + len(END):]
    else:
        text = text.rstrip() + "\n\n" + block + "\n"
    DOC.write_text(text, encoding="utf-8")
    print(f"wrote {DOC.relative_to(ROOT)}" + (f"; needs attention: {len(problems)} item(s)" if problems else ""))
    for p in problems:
        print("  " + p)
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
