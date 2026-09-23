# AG Asian Sweep -- Runtime-Error Provenance Reconciliation (2026-09-23)

Dated evidence snapshot per `docs/status/LIVE_STATUS_MAINTENANCE.md`. Continuation of
`AG_V1_0_3_FX_SHADOW_SERIES_002` (`ST_ASIAN_SWEEP_5R_V1`, FX proposal-only shadow
qualification toward 20 VALID DAYS). **No new strategy cycle was run, no order was
placed, no historical evidence was mutated or replayed this session.** This document
resolves the classification provenance of `operations.runtime_errors` for the four days
left `PENDING_RECONCILIATION` by the immediately-prior session
(`docs/status/AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_SERIES_002_BACKLOG_RECONCILIATION_STATUS.md`).

## P0 -- baseline verified from artifacts

Read the prior session's status document directly (not assumed). Confirmed campaign
state before this session:

```text
VALID (4):    2026-09-09, 2026-09-11, 2026-09-15, 2026-09-21
INVALID (5):  2026-09-04, 2026-09-07, 2026-09-08, 2026-09-10, 2026-09-17
PENDING (4):  2026-09-14, 2026-09-16, 2026-09-18, 2026-09-22
```

Series 001 Day 1 (2026-09-02, `EXCLUDED_DAY`) remains the separate, non-counting
predecessor observation -- not touched, not reopened.

## P1/P2 -- runtime_errors source trace and semantics

Bounded provenance map, read once from source (no source file edited):

```text
src/post_asian_pilot/pipeline.py::_evaluate_pair  (3 increment sites)
  1. get_candles(asian reference window) raises MarketDataError        (line ~127)
  2. build_asian_session_snapshot(...) returns status == "DATA_ERROR"  (line ~138)
  3. get_candles(post-session execution window) raises MarketDataError (line ~173)
     -> stores.counters.increment(strategy_id, trading_date, COUNTER_DATA_ERRORS)
     -> immediately, same call: save_decision(..., data_error_decision(..., STATUS_DATA_ERROR))
        for that exact (strategy_id, symbol, trading_date, reference_session) unit

src/post_asian_pilot/monitor.py::MonitoringCounters
  COUNTER_DATA_ERRORS = "data_errors"; increment() only adds, never decrements or resets
  intraday; keyed by (strategy_id, trading_date) per pilot state_dir (i.e. per cycle:
  ASIAN_LONDON and LONDON_NEWYORK each have their own counters store/file)

src/post_asian_pilot/store.py::save_decision
  key = (strategy_id, symbol, trading_date, reference_session) -- a LATER call with a
  differing (status, reason_codes, missing_condition) signature OVERWRITES the prior
  record for the same key; the store is last-write-wins per unit, not append-only

src/post_asian_pilot/report.py::render_pilot_end_report  (line 276)
  operations.runtime_errors = counters["data_errors"]   -- a direct, unmodified copy of
  the aggregate counter, not re-derived from current decision state
  result = "PASS_WITH_OBSERVATIONS" if (any current DATA_ERROR decision) OR
           counters["data_errors"] > 0 OR counters["mt5_disconnects"] > 0 else "PASS"

src/post_asian_pilot/daily_fx_report.py::build_fx_daily_report
  pure passthrough: calls render_pilot_end_report once per cycle (ASIAN_LONDON,
  LONDON_NEWYORK -- same pipeline/report/monitor code, different pilot config/state_dir),
  adds no new increment/aggregation logic of its own

scripts/run_fx_daily_report.py -> journal/reports/fx/2026/<date>.json
  archives the above dict verbatim (verified this session: no source file changed)
```

