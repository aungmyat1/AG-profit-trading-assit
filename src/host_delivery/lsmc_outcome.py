"""LSMC alert expiry/outcome resolver (owner decisions 2026-10-07, P1). Measurement only.

After an OPPORTUNITY alert is sent, later CLOSED M5 bars are read to record what price did
relative to the alert's own levels. It is not a trade result, not a fill and not evidence of
edge; nothing here feeds back into detection, actionability or delivery.

Rules (first qualifying bar wins, scanned from the trigger bar close):
- TARGET_REACHED: bar high >= target (LONG) / low <= target (SHORT), a touch;
- STOP_TOUCHED: a C10 stop exists and the bar low <= stop (LONG) / high >= stop (SHORT);
- INVALIDATED: M5 close beyond the sweep extreme (the watch's own invalidation rule);
- AMBIGUOUS_SAME_BAR: the target and a stop/invalidation event occur on the same bar
  (OHLC cannot order them);
- EXPIRED: expires_at passed with none of the above. None = still open.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, Optional, Sequence

TARGET_REACHED = "TARGET_REACHED"
STOP_TOUCHED = "STOP_TOUCHED"
INVALIDATED = "INVALIDATED"
AMBIGUOUS_SAME_BAR = "AMBIGUOUS_SAME_BAR"
EXPIRED = "EXPIRED"
UTC = dt.timezone.utc
M5 = dt.timedelta(minutes=5)


def _ts(v: Any) -> Optional[dt.datetime]:
    if v is None:
        return None
    t = v if isinstance(v, dt.datetime) else dt.datetime.fromisoformat(str(v))
    return t.astimezone(UTC) if t.tzinfo else t.replace(tzinfo=UTC)


def resolve(alert: Dict[str, Any], m5: Sequence[Any], now: dt.datetime) -> Optional[Dict[str, Any]]:
    """`alert`: direction, target, sweep_extreme, stop_c10 (optional), trigger_bar_close_ts, expires_at.
    `m5`: candles with .time (open), .high, .low, .close. Only bars closed by `now` are read."""
    direction, target = alert.get("direction"), alert.get("target")
    extreme, stop = alert.get("sweep_extreme"), alert.get("stop_c10")
    start, expires, now = _ts(alert.get("trigger_bar_close_ts")), _ts(alert.get("expires_at")), _ts(now)
    if direction not in ("LONG", "SHORT") or start is None:
        return None
    long = direction == "LONG"
    for b in m5:
        close_at = _ts(b.time) + M5
        if _ts(b.time) < start or close_at > now:
            continue
        if expires is not None and close_at > expires:
            break
        hit = target is not None and (b.high >= target if long else b.low <= target)
        stopped = stop is not None and (b.low <= stop if long else b.high >= stop)
        invalid = extreme is not None and (b.close < extreme if long else b.close > extreme)
        event = (AMBIGUOUS_SAME_BAR if hit and (stopped or invalid) else TARGET_REACHED if hit
                 else STOP_TOUCHED if stopped else INVALIDATED if invalid else None)
        if event:
            return {"outcome": event, "event_bar_close_ts": close_at.isoformat(), "resolved_at": now.isoformat()}
    if expires is not None and now >= expires:
        return {"outcome": EXPIRED, "event_bar_close_ts": None, "resolved_at": now.isoformat()}
    return None
