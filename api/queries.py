"""SQL read functions for the public API.

Plain SQLAlchemy Core (no pandas) so the API image carries no numpy/pandas.
Every function returns built-in types (lists of dicts, dicts) ready to serialize.

PUBLIC-SAFE COLUMN POLICY
-------------------------
The website is public, so we never expose model internals. These columns are
deliberately NOT selected:
  * features_used      — JSON snapshot of feature values (model internals)
  * feature_count      — model internals
  * model_version      — internal naming scheme / training provenance
  * home_win_probability_raw — pre-calibration A/B value (internal diagnostic)
Only fan-facing fields (teams, pick, probability, margin, actual result) ship.
"""
from __future__ import annotations

import re as _re
from functools import lru_cache
from typing import Optional
import sqlalchemy as sa

from api.db import get_engine

# Columns safe to return for a prediction row.
_PUBLIC_PREDICTION_COLS = """
    game_id,
    game_date,
    model_type,
    home_team,
    away_team,
    predicted_winner,
    predicted_margin,
    home_win_probability,
    margin_uncertainty,
    actual_winner,
    actual_margin,
    is_correct
"""


def _rows(result) -> list[dict]:
    return [dict(r) for r in result.mappings().all()]


def latest_prediction_date(model_type: Optional[str] = None) -> Optional[str]:
    """Most recent game_date that has any prediction rows. None if table empty."""
    q = "SELECT MAX(game_date) AS d FROM model_predictions"
    params: dict = {}
    if model_type:
        q += " WHERE model_type = :mt"
        params['mt'] = model_type
    with get_engine().connect() as conn:
        d = conn.execute(sa.text(q), params).scalar()
    return d.isoformat() if d is not None else None


def _attach_scores(rows: list[dict]) -> list[dict]:
    """Attach the final score (home_score/away_score) to prediction rows, from
    game_list. Only final games (WL set) get scores; upcoming/in-progress rows
    keep None. MATCHUP 'vs.' marks the home row, '@' the away row."""
    gids = {int(r['game_id']) for r in rows if r.get('game_id') is not None}
    scores: dict[int, dict] = {}
    if gids:
        id_list = ",".join(str(g) for g in sorted(gids))  # ints, safe to inline
        q = f"""
            SELECT GAME_ID, PTS, MATCHUP
            FROM game_list
            WHERE GAME_ID IN ({id_list}) AND WL IS NOT NULL
        """
        try:
            with get_engine().connect() as conn:
                for gid, pts, matchup in conn.execute(sa.text(q)):
                    side = 'home' if ' vs. ' in (matchup or '') else 'away'
                    scores.setdefault(int(gid), {})[side] = int(pts)
        except Exception as e:
            print(f"[scores] attach failed: {e}")
    for r in rows:
        s = scores.get(int(r['game_id']) if r.get('game_id') is not None else -1, {})
        r['home_score'] = s.get('home')
        r['away_score'] = s.get('away')
    return rows


def predictions_for_date(game_date: str, model_type: Optional[str] = None) -> list[dict]:
    """Predictions for a date — ONE row per (game, model): the most recent.

    The table can hold several model_versions for the same game (e.g. a retrain
    re-logged a backfill date). A public "today's games" view must show each
    matchup once per model, so we keep only the latest prediction_timestamp per
    (game_id, model_type) via a window function.
    """
    q = f"""
    SELECT {_PUBLIC_PREDICTION_COLS}
    FROM (
        SELECT *,
               ROW_NUMBER() OVER (
                   PARTITION BY game_id, model_type
                   ORDER BY prediction_timestamp DESC
               ) AS _rn
        FROM model_predictions
        WHERE game_date = :d
    ) ranked
    WHERE _rn = 1
    """
    params: dict = {'d': game_date}
    if model_type:
        q += " AND model_type = :mt"
        params['mt'] = model_type
    q += " ORDER BY game_id, model_type"
    with get_engine().connect() as conn:
        return _attach_scores(_rows(conn.execute(sa.text(q), params)))


# Preferred vegas_lines source order (mirrors the internal Dash app):
# DraftKings > other current-day books/consensus > kaggle historical > anything.
_VEGAS_SOURCE_PRIORITY = {
    'espn_draftkings': 0, 'espn_consensus': 1, 'espn_fanduel': 1,
    'espn_espnbet': 1, 'kaggle_sbr': 2, 'espn_teamrankings': 3,
}


