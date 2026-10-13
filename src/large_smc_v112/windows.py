"""Candidate expiry uses the committed crypto ticket windows; no scheduler change."""
import datetime as dt
from typing import List
from zoneinfo import ZoneInfo


def _crypto_session_end(at: dt.datetime, config: dict) -> dt.datetime:
    """Candidate-only expiry from the configured crypto ticket windows; no runtime wiring."""
    window = config.get("window") or {}
    if window.get("kind") == "MULTI":
        windows = list(window.get("windows") or [])
    elif window.get("kind") == "LOCAL_WEEKDAY":
        windows = [window]
    else:
        raise ValueError(f"unsupported crypto window kind {window.get('kind')!r}")
    windows = [w for w in windows if isinstance(w, dict) and w.get("enabled", True) is not False]
    if not windows:
        raise ValueError("no enabled crypto ticket windows")

    utc = at.astimezone(dt.timezone.utc)
    candidates: List[dt.datetime] = []
    for spec in windows:
        zone = ZoneInfo(spec["timezone"])
        start = dt.time(*map(int, str(spec["start"]).split(":")))
        end = dt.time(*map(int, str(spec["end"]).split(":")))
        weekdays = {int(day) for day in spec["weekdays"]}
        if not weekdays or not weekdays <= set(range(1, 8)) or start == end:
            raise ValueError("invalid crypto window weekdays or duration")
        local_date = utc.astimezone(zone).date()
        for day_offset in range(-1, 15):
            start_date = local_date + dt.timedelta(days=day_offset)
            if start_date.isoweekday() not in weekdays:
                continue
            end_date = start_date + dt.timedelta(days=1 if end <= start else 0)
            start_at = dt.datetime.combine(start_date, start, tzinfo=zone)
            end_at = dt.datetime.combine(end_date, end, tzinfo=zone)
            if start_at <= utc < end_at:
                return end_at.astimezone(dt.timezone.utc)
            if end_at > utc:
                candidates.append(end_at.astimezone(dt.timezone.utc))
    if not candidates:
        raise ValueError("no future crypto ticket-window end")
    return min(candidates)
