"""Experiment-loop results in MySQL: header, per-arm metrics, paired tests.

Companion to ``core/model_registry.py`` for the autonomous experiment loop
(2026-07). Three tables:

``experiments``
    One row per experiment: hypothesis, spec, verdict, tuning-log anchor.
``experiment_results``
    Per (experiment, stage, arm, model, window, seed) metrics. ``seed = -1``
    means "pooled across seeds" (bootstrap summary). A real column instead of
    NULL because MySQL unique keys admit unlimited NULL duplicates.
``experiment_comparisons``
    Paired-test rows arm-vs-baseline per (stage, model, window), including the
    mechanical gate outcome once evaluated.

Design rules:
  - Harnesses stay DB-free — they write JSON to ``outputs/`` (repo convention).
    The analyze phase calls ``ingest_ab_json`` to mirror a result JSON into the
    DB. Ingest is idempotent: delete-then-insert per (experiment_id, stage).
  - One aggregate ``model_registry`` row per (arm, family, task) via
    ``register_arm_models`` (``run_kind='experiment'``, never current) so
    experiments appear in the registry timeline next to trains/validations.

Expected JSON shape (written by ``experiments/loop_ab.py``)::

    {
      "experiment_id": "E22", "stage": "w5",
      "baseline_label": "full_573",
      "models": ["RF", "XGB"], "seeds": [...], "n_bootstrap": 1000,
      "arms_resolved": {"top250": {"n_features": 250, ...}, ...},
      "windows": {
        "W5": {
          "test_start": "2026-03-15", "test_end": "2026-04-15",
          "n_train": 6021, "n_test": 230,
          "summary":  {"<arm>|<MODEL>|<metric>": {"mean":..,"ci_lo":..,"ci_hi":..}},
          "per_seed": {"<arm>|<MODEL>|<seed>": {"acc":..,"auc":..,"mae":..,...}},
          "paired":   {"<arm>|<MODEL>": {...e3-style paired stats...}}
        }, ...
      },
      "pooled": {"summary": {...}, "paired": {...}}   # windows stage only
    }
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
from sqlalchemy import text

EXPERIMENTS_TABLE = 'experiments'
RESULTS_TABLE = 'experiment_results'
COMPARISONS_TABLE = 'experiment_comparisons'

_SUMMARY_METRICS = ('acc', 'auc', 'mae', 'logloss', 'brier', 'ece')


# ============================================================================
# DDL
# ============================================================================

def ensure_experiment_tables(engine) -> None:
    """Create the three experiment tables if they don't exist (idempotent)."""
    ddl_experiments = f"""
    CREATE TABLE IF NOT EXISTS {EXPERIMENTS_TABLE} (
        experiment_id       VARCHAR(32)  NOT NULL,
        title               VARCHAR(200) NOT NULL,
        hypothesis          TEXT NULL,
        spec_json           JSON NULL,
        feature_set_version VARCHAR(40) NULL,
        csv_path            VARCHAR(255) NULL,
        status              VARCHAR(20) NOT NULL DEFAULT 'running',
        verdict             VARCHAR(20) NULL,
        decision_notes      TEXT NULL,
        tuning_log_anchor   VARCHAR(120) NULL,
        started_at          TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
        finished_at         TIMESTAMP NULL,
        PRIMARY KEY (experiment_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """
    ddl_results = f"""
    CREATE TABLE IF NOT EXISTS {RESULTS_TABLE} (
        result_id     BIGINT AUTO_INCREMENT PRIMARY KEY,
        experiment_id VARCHAR(32) NOT NULL,
        stage         VARCHAR(20) NOT NULL,
        arm           VARCHAR(64) NOT NULL,
        model_type    VARCHAR(16) NOT NULL,
        window_name   VARCHAR(32) NOT NULL,
        test_start    DATE NULL,
        test_end      DATE NULL,
        seed          INT NOT NULL DEFAULT -1,
        n_train       INT NULL,
        n_test        INT NULL,
        n_features    INT NULL,
        acc  DOUBLE NULL, acc_ci_lo DOUBLE NULL, acc_ci_hi DOUBLE NULL,
        auc  DOUBLE NULL, auc_ci_lo DOUBLE NULL, auc_ci_hi DOUBLE NULL,
        mae  DOUBLE NULL, mae_ci_lo DOUBLE NULL, mae_ci_hi DOUBLE NULL,
        logloss DOUBLE NULL, brier DOUBLE NULL, ece DOUBLE NULL,
        extra_json    JSON NULL,
        created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_res (experiment_id, stage, arm, model_type, window_name, seed),
        KEY idx_exp_res (experiment_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """
    ddl_comparisons = f"""
    CREATE TABLE IF NOT EXISTS {COMPARISONS_TABLE} (
        comparison_id  BIGINT AUTO_INCREMENT PRIMARY KEY,
        experiment_id  VARCHAR(32) NOT NULL,
        stage          VARCHAR(20) NOT NULL,
        arm            VARCHAR(64) NOT NULL,
        baseline_arm   VARCHAR(64) NOT NULL,
        model_type     VARCHAR(16) NOT NULL,
        window_name    VARCHAR(32) NOT NULL,
        mcnemar_stat   DOUBLE NULL, mcnemar_p DOUBLE NULL,
        arm_wins       INT NULL,    base_wins INT NULL,
        paired_t_stat  DOUBLE NULL, paired_t_p DOUBLE NULL,
        mae_diff       DOUBLE NULL, mae_diff_sd DOUBLE NULL,
        mae_diff_ci_lo DOUBLE NULL, mae_diff_ci_hi DOUBLE NULL, mae_diff_p DOUBLE NULL,
        auc_diff       DOUBLE NULL, auc_diff_ci_lo DOUBLE NULL,
        auc_diff_ci_hi DOUBLE NULL, auc_diff_p DOUBLE NULL,
        acc_diff       DOUBLE NULL, acc_diff_ci_lo DOUBLE NULL,
        acc_diff_ci_hi DOUBLE NULL, acc_diff_p DOUBLE NULL,
        gate           VARCHAR(20) NULL,
        extra_json     JSON NULL,
        created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_cmp (experiment_id, stage, arm, baseline_arm, model_type, window_name),
        KEY idx_exp_cmp (experiment_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """
    with engine.begin() as conn:
        conn.execute(text(ddl_experiments))
        conn.execute(text(ddl_results))
        conn.execute(text(ddl_comparisons))


