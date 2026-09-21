"""SSC (ST_SESSION_SWEEP_CONTINUATION_V1) V2-3B shadow/replay adapter.

Thin `opportunity.adapter.StrategyFunnelAdapter` over the EXISTING canonical SSC
decision contract, `strategy_contract.decision.StrategyDecision` as built by
`strategy_contract.decision.from_session_sweep_continuation_replay` from a
`session_sweep_continuation.replay.ReplayResult`. That `ReplayResult` is the
canonical, UNCHANGED-BEHAVIOR output of `session_sweep_continuation.replay.
run_replay` (H1 bias / M15 regime / S1-S2-S3 setup evaluation / campaign risk
control / outcome resolution -- see that module's own docstring), reached either
directly or through `session_sweep_continuation.canonical_consumer.
run_canonical_shadow_cycle`, which is this strategy's own existing canonical-
observation replay/data authority (MARKET_BIAS + MARKET_REGIME wrapped as
`trading_skills.MarketObservation`, unwrapped and passed to `run_replay`
UNCHANGED -- see canonical_consumer.py's module docstring).

This adapter does NOT reimplement H1 bias, M15 regime/session logic, S1/S2/S3
setup rules, campaign risk allocation, or outcome resolution. It only maps
already-canonical `StrategyDecision.setup_properties` fields (themselves copied
verbatim from `ReplayResult`/`Campaign` by `from_session_sweep_continuation_
replay`, never recomputed) onto the V2 universal funnel:

    S1/S2/S3 setup evaluation / campaign state machine   (canonical strategy truth)
            |  replay.run_replay (existing, UNCHANGED)
            v
    ReplayResult / Campaign                                (existing canonical output)
            |  strategy_contract.decision.from_session_sweep_continuation_replay
            |  (existing, UNCHANGED)
            v
    StrategyDecision.setup_properties                      (existing canonical contract)
            |  _CAMPAIGN_STATUS_TO_STAGE / _CAMPAIGN_STATUS_TO_OUTCOME (THIS module, new)
            v
    opportunity.stages FUNNEL_STAGES / FUNNEL_OUTCOMES     (V2 universal funnel)

REPLAY AUTHORITY / DATA-MODE FIREWALL: this module never fetches MT5 or any live
feed itself -- it consumes only an already-built `StrategyDecision` (a frozen
dataclass produced upstream from an already-run replay). `market_data_mode` is
carried on the `MarketEvent`/`StrategyObservation` the caller supplies, exactly
as every other opportunity adapter does; this module never inspects or mutates
it, so a REPLAY-mode event cannot silently become REAL/LIVE by passing through
here (see `opportunity.contracts.synthetic_or_replay_block_reasons`, downstream
of this adapter's output, for where that firewall is actually enforced).

INTENDED EVENT-IDENTITY PATTERN: `opportunity.engine._candidate_id` keys
candidate identity off `(strategy_id, strategy_version, event.event_id,
symbol)`. For "the same logical session-pair/trading-date occurrence produces
ONE candidate across a day's repeated cycles" to hold, the caller must build one
`MarketEvent` per occurrence whose `event_id` is stable across re-evaluations of
the SAME (symbol, session_pair, trading_date) decision cycle -- e.g.
`event_id=f"SSC:{symbol}:{session_pair}:{trading_date}"` -- deliberately
excluding direction, since a campaign's direction is resolved DURING the cycle
(no campaign yet -> direction known) and identity must survive that transition.

FAIL-CLOSED: an unrecognized `campaign_status` string (i.e. not one of
`session_sweep_continuation.campaign.CampaignStatus`'s five members) raises
`SSCUnmappedCampaignStatusError` rather than defaulting to any funnel stage.

NO EXECUTION AUTHORITY: imports only `strategy_contract.decision`
(StrategyDecision, a plain dataclass) -- never `execution.*`, `mt5.executor`, or
`mt5.mt5_gateway` -- enforced by tests/test_opportunity_import_boundaries.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from strategy_contract.decision import StrategyDecision

from .adapter import FunnelProjection, StrategyObservation
from .contracts import CandidateGeometry, MarketEvent
from .registry_binding import StrategyBinding
from .stages import (
    OUTCOME_ACTIVE,
    OUTCOME_EXPIRED,
    OUTCOME_INVALIDATED,
    OUTCOME_WAIT,
    STAGE_CONTEXT_VALID,
    STAGE_ENTRY_CONFIRMED,
    STAGE_MARKET_ELIGIBLE,
    STAGE_OPPORTUNITY_READY,
    STAGE_SETUP_DETECTED,
)
from .transitions import FunnelState

STRATEGY_ID = "ST_SESSION_SWEEP_CONTINUATION_V1"
STRATEGY_VERSION = "1.0.1"

CAMPAIGN_STATUS_ACTIVE = "ACTIVE"
CAMPAIGN_STATUS_INVALIDATED = "INVALIDATED"
CAMPAIGN_STATUS_SESSION_EXPIRED = "SESSION_EXPIRED"
CAMPAIGN_STATUS_RISK_EXHAUSTED = "RISK_EXHAUSTED"
CAMPAIGN_STATUS_COMPLETE = "COMPLETE"

_KNOWN_CAMPAIGN_STATUSES = frozenset(
    {
        CAMPAIGN_STATUS_ACTIVE,
        CAMPAIGN_STATUS_INVALIDATED,
        CAMPAIGN_STATUS_SESSION_EXPIRED,
        CAMPAIGN_STATUS_RISK_EXHAUSTED,
        CAMPAIGN_STATUS_COMPLETE,
    }
)

REGIME_UNKNOWN = "UNKNOWN"


class SSCUnmappedCampaignStatusError(RuntimeError):
    """Fail-closed: a campaign_status this adapter has no documented V2
    projection for (session_sweep_continuation.campaign.CampaignStatus gained a
    member this adapter has not been updated for)."""


class SSCStrategyIdentityMismatchError(RuntimeError):
    """Fail-closed: the StrategyDecision handed to this adapter was not built
    from an ST_SESSION_SWEEP_CONTINUATION_V1 decision -- never silently
    adopted under a mismatched strategy identity."""


def _serialize_setup_properties(decision: StrategyDecision) -> Dict[str, Any]:
    """JSON-stable snapshot of the fields this adapter actually consumes, copied
    verbatim from `StrategyDecision.setup_properties` (itself already copied
    verbatim from `ReplayResult`/`Campaign` upstream -- see module docstring).
    `accepted_setups`/`rejected_setups` are preserved exactly as produced by
    `session_sweep_continuation.replay.run_replay` -- never recomputed here."""
    props = decision.setup_properties
    return {
        "trading_date": props.get("trading_date"),
        "session_pair": props.get("session_pair"),
        "regime": props.get("regime"),
        "campaign_status": props.get("campaign_status"),
        "entry_count": props.get("entry_count", 0),
        "open_risk_pct": props.get("open_risk_pct", 0.0),
        "accepted_setups": props.get("accepted_setups", []),
        "rejected_setups": props.get("rejected_setups", []),
        "observations": props.get("observations", []),
        "direction": decision.direction,
        "evidence_ref": decision.evidence_ref,
    }


def _project_no_campaign(regime: Optional[str]) -> FunnelProjection:
    """No `Campaign` has formed yet this cycle (StrategyDecision.setup_properties
    ["campaign_status"] is None) -- either the reference session/regime has not
    been classified yet, or the regime resolved to UNKNOWN (session_sweep_
    continuation.state_machine.State.NO_TRADE, a terminal-for-the-day rejection
    per that module's own state table)."""
    if regime is None:
        return FunnelProjection(
            stage=STAGE_MARKET_ELIGIBLE,
            outcome=OUTCOME_WAIT,
            reason_codes=("SSC_REGIME_NOT_YET_CLASSIFIED",),
        )
    if regime == REGIME_UNKNOWN:
        return FunnelProjection(
            stage=STAGE_CONTEXT_VALID,
            outcome=OUTCOME_INVALIDATED,
            reason_codes=("SSC_REGIME_UNKNOWN_NO_TRADE",),
            context_evidence={"regime": regime},
        )
    return FunnelProjection(
        stage=STAGE_CONTEXT_VALID,
        outcome=OUTCOME_WAIT,
        reason_codes=("SSC_REGIME_CLASSIFIED_NO_SETUP_YET",),
        context_evidence={"regime": regime},
    )


def _project_campaign(campaign_status: str, entry_count: int) -> FunnelProjection:
    has_entries = entry_count > 0
    if campaign_status == CAMPAIGN_STATUS_ACTIVE:
        stage = STAGE_ENTRY_CONFIRMED if has_entries else STAGE_SETUP_DETECTED
        return FunnelProjection(stage=stage, outcome=OUTCOME_ACTIVE, reason_codes=("SSC_CAMPAIGN_ACTIVE",))
    if campaign_status == CAMPAIGN_STATUS_INVALIDATED:
        stage = STAGE_ENTRY_CONFIRMED if has_entries else STAGE_SETUP_DETECTED
        return FunnelProjection(stage=stage, outcome=OUTCOME_INVALIDATED, reason_codes=("SSC_CAMPAIGN_INVALIDATED",))
    if campaign_status == CAMPAIGN_STATUS_SESSION_EXPIRED:
        stage = STAGE_ENTRY_CONFIRMED if has_entries else STAGE_SETUP_DETECTED
        return FunnelProjection(stage=stage, outcome=OUTCOME_EXPIRED, reason_codes=("SSC_CAMPAIGN_SESSION_EXPIRED",))
    if campaign_status == CAMPAIGN_STATUS_RISK_EXHAUSTED:
        # Terminal, but not a setup-quality rejection: at least one entry already
        # exists (risk budget can only be exhausted by prior entries -- see
        # campaign.allocate_risk), so ENTRY_CONFIRMED is always the correct stage
        # here. Mapped to EXPIRED (documented, accepted choice: "no further
        # entries possible today", distinct from a structural INVALIDATED) rather
        # than fabricating a dedicated V2 outcome -- see parity status doc.
        return FunnelProjection(
            stage=STAGE_ENTRY_CONFIRMED,
            outcome=OUTCOME_EXPIRED,
            reason_codes=("SSC_CAMPAIGN_RISK_EXHAUSTED",),
        )
    if campaign_status == CAMPAIGN_STATUS_COMPLETE:
        # Campaign closed out normally (state_machine.Event.CAMPAIGN_CLOSED).
        # ACTIVE, not a terminal V2 outcome: trade P&L / success is out of the
        # opportunity funnel's scope entirely (see opportunity strategy-model
        # doc, "candidate != proposal != risk approval"); the occurrence simply
        # completed its detection/management lifecycle.
        return FunnelProjection(
            stage=STAGE_OPPORTUNITY_READY,
            outcome=OUTCOME_ACTIVE,
            reason_codes=("SSC_CAMPAIGN_COMPLETE",),
        )
    raise SSCUnmappedCampaignStatusError(
        f"campaign_status {campaign_status!r} has no documented V2 funnel projection "
        "(see ssc_adapter module docstring)"
    )


@dataclass(frozen=True)
class SSCFunnelAdapter:
    """One instance projects ONE canonical `StrategyDecision` (built upstream by
    `strategy_contract.decision.from_session_sweep_continuation_replay` from one
    `session_sweep_continuation.replay.run_replay` decision cycle) into the V2
    universal funnel. Constructed by the caller per cycle -- see module
    docstring, "REPLAY AUTHORITY / DATA-MODE FIREWALL"."""

    decision: StrategyDecision
    strategy_id: str = STRATEGY_ID
    strategy_version: str = STRATEGY_VERSION

    def __post_init__(self) -> None:
        if self.decision.strategy_id != self.strategy_id:
            raise SSCStrategyIdentityMismatchError(
                f"StrategyDecision.strategy_id {self.decision.strategy_id!r} does not "
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
            raw_strategy_state={"setup_properties": _serialize_setup_properties(self.decision)},
        )

    def project(self, observation: StrategyObservation) -> FunnelProjection:
        props = observation.raw_strategy_state["setup_properties"]
        campaign_status = props.get("campaign_status")
        if campaign_status is None:
            projection = _project_no_campaign(props.get("regime"))
        else:
            if campaign_status not in _KNOWN_CAMPAIGN_STATUSES:
                raise SSCUnmappedCampaignStatusError(
                    f"campaign_status {campaign_status!r} has no documented V2 funnel "
                    "projection (see ssc_adapter module docstring)"
                )
            projection = _project_campaign(campaign_status, int(props.get("entry_count", 0)))

        setup_evidence = {
            "accepted_setups": props.get("accepted_setups", []),
            "session_pair": props.get("session_pair"),
            "trading_date": props.get("trading_date"),
        }
        trigger_evidence = {"rejected_setups": props.get("rejected_setups", [])}
        context_evidence = dict(projection.context_evidence)
        context_evidence.setdefault("regime", props.get("regime"))
        context_evidence["observations"] = props.get("observations", [])

        return FunnelProjection(
            stage=projection.stage,
            outcome=projection.outcome,
            reason_codes=projection.reason_codes,
            context_evidence=context_evidence,
            setup_evidence=setup_evidence,
            trigger_evidence=trigger_evidence,
        )

    def candidate_geometry(self, observation: StrategyObservation) -> Optional[CandidateGeometry]:
        props = observation.raw_strategy_state["setup_properties"]
        direction = props.get("direction")
        if direction is None:
            # No campaign/direction resolved yet this cycle -- never fabricated.
            return None
        # session_sweep_continuation's accepted-entry geometry (entry_price/
        # stop_price) lives on Campaign.entries (CampaignEntry), which is not
        # copied into StrategyDecision.setup_properties by
        # from_session_sweep_continuation_replay today (that function copies
        # accepted_setups/rejected_setups -- pre-acceptance setup records -- not
        # the campaign's realized entries). Rather than reach past the existing
        # canonical decision contract to re-derive entry/stop from
        # accepted_setups (which would risk disagreeing with Campaign.entries),
        # this adapter reports direction only and leaves entry/invalidation/
        # targets unavailable -- documented, non-fabricated gap (see parity
        # status doc), not a silent omission.
        return CandidateGeometry(direction=direction, entry=None, invalidation=None, targets=(), estimated_rr=None)
