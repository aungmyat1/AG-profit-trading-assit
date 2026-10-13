---
class: evidence
state: DESIGN
owner_reviewed: null
review_by: null
---
# AGP-C18-R2 — Three-strategy observational tickets and Telegram reporting (implementation plan, 2026-10-13)

**Status:** plan plus PR A in progress. **Authority:** this plan adds observational reporting only.

**Guarantees:**
- No READY expansion.
- No demo/live flag, registry or `ready_authority.yaml` change.
- No order_check/order_send.
- No broker mutation.
- A strategy is never marked LOGIC_VERIFIED because its reporting works.

## 1. Goal

ASW (`ST_ASIAN_SWEEP_5R_V1`), LSMC (`ST_LARGE_SMC_V1`) and CCFD (`ST_CRYPTO_CFD_SWEEP_RETEST_V1`) each produce scope-specific observational tickets and Telegram reports while logical verification continues:
- priced candidates
- BLOCKED diagnostics
- WATCH alerts
- NO_OPPORTUNITY summaries
- a daily per-strategy summary

Execution authority and frozen strategy identities are preserved.

## 2. Owner decisions (2026-10-13, chat)

| # | Decision |
|---|---|
| D1 | Immediate REPORT_ONLY sends: priced candidates, BLOCKED diagnostics, LSMC WATCH/OPPORTUNITY. Also NO_OPPORTUNITY session summaries and a daily per-strategy summary. This resolves C16 for REPORT_ONLY messages and is recorded in the tracked config plus the decision register. The local sender policy is never widened beyond tracked authority. |
| D2 | ASW: evaluate all 8 FX scopes on live data in a separate read-only lane. Unverified scopes report priced REPORT_ONLY candidates. EURUSD × ASIAN_LONDON v1.1.2 stays SUSPENDED and gets a BLOCKED diagnostic with no prices. The S1 path is unchanged. |
| D3 | CCFD: run the existing v1.0.0 `run_crypto_cfd_windows` as a REPORT_ONLY lane in host crypto mode. |
| D4 | LSMC: the host runner passes the live bid/ask to `evaluate_snapshot`. The engine is unchanged. |

## 3. Before-state (origin/main `761f00f`)

