#!/usr/bin/env python
"""COUNTERFACTUAL_REPLAY -- MODEL_A (SESSION_RANGE_25) candidate stop-loss geometry
against the same 13 frozen ST_ASIAN_SWEEP_5R_V1 v1.1.1 forward-shadow READY proposals
already resolved by scripts/resolve_forward_shadow_outcomes.py.

NOT_ORIGINAL_EVIDENCE. NOT_LIVE_OBSERVATION. NOT_PROMOTION_EVIDENCE.

This tool:
  - never calls mt5.order_check / mt5.order_send / any broker mutation (read-only market
    data fetch only, identical to the original resolver's own MT5 usage);
  - never writes to journal/post_asian_pilot/, journal/post_london_newyork_pilot/,
    journal/reports/fx/, or artifacts/outcome_resolution/ (the original evidence is never
    touched, read-only input only);
  - writes only under artifacts/candidate_research/model_a_session_range_25/, a new,
    isolated research surface, one record per proposal plus an aggregate snapshot;
  - never modifies strategies/ST_ASIAN_SWEEP_5R_V1.yaml or any release/qualification file.

For every original event this script preserves (read-only, from the existing
artifacts/outcome_resolution/records/*.json) the original_proposal_id,
original_strategy_version, original_entry, original_direction, original_SL,
original_result, original_R, and adds only derived candidate_* fields plus
risk-sizing comparison fields.

MODEL A CONTRACT (from strategies/ST_ASIAN_SWEEP_5R_V1.yaml's own already-declared,
never-consumed stop_loss_range_pct=0.25):
    candidate_SL_distance = (box_high - box_low) * stop_loss_range_pct
TP1 stays OPPOSITE_SESSION_BOUNDARY (unchanged strategy contract, not the variable under
test). TP2 stays the existing 5.0R-on-remaining-25% formula, but R is now measured off
the candidate SL distance -- this is the same formula the original resolver used, only
the risk denominator changes.

Usage:
    python scripts/replay_candidate_model_a_session_range_25.py [--json]
"""
from __future__ import annotations

import json
import statistics
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from mt5.connection import MT5ConnectionError, connect  # noqa: E402
from mt5.market_data import MarketDataError, get_candles  # noqa: E402
from mt5.symbol_resolver import SymbolMeta  # noqa: E402
from execution.risk import size_position  # noqa: E402
from strategy_engine.session.candidate_stop_models import (  # noqa: E402
    CANDIDATE_MODEL_ID, CANDIDATE_VERSION, CandidateStopModelError, session_range_25_stop,
)
from strategy_engine.session.setups import Direction  # noqa: E402

STRATEGY_ID = "ST_ASIAN_SWEEP_5R_V1"
STRATEGY_VERSION = "1.1.1"
STOP_LOSS_RANGE_PCT = 0.25  # strategies/ST_ASIAN_SWEEP_5R_V1.yaml risk_and_money_management

JOURNAL_DIRS = {
    "ASIAN_LONDON": REPO_ROOT / "journal" / "post_asian_pilot",
    "LONDON_NEWYORK": REPO_ROOT / "journal" / "post_london_newyork_pilot",
}
TRADE_SESSION_END_UTC = {"ASIAN_LONDON": "11:00", "LONDON_NEWYORK": "15:00"}

ORIGINAL_RECORDS_DIR = REPO_ROOT / "artifacts" / "outcome_resolution" / "records"
OUTPUT_DIR = REPO_ROOT / "artifacts" / "candidate_research" / "model_a_session_range_25"
RECORDS_DIR = OUTPUT_DIR / "records"

TP1_VOLUME_PCT = 0.75
TP2_VOLUME_PCT = 0.25
TP2_FIXED_R = 5.0

# Same illustrative EURUSD/GBPUSD broker metadata shape used elsewhere in this repo's own
# test fixtures (tests/test_execution_coordinator.py) -- not real live account state.
SYMBOL_META = {
    "EURUSD": SymbolMeta(symbol="EURUSD", tick_size=0.00001, tick_value=1.0, contract_size=100000.0,
                          volume_min=0.01, volume_max=50.0, volume_step=0.01, digits=5),
    "GBPUSD": SymbolMeta(symbol="GBPUSD", tick_size=0.00001, tick_value=1.0, contract_size=100000.0,
                          volume_min=0.01, volume_max=50.0, volume_step=0.01, digits=5),
}
RESEARCH_EQUITY = 10_000.0
RESEARCH_RISK_PCT = 1.0


