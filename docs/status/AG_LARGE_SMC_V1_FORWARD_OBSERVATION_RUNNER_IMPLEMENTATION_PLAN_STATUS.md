# Large-SMC Forward Observation Runner -- Implementation Plan (not implemented)

Status: **PLAN_ONLY, NOT_IMPLEMENTED**. This task searched for an existing natural
forward-observation mechanism for `ST_LARGE_SMC_V1`, confirmed none exists, and stops
here with a plan rather than writing a runner under time pressure -- per this task's own
instruction ("if substantial architecture is missing: return a dedicated implementation
plan; do not cram it into" an unrelated task).

## Discovery: why a runner cannot be safely built as a small addition today

A forward (live) observation runner needs two things `LargeSMCResearchEngine.evaluate()`
already assumes are supplied to it:

```text
1. a Stage1Dataset of QualifiedEEvent objects (the E1/E2/E3 qualification layer)
2. an evaluation_time, with live D1/H1/M5 candle/tick access for that instant
```

(2) already works unpatched: `engine.py`'s own docstring notes it only calls
`historical_replay.stage2.get_latest_candles`/`.get_tick`/
`market_structure.tiers.analyze_structure_tiers`, all of which pass through to the real
MT5 connection when NOT wrapped in `historical_data_context` (that context manager is
what substitutes historical data for backtests; outside it, these calls are already
live). So the engine itself needs no new live-data plumbing.

**(1) does not exist for live use anywhere in this repository.** Searched
`src/`/`scripts/` for every `QualifiedEEvent`/`Stage1Dataset` reference:

```text
src/historical_replay/orchestrator.py   -- Stage1 qualification logic (E1/E2/E3), but
                                            only ever invoked against a frozen,
                                            pre-loaded historical candle series
                                            (see scripts/build_native_stage1.py)
src/historical_replay/stage1.py          -- QualifiedEEvent/Stage1Dataset types + the
                                            existing load_stage1_dataset() loader (reads
                                            an already-produced JSON file, does not
                                            produce one)
scripts/build_native_stage1.py           -- the ONLY producer of a Stage1Dataset in this
                                            repository, and it is explicitly an offline,
                                            batch, historical-CSV-driven tool
```

There is no code path that runs `orchestrator`'s E1/E2/E3 qualification against a
rolling live window ending at "now." Building a forward runner therefore requires
writing new logic to do that -- not merely scheduling an existing capability.

## Why this was not attempted as a "small" addition this task

Wiring live E-event qualification is not a thin wrapper: it means deciding (a) how much
trailing D1/H1/M5 history to fetch each run, (b) how to avoid re-qualifying the same
event on every run (the historical batch tool has no natural "already seen" concept --
that only exists downstream, in `proposals/occurrence_identity.py`, for *candidate*
occurrences, not E-event qualification itself), and (c) verifying the live-fetched
candle/tick data satisfies the same no-lookahead and closed-bar guarantees the frozen
historical CSV path already has tested (`historical_replay`'s own no-lookahead suite
covers the *replay* path, not a fresh live-qualification path). Implementing this
correctly, under this task's own explicit prohibition on inventing detection logic,
requires careful reuse of `orchestrator`'s existing qualification functions against live
data plus new, tested deduplication -- a real, multi-step engineering task, not
something safely finished as an afterthought alongside FX/BTC governance work in the
same session.

## Minimum safe next steps (not started)

```text
1. Confirm which orchestrator.py functions implement E1/E2/E3 qualification in a form
   that can be called against a live-fetched rolling window (not just a frozen CSV
   iterator) -- read-only investigation, no code change.
2. Define event-level deduplication explicitly (what makes "the same E-event" across
   two consecutive runs) -- a governance/design decision, analogous to how
   proposals/occurrence_identity.py already defines it one layer down.
3. Implement the smallest live qualifier reusing (1)'s functions, with its own focused
   no-lookahead/dedup tests, BEFORE wiring it to LargeSMCResearchEngine.evaluate().
4. Only then add the thin runner script + evidence ledger (per this task's own
   requested schema: strategy_id/version, run_id, event_id, occurrence_id, timestamp,
   data_cutoff, E/M model, entry, invalidation anchor, ATR14, C10 buffer, final stop,
   target, decision state, MAE/MFE/outcome once resolved) and, separately, scheduler
   installation (OS-level; report as pending, do not silently install).
```

## What this plan does NOT authorize

- Does not implement any part of steps 1-4 above.
- Does not modify `src/large_smc_research/` or `src/historical_replay/`.
- Does not create any observation, real or synthetic.
- Does not change `ST_LARGE_SMC_V1 v1.0.7`'s frozen semantics or C10 parameters.
