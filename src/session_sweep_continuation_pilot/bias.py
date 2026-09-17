"""Live H1 bias resolution for ST_SESSION_SWEEP_CONTINUATION_V1.

session_sweep_continuation.h1_bias.resolve_h1_market_bias is HISTORICAL-REPLAY-ONLY --
it requires an already-loaded HistoricalCandleStore plus a HistoricalSymbolMetadataManifest
carrying authority=="OWNER_APPROVED_DATASET_MANIFEST" (EURUSD's is currently
PENDING_OWNER_AUTHORIZATION, so that path cannot serve live proposals). This module
reuses the exact two generic, strategy-neutral, already-live-wired functions
daytrading.decision.market_bias.derive_market_bias() calls for other strategies'
live H1 bias -- market_structure.tiers.analyze_structure_tiers (live MT5, no historical
patch) and market_intelligence.bias_resolver.resolve_from_structure_tiers/
resolve_unavailable -- rather than writing new bias logic. session_sweep_continuation's
own M15 regime.py is untouched; this only supplies the bias_result run_replay's own
existing BIAS_MISSING fail-closed path (bias_gate.py) already handles when None.
"""
from __future__ import annotations

from datetime import datetime

from market_intelligence.bias_resolver import resolve_from_structure_tiers, resolve_unavailable
from market_intelligence.models import MarketBiasResult
from market_structure.tiers import analyze_structure_tiers

H1_TIMEFRAME = "H1"


def resolve_live_h1_bias(symbol: str, decision_time: datetime, session_pair: str) -> MarketBiasResult:
    """One MarketBiasResult for (symbol, decision_time, session_pair), sourced from
    LIVE MT5 H1 data (via analyze_structure_tiers's own live default), not a historical
    store. Fails closed to resolve_unavailable (NEUTRAL) on any non-VALID tiers status
    -- never a guessed direction."""
    tiers = analyze_structure_tiers(symbol, H1_TIMEFRAME)
    if tiers.status != "VALID":
        return resolve_unavailable(symbol, decision_time, session_pair, f"H1_TIERED_STRUCTURE_STATUS={tiers.status}")
    return resolve_from_structure_tiers(tiers, symbol, decision_time, session_pair, timeframe=H1_TIMEFRAME)
