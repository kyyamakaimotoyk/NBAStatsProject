"""One-shot migration: load the legacy nba_ml_features.csv into the
``features`` MySQL table created by ``core.features_io``.

Usage (from project root):

    python scripts/migrate_features_csv_to_db.py
    python scripts/migrate_features_csv_to_db.py --csv nba_ml_features.csv
    python scripts/migrate_features_csv_to_db.py --version legacy_initial
    python scripts/migrate_features_csv_to_db.py --no-set-current   # write, don't promote

Idempotent: safe to re-run with a different ``--version`` to compare snapshots.
The default version is a UTC timestamp tag (e.g. ``20260528T143015Z``).
"""
from __future__ import annotations

import argparse
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

import pandas as pd

from core.db import get_engine
from core.features_io import write_features, get_current_version, list_versions


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument(
        '--csv', default=os.path.join(_PROJECT_ROOT, 'nba_ml_features.csv'),
        help='Path to the CSV to migrate (default: nba_ml_features.csv at project root)',
    )
    parser.add_argument(
        '--version', default=None,
        help='feature_set_version tag for this snapshot (default: UTC timestamp)',
    )
    parser.add_argument(
        '--no-set-current', action='store_true',
        help='Insert rows but do not promote the version to feature_set_current',
    )
    parser.add_argument(
        '--chunksize', type=int, default=200,
        help='Rows per multi-row INSERT (default: 200)',
    )
    args = parser.parse_args()

    if not os.path.exists(args.csv):
        sys.exit(f"CSV not found: {args.csv}")

    print(f"Loading {args.csv} ...")
    df = pd.read_csv(args.csv)
    print(f"  {len(df)} rows, {len(df.columns)} columns")

    engine = get_engine()

    prior_current = get_current_version(engine)
    print(f"  Current pointer before: {prior_current!r}")

    print("Writing to features table (this may take a minute on first run) ...")
    version = write_features(
        df, engine,
        version=args.version,
        set_current=not args.no_set_current,
        chunksize=args.chunksize,
    )
    print(f"Done. version={version}  set_current={not args.no_set_current}")

    print()
    print("Versions in features table:")
    print(list_versions(engine).to_string(index=False))


if __name__ == '__main__':
    main()
