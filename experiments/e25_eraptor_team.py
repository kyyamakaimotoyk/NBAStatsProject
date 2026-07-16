"""E25: team-level prior-season eRAPTOR roster-strength columns.

The assessment's item #2 (RAPM-family talent aggregates, team-model sibling of
P3) and the P3 caveat's explicit follow-up: impact metrics measure margin per
possession, so the TEAM model is the natural consumer. This script builds
per-game, per-side roster-strength aggregates that are pregame-honest:

  roster(game, team) = players who appeared for the team in the trailing 45
                       days (knowable pregame), MINUS players listed Out or
                       Doubtful on the official pregame injury report
  weight(player)     = mean minutes over their last 10 appearances strictly
                       before the game (shift-1, pregame-honest)
  rating(player)     = PRIOR-season minutes-weighted Estimated RAPTOR
                       (P3's loader + normalized-name join, ~87.5% match)

Emitted columns (keyed GAME_ID, NaN when nothing matched):
  {HOME,AWAY}_ERAPTOR_{TOT,OFF,DEF}_WMEAN   MPG-weighted mean rating
  {HOME,AWAY}_ERAPTOR_TOT_MINSUM            sum(MPG_i * eRT_i) — the
                                            "available talent-minutes" shape
  {HOME,AWAY}_ERAPTOR_MATCH_FRAC            weight share with a matched rating
  DIFF_ERAPTOR_TOT_WMEAN, DIFF_ERAPTOR_TOT_MINSUM

These are experiment columns consumed by loop_ab's ``add_columns_file`` arm —
nothing here touches feature_engineering or the features table.

Usage:
  python experiments/e25_eraptor_team.py --csv nba_ml_features_frozen.csv \
      --out outputs/e25_eraptor_team_cols.csv
"""
from __future__ import annotations

import sys as _sys
import os as _os
_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)

from experiments.harness import load_frozen_csv  # torch-first + chdir

import argparse
from collections import deque
from datetime import timedelta

import numpy as np
import pandas as pd

from core.db import get_engine
from experiments.p3_impact_metrics import load_eraptor, norm_name

ROSTER_WINDOW_DAYS = 45
MPG_LOOKBACK = 10


def _parse_minutes(val) -> float:
    """boxscoretraditionalv3 'minutes' is 'MM:SS' (sometimes blank/None)."""
    if val is None or val != val or val == '':
        return 0.0
    s = str(val)
    if ':' in s:
        m, sec = s.split(':', 1)
        try:
            return float(m) + float(sec) / 60.0
        except ValueError:
            return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def load_player_log(engine, start_date: str) -> pd.DataFrame:
    q = f"""
        SELECT p.gameId AS game_id, p.teamId AS team_id, p.personId AS person_id,
               p.firstName, p.familyName, p.minutes,
               g.GAME_DATE AS game_date
        FROM boxscoretraditionalv3_player p
        JOIN game_list g ON g.GAME_ID = p.gameId AND g.TEAM_ID = p.teamId
        WHERE g.GAME_DATE >= '{start_date}'
    """
    log = pd.read_sql(q, engine)
    log['game_date'] = pd.to_datetime(log['game_date'])
    log['min_played'] = log['minutes'].map(_parse_minutes)
    log['name_key'] = (log['firstName'].fillna('') + ' '
                       + log['familyName'].fillna('')).map(norm_name)
    log = log.sort_values(['team_id', 'game_date', 'game_id'])
    return log


def load_game_sides(engine, game_ids: list) -> pd.DataFrame:
    ids = ','.join(f"'{g}'" for g in game_ids)
    q = f"""
        SELECT GAME_ID AS game_id, TEAM_ID AS team_id, GAME_DATE AS game_date,
               MATCHUP
        FROM game_list
        WHERE GAME_ID IN ({ids})
    """
    sides = pd.read_sql(q, engine)
    sides['game_date'] = pd.to_datetime(sides['game_date'])
    sides['is_home'] = sides['MATCHUP'].str.contains('vs.', regex=False)
    return sides


