"""Nightly per-player projections (P-series, Phase B).

Three production entry points:

  train_and_save(engine)            weekly: build the training dataset, fit the
                                    two-stage XGB, save a versioned bundle
                                    (models/bundles/player_xgb_*.joblib + S3)
  predict_players_for_date(...)     nightly: top-8 per team for a slate, using
                                    the PREGAME injury report for roster/vacated
                                    features, upserted into player_predictions
  backfill_player_actuals(engine)   nightly: grade past rows against final
                                    boxscores (predicted-but-DNP rows grade as 0s
                                    — that is real minutes-model error)

Feature assembly reuses data_engineering.player_dataset.build_inference_features,
which runs the SAME shift(1) pipeline as training (train/serve parity). Bundles
ride the same save/load helpers as the game models, so the artifact store,
current-pointer, and leakage metadata behave identically.
"""
import os
import sys
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import sqlalchemy as sa

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.db import get_engine  # noqa: E402
from data_engineering.player_dataset import (  # noqa: E402
    TARGETS, build, build_inference_features)
from data_engineering.player_impact import parse_minutes  # noqa: E402
from modeling.player_projection_models import TwoStageXGB  # noqa: E402

MODEL_KEY = 'player_xgb'      # bundle-file key (models/bundles/player_xgb_*.joblib)
MODEL_TYPE = 'xgb_player'     # model_type value in player_predictions rows

