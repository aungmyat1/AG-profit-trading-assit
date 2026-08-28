# AG Profit Trading

Trading Assistant + Strategy Execution Platform for MT5. See `AGENTS.md` for agent
working rules and `PROJECT_STATUS.md` for what's implemented vs. scaffolding.

## Authority order

```
Strategy YAML -> Strategy Engine -> Execution Engine -> MT5
Agent skills  -> ADVISORY ONLY, no independent execution authority
```

Trading skills advise, inspect, validate, and explain. `strategy_engine/` decides.
`execution/` sends orders — but only via `execution/executor.py`, reached only through
`assistant/commands.py`, and only with an explicit, non-defaulted user command each
call (see PROJECT_STATUS.md "Execution authority restructure"). `mt5/` is the broker
interface. See `AGENTS.md`.

## Layout

Source moved under `src/` (2026-08-28 reorganization) — a flat layout, one directory
per package, package names unchanged from before the move (`import mt5`, `import
execution`, etc. still work identically; see `pyproject.toml`'s `pythonpath`/packaging
config). Deep spec/status docs moved into `docs/`; `README.md`, `AGENTS.md`, and
`PROJECT_STATUS.md` stay at root as the three things a new reader hits first.

```
AGENTS.md                Agent working rules (short, always-load)
PROJECT_STATUS.md         Implemented vs. scaffolding, implementation sequence
pyproject.toml            src/ packaging config + pytest pythonpath

docs/
  architecture/            TRADE_ASSISTANT_ARCHITECTURE.md, ARCHITECTURE_CONFLICT_AUDIT.md
  specs/                   *_SPEC.md contracts (entry-confirmation, trade-management, ...)
  status/                  Phase/runtime status snapshots
  setup/                   MT5_MCP_SETUP.md

config/
  canonical_sessions.yaml Session-window authority (Asian/London/NY, UTC, M15)
  trading.yaml             Operating mode (ANALYSIS/DRY_RUN/TRADING) + live-trading gate
  mt5.yaml                 MT5 connection config (no secrets committed here)

strategies/
  ST_ASIAN_SWEEP_5R_V1.yaml  Strategy authority for this strategy
  STRATEGY_LEDGER.md          Index of registered strategies

src/
  strategy_engine/         Deterministic: candles -> TradeSignal. No MT5 import.
    loader.py, models.py, engine.py
    session/                Session-box family (box/classify/route); formerly session_router/

  execution/                TradeSignal/TradeCommand -> risk -> validation -> MT5 -> journal
  mt5/                       Broker adapter: connection, market data, account, symbols
  trade_management/          Pre-trade geometry/sizing + manual-entry position management
  market_structure/, supply_demand/, liquidity/, entry_confirmation/, chart_renderer/
                              Capability/analysis layer (advisory only)
  assistant/                  Agent-facing orchestration/execution-funnel layer
  strategy_manager/           Registered-strategy dispatch
  session_clock.py

.claude/skills/, .agents/skills/   Agent skills (identical mirrors)
scripts/                   CLI entry points (run_strategy, dry_run, check_mt5,
                            execute_trade, trade_assistant, ...) + setup .ps1 scripts
tests/
```

## Quick start

```
python -m pytest tests/ -q
```

`strategy_engine/loader.py` and `engine.py` are implemented and tested — they turn a
`strategies/*.yaml` file into a `TradeSignal` given candle data. `execution/mt5_gateway.py`
and `executor.py` now implement OPEN-side order placement (explicit-user-command-gated,
DEMO only); see `PROJECT_STATUS.md`'s "Execution authority restructure" for the current
state and `scripts/execute_trade.py` for the CLI entry point.
