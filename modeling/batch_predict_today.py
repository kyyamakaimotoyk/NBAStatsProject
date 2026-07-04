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
from datetime import datetime, timedelta, timezone, date as date_cls
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
    backfill_actuals,
)

try:
    from data_engineering.injury_data import get_current_injuries
    LIVE_INJURIES_AVAILABLE = True
except Exception:
    LIVE_INJURIES_AVAILABLE = False


MODEL_KEYS = ('rf', 'nn', 'xgb')


# ---------------------------------------------------------------------------
# Data-freshness guard
# ---------------------------------------------------------------------------

def _run_freshness_checks(engine, bucket) -> None:
    """Print a ``DATA_FRESHNESS_ALERT: <reason>`` line for each staleness problem.

    The token is load-bearing: a CloudWatch metric filter (infra/alarms.tf)
    turns it into an email. Two checks:
      1. Home-job liveness — a drop should land in S3 EVERY day (the reference
         tables ship even in the offseason), so the newest drop being >26h old
         means the home PC slept through the task, the task is disabled, or the
         upload broke.
      2. Boxscore completeness — if the schedule says games happened yesterday,
         game_list should have final (WL set) rows for that date by now.
    """
    problems = []

    if bucket:
        try:
            import boto3
            s3 = boto3.client('s3')
            stamps = []
            for prefix in ('processed/', 'pending/'):
                resp = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, Delimiter='/')
                stamps += [p['Prefix'].split('/')[1] for p in resp.get('CommonPrefixes', [])]
            if not stamps:
                problems.append('no ingest drops in S3 at all')
            else:
                newest = max(stamps)  # ISO-like stamps sort lexicographically
                newest_dt = datetime.strptime(newest, '%Y-%m-%dT%H%M%SZ').replace(
                    tzinfo=timezone.utc)
                age_h = (datetime.now(timezone.utc) - newest_dt).total_seconds() / 3600
                if age_h > 26:
                    problems.append(f'newest ingest drop is {age_h:.0f}h old '
                                    f'(home ingest job not running?)')
        except Exception as exc:
            problems.append(f'could not check ingest drop age: {exc}')

    try:
        import sqlalchemy as sa
        yday = (datetime.now().date() - timedelta(days=1)).isoformat()
        with engine.connect() as conn:
            has_sched = conn.execute(sa.text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = DATABASE() AND table_name = 'league_schedule'"
            )).scalar()
            if has_sched:  # table appears once the season's schedule is published
                n_sched = conn.execute(sa.text(
                    'SELECT COUNT(*) FROM league_schedule WHERE gameDate = :d'),
                    {'d': yday}).scalar()
                if n_sched:
                    n_final = conn.execute(sa.text(
                        'SELECT COUNT(DISTINCT GAME_ID) FROM game_list '
                        'WHERE GAME_DATE = :d AND WL IS NOT NULL'), {'d': yday}).scalar()
                    if not n_final:
                        problems.append(
                            f'{n_sched} games scheduled for {yday} but game_list has '
                            f'no final rows (home fetch failed or ran mid-slate?)')
    except Exception as exc:
        # A broken DB connection has its own alarm; don't double-report it here.
        print(f'WARN: boxscore freshness check failed — {exc}')

    for p in problems:
        print(f'DATA_FRESHNESS_ALERT: {p}')
    if not problems:
        print('freshness: OK')


