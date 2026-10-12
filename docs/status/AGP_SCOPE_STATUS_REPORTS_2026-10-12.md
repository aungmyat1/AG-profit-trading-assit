---
class: evidence
state: DESIGN
owner_reviewed: null
review_by: null
---
# AGP scope-status Telegram reports (2026-10-12)

This change implements follow-up (d) of the OD1012-ROUTING amendment (PR #177): read-only
Telegram status reporting for all three strategy families. Every relevant scope is reported
with its current verification status. Every route is `REPORT_ONLY`. No READY, registry
authority, demo or live flag changed, and nothing new can reach an order path.

## What is reported

| Family | Strategy | Pairs | Delivery |
|---|---|---|---|
| Session FX/gold | `ST_ASIAN_SWEEP_5R_V1` (scoped v1.1.2) | EURUSD, GBPUSD, USDJPY, XAUUSD | Existing FX session summary after each session (ASIAN_LONDON, LONDON_NEWYORK), now stamped per symbol |
| Crypto CFD | `ST_CRYPTO_CFD_SWEEP_RETEST_V1` | BTCUSD, ETHUSD | New crypto strategy summary, once per active crypto ticket window: `CRYPTO_DAY` (weekdays) and `CRYPTO_WEEKEND` (Sat/Sun). It also shows the runtime research runner `ST_LIQUIDITY_SWEEP_RETEST_V1` outcome, labelled separately. |
| Large-SMC | `ST_LARGE_SMC_V1` | all six | No scheduled report (watch/alert system). Each alert gains one `STATUS: … · REPORT ONLY — NOT AN ENTRY` line. |

The family→pair map is the owner-stated universe from PR #177. It is pinned as constants in
`src/v1_tickets/scope_status.py`; it is never read from the SPEC-only schema. AUDUSD is excluded.

## Status semantics (from `strategies/registry.yaml`, fail closed)

- **Session FX/gold:**
  - `LOGIC_VERIFIED` only via `ready_authority.logic_scope_verified`, which requires an exact scope and matching identity hashes.
  - `SUSPENDED` from `logic_suspended_scopes`.
  - `STALE_IDENTITY` when a recorded scope's identity no longer matches.
  - Otherwise `UNVERIFIED`.
- **Crypto CFD:**
  - The candidate `logic_status` is checked together with the recomputed `authority.logic_identity` digest.
  - Today both symbols are `STALE_IDENTITY`.
- **Large-SMC:**
  - Detection verification is not entry verification.
  - Every scope is `UNVERIFIED` (`ENTRY_LOGIC_NOT_VERIFIED`), with `detection=…` shown as detail.
- **Route:** `REPORT_ONLY` with a non-empty reason, e.g. `READY_AUTHORITY_OFF_D6`, `LOGIC_NOT_VERIFIED`, `STALE_IDENTITY`, `REGISTRY_ENTRY_MISSING`.
- **Fail closed:** a registry fault yields `UNVERIFIED` / `REGISTRY_ENTRY_MISSING`.
- **Report-only guard:** the renderer rejects any route other than `REPORT_ONLY`.

Current values: GBPUSD × ASIAN_LONDON is `LOGIC_VERIFIED` (`READY_AUTHORITY_OFF_D6`), and EURUSD is
`SUSPENDED` (`L3_REPAINT_UNRESOLVED_2026-07-31`). All other session scopes are `UNVERIFIED`.

## Delivery

- **Engine:** reuses the once-only engine `_process_due_summary`, the dedupe ledger `Sender`, and `build_sender` gating (local `canonical_ticket_delivery.yaml` + `TELEGRAM_DELIVERY_ENABLED` + chat allowlist). While disabled, the result is recorded as `disabled` and nothing is transported.
- **When crypto summaries run:** in `--mode crypto` on the outside-window branch, before any runner lock or MT5 access. No scheduled task changed.

## Files

- New:
  - `src/v1_tickets/scope_status.py`
  - `src/ticket_delivery/archive_reader.py`
  - `tests/test_scope_status.py`
  - `tests/test_crypto_strategy_summary.py`
- Changed:
  - `scripts/host/canonical_fx_delivery.py`
  - `src/telegram_delivery/adapter.py`
  - `src/host_delivery/telegram_message.py`
  - `scripts/host/live_candles_smoke.py`
  - `tests/test_host_go_live_kit.py`

## Evidence

- **Command:** `python -m pytest -q tests/test_scope_status.py tests/test_crypto_strategy_summary.py tests/test_canonical_fx_delivery.py tests/test_telegram_delivery_adapter.py tests/test_lsmc_crypto_session_summary.py tests/test_telegram_message_format.py tests/test_host_go_live_kit.py tests/test_host_heartbeat.py tests/test_lsmc_delivery_diagnostics.py`
- **Result:** 311 passed (2026-10-12, Windows workstation, Python 3.14).
- **Environment:** offline; transport faked; no MT5, broker or network.
- **Not host-verified.** A first open-window run on the VTMarkets-Demo …999 host, with delivery enabled, is deferred and needs owner go-ahead.
