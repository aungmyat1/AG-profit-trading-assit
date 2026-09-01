# AG_TRADE_ASSISTANT_V1_0_2 Status (2026-09-01)

Scope: operational observability + restart recovery for the 2026-09-02 pilot. **This is
an application release, not a strategy release.** `ST_ASIAN_SWEEP_5R_V1` v1.1.1's
semantics, risk policy, and portfolio numbers are unchanged from V1.0.1 -- V1.0.2 only
adds reliability/reporting capabilities. `AG_TRADE_ASSISTANT_V1_0` and `AG_TRADE_
ASSISTANT_V1_0_1` (and their pilot config) are left byte-for-byte unchanged and remain
independently reproducible. See `docs/VERSION_HISTORY.md` for the full
application-vs-strategy version separation this release establishes.

## Fixes

**A. READY restart recovery (real defect, now fixed).** `store.decision_from_record()`
previously hardcoded `signal=None` on every reload, even though `save_decision()`
already recursively serializes the full `TradeSignal` into the persisted record
(`dataclasses.asdict`) -- the data was there, just discarded on the way back out. A
reloaded READY decision would silently downgrade to `NOT_READY` in `build_entry_
proposal()`, and a previously selected proposal could disappear from later reports. Now
`_signal_from_record()` reconstructs the same `TradeSignal` (setup/direction/entry/
stop_loss/risk_distance/signal_timestamp/box_high/box_low/box_mid/reason_code -- exactly
what `build_entry_proposal()` needs), so a restart reproduces the identical `setup_id`/
`proposal_id`/`ready_at`/geometry with zero re-evaluation and zero lookahead. Verified by
test (`test_ready_decision_restart_recovery_preserves_signal`).

**B. Immutable Asian snapshots.** `store.save_snapshot()` previously silently overwrote
a frozen snapshot if a later computation produced different OHLC for the same identity.
Now: identical re-freeze is an idempotent no-op; a genuinely different snapshot for an
already-frozen identity raises `SnapshotImmutabilityViolation` (mapped to decision reason
`SNAPSHOT_IMMUTABILITY_VIOLATION` in the pipeline); a corrupted/unreadable snapshot store
raises `StateStoreCorrupted` (mapped to `ASIAN_SNAPSHOT_CORRUPT`). Neither is ever
silently regenerated.

**C. Dedicated `--preflight` CLI.** `scripts/run_post_asian_pilot.py --preflight`
verifies release/strategy/fingerprint-baseline/session-contract/MT5/account-mode/
symbols/ledger/snapshot-store/reconciliation readiness ONLY -- never runs a strategy
cycle, claims a slot, mutates a snapshot, or sends an order (verified live, see below).
`--status` (one cycle) and `--watch` (continuous) keep their own distinct meanings.

**D. Event-driven `--watch` output.** Internal polling still runs every `--interval`
seconds, but operator-facing output now prints only on a per-symbol state change, a
READY, an operational error, or the execution window closing (which also renders the new
end-of-window report) -- never on an unchanged poll.

**E. Complete Entry Ticket.** `report.render_entry_ticket()` renders every field from
spec section 17: application (release id/fingerprint), strategy (id/version/fingerprint),
identity (ledger slot/proposal_id/setup_id), market (symbol/direction/setup_type/
ready_at), session (Asian high/low/mid/range/swept level/snapshot_id), entry/TP1/TP2,
75/25 allocation, risk (percent/amount/raw+normalized volume/estimated loss at SL),
portfolio (daily slots used, aggregate open risk), timing, evidence, decision, execution
status. Fields that aren't safely available (aggregate open risk, absent a live equity
fetch at render time) report the explicit string `UNAVAILABLE_NOT_WIRED`, never a
fabricated number. Also fixed a real gap along the way: `pipeline.py` was calling
`build_entry_proposal()` without ever passing `swept_level`, so it was always `None` --
now derived from `signal.box_high`/`box_low` by direction.

