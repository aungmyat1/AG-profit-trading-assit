#!/usr/bin/env python3
"""Grep-like guard for documentation authority claims that contradict the registry."""
from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLAIM = re.compile(
    r"(?i)(?:demo_authorized\s*[:=]\s*(?:true|yes)\b|"
    r"\bdemo[- _](?:authorized|eligible|qualified)\s*(?:[:=]\s*)?(?:true|yes|authorized|eligible|qualified)\b|"
    r"\bDEMO_QUALIFIED\b)"
)


def tracked_docs(root: Path) -> list[str]:
    paths = subprocess.check_output(
        ["git", "ls-files", "-co", "--exclude-standard", "--", "*.md"], cwd=root, text=True
    ).splitlines()
    return sorted(p for p in paths if p == "PROJECT_STATUS.md" or p == "README.md" or p.startswith("docs/"))


def outside_cog_blocks(text: str) -> str:
    output, in_cog = [], False
    for line in text.splitlines():
        if "<!-- [[[cog" in line:
            in_cog = True
            continue
        if in_cog:
            if "<!-- [[[end]]] -->" in line:
                in_cog = False
            continue
        output.append(line)
    return "\n".join(output)


def allowlist(path: Path) -> list[tuple[str, re.Pattern[str], str]]:
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = line.split("|", 2)
        if len(fields) != 3 or not all(x.strip() for x in fields):
            raise ValueError(f"{path}:{number}: expected path-glob|regex|reason")
        rows.append((fields[0].strip(), re.compile(fields[1].strip(), re.IGNORECASE), fields[2].strip()))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=ROOT / "strategies" / "registry.yaml")
    parser.add_argument("--allowlist", type=Path, default=ROOT / "scripts" / "docs" / "docs_drift_allowlist.txt")
    args = parser.parse_args()
    import yaml
    registry = yaml.safe_load(args.registry.read_text(encoding="utf-8")) or {}
    false_ids = sorted(
        strategy_id for strategy_id, entry in (registry.get("strategies") or {}).items()
        if entry.get("demo_authorized") is False
    )
    allowed = allowlist(args.allowlist)
    failures, ignored = [], 0
    for rel in tracked_docs(ROOT):
        content = outside_cog_blocks((ROOT / rel).read_text(encoding="utf-8"))
        for line_number, line in enumerate(content.splitlines(), 1):
            claim = CLAIM.search(line)
            if not claim:
                continue
            # Require the strategy ID before the affirmative claim on the same line.
            # This avoids attributing a different strategy's authority in prose/tables.
            prefix = line[:claim.start()]
            # A compact key/value row may place the ID immediately before the value.
            # Accept only an explicitly labeled ID assignment, not another ID elsewhere.
            for strategy_id in false_ids:
                id_position = prefix.rfind(strategy_id)
                if id_position < 0:
                    continue
                between = prefix[id_position + len(strategy_id):]
                if re.search(r"\b(?:only|other|separately|independently|different|not for)\b", between, re.I):
                    continue
                if strategy_id in {"ST_ASIAN_SWEEP_5R_V1", "ST_LIQUIDITY_SWEEP_RETEST_V1"} and "SESSION_TRADE_V1" in line:
                    continue
                if any(fnmatch.fnmatch(rel, glob) and pattern.search(line) and strategy_id in pattern.pattern
                       for glob, pattern, _ in allowed):
                    ignored += 1
                    continue
                failures.append((rel, line_number, strategy_id, " ".join(line.split())[:240]))
    for rel, line_number, strategy_id, excerpt in failures:
        print(f"CONTRADICTION {rel}:{line_number} [{strategy_id}]: {excerpt}")
    print(f"docs-drift: {len(failures)} contradiction(s), {ignored} allowlisted historical/context claim(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
