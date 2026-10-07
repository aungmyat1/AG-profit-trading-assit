# AGP-TG-01 — 2026-10-08

STATUS_EVIDENCE: UNIT_TESTED, offline Linux. Live Telegram deferred. No broker,
MT5 import, market evaluation, execution authority or scheduler wiring in adapter.

## Canonical contract inspected

Source: `src/v1_tickets/canonical_ticket.py`, `AG_CANONICAL_TICKET_V1`.
Decisions: WATCH_READY, INFO_ONLY_STALE, INFO_ONLY_INSUFFICIENT_REMAINING_R,
INFO_ONLY_POLICY_UNRESOLVED, NO_TRADE, EXPIRED, MISSED, BLOCKED,
INSUFFICIENT_DATA, OUT_OF_SESSION. Presentations: WATCH_READY, INFO_ONLY, OTHER.
INFO_ONLY_POLICY_UNRESOLVED maps to OTHER upstream; delivery uses its existing decision,
so every INFO_ONLY_* decision sends individually.
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

Per-ticket sends: WATCH_READY and every canonical INFO_ONLY_* decision, regardless of presentation.
NO_TRADE, EXPIRED and MISSED remain summary-only even though upstream presents
those as INFO_ONLY. Every input row and reason appears in a single-session summary.
Summary identity is session_date + session, persisted once, including across restart.
Caller supplies the complete final session batch; subsequent batches do not replace it.
Messages above Telegram's 4096 UTF-16 unit limit fail closed without truncation/splitting.
Ticket and summary bodies use escaped HTML <pre> with parse_mode=HTML for monospace
levels. An explicit HTML-format rejection falls back to the original plain text;
no fallback follows ambiguous failures or unrelated HTTP errors. No inline buttons.

SQLite commits a pending claim before network, then marks acknowledged sends sent.
HTTP 429/500/502/503/504 retry at 1s/2s (default three attempts).
Ambiguous failures (timeout after the send attempt, crash-equivalent transport errors)
persist state DELIVERY_UNCERTAIN plus the exception *class name* (never the message)
while keeping the dedupe claim: restart does not auto-resend. The next session
summary lists uncertain identities. Owner-only CLI
`python -m telegram_delivery.adapter resend --ticket-id X --force --store PATH
--ticket-file FILE --actor WHO` is allowed only when state is DELIVERY_UNCERTAIN.
`--actor` is an audit label, not authentication. A DELIVERED row is refused unless
`--allow-duplicate` is also given; refusals are logged. Token values are never
logged or rendered. Exhausted explicit HTTP retries remain failed without auto-resend.
Telegram sendMessage has no server idempotency key. No exception text/token URL is
logged. Transport is injectable for offline tests.

Dependency: plain HTTPS Telegram Bot API via Python standard library urllib/json/
sqlite3; no third-party delivery dependency. Verified interpreter CPython 3.12.14,
PSF License Version 2 (bundled SQLite public domain). Existing Python >=3.10 support
unchanged. Bot API is hosted and has no client package version to pin; offline
verification runtime is pinned in `tests/fixtures/telegram_delivery/python-version.txt`.

## Verification

`.venv/bin/python -m pytest -q tests/test_telegram_delivery_adapter.py tests/test_actionability_and_canonical_ticket.py tests/test_ticket_delivery_execution_boundary.py`

65 focused tests: 42 adapter (UNCERTAIN class-name, force vs DELIVERED refuse,
`--allow-duplicate`) plus 23 existing canonical/boundary. Full default suite
1162 passed, 4 skipped (live_mt5/slow deselected). Golden files cover all ten
decisions plus complete summary.
Golden files cover all ten decisions plus complete summary. Transport tests are fakes;
no Telegram, broker or market-data network request occurred. The full regression
baseline was not changed or claimed. No live authorization granted.

## Rebase verification — 2026-10-08

Rebased onto main `96f4aa6a8470f86b876294bfa27b89989467842d`. Preserved the
DELIVERY_UNCERTAIN and owner-resend review changes. Decision-based routing fixes
policy-unresolved delivery; forced resend also keeps negative/data decisions summary-only.
A two-process SQLite restart test sends once then returns duplicate with zero
transport calls. Missing canonical prices/risk print SCHEMA_GAP without estimates.
No strategy/session/threshold/authority changes relative to that main snapshot.

Focused command: `python -m pytest -q tests/test_telegram_delivery_adapter.py tests/test_actionability_and_canonical_ticket.py tests/test_mt5_candles_readonly.py tests/test_mt5_provider_integration.py tests/test_stale_gate_trigger_close.py tests/test_ticket_delivery_execution_boundary.py`

135 passed, zero skips (47 adapter tests). Full default suite result recorded below.
Open review: draft CodeRabbit review has not run; live Telegram remains unverified;
plain-text ladder alignment is client-font dependent; ambiguous-delivery recovery
requires owner investigation and a deliberate forced resend.

Full default suite: `python -m pytest -q` — **1191 passed, 2 skipped,
1 Starlette deprecation warning**, 23.39s, Linux CPython 3.12.14. The default
slow-marker exclusions remain unchanged. Initial restricted-sandbox run stalled
in the existing FastAPI/AnyIO local event loop; diagnostic passed with local
network permission and the complete suite was rerun with that permission.
The two live-MT5 skips are deferred host checks, not passes.

## HTML and ambiguous delivery — 2026-10-08

Bodies escape &, < and > inside <pre>. HTML parse rejection (HTTP 400 or explicit
Bot API error) falls back to plain text. Timeout, ConnectionResetError and a
URLError wrapping reset after request dispatch consume the ticket_id + decision
claim as DELIVERY_UNCERTAIN, without retry or fallback. Restart returns duplicate;
the next session summary lists `possibly undelivered: <ticket_id>`. Unit tests
inspect dispatched HTTP payloads and durable SQLite keys. No live sends.
Focused canonical/market-data/boundary suite: 141 passed (53 adapter tests).

Final full default suite: `python -m pytest -q` — 1197 passed, 2 live-MT5
skips, 1 existing Starlette warning, 23.31s. Local network permission permits
FastAPI/AnyIO test-client sockets; adapter requests are mocked. Strategy, session,
threshold and authority files are unchanged by this update.
