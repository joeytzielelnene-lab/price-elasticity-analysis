# Retail Pricing Case Study

Price elasticity of demand on the UCI *Online Retail II* dataset — a UK online
giftware retailer, Dec 2009 to Dec 2011. 1.07M invoice lines loaded into
Postgres, cleaned in SQL, modelled in Python.

**Headline:** a bounded ±10% price move projects **+£622k revenue (+11.7%)** —
but £621k of that comes from price cuts whose profitability cannot be verified,
because the dataset has no cost of goods. The margin-safe half is £1.3k across
11 products. See **[docs/findings.md](docs/findings.md)** for the full argument.

---

## Architecture

```
data/online_retail_II.xlsx
        │  ingest.py  (COPY, ~50s)
        ▼
raw.online_retail          1,067,371 rows — verbatim, auditable
        │  sql/01_staging_transactions.sql
        ▼
staging.transactions       1,003,355 clean sales lines (94.0%)
staging.returns            credit notes, kept separately
staging.line_audit         the removal funnel, row by row
        │  sql/02_marts_pricing.sql
        ▼
marts.product_week         197,889 product-weeks — the elasticity panel
marts.product_catalog      4,895 products
marts.weekly_revenue       104 weeks
marts.customer_rfm         5,852 scored customers
marts.product_returns
        │  elasticity.py → optimize.py
        ▼
outputs/   estimates, recommendations, figures
```

Cleaning lives in SQL so it runs in the warehouse and stays reviewable; the raw
layer is never mutated.

## Setup

Requires Postgres and [uv](https://docs.astral.sh/uv/).

```bash
createdb retail_case          # skip if it exists
uv sync
```

Connection defaults to `postgresql+psycopg://<you>@localhost:5432/retail_case`.
Override with `DATABASE_URL` in a `.env` at the repo root.

## Running it

```bash
# everything: SQL, models, figures  (~60s; add --reload to re-read the workbook)
uv run python -m retail_pricing.pipeline --reload

# just the load
uv run python -m retail_pricing.ingest
```

Then the notebooks:

```bash
uv run jupyter lab notebooks/
```

- **[01_data_quality.ipynb](notebooks/01_data_quality.ipynb)** — what is wrong
  with the raw data and what the cleaning does about it.
- **[02_pricing_analysis.ipynb](notebooks/02_pricing_analysis.ipynb)** — trading
  pattern, segmentation, elasticity, recommendations.

## Layout

| Path | |
|---|---|
| `src/retail_pricing/config.py` | paths, DB URL, the non-product code list |
| `src/retail_pricing/db.py` | engine, `read_sql`, migration runner |
| `src/retail_pricing/ingest.py` | Excel → Parquet cache → Postgres via `COPY` |
| `src/retail_pricing/elasticity.py` | the demand model and its diagnostics |
| `src/retail_pricing/optimize.py` | bounded price moves and revenue impact |
| `src/retail_pricing/plots.py` | figures |
| `src/retail_pricing/pipeline.py` | end-to-end entry point |
| `sql/` | staging and marts, idempotent, applied in filename order |
| `outputs/` | CSV + Parquet estimates, PNG figures |

## Method, in brief

Per product, on weekly data:

```
log(units) = α + β·log(price) + γ·log(market_units) + ε
```

`market_units` (all *other* products that week) absorbs catalogue-wide
seasonality — this is a Christmas business and Q4 roughly doubles. Newey-West
standard errors; Benjamini-Hochberg FDR correction across ~1,900 regressions.

**1,546 products** yield estimates that are both statistically significant and
correctly signed. Median elasticity **−1.79**.

## Three things this study gets right that are easy to get wrong

**The price measure is not `revenue ÷ units`.** That puts quantity on both sides
of the regression, and noise alone drags the slope negative. It inflated the
median elasticity from −1.62 to −2.39 — a bigger effect than any modelling
choice made afterwards. `compare_price_measures()` quantifies it.

**There is no "optimal price" column.** Under constant elasticity revenue is
monotonic in price, so no interior optimum exists. Reporting one would mean
smuggling in an assumption as a result. The output is a bounded move within
observed price support instead.

**Revenue is not profit.** With no cost of goods, price cuts on elastic products
cannot be validated. The recommendations are split so the margin-safe subset is
visible rather than blended into a flattering total.

## Caveats

Prices were set by the retailer, not randomised, so these are associations, not
causal effects — and the bias runs toward *understating* price sensitivity.
Read the output as a ranking of products to test, not a forecast.
[docs/findings.md](docs/findings.md) §5 lists what would be needed to close that
gap.

## Data

`data/online_retail_II.xlsx` — [UCI Machine Learning Repository, Online Retail II](https://archive.ics.uci.edu/dataset/502/online+retail+ii).