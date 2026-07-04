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
        return _rows(conn.execute(sa.text(q), params))


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
    return rows


def accuracy_summary(days: int = 30, model_type: Optional[str] = None) -> list[dict]:
    """Aggregate accuracy over the last ``days`` of completed games, per model.

    Mirrors modeling/prediction_tracker.get_prediction_accuracy so the public
    numbers match the internal dashboard. Only games with actual_winner set
    (i.e. already played and backfilled) count.
    """
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
    FROM model_predictions
    WHERE actual_winner IS NOT NULL
      AND game_date >= DATE_SUB(CURDATE(), INTERVAL :days DAY)
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
    q = """
    SELECT
        game_date,
        model_type,
        COUNT(*)                                        AS n_games,
        AVG(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) AS accuracy,
        AVG(margin_error)                               AS mae
    FROM model_predictions
    WHERE actual_winner IS NOT NULL
      AND game_date >= DATE_SUB(CURDATE(), INTERVAL :days DAY)
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
