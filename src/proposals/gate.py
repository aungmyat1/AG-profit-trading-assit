"""generate_proposals() -- the deterministic gate (spec section 31). A proposal is
emitted ONLY for a combination the composer already marked READY (qualified E + valid M
+ direction alignment + entry array + not invalidated -- entirely composer.py's own
gating, never re-checked or loosened here). Everything else -- WAITING, direction
mismatch, INVALIDATED, EXPIRED, missing entry array -- produces NO proposal (spec
section 65: multiple simultaneous READY combinations are all returned, unranked).
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Dict, Optional, Sequence, Tuple

from entry_confirmation.entry_models_v1 import EntryModelState, SMCConditionalEntryAnalysis, SMCEntryCombinationResult
from entry_confirmation.m1_character_change_inducement import M1Result
from entry_confirmation.m2_supply_demand_shift import M2Result

from .models import STATUS_ENTRY_CANDIDATE_READY, SMCTradeProposal


def _proposal_id(symbol: str, combination: str, snapshot_time: Optional[str]) -> str:
    digest = hashlib.blake2b(f"{symbol}|{combination}|{snapshot_time}".encode("utf-8"), digest_size=6).hexdigest()
    return f"PROPOSAL-{symbol}-{combination}-{digest}"


def _matching_m_result(analysis: SMCConditionalEntryAnalysis, combo: SMCEntryCombinationResult):
    for r in analysis.m_maneuvers.get(combo.maneuver, ()):
        if r.direction == combo.direction and r.state == combo.state:
            return r
    return None


def _entry_range(m_result) -> Tuple[Optional[float], Optional[float]]:
    """Only M1 currently exposes an explicit entry-array PRICE RANGE (entry_array_low/
    high); M2 exposes a zone object (entry_fvg/entry_ob) with its own low/high; M3
    exposes only a single entry_level, no range. Returning (None, None) for those is
    the honest answer, not a gap to paper over -- see models.py's invalidation_state
    docstring for the same discipline applied to invalidation."""
    if isinstance(m_result, M1Result):
        return m_result.entry_array_low, m_result.entry_array_high
    if isinstance(m_result, M2Result):
        zone = m_result.entry_fvg or m_result.entry_ob
        if zone is not None:
            low = getattr(zone, "low", None)
            high = getattr(zone, "high", None)
            if zone.__class__.__name__ == "ValidatedOrderBlock" and zone.candidate is not None:
                low, high = zone.candidate.low, zone.candidate.high
            return low, high
    return None, None


def generate_proposals(analysis: SMCConditionalEntryAnalysis,
                        market_map_snapshot_id: Optional[str] = None) -> Tuple[SMCTradeProposal, ...]:
    snapshot_time = analysis.snapshot_time.isoformat() if analysis.snapshot_time is not None else None
    proposals = []

    for combo in analysis.combinations:
        if combo.state != EntryModelState.READY.value:
            continue

        m_result = _matching_m_result(analysis, combo)
        entry_low, entry_high = _entry_range(m_result) if m_result is not None else (None, None)

        proposals.append(SMCTradeProposal(
            proposal_id=_proposal_id(analysis.symbol, combo.combination, snapshot_time),
            snapshot_time=snapshot_time, symbol=analysis.symbol,
            combination=combo.combination, entry_condition=combo.entry_condition, maneuver=combo.maneuver,
            direction=combo.direction,
            reference_timeframe=combo.reference_timeframe, check_timeframe=combo.check_timeframe,
            confirmation_timeframe=combo.confirmation_timeframe, execution_timeframe=combo.execution_timeframe,
            entry_type=combo.entry_array, entry_low=entry_low, entry_high=entry_high,
            entry_reference=combo.entry_price,
            invalidation_state=combo.invalidation,
            evidence=dict(combo.evidence), missing_conditions=combo.missing_conditions,
            market_map_snapshot_id=market_map_snapshot_id, status=STATUS_ENTRY_CANDIDATE_READY,
        ))

    return tuple(proposals)
