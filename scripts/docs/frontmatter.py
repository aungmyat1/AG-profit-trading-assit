"""Read/write YAML front-matter on Markdown files (DOCS-LIVE-2). Body bytes are never changed."""
from __future__ import annotations

from typing import Optional, Tuple

import yaml

KEYS = ("class", "state", "owner_reviewed", "review_by")


def split(text: str) -> Tuple[Optional[dict], str]:
    """(front-matter dict or None, body). Only a leading '---' block counts."""
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            data = yaml.safe_load(text[4:end]) or {}
            if isinstance(data, dict):
                return data, text[end + 5:]
    return None, text


def render(meta: dict) -> str:
    lines = ["---"]
    for k in KEYS:
        v = meta.get(k)
        lines.append(f"{k}: {'null' if v is None else v}")
    return "\n".join(lines) + "\n---\n"


def add(text: str, meta: dict) -> str:
    """Prepend front-matter. A file that already has one is returned unchanged (idempotent)."""
    existing, _ = split(text)
    if existing is not None:
        return text
    return render(meta) + text
