"""
E17 (Track A eval) — Do playoff series-context features help?

Critical design point: series features are 0 for regular-season games, so a model
must TRAIN ON PLAYOFFS to learn them. So unlike E15 (regular-only train), here we
train on ALL games (regular + prior-season playoffs) strictly before each test
season's playoffs, then test on that season's playoffs. Series features for training
playoff games use only earlier games of the same series (no leakage), and those games
are from seasons before the test season (no cross-season leakage).

Paired comparison, same train rows / seeds, only the feature set differs:
  - WITHOUT series: select_features(enable_series=False)
  - WITH series:    select_features(enable_series=True)
Pooled across seasons (first seed for paired tests; all seeds for stability).
Tests: McNemar (accuracy), paired-t on |error| (MAE), bootstrap AUC delta.
Vegas metrics on the same games shown for ceiling context (~0.65 AUC from E16).

Note: 2022 has no prior playoffs in training -> series features inert that season;
we also report pooled-excluding-2022.

Usage:
    python experiments/e17_series_eval.py --seeds 5
"""
from __future__ import annotations
try:
    import torch  # noqa
except Exception:
    pass
import sys as _sys, os as _os
_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _PROJECT_ROOT)
if _os.getcwd() != _PROJECT_ROOT:
    _os.chdir(_PROJECT_ROOT)

import argparse, json
from datetime import datetime
import numpy as np
import pandas as pd
from scipy import stats as scistats
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import roc_auc_score
import xgboost as xgb
from sqlalchemy import text
from core.db import get_engine
from core.features import select_features

SEEDS = [42, 123, 456, 789, 1000, 2024, 31337, 65535, 8675309, 99999]
RF_CLF = {'n_estimators': 100, 'max_depth': 5, 'min_samples_leaf': 20}
RF_REG = {'n_estimators': 100, 'max_depth': 5, 'min_samples_leaf': 20}
XGB_CLF = {'n_estimators': 200, 'max_depth': 4, 'learning_rate': 0.1, 'min_child_weight': 10,
           'subsample': 0.8, 'colsample_bytree': 0.8, 'reg_lambda': 1.0, 'eval_metric': 'logloss'}
XGB_REG = {'n_estimators': 200, 'max_depth': 4, 'learning_rate': 0.1, 'min_child_weight': 10,
           'subsample': 0.8, 'colsample_bytree': 0.8, 'reg_lambda': 1.0}


def load():
    df = pd.read_csv('nba_ml_features.csv')
    df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE']); df['GAME_ID'] = df['GAME_ID'].astype('int64')
    eng = get_engine()
    gl = pd.read_sql(text('SELECT DISTINCT GAME_ID, SEASON_ID FROM game_list'), eng)
    gl['GAME_ID'] = gl['GAME_ID'].astype('int64')
    gl['regime'] = gl['SEASON_ID'].astype(str).str[0].map(
        {'2': 'regular', '4': 'playoffs', '5': 'playin', '3': 'allstar', '1': 'preseason', '6': 'cup'})
    df = df.merge(gl[['GAME_ID', 'regime']], on='GAME_ID', how='left')
    vl = pd.read_sql(text('SELECT game_id, source, home_spread FROM vegas_lines WHERE home_spread IS NOT NULL AND game_id IS NOT NULL'), eng)
    vl['game_id'] = vl['game_id'].astype('int64')
    vl['pri'] = vl['source'].map({'espn_draftkings': 0, 'kaggle_sbr': 1, 'espn_consensus': 2}).fillna(9)
    vl = vl.sort_values('pri').drop_duplicates('game_id', keep='first')
    df = df.merge(vl[['game_id', 'home_spread']].rename(columns={'game_id': 'GAME_ID'}), on='GAME_ID', how='left')
    return df


def make(model, seed):
    if model == 'RF':
        return RandomForestClassifier(**RF_CLF, random_state=seed, n_jobs=-1), RandomForestRegressor(**RF_REG, random_state=seed, n_jobs=-1)
    return xgb.XGBClassifier(**XGB_CLF, random_state=seed, n_jobs=-1), xgb.XGBRegressor(**XGB_REG, random_state=seed, n_jobs=-1)


def predict_config(df, fc, tr, cal, test, model, seed):
    vc = [c for c in fc if tr[c].notna().any()]
    imp = SimpleImputer(strategy='median').fit(tr[vc]); scl = StandardScaler().fit(imp.transform(tr[vc]))
    Xtr = scl.transform(imp.transform(tr[vc])); Xcal = scl.transform(imp.transform(cal[vc])); Xte = scl.transform(imp.transform(test[vc]))
    clf, reg = make(model, seed)
    clf.fit(Xtr, tr['TARGET_WIN'].values); reg.fit(Xtr, tr['TARGET_MARGIN'].values)
    iso = IsotonicRegression(out_of_bounds='clip'); iso.fit(clf.predict_proba(Xcal)[:, 1], cal['TARGET_WIN'].values)
    return np.clip(iso.predict(clf.predict_proba(Xte)[:, 1]), 0, 1), reg.predict(Xte)


