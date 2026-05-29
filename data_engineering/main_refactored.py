"""
NBA Data Importer - Refactored Version
Fetches NBA game data from the API and stores it in a MySQL database.
"""

# Project-root bootstrap so cross-folder imports (core.db, ...) work regardless of CWD.
import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

from nba_api.stats.static import teams, players
from nba_api.stats.endpoints import (
    boxscoreadvancedv3, boxscoredefensivev2, boxscorefourfactorsv3,
    boxscorehustlev2, boxscoremiscv3, boxscoreplayertrackv3,
    boxscorescoringv3, boxscoresummaryv2, boxscoresummaryv3, boxscoretraditionalv3,
    boxscoreusagev3, leaguegamefinder
)
from tqdm import tqdm
import pandas as pd
import sqlalchemy as sql
import timeit
import datetime
import logging
from multiprocessing import Pool, cpu_count, Manager
import os
import time
from collections import defaultdict


# ---------------------------------------------------------------------------
# NBA API tuning. The stats.nba.com endpoint is slow and flaky; the defaults
# here trade throughput for reliability. If you stop seeing timeouts you can
# raise NBA_API_WORKERS (gradually) or lower NBA_API_TIMEOUT_SECONDS.
# ---------------------------------------------------------------------------
NBA_API_TIMEOUT_SECONDS = 60   # per-request read timeout (nba_api default is 30)
NBA_API_MAX_RETRIES = 3        # total attempts on a transient (timeout/connection) failure
NBA_API_BACKOFF_BASE = 2       # seconds; sleep grows as base * (2 ** attempt_index)
NBA_API_DEFAULT_WORKERS = 2    # parallel workers for run_import_parallel

# ---------------------------------------------------------------------------
# Status-2 retry policy. Status 2 = "API returned no data for this endpoint."
# It has two very different causes:
#   (a) The game predates an endpoint's data coverage (e.g. V3 endpoints don't
#       go back before ~Oct 2025). Status 2 is then *permanent* — never retry.
#   (b) The game is recent but data isn't posted yet (still in progress, or the
#       endpoint hadn't backfilled when we ran). Status 2 is *provisional* —
#       we should re-call it on the next pipeline run, until the data appears
#       or we've tried enough times.
# We disambiguate by game date vs V3_ENDPOINT_CUTOFF_DATE, and cap retries at
# MAX_STATUS2_RETRIES (using the existing number_reattempts column on
# importedgamesmemory — no schema change required).
# ---------------------------------------------------------------------------
V3_ENDPOINT_CUTOFF_DATE = datetime.date(2025, 10, 1)
MAX_STATUS2_RETRIES = 2


def _is_transient_api_error(exc):
    """Treat read/connect timeouts and pool errors as transient (retry); everything else is fatal."""
    msg = str(exc).lower()
    return (
        'timeout' in msg or 'timed out' in msg
        or 'connection aborted' in msg or 'connection reset' in msg
        or 'remote end closed' in msg or 'connectionpool' in msg
    )


