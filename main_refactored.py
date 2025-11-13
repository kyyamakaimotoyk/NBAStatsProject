"""
NBA Data Importer - Refactored Version
Fetches NBA game data from the API and stores it in a MySQL database.
"""

from nba_api.stats.static import teams, players
from nba_api.stats.endpoints import (
    boxscoreadvancedv3, boxscoredefensivev2, boxscorefourfactorsv3,
    boxscorehustlev2, boxscoremiscv3, boxscoreplayertrackv3,
    boxscorescoringv3, boxscoresummaryv2, boxscoretraditionalv3,
    boxscoreusagev3, leaguegamefinder
)
from tqdm import tqdm
import pandas as pd
import sqlalchemy as sql
import timeit
import datetime
import logging


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
        """Return table configuration for boxscore endpoints"""
        return {
            'nba_data.boxscoreadvancedv3_player': ['gameId', 'personId', 1],
            'nba_data.boxscoreadvancedv3_team': ['gameId', 'teamId', 1],
            'nba_data.boxscoredefensivev2_player': ['gameId', 'personId', 1],
            'nba_data.boxscoredefensivev2_team': ['gameId', 'teamId', 1],
            'nba_data.boxscorefourfactorsv3_player': ['gameId', 'personId', 1],
            'nba_data.boxscorefourfactorsv3_team': ['gameId', 'teamId', 1],
            'nba_data.boxscorehustlev2_player': ['gameId', 'personId', 1],
            'nba_data.boxscorehustlev2_team': ['gameId', 'teamId', 1],
            'nba_data.boxscoremiscv3_player': ['gameId', 'personId', 1],
            'nba_data.boxscoremiscv3_team': ['gameId', 'teamId', 1],
            'nba_data.boxscoreplayertrackv3_player': ['gameId', 'personId', 1],
            'nba_data.boxscoreplayertrackv3_team': ['gameId', 'teamId', 1],
            'nba_data.boxscorescoringv3_player': ['gameId', 'personId', 1],
            'nba_data.boxscorescoringv3_team': ['gameId', 'teamId', 1],
            'nba_data.boxscoresummaryv2_game_info': ['GAME_ID', 'GAME_ID', 1],
            'nba_data.boxscoresummaryv2_inactive_players': ['GAME_ID', 'PLAYER_ID', 1],
            'nba_data.boxscoresummaryv2_other_stats': ['GAME_ID', 'GAME_ID', 1],
            'nba_data.boxscoresummaryv2_referee': ['GAME_ID', 'OFFICIAL_ID', 1],
            'nba_data.boxscoresummaryv2_summary': ['GAME_ID', 'TEAM_ID', 1],
            'nba_data.boxscoretraditionalv3_bench': ['gameId', 'teamId', 2],
            'nba_data.boxscoretraditionalv3_player': ['gameId', 'personId', 1],
            'nba_data.boxscoretraditionalv3_team': ['gameId', 'teamId', 1],
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

    def get_games_to_process(self, date_from='07/02/2025', date_to='07/01/2026'):
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

    def check_game_data_status(self, game_id):
        """Check the status of game data for each table"""
        status = {}

        for table_name, config in self.table_config.items():
            column1, column2, expected_count = config

            try:
                stmt = f"""SELECT COUNT({column2}) FROM {table_name}
                          WHERE {column1} = {game_id}
                          GROUP BY {column1}, {column2}"""
                result = self.connection.execute(sql.text(stmt))
                results = list(result)

                if not results:
                    status[table_name] = 0  # No data exists
                elif len(results) == expected_count and all(r[0] == expected_count for r in results):
                    status[table_name] = 1  # Correct data exists
                else:
                    status[table_name] = -1  # Incorrect data, needs cleanup

            except Exception as e:
                self.logger.error(f"Error checking {table_name}: {e}")
                status[table_name] = 0

        return status

    def process_boxscore_endpoint(self, endpoint_class, table_name, game_id, dataframe_index=0, add_game_id=False):
        """Generic function to process any boxscore endpoint"""
        try:
            # Fetch data from API
            boxscore_data = endpoint_class(game_id=str(game_id)).get_data_frames()
            df = boxscore_data[dataframe_index]

            # Add GAME_ID column if needed (for summary endpoints)
            if add_game_id:
                df['GAME_ID'] = game_id

            # Save to database
            df.to_sql(name=table_name, con=self.db_engine, if_exists='append', index=False)
            self.connection.commit()

            return True

        except Exception as e:
            self.logger.error(f"Failed to import {table_name} for game_id = {game_id}: {e}")
            return False

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

        # Process each endpoint based on status
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

        # Process summary endpoints separately (they need special handling)
        summary_endpoints = {
            'nba_data.boxscoresummaryv2_summary': (boxscoresummaryv2.BoxScoreSummaryV2, 'boxscoresummaryv2_summary', 1, True),
            'nba_data.boxscoresummaryv2_referee': (boxscoresummaryv2.BoxScoreSummaryV2, 'boxscoresummaryv2_referee', 2, True),
            'nba_data.boxscoresummaryv2_inactive_players': (boxscoresummaryv2.BoxScoreSummaryV2, 'boxscoresummaryv2_inactive_players', 3, True),
            'nba_data.boxscoresummaryv2_other_stats': (boxscoresummaryv2.BoxScoreSummaryV2, 'boxscoresummaryv2_other_stats', 6, False),
            'nba_data.boxscoresummaryv2_game_info': (boxscoresummaryv2.BoxScoreSummaryV2, 'boxscoresummaryv2_game_info', 7, False),
        }

        # Process regular endpoints
        for table_name, (endpoint_class, db_table, df_index) in endpoints.items():
            if status[table_name] == 1:
                self.logger.info(f"Game {game_id} already has data in {table_name}")
                import_results[table_name] = 1  # Already exists
                continue
            elif status[table_name] == -1:
                # Clean existing incorrect data
                column_name = self.table_config[table_name][0]
                self.clean_existing_data(table_name, game_id, column_name)

            # Process the endpoint and record the result
            success = self.process_boxscore_endpoint(endpoint_class, db_table, game_id, df_index)
            import_results[table_name] = 1 if success else 0

        # Process summary endpoints
        for table_name, (endpoint_class, db_table, df_index, add_game_id) in summary_endpoints.items():
            if status[table_name] == 1:
                self.logger.info(f"Game {game_id} already has data in {table_name}")
                import_results[table_name] = 1  # Already exists
                continue
            elif status[table_name] == -1:
                # Clean existing incorrect data
                self.clean_existing_data(table_name, game_id, 'GAME_ID')

            # Process the endpoint and record the result
            success = self.process_boxscore_endpoint(endpoint_class, db_table, game_id, df_index, add_game_id)
            import_results[table_name] = 1 if success else 0

        # Record that this game has been processed with actual results
        self._record_game_processed(game_id, import_results)

    def _record_game_processed(self, game_id, import_results, is_reattempt=False, previous_attempts=0):
        """Record that a game has been processed with actual import results"""
        try:
            if is_reattempt:
                # Update existing record
                self._update_game_record(game_id, import_results, previous_attempts + 1)
            else:
                # Create new record for imported games memory
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
            self.logger.info(f"Game {game_id} recorded{attempt_msg}: {successful} successful, {failed} failed")

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

        # Set all tables to their current status first
        for table_name in self.table_config.keys():
            if status.get(table_name) == 1:
                import_results[table_name] = 1

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

            # Clean if data exists but is incorrect
            if status.get(table_name) == -1:
                column_name = 'GAME_ID' if add_game_id else self.table_config[table_name][0]
                self.clean_existing_data(table_name, game_id, column_name)

            # Attempt import
            success = self.process_boxscore_endpoint(endpoint_class, db_table, game_id, df_index, add_game_id)
            import_results[table_name] = 1 if success else 0

            if success:
                self.logger.info(f"Successfully re-imported {table_name} for game {game_id}")
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


if __name__ == '__main__':
    importer = NBADataImporter()
    importer.run_import()