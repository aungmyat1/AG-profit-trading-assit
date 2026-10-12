---
class: status_evidence
state: NOT_VERIFIED
owner_reviewed: null
review_by: 2026-11-12
---
# OD1012 S1 activation R3 — review only, no deployment

Owner Aung explicitly approved in AGP-OD1012-S1-ACTIVATION-R3: OD1012-S1-READY (v1.1.2 GBPUSD ASIAN_LONDON only), OD1012-S1-NOTIFY (BLOCK_NEW_ORDERS), and OD1012-ACCOUNT (VTMarkets-Demo, DEMO, suffix 999). The structured owner record is in OWNER_DECISION_REGISTER.md. This PR has not been merged or deployed.

## Source and upstream merges
Initial main: 65efdd87e1f762d0ee79ebef5bc1de01d18564f3.
PR #180 head d28cacb74eec3cc3ba217ccd6892904fd000bf3a: 19 focused resource tests passed; all remote CI jobs passed. Merge SHA 7dfc8a2079f46d6cfd5097a344249603b13339d2.
PR #183 initial head 57a05154e8b2ee468df5058c3f1c17cd23271417: remote tests 2583 passed / 6 skipped, Python lint failed I001. Corrected import order and updated against #180, resolving only docs-index conflict by keeping both entries. Final upstream head 68277ec136746e223d3b273c26c09f89607c9538: focused 65 passed / 1 skipped, Ruff passed, all remote CI passed. Merge SHA a8271feadbd3f0a78aef7b2cd8e814e8362534ea.
GitHub forbids merge commits, so merges were squash. Both final source trees were compared against main for all PR paths; no reviewed change was omitted. Activation branch starts from a8271fea. #181/#182 remain historical evidence; #175 untouched.

Raw contract SHA256 4f936bbe17f4aa4fd3cd9fc85640bed57b6786f43c52e8e2d69aabb7234b14cf; canonical contract 941dec5529f7e5008db9e5b0ae2e7417f7a95c5fe5f29752dd324bb7d4737d69; logic identity d7a8ebe5b176e8089905c75a6b0223eebd893c2b9324ca61865aa135d2eec7d5. Frozen strategy files and registry unchanged. v1.2.0 is outside S1.

## Exact configuration diff
- ready_authority.yaml: ST_ASIAN_SWEEP_5R_V1 ON, reason OD1012-S1-READY, subject to exact v1.1.2 raw hash plus owner symbol/session binding and existing S1 RANGE_SWEEP identity.
- demo_execution_s1.yaml: account_login_suffix 985 → 999; notification policy PENDING_OWNER → BLOCK_NEW_ORDERS.
- enabled remains false; per_order_confirm_required remains true. Risk limits, daily reset, broker symbol map and strategy registry unchanged.
- Historical account evidence and magic inventory preserved; only the inventory comment clarifies the S1 pin moved.

## Gate matrices
READY matrix tested for EURUSD/GBPUSD/USDJPY/XAUUSD/BTCUSD/ETHUSD × ASIAN_LONDON/LONDON_NEWYORK: only GBPUSD ASIAN_LONDON may pass the owner binding. Registry logic-scope matching also remains mandatory. Wrong hash, malformed/missing owner and temporary READY OFF reject. Legacy OFF negatives use a temporary OFF config; no negative coverage deleted. Report-only routes remain REPORT_ONLY and S1 reason becomes DEMO_AUTHORIZATION_ABSENT. Scope reporter was corrected to supply actual version/raw hash/symbol/session to the existing READY loader rather than calling it without identity.

Account: 999 + VTMarkets-Demo + DEMO matches; 985, unknown, missing identity, wrong server and non-DEMO reject. Existing boundary negative coverage remains.

Notification: sealed append-only S1_PRE_ORDER_TELEGRAM_NOTICE outcome, source LIVE, exact ticket-scope/signal/geometry/window binding, current valid-window timestamp, DELIVERED result, delivered true, TELEGRAM channel, api_ok true and positive integer message_id required. Failed, unknown, absent, unsealed, preview, wrong-ticket, invalid/future/expired evidence and unresolved policy block. Latest receipt wins; no fallback to older success. Tied timestamps with distinct receipts reject as ambiguous. No production Telegram sender/writer or broker adapter is connected by this PR; future integration must persist genuine Telegram API results using the existing store. A caller claim or preview is insufficient. Receipt seals detect tampering; they are not cryptographic authentication, so the trusted host delivery integration remains a separate acceptance requirement.

