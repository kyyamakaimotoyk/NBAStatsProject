"""
NBA Data Importer - Refactored Version
Fetches NBA game data from the API and stores it in a MySQL database.
"""

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

            host = 'localhost'
            user = 'kaiyamamoto'
            password = 'KN!yoWMhiH8cBvD'
            port = '3306'
            database = 'nba_data'

            connection_string = f'mysql://{user}:{password}@{host}:{port}/{database}'
            self.db_engine = sql.create_engine(connection_string)
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

    def get_games_to_process(self, date_from='11/22/2025', date_to='07/01/2026'):
        """Get list of games to process from the API"""
        self.logger.info(f"Fetching games from {date_from} to {date_to}")

        gamefinder = leaguegamefinder.LeagueGameFinder(
            league_id_nullable='00',
            date_from_nullable=date_from,
            date_to_nullable=date_to
        )
        gamefinder_df = gamefinder.get_data_frames()[0]

        # Update game_list table
        self._update_game_list_table(gamefinder_df)

        return pd.unique(gamefinder_df['GAME_ID'])

    def _update_game_list_table(self, gamefinder_df):
        """Update the game_list table with new games"""
        try:
            # Get existing games
            stmt = """SELECT GAME_ID, TEAM_ID, COUNT(TEAM_ID)
                     FROM nba_data.game_list
                     GROUP BY GAME_ID, TEAM_ID"""
            result = self.connection.execute(sql.text(stmt))
            existing_games = {(r[0], r[1]): r[2] for r in result}

            for index, row in gamefinder_df.iterrows():
                game_id = int(row['GAME_ID'])
                team_id = int(row['TEAM_ID'])

                if (game_id, team_id) in existing_games:
                    if existing_games[(game_id, team_id)] > 1:
                        # Remove duplicates
                        delete_stmt = f"DELETE FROM nba_data.game_list WHERE GAME_ID = {game_id} AND TEAM_ID = {team_id}"
                        self.connection.execute(sql.text(delete_stmt))
                        self.connection.commit()

                        # Re-add the game
                        gamefinder_df.iloc[[index]].to_sql(
                            name='game_list', con=self.db_engine, if_exists='append', index=False
                        )
                else:
                    # Add new game
                    gamefinder_df.iloc[[index]].to_sql(
                        name='game_list', con=self.db_engine, if_exists='append', index=False
                    )

        except sql.exc.ProgrammingError:
            # Table doesn't exist, create it
            gamefinder_df.to_sql(name='game_list', con=self.db_engine, if_exists='replace', index=False)

    def get_imported_games(self):
        """Get list of fully imported games (all tables successful)"""
        try:
            # Get all game records with their import status
            query = "SELECT * FROM nba_data.importedGamesMemory"
            df = pd.read_sql(query, self.connection)

            fully_imported_games = []

            for _, row in df.iterrows():
                game_id = row['gameId']
                all_successful = True

                # Check if all tables have status = 1 (successful)
                for table_name in self.table_config.keys():
                    if table_name in df.columns:
                        if row[table_name] != 1:
                            all_successful = False
                            break
                    else:
                        # Column missing, treat as failed
                        all_successful = False
                        break

                if all_successful:
                    fully_imported_games.append(game_id)

            self.logger.info(f"Found {len(fully_imported_games)} fully imported games out of {len(df)} total records")
            return fully_imported_games

        except sql.exc.ProgrammingError:
            # Table doesn't exist yet
            self.logger.info("importedGamesMemory table doesn't exist yet")
            return []
        except Exception as e:
            self.logger.error(f"Error reading importedGamesMemory: {e}")
            return []

    def get_games_needing_reimport(self):
        """Get games that have at least one failed table import"""
        try:
            query = "SELECT * FROM nba_data.importedGamesMemory"
            df = pd.read_sql(query, self.connection)

            games_to_reimport = {}

            for _, row in df.iterrows():
                game_id = row['gameId']
                failed_tables = []

                # Check which tables failed (status = 0)
                for table_name in self.table_config.keys():
                    if table_name in df.columns:
                        if row[table_name] == 0:
                            failed_tables.append(table_name)
                    else:
                        # Column missing, needs import
                        failed_tables.append(table_name)

                if failed_tables:
                    current_attempts = row.get('number_reattempts', 0)
                    games_to_reimport[game_id] = {
                        'failed_tables': failed_tables,
                        'attempts': current_attempts
                    }
                    self.logger.info(f"Game {game_id} needs re-import for {len(failed_tables)} tables (attempt #{current_attempts + 1})")

            self.logger.info(f"Found {len(games_to_reimport)} games needing re-import")
            return games_to_reimport

        except sql.exc.ProgrammingError:
            self.logger.info("importedGamesMemory table doesn't exist yet")
            return {}
        except Exception as e:
            self.logger.error(f"Error reading importedGamesMemory for re-imports: {e}")
            return {}

    def load_all_game_statuses(self):
        """Load all game statuses into memory for fast lookup (Solution 4 optimization)"""
        try:
            query = "SELECT * FROM nba_data.importedGamesMemory"
            df = pd.read_sql(query, self.connection)

            game_statuses = {}
            for _, row in df.iterrows():
                game_id = row['gameId']

                # Check if all tables are successfully imported
                all_complete = True
                for table_name in self.table_config.keys():
                    if table_name in df.columns:
                        if row[table_name] != 1:
                            all_complete = False
                            break
                    else:
                        all_complete = False
                        break

                game_statuses[game_id] = {
                    'all_complete': all_complete,
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
                # Fetch from API and cache the response
                boxscore_data = endpoint_class(game_id=str(game_id)).get_data_frames()
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

    def run_import(self):
        """Main function to run the complete import process"""
        start_time = timeit.default_timer()

        try:
            # Initialize
            self.connect_to_database()
            self.initialize_teams_data()
            self.initialize_players_data()

            # Get games to process
            games_list = self.get_games_to_process()
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

    def run_import_parallel(self, num_workers=None):
        """
        Main function to run import process with parallel processing (Solution 1)

        Args:
            num_workers: Number of parallel workers. If None, defaults to 2 (safe for NBA API rate limits)
        """
        start_time = timeit.default_timer()

        try:
            # Determine number of workers (default to 2 to avoid API rate limiting)
            if num_workers is None:
                num_workers = 20

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
            games_list = self.get_games_to_process()
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


if __name__ == '__main__':
    importer = NBADataImporter()

    # Use parallel processing by default
    # To use sequential processing, change to: importer.run_import()
    importer.run_import_parallel()