"""AGP-LANE-B: replay ST_CRYPTO_CFD_SWEEP_RETEST_V1@1.0.0 on the VT recorded BTCUSD/ETHUSD captures.

Inputs are the PR #128 / #131 recorded files (tests/fixtures/ccfd_v100/recorded, every sha256 in its
manifest is verified first). Nothing here adds time or pricing code; it only wires existing modules:

  engine     crypto_cfd_contract.evaluate (guard.evaluate: drops any bar with close_time > now on
             every timeframe, then the frozen rules.evaluate) -- the CFD contract's entry point
             (strategy_engine.session.Candle input, strategy_engine.sweep_retest primitives).
             strategy_engine.evaluate() is the FX session-box entry; it needs session_pairs, which
             this contract forbids (FX_SESSION_GATE_APPLIED=False), so it is not called.
  time       v1_tickets.crypto_cfd._closed (server-rule D1 close), ._config/._window (WEEKDAY and
             WEEKEND gates), crypto_cfd_contract.rules UTC-day windows, session_clock (display only).
  tickets    v1_tickets.crypto_cfd.build_crypto_cfd_cycle and
             v1_tickets.manual_ticket.build_crypto_cfd_manual_ticket -- unchanged v1_tickets schema;
             lot size via manual_ticket.lot_size -> sizing_math.risk.size_position.
  spread     manual_ticket.crypto_cfd_cost_gate with config/v1_tickets/crypto_cfd_ticket_policy.yaml
             (owner bands: <=10% of stop OK, 10-20% WARN, >20% BLOCK). Bands change ticket state
             only; no L1-L6 check reads them.

Scan: every M5 close of every UTC day in the capture, weekends included. Tickets: one live-cycle
ticket per manifest case (each M15 close inside a WEEKDAY/WEEKEND window), plus one research
ticket at each first ENTRY_VALID scan of a UTC day (stream EMISSION_RESEARCH, beside the live-cycle
decision for the same instant). The replay quote is the last closed M5 bar: bid = recorded close
(MT5 bars are bid bars), ask = bid + recorded spread_price. balance defaults to None: no account
equity is invented, so READY-capable tickets carry ACCOUNT_BALANCE_UNAVAILABLE.

Read-only and hermetic: no broker, network or MT5 call; registry untouched.

    python scripts/ccfd_sweep_retest_replay.py --date 2026-10-10 [--out-dir DIR] [--balance X]
"""
from __future__ import annotations

import argparse
import bisect
import datetime as dt
import hashlib
import importlib.util
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

# Import-only Linux MetaTrader5 portability shim (raises on any real MT5 call).
if "MetaTrader5" not in sys.modules:
    _spec = importlib.util.spec_from_file_location("ccfd_replay_test_conftest", ROOT / "tests/conftest.py")
    if _spec is not None and _spec.loader is not None:
        _spec.loader.exec_module(importlib.util.module_from_spec(_spec))

import yaml  # noqa: E402

from crypto_cfd_contract import guard, rules  # noqa: E402
from crypto_cfd_contract.contract import (  # noqa: E402
    CONTRACT_ID,
    CONTRACT_VERSION,
    CONTRACT_YAML,
    INSTRUMENTS,
    STOP_BUFFER_PRICE,
    TP1_VOLUME_PCT,
)
from market_structure.config import load_market_structure_config  # noqa: E402
from scripts.ccfd_recorded_cases import (  # noqa: E402
    RECORDED,
    parse_ts,
    read_rows,
    shared_paths,
    verify,
)
from session_clock import local_time_diagnostics  # noqa: E402
from strategy_engine.session import Candle  # noqa: E402
from strategy_engine.sweep_retest.retest import ENTRY_TTL_M5_BARS  # noqa: E402
from strategy_engine.sweep_retest.targets import MIN_TP2_R_MULTIPLE  # noqa: E402
from ticket_delivery.renderer import payload_hash  # noqa: E402
from v1_tickets import crypto_cfd, manual_ticket  # noqa: E402
from v1_tickets.authority import logic_identity  # noqa: E402
from v1_tickets.crypto_cfd_policy import load_ticket_policy  # noqa: E402
from v1_tickets.logic_gate import (  # noqa: E402
    FAIL,
    PASS,
    WARN,
    l1_determinism,
    l5_cost,
    l6_freshness,
)

