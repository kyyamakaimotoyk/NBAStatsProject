"""Remote artifact store for model bundles (and other large binaries).

Model weights should not live in git. This module is the seam that lets the
training pipeline push bundles to S3 and the prediction job pull them back,
while keeping a working local-only path for day-to-day development.

Backend selection (checked in order, first match wins):

  1. ``MODELS_S3_BUCKET``    → S3 backend (requires boto3 + AWS creds in env)
  2. ``MODELS_ARTIFACT_DIR`` → local-mirror backend (a directory that simulates
                               a remote bucket; used to test push/pull without AWS)
  3. neither set            → DISABLED (no-op). Pure-local behavior, unchanged
                               from before this module existed.

All keys are repo-relative POSIX paths, e.g. ``models/bundles/rf_current.joblib``.
With S3 they are optionally prefixed by ``MODELS_S3_PREFIX`` (e.g. ``prod/``).

Typical wiring:
    from core.artifact_store import get_store
    store = get_store()
    store.push('models/bundles/rf_current.joblib')   # after a local save
    store.pull('models/bundles/rf_current.joblib')   # before a load, if missing

Nothing here raises on a DISABLED backend — push/pull/exists become no-ops that
return sensible defaults, so call sites don't need to branch on configuration.
"""
from __future__ import annotations

import os
import shutil
from abc import ABC, abstractmethod
from typing import Optional, List

# Repo root = parent of this file's directory (core/).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _to_key(local_path: str) -> str:
    """Normalize a local path to a repo-relative POSIX key."""
    abspath = os.path.abspath(local_path)
    rel = os.path.relpath(abspath, _REPO_ROOT)
    return rel.replace(os.sep, '/')


def _to_local(key: str) -> str:
    """Resolve a repo-relative key back to an absolute local path."""
    return os.path.join(_REPO_ROOT, key.replace('/', os.sep))


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------

class ArtifactStore(ABC):
    enabled: bool = True
    name: str = 'base'

    @abstractmethod
    def push(self, local_path: str) -> bool: ...

    @abstractmethod
    def pull(self, local_path: str) -> bool: ...

    @abstractmethod
    def exists(self, local_path: str) -> bool: ...

    @abstractmethod
    def list_keys(self, prefix: str = 'models/') -> List[str]: ...

    def push_dir(self, local_dir: str) -> int:
        """Push every file under ``local_dir`` recursively. Returns count pushed."""
        n = 0
        for root, _, files in os.walk(local_dir):
            for fname in files:
                if self.push(os.path.join(root, fname)):
                    n += 1
        return n

    def pull_dir(self, key_prefix: str = 'models/') -> int:
        """Pull every remote key under ``key_prefix``. Returns count pulled."""
        n = 0
        for key in self.list_keys(key_prefix):
            if self.pull(_to_local(key)):
                n += 1
        return n


class DisabledStore(ArtifactStore):
    """No remote configured. Push/pull are no-ops; exists() checks local disk only."""
    enabled = False
    name = 'disabled'

    def push(self, local_path: str) -> bool:
        return False

    def pull(self, local_path: str) -> bool:
        # Nothing to pull from; succeed iff the file is already on local disk.
        return os.path.exists(local_path)

    def exists(self, local_path: str) -> bool:
        return os.path.exists(local_path)

    def list_keys(self, prefix: str = 'models/') -> List[str]:
        return []


