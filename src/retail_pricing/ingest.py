"""Load the source workbook into Postgres.

The Excel file is slow to parse (~60s for 1.07M rows across two sheets), so it
is cached to Parquet on first read. The raw table is a verbatim copy of the
source: no filtering or type coercion beyond what Postgres requires. All
cleaning happens in SQL downstream, so the raw layer stays auditable.
"""

from __future__ import annotations

import argparse

import pandas as pd
from sqlalchemy import text

from retail_pricing.config import RAW_PARQUET, RAW_SCHEMA, RAW_XLSX, SHEETS
from retail_pricing.db import get_engine, table_count

RAW_TABLE = "online_retail"

# Source column -> destination column. The source uses spaces and title case.
COLUMN_MAP = {
    "Invoice": "invoice",
    "StockCode": "stock_code",
    "Description": "description",
    "Quantity": "quantity",
    "InvoiceDate": "invoice_date",
    "Price": "price",
    "Customer ID": "customer_id",
    "Country": "country",
    "source_sheet": "source_sheet",
}

DDL = f"""
CREATE SCHEMA IF NOT EXISTS {RAW_SCHEMA};

DROP TABLE IF EXISTS {RAW_SCHEMA}.{RAW_TABLE};

CREATE TABLE {RAW_SCHEMA}.{RAW_TABLE} (
    invoice       text        NOT NULL,
    stock_code    text        NOT NULL,
    description   text,
    quantity      integer     NOT NULL,
    invoice_date  timestamp   NOT NULL,
    price         numeric(12, 3) NOT NULL,
    customer_id   integer,
    country       text        NOT NULL,
    source_sheet  text        NOT NULL
);
"""

INDEXES = f"""
CREATE INDEX ON {RAW_SCHEMA}.{RAW_TABLE} (stock_code);
CREATE INDEX ON {RAW_SCHEMA}.{RAW_TABLE} (invoice_date);
CREATE INDEX ON {RAW_SCHEMA}.{RAW_TABLE} (invoice);
"""


def read_workbook(use_cache: bool = True) -> pd.DataFrame:
    """Read both sheets into one DataFrame, caching to Parquet."""
    if use_cache and RAW_PARQUET.exists():
        return pd.read_parquet(RAW_PARQUET)

    frames = []
    for sheet in SHEETS:
        part = pd.read_excel(RAW_XLSX, sheet_name=sheet)
        part["source_sheet"] = sheet
        frames.append(part)

    df = pd.concat(frames, ignore_index=True)
    # These columns are numeric in some rows and text in others (credit notes
    # are 'C'-prefixed, fee codes are alphabetic, a few descriptions are bare
    # numbers), leaving mixed-type object columns that Parquet cannot encode.
    # The nullable string dtype normalises them while keeping NA as NA rather
    # than the literal string "nan".
    for col in ("Invoice", "StockCode", "Description", "Country"):
        df[col] = df[col].astype("string")
    df.to_parquet(RAW_PARQUET, index=False)
    return df


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Rename columns and coerce types for COPY.

    Invoice is text because credit notes carry a 'C' prefix. Customer ID is
    nullable because 22.8% of rows have no customer attached.
    """
    out = df.rename(columns=COLUMN_MAP)[list(COLUMN_MAP.values())].copy()
    for col in ("invoice", "stock_code", "description", "country"):
        out[col] = out[col].astype("string").str.strip()
    out["customer_id"] = out["customer_id"].astype("Float64").astype("Int64")
    return out


def load_raw(use_cache: bool = True) -> int:
    """Create the raw table and COPY the workbook into it. Returns row count."""
    df = _prepare(read_workbook(use_cache=use_cache))
    engine = get_engine()

    with engine.begin() as conn:
        conn.exec_driver_sql(DDL)

        columns = ", ".join(df.columns)
        copy_sql = f"COPY {RAW_SCHEMA}.{RAW_TABLE} ({columns}) FROM STDIN"
        driver_conn = conn.connection.driver_connection

        with driver_conn.cursor().copy(copy_sql) as copy:
            for row in df.itertuples(index=False, name=None):
                copy.write_row(
                    tuple(None if pd.isna(v) else v for v in row)
                )

        conn.exec_driver_sql(INDEXES)
        conn.execute(text(f"ANALYZE {RAW_SCHEMA}.{RAW_TABLE}"))

    return table_count(RAW_SCHEMA, RAW_TABLE)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="re-parse the Excel file instead of using the Parquet cache",
    )
    args = parser.parse_args()

    rows = load_raw(use_cache=not args.no_cache)
    print(f"Loaded {rows:,} rows into {RAW_SCHEMA}.{RAW_TABLE}")


if __name__ == "__main__":
    main()
