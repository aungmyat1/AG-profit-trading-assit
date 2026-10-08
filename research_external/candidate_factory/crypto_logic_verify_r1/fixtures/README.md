# Fixtures — AG_CRYPTO_LOGIC_VERIFY_R1

All fixtures are SYNTHETIC/HAND-CONSTRUCTED. None are real VT Markets, Bybit, or Binance
market data. They exist solely to exercise specific, named scenarios deterministically;
they are never used as evidence of real-world signal count, profitability, or edge.

- `clean_breakout_long.csv` — D1 bars forming a flat 55-bar range then a decisive close
  above the range high (should trigger a LONG entry trigger under the frozen spec).
- `clean_breakout_short.csv` — mirror image, decisive close below the range low.
- `ranging_no_breakout.csv` — 80 bars oscillating inside a fixed band; no closes exceed
  the N=55 channel in either direction (should produce zero entries).
- `weekend_gap.csv` — Friday close then a large Monday-open gap (tests weekend-window
  exclusion and gap-driven stop/target behavior against the tick grid, not look-ahead).
- `expiry_no_fill.csv` — a valid trigger bar followed by price that never reaches the
  computed LIMIT entry before the declared expiry (tests that expiry always terminates
  the pending ticket, never leaves it open indefinitely).