The receipt is re-read at pre-send admission and inside every pre-trade guarded transition, including send authorization. Failed notice never consumes the owner confirmation. Existing risk/expiry reason precedence is preserved.

## Tests and simulation
Baseline related suites: 602 passed, 1 skipped in 48.65s (not the historical 67/340). After initial configuration, 13 stale related expectations were exposed (630 passed, 1 skipped); preserved OFF negatives and adjusted version-specific historical contexts. Focused affected tests plus recorded positive preview: 171 passed, 1 skipped in 10.35s.
Initial full local suite: 2644 passed, 5 skipped, 1 failure in 220.53s. The sole failure was documentation subprocess unable to find cog on PATH; installed cogapp 3.5.1 and reran the documentation tests with the venv on PATH (all passed). Final notification/recorded-preview tests: 43 passed in 2.25s. Final related suite: 645 passed, 1 skipped in 36.92s. Machine-readable [scope and actual simulation evidence](AGP_OD1012_S1_ACTIVATION_R3_2026-10-12.json) accompanies this report. Remote full CI is recorded in the PR body/final response on the exact head; no pending result is a PASS. Changed-file Ruff, git diff --check, documentation links (0 broken), skill mirrors (33 identical) and blocking documentation drift (0 errors) pass. Generated outputs were regenerated via collect_facts.py, generate_live_status.py, cog, build_context_pack.py and generated_files.py, never hand-edited. check_generated_files.py --mode strict reports 0 failures / 4 fingerprint-only warnings. A direct --mode pr check on a non-merge local checkout failed PR_CONTEXT_UNAVAILABLE; remote merge-context CI is authoritative for that check.

Hermetic decision-only simulation covers valid scope, wrong scope, wrong raw hash, wrong account/server, stale data, missing stop, failed risk, failed delivery, missing authorization, uncertain duplicate ticket and broker-unavailable identity. It uses temporary test-only standing records, never owner host authorization. Mock only records NO_ORDER_SUBMISSION decisions and exposes no broker methods. Valid synthetic gates may be ADMITTED_PRE_SEND; that is not real DEMO authority or a broker action.
Recorded positive preview uses GBPUSD 2026-07-23 prefixes from immutable 60-day fixture SHA256 aeaf0ba504569f1fa8b9867f2ac8992e8b33fc143a247644e48a34be16cf2a33. Quote snapshots and test policies are explicitly replay inputs; no live tick or host claim. Frozen engine produces a genuine recorded qualifying ticket; route remains EXECUTION_DISABLED, risk snapshot missing, notification missing, ASCII preview only. Unclosed M15 bars reject.

## Read-only Windows command
Claude Code Local must use a separate checkout of this exact PR head; do not pull/update the installed live tree or modify tasks, MT5 settings or host authorization. Verify the existing approved AG terminal path; never attach the sandbox. Acquire R1 through resource_guard for the actual workload PID, with one worker; BUSY/UNKNOWN/resource failure blocks.

```powershell
python scripts/resource_guard.py status --json
python scripts/host/s1_readonly_acceptance.py --terminal-path '<APPROVED_AG_TERMINAL_PATH>' --out work/s1_acceptance.json
Get-FileHash work/s1_acceptance.json -Algorithm SHA256
```

Acquire/release wrapper and owner-review handoff are described in the policy; do not copy a shell PID from a terminated command. Run during the contract ASIAN_LONDON window. The harness verifies exact suffix 999/server/DEMO, pinned terminal path and connectivity, reads GBPUSD through the existing accepted MT5 adapter, checks closed bars and quote freshness, evaluates frozen runtime scope, records raw/canonical ticket and every gate, and renders existing canonical ASCII text without a sender. Host path is redacted at capture. Actual NO_OPPORTUNITY is accepted; data/authority failures stay explicit. Missing host risk metrics remain RISK_SNAPSHOT_MISSING rather than invented daily totals. No signal is forced and no pre-order notice receipt is fabricated.

