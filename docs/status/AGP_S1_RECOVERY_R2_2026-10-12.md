---
class: status_evidence
state: NOT_VERIFIED
owner_reviewed: null
review_by: 2026-11-12
---
# S1 recovery R2 — validation prepared, authority pending

S1_OWNER_AUTHORITY_BLOCKED; S1_RESOURCE_VALIDATION_PENDING.
LOCAL_LIVE_DATA_ACCEPTANCE = NOT_RUN
SIMULATED_EXECUTION_PATH = NOT_RUN
REAL_DEMO_ORDER_AUTHORIZED = FALSE
REAL_LIVE_ORDER_AUTHORIZED = FALSE

Base/main: 65efdd87e1f762d0ee79ebef5bc1de01d18564f3. New branch from fresh main; no dependency on missing old branch. PR #182 remains historical blocker evidence. No superseding S1 branch advertised.

## Exact authority
Owner register has OD1012-ACCOUNT APPROVED for VTMarkets-Demo suffix 999; OD1012-S1-ACCEPT explicitly says no READY change. OD1012-S1-READY is absent. C14 ratification and OD1010-C6-RISK preserve separate strategy-specific DEMO authorization and leave notification policy pending. No approved BLOCK_NEW_ORDERS policy found. Thus READY remains OFF, S1 enabled false, existing account scope/config unchanged, notification PENDING_OWNER, per-order confirmation true. Account migration is not represented as completed.

Raw frozen contract: 4f936bbe17f4aa4fd3cd9fc85640bed57b6786f43c52e8e2d69aabb7234b14cf.
Canonical contract: 941dec5529f7e5008db9e5b0ae2e7417f7a95c5fe5f29752dd324bb7d4737d69.
Engine: 243c4ff13b1aabe6a5ccdd3fad0b847f15cbfae99e1608ee1636c4d31c07e959.
Logic identity: d7a8ebe5b176e8089905c75a6b0223eebd893c2b9324ca61865aa135d2eec7d5.
Only registry scope S1 is verified: GBPUSD ASIAN_LONDON RANGE_SWEEP, engine_setup SWEEP. Raw and canonical hashes are distinct by design.

## Lightweight implementation
Existing READY code already validates explicit ON, owner version/raw hash/symbol/session binding, and registry logic scope. Static inspection found a narrow malformed-input defect: a list or mapping status is unhashable and membership in the approved-status set raises TypeError. Require a string before membership; malformed records return OWNER_DECISION_RECORD_INVALID. No authorization logic broadened. Reproduction by executed test: deferred, not claimed.

New tests use only temporary TEST_ONLY_S1 records, never committed owner approval:
- 12 combinations: EURUSD/GBPUSD/USDJPY/XAUUSD/BTCUSD/ETHUSD × ASIAN_LONDON/LONDON_NEWYORK. Only GBPUSD ASIAN_LONDON may satisfy the temporary READY owner binding.
- Wrong raw hash, missing owner record, temporary READY OFF.
- Four malformed status shapes: list/mapping/null/boolean.
- Exact raw frozen-file hash assertion.
This is owner-binding unit coverage; it is not complete engine-to-order acceptance and does not grant demo authorization.

## Validation and governance PR #180
PR #180 inspected: open, draft, unmerged, head d28cacb74eec3cc3ba217ccd6892904fd000bf3a. Policy/guard/test blobs were restored unchanged; no amendment needed to the historical source. Existing remote workflows reported completed/success: run 38275660107 (PR merge readiness audit), 38275660073 (docs-hygiene), 38275659849 (main CI). These workflow statuses do not establish that the focused restored guard tests executed; focused validation remains pending.
Phase 1 permits only lightweight work until approved/merged governance. No local baseline pytest, after pytest, Ruff or execution simulation ran. Before/after counts NOT_RUN; historical 67/340 not adopted. git diff --check passed before report/index creation. No broker, order API, Telegram, sealed fixture, dependency install or heavy workload call.

Commands actually executed: git fetch origin --prune; git rev-parse origin/main; git ls-remote --heads origin '*s1*'; targeted owner-register/C14/config/registry/code/test reads; git worktree add /workspace/work/s1-recovery-r2 -b codex/s1-recovery-r2 origin/main; git diff --check; git diff --stat; git status --short. GitHub get_pr_info #180/#182 and workflow queries inspected current PR metadata. Tests edited, not executed.

## Windows read-only acceptance
After resource approval and before any live read, confirm the approved account pin remains VTMarkets-Demo suffix 999 DEMO and the existing host MT5_TERMINAL_PATH identifies the AG terminal, not sandbox. Keep authorization and execution flags disabled. From separate checkout:

```powershell
python scripts/resource_guard.py status --json
python scripts/host/live_eval_smoke.py --out artifacts/validation/s1_recovery_r2
```
Acquire/release R1 around the second command per the restored policy using the workload PID; a failing resource gate blocks it. Existing evaluator uses GuardedMT5 and the existing read-only candle adapter. It evaluates configured FX scopes, not only S1; inspect the GBPUSD ASIAN_LONDON result and archive report SHA256. This command does not provide complete S1 risk/notification simulation and must not be labelled full acceptance.

Record suffix/server/DEMO, terminal identity/connectivity (redact local paths), recent GBPUSD M15 UTC timestamps and closed-bar cutoff, strategy identity, actual signal/ticket or NO_OPPORTUNITY only when the underlying market reason supports it, every authority/actionability/risk/cost refusal, and zero mutation attempts. Missing gates stay NOT_EVALUATED. Generate ASCII Telegram preview only through the existing renderer without a sender; never treat a preview as confirmed delivery. No order-capable adapter may be instantiated. No valid market setup is required. Do not run canonical delivery as a preview because it can send messages.

## Concrete remaining work
1. Review/merge #180 through owner workflow; run focused guard tests and resource status/acquire before this branch's baseline/after regression and Ruff. No automatic merge.
2. Record verifiable OD1012-S1-READY approval with exact frozen raw hash and GBPUSD ASIAN_LONDON scope if READY is intended. Keep OFF until that record exists.
3. Record notification failure-policy approval; then implement delivery-evidence validation with confirmed/failed/unknown/missing/invalid evidence and no bypass of risk/broker/demo gates.
4. Implement approved account 999 migration with explicit 985/unknown/wrong-server negatives and rerun existing boundary fixtures. No historical evidence rewrite.
5. Run hermetic recorded-fixture acceptance and non-order-capable simulation for all 12 requested cases; report exact gate reasons. Current results for account/notification/simulation: NOT_RUN, not PASS.
6. Local agent independently accepts Windows market-data/preview path; separate broker adapter, strategy-specific standing authorization and all C14 broker/risk/idempotency checks remain blockers to real demo orders. This mission authorizes none.

PR=see final response | FINAL_HEAD=containing implementation commit | LINES_ADDED/REMOVED=see PR diff | CONFLICTS_FOUND=NONE | POLICY_CHANGES=0
