"""
E27 — Win probability derived from the margin regressor.

Each family logs a pick + win probability from its CLASSIFIER and a margin from
a separately trained REGRESSOR; early 2026-27 they pointed at different teams
on 20-57% of games. Candidate fix: drop the classifier's probability and use
    p(home win) = Phi(margin / sigma)
so the pick is the margin's sign and the two can never disagree.

No new estimators: every arm is a transform of the SAME fitted classifier and
regressor, so the comparison is exactly paired.
    clf_raw    classifier predict_proba          (prod pick; RF/NN display)
    clf_iso    eval-slice isotonic on clf_raw     (prod XGB display)
    phi_mle    Phi(m/s), s = probit MLE on eval   (PRIMARY, pre-registered)
    phi_resid  Phi(m/s), s = eval residual SD
The eval slice mirrors production calibration: refit on the first 80% of the
training rows, predict the last 20%.

Pre-registered gates: experiments/specs/e27_margin_prob.json (written before
launch). Result JSON is rewritten after every window so a crash keeps progress.

Usage:
    python experiments/e27_margin_prob.py                       # full run
    python experiments/e27_margin_prob.py --limit-windows 1 --models RF --seeds 1   # smoke
"""
from __future__ import annotations

import sys as _sys
import os as _os
_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)

# harness import MUST come first: torch-before-pandas + chdir to project root.
from experiments.harness import (
    PYTORCH_AVAILABLE, SEEDS, N_BOOTSTRAP, month_windows, load_frozen_csv,
    prepare_xy, mcnemar_test,
)
from experiments.loop_ab import train_predict
from experiments.e13_calibration import expected_calibration_error

import argparse
import json
import time
from datetime import datetime

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.stats import norm
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import roc_auc_score

from core.features import select_features, load_pruned_columns

ARMS = ('clf_raw', 'clf_iso', 'phi_mle', 'phi_resid')
PRIMARY = 'phi_mle'
# Production probability each family displays (the log-loss comparator).
PROD_PROB = {'RF': 'clf_raw', 'NN': 'clf_raw', 'XGB': 'clf_iso'}
GATE_ACC_CI_LO = -0.010
GATE_LOGLOSS_CI_HI = 0.005
EPS = 1e-6
EARLY_MONTHS = (10, 11)


# ----------------------------------------------------------------------------
# sigma fits + metrics
# ----------------------------------------------------------------------------

def fit_sigma_mle(margin: np.ndarray, y: np.ndarray) -> float:
    """1-parameter probit, no intercept: maximise sum log Phi(+-m/s)."""
    def nll(log_s):
        p = np.clip(norm.cdf(margin / np.exp(log_s)), EPS, 1 - EPS)
        return -np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))
    res = minimize_scalar(nll, bounds=(np.log(1.0), np.log(80.0)), method='bounded')
    return float(np.exp(res.x))


def logloss_vec(y, p):
    p = np.clip(p, EPS, 1 - EPS)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def metrics(y, p):
    out = {'acc': float(np.mean((p >= 0.5) == y)),
           'logloss': float(np.mean(logloss_vec(y, p))),
           'brier': float(np.mean((p - y) ** 2)),
           'ece': expected_calibration_error(y, p),
           'home_pick_share': float(np.mean(p >= 0.5))}
    try:
        out['auc'] = float(roc_auc_score(y, p))
    except ValueError:
        out['auc'] = None
    return out


def paired_bootstrap(delta: np.ndarray, n_boot: int, seed: int = 0):
    """Mean of a per-game delta with a paired-bootstrap 95% CI and 2-sided p."""
    rng = np.random.default_rng(seed)
    n = len(delta)
    means = np.array([delta[rng.integers(0, n, n)].mean() for _ in range(n_boot)])
    p = float(2 * min((means <= 0).mean(), (means >= 0).mean()))
    return {'mean': float(delta.mean()), 'ci_lo': float(np.percentile(means, 2.5)),
            'ci_hi': float(np.percentile(means, 97.5)), 'p': min(p, 1.0)}


