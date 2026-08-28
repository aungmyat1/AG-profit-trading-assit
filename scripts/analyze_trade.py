#!/usr/bin/env python
"""AG Trading Assistant primary CLI runner (AG_TRADING_ASSISTANT_WORKFLOW_V1 spec
section 34): a single practical entry point over assistant.technique_router.
analyze_by_technique(), for either technique.

Usage:
    python scripts/analyze_trade.py EURUSD --technique DAYTRADING [--time ISO8601] [--json] [--verbose]
    python scripts/analyze_trade.py EURUSD --technique SMC [--json] [--verbose]

Read-only: no order is ever placed. Journals a decision_snapshot via
assistant.idea_journal (see technique_router._journal_decision) as a side effect of
calling analyze_by_technique(), same as any other caller.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from datetime import datetime
from enum import Enum
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from assistant.analysis_models import FiveSkillAnalysisResult
from assistant.assessment import build_assistant_assessment
from assistant.canonical_state import daytrading_canonical_state, smc_canonical_state
from assistant.technique_router import TECHNIQUE_DAYTRADING, TECHNIQUE_SMC, analyze_by_technique
from daytrading.models import DayTradingResult
from entry_confirmation import CandidateDirection
from mt5.connection import MT5ConnectionError, connect


def main(argv=None) -> int:
    args = _parse_args(argv)

    try:
        connect()
    except MT5ConnectionError as exc:
        print(f"Status: MT5_NOT_CONNECTED\nReason: {exc}")
        return 1

    kwargs = {}
    if args.technique == TECHNIQUE_DAYTRADING:
        direction = CandidateDirection(args.direction) if args.direction else CandidateDirection.NONE
        result = analyze_by_technique(args.technique, args.symbol, candidate_direction=direction)
    else:
        result = analyze_by_technique(args.technique, args.symbol)

    if args.json:
        print(json.dumps(_to_jsonable(result), sort_keys=True, indent=2))
        return 0

    if isinstance(result, DayTradingResult):
        print(_render_daytrading(args.symbol, result, verbose=args.verbose))
    else:
        print(_render_smc(args.symbol, result, verbose=args.verbose))
    return 0


def _render_daytrading(symbol: str, result: DayTradingResult, verbose: bool) -> str:
    narrative, affinity, ltf, risk = result.narrative_bias, result.liquidity_affinity, result.ltf_execution, result.risk_management
    state = daytrading_canonical_state(result)
    reason = "; ".join(result.reasons) if result.reasons else "-"

    lines = [
        "AG TRADING ASSISTANT", "", "SYMBOL", symbol, "", "TECHNIQUE", "DAYTRADING", "",
        "NARRATIVE",
        f"Profile: {narrative.expected_profile}",
        f"Preferred Direction: {narrative.preferred_direction}",
        f"Primary Draw: {narrative.primary_draw or '-'}",
        "",
        "LIQUIDITY AFFINITY",
        f"Status: {affinity.status if affinity else 'NOT_EVALUATED'}",
        f"Primary Target: {affinity.primary_target_price if affinity and affinity.primary_target_price else '-'}",
        "",
        "LTF EXECUTION",
        f"Status: {ltf.status if ltf else 'NOT_EVALUATED'}",
        f"Execution Model: {ltf.execution_model if ltf else '-'}",
        f"Sweep-Shift Corroboration: {ltf.sweep_shift_result.aggregation_status if ltf and ltf.sweep_shift_result else 'NOT_EVALUATED'}",
        "",
        "RISK",
        f"Status: {risk.status if risk else 'NOT_EVALUATED'}",
        "",
        "FINAL", state, "", "REASON", reason,
    ]
    if verbose:
        lines += ["", "--- VERBOSE ---",
                   f"trade_state: {result.trade_state}",
                   f"direction: {result.direction}",
                   f"narrative_status: {narrative.narrative_status}",
                   f"structure_evidence: {narrative.structure_evidence}",
                   f"liquidity_evidence: {narrative.liquidity_evidence}"]
        if affinity is not None:
            lines.append(f"affinity_evidence: {affinity.evidence}")
        if ltf is not None:
            lines.append(f"ltf_reason: {ltf.reason}")
            if ltf.sweep_shift_result is not None:
                lines.append(f"sweep_shift_status: {ltf.sweep_shift_result.status} "
                              f"({ltf.sweep_shift_result.setup_family})")
    return "\n".join(lines)


def _render_smc(symbol: str, result: FiveSkillAnalysisResult, verbose: bool) -> str:
    state = smc_canonical_state(result)
    assessment = build_assistant_assessment(result)
    lines = [assessment.report_text, "", "FINAL", state]
    if verbose:
        lines += ["", "--- EVIDENCE ---", *assessment.evidence_summary]
    return "\n".join(lines)


def _to_jsonable(value):
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _to_jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    return value


def _parse_args(argv) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("symbol")
    parser.add_argument("--technique", choices=(TECHNIQUE_SMC, TECHNIQUE_DAYTRADING), default=TECHNIQUE_DAYTRADING)
    parser.add_argument("--direction", choices=("LONG", "SHORT"), default=None,
                         help="Candidate direction for DAYTRADING (default: NONE -- context-only read).")
    parser.add_argument("--time", default=None, help="Reserved for a future evaluation_time override; not yet wired.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
