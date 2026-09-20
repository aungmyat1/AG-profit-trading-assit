"""Small structural validator for the bounded agent-context manifest."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config" / "agent_context.json"


def main() -> int:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert data.get("schema") == "AG_AGENT_CONTEXT_V1"
    authorities = data["authorities"]
    for key in ("agent_instructions", "strategy_registry", "project_status", "trading_config"):
        assert (ROOT / authorities[key]).exists(), authorities[key]
    seen: set[str] = set()
    for name, stream in data["workstreams"].items():
        for field in ("authority", "status"):
            path = stream[field]
            assert (ROOT / path).exists(), f"{name}: {path}"
        for path in stream["read_first"]:
            assert (ROOT / path).exists(), f"{name}: {path}"
        key = stream["authority"]
        assert key not in seen, f"duplicate authority: {key}"
        seen.add(key)
    print(f"AG_AGENT_CONTEXT_V1 valid workstreams={len(data['workstreams'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
