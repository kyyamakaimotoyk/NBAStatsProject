"""
Ad-hoc Verification and Repair Script for importedGamesMemory Table
Verifies that all entries in importedgamesmemory accurately reflect actual database state.
Automatically fixes discrepancies so that main_refactored.py can trust the data.
"""

import pandas as pd
import sqlalchemy as sql
from datetime import datetime
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ImportedGamesVerifier:
    def __init__(self):
        self.db_engine = None
        self.connection = None
        self.table_config = self._get_table_config()
        self.discrepancies = []
        self.game_data_cache = {}  # Cache for game data per table
        self.game_metadata_cache = {}  # Cache for game metadata

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
            logger.info("Database connection established")

        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    def load_all_game_data_into_memory(self):
        """Load all game data from all tables into memory for fast lookup"""
        logger.info("Loading all game data into memory...")
        logger.info("=" * 80)

        for table_name, config in self.table_config.items():
            column1, column2, expected_count = config

            try:
                # Get all unique game_ids from this table
                query = f"SELECT DISTINCT {column1} FROM {table_name}"
                result = self.connection.execute(sql.text(query))

                # Store as a set for O(1) lookup
                game_ids = set(row[0] for row in result)
                self.game_data_cache[table_name] = game_ids

                logger.info(f"  Loaded {len(game_ids)} games from {table_name.split('.')[-1]}")

            except Exception as e:
                logger.error(f"  Error loading data from {table_name}: {e}")
                self.game_data_cache[table_name] = set()  # Empty set on error

        logger.info("=" * 80)
        logger.info(f"Finished loading data from {len(self.table_config)} tables into memory")
        logger.info("=" * 80)

    def load_all_game_metadata_into_memory(self):
        """Load all game metadata (dates and matchups) into memory"""
        logger.info("Loading all game metadata into memory...")

        try:
            # Get all game metadata in one query
            query = """
                SELECT GAME_ID, GAME_DATE, MATCHUP
                FROM nba_data.game_list
            """
            result = self.connection.execute(sql.text(query))

            # Store in dictionary, taking first occurrence of each game_id
            for row in result:
                game_id = row[0]
                if game_id not in self.game_metadata_cache:
                    self.game_metadata_cache[game_id] = {
                        'game_date': row[1],
                        'matchup': row[2]
                    }

            logger.info(f"Loaded metadata for {len(self.game_metadata_cache)} unique games")
            logger.info("=" * 80)

        except Exception as e:
            logger.error(f"Failed to load game metadata: {e}")

    def check_game_data_status(self, game_id):
        """Check the actual status of game data for each table using in-memory cache"""
        status = {}

        for table_name in self.table_config.keys():
            # Check if game_id exists in the cached set for this table
            if game_id in self.game_data_cache.get(table_name, set()):
                status[table_name] = 1  # Data exists
            else:
                status[table_name] = 0  # No data exists

        return status

    def get_all_imported_games(self):
        """Get all entries from importedGamesMemory table"""
        try:
            query = "SELECT * FROM nba_data.importedGamesMemory"
            df = pd.read_sql(query, self.connection)
            logger.info(f"Found {len(df)} entries in importedGamesMemory")
            return df
        except Exception as e:
            logger.error(f"Failed to read importedGamesMemory: {e}")
            raise

    def get_game_metadata(self, game_id):
        """Get game date and matchup from in-memory cache"""
        # Return cached metadata or default values if not found
        return self.game_metadata_cache.get(game_id, {
            'game_date': 'Unknown',
            'matchup': 'Unknown'
        })

    def verify_single_game(self, game_id, recorded_status):
        """Verify a single game's data against what's recorded in importedGamesMemory"""
        actual_status = self.check_game_data_status(game_id)

        game_discrepancies = []

        for table_name in self.table_config.keys():
            recorded_value = recorded_status.get(table_name, -999)
            actual_value = actual_status.get(table_name, -999)

            # Convert actual_value to what should be recorded (0 or 1)
            # -1 means incorrect data exists, should be recorded as 0 (needs reimport)
            if actual_value == -1:
                expected_recorded = 0
            else:
                expected_recorded = actual_value

            if recorded_value != expected_recorded:
                game_discrepancies.append({
                    'gameId': game_id,
                    'table': table_name,
                    'recorded': recorded_value,
                    'actual': actual_value,
                    'expected_recorded': expected_recorded,
                    'issue': self._get_issue_description(recorded_value, actual_value)
                })

        return game_discrepancies

    def _get_issue_description(self, recorded, actual):
        """Generate human-readable description of the discrepancy"""
        if recorded == 1 and actual == 0:
            return "CRITICAL: Marked as imported but no data exists"
        elif recorded == 1 and actual == -1:
            return "CRITICAL: Marked as imported but data is incorrect/duplicated"
        elif recorded == 0 and actual == 1:
            return "INFO: Marked as not imported but data exists correctly"
        elif recorded == 0 and actual == -1:
            return "WARNING: Marked as not imported and data is incorrect"
        else:
            return f"UNKNOWN: recorded={recorded}, actual={actual}"

    def verify_all_games(self):
        """Verify all games in importedGamesMemory"""
        logger.info("Starting verification of all imported games...")
        logger.info("=" * 80)

        # Load all data into memory first (batch approach)
        self.load_all_game_data_into_memory()
        self.load_all_game_metadata_into_memory()

        imported_games_df = self.get_all_imported_games()

        total_games = len(imported_games_df)
        games_with_issues = 0
        total_discrepancies = 0

        for idx, row in imported_games_df.iterrows():
            game_id = row['gameId']
            game_num = idx + 1

            # Get game metadata (date and matchup)
            metadata = self.get_game_metadata(game_id)
            game_date = metadata['game_date']
            matchup = metadata['matchup']

            # Extract recorded status for all tables
            recorded_status = {}
            for table_name in self.table_config.keys():
                if table_name in row:
                    recorded_status[table_name] = row[table_name]
                else:
                    recorded_status[table_name] = -999  # Column missing

            # Verify this game
            game_discrepancies = self.verify_single_game(game_id, recorded_status)

            # Print detailed progress for this game
            if game_discrepancies:
                games_with_issues += 1
                total_discrepancies += len(game_discrepancies)
                self.discrepancies.extend(game_discrepancies)

                # List ALL tables with discrepancies
                failed_tables = [disc['table'] for disc in game_discrepancies]
                failed_tables_str = ', '.join([t.split('.')[-1] for t in failed_tables])

                print(f"[Game {game_num} of {total_games}] Processing Game_ID = {game_id}, "
                      f"Game_date = {game_date}, Matchup = {matchup}")
                print(f"  └─> DISCREPANCIES FOUND: {len(game_discrepancies)} table(s) - {failed_tables_str}")
            else:
                # No discrepancies - all good
                print(f"[Game {game_num} of {total_games}] Processing Game_ID = {game_id}, "
                      f"Game_date = {game_date}, Matchup = {matchup}")
                print(f"  └─> OK: No discrepancies")

        # Summary
        print("\n" + "=" * 80)
        logger.info("VERIFICATION COMPLETE")
        logger.info("=" * 80)
        logger.info(f"Total games verified: {total_games}")
        logger.info(f"Games with discrepancies: {games_with_issues}")
        logger.info(f"Total discrepancies found: {total_discrepancies}")

        if total_discrepancies > 0:
            logger.warning(f"\nFound {total_discrepancies} discrepancies across {games_with_issues} games!")
        else:
            logger.info("\nNo discrepancies found! Database is consistent.")

        return self.discrepancies

    def export_discrepancies_report(self, filename=None):
        """Export discrepancies to CSV file"""
        if not self.discrepancies:
            logger.info("No discrepancies to export")
            return

        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"importedgamesmemory_discrepancies_{timestamp}.csv"

        df = pd.DataFrame(self.discrepancies)
        df.to_csv(filename, index=False)
        logger.info(f"Discrepancies exported to {filename}")

        # Print summary statistics
        print("\n" + "=" * 80)
        print("DISCREPANCY SUMMARY BY ISSUE TYPE")
        print("=" * 80)
        issue_summary = df.groupby('issue').size().sort_values(ascending=False)
        print(issue_summary)

        print("\n" + "=" * 80)
        print("DISCREPANCY SUMMARY BY TABLE")
        print("=" * 80)
        table_summary = df.groupby('table').size().sort_values(ascending=False)
        print(table_summary.head(20))

        print("\n" + "=" * 80)
        print("SAMPLE DISCREPANCIES (first 20)")
        print("=" * 80)
        print(df.head(20).to_string())

    def generate_fix_script(self, filename=None):
        """Generate SQL script to fix importedGamesMemory table"""
        if not self.discrepancies:
            logger.info("No discrepancies to fix")
            return

        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"fix_importedgamesmemory_{timestamp}.sql"

        # Group discrepancies by game
        games_to_fix = {}
        for disc in self.discrepancies:
            game_id = disc['gameId']
            if game_id not in games_to_fix:
                games_to_fix[game_id] = []
            games_to_fix[game_id].append(disc)

        with open(filename, 'w') as f:
            f.write("-- SQL Script to Fix importedGamesMemory Table\n")
            f.write(f"-- Generated: {datetime.now()}\n")
            f.write(f"-- Total games to fix: {len(games_to_fix)}\n\n")

            for game_id, discrepancies in games_to_fix.items():
                f.write(f"\n-- Fix game {game_id} ({len(discrepancies)} tables need correction)\n")
                for disc in discrepancies:
                    table_name = disc['table']
                    expected_value = disc['expected_recorded']
                    f.write(f"UPDATE nba_data.importedGamesMemory SET `{table_name}` = {expected_value} WHERE gameId = {game_id};\n")

        logger.info(f"Fix script generated: {filename}")
        logger.info(f"Review the script and run it manually to fix the importedGamesMemory table")

    def ensure_number_reattempts_column(self):
        """Ensure number_reattempts column exists in importedGamesMemory"""
        try:
            # Check if column exists
            query = "SELECT * FROM nba_data.importedGamesMemory LIMIT 1"
            df = pd.read_sql(query, self.connection)

            if 'number_reattempts' not in df.columns:
                logger.info("Adding number_reattempts column to importedGamesMemory...")
                alter_stmt = """
                    ALTER TABLE nba_data.importedGamesMemory
                    ADD COLUMN number_reattempts INT DEFAULT 0
                """
                self.connection.execute(sql.text(alter_stmt))
                self.connection.commit()
                logger.info("Successfully added number_reattempts column")
            else:
                logger.info("number_reattempts column already exists")

        except Exception as e:
            logger.error(f"Error ensuring number_reattempts column: {e}")

    def fix_game_record(self, game_id, corrections):
        """Fix a single game record in importedGamesMemory"""
        try:
            # Build UPDATE statement
            update_parts = []
            for table_name, expected_value in corrections.items():
                column_name = f"`{table_name}`"
                update_parts.append(f"{column_name} = {expected_value}")

            if update_parts:
                update_stmt = f"""
                    UPDATE nba_data.importedgamesmemory
                    SET {', '.join(update_parts)}
                    WHERE gameId = {game_id}
                """
                self.connection.execute(sql.text(update_stmt))
                self.connection.commit()
                logger.info(f"Fixed {len(update_parts)} table(s) for game {game_id}")
                return True
            return False

        except Exception as e:
            logger.error(f"Failed to fix game {game_id}: {e}")
            return False

    def auto_fix_all_discrepancies(self):
        """Automatically fix all discrepancies found"""
        if not self.discrepancies:
            logger.info("No discrepancies to fix")
            return 0

        logger.info("=" * 80)
        logger.info("STARTING AUTO-FIX PROCESS")
        logger.info("=" * 80)

        # Group discrepancies by game
        games_to_fix = {}
        for disc in self.discrepancies:
            game_id = disc['gameId']
            table_name = disc['table']
            expected_value = disc['expected_recorded']

            if game_id not in games_to_fix:
                games_to_fix[game_id] = {}
            games_to_fix[game_id][table_name] = expected_value

        # Fix each game
        fixed_count = 0
        failed_count = 0

        for game_id, corrections in games_to_fix.items():
            if self.fix_game_record(game_id, corrections):
                fixed_count += 1
            else:
                failed_count += 1

        logger.info("=" * 80)
        logger.info("AUTO-FIX COMPLETE")
        logger.info("=" * 80)
        logger.info(f"Games fixed successfully: {fixed_count}")
        logger.info(f"Games failed to fix: {failed_count}")
        logger.info(f"Total table corrections made: {len(self.discrepancies)}")

        return fixed_count

    def close(self):
        """Close database connection"""
        if self.connection:
            self.connection.close()
            logger.info("Database connection closed")


