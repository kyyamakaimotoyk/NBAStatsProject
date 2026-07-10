"""P1 — player-game dataset builder for counting-stat projections.

Builds one row per (player, game) for the top-8 players per team by rolling
minutes, with leakage-safe (shift-1) rolling features, over the last three
regular seasons (2023-24, 2024-25, 2025-26) plus 2022-23 as rolling warm-up.

Feature groups (see docs/player_projections_plan.md §2 — approved Tier-2
groups for the first round: A, B, C, G):
  A  player form/volume  (traditional + advanced player tables)
  B  opportunity/role    (playertrack, hustle, misc player tables)
  C  teammate context    (vacated minutes/usage of absent regulars)
  D  schedule/fatigue    (Tier-1 only: rest, B2B, games-last-7)
  E  own-team context    (Tier-1 only)
  F  opponent defense    (Tier-1 only, incl. *_ALLOWED_L10)
  G  market              (vegas_lines: spread, total, implied team total)
  H  EXPECTED_POSS interaction (Tier-1 only)

Known caveat (documented in the P1 report): the vacated-minutes/usage
features and the top-8 row selection use *did-not-play-today* as the
absence signal, which includes surprise scratches the market knew pregame
but a naive backtest would not (the E7 problem, in a milder form).
Phase B production replaces this with `historical_injury_report`.

Output: outputs/p1_player_dataset.pkl (pandas DataFrame).
Run:    python data_engineering/player_dataset.py
"""
import os
import sys
import time

import numpy as np
import pandas as pd
import sqlalchemy as sa

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


def _season_filter():
    return "','".join(ALL_SEASONS)


def load_frames(engine):
    """Pull the raw player/team/market frames for the season window."""
    frames = {}
    q_games = f"""
        SELECT GAME_ID, TEAM_ID, SEASON_ID, GAME_DATE, MATCHUP,
               PTS, FGM, FGA, FG3M, FG3A, FTM, FTA, OREB, DREB, REB,
               AST, STL, BLK, TOV, PF
        FROM game_list
        WHERE SEASON_ID IN ('{_season_filter()}')
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
        WHERE g.SEASON_ID IN ('{_season_filter()}')
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
        WHERE g.SEASON_ID IN ('{_season_filter()}')
    """
    frames['player_adv'] = pd.read_sql(q_adv, engine)

    q_track = f"""
        SELECT p.gameId, p.teamId, p.personId,
               p.touches, p.passes, p.reboundChancesTotal
        FROM boxscoreplayertrackv3_player p
        JOIN game_list g ON g.GAME_ID = p.gameId AND g.TEAM_ID = p.teamId
        WHERE g.SEASON_ID IN ('{_season_filter()}')
    """
    frames['player_track'] = pd.read_sql(q_track, engine)

    q_hustle = f"""
        SELECT p.gameId, p.teamId, p.personId,
               p.contestedShots, p.deflections, p.looseBallsRecoveredTotal
        FROM boxscorehustlev2_player p
        JOIN game_list g ON g.GAME_ID = p.gameId AND g.TEAM_ID = p.teamId
        WHERE g.SEASON_ID IN ('{_season_filter()}')
    """
    frames['player_hustle'] = pd.read_sql(q_hustle, engine)

    q_misc = f"""
        SELECT p.gameId, p.teamId, p.personId,
               p.pointsSecondChance, p.pointsFastBreak, p.pointsPaint
        FROM boxscoremiscv3_player p
        JOIN game_list g ON g.GAME_ID = p.gameId AND g.TEAM_ID = p.teamId
        WHERE g.SEASON_ID IN ('{_season_filter()}')
    """
    frames['player_misc'] = pd.read_sql(q_misc, engine)

    q_team_adv = f"""
        SELECT t.gameId, t.teamId,
               t.pace, t.defensiveRating, t.offensiveRating,
               t.offensiveReboundPercentage, t.defensiveReboundPercentage,
               t.effectiveFieldGoalPercentage, t.assistPercentage
        FROM boxscoreadvancedv3_team t
        JOIN game_list g ON g.GAME_ID = t.gameId AND g.TEAM_ID = t.teamId
        WHERE g.SEASON_ID IN ('{_season_filter()}')
    """
    frames['team_adv'] = pd.read_sql(q_team_adv, engine)

    q_team_ff = f"""
        SELECT t.gameId, t.teamId,
               t.freeThrowAttemptRate, t.teamTurnoverPercentage,
               t.oppFreeThrowAttemptRate, t.oppTeamTurnoverPercentage
        FROM boxscorefourfactorsv3_team t
        JOIN game_list g ON g.GAME_ID = t.gameId AND g.TEAM_ID = t.teamId
        WHERE g.SEASON_ID IN ('{_season_filter()}')
    """
    frames['team_ff'] = pd.read_sql(q_team_ff, engine)

    frames['vegas'] = pd.read_sql(
        """
        SELECT game_id, line_type, home_spread, total
        FROM vegas_lines
        WHERE game_id IS NOT NULL
          AND (home_spread IS NOT NULL OR total IS NOT NULL)
        """, engine)
    return frames


