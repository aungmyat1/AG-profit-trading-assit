"""AG_R6_GOVERNANCE_BASELINE_FREEZE_V1 -- thin orchestration entrypoint for
src/validation_framework/ledger.py.

Why this script exists: the R5 readiness audit (docs/status/AG_R5_EVIDENCE_PIPELINE_STATUS.md)
found that build_ledger()/write_snapshot() (src/validation_framework/ledger.py) and the
three per-strategy adapters (validation_framework/adapters/{fx,btc,large_smc}_adapter.py)
were fully built and tested (tests/test_validation_framework.py), but had NO production
CLI entrypoint -- their only callers were the module itself and the test suite. This
script adds exactly that missing orchestration, nothing else: it calls the three
existing adapters, the existing build_ledger()/write_snapshot() functions, and writes one
immutable snapshot under artifacts/validation_ledger/ using this repository's actual
current git HEAD. It contains no evaluation logic, no new performance model, no new
ledger format -- see each imported function's own module for the real implementation.

Read-only against strategy/evidence files; writes only a new, uniquely-named snapshot
file (write_snapshot() never overwrites an existing one).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from validation_framework.adapters.btc_adapter import build_btc_record  # noqa: E402
from validation_framework.adapters.fx_adapter import build_fx_record  # noqa: E402
from validation_framework.adapters.large_smc_adapter import build_large_smc_record  # noqa: E402
from validation_framework.ledger import build_ledger, serialize_record, write_snapshot  # noqa: E402


def _git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT).decode().strip()


def generate() -> str:
    records = [
        build_fx_record(repo_root=str(REPO_ROOT)),
        build_btc_record(repo_root=str(REPO_ROOT)),
        build_large_smc_record(repo_root=str(REPO_ROOT)),
    ]
    ledger = build_ledger(records, repository_head=_git_head())
    return write_snapshot(ledger)


def main() -> int:
    path = generate()
    print(json.dumps({"snapshot_path": path}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