def _market_margins(days: int) -> dict:
    """(game_date_iso, home, away) -> the market closing line's implied home margin.

    home_spread is home-perspective (negative = home favored), so the market's
    predicted home margin is -home_spread. One line per game, best source wins.
    Returns {} on any failure — the market benchmark is optional garnish.
    """
    q = """
        SELECT game_date, home_team_abbrev, away_team_abbrev, source, home_spread
        FROM vegas_lines
        WHERE home_spread IS NOT NULL
          AND game_date >= DATE_SUB(CURDATE(), INTERVAL :days DAY)
    """
    best: dict = {}
    try:
        with get_engine().connect() as conn:
            for r in conn.execute(sa.text(q), {'days': days}).mappings():
                gd = r['game_date']
                key = (gd.isoformat() if hasattr(gd, 'isoformat') else str(gd),
                       r['home_team_abbrev'], r['away_team_abbrev'])
                prio = _VEGAS_SOURCE_PRIORITY.get(r['source'], 99)
                cur = best.get(key)
                if cur is None or prio < cur[0]:
                    best[key] = (prio, -float(r['home_spread']))
    except Exception as e:
        print(f"[performance] market margin lookup failed: {e}")
        return {}
    return {k: v[1] for k, v in best.items()}


def performance_results(days: int = 90, model_type: Optional[str] = None) -> list[dict]:
    """Per-(game, model) predicted-vs-actual rows over the last ``days`` (completed
    games only — actual_winner filled in by backfill).

    This is the raw material the public Model Performance page aggregates CLIENT-SIDE
    into every chart (headline accuracy/MAE/calibration, rolling accuracy, calibration/
    reliability, ROC, confusion matrix, residuals). The web tier never computes models;
    it just reads these already-stored rows. Public-safe columns only (same policy as
    predictions_for_date — no raw probabilities, model_version, or feature internals).
    One row per (game, model): the latest prediction_timestamp, like predictions_for_date.
    """
    q = f"""
    SELECT {_PUBLIC_PREDICTION_COLS}
    FROM (
        SELECT *,
               ROW_NUMBER() OVER (
                   PARTITION BY game_id, model_type
                   ORDER BY prediction_timestamp DESC
               ) AS _rn
        FROM model_predictions
        WHERE actual_winner IS NOT NULL
          AND game_date >= DATE_SUB(CURDATE(), INTERVAL :days DAY)
    ) ranked
    WHERE _rn = 1
    """
    params: dict = {'days': days}
    if model_type:
        q += " AND model_type = :mt"
        params['mt'] = model_type
    q += " ORDER BY game_date ASC, game_id, model_type"
    with get_engine().connect() as conn:
        rows = _rows(conn.execute(sa.text(q), params))
    # Attach the market closing line (benchmark) to each row where one exists.
    market = _market_margins(days)
    for r in rows:
        gd = r['game_date']
        key = (gd.isoformat() if hasattr(gd, 'isoformat') else str(gd),
               r['home_team'], r['away_team'])
        r['market_margin'] = market.get(key)
    return _attach_scores(rows)


def accuracy_summary(days: int = 30, model_type: Optional[str] = None) -> list[dict]:
    """Aggregate accuracy over the last ``days`` of completed games, per model.

    Mirrors modeling/prediction_tracker.get_prediction_accuracy so the public
    numbers match the internal dashboard. Only games with actual_winner set
    (i.e. already played and backfilled) count.
    """
    # Dedup to the LATEST prediction per (game, model) — the table can hold
    # several model_versions for the same game (re-logs, walk-forward rows,
    # superseded predictions). Without this the aggregates counted every stale
    # row (found 2026-07-04: 432 "games" in a 159-game window).
    q = """
    SELECT
        model_type,
        COUNT(*)                                            AS total_predictions,
        SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END)     AS correct_predictions,
        AVG(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END)     AS accuracy,
        AVG(margin_error)                                   AS mae,
        SQRT(AVG(margin_error * margin_error))              AS rmse,
        AVG(ABS(home_win_probability
            - (CASE WHEN actual_winner = home_team THEN 1 ELSE 0 END))) AS calibration_error
    FROM (
        SELECT *,
               ROW_NUMBER() OVER (
                   PARTITION BY game_id, model_type
                   ORDER BY prediction_timestamp DESC
               ) AS _rn
        FROM model_predictions
        WHERE actual_winner IS NOT NULL
          AND game_date >= DATE_SUB(CURDATE(), INTERVAL :days DAY)
    ) ranked
    WHERE _rn = 1
    """
    params: dict = {'days': days}
    if model_type:
        q += " AND model_type = :mt"
        params['mt'] = model_type
    q += " GROUP BY model_type ORDER BY model_type"
    with get_engine().connect() as conn:
        return _rows(conn.execute(sa.text(q), params))


def accuracy_rolling(days: int = 90, model_type: Optional[str] = None) -> list[dict]:
    """Per-day accuracy + MAE timeseries for the historical-accuracy chart.

    One row per (game_date, model_type) with that day's hit rate and mean margin
    error. The frontend can plot these directly or compute a rolling average.
    """
    # Same latest-per-(game, model) dedup as accuracy_summary (2026-07-04).
    q = """
    SELECT
        game_date,
        model_type,
        COUNT(*)                                        AS n_games,
        AVG(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) AS accuracy,
        AVG(margin_error)                               AS mae
    FROM (
        SELECT *,
               ROW_NUMBER() OVER (
                   PARTITION BY game_id, model_type
                   ORDER BY prediction_timestamp DESC
               ) AS _rn
        FROM model_predictions
        WHERE actual_winner IS NOT NULL
          AND game_date >= DATE_SUB(CURDATE(), INTERVAL :days DAY)
    ) ranked
    WHERE _rn = 1
    """
    params: dict = {'days': days}
    if model_type:
        q += " AND model_type = :mt"
        params['mt'] = model_type
    q += " GROUP BY game_date, model_type ORDER BY game_date ASC, model_type"
    with get_engine().connect() as conn:
        return _rows(conn.execute(sa.text(q), params))


