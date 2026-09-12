"""StrategyDecision -- a canonical, LEAN AlphaModel->Insight-inspired, Strategy-side
decision contract (AG_STRATEGY_TECH_SELECTIVE_PORT_AND_REUSE_V1, Phase 1).

NON-GOALS (read first): this module is an ADDITIVE, READ-ONLY, ONE-WAY VIEW layer. It
does not replace, wrap, mutate, or change the behavior, economics, authority, or
historical attribution of any native strategy output. The three native decision shapes
remain the sole authoritative record for their strategies:

- FX:        src/post_asian_pilot/decision.py::PostAsianDecision   (ST_ASIAN_SWEEP_5R_V1)
- BTC:       src/strategy_engine/sweep_retest/models.py::SetupState (ST_LIQUIDITY_SWEEP_RETEST_V1)
- Large-SMC: src/large_smc_research/decision.py::LargeSMCResearchDecision (ST_LARGE_SMC_V1)

A StrategyDecision is built FROM an already-produced native decision object; it is NEVER
fed back into a strategy engine and NEVER used to reconstruct/replace a native decision.
It carries NO account/broker/lot-size/margin/order/fill fields -- those remain Execution's
exclusive responsibility (see docs/architecture/AG_TWO_SYSTEM_OPEN_SOURCE_REUSE_LEDGER.md
for the Strategy/Execution boundary this preserves).

Field provenance (nothing here is fabricated; every field is either copied verbatim from
the native decision or explicitly None when the native decision has no such value):

- strategy_id / strategy_version: identity. Copied verbatim from the native decision where
  the native shape carries it (FX's PostAsianDecision, Large-SMC's LargeSMCResearchDecision
  both already stamp strategy_id/strategy_version themselves). BTC's SetupState does NOT
  carry strategy_version in its own frozen dataclass (see models.py) -- the adapter
  requires the caller to pass strategy_version explicitly, sourced from
  strategies/ST_LIQUIDITY_SWEEP_RETEST_V1.yaml / strategies/registry.yaml, never invented.
- symbol: verbatim.
- direction: "LONG" / "SHORT" / None. None whenever the native decision has not reached a
  directional qualification (e.g. FX WATCH/NO_TRADE with no signal, BTC WAITING_*, Large-
  SMC WATCH/NO_TRADE).
- decision_timestamp: the native decision's OWN authoritative evaluation/decision time --
  PostAsianDecision.evaluation_time, SetupState.evaluated_at,
  LargeSMCResearchDecision.evaluation_timestamp -- never wall-clock "now" recomputed here.
- confidence: always None for all three strategies today. None of the three native models
  currently emit a probabilistic confidence score; this field exists for contract-shape
  compatibility with a future strategy that does, and is explicitly NOT fabricated (e.g.
  never derived from R-multiple, win-rate, or any proxy) for FX/BTC/Large-SMC.
- evidence_ref: an opaque identifier that lets a caller look the FULL native decision back
  up (PostAsianDecision.decision_id, SetupState.setup_id,
  LargeSMCResearchDecision.candidate_occurrence_id or event_id) -- StrategyDecision itself
  is never a substitute for the native evidence dict.
- setup_properties: a plain dict of native, strategy-specific observations, copied
  verbatim, never recomputed or backfilled. Where the native strategy has no valid value
  for a would-be-common field (most importantly: Large-SMC's stop is always None this
  phase because C10 -- the broker-stop contract gap -- is UNSIGNED), the corresponding key
  is set to None and the native blocking reason code is preserved under
  setup_properties["blockers"] -- never a fabricated numeric stop or target.

This module changes no native strategy behavior, output, or version, and grants no new
execution authority to anything.

WP1/WP4 market-truth propagation (AG_CANONICAL_R2_R4_PROPOSAL_PIPELINE_V1): each adapter
now accepts an optional `market_snapshot: MarketSnapshot` (src/strategy_contract/
market_snapshot.py). When supplied, its market_data_mode/source/asof/fingerprint are
copied VERBATIM onto the resulting StrategyDecision -- never recomputed, never
defaulted to REAL, never inferred from the native decision (none of the three native
decision shapes carry a mode field of their own; this is the sole channel by which mode
provenance reaches a StrategyDecision). When omitted, the four market_data_* fields stay
None -- this is the pre-WP4 shape, preserved for the existing test suite and any future
caller that has no snapshot available. Fail-closed guard: a symbol mismatch between the
snapshot and the native decision raises MARKET_SNAPSHOT_SYMBOL_MISMATCH rather than
silently attaching the wrong market's provenance to a decision.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

from large_smc_research.decision import LargeSMCResearchDecision
from post_asian_pilot.decision import PostAsianDecision
from session_sweep_continuation.replay import ReplayResult
from strategy_engine.sweep_retest.models import SetupState, TERMINAL_STATES
from strategy_contract.market_snapshot import MarketSnapshot


@dataclass(frozen=True)
class StrategyDecision:
    """Canonical Strategy-side decision contract. See module docstring for field
    provenance rules -- every value here is either copied verbatim from a native decision
    or explicitly None; nothing is derived, estimated, or fabricated by this module."""

    strategy_id: str
    strategy_version: str
    symbol: str
    direction: Optional[str]
    decision_timestamp: Optional[datetime]
    confidence: Optional[float]
    evidence_ref: Optional[str]
    setup_properties: Dict[str, Any] = field(default_factory=dict)
    market_data_mode: Optional[str] = None
    market_data_source: Optional[str] = None
    market_data_asof: Optional[datetime] = None
    market_data_fingerprint: Optional[str] = None


class MarketSnapshotSymbolMismatch(ValueError):
    """Raised when a market_snapshot passed to an adapter names a different symbol than
    the native decision it is being attached to -- fail closed rather than silently
    mislabeling one market's provenance onto another market's decision."""


def _require_matching_symbol(symbol: str, market_snapshot: Optional[MarketSnapshot]) -> None:
    if market_snapshot is not None and market_snapshot.symbol != symbol:
        raise MarketSnapshotSymbolMismatch(
            f"MARKET_SNAPSHOT_SYMBOL_MISMATCH: decision symbol {symbol!r} != "
            f"market_snapshot.symbol {market_snapshot.symbol!r}"
        )


def from_fx_decision(
    decision: PostAsianDecision, market_snapshot: Optional[MarketSnapshot] = None,
) -> StrategyDecision:
    """FX / ST_ASIAN_SWEEP_5R_V1. PostAsianDecision already stamps strategy_id and
    strategy_version itself -- no external parameter needed. direction/entry/stop_loss
    are only present on decision.signal (a TradeSignal), which is None unless status is
    READY; when present they are copied verbatim, never recomputed.

    market_snapshot (optional): the MarketSnapshot the caller retrieved for this
    symbol/timeframe/cycle. Its mode/source/asof/fingerprint are copied verbatim; see
    module docstring. Raises MarketSnapshotSymbolMismatch if its symbol disagrees with
    decision.symbol."""
    _require_matching_symbol(decision.symbol, market_snapshot)
    signal = decision.signal
    setup_properties: Dict[str, Any] = {
        "status": decision.status,
        "reason_codes": decision.reason_codes,
        "reference_session": decision.reference_session,
        "trading_date": decision.trading_date,
        "trigger_type": decision.trigger_type,
        "trigger_level": decision.trigger_level,
        "trigger_timeframe": decision.trigger_timeframe,
        "valid_until": decision.valid_until,
        "entry": signal.entry if signal is not None else None,
        "stop_loss": signal.stop_loss if signal is not None else None,
        "setup": signal.setup if signal is not None else None,
    }
    return StrategyDecision(
        strategy_id=decision.strategy_id,
        strategy_version=decision.strategy_version,
        symbol=decision.symbol,
        direction=signal.direction if signal is not None else None,
        decision_timestamp=decision.ready_at or decision.evaluation_time,
        confidence=None,
        evidence_ref=decision.decision_id,
        setup_properties=setup_properties,
        market_data_mode=market_snapshot.market_data_mode if market_snapshot else None,
        market_data_source=market_snapshot.source if market_snapshot else None,
        market_data_asof=market_snapshot.market_data_asof if market_snapshot else None,
        market_data_fingerprint=market_snapshot.fingerprint if market_snapshot else None,
    )


def from_btc_setup_state(
    state: SetupState, strategy_version: str, market_snapshot: Optional[MarketSnapshot] = None,
) -> StrategyDecision:
    """BTC / ST_LIQUIDITY_SWEEP_RETEST_V1 (research-only; broker_execution=DISABLED).
    SetupState carries no strategy_version field of its own (see models.py) -- the caller
    must supply it from strategy config (never invented here). `strategy_qualified` /
    `tradability_blocked` are preserved verbatim under setup_properties so the two-layer
    qualification-vs-tradability distinction the engine documents is not collapsed.

    market_snapshot (optional): see from_fx_decision docstring for the propagation
    contract; raises MarketSnapshotSymbolMismatch on a symbol disagreement."""
    _require_matching_symbol(state.symbol, market_snapshot)
    setup_properties: Dict[str, Any] = {
        "state": state.state,
        "reason_code": state.reason_code,
        "profile_id": state.profile_id,
        "entry": state.entry,
        "stop_loss": state.stop_loss,
        "tp1": state.tp1,
        "tp2": state.tp2,
        "tp2_r_multiple": state.tp2_r_multiple,
        "strategy_qualified": state.strategy_qualified,
        "tradability_blocked": state.tradability_blocked,
        "tradability_reason": state.tradability_reason,
        "is_terminal": state.state in TERMINAL_STATES,
    }
    return StrategyDecision(
        strategy_id=state.strategy_id,
        strategy_version=strategy_version,
        symbol=state.symbol,
        direction=state.direction,
        decision_timestamp=state.evaluated_at,
        confidence=None,
        evidence_ref=state.setup_id,
        setup_properties=setup_properties,
        market_data_mode=market_snapshot.market_data_mode if market_snapshot else None,
        market_data_source=market_snapshot.source if market_snapshot else None,
        market_data_asof=market_snapshot.market_data_asof if market_snapshot else None,
        market_data_fingerprint=market_snapshot.fingerprint if market_snapshot else None,
    )


def from_large_smc_decision(
    decision: LargeSMCResearchDecision, market_snapshot: Optional[MarketSnapshot] = None,
) -> StrategyDecision:
    """Large-SMC / ST_LARGE_SMC_V1 (research-only; C10 UNSIGNED, proposal-promotion
    BLOCKED). LargeSMCResearchDecision already stamps strategy_id/strategy_version.
    `simulated_broker_stop` is always None this phase (C10 unsigned) -- copied verbatim,
    NEVER substituted with structural_invalidation_price or any other value, and the
    UNSIGNED_CONTRACT:C10_BROKER_STOP reason code (when present) is surfaced explicitly
    under setup_properties["blockers"] so the C10 gap is never silently dropped.

    market_snapshot (optional): see from_fx_decision docstring for the propagation
    contract. Large-SMC's replay-derived research runs will typically pass a REPLAY-mode
    snapshot, never REAL -- see historical_replay/'s data source; raises
    MarketSnapshotSymbolMismatch on a symbol disagreement."""
    _require_matching_symbol(decision.symbol, market_snapshot)
    blockers = tuple(rc for rc in decision.reason_codes if rc.startswith("UNSIGNED_CONTRACT"))
    setup_properties: Dict[str, Any] = {
        "state": decision.state,
        "reason_codes": decision.reason_codes,
        "missing_conditions": decision.missing_conditions,
        "combination": decision.combination,
        "entry_price": decision.entry_price,
        "entry_low": decision.entry_low,
        "entry_high": decision.entry_high,
        "stop_loss": decision.simulated_broker_stop,  # always None this phase -- see docstring
        "target_price": decision.target_price,
        "target_tier": decision.target_tier,
        "structural_invalidation_price": decision.structural_invalidation_price,
        "data_quality_state": decision.data_quality_state,
        "blockers": blockers,
    }
    return StrategyDecision(
        strategy_id=decision.strategy_id,
        strategy_version=decision.strategy_version,
        symbol=decision.symbol,
        direction=decision.direction,
        decision_timestamp=decision.evaluation_timestamp,
        confidence=None,
        evidence_ref=decision.candidate_occurrence_id or decision.event_id,
        setup_properties=setup_properties,
        market_data_mode=market_snapshot.market_data_mode if market_snapshot else None,
        market_data_source=market_snapshot.source if market_snapshot else None,
        market_data_asof=market_snapshot.market_data_asof if market_snapshot else None,
        market_data_fingerprint=market_snapshot.fingerprint if market_snapshot else None,
    )


def from_session_sweep_continuation_replay(
    replay_result: ReplayResult,
    observations: Optional[list] = None,
    strategy_version: str = "1.0.0",
) -> StrategyDecision:
    """ST_SESSION_SWEEP_CONTINUATION_V1 (research-only; OFFLINE_RESEARCH lifecycle
    stage, no demo/live authorization). ReplayResult is one full decision-cycle
    (symbol x session_pair x trading_date) outcome from session_sweep_continuation.
    replay.run_replay -- unlike PostAsianDecision/SetupState/LargeSMCResearchDecision,
    it carries no strategy_version field of its own (see session_sweep_continuation.
    STRATEGY_VERSION), so the caller supplies it (defaulting to the current frozen
    "1.0.0"); it is never invented per-call.

    `observations` (optional): the canonical MarketObservation[] this cycle's shadow
    path produced (session_sweep_continuation.canonical_consumer.
    run_canonical_shadow_cycle) -- copied verbatim (skill_id/version/classification
    only, never the full evidence payload) under setup_properties["observations"] for
    traceability; omitted (None) when the caller has no canonical observations for this
    cycle (e.g. the legacy-only path).

    decision_timestamp is always None: ReplayResult carries only a trading_date (a
    date, not a timestamp) and no single evaluation instant of its own -- never
    fabricated here. direction is the campaign's direction once one exists, else None
    (mirrors "no directional qualification yet", the same convention the other three
    adapters use)."""
    campaign = replay_result.campaign
    setup_properties: Dict[str, Any] = {
        "trading_date": str(replay_result.trading_date),
        "session_pair": replay_result.session_pair,
        "regime": replay_result.regime,
        "campaign_status": campaign.status.value if campaign else None,
        "entry_count": campaign.entry_count if campaign else 0,
        "open_risk_pct": campaign.open_risk_pct if campaign else 0.0,
        "accepted_setups": replay_result.accepted_setups,
        "rejected_setups": replay_result.rejected_setups,
        "observations": [
            {"skill_id": o.skill_id, "skill_version": o.skill_version, "classification": o.classification}
            for o in observations
        ] if observations else [],
    }
    return StrategyDecision(
        strategy_id="ST_SESSION_SWEEP_CONTINUATION_V1",
        strategy_version=strategy_version,
        symbol=replay_result.symbol,
        direction=campaign.direction if campaign else None,
        decision_timestamp=None,
        confidence=None,
        evidence_ref=campaign.campaign_id if campaign else None,
        setup_properties=setup_properties,
    )