DDL = """
CREATE TABLE IF NOT EXISTS player_predictions (
    id BIGINT NOT NULL AUTO_INCREMENT,
    game_id BIGINT NOT NULL,
    game_date DATE NOT NULL,
    person_id BIGINT NOT NULL,
    player_name VARCHAR(100),
    team_id BIGINT,
    team_abbrev VARCHAR(10),
    opp_team_id BIGINT,
    opp_abbrev VARCHAR(10),
    is_home TINYINT,
    model_type VARCHAR(30) NOT NULL,
    model_version VARCHAR(50) NOT NULL,
    pred_min FLOAT, pred_pts FLOAT, pred_reb FLOAT, pred_ast FLOAT,
    pred_stl FLOAT, pred_blk FLOAT, pred_tov FLOAT, pred_fg3m FLOAT,
    pred_fg3a FLOAT, pred_ftm FLOAT, pred_fta FLOAT,
    actual_min FLOAT, actual_pts FLOAT, actual_reb FLOAT, actual_ast FLOAT,
    actual_stl FLOAT, actual_blk FLOAT, actual_tov FLOAT, actual_fg3m FLOAT,
    actual_fg3a FLOAT, actual_ftm FLOAT, actual_fta FLOAT,
    prediction_timestamp TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_player_pred (game_id, person_id, model_type, model_version),
    KEY idx_pp_person_date (person_id, game_date),
    KEY idx_pp_date (game_date),
    KEY idx_pp_team (team_id, game_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

UPSERT_COLS = [
    'game_id', 'game_date', 'person_id', 'player_name', 'team_id', 'team_abbrev',
    'opp_team_id', 'opp_abbrev', 'is_home', 'model_type', 'model_version',
] + [f'pred_{s.lower()}' for s in TARGETS] + [f'actual_{s.lower()}' for s in TARGETS]


def ensure_player_predictions_table(engine):
    with engine.begin() as conn:
        conn.execute(sa.text(DDL))


def upsert_player_predictions(engine, rows, chunk: int = 2000):
    if not rows:
        return
    cols = ', '.join(UPSERT_COLS)
    placeholders = ', '.join(f':{c}' for c in UPSERT_COLS)
    updates = ', '.join(f'{c} = VALUES({c})' for c in UPSERT_COLS
                        if c not in ('game_id', 'person_id', 'model_type', 'model_version'))
    stmt = sa.text(
        f"INSERT INTO player_predictions ({cols}) VALUES ({placeholders}) "
        f"ON DUPLICATE KEY UPDATE {updates}")
    with engine.begin() as conn:
        for i in range(0, len(rows), chunk):
            conn.execute(stmt, rows[i:i + chunk])


def team_abbrev_map(engine) -> dict:
    q = """
        SELECT TEAM_ID, TEAM_ABBREVIATION
        FROM game_list
        WHERE GAME_DATE = (SELECT MAX(g2.GAME_DATE) FROM game_list g2
                           WHERE g2.TEAM_ID = game_list.TEAM_ID)
    """
    with engine.connect() as conn:
        return {int(tid): ab for tid, ab in conn.execute(sa.text(q))}


# ---------------------------------------------------------------------------
# Training (weekly pipeline stage: player_train)
# ---------------------------------------------------------------------------

def train_and_save(engine=None, seasons=None) -> str:
    """Build the dataset, sanity-check on a temporal holdout, refit on ALL rows
    (repo convention: eval model informs, production model sees everything),
    save the bundle. Returns the versioned bundle path."""
    from modeling.predict_games import save_model_bundle
    engine = engine or get_engine()
    t0 = time.time()
    ds = build(engine, seasons=seasons).sort_values('GAME_DATE')

    n_hold = max(int(len(ds) * 0.1), 500)
    probe = TwoStageXGB().fit(ds.iloc[:-n_hold])
    hp = probe.predict(ds.iloc[-n_hold:])
    holdout_mae = {
        s: round(float(np.mean(np.abs(
            hp[f'pred_{s}'].to_numpy(dtype=float)
            - ds.iloc[-n_hold:][s].to_numpy(dtype=float)))), 3)
        for s in TARGETS}
    print(f"[player_train] holdout sanity (last {n_hold:,} rows): "
          + ', '.join(f'{k} {v}' for k, v in holdout_mae.items()))

    model = TwoStageXGB().fit(ds)
    data_through = pd.to_datetime(ds['GAME_DATE']).max().date().isoformat()
    version = datetime.now().strftime('%Y%m%d')
    bundle = {
        'model': model,
        'feature_names': model.features,
        'targets': list(TARGETS),
        'train_seasons': sorted(set(ds['SEASON_ID'])),
        'n_rows': int(len(ds)),
        'holdout_mae': holdout_mae,
        'train_start_date': pd.to_datetime(ds['GAME_DATE']).min().date().isoformat(),
        'train_end_date': data_through,
        'data_through_date': data_through,
        'model_version': f'{MODEL_TYPE}_{version}',
    }
    path = save_model_bundle(MODEL_KEY, bundle, version=version)
    print(f"[player_train] bundle saved: {path} "
          f"({len(ds):,} rows, through {data_through}, {time.time()-t0:.0f}s)")
    return path


# ---------------------------------------------------------------------------
# Nightly prediction
# ---------------------------------------------------------------------------

def _out_names_by_team(engine, game_date: str, injury_mode: str) -> dict:
    """{team_tricode: set of player names OUT pregame}. Empty dict on failure —
    predictions then assume full rosters (logged as WARN, not fatal)."""
    mode = injury_mode
    if mode == 'auto':
        today = datetime.now().strftime('%Y-%m-%d')
        mode = 'live' if game_date >= today else 'historical'
    try:
        if mode == 'live':
            from data_engineering.injury_data import get_current_injuries
            inj = get_current_injuries()
        else:
            from modeling.predict_games import _fetch_historical_injuries_for_date
            inj = _fetch_historical_injuries_for_date(engine, game_date)
    except Exception as exc:
        print(f"WARN: player injury fetch failed ({mode}) — {exc}; "
              "predicting full rosters")
        return {}
    out = {}
    for r in inj or []:
        if 'OUT' in str(r.get('status', '')).upper():
            ab = r.get('team_abbrev')
            if ab:
                out.setdefault(ab, set()).add(r.get('player_name', ''))
    return out


def predict_players_for_date(engine, game_date: str, injury_mode: str = 'auto',
                             skip_log: bool = False,
                             allow_leakage: bool = False) -> dict:
    """Project the top-8 players per team for one date's slate and upsert into
    player_predictions. Returns {'n_games', 'n_rows', 'n_errors'}."""
    from modeling.predict_games import get_scheduled_games, load_model_bundle
    stats = {'n_games': 0, 'n_rows': 0, 'n_errors': 0}

    bundle = load_model_bundle(MODEL_KEY)
    if bundle is None:
        print("ERROR: player_xgb bundle missing — run the player_train pipeline "
              "stage (modeling.player_predict.train_and_save)")
        stats['n_errors'] += 1
        return stats
    data_through = (bundle.get('data_through_date')
                    or bundle.get('metadata', {}).get('data_through_date'))
    if data_through and game_date <= data_through and not allow_leakage:
        print(f"player projections: skipping {game_date} — inside the bundle's "
              f"training window (through {data_through}); pass allow_leakage "
              "for deliberate backtests")
        return stats

    slate = get_scheduled_games(game_date)
    if slate is None or len(slate) == 0:
        print(f"player projections: no games for {game_date}")
        return stats
    slate = slate.copy()
    # Model covers regular season, playoffs, play-in, and the Cup final —
    # skip preseason/all-star games (experimental rosters, no signal).
    from data_engineering.player_dataset import PREDICTABLE_GID_TYPES
    gid_type = slate['GAME_ID'].map(lambda g: str(int(g)).zfill(10)[2])
    skipped = int((~gid_type.isin(PREDICTABLE_GID_TYPES)).sum())
    if skipped:
        print(f"player projections: skipping {skipped} preseason/exhibition game(s)")
    slate = slate[gid_type.isin(PREDICTABLE_GID_TYPES)].copy()
    if len(slate) == 0:
        return stats
    slate['GAME_DATE'] = game_date

    outs = _out_names_by_team(engine, game_date, injury_mode)
    n_out = sum(len(v) for v in outs.values())
    feats = build_inference_features(engine, slate, outs)
    if len(feats) == 0:
        print(f"ERROR: player feature assembly produced 0 rows for {game_date}")
        stats['n_errors'] += 1
        return stats

    model = bundle['model']
    version = bundle.get('model_version', f'{MODEL_TYPE}_unknown')
    preds = model.predict(feats)
    abbrevs = team_abbrev_map(engine)

    rows = []
    for (_, f), (_, p) in zip(feats.iterrows(), preds.iterrows()):
        row = {
            'game_id': int(f['GAME_ID']),
            'game_date': pd.to_datetime(f['GAME_DATE']).date(),
            'person_id': int(f['personId']),
            'player_name': str(f['PLAYER_NAME']).strip(),
            'team_id': int(f['TEAM_ID']),
            'team_abbrev': abbrevs.get(int(f['TEAM_ID'])),
            'opp_team_id': int(f['OPP_TEAM_ID']),
            'opp_abbrev': abbrevs.get(int(f['OPP_TEAM_ID'])),
            'is_home': int(f['IS_HOME']),
            'model_type': MODEL_TYPE,
            'model_version': version,
        }
        for s in TARGETS:
            v = p[f'pred_{s}']
            row[f'pred_{s.lower()}'] = round(float(v), 2) if np.isfinite(v) else None
            row[f'actual_{s.lower()}'] = None
        rows.append(row)

    if not skip_log:
        ensure_player_predictions_table(engine)
        upsert_player_predictions(engine, rows)
    stats.update(n_games=int(len(slate)), n_rows=len(rows))
    print(f"player projections {game_date}: {len(rows)} rows across "
          f"{len(slate)} games ({n_out} players OUT pregame, v={version})")
    return stats


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------

_ACTUAL_SRC = {  # player_predictions column -> boxscore column
    'actual_pts': 'points', 'actual_reb': 'reboundsTotal', 'actual_ast': 'assists',
    'actual_stl': 'steals', 'actual_blk': 'blocks', 'actual_tov': 'turnovers',
    'actual_fg3m': 'threePointersMade', 'actual_fg3a': 'threePointersAttempted',
    'actual_ftm': 'freeThrowsMade', 'actual_fta': 'freeThrowsAttempted',
}


def backfill_player_actuals(engine, lookback_days: int = 30) -> dict:
    """Fill actual_* on rows whose games have gone final. A predicted player
    with no boxscore row (or zero minutes) grades as all-zero actuals — the
    honest cost of a missed scratch."""
    ensure_player_predictions_table(engine)
    cutoff = (datetime.now() - timedelta(days=lookback_days)).strftime('%Y-%m-%d')
    today = datetime.now().strftime('%Y-%m-%d')
    with engine.connect() as conn:
        pending = conn.execute(sa.text("""
            SELECT id, game_id, person_id FROM player_predictions
            WHERE actual_pts IS NULL AND game_date >= :cutoff AND game_date < :today
        """), {'cutoff': cutoff, 'today': today}).fetchall()
        if not pending:
            return {'games': 0, 'rows': 0}
        gids = sorted({int(r[1]) for r in pending})
        id_list = ','.join(str(g) for g in gids)  # ints, safe to inline
        final_ids = {int(g) for (g,) in conn.execute(sa.text(
            f"SELECT DISTINCT GAME_ID FROM game_list "
            f"WHERE GAME_ID IN ({id_list}) AND WL IS NOT NULL"))}
        if not final_ids:
            return {'games': 0, 'rows': 0}
        fid_list = ','.join(str(g) for g in sorted(final_ids))
        box = {}
        cols = ', '.join(sorted(set(_ACTUAL_SRC.values())))
        for row in conn.execute(sa.text(
                f"SELECT gameId, personId, minutes, {cols} "
                f"FROM boxscoretraditionalv3_player WHERE gameId IN ({fid_list})")
                ).mappings():
            box[(int(row['gameId']), int(row['personId']))] = row

    updates = []
    for pid_row in pending:
        row_id, gid, pid = int(pid_row[0]), int(pid_row[1]), int(pid_row[2])
        if gid not in final_ids:
            continue
        src = box.get((gid, pid))
        upd = {'id': row_id}
        if src is None:
            upd['actual_min'] = 0.0
            for c in _ACTUAL_SRC:
                upd[c] = 0.0
        else:
            upd['actual_min'] = round(parse_minutes(src['minutes']), 2)
            for c, s in _ACTUAL_SRC.items():
                v = src[s]
                upd[c] = float(v) if v is not None else 0.0
        updates.append(upd)

    if updates:
        set_clause = ', '.join(f'{c} = :{c}' for c in ['actual_min'] + list(_ACTUAL_SRC))
        stmt = sa.text(f"UPDATE player_predictions SET {set_clause} WHERE id = :id")
        with engine.begin() as conn:
            for i in range(0, len(updates), 2000):
                conn.execute(stmt, updates[i:i + 2000])
    return {'games': len(final_ids), 'rows': len(updates)}


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='Player projections: train / predict / grade')
    ap.add_argument('--train', action='store_true')
    ap.add_argument('--date', type=str, help='Predict a date (YYYY-MM-DD)')
    ap.add_argument('--allow-leakage', action='store_true')
    ap.add_argument('--grade', action='store_true')
    args = ap.parse_args()
    eng = get_engine()
    if args.train:
        train_and_save(eng)
    if args.date:
        predict_players_for_date(eng, args.date, allow_leakage=args.allow_leakage)
    if args.grade:
        print(backfill_player_actuals(eng))
