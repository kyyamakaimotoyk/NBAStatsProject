"""Player-game feature dataset for counting-stat projections (P-series).

Builds one row per (player, game) for the top-8 players per team by rolling
minutes, with leakage-safe (shift-1) rolling features. Serves BOTH:

  * training     — build(): historical seasons, rows for games actually played
                   (P1 protocol: 2023-24..2025-26 regular seasons, 2022-23 warm-up)
  * inference    — build_inference_features(): appends PLACEHOLDER rows for an
                   upcoming slate to the same historical frames and runs the
                   identical shift(1) pipeline, so a future game's features are
                   computed by the exact code that built the training data
                   (no second feature implementation to drift — train/serve parity).

Feature groups (docs/player_projections_plan.md §2 — approved Tier-2 groups
A, B, C, G):
  A  player form/volume  (traditional + advanced player tables)
  B  opportunity/role    (playertrack, hustle, misc player tables)
  C  teammate context    (vacated minutes/usage of absent regulars)
  D  schedule/fatigue    (Tier-1 only: rest, B2B, games-last-7)
  E  own-team context    (Tier-1 only)
  F  opponent defense    (Tier-1 only, incl. *_ALLOWED_L10)
  G  market              (vegas_lines: spread, total, implied team total)
  H  EXPECTED_POSS interaction (Tier-1 only)

Absence semantics: in TRAINING, vacated-minutes/usage and top-8 selection use
did-not-play-today (the E7 caveat, documented in the P1 report). In INFERENCE,
callers pass the pregame injury report — OUT players are excluded from the
placeholder roster, so the same vacated-features code sees them as absent
regulars. That is the pregame-absence upgrade, and it needs no special casing.

Run (training build): python data_engineering/player_dataset.py
"""
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.db import get_engine  # noqa: E402
from data_engineering.player_impact import parse_minutes  # noqa: E402

WARMUP_SEASON = '22022'
TRAIN_SEASONS = ['22023', '22024', '22025']
ALL_SEASONS = [WARMUP_SEASON] + TRAIN_SEASONS

TARGETS = ['MIN', 'PTS', 'REB', 'AST', 'STL', 'BLK', 'TOV', 'FG3M', 'FG3A', 'FTM', 'FTA']
STAT_COLS = TARGETS[1:]  # everything but MIN

OUT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'outputs', 'p1_player_dataset.pkl')

REGULAR_MIN_MPG = 15.0     # rolling MPG threshold to count as a "regular"
REGULAR_RECENCY_DAYS = 21  # regular must have played within this window
TOP_N_PER_TEAM = 8


def normalize_player_name(name: str) -> str:
    """Match injury-report names to boxscore names: lowercase, strip
    punctuation and generational suffixes."""
    s = str(name).lower().replace('.', '').replace("'", '').strip()
    for suffix in (' jr', ' sr', ' ii', ' iii', ' iv', ' v'):
        if s.endswith(suffix):
            s = s[: -len(suffix)].strip()
    return ' '.join(s.split())


def season_id_from_game_id(game_id) -> str:
    """'0022500306' -> '22025' (2025-26). Works for pre/regular/post prefixes."""
    g = str(int(game_id)).zfill(10)
    return f"2{2000 + int(g[3:5])}"


def _season_filter(seasons) -> str:
    return "','".join(seasons)


