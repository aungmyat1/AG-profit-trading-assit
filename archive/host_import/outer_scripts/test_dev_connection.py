#!/usr/bin/env python
"""Read-only local development connectivity check (AG_VSCODE_ONE_CLICK_TEST_RUN_V1).

Calls ONLY: GET /api/health, GET /api/broker/status, and (optionally) the frontend's
root URL. Never calls authorize-demo, any execution endpoint, or order_send -- this
script cannot submit a broker order under any circumstance.

Usage:
    python scripts/test_dev_connection.py [--api-url http://127.0.0.1:8000] [--frontend-url http://localhost:3000]
"""
from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
import json


def _get_json(url: str, timeout: float = 5.0):
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 -- local dev URL only
        return resp.status, json.loads(resp.read().decode("utf-8"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--frontend-url", default="http://localhost:3000")
    args = parser.parse_args(argv)

    print("AG DEVELOPMENT CHECK")
    print()

    results = []

    # 1. FastAPI reachable + health
    try:
        status, body = _get_json(f"{args.api_url}/api/health")
        ok = status == 200 and body.get("status") == "OK"
        results.append(("FastAPI reachable", ok))
        results.append(("Health endpoint", ok))
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        results.append(("FastAPI reachable", False))
        results.append(("Health endpoint", False))
        _print_results(results)
        print()
        print("RESULT = BACKEND_UNREACHABLE")
        print(f"  reason: {exc}")
        return 1

    # 2. broker/status endpoint + broker connectivity (informational, never blocking)
    broker_connected = False
    environment = None
    try:
        status, body = _get_json(f"{args.api_url}/api/broker/status")
        results.append(("Broker status endpoint", status == 200))
        broker_connected = bool(body.get("connected"))
        environment = body.get("environment")
        if broker_connected:
            results.append(("Broker connected", True))
            results.append((f"Environment = {environment}", environment == "DEMO"))
        else:
            results.append(("MT5 disconnected", None))  # WARN, not FAIL -- see below
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        results.append(("Broker status endpoint", False))
        print(f"  broker/status error: {exc}")

    # 3. frontend reachability (best-effort only -- not required for backend to be "ready")
    frontend_reachable = None
    try:
        req = urllib.request.Request(args.frontend_url, method="GET")
        with urllib.request.urlopen(req, timeout=5.0) as resp:  # noqa: S310
            frontend_reachable = resp.status < 500
        results.append(("Frontend reachable", frontend_reachable))
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        results.append(("Frontend reachable", None))  # not tested/unreachable -- informational

    _print_results(results)
    print()

    if not broker_connected:
        outcome = "UI_READY_BROKER_DISCONNECTED"
    elif frontend_reachable is False:
        outcome = "BACKEND_READY_FRONTEND_UNREACHABLE"
    else:
        outcome = "READY_FOR_LOCAL_UI_TEST"

    print(f"RESULT = {outcome}")
    return 0


def _print_results(results) -> None:
    for label, ok in results:
        if ok is True:
            tag = "PASS"
        elif ok is False:
            tag = "FAIL"
        else:
            tag = "WARN"
        print(f"[{tag}] {label}")


if __name__ == "__main__":
    sys.exit(main())
