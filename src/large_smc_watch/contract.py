"""ST_LARGE_SMC_V1@1.1.0 -- owner-stated rule constants (AG V1, 2026-09-30).

Authority: the owner-stated 1.1.0 rules recorded in
docs/governance/AG_V1_TWO_GOALS_OWNER_DECISIONS.md (owner decision 3: the RMR-A
catalogue branch was never pushed, so the rules written in the mission are
authoritative). Contract file: strategies/ST_LARGE_SMC_V1_1_1_0.yaml. v1.0.7
(strategies/ST_LARGE_SMC_V1.yaml) is preserved unchanged.

Alerts only: proposal_generation_authorized = False; no execution authority.
"""
from __future__ import annotations

from typing import Dict, Optional

STRATEGY_ID = "ST_LARGE_SMC_V1"
STRATEGY_VERSION = "1.1.0"
PROPOSAL_GENERATION_AUTHORIZED = False
ECONOMIC_STATUS = "NOT_EVALUATED"  # D30: OPPORTUNITY is a badge, never an economic claim

# D00: keep D1/H1/M5. D1 = trading-day context, H1 = bias + POI, M5 = sweep/CHoCH trigger.
TIMEFRAME_MINUTES = {"D1": 1440, "H1": 60, "M5": 5}

# Swings: SW-A strict fractal, causal (fx_discovery.features.swings). K is not in the
# owner-stated rules; K=2 is the canonical fx_discovery value (families.py: K = 2).
SWING_K = 2
TIE_TOLERANCE_POINTS = 5          # break by close; a close within 5 points of the level is a tie
POI_MAX_AGE_TRADING_DAYS = 5
SWEEP_TO_CHOCH_WINDOW_M5 = 12
NEAR_POI_BAND_ATR_MULT = 0.5      # x ATR(H1, 14)
ATR_H1_PERIOD = 14
OB_MAX_ORIGIN_LOOKBACK = 3        # AG_ORDER_BLOCK_V1 MAX_CANDLES_TO_FVG = 3, reused for origin search
DAY_BOUNDARY_TZ = "America/New_York"
DAY_BOUNDARY_HOUR = 17            # trading day rolls at 17:00 New York (IANA, DST-aware)
STALE_AFTER_MINUTES = 15          # 3 missing M5 bars -> data is stale
MIN_H1_BARS = ATR_H1_PERIOD + 16
MIN_M5_BARS = 30

# Alert mapping (owner-stated). SUSPENDED / IDLE / DATA_ERROR / MARKET_CLOSED emit nothing.
ALERT_LEVEL = {
    "DEVELOPING": "INFO",
    "NEAR_POI": "WATCH",
    "OPPORTUNITY": "OPPORTUNITY",
    "INVALIDATED": "INFO",
    "EXPIRED": "INFO",
}

CRYPTO_SYMBOLS = ("BTCUSDT", "ETHUSDT")
V1_SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSDT", "ETHUSDT")

# Symbol point sizes already evidenced in this repository. USDJPY and XAUUSD have none:
# their watch path is FIXTURE_ONLY until the host captures MT5 symbol_info() (see
# docs/status/AG_V1_TWO_GOALS_CLOUD_STATUS.md). A caller may pass an explicit point for
# fixtures; it is then stamped metadata_source=CALLER_SUPPLIED.
EVIDENCED_POINT: Dict[str, float] = {
    "EURUSD": 0.00001,  # config/historical_datasets/EURUSD_*_symbol_metadata.yaml (owner-approved)
    "GBPUSD": 0.00001,  # config/historical_datasets/GBPUSD_H1_symbol_metadata.yaml @ 2b75bbf (owner-approved)
    "BTCUSDT": 0.1,     # strategy_engine/sweep_retest/crypto_symbols.py CRYPTO_TICK_SIZE (frozen)
    "ETHUSDT": 0.01,    # strategy_engine/sweep_retest/crypto_symbols.py CRYPTO_TICK_SIZE (frozen)
}
# C10's hard floor is expressed in pips; a pip is only evidenced for 5-digit FX majors.
C10_PIP_SIZE: Dict[str, float] = {"EURUSD": 0.0001, "GBPUSD": 0.0001}


def resolve_point(symbol: str, supplied: Optional[float] = None) -> "tuple[Optional[float], str]":
    if symbol in EVIDENCED_POINT:
        return EVIDENCED_POINT[symbol], "REPO_EVIDENCED"
    # Host go-live kit: a verified host capture (scripts/host/capture_symbol_metadata.py,
    # sha256-checked) promotes USDJPY/XAUUSD from FIXTURE_ONLY. A bad or missing file fails closed.
    from host_evidence.symbol_metadata import HOST_CAPTURED, load_record
    record = load_record(symbol)
    if record is not None:
        return float(record["fields"]["point"]), HOST_CAPTURED
    if supplied is not None and supplied > 0:
        return float(supplied), "CALLER_SUPPLIED"
    return None, "MISSING"
