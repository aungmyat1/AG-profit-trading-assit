"""AG Scanner Checklist V1.1 -- structured deterministic phase gates over frozen Scanner V1.

    FROZEN SCANNER V1 (scanner.py / checklist.py -- unchanged authority)
        -> PHASE 0 DATA INTEGRITY   (consumes V1's final gates only; never re-fetches)
        -> PHASE 1 CONTEXT          (session + D1/H1 structure alignment; permission, not entry)
        -> PHASE 2 LOCATION         (strategy-authorized POI engagement)
        -> PHASE 3 TRIGGER          (wraps the strategy engine; preserves expired-signal and
                                     TREND-timing invariants of Scanner V1 verbatim)
        -> PHASE 4 RISK             (pilot risk authority + contract geometry)
        -> PHASE 5 PROPOSAL ELIGIBILITY
        -> READY_FOR_PROPOSAL | NO_TRADE | BLOCKED | INSUFFICIENT_DATA | OUT_OF_SESSION

Phases are SEQUENTIAL GATES, never a score: a mandatory earlier phase FAIL/BLOCKED makes
proposal eligibility impossible, regardless of later phases. The layer is READ_ONLY,
DETERMINISTIC, FAIL_CLOSED and NON_EXECUTING: it contains no broker-mutation import and
``execution_authorized`` is a constant False everywhere.

Status vocabulary is the single shared model below (PhaseStatus); reason codes are the
single shared taxonomy (ReasonCode). Scanner V1's ``time_gate`` field is consumed under its
canonical key only (no parallel ``gate`` alias is introduced). Scanner V1's flat checklist
output remains untouched -- this module is purely additive.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from .strategy_adapter import (ADAPTER_BOX_INCOMPLETE, ADAPTER_SIGNAL, ADAPTER_SYMBOL_NOT_IN_CONTRACT)
from .timebase import TIME_GATE_PASS

CHECKLIST_VERSION = "AG_SCANNER_CHECKLIST_V1_1"

# Scanner V1 final-result keys this layer consumes (Phase 0 contract).
_GATE_PASS = "PASS"


# ------------------------------------------------------------------ shared phase-status model

class PhaseStatus(str, Enum):
    """The ONLY status vocabulary for Checklist V1.1 phases."""

    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    INCOMPLETE_CONTRACT = "INCOMPLETE_CONTRACT"


class ChecklistResult(str, Enum):
    """Final per-instrument decision states of Checklist V1.1."""

    READY_FOR_PROPOSAL = "READY_FOR_PROPOSAL"
    NO_TRADE = "NO_TRADE"
    BLOCKED = "BLOCKED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    OUT_OF_SESSION = "OUT_OF_SESSION"


class StructureState(str, Enum):
    """Allowed structure vocabulary -- a market is never forced into bullish/bearish."""

    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    RANGE = "RANGE"
    MIXED = "MIXED"
    INSUFFICIENT = "INSUFFICIENT"


class DirectionPermission(str, Enum):
    """Context permission. Permission is not an entry signal."""

    LONG_ALLOWED = "LONG_ALLOWED"
    SHORT_ALLOWED = "SHORT_ALLOWED"
    BOTH_ALLOWED = "BOTH_ALLOWED"
    NO_DIRECTION = "NO_DIRECTION"


# ------------------------------------------------------------------ reason-code taxonomy

class ReasonCode(str, Enum):
    """Stable machine-readable reason codes (mission section 12 taxonomy)."""

    # Data
    DATA_STALE = "DATA_STALE"
    DATA_GAPPED = "DATA_GAPPED"
    DATA_INVALID = "DATA_INVALID"
    SOURCE_MISMATCH = "SOURCE_MISMATCH"
    TIME_AUTHORITY_INVALID = "TIME_AUTHORITY_INVALID"
    # Context
    OUT_OF_SESSION = "OUT_OF_SESSION"
    HTF_DIRECTION_CONFLICT = "HTF_DIRECTION_CONFLICT"
    NEWS_POLICY_NOT_DEFINED = "NEWS_POLICY_NOT_DEFINED"
    # Location
    LOCATION_NOT_REACHED = "LOCATION_NOT_REACHED"
    STRATEGY_CONTRACT_INCOMPLETE = "STRATEGY_CONTRACT_INCOMPLETE"
    # Trigger
    NO_TRIGGER = "NO_TRIGGER"
    SIGNAL_ENTRY_WINDOW_PASSED = "SIGNAL_ENTRY_WINDOW_PASSED"
    ENTRY_TIMING_NOT_DEFINED_FOR_SETUP = "ENTRY_TIMING_NOT_DEFINED_FOR_SETUP"
    # Risk
    RISK_POLICY_AMBIGUOUS = "RISK_POLICY_AMBIGUOUS"
    INVALID_STOP_DISTANCE = "INVALID_STOP_DISTANCE"
    RR_POLICY_FAILED = "RR_POLICY_FAILED"
    # Costs / proposal
    SPREAD_POLICY_UNDEFINED = "SPREAD_POLICY_UNDEFINED"
    SPREAD_TOO_WIDE = "SPREAD_TOO_WIDE"
    PROPOSAL_NOT_AUTHORIZED = "PROPOSAL_NOT_AUTHORIZED"
    EXECUTION_NOT_AUTHORIZED = "EXECUTION_NOT_AUTHORIZED"


# Series-quality status -> data reason code (V1 quality vocabulary is the input authority).
_SERIES_REASON = {"STALE": ReasonCode.DATA_STALE, "GAPPED": ReasonCode.DATA_GAPPED}


@dataclass(frozen=True)
class PhaseOutcome:
    """One phase's result: shared status + machine reason codes + deterministic evidence."""

    name: str
    status: PhaseStatus
    reason_codes: Tuple[ReasonCode, ...] = ()
    evidence: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"status": self.status.value,
                "reason_codes": [c.value for c in self.reason_codes],
                "evidence": self.evidence}


