#!/usr/bin/env python3
"""Lightweight repository documentation integrity checker.

Checks:
1. Relative Markdown link destinations exist.
2. Primary docs/<domain>/README.md indexes are discoverable from docs/README.md.

This checker validates documentation structure only. It grants no runtime,
strategy, proposal, Demo, Live, or execution authority.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
DOCS_ROOT = ROOT / "docs"
DOCS_INDEX = DOCS_ROOT / "README.md"

LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "tel:")


def markdown_files() -> list[Path]:
    files = [p for p in ROOT.rglob("*.md") if ".git" not in p.parts]
    return sorted(files)


def normalize_target(raw: str) -> str | None:
    target = raw.strip()
    if not target or target.startswith("#") or target.startswith(EXTERNAL_PREFIXES):
        return None

    # Markdown permits optional titles after a whitespace-separated destination.
    if target.startswith("<") and ">" in target:
        target = target[1 : target.index(">")]
    else:
        target = target.split()[0]

    target = unquote(target.split("#", 1)[0].split("?", 1)[0]).strip()
    return target or None


def broken_relative_links() -> list[tuple[Path, str]]:
    broken: list[tuple[Path, str]] = []
    for source in markdown_files():
        try:
            text = source.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for match in LINK_RE.finditer(text):
            target = normalize_target(match.group(1))
            if target is None:
                continue
            destination = (source.parent / target).resolve()
            try:
                destination.relative_to(ROOT.resolve())
            except ValueError:
                broken.append((source.relative_to(ROOT), match.group(1)))
                continue
            if not destination.exists():
                broken.append((source.relative_to(ROOT), match.group(1)))
    return broken


def undiscoverable_domains() -> list[Path]:
    if not DOCS_INDEX.exists():
        return [DOCS_INDEX.relative_to(ROOT)]

    index_text = DOCS_INDEX.read_text(encoding="utf-8")
    missing: list[Path] = []
    for child in sorted(DOCS_ROOT.iterdir()):
        domain_index = child / "README.md"
        if not child.is_dir() or not domain_index.is_file():
            continue
        rel = domain_index.relative_to(DOCS_ROOT).as_posix()
        # Accept either direct README link or a link to the domain directory.
        domain_prefix = f"{child.name}/"
        if rel not in index_text and domain_prefix not in index_text:
            missing.append(domain_index.relative_to(ROOT))
    return missing


def main() -> int:
    broken = broken_relative_links()
    undiscoverable = undiscoverable_domains()

    if broken:
        print("BROKEN_RELATIVE_LINKS:")
        for source, target in broken:
            print(f"  {source}: {target}")

    if undiscoverable:
        print("UNDISCOVERABLE_PRIMARY_DOC_DOMAINS:")
        for path in undiscoverable:
            print(f"  {path}")

    if broken or undiscoverable:
        print("DOCS_LINK_CHECK = FAIL")
        print(f"BROKEN_RELATIVE_LINKS = {len(broken)}")
        print(f"UNDISCOVERABLE_PRIMARY_DOC_DOMAINS = {len(undiscoverable)}")
        return 1

    print("DOCS_LINK_CHECK = PASS")
    print("BROKEN_RELATIVE_LINKS = 0")
    print("UNDISCOVERABLE_PRIMARY_DOC_DOMAINS = 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
