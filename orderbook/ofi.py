"""Order Flow Imbalance (OFI).

OFI is a microstructure signal introduced by Cont, Kukanov & Stoikov (2014,
"Price Impact of Order Book Imbalance"). The intuition:

  When the bid queue grows, sellers are pulling liquidity / buyers are
  adding it => upward price pressure. When the ask queue grows, the
  opposite. We measure the *change* in queue size at the top levels
  between consecutive snapshots, sum the bid deltas, subtract the ask
  deltas, and call that OFI(t).

  OFI(t) = sum_l [ dBidQty_l(t) - dAskQty_l(t) ]

A strong empirical regularity is that OFI is positively correlated with
short-horizon mid-price returns — i.e., the order book "leans" before the
price moves. We expose that correlation here.
"""

from __future__ import annotations

from typing import Tuple

import numpy as np
import pandas as pd


def compute_ofi(df: pd.DataFrame, n_levels: int = 10) -> Tuple[pd.DataFrame, float]:
    """Compute per-snapshot OFI and its correlation with short-horizon returns.

    Parameters
    ----------
    df : long-format L2 DataFrame
    n_levels : how many top levels to include in the imbalance sum.

    Returns
    -------
    ofi_df : DataFrame indexed by timestamp with columns
        bid_delta_sum, ask_delta_sum, ofi, mid, mid_ret, ofi_roll_50
    corr   : Pearson correlation between OFI(t) and mid_ret(t+1)
             (lagged so we measure predictive content, not contemporaneous).
    """
    top = df[df["level"] < n_levels].copy()
    top = top.sort_values(["timestamp", "level"]).reset_index(drop=True)

    # Per-level queue changes between consecutive snapshots
    top["bid_qty_prev"] = top.groupby("level")["bid_qty"].shift(1)
    top["ask_qty_prev"] = top.groupby("level")["ask_qty"].shift(1)
    top["bid_delta"] = top["bid_qty"] - top["bid_qty_prev"]
    top["ask_delta"] = top["ask_qty"] - top["ask_qty_prev"]

    # First snapshot has no previous => deltas are NaN; fill with 0
    top[["bid_delta", "ask_delta"]] = top[["bid_delta", "ask_delta"]].fillna(0.0)

    by_ts = top.groupby("timestamp").agg(
        bid_delta_sum=("bid_delta", "sum"),
        ask_delta_sum=("ask_delta", "sum"),
    )
    by_ts["ofi"] = by_ts["bid_delta_sum"] - by_ts["ask_delta_sum"]

    # Mid + 1-snapshot log return
    by_ts["mid"] = df.groupby("timestamp")["mid"].first()
    by_ts["mid_ret"] = np.log(by_ts["mid"]).diff().fillna(0.0)

    # Rolling OFI (cumulative pressure over last 50 snapshots)
    by_ts["ofi_roll_50"] = by_ts["ofi"].rolling(50, min_periods=1).sum()

    # Predictive correlation: corr(OFI(t), mid_ret(t+1))
    ofi_df = by_ts.reset_index()
    ofi_df["mid_ret_lead1"] = ofi_df["mid_ret"].shift(-1).fillna(0.0)
    mask = ofi_df["ofi"].notna() & ofi_df["mid_ret_lead1"].notna()
    corr = float(ofi_df.loc[mask, ["ofi", "mid_ret_lead1"]].corr().iloc[0, 1])
    return ofi_df, corr


def ofi_summary_stats(ofi_df: pd.DataFrame) -> pd.DataFrame:
    """One-row summary of OFI distribution."""
    row = {
        "ofi_mean": ofi_df["ofi"].mean(),
        "ofi_std": ofi_df["ofi"].std(),
        "ofi_skew": ofi_df["ofi"].skew(),
        "ofi_kurt": ofi_df["ofi"].kurt(),
        "ofi_roll50_mean": ofi_df["ofi_roll_50"].mean(),
        "ofi_roll50_std": ofi_df["ofi_roll_50"].std(),
    }
    return pd.DataFrame([row])
