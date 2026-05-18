"""
Database connection helper.

Centralizes MySQL configuration so credentials live in environment variables,
not in source code. All other modules should import `get_engine()` from here
instead of constructing engines themselves.

Setup:
    1. Copy .env.example to .env
    2. Fill in your MySQL credentials
    3. Scripts will pick them up automatically via python-dotenv

Required environment variables:
    NBA_DB_HOST        e.g. localhost
    NBA_DB_PORT        e.g. 3306
    NBA_DB_USER        MySQL username
    NBA_DB_PASSWORD    MySQL password
    NBA_DB_NAME        MySQL database name (e.g. nba_data)
"""

import os
import sqlalchemy as sql
from dotenv import load_dotenv

load_dotenv()

_REQUIRED = ('NBA_DB_HOST', 'NBA_DB_PORT', 'NBA_DB_USER', 'NBA_DB_PASSWORD', 'NBA_DB_NAME')


def get_engine():
    """Build a SQLAlchemy engine for the NBA MySQL database from env vars."""
    missing = [name for name in _REQUIRED if not os.environ.get(name)]
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}. "
            f"Copy .env.example to .env and fill in your MySQL credentials."
        )

    connection_string = (
        f"mysql://{os.environ['NBA_DB_USER']}:{os.environ['NBA_DB_PASSWORD']}"
        f"@{os.environ['NBA_DB_HOST']}:{os.environ['NBA_DB_PORT']}/{os.environ['NBA_DB_NAME']}"
    )
    return sql.create_engine(connection_string)


def get_url():
    """Return the SQLAlchemy URL object form (used by a few legacy call-sites)."""
    missing = [name for name in _REQUIRED if not os.environ.get(name)]
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}. "
            f"Copy .env.example to .env and fill in your MySQL credentials."
        )
    return sql.URL.create(
        drivername='mysql',
        username=os.environ['NBA_DB_USER'],
        password=os.environ['NBA_DB_PASSWORD'],
        host=os.environ['NBA_DB_HOST'],
        port=os.environ['NBA_DB_PORT'],
        database=os.environ['NBA_DB_NAME'],
    )
