"""CLI entry point for the Order Book Analysis package.

Examples
--------
# Default run (synthetic data, generic params):
    python main.py

# Custom params:
    python main.py --ticks 20000 --levels 50 --tick 0.01 --init-mid 30000 \
                   --vol 5e-4 --base-qty 0.5 --out output/crypto

# Load real L2 CSV instead:
    python main.py --csv /path/to/l2.csv --tick 0.01 --out output/real

# Skip OFI/slippage (spread + depth only):
    python main.py --no-ofi --no-impact
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Matplotlib (Agg backend -> no display needed)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# Resolve package import whether run as `python main.py` or `python -m main`
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from orderbook.data import BookParams, generate_synthetic_l2, load_l2_csv  # noqa: E402
from orderbook.metrics import (  # noqa: E402
    bid_ask_spread,
    depth_at_top_n,
    mean_size_per_level,
    cumulative_depth_curve,
    liquidity_heatmap,
    book_imbalance,
)
from orderbook.ofi import compute_ofi, ofi_summary_stats  # noqa: E402
from orderbook.impact import walk_the_book_slippage, square_root_impact  # noqa: E402
from orderbook.signal_backtest import ofi_backtest  # noqa: E402


# ----- Matplotlib font hygiene -------------------------------------------------
try:
    fm.fontManager.addfont("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
except Exception:
    pass
plt.rcParams["font.sans-serif"] = ["DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 110


# ----- Plot helpers ------------------------------------------------------------
def plot_spread(spread_df: pd.DataFrame, out_path: str) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(12, 6), constrained_layout=True, sharex=True)
    axes[0].plot(spread_df["timestamp"], spread_df["mid"], color="steelblue", lw=0.6)
    axes[0].set_title("Mid price")
    axes[0].set_ylabel("Price")
    axes[0].grid(alpha=0.3)

    axes[1].plot(spread_df["timestamp"], spread_df["spread_bps"],
                 color="darkorange", lw=0.5)
    mean_bps = spread_df["spread_bps"].mean()
    axes[1].axhline(mean_bps, color="red", ls="--", lw=0.8,
                    label=f"mean = {mean_bps:.2f} bps")
    axes[1].set_title("Bid-ask spread (bps)")
    axes[1].set_ylabel("bps")
    axes[1].set_xlabel("Snapshot")
    axes[1].legend()
    axes[1].grid(alpha=0.3)
    plt.savefig(out_path, dpi=130)
    plt.close(fig)


def plot_depth_profile(depth_df: pd.DataFrame, cum_df: pd.DataFrame, out_path: str) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), constrained_layout=True)

    axes[0].bar(depth_df["level"] - 0.2, depth_df["bid_qty"], width=0.4,
                color="seagreen", label="Bid qty (mean)")
    axes[0].bar(depth_df["level"] + 0.2, depth_df["ask_qty"], width=0.4,
                color="firebrick", label="Ask qty (mean)")
    axes[0].set_title("Average size at each level")
    axes[0].set_xlabel("Level (0 = best)")
    axes[0].set_ylabel("Mean size")
    axes[0].legend()
    axes[0].grid(alpha=0.3, axis="y")

    axes[1].plot(cum_df["level"], cum_df["cum_bid"], color="seagreen",
                 marker="o", ms=3, label="Cumulative bid")
    axes[1].plot(cum_df["level"], cum_df["cum_ask"], color="firebrick",
                 marker="o", ms=3, label="Cumulative ask")
    axes[1].plot(cum_df["level"], cum_df["cum_total"], color="steelblue",
                 marker="s", ms=3, label="Cumulative total")
    axes[1].set_title("Cumulative depth curve")
    axes[1].set_xlabel("Level")
    axes[1].set_ylabel("Cumulative size")
    axes[1].legend()
    axes[1].grid(alpha=0.3)
    plt.savefig(out_path, dpi=130)
    plt.close(fig)


def plot_heatmap(heat: pd.DataFrame, out_path: str) -> None:
    fig, ax = plt.subplots(figsize=(12, 6), constrained_layout=True)
    im = ax.imshow(heat.values, aspect="auto", origin="lower",
                   cmap="viridis", interpolation="nearest")
    ax.set_title("Liquidity heatmap: mean size per (time-bin, level)")
    ax.set_xlabel("Level (0 = best)")
    ax.set_ylabel("Time bin")
    ax.set_xticks(np.arange(0, heat.shape[1], max(1, heat.shape[1] // 10)))
    ax.set_yticks(np.linspace(0, heat.shape[0] - 1, 6).astype(int))
    fig.colorbar(im, ax=ax, label="Mean size (bid + ask)")
    plt.savefig(out_path, dpi=130)
    plt.close(fig)


def plot_imbalance(imb_df: pd.DataFrame, out_path: str) -> None:
    fig, ax = plt.subplots(figsize=(12, 4), constrained_layout=True)
    ax.plot(imb_df["timestamp"], imb_df["imbalance"], color="purple", lw=0.5)
    ax.axhline(0, color="black", lw=0.8)
    ax.set_title("Top-5 book imbalance: (bid - ask) / (bid + ask)")
    ax.set_xlabel("Snapshot")
    ax.set_ylabel("Imbalance")
    ax.set_ylim(-1.05, 1.05)
    ax.grid(alpha=0.3)
    plt.savefig(out_path, dpi=130)
    plt.close(fig)


def plot_ofi(ofi_df: pd.DataFrame, corr: float, out_path: str) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), constrained_layout=True, sharex=True)
    axes[0].plot(ofi_df["timestamp"], ofi_df["ofi_roll_50"],
                 color="darkcyan", lw=0.6)
    axes[0].axhline(0, color="black", lw=0.8)
    axes[0].set_title(f"Rolling OFI (window=50)  |  corr(OFI_t, mid_ret_{{t+1}}) = {corr:+.3f}")
    axes[0].set_ylabel("OFI (50-snap sum)")
    axes[0].grid(alpha=0.3)

    axes[1].plot(ofi_df["timestamp"], ofi_df["mid"], color="steelblue", lw=0.6)
    axes[1].set_title("Mid price")
    axes[1].set_ylabel("Price")
    axes[1].set_xlabel("Snapshot")
    axes[1].grid(alpha=0.3)
    plt.savefig(out_path, dpi=130)
    plt.close(fig)


def plot_slippage(slip_df: pd.DataFrame, sqrt_df: pd.DataFrame, out_path: str) -> None:
    fig, ax = plt.subplots(figsize=(10, 6), constrained_layout=True)
    ax.plot(slip_df["order_size"], slip_df["avg_slippage_bps"],
            "o-", color="darkorange", label="Walk-the-book (empirical avg)")
    ax.fill_between(
        slip_df["order_size"],
        slip_df["p50_slippage_bps"],
        slip_df["p95_slippage_bps"],
        color="darkorange", alpha=0.2, label="p50–p95 band",
    )
    if not sqrt_df.empty:
        ax.plot(sqrt_df["order_size"], sqrt_df["impact_bps"],
                "s--", color="steelblue", label="Square-root model")
    ax.set_xlabel("Order size (units of qty)")
    ax.set_ylabel("Slippage / Impact (bps)")
    ax.set_title("Slippage vs order size")
    ax.set_xscale("log")
    ax.legend()
    ax.grid(alpha=0.3, which="both")
    plt.savefig(out_path, dpi=130)
    plt.close(fig)


def plot_backtest(bt_df: pd.DataFrame, out_path: str) -> None:
    """Plot OFI signal + position + cumulative P&L."""
    fig, axes = plt.subplots(3, 1, figsize=(12, 9), constrained_layout=True,
                             sharex=True,
                             gridspec_kw={"height_ratios": [2, 1, 2]})

    axes[0].plot(bt_df["timestamp"], bt_df["z"], color="darkcyan", lw=0.5)
    axes[0].axhline(1.0, color="red", ls="--", lw=0.7, alpha=0.6, label="+1 z (long entry)")
    axes[0].axhline(-1.0, color="blue", ls="--", lw=0.7, alpha=0.6, label="-1 z (short entry)")
    axes[0].axhline(0, color="black", lw=0.7)
    axes[0].set_title("OFI z-score")
    axes[0].set_ylabel("z-score")
    axes[0].legend(loc="upper right", fontsize=8)
    axes[0].grid(alpha=0.3)

    axes[1].fill_between(bt_df["timestamp"], bt_df["position"], 0,
                         where=bt_df["position"] > 0, color="seagreen",
                         alpha=0.6, label="Long")
    axes[1].fill_between(bt_df["timestamp"], bt_df["position"], 0,
                         where=bt_df["position"] < 0, color="firebrick",
                         alpha=0.6, label="Short")
    axes[1].set_title("Position")
    axes[1].set_ylabel("Position")
    axes[1].set_ylim(-1.5, 1.5)
    axes[1].legend(loc="upper right", fontsize=8)
    axes[1].grid(alpha=0.3)

    axes[2].plot(bt_df["timestamp"], bt_df["cumulative_pnl_bps"],
                 color="darkorange", lw=1.0)
    axes[2].axhline(0, color="black", lw=0.7)
    stats = bt_df.attrs.get("stats", {})
    n_trades = stats.get("n_trades", 0)
    hit = stats.get("hit_rate", 0)
    axes[2].set_title(f"Cumulative P&L  |  trades={n_trades}  hit rate={hit:.1%}")
    axes[2].set_ylabel("P&L (bps)")
    axes[2].set_xlabel("Snapshot")
    axes[2].grid(alpha=0.3)
    plt.savefig(out_path, dpi=130)
    plt.close(fig)


# ----- Summary printer --------------------------------------------------------
def print_summary(spread_df, depth_top, cum_df, ofi_df=None, corr=None,
                  slip_df=None, sqrt_df=None) -> None:
    sep = "=" * 70
    print(f"\n{sep}\nORDER BOOK ANALYSIS — SUMMARY\n{sep}")
    print(f"Snapshots analyzed      : {len(spread_df):,}")
    print(f"Mid price (last)        : {spread_df['mid'].iloc[-1]:.4f}")
    print(f"Mid price range         : [{spread_df['mid'].min():.4f}, "
          f"{spread_df['mid'].max():.4f}]")
    print(f"Spread (mean, bps)      : {spread_df['spread_bps'].mean():.3f}")
    print(f"Spread (median, bps)    : {spread_df['spread_bps'].median():.3f}")
    print(f"Spread (p95, bps)       : {spread_df['spread_bps'].quantile(0.95):.3f}")
    print(f"Top-5 depth (mean)      : bid={depth_top['bid_depth'].mean():.2f}, "
          f"ask={depth_top['ask_depth'].mean():.2f}")
    print(f"Cumulative depth @L10   : {cum_df['cum_total'].iloc[10] if len(cum_df) > 10 else cum_df['cum_total'].iloc[-1]:.2f}")

    if ofi_df is not None and corr is not None:
        print(f"\nOFI mean / std          : {ofi_df['ofi'].mean():.3f} / {ofi_df['ofi'].std():.3f}")
        print(f"OFI -> mid_ret(t+1) corr: {corr:+.4f}")

    if slip_df is not None and not slip_df.empty:
        print("\nSlippage (walk-the-book, buy side):")
        print(slip_df.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    if sqrt_df is not None and not sqrt_df.empty:
        print("\nSquare-root impact model:")
        print(sqrt_df.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    print(sep + "\n")


# ----- Main -------------------------------------------------------------------
def parse_args():
    p = argparse.ArgumentParser(
        description="Order Book Analysis & Liquidity Modeling",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    src = p.add_argument_group("data source")
    src.add_argument("--csv", type=str, default=None,
                     help="Path to long-format L2 CSV. If omitted, synthetic data is generated.")
    src.add_argument("--ticks", type=int, default=5_000,
                     help="Number of snapshots (synthetic only)")
    src.add_argument("--levels", type=int, default=20,
                     help="Depth levels per side (synthetic only)")
    src.add_argument("--tick", type=float, default=0.01,
                     help="Tick size (used for spread-in-ticks metric)")
    src.add_argument("--init-mid", type=float, default=100.0,
                     help="Initial mid price (synthetic only)")
    src.add_argument("--vol", type=float, default=2e-3,
                     help="Per-snapshot mid log-return volatility (synthetic only)")
    src.add_argument("--base-qty", type=float, default=1.0,
                     help="Base size at top of book (synthetic only)")
    src.add_argument("--qty-decay", type=float, default=0.85,
                     help="Exponential size decay per level (synthetic only)")
    src.add_argument("--seed", type=int, default=42)
    src.add_argument("--no-realistic-ofi", action="store_true",
                     help="Disable realistic OFI mode (queue changes independent of returns -> OFI corr ~ 0)")

    p.add_argument("--out", type=str, default="output",
                   help="Output directory for charts + CSVs")
    p.add_argument("--no-ofi", action="store_true", help="Skip OFI analysis")
    p.add_argument("--no-impact", action="store_true", help="Skip slippage / impact analysis")
    p.add_argument("--no-backtest", action="store_true",
                   help="Skip signal-to-strategy backtest")
    p.add_argument("--save-csv", action="store_true",
                   help="Also dump computed metrics to CSV in --out")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- Load / generate data ---
    if args.csv:
        print(f"Loading L2 CSV from {args.csv} ...")
        df = load_l2_csv(args.csv)
    else:
        print("Generating synthetic L2 data ...")
        params = BookParams(
            n_ticks=args.ticks,
            n_levels=args.levels,
            tick_size=args.tick,
            init_mid=args.init_mid,
            vol_per_tick=args.vol,
            base_qty=args.base_qty,
            qty_decay=args.qty_decay,
            seed=args.seed,
            realistic_ofi=not args.no_realistic_ofi,
        )
        print(f"  realistic_ofi = {params.realistic_ofi} "
              f"({'OFI will have predictive content' if params.realistic_ofi else 'OFI will be uncorrelated with returns (null case)'})")
        df = generate_synthetic_l2(params)
    print(f"  -> {len(df):,} rows, {df['timestamp'].nunique():,} snapshots, "
          f"{df['level'].nunique()} levels per side")

    # --- Metrics ---
    spread_df = bid_ask_spread(df, tick_size=args.tick)
    depth_top = depth_at_top_n(df, n=5)
    mean_size_df = mean_size_per_level(df)         # per-level mean sizes (for bar chart)
    cum_df = cumulative_depth_curve(df)            # adds cumulative sums (for line chart)
    heat = liquidity_heatmap(df, n_levels=min(20, df["level"].nunique()), n_bins=50)
    imb_df = book_imbalance(df, n=5)

    # --- Plots (primary) ---
    plot_spread(spread_df, str(out_dir / "01_spread_timeseries.png"))
    plot_depth_profile(mean_size_df, cum_df, str(out_dir / "02_depth_profile.png"))
    plot_heatmap(heat, str(out_dir / "03_liquidity_heatmap.png"))
    plot_imbalance(imb_df, str(out_dir / "04_book_imbalance.png"))

    ofi_df, corr = (None, None)
    if not args.no_ofi:
        ofi_df, corr = compute_ofi(df, n_levels=10)
        plot_ofi(ofi_df, corr, str(out_dir / "05_ofi.png"))

    slip_df, sqrt_df = None, None
    if not args.no_impact:
        # Order sizes spanning ~0.1x to ~10x top-of-book size
        top_qty = float(df[df["level"] == 0][["bid_qty", "ask_qty"]].mean().mean())
        sizes = [top_qty * f for f in (0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0)]
        slip_df = walk_the_book_slippage(df, sizes, side="buy", max_snapshots=500)
        sqrt_df = square_root_impact(df, sizes)
        plot_slippage(slip_df, sqrt_df, str(out_dir / "06_slippage_curve.png"))

    # --- Signal-to-strategy backtest ---
    bt_df = None
    if not args.no_backtest and ofi_df is not None:
        from orderbook.signal_backtest import ofi_backtest, BacktestConfig, print_backtest_summary
        bt_df = ofi_backtest(ofi_df, BacktestConfig())
        plot_backtest(bt_df, str(out_dir / "07_ofi_backtest.png"))
        print_backtest_summary(bt_df)

    # --- Summary ---
    print_summary(spread_df, depth_top, cum_df, ofi_df, corr, slip_df, sqrt_df)

    # --- Optional CSV dumps ---
    if args.save_csv:
        spread_df.to_csv(out_dir / "spread.csv", index=False)
        depth_top.to_csv(out_dir / "depth_top5.csv", index=False)
        cum_df.to_csv(out_dir / "cumulative_depth.csv", index=False)
        if ofi_df is not None:
            ofi_df.to_csv(out_dir / "ofi.csv", index=False)
        if slip_df is not None:
            slip_df.to_csv(out_dir / "slippage.csv", index=False)
        if bt_df is not None:
            bt_df.to_csv(out_dir / "backtest.csv", index=False)

    print(f"Charts + CSVs written to: {out_dir.resolve()}\n")


if __name__ == "__main__":
    main()
