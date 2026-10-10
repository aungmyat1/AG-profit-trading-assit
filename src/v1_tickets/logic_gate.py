"""Manual Trade Ticket V1 Phase 4 -- Logic Gate L1-L6 (pure functions, per-check evidence).

Each gate returns {"gate", "status", "checks": [{id, rule, value, expected, verdict, note}]}.
L1-L4 FAIL -> no TICKET_READY. L5 (cost) and L6 (freshness fields) are displayed flags only.

LOGIC_VERIFIED is a statement about rule conformance and internal consistency -- never
about profitability or authorization. The gate reads the frozen strategy YAML and the
engine output; it never changes a rule. Where the YAML and the frozen engine disagree,
or the YAML is not evaluable, L2 records the divergence and FAILS (fail closed) instead of
choosing an interpretation. Known, pre-existing examples for ST_ASIAN_SWEEP_5R_V1@1.1.1:
`stop_loss_mode: PERCENT_OF_SESSION_RANGE 0.25` vs the engine's sweep-wick stop
(docs/status/AG_ST_ASIAN_SWEEP_V1_1_2_GOVERNED_SL_GEOMETRY_RECONCILIATION_STATUS.md) and the
declared-but-unconsumed EMA_50 trend filter (no timeframe/price source in the YAML).
Checks are driven by what the YAML declares: the v1.1.2 candidate
(strategies/ST_ASIAN_SWEEP_5R_V1_1_1_2.yaml) declares the engine's own geometry and its
fail-closed rules, so its L2 evaluates those instead.
"""
from __future__ import annotations

import datetime as dt
import math
from typing import Any, Callable, Dict, List, Optional, Sequence

import yaml

from strategy_engine.models import StrategyConfig
from strategy_engine.session import Candle
from ticket_delivery.renderer import payload_hash
from v1_tickets.guards import (
    LEGACY_STALE_SIGNAL,
    MAX_SPREAD_RISK_FRACTION,
    SIGNAL_STALE,
    STALE_AFTER,
)

PASS, FAIL, WARN, NOT_EVALUABLE = "PASS", "FAIL", "WARN", "NOT_EVALUABLE"
NOT_APPLICABLE = "NOT_APPLICABLE"   # post-fill / execution-time rule: recorded, not part of a manual ticket decision
M15 = dt.timedelta(minutes=15)
# Pip size only where the repo already evidences it (large_smc_watch.contract.C10_PIP_SIZE).
EVIDENCED_PIP = {"EURUSD": 0.0001, "GBPUSD": 0.0001}


def _check(cid: str, rule: str, value: Any, expected: Any, verdict: str, note: str = "") -> Dict[str, Any]:
    return {"id": cid, "rule": rule, "value": value, "expected": expected, "verdict": verdict, "note": note}


def _gate(name: str, checks: List[Dict[str, Any]], *, advisory: bool = False) -> Dict[str, Any]:
    bad = [c for c in checks if c["verdict"] in (FAIL, NOT_EVALUABLE)]
    warn = [c for c in checks if c["verdict"] == WARN]
    status = (WARN if bad or warn else PASS) if advisory else (FAIL if bad else (WARN if warn else PASS))
    return {"gate": name, "status": status, "checks": checks}


def _point(digits: Optional[int]) -> float:
    return 10.0 ** -digits if digits is not None else 0.0


EQ_EPS_POINTS = 1e-6   # float-noise slack, in points; never a price tolerance


def _eq(a: Optional[float], b: Optional[float], digits: Optional[int]) -> bool:
    """`a` equals expectation `b` rounded to the ticket's point grid, or to float precision when unrounded.

    `b` is rounded ROUND_HALF_UP (ties away from zero, OD1011-ROUNDING); only EQ_EPS_POINTS x point of
    float noise is tolerated, so a half-point error, a one-point error or the other tie neighbour fails."""
    if a is None or b is None:
        return False
    if digits is None:
        return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))
    point = _point(digits)
    k = abs(b) / point
    base = math.floor(k)
    g = base + 1 if k - base >= 0.5 - EQ_EPS_POINTS else base
    return abs(a - math.copysign(g * point, b)) <= EQ_EPS_POINTS * point