**F. End-of-window report.** `report.render_pilot_end_report()` reads ONLY persisted
journal state (decision store, ledger, counters) for both symbols -- never in-memory
results from a single cycle -- and classifies `PASS` / `PASS_WITH_OBSERVATIONS` (data
errors/disconnects seen) / `BLOCKED` (snapshot conflict). Wired into `--watch`, which
renders it automatically the first time it observes the execution window has closed.

**G. Monitoring counters.** New `monitor.MonitoringCounters` (lightweight, per-trading-day
event counts, not per-poll telemetry): MT5 disconnects, data errors, stale-data events,
new-closed-M15 cycles, READY transitions, proposals created, restart-recovery events,
duplicate-suppressed writes, snapshot conflicts. Wired into the pipeline at each relevant
point.

**H. Journal hygiene.** `journal/post_asian_pilot/` (confirmed, by audit, to be pure
runtime state -- no fixtures) is now gitignored; the 3 previously-tracked files were
untracked (`git rm --cached`, files preserved locally, not deleted). `journal/ag_
daytrading_last_closed_bar.json` and other pre-existing, unrelated-process journal files
were left untouched, as were `.env` (already gitignored, confirmed by test) and every
canonical fixture/golden-oracle artifact.

## Release

`config/releases/AG_TRADE_ASSISTANT_V1_0_2.yaml` -- reuses `config/pilot/
AG_POST_ASIAN_LONDON_PILOT_V1_0_1.yaml`'s risk/portfolio numbers verbatim (no new pilot
policy file; nothing about risk/portfolio changed) and adds an `application_capabilities`
block documenting what's new. `pilot_config.DEFAULT_RELEASE_CONFIG_PATH` now points here;
V1.0 and V1.0.1's release paths remain separately addressable constants.

## Tests

```
pilot focused (tests/test_post_asian_pilot.py)  = 58 passed (was 51)
  new: restart recovery, snapshot immutability (idempotent/conflict/corrupt),
  complete entry ticket, end-of-window report (no-trade + data-error days),
  journal-hygiene gitignore check
existing regression (strategy_engine/execution)  = 57 passed, unmodified
golden vertical slice (frozen replay)             = 10 passed, unmodified
broader repository suite (run once)                = 1188 passed, 0 failures, 0 skips
```

## Live read-only validation -- PASSED

MT5 was reachable this session. `python scripts/run_post_asian_pilot.py --preflight
--json`: all 11 checks PASS, `pilot_status=READY_TO_MONITOR`. `python scripts/
run_post_asian_pilot.py --status`: both EURUSD/GBPUSD correctly `WATCH` (window not yet
open at the time of the run), no fabricated READY. The Asian snapshot for 2026-09-01 was
frozen for real, for both symbols, and confirmed still present alongside the earlier
2026-08-31 snapshot (immutability, additive, working as intended).
`order_check`/`order_send` calls: 0 (structurally impossible -- verified by test and
grep).

## V1.0.1 behavioral equivalence

Verified by construction, not a separate test: there is no version-conditional strategy
code path in `pipeline.py`/`proposal.py`/`decision.py` -- V1.0.1 and V1.0.2 run the exact
same `strategy_engine.evaluate()` -> `build_entry_proposal()` chain. The only things
V1.0.2 changed are restart-recovery/immutability/reporting/CLI/monitoring, all of which
sit either upstream (persistence) or downstream (rendering) of that chain, never inside
it.

## First unresolved requirement

None blocking. `execution_integration = NOT_WIRED` remains explicit and honest, per
spec -- `governor.evaluate_execution_eligibility()`/`validate_slot_ownership()` are
durable-contract primitives for a future, separate execution workflow; nothing in this
release calls them from a real execution path, and the report never claims otherwise.

NEXT_RELEASE = `AG_TRADE_ASSISTANT_V1_1` (deferred). `ST_ASIAN_SWEEP_5R_V1` remains
v1.1.1.