UTC = dt.timezone.utc
INSUFFICIENT = "INSUFFICIENT"
STEP = {"D1": dt.timedelta(days=1), "H1": dt.timedelta(hours=1), "M15": dt.timedelta(minutes=15),
        "M5": dt.timedelta(minutes=5)}
M5 = STEP["M5"]
SIGNAL_TTL = M5 + dt.timedelta(minutes=15)   # manual_ticket.build_crypto_cfd_manual_ticket valid_until
MANIFEST = RECORDED / "manifest.json"
REGISTRY = ROOT / "strategies/registry.yaml"
OUT_DIR = ROOT / "artifacts/logic_verification/ST_CRYPTO_CFD_SWEEP_RETEST_V1_1_0_0/vt_recorded_2026-09-26_2026-10-09"


# ------------------------------------------------------------------------------- data / feed

def load_symbol(symbol: str) -> Dict[str, Any]:
    paths = shared_paths(symbol)
    bars = {tf: [Candle(parse_ts(r["timestamp_utc"]), float(r["open"]), float(r["high"]), float(r["low"]),
                        float(r["close"])) for r in read_rows(RECORDED / paths[tf.lower()])] for tf in STEP}
    spread = {parse_ts(r["timestamp_utc"]): float(r["spread_price"])
              for r in read_rows(RECORDED / f"{symbol}_m5_meta.csv")}
    return {"bars": bars, "times": {tf: [c.time for c in rows] for tf, rows in bars.items()}, "spread": spread}


class ReplayFeed:
    """ReadOnlyCryptoFeed over the recorded capture as of `now`: bars opened before `now` (the forming
    bar included, as a terminal returns it; crypto_cfd._closed drops it) and the last closed M5 quote."""

    def __init__(self, data: Dict[str, Any], now: dt.datetime):
        self.data, self.now, self.requests = data, now, []

    def fetch(self, broker_symbol: str, timeframe: str, count: int) -> List[Candle]:
        self.requests.append((timeframe, count))
        end = bisect.bisect_left(self.data["times"][timeframe], self.now)
        return self.data["bars"][timeframe][max(0, end - count):end]

    def quote(self, broker_symbol: str):
        bar_open = self.now - M5
        i = bisect.bisect_left(self.data["times"]["M5"], bar_open)
        if i == len(self.data["times"]["M5"]) or self.data["times"]["M5"][i] != bar_open:
            raise ValueError("QUOTE_UNAVAILABLE")      # never invented from a neighbouring bar
        bid = self.data["bars"]["M5"][i].close
        return bid, round(bid + self.data["spread"][bar_open], 2), bar_open


def closed_inputs(data, now, counts) -> Dict[str, List[Candle]]:
    feed = ReplayFeed(data, now)
    return {tf: crypto_cfd._closed(feed.fetch("", tf, counts[tf]), now, STEP[tf]) for tf in STEP}


def engine(symbol, now, x, cfg) -> dict:
    return guard.evaluate(symbol, now, x["D1"], x["H1"], x["M5"], x["M15"], structure_config=cfg)


def semantic(r: dict) -> dict:
    ev = r["evidence"]
    return {"result": r["result"], **{k: ev.get(k) for k in ("sweep", "mss", "retest", "target_plan")}}


def day_type(day: dt.date) -> str:
    return "WEEKEND" if day.isoweekday() in (6, 7) else "WEEKDAY"


# ------------------------------------------------------------------------------- L2 / L4 checks

