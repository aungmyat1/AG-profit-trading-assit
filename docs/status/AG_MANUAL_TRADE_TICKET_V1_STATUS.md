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

## Phases 1–8 — implemented (2026-10-06, Linux cloud container, unit/fixture-tested only)

| Phase | Result | Code | Tests |
|---|---|---|---|
| 1 Registry authority | `ticket_authority`, `logic_status`, `logic_verified_identity`, `economic_status`, `demo_order_authority` on `ST_ASIAN_SWEEP_5R_V1` and `SESSION_TRADE_V1`; unknown/missing → fail closed; `SESSION_TRADE_V1` → `STRATEGY_ADAPTER_NOT_IMPLEMENTED`; `LOGIC_VERIFIED` bound to strategy+version+engine+contract hash | `src/v1_tickets/authority.py`, `strategies/registry.yaml` | `tests/test_manual_ticket_authority.py` |
| 2 DST display | `session_clock.local_time_diagnostics` (London/New York/MMT); `v1_tickets.fx.session_windows_utc` single fixed-UTC source; eligibility unchanged on 2026-03-10, 04-14, 10-23, 10-27, 11-03 | `src/session_clock.py`, `src/v1_tickets/fx.py` | `tests/test_manual_ticket_dst_clock.py` |
| 3 Scan records | One append-only record per strategy/session/symbol per scheduled run; `coverage()` → `NOT_RUN` for a missing record | `src/v1_tickets/scan_record.py` | `tests/test_manual_ticket_scan_records.py` |
| 4 Logic gate | L1–L6 pure functions with per-check evidence | `src/v1_tickets/logic_gate.py` | `tests/test_manual_ticket_logic_gate.py` (recorded EURUSD M15 sessions) |
| 5 Manual ticket | Extends the V1 FX ticket dict; owner layout; existing Telegram channel only for `TICKET_READY` | `src/v1_tickets/manual_ticket.py`, `config/owner_ticket.yaml` | `tests/test_manual_ticket_build.py` |
| 6 Owner decision | `AG_MANUAL_TICKET_DECISION_V1`, append-only; auto `EXPIRED` | `src/v1_tickets/owner_decision.py`, `scripts/manual_ticket_decision.py` | `tests/test_manual_ticket_owner_decision.py` |
| 7 Outcomes | `VIRTUAL_FORWARD` first-touch resolver, `AMBIGUOUS` same bar, once per UTC day on the FX task | `src/v1_tickets/outcome.py` | `tests/test_manual_ticket_outcome.py` |
| 8 Daily report + boundary | Report after last window + 30 min; static import-graph proof of no broker mutation | `src/v1_tickets/manual_report.py`, `scripts/run_manual_ticket_report.py` | `tests/test_manual_ticket_report_and_boundary.py` |

Scheduling: no new task or orchestrator. The existing `AG-V1-FX-Cycles` task
(`live_candles_smoke.py --mode fx`) runs the daily jobs (`run_manual_jobs`) before the
FX cycle: auto-expiry every run, the resolver once per UTC day, the report once per day
after 15:30 UTC.

### Finding — frozen v1.1.1 is not logic-verifiable (repo wins; nothing repaired)

L2 evaluates every rule declared in `strategies/ST_ASIAN_SWEEP_5R_V1.yaml`. On every
recorded sweep it **fails** for reasons that were already documented in the repository
before this change:

- `stop_loss_mode: PERCENT_OF_SESSION_RANGE 0.25` vs the engine's sweep-wick stop
  (`docs/status/AG_ST_ASIAN_SWEEP_V1_1_2_GOVERNED_SL_GEOMETRY_RECONCILIATION_STATUS.md`).
- `trend_bias_filter: EMA_50` declares no timeframe/price source and is not consumed.
- `entry_level: Sweep_Candle_Body_Close` vs the engine's body edge (`min/max(open, close)`)
  whenever the sweep candle closes in the trade direction.
- `TREND`/`RANGE` engine branches are not declared in the YAML `entry_rules`.
- `range_session_check` (25 pips, EURUSD only) has no stated gating effect.
- `structural_invalidation` ("expansion volume") has no measurable definition.

Effect: `ST_ASIAN_SWEEP_5R_V1@1.1.1` produces `TICKET_BLOCKED` with
`LOGIC_GATE_FAIL:L2` and **zero `TICKET_READY`** in production. `logic_status` stays
`NOT_VERIFIED`. The fix is a new candidate version whose spec and engine agree, which is
out of scope. The `TICKET_READY` path (risk, lot, expiry, decision, delivery) is tested
with an explicit test-only L2 stub.

Other recorded observations: the existing 15 % spread/stop guard blocks many tight-stop
sweeps (`SPREAD_TOO_WIDE`); the recorded 2026-07-17 sweep has zero stop distance (L3 FAIL).
The existing informational READY Telegram message (`tg.format_ticket`) is unchanged.

### Tests

`python -m pytest -q` → **980 passed, 2 skipped** (baseline 878 passed, 2 skipped; +102
new). Frozen strategy files: `git diff main -- strategies/` changes only `registry.yaml`
and `STRATEGY_LEDGER.md` (additive authority fields/notes); `ST_ASIAN_SWEEP_5R_V1.yaml`,
`session_trade/contract.yaml` and `src/strategy_engine/` are unchanged.

