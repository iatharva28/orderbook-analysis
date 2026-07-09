# Order Book Analysis & Liquidity Modeling

Python project that ingests Level-2 order book data and computes the usual
microstructure metrics — bid-ask spread, depth, cumulative depth, a
liquidity heatmap, and book imbalance. The main focus is **Order Flow
Imbalance (OFI)** as defined in Cont, Kukanov & Stoikov (2014), which I
use as a short-horizon alpha signal and turn into a simple long/short
backtest. There's also a walk-the-book slippage simulator and a
square-root impact model on the execution side.

Stack: NumPy, Pandas, Matplotlib. No external data required — a synthetic
L2 generator with a "realistic OFI" mode lets the signal-to-return
correlation show up without needing real data.

## Why this project

I wanted to actually implement the OFI formula from Cont et al. (2014)
rather than just read about it. Most resources stop at "OFI predicts
returns" — I wanted to see the correlation number, plot it, and run a
backtest to see if the signal translates into P&L (spoiler: yes on
synthetic data, more modestly on real data, which is what the literature
says).

## Files

```
orderbook_analysis/
├── main.py                    CLI entry point
├── demo_notebook.ipynb        walkthrough with inline plots
├── requirements.txt
├── orderbook/
│   ├── data.py                synthetic L2 generator + CSV loader
│   ├── metrics.py             spread, depth, heatmap, imbalance
│   ├── ofi.py                 OFI computation + return correlation
│   ├── impact.py              walk-the-book slippage + sqrt model
│   ├── signal_backtest.py     OFI -> z-score -> long/short -> P&L
│   └── binance_loader.py      optional: live capture from Binance WS
├── output/                    pre-generated PNG charts
└── GLOSSARY.md                plain-English term definitions
```

## Quick start

```bash
pip install -r requirements.txt
python main.py
```

That generates 7 charts in `output/` and prints summary stats to the
terminal. The notebook walks through the same code with commentary:

```bash
jupyter notebook demo_notebook.ipynb
```

## What it actually does

**1. Data.** The synthetic generator builds a stream of L2 snapshots. Mid
price is a geometric random walk, spread is Poisson in tick units, sizes
decay exponentially with depth and get log-normal noise. There's a
`realistic_ofi` flag (on by default) that adds a latent AR(1) pressure
process driving both queue changes and the next return — without it, OFI
correlation is ~0 by construction; with it, you get something close to
the empirical 0.2-0.5 range.

**2. Spread / depth / heatmap.** Standard descriptive metrics. Spread in
bps is the asset-normalized one I care about. The heatmap (time x level
grid of mean size) is the most useful single chart for spotting liquidity
regimes.

**3. OFI.** Implemented per Cont et al. (2014): sum of queue deltas at
the top L levels, then I check `corr(OFI(t), mid_ret(t+1))`. On default
synthetic params this comes out around +0.16. On real BTC/USDT from
Binance it's in the documented 0.2-0.5 range.

**4. Backtest.** Smoothed OFI -> trailing z-score -> long/short on
±1σ -> hold 5 snapshots -> 1 bp round-trip cost. On synthetic data the
Sharpe is inflated (~10+) because there's no adverse selection or
microstructure noise. On real data it's much more modest.

**5. Slippage & impact.** Walk-the-book VWAP simulation for marketable
orders, plus the square-root model `σ√(Q/ADV)` for comparison. They
track each other qualitatively, as expected.

## Using real data

The Binance loader is optional. If you want to validate on real data:

```bash
pip install websocket-client
python -m orderbook.binance_loader --symbol btcusdt --levels 20 --seconds 600 --out real_l2.csv
python main.py --csv real_l2.csv --tick 0.01 --out output/real
```

Or load any L2 CSV with columns `timestamp, level, bid_price, bid_qty,
ask_price, ask_qty` via `load_l2_csv()`.

## CLI flags

```
--csv PATH           load a CSV instead of generating synthetic data
--ticks N            number of snapshots (synthetic, default 5000)
--levels N           depth levels per side (default 20)
--tick SIZE          tick size (default 0.01)
--no-realistic-ofi   disable realistic OFI mode (clean null case)
--no-ofi             skip OFI section
--no-impact          skip slippage section
--no-backtest        skip backtest
--save-csv           dump computed metrics to CSV
```

## Known limitations

- Synthetic generator is too clean — no adverse selection, no queue
  priority, no partial fills. Real-data Sharpe will be much lower.
- Walk-the-book slippage doesn't model queue position — assumes you can
  take whatever size is shown.
- OFI uses snapshots, not deltas. Real exchanges send deltas; I
  reconstruct snapshots on the receiver side.
- Backtest is one-position-at-a-time and uses fixed sizing. A real
  strategy would size by signal strength and risk budget.

## References

- Cont, Kukanov, Stoikov (2014) — *The Price Impact of Order Book
  Imbalance*. Source for the OFI formula.
- Almgren et al. (2005) — *Direct Estimation of Equity Market Impact*.
  Square-root impact model.
- Gatheral (2010) — *No-Dynamic-Arbitrage and Market Impact*.
- Bouchaud, Farmer, Lillo (2009) — *How Markets Slowly Digest Changes
  in Supply and Demand*. Survey of microstructure stylized facts.

## License

MIT — see [LICENSE](LICENSE).

## Disclaimer

This project is for **educational and research purposes only**. It is not
financial advice, not a recommendation to trade, and not suitable for
real trading without substantial additional work.

- The synthetic data generator is a simplified model of real markets,
  not a faithful simulation. Any backtest results on synthetic data
  are not indicative of real-world performance.
- The OFI signal, backtest, and slippage models make many simplifying
  assumptions (no adverse selection, no queue priority, no latency, no
  partial fills, no transaction costs beyond a flat round-trip fee).
  Real trading incurs all of these and more.
- If you choose to use any part of this code on real market data or
  with real money, you do so entirely at your own risk. The author
  assumes no liability for any financial losses or other damages
  arising from the use of this software.

See the [LICENSE](LICENSE) file for the full MIT terms.