# ---------------------------------------------------------------------------
# Data exploration: rolling-feature time series (Dash Tab 4 port)
# ---------------------------------------------------------------------------

# Curated, public-safe base features (mirrors the Dash feature_categories). The
# column name is built as HOME_<feature>_<window> — so `feature` MUST be validated
# against this allowlist before it touches SQL (no column-name injection).
_EXPLORE_FEATURES: frozenset[str] = frozenset({
    # Traditional
    "PTS", "FGM", "FGA", "FG_PCT", "FG3M", "FG3A", "FG3_PCT", "FTM", "FTA", "FT_PCT",
    "OREB", "DREB", "REB", "AST", "STL", "BLK", "TOV", "PF", "PLUS_MINUS",
    # Advanced
    "offensiveRating", "defensiveRating", "netRating", "pace", "possessions",
    "EFG_PCT", "TS_PCT", "assistPercentage", "assistToTurnover", "PIE",
    # Four Factors
    "FT_RATE", "TOV_PCT", "OREB_PCT", "OPP_EFG_PCT", "OPP_FT_RATE", "OPP_TOV_PCT",
    # Hustle
    "contestedShots", "deflections", "chargesDrawn", "looseBallsRecovered", "boxOuts",
    # Tracking
    "speed", "distance", "touches", "passes", "secondaryAssists",
    # Misc
    "pointsOffTurnovers", "pointsSecondChance", "pointsFastBreak", "pointsPaint",
    # Scoring
    "pctFGA_2pt", "pctFGA_3pt", "pctPTS_2pt", "pctPTS_3pt", "pctAssisted",
})


def feature_timeseries(feature: str, window: str = "L5", days: int = 365) -> list[dict]:
    """Rolling-feature time series from the CURRENT feature_set_version.

    Since 2026-07-08 the weekly features build covers full history, so the
    pointer version alone serves the whole Explore horizon (a narrow build
    promoted by mistake would shrink this page again — keep the build
    date-unfiltered).

    Returns one row per game in the window with each side's rolling value
    (``HOME_<feature>_<window>`` / ``AWAY_<feature>_<window>``). The frontend picks
    home_value or away_value per selected team to build per-team series.

    ``feature`` is validated against ``_EXPLORE_FEATURES`` and ``window`` against
    {L5, L10}, so the interpolated column names are safe. Returns [] (not an error)
    if the column happens not to exist in this feature set.
    """
    if feature not in _EXPLORE_FEATURES:
        raise ValueError(f"unknown feature {feature!r}")
    if window not in ("L5", "L10"):
        raise ValueError("window must be 'L5' or 'L10'")

    home_col = f"HOME_{feature}_{window}"
    away_col = f"AWAY_{feature}_{window}"
    q = f"""
        SELECT DATE(GAME_DATE)              AS game_date,
               HOME_TEAM_NAME               AS home_team,
               AWAY_TEAM_NAME               AS away_team,
               `{home_col}`                 AS home_value,
               `{away_col}`                 AS away_value
        FROM features
        WHERE feature_set_version = (SELECT version FROM feature_set_current WHERE id = 1)
          AND GAME_DATE >= DATE_SUB(CURDATE(), INTERVAL :days DAY)
          -- Real franchises only: All-Star/exhibition squads carry non-franchise
          -- team ids. Filter on id, not name (features says "LA Clippers",
          -- nba_teams says "Los Angeles Clippers").
          AND HOME_TEAM_ID IN (SELECT id FROM nba_teams)
          AND AWAY_TEAM_ID IN (SELECT id FROM nba_teams)
        ORDER BY GAME_DATE ASC
    """
    try:
        with get_engine().connect() as conn:
            return _rows(conn.execute(sa.text(q), {"days": days}))
    except Exception as e:  # unknown column / empty feature set → degrade gracefully
        print(f"[explore] feature_timeseries failed for {home_col}: {e}")
        return []


# ---------------------------------------------------------------------------
# Data exploration: per-team-game scatter (Dash Tabs 1 & 3 port)
# ---------------------------------------------------------------------------

