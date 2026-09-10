"""NEWS_RISK tagging (spec sections 13-15). A qualifying high-impact event within
+/-risk_window_minutes of a bar close flags NEWS_RISK_FLAG=true. During current
OFFLINE_RESEARCH/shadow evaluation this never blocks a setup -- it is recorded as
evidence so NORMAL vs NEWS_RISK expectancy can be compared later. Provider UNAVAILABLE
is a distinct, retained state -- never conflated with "no relevant event found".
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional, Sequence

from ag_scheduler_v2.config_loader import load_config
from ag_scheduler_v2.news_provider import STATUS_OK, STATUS_UNAVAILABLE, EconomicEvent

NEWS_STATE_NORMAL = "NORMAL"
NEWS_STATE_NEWS_RISK = "NEWS_RISK"
NEWS_STATE_UNKNOWN = "UNKNOWN_NEWS_STATE"  # provider UNAVAILABLE -- fail closed for future execution


@dataclass(frozen=True)
class NewsRiskWindow:
    impact: str
    minutes_before: int
    minutes_after: int

    @classmethod
    def from_config(cls, path: Optional[str] = None) -> "NewsRiskWindow":
        raw = load_config(path).get("news") or {}
        for key in ("impact", "risk_window_minutes_before", "risk_window_minutes_after"):
            if key not in raw:
                raise ValueError(f"SCHEDULER_CONFIG_CONFLICT: news.{key} is required")
        return cls(
            impact=raw["impact"],
            minutes_before=int(raw["risk_window_minutes_before"]),
            minutes_after=int(raw["risk_window_minutes_after"]),
        )


@dataclass(frozen=True)
class NewsRiskEvidence:
    news_status: str  # STATUS_OK | STATUS_UNAVAILABLE (from the calendar fetch)
    news_state: str  # NEWS_STATE_NORMAL | NEWS_STATE_NEWS_RISK | NEWS_STATE_UNKNOWN
    matched_events: tuple  # EconomicEvent entries that triggered NEWS_RISK, empty otherwise


def evaluate_news_risk(
    *,
    bar_close_utc: dt.datetime,
    calendar_status: str,
    events: Sequence[EconomicEvent],
    window: NewsRiskWindow,
) -> NewsRiskEvidence:
    if calendar_status == STATUS_UNAVAILABLE:
        return NewsRiskEvidence(news_status=STATUS_UNAVAILABLE, news_state=NEWS_STATE_UNKNOWN, matched_events=tuple())

    before = bar_close_utc - dt.timedelta(minutes=window.minutes_before)
    after = bar_close_utc + dt.timedelta(minutes=window.minutes_after)
    matched = tuple(
        e for e in events
        if e.impact == window.impact and before <= e.event_time_utc <= after
    )
    news_state = NEWS_STATE_NEWS_RISK if matched else NEWS_STATE_NORMAL
    return NewsRiskEvidence(news_status=STATUS_OK, news_state=news_state, matched_events=matched)
