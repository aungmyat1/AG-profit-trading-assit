"""Canonical Stage-1 contract: QualifiedEEvent -- the frozen, persisted output of
E1/E2/E3 discovery + eligibility-lifecycle reconstruction, consumed by Stage 2
(historical_replay.stage2) without ever re-calling D1/H1 discovery.

Explicit reference fields (reference_type/low/high/level) are the canonical geometry;
reference_key is a DERIVED, deterministic identity string (proposals.identity.
reference_key_for), never the other way around -- _parse_reference_key() in stage2.py
remains a migration-compatibility path only, not the permanent source of truth.

Eligibility is time-varying (spec finding this phase: the same reference can go
FALSE -> TRUE -> FALSE -> TRUE -> FALSE), so eligibility_intervals is a list of
[start, end) pairs, not a single flag or a research-window assumption.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from proposals.identity import reference_key_for

from .stage2 import Stage1LiquidityReference, _parse_reference_key

SCHEMA_VERSION = "QUALIFIED_E_EVENT_V1"
CONTEXT_SCHEMA_VERSION = "STAGE1_CONTEXT_V2"
PRODUCER_VERSION = "AG_NATIVE_STAGE1_V1"


@dataclass(frozen=True)
class QualifiedEEvent:
    event_id: str
    producer_version: str

    symbol: str
    entry_condition: str
    direction: str

    qualification_time: datetime

    reference_type: Optional[str]
    reference_low: Optional[float]
    reference_high: Optional[float]
    reference_level: Optional[float]
    reference_key: Optional[str]

    eligibility_intervals: Tuple[Tuple[datetime, datetime], ...]

    htf_liquidity_reference: Optional[Stage1LiquidityReference] = None

    def is_eligible_at(self, t: datetime) -> bool:
        """Consumer contract for Stage 2: t must fall inside a [start, end) interval.
        Between two intervals, or before the first / after the last, is NOT eligible --
        this is the exact fix for the false 2025-08-19 READY regression (spec finding
        this phase): Stage 2 must not evaluate M1/M2/M3 for an event outside its real
        eligibility window."""
        return any(start <= t < end for start, end in self.eligibility_intervals)


def _make_event_id(symbol: str, entry_condition: str, direction: str, reference_key: Optional[str]) -> str:
    import hashlib
    digest = hashlib.blake2b(
        f"{symbol}|{entry_condition}|{direction}|{reference_key or 'NONE'}".encode("utf-8"), digest_size=8,
    ).hexdigest()
    return f"QE-{symbol}-{entry_condition}-{digest}"


def build_qualified_e_events(
    reference_geometry: List[Dict[str, Any]],
    eligibility: List[Dict[str, Any]],
    liquidity_references: Dict[Tuple[str, Optional[str], str], Stage1LiquidityReference],
    symbol: str,
) -> Tuple[QualifiedEEvent, ...]:
    """Merges three already-computed inputs into the canonical contract:
    - reference_geometry: [{entry_condition, reference_key, direction, qual_time}, ...]
      (from the existing migration fixture; reference fields are recovered from
      reference_key via _parse_reference_key -- ONLY acceptable as a migration path,
      see module docstring)
    - eligibility: [{entry_condition, reference_key, direction, eligibility_intervals}, ...]
      (from stage1_eligibility_intervals.json, ISO timestamp pairs)
    - liquidity_references: keyed by (entry_condition, reference_key, direction), E3 only
    """
    elig_by_key = {(e["entry_condition"], e["reference_key"], e["direction"]): e["eligibility_intervals"]
                   for e in eligibility}

    events = []
    for row in reference_geometry:
        key = (row["entry_condition"], row["reference_key"], row["direction"])
        ref_type, ref_low, ref_high, ref_level = _parse_reference_key(row["reference_key"])
        intervals_raw = elig_by_key.get(key, [])
        intervals = tuple(
            (datetime.fromisoformat(s), datetime.fromisoformat(e)) for s, e in intervals_raw
        )
        events.append(QualifiedEEvent(
            event_id=_make_event_id(symbol, row["entry_condition"], row["direction"], row["reference_key"]),
            producer_version=PRODUCER_VERSION, symbol=symbol,
            entry_condition=row["entry_condition"], direction=row["direction"],
            qualification_time=datetime.fromisoformat(row["qual_time"]),
            reference_type=ref_type, reference_low=ref_low, reference_high=ref_high, reference_level=ref_level,
            reference_key=row["reference_key"],
            eligibility_intervals=intervals,
            htf_liquidity_reference=liquidity_references.get(key),
        ))
    return tuple(events)


def _serialize_event(e: QualifiedEEvent) -> Dict[str, Any]:
    d = asdict(e)
    d["qualification_time"] = e.qualification_time.isoformat()
    d["eligibility_intervals"] = [[s.isoformat(), en.isoformat()] for s, en in e.eligibility_intervals]
    if e.htf_liquidity_reference is not None:
        lr = asdict(e.htf_liquidity_reference)
        for k in ("origin_time", "sweep_time", "reclaim_time"):
            if lr.get(k) is not None:
                lr[k] = lr[k].isoformat()
        d["htf_liquidity_reference"] = lr
    return d


def _deserialize_event(d: Dict[str, Any]) -> QualifiedEEvent:
    d = dict(d)
    d["qualification_time"] = datetime.fromisoformat(d["qualification_time"])
    d["eligibility_intervals"] = tuple(
        (datetime.fromisoformat(s), datetime.fromisoformat(e)) for s, e in d["eligibility_intervals"]
    )
    lr = d.get("htf_liquidity_reference")
    if lr is not None:
        lr = dict(lr)
        for k in ("origin_time", "sweep_time", "reclaim_time"):
            if lr.get(k) is not None:
                lr[k] = datetime.fromisoformat(lr[k])
        d["htf_liquidity_reference"] = Stage1LiquidityReference(**lr)
    return QualifiedEEvent(**d)


def save_qualified_e_events(events: Tuple[QualifiedEEvent, ...], path: str, metadata: Dict[str, Any]) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "producer_version": PRODUCER_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "metadata": metadata,
        "events": [_serialize_event(e) for e in events],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def fingerprint_qualified_e_events(events: Tuple[QualifiedEEvent, ...]) -> str:
    """SHA-256 over the deterministic, semantic content of a QualifiedEEvent set --
    event fields sorted by event_id, JSON-canonicalized (sort_keys, no whitespace).
    Deliberately excludes wall-clock `created_at`/producer metadata and any
    non-semantic ordering (golden-slice spec section 12): same semantic Stage1
    artifact -> same fingerprint, regardless of when/where it was regenerated."""
    import hashlib
    rows = sorted((_serialize_event(e) for e in events), key=lambda d: d["event_id"])
    canonical = json.dumps(rows, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_qualified_e_events(path: str) -> Tuple[Tuple[QualifiedEEvent, ...], Dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    if payload["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"schema_version mismatch: {payload['schema_version']!r} != {SCHEMA_VERSION!r}")
    events = tuple(_deserialize_event(e) for e in payload["events"])
    return events, payload["metadata"]


# --------------------------------------------------------------------------- directional HTF liquidity
# Call-graph audit finding (this phase): M3's liquidity_level is NOT owned by E3.
# conditional_entry_snapshot.py:222-256 computes htf_liquidity_buy/htf_liquidity_sell
# ONCE per poll (from one liquidity_result(symbol,"H1") call), selects
# `liquidity_level = htf_liquidity_buy if direction==SHORT else htf_liquidity_sell`
# purely by DIRECTION inside the per-direction loop, and the resulting M3 result is
# then cross-joined with E1/E2/E3 of matching direction by the composer. Modeling this
# as "E3's own payload" (the earlier, WRONG design) starves E1-paired and E2-paired M3
# evaluations of a liquidity_level they should have had, exactly as diagnosed via the
# missing SETUP-EURUSD-E1M3-29ef3d6e78d5f9c2 setup this phase found.

@dataclass(frozen=True)
class DirectionalLiquidityInterval:
    start_time: datetime
    end_time: datetime
    liquidity_reference: Optional[Stage1LiquidityReference]


@dataclass(frozen=True)
class DirectionalLiquidityTimeline:
    """[start, end) intervals per side ("BUY_SIDE"/"SELL_SIDE" -- matches
    LiquiditySide.value), time-varying, gaps preserved as liquidity_reference=None.
    No fallback/backfill: a query outside any interval, or inside a None interval,
    returns None -- exactly what the original per-poll evaluator would have seen."""
    buy: Tuple[DirectionalLiquidityInterval, ...]
    sell: Tuple[DirectionalLiquidityInterval, ...]

    def lookup(self, direction: str, t: datetime) -> Optional[Stage1LiquidityReference]:
        # direction "SHORT" -> BUY_SIDE liquidity, "LONG" -> SELL_SIDE (matches
        # conditional_entry_snapshot.py:254's own mapping exactly)
        intervals = self.buy if direction == "SHORT" else self.sell
        for iv in intervals:
            if iv.start_time <= t < iv.end_time:
                return iv.liquidity_reference
        return None


@dataclass(frozen=True)
class Stage1Dataset:
    """Wraps the unchanged QualifiedEEvent set (E identity/reference/qualification/
    eligibility -- STAGE1_CORE, frozen) together with the directional liquidity
    timeline (the one field that was mis-scoped to E3-only; now direction-scoped and
    shared, matching original semantics) -- spec source phase's `Stage1Dataset`."""
    events: Tuple[QualifiedEEvent, ...]
    liquidity_timeline: DirectionalLiquidityTimeline
    metadata: Dict[str, Any]


