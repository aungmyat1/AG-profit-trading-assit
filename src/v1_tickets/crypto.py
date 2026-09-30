"""AG V1 crypto informational tickets: ST_LIQUIDITY_SWEEP_RETEST_V1@2.0.0 CRYPTO_PERP.

- BTCUSDT and ETHUSDT run the unchanged frozen engine through
  btc_sweep_research.pipeline.run_research_cycle (the `symbol` parameter is additive).
  ETHUSDT's status is SHADOW (registry).
- Tickets are only evaluated in the frozen daily report window
  (btc_sweep_research.daily_report.report_window_status). Outside it the ticket is BLOCKED,
  with no evaluation and no data fetch.
- Data: FallbackPublicCryptoFeed.fetch_bundle(), one venue per ticket, Bybit primary and
  Binance fallback. `data_source` and `primary_failure_reason` are printed on every ticket,
  including DATA_ERROR tickets.
- The decision uses daily_report._decision_from_cycle_report (read-only mapping of the
  engine report).
"""
from __future__ import annotations

import datetime as dt
import os
from typing import Any, Dict, Optional

from btc_sweep_research import daily_report, pipeline
from btc_sweep_research.ledger import BTCResearchLedger
from execution_runtime import binance_usdtm_feed as BN
from execution_runtime import bybit_linear_perp_feed as BY
from execution_runtime.public_crypto_feed import FallbackPublicCryptoFeed, PrefetchedFeed, PublicCryptoFeedUnavailable
from sizing_math.daily_loss_guard import DailyLossGuard
from sizing_math.position_guard import OpenPositionGuard
from runtime_state.store import JsonKeyValueStore
from strategy_engine.sweep_retest.crypto_symbols import crypto_symbol_meta
from strategy_engine.sweep_retest.engine import SweepRetestRuntime
from strategy_engine.sweep_retest.state_store import SweepRetestStateStore
from ticket_delivery.archive import (
    CYCLE_STATE_BLOCKED, CYCLE_STATE_DATA_ERROR, CYCLE_STATE_NO_TRADE, CYCLE_STATE_READY, CYCLE_STATE_WATCH,
    CycleDecisionRecord, archive_cycle_decision,
)

V1_CRYPTO_SYMBOLS = ("BTCUSDT", "ETHUSDT")
SYMBOL_STATUS = {"BTCUSDT": "ACTIVE_INCUBATION", "ETHUSDT": "SHADOW"}
CYCLE = "DAILY_WINDOW"
APPLICATION_RELEASE = "AG_V1_CLOUD"


def _symbol_meta(symbol: str, source: str):
    if symbol == "BTCUSDT":
        if source == BY.EXCHANGE_ID:
            return BY.to_symbol_meta(BY.default_symbol_meta(symbol))
        return BN.to_symbol_meta(BN.default_symbol_meta(symbol))
    return crypto_symbol_meta(symbol)  # frozen crypto_symbols tick table, SYNTHETIC_RESEARCH-tagged


def build_crypto_ticket(
    symbol: str, observation_date: dt.date, now: dt.datetime, *, feed: FallbackPublicCryptoFeed, state_dir: str,
) -> Dict[str, Any]:
    if symbol not in V1_CRYPTO_SYMBOLS:
        raise ValueError(f"{symbol!r} is not a V1 crypto ticket symbol")
    base: Dict[str, Any] = {
        "label": "INFORMATIONAL TICKET -- NOT A BROKER ORDER", "strategy_id": daily_report.STRATEGY_ID,
        "strategy_version": daily_report.STRATEGY_VERSION, "profile": "CRYPTO_PERP", "symbol": symbol,
        "symbol_status": SYMBOL_STATUS[symbol], "cycle": CYCLE, "observation_date": observation_date.isoformat(),
        "evaluated_at": now.astimezone(dt.timezone.utc).isoformat(), "delivery_mode": "ARCHIVE_ONLY",
        "data_source": None, "primary_failure_reason": None,
    }
    window = daily_report.report_window_status(observation_date, now)
    base["window_status"] = window
    if window != "IN_WINDOW":
        return {**base, "decision": "BLOCKED", "reason_codes": ["OUTSIDE_FROZEN_DAILY_WINDOW"]}
    try:
        bundle = feed.fetch_bundle(symbol, [("H1", pipeline.H1_LOOKBACK_COUNT), ("M5", pipeline.M5_LOOKBACK_COUNT)])
    except PublicCryptoFeedUnavailable as exc:
        return {**base, "data_source": "NONE", "decision": "DATA_ERROR",
                "reason_codes": ["PUBLIC_FEEDS_UNAVAILABLE"], "primary_failure_reason": exc.primary_reason,
                "fallback_failure_reason": exc.fallback_reason}
    base.update(data_source=bundle.source, primary_failure_reason=bundle.primary_failure_reason)
    os.makedirs(state_dir, exist_ok=True)
    p = lambda name: os.path.join(state_dir, f"{symbol}_{name}.json")  # noqa: E731
    try:
        report = pipeline.run_research_cycle(
            PrefetchedFeed(bundle), runtime=SweepRetestRuntime(SweepRetestStateStore(p("setup_state"))),
            ledger=BTCResearchLedger(p("ledger")),
            daily_loss_guard=DailyLossGuard(JsonKeyValueStore(p("daily_loss")), daily_report.STRATEGY_ID),
            open_position_guard=OpenPositionGuard(JsonKeyValueStore(p("positions"))),
            now=now, exchange_id=bundle.source, symbol_meta=_symbol_meta(symbol, bundle.source), symbol=symbol,
        )
    except Exception as exc:  # noqa: BLE001 -- any engine/data-quality failure is DATA_ERROR, never a guess
        return {**base, "decision": "DATA_ERROR", "reason_codes": [type(exc).__name__], "detail": str(exc)[:300]}
    decision = daily_report._decision_from_cycle_report(report)
    ticket = {**base, **decision, "trading_day": report.trading_day.isoformat()}
    if decision["decision"] == "READY":
        o = report.qualified_occurrences[0].setup_state
        ticket.update(direction=o.direction, entry=o.entry, stop_loss=o.stop_loss, tp1=o.tp1, tp2=o.tp2,
                      position_size="RESEARCH_ONLY_NOT_AN_ORDER")
    return ticket


_STATE = {"READY": CYCLE_STATE_READY, "WATCH": CYCLE_STATE_WATCH, "NO_TRADE": CYCLE_STATE_NO_TRADE,
          "DATA_ERROR": CYCLE_STATE_DATA_ERROR, "BLOCKED": CYCLE_STATE_BLOCKED}


def archive_crypto_ticket(ticket: Dict[str, Any], root: str) -> str:
    record = CycleDecisionRecord(
        strategy_id=ticket["strategy_id"], strategy_version=ticket["strategy_version"],
        application_release=APPLICATION_RELEASE, symbol=ticket["symbol"], cycle=CYCLE,
        trading_date=dt.date.fromisoformat(ticket["observation_date"]), cycle_state=_STATE[ticket["decision"]],
        evaluation_time_utc=ticket["evaluated_at"], payload=ticket, reason_codes=tuple(ticket["reason_codes"]),
    )
    return archive_cycle_decision(record, root=root)
