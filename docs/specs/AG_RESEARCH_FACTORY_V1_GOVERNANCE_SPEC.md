# AG Research Factory V1 Governance Specification

Status: normative infrastructure contract, implemented 2026-09-14. This specification
supersedes example schemas in `AG_REUSABLE_STRATEGY_IMPLEMENTATION_PLAN_V1.md`; examples
are not evidence and placeholder hashes are invalid.

## Authority and lifecycle

Research results, narrative reports, and MLflow records are indexes—not frozen-candidate
authority. Candidate identity requires persisted physical bytes, a complete effective
configuration, provenance, dataset/split/economic identities, and independently reopened
SHA-256 verification.

`DRAFT → EXPERIMENTING → ROBUSTNESS_REVIEW → FREEZE_ELIGIBLE →
ARTIFACT_PERSISTENCE_CHECK → FROZEN_FOR_HOLDOUT → HOLDOUT_PASS/HOLDOUT_FAIL →
CANONICAL_IMPORT_CHECK → CANONICAL_INTEGRATION → PARITY_PASS/PARITY_FAIL → R6_REVIEW →
R6_PASS/R6_FAIL → DEMO_ELIGIBILITY_REVIEW → DEMO_AUTHORIZATION_REVIEW → STAGE1_DEMO`.

`R6_PASS` does not grant Demo authorization. Demo eligibility and Demo authorization are
separate reviews. Demo authorization never grants Live authorization.

## Candidate Artifact Persistence Gate

The pre-Holdout package is the exact file set declared by
`external_candidate.research_factory.PRE_HOLDOUT_FILES`. In particular,
`effective_candidate_config.yaml`, `provenance.json`, `candidate_manifest.json`,
`dataset_manifest.json`, `split_manifest.json`, and `economic_contract.json` are
mandatory. Holdout artifacts must not be present before the authorized one-shot run.

Persistence passes only after all files are closed, reopened, schema-checked, hashed
against `SHA256SUMS.txt`, and reopened and hashed independently a second time. Missing,
empty, unreadable, mutated, duplicate-path, non-hex, wrong-length, manifest-mismatched,
or cross-identity-mismatched artifacts fail closed and block Holdout.

The effective configuration is the complete evaluated strategy, including symbols,
sessions and all window roles, timeframes, regime/H1/M15/M1 logic, setup state, entry,
SL, TP, campaign, risk, friction, and reason-code behavior. Parameter overrides or
narrative reports cannot substitute for it.

## Economic contract and Holdout firewall

`economic_contract.json` is frozen before Holdout, byte-hashed, and referenced by the
candidate manifest and evidence. Changing it invalidates the lineage. Holdout admission
requires `FROZEN_FOR_HOLDOUT`, persistence PASS, integrity PASS, binding PASS, and a
frozen economic contract. The identity ledger permits one claim only and records the
candidate/config/economic/dataset/split hashes plus authorization ID. A claim is treated
as consumed conservatively, including after interruption; it cannot be silently reset.

## Canonical import and parity

Canonical import independently recomputes physical hashes and requires a cryptographically
bound `holdout_result.json` with `result=PASS`, `holdout_state=CONSUMED`, and
`run_number=1`. Import preserves source bytes.

Semantic parity is exactly 100%, with zero unexplained mismatches. The comparison fields
are occurrence ID, symbol, timestamp, direction, setup, decision state, reason codes,
entry, stop loss, take profit, and campaign admission. Numeric tolerance defaults to
zero and may only be supplied as a predeclared deterministic policy. Any mismatch is
`PARITY_FAIL`; strategy economics are not changed to force agreement.

## Safety boundary

This infrastructure performs no optimization, broker interaction, strategy mutation,
Demo/Live promotion, or order submission. `ST_SESSION_SWEEP_CONTINUATION_V1` and the
unrecoverable `AG_EXTERNAL_CANDIDATE_S1S2_V1` lineage remain unchanged.