def load_frames(engine, seasons=None):
    """Pull the raw player/team/market frames for a season window."""
    seasons = list(seasons) if seasons else list(ALL_SEASONS)
    frames = {'seasons': seasons}
    q_games = f"""
        SELECT GAME_ID, TEAM_ID, SEASON_ID, GAME_DATE, MATCHUP,
               PTS, FGM, FGA, FG3M, FG3A, FTM, FTA, OREB, DREB, REB,
               AST, STL, BLK, TOV, PF
        FROM game_list
        WHERE SEASON_ID IN ('{_season_filter(seasons)}')
    """
    frames['team_games'] = pd.read_sql(q_games, engine)

    q_trad = f"""
        SELECT p.gameId, p.teamId, p.personId, p.firstName, p.familyName,
               p.position, p.minutes,
               p.points, p.reboundsOffensive, p.reboundsDefensive, p.reboundsTotal,
               p.assists, p.steals, p.blocks, p.turnovers,
               p.threePointersMade, p.threePointersAttempted,
               p.freeThrowsMade, p.freeThrowsAttempted,
               p.fieldGoalsMade, p.fieldGoalsAttempted
        FROM boxscoretraditionalv3_player p
        JOIN game_list g ON g.GAME_ID = p.gameId AND g.TEAM_ID = p.teamId
        WHERE g.SEASON_ID IN ('{_season_filter(seasons)}')
    """
    frames['player_trad'] = pd.read_sql(q_trad, engine)

    q_adv = f"""
        SELECT p.gameId, p.teamId, p.personId,
               p.usagePercentage, p.trueShootingPercentage,
               p.effectiveFieldGoalPercentage,
               p.offensiveReboundPercentage, p.defensiveReboundPercentage,
               p.assistPercentage, p.turnoverRatio, p.PIE
        FROM boxscoreadvancedv3_player p
        JOIN game_list g ON g.GAME_ID = p.gameId AND g.TEAM_ID = p.teamId
        WHERE g.SEASON_ID IN ('{_season_filter(seasons)}')
    """
    frames['player_adv'] = pd.read_sql(q_adv, engine)

    q_track = f"""
        SELECT p.gameId, p.teamId, p.personId,
               p.touches, p.passes, p.reboundChancesTotal
        FROM boxscoreplayertrackv3_player p
        JOIN game_list g ON g.GAME_ID = p.gameId AND g.TEAM_ID = p.teamId
        WHERE g.SEASON_ID IN ('{_season_filter(seasons)}')
    """
    frames['player_track'] = pd.read_sql(q_track, engine)

    q_hustle = f"""
        SELECT p.gameId, p.teamId, p.personId,
               p.contestedShots, p.deflections, p.looseBallsRecoveredTotal
        FROM boxscorehustlev2_player p
        JOIN game_list g ON g.GAME_ID = p.gameId AND g.TEAM_ID = p.teamId
        WHERE g.SEASON_ID IN ('{_season_filter(seasons)}')
    """
    frames['player_hustle'] = pd.read_sql(q_hustle, engine)

    q_misc = f"""
        SELECT p.gameId, p.teamId, p.personId,
               p.pointsSecondChance, p.pointsFastBreak, p.pointsPaint
        FROM boxscoremiscv3_player p
        JOIN game_list g ON g.GAME_ID = p.gameId AND g.TEAM_ID = p.teamId
        WHERE g.SEASON_ID IN ('{_season_filter(seasons)}')
    """
    frames['player_misc'] = pd.read_sql(q_misc, engine)

    q_team_adv = f"""
        SELECT t.gameId, t.teamId,
               t.pace, t.defensiveRating, t.offensiveRating,
               t.offensiveReboundPercentage, t.defensiveReboundPercentage,
               t.effectiveFieldGoalPercentage, t.assistPercentage
        FROM boxscoreadvancedv3_team t
        JOIN game_list g ON g.GAME_ID = t.gameId AND g.TEAM_ID = t.teamId
        WHERE g.SEASON_ID IN ('{_season_filter(seasons)}')
    """
    frames['team_adv'] = pd.read_sql(q_team_adv, engine)

    q_team_ff = f"""
        SELECT t.gameId, t.teamId,
               t.freeThrowAttemptRate, t.teamTurnoverPercentage,
               t.oppFreeThrowAttemptRate, t.oppTeamTurnoverPercentage
        FROM boxscorefourfactorsv3_team t
        JOIN game_list g ON g.GAME_ID = t.gameId AND g.TEAM_ID = t.teamId
        WHERE g.SEASON_ID IN ('{_season_filter(seasons)}')
    """
    frames['team_ff'] = pd.read_sql(q_team_ff, engine)

    # Both id-resolved and date/team keys: upcoming games usually have no
    # resolved game_id yet (they are not in game_list), so add_vegas falls
    # back to a (date, home, away) join for them.
    frames['vegas'] = pd.read_sql(
        """
        SELECT game_id, game_date, home_team_id, away_team_id,
               line_type, home_spread, total
        FROM vegas_lines
        WHERE home_spread IS NOT NULL OR total IS NOT NULL
        """, engine)
    return frames


def roll_mean(g, col, window):
    return g[col].transform(lambda s: s.shift(1).rolling(window, min_periods=1).mean())


