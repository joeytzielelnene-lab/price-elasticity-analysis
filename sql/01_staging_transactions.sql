-- Staging layer: one clean sales line per row.
--
-- raw.online_retail is a verbatim copy of the source workbook and is loaded by
-- src/retail_pricing/ingest.py. This script derives the cleaned transaction
-- grain from it. Idempotent: safe to re-run.
--
-- Cleaning decisions, all evidence-based (see docs/findings.md):
--   1. Exact duplicate lines are collapsed. 34,337 surplus rows (3.2%) repeat
--      the same invoice/product/quantity/timestamp/price/customer. Left in,
--      they inflate demand quantities.
--   2. Credit notes ('C'-prefixed invoices) are split into staging.returns
--      rather than deleted, so return behaviour stays analysable.
--   3. Fee and adjustment codes (postage, bank charges, vouchers, ...) are
--      excluded: they carry a price but have no demand curve.
--   4. Non-positive quantity or price is excluded from the sales grain.

CREATE SCHEMA IF NOT EXISTS staging;

-- Codes that are not goods. Kept as a table so SQL and Python share one
-- definition and the list is visible to anyone reading the warehouse.
DROP TABLE IF EXISTS staging.non_product_codes CASCADE;

CREATE TABLE staging.non_product_codes (
    stock_code text PRIMARY KEY,
    reason     text NOT NULL
);

INSERT INTO staging.non_product_codes (stock_code, reason) VALUES
    ('POST',         'postage'),
    ('DOT',          'dotcom postage'),
    ('C2',           'carriage'),
    ('M',            'manual adjustment'),
    ('BANK CHARGES', 'bank charges'),
    ('B',            'adjust bad debt'),
    ('S',            'samples'),
    ('D',            'discount'),
    ('CRUK',         'charity commission'),
    ('AMAZONFEE',    'marketplace fee'),
    ('ADJUST',       'stock adjustment'),
    ('ADJUST2',      'stock adjustment'),
    ('TEST001',      'test product'),
    ('TEST002',      'test product');


-- Deduplicated source, with each line classified. This is the single pass over
-- raw; everything below selects from it.
DROP TABLE IF EXISTS staging.transactions CASCADE;
DROP TABLE IF EXISTS staging.returns CASCADE;
DROP TABLE IF EXISTS staging.line_audit CASCADE;

CREATE TEMP TABLE _classified AS
WITH deduped AS (
    SELECT DISTINCT ON (invoice, stock_code, quantity, invoice_date, price, customer_id)
           invoice, stock_code, description, quantity, invoice_date,
           price, customer_id, country
    FROM raw.online_retail
    -- Prefer the row that carries a description when duplicates disagree.
    ORDER BY invoice, stock_code, quantity, invoice_date, price, customer_id,
             description NULLS LAST
)
SELECT
    d.*,
    (d.invoice LIKE 'C%')                              AS is_credit_note,
    (npc.stock_code IS NOT NULL
     OR lower(d.stock_code) ~ '^gift')                 AS is_non_product,
    (d.quantity > 0)                                   AS has_positive_quantity,
    (d.price > 0)                                      AS has_positive_price
FROM deduped d
LEFT JOIN staging.non_product_codes npc
       ON upper(d.stock_code) = upper(npc.stock_code);


-- The sales grain: positive-value lines for real goods.
CREATE TABLE staging.transactions AS
SELECT
    invoice,
    stock_code,
    description,
    quantity,
    invoice_date,
    invoice_date::date                       AS invoice_day,
    date_trunc('week', invoice_date)::date   AS invoice_week,
    price                                    AS unit_price,
    (quantity * price)::numeric(14, 2)       AS line_revenue,
    customer_id,
    country
FROM _classified
WHERE NOT is_credit_note
  AND NOT is_non_product
  AND has_positive_quantity
  AND has_positive_price;

ALTER TABLE staging.transactions
    ADD CONSTRAINT transactions_positive_qty   CHECK (quantity > 0),
    ADD CONSTRAINT transactions_positive_price CHECK (unit_price > 0);

CREATE INDEX ON staging.transactions (stock_code);
CREATE INDEX ON staging.transactions (invoice_week);
CREATE INDEX ON staging.transactions (stock_code, invoice_week);
CREATE INDEX ON staging.transactions (customer_id);


-- Returns, kept separately. Quantities are stored positive for convenience.
CREATE TABLE staging.returns AS
SELECT
    invoice,
    stock_code,
    description,
    abs(quantity)                            AS quantity_returned,
    invoice_date,
    date_trunc('week', invoice_date)::date   AS invoice_week,
    price                                    AS unit_price,
    (abs(quantity) * price)::numeric(14, 2)  AS return_value,
    customer_id,
    country
FROM _classified
WHERE is_credit_note
  AND NOT is_non_product
  AND price > 0;

CREATE INDEX ON staging.returns (stock_code);


-- Audit trail: how many source lines each rule removed, so the funnel from
-- 1,067,371 raw rows to the modelling set is reproducible rather than asserted.
CREATE TABLE staging.line_audit AS
SELECT 'raw lines'                AS stage, count(*) AS lines FROM raw.online_retail
UNION ALL
SELECT 'after dedupe',              count(*) FROM _classified
UNION ALL
SELECT 'credit notes',              count(*) FROM _classified WHERE is_credit_note
UNION ALL
SELECT 'non-product codes',         count(*) FROM _classified WHERE is_non_product
UNION ALL
SELECT 'non-positive quantity',     count(*) FROM _classified
                                    WHERE NOT is_credit_note AND NOT has_positive_quantity
UNION ALL
SELECT 'non-positive price',        count(*) FROM _classified
                                    WHERE NOT is_credit_note AND NOT has_positive_price
UNION ALL
SELECT 'clean sales lines',         count(*) FROM staging.transactions;

DROP TABLE _classified;

ANALYZE staging.transactions;
ANALYZE staging.returns;
