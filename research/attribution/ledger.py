"""Candidate ledger over the FROZEN SSC engine, with per-rule flags.

No rule is re-implemented. Each gate below is one frozen engine function; the
instrumentation wraps it inside the frozen `replay` module's namespace for the duration
of a single `run_replay` call, always calls the real function first, records its real
verdict, and -- only when that gate is in `relax` -- lets the candidate through using the
SAME frozen function with the gate's own threshold neutralised. `relax=()` reproduces
the frozen baseline exactly (asserted by test).

  G_BIAS        bias_gate.allowed_directions      (H1 MarketBiasResult direction)
  G_STOP_FLOOR  stop_engine.compute_stop          (friction.minimum_stop_multiple)
  G_RISK_ALLOC  campaign.allocate_risk            (campaign entry/setup/risk caps)
  G_S3_SCORE    setups.evaluate_s3_pullback_...   (continuation_score.minimum)

Counterfactual outcomes come from the all-gates-relaxed replay (`ALL_RELAXED`): the
frozen outcome resolver applied to every candidate. Path dependence (a relaxed entry
opens a campaign that later enables S3 / blocks S1-S2) is inherent and recorded as
`ledger_path = ALL_RELAXED`; ablation (ablation.py) therefore re-runs the engine per
relaxation instead of filtering this ledger.
"""
from __future__ import annotations

import contextlib
import copy
from typing import Dict, Iterable, List, Optional, Sequence

from research.attribution import costs

GATES = ("G_BIAS", "G_STOP_FLOOR", "G_RISK_ALLOC", "G_S3_SCORE")
ALL_RELAXED = frozenset(GATES)

# Declared rule swaps: alternatives the frozen engine/contract itself already exposes.
SWAPS = {
    "SWAP_REALIZED_R_BLOCK_ON": "campaign.block_new_entries_after_realized_r_enabled=true (contract opt-in)",
    "SWAP_FILL_M15": "outcome resolution on M15 instead of M1 (engine-supported switch)",
}

_RELAXED_CAPS = {"max_entries": 99, "maximum_total_risk_pct": 99.0}


def outcome_class(outcome: Optional[dict]) -> str:
    """TP1_FIRST / STOP_FIRST / EXPIRED / NEITHER from the frozen resolver's own
    event sequence (TP1 = the partial target)."""
    if not outcome:
        return "NEITHER"
    events = [e.get("event", "") for e in outcome.get("event_sequence") or []]
    first = events[0] if events else ""
    if first.startswith("PARTIAL"):
        return "TP1_FIRST"
    if first == "SL":
        return "STOP_FIRST"
    if first == "SESSION_EXIT_FULL_POSITION":
        return "EXPIRED"
    return "NEITHER"  # AMBIGUOUS_SEQUENCE (same-bar SL+TP1), UNRESOLVED_NO_DATA


def swap_config(config: dict, swap: Optional[str]) -> dict:
    cfg = copy.deepcopy(config)
    if swap == "SWAP_REALIZED_R_BLOCK_ON":
        cfg["campaign"]["block_new_entries_after_realized_r_enabled"] = True
    return cfg


class _Recorder:
    def __init__(self) -> None:
        self.permitted: frozenset = frozenset()
        self.current: Optional[dict] = None
        self.by_key: Dict[tuple, dict] = {}

    def open(self, candle, cand) -> None:
        setup, direction = cand.setup_model.value, cand.direction
        self.current = {"G_STOP_FLOOR": "N/A", "G_RISK_ALLOC": "N/A", "G_S3_SCORE": "N/A",
                        "_direction": direction}
        self.by_key[(str(candle.time), setup)] = self.current


