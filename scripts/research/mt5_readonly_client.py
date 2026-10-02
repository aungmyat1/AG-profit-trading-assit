"""Small, fail-closed stdio MCP client for the local MT5 read-only launcher."""
from __future__ import annotations

import json
import os
import re
import queue
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

ALLOWED_TOOLS = frozenset({
    "readonly_get_account_info", "readonly_get_all_symbols", "readonly_get_symbols",
    "readonly_get_symbol_price", "readonly_get_candles_latest",
})


class MCPError(RuntimeError):
    pass


_CREDENTIAL_KEYS = frozenset({
    "MT5_ENVIRONMENT", "MT5_DEMO_BROKER", "VTMARKETS-DEMO-LOGIN", "VTMARKETS_DEMO_LOGIN",
    "VTMARKETS_DEMO_ACCOUNT_ID", "VTMARKETS-DEMO-PASSWORD", "VTMARKETS_DEMO_PASSWORD",
    "VTMARKETS-DEMO_SERVER", "VTMARKETS_DEMO_SERVER", "MT5_ACCOUNT_ID", "MT5_LOGIN",
    "MT5_PASSWORD", "MT5_SERVER",
})
_LEGACY_VT_ALIASES = {
    "VTMARKET-DEMO-LOGIN": "VTMARKETS-DEMO-LOGIN",
    "VTMARKET-DEMO_PASSWORD": "VTMARKETS-DEMO-PASSWORD",
    "VTMARKET-DEMO_SERVER": "VTMARKETS-DEMO_SERVER",
}


def read_mt5_env_file(path: str | Path) -> dict[str, str]:
    """Read only the launcher's Demo identity keys; never include values in errors/logs."""
    values = {}
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = (part.strip() for part in line.split("=", 1))
            canonical_key = _LEGACY_VT_ALIASES.get(key, key)
            if canonical_key not in _CREDENTIAL_KEYS:
                continue
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            values[canonical_key] = value
    except OSError as exc:
        raise MCPError("cannot read requested MT5 environment file") from exc
    return values


def verified_vt_demo_configuration(env: dict[str, str]) -> bool:
    """Check explicit launcher interlocks without exposing identity values."""
    server = env.get("VTMARKETS-DEMO_SERVER") or env.get("MT5_SERVER", "")
    return env.get("MT5_ENVIRONMENT", "").upper() == "DEMO" and bool(re.match(r"^VTMarkets-Demo", server, re.I))


class ReadonlyMT5Client:
    def __init__(self, root: str | Path | None = None, startup_timeout: float = 40,
                 request_timeout: float = 30, process_factory=subprocess.Popen,
                 env_overrides: dict[str, str] | None = None):
        self.root = Path(root or Path(__file__).resolve().parents[2])
        self.startup_timeout = startup_timeout
        self.request_timeout = request_timeout
        self._factory = process_factory
        self._env_overrides = dict(env_overrides or {})
        self._proc = None
        self._responses: queue.Queue = queue.Queue()
        self._pending_responses: dict[str, dict[str, Any]] = {}
        self._next_id = 0
        self.tools: dict[str, dict[str, Any]] = {}

    def __enter__(self):
        script = self.root / "web" / "scripts" / "start_mt5_mcp.mjs"
        if not script.is_file():
            raise MCPError("MT5 read-only launcher not found")
        self._proc = self._factory(
            ["node", str(script)], cwd=str(self.root), stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
            bufsize=1, env={**os.environ, **self._env_overrides},
        )
        threading.Thread(target=self._reader, daemon=True).start()
        deadline = time.monotonic() + self.startup_timeout
        try:
            self._request("initialize", {
                "protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "ag-free-research-pipeline", "version": "1.0"},
            }, deadline=deadline)
            self._send_notification("notifications/initialized", {})
            while time.monotonic() < deadline:
                try:
                    result = self._request("tools/list", {}, deadline=min(deadline, time.monotonic() + 5.0))
                    listed = result.get("tools") if isinstance(result, dict) else None
                    if isinstance(listed, list):
                        if any(isinstance(t, dict) and t.get("name") == "readonly_mt5_setup_status" for t in listed):
                            raise MCPError("MT5 launcher setup is incomplete; market-data tools unavailable")
                        self.tools = {t["name"]: t for t in listed if isinstance(t, dict) and t.get("name") in ALLOWED_TOOLS}
                        if self.tools:
                            return self
                except MCPError as exc:
                    if "timeout" not in str(exc).lower() or self._proc.poll() is not None:
                        raise
                time.sleep(0.25)
            raise MCPError("timed out waiting for read-only MT5 tools")
        except Exception:
            self.close()
            raise

    def _reader(self):
        try:
            for line in self._proc.stdout:
                try:
                    msg = json.loads(line)
                except (json.JSONDecodeError, TypeError):
                    self._responses.put({"_malformed": True})
                    continue
                if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
                    self._responses.put({"_malformed": True})
                elif "id" in msg:
                    self._responses.put(msg)
        finally:
            self._responses.put(None)

    def _send(self, msg):
        if not self._proc or self._proc.poll() is not None:
            raise MCPError("MT5 launcher is not running")
        try:
            self._proc.stdin.write(json.dumps(msg, separators=(",", ":")) + "\n")
            self._proc.stdin.flush()
        except (OSError, BrokenPipeError) as exc:
            raise MCPError("MT5 launcher communication failed") from exc

    def _send_notification(self, method, params):
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _request(self, method, params, deadline=None):
        self._next_id += 1
        req_id = self._next_id
        self._send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
        end = deadline if deadline is not None else time.monotonic() + self.request_timeout
        if str(req_id) in self._pending_responses:
            msg = self._pending_responses.pop(str(req_id))
            return self._decode_response(msg, method)
        while True:
            remaining = end - time.monotonic()
            if remaining <= 0:
                raise MCPError(f"timeout waiting for MCP {method}")
            try:
                msg = self._responses.get(timeout=remaining)
            except queue.Empty as exc:
                raise MCPError(f"timeout waiting for MCP {method}") from exc
            if msg is None:
                raise MCPError("MT5 launcher closed its output")
            if msg.get("_malformed"):
                raise MCPError("malformed MCP response")
            if str(msg.get("id")) != str(req_id):
                try:
                    other_id = int(msg.get("id"))
                except (TypeError, ValueError):
                    raise MCPError("unexpected MCP response id") from None
                if other_id < req_id:  # delayed response to an earlier bounded startup poll
                    continue
                self._pending_responses[str(other_id)] = msg
                continue
            return self._decode_response(msg, method)

    @staticmethod
    def _decode_response(msg, method):
        if "error" in msg:
            raise MCPError(f"MCP {method} returned an error")
        if not isinstance(msg.get("result"), dict):
            raise MCPError("malformed MCP response")
        return msg["result"]

    def call(self, name: str, arguments: dict[str, Any]):
        if name not in ALLOWED_TOOLS:
            raise MCPError("tool is outside the client read-only allowlist")
        if name not in self.tools:
            raise MCPError("requested read-only tool is unavailable")
        result = self._request("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError") is True:
            raise MCPError("read-only MT5 tool reported an error")
        content = result.get("content")
        if not isinstance(content, list):
            raise MCPError("malformed tool result")
        return result

    def close(self):
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            if proc.stdin:
                proc.stdin.close()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                proc.kill()

    def __exit__(self, *_):
        self.close()

