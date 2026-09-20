"""Narrow, non-cutover MI -> SSC compatibility boundary."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional, Sequence

from historical_replay.evaluation_context import ReplayEvaluationContext, ReplayEvaluationError
from session_sweep_continuation.regime import RegimeResult
from strategy_engine.session import Candle

from .models import MarketBiasResult
from .snapshot import MarketIntelligenceSnapshot


class SSCCompatibilityError(ValueError):
    pass


@dataclass(frozen=True)
class SSCCompatibilityContext:
    """Existing SSC run_replay inputs, plus MI identity for parity auditing."""
    event_id: str
    symbol: str
    m15_candles: tuple[Candle, ...]
    m1_candles: Optional[tuple[Candle, ...]]
    bias_result: MarketBiasResult
    regime_result: Optional[RegimeResult]

    def run(self, *, config: dict, session_pair_id: str, trading_date: date,
            pip_size: float, pip_value_per_lot: float = 10.0):
        from session_sweep_continuation.replay import run_replay
        return run_replay(
            self.m15_candles, config, self.symbol, session_pair_id, trading_date,
            pip_size, pip_value_per_lot=pip_value_per_lot,
            bias_result=self.bias_result, m1_candles=self.m1_candles,
            regime_result=self.regime_result,
        )


def build_ssc_compatibility_context(
    snapshot: MarketIntelligenceSnapshot,
    replay_context: ReplayEvaluationContext,
    *,
    bias_result: MarketBiasResult,
    regime_result: Optional[RegimeResult] = None,
) -> SSCCompatibilityContext:
    """Adapt MI identity/provenance to unchanged SSC inputs; no calculations."""
    if snapshot.identity.event_id != replay_context.event_id:
        raise SSCCompatibilityError("MI/SSC event identity mismatch")
    if snapshot.identity.symbol != replay_context.symbol or snapshot.identity.as_of != replay_context.as_of:
        raise SSCCompatibilityError("MI/SSC symbol or as-of mismatch")
    if snapshot.quality.overall_status == "INVALID":
        raise SSCCompatibilityError("invalid MI cannot enter SSC")
    if snapshot.higher_timeframe_context.status != "AVAILABLE":
        raise SSCCompatibilityError("SSC requires available MI higher-timeframe evidence")
    if bias_result.symbol != replay_context.symbol or bias_result.decision_time > replay_context.as_of:
        raise SSCCompatibilityError("SSC bias evidence is for a different event")
    m15 = replay_context.candles("M15")
    m1 = replay_context.candles("M1") if "M1" in replay_context.timeframes else None
    return SSCCompatibilityContext(snapshot.identity.event_id, replay_context.symbol,
                                   tuple(m15), tuple(m1) if m1 is not None else None,
                                   bias_result, regime_result)
