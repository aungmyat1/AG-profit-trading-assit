"""Frozen-engine parity self-check on seeded synthetic M15 candles (no market data).

    python -m research.attribution.parity_check

Asserts: (1) instrumentation with relax=() returns a result identical to a plain frozen
`run_replay` call; (2) the ALL_RELAXED ledger contains every frozen-baseline fill;
(3) every ledger row carries a verdict for every gate. Prints a JSON summary.
Runs in its own process (frozen_engine.load() shadows current src packages).
"""
from __future__ import annotations

import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from research.attribution import frozen_engine, ledger  # noqa: E402


def main(days: int = 12) -> dict:
    replay = frozen_engine.load()
    cfg = frozen_engine.load_config()
    from market_intelligence.models import MarketBiasResult
    from strategy_engine.session.candles import Candle

    rng = random.Random(7)
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    price, m15 = 1.10, []
    for i in range(96 * (days + 6)):
        o = price
        price += rng.gauss(0, 0.0006)
        m15.append(Candle(t0 + timedelta(minutes=15 * i), o, max(o, price) + abs(rng.gauss(0, 0.0003)),
                          min(o, price) - abs(rng.gauss(0, 0.0003)), price))
    summary = {"cycles": 0, "baseline_fills": 0, "ledger_rows": 0, "baseline_rows": 0}
    for day in range(5, 5 + days):
        d = (t0 + timedelta(days=day)).date()
        if d.weekday() > 4:
            continue
        for pair in ("ASIAN_LONDON", "LONDON_NEWYORK"):
            ref = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
            bias = MarketBiasResult(bias="BULLISH", confidence="HIGH", decision_cycle_id="SYNTH",
                                    symbol="EURUSD", decision_time=ref, htf_structure="",
                                    mtf_alignment="", liquidity_context="", session_context="",
                                    reason_codes=(), model_version="SYNTH", input_fingerprint="SYNTH")
            plain = replay.run_replay(m15, cfg, "EURUSD", pair, d, 0.0001, bias_result=bias).to_dict()
            base, _ = ledger.run_cycle(replay, m15, cfg, "EURUSD", pair, d, 0.0001, bias_result=bias)
            assert base.to_dict() == plain, f"BASELINE_PARITY_FAIL {d} {pair}"
            rel, rec = ledger.run_cycle(replay, m15, cfg, "EURUSD", pair, d, 0.0001, bias_result=bias,
                                        relax=ledger.ALL_RELAXED)
            rows = ledger.ledger_rows(rel, rec, base, 0.0001, "BULLISH/HIGH")
            in_base = [r for r in rows if r["in_frozen_baseline"]]
            assert len(in_base) == len(base.accepted_setups), "BASELINE_FILL_MISSING_FROM_LEDGER"
            assert all(r[g] for r in rows for g in ledger.GATES), "GATE_VERDICT_MISSING"
            summary["cycles"] += 1
            summary["baseline_fills"] += len(base.accepted_setups)
            summary["ledger_rows"] += len(rows)
            summary["baseline_rows"] += len(in_base)
    summary["status"] = "PASS"
    return summary


if __name__ == "__main__":
    print(json.dumps(main()))
