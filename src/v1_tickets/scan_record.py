"""Manual Trade Ticket V1 Phase 3 -- one scan record per (strategy, symbol, session) per run.

Every scheduled FX run appends a record for every configured symbol, including "ran,
nothing found", so a missing record (state NOT_RUN in `coverage`) is distinguishable
from NO_SETUP. Records are append-only JSONL in the existing journal store
(journal/ticket_delivery/manual/scan_records/<date>.jsonl). No broker access.

States: NO_SETUP | WATCH | OPPORTUNITY | TICKET_BLOCKED | TICKET_READY. TICKET_READY is a
manual analysis artifact only -- never ORDER_READY, BROKER_AUTHORIZED or EDGE_VERIFIED.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from v1_tickets.guards import PENDING_BAR_CLOSE, SIGNAL_STALE  # noqa: F401  (canonical; re-exported for readers)

NO_SETUP, WATCH, OPPORTUNITY, TICKET_BLOCKED, TICKET_READY = (
    "NO_SETUP", "WATCH", "OPPORTUNITY", "TICKET_BLOCKED", "TICKET_READY")
REFERENCE_NOT_READY = "REFERENCE_NOT_READY"     # ran before the reference window closed (lifecycle)
TICKET_EXPIRED = "TICKET_EXPIRED"               # actionable ticket past valid_until
STATES = (REFERENCE_NOT_READY, NO_SETUP, WATCH, OPPORTUNITY, TICKET_BLOCKED, TICKET_READY)
NOT_RUN = "NOT_RUN"
STAGES = ("AUTHORITY", "SESSION", "DATA", "ENGINE", "LOGIC_GATE", "RISK", "TICKET")
# Engine reasons that are final regardless of the clock; others may still change before window end.
_OPEN_WINDOW_REASONS = {"NO_QUALIFIED_SWEEP_IN_WINDOW", "NO_SETUP_BY_WINDOW_END"}
SCAN_DIR = os.path.join("ticket_delivery", "manual", "scan_records")


@dataclass(frozen=True)
class ScanRecord:
    scheduler_run_id: str
    session: str
    symbol: str
    strategy: str                 # strategy_id@version
    session_anchor_tz: str        # signed rules are fixed UTC (owner decision C3)
    window_start_utc: Optional[str]
    window_end_utc: Optional[str]
    data_freshness_s: Optional[float]
    stage_reached: str
    state: str
    stop_reason: Optional[str]
    created_at: str
    ticket_id: Optional[str] = None
    block_reasons: Tuple[str, ...] = ()          # ordered by severity; stop_reason == block_reasons[0] alias
    primary_block_reason: Optional[str] = None
    warnings: Tuple[str, ...] = ()               # advisory only (e.g. L5_WARN); never blocks
    code_sha: str = "UNKNOWN"                    # git HEAD at process start (code_identity), never fatal

    def __post_init__(self) -> None:
        if self.state not in STATES:
            raise ValueError(f"state {self.state!r} not in {STATES}")
        if self.stage_reached not in STAGES:
            raise ValueError(f"stage_reached {self.stage_reached!r} not in {STAGES}")


def classify_fx_ticket(ticket: Dict[str, Any], *, now: dt.datetime, window_end: dt.datetime) -> Tuple[str, str, str]:
    """(state, stage_reached, stop_reason) from an existing V1 FX ticket, before manual gates."""
    decision = ticket.get("decision")
    reason = ticket.get("reason_code")
    if decision == REFERENCE_NOT_READY:
        return REFERENCE_NOT_READY, "SESSION", reason
    if decision == "DATA_ERROR":
        return TICKET_BLOCKED, "DATA", f"DATA_ERROR:{reason}"
    if decision == "BLOCKED":
        return TICKET_BLOCKED, "DATA", reason
    if ticket.get("suppressed_decision") == "READY" or decision == "READY":
        if decision == "READY":
            return TICKET_READY, "TICKET", None
        if decision == PENDING_BAR_CLOSE:          # D4: not stale; re-evaluated once the bar closes
            return WATCH, "TICKET", f"{PENDING_BAR_CLOSE}:{reason}"
        # Canonical stale/expiry semantics: a signal that aged out before any actionable ticket
        # existed is SIGNAL_STALE (legacy reason code STALE_SIGNAL stays on the legacy ticket);
        # TICKET_EXPIRED is reserved for an already-actionable ticket past valid_until.
        return TICKET_BLOCKED, "TICKET", SIGNAL_STALE if decision == "STALE" else reason
    if decision == "STALE":
        return TICKET_BLOCKED, "DATA", reason
    if decision == "NO_TRADE":
        if reason in _OPEN_WINDOW_REASONS and now < window_end:
            return WATCH, "ENGINE", f"SETUP_WINDOW_OPEN:{reason}"
        return NO_SETUP, "ENGINE", reason
    return TICKET_BLOCKED, "ENGINE", f"UNMAPPED_DECISION:{decision}"     # fail closed


def build_scan_record(*, run_id: str, session: str, symbol: str, strategy_id: str, strategy_version: str,
                      window: Optional[Tuple[dt.datetime, dt.datetime]], data_close: Optional[dt.datetime],
                      state: str, stage: str, stop_reason: Optional[str], now: dt.datetime,
                      ticket_id: Optional[str] = None,
                      block_reasons: Optional[Sequence[str]] = None,
                      warnings: Sequence[str] = ()) -> ScanRecord:
    from v1_tickets.code_identity import code_sha
    from v1_tickets.logic_gate import LIFECYCLE_STATES, order_block_reasons
    ordered = tuple(order_block_reasons(block_reasons if block_reasons is not None else [stop_reason]))
    return ScanRecord(
        scheduler_run_id=run_id, session=session, symbol=symbol, strategy=f"{strategy_id}@{strategy_version}",
        session_anchor_tz="UTC",
        window_start_utc=window[0].isoformat() if window else None,
        window_end_utc=window[1].isoformat() if window else None,
        data_freshness_s=round((now - data_close).total_seconds(), 3) if data_close else None,
        stage_reached=stage, state=state, stop_reason=stop_reason, created_at=now.isoformat(),
        ticket_id=ticket_id, block_reasons=ordered,
        primary_block_reason=(stop_reason if state not in (TICKET_READY, REFERENCE_NOT_READY)
                              and stop_reason not in LIFECYCLE_STATES else None),
        warnings=tuple(warnings), code_sha=code_sha(),
    )


def append_jsonl(path: str, entry: Dict[str, Any]) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True, default=str) + "\n")


def read_jsonl(path: str) -> List[Dict[str, Any]]:
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def scan_path(journal: str, day: dt.date) -> str:
    return os.path.join(journal, SCAN_DIR, f"{day.isoformat()}.jsonl")


def write_scan_record(journal: str, record: ScanRecord) -> str:
    path = scan_path(journal, dt.date.fromisoformat(record.created_at[:10]))
    append_jsonl(path, asdict(record))
    return path


def coverage(records: Iterable[Dict[str, Any]], run_id: str,
             expected: Sequence[Tuple[str, str, str]]) -> Dict[Tuple[str, str, str], str]:
    """expected: (strategy@version, session, symbol). Missing -> NOT_RUN (not NO_SETUP)."""
    seen = {(r["strategy"], r["session"], r["symbol"]): r["state"] for r in records
            if r.get("scheduler_run_id") == run_id}
    return {key: seen.get(key, NOT_RUN) for key in expected}


SESSION_TRADE_V1_CONTRACT = "strategies/session_trade/contract.yaml"


def adapterless_scan_records(*, run_id: str, cycle: str, now: dt.datetime, root: Optional[str] = None,
                             window: Optional[Tuple[dt.datetime, dt.datetime]] = None) -> List[ScanRecord]:
    """Scanner-visible records for SESSION_TRADE_V1 (owner decision C1): its engine is not in
    this repo, so every ACTIVE-cycle symbol is TICKET_BLOCKED with the authority reason and
    no strategy logic is evaluated, borrowed or inferred."""
    import yaml
    from v1_tickets.authority import REPO_ROOT, resolve_ticket_authority

    base = root or str(REPO_ROOT)
    with open(os.path.join(base, SESSION_TRADE_V1_CONTRACT), "r", encoding="utf-8") as f:
        contract = yaml.safe_load(f)
    if (contract.get("supported_cycles") or {}).get(cycle, {}).get("status") != "ACTIVE":
        return []
    sid, version = contract["strategy_id"], str(contract["version"])
    authority = resolve_ticket_authority(sid, version)
    if not authority.scanner_visible or authority.ticket_eligible:
        return []          # ticket-eligible strategies are scanned by their own adapter
    return [build_scan_record(run_id=run_id, session=cycle, symbol=s, strategy_id=sid, strategy_version=version,
                              window=window, data_close=None, state=TICKET_BLOCKED, stage="AUTHORITY",
                              stop_reason=authority.reason, now=now)
            for s in contract.get("supported_symbols") or ()]
