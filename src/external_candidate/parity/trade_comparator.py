"""External-candidate vs. canonical-repository-replay TRADE parity (mission
section 15). Compares resolved-trade-level facts. Accepts plain mappings (e.g.
`dataclasses.asdict(ExternalTradeRecord(...))` on one side and an equivalent repo
trade mapping on the other) so it does not force a shared trade class between the
two sources -- only a shared field vocabulary.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from ._common import ComparisonResult, compare_records

TRADE_COMPARE_FIELDS = (
    "direction", "entry", "stop_loss", "take_profit", "exit_price", "outcome", "gross_R", "net_R",
)
TRADE_NUMERIC_FIELDS = ("entry", "stop_loss", "take_profit", "exit_price")


def compare_trades(
    external_trades: Sequence[Mapping[str, Any]],
    repo_trades: Sequence[Mapping[str, Any]],
    *,
    key_field: str = "cycle",
    candidate_fingerprint: str,
    dataset_fingerprint: str,
) -> ComparisonResult:
    return compare_records(
        external_trades, repo_trades,
        key_field=key_field,
        compare_fields=TRADE_COMPARE_FIELDS,
        numeric_fields=TRADE_NUMERIC_FIELDS,
        candidate_fingerprint=candidate_fingerprint,
        dataset_fingerprint=dataset_fingerprint,
    )
