# AG_TRADE_ASSISTANT_V1_0_1 Status (2026-09-01)

Scope: operational hardening of `AG_TRADE_ASSISTANT_V1_0` for the 2026-09-02 pilot --
`ready_at`-based (never wall-clock) selection ordering, a two-slot daily opportunity
ledger with real cross-process atomic claims (both EURUSD and GBPUSD may be selected the
same day, one slot each), `max_open_positions=2` with a `1.0%` aggregate-open-risk gate,
and a preflight readiness check. `AG_TRADE_ASSISTANT_V1_0` (`config/releases/
AG_TRADE_ASSISTANT_V1_0.yaml`, `config/pilot/AG_POST_ASIAN_LONDON_PILOT_V1.yaml`) is left
byte-for-byte unchanged and remains independently loadable -- V1.0.1 is a new,
superseding release, not a mutation. `ST_ASIAN_SWEEP_5R_V1`'s own strategy semantics
(sweep qualification, entry/SL/TP1/5R-runner/75-25 allocation, canonical session
definitions) are untouched.

## 1. `ready_at` (not `evaluation_time`)

`strategy_engine.models.TradeSignal` gained an additive, backward-compatible
`signal_timestamp: Optional[datetime] = None` field (`strategy_engine/models.py`),
populated in `strategy_engine.engine.evaluate()` from the underlying
`SetupDecision.signal_timestamp` (the qualifying CLOSED M15 candle's own open time --
already computed by `entry_2_sweep`, just not previously surfaced). `PostAsianDecision.
ready_at` is derived from this field; a READY sweep decision with no `signal_timestamp`
raises (`ValueError`) rather than silently falling back to polling time -- this is the
literal STOP condition the spec named ("ready_at cannot be derived from authoritative
strategy evidence"), and it never actually fires because `entry_2_sweep` always sets it.
Ordering (`tiebreak.order_candidates`) sorts purely on `ready_at`, never
`evaluation_time`.

## 2. Two-slot daily opportunity ledger

`governor.DailyTradeLedger` replaces the earlier single-slot design: up to `max_slots=2`
opportunities per `strategy_id`+`trading_date`, at most one per symbol. Claims are
atomic across processes via `_ExclusiveFileLock` -- real OS-level exclusive file
creation (`os.O_CREAT | os.O_EXCL`, atomic on both Windows and POSIX), not an
in-process `threading.Lock`. Re-claiming the exact same identity
(`symbol`+`setup_id`+`proposal_id`) is idempotent success, which is what makes crash
recovery safe: a process that crashed after claiming but before persisting its proposal
simply re-derives the same deterministic identity (proposal_id is a pure function of
`signal_id` = `strategy_id:pair_id:symbol:session_date`, not of `ready_at` or wall-clock
time) and re-claims it on restart. Terminal states (`EXECUTED`/`EXPIRED`/`DECLINED`)
never free a slot back to capacity; only `CLAIMED` may transition (`transition()`), and
this pilot's own pipeline never calls it -- only a later, separate, explicit execution
workflow would.

Pipeline ordering (`pipeline.run_pilot_cycle`): evaluate both symbols -> persist
decisions -> order READY candidates by `ready_at` -> for each, build the proposal
*candidate* in memory -> atomically claim -> only on claim success is the proposal
persisted with `actionable=True`; a losing/blocked candidate's proposal is still
persisted (research evidence) but `actionable=False`. Nothing is published as actionable
before it owns a ledger slot.

## 3. `max_open_positions=2` + aggregate open-risk gate

The existing shared `execution.position_guard.OpenPositionGuard` is a **global,
cross-strategy** guard hardcoded to 1 -- deliberately left untouched (weakening it would
affect every other strategy). This pilot's own `max_open_positions=2` is a
**strategy-scoped** count over the same store (`governor.strategy_open_position_count`,
filters by `strategy_id`), and `governor.strategy_open_risk_pct` sums each open
position's *original* `risk_amount` at open time (never a breakeven-aware
mark-to-market recalculation -- no trustworthy existing primitive for that) as a
conservative/fail-closed percentage of equity. `evaluate_execution_eligibility()`
checks slot ownership, position count, aggregate risk, and both loss guards, in that
order -- built for the later, separate, explicit execution workflow; this pilot's own
selection pipeline never calls it (selection only checks the loss guards, per spec
section 17: open-position/aggregate-risk capacity gates execution, not selection).

