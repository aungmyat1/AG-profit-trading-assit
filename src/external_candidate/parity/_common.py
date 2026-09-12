"""Shared comparison engine for signal_comparator.py / trade_comparator.py. Not a
public module on its own -- both callers need the identical alignment/tolerance
logic, and mission section 15 explicitly forbids two competing definitions of
"close enough."
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence, Tuple

from .divergence import DivergenceReport, build_divergence_report

# Deliberately tight -- mission section 15: "Do not hide genuine semantic mismatches
# behind wide numerical tolerances." This only absorbs float round-trip noise, not
# real broker-precision differences.
PRICE_TOLERANCE = 1e-9
R_TOLERANCE = 1e-6


@dataclass(frozen=True)
class ComparisonResult:
    total_cycles: int
    matched_cycles: int
    mismatched_cycles: int
    unmatched_external_keys: Tuple[str, ...]
    unmatched_repo_keys: Tuple[str, ...]
    first_mismatch: Optional[DivergenceReport]


def _values_match(a: Any, b: Any, tolerance: float) -> bool:
    if a is None or b is None:
        return a is b  # both-None matches; either-None-alone does not
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= tolerance
    return a == b


def compare_records(
    external: Sequence[Mapping[str, Any]],
    repo: Sequence[Mapping[str, Any]],
    *,
    key_field: str,
    compare_fields: Sequence[str],
    numeric_fields: Sequence[str],
    candidate_fingerprint: str,
    dataset_fingerprint: str,
) -> ComparisonResult:
    external_by_key = {str(r[key_field]): r for r in external if r.get(key_field) is not None}
    repo_by_key = {str(r[key_field]): r for r in repo if r.get(key_field) is not None}

    common_keys = sorted(set(external_by_key) & set(repo_by_key))
    unmatched_external = tuple(sorted(set(external_by_key) - set(repo_by_key)))
    unmatched_repo = tuple(sorted(set(repo_by_key) - set(external_by_key)))

    matched = 0
    mismatched = 0
    first_mismatch: Optional[DivergenceReport] = None

    for key in common_keys:
        ext_row = external_by_key[key]
        repo_row = repo_by_key[key]
        row_mismatch = False
        for field_name in compare_fields:
            ext_val = ext_row.get(field_name)
            repo_val = repo_row.get(field_name)
            tolerance = R_TOLERANCE if field_name.endswith("_R") else (
                PRICE_TOLERANCE if field_name in numeric_fields else 0.0
            )
            if not _values_match(ext_val, repo_val, tolerance):
                row_mismatch = True
                if first_mismatch is None:
                    first_mismatch = build_divergence_report(
                        field_name, ext_val, repo_val,
                        candidate_fingerprint=candidate_fingerprint,
                        dataset_fingerprint=dataset_fingerprint,
                        key=key,
                    )
        if row_mismatch:
            mismatched += 1
        else:
            matched += 1

    total = len(common_keys) + len(unmatched_external) + len(unmatched_repo)
    return ComparisonResult(
        total_cycles=total,
        matched_cycles=matched,
        mismatched_cycles=mismatched + len(unmatched_external) + len(unmatched_repo),
        unmatched_external_keys=unmatched_external,
        unmatched_repo_keys=unmatched_repo,
        first_mismatch=first_mismatch,
    )
