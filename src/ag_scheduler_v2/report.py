"""Daily combined report (spec sections 31, 32, 34). Aggregates persisted shadow
evidence + missed-cycle accounting into the report shape the owner specified. No
profitability claim is made from a single day's evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

MISSED_OBSERVATION_CYCLE_RATE = "missed_observation_cycle_rate"  # research-mode name (spec 32)


@dataclass(frozen=True)
class DailyReport:
    scheduler_id: str
    scheduler_version: str
    expected_cycles: int
    completed_live_cycles: int
    catch_up_cycles: int
    missed_cycles: int
    missed_observation_cycle_rate: float
    per_symbol_counts: dict
    per_session_pair_counts: dict
    per_setup_type_counts: dict
    total_qualified_opportunities: int
    total_rejected_opportunities: int
    rejection_reason_counts: dict
    news_risk_count: int
    normal_count: int
    unknown_news_state_count: int
    priority_decisions: int


def build_daily_report(
    *,
    scheduler_id: str,
    scheduler_version: str,
    evidence_records: Sequence[dict],
    expected_cycles: int,
    completed_live_cycles: int,
    catch_up_cycles: int,
) -> DailyReport:
    """`evidence_records` are ShadowEvidenceRecord.to_dict() outputs for one report
    period. `expected_cycles`/`completed_live_cycles`/`catch_up_cycles` are supplied by
    the caller (from recovery.py/cycle_identity.py accounting) rather than re-derived
    here, since this module has no access to the schedule/checkpoint state itself."""
    missed_cycles = max(expected_cycles - completed_live_cycles - catch_up_cycles, 0)
    missed_rate = (missed_cycles / expected_cycles) if expected_cycles else 0.0

    per_symbol: dict = {}
    per_session_pair: dict = {}
    per_setup_type: dict = {}
    rejection_reasons: dict = {}
    qualified = 0
    rejected = 0
    news_risk = 0
    normal = 0
    unknown_news = 0
    priority_decisions = 0

    for rec in evidence_records:
        per_symbol[rec["symbol"]] = per_symbol.get(rec["symbol"], 0) + 1
        per_session_pair[rec["session_pair"]] = per_session_pair.get(rec["session_pair"], 0) + 1
        if rec.get("setup_type"):
            per_setup_type[rec["setup_type"]] = per_setup_type.get(rec["setup_type"], 0) + 1

        if rec.get("qualified"):
            qualified += 1
        else:
            rejected += 1
            for code in rec.get("reason_codes") or []:
                rejection_reasons[code] = rejection_reasons.get(code, 0) + 1

        news_state = rec.get("news_state")
        if news_state == "NEWS_RISK":
            news_risk += 1
        elif news_state == "NORMAL":
            normal += 1
        elif news_state == "UNKNOWN_NEWS_STATE":
            unknown_news += 1

        if rec.get("priority_action") == "WOULD_PRIORITIZE":
            priority_decisions += 1

    return DailyReport(
        scheduler_id=scheduler_id,
        scheduler_version=scheduler_version,
        expected_cycles=expected_cycles,
        completed_live_cycles=completed_live_cycles,
        catch_up_cycles=catch_up_cycles,
        missed_cycles=missed_cycles,
        missed_observation_cycle_rate=missed_rate,
        per_symbol_counts=per_symbol,
        per_session_pair_counts=per_session_pair,
        per_setup_type_counts=per_setup_type,
        total_qualified_opportunities=qualified,
        total_rejected_opportunities=rejected,
        rejection_reason_counts=rejection_reasons,
        news_risk_count=news_risk,
        normal_count=normal,
        unknown_news_state_count=unknown_news,
        priority_decisions=priority_decisions,
    )
