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
- Runner config versions (config/v1_tickets/crypto_ticket_v<N>.yaml) choose the venue and
  the evaluation window; the engine is the same frozen 2.0.0 in every version. With no
  config, build_crypto_ticket behaves exactly as version 1 (public perp feed, frozen daily
  window). Version 2 (ACTIVE, owner decision 2026-09-30): VT Markets MT5 BTCUSD/ETHUSD
  via Mt5CryptoFeed, weekdays 09:00-12:00 America/New_York, no weekend runs.
"""
from __future__ import annotations

import datetime as dt
import os
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

import yaml

from btc_sweep_research import daily_report, pipeline
from btc_sweep_research.ledger import BTCResearchLedger
from execution_runtime import binance_usdtm_feed as BN
from execution_runtime import bybit_linear_perp_feed as BY
from execution_runtime.public_crypto_feed import (
    CandleBundle, FallbackPublicCryptoFeed, PrefetchedFeed, PublicCryptoFeedUnavailable,
)
from host_evidence.symbol_metadata import SWAP_FIELDS, load_record
from mt5.symbol_resolver import METADATA_SOURCE_SYNTHETIC_RESEARCH, SymbolMeta
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
CONFIG_DIR = os.path.join("config", "v1_tickets")
ACTIVE_CONFIG = os.path.join(CONFIG_DIR, "crypto_ticket_v2.yaml")
MT5_SOURCE = "MT5_VT_MARKETS_DEMO"


def load_ticket_config(path: str = ACTIVE_CONFIG, root: str = ".") -> Dict[str, Any]:
    with open(path if os.path.isabs(path) else os.path.join(root, path), encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if cfg.get("config_id") != "AG_V1_CRYPTO_TICKET" or not isinstance(cfg.get("version"), int):
        raise ValueError(f"{path}: not an AG_V1_CRYPTO_TICKET config")
    return cfg


def _hhmm(s: str) -> dt.time:
    return dt.time(*map(int, s.split(":")))


def window_status(config: Optional[Dict[str, Any]], observation_date: dt.date, now: dt.datetime) -> str:
    """IN_WINDOW / BEFORE_WINDOW / AFTER_WINDOW / OUTSIDE_WEEKDAYS. No config = version 1."""
    w = (config or {}).get("window") or {"kind": "FROZEN_DAILY_REPORT_UTC"}
    if w["kind"] == "FROZEN_DAILY_REPORT_UTC":
        return daily_report.report_window_status(observation_date, now)
    if w["kind"] != "LOCAL_WEEKDAY":
        raise ValueError(f"unknown window kind {w['kind']!r}")
    local = now.astimezone(ZoneInfo(w["timezone"]))
    if local.isoweekday() not in w["weekdays"]:
        return "OUTSIDE_WEEKDAYS"
    if local.time() < _hhmm(w["start"]):
        return "BEFORE_WINDOW"
    return "IN_WINDOW" if local.time() < _hhmm(w["end"]) else "AFTER_WINDOW"


class Mt5CryptoFeed:
    """fetch_bundle over VT Markets MT5 (read-only). `fetch(broker_symbol, tf, count)` is the
    host kit's rule-timestamped fetcher; every timeframe comes from this one source."""

    def __init__(self, fetch: Callable[[str, str, int], List[Any]], symbols: Dict[str, str], source: str = MT5_SOURCE):
        self._fetch, self.symbols, self.source = fetch, dict(symbols), source

    def fetch_bundle(self, symbol: str, requests_: Sequence[Tuple[str, int]]) -> CandleBundle:
        broker = self.symbols[symbol]
        return CandleBundle(symbol, self.source, {tf: list(self._fetch(broker, tf, n)) for tf, n in requests_}, None)


