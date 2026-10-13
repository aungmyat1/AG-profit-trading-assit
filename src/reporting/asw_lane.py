"""ASW observational lane (AGP-C18-R2, owner decision D2).

Evaluates the declared FX session scopes read-only with the frozen v1.1.2 candidate contract
(`fx.SCOPED_CANDIDATE_PATH`) and without the runtime S1 scope block, producing REPORT_ONLY
observations. S1 (GBPUSD x ASIAN_LONDON) is skipped: its existing canonical READY path is untouched.
EURUSD x ASIAN_LONDON stays SUSPENDED (L3) and is reported as a BLOCKED diagnostic without evaluation.
Strategy rules are not modified; nothing here can produce READY.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Callable, Dict, List, Optional, Sequence

import yaml

from reporting.common import archive_observation, block, observational_canonical
from v1_tickets import fx as v1_fx

FAMILY = "session_fx_gold"
S1_SCOPE = ("GBPUSD", "ASIAN_LONDON")
SUSPENDED_SCOPES = {("EURUSD", "ASIAN_LONDON"): "SUSPENDED_L3_REPAINT"}
STRATEGY_PATH = v1_fx.SCOPED_CANDIDATE_PATH          # v1.1.2 candidate; v1.1.3 (PR #186) stays separate


def evaluate_scope(symbol: str, cycle: str, *, now: dt.datetime, day: dt.date,
                   candle_provider: Callable[..., Any], data_source: str = "MT5_VT_MARKETS_DEMO",
                   policy=None) -> Optional[Dict[str, Any]]:
    """One observational canonical ticket for (symbol, cycle), or None for S1 (owned by the canonical path)."""
    if (symbol, cycle) == S1_SCOPE:
        return None
    trade_end = v1_fx.session_windows_utc(day, strategy_path=STRATEGY_PATH)[cycle]["trade"][1]
    blocked = SUSPENDED_SCOPES.get((symbol, cycle))
    if blocked:
        raw = v1_fx.build_fx_error_ticket(symbol, cycle, day, evaluated_at=now, reason_code=blocked,
                                          detail="scope suspended for this strategy version; not evaluated",
                                          decision="BLOCKED", data_source=data_source,
                                          strategy_path=STRATEGY_PATH)
        return observational_canonical(raw, now=now, window_end=trade_end, report_class="BLOCKED", policy=policy)
    try:
        bundle = candle_provider(symbol, cycle, day, now)
    except Exception as exc:  # noqa: BLE001 -- data failure is an observation, never a guess
        raw = v1_fx.build_fx_error_ticket(symbol, cycle, day, evaluated_at=now, reason_code=type(exc).__name__,
                                          detail=str(exc)[:300], decision="DATA_ERROR", data_source=data_source,
                                          strategy_path=STRATEGY_PATH)
        return observational_canonical(raw, now=now, window_end=trade_end, report_class="DATA_ERROR", policy=policy)
    if bundle is None:
        raw = v1_fx.build_fx_error_ticket(symbol, cycle, day, evaluated_at=now, reason_code="NO_CANDLE_DATA",
                                          detail="candle provider returned no data", decision="DATA_ERROR",
                                          data_source=data_source, strategy_path=STRATEGY_PATH)
        return observational_canonical(raw, now=now, window_end=trade_end, report_class="DATA_ERROR", policy=policy)
    raw = v1_fx.build_fx_ticket(symbol, cycle, day, list(bundle.session_candles), bundle.expected_bar_count,
                                list(bundle.post_session_candles), data_source=data_source, evaluated_at=now,
                                data_close=bundle.data_close, spread=bundle.spread, strategy_path=STRATEGY_PATH,
                                runtime_scope=False)
    canonical = observational_canonical(raw, now=now, current_price=bundle.current_price, window_end=trade_end,
                                        policy=policy)
    return finalize_candidate(canonical)


def finalize_candidate(canonical: Dict[str, Any]) -> Dict[str, Any]:
    """Contract target order first, then: a SUSPENDED scope is never presented as a candidate."""
    canonical = enforce_target_order(canonical, STRATEGY_PATH)
    if canonical.get("report_class") == "CANDIDATE" and canonical.get("scope_verification_status") == "SUSPENDED":
        block(canonical, "SCOPE_SUSPENDED")
    return canonical


def contract_target_order_rule(strategy_path: str) -> Optional[str]:
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    spec = yaml.safe_load((root / strategy_path).read_text(encoding="utf-8")) or {}
    return (spec.get("position_split_and_targets") or {}).get("target_order_rule")


def enforce_target_order(canonical: Dict[str, Any], strategy_path: str) -> Dict[str, Any]:
    """The frozen contract's own rule: TP1 beyond TP2 fails closed. Reporting-only; prices are never
    swapped or relabelled, and a missing rule leaves the observation unchanged."""
    if canonical.get("report_class") != "CANDIDATE":
        return canonical
    rule = contract_target_order_rule(strategy_path)
    prices = canonical.get("prices") or {}
    tp1, tp2, direction = prices.get("tp1_raw"), prices.get("tp2_raw"), canonical.get("direction")
    if rule != "FAIL_CLOSED_IF_TP1_BEYOND_TP2" or tp1 is None or tp2 is None:
        return canonical
    if (direction == "LONG" and tp1 > tp2) or (direction == "SHORT" and tp1 < tp2):
        return block(canonical, "TARGET_ORDER_INVALID:FAIL_CLOSED_IF_TP1_BEYOND_TP2")
    return canonical


def run_asw_lane(*, now: dt.datetime, day: dt.date, cycles: Sequence[str], candle_provider: Callable[..., Any],
                 archive_root: str, data_source: str = "MT5_VT_MARKETS_DEMO", policy=None) -> List[Dict[str, Any]]:
    """All non-S1 declared scopes of the given cycles, each archived before it is returned."""
    out: List[Dict[str, Any]] = []
    for cycle in cycles:
        for symbol in v1_fx.V1_FX_SYMBOLS:
            canonical = evaluate_scope(symbol, cycle, now=now, day=day, candle_provider=candle_provider,
                                       data_source=data_source, policy=policy)
            if canonical is not None:
                archive_observation(archive_root, FAMILY, canonical)
                out.append(canonical)
    return out
