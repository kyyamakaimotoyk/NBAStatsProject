"""P-2 (2026-10-30): are the rf / xgb / nn production bundles from one training run?

In 2025-26 the three models were never on a common schedule (RF/NN ran a
preseason-trained bundle all season, XGB never ran in-season), and nothing
noticed. This module compares the ``*_current`` bundles on the fields that must
agree when all three come from the same weekly retrain:

  * ``data_through_date``  - latest GAME_DATE each model was fit on
  * ``feature_set_version`` - the features snapshot each model was trained from
  * the model-input feature list

Used by the weekly ``train`` stage (fails the stage on mismatch) and the nightly
batch (alerts but still predicts - a stale model's picks beat no picks).

Standalone:
    python modeling/bundle_sync.py            # prints a report, exit 1 on mismatch
"""
from __future__ import annotations

import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

MODEL_KEYS = ('rf', 'xgb', 'nn')


def _as_iso(d) -> str | None:
    if d is None:
        return None
    if hasattr(d, 'date') and callable(d.date):  # datetime / Timestamp -> date
        d = d.date()
    return d.isoformat() if hasattr(d, 'isoformat') else str(d)


def bundle_summary(key: str) -> dict | None:
    """The sync-relevant fields of one ``<key>_current`` bundle, or None if missing.

    Goes through predict_games.load_model_bundle so a fresh container pulls the
    bundle from the artifact store exactly as the nightly does.
    """
    from modeling.predict_games import load_model_bundle
    b = load_model_bundle(key)
    if b is None:
        return None
    meta = b.get('metadata', {})
    hp = b.get('hyperparameters_classifier') or {}
    feats = list(b.get('feature_names') or [])
    return {
        'key': key,
        'version': meta.get('version'),
        'data_through_date': _as_iso(b.get('data_through_date') or meta.get('data_through_date')),
        'feature_set_version': hp.get('feature_set_version'),
        'feature_count': len(feats),
        'feature_names': feats,
    }


def check_bundle_sync(keys=MODEL_KEYS) -> tuple[bool, list[str]]:
    """Compare the current bundles for ``keys``. Returns (in_sync, report_lines).

    A missing bundle counts as out of sync: every requested model is meant to
    come from the same run.
    """
    summaries, lines, problems = {}, [], []
    for k in keys:
        s = bundle_summary(k)
        if s is None:
            problems.append(f'{k}: no current bundle')
            continue
        summaries[k] = s
        lines.append(f"  {k:4s} version={s['version']} data_through={s['data_through_date']} "
                     f"feature_set={s['feature_set_version']} features={s['feature_count']}")

    for field in ('data_through_date', 'feature_set_version'):
        values = {k: s[field] for k, s in summaries.items()}
        if len(set(values.values())) > 1:
            problems.append(f'{field} differs: ' + ', '.join(f'{k}={v}' for k, v in values.items()))

    feature_sets = {k: tuple(s['feature_names']) for k, s in summaries.items()}
    if len(set(feature_sets.values())) > 1:
        problems.append('model-input feature lists differ: ' + ', '.join(
            f'{k}={len(v)} cols' for k, v in feature_sets.items()))

    lines += [f'  MISMATCH: {p}' for p in problems]
    return not problems, lines


def main() -> int:
    in_sync, lines = check_bundle_sync()
    print('bundle sync:', 'OK' if in_sync else 'MISMATCH')
    for line in lines:
        print(line)
    return 0 if in_sync else 1


if __name__ == '__main__':
    sys.exit(main())
