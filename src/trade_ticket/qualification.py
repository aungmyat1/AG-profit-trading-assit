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
import hashlib
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import yaml

from fx_opportunity.instruments import UnknownInstrumentError, get_instrument
from fx_opportunity.market_state import SCHEMA as MARKET_STATE_SCHEMA
from fx_opportunity.market_state import MarketState
from opportunity.contracts import OpportunityCandidate
from opportunity.registry_binding import StrategyBinding

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

AUTHORITY_SOURCE_REGISTRY = "REGISTRY"
AUTHORITY_SOURCE_PIPELINE_TEST = "PIPELINE_TEST_FIXTURE"

# Hashed into every ticket (policy_fingerprint): a change to these rules changes ticket identity.
QUALIFICATION_POLICY = {
    "version": "AG_TICKET_QUALIFICATION_V1_R1",
    "max_market_state_age_seconds": int(MAX_MARKET_STATE_AGE.total_seconds()),
    "targets_required": True,
    "expiry_fallback": "EXECUTION_WINDOW_END",
    "real_mode_authority": ("StrategyBinding.proposal_authority is True AND canonical-registry "
                            "proposal_authorization scope permits strategy_version/symbol/cycle/"
                            "market_data_mode AND registry fingerprint matches expected lineage"),
    "pipeline_test_authority": "none (no authority object; fixture binding claims no authority)",
}


