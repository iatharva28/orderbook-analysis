"""Data layer: synthetic Level-2 order book generator + CSV loader.

A *Level-2* feed is a sequence of book snapshots. Each snapshot contains the
top-N price levels on both the bid and ask side, with the available size at
each level. Real exchanges (NASDAQ ITCH, Binance depth20, etc.) emit deltas;
here we model snapshots directly because they are the unit that downstream
microstructure metrics (spread, depth, OFI) operate on.

The synthetic generator builds books that share the *stylised facts* of real
limit-order books:
  * Mid-price follows a geometric random walk (log-returns ~ N(0, sigma)).
  * Spread is sticky, integer multiple of tick_size, ~ Poisson.
  * Size at each level decays exponentially with depth (typical "depth profile").
  * Sizes are perturbed with multiplicative log-normal noise.

The CSV loader accepts the same long-format schema the generator emits, so any
real L2 feed that is reshaped into (timestamp, level, bid_price, bid_qty,
ask_price, ask_qty) plugs in directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class BookParams:
    """Parameters for the synthetic Level-2 generator.

    Defaults are asset-agnostic. Override any field to mimic a specific asset:

    Examples
    --------
    Crypto (BTC/USDT, tick=0.01):
        BookParams(init_mid=30_000, tick_size=0.01, vol_per_tick=5e-4,
                   n_levels=50, base_qty=0.5)
    US equity (AAPL, tick=$0.01):
        BookParams(init_mid=190.0, tick_size=0.01, vol_per_tick=2e-4,
                   n_levels=20, base_qty=100.0)
    Futures (E-mini S&P, tick=0.25):
        BookParams(init_mid=5_400.0, tick_size=0.25, vol_per_tick=3e-4,
                   n_levels=10, base_qty=5.0)

    realistic_ofi
    -------------
    When True (default), a latent "pressure" process drives BOTH queue
    changes and the next snapshot's mid return. This makes OFI predictive
    of short-horizon returns — exactly the empirical regularity the
    Cont, Kukanov & Stoikov (2014) paper documents. Use this mode to
    demonstrate that the OFI signal works as advertised.

    When False, queue changes and mid returns are independent (the
    original textbook random-walk model). OFI correlation with returns
    will be ~0 by construction — useful as a null / control case.
    """

    n_ticks: int = 5_000          # number of book snapshots
    n_levels: int = 20            # depth levels per side
    tick_size: float = 0.01       # minimum price increment
    init_mid: float = 100.0       # initial mid price
    vol_per_tick: float = 2e-3    # mid-price log-return std dev per snapshot
    base_qty: float = 1.0         # base order size at top of book
    qty_decay: float = 0.85       # exponential decay of size by depth level
    qty_noise: float = 0.30       # multiplicative noise on size (sigma of log-normal)
    spread_ticks_mean: int = 2    # mean spread in ticks (Poisson)
    seed: int = 42

    # Realistic-OFI parameters (only used when realistic_ofi=True)
    realistic_ofi: bool = True    # inject OFI <-> return predictive content
    pressure_ar_coef: float = 0.85   # AR(1) persistence of latent pressure
    pressure_to_qty: float = 0.40    # how strongly pressure biases queue changes
    pressure_to_return: float = 0.50 # how strongly pressure drives next return
                                     # (relative to vol_per_tick)


def generate_synthetic_l2(params: Optional[BookParams] = None) -> pd.DataFrame:
    """Generate a synthetic Level-2 order book snapshot stream.

    Returns
    -------
    DataFrame with long-format columns:
        timestamp  : int, snapshot index (0..n_ticks-1)
        level      : int, 0..n_levels-1 (0 = best bid/ask)
        bid_price  : float
        bid_qty    : float
        ask_price  : float
        ask_qty    : float
        mid        : float, mid price at this snapshot (broadcast across levels)
        spread     : float, best_ask - best_bid (broadcast across levels)
    """
    p = params or BookParams()
    rng = np.random.default_rng(p.seed)

    # --- Latent pressure process (AR(1)) -------------------------------------
    # pressure(t) is a hidden signal representing net buy/sell interest.
    # In realistic_ofi mode it biases BOTH queue growth and the next return,
    # giving OFI predictive content for returns (Cont et al. 2014 regularity).
    pressure = np.zeros(p.n_ticks)
    for t in range(1, p.n_ticks):
        pressure[t] = (p.pressure_ar_coef * pressure[t - 1]
                       + rng.normal(0.0, 1.0))

    # --- Mid-price: geometric random walk (+ pressure feedback if realistic) --
    noise = rng.normal(0.0, p.vol_per_tick, p.n_ticks)
    if p.realistic_ofi:
        # Pressure at t-1 pushes the return at t (lagged impact)
        log_rets = noise + p.pressure_to_return * p.vol_per_tick * np.roll(pressure, 1)
        log_rets[0] = noise[0]  # no lag for first snapshot
    else:
        log_rets = noise
    mid = p.init_mid * np.exp(np.cumsum(log_rets))

    # --- Spread: integer ticks, sticky, ~ Poisson, min 1 ---
    raw_spread = rng.poisson(max(1, p.spread_ticks_mean), p.n_ticks)
    spread_ticks = np.maximum(1, raw_spread).astype(int)

    half_spread = spread_ticks * p.tick_size / 2.0
    best_bid = mid - half_spread
    best_ask = mid + half_spread

    # --- Build long-format frame ---
    # Vectorise across (snapshot, level) grid.
    ts_grid, lvl_grid = np.meshgrid(
        np.arange(p.n_ticks), np.arange(p.n_levels), indexing="ij"
    )

    # Level offsets in price (in tick_size units)
    lvl_offset = lvl_grid * p.tick_size

    bid_price = best_bid[:, None] - lvl_offset
    ask_price = best_ask[:, None] + lvl_offset

    # Size profile: base * decay^level, perturbed by log-normal noise
    size_base = p.base_qty * (p.qty_decay ** lvl_grid)
    bid_qty = size_base * np.exp(rng.normal(0.0, p.qty_noise, size=size_base.shape))
    ask_qty = size_base * np.exp(rng.normal(0.0, p.qty_noise, size=size_base.shape))

    # --- Inject pressure into queue changes (realistic OFI mode) -------------
    # When pressure(t) > 0, bias bid_qty up and ask_qty down at top levels.
    # This makes the lagged OFI signal actually correlate with the next return.
    if p.realistic_ofi:
        # Pressure affects primarily the top 5 levels (decays with depth)
        depth_weight = np.exp(-0.3 * lvl_grid)  # top-heavy
        bias = p.pressure_to_qty * pressure[:, None] * depth_weight
        bid_qty = bid_qty * np.exp(bias)
        ask_qty = ask_qty * np.exp(-bias)

    # Snap prices to tick grid (avoid float drift)
    bid_price = np.round(bid_price / p.tick_size) * p.tick_size
    ask_price = np.round(ask_price / p.tick_size) * p.tick_size

    df = pd.DataFrame({
        "timestamp": ts_grid.ravel(),
        "level": lvl_grid.ravel(),
        "bid_price": bid_price.ravel(),
        "bid_qty": bid_qty.ravel(),
        "ask_price": ask_price.ravel(),
        "ask_qty": ask_qty.ravel(),
    })

    # Attach snapshot-level columns (mid, spread) for downstream convenience
    snap = pd.DataFrame({
        "timestamp": np.arange(p.n_ticks),
        "mid": mid,
        "spread": best_ask - best_bid,
    })
    df = df.merge(snap, on="timestamp", how="left")
    return df


def load_l2_csv(path: str, **read_csv_kwargs) -> pd.DataFrame:
    """Load a long-format Level-2 CSV.

    Required columns:
        timestamp, level, bid_price, bid_qty, ask_price, ask_qty

    Optional (computed if missing):
        mid, spread

    Returns
    -------
    Same schema as `generate_synthetic_l2`.
    """
    df = pd.read_csv(path, **read_csv_kwargs)
    required = {"timestamp", "level", "bid_price", "bid_qty", "ask_price", "ask_qty"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"CSV at {path} is missing required columns: {sorted(missing)}. "
            f"Expected schema: {sorted(required)}"
        )

    if "mid" not in df.columns or "spread" not in df.columns:
        snap = df.groupby("timestamp").agg(
            best_bid=("bid_price", "first"),
            best_ask=("ask_price", "first"),
        )
        snap["mid"] = (snap["best_bid"] + snap["best_ask"]) / 2
        snap["spread"] = snap["best_ask"] - snap["best_bid"]
        df = df.drop(columns=[c for c in ("mid", "spread") if c in df.columns])
        df = df.merge(snap[["mid", "spread"]], on="timestamp", how="left")

    return df


def export_l2_csv(df: pd.DataFrame, path: str) -> None:
    """Write a long-format L2 DataFrame to CSV (round-trip with load_l2_csv)."""
    df.to_csv(path, index=False)
