"""
NBA Stats Pipeline Orchestrator
================================

One-shot runner that sequences the existing scripts (data fetch → features → train
→ predict → backfill → validate) and decides which stages need to run based on
the freshness of various DB tables.

Each individual .py script keeps its own CLI surface — this file does not replace
them. It calls them via subprocess so behavior stays identical to running them
by hand. Output from each stage is appended to logs/pipeline_<run_id>.log.

Usage
-----
    python orchestration/pipeline.py status              # JSON-ish status report, no side effects
    python orchestration/pipeline.py recommend           # what stages should run, given current state
    python orchestration/pipeline.py run --stages all    # run every stage end-to-end
    python orchestration/pipeline.py run --stages features,train,predict
    python orchestration/pipeline.py run --stages predict --predict-date 2026-05-18

The dashboard's Operations tab uses the same status/recommend/run entry points,
so anything you can do here is available in the GUI too.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any

# Project-root bootstrap so cross-folder imports (core.*, modeling.*, ...) work regardless of CWD.
# pipeline.py now lives in orchestration/, so REPO_ROOT must climb two `dirname` calls.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from sqlalchemy import text

from core.db import get_engine
from modeling.model_types import cli_choices as _model_cli_choices, model_keys as _model_keys


# ============================================================================
# CONSTANTS
# ============================================================================

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(REPO_ROOT, 'logs')
STATE_FILE = os.path.join(LOG_DIR, 'pipeline_state.json')
FEATURES_CSV = os.path.join(REPO_ROOT, 'nba_ml_features.csv')

STAGE_ORDER = ['fetch_data', 'player_impact', 'features', 'train', 'predict', 'backfill', 'validate']


# ============================================================================
# STATUS INSPECTION
# ============================================================================

def _max_date(engine, sql: str) -> Optional[date]:
    try:
        with engine.connect() as conn:
            row = conn.execute(text(sql)).fetchone()
        if row is None or row[0] is None:
            return None
        v = row[0]
        if isinstance(v, datetime):
            return v.date()
        if isinstance(v, date):
            return v
        return pd.to_datetime(v).date()
    except Exception:
        return None


def inspect_status(engine=None) -> Dict[str, Any]:
    """Survey freshness of every input the pipeline depends on.

    Returns a dict with the last meaningful date for each layer of the system,
    plus the days-since-today for each so the dashboard can color-code staleness.
    No side effects — safe to call from a Dash callback on every interval tick.
    """
    eng = engine if engine is not None else get_engine()
    own_engine = engine is None
    try:
        today = date.today()
        status: Dict[str, Any] = {'as_of': today.isoformat()}

        # Raw game data (most recent imported boxscore date).
        # game_list contains the master schedule; the v3 game_info table is the actual ingested
        # boxscore. We surface both so the user can see the gap between "scheduled" and "ingested".
        status['latest_schedule_date'] = _max_date(eng, 'SELECT MAX(GAME_DATE) FROM game_list')
        status['latest_boxscore_v3_date'] = _max_date(eng, 'SELECT MAX(gameDate) FROM boxscoresummaryv3_game_info')
        status['latest_boxscore_v2_date'] = _max_date(eng, 'SELECT MAX(GAME_DATE_EST) FROM boxscoresummaryv2_game_info')

        # Player impact cache
        status['latest_player_impact_date'] = _max_date(eng, 'SELECT MAX(compute_date) FROM player_impact')

        # Feature CSV
        if os.path.exists(FEATURES_CSV):
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(FEATURES_CSV)).date()
                csv_max = pd.read_csv(FEATURES_CSV, usecols=['GAME_DATE'])
                csv_max['GAME_DATE'] = pd.to_datetime(csv_max['GAME_DATE'])
                status['features_csv_mtime'] = mtime
                status['features_csv_max_date'] = csv_max['GAME_DATE'].max().date()
                status['features_csv_rows'] = len(csv_max)
            except Exception:
                status['features_csv_mtime'] = None
                status['features_csv_max_date'] = None
                status['features_csv_rows'] = None
        else:
            status['features_csv_mtime'] = None
            status['features_csv_max_date'] = None
            status['features_csv_rows'] = None

        # Models — latest training rows (not validation)
        for mt in ('rf_classifier', 'rf_regressor', 'nn_classifier', 'nn_regressor'):
            status[f'latest_train_{mt}'] = _max_date(
                eng,
                f"SELECT MAX(training_date) FROM model_registry "
                f"WHERE model_type='{mt}' AND (run_kind='train' OR run_kind IS NULL)"
            )
        # Most-recent train across any model
        status['latest_train_any'] = _max_date(
            eng,
            "SELECT MAX(training_date) FROM model_registry WHERE (run_kind='train' OR run_kind IS NULL)"
        )
        # Most-recent validation run
        status['latest_validation_any'] = _max_date(
            eng,
            "SELECT MAX(training_date) FROM model_registry WHERE run_kind='validation'"
        )

        # Predictions
        status['latest_prediction_date'] = _max_date(eng, 'SELECT MAX(game_date) FROM model_predictions')
        status['latest_backfilled_prediction_date'] = _max_date(
            eng, 'SELECT MAX(game_date) FROM model_predictions WHERE actual_winner IS NOT NULL'
        )

        # Convert dates → days_since for staleness UI
        for k, v in list(status.items()):
            if isinstance(v, date) and not isinstance(v, datetime):
                status[k] = v.isoformat()
                status[f'{k}_days_ago'] = (today - v).days

        return status
    finally:
        if own_engine:
            eng.dispose()


# ============================================================================
# RECOMMENDATION
# ============================================================================

def recommend(status: Optional[Dict[str, Any]] = None) -> List[Dict[str, str]]:
    """Given the current status, suggest which stages need to run and why.

    Heuristics are conservative — better to recommend a no-op stage than to skip a
    stale one. Returns a list of {'stage', 'reason'} dicts in run order.
    """
    if status is None:
        status = inspect_status()

    today = date.today()
    suggestions: List[Dict[str, str]] = []

    # 1) Boxscore data — if the latest v3 ingest is more than 2 days behind the schedule, fetch.
    sched_iso = status.get('latest_schedule_date')
    box_iso = status.get('latest_boxscore_v3_date')
    if sched_iso and box_iso:
        sched_d = pd.to_datetime(sched_iso).date()
        box_d = pd.to_datetime(box_iso).date()
        gap = (sched_d - box_d).days
        if gap >= 2:
            suggestions.append({
                'stage': 'fetch_data',
                'reason': f'Boxscore ingest is {gap} day(s) behind the schedule '
                          f'({box_iso} vs {sched_iso}). Run main_refactored.py.'
            })

    # 2) Player impact — if more than 14 days stale, refresh.
    pi_iso = status.get('latest_player_impact_date')
    if pi_iso:
        pi_d = pd.to_datetime(pi_iso).date()
        if (today - pi_d).days >= 14:
            suggestions.append({
                'stage': 'player_impact',
                'reason': f'player_impact cache last computed {(today - pi_d).days}d ago ({pi_iso}). Refresh.'
            })
    else:
        suggestions.append({'stage': 'player_impact',
                            'reason': 'player_impact table empty — populate it.'})

    # 3) Features — if the CSV is older than the latest boxscore, rebuild.
    feat_iso = status.get('features_csv_max_date')
    if not feat_iso:
        suggestions.append({'stage': 'features',
                            'reason': 'nba_ml_features.csv missing — rebuild.'})
    elif box_iso:
        feat_d = pd.to_datetime(feat_iso).date()
        box_d = pd.to_datetime(box_iso).date()
        if box_d > feat_d:
            suggestions.append({
                'stage': 'features',
                'reason': f'Features CSV ends {feat_iso}; boxscore goes to {box_iso}. Rebuild.'
            })

    # 4) Train — if the latest training row is older than features by more than 7 days, retrain.
    train_iso = status.get('latest_train_any')
    if not train_iso:
        suggestions.append({'stage': 'train', 'reason': 'No training rows in model_registry — train.'})
    elif feat_iso:
        train_d = pd.to_datetime(train_iso).date()
        feat_d = pd.to_datetime(feat_iso).date()
        if (feat_d - train_d).days >= 7:
            suggestions.append({
                'stage': 'train',
                'reason': f'Last train {train_iso}; features now go to {feat_iso}. Retrain.'
            })

    # 5) Predict — if the latest prediction is older than today, predict for today.
    pred_iso = status.get('latest_prediction_date')
    if not pred_iso or pd.to_datetime(pred_iso).date() < today:
        suggestions.append({
            'stage': 'predict',
            'reason': f'No predictions for today ({today}). Run predict_games.py --date {today}.'
        })

    # 6) Backfill — if there are predictions whose game date is past but actuals not filled.
    pred_max = status.get('latest_prediction_date')
    backfilled_max = status.get('latest_backfilled_prediction_date')
    if pred_max and (not backfilled_max or pd.to_datetime(backfilled_max).date() < pd.to_datetime(pred_max).date()):
        gap = ((pd.to_datetime(pred_max) - pd.to_datetime(backfilled_max)).days
               if backfilled_max else (today - pd.to_datetime(pred_max).date()).days)
        suggestions.append({
            'stage': 'backfill',
            'reason': f'Some past predictions still lack actual outcomes (latest backfilled '
                      f'{backfilled_max}, latest prediction {pred_max}, gap ~{gap}d).'
        })

    # 7) Validate — if no recent validation run after the last train.
    val_iso = status.get('latest_validation_any')
    if train_iso and (not val_iso or pd.to_datetime(val_iso).date() < pd.to_datetime(train_iso).date()):
        suggestions.append({
            'stage': 'validate',
            'reason': f'No validation run since the {train_iso} retrain. '
                      f'Run validate_models.py over recent games.'
        })

    return suggestions


# ============================================================================
# STAGE DEFINITIONS
# ============================================================================

@dataclass
class StageSpec:
    name: str
    description: str
    args: List[Dict[str, Any]] = field(default_factory=list)

    def build_cmd(self, **kwargs) -> List[str]:
        raise NotImplementedError


@dataclass
class FetchDataStage(StageSpec):
    name: str = 'fetch_data'
    description: str = 'Fetch raw NBA boxscore data from the nba_api into MySQL (main_refactored.py).'

    def build_cmd(self, **kwargs) -> List[str]:
        # main_refactored.py has no CLI args; it just runs run_import_parallel()
        return [sys.executable, 'data_engineering/main_refactored.py']


@dataclass
class PlayerImpactStage(StageSpec):
    name: str = 'player_impact'
    description: str = 'Refresh player_impact cache (player_impact.py --populate).'
    args: List[Dict[str, Any]] = field(default_factory=lambda: [
        {'name': 'dates', 'cli': '--date', 'type': 'list', 'help': 'One or more YYYY-MM-DD anchor dates'},
    ])

    def build_cmd(self, **kwargs) -> List[str]:
        cmd = [sys.executable, 'data_engineering/player_impact.py', '--populate']
        for d in (kwargs.get('dates') or []):
            cmd += ['--date', d]
        return cmd


@dataclass
class FeaturesStage(StageSpec):
    name: str = 'features'
    description: str = 'Rebuild nba_ml_features.csv (feature_engineering.py).'
    args: List[Dict[str, Any]] = field(default_factory=lambda: [
        {'name': 'start_date', 'cli': '--start-date', 'type': 'date', 'help': 'Earliest game date to include'},
        {'name': 'end_date', 'cli': '--end-date', 'type': 'date', 'help': 'Latest game date to include'},
        {'name': 'no_player_features', 'cli': '--no-player-features', 'type': 'flag',
         'help': 'Skip player projection features (faster)'},
    ])

    def build_cmd(self, **kwargs) -> List[str]:
        cmd = [sys.executable, 'data_engineering/feature_engineering.py']
        if kwargs.get('start_date'):
            cmd += ['--start-date', kwargs['start_date']]
        if kwargs.get('end_date'):
            cmd += ['--end-date', kwargs['end_date']]
        if kwargs.get('no_player_features'):
            cmd += ['--no-player-features']
        return cmd


@dataclass
class TrainStage(StageSpec):
    name: str = 'train'
    description: str = 'Retrain RF and NN models. Implemented as a thin wrapper invoking predict_games._force_retrain().'

    def build_cmd(self, **kwargs) -> List[str]:
        # Force retrain by importing predict_games and calling the loaders with force_retrain=True.
        # CWD will be the project root (set in run_stage_blocking), and the bootstrap inside
        # predict_games.py adds the project root to sys.path so its own cross-folder imports work.
        # But the -c subprocess starts fresh, so we must also seed sys.path before the import here.
        # E8 cleanup: XGBoost added — was previously omitted, causing the production XGB bundle
        # to drift behind RF/NN whenever this stage ran.
        code = (
            "import sys, os; "
            "sys.path.insert(0, os.getcwd()); "
            "from core.db import get_engine; "
            "from modeling.predict_games import (load_or_train_rf_models, load_or_train_pytorch_models, "
            "                                     load_or_train_xgb_models, PYTORCH_AVAILABLE, XGBOOST_AVAILABLE); "
            "eng = get_engine(); "
            "print('[pipeline.train] Forcing RF retrain...'); "
            "load_or_train_rf_models(eng, force_retrain=True); "
            "print('[pipeline.train] Forcing XGB retrain...') if XGBOOST_AVAILABLE else print('[pipeline.train] xgboost unavailable, skipping XGB'); "
            "XGBOOST_AVAILABLE and load_or_train_xgb_models(eng, force_retrain=True); "
            "print('[pipeline.train] Forcing NN retrain...') if PYTORCH_AVAILABLE else print('[pipeline.train] PyTorch unavailable, skipping NN'); "
            "PYTORCH_AVAILABLE and load_or_train_pytorch_models(eng, force_retrain=True); "
            "print('[pipeline.train] done.')"
        )
        return [sys.executable, '-c', code]


@dataclass
class PredictStage(StageSpec):
    name: str = 'predict'
    description: str = ('Run predict_games.py. Defaults to today. Set start_date to backfill '
                       'predictions across a date range (uses point-in-time team stats and '
                       'player_impact snapshots so historical predictions reflect what was '
                       'known at game time; auto-injuries are force-disabled in this mode).')
    args: List[Dict[str, Any]] = field(default_factory=lambda: [
        {'name': 'predict_date', 'cli': '--date', 'type': 'date',
         'help': 'Single game date (YYYY-MM-DD). Ignored if start_date set.'},
        {'name': 'start_date', 'cli': '--start-date', 'type': 'date',
         'help': 'Backfill mode: first date in the range to predict.'},
        {'name': 'end_date', 'cli': '--end-date', 'type': 'date',
         'help': 'Backfill mode: last date in the range (defaults to today).'},
        # `choices` derived from modeling.model_types.MODEL_TYPES so adding a new model
        # type updates this dropdown automatically (no edit to pipeline.py needed).
        {'name': 'model', 'cli': '--model', 'type': 'choice',
         'choices': _model_cli_choices(), 'default': 'both', 'help': 'Which model(s)'},
        {'name': 'no_shap', 'cli': '--no-shap', 'type': 'flag', 'help': 'Skip SHAP (much faster — recommended for backfill)'},
        {'name': 'no_plot', 'cli': '--no-plot', 'type': 'flag', 'help': 'Skip histogram plots (forced on in backfill)'},
        {'name': 'no_log', 'cli': '--no-log', 'type': 'flag', 'help': 'Skip logging predictions to DB'},
    ])

    def build_cmd(self, **kwargs) -> List[str]:
        cmd = [sys.executable, 'modeling/predict_games.py']
        # If a range is supplied, use it; otherwise fall back to single --date.
        if kwargs.get('start_date'):
            cmd += ['--start-date', kwargs['start_date']]
            if kwargs.get('end_date'):
                cmd += ['--end-date', kwargs['end_date']]
        else:
            cmd += ['--date', kwargs.get('predict_date') or date.today().isoformat()]
        if kwargs.get('model'):
            cmd += ['--model', kwargs['model']]
        for flag in ('no_shap', 'no_plot', 'no_log'):
            if kwargs.get(flag):
                cmd += ['--' + flag.replace('_', '-')]
        return cmd


@dataclass
class BackfillStage(StageSpec):
    name: str = 'backfill'
    description: str = 'Backfill actual outcomes onto past predictions (prediction_tracker.py --backfill).'
    args: List[Dict[str, Any]] = field(default_factory=lambda: [
        {'name': 'lookback', 'cli': '--lookback', 'type': 'int', 'default': 30,
         'help': 'Days to look back for backfill (default 30; use 200+ after long idle stretch)'},
    ])

    def build_cmd(self, **kwargs) -> List[str]:
        return [sys.executable, 'modeling/prediction_tracker.py', '--backfill',
                '--lookback', str(kwargs.get('lookback') or 30)]


@dataclass
class ValidateStage(StageSpec):
    name: str = 'validate'
    description: str = 'Held-out validation of saved models over a recent window (validate_models.py).'
    args: List[Dict[str, Any]] = field(default_factory=lambda: [
        {'name': 'days', 'cli': '--days', 'type': 'int', 'default': 60,
         'help': 'Window size in days back from --end (default 60)'},
        {'name': 'start_date', 'cli': '--start', 'type': 'date', 'help': 'Window start (overrides --days)'},
        {'name': 'end_date', 'cli': '--end', 'type': 'date', 'help': 'Window end'},
        {'name': 'model', 'cli': '--model', 'type': 'choice',
         'choices': ['rf', 'nn', 'both'], 'default': 'both', 'help': 'Which model(s)'},
    ])

    def build_cmd(self, **kwargs) -> List[str]:
        cmd = [sys.executable, 'modeling/validate_models.py']
        if kwargs.get('days'):
            cmd += ['--days', str(kwargs['days'])]
        if kwargs.get('start_date'):
            cmd += ['--start', kwargs['start_date']]
        if kwargs.get('end_date'):
            cmd += ['--end', kwargs['end_date']]
        if kwargs.get('model'):
            cmd += ['--model', kwargs['model']]
        return cmd


STAGE_REGISTRY: Dict[str, StageSpec] = {
    'fetch_data': FetchDataStage(),
    'player_impact': PlayerImpactStage(),
    'features': FeaturesStage(),
    'train': TrainStage(),
    'predict': PredictStage(),
    'backfill': BackfillStage(),
    'validate': ValidateStage(),
}


def get_stage_specs_for_ui() -> List[Dict[str, Any]]:
    """Serializable stage definitions for the Operations tab to render forms from."""
    out = []
    for name in STAGE_ORDER:
        spec = STAGE_REGISTRY[name]
        out.append({
            'name': spec.name,
            'description': spec.description,
            'args': spec.args,
        })
    return out


# ============================================================================
# EXECUTION
# ============================================================================

def _write_state(state: Dict[str, Any]) -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    tmp = STATE_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fp:
        json.dump(state, fp, default=str, indent=2)
    os.replace(tmp, STATE_FILE)


def read_state() -> Dict[str, Any]:
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, encoding='utf-8') as fp:
            return json.load(fp)
    except Exception:
        return {}


def run_stage_blocking(stage_name: str, run_id: str, stage_kwargs: Dict[str, Any]) -> int:
    """Run a single stage to completion, streaming output to logs/pipeline_<run_id>.log."""
    spec = STAGE_REGISTRY[stage_name]
    cmd = spec.build_cmd(**stage_kwargs)
    log_path = os.path.join(LOG_DIR, f'pipeline_{run_id}.log')
    os.makedirs(LOG_DIR, exist_ok=True)

    header = (
        f"\n{'='*72}\n"
        f"[{datetime.now().isoformat(timespec='seconds')}] STAGE: {stage_name}\n"
        f"  description: {spec.description}\n"
        f"  command:     {' '.join(cmd)}\n"
        f"{'='*72}\n"
    )
    with open(log_path, 'a', encoding='utf-8') as fp:
        fp.write(header)
        fp.flush()
        proc = subprocess.Popen(cmd, cwd=REPO_ROOT, stdout=fp, stderr=subprocess.STDOUT)
        return_code = proc.wait()
        fp.write(f"\n[{datetime.now().isoformat(timespec='seconds')}] stage '{stage_name}' "
                 f"exited with code {return_code}\n")
    return return_code


def run_pipeline_blocking(stages: List[str], per_stage_kwargs: Dict[str, Dict[str, Any]],
                          run_id: Optional[str] = None) -> Dict[str, Any]:
    """Run a sequence of stages, halting on first non-zero return code.

    Returns a final state dict describing what ran, exit codes, and the log path.
    Updates STATE_FILE between every stage so the dashboard can poll progress.
    """
    if run_id is None:
        run_id = datetime.now().strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:6]
    log_path = os.path.join(LOG_DIR, f'pipeline_{run_id}.log')

    state: Dict[str, Any] = {
        'run_id': run_id,
        'started_at': datetime.now().isoformat(),
        'finished_at': None,
        'log_path': log_path,
        'stages_requested': list(stages),
        'per_stage_kwargs': per_stage_kwargs,
        'stage_results': [],
        'current_stage': None,
        'status': 'running',
    }
    _write_state(state)

    for stage_name in stages:
        state['current_stage'] = stage_name
        _write_state(state)
        kwargs = per_stage_kwargs.get(stage_name, {})
        try:
            rc = run_stage_blocking(stage_name, run_id, kwargs)
        except Exception as e:
            state['stage_results'].append({'stage': stage_name, 'exit_code': -1, 'error': str(e),
                                           'finished_at': datetime.now().isoformat()})
            state['status'] = 'failed'
            state['finished_at'] = datetime.now().isoformat()
            state['current_stage'] = None
            _write_state(state)
            return state

        state['stage_results'].append({'stage': stage_name, 'exit_code': rc,
                                       'finished_at': datetime.now().isoformat()})
        if rc != 0:
            state['status'] = 'failed'
            state['finished_at'] = datetime.now().isoformat()
            state['current_stage'] = None
            _write_state(state)
            return state

    state['status'] = 'completed'
    state['finished_at'] = datetime.now().isoformat()
    state['current_stage'] = None
    _write_state(state)
    return state


def launch_pipeline_background(stages: List[str], per_stage_kwargs: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Spawn `python pipeline.py run` as a detached subprocess so the caller (e.g. a Dash
    callback) returns immediately. Returns the descriptor written to STATE_FILE.

    The launched process will keep STATE_FILE updated; poll read_state() for progress.
    """
    run_id = datetime.now().strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:6]
    payload = {
        'stages': stages,
        'per_stage_kwargs': per_stage_kwargs,
        'run_id': run_id,
    }
    payload_path = os.path.join(LOG_DIR, f'pipeline_{run_id}.request.json')
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(payload_path, 'w', encoding='utf-8') as fp:
        json.dump(payload, fp)

    creationflags = 0
    if os.name == 'nt':
        # Detach so parent (Dash) exit doesn't kill the run; also no console window.
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000008  # DETACHED_PROCESS

    subprocess.Popen(
        [sys.executable, 'orchestration/pipeline.py', 'run-from-file', '--payload', payload_path],
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
        close_fds=True,
    )

    # Seed initial state so the UI has something to show before the child writes.
    seed = {
        'run_id': run_id,
        'started_at': datetime.now().isoformat(),
        'finished_at': None,
        'log_path': os.path.join(LOG_DIR, f'pipeline_{run_id}.log'),
        'stages_requested': list(stages),
        'per_stage_kwargs': per_stage_kwargs,
        'stage_results': [],
        'current_stage': None,
        'status': 'queued',
    }
    _write_state(seed)
    return seed


