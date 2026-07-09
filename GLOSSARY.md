# Glossary — Order Book Analysis 

Every term used in this project, explained simply. Read this alongside
the README if any part of the code feels unfamiliar.

---

## A. The Order Book Itself

### Level-2 Order Book
A list showing **all the pending buy and sell orders** waiting on an
exchange, organized by price level. "Level-2" means we see multiple
price levels deep — not just the best price. Imagine a restaurant menu
where buyers and sellers have placed "standing orders": *I'll buy 5
shares at $99.50, I'll buy 3 at $99.49, ...* and *I'll sell 4 shares
at $99.52, I'll sell 6 at $99.53, ...*. That whole list, updated in
real time, is the Level-2 order book.

### Bid
The **highest price anyone is willing to pay** right now. There can be
many bid prices stacked below the best bid (each one lower than the
one above it). "Bid side" = all the buy orders.

### Ask (also called "Offer")
The **lowest price anyone is willing to sell at** right now. "Ask side"
= all the sell orders. Best ask is always higher than best bid —
otherwise trade would happen instantly.

### Mid Price
The average of the best bid and best ask: `(best_bid + best_ask) / 2`.
A reasonable "fair value" estimate at any moment. We use it as the
reference price for almost every metric.

### Spread
The gap between best ask and best bid: `best_ask - best_bid`. The
simplest measure of liquidity — a tight spread means buyers and
sellers nearly agree on price.

### Tick Size
The smallest allowed price increment on an exchange. For US stocks
it's usually $0.01. For BTC/USDT it's $0.01. For E-mini S&P futures
it's $0.25. Prices must move in whole multiples of the tick.

### Snapshot
A single moment-in-time picture of the entire order book — like
pressing pause and reading off every level. Our project works with
snapshots (5,000 of them by default), each one frozen at a different
moment.

### Delta
The *change* between two snapshots. Real exchanges send deltas
("level 3 just got 100 shares bigger"); we work with snapshots
directly because that's what most analysis needs.

### Queue
The line of pending orders at a specific price level. The "bid queue
at $99.50" = all buy orders waiting at that price. When new buy
orders arrive at $99.50, the queue grows. When buyers cancel or
trades happen, the queue shrinks.

---

## B. Liquidity Concepts

### Liquidity
How easy it is to buy or sell a lot of something without moving the
price much. A liquid market = tight spreads, deep books, lots of
trading. An illiquid market = wide spreads, thin books, big price
moves when you trade.

### Depth
How much size (number of shares / contracts / coins) is sitting on
the book at various price levels. "Deep" book = lots of size
available. "Thin" book = little size available.

### Top-N Depth
Total size available in the top N price levels. "Top-5 depth" = sum
of sizes at levels 0, 1, 2, 3, 4. A single number that summarizes
"how thick is the book near the top."

### Cumulative Depth Curve
A running total: at level 0 you have X size, at level 1 you have X +
Y, at level 2 you have X + Y + Z, and so on. Tells you "if I sweep
levels 0 through L, how much can I fill?" — which is exactly what a
large market order does.

### Liquidity Heatmap
A 2D color chart: rows = time bins, columns = depth levels, color =
average size in that cell. Best chart for spotting **liquidity
regimes** — quiet periods vs stressed periods where the whole book
thins out at once.

### Book Imbalance
`(bid_depth − ask_depth) / (bid_depth + ask_depth)`. Range: −1 to +1.
- Positive = more buy orders than sell orders (buyers more eager)
- Negative = more sell orders than buy orders (sellers more eager)
A simple directional pressure indicator.

---

## C. Spread Measurement Units

### Spread in Absolute Terms
Just `best_ask - best_bid` in price units (e.g., $0.02).

### Spread in Ticks
`spread_abs / tick_size`. Tells you "how many minimum price
increments wide is the spread?" A $0.02 spread on a $0.01-tick asset
= 2 ticks. More natural for exchange data than absolute price.

### Spread in Basis Points (bps)
`spread_abs / mid × 10,000`. One basis point = 1/100th of a percent.
Asset-normalized — lets you compare spreads across assets of very
different prices (e.g., a $100 stock vs a $30,000 bitcoin).

---

## D. Order Flow Imbalance (OFI)

### Order Flow
The stream of new orders entering the book: market orders (aggressive,
cross the spread), limit orders (passive, sit in the book),
cancellations.

