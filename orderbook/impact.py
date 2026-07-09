"""Price impact & slippage modeling.

Two complementary views of *how much it costs to trade*:

1. Walk-the-book slippage (empirical):
   For a marketable order of size Q, walk through the levels of the book,
   consume available size at each price, and record the volume-weighted
   average fill price. Slippage = (avg_fill - mid) / mid, in bps.

2. Square-root impact model (theoretical):
   A robust empirical regularity: impact ~ sigma * sqrt(Q / ADV).
   See: Almgren et al. (2005), Gatheral (2010), Bacry et al. (2015).
"""

from __future__ import annotations

from typing import List, Optional

import numpy as np
import pandas as pd


def walk_the_book_slippage(
    df: pd.DataFrame,
    order_sizes: List[float],
    side: str = "buy",
    max_snapshots: Optional[int] = None,
) -> pd.DataFrame:
    """Simulate marketable orders walking the book; compute slippage per size.

    Parameters
    ----------
    df : long-format L2 DataFrame
    order_sizes : list of order sizes (in same units as book qty)
    side : 'buy' (consume asks) or 'sell' (consume bids)
    max_snapshots : cap on snapshots processed (None => all). Useful for
        keeping runtime bounded on huge datasets.

    Returns
    -------
    DataFrame with one row per order_size:
        order_size, avg_slippage_bps, p50, p95, fill_rate
    """
    if side not in ("buy", "sell"):
        raise ValueError("side must be 'buy' or 'sell'")

    snapshots = list(df.groupby("timestamp"))
    if max_snapshots is not None and len(snapshots) > max_snapshots:
        # Evenly subsample
        idx = np.linspace(0, len(snapshots) - 1, max_snapshots, dtype=int)
        snapshots = [snapshots[i] for i in idx]

    results = []
    for size in order_sizes:
        slippages = []
        for _, snap in snapshots:
            snap = snap.sort_values("level")
            mid = snap["mid"].iloc[0]

            if side == "buy":
                prices = snap["ask_price"].values
                qtys = snap["ask_qty"].values
            else:
                prices = snap["bid_price"].values
                qtys = snap["bid_qty"].values

            remaining = size
            total_cost = 0.0
            for price, qty in zip(prices, qtys):
                if remaining <= 0:
                    break
                filled = min(remaining, qty)
                total_cost += filled * price
                remaining -= filled

            if remaining > 0:
                # Book exhausted before order filled -> skip this snapshot
                continue

            avg_price = total_cost / size
            if side == "buy":
                slip_bps = (avg_price - mid) / mid * 10_000.0
            else:
                slip_bps = (mid - avg_price) / mid * 10_000.0
            slippages.append(slip_bps)

        if not slippages:
            results.append({
                "order_size": size,
                "avg_slippage_bps": np.nan,
                "p50_slippage_bps": np.nan,
                "p95_slippage_bps": np.nan,
                "fill_rate": 0.0,
            })
            continue

        results.append({
            "order_size": size,
            "avg_slippage_bps": float(np.mean(slippages)),
            "p50_slippage_bps": float(np.percentile(slippages, 50)),
            "p95_slippage_bps": float(np.percentile(slippages, 95)),
            "fill_rate": float(len(slippages) / len(snapshots)),
        })

    return pd.DataFrame(results)


def square_root_impact(
    df: pd.DataFrame,
    order_sizes: List[float],
    sigma: Optional[float] = None,
    adv: Optional[float] = None,
) -> pd.DataFrame:
    """Square-root impact model: I(Q) = sigma * sqrt(Q / ADV).

    Parameters
    ----------
    df : long-format L2 DataFrame (used to estimate sigma and ADV if not given)
    order_sizes : list of order sizes
    sigma : per-snapshot volatility of mid returns (estimated if None)
    adv : average daily volume proxy (estimated as mean per-snapshot total
        depth if None)

    Returns
    -------
    DataFrame: order_size, sigma, adv, impact_bps
    """
    mid = df.groupby("timestamp")["mid"].first()
    rets = np.log(mid).diff().dropna()

    if sigma is None:
        sigma = float(rets.std())

    if adv is None:
        # Proxy: mean total book size per snapshot
        adv = float(df.groupby("timestamp")[["bid_qty", "ask_qty"]].sum().sum(axis=1).mean())

    rows = []
    for Q in order_sizes:
        impact = sigma * np.sqrt(Q / adv) * 10_000.0
        rows.append({
            "order_size": Q,
            "sigma": sigma,
            "adv": adv,
            "impact_bps": float(impact),
        })
    return pd.DataFrame(rows)
