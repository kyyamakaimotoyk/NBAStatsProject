"""Single source of truth for model-feature selection from the nba_ml_features.csv.

Three sites used to maintain their own copy of the pattern list:
  - data_engineering/feature_engineering.py::prepare_ml_dataset (CSV writer)
  - modeling/predict_games.py::_prepare_training_data           (production training)
  - experiments/e2_walk_forward.py::select_feature_columns      (validation)

That triplet drifted: E9 added ELO patterns to the CSV writer but not the trainer
or validator, so HOME_ELO/AWAY_ELO/ELO_DIFF/ELO_P_HOME columns shipped to the CSV
and were silently filtered out before reaching the model. Same with E11 LINEUP.
Discovered 2026-05-19 when E11 walk-forward returned bit-identical numbers to E10.

This module collapses the three lists into one. Use:

    from core.features import select_features
    feature_cols = select_features(df.columns)            # full default set
    feature_cols = select_features(df.columns, enable_e9=False)  # ablation toggle

When adding a new feature column to the CSV:
  - If it's a *_L5 / *_L10 rolling stat, no change needed (caught by BASE_PATTERNS).
  - Otherwise: add its pattern to BASE_PATTERNS or to the relevant experiment list
    below.
"""
from __future__ import annotations
import re
from typing import Iterable


# ----------------------------------------------------------------------------
# Always-on patterns (every model run regardless of ablation toggles)
# ----------------------------------------------------------------------------
BASE_PATTERNS: tuple = (
    # Rolling box-score stats. Catches PTS_L10, EFG_PCT_L5, etc.
    # ALSO catches E10's OPP_ADJ_*_L10 and *_ALLOWED_L10 via the substring match.
    '_L5', '_L10',

    # Streaks / records
    'STREAK', 'REST_DAYS', 'WIN_PCT',

    # Fatigue / schedule density
    'IS_BACK_TO_BACK', 'IS_3_IN_4_NIGHTS', 'GAMES_LAST',
    'AVG_REST_LAST', 'ROAD_TRIP_LENGTH',

    # Player projection features (additive — sum of per-player projections)
    'PROJ_PTS_FROM_PLAYERS', 'PROJ_REB_FROM_PLAYERS', 'PROJ_AST_FROM_PLAYERS',
    'WEIGHTED_AVG_USAGE', 'WEIGHTED_AVG_TS_PCT', 'WEIGHTED_AVG_PIE',
    'ROSTER_DEPTH_SCORE', 'STAR_PLAYER_IMPACT', 'TOP_3_SCORER_SHARE',

    # Player slot model (E7-aware via _AVAILABLE column values, but the column
    # NAMES are E7-independent)
    '_SLOT_', '_IMPACT', '_AVAILABLE',
    'TOTAL_AVAILABLE_IMPACT', 'TOTAL_MISSING_IMPACT', 'PLAYERS_OUT',
)


# ----------------------------------------------------------------------------
# Experiment-specific patterns (toggleable for ablation)
# ----------------------------------------------------------------------------

# E9: ELO ratings (joined from team_elo_pregame)
E9_ELO_PATTERNS: tuple = ('HOME_ELO', 'AWAY_ELO', 'ELO_DIFF', 'ELO_P_HOME')

# E11: 5-man lineup snapshots (joined from team_lineup_snapshots)
E11_LINEUP_PATTERNS: tuple = ('LINEUP_',)

# Track A: playoff series-context (joined from playoff_series_context). Zero for
# non-playoff games, so harmless to regular-season models; only "activates" in the
# postseason. Under evaluation (playoff-improvement plan) — kept on by default once
# the CSV carries them; the keep/drop decision is gated on the Track-A ablation.
SERIES_PATTERNS: tuple = ('SERIES_', 'FACES_ELIM', 'HAS_HCA')

# E10: opponent-strength-adjusted rolling stats. These have names like
# HOME_OPP_ADJ_PTS_L10 / AWAY_PTS_ALLOWED_L10 — both end in `_L10` so they
# are caught by BASE_PATTERNS. To disable E10 we POST-FILTER by regex.
E10_OPP_ADJ_REGEX = re.compile(r'(OPP_ADJ_|_ALLOWED_L10)')


# ----------------------------------------------------------------------------
# E7 NOTE: E7 (pre-game injury data) is a *data-source* toggle, not a feature-
# pattern toggle. The column NAMES are identical whether _AVAILABLE comes from
# the historical_injury_report table (E7-on) or from postgame boxscores
# (E7-off). Therefore E7 cannot be toggled from this module — it requires a
# separate CSV built with availability_source='postgame'.
# ----------------------------------------------------------------------------


