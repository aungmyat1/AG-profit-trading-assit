"""AG_FX_SESSION_DAYTRADE_EURUSD_V1 CLI entrypoint.

Read-only, PROPOSAL_ONLY: never calls execution.executor / execution.mt5_gateway, and
never reaches a broker order-send or order-check call. This wrapper forks no strategy,
sizing, or journal logic of its own -- it only selects one of this book's two frozen
pilot overlays and delegates to the same src/post_asian_pilot/* functions
scripts/run_post_asian_pilot.py already uses (run_preflight, run_pilot_cycle,
cycle_to_dict, human_readable_report).

Book: AG_FX_SESSION_DAYTRADE_EURUSD_V1
Strategy: ST_ASIAN_SWEEP_5R_V1@1.1.1 (frozen -- see strategies/ST_ASIAN_SWEEP_5R_V1.yaml)
Cycles: ASIAN_LONDON (config/pilot/AG_FX_SESSION_DAYTRADE_EURUSD_ASIAN_LONDON_V1.yaml)
        LONDON_NEWYORK (config/pilot/AG_FX_SESSION_DAYTRADE_EURUSD_LONDON_NEWYORK_V1.yaml)
Cap: 1 new slot/day per cycle, 2/day maximum for the book.

--preflight            operational readiness only. Never runs a strategy cycle, never
                        claims a slot, never sends an order.
--once --cycle X        run a single evaluation cycle for cycle X (ASIAN_LONDON or
                        LONDON_NEWYORK). --cycle BOTH is rejected here -- a --once call
                        must resolve to exactly one temporal cycle boundary, never both
                        (a caller wanting both runs two separate --once invocations, at
                        each cycle's own valid time).
--status --cycle X|BOTH one operational cycle per selected pilot, forced JSON. BOTH is
                        allowed here (and for --preflight) because it is read-only and
                        never claims a slot or writes a decision-changing state -- it
                        loops both overlays independently and never merges their state.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import mt5.connection as mt5_connection  # noqa: E402
from post_asian_pilot.pipeline import run_pilot_cycle  # noqa: E402
from post_asian_pilot.preflight import run_preflight  # noqa: E402
from post_asian_pilot.report import cycle_to_dict, human_readable_report  # noqa: E402

_CYCLE_PATHS = {
    "ASIAN_LONDON": "config/pilot/AG_FX_SESSION_DAYTRADE_EURUSD_ASIAN_LONDON_V1.yaml",
    "LONDON_NEWYORK": "config/pilot/AG_FX_SESSION_DAYTRADE_EURUSD_LONDON_NEWYORK_V1.yaml",
}


def _resolve_cycle_paths(cycle: str) -> dict:
    if cycle == "BOTH":
        return dict(_CYCLE_PATHS)
    return {cycle: _CYCLE_PATHS[cycle]}


def _run_preflight(as_json: bool, cycle: str) -> int:
    exit_code = 0
    for cycle_name, pilot_path in _resolve_cycle_paths(cycle).items():
        result = run_preflight(pilot_path=pilot_path)
        payload = {
            "cycle": cycle_name, "release_id": result.release_id,
            "release_fingerprint": result.release_fingerprint,
            "strategy_id": result.strategy_id, "strategy_version": result.strategy_version,
            "account_mode": result.account_mode, "trading_date": result.trading_date.isoformat()
            if result.trading_date else None,
            "daily_slot_state": result.daily_slot_state, "open_positions": result.open_positions,
            "checks": [{"name": n, "result": r} for n, r in result.checks],
            "pilot_status": result.pilot_status, "first_block_reason": result.first_block_reason,
        }
        if as_json:
            print(json.dumps(payload, indent=2, default=str))
        else:
            print(f"AG_FX_SESSION_DAYTRADE_EURUSD_V1_PREFLIGHT [{cycle_name}]")
            for name, value in payload.items():
                if name == "checks":
                    continue
                print(f"{name} = {value}")
            for name, r in result.checks:
                print(f"  check[{name}] = {r}")
        if result.pilot_status == "PILOT_STARTUP_BLOCKED":
            exit_code = 1
    return exit_code


def _execute_cycle(pilot_path: str):
    mt5_connection.connect()
    try:
        return run_pilot_cycle(pilot_path)
    finally:
        mt5_connection.shutdown()


def _run_once(as_json: bool, cycle: str) -> int:
    if cycle == "BOTH":
        print("--once does not accept --cycle BOTH: each call must resolve to exactly "
              "one temporal cycle boundary. Run --once --cycle ASIAN_LONDON and "
              "--once --cycle LONDON_NEWYORK separately.", file=sys.stderr)
        return 2
    pilot_path = _CYCLE_PATHS[cycle]
    result = _execute_cycle(pilot_path)
    if as_json:
        print(json.dumps(cycle_to_dict(result, None, None, None), indent=2, default=str))
    else:
        print(human_readable_report(result, None, None, None))
    return 0


def _run_status(as_json: bool, cycle: str) -> int:
    for cycle_name, pilot_path in _resolve_cycle_paths(cycle).items():
        result = _execute_cycle(pilot_path)
        payload = cycle_to_dict(result, None, None, None)
        payload["cycle"] = cycle_name
        print(json.dumps(payload, indent=2, default=str))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AG_FX_SESSION_DAYTRADE_EURUSD_V1 (read-only, PROPOSAL_ONLY)")
    parser.add_argument("--preflight", action="store_true", help="operational readiness only")
    parser.add_argument("--once", action="store_true", help="run a single evaluation cycle")
    parser.add_argument("--status", action="store_true", help="one operational cycle, JSON report")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of the human-readable report")
    parser.add_argument("--cycle", choices=["ASIAN_LONDON", "LONDON_NEWYORK", "BOTH"], default=None,
                         help="which book cycle to run/check")
    args = parser.parse_args()

    if not args.cycle:
        parser.error("--cycle is required (ASIAN_LONDON, LONDON_NEWYORK, or BOTH)")

    as_json = args.json or args.status

    if args.preflight:
        sys.exit(_run_preflight(as_json, args.cycle))
    elif args.status:
        sys.exit(_run_status(as_json, args.cycle))
    else:
        sys.exit(_run_once(as_json, args.cycle))


if __name__ == "__main__":
    main()
