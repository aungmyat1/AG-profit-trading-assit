# AG FX Runtime-Error Structured Provenance Remediation — Status

**Mission:** AG_FX_RUNTIME_ERROR_STRUCTURED_PROVENANCE_REMEDIATION_V1
**Branch:** `feat/fx-runtime-error-structured-provenance`
**Worktree:** `D:/AG-fx-runtime-error-provenance` (isolated from the live main tree at
`D:/ddev/AG profit trading`, which runs the actual forward-shadow scheduler and was never
read or written by this work)
**Baseline SHA:** `e7e9583749bebade5b89c4c53c9af97739d5f20f`

## Baseline

Active `ST_ASIAN_SWEEP_5R_V1` forward-shadow qualification campaign
(`AG_V1_0_3_FX_SHADOW_SERIES_002`): VALID=8/20, INVALID=5, PENDING_RECONCILIATION=0,
VALID_REMAINING=12. This remediation does not reinvestigate or reclassify
2026-09-14/16/18/22 — those remain the historical-reconciliation authority. This work is
prospective observability/provenance hardening only.

## Problem addressed

`operations.runtime_errors` in `post_asian_pilot/report.py::render_pilot_end_report`
was a single monotonically-increasing counter (`MonitoringCounters` `data_errors`,
`post_asian_pilot/monitor.py`), copied verbatim from `post_asian_pilot/pipeline.py`'s 3
increment sites in `_evaluate_pair` (asian-window `get_candles`, `build_asian_session_
snapshot` DATA_ERROR, post-session-window `get_candles`). It could not by itself
distinguish a permanent processing failure from a transient failure followed by a
successful retry — a reviewer had to trace source code to tell them apart (already done
once, for 2026-09-14/16/18/22; see the prior reconciliation finding this mission
inherits as given context).

## Changed files

- `src/post_asian_pilot/runtime_error_log.py` (new) — `RuntimeErrorLog`: structured
  runtime-error event store, additive to `MonitoringCounters`.
- `src/post_asian_pilot/store.py` — `PilotStores` gains a `runtime_error_log` field
  (`journal/post_asian_pilot/runtime_error_log.json`), wired the same way as every other
  field on `PilotStores.default()`.
- `src/post_asian_pilot/pipeline.py` — at the same 3 already-established increment
  sites in `_evaluate_pair`, added a `record_error(...)` call alongside the existing
  `COUNTER_DATA_ERRORS` increment, and a `record_recovery(...)` call on the
  corresponding success path (asian `get_candles`, `build_asian_session_snapshot`,
  post-session `get_candles`). No control flow, gating, or decision logic changed.
- `src/post_asian_pilot/report.py` — `render_pilot_end_report`'s `operations` block
  gains `recovered_errors`, `unresolved_errors`, and `runtime_error_events` (the raw
  structured events for the day), derived from `RuntimeErrorLog.events_for_date()`.
  `runtime_errors` (the pre-existing aggregate) and `result` classification are
  unchanged in both code and value for any day with no structured events.
- `tests/test_runtime_error_log.py` (new) — focused test matrix, see below.
- `docs/status/AG_FX_RUNTIME_ERROR_STRUCTURED_PROVENANCE_REMEDIATION_STATUS.md` (this
  file).

No other file was touched. Strategy YAML, `strategies/registry.yaml`,
`src/owner_decision/` (R5C), `execution/`, `mt5/` gateway/order paths, and
`config/trading.yaml` are all untouched (`git diff --stat` on this branch shows only the
5 files listed above as changed/added).

## Prospective boundary

Structured provenance begins the first cycle that runs against this code after it lands
on whatever branch is deployed. There is no backfill: `RuntimeErrorLog.events_for_date()`
returns `[]` for any day/unit that never had a `record_error()` call against this store
file, including every day before this remediation was live — that is the intended,
correct behavior (P7), not a gap.

## Schema (per structured event)

```
{
  "strategy_id": str,
  "symbol": str,               # unit_id
  "trading_date": "YYYY-MM-DD",
  "reference_session": str,    # session
  "operation": str,            # one of ASIAN_CANDLES_FETCH / ASIAN_SNAPSHOT_BUILD /
                                # POST_SESSION_CANDLES_FETCH (bounded enum, the 3
                                # already-established COUNTER_DATA_ERRORS sites)
  "error_class": str,          # bounded reason_code from MarketDataError/snapshot
                                # validation, never a free-text message
  "timestamp": ISO8601,        # of the failing attempt
  "attempt": int,               # 1-based count of failed attempts for this exact
                                # (strategy_id, symbol, trading_date, reference_session,
                                # operation) identity
  "retry_occurred": bool,      # attempt > 1
  "recovered": bool,
  "recovered_at": ISO8601 | null,
  "final_state": "UNRESOLVED" | "RECOVERED"
}
```

Persisted as a JSON list per `(strategy_id, symbol, trading_date, reference_session,
operation)` key inside `journal/post_asian_pilot/runtime_error_log.json`, via
`runtime_state.store.JsonKeyValueStore` — the same store class and same directory
convention (`journal/post_asian_pilot/`) as `decision.json`, `proposal.json`,
`monitoring_counters.json`, etc. No new persistence architecture.

## Retry/recovery semantics

- **Recovered case:** attempt 1 fails at an operation -> `record_error()` appends an
  `UNRESOLVED` event (attempt=1). A later cycle for the same unit+operation succeeds ->
  `record_recovery()` finds that still-unresolved event and flips it to
  `recovered=True, final_state=RECOVERED, recovered_at=<success timestamp>`. Proven by
  `test_pipeline_asian_candles_transient_failure_then_recovery` (runs the real
  `_evaluate_pair`, not a mock of the log itself).