| Family | Evaluated | Archived | Telegram |
|---|---|---|---|
| ASW | LIVE: only S1 (GBPUSD × ASIAN_LONDON, READY ON via #184). The other 7 scopes are BLOCKED `LOGIC_SCOPE_NOT_VERIFIED` before any data fetch, with no prices. | Canonical ticket + TICKET_STORE | No immediate ticket (WATCH_READY is not in the immediate scope). Session summaries only. |
| LSMC | All 6 symbols. A stop is possible only for EURUSD/GBPUSD **LONG**. SHORT always gets `MISSING_SPREAD` because no bid/ask is passed. | `LSMC_WATCH-*` transitions (ARCHIVE_ONLY) | OPPORTUNITY only, through the legacy sender. No BLOCKED diagnostic: a missing C10 is collapsed to `REJECT_NO_STOP`. |
| CCFD | Nothing is scheduled. `run_crypto_cfd_windows` (v1.0.0) is unused. | None in production | The crypto summary shows `NO_RECORD`. |

## 4. Hard constraints

- **Identity-bound files are not edited.** New code lives in new modules or non-identity files.
  - ASW (S1 identity `d7a8ebe5…`): `strategy_engine/engine.py`, `strategy_engine/session/*`.
  - LSMC: `large_smc_watch/*`.
  - CCFD `authority.ADAPTERS` files: `crypto_cfd.py`, `manual_ticket.py`, `logic_gate.py`, `ccfd_logic_gate.py`, `crypto_cfd_policy.py`, and the listed configs.
- **PR #186 (v1.1.3 engine) is not touched.** This work does not modify `fx.py` or `authority.py`. v1.1.3 stays separately identified.
- **Routing:** every observational ticket has `scope_route = REPORT_ONLY`. Evaluation gates and execution gates are separate: a report-lane ticket never enters the READY ticket path, `src/demo_execution/` or `execution/`.
- **Delivery:** archive first, then intent, then the existing `telegram_delivery.adapter.Sender` (SQLite ledger: sent / failed / uncertain / disabled / duplicate, no automatic retry).
- **Resource governance:** take the R1 lock for test and replay runs. When the gate is BLOCKED_RESOURCE, nothing starts.
- **Branches:** one PR per concern, never force-push.

## 5. Work packages

### PR A — Scope-aware canonical ticket (branch `feat/c18-scope-canonical-ticket`)
- `v1_tickets/scope_status.resolve_ticket_scope(strategy_id, version, symbol, session, direction)` resolves status at the **exact** version, symbol, session and direction (CCFD).
  - A version outside the pinned scope gives `VERSION_NOT_IN_SCOPE:<v>`.
  - An undeclared symbol or session gives `SCOPE_NOT_DECLARED`.
  - CCFD: a direction outside the recorded branches gives `DIRECTION_NOT_IN_SCOPE`. A verified status with no recorded window gives `WINDOW_NOT_IN_SCOPE`.
  - It never borrows family-level status.
- `AG_CANONICAL_TICKET_V1` gains **additive** fields:
  - `scope_verification_status`
  - `scope_route` (always `REPORT_ONLY`)
  - `scope_reason`
  - `verification_identity`
  - `candidate_signal_id` = `id@version|symbol|session|direction|signal_time`
  - `report_class` ∈ {READY_TICKET, CANDIDATE, BLOCKED, NO_OPPORTUNITY, DATA_ERROR, OUT_OF_SESSION}
- Compatibility:
  - The schema id is unchanged. The ticket store reads named keys only.
  - `canonical_hash` covers the new fields, so new records hash differently. Existing records are untouched.
- Telegram `footer()` adds ASCII `scope:` and `report_class:` lines when present. It rejects any route other than REPORT_ONLY. Older tickets render unchanged.
- Tests: `tests/test_canonical_ticket_scope_fields.py`.

### PR B — Strategy adapters (read-only evaluation lanes; new modules)
- **ASW `src/reporting/asw_lane.py`:**
  - Calls the existing `fx.build_fx_ticket(..., strategy_path=SCOPED_CANDIDATE_PATH, runtime_scope=False)`, so v1.1.2 runs read-only for every scope other than S1.
  - EURUSD × ASIAN_LONDON: SUSPENDED gives a BLOCKED diagnostic with no evaluation.
  - S1 stays on the canonical path, unchanged.
  - Invoked from `canonical_fx_delivery.run_report_lane()` after `run_canonical_fx_cycle`, with the same provider and no extra MT5 attach.
- **LSMC `src/reporting/lsmc_lane.py`:**
  - On a `WatchTracker` transition:
    - DEVELOPING/NEAR_POI → WATCH.
    - OPPORTUNITY with C10 stop and C11 target present, and passing the gate → priced CANDIDATE.
    - REJECTED → BLOCKED with the specific `stop_reason` or target reason, and no invented stop.
    - DATA_ERROR/STALE → DATA_ERROR.
  - Bid/ask are passed in `live_candles_smoke._watch_once` and the crypto feed.
  - The legacy `format_alert` stays, so the golden test still passes.
- **CCFD `src/reporting/ccfd_lane.py`:**
  - In-window crypto mode calls the existing archive-first `run_crypto_cfd_windows` (v1.0.0) through a read-only MT5 feed adapter, then maps the rows to canonical observational tickets.
  - Scope is per symbol and direction. Window-level verification waits for C17 registry admission.

### PR C — Telegram reporting policy and summaries
- Tracked policy:
  - `config/ticket_delivery.yaml` `immediate_send_scope`: `REPORT_CANDIDATE`, `REPORT_BLOCKED`, `REPORT_WATCH`.
  - `telegram_delivery/scope_policy.py` accepts the new scopes.
  - Decision register row `OD1013-C18-REPORT-SCOPE`.
  - Local override can still only narrow.
- `Sender.send_report` (kind `report`, identity = `candidate_signal_id` or ticket id + `report_class`).
- ASCII renderers: compact alert, detailed candidate report (existing ASCII ladder), BLOCKED diagnostic. All end with `REPORT ONLY - NOT AN ORDER | EXECUTION: DISABLED`.
- Summaries:
  - NO_OPPORTUNITY lines in the existing session and crypto summaries.
  - New daily per-strategy summary (`DAILY_REPORT`, once per day through `_process_due_summary`).
- Delivery evidence: a RESULT event per message (sent / failed / uncertain / disabled, `telegram_message_id`). An attempted send is never reported as delivered.

## 6. Tests and evidence

| # | Proof | Where |
|---|---|---|
| 1 | All three families generate candidate or status records | lane tests, one per family |
| 2 | Unverified scopes evaluate without reaching order APIs | AST import bans on `src/reporting/*` (no `execution`, `demo_execution`, `mt5.management_gateway`, `order_send`, `order_check`) |
| 3 | Per-scope labels are exact | `test_canonical_ticket_scope_fields.py` |
| 4 | Missing data and invalid geometry fail closed | lane tests: DATA_ERROR, zero risk, inverted targets, stale, wrong version/hash |
| 5 | Telegram messages are approved ASCII | renderer tests (`isascii`), golden LSMC test kept |
| 6 | Duplicate and uncertain deliveries are not retried | Sender ledger tests: duplicate, failed, uncertain, restart |
| 7 | S1 behaviour is unchanged | S1 decision and delivery path tests; S1/LSMC/CCFD identity digests pinned |
| 8 | No authorization change | registry, `ready_authority.yaml`, demo/live flags diffed unchanged |

Regression suites:
- `test_canonical_fx_delivery`, `test_actionability_and_canonical_ticket`, `test_telegram_delivery_adapter`, `test_ticket_store_v1`
- `test_d6_*`, `test_s1_activation`, `test_scope_status`
- `test_lsmc_*`, `test_crypto_cfd*`, `test_ccfd_*`, `test_host_go_live_kit`

After those: ruff on changed files, the generated-files strict check, then full CI.

**Acceptance is reported in two separate tiers:**
- **Synthetic:** fake transport, fixture providers.
- **Real:** a Windows/MT5/Telegram host run on VTMarkets-Demo …999 during open windows. One ASW session, one LSMC transition and one CCFD window, with delivery enabled. Recorded: journal INTENT/RESULT events, Telegram message ids, `broker_mutations=0`, `order_api_calls=0`. This needs the owner's go-ahead.

C18 is not reported complete until all three families show end-to-end read-only generation and authorized Telegram delivery on the host.

## 7. Progress

| Item | State |
|---|---|
| PR A (#187) scope-aware canonical ticket | Open; CI green except one pending run when checked |
| PR B (#188) ASW/LSMC/CCFD read-only lanes | Open; `tests/test_report_lanes.py` 21 passed |
| PR C delivery policy, `send_report`, daily summary | Implemented; `tests/test_report_delivery.py` 7 passed; regression 263+ passed |
| Host acceptance (real Windows/MT5/Telegram) | NOT_RUN: needs merge, owner go-ahead and open windows |

## 8. Out of scope (owner-gated)

- Registering or admitting v1.1.3 (PR #186) or the CCFD v1.1.0 scopes (C17).
- Re-binding the LSMC engine hash (`88dd9f1f` vs `ec0b2f3d`).
- The crypto 2-entry cap and day boundary (#175).
- Any demo/live activation.
