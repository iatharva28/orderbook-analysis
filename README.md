# Order Book Analysis & Liquidity Modeling

A small Python package that parses high-frequency **Level-2 order book**
data and quantifies real-time liquidity — bid-ask spreads, depth profiles,
liquidity heatmaps — plus **Order Flow Imbalance (OFI)** as a
short-horizon alpha signal, a **signal-to-strategy backtest**, and
**slippage / price-impact** modeling.

Built with **NumPy + Pandas + Matplotlib**. Ships with:
- A **CLI** (`main.py`) for batch analysis
- A **Jupyter notebook** (`demo_notebook.ipynb`) for interactive walkthrough
- A **Binance WebSocket loader** (`orderbook/binance_loader.py`) for capturing real L2 data

> **New to order book jargon?** Open `GLOSSARY.md` — every term used in
> this project explained in plain English (Level-2, spread, depth, OFI,
> slippage, square-root impact, backtest, Sharpe, etc.).
>
> **Prepping for an interview (Akuna, Jane Street, Optiver, etc.)?**
> Open `CONCEPT.md` — every project term PLUS options, greeks, market
> making, volatility, and Black-Scholes, each with an "If interviewer
> asks" block showing how to answer in 30 seconds. Includes a Top 10
> interview questions cheat sheet at the end.

---

## What's in the box

```
orderbook_analysis/
├── README.md                  <- you are here
├── GLOSSARY.md                <- plain-English definitions of every term
├── requirements.txt           <- pip install -r requirements.txt
├── main.py                    <- CLI entry point
├── demo_notebook.ipynb        <- walkthrough notebook (already executed)
├── orderbook/                 <- the Python package
│   ├── __init__.py
│   ├── data.py                <- synthetic L2 generator + CSV loader (realistic OFI mode)
│   ├── metrics.py             <- spread, depth, cumulative depth, heatmap, imbalance
│   ├── ofi.py                 <- Order Flow Imbalance
│   ├── impact.py              <- walk-the-book slippage + sqrt-impact model
│   ├── signal_backtest.py     <- OFI -> long/short -> P&L backtest
│   └── binance_loader.py      <- captures real L2 from Binance WebSocket
└── output/                    <- generated charts (PNG) + optional CSVs
    ├── 01_spread_timeseries.png
    ├── 02_depth_profile.png
    ├── 03_liquidity_heatmap.png
    ├── 04_book_imbalance.png
    ├── 05_ofi.png
    ├── 06_slippage_curve.png
    └── 07_ofi_backtest.png
```

---

## Quick start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the CLI on synthetic data (no input files needed)
python main.py