### Order Flow Imbalance (OFI)
A signal that measures **net pressure on the book** by tracking how
much the bid and ask queues change between snapshots:
```
OFI(t) = Σ over top-L levels of [ ΔBidQty(t) − ΔAskQty(t) ]
```
- Bid queue growing → buyers adding liquidity → upward pressure
- Ask queue growing → sellers adding liquidity → downward pressure
- OFI > 0 = net buying pressure; OFI < 0 = net selling pressure

### Rolling OFI
Sum of OFI over the last N snapshots (e.g., 50). Smooths out
snapshot-to-snapshot noise and shows the *trend* in pressure.

### Lagged Correlation
We measure `corr(OFI(t), mid_return(t+1))` — does today's OFI predict
the next snapshot's price move? On real data this is typically
0.2–0.5 for liquid assets. (On our synthetic data it's near zero by
construction — the simulator makes queues and price independent.)

### Short-Horizon Return
The price change over a small number of snapshots (1, 5, 50). "Short"
in high-frequency context = seconds to minutes, not days.

---

## E. Slippage & Price Impact

### Marketable Order
A buy order priced at or above the best ask, or a sell order priced
at or below the best bid. It will execute immediately against the
book. Same as a "market order" in practice.

### Walking the Book
What happens when your marketable order is bigger than the top level:
it "walks" through the levels, consuming size at each price.
Example: you want to buy 100 units. The book has 30 at $100.00, 40
at $100.01, 30 at $100.02. Your order fills 30 + 40 + 30 = 100,
paying three different prices.

### VWAP (Volume-Weighted Average Price)
The average price you actually paid, weighted by how much you filled
at each level. In the example above:
```
VWAP = (30×100 + 40×100.01 + 30×100.02) / 100 = 100.01
```

### Slippage
How much worse your fill price was versus the mid price when you
started. Usually expressed in basis points:
```
slippage_bps = (VWAP - mid) / mid × 10,000   (for a buy)
slippage_bps = (mid - VWAP) / mid × 10,000   (for a sell)
```
Slippage is the **cost of trading** — what you lose to the book's
limited depth.

### Price Impact
The general phenomenon: larger orders move the price against you.
Slippage is the *measured* cost; impact is the *underlying force*
that causes it. Often used interchangeably.

### Square-Root Impact Model
A robust empirical regularity: impact grows with the **square root**
of order size, not linearly:
```
impact ≈ σ × √(Q / ADV)
```
where σ = volatility, Q = order size, ADV = average daily volume.
Doubling your order size doesn't double the cost — it increases it
by about √2 ≈ 1.41x. This pattern shows up across stocks, futures,
crypto, basically every liquid market.

### ADV (Average Daily Volume)
How much of an asset trades in a typical day. Used as a "normal size"
benchmark — a $10M order is huge for a stock with $50M ADV, tiny for
one with $5B ADV. Our project uses mean per-snapshot total depth as
an ADV proxy.

### Volatility (σ)
How much the price moves around. Mathematically: standard deviation
of log returns. Higher volatility = wilder price swings = larger
impact for the same order size.

### Fill Rate
% of snapshots where your order actually got fully filled. If the
book is too thin and your order is too big, you can't fill at all —
fill rate drops below 100%. Our slippage table reports this.

---

## F. Statistical / Math Terms Used in the Code

### Random Walk
A path where each step is random and independent of previous steps.
Drunkard's walk. Our mid-price is a random walk — each snapshot's
log-return is drawn fresh from a normal distribution.

### Geometric Random Walk
A random walk on the **log** of price, so price changes are
*percentage* changes, not absolute. Standard model for stock prices:
$100 → +1% → $101 → -1% → $99.99, not $100 → +$1 → $101 → -$1 →
$100. Same idea, multiplicative instead of additive.

### Log Return
`log(price_t / price_{t-1})`. Why log instead of simple
`(p_t - p_{t-1})/p_{t-1}`? Log returns are symmetric (a +10% then
-10% gets you back to start) and additive over time. Standard in
finance.

### Normal Distribution (Gaussian)
The bell curve. Defined by mean (center) and standard deviation
(width). We use it for per-snapshot log returns: each step is drawn
from `N(0, σ)`.

### Poisson Distribution
A distribution for "count of events in a fixed window." We use it for
spread-in-ticks: usually 1-3 ticks, occasionally 5+, rarely 8+.
Models the sticky-but-occasionally-jumpy behavior of real spreads.