def auc_diff_bootstrap(y, pa, pb, n_boot: int, seed: int = 0):
    rng = np.random.default_rng(seed)
    n = len(y)
    diffs = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        if y[idx].min() == y[idx].max():
            continue
        diffs.append(roc_auc_score(y[idx], pa[idx]) - roc_auc_score(y[idx], pb[idx]))
    diffs = np.array(diffs)
    p = float(2 * min((diffs <= 0).mean(), (diffs >= 0).mean()))
    return {'mean': float(roc_auc_score(y, pa) - roc_auc_score(y, pb)),
            'ci_lo': float(np.percentile(diffs, 2.5)),
            'ci_hi': float(np.percentile(diffs, 97.5)), 'p': min(p, 1.0)}


def compare(y, p_arm, p_prob_base, p_pick_base, n_boot):
    """arm vs base: picks against p_pick_base, probability quality against
    p_prob_base. Negative logloss/brier delta = arm better."""
    pick_a = (p_arm >= 0.5).astype(int)
    pick_b = (p_pick_base >= 0.5).astype(int)
    _, mc_p, a_only, b_only = mcnemar_test(pick_a, pick_b, y)
    acc = paired_bootstrap((pick_a == y).astype(float) - (pick_b == y).astype(float), n_boot)
    ll = paired_bootstrap(logloss_vec(y, p_arm) - logloss_vec(y, p_prob_base), n_boot)
    br = paired_bootstrap((p_arm - y) ** 2 - (p_prob_base - y) ** 2, n_boot)
    auc = auc_diff_bootstrap(y, p_arm, p_prob_base, n_boot)
    return {'n': int(len(y)), 'acc': acc, 'mcnemar_p': float(mc_p),
            'arm_right_base_wrong': a_only, 'base_right_arm_wrong': b_only,
            'logloss': ll, 'brier': br, 'auc': auc,
            'ece_arm': expected_calibration_error(y, p_arm),
            'ece_base': expected_calibration_error(y, p_prob_base)}


def gate(c: dict) -> dict:
    against = ((c['mcnemar_p'] < 0.05 and c['base_right_arm_wrong'] > c['arm_right_base_wrong'])
               or (c['logloss']['p'] < 0.05 and c['logloss']['mean'] > 0)
               or (c['brier']['p'] < 0.05 and c['brier']['mean'] > 0)
               or c['auc']['ci_hi'] < 0)
    checks = {'acc_noninferior': c['acc']['ci_lo'] > GATE_ACC_CI_LO,
              'logloss_noninferior': c['logloss']['ci_hi'] < GATE_LOGLOSS_CI_HI,
              'no_significant_regression': not against}
    return {'pass': all(checks.values()), 'checks': checks}


# ----------------------------------------------------------------------------
# main loop
# ----------------------------------------------------------------------------

def arm_probs(clf_te, reg_te, clf_ev, reg_ev, y_ev, yreg_ev):
    iso = IsotonicRegression(out_of_bounds='clip', y_min=0, y_max=1).fit(clf_ev, y_ev)
    s_mle = fit_sigma_mle(reg_ev, y_ev)
    s_res = float(np.std(yreg_ev - reg_ev))
    return ({'clf_raw': clf_te, 'clf_iso': iso.predict(clf_te),
             'phi_mle': norm.cdf(reg_te / s_mle), 'phi_resid': norm.cdf(reg_te / s_res)},
            {'sigma_mle': s_mle, 'sigma_resid': s_res})