# Curated public-safe scatter stats -> their qualified column in the boxscore join.
# x/y are validated against these keys, so the interpolated SQL is injection-safe.
_SCATTER_COLUMNS: dict[str, str] = {
    # Traditional (the team game log itself)
    "PTS": "gl.PTS", "FGM": "gl.FGM", "FGA": "gl.FGA", "FG_PCT": "gl.FG_PCT",
    "FG3M": "gl.FG3M", "FG3A": "gl.FG3A", "FG3_PCT": "gl.FG3_PCT",
    "FTM": "gl.FTM", "FTA": "gl.FTA", "FT_PCT": "gl.FT_PCT",
    "OREB": "gl.OREB", "DREB": "gl.DREB", "REB": "gl.REB", "AST": "gl.AST",
    "STL": "gl.STL", "BLK": "gl.BLK", "TOV": "gl.TOV", "PF": "gl.PF",
    "PLUS_MINUS": "gl.PLUS_MINUS",
    # Four Factors
    "effectiveFieldGoalPercentage": "bff.effectiveFieldGoalPercentage",
    "freeThrowAttemptRate": "bff.freeThrowAttemptRate",
    "teamTurnoverPercentage": "bff.teamTurnoverPercentage",
    "offensiveReboundPercentage": "bff.offensiveReboundPercentage",
    # Player tracking
    "distance": "bpt.distance", "touches": "bpt.touches", "passes": "bpt.passes",
    "secondaryAssists": "bpt.secondaryAssists",
    # Hustle
    "contestedShots": "bsh.contestedShots", "deflections": "bsh.deflections",
    "chargesDrawn": "bsh.chargesDrawn", "screenAssists": "bsh.screenAssists",
    "boxOuts": "bsh.boxOuts",
    # Misc
    "pointsPaint": "bsm.pointsPaint", "pointsSecondChance": "bsm.pointsSecondChance",
    "pointsOffTurnovers": "bsm.pointsOffTurnovers",
    # Scoring
    "percentagePoints3pt": "bss.percentagePoints3pt",
    "percentageAssistedFGM": "bss.percentageAssistedFGM",
}

# LEFT JOIN clause per table alias (only the ones a request needs get joined).
_SCATTER_JOINS: dict[str, str] = {
    "bff": "LEFT JOIN boxscorefourfactorsv3_team bff ON gl.GAME_ID = bff.gameId AND gl.TEAM_ID = bff.teamId",
    "bpt": "LEFT JOIN boxscoreplayertrackv3_team bpt ON gl.GAME_ID = bpt.gameId AND gl.TEAM_ID = bpt.teamId",
    "bst": "LEFT JOIN boxscoretraditionalv3_team bst ON gl.GAME_ID = bst.gameId AND gl.TEAM_ID = bst.teamId",
    "bsh": "LEFT JOIN boxscorehustlev2_team bsh ON gl.GAME_ID = bsh.gameId AND gl.TEAM_ID = bsh.teamId",
    "bss": "LEFT JOIN boxscorescoringv3_team bss ON gl.GAME_ID = bss.gameId AND gl.TEAM_ID = bss.teamId",
    "bsm": "LEFT JOIN boxscoremiscv3_team bsm ON gl.GAME_ID = bsm.gameId AND gl.TEAM_ID = bsm.teamId",
}


def _parse_matchup(matchup, wl):
    """Derive (home, away, winner) team abbreviations from an NBA MATCHUP string.

    MATCHUP is "<team> vs. <opp>" when <team> is home, "<team> @ <opp>" when away;
    the left token is always this row's team, and WL says whether that team won.
    """
    m = (matchup or "").strip()
    if " vs. " in m:
        this_t, opp_t = [s.strip() for s in m.split(" vs. ", 1)]
        home, away = this_t, opp_t
    elif " @ " in m:
        this_t, opp_t = [s.strip() for s in m.split(" @ ", 1)]
        home, away = opp_t, this_t
    else:
        return None, None, None
    winner = this_t if wl == "W" else opp_t
    return home, away, winner


def scatter_data(x: str, y: str, days: int = 365) -> list[dict]:
    """One point per team-game: the chosen x/y stats, the team, win/loss, and the
    game's home/away/winning teams (derived from MATCHUP) for the hover tooltip.

    Replicates the Dash boxscore join, but only across the tables the requested
    columns need (+ bst for teamName). x/y are validated against _SCATTER_COLUMNS.
    """
    if x not in _SCATTER_COLUMNS or y not in _SCATTER_COLUMNS:
        raise ValueError("unknown x or y column")
    xq, yq = _SCATTER_COLUMNS[x], _SCATTER_COLUMNS[y]

    needed = {"bst"}  # always: teamName
    for expr in (xq, yq):
        alias = expr.split(".", 1)[0]
        if alias in _SCATTER_JOINS:
            needed.add(alias)
    joins = "\n        ".join(_SCATTER_JOINS[a] for a in sorted(needed))

    q = f"""
        SELECT DATE(gl.GAME_DATE) AS game_date, bst.teamName AS team, gl.WL AS wl,
               gl.MATCHUP AS matchup, {xq} AS x, {yq} AS y
        FROM game_list gl
        {joins}
        WHERE gl.GAME_DATE >= DATE_SUB(CURDATE(), INTERVAL :days DAY)
          AND {xq} IS NOT NULL AND {yq} IS NOT NULL
          -- Real franchises only (drops preseason internationals, All-Star and
          -- celebrity-game squads, which all carry non-franchise team ids).
          AND gl.TEAM_ID IN (SELECT id FROM nba_teams)
        ORDER BY gl.GAME_DATE ASC
    """
    try:
        with get_engine().connect() as conn:
            rows = _rows(conn.execute(sa.text(q), {"days": days}))
    except Exception as e:
        print(f"[explore] scatter_data failed for {xq},{yq}: {e}")
        return []
    # Split the MATCHUP string into home/away/winner (abbreviations) per point.
    for r in rows:
        r["home_team"], r["away_team"], r["winner"] = _parse_matchup(
            r.pop("matchup", None), r.get("wl")
        )
    return rows