PHASE_KEYS: Tuple[str, ...] = ("data", "context", "location", "trigger", "risk", "proposal_eligibility")

_SETUP_PHASES = ("data", "context", "location", "trigger")  # setup_valid scope (mission section 10)


# ------------------------------------------------------------------ phase 0 -- data integrity

def _phase0_data(item: dict, scan: dict, facts: dict) -> PhaseOutcome:
    """Consume Scanner V1's FINAL data results. No strategy trigger logic is authoritative
    on invalid data; a fail here short-circuits every later phase."""
    evidence: dict = {}
    codes: List[ReasonCode] = []
    detail: List[str] = []

    if item.get("asset_class") == "CRYPTO":
        if (scan.get("time") or {}).get("time_gate") != TIME_GATE_PASS:
            return PhaseOutcome("data", PhaseStatus.FAIL, (ReasonCode.TIME_AUTHORITY_INVALID,),
                                {"time_gate": (scan.get("time") or {}).get("time_gate")})
        series = item.get("data_quality") or {}
        evidence.update({"series_status": {tf: q.get("status") for tf, q in series.items()},
                         "history_retry": {tf: bool(q.get("retry_performed")) for tf, q in series.items()},
                         "actual_source": scan.get("actual_source") or scan.get("source"),
                         "data_source_degraded": bool(scan.get("data_source_degraded")),
                         "time_gate": (scan.get("time") or {}).get("time_gate")})
        required = {"D1", "H1", "M15", "M5"}
        if (item.get("data_quality_gate") != "PASS" or facts.get("data_gate") != "PASS"
                or not required.issubset(series)
                or any(series[tf].get("status") != "VALID" for tf in required)):
            return PhaseOutcome("data", PhaseStatus.FAIL, (ReasonCode.DATA_INVALID,), evidence)
        return PhaseOutcome("data", PhaseStatus.PASS, (), evidence)

    time_gate = (scan.get("time") or {}).get("time_gate")  # canonical V1 key, no alias
    evidence["time_gate"] = time_gate
    if time_gate != TIME_GATE_PASS:
        codes.append(ReasonCode.TIME_AUTHORITY_INVALID)
        detail.append(f"TIME_GATE_{time_gate or 'MISSING'}")

    aggregate = scan.get("data_quality_gate")
    instrument_gate = item.get("data_quality_gate")
    evidence["aggregate_data_quality_gate"] = aggregate
    evidence["instrument_data_quality_gate"] = instrument_gate
    evidence["actual_source"] = scan.get("actual_source") or scan.get("source")
    evidence["data_source_degraded"] = bool(scan.get("data_source_degraded"))

    series = item.get("data_quality") or {}
    evidence["series_status"] = {tf: (series.get(tf) or {}).get("status") for tf in series}
    evidence["history_retry"] = {tf: bool((series.get(tf) or {}).get("retry_performed")) for tf in series}
    evidence["closed_bar_status"] = {
        tf: {"last_closed_bar_utc": (series.get(tf) or {}).get("last_closed_bar_utc"),
             "expected_last_closed_bar_utc": (series.get(tf) or {}).get("expected_last_closed_bar_utc")}
        for tf in series}

    if item.get("result") == "INSUFFICIENT_DATA" and not series:
        # Registry fail-closed path: no bars were ever fetched for this instrument.
        codes.append(ReasonCode.DATA_INVALID)
        detail.append(str(item.get("reason")))
    else:
        for tf, q in sorted(series.items()):
            status = q.get("status")
            if status == "VALID":
                continue
            codes.append(_SERIES_REASON.get(status, ReasonCode.DATA_INVALID))
            detail.append(f"{tf}_{status or 'MISSING'}")
        quote_status = (item.get("quote") or {}).get("status") if item.get("quote") is not None else None
        evidence["quote_status"] = quote_status
        if quote_status != "FRESH":
            codes.append(ReasonCode.DATA_STALE if quote_status == "STALE" else ReasonCode.DATA_INVALID)
            detail.append(f"QUOTE_{quote_status or 'MISSING'}")

    adapter_status = facts.get("adapter_status")
    evidence["reference_box_status"] = adapter_status
    if adapter_status == ADAPTER_BOX_INCOMPLETE:  # same classification as V1's DATA row
        codes.append(ReasonCode.DATA_INVALID)
        detail.append(f"REFERENCE_BOX_INCOMPLETE:{facts.get('adapter_reason')}")

    if instrument_gate != _GATE_PASS and not any(
            c in codes for c in (ReasonCode.DATA_STALE, ReasonCode.DATA_GAPPED, ReasonCode.DATA_INVALID)):
        codes.append(ReasonCode.DATA_INVALID)
    if aggregate != _GATE_PASS and not codes:
        # Another mandatory instrument or the instrument count failed while this one passed.
        codes.append(ReasonCode.DATA_INVALID)
        detail.append("AGGREGATE_DATA_QUALITY_GATE_FAIL")

    evidence["detail"] = detail
    status = PhaseStatus.PASS if not codes else PhaseStatus.FAIL
    return PhaseOutcome("data", status, tuple(dict.fromkeys(codes)), evidence)