- **Unrecovered case:** attempt 1 fails, no later success for that unit+operation is
  ever observed -> the event stays `recovered=False, final_state=UNRESOLVED`
  indefinitely. Proven by `test_unrecovered_failure_remains_distinguishable`.
- **Ordinary success (no prior failure):** `record_recovery()` is a pure no-op (returns
  `None`, writes nothing) when there is no unresolved prior event for that unit+
  operation — proven both at the unit level
  (`test_ordinary_success_creates_no_false_runtime_error`) and through the real pipeline
  call site (`test_pipeline_ordinary_success_creates_no_runtime_error_event`).
- The aggregate `MonitoringCounters` `data_errors` counter is untouched by recovery — it
  still only ever increments on a failure, exactly as before this remediation (so its
  historical meaning for 2026-09-14/16/18/22 is unchanged).

## Persistence / restart

`RuntimeErrorLog` is backed by `JsonKeyValueStore`, atomic-write (temp file +
`os.replace`), same convention as `decision_store`/`proposal_store`/`counters`/
`owner_decision.bridge.OwnerDecisionStore`. `test_restart_preserves_structured_
provenance` constructs a fresh `RuntimeErrorLog` instance against the same path
(simulating a process restart) after each write and confirms both the original
unresolved event and, later, its recovered state survive.

## Backward compatibility

`events_for_date()` on a day/store with no matching entries returns `[]` — never raises,
never fabricates `recovered=True`/`False`. `test_old_format_record_remains_readable_
with_no_fabricated_recovery` builds a decision record in the real pre-existing
`data_error_decision()`/`save_decision()` shape for `2026-09-14` (one of the actual
closed historical days) with no corresponding `runtime_error_log.json` entry, and
confirms the structured log reports `[]` for it rather than inventing anything.
`test_historical_day_report_unaffected_by_missing_structured_provenance` confirms
`render_pilot_end_report` for such a day still returns `result=PASS_WITH_OBSERVATIONS`
and `operations.runtime_errors=1` exactly as before, with the new fields correctly at
`recovered_errors=0, unresolved_errors=0, runtime_error_events=[]` (not fabricated
recovery, just genuinely-absent structured evidence).

## Tests

Focused (new): `tests/test_runtime_error_log.py` — 12/12 passed
(`python -m pytest tests/test_runtime_error_log.py -q`), covering the P11 matrix items
1–9 and 13.

Relevant regression: `tests/test_post_asian_pilot.py`,
`tests/test_daily_fx_report.py`, `tests/test_post_asian_observe_only_remediation.py`,
`tests/test_post_asian_status_readonly_remediation.py`,
`tests/test_run_post_asian_pilot_ticket_delivery_wiring.py`,
`tests/test_pipeline_canonical_wiring.py` — 133/133 passed, no regressions.

Full suite: not run. The repository collects 4173 tests; per this mission's own P11
instruction ("Do not run the unrelated full-suite unless genuinely warranted"), and
AGENTS.md's progressive-testing rule (run the full suite "only for a real milestone or
broad shared-surface change"), the full suite was judged not warranted here — this
change touches only `src/post_asian_pilot/{runtime_error_log.py,store.py,pipeline.py,
report.py}`, all covered by the relevant-regression scope above, and
`runtime_state.store.JsonKeyValueStore` itself was not modified (only used, the same way
every other `post_asian_pilot` store already uses it).

Items 10, 11, 12, 14 of the P11 matrix are proven by inspection/diff rather than a
dedicated new test:
- 10 (report can consume richer evidence without changing historical classification) —
  proven by `test_historical_day_report_unaffected_by_missing_structured_provenance` and
  by every existing `test_end_report_*` test in `test_post_asian_pilot.py` continuing to
  pass unmodified.
- 11 (historical campaign counts unchanged) — this worktree never touches the live
  campaign's persisted files at all; by construction this is trivially true. The
  backward-compatibility test above additionally proves nothing in this change would
  retroactively reinterpret an old-format record if this code were later deployed and
  pointed at the real files.
- 12 (strategy outputs unchanged for equivalent inputs) — `strategy_engine.evaluate()`
  is never called, imported differently, or wrapped by this change; `git diff` confirms
  zero touches to `strategy_engine/`, any strategy YAML, or `strategies/registry.yaml`.
- 14 (zero execution/broker calls) — `execution/`, `mt5/market_data.py`'s
  `order_check`/`order_send` surfaces, and `mt5/mt5_gateway.py` are never touched or
  imported by `runtime_error_log.py`; the only MT5-adjacent symbol used is the existing
  `MarketDataError` exception type, already imported by `pipeline.py` before this change.

## Campaign / strategy / execution firewall

- `strategies/registry.yaml`: unchanged (not in `git diff --stat`).
- Strategy implementation/config/parameters: unchanged.
- `src/owner_decision/` (R5C): unchanged.
- `execution/`: unchanged.
- Risk policy: unchanged.
- No `order_check`/`order_send` call added anywhere in this change; broker/demo/live
  order counts are 0 throughout (nothing here reaches `mt5.mt5_gateway` or
  `execution.executor`).

## Deploy note (explicit, per P18)

This branch (`feat/fx-runtime-error-structured-provenance`) is **not** merged into the
live scheduler's branch/main tree. Deployment to the live path is a separate decision by
a human/later package. If/when deployed, the change is additive and backward-compatible:
the new `journal/post_asian_pilot/runtime_error_log.json` file starts empty and
accumulates structured events only from the first cycle that runs the new code onward;
no existing file is migrated, rewritten, or required to change shape first, so deployment
would not require pausing the campaign or discarding in-flight observations.

## Classification

See the handback report for this session's exact `FOCUSED_TESTS`/`RELEVANT_REGRESSION`
result strings, `COMMIT_SHA`, and final `CLASSIFICATION`.
