"""Read-only MT5 acquisition implementing daily_evaluator.CandleProvider.

Only M15 is required by the frozen FX contract. H1/D1 presentation facts are
not acquisition requirements. No strategy or actionability decision lives here.
"""
from __future__ import annotations

import datetime as dt
import math
from typing import Any, Mapping, Protocol, Sequence

from mt5 import mt5_candles_readonly as adapter
from v1_tickets.daily_evaluator import CandleBundle
from v1_tickets.fx import M15, session_windows_utc


class CandleRangeReader(Protocol):
    def fetch_range(self, symbol: str, timeframe: str, start: dt.datetime,
                    end: dt.datetime) -> Sequence[adapter.CanonicalCandle]: ...

    def quote(self, symbol: str) -> tuple[float, float, dt.datetime]:
        """Return observed bid, ask and aware UTC observation time."""
        ...


class MT5ReadOnlyCandleAdapter:
    """Bind the accepted adapter functions to an injected read-only MT5 surface."""
    def __init__(self, mt5: Any, symbol_map: dict[str, str]):
        self._mt5 = mt5
        self._symbol_map = dict(symbol_map)

    def fetch_range(self, symbol, timeframe, start, end):
        return adapter.fetch_candles_range(
            self._mt5, symbol, timeframe, start, end, self._symbol_map)

    def quote(self, symbol):
        broker = adapter.resolve_broker_symbol(symbol, self._symbol_map)
        info = self._mt5.symbol_info(broker)
        if info is None:
            raise adapter.CandleAdapterError(adapter.SYMBOL_MAPPING_MISSING)
        try:
            return (float(info.bid), float(info.ask),
                    dt.datetime.fromtimestamp(info.time, dt.timezone.utc))
        except (AttributeError, TypeError, ValueError, OverflowError) as exc:
            raise adapter.CandleAdapterError(adapter.DATA_MISSING, "QUOTE_MISSING") from exc


class MT5CandleProvider:
    def __init__(self, reader: CandleRangeReader, *,
                 quote_snapshot: Mapping[str, tuple[float, float, dt.datetime] | None] | None = None):
        self._reader = reader
        self._quotes = dict(quote_snapshot) if quote_snapshot is not None else None

    def _window(self, symbol, start, end):
        """Require every requested closed bar, without filling or dropping gaps."""
        if end <= start:
            return []
        rows = list(self._reader.fetch_range(symbol, "M15", start, end - M15))
        expected = [start + i * M15 for i in range(int((end - start) / M15))]
        if [row.time for row in rows] != expected or any(row.symbol != symbol for row in rows):
            raise adapter.CandleAdapterError(adapter.DATA_MISSING, "M15_WINDOW_INCOMPLETE")
        return [row.to_engine_candle() for row in rows]

    def __call__(self, symbol, cycle, day, now) -> CandleBundle:
        if now.tzinfo is None:
            raise ValueError("evaluation time must be timezone-aware")
        now = now.astimezone(dt.timezone.utc)
        windows = session_windows_utc(day)[cycle]
        ref_start, ref_end = windows["ref"]
        trade_start, trade_end = windows["trade"]
        count = int((ref_end - ref_start) / M15)
        if now < ref_end:
            # Let the evaluator's existing REFERENCE_NOT_READY lifecycle gate decide.
            return CandleBundle([], count, [], None, None, None)
        reference = self._window(symbol, ref_start, ref_end)
        closed_end = min(now.replace(minute=now.minute // 15 * 15, second=0,
                                     microsecond=0), trade_end)
        post = self._window(symbol, trade_start, closed_end)
        quote = self._reader.quote(symbol) if self._quotes is None else self._quotes.get(symbol)
        if quote is None:
            raise adapter.CandleAdapterError(adapter.DATA_MISSING, "QUOTE_MISSING")
        bid, ask, observed = quote
        if (not all(math.isfinite(p) and p > 0 for p in (bid, ask)) or ask < bid
                or observed.tzinfo is None or not dt.timedelta(0) <= now - observed <= M15):
            raise adapter.CandleAdapterError(adapter.DATA_MISSING, "QUOTE_INVALID_OR_STALE")
        # Never substitute the last candle close for a current quote. Midpoint is
        # direction-independent; spread is the observed ask-bid, in price units.
        return CandleBundle(reference, count, post,
                            post[-1].time + M15 if post else ref_end,
                            ask - bid, (ask + bid) / 2)
