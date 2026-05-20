"""
Historical NBA injury report scraper.

Pulls the league's official pre-game injury reports (PDFs hosted on
ak-static.cms.nba.com) via the `nbainjuries` PyPI package and inserts them into a
`historical_injury_report` MySQL table — one row per (game_date, team, player).

Why this exists
---------------
For training-data correctness: the project's `*_SLOT_X_AVAILABLE` features
currently derive a player's availability from the POST-game boxscore (did they
appear with non-DNP minutes?). That's a leak — the training model sees pre-game
info it wouldn't have at real prediction time. The fix is to source availability
from the league's official PRE-game injury report.

For backfilled predictions: `predict_games.py --start-date X` re-runs predictions
for past dates with `--auto-injuries` force-disabled (because the live ESPN feed
isn't point-in-time). With the new table populated, we can replace the live feed
with a point-in-time lookup against `historical_injury_report`, so backfilled
predictions match what the model would have seen if it had been run live.

Strategy
--------
1. For each distinct game date in `game_list` within our window, try a list of
   late-day timestamps (latest first). Take the LATEST report that's valid. NBA
   publishes hourly through game day; the 30-min-before-tipoff version is the
   "final" report and the closest analogue to live ESPN.
2. Parse the report (the package wraps tabula-py for PDF table extraction).
3. Resolve team names and player names against existing `nba_teams` / `nba_players`
   tables. Unresolved rows still get inserted with NULL ids — feature lookup
   downstream can fall back to fuzzy name match if needed.
4. Insert with `INSERT IGNORE` on the unique key (game_date, team_name, player_name)
   so the script is fully resumable.

Usage
-----
    python data_engineering/historical_injury_scraper.py                  # 2022-01-01 → today
    python data_engineering/historical_injury_scraper.py --start 2024-10-01 --end 2024-10-31
    python data_engineering/historical_injury_scraper.py --limit 5        # test mode (first 5 dates)
"""
from __future__ import annotations

# Project-root bootstrap
import sys as _sys
import os as _os
_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _PROJECT_ROOT)
if _os.getcwd() != _PROJECT_ROOT:
    _os.chdir(_PROJECT_ROOT)

import argparse
import time
from datetime import datetime, date, timedelta
from typing import Optional

import pandas as pd
from sqlalchemy import text

from core.db import get_engine

try:
    from nbainjuries import injury
    NBAINJURIES_AVAILABLE = True
except ImportError:
    NBAINJURIES_AVAILABLE = False
    print("ERROR: nbainjuries package not installed. Run: pip install nbainjuries")


# ============================================================================
# URL FORMAT HANDLING (NBA changed convention starting 2025-12-22)
# ============================================================================
# The nbainjuries package's gen_url() uses the OLD format (hourly granularity):
#   Injury-Report_YYYY-MM-DD_HHPM.pdf   (e.g., '08PM')
# Starting 2025-12-22 the NBA switched to 15-min granularity:
#   Injury-Report_YYYY-MM-DD_HH_MMPM.pdf   (e.g., '08_30PM')
# The two formats do not co-exist — old returns 200 for pre-cutoff dates only and
# new returns 200 for post-cutoff dates only. We monkey-patch _gen_url to support
# both, trying the format most likely for the date first.

if NBAINJURIES_AVAILABLE:
    _ORIGINAL_GEN_URL = injury._gen_url

    def _gen_url_old_format(timestamp):
        """Hourly format used by the NBA through 2025-12-21."""
        URLstem_date = timestamp.date().strftime('%Y-%m-%d')
        URLstem_time = (timestamp - timedelta(minutes=30)).time().strftime('%I%p')
        return injury._constants.urlstem_injreppdf.replace('*', URLstem_date + '_' + URLstem_time)

    def _gen_url_new_format(timestamp):
        """15-min-granularity format used by the NBA from 2025-12-22 onward."""
        URLstem_date = timestamp.date().strftime('%Y-%m-%d')
        URLstem_time = (timestamp - timedelta(minutes=30)).time().strftime('%I_%M%p')
        return injury._constants.urlstem_injreppdf.replace('*', URLstem_date + '_' + URLstem_time)

