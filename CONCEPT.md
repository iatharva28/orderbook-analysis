# Concepts & Interview Prep Guide

**Purpose:** Every term used in this project + every concept an Akuna
Capital interviewer might ask you about, explained in plain English.

**How to use this file:**
- Section A-G cover terms actually used in this project (look them up
  when you see them in the code)
- Section H-K cover the *broader* concepts Akuna's "101 course" and
  interviews expect you to know, even though we didn't implement them
  (options, greeks, market making, volatility)
- Each term has a **"If interviewer asks"** block showing how to answer
  confidently in 30 seconds or less

---

## A. The Order Book

### Level-2 Order Book
A real-time list of every pending buy and sell order on an exchange,
organized by price level. "Level-1" = just the best bid and best ask.
"Level-2" = the top N levels deep on each side. "Level-3" = full order
queue with order IDs (only available to market makers paying for direct
data feeds).

**If interviewer asks:** *"Walk me through what's in a Level-2 feed."*
> "Each snapshot contains the top-N price levels on both sides. For each
> level you see the price and the total size available. NASDAQ TotalView
> and Binance depth20 are examples. Market makers use Level-2 to read
> imbalance and anticipate short-horizon price moves."

### Bid
The highest price anyone is willing to pay right now. Below the best
bid there can be many more bids at lower prices, each with its own
size. The bid side = all buy limit orders waiting to be filled.

**If interviewer asks:** *"What's the difference between bid and ask?"*
> "Bid is the best price a buyer will pay. Ask is the best price a
> seller will accept. They never cross — if they did, a trade would
> happen instantly. The gap between them is the spread."

### Ask (also called Offer)
The lowest price anyone is willing to sell at right now. Always above
the best bid. The ask side = all sell limit orders.

### Mid Price
The midpoint between best bid and best ask: `(best_bid + best_ask) / 2`.
A reasonable "fair value" estimate at any instant. Used as the
reference price for almost every microstructure metric.

### Spread
The gap between best ask and best bid. The simplest liquidity metric.
Tight spread = liquid market; wide spread = illiquid.

**If interviewer asks:** *"Why is the spread a liquidity measure?"*
> "Spread is the cost of an immediate round-trip: buy at ask, instantly
> sell at bid, you lose the spread. A tight spread means that cost is
> small — that's the definition of liquid."

### Tick Size
The minimum allowed price increment. US stocks: $0.01. E-mini S&P
futures: $0.25. BTC/USDT: $0.01. Prices must move in whole multiples.

**If interviewer asks:** *"Why do tick sizes matter?"*
> "They set the minimum spread. If the tick is $0.01 on a $100 stock,
> the tightest possible spread is 1 bp. On a $1000 stock the same
> tick is 0.1 bp — relative spread tightens, which is why high-priced
> stocks are often more liquid. Exchanges choose tick sizes to balance
> spread tightness against quote clutter."

### Snapshot
A single moment-in-time picture of the entire order book. Our project
works with 5,000 snapshots per run. Real exchanges emit updates
(deltas) but most analysis is done on reconstructed snapshots.

### Delta (in order book context)
The change between two snapshots. "Bid at level 3 grew by 50 shares"
is a delta. Real exchange feeds (NASDAQ ITCH, Binance diff depth)
send deltas; receivers stitch them into snapshots.

> ⚠️ Don't confuse with **options delta** (Section I) — same word,
> different meaning. Context tells you which.

### Queue
The line of pending orders at a specific price level. The "bid queue
at $99.50" = all buy orders waiting at that price. When new buy orders
arrive at $99.50, the queue grows. When buyers cancel or trades happen,
the queue shrinks. Queue position matters: FIFO means first to arrive
gets filled first.

---

## B. Liquidity Concepts

### Liquidity
How easily you can buy or sell a lot of something without moving the
price. A liquid market = tight spreads, deep books, lots of trading.
An illiquid market = wide spreads, thin books, big price moves when
you trade.

**If interviewer asks:** *"How would you measure liquidity?"*
> "Three dimensions: tightness (spread), depth (size at top levels),
> and resiliency (how fast the book refills after a large trade). Our
> project measures the first two directly; the heatmap gives a view of
> the third over time."

### Depth
How much size is sitting on the book at various price levels. "Deep"
book = lots of size available. "Thin" book = little size.

### Top-N Depth
Total size in the top N price levels. "Top-5 depth" = sum of sizes at
levels 0, 1, 2, 3, 4. A single number that summarizes "how thick is
the book near the top."

### Cumulative Depth Curve
A running total: at level 0 you have X size, at level 1 X+Y, at level
2 X+Y+Z, etc. Tells you "if I sweep levels 0 through L, how much can
I fill?" — which is exactly what a large market order does.

### Liquidity Heatmap
A 2D color chart: rows = time bins, columns = depth levels, color =
average size in that cell. Best chart for spotting liquidity regimes
— quiet periods vs stressed periods where the whole book thins out
at once.

