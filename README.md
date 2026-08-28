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

```
AGENTS.md                Agent working rules (short, always-load)
PROJECT_STATUS.md         Implemented vs. scaffolding, implementation sequence

config/
  canonical_sessions.yaml Session-window authority (Asian/London/NY, UTC, M15)
  trading.yaml             Operating mode (ANALYSIS/DRY_RUN/TRADING) + live-trading gate
  mt5.yaml                 MT5 connection config (no secrets committed here)

strategies/
  ST_ASIAN_SWEEP_5R_V1.yaml  Strategy authority for this strategy
  STRATEGY_LEDGER.md          Index of registered strategies

strategy_engine/           Deterministic: candles -> TradeSignal. No MT5 import.
  loader.py, models.py, engine.py
  session/                  Session-box family (box/classify/route); formerly session_router/

execution/                 TradeSignal -> TradeIntent -> risk -> validation -> MT5 -> journal
mt5/                       Broker adapter: connection, market data, account, symbols
assistant/                 Agent-facing reporting/explanation layer (advisory only)

.claude/skills/, .agents/skills/   Agent skills (identical mirrors)
scripts/                   CLI entry points (run_strategy, dry_run, check_mt5, trade_assistant)
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
