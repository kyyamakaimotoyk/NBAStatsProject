"""Headless prediction job: predict NBA games for a date (or range) and write
to ``model_predictions``. Intended for nightly Fargate scheduled tasks and
local cron — the public web tier reads from ``model_predictions``, never from
this script.

Usage (from project root):

    python modeling/batch_predict_today.py                    # today
    python modeling/batch_predict_today.py --date 2026-05-29  # specific date
    python modeling/batch_predict_today.py --start-date 2026-05-20 --end-date 2026-05-28
    python modeling/batch_predict_today.py --models rf,nn     # subset of models

Differences from ``predict_games.py``:
  * No SHAP (skipped via ``skip_shap=True`` everywhere)
  * No matplotlib / no PNGs
  * No comparison tables / interactive output
  * No manual ``--injuries`` flag — always auto-fetched (live for today,
    point-in-time from ``historical_injury_report`` for backfill dates)
  * No retrain (will fail loudly if a bundle is missing — batch jobs should
    not silently kick off a 10-minute training run)
  * Exit code = number of game-dates that errored (0 = clean run)

Re-runnable: ``model_predictions`` has a unique constraint on
``(game_id, model_type, model_version)``; ``log_prediction`` uses
``ON DUPLICATE KEY UPDATE`` so repeats overwrite the previous row for the same
key. Safe to run multiple times per day.
"""
from __future__ import annotations

# Project-root bootstrap so cross-folder imports work regardless of CWD.
import sys as _sys
import os as _os
_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _PROJECT_ROOT)
if _os.getcwd() != _PROJECT_ROOT:
    _os.chdir(_PROJECT_ROOT)

# PyTorch MUST be imported before numpy/pandas on Windows. predict_games already
# does this in its own module load, but importing it here first keeps a clean
# order even if a future caller imports batch_predict_today directly.
try:
    import torch  # noqa: F401
except ImportError:
    pass  # NN models will be skipped if torch is unavailable.

import argparse
import sys
from datetime import datetime, timedelta, date as date_cls
from typing import Iterable

# Pull primitives out of predict_games. This is the seam: batch_predict_today
# owns the *job orchestration*; predict_games owns the *per-game logic*.
from modeling.predict_games import (
    create_engine,
    get_scheduled_games,
    get_team_rolling_stats,
    build_matchup_features,
    parse_injuries_for_game,
    load_or_train_rf_models,
    load_or_train_pytorch_models,
    load_or_train_xgb_models,
    predict_with_rf,
    predict_with_pytorch,
    predict_with_xgb,
    _fetch_historical_injuries_for_date,
    _model_data_through_date,
)
from modeling.prediction_tracker import (
    log_prediction,
    ensure_table_exists,
    get_model_version,
)

try:
    from data_engineering.injury_data import get_current_injuries
    LIVE_INJURIES_AVAILABLE = True
except Exception:
    LIVE_INJURIES_AVAILABLE = False


MODEL_KEYS = ('rf', 'nn', 'xgb')


# ---------------------------------------------------------------------------
# Injury fetch — live for today, point-in-time for backfill
# ---------------------------------------------------------------------------

def _build_injury_lookup_for_date(engine, game_date: str, mode: str) -> dict:
    """Return a {team_abbrev: [injury dict, ...]} lookup for the given date.

    mode='live'        — current ESPN/NBA feed (only valid for today/future)
    mode='historical'  — ``historical_injury_report`` row at game_date
    """
    lookup: dict = {}
    if mode == 'live':
        if not LIVE_INJURIES_AVAILABLE:
            return lookup
        try:
            for inj in get_current_injuries():
                team = inj.get('team_abbrev')
                if team:
                    lookup.setdefault(team, []).append(inj)
        except Exception as exc:
            print(f"  WARN: live injury fetch failed — {exc}")
    else:
        try:
            for inj in _fetch_historical_injuries_for_date(engine, game_date):
                team = inj.get('team_abbrev')
                if team:
                    lookup.setdefault(team, []).append(inj)
        except Exception as exc:
            print(f"  WARN: historical injury fetch failed for {game_date} — {exc}")
    return lookup


def _game_injuries_from_lookup(home_team_abbrev: str, away_team_abbrev: str,
                                lookup: dict) -> list:
    """Filter the day's lookup down to OUT/DOUBTFUL players on either team."""
    out = []
    seen = set()
    for team_abbrev in (home_team_abbrev, away_team_abbrev):
        for inj in lookup.get(team_abbrev, ()):
            if inj.get('status') in ('OUT', 'DOUBTFUL'):
                name = (inj.get('player_name') or '').strip()
                if not name or name.lower() in seen:
                    continue
                seen.add(name.lower())
                out.append({
                    'name': name,
                    'status': inj['status'].lower(),
                    'team_abbrev': team_abbrev,
                    'team_side': 'home' if team_abbrev == home_team_abbrev else 'away',
                })
    return out


