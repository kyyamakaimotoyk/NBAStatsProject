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
from datetime import date
import plotly.graph_objects as go
import numpy as np
from sklearn.feature_selection import SelectKBest


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
            ])
        ])
    ]
)


if __name__ == '__main__':
    app.run_server(port = 5000)