# ---------------------------------------------------------------------------
# Injury report for a game date (public info — NBA publishes these pre-game)
# ---------------------------------------------------------------------------

def injury_report(game_date: str) -> list[dict]:
    """Pre-game injury report rows for one date, from historical_injury_report
    (NBA official PDFs; refreshed by the home-side scraper). Player names arrive
    as "Last, First" from the PDFs — flipped here so the site shows "First Last".
    """
    # Strict date validation — the only user input, never interpolated.
    from datetime import date as _date
    _date.fromisoformat(game_date)  # raises ValueError on junk -> 400 upstream

    q = """
        SELECT team_name, player_name, status, reason
        FROM historical_injury_report
        WHERE game_date = :d
        ORDER BY team_name, FIELD(status, 'Out', 'Doubtful', 'Questionable',
                                   'Probable', 'Available'), player_name
    """
    try:
        with get_engine().connect() as conn:
            rows = _rows(conn.execute(sa.text(q), {'d': game_date}))
    except Exception as e:
        print(f"[explore] injury_report failed for {game_date}: {e}")
        return []
    for r in rows:
        name = r.get('player_name') or ''
        if ',' in name:
            last, first = name.split(',', 1)
            r['player_name'] = f"{first.strip()} {last.strip()}"
    return rows


# ---------------------------------------------------------------------------
# Data exploration: feature correlations with winning margin (Dash Tab 5 port)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _features_columns() -> frozenset[str]:
    """Column names present in the features table (cached for the process)."""
    q = """
        SELECT COLUMN_NAME FROM information_schema.columns
        WHERE table_schema = DATABASE() AND table_name = 'features'
    """
    try:
        with get_engine().connect() as conn:
            return frozenset(r[0] for r in conn.execute(sa.text(q)))
    except Exception:
        return frozenset()


def _pearson(pairs: list[tuple[float, float]]) -> Optional[float]:
    """Pearson correlation over (x, y) pairs; None if undefined."""
    n = len(pairs)
    if n < 3:
        return None
    sx = sy = sxx = syy = sxy = 0.0
    for x, y in pairs:
        sx += x
        sy += y
        sxx += x * x
        syy += y * y
        sxy += x * y
    num = n * sxy - sx * sy
    den = ((n * sxx - sx * sx) * (n * syy - sy * sy)) ** 0.5
    return num / den if den else None


def margin_correlations(kind: str = "DIFF", window: str = "L5") -> list[dict]:
    """Pearson correlation of each curated rolling feature with TARGET_MARGIN.

    Returns the full curated set (one ``kind`` + ``window``, ~50 features) ranked by
    |correlation| — the frontend slices the top-N. Computed in pure Python over a
    bounded column set (no pandas/numpy in the API), then cached at the edge.
    """
    if kind not in ("DIFF", "HOME", "AWAY"):
        raise ValueError("kind must be DIFF, HOME, or AWAY")
    if window not in ("L5", "L10"):
        raise ValueError("window must be L5 or L10")

    existing = _features_columns()
    if "TARGET_MARGIN" not in existing:
        return []
    cols = [(feat, f"{kind}_{feat}_{window}") for feat in sorted(_EXPLORE_FEATURES)]
    cols = [(feat, c) for feat, c in cols if c in existing]
    if not cols:
        return []

    select = ", ".join(f"`{c}`" for _, c in cols)
    q = f"""
        SELECT {select}, TARGET_MARGIN
        FROM features
        WHERE feature_set_version = (SELECT version FROM feature_set_current WHERE id = 1)
          AND TARGET_MARGIN IS NOT NULL
    """
    try:
        with get_engine().connect() as conn:
            rows = conn.execute(sa.text(q)).mappings().all()
    except Exception as e:
        print(f"[explore] margin_correlations query failed: {e}")
        return []

    out: list[dict] = []
    for feat, c in cols:
        pairs = [
            (float(r[c]), float(r["TARGET_MARGIN"]))
            for r in rows
            if r[c] is not None and r["TARGET_MARGIN"] is not None
        ]
        corr = _pearson(pairs)
        if corr is not None:
            out.append({"feature": feat, "column": c, "correlation": round(corr, 4)})
    out.sort(key=lambda d: abs(d["correlation"]), reverse=True)
    return out


