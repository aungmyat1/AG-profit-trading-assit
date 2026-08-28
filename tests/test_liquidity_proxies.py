"""Tests for liquidity.proxies: retail liquidity proxy relabeling (VALIDATED) and
engineered liquidity candidate evidence scoring (always RESEARCH_ONLY). Pure functions,
no MT5 connection."""
from __future__ import annotations

from datetime import datetime, timezone

from liquidity.models import LiquidityLevel, LiquiditySide, LiquidityStatus
from liquidity.proxies import engineered_liquidity_candidates, retail_liquidity_proxies

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
TOLERANCE = 5 * 0.00001


def _level(source, side, price, status=LiquidityStatus.UNSWEPT) -> LiquidityLevel:
    return LiquidityLevel(symbol="EURUSD", timeframe="H1", side=side, source=source, price=price,
                           origin_time=NOW, status=status)


def test_retail_proxy_includes_known_objective_sources():
    levels = [
        _level("EQUAL_HIGHS", LiquiditySide.BUY_SIDE, 1.1100),
        _level("PDH", LiquiditySide.BUY_SIDE, 1.1150),
    ]
    proxies = retail_liquidity_proxies(levels)
    assert len(proxies) == 2
    assert all(p.classification == "VALIDATED" for p in proxies)


def test_retail_proxy_excludes_unknown_source():
    levels = [_level("SOMETHING_UNDEFINED", LiquiditySide.BUY_SIDE, 1.1100)]
    assert retail_liquidity_proxies(levels) == ()


def test_engineered_candidate_all_evidence_present():
    levels = [
        _level("EQUAL_HIGHS", LiquiditySide.BUY_SIDE, 1.1100, status=LiquidityStatus.SWEPT),
        _level("SWING_HIGH", LiquiditySide.BUY_SIDE, 1.1100 + TOLERANCE / 2),  # repeated (within tolerance)
        _level("PDH", LiquiditySide.BUY_SIDE, 1.1200, status=LiquidityStatus.UNSWEPT),  # external objective, still unswept
    ]
    candidates = engineered_liquidity_candidates(levels, TOLERANCE)
    swept_candidate = next(c for c in candidates if c.level.source == "EQUAL_HIGHS")
    assert swept_candidate.evidence_repeated_internal_levels is True
    assert swept_candidate.evidence_external_objective_present is True
    assert swept_candidate.evidence_inducement_pattern is True
    assert swept_candidate.evidence_score == 3
    assert swept_candidate.status == "RESEARCH_ONLY"


def test_engineered_candidate_no_evidence():
    levels = [_level("EQUAL_HIGHS", LiquiditySide.BUY_SIDE, 1.1100, status=LiquidityStatus.UNSWEPT)]
    candidates = engineered_liquidity_candidates(levels, TOLERANCE)
    assert len(candidates) == 1
    assert candidates[0].evidence_score == 0
    assert candidates[0].status == "RESEARCH_ONLY"


def test_engineered_candidate_never_claims_certainty():
    # Even a maximal score must stay RESEARCH_ONLY -- spec section 33/46.
    levels = [
        _level("EQUAL_HIGHS", LiquiditySide.SELL_SIDE, 1.0900, status=LiquidityStatus.CONSUMED),
        _level("EQUAL_LOWS", LiquiditySide.SELL_SIDE, 1.0900 - TOLERANCE / 2),
        _level("PDL", LiquiditySide.SELL_SIDE, 1.0800, status=LiquidityStatus.UNSWEPT),
    ]
    candidates = engineered_liquidity_candidates(levels, TOLERANCE)
    assert all(c.status == "RESEARCH_ONLY" for c in candidates)
    assert all(0 <= c.evidence_score <= 3 for c in candidates)
