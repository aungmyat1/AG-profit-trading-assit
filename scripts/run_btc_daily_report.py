"""Scheduled read-only BTC daily decision for Bybit BTCUSDT linear perpetual.

Default invocation evaluates the preceding UTC observation date and is accepted only
inside the frozen 00:05-00:15 UTC next-day report window. It archives one immutable
daily decision and prints either canonical JSON or a human-readable decision/proposal
ticket. It has no exchange execution path and uses no API credentials.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import io
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# A third-party analysis dependency prints an ANSI promotional banner at import time.
# Suppress import-time noise so --json remains valid machine-readable JSON for the
# scheduler and downstream consumers. Runtime errors/output are never suppressed.
with contextlib.redirect_stdout(io.StringIO()):
    from btc_sweep_research.daily_report import (  # noqa: E402
        archive_btc_daily_report,
        build_btc_daily_report,
        human_readable_btc_daily_report,
        report_window_status,
    )
    from execution_runtime.bybit_linear_perp_feed import (  # noqa: E402
        BybitLinearPerpFeed,
        CANONICAL_SYMBOL,
        EXCHANGE_ID,
        fetch_exchange_symbol_meta,
        to_symbol_meta,
    )
    from btc_sweep_research.ledger import BTCResearchLedger  # noqa: E402
    from execution.daily_loss_guard import DailyLossGuard  # noqa: E402
    from execution.position_guard import OpenPositionGuard  # noqa: E402
    from runtime_state.store import JsonKeyValueStore  # noqa: E402
    from strategy_engine.sweep_retest.engine import SweepRetestRuntime  # noqa: E402
    from strategy_engine.sweep_retest.state_store import SweepRetestStateStore  # noqa: E402

APPLICATION_RELEASE = "AG_TRADE_ASSISTANT_V1_0_3"
PROVIDER = "BYBIT"
MARKET_TYPE = "LINEAR_USDT_PERPETUAL"


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Read-only scheduled BTC daily decision (Bybit production market data; execution disabled)"
    )
    parser.add_argument(
        "--date", help="Observation date YYYY-MM-DD (default: previous UTC date)",
    )
    parser.add_argument("--json", action="store_true", help="Print canonical JSON")
    parser.add_argument(
        "--allow-outside-window", action="store_true",
        help="Diagnostic smoke run only; requires --no-archive and never counts as qualification evidence",
    )
    parser.add_argument("--no-archive", action="store_true", help="Do not write the immutable daily archive")
    return parser.parse_args(argv)


def main(argv=None, *, clock=None) -> int:
    args = _parse_args(argv)
    now = (clock or (lambda: dt.datetime.now(dt.timezone.utc)))()
    if now.tzinfo is None:
        raise ValueError("clock must return a timezone-aware datetime")
    now = now.astimezone(dt.timezone.utc)
    observation_date = (
        dt.date.fromisoformat(args.date) if args.date else now.date() - dt.timedelta(days=1)
    )
    window_status = report_window_status(observation_date, now)
    if window_status != "IN_WINDOW" and not args.allow_outside_window:
        print(
            f"BTC_DAILY_REPORT_WINDOW_{window_status}: observation_date={observation_date} now={now.isoformat()}",
            file=sys.stderr,
        )
        return 2
    if args.allow_outside_window and not args.no_archive:
        print("--allow-outside-window requires --no-archive", file=sys.stderr)
        return 2

    live_meta = fetch_exchange_symbol_meta(CANONICAL_SYMBOL)
    feed = BybitLinearPerpFeed()
    runtime_kwargs = {}
    temporary_state = None
    if args.allow_outside_window:
        # A diagnostic must not create campaign/runtime evidence. Use disposable state
        # while still exercising the real production feed and deterministic engine.
        temporary_state = tempfile.TemporaryDirectory(prefix="ag-btc-diagnostic-")
        root = Path(temporary_state.name)
        runtime_kwargs = {
            "runtime": SweepRetestRuntime(SweepRetestStateStore(str(root / "setup.json"))),
            "ledger": BTCResearchLedger(str(root / "occurrences.json")),
            "daily_loss_guard": DailyLossGuard(
                JsonKeyValueStore(str(root / "daily-loss.json")), "ST_LIQUIDITY_SWEEP_RETEST_V1",
            ),
            "open_position_guard": OpenPositionGuard(JsonKeyValueStore(str(root / "positions.json"))),
        }
    try:
        report = build_btc_daily_report(
            feed,
            observation_date,
            application_release=APPLICATION_RELEASE,
            provider=PROVIDER,
            provider_symbol=CANONICAL_SYMBOL,
            market_type=MARKET_TYPE,
            exchange_id=EXCHANGE_ID,
            symbol_meta=to_symbol_meta(live_meta),
            now=now,
            generated_at=now,
            validate_observation_data=True,
            **runtime_kwargs,
        )
    finally:
        if temporary_state is not None:
            temporary_state.cleanup()
    report["report_window_status"] = window_status
    report["qualification_evidence_eligible"] = window_status == "IN_WINDOW"

    archived_path = None
    if not args.no_archive:
        archived_path = archive_btc_daily_report(observation_date, report)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    else:
        print(human_readable_btc_daily_report(report))
    if archived_path:
        print(f"\n(archived: {archived_path})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