def run(args):
    df, meta = load_frozen_csv(args.csv)
    cols = select_features(df.columns, keep_only=load_pruned_columns())
    seeds = SEEDS[:args.seeds]
    models = [m for m in args.models if m != 'NN' or PYTORCH_AVAILABLE]
    wins = month_windows(df['GAME_DATE'], start=args.window_start)
    if args.limit_windows:
        wins = wins[:args.limit_windows]
    print(f'{args.csv}: {len(df)} games, {len(cols)} features, {len(wins)} windows, '
          f'models={models}, seeds={seeds}', flush=True)

    out = {'experiment_id': 'E27', 'spec': args.spec, 'csv': args.csv, 'csv_meta': meta,
           'n_features': len(cols), 'models': models, 'seeds': seeds,
           'n_bootstrap': args.n_bootstrap, 'run_at': datetime.now().isoformat(timespec='seconds'),
           'status': 'partial', 'windows': {}, 'pooled': {}}
    # per family: seed-mean per-game arrays across all windows
    pool = {m: {'y': [], 'month': [], 'margin': [], **{a: [] for a in ARMS}} for m in models}
    per_seed_pool = {m: {s: {'y': [], **{a: [] for a in ARMS}} for s in seeds} for m in models}

    t_all = time.time()
    for win in wins:
        train_df = df[df['GAME_DATE'] < win['start']]
        test_df = df[(df['GAME_DATE'] >= win['start']) & (df['GAME_DATE'] <= win['end'])]
        split = int(0.8 * len(train_df))
        fit_df, ev_df = train_df.iloc[:split], train_df.iloc[split:]
        X_tr, X_te, _ = prepare_xy(train_df, test_df, cols)
        X_fit, X_ev, _ = prepare_xy(fit_df, ev_df, cols)
        y_tr = train_df['TARGET_WIN'].values.astype(int)
        yreg_tr = train_df['TARGET_MARGIN'].values.astype(float)
        y_fit = fit_df['TARGET_WIN'].values.astype(int)
        yreg_fit = fit_df['TARGET_MARGIN'].values.astype(float)
        y_ev = ev_df['TARGET_WIN'].values.astype(int)
        yreg_ev = ev_df['TARGET_MARGIN'].values.astype(float)
        y_te = test_df['TARGET_WIN'].values.astype(int)
        month = int(str(win['start'])[5:7])

        w_out = {'n_train': len(train_df), 'n_test': len(test_df), 'families': {}}
        for fam in models:
            seed_probs, seed_margins, sigmas, splits = [], [], [], []
            for seed in seeds:
                t0 = time.time()
                clf_te, reg_te = train_predict(fam, X_tr, y_tr, yreg_tr, X_te, seed)
                clf_ev, reg_ev = train_predict(fam, X_fit, y_fit, yreg_fit, X_ev, seed)
                probs, sig = arm_probs(np.asarray(clf_te), np.asarray(reg_te),
                                       np.asarray(clf_ev), np.asarray(reg_ev), y_ev, yreg_ev)
                seed_probs.append(probs)
                seed_margins.append(np.asarray(reg_te))
                sigmas.append(sig)
                splits.append(float(np.mean((clf_te >= 0.5) != (reg_te > 0))))
                ps = per_seed_pool[fam][seed]
                ps['y'].append(y_te)
                for a in ARMS:
                    ps[a].append(probs[a])
                print(f'  [{win["name"]}] {fam} seed={seed} {time.time()-t0:.1f}s '
                      f'sigma_mle={sig["sigma_mle"]:.1f} sigma_resid={sig["sigma_resid"]:.1f} '
                      f'split={splits[-1]:.1%}', flush=True)
            mean_probs = {a: np.mean([sp[a] for sp in seed_probs], axis=0) for a in ARMS}
            mean_margin = np.mean(seed_margins, axis=0)
            w_out['families'][fam] = {
                'metrics': {a: metrics(y_te, mean_probs[a]) for a in ARMS},
                'sigma_mle': float(np.mean([s['sigma_mle'] for s in sigmas])),
                'sigma_resid': float(np.mean([s['sigma_resid'] for s in sigmas])),
                'split_rate_per_seed_mean': float(np.mean(splits)),
            }
            p = pool[fam]
            p['y'].append(y_te)
            p['month'].append(np.full(len(y_te), month))
            p['margin'].append(mean_margin)
            for a in ARMS:
                p[a].append(mean_probs[a])
            m = w_out['families'][fam]['metrics']
            print(f'[{win["name"]}] {fam} n={len(y_te)} acc clf/phi {m["clf_raw"]["acc"]:.3f}/'
                  f'{m[PRIMARY]["acc"]:.3f} logloss {m[PROD_PROB[fam]]["logloss"]:.4f}/'
                  f'{m[PRIMARY]["logloss"]:.4f} split {np.mean(splits):.1%}', flush=True)
        out['windows'][win['name']] = w_out
        out['elapsed_min'] = round((time.time() - t_all) / 60, 1)
        _dump(out, args.out)

    # ---- pooled analysis ----
    for fam in models:
        p = {k: np.concatenate(v) for k, v in pool[fam].items()}
        y = p['y'].astype(int)
        base_prob, base_pick = p[PROD_PROB[fam]], p['clf_raw']
        res = {'n': int(len(y)),
               'metrics': {a: metrics(y, p[a]) for a in ARMS},
               'split_rate_seed_mean_ensemble': float(np.mean((p['clf_raw'] >= 0.5) != (p['margin'] > 0))),
               'comparisons': {}}
        for a in ('phi_mle', 'phi_resid'):
            res['comparisons'][f'{a}_vs_prod'] = compare(y, p[a], base_prob, base_pick, args.n_bootstrap)
        res['comparisons']['phi_resid_vs_phi_mle'] = compare(
            y, p['phi_resid'], p['phi_mle'], p['phi_mle'], args.n_bootstrap)
        res['gate_primary'] = gate(res['comparisons']['phi_mle_vs_prod'])

        early = np.isin(p['month'], EARLY_MONTHS)
        res['early_vs_rest'] = {}
        for label, mask in (('oct_nov', early), ('dec_on', ~early)):
            if mask.sum() < 50:
                continue
            c = compare(y[mask], p[PRIMARY][mask], base_prob[mask], base_pick[mask], args.n_bootstrap)
            c['split_rate'] = float(np.mean((p['clf_raw'][mask] >= 0.5) != (p['margin'][mask] > 0)))
            res['early_vs_rest'][label] = c

        # per-seed direction consistency (no seed averaging)
        cons = {'acc_delta': [], 'logloss_delta': []}
        for seed in seeds:
            ps = {k: np.concatenate(v) for k, v in per_seed_pool[fam][seed].items()}
            ys = ps['y'].astype(int)
            cons['acc_delta'].append(float(np.mean((ps[PRIMARY] >= 0.5) == ys)
                                           - np.mean((ps['clf_raw'] >= 0.5) == ys)))
            cons['logloss_delta'].append(float(np.mean(logloss_vec(ys, ps[PRIMARY]))
                                               - np.mean(logloss_vec(ys, ps[PROD_PROB[fam]]))))
        res['per_seed'] = cons
        out['pooled'][fam] = res

        c = res['comparisons']['phi_mle_vs_prod']
        print(f'\n=== {fam} pooled n={len(y)} (vs prod prob {PROD_PROB[fam]}) ===')
        print(f'  acc   d={c["acc"]["mean"]:+.4f} [{c["acc"]["ci_lo"]:+.4f}, {c["acc"]["ci_hi"]:+.4f}] '
              f'McNemar p={c["mcnemar_p"]:.3f}')
        print(f'  logloss d={c["logloss"]["mean"]:+.4f} [{c["logloss"]["ci_lo"]:+.4f}, '
              f'{c["logloss"]["ci_hi"]:+.4f}] p={c["logloss"]["p"]:.3f}')
        print(f'  brier d={c["brier"]["mean"]:+.4f} p={c["brier"]["p"]:.3f} | '
              f'AUC d={c["auc"]["mean"]:+.4f} p={c["auc"]["p"]:.3f} | '
              f'ECE {c["ece_base"]:.3f} -> {c["ece_arm"]:.3f}')
        print(f'  split rate {res["split_rate_seed_mean_ensemble"]:.1%} | '
              f'per-seed acc d {cons["acc_delta"]} | GATE {res["gate_primary"]}')

    out['status'] = 'done'
    out['elapsed_min'] = round((time.time() - t_all) / 60, 1)
    _dump(out, args.out)
    print(f'\nSaved -> {args.out} ({out["elapsed_min"]} min)')


def _dump(obj, path):
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(obj, f, indent=2, default=float)
    _os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--csv', default='nba_ml_features_frozen.csv')
    ap.add_argument('--spec', default='experiments/specs/e27_margin_prob.json')
    ap.add_argument('--models', nargs='+', default=['RF', 'XGB', 'NN'])
    ap.add_argument('--seeds', type=int, default=3)
    ap.add_argument('--window-start', default='2023-10')
    ap.add_argument('--limit-windows', type=int, default=0)
    ap.add_argument('--n-bootstrap', type=int, default=N_BOOTSTRAP)
    ap.add_argument('--out', default='outputs/e27_margin_prob.json')
    main_args = ap.parse_args()
    run(main_args)


if __name__ == '__main__':
    main()
