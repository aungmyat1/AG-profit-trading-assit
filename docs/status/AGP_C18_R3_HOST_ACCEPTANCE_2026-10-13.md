# AGP-C18-R3 — Windows Host Acceptance Evidence

**Date:** 2026-10-13 (UTC)

**Final verdict:** `C18_HOST_PREFLIGHT_BLOCKED`

**Evidence tier:** GitHub integration and synthetic repository validation only; no real-host evidence.

## Executive result

The C18 software changes are merged into `main`, and the focused synthetic integration suite passes. The Windows host at `D:/wp3-main-integ` is not exposed to this Linux Arena workspace: the D: path and `/mnt/d` mount are absent, PowerShell is unavailable, and no Windows-host or Telegram connector is available here. The actual MT5 terminal, Task Scheduler, host-local configuration, resource state, and Telegram destination therefore could not be inspected.

The ordered gate stopped at Phase 3. **No deployment, scheduled-task inspection or enablement, real-market evaluation, Telegram send, or host broker-history reconciliation was performed.** Synthetic results below are not host acceptance evidence.

## 1. GitHub authority and merge state

A fresh `git fetch origin --prune` on 2026-10-13 reported `origin/main` at **`5d8a6fba2bee624709446e0191b51de95c32e7f1`**. That is also PR #190's merge commit. The Arena working branch was clean at that SHA before this evidence report was added.

| PR | State | Base | Head | Mergeability (fresh query) | Merge SHA / merged time |
|---|---|---|---|---|---|
| #186 | OPEN; separate ASW v1.1.3 candidate | `main` | `feat/asw-v113-engine` @ `04a1ccbdbb7627bb3806f965b02279dff0d3a0a6` | `DIRTY` / `CONFLICTING` | — |
| #187 | MERGED | `main` | `feat/c18-scope-canonical-ticket` @ `06531ee739e970f0fd34974e9bc044adfbaa650e` | `UNKNOWN` after merge | `e7c2220d60b10bc0d86e5b9f39763736a5372267`; 2026-10-13 05:56:21Z |
| #188 | MERGED | `main` | `feat/c18-report-lanes` @ `7563d2aa208ff8b6b388daad344b42945bcb0a56` | `UNKNOWN` after merge | `7b4cfc68cb7bbb6dad8596f72b81e1bba900d9a3`; 2026-10-13 05:56:42Z |
| #189 | OPEN; separate LSMC audit | `main` | `arena/b50fb2fa-ag-profit-trading-assit` @ `0cd570348edfc793654e07b9bee873b624b389e0` | `CLEAN` / `MERGEABLE` | — |
| #190 | MERGED | `main` | `feat/c18-report-delivery` @ `212ff4ac4944dff2413ce785d05f7302e78e997d` | `UNKNOWN` after merge | `5d8a6fba2bee624709446e0191b51de95c32e7f1`; 2026-10-13 07:19:48Z |

GitHub compare results confirm #187's merge SHA is an ancestor of current main (`ahead_by=2`, `behind_by=0`) and #188's merge SHA is an ancestor (`ahead_by=1`, `behind_by=0`). PR #190's merge SHA equals current main. Thus **#187, #188, and #190 are incorporated**; #186 and #189 remain separate and unmerged. #190 was already merged on the fresh check, so no branch update or merge action was necessary.

### Required checks

On the exact HEAD SHA of each of #186, #187, #188, #189, and #190, GitHub reported **SUCCESS** for all six named checks: `python-tests`, `docs-drift`, `audit`, `frontend-checks`, `stale-check`, and `CodeRabbit` (some workflows had duplicate successful runs). The green checks on #186 and #189 do not mean those PRs were merged.

On current main `5d8a6fba2bee624709446e0191b51de95c32e7f1`, the post-merge push run reported `python-tests`, `docs-drift`, `audit`, `frontend-checks`, and `stale-check` successful. The separate `regenerate` job failed at **“Publish through the regeneration PR”**; its “Regenerate the four generated files” and “Check regenerated outputs are self-consistent” steps succeeded. This non-listed job failure is recorded, not treated as a required PR check or hidden. Its underlying publish-step cause was not available from the returned GitHub job metadata.

### Fresh changed-file inventory

Inventory below is from the current GitHub PR file lists. It is included to distinguish the C18 integration from the two unmerged candidates.