def _parse_utc(value: str) -> datetime:
    v = value.strip()
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    dt = datetime.fromisoformat(v)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _session_cutoff(ready_at: datetime, cycle: str) -> datetime:
    hh, mm = (int(x) for x in TRADE_SESSION_END_UTC[cycle].split(":"))
    return ready_at.replace(hour=hh, minute=mm, second=0, microsecond=0)


def load_original_population() -> List[dict]:
    """Read-only: pair each frozen original outcome record with its box_high/box_low
    (needed for Model A, not stored in the original outcome record) from the same
    decision.json journals the original resolver read. Never writes to either source."""
    box_by_key: Dict[str, dict] = {}
    for cycle, journal_dir in JOURNAL_DIRS.items():
        decision_path = journal_dir / "decision.json"
        if not decision_path.exists():
            continue
        decisions = json.loads(decision_path.read_text(encoding="utf-8"))
        for key, decision in decisions.items():
            if decision.get("status") != "READY":
                continue
            if decision.get("strategy_id") != STRATEGY_ID or decision.get("strategy_version") != STRATEGY_VERSION:
                continue
            signal = decision.get("signal") or {}
            box_by_key[(decision.get("symbol"), cycle, decision.get("trading_date"))] = {
                "box_high": signal.get("box_high"), "box_low": signal.get("box_low"),
            }

    records = []
    for f in sorted(ORIGINAL_RECORDS_DIR.glob("*.json")):
        original = json.loads(f.read_text(encoding="utf-8"))
        key = (original["symbol"], original["cycle"], original["trading_date"])
        box = box_by_key.get(key)
        if box is None or box["box_high"] is None or box["box_low"] is None:
            original["_box_lookup_status"] = "BOX_NOT_FOUND"
        else:
            original["_box_lookup_status"] = "OK"
            original["_box_high"] = box["box_high"]
            original["_box_low"] = box["box_low"]
        records.append(original)
    return records


@dataclass
class CandidateReplayRecord:
    original_proposal_id: str
    original_strategy_version: str
    original_entry: float
    original_direction: str
    original_SL: float
    original_result: str
    original_R: Optional[float]
    candidate_model: str = CANDIDATE_MODEL_ID
    candidate_version: str = CANDIDATE_VERSION
    box_high: Optional[float] = None
    box_low: Optional[float] = None
    reference_session_range: Optional[float] = None
    candidate_SL: Optional[float] = None
    candidate_SL_distance: Optional[float] = None
    candidate_TP1: Optional[float] = None
    candidate_TP2: Optional[float] = None
    candidate_result: Optional[str] = None
    candidate_R: Optional[float] = None
    legacy_lot: Optional[float] = None
    legacy_risk_amount: Optional[float] = None
    legacy_lot_reason: Optional[str] = None
    candidate_lot: Optional[float] = None
    candidate_risk_amount: Optional[float] = None
    candidate_lot_reason: Optional[str] = None
    geometry_error: Optional[str] = None
    event_sequence: list = field(default_factory=list)
    classification: str = "COUNTERFACTUAL_REPLAY"
    evidence_labels: list = field(default_factory=lambda: [
        "COUNTERFACTUAL_REPLAY", "NOT_ORIGINAL_EVIDENCE", "NOT_LIVE_OBSERVATION", "NOT_PROMOTION_EVIDENCE",
    ])


def _simulate(direction: str, entry: float, stop_loss: float, tp1: float, tp2: float,
              risk: float, candles) -> tuple:
    """Same three-phase (SL/TP1 -> BE/TP2 runner) simulation the original resolver uses,
    parameterized so it can be re-run against candidate geometry. Returns
    (terminal_state, realized_R, event_sequence)."""
    is_long = direction == "LONG"
    tp1_R = ((tp1 - entry) / risk) if is_long else ((entry - tp1) / risk)
    events = []

    tp1_index = None
    for i, c in enumerate(candles):
        sl_hit = (c.low <= stop_loss) if is_long else (c.high >= stop_loss)
        tp1_hit = (c.high >= tp1) if is_long else (c.low <= tp1)
        if sl_hit and tp1_hit:
            events.append({"time": c.time.isoformat(), "event": "SL_AND_TP1_SAME_CANDLE"})
            return "AMBIGUOUS_SEQUENCE", None, events
        if sl_hit:
            events.append({"time": c.time.isoformat(), "event": "SL"})
            return "RESOLVED_SL", -1.0, events
        if tp1_hit:
            tp1_index = i
            events.append({"time": c.time.isoformat(), "event": "TP1"})
            break

    if tp1_index is None:
        last = candles[-1]
        realized_R = ((last.close - entry) / risk) if is_long else ((entry - last.close) / risk)
        events.append({"time": last.time.isoformat(), "event": "SESSION_EXIT_FULL_POSITION"})
        return "RESOLVED_SESSION_EXIT", realized_R, events

    be_price = entry
    for c in candles[tp1_index:]:
        if c is candles[tp1_index]:
            continue
        be_hit = (c.low <= be_price) if is_long else (c.high >= be_price)
        tp2_hit = (c.high >= tp2) if is_long else (c.low <= tp2)
        if be_hit and tp2_hit:
            events.append({"time": c.time.isoformat(), "event": "BE_AND_TP2_SAME_CANDLE"})
            return "AMBIGUOUS_SEQUENCE", None, events
        if be_hit:
            events.append({"time": c.time.isoformat(), "event": "RUNNER_BE_STOP"})
            return "RESOLVED_TP1_BE", TP1_VOLUME_PCT * tp1_R, events
        if tp2_hit:
            events.append({"time": c.time.isoformat(), "event": "RUNNER_TP2"})
            return "RESOLVED_TP1_TP2", TP1_VOLUME_PCT * tp1_R + TP2_VOLUME_PCT * TP2_FIXED_R, events

    last = candles[-1]
    runner_R = ((last.close - entry) / risk) if is_long else ((entry - last.close) / risk)
    events.append({"time": last.time.isoformat(), "event": "SESSION_EXIT_RUNNER"})
    return "RESOLVED_SESSION_EXIT", TP1_VOLUME_PCT * tp1_R + TP2_VOLUME_PCT * runner_R, events


