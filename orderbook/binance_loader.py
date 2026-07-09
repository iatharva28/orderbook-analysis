"""Real-data capture: Binance Spot WebSocket L2 depth stream.

Binance exposes a free, public WebSocket that pushes partial book
snapshots at 100ms or 1000ms cadence. Documentation:
    https://binance-docs.github.io/apidocs/spot/en/#partial-book-depth-streams

Stream name: <symbol>@depth<levels>@<speed>
    e.g. btcusdt@depth20@100ms -> top-20 levels, 10 snapshots/sec

This module:
    1. Connects to the WebSocket
    2. Captures N snapshots (or runs for T seconds)
    3. Normalises them into the long-format schema used by the rest
       of the package (timestamp, level, bid_price, bid_qty, ask_price,
       ask_qty, mid, spread)
    4. Saves to CSV

Usage (CLI):
    python -m orderbook.binance_loader \\
        --symbol btcusdt --levels 20 --seconds 60 \\
        --out real_l2_btcusdt.csv

Usage (Python):
    from orderbook.binance_loader import capture_binance_l2
    df = capture_binance_l2(symbol='btcusdt', levels=20, seconds=60)
    df.to_csv('real_l2.csv', index=False)

Dependencies (install separately — not in requirements.txt by default):
    pip install websocket-client

Note: This module is NOT exercised by the unit tests or the notebook
because it requires live internet access. It's provided as ready-to-run
code for the user to execute locally.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Optional

import pandas as pd


BINANCE_WS_BASE = "wss://stream.binance.com:9443/ws"


def _normalize_snapshot(raw: dict, ts_counter: int) -> list[dict]:
    """Convert a Binance depth message to long-format rows.

    Binance message format (partial book depth stream):
    {
      "lastUpdateId": 12345,
      "bids": [["100.0", "1.5"], ["99.9", "2.0"], ...],   # [price, qty]
      "asks": [["100.1", "0.8"], ["100.2", "1.2"], ...],
      "E": 1697000000000   # event time (ms)
    }
    """
    bids = raw.get("bids", []) or raw.get("b", [])
    asks = raw.get("asks", []) or raw.get("a", [])
    n = min(len(bids), len(asks))

    rows = []
    for level in range(n):
        bid_price = float(bids[level][0])
        bid_qty = float(bids[level][1])
        ask_price = float(asks[level][0])
        ask_qty = float(asks[level][1])
        rows.append({
            "timestamp": ts_counter,
            "level": level,
            "bid_price": bid_price,
            "bid_qty": bid_qty,
            "ask_price": ask_price,
            "ask_qty": ask_qty,
        })
    return rows


def capture_binance_l2(
    symbol: str = "btcusdt",
    levels: int = 20,
    seconds: int = 60,
    speed: str = "100ms",
    out_path: Optional[str] = None,
) -> pd.DataFrame:
    """Capture real L2 snapshots from Binance and return as a DataFrame.

    Parameters
    ----------
    symbol : lower-case trading pair, e.g. 'btcusdt', 'ethusdt'
    levels : 5, 10, or 20 (Binance supports these)
    seconds : capture duration
    speed : '100ms' (10 Hz) or '1000ms' (1 Hz)
    out_path : if given, also write CSV

    Returns
    -------
    Long-format L2 DataFrame with mid and spread attached.
    """
    try:
        import websocket  # type: ignore
    except ImportError as e:
        raise ImportError(
            "This module requires `websocket-client`. Install it with:\n"
            "    pip install websocket-client"
        ) from e

    if levels not in (5, 10, 20):
        raise ValueError("Binance supports levels = 5, 10, or 20 only")
    if speed not in ("100ms", "1000ms"):
        raise ValueError("speed must be '100ms' or '1000ms'")

    stream = f"{symbol}@depth{levels}@{speed}"
    url = f"{BINANCE_WS_BASE}/{stream}"

    all_rows: list[dict] = []
    ts_counter = 0
    start_time = time.time()
    done = [False]  # mutable holder for the closure

    print(f"Connecting to {url}")
    print(f"Capturing for {seconds}s ...")

    def on_message(ws, message):
        nonlocal ts_counter
        if done[0]:
            return
        try:
            raw = json.loads(message)
        except json.JSONDecodeError:
            return
        rows = _normalize_snapshot(raw, ts_counter)
        if rows:
            all_rows.extend(rows)
            ts_counter += 1
        if time.time() - start_time > seconds:
            done[0] = True
            ws.close()

    def on_error(ws, error):
        print(f"WebSocket error: {error}")

    def on_close(ws, close_status, msg):
        print(f"WebSocket closed. Captured {ts_counter} snapshots.")

    def on_open(ws):
        print(f"WebSocket open. Streaming {stream} ...")

    ws = websocket.WebSocketApp(
        url,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )
    ws.run_forever()

    if not all_rows:
        raise RuntimeError("No data captured. Check your internet connection.")

    df = pd.DataFrame(all_rows)
    snap = df.groupby("timestamp").agg(
        best_bid=("bid_price", "first"),
        best_ask=("ask_price", "first"),
    )
    snap["mid"] = (snap["best_bid"] + snap["best_ask"]) / 2
    snap["spread"] = snap["best_ask"] - snap["best_bid"]
    df = df.merge(snap[["mid", "spread"]], on="timestamp", how="left")

    print(f"  -> {len(df):,} rows, {df['timestamp'].nunique():,} snapshots, "
          f"{df['level'].nunique()} levels per side")

    if out_path:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out_path, index=False)
        print(f"  -> wrote {out_path}")
    return df


def main():
    p = argparse.ArgumentParser(
        description="Capture real L2 data from Binance WebSocket",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--symbol", type=str, default="btcusdt",
                   help="Lower-case trading pair (e.g. btcusdt, ethusdt)")
    p.add_argument("--levels", type=int, default=20, choices=[5, 10, 20],
                   help="Number of depth levels per side")
    p.add_argument("--seconds", type=int, default=60,
                   help="Capture duration in seconds")
    p.add_argument("--speed", type=str, default="100ms",
                   choices=["100ms", "1000ms"],
                   help="Snapshot cadence")
    p.add_argument("--out", type=str, default="real_l2.csv",
                   help="Output CSV path")
    args = p.parse_args()

    capture_binance_l2(
        symbol=args.symbol,
        levels=args.levels,
        seconds=args.seconds,
        speed=args.speed,
        out_path=args.out,
    )


if __name__ == "__main__":
    main()
