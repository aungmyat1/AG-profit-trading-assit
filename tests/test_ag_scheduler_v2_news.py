import datetime as dt

import pytest

from ag_scheduler_v2.news_provider import (
    STATUS_OK, STATUS_UNAVAILABLE, EconomicCalendarProvider, EconomicEvent, EconomicProviderFailure,
    currencies_for_symbol, fetch_relevant_events,
)
from ag_scheduler_v2.news_risk import NEWS_STATE_NEWS_RISK, NEWS_STATE_NORMAL, NEWS_STATE_UNKNOWN, NewsRiskWindow, evaluate_news_risk


def _utc(y, mo, d, h, mi):
    return dt.datetime(y, mo, d, h, mi, tzinfo=dt.timezone.utc)


class _WorkingProvider(EconomicCalendarProvider):
    def __init__(self, events):
        self._events = events

    def fetch_events(self, *, currencies, window_start_utc, window_end_utc):
        return [e for e in self._events if e.currency in currencies]


class _FailingProvider(EconomicCalendarProvider):
    def fetch_events(self, *, currencies, window_start_utc, window_end_utc):
        raise EconomicProviderFailure("upstream timeout")


def _event(currency, when, impact="HIGH"):
    return EconomicEvent(event_id=f"{currency}-{when.isoformat()}", currency=currency, event_time_utc=when, impact=impact, event_name="CPI", provider="test", retrieved_at_utc=when)


class TestCurrencyDecomposition:
    def test_eurusd(self):
        assert currencies_for_symbol("EURUSD") == ("EUR", "USD")

    def test_gbpusd(self):
        assert currencies_for_symbol("GBPUSD") == ("GBP", "USD")


class TestProviderAbstraction:
    def test_fetch_ok(self):
        now = _utc(2026, 9, 10, 8, 0)
        provider = _WorkingProvider([_event("USD", now)])
        result = fetch_relevant_events(provider, currencies=("EUR", "USD"), window_start_utc=now, window_end_utc=now, now_utc=now)
        assert result.status == STATUS_OK
        assert len(result.events) == 1

    def test_fetch_failure_is_unavailable_never_no_news(self):
        now = _utc(2026, 9, 10, 8, 0)
        provider = _FailingProvider()
        result = fetch_relevant_events(provider, currencies=("EUR", "USD"), window_start_utc=now, window_end_utc=now, now_utc=now)
        assert result.status == STATUS_UNAVAILABLE
        assert result.events == tuple()
        assert result.error_detail == "upstream timeout"


class TestNewsRisk:
    def setup_method(self):
        self.window = NewsRiskWindow(impact="HIGH", minutes_before=15, minutes_after=15)

    def test_relevant_currency_event_inside_window_flags_news_risk(self):
        bar_close = _utc(2026, 9, 10, 8, 15)
        event = _event("USD", bar_close + dt.timedelta(minutes=10))
        evidence = evaluate_news_risk(bar_close_utc=bar_close, calendar_status="OK", events=[event], window=self.window)
        assert evidence.news_state == NEWS_STATE_NEWS_RISK
        assert len(evidence.matched_events) == 1

    def test_irrelevant_impact_does_not_flag(self):
        bar_close = _utc(2026, 9, 10, 8, 15)
        event = _event("USD", bar_close, impact="LOW")
        evidence = evaluate_news_risk(bar_close_utc=bar_close, calendar_status="OK", events=[event], window=self.window)
        assert evidence.news_state == NEWS_STATE_NORMAL

    def test_event_just_inside_minus_15_boundary(self):
        bar_close = _utc(2026, 9, 10, 8, 15)
        event = _event("USD", bar_close - dt.timedelta(minutes=15))
        evidence = evaluate_news_risk(bar_close_utc=bar_close, calendar_status="OK", events=[event], window=self.window)
        assert evidence.news_state == NEWS_STATE_NEWS_RISK

    def test_event_just_outside_plus_15_boundary(self):
        bar_close = _utc(2026, 9, 10, 8, 15)
        event = _event("USD", bar_close + dt.timedelta(minutes=15, seconds=1))
        evidence = evaluate_news_risk(bar_close_utc=bar_close, calendar_status="OK", events=[event], window=self.window)
        assert evidence.news_state == NEWS_STATE_NORMAL

    def test_provider_unavailable_is_unknown_not_no_news(self):
        bar_close = _utc(2026, 9, 10, 8, 15)
        evidence = evaluate_news_risk(bar_close_utc=bar_close, calendar_status=STATUS_UNAVAILABLE, events=[], window=self.window)
        assert evidence.news_state == NEWS_STATE_UNKNOWN
        assert evidence.news_status == STATUS_UNAVAILABLE
