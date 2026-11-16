"""Importer status handling (2026-11-16): time-based status-2 retries, rows
without ids, nba_api null-block parser crashes. Run: python -m unittest tests.test_importer_status"""
import datetime
import logging
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data_engineering import main_refactored as mr  # noqa: E402

TRAD_P = 'nba_data.boxscoretraditionalv3_player'
TRAD_T = 'nba_data.boxscoretraditionalv3_team'
INACTIVE = 'nba_data.boxscoresummaryv3_inactive_players'
V2 = 'nba_data.boxscoresummaryv2_summary'
COLS = [TRAD_P, TRAD_T, INACTIVE, V2]


def importer():
    imp = mr.NBADataImporter.__new__(mr.NBADataImporter)  # no DB, no log files
    imp.logger = logging.getLogger('test_importer_status')
    imp.table_config = imp._get_table_config()
    return imp


def row(attempts=0, **status):
    base = {TRAD_P: 1, TRAD_T: 1, INACTIVE: 1, V2: 2, 'number_reattempts': attempts}
    base.update({k.replace('__', '.'): v for k, v in status.items()})
    return pd.Series(base)


def days_ago(n):
    return datetime.date.today() - datetime.timedelta(days=n)


class ClassifyStatus(unittest.TestCase):
    def setUp(self):
        self.imp = importer()

    def classify(self, r, age):
        return self.imp._classify_game_status(r, COLS, days_ago(age))

    def test_done_when_only_summary_v2_is_status2(self):
        self.assertEqual(self.classify(row(), 2), ('done', []))

    def test_status2_retried_inside_window_regardless_of_attempts(self):
        r = row(attempts=7, **{'nba_data__boxscoretraditionalv3_player': 2})
        self.assertEqual(self.classify(r, mr.STATUS2_RETRY_DAYS), ('retry_status2', [TRAD_P]))

    def test_status2_given_up_after_window(self):
        r = row(**{'nba_data__boxscoretraditionalv3_player': 2})
        self.assertEqual(self.classify(r, mr.STATUS2_RETRY_DAYS + 1), ('done', []))

    def test_often_empty_tables_keep_attempt_cap(self):
        r = row(attempts=mr.MAX_STATUS2_RETRIES, **{'nba_data__boxscoresummaryv3_inactive_players': 2})
        self.assertEqual(self.classify(r, 1), ('done', []))
        r = row(attempts=0, **{'nba_data__boxscoresummaryv3_inactive_players': 2})
        self.assertEqual(self.classify(r, 1), ('retry_status2', [INACTIVE]))

    def test_hard_failure_always_reimported(self):
        r = row(**{'nba_data__boxscoretraditionalv3_team': 0})
        self.assertEqual(self.classify(r, 400), ('reimport', [TRAD_T]))

    def test_pre_cutoff_games_never_retried(self):
        r = row(**{'nba_data__boxscoretraditionalv3_player': 2})
        old = mr.V3_ENDPOINT_CUTOFF_DATE - datetime.timedelta(days=1)
        self.assertEqual(self.imp._classify_game_status(r, COLS, old), ('done', []))


class DropRowsWithoutIds(unittest.TestCase):
    def test_all_null_rows_dropped(self):
        imp = importer()
        df = pd.DataFrame({'gameId': [None, None], 'teamId': [None, None], 'x': [None, None]})
        self.assertEqual(len(imp._drop_rows_without_ids(df, 'boxscoreplayertrackv3_team', 1)), 0)

    def test_partial_null_ids(self):
        imp = importer()
        df = pd.DataFrame({'gameId': ['0022600001'] * 3, 'personId': [1, None, 3]})
        out = imp._drop_rows_without_ids(df, 'boxscoretraditionalv3_player', 1)
        self.assertEqual(list(out.personId), [1, 3])


class NullBlockParseError(unittest.TestCase):
    def test_parser_crash_recognised(self):
        from nba_api.stats.endpoints._parsers import boxscoreplayertrackv3 as p
        parser = p.NBAStatsBoxscorePlayerTrackV3Parser.__new__(p.NBAStatsBoxscorePlayerTrackV3Parser)
        parser.boxscore = {'gameId': '1', 'homeTeam': {'teamId': 1, 'statistics': None}}
        try:  # not assertRaises: it strips the traceback the check walks
            parser.get_team_data()
        except AttributeError as e:
            self.assertTrue(mr._is_null_block_parse_error(e))
        else:
            self.fail('parser did not crash on null statistics')

    def test_other_errors_not_matched(self):
        try:
            None.get('x')
        except AttributeError as e:
            self.assertFalse(mr._is_null_block_parse_error(e))
        self.assertFalse(mr._is_null_block_parse_error(KeyError('x')))


class GameIdPadding(unittest.TestCase):
    def test_reimport_int_id_is_padded(self):
        seen = []

        class FakeEndpoint:
            def __init__(self, game_id, timeout, get_request):
                seen.append(game_id)
                self.nba_response = None

            def get_request(self):
                pass

            def get_data_frames(self):
                return [pd.DataFrame()]

        imp = importer()
        orig_save, mr.raw_api_archive.save_endpoint = mr.raw_api_archive.save_endpoint, lambda *a, **k: True
        orig_sleep, mr.time.sleep = mr.time.sleep, lambda s: None
        try:
            self.assertEqual(imp.process_boxscore_endpoint(FakeEndpoint, 'boxscoretraditionalv3_player', 22400129), 2)
            imp.process_boxscore_endpoint(FakeEndpoint, 'boxscoretraditionalv3_player', '0022600001')
        finally:
            mr.time.sleep = orig_sleep
            mr.raw_api_archive.save_endpoint = orig_save
        self.assertEqual(seen, ['0022400129', '0022600001'])


if __name__ == '__main__':
    unittest.main()
