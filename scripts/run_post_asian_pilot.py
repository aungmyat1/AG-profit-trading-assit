"""AG_TRADE_ASSISTANT_V1_0_3 CLI entrypoint.

Read-only, PROPOSAL_ONLY: never calls execution.executor / execution.mt5_gateway /
order_check / order_send. See src/post_asian_pilot/pipeline.py for the actual cycle
logic -- this script only wires MT5 connect/shutdown and report output around it.

Three distinct commands (spec section 30 -- do not overload one flag with three
meanings):
  --preflight  operational readiness ONLY. Never runs a strategy cycle, never claims a
               slot, never mutates a snapshot, never sends an order.
  --status     one operational cycle (existing contract, preserved).
  --watch      continuous observation. Internal polling continues every --interval
               seconds regardless, but operator-facing OUTPUT is event-driven: only
               printed on a new closed M15 processed, a state change, an operational
               error, a READY, or the execution window closing (which also renders the
               end-of-window report) -- never on an unchanged poll.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import mt5.connection as mt5_connection  # noqa: E402
from post_asian_pilot.pilot_config import DEFAULT_RELEASE_CONFIG_PATH, load_pilot_config, load_raw_yaml  # noqa: E402
from post_asian_pilot.pipeline import run_pilot_cycle  # noqa: E402
from post_asian_pilot.preflight import run_preflight  # noqa: E402
from post_asian_pilot.report import (  # noqa: E402
    cycle_to_dict, human_readable_report, release_fingerprints, render_pilot_end_report,
)
from post_asian_pilot.store import DEFAULT_STATE_DIR, PilotStores  # noqa: E402
from strategy_engine.loader import load_strategy  # noqa: E402


def _run_preflight(as_json: bool, pilot_path: str = None) -> None:
    result = run_preflight(pilot_path=pilot_path)
    payload = {
        "release_id": result.release_id, "release_fingerprint": result.release_fingerprint,
        "strategy_id": result.strategy_id, "strategy_version": result.strategy_version,
        "account_mode": result.account_mode, "trading_date": result.trading_date.isoformat()
        if result.trading_date else None,
        "daily_slot_state": result.daily_slot_state, "open_positions": result.open_positions,
        "checks": [{"name": n, "result": r} for n, r in result.checks],
        "pilot_status": result.pilot_status, "first_block_reason": result.first_block_reason,
    }
    if as_json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print("AG_TRADE_ASSISTANT_V1_0_3_PREFLIGHT")
        for name, value in payload.items():
            if name == "checks":
                continue
            print(f"{name} = {value}")
        for name, r in result.checks:
            print(f"  check[{name}] = {r}")
    if result.pilot_status == "PILOT_STARTUP_BLOCKED":
        sys.exit(1)


def _execute_cycle(pilot_path: str = None):
    mt5_connection.connect()
    try:
        return run_pilot_cycle(pilot_path)
    finally:
        mt5_connection.shutdown()


def _entry_ticket_context(pilot_path: str, result):
    """Reporting-only, read-only reconstruction of the context render_entry_ticket()
    needs (ledger + fingerprints) -- reuses the same PilotStores.default(...) /
    release_fingerprints(...) pattern render_pilot_end_report's own caller already uses
    below, never a new persistence mechanism. Any failure here degrades to no Entry
    Ticket enrichment (cycle_to_dict/human_readable_report already treat a None ledger
    as "omit entry_ticket*") -- it never affects the decision/proposal already
    established by run_pilot_cycle()."""
    try:
        pilot = load_pilot_config(pilot_path) if pilot_path else load_pilot_config()
        stores = PilotStores.default(result.strategy.strategy_id, pilot.state_dir or DEFAULT_STATE_DIR)
        fps = release_fingerprints(DEFAULT_RELEASE_CONFIG_PATH, pilot.strategy_source_path,
                                   "config/canonical_sessions.yaml", pilot.raw["risk"])
        return stores.ledger, fps["release_fingerprint"], fps["strategy_fingerprint"]
    except Exception:  # noqa: BLE001 -- presentation-only context; never block the cycle report
        return None, None, None


def _process_ticket_delivery(result, pilot_path: str, ledger, release_fp, strategy_fp, as_json: bool) -> bool:
    """Additive, best-effort: NEVER alters the strategy/report output already printed
    by the caller (AG_FX_DAILY_REPORT_V1's cycle_to_dict()/human_readable_report()
    schemas stay frozen, untouched by this function). Ships DISABLED by default
    (config/ticket_delivery.yaml) -- a no-op until an operator explicitly opts in.
    Returns True if an archive failure occurred for any pair (the one condition this
    function treats as worth a nonzero scheduler exit code; render-blocked/
    transport-not-configured are expected, non-critical outcomes in ARCHIVE_ONLY mode).
    """
    try:
        from ticket_delivery.scheduler_integration import load_integration_config, process_cycle_result

        config = load_integration_config()
        if config.mode == "DISABLED":
            return False
        outcomes = process_cycle_result(
            result, pilot_path=pilot_path, config=config, ledger=ledger,
            release_fingerprint=release_fp, strategy_fingerprint=strategy_fp,
        )
    except Exception as exc:  # noqa: BLE001 -- ticket-delivery is additive; never fail the scheduled cycle for an unexpected error here
        print(f"TICKET_DELIVERY_OPERATIONAL_ERROR: {exc}", file=sys.stderr)
        return False

    if as_json:
        print(json.dumps({"ticket_delivery": {"mode": config.mode, "outcomes": outcomes}}, default=str))
    else:
        print(f"TICKET_DELIVERY ({config.mode}):")
        for o in outcomes:
            print(f"  {o['symbol']}: cycle_state={o['cycle_state']} delivery_state={o['delivery_state']}"
                 + (f" reason={o['reason_code']}" if o['reason_code'] else ""))

    return any(o["delivery_state"] == "ARCHIVE_FAILED" for o in outcomes)


def _run_once(as_json: bool, pilot_path: str = None):
    result = _execute_cycle(pilot_path)
    ledger, release_fp, strategy_fp = _entry_ticket_context(pilot_path, result)
    if as_json:
        print(json.dumps(cycle_to_dict(result, ledger, release_fp, strategy_fp), indent=2, default=str))
    else:
        print(human_readable_report(result, ledger, release_fp, strategy_fp))
    archive_failed = _process_ticket_delivery(result, pilot_path, ledger, release_fp, strategy_fp, as_json)
    if archive_failed:
        sys.exit(1)
    return result


def _watch_signature(result) -> tuple:
    """What operator-facing output should be sensitive to: per-symbol strategy/portfolio
    state -- deliberately NOT evaluation_time (that changes every poll and would defeat
    the whole point of event-driven output)."""
    return tuple((pr.symbol, pr.decision.status, pr.portfolio_state, pr.portfolio_reason_code)
                for pr in result.pairs)


def _run_watch(as_json: bool, interval: int, pilot_path: str = None) -> None:
    pilot = load_pilot_config(pilot_path) if pilot_path else load_pilot_config()
    strategy = load_strategy(pilot.strategy_source_path)
    release_id = load_raw_yaml(DEFAULT_RELEASE_CONFIG_PATH).get("release_id")
    window_end_seen = False
    last_signature = None

    while True:
        try:
            result = _execute_cycle(pilot_path)
        except Exception as exc:  # noqa: BLE001 -- an operational error is itself an event to report
            print(f"[{datetime.now(timezone.utc).isoformat()}] ERROR: {exc}")
            time.sleep(interval)
            continue

        signature = _watch_signature(result)
        window_end = datetime.combine(result.trading_date,
                                      datetime.strptime(pilot.execution_window_end_utc, "%H:%M").time(),
                                      tzinfo=timezone.utc)
        is_ready = any(pr.decision.status == "READY" for pr in result.pairs)

        if signature != last_signature or is_ready:
            ledger, release_fp, strategy_fp = _entry_ticket_context(pilot_path, result)
            if as_json:
                print(json.dumps(cycle_to_dict(result, ledger, release_fp, strategy_fp), indent=2, default=str))
            else:
                print(human_readable_report(result, ledger, release_fp, strategy_fp))
            last_signature = signature

        if result.evaluation_time >= window_end and not window_end_seen:
            window_end_seen = True
            stores = PilotStores.default(strategy.strategy_id, pilot.state_dir or DEFAULT_STATE_DIR)
            end_report = render_pilot_end_report(pilot, strategy, release_id, result.trading_date, stores)
            print(json.dumps(end_report, indent=2, default=str) if as_json
                 else f"AG_TRADE_ASSISTANT_V1_0_3_PILOT_END: {end_report['result']}")

        time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="AG_TRADE_ASSISTANT_V1_0_3 (read-only, PROPOSAL_ONLY)")
    parser.add_argument("--preflight", action="store_true", help="operational readiness only, no strategy cycle")
    parser.add_argument("--once", action="store_true", help="run a single evaluation cycle")
    parser.add_argument("--watch", action="store_true", help="continuous, event-driven observation")
    parser.add_argument("--status", action="store_true", help="one operational cycle, JSON report")
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--json", action="store_true", help="emit JSON instead of the human-readable report")
    parser.add_argument("--pilot-config", default=None,
                        help="path to a pilot config yaml (default: AG_POST_ASIAN_LONDON_PILOT_V1_0_1.yaml); "
                             "use to run a different session_pairs cycle, e.g. LONDON_NEWYORK")
    args = parser.parse_args()

    as_json = args.json or args.status

    if args.preflight:
        _run_preflight(as_json, args.pilot_config)
    elif args.watch:
        _run_watch(as_json, args.interval, args.pilot_config)
    else:
        _run_once(as_json, args.pilot_config)


if __name__ == "__main__":
    main()