# ============================================================================
# Header rows
# ============================================================================

def start_experiment(engine, experiment_id: str, title: str, hypothesis: str,
                     spec: Optional[dict] = None,
                     feature_set_version: Optional[str] = None,
                     csv_path: Optional[str] = None) -> None:
    """Pre-register an experiment (hypothesis written BEFORE results exist)."""
    ensure_experiment_tables(engine)
    with engine.begin() as conn:
        conn.execute(text(
            f"REPLACE INTO {EXPERIMENTS_TABLE} "
            "(experiment_id, title, hypothesis, spec_json, feature_set_version,"
            " csv_path, status) "
            "VALUES (:eid, :title, :hyp, :spec, :fsv, :csv, 'running')"
        ), {'eid': experiment_id, 'title': title, 'hyp': hypothesis,
            'spec': json.dumps(spec) if spec is not None else None,
            'fsv': feature_set_version, 'csv': csv_path})


def finish_experiment(engine, experiment_id: str, verdict: str,
                      decision_notes: str,
                      tuning_log_anchor: Optional[str] = None,
                      status: str = 'done') -> None:
    """Record the final verdict: KEEP | REJECT | INCONCLUSIVE | INFRA_FAIL."""
    with engine.begin() as conn:
        conn.execute(text(
            f"UPDATE {EXPERIMENTS_TABLE} SET status = :status, verdict = :verdict,"
            " decision_notes = :notes, tuning_log_anchor = :anchor,"
            " finished_at = CURRENT_TIMESTAMP WHERE experiment_id = :eid"
        ), {'status': status, 'verdict': verdict, 'notes': decision_notes,
            'anchor': tuning_log_anchor, 'eid': experiment_id})