### Log-Normal Distribution
If `X ~ Normal`, then `e^X ~ LogNormal`. Always positive, right-
skewed. We use it for size noise: multiply the base size by a
log-normal random factor, so sizes are always positive and
occasionally spike.

### Exponential Decay
A quantity that shrinks by a fixed fraction each step. We use it for
the depth profile: each level has `qty_decay` (e.g., 0.85) as much
size as the level above. So level 0 = 1.0, level 1 = 0.85, level 2 =
0.72, level 3 = 0.61, etc. Most real books look like this.

### Pearson Correlation
A number between −1 and +1 measuring linear relationship between two
variables. +1 = perfectly in sync, 0 = no linear relationship, −1 =
perfectly opposite. We use it to measure whether OFI predicts
returns.

---

## G. Code / Project Terms

### DataFrame (Pandas)
A 2D table with named columns, like an Excel sheet. The standard data
structure in Python data science. Our entire project revolves around
one big DataFrame with columns: `timestamp, level, bid_price,
bid_qty, ask_price, ask_qty, mid, spread`.

### Long Format
One row per (timestamp, level) combination. Wide format would have
one row per timestamp with columns `bid_price_0, bid_price_1, ...`.
Long format is easier to filter/group/aggregate in Pandas.

### CLI (Command-Line Interface)
A program you run from the terminal: `python main.py --ticks 5000`.
The alternative is a GUI or notebook. We have both.

### Argparse
Python's built-in argument parser. Reads flags like `--ticks 5000`
from the command line and turns them into Python variables.

### Module / Package
A Python file is a *module* (e.g., `data.py`). A folder of modules
with an `__init__.py` is a *package* (e.g., `orderbook/`). Lets you
`from orderbook.data import BookParams`.

### Dataclass
A Python decorator (`@dataclass`) that auto-generates boilerplate
methods (constructor, repr, equality) for a class that mostly holds
data. `BookParams` is a dataclass — just a tidy container for
parameters.

### Seed (Random Seed)
A starting number for the random number generator. Same seed → same
"random" numbers → reproducible results. We default to `seed=42` so
the synthetic data is identical every run.

---

## H. Asset Class Presets

The README has presets for three asset classes. Quick definitions:

### Crypto (e.g., BTC/USDT)
Bitcoin priced in US dollars on an exchange like Binance. Tiny tick
($0.01), high volatility, very deep books (50+ levels), trades 24/7.

### US Equity (e.g., AAPL)
Apple stock on NASDAQ/NYSE. $0.01 tick, lower volatility, ~20 levels
deep, trades 9:30–16:00 Eastern. Regulated by Reg NMS (best execution
rules).

### Futures (e.g., E-mini S&P 500 — "ES")
A contract on the S&P 500 index, traded on CME. $0.25 tick (much
bigger than equities), intermediate volatility, ~10 levels deep,
trades nearly 24 hours.

### Generic
Asset-agnostic defaults. What the project uses if you don't override.
Useful for testing and learning the code without picking a real
asset.

---

## I. References (Papers Behind the Methods)

If you want to go deeper, these are the original papers:

1. **Cont, R., Kukanov, A., & Stoikov, S. (2014).**
   *The price impact of order book imbalance.*
   — Source of the OFI formula.

2. **Almgren, R., Thum, C., Hauptmann, E., & Li, H. (2005).**
   *Direct estimation of equity market impact.*
   — Empirical square-root impact model.

3. **Gatheral, J. (2010).**
   *No-dynamic-arbitrage and market impact.*
   — Theoretical justification for the square-root form.

4. **Bouchaud, J.-P., Farmer, J. D., & Lillo, F. (2009).**
   *How markets slowly digest changes in supply and demand.*
   — Great survey of microstructure stylized facts.

You don't need to read these to use the code, but if you're showing
this project in an interview or portfolio, at least skim the Cont
(2014) abstract so you can explain OFI confidently.

---

## J. New Terms (Backtest & Realistic OFI Mode)

These terms appear in the new signal-to-strategy backtest and the
realistic OFI generator added in v0.2.

### Latent Pressure
A hidden (unobservable) variable that represents net buy/sell interest
in the market. We model it as an AR(1) process. In `realistic_ofi`
mode, pressure drives BOTH queue changes at the top of the book AND
the next snapshot's mid return — which is what creates the OFI → return
predictive relationship.

