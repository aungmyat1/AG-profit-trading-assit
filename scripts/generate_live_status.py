"""AG_PROJECT_LIVE_CONTROL_PLANE_V1 -- thin orchestration entrypoint.

Derives a LiveStatusSnapshot (src/validation_orchestrator/live_status.py), computes
its state fingerprint, renders it to Markdown (src/validation_orchestrator/render.py),
and writes docs/status/PROJECT_LIVE_STATUS.md only if the rendered content actually
changed (write-if-changed, keyed on the embedded fingerprint comment, so unrelated
`generated_at_utc` churn never produces a spurious diff).

Contains no evaluation logic of its own -- see the imported modules for the real
implementation. Read-only against strategy/evidence/git state; writes only the one
generated status file.

Usage:
    python scripts/generate_live_status.py            # write if changed
    python scripts/generate_live_status.py --check     # exit 1 if stale/missing, no write
    python scripts/generate_live_status.py --json       # print snapshot as JSON, no write
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from validation_orchestrator.live_status import compute_fingerprint, derive_snapshot  # noqa: E402
from validation_orchestrator.render import render_markdown  # noqa: E402

OUTPUT_PATH = REPO_ROOT / "docs" / "status" / "PROJECT_LIVE_STATUS.md"
_FINGERPRINT_RE = re.compile(r"<!-- LIVE_STATE_FINGERPRINT: ([0-9a-f]{64}) -->")


def _existing_fingerprint(path: Path) -> str:
    if not path.exists():
        return ""
    match = _FINGERPRINT_RE.search(path.read_text(encoding="utf-8"))
    return match.group(1) if match else ""


def freshness(path: Path, fingerprint: str) -> str:
    if not path.exists():
        return "LIVE_STATUS_MISSING"
    if _existing_fingerprint(path) != fingerprint:
        return "LIVE_STATUS_STALE"
    return "LIVE_STATUS_FRESH"


def _snapshot_to_jsonable(snapshot) -> dict:
    data = asdict(snapshot)
    return data


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 if stale/missing; never writes")
    parser.add_argument("--json", action="store_true", help="print the snapshot as JSON; never writes")
    args = parser.parse_args(argv)

    snapshot = derive_snapshot(repo_root=REPO_ROOT)
    fp = compute_fingerprint(snapshot)

    if args.json:
        print(json.dumps(_snapshot_to_jsonable(snapshot), indent=2, sort_keys=True, default=str))
        return 0

    state = freshness(OUTPUT_PATH, fp)

    if args.check:
        print(json.dumps({"state": state, "fingerprint": fp, "path": str(OUTPUT_PATH)}, indent=2))
        return 0 if state == "LIVE_STATUS_FRESH" else 1

    if state == "LIVE_STATUS_FRESH":
        print(json.dumps({"written": False, "state": state, "fingerprint": fp}, indent=2))
        return 0

    rendered = render_markdown(snapshot, fp)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(rendered, encoding="utf-8")
    print(json.dumps({"written": True, "state": state, "fingerprint": fp, "path": str(OUTPUT_PATH)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
