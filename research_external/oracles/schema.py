"""Shared classified-disagreement record schema for research oracle lanes."""
from __future__ import annotations

from typing import Any, Literal, TypedDict


class Disagreement(TypedDict):
    schema_version: Literal["AGP_ORACLE_DISAGREEMENT_V1"]
    lane: str
    category: str
    subject: str
    expected: Any
    observed: Any
    bar_index: int | None
    details: dict[str, Any]


def disagreement(lane: str, category: str, subject: str, expected: Any, observed: Any, *,
                 bar_index: int | None = None, details: dict[str, Any] | None = None) -> Disagreement:
    return {"schema_version": "AGP_ORACLE_DISAGREEMENT_V1", "lane": lane,
            "category": category, "subject": subject, "expected": expected,
            "observed": observed, "bar_index": bar_index, "details": details or {}}
