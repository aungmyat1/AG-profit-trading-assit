"""Read-only Terminal MCP adapter (MetaTrader 5 MCP over streamable HTTP).

The ONLY network path in the scanner. `call()` refuses every tool name that is not in
READ_ONLY_TOOLS -- an allowlist, not a denylist, so a tool the server adds later is
blocked by default. Claude Code's user-scope permission denies do not govern this
process's HTTP calls; this allowlist is the scanner's own enforcement.

The bearer token is read from the environment variable named in config at call time and
is never stored on the object, logged, or included in any exception message.
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional

READ_ONLY_TOOLS = frozenset({
    "get_time_information",
    "get_marketwatch_symbols",
    "get_chart_history",
    "get_chart_ticks_history",
    "get_trading_account_info",
})


class TerminalToolBlocked(PermissionError):
    pass


class TerminalMcpError(RuntimeError):
    pass


def _iso(dt: datetime) -> str:
    return dt.replace(tzinfo=None).isoformat(timespec="seconds")


class TerminalMcpClient:
    def __init__(self, url: str, token_env: str, timeout_s: float = 30.0,
                 source_name: str = "TERMINAL_MCP"):
        self._url = url
        self._token_env = token_env
        self._timeout_s = timeout_s
        self._session_id: Optional[str] = None
        self._next_id = 1
        self.source_name = source_name

    # ------------------------------------------------------------------ transport
    def _post(self, payload: dict) -> Optional[dict]:
        token = os.environ.get(self._token_env)
        if not token:
            raise TerminalMcpError(f"TOKEN_ENV_MISSING: {self._token_env}")
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        req = urllib.request.Request(self._url, data=json.dumps(payload).encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self._timeout_s) as resp:
                sid = resp.headers.get("Mcp-Session-Id")
                if sid:
                    self._session_id = sid
                body = resp.read().decode("utf-8", errors="replace")
        except Exception as exc:  # never echo headers
            raise TerminalMcpError(f"TRANSPORT_ERROR: {type(exc).__name__}") from None
        if not body.strip():
            return None
        if body.lstrip().startswith("{"):
            return json.loads(body)
        data_lines = [ln[5:].strip() for ln in body.splitlines() if ln.startswith("data:")]
        return json.loads(data_lines[-1]) if data_lines else None

    def _rpc(self, method: str, params: dict) -> Any:
        self._next_id += 1
        msg = self._post({"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": params})
        if msg is None:
            raise TerminalMcpError(f"EMPTY_RESPONSE: {method}")
        if "error" in msg:
            raise TerminalMcpError(f"RPC_ERROR: {msg['error'].get('message')}")
        return msg["result"]

    def connect(self) -> dict:
        info = self._rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                        "clientInfo": {"name": "ag-session-scanner-v1", "version": "1"}})
        try:
            self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        except TerminalMcpError:
            pass
        return info.get("serverInfo", {})

    def call(self, name: str, arguments: Dict[str, Any]) -> Any:
        if name not in READ_ONLY_TOOLS:
            raise TerminalToolBlocked(f"BLOCKED_NON_READ_ONLY_TOOL: {name}")
        if self._session_id is None:
            self.connect()
        result = self._rpc("tools/call", {"name": name, "arguments": arguments})
        text = "".join(c.get("text", "") for c in result.get("content", []) if c.get("type") == "text")
        if result.get("isError"):
            raise TerminalMcpError(f"TOOL_ERROR: {name}: {text[:200]}")
        return json.loads(text)

    # ------------------------------------------------------------------ MarketDataSource
    def time_information(self) -> dict:
        return self.call("get_time_information", {})

    def symbol_info(self, broker_symbol: str) -> Optional[dict]:
        out = self.call("get_marketwatch_symbols", {"symbol": broker_symbol, "include_hidden": True, "limit": 5})
        matches = [s for s in out.get("symbols", []) if s.get("symbol") == broker_symbol]
        return matches[0] if len(matches) == 1 else None

    def bars(self, broker_symbol: str, timeframe: str, from_server: datetime, to_server: datetime) -> List[dict]:
        out = self.call("get_chart_history", {"symbol": broker_symbol, "period": timeframe,
                                              "datetime_from": _iso(from_server), "datetime_to": _iso(to_server)})
        if not out.get("ok", False):
            raise TerminalMcpError(f"HISTORY_NOT_OK: {broker_symbol} {timeframe}")
        return list(out.get("history", []))

    def ticks(self, broker_symbol: str, from_server: datetime, to_server: datetime) -> List[dict]:
        out = self.call("get_chart_ticks_history", {"symbol": broker_symbol, "datetime_from": _iso(from_server),
                                                    "datetime_to": _iso(to_server)})
        return list(out.get("history", []))

    def account_info(self) -> dict:
        out = self.call("get_trading_account_info", {})
        acct = out.get("account", out)
        return {k: acct.get(k) for k in ("equity", "balance", "currency", "type", "server")}


class Mt5ReadOnlyClient(TerminalMcpClient):
    """Explicit secondary ``mt5ReadOnly`` source using the same read-only MCP schema."""

    def __init__(self, url: str, token_env: str, timeout_s: float = 30.0):
        super().__init__(url, token_env, timeout_s, source_name="MT5_READONLY")
