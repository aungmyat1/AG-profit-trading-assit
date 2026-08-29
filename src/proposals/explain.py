"""explain() -- human-readable proposal text (spec sections 33-34), built ONLY from
fields already present on the proposal (which are themselves copied verbatim from the
frozen SMC_CONDITIONAL_ENTRY_V2 contracts). No invented trading narrative ("strong
institutional selling pressure") -- every line states a deterministic fact or says it is
unavailable.
"""
from __future__ import annotations

from .models import SMCTradeProposal

_ENTRY_CONDITION_NAME = {
    "E1": "D1 gap fill and reaction",
    "E2": "H1 point-of-interest reaction",
    "E3": "HTF liquidity sweep",
}
_MANEUVER_NAME = {
    "M1": "internal character change with inducement",
    "M2": "supply/demand control shift",
    "M3": "sweep + drop/pump",
}


def explain(proposal: SMCTradeProposal) -> str:
    lines = [f"{proposal.symbol} {proposal.direction or '?'} PROPOSAL", "", "MODEL", proposal.combination, ""]

    lines.append("WHY HERE")
    lines.append(f"{_ENTRY_CONDITION_NAME.get(proposal.entry_condition, proposal.entry_condition)} "
                 f"on {proposal.reference_timeframe or '?'}, checked on {proposal.check_timeframe or '?'}.")
    lines.append("")

    lines.append("M5 CONFIRMATION")
    lines.append(f"{_MANEUVER_NAME.get(proposal.maneuver, proposal.maneuver)} "
                 f"confirmed on {proposal.confirmation_timeframe or '?'}.")
    lines.append("")

    lines.append("ENTRY")
    if proposal.entry_low is not None and proposal.entry_high is not None:
        lines.append(f"{proposal.entry_type or 'entry array'}: {proposal.entry_low:.5f} - {proposal.entry_high:.5f}")
    elif proposal.entry_reference is not None:
        lines.append(f"{proposal.entry_type or 'entry reference'}: {proposal.entry_reference:.5f}")
    else:
        lines.append("no entry price available")
    lines.append("")

    lines.append("INVALIDATION")
    if proposal.invalidation_price is not None:
        lines.append(f"Price: {proposal.invalidation_price:.5f}")
        lines.append(f"Source: {proposal.invalidation_source_type}")
        lines.append(f"Trigger: {proposal.invalidation_trigger}")
        if proposal.invalidation_reason:
            lines.append(f"Reason: {proposal.invalidation_reason}")
    else:
        lines.append("no invalidation level defined by the underlying M-model yet")
    lines.append("")

    lines.append("LIFECYCLE")
    lines.append(proposal.lifecycle)
    if proposal.changed_fields:
        lines.append(f"changed: {', '.join(proposal.changed_fields)}")
    lines.append("")

    lines.append("STATUS")
    lines.append(proposal.status)

    return "\n".join(lines)