class LocalMirrorStore(ArtifactStore):
    """Simulates a remote bucket with a local directory (``MODELS_ARTIFACT_DIR``).

    Lets the entire push/pull flow be exercised on one machine with no AWS — the
    mirror dir stands in for the bucket. Used by the Week-1 local docker-compose.
    """
    name = 'local-mirror'

    def __init__(self, mirror_dir: str):
        self.mirror_dir = os.path.abspath(mirror_dir)
        os.makedirs(self.mirror_dir, exist_ok=True)

    def _mirror_path(self, key: str) -> str:
        return os.path.join(self.mirror_dir, key.replace('/', os.sep))

    def push(self, local_path: str) -> bool:
        if not os.path.exists(local_path):
            return False
        dest = self._mirror_path(_to_key(local_path))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(local_path, dest)
        return True

    def pull(self, local_path: str) -> bool:
        src = self._mirror_path(_to_key(local_path))
        if not os.path.exists(src):
            return os.path.exists(local_path)  # fall back to whatever is local
        os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)
        shutil.copy2(src, local_path)
        return True

    def exists(self, local_path: str) -> bool:
        return (os.path.exists(self._mirror_path(_to_key(local_path)))
                or os.path.exists(local_path))

    def list_keys(self, prefix: str = 'models/') -> List[str]:
        base = os.path.join(self.mirror_dir, prefix.replace('/', os.sep))
        keys: List[str] = []
        if not os.path.isdir(base):
            return keys
        for root, _, files in os.walk(base):
            for fname in files:
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, self.mirror_dir).replace(os.sep, '/')
                keys.append(rel)
        return keys


class S3Store(ArtifactStore):
    """S3-backed store (``MODELS_S3_BUCKET``, optional ``MODELS_S3_PREFIX``)."""
    name = 's3'

    def __init__(self, bucket: str, prefix: str = ''):
        import boto3  # imported lazily so the dep is optional for local-only users
        self.bucket = bucket
        self.prefix = prefix.strip('/')
        self._s3 = boto3.client('s3')

    def _s3_key(self, key: str) -> str:
        return f"{self.prefix}/{key}" if self.prefix else key

    def push(self, local_path: str) -> bool:
        if not os.path.exists(local_path):
            return False
        self._s3.upload_file(local_path, self.bucket, self._s3_key(_to_key(local_path)))
        return True

    def pull(self, local_path: str) -> bool:
        s3_key = self._s3_key(_to_key(local_path))
        try:
            os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)
            self._s3.download_file(self.bucket, s3_key, local_path)
            return True
        except Exception:
            return os.path.exists(local_path)

    def exists(self, local_path: str) -> bool:
        if os.path.exists(local_path):
            return True
        try:
            self._s3.head_object(Bucket=self.bucket, Key=self._s3_key(_to_key(local_path)))
            return True
        except Exception:
            return False

    def list_keys(self, prefix: str = 'models/') -> List[str]:
        s3_prefix = self._s3_key(prefix)
        keys: List[str] = []
        paginator = self._s3.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=self.bucket, Prefix=s3_prefix):
            for obj in page.get('Contents', []):
                k = obj['Key']
                if self.prefix and k.startswith(self.prefix + '/'):
                    k = k[len(self.prefix) + 1:]
                keys.append(k)
        return keys


# ---------------------------------------------------------------------------
# Factory (cached singleton)
# ---------------------------------------------------------------------------

_STORE: Optional[ArtifactStore] = None


def get_store(force_reload: bool = False) -> ArtifactStore:
    """Return the configured artifact store (cached). Selection per module docstring."""
    global _STORE
    if _STORE is not None and not force_reload:
        return _STORE

    bucket = os.environ.get('MODELS_S3_BUCKET')
    mirror = os.environ.get('MODELS_ARTIFACT_DIR')

    if bucket:
        try:
            _STORE = S3Store(bucket, os.environ.get('MODELS_S3_PREFIX', ''))
        except Exception as exc:
            print(f"[artifact_store] S3 backend unavailable ({exc}); falling back to DISABLED.")
            _STORE = DisabledStore()
    elif mirror:
        _STORE = LocalMirrorStore(mirror)
    else:
        _STORE = DisabledStore()
    return _STORE


if __name__ == '__main__':
    store = get_store()
    print(f"Artifact store backend: {store.name} (enabled={store.enabled})")
    if store.enabled:
        keys = store.list_keys('models/')
        print(f"{len(keys)} remote keys under models/:")
        for k in keys[:30]:
            print(f"  {k}")
        if len(keys) > 30:
            print(f"  ... and {len(keys) - 30} more")
