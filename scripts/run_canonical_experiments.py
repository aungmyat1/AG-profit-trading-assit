"""Run discovery-only exit experiments over a frozen canonical population.

This command intentionally has no holdout mode. A separate candidate-freeze and
one-time holdout command must be added before holdout results can be accessed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from canonical_experiments import ControlPolicy, TimeStopPolicy  # noqa: E402
from canonical_experiments.population import load_population  # noqa: E402
from canonical_experiments.runner import CanonicalExperimentRunner  # noqa: E402
from canonical_experiments.splits import chronological_split  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run discovery-only canonical exit experiments")
    parser.add_argument("population", help="write-once CANONICAL_POPULATION_V1 JSON")
    args = parser.parse_args()
    manifest, occurrences = load_population(args.population)
    split = chronological_split(occurrences)
    runner = CanonicalExperimentRunner(occurrences, split["discovery_ids"], "discovery")
    policies = [ControlPolicy(), *(TimeStopPolicy(minutes) for minutes in (30, 45, 60, 90, 120))]
    results = runner.run_suite(policies)
    print(json.dumps({
        "status": "DISCOVERY_ONLY",
        "strategy_id": manifest["strategy_id"],
        "strategy_version": manifest["strategy_version"],
        "population_hash": manifest["population_hash"],
        "discovery_count": len(split["discovery_ids"]),
        "holdout_count": len(split["holdout_ids"]),
        "holdout_access": "BLOCKED_UNTIL_CANDIDATE_FREEZE",
        "results": [{"policy_id": result.policy_id, "sample_size": result.sample_size, "net_expectancy_R": result.net_expectancy_R} for result in results],
    }, indent=2))


if __name__ == "__main__":
    main()