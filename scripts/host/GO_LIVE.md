# AG V1 host go-live kit (Windows MT5 host)

This kit runs on the Windows machine where the **VT Markets DEMO** MT5 terminal is installed,
open and logged in. It is read-only: nothing here places, checks or modifies orders or
positions. Tickets and alerts are informational and are archived to `journal\`. Telegram is
optional and off by default.

## Prerequisites (one time)

1. Install 64-bit Python 3.11, then from the repo root run:
   ```
   py -3.11 -m venv .venv
   .venv\Scripts\pip install -r requirements.txt
   ```
2. Credentials go in `src\.env` or user environment variables, never in git:
   `VTMARKETS-DEMO-LOGIN`, `VTMARKETS-DEMO-PASSWORD`, `VTMARKETS-DEMO-SERVER`.
   The underscore forms `VTMARKETS_DEMO_*` also work.
3. Optionally set `MT5_TERMINAL_PATH` to the VT Markets `terminal64.exe`.

Run every step from the repo root, in this order. Stop at the first step that does not show
its expected output.

## 1. Diagnose

```
.venv\Scripts\python.exe scripts\host\diagnose_mt5.py
```

Expected output:
- `[OK ] python_arch: 3.11.x 64-bit`
- `[OK ] metatrader5_package`
- `[OK ] initialize: last_error=(1, 'Success')`
- `[OK ] account_info: login=… server=VTMarkets-… trade_mode=0`
- `[OK ] demo_account: DEMO`
- `[OK ] claude_desktop_mt5ReadOnly`
- `RESULT: ALL_OK`

No balance or equity figure is printed. Any `[FAIL]` line is followed by a `FIX:` line with
the exact remedy:
- terminal not running
- wrong path (`--terminal-path`)
- not logged in
- not a demo account
- 32-bit Python
- package missing
- Claude Desktop entry missing or relative (config `%APPDATA%\Claude\claude_desktop_config.json`, logs `%APPDATA%\Claude\logs`)

## 2. Capture USDJPY / XAUUSD symbol metadata

```
.venv\Scripts\python.exe scripts\host\capture_symbol_metadata.py --symbol USDJPY
```

Expected: `Candidates for USDJPY: [...]` and exit code 2. The script never guesses a name.
Re-run with the exact broker name from that list, then repeat for XAUUSD:

```
.venv\Scripts\python.exe scripts\host\capture_symbol_metadata.py --symbol USDJPY --broker-symbol <EXACT NAME>
.venv\Scripts\python.exe scripts\host\capture_symbol_metadata.py --symbol XAUUSD
.venv\Scripts\python.exe scripts\host\capture_symbol_metadata.py --symbol XAUUSD --broker-symbol <EXACT NAME>
```

Expected: `WROTE config\symbol_metadata\host_captured\USDJPY.json broker_symbol=… digits=… point=… server_utc_offset_hours=… sha256=…`
and then `STATUS: HOST_CAPTURED (FIXTURE_ONLY -> CODE_READY)`.

Commit the two JSON files. They are evidence and contain no secrets.

## 3. Live candle smoke test

```
.venv\Scripts\python.exe scripts\host\live_candles_smoke.py
```

Expected output: states only.
- One `BARS <SYMBOL> (<broker name>) status=FRESH|STALE|MARKET_CLOSED last_closed={D1,H1,M15,M5}` line per symbol.
- `FX <SYMBOL> <ASIAN_LONDON|LONDON_NEWYORK> data=… decision=READY|NO_TRADE|DATA_ERROR metadata=REPO_EVIDENCED|HOST_CAPTURED`.
- `LSMC <SYMBOL> data=… state=IDLE|DEVELOPING|NEAR_POI|OPPORTUNITY|… alerts=[…]`.

EURUSD and GBPUSD always run. USDJPY and XAUUSD run only after step 2. Results are archived
under `journal\host_smoke\` (ARCHIVE_ONLY; nothing is sent). On a weekend, FX shows
`MARKET_CLOSED`, which is expected.

## 4. Scheduled tasks: preview

```
powershell -ExecutionPolicy Bypass -File scripts\host\install_tasks.ps1
```

Expected: four plan lines (`AG-V1-FX-Cycles` every 15 min at +1 min daily, `AG-V1-Crypto-Daily`
every 5 min at +2 min daily, `AG-V1-LSMC-Watch` every 5 min at +3 min Mon-Fri,
`AG-V1-LSMC-Crypto-Weekend` every 5 min at +3 min Sat+Sun 20:45-23:15 UTC with its local-time
equivalent; staggered starts, 4-minute task limit, runner self-exits after 120 s), then
`WhatIf: no changes made.`

## 5. Scheduled tasks: install

```
powershell -ExecutionPolicy Bypass -File scripts\host\install_tasks.ps1 -Apply
```

Expected: `INSTALLED …` three times and a table of the three `AG-V1-*` tasks in state `Ready`.

What happens once the tasks run:
- The runner acts only inside the frozen UTC windows, so it is DST-safe:
  - FX `07:00–11:00` / `12:00–15:00` GMT (+30 min grace)
  - crypto `06:30–06:45` UTC
- Logs go to `logs\ag_v1_<mode>.log`. The Windows user must stay logged on, with MT5 open.
- To undo: `powershell -ExecutionPolicy Bypass -File scripts\host\uninstall_tasks.ps1 -Apply`.

## 6. Optional: Telegram (message-only)

```
$env:TELEGRAM_BOT_TOKEN = '<token>'; $env:TELEGRAM_CHAT_ID = '<chat id>'
powershell -ExecutionPolicy Bypass -File scripts\host\enable_telegram.ps1
```

Expected: `TELEGRAM_TEST: OK`, a test message in the chat, and then
`Telegram MESSAGE_DELIVERY enabled on this host for READY tickets + Large-SMC OPPORTUNITY alerts only.`

- Only READY tickets and OPPORTUNITY alerts are sent; WATCH and INFO stay in the archive.
- Messages are plain text, with no buttons.
- The token and chat ID are never printed or written to disk.
- For scheduled tasks, set both as persistent user environment variables.
- To disable: delete `config\local\delivery_override.yaml`.