### Book Imbalance
`(bid_depth − ask_depth) / (bid_depth + ask_depth)`. Range: −1 to +1.
Positive = more buy orders than sell orders (buyers more eager).
A simple directional pressure indicator.

**If interviewer asks:** *"What's the difference between imbalance and OFI?"*
> "Imbalance is a *snapshot* — it looks at the current state of the
> book. OFI is a *flow* — it looks at queue *changes* between
> snapshots. OFI captures cancellations and additions, which are the
> actual signal; imbalance is a coarser proxy."

---

## C. Spread Measurement Units

### Spread in Absolute Terms
Just `best_ask − best_bid` in price units (e.g., $0.02).

### Spread in Ticks
`spread_abs / tick_size`. Tells you "how many minimum price increments
wide is the spread?" A $0.02 spread on a $0.01-tick asset = 2 ticks.

### Spread in Basis Points (bps)
`spread_abs / mid × 10,000`. One basis point = 1/100th of a percent.
Lets you compare spreads across assets of very different prices.

**If interviewer asks:** *"Why use bps instead of absolute?"*
> "A $0.01 spread on a $10 stock is 10 bps — pretty wide. The same
> $0.01 spread on a $1,000 stock is 0.1 bps — extremely tight. Bps
> normalizes for price level, so you can compare liquidity across
> assets."

---

## D. Order Flow Imbalance (OFI)

### Order Flow
The stream of new orders entering the book: market orders (aggressive,
cross the spread), limit orders (passive, sit in the book),
cancellations.

### Order Flow Imbalance (OFI)
A signal measuring **net pressure on the book** by tracking queue
changes between snapshots:
```
OFI(t) = Σ over top-L levels of [ ΔBidQty(t) − ΔAskQty(t) ]
```
- Bid queue growing → buyers adding liquidity → upward pressure
- Ask queue growing → sellers adding liquidity → downward pressure
- OFI > 0 = net buying pressure; OFI < 0 = net selling pressure

**If interviewer asks:** *"What is OFI and why does it work?"*
> "OFI was introduced by Cont, Kukanov, and Stoikov in 2014. It sums
> queue changes at the top levels of the book — when the bid queue
> grows and the ask queue shrinks, that's net buying pressure, and
> the mid price tends to drift up over the next few snapshots. The
> correlation with short-horizon returns is typically 0.2 to 0.5 on
> liquid assets."

**If interviewer asks:** *"Why use OFI instead of just trade flow?"*
> "Trade flow only sees aggressor side. OFI captures the *passive*
> side too: cancellations, new limit orders, modifications. A big
> cancel on the bid is a strong signal even though no trade happened.
> OFI sees that; trade flow doesn't."

### Rolling OFI
Sum of OFI over the last N snapshots (e.g., 50). Smooths out
snapshot-to-snapshot noise and shows the *trend* in pressure.

### Lagged Correlation
We measure `corr(OFI(t), mid_return(t+1))` — does today's OFI predict
the next snapshot's price move? On real data this is typically
0.2–0.5 for liquid assets. Lagged (not contemporaneous) is what makes
it a *signal* — if it were contemporaneous, you couldn't trade on it.

### Short-Horizon Return
Price change over a small number of snapshots (1, 5, 50). "Short"
in high-frequency context = seconds to minutes, not days.

---

## E. Slippage & Price Impact

### Marketable Order
A buy order priced at or above the best ask, or a sell order priced
at or below the best bid. Will execute immediately against the book.
Same as a "market order" in practice.

### Walking the Book
What happens when your marketable order is bigger than the top level:
it walks through the levels, consuming size at each price.
Example: buy 100 units. Book has 30 at $100.00, 40 at $100.01, 30
at $100.02. Your order fills 30 + 40 + 30 = 100, paying three prices.

### VWAP (Volume-Weighted Average Price)
The average price you actually paid, weighted by how much you filled
at each level. Example:
```
VWAP = (30×100 + 40×100.01 + 30×100.02) / 100 = 100.01
```

**If interviewer asks:** *"What is VWAP and how is it used?"*
> "VWAP is the volume-weighted average fill price. It's the benchmark
> for execution quality — if your fills are below VWAP (for buys),
> you executed well; above VWAP, you paid too much. Many institutional
> algos are designed to track or beat VWAP over the day."

### Slippage
How much worse your fill price was versus the mid when you started.
Usually expressed in basis points:
```
slippage_bps = (VWAP - mid) / mid × 10,000  (for a buy)
```
Slippage is the **cost of trading** — what you lose to the book's
limited depth.

### Price Impact
The general phenomenon: larger orders move the price against you.
Slippage is the *measured* cost; impact is the *underlying force*
that causes it. Often used interchangeably.

