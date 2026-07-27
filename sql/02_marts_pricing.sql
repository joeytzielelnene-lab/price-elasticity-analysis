-- Marts layer: analysis-ready aggregates built from staging.transactions.
-- Idempotent: safe to re-run.

CREATE SCHEMA IF NOT EXISTS marts;

-- ---------------------------------------------------------------------------
-- Product catalogue: one row per SKU, with the price-variation stats used to
-- decide which products can support a demand model at all.
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS marts.product_catalog CASCADE;

CREATE TABLE marts.product_catalog AS
SELECT
    t.stock_code,
    -- Descriptions drift over time; take the most frequent as canonical.
    mode() WITHIN GROUP (ORDER BY t.description)      AS description,
    min(t.invoice_day)                                AS first_sold,
    max(t.invoice_day)                                AS last_sold,
    count(DISTINCT t.invoice_week)                    AS active_weeks,
    count(*)                                          AS sales_lines,
    count(DISTINCT t.invoice)                         AS invoices,
    count(DISTINCT t.customer_id)                     AS customers,
    sum(t.quantity)                                   AS total_units,
    sum(t.line_revenue)::numeric(14, 2)               AS total_revenue,
    count(DISTINCT t.unit_price)                      AS distinct_prices,
    min(t.unit_price)                                 AS min_price,
    max(t.unit_price)                                 AS max_price,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY t.unit_price)::numeric(12, 3)
                                                      AS median_price,
    (sum(t.line_revenue) / NULLIF(sum(t.quantity), 0))::numeric(12, 3)
                                                      AS avg_realised_price
FROM staging.transactions t
GROUP BY t.stock_code;

ALTER TABLE marts.product_catalog ADD PRIMARY KEY (stock_code);
CREATE INDEX ON marts.product_catalog (total_revenue DESC);


-- ---------------------------------------------------------------------------
-- The elasticity panel: product x week.
--
-- Price is the revenue-weighted realised price for the week, not a simple mean
-- of line prices. A simple mean would weight a 1-unit line the same as a
-- 500-unit line and understate what customers actually paid.
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS marts.product_week CASCADE;

CREATE TABLE marts.product_week AS
SELECT
    t.stock_code,
    t.invoice_week                                    AS week_start,
    sum(t.quantity)                                   AS units,
    sum(t.line_revenue)::numeric(14, 2)               AS revenue,
    (sum(t.line_revenue) / sum(t.quantity))::numeric(12, 4)
                                                      AS avg_price,
    -- Quantity-independent price measures. avg_price above is revenue/units,
    -- which puts units in the denominator of the regressor and the numerator
    -- of the outcome -- noise in units alone would then produce a spurious
    -- negative elasticity (division bias). These two summarise the posted
    -- line prices without reference to quantity, and are what the demand
    -- model actually regresses on.
    percentile_cont(0.5) WITHIN GROUP (ORDER BY t.unit_price)::numeric(12, 4)
                                                      AS median_line_price,
    mode() WITHIN GROUP (ORDER BY t.unit_price)::numeric(12, 4)
                                                      AS modal_line_price,
    min(t.unit_price)                                 AS min_price,
    max(t.unit_price)                                 AS max_price,
    count(*)                                          AS lines,
    count(DISTINCT t.invoice)                         AS invoices,
    count(DISTINCT t.customer_id)                     AS customers
FROM staging.transactions t
GROUP BY t.stock_code, t.invoice_week;

ALTER TABLE marts.product_week ADD PRIMARY KEY (stock_code, week_start);
CREATE INDEX ON marts.product_week (week_start);


-- ---------------------------------------------------------------------------
-- Overall trading trend, for the descriptive half of the study.
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS marts.weekly_revenue CASCADE;

CREATE TABLE marts.weekly_revenue AS
SELECT
    invoice_week                                      AS week_start,
    sum(line_revenue)::numeric(14, 2)                 AS revenue,
    sum(quantity)                                     AS units,
    count(DISTINCT invoice)                           AS invoices,
    count(DISTINCT customer_id)                       AS customers,
    count(DISTINCT stock_code)                        AS products_sold,
    (sum(line_revenue) / NULLIF(count(DISTINCT invoice), 0))::numeric(12, 2)
                                                      AS revenue_per_invoice
FROM staging.transactions
GROUP BY invoice_week
ORDER BY invoice_week;

ALTER TABLE marts.weekly_revenue ADD PRIMARY KEY (week_start);


-- ---------------------------------------------------------------------------
-- Return exposure per product. Returns are matched to sales on stock_code
-- only, because credit notes do not reference the original invoice.
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS marts.product_returns CASCADE;

CREATE TABLE marts.product_returns AS
SELECT
    c.stock_code,
    c.description,
    c.total_units,
    c.total_revenue,
    COALESCE(r.units_returned, 0)                     AS units_returned,
    COALESCE(r.return_value, 0)::numeric(14, 2)       AS return_value,
    ROUND(
        COALESCE(r.units_returned, 0)::numeric
        / NULLIF(c.total_units, 0) * 100, 2
    )                                                 AS return_rate_pct
FROM marts.product_catalog c
LEFT JOIN (
    SELECT stock_code,
           sum(quantity_returned) AS units_returned,
           sum(return_value)      AS return_value
    FROM staging.returns
    GROUP BY stock_code
) r ON r.stock_code = c.stock_code;

ALTER TABLE marts.product_returns ADD PRIMARY KEY (stock_code);


-- ---------------------------------------------------------------------------
-- Customer RFM. Recency is measured from the last day in the dataset, not
-- today, since the data ends in December 2011.
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS marts.customer_rfm CASCADE;

CREATE TABLE marts.customer_rfm AS
WITH bounds AS (
    SELECT max(invoice_day) AS as_of FROM staging.transactions
),
base AS (
    SELECT
        t.customer_id,
        max(t.country)                                AS country,
        (SELECT as_of FROM bounds) - max(t.invoice_day) AS recency_days,
        count(DISTINCT t.invoice)                     AS frequency,
        sum(t.line_revenue)::numeric(14, 2)           AS monetary,
        min(t.invoice_day)                            AS first_order,
        max(t.invoice_day)                            AS last_order
    FROM staging.transactions t
    WHERE t.customer_id IS NOT NULL
    GROUP BY t.customer_id
)
SELECT
    *,
    -- Recency is reversed: fewer days since last order is a better score.
    ntile(5) OVER (ORDER BY recency_days DESC) AS r_score,
    ntile(5) OVER (ORDER BY frequency)         AS f_score,
    ntile(5) OVER (ORDER BY monetary)          AS m_score
FROM base;

ALTER TABLE marts.customer_rfm ADD PRIMARY KEY (customer_id);


ANALYZE marts.product_catalog;
ANALYZE marts.product_week;
ANALYZE marts.weekly_revenue;
ANALYZE marts.product_returns;
ANALYZE marts.customer_rfm;
