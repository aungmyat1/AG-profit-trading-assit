"""Fail-closed open-bar guard for ST_CRYPTO_CFD_SWEEP_RETEST_V1 (AGP-LANE-B2).

`evaluate()` here is the strategy's public entry point (re-exported as
`crypto_cfd_contract.evaluate`). It ignores every supplied bar whose close_time > now --
on M5, M15, H1 and D1 -- before the frozen chain in rules.evaluate runs, so a forming
H1/D1 bar can never influence a result whatever the caller passes.

rules.py is byte-frozen by research candidate CRYPTO_CFD_C001
(research/edge_discovery/candidates/CRYPTO_CFD_C001.freeze.json); its own filter only drops
bars timestamped at/after `now`. Folding this guard into rules.py would need a new
candidate id (OWNER_DECISION_REGISTER C001-PRE-RESULT-CORRECTION), so it lives here.

close_time: M5/M15/H1 = open + step; D1 = broker server-day close via the shared
host_evidence.symbol_metadata.server_bar_close_utc (23h/25h across a US DST change).
No new time arithmetic. For closed-only input the result is byte-identical to
rules.evaluate; when a forming bar is dropped, evidence.causal_filter.open_bar_guard
records how many per timeframe.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Sequence

from host_evidence.symbol_metadata import server_bar_close_utc
from market_structure.models import MarketStructureConfig
from strategy_engine.session import Candle

from . import rules

BAR_STEP = {"m5": timedelta(minutes=5), "m15": timedelta(minutes=15), "h1": timedelta(hours=1),
            "d1": timedelta(days=1)}
OPEN_BAR_RULE = "a bar whose close_time > now is forming and is ignored (D1 close = server-day close)"


def bar_close_utc(candle: Candle, timeframe: str) -> datetime:
    step = BAR_STEP[timeframe]
    return server_bar_close_utc(candle.time, step) if timeframe == "d1" else candle.time + step


def drop_open_bars(candles: Sequence[Candle], timeframe: str, now: datetime) -> List[Candle]:
    return [c for c in candles if bar_close_utc(c, timeframe) <= now]


def evaluate(symbol: str, now: datetime, d1_candles: Sequence[Candle],
             h1_candles: Sequence[Candle], m5_candles: Sequence[Candle],
             m15_candles: Sequence[Candle] = (),
             structure_config: Optional[MarketStructureConfig] = None) -> dict:
    supplied = {"d1": list(d1_candles), "h1": list(h1_candles), "m5": list(m5_candles),
                "m15": list(m15_candles)}
    kept = {tf: drop_open_bars(rows, tf, now) for tf, rows in supplied.items()}
    result = rules.evaluate(symbol, now, kept["d1"], kept["h1"], kept["m5"], kept["m15"],
                            structure_config=structure_config)
    forming: Dict[str, int] = {tf: sum(1 for c in supplied[tf] if c.time < now) - sum(1 for c in kept[tf]
                                                                                    if c.time < now)
                               for tf in supplied}
    if any(forming.values()):
        result["evidence"].setdefault("causal_filter", {})["open_bar_guard"] = {
            "rule": OPEN_BAR_RULE, "dropped_forming": forming}
    return result