def _mt5_symbol_meta(symbol: str, broker_symbol: str) -> SymbolMeta:
    """SymbolMeta from the verified host capture of the broker symbol. Tagged
    SYNTHETIC_RESEARCH like every crypto research record (never broker-order eligible).
    Raises LookupError if swap/rollover fields are absent (required for CFD cost model)."""
    rec = load_record(broker_symbol)
    if rec is None or rec["broker_symbol"] != broker_symbol:
        raise LookupError(f"HOST_METADATA_MISSING {broker_symbol}")
    f = rec["fields"]
    missing_swap = [sf for sf in SWAP_FIELDS if f.get(sf) is None]
    if missing_swap:
        raise LookupError(f"HOST_SWAP_METADATA_MISSING {broker_symbol}: {missing_swap} "
                          f"-- re-run capture_symbol_metadata.py to update the record")
    return SymbolMeta(symbol=symbol, tick_size=float(f["trade_tick_size"]), tick_value=float(f["trade_tick_value"]),
                      contract_size=float(f["trade_contract_size"]), volume_min=float(f["volume_min"]),
                      volume_max=float(f["volume_max"]), volume_step=float(f["volume_step"]),
                      digits=int(f["digits"]), point=float(f["point"]),
                      trade_stops_level=int(f["trade_stops_level"]), trade_freeze_level=int(f["trade_freeze_level"]),
                      metadata_source=METADATA_SOURCE_SYNTHETIC_RESEARCH)


def _symbol_meta(symbol: str, source: str, feed=None):
    if isinstance(feed, Mt5CryptoFeed):
        return _mt5_symbol_meta(symbol, feed.symbols[symbol])
    if symbol == "BTCUSDT":
        if source == BY.EXCHANGE_ID:
            return BY.to_symbol_meta(BY.default_symbol_meta(symbol))
        return BN.to_symbol_meta(BN.default_symbol_meta(symbol))
    return crypto_symbol_meta(symbol)  # frozen crypto_symbols tick table, SYNTHETIC_RESEARCH-tagged


def build_crypto_ticket(
    symbol: str, observation_date: dt.date, now: dt.datetime, *, feed: FallbackPublicCryptoFeed, state_dir: str,
    config: Optional[Dict[str, Any]] = None,
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
    if config is not None:
        base["ticket_config"] = f"{config['config_id']}@v{config['version']}"
    window = window_status(config, observation_date, now)
    base["window_status"] = window
    if window != "IN_WINDOW":
        reason = "OUTSIDE_FROZEN_DAILY_WINDOW" if config is None or config["version"] == 1 else "OUTSIDE_CONFIG_WINDOW"
        return {**base, "decision": "BLOCKED", "reason_codes": [reason]}
    try:
        bundle = feed.fetch_bundle(symbol, [("H1", pipeline.H1_LOOKBACK_COUNT), ("M5", pipeline.M5_LOOKBACK_COUNT)])
        meta = _symbol_meta(symbol, bundle.source, feed)
    except PublicCryptoFeedUnavailable as exc:
        return {**base, "data_source": "NONE", "decision": "DATA_ERROR",
                "reason_codes": ["PUBLIC_FEEDS_UNAVAILABLE"], "primary_failure_reason": exc.primary_reason,
                "fallback_failure_reason": exc.fallback_reason}
    except Exception as exc:  # noqa: BLE001 -- MT5 venue data/metadata failure: DATA_ERROR, never a guess
        if not isinstance(feed, Mt5CryptoFeed):
            raise
        return {**base, "data_source": feed.source, "decision": "DATA_ERROR",
                "reason_codes": ["MT5_FEED_ERROR"], "detail": str(exc)[:300]}
    base.update(data_source=bundle.source, primary_failure_reason=bundle.primary_failure_reason)
    os.makedirs(state_dir, exist_ok=True)
    p = lambda name: os.path.join(state_dir, f"{symbol}_{name}.json")  # noqa: E731
    try:
        report = pipeline.run_research_cycle(
            PrefetchedFeed(bundle), runtime=SweepRetestRuntime(SweepRetestStateStore(p("setup_state"))),
            ledger=BTCResearchLedger(p("ledger")),
            daily_loss_guard=DailyLossGuard(JsonKeyValueStore(p("daily_loss")), daily_report.STRATEGY_ID),
            open_position_guard=OpenPositionGuard(JsonKeyValueStore(p("positions"))),
            now=now, exchange_id=bundle.source, symbol_meta=meta, symbol=symbol,
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
