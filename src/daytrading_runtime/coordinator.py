"""RuntimeCoordinator.run_cycle() (spec section 25): one evaluation pass over the
SESSION and SMC workflows. Orchestration only -- every fetch/evaluate call below
delegates to an existing, already-verified capability; nothing here computes a
regime, a bias, a gap, a POI, or a sweep itself.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

import session_clock as sc
from daytrading.decision.market_bias import derive_market_bias
from daytrading_workflow.universe import DEFAULT_STRATEGY_PATH, load_session_universe
from entry_confirmation.models import EntryConfirmationRequest
from mt5.market_data import MarketDataError, get_candles
from runtime_state.store import JsonKeyValueStore
from strategy_engine.loader import load_strategy

from .session_runtime import PersistentSessionRuntime
from .smc_runtime import PersistentSMCRuntime
from .snapshot import build_symbol_snapshot

# Only names that ARE genuinely one of canonical_sessions.yaml's frozen boxes belong
# here -- same mapping scripts/run_strategy.py already uses (not re-derived).
_CANONICAL_REFERENCE_SESSION = {"Asian": "asian", "London": "london_am"}

DEFAULT_STATE_DIR = "journal/runtime"


class RuntimeCoordinator:
    def __init__(
        self,
        session_strategy_path: str = DEFAULT_STRATEGY_PATH,
        state_dir: str = DEFAULT_STATE_DIR,
        alert_sink: Optional[Any] = None,
    ):
        self.session_strategy_path = session_strategy_path
        self.session_runtime = PersistentSessionRuntime(
            JsonKeyValueStore(f"{state_dir}/session_events.json"),
        )
        self.smc_runtime = PersistentSMCRuntime(
            JsonKeyValueStore(f"{state_dir}/smc_alerts.json"),
            JsonKeyValueStore(f"{state_dir}/bar_cursors.json"),
            alert_sink=alert_sink,
        )

    def run_cycle(self) -> Dict[str, Any]:
        now_utc = dt.datetime.now(dt.timezone.utc)
        return {
            "runtime": {"mode": "READ_ONLY", "execution_submission": "DISABLED", "cycle_time_utc": now_utc.isoformat()},
            "session": self._run_session_cycle(now_utc),
            "smc": self._run_smc_cycle(now_utc),
        }

    def _run_session_cycle(self, now_utc: dt.datetime) -> Dict[str, Any]:
        strategy = load_strategy(self.session_strategy_path)
        universe = load_session_universe(self.session_strategy_path)
        results: List[Dict[str, Any]] = []

        for pair in strategy.session_pairs:
            canonical_name = _CANONICAL_REFERENCE_SESSION.get(pair.reference_session.name)
            if canonical_name is None:
                continue  # no canonical mapping -- not this coordinator's job to guess one

            session_date = now_utc.date()
            if not sc.session_complete(now_utc, session_date, canonical_name):
                continue  # SESSION_INCOMPLETE -- not yet a completion event, nothing to evaluate

            ref_start, ref_end = sc.get_session_bounds(session_date, canonical_name)
            expected_bars = sc.expected_bar_count(canonical_name, strategy.timeframe)

            for symbol in universe.configured_symbols:
                try:
                    ref_candles = get_candles(symbol, strategy.timeframe, ref_start, ref_end)
                    bias = derive_market_bias(symbol, timeframe="H1")
                except MarketDataError as exc:
                    results.append({"symbol": symbol, "reference_session": pair.reference_session.name,
                                     "status": "DATA_ERROR", "reason_code": exc.reason_code})
                    continue

                record = self.session_runtime.process_symbol(
                    strategy.strategy_id, symbol, pair.reference_session.name, session_date,
                    ref_candles, expected_bars, bias, evaluation_time=now_utc,
                )
                if record is not None:
                    results.append(record)

        return {"strategy_id": strategy.strategy_id, "configured_symbols": list(universe.configured_symbols),
                "configured_symbol_count": len(universe.configured_symbols), "events": results}

    def _run_smc_cycle(self, now_utc: dt.datetime) -> Dict[str, Any]:
        universe = load_session_universe(self.session_strategy_path)  # spec section 2: pluggable, same config for now
        alerts: List[Dict[str, Any]] = []
        watching: List[Dict[str, Any]] = []

        for symbol in universe.configured_symbols:
            snapshot = build_symbol_snapshot(symbol)
            record = self.smc_runtime.evaluate_and_persist(
                "SMC_CONDITIONAL", symbol, e1_result=snapshot.e1, e2_result=snapshot.e2,
                e3_result=snapshot.e3_sell_side if snapshot.e3_sell_side.triggered else snapshot.e3_buy_side,
                evaluation_time=now_utc,
            )
            if record is not None:
                alerts.append(record)
            else:
                watching.append({
                    "symbol": symbol, "e1": snapshot.e1.state, "e2": snapshot.e2.state,
                    "e3_buy_side": snapshot.e3_buy_side.state, "e3_sell_side": snapshot.e3_sell_side.state,
                })

        return {"configured_symbols": list(universe.configured_symbols), "new_alerts": alerts, "watching": watching}
