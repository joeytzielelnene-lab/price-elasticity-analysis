"""Database access helpers.

A single lazily-created engine is shared across the project so notebooks and
scripts do not each open their own pool.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd
from sqlalchemy import Engine, create_engine, text

from retail_pricing.config import DATABASE_URL, SQL_DIR


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Return the shared SQLAlchemy engine."""
    return create_engine(DATABASE_URL, future=True)


def read_sql(query: str, **params) -> pd.DataFrame:
    """Run a query and return the result as a DataFrame."""
    with get_engine().connect() as conn:
        return pd.read_sql(text(query), conn, params=params or None)


def execute_script(path: str | Path) -> None:
    """Execute a .sql file as a single transaction.

    The file is sent to the server whole rather than split on semicolons, so
    functions and dollar-quoted bodies survive intact.

    Executed through the raw DBAPI cursor with no parameters, because psycopg
    only treats '%' as a placeholder when parameters are supplied. Going via
    SQLAlchemy would make literals such as LIKE 'C%' fail to parse.
    """
    sql = Path(path).read_text()
    with get_engine().begin() as conn:
        with conn.connection.driver_connection.cursor() as cur:
            cur.execute(sql)


def run_migrations() -> list[str]:
    """Execute every numbered script in sql/ in filename order.

    Scripts are written to be idempotent, so this is safe to re-run.
    Returns the names of the scripts that ran.
    """
    scripts = sorted(SQL_DIR.glob("[0-9]*.sql"))
    for script in scripts:
        execute_script(script)
    return [s.name for s in scripts]


def table_count(schema: str, table: str) -> int:
    """Row count for a table, or -1 if it does not exist."""
    with get_engine().connect() as conn:
        exists = conn.execute(
            text("SELECT to_regclass(:qualified)"),
            {"qualified": f"{schema}.{table}"},
        ).scalar()
        if exists is None:
            return -1
        return conn.execute(
            text(f'SELECT count(*) FROM "{schema}"."{table}"')
        ).scalar_one()