@contextlib.contextmanager
def _instrumented(replay, config: dict, relax: frozenset, rec: _Recorder,
                  excluded=lambda setup, direction, regime: False):
    names = ("allowed_directions", "compute_stop", "allocate_risk",
             "evaluate_s1_sweep_reversal", "evaluate_s2_breakout_continuation",
             "evaluate_s3_pullback_continuation")
    real = {n: getattr(replay, n) for n in names}
    relaxed_cfg = copy.deepcopy(config)
    relaxed_cfg["campaign"].update(_RELAXED_CAPS)
    relaxed_cfg["setup_limits"] = {k: 99 for k in relaxed_cfg["setup_limits"]}

    def allowed_directions(bias_result, symbol):
        rec.permitted = real["allowed_directions"](bias_result, symbol)
        return frozenset({"LONG", "SHORT"}) if "G_BIAS" in relax else rec.permitted

    def _wrap_s12(name):
        regime_pos = 2 if name.endswith("continuation") else 4
        def fn(*args, **kwargs):
            cand = real[name](*args, **kwargs)
            if cand is not None and excluded(cand.setup_model.value, cand.direction, getattr(args[regime_pos], "value", args[regime_pos])):
                return None
            if cand is not None:
                rec.open(args[1] if name.endswith("continuation") else args[0], cand)
            return cand
        return fn

    def evaluate_s3(prior_bos, candle, candle_index, direction, regime, signals, minimum_score):
        cand = real["evaluate_s3_pullback_continuation"](
            prior_bos, candle, candle_index, direction, regime, signals, minimum_score)
        if excluded(replay.SetupModel.S3.value, direction, getattr(regime, "value", regime)):
            return None
        verdict = "PASS"
        if cand is None:
            cand = real["evaluate_s3_pullback_continuation"](
                prior_bos, candle, candle_index, direction, regime, signals, 0)
            if cand is None:
                return None
            verdict = "FAIL"
            if "G_S3_SCORE" not in relax:
                rec.open(candle, cand)
                rec.current["G_S3_SCORE"] = verdict
                rec.current["_dropped_by"] = "G_S3_SCORE"
                return None
        rec.open(candle, cand)
        rec.current["G_S3_SCORE"] = verdict
        return cand

    def compute_stop(direction, entry_price, anchor, atr, mult, friction, min_multiple):
        res = real["compute_stop"](direction, entry_price, anchor, atr, mult, friction, min_multiple)
        if res.accepted:
            rec.current["G_STOP_FLOOR"] = "PASS"
            return res
        alt = real["compute_stop"](direction, entry_price, anchor, atr, mult, friction, 0.0)
        rec.current["G_STOP_FLOOR"] = "FAIL" if alt.accepted else f"FAIL_OTHER:{res.reason}"
        rec.current["_stop_if_relaxed"] = alt.stop_price if alt.accepted else None
        return alt if (alt.accepted and "G_STOP_FLOOR" in relax) else res

    def allocate_risk(campaign, setup_model, cfg):
        res = real["allocate_risk"](campaign, setup_model, cfg)
        if res.accepted:
            rec.current["G_RISK_ALLOC"] = "PASS"
            return res
        alt = real["allocate_risk"](campaign, setup_model, relaxed_cfg)
        rec.current["G_RISK_ALLOC"] = "FAIL" if alt.accepted else f"FAIL_OTHER:{res.reason}"
        return alt if (alt.accepted and "G_RISK_ALLOC" in relax) else res

    patched = {
        "allowed_directions": allowed_directions,
        "compute_stop": compute_stop,
        "allocate_risk": allocate_risk,
        "evaluate_s1_sweep_reversal": _wrap_s12("evaluate_s1_sweep_reversal"),
        "evaluate_s2_breakout_continuation": _wrap_s12("evaluate_s2_breakout_continuation"),
        "evaluate_s3_pullback_continuation": evaluate_s3,
    }
    try:
        for n, fn in patched.items():
            setattr(replay, n, fn)
        yield
    finally:
        for n, fn in real.items():
            setattr(replay, n, fn)


def run_cycle(replay, m15: Sequence, config: dict, symbol: str, pair: str, trading_date,
              pip_size: float, bias_result=None, m1: Optional[Sequence] = None,
              relax: Iterable[str] = (), swap: Optional[str] = None,
              exclude: Sequence[dict] = ()):
    """One frozen `run_replay` call with the requested gates relaxed. `exclude` is a
    preregistered variant's candidate filter (list of {setup_model, direction,
    session_pair, symbol, regime} matchers): a matching candidate never exists, i.e.
    new-rule semantics layered on top of the untouched frozen engine. Returns
    (ReplayResult, recorder)."""
    cfg = swap_config(config, swap)
    m1_used = None if swap == "SWAP_FILL_M15" else m1
    rec = _Recorder()

    def excluded(setup, direction, regime):
        attrs = {"setup_model": setup, "direction": direction, "regime": regime,
                 "session_pair": pair, "symbol": symbol}
        return any(all(attrs.get(k) == v for k, v in m.items()) for m in exclude)

    with _instrumented(replay, cfg, frozenset(relax), rec, excluded):
        result = replay.run_replay(m15, cfg, symbol, pair, trading_date, pip_size,
                                   bias_result=bias_result, m1_candles=m1_used)
    return result, rec


