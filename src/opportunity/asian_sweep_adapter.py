"""Asian Sweep (ST_ASIAN_SWEEP_5R_V1) V2-3C shadow/funnel adapter.

Thin `opportunity.adapter.StrategyFunnelAdapter` over the EXISTING canonical
Asian Sweep decision contract, `post_asian_pilot.decision.PostAsianDecision`, as
built by that module's `map_trade_signal_to_decision` / `watch_decision` /
`data_error_decision` from a `strategy_engine.models.TradeSignal` -- itself the
UNCHANGED-BEHAVIOR output of `strategy_engine.engine.evaluate()`
(`strategies/ST_ASIAN_SWEEP_5R_V1.yaml` -> `StrategyConfig` -> frozen reference
box -> TREND/RANGE classification -> Entry 1/2/3 candidate-setup detection --
see that module's own docstring), reached either directly or through
`post_asian_pilot.pipeline._evaluate_pair`, which is this strategy's own
existing canonical polling/persistence/scope authority (it ALSO applies the
strategy's own "sweep-only" scope decision -- see decision.py's module
docstring, "SCOPE DECISION" -- mapping a canonical TREND/RANGE `TradeSignal`
to `NO_TRADE` rather than promoting it, since `ST_ASIAN_SWEEP_5R_V1`'s own
`entry_rules` define only `SWEEP_REFERENCE_LOW`/`SWEEP_REFERENCE_HIGH`
triggers).

This adapter does NOT reimplement reference-box construction, TREND/RANGE
classification, sweep/trend/range detection, or the sweep-only scope decision.
It only maps an already-canonical `PostAsianDecision.status` (plus, where a
`TradeSignal` is attached, its `setup`/`reason_code`) onto the V2 universal
funnel:

    reference box / TREND-RANGE classify / Entry 1-2-3 detectors  (canonical strategy truth)
            |  strategy_engine.engine.evaluate() (existing, UNCHANGED)
            v
    TradeSignal                                            (existing canonical output)
            |  post_asian_pilot.decision.map_trade_signal_to_decision /
            |  watch_decision / data_error_decision (existing, UNCHANGED --
            |  also where the sweep-only scope decision is already made)
            v
    PostAsianDecision                                      (existing canonical contract)
            |  _project_watch / _project_ready / _project_no_trade /
            |  _project_expired / _project_data_error (THIS module, new)
            v
    opportunity.stages FUNNEL_STAGES / FUNNEL_OUTCOMES     (V2 universal funnel)

SESSION-PAIR / TRADING-DATE IDENTITY: `PostAsianDecision` carries
`reference_session` (the reference-session name, e.g. "Asian"/"London" --
always populated, including for WATCH/DATA_ERROR states with no `TradeSignal`
yet) and `trading_date`. Since `strategies/ST_ASIAN_SWEEP_5R_V1.yaml` defines
exactly one `reference_session.name` per `pair_id` (ASIAN_LONDON -> "Asian",
LONDON_NEWYORK -> "London"), `reference_session` distinguishes session pairs
one-to-one and is used by this adapter's `supports()`/serialization instead of
requiring `pair_id` directly (not always present -- `TradeSignal.pair_id` only
exists once a `TradeSignal` has actually been produced).

TRADING-DATE SEMANTICS (verified, not assumed): `session_clock.get_session_bounds`
computes `[start, end)` for a session name as same-calendar-day UTC hours (see
that module). `ST_ASIAN_SWEEP_5R_V1.yaml`'s own session windows (Asian
00:00-06:00, London 06:00-11:00, London_Open 07:00-11:00, New_York_Open
12:00-15:00, all GMT) never cross a UTC midnight boundary, so for this specific
strategy `trading_date` and the UTC calendar date coincide -- this is a
verified property of the canonical config/session_clock authority, not an
assumption carried over from another strategy.

REPLAY AUTHORITY / DATA-MODE FIREWALL: this module never fetches MT5 or any
live feed itself -- it consumes only an already-built `PostAsianDecision`.
`market_data_mode` is carried on the `MarketEvent`/`StrategyObservation` the
caller supplies, exactly as every other opportunity adapter does; this module
never inspects or mutates it.

PORTFOLIO-RISK / GOVERNOR EXCLUSION: `PostAsianDecision.status` as produced by
`decision.py`'s own three constructors is always one of WATCH/READY/NO_TRADE/
DATA_ERROR/EXPIRED -- never `BLOCKED` (that status is layered on top, after a
READY decision, by `post_asian_pilot.governor`/`tiebreak`, which is portfolio-
risk/tie-break authority, not candidate/funnel authority -- see
`opportunity.contracts` module docstring, "risk sits downstream of a
candidate"). This adapter fails closed if it is ever handed a `BLOCKED`
decision rather than silently reinterpreting a risk-gate decision as a funnel
stage.

INTENDED EVENT-IDENTITY PATTERN: `opportunity.engine._candidate_id` keys
candidate identity off `(strategy_id, strategy_version, event.event_id,
symbol)`. For "the same logical (symbol, session-pair, trading-date)
occurrence produces ONE candidate across a day's repeated cycles" to hold
(and to prevent one session pair's candidate colliding with the other's), the
caller must build one `MarketEvent` per occurrence whose `event_id` is stable
across re-evaluations of the SAME (symbol, session_pair, trading_date) cycle --
e.g. `event_id=f"ASIAN_SWEEP:{symbol}:{pair_id}:{trading_date}"` --
deliberately excluding direction, since direction is only known once a sweep
signal actually fires (no signal yet -> direction unknown) and identity must
survive that transition.

FAIL-CLOSED: an unrecognized `PostAsianDecision.status`, `missing_condition`
(for WATCH), or NO_TRADE `TradeSignal.setup`/`reason_code` combination raises
`AsianSweepUnmappedDecisionError` rather than defaulting to any funnel stage.

NO EXECUTION AUTHORITY: imports only `post_asian_pilot.decision`
(`PostAsianDecision` and its status constants, a plain dataclass/module of
constants) -- never `execution.*`, `mt5.executor`, or `mt5.mt5_gateway` --
enforced by tests/test_opportunity_import_boundaries.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from post_asian_pilot.decision import (
    PostAsianDecision,
    STATUS_DATA_ERROR,
    STATUS_EXPIRED,
    STATUS_NO_TRADE,
    STATUS_READY,
    STATUS_WATCH,
)

from .adapter import FunnelProjection, StrategyObservation
from .contracts import CandidateGeometry, MarketEvent
from .registry_binding import StrategyBinding
from .stages import (
    OUTCOME_ACTIVE,
    OUTCOME_ERROR,
    OUTCOME_EXPIRED,
    OUTCOME_REJECT,
    OUTCOME_WAIT,
    STAGE_CONTEXT_VALID,
    STAGE_ENTRY_CONFIRMED,
    STAGE_LOCATION_VALID,
    STAGE_MARKET_ELIGIBLE,
    STAGE_SETUP_DETECTED,
)
from .transitions import FunnelState

STRATEGY_ID = "ST_ASIAN_SWEEP_5R_V1"
STRATEGY_VERSION = "1.1.1"

_MISSING_CONDITION_TO_STAGE = {
    "WAITING_REFERENCE_SESSION_COMPLETION": STAGE_MARKET_ELIGIBLE,
    "WAITING_EXECUTION_WINDOW_OPEN": STAGE_LOCATION_VALID,
    "WAITING_CLOSED_M15_CONFIRMATION": STAGE_LOCATION_VALID,
    "WAITING_REFERENCE_SWEEP": STAGE_CONTEXT_VALID,
}

_OUT_OF_SCOPE_SETUP_TYPES = frozenset({"TREND", "RANGE"})


class AsianSweepUnmappedDecisionError(RuntimeError):
    """Fail-closed: a `PostAsianDecision` shape this adapter has no documented
    V2 projection for (an unrecognized status, missing_condition, or NO_TRADE
    setup/reason_code combination)."""


class AsianSweepStrategyIdentityMismatchError(RuntimeError):
    """Fail-closed: the PostAsianDecision handed to this adapter was not built
    from an ST_ASIAN_SWEEP_5R_V1 decision -- never silently adopted under a
    mismatched strategy identity."""


def _serialize_decision(decision: PostAsianDecision) -> Dict[str, Any]:
    """JSON-stable snapshot of the fields this adapter actually consumes,
    copied verbatim from `PostAsianDecision`/its attached `TradeSignal`
    (themselves already copied verbatim from canonical `strategy_engine`
    output -- see module docstring). Never recomputed here."""
    signal = decision.signal
    return {
        "status": decision.status,
        "trading_date": decision.trading_date.isoformat(),
        "reference_session": decision.reference_session,
        "reason_codes": list(decision.reason_codes),
        "missing_condition": decision.missing_condition,
        "ready_at": decision.ready_at.isoformat() if decision.ready_at else None,
        "valid_until": decision.valid_until.isoformat() if decision.valid_until else None,
        "signal": None
        if signal is None
        else {
            "pair_id": signal.pair_id,
            "regime": signal.regime,
            "setup": signal.setup,
            "status": signal.status,
            "reason_code": signal.reason_code,
            "direction": signal.direction,
            "entry": signal.entry,
            "stop_loss": signal.stop_loss,
            "risk_distance": signal.risk_distance,
            "box_high": signal.box_high,
            "box_low": signal.box_low,
            "box_mid": signal.box_mid,
            "signal_timestamp": signal.signal_timestamp.isoformat() if signal.signal_timestamp else None,
        },
    }


def _project_watch(missing_condition: Optional[str]) -> FunnelProjection:
    stage = _MISSING_CONDITION_TO_STAGE.get(missing_condition) if missing_condition else None
    if stage is None:
        raise AsianSweepUnmappedDecisionError(
            f"WATCH missing_condition {missing_condition!r} has no documented V2 funnel "
            "projection (see asian_sweep_adapter module docstring)"
        )
    return FunnelProjection(
        stage=stage,
        outcome=OUTCOME_WAIT,
        reason_codes=(f"ASIAN_SWEEP_{missing_condition}",),
    )


def _project_ready(signal_setup: Optional[str], signal_status: Optional[str]) -> FunnelProjection:
    if signal_setup != "SWEEP" or signal_status != "SIGNAL":
        # Defensive: decision.py's own map_trade_signal_to_decision only ever
        # produces STATUS_READY for setup == "SWEEP" and status == "SIGNAL" --
        # reaching here means that invariant broke upstream.
        raise AsianSweepUnmappedDecisionError(
            f"READY decision with unexpected signal shape setup={signal_setup!r} "
            f"status={signal_status!r} (see asian_sweep_adapter module docstring)"
        )
    return FunnelProjection(
        stage=STAGE_ENTRY_CONFIRMED,
        outcome=OUTCOME_ACTIVE,
        reason_codes=("ASIAN_SWEEP_SIGNAL_READY",),
    )


def _project_no_trade(signal_setup: Optional[str], signal_status: Optional[str], reason_code: Optional[str]) -> FunnelProjection:
    if signal_setup in _OUT_OF_SCOPE_SETUP_TYPES and signal_status == "SIGNAL":
        # A genuine TREND/RANGE candidate was found by the shared canonical
        # router, but ST_ASIAN_SWEEP_5R_V1's own entry_rules define sweep
        # triggers only -- decision.py already rejected it as out-of-scope
        # (see its module docstring, "SCOPE DECISION"); this adapter mirrors
        # that rejection, never promoting it.
        return FunnelProjection(
            stage=STAGE_SETUP_DETECTED,
            outcome=OUTCOME_REJECT,
            reason_codes=("ASIAN_SWEEP_NON_SWEEP_SETUP_OUT_OF_SCOPE", reason_code or ""),
        )
    if reason_code == "AMBIGUOUS_DUAL_SWEEP":
        return FunnelProjection(
            stage=STAGE_SETUP_DETECTED,
            outcome=OUTCOME_REJECT,
            reason_codes=("ASIAN_SWEEP_AMBIGUOUS_DUAL_SWEEP",),
        )
    if reason_code == "BOX_DIRECTION_V1_FLAT_NO_TRADE":
        return FunnelProjection(
            stage=STAGE_CONTEXT_VALID,
            outcome=OUTCOME_REJECT,
            reason_codes=("ASIAN_SWEEP_BOX_FLAT_NO_TRADE",),
        )
    raise AsianSweepUnmappedDecisionError(
        f"NO_TRADE decision with setup={signal_setup!r} status={signal_status!r} "
        f"reason_code={reason_code!r} has no documented V2 funnel projection "
        "(see asian_sweep_adapter module docstring)"
    )


def _project_expired() -> FunnelProjection:
    # RANGE regime classified, Entry 2 (sweep) and Entry 3 (range-boundary
    # rejection) both scanned the full execution window with no qualified
    # setup -- context established, window ran out.
    return FunnelProjection(
        stage=STAGE_CONTEXT_VALID,
        outcome=OUTCOME_EXPIRED,
        reason_codes=("ASIAN_SWEEP_WINDOW_EXPIRED_NO_SETUP",),
    )


def _project_data_error(reason_codes) -> FunnelProjection:
    # Per post_asian_pilot.decision's own module docstring: DATA_ERROR is never
    # translated into NO_TRADE. Mapped to OUTCOME_ERROR regardless of the
    # specific underlying reason (MarketDataError variants, snapshot
    # corruption/immutability conflicts, etc.) -- all equally mean "no reliable
    # canonical evaluation happened this cycle", not "the strategy rejected".
    return FunnelProjection(
        stage=STAGE_MARKET_ELIGIBLE,
        outcome=OUTCOME_ERROR,
        reason_codes=tuple(reason_codes) or ("ASIAN_SWEEP_DATA_ERROR",),
    )


@dataclass(frozen=True)
class AsianSweepFunnelAdapter:
    """One instance projects ONE canonical `PostAsianDecision` (built upstream
    by `post_asian_pilot.decision.map_trade_signal_to_decision`/`watch_decision`/
    `data_error_decision`, typically via one `post_asian_pilot.pipeline.
    _evaluate_pair` cycle) into the V2 universal funnel. Constructed by the
    caller per cycle -- see module docstring, "REPLAY AUTHORITY / DATA-MODE
    FIREWALL"."""

    decision: PostAsianDecision
    strategy_id: str = STRATEGY_ID
    strategy_version: str = STRATEGY_VERSION

    def __post_init__(self) -> None:
        if self.decision.strategy_id != self.strategy_id:
            raise AsianSweepStrategyIdentityMismatchError(
                f"PostAsianDecision.strategy_id {self.decision.strategy_id!r} does not "
                f"match adapter strategy_id {self.strategy_id!r}"
            )

    def supports(self, event: MarketEvent, binding: StrategyBinding) -> bool:
        return (
            binding.strategy_id == self.strategy_id
            and event.symbol == self.decision.symbol
        )

    def observe(self, event: MarketEvent, previous_state: FunnelState) -> StrategyObservation:
        return StrategyObservation(
            strategy_id=self.strategy_id,
            event_id=event.event_id,
            market_data_mode=event.market_data_mode,
            raw_strategy_state={"decision": _serialize_decision(self.decision)},
        )

    def project(self, observation: StrategyObservation) -> FunnelProjection:
        payload = observation.raw_strategy_state["decision"]
        status = payload["status"]
        signal = payload["signal"]

        if status == STATUS_WATCH:
            projection = _project_watch(payload["missing_condition"])
        elif status == STATUS_READY:
            projection = _project_ready(signal["setup"] if signal else None, signal["status"] if signal else None)
        elif status == STATUS_NO_TRADE:
            projection = _project_no_trade(
                signal["setup"] if signal else None,
                signal["status"] if signal else None,
                signal["reason_code"] if signal else None,
            )
        elif status == STATUS_EXPIRED:
            projection = _project_expired()
        elif status == STATUS_DATA_ERROR:
            projection = _project_data_error(payload["reason_codes"])
        else:
            raise AsianSweepUnmappedDecisionError(
                f"PostAsianDecision.status {status!r} has no documented V2 funnel "
                "projection (see asian_sweep_adapter module docstring)"
            )

        context_evidence = dict(projection.context_evidence)
        context_evidence.setdefault("reference_session", payload["reference_session"])
        context_evidence.setdefault("trading_date", payload["trading_date"])
        if signal is not None:
            context_evidence.setdefault("regime", signal["regime"])
        setup_evidence = dict(projection.setup_evidence)
        if signal is not None:
            setup_evidence["pair_id"] = signal["pair_id"]
            setup_evidence["setup"] = signal["setup"]

        return FunnelProjection(
            stage=projection.stage,
            outcome=projection.outcome,
            reason_codes=projection.reason_codes,
            context_evidence=context_evidence,
            setup_evidence=setup_evidence,
            trigger_evidence={},
        )

    def candidate_geometry(self, observation: StrategyObservation) -> Optional[CandidateGeometry]:
        payload = observation.raw_strategy_state["decision"]
        signal = payload["signal"]
        if payload["status"] != STATUS_READY or signal is None:
            # No in-scope sweep signal this cycle -- never fabricated. Includes
            # out-of-scope TREND/RANGE signals: their direction/entry belong to
            # a setup type this strategy's own contract does not trade.
            return None
        return CandidateGeometry(
            direction=signal["direction"],
            entry=signal["entry"],
            invalidation=signal["stop_loss"],
            targets=(),
            estimated_rr=None,
        )