# ---------------------------------------------------------------------------
# Per-model prediction + log
# ---------------------------------------------------------------------------

def _features_for_log(model_bundle, model_key):
    """Return (feature_names, feature_count) regardless of model-tuple shape."""
    # RF: (clf, reg, scaler, features)
    # NN: (clf, reg, scaler, features, target_scaler)
    # XGB: same as RF
    return model_bundle[3], len(model_bundle[3])


def _predict_and_log_one(engine, model_key: str, model_bundle, matchup: dict,
                          game_id, home_team: str, away_team: str,
                          game_date: str, model_version: str | None,
                          feature_count: int, skip_log: bool) -> int:
    """Run one model on one game; log the prediction. Returns 1 on success, 0 on skip/error."""
    try:
        if model_key == 'rf':
            clf, reg, scaler, features = model_bundle
            result = predict_with_rf(clf, reg, scaler, features, matchup, skip_shap=True)
        elif model_key == 'nn':
            clf, reg, scaler, features, target_scaler = model_bundle
            result = predict_with_pytorch(clf, reg, scaler, features, matchup,
                                          skip_shap=True, target_scaler=target_scaler)
        elif model_key == 'xgb':
            clf, reg, scaler, features = model_bundle
            result = predict_with_xgb(clf, reg, scaler, features, matchup, skip_shap=True)
        else:
            print(f"  WARN: unknown model key {model_key!r}")
            return 0
    except Exception as exc:
        print(f"  ERROR: {model_key} prediction failed for {away_team} @ {home_team} — {exc}")
        return 0

    if skip_log:
        return 1

    try:
        p_cal = float(result.get('win_prob_classifier', result['win_prob']))
        p_raw = result.get('win_prob_classifier_raw')
        predicted_winner = home_team if p_cal > 0.5 else away_team
        log_prediction(
            engine=engine,
            game_id=game_id,
            game_date=game_date,
            home_team=home_team,
            away_team=away_team,
            model_type=model_key,
            model_version=model_version,
            predicted_winner=predicted_winner,
            predicted_margin=result['margin_mean'],
            home_win_probability=p_cal,
            home_win_probability_raw=(float(p_raw) if p_raw is not None else None),
            margin_uncertainty=result['margin_std'],
            feature_count=feature_count,
        )
        return 1
    except Exception as exc:
        print(f"  ERROR: {model_key} log_prediction failed for {away_team} @ {home_team} — {exc}")
        return 0


# ---------------------------------------------------------------------------
# Per-date loop
# ---------------------------------------------------------------------------

def predict_for_date(engine, game_date: str, model_bundles: dict,
                      injury_mode: str, skip_log: bool = False) -> dict:
    """Predict + log every scheduled game on ``game_date``.

    Returns ``{'n_games': N, 'n_predictions': K, 'n_errors': E}``.
    """
    games = get_scheduled_games(game_date)
    if len(games) == 0:
        print(f"  {game_date}: no scheduled games")
        return {'n_games': 0, 'n_predictions': 0, 'n_errors': 0}

    print(f"  {game_date}: {len(games)} scheduled games")
    injuries_today = _build_injury_lookup_for_date(engine, game_date, injury_mode)

    n_predictions = 0
    n_errors = 0
    for _, game in games.iterrows():
        home_id = game['HOME_TEAM_ID']
        away_id = game['AWAY_TEAM_ID']
        home_team = game['HOME_TEAM']
        away_team = game['AWAY_TEAM']
        game_id = game['GAME_ID']

        home_features = get_team_rolling_stats(engine, home_id, game_date)
        away_features = get_team_rolling_stats(engine, away_id, game_date)
        if home_features is None or away_features is None:
            print(f"  SKIP {away_team} @ {home_team}: missing rolling stats")
            n_errors += 1
            continue

        game_injuries = _game_injuries_from_lookup(home_team, away_team, injuries_today)
        injury_info = parse_injuries_for_game(engine, game_injuries, home_id, away_id, game_date)
        home_out = [d['name'] for d in injury_info['injury_details'] if d['team'] == 'home']
        away_out = [d['name'] for d in injury_info['injury_details'] if d['team'] == 'away']

        matchup = build_matchup_features(
            home_features, away_features,
            engine=engine,
            home_team_id=home_id,
            away_team_id=away_id,
            game_date=game_date,
            home_injuries=home_out,
            away_injuries=away_out,
        )

        for model_key, bundle in model_bundles.items():
            feat_names, feat_count = _features_for_log(bundle, model_key)
            model_version = get_model_version(feat_count)
            ok = _predict_and_log_one(
                engine, model_key, bundle, matchup,
                game_id, home_team, away_team, game_date,
                model_version, feat_count, skip_log,
            )
            n_predictions += ok
            n_errors += (1 - ok)

    return {'n_games': len(games), 'n_predictions': n_predictions, 'n_errors': n_errors}


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------

