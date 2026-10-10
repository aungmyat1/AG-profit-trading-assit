# AG V1 host go-live kit (Windows MT5 host)

This kit runs on the Windows machine where the **VT Markets DEMO** MT5 terminal is installed,
open and logged in. The complete objective universe is three FX majors (EURUSD, GBPUSD,
USDJPY), gold (XAUUSD), and two crypto instruments (BTCUSDT, ETHUSDT): both FX session cycles
produce informational tickets, both crypto instruments produce daily-window tickets, and
Large-SMC watches all six instruments. It is read-only: nothing here places, checks or
modifies orders or positions. The installed scheduled FX task keeps `run_manual_jobs`, then
uses the canonical daily evaluator; each selected result is archived and appended to
`journal\ticket_store` before any optional message-only delivery. The host fails closed unless
`account_info().trade_mode` is DEMO. Telegram is off by default and requires both the
host-local canonical recipient allowlist and the environment feature/owner allowlist. The
unscheduled legacy `--mode fx` path remains available without `--canonical`; its separate
paper-ledger behavior is not part of the canonical scheduled path.

## Prerequisites (one time)

1. Install 64-bit Python 3.11, then from the repo root run:
   ```
   py -3.11 -m venv .venv
   .venv\Scripts\pip install -r requirements.txt
   ```
2. Credentials go in persistent user environment variables, never in git:
   `VTMARKETS-DEMO-LOGIN`, `VTMARKETS-DEMO-PASSWORD`, `VTMARKETS-DEMO-SERVER`.
   The underscore forms `VTMARKETS_DEMO_*` also work.
3. Optionally set `MT5_TERMINAL_PATH` to the VT Markets `terminal64.exe`.

Run every step from the repo root, in this order. Stop at the first step that does not show
its expected output.

## Required actionability preflight (before diagnosis or task installation)

The host-local `config/local/actionability_policy.yaml` must explicitly contain:

```yaml
# owner-set operational parameter, 2026-10-10, not a contract value.
lsmc_min_remaining_reward_fraction: 0.5
```

Preserve the host policy's other fields. The tracked policy is a template, not a
runtime fallback. Run this read-only check before proceeding:

```
.venv\Scripts\python.exe scripts\host\preflight_actionability.py
```

Expected: `PASS lsmc_min_remaining_reward_fraction=0.5`, exit 0. Missing or invalid
values exit nonzero and name the key; stop deployment. The emitter otherwise fails
closed and logs `LSMC_CONFIG_MISSING` once per run; summaries show `CONFIG_MISSING`.

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
- `FX <SYMBOL> <ASIAN_LONDON|LONDON_NEWYORK> data=… decision=READY|NO_TRADE|BLOCKED|DATA_ERROR metadata=HOST_CAPTURED paper=OPENED|ALREADY_RECORDED|INELIGIBLE:…`.
- `LSMC <SYMBOL> data=… state=IDLE|DEVELOPING|NEAR_POI|OPPORTUNITY|… alerts=[…]`.

