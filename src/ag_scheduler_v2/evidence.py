"""Scheduler identity + shadow-evidence envelope (spec sections 16, 37). Every
scheduler-generated evidence record carries scheduler_id/version/config_hash/strategy
identity so missed-cycle and runtime behavior can later be attributed to a specific
scheduler version, and captures LIVE_WINDOW/CATCH_UP + NEWS_RISK + priority metadata
alongside whatever the strategy engine actually returned.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Optional

from ag_scheduler_v2 import SCHEDULER_ID, SCHEDULER_VERSION
from ag_scheduler_v2.config_loader import config_hash


@dataclass(frozen=True)
class SchedulerIdentity:
    scheduler_id: str
    scheduler_version: str
    git_commit: Optional[str]
    application_release: Optional[str]
    strategy_id: str
    strategy_version: str
    config_hash: str

    @classmethod
    def build(
        cls,
        *,
        strategy_id: str,
        strategy_version: str,
        git_commit: Optional[str] = None,
        application_release: Optional[str] = None,
        path: Optional[str] = None,
    ) -> "SchedulerIdentity":
        return cls(
            scheduler_id=SCHEDULER_ID,
            scheduler_version=SCHEDULER_VERSION,
            git_commit=git_commit,
            application_release=application_release,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            config_hash=config_hash(path),
        )


@dataclass(frozen=True)
class ShadowEvidenceRecord:
    """One qualified candidate's full evidence record for one M15 cycle. Never a mock
    fallback -- callers must only construct this from an actual StrategyResult the
    strategy engine returned (spec section 18)."""

    scheduler_identity: SchedulerIdentity
    cycle_id: str
    symbol: str
    session_pair: str
    bar_close_utc: str
    observation_mode: str  # LIVE_WINDOW | CATCH_UP
    news_status: str
    news_state: str
    setup_type: Optional[str]
    strategy_status: str
    qualified: bool
    priority_status: str
    priority_score: Optional[float]
    priority_rank: Optional[int]
    priority_action: Optional[str]  # WOULD_PRIORITIZE, never EXECUTE
    reason_codes: tuple = field(default_factory=tuple)
    recorded_at_utc: str = ""

    def to_dict(self) -> dict:
        return {
            "scheduler_id": self.scheduler_identity.scheduler_id,
            "scheduler_version": self.scheduler_identity.scheduler_version,
            "git_commit": self.scheduler_identity.git_commit,
            "application_release": self.scheduler_identity.application_release,
            "strategy_id": self.scheduler_identity.strategy_id,
            "strategy_version": self.scheduler_identity.strategy_version,
            "config_hash": self.scheduler_identity.config_hash,
            "cycle_id": self.cycle_id,
            "symbol": self.symbol,
            "session_pair": self.session_pair,
            "bar_close_utc": self.bar_close_utc,
            "observation_mode": self.observation_mode,
            "news_status": self.news_status,
            "news_state": self.news_state,
            "setup_type": self.setup_type,
            "strategy_status": self.strategy_status,
            "qualified": self.qualified,
            "priority_status": self.priority_status,
            "priority_score": self.priority_score,
            "priority_rank": self.priority_rank,
            "priority_action": self.priority_action,
            "reason_codes": list(self.reason_codes),
            "recorded_at_utc": self.recorded_at_utc,
        }
