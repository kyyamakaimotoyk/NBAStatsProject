"""
E11 — LeagueDashLineups 5-man synergy features.

For each team-game, attaches features derived from the team's most-used 5-man
lineups for that season (point-in-time as of the game date).

Why E11 exists
--------------
Our existing player-impact features are *additive* — sum of individual player
projections weighted by availability. Two teams with identical player rosters
have identical sums even if one runs cohesive starter-heavy units and the
other rotates 12 deep. That misses cohesion, bench-unit dropoff, and lineup
synergies that nba.com's LeagueDashLineups endpoint exposes directly.

API characteristics
-------------------
- `LeagueDashLineups` with `Advanced/PerGame/5-man` returns ~2000 rows per
  season (after at least a month of games). Each row is one 5-man combo with
  NetRtg/OffRtg/DefRtg/Pace/TS%/etc + minutes played.
- Calling it with no date_to gives season-to-date. To make features
  point-in-time-correct for walk-forward, we snapshot at month-end boundaries
  and look up the previous-month snapshot for each game.
- One API call per (season, month_end). ~30-40 calls total to cover seasons
  2022-2026, cached to MySQL `team_lineup_snapshots`.

Features generated per (team, snapshot_date)
--------------------------------------------
- LINEUP_TOP_MIN          — minutes of the most-used 5-man combo
- LINEUP_TOP_NET_RTG      — NetRtg of that combo
- LINEUP_TOP_OFF_RTG      — OffRtg of that combo
- LINEUP_TOP_DEF_RTG      — DefRtg of that combo
- LINEUP_TOP_PACE         — Pace of that combo
- LINEUP_TOP_TS_PCT       — TS% of that combo
- LINEUP_TOP5_AVG_NET_RTG — avg NetRtg over team's top-5 combos by minutes
- LINEUP_TOP5_MIN_SHARE   — % of total lineup-minutes consumed by top 5
- LINEUP_N_ACTIVE         — # of distinct combos with >5 minutes (lineup
                            consolidation — low = "rides the starters")

Usage
-----
    python data_engineering/lineup_features.py --season 2025-26
    python data_engineering/lineup_features.py --all-seasons   # 2022-23 → current
"""
from __future__ import annotations

import sys as _sys
import os as _os
_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _PROJECT_ROOT)
if _os.getcwd() != _PROJECT_ROOT:
    _os.chdir(_PROJECT_ROOT)

import argparse
import time
from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd
from sqlalchemy import text

from core.db import get_engine


