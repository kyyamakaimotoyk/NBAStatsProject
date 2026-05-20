"""
E16 (Playoff Step 0) — Establish the playoff prediction *ceiling* via Vegas.

E15 showed our model drops to ~0.64 AUC on playoffs. Question: is that close to the
irreducible ceiling, or is there real signal we're missing? Compare our model vs the
Vegas closing line on the SAME playoff games (head-to-head, same test set).

Method (mirrors E15 regime mode for the model side):
  For each season's playoffs, train RF/XGB on regular-season games strictly before
  that season's playoffs, predict on that season's playoff games. Pool predictions,
  restrict to games that have a Vegas line, and score both:
    - accuracy: did the favorite (model pick / Vegas favorite) win?
    - AUC:      ranking score (model calibrated prob / Vegas -home_spread)
    - MAE:      |actual_margin - predicted_margin|; Vegas predicted margin = -home_spread
  Bootstrap the model-minus-Vegas deltas for CIs.

If Vegas also lands ~0.64-0.66 AUC -> near the ceiling, cap the investment.
If Vegas holds ~0.70+ -> real signal to chase (Tracks A/B in the plan).

Usage:
    python experiments/e16_playoff_ceiling.py --seeds 5
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


def load_with_vegas():
    df = pd.read_csv('nba_ml_features.csv')
    df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])
    df['GAME_ID'] = df['GAME_ID'].astype('int64')
    eng = get_engine()
    gl = pd.read_sql(text('SELECT DISTINCT GAME_ID, SEASON_ID FROM game_list'), eng)
    gl['GAME_ID'] = gl['GAME_ID'].astype('int64')
    gl['regime'] = gl['SEASON_ID'].astype(str).str[0].map(
        {'2': 'regular', '4': 'playoffs', '5': 'playin', '3': 'allstar', '1': 'preseason', '6': 'cup'})
    df = df.merge(gl[['GAME_ID', 'regime']], on='GAME_ID', how='left')
    # Vegas: prefer DraftKings, else consensus/kaggle. One row per game_id.
    vl = pd.read_sql(text('''SELECT game_id, source, home_spread FROM vegas_lines
                             WHERE home_spread IS NOT NULL AND game_id IS NOT NULL'''), eng)
    vl['game_id'] = vl['game_id'].astype('int64')
    pri = {'espn_draftkings': 0, 'kaggle_sbr': 1, 'espn_consensus': 2}
    vl['pri'] = vl['source'].map(pri).fillna(9)
    vl = vl.sort_values('pri').drop_duplicates('game_id', keep='first')
    df = df.merge(vl[['game_id', 'home_spread']].rename(columns={'game_id': 'GAME_ID'}),
                  on='GAME_ID', how='left')
    return df


def make_models(model, seed):
    if model == 'RF':
        return (RandomForestClassifier(**RF_CLF, random_state=seed, n_jobs=-1),
                RandomForestRegressor(**RF_REG, random_state=seed, n_jobs=-1))
    return (xgb.XGBClassifier(**XGB_CLF, random_state=seed, n_jobs=-1),
            xgb.XGBRegressor(**XGB_REG, random_state=seed, n_jobs=-1))


def run(seeds, models):
    df = load_with_vegas()
    fc = select_features(df.columns)
    po = df[df['regime'] == 'playoffs'].copy()
    po['yr'] = po['GAME_DATE'].dt.year

    # collect model predictions on playoff games (first seed, per-season temporal train)
    rows = {m: [] for m in models}
    for yr in sorted(po['yr'].unique()):
        po_start = po[po['yr'] == yr]['GAME_DATE'].min()
        train = df[(df['regime'] == 'regular') & (df['GAME_DATE'] < po_start)].sort_values('GAME_DATE')
        if len(train) < 500:
            continue
        cut = int(len(train) * 0.85)
        tr, cal = train.iloc[:cut], train.iloc[cut:]
        test = po[po['yr'] == yr]
        vc = tr[fc].columns[tr[fc].notna().any()].tolist()
        imp = SimpleImputer(strategy='median').fit(tr[vc])
        scl = StandardScaler().fit(imp.transform(tr[vc]))
        Xtr = scl.transform(imp.transform(tr[vc]))
        Xcal = scl.transform(imp.transform(cal[vc]))
        Xte = scl.transform(imp.transform(test[vc]))
        for m in models:
            clf_seeds, reg_seeds = [], []
            for s in seeds:
                clf, reg = make_models(m, s)
                clf.fit(Xtr, tr['TARGET_WIN'].values); reg.fit(Xtr, tr['TARGET_MARGIN'].values)
                iso = IsotonicRegression(out_of_bounds='clip')
                iso.fit(clf.predict_proba(Xcal)[:, 1], cal['TARGET_WIN'].values)
                clf_seeds.append(np.clip(iso.predict(clf.predict_proba(Xte)[:, 1]), 0, 1))
                reg_seeds.append(reg.predict(Xte))
            sub = pd.DataFrame({
                'GAME_ID': test['GAME_ID'].values,
                'ywin': test['TARGET_WIN'].values,
                'ymargin': test['TARGET_MARGIN'].values,
                'home_spread': test['home_spread'].values,
                'model_p': np.mean(clf_seeds, axis=0),
                'model_margin': np.mean(reg_seeds, axis=0),
            })
            rows[m].append(sub)

    results = {'run_at': datetime.now().isoformat(timespec='seconds'), 'seeds': seeds, 'models': {}}
    for m in models:
        allp = pd.concat(rows[m], ignore_index=True)
        cov = allp.dropna(subset=['home_spread']).copy()  # games with Vegas
        n_all, n_cov = len(allp), len(cov)
        ywin = cov['ywin'].values.astype(int); ymar = cov['ymargin'].values.astype(float)
        # model
        m_acc = ((cov['model_p'] >= 0.5).astype(int) == ywin).mean()
        m_auc = roc_auc_score(ywin, cov['model_p'])
        m_mae = np.abs(cov['model_margin'] - ymar).mean()
        # vegas: favorite = home if home_spread<0; score for AUC = -home_spread; margin = -home_spread
        veg_pick_home = (cov['home_spread'] < 0).astype(int)
        v_acc = (veg_pick_home == ywin).mean()
        v_auc = roc_auc_score(ywin, -cov['home_spread'].values)
        v_mae = np.abs((-cov['home_spread'].values) - ymar).mean()
        # bootstrap deltas (model - vegas)
        rng = np.random.default_rng(0); n = len(cov)
        d_auc, d_mae, d_acc = [], [], []
        mp = cov['model_p'].values; mm = cov['model_margin'].values; hs = cov['home_spread'].values
        for _ in range(2000):
            idx = rng.integers(0, n, n)
            try:
                d_auc.append(roc_auc_score(ywin[idx], mp[idx]) - roc_auc_score(ywin[idx], -hs[idx]))
            except ValueError:
                continue
            d_mae.append(np.abs(mm[idx]-ymar[idx]).mean() - np.abs(-hs[idx]-ymar[idx]).mean())
            d_acc.append(((mp[idx] >= .5).astype(int) == ywin[idx]).mean() - ((hs[idx] < 0).astype(int) == ywin[idx]).mean())
        def ci(a): a=np.array(a); return [float(np.percentile(a,2.5)), float(np.percentile(a,97.5))]
        results['models'][m] = {
            'n_playoff_all': int(n_all), 'n_with_vegas': int(n_cov),
            'model': {'acc': float(m_acc), 'auc': float(m_auc), 'mae': float(m_mae)},
            'vegas': {'acc': float(v_acc), 'auc': float(v_auc), 'mae': float(v_mae)},
            'delta_model_minus_vegas': {
                'auc_mean': float(np.mean(d_auc)), 'auc_ci': ci(d_auc),
                'mae_mean': float(np.mean(d_mae)), 'mae_ci': ci(d_mae),
                'acc_mean': float(np.mean(d_acc)), 'acc_ci': ci(d_acc)},
        }
        print(f"\n=== {m} on {n_cov} playoff games with Vegas (of {n_all}) ===")
        print(f"  {'':8}{'acc':>8}{'auc':>8}{'mae':>8}")
        print(f"  {'MODEL':8}{m_acc:>8.3f}{m_auc:>8.3f}{m_mae:>8.2f}")
        print(f"  {'VEGAS':8}{v_acc:>8.3f}{v_auc:>8.3f}{v_mae:>8.2f}")
        r = results['models'][m]['delta_model_minus_vegas']
        print(f"  delta (model-vegas): AUC {r['auc_mean']:+.3f} CI{r['auc_ci']}  "
              f"MAE {r['mae_mean']:+.2f} CI{r['mae_ci']}  ACC {r['acc_mean']:+.3f} CI{r['acc_ci']}")
    return results


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--seeds', type=int, default=5)
    p.add_argument('--models', nargs='+', default=['RF', 'XGB'])
    p.add_argument('--out', default='outputs/e16_playoff_ceiling.json')
    a = p.parse_args()
    res = run(SEEDS[:a.seeds], a.models)
    _os.makedirs('outputs', exist_ok=True)
    json.dump(res, open(a.out, 'w'), indent=2)
    print(f'\nSaved -> {a.out}')


if __name__ == '__main__':
    main()
