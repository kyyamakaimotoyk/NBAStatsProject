# Project-root bootstrap so cross-folder imports (core.*, modeling.*, orchestration.*)
# work regardless of CWD.
import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

import plotly as plt
import plotly.express as px
import plotly.graph_objects as go
import sqlalchemy as sql
from nba_api.stats.static import teams, players
import pandas as pd
import os
import json

import dash
from dash import dcc
from dash import html
from dash import callback, Input, Output
from dash import dash_table
from itertools import cycle
import dash_bootstrap_components as dbc
from dash_bootstrap_templates import load_figure_template
from datetime import date, datetime, timedelta
import plotly.graph_objects as go
import numpy as np
from sklearn.feature_selection import SelectKBest
from plotly.subplots import make_subplots
import joblib


########################################################################################################################

# MySQL config now lives in environment variables (see db.py / .env.example)
from core.db import get_engine
databaseEngine = get_engine()
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

########################################################################################################################
# Load ML Features Dataset (from feature_engineering.py output)
########################################################################################################################

# nba_ml_features.csv lives at the project root (one level above visualization/),
# so resolve the path relative to the repo root, not this script's folder.
try:
    _project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
except NameError:
    _project_root = os.getcwd()
ml_features_path = os.path.join(_project_root, 'nba_ml_features.csv')
if os.path.exists(ml_features_path):
    df_ml = pd.read_csv(ml_features_path)
    df_ml['GAME_DATE'] = pd.to_datetime(df_ml['GAME_DATE'])
    print(f"Loaded ML features: {len(df_ml)} games, {len(df_ml.columns)} columns")
    ML_FEATURES_AVAILABLE = True
else:
    print("Warning: nba_ml_features.csv not found. Run feature_engineering.py first.")
    df_ml = pd.DataFrame()
    ML_FEATURES_AVAILABLE = False

# Extract rolling feature columns for the feature tracker
if ML_FEATURES_AVAILABLE:
    # Get all rolling feature columns (L5 and L10)
    rolling_feature_cols = [col for col in df_ml.columns if '_L5' in col or '_L10' in col]

    # Separate HOME, AWAY, and DIFF features
    home_rolling_features = sorted([col for col in rolling_feature_cols if col.startswith('HOME_')])
    away_rolling_features = sorted([col for col in rolling_feature_cols if col.startswith('AWAY_')])
    diff_rolling_features = sorted([col for col in rolling_feature_cols if col.startswith('DIFF_')])

    # Get unique team names from the ML dataset
    ml_team_columns = df_ml['HOME_TEAM_NAME'].dropna().unique().tolist() if 'HOME_TEAM_NAME' in df_ml.columns else []

#######################################################################################################################

# app creation/formatting

load_figure_template(['slate', 'minty_dark'])

#Needed to match theme between dbc and dcc
dbc_css = "https://cdn.jsdelivr.net/gh/AnnMarieW/dash-bootstrap-templates/dbc.min.css"
app = dash.Dash(__name__, external_stylesheets = [dbc.themes.SLATE, dbc.icons.FONT_AWESOME, dbc_css])

WLcolorPalette = {'W':'#FA7851', #orange
                  'L': '#95DFC9' #green
                  }

colorPalette = {
    'Hawks':'#E03A3E',
    'Celtics':'#007A33',
    'Nets': '#000000',
    'Hornets': '#1D1160',
    'Bulls': '#CE1141',
    'Cavaliers':'#860038',
    'Mavericks': '#00538C',
    'Nuggets':'#0E2240',
    'Pistons': '#C8102E',
    'Warriors': '#1D428A',
    'Rockets': '#CE1141',
    'Pacers': '#002D62',
    'Clippers': '#C8102E',
    'Lakers': '#552583',
    'Grizzlies': '#5D76A9',
    'Heat': '#98002E',
    'Bucks': '#00471B',
    'Timberwolves': '#0C2340',
    'Knicks': '#006BB6',
    'Thunder': '#007AC1',
    'Magic': '#0077C0',
    '76ers': '#006BB6',
    'Suns': '#1D1160',
    'Trail Blazers': '#E03A3E',
    'Kings': '#5A2D81',
    'Spurs': '#C4CED4',
    'Raptors': '#CE1141',
    'Jazz': '#002B5C',
    'Wizards': '#002B5C',
    'Pelicans': '#0C2340'
}

########################################################################################################################
xColumns = sorted(df.columns, key = str.lower)
yColumns = sorted(df.columns, key = str.lower)

xDropdown = html.Div(
    [
        html.Label('Select horizontal axis variable', htmlFor = 'x_val'),
        dcc.Dropdown(options = xColumns,
                     value = 'GAME_DATE',
                     searchable = True,
                     id = 'x_val',
                     className = 'dbc'
        )
    ]
)

yDropdown = html.Div(
    [
        html.Label('Select vertical axis variable', htmlFor = 'y_val'),
        dcc.Dropdown(options = yColumns,
                     value = 'FG3A',
                     searchable = True,
                     id = 'y_val',
                     className = 'dbc'

        )
    ]
)

datePicker = html.Div(
    [
        html.Label(children = 'Select date range of stats', htmlFor = 'datePicker'),
        html.Br(),
        dcc.DatePickerRange(
            id = 'datePicker',
            start_date = min(df.GAME_DATE),
            end_date = max(df.GAME_DATE),
            display_format = 'YYYY MM DD',
            className = 'dbc'
        )
    ]
)