def reconstruct(r: dict, x: Dict[str, List[Candle]], now: dt.datetime, spec: dict) -> List[str]:
    """Re-derive an ENTRY_VALID result from raw closed candles and the YAML predicates; return the ids
    of failed checks. MSS swing location is the shared full_swings primitive and is taken as given."""
    ev, plan, bad = r["evidence"], r["evidence"]["target_plan"], []
    start, end = rules.previous_utc_day_window(now)
    prev = [c for c in x["M5"] if start <= c.time < end]
    if [c.time for c in prev] != [start + i * M5 for i in range(288)]:
        return ["reference_grid"]
    pdh, pdl = max(c.high for c in prev), min(c.low for c in prev)
    long = plan["direction"] == "LONG"
    if ev["context"]["direction_permission"] != ("LONG_ALLOWED" if long else "SHORT_ALLOWED"):
        bad.append("permission_side")
    if (ev["reference"]["high"], ev["reference"]["low"], ev["reference"]["mid"]) != (pdh, pdl, (pdh + pdl) / 2):
        bad.append("reference_levels")
    day0, _ = rules.utc_day_window(now)
    today = [c for c in x["M5"] if c.time >= day0]

    def swept(c):   # YAML m5_trigger_contract.sweep; dual-side candle skipped
        hi, lo = c.high > pdh and c.close < pdh, c.low < pdl and c.close > pdl
        return (lo if long else hi) and not (hi and lo)
    sweep = next((c for c in today if swept(c)), None)
    if sweep is None or sweep.time.isoformat() != ev["sweep"]["candle_time_utc"]:
        return bad + ["first_sweep"]
    level = ev["mss"]["broken_swing_price"]
    mss = next((c for c in today if c.time > sweep.time and (c.close > level if long else c.close < level)), None)
    if mss is None or mss.time.isoformat() != ev["mss"]["confirmed_at_utc"]:
        return bad + ["mss_close_break"]
    window = [c for c in today if c.time > mss.time][:ENTRY_TTL_M5_BARS]
    touch = next((c for c in window if (c.low <= level if long else c.high >= level)), None)
    if touch is None or touch.time.isoformat() != ev["retest"]["candle_time_utc"]:
        bad.append("retest_first_touch_ttl")
    stop = (sweep.low - STOP_BUFFER_PRICE) if long else (sweep.high + STOP_BUFFER_PRICE)
    expected = {"entry": level, "stop_loss": stop, "tp1": (pdh + pdl) / 2, "tp2": pdh if long else pdl}
    bad += [f"plan_{k}" for k, v in expected.items() if plan[k] != v]
    if plan["tp1_volume_pct"] != spec["targets_contract"]["tp1_volume_pct"]:
        bad.append("tp1_split")
    return bad


def geometry_ok(plan: dict) -> bool:
    entry, sl, tp1, tp2, risk = (plan[k] for k in ("entry", "stop_loss", "tp1", "tp2", "risk_distance"))
    long = plan["direction"] == "LONG"
    ordered = sl < entry < tp1 < tp2 if long else sl > entry > tp1 > tp2
    rr = abs(tp2 - entry) / risk if risk and risk > 0 else None
    return (ordered and risk > 0 and math.isclose(risk, abs(entry - sl)) and rr is not None
            and rr >= MIN_TP2_R_MULTIPLE and math.isclose(rr, plan["tp2_r_multiple"]))


def geometry_reject_ok(plan: dict) -> bool:
    """NO_TRADE_TARGET_GEOMETRY must really violate the guard: wrong-side target or RR < 1.5."""
    entry, tp1, tp2 = plan["entry"], plan["tp1"], plan["tp2"]
    wrong_side = not (tp1 > entry and tp2 > entry) if plan["direction"] == "LONG" else not (tp1 < entry and tp2 < entry)
    return wrong_side or (plan["tp2_r_multiple"] is not None and plan["tp2_r_multiple"] < MIN_TP2_R_MULTIPLE)


