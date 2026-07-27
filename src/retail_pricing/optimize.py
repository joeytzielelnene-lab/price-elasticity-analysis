"""Translate estimated elasticities into bounded price recommendations.

A note on why there is no "optimal price" column here.

Under a constant-elasticity demand curve, revenue is R(p) = k * p^(1+b). That
is monotonic in price: if b < -1 revenue rises without limit as price falls,
and if -1 < b < 0 it rises without limit as price rises. There is no interior
maximum to solve for. Any case study that reports a single revenue-optimal
price from a log-log model has quietly assumed something it did not estimate.

So this module answers a narrower and answerable question instead: for a small
price move, in which direction does revenue go, and by roughly how much? Moves
are bounded twice --

  * to +/- `max_change_pct`, because the elasticity is a local approximation
    and nothing licenses extrapolating it far from observed prices; and
  * to the price range the product has actually traded at, so a recommendation
    is never outside the support of the data it came from.

REVENUE IS NOT PROFIT. This dataset has no cost of goods, so margin cannot be
computed. Recommending a price cut on an elastic product raises revenue and may
still destroy profit -- selling 20% more units at a 10% lower price is a loss if
the gross margin is under ~50%. The price *increases* on inelastic products are
the trustworthy half of this output: they raise revenue and unit margin at once.
Read the cuts as candidates for a margin review, not as instructions.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Elasticities beyond this magnitude are treated as noise rather than signal.
# A -14 elasticity implies a 1% price rise wipes out 14% of volume; in practice
# it means the product had little price variation and the fit latched onto it.
MAX_PLAUSIBLE_ELASTICITY = 5.0

DEFAULT_MAX_CHANGE_PCT = 0.10


def _revenue_ratio(elasticity: np.ndarray, pct_change: np.ndarray) -> np.ndarray:
    """Revenue multiplier from a proportional price change under R = k*p^(1+b)."""
    return np.power(1.0 + pct_change, 1.0 + elasticity)


def recommend_price_changes(
    results: pd.DataFrame,
    max_change_pct: float = DEFAULT_MAX_CHANGE_PCT,
    max_abs_elasticity: float = MAX_PLAUSIBLE_ELASTICITY,
) -> pd.DataFrame:
    """Bounded price-move recommendations for the defensible product set.

    The projected revenue range is derived from the 95% confidence interval of
    each elasticity, so products whose elasticity is barely identified show a
    correspondingly wide range instead of a falsely precise number.
    """
    df = results[
        results["defensible"] & (results["elasticity"].abs() <= max_abs_elasticity)
    ].copy()

    if df.empty:
        return df

    # Elastic products: cut price. Inelastic: raise it.
    df["direction"] = np.where(df["elasticity"] < -1, "decrease", "increase")
    signed_change = np.where(df["direction"] == "decrease", -max_change_pct, max_change_pct)

    current = df["median_price"].to_numpy()
    proposed = current * (1.0 + signed_change)

    # Never recommend a price the product has not actually traded near.
    proposed = np.clip(proposed, df["min_price"].to_numpy(), df["max_price"].to_numpy())
    realised_change = proposed / current - 1.0

    df["current_price"] = current
    df["recommended_price"] = np.round(proposed, 2)
    df["price_change_pct"] = np.round(realised_change * 100, 2)

    elasticity = df["elasticity"].to_numpy()
    df["projected_revenue_ratio"] = _revenue_ratio(elasticity, realised_change)
    df["projected_revenue_change_pct"] = np.round(
        (df["projected_revenue_ratio"] - 1.0) * 100, 2
    )
    df["projected_revenue_delta"] = np.round(
        df["total_revenue"] * (df["projected_revenue_ratio"] - 1.0), 2
    )

    # Uncertainty: propagate the elasticity CI through the same formula.
    low = _revenue_ratio(df["ci_low"].to_numpy(), realised_change)
    high = _revenue_ratio(df["ci_high"].to_numpy(), realised_change)
    df["revenue_delta_low"] = np.round(
        df["total_revenue"] * (np.minimum(low, high) - 1.0), 2
    )
    df["revenue_delta_high"] = np.round(
        df["total_revenue"] * (np.maximum(low, high) - 1.0), 2
    )
    # A recommendation is only robust if the whole CI agrees on the sign.
    df["ci_agrees_on_sign"] = (df["revenue_delta_low"] > 0) == (
        df["revenue_delta_high"] > 0
    )

    columns = [
        "stock_code",
        "elasticity",
        "ci_low",
        "ci_high",
        "n_weeks",
        "r_squared",
        "direction",
        "current_price",
        "recommended_price",
        "price_change_pct",
        "total_revenue",
        "projected_revenue_change_pct",
        "projected_revenue_delta",
        "revenue_delta_low",
        "revenue_delta_high",
        "ci_agrees_on_sign",
    ]
    return df[columns].sort_values(
        "projected_revenue_delta", ascending=False
    ).reset_index(drop=True)


def portfolio_impact(recommendations: pd.DataFrame) -> pd.DataFrame:
    """Aggregate the recommendations, separating the trustworthy half.

    Price increases on inelastic products are reported separately because they
    are the only recommendations that improve revenue and margin together
    without cost data.
    """
    if recommendations.empty:
        return pd.DataFrame()

    robust = recommendations[recommendations["ci_agrees_on_sign"]]
    increases = robust[robust["direction"] == "increase"]
    decreases = robust[robust["direction"] == "decrease"]

    def block(name: str, frame: pd.DataFrame) -> dict:
        return {
            "segment": name,
            "products": len(frame),
            "current_revenue": round(float(frame["total_revenue"].sum()), 2),
            "projected_delta": round(float(frame["projected_revenue_delta"].sum()), 2),
            "delta_low": round(float(frame["revenue_delta_low"].sum()), 2),
            "delta_high": round(float(frame["revenue_delta_high"].sum()), 2),
            "pct_of_segment_revenue": round(
                float(
                    frame["projected_revenue_delta"].sum()
                    / frame["total_revenue"].sum()
                    * 100
                ),
                2,
            )
            if len(frame) and frame["total_revenue"].sum()
            else 0.0,
        }

    return pd.DataFrame(
        [
            block("price increases (inelastic, margin-safe)", increases),
            block("price decreases (elastic, needs margin check)", decreases),
            block("all robust recommendations", robust),
        ]
    )