**If interviewer asks:** *"Why does impact grow with sqrt(size) and not linearly?"*
> "Empirically observed across every liquid market — stocks, futures,
> crypto. The intuition is that as you walk deeper into the book,
> each incremental unit of size hits a thinner marginal layer, so
> the marginal cost per unit rises. Almgren et al. (2005) and
> Gatheral (2010) give the theoretical justification."

### Square-Root Impact Model
A robust empirical regularity: impact grows with the **square root**
of order size:
```
impact ≈ σ × √(Q / ADV)
```
where σ = volatility, Q = order size, ADV = average daily volume.
Doubling your order size doesn't double the cost — it increases it
by √2 ≈ 1.41x.

### ADV (Average Daily Volume)
How much of an asset trades in a typical day. Used as a "normal
size" benchmark — a $10M order is huge for a stock with $50M ADV,
tiny for one with $5B ADV.

### Volatility (σ)
How much the price moves around. Mathematically: standard deviation
of log returns. Higher volatility = wilder price swings = larger
impact for the same order size.

### Fill Rate
% of snapshots where your order actually got fully filled. If the
book is too thin and your order is too big, you can't fill at all —
fill rate drops below 100%.

---

## F. Statistical Terms Used in the Code

### Random Walk
A path where each step is random and independent of previous steps.
Our mid-price is a random walk — each snapshot's log-return is drawn
fresh from a normal distribution.

### Geometric Random Walk
A random walk on the **log** of price, so price changes are
*percentage* changes, not absolute. Standard model for stock prices:
$100 → +1% → $101 → -1% → $99.99, not $100 → +$1 → $101 → -$1 →
$100. Multiplicative, not additive.

**If interviewer asks:** *"Why geometric and not arithmetic?"*
> "Stocks can't go negative. An arithmetic random walk can — that's
> unrealistic. Geometric (log) random walks guarantee positivity,
> and log returns are additive over time, which makes the math
> cleaner."

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
A distribution for "count of events in a fixed window." We use it
for spread-in-ticks: usually 1-3 ticks, occasionally 5+, rarely 8+.
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
0.72, level 3 = 0.61, etc.

### Pearson Correlation
A number between −1 and +1 measuring linear relationship between two
variables. +1 = perfectly in sync, 0 = no linear relationship, −1 =
perfectly opposite. We use it to measure whether OFI predicts returns.

### AR(1) Process (Autoregressive of order 1)
A time series where each value depends on its previous value plus
random noise: `x(t) = φ * x(t-1) + noise`. The parameter φ (0 to 1)
controls persistence — high φ means slow decay, low φ means fast
mean-reversion.

We use φ=0.85 for the latent pressure process in realistic OFI mode,
so pressure persists for ~10-20 snapshots before fading.

---

## G. Backtest & Signal Terms

### Latent Pressure
A hidden (unobservable) variable representing net buy/sell interest
in the market. In our `realistic_ofi` mode, pressure drives BOTH
queue changes AND the next snapshot's mid return — which is what
creates the OFI → return predictive relationship.

### Z-Score
How many standard deviations a value is from its mean:
`z = (x - mean) / std`. We compute a *trailing* z-score (mean and
std over the last 200 snapshots) so the signal adapts. Z = +1 means
"OFI is one standard deviation above its recent average."

### Entry Threshold
The z-score magnitude required to trigger a trade. We use ±1.0.
Higher threshold (±2.0) = fewer trades but each more convincing;
lower threshold (±0.5) = more trades but noisier.

### Holding Period
How long we keep a position open before closing it. We use 5
snapshots by default. Longer holding periods capture slower-moving
signals but expose us to more random price noise.

### Round-Trip Cost
The total cost of entering AND exiting a trade. Includes the bid-ask
spread (you pay half on entry, half on exit) plus any exchange fees.
We default to 1 basis point — realistic for liquid futures,
optimistic for spot crypto.

### Backtest
Running a trading strategy on historical data to see how it would
have performed. The simplest backtest assumes you can trade at the
mid price (no slippage) — we go one step better and charge a fixed
round-trip cost. Real production backtests model slippage, queue
position, latency, and partial fills.

### Hit Rate
% of trades that were profitable. A hit rate above 50% is necessary
(but not sufficient) for a strategy to make money — you also need
the average win to be at least as big as the average loss.