def build_team_context(team_games, team_adv, team_ff):
    """Per (GAME_ID, TEAM_ID): rolling L10 team profile + allowed-stats.

    Placeholder (future-game) rows are welcome: their own-game stats are NaN,
    but shift(1) rolling gives them features from all prior real games.
    """
    tg = team_games.drop_duplicates(subset=['GAME_ID', 'TEAM_ID']).copy()
    tg['GAME_DATE'] = pd.to_datetime(tg['GAME_DATE'])
    tg = tg.merge(team_adv.drop_duplicates(subset=['gameId', 'teamId']),
                  left_on=['GAME_ID', 'TEAM_ID'],
                  right_on=['gameId', 'teamId'], how='left').drop(columns=['gameId', 'teamId'])
    tg = tg.merge(team_ff.drop_duplicates(subset=['gameId', 'teamId']),
                  left_on=['GAME_ID', 'TEAM_ID'],
                  right_on=['gameId', 'teamId'], how='left').drop(columns=['gameId', 'teamId'])

    # Attach the opponent's same-game raw stats (two rows per GAME_ID).
    opp = tg[['GAME_ID', 'TEAM_ID', 'FG3M', 'FG3A', 'TOV', 'PTS']].rename(
        columns={'TEAM_ID': 'OPP_TEAM_ID', 'FG3M': 'opp_FG3M', 'FG3A': 'opp_FG3A',
                 'TOV': 'opp_TOV', 'PTS': 'opp_PTS'})
    tg = tg.merge(opp, on='GAME_ID', how='left')
    tg = tg[tg['TEAM_ID'] != tg['OPP_TEAM_ID']].copy()

    # Per-game derived rates.
    tg['THREE_RATE'] = tg['FG3A'] / tg['FGA'].replace(0, np.nan)
    tg['PITP_PROXY'] = (tg['PTS'] - 3 * tg['FG3M'] - tg['FTM']) / tg['PTS'].replace(0, np.nan)
    tg['ALLOWED_3PA'] = tg['opp_FG3A']
    tg['ALLOWED_3P_PCT'] = tg['opp_FG3M'] / tg['opp_FG3A'].replace(0, np.nan)
    tg['FORCED_TOV'] = tg['opp_TOV']

    tg = tg.sort_values(['TEAM_ID', 'GAME_DATE'])
    g = tg.groupby('TEAM_ID')
    rolled = pd.DataFrame({
        'GAME_ID': tg['GAME_ID'], 'TEAM_ID': tg['TEAM_ID'], 'GAME_DATE': tg['GAME_DATE'],
        'TEAM_PACE_L10': roll_mean(g, 'pace', 10),
        'TEAM_ORTG_L10': roll_mean(g, 'offensiveRating', 10),
        'TEAM_DRTG_L10': roll_mean(g, 'defensiveRating', 10),
        'TEAM_OREB_PCT_L10': roll_mean(g, 'offensiveReboundPercentage', 10),
        'TEAM_DREB_PCT_L10': roll_mean(g, 'defensiveReboundPercentage', 10),
        'TEAM_EFG_L10': roll_mean(g, 'effectiveFieldGoalPercentage', 10),
        'TEAM_AST_PCT_L10': roll_mean(g, 'assistPercentage', 10),
        'TEAM_TOV_PCT_L10': roll_mean(g, 'teamTurnoverPercentage', 10),
        'TEAM_FT_RATE_L10': roll_mean(g, 'freeThrowAttemptRate', 10),
        'TEAM_3PA_RATE_L10': roll_mean(g, 'THREE_RATE', 10),
        'TEAM_PITP_SHARE_L10': roll_mean(g, 'PITP_PROXY', 10),
        'TEAM_PF_L10': roll_mean(g, 'PF', 10),
        'TEAM_3PA_ALLOWED_L10': roll_mean(g, 'ALLOWED_3PA', 10),
        'TEAM_3P_PCT_ALLOWED_L10': roll_mean(g, 'ALLOWED_3P_PCT', 10),
        'TEAM_FT_RATE_ALLOWED_L10': roll_mean(g, 'oppFreeThrowAttemptRate', 10),
        'TEAM_TOV_FORCED_L10': roll_mean(g, 'FORCED_TOV', 10),
        'TEAM_TOV_COMMITTED_L10': roll_mean(g, 'TOV', 10),
    })

    # Schedule features per team-game.
    rolled = rolled.sort_values(['TEAM_ID', 'GAME_DATE'])
    grp = rolled.groupby('TEAM_ID')['GAME_DATE']
    rolled['TEAM_REST_DAYS'] = grp.diff().dt.days.clip(upper=10)
    rolled['TEAM_IS_B2B'] = (rolled['TEAM_REST_DAYS'] == 1).astype(float)
    game_dates = rolled[['TEAM_ID', 'GAME_DATE']].copy()
    counts = []
    for _, sub in game_dates.groupby('TEAM_ID'):
        dates = sub['GAME_DATE'].values
        c = [(np.sum((dates < d) & (dates >= d - np.timedelta64(7, 'D')))) for d in dates]
        counts.append(pd.Series(c, index=sub.index))
    rolled['TEAM_GAMES_LAST7'] = pd.concat(counts).sort_index()
    rolled['TEAM_GAME_NUM'] = rolled.groupby('TEAM_ID').cumcount() + 1
    return rolled, tg[['GAME_ID', 'TEAM_ID', 'OPP_TEAM_ID', 'SEASON_ID', 'MATCHUP']].copy()


