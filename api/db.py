"""Read-only database engine for the public API.

Intentionally separate from core/db.py:

  * It uses the pure-Python ``pymysql`` driver instead of ``mysqlclient``.
    pymysql needs no C compiler or libmysqlclient headers, so the API Docker
    image stays small and builds without system deps.
  * It enables ``pool_pre_ping`` so dropped RDS connections (idle timeouts,
    failovers) are detected and recycled instead of surfacing as 500s.
  * It is ROTATION-AWARE. RDS's managed master password rotates weekly via
    Secrets Manager. The old design injected the password as an env var at
    task launch, so a long-lived task went stale on rotation and threw
    ``Access denied`` until restarted (the 2026-06-29 and 2026-07-03
    incidents). Now: when ``NBA_DB_SECRET_ARN`` is set, every NEW pooled
    connection fetches the password from Secrets Manager (cached), and an
    auth failure (MySQL error 1045) invalidates the cache and retries once
    with a fresh fetch. Rotation becomes a non-event. Existing pooled
    connections are unaffected by rotation (MySQL doesn't kill live
    sessions on password change).

Without ``NBA_DB_SECRET_ARN`` (local dev), behavior is unchanged: the
``NBA_DB_PASSWORD`` env var is used directly.
"""
from __future__ import annotations

import os
from functools import lru_cache

import sqlalchemy as sa
from dotenv import load_dotenv

load_dotenv()

# Password intentionally NOT in this list — it may come from Secrets Manager.
_REQUIRED = ('NBA_DB_HOST', 'NBA_DB_PORT', 'NBA_DB_USER', 'NBA_DB_NAME')

# Cached secret value; module-level so all pooled connections share one fetch.
_pw_cache: dict = {'value': None}


def _password(force_refresh: bool = False) -> str:
    """Current DB password: Secrets Manager (cached) if configured, else env."""
    arn = os.environ.get('NBA_DB_SECRET_ARN')
    if not arn:
        return os.environ['NBA_DB_PASSWORD']
    if _pw_cache['value'] is None or force_refresh:
        import json
        import boto3
        resp = boto3.client('secretsmanager').get_secret_value(SecretId=arn)
        _pw_cache['value'] = json.loads(resp['SecretString'])['password']
    return _pw_cache['value']


def _connect():
    """DBAPI creator with rotation retry: on 'Access denied' (1045), refresh
    the cached secret once and reconnect. Covers the window where the pool
    opens a new connection after a rotation."""
    import pymysql

    for attempt in (1, 2):
        try:
            return pymysql.connect(
                host=os.environ['NBA_DB_HOST'],
                port=int(os.environ['NBA_DB_PORT']),
                user=os.environ['NBA_DB_USER'],
                password=_password(force_refresh=(attempt == 2)),
                database=os.environ['NBA_DB_NAME'],
            )
        except pymysql.err.OperationalError as exc:
            stale_auth = bool(exc.args) and exc.args[0] == 1045
            if stale_auth and attempt == 1 and os.environ.get('NBA_DB_SECRET_ARN'):
                continue  # attempt 2 re-fetches the secret
            raise
    raise RuntimeError('unreachable')


@lru_cache(maxsize=1)
def get_engine() -> sa.Engine:
    """Build (once) a pooled, pre-pinging, rotation-aware SQLAlchemy engine."""
    missing = [name for name in _REQUIRED if not os.environ.get(name)]
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}."
        )
    if not os.environ.get('NBA_DB_SECRET_ARN') and not os.environ.get('NBA_DB_PASSWORD'):
        raise RuntimeError(
            "Set NBA_DB_PASSWORD (local dev) or NBA_DB_SECRET_ARN (prod)."
        )
    # With a `creator`, the URL only picks the dialect; connection parameters
    # all come from _connect().
    return sa.create_engine(
        'mysql+pymysql://',
        creator=_connect,
        pool_pre_ping=True,
        pool_recycle=1800,   # recycle connections older than 30 min
        pool_size=5,
        max_overflow=5,
        future=True,
    )


def db_healthy() -> bool:
    """Cheap connectivity probe for the /api/health endpoint."""
    try:
        with get_engine().connect() as conn:
            conn.execute(sa.text("SELECT 1"))
        return True
    except Exception:
        return False
