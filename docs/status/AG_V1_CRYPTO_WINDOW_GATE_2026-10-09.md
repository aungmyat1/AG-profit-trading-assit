---
class: evidence
state: DESIGN
owner_reviewed: null
review_by: null
---
# Crypto V3 window preflight — 2026-10-09

## Change

`scripts/host/live_candles_smoke.py --mode crypto` evaluates the selected MT5 crypto
configuration's existing window before acquiring `single_instance` or `mt5_access_lock` and
before `import_mt5` / `mt5_initialize`. Outside the window the runner logs
`CRYPTO OUTSIDE_WINDOW (<window status>)` and returns 0. This is an orchestration gate only;
the config, strategy, thresholds, and ticket evaluator are unchanged. Non-MT5 public-feed V1
behavior is unchanged.

V3 weekday windows continue to use `America/New_York` zoneinfo; V3 weekend hours continue to
use UTC. DST evidence covers the 2026-10-25 London clock change (no impact on the New York
weekday window or fixed-UTC weekend window) and the 2026-11-01 New York fall-back (the next
weekday's 09:00 New York start is 14:00 UTC).

## Verification

- `pytest -q tests/test_host_go_live_kit.py tests/test_v1_tickets.py` — 128 passed, 1 skipped.
- The outside-window main-path test asserts no single-instance lock, MT5 lock, MT5 import, or
  initialize call; the inside-window path retains the existing lock / attach / evaluator order.
- Measured real process run: `python scripts/host/live_candles_smoke.py --mode crypto` at
  `2026-10-08T18:58:00Z` (`2026-10-09 01:28 MMT`) printed
  `CRYPTO OUTSIDE_WINDOW (AFTER_WINDOW)` and completed in **0.496 s** wall time. The preflight
  returned before MT5 import/initialization or either lock. This was a Linux web-runner check,
  not a Windows host or MT5 live verification.
- No order or account mutation occurred. No strategy, threshold, authorization, or broker
  configuration changed.
