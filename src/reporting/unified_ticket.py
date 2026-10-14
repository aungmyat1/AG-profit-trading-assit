"""Versioned presentation record; never an execution authority source.

Raw diagnostic evidence is archived separately from the renderer's validated
fields. Missing values remain None with explicit reasons, never invented prices.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

SCHEMA_VERSION = "AGP_REPORTING_TICKET_V2"


@dataclass(frozen=True)
class ReportingTicket:
    schema_version: str = SCHEMA_VERSION
    ticket_id: Optional[str] = None
    strategy_id: Optional[str] = None
    strategy_version: Optional[str] = None
    contract_hash: Optional[str] = None
    scope_id: Optional[str] = None
    broker_symbol: Optional[str] = None
    display_symbol: Optional[str] = None
    poi_id: Optional[str] = None
    reporting_lane: str = "REPORT_ONLY"
    verification_status: str = "NOT_VERIFIED"
    demo_authorization_status: str = "NOT_AUTHORIZED_BY_REPORT"
    opportunity_status: str = "BLOCKED"
    previous_poi_state: Optional[str] = None
    current_poi_state: Optional[str] = None
    execution_status: str = "DISABLED"
    direction: Optional[str] = None
    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    calculated_rr: Optional[float] = None
    minimum_rr: Optional[float] = None
    geometry_verdict: str = "NOT_EVALUATED"
    spread_pips: Optional[float] = None
    spread_r: Optional[float] = None
    stop_distance_pips: Optional[float] = None
    cost_verdict: str = "INSUFFICIENT"
    cost_evidence_status: str = "NOT_EVIDENCED"
    market_data_timestamp_utc: Optional[str] = None
    evaluated_at_utc: Optional[str] = None
    expires_at_utc: Optional[str] = None
    freshness_verdict: str = "NOT_EVIDENCED"
    decisive_block_reason: Optional[str] = None
    secondary_block_reasons: tuple[str, ...] = ()
    current_price: Optional[float] = None
    entry_distance_pips: Optional[float] = None
    digits: Optional[int] = None
    pip_size: Optional[float] = None
    spread_limit_pips: Optional[float] = None
    notes: tuple[str, ...] = ()
    raw_evidence: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    def evidence_record(self) -> dict[str, Any]:
        """Journal projection including originals, not a broker or proposal input."""
        return asdict(self)
