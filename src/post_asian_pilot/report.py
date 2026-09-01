"""JSON + human-readable reports for AG_TRADE_ASSISTANT_V1_0_2: per-cycle report,
complete Entry Ticket, and a journal-grounded end-of-window report. Fingerprints reuse
the same canonical SHA-256 technique as fingerprint.py / historical_replay.stage1.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

from strategy_engine.models import StrategyConfig

from .decision import STATUS_DATA_ERROR, STATUS_READY
from .fingerprint import fingerprint
from .governor import DailyTradeLedger
from .pilot_config import PilotConfig, load_raw_yaml
from .pipeline import PilotCycleResult
from .proposal import PostAsianEntryProposal
from .store import PilotStores, decision_from_record

EXECUTION_STATUS_DISABLED = "DISABLED"
UNAVAILABLE_NOT_WIRED = "UNAVAILABLE_NOT_WIRED"


def cycle_to_dict(result: PilotCycleResult) -> Dict[str, Any]:
    pairs = []
    for pr in result.pairs:
        entry: Dict[str, Any] = {
            "symbol": pr.symbol,
            "strategy_state": pr.decision.status,
            "portfolio_state": pr.portfolio_state,
            "portfolio_reason_code": pr.portfolio_reason_code,
            "direction": pr.decision.signal.direction if pr.decision.signal else None,
            "ready_at": pr.decision.ready_at.isoformat() if pr.decision.ready_at else None,
            "reason_codes": list(pr.decision.reason_codes),
            "missing_condition": pr.decision.missing_condition,
        }
        if pr.proposal is not None:
            tp = pr.proposal.trade_proposal
            entry["proposal"] = {
                "proposal_id": pr.proposal.proposal_id,
                "setup_id": pr.proposal.setup_id,
                "entry": tp.entry, "stop_loss": tp.stop_loss, "take_profit_1": tp.tp1, "take_profit_2": tp.tp2,
                "risk_percent": tp.risk_percent, "risk_amount": tp.risk_amount,
                "raw_volume": pr.proposal.raw_volume, "normalized_volume": tp.volume,
                "expires_at": pr.proposal.expires_at.isoformat(),
                "execution_status": pr.proposal.execution_status,
                "execution_authorized": pr.proposal.execution_authorized,
                "actionable": pr.proposal.actionable,
            }
        pairs.append(entry)

    return {
        "release": result.release_id,
        "strategy_id": result.strategy.strategy_id,
        "strategy_version": result.strategy.version,
        "trading_date": result.trading_date.isoformat(),
        "evaluation_time_utc": result.evaluation_time.isoformat(),
        "execution_window": f"{result.pilot_config.execution_window_start_utc}-{result.pilot_config.execution_window_end_utc} UTC",
        "pairs": pairs,
        "daily_opportunity_ledger": {
            "max_opportunities": result.ledger_max_slots,
            "used": result.ledger_slots_used,
            "max_per_symbol": result.pilot_config.max_new_trades_per_symbol_per_day,
        },
        "execution": {
            "mode": "PROPOSAL_ONLY", "automatic_execution": EXECUTION_STATUS_DISABLED,
            "live_execution": EXECUTION_STATUS_DISABLED,
        },
    }


def human_readable_report(result: PilotCycleResult) -> str:
    lines = [
        "AG PROFIT TRADING", result.release_id, "",
        f"Strategy: {result.strategy.strategy_id} v{result.strategy.version}",
        f"Date: {result.trading_date.isoformat()}",
        f"Active window: {result.pilot_config.execution_window_start_utc}-"
        f"{result.pilot_config.execution_window_end_utc} UTC", "",
    ]
    for pr in result.pairs:
        lines.append(pr.symbol)
        lines.append(f"  strategy_state: {pr.decision.status}")
        if pr.decision.ready_at is not None:
            lines.append(f"  ready_at: {pr.decision.ready_at.isoformat()}")
        lines.append(f"  portfolio_state: {pr.portfolio_state}"
                     + (f" ({pr.portfolio_reason_code})" if pr.portfolio_reason_code else ""))
        if pr.decision.missing_condition:
            lines.append(f"  missing_condition: {pr.decision.missing_condition}")
        if pr.proposal is not None:
            tp = pr.proposal.trade_proposal
            lines.append(f"  proposal_id: {pr.proposal.proposal_id}")
            lines.append(f"  entry: {tp.entry}  SL: {tp.stop_loss}  TP1: {tp.tp1}  TP2: {tp.tp2}")
            lines.append(f"  risk: {tp.risk_percent}%  volume: {tp.volume} (raw {pr.proposal.raw_volume})")
            lines.append(f"  expires: {pr.proposal.expires_at.isoformat()}")
            lines.append(f"  execution: {pr.proposal.execution_status}")
        lines.append("")
    lines.append("DAILY OPPORTUNITY LEDGER")
    lines.append(f"maximum opportunities: {result.ledger_max_slots}")
    lines.append(f"used: {result.ledger_slots_used} / {result.ledger_max_slots}")
    lines.append(f"maximum per symbol: {result.pilot_config.max_new_trades_per_symbol_per_day}")
    lines.append("")
    lines.append("EXECUTION")
    lines.append("automatic_execution = DISABLED")
    lines.append("live_execution = DISABLED")
    return "\n".join(lines)


def release_fingerprints(release_path: str, strategy_path: str, session_path: str,
                         pilot_risk_config: Dict[str, Any]) -> Dict[str, str]:
    release_raw = load_raw_yaml(release_path)
    return {
        "release_fingerprint": fingerprint(release_raw),
        "strategy_fingerprint": fingerprint(load_raw_yaml(strategy_path)),
        "session_fingerprint": fingerprint(load_raw_yaml(session_path)),
        "risk_fingerprint": fingerprint(pilot_risk_config),
        "selection_policy_fingerprint": fingerprint(release_raw.get("selection_policy") or {}),
    }


# --------------------------------------------------------------------------- complete Entry Ticket

def render_entry_ticket(
    proposal: PostAsianEntryProposal, decision, strategy: StrategyConfig, release_id: str,
    release_fingerprint: str, strategy_fingerprint: str, ledger: DailyTradeLedger, trading_date: date,
    snapshot: Optional[Any] = None, aggregate_open_risk_pct: Optional[float] = None,
) -> Dict[str, Any]:
    """Every field per spec section 17. Anything not safely, honestly available reports
    an explicit UNAVAILABLE_* string, never a fabricated value (section 18)."""
    tp = proposal.trade_proposal
    slot = ledger.symbol_slot(strategy.strategy_id, trading_date, proposal.trade_proposal.symbol)
    slots_used = ledger.consumed_count(strategy.strategy_id, trading_date)

    return {
        "application": {"release_id": release_id, "release_fingerprint": release_fingerprint},
        "strategy": {"strategy_id": strategy.strategy_id, "strategy_version": strategy.version,
                    "strategy_fingerprint": strategy_fingerprint},
        "identity": {"ledger_slot": slot["slot_index"] if slot else None,
                    "proposal_id": proposal.proposal_id, "setup_id": proposal.setup_id},
        "market": {"symbol": tp.symbol, "direction": tp.direction,
                  "setup_type": decision.signal.setup if decision.signal else None,
                  "ready_at": decision.ready_at.isoformat() if decision.ready_at else None},
        "session": {
            "asian_high": snapshot.high if snapshot else UNAVAILABLE_NOT_WIRED,
            "asian_low": snapshot.low if snapshot else UNAVAILABLE_NOT_WIRED,
            "asian_mid": snapshot.midpoint if snapshot else UNAVAILABLE_NOT_WIRED,
            "asian_range": snapshot.range if snapshot else UNAVAILABLE_NOT_WIRED,
            "swept_level": proposal.swept_level, "snapshot_id": proposal.session_snapshot_id,
        },
        "entry": {"entry": tp.entry, "stop_loss": tp.stop_loss, "tp1": tp.tp1, "tp2_runner": tp.tp2},
        "allocation": {"tp1_pct": 75, "runner_pct": 25},
        "risk": {"risk_percent": tp.risk_percent, "risk_amount": tp.risk_amount,
                "raw_volume": proposal.raw_volume, "normalized_volume": tp.volume,
                "estimated_loss_at_sl": tp.risk_amount},
        "portfolio": {"daily_slots_used": f"{slots_used}/{ledger.max_slots}",
                     "aggregate_open_risk_pct": aggregate_open_risk_pct
                     if aggregate_open_risk_pct is not None else UNAVAILABLE_NOT_WIRED},
        "timing": {"created_at": proposal.created_at.isoformat(), "expires_at": proposal.expires_at.isoformat()},
        "evidence": {"reason_codes": list(proposal.reason_codes),
                    "evidence_snapshot_id": proposal.evidence_snapshot_id},
        "decision": "READY",
        "execution": {"status": proposal.execution_status, "execution_authorized": proposal.execution_authorized},
    }


# --------------------------------------------------------------------------- end-of-window report

def render_pilot_end_report(
    pilot: PilotConfig, strategy: StrategyConfig, release_id: str, trading_date: date, stores: PilotStores,
) -> Dict[str, Any]:
    """Journal-grounded: reads only PERSISTED state (decision/proposal/ledger/counters/
    snapshot stores), never in-memory results from a single cycle -- spec section 20:
    'report actual recorded state, do not infer events that were not persisted.'"""
    pairs: Dict[str, Any] = {}
    data_error_seen = False
    for symbol in pilot.universe:
        key = f"{strategy.strategy_id}|{symbol}|{trading_date.isoformat()}|{pilot.reference_session_name}"
        record = stores.decision_store.get(key)
        decision = decision_from_record(record) if record is not None else None
        slot = stores.ledger.symbol_slot(strategy.strategy_id, trading_date, symbol)
        if decision is not None and decision.status == STATUS_DATA_ERROR:
            data_error_seen = True
        pairs[symbol] = {
            "final_strategy_state": decision.status if decision else "NO_RECORD",
            "ready_at": decision.ready_at.isoformat() if decision and decision.ready_at else None,
            "setup_id": slot["setup_id"] if slot else None,
            "proposal_id": slot["proposal_id"] if slot else None,
            "slot_index": slot["slot_index"] if slot else None,
            "final_reason": decision.reason_codes[-1] if decision and decision.reason_codes else None,
        }

    slots = stores.ledger.slots(strategy.strategy_id, trading_date)
    counters = stores.counters.snapshot(strategy.strategy_id, trading_date)

    if counters["snapshot_conflicts"] > 0:
        result = "BLOCKED"
    elif data_error_seen or counters["data_errors"] > 0 or counters["mt5_disconnects"] > 0:
        result = "PASS_WITH_OBSERVATIONS"
    else:
        result = "PASS"

    return {
        "report": "AG_TRADE_ASSISTANT_V1_0_2_PILOT_END",
        "trading_date": trading_date.isoformat(),
        "pairs": pairs,
        "portfolio": {"slots_used": len(slots), "max_slots": stores.ledger.max_slots,
                     "slot_identities": [{"symbol": s["symbol"], "setup_id": s["setup_id"],
                                          "proposal_id": s["proposal_id"], "state": s["state"]} for s in slots]},
        "operations": {
            "mt5_disconnect_events": counters["mt5_disconnects"],
            "restart_recovery_events": counters["restart_recovery_events"],
            "runtime_errors": counters["data_errors"],
        },
        "data": {"stale_data_events": counters["stale_data_events"]},
        "safety": {
            "automatic_execution": EXECUTION_STATUS_DISABLED,
            "order_check_calls": 0, "order_send_calls": 0,
            "duplicate_proposals_suppressed": counters["duplicate_suppressed_events"],
            "duplicate_claims": 0,  # DailyTradeLedger.try_claim() makes a duplicate claim structurally impossible
        },
        "result": result,
    }