# ---------------------------------------------------------------------------
# Player explore (player_predictions + per-player boxscores)
# ---------------------------------------------------------------------------

_PLAYER_MODEL_TYPE = 'xgb_player'
_MIN_ISO_RE = _re.compile(r'PT(\d+)M([\d.]+)S')


def _parse_minutes(raw) -> Optional[float]:
    """Boxscore minutes text ('34:12' or 'PT34M12.00S') -> float minutes."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    m = _MIN_ISO_RE.match(s)
    if m:
        return round(float(m.group(1)) + float(m.group(2)) / 60, 2)
    if ':' in s:
        try:
            head, tail = s.split(':', 1)
            return round(float(head) + float(tail) / 60, 2)
        except ValueError:
            return None
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def player_directory() -> list[dict]:
    """Players that have model projections, tagged with their most recent team.

    Sourced from player_predictions (top-8 rotation players only), so the
    dropdowns never list deep-bench players the model does not project.
    """
    q = """
        SELECT person_id, player_name, team_id, team_abbrev
        FROM (
            SELECT person_id, player_name, team_id, team_abbrev,
                   ROW_NUMBER() OVER (
                       PARTITION BY person_id ORDER BY game_date DESC
                   ) AS _rn
            FROM player_predictions
            WHERE model_type = :mt
        ) x
        WHERE _rn = 1
        ORDER BY team_abbrev, player_name
    """
    with get_engine().connect() as conn:
        return _rows(conn.execute(sa.text(q), {'mt': _PLAYER_MODEL_TYPE}))


def player_gamelog(person_id: int, days: int = 1150) -> tuple[list[dict], Optional[str]]:
    """Per-game actual stats (last ~3 seasons) with the model's out-of-sample
    prediction attached where one exists. Public-safe: no model internals."""
    q = """
        SELECT g.GAME_DATE AS game_date,
               SUBSTRING_INDEX(g.MATCHUP, ' ', -1) AS opp,
               CASE WHEN POSITION(' vs. ' IN g.MATCHUP) > 0 THEN 1 ELSE 0 END AS is_home,
               p.minutes AS _raw_minutes,
               p.points AS pts, p.reboundsTotal AS reb, p.assists AS ast,
               p.steals AS stl, p.blocks AS blk, p.turnovers AS tov,
               p.threePointersMade AS fg3m, p.threePointersAttempted AS fg3a,
               p.freeThrowsMade AS ftm, p.freeThrowsAttempted AS fta,
               p.foulsPersonal AS pf,
               pp.pred_min, pp.pred_pts, pp.pred_reb, pp.pred_ast, pp.pred_stl,
               pp.pred_blk, pp.pred_tov, pp.pred_fg3m, pp.pred_fg3a, pp.pred_ftm,
               pp.pred_fta
        FROM boxscoretraditionalv3_player p
        JOIN game_list g ON g.GAME_ID = p.gameId AND g.TEAM_ID = p.teamId
        LEFT JOIN (
            SELECT game_id, person_id,
                   pred_min, pred_pts, pred_reb, pred_ast, pred_stl, pred_blk,
                   pred_tov, pred_fg3m, pred_fg3a, pred_ftm, pred_fta,
                   ROW_NUMBER() OVER (
                       PARTITION BY game_id, person_id
                       ORDER BY prediction_timestamp DESC
                   ) AS _rn
            FROM player_predictions
            WHERE model_type = :mt AND person_id = :pid
        ) pp ON pp.game_id = p.gameId AND pp.person_id = p.personId AND pp._rn = 1
        WHERE p.personId = :pid
          AND COALESCE(p.minutes, '') <> ''  -- exclude DNP rows
          AND g.GAME_DATE >= DATE_SUB(CURDATE(), INTERVAL :days DAY)
        ORDER BY g.GAME_DATE
    """
    name_q = """
        SELECT player_name FROM player_predictions
        WHERE person_id = :pid ORDER BY game_date DESC LIMIT 1
    """
    with get_engine().connect() as conn:
        rows = _rows(conn.execute(
            sa.text(q), {'pid': person_id, 'mt': _PLAYER_MODEL_TYPE, 'days': days}))
        name = conn.execute(sa.text(name_q), {'pid': person_id}).scalar()
    for r in rows:
        r['min'] = _parse_minutes(r.pop('_raw_minutes'))
    return rows, name


def _team_profile(conn, team_id: int) -> Optional[dict]:
    """Rolling last-10-games profile for a team (advanced + volume stats)."""
    q_adv = """
        SELECT AVG(x.pace) AS pace, AVG(x.offensiveRating) AS off_rtg,
               AVG(x.defensiveRating) AS def_rtg,
               AVG(x.offensiveReboundPercentage) AS oreb_pct,
               AVG(x.defensiveReboundPercentage) AS dreb_pct,
               AVG(x.effectiveFieldGoalPercentage) AS efg_pct,
               AVG(x.assistPercentage) AS ast_pct
        FROM (
            SELECT t.pace, t.offensiveRating, t.defensiveRating,
                   t.offensiveReboundPercentage, t.defensiveReboundPercentage,
                   t.effectiveFieldGoalPercentage, t.assistPercentage
            FROM boxscoreadvancedv3_team t
            JOIN game_list g ON g.GAME_ID = t.gameId AND g.TEAM_ID = t.teamId
            WHERE t.teamId = :tid
            ORDER BY g.GAME_DATE DESC
            LIMIT 10
        ) x
    """
    q_vol = """
        SELECT AVG(x.FG3A) AS fg3a_pg, AVG(x.FTA) AS fta_pg, AVG(x.PTS) AS pts_pg,
               MAX(x.TEAM_ABBREVIATION) AS team_abbrev
        FROM (SELECT FG3A, FTA, PTS, TEAM_ABBREVIATION FROM game_list
              WHERE TEAM_ID = :tid ORDER BY GAME_DATE DESC LIMIT 10) x
    """
    adv = conn.execute(sa.text(q_adv), {'tid': team_id}).mappings().first()
    vol = conn.execute(sa.text(q_vol), {'tid': team_id}).mappings().first()
    if adv is None or adv['pace'] is None:
        return None
    out = {'team_id': team_id}
    for src in (adv, vol):
        for k, v in dict(src).items():
            # AVG() over MySQL ints comes back as Decimal — normalize to float.
            out[k] = v if v is None or isinstance(v, str) else round(float(v), 2)
    return out


def _next_game(conn, team_id: int) -> Optional[dict]:
    """Next scheduled game for a team from league_schedule (None offseason /
    if the schedule table is missing)."""
    q = """
        SELECT gameDate, homeTeam_teamId, awayTeam_teamId,
               homeTeam_teamTricode, awayTeam_teamTricode
        FROM league_schedule
        WHERE (homeTeam_teamId = :tid OR awayTeam_teamId = :tid)
          AND gameDate >= CURDATE()
        ORDER BY gameDate
        LIMIT 1
    """
    try:
        row = conn.execute(sa.text(q), {'tid': team_id}).mappings().first()
    except Exception as e:
        print(f"[players] next_game lookup failed: {e}")
        return None
    if row is None:
        return None
    is_home = int(row['homeTeam_teamId']) == int(team_id)
    return {
        'game_date': str(row['gameDate'])[:10],
        'is_home': is_home,
        'opp_team_id': int(row['awayTeam_teamId'] if is_home else row['homeTeam_teamId']),
        'opp_abbrev': row['awayTeam_teamTricode'] if is_home else row['homeTeam_teamTricode'],
    }


def player_team_context(team_id: int) -> Optional[dict]:
    """L10 profile for the player's team, plus the next opponent's profile
    when a scheduled game exists (offseason: next_game/opponent are null)."""
    with get_engine().connect() as conn:
        team = _team_profile(conn, team_id)
        if team is None:
            return None
        nxt = _next_game(conn, team_id)
        opp = _team_profile(conn, nxt['opp_team_id']) if nxt else None
    return {'team': team, 'next_game': nxt, 'opponent': opp}


# Public columns for the daily projections table. model_version / model_type
# and game_id stay internal (public-safe policy).
_PLAYER_PRED_PUBLIC_COLS = """
    game_date, person_id, player_name, team_abbrev, opp_abbrev, is_home,
    team_pace_l10, opp_pace_l10, opp_drtg_l10, opp_3pa_allowed_l10,
    pred_min, pred_pts, pred_reb, pred_ast, pred_stl, pred_blk, pred_tov,
    pred_fg3m, pred_fg3a, pred_ftm, pred_fta,
    actual_min, actual_pts, actual_reb, actual_ast, actual_stl, actual_blk,
    actual_tov, actual_fg3m, actual_fg3a, actual_ftm, actual_fta