# ----------------------------------------------------------------------------
# Production defaults (set by the E3 noise-aware ablation, 2026-05-19)
# ----------------------------------------------------------------------------
# E3 results (docs/e3_ablation_report.md) found that on the W5 walk-forward
# test set with 10 seeds × 1000 bootstrap resamples:
#   - E9 (ELO):           SIGNIFICANT AUC gain on RF (p=0.012-0.016)
#   - E10 (OPP_ADJ):      SIGNIFICANT MAE REGRESSION on RF (p=0.011-0.023)
#                         and AUC regression on XGB in some combos
#   - E11 (LINEUP):       NO significant improvement on any model
# Hence the production defaults below: E9 on, E10 + E11 off.
# Override via the kwargs for ablation experiments.
ENABLE_E9_DEFAULT = True
ENABLE_E10_DEFAULT = False
ENABLE_E11_DEFAULT = False
ENABLE_SERIES_DEFAULT = False  # Track A: E17 ablation found NO significant playoff gain
                               # (RF dAUC -0.014, XGB McNemar 26/26, all CIs cross zero).
                               # Build/table retained for re-eval as playoff data grows;
                               # off in production. See docs/playoff_improvement_plan.md.


def get_active_patterns(*, enable_e9: bool = ENABLE_E9_DEFAULT,
                        enable_e11: bool = ENABLE_E11_DEFAULT,
                        enable_series: bool = ENABLE_SERIES_DEFAULT) -> tuple:
    """Return the substring-pattern tuple for the given ablation config.

    E10 isn't here because it's toggled via post-filter regex (see select_features).
    E7 isn't here because it's a CSV-level toggle, not a column-selection one.
    """
    patterns = list(BASE_PATTERNS)
    if enable_e9:
        patterns.extend(E9_ELO_PATTERNS)
    if enable_e11:
        patterns.extend(E11_LINEUP_PATTERNS)
    if enable_series:
        patterns.extend(SERIES_PATTERNS)
    return tuple(patterns)


def select_features(
    df_columns: Iterable[str],
    *,
    enable_e9: bool = ENABLE_E9_DEFAULT,
    enable_e10: bool = ENABLE_E10_DEFAULT,
    enable_e11: bool = ENABLE_E11_DEFAULT,
    enable_series: bool = ENABLE_SERIES_DEFAULT,
) -> list:
    """Select model-feature columns from df.columns given experiment toggles.

    Defaults reflect the E3 noise-aware ablation decision: E9 on, E10/E11 off.
    Track-A series-context on by default (harmless to regular season). See
    docs/e3_ablation_report.md and docs/playoff_improvement_plan.md.

    PLAYER_ID columns are always excluded (they're for embedding/SHAP, not as
    direct RF/XGB/NN inputs).
    """
    patterns = get_active_patterns(enable_e9=enable_e9, enable_e11=enable_e11,
                                   enable_series=enable_series)
    cols = [c for c in df_columns if any(p in c for p in patterns)]
    cols = [c for c in cols if 'PLAYER_ID' not in c]

    if not enable_e10:
        cols = [c for c in cols if not E10_OPP_ADJ_REGEX.search(c)]

    return cols


def assert_features_present(df_columns: Iterable[str],
                            *, require_e9: bool = ENABLE_E9_DEFAULT,
                            require_e11: bool = ENABLE_E11_DEFAULT) -> None:
    """Sanity check: fail loud if the CSV is missing patterns we expect.

    Call this at training time. Without it, a missing CSV column would just
    silently shrink the model's input vector — the bug class that motivated
    this module.
    """
    cols = set(df_columns)

    def has_match(pattern: str) -> bool:
        return any(pattern in c for c in cols)

    missing = []
    if require_e9:
        for p in E9_ELO_PATTERNS:
            if not has_match(p):
                missing.append(f'E9:{p}')
    if require_e11:
        for p in E11_LINEUP_PATTERNS:
            if not has_match(p):
                missing.append(f'E11:{p}')

    if missing:
        raise RuntimeError(
            f"select_features check failed: CSV missing expected feature patterns: "
            f"{missing}. Either rebuild the CSV with the corresponding "
            f"_join_*_features calls or pass enable_e9=False / enable_e11=False."
        )
