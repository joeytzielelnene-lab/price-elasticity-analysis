"""Per-product price elasticity of demand.

Specification, estimated separately for each product i:

    log(units_it) = a + b * log(price_it) + g * log(market_units_it) + e_it

`b` is the price elasticity of demand: the percentage change in units sold for
a 1% change in price. `market_units_it` is total units sold across all *other*
products in week t. It absorbs shocks common to the whole catalogue -- this is
a Christmas-heavy giftware retailer, so without it a product that is both
pricier and busier in Q4 would show a spurious positive elasticity.

Standard errors are Newey-West (HAC), because weekly demand for a given product
is autocorrelated and plain OLS errors would be too small.

What this design does NOT fix, and what the results must be read against:

  * Endogeneity. Prices were set by the retailer, not randomised. If prices
    were raised into strong demand, `b` is biased toward zero, and the true
    response to a price cut is larger than estimated. There is no instrument
    or experiment in this dataset to correct it.
  * Selection. Only weeks with at least one sale appear in the panel. Weeks
    where a high price choked demand to zero are missing, which also biases
    `b` toward zero.
  * Multiplicity. Fitting a regression per product means some will look
    significant by chance. p-values are corrected across products with
    Benjamini-Hochberg FDR; use `p_value_fdr`, not `p_value`.

Treat the output as a ranking of which products look price-sensitive, not as a
causal estimate of what a price change will do.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.multitest import multipletests

from retail_pricing.db import read_sql

# Minimum evidence required before a product is fitted at all. A regression on
# 12 weeks with two distinct prices will happily return a number; it just will
# not mean anything.
MIN_WEEKS = 30
MIN_DISTINCT_PRICES = 5
MIN_PRICE_CV = 0.05  # coefficient of variation of weekly price

HAC_MAXLAGS = 4

# The price the model regresses on. Deliberately the median posted line price,
# not revenue/units: the latter has units in its denominator and would induce a
# negative slope from measurement noise alone. `compare_price_measures` below
# quantifies how much that choice matters.
PRICE_COLUMN = "median_line_price"

PANEL_QUERY = """
SELECT stock_code, week_start, units, revenue,
       avg_price, median_line_price, modal_line_price, invoices
