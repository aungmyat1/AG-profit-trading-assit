"""Per-symbol fixture loader for the ST_LARGE_SMC_V1@1.1.1 candidate audit.

The JSON files and manifest are deliberately separate from the 1.1.0 synthetic fixtures:
EURUSD is recorded/derived from admitted host candles, GBPUSD is mixed host warmup context
plus explicitly synthetic D1/M5 probes, and the other four symbols are SYNTHETIC.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List

from strategy_engine.session import Candle

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "large_smc_v111"
MANIFEST_PATH = FIXTURE_DIR / "manifest.json"


def fixture_manifest() -> Dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def fixture_symbols() -> tuple[str, ...]:
    return tuple(item["symbol"] for item in fixture_manifest()["sources"])


def decision_time_utc() -> str:
    """The manifest's single declared decision time for this fixture set."""
    return str(fixture_manifest()["decision_time_utc"])


def check_decision_time(symbol: str, evaluated_at_utc: str) -> None:
    """Fail closed when a fixture's own evaluation time is not the manifest decision time.

    A regenerated EURUSD.json once carried its generation wall-clock
    (2026-10-10T19:45:53.895829Z) instead of the manifest's 2026-08-03T00:00:00Z: 68 days
    after its own last bar and inside the FX weekend close, so the case short-circuited to
    MARKET_CLOSED, L4 failed on freshness, and the oracle's closed-input check could never
    fail. Corrected 2026-10-13 (all 754 bars unchanged); this guard keeps the defect class
    from coming back silently through any harness that reads `evaluated_at`.
    """
    want = decision_time_utc()
    if evaluated_at_utc != want:
        raise ValueError(
            f"{symbol}: fixture evaluated_at_utc {evaluated_at_utc!r} != manifest decision_time_utc "
            f"{want!r}; the fixture would be evaluated outside its own recorded data window"
        )


def _parse_time(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def load_fixture(symbol: str) -> Dict[str, Any]:
    """Load a single canonical-symbol fixture without aliasing or cross-symbol scaling."""
    path = FIXTURE_DIR / f"{symbol}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("symbol") != symbol:
        raise ValueError(f"fixture symbol mismatch: requested {symbol}, got {raw.get('symbol')!r}")
    check_decision_time(symbol, str(raw["evaluated_at_utc"]))

    result: Dict[str, Any] = {
        "symbol": symbol,
        "evaluated_at": _parse_time(raw["evaluated_at_utc"]),
        "fixture_file": str(path.relative_to(ROOT)),
    }
    for timeframe in ("D1", "H1", "M5"):
        result[timeframe] = [
            Candle(
                _parse_time(row["time_utc"]),
                float(row["open"]),
                float(row["high"]),
                float(row["low"]),
                float(row["close"]),
            )
            for row in raw[timeframe]
        ]
    return result


def load_fixtures() -> List[Dict[str, Any]]:
    return [load_fixture(symbol) for symbol in fixture_symbols()]
