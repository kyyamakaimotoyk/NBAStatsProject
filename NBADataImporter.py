import timeit
import pandas as pd
import sqlalchemy as sql
from nba_api.stats.static import teams, players
from nba_api.stats.endpoints import (
    boxscoreadvancedv3, boxscoredefensivev2, boxscorefourfactorsv3,
    boxscorehustlev2, boxscoremiscv3, boxscoreplayertrackv3,
    boxscorescoringv3, boxscoresummaryv2, boxscoretraditionalv3,
    boxscoreusagev3, leaguegamefinder
)
from tqdm import tqdm
import datetime

class NBADataImporter:
    def __init__(self, **DBConfig):
        '''Initialize NBADataImporter with SQL database configuration.'''
        self.host = DBConfig.get('host')
        self.user = DBConfig.get('user')
        self.password = DBConfig.get('password')
        self.port = DBConfig.get('port')
        self.database = DBConfig.get('database')
        self.database_connection = None

    def connect_to_database(self):
        '''Establishing a connection to the database using the unpacked DBConfig dictionary during instantiation'''
        self.database_connection = sql.create_engine(
            f"mysql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
        )

    def execute_query(self, query, params = None):
        '''Execute a query on the database and return the result.'''
        try:
            with self.database_connection.connect() as connection:
                result = connection.execute(sql.text(query), params or {})
                return result.fetchall()
        except Exception as e:
            print(f"Error executing query: {query}, Error: {e}")
            return []

    def fetch_teams_and_players(self):
        '''Fetching team and player data from NBA_API'''
        self.nba_teams = teams.get_teams()
        self.nba_players = players.get_players()

    def update_teams_table(self):
        '''Update the NBA teams table in the database with the latest team data.'''
        nba_teams_df = pd.DataFrame(self.nba_teams)

        try:
            existing_ids = [row[0] for row in self.execute_query("Select id from nba_data.nba_teams")]

            for team in self.nba_teams:
                if team['id'] not in existing_ids:
                    self.execute_query(
                        query = """
                        Insert into nba_data.nba_teams (id, full_name, abbreviation, nickname, city, state, year_founded)
                        values (:id, :full_name, :abbreviation, :nickname, :city, :state, :year_founded)
                        """,
                        params = team
                    )
        except Exception:
            nba_teams_df.to_sql('nba_teams', con = self.database_connection, if_exists = 'replace', index = False)

    def update_players_table(self):
        '''Update the players table in the database with the latest player data.'''
        nba_players_df = pd.DataFrame(self.nba_players)

        try:
            existing_ids = [row[0] for row in self.execute_query("Select id from nba_data.nba_players")]

            for player in self.nba_players:
                if player['id'] not in existing_ids:
                    self.execute_query(
                        query = """
                        Insert into nba_data.nba_players (id, full_name, first_name, last_name, is_active)
                        values (:id, :full_name, :first_name, :last_name, :is_active)
                        """,
                        params = player
                    )

        except Exception:
            nba_players_df.to_sql('nba_players', con = self.database_connection, if_exists = 'replace', index = False)

    def update_game_list(self, date_from, date_to):
        """Update the game list in the database with new games from the NBA API"""

        gamefinder = leaguegamefinder.LeagueGameFinder(league_id_nullable = '00', date_from_nullable = date_from,
                                                       date_to_nullable = date_to)
        gamefinder_df = gamefinder.get_data_frame()[0]

        existing_games = [(row[0], row[1], row[2] for row in self.execute_query("Select game_id, team_id, count(team_id) from nba_data.game_list group by game_id, team_id"))]

        for _, game_row in gamefinder_df.iterrows():
            game_id, team_id = int(game_row['GAME_ID']), int(game_row['TEAM_ID'])

            if (game_id, team_id, 2) in existing_games: # Case when the game has already been imported to game_list
                self.execute_query("DELETE FROM nba_data.game_list WHERE GAME_ID = :game_id AND TEAM_ID = :team_id",
                                   {'game_id': game_id, 'team_id': team_id})

            if (game_id, team_id, 1) not in existing_games: # Case when there is no game_id, team_id combination in the database
                game_row.to_frame().T.to_sql('game_list', con=self.database_connection, if_exists='append', index=False)
