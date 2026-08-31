"""AG_POST_ASIAN_LONDON_PILOT_V1 CLI entrypoint.

Read-only, PROPOSAL_ONLY: never calls execution.executor / execution.mt5_gateway /
order_check / order_send. See src/post_asian_pilot/pipeline.py for the actual cycle logic
-- this script only wires MT5 connect/shutdown and report output around it, mirroring
scripts/run_daytrading_runtime.py's own CLI shape (--once/--watch/--status).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import mt5.connection as mt5_connection  # noqa: E402
from post_asian_pilot.pipeline import run_pilot_cycle  # noqa: E402
from post_asian_pilot.report import cycle_to_dict, human_readable_report  # noqa: E402


def _run_once(as_json: bool) -> None:
    mt5_connection.connect()
    try:
        result = run_pilot_cycle()
    finally:
        mt5_connection.shutdown()
    if as_json:
        print(json.dumps(cycle_to_dict(result), indent=2, default=str))
    else:
        print(human_readable_report(result))


def main() -> None:
    parser = argparse.ArgumentParser(description="AG_POST_ASIAN_LONDON_PILOT_V1 (read-only, PROPOSAL_ONLY)")
    parser.add_argument("--once", action="store_true", help="run a single evaluation cycle")
    parser.add_argument("--watch", action="store_true", help="loop, evaluating every --interval seconds")
    parser.add_argument("--status", action="store_true", help="alias for --once with a JSON report")
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--json", action="store_true", help="emit JSON instead of the human-readable report")
    args = parser.parse_args()

    as_json = args.json or args.status

    if args.watch:
        while True:
            _run_once(as_json)
            time.sleep(args.interval)
    else:
        _run_once(as_json)


if __name__ == "__main__":
    main()
