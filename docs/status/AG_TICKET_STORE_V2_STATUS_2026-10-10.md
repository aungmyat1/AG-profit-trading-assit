---
class: evidence
state: UNIT_TESTED
owner_reviewed: null
review_by: null
---
# AGP-TS-V2 — storage-only lifecycle history (2026-10-10)

Draft PR: https://github.com/aungmyat1/AG-profit-trading-assit/pull/133.
Base: `5b671996ef91934f2e8b58f9748ee78b1804a099`, the requested fallback because PR131's stack is not merged. V1's evaluation/outcome field order, schemas, identity, JSONL serialization and existing callers remain unchanged. DEMO is added as a storage source. No strategy, decision, authority, delivery or broker module changes; execution rows are optional and never authorize execution.

## Append-only records

New directories under the same store root: `deliveries/`, `owner_decisions/`, `order_events/`, `position_closes/`; each contains `<recorded_at_utc day>.jsonl`.

Common fields: `schema, record_id, ticket_id, record_ref, recorded_at_utc, source, provenance, record_sha256`. All fields are present; missing measurements are null. `record_ref` is a caller-supplied stable event reference, distinct for each event/transition. `recorded_at_utc` must be aware UTC. IDs hash `[schema, ticket_id, evaluation cohort, record_ref]`, so moving a conflicting event to a different date file cannot bypass immutability. The shared V1 append writer implements duplicate no-op, conflict rejection and corrupt/truncated-tail rejection. V2 additionally validates its seals on append/read/reindex. No files are repaired. In-process writes are serialized; V1's single-process-writer-per-root restriction remains.

| Kind | Schema suffix | Fields beyond common |
|---|---|---|
| DELIVERY | V2_DELIVERY | channel, status, attempt_ref |
| OWNER_DECISION | V2_OWNER_DECISION | decision, actor, reason, evaluation_source |
| ORDER_EVENT | V2_ORDER_EVENT | event, actor, account, broker_order_id, price, sl, tp, volume, order_type, side, average, filled, remaining, cost |
| POSITION_CLOSE | V2_POSITION_CLOSE | close_price, close_reason, realized_R, realized_pnl, commission, swap, max_adverse_R |

`source` is LIVE/DEMO/REPLAY/LEGACY except OWNER_DECISION, where it is TELEGRAM/LOCAL and the separately required `evaluation_source` carries the cohort. This preserves the decision's origin without contaminating evaluation-source statistics. Unknown facts, including a broker ID before submission, remain null. Order event actor is SYSTEM/OWNER; event is INITIALIZED/SUBMITTED/ACCEPTED/REJECTED/MODIFIED/FILLED/PARTIALLY_FILLED/CANCELED/EXPIRED. `account` must be DEMO; LIVE and missing account are rejected. This is metadata validation, not a trading state machine; no transition or price-level decision is performed. Child records may arrive before their evaluation; the index retains them, and history joins them once an evaluation is available.

Builder/append pairs are exported from `ticket_store`: `build_delivery` / `append_delivery`, `build_owner_decision` / `append_owner_decision`, `build_order_event` / `append_order_event`, `build_position_close` / `append_position_close`. Existing evaluation/outcome builders and append methods stay available. Read new kinds with `lifecycle_records(kind, ticket_id=None)`.

## Rebuildable index and views

`index.sqlite` remains disposable. Reindex creates typed tables for every new kind and keeps the original record JSON with file/line references. `check()` compares IDs/counts for all six tables. Rebuild failure preserves the prior index. Empty new tables are allowed; V1-only rebuild return counts retain their existing shape. Rebuild an old V1 index before using the new views.

- `v_ticket_history`: one row per ticket, latest evaluation cohort as the scalar summary; ordered JSON arrays retain evaluations → deliveries → decisions → order events → closes/outcomes within that cohort. Missing V1 ticket IDs use their evaluation ID as the history key. Equal timestamps are ordered by stable record ID. A ticket ID reused across cohorts selects the latest evaluation for history; no child from another cohort is joined.
- `v_ticket_cohorts`: internal one-row-per-ticket-per-source projection. This keeps earlier LIVE/DEMO evidence available even if a later REPLAY record shares the ticket ID.
- `v_strategy_stats`: grouped by strategy@version × symbol × session × source, explicitly `source IN ('LIVE','DEMO')`. Child records must match that cohort. REPLAY/LEGACY never appear. Counterfactual outcomes are excluded.

Statistics: tickets = distinct ticket/cohort rows; decided = tickets with an owner-decision record; filled = tickets with FILLED or PARTIALLY_FILLED event (repeated/partial order events do not inflate counts). Resolved = tickets with a measured R. Latest POSITION_CLOSE realized_R takes precedence over latest non-counterfactual OUTCOME payload.net_R/payload.realized_R. Each close represents final position totals, not incremental partial-close fills. Win rate = positive measured R / resolved tickets, including zero R in the denominator. avg R and expectancy = arithmetic mean measured R, including losses and breakevens; unknown R is excluded, never replaced with zero. max adverse R = largest measured nonnegative adverse-excursion magnitude from close.max_adverse_R or outcome.payload.mae_R. Null metrics mean unmeasured. V1 outcomes without order events can supply resolved R while filled remains zero; neither field implies execution evidence.