# ============================================================================
# Ingest
# ============================================================================

def _f(value) -> Optional[float]:
    """Coerce to float, passing None through (numpy/str tolerant)."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # NaN -> NULL


def _result_row(experiment_id: str, stage: str, arm: str, model: str,
                window_name: str, window: dict, seed: int,
                metrics: Dict[str, Any], n_features: Optional[int]) -> dict:
    row = {
        'eid': experiment_id, 'stage': stage, 'arm': arm, 'model': model,
        'win': window_name,
        'test_start': window.get('test_start'), 'test_end': window.get('test_end'),
        'seed': seed,
        'n_train': window.get('n_train'), 'n_test': window.get('n_test'),
        'n_features': n_features,
    }
    for m in _SUMMARY_METRICS:
        row[m] = _f(metrics.get(m))
    for m in ('acc', 'auc', 'mae'):
        row[f'{m}_ci_lo'] = _f(metrics.get(f'{m}_ci_lo'))
        row[f'{m}_ci_hi'] = _f(metrics.get(f'{m}_ci_hi'))
    known = set(_SUMMARY_METRICS) | {f'{m}_ci_{s}' for m in ('acc', 'auc', 'mae')
                                     for s in ('lo', 'hi')}
    extra = {k: v for k, v in metrics.items() if k not in known}
    row['extra'] = json.dumps(extra, default=str) if extra else None
    return row


_INSERT_RESULT = text(f"""
    INSERT INTO {RESULTS_TABLE}
    (experiment_id, stage, arm, model_type, window_name, test_start, test_end,
     seed, n_train, n_test, n_features,
     acc, acc_ci_lo, acc_ci_hi, auc, auc_ci_lo, auc_ci_hi,
     mae, mae_ci_lo, mae_ci_hi, logloss, brier, ece, extra_json)
    VALUES
    (:eid, :stage, :arm, :model, :win, :test_start, :test_end,
     :seed, :n_train, :n_test, :n_features,
     :acc, :acc_ci_lo, :acc_ci_hi, :auc, :auc_ci_lo, :auc_ci_hi,
     :mae, :mae_ci_lo, :mae_ci_hi, :logloss, :brier, :ece, :extra)
""")

_INSERT_COMPARISON = text(f"""
    INSERT INTO {COMPARISONS_TABLE}
    (experiment_id, stage, arm, baseline_arm, model_type, window_name,
     mcnemar_stat, mcnemar_p, arm_wins, base_wins,
     paired_t_stat, paired_t_p, mae_diff, mae_diff_sd,
     mae_diff_ci_lo, mae_diff_ci_hi, mae_diff_p,
     auc_diff, auc_diff_ci_lo, auc_diff_ci_hi, auc_diff_p,
     acc_diff, acc_diff_ci_lo, acc_diff_ci_hi, acc_diff_p, gate, extra_json)
    VALUES
    (:eid, :stage, :arm, :base, :model, :win,
     :mcnemar_stat, :mcnemar_p, :arm_wins, :base_wins,
     :paired_t_stat, :paired_t_p, :mae_diff, :mae_diff_sd,
     :mae_diff_ci_lo, :mae_diff_ci_hi, :mae_diff_p,
     :auc_diff, :auc_diff_ci_lo, :auc_diff_ci_hi, :auc_diff_p,
     :acc_diff, :acc_diff_ci_lo, :acc_diff_ci_hi, :acc_diff_p, :gate, :extra)
