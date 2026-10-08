"""Windows-only read-only evaluator acceptance. Do not run against MT5 offline.

Uses the accepted candle adapter, all eight FX pairs, and the existing policy.
No production threshold is supplied by this script. Evidence excludes raw errors,
account identity, local paths and policy signatory/source information.
"""
from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from mt5.mt5_candles_readonly import ALLOWED_MT5_CALLS, SUPPORTED_SYMBOLS, default_symbol_map
from v1_tickets.daily_evaluator import FX_PAIRS, run_daily_evaluation
from v1_tickets.mt5_provider import MT5CandleProvider, MT5ReadOnlyCandleAdapter


class GuardedMT5:
    """Deny every broker surface except accepted candle/metadata reads."""
    def __init__(self, mt5):
        self._mt5 = mt5
        self.refused = []

    def __getattr__(self, name):
        if name not in ALLOWED_MT5_CALLS and name not in {"TIMEFRAME_M15", "TIMEFRAME_H1"}:
            self.refused.append(name)
            raise PermissionError("Read-only MT5 surface refused")
        return getattr(self._mt5, name)


def snapshot_provider(guard):
    """Capture quotes before fixing the evaluation clock; missing quotes stay missing."""
    reader = MT5ReadOnlyCandleAdapter(guard, default_symbol_map())
    quotes = {}
    for symbol in SUPPORTED_SYMBOLS:
        try:
            quotes[symbol] = reader.quote(symbol)
        except Exception:  # Each failed acquisition must still receive a terminal record.
            quotes[symbol] = None
    return MT5CandleProvider(reader, quote_snapshot=quotes)


def evaluate_report(provider, *, now, archive_root, policy_root=ROOT, policy=None,
                    ticket_source="REPLAY", cycles=None):
    results = run_daily_evaluation(
        now=now, day=now.date(), candle_provider=provider, include_crypto=False,
        archive_root=str(archive_root), policy_root=str(policy_root), policy=policy,
        ticket_source=ticket_source, cycles=cycles)
    actual = Counter((r.instrument, r.session) for r in results)
    expected_pairs = [pair for pair in FX_PAIRS if cycles is None or pair[1] in set(cycles)]
    expected = Counter(expected_pairs)
    rows = []
    for result in results:
        ticket = result.canonical
        action = ticket["actionability"]
        row = {
            "instrument": result.instrument, "session": result.session,
            "decision": result.decision, "reason": ticket["reason_code"],
            "ticket_id": result.ticket_id, "signal_valid": action["valid_at_trigger"],
            "logic_status": ticket["logic_status"], "economic_status": ticket["economic_status"],
            "actionability": action["actionability_at_send"], "policy_id": action["policy_id"],
            "policy_version": action["policy_version"], "policy_status": action["policy_status"],
            "data_source": result.venue, "evaluated_at_utc": ticket["created_at"],
        }
        if "data_error" in ticket:
            row["data_error"] = ticket["data_error"]
        for key in ("current_send_raw", "entry_reference_raw", "sl_raw", "tp1_raw", "tp2_raw"):
            value = ticket["prices"].get(key)
            if value is not None:
                row[key] = value
        for key in ("remaining_R_tp1", "remaining_R_tp2"):
            value = ticket["risk"].get(key)
            if value is not None:
                row[key] = value
        rows.append(row)
    return {
        "mission": "AG_OBJECTIVE_INTEGRATION_R1",
        "ticket_store_source": ticket_source,
        "host_acceptance_status": "NOT_EVALUATED",
        "evaluated_at_utc": now.isoformat(), "expected_evaluations": sum(expected.values()),
        "actual_evaluations": len(rows), "matrix_complete": actual == expected,
        "missing_evaluations": [list(pair) for pair in (expected - actual).elements()],
        "unexpected_evaluations": [list(pair) for pair in (actual - expected).elements()],
        "terminal_counts": dict(Counter(row["decision"] for row in rows)),
        "execution_authorization": False, "results": rows,
    }


def save_report(report, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / (report["evaluated_at_utc"][:10] + "_live_evaluator_report.json")
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "artifacts/validation/live_evaluator_r1")
    args = parser.parse_args(argv)
    # Import terminal lifecycle helpers only in the live entrypoint, never on import.
    sys.path.insert(0, str(ROOT / "scripts/host"))
    from _host_common import (AlreadyRunning, import_mt5, mt5_access_lock, mt5_initialize,
                              require_demo_account, single_instance, utcnow)

    mt5 = import_mt5()
    if mt5 is None:
        print("BLOCKER = MT5_PACKAGE_UNAVAILABLE")
        return 2
    try:
        with single_instance("ag_v1_fx"), mt5_access_lock():
            ok, _ = mt5_initialize(mt5)
            if not ok:
                print("BLOCKER = MT5_INITIALIZE_FAILED")
                return 2
            try:
                demo_ok, _ = require_demo_account(mt5)
                if not demo_ok:
                    print("BLOCKER = DEMO_ACCOUNT_REQUIRED")
                    return 2
                guard = GuardedMT5(mt5)
                provider = snapshot_provider(guard)
                report = evaluate_report(provider, now=utcnow(), archive_root=ROOT / "journal",
                                         ticket_source="LIVE")     # real MT5 snapshot provider only
                report["refused_mt5_calls"] = guard.refused
                report["broker_mutation_attempts"] = len(guard.refused)
            finally:
                mt5.shutdown()
    except AlreadyRunning:
        print("BLOCKER = FX_STORE_WRITER_ACTIVE")
        return 2
    save_report(report, args.out)
    for row in report["results"]:
        print(json.dumps(row, sort_keys=True))
    print(json.dumps({"terminal_counts": report["terminal_counts"],
                      "matrix_complete": report["matrix_complete"],
                      "broker_mutation_attempts": report["broker_mutation_attempts"]}, sort_keys=True))
    return 0 if report["matrix_complete"] and not guard.refused else 1


if __name__ == "__main__":
    raise SystemExit(main())
