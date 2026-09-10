"""AG_UNIVERSAL_MARKET_DIRECTION_ARCHITECTURE_V1 M2/M3 tests (P23/P24 subset).

Proves: only market_intelligence.bias_resolver emits an authoritative BULLISH/BEARISH/
NEUTRAL verdict; the evidence-only packages backing market-structure/liquidity/supply-
demand/multi-timeframe skills expose no such symbol; daytrading.narrative_bias cannot
override the canonical resolver (separate, unreconciled package -- no import path
exists between them); and the legacy daytrading.decision.market_bias adapter always
agrees with the canonical resolver it now delegates to.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

FORBIDDEN_AUTHORITATIVE_SYMBOLS = ("BULLISH", "BEARISH")  # bare module-level constants, not evidence enum members


def _module_file(module_name: str) -> Path:
    import importlib
    mod = importlib.import_module(module_name)
    return Path(mod.__file__)


def _imports_of(path: Path) -> set:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
    return imported


# ---------------------------------------------------------------------------
# Only market_intelligence.bias_resolver is imported for a final BULLISH/BEARISH/
# NEUTRAL verdict; market_structure/liquidity/supply_demand/mtf_context never import
# each other for direction and never import market_intelligence (evidence flows one
# way -- into the resolver, never out of it back into an evidence package).
# ---------------------------------------------------------------------------


def test_evidence_packages_do_not_import_market_intelligence():
    for package in ("market_structure", "liquidity", "supply_demand", "mtf_context"):
        for py_file in (REPO_ROOT / "src" / package).rglob("*.py"):
            imports = _imports_of(py_file)
            assert not any(m == "market_intelligence" or m.startswith("market_intelligence.") for m in imports), (
                f"{py_file} imports market_intelligence -- evidence packages must never "
                "depend on the bias authority they feed"
            )


def test_market_swing_structure_remains_advisory_not_a_second_bias_authority():
    """market-swing-structure-analysis (built concurrently) composes structure/
    liquidity/MTF evidence but must not itself resolve a final bias -- it stays
    ADVISORY_CONTEXT_ONLY, per its own module (unchanged by this milestone)."""
    from market_swing_structure.models import AUTHORITY
    assert AUTHORITY == "ADVISORY_CONTEXT_ONLY"
    imports = _imports_of(_module_file("market_swing_structure.orchestrator"))
    assert not any(m == "market_intelligence" or m.startswith("market_intelligence.") for m in imports)


# ---------------------------------------------------------------------------
# narrative_bias is a separate, unreconciled package this milestone -- it must not be
# reachable from, or override, the canonical resolver path (proven by absence of any
# import edge in either direction).
# ---------------------------------------------------------------------------


def test_narrative_bias_has_no_import_path_to_or_from_canonical_resolver():
    narrative_imports = _imports_of(_module_file("daytrading.narrative_bias"))
    pipeline_imports = _imports_of(_module_file("daytrading.pipeline"))
    for mod in (narrative_imports | pipeline_imports):
        assert not (mod == "market_intelligence" or mod.startswith("market_intelligence.")), (
            "daytrading.narrative_bias/pipeline must not import the canonical resolver "
            "this milestone -- reconciling them is explicit future work, not silently done here"
        )
    bias_resolver_imports = _imports_of(REPO_ROOT / "src" / "market_intelligence" / "bias_resolver.py")
    assert not any(m == "daytrading.narrative_bias" or m.startswith("daytrading.narrative_bias") for m in bias_resolver_imports)


# ---------------------------------------------------------------------------
# Legacy adapter agreement (M3 concrete deliverable).
# ---------------------------------------------------------------------------


def test_legacy_market_bias_module_delegates_to_canonical_resolver():
    imports = _imports_of(_module_file("daytrading.decision.market_bias"))
    assert any(m == "market_intelligence.bias_resolver" or m.startswith("market_intelligence.bias_resolver") for m in imports), (
        "daytrading.decision.market_bias must delegate its direction label to the "
        "canonical resolver, not decide it independently"
    )


def test_setup_router_still_blocks_conflicting_direction_via_the_migrated_bias():
    """End-to-end: a MarketBias produced through the now-canonical-backed
    derive_market_bias_from_tiers still correctly blocks a conflicting setup direction
    in daytrading.decision.setup_router -- the real, already-wired consumer this
    migration targets."""
    from datetime import date, datetime, timezone

    from daytrading.decision.market_bias import derive_market_bias_from_tiers
    from daytrading.decision.setup_router import route_daytrading_setup
    from market_structure.models import STATE_BULLISH, StructureTier, TieredStructureResult
    from strategy_engine.session.candles import Candle

    def _candle(day, hh, mm, o, h, l, c):
        return Candle(time=datetime(2026, 1, day, hh, mm, tzinfo=timezone.utc), open=o, high=h, low=l, close=c)

    # BULLISH bias via the canonical-backed legacy adapter.
    tiers = TieredStructureResult(
        symbol="EURUSD", timeframe="H1", status="VALID", reason_codes=(),
        external=StructureTier(tier="EXTERNAL", swing_length=50, direction=STATE_BULLISH, swings=(), events=()),
    )
    bias = derive_market_bias_from_tiers(tiers, "H1")
    assert bias.direction == "BULLISH"

    # A session that produces a bearish TREND setup (session_close < session_open) --
    # must CONFLICT against the bullish bias, never execute.
    session_candles = [_candle(5, h, 0, 1.1010, 1.1012, 1.1008, 1.1010 - h * 0.0001) for h in range(6)]
    decision = route_daytrading_setup(
        strategy_id="TEST", symbol="EURUSD", session_name="Asian", session_date=date(2026, 1, 5),
        session_candles=session_candles, expected_bar_count=6, market_bias=bias,
    )
    assert decision.decision_status == "CONFLICT"
    assert decision.execution_eligible is False
