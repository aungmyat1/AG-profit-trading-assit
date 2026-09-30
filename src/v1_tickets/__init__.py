"""AG V1 Goal 1: informational session tickets, ARCHIVE_ONLY. A ticket is not a broker order.

- fx.py: ST_ASIAN_SWEEP_5R_V1@1.1.1 (frozen) for EURUSD, GBPUSD, USDJPY and XAUUSD on
  both frozen session pairs (ASIAN_LONDON, LONDON_NEWYORK).
- crypto.py: ST_LIQUIDITY_SWEEP_RETEST_V1@2.0.0 CRYPTO_PERP for BTCUSDT and ETHUSDT
  (ETHUSDT status SHADOW) in the frozen BTC daily report window. Data comes from Bybit
  public (primary) or Binance public (fallback), and the source is printed on every ticket.

Tickets are archived through the existing ticket_delivery journal (archive_cycle_decision).
No module here sends anything, sizes an order, or imports execution / order / position
paths.
"""
