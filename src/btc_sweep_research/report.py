"""Human-readable + JSON report rendering for one ResearchCycleResult (mirrors
post_asian_pilot/report.py's cycle_to_dict/human_readable_report split, scaled down to
this package's single-symbol, single-profile scope)."""
from __future__ import annotations

import dataclasses
from typing import Any, Dict

from .pipeline import ResearchCycleResult


def cycle_to_dict(result: ResearchCycleResult) -> Dict[str, Any]:
    payload = {
        "trading_day": result.trading_day.isoformat(),
        "setup_state": {
            k: (v.isoformat() if hasattr(v, "isoformat") else v)
            for k, v in dataclasses.asdict(result.setup_state).items()
        },
        "ledger_new_row": result.ledger_new_row,
        "proposal": None,
    }
    if result.proposal is not None:
        payload["proposal"] = {
            k: (v.isoformat() if hasattr(v, "isoformat") else v)
            for k, v in dataclasses.asdict(result.proposal).items()
        }
    return payload


def human_readable_report(result: ResearchCycleResult) -> str:
    lines = [
        "AG_BTC_SWEEP_RESEARCH_V1",
        f"trading_day = {result.trading_day.isoformat()}",
        f"setup_state = {result.setup_state.state}",
        f"reason_code = {result.setup_state.reason_code}",
    ]
    if result.setup_state.direction:
        lines.append(f"direction = {result.setup_state.direction}")
    if result.proposal is not None:
        p = result.proposal
        lines += [
            f"occurrence_id = {p.occurrence_id}",
            f"ledger_new_row = {result.ledger_new_row}",
            f"entry = {p.entry}  stop = {p.stop}  tp1 = {p.target.get('tp1')}  tp2 = {p.target.get('tp2')}",
            f"RR = {p.RR}",
            f"estimated_fees = {p.estimated_fees:.4f} USDT",
            f"execution_domain = {p.execution_domain}  execution_authority = {p.execution_authority}",
        ]
    else:
        lines.append("ledger_new_row = False (no ENTRY_READY setup this cycle)")
    return "\n".join(lines)