# ------------------------------------------------------------------ phase 1 -- context

def _structure_state(raw: Optional[dict]) -> StructureState:
    """Map the market_structure authority output onto the allowed structure vocabulary."""
    if not raw or raw.get("status") != "VALID":
        return StructureState.INSUFFICIENT
    return {"BULLISH": StructureState.BULLISH, "BEARISH": StructureState.BEARISH}.get(
        raw.get("state"), StructureState.MIXED)


def _alignment_and_permission(d1: StructureState, h1: StructureState,
                              ) -> Tuple[str, DirectionPermission, Tuple[ReasonCode, ...]]:
    """D1/H1 alignment drives a permission LABEL only. It never vetoes the strategy
    engine: ST_ASIAN_SWEEP_5R_V1 defines no HTF-direction filter, so a conflict is
    observational (ReasonCode.HTF_DIRECTION_CONFLICT), not an invented block."""
    if d1 is StructureState.BULLISH and h1 is StructureState.BULLISH:
        return "ALIGNED_BULLISH", DirectionPermission.LONG_ALLOWED, ()
    if d1 is StructureState.BEARISH and h1 is StructureState.BEARISH:
        return "ALIGNED_BEARISH", DirectionPermission.SHORT_ALLOWED, ()
    if d1 is StructureState.RANGE and h1 is StructureState.RANGE:
        return "ALIGNED_RANGE", DirectionPermission.BOTH_ALLOWED, ()
    if {d1, h1} == {StructureState.BULLISH, StructureState.BEARISH}:
        return "CONFLICT", DirectionPermission.NO_DIRECTION, (ReasonCode.HTF_DIRECTION_CONFLICT,)
    return "UNRESOLVED", DirectionPermission.NO_DIRECTION, ()


