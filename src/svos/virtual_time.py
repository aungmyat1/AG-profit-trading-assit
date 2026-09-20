"""Deterministic, historical-only VD clock and incremental TD-8E feed.

This module schedules candidate close instants; ReplayEvaluationContext remains the
sole authority for which bound candles are visible at each virtual T.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional, Tuple

from historical_replay.candle_store import HistoricalCandleStore, timeframe_duration
from historical_replay.evaluation_context import ReplayEvaluationContext


class VirtualTimeError(ValueError):
    """Invalid clock, missing historical series, or violated feed invariant."""


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise VirtualTimeError("virtual time and candle timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def _fingerprint(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass
class VirtualClock:
    start: datetime
    end: datetime
    T: datetime = field(init=False)
    ended: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self.start, self.end = _utc(self.start), _utc(self.end)
        if self.end < self.start:
            raise VirtualTimeError("end precedes start")
        self.T = self.start

    def advance_to(self, at: datetime) -> datetime:
        at = _utc(at)
        if self.ended or at < self.T or at > self.end:
            raise VirtualTimeError("clock advance outside monotone open interval")
        self.T = at
        return self.T

    def finish(self) -> datetime:
        self.T = self.end
        self.ended = True
        return self.T


@dataclass(frozen=True)
class VirtualMarketEvent:
    at: datetime
    symbol: str
    timeframe: str
    source_id: str
    dataset_id: str
    dataset_fingerprint: str
    sequence: int
    candle: object
    payload_id: str
    event_id: str
    replay_event_id: str


class VirtualMarketFeed:
    """Historical store only; no live adapter, broker, strategy, or P&L dependency."""

    def __init__(self, store: HistoricalCandleStore, symbol: str,
                 timeframes: Tuple[str, ...], clock: VirtualClock):
        if not isinstance(store, HistoricalCandleStore):
            raise VirtualTimeError("feed requires HistoricalCandleStore")
        if not symbol or not timeframes or len(set(timeframes)) != len(timeframes):
            raise VirtualTimeError("symbol and unique timeframes required")
        if not set(timeframes).issubset({"M1", "M15", "H1"}):
            raise VirtualTimeError("only TD-8E M1/M15/H1 feed timeframes are supported")
        self.store, self.symbol, self.clock = store, symbol, clock
        self.timeframes = tuple(tf for tf in ("H1", "M15", "M1") if tf in timeframes)
        # Bind once through TD-8E. A missing series fails before any event is emitted.
        initial = ReplayEvaluationContext.create(store, symbol, clock.start, self.timeframes)
        self._identities = tuple(initial.provider.identities)
        self._schedule = tuple(sorted({
            _utc(c.time) + timeframe_duration(tf)
            for series in initial.provider.bound_series for tf in (series.timeframe,)
            for c in series.candles
            if clock.start <= _utc(c.time) + timeframe_duration(tf) <= clock.end
        }))
        self._cursor = 0
        self._seen = {
            tf: sum(c.time + timeframe_duration(tf) < clock.start
                    for c in initial.candles(tf))
            for tf in self.timeframes
        }
        self._events: list[VirtualMarketEvent] = []
        self._finished = False

    @property
    def status(self) -> str:
        return "END_OF_DATA" if self._finished else "ACTIVE"

    @property
    def events(self) -> Tuple[VirtualMarketEvent, ...]:
        return tuple(self._events)

    @property
    def sequence_id(self) -> str:
        # Full lineage identity differs when future-only dataset content changes.
        return _fingerprint([e.event_id for e in self._events])

    @property
    def semantic_sequence_id(self) -> str:
        # Visible payload semantics remain equal under future-only mutation.
        return _fingerprint([e.payload_id for e in self._events])

    def step(self) -> Tuple[VirtualMarketEvent, ...]:
        if self._finished:
            return ()
        if self._cursor == len(self._schedule):
            self.clock.finish()
            self._finished = True
            return ()
        at = self.clock.advance_to(self._schedule[self._cursor])
        self._cursor += 1
        context = ReplayEvaluationContext.create(self.store, self.symbol, at, self.timeframes)
        if tuple(context.provider.identities) != self._identities:
            raise VirtualTimeError("bound replay dataset identity changed")
        emitted = []
        for tf in self.timeframes:
            visible = context.candles(tf)  # TD-8E performs admission.
            old = self._seen[tf]
            if len(visible) < old:
                raise VirtualTimeError("admitted series regressed")
            identity = context.series_identity(tf)
            for sequence, candle in enumerate(visible[old:], start=old):
                payload = {"symbol": self.symbol, "timeframe": tf,
                           "time": _utc(candle.time).isoformat(), "open": candle.open,
                           "high": candle.high, "low": candle.low,
                           "close": candle.close, "volume": candle.volume}
                payload_id = _fingerprint(payload)
                event_id = _fingerprint({"payload": payload_id,
                                         "dataset": identity.as_composed_identity_token()})
                emitted.append(VirtualMarketEvent(
                    at, self.symbol, tf, identity.source, identity.dataset_id,
                    identity.fingerprint, sequence, candle, payload_id, event_id,
                    context.event_id))
            self._seen[tf] = len(visible)
        emitted.sort(key=lambda e: (e.at, e.source_id, e.sequence, e.event_id))
        self._events.extend(emitted)
        return tuple(emitted)

    def run(self, mode: str = "maximum", *, sleep: Optional[Callable[[float], None]] = None,
            acceleration: float = 60.0) -> Tuple[VirtualMarketEvent, ...]:
        if mode not in {"step", "accelerated", "maximum"}:
            raise VirtualTimeError("unsupported playback mode")
        if mode == "accelerated" and acceleration <= 0:
            raise VirtualTimeError("acceleration must be positive")
        while self.status != "END_OF_DATA":
            before = self.clock.T
            self.step()
            if mode == "accelerated" and sleep is not None and not self._finished:
                sleep((self.clock.T - before).total_seconds() / acceleration)
        return self.events
