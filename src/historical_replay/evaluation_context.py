"""Immutable, strategy-neutral replay event boundary (TD-8E)."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional, Sequence, Tuple

from .candle_store import BoundReplaySeries, HistoricalCandleStore, HistoricalDataError, timeframe_duration
from .dataset_identity import ReplayDatasetIdentity

VISIBILITY_RULE_VERSION = "CLOSED_BAR_OPEN_PLUS_DURATION_LE_T_V1"


class ReplayEvaluationError(ValueError):
    pass


@dataclass(frozen=True)
class ReplayDataProvider:
    """Read-only view of a store bound to one historical clock and identities."""
    store: HistoricalCandleStore
    symbol: str
    as_of: datetime
    identities: Tuple[Tuple[str, ReplayDatasetIdentity], ...]
    bound_series: Tuple[BoundReplaySeries, ...]

    def _identity(self, timeframe: str) -> ReplayDatasetIdentity:
        bound = dict(self.identities).get(timeframe)
        current = self.store.dataset_identity(self.symbol, timeframe)
        if bound is None or current is None or current != bound:
            raise ReplayEvaluationError(f"replay series replaced or missing: {self.symbol} {timeframe}")
        return bound

    def _bound(self, timeframe: str) -> Tuple[Any, ...]:
        self._identity(timeframe)
        series = next((s for s in self.bound_series if s.timeframe == timeframe), None)
        if series is None:
            raise ReplayEvaluationError(f"missing bound replay series: {self.symbol} {timeframe}")
        return series.candles

    def candles(self, timeframe: str, *, effective_cutoff: Optional[datetime] = None,
                count: Optional[int] = None) -> Tuple[Any, ...]:
        self._identity(timeframe)
        cutoff = effective_cutoff or self.as_of
        if cutoff.tzinfo is None or cutoff.utcoffset() is None or cutoff > self.as_of:
            raise ReplayEvaluationError("effective cutoff must be aware and no later than replay T")
        series = self._bound(timeframe)
        if count is not None:
            duration = timeframe_duration(timeframe)
            visible = tuple(c for c in series if c.time + duration <= cutoff)
            if len(visible) < count:
                raise ReplayEvaluationError("bound replay series lacks requested history")
            return visible[-count:]
        duration = timeframe_duration(timeframe)
        return tuple(c for c in series if c.time + duration <= cutoff)

    def store_view(self) -> "BoundReplayStoreView":
        return BoundReplayStoreView(self)


class BoundReplayStoreView:
    """HistoricalCandleStore-compatible view backed only by the bound tuples."""
    def __init__(self, provider: ReplayDataProvider):
        self._provider = provider

    def dataset_identity(self, symbol: str, timeframe: str):
        if symbol != self._provider.symbol:
            return None
        return self._provider._identity(timeframe)

    def closed_candles(self, symbol: str, timeframe: str, as_of: datetime, count: int):
        if symbol != self._provider.symbol:
            raise HistoricalDataError("DATA_MISSING", f"unbound symbol {symbol}")
        if as_of > self._provider.as_of:
            raise HistoricalDataError("DATA_MISSING", "cutoff exceeds replay T")
        duration = timeframe_duration(timeframe)
        visible = [c for c in self._provider._bound(timeframe) if c.time + duration <= as_of]
        if len(visible) < count:
            raise HistoricalDataError("INSUFFICIENT_CANDLES", "bound replay series lacks requested history")
        return visible[-count:]

    def last_closed_price(self, symbol: str, timeframe: str, as_of: datetime):
        return self.closed_candles(symbol, timeframe, as_of, 1)[0].close

    def closed_candles_in_range(self, symbol: str, timeframe: str, start: datetime,
                                end: datetime, as_of: datetime):
        if symbol != self._provider.symbol or as_of > self._provider.as_of:
            raise HistoricalDataError("DATA_MISSING", "unbound replay query")
        duration = timeframe_duration(timeframe)
        visible = [c for c in self._provider._bound(timeframe)
                   if start <= c.time < end and c.time + duration <= as_of]
        if not visible:
            raise HistoricalDataError("DATA_MISSING", "no closed bound replay bars")
        return visible


@dataclass(frozen=True)
class ReplayEvaluationContext:
    symbol: str
    as_of: datetime
    timeframes: Tuple[str, ...]
    provider: ReplayDataProvider
    event_id: str
    visibility_rule_version: str = VISIBILITY_RULE_VERSION

    @classmethod
    def create(cls, store: HistoricalCandleStore, symbol: str, as_of: datetime,
               timeframes: Sequence[str] = ("H1", "M15"),
               *, visibility_rule_version: str = VISIBILITY_RULE_VERSION) -> "ReplayEvaluationContext":
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ReplayEvaluationError("as_of must be timezone-aware")
        requested = set(timeframes)
        if not requested or not requested.issubset({"H1", "M15", "M1"}):
            raise ReplayEvaluationError("supported replay timeframes are H1, M15, and M1")
        ordered = tuple(tf for tf in ("H1", "M15", "M1") if tf in requested)
        pairs = []
        series = []
        for tf in ordered:
            try:
                bound = store.bind_series(symbol, tf)
            except HistoricalDataError as exc:
                raise ReplayEvaluationError(str(exc)) from exc
            pairs.append((tf, bound.identity))
            series.append(bound)
        token = "|".join([symbol, as_of.astimezone(timezone.utc).isoformat(),
                           ",".join(ordered), visibility_rule_version,
                           *[identity.as_composed_identity_token() for _, identity in pairs]])
        event_id = "REPLAY-EVENT-" + hashlib.blake2b(token.encode(), digest_size=16).hexdigest()
        provider = ReplayDataProvider(store, symbol, as_of, tuple(pairs), tuple(series))
        return cls(symbol, as_of, ordered, provider, event_id, visibility_rule_version)

    def candles(self, timeframe: str, **kwargs) -> Tuple[Any, ...]:
        return self.provider.candles(timeframe, **kwargs)

    def series_identity(self, timeframe: str) -> ReplayDatasetIdentity:
        return self.provider._identity(timeframe)

    @property
    def series_identities(self) -> Dict[str, ReplayDatasetIdentity]:
        return dict(self.provider.identities)

    def session_fact(self, session_name: str, session_date: Optional[date] = None):
        """Return the existing canonical session authority at this exact T."""
        from assistant.market_data import session_snapshot
        from .data_source_patch import historical_data_context
        with historical_data_context(self.provider.store_view(), self.as_of):
            return session_snapshot(self.symbol, session_name, session_date)