def build_player_frame(frames):
    """Merge player tables, parse minutes, compute per-game derived cols."""
    pt = frames['player_trad'].copy()
    pt['MIN'] = pt['minutes'].map(parse_minutes)
    pt = pt[pt['MIN'] > 0].copy()  # rows for players who actually played
    pt = pt.rename(columns={
        'points': 'PTS', 'reboundsTotal': 'REB', 'reboundsOffensive': 'OREB_P',
        'reboundsDefensive': 'DREB_P', 'assists': 'AST', 'steals': 'STL',
        'blocks': 'BLK', 'turnovers': 'TOV',
        'threePointersMade': 'FG3M', 'threePointersAttempted': 'FG3A',
        'freeThrowsMade': 'FTM', 'freeThrowsAttempted': 'FTA',
        'fieldGoalsMade': 'FGM_P', 'fieldGoalsAttempted': 'FGA_P'})
    pt['STARTED'] = (pt['position'].fillna('').str.strip() != '').astype(float)
    pt['PLAYER_NAME'] = pt['firstName'].fillna('') + ' ' + pt['familyName'].fillna('')

    pt = pt.drop_duplicates(subset=['gameId', 'teamId', 'personId'])
    for name in ['player_adv', 'player_track', 'player_hustle', 'player_misc']:
        f = frames[name].drop_duplicates(subset=['gameId', 'teamId', 'personId'])
        pt = pt.merge(f, on=['gameId', 'teamId', 'personId'], how='left')
    return pt


