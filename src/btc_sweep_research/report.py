"""Human-readable + JSON report rendering for one ResearchCycleReport (mirrors
post_asian_pilot/report.py's cycle_to_dict/human_readable_report split, scaled down to
this package's single-symbol, single-profile scope).

Remediation Gap 1: a cycle can now report 0..N occurrences (previously always exactly 0
or 1) -- this module renders every one of them, never just the first/last."""
from __future__ import annotations

import dataclasses
from typing import Any, Dict

from .pipeline import ResearchCycleReport, ResearchCycleResult


def _setup_state_dict(setup_state) -> Dict[str, Any]:
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v)
           for k, v in dataclasses.asdict(setup_state).items()}


def _occurrence_to_dict(result: ResearchCycleResult) -> Dict[str, Any]:
    payload = {"setup_state": _setup_state_dict(result.setup_state), "ledger_new_row": result.ledger_new_row,
               "proposal": None}
    if result.proposal is not None:
        payload["proposal"] = {
            k: (v.isoformat() if hasattr(v, "isoformat") else v)
            for k, v in dataclasses.asdict(result.proposal).items()
        }
    return payload


def cycle_to_dict(report: ResearchCycleReport) -> Dict[str, Any]:
    return {
        "trading_day": report.trading_day.isoformat(),
        "container_state": _setup_state_dict(report.container_state) if report.container_state is not None else None,
        "occurrence_count": len(report.occurrences),
        "qualified_count": len(report.qualified_occurrences),
        "tradable_count": len(report.tradable_occurrences),
        "occurrences": [_occurrence_to_dict(o) for o in report.occurrences],
    }


def human_readable_report(report: ResearchCycleReport) -> str:
    lines = ["AG_BTC_SWEEP_RESEARCH_V1", f"trading_day = {report.trading_day.isoformat()}"]

    if report.container_state is not None:
        lines.append(f"state = {report.container_state.state}")
        lines.append(f"reason_code = {report.container_state.reason_code}")
        return "\n".join(lines)

    lines.append(f"occurrences = {len(report.occurrences)} "
                f"(qualified={len(report.qualified_occurrences)}, tradable={len(report.tradable_occurrences)})")
    for i, result in enumerate(report.occurrences, start=1):
        s = result.setup_state
        lines.append(f"--- occurrence {i} ---")
        lines.append(f"setup_state = {s.state}  reason_code = {s.reason_code}")
        if s.direction:
            lines.append(f"direction = {s.direction}")
        if result.proposal is not None:
            p = result.proposal
            lines += [
                f"occurrence_id = {p.occurrence_id}",
                f"ledger_new_row = {result.ledger_new_row}",
                f"entry = {p.entry}  stop = {p.stop}  tp1 = {p.target.get('tp1')}  tp2 = {p.target.get('tp2')}",
                f"RR = {p.RR}",
                f"estimated_fees = {p.estimated_fees:.4f} USDT",
                f"tradability_allowed = {p.tradability_allowed}"
                + (f"  reason = {p.tradability_block_reason}" if not p.tradability_allowed else ""),
                f"execution_domain = {p.execution_domain}  execution_authority = {p.execution_authority}",
            ]
    return "\n".join(lines)