**Semantics determined (Category B, from source, not inferred from field name):**
`operations.runtime_errors` is an aggregate, monotonically-increasing, intraday count of
transient data-fetch/snapshot failures. It is **not** re-derived from the current/final
persisted decision state, and the counter itself carries no per-event provenance (no
timestamp, unit id, error class, or recovery flag -- see P10 below). Because every
increment site unconditionally persists a `STATUS_DATA_ERROR` decision in the same call,
and because `save_decision` overwrites on any later differing-signature write, **a
nonzero `runtime_errors` count together with a current terminal state that is NOT
`DATA_ERROR` for every unit is only possible if an earlier failed attempt was later
overwritten by a successful one.** This is Category (B) from the mission's taxonomy:
"operational error with successful authoritative recovery -- initial attempt failed,
retry completed, all required units have authoritative final outcomes." It is not (A)
(the frozen Data-Error Contract keys `DATA_ERROR`/`SYSTEM_COULD_NOT_EVALUATE` off current
`pr.decision.status`, not off the aggregate counter -- see
`AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_VALIDATION_STATUS.md`, "Data-error contract"
section), and it is not (D)/ambiguous, because the overwrite conclusion follows
deterministically from the store's own key/overwrite semantics plus the observed final
persisted state, not from a favorable guess.

## P3 -- per-date evidence (`journal/reports/fx/2026/<date>.json` + both pilots'
`monitoring_counters.json`, read-only; no strategy rerun)

```text
DATE          CYCLE            runtime_errors  new_closed_m15_cycles  units (final_strategy_state / final_reason)
2026-09-14    ASIAN_LONDON     1               25   EURUSD NO_TRADE (NON_SWEEP_SETUP_OUT_OF_SCOPE)
                                                     GBPUSD WATCH (NO_SETUP_BY_WINDOW_END)
              LONDON_NEWYORK   0               24   EURUSD NO_TRADE (NON_SWEEP_SETUP_OUT_OF_SCOPE)
                                                     GBPUSD READY (LOWER_SWEEP_STRICT_PENETRATION, proposal claimed)
2026-09-16    ASIAN_LONDON     1               25   EURUSD READY (UPPER_SWEEP_STRICT_PENETRATION, proposal claimed)
                                                     GBPUSD NO_TRADE (NON_SWEEP_SETUP_OUT_OF_SCOPE)
              LONDON_NEWYORK   0               24   EURUSD READY (LOWER_SWEEP_STRICT_PENETRATION, proposal claimed)
                                                     GBPUSD NO_TRADE (NON_SWEEP_SETUP_OUT_OF_SCOPE)
2026-09-18    ASIAN_LONDON     1               28   EURUSD WATCH (NO_SETUP_BY_WINDOW_END)
                                                     GBPUSD WATCH (NO_SETUP_BY_WINDOW_END)
              LONDON_NEWYORK   0               2    EURUSD EXPIRED (NO_SETUP_BY_WINDOW_END)
                                                     GBPUSD READY (LOWER_SWEEP_STRICT_PENETRATION, proposal claimed)
2026-09-22    ASIAN_LONDON     0               6    EURUSD READY (LOWER_SWEEP_STRICT_PENETRATION, proposal claimed)
                                                     GBPUSD READY (LOWER_SWEEP_STRICT_PENETRATION, proposal claimed)
              LONDON_NEWYORK   1               21   EURUSD WATCH (NO_SETUP_BY_WINDOW_END)
                                                     GBPUSD WATCH (NO_SETUP_BY_WINDOW_END)
```

For every affected cycle: exactly one `data_errors` increment against 21-28 successful
`new_closed_m15_cycles` that same trading day; zero units currently show
`final_strategy_state == "DATA_ERROR"`; every unit carries a real strategy-engine reason
code (not a placeholder/default), i.e. positive completeness evidence (P5), not merely
"no known error." `duplicate_proposals_suppressed` is nonzero on most cycles -- same
`EXPECTED_REPLAY_OR_RESTART_REUSE` pattern already accepted for the 4 already-VALID days
in the prior session's document (idempotent re-poll behavior, not an anomaly; Duplicate
Contract). `duplicate_claims = 0`, `order_check_calls = 0`, `order_send_calls = 0`,
`automatic_execution = DISABLED` on every cycle, every date.