def add_player_rolling(pt, seasons):
    """Groups A + B: rolling form, per-36, priors, opportunity metrics."""
    pt = pt.sort_values(['personId', 'GAME_DATE']).copy()

    # Per-36 per-game rates (only meaningful above a minutes floor).
    for s in STAT_COLS:
        pt[f'{s}_36G'] = np.where(pt['MIN'] >= 4, pt[s] / pt['MIN'] * 36, np.nan)

    g = pt.groupby('personId')
    pt['MIN_L5'] = roll_mean(g, 'MIN', 5)
    pt['MIN_L10'] = roll_mean(g, 'MIN', 10)
    pt['MIN_STD_L10'] = g['MIN'].transform(
        lambda s: s.shift(1).rolling(10, min_periods=2).std())
    pt['MIN_TREND'] = pt['MIN_L5'] - pt['MIN_L10']
    pt['STARTS_SHARE_L10'] = roll_mean(g, 'STARTED', 10)

    for s in STAT_COLS:
        pt[f'{s}_L5'] = roll_mean(g, s, 5)
        pt[f'{s}_L10'] = roll_mean(g, s, 10)
        pt[f'{s}36_L10'] = roll_mean(g, f'{s}_36G', 10)

    # Group A Tier-2 skill rates from the advanced table.
    for src, name in [('usagePercentage', 'USG_PCT'), ('trueShootingPercentage', 'TS_PCT'),
                      ('effectiveFieldGoalPercentage', 'EFG_PCT'),
                      ('offensiveReboundPercentage', 'OREB_PCT'),
                      ('defensiveReboundPercentage', 'DREB_PCT'),
                      ('assistPercentage', 'AST_PCT'),
                      ('turnoverRatio', 'TOV_RATIO'), ('PIE', 'PIE')]:
        pt[f'{name}_L10'] = roll_mean(g, src, 10)

    # Shot diet.
    pt['THREE_RATE_G'] = pt['FG3A'] / pt['FGA_P'].replace(0, np.nan)
    pt['FT_RATE_G'] = pt['FTA'] / pt['FGA_P'].replace(0, np.nan)
    pt['3PAR_L10'] = roll_mean(g, 'THREE_RATE_G', 10)
    pt['FTR_L10'] = roll_mean(g, 'FT_RATE_G', 10)

    # Scoring-profile shares (from traditional + misc).
    pt['SHARE_PTS_3_G'] = 3 * pt['FG3M'] / pt['PTS'].replace(0, np.nan)
    pt['SHARE_PTS_FT_G'] = pt['FTM'] / pt['PTS'].replace(0, np.nan)
    pt['SHARE_PTS_PAINT_G'] = pt['pointsPaint'] / pt['PTS'].replace(0, np.nan)
    for c, out in [('SHARE_PTS_3_G', 'SHARE_PTS_3_L10'),
                   ('SHARE_PTS_FT_G', 'SHARE_PTS_FT_L10'),
                   ('SHARE_PTS_PAINT_G', 'SHARE_PTS_PAINT_L10')]:
        pt[out] = roll_mean(g, c, 10)

    # Group B opportunity/role.
    for src, out in [('touches', 'TOUCHES_L10'), ('passes', 'PASSES_L10'),
                     ('reboundChancesTotal', 'REB_CHANCES_L10'),
                     ('contestedShots', 'CONTESTED_SHOTS_L10'),
                     ('deflections', 'DEFLECTIONS_L10'),
                     ('looseBallsRecoveredTotal', 'LOOSE_BALLS_L10'),
                     ('pointsSecondChance', 'PTS_2ND_CHANCE_L10'),
                     ('pointsFastBreak', 'PTS_FASTBREAK_L10'),
                     ('pointsPaint', 'PTS_PAINT_L10')]:
        pt[out] = roll_mean(g, src, 10)

    # Season-to-date expanding per-36 (shifted), GP, shrunk make-rates.
    gs = pt.groupby(['personId', 'SEASON_ID'])
    pt['GP_SEASON'] = gs.cumcount()
    csum_min = gs['MIN'].transform(lambda s: s.shift(1).expanding().sum())
    pt['MIN_SEASON_AVG'] = gs['MIN'].transform(lambda s: s.shift(1).expanding().mean())
    for s in STAT_COLS:
        csum = gs[s].transform(lambda x: x.shift(1).expanding().sum())
        pt[f'{s}36_SEASON'] = csum / csum_min.replace(0, np.nan) * 36
    c3m = gs['FG3M'].transform(lambda x: x.shift(1).expanding().sum())
    c3a = gs['FG3A'].transform(lambda x: x.shift(1).expanding().sum())
    cftm = gs['FTM'].transform(lambda x: x.shift(1).expanding().sum())
    cfta = gs['FTA'].transform(lambda x: x.shift(1).expanding().sum())
    pt['SHRUNK_3P_PCT'] = (c3m.fillna(0) + 0.36 * 50) / (c3a.fillna(0) + 50)
    pt['SHRUNK_FT_PCT'] = (cftm.fillna(0) + 0.78 * 30) / (cfta.fillna(0) + 30)

    # Previous-season per-36 priors (season -> next season, in sorted order).
    season_sorted = sorted(set(seasons))
    next_season = {s: season_sorted[i + 1] for i, s in enumerate(season_sorted[:-1])}
    agg = pt.groupby(['personId', 'SEASON_ID']).agg(
        prev_min=('MIN', 'sum'),
        **{f'prev_{s}': (s, 'sum') for s in STAT_COLS}).reset_index()
    for s in STAT_COLS:
        agg[f'PREV_{s}36'] = agg[f'prev_{s}'] / agg['prev_min'].replace(0, np.nan) * 36
    agg['applies_to'] = agg['SEASON_ID'].map(next_season)
    prev = agg.dropna(subset=['applies_to'])[
        ['personId', 'applies_to', 'prev_min'] + [f'PREV_{s}36' for s in STAT_COLS]]
    prev = prev.rename(columns={'applies_to': 'SEASON_ID', 'prev_min': 'PREV_SEASON_MIN'})
    pt = pt.merge(prev, on=['personId', 'SEASON_ID'], how='left')

    # Rest / absence.
    pt['PLAYER_REST_DAYS'] = pt.groupby('personId')['GAME_DATE'].diff().dt.days.clip(upper=30)
    pt['LONG_ABSENCE_RETURN'] = (pt['PLAYER_REST_DAYS'] > 14).astype(float)
    return pt