# ------------------------------------------------------------------------------- prefix (TEMP)

# TEMP(AGP-ORACLE): minimal inline prefix-invariance check. Replace with the AGP-ORACLE
# prefix_invariance import once that PR is merged; do not extend this function.
def prefix_invariance_temp(stream: Sequence[tuple]) -> dict:
    """stream: (now, semantic) for every M5 close, chronological. Within a UTC day, once ENTRY_VALID is
    first emitted every longer prefix must carry the identical decision; before it, none."""
    by_day: Dict[dt.date, list] = {}
    for now, sem in stream:
        by_day.setdefault(now.date(), []).append((now, sem))
    mismatches, pre_emission, emissions, by_day_bad = [], 0, 0, {}
    for rows in by_day.values():
        first = next((k for k, (_, s) in enumerate(rows) if s["result"] == "ENTRY_VALID"), None)
        pre_emission += sum(1 for k, (_, s) in enumerate(rows)
                            if (first is None or k < first) and s["result"] == "ENTRY_VALID")
        if first is not None:
            emissions += 1
            bad = [now.isoformat() for now, s in rows[first:] if s != rows[first][1]]
            mismatches += bad
            if bad:
                by_day_bad[rows[0][0].date().isoformat()] = len(bad)
    return {"source": "TEMP_INLINE (AGP-ORACLE not merged)", "days": len(by_day), "prefixes": len(stream),
            "emissions": emissions, "prefix_mismatches": len(mismatches), "mismatch_at": mismatches[:20],
            "pre_emission_signals": pre_emission, "mismatches_by_day": by_day_bad,
            "verdict": PASS if not mismatches and not pre_emission else FAIL}


# ------------------------------------------------------------------------------- tickets

def spread_band(ticket: dict) -> str:
    """Read the band the ticket already carries (crypto_cfd_cost_gate); no recomputation."""
    if "SPREAD_TOO_WIDE" in ticket.get("reason_codes", []):
        return "BLOCK"
    if "SPREAD_WARN" in ticket.get("warnings", []):
        return "WARN"
    return "OK" if ticket.get("spread_pct_of_stop") is not None else "NOT_EVALUATED"


def envelope(stream: str, case_id: str, symbol: str, now: dt.datetime, ticket: dict, **extra) -> dict:
    return {"stream": stream, "case_id": case_id, "symbol": symbol, "now": now.isoformat(),
            "day_type": day_type(now.date()), "spread_band": spread_band(ticket), **extra,
            "content_hash": manual_ticket.content_hash(ticket), "ticket": ticket}


# ------------------------------------------------------------------------------- run

