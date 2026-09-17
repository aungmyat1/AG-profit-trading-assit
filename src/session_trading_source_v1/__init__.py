"""ST_SESSION_TRADING_SOURCE_V1 -- isolated RESEARCH_CANDIDATE lineage.

Parent evidence: artifacts/validation/EXTERNAL_SOURCE_ES_S1S/
  (EXTERNAL_SOURCE_ES_S1S, EXTERNAL_SOURCE_ES_S1R,
   ST_SESSION_TRADING_SOURCE_V1_CANDIDATE_SPEC.md).

This package does NOT modify, import behavior from, or share stop/target/partial
geometry with `ST_ASIAN_SWEEP_5R_V1` (strategies/ST_ASIAN_SWEEP_5R_V1.yaml,
src/strategy_engine/session/setups.py::entry_2_sweep) or
`ST_SESSION_SWEEP_CONTINUATION_V1` (src/session_sweep_continuation/). The only
cross-import is `strategy_engine.session.candles.Candle`, a generic immutable
OHLC dataclass with no strategy-specific behavior -- see SEMANTIC_REUSE_MANIFEST
in the evidence package for the full accounting of what was and was not reused.

No Demo/Live execution authority exists anywhere in this package.
"""
from __future__ import annotations

STRATEGY_ID = "ST_SESSION_TRADING_SOURCE_V1"
VERSION = "0.1.0"
COMPONENT = "SWEEP"
CLASSIFICATION = "RESEARCH_CANDIDATE"

NATIVE_TIMEFRAME = "M15"
H1_REQUIRED = False
M1_REQUIRED = False

SOURCE_SWEEP_DETERMINISTIC_SPEC_READY = True
SOURCE_SWEEP_FULL_SOURCE_PARITY_READY = False  # several source rules remain unresolved -- see uncertainty.py

DEMO_AUTHORIZED = False
LIVE_AUTHORIZED = False

RANGE_COMPONENT = "SPEC_UNRESOLVED"
TREND_COMPONENT = "SPEC_UNRESOLVED"
