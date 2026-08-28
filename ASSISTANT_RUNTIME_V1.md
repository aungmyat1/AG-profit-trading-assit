# ASSISTANT_RUNTIME_V1

Runtime that lets the Trade Assistant coordinate `SESSION_TRADE_V1` (`ASIAN_LONDON`
cycle only) end-to-end, without reimplementing anything that strategy already owns.

## Purpose

Prove `MT5 -> MarketContext -> Strategy Manager -> Strategy Registry -> SESSION_TRADE_V1
-> StrategyResult -> AssistantDecision -> Report + Journal` works, in three explicit
modes, with `LONDON_NEWYORK` and `LIVE` both hard-blocked regardless of any flag.

## Why a thin wrapper, not a rebuilt pipeline

`SESSION_TRADE_V1`'s entire execution stack — its own `TradeIntent`-equivalent
(`build_intent()`), risk sizing (`RiskSupervisor`), `MT5ExecutionGateway`, duplicate/quota
protection (`ExecutionLedger`), governance/signoff, and journal — already exists, fully
built and independently tested, in the separate `Session Trade Codex` repository
(`D:\ddev\Session Trade Codex`, `session_strategy/` package + `scripts/
execute_session_signal.py`). That repo's own `strategies/session_trade/contract.yaml`
(this repo) states explicitly: *"This repo does not duplicate the strategy's
classifier/setup/risk logic... Do not port SESSION_TRADE_V1's logic into
`strategy_engine/` — that would create a second, divergent implementation."*

So `ASSISTANT_RUNTIME_V1` is a **thin, honest adapter**: it invokes the existing,
already-governed `execute_session_signal.py` as a subprocess with mode-appropriate
flags, reads back its structured output, and normalizes it into this repo's own
`StrategyResult`/`AssistantDecision` for unified reporting/journaling. All strategy
decision, risk, duplicate-protection, governance, and broker-write authority stay
exactly where they already live. This mirrors an established pattern already in place
the other direction: `execute_session_signal.py` itself cross-repo-imports **this**
repo's `market_structure` package for an optional structure-confirmation signal.

## Architecture

```
scripts/trade_assistant.py  (CLI)
        |
assistant/runtime.py         TradeAssistant.evaluate(strategy_id, symbol, cycle, mode)
        |
strategy_manager/manager.py  registry + cycle authority (independent gate) + dispatch
        |             \
        |              strategy_manager/context_builder.py  -> MarketContext
        |
strategy_manager/session_trade_adapter.py
        |             (the ONLY module that knows about Session Trade Codex)
        v
D:\ddev\Session Trade Codex\scripts\execute_session_signal.py  (subprocess)
        |
        v
assistant/models.py: StrategyResult -> AssistantDecision
        |          \
assistant/journal.py    assistant/report.py
```

### MarketContext (`strategy_manager/context_builder.py`)

Strategy-neutral: symbol, account identity/DEMO flag, current bid/ask, tick freshness.
Reuses `mt5.account.account()` and `mt5.market_data.get_tick()`/`check_freshness()`
directly — no new MT5 read logic. Does **not** fetch M15 candles, session boxes, or run
any capability-layer analysis itself (Order Blocks/FVG/full structure) — those stay
each strategy's own concern via its adapter, per the mission's own instruction not to
force unrelated capabilities. Fails closed (`CONTEXT_FAILED` + reason) on missing
account/tick/stale data, never guesses.

### Strategy Manager (`strategy_manager/manager.py`)

