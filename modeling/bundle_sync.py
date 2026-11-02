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
    return _summarize(key, b)


def _summarize(key: str, b: dict) -> dict:
    meta = b.get('metadata', {})
    hp = b.get('hyperparameters_classifier') or {}
    feats = list(b.get('feature_names') or [])
    return {
        'key': key,
        'version': meta.get('version'),
        'created_at': meta.get('created_at'),
        'data_through_date': _as_iso(b.get('data_through_date') or meta.get('data_through_date')),
        'feature_set_version': hp.get('feature_set_version'),
        'feature_count': len(feats),
        'feature_names': feats,
    }


def remote_bundle_summary(key: str) -> dict | None:
    """Summary of ``<key>_current`` as it sits in the artifact store (S3), read into
    a temp file so the local copy is untouched. None if the store is disabled or
    the object is missing.

    Needed because a local check alone passes when the push failed: the freshly
    saved local bundle looks fine while S3 still holds the old one (E26).
    """
    import tempfile
    import joblib
    from core.artifact_store import get_store, S3Store, LocalMirrorStore

    store = get_store()
    if not store.enabled:
        return None
    rel = f'models/bundles/{key}_current.joblib'
    with tempfile.TemporaryDirectory() as tmp:
        dest = os.path.join(tmp, f'{key}_current.joblib')
        try:
            if isinstance(store, S3Store):
                store._s3.download_file(store.bucket, store._s3_key(rel), dest)
            elif isinstance(store, LocalMirrorStore):
                import shutil
                shutil.copy2(store._mirror_path(rel), dest)
            else:
                return None
        except Exception:
            return None
        return _summarize(key, joblib.load(dest))


def check_remote_matches_local(keys=MODEL_KEYS) -> tuple[bool, list[str]]:
    """After a retrain: is the artifact store's current bundle the one just saved?"""
    from core.artifact_store import get_store
    if not get_store().enabled:
        return True, ['  artifact store disabled (local dev): remote check skipped']
    ok, lines = True, []
    for k in keys:
        local, remote = bundle_summary(k), remote_bundle_summary(k)
        if local is None or remote is None or local['created_at'] != remote['created_at']:
            ok = False
            lines.append(f"  MISMATCH: {k} local created_at={local and local['created_at']} "
                         f"remote={remote and remote['created_at']}")
        else:
            lines.append(f"  {k:10s} store copy matches ({remote['created_at']})")
    return ok, lines


def check_staleness(engine, keys=MODEL_KEYS, max_gap_days: int = 14) -> tuple[bool, list[str]]:
    """Are the bundles trained on recent games? Compares each bundle's
    data_through_date with the latest graded game in game_list.

    The sync check alone passes when all three are equally stale. Naturally quiet
    in the offseason: the latest game and the bundles' data stop at the Finals.
    """
    from datetime import date
    import sqlalchemy as sa
    with engine.connect() as conn:
        latest = conn.execute(sa.text(
            'SELECT MAX(GAME_DATE) FROM game_list WHERE WL IS NOT NULL')).scalar()
    if latest is None:
        return True, ['  no graded games: staleness check skipped']
    latest = date.fromisoformat(_as_iso(latest))
    ok, lines = True, []
    for k in keys:
        s = bundle_summary(k)
        through = s and s['data_through_date']
        if not through:
            ok = False
            lines.append(f'  STALE: {k} has no data_through_date')
            continue
        gap = (latest - date.fromisoformat(through)).days
        if gap > max_gap_days:
            ok = False
            lines.append(f'  STALE: {k} trained through {through}, latest graded game '
                         f'{latest} ({gap} days)')
        else:
            lines.append(f'  {k:10s} trained through {through} ({gap} days behind {latest})')
    return ok, lines


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
