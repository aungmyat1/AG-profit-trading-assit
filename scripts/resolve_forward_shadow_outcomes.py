#!/usr/bin/env python
"""AG_TRADE_OUTCOME_RESOLVER_V1 -- retrospective, read-only economic outcome resolution
for genuine ST_ASIAN_SWEEP_5R_V1 v1.1.1 forward-shadow READY proposals.

This is a PROFITABILITY_RESEARCH tool, not a qualification or execution surface:

  - It never calls mt5.order_check / mt5.order_send / any broker mutation.
  - It never writes to journal/post_asian_pilot/, journal/post_london_newyork_pilot/,
    journal/reports/fx/, or any other qualification/production journal path.
  - It writes only under artifacts/outcome_resolution/ (a new, isolated, read-only-input
    research surface), one immutable JSON record per proposal plus an aggregate snapshot.
  - It never modifies strategies/ST_ASIAN_SWEEP_5R_V1.yaml or any release/qualification file.

Resolution contract (AG_OUTCOME_RESOLUTION_CONTRACT_V1_DRAFT -- see module docstring
sections below for the exact interpretations applied; two of these are genuine
ambiguity-resolutions in the frozen strategy YAML, flagged explicitly rather than
silently assumed):

  ENTRY / FILL
    entry_order_type is MARKET at `entry_level: Sweep_Candle_Body_Close` (strategy YAML).
    The `entry` price already recorded in the proposal/decision journal at `ready_at` IS
    the real historical fill price (the close of the M15 candle that produced the sweep
    signal) -- there is no separate "wait for a resting order to fill" phase for this
    strategy. Every genuine READY record is therefore FILLED by construction, at
    `ready_at`, at the recorded `entry` price. fill_quality = EXACT.

  STOP LOSS / TP1 / TP2
    Read directly from the proposal/decision record (already computed by the live
    strategy engine from stop_loss_range_pct=0.25 and the reference-session box) --
    never recomputed from scratch here, to avoid silently re-deriving strategy logic
    this tool has no authority to change.
    TP1 = OPPOSITE_SESSION_BOUNDARY, 75% of volume, and on fill moves the runner's SL to
    breakeven (basis: the recorded entry price -- the only fill price this contract
    knows about).
    TP2 = fixed 5.0R on the remaining 25%, no trailing.

  SESSION EXIT CUTOFF -- INTERPRETATION, NOT CERTAINTY (see AGENTS.md fail-closed rule)
    strategies/ST_ASIAN_SWEEP_5R_V1.yaml's invalidation_rules.time_invalidation says
    "15:00 GMT ... still functions as a single global cutoff covering both
    session_pairs" as an inline comment, but does not explicitly state whether a
    position opened under ASIAN_LONDON (trade_session 07:00-11:00) is held open past its
    own trade_session end until the global 15:00 mark, or is marked closed at its own
    trade_session end. This tool applies the narrower, pair-own-trade_session-end
    interpretation (11:00 UTC for ASIAN_LONDON, 15:00 UTC for LONDON_NEWYORK) as the
    session-exit cutoff, and records this choice explicitly in every output record's
    `session_exit_cutoff_interpretation` field so it can be revisited/overridden once the
    owner freezes an explicit written contract. This is a measurement-tool assumption,
    not a change to the strategy's own frozen entry/exit rules.

  INTRABAR EVENT ORDERING
    Resolved against M1 candles (the finest timeframe this MT5 terminal exposes) rather
    than the M15 signal timeframe, purely for outcome-sequencing purposes -- this does
    not change how the M15 strategy itself generates signals. If M1 data is unavailable
    for a proposal's window, M15 is used as a fallback with fill_quality/event ordering
    downgraded to APPROXIMATED. If the same candle (at whichever timeframe was actually
    used) contains two conflicting trigger conditions (e.g. both SL and TP1, or both the
    breakeven stop and TP2) the record is classified AMBIGUOUS_SEQUENCE -- never resolved
    by assumption, per instruction.

  COSTS
    Spread/commission/slippage/swap are NOT modeled or deducted. Every realized_R value
    in this tool's output is GROSS of these costs. cost_model fields are all
    NOT_INCLUDED. This must never be reported as net/real-world expectancy.

Usage:
    python scripts/resolve_forward_shadow_outcomes.py [--dry-run] [--json]

    --dry-run   Resolve only a small representative sample (long/short/simple/ambiguous
                if available) and print results without writing the aggregate snapshot
                or the full per-proposal record population.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from mt5.connection import MT5ConnectionError, connect  # noqa: E402
from mt5.market_data import MarketDataError, get_candles  # noqa: E402

STRATEGY_ID = "ST_ASIAN_SWEEP_5R_V1"
STRATEGY_VERSION = "1.1.1"
RESOLUTION_CONTRACT_VERSION = "AG_OUTCOME_RESOLUTION_CONTRACT_V1_DRAFT"

JOURNAL_DIRS = {
    "ASIAN_LONDON": REPO_ROOT / "journal" / "post_asian_pilot",
    "LONDON_NEWYORK": REPO_ROOT / "journal" / "post_london_newyork_pilot",
}

# Pair's own trade_session end, from strategies/ST_ASIAN_SWEEP_5R_V1.yaml session_pairs.
TRADE_SESSION_END_UTC = {
    "ASIAN_LONDON": "11:00",
    "LONDON_NEWYORK": "15:00",
}

OUTPUT_DIR = REPO_ROOT / "artifacts" / "outcome_resolution"
RECORDS_DIR = OUTPUT_DIR / "records"

TP1_VOLUME_PCT = 0.75
TP2_VOLUME_PCT = 0.25
TP2_FIXED_R = 5.0


@dataclass
class ResolvedOutcome:
    proposal_id: str
    strategy_id: str
    strategy_version: str
    symbol: str
    cycle: str
    trading_date: str
    proposal_timestamp: str
    direction: str
    entry: float
    stop_loss: float
    tp1: float
    tp2: float
    session_exit_cutoff_utc: str
    session_exit_cutoff_interpretation: str
    market_data_source: str
    market_data_timeframe: str
    market_data_start: Optional[str]
    market_data_end: Optional[str]
    resolution_contract_version: str
    fill_model: str
    fill_quality: str
    event_sequence: List[dict] = field(default_factory=list)
    terminal_state: str = "UNRESOLVED"
    realized_R: Optional[float] = None
    tp1_R: Optional[float] = None
    cost_status: str = "NOT_INCLUDED"
    evidence_quality: str = "UNVERIFIED"
    note: str = ""


def discover_ready_population() -> List[dict]:
    """Read-only scan of journal/post_asian_pilot and journal/post_london_newyork_pilot
    for genuine ST_ASIAN_SWEEP_5R_V1 v1.1.1 READY records. Never writes to these paths."""
    population: Dict[str, dict] = {}
    for cycle, journal_dir in JOURNAL_DIRS.items():
        decision_path = journal_dir / "decision.json"
        proposal_path = journal_dir / "proposal.json"
        if not decision_path.exists():
            continue
        decisions = json.loads(decision_path.read_text(encoding="utf-8"))
        proposals = json.loads(proposal_path.read_text(encoding="utf-8")) if proposal_path.exists() else {}

        for key, decision in decisions.items():
            if decision.get("status") != "READY":
                continue
            if decision.get("strategy_id") != STRATEGY_ID:
                continue
            if decision.get("strategy_version") != STRATEGY_VERSION:
                continue
            signal = decision.get("signal") or {}
            if not signal or signal.get("direction") not in ("LONG", "SHORT"):
                continue

            setup_id = signal.get("signal_id") or key
            entry = signal.get("entry")
            stop_loss = signal.get("stop_loss")
            box_high = signal.get("box_high")
            box_low = signal.get("box_low")
            direction = signal["direction"]
            if entry is None or stop_loss is None or box_high is None or box_low is None:
                continue

            # TP1 = OPPOSITE_SESSION_BOUNDARY (strategy YAML position_split_and_targets).
            tp1 = box_high if direction == "LONG" else box_low
            risk = (entry - stop_loss) if direction == "LONG" else (stop_loss - entry)
            if risk <= 0:
                continue  # malformed proposal: non-positive risk distance -- exclude, don't guess
            tp2 = entry + TP2_FIXED_R * risk if direction == "LONG" else entry - TP2_FIXED_R * risk

            # Prefer the proposal.json record's own stored tp1/tp2/entry when present --
            # it is the strategy engine's own persisted output, more authoritative than
            # this script's reconstruction from decision.json's signal fields alone.
            proposal = proposals.get(setup_id)
            if proposal and "trade_proposal" in proposal:
                tpx = proposal["trade_proposal"]
                entry = tpx.get("entry", entry)
                stop_loss = tpx.get("stop_loss", stop_loss)
                tp1 = tpx.get("tp1", tp1)
                tp2 = tpx.get("tp2", tp2)

            ready_at = decision.get("ready_at") or signal.get("signal_timestamp")
            if not ready_at:
                continue

            population[setup_id] = {
                "proposal_id": proposal.get("proposal_id") if proposal else setup_id,
                "setup_id": setup_id,
                "strategy_id": STRATEGY_ID,
                "strategy_version": STRATEGY_VERSION,
                "symbol": decision.get("symbol"),
                "cycle": cycle,
                "trading_date": decision.get("trading_date"),
                "ready_at": ready_at,
                "direction": direction,
                "entry": entry,
                "stop_loss": stop_loss,
                "tp1": tp1,
                "tp2": tp2,
            }
    return sorted(population.values(), key=lambda r: (r["ready_at"], r["symbol"]))


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


def resolve_proposal(rec: dict) -> ResolvedOutcome:
    ready_at = _parse_utc(rec["ready_at"])
    cutoff = _session_cutoff(ready_at, rec["cycle"])
    direction = rec["direction"]
    entry = float(rec["entry"])
    stop_loss = float(rec["stop_loss"])
    tp1 = float(rec["tp1"])
    tp2 = float(rec["tp2"])
    risk = (entry - stop_loss) if direction == "LONG" else (stop_loss - entry)
    tp1_R = ((tp1 - entry) / risk) if direction == "LONG" else ((entry - tp1) / risk)

    outcome = ResolvedOutcome(
        proposal_id=rec["proposal_id"],
        strategy_id=rec["strategy_id"],
        strategy_version=rec["strategy_version"],
        symbol=rec["symbol"],
        cycle=rec["cycle"],
        trading_date=rec["trading_date"],
        proposal_timestamp=ready_at.isoformat(),
        direction=direction,
        entry=entry,
        stop_loss=stop_loss,
        tp1=tp1,
        tp2=tp2,
        session_exit_cutoff_utc=cutoff.isoformat(),
        session_exit_cutoff_interpretation=(
            "pair_own_trade_session_end (ASIAN_LONDON=11:00Z / LONDON_NEWYORK=15:00Z) -- "
            "an explicit interpretation of an ambiguous invalidation_rules.time_invalidation "
            "clause, not a certainty; see module docstring"
        ),
        market_data_source="MT5 (VantageMarkets-Demo)",
        market_data_timeframe="M1",
        market_data_start=None,
        market_data_end=None,
        resolution_contract_version=RESOLUTION_CONTRACT_VERSION,
        fill_model="MARKET_at_recorded_entry_price_at_ready_at",
        fill_quality="EXACT",
        tp1_R=tp1_R,
    )

    if cutoff <= ready_at:
        outcome.terminal_state = "INVALID_EVIDENCE"
        outcome.note = "session_exit_cutoff <= ready_at (malformed timestamps) -- excluded from resolution"
        return outcome

    timeframe = "M1"
    try:
        candles = get_candles(rec["symbol"], "M1", ready_at, cutoff)
    except MarketDataError:
        timeframe = "M15"
        try:
            candles = get_candles(rec["symbol"], "M15", ready_at, cutoff)
            outcome.fill_quality = "APPROXIMATED"
        except MarketDataError as exc2:
            outcome.terminal_state = "UNRESOLVED"
            outcome.note = f"DATA_MISSING at both M1 and M15: {exc2.reason_code}"
            return outcome

    outcome.market_data_timeframe = timeframe
    if not candles:
        outcome.terminal_state = "UNRESOLVED"
        outcome.note = "no candles returned in window"
        return outcome

    outcome.market_data_start = candles[0].time.isoformat()
    outcome.market_data_end = candles[-1].time.isoformat()

    is_long = direction == "LONG"

    # --- Phase 1: full position, watching for SL vs TP1 ---
    tp1_index = None
    for i, c in enumerate(candles):
        sl_hit = (c.low <= stop_loss) if is_long else (c.high >= stop_loss)
        tp1_hit = (c.high >= tp1) if is_long else (c.low <= tp1)
        if sl_hit and tp1_hit:
            outcome.terminal_state = "AMBIGUOUS_SEQUENCE"
            outcome.event_sequence.append({
                "time": c.time.isoformat(), "event": "SL_AND_TP1_SAME_CANDLE",
                "candle": {"open": c.open, "high": c.high, "low": c.low, "close": c.close},
            })
            outcome.note = (
                f"{timeframe} candle at {c.time.isoformat()} touches both SL ({stop_loss}) and "
                f"TP1 ({tp1}); true intrabar order cannot be established at this granularity"
            )
            return outcome
        if sl_hit:
            outcome.terminal_state = "RESOLVED_SL"
            outcome.realized_R = -1.0
            outcome.event_sequence.append({
                "time": c.time.isoformat(), "event": "SL",
                "candle": {"open": c.open, "high": c.high, "low": c.low, "close": c.close},
            })
            outcome.evidence_quality = "MODERATE" if timeframe == "M1" else "LOW"
            return outcome
        if tp1_hit:
            tp1_index = i
            outcome.event_sequence.append({
                "time": c.time.isoformat(), "event": "TP1",
                "candle": {"open": c.open, "high": c.high, "low": c.low, "close": c.close},
            })
            break

    if tp1_index is None:
        # Never hit SL or TP1 by session cutoff -- full position marked at last candle close.
        last = candles[-1]
        exit_price = last.close
        realized_R = ((exit_price - entry) / risk) if is_long else ((entry - exit_price) / risk)
        outcome.terminal_state = "RESOLVED_SESSION_EXIT"
        outcome.realized_R = realized_R
        outcome.event_sequence.append({
            "time": last.time.isoformat(), "event": "SESSION_EXIT_FULL_POSITION",
            "exit_price": exit_price,
        })
        outcome.evidence_quality = "MODERATE" if timeframe == "M1" else "LOW"
        return outcome

    # --- Phase 2: runner (25%), SL moved to BE, watching for BE-stop vs TP2 ---
    be_price = entry
    for c in candles[tp1_index:]:
        be_hit = (c.low <= be_price) if is_long else (c.high >= be_price)
        tp2_hit = (c.high >= tp2) if is_long else (c.low <= tp2)
        # On the TP1 candle itself, the BE stop is not armed until AFTER TP1 fires, so a
        # BE touch recorded on that exact same candle is only checked from the next candle
        # onward to avoid crediting a BE-stop that could only follow TP1 within the bar.
        if c is candles[tp1_index]:
            continue
        if be_hit and tp2_hit:
            outcome.terminal_state = "AMBIGUOUS_SEQUENCE"
            outcome.event_sequence.append({
                "time": c.time.isoformat(), "event": "BE_AND_TP2_SAME_CANDLE",
                "candle": {"open": c.open, "high": c.high, "low": c.low, "close": c.close},
            })
            outcome.note = (
                f"{timeframe} candle at {c.time.isoformat()} touches both the BE stop ({be_price}) "
                f"and TP2 ({tp2}) for the runner leg; true intrabar order cannot be established"
            )
            return outcome
        if be_hit:
            outcome.terminal_state = "RESOLVED_TP1_BE"
            outcome.realized_R = TP1_VOLUME_PCT * outcome.tp1_R + TP2_VOLUME_PCT * 0.0
            outcome.event_sequence.append({
                "time": c.time.isoformat(), "event": "RUNNER_BE_STOP",
                "candle": {"open": c.open, "high": c.high, "low": c.low, "close": c.close},
            })
            outcome.evidence_quality = "MODERATE" if timeframe == "M1" else "LOW"
            return outcome
        if tp2_hit:
            outcome.terminal_state = "RESOLVED_TP1_TP2"
            outcome.realized_R = TP1_VOLUME_PCT * outcome.tp1_R + TP2_VOLUME_PCT * TP2_FIXED_R
            outcome.event_sequence.append({
                "time": c.time.isoformat(), "event": "RUNNER_TP2",
                "candle": {"open": c.open, "high": c.high, "low": c.low, "close": c.close},
            })
            outcome.evidence_quality = "MODERATE" if timeframe == "M1" else "LOW"
            return outcome

    # Session cutoff reached with runner still open -- mark runner at last candle close.
    last = candles[-1]
    runner_R = ((last.close - entry) / risk) if is_long else ((entry - last.close) / risk)
    outcome.terminal_state = "RESOLVED_SESSION_EXIT"
    outcome.realized_R = TP1_VOLUME_PCT * outcome.tp1_R + TP2_VOLUME_PCT * runner_R
    outcome.event_sequence.append({
        "time": last.time.isoformat(), "event": "SESSION_EXIT_RUNNER", "exit_price": last.close,
    })
    outcome.evidence_quality = "MODERATE" if timeframe == "M1" else "LOW"
    return outcome


def build_snapshot(outcomes: List[ResolvedOutcome]) -> dict:
    resolved_terminal = {"RESOLVED_SL", "RESOLVED_TP1_BE", "RESOLVED_TP1_TP2", "RESOLVED_SESSION_EXIT"}
    resolved = [o for o in outcomes if o.terminal_state in resolved_terminal]
    ambiguous = [o for o in outcomes if o.terminal_state == "AMBIGUOUS_SEQUENCE"]
    invalid = [o for o in outcomes if o.terminal_state == "INVALID_EVIDENCE"]
    unresolved = [o for o in outcomes if o.terminal_state == "UNRESOLVED"]

    realized = [o.realized_R for o in resolved if o.realized_R is not None]
    wins = [r for r in realized if r > 0.0001]
    losses = [r for r in realized if r < -0.0001]
    be_or_partial = [r for r in realized if -0.0001 <= r <= 0.0001]

    def _seg(records):
        rs = [o.realized_R for o in records if o.terminal_state in resolved_terminal and o.realized_R is not None]
        if not rs:
            return {"trades": 0, "expectancy_R": None, "net_R": None, "win_rate": None}
        w = sum(1 for r in rs if r > 0.0001)
        return {
            "trades": len(rs),
            "wins": w,
            "win_rate": round(w / len(rs), 4),
            "expectancy_R": round(statistics.mean(rs), 4),
            "net_R": round(sum(rs), 4),
        }

    gross_profit = sum(r for r in realized if r > 0)
    gross_loss = sum(r for r in realized if r < 0)
    profit_factor = (gross_profit / abs(gross_loss)) if gross_loss < 0 else (None if gross_profit == 0 else float("inf"))

    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in realized:
        cum += r
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)

    n = len(realized)
    if n == 0:
        classification = "INSUFFICIENT_RESOLVED_EVIDENCE"
    else:
        exp = statistics.mean(realized)
        if exp < -0.05:
            classification = "NEGATIVE_EXPECTANCY_OBSERVED"
        elif abs(exp) <= 0.05:
            classification = "NEAR_ZERO_EXPECTANCY_OBSERVED"
        elif n < 10:
            classification = "POSITIVE_EXPECTANCY_VERY_SMALL_SAMPLE"
        else:
            classification = "POSITIVE_EXPECTANCY_SMALL_SAMPLE"

    snapshot = {
        "schema": "AG_FORWARD_SHADOW_PERFORMANCE_SNAPSHOT_V1",
        "strategy": STRATEGY_ID,
        "version": STRATEGY_VERSION,
        "evidence_class": "FORWARD_SHADOW_RETROSPECTIVE_RESOLUTION",
        "resolution_contract_version": RESOLUTION_CONTRACT_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "date_range": [outcomes[0].trading_date, outcomes[-1].trading_date] if outcomes else None,
        "READY_total": len(outcomes),
        "FILLED": len(outcomes),  # every genuine READY = MARKET fill by contract; see docstring
        "ENTRY_NOT_REACHED": 0,
        "RESOLVED": len(resolved),
        "AMBIGUOUS": len(ambiguous),
        "INVALID_EVIDENCE": len(invalid),
        "UNRESOLVED": len(unresolved),
        "wins": len(wins),
        "losses": len(losses),
        "breakevens_or_partial": len(be_or_partial),
        "fill_rate": 1.0 if outcomes else None,
        "win_rate": round(len(wins) / n, 4) if n else None,
        "win_rate_excluding_BE": round(len(wins) / (len(wins) + len(losses)), 4) if (wins or losses) else None,
        "average_win_R": round(statistics.mean(wins), 4) if wins else None,
        "average_loss_R": round(statistics.mean(losses), 4) if losses else None,
        "expectancy_R": round(statistics.mean(realized), 4) if realized else None,
        "net_R": round(sum(realized), 4) if realized else None,
        "profit_factor": profit_factor,
        "max_drawdown_R": round(max_dd, 4) if realized else None,
        "cost_model": {"spread": "NOT_INCLUDED", "commission": "NOT_INCLUDED", "slippage": "NOT_INCLUDED", "swap": "NOT_INCLUDED"},
        "performance_basis": "GROSS_OF_UNMODELED_COSTS",
        "EURUSD": _seg([o for o in outcomes if o.symbol == "EURUSD"]),
        "GBPUSD": _seg([o for o in outcomes if o.symbol == "GBPUSD"]),
        "ASIAN_LONDON": _seg([o for o in outcomes if o.cycle == "ASIAN_LONDON"]),
        "LONDON_NEWYORK": _seg([o for o in outcomes if o.cycle == "LONDON_NEWYORK"]),
        "sample_size_warning": "VERY_SMALL_SAMPLE" if n < 20 else ("SMALL_SAMPLE" if n < 50 else "MODERATE_SAMPLE"),
        "profitability_classification": classification,
    }
    return snapshot


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="resolve a small representative sample only, do not write files")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    population = discover_ready_population()
    if not population:
        print(json.dumps({"status": "NO_READY_POPULATION_FOUND"}))
        return 1

    try:
        connect()
    except MT5ConnectionError as exc:
        print(json.dumps({"status": "MT5_NOT_CONNECTED", "reason": str(exc)}))
        return 1

    if args.dry_run:
        sample_keys = set()
        by_dir = {"LONG": None, "SHORT": None}
        for rec in population:
            if by_dir.get(rec["direction"]) is None:
                by_dir[rec["direction"]] = rec["setup_id"]
        sample_keys.update(v for v in by_dir.values() if v)
        sample = [r for r in population if r["setup_id"] in sample_keys][:4]
        results = [asdict(resolve_proposal(r)) for r in sample]
        print(json.dumps({"status": "DRY_RUN", "cases": results}, indent=2, default=str))
        return 0

    RECORDS_DIR.mkdir(parents=True, exist_ok=True)
    outcomes: List[ResolvedOutcome] = []
    for rec in population:
        outcome = resolve_proposal(rec)
        outcomes.append(outcome)
        record_path = RECORDS_DIR / f"{rec['setup_id'].replace(':', '_')}.json"
        record_path.write_text(json.dumps(asdict(outcome), indent=2, default=str), encoding="utf-8")

    snapshot = build_snapshot(outcomes)
    (OUTPUT_DIR / "AG_FORWARD_SHADOW_PERFORMANCE_SNAPSHOT_V1.json").write_text(
        json.dumps(snapshot, indent=2, default=str), encoding="utf-8"
    )

    if args.json:
        print(json.dumps(snapshot, indent=2, default=str))
    else:
        print(f"Resolved {len(outcomes)} proposals -> {OUTPUT_DIR}")
        print(json.dumps({k: v for k, v in snapshot.items() if k not in ("EURUSD", "GBPUSD", "ASIAN_LONDON", "LONDON_NEWYORK")}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
