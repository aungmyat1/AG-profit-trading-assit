---
name: risk-manager
description: Compute current R multiple and remaining risk/exposure for a claimed manual position, from its frozen initial risk distance. Use when asked how much R a trade is at, or before evaluating any partial/breakeven/exit rule.
---

# Risk Manager

Phase 6 (Trade Management, manual-entry only). Wraps `trade_management.risk`:
`current_r()`, `target_price()`, and `normalize_partial_close_volume()`.

## Scope

- `current_r(direction, entry_price, current_price, initial_r_distance)` -- always
  divides by the Claim's frozen `initial_r_distance` (captured once, at claim time from
  entry vs. original SL). Never recompute R from a moved (e.g. breakeven) stop.
- `target_price(...)` -- price for a given R multiple from entry (e.g. the 5R final
  target), from the same frozen distance.
- `normalize_partial_close_volume(current_volume, close_fraction, symbol_meta)` --
  broker-legal close/remaining volume for the 75% partial, rounded to the symbol's real
  `volume_step`/`volume_min`. Fails closed (`CLOSE_VOLUME_BELOW_MIN` /
  `ILLEGAL_REMAINDER_VOLUME`) rather than picking an ad hoc rounding.

## Guardrails

- **THIS SKILL DOES NOT OPEN TRADES.**
- Never enlarge risk or volume. A management action must only hold, reduce, or remove
  risk (spec Rule 6/7) -- if a computation would imply otherwise, report it as blocked,
  don't apply it.
- Report R math and volume normalization; the actual PARTIAL_CLOSE/MOVE_SL/CLOSE
  decision is `partial-profit-manager`/`breakeven-manager`/`exit-manager`'s job, not
  this skill's.
