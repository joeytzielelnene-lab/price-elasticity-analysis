"""Project paths and database configuration.

Everything resolves relative to the repo root, so modules and notebooks
behave the same regardless of the working directory they run from.
"""

from __future__ import annotations

import getpass
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = ROOT / "data"
SQL_DIR = ROOT / "sql"
OUTPUTS_DIR = ROOT / "outputs"
DOCS_DIR = ROOT / "docs"

RAW_XLSX = DATA_DIR / "online_retail_II.xlsx"
RAW_PARQUET = DATA_DIR / "online_retail_II.parquet"

load_dotenv(ROOT / ".env")

# Defaults to the OS user, which is how a local Homebrew Postgres is normally
# set up. Override with DATABASE_URL in .env for anything else.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql+psycopg://{getpass.getuser()}@localhost:5432/retail_case",
)

# Schema layout: raw is a verbatim copy of the source, staging holds the
# cleaned transaction grain, marts holds analysis-ready aggregates.
RAW_SCHEMA = "raw"
STAGING_SCHEMA = "staging"
MARTS_SCHEMA = "marts"

# The source sheets, in chronological order.
SHEETS = ("Year 2009-2010", "Year 2010-2011")

# StockCode values that are fees, adjustments, or instruments rather than
# products. These carry a price but have no demand curve, so they are excluded
# from the cleaned layer. Matched case-insensitively and exactly.
#
# Derived by inspecting every code not matching '^[0-9]{5}' together with its
# description and gross value -- not by pattern alone. The DCGS* codes look
# irregular but are genuine catalogue items (e.g. 'SUNJAR LED NIGHT LIGHT'),
# so a regex-based exclusion would have wrongly dropped them.
NON_PRODUCT_STOCK_CODES = frozenset(
    {
        "POST",  # postage
        "DOT",  # dotcom postage
        "C2",  # carriage
        "M",  # manual adjustment
        "BANK CHARGES",
        "B",  # adjust bad debt
        "S",  # samples
        "D",  # discount
        "CRUK",  # charity commission
        "AMAZONFEE",
        "ADJUST",
        "ADJUST2",
        "TEST001",
        "TEST002",
    }
)

# Gift vouchers (gift_0001_20, gift_0001_30, ...) are stored value, not goods.
NON_PRODUCT_STOCK_CODE_PATTERN = "^gift"

OUTPUTS_DIR.mkdir(exist_ok=True)
