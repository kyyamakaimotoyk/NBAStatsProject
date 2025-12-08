import plotly as plt
import plotly.express as px
import plotly.graph_objects as go
import sqlalchemy as sql
from nba_api.stats.static import teams, players
import pandas as pd
import os

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

########################################################################################################################
# Load ML Features Dataset (from feature_engineering.py output)
########################################################################################################################

# Handle both direct execution and import scenarios
try:
    _current_dir = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _current_dir = os.getcwd()
ml_features_path = os.path.join(_current_dir, 'nba_ml_features.csv')
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

# Import prediction functions
try:
    from predict_games import (
        get_scheduled_games, get_team_rolling_stats, build_matchup_features,
        load_or_train_rf_models, load_or_train_pytorch_models,
        predict_with_rf, predict_with_pytorch,
        create_engine as pred_create_engine,
        NBA_API_AVAILABLE, PYTORCH_AVAILABLE, SHAP_AVAILABLE,
        get_top_shap_features, format_feature_impact
    )
    PREDICTIONS_AVAILABLE = True
except (ImportError, OSError) as e:
    print(f"Warning: Could not import prediction functions: {e}")
    PREDICTIONS_AVAILABLE = False
    NBA_API_AVAILABLE = False
    PYTORCH_AVAILABLE = False
    SHAP_AVAILABLE = False

# Pre-load BOTH models if available
rf_models = None
nn_models = None

