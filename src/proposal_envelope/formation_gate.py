"""WP6 Proposal Formation Gate (AG_CANONICAL_R2_R4_PROPOSAL_PIPELINE_V1).

Technical completeness gate only -- never an economic/edge decision. Each per-family
adapter in proposal_envelope/adapters/ already enforces per-family missing-required-field
-> BLOCKED (see each adapter's own module docstring and "missing required field" tests).
This module applies the one cross-family check none of them can perform on their own:
REAL market-data-mode enforcement, using WP1's MarketSnapshot contract
(strategy_contract/market_snapshot.py) and WP4's propagation pattern. A PROPOSAL_READY
envelope backed by REPLAY, SYNTHETIC, or missing market-data-mode provenance is
downgraded to PROPOSAL_BLOCKED here -- it never silently becomes an operational canonical
proposal, matching the plan's "mixed-mode chains fail closed" invariant.

Freshness vs. lifecycle expiry, kept distinct per the plan: `envelope.plan_expires_at` /
`timestamps.expires_at` already represent LIFECYCLE expiry (owned by each adapter, from
the source strategy's own valid_until/expiry field) -- untouched here.
`data_provenance.market_data_mode/asof/fingerprint` represents MARKET provenance/
freshness, a distinct concept this gate adds; the two are never conflated into one field.

This gate does not construct a proposal from nothing and does not repair missing
geometry -- it only ever narrows an already-PROPOSAL_READY envelope to PROPOSAL_BLOCKED,
never the reverse.
"""
from __future__ import annotations

import dataclasses
from typing import Optional

from strategy_contract.market_snapshot import MARKET_DATA_MODE_REAL, MarketSnapshot

from .models import CanonicalProposal, PROPOSAL_BLOCKED, PROPOSAL_READY

REASON_NON_REAL_MARKET_MODE = "NON_REAL_MARKET_MODE"
REASON_MISSING_MARKET_SNAPSHOT = "MISSING_MARKET_SNAPSHOT"


def apply_formation_gate(
    envelope: CanonicalProposal, market_snapshot: Optional[MarketSnapshot] = None,
) -> CanonicalProposal:
    """Only acts on PROPOSAL_READY envelopes -- every other proposal_state (NO_TRADE,
    INCOMPLETE, BLOCKED, EXPIRED, INVALIDATED, STRATEGY_UNMATCHED) already correctly
    excludes proposal formation upstream in the adapter and is returned unchanged.

    Never invents a market_snapshot when one isn't supplied -- a PROPOSAL_READY envelope
    with no market_snapshot is technically incomplete for REAL operational formation and
    is rejected the same as a wrong-mode one, per the plan's fail-closed invariant."""
    if envelope.proposal_state != PROPOSAL_READY:
        return envelope

    if market_snapshot is None:
        return dataclasses.replace(
            envelope, proposal_state=PROPOSAL_BLOCKED,
            reasons=envelope.reasons + (REASON_MISSING_MARKET_SNAPSHOT,),
        )

    provenance = dataclasses.replace(
        envelope.data_provenance,
        market_data_mode=market_snapshot.market_data_mode,
        market_data_asof=market_snapshot.market_data_asof.isoformat(),
        market_data_fingerprint=market_snapshot.fingerprint,
    )

    if market_snapshot.market_data_mode != MARKET_DATA_MODE_REAL:
        return dataclasses.replace(
            envelope, proposal_state=PROPOSAL_BLOCKED, data_provenance=provenance,
            reasons=envelope.reasons + (REASON_NON_REAL_MARKET_MODE,),
        )

    return dataclasses.replace(envelope, data_provenance=provenance)