def run_symbol(symbol: str, data: dict, cases: List[dict], days: Sequence[dt.date], cfg, spec: dict,
               policy: dict, balance: Optional[float]) -> dict:
    mism = Counter()
    dfail: Dict[str, Counter] = {}       # per UTC day: failed checks by gate (L1..L6)

    def bump(t: dt.datetime, gate: str, failed: bool = True) -> None:
        dfail.setdefault(t.date().isoformat(), Counter())[gate] += int(failed)
    tickets, cycle_l1 = [], []
    counts: Dict[str, int] = {}
    for case in cases:                                    # live-cycle tickets (manifest cases)
        now = dt.datetime.fromisoformat(case["now"])
        feed = ReplayFeed(data, now)
        build = lambda now=now: crypto_cfd.build_crypto_cfd_cycle(symbol, now, feed=ReplayFeed(data, now),
                                                                   balance=balance)
        ticket = crypto_cfd.build_crypto_cfd_cycle(symbol, now, feed=feed, balance=balance)
        counts = counts or dict(feed.requests)
        x = closed_inputs(data, now, dict(feed.requests)) if feed.requests else {"M5": []}
        cycle_l1.append(l1_determinism(build, x["M5"], now, bar=M5)["status"])
        bid, ask, quote_time = ReplayFeed(data, now).quote("")
        mism["manifest_parity"] += (ticket["cycle"] != case["window"] or quote_time.isoformat() != case["quote_time"]
                                    or round(ask - bid, 2) != case["spread"])
        tickets.append(envelope("CYCLE", case["id"], symbol, now, ticket))
    if not counts:
        raise SystemExit(f"{symbol}: no in-window case reached the feed; fetch counts unknown")

    stream, results, emissions = [], Counter(), []
    by_day: Dict[str, Counter] = {}
    l2_bad, l4_bad, l4_neg_bad, l2_neg_bad = [], [], [], []
    for day in days:
        day0 = dt.datetime.combine(day, dt.time(), tzinfo=UTC)
        emitted = False
        for k in range(288):
            now = day0 + k * M5
            x = closed_inputs(data, now, counts)
            r = engine(symbol, now, x, cfg)
            nondet = payload_hash(r) != payload_hash(engine(symbol, now, x, cfg))
            mism["determinism"] += nondet
            bump(now, "L1", nondet)
            future = {tf: x[tf] + data["bars"][tf][bisect.bisect_left(data["times"][tf], now):] for tf in STEP}
            leaked = semantic(engine(symbol, now, future, cfg)) != semantic(r)
            mism["truncation"] += leaked
            bump(now, "L3", leaked)
            sem = semantic(r)
            stream.append((now, sem))
            results[r["result"]] += 1
            by_day.setdefault(day.isoformat(), Counter())[r["result"]] += 1
            start, end = rules.previous_utc_day_window(now)
            exact = [c.time for c in x["M5"] if start <= c.time < end] == [start + i * M5 for i in range(288)]
            if exact == (r["result"] == "REFERENCE_INCOMPLETE"):
                l2_neg_bad.append(now.isoformat())
                bump(now, "L2")
            if r["result"] == "ENTRY_VALID":
                bad = reconstruct(r, x, now, spec)
                if bad:
                    l2_bad.append({"now": now.isoformat(), "failed": bad})
                    bump(now, "L2")
                if not geometry_ok(r["evidence"]["target_plan"]):
                    l4_bad.append(now.isoformat())
                    bump(now, "L4")
                if not emitted:
                    emitted = True
                    emissions.append((now, r, x))
            elif r["result"] == "NO_TRADE_TARGET_GEOMETRY" and not geometry_reject_ok(r["evidence"]["target_plan"]):
                l4_neg_bad.append(now.isoformat())
                bump(now, "L4")
    mism["l2_reconstruction"], mism["l4_geometry"] = len(l2_bad), len(l4_bad) + len(l4_neg_bad)
    mism["l2_reference_rule"] = len(l2_neg_bad)

    # ticket <-> scan parity: a cycle ticket's engine_result equals the scan result at the same instant
    scan_at = dict((now.isoformat(), sem) for now, sem in stream)
    for env in tickets:
        er = env["ticket"].get("engine_result")
        if er is not None and env["now"] in scan_at:
            mism["ticket_scan_parity"] += semantic(er) != scan_at[env["now"]]

    _, windows = crypto_cfd._config()
    meta, commission = manual_ticket.symbol_meta_from_host(symbol), manual_ticket.crypto_cfd_commission(symbol)
    emission_rows, l3_seq_bad, l5, l6 = [], [], [], []
    for now, r, x in emissions:
        ev, plan = r["evidence"], r["evidence"]["target_plan"]
        sweep_at, mss_at, retest_at = (dt.datetime.fromisoformat(ev[k][f]) for k, f in
                                       (("sweep", "candle_time_utc"), ("mss", "confirmed_at_utc"),
                                        ("retest", "candle_time_utc")))
        before = engine(symbol, retest_at, closed_inputs(data, retest_at, counts), cfg)
        if not (sweep_at < mss_at < retest_at and retest_at + M5 <= now and before["result"] != "ENTRY_VALID"):
            l3_seq_bad.append(now.isoformat())
            bump(now, "L3")
        bid, ask, quote_time = ReplayFeed(data, now).quote("")
        ticket = manual_ticket.build_crypto_cfd_manual_ticket(
            r, now=now, window=crypto_cfd._window(now, windows) or "OUTSIDE_WINDOW", spread=ask - bid,
            balance=balance, meta=meta, commission_r=commission, policy=policy, quote_time=quote_time)
        live = crypto_cfd.build_crypto_cfd_cycle(symbol, now, feed=ReplayFeed(data, now), balance=balance)
        tickets.append(envelope("EMISSION_RESEARCH", f"{symbol}_EMISSION_{now:%Y%m%dT%H%MZ}", symbol, now, ticket,
                                live_cycle_decision=live["decision"], live_cycle_reason_codes=live["reason_codes"],
                                local_time=local_time_diagnostics(now)))
        l5.append(l5_cost(ask - bid, plan["risk_distance"], commission_r=commission, warn_r=policy["cost_warn_R"]))
        expected_until = (retest_at + SIGNAL_TTL).isoformat()
        gate6 = l6_freshness(ticket["valid_until"], {"rule": "SIGNAL_STALE once now > retest close + 15 min",
                                                     "or_after": ticket["valid_until"]},
                             {"sl_touched_before_fill": plan["stop_loss"]})
        l6.append(PASS if gate6["status"] == PASS and ticket["valid_until"] == expected_until
                  and now < retest_at + SIGNAL_TTL else FAIL)
        bump(now, "L6", l6[-1] == FAIL)
        emission_rows.append({"now": now.isoformat(), "day_type": day_type(now.date()),
                              "direction": plan["direction"], "entry": plan["entry"], "stop_loss": plan["stop_loss"],
                              "tp1": plan["tp1"], "tp2": plan["tp2"], "risk_distance": plan["risk_distance"],
                              "tp2_r_multiple": plan["tp2_r_multiple"], "sweep_at": sweep_at.isoformat(),
                              "mss_at": mss_at.isoformat(), "retest_at": retest_at.isoformat(),
                              "spread": round(ask - bid, 2), "spread_pct_of_stop": ticket["spread_pct_of_stop"],
                              "spread_band": spread_band(ticket), "ticket_decision": ticket["decision"],
                              "ticket_reason_codes": ticket["reason_codes"], "ticket_warnings": ticket["warnings"],
                              "live_cycle_decision": live["decision"], "live_cycle_reason_codes": live["reason_codes"]})
    prefix = prefix_invariance_temp(stream)
    mism["prefix"], mism["l3_sequence"] = prefix["prefix_mismatches"], len(l3_seq_bad)
    for d, n in prefix["mismatches_by_day"].items():
        dfail.setdefault(d, Counter())["L3"] += n
    mism["ticket_determinism"] = sum(s != PASS for s in cycle_l1)

    identity = logic_identity(CONTRACT_ID, CONTRACT_VERSION)
    spec_ok = (spec["strategy_id"] == CONTRACT_ID and str(spec["version"]) == CONTRACT_VERSION
               and spec["targets_contract"]["tp1_volume_pct"] == TP1_VOLUME_PCT
               and spec["targets_contract"]["min_tp2_r_multiple"] == MIN_TP2_R_MULTIPLE
               and str(spec["m5_trigger_contract"]["retest"]["max_bars_after_mss"]).startswith(f"{ENTRY_TTL_M5_BARS} ")
               and spec["stop_loss_contract"]["stop_buffer"].startswith("0.00") and STOP_BUFFER_PRICE == 0
               and spec["context_contract"]["structure_params"] == {"swing_length": cfg.swing_length,
                                                                     "close_break": cfg.close_break})
    entries = results["ENTRY_VALID"]

    def v(failed: bool, positive: bool) -> str:
        return FAIL if failed else (PASS if positive else INSUFFICIENT)
    l5_status = INSUFFICIENT if not l5 else (WARN if any(g["status"] != PASS for g in l5) else PASS)
    gates = {
        "L1": v(identity is None or mism["determinism"] or mism["ticket_determinism"], True),
        "L2": v(not spec_ok or mism["l2_reconstruction"] or mism["l2_reference_rule"], entries > 0),
        "L3": v(mism["truncation"] or mism["prefix"] or mism["l3_sequence"] or prefix["pre_emission_signals"],
                bool(emissions)),
        "L4": v(bool(mism["l4_geometry"]), entries > 0),
        "L5": l5_status,                       # advisory (logic_gate.l5_cost); spread band NOT consulted
        "L6": v(FAIL in l6, bool(l6)),
    }
    emitted_days = {e["now"][:10]: e for e in emission_rows}
    l5_by_day = {e["now"][:10]: g["status"] for e, g in zip(emission_rows, l5)}
    per_day = {}
    for d, c in by_day.items():
        f, pos = dfail.get(d, Counter()), c["ENTRY_VALID"] > 0
        gd = {"L1": v(f["L1"] > 0, True), "L2": v(f["L2"] > 0, pos), "L3": v(f["L3"] > 0, True),
              "L4": v(f["L4"] > 0, pos), "L5": l5_by_day.get(d, INSUFFICIENT), "L6": v(f["L6"] > 0, d in emitted_days),
              "prefix_mismatches": prefix["mismatches_by_day"].get(d, 0)}
        gd["failure_class"] = "UNCLASSIFIED_FAILURE" if FAIL in gd.values() else None
        per_day[d] = {"day_type": day_type(dt.date.fromisoformat(d)), "results": dict(sorted(c.items())), **gd}
    return {
        "symbol": symbol, "fetch_counts": counts, "per_day": per_day, "days": len(days), "scans": len(stream),
        "scan_results": dict(sorted(results.items())), "scan_results_by_day": {d: dict(sorted(c.items()))
                                                                               for d, c in by_day.items()},
        "entry_valid_scans": entries, "emissions": emission_rows, "gates": gates,
        "gate_evidence": {"logic_identity": identity, "spec_constants_match": spec_ok,
                          "l2_failures": l2_bad[:20], "l2_reference_rule_failures": l2_neg_bad[:20],
                          "l4_failures": l4_bad[:20], "l4_reject_failures": l4_neg_bad[:20],
                          "l3_sequence_failures": l3_seq_bad,
                          "l5_cost_gates": l5, "l6": l6, "cycle_ticket_l1": dict(Counter(cycle_l1))},
        "prefix_invariance": prefix, "mismatches": dict(sorted(mism.items())),
        "tickets": tickets,
    }


