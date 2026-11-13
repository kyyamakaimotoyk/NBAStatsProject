"""The ONE way to get model inputs for games that haven't been played (E28).

Every prediction caller (nightly batch job, predict_games.py interactive mode,
the dashboard's Game Predictions tab) goes through ``build_game_features``. It
runs the training feature pipeline itself (feature_engineering.build_serving_features),
so a served row is computed by the same code as a training row. The old
hand-written live builder (predict_games.get_team_rolling_stats /
build_matchup_features) was removed on 2026-11-13: it never produced ELO,
last-10 win % or the DIFF slot/availability columns, and the models saw training
medians in their place from 2026-05-20 to 2026-11-13 (tuning log §E28).

Availability (who is out tonight) is the one input that can't come from
game_list. Training reads the NBA's official pre-game report
(historical_injury_report, Out/Doubtful). Serving uses that table when it has
rows for the date, plus any injuries the caller passes (live feed / manual),
matched to player IDs with predict_games.parse_injuries_for_game. A player out
in either source counts as unavailable.
"""
from __future__ import annotations

import math
from typing import Iterable

import pandas as pd
from sqlalchemy import text

# Columns whose absence would silently gut the model (E28). NaN here is an ERROR.
CRITICAL_FEATURES = ('ELO_DIFF', 'ELO_P_HOME', 'HOME_ELO', 'AWAY_ELO')
# More than this share of a model's columns NaN on one game is also an ERROR.
MAX_NAN_SHARE = 0.10
N_SLOTS = 8


def official_report_availability(engine, game_date: str, games: pd.DataFrame) -> dict:
    """Out/Doubtful players from historical_injury_report for ``game_date``, keyed
    (game_id, team_id) like bulk_fetch_pregame_availability — the training source,
    but joined on date + team instead of through game_list."""
    team_to_game = {}
    for _, g in games.iterrows():
        gid = int(g['GAME_ID'])
        team_to_game[int(g['HOME_TEAM_ID'])] = gid
        team_to_game[int(g['AWAY_TEAM_ID'])] = gid
    if not team_to_game:
        return {}
    try:
        with engine.connect() as conn:
            df = pd.read_sql(text("""
                SELECT team_id, player_id, player_name, status, reason
                FROM historical_injury_report
                WHERE game_date = :d AND player_id IS NOT NULL
                  AND status IN ('Out', 'Doubtful')
            """), conn, params={'d': game_date})
    except Exception as exc:
        print(f"  WARN: official injury report unavailable for {game_date} - {exc}")
        return {}
    out: dict = {}
    for _, r in df.iterrows():
        gid = team_to_game.get(int(r['team_id']))
        if gid is None:
            continue
        out.setdefault((gid, int(r['team_id'])), {})[int(r['player_id'])] = {
            'available': False, 'player_name': r['player_name'],
            'comment': f"INJURY_REPORT: {r['status']} - {r['reason']}",
            'minutes': 0.0, 'source': 'pregame_injury_report'}
    return out


def caller_injury_availability(engine, game_date: str, games: pd.DataFrame,
                               injuries_by_game: dict) -> dict:
    """Map caller-supplied injuries ({game_id: [{'name', 'status', 'team_side'}]},
    statuses already filtered to out/doubtful) to player IDs, same keying."""
    from modeling.predict_games import parse_injuries_for_game
    out: dict = {}
    for _, g in games.iterrows():
        gid = int(g['GAME_ID'])
        items = injuries_by_game.get(gid) or injuries_by_game.get(str(g['GAME_ID'])) or []
        if not items:
            continue
        info = parse_injuries_for_game(engine, items, int(g['HOME_TEAM_ID']),
                                       int(g['AWAY_TEAM_ID']), game_date)
        for side, team_col in (('home', 'HOME_TEAM_ID'), ('away', 'AWAY_TEAM_ID')):
            for d in info['injury_details']:
                if d['team'] != side:
                    continue
                out.setdefault((gid, int(g[team_col])), {})[int(d['player_id'])] = {
                    'available': False, 'player_name': d['name'],
                    'comment': f"CALLER: {d.get('status', 'out')}", 'minutes': 0.0,
                    'source': 'caller_injuries'}
    return out


def injuries_by_game_from_team_lookup(games: pd.DataFrame, lookup: dict,
                                      statuses: Iterable[str] = ('OUT', 'DOUBTFUL')) -> dict:
    """{team_abbrev: [injury dict with player_name/status]} -> injuries_by_game."""
    keep = {s.upper() for s in statuses}
    out = {}
    for _, g in games.iterrows():
        items, seen = [], set()
        for side, abbr in (('home', g['HOME_TEAM']), ('away', g['AWAY_TEAM'])):
            for inj in lookup.get(abbr, ()):
                name = (inj.get('player_name') or inj.get('name') or '').strip()
                if not name or str(inj.get('status', '')).upper() not in keep or name.lower() in seen:
                    continue
                seen.add(name.lower())
                items.append({'name': name, 'status': str(inj['status']).lower(),
                              'team_abbrev': abbr, 'team_side': side})
        out[int(g['GAME_ID'])] = items
    return out


