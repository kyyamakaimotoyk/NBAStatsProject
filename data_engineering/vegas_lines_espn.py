"""
ESPN scoreboard / pickcenter fetcher for NBA Vegas lines.

Pulls current and upcoming games from ESPN's public scoreboard, then queries
each game's /summary endpoint for the pickcenter array. Saves DraftKings lines
(or whatever provider ESPN exposes for that game) into the `vegas_lines` table.

Why ESPN: free, no auth, no geo-block from non-US IPs. DraftKings is geo-blocked
direct from non-US, but ESPN proxies the DK line for current games. For dates
before ~2025-12, ESPN exposes a "consensus" / "teamrankings" provider rather
than a specific bookmaker. We record whatever it returns.

Usage:
    python data_engineering/vegas_lines_espn.py                        # today only
    python data_engineering/vegas_lines_espn.py --days-ahead 7         # today + next 7
    python data_engineering/vegas_lines_espn.py --start 2026-05-19 --end 2026-05-25
    python data_engineering/vegas_lines_espn.py --start 2022-01-01 --end 2022-03-31  # historical backfill
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

import requests
from sqlalchemy import text

from core.db import get_engine


SCOREBOARD_URL = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard'
SUMMARY_URL = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary'
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}


# ESPN uses a handful of team abbreviations that differ from the NBA/nba_teams
# canonical set. Left unmapped, these rows (a) fail to resolve a team_id and
# (b) never match the dashboard's Vegas overlay, which keys on the canonical
# abbreviation from the schedule (e.g. schedule says 'SAS', ESPN says 'SA').
ESPN_ABBREV_FIX = {
    'GS': 'GSW', 'NO': 'NOP', 'NY': 'NYK',
    'SA': 'SAS', 'UTAH': 'UTA', 'WSH': 'WAS',
}


# Provider name from ESPN -> our source label + bookmaker fields
PROVIDER_TO_SOURCE = {
    'Draft Kings':  ('espn_draftkings',  'Draft Kings'),
    'DraftKings':   ('espn_draftkings',  'Draft Kings'),
    'consensus':    ('espn_consensus',   'Market consensus'),
    'teamrankings': ('espn_teamrankings', 'TeamRankings.com'),
    'ESPN BET':     ('espn_espnbet',     'ESPN BET'),
    'FanDuel':      ('espn_fanduel',     'FanDuel'),
    'caesars':      ('espn_caesars',     'Caesars'),
}


def get_events_for_date(date_str: str) -> list:
    """Return list of events from ESPN scoreboard for one date (YYYYMMDD)."""
    try:
        r = requests.get(SCOREBOARD_URL, params={'dates': date_str},
                         headers=HEADERS, timeout=30)
        if r.status_code != 200:
            return []
        return r.json().get('events', [])
    except Exception as e:
        print(f'    [scoreboard] {date_str}: {type(e).__name__}: {str(e)[:60]}')
        return []


def get_pickcenter_for_event(event_id: str) -> list:
    """Return pickcenter list (one entry per provider) for a single game."""
    try:
        r = requests.get(SUMMARY_URL, params={'event': event_id},
                         headers=HEADERS, timeout=30)
        if r.status_code != 200:
            return []
        return r.json().get('pickcenter', []) or []
    except Exception as e:
        print(f'    [summary] event={event_id}: {type(e).__name__}: {str(e)[:60]}')
        return []


def build_team_id_resolver(engine) -> dict:
    """{abbreviation: team_id} from nba_teams."""
    with engine.connect() as c:
        rows = c.execute(text("SELECT id, abbreviation FROM nba_teams")).fetchall()
    return {r[1]: r[0] for r in rows}


def build_game_id_resolver(engine, start_date: date, end_date: date) -> dict:
    """{(game_date, home_team_id, away_team_id): GAME_ID}."""
    with engine.connect() as c:
        rows = c.execute(text("""
            SELECT GAME_ID, GAME_DATE, TEAM_ID, MATCHUP
            FROM game_list
            WHERE GAME_DATE >= :start AND GAME_DATE <= :end
        """), {'start': start_date.isoformat(), 'end': end_date.isoformat()}).fetchall()

    games = {}
    for game_id, game_date, team_id, matchup in rows:
        if game_id not in games:
            games[game_id] = {'date': game_date.date() if hasattr(game_date, 'date') else game_date}
        if matchup and 'vs.' in str(matchup):
            games[game_id]['home'] = int(team_id)
        elif matchup and '@' in str(matchup):
            games[game_id]['away'] = int(team_id)

    return {(g['date'], g['home'], g['away']): gid
            for gid, g in games.items() if 'home' in g and 'away' in g}


def fetch_lines_for_date(engine, target_date: date, team_resolver: dict,
                         game_resolver: dict, sleep_per_event: float = 0.3) -> int:
    """Fetch all games for one date, insert pickcenter lines into vegas_lines.
    Returns number of new rows inserted."""
    date_str = target_date.strftime('%Y%m%d')
    events = get_events_for_date(date_str)
    if not events:
        return 0

    rows_to_insert = []
    for ev in events:
        ev_id = ev['id']
        # Identify home/away teams from the event's competition data
        comp = ev.get('competitions', [{}])[0]
        competitors = comp.get('competitors', [])
        home_abbrev = away_abbrev = None
        for c in competitors:
            team = c.get('team', {})
            abbr = team.get('abbreviation')
            if not abbr: continue
            abbr = ESPN_ABBREV_FIX.get(abbr, abbr)  # normalize to canonical NBA abbrev
            if c.get('homeAway') == 'home':
                home_abbrev = abbr
            elif c.get('homeAway') == 'away':
                away_abbrev = abbr
        if not home_abbrev or not away_abbrev:
            continue

        home_id = team_resolver.get(home_abbrev)
        away_id = team_resolver.get(away_abbrev)
        game_id = game_resolver.get((target_date, home_id, away_id)) if (home_id and away_id) else None

        pickcenter = get_pickcenter_for_event(ev_id)
        time.sleep(sleep_per_event)
        for p in pickcenter:
            prov_name = p.get('provider', {}).get('name', '')
            mapping = PROVIDER_TO_SOURCE.get(prov_name)
            if not mapping:
                # Unknown provider — still insert under a generic label so we don't lose it
                source_label = f'espn_other_{prov_name.lower().replace(" ", "_")[:30]}'
                bookmaker = prov_name
            else:
                source_label, bookmaker = mapping

            # ESPN's `spread` field convention: negative = the FAVORED team is favored by that much,
            # and `details` carries the team string (e.g., "OKC -7.5"). The sign is from the favored
            # team's perspective. We need to convert to home-perspective.
            #
            # Easier path: read `homeTeamOdds.favorite` and `spread` magnitude.
            spread_raw = p.get('spread')
            details = p.get('details', '')
            home_spread = None
            if spread_raw is not None:
                try:
                    spread_val = float(spread_raw)
                    home_odds = p.get('homeTeamOdds', {})
                    if home_odds.get('favorite') is True:
                        # Home is favored — home_spread is negative magnitude
                        home_spread = -abs(spread_val)
                    elif home_odds.get('favorite') is False:
                        # Away is favored — home_spread is positive magnitude
                        home_spread = abs(spread_val)
                    else:
                        # Sign-ambiguous; parse details for team abbrev
                        if details and home_abbrev and details.startswith(home_abbrev):
                            home_spread = -abs(spread_val)
                        elif details and away_abbrev and details.startswith(away_abbrev):
                            home_spread = abs(spread_val)
                        else:
                            home_spread = spread_val  # best-effort
                except (TypeError, ValueError):
                    pass

            total = p.get('overUnder')
            try:
                total = float(total) if total is not None else None
            except (TypeError, ValueError):
                total = None

            hto = p.get('homeTeamOdds', {})
            ato = p.get('awayTeamOdds', {})
            home_ml = hto.get('moneyLine')
            away_ml = ato.get('moneyLine')
            try:
                home_ml = int(home_ml) if home_ml not in (None, '') else None
                away_ml = int(away_ml) if away_ml not in (None, '') else None
            except (TypeError, ValueError):
                home_ml = away_ml = None

            rows_to_insert.append({
                'game_date': target_date,
                'home_team_id': home_id,
                'away_team_id': away_id,
                'home_team_abbrev': home_abbrev,
                'away_team_abbrev': away_abbrev,
                'game_id': game_id,
                'source': source_label,
                'bookmaker': bookmaker,
                'line_type': 'pregame',
                'home_spread': home_spread,
                'total': total,
                'home_moneyline': home_ml,
                'away_moneyline': away_ml,
                'notes': f'espn event_id={ev_id}; details="{details}"',
            })

    if not rows_to_insert:
        return 0

    sql = text("""
        INSERT IGNORE INTO vegas_lines (
            game_date, home_team_id, away_team_id, home_team_abbrev, away_team_abbrev,
            game_id, source, bookmaker, line_type, home_spread, total,
            home_moneyline, away_moneyline, notes
        ) VALUES (
            :game_date, :home_team_id, :away_team_id, :home_team_abbrev, :away_team_abbrev,
            :game_id, :source, :bookmaker, :line_type, :home_spread, :total,
            :home_moneyline, :away_moneyline, :notes
        )
    """)
    with engine.connect() as c:
        result = c.execute(sql, rows_to_insert)
        c.commit()
        return result.rowcount


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--start', dest='start_date', default=None,
                   help='Start date (YYYY-MM-DD). Defaults to today.')
    p.add_argument('--end', dest='end_date', default=None,
                   help='End date (YYYY-MM-DD). Defaults to start_date + days-ahead.')
    p.add_argument('--days-ahead', type=int, default=0,
                   help='If --end not set: scrape today + this many future days (default 0 = today only)')
    p.add_argument('--sleep', type=float, default=0.3,
                   help='Seconds between event API calls (default 0.3)')
    args = p.parse_args()

    if args.start_date:
        start = datetime.strptime(args.start_date, '%Y-%m-%d').date()
    else:
        start = date.today()

    if args.end_date:
        end = datetime.strptime(args.end_date, '%Y-%m-%d').date()
    else:
        end = start + timedelta(days=args.days_ahead)

    eng = get_engine()
    print(f'[setup] Building team_id and game_id resolvers...')
    team_resolver = build_team_id_resolver(eng)
    game_resolver = build_game_id_resolver(eng, start, end + timedelta(days=14))
    print(f'  {len(team_resolver)} teams, {len(game_resolver)} game-lookups in window')

    dates = []
    cur = start
    while cur <= end:
        dates.append(cur)
        cur += timedelta(days=1)

    total_inserted = 0
    for i, d in enumerate(dates, 1):
        n = fetch_lines_for_date(eng, d, team_resolver, game_resolver, sleep_per_event=args.sleep)
        total_inserted += n
        print(f'[{i:3d}/{len(dates)}] {d}: {n} new rows')

    print(f'\nDone. {total_inserted:,} new rows inserted into vegas_lines.')


if __name__ == '__main__':
    main()
