"""AGP-C25 OSS differential verification (evidence only; 60 committed recorded days).

Oracles are REFERENCE evidence, never authority (AGENTS.md OSS-FIRST). Nothing here changes an engine,
contract, registry or flag. Inputs are committed recorded fixtures only; no network, no MT5.

1. Geometry/outcome oracle: every emitted ASW v1.1.3 and CCFD 1.0.0 signal is resolved twice on the same bar
   path with identical entry / SL / TP1 / horizon -- by the repo resolver (v1_tickets.outcome.resolve_levels)
   and by backtesting.py (AGPL-3.0, research-only, never imported by runtime code). Range geometry (ASW
   session box, CCFD previous-UTC-day reference) is cross-checked with pandas-ta donchian.
2. Sweep oracle (CCFD): smartmoneyconcepts previous_high_low("1D") / swing_highs_lows vs our sweep and MSS
   evidence.
3. Causality fuzz, owner/PM ruling 2026-10-14: L3 = (a) bars after the signal close removed -> identical to the
   emitted signal, (b) bars strictly after the signal close perturbed, incl. the forming bar -> identical.
   (c) signal bar perturbed is L4, not L3: recomputed levels must equal the contract formulas on the perturbed
   OHLC (ASW). Harness history: docs/status/C25_HARNESS_CHANGE_LOG.md.

    python scripts/c25_oss_differential.py --out artifacts/oss_differential/c25_report.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import random
import runpy
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

UTC = dt.timezone.utc
M5, M15 = dt.timedelta(minutes=5), dt.timedelta(minutes=15)
SEED = 20261014
V113 = "strategies/ST_ASIAN_SWEEP_5R_V1_1_1_3.yaml"
ASW_SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD")
CCFD_SYMBOLS = ("BTCUSD", "ETHUSD")
CCFD_COUNTS = {"D1": 50, "H1": 100, "M15": 96, "M5": 576}
CCFD_HORIZON = dt.timedelta(hours=24)        # identical on both sides; the contract defines no trade horizon
REL_TOL = 1e-9
DATA_INSUFFICIENT_60D = [
    {"family": "ASW v1.1.3", "scope": "USDJPY x ASIAN_LONDON/LONDON_NEWYORK"},
    {"family": "ASW v1.1.3", "scope": "XAUUSD x ASIAN_LONDON/LONDON_NEWYORK"},
    {"family": "CCFD 1.0.0", "scope": "BTCUSD LONG"},
]


# ------------------------------------------------------------------------------------ shared oracle

def oracle_outcome(direction: str, entry: float, sl: float, tp: float, entry_time: dt.datetime,
                   bars: List[Any], horizon: dt.datetime, tf: dt.timedelta) -> Dict[str, Any]:
    """backtesting.py resolution. Bar 0 is a synthetic anchor O=H=L=C=entry at the entry time (identical
    entry by construction; trade_on_close fills there), then the real bars with open in (entry_time, horizon)."""
    import pandas as pd
    from backtesting import Backtest, Strategy

    path = [b for b in bars if entry_time < b.time < horizon]
    # backtesting.py never calls next() on the first bar, so two identical anchor bars are used: the order is
    # placed on the first next() call and filled at the anchor close (= entry) via trade_on_close.
    rows = [{"time": entry_time - dt.timedelta(seconds=2), "Open": entry, "High": entry, "Low": entry, "Close": entry},
            {"time": entry_time - dt.timedelta(seconds=1), "Open": entry, "High": entry, "Low": entry, "Close": entry}]
    rows += [{"time": b.time, "Open": b.open, "High": b.high, "Low": b.low, "Close": b.close} for b in path]
    if path:   # backtesting.py never processes its final row: a flat terminal row at the horizon lets
        last_close = path[-1].close   # finalize_trades exit at the last real bar's close (= repo EXPIRY price)
        rows.append({"time": horizon, "Open": last_close, "High": last_close, "Low": last_close, "Close": last_close})
    if len(rows) < 3:
        return {"result": "DATA_INSUFFICIENT"}
    frame = pd.DataFrame(rows).set_index("time")
    frame.index = pd.DatetimeIndex(frame.index)
    long = direction == "LONG"

    class Once(Strategy):
        def init(self):
            self.rejected, self.placed = None, False

        def next(self):
            if not self.placed:
                self.placed = True
                try:
                    (self.buy if long else self.sell)(size=1, sl=sl, tp=tp)
                except ValueError as exc:
                    self.rejected = str(exc)
            # no manual exit: finalize_trades closes an open trade at the last bar's close (= horizon expiry)

    bt = Backtest(frame, Once, cash=1e12, commission=0.0, spread=0.0, trade_on_close=True,
                  exclusive_orders=True, finalize_trades=True)
    stats = bt.run()
    trades = stats["_trades"]
    if trades.empty:
        return {"result": "ORACLE_REJECT", "reason": getattr(stats["_strategy"], "rejected", None)}
    t = trades.iloc[0]
    exit_price, entry_price = float(t["ExitPrice"]), float(t["EntryPrice"])
    risk = abs(entry - sl)
    sign = 1.0 if long else -1.0
    if math.isclose(exit_price, tp, rel_tol=REL_TOL):
        result = "TP1"
    elif math.isclose(exit_price, sl, rel_tol=REL_TOL):
        result = "SL"
    else:
        result = "EXPIRY"
    return {"result": result, "entry_price": entry_price, "exit_price": exit_price,
            "exit_time": pd.Timestamp(t["ExitTime"]).isoformat(), "gross_R": round(sign * (exit_price - entry) / risk, 4)}


def compare(engine: Dict[str, Any], oracle: Dict[str, Any], *, direction: str = "", tp: float = 0.0) -> Dict[str, Any]:
    e, o = engine.get("result"), oracle.get("result")
    gap_tp = (e == "TP1" and o == "EXPIRY" and oracle.get("exit_time", "")[:16] == (engine.get("bar") or "")[:16]
              and ((oracle.get("exit_price", tp) > tp) if direction == "LONG" else (oracle.get("exit_price", tp) < tp)))
    if gap_tp:
        return {"class": "SPEC_DIFFERENCE",
                "note": "bar gapped through TP1: backtesting.py fills at the bar open, repo resolver books TP1"}
    if e == "DATA_INSUFFICIENT" and engine.get("reason") == "BARS_END_BEFORE_HORIZON":
        return {"class": "SPEC_DIFFERENCE",
                "note": "dataset ends before the horizon: repo resolver refuses, backtesting.py finalizes at last bar"}
    if e == "AMBIGUOUS":
        cls = "SPEC_DIFFERENCE"       # repo resolver never guesses a same-bar TP/SL; backtesting.py picks one
        note = "TP1 and SL in the same bar: repo=AMBIGUOUS (by design), oracle=" + str(o)
    elif e == o and (e not in ("TP1", "SL", "EXPIRY")
                     or math.isclose(engine.get("gross_R") or 0.0, oracle.get("gross_R") or 0.0, abs_tol=1e-3)):
        cls, note = "AGREE", ""
    elif o == "ORACLE_REJECT":
        cls, note = "ORACLE_DEFECT", f"backtesting.py rejected the bracket: {oracle.get('reason')}"
    else:
        cls, note = "UNCLASSIFIED_DIVERGENCE", f"repo={e} oracle={o}"
    return {"class": cls, "note": note}


def donchian(highs: List[float], lows: List[float]) -> Dict[str, float]:
    import pandas as pd
    import pandas_ta as ta
    frame = ta.donchian(pd.Series(highs, dtype=float), pd.Series(lows, dtype=float),
                        lower_length=len(lows), upper_length=len(highs))
    row = frame.iloc[-1]
    return {"high": float(row.filter(like="DCU").iloc[0]), "low": float(row.filter(like="DCL").iloc[0])}


# ------------------------------------------------------------------------------------------ ASW

def _asw_harness():
    g = runpy.run_path(str(ROOT / "scripts" / "asw_v112_60d_replay.py"), run_name="c25_asw")
    h = g["h"]
    h.use_candidate(V113, "1.1.3")
    h.SYMBOLS = dict(h.D60_SYMBOLS)
    return h


def _signal_key(t: Dict[str, Any]) -> tuple:
    return (t.get("direction"), t.get("signal_timestamp"), t.get("entry"), t.get("stop_loss"),
            tuple(x["price"] for x in t.get("targets") or []))


def run_asw(rng: random.Random) -> Dict[str, Any]:
    from v1_tickets.outcome import resolve_levels
    from v1_tickets.target_geometry import geometry_violation
    h = _asw_harness()
    rows, fuzz, gated = [], [], []
    for symbol in ASW_SYMBOLS:
        candles = h.load_candles(symbol)
        by_day: Dict[str, list] = {}
        for c in candles:
            by_day.setdefault(c.time.date().isoformat(), []).append(c)
        for cycle in h.CYCLES:
            for ds in h.fixture_days(candles):
                day = dt.date.fromisoformat(ds)
                w, now, session, post = h.split(by_day[ds], cycle, day)
                t = h.ticket(cycle, day, session, post, now, symbol=symbol)
                if not (t.get("direction") and t.get("entry") is not None and t.get("stop_loss") is not None
                        and t.get("targets") and t.get("signal_timestamp")):
                    continue
                signal_open = dt.datetime.fromisoformat(t["signal_timestamp"])
                signal_close = signal_open + M15
                tp1 = t["targets"][0]["price"]
                horizon = dt.datetime.combine(day, dt.time(15, 0), tzinfo=UTC)   # time_invalidation_gmt 15:00
                engine = resolve_levels(direction=t["direction"], entry=t["entry"], sl=t["stop_loss"], tp1=tp1,
                                        start=signal_close, horizon=horizon, bars=candles, tf=M15,
                                        now=horizon + M15, cost_r=None)
                oracle = oracle_outcome(t["direction"], t["entry"], t["stop_loss"], tp1, signal_open, candles,
                                        horizon, M15)
                comparison = compare(engine, oracle, direction=t["direction"], tp=tp1)
                if not all(h.geometry_ok(t).values()):     # the engine's own target-order gate blocks this ticket
                    tp2 = next((x["price"] for x in t["targets"] if x.get("leg") == 2), None)
                    reason = geometry_violation(t["entry"], t["stop_loss"], tp1, tp2, t["direction"])
                    if reason == "TP1_NOT_BEYOND_ENTRY" and oracle.get("result") == "ORACLE_REJECT":
                        comparison = {"class": "SPEC_DIFFERENCE",
                                      "note": "bracket invalid by construction (TP1 not beyond entry); engine blocks it"}
                    gated.append({"symbol": symbol, "cycle": cycle, "day": ds, "geometry": h.geometry_ok(t),
                                  "signal_timestamp": t["signal_timestamp"], "direction": t["direction"],
                                  "entry": t["entry"], "sl": t["stop_loss"], "tp1": tp1, "tp2": tp2,
                                  "guard_reason": reason, "engine": engine, "oracle": oracle,
                                  "comparison_supplementary": comparison})
                    fuzz.append(_asw_fuzz(h, symbol, cycle, day, session, post, t, signal_open, rng))
                    continue
                box = donchian([c.high for c in session], [c.low for c in session])
                box_ok = (math.isclose(box["high"], t["box"]["high"], abs_tol=1e-9)
                          and math.isclose(box["low"], t["box"]["low"], abs_tol=1e-9))
                rows.append({"symbol": symbol, "cycle": cycle, "day": ds, "direction": t["direction"],
                             "entry": t["entry"], "sl": t["stop_loss"], "tp1": tp1, "engine": engine,
                             "oracle": oracle,
                             "comparison": comparison,
                             "box_engine": t["box"], "box_pandas_ta": box, "box_agree": box_ok})
                fuzz.append(_asw_fuzz(h, symbol, cycle, day, session, post, t, signal_open, rng))
    return {"rows": rows, "fuzz": fuzz, "engine_gated_geometry": gated}


def _asw_fuzz(h, symbol, cycle, day, session, post, t, signal_open, rng) -> Dict[str, Any]:
    from strategy_engine.session import Candle
    key = _signal_key(t)
    signal_close = signal_open + M15
    upto = [c for c in post if c.time <= signal_open]
    truncated = h.ticket(cycle, day, session, upto, signal_close, symbol=symbol)
    a = _signal_key(truncated) == key
    later = [c for c in post if c.time > signal_open]
    mutated = [Candle(c.time, *(round(p * (1 + rng.uniform(-0.002, 0.002)), 6) for p in (c.open, c.high, c.low, c.close)))
               for c in later]
    mutated = [Candle(c.time, c.open, max(c.open, c.high, c.low, c.close), min(c.open, c.high, c.low, c.close), c.close)
               for c in mutated]
    future = h.ticket(cycle, day, session, upto + mutated, h.split([], cycle, day)[1], symbol=symbol)
    b = _signal_key(future) == key
    # (b) also covers the latest (forming) bar: perturb the last bar of the full input when it opens after the
    # signal bar close (owner/PM ruling 2026-10-14).
    full_now = h.split([], cycle, day)[1]
    if post[-1].time <= signal_open:
        post_cls = "NOT_APPLICABLE_SIGNAL_BAR_IS_LAST"
    else:
        lb = post[-1]
        k = 1 + rng.uniform(-0.002, 0.002)
        o, c = lb.open * k, lb.close * (1 + rng.uniform(-0.002, 0.002))
        lp = Candle(lb.time, o, max(o, c, lb.high * k), min(o, c, lb.low * k), c)
        post_cls = ("IDENTICAL" if _signal_key(h.ticket(cycle, day, session, post[:-1] + [lp], full_now,
                                                         symbol=symbol)) == key else "CHANGED")
    # (c) signal bar perturbed (range shrunk 25%): not an L3 test (owner/PM ruling). L4: the recomputed levels must
    # equal the contract formulas applied to the perturbed OHLC.
    last = upto[-1]
    shrink = (last.high - last.low) * 0.25
    pert = Candle(last.time, last.open, last.high - shrink, last.low + shrink, last.close)
    pert = Candle(pert.time, pert.open, max(pert.open, pert.high, pert.close), min(pert.open, pert.low, pert.close),
                  pert.close)
    perturbed = h.ticket(cycle, day, session, upto[:-1] + [pert], signal_close, symbol=symbol)
    pk = _signal_key(perturbed)
    sig_cls = "IDENTICAL" if pk == key else ("ABSENT" if not perturbed.get("direction") else "CHANGED")
    names = ("direction", "signal_timestamp", "entry", "stop_loss", "targets")
    changed = [n for n, x, y in zip(names, key, pk) if x != y] if sig_cls == "CHANGED" else []
    l4 = _asw_formula_check(t, perturbed, pert, symbol)
    l3 = a and b and post_cls != "CHANGED"
    return {"case": f"{symbol}:{cycle}:{day}", "truncation_identical": a, "future_perturbation_identical": b,
            "forming_bar_perturbation": post_cls, "l3_verdict": "PASS" if l3 else "FAIL",
            "signal_bar_perturbation": sig_cls, "signal_bar_changed_fields": changed, "signal_bar_l4": l4,
            "verdict": "PASS" if l3 and l4["status"] == "PASS" else "FAIL"}


def _asw_formula_check(base: Dict[str, Any], t: Dict[str, Any], bar: Any, symbol: str) -> Dict[str, Any]:
    """L4 on the perturbed signal bar: contract formulas (ST_ASIAN_SWEEP_5R_V1_1_1_3.yaml) on its OHLC.
    entry = SWEEP_CANDLE_BODY_EDGE (:158/:163), stop = SWEEP_CANDLE_WICK_EXTREME (:170), risk > 0 (:171),
    TP1 = OPPOSITE_SESSION_BOUNDARY, TP2 = entry +/- 5R (:181-:191); trigger = entry_rules condition (:156/:161)."""
    from v1_tickets.fx import _digits
    direction = base["direction"]
    long = direction == "LONG"
    hi, lo = base["box"]["high"], base["box"]["low"]
    trigger = (bar.low < lo and bar.close > lo) if long else (bar.high > hi and bar.close < hi)
    entry_f = min(bar.open, bar.close) if long else max(bar.open, bar.close)
    sl_f = bar.low if long else bar.high
    risk_f = (entry_f - sl_f) if long else (sl_f - entry_f)
    if not t.get("direction"):
        if not trigger:
            return {"status": "PASS", "outcome": "ABSENT", "reason": "TRIGGER_NOT_MET_ON_PERTURBED_BAR"}
        if risk_f <= 0:
            return {"status": "PASS", "outcome": "ABSENT", "reason": "NON_POSITIVE_RISK_ON_PERTURBED_BAR"}
        return {"status": "FAIL", "outcome": "ABSENT", "reason": "ABSENT_BUT_CONTRACT_TRIGGER_HOLDS"}
    digits = _digits(symbol)
    tol = 0.5 * 10.0 ** -digits + 1e-9 if digits is not None else 1e-9    # result is the formula rounded to digits
    same = t.get("direction") == direction and t.get("signal_timestamp") == base.get("signal_timestamp")
    if t.get("setup") == "RANGE":
        # No qualified sweep on the perturbed bar (risk <= 0 is no setup, :171), so the engine evaluates the
        # RANGE_REJECTION branch (:147-:150; entry = box boundary, stop = candle extreme), which the contract
        # declares ticket FAIL_CLOSED (ENTRY_LEVEL_NOT_MARKET_AT_SIGNAL): no tradable ticket, targets not defined.
        rejection = ((bar.low <= lo and bar.close > lo and bar.close > bar.open) if long
                     else (bar.high >= hi and bar.close < hi and bar.close < bar.open))
        expected = {"entry": lo if long else hi, "stop_loss": bar.low if long else bar.high}
        got = {"entry": t.get("entry"), "stop_loss": t.get("stop_loss")}
        checks = {k: got[k] is not None and abs(got[k] - expected[k]) <= tol for k in expected}
        checks.update(sweep_not_qualified=not trigger or risk_f <= 0, range_rejection_holds=rejection,
                      direction_and_time_unchanged=same)
        return {"status": "PASS" if all(checks.values()) else "FAIL", "outcome": "RANGE_BRANCH_FAIL_CLOSED",
                "checks": checks, "expected": {k: round(v, 8) for k, v in expected.items()}, "got": got}
    tp = {x["leg"]: x["price"] for x in t.get("targets") or []}
    expected = {"entry": entry_f, "stop_loss": sl_f, "tp1": hi if long else lo,
                "tp2": entry_f + (5.0 if long else -5.0) * risk_f}
    got = {"entry": t.get("entry"), "stop_loss": t.get("stop_loss"), "tp1": tp.get(1), "tp2": tp.get(2)}
    checks = {k: got[k] is not None and abs(got[k] - expected[k]) <= tol * (5 if k == "tp2" else 1)
              for k in expected}
    checks["direction_and_time_unchanged"] = same
    checks["trigger_holds"] = trigger
    return {"status": "PASS" if all(checks.values()) else "FAIL", "outcome": "PRESENT", "checks": checks,
            "expected": {k: round(v, 8) for k, v in expected.items()}, "got": got}


# ----------------------------------------------------------------------------------------- CCFD

def _ccfd():
    g = runpy.run_path(str(ROOT / "scripts" / "ccfd_sweep_retest_replay.py"), run_name="c25_ccfd")
    return g


CCFD_EXCLUDED: List[Dict[str, Any]] = []


def ccfd_signals(g) -> List[Dict[str, Any]]:
    path = g["DATASETS"]["recorded_60d"][1] / "tickets.jsonl"
    seen, out = set(), []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        tk = json.loads(line).get("ticket") or {}
        ev = (tk.get("engine_result") or {}).get("evidence") or {}
        if tk.get("entry") is None or not ev.get("retest"):
            continue
        result = (tk.get("engine_result") or {}).get("result")
        if result != "ENTRY_VALID":        # not an emitted signal (rules.py RESULT_ENTRY_VALID)
            key = ("EXCLUDED", tk["symbol"], tk["direction"], ev["retest"]["candle_time_utc"], result)
            if key not in seen:
                seen.add(key)
                CCFD_EXCLUDED.append({"symbol": tk["symbol"], "direction": tk["direction"],
                                      "retest_time": ev["retest"]["candle_time_utc"], "engine_result": result})
            continue
        key = (tk["symbol"], tk["direction"], ev["retest"]["candle_time_utc"])
        if key in seen:
            continue
        seen.add(key)
        out.append({"symbol": tk["symbol"], "direction": tk["direction"], "entry": tk["entry"],
                    "now": json.loads(line).get("now") or tk.get("evaluated_at"),
                    "sl": tk["stop_loss"], "tp1": tk["tp1"], "retest_time": ev["retest"]["candle_time_utc"],
                    "evidence": ev})
    return sorted(out, key=lambda s: (s["symbol"], s["retest_time"]))


def run_ccfd(rng: random.Random) -> Dict[str, Any]:
    from v1_tickets.outcome import resolve_levels
    g = _ccfd()
    base = g["DATASETS"]["recorded_60d"][0]
    data = {s: g["load_symbol"](s, base) for s in CCFD_SYMBOLS}
    rows, sweeps, fuzz = [], [], []
    for s in ccfd_signals(g):
        bars = data[s["symbol"]]["bars"]["M5"]
        retest = dt.datetime.fromisoformat(s["retest_time"])
        start = retest + M5
        horizon = start + CCFD_HORIZON
        engine = resolve_levels(direction=s["direction"], entry=s["entry"], sl=s["sl"], tp1=s["tp1"], start=start,
                                horizon=horizon, bars=bars, tf=M5, now=horizon + M5, cost_r=None)
        oracle = oracle_outcome(s["direction"], s["entry"], s["sl"], s["tp1"], retest, bars, horizon, M5)
        ref = s["evidence"]["reference"]
        day = dt.datetime.combine(retest.date() - dt.timedelta(days=1), dt.time(0), tzinfo=UTC)
        prev = [b for b in bars if day <= b.time < day + dt.timedelta(days=1)]
        dc = donchian([b.high for b in prev], [b.low for b in prev])
        rows.append({**{k: s[k] for k in ("symbol", "direction", "entry", "sl", "tp1", "retest_time")},
                     "engine": engine, "oracle": oracle,
                     "comparison": compare(engine, oracle, direction=s["direction"], tp=s["tp1"]),
                     "reference_engine": {"high": ref["high"], "low": ref["low"]}, "reference_pandas_ta": dc,
                     "reference_agree": math.isclose(dc["high"], ref["high"], abs_tol=1e-9)
                     and math.isclose(dc["low"], ref["low"], abs_tol=1e-9)})
        sweeps.append(_smc_sweep(s, bars))
        fuzz.append(_ccfd_fuzz(g, data[s["symbol"]], s, rng))
    return {"rows": rows, "sweeps": sweeps, "fuzz": fuzz,
            "excluded_not_entry_valid": sorted(CCFD_EXCLUDED, key=lambda x: (x["symbol"], x["retest_time"]))}


def _smc_sweep(s: Dict[str, Any], bars: List[Any]) -> Dict[str, Any]:
    import pandas as pd
    from smartmoneyconcepts import smc
    sweep, mss = s["evidence"]["sweep"], s["evidence"]["mss"]
    st = dt.datetime.fromisoformat(sweep["candle_time_utc"])
    window = [b for b in bars if st - dt.timedelta(days=2) <= b.time <= st + dt.timedelta(hours=6)]
    df = pd.DataFrame([{"open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": 0.0}
                       for b in window], index=pd.DatetimeIndex([b.time for b in window]))
    phl = smc.previous_high_low(df, time_frame="1D")
    i = list(df.index).index(pd.Timestamp(st))
    high_sweep = sweep["direction"] == "HIGH_SWEEP"
    level = float(phl["PreviousHigh" if high_sweep else "PreviousLow"].iloc[i])
    broken = bool(phl["BrokenHigh" if high_sweep else "BrokenLow"].iloc[i])
    level_agree = math.isclose(level, sweep["swept_level"], rel_tol=1e-6)   # smc returns float32 levels
    shl = smc.swing_highs_lows(df, swing_length=5)
    mss_t = dt.datetime.fromisoformat(mss["confirmed_at_utc"])
    swings = [float(v) for t, v in zip(df.index, shl["Level"]) if not pd.isna(v) and t <= pd.Timestamp(mss_t)]
    mss_agree = any(math.isclose(v, mss["broken_swing_price"], rel_tol=1e-6) for v in swings)
    if level_agree and broken:
        cls = "AGREE"
    elif not level_agree:
        cls = "SPEC_DIFFERENCE"     # smc previous-day boundary/resample vs our PREVIOUS_UTC_DAY 288-bar reference
    else:
        cls = "SPEC_DIFFERENCE"     # smc BrokenHigh/Low flags a break from the day's open, not per-bar sweep
    return {"signal": f"{s['symbol']}:{s['direction']}:{s['retest_time']}", "sweep_level_engine": sweep["swept_level"],
            "sweep_level_smc": level, "smc_broken_flag": broken, "sweep_class": cls,
            "mss_swing_in_smc_swings": mss_agree,
            "mss_class": "AGREE" if mss_agree else "SPEC_DIFFERENCE"}   # swing_length/definition differ by design


def _ccfd_fuzz(g, data: Dict[str, Any], s: Dict[str, Any], rng: random.Random) -> Dict[str, Any]:
    import copy

    from market_structure.config import load_market_structure_config
    from strategy_engine.session import Candle
    cfg = load_market_structure_config()
    retest = dt.datetime.fromisoformat(s["retest_time"])
    now = retest + M5                                   # the signal (retest) bar close: owner L3 definition
    ticket_now = dt.datetime.fromisoformat(s["now"])    # when the recorded ticket was emitted (supplementary)

    def sig(d, now=now):
        x = g["closed_inputs"](d, now, CCFD_COUNTS)
        r = g["engine"](s["symbol"], now, x, cfg)
        plan = (r.get("evidence") or {}).get("target_plan") or {}
        rt = ((r.get("evidence") or {}).get("retest") or {}).get("candle_time_utc")
        return (r.get("result"), plan.get("direction"), plan.get("entry"), plan.get("stop_loss"), plan.get("tp1"),
                plan.get("tp2"), rt)

    recorded = ("ENTRY_VALID", s["direction"], s["entry"], s["sl"], s["tp1"], s["retest_time"])

    def core(x):
        return (x[0], x[1], x[2], x[3], x[4], x[6])

    base_sig = sig(data)
    trunc = copy.deepcopy(data)
    for tf in trunc["bars"]:
        keep = [b for b in trunc["bars"][tf] if b.time < now]
        trunc["bars"][tf], trunc["times"][tf] = keep, [b.time for b in keep]
    a = core(sig(trunc)) == recorded              # emitted signal reproduced with every later bar removed
    fut = copy.deepcopy(data)
    for tf in fut["bars"]:
        out = []
        for b in fut["bars"][tf]:
            if b.time >= now:
                k = 1 + rng.uniform(-0.01, 0.01)
                o, c = b.open * k, b.close * (1 + rng.uniform(-0.01, 0.01))
                out.append(Candle(b.time, o, max(o, c, b.high * k), min(o, c, b.low * k), c))
            else:
                out.append(b)
        fut["bars"][tf] = out
    b_ok = sig(fut) == base_sig
    sbar = copy.deepcopy(trunc)
    i = sbar["times"]["M5"].index(retest)
    bar = sbar["bars"]["M5"][i]
    shrink = (bar.high - bar.low) * 0.25
    nb = Candle(bar.time, bar.open, bar.high - shrink, bar.low + shrink, bar.close)
    nb = Candle(nb.time, nb.open, max(nb.open, nb.high, nb.close), min(nb.open, nb.low, nb.close), nb.close)
    sbar["bars"]["M5"][i] = nb
    ps = sig(sbar)
    sig_cls = "IDENTICAL" if ps == base_sig else ("ABSENT" if ps[0] != "ENTRY_VALID" else "CHANGED")
    per = copy.deepcopy(data)
    closed = [j for j, t in enumerate(per["times"]["M5"]) if t + M5 <= ticket_now]
    i = closed[-1]   # supplementary: the latest closed bar at the ticket's emission time
    if per["times"]["M5"][i] <= retest:
        c_cls = "NOT_APPLICABLE_SIGNAL_BAR_IS_LAST"
    else:
        bar = per["bars"]["M5"][i]
        k = 1 + rng.uniform(-0.01, 0.01)
        o, c = bar.open * k, bar.close * (1 + rng.uniform(-0.01, 0.01))
        per["bars"]["M5"][i] = Candle(bar.time, o, max(o, c, bar.high * k), min(o, c, bar.low * k), c)
        c_cls = "IDENTICAL" if sig(per, ticket_now) == sig(data, ticket_now) else "CHANGED"
    return {"signal": f"{s['symbol']}:{s['direction']}:{s['retest_time']}", "base_result": base_sig[0],
            "ticket_now": s["now"], "truncation_identical": a, "future_perturbation_identical": b_ok,
            "forming_bar_perturbation": c_cls, "l3_verdict": "PASS" if a and b_ok and c_cls != "CHANGED" else "FAIL",
            # (c) not an L3 test (owner/PM ruling); the ASW level formulas do not apply to CCFD -- outcome recorded only
            "signal_bar_perturbation": sig_cls, "signal_bar_l4": {"status": "NOT_APPLIED", "outcome": sig_cls},
            "verdict": "PASS" if a and b_ok and c_cls != "CHANGED" else "FAIL"}


# ------------------------------------------------------------------------------------------ main

def _asw_signal_breakdown(asw: Dict[str, Any]) -> Dict[str, Any]:
    """One ticket per symbol x cycle x fixture day: every emitted signal is unique (no repeated scan records)."""
    keys = [(r["symbol"], r["cycle"], r["day"]) for r in asw["rows"] + asw["engine_gated_geometry"]]
    by_scope: Dict[str, Dict[str, Any]] = {}
    for r in asw["rows"]:
        by_scope.setdefault(f"{r['symbol']}x{r['cycle']}", {"signals": 0, "geometry_invalid": 0})["signals"] += 1
    reasons: Dict[str, int] = {}
    oracle_classes: Dict[str, int] = {}
    for g in asw["engine_gated_geometry"]:
        cell = by_scope.setdefault(f"{g['symbol']}x{g['cycle']}", {"signals": 0, "geometry_invalid": 0})
        cell["signals"] += 1
        cell["geometry_invalid"] += 1
        reasons[str(g["guard_reason"])] = reasons.get(str(g["guard_reason"]), 0) + 1
        cls = g["comparison_supplementary"]["class"]
        oracle_classes[cls] = oracle_classes.get(cls, 0) + 1
    for cell in by_scope.values():
        cell["geometry_invalid_pct"] = round(100.0 * cell["geometry_invalid"] / cell["signals"], 1)
    return {"signals": len(keys), "unique_signals": len(set(keys)),
            "geometry_invalid": len(asw["engine_gated_geometry"]),
            "geometry_invalid_by_guard_reason": dict(sorted(reasons.items())),
            "geometry_invalid_oracle_supplementary": dict(sorted(oracle_classes.items())),
            "by_scope": dict(sorted(by_scope.items()))}


def _fuzz_summary(cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    def count(key, sub=None):
        out: Dict[str, int] = {}
        for f in cases:
            v = str((f.get(key) or {}).get(sub) if sub else f.get(key))
            out[v] = out.get(v, 0) + 1
        return dict(sorted(out.items()))
    fields: Dict[str, int] = {}
    for f in cases:
        for n in f.get("signal_bar_changed_fields") or []:
            fields[n] = fields.get(n, 0) + 1
    return {"cases": len(cases),
            "l3_fail": sum(f["l3_verdict"] == "FAIL" for f in cases),
            "truncation_not_identical": sum(not f["truncation_identical"] for f in cases),
            "future_perturbation_not_identical": sum(not f["future_perturbation_identical"] for f in cases),
            "forming_bar_perturbation": count("forming_bar_perturbation"),
            "signal_bar_perturbation": count("signal_bar_perturbation"),
            "signal_bar_changed_fields": dict(sorted(fields.items())),
            "signal_bar_l4": count("signal_bar_l4", "status"),
            "signal_bar_l4_fail": sum((f.get("signal_bar_l4") or {}).get("status") == "FAIL" for f in cases)}


def summarize(asw: Dict[str, Any], ccfd: Dict[str, Any]) -> Dict[str, Any]:
    def agree(rows):
        n = len(rows)
        classes: Dict[str, int] = {}
        for r in rows:
            classes[r["comparison"]["class"]] = classes.get(r["comparison"]["class"], 0) + 1
        return {"signals": n, "classes": dict(sorted(classes.items())),
                "agreement_pct": round(100.0 * classes.get("AGREE", 0) / n, 1) if n else None}
    sweeps = ccfd["sweeps"]
    return {
        "outcome_oracle": {"ASW_v1.1.3": agree(asw["rows"]), "CCFD_1.0.0": agree(ccfd["rows"]),
                           "ASW_engine_gated_geometry_excluded": len(asw["engine_gated_geometry"])},
        "asw_emitted_signals": _asw_signal_breakdown(asw),
        "ccfd_excluded_not_entry_valid": len(ccfd["excluded_not_entry_valid"]),
        "range_crosscheck_pandas_ta": {"ASW_box_agree": sum(r["box_agree"] for r in asw["rows"]),
                                       "ASW_rows": len(asw["rows"]),
                                       "CCFD_reference_agree": sum(r["reference_agree"] for r in ccfd["rows"]),
                                       "CCFD_rows": len(ccfd["rows"])},
        "sweep_oracle_smc": {"signals": len(sweeps),
                             "sweep_level_agree_pct": round(100.0 * sum(s["sweep_class"] == "AGREE" for s in sweeps)
                                                            / len(sweeps), 1) if sweeps else None,
                             "mss_swing_agree_pct": round(100.0 * sum(s["mss_class"] == "AGREE" for s in sweeps)
                                                          / len(sweeps), 1) if sweeps else None},
        "l3_fuzz": {"ASW": _fuzz_summary(asw["fuzz"]), "CCFD": _fuzz_summary(ccfd["fuzz"])},
        "data_insufficient_60d": DATA_INSUFFICIENT_60D,
    }


def main(argv=None) -> int:
    import importlib.metadata as md
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="artifacts/oss_differential/c25_report.json")
    args = ap.parse_args(argv)
    rng = random.Random(SEED)
    asw, ccfd = run_asw(rng), run_ccfd(rng)
    report = {"schema": "AGP_C25_OSS_DIFFERENTIAL_V1", "seed": SEED, "scope": "60 committed recorded days only",
              "oss_versions": {p: md.version(p) for p in ("backtesting", "pandas-ta", "smartmoneyconcepts", "pandas")},
              "summary": summarize(asw, ccfd), "asw": asw, "ccfd": ccfd}
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
