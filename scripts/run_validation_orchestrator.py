"""AVO-WP1 -- narrow read-only validation orchestrator CLI.

python scripts/run_validation_orchestrator.py --status
python scripts/run_validation_orchestrator.py --strategy ST_LARGE_SMC_V1

Prints a strategy-neutral validation status snapshot derived from canonical
repository evidence (strategies/registry.yaml, config/governance/
strategy_lifecycle.yaml, and the existing validation_framework adapters via
api.strategy_service). Read-only: this script writes nothing and imports nothing
under src/execution/, src/mt5/, or src/authorization/. No Task Scheduler
integration, persistent ledger, agent dispatch, or execution command belongs in
this CLI -- see docs/validation/AG_AUTO_VALIDATION_ORCHESTRATOR_V1.md section 12.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from validation_orchestrator.status import (  # noqa: E402
    UnknownStrategyError,
    derive_all_status,
    derive_status,
)


def _to_dict(status) -> dict:
    return dataclasses.asdict(status)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="AG validation orchestrator -- read-only status (AVO-WP1)"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--status", action="store_true", help="print status for every registered strategy"
    )
    group.add_argument(
        "--strategy", metavar="STRATEGY_ID", help="print status for one strategy_id"
    )
    args = parser.parse_args(argv)

    if args.status:
        payload = [_to_dict(status) for status in derive_all_status()]
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    try:
        status = derive_status(args.strategy)
    except UnknownStrategyError as exc:
        print(
            json.dumps(
                {"error": "STRATEGY_NOT_REGISTERED", "strategy_id": exc.strategy_id},
                indent=2,
                sort_keys=True,
            )
        )
        return 2

    print(json.dumps(_to_dict(status), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