def replay_one(original: dict) -> CandidateReplayRecord:
    rec = CandidateReplayRecord(
        original_proposal_id=original["proposal_id"],
        original_strategy_version=original["strategy_version"],
        original_entry=original["entry"],
        original_direction=original["direction"],
        original_SL=original["stop_loss"],
        original_result=original["terminal_state"],
        original_R=original.get("realized_R"),
    )

    if original.get("_box_lookup_status") != "OK":
        rec.geometry_error = "BOX_NOT_FOUND"
        return rec

    box_high = original["_box_high"]
    box_low = original["_box_low"]
    rec.box_high = box_high
    rec.box_low = box_low
    direction_enum = Direction.LONG if original["direction"] == "LONG" else Direction.SHORT

    try:
        candidate = session_range_25_stop(
            direction=direction_enum, entry=original["entry"], box_high=box_high, box_low=box_low,
            stop_loss_range_pct=STOP_LOSS_RANGE_PCT,
        )
    except CandidateStopModelError as exc:
        rec.geometry_error = str(exc)
        return rec

    rec.reference_session_range = candidate.reference_session_range
    rec.candidate_SL = candidate.stop_loss
    rec.candidate_SL_distance = candidate.stop_distance

    is_long = original["direction"] == "LONG"
    entry = original["entry"]
    # TP1 unchanged (OPPOSITE_SESSION_BOUNDARY) -- not the variable under test.
    tp1 = box_high if is_long else box_low
    tp2 = entry + TP2_FIXED_R * candidate.stop_distance if is_long else entry - TP2_FIXED_R * candidate.stop_distance
    rec.candidate_TP1 = tp1
    rec.candidate_TP2 = tp2

    symbol = original["symbol"]
    meta = SYMBOL_META.get(symbol)
    if meta is not None:
        legacy_dist = abs(original["entry"] - original["stop_loss"])
        l_vol, l_risk, l_reason = (None, None, "INVALID_STOP_DISTANCE") if legacy_dist <= 0 else \
            size_position(original["entry"], original["stop_loss"], RESEARCH_EQUITY, RESEARCH_RISK_PCT, meta)
        rec.legacy_lot, rec.legacy_risk_amount, rec.legacy_lot_reason = l_vol, l_risk, l_reason

        c_vol, c_risk, c_reason = size_position(entry, candidate.stop_loss, RESEARCH_EQUITY, RESEARCH_RISK_PCT, meta)
        rec.candidate_lot, rec.candidate_risk_amount, rec.candidate_lot_reason = c_vol, c_risk, c_reason

    ready_at = _parse_utc(original["proposal_timestamp"])
    cutoff = _session_cutoff(ready_at, original["cycle"])
    try:
        candles = get_candles(symbol, "M1", ready_at, cutoff)
    except MarketDataError as exc:
        rec.geometry_error = f"DATA_MISSING: {exc.reason_code}"
        return rec
    if not candles:
        rec.geometry_error = "NO_CANDLES_IN_WINDOW"
        return rec

    state, realized_R, events = _simulate(
        original["direction"], entry, candidate.stop_loss, tp1, tp2, candidate.stop_distance, candles,
    )
    rec.candidate_result = state
    rec.candidate_R = realized_R
    rec.event_sequence = events
    return rec