NEW_FORMAT_CUTOFF = date(2025, 12, 22)


# ============================================================================
# SCHEMA
# ============================================================================

ENSURE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS historical_injury_report (
    id INT AUTO_INCREMENT PRIMARY KEY,
    game_date DATE NOT NULL,
    report_timestamp DATETIME NOT NULL,
    team_name VARCHAR(50) NOT NULL,
    team_id BIGINT NULL,
    matchup VARCHAR(20) NULL,
    player_name VARCHAR(100) NOT NULL,
    player_id BIGINT NULL,
    status VARCHAR(20) NOT NULL,
    reason TEXT NULL,
    source VARCHAR(50) NOT NULL DEFAULT 'nba_official_pdf',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_game_date (game_date),
    INDEX idx_team_player (team_id, player_id),
    INDEX idx_status (status),
    UNIQUE KEY unique_player_game (game_date, team_name, player_name)
)
"""


# ============================================================================
# REPORT FETCHING
# ============================================================================

# Late-evening hours probed in order — newest probed first so the LATEST report
# (closest to the "final" league report published ~30 min before tipoff) wins.
ET_HOURS_TO_TRY = [21, 20, 19, 18, 17, 16, 14, 12]
# For NEW format only: also probe 15-min slots within each hour.
ET_MINUTES_TO_TRY = [30, 0, 45, 15]  # latest first


def _try_format(game_date: date, gen_url_fn, hours, minutes=None) -> Optional[tuple]:
    """Probe candidate timestamps under one URL format. Returns (timestamp, df) or None."""
    injury._gen_url = gen_url_fn  # monkey-patch the package's URL generator
    try:
        for hr in hours:
            mins_list = minutes if minutes is not None else [0]
            for mn in mins_list:
                ts = datetime.combine(game_date, datetime.min.time().replace(hour=hr, minute=mn))
                try:
                    if injury.check_reportvalid(ts):
                        df = injury.get_reportdata(ts, return_df=True)
                        if df is not None and len(df) > 0:
                            return ts, df
                except Exception:
                    continue
    finally:
        injury._gen_url = _ORIGINAL_GEN_URL  # restore
    return None


def fetch_latest_report_for_date(game_date: date) -> Optional[tuple]:
    """Try both URL formats; return (timestamp, df) of the latest valid report,
    or None if neither format yields a parseable report for any candidate timestamp.

    Strategy: pick the most-likely format first based on `game_date` vs the
    NEW_FORMAT_CUTOFF, then fall back to the other format. Saves wasted requests
    in the common case where the date's format is predictable.
    """
    if not NBAINJURIES_AVAILABLE:
        return None
    if game_date >= NEW_FORMAT_CUTOFF:
        # Try new format (hourly + 15-min) first; fall back to old just in case
        result = _try_format(game_date, _gen_url_new_format, ET_HOURS_TO_TRY, ET_MINUTES_TO_TRY)
        if result is not None:
            return result
        return _try_format(game_date, _gen_url_old_format, ET_HOURS_TO_TRY)
    else:
        # Old format covers everything pre-cutoff; only try new format as a safety net
        result = _try_format(game_date, _gen_url_old_format, ET_HOURS_TO_TRY)
        if result is not None:
            return result
        return _try_format(game_date, _gen_url_new_format, ET_HOURS_TO_TRY, ET_MINUTES_TO_TRY)


# ============================================================================
# RESOLUTION (team name / player name -> integer IDs)
# ============================================================================

def build_team_resolver(engine) -> dict:
    """{team_full_name: team_id}. Injury reports use full names like 'Sacramento Kings'."""
    with engine.connect() as c:
        rows = c.execute(text("SELECT id, full_name FROM nba_teams")).fetchall()
    return {r[1]: r[0] for r in rows}


def build_player_resolver(engine) -> dict:
    """{(first_lower, last_lower): player_id}. Multiple matches → prefer active + recent."""
    with engine.connect() as c:
        rows = c.execute(text("""
            SELECT id, first_name, last_name, is_active
            FROM nba_players
            ORDER BY is_active DESC, id DESC
        """)).fetchall()
    resolver = {}
    for r in rows:
        if not r[1] or not r[2]:
            continue
        key = (r[1].lower().strip(), r[2].lower().strip())
        if key not in resolver:
            resolver[key] = r[0]
    return resolver


def resolve_player(name, resolver: dict) -> Optional[int]:
    """Injury report format is 'Last, First'. Returns player_id or None.

    Defensive against pandas NaN floats / non-string values that pdfplumber can return
    when a row is partially blank — `not name` doesn't short-circuit NaN (which is truthy).
    """
    if name is None or not isinstance(name, str) or ',' not in name:
        return None
    parts = name.split(',', 1)
    last = parts[0].strip().lower()
    first = parts[1].strip().lower()
    # Direct match
    pid = resolver.get((first, last))
    if pid is not None:
        return pid
    # Suffix-stripped fallback (Jr., Sr., II, III)
    for suffix in [' jr.', ' sr.', ' ii', ' iii']:
        if last.endswith(suffix):
            pid = resolver.get((first, last[:-len(suffix)].strip()))
            if pid is not None:
                return pid
    return None


# ============================================================================
# DB OPS
# ============================================================================

def get_game_dates_to_scrape(engine, start_date: date, end_date: date) -> list:
    """Distinct game_dates in game_list within [start, end], chronological."""
    with engine.connect() as c:
        rows = c.execute(text("""
            SELECT DISTINCT DATE(GAME_DATE) AS d
            FROM game_list
            WHERE GAME_DATE >= :start AND GAME_DATE <= :end
            ORDER BY d
        """), {'start': start_date.isoformat(), 'end': end_date.isoformat()}).fetchall()
    return [r[0].date() if hasattr(r[0], 'date') else r[0] for r in rows]


def get_already_scraped_dates(engine) -> set:
    with engine.connect() as c:
        rows = c.execute(text("SELECT DISTINCT game_date FROM historical_injury_report")).fetchall()
    return {r[0] for r in rows}


def insert_report_rows(engine, df, game_date, report_ts, team_resolver, player_resolver):
    """Bulk insert rows from one report. Returns (inserted, n_team_resolved, n_player_resolved)."""
    if df is None or len(df) == 0:
        return 0, 0, 0

    rows_to_insert = []
    n_team_resolved = 0
    n_player_resolved = 0

    def _clean(v):
        """Coerce NaN/None to empty string; keep real strings as-is."""
        if v is None:
            return ''
        if isinstance(v, float):
            # pandas reads blank PDF cells as NaN floats
            return '' if pd.isna(v) else str(v)
        return str(v).strip()

    for _, row in df.iterrows():
        team_name = _clean(row.get('Team'))
        team_id = team_resolver.get(team_name) if team_name else None
        if team_id is not None:
            n_team_resolved += 1

        player_name = _clean(row.get('Player Name'))
        if not player_name:
            # Skip blank rows entirely — no point inserting "" player names
            continue
        player_id = resolve_player(player_name, player_resolver)
        if player_id is not None:
            n_player_resolved += 1

        status = _clean(row.get('Current Status')) or 'Unknown'
        rows_to_insert.append({
            'game_date': game_date,
            'report_timestamp': report_ts,
            'team_name': team_name,
            'team_id': team_id,
            'matchup': _clean(row.get('Matchup')) or None,
            'player_name': player_name,
            'player_id': player_id,
            'status': status,
            'reason': _clean(row.get('Reason')) or None,
        })

    if not rows_to_insert:
        return 0, 0, 0

    sql = text("""
        INSERT IGNORE INTO historical_injury_report
            (game_date, report_timestamp, team_name, team_id, matchup,
             player_name, player_id, status, reason)
        VALUES
            (:game_date, :report_timestamp, :team_name, :team_id, :matchup,
             :player_name, :player_id, :status, :reason)
    """)
    with engine.connect() as c:
        result = c.execute(sql, rows_to_insert)
        c.commit()
        inserted = result.rowcount

    return inserted, n_team_resolved, n_player_resolved


# ============================================================================
# MAIN
# ============================================================================

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--start-date', dest='start_date', default='2022-01-01',
                   help='First game date to scrape (default 2022-01-01)')
    p.add_argument('--end-date', dest='end_date', default=date.today().isoformat(),
                   help='Last game date to scrape (default today)')
    p.add_argument('--limit', type=int, default=None,
                   help='Test mode: only scrape the first N dates (after --skip-existing)')
    p.add_argument('--no-skip-existing', action='store_true',
                   help='Re-scrape dates already in the table (default: skip)')
    p.add_argument('--sleep', type=float, default=0.0,
                   help='Seconds to sleep between requests (default 0; bump if NBA throttles)')
    args = p.parse_args()

    if not NBAINJURIES_AVAILABLE:
        print("Cannot proceed without nbainjuries; install it first.")
        return 1

    start = pd.to_datetime(args.start_date).date()
    end = pd.to_datetime(args.end_date).date()

    eng = get_engine()

    print(f'[setup] Ensuring historical_injury_report table exists...')
    with eng.connect() as c:
        c.execute(text(ENSURE_TABLE_SQL))
        c.commit()

    print(f'[setup] Building team/player resolvers...')
    team_resolver = build_team_resolver(eng)
    player_resolver = build_player_resolver(eng)
    print(f'         {len(team_resolver)} teams, {len(player_resolver)} players in lookup')

    already_scraped = set() if args.no_skip_existing else get_already_scraped_dates(eng)
    print(f'         {len(already_scraped)} game_dates already in table (will skip)')

    all_dates = get_game_dates_to_scrape(eng, start, end)
    dates_to_do = [d for d in all_dates if d not in already_scraped]
    if args.limit:
        dates_to_do = dates_to_do[:args.limit]

    print(f'[scrape] {len(all_dates)} total game dates in range {start}..{end}')
    print(f'[scrape] {len(dates_to_do)} dates to scrape now')
    print()

    total_inserted = 0
    total_resolved_team = 0
    total_resolved_player = 0
    total_rows = 0
    failed_dates = []

    start_ts = time.time()
    for i, d in enumerate(dates_to_do, 1):
        print(f'[{i:4d}/{len(dates_to_do)}] {d} ', end='', flush=True)
        try:
            result = fetch_latest_report_for_date(d)
            if result is None:
                print('-- no report found, skipping')
                failed_dates.append(d)
                continue
            ts, df = result
            inserted, rt, rp = insert_report_rows(eng, df, d, ts, team_resolver, player_resolver)
            total_inserted += inserted
            total_resolved_team += rt
            total_resolved_player += rp
            total_rows += len(df)
            elapsed = time.time() - start_ts
            rate = i / elapsed if elapsed > 0 else 0
            print(f'-> ts={ts.strftime("%H:%M")} rows={len(df)} inserted={inserted} '
                  f'res(team/player)={rt}/{rp} | {rate:.2f} dates/sec')
        except Exception as e:
            print(f'-- ERROR: {type(e).__name__}: {str(e)[:80]}')
            failed_dates.append(d)
        if args.sleep > 0:
            time.sleep(args.sleep)

    print()
    print(f'=== Done ===')
    print(f'Dates with successful scrape: {len(dates_to_do) - len(failed_dates)}/{len(dates_to_do)}')
    print(f'Rows inserted: {total_inserted} (of {total_rows} rows in reports)')
    if total_rows > 0:
        print(f'Resolution rate: '
              f'team {total_resolved_team}/{total_rows} ({total_resolved_team/total_rows*100:.1f}%), '
              f'player {total_resolved_player}/{total_rows} ({total_resolved_player/total_rows*100:.1f}%)')
    if failed_dates:
        print(f'Failed dates ({len(failed_dates)}): '
              f'{failed_dates[:5]}{"..." if len(failed_dates) > 5 else ""}')


if __name__ == '__main__':
    main()
