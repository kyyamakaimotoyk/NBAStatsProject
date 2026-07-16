"""Export a frozen feature snapshot from MySQL to a CSV for experiments.

The experiment harnesses read flat CSVs (repo convention), but reproducible
experiments need a *pinned* feature_set_version rather than the moving
``feature_set_current`` pointer. This script exports one explicit version to
a CSV plus a ``<out>.meta.json`` sidecar carrying provenance, so any harness
can assert it is running on exactly the snapshot it thinks it is.

Read-only against the database: never writes the features table, never touches
the pointer.

Usage:
    python scripts/export_features_snapshot.py --version 20260703T072718Z \
        --out nba_ml_features_frozen.csv
"""
from __future__ import annotations

import sys as _sys
import os as _os
_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _PROJECT_ROOT)

import argparse
import json
from datetime import datetime, timezone

import pandas as pd

from core.db import get_engine
from core.features import select_features
from core.features_io import load_features


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--version', required=True,
                    help='feature_set_version to export (explicit, never the pointer)')
    ap.add_argument('--out', default='nba_ml_features_frozen.csv',
                    help='Output CSV path (project root by convention)')
    args = ap.parse_args()

    engine = get_engine()
    print(f'Loading features version {args.version} ...')
    df = load_features(engine, version=args.version)
    if df.empty:
        raise SystemExit(f'ERROR: no rows for feature_set_version={args.version}')

    for target in ('TARGET_WIN', 'TARGET_MARGIN'):
        if target not in df.columns:
            raise SystemExit(f'ERROR: exported frame is missing {target}')

    n_model_features = len(select_features(df.columns))
    min_date = pd.to_datetime(df['GAME_DATE']).min()
    max_date = pd.to_datetime(df['GAME_DATE']).max()
    w5 = df[(df['GAME_DATE'] >= '2026-03-15') & (df['GAME_DATE'] <= '2026-04-15')]

    out_path = _os.path.join(_PROJECT_ROOT, args.out) if not _os.path.isabs(args.out) else args.out
    df.to_csv(out_path, index=False)

    meta = {
        'feature_set_version': args.version,
        'exported_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'n_rows': int(len(df)),
        'n_games': int(df['GAME_ID'].nunique()),
        'n_columns': int(len(df.columns)),
        'n_model_features_prod_config': int(n_model_features),
        'min_date': str(min_date.date()),
        'max_date': str(max_date.date()),
        'n_w5_games': int(len(w5)),
    }
    meta_path = out_path + '.meta.json'
    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)

    print(f'Exported {meta["n_rows"]} rows x {meta["n_columns"]} cols '
          f'({meta["min_date"]} .. {meta["max_date"]})')
    print(f'Model features under prod config (E9 on / E10 off / E11 off): {n_model_features}')
    print(f'W5 window (2026-03-15..2026-04-15) rows: {meta["n_w5_games"]}')
    print(f'CSV  -> {out_path}')
    print(f'meta -> {meta_path}')


if __name__ == '__main__':
    main()
