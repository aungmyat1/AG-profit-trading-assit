# AG Manual Trade Ticket V1 — Status (2026-10-06)

Pre-edge phase. `EDGE_VERIFIED = FALSE` for every strategy. A manual ticket is an
analysis/proposal artifact only:

```
TICKET_READY != ORDER_READY
TICKET_READY != BROKER_AUTHORIZED
TICKET_READY != EDGE_VERIFIED
```

This file is additive evidence. It does not rewrite any earlier status document.

## Phase 0 — discovery (2026-10-06, no code changes)

Baseline before this change set: `python -m pytest -q` → **878 passed, 2 skipped**
(Linux cloud container, no MT5 package; `tests/conftest.py` placeholder).

| Area | Existing authority found |
|---|---|
| Scheduler | `scripts/host/live_candles_smoke.py --mode fx` via Windows Task Scheduler (`scripts/host/install_tasks.ps1`; `scripts/run_fx_cycle_once.py` delegates to it). `config/ag_scheduler_v2.yaml` (RESEARCH) has no Python consumer. |
| Session windows | `src/session_clock.py` + `config/canonical_sessions.yaml` (`dst_policy: fixed_utc`); strategy windows in the strategy YAML (GMT). |
| Scanner | `src/session_scanner/` (Scanner V1 / Checklist V1.1). |
| Strategy evaluation | `src/strategy_engine/` — `ST_ASIAN_SWEEP_5R_V1@1.1.1`. |
| Ticket model | No `TradeTicket` class; V1 tickets are dicts built by `src/v1_tickets/fx.py`. |
| Risk / lot | `src/sizing_math/` (not used by V1 tickets). |
| Journal | `src/ticket_delivery/archive.py` (via `post_asian_pilot.report_archive.write_report`), `attempt_journal.py` (append-only JSONL). |
| Reporter | `scripts/run_fx_daily_report.py`. |
| Registry | `strategies/registry.yaml`; loaders `src/proposal_envelope/strategy_authority.py`, `src/session_scanner/registry.py`. |

Broker mutation reachability: no `.order_send(`, `.order_check(`, `.positions_get(`,
`.orders_get(` call site exists in any `.py` file; `TRADE_ACTION_*` appears only as
constants in the root `MetaTrader5.py` placeholder.

Repository conflicts found (repo wins):

- **C1** `SESSION_TRADE_V1`'s engine lives in `D:\ddev\Session Trade Codex` (referenced,
  not vendored); its contract forbids porting the logic here.
- **C2** `SESSION_TRADE_V1.demo_authorized` is already `false` (owner decision D3).
- **C3** Signed session windows are fixed UTC; DST anchoring would be a rule change.
- **C4** `config/trading.yaml` `risk.risk_per_trade_pct: 1.0` is an execution default,
  not owner manual-ticket risk authorization.

## Owner decisions (approved 2026-10-06)

| # | Decision |
|---|---|
| C1 | Option A. The manual-ticket vertical slice uses `ST_ASIAN_SWEEP_5R_V1@1.1.1` (engine in this repo). `SESSION_TRADE_V1` gets registry/scanner visibility only: `logic_evaluable=false`, `ticket_eligible=false`, reason `STRATEGY_ADAPTER_NOT_IMPLEMENTED`, zero `TICKET_READY`. No vendoring, porting or borrowed logic. |
| C2 | No authority change. `demo_authorized` stays `false`. No order/position/SL/TP mutation path may be introduced; Phase 8 enforces this statically. |
| C3 | DST is display/verification only. Signed rules stay fixed UTC. Tests must prove DST conversion never changes canonical fixed-UTC eligibility. A DST-anchored model is a future candidate version. |
| C4 | Owner config `owner_ticket.risk_pct` / `owner_ticket.cost_warn_R` with **no** inherited default (not `risk_per_trade_pct`, not any historical 0.5%). Missing/null/malformed/zero/negative risk → `risk_status = RISK_CONFIG_MISSING`, `ticket_ready = false`. `cost_warn_R` is advisory only. |
| Contracts | `src/contracts/v1.py` is immutable; owner decisions use a dedicated manual-ticket decision contract. |
| States | Every scheduled symbol evaluation resolves to `NO_SETUP`, `WATCH`, `OPPORTUNITY`, `TICKET_BLOCKED` or `TICKET_READY`; a missing record is distinguishable from "ran, no setup". |
| Logic identity | `logic_identity = strategy_id + strategy_version + engine_identity + contract_hash`; any change invalidates a prior `LOGIC_VERIFIED` claim. |
| Shadow outcomes | Skipped/expired/rejected tickets resolve as `VIRTUAL_FORWARD` observations, never as executed trades; raw proposal, owner decision and virtual outcome are kept side by side. No optimization from them. |
| Expiry | `valid_until` is strategy/session-derived; after it `ticket_status = EXPIRED`, `owner_accept_allowed = false`. |
| Delivery | One PR, commits separated by phase. |
