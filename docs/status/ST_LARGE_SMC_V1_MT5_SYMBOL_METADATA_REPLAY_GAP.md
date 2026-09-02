# MT5 Symbol-Metadata Replay Gap — Discovered During ST_LARGE_SMC_V1 OUTCOME_LIFECYCLE_V1

Status: **RESOLVED (2026-09-02, `ST_LARGE_SMC_V1_REPLAY_METADATA_DECOUPLING_V1`)**, per
explicit owner authorization of a dataset-bound historical `tick_size`. See
`docs/status/ST_LARGE_SMC_V1_REPLAY_METADATA_DECOUPLING_V1_STATUS.md` for the full
fix, parity proof, and corrected-replay evidence. This document is retained as the
original disclosure record.

Original disclosure below (2026-09-02, `OUTCOME_LIFECYCLE_V1`): **DISCLOSED, NOT FIXED
— SHARED_CHANGE_REQUIRED**.

## What was found

While wiring `LargeSMCResearchEngine.evaluate()` into a real historical replay for the
first time (`scripts/run_large_smc_outcome_lifecycle_check.py`, targeted at the three
previously-known September 2025 READY-equivalent occurrences), every call to C11's
target-model adapter failed with `SYMBOL_METADATA_MISSING`:

```
market_structure.tiers.analyze_structure_tiers("EURUSD", "M5")
  -> get_symbol_meta("EURUSD")  # mt5/symbol_resolver.py
  -> requires a live, connected MT5 terminal (symbol_info() IPC call)
  -> raises SymbolMetaError during historical replay (no terminal connected)
  -> analyze_structure_tiers catches it internally, returns status="SYMBOL_METADATA_MISSING"
```

`historical_replay/data_source_patch.py` patches `get_latest_candles`/`get_tick` for
every consumer module that needs them (its own module docstring lists the exact
targets), but **never patches `mt5.symbol_resolver.get_symbol_meta`**. Nothing in that
patch target list mentions symbol metadata at all.

## Why this matters beyond C11

`market_structure.tiers.analyze_structure_tiers` is not new to this phase —
`historical_replay/stage2.py::_m5_side_primitives` already calls it, unconditionally,
on every M5 step, to build M1's inducement-candidate list:

```python
tiers = analyze_structure_tiers(symbol, "M5")
if tiers.status == "VALID" and tiers.external is not None and m5_liq.status == "LIQUIDITY_OK":
    ...
```

Because `analyze_structure_tiers` fails closed *internally* (returns a result object,
never raises), this condition silently evaluates `False` whenever historical replay is
running, and `inducement_candidates` stays empty — every single time, for every symbol,
in every historical replay that has ever run against this codebase.

This directly explains a finding recorded in multiple prior status documents as
research evidence rather than a defect: **M1 has never once formed an entry array in
any sampled historical window**, including a 2-week sample with 5/5 confirmed
inducement-sweep sequences
(`docs/specs/LARGE_SMC_V1_SPEC.md` §32: *"Zero entry arrays formed in either sampled
window (`ENTRY_ARRAY_CREATED=0`) despite 5/5 confirmations"*, classified there as
`INSUFFICIENT_EVIDENCE`, "a valid research result, not a defect to fix"). That
classification was made in good faith but is now known to be at least partly wrong: M1
could not have formed an entry array in *any* replay, live-market conditions aside,
because its inducement-candidate detection has been silently starved by this gap the
entire time. This does not necessarily mean M1 would perform differently live — it
means the *historical evidence* gathered so far cannot distinguish "M1 genuinely rarely
qualifies" from "M1's inducement-candidate detection was never actually exercised in
replay."

## Scope of this disclosure

This phase (`ST_LARGE_SMC_V1_OUTCOME_LIFECYCLE_V1`) does **not** fix this gap. Doing so
means changing `historical_replay/data_source_patch.py`, which is shared with the live
`SMC_CONDITIONAL_ENTRY_V2` watcher (`daily_routine/m5_execution.py`) — a
`SHARED_CHANGE_REQUIRED` decision, the same class of deferral already used for C14B's
lifecycle-store migration. Fixing it correctly would need:

- a historical stand-in for `SymbolMeta` (tick_size, contract size, volume step) keyed
  by symbol, not live-queried;
- verification that every existing consumer of `get_symbol_meta` during replay
  (`market_structure/tiers.py`, and any other caller reachable during
  `historical_data_context`) tolerates the substitution identically to the live path;
- re-running the golden vertical slice / `TRUE_STAGE2_ORACLE_RECONCILIATION` regression
  to confirm no semantic change, since M1's historical behavior would likely change
  once inducement candidates can actually be detected.

That is a meaningfully larger, cross-cutting change than this additive research phase's
own mandate ("smallest possible additive change," zero redetection, no modification to
shared frozen modules). It is recorded here as its own decision point for future
authorization.

## What this engine does correctly in the meantime

`src/large_smc_research/engine.py`'s target-selection branch now distinguishes this
case explicitly: a target-model failure whose `reason` is anything other than the
genuine C11 outcome `REJECT_NO_TARGET` (e.g. `MISSING_DIRECTION_OR_STRUCTURE_TIER`)
fails closed to `DATA_ERROR`, never a silently-plausible `NO_TRADE`. This was itself a
bug found and fixed during this same phase (see
`docs/status/ST_LARGE_SMC_V1_OUTCOME_LIFECYCLE_V1_STATUS.md`) — before the fix, all
three known September occurrences were misreported as `NO_TRADE:REJECT_NO_TARGET`,
which would have read as a legitimate (if uninteresting) trading conclusion rather than
the data problem it actually is.

## Recommended next step (superseded — see resolution below)

~~Treat this as a new, separate decision point: authorize (or decline) a historical
stand-in for `get_symbol_meta` in `historical_replay/data_source_patch.py`, scoped
narrowly to symbol metadata only, with its own regression proof against the existing
golden fixtures before any Large-SMC or live-watcher behavior is considered to rely on
it.~~

## Resolution (2026-09-02)

The owner authorized a dataset-bound historical `tick_size = 0.00001` for
`EURUSD_M5_202504211715_202607310000` (fingerprint-verified,
`HISTORICAL_ANALYSIS_ONLY` scope only). Implemented as
`historical_replay/symbol_metadata_manifest.py` (loader/validator) +
`historical_data_context`'s new opt-in `symbol_metadata_manifest` parameter, patching
exactly the one call site (`market_structure.tiers.get_symbol_meta`) both C11 and M1's
inducement detection go through — no fabricated broker metadata, no live-behavior
change (verified: the live watcher never enters `historical_data_context` at all).
Corrected September 2025 replay: M1 now genuinely detects inducement candidates
(0→1 at the same timestamp) and produces one new READY-equivalent occurrence (E1M1);
every other combination cell is byte-identical to the pre-fix run. Full evidence:
`docs/status/ST_LARGE_SMC_V1_REPLAY_METADATA_DECOUPLING_V1_STATUS.md`.