def load_model_bundles(engine, model_keys: Iterable[str]) -> dict:
    """Load each requested model from its current bundle. No retrain — fail loudly."""
    bundles = {}
    for key in model_keys:
        if key == 'rf':
            bundles['rf'] = load_or_train_rf_models(engine, force_retrain=False)
        elif key == 'nn':
            try:
                bundles['nn'] = load_or_train_pytorch_models(engine, force_retrain=False)
            except Exception as exc:
                print(f"WARN: skipping nn — {exc}")
        elif key == 'xgb':
            try:
                bundles['xgb'] = load_or_train_xgb_models(engine, force_retrain=False)
            except Exception as exc:
                print(f"WARN: skipping xgb — {exc}")
        else:
            print(f"WARN: unknown model key {key!r}")
    if not bundles:
        raise RuntimeError("No models loaded — check models/bundles/*_current.joblib")
    return bundles


# ---------------------------------------------------------------------------
# Date list resolution + leakage guard
# ---------------------------------------------------------------------------

def resolve_game_dates(args) -> list:
    if args.start_date:
        start_d = datetime.strptime(args.start_date, '%Y-%m-%d').date()
        end_d = (datetime.strptime(args.end_date, '%Y-%m-%d').date()
                 if args.end_date else datetime.now().date())
        if end_d < start_d:
            raise SystemExit(f"ERROR: --end-date {end_d} is before --start-date {start_d}")
        return [(start_d + timedelta(days=i)).strftime('%Y-%m-%d')
                for i in range((end_d - start_d).days + 1)]
    if args.date:
        return [args.date]
    if args.tomorrow:
        return [(datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')]
    return [datetime.now().strftime('%Y-%m-%d')]


def apply_leakage_guard(game_dates: list, allow_leakage: bool) -> list:
    if allow_leakage or len(game_dates) <= 1:
        return game_dates
    through = _model_data_through_date()
    if through is None:
        print("WARN: bundle lacks data_through_date metadata; leakage guard cannot enforce.")
        return game_dates
    kept = [d for d in game_dates if datetime.strptime(d, '%Y-%m-%d').date() > through]
    dropped = len(game_dates) - len(kept)
    if dropped:
        print(f"[leakage guard] model trained through {through}; dropping {dropped} of "
              f"{len(game_dates)} dates. --allow-leakage to override.")
    return kept


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Headless batch predictor for nightly jobs.")
    p.add_argument('--date', type=str, default=None,
                   help='Single date YYYY-MM-DD (default: today)')
    p.add_argument('--tomorrow', action='store_true',
                   help='Predict tomorrow instead of today')
    p.add_argument('--start-date', type=str, default=None,
                   help='Start of a backfill window (uses point-in-time injuries)')
    p.add_argument('--end-date', type=str, default=None,
                   help='End of backfill window (default: today)')
    p.add_argument('--models', type=str, default='rf,nn,xgb',
                   help='Comma-separated subset of: rf, nn, xgb')
    p.add_argument('--no-log', action='store_true',
                   help='Compute predictions but skip writing to model_predictions')
    p.add_argument('--allow-leakage', action='store_true',
                   help='Permit backfill predictions for dates inside the model\'s training window.')
    p.add_argument('--injury-source', choices=('auto', 'live', 'historical'), default='auto',
                   help="auto = live for today/future, historical for older dates")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    model_keys = [k.strip() for k in args.models.split(',') if k.strip()]
    invalid = [k for k in model_keys if k not in MODEL_KEYS]
    if invalid:
        raise SystemExit(f"ERROR: unknown model keys {invalid}; valid keys: {MODEL_KEYS}")

    engine = create_engine()
    try:
        ensure_table_exists(engine)
        model_bundles = load_model_bundles(engine, model_keys)
        game_dates = resolve_game_dates(args)
        game_dates = apply_leakage_guard(game_dates, args.allow_leakage)
        if not game_dates:
            print("Nothing to predict. Exiting.")
            return 0

        today_iso = datetime.now().strftime('%Y-%m-%d')

        totals = {'n_games': 0, 'n_predictions': 0, 'n_errors': 0}
        for game_date in game_dates:
            if args.injury_source == 'auto':
                injury_mode = 'live' if game_date >= today_iso else 'historical'
            else:
                injury_mode = args.injury_source
            stats = predict_for_date(
                engine, game_date, model_bundles,
                injury_mode=injury_mode, skip_log=args.no_log,
            )
            for k, v in stats.items():
                totals[k] += v

        print()
        print(f"Done. {totals['n_predictions']} predictions across {totals['n_games']} games; "
              f"{totals['n_errors']} errors.")
        return min(totals['n_errors'], 127)
    finally:
        engine.dispose()


if __name__ == '__main__':
    sys.exit(main())
