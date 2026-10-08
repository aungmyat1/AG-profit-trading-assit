---
class: evidence
state: DESIGN
owner_reviewed: null
review_by: null
---
# AGP Host Ticket Delivery R1 (FAST) — canonical FX ticket + delivery pipeline (2026-10-08)

Mission `AGP_HOST_TICKET_DELIVERY_R1_FAST` (P0). Shortest safe path: read-only VT Markets MT5
Demo candles → deterministic canonical FX evaluation → durable ticket records → canonical
delivery → delivery/session journals → owner decision capture. This is an **informational
ticket pipeline**, not an execution system. No strategy logic, session definition,
entry/SL/TP formula, risk rule, eligibility rule, economic threshold or verification state was
changed. `demo_authorized` and `live_authorized` remain `false`; `order_send`, `order_check`
and every broker mutation path remain uncalled (0 broker mutations).

## Snapshot

| Field | Value |
| --- | --- |
| Base | `main` @ `ed0252dbf21da73231e7a1f89f13e0ccc5e6210b` |
| Work branch | `arena/ca7a6ec4-ag-profit-trading-assit` |
| Code + offline tests | COMPLETE on the branch |
| Full offline suite | `1338 passed, 3 skipped` (no `cogapp`) / `1339 passed, 2 skipped` (with `cogapp`, as CI's docs job runs it); identical in deterministic **and** randomized order |
| `scripts/host/verify_objective.py` | `RESULT: PASS` |
| Windows host acceptance | **NOT_EVALUATED** — no authorized Windows MT5 host or open window in this session; Linux fixtures were not substituted for live evidence |
| Telegram live acceptance | **NOT_AUTHORIZED** — transport mocked in every test; no destination approved by the owner |
| Broker mutations | 0 |

## What changed

- **Delivery taxonomy (`src/telegram_delivery/adapter.py`, derived from PR #60).** The adapter now
  carries the full canonical taxonomy, including the previously unsupported `INFO_ONLY_SUPPRESSED`,
  and routes it to `summary_only`: a suppressed READY (production READY authority OFF, reason
  `READY_AUTHORITY_OFF_D6`) is persisted and counted in the session summary but is never an
  immediate alert. `_known_decision` fails closed on an unknown decision string, and unknown or
  incompatible states are recorded through `compatibility_errors()` instead of being silently
  dropped or promoted.
- **Delivery attempts and session summaries.** `delivery_attempts(kind, identities)` gives an
  audited per-identity attempt record, and `build_session_summary` / `render_session_summary` /
  `send_session_summary` produce a deterministic per-session digest (one typed terminal outcome
  per instrument × session, explicit `Delivery enabled:` line, explicit
  `Missing scheduled evaluations (MISSED):` line, persistence-failure and compatibility-error
  lines). Summaries are a separate delivery kind, deduplicated by session key and disabled by
  default; missing data is reported as `MISSED`, never rewritten into `NO_TRADE`.
- **Persistence verification (`scripts/host/canonical_fx_delivery.py`).** `_verify_persisted_result`
  re-reads the ticket store after a write and reports `ticket_store_status`; a store failure is
  surfaced as `delivery_state="persistence_failed"` and never as a delivered or dropped ticket.
- **Scheduled canonical FX path.** `scripts/host/live_candles_smoke.py --mode fx --canonical`
  preserves `run_manual_jobs`, evaluates only the active frozen FX cycle through `daily_evaluator`,
  appends canonical results to `TICKET_STORE_V1`, and writes the separate durable
  delivery/session journals. `--mode fx` without `--canonical` stays the unscheduled legacy
  compatibility path. Restart/idempotency is covered: an interrupted cycle re-runs without
  duplicate tickets or duplicate alerts, and one typed terminal outcome is recorded per
  instrument × session.
- **LSMC alert dedup ledger (`src/host_delivery/lsmc_alert_dedup.py`).** `AlertLedger` +
  `deliver_once` record the attempt before the network call and resolve it afterwards, so a
  `DELIVERY_UNCERTAIN` or `SENT` outcome is never blind-retried, a definite rejection may be
  retried, and a confirmation identity that cannot be derived fails closed as
  `IDENTITY_UNAVAILABLE`. No network call happens under the main journal transaction lock.
- **Typed transport outcome (`src/host_delivery/telegram_message.py`).** `TelegramSendError`
  carries `delivery_state` ∈ {`BLOCKED`, `RETRYABLE_REJECTED`, `DELIVERY_UNCERTAIN`,
  `DELIVERY_FAILED`}: missing credentials or an unauthorized recipient fail closed as `BLOCKED`,
  HTTP 429 is `RETRYABLE_REJECTED`, 5xx/408/timeout stay `DELIVERY_UNCERTAIN`, other non-OK
  responses are `DELIVERY_FAILED`. Rendering is tick-normalized and uses the configured broker
  symbol (`_configured_broker_symbol`, `_display_record`) so crypto alerts carry correct metadata
  (PR #48 review finding).
- **Legacy journal contract preserved.** The legacy `ticket_delivery/delivery_status` rows keep
  their frozen `status` vocabulary (`SENT` / `NOT_SENT_POLICY` / `FAILED` / `ERROR`); the typed
  transport outcome is reported in `logs/telegram.log` only
  (`TELEGRAM_SEND_DELIVERY_UNCERTAIN`, `TELEGRAM_SEND_DELIVERY_FAILED`, …). No durable row schema
  was changed.
- **Host task wiring and docs.** `install_tasks.ps1` / `verify_tasks.ps1` install and verify the
  canonical FX task alongside the crypto and LSMC tasks; `GO_LIVE.md`, `verify_objective.py` and
  `live_eval_smoke.py` were updated to match. `CANONICAL_OVERRIDE` is the literal
  `config/local/canonical_ticket_delivery.yaml`, and no override file is committed
  (`config/local/` stays gitignored).
- **Evidence integrity.** The four stale/ambiguous artifacts and the stale mission label in
  `docs/status/AG_MARKET_DATA_CONTRACT_R2_2026-10-08.md` were reconciled and quarantined in
  [AGP_EVIDENCE_INTEGRITY_R1](AGP_EVIDENCE_INTEGRITY_R1.md).

## Delivery scope (unchanged authority)

`verify_objective.py` reports `telegram_report_scope: ticket=['READY'] lsmc=['OPPORTUNITY']
canonical_opt_in=True` and `safe_delivery_default: mode=ARCHIVE_ONLY committed_override=False
canonical_override=False`. Immediate sends remain limited to `TICKET_READY` and
`LSMC_OPPORTUNITY` on the legacy host path; canonical `WATCH_READY` / `INFO_ONLY_*` delivery sits
behind a default-OFF local flag plus recipient authorization and the environment gate; session
summaries are permitted as their own kind and are also default-OFF. Production READY authority is
OFF, so every canonical decision in this build is `INFO_ONLY_SUPPRESSED` and produces 0 immediate
sends (see `tests/test_canonical_fx_delivery.py::test_suppressed_ready_is_persisted_but_never_alerted`).
The D6 pause is carried on `main` independently of PR #50 (still open/draft): `config/v1_tickets/ready_authority.yaml`
and `src/v1_tickets/{ready_authority,actionability}.py` are byte-identical to `main`, and
`ready_authority('ST_ASIAN_SWEEP_5R_V1')` returns `(False, 'READY_AUTHORITY_OFF_D6')`.

## Offline test evidence

- Full suite: `python -m pytest -q` → `1338 passed, 3 skipped` in this sandbox (`cogapp` absent) and
  `1339 passed, 2 skipped` after installing `cogapp`, which is how CI's docs job runs it. The two
  remaining skips are the live Binance network smoke and the real `MetaTrader5` package: no
  live-host path was exercised offline.
- New/changed focused suites: `tests/test_canonical_fx_delivery.py` 29 passed;
  `tests/test_telegram_delivery_adapter.py` 70 passed; `tests/test_lsmc_alert_dedup.py` 6 passed;
  `tests/test_telegram_message_metadata.py` 5 passed; `tests/test_mt5_provider_integration.py`
  29 passed; `tests/test_host_go_live_kit.py` 71 passed, 1 skipped.
- Suppression evidence: `tests/test_d6_ready_authority.py` + `tests/test_d6_actionability_suppressed.py`
  + `test_suppressed_ready_is_persisted_but_never_alerted` → 22 passed (no `ASIAN_LONDON`
  `ST_ASIAN_SWEEP_5R_V1` READY can be emitted; the shadow decision never reaches Telegram scope).
- Delivery-gate evidence: `tests/test_host_go_live_kit.py -k "telegram or notify"` → 15 passed;
  `tests/test_canonical_fx_delivery.py -k "sender or disabled or unauthorized or repo_delivery"` → 5 passed.

## Behavior changes an owner must note

1. The session summary no longer reports `owner_decision_counts`. Nothing in this build writes
   `outcome_kind == "OWNER_DECISION"` rows for canonical tickets, so the field was always 0 and
   was removed rather than reported as a misleading zero. Owner decisions continue to use the
   existing append-only mechanism in `src/v1_tickets/owner_decision.py` (preserved, untouched).
2. `INFO_ONLY_SUPPRESSED` is now a first-class supported state and is excluded from the
   per-ticket immediate-alert selection (`test_per_ticket_selection` narrowed accordingly).
3. Telegram failure logging is typed (`TELEGRAM_SEND_<delivery_state>`) instead of the single
   `TELEGRAM_SEND_FAILED` string.

## Known limitation recorded honestly

An in-session extension of the owner-decision capture path (a canonical capture script, a ticket
store decision module and its test) was deleted by an explicit `rm -f` before it was ever
committed, so its content is unrecoverable. A7 is therefore delivered as *existing append-only
owner-decision mechanism preserved*, not extended. No other file loss occurred; the reflog,
stash list and history were checked to confirm the deletion was the only cause.

## Corrections caught before commit

1. `scripts/host/live_candles_smoke.py::_notify` first shipped the typed `delivery_state` as the
   legacy journal `status`, which broke the frozen row contract pinned by
   `tests/test_manual_ticket_scan_records.py::test_telegram_failure_never_hides_scan_records_and_is_traced`
   (`FAILED` / `ERROR`). The journal vocabulary was restored and the typed outcome moved to
   `logs/telegram.log` only.
2. `scripts/host/install_tasks.ps1` first inserted `Canonical = $true` between `Mode` and
   `Minutes`, which silently broke the positional parse in `scripts/docs/build_context_pack.py`
   and would have published a CONTEXT_PACK listing zero scheduled tasks. The rows were reordered
   (`Name; Mode; Minutes; Canonical; Offset`) and the ordering is now pinned by assertions in
   `tests/test_host_go_live_kit.py` and `tests/test_canonical_fx_delivery.py`;
   `build_context_pack.py --check` reports `UP_TO_DATE`.
3. `tests/test_telegram_delivery_adapter.py::test_bot_api_plain_payload` had lost its
   `chat_id`/`timeout`/endpoint assertions (they only existed in the newer HTML-escaping test);
   both were restored, so the transport contract is asserted on both paths.

## Dependencies

- `src/telegram_delivery/` is derived from **PR #60** (head `80dd66a1`): `__init__.py` and 12 of 13
  fixtures are byte-identical to `origin/pr-60`; `adapter.py` and its test carry this mission's
  changes. #60 must be frozen (or this branch rebased onto it) before merge.
- PR **#48** (head `256774e0`) review findings addressed: crypto symbol metadata fixed; this
  document plus the new dated `PROJECT_STATUS.md` section provide the rolling status update.
- PR **#50** remains open/draft/unmerged; the D6 pause it carries is already on `main`.

No authority is granted by this document: no Demo execution, no Live execution, no economic edge
claim (`EDGE_VERIFIED=FALSE`), and no Windows host acceptance.
