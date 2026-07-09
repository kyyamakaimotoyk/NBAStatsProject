"""P1 — create `player_predictions` and backfill walk-forward predictions.

Writes the OUT-OF-SAMPLE predictions from the P1 walk-forward protocol
(train 2023-24 -> predict 2024-25; train 2023-24+2024-25 -> predict 2025-26)
so the player-explore page can show "what the model would have said" next to
what actually happened. 2023-24 has no rows: it is training-only in fold 1,
and inventing in-sample predictions for it would violate the leakage rules.

The table schema is the Phase-B production schema (nightly job will upsert
into the same unique key), so this doubles as the migration.

Run locally against the home DB, and once on the pipeline task against RDS:
    python experiments/p1_backfill_predictions.py
"""
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd
import sqlalchemy as sa

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.db import get_engine  # noqa: E402
from experiments.p1_player_dataset import OUT_PATH as DATASET_PATH, build as build_dataset  # noqa: E402
from experiments.p1_player_models import TwoStageXGB  # noqa: E402

MODEL_TYPE = 'xgb_player'
MODEL_VERSION = 'p1_wf_20260709'
FOLDS = [
    {'train': ['22023'], 'test': '22024'},
    {'train': ['22023', '22024'], 'test': '22025'},
]
STATS = ['MIN', 'PTS', 'REB', 'AST', 'STL', 'BLK', 'TOV', 'FG3M', 'FG3A', 'FTM', 'FTA']

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
] + [f'pred_{s.lower()}' for s in STATS] + [f'actual_{s.lower()}' for s in STATS]


def team_abbrev_map(engine) -> dict:
    q = """
        SELECT TEAM_ID, TEAM_ABBREVIATION
        FROM game_list
        WHERE GAME_DATE = (SELECT MAX(g2.GAME_DATE) FROM game_list g2
                           WHERE g2.TEAM_ID = game_list.TEAM_ID)
    """
    with engine.connect() as conn:
        return {int(tid): ab for tid, ab in conn.execute(sa.text(q))}


def build_rows(ds: pd.DataFrame, abbrevs: dict) -> list[dict]:
    rows = []
    for fold in FOLDS:
        train = ds[ds['SEASON_ID'].isin(fold['train'])]
        test = ds[ds['SEASON_ID'] == fold['test']].copy()
        model = TwoStageXGB().fit(train)
        preds = model.predict(test)
        print(f"fold test={fold['test']}: {len(test):,} predictions")
        for (_, t), (_, p) in zip(test.iterrows(), preds.iterrows()):
            row = {
                'game_id': int(t['GAME_ID']),
                'game_date': t['GAME_DATE'].date(),
                'person_id': int(t['personId']),
                'player_name': str(t['PLAYER_NAME']).strip(),
                'team_id': int(t['TEAM_ID']),
                'team_abbrev': abbrevs.get(int(t['TEAM_ID'])),
                'opp_team_id': int(t['OPP_TEAM_ID']),
                'opp_abbrev': abbrevs.get(int(t['OPP_TEAM_ID'])),
                'is_home': int(t['IS_HOME']),
                'model_type': MODEL_TYPE,
                'model_version': MODEL_VERSION,
            }
            for s in STATS:
                v = p[f'pred_{s}']
                row[f'pred_{s.lower()}'] = round(float(v), 2) if np.isfinite(v) else None
                av = t[s]
                row[f'actual_{s.lower()}'] = round(float(av), 2) if pd.notna(av) else None
            rows.append(row)
    return rows


def upsert(engine, rows: list[dict], chunk: int = 2000):
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
    print(f"upserted {len(rows):,} rows into player_predictions")


def main():
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(sa.text(DDL))
    if not os.path.exists(DATASET_PATH):
        build_dataset(engine)
    ds = pd.read_pickle(DATASET_PATH)
    rows = build_rows(ds, team_abbrev_map(engine))
    upsert(engine, rows)
    print(f"done at {datetime.now().isoformat(timespec='seconds')}")


if __name__ == '__main__':
    main()