# 3. Or open the notebook
jupyter notebook demo_notebook.ipynb
```

That's it. The CLI prints summary stats to the terminal and writes six
charts into `output/`. The notebook walks through the same code with
narrative markdown and inline plots.

---

## What each step does (plain English)

### Step 1 — Get the data (`orderbook/data.py`)

We need a stream of order book snapshots. Each snapshot is a list of
price levels on the bid and ask side, with the size available at each
level. The generator builds a stream of 5,000 such snapshots by default.

How the synthetic data is built:

- **Mid price** follows a random walk. Each snapshot the log-return is
  drawn from a normal distribution with mean 0 and std `vol_per_tick`.
- **Spread** is sticky, an integer multiple of the tick size, drawn
  from a Poisson distribution (so it's usually 1–3 ticks).
- **Best bid / ask** = mid ± half the spread.
- **Levels deeper** are placed at fixed tick increments away from the
  best price.
- **Size at each level** decays exponentially with depth (top of book
  is fullest, deeper levels are thinner), with multiplicative
  log-normal noise so the shape varies snapshot-to-snapshot.

If you have your own L2 data, skip the generator and call
`load_l2_csv('your_file.csv')`. The CSV must have columns:
`timestamp, level, bid_price, bid_qty, ask_price, ask_qty`.

### Step 2 — Bid-ask spread (`bid_ask_spread` in `metrics.py`)

For each snapshot, take the best bid and best ask (level 0) and compute:

- `spread_abs` = best_ask − best_bid (price units)
- `spread_ticks` = spread_abs / tick_size (integer multiple of tick)
- `spread_bps` = spread_abs / mid × 10,000 (basis points, asset-normalised)

Output: one row per snapshot. We plot the mid price on top, the spread
(in bps) on the bottom. A tight, stable spread = liquid market.

### Step 3 — Depth profile & cumulative depth curve (`depth_at_top_n`, `cumulative_depth_curve`)

Spread only describes the *top* of the book. Depth describes how much
size sits at each level.

- `depth_at_top_n(df, n=5)`: total size in the top 5 levels, per side,
  per snapshot. Useful as a single "thick vs thin book" indicator.
- `cumulative_depth_curve(df)`: time-averaged size at each level, then
  a running sum. Answers: "if I sweep levels 0..L, how much can I fill?"

We plot two charts side-by-side:
- Average size at each level (bid vs ask bars)
- Cumulative depth curve (running total)

A convex cumulative curve = healthy book (most liquidity near the top).

### Step 4 — Liquidity heatmap (`liquidity_heatmap`)

Instead of averaging across time, the heatmap keeps *both* dimensions:
rows = time bins, columns = depth levels, cell colour = mean size in
that bucket. Best chart for spotting liquidity regimes — bright bands
mean deep liquidity, dark bands mean thin liquidity.

### Step 5 — Book imbalance (`book_imbalance`)

Top-N imbalance = `(bid_depth − ask_depth) / (bid_depth + ask_depth)`.
Range: −1 (all ask) to +1 (all bid). A free directional pressure proxy.

### Step 6 — Order Flow Imbalance (`compute_ofi` in `ofi.py`)

OFI is a rigorously defined version of imbalance. Instead of looking at
*levels*, it looks at *queue changes* between consecutive snapshots:

```
OFI(t) = Σ over top-L levels of [ ΔBidQty(t) − ΔAskQty(t) ]
```

When the bid queue grows and the ask queue shrinks, buyers are adding
aggressiveness / sellers pulling it → upward pressure. Empirically, OFI
is positively correlated with short-horizon mid returns (typically
0.2–0.5 on real liquid assets). We compute `corr(OFI_t, mid_ret_{t+1})`
— the *lagged* correlation, so we measure predictive content, not
contemporaneous.

**Realistic OFI mode (default).** The synthetic generator injects a
latent "pressure" AR(1) process that drives BOTH queue changes AND the
next snapshot's mid return, so the synthetic OFI correlation is
non-zero (~0.16 on default params) — close to what real data shows.
This lets you validate the entire signal-to-strategy pipeline without
needing real data. Set `realistic_ofi=False` to get the clean null
case (~0 correlation) for sanity-checking.

### Step 7 — Signal-to-strategy backtest (`ofi_backtest` in `signal_backtest.py`)

Correlation is a statistic; P&L is a verdict. This step turns OFI into a
toy trading strategy:

1. Smooth OFI with a 50-snapshot rolling sum.
2. Convert to a trailing z-score (200-snapshot window).
3. If z > +1 → go LONG 1 unit at next mid.
   If z < −1 → go SHORT 1 unit at next mid.
4. Hold for 5 snapshots, then close at the prevailing mid.
5. Charge 1 bp round-trip cost (entry + exit).

Reports: trades, hit rate, mean P&L per trade, annualized Sharpe,
cumulative P&L. The chart shows the z-score, position, and cumulative
P&L over time.

> The Sharpe looks high (~10+) on synthetic data because the simulator
> is too clean — no microstructure noise, no adverse selection, no
> queue priority modelling. On real data it will be much more modest
> (and may turn negative after costs), which is exactly what real
> microstructure alpha looks like.

### Step 8 — Slippage & price impact (`walk_the_book_slippage`, `square_root_impact` in `impact.py`)

Two complementary views of "how much does it cost to trade size Q?":

1. **Walk-the-book (empirical)**: For each snapshot, simulate a
   marketable buy order of size Q. Walk through ask levels, consume
   size at each price, record the volume-weighted average fill price.
   Slippage = (avg_fill − mid) / mid, in bps. We sweep Q from 0.1× to
   20× the average top-of-book size.
2. **Square-root model (theoretical)**: A robust empirical regularity
   `impact ≈ σ × √(Q / ADV)` where σ is volatility and ADV is average
   daily volume. We estimate σ from mid returns and ADV from mean
   per-snapshot total depth (a proxy).

We plot both on the same log-x chart. They should agree qualitatively
(both grow roughly with √Q).

### Step 9 — Real data from Binance (`orderbook/binance_loader.py`)

Ready-to-run WebSocket loader that captures the free public
`btcusdt@depth20@100ms` stream and writes it into the same long-format
CSV our pipeline expects. See "Capturing real data from Binance"
section below.

---

## Capturing real data from Binance

The synthetic generator demonstrates the *machinery* of microstructure
analysis. To validate on real data, we ship a Binance WebSocket loader.

```bash
# 1. Install the WebSocket client (not in requirements.txt by default)
pip install websocket-client

# 2. Capture 60 seconds of BTC/USDT L2 data
python -m orderbook.binance_loader \
    --symbol btcusdt --levels 20 --seconds 60 \
    --out real_l2_btcusdt.csv

# 3. Run the full analysis on the real data
python main.py --csv real_l2_btcusdt.csv --tick 0.01 --out output/real
```

On real data you should see `corr(OFI_t, mid_ret_{t+1})` in the
**0.2–0.5 range** — the empirical regularity documented in Cont et al.
(2014). The backtest P&L will be much more modest (and may turn
negative after costs), which is exactly what real microstructure alpha
looks like.

---

## CLI usage

```bash
# Default (synthetic data with realistic OFI)
python main.py