def main(argv=None) -> int:
    as_json = "--json" in (argv or sys.argv[1:])

    population = load_original_population()
    if not population:
        print(json.dumps({"status": "NO_ORIGINAL_POPULATION_FOUND"}))
        return 1

    try:
        connect()
    except MT5ConnectionError as exc:
        print(json.dumps({"status": "MT5_NOT_CONNECTED", "reason": str(exc)}))
        return 1

    RECORDS_DIR.mkdir(parents=True, exist_ok=True)
    results: List[CandidateReplayRecord] = []
    for original in population:
        rec = replay_one(original)
        results.append(rec)
        out_path = RECORDS_DIR / (Path(original["proposal_id"].replace(":", "_")).name + ".json")
        out_path.write_text(json.dumps(asdict(rec), indent=2, default=str), encoding="utf-8")

    resolved_states = {"RESOLVED_SL", "RESOLVED_TP1_BE", "RESOLVED_TP1_TP2", "RESOLVED_SESSION_EXIT"}
    blocked = [r for r in results if r.geometry_error is not None]
    resolved = [r for r in results if r.candidate_result in resolved_states]
    ambiguous = [r for r in results if r.candidate_result == "AMBIGUOUS_SEQUENCE"]
    realized = [r.candidate_R for r in resolved if r.candidate_R is not None]
    wins = [r for r in realized if r > 0.0001]
    losses = [r for r in realized if r < -0.0001]

    sl_distances_pips = []
    for r in results:
        if r.candidate_SL_distance is not None:
            pip = 0.01 if "JPY" in r.original_proposal_id else 0.0001
            sl_distances_pips.append(r.candidate_SL_distance / pip)

    candidate_lots = [r.candidate_lot for r in results if r.candidate_lot is not None]
    legacy_lots = [r.legacy_lot for r in results if r.legacy_lot is not None]
    candidate_rejections = [r for r in results if r.candidate_lot_reason is not None]

    snapshot = {
        "schema": "AG_CANDIDATE_MODEL_A_COUNTERFACTUAL_REPLAY_V1",
        "strategy": STRATEGY_ID,
        "reference_strategy_version": STRATEGY_VERSION,
        "candidate_model": CANDIDATE_MODEL_ID,
        "candidate_version": CANDIDATE_VERSION,
        "classification": "COUNTERFACTUAL_REPLAY",
        "labels": ["COUNTERFACTUAL_REPLAY", "NOT_ORIGINAL_EVIDENCE", "NOT_LIVE_OBSERVATION", "NOT_PROMOTION_EVIDENCE"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "events_evaluated": len(results),
        "events_blocked": len(blocked),
        "blocked_reasons": [r.geometry_error for r in blocked],
        "resolved": len(resolved),
        "ambiguous": len(ambiguous),
        "wins": len(wins),
        "losses": len(losses),
        "net_R": round(sum(realized), 4) if realized else None,
        "expectancy_R": round(statistics.mean(realized), 4) if realized else None,
        "min_SL_pips": round(min(sl_distances_pips), 3) if sl_distances_pips else None,
        "median_SL_pips": round(statistics.median(sl_distances_pips), 3) if sl_distances_pips else None,
        "max_SL_pips": round(max(sl_distances_pips), 3) if sl_distances_pips else None,
        "sub_pip_stops_remaining": sum(1 for p in sl_distances_pips if p < 1.0),
        "candidate_lot_distribution": {
            "min": min(candidate_lots) if candidate_lots else None,
            "max": max(candidate_lots) if candidate_lots else None,
            "median": statistics.median(candidate_lots) if candidate_lots else None,
        },
        "legacy_lot_distribution": {
            "min": min(legacy_lots) if legacy_lots else None,
            "max": max(legacy_lots) if legacy_lots else None,
            "median": statistics.median(legacy_lots) if legacy_lots else None,
        },
        "candidate_risk_guard_rejections": len(candidate_rejections),
        "cost_model": "NOT_INCLUDED (matches original resolver's own gross-of-costs basis)",
        "research_equity_assumption": RESEARCH_EQUITY,
        "research_risk_pct_assumption": RESEARCH_RISK_PCT,
    }
    (OUTPUT_DIR / "AG_CANDIDATE_MODEL_A_COUNTERFACTUAL_REPLAY_SNAPSHOT_V1.json").write_text(
        json.dumps(snapshot, indent=2, default=str), encoding="utf-8",
    )

    if as_json:
        print(json.dumps(snapshot, indent=2, default=str))
    else:
        print(f"Replayed {len(results)} original events (candidate={CANDIDATE_MODEL_ID}/{CANDIDATE_VERSION}) -> {OUTPUT_DIR}")
        print(json.dumps(snapshot, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
