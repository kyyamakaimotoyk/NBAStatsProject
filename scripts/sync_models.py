"""Push/pull the local ``models/`` tree to/from the configured artifact store.

The training pipeline already pushes individual bundles on save (see
``save_model_bundle``), and the prediction job pulls bundles on demand. This
script is for the bulk/manual cases:

  * First-time seeding of a fresh S3 bucket from your local machine
  * Hydrating a brand-new dev machine or container from the bucket
  * Backing up the legacy fixed-name files (models/*.joblib, *.pt)

Backend is chosen by env vars (see core/artifact_store.py):
  MODELS_S3_BUCKET (+ optional MODELS_S3_PREFIX)  → S3
  MODELS_ARTIFACT_DIR                              → local-mirror (for testing)

Usage (from project root):
    python scripts/sync_models.py push          # upload entire models/ tree
    python scripts/sync_models.py pull          # download entire models/ tree
    python scripts/sync_models.py status        # show backend + remote key count
    python scripts/sync_models.py push --dir models/bundles   # subset
"""
from __future__ import annotations

import argparse
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

from core.artifact_store import get_store  # noqa: E402


def cmd_status(store, _args):
    print(f"Backend: {store.name} (enabled={store.enabled})")
    if not store.enabled:
        print("No remote configured. Set MODELS_S3_BUCKET or MODELS_ARTIFACT_DIR.")
        return 0
    keys = store.list_keys('models/')
    print(f"{len(keys)} remote keys under models/:")
    for k in keys[:40]:
        print(f"  {k}")
    if len(keys) > 40:
        print(f"  ... and {len(keys) - 40} more")
    return 0


def cmd_push(store, args):
    if not store.enabled:
        print("No remote configured — nothing pushed. "
              "Set MODELS_S3_BUCKET or MODELS_ARTIFACT_DIR.")
        return 1
    local_dir = os.path.join(_PROJECT_ROOT, args.dir)
    if not os.path.isdir(local_dir):
        print(f"Local dir not found: {local_dir}")
        return 1
    print(f"Pushing {local_dir} → {store.name} ...")
    n = store.push_dir(local_dir)
    print(f"Pushed {n} files.")
    return 0


def cmd_pull(store, args):
    if not store.enabled:
        print("No remote configured — nothing pulled. "
              "Set MODELS_S3_BUCKET or MODELS_ARTIFACT_DIR.")
        return 1
    prefix = args.dir.replace(os.sep, '/').rstrip('/') + '/'
    print(f"Pulling {prefix} ← {store.name} ...")
    n = store.pull_dir(prefix)
    print(f"Pulled {n} files.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)

    p_status = sub.add_parser('status', help='Show backend and remote key count')
    p_status.set_defaults(func=cmd_status)

    p_push = sub.add_parser('push', help='Upload local files to the remote store')
    p_push.add_argument('--dir', default='models', help='Subtree to push (default: models)')
    p_push.set_defaults(func=cmd_push)

    p_pull = sub.add_parser('pull', help='Download remote files to local disk')
    p_pull.add_argument('--dir', default='models', help='Key prefix to pull (default: models)')
    p_pull.set_defaults(func=cmd_pull)

    args = parser.parse_args(argv)
    store = get_store()
    return args.func(store, args)


if __name__ == '__main__':
    sys.exit(main())
