"""Read-only P-2 health check: retrain cadence, bundle sync, track-record provenance.

Answers three questions against whichever DB core.db points at (local MySQL,
or RDS when run as a one-off pipeline task):

  1. Did the weekly retrain train ALL three models every week since --since?
     (model_registry run_kind='train' rows per week x model family. CloudWatch
     keeps pipeline logs only 14 days, so the registry is the only long record.)
  2. Do the rf / xgb / nn current bundles come from one run? (modeling/bundle_sync;
     in the pipeline container the bundles are pulled from S3.)
  3. Per season x model, which process produced the rows the public record
     serves (wf_ walk-forward vs live/retrospective), and how each model scores
     on the games all three share (regular season only).

Usage:
    python scripts/check_track_record.py
    python scripts/check_track_record.py --since 2026-07-06 --skip-bundles
"""
from __future__ import annotations

# torch first (Windows MKL import order) - bundle_sync imports predict_games.
try:
    import torch  # noqa: F401
except (ImportError, OSError):
    pass

import argparse
import sys
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.db import get_engine  # noqa: E402

FAMILIES = ('rf', 'xgb', 'nn')


def retrain_cadence(engine, since: str) -> None:
    q = """
        SELECT model_type, training_date, MAX(train_end_date) AS train_end,
               MAX(test_end_date) AS data_end, COUNT(*) AS n
        FROM model_registry
        WHERE (run_kind = 'train' OR run_kind IS NULL) AND training_date >= :s
        GROUP BY model_type, training_date
    """
    df = pd.read_sql(sa.text(q), engine, params={'s': since})
    print(f"\n== 1. Training runs since {since} (model_registry, run_kind=train) ==")
    if df.empty:
        print("  NONE - no model trained since then. The weekly retrain is not running.")
        return
    df['family'] = df['model_type'].str.split('_').str[0]
    df = df[df['family'].isin(FAMILIES)]
    df['week'] = pd.to_datetime(df['training_date']).dt.to_period('W-SUN').dt.start_time.dt.date
    grid = (df.groupby(['week', 'family'])['training_date'].max()
            .unstack().reindex(columns=list(FAMILIES)))
    print(grid.fillna('-- MISSING --').to_string())
    weeks = pd.period_range(pd.Timestamp(since), pd.Timestamp.today(), freq='W-SUN')
    missing_weeks = [str(w.start_time.date()) for w in weeks
                     if w.start_time.date() not in set(grid.index)]
    gaps = grid.isna().any(axis=1)
    print(f"  weeks with no training at all: {missing_weeks or 'none'}")
    print(f"  weeks where a family was skipped: {list(map(str, grid.index[gaps])) or 'none'}")
    latest = df.sort_values('training_date').groupby('family').tail(1)
    print("  latest per family (data_end = last game in the eval slice):")
    for _, r in latest.iterrows():
        print(f"    {r['family']:4s} trained {r['training_date']}  data_end {r['data_end']}")


def bundle_sync() -> None:
    print("\n== 2. Current bundle sync ==")
    from modeling.bundle_sync import check_bundle_sync
    in_sync, lines = check_bundle_sync()
    print('  ' + ('OK' if in_sync else 'MISMATCH'))
    for line in lines:
        print(line)


def provenance(engine) -> None:
    q = """
        SELECT game_id, game_date, model_type, model_version,
               is_correct, margin_error
        FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY game_id, model_type
                                           ORDER BY prediction_timestamp DESC) AS rn
              FROM model_predictions WHERE actual_winner IS NOT NULL) x
        WHERE rn = 1
    """
    df = pd.read_sql(sa.text(q), engine)
    df = df[df['model_type'].isin(FAMILIES)]
    # Regular season only (GAME_ID type digit 2), as the article analyses use.
    df = df[df['game_id'].astype(str).str.zfill(10).str[2] == '2']
    gd = pd.to_datetime(df['game_date'])
    start = gd.dt.year - (gd.dt.month < 8).astype(int)
    df['season'] = start.astype(str) + '-' + ((start + 1) % 100).astype(str).str.zfill(2)
    df['kind'] = df['model_version'].str.startswith('wf_').map({True: 'wf', False: 'other'})

    print("\n== 3a. Served-row provenance, regular season (wf_ = walk-forward) ==")
    print(df.pivot_table(index='season', columns=['model_type', 'kind'], values='game_id',
                         aggfunc='count', fill_value=0).to_string())

    print("\n== 3b. Paired games (all three models graded): accuracy / margin MAE ==")
    wide = df.pivot_table(index=['season', 'game_id'], columns='model_type',
                          values=['is_correct', 'margin_error'], aggfunc='first')
    wide = wide.dropna()
    out = pd.DataFrame({
        'games': wide.groupby(level='season').size(),
        **{f'acc_{m}': wide['is_correct'][m].groupby(level='season').mean().round(3)
           for m in FAMILIES},
        **{f'mae_{m}': wide['margin_error'][m].abs().groupby(level='season').mean().round(2)
           for m in FAMILIES},
    })
    print(out.to_string())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--since', default='2026-07-06',
                    help='first Monday to audit for weekly retrains (default 2026-07-06)')
    ap.add_argument('--skip-bundles', action='store_true',
                    help='skip the bundle sync check (no model files / S3 access)')
    args = ap.parse_args()

    engine = get_engine()
    try:
        retrain_cadence(engine, args.since)
        if not args.skip_bundles:
            bundle_sync()
        provenance(engine)
    finally:
        engine.dispose()
    return 0


if __name__ == '__main__':
    sys.exit(main())
