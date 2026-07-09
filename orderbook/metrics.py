"""Liquidity metrics: bid-ask spread, depth, cumulative depth, heatmap.

All functions accept the long-format L2 DataFrame produced by
`orderbook.data.generate_synthetic_l2` or `orderbook.data.load_l2_csv`
and return tidy DataFrames suitable for plotting or further analysis.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def bid_ask_spread(df: pd.DataFrame, tick_size: float = 0.01) -> pd.DataFrame:
    """Per-snapshot bid-ask spread.

    Returns a DataFrame with one row per snapshot:
        timestamp
        mid
        spread_abs   : best_ask - best_bid (price units)
        spread_ticks : spread_abs / tick_size
        spread_bps   : spread_abs / mid * 10_000 (basis points)
    """
    snap = df[df["level"] == 0].copy().sort_values("timestamp").reset_index(drop=True)
    snap["spread_abs"] = snap["ask_price"] - snap["bid_price"]
    snap["spread_ticks"] = snap["spread_abs"] / tick_size
    snap["spread_bps"] = snap["spread_abs"] / snap["mid"] * 10_000.0
    return snap[["timestamp", "mid", "spread_abs", "spread_ticks", "spread_bps"]]


def depth_at_top_n(df: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    """Total available size in the top N levels, per side, per snapshot.

    Returns:
        timestamp, bid_depth, ask_depth, total_depth
    """
    top = df[df["level"] < n]
    agg = top.groupby("timestamp").agg(
        bid_depth=("bid_qty", "sum"),
        ask_depth=("ask_qty", "sum"),
    ).reset_index()
    agg["total_depth"] = agg["bid_depth"] + agg["ask_depth"]
    return agg


def mean_size_per_level(df: pd.DataFrame) -> pd.DataFrame:
    """Time-averaged size at each level (one row per level).

    Returns: level, bid_qty (mean), ask_qty (mean)
    Use this for the per-level bar chart — distinct from the cumulative
    depth curve, which adds a running sum on top of the same per-level means.
    """
    return df.groupby("level").agg(
        bid_qty=("bid_qty", "mean"),
        ask_qty=("ask_qty", "mean"),
    ).reset_index()


def cumulative_depth_curve(df: pd.DataFrame) -> pd.DataFrame:
    """Time-averaged cumulative depth as a function of level.

    Returns:
        level, bid_qty (mean), ask_qty (mean),
        cum_bid, cum_ask, cum_total
    """
    by_level = mean_size_per_level(df)
    by_level["cum_bid"] = by_level["bid_qty"].cumsum()
    by_level["cum_ask"] = by_level["ask_qty"].cumsum()
    by_level["cum_total"] = by_level["cum_bid"] + by_level["cum_ask"]
    return by_level


def liquidity_heatmap(
    df: pd.DataFrame,
    n_levels: int = 20,
    n_bins: int = 50,
    value_col: str = "total_qty",
) -> pd.DataFrame:
    """Time x level heatmap of available liquidity.

    Splits the snapshot stream into `n_bins` equal-width time bins, then
    averages `value_col` (default: bid_qty + ask_qty) within each
    (time_bin, level) cell.

    Returns a DataFrame with:
        index  = time_bin (0..n_bins-1)
        columns= level (0..n_levels-1)
        values = mean total size in that cell
    """
    df = df.copy()
    if value_col == "total_qty":
        df["total_qty"] = df["bid_qty"] + df["ask_qty"]

    df = df[df["level"] < n_levels]
    df["time_bin"] = pd.cut(df["timestamp"], bins=n_bins, labels=False)
    heat = df.pivot_table(
        index="time_bin", columns="level", values=value_col, aggfunc="mean"
    )
    # Fill any NaN (shouldn't be any if long format is complete)
    heat = heat.fillna(0.0)
    return heat


def book_imbalance(df: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    """Bid/ask imbalance at top-N: (bid_depth - ask_depth) / (bid_depth + ask_depth).

    Returns: timestamp, imbalance  (range: -1 .. +1)
    Positive imbalance => more size on bid side (typical "buy pressure" proxy).
    """
    d = depth_at_top_n(df, n=n)
    d["imbalance"] = (d["bid_depth"] - d["ask_depth"]) / d["total_depth"].replace(0, np.nan)
    return d[["timestamp", "imbalance"]]
