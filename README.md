# AG Profit Trading

AG Profit Trading is a deterministic FX and crypto trading assistant designed to
produce four complementary decision products:

- **Session Trade** proposals for recurring intraday opportunities around defined
  market sessions.
- **Large-SMC Trade** proposals for selective higher-timeframe liquidity and structure
  opportunities with lower-timeframe confirmation.
- **Large-SMC Watch** funnel-status updates and entry-confirmation alerts for a preset
  watchlist.
- **Interactive Top-Down Analysis** assistance that coordinates structure, zones,
  liquidity, registered-strategy matching, and cross-timeframe entry confirmation when
  the owner is analyzing a chart.

The owner-directed product target is two daily FX session decision cycles for EURUSD,
GBPUSD, USDJPY, and XAUUSD; scheduled crypto decisions for BTCUSDT and ETHUSDT; and a
persistent Large-SMC watch. The immediate delivery stage uses current frozen strategy
behavior to publish informational trade tickets. Strategy validation and candidate
promotion follow as a separate next stage. See
[`docs/PROJECT_ROADMAP.md`](docs/PROJECT_ROADMAP.md).

For chart-led analysis, agent skills organize advisory evidence from higher timeframe
to lower timeframe. A related strategy is considered only when its registered contract
matches the symbol, session, setup, and timeframe chain. The deterministic strategy
decision remains authoritative; advisory confirmation never becomes a trade signal by
itself.

The guaranteed daily output is a decision (`READY`, `WATCH`, `NO_TRADE`, or a fail-closed
data/error state), not a forced trade. A pre-trade proposal ticket is not a broker
execution ticket. MT5
or a future crypto venue creates a broker ticket only after a qualifying proposal is
refreshed, validated, explicitly authorized by the user, and successfully executed.

The current operational implementation is FX/MT5-first. The crypto research path has a
live-validated, public/read-only Bybit BTCUSDT linear-perpetual feed and a scheduler-ready
daily decision CLI; crypto execution remains unimplemented and disabled.
AI capabilities inspect and explain market state; they do not independently authorize
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
- The web workspace defaults to an explicitly labelled **SIMULATION MODE**. Its generated
  candles, proposals, positions, and mock execution/management responses never represent
  broker activity. In `VITE_AG_API_MODE=real`, the legacy manual controls fail closed;
  backend status and authorized-ticket surfaces use the real API. The AG Backend panel
  can authorize an existing `PENDING` Demo ticket after a fresh per-ticket confirmation;
  it cannot create order parameters or bypass strategy/proposal authority. The same
  panel displays sanitized account status and closing-deal history read directly from
  the connected MT5 terminal; fixture performance remains visually separate.

See [`AGENTS.md`](AGENTS.md) for mandatory agent rules and
[`PROJECT_STATUS.md`](PROJECT_STATUS.md) for the current implementation state — in
particular its "Capability & Roadmap Reconciliation (dated 2026-09-06)" section, which
distinguishes IMPLEMENTED from VERIFIED from ENABLED from AUTHORIZED, and separates
the proposal-only FX runtime from the independently-gated MT5 Demo execution
subsystem: a generic proposal→execution bridge exists and was live-verified
(2026-08-28), but `ST_ASIAN_SWEEP_5R_V1` itself is not `demo_authorized`, so its
proposals cannot use it today.

## Run locally from VS Code

After the one-time `AG: Setup Dev (first time)` task, press `Ctrl+Shift+B` or run
`Tasks: Run Task` → `AG: Start Dev`. The supervised task starts the local FastAPI
backend at `http://127.0.0.1:8000` and the Vite frontend at
`http://localhost:3000` in one dedicated terminal. Stop that task to stop both.
See [`docs/setup/AI_STUDIO_VSCODE_DEVELOPMENT.md`](docs/setup/AI_STUDIO_VSCODE_DEVELOPMENT.md)
for environment and troubleshooting details.

## Current state

Roadmap scope is broader than current implementation. Today the operational FX pilot
and complete Entry Ticket cover EURUSD/GBPUSD; USDJPY/XAUUSD require candidate-version
integration. Crypto reporting is BTCUSDT-only; ETHUSDT remains to be implemented.
Large-SMC has a research engine and live-batch ledger but not yet the complete
incremental funnel-status and external confirmation-alert service.

