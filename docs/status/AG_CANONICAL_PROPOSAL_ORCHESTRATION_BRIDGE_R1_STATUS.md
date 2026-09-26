# Canonical Proposal Orchestration Bridge R1 Status

**Classification:** `UNIT_TESTED`
**Evidence date:** 2026-09-27
**Frozen Foundation:** `ef84d2fe296c3b3582bc26921b59e97cf1a1a086`
**Branch:** `feature/real-mt5-canonical-proposal`

## Implemented boundary

`src/post_asian_pilot/orchestration_bridge.py` adds a production composition that accepts
the canonical immutable `MarketState`, existing immutable `strategy_engine.session.Candle`
objects, and their matching `MarketSnapshot`. It checks symbol, source, closed-bar, and
time lineage and requires REAL mode. It evaluates `ST_ASIAN_SWEEP_5R_V1` v1.1.1, uses the
existing Asian Sweep Opportunity adapter and actual ProposalEligibility evaluator, then
calls the existing FX proposal/risk builder only for a matching typed ELIGIBLE decision.
The 0.5% risk policy comes from
`config/pilot/AG_POST_ASIAN_LONDON_PILOT_V1_0_1.yaml`. Canonical proposal formation uses
the existing opportunity adapter and REAL-only formation gate. Successful production
proposals are persisted through the existing ProposalLedger for the read-only
`/api/canonical-proposals` and Owner Analysis consumer.

No strategy, MarketState schema, eligibility rule, strategy authorization, execution
authority, or broker gate changed. No Crypto path was added.

## Offline evidence and limits

Command:

```powershell
$env:PYTHONPATH='src'
python -m pytest -q tests/test_post_asian_orchestration_bridge.py tests/test_opportunity_proposal_eligibility.py tests/test_opportunity_proposal_bridge.py tests/test_opportunity_import_boundaries.py tests/test_proposal_envelope_execution_boundary.py tests/test_proposal_envelope_adapters.py tests/test_proposal_ledger.py tests/test_post_asian_pilot.py
```

Result: **197 passed** on Windows / Python 3.14. All locally generated candles and
snapshots are labeled SYNTHETIC; replay firewall inputs are labeled REPLAY. A typed
accepted eligibility decision is constructed only in the test file to prove the
post-eligibility seam. The REAL-only formation gate blocks offline proposals, and the
ledger rejects the blocked envelope. Owner Analysis response shape is checked in memory;
offline fixture proposals are not persisted. These tests do not establish production REAL
eligibility acceptance, REAL risk sizing, persistence, or API readback.

`REAL_MT5_END_TO_END_PROOF = NOT_CLAIMED`. No MT5 connection or broker calls were made:
`order_check=0`, `order_send=0`, demo orders=0, live orders=0. Fresh REAL closed-bar input
after market open remains necessary to exercise the complete production and readback path.

## Changed paths

- `src/post_asian_pilot/orchestration_bridge.py`
- `tests/test_post_asian_orchestration_bridge.py`
- `PROJECT_STATUS.md`
- `docs/README.md`
- `docs/status/AG_CANONICAL_PROPOSAL_ORCHESTRATION_BRIDGE_R1_STATUS.md`
