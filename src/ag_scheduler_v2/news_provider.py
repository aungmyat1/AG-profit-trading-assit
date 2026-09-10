"""Provider-agnostic economic calendar abstraction (spec section 12). No hard-coded
scraping dependency -- callers depend only on EconomicCalendarProvider's interface. A
provider failure must surface as UNAVAILABLE and never be silently treated as NO_NEWS.
"""
from __future__ import annotations

import abc
import datetime as dt
from dataclasses import dataclass
from typing import Optional, Sequence

STATUS_OK = "OK"
STATUS_UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class EconomicEvent:
    event_id: str
    currency: str
    event_time_utc: dt.datetime
    impact: str  # e.g. HIGH/MEDIUM/LOW, provider-defined vocabulary
    event_name: str
    provider: str
    retrieved_at_utc: dt.datetime


class EconomicCalendarProvider(abc.ABC):
    """Any real provider (a paid API, a signed internal feed, etc.) implements this.
    The scheduler never imports a concrete provider directly -- only this interface."""

    @abc.abstractmethod
    def fetch_events(
        self, *, currencies: Sequence[str], window_start_utc: dt.datetime, window_end_utc: dt.datetime
    ) -> Sequence[EconomicEvent]:
        """Raise on failure -- do not return an empty list to mean 'unavailable'. An
        empty list must mean 'the provider succeeded and found nothing', which is a
        materially different fact from 'the provider could not be reached'."""
        raise NotImplementedError


class EconomicProviderFailure(RuntimeError):
    """Raised by a provider implementation when the calendar cannot be fetched."""


@dataclass(frozen=True)
class CalendarFetchResult:
    status: str  # STATUS_OK | STATUS_UNAVAILABLE
    events: tuple
    provider: Optional[str]
    retrieved_at_utc: dt.datetime
    error_detail: Optional[str] = None


def fetch_relevant_events(
    provider: EconomicCalendarProvider,
    *,
    currencies: Sequence[str],
    window_start_utc: dt.datetime,
    window_end_utc: dt.datetime,
    now_utc: dt.datetime,
) -> CalendarFetchResult:
    """Wraps a provider call, converting any failure into an explicit UNAVAILABLE
    result rather than letting it propagate as an unhandled exception or, worse, get
    swallowed into an empty NO_NEWS-looking list."""
    try:
        events = tuple(provider.fetch_events(currencies=currencies, window_start_utc=window_start_utc, window_end_utc=window_end_utc))
    except EconomicProviderFailure as exc:
        return CalendarFetchResult(status=STATUS_UNAVAILABLE, events=tuple(), provider=None, retrieved_at_utc=now_utc, error_detail=str(exc))
    return CalendarFetchResult(status=STATUS_OK, events=events, provider=type(provider).__name__, retrieved_at_utc=now_utc)


def currencies_for_symbol(symbol: str) -> tuple:
    """EURUSD -> (EUR, USD), GBPUSD -> (GBP, USD), etc. -- pure string decomposition,
    not a broker/instrument lookup."""
    symbol = symbol.upper()
    if len(symbol) != 6:
        raise ValueError(f"UNSUPPORTED_SYMBOL_FORMAT: cannot derive currencies from {symbol!r}")
    return (symbol[:3], symbol[3:])
