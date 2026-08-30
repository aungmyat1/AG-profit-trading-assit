# AG Profit Trading

AG Profit Trading is an MT5-connected trading assistant built around deterministic
strategy evaluation, explicit risk controls, and human-authorized execution. AI
capabilities inspect and explain market state; they do not independently authorize
orders or override strategy results.

## Safety and authority

```text
Strategy YAML -> Strategy Engine -> Execution Engine -> MT5
Agent skills  -> advisory and explanatory only
```

- `strategy_engine/` owns deterministic trade signals.
- `execution/risk.py` owns entry-side sizing and risk constraints.
- New orders reach MT5 only through `assistant.commands.execute_command()` and require
  an explicit, non-defaulted `user_confirmed=True` for that user instruction.
- Manual-entry position management is a separate, ticket-claimed pathway. It can
  modify or reduce an existing position but cannot open one.
- Live trading and live trade management are disabled by default in
  [`config/trading.yaml`](config/trading.yaml).

See [`AGENTS.md`](AGENTS.md) for mandatory agent rules and
[`PROJECT_STATUS.md`](PROJECT_STATUS.md) for the current implementation state.

## Current state

- Market data, structure, supply/demand, liquidity, and entry-confirmation layers are
  implemented with fail-closed reason codes.
- Explicit-command DEMO execution supports OPEN and CLOSE.
- Execution commands use persistent atomic claims, duplicate protection, safe journal
  filenames, and conservative CLOSE-volume normalization.
- Manual-entry trade management supports ticket claiming, TP1 partial close,
  breakeven, and a 5R runner under an independent safety gate.
- Historical replay prohibits live MT5 candle/tick access. Historical session-box
  reconstruction remains a documented completeness gap and degrades explicitly.
- Current regression baseline: **979 passed, 5 skipped, 0 failed** (2026-08-30).

## Quick start

Requirements: Python 3.10 or newer and, for live market-data checks, a running and
logged-in MetaTrader 5 terminal.

```powershell
python -m pip install -r requirements.txt
python -m pytest -q
```

Safe read-only examples:

```powershell
python scripts/check_mt5.py --symbol EURUSD
python scripts/analyze_structure.py --symbol EURUSD --timeframe M15
python scripts/run_strategy.py --help
python scripts/trade_assistant.py --help
```

Execution preview and manual-position management:

```powershell
# Without --confirm, execute_trade reports the broker request but does not send it.
python scripts/execute_trade.py --help

# Claim only a position that the user already opened manually.
python scripts/manage_trade.py --help
python scripts/manage_positions.py --once
```

Do not enable `mode: TRADING`, `allow_order_send`, `allow_live_trading`, or
`allow_live_management` without an intentional, separately reviewed operation.

## Repository map

```text
config/                    Session, analysis, risk, and trading safety configuration
strategies/                Strategy YAML authority and strategy ledger
src/
  strategy_engine/         Deterministic strategy evaluation
  execution/               Authorization, risk, validation, command lifecycle, OPEN/CLOSE
  mt5/                     Broker connection and MT5 adapters
  trade_management/        Pre-trade analysis and claimed manual-position management
  assistant/               User-facing analysis and execution funnel
  strategy_manager/        Registered-strategy dispatch
  historical_replay/       Point-in-time data store, replay guards, fill simulation
  market_structure/        Structure analysis
  supply_demand/           Zones and order-block contracts
  liquidity/               Liquidity levels and sweep/reclaim state
  entry_confirmation/      Frozen entry-confirmation contracts and implementations
scripts/                   Operator and research command-line tools
tests/                     Offline, live-guarded, execution-safety, and replay tests
docs/                      Architecture, specifications, setup, and evidence snapshots
```

Python packages use the flat `src/` layout. Imports remain package-based (`import mt5`,
`import execution`, and so on) through the project configuration in `pyproject.toml`.

## Documentation

Start with the [`docs` index](docs/README.md). The documentation types have different
authority:

1. Strategy YAML and frozen specification documents define intended behavior.
2. `PROJECT_STATUS.md` describes the current implementation and known gaps.
3. `docs/status/` records dated verification evidence; older test totals are historical.
4. Architecture documents explain seams and authority but do not override strategy or
   execution gates.

## Testing notes

```powershell
# Full regression
python -m pytest -q

# Execution safety
python -m pytest -q tests/test_execution_command_safety.py tests/test_execution_safety_v1.py

# Historical replay isolation and no-lookahead behavior
python -m pytest -q tests/test_historical_replay_no_lookahead.py tests/test_replay_orchestrator.py
```

Live MT5 tests are environment-aware and may skip when the FX session is closed. They
never fabricate fresh candles or weaken production stale-data checks.