def all_checks_pass(r: dict) -> bool:
    """Repo precedent (ASW 1.1.2): L1-L4 and L6 PASS, L5 advisory (WARN allowed, never FAIL), zero
    mismatches, and no recorded day with a FAIL. INSUFFICIENT on a no-signal day is not a failure."""
    g = r["gates"]
    return (all(g[k] == PASS for k in ("L1", "L2", "L3", "L4", "L6")) and g["L5"] in (PASS, WARN)
            and not any(r["mismatches"].values()) and r["prefix_invariance"]["verdict"] == PASS
            and not any(d["failure_class"] for d in r["per_day"].values()))


def build(date: str, symbols: Sequence[str] = INSTRUMENTS, days: Optional[Sequence[dt.date]] = None,
          balance: Optional[float] = None) -> dict:
    manifest = verify(MANIFEST)              # every listed sha256, else SystemExit before any replay
    registry_before = REGISTRY.read_bytes()
    spec = yaml.safe_load((ROOT / CONTRACT_YAML).read_text(encoding="utf-8"))
    cfg, policy = load_market_structure_config(), load_ticket_policy()
    out: Dict[str, Any] = {}
    for symbol in symbols:
        data = load_symbol(symbol)
        all_days = sorted({c.time.date() for c in data["bars"]["M5"]})
        run_days = [d for d in all_days if days is None or d in days]
        cases = [c for c in manifest["cases"] if c["symbol"] == symbol
                 and (days is None or dt.datetime.fromisoformat(c["now"]).date() in days)]
        out[symbol] = run_symbol(symbol, data, cases, run_days, cfg, spec, policy, balance)
    registry = yaml.safe_load(registry_before)["strategies"][CONTRACT_ID]
    tickets = [t for s in out.values() for t in s.pop("tickets")]
    identity = logic_identity(CONTRACT_ID, CONTRACT_VERSION)
    verification = {sym: {"all_checks_pass": all_checks_pass(r), "logic_identity": identity} for sym, r in out.items()}
    summary = Counter((t["stream"], t["symbol"], t["day_type"], t["ticket"]["decision"], t["spread_band"])
                      for t in tickets)
    first = out[symbols[0]]
    return {
        "schema": "AG_CCFD_V100_REPLAY_V1", "mission": "AGP-LANE-B", "date": date,
        "strategy": f"{CONTRACT_ID}@{CONTRACT_VERSION}", "contract_path": CONTRACT_YAML,
        "contract_sha256": hashlib.sha256((ROOT / CONTRACT_YAML).read_bytes()).hexdigest(),
        "dataset": {"manifest": str(MANIFEST.relative_to(ROOT)),
                    "manifest_sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
                    "file_hashes_verified": True, "source": manifest["source"], "gaps": manifest["gaps"]},
        "days_run": sorted(first["scan_results_by_day"]),
        "weekend_days": [d for d in first["scan_results_by_day"] if day_type(dt.date.fromisoformat(d)) == "WEEKEND"],
        "spread_policy": {k: policy[k] for k in ("spread_ok_pct", "spread_block_pct", "cost_warn_R", "cost_block_R")},
        "spread_band_scope": "ticket state only; no L1-L6 check reads the band",
        "prefix_invariance_source": "TEMP_INLINE (AGP-ORACLE not merged)",
        "balance": balance, "symbols": out, "logic_verification": verification,
        "ticket_summary": [dict(zip(("stream", "symbol", "day_type", "decision", "spread_band"), k), count=n)
                           for k, n in sorted(summary.items())],
        "tickets_total": len(tickets),
        "registry": {"active": registry["active"], "research": registry["research"],
                     "modified": REGISTRY.read_bytes() != registry_before},
        "edge_verified": False, "logic_verified_claim": False, "demo_authorized": False, "live_authorized": False,
        "ORDER_API_CALLS": 0, "BROKER_MUTATION_COUNT": 0, "_tickets": tickets,
    }


def write(report: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    tickets = report.pop("_tickets")
    with (out_dir / "tickets.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for t in tickets:
            f.write(json.dumps(t, sort_keys=True, default=str) + "\n")
    prefix = {s: r["prefix_invariance"] for s, r in report["symbols"].items()}
    (out_dir / "prefix_invariance.json").write_text(json.dumps(prefix, indent=2, sort_keys=True) + "\n",
                                                    encoding="utf-8", newline="\n")
    (out_dir / "replay_report.json").write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
                                                encoding="utf-8", newline="\n")


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--date", required=True)
    p.add_argument("--out-dir", type=Path, default=OUT_DIR)
    p.add_argument("--balance", type=float, default=None)
    p.add_argument("--symbols", nargs="+", default=list(INSTRUMENTS), choices=list(INSTRUMENTS))
    args = p.parse_args(argv)
    report = build(args.date, symbols=tuple(args.symbols), balance=args.balance)
    write(report, args.out_dir)
    for s, r in report["symbols"].items():
        print(s, r["days"], "days", r["scans"], "scans", r["gates"], "mismatches", sum(r["mismatches"].values()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