def roll_mean(g, col, window):
    return g[col].transform(lambda s: s.shift(1).rolling(window, min_periods=1).mean())


def build_team_context(team_games, team_adv, team_ff):
    """Per (GAME_ID, TEAM_ID): rolling L10 team profile + allowed-stats."""
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


def add_player_rolling(pt):
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

    # Previous-season per-36 priors.
    season_order = {s: i for i, s in enumerate(ALL_SEASONS)}
    agg = pt.groupby(['personId', 'SEASON_ID']).agg(
        prev_min=('MIN', 'sum'),
        **{f'prev_{s}': (s, 'sum') for s in STAT_COLS}).reset_index()
    for s in STAT_COLS:
        agg[f'PREV_{s}36'] = agg[f'prev_{s}'] / agg['prev_min'].replace(0, np.nan) * 36
    agg['season_idx'] = agg['SEASON_ID'].map(season_order) + 1  # applies to NEXT season
    idx_to_season = {v: k for k, v in {s: i for i, s in enumerate(ALL_SEASONS)}.items()}
    agg['applies_to'] = agg['season_idx'].map(idx_to_season)
    prev = agg.dropna(subset=['applies_to'])[
        ['personId', 'applies_to', 'prev_min'] + [f'PREV_{s}36' for s in STAT_COLS]]
    prev = prev.rename(columns={'applies_to': 'SEASON_ID', 'prev_min': 'PREV_SEASON_MIN'})
    pt = pt.merge(prev, on=['personId', 'SEASON_ID'], how='left')

    # Rest / absence.
    pt['PLAYER_REST_DAYS'] = pt.groupby('personId')['GAME_DATE'].diff().dt.days.clip(upper=30)
    pt['LONG_ABSENCE_RETURN'] = (pt['PLAYER_REST_DAYS'] > 14).astype(float)
    return pt


def add_vacated_features(pt, team_ctx):
    """Group C: per team-game, minutes/usage of absent regulars + missed games."""
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
    """Group G: spread / total / implied team total (line-type priority)."""
    prio = {'closing': 0, 'pregame': 1, 'opening': 2}
    v = vegas.copy()
    v['prio'] = v['line_type'].map(prio).fillna(3)
    v = v.sort_values(['game_id', 'prio'])
    best = v.groupby('game_id').first().reset_index()[['game_id', 'home_spread', 'total']]
    pt = pt.merge(best, left_on='GAME_ID', right_on='game_id', how='left').drop(columns=['game_id'])
    sign = np.where(pt['IS_HOME'] == 1, 1.0, -1.0)
    pt['TEAM_SPREAD'] = pt['home_spread'] * sign
    pt['ABS_SPREAD'] = pt['home_spread'].abs()
    pt['GAME_TOTAL'] = pt['total']
    pt['TEAM_IMPLIED_TOTAL'] = pt['total'] / 2 - pt['TEAM_SPREAD'] / 2
    return pt.drop(columns=['home_spread', 'total'])


def build(engine=None, out_path=OUT_PATH):
    t0 = time.time()
    engine = engine or get_engine()
    frames = load_frames(engine)
    print(f"loaded raw frames in {time.time()-t0:.0f}s "
          f"(player rows: {len(frames['player_trad']):,})")

    team_ctx, pairing = build_team_context(
        frames['team_games'], frames['team_adv'], frames['team_ff'])

    pt = build_player_frame(frames)
    pt = pt.rename(columns={'gameId': 'GAME_ID', 'teamId': 'TEAM_ID'})
    meta = pairing.merge(
        team_ctx[['GAME_ID', 'TEAM_ID', 'GAME_DATE']], on=['GAME_ID', 'TEAM_ID'])
    pt = pt.merge(meta, on=['GAME_ID', 'TEAM_ID'], how='inner')
    pt['IS_HOME'] = pt['MATCHUP'].str.contains('vs.', regex=False).astype(float)

    pt = add_player_rolling(pt)
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
    ds = pt[(pt['MIN_RANK'] <= TOP_N_PER_TEAM) & pt['MIN_L10'].notna()].copy()
    ds = ds[ds['SEASON_ID'].isin(TRAIN_SEASONS)].copy()  # drop warm-up season rows

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    ds.to_pickle(out_path)
    print(f"dataset: {len(ds):,} rows / {ds.shape[1]} cols -> {out_path} "
          f"({time.time()-t0:.0f}s total)")
    return ds


if __name__ == '__main__':
    build()
