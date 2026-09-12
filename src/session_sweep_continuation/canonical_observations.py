"""Thin TradingSkill adapters wrapping ST_SESSION_SWEEP_CONTINUATION_V1's existing
deterministic market-fact components (h1_bias.resolve_h1_market_bias, regime.
classify_regime) into the canonical `trading_skills.MarketObservation` shape
(AG_PLAN2_GOLDEN_STRATEGY_CANONICAL_OBSERVATION_MIGRATION_V1).

Representation transformation only -- see module docstrings of h1_bias.py and
regime.py for the actual classification logic, which is called here VERBATIM and
never reimplemented, re-thresholded, or re-timed. Each adapter's `evidence` dict
carries the native result object under "native_result" so a consumer can recover it
exactly (no lossy re-serialization round trip) -- the MarketObservation wrapper adds
identity/authority-separation metadata around an unchanged native value, it does not
replace the value.

Only two observation types are implemented, matching the golden strategy's own two
externally-classifiable market facts:

- MARKET_BIAS: already an external input to session_sweep_continuation.replay.
  run_replay (its `bias_result` parameter) -- wrapping it here and unwrapping via
  `unwrap_bias_observation` before that same call is a fully transparent round trip;
  the shadow canonical path and the legacy path invoke the identical function with the
  identical bias_result object, so they cannot semantically diverge on bias by
  construction.
- MARKET_REGIME: AG_PLAN2_GOLDEN_CANONICAL_COMPLETION_V1 -- run_replay now accepts an
  optional `regime_result` override (mirroring `bias_result` exactly); wrapping it here
  and unwrapping via `unwrap_regime_observation` before that same call is a fully
  transparent round trip, identical in shape to the bias round trip.

SESSION_CONTEXT (reference-session high/low/range) was evaluated and deliberately NOT
implemented as a separate observation type this slice: sessions.build_reference_session
produces raw aggregation values consumed directly as float parameters by regime/setup
code, not a market-fact classification/enum a fail-closed guard would gate on the way
bias/regime are -- adding a wrapper would be representation overhead with no additional
authority-separation benefit. Deferred, not silently dropped.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Optional

from market_intelligence.models import MarketBiasResult

from trading_skills import MarketObservation, fingerprint_input

from .regime import Regime, RegimeResult, classify_regime
from .h1_bias import (
    HistoricalCandleStore,
    HistoricalSymbolMetadataManifest,
    resolve_h1_market_bias,
)

MARKET_BIAS_SKILL_ID = "H1_MARKET_BIAS_V1"
MARKET_BIAS_SKILL_VERSION = "1.0.0"
MARKET_REGIME_SKILL_ID = "M15_MARKET_REGIME_V1"
MARKET_REGIME_SKILL_VERSION = "1.0.0"

REQUIRED_OBSERVATION_TYPES = ("MARKET_BIAS", "MARKET_REGIME")


class ObservationValidationError(ValueError):
    """Fail-closed: raised by the consumer, never by the adapter itself, when an
    observation cannot be trusted for a given decision cycle (wrong symbol/timeframe,
    stale, unsupported skill version, or missing evidence)."""


@dataclass(frozen=True)
class H1MarketBiasSkill:
    """TradingSkill adapter over h1_bias.resolve_h1_market_bias. Structurally satisfies
    trading_skills.TradingSkill (skill_id, version, evaluate(context) -> MarketObservation)."""

    skill_id: str = MARKET_BIAS_SKILL_ID
    version: str = MARKET_BIAS_SKILL_VERSION

    def evaluate(self, context: Mapping[str, Any]) -> MarketObservation:
        h1_store: HistoricalCandleStore = context["h1_store"]
        manifest: HistoricalSymbolMetadataManifest = context["manifest"]
        symbol: str = context["symbol"]
        decision_time: datetime = context["decision_time"]
        session_pair: str = context["session_pair"]

        bias_result: MarketBiasResult = resolve_h1_market_bias(
            h1_store, manifest, symbol, decision_time, session_pair,
        )
        return MarketObservation(
            skill_id=self.skill_id,
            skill_version=self.version,
            symbol=symbol,
            timeframe="H1",
            observed_at=decision_time,
            classification=bias_result.bias,
            # Reused verbatim from the native resolver -- P5 forbids a second hashing
            # system; MarketBiasResult already computes its own input_fingerprint.
            input_fingerprint=bias_result.input_fingerprint,
            evidence={
                "native_result": bias_result,
                "confidence": bias_result.confidence,
                "decision_cycle_id": bias_result.decision_cycle_id,
                "model_version": bias_result.model_version,
                "reason_codes": bias_result.reason_codes,
            },
        )


@dataclass(frozen=True)
class M15RegimeSkill:
    """TradingSkill adapter over regime.classify_regime. Observation-only: this
    adapter's output is not (yet) fed back into run_replay -- see module docstring."""

    skill_id: str = MARKET_REGIME_SKILL_ID
    version: str = MARKET_REGIME_SKILL_VERSION

    def evaluate(self, context: Mapping[str, Any]) -> MarketObservation:
        reference_closes = context["reference_closes"]
        range_pips = context["range_pips"]
        candle_count = context["candle_count"]
        config: dict = context["config"]
        symbol: str = context["symbol"]
        observed_at: datetime = context["observed_at"]

        regime_result: RegimeResult = classify_regime(reference_closes, range_pips, candle_count, config)
        fingerprint = fingerprint_input({
            "reference_closes": list(reference_closes),
            "range_pips": range_pips,
            "candle_count": candle_count,
            "regime_config": config.get("regime", {}),
        })
        return MarketObservation(
            skill_id=self.skill_id,
            skill_version=self.version,
            symbol=symbol,
            timeframe="M15",
            observed_at=observed_at,
            classification=regime_result.regime.value,
            input_fingerprint=fingerprint,
            evidence={
                "native_result": regime_result,
                "ema_fast": regime_result.ema_fast,
                "ema_slow": regime_result.ema_slow,
                "range_pips": regime_result.range_pips,
                "reason": regime_result.reason,
            },
        )


