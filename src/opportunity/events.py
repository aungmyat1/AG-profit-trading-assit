"""MarketEvent construction (P9).

Thin, additive wrapper around strategy_contract.market_snapshot.MarketSnapshot,
which remains the sole market-truth authority. This module never fetches data
itself -- it only builds a MarketEvent from an already-constructed MarketSnapshot
(or, for REPLAY/SYNTHETIC callers with no MarketSnapshot-producing feed, from
explicit already-closed values passed in verbatim).
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from .contracts import MarketEvent

EVENT_TYPE_BAR_CLOSE = "BAR_CLOSE"


def _event_id(symbol: str, timeframe: str, source: str, mode: str, bar_close_time: datetime) -> str:
    """Deterministic: same closed bar + same authoritative source always resolves
    to the same event_id, regardless of how many times it is (re)observed."""
    payload = "|".join(
        [
            symbol,
            timeframe,
            source,
            mode,
            bar_close_time.astimezone(timezone.utc).isoformat(),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def from_market_snapshot(
    snapshot,
    *,
    market: str,
    venue: str | None = None,
    sequence_id: int | None = None,
) -> MarketEvent:
    """Build a MarketEvent from an existing MarketSnapshot. `snapshot` must be a
    strategy_contract.market_snapshot.MarketSnapshot (duck-typed here to avoid a
    hard import-time dependency cycle; callers pass the real object)."""
    if not snapshot.is_closed:
        raise ValueError(
            "MarketEvent can only be built from a closed bar -- future/forming "
            "data at T is not representable"
        )
    event_id = _event_id(
        snapshot.symbol,
        snapshot.timeframe,
        snapshot.source,
        snapshot.market_data_mode,
        snapshot.bar_close_time,
    )
    return MarketEvent(
        event_id=event_id,
        event_type=EVENT_TYPE_BAR_CLOSE,
        symbol=snapshot.symbol,
        market=market,
        venue=venue,
        timeframe=snapshot.timeframe,
        bar_open_time=snapshot.bar_open_time,
        bar_close_time=snapshot.bar_close_time,
        market_data_asof=snapshot.market_data_asof,
        market_data_mode=snapshot.market_data_mode,
        snapshot_fingerprint=snapshot.fingerprint,
        source=snapshot.source,
        sequence_id=sequence_id,
    )
