"""Strategy governance view + the one live adapter (ST_ASIAN_SWEEP_5R_V1 via strategy_engine.evaluate).

Governance is READ from strategies/registry.yaml and the release's pilot configs; it is never
promoted or written here. The adapter feeds the frozen engine CLOSED M15 candles only and
passes its TradeSignal through untouched -- no rule is reinterpreted.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List, Optional

import yaml

from post_asian_pilot.pilot_config import PilotConfig, load_pilot_config
from strategy_engine.engine import evaluate
from strategy_engine.loader import load_strategy
from strategy_engine.models import StrategyConfig, TradeSignal

from .market_state import to_engine_candles

REGISTRY_PATH = "strategies/registry.yaml"

ADAPTER_SIGNAL = "SIGNAL"
ADAPTER_NO_TRADE = "NO_TRADE"
ADAPTER_BOX_INCOMPLETE = "BOX_INCOMPLETE"
ADAPTER_REFERENCE_OPEN = "REFERENCE_SESSION_NOT_COMPLETE"
ADAPTER_SYMBOL_NOT_IN_CONTRACT = "SYMBOL_NOT_IN_CONTRACT"


def _t(s: str) -> time:
    return time.fromisoformat(s)


def _contract_meta(config_source: str) -> dict:
    if not (isinstance(config_source, str) and config_source.endswith(".yaml") and os.path.exists(config_source)):
        return {}
    with open(config_source, "r", encoding="utf-8") as f:
        c = yaml.safe_load(f) or {}
    sessions = [p.get("pair_id") for p in c.get("session_pairs", []) if isinstance(p, dict)]
    return {"version": c.get("version"), "supported_symbols": c.get("instruments"), "supported_sessions": sessions or None}


def strategy_catalog(scanner_cfg: dict, registry_path: str = REGISTRY_PATH) -> List[dict]:
    with open(registry_path, "r", encoding="utf-8") as f:
        reg = yaml.safe_load(f)["strategies"]
    adapters = scanner_cfg.get("strategy_adapters", {})
    out = []
    for sid, entry in reg.items():
        meta = _contract_meta(entry.get("config_source"))
        adapter = adapters.get(sid)
        scope = []
        if adapter:
            for pair_id, path in adapter.get("proposal_scope", {}).items():
                p = load_pilot_config(path)
                scope.append({"pair_id": pair_id, "symbols": list(p.universe), "risk_per_trade_pct": p.risk_per_trade_pct,
                              "pilot_id": p.pilot_id})
        out.append({
            "strategy_id": sid,
            "version": meta.get("version"),
            "supported_symbols": meta.get("supported_symbols"),
            "supported_sessions": meta.get("supported_sessions"),
            "research_status": entry.get("research_lifecycle"),
            "scanner_adapter": adapter["adapter"] if adapter else "NONE",
            "opportunity_scan_allowed": bool(entry.get("registered")) and adapter is not None,
            "ticket_proposal_allowed": scope if scope else False,
            "demo_execution_allowed": bool(entry.get("demo_authorized")),  # reported only; scanner never executes
            "live_execution_allowed": bool(entry.get("live_authorized")),
        })
    return out


@dataclass(frozen=True)
class ProposalScope:
    authorized: bool
    reason: str
    risk_per_trade_pct: Optional[float] = None
    pilot_id: Optional[str] = None


def resolve_proposal_scope(strategy: StrategyConfig, pair_id: str, canonical_symbol: str,
                           pilots: Dict[str, PilotConfig]) -> ProposalScope:
    pilot = pilots.get(pair_id)
    if pilot is None:
        return ProposalScope(False, "NO_PROPOSAL_SCOPE_FOR_CYCLE")
    if pilot.strategy_id != strategy.strategy_id or str(pilot.strategy_version) != str(strategy.version):
        return ProposalScope(False, "RISK_POLICY_AMBIGUOUS:PILOT_STRATEGY_IDENTITY_MISMATCH")
    if canonical_symbol not in pilot.universe:
        return ProposalScope(False, "SYMBOL_OUTSIDE_PILOT_UNIVERSE", pilot_id=pilot.pilot_id)
    return ProposalScope(True, "PILOT_SCOPE", pilot.risk_per_trade_pct, pilot.pilot_id)


@dataclass(frozen=True)
class AdapterResult:
    status: str
    pair_id: str
    signal: Optional[TradeSignal]
    reference_window: tuple
    trade_window: tuple
    reference_bars: int
    expected_reference_bars: int
    post_bars: tuple
    reason: str = ""


class AsianSweepAdapter:
    strategy_id = "ST_ASIAN_SWEEP_5R_V1"

    def __init__(self, contract_path: str, proposal_scope_paths: Dict[str, str]):
        self.strategy = load_strategy(contract_path)
        self.pilots = {pair: load_pilot_config(p) for pair, p in proposal_scope_paths.items()}

    def cycles(self) -> Dict[str, tuple]:
        return {p.pair_id: (_t(p.trade_session.start_time_gmt), _t(p.trade_session.end_time_gmt))
                for p in self.strategy.session_pairs}

    def evaluate_cycle(self, pair_id: str, canonical_symbol: str, day: date, m15_closed, now_utc: datetime) -> AdapterResult:
        pair = next(p for p in self.strategy.session_pairs if p.pair_id == pair_id)
        b = lambda s: datetime.combine(day, _t(s), tzinfo=timezone.utc)  # noqa: E731
        ref = (b(pair.reference_session.start_time_gmt), b(pair.reference_session.end_time_gmt))
        trade = (b(pair.trade_session.start_time_gmt), b(pair.trade_session.end_time_gmt))
        expected = int((ref[1] - ref[0]) / timedelta(minutes=15))
        session = [x for x in m15_closed if ref[0] <= x.time_utc < ref[1]]
        post = tuple(x for x in m15_closed
                     if trade[0] <= x.time_utc < trade[1] and x.time_utc + timedelta(minutes=15) <= now_utc)
        base = dict(pair_id=pair_id, reference_window=ref, trade_window=trade,
                    reference_bars=len(session), expected_reference_bars=expected, post_bars=post)
        if canonical_symbol not in self.strategy.instruments:
            return AdapterResult(ADAPTER_SYMBOL_NOT_IN_CONTRACT, signal=None, **base)
        if now_utc < ref[1]:
            return AdapterResult(ADAPTER_REFERENCE_OPEN, signal=None, **base)
        try:
            sig = evaluate(self.strategy, pair_id, canonical_symbol, day, to_engine_candles(session), expected,
                           post_session_candles=to_engine_candles(post))
        except ValueError as exc:
            return AdapterResult(ADAPTER_BOX_INCOMPLETE, signal=None, reason=str(exc), **base)
        return AdapterResult(ADAPTER_SIGNAL if sig.status == "SIGNAL" else ADAPTER_NO_TRADE, signal=sig,
                             reason=sig.reason_code, **base)
