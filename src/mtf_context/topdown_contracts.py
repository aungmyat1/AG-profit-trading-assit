"""Top-down market-context data contracts (TD-1, TD0_TOPDOWN_CONTEXT_AUDIT).

TD-1 SCOPE ONLY -- freezes the shared timeframe registry and the frozen dataclasses
(TimeframeRequirement, StructureFact, WeeklyContext..M5Context, TopDownContext). No
market data is fetched, no indicator/structure/liquidity calculation happens here, and
no cache/scheduler exists yet -- every field is populated by a caller who already
computed it elsewhere. Same NON-GOALS discipline as strategy_contract/market_snapshot.py
and mtf_context/models.py: this module is an additive, read-only VIEW/CONTRACT layer.

EXTENDS the existing src/mtf_context package (TD-0's audit found this WRAPPER_ONLY /
ADVISORY_ONLY package is the correct foundation) rather than a parallel package.
Inherits mtf_context's authority contract verbatim -- AUTHORITY is imported from
.models, not redefined. tests/test_mtf_context_execution_guard.py already AST-scans
this entire package (PACKAGE_ROOT = src/mtf_context) for forbidden imports/calls/
terminal-state literals, so this module is automatically covered by that guard.

CRITICAL STRUCTURE-SEMANTIC RULE (TD-0 finding: at least 6 incompatible BOS/MSS/CHOCH
definitions exist across the repo -- market_structure/smc_adapter.py + tiers.py,
strategy_engine/sweep_retest/trend.py, session_sweep_continuation/swing_structure.py,
strategy_engine/sweep_retest/mss.py, entry_confirmation/structure_alignment.py). This
module does NOT unify them and never will by silent default. Every StructureFact MUST
carry an explicit structure_definition_id drawn from ALLOWED_STRUCTURE_DEFINITION_IDS
below -- there is no unqualified/global bos/choch/mss/structure field anywhere in this
contract. TD-1 seeds exactly one allowed definition, SMC_MARKET_STRUCTURE_V1, matching
the market_structure/tiers.py + market_structure/smc_adapter.py semantics named in
strategies/ST_LARGE_SMC_V1.yaml. SSC's own hand-rolled BOS
(session_sweep_continuation/swing_structure.py) and Sweep-Retest's MSS
(strategy_engine/sweep_retest/mss.py) remain strategy-owned and are deliberately not
represented here.
"""
from __future__ import annotations

import dataclasses
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from .models import AUTHORITY

# ---------------------------------------------------------------------------
# Canonical timeframe registry (additive -- TD-0 found 4+ independent, mutually
# inconsistent timeframe dicts already in the repo: mt5/market_data.py,
# historical_replay/candle_store.py, strategy_contract/market_snapshot.py,
# smc_map/models.py -- none of which include W1. This is a NEW, independent source of
# truth; per the TD-1 mission, none of those existing dicts are rewritten here. Later
# work packages may adopt this registry incrementally.)
# ---------------------------------------------------------------------------

TIMEFRAME_W1 = "W1"
TIMEFRAME_D1 = "D1"
TIMEFRAME_H4 = "H4"
TIMEFRAME_H1 = "H1"
TIMEFRAME_M15 = "M15"
TIMEFRAME_M5 = "M5"
TIMEFRAME_M1 = "M1"  # execution-oriented consumers only -- NOT part of TopDownContext V1

# Top-down hierarchy order, highest timeframe first. TopDownContext V1 covers exactly
# this tuple; M1 is registered above for other, execution-oriented consumers only.
TOPDOWN_TIMEFRAMES: Tuple[str, ...] = (
    TIMEFRAME_W1, TIMEFRAME_D1, TIMEFRAME_H4, TIMEFRAME_H1, TIMEFRAME_M15, TIMEFRAME_M5,
)
ALL_CANONICAL_TIMEFRAMES: Tuple[str, ...] = TOPDOWN_TIMEFRAMES + (TIMEFRAME_M1,)


