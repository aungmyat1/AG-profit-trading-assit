"""Shared paths and LF normalization for generated documentation authorities."""
from __future__ import annotations

from pathlib import Path

GENERATED_FILES = (
    "PROJECT_STATUS.md",
    "docs/status/PROJECT_LIVE_STATUS.md",
    "status/facts.json",
    "docs/agents/CONTEXT_PACK.md",
)


def normalize_line_endings(path: Path) -> bool:
    """Write a generated text file with LF endings; return whether bytes changed."""
    original = path.read_bytes()
    normalized = original.replace(b"\r\n", b"\n")
    if normalized == original:
        return False
    path.write_bytes(normalized)
    return True


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    changed = [relative for relative in GENERATED_FILES if normalize_line_endings(root / relative)]
    print(f"GENERATED_FILES_LF_NORMALIZED={len(changed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
