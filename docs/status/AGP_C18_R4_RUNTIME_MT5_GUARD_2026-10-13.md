---
class: evidence
state: DESIGN
owner_reviewed: null
review_by: null
---
# AGP-C18-R4 — Runtime read-only MT5 guard (2026-10-13)

Deliverable A of C18-R4. This adds runtime proof, not only static proof, that the reporting runner
cannot reach broker mutation. Evidence tier: **synthetic** (fake brokers); host acceptance is pending.

## Coverage (main `5d8a6fb` + this change)

| Lane | MT5 entrypoint | Adapter | Guarded? | Mutation reachable? |
|---|---|---|---|---|
| ASW FX (`--mode fx --canonical`) | `live_candles_smoke._main` → `import_mt5()` | `GuardedMT5` → `snapshot_provider`; `host_fetch`/`host_quote` | Yes: process-wide guard installed before `mt5_initialize` | No: `order_*` refused before MT5 |
| Large SMC (`--mode lsmc`, `lsmc-weekend`) | same single `import_mt5()` branch | `host_fetch`, `host_quote`, `Mt5CryptoFeed` | Yes | No |
| Crypto CFD (`--mode crypto`) | same branch | `CcfdFeed(host_fetch, host_quote_observed)` | Yes | No |
| Shared modules holding `MetaTrader5` (`mt5.market_data`, `mt5.symbol_resolver`, `mt5.broker_time`) | module-level `import MetaTrader5 as mt5` | n/a | Yes: `install()` rebinds every module attribute that points at the real module, plus `sys.modules["MetaTrader5"]`. Coverage is reported `COMPLETE` only when no direct reference remains, otherwise `INCOMPLETE`. | No |

- **One process per run.** The runner starts no subprocess or second interpreter. There is no `order_send`/`order_check` call site anywhere in `src/` or `scripts/host`.

## Guard (`src/mt5/readonly_guard.py`)

- **Prohibited:** `order_send` and `order_check`, plus any other `order_*` entry point except the read-only `order_calc_margin`/`order_calc_profit`.
- **What a refused call does:** it never reaches MT5. It counts, records a redacted `path:line` call site, and raises `ProhibitedBrokerCall`. The run then exits with code 3 and logs `MT5_GUARD RUN_FAILED`.
- **Read-only queries:** rates, ticks, symbols, account/terminal info, positions/orders/history are forwarded and counted.
- **Per-run counters** (keyed by run id `mode-timestamp-pid`):
  - `MT5_READ_CALLS`
  - `PROHIBITED_ORDER_API_ATTEMPTS`
  - `ORDER_SEND_ATTEMPTS`
  - `ORDER_CHECK_ATTEMPTS`
  - `BROKER_MUTATION_REQUESTS_FORWARDED`
  - `GUARD_COVERAGE_STATUS`
- **Evidence output:** a log line `MT5_GUARD …` and JSONL at `journal/ticket_delivery/mt5_guard/<date>.jsonl`.

## Broker-history reconciliation (per run, read-only)

`broker_history_window(guard, run_start, run_end, to_utc=server-time rule)` queries order and deal history with one day of padding, because MT5 history uses server time. It then filters on each record's own timestamp, converted with the host server-time rule.

| Result | Meaning |
|---|---|
| `BROKER_HISTORY_CLEAN` | No order or deal inside the run window |
| `BROKER_HISTORY_AMBIGUOUS` | At least one record inside the window. Ticket suffix and magic are recorded; another process's activity can't be attributed. |
| `BROKER_HISTORY_UNAVAILABLE` | The query failed |

Unchanged history alone is never treated as proof of zero order calls. The runtime counters are the primary proof.

## Tests

- `tests/test_mt5_readonly_guard.py` covers:
  - positive control: `order_send`/`order_check`/`order_*` against a **fake** broker are refused, counted, and never reached;
  - reads are allowed and counted;
  - alternate references are rebound; coverage is COMPLETE or INCOMPLETE as appropriate;
  - counters are partitioned per run; the guard is immutable;
  - history CLEAN, AMBIGUOUS, UNAVAILABLE, and the timestamp filter;
  - the runner installs the guard before `mt5_initialize` in its single MT5 branch;
  - machine-readable evidence is written;
  - execution flags and identity digests are unchanged.
- **Results:** guard + host kit 102 passed. Regression (lanes, delivery, canonical FX, LSMC, CCFD guard, S1/D6, LSMC summaries) 211 passed. LSMC summaries alone 16 passed.

**Unchanged:**
- execution authority: `enabled: false`, `per_order_confirm_required: true`
- READY, the registry, strategy engines/contracts, and the Telegram policy
