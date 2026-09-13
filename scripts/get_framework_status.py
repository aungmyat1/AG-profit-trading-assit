"""Print a compact, evidence-linked summary for agent workflows."""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = REPO_ROOT / "strategies" / "registry.yaml"
PROJECT_STATUS_PATH = REPO_ROOT / "PROJECT_STATUS.md"
BTC_CONTRACT_PATH = REPO_ROOT / "docs" / "status" / "AG_BTC_DAILY_OBSERVATION_CONTRACT_V1.md"


def _registry_summary() -> dict[str, dict[str, object]]:
    registry = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    return {
        strategy_id: {
            key: entry.get(key)
            for key in ("registered", "active", "research", "demo_authorized", "live_authorized")
        }
        for strategy_id, entry in registry.get("strategies", {}).items()
    }


def _gate_summary() -> dict[str, str]:
    text = PROJECT_STATUS_PATH.read_text(encoding="utf-8")
    gates: dict[str, str] = {}
    gate_pattern = r"\|\s*(R\d+(?:[-\u2013]R\d+)?(?:\s+[^|]+)?)\s*\|\s*`([^`]+)`\s*\|"
    for match in re.finditer(gate_pattern, text):
        gates[match.group(1).strip()] = match.group(2)
    return gates


def _btc_status() -> str:
    if not BTC_CONTRACT_PATH.exists():
        return "NOT_FOUND"
    excerpt = BTC_CONTRACT_PATH.read_text(encoding="utf-8")[:2000]
    if "DATA_ERROR" in excerpt or "403" in excerpt:
        return "DATA_ERROR"
    return "PRESENT"


def build_summary() -> dict[str, object]:
    return {
        "project_status": {
            "gates": _gate_summary(),
            "source": "PROJECT_STATUS.md",
        },
        "strategies": _registry_summary(),
        "btc_observation_contract": {
            "status": _btc_status(),
            "source": "docs/status/AG_BTC_DAILY_OBSERVATION_CONTRACT_V1.md",
        },
    }


if __name__ == "__main__":
    print("=== AG FRAMEWORK STATUS (COMPACT) ===")
    print(json.dumps(build_summary(), sort_keys=True, separators=(",", ":")))
