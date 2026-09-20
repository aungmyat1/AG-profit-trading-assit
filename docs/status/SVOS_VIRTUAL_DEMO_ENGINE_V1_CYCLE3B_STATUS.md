# SVOS Virtual Demo Engine V1 — Cycle 3B isolated exchange core

Date: 2026-09-20. Classification: **VD_EXCHANGE_CORE_READY** for deterministic engineering fixtures only.

## Freeze and scope

Cycle 3A evidence was frozen first in commit `3fa107aec51db9d3871a5785c564429adf827623` (from temporal foundation `04a8d122682e0888d3260b103303576c887d83ee`). Only its five mission-owned files were staged; no unrelated WIP was present. Cycle 3B HEAD before implementation was that commit. HEAD after implementation is recorded by the final commit. No MI, TD-8E, SSC, execution, broker, or account code changed.

## Core behavior

`ResearchReferenceEntry` represents SSC/research signal-close semantics and is retained as metadata. `ProposalFixture` binds the decision cutoff, dataset, decision event, and reference entry. `VirtualOrder` transitions through `CREATED → PENDING → ELIGIBLE → FILLED`, or `REJECTED`, `EXPIRED`, and `CANCELLED` states as applicable. Every `ExchangeRecord` carries virtual time, dataset/event lineage, decision/proposal/order IDs, state/reason, and deterministic content identity.

For `OHLC_M1`, the first eligible bar must have `bar.time > decision_cutoff`; bars at or before the cutoff are ignored. The engineering fill uses that bar's open and records `OHLC_M1_ENGINEERING_OPEN`. It never retroactively uses the SSC reference price, although that price remains in the fill record for later parity analysis. This is a fixture convention, not a broker quote, spread, slippage, or latency claim.

After a fill, only later M1 bars are examined. Stop-only, target-only, and both-level cases produce `ADVERSE`, `FAVORABLE`, and `AMBIGUOUS_SEQUENCE` observations. The ambiguous case makes no intrabar ordering assumption and preserves the SSC resolver's `AMBIGUOUS_SEQUENCE_NO_ASSUMED_INTRABAR_ORDER` principle. No account, cash, R, or profitability result is produced.

## Proofs and failures

Focused tests prove reference/fill separation, pre-cutoff exclusion, all three exit observations, repeated determinism and input-order independence across `step`, `accelerated`, and `maximum` modes, unsupported quality rejection, missing evidence rejection, symbol/dataset mismatch rejection, invalid OHLC rejection, and deterministic expiry. There is no MT5 import or fallback path; the existing static MT5-isolation tests also pass.

## Verification

- `python -m pytest -q tests/test_svos_virtual_exchange_cycle3b.py` → **8 passed** before the combined run; the final parametrized suite is included below.
- `python -m pytest -q tests/test_svos_virtual_exchange_cycle3b.py tests/test_svos_virtual_time_cycle2.py tests/test_svos_mt5_isolation.py tests/test_svos_context_authority.py tests/test_svos_ssc_adapter.py tests/test_td8e_evaluation_context.py tests/test_td8e_ssc_reference_completeness.py tests/test_td8e_shared_consumer_integration.py tests/test_market_intelligence_v1_core.py tests/test_market_intelligence_v1_cycle3_parity.py tests/test_market_intelligence_v1_cycle4_ssc.py` → **67 passed**.

## Remaining blockers and safety

Canonical SSC integration remains intentionally absent. The core does not model spread, commission, slippage, calibrated latency, bid/ask, account balance/equity, margin, sizing, currency conversion, or economics. `OHLC_M1` is the only accepted quality. No protected, holdout, OOS, sealed campaign, Demo/Live order, optimization, or execution-authority change occurred.
