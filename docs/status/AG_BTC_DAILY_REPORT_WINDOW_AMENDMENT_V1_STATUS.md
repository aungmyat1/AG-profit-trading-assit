# AG BTC Daily Report Window Amendment V1 — Status

**Date:** 2026-09-06  
**Classification:** `REPORT_WINDOW_AMENDED_NOT_STARTED`

## Owner decision

The owner requested that the BTC evidence report move from the early-morning Myanmar
window into the 13:00-22:00 MMT availability range. The selected window is:

```text
Myanmar report window = 13:00-13:15 MMT
UTC report window     = 06:30-06:45 UTC
suggested run time    = 13:05 MMT / 06:35 UTC
observation date      = preceding UTC calendar date
```

This is the earliest clean slot in the requested range and ends 15 minutes before the
13:30 MMT Asian-to-London FX decision window. The preceding UTC observation day has
already been closed for 6.5 hours at window open, so the existing complete 24 H1 + 288
M5 data audit remains applicable.

## Scope and invariants

- Prospective reporting-time amendment only; no prior evidence is reclassified.
- BTC strategy timing, entry, stop, target, risk, and decision semantics are unchanged.
- Bybit access remains public/read-only.
- Crypto execution remains unimplemented and disabled.
- The observation campaign remains authorized but not started at 0/30.
- The qualification baseline is marked `PENDING_REPORT_WINDOW_AMENDMENT_COMMIT`; the
  amendment must be committed and its hash pinned before the first counted observation.
- The Task Scheduler installer default was updated as a template only; no task was
  installed or enabled.
- The report window remains half-open: 06:30 UTC is included and 06:45 UTC is excluded.

## Verification

Focused boundary and CLI tests cover before-window, inclusive start, in-window, and
exclusive end behavior: `23 passed` from
`python -m pytest -q tests/test_btc_daily_report.py tests/test_btc_daily_cli.py`.
Historical dated documents describing the prior 00:05-00:15
UTC window remain preserved as historical evidence; this document supersedes that
window prospectively.