if PREDICTIONS_AVAILABLE:
    try:
        pred_engine = pred_create_engine()

        # Load Random Forest models
        print("Loading Random Forest models...")
        rf_models = load_or_train_rf_models(pred_engine)
        print("Random Forest models loaded successfully")

        # Load PyTorch models if available
        if PYTORCH_AVAILABLE:
            print("Loading PyTorch models...")
            nn_models = load_or_train_pytorch_models(pred_engine)
            print("PyTorch models loaded successfully")
        else:
            print("PyTorch not available - only Random Forest models loaded")

        pred_engine.dispose()
    except Exception as e:
        print(f"Warning: Could not load prediction models: {e}")
        import traceback
        traceback.print_exc()
        PREDICTIONS_AVAILABLE = False

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

        # Create engine for database queries
        engine = pred_create_engine()

        rf_predictions = []
        nn_predictions = []

        for _, game in games.iterrows():
            home_id = game['HOME_TEAM_ID']
            away_id = game['AWAY_TEAM_ID']
            home_team = game['HOME_TEAM']
            away_team = game['AWAY_TEAM']

            # Get team features
            home_features = get_team_rolling_stats(engine, home_id, game_date)
            away_features = get_team_rolling_stats(engine, away_id, game_date)

            if home_features is None or away_features is None:
                continue

            # Build matchup features
            matchup = build_matchup_features(home_features, away_features)

            # Random Forest prediction
            if rf_models:
                clf, reg, scaler, feature_names = rf_models
                rf_result = predict_with_rf(clf, reg, scaler, feature_names, matchup)
                rf_predictions.append({
                    'home_team': home_team,
                    'away_team': away_team,
                    'win_prob': rf_result['win_prob'],
                    'margin_mean': rf_result['margin_mean'],
                    'margin_std': rf_result['margin_std'],
                    'margin_samples': rf_result['margin_samples']
                })

            # Neural Network prediction (if available)
            if nn_models:
                clf, reg, scaler, feature_names = nn_models
                nn_result = predict_with_pytorch(clf, reg, scaler, feature_names, matchup)
                nn_predictions.append({
                    'home_team': home_team,
                    'away_team': away_team,
                    'win_prob': nn_result['win_prob'],
                    'margin_mean': nn_result['margin_mean'],
                    'margin_std': nn_result['margin_std'],
                    'margin_samples': nn_result['margin_samples']
                })

        engine.dispose()

        if not rf_predictions:
            return (
                dbc.Alert("Could not generate predictions (missing team data)", color='warning'),
                [],
                go.Figure(),
                go.Figure(),
                []
            )

        # Build comparison results table
        table_rows = []
        for i, rf_pred in enumerate(rf_predictions):
            nn_pred = nn_predictions[i] if i < len(nn_predictions) else None

            rf_pick = rf_pred['home_team'] if rf_pred['win_prob'] > 0.5 else rf_pred['away_team']
            nn_pick = nn_pred['home_team'] if nn_pred and nn_pred['win_prob'] > 0.5 else (nn_pred['away_team'] if nn_pred else '-')

            # Check if models agree
            agree = rf_pick == nn_pick if nn_pred else True
            agree_badge = dbc.Badge("AGREE", color="success") if agree else dbc.Badge("DISAGREE", color="danger")

            table_rows.append(html.Tr([
                html.Td(f"{rf_pred['away_team']} @ {rf_pred['home_team']}"),
                # Random Forest columns
                html.Td(rf_pick, style={'fontWeight': 'bold', 'color': '#3498db'}),
                html.Td(f"{rf_pred['win_prob']:.1%}"),
                html.Td(f"{rf_pred['margin_mean']:+.1f}"),
                # Neural Network columns
                html.Td(nn_pick if nn_pred else '-', style={'fontWeight': 'bold', 'color': '#e74c3c'}),
                html.Td(f"{nn_pred['win_prob']:.1%}" if nn_pred else '-'),
                html.Td(f"{nn_pred['margin_mean']:+.1f}" if nn_pred else '-'),
                # Agreement
                html.Td(agree_badge)
            ]))

        results_table = dbc.Table([
            html.Thead([
                html.Tr([
                    html.Th("Matchup", rowSpan=2, style={'verticalAlign': 'middle'}),
                    html.Th("Random Forest (sklearn)", colSpan=3, style={'textAlign': 'center', 'backgroundColor': 'rgba(52, 152, 219, 0.3)'}),
                    html.Th("Neural Network (PyTorch)", colSpan=3, style={'textAlign': 'center', 'backgroundColor': 'rgba(231, 76, 60, 0.3)'}),
                    html.Th("", rowSpan=2)
                ]),
                html.Tr([
                    html.Th("Pick", style={'backgroundColor': 'rgba(52, 152, 219, 0.2)'}),
                    html.Th("Win%", style={'backgroundColor': 'rgba(52, 152, 219, 0.2)'}),
                    html.Th("Margin", style={'backgroundColor': 'rgba(52, 152, 219, 0.2)'}),
                    html.Th("Pick", style={'backgroundColor': 'rgba(231, 76, 60, 0.2)'}),
                    html.Th("Win%", style={'backgroundColor': 'rgba(231, 76, 60, 0.2)'}),
                    html.Th("Margin", style={'backgroundColor': 'rgba(231, 76, 60, 0.2)'}),
                ])
            ]),
            html.Tbody(table_rows)
        ], bordered=True, hover=True, responsive=True, striped=True, className='mt-3')

        # Build SIDE-BY-SIDE probability chart
        fig_prob = go.Figure()

        matchups = [f"{p['away_team']} @ {p['home_team']}" for p in rf_predictions]

        # Random Forest bars (blue)
        fig_prob.add_trace(go.Bar(
            name='Random Forest',
            x=[p['win_prob'] for p in rf_predictions],
            y=matchups,
            orientation='h',
            marker_color='#3498db',
            text=[f"RF: {p['win_prob']:.1%}" for p in rf_predictions],
            textposition='inside',
            offsetgroup=0
        ))

        # Neural Network bars (red) - if available
        if nn_predictions:
            fig_prob.add_trace(go.Bar(
                name='Neural Network',
                x=[p['win_prob'] for p in nn_predictions],
                y=matchups,
                orientation='h',
                marker_color='#e74c3c',
                text=[f"NN: {p['win_prob']:.1%}" for p in nn_predictions],
                textposition='inside',
                offsetgroup=1
            ))

        fig_prob.update_layout(
            title=f'Win Probability Comparison: RF vs NN ({game_date})',
            barmode='group',
            xaxis_title='Home Team Win Probability',
            xaxis=dict(tickformat='.0%', range=[0, 1]),
            yaxis_title='',
            template='minty_dark',
            height=max(400, len(rf_predictions) * 60),
            margin=dict(l=150),
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
        )

        fig_prob.add_vline(x=0.5, line_dash="dash", line_color="white", opacity=0.5,
                          annotation_text="50%", annotation_position="top")

        # Build SIDE-BY-SIDE margin distribution chart
        fig_margin = go.Figure()

        for i, rf_pred in enumerate(rf_predictions):
            matchup = f"{rf_pred['away_team']} @ {rf_pred['home_team']}"
            nn_pred = nn_predictions[i] if i < len(nn_predictions) else None

            # RF distribution (blue)
            fig_margin.add_trace(go.Violin(
                y=[f"{matchup} "] * len(rf_pred['margin_samples']),  # Extra space to separate
                x=rf_pred['margin_samples'],
                name=f'RF: {matchup}',
                orientation='h',
                side='positive',
                meanline_visible=True,
                box_visible=True,
                points=False,
                showlegend=(i == 0),
                legendgroup='RF',
                fillcolor='rgba(52, 152, 219, 0.5)',
                line_color='#3498db'
            ))

            # NN distribution (red) - if available
            if nn_pred:
                fig_margin.add_trace(go.Violin(
                    y=[f"{matchup}"] * len(nn_pred['margin_samples']),
                    x=nn_pred['margin_samples'],
                    name=f'NN: {matchup}',
                    orientation='h',
                    side='positive',
                    meanline_visible=True,
                    box_visible=True,
                    points=False,
                    showlegend=(i == 0),
                    legendgroup='NN',
                    fillcolor='rgba(231, 76, 60, 0.5)',
                    line_color='#e74c3c'
                ))

        fig_margin.update_layout(
            title=f'Margin Distribution Comparison: RF (blue) vs NN (red) ({game_date})',
            xaxis_title='Point Margin (+ = Home Team Wins)',
            yaxis_title='',
            template='minty_dark',
            height=max(400, len(rf_predictions) * 100),
            margin=dict(l=150),
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
        )

        fig_margin.add_vline(x=0, line_dash="dash", line_color="yellow", opacity=0.7,
                            annotation_text="Even", annotation_position="top")

        # Build SHAP Feature Importance visualizations
        shap_components = []

        if SHAP_AVAILABLE:
            for i, rf_pred in enumerate(rf_predictions):
                nn_pred = nn_predictions[i] if i < len(nn_predictions) else None

                # Create card for each game's SHAP explanation
                matchup = f"{rf_pred['away_team']} @ {rf_pred['home_team']}"

                # Get SHAP features for both models
                rf_shap = rf_pred.get('shap_feature_importance', {})
                nn_shap = nn_pred.get('shap_feature_importance', {}) if nn_pred else {}

                if rf_shap:
                    # Create SHAP bar chart for RF
                    top_features_rf = get_top_shap_features(rf_shap, top_n=10)

                    if top_features_rf:
                        feature_names = [f.replace('DIFF_', '').replace('HOME_', 'H_').replace('AWAY_', 'A_')[:20] for f, _, _ in top_features_rf]
                        shap_values = [v for _, v, _ in top_features_rf]

                        fig_shap_rf = go.Figure()
                        colors = ['#2ecc71' if v > 0 else '#e74c3c' for v in shap_values]

                        fig_shap_rf.add_trace(go.Bar(
                            x=shap_values,
                            y=feature_names,
                            orientation='h',
                            marker_color=colors,
                            text=[f'{v:+.2f}' for v in shap_values],
                            textposition='outside',
                            name='Random Forest'
                        ))

                        fig_shap_rf.update_layout(
                            title=f'RF: Top Features - {matchup}',
                            xaxis_title='SHAP Value (Impact on Point Margin)',
                            yaxis_title='',
                            template='minty_dark',
                            height=400,
                            yaxis=dict(autorange='reversed'),
                            margin=dict(l=150)
                        )
                        fig_shap_rf.add_vline(x=0, line_dash="dash", line_color="white", opacity=0.5)

                        # Create NN SHAP chart if available
                        fig_shap_nn = go.Figure()
                        if nn_shap:
                            top_features_nn = get_top_shap_features(nn_shap, top_n=10)
                            if top_features_nn:
                                nn_feature_names = [f.replace('DIFF_', '').replace('HOME_', 'H_').replace('AWAY_', 'A_')[:20] for f, _, _ in top_features_nn]
                                nn_shap_values = [v for _, v, _ in top_features_nn]
                                nn_colors = ['#2ecc71' if v > 0 else '#e74c3c' for v in nn_shap_values]

                                fig_shap_nn.add_trace(go.Bar(
                                    x=nn_shap_values,
                                    y=nn_feature_names,
                                    orientation='h',
                                    marker_color=nn_colors,
                                    text=[f'{v:+.2f}' for v in nn_shap_values],
                                    textposition='outside',
                                    name='Neural Network'
                                ))

                                fig_shap_nn.update_layout(
                                    title=f'NN: Top Features - {matchup}',
                                    xaxis_title='SHAP Value (Impact on Point Margin)',
                                    yaxis_title='',
                                    template='minty_dark',
                                    height=400,
                                    yaxis=dict(autorange='reversed'),
                                    margin=dict(l=150)
                                )
                                fig_shap_nn.add_vline(x=0, line_dash="dash", line_color="white", opacity=0.5)

                        # Add to components
                        shap_components.append(
                            dbc.Card([
                                dbc.CardHeader(f"Feature Importance: {matchup}", style={'fontWeight': 'bold'}),
                                dbc.CardBody([
                                    dbc.Row([
                                        dbc.Col(dcc.Graph(figure=fig_shap_rf), width=6),
                                        dbc.Col(dcc.Graph(figure=fig_shap_nn) if nn_shap else html.Div("NN SHAP not available"), width=6),
                                    ]),
                                    html.Hr(),
                                    html.Div([
                                        html.P([
                                            html.Strong("How to read: "),
                                            html.Span("Green bars = helps home team win. Red bars = helps away team win. ", style={'color': '#95DFC9'}),
                                            html.Span("Longer bars = stronger impact on the prediction.", style={'color': '#FA7851'})
                                        ]),
                                        html.P([
                                            html.Strong("Example: "),
                                            "If 'DIFF_netRating_L10' is +2.5 (green), the home team's better net rating over last 10 games adds ~2.5 points to the predicted margin."
                                        ])
                                    ], style={'fontSize': '12px', 'backgroundColor': 'rgba(255,255,255,0.05)', 'padding': '10px', 'borderRadius': '5px'})
                                ])
                            ], className='mb-3')
                        )

        # Status message
        nn_status = " and Neural Network" if nn_predictions else " (Neural Network not available)"
        shap_status = " with SHAP explanations" if SHAP_AVAILABLE else ""
        status = dbc.Alert(
            f"Generated Random Forest{nn_status} predictions{shap_status} for {len(rf_predictions)} games on {game_date}",
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

app.layout = html.Div(
    [
        html.H1('Kai NBA Data Project'),
        html.Div('This is my shit-ass website'),
        html.Br(),

        dbc.Tabs([
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
                            html.P([html.Strong('Test AUC: '), '0.792 | Test MAE: 9.33 points']),
                        ])
                    ]), width=6),
                    dbc.Col(dbc.Card([
                        dbc.CardHeader('Neural Network (PyTorch)', style={'backgroundColor': 'rgba(231, 76, 60, 0.3)'}),
                        dbc.CardBody([
                            html.P([html.Strong('Algorithm: '), '3-layer MLP (128→64→32→1) with BatchNorm & Dropout']),
                            html.P([html.Strong('Uncertainty: '), 'Monte Carlo Dropout - run inference 100x with dropout ON']),
                            html.P([html.Strong('Strengths: '), 'Learns complex patterns, scales to large data, GPU acceleration']),
                            html.P([html.Strong('Test AUC: '), '0.776 | Test MAE: 9.94 points']),
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
            ])
        ])
    ]
)


if __name__ == '__main__':
    app.run_server(port = 5000)