# Crypto-like book
python main.py --ticks 10000 --levels 50 --tick 0.01 \
               --init-mid 30000 --vol 5e-4 --base-qty 0.5 \
               --out output/crypto

# Load real CSV (e.g. captured from Binance)
python main.py --csv real_l2_btcusdt.csv --tick 0.01 --out output/real --save-csv

# Disable realistic OFI mode (clean null case for sanity-checking)
python main.py --no-realistic-ofi

# Skip sections
python main.py --no-ofi --no-impact --no-backtest
```

All flags:

| Flag          | Default  | Meaning                                       |
|---------------|----------|-----------------------------------------------|
| `--csv`       | (none)   | Load L2 CSV instead of generating synthetic   |
| `--ticks`     | 5,000    | Number of snapshots (synthetic only)          |
| `--levels`    | 20       | Depth levels per side (synthetic only)        |
| `--tick`      | 0.01     | Tick size (also used for spread-in-ticks)     |
| `--init-mid`  | 100.0    | Initial mid price (synthetic only)            |
| `--vol`       | 2e-3     | Per-snapshot mid log-return volatility        |
| `--base-qty`  | 1.0      | Base size at top of book (synthetic only)     |
| `--qty-decay` | 0.85     | Exponential size decay per level              |
| `--seed`      | 42       | RNG seed                                      |
| `--no-realistic-ofi` | (flag) | Disable realistic OFI mode (null case)  |
| `--out`       | `output` | Output directory                              |
| `--no-ofi`    | (flag)   | Skip OFI analysis                             |
| `--no-impact` | (flag)   | Skip slippage / impact analysis               |
| `--no-backtest` | (flag) | Skip signal-to-strategy backtest              |
| `--save-csv`  | (flag)   | Dump computed metrics to CSV in `--out`       |

---

## Asset class presets

`BookParams` docstring contains ready-to-use presets. Quick reference:

| Asset         | `tick_size` | `init_mid` | `vol_per_tick` | `n_levels` | `base_qty` |
|---------------|-------------|------------|----------------|------------|------------|
| Crypto BTC    | 0.01        | 30,000     | 5e-4           | 50         | 0.5        |
| US equity     | 0.01        | 190        | 2e-4           | 20         | 100.0      |
| E-mini S&P    | 0.25        | 5,400      | 3e-4           | 10         | 5.0        |
| Generic       | 0.01        | 100        | 2e-3           | 20         | 1.0        |

---

## Using your own L2 data

1. Reshape your feed into long format with one row per
   `(timestamp, level)` and columns
   `bid_price, bid_qty, ask_price, ask_qty`.
2. Save as CSV.
3. Run:
   ```bash
   python main.py --csv your_file.csv --tick <your_tick> --out output/real
   ```
4. Or in Python:
   ```python
   from orderbook.data import load_l2_csv
   df = load_l2_csv('your_file.csv')
   # ... then call any metric on df
   ```

---

## File-by-file map

| File                       | What it does                                              |
|----------------------------|-----------------------------------------------------------|
| `orderbook/data.py`        | Synthetic L2 generator (with realistic OFI mode) + CSV loader + `BookParams` |
| `orderbook/metrics.py`     | `bid_ask_spread`, `depth_at_top_n`, `mean_size_per_level`, `cumulative_depth_curve`, `liquidity_heatmap`, `book_imbalance` |
| `orderbook/ofi.py`         | `compute_ofi` (queue deltas + rolling + corr) + summary  |
| `orderbook/impact.py`      | `walk_the_book_slippage` + `square_root_impact`           |
| `orderbook/signal_backtest.py` | `ofi_backtest` (OFI → z-score → long/short → P&L)     |
| `orderbook/binance_loader.py` | Live L2 capture from Binance WebSocket → CSV           |
| `main.py`                  | CLI entry: argparse, runs all metrics + backtest, saves charts |
| `demo_notebook.ipynb`      | Walkthrough notebook (already executed, with inline PNGs) |

---

## Dependencies

- Python 3.9+
- numpy, pandas, matplotlib
- jupyter / nbconvert / ipykernel (only needed to re-run the notebook)
- websocket-client (only needed for live Binance capture)

Install core deps with `pip install -r requirements.txt`.
For Binance capture, additionally: `pip install websocket-client`.

---

## References

- Cont, R., Kukanov, A., & Stoikov, S. (2014). *The price impact of order
  book imbalance.* SSRN.
- Almgren, R., Thum, C., Hauptmann, E., & Li, H. (2005). *Direct
  estimation of equity market impact.* Risk.
- Gatheral, J. (2010). *No-dynamic-arbitrage and market impact.*
  Quantitative Finance.
- Bouchaud, J.-P., Farmer, J. D., & Lillo, F. (2009). *How markets slowly
  digest changes in supply and demand.* Handbook of Financial Markets.
