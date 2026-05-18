from nba_api.stats.static import teams, players
from nba_api.stats.endpoints import (
    boxscoreadvancedv3, boxscoredefensivev2, boxscorefourfactorsv3,
    boxscorehustlev2, boxscoremiscv3, boxscoreplayertrackv3,
    boxscorescoringv3, boxscoresummaryv2, boxscoretraditionalv3,
    boxscoreusagev3, leaguegamefinder)
from tqdm import tqdm
import pandas as pd
import sqlalchemy as sql
import timeit
import plotly
import datetime



if __name__ == '__main__':
    start = timeit.default_timer()
    # Permanently changes the pandas settings for DataFrame display
    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)

    # MySQL config now lives in environment variables (see db.py / .env.example).
    # NOTE: this file is in Deprecated/ and is kept for reference only.
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from core.db import get_engine
    databaseConnection = get_engine()
    connection = databaseConnection.connect()


    #getting list of teams and players, to look up playerID and teamID for dataframe creation
    nba_teams = teams.get_teams()
    print("Number of teams fetched: {}".format(len(nba_teams)))
    # print(nba_teams)
    nba_players = players.get_players()

    print("Number of players fetched: {}".format(len(nba_players)))


    #Grab team_id and player_id
    nba_teams_df = pd.DataFrame(nba_teams)
    try:
        result = connection.execute(sql.text("select id from nba_data.nba_teams"))
        print('\nTable nba_teams already in DB, fetching existing teams.')
        #result is a 'Row-object' which seeks to act as much like a Python named tuple as possible... see sqlalchemy docs
        resultList = [r[0] for r in result]

        for index in range(0, len(nba_teams_df)):
            if nba_teams[index]['id'] in list(resultList):
                # print(str(nba_teams[index]['full_name']),' already in database.')
                continue
            else:
                print(str(nba_teams[index]['full_name']), ' not in database. Adding now.')
                sqlStmt = sql.text(
                    "Insert into nba_data.nba_teams (id, full_name, abbreviation, nickname, city, state, year_founded) values (:id, :full_name, :abbreviation, :nickname, :city, :state, :year_founded)")
                connection.execute(sqlStmt, nba_teams[index])
                connection.commit()

    except:
        print('\nTable nba_teams not in DB, creating.')
        nba_teams_df.to_sql(name='nba_teams', con=databaseConnection, if_exists='replace', index=False)



    nba_players_df = pd.DataFrame(nba_players)
    # print(nba_players_df.head())
    try:
        result = connection.execute(sql.text("select id from nba_data.nba_players"))
        print('\nTable nba_players already in DB, fetching existing players.')
        resultList = [r[0] for r in result]

        for index in range(0, len(nba_players)):
            if nba_players[index]['id'] in list(resultList):
                print(str(nba_players[index]['full_name']),'already in database.')
                continue
            else:
                print(str(nba_players[index]['full_name']), 'not in database. Adding now.')
                sqlStmt = sql.text(
                    "Insert into nba_data.nba_players (id, full_name, first_name, last_name, is_active) values (:id, :full_name, :first_name, :last_name, :is_active)")
                connection.execute(sqlStmt, nba_players[index])
                connection.commit()
    except:
        print('\nTable nba_players not in DB, creating.')
        nba_players_df.to_sql(name='nba_players', con=databaseConnection, if_exists='replace', index=False)


    #Get List of game_id using leaguegamefinder

    gamefinder = leaguegamefinder.LeagueGameFinder(league_id_nullable = '00', date_from_nullable = '11/15/2024', date_to_nullable = '07/01/2025')
    gamefinder_df = gamefinder.get_data_frames()[0]

    sqlStatement = '''select GAME_ID, TEAM_ID, count(TEAM_ID) from nba_data.game_list
            group by GAME_ID, TEAM_ID'''

    gameListResultCursor = connection.execute(sql.text(sqlStatement))
    gameListResult = [(i[0],i[1], i[2]) for i in gameListResultCursor]



    for index in range(0, len(gamefinder_df)):
        gameID = int(gamefinder_df.loc[index, 'GAME_ID'])
        teamID = int(gamefinder_df.loc[index, 'TEAM_ID'])



        if (gameID, teamID, 2) in gameListResult:


            print('\nGame {0} of {1}: Multiple entries of gameId = {2} in nba_data.game_list. Removing'.format(index + 1,
                                                                                                len(gamefinder_df),
                                                                                                gameID))
            connection.execute(
                sql.text('delete from nba_data.game_list where GAME_ID = {} and TEAM_ID = {}'.format(gameID, teamID)))
            connection.commit()

            gamefinder_df.iloc[[index]].to_sql(name='game_list', con=databaseConnection, if_exists='append',
                                               index=False)
        elif (gameID, teamID, 1) not in gameListResult:
            gamefinder_df.iloc[[index]].to_sql(name='game_list', con=databaseConnection, if_exists='append',
                                               index=False)
            print(
                '\n(Game {0} of {1}: Appended gameId = {2}, teamId = {3} to nba_data.game_list'.format(index + 1, len(gamefinder_df),
                                                                                         gameID, teamID))

        else:
            print('\nGame {0} of {1}: gameId = {2} already exists in nba_data.game_list'.format(index+1, len(gamefinder_df), gameID))


    tableGameIdColumn = {
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
    def sqlGameIdExistChecker(sqlTable, tableParameters, dbConnection):

        column1 = tableParameters[sqlTable][0]
        column2 = tableParameters[sqlTable][1]
        limiter = tableParameters[sqlTable][2]

        sqlStatement = sql.text('''
                                    select {0} from {2}
                                
                                '''.format(column1, column2, sqlTable, limiter))

        result = dbConnection.execute(sqlStatement)
        resultList = [r[0] for r in result]
        return resultList #outputs empty list if gameId not found in table



    try:
        result = connection.execute(sql.text("select distinct gameId from nba_data.importedGamesMemory"))
        print('\nTable game_list already in DB, fetching existing games.')

        importedGameList = [r[0] for r in result]

    except:
        print('\nTable nba_data.importedGamesMemory not in DB, creating.')
        importedGameList = []

    gamesList = pd.unique(gamefinder_df['GAME_ID'])

    importedGamesDB = {
        'nba_data.boxscoreadvancedv3_player': [],
        'nba_data.boxscoreadvancedv3_team': [],
        'nba_data.boxscoredefensivev2_player': [],
        'nba_data.boxscoredefensivev2_team': [],
        'nba_data.boxscorefourfactorsv3_player': [],
        'nba_data.boxscorefourfactorsv3_team': [],
        'nba_data.boxscorehustlev2_player': [],
        'nba_data.boxscorehustlev2_team': [],
        'nba_data.boxscoremiscv3_player': [],
        'nba_data.boxscoremiscv3_team': [],
        'nba_data.boxscoreplayertrackv3_player': [],
        'nba_data.boxscoreplayertrackv3_team': [],
        'nba_data.boxscorescoringv3_player': [],
        'nba_data.boxscorescoringv3_team': [],
        'nba_data.boxscoresummaryv2_game_info': [],
        'nba_data.boxscoresummaryv2_inactive_players': [],
        'nba_data.boxscoresummaryv2_other_stats': [],
        'nba_data.boxscoresummaryv2_referee': [],
        'nba_data.boxscoresummaryv2_summary': [],
        'nba_data.boxscoretraditionalv3_bench': [],
        'nba_data.boxscoretraditionalv3_player': [],
        'nba_data.boxscoretraditionalv3_team': [],
        'nba_data.boxscoreusagev3_player': [],
        'nba_data.boxscoreusagev3_team': []
    }

    # Storing all of the GameIDs that are already in each database table, to do a comparison to see if a new entry needs to be inserted
    for keys in tableGameIdColumn.keys():
        importedGamesDB[keys] = sqlGameIdExistChecker(keys, tableGameIdColumn, connection)



    for index in tqdm(range (0, len(gamesList))):
        games = gamesList[index]

        importedGamesMemory = {
            'gameId': [],
            'nba_data.boxscoreadvancedv3_player': [],
            'nba_data.boxscoreadvancedv3_team': [],
            'nba_data.boxscoredefensivev2_player': [],
            'nba_data.boxscoredefensivev2_team': [],
            'nba_data.boxscorefourfactorsv3_player': [],
            'nba_data.boxscorefourfactorsv3_team': [],
            'nba_data.boxscorehustlev2_player': [],
            'nba_data.boxscorehustlev2_team': [],
            'nba_data.boxscoremiscv3_player': [],
            'nba_data.boxscoremiscv3_team': [],
            'nba_data.boxscoreplayertrackv3_player': [],
            'nba_data.boxscoreplayertrackv3_team': [],
            'nba_data.boxscorescoringv3_player': [],
            'nba_data.boxscorescoringv3_team': [],
            'nba_data.boxscoresummaryv2_game_info': [],
            'nba_data.boxscoresummaryv2_inactive_players': [],
            'nba_data.boxscoresummaryv2_other_stats': [],
            'nba_data.boxscoresummaryv2_referee': [],
            'nba_data.boxscoresummaryv2_summary': [],
            'nba_data.boxscoretraditionalv3_bench': [],
            'nba_data.boxscoretraditionalv3_player': [],
            'nba_data.boxscoretraditionalv3_team': [],
            'nba_data.boxscoreusagev3_player': [],
            'nba_data.boxscoreusagev3_team': [],
            'dateImportedToDB': []
        }

        if int(games) in importedGameList:
            print('\nGAME_ID {0} was previously imported into database, skipping. Game {1} of {2}'.format(str(games), str(index + 1),
                                                                                                                str(len(gamesList) + 1)))
            continue
        else:
            print('\nGAME_ID {0} NOT in database. Importing game {1} of {2}'.format(games,index+1, len(gamesList)+1))

            importedGamesMemory['gameId'].append(games)
            importedGamesMemory['dateImportedToDB'] = datetime.datetime.now(datetime.timezone.utc)

            for keys in tableGameIdColumn.keys():


                if games not in importedGamesDB[keys]:
                    # Entry doesn't exist in DB (i.e. sqlGameIdExistChecker returns empty list), so adding 0 in appropriate column
                    importedGamesMemory[keys].append(0)
                elif importedGamesDB[keys].count(games) == tableGameIdColumn[keys][2]:
                    # Entry exists, and matches how many entries are supposed to be there, then the database is correct, append 1
                    importedGamesMemory[keys].append(1)
                else:
                    # Entry exists, but doesn't match how many there are supposed to be there, so must delete everything and repopulate, append -1
                    importedGamesMemory[keys].append(-1)

            importedGamesMemory_df = pd.DataFrame.from_dict(importedGamesMemory)

            ###########################################################################################################
            if importedGamesMemory_df.loc[0, 'nba_data.boxscoreadvancedv3_player'] == 1:
                print('\nGAME_ID {} already has entry in nba_data.boxscoreadvancedv3_player'.format(games))
            elif importedGamesMemory_df.loc[0, 'nba_data.boxscoreadvancedv3_player'] == 0:
                try:
                    boxscoreadvancedv3_df = boxscoreadvancedv3.BoxScoreAdvancedV3(game_id=str(games)).get_data_frames()
                    boxscoreadvancedv3_df[0].to_sql(name = 'boxscoreadvancedv3_player', con=databaseConnection, if_exists = 'append', index = False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscoreadvancedv3_player'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscoreadvancedv3_player for game_id = {}'.format(str(games)))



            elif importedGamesMemory_df.loc[0, 'nba_data.boxscoreadvancedv3_player'] == -1:
                connection.execute(sql.text('delete from nba_data.boxscoreadvancedv3_player where gameId = {}'.format(games)))
                print('\nDeleted game_id = {} from  boxscoreadvancedv3_player due to multiple entries. '.format(str(games)))
                importedGamesMemory_df.loc[0,'nba_data.boxscoreadvancedv3_player'] = 0
                connection.commit()

                try:
                    boxscoreadvancedv3_df = boxscoreadvancedv3.BoxScoreAdvancedV3(game_id=str(games)).get_data_frames()
                    boxscoreadvancedv3_df[0].to_sql(name='boxscoreadvancedv3_player', con=databaseConnection,
                                                    if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscoreadvancedv3_player'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscoreadvancedv3_player for game_id = {}'.format(str(games)))
            ###########################################################################################################
            if importedGamesMemory_df.loc[0,'nba_data.boxscoreadvancedv3_team'] == 1:
                print('\nGAME_ID {} already has entry in nba_data.boxscoreadvancedv3_team'.format(games))
            elif importedGamesMemory_df.loc[0,'nba_data.boxscoreadvancedv3_team'] == 0:

                try:
                    boxscoreadvancedv3_df = boxscoreadvancedv3.BoxScoreAdvancedV3(game_id=str(games)).get_data_frames()
                    boxscoreadvancedv3_df[1].to_sql(name='boxscoreadvancedv3_team', con=databaseConnection,
                                                    if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscoreadvancedv3_team'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscoreadvancedv3_team for game_id = {}'.format(str(games)))


            elif importedGamesMemory_df.loc[0,'nba_data.boxscoreadvancedv3_team'] == -1:
                connection.execute(
                    sql.text('delete from nba_data.boxscoreadvancedv3_team where gameId = {}'.format(games)))
                print('\nDeleted game_id = {} from  boxscoreadvancedv3_team due to multiple entries. '.format(
                    str(games)))
                importedGamesMemory_df.loc[0,'nba_data.boxscoreadvancedv3_team'] = 0
                connection.commit()


                try:
                    boxscoreadvancedv3_df = boxscoreadvancedv3.BoxScoreAdvancedV3(game_id=str(games)).get_data_frames()
                    boxscoreadvancedv3_df[1].to_sql(name='boxscoreadvancedv3_team', con=databaseConnection,
                                                    if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscoreadvancedv3_team'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscoreadvancedv3_team for game_id = {}'.format(str(games)))
            ############################################################################################################
            if importedGamesMemory_df.loc[0,'nba_data.boxscoredefensivev2_team'] == 1:
                print('\nGAME_ID {} already has entry in nba_data.boxscoredefensivev2_team'.format(games))
            elif importedGamesMemory_df.loc[0,'nba_data.boxscoredefensivev2_team'] == 0:

                try:
                    boxscoredefensivev2_df = boxscoredefensivev2.BoxScoreDefensiveV2(
                        game_id=str(games)).get_data_frames()
                    boxscoredefensivev2_df[1].to_sql(name='boxscoredefensivev2_team', con=databaseConnection,
                                                    if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscoredefensivev2_team'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscoredefensivev2_team for game_id = {}'.format(str(games)))


            elif importedGamesMemory_df.loc[0,'nba_data.boxscoredefensivev2_team'] == -1:
                connection.execute(
                    sql.text('delete from nba_data.boxscoredefensivev2_team where gameId = {}'.format(games)))
                print('\nDeleted game_id = {} from  boxscoredefensivev2_team due to multiple entries. '.format(
                    str(games)))
                importedGamesMemory_df.loc[0,'nba_data.boxscoredefensivev2_team'] = 0
                connection.commit()


                try:
                    boxscoredefensivev2_df = boxscoredefensivev2.BoxScoreDefensiveV2(
                        game_id=str(games)).get_data_frames()
                    boxscoredefensivev2_df[1].to_sql(name='boxscoredefensivev2_team', con=databaseConnection,
                                                    if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscoredefensivev2_team'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscoredefensivev2_team for game_id = {}'.format(str(games)))
            ############################################################################################################
            if importedGamesMemory_df.loc[0,'nba_data.boxscoredefensivev2_player'] == 1:
                print('\nGAME_ID {} already has entry in nba_data.boxscoredefensivev2_player'.format(games))

            elif importedGamesMemory_df.loc[0,'nba_data.boxscoredefensivev2_player'] == 0:

                try:
                    boxscoredefensivev2_df = boxscoredefensivev2.BoxScoreDefensiveV2(
                        game_id=str(games)).get_data_frames()
                    boxscoredefensivev2_df[0].to_sql(name='boxscoredefensivev2_player', con=databaseConnection,
                                                     if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscoredefensivev2_player'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscoredefensivev2_player for game_id = {}'.format(str(games)))


            elif importedGamesMemory_df.loc[0,'nba_data.boxscoredefensivev2_player'] == -1:
                connection.execute(
                    sql.text('delete from nba_data.boxscoredefensivev2_player where gameId = {}'.format(games)))
                print('\nDeleted game_id = {} from  boxscoredefensivev2_player due to multiple entries. '.format(
                    str(games)))
                importedGamesMemory_df.loc[0,'nba_data.boxscoredefensivev2_player'] = 0
                connection.commit()


                try:
                    boxscoredefensivev2_df = boxscoredefensivev2.BoxScoreDefensiveV2(
                        game_id=str(games)).get_data_frames()
                    boxscoredefensivev2_df[0].to_sql(name='boxscoredefensivev2_player', con=databaseConnection,
                                                     if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscoredefensivev2_player'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscoredefensivev2_player for game_id = {}'.format(str(games)))
                ############################################################################################################
            if importedGamesMemory_df.loc[0,'nba_data.boxscorefourfactorsv3_player'] == 1:
                print('\nGAME_ID {} already has entry in nba_data.boxscorefourfactorsv3_player'.format(games))
            elif importedGamesMemory_df.loc[0,'nba_data.boxscorefourfactorsv3_player'] == 0:

                try:
                    boxscorefourfactorsv3_df = boxscorefourfactorsv3.BoxScoreFourFactorsV3(
                        game_id=str(games)).get_data_frames()
                    boxscorefourfactorsv3_df[0].to_sql(name='boxscorefourfactorsv3_player', con=databaseConnection,
                                                     if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscorefourfactorsv3_player'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscorefourfactorsv3_player for game_id = {}'.format(str(games)))


            elif importedGamesMemory_df.loc[0,'nba_data.boxscorefourfactorsv3_player'] == -1:
                connection.execute(
                    sql.text('delete from nba_data.boxscorefourfactorsv3_player where gameId = {}'.format(games)))
                print('\nDeleted game_id = {} from  boxscorefourfactorsv3_player due to multiple entries. '.format(
                    str(games)))
                importedGamesMemory_df.loc[0,'nba_data.boxscorefourfactorsv3_player'] = 0
                connection.commit()


                try:
                    boxscorefourfactorsv3_df = boxscorefourfactorsv3.BoxScoreFourFactorsV3(
                        game_id=str(games)).get_data_frames()
                    boxscorefourfactorsv3_df[0].to_sql(name='boxscorefourfactorsv3_player', con=databaseConnection,
                                                     if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscorefourfactorsv3_player'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscorefourfactorsv3_player for game_id = {}'.format(str(games)))
                ############################################################################################################
            if importedGamesMemory_df.loc[0,'nba_data.boxscorefourfactorsv3_team'] == 1:
                print('\nGAME_ID {} already has entry in nba_data.boxscorefourfactorsv3_team'.format(games))
            elif importedGamesMemory_df.loc[0,'nba_data.boxscorefourfactorsv3_team'] == 0:

                try:
                    boxscorefourfactorsv3_df = boxscorefourfactorsv3.BoxScoreFourFactorsV3(
                        game_id=str(games)).get_data_frames()
                    boxscorefourfactorsv3_df[1].to_sql(name='boxscorefourfactorsv3_team', con=databaseConnection,
                                                     if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscorefourfactorsv3_team'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscorefourfactorsv3_team for game_id = {}'.format(str(games)))


            elif importedGamesMemory_df.loc[0,'nba_data.boxscorefourfactorsv3_team'] == -1:
                connection.execute(
                    sql.text('delete from nba_data.boxscorefourfactorsv3_team where gameId = {}'.format(games)))
                print('\nDeleted game_id = {} from  boxscorefourfactorsv3_team due to multiple entries. '.format(
                    str(games)))
                importedGamesMemory_df.loc[0,'nba_data.boxscorefourfactorsv3_team'] = 0
                connection.commit()


                try:
                    boxscorefourfactorsv3_df = boxscorefourfactorsv3.BoxScoreFourFactorsV3(
                        game_id=str(games)).get_data_frames()
                    boxscorefourfactorsv3_df[1].to_sql(name='boxscorefourfactorsv3_team', con=databaseConnection,
                                                     if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscorefourfactorsv3_team'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscorefourfactorsv3_team for game_id = {}'.format(str(games)))
            ############################################################################################################
            if importedGamesMemory_df.loc[0,'nba_data.boxscorehustlev2_player'] == 1:
                print('\nGAME_ID {} already has entry in nba_data.boxscorehustlev2_player'.format(games))
            elif importedGamesMemory_df.loc[0,'nba_data.boxscorehustlev2_player'] == 0:

                try:
                    boxscorehustlev2_df = boxscorehustlev2.BoxScoreHustleV2(
                        game_id=str(games)).get_data_frames()
                    boxscorehustlev2_df[0].to_sql(name='boxscorehustlev2_player', con=databaseConnection,
                                                       if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscorehustlev2_player'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscorehustlev2_player for game_id = {}'.format(str(games)))


            elif importedGamesMemory_df.loc[0,'nba_data.boxscorehustlev2_player'] == -1:
                connection.execute(
                    sql.text('delete from nba_data.boxscorehustlev2_player where gameId = {}'.format(games)))
                print('\nDeleted game_id = {} from  boxscorehustlev2_player due to multiple entries. '.format(
                    str(games)))
                importedGamesMemory_df.loc[0,'nba_data.boxscorehustlev2_player'] = 0
                connection.commit()


                try:
                    boxscorehustlev2_df = boxscorehustlev2.BoxScoreHustleV2(
                        game_id=str(games)).get_data_frames()
                    boxscorehustlev2_df[0].to_sql(name='boxscorehustlev2_player', con=databaseConnection,
                                                       if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscorehustlev2_player'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscorehustlev2_player for game_id = {}'.format(str(games)))
                ############################################################################################################
            if importedGamesMemory_df.loc[0,'nba_data.boxscorehustlev2_team'] == 1:
                print('\nGAME_ID {} already has entry in nba_data.boxscorehustlev2_team'.format(games))
            elif importedGamesMemory_df.loc[0,'nba_data.boxscorehustlev2_team'] == 0:

                try:
                    boxscorehustlev2_df = boxscorehustlev2.BoxScoreHustleV2(
                        game_id=str(games)).get_data_frames()
                    boxscorehustlev2_df[1].to_sql(name='boxscorehustlev2_team', con=databaseConnection,
                                                       if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscorehustlev2_team'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscorehustlev2_team for game_id = {}'.format(str(games)))


            elif importedGamesMemory_df.loc[0,'nba_data.boxscorehustlev2_team'] == -1:
                connection.execute(
                    sql.text('delete from nba_data.boxscorehustlev2_team where gameId = {}'.format(games)))
                print('\nDeleted game_id = {} from  boxscorehustlev2_team due to multiple entries. '.format(
                    str(games)))
                importedGamesMemory_df.loc[0,'nba_data.boxscorehustlev2_team'] = 0
                connection.commit()


                try:
                    boxscorehustlev2_df = boxscorehustlev2.BoxScoreHustleV2(
                        game_id=str(games)).get_data_frames()
                    boxscorehustlev2_df[1].to_sql(name='boxscorehustlev2_team', con=databaseConnection,
                                                       if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscorehustlev2_team'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscorehustlev2_team for game_id = {}'.format(str(games)))
                ############################################################################################################
            if importedGamesMemory_df.loc[0,'nba_data.boxscoremiscv3_player'] == 1:
                print('\nGAME_ID {} already has entry in nba_data.boxscoremiscv3_player'.format(games))
            elif importedGamesMemory_df.loc[0,'nba_data.boxscoremiscv3_player'] == 0:

                try:
                    boxscoremiscv3_df = boxscoremiscv3.BoxScoreMiscV3(
                        game_id=str(games)).get_data_frames()
                    boxscoremiscv3_df[0].to_sql(name='boxscoremiscv3_player', con=databaseConnection,
                                                       if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscoremiscv3_player'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscoremiscv3_player for game_id = {}'.format(str(games)))


            elif importedGamesMemory_df.loc[0,'nba_data.boxscoremiscv3_player'] == -1:
                connection.execute(
                    sql.text('delete from nba_data.boxscoremiscv3_player where gameId = {}'.format(games)))
                print('\nDeleted game_id = {} from  boxscoremiscv3_player due to multiple entries. '.format(
                    str(games)))
                importedGamesMemory_df.loc[0,'nba_data.boxscoremiscv3_player'] = 0
                connection.commit()


                try:
                    boxscoremiscv3_df = boxscoremiscv3.BoxScoreMiscV3(
                        game_id=str(games)).get_data_frames()
                    boxscoremiscv3_df[0].to_sql(name='boxscoremiscv3_player', con=databaseConnection,
                                                       if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscoremiscv3_player'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscoremiscv3_player for game_id = {}'.format(str(games)))
                ############################################################################################################
            if importedGamesMemory_df.loc[0,'nba_data.boxscoremiscv3_team'] == 1:
                print('\nGAME_ID {} already has entry in nba_data.boxscoremiscv3_team'.format(games))
            elif importedGamesMemory_df.loc[0,'nba_data.boxscoremiscv3_team'] == 0:

                try:
                    boxscoremiscv3_df = boxscoremiscv3.BoxScoreMiscV3(
                        game_id=str(games)).get_data_frames()
                    boxscoremiscv3_df[1].to_sql(name='boxscoremiscv3_team', con=databaseConnection,
                                                       if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscoremiscv3_team'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscoremiscv3_team for game_id = {}'.format(str(games)))


            elif importedGamesMemory_df.loc[0,'nba_data.boxscoremiscv3_team'] == -1:
                connection.execute(
                    sql.text('delete from nba_data.boxscoremiscv3_team where gameId = {}'.format(games)))
                print('\nDeleted game_id = {} from  boxscoremiscv3_team due to multiple entries. '.format(
                    str(games)))
                importedGamesMemory_df.loc[0,'nba_data.boxscoremiscv3_team'] = 0
                connection.commit()

                try:
                    boxscoremiscv3_df = boxscoremiscv3.BoxScoreMiscV3(
                        game_id=str(games)).get_data_frames()
                    boxscoremiscv3_df[1].to_sql(name='boxscoremiscv3_team', con=databaseConnection,
                                                       if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscoremiscv3_team'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscoremiscv3_team for game_id = {}'.format(str(games)))
                ############################################################################################################
            if importedGamesMemory_df.loc[0,'nba_data.boxscoreplayertrackv3_player'] == 1:
                print('\nGAME_ID {} already has entry in nba_data.boxscoreplayertrackv3_player'.format(games))
            elif importedGamesMemory_df.loc[0,'nba_data.boxscoreplayertrackv3_player'] == 0:

                try:
                    boxscoreplayertrackv3_df = boxscoreplayertrackv3.BoxScorePlayerTrackV3(
                        game_id=str(games)).get_data_frames()
                    boxscoreplayertrackv3_df[0].to_sql(name='boxscoreplayertrackv3_player', con=databaseConnection,
                                                       if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscoreplayertrackv3_player'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscoreplayertrackv3_player for game_id = {}'.format(str(games)))


            elif importedGamesMemory_df.loc[0,'nba_data.boxscoreplayertrackv3_player'] == -1:
                connection.execute(
                    sql.text('delete from nba_data.boxscoreplayertrackv3_player where gameId = {}'.format(games)))
                print('\nDeleted game_id = {} from  boxscoreplayertrackv3_player due to multiple entries. '.format(
                    str(games)))
                importedGamesMemory_df.loc[0,'nba_data.boxscoreplayertrackv3_player'] = 0
                connection.commit()

                try:
                    boxscoreplayertrackv3_df = boxscoreplayertrackv3.BoxScorePlayerTrackV3(
                        game_id=str(games)).get_data_frames()
                    boxscoreplayertrackv3_df[0].to_sql(name='boxscoreplayertrackv3_player', con=databaseConnection,
                                                       if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscoreplayertrackv3_player'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscoreplayertrackv3_player for game_id = {}'.format(str(games)))
                ############################################################################################################
            if importedGamesMemory_df.loc[0,'nba_data.boxscoreplayertrackv3_team'] == 1:
                print('\nGAME_ID {} already has entry in nba_data.boxscoreplayertrackv3_team'.format(games))
            elif importedGamesMemory_df.loc[0,'nba_data.boxscoreplayertrackv3_team'] == 0:

                try:
                    boxscoreplayertrackv3_df = boxscoreplayertrackv3.BoxScorePlayerTrackV3(
                        game_id=str(games)).get_data_frames()
                    boxscoreplayertrackv3_df[1].to_sql(name='boxscoreplayertrackv3_team', con=databaseConnection,
                                                       if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscoreplayertrackv3_team'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscoreplayertrackv3_team for game_id = {}'.format(str(games)))


            elif importedGamesMemory_df.loc[0,'nba_data.boxscoreplayertrackv3_team'] == -1:
                connection.execute(
                    sql.text('delete from nba_data.boxscoreplayertrackv3_team where gameId = {}'.format(games)))
                print('\nDeleted game_id = {} from  boxscoreplayertrackv3_team due to multiple entries. '.format(
                    str(games)))
                importedGamesMemory_df.loc[0,'nba_data.boxscoreplayertrackv3_team'] = 0
                connection.commit()

                try:
                    boxscoreplayertrackv3_df = boxscoreplayertrackv3.BoxScorePlayerTrackV3(
                        game_id=str(games)).get_data_frames()
                    boxscoreplayertrackv3_df[1].to_sql(name='boxscoreplayertrackv3_team', con=databaseConnection,
                                                       if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscoreplayertrackv3_team'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscoreplayertrackv3_team for game_id = {}'.format(str(games)))
                    ############################################################################################################
            if importedGamesMemory_df.loc[0,'nba_data.boxscorescoringv3_player'] == 1:
                print('\nGAME_ID {} already has entry in nba_data.boxscorescoringv3_player'.format(games))
            elif importedGamesMemory_df.loc[0,'nba_data.boxscorescoringv3_player'] == 0:

                try:
                    boxscorescoringv3_df = boxscorescoringv3.BoxScoreScoringV3(
                        game_id=str(games)).get_data_frames()
                    boxscorescoringv3_df[0].to_sql(name='boxscorescoringv3_player', con=databaseConnection,
                                                       if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscorescoringv3_player'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscorescoringv3_player for game_id = {}'.format(str(games)))


            elif importedGamesMemory_df.loc[0,'nba_data.boxscorescoringv3_player'] == -1:
                connection.execute(
                    sql.text('delete from nba_data.boxscorescoringv3_player where gameId = {}'.format(games)))
                print('\nDeleted game_id = {} from  boxscorescoringv3_player due to multiple entries. '.format(
                    str(games)))
                importedGamesMemory_df.loc[0,'nba_data.boxscorescoringv3_player'] = 0
                connection.commit()

                try:
                    boxscorescoringv3_df = boxscorescoringv3.BoxScoreScoringV3(
                        game_id=str(games)).get_data_frames()
                    boxscorescoringv3_df[0].to_sql(name='boxscorescoringv3_player', con=databaseConnection,
                                                       if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscorescoringv3_player'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscorescoringv3_player for game_id = {}'.format(str(games)))
                ############################################################################################################
            if importedGamesMemory_df.loc[0,'nba_data.boxscorescoringv3_team'] == 1:
                print('\nGAME_ID {} already has entry in nba_data.boxscorescoringv3_team'.format(games))
            elif importedGamesMemory_df.loc[0,'nba_data.boxscorescoringv3_team'] == 0:

                try:
                    boxscorescoringv3_df = boxscorescoringv3.BoxScoreScoringV3(
                        game_id=str(games)).get_data_frames()
                    boxscorescoringv3_df[1].to_sql(name='boxscorescoringv3_team', con=databaseConnection,
                                                       if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscorescoringv3_team'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscorescoringv3_team for game_id = {}'.format(str(games)))


            elif importedGamesMemory_df.loc[0,'nba_data.boxscorescoringv3_team'] == -1:
                connection.execute(
                    sql.text('delete from nba_data.boxscorescoringv3_team where gameId = {}'.format(games)))
                print('\nDeleted game_id = {} from  boxscorescoringv3_team due to multiple entries. '.format(
                    str(games)))
                importedGamesMemory_df.loc[0,'nba_data.boxscorescoringv3_team'] = 0
                connection.commit()

                try:
                    boxscorescoringv3_df = boxscorescoringv3.BoxScoreScoringV3(
                        game_id=str(games)).get_data_frames()
                    boxscorescoringv3_df[1].to_sql(name='boxscorescoringv3_team', con=databaseConnection,
                                                       if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscorescoringv3_team'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscorescoringv3_team for game_id = {}'.format(str(games)))
                ############################################################################################################
            if importedGamesMemory_df.loc[0,'nba_data.boxscoreusagev3_player'] == 1:
                print('\nGAME_ID {} already has entry in nba_data.boxscoreusagev3_player'.format(games))
            elif importedGamesMemory_df.loc[0,'nba_data.boxscoreusagev3_player'] == 0:

                try:
                    boxscoreusagev3_df = boxscoreusagev3.BoxScoreUsageV3(
                        game_id=str(games)).get_data_frames()
                    boxscoreusagev3_df[0].to_sql(name='boxscoreusagev3_player', con=databaseConnection,
                                                       if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscoreusagev3_player'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscoreusagev3_player for game_id = {}'.format(str(games)))


            elif importedGamesMemory_df.loc[0,'nba_data.boxscoreusagev3_player'] == -1:
                connection.execute(
                    sql.text('delete from nba_data.boxscoreusagev3_player where gameId = {}'.format(games)))
                print('\nDeleted game_id = {} from  boxscoreusagev3_player due to multiple entries. '.format(
                    str(games)))
                importedGamesMemory_df.loc[0,'nba_data.boxscoreusagev3_player'] = 0
                connection.commit()

                try:
                    boxscoreusagev3_df = boxscoreusagev3.BoxScoreUsageV3(
                        game_id=str(games)).get_data_frames()
                    boxscoreusagev3_df[0].to_sql(name='boxscoreusagev3_player', con=databaseConnection,
                                                       if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscoreusagev3_player'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscoreusagev3_player for game_id = {}'.format(str(games)))
                ############################################################################################################
            if importedGamesMemory_df.loc[0,'nba_data.boxscoreusagev3_team'] == 1:
                print('\nGAME_ID {} already has entry in nba_data.boxscoreusagev3_team'.format(games))
            elif importedGamesMemory_df.loc[0,'nba_data.boxscoreusagev3_team'] == 0:

                try:
                    boxscoreusagev3_df = boxscoreusagev3.BoxScoreUsageV3(
                        game_id=str(games)).get_data_frames()
                    boxscoreusagev3_df[1].to_sql(name='boxscoreusagev3_team', con=databaseConnection,
                                                       if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscoreusagev3_team'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscoreusagev3_team for game_id = {}'.format(str(games)))


            elif importedGamesMemory_df.loc[0,'nba_data.boxscoreusagev3_team'] == -1:
                connection.execute(
                    sql.text('delete from nba_data.boxscoreusagev3_team where gameId = {}'.format(games)))
                print('\nDeleted game_id = {} from  boxscoreusagev3_team due to multiple entries. '.format(
                    str(games)))
                importedGamesMemory_df.loc[0,'nba_data.boxscoreusagev3_team'] = 0
                connection.commit()

                try:
                    boxscoreusagev3_df = boxscoreusagev3.BoxScoreUsageV3(
                        game_id=str(games)).get_data_frames()
                    boxscoreusagev3_df[1].to_sql(name='boxscoreusagev3_team', con=databaseConnection,
                                                       if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscoreusagev3_team'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscoreusagev3_team for game_id = {}'.format(str(games)))
                ############################################################################################################
            if importedGamesMemory_df.loc[0,'nba_data.boxscoresummaryv2_summary'] == 1:
                print('\nGAME_ID {} already has entry in nba_data.boxscoresummaryv2_summary'.format(games))
            elif importedGamesMemory_df.loc[0,'nba_data.boxscoresummaryv2_summary'] == 0:

                try:
                    boxscoresummaryv2_df = boxscoresummaryv2.BoxScoreSummaryV2(
                        game_id=str(games)).get_data_frames()
                    boxscoresummaryv2_df[1]['GAME_ID'] = games
                    boxscoresummaryv2_df[1].to_sql(name='boxscoresummaryv2_summary', con=databaseConnection,
                                                       if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscoresummaryv2_summary'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscoresummaryv2_summary for game_id = {}'.format(str(games)))


            elif importedGamesMemory_df.loc[0,'nba_data.boxscoresummaryv2_summary'] == -1:
                connection.execute(
                    sql.text('delete from nba_data.boxscoresummaryv2_summary where GAME_ID = {}'.format(games)))
                print('\nDeleted game_id = {} from  boxscoresummaryv2_summary due to multiple entries. '.format(
                    str(games)))
                importedGamesMemory_df.loc[0,'nba_data.boxscoresummaryv2_summary'] = 0
                connection.commit()


                try:
                    boxscoresummaryv2_df = boxscoresummaryv2.BoxScoreSummaryV2(
                        game_id=str(games)).get_data_frames()
                    boxscoresummaryv2_df[1]['GAME_ID'] = games
                    boxscoresummaryv2_df[1].to_sql(name='boxscoresummaryv2_summary', con=databaseConnection,
                                                       if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscoresummaryv2_summary'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscoresummaryv2_summary for game_id = {}'.format(str(games)))
                ############################################################################################################
            if importedGamesMemory_df.loc[0,'nba_data.boxscoresummaryv2_referee'] == 1:
                print('\nGAME_ID {} already has entry in nba_data.boxscoresummaryv2_referee'.format(games))
            elif importedGamesMemory_df.loc[0,'nba_data.boxscoresummaryv2_referee'] == 0:

                try:
                    boxscoresummaryv2_df = boxscoresummaryv2.BoxScoreSummaryV2(
                        game_id=str(games)).get_data_frames()
                    boxscoresummaryv2_df[2]['GAME_ID'] = games
                    boxscoresummaryv2_df[2].to_sql(name='boxscoresummaryv2_referee', con=databaseConnection,
                                                       if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscoresummaryv2_referee'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscoresummaryv2_referee for game_id = {}'.format(str(games)))


            elif importedGamesMemory_df.loc[0,'nba_data.boxscoresummaryv2_referee'] == -1:
                connection.execute(
                    sql.text('delete from nba_data.boxscoresummaryv2_referee where GAME_ID = {}'.format(games)))
                print('\nDeleted game_id = {} from  boxscoresummaryv2_referee due to multiple entries. '.format(
                    str(games)))
                importedGamesMemory_df.loc[0,'nba_data.boxscoresummaryv2_referee'] = 0
                connection.commit()


                try:
                    boxscoresummaryv2_df = boxscoresummaryv2.BoxScoreSummaryV2(
                        game_id=str(games)).get_data_frames()
                    boxscoresummaryv2_df[2]['GAME_ID'] = games
                    boxscoresummaryv2_df[2].to_sql(name='boxscoresummaryv2_referee', con=databaseConnection,
                                                       if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscoresummaryv2_referee'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscoresummaryv2_referee for game_id = {}'.format(str(games)))
                ############################################################################################################
            if importedGamesMemory_df.loc[0,'nba_data.boxscoresummaryv2_inactive_players'] == 1:
                print('\nGAME_ID {} already has entry in nba_data.boxscoresummaryv2_inactive_players'.format(games))
            elif importedGamesMemory_df.loc[0,'nba_data.boxscoresummaryv2_inactive_players'] == 0:

                try:
                    boxscoresummaryv2_df = boxscoresummaryv2.BoxScoreSummaryV2(
                        game_id=str(games)).get_data_frames()
                    boxscoresummaryv2_df[3]['GAME_ID'] = games
                    boxscoresummaryv2_df[3].to_sql(name='boxscoresummaryv2_inactive_players', con=databaseConnection,
                                                   if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscoresummaryv2_inactive_players'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscoresummaryv2_inactive_players for game_id = {}'.format(str(games)))


            elif importedGamesMemory_df.loc[0,'nba_data.boxscoresummaryv2_inactive_players'] == -1:
                connection.execute(
                    sql.text('delete from nba_data.boxscoresummaryv2_inactive_players where GAME_ID = {}'.format(games)))
                print('\nDeleted game_id = {} from  boxscoresummaryv2_inactive_players due to multiple entries. '.format(
                    str(games)))
                importedGamesMemory_df.loc[0,'nba_data.boxscoresummaryv2_inactive_players'] = 0
                connection.commit()



                try:
                    boxscoresummaryv2_df = boxscoresummaryv2.BoxScoreSummaryV2(
                        game_id=str(games)).get_data_frames()
                    boxscoresummaryv2_df[3]['GAME_ID'] = games
                    boxscoresummaryv2_df[3].to_sql(name='boxscoresummaryv2_inactive_players', con=databaseConnection,
                                                   if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscoresummaryv2_inactive_players'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscoresummaryv2_inactive_players for game_id = {}'.format(str(games)))

            ############################################################################################################
            if importedGamesMemory_df.loc[0,'nba_data.boxscoresummaryv2_other_stats'] == 1:
                print('\nGAME_ID {} already has entry in nba_data.boxscoresummaryv2_other_stats'.format(games))
            elif importedGamesMemory_df.loc[0,'nba_data.boxscoresummaryv2_other_stats'] == 0:


                try:
                    boxscoresummaryv2_df = boxscoresummaryv2.BoxScoreSummaryV2(
                        game_id=str(games)).get_data_frames()
                    boxscoresummaryv2_df[6].to_sql(name='boxscoresummaryv2_other_stats', con=databaseConnection,
                                                   if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscoresummaryv2_other_stats'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscoresummaryv2_other_stats for game_id = {}'.format(str(games)))


            elif importedGamesMemory_df.loc[0,'nba_data.boxscoresummaryv2_other_stats'] == -1:
                connection.execute(
                    sql.text('delete from nba_data.boxscoresummaryv2_other_stats where GAME_ID = {}'.format(games)))
                print('\nDeleted game_id = {} from  boxscoresummaryv2_other_stats due to multiple entries. '.format(
                    str(games)))
                importedGamesMemory_df.loc[0,'nba_data.boxscoresummaryv2_other_stats'] = 0
                connection.commit()



                try:
                    boxscoresummaryv2_df = boxscoresummaryv2.BoxScoreSummaryV2(
                        game_id=str(games)).get_data_frames()
                    boxscoresummaryv2_df[6].to_sql(name='boxscoresummaryv2_other_stats', con=databaseConnection,
                                                   if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscoresummaryv2_other_stats'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscoresummaryv2_other_stats for game_id = {}'.format(str(games)))
                ############################################################################################################
            ############################################################################################################
            if importedGamesMemory_df.loc[0,'nba_data.boxscoresummaryv2_game_info'] == 1:
                print('\nGAME_ID {} already has entry in nba_data.boxscoresummaryv2_game_info'.format(games))
            elif importedGamesMemory_df.loc[0,'nba_data.boxscoresummaryv2_game_info'] == 0:


                try:
                    boxscoresummaryv2_df = boxscoresummaryv2.BoxScoreSummaryV2(
                        game_id=str(games)).get_data_frames()
                    boxscoresummaryv2_df[7].to_sql(name='boxscoresummaryv2_game_info', con=databaseConnection,
                                                   if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscoresummaryv2_game_info'] = 1
                    connection.commit()
                except:
                    print(
                        '\nFailed to import boxscoresummaryv2_game_info for game_id = {}'.format(str(games)))


            elif importedGamesMemory_df.loc[0,'nba_data.boxscoresummaryv2_game_info'] == -1:
                connection.execute(
                    sql.text(
                        'delete from nba_data.boxscoresummaryv2_game_info where GAME_ID = {}'.format(games)))
                print(
                    '\nDeleted game_id = {} from  boxscoresummaryv2_game_info due to multiple entries. '.format(
                        str(games)))
                importedGamesMemory_df.loc[0,'nba_data.boxscoresummaryv2_game_info'] = 0
                connection.commit()



                try:
                    boxscoresummaryv2_df = boxscoresummaryv2.BoxScoreSummaryV2(
                        game_id=str(games)).get_data_frames()
                    boxscoresummaryv2_df[7].to_sql(name='boxscoresummaryv2_game_info', con=databaseConnection,
                                                   if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscoresummaryv2_game_info'] = 1
                    connection.commit()
                except:
                    print(
                        '\nFailed to import boxscoresummaryv2_game_info for game_id = {}'.format(str(games)))
                ###########################################################################################################
            if importedGamesMemory_df.loc[0,'nba_data.boxscoretraditionalv3_player'] == 1:
                print('\nGAME_ID {} already has entry in nba_data.boxscoretraditionalv3_player'.format(games))
            elif importedGamesMemory_df.loc[0,'nba_data.boxscoretraditionalv3_player'] == 0:


                try:
                    boxscoretraditionalv3_df = boxscoretraditionalv3.BoxScoreTraditionalV3(
                        game_id=str(games)).get_data_frames()
                    boxscoretraditionalv3_df[0].to_sql(name='boxscoretraditionalv3_player',
                                                   con=databaseConnection,
                                                   if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscoretraditionalv3_player'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscoretraditionalv3_player for game_id = {}'.format(
                        str(games)))


            elif importedGamesMemory_df.loc[0,'nba_data.boxscoretraditionalv3_player'] == -1:
                connection.execute(
                    sql.text('delete from nba_data.boxscoretraditionalv3_player where gameId = {}'.format(
                        games)))
                print(
                    '\nDeleted game_id = {} from  boxscoretraditionalv3_player due to multiple entries. '.format(
                        str(games)))
                importedGamesMemory_df.loc[0,'nba_data.boxscoretraditionalv3_player'] = 0
                connection.commit()


                try:
                    boxscoretraditionalv3_df = boxscoretraditionalv3.BoxScoreTraditionalV3(
                        game_id=str(games)).get_data_frames()
                    boxscoretraditionalv3_df[0].to_sql(name='boxscoretraditionalv3_player',
                                                   con=databaseConnection,
                                                   if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscoretraditionalv3_player'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscoretraditionalv3_player for game_id = {}'.format(
                        str(games)))
                ############################################################################################################
            if importedGamesMemory_df.loc[0,'nba_data.boxscoretraditionalv3_bench'] == 1:
                print('\nGAME_ID {} already has entry in nba_data.boxscoretraditionalv3_bench'.format(games))
            elif importedGamesMemory_df.loc[0,'nba_data.boxscoretraditionalv3_bench'] == 0:


                try:
                    boxscoretraditionalv3_df = boxscoretraditionalv3.BoxScoreTraditionalV3(
                        game_id=str(games)).get_data_frames()
                    boxscoretraditionalv3_df[1].to_sql(name='boxscoretraditionalv3_bench',
                                                       con=databaseConnection,
                                                       if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscoretraditionalv3_bench'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscoretraditionalv3_bench for game_id = {}'.format(
                        str(games)))


            elif importedGamesMemory_df.loc[0,'nba_data.boxscoretraditionalv3_bench'] == -1:
                connection.execute(
                    sql.text('delete from nba_data.boxscoretraditionalv3_bench where gameId = {}'.format(
                        games)))
                print(
                    '\nDeleted game_id = {} from  boxscoretraditionalv3_bench due to multiple entries. '.format(
                        str(games)))
                importedGamesMemory_df.loc[0,'nba_data.boxscoretraditionalv3_bench'] = 0
                connection.commit()



                try:
                    boxscoretraditionalv3_df = boxscoretraditionalv3.BoxScoreTraditionalV3(
                        game_id=str(games)).get_data_frames()
                    boxscoretraditionalv3_df[1].to_sql(name='boxscoretraditionalv3_bench',
                                                       con=databaseConnection,
                                                       if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscoretraditionalv3_bench'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscoretraditionalv3_bench for game_id = {}'.format(
                        str(games)))
                ############################################################################################################
            if importedGamesMemory_df.loc[0,'nba_data.boxscoretraditionalv3_team'] == 1:
                print('\nGAME_ID {} already has entry in nba_data.boxscoretraditionalv3_team'.format(games))
            elif importedGamesMemory_df.loc[0,'nba_data.boxscoretraditionalv3_team'] == 0:


                try:
                    boxscoretraditionalv3_df = boxscoretraditionalv3.BoxScoreTraditionalV3(
                        game_id=str(games)).get_data_frames()
                    boxscoretraditionalv3_df[2].to_sql(name='boxscoretraditionalv3_team',
                                                       con=databaseConnection,
                                                       if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscoretraditionalv3_team'] = 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscoretraditionalv3_team for game_id = {}'.format(
                        str(games)))


            elif importedGamesMemory_df.loc[0,'nba_data.boxscoretraditionalv3_team'] == -1:
                connection.execute(
                    sql.text('delete from nba_data.boxscoretraditionalv3_team where gameId = {}'.format(
                        games)))
                print(
                    '\nDeleted game_id = {} from  boxscoretraditionalv3_team due to multiple entries. '.format(
                        str(games)))
                importedGamesMemory_df.loc[0,'nba_data.boxscoretraditionalv3_team'] = 0
                connection.commit()



                try:
                    boxscoretraditionalv3_df = boxscoretraditionalv3.BoxScoreTraditionalV3(
                        game_id=str(games)).get_data_frames()
                    boxscoretraditionalv3_df[2].to_sql(name='boxscoretraditionalv3_team',
                                                       con=databaseConnection,
                                                       if_exists='append', index=False)
                    importedGamesMemory_df.loc[0,'nba_data.boxscoretraditionalv3_team']= 1
                    connection.commit()
                except:
                    print('\nFailed to import boxscoretraditionalv3_team for game_id = {}'.format(
                        str(games)))
                ############################################################################################################

            importedGamesMemory_df.to_sql(name='importedgamesmemory', con=databaseConnection, if_exists='append',
                         index=False)
            connection.commit()
    end = timeit.default_timer()
    print('\nProcess completed after {} seconds'.format(str(end-start)))
    connection.close()

