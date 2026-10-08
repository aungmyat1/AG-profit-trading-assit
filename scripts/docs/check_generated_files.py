#!/usr/bin/env python3
"""Classify generated-file drift, allowing fingerprint-only changes as warnings."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from generated_files import GENERATED_FILES  # noqa: E402

FINGERPRINT = re.compile(r"(?m)^inputs_sha256: `[0-9a-f]{64}`\.?$")


def normalized(path: str, content: str) -> object:
    if path.endswith(".json"):
        value = json.loads(content)
        if isinstance(value, dict):
            value.pop("inputs_sha256", None)
        return value
    return FINGERPRINT.sub("inputs_sha256: <fingerprint>", content)


def committed_content(path: str, revision: str = "HEAD") -> str:
    result = subprocess.run(
        ["git", "show", f"{revision}:{path}"], cwd=ROOT,
        capture_output=True, text=True, encoding="utf-8",
    )
    if result.returncode:
        raise RuntimeError(f"cannot read {revision}:{path}: {result.stderr.strip()}")
    return result.stdout


def classify(path: str, committed: str, generated: str) -> str:
    if committed == generated:
        return "FRESH"
    if normalized(path, committed) == normalized(path, generated):
        return "FINGERPRINT_ONLY"
    return "CONTENT_STALE"


def main() -> int:
    warnings = []
    failures = []
    for relative in GENERATED_FILES:
        try:
            expected = committed_content(relative)
            actual = (ROOT / relative).read_text(encoding="utf-8")
            result = classify(relative, expected, actual)
        except (OSError, ValueError, RuntimeError) as exc:
            failures.append(f"{relative}: {exc}")
            continue
        print(f"{relative}: {result}")
        if result == "FINGERPRINT_ONLY":
            warnings.append(relative)
        elif result == "CONTENT_STALE":
            failures.append(f"{relative}: generated content differs")
    for path in warnings:
        print(f"::warning::generated input fingerprint changed in {path}; content is unchanged")
    for failure in failures:
        print(f"::error::{failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