def registry_fingerprint(registry_path: Optional[str] = None) -> str:
    """SHA-256 of the registry file bytes -- the lineage an authority was resolved from."""
    with open(registry_path or REGISTRY_PATH, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


@dataclass(frozen=True)
class ProposalAuthority:
    """Registry-resolved proposal authority and its exact scope. Only
    `resolve_proposal_authority` is meant to build one; `qualify` never trusts it
    alone -- it must agree with StrategyBinding and the expected registry lineage."""
    strategy_id: str
    proposal_authorized: bool
    source: str
    resolution: str  # AUTHORIZED | ENTRY_ABSENT | FIELD_ABSENT | NOT_AUTHORIZED | MALFORMED
    registry_path: str
    registry_fingerprint: str
    strategy_version: Optional[str] = None
    symbols: Tuple[str, ...] = ()
    cycles: Tuple[str, ...] = ()
    market_data_modes: Tuple[str, ...] = ()


def resolve_proposal_authority(strategy_id: str, registry_path: Optional[str] = None) -> ProposalAuthority:
    """Read-only. Authority exists only when the strategy's registry entry carries

        proposal_authorization: {authorized: true, strategy_version: <str>,
                                 symbols: [...], cycles: [...], market_data_modes: [...]}

    with every scope field present. No entry carries it today. Never writes the registry."""
    path = registry_path or REGISTRY_PATH
    with open(path, "rb") as fh:
        raw = fh.read()
    fp = hashlib.sha256(raw).hexdigest()
    entries = (yaml.safe_load(raw.decode("utf-8")) or {}).get("strategies") or {}
    base = dict(strategy_id=strategy_id, source=AUTHORITY_SOURCE_REGISTRY, registry_path=path,
                registry_fingerprint=fp)
    entry = entries.get(strategy_id)
    if entry is None:
        return ProposalAuthority(proposal_authorized=False, resolution="ENTRY_ABSENT", **base)
    block = entry.get("proposal_authorization")
    if block is None:
        return ProposalAuthority(proposal_authorized=False, resolution="FIELD_ABSENT", **base)
    scope = ("strategy_version", "symbols", "cycles", "market_data_modes")
    if (not isinstance(block, dict) or any(not block.get(k) for k in scope)
            or not isinstance(block["strategy_version"], str)
            or not all(isinstance(block[k], list) for k in scope[1:])):
        return ProposalAuthority(proposal_authorized=False, resolution="MALFORMED", **base)
    authorized = block.get("authorized") is True
    return ProposalAuthority(
        proposal_authorized=authorized, resolution="AUTHORIZED" if authorized else "NOT_AUTHORIZED",
        strategy_version=block["strategy_version"], symbols=tuple(block["symbols"]),
        cycles=tuple(block["cycles"]), market_data_modes=tuple(block["market_data_modes"]), **base)


def _real_authority_denials(candidate: OpportunityCandidate, binding: StrategyBinding, cycle: str,
                            authority: Optional[ProposalAuthority],
                            expected_registry_fingerprint: Optional[str]) -> List[str]:
    """Every disagreement, in fixed order. Neither representation can override the other."""
    reasons: List[str] = []
    if binding.strategy_id != candidate.strategy_id:
        reasons.append("BINDING_STRATEGY_MISMATCH")
    if binding.proposal_authority is not True:
        reasons.append("BINDING_PROPOSAL_AUTHORITY_FALSE")
    if authority is None:
        return reasons + ["AUTHORITY_MISSING"]
    if authority.strategy_id != candidate.strategy_id:
        reasons.append("AUTHORITY_STRATEGY_MISMATCH")
    if authority.source != AUTHORITY_SOURCE_REGISTRY:
        reasons.append("AUTHORITY_SOURCE_NOT_REGISTRY")
    if authority.registry_path != REGISTRY_PATH:
        reasons.append("AUTHORITY_REGISTRY_PATH_NOT_CANONICAL")
    if not expected_registry_fingerprint or authority.registry_fingerprint != expected_registry_fingerprint:
        reasons.append("AUTHORITY_REGISTRY_LINEAGE_MISMATCH")
    if authority.proposal_authorized is not True:
        reasons.append(f"PROPOSAL_AUTHORITY_{authority.resolution}")
        return reasons
    if authority.strategy_version != candidate.strategy_version:
        reasons.append("AUTHORITY_STRATEGY_VERSION_MISMATCH")
    if candidate.symbol not in authority.symbols:
        reasons.append("AUTHORITY_SYMBOL_NOT_PERMITTED")
    if cycle not in authority.cycles:
        reasons.append("AUTHORITY_CYCLE_NOT_PERMITTED")
    if candidate.market_data_mode not in authority.market_data_modes:
        reasons.append("AUTHORITY_DATA_MODE_NOT_PERMITTED")
    return reasons


def _authority_provenance(mode: str, authority: Optional[ProposalAuthority]) -> Dict[str, Any]:
    """Immutable, JSON-plain record of the authority actually used (no secrets, no objects)."""
    if mode == MODE_PIPELINE_TEST:
        return {"source": AUTHORITY_SOURCE_PIPELINE_TEST, "strategy_authority": "NONE"}
    return {"source": authority.source, "resolution": authority.resolution,
            "registry_path": authority.registry_path, "registry_fingerprint": authority.registry_fingerprint,
            "strategy_version": authority.strategy_version, "symbols": list(authority.symbols),
            "cycles": list(authority.cycles), "market_data_modes": list(authority.market_data_modes),
            "binding_proposal_authority": True}


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
    authority_provenance: Dict[str, Any] = field(default_factory=dict)

    @property
    def qualified(self) -> bool:
        return self.status == QUALIFIED


def _iso_to_dt(value: Optional[str]) -> Optional[dt.datetime]:
    return dt.datetime.fromisoformat(value) if value else None


def qualify(
    *,
    candidate: OpportunityCandidate,
    market_state: Optional[MarketState],
    binding: StrategyBinding,
    cycle: str,
    mode: str,
    authority: Optional[ProposalAuthority],
    evaluated_at: dt.datetime,
    expected_registry_fingerprint: Optional[str] = None,
) -> QualificationResult:
    """Deterministic for identical inputs. Gates run in fixed order and stop at the
    first failing gate: mode/authority -> data consistency -> look-ahead -> staleness
    -> setup presence -> trade-plan completeness.

    REAL_STRATEGY_MODE: StrategyBinding and the registry-resolved ProposalAuthority must
    BOTH affirm authority for this exact strategy/version/symbol/cycle/data mode, from the
    canonical registry at the expected fingerprint. PIPELINE_TEST_MODE: no authority
    object is accepted and the fixture binding must claim none."""
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
    if mode == MODE_REAL:
        denials = _real_authority_denials(candidate, binding, cycle, authority, expected_registry_fingerprint)
    else:
        denials = []
        if authority is not None:
            denials.append("AUTHORITY_NOT_ALLOWED_IN_PIPELINE_TEST")
        if binding.strategy_id != candidate.strategy_id:
            denials.append("BINDING_STRATEGY_MISMATCH")
        if binding.proposal_authority or binding.execution_authority != "NONE":
            denials.append("FIXTURE_BINDING_CLAIMS_AUTHORITY")
    if denials:
        return result(NO_PROPOSAL_AUTHORITY, *denials)
    base["authority_provenance"] = _authority_provenance(mode, authority)

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
