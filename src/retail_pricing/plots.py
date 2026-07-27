"""Charts for the pricing study.

Figures are rendered on a light surface only: they are committed as static PNGs
in outputs/ and embedded in the report, so there is no viewer theme to follow.
Colours come from a validated categorical palette -- slots are assigned in fixed
order and never cycled.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from retail_pricing.config import OUTPUTS_DIR

# Categorical slots, in fixed assignment order.
SERIES_1 = "#2a78d6"  # blue
SERIES_2 = "#eb6834"  # orange

SURFACE = "#fcfcfb"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"

FIGSIZE = (10, 5.5)
DPI = 160


def use_house_style() -> None:
    """Apply the chart chrome: recessive grid and axes, ink-coloured text."""
    mpl.rcParams.update(
        {
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "savefig.facecolor": SURFACE,
            "font.family": "sans-serif",
            "font.size": 10,
            "axes.titlesize": 13,
            "axes.titleweight": "bold",
            "axes.titlecolor": INK_PRIMARY,
            "axes.labelcolor": INK_SECONDARY,
            "axes.labelsize": 10,
            "axes.edgecolor": BASELINE,
            "axes.linewidth": 1.0,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "xtick.color": INK_MUTED,
            "ytick.color": INK_MUTED,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "grid.color": GRIDLINE,
            "grid.linewidth": 0.8,
            "legend.frameon": False,
            "legend.fontsize": 9,
            "legend.labelcolor": INK_SECONDARY,
            "lines.linewidth": 2.0,
        }
    )


def _finish(ax, title: str, subtitle: str | None = None) -> None:
    ax.set_title(title, loc="left", pad=18 if subtitle else 10)
    if subtitle:
        ax.text(
            0.0,
            1.02,
            subtitle,
            transform=ax.transAxes,
            fontsize=9.5,
            color=INK_SECONDARY,
            va="bottom",
        )
    ax.grid(axis="y", alpha=0.9)
    ax.set_axisbelow(True)


def _save(fig, name: str) -> Path:
    path = OUTPUTS_DIR / name
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    return path


def plot_weekly_revenue(weekly: pd.DataFrame, save_as: str = "weekly_revenue.png") -> Path:
    """Trading trend. Single series, so the title names it and no legend is needed."""
    use_house_style()
    fig, ax = plt.subplots(figsize=FIGSIZE)

    x = pd.to_datetime(weekly["week_start"])
    y = weekly["revenue"].astype(float)
    ax.plot(x, y, color=SERIES_1)

    # The source starts mid-week (01 Dec 2009) and ends mid-week (09 Dec 2011),
    # so the first and last points cover fewer than seven days. Labelling the
    # global maximum without excluding them would headline a truncated week.
    interior = y.iloc[1:-1]
    peak = int(interior.idxmax())
    ax.scatter([x.iloc[peak]], [y.iloc[peak]], s=40, color=SERIES_1, zorder=3)
    ax.annotate(
        f"peak full week  £{y.iloc[peak]:,.0f}\n{x.iloc[peak]:%d %b %Y}",
        (x.iloc[peak], y.iloc[peak]),
        textcoords="offset points",
        xytext=(-14, 14),
        ha="right",
        fontsize=9,
        color=INK_SECONDARY,
    )

    # Mark the partial weeks so the end points are not read as a collapse/spike.
    for idx in (0, len(y) - 1):
        ax.scatter([x.iloc[idx]], [y.iloc[idx]], s=28, facecolor=SURFACE,
                   edgecolor=INK_MUTED, linewidth=1.4, zorder=3)
    ax.annotate(
        "partial weeks",
        (x.iloc[-1], y.iloc[-1]),
        textcoords="offset points",
        xytext=(-6, 10),
        ha="right",
        fontsize=8.5,
        color=INK_MUTED,
    )

    ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda v, _: f"£{v/1000:,.0f}k"))
    ax.set_ylabel("Weekly revenue")
    ax.set_xlabel("")
    _finish(
        ax,
        "Weekly revenue, Dec 2009 – Dec 2011",
        "Cleaned sales lines only. Both Q4 peaks are the gifting season; hollow points are partial weeks.",
    )
    return _save(fig, save_as)


def plot_division_bias(comparison_long: pd.DataFrame, save_as: str = "division_bias.png") -> Path:
    """Why the price measure matters.

    Expects a long frame with columns `measure` and `elasticity`, holding the
    per-product estimates under revenue/units versus the median posted price.
    """
    use_house_style()
    fig, ax = plt.subplots(figsize=FIGSIZE)

    lo, hi = -6.0, 1.0
    bins = np.linspace(lo, hi, 60)
    spec = [
        ("median_line_price", SERIES_1, "Median posted price"),
        ("avg_price", SERIES_2, "Revenue ÷ units"),
    ]
    trimmed = 0
    for measure, colour, label in spec:
        vals = comparison_long.loc[comparison_long["measure"] == measure, "elasticity"]
        # Drop out-of-range estimates rather than clipping them: clipping piles
        # every outlier into the end bin and invents a spike that isn't there.
        trimmed += int(((vals < lo) | (vals > hi)).sum())
        vals = vals[(vals >= lo) & (vals <= hi)]
        ax.hist(vals, bins=bins, color=colour, alpha=0.55, label=label, edgecolor=SURFACE, linewidth=0.5)

    ax.axvline(-1, color=INK_MUTED, linestyle="--", linewidth=1.2)
    ax.text(-1.05, ax.get_ylim()[1] * 0.94, "unit elastic", rotation=90,
            ha="right", va="top", fontsize=8.5, color=INK_MUTED)

    ax.set_xlabel("Estimated price elasticity")
    ax.set_ylabel("Products")
    ax.legend(loc="upper left")
    _finish(
        ax,
        "Division bias inflates estimated elasticity",
        f"Revenue÷units puts quantity on both sides of the regression, shifting the distribution left. "
        f"{trimmed} estimates outside [{lo:.0f}, {hi:.0f}] not shown.",
    )
    return _save(fig, save_as)


def plot_elasticity_distribution(
    results: pd.DataFrame, save_as: str = "elasticity_distribution.png"
) -> Path:
    """Distribution of the defensible estimates, split at unit elasticity."""
    use_house_style()
    fig, ax = plt.subplots(figsize=FIGSIZE)

    all_vals = results.loc[results["defensible"], "elasticity"]
    lo, hi = -6.0, 0.5
    trimmed = int(((all_vals < lo) | (all_vals > hi)).sum())
    vals = all_vals[(all_vals >= lo) & (all_vals <= hi)]

    bins = np.linspace(lo, hi, 55)
    counts, edges = np.histogram(vals, bins=bins)
    centres = (edges[:-1] + edges[1:]) / 2
    colours = [SERIES_1 if c < -1 else SERIES_2 for c in centres]

    ax.bar(centres, counts, width=(edges[1] - edges[0]) * 0.9, color=colours, edgecolor=SURFACE, linewidth=0.5)
    ax.axvline(-1, color=INK_MUTED, linestyle="--", linewidth=1.2)

    # Identity via a colour swatch beside ink-coloured text, never coloured text.
    n_elastic = int((all_vals < -1).sum())
    n_inelastic = int((all_vals >= -1).sum())
    handles = [
        mpl.patches.Patch(color=SERIES_1, label=f"Elastic (β < −1): {n_elastic:,}"),
        mpl.patches.Patch(color=SERIES_2, label=f"Inelastic (−1 ≤ β < 0): {n_inelastic:,}"),
    ]
    ax.legend(handles=handles, loc="upper left")

    ax.set_xlabel("Estimated price elasticity (β)")
    ax.set_ylabel("Products")
    _finish(
        ax,
        "Estimated elasticity, statistically defensible products only",
        f"Significant after Benjamini-Hochberg FDR correction and correctly signed. "
        f"{trimmed} estimates below {lo:.0f} not shown.",
    )
    return _save(fig, save_as)


def plot_elasticity_vs_revenue(
    results: pd.DataFrame, save_as: str = "elasticity_vs_revenue.png"
) -> Path:
    """Where the money sits relative to price sensitivity."""
    use_house_style()
    fig, ax = plt.subplots(figsize=FIGSIZE)

    d = results[results["defensible"] & (results["elasticity"].abs() <= 5)]
    elastic = d[d["elasticity"] < -1]
    inelastic = d[d["elasticity"] >= -1]

    for frame, colour, label in (
        (elastic, SERIES_1, "Elastic (β < −1)"),
        (inelastic, SERIES_2, "Inelastic (−1 ≤ β < 0)"),
    ):
        ax.scatter(
            frame["elasticity"],
            frame["total_revenue"].astype(float),
            s=22,
            color=colour,
            alpha=0.6,
            edgecolor=SURFACE,
            linewidth=0.5,
            label=label,
        )

    ax.set_yscale("log")
    ax.axvline(-1, color=INK_MUTED, linestyle="--", linewidth=1.2)
    ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda v, _: f"£{v:,.0f}"))
    ax.set_xlabel("Estimated price elasticity (β)")
    ax.set_ylabel("Revenue over the period (log scale)")
    ax.legend(loc="lower left")
    _finish(
        ax,
        "Price sensitivity against revenue at stake",
        "Each point is one product. Estimates beyond |β| > 5 are excluded as noise.",
    )
    return _save(fig, save_as)
