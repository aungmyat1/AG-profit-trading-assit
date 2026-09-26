# Canonical Proposal Orchestration Bridge R1.1 Status

**Classification:** `ORCHESTRATION_BRIDGE_R1_1_READY_FOR_INDEPENDENT_REAUDIT`  
**Evidence date:** 2026-09-27  
**Foundation:** `ef84d2fe296c3b3582bc26921b59e97cf1a1a086`  
**R1 parent:** `b0b33d894d0a2e61fd5365e5dbe32946ac633931`  
**Branch:** `fix/real-mt5-canonical-proposal-r1-1`

## Remediation

The public `evaluate_marketstate_to_proposal` entrypoint owns Strategy, Opportunity,
actual ProposalEligibility evaluation, Risk, canonical proposal formation, and ledger
persistence. Caller-supplied eligibility and market-data-mode overrides are absent.
Candidate symbol, mode, fingerprint, as-of time, strategy identity, and signal geometry
are validated before Risk; canonical provenance is checked against the candidate and
formation snapshot. The REAL-only formation gate remains mandatory. The entrypoint
persists successful READY output through the explicit default `ProposalLedger`; blocked
formation does not persist. The strategy risk remains sourced from
`config/pilot/AG_POST_ASIAN_LONDON_PILOT_V1_0_1.yaml` at configured 0.5%.

## Reproduced R1 findings

On the isolated R1 worktree, a caller-created typed `ELIGIBLE` decision matching a
SYNTHETIC candidate reached the public downstream helper and caused **one risk call**;
REAL-only formation then returned `BLOCKED` (`CANONICAL_FORMATION_REJECTED`). R1's helper
signature also does not accept `apply_real_formation_gate=True`, so the exact call shape
raises `TypeError`. Candidate/snapshot provenance binding was absent in that helper; the
R1.1 synthetic/replay-to-REAL mismatch probes now fail before Risk.

## R1.1 verification

Environment: Windows, Python 3.14. No broker connection, account probe, order check, or
order send was made. Test doubles at the market-truth boundary use synthetic candles and
are explicitly not REAL MT5 evidence.

| Purpose | Command | Result |
|---|---|---:|
| Adversarial bridge and formation/ledger coverage | `python -m pytest -q tests/test_post_asian_orchestration_bridge.py` | 19 passed |
| Previous R1 selection (same eight files) | `python -m pytest -q tests/test_post_asian_orchestration_bridge.py tests/test_opportunity_proposal_eligibility.py tests/test_opportunity_proposal_bridge.py tests/test_opportunity_import_boundaries.py tests/test_proposal_envelope_execution_boundary.py tests/test_proposal_envelope_adapters.py tests/test_proposal_ledger.py tests/test_post_asian_pilot.py` | 206 passed |
| Bounded relevant regression (bridge, Opportunity, envelope, risk) | `python -m pytest -q tests/test_post_asian_orchestration_bridge.py tests/test_proposal_formation_gate.py tests/test_proposal_ledger.py tests/test_opportunity_proposal_eligibility.py tests/test_opportunity_proposal_bridge.py tests/test_proposal_envelope_execution_boundary.py tests/test_proposal_envelope_adapters.py tests/test_opportunity_import_boundaries.py tests/test_execution_intent_builder.py tests/test_trade_management_risk.py` | 155 passed |

The accepted main production composition executed through the REAL-only formation gate
and persisted the READY test-boundary result using the default ledger. This is a
unit-tested dependency-boundary proof, not real-market validation. `REAL_MT5_END_TO_END_PROOF
= NOT_CLAIMED`. Broker safety counts: order check 0, order send 0, demo orders 0, live
orders 0.

## Scope

Changed paths are `src/post_asian_pilot/orchestration_bridge.py`,
`tests/test_post_asian_orchestration_bridge.py`, `PROJECT_STATUS.md`, `docs/README.md`,
and this evidence document. Foundation contracts, strategy rules/version (1.1.1), risk
engine, execution runtime, and broker gateway were not changed. Independent re-audit is
the next gate: `AG_CANONICAL_PROPOSAL_ORCHESTRATION_BRIDGE_R1_1_INDEPENDENT_REAUDIT`.