### AR(1) Process (Autoregressive of order 1)
A time series where each value depends on its previous value plus
random noise: `x(t) = phi * x(t-1) + noise`. The parameter `phi`
(0 to 1) controls persistence — high phi means slow decay, low phi
means fast mean-reversion. We use phi=0.85 for the pressure process,
so pressure persists for ~10-20 snapshots before fading.

### Z-Score
How many standard deviations a value is from its mean:
`z = (x - mean) / std`. We compute a *trailing* z-score (mean and std
over the last 200 snapshots) so the signal adapts to changing market
conditions. Z = +1 means "OFI is one standard deviation above its
recent average" — a moderate buy signal.

### Entry Threshold
The z-score magnitude required to trigger a trade. We use ±1.0 by
default. Higher threshold (e.g., ±2.0) = fewer trades but each more
convincing; lower threshold (e.g., ±0.5) = more trades but noisier.

### Holding Period
How long we keep a position open before closing it. We use 5 snapshots
by default. Longer holding periods capture slower-moving signals but
expose us to more random price noise.

### Round-Trip Cost
The total cost of entering AND exiting a trade. Includes the bid-ask
spread (you pay half on entry, half on exit) plus any exchange fees.
We default to 1 basis point (0.01%) — realistic for liquid futures,
optimistic for spot crypto.

### Backtest
Running a trading strategy on historical data to see how it would
have performed. The simplest backtest assumes you can trade at the
mid price (no slippage) — we go one step better and charge a fixed
round-trip cost to keep things honest. Real production backtests
model slippage, queue position, latency, and partial fills.

### Hit Rate
% of trades that were profitable. A hit rate above 50% is necessary
(but not sufficient) for a strategy to make money — you also need
the average win to be at least as big as the average loss.

### Sharpe Ratio
Risk-adjusted return: `mean_return / std_return` (annualized by
multiplying by sqrt(252) for daily, or sqrt(N) for whatever horizon).
- Sharpe > 1 = good
- Sharpe > 2 = excellent
- Sharpe > 5 = suspicious (probably overfit or unrealistic
  assumptions)
- Our synthetic-data Sharpe of ~12 is artificially high — see the
  notebook caveat. Real microstructure alphas typically run 1-3.

### Long / Short
- **Long**: buy an asset, profit if price goes up.
- **Short**: sell borrowed asset, profit if price goes down.
Our backtest takes both long and short positions based on the OFI
signal direction.

### Position
How much of an asset you currently hold. +1 = long 1 unit, -1 = short
1 unit, 0 = flat (no position). Our backtest only takes positions of
size 1 (toy strategy — real strategies size positions by signal
strength and risk budget).

### Cumulative P&L
Running total of profit-and-loss from all trades. Starts at 0,
increases with winning trades, decreases with losing trades (and
costs). The final number is the strategy's total return over the
backtest period, in basis points.

### Realistic OFI Mode vs. Null Mode
- **Realistic mode** (`realistic_ofi=True`, default): latent pressure
  drives queues and returns together → OFI correlates with next
  return (~0.16 on default params, similar to real-data 0.2-0.5).
- **Null mode** (`realistic_ofi=False`): queues and returns are
  independent → OFI correlation ~0. Useful as a control / sanity
  check: if your signal still makes money in null mode, something is
  wrong (likely lookahead bias).

### Lookahead Bias
A common backtest bug where you accidentally use information from the
future to make decisions in the present. Our backtest carefully uses
only past data (lagged OFI) to predict future returns. The
`realistic_ofi=False` null mode is a guard against this: if the
backtest still shows profits in null mode, you've got a lookahead bug.

---

## K. Reading the Charts (Quick Reference)

| Chart | What it shows | What to look for |
|---|---|---|
| 01_spread_timeseries.png | Mid price + spread over time | Stable spread = liquid; spikes = stress |
| 02_depth_profile.png | Size per level + cumulative | Convex cumulative curve = healthy book |
| 03_liquidity_heatmap.png | Size by (time, level) | Dark bands = thin liquidity periods |
| 04_book_imbalance.png | Bid-ask imbalance over time | Sustained + or - = directional pressure |
| 05_ofi.png | Rolling OFI vs mid price | OFI should lead price (positive corr) |
| 06_slippage_curve.png | Slippage vs order size | Curves up like √Q — the "square-root law" |
| 07_ofi_backtest.png | Z-score + position + cumulative P&L | Upward-sloping P&L = signal works |
