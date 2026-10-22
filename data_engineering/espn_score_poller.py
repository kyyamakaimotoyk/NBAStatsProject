"""
ESPN final-score poller — the cloud half of the hybrid ingest.

stats.nba.com hard-blocks AWS IPs, so box scores (game_list + the boxscore*
tables the models train on) still arrive once a day via the home drop
(home_ingest_push.py -> S3 -> s3_ingest_loader). That left grading and the
site's final scores ~a day behind the games. ESPN's public scoreboard is NOT
blocked from Fargate (vegas_lines_espn.py and the injury fetch already call it
every pipeline run), so this poller runs every 30 min during the slate and:

    1. fetches the ESPN scoreboard for yesterday + today (US Eastern dates),
    2. matches each event to our NBA game_id via model_predictions
       (game_date + home/away abbreviation),
    3. upserts status + score into `live_scores` (its own table — game_list
       stays home-ingest-owned, since features are built from it),
    4. runs backfill_actuals(through_today=True), which grades from
       live_scores whenever game_list doesn't have the final yet.

The API's _attach_scores reads live_scores the same way, so a final shows on
the site within ~30 min of the buzzer. When the home drop lands, game_list
takes precedence everywhere; the two agree on finals.

Usage:
    python data_engineering/espn_score_poller.py                 # yesterday + today
    python data_engineering/espn_score_poller.py --date 2026-10-21
    python data_engineering/espn_score_poller.py --dry-run       # fetch + match only
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
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text

from core.db import get_engine
from data_engineering.vegas_lines_espn import ESPN_ABBREV_FIX, get_events_for_date


ET = ZoneInfo('America/New_York')

CREATE_LIVE_SCORES_SQL = """
CREATE TABLE IF NOT EXISTS live_scores (
    game_id VARCHAR(50) NOT NULL PRIMARY KEY,
    game_date DATE NOT NULL,
    home_team VARCHAR(10) NOT NULL,
    away_team VARCHAR(10) NOT NULL,
    home_score INT NULL,
    away_score INT NULL,
    status VARCHAR(40) NOT NULL COMMENT 'ESPN status.type.name, e.g. STATUS_FINAL',
    is_final BOOLEAN NOT NULL,
    espn_event_id VARCHAR(20) NOT NULL,
    source VARCHAR(20) NOT NULL DEFAULT 'espn',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_game_date (game_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

UPSERT_SQL = """
INSERT INTO live_scores (game_id, game_date, home_team, away_team,
                         home_score, away_score, status, is_final, espn_event_id)
VALUES (:game_id, :game_date, :home_team, :away_team,
        :home_score, :away_score, :status, :is_final, :espn_event_id)
ON DUPLICATE KEY UPDATE
    home_score = VALUES(home_score),
    away_score = VALUES(away_score),
    status = VALUES(status),
    is_final = VALUES(is_final),
    espn_event_id = VALUES(espn_event_id)
"""


def parse_event(ev: dict) -> dict | None:
    """ESPN event -> {home, away, home_score, away_score, status, is_final, espn_event_id}."""
    comp = (ev.get('competitions') or [{}])[0]
    sides = {}
    for c in comp.get('competitors', []):
        abbr = (c.get('team') or {}).get('abbreviation')
        if not abbr or c.get('homeAway') not in ('home', 'away'):
            continue
        score = c.get('score')
        sides[c['homeAway']] = (ESPN_ABBREV_FIX.get(abbr, abbr),
                                int(score) if score not in (None, '') else None)
    if 'home' not in sides or 'away' not in sides:
        return None

    st = (comp.get('status') or ev.get('status') or {}).get('type', {})
    name = st.get('name', 'UNKNOWN')
    home_score, away_score = sides['home'][1], sides['away'][1]
    # Final = ESPN says completed AND the game is in its 'post' state AND we have
    # a decisive score. Postponed/canceled games are 'post' but not completed.
    is_final = bool(st.get('completed')) and st.get('state') == 'post' \
        and home_score is not None and away_score is not None and home_score != away_score
    return {
        'home': sides['home'][0], 'away': sides['away'][0],
        'home_score': home_score, 'away_score': away_score,
        'status': name, 'is_final': is_final, 'espn_event_id': str(ev.get('id')),
    }


def predicted_games(engine, game_date: date) -> dict:
    """{(home_abbrev, away_abbrev): game_id} for games we've predicted on a date."""
    with engine.connect() as c:
        rows = c.execute(text("""
            SELECT DISTINCT game_id, home_team, away_team
            FROM model_predictions WHERE game_date = :d
        """), {'d': game_date}).fetchall()
    return {(home, away): gid for gid, home, away in rows}


def poll_date(engine, game_date: date, dry_run: bool = False) -> dict:
    events = get_events_for_date(game_date.strftime('%Y%m%d'))
    lookup = predicted_games(engine, game_date)
    counts = {'events': len(events), 'matched': 0, 'final': 0, 'unmatched': 0}
    rows = []
    for ev in events:
        g = parse_event(ev)
        if g is None:
            continue
        game_id = lookup.get((g['home'], g['away']))
        if game_id is None:
            counts['unmatched'] += 1
            print(f"  {game_date} no prediction row for {g['away']} @ {g['home']} (espn {g['espn_event_id']})")
            continue
        counts['matched'] += 1
        counts['final'] += g['is_final']
        rows.append({
            'game_id': game_id, 'game_date': game_date,
            'home_team': g['home'], 'away_team': g['away'],
            'home_score': g['home_score'], 'away_score': g['away_score'],
            'status': g['status'], 'is_final': g['is_final'],
            'espn_event_id': g['espn_event_id'],
        })
        print(f"  {game_id}: {g['away']} {g['away_score']} @ {g['home']} {g['home_score']}  [{g['status']}]")

    if rows and not dry_run:
        with engine.begin() as c:
            c.execute(text(UPSERT_SQL), rows)
    return counts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--date', help='Single ET game date (YYYY-MM-DD); default yesterday + today')
    ap.add_argument('--dry-run', action='store_true', help='Fetch + match, no DB writes, no grading')
    args = ap.parse_args()

    if args.date:
        dates = [date.fromisoformat(args.date)]
    else:
        today_et = datetime.now(ET).date()
        dates = [today_et - timedelta(days=1), today_et]

    engine = get_engine()
    if not args.dry_run:
        with engine.begin() as c:
            c.execute(text(CREATE_LIVE_SCORES_SQL))

    for d in dates:
        counts = poll_date(engine, d, dry_run=args.dry_run)
        print(f"score poll {d}: {counts}", flush=True)

    if not args.dry_run:
        from modeling.prediction_tracker import backfill_actuals
        result = backfill_actuals(engine, lookback_days=3, through_today=True, verbose=False)
        print(f"score poll grading: {result}", flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
