"""C11 primary/H1 fallback, reused from the committed candidate audit adapter."""
import math
from typing import Any, Dict, Optional, Sequence

from fx_discovery import features as F
from host_evidence.symbol_metadata import load_record as load_host_symbol_metadata
from large_smc_core.target_model import TARGET_TIER_PRIMARY, select_target
from market_structure.config import load_market_structure_config
from market_structure.smc_adapter import candles_to_dataframe
from market_structure.tiers import (
    EXTERNAL_SWING_LENGTH,
    _build_tier,
    _equal_level_tolerance_points,
)
from strategy_engine.session import Candle

from . import contract as C

C11_PRIMARY = "PRIMARY_EXTERNAL_LIQUIDITY"
C11_H1_FALLBACK = "CONFIRMED_OPPOSING_H1_SWING"

def _external_tier(spec: dict, symbol: str, m5: Sequence[Candle]):
    """Build the existing EXTERNAL tier from closed candles and the spec's broker alias."""
    if len(m5) < 2 * EXTERNAL_SWING_LENGTH + 1:
        return None, "INSUFFICIENT_EXTERNAL_STRUCTURE_HISTORY"
    host_meta = load_host_symbol_metadata(symbol)
    if host_meta is None:
        return None, "C11_TICK_SIZE_METADATA_UNAVAILABLE"
    # The core structure tier's HH/HL tie tolerance is defined in captured tick-size
    # units. This value is C11 structure metadata only; it is never converted to pip_size.
    tick_size = float(host_meta["fields"]["trade_tick_size"])
    tolerance_price = _equal_level_tolerance_points() * tick_size
    config = load_market_structure_config()
    try:
        tier = _build_tier(
            candles_to_dataframe(m5),
            "EXTERNAL",
            EXTERNAL_SWING_LENGTH,
            config.close_break,
            tolerance_price,
        )
    except Exception as exc:  # candidate audit reports structure failure; no invented target
        return None, f"EXTERNAL_STRUCTURE_ERROR:{type(exc).__name__}"
    return tier, ""


def _h1_fallback_target(
    direction: Optional[str],
    anchor: Any,
    h1: Sequence[Candle],
) -> Dict[str, Any]:
    if direction not in ("LONG", "SHORT") or not isinstance(anchor, (int, float)) or not h1:
        return {
            "price": None,
            "tier": None,
            "source": None,
            "c11_source": None,
            "reason": "TARGET_INPUT_UNAVAILABLE",
        }

    last_closed_index = len(h1) - 1
    swings = F.swings(h1, C.SWING_K)
    candidates = []
    for swing in swings:
        if swing.known_at > last_closed_index:
            continue
        opposing = swing.kind == ("high" if direction == "LONG" else "low")
        beyond = swing.price > anchor if direction == "LONG" else swing.price < anchor
        if opposing and beyond:
            candidates.append(swing)
    if not candidates:
        return {
            "price": None,
            "tier": None,
            "source": None,
            "c11_source": None,
            "reason": "TARGET_UNAVAILABLE",
        }

    distances = [abs(swing.price - anchor) for swing in candidates]
    nearest_distance = min(distances)
    nearest = [
        swing
        for swing, distance in zip(candidates, distances)
        if math.isclose(distance, nearest_distance, rel_tol=0.0, abs_tol=1e-12)
    ]
    if len(nearest) != 1:
        return {
            "price": None,
            "tier": None,
            "source": None,
            "c11_source": None,
            "reason": "AMBIGUOUS_TARGET",
        }
    chosen = nearest[0]
    return {
        "price": float(chosen.price),
        "tier": "FALLBACK_H1_SWING",
        "source": "fx_discovery.features.swings",
        "c11_source": C11_H1_FALLBACK,
        "reason": "CONFIRMED_OPPOSING_H1_SWING",
        "swing_index": chosen.index,
        "known_at_index": chosen.known_at,
        "kind": chosen.kind,
    }


def _candidate_target(
    spec: dict,
    opportunity: dict,
    h1: Sequence[Candle],
    m5: Sequence[Candle],
) -> Dict[str, Any]:
    """Call core C11; accept only its primary external tier, then use causal H1 SW-A."""
    direction = opportunity.get("direction")
    anchor = opportunity.get("entry_reference")
    external, structure_note = _external_tier(spec, opportunity.get("symbol", ""), m5)
    core = select_target(
        direction=direction,
        anchor_price=float(anchor) if isinstance(anchor, (int, float)) else float("nan"),
        symbol=opportunity.get("symbol", ""),
        timeframe="M5",
        external_tier=external,
        m5_candles=m5,
    )
    core_details = {
        "core_selector_tier": core.target_tier,
        "core_selector_reason": core.reason,
        "core_selector_source": core.target_source,
        "core_selector_source_id": core.target_source_id,
        "structure_note": structure_note or None,
    }
    if (
        core.found
        and core.target_tier == TARGET_TIER_PRIMARY
        and isinstance(core.target_price, (int, float))
    ):
        return {
            "price": float(core.target_price),
            "tier": TARGET_TIER_PRIMARY,
            "source": core.target_source or "large_smc_core.target_model.select_target",
            "c11_source": C11_PRIMARY,
            "reason": core.reason,
            "source_id": core.target_source_id,
            "status_at_selection": core.target_status_at_selection,
            "evidence_timestamp": core.target_evidence_timestamp.isoformat()
            if core.target_evidence_timestamp
            else None,
            **core_details,
        }

    # The target model's FALLBACK_M5_SWING is deliberately ignored here. Candidate C11
    # requires the nearest confirmed opposing H1 swing when the primary is unavailable.
    fallback = _h1_fallback_target(direction, anchor, h1)
    fallback["core_selector_tier"] = core.target_tier
    fallback["core_selector_reason"] = core.reason
    fallback["core_selector_source"] = core.target_source
    fallback["core_selector_source_id"] = core.target_source_id
    fallback["structure_note"] = structure_note or None
    if fallback.get("price") is not None:
        fallback["reason"] = "PRIMARY_UNAVAILABLE_H1_FALLBACK"
        fallback["core_m5_fallback_ignored"] = core.target_tier == "FALLBACK_M5_SWING"
    return fallback
