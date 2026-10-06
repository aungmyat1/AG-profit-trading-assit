"""AG V1 Goal 1: informational session tickets, ARCHIVE_ONLY. A ticket is not a broker order.

- fx.py: ST_ASIAN_SWEEP_5R_V1@1.1.1 (frozen) for EURUSD, GBPUSD, USDJPY and XAUUSD on
  both frozen session pairs (ASIAN_LONDON, LONDON_NEWYORK).
- crypto.py: ST_LIQUIDITY_SWEEP_RETEST_V1@2.0.0 CRYPTO_PERP for BTCUSDT and ETHUSDT
  (ETHUSDT status SHADOW) in the frozen BTC daily report window. Data comes from Bybit
  public (primary) or Binance public (fallback), and the source is printed on every ticket.

Tickets are archived through the existing ticket_delivery journal (archive_cycle_decision).
No module here sends anything or imports execution / order / position paths.

Manual Trade Ticket V1 (authority, scan_record, logic_gate, manual_ticket, owner_decision,
outcome, manual_report): MANUAL tickets for the owner to act on by hand. manual_ticket
shows an informational lot size from the owner's risk % (broker-free sizing_math); it is
never sent anywhere as an order. See docs/status/AG_MANUAL_TRADE_TICKET_V1_STATUS.md.
"""
