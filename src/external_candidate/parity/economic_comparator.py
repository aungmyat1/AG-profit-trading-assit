"""External-candidate vs. canonical-repository-replay ECONOMIC parity (mission
section 16). Reuses `performance.models.TradeMetrics` and
`performance.calculator.compute_trade_metrics` verbatim -- this module computes no
metric itself, it only diffs two already-computed TradeMetrics instances.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from performance.models import NOT_EVALUATED, TradeMetrics

_R_TOLERANCE = 1e-6

_COMPARED_FIELDS = (
    "sample_size", "wins", "losses", "breakevens", "gross_total_R", "net_total_R",
    "gross_expectancy_R", "net_expectancy_R", "profit_factor", "max_drawdown_R",
)


@dataclass(frozen=True)
class EconomicParityResult:
    matched_fields: Tuple[str, ...]
    mismatched_fields: Tuple[str, ...]
    field_diffs: dict

    @property
    def matches(self) -> bool:
        return not self.mismatched_fields


def _field_matches(a, b) -> bool:
    if a is NOT_EVALUATED or b is NOT_EVALUATED:
        return a == b
    if isinstance(a, str) or isinstance(b, str):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= _R_TOLERANCE
    return a == b


def compare_economics(external: TradeMetrics, repo: TradeMetrics) -> EconomicParityResult:
    matched = []
    mismatched = []
    diffs = {}
    for field_name in _COMPARED_FIELDS:
        ext_val = getattr(external, field_name)
        repo_val = getattr(repo, field_name)
        if _field_matches(ext_val, repo_val):
            matched.append(field_name)
        else:
            mismatched.append(field_name)
            diffs[field_name] = {"external": ext_val, "repo": repo_val}
    return EconomicParityResult(tuple(matched), tuple(mismatched), diffs)