Output checklist: host SHA, terminal/server identity, suffix/mode, UTC candle timestamps and quote freshness, strategy version/full raw hash, signal or no-opportunity reason, entry/stop/targets, READY/actionability, risk/cost/notice gates, ASCII preview and EXECUTION_DISABLED. Confirm broker_mutations=0/order_api_calls=0/telegram_sends=0; archive report hash. Actual Windows acceptance NOT_RUN in cloud.

## Safety and remaining demo requirements
LOCAL_LIVE_DATA_ACCEPTANCE = NOT_RUN. Host deployment and activation-PR merge NOT_PERFORMED. Broker mutations 0; actual order API calls 0; Telegram sends 0. No standing DEMO authorization created; real demo/live order authority FALSE.
Before any future demo execution: owner separately approves activation PR/deployment, independent host acceptance, trusted Telegram delivery receipt persistence, verified account/magic inventory, host risk snapshots, C11 broker adapter and broker round-trip acceptance, separate revocable strategy-specific standing DEMO authorization, and all existing confirmation/risk/freshness/cost/idempotency gates. No live authorization.

OSS-FIRST: strategy/ticket/preview orchestration | existing frozen repo engine + canonical renderer + MT5 read-only adapter | REUSED | no new trading or indicator rules. Delivery evidence | existing TicketStore sealed outcomes | WRAPPED | ticket-bound owner-policy gate, no sender/order implementation.

PR=see final response | FINAL_HEAD=containing activation commit | LINES_ADDED/REMOVED=see PR diff | CONFLICTS_FOUND=docs-index upstream conflict resolved keeping both entries | POLICY_CHANGES=2 owner-approved S1 READY/notification; account applies existing OD1012

## Reproducibility commands
Dependencies: requirements.txt pinned versions, Python 3.12.14, plus cogapp 3.5.1. All local test jobs acquired the canonical resource lock as ARENA_WEB with their workload shell PID and released it; resource class R1 for focused/related checks, R2 for full suite; one worker and no concurrent heavy local replay. Available RAM at full acquisition 9236 MB, required 2500 MB; peak observed process RSS about 193 MB. Captured resource snapshots and UTC execution stamps are in the machine-readable evidence; no host path/account secrets captured.

Related baseline command: python -m pytest -q tests/test_d6_*.py tests/test_demo_execution_*.py tests/test_scope_status.py tests/test_crypto_strategy_summary.py tests/test_canonical_fx_delivery.py tests/test_manual_ticket_*.py tests/test_g3_manual_ticket_risk_cost_gate.py tests/test_s1_recovery_ready_validation.py
Final related command adds tests/test_s1_activation.py tests/test_s1_readonly_acceptance.py and AGP_S1_SIM_EVIDENCE_DIR for actual decision evidence. Full command python -m pytest -q. Only configured slow tests are deselected; genuine MT5-required tests are skipped by the existing Linux portability shim, never labelled host PASS.

Exact Windows acquire/preview/release wrapper from the separate reviewed checkout:
```powershell
@'
import os, subprocess, sys
resource = [sys.executable, "scripts/resource_guard.py"]
owner = ["--agent", "CLAUDE_CODE", "--mission", "S1-R3-WINDOWS-PREVIEW", "--pid", str(os.getpid())]
subprocess.run(resource + ["status", "--json"], check=True)
subprocess.run(resource + ["acquire"] + owner + ["--class", "R1", "--command-summary", "S1 read-only preview"], check=True)
try:
    subprocess.run([sys.executable, "scripts/host/s1_readonly_acceptance.py", "--terminal-path", sys.argv[1], "--out", sys.argv[2]], check=True)
finally:
    subprocess.run(resource + ["release"] + owner, check=True)
'@ | python - '<APPROVED_AG_TERMINAL_PATH>' 'work/s1_acceptance.json'
Get-FileHash work/s1_acceptance.json -Algorithm SHA256
```
This is supplied for Claude Code Local only; no Windows invocation executed in cloud. Execute once during the authoritative window; preserve actual blocked/data/no-opportunity results and do not change parameters for a signal.