def _liq_ref_from_dict(d: Optional[Dict[str, Any]]) -> Optional[Stage1LiquidityReference]:
    if d is None:
        return None
    return Stage1LiquidityReference(
        symbol=d.get("symbol", ""), timeframe=d.get("timeframe", "H1"), side=d["side"], source=d["source"],
        price=d["price"], origin_time=None, status=d.get("status", "UNKNOWN"),
        sweep_time=datetime.fromisoformat(d["sweep_time"]) if d.get("sweep_time") else None,
        reclaim_time=datetime.fromisoformat(d["reclaim_time"]) if d.get("reclaim_time") else None,
    )


def load_directional_liquidity_timeline(path: str) -> DirectionalLiquidityTimeline:
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)

    def _side(raw: List[Dict[str, Any]]) -> Tuple[DirectionalLiquidityInterval, ...]:
        return tuple(
            DirectionalLiquidityInterval(
                start_time=datetime.fromisoformat(iv["start_time"]), end_time=datetime.fromisoformat(iv["end_time"]),
                liquidity_reference=_liq_ref_from_dict(iv["liquidity_reference"]),
            )
            for iv in raw
        )

    return DirectionalLiquidityTimeline(buy=_side(payload["BUY"]), sell=_side(payload["SELL"]))


def load_stage1_dataset(events_path: str, liquidity_path: str) -> Stage1Dataset:
    events, metadata = load_qualified_e_events(events_path)
    timeline = load_directional_liquidity_timeline(liquidity_path)
    return Stage1Dataset(events=events, liquidity_timeline=timeline, metadata=metadata)