def tail_log(log_path: str, n_lines: int = 200) -> str:
    if not log_path or not os.path.exists(log_path):
        return ''
    try:
        with open(log_path, 'rb') as fp:
            fp.seek(0, os.SEEK_END)
            size = fp.tell()
            chunk = min(size, 64 * 1024)
            fp.seek(size - chunk)
            data = fp.read().decode('utf-8', errors='replace')
        lines = data.splitlines()
        return '\n'.join(lines[-n_lines:])
    except Exception as e:
        return f'<could not read log: {e}>'


# ============================================================================
# CLI
# ============================================================================

def _expand_stages(token: str) -> List[str]:
    if token == 'all':
        return list(STAGE_ORDER)
    parts = [s.strip() for s in token.split(',') if s.strip()]
    unknown = [s for s in parts if s not in STAGE_REGISTRY]
    if unknown:
        raise SystemExit(f"Unknown stage(s): {unknown}. Valid: {STAGE_ORDER}")
    return parts


def main():
    parser = argparse.ArgumentParser(description='NBA Stats Pipeline Orchestrator')
    sub = parser.add_subparsers(dest='cmd', required=True)

    sub.add_parser('status', help='Print freshness report for every input the pipeline uses.')
    sub.add_parser('recommend', help='Print suggested stages based on staleness.')

    p_run = sub.add_parser('run', help='Run one or more stages in order.')
    p_run.add_argument('--stages', required=True,
                       help='Comma-separated stage names, or "all". Choices: ' + ','.join(STAGE_ORDER))
    p_run.add_argument('--predict-date', type=str, help='For predict stage: single target game date (YYYY-MM-DD).')
    p_run.add_argument('--predict-start', type=str, default=None,
                       help='For predict stage: backfill mode — first date in range (YYYY-MM-DD). '
                            'When set, --predict-date is ignored.')
    p_run.add_argument('--predict-end', type=str, default=None,
                       help='For predict stage: backfill mode — last date in range (YYYY-MM-DD, '
                            'inclusive). Defaults to today.')
    p_run.add_argument('--predict-model', type=str, default='both', help='For predict stage: rf|nn|nn-embed|both.')
    p_run.add_argument('--predict-no-shap', action='store_true',
                       help='For predict stage: pass --no-shap (much faster, recommended for backfill).')
    p_run.add_argument('--validate-days', type=int, default=60, help='For validate stage: window in days.')
    p_run.add_argument('--validate-start', type=str, default=None, help='For validate stage: window start.')
    p_run.add_argument('--validate-end', type=str, default=None, help='For validate stage: window end.')
    p_run.add_argument('--backfill-lookback', type=int, default=30,
                       help='For backfill stage: --lookback days passed to prediction_tracker.py.')

    p_runfile = sub.add_parser('run-from-file',
                                help='Internal: execute a stages payload from a JSON file '
                                     '(used by the background launcher).')
    p_runfile.add_argument('--payload', required=True)

    args = parser.parse_args()

    if args.cmd == 'status':
        s = inspect_status()
        print(json.dumps(s, indent=2, default=str))
        return

    if args.cmd == 'recommend':
        recs = recommend()
        if not recs:
            print('Nothing to do — every layer is fresh.')
            return
        print('Recommended stages:')
        for r in recs:
            print(f"  - {r['stage']}: {r['reason']}")
        return

    if args.cmd == 'run':
        stages = _expand_stages(args.stages)
        per_stage_kwargs: Dict[str, Dict[str, Any]] = {
            'predict': {'predict_date': args.predict_date, 'model': args.predict_model,
                        'start_date': args.predict_start, 'end_date': args.predict_end,
                        'no_shap': args.predict_no_shap},
            'validate': {'days': args.validate_days, 'start_date': args.validate_start,
                         'end_date': args.validate_end},
            'backfill': {'lookback': args.backfill_lookback},
        }
        state = run_pipeline_blocking(stages, per_stage_kwargs)
        print(json.dumps(state, indent=2, default=str))
        sys.exit(0 if state['status'] == 'completed' else 1)

    if args.cmd == 'run-from-file':
        with open(args.payload, encoding='utf-8') as fp:
            payload = json.load(fp)
        state = run_pipeline_blocking(
            stages=payload['stages'],
            per_stage_kwargs=payload.get('per_stage_kwargs', {}),
            run_id=payload.get('run_id'),
        )
        sys.exit(0 if state['status'] == 'completed' else 1)


if __name__ == '__main__':
    main()
