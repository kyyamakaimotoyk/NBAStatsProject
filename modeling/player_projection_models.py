"""P1 — models for player counting-stat projection.

Three predictors, all emitting the same interface (DataFrame of pred_{stat}):

  naive   — player's L10 per-game average (sanity floor)
  marcel  — Marcel-style shrinkage: blended per-36 rates (L10 / season /
            prior season) regressed toward the league mean, x projected
            minutes. The must-beat baseline.
  xgb     — approved production candidate: two-stage XGBoost.
            Stage 1: minutes regressor. Stage 2: per-36 rate models
            (squared error, minutes-weighted) for PTS/REB/AST and
            Poisson-with-exposure models (base_margin = log(min/36)) for
            STL/BLK/TOV/3PA/FTA. 3PM/FTM are derived as attempts x
            shrunken season make-rate, guaranteeing makes <= attempts.
"""
import numpy as np
import pandas as pd
import xgboost as xgb

SEED = 42
TARGETS = ['MIN', 'PTS', 'REB', 'AST', 'STL', 'BLK', 'TOV', 'FG3M', 'FG3A', 'FTM', 'FTA']
STAT_COLS = TARGETS[1:]
RATE_STATS = ['PTS', 'REB', 'AST']                  # squared error on per-36 rate
POISSON_STATS = ['STL', 'BLK', 'TOV', 'FG3A', 'FTA']  # count:poisson with exposure
DERIVED = {'FG3M': ('FG3A', 'SHRUNK_3P_PCT'), 'FTM': ('FTA', 'SHRUNK_FT_PCT')}

_EXPLICIT_FEATURES = [
    'MIN_STD_L10', 'MIN_TREND', 'STARTS_SHARE_L10', 'GP_SEASON', 'MIN_SEASON_AVG',
    'MIN_PREV_GAME', 'CUM_MIN_LAST3',   # P4 heavy-legs (2026-07-16, §P4)
    'SHRUNK_3P_PCT', 'SHRUNK_FT_PCT', 'PREV_SEASON_MIN',
    'PLAYER_REST_DAYS', 'LONG_ABSENCE_RETURN', 'MISSED_GAMES_SEASON',
    'N_REGULARS_OUT', 'VACATED_MIN', 'VACATED_USG', 'MIN_RANK',
    'IS_HOME', 'IS_PLAYOFF', 'TEAM_REST_DAYS', 'TEAM_IS_B2B', 'TEAM_GAMES_LAST7',
    'OPP_REST_DAYS', 'OPP_IS_B2B', 'OPP_GAMES_LAST7',
    'TEAM_SPREAD', 'ABS_SPREAD', 'GAME_TOTAL', 'TEAM_IMPLIED_TOTAL',
    'EXPECTED_POSS', 'EXPECTED_USG_POSS',
]
_SUFFIXES = ('_L5', '_L10', '_TREND', '36_SEASON')


def feature_columns(df):
    """Whitelist of leakage-safe feature columns (never same-game stats)."""
    cols = []
    for c in df.columns:
        if c in _EXPLICIT_FEATURES:
            cols.append(c)
        elif c.endswith(_SUFFIXES) and not c.endswith('_36G'):
            cols.append(c)
        elif c.startswith('PREV_') and c.endswith('36'):
            cols.append(c)
    return sorted(set(cols))


def _nan_weighted(cols, weights):
    """Row-wise weighted mean over columns, renormalizing over non-NaN."""
    vals = np.stack([c.to_numpy(dtype=float) for c in cols], axis=1)
    w = np.asarray(weights, dtype=float)[None, :].repeat(len(vals), axis=0)
    w = np.where(np.isnan(vals), 0.0, w)
    tot = w.sum(axis=1)
    out = np.where(tot > 0, np.nansum(vals * w, axis=1) / np.where(tot == 0, 1, tot), np.nan)
    return out


class NaiveBaseline:
    def fit(self, train):
        return self

    def predict(self, df):
        out = pd.DataFrame(index=df.index)
        out['pred_MIN'] = df['MIN_L10']
        for s in STAT_COLS:
            out[f'pred_{s}'] = df[f'{s}_L10']
        return out


class MarcelBaseline:
    """Blended per-36 rates shrunk toward the (minutes-weighted) league mean."""

    MIN_W = [0.5, 0.3, 0.2]      # MIN_L5, MIN_L10, MIN_SEASON_AVG
    RATE_W = [0.45, 0.35, 0.20]  # s36_L10, s36_SEASON, PREV_s36
    SHRINK_GP = 10               # alpha = GP / (GP + SHRINK_GP)

    def fit(self, train):
        self.league36 = {}
        w = train['MIN'].to_numpy(dtype=float)
        for s in STAT_COLS:
            v = train[f'{s}_36G'].to_numpy(dtype=float)
            m = ~np.isnan(v)
            self.league36[s] = float(np.average(v[m], weights=w[m]))
        return self

    def predict(self, df):
        out = pd.DataFrame(index=df.index)
        pred_min = _nan_weighted(
            [df['MIN_L5'], df['MIN_L10'], df['MIN_SEASON_AVG']], self.MIN_W)
        out['pred_MIN'] = np.clip(pred_min, 0, 48)
        alpha = (df['GP_SEASON'] / (df['GP_SEASON'] + self.SHRINK_GP)).to_numpy(dtype=float)
        for s in STAT_COLS:
            rate = _nan_weighted(
                [df[f'{s}36_L10'], df[f'{s}36_SEASON'], df[f'PREV_{s}36']], self.RATE_W)
            rate = np.where(np.isnan(rate), self.league36[s], rate)
            shrunk = alpha * rate + (1 - alpha) * self.league36[s]
            out[f'pred_{s}'] = out['pred_MIN'] * shrunk / 36.0
        out['pred_FG3M'] = np.minimum(out['pred_FG3M'], out['pred_FG3A'])
        out['pred_FTM'] = np.minimum(out['pred_FTM'], out['pred_FTA'])
        return out


