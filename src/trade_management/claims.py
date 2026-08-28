"""Ticket ownership store: only a claimed ticket may receive automatic management
actions (spec section 7). Backed by a single JSON file (journal/claims.json by default)
-- one record per ticket, simplest reliable mechanism for V1, no database needed.

claim_position() also captures the immutable initial snapshot (spec section 8): reject
the claim outright (reason_code, no partial/garbage state written) if SL is missing,
R <= 0, direction is invalid, or price data is non-finite. Never invents a stop loss.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

from .models import Claim, NormalizedPosition

DEFAULT_CLAIMS_PATH = os.path.join("journal", "claims.json")

REASON_SL_MISSING = "SL_MISSING"
REASON_INVALID_R = "INVALID_R"
REASON_INVALID_DIRECTION = "INVALID_DIRECTION"
REASON_ALREADY_CLAIMED = "ALREADY_CLAIMED"


def _serialize(claim: Claim) -> dict:
    d = asdict(claim)
    d["claimed_at"] = claim.claimed_at.isoformat()
    return d


def _deserialize(d: dict) -> Claim:
    d = dict(d)
    d["claimed_at"] = datetime.fromisoformat(d["claimed_at"])
    return Claim(**d)


def load_claims(path: str = DEFAULT_CLAIMS_PATH) -> Dict[int, Claim]:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return {int(ticket): _deserialize(d) for ticket, d in raw.items()}


def _save_all(claims: Dict[int, Claim], path: str = DEFAULT_CLAIMS_PATH) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    payload = {str(ticket): _serialize(c) for ticket, c in claims.items()}
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
    os.replace(tmp_path, path)


def get_claim(ticket: int, path: str = DEFAULT_CLAIMS_PATH) -> Optional[Claim]:
    return load_claims(path).get(ticket)


def compute_initial_r_distance(direction: str, entry_price: float, initial_sl: float) -> Optional[float]:
    if direction == "BUY":
        distance = entry_price - initial_sl
    elif direction == "SELL":
        distance = initial_sl - entry_price
    else:
        return None
    if not math.isfinite(distance):
        return None
    return distance


def claim_position(
    position: NormalizedPosition,
    tp1: Optional[float],
    final_r_multiple: float,
    strategy: Optional[str] = None,
    setup: Optional[str] = None,
    path: str = DEFAULT_CLAIMS_PATH,
    allow_reclaim: bool = False,
) -> Tuple[Optional[Claim], Optional[str]]:
    """Returns (Claim, None) on success, (None, reason_code) on rejection. Fail-closed:
    never writes a claim on any ambiguous input (spec section 8/39)."""
    claims = load_claims(path)
    if position.ticket in claims and not allow_reclaim:
        return None, REASON_ALREADY_CLAIMED

    if position.direction not in ("BUY", "SELL"):
        return None, REASON_INVALID_DIRECTION

    if position.sl is None or not math.isfinite(position.sl):
        return None, REASON_SL_MISSING

    r_distance = compute_initial_r_distance(position.direction, position.entry_price, position.sl)
    if r_distance is None or r_distance <= 0:
        return None, REASON_INVALID_R

    claim = Claim(
        ticket=position.ticket,
        symbol=position.symbol,
        direction=position.direction,
        entry_price=position.entry_price,
        initial_sl=position.sl,
        initial_volume=position.volume_initial,
        initial_r_distance=r_distance,
        tp1=tp1,
        final_r_multiple=final_r_multiple,
        strategy=strategy,
        setup=setup,
        claimed_at=datetime.now(timezone.utc),
    )
    claims[position.ticket] = claim
    _save_all(claims, path)
    return claim, None