statListGroup = dbc.ListGroup(
    id = 'statList',
    children = [
        dbc.ListGroupItem(
            children = 'Number of data points: {} games. ({} teams)'.format(len(df)//2, len(df)),
            id = 'listItemNumDataPoints'
        )
    ]
)


@dash.callback(
    [
        Output('leagueChart','figure'),
        Output('listItemNumDataPoints', 'children')
    ],
    [
        Input('x_val', 'value'),
        Input('y_val', 'value'),
        Input('datePicker', 'start_date'),
        Input('datePicker', 'end_date')
    ]
)
def overallScatter(x, y, startDate, endDate):
    # startDate = date.fromisoformat(startDate)
    # endDate = date.fromisoformat(endDate)

    fig = px.scatter(data_frame = df.loc[(df.GAME_DATE>=startDate)&(df.GAME_DATE <= endDate)],
                     x = x,
                     y = y,
                     color = 'WL', symbol = 'WL',
                     hover_data = ['GAME_DATE', 'MATCHUP', 'teamName', x, y],
                     width = 800,
                     height = 800,
                     marginal_x='box',
                     marginal_y = 'box',
                     template = 'minty_dark',
                     color_discrete_map = WLcolorPalette,
                     trendline="ols",
                     opacity = 0.2

                     )


    if x == 'GAME_DATE':
        fig = px.scatter(data_frame=df.loc[(df.GAME_DATE >= startDate) & (df.GAME_DATE <= endDate)],
                         x=x,
                         y=y,
                         color='WL', symbol = 'WL',
                         hover_data=['GAME_DATE', 'MATCHUP', 'teamName', x, y],
                         width=800,
                         height=800,
                         marginal_x='box',
                         marginal_y='box',
                         template='minty_dark',
                         color_discrete_map = WLcolorPalette,
                         trendline='rolling',
                         trendline_options=dict(window=50),
                         opacity = 0.2
                         )

    fig.update_layout(font=dict(
        size=18))

    #Finding which id are the trendline, and formatting the trendline to make it more prominent
    tr_line = []
    for k, trace in enumerate(fig.data):
        try:
            if trace.mode is not None and trace.mode == 'lines':
                tr_line.append(k)
        except:
            pass


    linecolor = ['#3BB27A',# green for losses
                '#F34109'  #orange for wins
                 ]
    linecycle = cycle(linecolor)
    for id in tr_line:
        fig.data[id].update(line = dict(width=5,
                            color = next(linecycle)))

    listItemNumChild = 'Number of data points: {} games. ({} teams)'.format(len(df.loc[(df.GAME_DATE>=startDate)&(df.GAME_DATE <= endDate)])//2, len(df.loc[(df.GAME_DATE>=startDate)&(df.GAME_DATE <= endDate)]))

    return fig, listItemNumChild


#######################################################################################################################

xDropdownTeam = html.Div(
    [
        html.Label('Select horizontal axis variable', htmlFor = 'x_valTeam'),
        dcc.Dropdown(options = xColumns,
                     value = 'GAME_DATE',
                     searchable = True,
                     id = 'x_valTeam',
                     className = 'dbc'
        )
    ]
)

yDropdownTeam = html.Div(
    [
        html.Label('Select vertical axis variable', htmlFor = 'y_valTeam'),
        dcc.Dropdown(options = yColumns,
                     value = 'FG3A',
                     searchable = True,
                     id = 'y_valTeam',
                     className = 'dbc'

        )
    ]
)

teamColumns = sorted(df['teamName'].dropna().unique())

teamPicker = html.Div(
    [
        html.Label('Select team to plot', htmlFor = 'teamPicker'),
        dcc.Dropdown(options = teamColumns,
                     searchable = True,
                     multi = True,
                     id = 'teamPicker',
                     className = 'dbc')
    ]
)

datePickerTeam = html.Div(
    [
        html.Label(children = 'Select date range of stats', htmlFor = 'datePickerTeam'),
        html.Br(),
        dcc.DatePickerRange(
            id = 'datePickerTeam',
            start_date = min(df.GAME_DATE),
            end_date = max(df.GAME_DATE),
            display_format = 'YYYY MM DD',
            className = 'dbc'
        )
    ]
)

statListGroupTeam = dbc.ListGroup(
    id = 'statListTeam',
    children = [
        dbc.ListGroupItem(
            children = 'Number of data points: {} games. ({} teams)'.format(len(df)//2, len(df)),
            id = 'listItemNumDataPointsTeam'
        )
    ]
)

@dash.callback(
    [
        Output('teamChart','figure'),
        Output('listItemNumDataPointsTeam', 'children')
    ],
    [
        Input('x_valTeam', 'value'),
        Input('y_valTeam', 'value'),
        Input('datePickerTeam', 'start_date'),
        Input('datePickerTeam', 'end_date'),
        Input('teamPicker', 'value')
    ]
)
def teamScatter(x, y, startDate, endDate, teamList):
    # startDate = date.fromisoformat(startDate)
    # endDate = date.fromisoformat(endDate)
    fig = px.scatter(data_frame = df.loc[(df.GAME_DATE>=startDate)&(df.GAME_DATE <= endDate)&(df.teamName.isin(teamList))],
                     x = x,
                     y = y,
                     color = 'teamName', symbol = 'teamName',
                     hover_data = ['GAME_DATE', 'MATCHUP', 'teamName', x, y],
                     width = 800,
                     height = 800,
                     marginal_x='box',
                     marginal_y = 'box',
                     color_discrete_map = colorPalette,
                     template = 'plotly_white',
                     trendline="ols",
                     opacity = 0.2
                     )


    if x == 'GAME_DATE':
        fig = px.scatter(
            data_frame=df.loc[(df.GAME_DATE >= startDate) & (df.GAME_DATE <= endDate) & (df.teamName.isin(teamList))],
            x=x,
            y=y,
            color='teamName', symbol = 'teamName',
            hover_data=['GAME_DATE', 'MATCHUP', 'teamName', x, y],
            width=800,
            height=800,
            marginal_x='box',
            marginal_y='box',
            color_discrete_map=colorPalette,
            template='plotly_white',
            trendline='rolling',
            trendline_options=dict(window=5),
            opacity = 0.2
            )

    fig.update_layout(font=dict(
        size=18))

    # Finding which id are the trendline, and formatting the trendline to make it more prominent
    tr_line = []
    for k, trace in enumerate(fig.data):
        try:
            if trace.mode is not None and trace.mode == 'lines':
                tr_line.append(k)
        except:
            pass


    for id in tr_line:
        fig.data[id].update(line_width=5)


    listItemNumChild = 'Number of data points: {} games. ({} teams)'.format(len(df.loc[(df.GAME_DATE>=startDate)&(df.GAME_DATE <= endDate)&(df.teamName.isin(teamList))])//2, len(df.loc[(df.GAME_DATE>=startDate)&(df.GAME_DATE <= endDate)&(df.teamName.isin(teamList))]))

    return fig, listItemNumChild


########################################################################################################################
datePickerScatterMatrix = html.Div(
    [
        html.Label(children = 'Select date range of stats', htmlFor = 'datePickerScatterMatrix'),
        html.Br(),
        dcc.DatePickerRange(
            id = 'datePickerScatterMatrix',
            start_date = min(df.GAME_DATE),
            end_date = max(df.GAME_DATE),
            display_format = 'YYYY MM DD',
            className = 'dbc' #needed for theming/color to match dbc (dash bootstrap components)
        )
    ]
)

teamPickerScatterMatrix = html.Div(
    [
        html.Label('Select team to plot', htmlFor = 'teamPickerScatterMatrix'),
        dcc.Dropdown(options = teamColumns,
                     searchable = True,
                     multi = True,
                     id = 'teamPicker',
                     className = 'dbc')
    ]
)

attributeList = df.select_dtypes(exclude = ['datetime', 'object']).columns.to_list()

attributeDropdown = html.Div(
    [
        html.Label('Select stat to analyze', htmlFor = 'attributePicker'),
        dcc.Dropdown(
            options = attributeList,
            searchable = True,
            multi = False,
            id = 'attributePicker',
            className = 'dbc'
        )
    ]
)

countList = [i for i in range(1,11)]
attributeCount = html.Div(
    [
        html.Label('Select top N correlated stats', htmlFor = 'countPicker'),
        dcc.Dropdown(
            options = countList,
            searchable = True,
            multi = False,
            id = 'countPicker',
            className = 'dbc'
        )
    ]
)

featureSelectionBanner = dbc.ListGroup(
    id = 'featureSelectionBanner',
    children = [
        dbc.ListGroupItem(
            id = 'featureSelection'
        )
    ]
)

from sklearn.feature_selection import SelectKBest, f_regression
from datetime import datetime, date

@dash.callback(
        [
        Output('scatterMatrix', 'figure')
        ],
        [
        Input('datePickerScatterMatrix', 'start_date'),
        Input('datePickerScatterMatrix', 'end_date')
        ]
)
def scatterMatrix(startDate, endDate):

    df_corr = df.loc[(df.GAME_DATE >= startDate) & (df.GAME_DATE <= endDate)].select_dtypes(exclude = ['object','datetime']).drop(columns = ['MIN']).corr()
    fig = go.Figure()
    fig.add_trace(
        go.Heatmap(
            x = df_corr.columns,
            y = df_corr.index,
            z = np.array(df_corr),
            text = df_corr.values,
            texttemplate = '%{text:.2f}'
        )
    )

    fig.update_layout(dict(
        height = 3000,
        width = 3000
    ))
    return [fig]

@dash.callback([
        Output('reducedCorrelationMatrix', 'figure'),
        Output('reducedScatterMatrix', 'figure'),
        Output('featureSelection', 'children')
    ],
    [
        Input('datePickerScatterMatrix', 'start_date'),
        Input('datePickerScatterMatrix', 'end_date'),
        Input('attributePicker', 'value'),
        Input('countPicker', 'value')
    ]
)
def reducedCorrelationMatrix(startDate, endDate, attribute, count):
    kbest = SelectKBest(score_func=f_regression, k=count)
    y_data = df.select_dtypes(exclude=['object', 'datetime']).dropna().loc[:,attribute].loc[
        (df.GAME_DATE >= startDate) & (df.GAME_DATE <= endDate)]
    x_data = df.select_dtypes(exclude=['object', 'datetime']).dropna().drop(columns=attribute).loc[
        (df.GAME_DATE >= startDate) & (df.GAME_DATE <=endDate)]

    x_data_new = kbest.fit_transform(x_data, y_data)

    colNames = []


    for feature_list_index in kbest.get_support(indices=True):
        colNames.append(x_data.columns[feature_list_index])





    featureSelectionDisplay = "The top {} correlated features to the attribute {} are: \n{}".format(count, attribute, kbest.get_feature_names_out())

    df_new = df.select_dtypes(exclude=['object', 'datetime']).dropna().loc[(df.GAME_DATE >=
                 startDate) & (df.GAME_DATE <= endDate)].loc[:, colNames]

    df_new = df_new.join(y_data, how='inner')

    df_new_correlation = df_new.corr()
    fig = go.Figure()
    fig.add_trace(
        go.Heatmap(
            x = df_new_correlation.columns,
            y = df_new_correlation.index[::-1], #Need to reverse order to match the format of px.scatter_matrix
            z = np.array(df_new_correlation)[::-1],#Need to reverse order to match the format of px.scatter_matrix
            text = df_new_correlation.values[::-1],#Need to reverse order to match the format of px.scatter_matrix
            texttemplate = '%{text:.2f}'
        )
    )
    fig.update_layout(dict(
        height = 1200,
        width = 1200
    ))

    fig2 = px.scatter_matrix(
        data_frame=df_new,
        template='minty_dark',
    )
    fig2.update_layout(dict(
        height=1200,
        width=1200
    ))

    return fig, fig2, featureSelectionDisplay



########################################################################################################################
# TAB 4: Rolling Feature Tracker (Track features over season by team)
########################################################################################################################

if ML_FEATURES_AVAILABLE:
    # Feature category mapping for organized dropdown
    feature_categories = {
        'Traditional': ['PTS', 'FGM', 'FGA', 'FG_PCT', 'FG3M', 'FG3A', 'FG3_PCT', 'FTM', 'FTA', 'FT_PCT',
                       'OREB', 'DREB', 'REB', 'AST', 'STL', 'BLK', 'TOV', 'PF', 'PLUS_MINUS'],
        'Advanced': ['offensiveRating', 'defensiveRating', 'netRating', 'pace', 'possessions',
                    'EFG_PCT', 'TS_PCT', 'assistPercentage', 'assistToTurnover', 'PIE'],
        'Four Factors': ['FT_RATE', 'TOV_PCT', 'OREB_PCT', 'OPP_EFG_PCT', 'OPP_FT_RATE', 'OPP_TOV_PCT'],
        'Hustle': ['contestedShots', 'deflections', 'chargesDrawn', 'looseBallsRecovered', 'boxOuts'],
        'Tracking': ['speed', 'distance', 'touches', 'passes', 'secondaryAssists'],
        'Misc': ['pointsOffTurnovers', 'pointsSecondChance', 'pointsFastBreak', 'pointsPaint'],
        'Scoring': ['pctFGA_2pt', 'pctFGA_3pt', 'pctPTS_2pt', 'pctPTS_3pt', 'pctAssisted']
    }

    # Build feature options with categories
    feature_options_tracker = []
    for cat, features in feature_categories.items():
        for feat in features:
            # Check if L5 version exists in home features
            l5_col = f'HOME_{feat}_L5'
            if l5_col in home_rolling_features:
                feature_options_tracker.append({'label': f'{feat} ({cat})', 'value': feat})

    teamPickerFeatureTracker = html.Div([
        html.Label('Select teams to compare', htmlFor='teamPickerFeatureTracker'),
        dcc.Dropdown(
            options=sorted(ml_team_columns),
            searchable=True,
            multi=True,
            value=ml_team_columns[:2] if len(ml_team_columns) >= 2 else ml_team_columns,
            id='teamPickerFeatureTracker',
            className='dbc'
        )
    ])

    featurePickerTracker = html.Div([
        html.Label('Select feature to track', htmlFor='featurePickerTracker'),
        dcc.Dropdown(
            options=feature_options_tracker,
            searchable=True,
            value='PTS',
            id='featurePickerTracker',
            className='dbc'
        )
    ])

    windowPicker = html.Div([
        html.Label('Rolling window', htmlFor='windowPicker'),
        dcc.RadioItems(
            options=[{'label': 'Last 5 games (L5)', 'value': 'L5'},
                    {'label': 'Last 10 games (L10)', 'value': 'L10'}],
            value='L5',
            id='windowPicker',
            inline=True,
            className='dbc'
        )
    ])

    datePickerFeatureTracker = html.Div([
        html.Label('Select date range', htmlFor='datePickerFeatureTracker'),
        html.Br(),
        dcc.DatePickerRange(
            id='datePickerFeatureTracker',
            start_date=df_ml['GAME_DATE'].min() if len(df_ml) > 0 else date(2020, 1, 1),
            end_date=df_ml['GAME_DATE'].max() if len(df_ml) > 0 else date(2025, 12, 31),
            display_format='YYYY MM DD',
            className='dbc'
        )
    ])

    @dash.callback(
        Output('featureTrackerChart', 'figure'),
        [
            Input('teamPickerFeatureTracker', 'value'),
            Input('featurePickerTracker', 'value'),
            Input('windowPicker', 'value'),
            Input('datePickerFeatureTracker', 'start_date'),
            Input('datePickerFeatureTracker', 'end_date')
        ]
    )
    def updateFeatureTracker(teams, feature, window, startDate, endDate):
        if not teams or not feature:
            return go.Figure()

        # Build the column name
        col_name = f'HOME_{feature}_{window}'

        if col_name not in df_ml.columns:
            return go.Figure().add_annotation(text=f"Feature {col_name} not found", showarrow=False)

        # Filter data
        mask = (df_ml['GAME_DATE'] >= startDate) & (df_ml['GAME_DATE'] <= endDate)
        filtered_df = df_ml[mask].copy()

        fig = go.Figure()

        for team in teams:
            # Get games where this team played at home
            team_home = filtered_df[filtered_df['HOME_TEAM_NAME'] == team].copy()
            team_home['feature_val'] = team_home[col_name]
            team_home['location'] = 'Home'

            # Get games where this team played away
            away_col = col_name.replace('HOME_', 'AWAY_')
            team_away = filtered_df[filtered_df['AWAY_TEAM_NAME'] == team].copy()
            if away_col in team_away.columns:
                team_away['feature_val'] = team_away[away_col]
                team_away['location'] = 'Away'

            # Combine and sort
            team_data = pd.concat([
                team_home[['GAME_DATE', 'feature_val', 'location']],
                team_away[['GAME_DATE', 'feature_val', 'location']]
            ]).sort_values('GAME_DATE')

            # Add trace
            team_color = colorPalette.get(team.split()[-1], '#808080')  # Use team nickname for color lookup
            fig.add_trace(go.Scatter(
                x=team_data['GAME_DATE'],
                y=team_data['feature_val'],
                mode='lines+markers',
                name=team,
                line=dict(color=team_color, width=2),
                marker=dict(size=6),
                hovertemplate=f'{team}<br>Date: %{{x}}<br>{feature}: %{{y:.2f}}<extra></extra>'
            ))

        fig.update_layout(
            title=f'{feature} ({window}) Over Season',
            xaxis_title='Date',
            yaxis_title=f'{feature} (Rolling Average)',
            template='minty_dark',
            height=600,
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
            hovermode='x unified'
        )

        return fig

########################################################################################################################
# TAB 5: Correlation Matrix for Winning Margin (TARGET_MARGIN)
########################################################################################################################

if ML_FEATURES_AVAILABLE:
    # Get numeric columns that are features (not identifiers)
    numeric_cols_ml = df_ml.select_dtypes(include=[np.number]).columns.tolist()
    feature_cols_for_corr = [col for col in numeric_cols_ml
                            if any(p in col for p in ['_L5', '_L10', 'STREAK', 'REST', 'WIN_PCT'])]

    correlationFeatureType = html.Div([
        html.Label('Select feature type', htmlFor='correlationFeatureType'),
        dcc.Dropdown(
            options=[
                {'label': 'Differential Features (DIFF_)', 'value': 'DIFF'},
                {'label': 'Home Team Features (HOME_)', 'value': 'HOME'},
                {'label': 'Away Team Features (AWAY_)', 'value': 'AWAY'},
                {'label': 'All Features', 'value': 'ALL'}
            ],
            value='DIFF',
            id='correlationFeatureType',
            className='dbc'
        )
    ])

    topNCorrelation = html.Div([
        html.Label('Show top N features by correlation', htmlFor='topNCorrelation'),
        dcc.Slider(
            id='topNCorrelation',
            min=10,
            max=50,
            step=5,
            value=20,
            marks={i: str(i) for i in range(10, 55, 10)}
        )
    ])

    @dash.callback(
        [
            Output('marginCorrelationBar', 'figure'),
            Output('marginCorrelationHeatmap', 'figure'),
            Output('correlationStats', 'children')
        ],
        [
            Input('correlationFeatureType', 'value'),
            Input('topNCorrelation', 'value')
        ]
    )
    def updateMarginCorrelation(featureType, topN):
        if not ML_FEATURES_AVAILABLE or 'TARGET_MARGIN' not in df_ml.columns:
            empty_fig = go.Figure()
            return empty_fig, empty_fig, "No data available"

        # Filter features by type
        if featureType == 'DIFF':
            features = [col for col in feature_cols_for_corr if col.startswith('DIFF_')]
        elif featureType == 'HOME':
            features = [col for col in feature_cols_for_corr if col.startswith('HOME_')]
        elif featureType == 'AWAY':
            features = [col for col in feature_cols_for_corr if col.startswith('AWAY_')]
        else:
            features = feature_cols_for_corr

        # Calculate correlations with TARGET_MARGIN
        correlations = df_ml[features + ['TARGET_MARGIN']].corr()['TARGET_MARGIN'].drop('TARGET_MARGIN')
        correlations = correlations.dropna().sort_values(key=abs, ascending=False)

        # Get top N
        top_correlations = correlations.head(topN)

        # Bar chart of correlations
        fig_bar = go.Figure()
        colors = ['#FA7851' if v > 0 else '#95DFC9' for v in top_correlations.values]

        fig_bar.add_trace(go.Bar(
            x=top_correlations.values,
            y=top_correlations.index,
            orientation='h',
            marker_color=colors,
            text=[f'{v:.3f}' for v in top_correlations.values],
            textposition='outside'
        ))

        fig_bar.update_layout(
            title=f'Top {topN} Features Correlated with Winning Margin',
            xaxis_title='Pearson Correlation Coefficient',
            yaxis_title='Feature',
            template='minty_dark',
            height=max(400, topN * 25),
            yaxis=dict(autorange='reversed'),
            margin=dict(l=300)
        )

        # Heatmap of top features
        top_feature_names = top_correlations.index.tolist()
        corr_matrix = df_ml[top_feature_names + ['TARGET_MARGIN']].corr()

        fig_heatmap = go.Figure(data=go.Heatmap(
            z=corr_matrix.values,
            x=corr_matrix.columns,
            y=corr_matrix.index,
            colorscale='RdBu_r',
            zmid=0,
            text=np.round(corr_matrix.values, 2),
            texttemplate='%{text}',
            textfont={"size": 8},
            hovertemplate='%{x} vs %{y}<br>Correlation: %{z:.3f}<extra></extra>'
        ))

        fig_heatmap.update_layout(
            title=f'Correlation Matrix: Top {topN} Features + Margin',
            template='minty_dark',
            height=max(600, topN * 20),
            width=max(800, topN * 20),
            xaxis=dict(tickangle=45)
        )

        # Stats summary
        stats_text = f"""
        Feature Analysis Summary:
        - Total features analyzed: {len(features)}
        - Strongest positive correlation: {correlations.idxmax()} ({correlations.max():.3f})
        - Strongest negative correlation: {correlations.idxmin()} ({correlations.min():.3f})
        - Features with |r| > 0.1: {len(correlations[abs(correlations) > 0.1])}
        - Features with |r| > 0.2: {len(correlations[abs(correlations) > 0.2])}
        """

        return fig_bar, fig_heatmap, stats_text

########################################################################################################################
# TAB 6: Game Predictions (Comparing Scikit-learn vs PyTorch)
########################################################################################################################

# Import prediction functions via the generic dispatchers so adding a new model type
# to modeling.model_types.MODEL_TYPES is picked up here automatically with no edits.
try:
    from modeling.predict_games import (
        get_scheduled_games, get_team_rolling_stats, build_matchup_features,
        load_model_by_key, predict_with_loaded_model,
        create_engine as pred_create_engine,
        NBA_API_AVAILABLE, PYTORCH_AVAILABLE, SHAP_AVAILABLE,
        get_top_shap_features, format_feature_impact
    )
    from modeling.model_types import MODEL_TYPES as _MODEL_SPECS
    PREDICTIONS_AVAILABLE = True
except (ImportError, OSError) as e:
    print(f"Warning: Could not import prediction functions: {e}")
    PREDICTIONS_AVAILABLE = False
    NBA_API_AVAILABLE = False
    PYTORCH_AVAILABLE = False
    SHAP_AVAILABLE = False
    _MODEL_SPECS = []

# Pre-load every registered model type. Keys with no loaded model (e.g. nn-embed when its
# bundle hasn't been trained yet, or NN when PyTorch is missing) stay as None and are
# skipped throughout the prediction pipeline.
loaded_models = {spec.key: None for spec in _MODEL_SPECS}

if PREDICTIONS_AVAILABLE:
    try:
        pred_engine = pred_create_engine()
        for spec in _MODEL_SPECS:
            if spec.framework == 'pytorch' and not PYTORCH_AVAILABLE:
                print(f"Skipping {spec.display_name}: PyTorch unavailable")
                continue
            try:
                print(f"Loading {spec.display_name} ({spec.key})...")
                loaded_models[spec.key] = load_model_by_key(spec.key, pred_engine)
                print(f"  {spec.display_name} loaded")
            except Exception as e:
                print(f"  Warning: could not load {spec.key}: {e}")
                loaded_models[spec.key] = None
        pred_engine.dispose()
    except Exception as e:
        print(f"Warning: Could not load prediction models: {e}")
        import traceback
        traceback.print_exc()
        PREDICTIONS_AVAILABLE = False

# ============================================================================
# E5 helper: Vegas line lookup for the margin-chart overlay + comparison plots.
# ============================================================================

def _fetch_vegas_lines_for_games(game_date_str, team_pairs):
    """For a date + list of (home_abbrev, away_abbrev) tuples, return
    {(home_abbrev, away_abbrev): {home_spread, total, bookmaker, source}}.

    Sources in `vegas_lines` may include kaggle_sbr (historical Pinnacle/SBR consensus)
    and espn_draftkings / espn_consensus (current-day). When multiple rows exist for
    the same matchup, we prefer DraftKings > consensus > other.
    """
    if not team_pairs:
        return {}
    try:
        from sqlalchemy import text as _t
        eng = get_engine()
        try:
            rows = []
            with eng.connect() as conn:
                # Pull all candidate rows for this date, then dedupe in Python
                result = conn.execute(_t("""
                    SELECT home_team_abbrev, away_team_abbrev, source, bookmaker,
                           home_spread, total
                    FROM vegas_lines
                    WHERE game_date = :gd
                """), {'gd': game_date_str}).fetchall()
                rows = list(result)
        finally:
            eng.dispose()
    except Exception as e:
        print(f"[vegas] lookup failed: {e}")
        return {}

    # Preferred source order — DK > consensus > kaggle > anything else
    SOURCE_PRIORITY = {'espn_draftkings': 0, 'espn_consensus': 1,
                       'espn_fanduel': 1, 'espn_espnbet': 1,
                       'kaggle_sbr': 2, 'espn_teamrankings': 3}

    by_pair = {}
    for r in rows:
        key = (r[0], r[1])  # (home, away)
        prio = SOURCE_PRIORITY.get(r[2], 99)
        existing = by_pair.get(key)
        if existing is None or prio < existing['_prio']:
            by_pair[key] = {
                '_prio': prio,
                'source': r[2],
                'bookmaker': r[3],
                'home_spread': r[4],
                'total': r[5],
            }

    # Strip the priority field before returning
    return {k: {kk: vv for kk, vv in v.items() if kk != '_prio'} for k, v in by_pair.items()}


# UI Components for Predictions Tab
predictionDatePicker = html.Div([
    html.Label('Select prediction date', htmlFor='predictionDatePicker'),
    dcc.DatePickerSingle(
        id='predictionDatePicker',
        date=datetime.now().strftime('%Y-%m-%d'),
        display_format='YYYY-MM-DD',
        className='dbc'
    )
])

predictionQuickSelect = html.Div([
    html.Label('Quick select', htmlFor='predictionQuickSelect'),
    dbc.ButtonGroup([
        dbc.Button("Today", id='btn-today', color='primary', size='sm'),
        dbc.Button("Tomorrow", id='btn-tomorrow', color='secondary', size='sm'),
    ])
])

predictionRefreshBtn = html.Div([
    dbc.Button("Fetch Games & Predict", id='btn-predict', color='success', size='lg', className='mt-2'),
])

predictionStatus = html.Div(id='predictionStatus', className='mt-2')

# Callback for quick date selection
@dash.callback(
    Output('predictionDatePicker', 'date'),
    [Input('btn-today', 'n_clicks'),
     Input('btn-tomorrow', 'n_clicks')],
    prevent_initial_call=True
)
def quick_select_date(today_clicks, tomorrow_clicks):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update

    button_id = ctx.triggered[0]['prop_id'].split('.')[0]

    if button_id == 'btn-today':
        return datetime.now().strftime('%Y-%m-%d')
    elif button_id == 'btn-tomorrow':
        return (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')

    return dash.no_update

# Main prediction callback - Now generates BOTH RF and NN predictions with SHAP
@dash.callback(
    [Output('predictionStatus', 'children'),
     Output('predictionResultsContainer', 'children'),
     Output('predictionProbChart', 'figure'),
     Output('predictionMarginChart', 'figure'),
     Output('predictionShapContainer', 'children')],
    [Input('btn-predict', 'n_clicks')],
    [dash.State('predictionDatePicker', 'date')],
    prevent_initial_call=True
)
def make_predictions(n_clicks, game_date):
    if not PREDICTIONS_AVAILABLE:
        return (
            dbc.Alert("Prediction system not available. Check console for errors.", color='danger'),
            [],
            go.Figure(),
            go.Figure(),
            []
        )

    if not NBA_API_AVAILABLE:
        return (
            dbc.Alert("NBA API not installed. Run: pip install nba_api", color='warning'),
            [],
            go.Figure(),
            go.Figure(),
            []
        )

    try:
        # Get scheduled games
        games = get_scheduled_games(game_date)

        if len(games) == 0:
            return (
                dbc.Alert(f"No games scheduled for {game_date}", color='info'),
                [],
                go.Figure().add_annotation(text="No games scheduled", showarrow=False),
                go.Figure().add_annotation(text="No games scheduled", showarrow=False),
                []
            )

        # Determine which models are actually loaded and usable for this run
        active_specs = [s for s in _MODEL_SPECS if loaded_models.get(s.key) is not None]
        if not active_specs:
            return (
                dbc.Alert("No models are loaded. Check console for load errors.", color='warning'),
                [], go.Figure(), go.Figure(), [])

        # Per-game prediction loop. predictions_by_key[key] is a list of dicts (one per game),
        # each carrying the standard fields plus the matchup teams. Lists stay aligned by index.
        predictions_by_key = {s.key: [] for s in active_specs}

        engine = pred_create_engine()
        for _, game in games.iterrows():
            home_id = game['HOME_TEAM_ID']
            away_id = game['AWAY_TEAM_ID']
            home_team = game['HOME_TEAM']
            away_team = game['AWAY_TEAM']

            home_features = get_team_rolling_stats(engine, home_id, game_date)
            away_features = get_team_rolling_stats(engine, away_id, game_date)
            if home_features is None or away_features is None:
                continue
            matchup = build_matchup_features(home_features, away_features)

            for spec in active_specs:
                try:
                    result = predict_with_loaded_model(spec.key, loaded_models[spec.key], matchup)
                except Exception as e:
                    print(f"  Warning: {spec.key} prediction failed for {away_team} @ {home_team}: {e}")
                    continue
                predictions_by_key[spec.key].append({
                    'home_team': home_team,
                    'away_team': away_team,
                    'win_prob': result['win_prob'],
                    # E13: isotonic-calibrated classifier probability (RF/XGB). Falls back
                    # to the margin-derived win_prob for models without a calibrated head.
                    'win_prob_calibrated': result.get('win_prob_classifier', result['win_prob']),
                    'margin_mean': result['margin_mean'],
                    'margin_std': result['margin_std'],
                    'margin_samples': result['margin_samples'],
                    # E14: split-conformal prediction intervals [lo, hi] (may be None for
                    # older bundles trained before E14).
                    'margin_interval_80': result.get('margin_interval_80'),
                    'margin_interval_90': result.get('margin_interval_90'),
                    'shap_feature_importance': result.get('shap_feature_importance', {}),
                })
        engine.dispose()

        # Empty-out check: if no model produced any predictions, bail
        if not any(predictions_by_key.values()):
            return (
                dbc.Alert("Could not generate predictions (missing team data)", color='warning'),
                [], go.Figure(), go.Figure(), [])

        # ---------- Comparison table (one column group per active model) ----------
        # Reference the longest prediction list as the matchup spine so we don't drop rows
        # when one model failed on a particular game.
        spine_key = max(active_specs, key=lambda s: len(predictions_by_key[s.key])).key
        n_games = len(predictions_by_key[spine_key])

        def _pred_for(spec_key, idx):
            preds = predictions_by_key.get(spec_key, [])
            return preds[idx] if idx < len(preds) else None

        def _pick(pred):
            if pred is None: return None
            # Pick + Win% use the E13 isotonic-calibrated probability (the validated one).
            return pred['home_team'] if pred['win_prob_calibrated'] > 0.5 else pred['away_team']

        # Header rows: top row spans column groups, bottom row labels per-model cells
        header_top = [html.Th("Matchup", rowSpan=2, style={'verticalAlign': 'middle'})]
        header_bot = []
        for spec in active_specs:
            bg_top = f'rgba({int(spec.color[1:3], 16)}, {int(spec.color[3:5], 16)}, {int(spec.color[5:7], 16)}, 0.3)'
            bg_bot = f'rgba({int(spec.color[1:3], 16)}, {int(spec.color[3:5], 16)}, {int(spec.color[5:7], 16)}, 0.2)'
            header_top.append(html.Th(spec.display_name, colSpan=3,
                                      style={'textAlign': 'center', 'backgroundColor': bg_top}))
            header_bot += [
                html.Th("Pick", style={'backgroundColor': bg_bot}),
                html.Th("Win%", style={'backgroundColor': bg_bot}),
                html.Th("Margin", style={'backgroundColor': bg_bot}),
            ]
        header_top.append(html.Th("Agreement", rowSpan=2, style={'verticalAlign': 'middle'}))

        table_rows = []
        for i in range(n_games):
            row_preds = {spec.key: _pred_for(spec.key, i) for spec in active_specs}
            spine = row_preds[spine_key]
            if spine is None:
                continue
            matchup_label = f"{spine['away_team']} @ {spine['home_team']}"
            picks = [_pick(p) for p in row_preds.values() if p is not None]

            # Agreement badge: AGREE if all non-null models pick the same team, else show majority split
            if len(set(picks)) <= 1:
                agree_badge = dbc.Badge("AGREE", color="success")
            else:
                # Show the split as "majority X / minority Y"
                from collections import Counter
                cnt = Counter(picks)
                top = cnt.most_common()
                if len(top) == 2 and top[0][1] == top[1][1]:
                    agree_badge = dbc.Badge("SPLIT", color="warning")
                else:
                    agree_badge = dbc.Badge(f"MAJORITY {top[0][0]}", color="danger")

            cells = [html.Td(matchup_label)]
            for spec in active_specs:
                p = row_preds[spec.key]
                if p is None:
                    cells += [html.Td('-'), html.Td('-'), html.Td('-')]
                else:
                    # Margin cell shows the point estimate + the conformal 80% interval
                    # (E14) when available, e.g. "+4.6 (80%: -14..+23)".
                    iv80 = p.get('margin_interval_80')
                    if iv80:
                        margin_txt = f"{p['margin_mean']:+.1f}  (80%: {iv80[0]:+.0f}..{iv80[1]:+.0f})"
                    else:
                        margin_txt = f"{p['margin_mean']:+.1f}"
                    cells += [
                        html.Td(_pick(p), style={'fontWeight': 'bold', 'color': spec.color}),
                        html.Td(f"{p['win_prob_calibrated']:.1%}"),
                        html.Td(margin_txt),
                    ]
            cells.append(html.Td(agree_badge))
            table_rows.append(html.Tr(cells))

        results_table = dbc.Table([
            html.Thead([html.Tr(header_top), html.Tr(header_bot)]),
            html.Tbody(table_rows)
        ], bordered=True, hover=True, responsive=True, striped=True, className='mt-3')

        # ---------- Probability chart (one bar trace per model, grouped by matchup) ----------
        matchups = [f"{predictions_by_key[spine_key][i]['away_team']} @ {predictions_by_key[spine_key][i]['home_team']}"
                    for i in range(n_games)]
        fig_prob = go.Figure()
        for offset, spec in enumerate(active_specs):
            preds = predictions_by_key[spec.key]
            xs = [(_pred_for(spec.key, i) or {}).get('win_prob_calibrated') for i in range(n_games)]
            raws = [(_pred_for(spec.key, i) or {}).get('win_prob') for i in range(n_games)]
            labels = [f"{spec.key.upper()}: {x:.1%}" if x is not None else "" for x in xs]
            # Hover shows both the calibrated (displayed) and the raw margin-derived prob.
            customdata = [[(r if r is not None else float('nan'))] for r in raws]
            fig_prob.add_trace(go.Bar(
                name=spec.display_name,
                x=xs, y=matchups,
                orientation='h',
                marker_color=spec.color,
                text=labels,
                textposition='inside',
                offsetgroup=offset,
                customdata=customdata,
                hovertemplate='%{y}<br>Calibrated P(home win): %{x:.1%}'
                              '<br>Raw (margin-derived): %{customdata[0]:.1%}<extra></extra>',
            ))
        fig_prob.update_layout(
            title=f'Win Probability — isotonic-calibrated (E13) ({", ".join(s.display_name for s in active_specs)}) — {game_date}',
            barmode='group',
            xaxis_title='Home Team Win Probability',
            xaxis=dict(tickformat='.0%', range=[0, 1]),
            yaxis_title='',
            template='minty_dark',
            height=max(400, n_games * 60 * max(1, len(active_specs) // 2 + 1)),
            margin=dict(l=150),
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
        )
        fig_prob.add_vline(x=0.5, line_dash="dash", line_color="white", opacity=0.5,
                          annotation_text="50%", annotation_position="top")

        # ---------- Margin distribution chart (one violin per (model, matchup)) ----------
        # E5: Also overlay the Vegas spread per matchup as a gold marker, so users can
        # see at a glance whether our model agrees with the line. Vegas data comes from
        # vegas_lines table (populated by ESPN fetcher for current games + Kaggle for historical).
        vegas_lookup = _fetch_vegas_lines_for_games(
            game_date,
            [(predictions_by_key[spine_key][i]['home_team'],
              predictions_by_key[spine_key][i]['away_team']) for i in range(n_games)]
        )

        fig_margin = go.Figure()
        vegas_legend_added = False
        for i in range(n_games):
            spine_pred = predictions_by_key[spine_key][i]
            matchup_label = f"{spine_pred['away_team']} @ {spine_pred['home_team']}"
            for spec in active_specs:
                p = _pred_for(spec.key, i)
                if p is None or len(p.get('margin_samples', [])) == 0:
                    continue
                rgba_fill = f'rgba({int(spec.color[1:3], 16)}, {int(spec.color[3:5], 16)}, {int(spec.color[5:7], 16)}, 0.5)'
                fig_margin.add_trace(go.Violin(
                    y=[matchup_label] * len(p['margin_samples']),
                    x=p['margin_samples'],
                    name=f"{spec.key.upper()}: {matchup_label}",
                    orientation='h',
                    side='positive',
                    meanline_visible=True,
                    box_visible=True,
                    points=False,
                    showlegend=(i == 0),
                    legendgroup=spec.key,
                    fillcolor=rgba_fill,
                    line_color=spec.color,
                ))
                # E14: split-conformal prediction intervals, drawn ON the category baseline
                # (below the side='positive' violin). Thick bar = 80% (validated ~75-78%
                # coverage), dotted line = 90% (~91%). The violin shows the model's *internal*
                # spread; the conformal bar shows *total* predictive uncertainty incl. the
                # irreducible game variance — and is the honest range for XGB (whose violin is
                # a degenerate spike).
                iv90 = p.get('margin_interval_90')
                iv80 = p.get('margin_interval_80')
                if iv90:
                    fig_margin.add_trace(go.Scatter(
                        x=iv90, y=[matchup_label, matchup_label], mode='lines',
                        line=dict(color=spec.color, width=1.5, dash='dot'),
                        showlegend=(i == 0), legendgroup=f'{spec.key}_ci',
                        name=f"{spec.key.upper()} 90% interval",
                        hovertemplate=f"{spec.key.upper()} 90 pct interval: "
                                      f"{iv90[0]:+.0f} .. {iv90[1]:+.0f}<extra></extra>",
                    ))
                if iv80:
                    fig_margin.add_trace(go.Scatter(
                        x=iv80, y=[matchup_label, matchup_label], mode='lines',
                        line=dict(color=spec.color, width=6), opacity=0.65,
                        showlegend=False, legendgroup=f'{spec.key}_ci',
                        name=f"{spec.key.upper()} 80% interval",
                        hovertemplate=f"{spec.key.upper()} 80 pct interval: "
                                      f"{iv80[0]:+.0f} .. {iv80[1]:+.0f}<extra></extra>",
                    ))
            # Vegas marker: ESPN uses convention "spread of -7.5 from the favored team's perspective"
            # — vegas_lines.home_spread is already home-perspective (negative = home favored). To
            # overlay on a "+ = home wins" margin axis, we want the MARGIN value Vegas predicts:
            # margin = -home_spread (so home_spread=-7.5 means Vegas predicts home wins by 7.5).
            vegas = vegas_lookup.get((spine_pred['home_team'], spine_pred['away_team']))
            if vegas is not None and vegas.get('home_spread') is not None:
                vegas_margin = -vegas['home_spread']
                bookmaker = vegas.get('bookmaker', 'Vegas')
                fig_margin.add_trace(go.Scatter(
                    x=[vegas_margin], y=[matchup_label],
                    mode='markers+text',
                    marker=dict(symbol='diamond-tall', size=18,
                                color='gold', line=dict(width=2, color='black')),
                    text=[f' Vegas {vegas_margin:+.1f}'],
                    textposition='middle right',
                    textfont=dict(color='gold', size=11),
                    name=f'Vegas line ({bookmaker})',
                    showlegend=not vegas_legend_added,
                    legendgroup='vegas',
                    hovertemplate=f'<b>Vegas ({bookmaker})</b><br>'
                                  f'Spread (home perspective): {vegas["home_spread"]:+.1f}<br>'
                                  f'Implied margin: {vegas_margin:+.1f}<extra></extra>',
                ))
                vegas_legend_added = True
        fig_margin.update_layout(
            title=f'Margin: model distribution + conformal interval + Vegas line — {game_date}',
            xaxis_title='Point Margin (+ = Home Team Wins)',
            yaxis_title='',
            template='minty_dark',
            height=max(400, n_games * 100),
            margin=dict(l=150, b=90),
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
        )
        fig_margin.add_vline(x=0, line_dash="dash", line_color="yellow", opacity=0.7,
                            annotation_text="Even", annotation_position="top")
        # Caption: explain the interval semantics + the honest coverage caveat (E14).
        fig_margin.add_annotation(
            xref='paper', yref='paper', x=0, y=-0.14, showarrow=False, align='left',
            font=dict(size=10, color='lightgray'),
            text=("Thick bar = 80% prediction interval, dotted = 90% (split-conformal, E14). "
                  "Validated coverage on held-out games: ~91% of margins land inside the 90% band. "
                  "Bands are wide (±18-25 pts) because NBA margin variance is irreducibly large."),
        )

        # ---------- SHAP cards (one column per active model, per game) ----------
        shap_components = []
        if SHAP_AVAILABLE:
            col_width = max(2, 12 // max(1, len(active_specs)))  # divide row across active models
            for i in range(n_games):
                spine_pred = predictions_by_key[spine_key][i]
                matchup_label = f"{spine_pred['away_team']} @ {spine_pred['home_team']}"

                shap_cols = []
                any_shap_present = False
                for spec in active_specs:
                    p = _pred_for(spec.key, i)
                    shap_dict = (p or {}).get('shap_feature_importance', {})
                    if not shap_dict:
                        shap_cols.append(dbc.Col(html.Div(f"{spec.display_name}: SHAP unavailable",
                                                          style={'opacity': 0.6}), width=col_width))
                        continue
                    top = get_top_shap_features(shap_dict, top_n=10)
                    if not top:
                        shap_cols.append(dbc.Col(html.Div(f"{spec.display_name}: no SHAP features",
                                                          style={'opacity': 0.6}), width=col_width))
                        continue
                    any_shap_present = True
                    fnames = [f.replace('DIFF_', '').replace('HOME_', 'H_').replace('AWAY_', 'A_')[:20]
                              for f, _, _ in top]
                    svals = [v for _, v, _ in top]
                    bar_colors = ['#2ecc71' if v > 0 else '#e74c3c' for v in svals]
                    fig_shap = go.Figure()
                    fig_shap.add_trace(go.Bar(
                        x=svals, y=fnames, orientation='h',
                        marker_color=bar_colors,
                        text=[f'{v:+.2f}' for v in svals], textposition='outside',
                        name=spec.display_name,
                    ))
                    fig_shap.update_layout(
                        title=f'{spec.display_name}: Top Features — {matchup_label}',
                        xaxis_title='SHAP Value (Impact on Point Margin)',
                        yaxis_title='',
                        template='minty_dark', height=400,
                        yaxis=dict(autorange='reversed'),
                        margin=dict(l=150),
                    )
                    fig_shap.add_vline(x=0, line_dash="dash", line_color="white", opacity=0.5)
                    shap_cols.append(dbc.Col(dcc.Graph(figure=fig_shap), width=col_width))

                if any_shap_present:
                    shap_components.append(dbc.Card([
                        dbc.CardHeader(f"Feature Importance: {matchup_label}", style={'fontWeight': 'bold'}),
                        dbc.CardBody([
                            dbc.Row(shap_cols),
                            html.Hr(),
                            html.Div([
                                html.P([
                                    html.Strong("How to read: "),
                                    html.Span("Green bars = helps home team win. Red bars = helps away team win. ",
                                              style={'color': '#95DFC9'}),
                                    html.Span("Longer bars = stronger impact on the prediction.",
                                              style={'color': '#FA7851'}),
                                ]),
                                html.P([
                                    html.Strong("Example: "),
                                    "If 'DIFF_netRating_L10' is +2.5 (green), the home team's better net rating "
                                    "over last 10 games adds ~2.5 points to the predicted margin."
                                ]),
                            ], style={'fontSize': '12px', 'backgroundColor': 'rgba(255,255,255,0.05)',
                                       'padding': '10px', 'borderRadius': '5px'})
                        ])
                    ], className='mb-3'))

        # Status message
        loaded_summary = ", ".join(s.display_name for s in active_specs)
        shap_status = " with SHAP explanations" if SHAP_AVAILABLE else ""
        status = dbc.Alert(
            f"Generated {loaded_summary} predictions{shap_status} for {n_games} games on {game_date}",
            color='success'
        )

        return status, results_table, fig_prob, fig_margin, shap_components

    except Exception as e:
        import traceback
        error_msg = f"Error: {str(e)}\n{traceback.format_exc()}"
        return (
            dbc.Alert(f"Error generating predictions: {str(e)}", color='danger'),
            html.Pre(error_msg, style={'fontSize': '10px', 'maxHeight': '200px', 'overflow': 'auto'}),
            go.Figure(),
            go.Figure(),
            []
        )

#######################################################################################################################
# TAB 7: Model Performance
#
# Combines training-time metrics (from model_registry) with live prediction
# performance (from model_predictions, backfilled with actual results) so we can
# see how each model is actually doing in the wild vs how it claimed to do at
# training time.
#######################################################################################################################

from sqlalchemy import text as _sql_text


def _load_registry_df(engine):
    """Load model_registry rows for the training-metrics view.

    Pulls the extended schema (training window, hyperparameters, train-set metrics,
    notes, run_kind). hyperparameters/train_metrics arrive as JSON strings and are
    flattened to short summary strings in `_format_registry_for_display`.
    """
    try:
        return pd.read_sql(_sql_text(
            "SELECT registry_id, run_kind, model_type, model_version, training_date, "
            "train_start_date, train_end_date, test_start_date, test_end_date, "
            "feature_count, training_samples, test_samples, "
            "test_accuracy, test_auc, test_mae, test_rmse, test_r2, "
            "hyperparameters, train_metrics, notes, is_current "
            "FROM model_registry ORDER BY training_date DESC, registry_id DESC"
        ), engine)
    except Exception as e:
        print(f"[model_perf] registry load failed: {e}")
        return pd.DataFrame()


def _summarize_json_field(v):
    """Render a JSON column as compact 'k=v, k=v' (or '' if missing)."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ''
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except Exception:
            return v[:80]
    if isinstance(v, dict):
        parts = []
        for k, val in v.items():
            if isinstance(val, float):
                parts.append(f"{k}={val:.3g}")
            else:
                parts.append(f"{k}={val}")
        return ', '.join(parts)[:120]
    return str(v)[:80]


def _format_registry_for_display(df):
    """Cosmetic prep of the registry DataFrame for the dash_table."""
    out = df.copy()
    for col in ('test_accuracy', 'test_auc', 'test_mae', 'test_rmse', 'test_r2'):
        if col in out.columns:
            out[col] = out[col].round(3)
    # Compact hyperparameter / train_metrics renderings
    if 'hyperparameters' in out.columns:
        out['hyperparameters'] = out['hyperparameters'].apply(_summarize_json_field)
    if 'train_metrics' in out.columns:
        out['train_metrics'] = out['train_metrics'].apply(_summarize_json_field)
    # Collapse the four date columns into two readable windows so the table is narrower
    if 'train_start_date' in out.columns:
        out['train_window'] = out.apply(
            lambda r: f"{r['train_start_date']} → {r['train_end_date']}"
            if r['train_start_date'] and r['train_end_date'] else '', axis=1)
    if 'test_start_date' in out.columns:
        out['test_window'] = out.apply(
            lambda r: f"{r['test_start_date']} → {r['test_end_date']}"
            if r['test_start_date'] and r['test_end_date'] else '', axis=1)
    out = out.drop(columns=[c for c in
                            ('train_start_date', 'train_end_date', 'test_start_date', 'test_end_date')
                            if c in out.columns])
    # Preferred column order
    preferred = ['registry_id', 'run_kind', 'model_type', 'model_version', 'training_date',
                 'is_current', 'feature_count', 'training_samples', 'test_samples',
                 'train_window', 'test_window',
                 'test_accuracy', 'test_auc', 'test_mae', 'test_rmse', 'test_r2',
                 'train_metrics', 'hyperparameters', 'notes']
    out = out[[c for c in preferred if c in out.columns] +
              [c for c in out.columns if c not in preferred]]
    return out


def _load_predictions_df(engine, start_date, end_date):
    """Load backfilled predictions in the date range (only rows where actuals are filled)."""
    try:
        df = pd.read_sql(_sql_text(
            "SELECT game_date, model_type, model_version, home_team, away_team, "
            "predicted_winner, predicted_margin, home_win_probability, "
            "actual_winner, actual_margin, is_correct, margin_error "
            "FROM model_predictions "
            "WHERE actual_winner IS NOT NULL "
            "  AND game_date BETWEEN :start AND :end "
            "ORDER BY game_date ASC"
        ), engine, params={'start': start_date, 'end': end_date})
        if len(df):
            df['game_date'] = pd.to_datetime(df['game_date'])
            df['is_correct'] = df['is_correct'].astype(int)
        return df
    except Exception as e:
        print(f"[model_perf] predictions load failed: {e}")
        return pd.DataFrame()


def _summary_metrics(df):
    """Per-model summary: count, accuracy, MAE, mean Brier-like calibration error."""
    rows = []
    for model_type, sub in df.groupby('model_type'):
        actual_home_win = (sub['actual_winner'] == sub['home_team']).astype(int)
        rows.append({
            'model_type': model_type,
            'n': len(sub),
            'accuracy': sub['is_correct'].mean(),
            'mae': sub['margin_error'].mean(),
            'rmse': float(np.sqrt((sub['margin_error'] ** 2).mean())),
            'calibration_error': float(np.mean(np.abs(sub['home_win_probability'] - actual_home_win))),
        })
    return pd.DataFrame(rows)


def _reliability_bins(df, n_bins=10):
    """Bin predicted home-win-probability into deciles; return per-bin actual rate + count."""
    if df.empty:
        return pd.DataFrame(columns=['bin_center', 'predicted', 'actual', 'count'])
    sub = df.copy()
    sub['actual_home_win'] = (sub['actual_winner'] == sub['home_team']).astype(int)
    edges = np.linspace(0, 1, n_bins + 1)
    sub['bin'] = pd.cut(sub['home_win_probability'], bins=edges, include_lowest=True)
    grouped = sub.groupby('bin', observed=True).agg(
        predicted=('home_win_probability', 'mean'),
        actual=('actual_home_win', 'mean'),
        count=('actual_home_win', 'size')
    ).reset_index(drop=True)
    grouped['bin_center'] = [(edges[i] + edges[i + 1]) / 2 for i in range(len(grouped))]
    return grouped


# Pull the color map from the central MODEL_TYPES registry so adding a new model type
# (xgb, lightgbm, ensemble, ...) automatically gets a chart color here without edits.
try:
    from modeling.model_types import color_map as _model_color_map
    _MODEL_COLOR = _model_color_map()
except ImportError:
    _MODEL_COLOR = {'rf': '#3498db', 'nn': '#e74c3c'}


def _engine_for_queries():
    """Build a fresh engine for callback queries — avoids reusing the module-level
    `conn` which may be stale across requests in long-running Dash sessions."""
    return get_engine()


modelPerfDateRange = html.Div([
    dbc.Label('Date range'),
    dcc.DatePickerRange(
        id='modelPerfDateRange',
        display_format='YYYY-MM-DD',
        start_date_placeholder_text='Start',
        end_date_placeholder_text='End',
    ),
])

modelPerfModelToggle = html.Div([
    dbc.Label('Models'),
    dcc.Checklist(
        id='modelPerfModelToggle',
        options=[
            {'label': ' Random Forest (rf)', 'value': 'rf'},
            {'label': ' Neural Network (nn)', 'value': 'nn'},
        ],
        value=['rf', 'nn'],
        inline=True,
        inputStyle={'marginRight': '6px', 'marginLeft': '12px'},
    ),
])

modelPerfRefreshBtn = html.Div([
    dbc.Label(' '),  # vertical alignment with sibling cols
    html.Br(),
    dbc.Button('Refresh', id='modelPerfRefreshBtn', n_clicks=0, color='primary', size='sm'),
])


@app.callback(
    [
        Output('modelPerfDateRange', 'start_date'),
        Output('modelPerfDateRange', 'end_date'),
        Output('modelPerfDateRange', 'min_date_allowed'),
        Output('modelPerfDateRange', 'max_date_allowed'),
    ],
    [Input('modelPerfRefreshBtn', 'n_clicks')],
)
def init_model_perf_date_range(_n):
    """On first load (and on Refresh), default the picker to the full backfilled range."""
    eng = _engine_for_queries()
    try:
        bounds = pd.read_sql(_sql_text(
            "SELECT MIN(game_date) as min_d, MAX(game_date) as max_d "
            "FROM model_predictions WHERE actual_winner IS NOT NULL"
        ), eng)
    finally:
        eng.dispose()
    if bounds.empty or pd.isna(bounds.iloc[0]['min_d']):
        today = date.today()
        return today.isoformat(), today.isoformat(), today.isoformat(), today.isoformat()
    min_d = pd.to_datetime(bounds.iloc[0]['min_d']).date().isoformat()
    max_d = pd.to_datetime(bounds.iloc[0]['max_d']).date().isoformat()
    return min_d, max_d, min_d, max_d


@app.callback(
    [
        Output('modelPerfHeadline', 'children'),
        Output('modelPerfRegistryTable', 'children'),
        Output('modelPerfRollingChart', 'figure'),
        Output('modelPerfReliabilityChart', 'figure'),
        Output('modelPerfResidualChart', 'figure'),
        Output('modelPerfErrorHistChart', 'figure'),
        Output('modelPerfRocChart', 'figure'),
        Output('modelPerfConfusionChart', 'figure'),
        Output('modelPerfVegasChart', 'figure'),
        Output('modelPerfStatus', 'children'),
    ],
    [
        Input('modelPerfDateRange', 'start_date'),
        Input('modelPerfDateRange', 'end_date'),
        Input('modelPerfModelToggle', 'value'),
        Input('modelPerfRefreshBtn', 'n_clicks'),
    ],
)
def update_model_perf(start_date, end_date, models_selected, _n_clicks):
    eng = _engine_for_queries()
    try:
        if not start_date or not end_date:
            empty_fig = go.Figure().update_layout(template='plotly_dark', title='No data')
            return (html.Div('Pick a date range to begin.'), html.Div(),
                    empty_fig, empty_fig, empty_fig, empty_fig, empty_fig, empty_fig, empty_fig,
                    dbc.Alert('Waiting for date range', color='secondary'))

        registry_df = _load_registry_df(eng)
        preds_df = _load_predictions_df(eng, start_date, end_date)

        if models_selected:
            preds_df = preds_df[preds_df['model_type'].isin(models_selected)]

        # ---------------- Headline cards ----------------
        if preds_df.empty:
            headline = dbc.Alert(
                f'No backfilled predictions in {start_date} to {end_date}. '
                f'Run `python prediction_tracker.py --backfill --lookback 200` to populate.',
                color='warning'
            )
        else:
            summary = _summary_metrics(preds_df)
            cards = []
            for _, row in summary.iterrows():
                color = _MODEL_COLOR.get(row['model_type'], '#888')
                cards.append(dbc.Col(dbc.Card([
                    dbc.CardHeader(row['model_type'].upper(),
                                   style={'backgroundColor': color, 'color': 'white', 'fontWeight': 'bold'}),
                    dbc.CardBody([
                        html.Div([html.Strong('Games: '), f"{int(row['n'])}"]),
                        html.Div([html.Strong('Accuracy: '), f"{row['accuracy'] * 100:.1f}%"]),
                        html.Div([html.Strong('MAE: '), f"{row['mae']:.2f} pts"]),
                        html.Div([html.Strong('RMSE: '), f"{row['rmse']:.2f} pts"]),
                        html.Div([html.Strong('Calibration error: '), f"{row['calibration_error']:.3f}"]),
                    ])
                ]), width=6))
            headline = dbc.Row(cards)

        # ---------------- Registry table ----------------
        if registry_df.empty:
            registry_table = dbc.Alert('model_registry is empty.', color='secondary')
        else:
            registry_display = _format_registry_for_display(registry_df)
            registry_table = dash_table.DataTable(
                data=registry_display.to_dict('records'),
                columns=[{'name': c, 'id': c} for c in registry_display.columns],
                style_table={'overflowX': 'auto'},
                style_cell={'textAlign': 'left', 'padding': '6px', 'fontSize': '12px',
                            'maxWidth': '260px', 'whiteSpace': 'normal',
                            'overflow': 'hidden', 'textOverflow': 'ellipsis'},
                style_header={'fontWeight': 'bold', 'backgroundColor': '#222', 'color': 'white'},
                style_data_conditional=[
                    {'if': {'filter_query': '{is_current} = 1'}, 'backgroundColor': '#1f3a5f', 'color': 'white'},
                    {'if': {'filter_query': '{run_kind} = "validation"'}, 'fontStyle': 'italic', 'opacity': 0.9},
                ],
                tooltip_data=[
                    {col: {'value': str(row[col]) if row.get(col) is not None else '', 'type': 'markdown'}
                     for col in registry_display.columns}
                    for row in registry_display.to_dict('records')
                ],
                tooltip_duration=None,
                page_size=15,
                sort_action='native',
                filter_action='native',
            )

        # ---------------- Rolling accuracy & MAE ----------------
        rolling_fig = make_subplots(
            rows=2, cols=1, shared_xaxes=True,
            subplot_titles=('Rolling accuracy (10-game window)', 'Rolling MAE (10-game window)'),
            vertical_spacing=0.12,
        )
        if not preds_df.empty:
            for mt, sub in preds_df.groupby('model_type'):
                sub = sub.sort_values('game_date').reset_index(drop=True)
                sub['rolling_acc'] = sub['is_correct'].rolling(10, min_periods=3).mean()
                sub['rolling_mae'] = sub['margin_error'].rolling(10, min_periods=3).mean()
                color = _MODEL_COLOR.get(mt, '#888')
                rolling_fig.add_trace(
                    go.Scatter(x=sub['game_date'], y=sub['rolling_acc'], name=f'{mt.upper()} acc',
                               line=dict(color=color)),
                    row=1, col=1
                )
                rolling_fig.add_trace(
                    go.Scatter(x=sub['game_date'], y=sub['rolling_mae'], name=f'{mt.upper()} MAE',
                               line=dict(color=color, dash='dot'), showlegend=False),
                    row=2, col=1
                )
            rolling_fig.add_hline(y=0.5, line_dash='dash', line_color='gray', row=1, col=1,
                                  annotation_text='coin flip', annotation_position='right')
        rolling_fig.update_layout(template='plotly_dark', height=480, hovermode='x unified',
                                  margin=dict(l=40, r=20, t=40, b=40))
        rolling_fig.update_yaxes(title_text='Accuracy', row=1, col=1, range=[0, 1])
        rolling_fig.update_yaxes(title_text='MAE (pts)', row=2, col=1)

        # ---------------- Reliability diagram ----------------
        rel_fig = go.Figure()
        rel_fig.add_trace(go.Scatter(
            x=[0, 1], y=[0, 1], mode='lines',
            line=dict(color='gray', dash='dash'), name='Perfect calibration',
            hoverinfo='skip',
        ))
        if not preds_df.empty:
            for mt, sub in preds_df.groupby('model_type'):
                bins = _reliability_bins(sub, n_bins=10)
                bins = bins.dropna(subset=['predicted', 'actual'])
                if bins.empty:
                    continue
                color = _MODEL_COLOR.get(mt, '#888')
                rel_fig.add_trace(go.Scatter(
                    x=bins['predicted'], y=bins['actual'],
                    mode='lines+markers',
                    name=mt.upper(),
                    marker=dict(size=8 + bins['count'].clip(0, 40) / 4, color=color),
                    line=dict(color=color),
                    customdata=np.stack([bins['count']], axis=-1),
                    hovertemplate='Predicted: %{x:.2f}<br>Actual: %{y:.2f}<br>n=%{customdata[0]}<extra></extra>',
                ))
        rel_fig.update_layout(
            template='plotly_dark',
            title='Reliability diagram (predicted home-win-prob vs actual rate)',
            xaxis=dict(title='Predicted P(home win)', range=[0, 1]),
            yaxis=dict(title='Actual home-win rate', range=[0, 1]),
            height=420, margin=dict(l=40, r=20, t=50, b=40),
        )

        # ---------------- Residual plot ----------------
        resid_fig = go.Figure()
        if not preds_df.empty:
            for mt, sub in preds_df.groupby('model_type'):
                color = _MODEL_COLOR.get(mt, '#888')
                resid = sub['actual_margin'] - sub['predicted_margin']
                resid_fig.add_trace(go.Scatter(
                    x=sub['predicted_margin'], y=resid,
                    mode='markers', name=mt.upper(),
                    marker=dict(color=color, opacity=0.6, size=6),
                    hovertemplate='Predicted: %{x:.1f}<br>Residual: %{y:.1f}<extra></extra>',
                ))
        resid_fig.add_hline(y=0, line_dash='dash', line_color='gray')
        resid_fig.update_layout(
            template='plotly_dark',
            title='Residuals: actual margin - predicted margin (closer to 0 = better)',
            xaxis_title='Predicted margin (pts)', yaxis_title='Residual (pts)',
            height=420, margin=dict(l=40, r=20, t=50, b=40),
        )

        # ---------------- Margin error histogram ----------------
        hist_fig = go.Figure()
        if not preds_df.empty:
            for mt, sub in preds_df.groupby('model_type'):
                color = _MODEL_COLOR.get(mt, '#888')
                hist_fig.add_trace(go.Histogram(
                    x=sub['margin_error'], name=mt.upper(),
                    marker=dict(color=color), opacity=0.6, nbinsx=25,
                ))
        hist_fig.update_layout(
            template='plotly_dark',
            title='Distribution of |actual - predicted| margin',
            xaxis_title='Absolute margin error (pts)', yaxis_title='Count',
            barmode='overlay',
            height=380, margin=dict(l=40, r=20, t=50, b=40),
        )

        # ---------------- ROC curves ----------------
        # One curve per model — shows the full threshold sweep. The closer to the
        # top-left corner, the better; the diagonal is the random baseline.
        roc_fig = go.Figure()
        roc_fig.add_trace(go.Scatter(
            x=[0, 1], y=[0, 1], mode='lines',
            line=dict(color='gray', dash='dash'),
            name='Random (AUC=0.5)', hoverinfo='skip',
        ))
        if not preds_df.empty:
            try:
                from sklearn.metrics import roc_curve as _roc_curve, auc as _sk_auc
                for mt, sub in preds_df.groupby('model_type'):
                    sub2 = sub.copy()
                    sub2['actual_home_win'] = (sub2['actual_winner'] == sub2['home_team']).astype(int)
                    if sub2['actual_home_win'].nunique() < 2:
                        continue
                    fpr, tpr, _ = _roc_curve(sub2['actual_home_win'], sub2['home_win_probability'])
                    auc_val = _sk_auc(fpr, tpr)
                    color = _MODEL_COLOR.get(mt, '#888')
                    roc_fig.add_trace(go.Scatter(
                        x=fpr, y=tpr, mode='lines',
                        line=dict(color=color, width=2),
                        name=f'{mt.upper()} (AUC={auc_val:.3f})',
                        hovertemplate='FPR=%{x:.2f}<br>TPR=%{y:.2f}<extra></extra>',
                    ))
            except Exception as e:
                print(f"[model_perf] ROC failed: {e}")
        roc_fig.update_layout(
            template='plotly_dark',
            title='ROC curves — true-positive rate vs false-positive rate (closer to top-left = better ranking)',
            xaxis=dict(title='False positive rate', range=[0, 1], tickformat='.0%'),
            yaxis=dict(title='True positive rate', range=[0, 1], tickformat='.0%'),
            height=420, margin=dict(l=40, r=20, t=50, b=40),
            legend=dict(x=0.6, y=0.1),
        )

        # ---------------- Confusion matrices ----------------
        # One 2x2 heatmap per model side-by-side. Each cell shows count + percentage.
        # Rows = actual, columns = predicted, so the diagonal is correct predictions.
        from plotly.subplots import make_subplots as _make_subplots
        if preds_df.empty:
            cm_fig = go.Figure().update_layout(template='plotly_dark', title='No data')
        else:
            model_types_in_data = sorted(preds_df['model_type'].unique())
            n_models = len(model_types_in_data)
            cm_fig = _make_subplots(rows=1, cols=max(1, n_models),
                                     subplot_titles=[mt.upper() for mt in model_types_in_data],
                                     horizontal_spacing=0.15)
            for i, mt in enumerate(model_types_in_data):
                sub = preds_df[preds_df['model_type'] == mt].copy()
                actual_home_win = (sub['actual_winner'] == sub['home_team']).astype(int)
                pred_home_win = (sub['home_win_probability'] >= 0.5).astype(int)
                # Confusion matrix: actual rows, predicted cols. [actual=0, pred=0], [actual=0, pred=1], etc.
                tn = int(((actual_home_win == 0) & (pred_home_win == 0)).sum())
                fp = int(((actual_home_win == 0) & (pred_home_win == 1)).sum())
                fn = int(((actual_home_win == 1) & (pred_home_win == 0)).sum())
                tp = int(((actual_home_win == 1) & (pred_home_win == 1)).sum())
                total = tn + fp + fn + tp
                z = [[tn, fp], [fn, tp]]
                text = [
                    [f'TN<br>{tn}<br>({tn/total:.1%})' if total else 'TN<br>0',
                     f'FP<br>{fp}<br>({fp/total:.1%})' if total else 'FP<br>0'],
                    [f'FN<br>{fn}<br>({fn/total:.1%})' if total else 'FN<br>0',
                     f'TP<br>{tp}<br>({tp/total:.1%})' if total else 'TP<br>0'],
                ]
                color = _MODEL_COLOR.get(mt, '#888')
                cm_fig.add_trace(go.Heatmap(
                    z=z,
                    x=['Pred: away wins', 'Pred: home wins'],
                    y=['Actual: away wins', 'Actual: home wins'],
                    text=text, texttemplate='%{text}',
                    colorscale=[[0, 'rgba(40,40,40,0.3)'], [1, color]],
                    showscale=False,
                    hovertemplate='%{y}<br>%{x}<br>Count: %{z}<extra></extra>',
                ), row=1, col=i + 1)
            cm_fig.update_layout(
                template='plotly_dark',
                title='Confusion matrix — diagonal = correct, off-diagonal = mistakes',
                height=380, margin=dict(l=40, r=20, t=70, b=40),
            )
            # Tighten axis labels
            for k in range(1, n_models + 1):
                cm_fig.update_yaxes(autorange='reversed', row=1, col=k)

        # ---------------- E5: Model vs Vegas vs Actual (margin MAE comparison) ----------------
        # For every backfilled prediction in the window that has a matched vegas_lines row,
        # compute |model_predicted_margin - actual_margin| and |vegas_implied_margin - actual_margin|.
        # Show the per-model MAE alongside Vegas as a horizontal bar chart, with a count
        # of paired games. This is the user-visible "are we beating Vegas?" answer.
        vegas_fig = go.Figure()
        try:
            vegas_df = pd.read_sql(_sql_text("""
                SELECT mp.model_type, mp.game_date, mp.home_team, mp.away_team,
                       mp.predicted_margin, mp.actual_margin,
                       vl.home_spread, vl.source AS vegas_source, vl.bookmaker
                FROM model_predictions mp
                JOIN vegas_lines vl
                  ON vl.game_date = mp.game_date
                 AND vl.home_team_abbrev = mp.home_team
                 AND vl.away_team_abbrev = mp.away_team
                WHERE mp.actual_winner IS NOT NULL
                  AND mp.actual_margin IS NOT NULL
                  AND vl.home_spread IS NOT NULL
                  AND mp.game_date BETWEEN :start AND :end
            """), eng, params={'start': start_date, 'end': end_date})

            if not vegas_df.empty:
                # Vegas implied margin = -home_spread (convention: home_spread negative = home favored)
                vegas_df['vegas_margin'] = -vegas_df['home_spread']
                vegas_df['model_err'] = (vegas_df['predicted_margin'] - vegas_df['actual_margin']).abs()
                vegas_df['vegas_err'] = (vegas_df['vegas_margin'] - vegas_df['actual_margin']).abs()

                # Per-model MAE
                model_mae = vegas_df.groupby('model_type')['model_err'].mean().to_dict()
                vegas_mae = vegas_df['vegas_err'].mean()
                n_paired = len(vegas_df)

                # Build bar chart: x=MAE, y=label
                labels = list(model_mae.keys()) + ['Vegas']
                values = [model_mae[k] for k in model_mae] + [vegas_mae]
                colors_bar = [_MODEL_COLOR.get(k, '#888') for k in model_mae] + ['gold']
                vegas_fig.add_trace(go.Bar(
                    x=values, y=[lbl.upper() for lbl in labels],
                    orientation='h', marker_color=colors_bar,
                    text=[f'{v:.2f} pts' for v in values],
                    textposition='outside',
                    hovertemplate='%{y}<br>MAE: %{x:.3f} pts<extra></extra>',
                ))
                vegas_fig.update_layout(
                    template='plotly_dark',
                    title=f'Margin MAE: model vs Vegas — {n_paired} paired games '
                          f'({vegas_df["game_date"].min().date()} to {vegas_df["game_date"].max().date()})',
                    xaxis_title='Mean absolute error (points; lower = better)',
                    yaxis_title='',
                    height=max(280, (len(labels) + 1) * 50),
                    margin=dict(l=80, r=80, t=60, b=40),
                    showlegend=False,
                )
                vegas_fig.add_vline(x=vegas_mae, line_dash='dash', line_color='gold', opacity=0.6,
                                    annotation_text='Vegas baseline', annotation_position='top')
            else:
                vegas_fig.update_layout(template='plotly_dark',
                                        title='No paired (model prediction + Vegas line + actual) data in this date range')
        except Exception as e:
            print(f"[model_perf] Vegas comparison failed: {e}")
            vegas_fig.update_layout(template='plotly_dark',
                                    title=f'Vegas comparison error: {e}')

        status = dbc.Alert(
            f"Loaded {len(preds_df)} backfilled predictions across "
            f"{preds_df['game_date'].nunique() if not preds_df.empty else 0} dates "
            f"(models: {', '.join(models_selected) if models_selected else 'none'}).",
            color='info'
        )
        return (headline, registry_table, rolling_fig, rel_fig, resid_fig, hist_fig,
                roc_fig, cm_fig, vegas_fig, status)
    finally:
        eng.dispose()


#######################################################################################################################

########################################################################################################################
# TAB 0: Operations — pipeline orchestrator + system status
#
# Surfaces pipeline.py from inside the dashboard: one panel for "is everything fresh?",
# one form per stage so the user can launch a subset, and a tailing log view. Long-running
# stages execute as a detached subprocess (pipeline.launch_pipeline_background) so the
# Dash callback returns immediately; we then poll pipeline.read_state() to update the UI.
########################################################################################################################

from orchestration import pipeline as _pipeline


def _ops_status_cards(status):
    """Render the freshness summary as a grid of cards.

    Each card shows one "layer" of the system, the last-known date for it, and a
    colored badge for staleness (green<3d, amber<14d, red>=14d, gray=missing).
    """
    def staleness_color(days_ago):
        if days_ago is None: return 'secondary'
        if days_ago < 3: return 'success'
        if days_ago < 14: return 'warning'
        return 'danger'

    layers = [
        ('Schedule (game_list)', 'latest_schedule_date'),
        ('Boxscore v3 ingest', 'latest_boxscore_v3_date'),
        ('Player impact cache', 'latest_player_impact_date'),
        ('Features CSV', 'features_csv_max_date'),
        ('Latest train', 'latest_train_any'),
        ('Latest validation', 'latest_validation_any'),
        ('Latest prediction', 'latest_prediction_date'),
        ('Latest backfilled prediction', 'latest_backfilled_prediction_date'),
    ]
    cards = []
    for label, key in layers:
        value = status.get(key) or '—'
        days_ago = status.get(f'{key}_days_ago')
        days_str = '?' if days_ago is None else f'{days_ago}d ago'
        cards.append(dbc.Col(dbc.Card([
            dbc.CardBody([
                html.Div(label, style={'fontSize': '12px', 'opacity': 0.7}),
                html.Div(str(value), style={'fontSize': '18px', 'fontWeight': 'bold'}),
                dbc.Badge(days_str, color=staleness_color(days_ago), className='mt-1'),
            ])
        ], style={'minHeight': '110px'}), width=3, className='mb-2'))
    return dbc.Row(cards)


def _ops_recommendations(recs):
    """Render the recommend()'s output."""
    if not recs:
        return dbc.Alert('Every layer is fresh. Nothing to do.', color='success')
    items = [html.Li([html.Code(r['stage']), ' — ', r['reason']]) for r in recs]
    return dbc.Alert([html.Strong('Suggested stages: '), html.Ul(items, className='mb-0')], color='info')


def _ops_stage_form(stage):
    """Build the per-stage form: checkbox to include + one input per arg."""
    inputs = [
        dbc.Col(dcc.Checklist(
            id={'kind': 'ops-stage-include', 'stage': stage['name']},
            options=[{'label': f"  {stage['name']}", 'value': stage['name']}],
            value=[], inline=True,
            inputStyle={'marginRight': '6px'},
        ), width=2),
        dbc.Col(html.Span(stage['description'], style={'fontSize': '12px', 'opacity': 0.75}),
                width=4, style={'paddingTop': '6px'}),
    ]
    arg_inputs = []
    for arg in stage['args']:
        arg_id = {'kind': 'ops-stage-arg', 'stage': stage['name'], 'arg': arg['name']}
        if arg['type'] == 'flag':
            ctl = dcc.Checklist(id=arg_id,
                                options=[{'label': f"  --{arg['cli'].lstrip('-')}", 'value': '1'}],
                                value=[], inline=True,
                                inputStyle={'marginRight': '4px'})
        elif arg['type'] == 'int':
            ctl = dbc.Input(id=arg_id, type='number', placeholder=str(arg.get('default', '')),
                            value=arg.get('default'), size='sm')
        elif arg['type'] == 'date':
            ctl = dbc.Input(id=arg_id, type='text', placeholder='YYYY-MM-DD', value='', size='sm')
        elif arg['type'] == 'choice':
            ctl = dcc.Dropdown(id=arg_id,
                               options=[{'label': c, 'value': c} for c in arg['choices']],
                               value=arg.get('default'), clearable=False,
                               style={'fontSize': '12px'})
        elif arg['type'] == 'list':
            ctl = dbc.Input(id=arg_id, type='text',
                            placeholder='comma-separated, e.g. 2026-05-01,2026-04-01',
                            value='', size='sm')
        else:
            ctl = dbc.Input(id=arg_id, type='text', value='', size='sm')
        arg_inputs.append(dbc.Col([
            html.Div(arg['cli'], style={'fontSize': '11px', 'opacity': 0.7}),
            ctl,
            html.Div(arg.get('help', ''), style={'fontSize': '10px', 'opacity': 0.5}),
        ], width='auto', style={'minWidth': '160px', 'maxWidth': '260px', 'marginRight': '8px'}))
    return dbc.Card(dbc.CardBody(dbc.Row(inputs + arg_inputs, className='g-2 align-items-center')),
                    className='mb-2')


def _collect_stage_kwargs_from_states(states_list, stage_specs):
    """Walk the pattern-matching states_list from the run callback and build the
    {stage_name: {arg_name: value}} dict pipeline.launch_pipeline_background expects."""
    # states_list is a list-of-list of {'id': dict, 'value': any} entries per matched Input/State.
    # We don't care which input slot it came from — we key on the id dict's 'arg' field.
    per_stage_kwargs: dict = {}
    for state_group in states_list or []:
        if not state_group:
            continue
        for item in state_group:
            comp_id = item['id']
            if not isinstance(comp_id, dict) or comp_id.get('kind') != 'ops-stage-arg':
                continue
            stage = comp_id['stage']
            arg = comp_id['arg']
            value = item.get('value')

            # Find the arg spec to know its type
            spec = next((a for sp in stage_specs if sp['name'] == stage
                         for a in sp['args'] if a['name'] == arg), None)
            if spec is None:
                continue
            if spec['type'] == 'flag':
                # Checklist: '1' present means flag on
                value = bool(value and '1' in value)
            elif spec['type'] == 'list':
                value = [v.strip() for v in (value or '').split(',') if v.strip()]
            elif spec['type'] == 'int':
                if value in (None, ''):
                    value = spec.get('default')
                else:
                    try: value = int(value)
                    except (ValueError, TypeError): value = spec.get('default')
            elif spec['type'] == 'date':
                value = (value or '').strip() or None
            # choice / text pass through

            if value in (None, '', [], False):
                continue
            per_stage_kwargs.setdefault(stage, {})[arg] = value
    return per_stage_kwargs


def _collect_selected_stages(states_list):
    """Pull the list of stage names whose include-checkbox is ticked."""
    selected = []
    for state_group in states_list or []:
        for item in state_group:
            comp_id = item['id']
            if isinstance(comp_id, dict) and comp_id.get('kind') == 'ops-stage-include':
                if item.get('value'):
                    selected.extend(item['value'])
    # Preserve canonical pipeline order regardless of UI order
    return [s for s in _pipeline.STAGE_ORDER if s in selected]


# ---- Layout pieces for the Operations tab ----
_OPS_STAGE_SPECS = _pipeline.get_stage_specs_for_ui()
_ops_stage_forms_block = html.Div([_ops_stage_form(s) for s in _OPS_STAGE_SPECS])


@app.callback(
    [Output('ops-status-cards', 'children'),
     Output('ops-recommendations', 'children')],
    [Input('ops-refresh-btn', 'n_clicks'),
     Input('ops-poll-interval', 'n_intervals')],
)
def _ops_refresh_status(_n, _ni):
    try:
        status = _pipeline.inspect_status()
        recs = _pipeline.recommend(status)
        return _ops_status_cards(status), _ops_recommendations(recs)
    except Exception as e:
        err = dbc.Alert(f'Status inspection failed: {e}', color='danger')
        return err, err


@app.callback(
    Output('ops-run-result', 'children'),
    Input('ops-run-btn', 'n_clicks'),
    [dash.State({'kind': 'ops-stage-include', 'stage': dash.ALL}, 'value'),
     dash.State({'kind': 'ops-stage-include', 'stage': dash.ALL}, 'id'),
     dash.State({'kind': 'ops-stage-arg', 'stage': dash.ALL, 'arg': dash.ALL}, 'value'),
     dash.State({'kind': 'ops-stage-arg', 'stage': dash.ALL, 'arg': dash.ALL}, 'id')],
    prevent_initial_call=True,
)
def _ops_run_pipeline(_n, include_values, include_ids, arg_values, arg_ids):
    # Pair values to their own IDs explicitly so we don't depend on Dash's pattern-matching order.
    include_states = [[{'id': iid, 'value': v} for iid, v in zip(include_ids, include_values)]]
    arg_states = [[{'id': aid, 'value': v} for aid, v in zip(arg_ids, arg_values)]]

    stages = _collect_selected_stages(include_states)
    if not stages:
        return dbc.Alert('Tick at least one stage checkbox first.', color='warning')
    per_stage_kwargs = _collect_stage_kwargs_from_states(arg_states, _OPS_STAGE_SPECS)

    try:
        seed = _pipeline.launch_pipeline_background(stages, per_stage_kwargs)
    except Exception as e:
        return dbc.Alert(f'Could not launch pipeline: {e}', color='danger')

    return dbc.Alert([
        html.Strong(f"Launched run {seed['run_id']}. "),
        f"Stages: {', '.join(stages)}. ",
        html.Br(),
        html.Small(f"Log: {seed['log_path']}", style={'opacity': 0.7}),
    ], color='success')


@app.callback(
    [Output('ops-current-run', 'children'),
     Output('ops-log-tail', 'value')],
    Input('ops-poll-interval', 'n_intervals'),
)
def _ops_poll(_ni):
    state = _pipeline.read_state()
    if not state:
        return html.Div('No pipeline runs yet.', style={'opacity': 0.6}), ''

    badge_color = {'queued': 'info', 'running': 'primary',
                   'completed': 'success', 'failed': 'danger'}.get(state.get('status'), 'secondary')
    summary = dbc.Card(dbc.CardBody([
        dbc.Row([
            dbc.Col(html.Div([html.Strong('Run: '), state.get('run_id', '?')]), width=4),
            dbc.Col([html.Strong('Status: '),
                     dbc.Badge(state.get('status', '?'), color=badge_color)], width=3),
            dbc.Col(html.Div([html.Strong('Stage: '),
                              state.get('current_stage') or '—']), width=3),
            dbc.Col(html.Div([html.Strong('Started: '),
                              str(state.get('started_at'))[:19]]),
                    width=2, style={'fontSize': '11px'}),
        ]),
        html.Hr(),
        html.Div([html.Strong('Stages requested: '),
                  ', '.join(state.get('stages_requested') or [])]),
        html.Div([html.Strong('Results so far: '), html.Br(),
                  html.Ul([html.Li(f"{r['stage']}: exit {r['exit_code']}"
                                   f" @ {str(r.get('finished_at'))[:19]}")
                           for r in (state.get('stage_results') or [])])]),
    ]))
    log_text = _pipeline.tail_log(state.get('log_path'), n_lines=400)
    return summary, log_text


# ---- The composed Operations tab layout (used inside dbc.Tabs below) ----
_ops_tab_children = [
    html.Div('Run the data → features → train → predict pipeline, monitor its progress, '
             'and see which layers are stale. Each stage maps 1:1 to an existing script — the '
             'underlying CLI is unchanged, this tab just makes the run sequence visible and '
             'configurable.', style={'fontSize': '13px', 'opacity': 0.8}),
    html.Br(),
    dcc.Interval(id='ops-poll-interval', interval=3000, n_intervals=0),
    html.H5('System status'),
    html.Div(id='ops-status-cards'),
    html.Div(id='ops-recommendations', className='mt-2'),
    html.Div(
        dbc.Button('Refresh status', id='ops-refresh-btn', color='secondary', size='sm'),
        className='mt-2 mb-3'
    ),
    html.Hr(),
    html.H5('Pipeline stages'),
    html.Div('Tick the stages you want to run, fill in any optional args, then hit Run. '
             'Stages execute in the canonical order (fetch_data → player_impact → features → '
             'train → predict → backfill → validate) regardless of UI ordering.',
             style={'fontSize': '12px', 'opacity': 0.7, 'marginBottom': '8px'}),
    _ops_stage_forms_block,
    html.Div([
        dbc.Button('Run selected stages', id='ops-run-btn', color='success'),
        html.Span(id='ops-run-result', className='ms-3'),
    ], className='mt-2 mb-3'),
    html.Hr(),
    html.H5('Current / last run'),
    html.Div(id='ops-current-run'),
    html.Br(),
    html.H6('Log tail (auto-refresh every 3s)'),
    dcc.Textarea(id='ops-log-tail', value='', readOnly=True,
                 style={'width': '100%', 'height': '300px', 'fontFamily': 'monospace',
                        'fontSize': '11px', 'backgroundColor': '#111', 'color': '#ddd'}),
]


app.layout = html.Div(
    [
        html.H1('Kai NBA Data Project'),
        html.Div('This is my shit-ass website'),
        html.Br(),

        dbc.Tabs([
            dbc.Tab(label='Operations', children=_ops_tab_children),
            dbc.Tab(label = 'Overall League Data - Scatter', children = [
                html.Div('On this page, you can play around with the vertical and horizontal axes to plot data.'),
                html.Br(),
                dbc.Row(
                    [
                        dbc.Col(
                            yDropdown,
                            align = 'center',
                            width = {'size':3}
                        ),
                        dbc.Col(
                            dcc.Graph(id='leagueChart')
                        ),
                        dbc.Col(
                            [statListGroup,
                             html.Br(),
                            datePicker]
                        )
                    ]
                ),

                dbc.Row(
                    dbc.Col(
                        xDropdown,
                        width = {'size': 3, 'offset':4}
                    )

                ),

            ]),

            dbc.Tab(label = 'Pearson Correlation Matrix View', children = [
                html.Div('Pearson correlation coefficient measures linear correlation between two sets of data. 1 means perfect positive correlation, -1 means perfect negative correlation.'),
                html.Br(),
                dbc.Row(
                    dbc.Col(
                        datePickerScatterMatrix
                    )
                ),
                dbc.Row(
                    dbc.Col(
                        attributeDropdown
                    )
                ),
                dbc.Row(
                    dbc.Col(
                        attributeCount
                    )
                ),
                dbc.Row(
                    [

                        dbc.Col(
                            dcc.Graph(id='scatterMatrix')
                        )
                    ]
                ),
                html.Br(),
                html.Div('Below is the reduced correlation matrix of the top K best identifiers. 1 means perfect positive correlation, -1 means perfect negative correlation.'),
                html.Br(),
                dbc.Row(
                    featureSelectionBanner
                ),
                dbc.Row(
                    [
                        dbc.Col(
                            dcc.Graph(id='reducedCorrelationMatrix'),
                            align = 'center'
                        ),
                        dbc.Col(
                            dcc.Graph(id='reducedScatterMatrix'),
                            align = 'left'
                        ),
                    ]
                )

            ]),

            dbc.Tab(label = 'Team-by-team Data - Scatter', children = [
                html.Br(),
                dbc.Row(
                    [
                        dbc.Col(
                            yDropdownTeam,
                            align = 'center',
                            width = {'size':3}
                        ),
                        dbc.Col(
                            dcc.Graph(id='teamChart')
                        ),
                        dbc.Col(
                            [statListGroupTeam,
                             html.Br(),
                             datePickerTeam,
                             html.Br(),
                             teamPicker]
                        )
                    ]
                ),

                dbc.Row(
                    dbc.Col(
                        xDropdownTeam,
                        width = {'size': 3, 'offset':4}
                    )

                ),
            ]),

            # TAB 4: Rolling Feature Tracker
            dbc.Tab(label='Rolling Feature Tracker', children=[
                html.Br(),
                html.Div('Track how team rolling statistics (L5/L10 averages) change over the course of the season.'),
                html.Br(),
                dbc.Row([
                    dbc.Col(teamPickerFeatureTracker if ML_FEATURES_AVAILABLE else html.Div('ML features not loaded'), width=4),
                    dbc.Col(featurePickerTracker if ML_FEATURES_AVAILABLE else html.Div(), width=4),
                    dbc.Col(windowPicker if ML_FEATURES_AVAILABLE else html.Div(), width=4),
                ]),
                html.Br(),
                dbc.Row([
                    dbc.Col(datePickerFeatureTracker if ML_FEATURES_AVAILABLE else html.Div(), width=6),
                ]),
                html.Br(),
                dbc.Row([
                    dbc.Col(dcc.Graph(id='featureTrackerChart'), width=12),
                ]) if ML_FEATURES_AVAILABLE else html.Div('Run feature_engineering.py first to generate ML features.')
            ]),

            # TAB 5: Winning Margin Correlation Analysis
            dbc.Tab(label='Margin Correlation Analysis', children=[
                html.Br(),
                html.Div('Analyze which rolling features are most correlated with winning margin (TARGET_MARGIN). Use this to identify predictive features for your ML model.'),
                html.Br(),
                dbc.Row([
                    dbc.Col(correlationFeatureType if ML_FEATURES_AVAILABLE else html.Div('ML features not loaded'), width=4),
                    dbc.Col(topNCorrelation if ML_FEATURES_AVAILABLE else html.Div(), width=6),
                ]),
                html.Br(),
                dbc.Row([
                    dbc.Col(
                        dbc.Card([
                            dbc.CardHeader('Correlation Summary'),
                            dbc.CardBody(html.Pre(id='correlationStats', style={'whiteSpace': 'pre-wrap'}))
                        ]),
                        width=12
                    ),
                ]) if ML_FEATURES_AVAILABLE else html.Div(),
                html.Br(),
                dbc.Row([
                    dbc.Col(dcc.Graph(id='marginCorrelationBar'), width=6),
                    dbc.Col(dcc.Graph(id='marginCorrelationHeatmap'), width=6),
                ]) if ML_FEATURES_AVAILABLE else html.Div('Run feature_engineering.py first to generate ML features.')
            ]),

            # TAB 6: Game Predictions - Comparing sklearn vs PyTorch
            dbc.Tab(label='Game Predictions', children=[
                html.Br(),
                html.H4('NBA Game Predictions: Scikit-learn vs PyTorch Comparison'),
                html.Div([
                    'Compare predictions from two different ML approaches: ',
                    html.Span('Random Forest (scikit-learn)', style={'color': '#3498db', 'fontWeight': 'bold'}),
                    ' vs ',
                    html.Span('Neural Network (PyTorch)', style={'color': '#e74c3c', 'fontWeight': 'bold'}),
                ]),
                html.Hr(),
                dbc.Row([
                    dbc.Col(predictionDatePicker, width=3),
                    dbc.Col(predictionQuickSelect, width=3),
                    dbc.Col(predictionRefreshBtn, width=3),
                ]),
                html.Div(id='predictionStatus', className='mt-3'),
                html.Br(),
                html.H5('Side-by-Side Comparison'),
                html.Div(id='predictionResultsContainer'),
                html.Br(),
                dbc.Row([
                    dbc.Col([
                        html.H5('Win Probability Comparison'),
                        html.Div([
                            html.Span('Blue = Random Forest', style={'color': '#3498db', 'marginRight': '20px'}),
                            html.Span('Red = Neural Network', style={'color': '#e74c3c'})
                        ]),
                        dcc.Graph(id='predictionProbChart')
                    ], width=6),
                    dbc.Col([
                        html.H5('Margin Distribution Comparison'),
                        html.Div([
                            'RF uses 100 decision trees. NN uses Monte Carlo Dropout (100 forward passes with dropout enabled).'
                        ]),
                        dcc.Graph(id='predictionMarginChart')
                    ], width=6),
                ]),
                html.Br(),
                dbc.Row([
                    dbc.Col(dbc.Card([
                        dbc.CardHeader('Random Forest (sklearn)', style={'backgroundColor': 'rgba(52, 152, 219, 0.3)'}),
                        dbc.CardBody([
                            html.P([html.Strong('Algorithm: '), 'Ensemble of 100 decision trees']),
                            html.P([html.Strong('Uncertainty: '), 'Each tree votes independently, distribution shows agreement']),
                            html.P([html.Strong('Strengths: '), 'Great for tabular data, handles missing values, fast training']),
                            html.P([html.Em('Current training/validation metrics: see Model Performance tab')], style={'fontSize': '11px', 'opacity': 0.7}),
                        ])
                    ]), width=6),
                    dbc.Col(dbc.Card([
                        dbc.CardHeader('Neural Network (PyTorch)', style={'backgroundColor': 'rgba(231, 76, 60, 0.3)'}),
                        dbc.CardBody([
                            html.P([html.Strong('Algorithm: '), '3-layer MLP (128→64→32→1) with BatchNorm & Dropout']),
                            html.P([html.Strong('Uncertainty: '), 'Monte Carlo Dropout - run inference 100x with dropout ON']),
                            html.P([html.Strong('Strengths: '), 'Learns complex patterns, scales to large data, GPU acceleration']),
                            html.P([html.Em('Current training/validation metrics: see Model Performance tab')], style={'fontSize': '11px', 'opacity': 0.7}),
                        ])
                    ]), width=6),
                ]),
                html.Br(),
                dbc.Card([
                    dbc.CardHeader('Key Insights'),
                    dbc.CardBody([
                        html.P([html.Strong('Why RF often wins on tabular data: '), 'Decision trees naturally capture feature interactions and handle heterogeneous features well.']),
                        html.P([html.Strong('When models disagree: '), 'Games where RF and NN pick different winners are higher uncertainty - consider the underdog.']),
                        html.P([html.Strong('Margin distribution width: '), 'Wider = more uncertain. If both models show wide distributions, the game is a toss-up.']),
                    ])
                ]),
                html.Br(),
                html.Hr(),
                html.H4('Feature Importance Explanations (SHAP)'),
                html.Div([
                    html.P([
                        'SHAP (SHapley Additive exPlanations) shows which features are driving each prediction. ',
                        html.Span('Green bars', style={'color': '#2ecc71', 'fontWeight': 'bold'}),
                        ' push toward the home team winning. ',
                        html.Span('Red bars', style={'color': '#e74c3c', 'fontWeight': 'bold'}),
                        ' push toward the away team winning. The length of each bar shows the magnitude of impact on the predicted point margin.'
                    ]),
                    html.P([
                        html.Strong('Example: '),
                        'If "DIFF_netRating_L10" has a SHAP value of +3.2, it means the home team\'s superior net rating (last 10 games) is adding approximately 3.2 points to the predicted margin.'
                    ]),
                ]),
                html.Div(id='predictionShapContainer')
            ]),

            # TAB 7: Model Performance - training vs live prediction metrics
            dbc.Tab(label='Model Performance', children=[
                html.Br(),
                html.H4('Model Performance: training claims vs live results'),
                html.Div([
                    'Live prediction accuracy from ',
                    html.Code('model_predictions'),
                    ' (backfilled with actual results), compared to the training-time metrics in ',
                    html.Code('model_registry'),
                    '. Use the date range to scope live metrics; the registry view is always full history.'
                ]),
                html.Hr(),
                dbc.Row([
                    dbc.Col(modelPerfDateRange, width=4),
                    dbc.Col(modelPerfModelToggle, width=5),
                    dbc.Col(modelPerfRefreshBtn, width=2),
                ]),
                html.Div(id='modelPerfStatus', className='mt-2'),
                html.Br(),
                html.H5('Live performance (date-range filtered)'),
                html.Div(id='modelPerfHeadline'),
                html.Br(),
                dbc.Row([
                    dbc.Col(dcc.Graph(id='modelPerfRollingChart'), width=12),
                ]),
                dbc.Row([
                    dbc.Col(dcc.Graph(id='modelPerfReliabilityChart'), width=6),
                    dbc.Col(dcc.Graph(id='modelPerfResidualChart'), width=6),
                ]),
                dbc.Row([
                    dbc.Col(dcc.Graph(id='modelPerfRocChart'), width=6),
                    dbc.Col(dcc.Graph(id='modelPerfConfusionChart'), width=6),
                ]),
                dbc.Row([
                    dbc.Col(dcc.Graph(id='modelPerfVegasChart'), width=12),
                ]),
                dbc.Row([
                    dbc.Col(dcc.Graph(id='modelPerfErrorHistChart'), width=12),
                ]),
                html.Hr(),
                html.H5('Training-time metrics (from model_registry)'),
                html.Div(
                    'Highlighted rows are the currently-active model versions. '
                    'Validation runs from validate_models.py will appear here as additional rows.',
                    style={'fontSize': '13px', 'color': '#aaa'}
                ),
                html.Br(),
                html.Div(id='modelPerfRegistryTable'),
            ]),
        ])
    ]
)


if __name__ == '__main__':
    app.run_server(port = 5000)


