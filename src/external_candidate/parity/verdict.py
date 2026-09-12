"""Overall EXTERNAL_REPO_PARITY verdict (mission section 18).

Hard rule enforced here: aggregate economic agreement ALONE never yields PASS.
Two candidates can have identical aggregate expectancy while diverging on every
individual trade (offsetting errors) -- semantic (signal/trade) parity must be
available and clean before PASS is possible.
"""
from __future__ import annotations

from typing import Optional

from ._common import ComparisonResult
from .economic_comparator import EconomicParityResult

PARITY_PASS = "EXTERNAL_REPO_PARITY_PASS"
PARITY_FAIL = "EXTERNAL_REPO_PARITY_FAIL"
PARITY_NOT_PROVABLE = "NOT_PROVABLE_INCOMPLETE_EXTERNAL_EVIDENCE"


def compute_parity_verdict(
    signal_result: Optional[ComparisonResult],
    trade_result: Optional[ComparisonResult],
    economic_result: Optional[EconomicParityResult],
) -> str:
    semantic_result = trade_result if trade_result is not None else signal_result
    if semantic_result is None:
        # Economic-only agreement is never sufficient (mission section 18).
        return PARITY_NOT_PROVABLE

    if semantic_result.mismatched_cycles > 0:
        return PARITY_FAIL

    if semantic_result.total_cycles == 0:
        return PARITY_NOT_PROVABLE

    if economic_result is not None and not economic_result.matches:
        return PARITY_FAIL

    return PARITY_PASS