def _phase1_context(item: dict, scan: dict, facts: dict) -> PhaseOutcome:
    if item.get("asset_class") == "CRYPTO":
        mstate = item.get("market_state") or {}
        h1 = (mstate.get("H1") or {}).get("structure") or {}
        d1 = facts.get("d1_structure") or {}
        d1_state, h1_state = _structure_state(d1), _structure_state(h1)
        alignment, permission, codes = _alignment_and_permission(d1_state, h1_state)
        return PhaseOutcome("context", PhaseStatus.PASS, codes, {
            "session_policy": "BROKER_DEFINED / 24H_OBSERVATION",
            "current_session": (scan.get("session") or {}).get("current_session"),
            "active_cycle": None, "fx_session_gate_applied": False,
            "d1_structure": d1, "h1_structure": h1,
            "structure_states": {"D1": d1_state.value, "H1": h1_state.value},
            "alignment": alignment, "direction_permission": permission.value,
            "direction_semantics": "PERMISSION_NOT_ENTRY",
        })
    session = scan.get("session") or {}
    active_cycle = session.get("active_cycle")
    if not active_cycle:
        return PhaseOutcome("context", PhaseStatus.FAIL, (ReasonCode.OUT_OF_SESSION,), {
            "current_session": session.get("current_session"),
            "active_cycle": None,
            "detail": "NO_ACTIVE_TRADE_CYCLE",
        })

    mstate = item.get("market_state") or {}
    h1_raw = (mstate.get("H1") or {}).get("structure")
    d1_raw = facts.get("d1_structure") or {}
    d1_state, h1_state = _structure_state(d1_raw), _structure_state(h1_raw)
    alignment, permission, align_codes = _alignment_and_permission(d1_state, h1_state)

    # No authoritative read-only economic-calendar path exists anywhere in the
    # repository; the policy stays observational and can never block a proposal.
    news = {"calendar_authority": None, "policy": ReasonCode.NEWS_POLICY_NOT_DEFINED.value,
            "blocking": False}

    codes: Tuple[ReasonCode, ...] = align_codes + (ReasonCode.NEWS_POLICY_NOT_DEFINED,)
    engine = item.get("engine") or {}
    evidence = {
        "current_session": session.get("current_session"),
        "active_cycle": active_cycle,
        "active_cycle_window_utc": session.get("active_cycle_window_utc"),
        "engine_regime": engine.get("regime"),
        "d1_structure": d1_raw,
        "h1_structure": h1_raw,
        "structure_states": {"D1": d1_state.value, "H1": h1_state.value},
        "alignment": alignment,
        "direction_permission": permission.value,
        "direction_semantics": "PERMISSION_NOT_ENTRY:_strategy_engine_remains_the_only_direction_authority",
        "news": news,
    }
    return PhaseOutcome("context", PhaseStatus.PASS, codes, evidence)


# ------------------------------------------------------------------ phase 2 -- location

def _phase2_location(item: dict, facts: dict) -> PhaseOutcome:
    """Strategy-authorized deterministic market facts only: the contract's reference-session
    box (Asian/London high/low) and strict-penetration sweep engagement. Previous-day
    high/low has NO defined role in this contract and is reported as a contract gap, never
    used as a decision. No generic indicators (fib/pivots/RSI/MACD/ADX/volume/OB/FVG)."""
    if item.get("asset_class") == "CRYPTO":
        return PhaseOutcome("location", PhaseStatus.INCOMPLETE_CONTRACT,
                            (ReasonCode.STRATEGY_CONTRACT_INCOMPLETE,),
                            {"strategy_id": None, "strategy_version": None,
                             "detail": facts.get("contract_gap"),
                             "previous_day_levels": "OBSERVED_ONLY_NO_CFD_STRATEGY_AUTHORITY"})
    mstate = item.get("market_state") or {}
    levels = item.get("session_levels") or {}
    box = (mstate.get("M15") or {}).get("reference_box")
    events = list(mstate.get("liquidity_events") or [])
    contract_gaps = list(mstate.get("liquidity_contract_gaps") or [])
    h1_structure = (mstate.get("H1") or {}).get("structure") or {}

    signal = facts.get("signal")
    trend_context = bool(signal and signal.get("regime") == "TREND")
    engine_signal = facts.get("adapter_status") == ADAPTER_SIGNAL
    # Location passes on three strategy-authorized engagements, none reinterpreted here:
    #   1. descriptive strict-penetration sweep events (the engine's own entry_2 predicate),
    #   2. the engine firing ANY valid setup (its own location predicate -- e.g. entry_3
    #      boundary rejection with >= touch -- was satisfied; Scanner V1 deliberately
    #      records the descriptive/engine difference as evidence instead of re-detecting),
    #   3. TREND context, where the completed reference box itself is the location (V1 parity).
    engaged = bool(events) or engine_signal or trend_context
    evidence = {
        "poi": {"type": "REFERENCE_SESSION_BOUNDARY", "authority": "strategy_engine",
                "reference_bars": f"{facts.get('reference_bars')}/{facts.get('expected_reference_bars')}",
                "box": box},
        "session_levels": {"asian": levels.get("asian"), "london": levels.get("london")},
        "engaged_events": events,
        "descriptive_event_present": bool(events),
        "sweep_events_predicate": "STRICT_PENETRATION:engine entry_2 predicate",
        "engine_signal_present": engine_signal,
        "h1_swing_high": h1_structure.get("swing_high"),
        "h1_swing_low": h1_structure.get("swing_low"),
        "position_vs_box": ((mstate.get("M15") or {}).get("breakout_state") or {}).get("state"),
        "trend_box_location": trend_context,
        "contract_gaps": contract_gaps,
        "previous_day_high_low": "OBSERVED_ONLY:contract_defines_no_PDH_PDL_role",
    }

    if engaged:
        return PhaseOutcome("location", PhaseStatus.PASS, (), evidence)
    if engine_signal and box is None:
        # Defensive: engine fired without any strategy-defined POI surface -- a contract
        # semantics gap, reported instead of guessed around. Unreachable for the frozen
        # ST_ASIAN_SWEEP_5R_V1 contract (a signal always carries its box).
        return PhaseOutcome("location", PhaseStatus.INCOMPLETE_CONTRACT,
                            (ReasonCode.STRATEGY_CONTRACT_INCOMPLETE,),
                            {**evidence, "detail": "ENGINE_SIGNAL_WITHOUT_POI"})
    return PhaseOutcome("location", PhaseStatus.FAIL, (ReasonCode.LOCATION_NOT_REACHED,), evidence)


