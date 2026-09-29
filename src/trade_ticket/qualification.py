"""StrategyQualification: the thin gate between an Opportunity and the existing
ProposalEligibility boundary.

    MarketState + OpportunityCandidate + proposal authority -> QualificationResult

It answers: is this candidate a strategy-owned, current, consistently-evidenced setup
from a strategy that may form proposals in this mode? It does NOT re-check geometry
(finite / side / entry != stop) -- that remains the sole job of
opportunity.proposal_eligibility, called next. No execution authority, no I/O except
the read-only registry lookup in `resolve_proposal_authority`.

CUSTOM_BUILD_REASON = NO_ACCEPTABLE_EXISTING_OR_OSS_COMPONENT: no existing module ties
MarketState provenance, the Opportunity candidate and proposal authority together, and
no OSS component carries AG's authority model.
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

import yaml

from fx_opportunity.instruments import UnknownInstrumentError, get_instrument
from fx_opportunity.market_state import SCHEMA as MARKET_STATE_SCHEMA
from fx_opportunity.market_state import MarketState
from opportunity.contracts import OpportunityCandidate

MODE_REAL = "REAL_STRATEGY_MODE"
MODE_PIPELINE_TEST = "PIPELINE_TEST_MODE"
MODES = frozenset({MODE_REAL, MODE_PIPELINE_TEST})
# Reserved namespace: never a registry entry, never market-authoritative.
PIPELINE_TEST_PREFIX = "PIPELINE_TEST_"

QUALIFIED = "QUALIFIED"
NO_SETUP = "NO_SETUP"
NO_PROPOSAL_AUTHORITY = "NO_PROPOSAL_AUTHORITY"
STALE = "STALE"
DATA_INVALID = "DATA_INVALID"
INCOMPLETE_TRADE_PLAN = "INCOMPLETE_TRADE_PLAN"

# One closed M15 bar: a MarketState older than this at evaluation time is stale.
MAX_MARKET_STATE_AGE = dt.timedelta(minutes=15)

REGISTRY_PATH = "strategies/registry.yaml"

# Hashed into every ticket (policy_fingerprint): a change to these rules changes ticket identity.
QUALIFICATION_POLICY = {
    "version": "AG_TICKET_QUALIFICATION_V1",
    "max_market_state_age_seconds": int(MAX_MARKET_STATE_AGE.total_seconds()),
    "targets_required": True,
    "expiry_fallback": "EXECUTION_WINDOW_END",
    "real_mode_authority": "registry proposal_authorized is True",
}


@dataclass(frozen=True)
class ProposalAuthority:
    strategy_id: str
    proposal_authorized: bool
    source: str


def resolve_proposal_authority(strategy_id: str, registry_path: str = REGISTRY_PATH) -> ProposalAuthority:
    """Read-only. Only a literal `proposal_authorized: true` on the strategy's own
    registry entry grants authority; absence is NONE. Never writes the registry."""
    with open(registry_path, "r", encoding="utf-8") as fh:
        entries = (yaml.safe_load(fh) or {}).get("strategies") or {}
    entry = entries.get(strategy_id)
    if entry is None:
        return ProposalAuthority(strategy_id, False, "REGISTRY_ENTRY_ABSENT")
    if "proposal_authorized" not in entry:
        return ProposalAuthority(strategy_id, False, "REGISTRY_FIELD_ABSENT")
    return ProposalAuthority(strategy_id, entry["proposal_authorized"] is True, "REGISTRY")


def pipeline_test_authority(strategy_id: str) -> ProposalAuthority:
    """Authority for a reserved-namespace fixture strategy -- PIPELINE_TEST_MODE only."""
    if not strategy_id.startswith(PIPELINE_TEST_PREFIX):
        raise ValueError(f"{strategy_id!r} is not in the {PIPELINE_TEST_PREFIX} namespace")
    return ProposalAuthority(strategy_id, True, "PIPELINE_TEST_FIXTURE")


@dataclass(frozen=True)
class QualificationResult:
    status: str
    reason_codes: Tuple[str, ...]
    mode: str
    strategy_id: str
    strategy_version: str
    symbol: str
    cycle: str
    candidate_id: str
    direction: Optional[str] = None
    entry: Optional[float] = None
    stop: Optional[float] = None
    targets: Tuple[float, ...] = ()
    invalidation: Optional[float] = None
    expires_at: Optional[str] = None
    expiry_source: Optional[str] = None
    evidence: Dict[str, Any] = field(default_factory=dict)
    data_provenance: Dict[str, Any] = field(default_factory=dict)

    @property
    def qualified(self) -> bool:
        return self.status == QUALIFIED


def _iso_to_dt(value: Optional[str]) -> Optional[dt.datetime]:
    return dt.datetime.fromisoformat(value) if value else None


def qualify(
    *,
    candidate: OpportunityCandidate,
    market_state: Optional[MarketState],
    cycle: str,
    mode: str,
    authority: ProposalAuthority,
    evaluated_at: dt.datetime,
) -> QualificationResult:
    """Deterministic for identical inputs. Gates run in fixed order and stop at the
    first failing gate: mode/authority -> data consistency -> look-ahead -> staleness
    -> setup presence -> trade-plan completeness."""
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}")
    if evaluated_at.tzinfo is None:
        raise ValueError("evaluated_at must be timezone-aware")

    base = dict(mode=mode, strategy_id=candidate.strategy_id, strategy_version=candidate.strategy_version,
                symbol=candidate.symbol, cycle=cycle, candidate_id=candidate.candidate_id)

    def result(status: str, *reasons: str, **extra: Any) -> QualificationResult:
        return QualificationResult(status=status, reason_codes=tuple(reasons), **base, **extra)

    # (1) authority and mode namespace
    is_test_id = candidate.strategy_id.startswith(PIPELINE_TEST_PREFIX)
    if mode == MODE_REAL and is_test_id:
        return result(NO_PROPOSAL_AUTHORITY, "PIPELINE_TEST_STRATEGY_IN_REAL_MODE")
    if mode == MODE_PIPELINE_TEST and not is_test_id:
        return result(NO_PROPOSAL_AUTHORITY, "REAL_STRATEGY_IN_PIPELINE_TEST_MODE")
    if authority.strategy_id != candidate.strategy_id:
        return result(NO_PROPOSAL_AUTHORITY, "AUTHORITY_STRATEGY_MISMATCH")
    if not authority.proposal_authorized:
        return result(NO_PROPOSAL_AUTHORITY, f"PROPOSAL_AUTHORITY_{authority.source}")

    # (2) supported symbol/cycle, then MarketState <-> candidate consistency
    try:
        instrument = get_instrument(candidate.symbol)
    except UnknownInstrumentError:
        return result(DATA_INVALID, "SYMBOL_NOT_IN_INSTRUMENT_CONTRACT")
    if cycle not in instrument.allowed_cycles:
        return result(DATA_INVALID, "UNSUPPORTED_CYCLE")
    if market_state is None:
        return result(DATA_INVALID, "MARKET_STATE_MISSING")
    if market_state.schema != MARKET_STATE_SCHEMA:
        return result(DATA_INVALID, "MARKET_STATE_SCHEMA_MISMATCH")
    if market_state.symbol != candidate.symbol:
        return result(DATA_INVALID, "MARKET_STATE_SYMBOL_MISMATCH")
    if market_state.cycle != cycle:
        return result(DATA_INVALID, "MARKET_STATE_CYCLE_MISMATCH")
    if market_state.market_data_mode != candidate.market_data_mode:
        return result(DATA_INVALID, "MARKET_DATA_MODE_MISMATCH")
    if not market_state.reference_complete:
        return result(DATA_INVALID, "REFERENCE_SESSION_INCOMPLETE")
    if not all(isinstance(v, (int, float)) and math.isfinite(v)
               for v in (market_state.reference_high, market_state.reference_low)):
        return result(DATA_INVALID, "MARKET_STATE_NONFINITE")

    # (3) look-ahead contamination
    as_of = _iso_to_dt(market_state.as_of)
    last_close = _iso_to_dt((market_state.last_closed_bar or {}).get("close_utc"))
    if (as_of > evaluated_at or (last_close is not None and last_close > as_of)
            or candidate.last_evaluated_at > evaluated_at):
        return result(DATA_INVALID, "LOOKAHEAD_CONTAMINATION")

    # (4) staleness
    if evaluated_at - as_of > MAX_MARKET_STATE_AGE:
        return result(STALE, "MARKET_STATE_STALE")
    window_end = _iso_to_dt(market_state.execution_window_utc[1])
    expires = candidate.expires_at or window_end
    expiry_source = "CANDIDATE" if candidate.expires_at is not None else "EXECUTION_WINDOW_END"
    if expires is None:
        return result(INCOMPLETE_TRADE_PLAN, "MISSING_EXPIRY")
    if expires <= evaluated_at:
        return result(STALE, "OPPORTUNITY_EXPIRED")

    # (5) strategy-owned setup present
    g = candidate.geometry
    if g is None or g.direction is None or g.entry is None or g.invalidation is None:
        return result(NO_SETUP, "NO_STRATEGY_GEOMETRY")

    plan = dict(direction=g.direction, entry=g.entry, stop=g.invalidation, invalidation=g.invalidation,
                targets=tuple(g.targets), expires_at=expires.isoformat(), expiry_source=expiry_source,
                evidence={"context": dict(candidate.context_evidence), "setup": dict(candidate.setup_evidence),
                          "trigger": dict(candidate.trigger_evidence), "stage": candidate.stage,
                          "outcome": candidate.outcome},
                data_provenance={"market_state_fingerprint": market_state.fingerprint,
                                 "market_data_mode": market_state.market_data_mode,
                                 "source": market_state.source, "as_of": market_state.as_of,
                                 "instrument_fingerprint": market_state.instrument_fingerprint,
                                 "data_lineage": candidate.data_lineage})

    # (6) complete plan: targets must be strategy-owned, never invented here
    if not g.targets:
        return result(INCOMPLETE_TRADE_PLAN, "TARGETS_NOT_STRATEGY_OWNED", **plan)
    return result(QUALIFIED, **plan)
