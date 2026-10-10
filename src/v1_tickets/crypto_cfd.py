"""Read-only VT Markets BTCUSD/ETHUSD CFD proposal cycle.

The v2 config supplies the exact broker symbols and weekday acquisition window; the
v3 config adds the weekend window. Neither the v2/v3 perpetual engine nor public feeds
are imported. Callers inject closed UTC candles and a fresh broker quote; no order API.
Every invocation archives one typed terminal row before any rendering.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Protocol
from zoneinfo import ZoneInfo

import yaml

from crypto_cfd_contract.contract import CONTRACT_ID, CONTRACT_VERSION, INSTRUMENTS
from crypto_cfd_contract.rules import evaluate
from mt5 import canonical_broker_map
from strategy_engine.session import Candle
from ticket_delivery.archive import CycleDecisionRecord, archive_cycle_decision
from ticket_delivery.renderer import render_informational_ticket
from v1_tickets import manual_ticket
from v1_tickets.authority import REPO_ROOT
from v1_tickets.crypto_cfd_policy import POLICY_PATH, load_ticket_policy

UTC = dt.timezone.utc
M5 = dt.timedelta(minutes=5)
M15 = dt.timedelta(minutes=15)
CONFIG_V2 = "config/v1_tickets/crypto_ticket_v2.yaml"
CONFIG_V3 = "config/v1_tickets/crypto_ticket_v3.yaml"


class ReadOnlyCryptoFeed(Protocol):
    def fetch(self, broker_symbol: str, timeframe: str, count: int) -> list[Candle]: ...
    def quote(self, broker_symbol: str) -> tuple[float, float, dt.datetime]: ...


def _config(root: Path = REPO_ROOT) -> tuple[dict, list[dict]]:
    v2 = yaml.safe_load((root / CONFIG_V2).read_text(encoding="utf-8"))
    v3 = yaml.safe_load((root / CONFIG_V3).read_text(encoding="utf-8"))
    if (v2.get("config_id") != "AG_V1_CRYPTO_TICKET" or v2.get("version") != 2
            or v2["venue"]["kind"] != "MT5" or v3.get("version") != 3
            or set(v2["venue"]["symbols"].values()) != set(INSTRUMENTS)):
        raise ValueError("VT crypto data-path config mismatch")
    weekday = {**v2["window"], "name": "WEEKDAY"}
    weekend = next(w for w in v3["window"]["windows"] if w["name"] == "WEEKEND")
    if weekend["weekdays"] != [6, 7]:
        raise ValueError("weekend window config mismatch")
    return v2["venue"], [weekday, weekend]


def _window(now: dt.datetime, windows: list[dict]) -> str | None:
    for window in windows:
        local = now.astimezone(ZoneInfo(window["timezone"]))
        start = dt.time.fromisoformat(window["start"])
        end = dt.time.fromisoformat(window["end"])
        if local.isoweekday() in window["weekdays"] and start <= local.time() < end:
            return window["name"]
    return None


def _closed(rows: list[Candle], now: dt.datetime, step: dt.timedelta) -> list[Candle]:
    if any(c.time.tzinfo is None for c in rows):
        raise ValueError("NAIVE_CANDLE_TIME")
    closed = [c for c in rows if c.time + step <= now]
    if any(c.time.utcoffset() != dt.timedelta(0) for c in closed):
        raise ValueError("NON_UTC_CANDLE")
    if any(a.time >= b.time for a, b in zip(closed, closed[1:])):
        raise ValueError("DUPLICATE_OR_UNSORTED_CANDLES")
    return closed


def build_crypto_cfd_cycle(symbol: str, now: dt.datetime, *, feed: ReadOnlyCryptoFeed | None,
                           balance: float | None = None, root: Path = REPO_ROOT) -> dict:
    """One typed decision per symbol/window, even for missing data or closed windows."""
    if symbol not in INSTRUMENTS or now.tzinfo is None:
        raise ValueError("BTCUSD/ETHUSD and aware evaluation time required")
    now = now.astimezone(UTC)
    base: dict[str, Any] = {
        "label": "INFORMATIONAL PROPOSAL -- NOT A BROKER ORDER",
        "strategy_id": CONTRACT_ID, "strategy_version": CONTRACT_VERSION, "symbol": symbol,
        "evaluated_at": now.isoformat(), "data_source": "MT5_VT_MARKETS_DEMO",
        "execution_authorized": False, "edge_verified": False, "owner_accept_allowed": False,
    }
    try:
        venue, windows = _config()
        name = _window(now, windows)
        base["cycle"] = name or "OUTSIDE_WINDOW"
        commission = manual_ticket.crypto_cfd_commission(symbol, root)
        base["warnings"] = ["COMMISSION_UNKNOWN"] if commission is None else []
        policy = load_ticket_policy(root / POLICY_PATH)
        missing = [r for r in ("SPREAD_POLICY_UNDEFINED", "RISK_POLICY_AMBIGUOUS")
                   if r in policy["open_authorities"]]
        if missing:
            return {**base, "decision": "BLOCKED", "reason_codes": missing}
        if name is None:
            return {**base, "decision": "BLOCKED", "reason_codes": ["OUTSIDE_CONFIG_WINDOW"]}
        try:  # the versioned CANONICAL_TO_BROKER_MAP is the resolution authority
            broker = canonical_broker_map.resolve(symbol)
        except (canonical_broker_map.SymbolUnmapped, canonical_broker_map.SymbolMapError):
            broker = None
        if broker is None or broker not in venue["symbols"].values():
            raise ValueError("SYMBOL_MAPPING_MISSING")
        if feed is None:
            raise ValueError("FEED_UNAVAILABLE")
        d1 = _closed(list(feed.fetch(broker, "D1", 50)), now, dt.timedelta(days=1))
        h1 = _closed(list(feed.fetch(broker, "H1", 100)), now, dt.timedelta(hours=1))
        m15 = _closed(list(feed.fetch(broker, "M15", 96)), now, M15)
        m5 = _closed(list(feed.fetch(broker, "M5", 576)), now, M5)
        if not m15 or not h1 or not d1 or not m5:
            raise ValueError("TIMEFRAME_MISSING")
        # The previous UTC-day reference requires every M5 bar, not merely 288 arbitrary
        # bars. Never forward-fill a missing broker candle.
        day = now.replace(hour=0, minute=0, second=0, microsecond=0) - dt.timedelta(days=1)
        previous = [c.time for c in m5 if day <= c.time < day + dt.timedelta(days=1)]
        if previous != [day + i * M5 for i in range(288)]:
            raise ValueError("REFERENCE_INCOMPLETE")
        result = evaluate(symbol, now, d1, h1, m5, m15)
        bid, ask, observed = feed.quote(broker)
        if not (0 < bid <= ask):
            raise ValueError("QUOTE_INVALID")
        spread = ask - bid
        ticket = manual_ticket.build_crypto_cfd_manual_ticket(
            result, now=now, window=name, spread=spread, quote_time=observed,
            balance=balance, meta=manual_ticket.symbol_meta_from_host(symbol),
            commission_r=commission, policy=policy,
        )
        return {**ticket, "data_source": venue["source_id"], "broker_symbol": broker}
    except Exception as exc:  # noqa: BLE001 -- acquisition failure must still emit an explicit row
        return {**base, "cycle": base.get("cycle", "UNAVAILABLE"), "decision": "DATA_ERROR",
                "reason_codes": [str(exc)[:100] or type(exc).__name__],
                "warnings": base.get("warnings", [])}


def run_crypto_cfd_cycle(symbol: str, now: dt.datetime, *, feed: ReadOnlyCryptoFeed | None,
                         archive_root: str, balance: float | None = None,
                         root: Path = REPO_ROOT) -> tuple[dict, str]:
    """Persist decision before rendering. No delivery and no broker mutation."""
    ticket = build_crypto_cfd_cycle(symbol, now, feed=feed, balance=balance, root=root)
    record = CycleDecisionRecord(
        strategy_id=CONTRACT_ID, strategy_version=CONTRACT_VERSION,
        application_release="AG_CRYPTO_CFD_PROPOSAL", symbol=symbol, cycle=ticket["cycle"],
        trading_date=now.astimezone(UTC).date(), cycle_state=ticket["decision"],
        evaluation_time_utc=ticket["evaluated_at"], payload=ticket,
        reason_codes=tuple(ticket["reason_codes"]),
    )
    archive_path = archive_cycle_decision(record, root=archive_root)
    ticket["manual_text"] = manual_ticket.render_text(ticket)
    if ticket["decision"] == "READY":
        plan = ticket["engine_result"]["evidence"]["target_plan"]
        proposal = {
            "identity": {"setup_id": record.logical_ticket_id()},
            "strategy": {"strategy_id": CONTRACT_ID, "strategy_version": CONTRACT_VERSION},
            "application": {"release_id": "AG_CRYPTO_CFD_PROPOSAL"},
            "market": {"symbol": symbol, "direction": plan["direction"]},
            "entry": {"entry": plan["entry"], "stop_loss": plan["stop_loss"],
                      "tp1": plan["tp1"], "tp2_runner": plan["tp2"]},
            "risk": {"risk_percent": ticket["risk_pct"], "normalized_volume": ticket["volume"]},
            "timing": {"created_at": ticket["evaluated_at"], "expires_at": ticket["valid_until"]},
            "evidence": {"reason_codes": ticket["reason_codes"]},
        }
        ticket["render_result"] = render_informational_ticket(
            logical_ticket_id=record.logical_ticket_id(), cycle=ticket["cycle"],
            trading_date=record.trading_date.isoformat(), decision_status="READY", proposal=proposal, warnings=ticket["warnings"],
            venue="MT5_VT_MARKETS", freshness_status="CURRENT",
        )
    return ticket, archive_path


def run_crypto_cfd_windows(now: dt.datetime, *, feed: ReadOnlyCryptoFeed | None,
                           archive_root: str, balance: float | None = None) -> list[tuple[dict, str]]:
    """Never silently omit either instrument, including weekends and feed failures."""
    return [run_crypto_cfd_cycle(s, now, feed=feed, archive_root=archive_root, balance=balance)
            for s in INSTRUMENTS]
