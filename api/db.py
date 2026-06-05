"""Read-only database engine for the public API.

Intentionally separate from core/db.py:

  * It uses the pure-Python ``pymysql`` driver (``mysql+pymysql://``) instead of
    ``mysqlclient`` (``mysql://``). pymysql needs no C compiler or libmysqlclient
    headers, so the API Docker image stays small and builds without system deps.
  * It enables ``pool_pre_ping`` so dropped RDS connections (idle timeouts,
    failovers) are detected and recycled instead of surfacing as 500s.

Same ``NBA_DB_*`` environment variables as the rest of the project, so it points
at local MySQL in dev and at RDS in prod with zero code change.
"""
from __future__ import annotations

import os
from functools import lru_cache

import sqlalchemy as sa
from dotenv import load_dotenv

load_dotenv()

_REQUIRED = ('NBA_DB_HOST', 'NBA_DB_PORT', 'NBA_DB_USER', 'NBA_DB_PASSWORD', 'NBA_DB_NAME')


@lru_cache(maxsize=1)
def get_engine() -> sa.Engine:
    """Build (once) a pooled, pre-pinging SQLAlchemy engine via pymysql."""
    missing = [name for name in _REQUIRED if not os.environ.get(name)]
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}."
        )
    url = sa.URL.create(
        drivername='mysql+pymysql',
        username=os.environ['NBA_DB_USER'],
        password=os.environ['NBA_DB_PASSWORD'],
        host=os.environ['NBA_DB_HOST'],
        port=int(os.environ['NBA_DB_PORT']),
        database=os.environ['NBA_DB_NAME'],
    )
    return sa.create_engine(
        url,
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
