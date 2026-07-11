"""P1 — backfill walk-forward player predictions into `player_predictions`.

Writes the OUT-OF-SAMPLE predictions from the P1 walk-forward protocol
(train 2023-24 -> predict 2024-25; train 2023-24+2024-25 -> predict 2025-26)
so the player-explore page can show "what the model would have said" next to
what actually happened. 2023-24 has no rows: it is training-only in fold 1,
and inventing in-sample predictions for it would violate the leakage rules.

Table DDL / upsert / abbrev plumbing is shared with the Phase-B nightly job
(modeling/player_predict.py) — this script only owns the fold protocol.

Run locally against the home DB, and once on the pipeline task against RDS:
    python scripts/backfill_player_predictions.py
"""
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.db import get_engine  # noqa: E402
from data_engineering.player_dataset import TARGETS, build as build_dataset  # noqa: E402
from modeling.player_predict import (  # noqa: E402
    MODEL_TYPE, context_values, ensure_player_predictions_table,
    team_abbrev_map, upsert_player_predictions)
from modeling.player_projection_models import TwoStageXGB  # noqa: E402

MODEL_VERSION = 'p2_wf_20260710'
# Walk-forward by SEASON_YEAR (each year includes its playoffs/play-in/Cup):
FOLDS = [
    {'train': ['22022'], 'test': '22023'},
    {'train': ['22022', '22023'], 'test': '22024'},
    {'train': ['22022', '22023', '22024'], 'test': '22025'},
]


def build_rows(ds: pd.DataFrame, abbrevs: dict) -> list:
    rows = []
    for fold in FOLDS:
        train = ds[ds['SEASON_YEAR'].isin(fold['train'])]
        test = ds[ds['SEASON_YEAR'] == fold['test']].copy()
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
            row.update(context_values(t))
            for s in TARGETS:
                v = p[f'pred_{s}']
                row[f'pred_{s.lower()}'] = round(float(v), 2) if np.isfinite(v) else None
                av = t[s]
                row[f'actual_{s.lower()}'] = round(float(av), 2) if pd.notna(av) else None
            rows.append(row)
    return rows


def main():
    engine = get_engine()
    ensure_player_predictions_table(engine)
    ds = build_dataset(engine)  # always fresh — the pkl may predate the protocol
    rows = build_rows(ds, team_abbrev_map(engine))
    upsert_player_predictions(engine, rows)
    print(f"upserted {len(rows):,} rows into player_predictions")
    # Retire rows from older walk-forward protocols (e.g. p1_wf_*): the page
    # dedupes by timestamp anyway, but stale rows are dead weight.
    import sqlalchemy as sa
    with engine.begin() as conn:
        n = conn.execute(sa.text(
            "DELETE FROM player_predictions WHERE model_type = :mt "
            "AND model_version LIKE '%_wf_%' AND model_version != :mv"),
            {'mt': MODEL_TYPE, 'mv': MODEL_VERSION}).rowcount
    if n:
        print(f"retired {n:,} rows from older walk-forward versions")
    print(f"done at {datetime.now().isoformat(timespec='seconds')}")


if __name__ == '__main__':
    main()