# ------------------------------------------------------------------ phase 3 -- trigger

def _phase3_trigger(item: dict, facts: dict) -> PhaseOutcome:
    """Wrap the strategy engine (the trigger authority) -- none of its rules is rewritten.
    Preserves Scanner V1's two invariants:
      * signal candle not current        -> FAIL / SIGNAL_ENTRY_WINDOW_PASSED / NO_TRADE
      * TREND condition without timing   -> INCOMPLETE_CONTRACT / ENTRY_TIMING_NOT_DEFINED_FOR_SETUP
    """
    if item.get("asset_class") == "CRYPTO":
        return PhaseOutcome("trigger", PhaseStatus.INCOMPLETE_CONTRACT,
                            (ReasonCode.STRATEGY_CONTRACT_INCOMPLETE,),
                            {"strategy_id": None, "strategy_version": None,
                             "trigger_status": "NOT_EVALUATED",
                             "detail": facts.get("contract_gap")})
    engine = item.get("engine") or {}
    signal = facts.get("signal")
    last_closed = facts.get("last_closed_m15_utc")
    sig_ts = (signal or {}).get("signal_timestamp_utc")
    evidence = {
        "strategy_id": facts.get("strategy_id"),
        "strategy_version": facts.get("strategy_version"),
        "setup_type": (signal or {}).get("setup"),
        "trigger_type": (signal or {}).get("setup"),  # engine's own setup vocabulary
        "regime": (signal or {}).get("regime"),
        "signal_timeframe": facts.get("strategy_timeframe"),
        "signal_bar_timestamp": sig_ts,
        "signal_bar_closed": bool(sig_ts and last_closed and sig_ts <= last_closed),
        "signal_current": bool(sig_ts and last_closed and sig_ts == last_closed),
        "last_closed_m15_utc": last_closed,
        "engine_status": engine.get("status"),
        "engine_reason": engine.get("reason"),
        "signal_entry_open": engine.get("signal_entry_open"),
        "signal_entry_reason": engine.get("signal_entry_reason"),
    }

    adapter_status = facts.get("adapter_status")
    if adapter_status == ADAPTER_SYMBOL_NOT_IN_CONTRACT:
        return PhaseOutcome("trigger", PhaseStatus.BLOCKED, (ReasonCode.PROPOSAL_NOT_AUTHORIZED,),
                            {**evidence, "detail": "SYMBOL_NOT_IN_CONTRACT"})

    entry_reason = engine.get("signal_entry_reason")
    if engine.get("status") == ADAPTER_SIGNAL and engine.get("signal_entry_open"):
        return PhaseOutcome("trigger", PhaseStatus.PASS, (), evidence)
    if entry_reason == ReasonCode.ENTRY_TIMING_NOT_DEFINED_FOR_SETUP.value:
        return PhaseOutcome("trigger", PhaseStatus.INCOMPLETE_CONTRACT,
                            (ReasonCode.ENTRY_TIMING_NOT_DEFINED_FOR_SETUP,), evidence)
    if entry_reason == ReasonCode.SIGNAL_ENTRY_WINDOW_PASSED.value:
        return PhaseOutcome("trigger", PhaseStatus.FAIL, (ReasonCode.SIGNAL_ENTRY_WINDOW_PASSED,),
                            evidence)
    return PhaseOutcome("trigger", PhaseStatus.FAIL, (ReasonCode.NO_TRIGGER,),
                        {**evidence, "detail": engine.get("reason") or adapter_status})


# ------------------------------------------------------------------ phase 4 -- risk

