"""Thin TradingSkill adapter wrapping ST_ASIAN_SWEEP_5R_V1's existing deterministic
market-fact component (session.classifier.classify, ER_ONLY_V2) into the canonical
`trading_skills.MarketObservation` shape
(AG_PROJECT_ARCHITECTURE_READINESS_COMPLETION_V1).

Representation transformation only -- see session/classifier.py and session/
reference_box.py for the actual classification logic, called here VERBATIM and never
reimplemented, re-thresholded, or re-timed.

Repository truth (P9.1 discovery, not assumed from the golden strategy): this
strategy has NO H1/bias-resolver dependency anywhere (grep confirmed -- neither
strategy_engine/ nor post_asian_pilot/ import market_intelligence). Its only
externally-classifiable market fact is session regime (TREND/RANGE via ER_ONLY_V2),
which session.router.route_completed_session now accepts as an optional
`regime_override`, mirroring session_sweep_continuation.replay.run_replay's
bias_result/regime_result injection pattern exactly.

SESSION_CONTEXT (the ReferenceBox itself: high/low/mid/range/efficiency_ratio) is
deliberately NOT wrapped as a separate observation, for the same reason the golden
strategy's reference session was deferred: it is raw aggregation consumed directly by
setup detectors (entry_1_trend/entry_2_sweep/entry_3_range use box.session_high/low
etc. as float inputs), not itself a market-fact classification/enum a fail-closed
guard gates on. classify() is called on the box here; the box's own construction is
unchanged and untouched.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Mapping, Optional, Sequence

from trading_skills import MarketObservation, fingerprint_input

from .session.candles import Candle
from .session.classifier import Regime, classify
from .session.reference_box import ReferenceBox, build_reference_box

MARKET_REGIME_SKILL_ID = "ASIAN_SWEEP_SESSION_REGIME_V1"
MARKET_REGIME_SKILL_VERSION = "1.0.0"


class ObservationValidationError(ValueError):
    """Fail-closed: raised by the consumer, never by the adapter itself, when an
    observation cannot be trusted for a given decision cycle."""


@dataclass(frozen=True)
class SessionRegimeSkill:
    """TradingSkill adapter over session.reference_box.build_reference_box +
    session.classifier.classify. Structurally satisfies trading_skills.TradingSkill."""

    skill_id: str = MARKET_REGIME_SKILL_ID
    version: str = MARKET_REGIME_SKILL_VERSION

    def evaluate(self, context: Mapping[str, Any]) -> MarketObservation:
        session_name: str = context["session_name"]
        session_candles: Sequence[Candle] = context["session_candles"]
        expected_bar_count: int = context["expected_bar_count"]
        symbol: str = context["symbol"]
        observed_at: datetime = context["observed_at"]

        box: ReferenceBox = build_reference_box(session_name, session_candles, expected_bar_count)
        regime: Regime = classify(box)
        fingerprint = fingerprint_input({
            "session_name": session_name,
            "expected_bar_count": expected_bar_count,
            "candle_times": [str(c.time) for c in session_candles],
            "candle_closes": [c.close for c in session_candles],
        })
        return MarketObservation(
            skill_id=self.skill_id,
            skill_version=self.version,
            symbol=symbol,
            timeframe="M15",
            observed_at=observed_at,
            classification=regime.value,
            input_fingerprint=fingerprint,
            evidence={
                "native_result": regime,
                "box_session_high": box.session_high,
                "box_session_low": box.session_low,
                "box_efficiency_ratio": box.efficiency_ratio,
                "box_session_complete": box.session_complete,
                "box_bar_count": box.bar_count,
            },
        )


def unwrap_regime_observation(
    observation: Optional[MarketObservation], *, symbol: str, observed_at: datetime,
) -> Optional[Regime]:
    """Fail-closed unwrap, structurally identical to session_sweep_continuation.
    canonical_observations.unwrap_regime_observation. Returns None (never raises) for
    a missing observation -- route_completed_session already treats
    regime_override=None as "compute it internally via classify()". Raises
    ObservationValidationError for a PRESENT but untrustworthy observation."""
    if observation is None:
        return None
    if observation.skill_id != MARKET_REGIME_SKILL_ID or observation.skill_version != MARKET_REGIME_SKILL_VERSION:
        raise ObservationValidationError(
            f"UNSUPPORTED_SKILL_VERSION: expected {MARKET_REGIME_SKILL_ID}@{MARKET_REGIME_SKILL_VERSION}, "
            f"got {observation.skill_id}@{observation.skill_version}"
        )
    if observation.symbol != symbol:
        raise ObservationValidationError(f"WRONG_SYMBOL: expected {symbol!r}, got {observation.symbol!r}")
    if observation.timeframe != "M15":
        raise ObservationValidationError(f"WRONG_TIMEFRAME: expected 'M15', got {observation.timeframe!r}")
    if observation.observed_at != observed_at:
        raise ObservationValidationError(
            f"STALE_OBSERVATION: observed_at {observation.observed_at} != expected {observed_at}"
        )
    if observation.classification not in {r.value for r in Regime}:
        raise ObservationValidationError(f"INVALID_CLASSIFICATION: {observation.classification!r}")
    native = observation.evidence.get("native_result")
    if not isinstance(native, Regime):
        raise ObservationValidationError("INVALID_SCHEMA: evidence['native_result'] is not a Regime")
    if native.value != observation.classification:
        raise ObservationValidationError("INVALID_EVIDENCE: native_result disagrees with classification")
    return native
