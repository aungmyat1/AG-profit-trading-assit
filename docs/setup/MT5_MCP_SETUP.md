# MT5 MCP — decision and setup

> **Note (2026-08-25):** "automated execution" below means the demo-only execution layer added
> 2026-08-22 exists and *can* submit orders — it does not mean anything runs unattended today, and
> live-account execution is explicitly disabled (`live_execution_authorized: false` in
> `config/strategy.yaml`). See `STATUS.md` for the current runtime state.

**Current integration: workspace-configured, read-only MCP spot checks.**

The repository's `.mcp.json` and `.vscode/mcp.json` configure an MT5 MCP launcher
and Bybit MCP launcher for VS Code-compatible clients. The MT5 launcher requires
`MT5_ENVIRONMENT=DEMO`, loads demo credentials from `src/.env`, and filters both
tool discovery and tool calls to the server's explicitly annotated read-only tools.
The Bybit launcher is pinned to `bybit-official-trading-server@2.1.22`, forces
`BYBIT_TESTNET=true`, strips API credentials, and only exposes explicitly
read-only public market-data tools. Neither MCP configuration authorizes any order.
For proposals, execution, or research evidence, continue using the canonical project
engines and data paths described in `AGENTS.md` and `PROJECT_STATUS.md`.

The MTX/MBT automated-execution statements below are dated historical context only;
they are not current authority and those servers are not configured by this workspace.

---

## Historical note: why `metatrader` was selected (2026-08-22)

It works. Verified live:

```
account_info      1144985 · balance 987.82 USD · leverage 500

get_candles_latest EURUSD M15
  2026-08-17 07:45   1.15866  1.15869  1.15861  1.15866   vol 61
  2026-08-17 07:30   1.15867  1.15872  1.15853  1.15866   vol 377
  2026-08-17 07:15   1.15871  1.15874  1.15855  1.15867   vol 412
```

**Every failure earlier in the session was MetaTrader 5 being closed, not a
configuration fault.** The intermediate diagnoses — "wrong terminal", "dead
connector" — were both wrong. The terminal simply was not running, and after
launching it the API needs a moment before its symbol cache is readable, which
produced the misleading `Symbol 'EURUSD' not found` in between.

**Operating requirement: MT5 must be open and logged in for the MCP to answer.**
Neither server can start it.

## Why not MBT

Installed to solve a problem that did not exist. Its distinctive capability — EA
compilation and driving the Strategy Tester headlessly — is not used here. This
project has no MQL5 indicator and no EA.

It also arrived badly: an elevated PowerShell put it in `C:\Windows\System32\MBT`,
and its installer copied `SignalLogger.mqh` and `MBT_IndicatorHost.mq5` into **every**
MT5 terminal profile. The `.mq5` is an Expert Advisor.

**Removal: `cleanup_mbt.ps1`** (run as Administrator). Quarantines the install and
both MQL5 artifacts to a dated folder, leaves `claude_desktop_config.json` untouched,
then re-verifies the MT5 connection.

## Historical note: MTX policy (superseded)

MTX provides the read/**write** half — it opens, modifies and closes real positions. 
Since the project charter was updated on 2026-08-22 to allow automated trading, MTX is the recommended way to execute the Python-driven trades directly via the MCP or python integrations.

The old claim that MTX or a scheduler permits unattended live trading is superseded.
Current execution authority and explicit per-command confirmation are defined in
`AGENTS.md`, `config/trading.yaml`, and `PROJECT_STATUS.md`.

---

## Known defects in the kept server

**`account_type` reports `"real"` on a demo account.** Confirmed again today: the API
says `real`, the title bar says `1144985 - VTMarkets-Demo: Demo Account - Hedge`.
**The field is unusable as a live-account interlock.** The interlock is the trader's
own eyes. Already recorded in `STATUS.md`.

**`spread` returns 0 on EURUSD.** Not an error — it is what this feed reports — but
any EURUSD cost figure derived from it is understated. Relevant because the 12-month
backtest charges spread from this column; the 0.127R/trade cost drag ex-gold is a
floor, not an estimate.

---

## Operating notes

- **Keep MT5 open** whenever the MCP is needed.
- MCP servers load **per session**. A new server needs a new conversation, not just
  an app restart.
- Symbol names carry broker suffixes on some instruments — gold is `XAUUSD.crp`.
- A symbol absent from Market Watch is invisible to the API even on the right
  terminal. Right-click → Show All.

## What the MCP does not replace

`scripts/fetch_mt5_year.py` remains the canonical data path. It writes sha256
manifests and drift detection; a conversational fetch writes neither, and
`STRATEGY_LEDGER.md` rule 2 requires every result to name its data hash.

Use the MCP for spot checks and live desk reads. Use the script for anything that
becomes evidence.

---

## Worth keeping from the guide

One technique, adopted into `fetch_mt5_year.py` as `offset_from_reopen()`:

> derive the broker's UTC offset from the weekly reopen gap — FX reopens at a fixed
> instant, Sunday 17:00 New York — instead of asserting a DST table.

Validated on both fixtures: the reopen hour flips 21:00 ↔ 22:00 UTC exactly at the
changeovers, confirming +3 summer / +2 winter by **deriving** it rather than assuming
it, and catching a broker that does not follow US DST.

**Source:** [How to Fully Connect Claude Code and Desktop to MT5 for Free](https://offbeatforex.com/how-to-connect-claude-to-mt5/) — Offbeat Forex, 3 Aug 2026.

---

## Common Troubleshooting

- **MT5 Terminal Path**: If MT5 is installed in a custom location, explicitly pass
  the path to `terminal64.exe` using the `--path` argument in `args`.
- **Connection Failures**: Ensure the MT5 terminal application is running in the
  background while Antigravity makes calls.
- **Account Permissions**: Ensure your MT5 login credentials have trade/read
  permissions on the target server.

## Current VS Code MCP setup

- Keep the MT5 terminal open and logged into the intended Demo account. The launcher
  never starts the terminal. `MT5_ENVIRONMENT` must be explicitly set to `DEMO` in
  the existing `src/.env` file.
- Credentials use the existing `VANTAGE-DEMO-LOGIN`, `VANTAGE-DEMO_PASSWORD`, and
  `VANTAGE-DEMO-SERVER` keys in `src/.env`. Do not put credentials in MCP JSON.
- If the MCP executable is not discovered automatically, set `MT5_MCP_COMMAND` in
  `src/.env` to its full path. The launcher forwards only Demo credentials and strips
  live-account, Bybit API, and paper API credentials from the child environment.
- Bybit is unauthenticated and testnet-forced. Its public tools expose market data
  only; Bybit account and order tools are intentionally filtered out.
- Run `node web/scripts/check_mt5_mcp.mjs` from the workspace root for a read-only
  setup diagnostic. Secret values are never printed.
- Restart the MCP server (or reload VS Code/start a new chat) after config changes.

These local MCP guardrails do not replace project execution authority, validation,
or venue qualification. The third-party MT5 server may internally implement trading
tools; they are not exposed through this workspace's MT5 launcher.
