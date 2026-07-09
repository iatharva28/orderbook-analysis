"""Order Book Analysis and Liquidity Modeling package.

Modules
-------
data    : Synthetic Level-2 generator + CSV loader.
metrics : Bid-ask spread, depth-at-top-N, cumulative depth curve, liquidity heatmap.
ofi     : Order Flow Imbalance (queue deltas, rolling OFI, return correlation).
impact  : Walk-the-book slippage simulation + square-root price impact model.
"""

from .data import BookParams, generate_synthetic_l2, load_l2_csv
from .metrics import (
    bid_ask_spread,
    depth_at_top_n,
    mean_size_per_level,
    cumulative_depth_curve,
    liquidity_heatmap,
)
from .ofi import compute_ofi
from .impact import walk_the_book_slippage, square_root_impact
from .signal_backtest import ofi_backtest

__all__ = [
    "BookParams",
    "generate_synthetic_l2",
    "load_l2_csv",
    "bid_ask_spread",
    "depth_at_top_n",
    "mean_size_per_level",
    "cumulative_depth_curve",
    "liquidity_heatmap",
    "compute_ofi",
    "walk_the_book_slippage",
    "square_root_impact",
    "ofi_backtest",
]

__version__ = "0.1.0"
