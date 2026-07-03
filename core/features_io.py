"""Read/write the versioned features dataset in MySQL.

Replaces the pattern of reading and writing ``nba_ml_features.csv`` at the
project root. Each ``feature_engineering.py`` run inserts a new snapshot under
a fresh ``feature_set_version`` tag and atomically updates a pointer table
``feature_set_current`` so readers don't have to know which version is live.

Schema
------
``features``
    feature_set_version VARCHAR(40)  NOT NULL
    GAME_ID             BIGINT       NOT NULL
    GAME_DATE           DATETIME     NULL
    <~767 more feature columns, auto-evolved>
    loaded_at           TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
    PRIMARY KEY (feature_set_version, GAME_ID)
    INDEX idx_features_game_date (GAME_DATE)

``feature_set_current`` (single row, ``id = 1``)
    id         TINYINT  PK
    version    VARCHAR(40)
    updated_at TIMESTAMP

Schema auto-evolves: if the DataFrame to write contains a column the table
doesn't have yet, ``ALTER TABLE ADD COLUMN`` is issued before the bulk insert.
"""
from __future__ import annotations

import os
import pandas as pd
import sqlalchemy as sql
from datetime import datetime, date
from typing import Optional


FEATURES_TABLE = 'features'
CURRENT_POINTER_TABLE = 'feature_set_current'
VERSIONS_TABLE = 'feature_set_versions'


def make_version() -> str:
    """UTC timestamp version tag, e.g. ``20260528T143015Z``."""
    return datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

def _pandas_to_sql_type(dtype) -> str:
    """Best-effort map from a pandas dtype to a MySQL column type."""
    kind = dtype.kind
    if kind == 'i':
        return 'BIGINT'
    if kind == 'u':
        return 'BIGINT UNSIGNED'
    if kind == 'f':
        return 'DOUBLE'
    if kind == 'b':
        return 'TINYINT(1)'
    if kind == 'M':
        return 'DATETIME'
    return 'TEXT'


def _existing_columns(engine, table: str) -> set:
    inspector = sql.inspect(engine)
    if not inspector.has_table(table):
        return set()
    return {col['name'] for col in inspector.get_columns(table)}


def _ensure_pointer_table(engine):
    with engine.begin() as conn:
        conn.execute(sql.text(
            f"CREATE TABLE IF NOT EXISTS {CURRENT_POINTER_TABLE} ("
            "  id TINYINT NOT NULL DEFAULT 1,"
            "  version VARCHAR(40) NOT NULL,"
            "  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"
            "    ON UPDATE CURRENT_TIMESTAMP,"
            "  PRIMARY KEY (id)"
            ") ENGINE=InnoDB"
        ))


def _create_features_table(engine, df: pd.DataFrame):
    """Issue the initial CREATE TABLE using the DataFrame's column list."""
    cols_sql = []
    for col in df.columns:
        backticked = f"`{col}`"
        if col == 'feature_set_version':
            cols_sql.append(f"{backticked} VARCHAR(40) NOT NULL")
        elif col == 'GAME_ID':
            cols_sql.append(f"{backticked} BIGINT NOT NULL")
        elif col == 'GAME_DATE':
            cols_sql.append(f"{backticked} DATETIME NULL")
        else:
            cols_sql.append(f"{backticked} {_pandas_to_sql_type(df[col].dtype)} NULL")

    cols_sql.append("`loaded_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP")

    ddl = (
        f"CREATE TABLE {FEATURES_TABLE} (\n  "
        + ",\n  ".join(cols_sql)
        + ",\n  PRIMARY KEY (feature_set_version, GAME_ID)"
        + ",\n  INDEX idx_features_game_date (GAME_DATE)"
        + "\n) ENGINE=InnoDB"
    )
    with engine.begin() as conn:
        conn.execute(sql.text(ddl))


