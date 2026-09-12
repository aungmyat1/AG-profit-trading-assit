"""Canonical StrategyController consumer for ST_ASIAN_SWEEP_5R_V1
(AG_PROJECT_ARCHITECTURE_READINESS_COMPLETION_V1, following the golden
session_sweep_continuation.canonical_consumer template).

`run_canonical_shadow_evaluate` calls `strategy_engine.engine.evaluate` UNCHANGED in
behavior -- no strategy, risk, or setup logic is reimplemented here. Its only job is to
route this decision cycle's MARKET_REGIME observation through the `regime_override`
parameter `evaluate`/`route_completed_session` now accept (transparent round trip: wrap
via SessionRegimeSkill, unwrap via unwrap_regime_observation, pass to the same call the
legacy pipeline already makes).

AsianSweepCanonicalController satisfies strategy_contract.controller.StrategyController
structurally. SHADOW_ONLY: never places an order, never touches lifecycle/demo/live
authorization. Its output reuses strategy_contract.decision.from_fx_decision UNCHANGED
(the same adapter post_asian_pilot.pipeline already calls for the native/live path) --
no new StrategyDecision adapter was written for this strategy, because the FX adapter
already exists and already covers PostAsianDecision verbatim."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, List, Mapping, Optional, Sequence

from trading_skills import MarketObservation

from .canonical_observations import SessionRegimeSkill, unwrap_regime_observation
from .engine import evaluate as evaluate_strategy
from .models import StrategyConfig
from .session.candles import Candle


@dataclass(frozen=True)
class CanonicalEvaluationResult:
    symbol: str
    pair_id: str
    session_date: date
    observations: List[MarketObservation]
    signal: Any  # strategy_engine.models.TradeSignal


def build_market_observations(
    *,
    session_name: str,
    session_candles: Sequence[Candle],
    expected_bar_count: int,
    symbol: str,
    observed_at: datetime,
) -> List[MarketObservation]:
    return [
        SessionRegimeSkill().evaluate({
            "session_name": session_name, "session_candles": session_candles,
            "expected_bar_count": expected_bar_count, "symbol": symbol, "observed_at": observed_at,
        })
    ]


def run_canonical_shadow_evaluate(
    *,
    strategy: StrategyConfig,
    pair_id: str,
    symbol: str,
    session_date: date,
    session_candles: Sequence[Candle],
    expected_bar_count: int,
    session_name: str,
    observed_at: datetime,
    post_session_candles: Sequence[Candle] = (),
) -> CanonicalEvaluationResult:
    """SHADOW_ONLY: computes the canonical MARKET_REGIME observation for this cycle,
    then calls the UNCHANGED-BEHAVIOR strategy_engine.engine.evaluate through its
    existing regime_override parameter. Fail-closed: an untrustworthy regime
    observation raises (ObservationValidationError propagates, never silently
    substituted)."""
    observations = build_market_observations(
        session_name=session_name, session_candles=session_candles,
        expected_bar_count=expected_bar_count, symbol=symbol, observed_at=observed_at,
    )
    regime_observation = observations[0]
    regime = unwrap_regime_observation(regime_observation, symbol=symbol, observed_at=observed_at)

    signal = evaluate_strategy(
        strategy, pair_id, symbol, session_date, session_candles, expected_bar_count,
        post_session_candles=post_session_candles, regime_override=regime,
    )

    return CanonicalEvaluationResult(
        symbol=symbol, pair_id=pair_id, session_date=session_date,
        observations=observations, signal=signal,
    )


@dataclass(frozen=True)
class AsianSweepCanonicalController:
    """Structurally satisfies strategy_contract.controller.StrategyController.
    SHADOW_ONLY: `evaluate` never places, authorizes, or proposes an order -- it
    returns a view-only StrategyDecision built via the SAME from_fx_decision adapter
    the native pipeline already uses (strategy_contract.decision.from_fx_decision +
    post_asian_pilot.decision.map_trade_signal_to_decision, both unchanged)."""

    @property
    def strategy_id(self) -> str:
        return "ST_ASIAN_SWEEP_5R_V1"

    def evaluate(self, market_context: Mapping[str, Any]) -> Optional[Any]:
        from post_asian_pilot.decision import map_trade_signal_to_decision
        from strategy_contract.decision import from_fx_decision

        cycle_kwargs = {k: v for k, v in market_context.items()
                         if k not in ("session_snapshot_id", "window_end_utc")}
        cycle = run_canonical_shadow_evaluate(**cycle_kwargs)
        post_asian_decision = map_trade_signal_to_decision(
            cycle.signal, market_context["session_snapshot_id"],
            market_context["observed_at"], market_context["window_end_utc"],
        )
        return from_fx_decision(post_asian_decision)