```text
DATE          runtime_errors_explained  data_error_present  evidence_sufficient  classification    reason
2026-09-14    YES (Category B)          NO                  YES                  VALID_DAY (#5)    transient error, later poll same day/unit recovered; all 4 units deterministic, non-DATA_ERROR
2026-09-16    YES (Category B)          NO                  YES                  VALID_DAY (#6)    same pattern
2026-09-18    YES (Category B)          NO                  YES                  VALID_DAY (#7)    same pattern; LONDON_NEWYORK EURUSD=EXPIRED is a contract-legitimate VALID_DAY terminal outcome
2026-09-22    YES (Category B)          NO                  YES                  VALID_DAY (#8)    same pattern
```

## P4 -- contract application (frozen, not reinterpreted)

`AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_VALIDATION_STATUS.md` (2026-09-03, frozen) was read
once. Two existing clauses directly determine these four days, applied as written, no new
rule invented:

- **Data-error contract**: "`DATA_ERROR` is never converted to `NO_TRADE`... this
  distinction is already structurally available via `pr.decision.status`." The
  contract's authority is the *current persisted decision status*, not the aggregate
  operations counter. No unit on any of the 4 days currently has `pr.decision.status ==
  STATUS_DATA_ERROR`.
- **Restart contract**: "A restart does not automatically invalidate a day... If restart
  recovery preserves frozen behavior... the day may remain `VALID_DAY`." The scheduler
  invokes `run_fx_cycle_once.py` repeatedly (Windows Task Scheduler, "--once" runner per
  the prior session's verified description), so each poll is effectively a fresh
  process run against durable state -- exactly the restart pattern the contract
  addresses. Source evidence (P1/P2) shows the anomaly is reconciled: a later poll
  produced the authoritative, currently-persisted terminal decision.

No new classification rule was created to handle these four days; both clauses already
existed in the frozen contract before this session.

## P5/P6 -- positive completeness and contractual basis

Not classified VALID merely for "no known error": each unit's `final_reason` is a real
strategy reason code (`NON_SWEEP_SETUP_OUT_OF_SCOPE`, `NO_SETUP_BY_WINDOW_END`,
`UPPER_SWEEP_STRICT_PENETRATION`, `LOWER_SWEEP_STRICT_PENETRATION`), i.e. positive
evidence the strategy engine actually ran to a deterministic conclusion for that unit.
Not classified INVALID merely because `runtime_errors > 0`: the underlying event (a
transient `MarketDataError`/snapshot-build failure on one poll, superseded by a
successful later poll for the same unit) is not one of the frozen `INVALID_DAY` triggers
(mandatory data incomplete, unexplained duplicate, cross-cycle contamination, corrupted
ledger, inconsistent restart reconstruction, missing mandatory evidence) -- the mandatory
data is present and complete in the current persisted state.

## P7 -- retry semantics confirmed, schema limitation documented

Confirmed pattern: attempt 1 (one poll) -> `MarketDataError`/`DATA_ERROR` snapshot ->
`data_errors` counter += 1, `STATUS_DATA_ERROR` decision persisted -> attempt N (a later
poll same day) -> success -> decision overwritten with the authoritative final state.
The frozen contract's Restart Contract says the successful final evidence keeps the day
eligible for `VALID_DAY` when reconciled, which this evidence satisfies. **Confirmed
schema limitation**: the current `data_errors`/`runtime_errors` aggregate counter loses
the distinction between "failed permanently" and "failed once then recovered" -- it can
only be disambiguated today by cross-referencing the per-unit final decision state and
`new_closed_m15_cycles` count, as done manually in this document. `report.py`'s own
`result` field (`PASS` vs `PASS_WITH_OBSERVATIONS`) inherits the same ambiguity, since it
also keys off the raw counter rather than current state alone.

## P9 -- no production code change required

All four dates were deterministically classified from already-persisted evidence. No
production code change was required or made this session.

## P10 -- prospective structured-provenance requirement (spec only, not implemented)

For future observations, `operations.runtime_errors` should be deterministically
explainable without manual cross-referencing. Recommended fields, scoped to the
identified need only (not a telemetry redesign): per data-error event ->
`timestamp`, `symbol` (unit id), `operation` (which of the 3 `_evaluate_pair` call
sites), `error_class`/`reason_code`, `recovered` (bool: was a later successful decision
persisted for the same unit same day), and `final_state` (the unit's current terminal
decision status at report time). Next package name (spec only, per mission transition
rules): `FX_RUNTIME_ERROR_STRUCTURED_PROVENANCE_REMEDIATION`.

## P12/P13 -- campaign counts and continuity

```text
valid_days     = 8/20   (2026-09-09, 09-11, 09-14, 09-15, 09-16, 09-18, 09-21, 09-22)
invalid_days   = 5      (2026-09-04, 09-07, 09-08, 09-10, 09-17 -- unchanged)
pending_days   = 0
excluded_days  = 0      (Series 001 Day 1 preserved, non-counting, untouched)
valid_remaining_to_20 = 12
CAMPAIGN_RESET = NO -- no evidence campaign integrity was broken; this session only
                       reclassified 4 already-collected days using an existing frozen
                       contract clause the prior session had not yet traced to source.
```

## P15/P16 -- protected areas and side-effect firewall

```text
strategy logic          = UNCHANGED    strategy config        = UNCHANGED
strategies/registry.yaml = UNCHANGED    execution               = UNCHANGED
MT5 order path            = UNCHANGED    R5C                       = UNCHANGED
frontend                    = UNCHANGED
historical raw evidence mutated                = NO
historical strategy reruns used as replacement = 0
broker order_check_calls = 0   broker order_send_calls = 0
demo_orders_sent          = 0   live_orders_sent         = 0
scheduler                                                = UNCHANGED, continues normally
state/fx_schedule/slot_ledger.json                       = NOT TOUCHED (pre-existing,
                                                            unrelated in-progress change,
                                                            preserved exactly as found)
Large-SMC friction-campaign artifacts (artifacts/validation/ST_LARGE_SMC_V1/...)  = NOT
                                                            TOUCHED
```

## Files changed this session

```text
NEW:      docs/status/AG_ASIAN_SWEEP_RUNTIME_ERROR_PROVENANCE_RECONCILIATION_STATUS.md
MODIFIED: PROJECT_STATUS.md (new rolling-snapshot section; prior
          AG_V1_0_3_FX_SHADOW_SERIES_002_BACKLOG_RECONCILIATION section preserved
          unchanged below it, per historical-evidence preservation)
NOT TOUCHED: strategies/registry.yaml, any src/*.py, any config/*.yaml,
          state/fx_schedule/slot_ledger.json, any journal/* raw evidence file,
          any artifacts/validation/ST_LARGE_SMC_V1/* file
```

## Classification

**`RUNTIME_ERROR_PROVENANCE_RESOLVED`**

## Safety state at completion

`ST_ASIAN_SWEEP_5R_V1` `demo_authorized = false` (unchanged), `risk_per_trade_pct =
UNRESOLVED` (unchanged), automatic execution disabled, Live authorization disabled,
Demo orders = 0, Live orders = 0.

## Next authorized step

1. Continue the scheduler (already running, unchanged) toward the remaining 12 VALID
   days needed.
2. Re-run `scripts/run_fx_daily_report.py --date 2026-09-23 --json` once both today's
   checkpoints (11:00 UTC ASIAN_LONDON, 15:00 UTC LONDON_NEWYORK) have passed.
3. `FX_RUNTIME_ERROR_STRUCTURED_PROVENANCE_REMEDIATION` (P10 above) is available as a
   scoped, prospective, non-strategy, non-execution reporting improvement whenever a
   maintainer chooses to schedule it -- not required to continue the campaign, since
   every currently-pending day was already resolvable from existing evidence.
4. Do not set `demo_authorized: true`, do not resolve `risk_per_trade_pct`, do not
   change any strategy/session/filter parameter in response to the above.
