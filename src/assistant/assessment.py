"""Renders a FiveSkillAnalysisResult as a human-readable Trade Assistant report (spec
section 27/31/32). Pure formatting over already-computed fields, same discipline as
assistant/report.py: never invents a fact, never a BUY/SELL/probability statement, and
every statement traces to a field already present on the result -- see
docs/specs/FIVE_SKILL_ASSISTANT_RUNTIME_V1_SPEC.md's "AI / reporting authority" section.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from entry_confirmation import ConfirmationState

from .analysis_models import FiveSkillAnalysisResult, SKILL_NOT_REQUESTED, SKILL_NO_CANDIDATE


@dataclass(frozen=True)
class AssistantAssessment:
    report_text: str
    evidence_summary: Tuple[str, ...]


def build_assistant_assessment(result: FiveSkillAnalysisResult) -> AssistantAssessment:
    evidence = _evidence_summary(result)
    lines = [
        f"AG TRADE ASSISTANT -- {result.symbol} {result.timeframe}",
        "",
        "MARKET CONTEXT",
        result.market_context_status,
        "",
        "MARKET STRUCTURE",
        *_structure_lines(result),
        "",
        "SUPPLY & DEMAND",
        *_supply_demand_lines(result),
        "",
        "LIQUIDITY",
        *_liquidity_lines(result),
        "",
        "ENTRY & CONFIRMATION",
        *_entry_confirmation_lines(result),
        "",
        "TRADE MANAGEMENT",
        *_trade_management_lines(result),
        "",
        "ASSESSMENT",
        *[f"{k}: {v}" for k, v in result.skill_statuses.items()],
        f"Overall: {result.overall_status}",
    ]
    if result.limitations:
        lines += ["", "LIMITATIONS"] + [f"- {l}" for l in result.limitations]
    if result.errors:
        lines += ["", "ERRORS"] + [f"- {e}" for e in result.errors]

    return AssistantAssessment(report_text="\n".join(lines), evidence_summary=evidence)


def _structure_lines(result: FiveSkillAnalysisResult):
    s = result.structure
    if s is None:
        return [_status_line(result, "market-structure")]
    lines = [f"State: {s.state or '-'}"]
    if s.latest_choch:
        lines.append(f"Latest CHoCH: {s.latest_choch.kind.value} @ {s.latest_choch.price} ({s.latest_choch.time_utc})")
    if s.latest_bos:
        lines.append(f"Latest BOS: {s.latest_bos.kind.value} @ {s.latest_bos.price} ({s.latest_bos.time_utc})")
    if s.status != "VALID":
        lines.append(f"Status: {s.status} ({', '.join(s.reason_codes)})")
    return lines


def _supply_demand_lines(result: FiveSkillAnalysisResult):
    sd = result.supply_demand
    if sd is None:
        return [_status_line(result, "supply-demand")]
    return [
        f"Validated Order Blocks: {len(sd.validated_order_blocks)}",
        f"Fair Value Gaps: {len(sd.fair_value_gaps.zones)} ({sd.fair_value_gaps.status})",
    ]


def _liquidity_lines(result: FiveSkillAnalysisResult):
    l = result.liquidity
    if l is None:
        return [_status_line(result, "liquidity")]
    lines = [f"Status: {l.status}", f"Levels: {len(l.levels)}"]
    if l.nearest_sell_side:
        lines.append(f"Nearest sell-side: {l.nearest_sell_side.price} ({l.nearest_sell_side.status.value})")
    if l.nearest_buy_side:
        lines.append(f"Nearest buy-side: {l.nearest_buy_side.price} ({l.nearest_buy_side.status.value})")
    return lines


def _entry_confirmation_lines(result: FiveSkillAnalysisResult):
    ec = result.entry_confirmation
    if ec is None:
        return [_status_line(result, "entry-confirmation")]
    lines = []
    for key in ("displacement", "structure_shift", "liquidity_reclaim", "rejection"):
        primitive = getattr(ec, key)
        if primitive.status == ConfirmationState.NOT_REQUESTED:
            continue
        if primitive.status == ConfirmationState.UNSIGNED_RULE:
            lines.append(f"{key}: measured, qualification UNSIGNED_RULE")
        else:
            lines.append(f"{key}: {primitive.status.value}")
    lines.append(f"Overall: {ec.overall_state.value}")
    return lines


def _trade_management_lines(result: FiveSkillAnalysisResult):
    tm = result.trade_management
    if tm is None:
        return ["No candidate trade supplied.", "Sizing and RR not evaluated."]
    lines = [f"Geometry: {tm.geometry.status}"]
    if tm.geometry.rr_multiple is not None:
        lines.append(f"RR: {tm.geometry.rr_multiple:.2f}R")
    lines.append(f"Sizing: {tm.sizing.status}")
    if tm.sizing.normalized_volume is not None:
        lines.append(f"Volume: {tm.sizing.normalized_volume}")
        lines.append(f"Actual risk: {tm.sizing.actual_risk_amount:.2f} ({tm.sizing.actual_risk_percent:.2f}%)")
    lines.append(f"Overall: {tm.overall_status}")
    return lines


def _status_line(result: FiveSkillAnalysisResult, skill: str) -> str:
    status = result.skill_statuses.get(skill, "-")
    if status == SKILL_NOT_REQUESTED:
        return "Not requested for this analysis."
    if status == SKILL_NO_CANDIDATE:
        return "No candidate trade supplied."
    return f"Status: {status}"


def _evidence_summary(result: FiveSkillAnalysisResult) -> Tuple[str, ...]:
    """One short line per skill that actually ran -- the auditable "evidence
    completeness" record the mission requires instead of a fake confidence score."""
    lines = []
    for skill, status in result.skill_statuses.items():
        if status in (SKILL_NOT_REQUESTED, SKILL_NO_CANDIDATE):
            continue
        lines.append(f"{skill}: {status}")
    return tuple(lines)
