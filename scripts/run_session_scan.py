"""Run one read-only session scan against the Terminal MCP broker feed.

    python scripts/run_session_scan.py [--json OUT.json]

READ-ONLY: no orders, no SL/TP changes, no chart/file/tester mutation. The bearer token is
read from the env var named in config/session_scanner_v1.yaml and never printed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))
os.chdir(ROOT)

from session_scanner.report import render_text  # noqa: E402
from session_scanner.scanner import load_scanner_config, run_scan  # noqa: E402
from session_scanner.terminal_client import Mt5ReadOnlyClient, TerminalMcpClient  # noqa: E402


def _secondary_client(data_authority: dict):
    secondary = data_authority.get("secondary") or {}
    url = secondary.get("url") or os.environ.get(secondary.get("url_env", ""))
    if not url:
        return None
    return Mt5ReadOnlyClient(url, secondary.get("token_env", "MT5_READONLY_MCP_TOKEN"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="write the machine-readable scan to this path")
    args = ap.parse_args()
    cfg = load_scanner_config()
    da = cfg["data_authority"]
    primary = da.get("primary") or {"url": da.get("terminal_mcp_url"), "token_env": da.get("token_env")}
    client = TerminalMcpClient(primary["url"], primary["token_env"], source_name="TERMINAL_MCP")
    scan = run_scan(client, cfg, local_utc_now=datetime.now(timezone.utc),
                    secondary_source=_secondary_client(da))
    print(render_text(scan))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(scan, f, indent=2, default=str)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