- Market data, structure, supply/demand, liquidity, and entry-confirmation layers are
  implemented with fail-closed reason codes.
- Explicit-command DEMO execution supports OPEN and CLOSE.
- Execution commands use persistent atomic claims, duplicate protection, safe journal
  filenames, and conservative CLOSE-volume normalization.
- Manual-entry trade management supports ticket claiming, TP1 partial close,
  breakeven, and a 5R runner under an independent safety gate.
- A read-only day-trading runtime evaluates completed-session events and SMC conditional
  surveillance, persists restart-safe state, and emits alerts. Its execution submission
  remains disabled.
- The execution runtime has restart-safe lifecycle reconciliation and explicit-confirmation
  routing for eligible FX proposals.
- Large SMC is registered as the separate `ST_LARGE_SMC_V1` research strategy. Its
  contract is advisory-only and intentionally incomplete; it has no engine or execution
  authorization and does not share authority with the Session Day Trading strategy.
- `ST_ASIAN_SWEEP_5R_V1`'s `LONDON_NEWYORK` session-pair cycle is now activated as an
  independent, proposal-only pilot (`config/pilot/AG_POST_LONDON_NEWYORK_PILOT_V1_0_1.yaml`,
  `scripts/run_post_asian_pilot.py --pilot-config ...`), isolated from the existing
  `ASIAN_LONDON` pilot's own ledger/snapshot state.
- A READY FX proposal (`ASIAN_LONDON` or `LONDON_NEWYORK`, EURUSD/GBPUSD) now shows a
  complete Entry Ticket in `scripts/run_post_asian_pilot.py --once`/`--status`/`--watch`
  operational output (JSON `entry_ticket` field, human-readable `ENTRY TICKET` section)
  -- the existing renderer (`report.render_entry_ticket`, unchanged), not a new
  capability; informational only, never implying a broker order was sent. Non-READY
  states and the canonical daily archive (`AG_FX_DAILY_REPORT_V1`) are unaffected.
- `scripts/run_post_asian_pilot.py --once` also now runs an additive, config-controlled
  exactly-once ticket-delivery step (`config/ticket_delivery.yaml`, `mode: ARCHIVE_ONLY`
  -- owner-authorized 2026-09-08; reverting to `mode: DISABLED` is a one-line rollback).
  `ARCHIVE_ONLY` durably archives every cycle decision with zero network calls, gated by
  an owner-signed catch-up policy (60-minute bound) for READY ticket registration;
  `MESSAGE_DELIVERY` is not authorized (currently behaves identically to
  `ARCHIVE_ONLY`). See
  `docs/plans/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_DELIVERY_V1.md`.
- The BTC sweep/retest research path uses Bybit production public market data for the
  BTCUSDT linear perpetual. `scripts/run_btc_daily_report.py` produces the previous UTC
  day's deterministic `READY`/`WATCH`/`NO_TRADE`/`DATA_ERROR` decision during the frozen
  06:30-06:45 UTC report window (13:00-13:15 MMT; see
  `docs/contracts/AG_BTC_DAILY_OBSERVATION_CONTRACT_V1.md`), validates complete closed
  H1/M5 evidence, and archives it immutably. A `READY` result includes an informational
  entry-proposal ticket—not a broker ticket. `scripts/install_btc_daily_task.ps1`
  installs the daily local task at 13:05 MMT (06:35 UTC), inside that window.
  No crypto research path can reach exchange or MT5 order submission; crypto execution
  remains unimplemented.
- Historical replay prohibits live MT5 candle/tick access. Historical session-box
  reconstruction remains a documented completeness gap and degrades explicitly.
- See [`PROJECT_STATUS.md`](PROJECT_STATUS.md) for the current regression baseline and
  live operational snapshot; dated totals elsewhere are milestone evidence.

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
python scripts/run_btc_daily_report.py --help
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
  large_smc_research/      ST_LARGE_SMC_V1 research-only decision engine (no execution authority)
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

When implementation, authorization, live validation, or regression state changes,
follow [`docs/status/LIVE_STATUS_MAINTENANCE.md`](docs/status/LIVE_STATUS_MAINTENANCE.md).
It defines which rolling documents must change together and which dated evidence must
remain immutable.

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