def _slot_to_player(engine, row: pd.Series) -> dict:
    """SHAP-display mapping {'HOME'|'AWAY': {slot: {player_id, player_name, impact,
    available}}} rebuilt from the row's slot columns."""
    ids = set()
    for side in ('HOME', 'AWAY'):
        for k in range(1, N_SLOTS + 1):
            v = row.get(f'{side}_SLOT_{k}_PLAYER_ID')
            if v is not None and not (isinstance(v, float) and math.isnan(v)) and int(v) > 0:
                ids.add(int(v))
    names = {}
    if ids:
        with engine.connect() as conn:
            res = conn.execute(text(
                f"SELECT id, full_name FROM nba_players WHERE id IN ({','.join(map(str, ids))})"))
            names = {int(r[0]): r[1] for r in res}
    mapping = {'HOME': {}, 'AWAY': {}}
    for side in ('HOME', 'AWAY'):
        for k in range(1, N_SLOTS + 1):
            pid = row.get(f'{side}_SLOT_{k}_PLAYER_ID')
            if pid is None or (isinstance(pid, float) and math.isnan(pid)) or int(pid) <= 0:
                continue
            mapping[side][k] = {'player_id': int(pid),
                                'player_name': names.get(int(pid), str(int(pid))),
                                'impact': float(row.get(f'{side}_SLOT_{k}_IMPACT', 0.0)),
                                'available': bool(row.get(f'{side}_SLOT_{k}_AVAILABLE', 1.0) >= 0.5)}
    return mapping


def build_game_features(engine, game_date: str, games: pd.DataFrame,
                        injuries_by_game: dict | None = None,
                        with_slot_names: bool = False) -> dict:
    """Model inputs for every game in ``games`` (get_scheduled_games shape).

    Returns {game_id (int): matchup dict}. Each dict holds every feature column
    the training pipeline produces (keys match the bundles' feature_names), plus
    '_slot_to_player' when with_slot_names=True (SHAP labels). Pass the dict to
    predict_with_rf / predict_with_xgb / predict_with_pytorch unchanged.
    """
    from data_engineering.feature_engineering import build_serving_features

    if games is None or len(games) == 0:
        return {}
    official = official_report_availability(engine, game_date, games)
    supplied = (caller_injury_availability(engine, game_date, games, injuries_by_game)
                if injuries_by_game else {})
    availability = {}
    for src in (official, supplied):
        for key, players in src.items():
            availability.setdefault(key, {}).update(players)
    n_off = sum(len(v) for v in official.values())
    n_sup = sum(len(v) for v in supplied.values())
    print(f"  availability for {game_date}: {n_off} out/doubtful from the official report, "
          f"{n_sup} from caller injuries"
          + ("" if n_off else " (official report has no rows for this date)"))

    rows = build_serving_features(engine, game_date, games, extra_availability=availability)
    out = {}
    for _, row in rows.iterrows():
        m = row.to_dict()
        if with_slot_names:
            m['_slot_to_player'] = _slot_to_player(engine, row)
        out[int(row['GAME_ID'])] = m
    missing_games = set(int(g) for g in pd.to_numeric(games['GAME_ID'])) - set(out)
    if missing_games:
        print(f"ERROR: SERVING_FEATURES_MISSING games={sorted(missing_games)} "
              f"produced no feature row for {game_date}")
    return out


def check_features(matchup: dict, feature_names: list, model_key: str, label: str) -> bool:
    """E28 guard. Prints ``ERROR: SERVING_FEATURES_MISSING`` (alarm-monitored) when
    a model column is absent, a critical column is NaN, or too many are NaN.
    Returns True when the row is healthy. Never blocks the prediction."""
    absent = [f for f in feature_names if f not in matchup]
    nan = [f for f in feature_names if f in matchup and _isnan(matchup[f])]
    crit = [f for f in CRITICAL_FEATURES if f in feature_names and (f in absent or f in nan)]
    share = (len(absent) + len(nan)) / max(1, len(feature_names))
    if absent or crit or share > MAX_NAN_SHARE:
        print(f"ERROR: SERVING_FEATURES_MISSING model={model_key} game={label} "
              f"absent={len(absent)} nan={len(nan)} critical={crit} "
              f"examples={(absent + nan)[:8]}")
        return False
    if nan:
        print(f"  WARN: {model_key} {label}: {len(nan)} NaN feature(s) imputed, e.g. {nan[:5]}")
    return True


def _isnan(v) -> bool:
    try:
        return v is None or (isinstance(v, float) and math.isnan(v)) or bool(pd.isna(v))
    except (TypeError, ValueError):
        return False