class InvalidTimeframeError(ValueError):
    """Raised for a timeframe outside ALL_CANONICAL_TIMEFRAMES, or a tier context
    constructed with a timeframe other than the one its class name implies -- never
    for a market-data problem (see DATA_QUALITY_* below for that)."""


def _require_canonical_timeframe(timeframe: str) -> None:
    if timeframe not in ALL_CANONICAL_TIMEFRAMES:
        raise InvalidTimeframeError(f"{timeframe!r} not in canonical registry {ALL_CANONICAL_TIMEFRAMES}")


def _require_fixed_timeframe(timeframe: str, expected: str) -> None:
    if timeframe != expected:
        raise InvalidTimeframeError(f"expected timeframe {expected!r}, got {timeframe!r}")


def _require_nonempty(name: str, value: str) -> None:
    if not value:
        raise ValueError(f"{name} is required and cannot be empty")


# ---------------------------------------------------------------------------
# Data-quality status -- deliberately reuses mtf_context/models.py's own vocabulary
# (STATUS_VALID/STATUS_PARTIAL/STATUS_MISSING/STATUS_DATA_ERROR) rather than inventing
# a second status enum for the same concept.
# ---------------------------------------------------------------------------

DATA_QUALITY_VALID = "VALID"
DATA_QUALITY_PARTIAL = "PARTIAL"
DATA_QUALITY_MISSING = "MISSING"
DATA_QUALITY_DATA_ERROR = "DATA_ERROR"
VALID_DATA_QUALITY_STATUSES = frozenset(
    {DATA_QUALITY_VALID, DATA_QUALITY_PARTIAL, DATA_QUALITY_MISSING, DATA_QUALITY_DATA_ERROR}
)


class InvalidDataQualityStatusError(ValueError):
    pass


def _require_valid_data_quality(status: str) -> None:
    if status not in VALID_DATA_QUALITY_STATUSES:
        raise InvalidDataQualityStatusError(
            f"data_quality_status must be one of {sorted(VALID_DATA_QUALITY_STATUSES)}, got {status!r}"
        )


# ---------------------------------------------------------------------------
# Structure semantics -- see module docstring's CRITICAL STRUCTURE-SEMANTIC RULE.
# ---------------------------------------------------------------------------

STRUCTURE_DEFINITION_SMC_MARKET_STRUCTURE_V1 = "SMC_MARKET_STRUCTURE_V1"
ALLOWED_STRUCTURE_DEFINITION_IDS = frozenset({STRUCTURE_DEFINITION_SMC_MARKET_STRUCTURE_V1})


class InvalidStructureDefinitionError(ValueError):
    """Raised when a StructureFact's structure_definition_id is missing or not in
    ALLOWED_STRUCTURE_DEFINITION_IDS. Enforces the critical structure-semantic rule --
    never silently defaults to an unqualified structure label."""


@dataclass(frozen=True)
class StructureFact:
    """One versioned structural observation -- e.g. a BOS/CHOCH event as defined by
    market_structure/smc_adapter.py + tiers.py ONLY (structure_definition_id pins this
    unambiguously). event_type/direction/level are opaque strings/floats here on
    purpose: this contract does not interpret them, it only carries them with
    mandatory provenance so a caller can trace exactly which already-authoritative
    detector produced them. TD-1 defines the shape only; no detector calls this yet.
    """

    structure_definition_id: str
    timeframe: str
    event_type: str
    direction: str
    level: float
    confirmation_bar_time: datetime
    source: str
    feature_version: str

    def __post_init__(self) -> None:
        if not self.structure_definition_id:
            raise InvalidStructureDefinitionError("structure_definition_id is required and cannot be empty")
        if self.structure_definition_id not in ALLOWED_STRUCTURE_DEFINITION_IDS:
            raise InvalidStructureDefinitionError(
                f"structure_definition_id {self.structure_definition_id!r} not in "
                f"{sorted(ALLOWED_STRUCTURE_DEFINITION_IDS)} -- TD-1 does not unify "
                "BOS/MSS/CHOCH definitions; see module docstring"
            )
        _require_canonical_timeframe(self.timeframe)
        _require_nonempty("event_type", self.event_type)
        _require_nonempty("direction", self.direction)
        _require_nonempty("source", self.source)
        _require_nonempty("feature_version", self.feature_version)


