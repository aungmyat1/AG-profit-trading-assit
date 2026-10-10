"""Offline CFD L1-L6 evidence; no admission or broker authority.

Numbering matches the ASW verification report: identity, equivalence, causality,
geometry, friction, freshness. Shared gate evidence shapes and cost policy are reused.
"""
from __future__ import annotations

import datetime as dt
import math

import yaml

from crypto_cfd_contract.contract import CONTRACT_ID, CONTRACT_VERSION
from crypto_cfd_contract import rules
from market_structure.config import load_market_structure_config
from strategy_engine.sweep_retest.sweep import find_qualified_sweep, SWEEP_LOW, SWEEP_HIGH
from strategy_engine.sweep_retest.mss import find_mss
from strategy_engine.sweep_retest.retest import find_retest
from v1_tickets.authority import REPO_ROOT, logic_identity
from v1_tickets.logic_gate import _check, _gate, PASS, FAIL, WARN, l6_freshness
from v1_tickets.manual_ticket import crypto_cfd_cost_gate
from ticket_delivery.renderer import payload_hash

STEPS = {"d1": dt.timedelta(days=1), "h1": dt.timedelta(hours=1),
         "m15": dt.timedelta(minutes=15), "m5": dt.timedelta(minutes=5)}


def verify_case(case: dict, candles: dict, policy: dict, *, structure_config=None) -> dict:
    """Replay caller-supplied closed UTC candles, independently check chain and prices."""
    now = dt.datetime.fromisoformat(case["now"])
    cfg = structure_config or load_market_structure_config()
    def replay(at=now, rows=candles):
        closed = {k: [c for c in rows[k] if c.time + step <= at] for k, step in STEPS.items()}
        return rules.evaluate(case["symbol"], at, closed["d1"], closed["h1"],
                              closed["m5"], closed["m15"], structure_config=cfg)
    result = replay()
    evidence = result["evidence"]
    gates = {}
    def gate(name, checks):
        gates[name] = _gate(name, [_check(f"{name}.{key}", key, value, expected,
                                        PASS if ok else FAIL) for key, value, expected, ok in checks])
    identity = logic_identity(CONTRACT_ID, CONTRACT_VERSION)
    gate("L1", [("identity", identity, "exact contract/engine", identity is not None),
                ("binding", [result["contract_id"], result["contract_version"]],
                 [CONTRACT_ID, CONTRACT_VERSION], result["contract_id"] == CONTRACT_ID
                 and result["contract_version"] == CONTRACT_VERSION),
                ("determinism", payload_hash(result), payload_hash(replay()), result == replay())])
    m5 = candles["m5"]
    reference = rules.previous_day_reference(m5, now)
    expected_result = case.get("expected_result")
    spec = yaml.safe_load((REPO_ROOT / "strategies/ST_CRYPTO_CFD_SWEEP_RETEST_V1.yaml").read_text())
    checks = [("contract_binding", [spec["strategy_id"], str(spec["version"])],
               [CONTRACT_ID, CONTRACT_VERSION], spec["strategy_id"] == CONTRACT_ID
               and str(spec["version"]) == CONTRACT_VERSION),
              ("structure_spec", spec["context_contract"]["structure_params"],
               {"swing_length": cfg.swing_length, "close_break": cfg.close_break},
               spec["context_contract"]["structure_params"] ==
               {"swing_length": cfg.swing_length, "close_break": cfg.close_break}),
              ("expiry_spec", spec["m5_trigger_contract"]["retest"]["max_bars_after_mss"],
               "3 completed M5 candles", str(spec["m5_trigger_contract"]["retest"]["max_bars_after_mss"]).startswith("3 completed M5 candles")),
              ("M15_observation", spec["timeframe_responsibilities"]["m15"], "OBSERVATION_ONLY_STRUCTURE_RECORD",
               spec["timeframe_responsibilities"]["m15"] == "OBSERVATION_ONLY_STRUCTURE_RECORD"),
              ("expected_result", result["result"], expected_result,
               expected_result is not None and result["result"] == expected_result),
              ("production_structure", [cfg.swing_length, cfg.close_break], [5, True],
               cfg.swing_length == 5 and cfg.close_break is True)]
    plan = evidence.get("target_plan") or {}
    if result["result"] == "ENTRY_VALID" and reference:
        long = plan["direction"] == "LONG"
        today = [c for c in m5 if now.replace(hour=0, minute=0, second=0, microsecond=0) <= c.time
                 and c.time + STEPS["m5"] <= now]
        sweep = find_qualified_sweep(today, reference.session_high, reference.session_low,
                                     required_direction=SWEEP_LOW if long else SWEEP_HIGH)
        mss = find_mss(sweep, [c for c in today if c.time <= sweep.candle_time],
                       [c for c in today if c.time > sweep.candle_time], cfg) if sweep else None
        retest = find_retest(mss, [c for c in today if c.time > mss.confirming_candle.time],
                            ttl_bars=3) if mss else None
        permission, _ = rules.direction_permission(rules.confirmed_direction(candles["d1"], cfg),
                                                    rules.confirmed_direction(candles["h1"], cfg))
        checks += [("context_permission", evidence["context"]["direction_permission"], permission,
                    evidence["context"]["direction_permission"] == permission),
                   ("direction", plan["direction"], case.get("expected_direction"),
                    plan["direction"] == case.get("expected_direction")),
                   ("permission", evidence["context"]["direction_permission"],
                    "LONG_ALLOWED" if long else "SHORT_ALLOWED",
                    evidence["context"]["direction_permission"] == ("LONG_ALLOWED" if long else "SHORT_ALLOWED")),
                   ("sweep_mss_retest", plan["entry"], retest.entry_price if retest else None,
                    retest is not None and plan["entry"] == retest.entry_price),
                   ("sequence_evidence", [evidence.get("sweep"), evidence.get("mss"), evidence.get("retest")],
                    "reconstructed confirmed chain, TTL <= 3", sweep is not None and mss is not None
                    and retest is not None
                    and evidence["sweep"]["candle_time_utc"] == sweep.candle_time.isoformat()
                    and evidence["mss"]["confirmed_at_utc"] == mss.confirmed_at.isoformat()
                    and evidence["mss"]["broken_swing_price"] == mss.broken_swing_price
                    and evidence["retest"]["candle_time_utc"] == retest.candle_time.isoformat()
                    and evidence["retest"]["bars_after_mss"] == retest.bars_after_mss <= 3),
                   ("stop", plan["stop_loss"], sweep.extreme_price if sweep else None,
                    sweep is not None and plan["stop_loss"] == sweep.extreme_price),
                   ("targets", [plan["tp1"], plan["tp2"]],
                    [reference.session_mid, reference.session_high if long else reference.session_low],
                    plan["tp1"] == reference.session_mid and plan["tp2"] ==
                    (reference.session_high if long else reference.session_low)),
                   ("split", plan["tp1_volume_pct"], 0.5, plan["tp1_volume_pct"] == spec["targets_contract"]["tp1_volume_pct"] == 0.5)]
    gate("L2", checks)
    # Check each input's full close, ordering, OHLC, and exact previous-day grid.
    valid_rows = all(rows and all(c.time.utcoffset() == dt.timedelta(0)
                     and c.time + STEPS[k] <= now and all(math.isfinite(v) for v in
                     (c.open, c.high, c.low, c.close)) and c.low <= min(c.open, c.close)
                     <= max(c.open, c.close) <= c.high for c in rows)
                     and all(a.time + STEPS[k] <= b.time for a, b in zip(rows, rows[1:]))
                     for k, rows in candles.items())
    start, end = rules.previous_utc_day_window(now)
    grid = [c.time for c in m5 if start <= c.time < end]
    exact = grid == [start + i * STEPS["m5"] for i in range(288)]
    # Appending future observations must not rewrite the semantic historical result.
    future = {k: rows + [type(rows[-1])(now + STEPS[k], 1, 2, 0.5, 1)] if rows else []
              for k, rows in candles.items()}
    unchanged = replay(rows=future) == result
    timing = True
    if result["result"] == "ENTRY_VALID":
        sweep_at = dt.datetime.fromisoformat(evidence["sweep"]["candle_time_utc"])
        mss_at = dt.datetime.fromisoformat(evidence["mss"]["confirmed_at_utc"])
        retest_at = dt.datetime.fromisoformat(evidence["retest"]["candle_time_utc"])
        timing = sweep_at < mss_at < retest_at and retest_at + STEPS["m5"] <= now
        before = replay(at=retest_at)
        timing = timing and before["result"] != "ENTRY_VALID"
    gate("L3", [("closed_UTC_OHLC", valid_rows, True, valid_rows),
                ("reference_grid", len(grid), 288, exact),
                ("future_invariance", unchanged, True, unchanged),
                ("sequence_causality", timing, True, timing)])
    if plan and result["result"] == "ENTRY_VALID":
        entry, sl, tp1, tp2, risk = (plan[k] for k in ("entry", "stop_loss", "tp1", "tp2", "risk_distance"))
        long = plan["direction"] == "LONG"
        ordered = sl < entry < tp1 <= tp2 if long else sl > entry > tp1 >= tp2
        geometry = risk > 0 and risk == abs(entry - sl) and ordered
        rr = abs(tp2 - entry) / risk if risk > 0 else None
        gate("L4", [("geometry", [sl, entry, tp1, tp2], "directional order", geometry),
                    ("RR", rr, plan["tp2_r_multiple"], rr is not None and rr >= spec["targets_contract"]["min_tp2_r_multiple"] == 1.5
                     and math.isclose(rr, plan["tp2_r_multiple"]))])
        blocks, warnings, pct, cost = crypto_cfd_cost_gate(risk, case.get("spread"),
                                                        case.get("commission_R"), policy)
        quote = dt.datetime.fromisoformat(case["quote_time"]) if case.get("quote_time") else None
        gate("L5", [("friction_block", blocks, [], not blocks),
                    ("quote_fresh", case.get("quote_time"), "within 15 minutes",
                     quote is not None and quote.tzinfo is not None and dt.timedelta(0) <= now - quote <= dt.timedelta(minutes=15))])
        gates["L5"]["spread_pct_of_stop"] = pct if math.isfinite(pct) else None
        gates["L5"]["cost_R"] = cost if math.isfinite(cost) else None
        gates["L5"]["warnings"] = warnings + (["COMMISSION_UNKNOWN"] if case.get("commission_R") is None else [])
        if gates["L5"]["status"] == PASS and gates["L5"]["warnings"]:
            gates["L5"]["status"] = WARN
        until = retest_at + STEPS["m5"] + dt.timedelta(minutes=15)
        gates["L6"] = l6_freshness(until.isoformat(), ["QUOTE_STALE", "SIGNAL_STALE"],
                                   ["UTC_DAY_ROTATION", "REFERENCE_INCOMPLETE"])
        if not retest_at + STEPS["m5"] <= now <= until:
            gates["L6"]["status"] = FAIL
    else:
        for name in ("L4", "L5", "L6"):
            gates[name] = {"gate": name, "status": "NOT_EVIDENCED", "checks": []}
    return {"result": result, "gates": gates, "logic_identity": identity,
            "execution_authorized": False, "edge_verified": False}
