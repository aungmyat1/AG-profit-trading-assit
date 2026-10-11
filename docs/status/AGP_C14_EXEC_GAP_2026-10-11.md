---
class: evidence
state: UNIT_TESTED
owner_reviewed: null
review_by: null
---
# AGP C14 execution-path gap audit — 2026-10-11 (UTC)

## Base, scope and verdict

- **Selected base: unmerged [PR #148](https://github.com/aungmyat1/AG-profit-trading-assit/pull/148) head `7532e6fb9b925c7d13d96209fcdcaa69aca57840`**, branch `docs/c14-auto-demo-ratification-20261011`. GitHub reported OPEN, `mergedAt=null`. The documentation PR is stacked onto that branch so its diff is one added file, not a replacement of `main` code.
- Fetched `origin/main`: `1d8891392fc522e9b979008e6f4be0091d9309b2`. It is **not** the selected audit base.
- [PR #133](https://github.com/aungmyat1/AG-profit-trading-assit/pull/133) is also OPEN/unmerged, head `6e4bcba9ea94112172c79d653ca30bc4de9c2c15`. Its lifecycle store was inspected and tested in an isolated export; it was **not** merged/cherry-picked into the selected base.
- Authority: [ratified C14](../governance/AGP_C14_AUTO_DEMO_OWNER_DECISION_2026-10-11.md), [objective](../PROJECT_OBJECTIVE.md), and [owner register](../governance/OWNER_DECISION_REGISTER.md), especially `C14` and `OD1010-C6-RISK`. C14 approves sequencing/ceilings, **not** a standing strategy authorization. EDGE_VERIFIED and a mandatory ten-cycle soak are not DEMO prerequisites.
- **Verdict: no complete, reachable C14 automatic DEMO execution chain exists in the tracked base.** Ticket/READY and informational delivery components exist; the execution boundary, scoped authority and their lifecycle integrations do not.
- Production remains `ready: OFF`, with no structured READY owner record in the register; every registry strategy has `demo_authorized=false` and `live_authorized=false`. `config/trading.yaml` remains ANALYSIS, both order API flags false, live trading false. Nothing in this audit changes these values.
- Documentation/status mission only: one new evidence file; no application code, configuration, generated/rolling documents, authorization records, host state or broker state changed. No execution CLI or gateway was invoked. **ORDER_API_CALLS=0; BROKER_MUTATION_COUNT=0.**

**Classification:** `IMPLEMENTED` = the named component exists and relevant offline regressions passed below; not host/broker validation. `IMPLEMENTED_NOT_TESTED` = inspected code exists, but its relevant behavior was not exercised in this audit. `MISSING` = no tracked implementation or no wiring that satisfies the requested C14 hop. Component-level implementation does not upgrade a missing execution integration. For an absent module, there is no actual `file:function` to name; the absent boundary and its surviving caller are stated explicitly.

## Actual paths versus the requested chain

```text
FX informational evaluation:
  daily_evaluator.evaluate_fx_pair
    -> fx.build_fx_ticket -> guards.gate_ready -> ready_authority.apply_ready_authority
    -> daily_evaluator._finalize -> canonical_ticket.build_canonical_ticket
    -> ticket_store.adapter.write_canonical (V1 evaluation, not an order lifecycle)

Manual FX ticket / owner intent (a separate lane):
  manual_ticket.build_manual_ticket -> fx.build_fx_ticket (same READY checks)
    -> L1-L6 / lot_size / ticket cost checks -> archive_manual_ticket
  archived TICKET_READY -> telegram_confirm.handle_callback
    -> owner_decision.record_decision / execution_handoff (always blocked stub)

Requested C14 automatic chain — not connected:
  immutable qualified ticket -> READY -> scoped standing DEMO authorization
    -> five C14 risk limits -> fresh cost gate -> order_check
    -> assistant.commands.execute_command -> order_send -> broker reconciliation
    -> correlated append-only #133 audit -> Telegram execution result
```

The first two lanes are not an implicit implementation of the third. In particular, scheduled canonical FX evaluation does not run `build_manual_ticket`'s risk/cost checks. Audit writes must also surround the irreversible send (durable intent before network, subsequent check/result/reconciliation events); the logical chain above does not permit postponing all persistence until after reconciliation.

## Hop-by-hop trace

| Hop | File:function / actual connection | Classification | Missing-input / fail-closed behavior | Duplicate / restart safety |
|---|---|---|---|---|
| 1. Engine output → informational ticket | `src/v1_tickets/daily_evaluator.py:evaluate_fx_pair`, `_finalize`; `src/v1_tickets/fx.py:build_fx_ticket`; `src/v1_tickets/guards.py:gate_ready`; `src/v1_tickets/canonical_ticket.py:build_canonical_ticket` | **IMPLEMENTED** — informational, not executable admission | Missing provider/data or engine errors yield explicit error/insufficient-data outcomes; missing engine signal timestamp yields `SIGNAL_TIME_UNAVAILABLE`; missing spread withholds READY. **Caveat:** `gate_ready(data_close=None)` skips the data-age gate; it is not send-time freshness enforcement. Canonical execution/demo/live flags are always false. | `src/ticket_delivery/identity.py:logical_ticket_id` is deterministic across retry/restart. `canonical_ticket.append_archive` appends reevaluations without deduplicating them. Neither identity nor archive reserves an order; immutable proposal-content/runtime/account binding for execution is missing. |
| 2. FX READY + owner binding | `src/v1_tickets/fx.py:build_fx_ticket` → `src/v1_tickets/ready_authority.py:apply_ready_authority` → `ready_authority`, `_owner_records`, `symbol_verified` | **IMPLEMENTED** — FX READY gate; not standing DEMO authority | Requires config ON, an approved record matching strategy/version, SHA256 of the **loaded contract**, symbol and session, plus registry per-symbol verification evidence. Missing/unreadable config, missing/invalid record, mismatch, unreadable contract or absent symbol evidence downgrades READY to `SHADOW_INFO_ONLY` with an explicit reason. Production is OFF/no record. | Pure admission check, reread on invocation; repeated calls grant no order and consume no execution slot. There is no atomic send claim or standing authorization expiry/revocation protocol here. |
| 2b. Uniform C14 READY/executable-ticket admission across scopes | Existing separate CFD route: `src/v1_tickets/crypto_cfd.py:build_crypto_cfd_cycle` → `src/v1_tickets/manual_ticket.py:build_crypto_cfd_manual_ticket`; shared executable-admission function: **none** | **MISSING** — all-scope execution integration | CFD proposals check policy, quotes and exact logic identity/active ticket admission, but do not call `apply_ready_authority`; their `execution_authorized` is false. The READY owner-binding call is wired into the FX builder only. Large-SMC watch/OPPORTUNITY is not executable READY. These products cannot inherit FX admission or C14 authorization. | No common immutable order-intent claim across FX/Gold, CFD crypto and Large-SMC. Watch/message deduplication is not an order reservation. |
| 3. READY → standing scoped DEMO authorization | `src/host_delivery/telegram_confirm.py:execution_handoff` is a **stub**; `src/v1_tickets/authority.py:resolve_ticket_authority` resolves informational authority only. No standing-authorization store/validator exists on this path. | **MISSING** | Stub returns `BLOCKED_NOT_AUTHORIZED` for false/missing DEMO flag, disabled send or unavailable authority config; even both flags true returns `HANDOFF_NOT_IMPLEMENTED`. No per-order binding to approved strategy/version/runtime SHA, account/venue, broker symbol/session, expiry/revocation or emergency stop. The informational authority resolver actually requires demo/live flags exactly false and `demo_order_authority=NONE`; flipping a flag is not an implementation. | Callback decision persistence is idempotent, not broker submission. Standing authorization/revocation and durable execution claims are absent. A Confirm is neither required under an authorized C14 scope nor capable of creating that scope. |
| 4. Authorization → five C14 risk limits | `src/sizing_math/risk.py:size_position`; `src/v1_tickets/manual_ticket.py:lot_size`; `src/sizing_math/position_guard.py:OpenPositionGuard`; `src/sizing_math/daily_loss_guard.py:DailyLossGuard`; pilot reference helpers detailed below | **MISSING** — unified server-owned C14 enforcement; sizing primitives exist | No send-path enforcement of all five approved ceilings using verified DEMO equity, broker positions and daily accounting. Missing daily-reset timezone must block; existing research defaults cannot supply it. `config/trading.yaml` still contains legacy 1.0% sizing configuration, not a C14 cap. | No atomic portfolio/trade-cap reservation tied to a durable order intent, no broker-backed recovery, and no account-wide loss latch. Details and missing-state caveats below. |
| 5. Risk → send-time cost gate | Ticket components: `src/v1_tickets/manual_ticket.py:load_owner_config`, `build_manual_ticket`, `cost_at_or_above_block`, `crypto_cfd_cost_gate`, `build_crypto_cfd_manual_ticket`; `src/v1_tickets/crypto_cfd_policy.py:load_ticket_policy`. Execution cost-gate function: **none** | **MISSING** — send-time gate; named ticket checks **IMPLEMENTED** | FX required risk/warn/block keys missing → `RISK_CONFIG_MISSING`/`TICKET_BLOCKED`; total cost ≥0.25R blocks. CFD missing/wrongly bound policy blocks; missing spread/quote time or stale quote blocks. **Unknown commission is only a warning on these informational paths**, with spread-only cost calculated; do not claim a complete verified-cost execution gate. No fresh spread/fees/geometry/volume/margin recheck before send. | Ticket checks can be recomputed without orders, but have no reservation or atomic quote-to-send binding. Previously passing ticket costs are not reusable execution approval after restart/expiry. |
| 6. Cost → broker `order_check` | `src/execution/mt5_gateway.py` is absent; no tracked check function/call exists. Historical reference: `config/trading.yaml`'s `execution.allow_order_check`. | **MISSING** | Flag defaults false, but comments/config are not an executing guard. No broker check request construction, current DEMO account validation, margin/stops/fill-policy checks or accepted-check result handling. Missing input must block a future executor; current stub never reaches this hop. | No checked-request hash persisted/bound to the subsequent send. A check would not itself reserve or deduplicate an order. |
| 7. Check → `execute_command` → `order_send` | `src/assistant/commands.py:execute_command`, `src/execution/executor.py` and `src/execution/mt5_gateway.py` are absent. Surviving legacy caller `scripts/execute_trade.py:main` imports the absent executor. | **MISSING** | There is no reachable canonical send boundary, C14 standing-authority entry point or final DEMO-only identity recheck. Legacy CLI fails at import, not through a typed C14 denial; it must not be used/restored as an authorization shortcut. Current Telegram handoff stays blocked regardless of flags. | No durable command/intent claim, at-most-once dispatch, send-time revocation/stop recheck or uncertain-send latch. Never manufacture `user_confirmed=True` to bypass historical confirmation semantics. |
| 8. Send → broker reconciliation | `scripts/run_ag_execution_runtime.py:_run_cycle` references `startup.ctx.coordinator.reconcile()`; `src/execution_runtime/startup.py`, `cycle.py`, `data_provider.py`, `src/execution/coordinator.py` and `lifecycle.py` are absent. No reachable broker reconciler. | **MISSING** | No verified positions/orders/deals recovery correlated to immutable intent and confirmed fill/reject/unknown result. Missing broker response/history cannot be called a fill or permit another send. `ticket_delivery.delivery_store.DeliveryStore.resolve_ambiguous_outcome` reconciles **message delivery**, not MT5 orders. | No startup/before-retry broker reconciliation or prevention of uncertain duplicate sends. Legacy runtime wrapper is unreachable because imports are missing. |
| 9. Reconciliation → append-only execution audit (#133) | Base: `src/ticket_store/adapter.py:write_canonical` → `src/ticket_store/store.py:TicketStore.append_evaluation`; separate manual `src/v1_tickets/owner_decision.py:record_decision`. #133 adds `v2.build_*` / `TicketStore.append_*`, detailed below. No executor/reconciler calls these lifecycle APIs. | **MISSING** — correlated execution integration; V1 storage **IMPLEMENTED**, #133 storage **IMPLEMENTED only on its unmerged head** | Base persists evaluation/outcome, not an order lifecycle. `_finalize` reports `ticket_store_error` without changing informational decision; this is **not** execution fail-closed on audit failure. No pre-send durable audit requirement or binding of standing authority/check/send/reconciliation/notification. #133 rejects malformed identity/seal/account metadata but does not enforce trading decisions. | V1/V2 identical sealed writes are no-ops; conflicts/corrupt tails reject. Store is single-process-writer-per-root, not a cross-process order coordinator. Storage idempotency alone cannot recover an uncertain broker submission. |
| 10. Audit → Telegram execution result | Existing informational transport: `src/telegram_delivery/adapter.py:Sender._send`, `send_ticket`, `send_session_summary`; callback reply: `src/host_delivery/telegram_confirm.py:process_callback_update`. Execution-result builder/router: **none** | **MISSING** — broker-result reporting; informational delivery **IMPLEMENTED** | Missing credentials/allowlist or invalid scope blocks sending; persistence errors return failed; ambiguous network/5xx returns uncertain, not sent. `send_ticket` routes informational WATCH/INFO states, not confirmed/rejected/uncertain orders. Callback refusal text is not a broker result. No correlated fill/slippage/broker-ID result or #133 delivery writer. | SQLite claim commits before network; per-key locking prevents concurrent sends; crash-left pending becomes uncertain and is not automatically resent. Tested message safety, **not** order safety. No order-result outbox or notification-failure execution latch. |

### Callback duplication boundary

`telegram_confirm._accept_refusal` calls the side-effect-free `execution_handoff` before decision append; `handle_callback` can call it again after an ACCEPTED append; `_already_recorded` can call it on a repeated ACCEPTED tap. Current safety relies on the handoff remaining a broker-free stub. Replacing it with a sending function would **not** inherit exactly-once order safety from `owner_decision.record_decision`'s process/thread lock and one-decision-per-ticket rule.

## Five C14 limits: enforcement gap, not just matching numbers

Each row below is **MISSING as a C14 execution limit**, irrespective of the existence of a similarly named helper.

| Approved ceiling | Existing file:function and mismatch | Missing-input / duplicate-restart consequence |
|---|---|---|
| **0.5% DEMO equity per trade** | `src/sizing_math/risk.py:size_position` sizes to the percentage the caller supplies; it does not enforce a maximum 0.5%. `src/v1_tickets/manual_ticket.py:lot_size` supplies account **balance**, with manual-ticket policy 0.5%, not verified send-time DEMO equity. | Wrapper blocks missing balance/metadata/risk, but no execution supervisor validates equity, cap or actual order volume. No durable per-intent risk reservation. |
| **1 open position per instrument, across all strategies** | `src/sizing_math/position_guard.py:OpenPositionGuard.is_blocked` counts a local map **globally**, not broker positions per instrument; no C14 broker integration. | `runtime_state.store.JsonKeyValueStore._load_unlocked` returns `{}` for a missing file; the guard then sees zero positions. Local persistence is not evidence of an empty broker account; no atomic cross-strategy instrument reservation/reconciliation. |
| **5 trades per strategy per day** | `src/post_asian_pilot/governor.py:DailyTradeLedger.try_claim` is a pilot opportunity/slot ledger with its own caps/identity, not a C14 account trade counter. Reference code is **IMPLEMENTED_NOT_TESTED in this audit**; no promotion/wiring implied. | No order/fill accounting or unknown-intent reservation against the five-trade ceiling. Missing accounting and pending reset timezone must block, not reset a day's count to zero. |
| **1% strategy daily loss** | `src/sizing_math/daily_loss_guard.py:DailyLossGuard.is_blocked` compares realized **R** to -2R; `src/post_asian_pilot/governor.py:evaluate_daily_governor`, `evaluate_execution_eligibility` use pilot R/portfolio policies, not a broker-backed 1% daily-loss control. Pilot helpers were inspected, not exercised here. | Missing day record reads 0R; `record_trade_result` adds results without a stable fill/close event id. Replayed results can be double-counted; read/add/write is not an atomic event-ledger update. No approved C14 day boundary or percent-loss accounting. |
| **2% account-wide daily loss** | No C14 account-loss supervisor/function exists in the tracked execution path. Strategy-local R guard/statistics are not a substitute. | Missing account identity/equity/P&L/day policy must block. No persistent account halt, idempotent broker-event aggregation or restart recovery. |

Corrupt `JsonKeyValueStore` files raise `StateStoreCorrupted`, but a **missing** file is treated as empty. Its individual operations have in-process thread locks/atomic replacement, not cross-process coordination or a transactional broker-risk reservation. Do not borrow its historical UTC-day convention as the still-unapproved C14 reset timezone.

## #133 audit store: available API versus missing callers

At **#133 head only**:

| Record | Builder → append method (`src/ticket_store/`) | Current execution integration |
|---|---|---|
| DELIVERY | `v2.py:build_delivery` → `store.py:TicketStore.append_delivery` | **MISSING** — Sender's SQLite state is not automatically appended here. |
| OWNER_DECISION | `v2.py:build_owner_decision` → `store.py:TicketStore.append_owner_decision` | **MISSING** — manual decision JSONL is separate; no scoped standing-authority lifecycle adapter. |
| ORDER_EVENT | `v2.py:build_order_event` → `store.py:TicketStore.append_order_event` | **MISSING** — no check/send/result/reconciliation writer. |
| POSITION_CLOSE | `v2.py:build_position_close` → `store.py:TicketStore.append_position_close` | **MISSING** — no reconciled broker-close/P&L writer. |

The storage implementation passed **31 tests, 2 optional skips** in this audit. `v2.py:build_record` requires stable ticket/event references, aware UTC timestamp, cohort and record-kind identity; ORDER_EVENT requires SYSTEM/OWNER actor and `account=DEMO`, rejecting LIVE/missing account. Unknown optional measurements may remain null; a sealed record is not proof that execution-critical inputs were validated.

`store.py:TicketStore._append_event` validates existing/new V2 seals, scans date files for stable event identity, and delegates to `_append` for identical-write no-op, conflict rejection, flush/fsync and corrupt-tail rejection. Restart/retry is safe for the **same supplied event reference/content** under the documented single-process-writer restriction. A caller generating a new reference on retry bypasses event deduplication. There is no broker transition state machine, authorization validator, emergency-stop enforcement or transactional send/outbox protocol in this storage-only PR. Its ORDER_EVENT vocabulary does not contain an UNCERTAIN event; a reviewed representation of unknown outcomes/check/authorization evidence is still required, not an invented FILLED record.

## Notification-failure policy plug-in points — PENDING_OWNER must block

**Current state: MISSING.** C14/`OD1010-C6-RISK` leave notification-failure behavior and daily reset timezone pending; the C6 plan also leaves kill-switch semantics pending. No execution policy resolver enforces these decisions today. **An unset, unreadable, malformed or PENDING_OWNER execution-critical policy must block new automatic orders even when Telegram appears healthy.** C16's immediate-message scope and transport retry/backoff settings are different policies and cannot supply this decision.

| Point | Existing file:function / missing integration surface | Required behavior, not an implemented default |
|---|---|---|
| Admission / before any dispatch | `telegram_confirm.py:execution_handoff` is today's blocked boundary; future `src/assistant/commands.py:execute_command` is absent. | Resolve separately approved, versioned notification policy alongside scoped authority/day/stop policy; block on PENDING_OWNER/missing policy. Recheck immediately before irreversible send, not just at activation. |
| Pre-trade notification / receipt | `src/telegram_delivery/adapter.py:Sender._send`, `delivery_attempts`; future executor/outbox adapter is missing. | Durably correlate delivery intent/attempt to immutable order intent, using #133 `build_delivery`/`append_delivery` when integrated. Apply the approved policy to blocked/disabled/failed/uncertain or missing receipt. `duplicate` is not proof of delivery: inspect the persisted state. Do not choose continue-on-outage behavior here. |
| After send/reconciliation, before the next order | Future reconciler/result writer → #133 audit → Sender result router, all currently unwired. | Preserve true confirmed/rejected/uncertain broker outcome first; retain an auditable pending notification on delivery failure. Consult approved policy and halt further new orders while it is unresolved. Never erase a broker fill, pretend notification success, blindly resend an order, or initiate an unauthorized close as notification recovery. |
| Startup / retry / operator recovery | `Sender.list_uncertain`, `_recover_pending` exist for messages; broker-intent reconciliation, durable result outbox and execution halt/recovery integration are missing. | Recover outstanding order intents and delivery states before permitting another dispatch. Missing/corrupt policy/accounting/audit or unresolved broker outcome blocks; notification retry cannot implicitly retry the order. Recovery/override must follow separately recorded owner policy, not an agent-invented default. |

Keep these hooks in canonical execution orchestration: the informational Telegram adapter and storage modules must remain unable to call broker mutation directly.

## Validation and limits of evidence

Environment: Linux sandbox, Python 3.11.2, pytest 8.3.5; no real Windows MT5 terminal or broker/Telegram acceptance run. Dependencies were installed only into ignored `.venv` using repository-pinned versions. Initial base-test collection lacked `smartmoneyconcepts`; after installing pinned 0.0.27 without replacing the pinned NumPy/Pandas stack, the suite below passed. No source workaround was made.

Base regression command (Telegram credentials/enabling variables removed):

```bash
env -u TELEGRAM_BOT_TOKEN -u TELEGRAM_CHAT_ID -u TELEGRAM_DELIVERY_ENABLED \
  -u TELEGRAM_OWNER_CHAT_IDS PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python -m pytest -q -rs -m 'not slow and not live_mt5' \
  tests/test_ready_authority_owner_binding.py \
  tests/test_d6_ready_authority.py tests/test_d6_per_symbol_verification.py \
  tests/test_manual_ticket_build.py tests/test_manual_ticket_authority.py \
  tests/test_crypto_cfd_proposal_policy.py tests/test_telegram_confirmation.py \
  tests/test_manual_ticket_owner_decision.py \
  tests/test_ticket_store_v1.py tests/test_ticket_store_grader.py \
  tests/test_telegram_delivery_adapter.py \
  tests/test_ticket_delivery_concurrency_and_restart.py \
  tests/test_ticket_delivery_execution_boundary.py \
  tests/test_actionability_and_canonical_ticket.py \
  tests/test_v1_sizing_math_boundary.py
```

**267 passed in 9.52s.** Covers fixture READY record matching/mismatch, production OFF, ticket risk/cost boundaries and missing keys, callback refusal/dedup/concurrency/zero-order sentinels, V1 store conflict/corruption, canonical outcomes and message concurrency/restart/uncertainty. Positive READY tests use fixture-only records/config; they do not authorize production or prove six-instrument admission.

#133 independent storage check (no branch checkout or merge):

```bash
REPO="$PWD"
scratch=$(mktemp -d /tmp/agp-c14-pr133-XXXXXX)
git archive 6e4bcba9ea94112172c79d653ca30bc4de9c2c15 \
  src/ticket_store scripts/ticket_history.py tests/test_ticket_store_v2.py \
  tests/fixtures/ticket_store_v1 | tar -x -C "$scratch"
(cd "$scratch" && env -u TELEGRAM_BOT_TOKEN -u TELEGRAM_CHAT_ID \
  -u TELEGRAM_DELIVERY_ENABLED PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$scratch/src" "$REPO/.venv/bin/python" \
  -m pytest -q -rs tests/test_ticket_store_v2.py)
```

**31 passed, 2 skipped in 0.49s.** Skips: optional PyArrow Parquet and DuckDB parity/export paths unavailable. Core lifecycle validation, idempotency across date files, conflicts/corruption/seals, threaded duplicate writes, V1 byte preservation and SQLite history/cohort checks passed. No lifecycle execution integration or host behavior was tested.

Tracked-file/function inventory and `git grep` over `src`, `packages`, `apps`, `scripts`, `mt5` found no actual canonical `execute_command`, `order_check`/`order_send` call or broker `reconcile` definition. Surviving wrappers/comments and historical status claims are not current code. C11's host-only execution artifacts remain `UNTRACKED_HOST` until reviewed into the repository; they cannot upgrade this result.

## MISSING hops — summary (9 lines)

1. Shared C14 immutable executable-ticket/READY admission beyond the implemented FX READY gate.
2. Scoped, expiring/revocable standing DEMO authority and send-time emergency-stop enforcement.
3. Unified enforcement/accounting/reservation for all five C14 risk limits, with approved daily reset policy.
4. Verified fresh execution-time cost/sizing/margin gate; ticket-only checks do not suffice.
5. Broker `order_check` request/result validation bound to the eventual send.
6. Canonical `assistant.commands.execute_command` → DEMO-only `order_send` dispatch and durable order claim.
7. Broker reconciliation/startup recovery and no-blind-retry handling of unknown outcomes.
8. #133 correlated append-only authorization/check/send/reconciliation/close/delivery audit integration.
9. Correlated Telegram execution results/outbox and notification-failure execution policy; **PENDING_OWNER must block**.