def add_vacated_features(pt, team_ctx):
    """Group C: per team-game, minutes/usage of absent regulars + missed games.

    A "regular" is anyone averaging >= REGULAR_MIN_MPG rolling minutes whose
    last appearance is recent. In training, absence = did-not-play-today; in
    inference, injured players were excluded from the placeholder roster
    upstream, so they show up as absent regulars here — same code, honest
    pregame semantics.
    """
    state_cols = ['MIN_L10', 'USG_PCT_L10']
    pt_small = pt[['GAME_ID', 'TEAM_ID', 'personId', 'GAME_DATE'] + state_cols]

    rows = []
    for team_id, sub in pt_small.groupby('TEAM_ID'):
        state = {}  # personId -> (last_date, MIN_L10, USG_L10)
        for game_id, game_rows in sub.sort_values('GAME_DATE').groupby('GAME_ID', sort=False):
            d = game_rows['GAME_DATE'].iloc[0]
            today = set(game_rows['personId'])
            vac_min = vac_usg = 0.0
            n_out = 0
            for pid, (last_d, m10, u10) in state.items():
                if pid in today:
                    continue
                if (d - last_d).days > REGULAR_RECENCY_DAYS:
                    continue
                if m10 is not None and not np.isnan(m10) and m10 >= REGULAR_MIN_MPG:
                    n_out += 1
                    vac_min += m10
                    if u10 is not None and not np.isnan(u10):
                        vac_usg += u10
            rows.append((game_id, team_id, n_out, vac_min, vac_usg))
            for _, r in game_rows.iterrows():
                state[r['personId']] = (d, r['MIN_L10'], r['USG_PCT_L10'])
    vac = pd.DataFrame(rows, columns=['GAME_ID', 'TEAM_ID', 'N_REGULARS_OUT',
                                      'VACATED_MIN', 'VACATED_USG'])
    pt = pt.merge(vac, on=['GAME_ID', 'TEAM_ID'], how='left')

    # Missed-games proxy: team game number minus player's own team-game count.
    pt = pt.merge(team_ctx[['GAME_ID', 'TEAM_ID', 'TEAM_GAME_NUM']],
                  on=['GAME_ID', 'TEAM_ID'], how='left')
    pt['PLAYER_TEAM_GAME_NUM'] = pt.sort_values('GAME_DATE').groupby(
        ['personId', 'TEAM_ID', 'SEASON_ID']).cumcount() + 1
    season_first = pt.groupby(['TEAM_ID', 'SEASON_ID'])['TEAM_GAME_NUM'].transform('min')
    team_game_num_season = pt['TEAM_GAME_NUM'] - season_first + 1
    pt['MISSED_GAMES_SEASON'] = (team_game_num_season - pt['PLAYER_TEAM_GAME_NUM']).clip(lower=0)
    return pt


def add_vegas(pt, vegas):
    """Group G: spread / total / implied team total.

    Two-pass join: by resolved game_id first (historical rows), then by
    (date, home, away) for rows the id-resolver couldn't match — upcoming
    games are not in game_list yet, so their vegas rows carry NULL game_id.
    """
    prio = {'closing': 0, 'pregame': 1, 'opening': 2}
    v = vegas.copy()
    v['prio'] = v['line_type'].map(prio).fillna(3)

    by_gid = (v.dropna(subset=['game_id']).sort_values(['game_id', 'prio'])
               .groupby('game_id').first().reset_index()[['game_id', 'home_spread', 'total']])
    pt = pt.merge(by_gid, left_on='GAME_ID', right_on='game_id', how='left').drop(columns=['game_id'])

    need = pt['home_spread'].isna() & pt['total'].isna()
    if need.any():
        v2 = v.dropna(subset=['home_team_id', 'away_team_id', 'game_date']).copy()
        if len(v2):
            v2['game_date'] = pd.to_datetime(v2['game_date'])
            v2 = (v2.sort_values('prio')
                    .groupby(['game_date', 'home_team_id', 'away_team_id']).first()
                    .reset_index()[['game_date', 'home_team_id', 'away_team_id',
                                    'home_spread', 'total']]
                    .rename(columns={'home_spread': '_hs2', 'total': '_tot2'}))
            v2['home_team_id'] = v2['home_team_id'].astype(float)
            v2['away_team_id'] = v2['away_team_id'].astype(float)
            is_home = pt['IS_HOME'] == 1
            key = pd.DataFrame({
                'game_date': pd.to_datetime(pt['GAME_DATE']).dt.normalize(),
                'home_team_id': np.where(is_home, pt['TEAM_ID'], pt['OPP_TEAM_ID']).astype(float),
                'away_team_id': np.where(is_home, pt['OPP_TEAM_ID'], pt['TEAM_ID']).astype(float),
            }, index=pt.index)
            merged = key.merge(v2, on=['game_date', 'home_team_id', 'away_team_id'], how='left')
            merged.index = pt.index
            pt['home_spread'] = pt['home_spread'].fillna(merged['_hs2'])
            pt['total'] = pt['total'].fillna(merged['_tot2'])

    sign = np.where(pt['IS_HOME'] == 1, 1.0, -1.0)
    pt['TEAM_SPREAD'] = pt['home_spread'] * sign
    pt['ABS_SPREAD'] = pt['home_spread'].abs()
    pt['GAME_TOTAL'] = pt['total']
    pt['TEAM_IMPLIED_TOTAL'] = pt['total'] / 2 - pt['TEAM_SPREAD'] / 2
    return pt.drop(columns=['home_spread', 'total'])


