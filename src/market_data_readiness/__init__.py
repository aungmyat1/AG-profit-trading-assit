"""AG_ST_SESSION_SWEEP_CONTINUATION_DATA_READINESS -- read-only D:\\ FX historical-CSV
discovery / fingerprinting / quality / timezone / readiness scanner.

Scope: DATA DISCOVERY / VALIDATION / FINGERPRINTING / REPLAY-READINESS work only. This
package never opens a source file in write mode, never modifies strategy parameters,
MarketBias rules, S1/S2/S3 semantics, risk, or lifecycle, and never submits orders. It
is additive and isolated from src/session_sweep_continuation/ (the strategy engine) and
src/session_tribranch_research/ (the existing single-dataset loader) -- it studies and
reuses their conventions (verify_dataset_fingerprint-style hashing, mt5.broker_time's
weekend-reopen-gap UTC offset detection) rather than replacing them.
"""
from __future__ import annotations

STRATEGY_ID_UNDER_EVALUATION = "ST_SESSION_SWEEP_CONTINUATION_V1"
STRATEGY_VERSION_UNDER_EVALUATION = "1.0.0"