## Execution-field mapping — REFERENCE only

Checked maintained upstream source on 2026-10-10: [Freqtrade persistence/trade_model.py](https://github.com/freqtrade/freqtrade/blob/develop/freqtrade/persistence/trade_model.py) and [Nautilus model enums](https://github.com/nautechsystems/nautilus_trader/blob/develop/crates/model/src/enums.rs). No upstream trading code or dependency is imported/copied; Freqtrade's model is a reference, not a storage/strategy authority.

| V2 field | Freqtrade reference | Semantics |
|---|---|---|
| broker_order_id | Order.order_id | Venue-issued identifier; null before acknowledgement |
| event | Order.status; Nautilus lifecycle vocabulary | Recorded event, not an inferred/current state |
| order_type, side | Order.order_type, Order.side | Pass-through order type and buy/sell side |
| price | Order.price | Requested order price, distinct from average execution price |
| average | Order.average | Average executed price; unknown stays null |
| volume | Order.amount | Requested quantity; caller must document native units/contract conversion in provenance |
| filled, remaining | Order.filled, Order.remaining | Cumulative executed and remaining quantity, in the same units as volume |
| cost | Order.cost | Executed quote-currency notional, not commission |
| sl | Order.stop_price | Requested stop level; no stop decision is made |
| tp | No single equivalent | Explicit ticket take-profit extension |
| close_price | Trade.close_rate | Final average exit price |
| close_reason | Trade.exit_reason | Caller-recorded reason |
| realized_pnl | Trade.close_profit_abs | Final net realized amount in documented account/settlement currency |
| realized_R | No equivalent | Net realized result divided by caller-recorded initial monetary risk; not recomputed here |
| commission | Trade.fee_open_cost + fee_close_cost | Total absolute fee cost, not fee ratio; unknown stays null |
| swap | Trade.funding_fees (conceptual) | Signed financing amount; CFD swap is distinct from perpetual funding |
| max_adverse_R | No equivalent | Optional measured adverse-excursion magnitude |

Nautilus references the supplied lifecycle vocabulary; MODIFIED corresponds conceptually to an order-update event, not an `OrderStatus::Modified` enum. No additional Nautilus states are silently added.

## Query and export

```bash
python scripts/ticket_store_reindex.py --store work/ticket_store
python scripts/ticket_history.py query --store work/ticket_store --view history --ticket-id T
python scripts/ticket_history.py query --store work/ticket_store --view stats --source DEMO
python scripts/ticket_history.py export --store work/ticket_store --output work/history.csv --backend sqlite
python scripts/ticket_history.py export --store work/ticket_store --view stats --output work/stats.parquet
```

Filters: ticket-id (history only), strategy, symbol, source; queries are parameterized and open the index read-only. SQLite is the portable view authority and requires no optional package. `--backend auto` uses optional DuckDB if installed, otherwise SQLite. DuckDB operates on the derived SQLite view results in memory, avoiding extension downloads or broker access. `--backend duckdb` requires optional `.[ticket-history]` (`duckdb==1.4.1`). CSV uses the standard library. Parquet requires optional `.[research]` (`pyarrow==25.0.1`) and preserves numeric schemas even for empty exports. No required dependency is added.

## OSS-FIRST

| COMPONENT | OSS_CANDIDATE | DECISION | REASON |
|---|---|---|---|
| Append storage | Existing TICKET_STORE_V1 | REUSED | Local immutable/idempotent writer and error model |
| Execution fields | Maintained Freqtrade trades/orders model | REUSED (REFERENCE only) | Semantics only; no external trading code copied/imported |
| Order vocabulary | Maintained Nautilus order status/event model | REUSED (REFERENCE only) | Supplied vocabulary, no engine dependency or transitions |
| Index/history/stats | Standard-library SQLite | REUSED | Existing rebuildable index, JSON and window SQL |
| Optional analytics | DuckDB 1.4.1 | WRAPPED | Optional in-memory result projection; SQLite fallback |
| Parquet export | Existing optional PyArrow 25.0.1 | REUSED | Typed export; no new mandatory package |

## Validation

Linux offline: `python -m pytest -q tests/test_ticket_store_v2.py tests/test_ticket_store_v1.py tests/test_ticket_store_grader.py` — **56 passed**. Both DuckDB and SQLite paths, CSV/Parquet, empty execution tables, cohort exclusion, conflicts/corruption, and V1 byte-identical corpus pass. The committed corpus was generated using the frozen `5b67199` V1 module for all three original sources and both original record kinds.

Full milestone suite: `python -m pytest -q tests` — **1813 passed, 3 skipped**, 45 warnings, 63.03 seconds. Ruff F/I checks and `git diff --check` pass. Final head is recorded in the draft PR. No host or broker check was performed. **NO_BROKER_MUTATION**: ORDER_API_CALLS=0; BROKER_MUTATION_COUNT=0.