def _signal_candle(ticket: Dict[str, Any], post: Sequence[Candle]) -> Optional[Candle]:
    ts = ticket.get("signal_timestamp")
    return next((c for c in post if c.time.isoformat() == ts), None) if ts else None


def v120_strategy_delta(decision: Any) -> Dict[str, Any]:
    """V1.2-only checks layered on the existing gate evidence model.

    The production evaluator owns prices; this function independently verifies the
    frozen owner deltas and never repairs a rejected candidate. It is intentionally not
    used for v1.1.1, whose historical behavior remains frozen.
    """
    if not getattr(decision, "direction", None):
        return _gate("V1.2", [_check("V12.candidate", "candidate exists", decision.status,
                                     "ACTIONABLE", FAIL)])
    long = decision.direction == "LONG"
    rng = decision.reference_high - decision.reference_low
    expected = rng * 0.25
    got = abs(decision.entry - decision.stop_loss)
    wick = decision.stop_loss <= decision.sweep_extreme if long else decision.stop_loss >= decision.sweep_extreme
    order = (decision.stop_loss < decision.entry < decision.tp1 <= decision.tp2) if long else (
        decision.stop_loss > decision.entry > decision.tp1 >= decision.tp2)
    expiry = decision.decision_time + dt.timedelta(minutes=15) == decision.expiry
    spread_abs = decision.spread_pips is not None and decision.spread_pips <= 2.0
    spread_r = decision.spread_R is not None and decision.spread_R <= 0.15
    return _gate("V1.2", [
        _check("V12.entry_close", "entry equals confirmed closed-candle close", decision.entry,
               "engine confirmation close", PASS if decision.decision_time is not None else FAIL),
        _check("V12.stop_25pct", "stop distance = 25% reference range", got, expected,
               PASS if abs(got - expected) <= 1e-12 else FAIL),
        _check("V12.wick_clear", "SL clears sweep extreme", decision.stop_loss, decision.sweep_extreme,
               PASS if wick else FAIL),
        _check("V12.target_order", "directional target ordering", [decision.stop_loss, decision.entry,
                                                                    decision.tp1, decision.tp2], True,
               PASS if order else FAIL),
        _check("V12.expiry", "expiry = decision + 15m", decision.expiry, decision.decision_time, PASS if expiry else FAIL),
        _check("V12.spread_absolute", "spread <= 2.0 pips", decision.spread_pips, 2.0,
               PASS if spread_abs else FAIL),
        _check("V12.spread_R", "spread <= 0.15R", decision.spread_R, 0.15, PASS if spread_r else FAIL),
    ])


# ---------------------------------------------------------------------------------- L1

def l1_determinism(build: Callable[[], Dict[str, Any]], candles: Sequence[Candle],
                   evaluated_at: dt.datetime, bar: dt.timedelta = M15) -> Dict[str, Any]:
    """Same inputs -> identical payload (hash of two independent builds); closed bars only."""
    first, second = build(), build()
    h1, h2 = payload_hash(first), payload_hash(second)
    last_close = max((c.time + bar for c in candles), default=None)
    return _gate("L1", [
        _check("L1.replay_hash", "two builds from identical inputs hash identically", h1, h2,
               PASS if h1 == h2 else FAIL),
        _check("L1.closed_bars_only", "every input bar closed at decision time (no look-ahead)",
               last_close.isoformat() if last_close else None, f"<= {evaluated_at.isoformat()}",
               PASS if last_close is None or last_close <= evaluated_at else FAIL),
    ])


# ---------------------------------------------------------------------------------- L2