"""


def latest_player_prediction_date() -> Optional[str]:
    """Most recent game_date with player projections. None if table empty."""
    q = "SELECT MAX(game_date) AS d FROM player_predictions WHERE model_type = :mt"
    with get_engine().connect() as conn:
        d = conn.execute(sa.text(q), {'mt': _PLAYER_MODEL_TYPE}).scalar()
    return d.isoformat() if d is not None else None


def player_predictions_for_date(game_date: str) -> list[dict]:
    """One row per (game, player) for a date's slate — most recent model
    version wins (weekly retrains coexist with the walk-forward backfill).
    actual_* are null until the game is graded."""
    from datetime import date as _date
    _date.fromisoformat(game_date)  # raises ValueError on junk
    q = f"""
        SELECT {_PLAYER_PRED_PUBLIC_COLS}
        FROM (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY game_id, person_id
                       ORDER BY prediction_timestamp DESC
                   ) AS _rn
            FROM player_predictions
            WHERE model_type = :mt AND game_date = :d
        ) x
        WHERE _rn = 1
        ORDER BY pred_pts DESC
    """
    with get_engine().connect() as conn:
        return _rows(conn.execute(sa.text(q), {'mt': _PLAYER_MODEL_TYPE, 'd': game_date}))


def player_season_averages(min_gp: int = 15) -> tuple[Optional[str], list[dict]]:
    """(season_label, rows) — per-player per-game averages for the most recent
    season, actual results from boxscores (not model output). Grounds the
    advisor's season tier: trades, keeper/draft questions, players without a
    slate projection, and the whole offseason.

    Season = games sharing the latest SEASON_ID year digit(s); regular season,
    playoffs, play-in and Cup count (type digits 2/4/5/6 — preseason and
    All-Star excluded, same set as PREDICTABLE_GID_TYPES). Universe: players
    with >= min_gp games; early in a season, when nobody clears 15 GP yet, the
    caller's fallback re-query with a lower bar keeps the tier populated.
    """
    yr_q = """
        SELECT MAX(RIGHT(CAST(SEASON_ID AS CHAR), 4)) FROM game_list
        WHERE LEFT(CAST(SEASON_ID AS CHAR), 1) IN ('2','4','5','6')
    """
    # Single scan of the season's boxscore rows: averages via GROUP BY, and the
    # player's latest name/team via MAX(CONCAT(date, ...)) instead of a second
    # windowed pass — a two-reference CTE materializes twice and was ~2x slower.
    q = """
        SELECT person_id, COUNT(*) AS gp,
               AVG(min_num) AS min_avg, AVG(points) AS pts_avg,
               AVG(reboundsTotal) AS reb_avg, AVG(assists) AS ast_avg,
               AVG(steals) AS stl_avg, AVG(blocks) AS blk_avg,
               AVG(turnovers) AS tov_avg,
               AVG(threePointersMade) AS fg3m_avg,
               100 * SUM(fieldGoalsMade) / NULLIF(SUM(fieldGoalsAttempted), 0) AS fg_pct,
               100 * SUM(freeThrowsMade) / NULLIF(SUM(freeThrowsAttempted), 0) AS ft_pct,
               MAX(CONCAT(DATE_FORMAT(game_date, '%Y%m%d'), '|',
                          player_name, '|', team_abbrev)) AS _latest
        FROM (
            SELECT p.personId AS person_id,
                   CONCAT(p.firstName, ' ', p.familyName) AS player_name,
                   p.teamTricode AS team_abbrev,
                   g.GAME_DATE AS game_date,
                   CASE
                       WHEN p.minutes LIKE 'PT%' THEN
                           CAST(SUBSTRING_INDEX(SUBSTRING(p.minutes, 3), 'M', 1) AS DECIMAL(8,3))
                           + CAST(REPLACE(SUBSTRING_INDEX(p.minutes, 'M', -1), 'S', '') AS DECIMAL(8,3)) / 60
                       WHEN p.minutes LIKE '%:%' THEN
                           CAST(SUBSTRING_INDEX(p.minutes, ':', 1) AS DECIMAL(8,3))
                           + CAST(SUBSTRING_INDEX(p.minutes, ':', -1) AS DECIMAL(8,3)) / 60
                       ELSE CAST(p.minutes AS DECIMAL(8,3))
                   END AS min_num,
                   p.points, p.reboundsTotal, p.assists, p.steals, p.blocks,
                   p.turnovers, p.threePointersMade,
                   p.fieldGoalsMade, p.fieldGoalsAttempted,
                   p.freeThrowsMade, p.freeThrowsAttempted
            FROM boxscoretraditionalv3_player p
            JOIN game_list g ON g.GAME_ID = p.gameId AND g.TEAM_ID = p.teamId
            WHERE RIGHT(CAST(g.SEASON_ID AS CHAR), 4) = :yr
              AND LEFT(CAST(g.SEASON_ID AS CHAR), 1) IN ('2','4','5','6')
              AND COALESCE(p.minutes, '') <> ''  -- exclude DNP rows
        ) season_games
        GROUP BY person_id
        HAVING COUNT(*) >= :min_gp
    """
    with get_engine().connect() as conn:
        yr = conn.execute(sa.text(yr_q)).scalar()
        if yr is None:
            return None, []
        rows = _rows(conn.execute(sa.text(q), {'yr': yr, 'min_gp': min_gp}))
    # AVG()/division return Decimal — coerce so formatters treat them as numbers.
    num_cols = ('min_avg', 'pts_avg', 'reb_avg', 'ast_avg', 'stl_avg',
                'blk_avg', 'tov_avg', 'fg3m_avg', 'fg_pct', 'ft_pct')
    for r in rows:
        for k in num_cols:
            r[k] = float(r[k]) if r[k] is not None else None
        _, r['player_name'], r['team_abbrev'] = r.pop('_latest').split('|', 2)
    rows.sort(key=lambda r: (r['team_abbrev'], r['player_name']))
    label = f"{yr}-{(int(yr) + 1) % 100:02d}"  # '2025' -> '2025-26'
    return label, rows