## 4. Credentials

Nothing in `src/post_asian_pilot/` references `.env`, `os.environ`, or `getenv`
(verified by test — grepping the actual source). MT5 connects via the already
logged-in desktop terminal (`mt5.connection.connect()` -> `mt5.initialize()`, no
credentials needed). `.env` was not read, opened, or staged at any point in this work.
`.gitignore` already excludes `.env`.

## 5. Fingerprints

`report.release_fingerprints()` hashes the release manifest (which includes
`selection_policy` -- capacity, priority, `ready_at` source), strategy YAML, canonical
session config, and pilot risk config (now including `max_open_positions`,
`max_aggregate_open_risk_pct`) via the same canonical-JSON SHA-256 technique proven in
the golden vertical slice. V1.0's release/strategy/session fingerprints are unchanged
(verified by test); V1.0.1's `release_fingerprint` and `selection_policy_fingerprint`
are new and distinct, since V1.0 has no `selection_policy` section at all.

## 6. Tests

```
pilot focused (tests/test_post_asian_pilot.py)     = 51 passed
  incl. ready_at semantics (CASE A/B), candidate ordering (A-E),
  atomic ledger claims (concurrent, via real OS-level lock races),
  same-symbol-second-setup block, terminal-state non-recycling, restart
  preservation, corrupt-ledger fail-closed, non-owner-execution block,
  max_open_positions=2 / aggregate-risk-gate pass+block cases,
  preflight (offline, monkeypatched), .env/credential exclusion
existing regression (strategy_engine/execution)     = 57 passed, unmodified
broader repository suite (run once)                  = 1161 passed, 20 skipped
                                                        (skips are live-MT5-gated tests --
                                                        MT5 was unreachable during this run,
                                                        see section 7), 0 new failures
```

## 7. Live read-only validation -- BLOCKED (environmental, not code)

`python scripts/run_post_asian_pilot.py --status` failed four consecutive attempts with
`MT5_INITIALIZE_FAILED: (-10005) IPC timeout` -- the MT5 terminal itself is currently
unreachable (the broader suite's own live-MT5-gated tests skipped for the same reason in
the same window, confirming this is an environmental terminal-availability issue, not a
regression in this code). **This step needs to be retried before the 2026-09-02 pilot
window** -- recommend running `python scripts/run_post_asian_pilot.py --status` again
once the MT5 terminal is confirmed reachable (e.g. via the `market-data` skill or a
direct `mt5.connection.connect()` check), ideally shortly before the 13:30 Myanmar-time
preflight.

## 8. Not implemented in this pass (deferred, per spec)

Real OS-process-level concurrency tests (covered instead via `ThreadPoolExecutor` racing
on the identical real exclusive-file-creation lock every process would use -- the
mechanism under test is process-agnostic); a live execution-gateway wiring of
`evaluate_execution_eligibility()`/`validate_slot_ownership()` (built as the durable
contract primitives, not yet called from any real execution path since this pilot stays
proposal-only); SMC/tick-volume/order-flow/Large-SMC/High-R:R/New-York-cycle/crypto —
all explicitly out of scope per spec.

## 9. First unresolved requirement

None blocking. The one open item is operational, not a code gap: confirm MT5
reachability before tomorrow (section 7).

NEXT_RELEASE = AG_TRADE_ASSISTANT_V1_1 (deferred until after the pilot is operationally
stable, per spec's own closing instruction).