- **#186 (15):** `PROJECT_STATUS.md`; `artifacts/logic_verification/ST_ASIAN_SWEEP_5R_V1_1_1_3/c17_2026-10-13/{asw_v112_60d_regression.json,asw_v113_60d_run1.json,asw_v113_60d_run2.json,l3_repro_eurusd_asian_london_2026-07-31_v113.json}`; `docs/README.md`; `docs/status/AGP_C17_ASW_V113_ENGINE_VERIFICATION_2026-10-13.md`; `scripts/{asw_v112_60d_replay.py,asw_v112_l3_repro_0731.py,asw_v112_logic_verification.py}`; `src/strategy_engine/append_only.py`; `src/v1_tickets/{authority.py,fx.py}`; `tests/{test_asw_v113_append_only_engine.py,test_asw_v113_zero_risk_append_only.py}`.
- **#187 (6):** `docs/README.md`; `docs/status/AGP_C18_R2_IMPLEMENTATION_PLAN_2026-10-13.md`; `src/telegram_delivery/adapter.py`; `src/v1_tickets/{canonical_ticket.py,scope_status.py}`; `tests/test_canonical_ticket_scope_fields.py`.
- **#188 (16):** `docs/README.md`; `docs/status/AGP_C18_R2_IMPLEMENTATION_PLAN_2026-10-13.md`; `scripts/host/{_host_common.py,live_candles_smoke.py}`; `src/reporting/{__init__.py,asw_lane.py,ccfd_lane.py,common.py,lsmc_lane.py}`; `src/telegram_delivery/adapter.py`; `src/v1_tickets/{canonical_ticket.py,scope_status.py}`; `tests/{test_canonical_fx_delivery.py,test_canonical_ticket_scope_fields.py,test_host_go_live_kit.py,test_report_lanes.py}`.
- **#189 (19):** `PROJECT_STATUS.md`; `artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_0/c15_lsmc_audit_2026-10-13/{lsmc_v110_logic_audit.json,lsmc_v110_logic_verification_18case.json,lsmc_v111_candidate_audit.json}`; `docs/agents/CONTEXT_PACK.md`; `docs/status/{AGP_C15_LSMC_V110_LOGIC_AUDIT_2026-10-13.md,AGP_C17_LSMC_LOGIC_COMPLETION_R1_2026-10-13.md,PROJECT_LIVE_STATUS.md,c16_2026-10-12/C16_DEFECT_REGISTER.md}`; `scripts/lsmc_v110_logic_audit.py`; `src/v1_tickets/lsmc_logic_gate.py`; `status/facts.json`; `strategies/{ST_LARGE_SMC_V1_1_1_2.yaml,registry.yaml}`; `tests/_lsmc_v111_fixtures.py`; `tests/fixtures/large_smc_v111/{EURUSD.json,manifest.json}`; `tests/{test_lsmc_v110_logic_audit.py,test_lsmc_v111_candidate_audit.py}`.
- **#190 (10):** `config/ticket_delivery.yaml`; `docs/governance/OWNER_DECISION_REGISTER.md`; `docs/status/AGP_C18_R2_IMPLEMENTATION_PLAN_2026-10-13.md`; `scripts/host/{canonical_fx_delivery.py,live_candles_smoke.py,verify_objective.py}`; `src/reporting/deliver.py`; `src/telegram_delivery/adapter.py`; `tests/{test_host_go_live_kit.py,test_report_delivery.py}`.

No C18 PR changed a frozen strategy engine/contract identity, strategy registry, risk limit, `config/trading.yaml`, `config/demo_execution_s1.yaml`, or `config/v1_tickets/ready_authority.yaml`. #186's ASW engine/authority changes and #189's LSMC contract/registry changes remain on their respective open PRs and are not part of current main. The expected #190 change is the reporting-only immediate-send scope and owner-decision record.

### Tracked execution and delivery settings reviewed

- `config/trading.yaml`: `mode: ANALYSIS`; `allow_order_check: false`; `allow_order_send: false`; `allow_live_trading: false`.
- `config/demo_execution_s1.yaml`: `enabled: false`; `per_order_confirm_required: true`; tracked account pin is VTMarkets-Demo / login suffix `999` / DEMO. No full account number is recorded here.
- `config/v1_tickets/ready_authority.yaml` retains its pre-existing S1 `ready: ON` row; C18 added no READY authorization and its observational lane downgrades executable-looking engine results.
- **Host-specific caveat:** `config/trading.demo.yaml` separately contains `allow_order_check: true` and `allow_order_send: true`. It was not changed by C18, and its use by either Windows task could not be inspected. The host's effective config path and task arguments must be checked before any task is run. This is not evidence that the host currently loads that file.
- The tracked C18 Telegram ceiling includes `REPORT_CANDIDATE`, `REPORT_BLOCKED`, and `REPORT_WATCH`. Host-local canonical delivery override, `TELEGRAM_DELIVERY_ENABLED`, token/chat configuration, and the authorized destination were not available for inspection. No destination was widened or contacted.

## 2. Post-merge software integration — synthetic tier

The merged tree contains the scope-aware canonical V1 fields and exact version/instrument/session/direction resolver; ASW, LSMC, and CCFD observation lanes; archive-first REPORT_ONLY delivery; INTENT/RESULT journaling; SQLite-backed duplicate and uncertain-delivery handling without automatic retry; and session plus daily strategy summaries.

The focused tests exercised and passed the following synthetic contracts:

- Every observation stays `scope_route=REPORT_ONLY`; scope verification and identity are bound to the exact version and evidence identity.
- ASW v1.1.3 does not inherit v1.1.2 status (`VERSION_NOT_IN_SCOPE:1.1.3`). The ASW lane short-circuits suspended EURUSD / ASIAN_LONDON v1.1.2 to a BLOCKED diagnostic without evaluating that scope. S1 remains on its existing canonical path.
- LSMC instrument-scope status stays UNVERIFIED. Missing C10/C11 evidence produces BLOCKED diagnostics without invented levels.
- CCFD rows retain the actual v1.0.0 identity and direction-specific scope; no v1.0.0 result is represented as v1.1.0.
- REPORT_ONLY renderers enforce ASCII format and execution-disabled language. Delivery tests cover archive/INTENT/RESULT, receipt-backed message IDs, duplicate suppression, failure/uncertain states without automatic retry, and summary-only handling.
- Static boundary tests reject order-capable imports/calls from the reporting lane; synthetic identity assertions preserve the existing S1 strategy identity.

**Local resource gate:** R1 PASS for the focused suite (3,939 MB total; 3,676 MB available at acquisition; 1,200 MB required); no pre-existing lock; no registered competing heavy job; lock acquired and released successfully. This is the Arena workspace result, not the Windows host's R1 result.

**Focused command:**

```text
.venv/bin/python -m pytest -q \
  tests/test_canonical_ticket_scope_fields.py tests/test_scope_status.py \
  tests/test_report_lanes.py tests/test_report_delivery.py \
  tests/test_canonical_fx_delivery.py tests/test_telegram_delivery_adapter.py \
  tests/test_lsmc_delivery_diagnostics.py \
  tests/test_ticket_delivery_concurrency_and_restart.py \
  tests/test_ticket_delivery_execution_boundary.py \
  tests/test_ticket_delivery_identity_and_archive.py \
  tests/test_ticket_delivery_policy.py tests/test_ticket_delivery_renderer.py \
  tests/test_host_go_live_kit.py
```

**Result:** `378 passed, 1 skipped in 15.80s`. The skip is `test_import_mt5_real_package_wins_over_stub_first_on_path`: the genuine MetaTrader5 package is not installed in this Linux workspace. No connected terminal was used. Fixtures and fake transports in this suite are synthetic; they do not establish real market-data acceptance or Telegram delivery. No full-repository test suite was run in this phase.

## 3. Windows preflight and ordered stop

| Required preflight item | Result |
|---|---|
| Windows host / `D:/wp3-main-integ` reachable | **BLOCKED** — Linux workspace only; specified path and `/mnt/d` mount absent; no PowerShell executable or host connector. |
| MT5 running; live server/account mode/login suffix verified | **NOT VERIFIED** — tracked pin says VTMarkets-Demo / …999 / DEMO, but no runtime account read was possible. |
| Host Git SHA and clean working tree | **NOT AVAILABLE** — host filesystem not accessible. |
| No scheduled trading cycle active | **NOT VERIFIED**. |
| Windows host resource threshold / R1 lock | **NOT EVALUATED**. The local R1 test gate above is not a substitute. |
| Task definitions, action/arguments, working directory, environment, triggers | **NOT INSPECTED** for `AG-V1-Crypto-Daily` or `AG-V1-LSMC-Watch`. |
| Effective execution flags, host-local pins, Telegram allowlist | **NOT INSPECTED**. |

The first preflight could not be established, so the required stop was applied:

- **Phase 4 deployment:** NOT RUN. No host `git pull`, checkout, or configuration overwrite was attempted; host SHA is unknown.
- **Phase 5 scheduled tasks:** NOT INSPECTED or changed. Neither task was enabled by this agent. Their actual enabled/disabled state on Windows is **UNKNOWN**; no unrelated task was touched.
- **Phase 6 strategy acceptance:** ASW session, LSMC live transition, and CCFD evaluation window are each **NOT RUN**. There is no real-host `NO_OPPORTUNITY` or signal result to report.
- **Phase 7 Telegram:** no real message was attempted or delivered; no host INTENT/RESULT record or Telegram message ID was collected. Synthetic fake-transport receipts are not real delivery evidence. Arena reports the Telegram connector as unsupported in this session.

## 4. Zero-order evidence boundary

No real MT5 terminal, broker API, or Windows task was invoked by this workspace run; the selected tests use fixtures, fakes, or the repository's refusal stub. The reporting-lane static tests pass. **That does not establish zero order calls on the Windows host**, because no host acceptance run or execution-boundary instrumentation was available and no broker-history reconciliation was performed.

For the requested host acceptance run, the required counters are therefore **NOT MEASURED / INSUFFICIENT EVIDENCE**, not PASS and not asserted as zero:

```text
acceptance_run_started = false
broker_mutations       = NOT_MEASURED
order_check_calls      = NOT_MEASURED
order_send_calls       = NOT_MEASURED
demo_orders_created    = NOT_MEASURED
live_orders_created    = NOT_MEASURED
```

## 5. Final status and resumption gate

**`C18_HOST_PREFLIGHT_BLOCKED`**

C18 is **not complete**. Repository integration and synthetic validation are complete, but host deployment, both task safety checks, all three real read-only strategy-family checks, approved Telegram delivery evidence, and host zero-order proof remain pending. Resume only when the Windows host is available and Phase 3 can verify account/server identity, current host SHA/tree, idle scheduler state, host resource gate, exact task actions/configuration, effective execution flags, and the existing authorized Telegram destination. Do not infer a host pass from merged PRs, green CI, or synthetic fixtures.