def _xgb_params(objective):
    return dict(objective=objective, n_estimators=300, max_depth=5,
                learning_rate=0.05, min_child_weight=20, subsample=0.8,
                colsample_bytree=0.8, reg_lambda=1.0, random_state=SEED,
                n_jobs=-1, tree_method='hist')


# P7/P7b (2026-07-17, tuning log §P7 + addendum): the first HP search found a
# heavily-regularized config that beats the P1 hand-set params on 9/11 stats
# (PTS −0.033, MIN −0.019 MAE) but regresses BLK — so it is adopted PER
# SUBMODEL: 'default' applies to the minutes head and every stat head except
# those with their own key; BLK's empty dict keeps the incumbent _xgb_params.
# Gate evidence: outputs/p7b_gate.json (3 folds × 3 seeds, zero regressions).
# Revert = set this dict to {}.
# NOTE for experiments: harness HP arms that monkeypatch _xgb_params should
# also clear/patch this dict, or their overrides will be layered UNDER it.
_PER_MODEL_HP_OVERRIDES = {
    'default': {
        'n_estimators': 350, 'max_depth': 4,
        'learning_rate': 0.02564888603022094, 'min_child_weight': 19,
        'subsample': 0.666016060577559, 'colsample_bytree': 0.8280441108448228,
        'reg_lambda': 21.34660167854208, 'reg_alpha': 7.97486168468657,
    },
    'BLK': {},
}


def _params_for(model_name, objective):
    """Production params for one of the 9 submodels ('MIN' or a stat name)."""
    override = _PER_MODEL_HP_OVERRIDES.get(
        model_name, _PER_MODEL_HP_OVERRIDES.get('default', {}))
    return {**_xgb_params(objective), **override}


class TwoStageXGB:
    """Minutes model + per-36 rate / Poisson-exposure stat models."""

    def __init__(self):
        self.features = None
        self.min_model = None
        self.rate_models = {}
        self.poisson_models = {}

    def fit(self, train):
        self.features = feature_columns(train)
        X = train[self.features].astype(float)

        self.min_model = xgb.XGBRegressor(**_params_for('MIN', 'reg:squarederror'))
        self.min_model.fit(X, train['MIN'])

        played = train['MIN'] >= 4
        Xp, tp = X[played], train[played]
        for s in RATE_STATS:
            y = tp[f'{s}_36G']
            m = y.notna()
            model = xgb.XGBRegressor(**_params_for(s, 'reg:squarederror'))
            model.fit(Xp[m], y[m], sample_weight=tp['MIN'][m])
            self.rate_models[s] = model
        offset = np.log(tp['MIN'] / 36.0)
        for s in POISSON_STATS:
            model = xgb.XGBRegressor(**_params_for(s, 'count:poisson'))
            model.fit(Xp, tp[s], base_margin=offset)
            self.poisson_models[s] = model
        return self

    def predict(self, df, actual_minutes=False):
        X = df[self.features].astype(float)
        out = pd.DataFrame(index=df.index)
        pred_min = np.clip(self.min_model.predict(X), 0.5, 48.0)
        out['pred_MIN'] = pred_min
        minutes = df['MIN'].to_numpy(dtype=float) if actual_minutes else pred_min
        minutes = np.clip(minutes, 0.5, 48.0)
        offset = np.log(minutes / 36.0)
        for s in RATE_STATS:
            rate = np.clip(self.rate_models[s].predict(X), 0, None)
            out[f'pred_{s}'] = rate * minutes / 36.0
        for s in POISSON_STATS:
            out[f'pred_{s}'] = np.clip(
                self.poisson_models[s].predict(X, base_margin=offset), 0, None)
        for made, (att, pct_col) in DERIVED.items():
            out[f'pred_{made}'] = out[f'pred_{att}'] * df[pct_col].to_numpy(dtype=float)
        return out

    def importances(self, top_n=20):
        """Top gain-importance features per model, for the report."""
        result = {}
        models = {'MIN': self.min_model, **self.rate_models, **self.poisson_models}
        for name, model in models.items():
            imp = pd.Series(model.feature_importances_, index=self.features)
            result[name] = imp.sort_values(ascending=False).head(top_n).round(4).to_dict()
        return result


MODELS = {'naive': NaiveBaseline, 'marcel': MarcelBaseline, 'xgb': TwoStageXGB}