def _assemble(frames) -> pd.DataFrame:
    """The shared feature pipeline: frames (optionally with placeholder rows
    appended) -> one feature row per (player, game), MIN_RANK included."""
    seasons = frames['seasons']
    team_ctx, pairing = build_team_context(
        frames['team_games'], frames['team_adv'], frames['team_ff'])

    pt = build_player_frame(frames)
    pt = pt.rename(columns={'gameId': 'GAME_ID', 'teamId': 'TEAM_ID'})
    extra = frames.get('placeholder_players')
    if extra is not None and len(extra):
        pt = pd.concat([pt, extra], ignore_index=True, sort=False)

    meta = pairing.merge(
        team_ctx[['GAME_ID', 'TEAM_ID', 'GAME_DATE']], on=['GAME_ID', 'TEAM_ID'])
    pt = pt.merge(meta, on=['GAME_ID', 'TEAM_ID'], how='inner')
    pt['IS_HOME'] = pt['MATCHUP'].str.contains('vs.', regex=False).astype(float)

    pt = add_player_rolling(pt, seasons)
    pt = add_vacated_features(pt, team_ctx)

    own = team_ctx.drop(columns=['GAME_DATE', 'TEAM_GAME_NUM'])
    pt = pt.merge(own, on=['GAME_ID', 'TEAM_ID'], how='left')
    opp = team_ctx.drop(columns=['GAME_DATE', 'TEAM_GAME_NUM'])
    opp.columns = ['GAME_ID', 'OPP_TEAM_ID'] + [
        c.replace('TEAM_', 'OPP_') for c in opp.columns[2:]]
    pt = pt.merge(opp, on=['GAME_ID', 'OPP_TEAM_ID'], how='left')

    pt = add_vegas(pt, frames['vegas'])
    pt['EXPECTED_POSS'] = (pt['TEAM_PACE_L10'] + pt['OPP_PACE_L10']) / 2
    pt['EXPECTED_USG_POSS'] = pt['EXPECTED_POSS'] * pt['USG_PCT_L10']

    # Top-8 per team-game by rolling minutes (pregame knowledge).
    pt['MIN_RANK'] = pt.groupby(['GAME_ID', 'TEAM_ID'])['MIN_L10'].rank(
        ascending=False, method='first')
    return pt


def build(engine=None, out_path=OUT_PATH, seasons=None, train_seasons=None):
    """Training dataset: top-8 rows for the train seasons (first season in
    sorted order acts as rolling warm-up and is dropped from the output)."""
    t0 = time.time()
    engine = engine or get_engine()
    seasons = list(seasons) if seasons else list(ALL_SEASONS)
    if train_seasons is None:
        train_seasons = sorted(seasons)[1:]
    frames = load_frames(engine, seasons)
    print(f"loaded raw frames in {time.time()-t0:.0f}s "
          f"(player rows: {len(frames['player_trad']):,})")

    pt = _assemble(frames)
    ds = pt[(pt['MIN_RANK'] <= TOP_N_PER_TEAM) & pt['MIN_L10'].notna()].copy()
    ds = ds[ds['SEASON_ID'].isin(train_seasons)].copy()

    if out_path:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        ds.to_pickle(out_path)
    print(f"dataset: {len(ds):,} rows / {ds.shape[1]} cols -> {out_path} "
          f"({time.time()-t0:.0f}s total)")
    return ds


