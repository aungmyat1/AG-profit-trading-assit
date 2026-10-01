# Install on the Windows MT5 Demo host

This procedure installs the read-only scheduled host for the complete AG V1 objective:

- session tickets for EURUSD, GBPUSD, USDJPY, and XAUUSD on `ASIAN_LONDON` and `LONDON_NEWYORK`;
- daily-window tickets for BTCUSDT and ETHUSDT;
- Large-SMC watch and alerts for all six instruments;
- optional Telegram reporting for fresh `READY` tickets and Large-SMC `OPPORTUNITY` alerts.

All tickets and alerts are informational. They are not broker orders. The host runtime rejects a
non-Demo MT5 account and contains no order or position-mutation calls.

## 1. Host prerequisites

Use the Windows computer on which the 64-bit VT Markets MetaTrader 5 terminal is installed.
The Windows user must remain signed in and MT5 must remain open and logged in because scheduled
tasks run interactively in that same user session.

From PowerShell in the repository root:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\pip.exe install -r requirements.txt
```

Provide MT5 Demo credentials through persistent user environment variables; never commit
credentials:

```powershell
[Environment]::SetEnvironmentVariable('VTMARKETS_DEMO_LOGIN', '<demo-login>', 'User')
[Environment]::SetEnvironmentVariable('VTMARKETS_DEMO_PASSWORD', '<demo-password>', 'User')
[Environment]::SetEnvironmentVariable('VTMARKETS_DEMO_SERVER', '<VTMarkets-Demo-server>', 'User')
```

If terminal auto-detection does not work, also set `MT5_TERMINAL_PATH` to `terminal64.exe`.
Open a new PowerShell session after changing persistent environment variables.

## 2. Verify the repository objective

```powershell
.venv\Scripts\python.exe scripts\host\verify_objective.py
```

Required result:

```text
9 PASS checks
RESULT: PASS
```

This validates both FX cycles, all six instruments, the active two-symbol crypto configuration,
all committed VT Markets symbol metadata, Large-SMC coverage, the three scheduled-task bindings,
the `ARCHIVE_ONLY` delivery default, and the `READY`/`OPPORTUNITY`-only Telegram reporting scope.
Do not install tasks if this preflight fails.

## 3. Verify MT5 Demo connectivity

```powershell
.venv\Scripts\python.exe scripts\host\diagnose_mt5.py
```

Required lines include:

```text
[OK ] python_arch
[OK ] metatrader5_package
[OK ] initialize
[OK ] account_info
[OK ] demo_account: DEMO
RESULT: ALL_OK
```

Stop if the account is not Demo. The scheduled runtime independently repeats the Demo-account
check and fails closed.

## 4. Run a live read-only smoke cycle

```powershell
.venv\Scripts\python.exe scripts\host\live_candles_smoke.py
```

Confirm that all six instruments appear. A closed market, stale data, or missing candles must be
reported explicitly rather than silently omitted. Smoke records are written below
`journal\host_smoke\`; no Telegram message or broker order is produced by this command.

## 5. Enable and validate Telegram proposal reporting

Telegram is intentionally off by default. Set the bot token and destination chat as persistent
user variables and in the current PowerShell session. Never place either value in Git, a command
argument, or a configuration file.

```powershell
$env:TELEGRAM_BOT_TOKEN = '<bot-token>'
$env:TELEGRAM_CHAT_ID = '<chat-id>'
[Environment]::SetEnvironmentVariable('TELEGRAM_BOT_TOKEN', $env:TELEGRAM_BOT_TOKEN, 'User')
[Environment]::SetEnvironmentVariable('TELEGRAM_CHAT_ID', $env:TELEGRAM_CHAT_ID, 'User')

powershell -ExecutionPolicy Bypass -File scripts\host\enable_telegram.ps1
```

The enable script sends one proposal through the same formatter and Telegram API path used by
scheduled tickets. The received message must begin with:

```text
SIMULATED TELEGRAM DELIVERY VALIDATION -- NOT A MARKET SIGNAL
```

It must also show `decision=READY`, entry, stop, both targets, spread check, data source, and
`VALID UNTIL`. Only after Telegram accepts that message does the script create the gitignored
host-local override `config\local\delivery_override.yaml`.

Validate again at any time:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\host\verify_telegram.ps1
```

Required result:

```text
TELEGRAM_STATUS: OK ... credentials=PRESENT
TELEGRAM_PROPOSAL_TEST: OK
RESULT: PASS -- simulated proposal rendered and accepted by Telegram.
```

Scheduled Telegram scope is deliberately narrow:

- send fresh, complete `READY` FX or crypto tickets;
- send Large-SMC `OPPORTUNITY` alerts;
- keep `WATCH`, `INFO`, `NO_TRADE`, `BLOCKED`, `STALE`, and `DATA_ERROR` archive-only;
- send plain text only, with no buttons or execution callback.

A `READY` ticket is archived before Telegram delivery. Telegram does not authorize or execute a
trade.

## 6. Preview and install scheduled tasks

Preview without changing Windows Task Scheduler:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\host\install_tasks.ps1
```

Install only after the preview, objective preflight, MT5 diagnostic, smoke test, and Telegram
validation are satisfactory:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\host\install_tasks.ps1 -Apply
```

The installer creates or replaces:

| Task | Schedule | Function |
|---|---:|---|
| `AG-V1-FX-Cycles` | Every 15 minutes, daily | Self-gated Asian-London and London-New York tickets |
| `AG-V1-Crypto-Daily` | Every 5 minutes, daily | Self-gated BTCUSDT and ETHUSDT ticket windows |
| `AG-V1-LSMC-Watch` | Every 5 minutes, daily | Six-instrument Large-SMC watch and alerts |

It also removes the superseded duplicate `AG-V1-LSMC-Crypto-Weekend` task. The Large-SMC task
continues watching crypto on weekends while FX returns `MARKET_CLOSED` when appropriate.

The installer automatically runs task verification. It can also be run manually:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\host\verify_tasks.ps1
```

Required result:

```text
RESULT: PASS (3/3 scheduled task bindings valid; no duplicate weekend watcher)
```

## 7. Confirm scheduled output

After the next eligible window, inspect:

```text
logs\ag_v1_fx.log
logs\ag_v1_crypto.log
logs\ag_v1_lsmc.log
journal\ticket_delivery\archive\
journal\paper_trades\
journal\large_smc_watch\
```

Expected behavior:

1. Every evaluated FX decision is archived, including `NO_TRADE`, `BLOCKED`, and `DATA_ERROR`.
2. Crypto decisions are archived during the active configured windows.
3. Only fresh and complete FX `READY` tickets create 1R paper records.
4. Large-SMC transition alerts are archived exactly once.
5. Eligible `READY` proposals and Large-SMC `OPPORTUNITY` alerts appear in the authorized
   Telegram chat when host-local delivery is enabled.
6. No order is opened, checked, changed, or closed.

## Disable or remove

Disable Telegram while retaining archives:

```powershell
Remove-Item config\local\delivery_override.yaml -ErrorAction SilentlyContinue
```

Remove scheduled tasks:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\host\uninstall_tasks.ps1 -Apply
```

Do not enable live trading flags as part of this installation.
