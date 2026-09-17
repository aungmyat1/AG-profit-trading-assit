"""ST_SESSION_SWEEP_CONTINUATION_V1 -- version-isolated OFFLINE_RESEARCH engine.

This package is completely independent of ST_ASIAN_SWEEP_5R_V1's code paths
(strategy_engine/session/*). It shares only the neutral `Candle` value type
(strategy_engine.session.candles.Candle) and, for performance attribution, the
strategy-agnostic src/performance/ calculator -- both pre-existing, reusable,
strategy-neutral utilities, not ST_ASIAN_SWEEP_5R_V1-specific code.

Authority boundary (enforced, not just documented): nothing in this package places an
order, calls a broker, mutates strategy_lifecycle.yaml, or grants demo/live
authorization. `DEMO_ELIGIBLE = False` and `DEMO_AUTHORIZED = False` below are the
single in-code source of that fact for this engine; every other module imports them
rather than redeclaring.
"""
from __future__ import annotations

STRATEGY_ID = "ST_SESSION_SWEEP_CONTINUATION_V1"
STRATEGY_VERSION = "1.0.1"
LIFECYCLE_STAGE = "OFFLINE_RESEARCH"
DEMO_ELIGIBLE = False
DEMO_AUTHORIZED = False