Not performed: live MT5 host run, Windows Task Scheduler run, Telegram delivery. These
paths are **unit-tested only, not live-verified**.

### Owner actions still open

1. Set `owner_ticket.risk_pct` / `cost_warn_R` in `config/local/owner_ticket.yaml` on the
   host (until then tickets are `RISK_CONFIG_MISSING`).
2. Decide on the L2 divergences: a new candidate version of the strategy, or an explicit
   owner ruling on which source (YAML or engine) is the authority.
3. Decide whether the existing informational READY message should continue while the
   manual gate blocks.
4. Commission per symbol is not available in the repo; `cost_in_R` is spread-only and L5
   shows `COMMISSION NOT AVAILABLE`.

## Phase A close-out (2026-10-06, Linux cloud container, unit/fixture-tested only)

Additive; Phases 0–8 above are unchanged historical evidence.

| Item | Result | Code | Tests |
|---|---|---|---|
| A1 L3 target ordering | New check `L3.target_order`: LONG `entry < TP1 <= TP2`, SHORT `entry > TP1 >= TP2`, else L3 FAIL. Owner fixture USDJPY SHORT 158.148 / SL 158.224 / TP1 157.762 / TP2 157.768 → FAIL. **New finding on recorded data:** 2026-06-17 EURUSD LONG (entry 1.16075, TP1 = box high 1.16160 = 6.07R, TP2 = 5R 1.16145) also fails; the Phase 4 test that asserted L3 PASS there encoded the defect and was replaced. READY-path composition tests moved to 2026-06-23 (SHORT, L3 passes); no extra stub was added. | `src/v1_tickets/logic_gate.py` | `tests/test_manual_ticket_logic_gate.py` |
| A2 block reasons | Ticket and scan record carry ordered `block_reasons[]` and `primary_block_reason`. Severity: L1–L4 FAIL > DATA/METADATA missing (`DATA_ERROR:*`, `STALE_DATA`, `MARKET_CLOSED`, `SPREAD_NOT_EVALUATED`, `SYMBOL_METADATA_MISSING`, `ACCOUNT_BALANCE_UNAVAILABLE`) > `RISK_CONFIG_MISSING` > other blocking (e.g. `SPREAD_TOO_WIDE`, authority) > `SIGNAL_STALE` / `TICKET_EXPIRED` > `L5_WARN` (advisory, never blocks). `STALE_SIGNAL` is normalised to `SIGNAL_STALE`. `stop_reason` remains as an alias of the primary for existing readers. Gates are now evaluated even when the base ticket was already withheld, so a stale signal no longer hides an L2 failure. | `logic_gate.py`, `manual_ticket.py`, `scan_record.py`, `live_candles_smoke.py` | `tests/test_manual_ticket_build.py`, `tests/test_manual_ticket_scan_records.py` |
| A2 PASS B re-run | Recorded EURUSD 2026-06-23 at 07:40 (stale signal): primary `LOGIC_GATE_FAIL:L2`, then `SIGNAL_STALE`, `TICKET_EXPIRED`, `L5_WARN`. GBPUSD/USDJPY PASS B inputs are not in the repository; their re-run needs the host capture. | | `test_pass_b_shape_l2_primary_with_signal_stale_secondary` |
| A3 `REFERENCE_NOT_READY` | **Not diagnosable from the repository.** No code path in `src/` or `scripts/` emits `REFERENCE_NOT_READY` (closest: `REFERENCE_SESSION_NOT_COMPLETE` in `session_scanner/strategy_adapter.py`, `REFERENCE_BOX_INCOMPLETE` in `session_scanner/checklist*.py`), and the four captures are not committed. Classification: `UNRESOLVED_EVIDENCE_NOT_IN_REPO`, possibly a message from a different subsystem. Needs the four raw captures (symbol, timestamp, full text). | — | — |
| A4 TELEGRAM_DELIVERY_TRACE_R1 | Existing subsystem only. Scan/ticket records are written before `_notify`; `_notify` never raises (send error → `FAILED`, any other exception → `ERROR` with class name only, policy off → `NOT_SENT_POLICY`) and appends a separate record to `journal/ticket_delivery/delivery_status/<date>.jsonl` (`channel, kind, value, ref, status, error, recorded_at`). No token, chat id, URL or message text is stored. LSMC alerts stay log-only (no journal in that path). | `scripts/host/live_candles_smoke.py` | `tests/test_manual_ticket_scan_records.py` |
| A5 status line | `PROJECT_STATUS.md` snapshot updated; host run recorded as `HOST_EVIDENCE_NOT_IN_REPO`. | | |

Tests: `python -m pytest -q tests/test_manual_ticket_*.py` → 117 passed;
`python -m pytest -q` → **995 passed, 2 skipped** (was 980 passed, 2 skipped).
Not performed: MT5 host run, Task Scheduler run, Telegram delivery (no host in this
container). `BROKER_MUTATION_COUNT = 0`; the static no-broker test still passes.
`ST_ASIAN_SWEEP_5R_V1.yaml` and `src/strategy_engine/` unchanged. `EDGE_VERIFIED = FALSE`.