@dataclass(frozen=True)
class TimeframeRequirement:
    """A consumer's declared need for one canonical timeframe tier. Contract-only --
    no builder in TD-1 reads or enforces this yet; it exists so a future orchestrator
    (TD-6+) has a stable, typed way to express "I need H1, and it's required, not
    optional" without re-deriving timeframe validation."""

    timeframe: str
    required: bool = True
    min_warmup_bars: Optional[int] = None

    def __post_init__(self) -> None:
        _require_canonical_timeframe(self.timeframe)
        if self.min_warmup_bars is not None and self.min_warmup_bars < 0:
            raise ValueError("min_warmup_bars cannot be negative")


# ---------------------------------------------------------------------------
# Deterministic context identity -- same blake2b, no-transient-input convention as
# proposals/identity.py::setup_id and proposals/occurrence_identity.py (no new hashing
# infrastructure invented here).
# ---------------------------------------------------------------------------

def compute_context_id(
    *, symbol: str, timeframe: str, source: str, bar_close_time: datetime,
    feature_version: str, parent_context_id: Optional[str] = None,
) -> str:
    """Deterministic identity: same (symbol, timeframe, source, bar_close_time,
    feature_version, parent_context_id) always yields the same context_id -- no wall-
    clock, no random, no retrieval-order input. Two callers building the same tier
    context from the same closed bar independently produce the same id."""
    _require_canonical_timeframe(timeframe)
    payload = "|".join([
        symbol, timeframe, source,
        bar_close_time.astimezone(timezone.utc).isoformat(),
        feature_version, parent_context_id or "",
    ])
    digest = hashlib.blake2b(payload.encode("utf-8"), digest_size=12).hexdigest()
    return f"TDCTX-{timeframe}-{digest}"


def _to_dict(obj: Any) -> Dict[str, Any]:
    """Generic, deterministic dict rendering shared by every contract in this module --
    datetimes become ISO-8601 strings, nested dataclasses/tuples recurse. Matches the
    rendering style already used by mtf_context.models.MTFContext.to_dict()."""
    result: Dict[str, Any] = {}
    for f in dataclasses.fields(obj):
        value = getattr(obj, f.name)
        result[f.name] = _render_value(value)
    return result


def _render_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if dataclasses.is_dataclass(value):
        return _to_dict(value)
    if isinstance(value, (tuple, list)):
        return [_render_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _render_value(item) for key, item in value.items()}
    return value


def _require_consistent_lineage(
    child_parent_context_id: Optional[str], parent_ctx: Optional[Any], label: str,
) -> None:
    """Validates presence only, never calculation: if BOTH a declared parent id and an
    actual parent context object are supplied, they must agree. A parent tier that has
    not been computed yet (parent_ctx is None) or a child that declares no parent yet
    (child_parent_context_id is None) is valid -- TD-1 defines no builder, so partial
    lineage is the expected common case, not an error."""
    if child_parent_context_id is not None and parent_ctx is not None:
        if child_parent_context_id != parent_ctx.context_id:
            raise ValueError(
                f"{label}: parent_context_id {child_parent_context_id!r} does not match "
                f"supplied parent context_id {parent_ctx.context_id!r}"
            )