EURUSD and GBPUSD always run. USDJPY and XAUUSD run only after step 2. Results are archived
under `journal\host_smoke\` (ARCHIVE_ONLY; nothing is sent). On a weekend, FX shows
`MARKET_CLOSED`, which is expected.

## 4. Scheduled tasks: objective preflight and preview

```
.venv\Scripts\python.exe scripts\host\verify_objective.py
powershell -ExecutionPolicy Bypass -File scripts\host\install_tasks.ps1
```

The preflight must report nine PASS checks and `RESULT: PASS`; it verifies the complete
six-instrument universe, both FX cycles, all six host metadata captures, the active two-symbol
crypto config, Large-SMC coverage, all three scheduler bindings (including `--canonical` on
FX), the ARCHIVE_ONLY default, and the legacy READY/OPPORTUNITY scopes. Canonical FX messages
remain disabled unless a host-local authorized-recipient file and the environment gates agree. Expected from the installer:
three plan lines (`AG-V1-FX-Cycles` every 15 min at +1 min daily, `AG-V1-Crypto-Daily`
every 5 min at +2 min daily, and `AG-V1-LSMC-Watch` every 5 min at +3 min daily;
staggered starts, 4-minute task limit, runner self-exits after 120 s), then
`WhatIf: no changes made.` The daily Large-SMC task watches crypto throughout weekends and
returns `MARKET_CLOSED` for FX while its market is shut.

## 5. Scheduled tasks: install

```
powershell -ExecutionPolicy Bypass -File scripts\host\install_tasks.ps1 -Apply
```

Expected: the objective preflight passes, `INSTALLED …` appears three times, then the automatic
post-install verification reports three `[PASS]` lines and
`RESULT: PASS (3/3 scheduled task bindings valid; no duplicate weekend watcher)`. The installer
also removes the superseded narrow weekend-only watcher if present. Verification can be rerun
without changing tasks:

```
powershell -ExecutionPolicy Bypass -File scripts\host\verify_tasks.ps1
```

What happens once the tasks run:
- The scheduled FX action is `live_candles_smoke.py --mode fx --canonical`. It runs the existing
  Manual Trade Ticket daily jobs, then evaluates only the active frozen cycle with the read-only
  MT5 provider. Canonical evaluation records are archived and persisted to `TICKET_STORE_V1`
  before ticket delivery. Append-only session events record store/delivery outcomes; deterministic
  session summaries reconcile missing weekday pairs as `MISSED` and weekend closures as
  `OUT_OF_SESSION`. Summary sends are deduplicated and uncertain outcomes are never auto-retried.
- The runner acts only inside the frozen UTC windows, so it is DST-safe:
  - FX `07:00–11:00` / `12:00–15:00` GMT (+30 min grace)
  - crypto `06:30–06:45` UTC
- Existing tasks that call `scripts\run_fx_cycle_once.py --cycle <CYCLE>` are supported; that
  command now delegates to the maintained host runtime instead of the removed pilot packages.
- Logs go to `logs\ag_v1_<mode>.log`. The Windows user must stay logged on, with MT5 open.
- To undo: `powershell -ExecutionPolicy Bypass -File scripts\host\uninstall_tasks.ps1 -Apply`.

## 6. Optional: Telegram (message-only)

```
$env:TELEGRAM_BOT_TOKEN = '<token>'; $env:TELEGRAM_CHAT_ID = '<chat id>'
powershell -ExecutionPolicy Bypass -File scripts\host\enable_telegram.ps1
```

Expected: `TELEGRAM_PROPOSAL_TEST: OK`, a message headed
`SIMULATED TELEGRAM DELIVERY VALIDATION -- NOT A MARKET SIGNAL`, and then
`Telegram MESSAGE_DELIVERY enabled on this host for READY tickets + Large-SMC OPPORTUNITY alerts only.`
Validate the enabled override, credentials, formatter, and Telegram API path again with:

```
powershell -ExecutionPolicy Bypass -File scripts\host\verify_telegram.ps1
```

- Only READY tickets and OPPORTUNITY alerts are sent; WATCH and INFO stay in the archive.
- Messages are plain text, with no buttons.
- The token and chat ID are never printed or written to disk.
- For scheduled tasks, set both as persistent user environment variables.
- To disable: delete `config\local\delivery_override.yaml`.
- Check report health (read-only, sends nothing, works even if `.venv` is missing):
  `py scripts\host\telegram_status.py` (add `--json` for machine output). It prints
  `TELEGRAM_REPORT_STATUS: OK | DEGRADED | DOWN | DISABLED` with reasons, and exits 1 on DEGRADED/DOWN.
  Every send is logged to `logs\telegram.log` as `TELEGRAM_SENT_OK` or `TELEGRAM_SEND_FAILED`.

For the complete installation procedure, expected outputs, archive paths, and rollback commands,
see `docs/setup/INSTALL_WINDOWS_MT5_DEMO_HOST.md`.
