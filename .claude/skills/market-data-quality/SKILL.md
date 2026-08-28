---
name: market-data-quality
description: Audit, document, and prepare historical market data before trading research or backtesting. Use for OHLCV, quotes, trades, fundamentals, rates, funding, open interest, corporate actions, missing bars, duplicate timestamps, timezone/session problems, point-in-time integrity, or suspected bad data. Do not use to invent or silently repair observations.
---

# Market Data Quality

Treat data validation as part of the research result, not as housekeeping.

## Required inputs

Ask for or infer, then explicitly record:

- instrument identifiers and asset class;
- source/vendor and retrieval date;
- bar or event frequency;
- timestamp meaning: bar open, bar close, event time, or publication time;
- timezone, trading session, and holiday calendar;
- raw versus adjusted prices;
- expected columns, units, and missing-value encoding.

If any item is unknown, label it unknown rather than guessing.

## Workflow

1. Preserve the raw input. Write cleaned data to a new path.
2. Inspect schema, data types, row count, date range, and sampling frequency.
3. Detect duplicate, unsorted, missing, or impossible timestamps.
4. Check numeric integrity:
   - finite prices and sizes;
   - nonnegative volume;
   - `high >= max(open, close)` and `low <= min(open, close)`;
   - `high >= low`;
   - suspicious zero or negative prices;
   - extreme returns and stale runs.
5. Compare observed gaps with the correct session/calendar. Do not label weekends as gaps for weekday markets or ignore outages in 24/7 markets.
6. Check asset-specific hazards by consulting `../multi-asset-conventions/SKILL.md` when available.
7. Check temporal integrity:
   - release/publication timestamps for fundamentals and macro data;
   - survivorship and delisting coverage;
   - split/dividend adjustment policy;
   - futures contract mapping and roll rules;
   - crypto funding and exchange outage handling.
8. Produce a data-audit report with severity, affected rows/ranges, proposed action, and unresolved risks.
9. Stop before backtesting if high-severity issues could change signals or P&L.

## Cleaning policy

- Never silently drop anomalies.
- Never forward-fill tradable prices across a closure/outage without a documented reason.
- Do not fill future-known values backward.
- Keep a machine-readable change log for every transformation.
- When correction is uncertain, retain the raw value, flag it, and run sensitivity variants.

## Output contract

Return:

1. **Data contract** — columns, units, timestamps, adjustment and calendar policy.
2. **Audit summary** — pass/warn/fail counts.
3. **Issue table** — severity, location, evidence, and action.
4. **Research limitations** — biases or unavailable fields.
5. **Go/no-go recommendation** for backtesting.

For OHLCV CSV files, prefer running `scripts/audit_ohlcv.py` and include its output rather than relying only on visual inspection.
