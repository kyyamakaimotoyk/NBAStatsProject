"""DB- and network-free tests for the nba_api schema check and its loader hook.

    python -m unittest tests.test_api_schema_check -v
"""
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data_engineering import api_schema_check as asc  # noqa: E402
from data_engineering.s3_ingest_loader import report_api_schema  # noqa: E402

# Real column lists for the tables the assertions touch (subset is enough).
DB_COLS = {
    "boxscoreadvancedv3_team": ["gameId", "teamId", "offensiveRating", "effectiveFieldGoalPercentage",
                                "PIE", "estimatedPace"],
    "boxscoreadvancedv3_player": ["gameId", "teamId", "personId", "PIE", "usagePercentage"],
    "boxscoreplayertrackv3_player": ["gameId", "teamId", "personId", "comment", "speed"],
    "boxscoremiscv3_team": ["gameId", "teamId", "pointsPaint", "oppPointsPaint"],
    "game_list": ["GAME_ID", "TEAM_ID", "PTS", "WL", "FT_PCT"],
}


class ScanUsage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.usage, cls.aliases = asc.scan_usage(DB_COLS)
        cls.feats = asc.team_feature_map(DB_COLS, cls.usage, cls.aliases)

    def test_team_feature_columns_found(self):
        u = self.usage["boxscoreadvancedv3_team"]
        self.assertIn("team", u["offensiveRating"])
        self.assertIn("team", u["effectiveFieldGoalPercentage"])
        self.assertNotIn("estimatedPace", u)  # nothing reads it

    def test_sql_alias_is_followed_to_feature_names(self):
        # effectiveFieldGoalPercentage AS EFG_PCT in feature_engineering
        self.assertIn("EFG_PCT", self.aliases["boxscoreadvancedv3_team"]["effectiveFieldGoalPercentage"])
        self.assertGreater(self.feats["boxscoremiscv3_team"]["oppPointsPaint"], 0)
        self.assertGreater(self.feats["game_list"]["FT_PCT"], 0)

    def test_join_does_not_leak_bare_names_across_tables(self):
        # player-table PIE feeds player impact, not the team rolling PIE features
        self.assertNotIn("boxscoreadvancedv3_player", self.feats)

    def test_docstrings_are_not_sql(self):
        # feature_engineering docstrings mention the playertrack player table and "speed"
        self.assertNotIn("speed", self.usage["boxscoreplayertrackv3_player"])
        self.assertIn("team", self.usage["boxscoreplayertrackv3_player"]["comment"])

    def test_alias_map_strings(self):
        # api/queries.py column map: "bsm.pointsPaint" with the JOIN in another string
        self.assertIn("site", self.usage["boxscoremiscv3_team"]["pointsPaint"])


class Coverage(unittest.TestCase):
    def test_every_importer_table_is_checked(self):
        self.assertEqual(asc.check_importer_coverage(), [])

    def test_keep_list_traced(self):
        keep = json.loads(asc.KEEP_LIST_PATH.read_text())
        self.assertEqual(len(keep), len(set(keep)))


class LoaderHook(unittest.TestCase):
    def _run(self, block):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            report_api_schema("2026-11-16T000000Z", block)
        return buf.getvalue()

    def test_alerts_print_error_token(self):
        out = self._run({"nba_api": "9.9", "alerts": ["API_SCHEMA_CHANGED t: removed ['x']", "API_DATA_GAP u"]})
        self.assertEqual(out.count("ERROR: API_"), 2)

    def test_ok_and_missing_block_are_quiet(self):
        self.assertNotIn("ERROR", self._run({"nba_api": "9.9", "alerts": [], "probe_game": "1"}))
        self.assertEqual(self._run(None), "")


if __name__ == "__main__":
    unittest.main()
