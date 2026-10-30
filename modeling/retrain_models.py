"""Retrain the production game models together, and fail loudly if any didn't.

Backs the pipeline's ``train`` stage (weekly cloud retrain). Replaces an inline
``python -c`` chain with two gaps found in P-2 (2026-10-30):

  1. One exception in RF training aborted the process, so XGB and NN silently
     kept last week's bundles.
  2. A missing xgboost / torch import was a print line, not a failure - the
     same silent skip that left XGB un-run for all of 2025-26 (E19 Finding 3).

Now each requested model trains in its own try block, a missing library counts
as a failure, and after training the three ``*_current`` bundles must agree on
data_through_date / feature_set_version / feature list (modeling/bundle_sync).
Any failure prints ``ERROR: RETRAIN_FAILED ...`` (the CloudWatch ERROR filter
emails on it) and exits non-zero, which fails the pipeline stage.

Usage:
    python modeling/retrain_models.py                 # rf,xgb,nn
    python modeling/retrain_models.py --models rf,nn
"""
from __future__ import annotations

# torch first (Windows MKL import order) - predict_games does the same.
try:
    import torch  # noqa: F401
except (ImportError, OSError):
    pass

import os
import sys
import traceback

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)
if os.getcwd() != _PROJECT_ROOT:
    os.chdir(_PROJECT_ROOT)

import argparse

from modeling.bundle_sync import MODEL_KEYS, check_bundle_sync


def _trainers():
    from modeling import predict_games as pg
    return {
        'rf': (True, pg.load_or_train_rf_models, 'scikit-learn'),
        'xgb': (pg.XGBOOST_AVAILABLE, pg.load_or_train_xgb_models, 'xgboost'),
        'nn': (pg.PYTORCH_AVAILABLE, pg.load_or_train_pytorch_models, 'torch'),
    }


def retrain(models) -> int:
    from core.db import get_engine

    trainers = _trainers()
    engine = get_engine()
    failed = []
    try:
        for key in models:
            available, train_fn, lib = trainers[key]
            if not available:
                print(f'ERROR: RETRAIN_FAILED model={key} reason={lib} not importable', flush=True)
                failed.append(key)
                continue
            print(f'[retrain] {key}: training...', flush=True)
            try:
                train_fn(engine, force_retrain=True)
                print(f'[retrain] {key}: done', flush=True)
            except Exception as exc:
                traceback.print_exc()
                print(f'ERROR: RETRAIN_FAILED model={key} reason={type(exc).__name__}: {exc}',
                      flush=True)
                failed.append(key)
    finally:
        engine.dispose()

    in_sync, lines = check_bundle_sync(models)
    print('[retrain] bundle sync:', 'OK' if in_sync else 'MISMATCH')
    for line in lines:
        print(line)
    if not in_sync:
        print('ERROR: RETRAIN_FAILED reason=bundles out of sync after training', flush=True)

    if failed or not in_sync:
        return 1
    print(f'[retrain] all {len(models)} models retrained and in sync')
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--models', default=','.join(MODEL_KEYS),
                    help='comma-separated subset of rf,xgb,nn (default: all three)')
    args = ap.parse_args()
    models = [m.strip() for m in args.models.split(',') if m.strip()]
    unknown = [m for m in models if m not in MODEL_KEYS]
    if unknown:
        raise SystemExit(f'unknown model keys {unknown}; valid: {MODEL_KEYS}')
    return retrain(models)


if __name__ == '__main__':
    sys.exit(main())
