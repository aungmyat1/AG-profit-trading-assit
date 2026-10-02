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
- **`Request timed out` on start (Claude Code / Cowork)**: fixed 2026-09-29.
  `metatrader-mcp-server` logs in to the MT5 terminal *before* it answers the MCP
  `initialize` request, so a closed, slow, or logged-out terminal (or a missing
  executable, or an upstream exit) outlasted the client's handshake timeout. The
  launcher now uses `startDeferredReadOnlyProxy` (`web/scripts/readonly_mcp_proxy.mjs`):
  it answers `initialize`/`ping` itself, queues requests until the upstream server is
  ready, and after `MT5_MCP_STARTUP_TIMEOUT_MS` (default `20000`) returns the
  `mt5_setup_status` tool instead of waiting, then sends
  `notifications/tools/list_changed` once MT5 connects. If the upstream server fails to
  start or exits, the MCP stays connected in setup-status mode and names the cause.
  If tools still show only `mt5_setup_status`: open MT5, log in to the demo account,
  run `node web/scripts/check_mt5_mcp.mjs`, then reconnect the MCP (`/mcp` in Claude Code).

## Current VS Code MCP setup

- Keep the MT5 terminal open and logged into the intended Demo account. The launcher
  never starts the terminal. `MT5_ENVIRONMENT` must be explicitly set to `DEMO` in
  the existing `src/.env` file.
- Install the pinned MT5 server: `pip install metatrader-mcp-server==0.5.1`
  (official: github.com/ariadng/metatrader-mcp-server, Python >= 3.10, Windows + MT5).
  Upstream registers tools without MCP annotations, so the launcher exposes only the
  exact query tools in `MT5_READ_ONLY_TOOL_NAMES` (`web/scripts/readonly_mcp_proxy.mjs`).
  Re-review that list before changing the pinned version.
- **Demo account: VT Markets Demo (default, 2026-09-29).** Put these keys in `src/.env`
  (gitignored; never in MCP JSON):

  ```
  MT5_ENVIRONMENT=DEMO
  VTMARKETS-DEMO-LOGIN=<numeric demo login>
  VTMARKETS-DEMO-PASSWORD=<demo password>
  VTMARKETS-DEMO-SERVER=VTMarkets-Demo
  ```

  Underscore forms (`VTMARKETS_DEMO_*`) and `MT5_LOGIN`/`MT5_PASSWORD`/`MT5_SERVER`
  aliases also work. The server must match the exact name shown in the MT5 login dialog
  and must start with `VTMarkets-Demo`; anything else is refused. To use the old Vantage
  Demo login instead, set `MT5_DEMO_BROKER=VANTAGE` (then the `VANTAGE-DEMO-*` keys apply).
- **Setup-status mode.** If credentials are incomplete, the server is not a demo server, or
  the host is not Windows (MetaTrader 5 and its Python package are Windows-only, so a cloud
  container can never connect), the launcher stays connected and exposes a single
  read-only `mt5_setup_status` tool explaining what to fix, instead of the opaque
  "Connection closed".
- VT Markets broker symbols are not yet recorded in `config/mt5.yaml` `symbol_map`; capture
  them read-only (`readonly_get_all_symbols`) before routing strategy symbols to it.
- If the MCP executable is not discovered automatically, set `MT5_MCP_COMMAND` in
  `src/.env` to its full path. The launcher forwards only Demo credentials and strips
  live-account, Bybit API, and paper API credentials from the child environment.
- Bybit uses the official `bybit-official-trading-server@2.1.22` (Node >= 20.6), pinned
  rather than `@latest`. It is unauthenticated and testnet-forced. Its public tools expose market data
  only; Bybit account and order tools are intentionally filtered out.
- Run `node web/scripts/check_mt5_mcp.mjs` from the workspace root for a read-only
  setup diagnostic. Secret values are never printed.
- Restart the MCP server (or reload VS Code/start a new chat) after config changes.

## Claude Desktop setup (chat sessions)

Claude Desktop does **not** read `.mcp.json` or `.vscode/mcp.json`. It reads
`%APPDATA%\Claude\claude_desktop_config.json` and launches servers from its own working
directory, so the workspace-relative `web/scripts/start_mt5_mcp.mjs` path fails there.
Claude Code on the web (cloud) sessions run on Linux and land in setup-status mode unless
they use the remote bridge below; otherwise MT5 chat access needs Claude Desktop (or Claude
Code) on the Windows PC running MT5.

On that Windows PC, from the project root:

```
node web/scripts/claude_desktop_config.mjs          # dry run: shows the merged config
node web/scripts/claude_desktop_config.mjs --write  # backs up, then merges mt5ReadOnly
node web/scripts/check_mt5_mcp.mjs                  # includes a Claude Desktop check
```

The script writes absolute paths to `node.exe` and `start_mt5_mcp.mjs`, keeps every other
server, writes no credentials (they stay in `src/.env`), and warns if `mtx`/`mbt` are
registered. Then fully quit Claude Desktop from the tray, reopen it, and start a new chat.
Equivalent manual entry:

```json
{
  "mcpServers": {
    "mt5ReadOnly": {
      "command": "C:\\Program Files\\nodejs\\node.exe",
      "args": ["D:\\path\\to\\AG-profit-trading-assit\\web\\scripts\\start_mt5_mcp.mjs"]
    }
  }
}
```

These local MCP guardrails do not replace project execution authority, validation,
or venue qualification. The third-party MT5 server may internally implement trading
tools; they are not exposed through this workspace's MT5 launcher.

## Remote access from cloud sessions (2026-10-02)

A Linux client cannot run MT5, so the Windows PC serves its normal read-only launcher over
HTTP and the cloud session's `mt5ReadOnly` launcher forwards to it. Tool names, the
read-only allowlist (enforced on both ends) and the setup-status fallback are identical to a
local run. Demo credentials never leave the Windows PC.

1. **Windows PC** (MT5 open and logged in to the Demo account, local MCP already working).
   Add a random token of at least 32 characters to `src/.env`, then start the server:

   ```
   MT5_MCP_REMOTE_TOKEN=<random 32+ characters>
   # optional: MT5_MCP_REMOTE_PORT=8765  MT5_MCP_REMOTE_HOST=127.0.0.1
   ```

   ```
   node web/scripts/serve_mt5_mcp_remote.mjs
   ```

   It binds `127.0.0.1:8765` and accepts only `POST /mcp` with
   `Authorization: Bearer <token>`. Publish it through an HTTPS tunnel you control (for
   example `cloudflared tunnel --url http://127.0.0.1:8765` or Tailscale Funnel); never open
   a raw public port.
2. **Cloud environment** (claude.ai/code environment settings → environment variables):

   ```
   MT5_ENVIRONMENT=DEMO
   MT5_MCP_REMOTE_URL=https://<your-tunnel-host>/mcp
   MT5_MCP_REMOTE_TOKEN=<same token>
   ```

   Allow `<your-tunnel-host>` in the environment's network policy. `.mcp.json` sets
   `NODE_USE_ENV_PROXY=1` so the launcher's `fetch` uses the sandbox HTTPS proxy. Start a
   new session; `mt5ReadOnly` then lists the same `readonly_*` tools as on Windows.

The URL must be `https://` (plain `http://` only for localhost), the token is never logged,
and a wrong token, unreachable tunnel or stopped server shows up as the
`mt5_setup_status` reason. Server-initiated `tools/list_changed` notifications are not
relayed; if MT5 was still connecting, list tools again. Code:
`web/scripts/mt5_remote_bridge.mjs`, `web/scripts/serve_mt5_mcp_remote.mjs`; tests:
`web/tests/mt5_remote_bridge.test.mjs`.

## MetaTrader 5 app built-in MCP servers (2026-10-02)

The MT5 app publishes its own MCP servers. They are registered in `.mcp.json` (Claude Code)
and `.codex/config.toml` (Codex) **without tokens**; the bearer tokens come from environment
variables on the machine running the client:

| Server | URL | Token variable | Reachable from |
| --- | --- | --- | --- |
| `metaeditor` | `http://127.0.0.1:22345/mcp` | `MT5_APP_MCP_TOKEN` | the Windows PC running MT5 only |
| `terminal` | `http://127.0.0.1:22346/mcp` | `MT5_APP_MCP_TOKEN` | the Windows PC running MT5 only |
| `marketdata` | `https://www.metatrader.com/mcp` | `METATRADER_MARKETDATA_MCP_TOKEN` | anywhere the host is allowed |

Claude Code and Codex read these from the **process environment, not `src/.env`**. If the
tokens are kept in `src/.env`, copy them into user environment variables (values never
printed; also checks that ports 22345/22346 are listening), then restart the client:

```
powershell -ExecutionPolicy Bypass -File scripts\host\set_mt5_app_mcp_env.ps1
```

Or set them by hand on the Windows PC (new terminal / restart Claude Code afterwards):

```
setx MT5_APP_MCP_TOKEN "<token shown by the MT5 app>"
setx METATRADER_MARKETDATA_MCP_TOKEN "<mq-... token shown by the MT5 app>"
```

For a cloud session, only `marketdata` can work: set `METATRADER_MARKETDATA_MCP_TOKEN` in the
environment settings and allow `www.metatrader.com` in its network policy. The `127.0.0.1`
servers are unreachable from the cloud; use the remote bridge above for terminal data.

Safety: the MT5 app's `terminal` server is not filtered by this project's read-only
allowlist and may expose trading tools. `.claude/settings.json` therefore puts every
`mcp__terminal` tool under `permissions.ask`, so each call needs the owner's explicit
approval, and the authority order in `AGENTS.md` still applies: agents must not place,
modify or close orders through it. Codex has no equivalent gate here; treat its `terminal`
tools the same way. Never paste these tokens into committed files; regenerate them in the
MT5 app if they are exposed.