def build_inference_features(engine, slate: pd.DataFrame,
                             out_names_by_team: dict = None,
                             candidate_lookback_days: int = 400) -> pd.DataFrame:
    """Feature rows for an UPCOMING slate, via the identical pipeline.

    slate columns: GAME_ID, GAME_DATE, HOME_TEAM_ID, AWAY_TEAM_ID,
    HOME_TEAM, AWAY_TEAM (tricodes) — the get_scheduled_games() shape plus date.
    out_names_by_team: {team_tricode: iterable of player names that are OUT
    pregame}; they are excluded from the roster, which both removes them from
    the top-8 and feeds VACATED_MIN/USG for their teammates.

    Returns the top-8 candidate feature rows per team, ready for
    TwoStageXGB.predict().
    """
    out_names_by_team = out_names_by_team or {}
    slate = slate.copy()
    slate['GAME_DATE'] = pd.to_datetime(slate['GAME_DATE'])
    d0 = slate['GAME_DATE'].min()
    slate_ids = {int(g) for g in slate['GAME_ID']}

    cur = max(season_id_from_game_id(g) for g in slate['GAME_ID'])
    prev = f"2{int(cur[1:]) - 1}"
    frames = load_frames(engine, [prev, cur])

    # If the slate games were already played (backtesting a past date through
    # the production path), drop their real rows so the placeholders see the
    # world exactly as it was pregame.
    frames['team_games'] = frames['team_games'][
        ~frames['team_games']['GAME_ID'].isin(slate_ids)]
    for k in ['player_trad', 'player_adv', 'player_track', 'player_hustle', 'player_misc']:
        frames[k] = frames[k][~frames[k]['gameId'].isin(slate_ids)]

    # Candidate roster per team: each player's most recent appearance (within
    # the lookback, before the slate) decides which team he belongs to.
    tg_dates = frames['team_games'][['GAME_ID', 'TEAM_ID', 'GAME_DATE']].copy()
    tg_dates['GAME_DATE'] = pd.to_datetime(tg_dates['GAME_DATE'])
    pr = frames['player_trad'][
        ['gameId', 'teamId', 'personId', 'firstName', 'familyName', 'minutes']].copy()
    pr = pr[pr['minutes'].fillna('').astype(str).str.strip() != '']
    pr = pr.merge(tg_dates, left_on=['gameId', 'teamId'],
                  right_on=['GAME_ID', 'TEAM_ID'], how='inner')
    hist = pr[(pr['GAME_DATE'] < d0)
              & (pr['GAME_DATE'] >= d0 - pd.Timedelta(days=candidate_lookback_days))]
    last = hist.sort_values('GAME_DATE').groupby('personId', as_index=False).tail(1)
    n_for_team = hist.groupby(['personId', 'teamId']).size().rename('n_for_team').reset_index()
    last = last.merge(n_for_team, on=['personId', 'teamId'], how='left')
    cand = last[last['n_for_team'] >= 2].copy()
    cand['PLAYER_NAME'] = (cand['firstName'].fillna('') + ' '
                           + cand['familyName'].fillna('')).str.strip()
    cand['_norm'] = cand['PLAYER_NAME'].map(normalize_player_name)

    placeholders_t, placeholders_p = [], []
    for _, gm in slate.iterrows():
        gid = int(gm['GAME_ID'])
        sid = season_id_from_game_id(gid)
        sides = [
            (int(gm['HOME_TEAM_ID']), True, str(gm['HOME_TEAM']), str(gm['AWAY_TEAM'])),
            (int(gm['AWAY_TEAM_ID']), False, str(gm['AWAY_TEAM']), str(gm['HOME_TEAM'])),
        ]
        for team_id, is_home, ab, opp_ab in sides:
            matchup = f"{ab} vs. {opp_ab}" if is_home else f"{ab} @ {opp_ab}"
            placeholders_t.append({
                'GAME_ID': gid, 'TEAM_ID': team_id, 'SEASON_ID': sid,
                'GAME_DATE': gm['GAME_DATE'], 'MATCHUP': matchup})
            out_norms = {normalize_player_name(n)
                         for n in out_names_by_team.get(ab, set())}
            roster = cand[cand['teamId'] == team_id]
            roster = roster[~roster['_norm'].isin(out_norms)]
            for _, pl in roster.iterrows():
                placeholders_p.append({
                    'GAME_ID': gid, 'TEAM_ID': team_id,
                    'personId': int(pl['personId']),
                    'PLAYER_NAME': pl['PLAYER_NAME'],
                    'MIN': np.nan,
                })
    if not placeholders_p:
        return pd.DataFrame()

    frames['team_games'] = pd.concat(
        [frames['team_games'], pd.DataFrame(placeholders_t)], ignore_index=True, sort=False)
    frames['placeholder_players'] = pd.DataFrame(placeholders_p)

    pt = _assemble(frames)
    inf = pt[pt['GAME_ID'].isin(slate_ids) & pt['MIN'].isna()].copy()
    inf = inf[inf['MIN_L10'].notna()]
    inf = inf[inf['MIN_RANK'] <= TOP_N_PER_TEAM]
    return inf


if __name__ == '__main__':
    build()
