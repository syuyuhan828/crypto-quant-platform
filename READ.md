"""
Pionex Futures Market Data Collector

Purpose:
- Pull crypto perpetual futures market data from Pionex public API.
- No API key required for these public market endpoints.
- Collects:
  1. Order book depth
  2. Recent taker-side trades
  3. Klines
  4. Book ticker
  5. Mark/index price and next funding rate
  6. Historical funding rates
  7. Open interest
  8. Simple imbalance features

Install:
    pip install requests pandas

Run:
    python pionex_market_data.py
"""