def _run_drift_check(engine) -> None:
    """E21 live drift monitor: are the DISPLAYED probabilities still honest on
    recent graded games?

    The 2025-26 calibrator incident showed a +0.28 gap between the mean
    displayed home probability and the actual home-win rate, sustained for
    weeks (healthy: a few pp) — visible in live data long before anyone
    looked. This check runs nightly after grading, per model, over the
    trailing 21 days (min 60 graded games, so it is naturally silent in the
    offseason). MODEL_DRIFT_ALERT is alarm-monitored (infra/alarms.tf).
    Threshold 0.12 is calibrated against the incident (+0.28) vs healthy live
    operation (~0.02-0.05).
    """
    try:
        import sqlalchemy as sa
        with engine.connect() as conn:
            rows = conn.execute(sa.text("""
                SELECT model_type, COUNT(*) AS n,
                       AVG(home_win_probability) AS mean_p,
                       AVG(actual_winner = home_team) AS home_rate
                FROM model_predictions
                WHERE actual_winner IS NOT NULL
                  AND game_date >= DATE_SUB(CURDATE(), INTERVAL 21 DAY)
                GROUP BY model_type
            """)).mappings().all()
        for r in rows:
            if r['n'] < 60:
                continue
            gap = float(r['mean_p']) - float(r['home_rate'])
            if abs(gap) > 0.12:
                print(f"MODEL_DRIFT_ALERT: {r['model_type']} displayed-prob gap "
                      f"{gap:+.2f} over last {r['n']} graded games "
                      f"(mean p={float(r['mean_p']):.2f} vs actual "
                      f"{float(r['home_rate']):.2f})")
            else:
                print(f"drift check {r['model_type']}: gap {gap:+.2f} "
                      f"over {r['n']} games (OK)")
    except Exception as exc:
        print(f"WARN: drift check failed - {exc}")


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
        from modeling.predict_games import _derive_pick_probability
        p_cal = float(result.get('win_prob_classifier', result['win_prob']))
        p_raw = result.get('win_prob_classifier_raw')
        # E21: picks derive from the RAW classifier probability (calibrated
        # value is display/logging only). See _derive_pick_probability.
        predicted_winner = (home_team if _derive_pick_probability(result) > 0.5
                            else away_team)
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
                # ERROR, not WARN: a requested-but-unloadable model is a config
                # problem (E21 found xgb silently skipped ALL season because its
                # bundle was never pushed to S3). The alarm emails on ERROR.
                print(f"ERROR: requested model 'nn' unavailable - {exc}")
        elif key == 'xgb':
            try:
                bundles['xgb'] = load_or_train_xgb_models(engine, force_retrain=False)
            except Exception as exc:
                print(f"ERROR: requested model 'xgb' unavailable - {exc}")
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
    p.add_argument('--skip-s3-load', action='store_true',
                   help='Skip loading pending home-ingest drops from S3 (INGEST_S3_BUCKET)')
    p.add_argument('--skip-vegas', action='store_true',
                   help='Skip refreshing today\'s market lines from ESPN')
    p.add_argument('--skip-backfill', action='store_true',
                   help='Skip grading past predictions against final scores')
    p.add_argument('--backfill-lookback', type=int, default=30,
                   help='Days to look back when grading past predictions (default 30)')
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

        # Residential-ingest handoff: load any pending home-box drops FIRST so
        # tonight's grading + rolling features see the freshest boxscores and
        # the league_schedule table is current (the ONLY schedule source that
        # works on AWS — cdn/stats both block datacenter IPs).
        if not args.skip_s3_load:
            bucket = _os.environ.get('INGEST_S3_BUCKET')
            if bucket:
                try:
                    from data_engineering.s3_ingest_loader import load_pending
                    load_pending(engine=engine, bucket=bucket)
                except Exception as exc:
                    print(f"ERROR: S3 ingest load failed — {exc} "
                          f"(predicting with existing DB state)")
            else:
                print("S3 ingest load skipped (INGEST_S3_BUCKET not set)")

        # Grade past predictions against final scores. Must come AFTER the S3
        # load (game_list's final WL rows arrive in the drops) and run nightly —
        # the Track Record page only shows games with actual_winner set, so
        # skipping this freezes the public record. 30-day lookback self-heals
        # after idle stretches.
        if not args.skip_backfill:
            try:
                bf = backfill_actuals(engine, lookback_days=args.backfill_lookback)
                print(f"backfill: {bf}")
            except Exception as exc:
                print(f"ERROR: backfill failed — {exc} (predictions still run)")

        # Refresh today's market lines. ESPN's APIs answer from AWS (probed
        # 2026-07-02) so this stays cloud-side. Skipped in backfill mode —
        # historical lines come from the kaggle import, not ESPN.
        if not args.skip_vegas and not args.start_date:
            try:
                from data_engineering.vegas_lines_espn import (
                    build_team_id_resolver, build_game_id_resolver, fetch_lines_for_date)
                v_start = datetime.now().date()
                v_end = v_start + timedelta(days=1)
                team_res = build_team_id_resolver(engine)
                game_res = build_game_id_resolver(engine, v_start, v_end + timedelta(days=14))
                n_lines = sum(fetch_lines_for_date(engine, d, team_res, game_res)
                              for d in (v_start, v_end))
                print(f"vegas: {n_lines} new rows for {v_start}..{v_end}")
            except Exception as exc:
                print(f"WARN: vegas refresh failed — {exc}")

        # After loading, check the data is actually fresh — prints
        # DATA_FRESHNESS_ALERT lines that the CloudWatch alarm emails on.
        _run_freshness_checks(engine, _os.environ.get('INGEST_S3_BUCKET'))

        # After grading, check the models' displayed probabilities are still
        # honest on recent games — the live-drift lesson from E19/E21.
        if not args.skip_backfill:
            _run_drift_check(engine)

        model_bundles = load_model_bundles(engine, model_keys)
        game_dates = resolve_game_dates(args)
        game_dates = apply_leakage_guard(game_dates, args.allow_leakage)
        if not game_dates:
            print("Nothing to predict. Exiting.")
            print("NIGHTLY_RUN_OK dates=0 predictions=0")  # dead-man heartbeat
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
        if totals['n_errors'] == 0:
            # Dead-man heartbeat: printed ONLY on a clean run. If the nightly task
            # never launches or errors out, this line is absent and the heartbeat
            # alarm (infra/alarms.tf) fires within a day.
            print(f"NIGHTLY_RUN_OK dates={len(game_dates)} "
                  f"predictions={totals['n_predictions']}")
        return min(totals['n_errors'], 127)
    finally:
        engine.dispose()


if __name__ == '__main__':
    sys.exit(main())