**If interviewer asks:** *"What's more important, hit rate or payoff ratio?"*
> "Neither alone — what matters is expectancy: `hit_rate × avg_win -
> (1 - hit_rate) × avg_loss`. A 55% hit rate with equal win/loss is
> profitable. A 70% hit rate where losses are 3x the wins is
> unprofitable. Expectancy is the only number that matters."

### Sharpe Ratio
Risk-adjusted return: `mean_return / std_return` (annualized by
multiplying by sqrt(N) for whatever horizon).
- Sharpe > 1 = good
- Sharpe > 2 = excellent
- Sharpe > 5 = suspicious (probably overfit or unrealistic
  assumptions)
- Our synthetic-data Sharpe of ~12 is artificially high. Real
  microstructure alphas typically run 1-3.

**If interviewer asks:** *"What's a good Sharpe ratio?"*
> "For a single strategy: 1-2 is solid, 2-3 is excellent, above 3
> starts to smell like overfitting. Multi-strategy portfolios can
> run higher because strategies are uncorrelated. Renaissance
> Technologies' Medallion Fund has reportedly run Sharpe above 5
> for decades — that's an outlier."

### Long / Short
- **Long**: buy an asset, profit if price goes up.
- **Short**: sell borrowed asset, profit if price goes down.

### Position
How much of an asset you currently hold. +1 = long 1 unit, -1 =
short 1 unit, 0 = flat (no position).

### Cumulative P&L
Running total of profit-and-loss from all trades. Starts at 0,
increases with winning trades, decreases with losing trades (and
costs).

### Lookahead Bias
A common backtest bug where you accidentally use information from
the future to make decisions in the present. Our backtest carefully
uses only past data (lagged OFI) to predict future returns. The
`realistic_ofi=False` null mode is a guard against this: if the
backtest still shows profits in null mode, you've got a lookahead
bug.

---

## H. Market Making Concepts (Akuna 101 — Core Business)

> These concepts are NOT in our project, but they are Akuna's
> *core business*. You WILL be asked about them.

### Market Maker
A firm that continuously posts both bid and ask quotes, profiting
from the spread. Provides liquidity to the market. Akuna, Jane
Street, Optiver, IMC, Virtu are all market makers.

**If interviewer asks:** *"How does a market maker make money?"*
> "Two ways: (1) the spread — buy at bid, sell at ask, capture the
> difference, repeat; (2) rebates — some exchanges pay for providing
> liquidity. The risk is adverse selection — you get filled right
> before the price moves against you."

### Adverse Selection
The tendency for your quotes to get filled precisely when informed
traders know something you don't. If you're bidding $100 and an
informed seller hits you, it's probably because the price is about
to drop. Your "inventory" then loses value. This is the market
maker's biggest enemy.

**If interviewer asks:** *"What's adverse selection?"*
> "When your resting quote gets filled, ask: why is the other side
> trading? If they have information you don't, you just got picked
> off. Market makers measure this as the typical price move
> *against* them right after a fill. Strategies to mitigate: tighten
> quotes in fast markets, cancel quickly on signals, use OFI-style
> signals to skew quotes."

### Inventory Risk
The risk of holding a position that moves against you. A market
maker accumulates inventory as they get filled on one side; they
need to manage this risk by skewing quotes to attract offsetting
flow.

### Quote Skew
Deliberately moving your bids and asks asymmetrically to attract
one side and repel the other. If you're long inventory, lower both
your bid and ask — makes you less attractive to sellers (who would
add to your long) and more attractive to buyers (who would reduce
it).

### Spread Capture
The market maker's basic revenue model: post bid at $99.98, post
ask at $100.02, capture $0.04 each time both sides fill. Do this
thousands of times per day.

### Reservation Price
The "fair value" a market maker uses as the center of their quotes,
adjusted for inventory. If you're flat, reservation = mid. If
you're long 1000 units, reservation = mid − small buffer (you'd
rather sell than buy more).

### Latency
Time between an event happening and your code reacting to it. Akuna
cares deeply about this — microseconds matter. Co-located servers
in the exchange data center, FPGA-based reaction logic, etc.

### Tick Capture / Rebate
Some exchanges (e.g., US equities under Reg NMS Maker-Taker) pay a
rebate (typically $0.0001-$0.003/share) for providing liquidity
(maker), and charge a fee for taking it (taker). Market makers
build strategies around capturing these rebates.

---

## I. Options Basics (Akuna 101 — Core Asset Class)

> Akuna is primarily an *options* market maker. You will be asked
> options questions. Our project doesn't cover options, but you must
> know these terms.

### Call Option
A contract giving the buyer the **right, but not obligation**, to
buy an asset at a fixed strike price K, on or before a fixed expiry
T. You buy a call when you think the price will go up.

**Payoff at expiry:** `max(S_T - K, 0)` where S_T is the asset price
at expiry.

**If interviewer asks:** *"When does a call buyer make money?"*
> "When the underlying ends above the strike plus the premium paid.
> If you buy a $100 strike call for $3, you profit if the stock ends
> above $103 at expiry. Below $100, you lose the full $3. Between
> $100 and $103, partial loss."

### Put Option
A contract giving the buyer the right, but not obligation, to
**sell** an asset at strike K on or before expiry T. You buy a put
when you think the price will go down.

**Payoff at expiry:** `max(K - S_T, 0)`.

### Strike Price (K)
The fixed price at which the option holder can exercise. Set when
the option is created.

### Expiry (T)
The date the option stops existing. After expiry, the option is
either exercised (if in the money) or worthless.

### In the Money (ITM)
- Call: underlying > strike
- Put: underlying < strike

### Out of the Money (OTM)
- Call: underlying < strike
- Put: underlying > strike

### At the Money (ATM)
Underlying ≈ strike. Most liquid strike typically.

### Premium
The price you pay to buy an option. Set by supply/demand in the
options market, but theoretically driven by Black-Scholes (Section
J).

### Underlying
The asset the option is written on. Could be a stock, an index, a
future, crypto, etc.

### Notional
The total value the option controls. For a call on 100 shares of a
$50 stock, notional = $5,000. Most US equity options are on 100
shares per contract.

### Moneyness
`S / K` — the ratio of underlying to strike. A useful normalized
coordinate for option pricing. Moneyness > 1 = ITM call.

### Payoff Diagram
A chart of option profit/loss at expiry vs underlying price.
- Long call: hockey stick, loss limited to premium, unlimited upside
- Long put: hockey stick mirror, loss limited to premium, upside
  capped at strike minus premium
- Short call: mirror of long call — unlimited downside
- Short put: mirror of long put — large downside

**If interviewer asks:** *"Draw the payoff of a long straddle."*
> "A straddle = long call + long put at the same strike. V-shaped
> payoff: you profit if the underlying moves a lot in either
> direction, lose the combined premium if it stays near the strike.
> You're long volatility."

### Open Interest
Total number of outstanding option contracts. High open interest =
liquid strike = tight spreads.

### Implied Volatility (IV)
The volatility input that, when plugged into Black-Scholes, gives
the observed option price. **Implied** by the market, not historical.
This is *the* key variable in options trading — you trade volatility,
not direction.

**If interviewer asks:** *"What's the difference between historical and implied vol?"*
> "Historical vol is computed from past price moves — it's backward
> looking. Implied vol is backed out of current option prices —
> it's the market's forward expectation. When IV > HV, options are
> 'expensive' — the market expects bigger moves than have happened
> recently. Option traders buy/sell based on this gap."

### Volatility Smile / Skew
The pattern of implied volatility across strikes at the same expiry.
- **Smile**: U-shaped, higher IV at both wings. Typical for FX.
- **Skew (smirk)**: One wing higher than the other. Equity index
  puts have higher IV than calls — crash protection demand.

**If interviewer asks:** *"Why does the volatility skew exist?"*
> "Equity markets crash down, not up. So out-of-the-money puts are
> in heavy demand as portfolio insurance — that bids up their price,
> which raises their implied vol. Calls don't have the same demand,
> so call IV is lower. The skew is a permanent feature of equity
> options."

### Term Structure of Volatility
IV across different expiries. Normally upward-sloping (longer
maturity = higher IV) but can invert near earnings or events.

---

## J. The Greeks (Akuna 101 — Hedging Language)

> Greeks are partial derivatives of option price with respect to
> various inputs. They tell you how the option's value changes as
> the market moves. **Memorize these.**

### Delta (Δ)
∂(option price) / ∂(underlying price).
- Call delta: 0 to +1 (deep ITM ≈ +1, ATM ≈ 0.5, deep OTM ≈ 0)
- Put delta: −1 to 0

Also: for an option on 100 shares, delta × 100 = "share-equivalent
exposure." A call with delta 0.3 behaves like being long 30 shares.

**If interviewer asks:** *"What is delta and how do you use it?"*
> "Delta is the option's directional exposure — how much the option
> price moves per $1 move in the underlying. A market maker hedges
> delta by trading the underlying: if you're long a call with delta
> 0.5, you short 50 shares per contract to be delta-neutral. Then
> your P&L no longer depends on small underlying moves."

### Gamma (Γ)
∂(delta) / ∂(underlying price) = ∂²(option price) / ∂(underlying)².

How fast delta changes. Long options have positive gamma — your
delta grows in your favor as the underlying moves your way. ATM
short-dated options have the highest gamma.

**If interviewer asks:** *"Why is gamma risky for market makers?"*
> "If you're short gamma, your delta moves against you. The underlying
> rises → your short call's delta gets more negative → you have to
> buy underlying to hedge, but at the now-higher price. You're
> buying high and selling low — that's the gamma trap. Short-dated
> ATM options are the most dangerous because gamma is highest there."

### Theta (Θ)
∂(option price) / ∂(time). Time decay. Options lose value as expiry
approaches (all else equal). Theta is negative for long options
(you bleed time value daily), positive for short options.

**If interviewer asks:** *"Explain theta."*
> "An option's value has two components: intrinsic (what it's worth
> if exercised now) and time (the chance it will move ITM before
> expiry). Theta is the daily erosion of the time component. A
> 30-day ATM call might lose $5 today, all else equal, simply
> because it's now a 29-day call. Short-option strategies profit
> from theta."

### Vega (ν)
∂(option price) / ∂(implied volatility). How much the option price
moves per 1-point (or 1%) change in IV. Long options have positive
vega — when IV rises, your option is worth more.

> Note: "Vega" is not a Greek letter. Sometimes called "kappa" or
> "sigma" in academic literature. Everyone in industry says "vega."

**If interviewer asks:** *"How do you trade volatility?"*
> "Buy options when you think IV will rise (long vega). Sell when
> you think IV will fall. The trick: also manage delta (hedge
> directional exposure by trading underlying) and gamma (manage
> hedging costs). A vega trade is a bet that implied vol is
> mispriced relative to future realized vol."

### Rho (ρ)
∂(option price) / ∂(interest rate). How much the option moves per
1-point change in the risk-free rate. Usually small and ignored
for short-dated options, but matters for long-dated LEAPS.

### Vanna
∂(delta) / ∂(IV) = ∂(vega) / ∂(underlying). How delta changes as
IV moves. Second-order Greek. Matters for vega-heavy books.

### Volga (Vomma)
∂(vega) / ∂(IV). How vega changes as IV moves. Second-order Greek.
Matters when you have a view on vol-of-vol.

### Delta Hedging
Trading the underlying to keep your net delta at zero. Eliminates
directional risk; leaves you exposed to gamma, vega, theta.

### Gamma Scalping
A strategy: long gamma (long options), delta-hedge continuously.
When the underlying moves, your delta drifts; you trade to
re-hedge. If the underlying moves enough, you buy low and sell high
on the re-hedges, capturing profit that pays for theta. Profitable
only if realized vol > implied vol.

**If interviewer asks:** *"Walk me through gamma scalping."*
> "You buy an ATM call (long gamma, long vega, short theta). The
> underlying drops — your delta goes from +0.5 to +0.4 — you buy
> shares to get back to delta-neutral. The underlying then rises —
> delta goes back to +0.5 — you sell the shares you just bought.
> You bought low, sold high. Repeat. If realized vol > implied vol,
> these re-hedge profits exceed theta decay."

### Pin Risk
The risk near expiry of an ATM option — you don't know if it will
be assigned (exercised) or not. A market maker short an ATM option
near expiry has uncertain position going into expiry.

---

## K. Black-Scholes & Pricing (Akuna 101 — Theory)

### Black-Scholes Formula
Theoretical price of a European call:
```
C = S * N(d1) - K * e^(-rT) * N(d2)
where:
  d1 = [ln(S/K) + (r + σ²/2)T] / (σ√T)
  d2 = d1 - σ√T
  N() = standard normal CDF
  S = spot price
  K = strike
  r = risk-free rate
  T = time to expiry (years)
  σ = volatility
