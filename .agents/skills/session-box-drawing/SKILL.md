---
name: session-box-drawing
description: Draw or validate Asian, London, or other fixed trading-session boxes from completed intraday candles. Use for chart boxes, frozen session levels, or session-range inputs; do not use strategy signals or future candles to alter box geometry.
---

# Session Box Drawing

Construct session boxes as immutable data objects before adding strategy annotations.

## Required inputs

- requested session start and end, with timezone;
- candle timeframe, normally M15;
- candle-open timestamps and OHLC values;
- expected candle count;
- whether the optional midpoint should be displayed.

Do not infer an unspecified session schedule from Trend/Range, Sweep, entry, or outcome data. If the requested window or timezone is ambiguous, obtain or report the missing contract.

For the standard Asian / London AM / New York AM boxes, the schedule is `config/canonical_sessions.yaml` (`CANONICAL_SESSION_WINDOWS_V1`, fixed UTC, half-open, no DST) — read it via `session_clock.get_session_bounds(date, name)` rather than hardcoding hours here or in any strategy-specific skill. Only use a different window when the caller explicitly supplies one for a non-canonical or historical box.

## Authoritative workflow

1. Use completed M15 candles only. Select candles by the half-open rule:

   `session_start <= candle_open < session_end`

2. Validate before calculating or drawing:

   - selected count equals the expected candle count;
   - timestamps are unique;
   - timestamps form the complete contiguous M15 schedule for the requested window;
   - every candle is complete;
   - OHLC values are finite and satisfy `Low <= Open, Close <= High` and `Low <= High`.

3. On validation success, calculate:

   ```text
   box_top    = maximum High
   box_bottom = minimum Low
   midpoint   = (box_top + box_bottom) / 2
   ```

4. Draw the rectangle from `session_start` to `session_end`, with its top at `box_top` and bottom at `box_bottom`. Draw the midpoint only when requested.

5. Freeze the box when the session closes. Preserve the source window, candle timestamps, bar count, top, bottom, and midpoint as immutable evidence.

6. Later candles may be displayed beside the box or tested against its frozen levels, but they must never change its geometry.

## Fail-closed result

If the session data is incomplete, duplicated, mistimed, still forming, or otherwise invalid:

```text
status = INVALID_SESSION_DATA
draw_box = false
```

Return the specific validation reason and do not draw a partial or estimated rectangle.

## Separation rule

Session box drawing uses only candles inside the requested session window. Trend/Range classification, Sweep detection, bias, entry rules, risk levels, trade results, and all future price action are downstream concerns and have no authority over box construction.