def _add_missing_columns(engine, df: pd.DataFrame):
    """ALTER TABLE ADD COLUMN for any DataFrame column not yet in the table."""
    existing = _existing_columns(engine, FEATURES_TABLE)
    if not existing:
        return
    missing = [c for c in df.columns if c not in existing]
    if not missing:
        return
    with engine.begin() as conn:
        for col in missing:
            col_type = _pandas_to_sql_type(df[col].dtype)
            conn.execute(sql.text(
                f"ALTER TABLE {FEATURES_TABLE} ADD COLUMN `{col}` {col_type} NULL"
            ))


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------

def _ensure_versions_table(engine) -> None:
    """Create the per-version metadata table if it doesn't exist.

    One row per snapshot: what changed (human-written description) and shape
    stats. This is what turns opaque timestamp tags into an experiment log —
    and what a model-registry row's ``feature_set_version`` joins against.
    """
    with engine.begin() as conn:
        conn.execute(sql.text(
            f"CREATE TABLE IF NOT EXISTS {VERSIONS_TABLE} ("
            "  feature_set_version VARCHAR(40) NOT NULL,"
            "  description TEXT NULL,"
            "  n_games INT NULL,"
            "  n_columns INT NULL,"
            "  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
            "  PRIMARY KEY (feature_set_version)"
            ")"
        ))


def write_features(
    df: pd.DataFrame,
    engine,
    version: Optional[str] = None,
    set_current: bool = True,
    chunksize: int = 200,
    description: Optional[str] = None,
) -> str:
    """Insert a snapshot of ``df`` under a new ``feature_set_version`` tag.

    Returns the version string used. If ``set_current`` is true (default),
    updates the singleton pointer row so subsequent ``load_features`` calls
    see the new snapshot. ``description`` (recommended!) records WHAT changed
    in this snapshot — e.g. "E9 on, dropped L5 fatigue cols" — in the
    ``feature_set_versions`` metadata table.

    The DataFrame must have a ``GAME_ID`` column and must not already carry a
    ``feature_set_version`` column (that's set by this function).
    """
    if 'GAME_ID' not in df.columns:
        raise ValueError("DataFrame must contain a 'GAME_ID' column")
    if 'feature_set_version' in df.columns:
        raise ValueError(
            "DataFrame must not contain 'feature_set_version' — it's set by this function"
        )

    version = version or make_version()
    df_to_write = df.copy()
    # Move feature_set_version to the front; column ordering doesn't matter for
    # to_sql (it matches by name), but readability while debugging is nicer.
    df_to_write.insert(0, 'feature_set_version', version)
    if 'GAME_DATE' in df_to_write.columns:
        df_to_write['GAME_DATE'] = pd.to_datetime(df_to_write['GAME_DATE'])

    inspector = sql.inspect(engine)
    if not inspector.has_table(FEATURES_TABLE):
        _create_features_table(engine, df_to_write)
    else:
        _add_missing_columns(engine, df_to_write)

    df_to_write.to_sql(
        FEATURES_TABLE, engine,
        if_exists='append', index=False,
        method='multi', chunksize=chunksize,
    )

    if set_current:
        _ensure_pointer_table(engine)
        with engine.begin() as conn:
            conn.execute(sql.text(
                f"REPLACE INTO {CURRENT_POINTER_TABLE} (id, version) VALUES (1, :v)"
            ), {'v': version})

    # Metadata row: description + shape. Written even without a description so
    # every version at least has created_at and counts on record.
    _ensure_versions_table(engine)
    with engine.begin() as conn:
        conn.execute(sql.text(
            f"REPLACE INTO {VERSIONS_TABLE} "
            "(feature_set_version, description, n_games, n_columns) "
            "VALUES (:v, :d, :n, :c)"
        ), {'v': version, 'd': description,
            'n': int(df_to_write['GAME_ID'].nunique()),
            'c': int(len(df.columns))})

    return version


# ---------------------------------------------------------------------------
# Reader
# ---------------------------------------------------------------------------

def get_current_version(engine) -> Optional[str]:
    """Return the version pointed to by ``feature_set_current``, or None if unset."""
    _ensure_pointer_table(engine)
    with engine.begin() as conn:
        row = conn.execute(sql.text(
            f"SELECT version FROM {CURRENT_POINTER_TABLE} WHERE id = 1"
        )).first()
    return row[0] if row else None