def _raw_spec(strategy: StrategyConfig) -> Dict[str, Any]:
    from v1_tickets.authority import REPO_ROOT
    path = strategy.source_path if strategy.source_path.startswith("/") else str(REPO_ROOT / strategy.source_path)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def l2_rule_conformance(strategy: StrategyConfig, ticket: Dict[str, Any], session: Sequence[Candle],
                        expected_bar_count: int, post: Sequence[Candle], *, digits: Optional[int],
                        spread: Optional[float]) -> Dict[str, Any]:
    """Every rule declared in the strategy YAML, with its measured value. Not evaluable = FAIL."""
    spec = _raw_spec(strategy)
    symbol, box = ticket["symbol"], ticket.get("box") or {}
    hi, lo = box.get("high"), box.get("low")
    rng = (hi - lo) if hi is not None and lo is not None else None
    long = ticket.get("direction") == "LONG"
    entry, sl, risk = ticket.get("entry"), ticket.get("stop_loss"), ticket.get("risk_distance")
    sig = _signal_candle(ticket, post)
    pair = next(p for p in strategy.session_pairs if p.pair_id == ticket["cycle"])
    checks: List[Dict[str, Any]] = []

    checks.append(_check("R.reference_session", f"{pair.reference_session.name} box complete",
                         len(session), expected_bar_count,
                         PASS if len(session) >= expected_bar_count else FAIL))
    regime_spec = spec.get("regime_classification") or {}
    if "trend_bias_filter" in regime_spec:
        trend = regime_spec["trend_bias_filter"] or {}
        checks.append(_check("R.trend_bias_filter", f"{trend.get('indicator')}: {trend.get('bullish_condition')} / "
                             f"{trend.get('bearish_condition')}", None, None, NOT_EVALUABLE,
                             "spec gives no timeframe/price source; frozen engine does not consume it"))
    if "range_session_check" in regime_spec:
        range_cap = strategy.max_range_pips_eurusd
        pip = EVIDENCED_PIP.get(symbol) if symbol == "EURUSD" else None
        range_pips = round(rng / pip, 1) if rng is not None and pip else None
        checks.append(_check("R.range_session_check", "Reference_Session_Range_Pips <= Max_Allowed_Pips",
                             range_pips, range_cap if symbol == "EURUSD" else None, NOT_EVALUABLE,
                             "spec defines no gating semantics for the regime result"
                             + ("" if symbol == "EURUSD" else "; max_range_pips defined for EURUSD only")))
    branches = regime_spec.get("branches")
    if branches is not None:
        branch = next((b for b in branches.values() if b.get("engine_setup") == ticket.get("setup")), None)
        checks.append(_check("R.regime_branch", "engine branch declared and ticket-eligible", ticket.get("setup"),
                             "ELIGIBLE", PASS if branch and branch.get("ticket") == "ELIGIBLE" else FAIL,
                             (branch or {}).get("reason") or ("" if branch else "engine branch not declared")))

    trigger = "SWEEP_REFERENCE_LOW" if long else "SWEEP_REFERENCE_HIGH"
    if ticket.get("setup") != "SWEEP" or sig is None:
        checks.append(_check("R.entry_trigger", trigger, ticket.get("setup"), "SWEEP", FAIL,
                             "only sweep entries are declared in entry_rules"))
    else:
        swept = (sig.low < lo and sig.close > lo) if long else (sig.high > hi and sig.close < hi)
        checks.append(_check("R.entry_trigger", "wick breaches reference boundary and closes back inside",
                             {"high": sig.high, "low": sig.low, "close": sig.close}, {"box_high": hi, "box_low": lo},
                             PASS if swept else FAIL))
    checks.append(_check("R.entry_order_type", "entry_order_type", ticket.get("entry_order_type"),
                         strategy.entry_order_type,
                         PASS if ticket.get("entry_order_type") == strategy.entry_order_type else FAIL))
    side_spec = (spec.get("entry_rules") or {}).get("long_setup" if long else "short_setup") or {}
    if side_spec.get("entry_level") == "SWEEP_CANDLE_BODY_EDGE":
        edge = (min(sig.open, sig.close) if long else max(sig.open, sig.close)) if sig else None
        at_edge = sig is not None and _eq(entry, edge, digits)
        at_close = sig is not None and _eq(edge, sig.close, digits)
        need_close = side_spec.get("entry_must_equal_close") is True
        checks.append(_check("R.entry_level", "SWEEP_CANDLE_BODY_EDGE" + (" == close" if need_close else ""),
                             entry, {"body_edge": edge, "close": sig.close if sig else None},
                             PASS if at_edge and (at_close or not need_close) else FAIL,
                             "" if not at_edge or at_close or not need_close
                             else "ENTRY_NOT_AVAILABLE_AT_SIGNAL: body edge is the pre-signal open (fail closed)"))
    else:
        checks.append(_check("R.entry_level", "Sweep_Candle_Body_Close", entry, sig.close if sig else None,
                             PASS if sig is not None and _eq(entry, sig.close, digits) else FAIL))
    got_dist = abs(entry - sl) if entry is not None and sl is not None else None
    if strategy.risk.stop_loss_mode == "SWEEP_CANDLE_WICK_EXTREME":
        wick = (sig.low if long else sig.high) if sig else None
        positive = risk is not None and risk > 0
        checks.append(_check("R.stop_loss", "SWEEP_CANDLE_WICK_EXTREME, risk_distance > 0", sl, wick,
                             PASS if _eq(sl, wick, digits) and positive else FAIL,
                             "" if positive else "risk_distance <= 0 (fail closed)"))
    else:
        want_dist = rng * strategy.risk.stop_loss_range_pct if rng is not None else None
        checks.append(_check("R.stop_loss", f"{strategy.risk.stop_loss_mode} {strategy.risk.stop_loss_range_pct}",
                             got_dist, want_dist, PASS if _eq(got_dist, want_dist, digits) else FAIL))
    targets = {t["leg"]: t for t in ticket.get("targets") or []}
    tp1 = (targets.get(1) or {}).get("price")
    checks.append(_check("R.target_leg1", "OPPOSITE_SESSION_BOUNDARY", tp1, hi if long else lo,
                         PASS if _eq(tp1, hi if long else lo, digits) else FAIL))
    leg2 = next((leg for leg in strategy.legs if leg.target_type == "FIXED_R_MULTIPLE"), None)
    want_tp2 = (entry + (1 if long else -1) * leg2.fixed_r_multiple * risk) if leg2 and entry is not None and risk else None
    tp2 = (targets.get(2) or {}).get("price")
    checks.append(_check("R.target_leg2", f"FIXED_R_MULTIPLE {leg2.fixed_r_multiple if leg2 else None}", tp2, want_tp2,
                         PASS if _eq(tp2, want_tp2, digits) else FAIL))
    vols = [t.get("volume_pct") for t in targets.values()]
    checks.append(_check("R.position_split", "leg volume_pct", vols, [leg.volume_pct for leg in strategy.legs],
                         PASS if vols == [leg.volume_pct for leg in strategy.legs] else FAIL))
    checks.append(_check("R.max_entries_per_session", "max_entries_per_session", 1, pair.max_entries_per_session,
                         PASS if pair.max_entries_per_session >= 1 else FAIL, "engine emits one decision per session"))
    spread_pips = round(spread / EVIDENCED_PIP[symbol], 2) if spread is not None and symbol in EVIDENCED_PIP else None
    cap = strategy.risk.max_spread_allowed_pips
    checks.append(_check("R.max_spread", "spread_pips <= max_spread_allowed_pips", spread_pips, cap,
                         (PASS if spread_pips <= cap else FAIL) if spread_pips is not None else NOT_EVALUABLE,
                         "" if spread_pips is not None else "no live spread or no evidenced pip size"))
    rm = spec.get("risk_and_money_management") or {}
    if "max_spread_fraction_of_stop" in rm:
        frac = rm["max_spread_fraction_of_stop"]
        measured = round(spread / risk, 4) if spread is not None and risk else None
        conforms = frac == MAX_SPREAD_RISK_FRACTION
        checks.append(_check("R.max_spread_fraction", f"spread / stop <= {frac}", measured, frac,
                             (PASS if measured <= frac else FAIL) if measured is not None and conforms else FAIL,
                             "" if conforms else f"implemented guard is {MAX_SPREAD_RISK_FRACTION}"))
    if "signal_expiry_minutes" in rm:
        implemented = int(STALE_AFTER.total_seconds() // 60)
        checks.append(_check("R.signal_expiry", "signal_expiry_minutes", implemented, rm["signal_expiry_minutes"],
                             PASS if implemented == rm["signal_expiry_minutes"] else FAIL))
    if (spec.get("position_split_and_targets") or {}).get("target_order_rule") == "FAIL_CLOSED_IF_TP1_BEYOND_TP2":
        ordered = (tp1 is not None and tp2 is not None and entry is not None
                   and ((entry < tp1 <= tp2) if long else (entry > tp1 >= tp2)))
        checks.append(_check("R.target_order", "FAIL_CLOSED_IF_TP1_BEYOND_TP2", [entry, tp1, tp2],
                             "entry < TP1 <= TP2" if long else "entry > TP1 >= TP2", PASS if ordered else FAIL))
    checks.append(_check("R.time_invalidation", strategy.time_invalidation, ticket.get("time_invalidation_gmt"),
                         "15:00", PASS if ticket.get("time_invalidation_gmt") == "15:00" else FAIL))
    checks.append(_check("R.risk_mode", strategy.risk.risk_mode, None, None, NOT_APPLICABLE,
                         "no percentage in the spec; owner manual-ticket risk is separate (decision C4)"))
    checks.append(_check("R.slippage_limit", f"slippage_limit_points {strategy.risk.slippage_limit_points}",
                         None, strategy.risk.slippage_limit_points, NOT_APPLICABLE, "fill-time rule; owner enters manually"))
    checks.append(_check("R.post_fill_management", "leg actions after fill",
                         [(leg.action_on_fill, leg.trailing_rule) for leg in strategy.legs], None, NOT_APPLICABLE,
                         "post-fill trade management; displayed only"))
    if strategy.structural_invalidation == "NONE":
        checks.append(_check("R.structural_invalidation", "NONE", None, None, NOT_APPLICABLE,
                             "removed in the spec; a close beyond the wick extreme implies the stop was hit"))
    else:
        checks.append(_check("R.structural_invalidation", strategy.structural_invalidation, None, None, NOT_EVALUABLE,
                             "'expansion volume' has no measurable definition in the spec"))
    return _gate("L2", checks)


# ---------------------------------------------------------------------------------- L3

def l3_geometry(ticket: Dict[str, Any], post: Sequence[Candle], *, digits: Optional[int],
                declared_rr: Optional[float]) -> Dict[str, Any]:
    long = ticket.get("direction") == "LONG"
    entry, sl, risk = ticket.get("entry"), ticket.get("stop_loss"), ticket.get("risk_distance")
    targets = {t["leg"]: t.get("price") for t in ticket.get("targets") or []}
    tp1, tp2 = targets.get(1), targets.get(2)
    sig = _signal_candle(ticket, post)
    side = lambda a, b: a is not None and b is not None and (a > b if long else a < b)  # noqa: E731
    checks = [
        _check("L3.sl_side", "SL on the loss side of entry", sl, f"{'<' if long else '>'} {entry}",
               PASS if side(entry, sl) else FAIL),
        _check("L3.sl_beyond_invalidation", "SL at or beyond the trigger candle extreme", sl,
               (sig.low if long else sig.high) if sig else None,
               PASS if sig is not None and sl is not None and ((sl <= sig.low) if long else (sl >= sig.high)) else FAIL),
        _check("L3.entry_in_trigger_zone", "entry inside the trigger candle range", entry,
               [sig.low, sig.high] if sig else None,
               PASS if sig is not None and entry is not None and sig.low <= entry <= sig.high else FAIL),
        _check("L3.tp1_direction", "TP1 in trade direction", tp1, f"{'>' if long else '<'} {entry}",
               PASS if side(tp1, entry) else FAIL),
        _check("L3.tp2_direction", "TP2 in trade direction", tp2, f"{'>' if long else '<'} {entry}",
               PASS if side(tp2, entry) else FAIL),
        _check("L3.target_order", "LONG entry < TP1 <= TP2 / SHORT entry > TP1 >= TP2", [entry, tp1, tp2],
               "entry < TP1 <= TP2" if long else "entry > TP1 >= TP2",
               PASS if side(tp1, entry) and tp2 is not None and (tp1 <= tp2 if long else tp1 >= tp2) else FAIL),
    ]
    rr2 = abs(tp2 - entry) / risk if tp2 is not None and entry is not None and risk else None
    rr_ok = rr2 is not None and declared_rr is not None and abs(rr2 - declared_rr) * risk <= max(_point(digits), 1e-9)
    checks.append(_check("L3.rr_tp2", "computed RR equals declared RR", round(rr2, 6) if rr2 is not None else None,
                         declared_rr, PASS if rr_ok else FAIL,
                         "spec declares no RR tolerance; only price rounding (<= 1 point) is allowed"))
    return _gate("L3", checks)


# ---------------------------------------------------------------------------------- L4

def l4_data_session(ticket: Dict[str, Any], *, ref_window, trade_window, reference_name: str,
                    session: Sequence[Candle], expected_bar_count: int, post: Sequence[Candle],
                    data_close: Optional[dt.datetime], now: dt.datetime) -> Dict[str, Any]:
    age = (now - data_close).total_seconds() if data_close else None
    checks = [
        _check("L4.data_fresh", f"latest bar closed within {int(STALE_AFTER.total_seconds())} s",
               age, int(STALE_AFTER.total_seconds()),
               PASS if age is not None and 0 <= age <= STALE_AFTER.total_seconds() else FAIL),
        _check("L4.reference_bars_in_window", "reference bars inside the fixed-UTC reference window",
               [session[0].time.isoformat(), session[-1].time.isoformat()] if session else None,
               [ref_window[0].isoformat(), ref_window[1].isoformat()],
               PASS if session and all(ref_window[0] <= c.time and c.time + M15 <= ref_window[1] for c in session)
               else FAIL),
        _check("L4.reference_complete", "reference bar count", len(session), expected_bar_count,
               PASS if len(session) == expected_bar_count else FAIL),
        _check("L4.trade_bars_in_window", "decision bars inside the fixed-UTC trade window",
               len(post), [trade_window[0].isoformat(), trade_window[1].isoformat()],
               PASS if all(trade_window[0] <= c.time < trade_window[1] for c in post) else FAIL),
        _check("L4.reference_source", "box built from the pair's own reference session",
               ticket.get("cycle"), reference_name,
               PASS if session and all(c.time < trade_window[0] for c in session) else FAIL),
    ]
    return _gate("L4", checks)


# ---------------------------------------------------------------------------------- L5 / L6

def l5_cost(spread: Optional[float], risk: Optional[float], *, commission_r: Optional[float],
            warn_r: Optional[float]) -> Dict[str, Any]:
    """Cost in R. Advisory only: never blocks. Owner warn level has no default."""
    spread_r = spread / risk if spread is not None and risk else None
    cost_r = spread_r + commission_r if spread_r is not None and commission_r is not None else spread_r
    complete = spread_r is not None and commission_r is not None
    checks = [
        _check("L5.spread_R", "spread / stop distance", round(spread_r, 4) if spread_r is not None else None, None,
               PASS if spread_r is not None else WARN, "" if spread_r is not None else "SPREAD NOT AVAILABLE"),
        _check("L5.commission_R", "commission in R", commission_r, None,
               PASS if commission_r is not None else WARN, "" if commission_r is not None else "COMMISSION NOT AVAILABLE"),
        _check("L5.cost_vs_warn_level", "cost_in_R <= owner_ticket.cost_warn_R",
               round(cost_r, 4) if cost_r is not None else None, warn_r,
               PASS if complete and warn_r is not None and cost_r <= warn_r else WARN,
               "WARN LEVEL NOT SET" if warn_r is None else ("" if complete else "COST INCOMPLETE")),
    ]
    return _gate("L5", checks, advisory=True)


def l6_freshness(valid_until: Optional[str], stale_if: Any, invalid_if: Any) -> Dict[str, Any]:
    checks = [_check(f"L6.{name}", f"{name} set", value, "set", PASS if value else WARN)
              for name, value in (("valid_until", valid_until), ("stale_if", stale_if), ("invalid_if", invalid_if))]
    return _gate("L6", checks, advisory=True)


BLOCKING = ("L1", "L2", "L3", "L4")


def blocking_failures(gates: Dict[str, Dict[str, Any]]) -> List[str]:
    return [g for g in BLOCKING if gates.get(g, {}).get("status") != PASS]


# ---------------------------------------------------------------------------------- block reasons

TICKET_EXPIRED, L5_WARN = "TICKET_EXPIRED", "L5_WARN"
# Data/metadata absent or unusable (fail closed). STALE_DATA is a data-freshness failure, not a signal one.
DATA_METADATA_REASONS = {"STALE_DATA", "MARKET_CLOSED", "SPREAD_NOT_EVALUATED", "SYMBOL_METADATA_MISSING",
                         "ACCOUNT_BALANCE_UNAVAILABLE"}
_NORMALISE = {LEGACY_STALE_SIGNAL: SIGNAL_STALE}
# Lifecycle states are not reasons: a scan before the reference window closes (I7), or while the
# trade window is still open with no setup yet (scan_record.classify_fx_ticket WATCH), is neither
# blocked nor warned, so these never enter block_reasons[] or warnings[].
LIFECYCLE_STATES = frozenset({"REFERENCE_NOT_READY",
                              "SETUP_WINDOW_OPEN:NO_SETUP_BY_WINDOW_END",
                              "SETUP_WINDOW_OPEN:NO_QUALIFIED_SWEEP_IN_WINDOW"})


def normalise_reason(reason: str) -> str:
    return _NORMALISE.get(reason, reason)


def reason_severity(reason: str) -> int:
    """Lower = more severe. L1-L4 FAIL > DATA/METADATA missing > missing risk/cost config or
    COST_ABOVE_BLOCK_R > other blocking reasons (e.g. SPREAD_TOO_WIDE, authority) > stale/expired.
    Owner-approved 2026-10-06. L5_WARN ranks last but is a warning, never a block reason."""
    if reason.startswith("LOGIC_GATE_FAIL:"):
        return 0
    if reason.startswith("DATA_ERROR:") or reason in DATA_METADATA_REASONS:
        return 1
    if reason in ("RISK_CONFIG_MISSING", "COST_ABOVE_BLOCK_R"):
        return 2
    if reason == L5_WARN:
        return 5
    if reason in (SIGNAL_STALE, TICKET_EXPIRED):
        return 4
    return 3


def order_block_reasons(reasons: Sequence[Optional[str]]) -> List[str]:
    """Blocking reasons only (warnings dropped), deduplicated, ordered by severity; original
    order breaks ties (L1 before L2 ...)."""
    seen: List[str] = []
    for r in reasons:
        if r and is_blocking(normalise_reason(r)) and normalise_reason(r) not in seen:
            seen.append(normalise_reason(r))
    return sorted(seen, key=lambda r: (reason_severity(r), seen.index(r)))


def is_blocking(reason: str) -> bool:
    return reason not in LIFECYCLE_STATES and reason_severity(reason) < reason_severity(L5_WARN)
