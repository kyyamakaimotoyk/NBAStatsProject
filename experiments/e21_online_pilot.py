"""
E21 leg 3 — Online-recalibration PILOT on live logged data.

Since E18, every prediction logs its RAW classifier probability alongside the
calibrated one, and backfill grades both. That gives ~186 (raw prob, outcome)
pairs per model (games 2026-04-02 -> 2026-06-13) — the production model's own
live output, the most distribution-matched calibration data that can exist.

This pilot replays those pairs chronologically: each week, refit a calibrator on
ALL PRIOR live pairs, apply it to the coming week's games. Compared against:
  raw          - no calibration (picks straight from the classifier)
  stale_prod   - the calibrated probability that ACTUALLY shipped (the logged
                 p_cal from the May-era eval-slice map — the E19 culprit)
  online_iso   - isotonic refit weekly on trailing live pairs
  online_platt - Platt (sigmoid on log-odds) refit weekly on trailing live pairs

PILOT caveats (do not over-read): n≈126 evaluated games after warmup, one
playoff-heavy quarter-season, single model era. Certification needs next
season's volume (~90 pairs/model/week).

Usage:  python experiments/e21_online_pilot.py [--warmup 60]
"""
from __future__ import annotations

import sys as _sys
import os as _os
_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _PROJECT_ROOT)
if _os.getcwd() != _PROJECT_ROOT:
    _os.chdir(_PROJECT_ROOT)

import argparse

import numpy as np
import pandas as pd
import sqlalchemy as sa
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss

from core.db import get_engine
from experiments.e13_calibration import expected_calibration_error


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def fit_platt(p_fit: np.ndarray, y_fit: np.ndarray):
    lr = LogisticRegression(C=1e6)  # near-unregularized: pure Platt refit
    lr.fit(_logit(p_fit).reshape(-1, 1), y_fit)
    return lambda p: lr.predict_proba(_logit(np.asarray(p)).reshape(-1, 1))[:, 1]


def fit_iso(p_fit: np.ndarray, y_fit: np.ndarray):
    iso = IsotonicRegression(out_of_bounds='clip').fit(p_fit, y_fit)
    return lambda p: iso.predict(np.asarray(p, dtype=float))


def replay(d: pd.DataFrame, warmup: int) -> dict:
    """Weekly walk-forward over chronologically sorted live pairs."""
    d = d.sort_values(['game_date', 'game_id']).reset_index(drop=True)
    y = d['home_won'].values.astype(int)
    p_raw = d['p_raw'].values.astype(float)
    p_stale = d['p_cal'].values.astype(float)
    dates = pd.to_datetime(d['game_date'])

    online = {'online_iso': np.full(len(d), np.nan),
              'online_platt': np.full(len(d), np.nan)}
    start = dates.iloc[warmup]
    week_starts = pd.date_range(start, dates.iloc[-1] + pd.Timedelta(days=7), freq='7D')
    for ws in week_starts:
        we = ws + pd.Timedelta(days=7)
        fit_mask = (dates < ws).values
        eval_mask = ((dates >= ws) & (dates < we)).values
        if eval_mask.sum() == 0 or fit_mask.sum() < 30:
            continue
        # Refit on ALL prior live pairs; both fitters see identical data.
        online['online_iso'][eval_mask] = fit_iso(p_raw[fit_mask], y[fit_mask])(p_raw[eval_mask])
        online['online_platt'][eval_mask] = fit_platt(p_raw[fit_mask], y[fit_mask])(p_raw[eval_mask])

    ev = ~np.isnan(online['online_iso'])  # games the online maps scored
    out = {'n_eval': int(ev.sum()),
           'span': f"{d['game_date'][np.argmax(ev)]} .. {d['game_date'].iloc[-1]}"}
    for name, probs in (('raw', p_raw), ('stale_prod', p_stale),
                        ('online_iso', online['online_iso']),
                        ('online_platt', online['online_platt'])):
        p = probs[ev]
        yy = y[ev]
        out[name] = {
            'acc': float(((p > 0.5).astype(int) == yy).mean()),
            'ece': expected_calibration_error(yy, p),
            'brier': float(brier_score_loss(yy, p)),
            'home_share': float((p > 0.5).mean()),
        }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--warmup', type=int, default=60,
                    help='games reserved before the first online fit (default 60)')
    args = ap.parse_args()

    df = pd.read_sql(sa.text("""
        SELECT model_type, game_id, game_date, home_team,
               home_win_probability AS p_cal, home_win_probability_raw AS p_raw,
               actual_winner
        FROM model_predictions
        WHERE actual_winner IS NOT NULL AND home_win_probability_raw IS NOT NULL
    """), get_engine())
    df['home_won'] = (df['actual_winner'] == df['home_team']).astype(int)

    for mt in sorted(df['model_type'].unique()):
        d = df[df['model_type'] == mt]
        # NN logs raw == calibrated (no calibrator) — replay is only meaningful
        # where a calibration layer exists, but run it anyway as a control.
        res = replay(d, args.warmup)
        print(f"\n=== {mt} (live pairs={len(d)}, evaluated={res['n_eval']}, {res['span']}) ===")
        print(f"{'':14s}{'acc':>8s}{'ece':>8s}{'brier':>8s}{'home%':>8s}")
        for proto in ('raw', 'stale_prod', 'online_iso', 'online_platt'):
            m = res[proto]
            print(f"{proto:14s}{m['acc']:8.3f}{m['ece']:8.3f}{m['brier']:8.3f}"
                  f"{m['home_share']:8.2f}")


if __name__ == '__main__':
    main()
