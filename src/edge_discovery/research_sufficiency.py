"""Pre-outcome coverage reporting and minimal structural sufficiency for C001.

This gate intentionally does *not* borrow the promotion policy's 30-trade threshold or
invent a profitability sample size.  Its only pass/fail requirement is the frozen C001
reference prerequisite: for each required symbol there must be two complete UTC days,
one to form the exactly-288-bar previous-day reference and one later day on which that
reference could be evaluated.  Other coverage quantities are reported, not optimized.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Mapping, Sequence, Tuple

from .ingestion import DerivedDataset
from .quality import complete_utc_days, utc_iso

RESEARCH_SUFFICIENCY_POLICY_ID = "C001_REFERENCE_CONTEXT_SUFFICIENCY_V1"
REQUIRED_C001_SYMBOLS = ("BTCUSD", "ETHUSD")


@dataclass(frozen=True)
class ResearchSufficiencyReport:
    status: str
    policy_id: str
    reason_codes: Tuple[str, ...]
    by_symbol: Mapping[str, Mapping[str, Any]]
    common_complete_utc_days: int


def _complete_iso_weeks(days: Sequence[str]) -> int:
    parsed = {date.fromisoformat(day) for day in days}
    weeks = defaultdict(set)
    for item in parsed:
        year, week, _ = item.isocalendar()
        weeks[(year, week)].add(item)
    return sum(1 for values in weeks.values() if len(values) == 7)


def _complete_months(days: Sequence[str]) -> int:
    parsed = {date.fromisoformat(day) for day in days}
    by_month = defaultdict(set)
    for item in parsed:
        by_month[(item.year, item.month)].add(item)
    complete = 0
    for (year, month), values in by_month.items():
        first = date(year, month, 1)
        next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
        expected = (next_month - first).days
        if len(values) == expected:
            complete += 1
    return complete


def evaluate_research_sufficiency(datasets: Mapping[str, DerivedDataset]) -> ResearchSufficiencyReport:
    """Report coverage before a replay or metric calculation.  Unknown/missing symbols
    fail closed.  No price values are inspected beyond their timestamp index."""
    by_symbol: Dict[str, Mapping[str, Any]] = {}
    codes: list[str] = []
    day_sets = []
    for symbol in REQUIRED_C001_SYMBOLS:
        dataset = datasets.get(symbol)
        if dataset is None:
            codes.append("REQUIRED_SYMBOL_DATASET_MISSING")
            by_symbol[symbol] = {
                "coverage": None, "complete_utc_days": 0, "complete_weeks": 0,
                "complete_months": 0, "usable_m5_rows": 0, "usable_d1_context": 0,
            }
            day_sets.append(set())
            continue
        days = complete_utc_days(dataset.bars)
        day_sets.append(set(days))
        coverage = {
            "start_utc": utc_iso(dataset.bars[0].time) if dataset.bars else None,
            "end_utc": utc_iso(dataset.bars[-1].time) if dataset.bars else None,
        }
        by_symbol[symbol] = {
            "coverage": coverage,
            "complete_utc_days": len(days),
            "complete_weeks": _complete_iso_weeks(days),
            "complete_months": _complete_months(days),
            "usable_m5_rows": sum(1 for bar in dataset.bars if bar.time.date().isoformat() in set(days)),
            # D1 context is an observed coverage count, not an invented eligibility minimum.
            "usable_d1_context": len(days),
        }
        if len(days) < 2:
            codes.append("INSUFFICIENT_C001_REFERENCE_CONTEXT")
    common_days = len(set.intersection(*day_sets)) if day_sets else 0
    if common_days < 2:
        codes.append("INSUFFICIENT_COMMON_C001_REFERENCE_CONTEXT")
    return ResearchSufficiencyReport(
        status="PASS" if not codes else "FAIL", policy_id=RESEARCH_SUFFICIENCY_POLICY_ID,
        reason_codes=tuple(dict.fromkeys(codes)), by_symbol=by_symbol,
        common_complete_utc_days=common_days,
    )


__all__ = ["RESEARCH_SUFFICIENCY_POLICY_ID", "ResearchSufficiencyReport", "evaluate_research_sufficiency"]