""")


def _comparison_row(experiment_id: str, stage: str, arm: str, base: str,
                    model: str, window_name: str, paired: Dict[str, Any],
                    gate: Optional[str] = None) -> dict:
    known = {
        'mcnemar_stat', 'mcnemar_p', 'cfg_wins', 'base_wins',
        'paired_t_stat', 'paired_t_p', 'mae_diff_mean', 'mae_diff_sd',
        'mae_diff_ci_lo', 'mae_diff_ci_hi', 'mae_diff_p',
        'auc_diff_mean', 'auc_diff_ci_lo', 'auc_diff_ci_hi', 'auc_diff_p',
        'acc_diff_mean', 'acc_diff_ci_lo', 'acc_diff_ci_hi', 'acc_diff_p',
    }
    extra = {k: v for k, v in paired.items() if k not in known}
    return {
        'eid': experiment_id, 'stage': stage, 'arm': arm, 'base': base,
        'model': model, 'win': window_name,
        'mcnemar_stat': _f(paired.get('mcnemar_stat')),
        'mcnemar_p': _f(paired.get('mcnemar_p')),
        'arm_wins': paired.get('cfg_wins'), 'base_wins': paired.get('base_wins'),
        'paired_t_stat': _f(paired.get('paired_t_stat')),
        'paired_t_p': _f(paired.get('paired_t_p')),
        'mae_diff': _f(paired.get('mae_diff_mean')),
        'mae_diff_sd': _f(paired.get('mae_diff_sd')),
        'mae_diff_ci_lo': _f(paired.get('mae_diff_ci_lo')),
        'mae_diff_ci_hi': _f(paired.get('mae_diff_ci_hi')),
        'mae_diff_p': _f(paired.get('mae_diff_p')),
        'auc_diff': _f(paired.get('auc_diff_mean')),
        'auc_diff_ci_lo': _f(paired.get('auc_diff_ci_lo')),
        'auc_diff_ci_hi': _f(paired.get('auc_diff_ci_hi')),
        'auc_diff_p': _f(paired.get('auc_diff_p')),
        'acc_diff': _f(paired.get('acc_diff_mean')),
        'acc_diff_ci_lo': _f(paired.get('acc_diff_ci_lo')),
        'acc_diff_ci_hi': _f(paired.get('acc_diff_ci_hi')),
        'acc_diff_p': _f(paired.get('acc_diff_p')),
        'gate': gate,
        'extra': json.dumps(extra, default=str) if extra else None,
    }


def ingest_ab_json(engine, experiment_id: str, json_path: str,
                   stage: Optional[str] = None) -> dict:
    """Mirror a loop_ab result JSON into the experiment tables.

    Idempotent: deletes all rows for (experiment_id, stage) first. Returns
    counts of inserted rows. ``stage`` defaults to the JSON's own stage field.
    """
    ensure_experiment_tables(engine)
    with open(json_path) as f:
        data = json.load(f)
    stage = stage or data['stage']
    arms_resolved = data.get('arms_resolved', {})
    windows = data.get('windows', {})

    result_rows: List[dict] = []
    comparison_rows: List[dict] = []

    def n_feat(arm: str) -> Optional[int]:
        info = arms_resolved.get(arm, {})
        return info.get('n_features')

    for window_name, window in windows.items():
        for key, metrics in window.get('summary', {}).items():
            arm, model, metric = key.split('|')
            # summary is keyed per-metric; collapse to one row per (arm, model)
            # lazily via a dict merge below.
            metrics = dict(metrics)
            metrics_key = (arm, model)
            merged = next((r for r in result_rows
                           if r.get('_k') == (window_name,) + metrics_key), None)
            if merged is None:
                merged = _result_row(experiment_id, stage, arm, model,
                                     window_name, window, -1, {}, n_feat(arm))
                merged['_k'] = (window_name,) + metrics_key
                result_rows.append(merged)
            merged[metric] = _f(metrics.get('mean'))
            merged[f'{metric}_ci_lo'] = _f(metrics.get('ci_lo')) if metric in ('acc', 'auc', 'mae') else merged.get(f'{metric}_ci_lo')
            merged[f'{metric}_ci_hi'] = _f(metrics.get('ci_hi')) if metric in ('acc', 'auc', 'mae') else merged.get(f'{metric}_ci_hi')

        for key, metrics in window.get('per_seed', {}).items():
            arm, model, seed = key.split('|')
            result_rows.append(_result_row(
                experiment_id, stage, arm, model, window_name, window,
                int(seed), dict(metrics), n_feat(arm)))

        base = data.get('baseline_label')
        for key, paired in window.get('paired', {}).items():
            arm, model = key.split('|')
            comparison_rows.append(_comparison_row(
                experiment_id, stage, arm, base, model, window_name, paired))

    pooled = data.get('pooled') or {}
    if pooled:
        pooled_window = {'test_start': None, 'test_end': None,
                         'n_train': None, 'n_test': pooled.get('n_test')}
        for key, metrics in pooled.get('summary', {}).items():
            arm, model, metric = key.split('|')
            merged = next((r for r in result_rows
                           if r.get('_k') == ('pooled', arm, model)), None)
            if merged is None:
                merged = _result_row(experiment_id, stage, arm, model,
                                     'pooled', pooled_window, -1, {}, n_feat(arm))
                merged['_k'] = ('pooled', arm, model)
                result_rows.append(merged)
            merged[metric] = _f(metrics.get('mean'))
        for key, paired in pooled.get('paired', {}).items():
            arm, model = key.split('|')
            comparison_rows.append(_comparison_row(
                experiment_id, stage, arm, data.get('baseline_label'),
                model, 'pooled', paired))

    result_keys = ('eid', 'stage', 'arm', 'model', 'win', 'test_start',
                   'test_end', 'seed', 'n_train', 'n_test', 'n_features',
                   'acc', 'acc_ci_lo', 'acc_ci_hi', 'auc', 'auc_ci_lo',
                   'auc_ci_hi', 'mae', 'mae_ci_lo', 'mae_ci_hi',
                   'logloss', 'brier', 'ece', 'extra')

    with engine.begin() as conn:
        conn.execute(text(
            f"DELETE FROM {RESULTS_TABLE} "
            "WHERE experiment_id = :eid AND stage = :stage"
        ), {'eid': experiment_id, 'stage': stage})
        conn.execute(text(
            f"DELETE FROM {COMPARISONS_TABLE} "
            "WHERE experiment_id = :eid AND stage = :stage"
        ), {'eid': experiment_id, 'stage': stage})
        for row in result_rows:
            conn.execute(_INSERT_RESULT, {k: row.get(k) for k in result_keys})
        for row in comparison_rows:
            conn.execute(_INSERT_COMPARISON, row)

    return {'results': len(result_rows), 'comparisons': len(comparison_rows)}


def set_comparison_gate(engine, experiment_id: str, stage: str, arm: str,
                        model_type: str, window_name: str, gate: str) -> None:
    """Record the mechanical gate outcome ('pass'/'fail') on a comparison row."""
    with engine.begin() as conn:
        conn.execute(text(
            f"UPDATE {COMPARISONS_TABLE} SET gate = :gate "
            "WHERE experiment_id = :eid AND stage = :stage AND arm = :arm "
            "AND model_type = :model AND window_name = :win"
        ), {'gate': gate, 'eid': experiment_id, 'stage': stage, 'arm': arm,
            'model': model_type, 'win': window_name})


# ============================================================================
# Registry bridge
# ============================================================================

def register_arm_models(engine, experiment_id: str, json_path: str,
                        arms: Optional[List[str]] = None,
                        date_tag: Optional[str] = None,
                        window_name: str = 'W5') -> List[str]:
    """One aggregate model_registry row per (arm, family, task).

    Uses run_kind='experiment', set_as_current=False and an explicit
    version_override so experiment rows sit in the registry timeline without
    ever displacing production. Metrics come from the given window's pooled
    bootstrap summary. Full pruned column lists live in outputs/ JSONs, not
    the registry (feature_names truncates at 100 anyway).
    """
    from core.model_registry import register_model

    with open(json_path) as f:
        data = json.load(f)
    window = data['windows'][window_name]
    summary = window['summary']
    arms_resolved = data.get('arms_resolved', {})
    models = data.get('models', [])
    date_tag = date_tag or datetime.now().strftime('%Y%m%d')

    versions: List[str] = []
    for arm in (arms if arms is not None else list(arms_resolved)):
        info = arms_resolved.get(arm, {})
        n_features = info.get('n_features') or 0
        lineage = {
            'experiment_id': experiment_id, 'arm': arm,
            'feature_set_version': (data.get('csv_meta') or {}).get('feature_set_version'),
            'config': info,
        }
        for family in models:
            def s(metric):
                entry = summary.get(f'{arm}|{family}|{metric}')
                return _f(entry.get('mean')) if entry else None
            common = dict(
                feature_count=n_features,
                training_samples=window.get('n_train') or 0,
                test_samples=window.get('n_test') or 0,
                file_path=json_path,
                feature_names=[],
                set_as_current=False,
                test_start_date=window.get('test_start'),
                test_end_date=window.get('test_end'),
                hyperparameters=lineage,
                notes=f'{experiment_id} arm={arm} window={window_name} (loop_ab pooled bootstrap means)',
                run_kind='experiment',
            )
            v_clf = register_model(
                engine, f'{family.lower()}_classifier',
                accuracy=s('acc'), auc=s('auc'),
                version_override=f'{experiment_id.lower()}_{arm}_{family.lower()}_clf_{date_tag}',
                **common)
            v_reg = register_model(
                engine, f'{family.lower()}_regressor',
                mae=s('mae'),
                version_override=f'{experiment_id.lower()}_{arm}_{family.lower()}_reg_{date_tag}',
                **common)
            versions.extend([v_clf, v_reg])
    return versions


# ============================================================================
# Read-back
# ============================================================================

def load_experiment(engine, experiment_id: str) -> Dict[str, pd.DataFrame]:
    """Return {'header', 'results', 'comparisons'} DataFrames for one experiment."""
    ensure_experiment_tables(engine)
    out = {}
    with engine.connect() as conn:
        out['header'] = pd.read_sql(text(
            f"SELECT * FROM {EXPERIMENTS_TABLE} WHERE experiment_id = :eid"),
            conn, params={'eid': experiment_id})
        out['results'] = pd.read_sql(text(
            f"SELECT * FROM {RESULTS_TABLE} WHERE experiment_id = :eid "
            "ORDER BY stage, window_name, arm, model_type, seed"),
            conn, params={'eid': experiment_id})
        out['comparisons'] = pd.read_sql(text(
            f"SELECT * FROM {COMPARISONS_TABLE} WHERE experiment_id = :eid "
            "ORDER BY stage, window_name, arm, model_type"),
            conn, params={'eid': experiment_id})
    return out


def delete_experiment(engine, experiment_id: str,
                      delete_registry_rows: bool = False) -> None:
    """Remove an experiment's rows (used for smoke-test cleanup)."""
    with engine.begin() as conn:
        for table in (RESULTS_TABLE, COMPARISONS_TABLE, EXPERIMENTS_TABLE):
            conn.execute(text(
                f"DELETE FROM {table} WHERE experiment_id = :eid"),
                {'eid': experiment_id})
        if delete_registry_rows:
            conn.execute(text(
                "DELETE FROM model_registry WHERE run_kind = 'experiment' "
                "AND model_version LIKE :prefix"),
                {'prefix': f'{experiment_id.lower()}_%'})
