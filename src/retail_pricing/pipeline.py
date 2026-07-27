"""Run the whole study end to end.

    uv run python -m retail_pricing.pipeline            # SQL + models + figures
    uv run python -m retail_pricing.pipeline --reload   # also reload raw from Excel

Every step is idempotent, so re-running rebuilds the warehouse and the outputs
from the source workbook without manual cleanup.
"""

from __future__ import annotations

import argparse

import pandas as pd

from retail_pricing import elasticity as el
from retail_pricing import plots
from retail_pricing.config import OUTPUTS_DIR
from retail_pricing.db import read_sql, run_migrations
from retail_pricing.ingest import load_raw
from retail_pricing.optimize import portfolio_impact, recommend_price_changes


def _write(frame: pd.DataFrame, stem: str) -> None:
    frame.to_csv(OUTPUTS_DIR / f"{stem}.csv", index=False)
    frame.to_parquet(OUTPUTS_DIR / f"{stem}.parquet", index=False)


def run(reload_raw: bool = False) -> dict[str, pd.DataFrame]:
    if reload_raw:
        rows = load_raw()
        print(f"raw.online_retail: {rows:,} rows")

    scripts = run_migrations()
    print(f"SQL applied: {', '.join(scripts)}")

    audit = read_sql("SELECT * FROM staging.line_audit")
    print("\nCleaning funnel:")
    print(audit.to_string(index=False))

    panel = el.load_panel()
    print(f"\nPanel: {panel.shape[0]:,} product-weeks")

    # Sensitivity of the headline result to the price measure, run first so the
    # main estimates are read in that context.
    comparison = el.compare_price_measures(panel)
    print("\nPrice-measure sensitivity:")
    print(comparison.to_string(index=False))
    _write(comparison, "price_measure_comparison")

    results = el.estimate_elasticities(panel)
    summary = el.summarise(results)
    print("\nEstimation summary:")
    print(summary.to_string(index=False))
    _write(results, "elasticities")
    _write(summary, "estimation_summary")

    recs = recommend_price_changes(results)
    impact = portfolio_impact(recs)
    print("\nPortfolio impact of a bounded ±10% move:")
    print(impact.to_string(index=False))
    _write(recs, "price_recommendations")
    _write(impact, "portfolio_impact")

    weekly = read_sql("SELECT * FROM marts.weekly_revenue ORDER BY week_start")
    long = pd.concat(
        [
            el.estimate_elasticities(panel, price_col=col)
            .assign(measure=col)[["measure", "elasticity"]]
            for col in ("median_line_price", "avg_price")
        ]
    )

    figures = [
        plots.plot_weekly_revenue(weekly),
        plots.plot_division_bias(long),
        plots.plot_elasticity_distribution(results),
        plots.plot_elasticity_vs_revenue(results),
    ]
    print("\nFigures:")
    for path in figures:
        print(f"  {path.relative_to(OUTPUTS_DIR.parent)}")

    return {
        "audit": audit,
        "comparison": comparison,
        "results": results,
        "summary": summary,
        "recommendations": recs,
        "impact": impact,
        "weekly": weekly,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reload", action="store_true", help="reload raw.online_retail from the workbook"
    )
    args = parser.parse_args()
    run(reload_raw=args.reload)


if __name__ == "__main__":
    main()
