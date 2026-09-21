"""Large-SMC (ST_LARGE_SMC_V1) V2-3A shadow/funnel adapter.

Thin `opportunity.adapter.StrategyFunnelAdapter` over the EXISTING canonical
Large-SMC watch-lifecycle projection
(`large_smc_research.watch_lifecycle.project_setup_row`), which is itself a pure,
documented, TOTAL projection of the canonical detection funnel
(`entry_confirmation.entry_models_v1.EntryModelState`) and post-READY occurrence
outcome (`historical_replay.fill_simulator` statuses) onto a lifecycle vocabulary
(see that module's own docstring). This adapter does NOT decide whether an SMC
setup exists, does NOT re-run entry-confirmation/fill-simulation logic, and does
NOT alter `watch_lifecycle`'s own projection -- it only maps an already-canonical
`WatchLifecycleRecord.stage` one more step onto the V2 universal funnel
(`opportunity.stages`). Two mapping layers stacked, neither duplicated:

    EntryModelState / fill_simulator status     (canonical strategy truth)
            |  watch_lifecycle.project_setup_row (existing, UNCHANGED)
            v
    WatchLifecycleRecord.stage                    (existing mission vocabulary)
            |  _NONTERMINAL_STAGE_FOR / _TERMINAL_OUTCOME_FOR (THIS module, new)
            v
    opportunity.stages FUNNEL_STAGES / FUNNEL_OUTCOMES  (V2 universal funnel)

SCHEDULED-WATCH COMPATIBILITY: an adapter instance is constructed from an
already-produced `historical_replay.orchestrator.SetupLedgerRow` (plus an
optional post-READY `occurrence_status`) -- the exact objects
`large_smc_research.live_watch`'s existing scheduled watch already produces
every run (`WatchRunResult` steps through `run_replay`, whose
`SetupLedger.rows` are `SetupLedgerRow`s). This module never fetches candles,
runs replay, or calls entry-confirmation itself; it is a pure, additive shadow
projection of output the scheduled watch already computes, evaluated by a
caller ALONGSIDE (never instead of) that watch.

INTENDED EVENT-IDENTITY PATTERN (for whatever caller drives this adapter through
`opportunity.engine.evaluate_funnel`): `opportunity.engine._candidate_id` keys
candidate identity off `(strategy_id, strategy_version, event.event_id, symbol)`,
NOT off any Large-SMC-native identity. For "the same logical occurrence produces
ONE candidate across repeated polls" (mission requirement) to hold, the caller
must build one `MarketEvent` per occurrence whose `event_id` is stable across
polls -- e.g. `event_id=f"LARGE_SMC:{setup_row.setup_id}"` -- while
`bar_close_time`/`market_data_asof` may still advance to the latest poll time.
This module does not construct `MarketEvent`s itself (that remains
`opportunity.events`'/the caller's job); it only documents the identity
contract its own `candidate_geometry`/`observe` output requires upstream.

FAIL-CLOSED: `WatchLifecycleRecord.stage == STAGE_RESOLVED` has no reachable
canonical producer today -- `large_smc_research.watch_lifecycle`'s own module
docstring: "RESOLVED has no canonical counterpart reachable today" (resolving
FILLED -> TARGET_HIT/STOP_HIT needs broker-stop-distance information this
adapter does not have). Rather than invent a V2 outcome for a state that cannot
occur, `project()` raises `LargeSMCUnmappedStageError` if it ever is -- see
docs/status/AG_V2_3A_3B_ADAPTER_PARITY_STATUS.md for the accepted-debt writeup.

NO EXECUTION AUTHORITY: imports only `historical_replay.orchestrator`
(SetupLedgerRow, a plain dataclass) and `large_smc_research.watch_lifecycle`
(the existing projection). Never imports `execution.*`, `mt5.executor`, or
`mt5.mt5_gateway` -- enforced by tests/test_opportunity_import_boundaries.py,
which globs every module in this package.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from historical_replay.orchestrator import SetupLedgerRow
from large_smc_research.watch_lifecycle import (
    STAGE_BLOCKED,
    STAGE_ENTRY_AVAILABLE,
    STAGE_EXPIRED,
    STAGE_FILLED,
    STAGE_INVALIDATED,
    STAGE_QUALIFIED,
    STAGE_RESOLVED,
    STAGE_UNFILLED,
    STAGE_WATCHING,
    WatchLifecycleRecord,
    project_setup_row,
)

from .adapter import FunnelProjection, StrategyObservation
from .contracts import CandidateGeometry, MarketEvent
from .registry_binding import StrategyBinding
from .stages import (
    OUTCOME_ACTIVE,
    OUTCOME_ERROR,
    OUTCOME_EXPIRED,
    OUTCOME_INVALIDATED,
    OUTCOME_WAIT,
    STAGE_ENTRY_CONFIRMED as V2_STAGE_ENTRY_CONFIRMED,  # noqa: F401 (documented, unused by design -- see module docstring table)
    STAGE_LOCATION_VALID,
    STAGE_MARKET_ELIGIBLE,
    STAGE_OPPORTUNITY_READY,
    STAGE_TRIGGER_ARMED,
)
from .transitions import FunnelState

STRATEGY_ID = "ST_LARGE_SMC_V1"
# strategies/registry.yaml has no semantic_version field for ST_LARGE_SMC_V1; the
# engine's own registered version string (large_smc_research/decision.py) is
# reused verbatim rather than inventing a new one.
STRATEGY_VERSION = "LARGE_SMC_RESEARCH_ENGINE_V1"

# Non-terminal canonical stages (WatchLifecycleRecord.is_terminal is False) -> V2
# universal-funnel stage/outcome. Documented, total over every non-terminal member
# of large_smc_research.watch_lifecycle.LIFECYCLE_ORDER.
_NONTERMINAL_STAGE_FOR: Dict[str, str] = {
    STAGE_WATCHING: STAGE_MARKET_ELIGIBLE,
    STAGE_QUALIFIED: STAGE_LOCATION_VALID,
    STAGE_ENTRY_AVAILABLE: STAGE_TRIGGER_ARMED,
    STAGE_FILLED: STAGE_OPPORTUNITY_READY,
    STAGE_UNFILLED: STAGE_TRIGGER_ARMED,
}
_NONTERMINAL_OUTCOME_FOR: Dict[str, str] = {
    STAGE_WATCHING: OUTCOME_ACTIVE,
    STAGE_QUALIFIED: OUTCOME_ACTIVE,
    STAGE_ENTRY_AVAILABLE: OUTCOME_ACTIVE,
    # FILLED's own resolution_status is UNRESOLVED_REQUIRES_C10 (watch_lifecycle.
    # resolution_status_for) -- the entry occurred but P&L resolution is out of
    # this adapter's (and the opportunity funnel's) scope entirely; ACTIVE reflects
    # "occurrence completed its detection funnel", not a profitability claim.
    STAGE_FILLED: OUTCOME_ACTIVE,
    # UNFILLED is explicitly documented upstream as "a data-boundary artifact,
    # never a fabricated strategy state" (large_smc_research.decision module
    # docstring) -- WAIT, not a terminal outcome, matches
    # WatchLifecycleRecord.is_terminal=False for this stage.
    STAGE_UNFILLED: OUTCOME_WAIT,
}

# Terminal canonical stages -> V2 outcome. WatchLifecycleRecord.is_terminal is True
# for INVALIDATED/EXPIRED only; BLOCKED is included here as an accepted, documented
# adapter-level terminal decision (see module/parity-status docs), not because
# watch_lifecycle itself marks it terminal.
_TERMINAL_OUTCOME_FOR: Dict[str, str] = {
    STAGE_INVALIDATED: OUTCOME_INVALIDATED,
    STAGE_EXPIRED: OUTCOME_EXPIRED,
    STAGE_BLOCKED: OUTCOME_ERROR,
}


class LargeSMCUnmappedStageError(RuntimeError):
    """Fail-closed: a WatchLifecycleRecord.stage this adapter has no documented
    V2 projection for (today: only STAGE_RESOLVED, unreachable in practice --
    see module docstring)."""


def _serialize_record(record: WatchLifecycleRecord) -> Dict[str, Any]:
    """JSON-stable snapshot of the canonical projection, preserved verbatim as
    `raw_strategy_state` -- never re-derived, only re-encoded for persistence.
    Every field here traces 1:1 to a `WatchLifecycleRecord` attribute."""
    return {
        "setup_family_id": record.setup_family_id,
        "symbol": record.symbol,
        "combination": record.combination,
        "direction": record.direction,
        "reference_key": record.reference_key,
        "stage": record.stage,
        "canonical_state": record.canonical_state,
        "canonical_state_source": record.canonical_state_source,
        "resolution_status": record.resolution_status,
        "first_seen_time": record.first_seen_time.isoformat() if record.first_seen_time else None,
        "last_seen_time": record.last_seen_time.isoformat() if record.last_seen_time else None,
        "ready_time": record.ready_time.isoformat() if record.ready_time else None,
        "final_time": record.final_time.isoformat() if record.final_time else None,
        "terminal": record.terminal,
        "entry_condition": record.entry_condition,
        "maneuver": record.maneuver,
        "entry_type": record.entry_type,
        "invalidation_trigger": record.invalidation_trigger,
    }


@dataclass(frozen=True)
class LargeSMCFunnelAdapter:
    """One instance projects ONE canonical `SetupLedgerRow` occurrence (Large-SMC's
    own occurrence identity, `row.setup_id`) into the V2 universal funnel.

    Constructed by the caller (the existing scheduled watch's own driver, or a
    test) from a `SetupLedgerRow` the canonical watch has already produced --
    see module docstring, "SCHEDULED-WATCH COMPATIBILITY". A later poll of the
    same occurrence constructs a NEW adapter instance with an updated
    `setup_row`/`occurrence_status` snapshot; the adapter itself never mutates
    or re-derives them.
    """

    setup_row: SetupLedgerRow
    occurrence_status: Optional[str] = None
    strategy_id: str = STRATEGY_ID
    strategy_version: str = STRATEGY_VERSION

    def supports(self, event: MarketEvent, binding: StrategyBinding) -> bool:
        return (
            binding.strategy_id == self.strategy_id
            and event.symbol == self.setup_row.symbol
        )

    def observe(self, event: MarketEvent, previous_state: FunnelState) -> StrategyObservation:
        record = project_setup_row(self.setup_row, self.occurrence_status)
        return StrategyObservation(
            strategy_id=self.strategy_id,
            event_id=event.event_id,
            market_data_mode=event.market_data_mode,
            raw_strategy_state={"watch_lifecycle_record": _serialize_record(record)},
        )

    def project(self, observation: StrategyObservation) -> FunnelProjection:
        record_dict = observation.raw_strategy_state["watch_lifecycle_record"]
        canonical_stage = record_dict["stage"]

        if canonical_stage in _TERMINAL_OUTCOME_FOR:
            # Highest stage actually reached, derived ONLY from the canonical
            # record's own ready_time field (never from adapter-side history --
            # see module docstring re why previous_state cannot be consulted
            # here without corrupting the no-op/idempotence check). ready_time
            # set means the occurrence reached READY (WAITING_M5_ENTRY/READY)
            # before terminating; absent it, the safe non-fabricating floor is
            # reported rather than guessed.
            stage = STAGE_TRIGGER_ARMED if record_dict["ready_time"] is not None else STAGE_MARKET_ELIGIBLE
            outcome = _TERMINAL_OUTCOME_FOR[canonical_stage]
        elif canonical_stage in _NONTERMINAL_STAGE_FOR:
            stage = _NONTERMINAL_STAGE_FOR[canonical_stage]
            outcome = _NONTERMINAL_OUTCOME_FOR[canonical_stage]
        else:
            raise LargeSMCUnmappedStageError(
                f"WatchLifecycleRecord.stage {canonical_stage!r} has no documented "
                "V2 funnel projection (see large_smc_adapter module docstring)"
            )

        return FunnelProjection(
            stage=stage,
            outcome=outcome,
            reason_codes=(f"LARGE_SMC_CANONICAL_STAGE:{canonical_stage}",),
            context_evidence={"canonical_state_source": record_dict["canonical_state_source"]},
            setup_evidence={
                "combination": record_dict["combination"],
                "entry_condition": record_dict["entry_condition"],
                "maneuver": record_dict["maneuver"],
            },
            trigger_evidence={
                "entry_type": record_dict["entry_type"],
                "invalidation_trigger": record_dict["invalidation_trigger"],
            },
        )

    def candidate_geometry(self, observation: StrategyObservation) -> Optional[CandidateGeometry]:
        row = self.setup_row
        return CandidateGeometry(
            direction=row.direction,
            entry=row.entry_reference,
            invalidation=row.invalidation_price,
            # SetupLedgerRow carries no target authority (see
            # large_smc_research.decision -- target selection lives on
            # LargeSMCResearchDecision, a separate per-E*M-combination decision
            # this adapter does not consume) -- never fabricated.
            targets=(),
            estimated_rr=None,
        )
