"""TD-8: stable dataset/source identity for a loaded historical candle series --
distinct from HistoricalSymbolMetadataManifest's file-level dataset_fingerprint
(symbol_metadata_manifest.py), which authorizes a whole owner-approved dataset FILE for
tick_size use. This module answers a narrower, purely structural question instead: "do
two loaded (symbol, timeframe) candle series actually contain the same content?" --
needed so HistoricalCandleStore can distinguish two datasets that share the exact same
symbol/timeframe/timestamps but differ in OHLC content (TD-8 dataset-collision
requirement), and so a future TD-6 Layer-B derived-fact cache key COULD safely include
dataset identity as a discriminator (not wired this pass -- see
TD6_DERIVED_CACHE_INTEGRATION_DEFERRED, still deferred).

Reuses the exact "sha256:<hex>" framing historical_replay/symbol_metadata_manifest.py's
compute_dataset_fingerprint() already established for candle-dataset-adjacent identity
in this repo -- no second checksum scheme invented. This one is a CONTENT fingerprint
(not a file-byte fingerprint, since HistoricalCandleStore.load_series() takes
already-parsed in-memory Candle objects, not a file path), using the same
JSON-canonicalization idiom historical_replay/stage1.py::fingerprint_qualified_e_events()
already established for semantic-content hashing in this package.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Sequence

from strategy_engine.session import Candle


@dataclass(frozen=True)
class ReplayDatasetIdentity:
    """Identifies WHICH underlying candle dataset a HistoricalCandleStore's
    (symbol, timeframe) series actually came from -- distinct from LIVE data (which
    never carries this at all; see mtf_context.topdown_contracts.TopDownContext's
    dataset_identity field, which is required for HISTORICAL_AS_OF and forbidden for
    LIVE_CURRENT) and from a different replay dataset that happens to share the same
    symbol/timeframe/timestamps but different OHLC content (`fingerprint` is
    content-derived, not shape-derived -- see compute_candle_series_fingerprint)."""

    dataset_id: str
    source: str
    symbol: str
    timeframe: str
    fingerprint: str
    coverage_start: datetime
    coverage_end: datetime

    def as_composed_identity_token(self) -> str:
        """Deterministic, pipe-joined token suitable for folding into a composed
        TopDownContext's own identity hash (see mtf_context.topdown_composer) -- same
        payload-construction discipline as topdown_contracts.compute_context_id, just
        scoped to this one object."""
        return "|".join([self.dataset_id, self.source, self.symbol, self.timeframe, self.fingerprint])


def compute_candle_series_fingerprint(symbol: str, timeframe: str, candles: Sequence[Candle]) -> str:
    """SHA-256 over the deterministic, semantic content of a candle series -- time,
    OHLC, and volume for every candle, JSON-canonicalized (sort_keys, no whitespace)
    and sorted by time. Two series with identical timestamps but different OHLC
    content (the exact TD-8 dataset-collision scenario) always produce different
    fingerprints; two series with identical content always produce the same one,
    regardless of the order `candles` was supplied in. `symbol`/`timeframe` are
    included in the hash so an otherwise-identical OHLC series loaded for a different
    symbol or timeframe is never mistaken for the same dataset."""
    rows = sorted(
        (
            {"t": c.time.isoformat(), "o": c.open, "h": c.high, "l": c.low, "c": c.close, "v": c.volume}
            for c in candles
        ),
        key=lambda row: row["t"],
    )
    canonical = json.dumps({"symbol": symbol, "timeframe": timeframe, "candles": rows},
                           sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def build_dataset_identity(
    *, symbol: str, timeframe: str, candles: Sequence[Candle],
    dataset_id: Optional[str] = None, source: str = "REPLAY",
) -> ReplayDatasetIdentity:
    """`dataset_id` defaults to a short, content-derived id (`SYMBOL:TIMEFRAME:<hash
    prefix>`) when the caller doesn't supply one -- collision-safety comes entirely
    from `fingerprint` (always content-derived), never from the label, so an
    un-labeled load still gets a real, distinguishing identity for free."""
    if not candles:
        raise ValueError(f"cannot build a dataset identity for {symbol} {timeframe} from an empty candle series")
    ordered = sorted(candles, key=lambda c: c.time)
    fingerprint = compute_candle_series_fingerprint(symbol, timeframe, candles)
    resolved_dataset_id = dataset_id or f"{symbol}:{timeframe}:{fingerprint.split(':', 1)[1][:16]}"
    return ReplayDatasetIdentity(
        dataset_id=resolved_dataset_id, source=source, symbol=symbol, timeframe=timeframe,
        fingerprint=fingerprint, coverage_start=ordered[0].time, coverage_end=ordered[-1].time,
    )