def load_features(
    engine,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    version: Optional[str] = None,
) -> pd.DataFrame:
    """Load a feature snapshot as a DataFrame, matching the legacy CSV shape.

    Defaults to the version pointed to by ``feature_set_current``. Drops the
    ``feature_set_version`` and ``loaded_at`` bookkeeping columns from the
    returned DataFrame so call sites see the same column set as the old CSV.
    """
    if version is None:
        version = get_current_version(engine)
        if version is None:
            raise RuntimeError(
                f"No current feature_set_version pointer found. "
                f"Run feature_engineering.py (or the migration script) "
                f"to populate the {FEATURES_TABLE} table."
            )

    clauses = ["feature_set_version = :version"]
    params = {'version': version}
    if start_date is not None:
        clauses.append("GAME_DATE >= :start_date")
        params['start_date'] = start_date
    if end_date is not None:
        clauses.append("GAME_DATE <= :end_date")
        params['end_date'] = end_date
    where = ' AND '.join(clauses)

    query = sql.text(
        f"SELECT * FROM {FEATURES_TABLE} WHERE {where} "
        f"ORDER BY GAME_DATE, GAME_ID"
    )
    df = pd.read_sql(query, engine, params=params)

    for bookkeeping in ('feature_set_version', 'loaded_at'):
        if bookkeeping in df.columns:
            df = df.drop(columns=[bookkeeping])
    if 'GAME_DATE' in df.columns:
        df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])
    return df


def load_features_with_csv_fallback(
    engine,
    csv_path: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    version: Optional[str] = None,
    bootstrap_db: bool = True,
) -> pd.DataFrame:
    """Try MySQL first; fall back to reading the legacy CSV.

    During the CSV → DB migration window, every reader still needs a working
    code path even if the table hasn't been populated yet on a fresh machine.
    If ``bootstrap_db`` is true and the CSV exists but the DB is empty, the
    CSV is also written into the DB so the next call uses the fast path.
    """
    if version is None and get_current_version(engine) is None:
        if csv_path and os.path.exists(csv_path):
            print(f"[features_io] DB empty — loading legacy CSV {csv_path}")
            df = pd.read_csv(csv_path)
            if 'GAME_DATE' in df.columns:
                df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])
            if bootstrap_db:
                try:
                    v = write_features(df, engine)
                    print(f"[features_io] bootstrapped features table (version={v})")
                except Exception as exc:
                    print(f"[features_io] WARN: DB bootstrap skipped — {exc}")
            if start_date is not None:
                df = df[df['GAME_DATE'] >= pd.to_datetime(start_date)]
            if end_date is not None:
                df = df[df['GAME_DATE'] <= pd.to_datetime(end_date)]
            return df.reset_index(drop=True)

    return load_features(engine, start_date=start_date, end_date=end_date, version=version)


# ---------------------------------------------------------------------------
# Introspection helpers (for ad-hoc inspection)
# ---------------------------------------------------------------------------

def list_versions(engine) -> pd.DataFrame:
    """Return a DataFrame summarizing every version present in the features table."""
    query = sql.text(
        f"SELECT feature_set_version, COUNT(*) AS n_games, "
        f"  MIN(GAME_DATE) AS min_date, MAX(GAME_DATE) AS max_date, "
        f"  MIN(loaded_at) AS loaded_at "
        f"FROM {FEATURES_TABLE} "
        f"GROUP BY feature_set_version "
        f"ORDER BY feature_set_version DESC"
    )
    return pd.read_sql(query, engine)


def delete_version(engine, version: str):
    """Drop all rows for a given version. The current pointer is not modified."""
    with engine.begin() as conn:
        conn.execute(
            sql.text(f"DELETE FROM {FEATURES_TABLE} WHERE feature_set_version = :v"),
            {'v': version},
        )


if __name__ == '__main__':
    # `python core/features_io.py` prints the version index. Useful sanity check.
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core.db import get_engine

    eng = get_engine()
    current = get_current_version(eng)
    print(f"Current version pointer: {current!r}")
    print("Versions in features table:")
    print(list_versions(eng).to_string(index=False))