def _phase4_risk(item: dict, facts: dict) -> PhaseOutcome:
    """Authoritative policy lineage only: the release pilot configs resolve EURUSD/GBPUSD at
    0.5%; USDJPY/XAUUSD stay RISK_POLICY_AMBIGUOUS. There is never a silent 1.0% fallback.
    Geometry (entry/invalidation/SL/stop distance/targets/RR) comes from the engine signal
    and the frozen contract; no generic minimum-RR rule is imposed."""
    if item.get("asset_class") == "CRYPTO":
        signal = facts.get("crypto_signal") or {}
        return PhaseOutcome("risk", PhaseStatus.BLOCKED, (ReasonCode.RISK_POLICY_AMBIGUOUS,), {
            "risk_authority": {"authorized": False, "policy_source": None,
                               "detail": "CRYPTO_RISK_POLICY_AMBIGUOUS", "generic_fallback_pct_used": False},
            "geometry": {"entry": signal.get("entry"), "stop_loss": signal.get("stop_loss"),
                         "risk_distance": signal.get("risk_distance")},
            "position_size": "NOT_CALCULATED", "account_equity_available": False,
        })
    if item.get("asset_class") == "CRYPTO":
        return PhaseOutcome("risk", PhaseStatus.BLOCKED, (ReasonCode.RISK_POLICY_AMBIGUOUS,), {
            "risk_authority": {"authorized": False, "policy_source": None,
                               "detail": "CRYPTO_RISK_POLICY_AMBIGUOUS", "generic_fallback_pct_used": False},
            "position_size": "NOT_CALCULATED", "account_equity_available": False})
    scope = facts.get("scope")
    signal = facts.get("signal") or {}
    targets = facts.get("contract_targets") or {}
    # Item-level marker ("NOT_CALCULATED") when V1 blocked sizing; the computed size lives
    # on the V1 ticket for the eligible path.
    item_position_size = item.get("position_size")
    if item_position_size is None:
        item_position_size = (item.get("proposal") or {}).get("position_size", "NOT_CALCULATED")

    risk_distance = signal.get("risk_distance")
    stop_distance_positive = bool(risk_distance and risk_distance > 0)
    authorized = bool(scope and scope.get("authorized"))
    evidence = {
        "risk_authority": {
            "authorized": authorized,
            "risk_per_trade_pct": scope.get("risk_per_trade_pct") if scope else None,
            "policy_source": scope.get("pilot_id") if scope else None,
            "detail": scope.get("reason") if scope else "NO_PROPOSAL_SCOPE_FOR_CYCLE",
            "generic_fallback_pct_used": False,
        },
        "geometry": {"entry": signal.get("entry"), "stop_loss": signal.get("stop_loss"),
                     "risk_distance": risk_distance, "stop_distance_positive": stop_distance_positive},
        "invalidation": {"time": targets.get("time_invalidation"),
                         "structural": targets.get("structural_invalidation")},
        "contract_targets": {"total_target_r": targets.get("total_target_r"), "legs": targets.get("legs"),
                             "min_rr_policy_defined": False},
        "position_size": item_position_size if item_position_size is not None else "NOT_CALCULATED",
        "account_equity_available": bool((facts.get("account") or {}).get("equity")),
    }
    if not stop_distance_positive:
        return PhaseOutcome("risk", PhaseStatus.FAIL, (ReasonCode.INVALID_STOP_DISTANCE,), evidence)
    if not authorized:
        return PhaseOutcome("risk", PhaseStatus.BLOCKED, (ReasonCode.RISK_POLICY_AMBIGUOUS,), evidence)
    return PhaseOutcome("risk", PhaseStatus.PASS, (), evidence)


# ------------------------------------------------------------------ phase 5 -- proposal eligibility