`evaluate(strategy_id, symbol, cycle, mode)`:
1. Build `MarketContext`; short-circuit `CONTEXT_FAILED` before ever touching the
   registry (registry is real disk I/O, not free — no reason to pay for it on a context
   failure the caller can't act on anyway).
2. Read `strategies/registry.yaml` — must be `registered` and `active`.
3. Only `SESSION_TRADE_V1` has an adapter in V1; any other `strategy_id` is
   `STRATEGY_ADAPTER_NOT_IMPLEMENTED`, never silently evaluated by a fallback path.
4. Read `strategies/session_trade/contract.yaml`'s `supported_cycles[cycle]` — must be
   `status: ACTIVE` and `execution_authority: SIGNED`. **This check runs for every
   mode, including `ANALYZE_ONLY`** — an unsigned cycle (`LONDON_NEWYORK`) is blocked
   before the adapter (and therefore the subprocess) is ever invoked, independent of
   the subprocess's own identical pair-signed check (defense in depth).
5. `mode == LIVE` is blocked here too, before dispatch.
6. Dispatch to `session_trade_adapter.run_session_trade_v1()`, normalize its result into
   `StrategyResult` via `to_strategy_result()`.

### Session Trade adapter (`strategy_manager/session_trade_adapter.py`)

Maps AG runtime mode -> the existing script's own CLI flags (verified against
`execute_session_signal.py` as of Session Trade Codex commit `d026f09a`, 2026-08-27):

| AG mode | flags | env vars | broker writes |
|---|---|---|---|
| `ANALYZE_ONLY` | (none) | — | none |
| `SHADOW_DEMO` | `--check` | — | real `order_check`, never `order_send` |
| `DEMO_EXECUTION` | `--check --confirm` | `ALLOW_ORDER_SUBMISSION=true`, `ALLOW_ONE_DEMO_ORDER=true` | real `order_send`, only if every existing gate in that repo passes |

Reads back `<temp_output_dir>/*/*/analysis.json` (that script's own
`AnalysisResult.to_dict()` artifact — unchanged, not reinterpreted) plus the last
balanced JSON object printed to stdout (`extract_last_json_object()` — a pure
brace-matching scan, tested against the exact stdout shapes the script produces:
`DRY_RUN`/`DUPLICATE_BLOCKED`/`REFUSED`/`ATTEMPTED`/`NOT_ATTEMPTED`/`NO_TRADE`/`error`).
Never re-derives `analyze()`'s own inputs (news calendar, account snapshot, drawdown,
journal-healthy, structure confirmation, etc.) — reading those back out of
`analysis.json` instead of recomputing them is exactly what keeps this from becoming
"a second, divergent implementation."

### AssistantDecision status mapping (`assistant/runtime.py::_map_status`/`_map_trade_ready`)

| `StrategyResult.status` | adapter `execution_outcome` | `AssistantDecision.status` |
|---|---|---|
| `INVALID_CONTEXT` (no adapter run) | — | `CONTEXT_FAILED` |
| `INVALID_CONTEXT` (adapter ran, environment error) | — | `EXECUTION_BLOCKED` |
| `BLOCKED`, reason `UNSIGNED_CYCLE` | — | `UNSIGNED_CYCLE` |
| `BLOCKED`, reason not-registered/not-active/no-adapter/cycle-not-supported | — | `UNSIGNED_STRATEGY` |
| `BLOCKED`, other | — | `EXECUTION_BLOCKED` |
| `NO_SETUP` | — | `NO_SETUP` |
| `TRADE_READY` | `DUPLICATE_BLOCKED` | `DUPLICATE_SIGNAL` |
| `TRADE_READY` | `REFUSED` (pair-unsigned wording) | `UNSIGNED_CYCLE` |
| `TRADE_READY` | `REFUSED` (other) | `EXECUTION_BLOCKED` |
| `TRADE_READY` | `DRY_RUN`, mode `ANALYZE_ONLY` | `TRADE_READY` |
| `TRADE_READY` | `DRY_RUN`, mode `SHADOW_DEMO`, `broker_check.retcode==0` | `SHADOW_CHECKED` |
| `TRADE_READY` | `DRY_RUN`, mode `SHADOW_DEMO`, `broker_check.retcode!=0` | `ORDER_CHECK_REJECTED` |
| `TRADE_READY` | `ATTEMPTED`, outcome in `{CONFIRMED, CONFIRMED_VIA_DEAL_HISTORY, PENDING_ORDER_CONFIRMED}` | `EXECUTED` |
| `TRADE_READY` | `ATTEMPTED`, other outcome | `EXECUTION_FAILED` |