```

**If interviewer asks:** *"What are Black-Scholes assumptions?"*
> "European exercise only, no dividends, constant volatility,
> constant interest rate, continuous trading, log-normal underlying,
> no arbitrage. None of these hold exactly in real markets — that's
> why we have the volatility smile (markets relax the constant-vol
> assumption). But BS is still the *language* of options trading —
> all quotes are in IV, which is just BS inverted."

### European vs American Exercise
- **European**: exercise only at expiry. Black-Scholes prices these.
- **American**: exercise any time before expiry. Worth ≥ European.
  Priced with binomial trees or finite difference methods.

### Risk-Neutral Pricing
The trick that makes Black-Scholes work: under the risk-neutral
measure, all assets grow at the risk-free rate. Option price =
discounted expected payoff under this measure.

### No-Arbitrage Principle
If two portfolios have the same payoff, they must have the same
price. Otherwise you buy the cheaper, sell the richer, lock in
profit. BS is built on this.

### Put-Call Parity
For European options on a non-dividend stock:
```
C - P = S - K * e^(-rT)
```
Call minus put = stock minus discounted strike. Lets you price a
put from a call (or vice versa) without BS.

**If interviewer asks:** *"Derive put-call parity."*
> "Consider two portfolios: (A) long call + cash K discounted to T;
> (B) long put + long stock. At expiry, both portfolios are worth
> max(S_T, K). Therefore they must have the same price today:
> C + K e^{-rT} = P + S. Rearrange: C - P = S - K e^{-rT}."

### Binomial Tree
A simpler option pricing model: split time into N steps, at each
step the underlying goes up or down by a fixed factor. Work
backwards from expiry to today. Converges to BS as N → ∞. Used
for American options where BS doesn't apply.

### Monte Carlo Pricing
Simulate many random paths for the underlying, compute the average
discounted payoff. Works for any payoff but is slow.

---

## L. Trading Strategy & Execution Concepts

### Alpha
A signal that predicts future returns. "Alpha" originally meant
excess return over the market (CAPM alpha), now means any
predictive signal.

### Beta
Exposure to the market portfolio. A stock with beta 1.2 moves 1.2%
for every 1% market move.

### Mean Reversion
The tendency of prices to return to a "normal" level. Strategy:
sell when price is above its mean, buy when below. Works in
range-bound markets, fails in trending markets.

### Momentum
The tendency of prices to keep moving in the same direction.
Strategy: buy what's been going up, sell what's been going down.
Works in trending markets, fails at turning points.

### Statistical Arbitrage (StatArb)
Quantitative strategies that exploit small statistical
inefficiencies, typically mean-reversion between cointegrated
pairs. Pairs trading is the classic example.

### Pairs Trading
Long stock A, short stock B, where A and B are cointegrated (their
price ratio mean-reverts). When the ratio deviates, trade expecting
reversion.

### Cointegration
Two time series are cointegrated if some linear combination is
stationary (mean-reverting). E.g., two share classes of the same
company — they should trade at a fixed ratio.

### Market Impact (revisited from Section E)
In execution context: the amount by which your trading moves the
price against you. Almgren-Chriss model is the classic optimal
execution framework.

### Implementation Shortfall
The difference between the decision price (when you decided to
trade) and the actual execution price. Total cost = market impact +
opportunity cost + fees.

### TWAP (Time-Weighted Average Price)
Execution algorithm: split a large order into equal-sized child
orders, spaced evenly over time. Minimizes market impact by avoiding
concentration.

### VWAP Algorithm
Execution algorithm: spread orders through the day, weighted by
expected volume pattern (more at open/close). Tries to match or
beat the day's VWAP.

### Almgren-Chriss Model
The classic optimal execution framework. Trades off market impact
(executing too fast costs impact) against volatility risk (executing
too slow exposes you to price moves). Produces an "efficient
frontier" of execution strategies.

---

## M. Code / Project Terms

### DataFrame (Pandas)
A 2D table with named columns, like an Excel sheet. The standard
data structure in Python data science.

### Long Format
One row per (timestamp, level) combination. Wide format would have
one row per timestamp with columns `bid_price_0, bid_price_1, ...`.
Long format is easier to filter/group/aggregate in Pandas.

### CLI (Command-Line Interface)
A program you run from the terminal: `python main.py --ticks 5000`.

### Argparse
Python's built-in argument parser. Reads flags like `--ticks 5000`
from the command line.

### Module / Package
A Python file is a *module* (e.g., `data.py`). A folder of modules
with an `__init__.py` is a *package* (e.g., `orderbook/`).

### Dataclass
A Python decorator (`@dataclass`) that auto-generates boilerplate
methods (constructor, repr, equality) for a class that mostly holds
data.

### Seed (Random Seed)
A starting number for the random number generator. Same seed → same
"random" numbers → reproducible results. We default to `seed=42`.

### Vectorization
Using NumPy operations on whole arrays instead of Python loops.
~100x faster. Our synthetic generator uses `np.meshgrid` to build
all 5,000 × 20 = 100,000 rows in one shot, no Python loop.

---

## N. Asset Class Presets

| Asset         | `tick_size` | `init_mid` | `vol_per_tick` | `n_levels` | `base_qty` |
|---------------|-------------|------------|----------------|------------|------------|
| Crypto BTC    | 0.01        | 30,000     | 5e-4           | 50         | 0.5        |
| US equity     | 0.01        | 190        | 2e-4           | 20         | 100.0      |
| E-mini S&P    | 0.25        | 5,400      | 3e-4           | 10         | 5.0        |
| Generic       | 0.01        | 100        | 2e-3           | 20         | 1.0        |

### Crypto (e.g., BTC/USDT)
Bitcoin priced in US dollars. Tiny tick ($0.01), high volatility,
very deep books (50+ levels), trades 24/7.

### US Equity (e.g., AAPL)
Apple stock on NASDAQ/NYSE. $0.01 tick, lower volatility, ~20
levels deep, trades 9:30–16:00 Eastern. Regulated by Reg NMS.

### Futures (e.g., E-mini S&P 500 — "ES")
A contract on the S&P 500 index, traded on CME. $0.25 tick, intermediate volatility, ~10 levels deep.

---

## O. Reading the Charts

| Chart | What it shows | What to look for |
|---|---|---|
| 01_spread_timeseries.png | Mid price + spread over time | Stable spread = liquid; spikes = stress |
| 02_depth_profile.png | Size per level + cumulative | Convex cumulative curve = healthy book |
| 03_liquidity_heatmap.png | Size by (time, level) | Dark bands = thin liquidity periods |
| 04_book_imbalance.png | Bid-ask imbalance over time | Sustained + or - = directional pressure |
| 05_ofi.png | Rolling OFI vs mid price | OFI should lead price (positive corr) |
| 06_slippage_curve.png | Slippage vs order size | Curves up like √Q — square-root law |
| 07_ofi_backtest.png | Z-score + position + cumulative P&L | Upward-sloping P&L = signal works |

---

## P. References

**Microstructure:**
1. Cont, R., Kukanov, A., & Stoikov, S. (2014). *The price impact of
   order book imbalance.* SSRN. — OFI formula.
2. Almgren, R., Thum, C., Hauptmann, E., & Li, H. (2005). *Direct
   estimation of equity market impact.* Risk.
3. Gatheral, J. (2010). *No-dynamic-arbitrage and market impact.*
   Quantitative Finance.
4. Bouchaud, J.-P., Farmer, J. D., & Lillo, F. (2009). *How markets
   slowly digest changes in supply and demand.*

**Options:**
5. Black, F., & Scholes, M. (1973). *The pricing of options and
   corporate liabilities.* JPE.
6. Hull, J. *Options, Futures, and Other Derivatives.* The standard
   textbook.
7. Sinclair, E. *Volatility Trading.* Practitioner-focused.

**Market making:**
8. Avellaneda, M., & Stoikov, S. (2008). *High-frequency trading in a
   limit order book.* Quantitative Finance.
9. Cartea, Á., Jaikumar, S., & Penalva, J. (2015). *Algorithmic and
   High-Frequency Trading.* Cambridge.

---

## Q. Interview Cheat Sheet — Top 10 Questions

### 1. "Walk me through your order book project."
> "I built a Python package that parses Level-2 order book data and
> computes liquidity metrics — spread, depth, cumulative depth, and
> a liquidity heatmap. The interesting part is OFI: I implemented
> the Cont, Kukanov, Stoikov 2014 formula, which sums queue changes
> at the top levels and correlates them with short-horizon returns.
> On synthetic data with my realistic mode, I get correlation around
> 0.16; on real BTC/USDT data from Binance, it's in the documented
> 0.2-0.5 range. I also built a toy backtest that converts OFI to a
> z-score, goes long/short on ±1σ, holds 5 snapshots, charges 1 bp
> round-trip cost."

### 2. "What is OFI and why does it work?"
> "OFI sums queue changes at the top of the book. When the bid queue
> grows and the ask queue shrinks, that's net buying pressure —
> buyers are adding liquidity, sellers are pulling it. The mid price
> tends to drift up over the next few snapshots. It works because
> limit order placement is informative — informed traders prefer
> limit orders to avoid signaling."

### 3. "Why does impact grow with sqrt(size)?"
> "Empirically observed everywhere. The intuition: as you walk deeper
> into the book, each incremental unit hits a thinner marginal layer,
> so marginal cost per unit rises. Almgren et al. 2005 and Gatheral
> 2010 give the theory. The implication: doubling your order size
> increases cost by √2, not 2x."

### 4. "Explain delta and how a market maker uses it."
> "Delta is ∂(option price)/∂(underlying) — the option's directional
> exposure. A call with delta 0.5 moves $0.50 when the underlying
> moves $1. A market maker hedges delta by trading the underlying:
> long 0.5 delta → short 50 shares per contract → net delta zero.
> Now P&L no longer depends on small underlying moves; you're left
> with gamma, vega, theta exposure."

### 5. "What is adverse selection?"
> "When your resting quote gets filled, ask why the other side is
> trading. If they have information, you just got picked off — the
> price will move against you. Market makers measure this as the
> typical move against them right after a fill. Mitigation: tighten
> quotes in fast markets, use OFI-style signals to skew, cancel
> quickly on signals."

### 6. "What's the difference between historical and implied vol?"
> "Historical vol is backward-looking — computed from past returns.
> Implied vol is forward-looking — backed out of current option
> prices via Black-Scholes. When IV > HV, options are 'expensive.'
> Option traders bet on the gap."

### 7. "Why does the volatility skew exist in equities?"
> "Equity markets crash down, not up. Out-of-the-money puts are in
> heavy demand as portfolio insurance, bidding up their price, which
> raises their IV. Calls don't have the same demand, so call IV is
> lower. The skew is permanent in equity options."

### 8. "Walk me through gamma scalping."
> "Buy an ATM call — long gamma, long vega, short theta. Underlying
> drops, delta falls from +0.5 to +0.4, you buy shares to
> re-hedge. Underlying rises back, delta rises to +0.5, you sell
> those shares. You bought low, sold high. If realized vol > implied
> vol, re-hedge profits exceed theta decay."

### 9. "Explain put-call parity."
> "Portfolio A: long call + cash K discounted to T. Portfolio B:
> long put + long stock. At expiry both are worth max(S_T, K). No-
> arbitrage: same payoff, same price. So C + K e^{-rT} = P + S,
> or C - P = S - K e^{-rT}. Lets you price a put from a call."

### 10. "What's a Sharpe ratio you'd consider good?"
> "For a single strategy: 1-2 solid, 2-3 excellent, above 3 starts
> to look like overfitting. Multi-strategy portfolios can run higher
> because of diversification. The Medallion Fund reportedly runs
> above 5 — that's an outlier. My project's synthetic-data Sharpe
> of 12 is artificially inflated; I'd expect 1-3 on real data."