def _phase5_eligibility(item: dict, facts: dict) -> PhaseOutcome:
    """Evaluated only after the mandatory preceding phases PASS. READY_FOR_PROPOSAL is not
    READY_FOR_EXECUTION: execution_authorized is a hard False and every proposal carries
    ReasonCode.EXECUTION_NOT_AUTHORIZED observably."""
    spread = dict(facts.get("spread") or {})
    scan_allowed = bool(facts.get("scan_allowed"))
    ticket_present = item.get("proposal") is not None
    evidence = {
        "spread": spread,
        "proposal_authority": {"opportunity_scan_allowed": scan_allowed,
                               "scope_authorized": bool(facts.get("scope") and facts["scope"].get("authorized"))},
        "proposal_ticket_present": ticket_present,
        "execution_authorized": False,
    }
    if item.get("asset_class") == "CRYPTO":
        return PhaseOutcome("proposal_eligibility", PhaseStatus.BLOCKED,
                            (ReasonCode.SPREAD_POLICY_UNDEFINED, ReasonCode.PROPOSAL_NOT_AUTHORIZED,
                             ReasonCode.EXECUTION_NOT_AUTHORIZED), evidence)
    if spread.get("status") == "FAIL":
        return PhaseOutcome("proposal_eligibility", PhaseStatus.FAIL, (ReasonCode.SPREAD_TOO_WIDE,),
                            evidence)
    codes: List[ReasonCode] = [ReasonCode.EXECUTION_NOT_AUTHORIZED]
    if spread.get("status") == "OBSERVED_ONLY":
        # Spread observed on the executable broker symbol with no contract/governance
        # threshold: recorded, never turned into an invented pass/fail limit (mission,
        # required case G).
        codes.append(ReasonCode.SPREAD_POLICY_UNDEFINED)
    if not scan_allowed:
        return PhaseOutcome("proposal_eligibility", PhaseStatus.BLOCKED,
                            (ReasonCode.PROPOSAL_NOT_AUTHORIZED,), evidence)
    if not ticket_present:
        return PhaseOutcome("proposal_eligibility", PhaseStatus.BLOCKED,
                            (ReasonCode.PROPOSAL_NOT_AUTHORIZED,),
                            {**evidence, "detail": "V1_PROPOSAL_TICKET_MISSING"})
    return PhaseOutcome("proposal_eligibility", PhaseStatus.PASS, tuple(codes), evidence)


# ------------------------------------------------------------------ orchestration (sequential, fail-closed)

def _not_applicable(name: str, blocked_by: str) -> PhaseOutcome:
    return PhaseOutcome(name, PhaseStatus.NOT_APPLICABLE, (),
                        {"blocked_by_phase": blocked_by, "authoritative": False})


def evaluate_instrument_checklist(scan: dict, item: dict, facts: Optional[dict]) -> dict:
    """Derive the Checklist V1.1 block for one scanned instrument from Scanner V1's own
    output (additive mutation of nothing V1 emitted). ``facts`` is the JSON-safe fact
    bundle captured by scanner.py during the instrument loop; None for registry-blocked
    instruments."""
    facts = facts or {}
    canonical = item.get("canonical_symbol")
    phases: Dict[str, PhaseOutcome] = {}

    data = _phase0_data(item, scan, facts)
    phases["data"] = data
    if data.status is not PhaseStatus.PASS:
        for name in PHASE_KEYS[1:]:
            phases[name] = _not_applicable(name, "data")
        return _final(canonical, item, phases, ChecklistResult.INSUFFICIENT_DATA, data)

    if item.get("asset_class") == "CRYPTO":
        phases["context"] = _phase1_context(item, scan, facts)
        phases["location"] = _phase2_location(item, facts)
        phases["trigger"] = _phase3_trigger(item, facts)
        phases["risk"] = _phase4_risk(item, facts)
        phases["proposal_eligibility"] = PhaseOutcome(
            "proposal_eligibility", PhaseStatus.BLOCKED,
            (ReasonCode.STRATEGY_CONTRACT_INCOMPLETE, ReasonCode.RISK_POLICY_AMBIGUOUS,
             ReasonCode.SPREAD_POLICY_UNDEFINED, ReasonCode.PROPOSAL_NOT_AUTHORIZED,
             ReasonCode.EXECUTION_NOT_AUTHORIZED),
            {"proposal_authority": False, "position_size": "NOT_CALCULATED",
             "execution_authorized": False, "spread": facts.get("spread")})
        deciding = phases["location"]
        return _final(canonical, item, phases, ChecklistResult.BLOCKED, deciding)

    context = _phase1_context(item, scan, facts)
    phases["context"] = context
    if context.status is PhaseStatus.FAIL:
        for name in PHASE_KEYS[2:]:
            phases[name] = _not_applicable(name, "context")
        return _final(canonical, item, phases, ChecklistResult.OUT_OF_SESSION, context)

    location = _phase2_location(item, facts)
    phases["location"] = location
    if location.status is PhaseStatus.FAIL:
        for name in PHASE_KEYS[3:]:
            phases[name] = _not_applicable(name, "location")
        return _final(canonical, item, phases, ChecklistResult.NO_TRADE, location)
    if location.status is PhaseStatus.INCOMPLETE_CONTRACT:
        for name in PHASE_KEYS[3:]:
            phases[name] = _not_applicable(name, "location")
        return _final(canonical, item, phases, ChecklistResult.BLOCKED, location)

    trigger = _phase3_trigger(item, facts)
    phases["trigger"] = trigger
    if trigger.status is not PhaseStatus.PASS:
        for name in PHASE_KEYS[4:]:
            phases[name] = _not_applicable(name, "trigger")
        # FAIL -> market-driven NO_TRADE; BLOCKED / INCOMPLETE_CONTRACT -> BLOCKED.
        result = ChecklistResult.NO_TRADE if trigger.status is PhaseStatus.FAIL else ChecklistResult.BLOCKED
        return _final(canonical, item, phases, result, trigger)

    risk = _phase4_risk(item, facts)
    phases["risk"] = risk
    if risk.status is not PhaseStatus.PASS:
        phases["proposal_eligibility"] = _not_applicable("proposal_eligibility", "risk")
        return _final(canonical, item, phases, ChecklistResult.BLOCKED, risk)

    eligibility = _phase5_eligibility(item, facts)
    phases["proposal_eligibility"] = eligibility
    if eligibility.status is PhaseStatus.PASS:
        result = ChecklistResult.READY_FOR_PROPOSAL
    elif eligibility.status is PhaseStatus.FAIL:
        result = ChecklistResult.NO_TRADE
    else:
        result = ChecklistResult.BLOCKED
    return _final(canonical, item, phases, result, eligibility)