def unwrap_bias_observation(
    observation: Optional[MarketObservation], *, symbol: str, decision_time: datetime,
) -> Optional[MarketBiasResult]:
    """Fail-closed unwrap: returns the native MarketBiasResult only when the
    observation genuinely matches this decision cycle's symbol/timeframe/instant and
    carries the expected skill identity and evidence shape. Returns None (never
    raises) for a missing observation -- run_replay already treats bias_result=None as
    UNAVAILABLE bias and rejects every candidate BIAS_MISSING (fail-closed, unchanged,
    reused here rather than re-implemented). Raises ObservationValidationError for a
    PRESENT but untrustworthy observation (wrong symbol/timeframe/skill/version/
    fingerprint-bearing-evidence-missing) -- that is a genuine integration bug, not a
    normal "no data yet" case, so it must not be silently downgraded to None."""
    if observation is None:
        return None
    if observation.skill_id != MARKET_BIAS_SKILL_ID or observation.skill_version != MARKET_BIAS_SKILL_VERSION:
        raise ObservationValidationError(
            f"UNSUPPORTED_SKILL_VERSION: expected {MARKET_BIAS_SKILL_ID}@{MARKET_BIAS_SKILL_VERSION}, "
            f"got {observation.skill_id}@{observation.skill_version}"
        )
    if observation.symbol != symbol:
        raise ObservationValidationError(f"WRONG_SYMBOL: expected {symbol!r}, got {observation.symbol!r}")
    if observation.timeframe != "H1":
        raise ObservationValidationError(f"WRONG_TIMEFRAME: expected 'H1', got {observation.timeframe!r}")
    if observation.observed_at != decision_time:
        raise ObservationValidationError(
            f"STALE_OBSERVATION: observed_at {observation.observed_at} != decision_time {decision_time}"
        )
    native = observation.evidence.get("native_result")
    if not isinstance(native, MarketBiasResult):
        raise ObservationValidationError("INVALID_SCHEMA: evidence['native_result'] is not a MarketBiasResult")
    if native.input_fingerprint != observation.input_fingerprint:
        raise ObservationValidationError("FINGERPRINT_MISMATCH: observation/native input_fingerprint disagree")
    return native


def unwrap_regime_observation(
    observation: Optional[MarketObservation], *, symbol: str, observed_at: datetime,
) -> Optional[RegimeResult]:
    """Fail-closed unwrap, mirroring unwrap_bias_observation exactly. Returns None
    (never raises) for a missing observation -- run_replay already treats
    regime_result=None as "compute it internally via classify_regime", its own
    pre-existing fail-closed-to-UNKNOWN behavior on insufficient data is unchanged and
    reused, never re-implemented. Raises ObservationValidationError for a PRESENT but
    untrustworthy observation (wrong symbol/timeframe/skill/version/stale/invalid
    classification/missing evidence/fingerprint mismatch) -- never silently substitutes
    a guessed or recomputed regime for an observation that failed validation."""
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
    if not isinstance(native, RegimeResult):
        raise ObservationValidationError("INVALID_SCHEMA: evidence['native_result'] is not a RegimeResult")
    if native.regime.value != observation.classification:
        raise ObservationValidationError("INVALID_EVIDENCE: native_result.regime disagrees with classification")
    # Fingerprint re-derivation would require re-supplying the original reference_closes
    # list, which this function intentionally does not accept (it would reintroduce the
    # same computation the adapter already performed -- a second hashing/recompute path
    # P5 forbids). Instead this checks the one thing that WOULD prove a swapped/forged
    # observation for a fixed evidence payload: that the observation's own recorded
    # ema_fast/ema_slow/range_pips/reason match the native RegimeResult's fields
    # byte-for-byte (both are frozen dataclasses populated from the same call, so any
    # divergence means the MarketObservation was tampered with after construction).
    if (
        observation.evidence.get("ema_fast") != native.ema_fast
        or observation.evidence.get("ema_slow") != native.ema_slow
        or observation.evidence.get("range_pips") != native.range_pips
        or observation.evidence.get("reason") != native.reason
    ):
        raise ObservationValidationError("FINGERPRINT_MISMATCH: observation evidence disagrees with native_result")
    return native