def prior_year(game_date: pd.Timestamp) -> int:
    """Paine's Year = calendar year the (prior) season ENDS in. A game in
    season 2025-26 (starts Oct 2025) uses the 2024-25 rating -> Year 2025,
    i.e. the season START year of the game's own season."""
    return game_date.year if game_date.month >= 8 else game_date.year - 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--csv', default='nba_ml_features_frozen.csv')
    ap.add_argument('--out', default='outputs/e25_eraptor_team_cols.csv')
    ap.add_argument('--roster-days', type=int, default=ROSTER_WINDOW_DAYS)
    args = ap.parse_args()

    engine = get_engine()
    games_df, meta = load_frozen_csv(args.csv)
    games = games_df[['GAME_ID', 'GAME_DATE']].drop_duplicates()
    print(f'{args.csv}: {len(games)} games '
          f'({games.GAME_DATE.min().date()} .. {games.GAME_DATE.max().date()})')

    # eRAPTOR: (name_key, Year) -> ratings, via P3's loader (latin-1, RS rows,
    # minutes-weighted across stints)
    er = load_eraptor()
    er_idx = {(r.name_key, int(r.Year)): (r.PREV_ERAPTOR_TOT, r.PREV_ERAPTOR_OFF,
                                          r.PREV_ERAPTOR_DEF)
              for r in er.itertuples()}

    warmup_start = (games['GAME_DATE'].min() - timedelta(days=200)).date()
    log = load_player_log(engine, str(warmup_start))
    print(f'player log: {len(log):,} rows from {warmup_start}')

    sides = load_game_sides(engine, games['GAME_ID'].astype(str).tolist())
    print(f'game sides: {len(sides):,} rows ({sides.is_home.sum()} home)')

    from data_engineering.player_impact import bulk_fetch_pregame_availability
    unavailable = bulk_fetch_pregame_availability(
        engine, games['GAME_ID'].astype(str).tolist())
    print(f'pregame OUT/Doubtful entries: {len(unavailable):,} (game, team) keys')

    # (team_id, game_id) -> feature dict, built by walking each team's player
    # log chronologically; the snapshot for a game is taken BEFORE that game's
    # rows update the state (pregame-honest by construction).
    need = {}
    for r in sides.itertuples():
        need.setdefault((r.team_id, r.game_date), []).append(
            (str(r.game_id), bool(r.is_home)))

    out_rows = {}
    n_snap = 0
    for team_id, tlog in log.groupby('team_id', sort=False):
        state = {}   # person_id -> {'last': date, 'mins': deque, 'name_key': str}
        team_dates = sorted({d for (t, d) in need if t == team_id})
        di = 0
        for game_date, rows in tlog.groupby('game_date', sort=True):
            # snapshot any needed game dates strictly <= this log date first
            while di < len(team_dates) and team_dates[di] <= game_date:
                snap_date = team_dates[di]
                for game_id, is_home in need[(team_id, snap_date)]:
                    out_rows[(game_id, is_home)] = _snapshot(
                        state, snap_date, args.roster_days, er_idx,
                        unavailable.get((game_id, team_id), {}))
                    n_snap += 1
                di += 1
            for r in rows.itertuples():
                st = state.setdefault(r.person_id, {'mins': deque(maxlen=MPG_LOOKBACK),
                                                    'name_key': r.name_key})
                st['last'] = game_date
                st['mins'].append(r.min_played)
        # trailing snapshots (dates after the last log row)
        while di < len(team_dates):
            snap_date = team_dates[di]
            for game_id, is_home in need[(team_id, snap_date)]:
                out_rows[(game_id, is_home)] = _snapshot(
                    state, snap_date, args.roster_days, er_idx,
                    unavailable.get((game_id, team_id), {}))
                n_snap += 1
            di += 1

    print(f'snapshots: {n_snap:,}')

    records = {}
    for (game_id, is_home), feats in out_rows.items():
        rec = records.setdefault(game_id, {'GAME_ID': game_id})
        prefix = 'HOME' if is_home else 'AWAY'
        for k, v in feats.items():
            rec[f'{prefix}_{k}'] = v
    out = pd.DataFrame(list(records.values()))
    for col in ('ERAPTOR_TOT_WMEAN', 'ERAPTOR_TOT_MINSUM'):
        out[f'DIFF_{col.replace("ERAPTOR_", "ERAPTOR_", 1)}'] = (
            out[f'HOME_{col}'] - out[f'AWAY_{col}'])
    out['GAME_ID'] = out['GAME_ID'].astype(np.int64)

    _os.makedirs('outputs', exist_ok=True)
    out.to_csv(args.out, index=False)

    n_frozen = len(games)
    joined = games.merge(out, left_on=games['GAME_ID'].astype(np.int64),
                         right_on='GAME_ID', how='left')
    cov = float(joined['HOME_ERAPTOR_TOT_WMEAN'].notna().mean())
    mf = pd.concat([out['HOME_ERAPTOR_MATCH_FRAC'], out['AWAY_ERAPTOR_MATCH_FRAC']])
    print(f'coverage: {cov:.3f} of {n_frozen} frozen games have HOME wmean')
    print(f'match_frac: mean={float(mf.mean()):.3f} p10={float(mf.quantile(0.1)):.3f}')
    print(f'{len(out.columns)-1} feature columns -> {args.out}')


def _snapshot(state: dict, snap_date, roster_days: int, er_idx: dict,
              out_players: dict) -> dict:
    cutoff = snap_date - timedelta(days=roster_days)
    tot_w = off_w = def_w = 0.0
    w_matched = 0.0
    w_total = 0.0
    minsum = 0.0
    for pid, st in state.items():
        if st.get('last') is None or st['last'] < cutoff:
            continue
        if pid in out_players:          # pregame Out/Doubtful
            continue
        mpg = float(np.mean(st['mins'])) if st['mins'] else 0.0
        if mpg <= 0:
            continue
        w_total += mpg
        year = prior_year(pd.Timestamp(snap_date))
        rating = er_idx.get((st['name_key'], year))
        if rating is None:
            continue
        tot, off, dfn = rating
        w_matched += mpg
        tot_w += mpg * tot
        off_w += mpg * off
        def_w += mpg * dfn
        minsum += mpg * tot
    if w_matched <= 0:
        return {'ERAPTOR_TOT_WMEAN': np.nan, 'ERAPTOR_OFF_WMEAN': np.nan,
                'ERAPTOR_DEF_WMEAN': np.nan, 'ERAPTOR_TOT_MINSUM': np.nan,
                'ERAPTOR_MATCH_FRAC': 0.0}
    return {
        'ERAPTOR_TOT_WMEAN': tot_w / w_matched,
        'ERAPTOR_OFF_WMEAN': off_w / w_matched,
        'ERAPTOR_DEF_WMEAN': def_w / w_matched,
        'ERAPTOR_TOT_MINSUM': minsum,
        'ERAPTOR_MATCH_FRAC': (w_matched / w_total) if w_total > 0 else 0.0,
    }


if __name__ == '__main__':
    main()