def _final(canonical: Optional[str], item: dict, phases: Dict[str, PhaseOutcome],
           result: ChecklistResult, deciding: PhaseOutcome) -> dict:
    """Assemble the section-13 structured output. ``setup_valid`` covers exactly the
    analytical phases; ``proposal_eligible`` additionally requires the risk authority and
    the proposal gate; ``execution_authorized`` is always False."""
    setup_valid = all(phases[k].status is PhaseStatus.PASS for k in _SETUP_PHASES)
    proposal_eligible = (setup_valid and result is ChecklistResult.READY_FOR_PROPOSAL
                         and item.get("asset_class") != "CRYPTO")
    block = {
        "version": CHECKLIST_VERSION,
        "symbol": canonical,
        "broker_symbol": item.get("broker_symbol"),
        "canonical_symbol": canonical,
        "asset_class": item.get("asset_class"),
        "phases": {k: phases[k].as_dict() for k in PHASE_KEYS},
        "setup_valid": setup_valid,
        "proposal_eligible": proposal_eligible,
        "execution_authorized": False,
        "result": result.value,
        "reason_codes": [c.value for c in deciding.reason_codes],
    }
    if proposal_eligible:
        block["proposal"] = build_proposal(item, phases)
    return block


# ------------------------------------------------------------------ non-executable proposal contract (section 14)

PROPOSAL_STATUS_READY = "READY_FOR_PROPOSAL"


def build_proposal(item: dict, phases: Dict[str, PhaseOutcome]) -> dict:
    """Wrap Scanner V1's non-executable ticket into the Checklist V1.1 proposal contract.
    The V1 ticket dict is copied, never mutated; no broker call may follow construction."""
    ticket = dict(item["proposal"])
    ticket["context_evidence"] = {
        "current_session": phases["context"].evidence.get("current_session"),
        "active_cycle": phases["context"].evidence.get("active_cycle"),
        "engine_regime": phases["context"].evidence.get("engine_regime"),
        "structure_states": phases["context"].evidence.get("structure_states"),
        "alignment": phases["context"].evidence.get("alignment"),
        "direction_permission": phases["context"].evidence.get("direction_permission"),
        "news": phases["context"].evidence.get("news"),
    }
    ticket["location_evidence"] = phases["location"].evidence
    ticket["checklist_status"] = {k: phases[k].as_dict() for k in PHASE_KEYS}
    ticket["proposal_status"] = PROPOSAL_STATUS_READY
    ticket["execution_authorized"] = False
    return ticket


# ------------------------------------------------------------------ scanner attachment

def attach_checklist_v1_1(scan: dict, facts_by_symbol: Dict[str, Optional[dict]]) -> dict:
    """Additively attach Checklist V1.1 to every instrument Scanner V1 emitted, and add a
    scan-level summary. Existing Scanner V1 keys are never modified."""
    results: Dict[str, str] = {}
    for item in scan.get("instruments", []):
        block = evaluate_instrument_checklist(scan, item, facts_by_symbol.get(item.get("canonical_symbol")))
        item["checklist_v1_1"] = block
        results[item.get("canonical_symbol")] = block["result"]
    scan["checklist_v1_1"] = {
        "version": CHECKLIST_VERSION,
        "results": results,
        "summary": {r.value: sum(1 for v in results.values() if v == r.value) for r in ChecklistResult},
        "execution_authorized": False,
    }
    return scan
