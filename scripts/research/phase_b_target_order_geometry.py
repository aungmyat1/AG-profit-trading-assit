"""Phase B (R2) carry-in B-TGT-ORDER -- geometry-only TP1 vs TP2 counts per stop option.

Read-only. Uses only recorded sweeps already committed in this repository; computes no
win/loss, no R outcome, no cost. For each recorded sweep it rebuilds the two targets the
frozen ST_ASIAN_SWEEP_5R_V1@1.1.1 contract declares (leg 1 OPPOSITE_SESSION_BOUNDARY,
leg 2 FIXED_R_MULTIPLE 5.0) under each stop option and reports whether TP1 lies beyond
TP2 (LONG: TP1 > TP2, SHORT: TP1 < TP2):

    ENGINE_WICK      stop = sweep-candle wick extreme (what the frozen engine does)
    SPEC_RANGE_25    stop distance = 0.25 x reference range (what the YAML declares)

Two entry rules are crossed with the two stop options:

    ENGINE_BODY_EDGE  entry = min/max(open, close) of the sweep candle (frozen engine)
    SPEC_BODY_CLOSE   entry = close of the sweep candle (YAML entry_level); only where the
                      signal candle's close is recorded (not in the R5 records)

Sources:
    R5_FORWARD_SHADOW  artifacts/outcome_resolution/records/*.json (13) + box from
                       artifacts/candidate_research/model_a_session_range_25/records/
    PASS_B_REPLAY      docs/status/evidence/pass_b_replay_b92f529_0740Z/... tickets (3)
    FIXTURE_EURUSD     tests/fixtures/manual_ticket/EURUSD_M15_recorded.csv via v1_tickets.fx

    python scripts/research/phase_b_target_order_geometry.py [--json OUT]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

R_MULT, RANGE_PCT = 5.0, 0.25


def _geometry(long, entry, wick_sl, box_high, box_low):
    tp1 = box_high if long else box_low
    out = {}
    for name, risk in (("ENGINE_WICK", abs(entry - wick_sl)), ("SPEC_RANGE_25", RANGE_PCT * (box_high - box_low))):
        tp2 = entry + (R_MULT if long else -R_MULT) * risk
        out[name] = {"risk": round(risk, 6), "tp1": tp1, "tp2": round(tp2, 6),
                     "tp1_R": round(abs(tp1 - entry) / risk, 3) if risk else None,
                     "tp1_beyond_tp2": ((tp1 > tp2) if long else (tp1 < tp2)) if risk else None}
    return out


def _row(source, key, direction, entry, wick_sl, box_high, box_low, close=None):
    long = direction == "LONG"
    return {"source": source, "key": key, "direction": direction, "entry": entry, "sweep_close": close,
            "box_high": box_high, "box_low": box_low, "entry_inside_box": box_low <= entry <= box_high,
            "ENGINE_BODY_EDGE": _geometry(long, entry, wick_sl, box_high, box_low),
            "SPEC_BODY_CLOSE": _geometry(long, close, wick_sl, box_high, box_low) if close is not None else None}


def r5_rows():
    rows = []
    for f in sorted(glob.glob(str(ROOT / "artifacts/outcome_resolution/records/*.json"))):
        r = json.load(open(f, encoding="utf-8"))
        c = json.load(open(ROOT / "artifacts/candidate_research/model_a_session_range_25/records"
                           / (r["proposal_id"].replace(":", "_") + ".json"), encoding="utf-8"))
        rows.append(_row("R5_FORWARD_SHADOW", r["proposal_id"], r["direction"], r["entry"], r["stop_loss"],
                         c["box_high"], c["box_low"]))
    return rows


def pass_b_rows():
    p = (ROOT / "docs/status/evidence/pass_b_replay_b92f529_0740Z/journal/ticket_delivery/manual/tickets"
         / "2026-10-06.jsonl")
    rows = []
    for line in p.open(encoding="utf-8"):
        t = json.loads(line)
        if t.get("direction"):
            trig = next(c for c in t["rule_evidence"] if c["id"] == "R.entry_trigger")["value"]
            rows.append(_row("PASS_B_REPLAY", f"{t['symbol']}:{t['cycle']}:{t['session_date']}", t["direction"],
                             t["entry"], t["stop_loss"], t["box"]["high"], t["box"]["low"], close=trig["close"]))
    return rows


def fixture_rows():
    from strategy_engine.session import Candle
    from v1_tickets.fx import build_fx_ticket, session_windows_utc
    path = ROOT / "tests/fixtures/manual_ticket/EURUSD_M15_recorded.csv"
    with path.open(encoding="utf-8") as f:
        candles = [Candle(time=dt.datetime.fromisoformat(r["timestamp_utc"]).replace(tzinfo=dt.timezone.utc), open=float(r["open"]), high=float(r["high"]),
                          low=float(r["low"]), close=float(r["close"])) for r in csv.DictReader(f)]
    rows = []
    for day in sorted({c.time.date() for c in candles}):
        for cycle, bars in (("ASIAN_LONDON", 24), ("LONDON_NEWYORK", 20)):
            w = session_windows_utc(day)[cycle]
            ref = [c for c in candles if w["ref"][0] <= c.time < w["ref"][1]]
            post = [c for c in candles if w["trade"][0] <= c.time < w["trade"][1]]
            if len(ref) < bars or not post:
                continue
            now = w["trade"][1]
            t = build_fx_ticket("EURUSD", cycle, day, ref, bars, post, data_source="FIXTURE", evaluated_at=now)
            if t.get("direction") and t.get("setup") == "SWEEP":
                sig = next(c for c in post if c.time.isoformat() == t["signal_timestamp"])
                rows.append(_row("FIXTURE_EURUSD", f"EURUSD:{cycle}:{day}", t["direction"], t["entry"],
                                 t["stop_loss"], t["box"]["high"], t["box"]["low"], close=sig.close))
    return rows


def summarise(rows):
    out = {}
    for src in sorted({r["source"] for r in rows}) + ["ALL"]:
        sel = [r for r in rows if src in ("ALL", r["source"])]
        out[src] = {"sweeps": len(sel), "engine_entry_outside_box": sum(not r["entry_inside_box"] for r in sel)}
        for entry in ("ENGINE_BODY_EDGE", "SPEC_BODY_CLOSE"):
            have = [r for r in sel if r[entry] is not None]
            for opt in ("ENGINE_WICK", "SPEC_RANGE_25"):
                v = [r[entry][opt]["tp1_beyond_tp2"] for r in have]
                out[src][f"{entry}+{opt}"] = {"evaluable": len(have), "tp1_beyond_tp2": sum(x is True for x in v),
                                              "zero_stop": sum(x is None for x in v)}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    rows = r5_rows() + pass_b_rows() + fixture_rows()
    result = {"schema": "AG_PHASE_B_TARGET_ORDER_GEOMETRY_V1", "strategy": "ST_ASIAN_SWEEP_5R_V1@1.1.1",
              "basis": "GEOMETRY_ONLY_NO_OUTCOME", "summary": summarise(rows), "rows": rows}
    text = json.dumps(result, indent=1, sort_keys=True)
    if a.json:
        Path(a.json).write_text(text + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
