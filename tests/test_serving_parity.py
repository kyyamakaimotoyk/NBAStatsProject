"""Train/serve parity tests (E28, 2026-11-13).

    python -m unittest tests.test_serving_parity -v

1. test_placeholder_invariant (no database): every team-game feature step gives a
   game the same values whether it is computed as a played game or as a
   placeholder with its result blanked. This is what makes serving through the
   training pipeline correct. Also runs in CI before the pipeline image is pushed.
2. test_serving_matches_features_table (needs MySQL): build_serving_features on
   past dates reproduces the stored features-table rows for every production
   model column (ELO checked against a fresh compute_elo pass). Skipped when no
   database is reachable. Set SERVING_PARITY_VERSION / SERVING_PARITY_DATES to
   override the snapshot and dates.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEFAULT_VERSION = '20260703T072718Z'
DEFAULT_DATES = ['2025-10-22', '2026-01-15']


class ServingParity(unittest.TestCase):

    def test_placeholder_invariant(self):
        from scripts.check_serving_invariants import check
        problems, n_cols, n_dates = check()
        self.assertGreater(n_cols, 10)
        self.assertEqual(problems, [], '\n'.join(problems[:20]))

    def test_serving_matches_features_table(self):
        try:
            from core.db import get_engine
            engine = get_engine()
            with engine.connect():
                pass
        except Exception as exc:  # no DB configured / reachable
            self.skipTest(f'database unavailable: {exc}')

        import pandas as pd
        from core.features import select_features, load_pruned_columns
        from core.features_io import load_features
        from data_engineering.feature_engineering import (
            build_serving_features, scheduled_games_from_game_list)
        from scripts.check_serving_parity import compare, fresh_elo_reference, ELO_COLS

        version = os.environ.get('SERVING_PARITY_VERSION', DEFAULT_VERSION)
        dates = os.environ.get('SERVING_PARITY_DATES', ','.join(DEFAULT_DATES)).split(',')
        table = load_features(engine, version=version)
        table['GAME_DATE'] = pd.to_datetime(table['GAME_DATE'])
        table['GAME_ID'] = table['GAME_ID'].astype('int64')
        cols = select_features(table.columns, keep_only=load_pruned_columns())
        elo_ref = fresh_elo_reference(engine)
        elo_ref['GAME_ID'] = elo_ref['GAME_ID'].astype('int64')

        for d in dates:
            with self.subTest(date=d):
                srv = build_serving_features(engine, d, scheduled_games_from_game_list(engine, d))
                tbl = table[table['GAME_DATE'] == pd.Timestamp(d)]
                tbl = tbl.drop(columns=[c for c in ELO_COLS if c in tbl]).merge(
                    elo_ref, on='GAME_ID', how='left')
                res, n = compare(srv, tbl, cols)
                bad = res[res['status'] != 'OK']
                self.assertGreater(n, 0, f'no games compared for {d}')
                self.assertTrue(bad.empty, f'{d}: {bad.to_dict("records")[:10]}')


if __name__ == '__main__':
    unittest.main()
