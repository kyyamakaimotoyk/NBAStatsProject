import plotly as plt
import plotly.express as px
import plotly.graph_objects as go
import sqlalchemy as sql
from nba_api.stats.static import teams, players
import pandas as pd

import dash
from dash import dcc
from dash import html
from dash import callback, Input, Output
from dash import dash_table
from itertools import cycle
import dash_bootstrap_components as dbc
from dash_bootstrap_templates import load_figure_template
from datetime import datetime
import plotly.graph_objects as go
import numpy as np
from sklearn.feature_selection import SelectKBest, f_regression

#credentials to SQL Database
host = 'localhost'
user = 'kaiyamamoto'
password = 'KN!yoWMhiH8cBvD'
port = '3306'
database = 'nba_data'

#creating a url to be used as an argument into sql.create_engine
url_db = sql.URL.create(drivername = 'mysql', username = 'kaiyamamoto', password = 'KN!yoWMhiH8cBvD', port = '3306',
                        database = 'nba_data')

#creating sql engine
databaseEngine = sql.create_engine(url_db)
#connecting to sql database using engine
conn = databaseEngine.connect()

# getting list of teams and players, to look up playerID and teamID for dataframe creation

#using pandas.read_sql_query and the connection to query in database, and outputing a dataframe
df = pd.read_sql_query('''select 
GAME_DATE,
MATCHUP,
WL,
MIN,
PTS,
FGM,
FGA,
FG_PCT,
FG3M,
FG3A,
FG3_PCT,
FTM,
FTA,
FT_PCT,
OREB,
DREB,
REB,
AST,
STL,
BLK,
TOV,
PF,
PLUS_MINUS,
bff.effectiveFieldGoalPercentage,
bff.freeThrowAttemptRate,
bff.teamTurnoverPercentage,
bff.offensiveReboundPercentage,
bff.oppEffectiveFieldGoalPercentage,
bff.oppFreeThrowAttemptRate,
bff.oppTeamTurnoverPercentage,
bff.oppOffensiveReboundPercentage,
bpt.distance,
bpt.reboundChancesOffensive,
bpt.reboundChancesDefensive,
bpt.reboundChancesTotal,
bpt.touches,
bpt.secondaryAssists,
bpt.freeThrowAssists,
bpt.passes,
bpt.contestedFieldGoalsMade,
bpt.contestedFieldGoalsAttempted,
bpt.contestedFieldGoalPercentage,
bpt.uncontestedFieldGoalsMade,
bpt.uncontestedFieldGoalsAttempted,
bpt.uncontestedFieldGoalsPercentage,
bpt.defendedAtRimFieldGoalsMade,
bpt.defendedAtRimFieldGoalsAttempted,
bpt.defendedAtRimFieldGoalPercentage,
bst.teamName,
bsh.contestedShots,
bsh.contestedShots2pt,
bsh.contestedShots3pt,
bsh.deflections,
bsh.chargesDrawn,
bsh.screenAssists,
bsh.screenAssistPoints,
bsh.looseBallsRecoveredOffensive,
bsh.looseBallsRecoveredDefensive,
bsh.looseBallsRecoveredTotal,
bsh.offensiveBoxOuts,
bsh.defensiveBoxOuts,
bsh.boxOutPlayerTeamRebounds,
bsh.boxOutPlayerRebounds,
bsh.boxOuts,
bss.percentageFieldGoalsAttempted2pt,
bss.percentageFieldGoalsAttempted3pt,
bss.percentagePoints2pt,
bss.percentagePointsMidrange2pt,
bss.percentagePoints3pt,
bss.percentagePointsFastBreak,
bss.percentagePointsFreeThrow,
bss.percentagePointsOffTurnovers,
bss.percentagePointsPaint,
bss.percentageAssisted2pt,
bss.percentageUnassisted2pt,
bss.percentageAssisted3pt,
bss.percentageUnassisted3pt,
bss.percentageAssistedFGM,
bss.percentageUnassistedFGM,
bsm.pointsOffTurnovers,
bsm.pointsSecondChance,
bsm.pointsPaint,
bsm.oppPointsOffTurnovers,
bsm.oppPointsSecondChance,
bsm.oppPointsFastBreak,
bsm.oppPointsPaint,
bsm.blocksAgainst,
bsm.foulsPersonal,
bsm.foulsDrawn

    from nba_data.game_list as gl
    left join nba_data.boxscorefourfactorsv3_team as bff 
    on (gl.GAME_ID = bff.gameId and gl.TEAM_ID = bff.teamId) 
    left join nba_data.boxscoreplayertrackv3_team as bpt 
    on (gl.GAME_ID = bpt.gameId and gl.TEAM_ID = bpt.teamId) 
    left join nba_data.boxscoretraditionalv3_team as bst
    on (gl.GAME_ID = bst.gameId and gl.TEAM_ID = bst.teamId)
    left join nba_data.boxscorehustlev2_team as bsh
    on (gl.GAME_ID = bsh.gameId and gl.TEAM_ID = bsh.teamId)
    left join nba_data.boxscorescoringv3_team as bss
    on (gl.GAME_ID = bss.gameId and gl.TEAM_ID = bss.teamId)
    left join nba_data.boxscoremiscv3_team as bsm
    on (gl.GAME_ID = bsm.gameId and gl.TEAM_ID = bsm.teamId)
    order by gl.GAME_ID''', conn)

conn.close()
# Permanently changes the pandas settings for DataFrame display
pd.set_option('display.max_columns', None)
pd.set_option('display.width', None)

kbest = SelectKBest(score_func = f_regression, k = 20)

y_data = df.select_dtypes(exclude = ['object', 'datetime']).dropna().PLUS_MINUS.loc[(df.GAME_DATE >= datetime(2021,9,1)) & (df.GAME_DATE <= datetime(2024,7, 8))]
x_data = df.select_dtypes(exclude = ['object', 'datetime']).dropna().drop(columns = 'PLUS_MINUS').loc[(df.GAME_DATE >= datetime(2021,9,1)) & (df.GAME_DATE <= datetime(2024,7, 8))]
print(y_data.shape)
print(x_data.shape)
x_data_new = kbest.fit_transform(x_data, y_data)

colNames = []
for feature_list_index in kbest.get_support(indices = True):
    colNames.append(x_data.columns[feature_list_index])

df_new = df.select_dtypes(exclude = ['object', 'datetime']).dropna().loc[(df.GAME_DATE >= datetime(2021,9,1)) & (df.GAME_DATE <= datetime(2024,7, 8))].loc[:, colNames]
df_new = df_new.join(y_data, how = 'inner')

#
# print('Number of features before feature selection: {}'.format(x_data.shape[1]))
# print('Number of features after feature selection: {}'.format(x_data_new.shape[1]))
#
# for feature_list_index in kbest.get_support(indices = True):
#     print(feature_list_index, ' - ', x_data.columns[feature_list_index])