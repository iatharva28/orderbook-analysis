"""Signal-to-strategy backtest: OFI -> simple long/short rule -> P&L.

The Cont, Kukanov & Stoikov (2014) paper shows OFI predicts short-horizon
returns. This module turns that statistical fact into a minimal trading
strategy so the project demonstrates signal *and* strategy, not just
correlation.

Strategy (intentionally simple — this is a teaching backtest, not a
production alpha engine):

    1. Compute rolling OFI over a window of W snapshots.
    2. Standardise to z-score using a trailing mean / std.
    3. If z-score > +entry_z  -> go LONG 1 unit at next mid
       If z-score < -entry_z -> go SHORT 1 unit at next mid
       Otherwise             -> flat
    4. Hold for `hold` snapshots, then close at the prevailing mid.
    5. P&L per trade = sign * (mid_at_close - mid_at_open) - round-trip cost

We charge a configurable round-trip cost (default 1 bp) to keep the
backtest honest — real execution pays at least the spread.

This is a one-position-at-a-time toy. It is NOT meant to be a real
alpha — its job is to make the OFI -> P&L relationship visible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class BacktestConfig:
    """Parameters for the OFI backtest."""
    roll_window: int = 50         # rolling window for OFI smoothing
    zscore_window: int = 200      # trailing window for z-score normalisation
    entry_z: float = 1.0          # |z| threshold to enter a trade
    hold: int = 5                 # holding period in snapshots
    cost_bps: float = 1.0         # round-trip cost in basis points
    side: str = "both"            # "long_only", "short_only", or "both"


def ofi_backtest(
    ofi_df: pd.DataFrame,
    config: Optional[BacktestConfig] = None,
) -> pd.DataFrame:
    """Run the OFI signal-to-strategy backtest.

    Parameters
    ----------
    ofi_df : DataFrame returned by `orderbook.ofi.compute_ofi`.
        Must contain columns: timestamp, ofi, mid, mid_ret
    config : BacktestConfig (defaults used if None)

    Returns
    -------
    DataFrame with one row per snapshot:
        timestamp, ofi_roll, z, position, mid, trade_pnl, cumulative_pnl
    Plus a `stats` dict accessible via `df.attrs`:
        n_trades, hit_rate, mean_pnl_bps, sharpe, cumulative_pnl_bps
    """
    cfg = config or BacktestConfig()
    df = ofi_df[["timestamp", "ofi", "mid", "mid_ret"]].copy().reset_index(drop=True)

    # 1. Rolling OFI smoothing
    df["ofi_roll"] = df["ofi"].rolling(cfg.roll_window, min_periods=1).sum()

    # 2. Trailing z-score
    roll_mean = df["ofi_roll"].rolling(cfg.zscore_window, min_periods=20).mean()
    roll_std = df["ofi_roll"].rolling(cfg.zscore_window, min_periods=20).std()
    df["z"] = (df["ofi_roll"] - roll_mean) / roll_std.replace(0, np.nan)
    df["z"] = df["z"].fillna(0.0)

    # 3. Generate target position at each timestamp
    # +1 = long, -1 = short, 0 = flat
    target = np.zeros(len(df), dtype=int)
    target[df["z"] > cfg.entry_z] = 1
    target[df["z"] < -cfg.entry_z] = -1
    if cfg.side == "long_only":
        target = np.where(target == -1, 0, target)
    elif cfg.side == "short_only":
        target = np.where(target == 1, 0, target)

    # 4. Enforce holding period: once we enter, hold for `hold` snapshots
    # and ignore new signals during the hold.
    position = np.zeros(len(df), dtype=int)
    entry_idx = -cfg.hold  # ensure first trade can happen at idx=0
    for i in range(len(df)):
        if i - entry_idx >= cfg.hold and target[i] != 0:
            # Enter a new position
            position[i] = target[i]
            entry_idx = i
        elif i - entry_idx < cfg.hold and entry_idx >= 0:
            # Still in a trade — keep the position
            position[i] = position[entry_idx]
        # else: flat (no position)

    df["position"] = position

    # 5. P&L: position * next-snapshot return, minus round-trip cost on entry
    df["mid_ret_lead1"] = df["mid_ret"].shift(-1).fillna(0.0)
    df["trade_pnl_bps"] = df["position"] * df["mid_ret_lead1"] * 10_000.0

    # Charge cost on entry (position changes from 0 to non-zero, or sign flip)
    pos_prev = np.roll(df["position"].values, 1)
    pos_prev[0] = 0
    entry_mask = (df["position"].values != 0) & (df["position"].values != pos_prev)
    df.loc[entry_mask, "trade_pnl_bps"] -= cfg.cost_bps

    # Exit cost too (position goes from non-zero to 0, or sign flip on entry
    # already implies a round-trip so we don't double-charge)
    exit_mask = (pos_prev != 0) & (df["position"].values == 0)
    df.loc[exit_mask, "trade_pnl_bps"] -= cfg.cost_bps

    df["cumulative_pnl_bps"] = df["trade_pnl_bps"].cumsum()

    # 6. Stats
    trades = df[entry_mask].copy()
    if len(trades) > 0:
        trade_returns = []
        for idx in trades.index:
            end = min(idx + cfg.hold, len(df) - 1)
            entry_mid = df.loc[idx, "mid"]
            exit_mid = df.loc[end, "mid"]
            sign = df.loc[idx, "position"]
            pnl_bps = sign * (exit_mid - entry_mid) / entry_mid * 10_000.0
            trade_returns.append(pnl_bps - 2 * cfg.cost_bps)  # entry + exit cost
        trade_returns = np.array(trade_returns)
        hit_rate = float((trade_returns > 0).mean())
        mean_pnl = float(trade_returns.mean())
        std_pnl = float(trade_returns.std())
        sharpe = float(mean_pnl / std_pnl * np.sqrt(252)) if std_pnl > 0 else 0.0
    else:
        hit_rate = 0.0
        mean_pnl = 0.0
        sharpe = 0.0

    stats = {
        "n_trades": int(len(trades)),
        "hit_rate": hit_rate,
        "mean_trade_pnl_bps": mean_pnl,
        "sharpe_annualized": sharpe,
        "cumulative_pnl_bps": float(df["cumulative_pnl_bps"].iloc[-1]),
        "cost_bps": cfg.cost_bps,
    }
    df.attrs["stats"] = stats
    return df


def print_backtest_summary(bt_df: pd.DataFrame) -> None:
    """Pretty-print the backtest stats."""
    s = bt_df.attrs["stats"]
    sep = "=" * 60
    print(f"\n{sep}\nOFI BACKTEST SUMMARY\n{sep}")
    print(f"Trades              : {s['n_trades']}")
    print(f"Hit rate            : {s['hit_rate']:.1%}")
    print(f"Mean trade P&L      : {s['mean_trade_pnl_bps']:+.2f} bps")
    print(f"Sharpe (annualized) : {s['sharpe_annualized']:+.2f}")
    print(f"Cumulative P&L      : {s['cumulative_pnl_bps']:+.2f} bps")
    print(f"Round-trip cost     : {s['cost_bps']:.2f} bps")
    print(sep + "\n")