FROM marts.product_week
ORDER BY stock_code, week_start
"""


def load_panel() -> pd.DataFrame:
    """Load the product-week panel and attach the market control.

    The control excludes the product's own units so a large product does not
    partly explain itself.
    """
    panel = read_sql(PANEL_QUERY)
    for col in ("avg_price", "median_line_price", "modal_line_price", "units", "revenue"):
        panel[col] = panel[col].astype(float)

    market = panel.groupby("week_start")["units"].transform("sum")
    panel["market_units"] = market - panel["units"]
    return panel


def _eligible(group: pd.DataFrame, price_col: str) -> bool:
    if len(group) < MIN_WEEKS:
        return False
    price = group[price_col]
    if price.nunique() < MIN_DISTINCT_PRICES:
        return False
    if price.mean() <= 0:
        return False
    return (price.std() / price.mean()) >= MIN_PRICE_CV


def _fit_one(group: pd.DataFrame, price_col: str = PRICE_COLUMN) -> dict | None:
    """Fit the log-log demand model for a single product."""
    g = group[(group[price_col] > 0) & (group["units"] > 0) & (group["market_units"] > 0)]
    if not _eligible(g, price_col):
        return None

    y = np.log(g["units"].to_numpy())
    X = np.column_stack(
        [
            np.log(g[price_col].to_numpy()),
            np.log(g["market_units"].to_numpy()),
        ]
    )
    X = sm.add_constant(X, has_constant="add")

    try:
        model = sm.OLS(y, X).fit(
            cov_type="HAC", cov_kwds={"maxlags": HAC_MAXLAGS}
        )
    except (ValueError, np.linalg.LinAlgError):
        return None

    if not np.isfinite(model.params).all() or not np.isfinite(model.bse).all():
        return None

    price = g[price_col]
    conf = model.conf_int(alpha=0.05)

    return {
        "stock_code": group.name if hasattr(group, "name") else g["stock_code"].iloc[0],
        "elasticity": float(model.params[1]),
        "std_error": float(model.bse[1]),
        "t_stat": float(model.tvalues[1]),
        "p_value": float(model.pvalues[1]),
        "ci_low": float(conf[1][0]),
        "ci_high": float(conf[1][1]),
        "market_beta": float(model.params[2]),
        "r_squared": float(model.rsquared),
        "n_weeks": int(len(g)),
        "price_cv": float(price.std() / price.mean()),
        "min_price": float(price.min()),
        "max_price": float(price.max()),
        "median_price": float(price.median()),
        "total_units": float(g["units"].sum()),
        "total_revenue": float(g["revenue"].sum()),
    }


def estimate_elasticities(
    panel: pd.DataFrame | None = None, price_col: str = PRICE_COLUMN
) -> pd.DataFrame:
    """Fit the demand model for every eligible product.

    Returns one row per fitted product, with FDR-corrected p-values and a
    `defensible` flag marking the subset worth acting on.
    """
    if panel is None:
        panel = load_panel()

    rows = []
    for stock_code, group in panel.groupby("stock_code", sort=False):
        result = _fit_one(group, price_col=price_col)
        if result is not None:
            result["stock_code"] = stock_code
            rows.append(result)

    if not rows:
        return pd.DataFrame()

    out = pd.DataFrame(rows)

    reject, p_fdr, _, _ = multipletests(out["p_value"], alpha=0.05, method="fdr_bh")
    out["p_value_fdr"] = p_fdr
    out["significant_fdr"] = reject

    # A usable estimate is statistically distinguishable from zero after
    # correction AND economically sensible: demand should fall as price rises.
    # A significant positive elasticity is a signal of endogeneity, not of a
    # Giffen good, so it is excluded rather than reported as a finding.
    out["defensible"] = out["significant_fdr"] & (out["elasticity"] < 0)

    out["elastic"] = out["elasticity"] < -1  # revenue rises if price falls
    return out.sort_values("total_revenue", ascending=False).reset_index(drop=True)


def compare_price_measures(panel: pd.DataFrame | None = None) -> pd.DataFrame:
    """Re-estimate under each price measure to expose division bias.

    `avg_price` (revenue/units) shares its denominator with the outcome, so it
    should produce systematically more negative elasticities than the posted
    line prices. The gap between the columns is the size of the artefact, and
    is worth reporting rather than hiding.
    """
    if panel is None:
        panel = load_panel()

    frames = {}
    for col in ("avg_price", "median_line_price", "modal_line_price"):
        res = estimate_elasticities(panel, price_col=col)
        frames[col] = res.set_index("stock_code")["elasticity"]

    wide = pd.DataFrame(frames)
    rows = []
    for col in wide.columns:
        series = wide[col].dropna()
        rows.append(
            {
                "price_measure": col,
                "products_fitted": int(series.notna().sum()),
                "median_elasticity": round(float(series.median()), 3),
                "mean_elasticity": round(float(series.mean()), 3),
                "pct_elastic_below_-1": round(float((series < -1).mean() * 100), 1),
                "pct_wrong_signed": round(float((series > 0).mean() * 100), 1),
            }
        )
    return pd.DataFrame(rows)


def summarise(results: pd.DataFrame) -> pd.DataFrame:
    """One-line-per-fact summary of the estimation run, for the report."""
    defensible = results[results["defensible"]]
    facts = [
        ("products fitted", len(results)),
        ("significant after FDR", int(results["significant_fdr"].sum())),
        ("wrong-signed (positive) elasticity", int((results["elasticity"] > 0).sum())),
        (
            "significant AND positive (endogeneity flag)",
            int((results["significant_fdr"] & (results["elasticity"] > 0)).sum()),
        ),
        ("defensible (significant, negative)", len(defensible)),
        ("  of which elastic (b < -1)", int((defensible["elasticity"] < -1).sum())),
        ("  of which inelastic (-1 <= b < 0)", int((defensible["elasticity"] >= -1).sum())),
        (
            "median elasticity (defensible)",
            round(float(defensible["elasticity"].median()), 3) if len(defensible) else None,
        ),
        (
            "revenue covered by defensible set",
            round(float(defensible["total_revenue"].sum()), 2),
        ),
    ]
    return pd.DataFrame(facts, columns=["metric", "value"])
