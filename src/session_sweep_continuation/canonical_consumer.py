"""Canonical StrategyController consumer for ST_SESSION_SWEEP_CONTINUATION_V1
(AG_PLAN2_GOLDEN_STRATEGY_CANONICAL_OBSERVATION_MIGRATION_V1, P6).

`run_canonical_shadow_cycle` calls `session_sweep_continuation.replay.run_replay`
UNCHANGED in behavior -- no strategy, risk, friction, or replay logic is reimplemented
here. Its only job is to route both this decision cycle's MARKET_BIAS and MARKET_REGIME
observations through the `bias_result`/`regime_result` parameters run_replay already
accepts (transparent round trip: wrap via H1MarketBiasSkill/M15RegimeSkill, unwrap via
unwrap_bias_observation/unwrap_regime_observation, pass to the same call the legacy
script already makes). AG_PLAN2_GOLDEN_CANONICAL_COMPLETION_V1: MARKET_REGIME is now
FULLY_INJECTED, closing the LEGACY_COUPLING_DEBT the prior slice recorded.

SessionSweepContinuationCanonicalController satisfies
strategy_contract.controller.StrategyController structurally (strategy_id property +
evaluate(market_context) -> Optional[StrategyDecision]) -- the SHADOW_ONLY canonical
seam this strategy did not have before. It never places an order, never touches
lifecycle/demo/live authorization, and its output is view-only (strategy_contract.
decision.StrategyDecision is itself documented as never fed back into a strategy
engine)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, List, Mapping, Optional, Sequence

from strategy_engine.session.candles import Candle
from trading_skills import MarketObservation

from . import STRATEGY_ID, STRATEGY_VERSION
from .canonical_observations import (
    H1MarketBiasSkill,
    M15RegimeSkill,
    ObservationValidationError,
    unwrap_bias_observation,
    unwrap_regime_observation,
)
from .h1_bias import HistoricalCandleStore, HistoricalSymbolMetadataManifest
from .replay import ReplayResult, run_replay
from .sessions import build_reference_session, session_windows_from_config


@dataclass(frozen=True)
class CanonicalCycleResult:
    symbol: str
    session_pair: str
    trading_date: object
    observations: List[MarketObservation]
    replay_result: ReplayResult


def build_market_observations(
    *,
    h1_store: HistoricalCandleStore,
    manifest: HistoricalSymbolMetadataManifest,
    m15_candles: Sequence[Candle],
    config: dict,
    symbol: str,
    session_pair_id: str,
    trading_date,
    decision_time: datetime,
    pip_size: float,
) -> List[MarketObservation]:
    """Builds this decision cycle's canonical observations without altering any
    existing strategy input. `decision_time` must be the SAME instant the legacy path
    resolves bias at (the reference-session close, ref_window.bounds_for_date(...)[1])
    -- callers should pass the identical value used for the legacy comparison run."""
    observations: List[MarketObservation] = []

    bias_observation = H1MarketBiasSkill().evaluate({
        "h1_store": h1_store, "manifest": manifest, "symbol": symbol,
        "decision_time": decision_time, "session_pair": session_pair_id,
    })
    observations.append(bias_observation)

    windows = session_windows_from_config(config)[session_pair_id]
    ref_window = windows["reference"]
    ref_end = ref_window.bounds_for_date(trading_date)[1]
    reference = build_reference_session(m15_candles, ref_window, trading_date, ref_end, pip_size)
    if reference.candle_count > 0 and reference.high is not None:
        reference_closes = [c.close for c in m15_candles if c.time < ref_end]
        regime_observation = M15RegimeSkill().evaluate({
            "reference_closes": reference_closes, "range_pips": reference.range_pips,
            "candle_count": reference.candle_count, "config": config, "symbol": symbol,
            "observed_at": ref_end,
        })
        observations.append(regime_observation)

    return observations


def run_canonical_shadow_cycle(
    *,
    h1_store: HistoricalCandleStore,
    manifest: HistoricalSymbolMetadataManifest,
    m15_candles: Sequence[Candle],
    config: dict,
    symbol: str,
    session_pair_id: str,
    trading_date,
    decision_time: datetime,
    pip_size: float,
    pip_value_per_lot: float = 10.0,
    m1_candles: Optional[Sequence[Candle]] = None,
) -> CanonicalCycleResult:
    """SHADOW_ONLY: computes canonical observations for this cycle, then calls the
    UNCHANGED-BEHAVIOR run_replay through its existing bias_result/regime_result
    parameters -- BOTH observations are actually consumed, not merely compared.
    Fail-closed: an untrustworthy bias/regime observation raises
    (ObservationValidationError propagates, never silently substituted); a missing
    bias observation degrades to run_replay's own existing None-bias fail-closed path
    (BIAS_MISSING), exactly like the legacy script; a missing regime observation
    (only possible when the reference session itself has no candles yet) degrades to
    run_replay's own existing internal classify_regime() call -- never a guessed
    regime."""
    observations = build_market_observations(
        h1_store=h1_store, manifest=manifest, m15_candles=m15_candles, config=config,
        symbol=symbol, session_pair_id=session_pair_id, trading_date=trading_date,
        decision_time=decision_time, pip_size=pip_size,
    )
    bias_observation = next((o for o in observations if o.skill_id == "H1_MARKET_BIAS_V1"), None)
    regime_observation = next((o for o in observations if o.skill_id == "M15_MARKET_REGIME_V1"), None)

    bias_result = unwrap_bias_observation(bias_observation, symbol=symbol, decision_time=decision_time)
    regime_result = None
    if regime_observation is not None:
        regime_result = unwrap_regime_observation(
            regime_observation, symbol=symbol, observed_at=regime_observation.observed_at,
        )

    replay_result = run_replay(
        m15_candles, config, symbol, session_pair_id, trading_date, pip_size,
        pip_value_per_lot=pip_value_per_lot, bias_result=bias_result, m1_candles=m1_candles,
        regime_result=regime_result,
    )

    return CanonicalCycleResult(
        symbol=symbol, session_pair=session_pair_id, trading_date=trading_date,
        observations=observations, replay_result=replay_result,
    )


@dataclass(frozen=True)
class SessionSweepContinuationCanonicalController:
    """Structurally satisfies strategy_contract.controller.StrategyController.
    SHADOW_ONLY: `evaluate` never places, authorizes, or proposes an order -- it
    returns a view-only StrategyDecision built from the same run_replay this
    strategy's existing golden-replay script already calls."""

    @property
    def strategy_id(self) -> str:
        return STRATEGY_ID

    def evaluate(self, market_context: Mapping[str, Any]) -> Optional[Any]:
        from strategy_contract.decision import from_session_sweep_continuation_replay

        cycle = run_canonical_shadow_cycle(**market_context)
        return from_session_sweep_continuation_replay(cycle.replay_result, cycle.observations)
