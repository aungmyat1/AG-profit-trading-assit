# AG_TASK_C_PER_SYMBOL_POSITION_GUARD_V1

Dated implementation and replay-gate record. Technical behavior is implemented and
focused-tested; the economic comparison is blocked because the exact historical baseline
population could not be identified. This record does not authorize strategy promotion,
Demo, Live, or broker execution.

## Repository and authority baseline

```text
branch at start = arena/01a0cfad-ag-profit-trading-assit
BASE_SHA        = 36bc3b668a7302a67ada5c48bc36ff7c0ff7cf7b
working tree    = clean before edits
strategy        = ST_LIQUIDITY_SWEEP_RETEST_V1 v2.0.0 (current YAML)
registry        = registered=true, active=false, research=true,
                  demo_authorized=false, live_authorized=false
```

No separate uploaded optimization-brief file was present in the checkout. The approximate
99-setups / 50-taken / 49-blocked / 48-position-guard-blocked numbers are retained only
as an unverified claim from the task prompt, not as reproduced evidence.

## Implementation

`src/execution/position_guard.py` now adds `MAX_OPEN_POSITIONS_PER_SYMBOL = 1` and an
optional `symbol` parameter to `open_count()` and `is_blocked()`:

- No-symbol calls keep the existing global behavior: `open_count()` counts every stored
  record and `is_blocked()` compares that total with
  `MAX_OPEN_STRATEGY_POSITIONS = 1`.
- Symbol-scoped calls count only records whose `symbol` exactly matches and compare that
  count with the per-symbol cap of one.
- A legacy record without a `symbol` remains part of the global total but never matches a
  symbol-specific query.

Only `src/strategy_engine/sweep_retest/engine.py::evaluate_setup` opts into the new scope,
calling `open_position_guard.is_blocked(symbol=symbol)`. This is the shared engine for the
FOREX and CRYPTO_PERP profiles, so the same per-symbol behavior applies to either profile.
No other `OpenPositionGuard` caller was changed.

### Pre-change caller matrix

| Caller | Pre-change invocation | Expected post-change semantics | Modified? |
|---|---|---|---|
| `strategy_engine.sweep_retest.engine.evaluate_setup` | `is_blocked()` | Per-symbol, using the current setup symbol | Yes, only call site |
| `execution.coordinator.ExecutionCoordinator.submit` | `is_blocked()` | Global execution guard | No |
| `execution.readiness` | `is_blocked()` | Global readiness guard | No |
| `authorization.mt5_execution_handler` | `is_blocked()` | Global execution guard | No |
| `scripts/run_ag_execution_runtime.py` | `open_count()` and `is_blocked()` | Global status totals | No |
| `post_asian_pilot.preflight` | `open_count()` | Global preflight total | No |
| `execution.lifecycle` | `register_open()` / `register_closed()` | Keep persisting/removing positions and their symbol metadata | No |
| `btc_sweep_research.pipeline` / `scripts/run_btc_daily_report.py` | Supply the guard to the shared Sweep Retest engine | Per-symbol through the single engine call site | No separate change |
| `post_asian_pilot.governor` | Strategy-filtered store reads; does not call `is_blocked()` | Existing pilot policy unchanged | No |

The global `ExecutionCoordinator` and readiness checks intentionally remain no-symbol,
therefore global. This task changes Sweep Retest engine tradability reporting only; it does
not change the generic execution gate or claim that a second-symbol signal could bypass it.

## Configuration and version truth

`max_open_strategy_positions` is **`CONFIRMED_UNUSED` as a behavioral setting**. The
Sweep Retest config loader reads it into `SweepRetestStrategyConfig`, but repository search
found no downstream use of that value. Search evidence:

```text
rg -n 'max_open_strategy_positions' src tests strategies --glob '*.py' --glob '*.yaml'
results: strategies/ST_LIQUIDITY_SWEEP_RETEST_V1.yaml (declaration),
         src/strategy_engine/sweep_retest/config.py (dataclass field and parser assignment)
behavioral consumers: none
```

Task C did not wire or edit the field or strategy YAML. The YAML's existing combined-scope
declaration is therefore left untouched and must be reconciled by the owner before any
strategy-version promotion.

`docs/VERSION_HISTORY.md` broadly says strategy versions change when risk semantics
change; its explicit trigger list names intrinsic trade-eligibility logic but does not
specifically name open-position concurrency. Task C changes the maximum simultaneous
exposure allowed by this strategy engine, so this is classified as version-relevant under
the broad risk-semantics rule: a new candidate strategy version is required before this
behavior is treated as authoritative. No direct repository precedent for this precise
global-to-per-symbol guard-scope change was found. The owner retains strategy-lifecycle
authority; the exact candidate version identifier is not assigned, and no promotion
occurred. `v2.0.0` metadata and historical evidence were not rewritten or reattributed.

```text
STRATEGY_VERSION_BUMP_STATUS = REQUIRED_BY_RISK_SEMANTICS_POLICY
CANDIDATE_VERSION_ID         = OWNER_DECISION_PENDING
```

The guard asymmetry is now explicit:

```text
DailyLossGuard                         = strategy/day scoped
OpenPositionGuard default              = global
ST_LIQUIDITY_SWEEP_RETEST_V1 opt-in    = per-symbol
```

## Validation evidence

```text
test environment = Python 3.11 on Linux, temporary venv using repository requirements
account class   = NONE (no broker/demo account connected)
venues accessed = NONE (no broker/exchange API or terminal operation)
fixtures        = EURUSD, GBPUSD, BTCUSDT, ETHUSDT test profiles; original replay symbols unknown
```

### Focused and affected suites

Command (repository-declared dependencies installed in a temporary Python 3.11 Linux
virtual environment; no repository dependency files changed):

```text
/tmp/ag-profit-trading-venv/bin/python -m pytest -q \
  tests/test_liquidity_sweep_retest_strategy.py \
  tests/test_btc_sweep_research_pipeline.py \
  tests/test_btc_daily_cli.py \
  tests/test_execution_coordinator.py \
  tests/test_execution_runtime_readiness.py \
  tests/test_execution_lifecycle.py \
  tests/test_mt5_execution_handler.py \
  tests/test_ag_existing_demo_gateway_gap_audit.py \
  tests/test_post_asian_pilot.py \
  tests/test_ag_daytrading_runtime.py \
  -k 'not test_end_report_data_error_day_is_pass_with_observations'
```

Result: **217 passed, 1 deselected** in 2.76 seconds. The deselected test was separately
run in the unfiltered command and failed when it called `MetaTrader5.initialize()`; the
portable stub correctly refuses MT5 operations because this Linux environment has no real
MetaTrader5 package or terminal. It is classified `ENVIRONMENTAL`, not as a guard
regression. The Sweep Retest engine tests cover all six requested cases, including the
symbol-spy integration assertion; the BTC pipeline guard fixture now records a same-symbol
position for its block case.

### Full default repository suite

Command: `/tmp/ag-profit-trading-venv/bin/python -m pytest -q`.

```text
passed=3874  failed=52  skipped=48  errors=3  deselected=1
warnings=11  duration=35.60 seconds
```

The default excludes the repository's sole `slow` test, an exhaustive Large-SMC golden
historical replay. It was not started. No Task C regression was identified: the changed
Sweep Retest and execution/readiness suites pass. All 52 full-suite failures and 3 errors
were individually classified in
`artifacts/backtests/AG_LIQUIDITY_SWEEP_RETEST_PER_SYMBOL_GUARD_REPLAY_V1.json`:

```text
REGRESSION_FROM_CHANGE = 0
ENVIRONMENTAL          = 36 failed tests + 3 collection/setup errors
PRE_EXISTING           = 4
STALE_TEST_EXPECTATION = 9
UNRELATED              = 3
```

Environmental causes include the absent Windows-only MT5 package/terminal, unavailable
`D:\` paths and git objects referenced by historical tests. The pre-existing SSC failures
are dataset-manifest hash mismatches. Stale expectations compare checked-in FX/BTC ledger
populations against old counts. Unrelated failures are in market-data filename parsing and
proposal-envelope adapter expectations. Nothing in those areas was edited. The full suite
is therefore **non-green** in this checkout despite zero failures traced to Task C.

No broker operation was executed. MT5-related tests encountered the refusal stub before a
real terminal or broker was available. No Demo/Live route was enabled or exercised.

## Baseline and replay gate

```text
BASELINE_REPRODUCTION = NOT_REPRODUCIBLE
CANDIDATE_REPLAY       = NOT_EVALUATED
```

Search found no exact population artifact, matching replay script, or strategy-specific
historical EURUSD/GBPUSD dataset. The two existing
`ST_LIQUIDITY_SWEEP_RETEST_V1@2.0.0` artifacts are determinism evidence, not the requested
historical economic baseline. The repository's current validation snapshot also lists
`HISTORICAL_REPLAY` as an open gate. Dataset identity, date range, original symbols,
original config fingerprint, baseline metrics, and costs therefore remain unknown. In
accordance with P7, replay stopped before any comparison; all candidate R, win/loss, and
concurrency metrics are null in the machine-readable artifact. No economic improvement is
claimed, and no gross/net R or friction assumption is fabricated.

## Safety boundary

The patch did not:

- add automatic execution or alter human confirmation;
- change Demo or Live authorization;
- modify broker submission or MT5 routing;
- alter risk percentages or strategy entry/exit logic;
- change another `OpenPositionGuard` caller to symbol-scoped behavior;
- redesign `DailyLossGuard`.

`strategies/registry.yaml`, execution submission code, MT5 routing, and trading gates are
unchanged. Strategy research/validation and platform execution authority remain separate.

## Next recommended gate

Obtain the original replay brief, exact population-generation script, pinned dataset and
config fingerprint. Then reproduce the baseline exactly before running the same population
with only the per-symbol guard difference. Separately obtain the owner's strategy-version
and YAML-scope decision before treating the candidate behavior as authoritative. Do not
start SSC WP4B or Large-SMC measurement work as part of Task C.
