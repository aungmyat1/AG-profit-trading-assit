# TD-1 — Top-Down Market Context: Contract Freeze

**Status:** COMPLETE (contract-only). Follows TD-0 (`AG_TD0_TOPDOWN_CONTEXT_AUDIT`,
READY_FOR_TD1).

## What this is

Freezes the additive data contracts for the shared, advisory, multi-timeframe
Top-Down Market Context framework (W1 → D1 → H4 → H1 → M15 → M5). No market data is
fetched, no indicator/structure/liquidity calculation happens, no cache/scheduler
exists, and no strategy consumes any of it. Every contract is a frozen dataclass
populated later, by a caller, from already-authoritative facts computed elsewhere.

## Architectural correction from TD-0

TD-0 found `src/mtf_context/` already exists as a `WRAPPER_ONLY` / `ADVISORY_ONLY`
multi-timeframe orchestrator (`MTFContext`/`MTFProfile`, role-based, not a fixed
hierarchy). TD-1 **extends that package** (`src/mtf_context/topdown_contracts.py`)
rather than creating a parallel `src/topdown_context/` package. It imports `AUTHORITY`
from `mtf_context.models` rather than redefining it, and inherits
`tests/test_mtf_context_execution_guard.py`'s existing AST scan (which already covers
every `*.py` under `src/mtf_context`) automatically — no new guard was written.

## Files changed

- `src/mtf_context/topdown_contracts.py` — **new**. Canonical timeframe registry,
  `TimeframeRequirement`, `StructureFact`, `WeeklyContext`, `DailyContext`,
  `H4Context`, `H1Context`, `M15Context`, `M5Context`, `TopDownContext`,
  `compute_context_id()`.
- `src/mtf_context/__init__.py` — extended (additive imports/`__all__` entries only;
  no existing export removed or changed).
- `tests/test_topdown_context_contracts.py` — **new**, 33 tests.
- `docs/status/TD1_TOPDOWN_CONTEXT_CONTRACT_STATUS.md` — this document.

No other file was modified. `src/mtf_context/models.py` and `orchestrator.py` are
untouched; no strategy code, YAML, proposal code, risk code, or execution code changed.

## Timeframe contract

New, independent, additive registry in `topdown_contracts.py`:

```
TIMEFRAME_W1, TIMEFRAME_D1, TIMEFRAME_H4, TIMEFRAME_H1, TIMEFRAME_M15, TIMEFRAME_M5, TIMEFRAME_M1
TOPDOWN_TIMEFRAMES = (W1, D1, H4, H1, M15, M5)          # TopDownContext V1 scope
ALL_CANONICAL_TIMEFRAMES = TOPDOWN_TIMEFRAMES + (M1,)   # M1 kept for execution-oriented consumers only
```

TD-0 found 4+ independent, mutually inconsistent timeframe dicts already in the repo
(`mt5/market_data.py`, `historical_replay/candle_store.py`,
`strategy_contract/market_snapshot.py`, `smc_map/models.py`), none including `W1`.
**None of those are rewritten in TD-1** (explicitly out of scope, per mission).
This registry is new and independent; later work packages may adopt it incrementally.

## Structure semantics

`structure_definition_id = SMC_MARKET_STRUCTURE_V1`

TD-0 found at least 6 incompatible BOS/MSS/CHOCH implementations/vocabularies across
the repo. TD-1 does **not** unify them. `StructureFact.structure_definition_id` is
mandatory and validated against a whitelist (`ALLOWED_STRUCTURE_DEFINITION_IDS`) that
currently contains exactly one entry, `SMC_MARKET_STRUCTURE_V1` — matching the
`market_structure/tiers.py` + `market_structure/smc_adapter.py` (smartmoneyconcepts-
derived) semantics that `strategies/ST_LARGE_SMC_V1.yaml` already names. An empty or
unqualified `structure_definition_id` (e.g. bare `"BOS"`) raises
`InvalidStructureDefinitionError`. There is no unqualified `bos`/`choch`/`mss`/
`structure` field anywhere in this contract.

- `SSC_semantics_changed = false` — `session_sweep_continuation/swing_structure.py`'s
  own hand-rolled BOS detector is untouched and not represented in this contract.
- `LSR_semantics_changed = false` — `strategy_engine/sweep_retest/mss.py`'s own MSS
  concept is untouched and not represented in this contract.

## Parent lineage

```
WeeklyContext
  ↓ (DailyContext.parent_weekly_context_id)
DailyContext
  ↓ (H4Context.parent_daily_context_id)
H4Context
  ↓ (H1Context.parent_h4_context_id)
H1Context
  ↓ (M15Context.parent_h1_context_id)
M15Context
  ↓ (M5Context.parent_m15_context_id)
M5Context
```

`TopDownContext.__post_init__` validates lineage **presence-consistency only** (if a
child declares a parent id AND the actual parent object is supplied, they must match)
— never calculation. A tier with a declared parent id but no parent object supplied
yet is valid (TD-1 defines no builder; partial lineage is the expected case until
TD-2+).

## Non-authoritative invariant

`TopDownContext.authority` is fixed to `mtf_context.models.AUTHORITY`
(`"ADVISORY_ONLY"`); `TopDownContext.authorization` is a fixed, all-`False` dict
(`may_create_trade`, `may_reject_trade`, `may_change_strategy_decision`,
`may_modify_risk`, `may_execute`) — mirroring `MTFContext`'s own existing default.
Both are validated in `__post_init__`; any attempt to override either raises
`ValueError`. There is no `direction`/`decision`/`signal`/`buy`/`sell`/
`ready_for_trade`/`position_size`/`risk_amount` field anywhere on the dataclass
(asserted by test).

## Mandatory provenance (every tier context)

`context_id`, `symbol`, `timeframe` (fixed per class, validated), `source`,
`bar_close_time`, `snapshot_fingerprint` (optional), `feature_version`,
`data_quality_status` (validated against `mtf_context`'s existing status vocabulary),
plus the tier's own `parent_*_context_id` where applicable. `context_id` is
deterministic (`compute_context_id()`, blake2b over symbol/timeframe/source/
bar_close_time/feature_version/parent_context_id — no wall-clock/random input, same
convention as `proposals/identity.py::setup_id` and
`proposals/occurrence_identity.py`). Every dataclass has a `to_dict()` for
serialization (ISO-8601 datetimes, recursive on nested dataclasses/tuples).

## Test results

`pytest tests/test_topdown_context_contracts.py tests/test_mtf_context_execution_guard.py tests/test_mtf_context.py tests/test_mtf_context_pivot_availability.py -q`
→ **42 passed** (33 new + 9 pre-existing `mtf_context` tests, all still green).

## Safety confirmation

No market data acquisition, calculation, cache, strategy logic, proposal logic, risk
logic, validation evidence, holdout data, or demo/live/execution authority was
touched. Working tree's pre-existing unrelated WIP (friction-campaign session
artifacts, `state/proposal_ledger/proposal_ledger.json`, `src/svos/`) was inspected and
left untouched.

## Next

TD-2 (data foundation: first real W1 candle acquisition + minimal WeeklyContext
builder) — **only after owner review of this contract freeze.**