def main():
    verifier = ImportedGamesVerifier()

    try:
        # Connect to database
        verifier.connect_to_database()

        # Ensure number_reattempts column exists
        verifier.ensure_number_reattempts_column()

        # Run verification
        logger.info("Running verification pass...")
        discrepancies = verifier.verify_all_games()

        if discrepancies:
            # Export report before fixing
            logger.info("\nExporting discrepancy report...")
            verifier.export_discrepancies_report()

            # Automatically fix all discrepancies
            logger.info("\nAutomatically fixing discrepancies...")
            fixed_count = verifier.auto_fix_all_discrepancies()

            if fixed_count > 0:
                # Re-verify to confirm fixes
                logger.info("\n" + "=" * 80)
                logger.info("RE-VERIFYING AFTER AUTO-FIX")
                logger.info("=" * 80)
                verifier.discrepancies = []  # Clear old discrepancies
                remaining_discrepancies = verifier.verify_all_games()

                if remaining_discrepancies:
                    logger.warning(f"\nWARNING: {len(remaining_discrepancies)} discrepancies remain after auto-fix!")
                    logger.warning("Please review the logs and discrepancy report")
                else:
                    logger.info("\n" + "=" * 80)
                    logger.info("SUCCESS! All discrepancies have been fixed!")
                    logger.info("importedGamesMemory table is now accurate and trustworthy")
                    logger.info("You can now safely run main_refactored.py")
                    logger.info("=" * 80)
        else:
            logger.info("\n" + "=" * 80)
            logger.info("SUCCESS! No discrepancies found!")
            logger.info("importedGamesMemory table is accurate and trustworthy")
            logger.info("You can now safely run main_refactored.py")
            logger.info("=" * 80)

    finally:
        verifier.close()


if __name__ == '__main__':
    main()