# ---------------------------------------------------------------------------
# Per-tier context contracts. Each carries the mandatory provenance set: symbol,
# timeframe, source, closed-bar timestamp, snapshot identity (where available),
# context identity, parent-context identity (where applicable), feature-version
# identity, and data-quality status. Each is a frozen, deterministic, serializable
# dataclass -- no I/O, no calculation.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WeeklyContext:
    context_id: str
    symbol: str
    timeframe: str
    source: str
    bar_close_time: datetime
    feature_version: str
    data_quality_status: str
    snapshot_fingerprint: Optional[str] = None
    structure_facts: Tuple[StructureFact, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _require_nonempty("context_id", self.context_id)
        _require_nonempty("symbol", self.symbol)
        _require_fixed_timeframe(self.timeframe, TIMEFRAME_W1)
        _require_nonempty("source", self.source)
        _require_nonempty("feature_version", self.feature_version)
        _require_valid_data_quality(self.data_quality_status)
        for fact in self.structure_facts:
            _require_fixed_timeframe(fact.timeframe, TIMEFRAME_W1)

    def to_dict(self) -> Dict[str, Any]:
        return _to_dict(self)


@dataclass(frozen=True)
class DailyContext:
    context_id: str
    symbol: str
    timeframe: str
    source: str
    bar_close_time: datetime
    feature_version: str
    data_quality_status: str
    snapshot_fingerprint: Optional[str] = None
    parent_weekly_context_id: Optional[str] = None
    structure_facts: Tuple[StructureFact, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _require_nonempty("context_id", self.context_id)
        _require_nonempty("symbol", self.symbol)
        _require_fixed_timeframe(self.timeframe, TIMEFRAME_D1)
        _require_nonempty("source", self.source)
        _require_nonempty("feature_version", self.feature_version)
        _require_valid_data_quality(self.data_quality_status)
        for fact in self.structure_facts:
            _require_fixed_timeframe(fact.timeframe, TIMEFRAME_D1)

    def to_dict(self) -> Dict[str, Any]:
        return _to_dict(self)


@dataclass(frozen=True)
class H4Context:
    context_id: str
    symbol: str
    timeframe: str
    source: str
    bar_close_time: datetime
    feature_version: str
    data_quality_status: str
    snapshot_fingerprint: Optional[str] = None
    parent_daily_context_id: Optional[str] = None
    structure_facts: Tuple[StructureFact, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _require_nonempty("context_id", self.context_id)
        _require_nonempty("symbol", self.symbol)
        _require_fixed_timeframe(self.timeframe, TIMEFRAME_H4)
        _require_nonempty("source", self.source)
        _require_nonempty("feature_version", self.feature_version)
        _require_valid_data_quality(self.data_quality_status)
        for fact in self.structure_facts:
            _require_fixed_timeframe(fact.timeframe, TIMEFRAME_H4)

    def to_dict(self) -> Dict[str, Any]:
        return _to_dict(self)


@dataclass(frozen=True)
class H1Context:
    context_id: str
    symbol: str
    timeframe: str
    source: str
    bar_close_time: datetime
    feature_version: str
    data_quality_status: str
    snapshot_fingerprint: Optional[str] = None
    parent_h4_context_id: Optional[str] = None
    structure_facts: Tuple[StructureFact, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _require_nonempty("context_id", self.context_id)
        _require_nonempty("symbol", self.symbol)
        _require_fixed_timeframe(self.timeframe, TIMEFRAME_H1)
        _require_nonempty("source", self.source)
        _require_nonempty("feature_version", self.feature_version)
        _require_valid_data_quality(self.data_quality_status)
        for fact in self.structure_facts:
            _require_fixed_timeframe(fact.timeframe, TIMEFRAME_H1)

    def to_dict(self) -> Dict[str, Any]:
        return _to_dict(self)


@dataclass(frozen=True)
class M15Context:
    context_id: str
    symbol: str
    timeframe: str
    source: str
    bar_close_time: datetime
    feature_version: str
    data_quality_status: str
    snapshot_fingerprint: Optional[str] = None
    parent_h1_context_id: Optional[str] = None
    structure_facts: Tuple[StructureFact, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _require_nonempty("context_id", self.context_id)
        _require_nonempty("symbol", self.symbol)
        _require_fixed_timeframe(self.timeframe, TIMEFRAME_M15)
        _require_nonempty("source", self.source)
        _require_nonempty("feature_version", self.feature_version)
        _require_valid_data_quality(self.data_quality_status)
        for fact in self.structure_facts:
            _require_fixed_timeframe(fact.timeframe, TIMEFRAME_M15)

    def to_dict(self) -> Dict[str, Any]:
        return _to_dict(self)


@dataclass(frozen=True)
class M5Context:
    context_id: str
    symbol: str
    timeframe: str
    source: str
    bar_close_time: datetime
    feature_version: str
    data_quality_status: str
    snapshot_fingerprint: Optional[str] = None
    parent_m15_context_id: Optional[str] = None
    structure_facts: Tuple[StructureFact, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _require_nonempty("context_id", self.context_id)
        _require_nonempty("symbol", self.symbol)
        _require_fixed_timeframe(self.timeframe, TIMEFRAME_M5)
        _require_nonempty("source", self.source)
        _require_nonempty("feature_version", self.feature_version)
        _require_valid_data_quality(self.data_quality_status)
        for fact in self.structure_facts:
            _require_fixed_timeframe(fact.timeframe, TIMEFRAME_M5)

    def to_dict(self) -> Dict[str, Any]:
        return _to_dict(self)


# ---------------------------------------------------------------------------
# TopDownContext -- composes/references the six tier contexts. Calculates nothing;
# TD-1 defines no builder, so every tier field is Optional and populated only by a
# caller who already computed it elsewhere (future TD-2..TD-7 work).
# ---------------------------------------------------------------------------

_FIXED_AUTHORIZATION: Dict[str, bool] = {
    "may_create_trade": False,
    "may_reject_trade": False,
    "may_change_strategy_decision": False,
    "may_modify_risk": False,
    "may_execute": False,
}


@dataclass(frozen=True)
class TopDownContext:
    """Composes/references WeeklyContext..M5Context for one symbol at one evaluation
    instant. NON-AUTHORITATIVE BY CONSTRUCTION: authority is fixed to
    mtf_context.models.AUTHORITY ("ADVISORY_ONLY") and authorization is a fixed,
    all-False dict identical in shape to mtf_context.models.MTFContext's own default --
    there is no field anywhere on this dataclass that can express BUY/SELL,
    READY_FOR_TRADE, a position size, or an execution/demo/live authorization change.
    Both are validated in __post_init__ so no caller can construct a divergent value.
    """

    context_id: str
    symbol: str
    evaluation_time: datetime
    data_quality_status: str
    authority: str = AUTHORITY
    weekly: Optional[WeeklyContext] = None
    daily: Optional[DailyContext] = None
    h4: Optional[H4Context] = None
    h1: Optional[H1Context] = None
    m15: Optional[M15Context] = None
    m5: Optional[M5Context] = None
    authorization: Dict[str, bool] = field(default_factory=lambda: dict(_FIXED_AUTHORIZATION))

    def __post_init__(self) -> None:
        _require_nonempty("context_id", self.context_id)
        _require_nonempty("symbol", self.symbol)
        _require_valid_data_quality(self.data_quality_status)
        if self.authority != AUTHORITY:
            raise ValueError(f"TopDownContext.authority must be {AUTHORITY!r}, got {self.authority!r}")
        if dict(self.authorization) != _FIXED_AUTHORIZATION:
            raise ValueError(
                "TopDownContext.authorization is fixed and must never be overridden -- "
                f"expected {_FIXED_AUTHORIZATION}, got {dict(self.authorization)}"
            )
        if self.daily is not None:
            _require_consistent_lineage(self.daily.parent_weekly_context_id, self.weekly, "daily")
        if self.h4 is not None:
            _require_consistent_lineage(self.h4.parent_daily_context_id, self.daily, "h4")
        if self.h1 is not None:
            _require_consistent_lineage(self.h1.parent_h4_context_id, self.h4, "h1")
        if self.m15 is not None:
            _require_consistent_lineage(self.m15.parent_h1_context_id, self.h1, "m15")
        if self.m5 is not None:
            _require_consistent_lineage(self.m5.parent_m15_context_id, self.m15, "m5")

    def to_dict(self) -> Dict[str, Any]:
        return _to_dict(self)
