"""TD-8D: canonical replay MarketSnapshot binding.

This module is a read-only bridge below strategy interpretation. It selects one closed
candle at caller time T, binds it to TD-8's dataset identity, and attaches the shared
TD-8C session facts. Consumers receive the same immutable bridge object; this module
does not import strategy engines, proposal, risk, execution, or intelligence code.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Callable, Mapping, Optional, Sequence, Tuple, TypeVar

from assistant.market_data import SessionSnapshot, session_snapshot
from historical_replay import HistoricalCandleStore, historical_data_context
from historical_replay.candle_store import HistoricalDataError
from strategy_engine.session import Candle

from .market_snapshot import MarketSnapshot, from_replay_candle

TConsumer = TypeVar("TConsumer")


class ReplayBridgeError(ValueError):
    """Fail-closed replay bridge validation error."""


@dataclass(frozen=True)
class ReplayMarketSnapshot:
    snapshot: MarketSnapshot
    dataset_identity: str
    as_of_time: datetime
    session_facts: Tuple[SessionSnapshot, ...]

    def __post_init__(self) -> None:
        if self.snapshot.market_data_mode != "REPLAY":
            raise ReplayBridgeError("replay bridge requires a REPLAY MarketSnapshot")
        if self.snapshot.market_data_asof > self.as_of_time:
            raise ReplayBridgeError("snapshot bar is not closed at the replay evaluation time")
        if not self.dataset_identity or not self.as_of_time.tzinfo:
            raise ReplayBridgeError("dataset identity and timezone-aware as_of_time are required")

    @property
    def identity(self) -> str:
        return f"{self.dataset_identity}|{self.snapshot.symbol}|{self.snapshot.timeframe}|{self.as_of_time.astimezone(timezone.utc).isoformat()}|{self.snapshot.fingerprint}"

    def deliver(self, consumers: Mapping[str, Callable[["ReplayMarketSnapshot"], TConsumer]]) -> Tuple[TConsumer, ...]:
        """Deliver this exact immutable object to each independent consumer."""
        return tuple(consumer(self) for consumer in consumers.values())


def build_replay_market_snapshot(
    symbol: str,
    timeframe: str,
    replay_store: HistoricalCandleStore,
    as_of_time: datetime,
    *,
    session_date: Optional[date] = None,
    session_names: Sequence[str] = ("asian", "london_am", "new_york_am"),
) -> ReplayMarketSnapshot:
    """Build one canonical replay snapshot and shared session facts at T."""
    if as_of_time.tzinfo is None or as_of_time.utcoffset() is None:
        raise ReplayBridgeError("as_of_time must be timezone-aware UTC")
    identity = replay_store.dataset_identity(symbol, timeframe)
    if identity is None:
        raise ReplayBridgeError(f"missing replay dataset identity for {symbol} {timeframe}")
    try:
        with historical_data_context(replay_store, as_of_time):
            candle = replay_store.closed_candles(symbol, timeframe, as_of_time, 1)[0]
            facts = tuple(session_snapshot(symbol, name, session_date) for name in session_names)
    except HistoricalDataError as exc:
        raise ReplayBridgeError(str(exc)) from exc
    if candle.time + _duration_minutes(timeframe) > as_of_time:
        raise ReplayBridgeError("forming candle cannot enter canonical replay snapshot")
    source = identity.as_composed_identity_token()
    snapshot = from_replay_candle(symbol, timeframe, candle, source=source, retrieved_at=as_of_time)
    return ReplayMarketSnapshot(snapshot=snapshot, dataset_identity=source, as_of_time=as_of_time, session_facts=facts)


def _duration_minutes(timeframe: str):
    from datetime import timedelta
    values = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440, "W1": 10080}
    if timeframe not in values:
        raise ReplayBridgeError(f"unsupported timeframe {timeframe!r}")
    return timedelta(minutes=values[timeframe])
