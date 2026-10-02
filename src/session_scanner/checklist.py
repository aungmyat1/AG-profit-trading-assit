"""Checklist: CONTEXT -> LOCATION -> TRIGGER -> RISK PARAMETERS -> EXECUTION ELIGIBILITY -> AUDIT.

Pure function over already-computed deterministic facts. The final state is derived in a
fixed precedence order; nothing here can turn an engine NO_TRADE into READY.
"""
from __future__ import annotations

from typing import List, Optional

from .quality import FRESH, VALID
from .strategy_adapter import (ADAPTER_BOX_INCOMPLETE, ADAPTER_SIGNAL, ADAPTER_SYMBOL_NOT_IN_CONTRACT,
                               AdapterResult, ProposalScope)

PASS, FAIL = "PASS", "FAIL"
NOT_AUTHORIZED = "NOT_AUTHORIZED"
OBSERVED_ONLY = "OBSERVED_ONLY"

READY = "READY"
NO_TRADE = "NO_TRADE"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
OUT_OF_SESSION = "OUT_OF_SESSION"
STRATEGY_NOT_AUTHORIZED = "STRATEGY_NOT_AUTHORIZED"

MANDATORY_TIMEFRAMES = ("D1", "H1", "M15", "M5")


def spread_gate(quote, asset_class: str, max_spread_pips: Optional[float]) -> dict:
    if quote is None:
        return {"status": FAIL, "reason": "NO_QUOTE"}
    if asset_class != "FX" or max_spread_pips is None:
        # No signed pip convention / threshold for this asset class: observe, never invent a limit.
        return {"status": OBSERVED_ONLY, "reason": "SPREAD_OBSERVED", "spread_points": quote.spread_points}
    ok = quote.spread_pips <= max_spread_pips
    return {"status": PASS if ok else FAIL, "reason": "WITHIN_CONTRACT_MAX" if ok else "SPREAD_EXCEEDS_CONTRACT_MAX",
            "spread_pips": round(quote.spread_pips, 3), "max_spread_allowed_pips": max_spread_pips}


def signal_entry_status(signal, last_closed_m15) -> tuple:
    """The contract's entry is MARKET at the sweep candle's body close, "entered immediately
    after signal detection" (ST_ASIAN_SWEEP_5R_V1.yaml entry_rules comment). So an engine
    SIGNAL is actionable only while its signal candle is the latest closed M15 bar; an older
    signal is reported, never re-offered as a fresh market entry."""
    if signal is None or signal.status != "SIGNAL":
        return False, None
    if signal.signal_timestamp is None:
        return False, "ENTRY_TIMING_NOT_DEFINED_FOR_SETUP"  # e.g. TREND box-mid entry has no signal candle
    if last_closed_m15 is None or signal.signal_timestamp != last_closed_m15:
        return False, "SIGNAL_ENTRY_WINDOW_PASSED"
    return True, None


def evaluate_checklist(*, time_gate: str, series_status: dict, quote_status: Optional[str],
                       cycle: Optional[str], strategy_scan_allowed: bool, adapter: Optional[AdapterResult],
                       location_events: List[dict], scope: Optional[ProposalScope], spread: dict,
                       signal_entry: tuple = (True, None)) -> dict:
    data_issues = []
    if time_gate != PASS:
        data_issues.append("TIME_GATE_FAIL")
    for tf in MANDATORY_TIMEFRAMES:
        if series_status.get(tf) != VALID:
            data_issues.append(f"{tf}_{series_status.get(tf, 'MISSING')}")
    if quote_status != FRESH:
        data_issues.append(f"QUOTE_{quote_status or 'MISSING'}")
    if adapter is not None and adapter.status == ADAPTER_BOX_INCOMPLETE:
        data_issues.append("REFERENCE_BOX_INCOMPLETE")

    rows = {"DATA": FAIL if data_issues else PASS,
            "SESSION": PASS if cycle else FAIL,
            "STRATEGY": PASS if strategy_scan_allowed and adapter is not None
            and adapter.status != ADAPTER_SYMBOL_NOT_IN_CONTRACT else FAIL}

    sig = adapter.signal if adapter else None
    rows["CONTEXT"] = PASS if sig is not None else FAIL
    trend_context = sig is not None and sig.regime == "TREND"
    rows["LOCATION"] = PASS if (trend_context or location_events) else FAIL
    engine_signal = adapter is not None and adapter.status == ADAPTER_SIGNAL
    entry_open, entry_reason = signal_entry
    rows["TRIGGER"] = PASS if engine_signal and entry_open else FAIL

    if spread["status"] == FAIL:
        rows["RISK"] = FAIL
    elif scope is None or not scope.authorized:
        rows["RISK"] = NOT_AUTHORIZED
    else:
        rows["RISK"] = PASS

    contradictions = []
    if engine_signal and rows["LOCATION"] == FAIL:
        contradictions.append("ENGINE_SIGNAL_WITHOUT_DESCRIPTIVE_LOCATION_EVENT")

    if rows["DATA"] == FAIL:
        state, reason = INSUFFICIENT_DATA, ",".join(data_issues)
    elif rows["SESSION"] == FAIL:
        state, reason = OUT_OF_SESSION, "NO_ACTIVE_TRADE_CYCLE"
    elif rows["STRATEGY"] == FAIL:
        state, reason = STRATEGY_NOT_AUTHORIZED, adapter.status if adapter else "NO_SCANNER_ADAPTER"
    elif rows["TRIGGER"] == FAIL:
        state = NO_TRADE
        reason = f"{entry_reason}:{adapter.reason}" if engine_signal else (adapter.reason or adapter.status)
    elif rows["RISK"] == FAIL:
        state, reason = NO_TRADE, spread.get("reason", "RISK_FAIL")
    elif rows["RISK"] == NOT_AUTHORIZED:
        state, reason = STRATEGY_NOT_AUTHORIZED, f"SIGNAL_OUTSIDE_PROPOSAL_SCOPE:{scope.reason if scope else 'NONE'}"
    else:
        state, reason = READY, sig.reason_code

    return {"checklist": rows, "result": state, "reason": reason, "contradictions": contradictions,
            "spread_gate": spread}
