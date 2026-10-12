"""S1 live-data preview in a separate checkout; no sender or order-capable adapter."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from demo_execution.admission import (
    MarketEvidence,
    check_cost_gate,
    check_freshness,
    evaluate_pre_send_gates,
)
from demo_execution.notification import notification_gate
from demo_execution.risk import evaluate_risk_caps
from demo_execution.scope import load_scope_policy
from mt5.mt5_candles_readonly import default_symbol_map
from v1_tickets.canonical_ticket import build_canonical_ticket, render_canonical
from v1_tickets.fx import build_fx_ticket
from v1_tickets.mt5_provider import MT5CandleProvider, MT5ReadOnlyCandleAdapter
from v1_tickets.ready_authority import logic_scope_verified, ready_authority

RAW_HASH = "4f936bbe17f4aa4fd3cd9fc85640bed57b6786f43c52e8e2d69aabb7234b14cf"


def evaluate_preview(bundle, *, now, market, policy=None, data_source="MT5_VT_MARKETS_DEMO"):
    """Use existing frozen strategy, ticket and gates; missing risk facts stay blocked."""
    scope = load_scope_policy(repo_root=ROOT)
    if scope.enabled or not scope.per_order_confirm_required:
        raise ValueError("ACCEPTANCE_REQUIRES_DISABLED_EXECUTION")
    if hashlib.sha256(scope.contract_path.read_bytes()).hexdigest() != RAW_HASH:
        raise ValueError("FROZEN_CONTRACT_MISMATCH")
    if not logic_scope_verified(scope.strategy_id, scope.strategy_version, scope.symbol,
                                 cycle=scope.session, setup="SWEEP", branch="RANGE_SWEEP",
                                 contract_path=str(scope.contract_path)):
        raise ValueError("S1_LOGIC_SCOPE_NOT_VERIFIED")
    bars = [*bundle.session_candles, *bundle.post_session_candles]
    if any(bar.time + dt.timedelta(minutes=15) > now for bar in bars):
        raise ValueError("UNCLOSED_M15_BAR")
    ticket = build_fx_ticket("GBPUSD", "ASIAN_LONDON", now.date(), bundle.session_candles,
                             bundle.expected_bar_count, bundle.post_session_candles,
                             data_source=data_source, evaluated_at=now, data_close=bundle.data_close,
                             spread=bundle.spread, runtime_scope=True)
    canonical = build_canonical_ticket(ticket, now=now, current_price=bundle.current_price,
                                        policy=policy, policy_root=str(ROOT))
    decision = evaluate_pre_send_gates(ticket, market, None, now_utc=now, scope=scope)
    cost, cost_details = check_cost_gate(ticket, market, scope)
    freshness, freshness_details = check_freshness(ticket, market, scope, now_utc=now)
    risk = evaluate_risk_caps(ticket, scope, None, now_utc=now)
    ready, ready_reason = ready_authority(scope.strategy_id, strategy_version=scope.strategy_version,
                                         contract_sha256=RAW_HASH, symbol=scope.symbol, session=scope.session)
    signal_present = ticket.get("entry") is not None and ticket.get("stop_loss") is not None
    no_setup = ticket.get("decision") == "NO_TRADE" or (ticket.get("decision") == "BLOCKED"
                                                         and ticket.get("reason_code") == "LOGIC_SCOPE_NOT_VERIFIED")
    outcome = "SIGNAL" if signal_present else ("NO_OPPORTUNITY" if no_setup
                                                else ticket.get("decision"))
    return {
        "strategy_version": scope.strategy_version, "raw_contract_sha256": RAW_HASH,
        "symbol": scope.symbol, "session": scope.session, "evaluated_at_utc": now.isoformat(),
        "candle_timestamps_utc": [bar.time.isoformat() for bar in bars], "closed_bar_causality": "PASS",
        "outcome": outcome, "ticket": ticket, "canonical_ticket": canonical,
        "gates": {"ready": {"allowed": ready, "reason": ready_reason},
                  "actionability": canonical["actionability"],
                  "cost": {"reason": cost, "details": cost_details},
                  "freshness": {"reason": freshness, "details": freshness_details},
                  "risk": {"allowed": risk.allowed, "reason": risk.reason_code},
                  "notification": notification_gate(scope.notification_failure_policy, None, ticket, now),
                  "standing_demo_authorization": "NOT_EVALUATED_EXECUTION_DISABLED"},
        "telegram_ascii_preview": render_canonical(canonical).encode("ascii", "backslashreplace").decode(),
        "execution_route": "NO_ORDER_SUBMISSION", "execution_reason": decision.reason_code,
        "broker_mutations": 0, "order_api_calls": 0, "telegram_sends": 0,
    }


def main(argv=None):
    from _host_common import (
        import_mt5,
        mt5_access_lock,
        mt5_initialize,
        require_pinned_demo_account,
        single_instance,
    )
    from live_eval_smoke import GuardedMT5

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--terminal-path", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    mt5 = import_mt5()
    if mt5 is None:
        raise RuntimeError("REAL_MT5_PACKAGE_REQUIRED")
    with single_instance("s1_readonly_acceptance"), mt5_access_lock():
        initialized, _ = mt5_initialize(mt5, args.terminal_path)
        if not initialized:
            raise RuntimeError("MT5_INITIALIZE_FAILED")
        try:
            pinned, _ = require_pinned_demo_account(mt5, root=str(ROOT), terminal_path=args.terminal_path)
            if not pinned:
                raise RuntimeError("ACCOUNT_PIN_MISMATCH")
            account, terminal = mt5.account_info(), mt5.terminal_info()
            if account is None or terminal is None or not terminal.connected:
                raise RuntimeError("BROKER_UNAVAILABLE")
            if str(account.login)[-3:] != "999" or account.server != "VTMarkets-Demo" or account.trade_mode != 0:
                raise RuntimeError("S1_ACCOUNT_MISMATCH")
            guard = GuardedMT5(mt5)
            reader = MT5ReadOnlyCandleAdapter(guard, default_symbol_map())
            bid, ask, observed = reader.quote("GBPUSD")
            now = dt.datetime.now(dt.timezone.utc)
            provider = MT5CandleProvider(reader, quote_snapshot={"GBPUSD": (bid, ask, observed)})
            bundle = provider("GBPUSD", "ASIAN_LONDON", now.date(), now)
            market = MarketEvidence("GBPUSD", bid, ask, observed, bundle.data_close)
            report = evaluate_preview(bundle, now=now, market=market)
            report["host_sha"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
            report["account"] = {"server": account.server, "login_suffix": "999", "mode": "DEMO"}
            report["terminal"] = {"path": "<HOST_TERMINAL>", "path_pin_matches": True,
                                  "name": terminal.name, "connected": bool(terminal.connected)}
            report["refused_read_surface_attempts"] = list(guard.refused)
            if guard.refused:
                raise RuntimeError("READ_ONLY_SURFACE_REFUSED")
        finally:
            mt5.shutdown()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(json.dumps({"outcome": report["outcome"], "route": report["execution_route"],
                      "reason": report["execution_reason"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
