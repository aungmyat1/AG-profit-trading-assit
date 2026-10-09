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


def _parse_time(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def load_fixture(symbol: str) -> Dict[str, Any]:
    """Load a single canonical-symbol fixture without aliasing or cross-symbol scaling."""
    path = FIXTURE_DIR / f"{symbol}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("symbol") != symbol:
        raise ValueError(f"fixture symbol mismatch: requested {symbol}, got {raw.get('symbol')!r}")

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
