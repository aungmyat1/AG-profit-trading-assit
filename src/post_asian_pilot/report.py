"""JSON + human-readable report for one pilot cycle, plus release-manifest fingerprints
(reuses the same canonical SHA-256 technique as fingerprint.py / historical_replay.stage1).
"""
from __future__ import annotations

import dataclasses
from typing import Any, Dict

from .fingerprint import fingerprint
from .pilot_config import load_raw_yaml
from .pipeline import PilotCycleResult

EXECUTION_STATUS_DISABLED = "DISABLED"


def cycle_to_dict(result: PilotCycleResult) -> Dict[str, Any]:
    pairs = []
    for pr in result.pairs:
        entry: Dict[str, Any] = {
            "symbol": pr.symbol,
            "strategy_state": pr.decision.status,
            "portfolio_state": pr.portfolio_state,
            "portfolio_reason_code": pr.portfolio_reason_code,
            "direction": pr.decision.signal.direction if pr.decision.signal else None,
            "reason_codes": list(pr.decision.reason_codes),
            "missing_condition": pr.decision.missing_condition,
        }
        if pr.proposal is not None:
            tp = pr.proposal.trade_proposal
            entry["proposal"] = {
                "proposal_id": pr.proposal.proposal_id,
                "setup_id": pr.proposal.setup_id,
                "entry": tp.entry, "stop_loss": tp.stop_loss, "take_profit_1": tp.tp1, "take_profit_2": tp.tp2,
                "risk_percent": tp.risk_percent, "risk_amount": tp.risk_amount, "volume": tp.volume,
                "expires_at": pr.proposal.expires_at.isoformat(),
                "execution_status": pr.proposal.execution_status,
                "execution_authorized": pr.proposal.execution_authorized,
                "user_confirmation_required": pr.proposal.user_confirmation_required,
            }
        pairs.append(entry)

    return {
        "release": "AG_TRADE_ASSISTANT_V1_0",
        "strategy_id": result.strategy.strategy_id,
        "strategy_version": result.strategy.version,
        "trading_date": result.trading_date.isoformat(),
        "evaluation_time_utc": result.evaluation_time.isoformat(),
        "execution_window": f"{result.pilot_config.execution_window_start_utc}-{result.pilot_config.execution_window_end_utc} UTC",
        "pairs": pairs,
        "tiebreak_status": result.tiebreak_status,
        "execution": {
            "mode": "PROPOSAL_ONLY", "automatic_execution": EXECUTION_STATUS_DISABLED,
            "live_execution": EXECUTION_STATUS_DISABLED,
        },
    }


def human_readable_report(result: PilotCycleResult) -> str:
    lines = [
        "AG PROFIT TRADING", "POST-ASIAN LONDON PILOT", "",
        f"Strategy: {result.strategy.strategy_id} v{result.strategy.version}",
        f"Date: {result.trading_date.isoformat()}",
        f"Active window: {result.pilot_config.execution_window_start_utc}-"
        f"{result.pilot_config.execution_window_end_utc} UTC", "",
    ]
    for pr in result.pairs:
        lines.append(pr.symbol)
        lines.append(f"  strategy_state: {pr.decision.status}")
        lines.append(f"  portfolio_state: {pr.portfolio_state}"
                     + (f" ({pr.portfolio_reason_code})" if pr.portfolio_reason_code else ""))
        if pr.decision.missing_condition:
            lines.append(f"  missing_condition: {pr.decision.missing_condition}")
        if pr.proposal is not None:
            tp = pr.proposal.trade_proposal
            lines.append(f"  proposal_id: {pr.proposal.proposal_id}")
            lines.append(f"  entry: {tp.entry}  SL: {tp.stop_loss}  TP1: {tp.tp1}  TP2: {tp.tp2}")
            lines.append(f"  risk: {tp.risk_percent}%  volume: {tp.volume}")
            lines.append(f"  expires: {pr.proposal.expires_at.isoformat()}")
            lines.append(f"  execution: {pr.proposal.execution_status}")
        lines.append("")
    lines.append("EXECUTION")
    lines.append("automatic_execution = DISABLED")
    lines.append("live_execution = DISABLED")
    return "\n".join(lines)


def release_fingerprints(release_path: str, strategy_path: str, session_path: str,
                         pilot_risk_config: Dict[str, Any]) -> Dict[str, str]:
    return {
        "release_fingerprint": fingerprint(load_raw_yaml(release_path)),
        "strategy_fingerprint": fingerprint(load_raw_yaml(strategy_path)),
        "session_fingerprint": fingerprint(load_raw_yaml(session_path)),
        "risk_fingerprint": fingerprint(pilot_risk_config),
    }
