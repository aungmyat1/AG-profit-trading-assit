"""Renders an AssistantDecision as the compact human-readable report shown to the user
(spec section 25). Pure formatting over already-computed fields -- never invents a
fact, never uses discretionary wording for the core facts (only the fixed field labels
below).
"""
from __future__ import annotations

from assistant.models import AssistantDecision, MODE_ANALYZE_ONLY, MODE_DEMO_EXECUTION, MODE_SHADOW_DEMO

_EXECUTION_LABEL = {
    MODE_ANALYZE_ONLY: "BLOCKED_BY_ANALYZE_ONLY",
    MODE_SHADOW_DEMO: "BLOCKED_BY_MODE (order_send not attempted)",
    MODE_DEMO_EXECUTION: None,  # filled in from the actual outcome below
}


def render(decision: AssistantDecision) -> str:
    lines = [
        "AG PROFIT TRADING ASSISTANT",
        "",
        f"Strategy: {decision.strategy_id}",
        f"Symbol: {decision.symbol}",
        f"Cycle: {decision.cycle}",
        f"Mode: {decision.execution_mode}",
        "",
        "MARKET CONTEXT",
        decision.context_status,
        "",
        "STRATEGY",
        f"Status: {decision.strategy_status or '-'}",
        f"Setup: {decision.setup or '-'}",
        f"Direction: {decision.direction or '-'}",
        "",
        "TRADE",
        f"Entry: {decision.entry if decision.entry is not None else '-'}",
        f"SL: {decision.stop_loss if decision.stop_loss is not None else '-'}",
        f"TP: {decision.target if decision.target is not None else '-'}",
        f"Signal ID: {decision.signal_id or '-'}",
        "",
        "EXECUTION",
    ]

    if decision.execution_mode == MODE_DEMO_EXECUTION and decision.execution_report:
        lines.append(str(decision.execution_report))
    else:
        lines.append(_EXECUTION_LABEL.get(decision.execution_mode, "-"))

    lines += [
        "",
        "RESULT",
        decision.status,
    ]
    if decision.reason_codes:
        lines.append(f"Reasons: {', '.join(decision.reason_codes)}")

    return "\n".join(lines)