def _row(result, pip_size, bias_label, setup, time, direction, gate_flags, fill, entry_no,
         in_baseline, path) -> dict:
    outcome = fill["outcome"] if fill else None
    stop_dist = abs(fill["entry_price"] - fill["stop_price"]) if fill else None
    vt_cost = costs.cost_r(result.symbol, stop_dist, pip_size) if fill else None
    gross = outcome.get("gross_R") if outcome else None
    return {
        "symbol": result.symbol, "session_pair": result.session_pair,
        "trading_date": str(result.trading_date), "regime": result.regime,
        "bias": bias_label, "setup_model": setup, "direction": direction,
        "candle_time": time, "filled": bool(fill), "entry_number": entry_no,
        "entry_price": fill["entry_price"] if fill else None,
        "stop_price": fill["stop_price"] if fill else None,
        "fill_precision": fill["fill_precision"] if fill else None,
        **gate_flags,
        "all_rules_pass": all(v in ("PASS", "N/A") for v in gate_flags.values()),
        "in_frozen_baseline": in_baseline,
        "terminal_state": outcome.get("terminal_state") if outcome else None,
        "outcome_class": outcome_class(outcome),
        "gross_R": gross, "engine_net_R": outcome.get("net_R") if outcome else None,
        "vt_cost_R": vt_cost,
        "vt_net_R": (gross - vt_cost) if (gross is not None and vt_cost is not None) else None,
        "cost_model": costs.COST_MODEL_ID, "cost_model_status": costs.COST_MODEL_STATUS,
        "ledger_path": path,
    }


def ledger_rows(result, rec: _Recorder, baseline_result, pip_size: float, bias_label: str) -> List[dict]:
    """Every candidate of the ALL_RELAXED run (filled or not) with real per-gate
    verdicts, plus any frozen-baseline fill that path dependence removed from the relaxed
    path (`ledger_path = FROZEN_BASELINE_ONLY`, all gates PASS by construction), so the
    ledger always contains the complete frozen baseline. `entry_number` is the entry's
    order within its own campaign: the baseline campaign for baseline fills, the relaxed
    campaign otherwise."""
    base_order = {(a["entry_time"], a["setup_model"]): i + 1
                  for i, a in enumerate(baseline_result.accepted_setups)}
    fills = {(a["entry_time"], a["setup_model"]): a for a in result.accepted_setups}
    rows: List[dict] = []
    relaxed_no = 0
    for (time, setup), flags in sorted(rec.by_key.items()):
        fill = fills.get((time, setup))
        relaxed_no += 1 if fill else 0
        direction = flags.get("_direction")
        g_bias = "PASS" if direction in rec.permitted else "FAIL"
        gate_flags = {"G_BIAS": g_bias, **{g: flags.get(g, "N/A") for g in GATES[1:]}}
        key = (time, setup)
        entry_no = base_order.get(key) or (relaxed_no if fill else None)
        rows.append(_row(result, pip_size, bias_label, setup, time, direction, gate_flags, fill,
                         entry_no, key in base_order, "ALL_RELAXED"))
    for a in baseline_result.accepted_setups:
        key = (a["entry_time"], a["setup_model"])
        if key not in fills:
            rows.append(_row(baseline_result, pip_size, bias_label, a["setup_model"], a["entry_time"],
                             a["direction"], {g: "PASS" for g in GATES}, a, base_order[key], True,
                             "FROZEN_BASELINE_ONLY"))
    return rows


def trade_returns(result, pip_size: float) -> List[dict]:
    """Filled entries of one (possibly relaxed/swapped) run, VT-costed, for metrics."""
    out = []
    for a in result.accepted_setups:
        o = a["outcome"]
        gross = o.get("gross_R")
        c = costs.cost_r(result.symbol, abs(a["entry_price"] - a["stop_price"]), pip_size)
        if gross is None or c is None:
            continue
        out.append({"trading_date": str(result.trading_date), "symbol": result.symbol,
                    "session_pair": result.session_pair, "setup_model": a["setup_model"],
                    "direction": a["direction"], "entry_time": a["entry_time"], "net_R": gross - c})
    return out
