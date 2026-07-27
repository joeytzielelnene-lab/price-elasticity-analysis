# Findings

UCI *Online Retail II* — a UK online giftware retailer, 1 Dec 2009 to 9 Dec 2011.
1,067,371 raw invoice lines, £19.6M of cleaned revenue across 4,895 products.

---

## Summary

A bounded ±10% price move across the products where demand could be estimated
projects **+£622k of revenue (+11.7%)**. That number should not be quoted
without the sentence that follows it:

> £621k of the £622k comes from **price cuts** whose profitability cannot be
> verified, because the dataset has no cost of goods. Only **£1.3k** comes from
> the margin-safe half.

The analysis is worth more for what it rules out than for the headline.

---

## 1. Data quality

1,067,371 raw lines → 1,003,355 clean sales lines (94.0% retained).

| Stage | Lines |
|---|---:|
| Raw | 1,067,371 |
| After dedupe | 1,033,034 |
| Credit notes (returns) | 19,104 |
| Non-product codes | 5,800 |
| Non-positive quantity | 3,393 |
| Non-positive price | 6,019 |
| **Clean sales lines** | **1,003,355** |

Three decisions worth defending:

**Duplicates were real and material.** 34,337 rows (3.2%) exactly repeat another
row's invoice, product, quantity, timestamp, price and customer. These are
data-entry artefacts, and leaving them in would inflate the quantities the
demand model is fitted on.

**The exclusion list was read, not pattern-matched.** Fee and adjustment codes
(`POST`, `DOT`, `BANK CHARGES`, `AMAZONFEE`, gift vouchers, …) carry a price but
have no demand curve. The obvious filter — require `StockCode` to match
`^[0-9]{5}` — would also have dropped the `DCGS*` codes, which are genuine
catalogue items (`SUNJAR LED NIGHT LIGHT`, `MISO PRETTY GUM`). Inspecting the
irregular codes individually avoided a silent, invisible data loss.

**Returns were separated, not deleted.** Credit notes go to `staging.returns`,
so return behaviour stays analysable. Returns run at 3.65% of revenue.

### Known limitations of the cleaned data

- **22.8% of lines have no `customer_id`.** Fine for pricing, which works at the
  product-week grain. Not fine for RFM, which necessarily describes only the
  attributed 77% of the business.
- **First and last weeks are partial.** The source begins on a Tuesday and ends
  on a Friday. The final 5-day week records £484k, higher than any complete
  week — the peak *full* week is £373k (14 Nov 2011). Charts mark both.
- **Returns cannot be matched to their original sale.** Credit notes carry no
  reference to the originating invoice, so return rates are joined on
  `stock_code` only and are approximate.

---

## 2. Descriptive

- **Revenue is highly concentrated**: the top 20% of products carry **78.7%** of
  revenue — steeper than the classic 80/20.
- **The business is domestic**: the UK is **85.5%** of revenue. EIRE (3.2%),
  Netherlands (2.8%), Germany (2.0%) and France (1.6%) follow. Country-level
  pricing conclusions outside the UK rest on thin data.
- **Strongly seasonal**: Q4 roughly doubles the rest of the year. This is why
  the demand model carries a market-wide control — without it, a product that is
  both pricier and busier at Christmas would appear price-*insensitive* purely
  from the season.

---

## 3. Price elasticity

Per product, on weekly data:

```
log(units_it) = α + β·log(price_it) + γ·log(market_units_it) + ε_it
```

`market_units` is total units across all *other* products that week, absorbing
catalogue-wide seasonality. Standard errors are Newey-West (HAC, 4 lags), since
weekly demand is autocorrelated. Products need ≥30 weeks, ≥5 distinct prices and
a price CV ≥ 0.05 to be fitted at all.

| | |
|---|---:|
| Products fitted | 1,885 |
| Significant after FDR correction | 1,547 |
| Defensible (significant **and** correctly signed) | 1,546 |
| — elastic (β < −1) | 1,422 |
| — inelastic (−1 ≤ β < 0) | 124 |
| Median elasticity | **−1.79** |

p-values are Benjamini-Hochberg corrected across products: ~1,900 regressions
will otherwise produce significant-looking results by chance alone.

### The finding that changed the answer

The first version of this analysis used `avg_price = revenue / units` as the
regressor and produced a median elasticity of **−2.39**, with 90.5% of products
elastic. That is an artefact, not a result.

Units appear in the denominator of that price measure and in the numerator of
the outcome, so measurement noise in units alone produces a negative slope —
**division bias**. Re-estimating on price measures that do not contain quantity:

| Price measure | Products fitted | Median β | % elastic |
|---|---:|---:|---:|
| `revenue ÷ units` | 2,388 | **−2.39** | 90.5% |
| Median posted line price | 1,885 | **−1.62** | 81.0% |
| Modal posted line price | 1,110 | **−1.61** | 82.0% |

The two quantity-independent measures agree closely with each other and differ
sharply from the biased one. The study uses the median posted price. **The
choice of price measure moved the headline elasticity by ~47% — more than any
modelling choice made afterwards.**

---

## 4. Recommendations, and why there is no "optimal price"

Under constant elasticity, revenue is `R(p) = k·p^(1+β)` — monotonic in price.
If β < −1 revenue rises without limit as price falls; if −1 < β < 0 it rises
without limit as price rises. **There is no interior maximum.** A single
"revenue-optimal price" derived from a log-log model is an assumption smuggled
in as a result.

So the output is a *bounded* move instead: ±10%, clipped to the price range each
product has actually traded at, with the projected revenue range propagated from
each elasticity's 95% confidence interval. Estimates with |β| > 5 are dropped as
noise, and a recommendation only counts as robust if the whole CI agrees on the
sign of the revenue change.

| Segment | Products | Current revenue | Projected Δ | Range |
|---|---:|---:|---:|---|
| Price **increases** (inelastic, margin-safe) | 11 | £25,715 | **+£1,292** | £429 – £2,184 |
| Price **decreases** (elastic, needs margin check) | 867 | £5,275,062 | **+£620,754** | £237,608 – £1,054,463 |
| All robust | 878 | £5,300,777 | +£622,046 | £238,037 – £1,056,648 |

### Why the margin-safe set is so small

Only 11 of 124 inelastic products survive. For products near unit elasticity the
confidence interval straddles β = −1, and the *sign* of the revenue effect flips
across that boundary — so the recommendation is not robust. That is the
estimator being honest, not a bug.

### Revenue is not profit

There is no cost of goods in this dataset. Cutting price 10% on a product with
β = −2 raises revenue, but is a loss if gross margin is below roughly 50%.
**The price increases are the trustworthy half of this output** — they raise
revenue and unit margin together. The cuts are a shortlist for a margin review,
not instructions.

---

## 5. What would be needed to make this causal

The estimates are associations. Prices here were set by the retailer in response
to conditions we cannot observe, which biases β toward zero in the usual case
(prices raised into strong demand), meaning true price sensitivity is probably
*understated*. Selection compounds it: weeks where a high price choked demand to
zero never appear in the panel.

Fixing that needs one of:

- **A randomised price experiment** — the only clean answer.
- **A cost shock or supplier price change as an instrument** — none is present here.
- **Competitor prices**, to separate own-price effects from market movement.
- **Cost of goods**, to optimise profit rather than revenue.

Absent those, treat this as a **ranking of which products look price-sensitive**
and a prioritised list for testing — not as a forecast of what a price change
will deliver.
