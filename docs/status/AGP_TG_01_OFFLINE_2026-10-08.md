# AGP-TG-01 — 2026-10-08

STATUS_EVIDENCE: UNIT_TESTED, offline Linux. Live Telegram deferred. No broker,
MT5 import, market evaluation, execution authority or scheduler wiring in adapter.

## Canonical contract inspected

Source: `src/v1_tickets/canonical_ticket.py`, `AG_CANONICAL_TICKET_V1`.
Decisions: WATCH_READY, INFO_ONLY_STALE, INFO_ONLY_INSUFFICIENT_REMAINING_R,
INFO_ONLY_POLICY_UNRESOLVED, NO_TRADE, EXPIRED, MISSED, BLOCKED,
INSUFFICIENT_DATA, OUT_OF_SESSION. Presentations: WATCH_READY, INFO_ONLY, OTHER.
INFO_ONLY_POLICY_UNRESOLVED currently maps to OTHER upstream; this adapter preserves it.
There is no literal STALE or INFO_ONLY decision and no status field;
`decision` supplies the ticket_id + status dedupe key.

Top-level fields: schema, label, ticket_id, proposal_id, presentation, decision,
reason_code, instrument, venue, session, session_date, strategy_id,
strategy_version, logic_status, economic_status, economic_edge, direction,
context, poi, fact_provenance, trigger, prices, risk, freshness, actionability,
setup_status, proposal_eligibility, execution_authorization, demo_authorized,
live_authorized, reason_codes, created_at, trigger_at, expires_at, send_timestamp,
structure_visual, checklist.

Nested fields:
- context: d1_context, h1_context, structure, poi.
- fact_provenance: those context keys, each with status/source.
- trigger: setup, trigger_timestamp, trigger_bar_close_utc.
- prices: entry_reference, current_send, sl, tp1, tp2 and their `_raw` equivalents.
- risk: risk_distance, initial_R_tp1/tp2, remaining_R_tp1/tp2.
- freshness: status, age_s, limit_s, policy.
- actionability: version, decision, reason, valid_at_trigger, actionability_at_send,
  policy_id/version/status/reason, min_remaining_r, policy_source_identity.
- checklist entries: phase, description, status.

SCHEMA_GAP: no `levels` field. The ladder uses the existing formatted `prices`
fields verbatim, in fixed TP2/TP1/NOW/ENTRY/SL order. It does not estimate POI,
sort using market calculations, reuse `structure_visual` or fill missing values.
Remaining R exists; null/missing values print `SCHEMA_GAP: risk.remaining_R_tp*`.
No literal STALE status is added; INFO_ONLY_STALE is preserved. Missing rendered
facts are explicitly marked SCHEMA_GAP, never computed.

## Operation and limits

Standalone API: `telegram_delivery.adapter.render_ticket`, `render_summary`,
`Sender(path).send_ticket` and `.send_summary`. No existing sender/scheduler changed.
Environment defaults: `TELEGRAM_DELIVERY_ENABLED=false`; only `true` enables.
`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` and comma-separated
`TELEGRAM_OWNER_CHAT_IDS` are required. Owner membership is exact. Keep the same
durable SQLite path across restarts; do not use an ephemeral container filesystem.

Per-ticket sends: WATCH_READY; INFO_ONLY presentation with INFO_ONLY_* decision.
NO_TRADE, EXPIRED and MISSED remain summary-only even though upstream presents
those as INFO_ONLY. Every input row and reason appears in a single-session summary.
Summary identity is session_date + session, persisted once, including across restart.
Caller supplies the complete final session batch; subsequent batches do not replace it.
Messages above Telegram's 4096 UTF-16 unit limit fail closed without truncation/splitting.
ASCII ladder is aligned plain text; no Telegram parse_mode or inline buttons are sent.
Telegram clients may display plain text with proportional fonts.

SQLite commits a pending claim before network, then marks acknowledged sends sent.
HTTP 429/500/502/503/504 retry at 1s/2s (default three attempts).
Ambiguous failures (timeout after the send attempt, crash-equivalent transport errors)
persist state DELIVERY_UNCERTAIN while keeping the dedupe claim: restart does not
auto-resend. The next session summary lists uncertain identities. Owner-only CLI
`python -m telegram_delivery.adapter resend --ticket-id X --force --store PATH
--ticket-file FILE --actor WHO` may deliver once; actor and timestamp are logged.
Token values are never logged or rendered. Exhausted explicit HTTP retries remain
failed without auto-resend. Telegram sendMessage has no server idempotency key.
No exception text/token URL is logged. Transport is injectable for offline tests.

Dependency: plain HTTPS Telegram Bot API via Python standard library urllib/json/
sqlite3; no third-party delivery dependency. Verified interpreter CPython 3.12.14,
PSF License Version 2 (bundled SQLite public domain). Existing Python >=3.10 support
unchanged. Bot API is hosted and has no client package version to pin; offline
verification runtime is pinned in `tests/fixtures/telegram_delivery/python-version.txt`.

## Verification

`.venv/bin/python -m pytest -q tests/test_telegram_delivery_adapter.py tests/test_actionability_and_canonical_ticket.py tests/test_ticket_delivery_execution_boundary.py`

64 adapter+regression tests targeted (41 adapter including UNCERTAIN/force-resend,
23 existing canonical/boundary). Golden files cover all ten decisions plus complete summary.
Golden files cover all ten decisions plus complete summary. Transport tests are fakes;
no Telegram, broker or market-data network request occurred. The full regression
baseline was not changed or claimed. No live authorization granted.
