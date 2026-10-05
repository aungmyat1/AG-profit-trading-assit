"""Read-only API projection of durable crypto OpportunityCandidates."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Optional

from crypto_opportunity_scanner.constants import DEFAULT_STORE_PATH, STRATEGY_ID
from opportunity.candidate_store import CandidateStore


def list_crypto_opportunities(
    symbol: Optional[str] = None,
    *,
    store_path: str = DEFAULT_STORE_PATH,
    limit: int = 50,
) -> list[dict[str, Any]]:
    if limit < 1 or limit > 200:
        raise ValueError("limit must be between 1 and 200")
    normalized_symbol = symbol.upper() if symbol else None
    candidates = [
        candidate for candidate in CandidateStore(store_path).all_candidates()
        if candidate.strategy_id == STRATEGY_ID
        and candidate.market == "CRYPTO"
        and (normalized_symbol is None or candidate.symbol == normalized_symbol)
    ]
    candidates.sort(key=lambda item: (item.last_evaluated_at, item.candidate_id), reverse=True)
    result = []
    for candidate in candidates[:limit]:
        row = asdict(candidate)
        for name in ("detected_at", "last_evaluated_at", "expires_at"):
            value = getattr(candidate, name)
            row[name] = value.isoformat() if value is not None else None
        return_geometry = row.get("geometry")
        if return_geometry is not None:
            return_geometry["targets"] = list(return_geometry.get("targets", ()))
        result.append(row)
    return result