ENSURE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS team_lineup_snapshots (
    id INT AUTO_INCREMENT PRIMARY KEY,
    season VARCHAR(10) NOT NULL,
    snapshot_date DATE NOT NULL,
    team_id BIGINT NOT NULL,
    team_abbrev VARCHAR(5) NULL,
    lineup_top_min FLOAT NULL,
    lineup_top_net_rtg FLOAT NULL,
    lineup_top_off_rtg FLOAT NULL,
    lineup_top_def_rtg FLOAT NULL,
    lineup_top_pace FLOAT NULL,
    lineup_top_ts_pct FLOAT NULL,
    lineup_top5_avg_net_rtg FLOAT NULL,
    lineup_top5_min_share FLOAT NULL,
    lineup_n_active INT NULL,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_snap (season, snapshot_date, team_id),
    INDEX idx_snap (snapshot_date),
    INDEX idx_team (team_id)
)
"""


def month_end_dates(season: str) -> list:
    """Return last-day-of-month dates that fall within the regular season.
    Season string is e.g. '2025-26' → Oct 2025 → Jun 2026."""
    start_year = int(season.split('-')[0])
    months = [
        (start_year, 10), (start_year, 11), (start_year, 12),
        (start_year + 1, 1), (start_year + 1, 2), (start_year + 1, 3),
        (start_year + 1, 4), (start_year + 1, 5), (start_year + 1, 6),
    ]
    out = []
    today = date.today()
    for y, m in months:
        if m == 12:
            last = date(y, 12, 31)
        else:
            last = date(y, m + 1, 1) - timedelta(days=1)
        if last <= today:
            out.append(last)
    return out


def fetch_lineup_snapshot(season: str, date_to: date, max_retries: int = 3) -> pd.DataFrame:
    """One API call per (season, date_to). Returns one row per (team, snapshot_date).
    Returns empty DataFrame if the API returns no data (early-season call)."""
    from nba_api.stats.endpoints import leaguedashlineups
    date_str = date_to.strftime('%m/%d/%Y')

    last_err = None
    for attempt in range(max_retries):
        try:
            ld = leaguedashlineups.LeagueDashLineups(
                season=season,
                season_type_all_star='Regular Season',
                measure_type_detailed_defense='Advanced',
                per_mode_detailed='PerGame',
                group_quantity='5',
                date_to_nullable=date_str,
                timeout=60,
            )
            df = ld.get_data_frames()[0]
            break
        except Exception as e:
            last_err = e
            print(f'    [retry {attempt+1}] {type(e).__name__}: {str(e)[:80]}')
            time.sleep(2 + attempt * 2)
    else:
        print(f'    [FAIL] {season} {date_str}: {last_err}')
        return pd.DataFrame()

    if df.empty:
        return pd.DataFrame()

    rows = []
    for tid, grp in df.groupby('TEAM_ID'):
        sorted_grp = grp.sort_values('MIN', ascending=False)
        top = sorted_grp.iloc[0]
        top5 = sorted_grp.head(5)
        total_min = sorted_grp['MIN'].sum()
        rows.append({
            'season': season,
            'snapshot_date': date_to,
            'team_id': int(tid),
            'team_abbrev': top['TEAM_ABBREVIATION'],
            'lineup_top_min': float(top['MIN']),
            'lineup_top_net_rtg': float(top['NET_RATING']),
            'lineup_top_off_rtg': float(top['OFF_RATING']),
            'lineup_top_def_rtg': float(top['DEF_RATING']),
            'lineup_top_pace': float(top['PACE']),
            'lineup_top_ts_pct': float(top['TS_PCT']),
            'lineup_top5_avg_net_rtg': float(top5['NET_RATING'].mean()),
            'lineup_top5_min_share': float(top5['MIN'].sum() / total_min) if total_min > 0 else 0.0,
            'lineup_n_active': int((sorted_grp['MIN'] > 5).sum()),
        })
    return pd.DataFrame(rows)


def write_snapshot(engine, snap_df: pd.DataFrame) -> int:
    if snap_df.empty:
        return 0
    with engine.connect() as c:
        c.execute(text(ENSURE_TABLE_SQL))
        c.commit()
        result = c.execute(text("""
            INSERT IGNORE INTO team_lineup_snapshots (
                season, snapshot_date, team_id, team_abbrev,
                lineup_top_min, lineup_top_net_rtg, lineup_top_off_rtg,
                lineup_top_def_rtg, lineup_top_pace, lineup_top_ts_pct,
                lineup_top5_avg_net_rtg, lineup_top5_min_share, lineup_n_active
            ) VALUES (
                :season, :snapshot_date, :team_id, :team_abbrev,
                :lineup_top_min, :lineup_top_net_rtg, :lineup_top_off_rtg,
                :lineup_top_def_rtg, :lineup_top_pace, :lineup_top_ts_pct,
                :lineup_top5_avg_net_rtg, :lineup_top5_min_share, :lineup_n_active
            )
        """), snap_df.to_dict('records'))
        c.commit()
        return result.rowcount


def run_season(engine, season: str, sleep: float = 1.5) -> int:
    print(f'[{season}] Generating month-end snapshots...')
    dates_ = month_end_dates(season)
    print(f'  {len(dates_)} snapshot dates: {[d.isoformat() for d in dates_]}')

    total = 0
    for i, d in enumerate(dates_, 1):
        snap = fetch_lineup_snapshot(season, d)
        n = write_snapshot(engine, snap)
        total += n
        print(f'  [{i}/{len(dates_)}] {d}: {len(snap)} teams, {n} new rows')
        time.sleep(sleep)
    print(f'  Season {season} done: {total} rows in team_lineup_snapshots')
    return total


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--season', default=None,
                   help='NBA season (e.g. 2025-26). Default: current.')
    p.add_argument('--all-seasons', action='store_true',
                   help='Process seasons 2021-22 → current.')
    p.add_argument('--sleep', type=float, default=1.5,
                   help='Seconds between API calls (default 1.5)')
    args = p.parse_args()

    eng = get_engine()

    if args.all_seasons:
        seasons = ['2021-22', '2022-23', '2023-24', '2024-25', '2025-26']
    elif args.season:
        seasons = [args.season]
    else:
        # Default to current
        today = date.today()
        yr = today.year if today.month >= 10 else today.year - 1
        seasons = [f'{yr}-{str(yr+1)[2:]}']

    grand = 0
    for s in seasons:
        grand += run_season(eng, s, sleep=args.sleep)
    print(f'\nDone. {grand:,} total rows across {len(seasons)} season(s).')


if __name__ == '__main__':
    main()