def run(seeds, models):
    df = load()
    fc_with = select_features(df.columns, enable_series=True)
    fc_without = select_features(df.columns, enable_series=False)
    n_series_cols = len(set(fc_with) - set(fc_without))
    print(f'Series feature columns added: {n_series_cols}  ({sorted(set(fc_with)-set(fc_without))})\n')

    po = df[df['regime'] == 'playoffs'].copy(); po['yr'] = po['GAME_DATE'].dt.year
    results = {'run_at': datetime.now().isoformat(timespec='seconds'), 'seeds': seeds,
               'n_series_cols': n_series_cols, 'models': {}}

    for model in models:
        # pool first-seed predictions for paired tests
        rows = []
        for yr in sorted(po['yr'].unique()):
            po_start = po[po['yr'] == yr]['GAME_DATE'].min()
            train = df[df['GAME_DATE'] < po_start].sort_values('GAME_DATE')  # ALL games (incl prior playoffs)
            if len(train) < 800:
                continue
            cut = int(len(train) * 0.85); tr, cal = train.iloc[:cut], train.iloc[cut:]
            test = po[po['yr'] == yr]
            for s in seeds:
                pw, mw = predict_config(df, fc_with, tr, cal, test, model, s)
                po_, mo = predict_config(df, fc_without, tr, cal, test, model, s)
                if s == seeds[0]:
                    rows.append(pd.DataFrame({
                        'yr': yr, 'GAME_ID': test['GAME_ID'].values,
                        'ywin': test['TARGET_WIN'].values, 'ymargin': test['TARGET_MARGIN'].values,
                        'home_spread': test['home_spread'].values,
                        'p_with': pw, 'm_with': mw, 'p_without': po_, 'm_without': mo}))
            print(f'  {model} {yr}: train={len(tr)} test_po={len(test)}')

        allp = pd.concat(rows, ignore_index=True)
        results['models'][model] = {}
        for scope, sub in [('all_seasons', allp), ('excl_2022', allp[allp.yr != 2022])]:
            yw = sub['ywin'].values.astype(int); ym = sub['ymargin'].values.astype(float)
            def m(p, mar):
                return {'acc': float(((p >= .5).astype(int) == yw).mean()),
                        'auc': float(roc_auc_score(yw, p)), 'mae': float(np.abs(mar - ym).mean())}
            with_m = m(sub['p_with'].values, sub['m_with'].values)
            without_m = m(sub['p_without'].values, sub['m_without'].values)
            # paired tests with vs without
            aw = (sub['p_with'] >= .5).astype(int).values; ao = (sub['p_without'] >= .5).astype(int).values
            b = int(((aw == yw) & (ao != yw)).sum()); c = int(((aw != yw) & (ao == yw)).sum())
            mcp = scistats.chi2.sf((abs(b - c) - 1) ** 2 / (b + c), 1) if (b + c) else 1.0
            ew = np.abs(sub['m_with'] - ym); eo = np.abs(sub['m_without'] - ym)
            t_t, t_p = scistats.ttest_rel(ew, eo)
            # bootstrap AUC delta (with - without)
            rng = np.random.default_rng(0); n = len(sub); d = []
            pw_, po_ = sub['p_with'].values, sub['p_without'].values
            for _ in range(2000):
                idx = rng.integers(0, n, n)
                try:
                    d.append(roc_auc_score(yw[idx], pw_[idx]) - roc_auc_score(yw[idx], po_[idx]))
                except ValueError:
                    pass
            d = np.array(d)
            # vegas on same games (context)
            cov = sub.dropna(subset=['home_spread'])
            veg = None
            if len(cov) > 10:
                ywc = cov['ywin'].values.astype(int)
                veg = {'n': int(len(cov)),
                       'acc': float(((cov['home_spread'] < 0).astype(int) == ywc).mean()),
                       'auc': float(roc_auc_score(ywc, -cov['home_spread'].values))}
            results['models'][model][scope] = {
                'n': int(len(sub)), 'with_series': with_m, 'without_series': without_m,
                'delta_auc_with_minus_without': {'mean': float(d.mean()),
                    'ci': [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))]},
                'mcnemar_p': float(mcp), 'with_wins': b, 'without_wins': c,
                'mae_paired_t_p': float(t_p), 'mae_diff_with_minus_without': float((ew - eo).mean()),
                'vegas_same_games': veg}
            print(f"\n  === {model} / {scope} (n={len(sub)}) ===")
            print(f"    without series: acc={without_m['acc']:.3f} auc={without_m['auc']:.3f} mae={without_m['mae']:.2f}")
            print(f"    with series:    acc={with_m['acc']:.3f} auc={with_m['auc']:.3f} mae={with_m['mae']:.2f}")
            print(f"    delta AUC (with-without): {d.mean():+.4f} CI[{np.percentile(d,2.5):+.4f},{np.percentile(d,97.5):+.4f}]")
            print(f"    McNemar p={mcp:.3f} (with_wins={b}/without_wins={c}); MAE paired-t p={t_p:.3f} (diff {(ew-eo).mean():+.3f})")
            if veg:
                print(f"    [ceiling] Vegas on same {veg['n']}: acc={veg['acc']:.3f} auc={veg['auc']:.3f}")
    return results


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--seeds', type=int, default=5)
    p.add_argument('--models', nargs='+', default=['RF', 'XGB'])
    p.add_argument('--out', default='outputs/e17_series_eval.json')
    a = p.parse_args()
    res = run(SEEDS[:a.seeds], a.models)
    _os.makedirs('outputs', exist_ok=True)
    json.dump(res, open(a.out, 'w'), indent=2)
    print(f'\nSaved -> {a.out}')


if __name__ == '__main__':
    main()