class NBADataImporter:
    def __init__(self):
        self.setup_logging()
        self.setup_pandas()
        self.db_engine = None
        self.connection = None
        self.table_config = self._get_table_config()

    def setup_logging(self):
        """Setup logging configuration"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

    def setup_pandas(self):
        """Configure pandas display options"""
        pd.set_option('display.max_rows', None)
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', None)

    def connect_to_database(self):
        """Establish database connection"""
        try:
            # Close existing connection and engine to prevent leaks
            if self.connection:
                try:
                    self.connection.close()
                except Exception:
                    pass
            if self.db_engine:
                try:
                    self.db_engine.dispose()
                except Exception:
                    pass

            # MySQL config now lives in environment variables (see db.py / .env.example)
            from core.db import get_engine
            self.db_engine = get_engine()
            self.connection = self.db_engine.connect()
            self.logger.info("Database connection established")

        except Exception as e:
            self.logger.error(f"Failed to connect to database: {e}")
            raise

    def _get_table_config(self):
        """
        Return table configuration for boxscore endpoints

        Dictionary structure: 'table_name': [game_id_column, unique_id_column, legacy_expected_count]

        Fields:
        - game_id_column: Column name for the game ID (e.g., 'gameId' or 'GAME_ID')
        - unique_id_column: Column name for unique entity ID (e.g., 'personId', 'teamId', 'OFFICIAL_ID')
        - legacy_expected_count: LEGACY VALUE - Originally intended to track expected row count per game
                                 (e.g., 1 for most tables, 2 for bench stats with 2 rows per team)
                                 NOTE: This value is NO LONGER USED in check_game_data_status()
                                 Kept for backward compatibility only. Status checks now simply verify
                                 if data exists (0=no data, 1=data exists). Status 2 (empty API response)
                                 is tracked in importedGamesMemory during import time.

        The third value was originally from main.py where it validated row counts, but this validation
        was removed because:
        1. Expected counts were incorrect for most tables (e.g., team tables should be 2, not 1)
        2. Player counts vary by game (roster size changes)
        3. Simpler to just check if data exists rather than validate row counts
        """
        return {
            # Advanced Stats (V3) - Player and team advanced metrics
            'nba_data.boxscoreadvancedv3_player': ['gameId', 'personId', 1],
            'nba_data.boxscoreadvancedv3_team': ['gameId', 'teamId', 1],

            # Defensive Stats (V2) - Player and team defensive metrics
            'nba_data.boxscoredefensivev2_player': ['gameId', 'personId', 1],
            'nba_data.boxscoredefensivev2_team': ['gameId', 'teamId', 1],

            # Four Factors (V3) - Shooting efficiency, turnover rate, rebounding, free throws
            'nba_data.boxscorefourfactorsv3_player': ['gameId', 'personId', 1],
            'nba_data.boxscorefourfactorsv3_team': ['gameId', 'teamId', 1],

            # Hustle Stats (V2) - Deflections, loose balls, screen assists, etc.
            'nba_data.boxscorehustlev2_player': ['gameId', 'personId', 1],
            'nba_data.boxscorehustlev2_team': ['gameId', 'teamId', 1],

            # Miscellaneous Stats (V3) - Points off turnovers, second chance points, etc.
            'nba_data.boxscoremiscv3_player': ['gameId', 'personId', 1],
            'nba_data.boxscoremiscv3_team': ['gameId', 'teamId', 1],

            # Player Tracking (V3) - Speed, distance, touches, passes, etc.
            'nba_data.boxscoreplayertrackv3_player': ['gameId', 'personId', 1],
            'nba_data.boxscoreplayertrackv3_team': ['gameId', 'teamId', 1],

            # Scoring Stats (V3) - Points breakdown by shot type and distance
            'nba_data.boxscorescoringv3_player': ['gameId', 'personId', 1],
            'nba_data.boxscorescoringv3_team': ['gameId', 'teamId', 1],

            # BoxScore Summary V2 (Legacy) - Game summary, officials, inactive players
            # Note: V2 uses UPPER_CASE column names
            'nba_data.boxscoresummaryv2_game_info': ['GAME_ID', 'GAME_ID', 1],  # Game date, attendance, duration
            'nba_data.boxscoresummaryv2_inactive_players': ['GAME_ID', 'PLAYER_ID', 1],  # Players not in game
            'nba_data.boxscoresummaryv2_other_stats': ['GAME_ID', 'GAME_ID', 1],  # Paint points, fast break, etc.
            'nba_data.boxscoresummaryv2_referee': ['GAME_ID', 'OFFICIAL_ID', 1],  # Game officials (DEPRECATED - empty data)
            'nba_data.boxscoresummaryv2_summary': ['GAME_ID', 'TEAM_ID', 1],  # Basic game summary

            # BoxScore Summary V3 (Current) - Replaces V2 with updated structure
            # Note: V3 uses camelCase column names
            'nba_data.boxscoresummaryv3_game_summary': ['gameId', 'gameId', 1],  # Game status, period, clock, attendance
            'nba_data.boxscoresummaryv3_game_info': ['gameId', 'gameId', 1],  # Game date, attendance, duration
            'nba_data.boxscoresummaryv3_arena_info': ['gameId', 'gameId', 1],  # Arena name, city, state, timezone
            'nba_data.boxscoresummaryv3_officials': ['gameId', 'personId', 1],  # Game officials (V3 replacement for V2 referee)
            'nba_data.boxscoresummaryv3_line_score': ['gameId', 'teamId', 1],  # Score by quarter/OT
            'nba_data.boxscoresummaryv3_inactive_players': ['gameId', 'personId', 1],  # Players not in game
            'nba_data.boxscoresummaryv3_last_five_meetings': ['gameId', 'gameId', 1],  # Historical matchup data
            'nba_data.boxscoresummaryv3_other_stats': ['gameId', 'teamId', 1],  # Paint points, fast break, etc.

            # Traditional Stats (V3) - Basic box score stats (points, rebounds, assists, etc.)
            'nba_data.boxscoretraditionalv3_bench': ['gameId', 'teamId', 2],  # Legacy value=2 (2 bench rows per team)
            'nba_data.boxscoretraditionalv3_player': ['gameId', 'personId', 1],
            'nba_data.boxscoretraditionalv3_team': ['gameId', 'teamId', 1],

            # Usage Stats (V3) - Usage rate, pace, possessions
            'nba_data.boxscoreusagev3_player': ['gameId', 'personId', 1],
            'nba_data.boxscoreusagev3_team': ['gameId', 'teamId', 1]
        }

    def initialize_teams_data(self):
        """Initialize NBA teams data in the database"""
        self.logger.info("Initializing teams data...")

        nba_teams = teams.get_teams()
        self.logger.info(f"Fetched {len(nba_teams)} teams")

        nba_teams_df = pd.DataFrame(nba_teams)

        try:
            # Check if teams table exists and get existing team IDs
            result = self.connection.execute(sql.text("SELECT id FROM nba_data.nba_teams"))
            existing_team_ids = [r[0] for r in result]
            self.logger.info("Teams table exists, checking for new teams")

            # Add only new teams
            for team in nba_teams:
                if team['id'] not in existing_team_ids:
                    self.logger.info(f"Adding new team: {team['full_name']}")
                    insert_stmt = sql.text(
                        """INSERT INTO nba_data.nba_teams
                           (id, full_name, abbreviation, nickname, city, state, year_founded)
                           VALUES (:id, :full_name, :abbreviation, :nickname, :city, :state, :year_founded)"""
                    )
                    self.connection.execute(insert_stmt, team)
                    self.connection.commit()

        except sql.exc.ProgrammingError:
            # Table doesn't exist, create it
            self.logger.info("Teams table doesn't exist, creating it")
            nba_teams_df.to_sql(name='nba_teams', con=self.db_engine, if_exists='replace', index=False)

    def initialize_players_data(self):
        """Initialize NBA players data in the database"""
        self.logger.info("Initializing players data...")

        nba_players = players.get_players()
        self.logger.info(f"Fetched {len(nba_players)} players")

        nba_players_df = pd.DataFrame(nba_players)

        try:
            # Check if players table exists and get existing player IDs
            result = self.connection.execute(sql.text("SELECT id FROM nba_data.nba_players"))
            existing_player_ids = [r[0] for r in result]
            self.logger.info("Players table exists, checking for new players")

            # Add only new players
            for player in nba_players:
                if player['id'] not in existing_player_ids:
                    self.logger.info(f"Adding new player: {player['full_name']}")
                    insert_stmt = sql.text(
                        """INSERT INTO nba_data.nba_players
                           (id, full_name, first_name, last_name, is_active)
                           VALUES (:id, :full_name, :first_name, :last_name, :is_active)"""
                    )
                    self.connection.execute(insert_stmt, player)
                    self.connection.commit()

        except sql.exc.ProgrammingError:
            # Table doesn't exist, create it
            self.logger.info("Players table doesn't exist, creating it")
            nba_players_df.to_sql(name='nba_players', con=self.db_engine, if_exists='replace', index=False)

    @staticmethod
    def _parse_user_date(s):
        """Accept a YYYY-MM-DD or MM/DD/YYYY string and return a datetime.date.
        Returns None for None/empty input."""
        if s is None or s == '':
            return None
        if isinstance(s, datetime.date) and not isinstance(s, datetime.datetime):
            return s
        if isinstance(s, datetime.datetime):
            return s.date()
        s = str(s).strip()
        for fmt in ('%Y-%m-%d', '%m/%d/%Y'):
            try:
                return datetime.datetime.strptime(s, fmt).date()
            except ValueError:
                continue
        raise ValueError(f"Date must be YYYY-MM-DD or MM/DD/YYYY (got: {s!r})")

    # Default season window — preserves legacy behaviour when no dates are passed.
    DEFAULT_DATE_FROM = '11/22/2025'
    DEFAULT_DATE_TO = '07/01/2026'

    def _games_in_window_from_db(self, date_from_obj, date_to_obj):
        """Return distinct GAME_IDs in game_list between two date objects."""
        try:
            stmt = sql.text(
                "SELECT DISTINCT GAME_ID FROM nba_data.game_list "
                "WHERE GAME_DATE BETWEEN :start AND :end"
            )
            df = pd.read_sql(stmt, self.connection,
                             params={'start': date_from_obj.isoformat(),
                                     'end': date_to_obj.isoformat()})
            return list(pd.unique(df['GAME_ID']))
        except Exception as e:
            self.logger.warning(f"_games_in_window_from_db failed: {e}")
            return []

    def _last_fully_processed_date(self, date_from_obj, date_to_obj):
        """Return the latest date d such that EVERY game in game_list with game_date in
        [date_from_obj, d] is fully present (all tracked tables = 1) in
        importedgamesmemory. Returns None if the very first date in the window has
        any incomplete game (so no narrowing is possible).

        This is the contiguous-prefix check used to narrow the bulk leaguegamefinder
        API window. By narrowing date_from forward to (this date + 1 day), we union
        with the DB-known games in the skipped portion so no game is dropped.
        """
        try:
            gl = pd.read_sql(sql.text(
                "SELECT GAME_DATE, GAME_ID, WL FROM nba_data.game_list "
                "WHERE GAME_DATE BETWEEN :start AND :end"
            ), self.connection,
                params={'start': date_from_obj.isoformat(),
                        'end': date_to_obj.isoformat()})
        except Exception as e:
            self.logger.warning(f"_last_fully_processed_date game_list query failed: {e}")
            return None
        if gl.empty:
            return None
        gl['GAME_DATE'] = pd.to_datetime(gl['GAME_DATE']).dt.date
        gl['GAME_ID'] = gl['GAME_ID'].astype(int)
        # Games with WL=NULL are stuck mid-game in game_list. They MUST be re-
        # fetched via leaguegamefinder (which writes the final PTS/MIN/WL via
        # _update_game_list_table's incomplete-refresh path). So treat any
        # date that contains a WL=NULL game as NOT done, even if every
        # importedgamesmemory entry says otherwise.
        incomplete_gids = set(gl.loc[gl['WL'].isna(), 'GAME_ID'].tolist())
        try:
            ig = pd.read_sql(sql.text("SELECT * FROM nba_data.importedgamesmemory"),
                             self.connection)
        except Exception as e:
            self.logger.warning(f"_last_fully_processed_date importedgamesmemory query failed: {e}")
            return None
        if ig.empty:
            return None
        ig['gameId'] = ig['gameId'].astype(int)
        track_cols = [c for c in self.table_config.keys() if c in ig.columns]
        if not track_cols:
            return None
        # Use the central classifier so this skip-prefix logic agrees with
        # get_imported_games / get_games_needing_reimport. Recent status-2 games
        # with retries remaining are NOT 'done' here, so a contiguous-done prefix
        # correctly stops at the first such game.
        gid_to_date = dict(zip(gl.drop_duplicates('GAME_ID')['GAME_ID'],
                                gl.drop_duplicates('GAME_ID')['GAME_DATE']))
        done_set = {
            int(r['gameId'])
            for _, r in ig.iterrows()
            if int(r['gameId']) not in incomplete_gids
            and self._classify_game_status(r, track_cols, gid_to_date.get(int(r['gameId'])))[0] == 'done'
        }

        # game_list has 2 rows per game (one per team); dedupe so per-date counts are
        # per-game, otherwise `done == n` would never hold (done would be 2x what we expect).
        gl = gl.drop_duplicates(subset=['GAME_ID'])
        gl['_done'] = gl['GAME_ID'].isin(done_set)
        per_date = gl.groupby('GAME_DATE').agg(n=('GAME_ID', 'size'),
                                                done=('_done', 'sum')).reset_index()
        per_date = per_date.sort_values('GAME_DATE').reset_index(drop=True)

        last_done = None
        for _, r in per_date.iterrows():
            if r['done'] == r['n']:
                last_done = r['GAME_DATE']
            else:
                break  # first incomplete date — stop the contiguous prefix
        return last_done

    def get_games_to_process(self, date_from=None, date_to=None, skip_processed=True):
        """Get list of games to process from the API.

        Parameters
        ----------
        date_from, date_to : str or datetime.date, optional
            Window bounds. Accepts YYYY-MM-DD or MM/DD/YYYY. Defaults to the
            hardcoded current-season window (DEFAULT_DATE_FROM/TO) for backwards
            compatibility with old callers.
        skip_processed : bool, default True
            If True, consult importedgamesmemory + game_list to short-circuit:
              - If the entire window is in the past AND every game already has
                all tracked tables = 1, skip the leaguegamefinder API call
                entirely and return GAME_IDs from game_list.
              - Otherwise, narrow date_from forward to (last contiguously-done
                date + 1) so the API only fetches the unprocessed tail. The
                skipped prior games are still returned (union from game_list)
                so the downstream filter can decide what to do with them.
            Set False to force a full re-fetch (e.g. to pick up retroactive
            schedule edits).
        """
        date_from_obj = self._parse_user_date(date_from) or self._parse_user_date(self.DEFAULT_DATE_FROM)
        date_to_obj = self._parse_user_date(date_to) or self._parse_user_date(self.DEFAULT_DATE_TO)
        if date_from_obj > date_to_obj:
            raise ValueError(f"date_from ({date_from_obj}) is after date_to ({date_to_obj})")

        today = datetime.date.today()
        effective_from = date_from_obj
        prior_db_ids = []

        if skip_processed:
            last_done = self._last_fully_processed_date(date_from_obj, date_to_obj)
            if last_done is not None and last_done >= date_to_obj and date_to_obj < today:
                # Whole window is fully processed AND it's all in the past. No API call.
                ids = self._games_in_window_from_db(date_from_obj, date_to_obj)
                self.logger.info(
                    f"All {len(ids)} games in [{date_from_obj}, {date_to_obj}] are already "
                    f"in importedgamesmemory. Skipping leaguegamefinder API call."
                )
                return pd.array(ids, dtype='object') if ids else pd.array([], dtype='object')
            if last_done is not None and last_done >= date_from_obj:
                # Narrow API window past the contiguous done prefix.
                new_from = last_done + datetime.timedelta(days=1)
                if new_from > effective_from:
                    prior_db_ids = self._games_in_window_from_db(date_from_obj,
                                                                  last_done)
                    self.logger.info(
                        f"Narrowing API window: {effective_from} -> {new_from} "
                        f"(skipping {len(prior_db_ids)} already-processed games "
                        f"from game_list)."
                    )
                    effective_from = new_from

        # Bulk API uses MM/DD/YYYY. effective_from may equal or be after date_to_obj
        # if narrowing went past it — in that case fall back to DB-only.
        if effective_from > date_to_obj:
            self.logger.info(
                f"Narrowed window is empty ({effective_from} > {date_to_obj}); "
                f"returning {len(prior_db_ids)} games from game_list only."
            )
            return pd.array(prior_db_ids, dtype='object')

        api_from = effective_from.strftime('%m/%d/%Y')
        api_to = date_to_obj.strftime('%m/%d/%Y')
        self.logger.info(f"Fetching games from {api_from} to {api_to}")

        # Retry the initial games-list fetch too — it sometimes times out before
        # parallelization even starts and causes the whole run to abort.
        last_err = None
        for attempt in range(NBA_API_MAX_RETRIES):
            try:
                gamefinder = leaguegamefinder.LeagueGameFinder(
                    league_id_nullable='00',
                    date_from_nullable=api_from,
                    date_to_nullable=api_to,
                    timeout=NBA_API_TIMEOUT_SECONDS,
                )
                gamefinder_df = gamefinder.get_data_frames()[0]
                break
            except Exception as e:
                last_err = e
                if not _is_transient_api_error(e) or attempt == NBA_API_MAX_RETRIES - 1:
                    raise
                sleep_for = NBA_API_BACKOFF_BASE * (2 ** attempt)
                self.logger.warning(
                    f"⚠️  leaguegamefinder transient error (attempt {attempt + 1}/"
                    f"{NBA_API_MAX_RETRIES}): {e}. Retrying in {sleep_for}s..."
                )
                time.sleep(sleep_for)
        else:  # pragma: no cover
            raise last_err

        # Update game_list table
        self._update_game_list_table(gamefinder_df)

        api_ids = list(pd.unique(gamefinder_df['GAME_ID']))
        if prior_db_ids:
            # Union without losing ordering: API ids first, then any DB-only ids
            seen = {str(g): True for g in api_ids}
            for g in prior_db_ids:
                if str(g) not in seen:
                    api_ids.append(g)
                    seen[str(g)] = True
        return pd.array(api_ids, dtype='object')

    def _update_game_list_table(self, gamefinder_df):
        """Update the game_list table with leaguegamefinder rows.

        Three cases per (GAME_ID, TEAM_ID):
          - New row → INSERT.
          - Existing row with duplicates (count > 1) → DELETE + re-INSERT (de-dup).
          - Existing row with WL IS NULL → DELETE + re-INSERT (REFRESH stale data).
            WL=NULL is the signal that the game was still in progress when we last
            recorded it; the fresh leaguegamefinder row carries the final PTS/MIN/WL.
            Without this branch, mid-game partial data (e.g. CLE 37 / NYK 61 / WL=NULL
            from a game imported at halftime) would persist forever and propagate
            into backfill_actuals as a wrong actual_margin.
          - Existing complete row (WL set, single copy) → leave alone.
        """
        try:
            # Pull the existing snapshot once. Need count for dedup and WL for the
            # incomplete-game refresh.
            stmt = """SELECT GAME_ID, TEAM_ID, COUNT(*) AS n,
                            SUM(CASE WHEN WL IS NULL THEN 1 ELSE 0 END) AS n_incomplete
                     FROM nba_data.game_list
                     GROUP BY GAME_ID, TEAM_ID"""
            result = self.connection.execute(sql.text(stmt))
            existing_games = {(r[0], r[1]): {'count': r[2], 'n_incomplete': r[3]} for r in result}

            n_inserted = n_refreshed = n_dedup = 0
            for index, row in gamefinder_df.iterrows():
                game_id = int(row['GAME_ID'])
                team_id = int(row['TEAM_ID'])
                key = (game_id, team_id)

                if key not in existing_games:
                    gamefinder_df.iloc[[index]].to_sql(
                        name='game_list', con=self.db_engine, if_exists='append', index=False
                    )
                    n_inserted += 1
                    continue

                meta = existing_games[key]
                needs_refresh = (meta['count'] > 1) or (meta['n_incomplete'] > 0)
                if not needs_refresh:
                    continue

                # Replace the existing row(s). We delete all copies for this
                # (game_id, team_id) and re-insert the fresh row, which handles both
                # the dup case and the WL=NULL refresh case in one path.
                self.connection.execute(sql.text(
                    f"DELETE FROM nba_data.game_list WHERE GAME_ID = {game_id} AND TEAM_ID = {team_id}"
                ))
                self.connection.commit()
                gamefinder_df.iloc[[index]].to_sql(
                    name='game_list', con=self.db_engine, if_exists='append', index=False
                )
                if meta['count'] > 1:
                    n_dedup += 1
                else:
                    n_refreshed += 1

            if n_inserted or n_refreshed or n_dedup:
                self.logger.info(
                    f"_update_game_list_table: inserted {n_inserted}, "
                    f"refreshed {n_refreshed} incomplete (WL=NULL), de-duped {n_dedup}"
                )

        except sql.exc.ProgrammingError:
            # Table doesn't exist, create it
            gamefinder_df.to_sql(name='game_list', con=self.db_engine, if_exists='replace', index=False)

    def _load_game_dates(self):
        """Return {int(GAME_ID): datetime.date} from game_list. Used to decide whether
        a status-2 entry is permanent (old game, no V3 coverage) or provisional
        (recent game, data may appear later)."""
        try:
            df = pd.read_sql(sql.text(
                "SELECT DISTINCT GAME_ID, GAME_DATE FROM nba_data.game_list"
            ), self.connection)
            df['GAME_ID'] = df['GAME_ID'].astype(int)
            df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE']).dt.date
            return dict(zip(df['GAME_ID'], df['GAME_DATE']))
        except Exception as e:
            self.logger.warning(f"_load_game_dates failed: {e}")
            return {}

    def _classify_game_status(self, row, table_cols, game_date):
        """Decide what to do with a row from importedgamesmemory.

        Status values: 1=success, 2='API has no data right now', 0=failed.
        The disambiguation of status 2 is the whole point — see the module-level
        comment above MAX_STATUS2_RETRIES.

        Returns (classification, retry_cols):
          ('done',          [])     - finished, skip on next run.
          ('reimport',      [cols]) - has hard failures (status 0); reimport those cols.
          ('retry_status2', [cols]) - recent game with status-2 cols and retries
                                       remaining; reimport those cols.
        """
        statuses = {c: row[c] for c in table_cols if c in row.index}
        if not statuses:
            return ('reimport', list(table_cols))  # nothing recorded yet

        failed = [c for c, s in statuses.items() if s == 0]
        if failed:
            return ('reimport', failed)

        if all(s == 1 for s in statuses.values()):
            return ('done', [])

        # All in {1, 2} with at least one 2.
        status2_cols = [c for c, s in statuses.items() if s == 2]
        # Old games genuinely lack data for V3 endpoints — never retry.
        if game_date is not None and game_date < V3_ENDPOINT_CUTOFF_DATE:
            return ('done', [])
        attempts = int(row.get('number_reattempts', 0) or 0)
        if attempts >= MAX_STATUS2_RETRIES:
            return ('done', [])
        return ('retry_status2', status2_cols)

    def get_imported_games(self):
        """Return GAME_IDs whose processing is 'done' (no further attempts needed).

        See _classify_game_status for the rules. In particular, recent games with
        status-2 columns are NOT 'done' until either the data appears or
        number_reattempts >= MAX_STATUS2_RETRIES.
        """
        try:
            df = pd.read_sql("SELECT * FROM nba_data.importedGamesMemory", self.connection)
            game_dates = self._load_game_dates()
            table_cols = list(self.table_config.keys())
            fully_imported_games = []
            for _, row in df.iterrows():
                game_id = row['gameId']
                gd = game_dates.get(int(game_id))
                cls, _ = self._classify_game_status(row, table_cols, gd)
                if cls == 'done':
                    fully_imported_games.append(game_id)
            self.logger.info(
                f"Found {len(fully_imported_games)} fully imported (done) games out of {len(df)} total records"
            )
            return fully_imported_games
        except sql.exc.ProgrammingError:
            self.logger.info("importedGamesMemory table doesn't exist yet")
            return []
        except Exception as e:
            self.logger.error(f"Error reading importedGamesMemory: {e}")
            return []

    def get_games_needing_reimport(self):
        """Games that need another pass — either hard failures (status 0) or
        recent games with status-2 columns that still have retry budget left.

        Returned dict carries `failed_tables` (the columns the reimport flow
        should re-call), `attempts` (current number_reattempts; the flow
        increments this), and `retry_reason` for logging visibility.
        """
        try:
            df = pd.read_sql("SELECT * FROM nba_data.importedGamesMemory", self.connection)
            game_dates = self._load_game_dates()
            table_cols = list(self.table_config.keys())
            games_to_reimport = {}
            for _, row in df.iterrows():
                game_id = row['gameId']
                gd = game_dates.get(int(game_id))
                cls, cols = self._classify_game_status(row, table_cols, gd)
                if cls == 'done':
                    continue
                current_attempts = row.get('number_reattempts', 0) or 0
                games_to_reimport[game_id] = {
                    'failed_tables': cols,
                    'attempts': int(current_attempts),
                    'retry_reason': cls,  # 'reimport' or 'retry_status2'
                }
            if games_to_reimport:
                n_failure = sum(1 for v in games_to_reimport.values() if v['retry_reason'] == 'reimport')
                n_retry = len(games_to_reimport) - n_failure
                self.logger.info(
                    f"get_games_needing_reimport: {len(games_to_reimport)} games "
                    f"({n_failure} with hard failures, {n_retry} status-2 retries within "
                    f"cap of {MAX_STATUS2_RETRIES})"
                )
            return games_to_reimport
        except sql.exc.ProgrammingError:
            self.logger.info("importedGamesMemory table doesn't exist yet")
            return {}
        except Exception as e:
            self.logger.error(f"Error reading importedGamesMemory: {e}")
            return {}

    def load_all_game_statuses(self):
        """Load all game statuses into memory for fast lookup (Solution 4 optimization).

        Uses _classify_game_status so the run_import_parallel skip-filter aligns
        with get_imported_games / get_games_needing_reimport (i.e. recent
        status-2 games are NOT 'complete' until retries are exhausted).
        """
        try:
            query = "SELECT * FROM nba_data.importedGamesMemory"
            df = pd.read_sql(query, self.connection)
            game_dates = self._load_game_dates()
            table_cols = list(self.table_config.keys())

            game_statuses = {}
            for _, row in df.iterrows():
                game_id = row['gameId']
                gd = game_dates.get(int(game_id))
                cls, _ = self._classify_game_status(row, table_cols, gd)
                game_statuses[game_id] = {
                    'all_complete': (cls == 'done'),
                    'classification': cls,
                    'row': row
                }

            self.logger.info(f"Loaded statuses for {len(game_statuses)} games into memory")
            return game_statuses

        except sql.exc.ProgrammingError:
            self.logger.info("importedGamesMemory table doesn't exist yet")
            return {}
        except Exception as e:
            self.logger.error(f"Error loading game statuses: {e}")
            return {}

    def check_game_data_status(self, game_id):
        """
        Check the status of game data for each table
        Returns:
            0 = No data exists / failed / never attempted
            1 = Data exists in table
            2 = API returned empty (no data available from API) - skip future re-imports
        """
        status = {}

        # First, check importedGamesMemory for status=2 (empty API responses)
        # These should be skipped in future imports since we know API has no data
        memory_status = {}  # Initialize to empty dict
        try:
            query = f"SELECT * FROM nba_data.importedGamesMemory WHERE gameId = {game_id}"
            result = self.connection.execute(sql.text(query))
            memory_row = result.fetchone()

            if memory_row:
                # Convert row to dictionary using column names
                columns = result.keys()
                memory_status = dict(zip(columns, memory_row))
        except Exception as e:
            self.logger.debug(f"Could not read importedGamesMemory for game {game_id}: {e}")
            memory_status = {}

        # Now check each table
        for table_name, config in self.table_config.items():
            column1, column2, _ = config  # Third value unused here (kept for backward compatibility)

            # If importedGamesMemory shows status=2 (empty API), preserve that status
            if memory_status.get(table_name) == 2:
                status[table_name] = 2  # API returned empty, skip future imports
                continue

            try:
                # Simple count query - just check if any rows exist for this game
                stmt = f"""SELECT COUNT(*) FROM {table_name}
                          WHERE {column1} = {game_id}"""
                result = self.connection.execute(sql.text(stmt))
                count = result.fetchone()[0]

                if count > 0:
                    status[table_name] = 1  # Data exists
                else:
                    status[table_name] = 0  # No data exists

            except Exception as e:
                self.logger.error(f"Error checking {table_name}: {e}")
                status[table_name] = 0

        return status

    def process_boxscore_endpoint(self, endpoint_class, table_name, game_id, dataframe_index=0, add_game_id=False, api_cache=None):
        """
        Generic function to process any boxscore endpoint with API response caching (Solution 2)

        Args:
            endpoint_class: The NBA API endpoint class
            table_name: Database table name
            game_id: Game ID to fetch
            dataframe_index: Which dataframe to extract from the response
            add_game_id: Whether to add GAME_ID column
            api_cache: Dictionary to cache API responses (key: endpoint_class.__name__)
        """
        try:
            # Small delay to be respectful to NBA API and avoid rate limiting
            time.sleep(0.6)  # 600ms delay between requests (increased from 100ms)

            # Use cache to avoid redundant API calls (Solution 2)
            endpoint_name = endpoint_class.__name__

            if api_cache is not None and endpoint_name in api_cache:
                # Reuse cached API response
                boxscore_data = api_cache[endpoint_name]
                self.logger.debug(f"Using cached API response for {endpoint_name}")
            else:
                # Fetch from API with retry-on-transient-error (timeouts, connection drops).
                # Non-transient errors (KeyError, 403/429, etc.) fall through to the existing
                # handlers below.
                boxscore_data = None
                last_err = None
                for attempt in range(NBA_API_MAX_RETRIES):
                    try:
                        boxscore_data = endpoint_class(
                            game_id=str(game_id),
                            timeout=NBA_API_TIMEOUT_SECONDS,
                        ).get_data_frames()
                        break
                    except Exception as fetch_err:
                        last_err = fetch_err
                        if not _is_transient_api_error(fetch_err) or attempt == NBA_API_MAX_RETRIES - 1:
                            raise
                        sleep_for = NBA_API_BACKOFF_BASE * (2 ** attempt)
                        self.logger.warning(
                            f"⚠️  Transient {type(fetch_err).__name__} for {table_name}, "
                            f"game {game_id} (attempt {attempt + 1}/{NBA_API_MAX_RETRIES}): "
                            f"{fetch_err}. Retrying in {sleep_for}s..."
                        )
                        time.sleep(sleep_for)
                if api_cache is not None:
                    api_cache[endpoint_name] = boxscore_data
                    self.logger.debug(f"Cached API response for {endpoint_name}")

            df = boxscore_data[dataframe_index]

            # Add GAME_ID column if needed (for summary endpoints)
            if add_game_id:
                df['GAME_ID'] = game_id

            # Check if dataframe is empty (API returned no data)
            if len(df) == 0:
                self.logger.warning(f"⚠️  API returned EMPTY dataframe for {table_name}, game {game_id} (0 rows)")
                # Return 2 to indicate: API call succeeded but no data available
                return 2

            # Save to database
            df.to_sql(name=table_name, con=self.db_engine, if_exists='append', index=False)
            self.connection.commit()

            # Return 1 to indicate: Success with data inserted
            return 1

        except KeyError as e:
            # KeyError means API response is missing expected keys (resultSet, boxScoreSummary, etc.)
            # For recent games (within 5 days), this might be temporary - retry
            # For old games, this means data doesn't exist - don't retry

            try:
                # Try to get game date from existing data to determine if game is recent
                game_date_query = """
                    SELECT GAME_DATE
                    FROM nba_data.game_list
                    WHERE GAME_ID = :game_id
                    LIMIT 1
                """
                result = self.connection.execute(sql.text(game_date_query), {"game_id": game_id})
                game_date_row = result.fetchone()

                if game_date_row:
                    game_date = pd.to_datetime(game_date_row[0])
                    days_ago = (datetime.datetime.now(datetime.timezone.utc) - game_date.tz_localize('UTC')).days

                    if days_ago <= 5:
                        # Recent game - data might not be available yet, retry
                        self.logger.warning(f"⚠️  Recent game ({days_ago} days ago) - API missing key {e} for {table_name}, game {game_id} - will retry")
                        return 0  # Failed - retry on next run
                    else:
                        # Old game - data doesn't exist
                        self.logger.warning(f"⚠️  Old game ({days_ago} days ago) - API has no data for {table_name}, game {game_id}: Missing key {e}")
                        return 2  # API has no data - skip future imports
                else:
                    # Can't determine game date, retry to be safe
                    self.logger.warning(f"⚠️  Cannot determine game date - API missing key {e} for {table_name}, game {game_id}")
                    return 2  # Failed - don't try again

            except Exception as date_error:
                # If we can't check the date, retry to be safe
                self.logger.warning(f"⚠️  Error checking game date - API missing key {e} for {table_name}, game {game_id}")
                return 2  # Failed - don't try again

        except Exception as e:
            error_msg = str(e).lower()

            # Detect rate limiting errors
            if '429' in error_msg or 'too many requests' in error_msg:
                self.logger.error(f"⚠️  RATE LIMIT ERROR for {table_name}, game {game_id}: {e}")
            elif '403' in error_msg or 'forbidden' in error_msg:
                self.logger.error(f"⚠️  BLOCKED/FORBIDDEN for {table_name}, game {game_id}: {e}")
            elif 'timeout' in error_msg or 'timed out' in error_msg:
                self.logger.error(f"⚠️  TIMEOUT for {table_name}, game {game_id}: {e}")
            else:
                self.logger.error(f"Failed to import {table_name} for game_id = {game_id}: {e}")

            # Return 0 to indicate: Import failed
            return 0

    def clean_existing_data(self, table_name, game_id, column_name):
        """Clean existing data for a game from a table"""
        try:
            delete_stmt = f"DELETE FROM {table_name} WHERE {column_name} = {game_id}"
            self.connection.execute(sql.text(delete_stmt))
            self.connection.commit()
            self.logger.info(f"Cleaned existing data for game {game_id} from {table_name}")

        except Exception as e:
            self.logger.error(f"Failed to clean data from {table_name}: {e}")

    def process_single_game(self, game_id):
        """Process all boxscore data for a single game"""
        self.logger.info(f"Processing game {game_id}")

        # Check current status
        status = self.check_game_data_status(game_id)

        # Track actual import results for this game
        import_results = {}

        # API response cache to avoid redundant calls (Solution 2)
        api_cache = {}

        # Check game date - BoxScoreSummaryV3 endpoints are only available for games from October 2025 onwards
        # For older games, skip these endpoints and mark as status 2 (API has no data)
        try:
            game_date_query = """
                SELECT GAME_DATE
                FROM nba_data.game_list
                WHERE GAME_ID = :game_id
                LIMIT 1
            """
            result = self.connection.execute(sql.text(game_date_query), {"game_id": game_id})
            game_date_row = result.fetchone()

            if game_date_row:
                game_date = pd.to_datetime(game_date_row[0])
                cutoff_date = pd.to_datetime('2025-10-01')

                # If game is before October 1, 2025, skip all boxscoresummaryv3 endpoints
                if game_date < cutoff_date:
                    self.logger.info(f"Game {game_id} occurred on {game_date.date()} (before Oct 2025) - skipping BoxScoreSummaryV3 endpoints")

                    # List of all boxscoresummaryv3 tables
                    v3_summary_tables = [
                        'nba_data.boxscoresummaryv3_game_summary',
                        'nba_data.boxscoresummaryv3_game_info',
                        'nba_data.boxscoresummaryv3_arena_info',
                        'nba_data.boxscoresummaryv3_officials',
                        'nba_data.boxscoresummaryv3_line_score',
                        'nba_data.boxscoresummaryv3_inactive_players',
                        'nba_data.boxscoresummaryv3_last_five_meetings',
                        'nba_data.boxscoresummaryv3_other_stats',
                    ]

                    # Set all V3 summary tables to status 2 (API has no data)
                    for table_name in v3_summary_tables:
                        status[table_name] = 2
                        import_results[table_name] = 2

                # If game is on or after October 1, 2025, skip all boxscoresummaryv2 endpoints
                else:
                    self.logger.info(f"Game {game_id} occurred on {game_date.date()} (Oct 2025 or later) - skipping BoxScoreSummaryV2 endpoints")

                    # List of all boxscoresummaryv2 tables
                    v2_summary_tables = [
                        'nba_data.boxscoresummaryv2_summary',
                        'nba_data.boxscoresummaryv2_referee',
                        'nba_data.boxscoresummaryv2_inactive_players',
                        'nba_data.boxscoresummaryv2_other_stats',
                        'nba_data.boxscoresummaryv2_game_info',
                    ]

                    # Set all V2 summary tables to status 2 (API has no data)
                    for table_name in v2_summary_tables:
                        status[table_name] = 2
                        import_results[table_name] = 2
        except Exception as e:
            self.logger.warning(f"Could not check game date for V3 endpoint filtering: {e}")

        # Regular boxscore endpoints (player/team stats)
        # Dictionary structure: 'table_name': (endpoint_class, db_table_name, dataframe_index)
        # - endpoint_class: NBA API endpoint class to call
        # - db_table_name: Database table name (without schema prefix)
        # - dataframe_index: Which dataframe to extract from API response (0=first, 1=second, etc.)
        endpoints = {
            'nba_data.boxscoreadvancedv3_player': (boxscoreadvancedv3.BoxScoreAdvancedV3, 'boxscoreadvancedv3_player', 0),
            'nba_data.boxscoreadvancedv3_team': (boxscoreadvancedv3.BoxScoreAdvancedV3, 'boxscoreadvancedv3_team', 1),
            'nba_data.boxscoredefensivev2_player': (boxscoredefensivev2.BoxScoreDefensiveV2, 'boxscoredefensivev2_player', 0),
            'nba_data.boxscoredefensivev2_team': (boxscoredefensivev2.BoxScoreDefensiveV2, 'boxscoredefensivev2_team', 1),
            'nba_data.boxscorefourfactorsv3_player': (boxscorefourfactorsv3.BoxScoreFourFactorsV3, 'boxscorefourfactorsv3_player', 0),
            'nba_data.boxscorefourfactorsv3_team': (boxscorefourfactorsv3.BoxScoreFourFactorsV3, 'boxscorefourfactorsv3_team', 1),
            'nba_data.boxscorehustlev2_player': (boxscorehustlev2.BoxScoreHustleV2, 'boxscorehustlev2_player', 0),
            'nba_data.boxscorehustlev2_team': (boxscorehustlev2.BoxScoreHustleV2, 'boxscorehustlev2_team', 1),
            'nba_data.boxscoremiscv3_player': (boxscoremiscv3.BoxScoreMiscV3, 'boxscoremiscv3_player', 0),
            'nba_data.boxscoremiscv3_team': (boxscoremiscv3.BoxScoreMiscV3, 'boxscoremiscv3_team', 1),
            'nba_data.boxscoreplayertrackv3_player': (boxscoreplayertrackv3.BoxScorePlayerTrackV3, 'boxscoreplayertrackv3_player', 0),
            'nba_data.boxscoreplayertrackv3_team': (boxscoreplayertrackv3.BoxScorePlayerTrackV3, 'boxscoreplayertrackv3_team', 1),
            'nba_data.boxscorescoringv3_player': (boxscorescoringv3.BoxScoreScoringV3, 'boxscorescoringv3_player', 0),
            'nba_data.boxscorescoringv3_team': (boxscorescoringv3.BoxScoreScoringV3, 'boxscorescoringv3_team', 1),
            'nba_data.boxscoretraditionalv3_player': (boxscoretraditionalv3.BoxScoreTraditionalV3, 'boxscoretraditionalv3_player', 0),
            'nba_data.boxscoretraditionalv3_bench': (boxscoretraditionalv3.BoxScoreTraditionalV3, 'boxscoretraditionalv3_bench', 1),
            'nba_data.boxscoretraditionalv3_team': (boxscoretraditionalv3.BoxScoreTraditionalV3, 'boxscoretraditionalv3_team', 2),
            'nba_data.boxscoreusagev3_player': (boxscoreusagev3.BoxScoreUsageV3, 'boxscoreusagev3_player', 0),
            'nba_data.boxscoreusagev3_team': (boxscoreusagev3.BoxScoreUsageV3, 'boxscoreusagev3_team', 1),
        }

        # BoxScoreSummaryV2 endpoints (game summary, officials, inactive players, etc.)
        # Dictionary structure: 'table_name': (endpoint_class, db_table_name, dataframe_index, add_game_id)
        # - endpoint_class: NBA API endpoint class to call
        # - db_table_name: Database table name (without schema prefix)
        # - dataframe_index: Which dataframe to extract from API response
        # - add_game_id: If True, manually add GAME_ID column (API doesn't include it); If False, gameId already in dataframe
        summary_endpoints = {
            'nba_data.boxscoresummaryv2_summary': (boxscoresummaryv2.BoxScoreSummaryV2, 'boxscoresummaryv2_summary', 1, True),
            'nba_data.boxscoresummaryv2_referee': (boxscoresummaryv2.BoxScoreSummaryV2, 'boxscoresummaryv2_referee', 2, True),
            'nba_data.boxscoresummaryv2_inactive_players': (boxscoresummaryv2.BoxScoreSummaryV2, 'boxscoresummaryv2_inactive_players', 3, True),
            'nba_data.boxscoresummaryv2_other_stats': (boxscoresummaryv2.BoxScoreSummaryV2, 'boxscoresummaryv2_other_stats', 6, False),
            'nba_data.boxscoresummaryv2_game_info': (boxscoresummaryv2.BoxScoreSummaryV2, 'boxscoresummaryv2_game_info', 7, False),
        }

        # BoxScoreSummaryV3 endpoints (new V3 API with updated structure)
        # Dictionary structure: 'table_name': (endpoint_class, db_table_name, dataframe_index, add_game_id)
        # Note: All V3 dataframes include gameId natively, so add_game_id=False for all
        summary_v3_endpoints = {
            'nba_data.boxscoresummaryv3_game_summary': (boxscoresummaryv3.BoxScoreSummaryV3, 'boxscoresummaryv3_game_summary', 0, False),
            'nba_data.boxscoresummaryv3_game_info': (boxscoresummaryv3.BoxScoreSummaryV3, 'boxscoresummaryv3_game_info', 1, False),
            'nba_data.boxscoresummaryv3_arena_info': (boxscoresummaryv3.BoxScoreSummaryV3, 'boxscoresummaryv3_arena_info', 2, False),
            'nba_data.boxscoresummaryv3_officials': (boxscoresummaryv3.BoxScoreSummaryV3, 'boxscoresummaryv3_officials', 3, False),
            'nba_data.boxscoresummaryv3_line_score': (boxscoresummaryv3.BoxScoreSummaryV3, 'boxscoresummaryv3_line_score', 4, False),
            'nba_data.boxscoresummaryv3_inactive_players': (boxscoresummaryv3.BoxScoreSummaryV3, 'boxscoresummaryv3_inactive_players', 5, False),
            'nba_data.boxscoresummaryv3_last_five_meetings': (boxscoresummaryv3.BoxScoreSummaryV3, 'boxscoresummaryv3_last_five_meetings', 6, False),
            'nba_data.boxscoresummaryv3_other_stats': (boxscoresummaryv3.BoxScoreSummaryV3, 'boxscoresummaryv3_other_stats', 7, False),
        }

        # Process regular endpoints
        for table_name, (endpoint_class, db_table, df_index) in endpoints.items():
            if status[table_name] == 1:
                self.logger.info(f"Game {game_id} already has data in {table_name}")
                import_results[table_name] = 1  # Already exists
                continue
            elif status[table_name] == 2:
                self.logger.info(f"Game {game_id} - {table_name} previously returned empty, skipping")
                import_results[table_name] = 2  # API has no data
                continue

            # Process the endpoint and record the result (with API caching)
            # Result: 0=failed, 1=success with data, 2=success but no data
            result = self.process_boxscore_endpoint(endpoint_class, db_table, game_id, df_index, api_cache=api_cache)
            import_results[table_name] = result

        # Process summary endpoints
        for table_name, (endpoint_class, db_table, df_index, add_game_id) in summary_endpoints.items():
            if status[table_name] == 1:
                self.logger.info(f"Game {game_id} already has data in {table_name}")
                import_results[table_name] = 1  # Already exists
                continue
            elif status[table_name] == 2:
                self.logger.info(f"Game {game_id} - {table_name} previously returned empty, skipping")
                import_results[table_name] = 2  # API has no data
                continue

            # Process the endpoint and record the result (with API caching)
            # Result: 0=failed, 1=success with data, 2=success but no data
            result = self.process_boxscore_endpoint(endpoint_class, db_table, game_id, df_index, add_game_id, api_cache=api_cache)
            import_results[table_name] = result

        # Process BoxScoreSummaryV3 endpoints
        for table_name, (endpoint_class, db_table, df_index, add_game_id) in summary_v3_endpoints.items():
            if status[table_name] == 1:
                self.logger.info(f"Game {game_id} already has data in {table_name}")
                import_results[table_name] = 1  # Already exists
                continue
            elif status[table_name] == 2:
                self.logger.info(f"Game {game_id} - {table_name} previously returned empty, skipping")
                import_results[table_name] = 2  # API has no data
                continue

            # Process the endpoint and record the result (with API caching)
            # Result: 0=failed, 1=success with data, 2=success but no data
            result = self.process_boxscore_endpoint(endpoint_class, db_table, game_id, df_index, add_game_id, api_cache=api_cache)
            import_results[table_name] = result

        # Log cache efficiency stats
        total_endpoints = len(endpoints) + len(summary_endpoints) + len(summary_v3_endpoints)
        cache_hits = sum(1 for key in api_cache.keys())
        self.logger.info(f"API Cache: {cache_hits} unique endpoints called for {total_endpoints} tables (saved {total_endpoints - cache_hits} API calls)")

        # Record that this game has been processed with actual results
        self._record_game_processed(game_id, import_results)

    def _record_game_processed(self, game_id, import_results, is_reattempt=False, previous_attempts=0):
        """Record that a game has been processed with actual import results"""
        try:
            # ALWAYS check if record exists first to prevent duplicates
            check_query = f"SELECT COUNT(*) as count FROM nba_data.importedgamesmemory WHERE gameId = {game_id}"
            result = self.connection.execute(sql.text(check_query))
            row = result.fetchone()
            record_exists = row[0] > 0 if row else False

            if record_exists:
                # Record exists - UPDATE it
                self._update_game_record(game_id, import_results, previous_attempts + 1 if is_reattempt else 0)
            else:
                # Record doesn't exist - INSERT new record
                record = {
                    'gameId': [game_id],
                    'dateImportedToDB': [datetime.datetime.now(datetime.timezone.utc)],
                    'number_reattempts': [0]
                }

                # Add actual status for each table based on import results
                for table_name in self.table_config.keys():
                    # Use actual result if available, otherwise mark as 0 (failed/not attempted)
                    record[table_name] = [import_results.get(table_name, 0)]

                record_df = pd.DataFrame(record)
                record_df.to_sql(name='importedgamesmemory', con=self.db_engine, if_exists='append', index=False)
                self.connection.commit()

            # Log summary of results
            successful = sum(1 for v in import_results.values() if v == 1)
            failed = sum(1 for v in import_results.values() if v == 0)
            attempt_msg = f" (reattempt #{previous_attempts + 1})" if is_reattempt else ""
            action = "updated" if record_exists else "created"
            self.logger.info(f"Game {game_id} {action}{attempt_msg}: {successful} successful, {failed} failed")

        except Exception as e:
            self.logger.error(f"Failed to record game {game_id} as processed: {e}")

    def _update_game_record(self, game_id, import_results, new_attempt_count):
        """Update an existing game record in importedGamesMemory"""
        try:
            # Build UPDATE statement for each table column
            update_parts = []
            for table_name, status in import_results.items():
                # Escape table name properly for SQL column names
                column_name = f"`{table_name}`"
                update_parts.append(f"{column_name} = {status}")

            # Add dateImportedToDB and number_reattempts
            update_parts.append(f"dateImportedToDB = '{datetime.datetime.now(datetime.timezone.utc)}'")
            update_parts.append(f"number_reattempts = {new_attempt_count}")

            update_stmt = f"""UPDATE nba_data.importedgamesmemory
                             SET {', '.join(update_parts)}
                             WHERE gameId = {game_id}"""

            self.connection.execute(sql.text(update_stmt))
            self.connection.commit()
            self.logger.info(f"Updated record for game {game_id} (attempt #{new_attempt_count})")

        except Exception as e:
            self.logger.error(f"Failed to update game {game_id} record: {e}")

    def process_game_reimport(self, game_id, failed_tables_list, previous_attempts):
        """Re-import only the failed tables for a game"""
        self.logger.info(f"Re-importing {len(failed_tables_list)} failed tables for game {game_id}")

        # Get current database status
        status = self.check_game_data_status(game_id)

        # Track results (start with existing status for tables not being reimported)
        import_results = {}

        # API response cache to avoid redundant calls (Solution 2)
        api_cache = {}

        # Check game date - BoxScoreSummaryV3 endpoints are only available for games from October 2025 onwards
        # For older games, skip these endpoints and mark as status 2 (API has no data)
        try:
            game_date_query = """
                SELECT GAME_DATE
                FROM nba_data.game_list
                WHERE GAME_ID = :game_id
                LIMIT 1
            """
            result = self.connection.execute(sql.text(game_date_query), {"game_id": game_id})
            game_date_row = result.fetchone()

            if game_date_row:
                game_date = pd.to_datetime(game_date_row[0])
                cutoff_date = pd.to_datetime('2025-10-01')

                # If game is before October 1, 2025, skip all boxscoresummaryv3 endpoints
                if game_date < cutoff_date:
                    self.logger.info(f"Re-import: Game {game_id} occurred on {game_date.date()} (before Oct 2025) - skipping BoxScoreSummaryV3 endpoints")

                    # List of all boxscoresummaryv3 tables
                    v3_summary_tables = [
                        'nba_data.boxscoresummaryv3_game_summary',
                        'nba_data.boxscoresummaryv3_game_info',
                        'nba_data.boxscoresummaryv3_arena_info',
                        'nba_data.boxscoresummaryv3_officials',
                        'nba_data.boxscoresummaryv3_line_score',
                        'nba_data.boxscoresummaryv3_inactive_players',
                        'nba_data.boxscoresummaryv3_last_five_meetings',
                        'nba_data.boxscoresummaryv3_other_stats',
                    ]

                    # Set all V3 summary tables to status 2 (API has no data)
                    for table_name in v3_summary_tables:
                        status[table_name] = 2
                        import_results[table_name] = 2
                        # Remove from failed_tables_list if present
                        if table_name in failed_tables_list:
                            failed_tables_list.remove(table_name)

                # If game is on or after October 1, 2025, skip all boxscoresummaryv2 endpoints
                else:
                    self.logger.info(f"Re-import: Game {game_id} occurred on {game_date.date()} (Oct 2025 or later) - skipping BoxScoreSummaryV2 endpoints")

                    # List of all boxscoresummaryv2 tables
                    v2_summary_tables = [
                        'nba_data.boxscoresummaryv2_summary',
                        'nba_data.boxscoresummaryv2_referee',
                        'nba_data.boxscoresummaryv2_inactive_players',
                        'nba_data.boxscoresummaryv2_other_stats',
                        'nba_data.boxscoresummaryv2_game_info',
                    ]

                    # Set all V2 summary tables to status 2 (API has no data)
                    for table_name in v2_summary_tables:
                        status[table_name] = 2
                        import_results[table_name] = 2
                        # Remove from failed_tables_list if present
                        if table_name in failed_tables_list:
                            failed_tables_list.remove(table_name)
        except Exception as e:
            self.logger.warning(f"Could not check game date for V3 endpoint filtering in re-import: {e}")

        # Set all tables to their current status first
        for table_name in self.table_config.keys():
            if status.get(table_name) == 1:
                import_results[table_name] = 1
            elif status.get(table_name) == 2:
                import_results[table_name] = 2  # API has no data, skip re-import

        # Prepare endpoint mappings
        endpoints = {
            'nba_data.boxscoreadvancedv3_player': (boxscoreadvancedv3.BoxScoreAdvancedV3, 'boxscoreadvancedv3_player', 0, False),
            'nba_data.boxscoreadvancedv3_team': (boxscoreadvancedv3.BoxScoreAdvancedV3, 'boxscoreadvancedv3_team', 1, False),
            'nba_data.boxscoredefensivev2_player': (boxscoredefensivev2.BoxScoreDefensiveV2, 'boxscoredefensivev2_player', 0, False),
            'nba_data.boxscoredefensivev2_team': (boxscoredefensivev2.BoxScoreDefensiveV2, 'boxscoredefensivev2_team', 1, False),
            'nba_data.boxscorefourfactorsv3_player': (boxscorefourfactorsv3.BoxScoreFourFactorsV3, 'boxscorefourfactorsv3_player', 0, False),
            'nba_data.boxscorefourfactorsv3_team': (boxscorefourfactorsv3.BoxScoreFourFactorsV3, 'boxscorefourfactorsv3_team', 1, False),
            'nba_data.boxscorehustlev2_player': (boxscorehustlev2.BoxScoreHustleV2, 'boxscorehustlev2_player', 0, False),
            'nba_data.boxscorehustlev2_team': (boxscorehustlev2.BoxScoreHustleV2, 'boxscorehustlev2_team', 1, False),
            'nba_data.boxscoremiscv3_player': (boxscoremiscv3.BoxScoreMiscV3, 'boxscoremiscv3_player', 0, False),
            'nba_data.boxscoremiscv3_team': (boxscoremiscv3.BoxScoreMiscV3, 'boxscoremiscv3_team', 1, False),
            'nba_data.boxscoreplayertrackv3_player': (boxscoreplayertrackv3.BoxScorePlayerTrackV3, 'boxscoreplayertrackv3_player', 0, False),
            'nba_data.boxscoreplayertrackv3_team': (boxscoreplayertrackv3.BoxScorePlayerTrackV3, 'boxscoreplayertrackv3_team', 1, False),
            'nba_data.boxscorescoringv3_player': (boxscorescoringv3.BoxScoreScoringV3, 'boxscorescoringv3_player', 0, False),
            'nba_data.boxscorescoringv3_team': (boxscorescoringv3.BoxScoreScoringV3, 'boxscorescoringv3_team', 1, False),
            'nba_data.boxscoresummaryv2_summary': (boxscoresummaryv2.BoxScoreSummaryV2, 'boxscoresummaryv2_summary', 1, True),
            'nba_data.boxscoresummaryv2_referee': (boxscoresummaryv2.BoxScoreSummaryV2, 'boxscoresummaryv2_referee', 2, True),
            'nba_data.boxscoresummaryv2_inactive_players': (boxscoresummaryv2.BoxScoreSummaryV2, 'boxscoresummaryv2_inactive_players', 3, True),
            'nba_data.boxscoresummaryv2_other_stats': (boxscoresummaryv2.BoxScoreSummaryV2, 'boxscoresummaryv2_other_stats', 6, False),
            'nba_data.boxscoresummaryv2_game_info': (boxscoresummaryv2.BoxScoreSummaryV2, 'boxscoresummaryv2_game_info', 7, False),
            'nba_data.boxscoresummaryv3_game_summary': (boxscoresummaryv3.BoxScoreSummaryV3, 'boxscoresummaryv3_game_summary', 0, False),
            'nba_data.boxscoresummaryv3_game_info': (boxscoresummaryv3.BoxScoreSummaryV3, 'boxscoresummaryv3_game_info', 1, False),
            'nba_data.boxscoresummaryv3_arena_info': (boxscoresummaryv3.BoxScoreSummaryV3, 'boxscoresummaryv3_arena_info', 2, False),
            'nba_data.boxscoresummaryv3_officials': (boxscoresummaryv3.BoxScoreSummaryV3, 'boxscoresummaryv3_officials', 3, False),
            'nba_data.boxscoresummaryv3_line_score': (boxscoresummaryv3.BoxScoreSummaryV3, 'boxscoresummaryv3_line_score', 4, False),
            'nba_data.boxscoresummaryv3_inactive_players': (boxscoresummaryv3.BoxScoreSummaryV3, 'boxscoresummaryv3_inactive_players', 5, False),
            'nba_data.boxscoresummaryv3_last_five_meetings': (boxscoresummaryv3.BoxScoreSummaryV3, 'boxscoresummaryv3_last_five_meetings', 6, False),
            'nba_data.boxscoresummaryv3_other_stats': (boxscoresummaryv3.BoxScoreSummaryV3, 'boxscoresummaryv3_other_stats', 7, False),
            'nba_data.boxscoretraditionalv3_player': (boxscoretraditionalv3.BoxScoreTraditionalV3, 'boxscoretraditionalv3_player', 0, False),
            'nba_data.boxscoretraditionalv3_bench': (boxscoretraditionalv3.BoxScoreTraditionalV3, 'boxscoretraditionalv3_bench', 1, False),
            'nba_data.boxscoretraditionalv3_team': (boxscoretraditionalv3.BoxScoreTraditionalV3, 'boxscoretraditionalv3_team', 2, False),
            'nba_data.boxscoreusagev3_player': (boxscoreusagev3.BoxScoreUsageV3, 'boxscoreusagev3_player', 0, False),
            'nba_data.boxscoreusagev3_team': (boxscoreusagev3.BoxScoreUsageV3, 'boxscoreusagev3_team', 1, False),
        }

        # Process only the failed tables
        for table_name in failed_tables_list:
            if table_name not in endpoints:
                self.logger.warning(f"Unknown table {table_name}, skipping")
                import_results[table_name] = 0
                continue

            endpoint_class, db_table, df_index, add_game_id = endpoints[table_name]

            # Attempt import (with API caching)
            # Result: 0=failed, 1=success with data, 2=success but no data
            result = self.process_boxscore_endpoint(endpoint_class, db_table, game_id, df_index, add_game_id, api_cache=api_cache)
            import_results[table_name] = result

            if result == 1:
                self.logger.info(f"Successfully re-imported {table_name} for game {game_id}")
            elif result == 2:
                self.logger.warning(f"Re-imported {table_name} for game {game_id} - API returned no data")
            else:
                self.logger.error(f"Failed to re-import {table_name} for game {game_id}")

        # Update the record with new results
        self._record_game_processed(game_id, import_results, is_reattempt=True, previous_attempts=previous_attempts)

    def run_import(self, date_from=None, date_to=None, skip_processed=True):
        """Main function to run the complete import process.

        date_from/date_to: optional window bounds (YYYY-MM-DD / MM/DD/YYYY / date).
        skip_processed: when True, narrow or skip the leaguegamefinder API call
        using importedgamesmemory (see get_games_to_process docstring).
        """
        start_time = timeit.default_timer()

        try:
            # Initialize
            self.connect_to_database()
            self.initialize_teams_data()
            self.initialize_players_data()

            # Get games to process
            games_list = self.get_games_to_process(date_from=date_from, date_to=date_to,
                                                    skip_processed=skip_processed)
            imported_games = self.get_imported_games()
            games_needing_reimport = self.get_games_needing_reimport()

            self.logger.info(f"Found {len(games_list)} games to check")
            self.logger.info(f"Already fully imported: {len(imported_games)} games")
            self.logger.info(f"Games needing re-import: {len(games_needing_reimport)} games")

            # Process new games
            games_processed = 0
            for game_id in tqdm(games_list, desc="Processing new games"):
                if int(game_id) not in imported_games and game_id not in games_needing_reimport:
                    self.process_single_game(game_id)
                    games_processed += 1
                else:
                    self.logger.info(f"Game {game_id} already processed, skipping")

            # Re-import failed tables for games that need it
            games_reimported = 0
            if games_needing_reimport:
                self.logger.info(f"\nStarting re-import process for {len(games_needing_reimport)} games...")
                for game_id, info in tqdm(games_needing_reimport.items(), desc="Re-importing failed tables"):
                    self.process_game_reimport(
                        game_id,
                        info['failed_tables'],
                        info['attempts']
                    )
                    games_reimported += 1

            end_time = timeit.default_timer()
            self.logger.info("=" * 80)
            self.logger.info(f"Process completed in {end_time - start_time:.2f} seconds")
            self.logger.info(f"Processed {games_processed} new games")
            self.logger.info(f"Re-imported {games_reimported} games with failed tables")
            self.logger.info("=" * 80)

        except Exception as e:
            self.logger.error(f"Import failed: {e}")
            raise
        finally:
            if self.connection:
                self.connection.close()
            if self.db_engine:
                self.db_engine.dispose()

    def run_import_parallel(self, num_workers=None, date_from=None, date_to=None,
                            skip_processed=True):
        """
        Main function to run import process with parallel processing (Solution 1)

        Args:
            num_workers: Number of parallel workers. If None, defaults to 2 (safe for NBA API rate limits)
            date_from, date_to: window bounds (YYYY-MM-DD / MM/DD/YYYY / date)
            skip_processed: when True, narrow or skip the leaguegamefinder API call
                using importedgamesmemory (see get_games_to_process docstring)
        """
        start_time = timeit.default_timer()

        try:
            # Determine number of workers (default to 2 to avoid API rate limiting)
            if num_workers is None:
                num_workers = NBA_API_DEFAULT_WORKERS

            self.logger.info("=" * 80)
            self.logger.info(f"PARALLEL IMPORT MODE: Using {num_workers} workers")
            self.logger.info(f"CPU cores available: {cpu_count()}")
            self.logger.warning(f"⚠️  Using {num_workers} workers to avoid NBA API rate limits")
            self.logger.warning(f"⚠️  Increase workers gradually if no rate limit errors occur")
            self.logger.info("=" * 80)

            # Initialize connection for main process
            self.connect_to_database()
            self.initialize_teams_data()
            self.initialize_players_data()

            # Get games to process and load statuses into memory (Solution 4)
            games_list = self.get_games_to_process(date_from=date_from, date_to=date_to,
                                                    skip_processed=skip_processed)
            game_statuses = self.load_all_game_statuses()
            games_needing_reimport = self.get_games_needing_reimport()

            self.logger.info(f"Found {len(games_list)} total games to check")
            self.logger.info(f"Games with complete data: {sum(1 for s in game_statuses.values() if s['all_complete'])} games")
            self.logger.info(f"Games needing re-import: {len(games_needing_reimport)} games")

            # Filter out fully imported games (Solution 4 optimization)
            games_to_process = []
            for game_id in games_list:
                # Skip if game is fully imported
                if game_id in game_statuses and game_statuses[game_id]['all_complete']:
                    continue
                # Skip if already in reimport queue
                if game_id in games_needing_reimport:
                    continue
                games_to_process.append(game_id)

            self.logger.info(f"Games requiring processing: {len(games_to_process)} games")
            self.logger.info("=" * 80)

            # Close main connection and dispose engine before forking
            if self.connection:
                self.connection.close()
            if self.db_engine:
                self.db_engine.dispose()

            # Process new games in parallel
            games_processed = 0
            error_stats = defaultdict(int)
            elapsed_times = []

            if games_to_process:
                self.logger.info(f"\nStarting parallel processing of {len(games_to_process)} games...")
                with Pool(processes=num_workers) as pool:
                    # Use imap for progress tracking
                    results = list(tqdm(
                        pool.imap(_process_game_worker, games_to_process),
                        total=len(games_to_process),
                        desc="Processing games"
                    ))

                    # Analyze results
                    for result in results:
                        if result['success']:
                            games_processed += 1
                            elapsed_times.append(result['elapsed'])
                        else:
                            error_stats[result['error']] += 1

                # Report statistics
                self.logger.info("\n" + "=" * 80)
                self.logger.info("PROCESSING STATISTICS")
                self.logger.info("=" * 80)
                self.logger.info(f"Successfully processed: {games_processed} games")
                self.logger.info(f"Failed: {len(results) - games_processed} games")

                if error_stats:
                    self.logger.info("\nError Breakdown:")
                    if error_stats['rate_limit'] > 0:
                        self.logger.warning(f"  ⚠️  Rate Limit (429): {error_stats['rate_limit']} games")
                        self.logger.warning(f"      → REDUCE num_workers or add delays!")
                    if error_stats['blocked'] > 0:
                        self.logger.warning(f"  ⚠️  Blocked/Forbidden (403): {error_stats['blocked']} games")
                        self.logger.warning(f"      → API may have blocked your IP temporarily")
                    if error_stats['timeout'] > 0:
                        self.logger.warning(f"  ⚠️  Timeouts: {error_stats['timeout']} games")
                    if error_stats['unknown'] > 0:
                        self.logger.info(f"  ❌ Other errors: {error_stats['unknown']} games")

                if elapsed_times:
                    avg_time = sum(elapsed_times) / len(elapsed_times)
                    self.logger.info(f"\nAverage processing time: {avg_time:.2f} seconds per game")
                    self.logger.info(f"Min: {min(elapsed_times):.2f}s, Max: {max(elapsed_times):.2f}s")

                self.logger.info("=" * 80)

            # Re-import failed tables in parallel
            games_reimported = 0
            reimport_error_stats = defaultdict(int)
            reimport_elapsed_times = []

            if games_needing_reimport:
                self.logger.info(f"\nStarting parallel re-import process for {len(games_needing_reimport)} games...")

                # Prepare data for parallel processing (game_id, failed_tables, attempts)
                reimport_tasks = [
                    (game_id, info['failed_tables'], info['attempts'])
                    for game_id, info in games_needing_reimport.items()
                ]

                with Pool(processes=num_workers) as pool:
                    # Use imap for progress tracking
                    results = list(tqdm(
                        pool.imap(_process_game_reimport_worker, reimport_tasks),
                        total=len(reimport_tasks),
                        desc="Re-importing failed tables"
                    ))

                    # Analyze results
                    for result in results:
                        if result['success']:
                            games_reimported += 1
                            reimport_elapsed_times.append(result['elapsed'])
                        else:
                            reimport_error_stats[result['error']] += 1

                # Report re-import statistics
                self.logger.info("\n" + "=" * 80)
                self.logger.info("RE-IMPORT STATISTICS")
                self.logger.info("=" * 80)
                self.logger.info(f"Successfully re-imported: {games_reimported} games")
                self.logger.info(f"Failed: {len(results) - games_reimported} games")

                if reimport_error_stats:
                    self.logger.info("\nRe-import Error Breakdown:")
                    if reimport_error_stats['rate_limit'] > 0:
                        self.logger.warning(f"  ⚠️  Rate Limit (429): {reimport_error_stats['rate_limit']} games")
                    if reimport_error_stats['blocked'] > 0:
                        self.logger.warning(f"  ⚠️  Blocked/Forbidden (403): {reimport_error_stats['blocked']} games")
                    if reimport_error_stats['timeout'] > 0:
                        self.logger.warning(f"  ⚠️  Timeouts: {reimport_error_stats['timeout']} games")
                    if reimport_error_stats['unknown'] > 0:
                        self.logger.info(f"  ❌ Other errors: {reimport_error_stats['unknown']} games")

                if reimport_elapsed_times:
                    avg_time = sum(reimport_elapsed_times) / len(reimport_elapsed_times)
                    self.logger.info(f"\nAverage re-import time: {avg_time:.2f} seconds per game")
                    self.logger.info(f"Min: {min(reimport_elapsed_times):.2f}s, Max: {max(reimport_elapsed_times):.2f}s")

                self.logger.info("=" * 80)

            end_time = timeit.default_timer()
            elapsed = end_time - start_time

            self.logger.info("\n" + "=" * 80)
            self.logger.info("PARALLEL IMPORT COMPLETE")
            self.logger.info("=" * 80)
            self.logger.info(f"Total time: {elapsed:.2f} seconds ({elapsed/60:.2f} minutes)")
            self.logger.info(f"Processed {games_processed} new games")
            self.logger.info(f"Re-imported {games_reimported} games with failed tables")
            if games_processed > 0:
                self.logger.info(f"Average time per game: {elapsed/games_processed:.2f} seconds")
            self.logger.info("=" * 80)

        except Exception as e:
            self.logger.error(f"Parallel import failed: {e}")
            raise
        finally:
            if self.connection:
                self.connection.close()
            if self.db_engine:
                self.db_engine.dispose()


def _process_game_worker(game_id):
    """
    Worker function for multiprocessing (Solution 1)
    Each worker creates its own database connection and processes a single game
    """
    start_time = time.time()
    importer = None
    try:
        # Create new importer instance for this worker
        importer = NBADataImporter()
        importer.connect_to_database()

        # Process the game
        importer.process_single_game(game_id)

        elapsed = time.time() - start_time
        return {'game_id': game_id, 'success': True, 'elapsed': elapsed, 'error': None}

    except Exception as e:
        elapsed = time.time() - start_time
        error_msg = str(e).lower()

        # Detect specific error types
        error_type = 'unknown'
        if '429' in error_msg or 'too many requests' in error_msg:
            error_type = 'rate_limit'
            print(f"⚠️  RATE LIMIT: Game {game_id}")
        elif '403' in error_msg or 'forbidden' in error_msg:
            error_type = 'blocked'
            print(f"⚠️  BLOCKED: Game {game_id}")
        elif 'timeout' in error_msg or 'timed out' in error_msg:
            error_type = 'timeout'
            print(f"⚠️  TIMEOUT: Game {game_id}")
        else:
            print(f"❌ Error processing game {game_id}: {e}")

        return {'game_id': game_id, 'success': False, 'elapsed': elapsed, 'error': error_type}

    finally:
        # Always close connection and dispose engine to prevent connection leaks
        if importer:
            if importer.connection:
                try:
                    importer.connection.close()
                except Exception:
                    pass  # Ignore errors during cleanup
            if importer.db_engine:
                try:
                    importer.db_engine.dispose()
                except Exception:
                    pass  # Ignore errors during cleanup


def _process_game_reimport_worker(task_data):
    """
    Worker function for parallel re-import processing
    Each worker creates its own database connection and re-imports failed tables for a single game

    Args:
        task_data: Tuple of (game_id, failed_tables, attempts)
    """
    game_id, failed_tables, attempts = task_data
    start_time = time.time()
    importer = None

    try:
        # Create new importer instance for this worker
        importer = NBADataImporter()
        importer.connect_to_database()

        # Process the game re-import
        importer.process_game_reimport(game_id, failed_tables, attempts)

        elapsed = time.time() - start_time
        return {'game_id': game_id, 'success': True, 'elapsed': elapsed, 'error': None}

    except Exception as e:
        elapsed = time.time() - start_time
        error_msg = str(e).lower()

        # Detect specific error types
        error_type = 'unknown'
        if '429' in error_msg or 'too many requests' in error_msg:
            error_type = 'rate_limit'
            print(f"⚠️  RATE LIMIT: Game {game_id} re-import")
        elif '403' in error_msg or 'forbidden' in error_msg:
            error_type = 'blocked'
            print(f"⚠️  BLOCKED: Game {game_id} re-import")
        elif 'timeout' in error_msg or 'timed out' in error_msg:
            error_type = 'timeout'
            print(f"⚠️  TIMEOUT: Game {game_id} re-import")
        else:
            print(f"❌ Error re-importing game {game_id}: {e}")

        return {'game_id': game_id, 'success': False, 'elapsed': elapsed, 'error': error_type}

    finally:
        # Always close connection and dispose engine to prevent connection leaks
        if importer:
            if importer.connection:
                try:
                    importer.connection.close()
                except Exception:
                    pass  # Ignore errors during cleanup
            if importer.db_engine:
                try:
                    importer.db_engine.dispose()
                except Exception:
                    pass  # Ignore errors during cleanup


def _build_arg_parser():
    import argparse
    p = argparse.ArgumentParser(
        description="Fetch NBA boxscore data into MySQL. By default the window covers "
                    "the current season, and games already fully present in "
                    "importedgamesmemory are skipped without hitting the API."
    )
    p.add_argument('--date-from', type=str, default=None,
                   help='Window start (YYYY-MM-DD or MM/DD/YYYY). '
                        f'Default: {NBADataImporter.DEFAULT_DATE_FROM}.')
    p.add_argument('--date-to', type=str, default=None,
                   help='Window end (YYYY-MM-DD or MM/DD/YYYY). '
                        f'Default: {NBADataImporter.DEFAULT_DATE_TO}.')
    p.add_argument('--workers', type=int, default=None,
                   help=f'Parallel worker processes (default: {NBA_API_DEFAULT_WORKERS}).')
    p.add_argument('--sequential', action='store_true',
                   help='Use the single-threaded run_import instead of run_import_parallel.')
    p.add_argument('--no-skip-processed', action='store_true',
                   help='Force a full leaguegamefinder API fetch over the window even if '
                        'some/all games are already in importedgamesmemory. Use this when '
                        'NBA retroactively edits the schedule.')
    return p


if __name__ == '__main__':
    args = _build_arg_parser().parse_args()
    importer = NBADataImporter()
    skip_processed = not args.no_skip_processed
    if args.sequential:
        importer.run_import(date_from=args.date_from, date_to=args.date_to,
                            skip_processed=skip_processed)
    else:
        importer.run_import_parallel(num_workers=args.workers,
                                      date_from=args.date_from, date_to=args.date_to,
                                      skip_processed=skip_processed)