No new terminology invented where the source repo's own vocabulary already says the
same thing.

## Execution flow

```
request(strategy_id, symbol, cycle, mode)
  -> MarketContext (fail closed)
  -> registry + contract cycle-authority check (independent gate, every mode)
  -> [ANALYZE_ONLY | SHADOW_DEMO | DEMO_EXECUTION] -> subprocess -> analysis.json + stdout JSON
  -> StrategyResult (verbatim copy of setup/direction/entry/SL/TP -- never recomputed)
  -> AssistantDecision (status mapping above)
  -> assistant/journal.py (append-only, every run)
  -> assistant/report.py (human-readable) or CLI --json
```

## Safety gates

- `LONDON_NEWYORK` blocked in `strategy_manager/manager.py`, independent of mode,
  independent of the subprocess's own identical check — two layers, not one.
- `LIVE` blocked in `strategy_manager/manager.py` before any subprocess call.
- `DEMO_EXECUTION` requires the subprocess's own **three** independent switches
  (`--confirm`, `ALLOW_ORDER_SUBMISSION`, `ALLOW_ONE_DEMO_ORDER`) — this repo does not
  add a fourth, weaker path; it only ever sets those exact three when instructed.
- No automatic mode promotion: passing `order_check` in `SHADOW_DEMO` never
  auto-triggers a `DEMO_EXECUTION` run; each `evaluate()` call takes an explicit `mode`.

## Journal

`assistant/journal.py` — append-only JSON-lines, `journal/assistant_runs.jsonl`, one
entry per `evaluate()` call (every status, not only executed trades). This is a
companion audit trail of "what the assistant decided" — it is **not** a replacement for
Session Trade Codex's own execution ledger, which stays authoritative for the actual
broker-facing history.

## CLI usage

```bash
python scripts/trade_assistant.py --strategy SESSION_TRADE_V1 --symbol EURUSD \
    --cycle ASIAN_LONDON --mode ANALYZE_ONLY [--json]
```

`--mode` accepts `ANALYZE_ONLY`, `SHADOW_DEMO`, `DEMO_EXECUTION`, `LIVE` (the last
always blocked).

## Promotion gates

- **Gate 1 `ASSISTANT_ANALYZE_ONLY_READY`**: Strategy Manager, MarketContext,
  AssistantDecision all work, zero broker-write calls, tests pass — **YES**, live-verified.
- **Gate 2 `ASSISTANT_SHADOW_DEMO_READY`**: Gate 1 + verified DEMO MT5 connection + real
  account verification + real `order_check` + `order_send` impossible — mode wiring
  live-verified; a REAL `order_check` call could not be exercised today because no
  signal was accepted (`INVALID_ASIAN_RANGE`) on the live run — **PARTIAL**, pending a
  day with an accepted signal.
- **Gate 3 `ASSISTANT_DEMO_EXECUTION_READY`**: Gate 2 + governance permits + controlled
  DEMO `order_send` path tested — implemented and unit-tested (mocked adapter); **no
  real `--confirm` run was attempted this pass**, matching this session's established
  pattern of deferring live order-changing validation until explicitly requested.

## Known blockers (not fixed this pass, by design)

- Session Trade Codex: `test_engine.py::test_governance_approves_stage_2_baseline...`
  (config-hash drift from a legitimate `config/strategy.yaml` fix) — needs trader
  re-signoff, not a code fix. `GOVERNANCE_RESIGN_REQUIRED`.
- Session Trade Codex: `test_golden_fixtures.py::test_versioned_golden_cases`
  (classifier returns `UNCERTAIN` where a golden case expects `RANGE`) — pre-existing,
  needs its own investigation, out of scope for runtime integration.
- `LONDON_NEWYORK` remains `UNSIGNED` — not touched, per mission scope.
