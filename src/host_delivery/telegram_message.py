"""Optional host-side message-only Telegram delivery (AG V1 host go-live kit, step 6).

- Off by default. The repo default stays ARCHIVE_ONLY (config/ticket_delivery.yaml is
  unchanged). Delivery is enabled only by the host-local, gitignored override
  config/local/delivery_override.yaml, which scripts/host/enable_telegram.ps1 writes after
  a successful test message.
- Scope: READY informational tickets and Large-SMC OPPORTUNITY alerts only. WATCH/INFO
  alerts and NO_TRADE/DATA_ERROR/BLOCKED tickets stay archive-only.
- Message-only: plain text; no reply_markup, keyboards, buttons or callbacks.
- Secrets: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are read from the environment at send
  time. They are never written to disk, printed or logged. Errors are sanitized so the
  token (which is part of the request URL) cannot leak through an exception message.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from typing import Any, Dict, Optional

import yaml

from telegram_delivery.scope_policy import resolve as resolve_immediate_scope
from host_evidence.symbol_metadata import load_record
from ticket_delivery.identity import logical_ticket_id
from v1_tickets.guards import STALE_AFTER

OVERRIDE_PATH = os.path.join("config", "local", "delivery_override.yaml")
MESSAGE_DELIVERY = "MESSAGE_DELIVERY"
ARCHIVE_ONLY = "ARCHIVE_ONLY"
SCOPES = ("TICKET_READY", "LSMC_OPPORTUNITY")          # legacy informational surface (pinned by verify_objective)
MANUAL_SCOPES = ("MANUAL_TICKET_READY",)              # Manual Trade Ticket V1, separate opt-in
# Two distinct notification semantics that must never share a state:
#   kind TICKET / value READY            -> LEGACY_INFORMATIONAL_READY (V1 informational ticket; scope TICKET_READY)
#   kind MANUAL_TICKET / MANUAL_TICKET_READY -> Manual Trade Ticket V1 readiness (own scope, opt-in)
# A signal can be legacy READY while its manual ticket is TICKET_BLOCKED (e.g. LOGIC_GATE_FAIL:L2).
LEGACY_INFORMATIONAL_READY = "LEGACY_INFORMATIONAL_READY"
MANUAL_TICKET = "MANUAL_TICKET"
MANUAL_TICKET_READY = "MANUAL_TICKET_READY"
API = "https://api.telegram.org"


class TelegramSendError(RuntimeError):
    """Sanitized Telegram failure with a conservative delivery classification."""
    def __init__(self, message: str, delivery_state: str = "DELIVERY_UNCERTAIN"):
        super().__init__(message)
        self.delivery_state = delivery_state


def load_mode(root: str = ".") -> Dict[str, Any]:
    try:
        with open(os.path.join(root, OVERRIDE_PATH), encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except (OSError, ValueError):
        return {"mode": ARCHIVE_ONLY, "scopes": ()}
    scope = resolve_immediate_scope(root, sender="legacy")
    if scope["error"]:
        return {"mode": ARCHIVE_ONLY, "scopes": (), "error": scope["error"]}
    if raw.get("mode") != MESSAGE_DELIVERY:
        return {"mode": ARCHIVE_ONLY, "scopes": ()}
    effective = set(scope["effective"])
    return {"mode": MESSAGE_DELIVERY,
            "scopes": tuple(s for s in raw.get("scopes", ()) if s in SCOPES + MANUAL_SCOPES
                             and s in effective)}


def should_send(kind: str, value: str, root: str = ".") -> bool:
    cfg = load_mode(root)
    if cfg["mode"] != MESSAGE_DELIVERY:
        return False
    if kind == "TICKET":
        return value == "READY" and "TICKET_READY" in cfg["scopes"]
    if kind == MANUAL_TICKET:
        return value == MANUAL_TICKET_READY and MANUAL_TICKET_READY in cfg["scopes"]
    if kind == "LSMC":
        return value == "OPPORTUNITY" and "LSMC_OPPORTUNITY" in cfg["scopes"]
    return False


def send_message(text: str, session: Optional[Any] = None) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        raise TelegramSendError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set in the environment",
                                delivery_state="BLOCKED")
    if session is None:
        import requests as session  # noqa: N813
    try:
        resp = session.post(f"{API}/bot{token}/sendMessage", timeout=10,
                            data={"chat_id": chat_id, "text": text[:4000], "disable_web_page_preview": True})
        status_code = getattr(resp, "status_code", 0)
        ok = status_code == 200 and bool((resp.json() or {}).get("ok"))
    except Exception as exc:  # noqa: BLE001 -- sanitize: never surface the URL/token
        raise TelegramSendError(f"send failed ({type(exc).__name__})",
                                delivery_state="DELIVERY_UNCERTAIN") from None
    if not ok:
        if status_code == 429:
            delivery_state = "RETRYABLE_REJECTED"
        elif status_code >= 500 or status_code == 408:
            # The server may have processed a request before its ambiguous error response.
            delivery_state = "DELIVERY_UNCERTAIN"
        else:
            delivery_state = "DELIVERY_FAILED"
        raise TelegramSendError(f"send failed (HTTP {status_code})", delivery_state=delivery_state)


MMT = dt.timezone(dt.timedelta(hours=6, minutes=30))
# Display-only pip sizes (targets.pip_size convention: 5/3-digit FX). Gold and crypto print price units.
_PIP = {"EURUSD": 0.0001, "GBPUSD": 0.0001, "USDJPY": 0.01}


def _ts(value: Optional[Any]) -> str:
    """'HH:MM MMT / HH:MM UTC (YYYY-MM-DD)' for an ISO string or datetime; 'n/a' when unknown."""
    if not value:
        return "n/a"
    t = value if isinstance(value, dt.datetime) else dt.datetime.fromisoformat(str(value))
    t = t.astimezone(dt.timezone.utc)
    return f"{t.astimezone(MMT):%H:%M} MMT / {t:%H:%M} UTC ({t:%Y-%m-%d})"


def _dist(symbol: str, value: float, decimals: int = 1) -> str:
    pip = _PIP.get(symbol)
    return f"{value / pip:.{decimals}f} pips" if pip else f"{value:g} (price units)"


UNNORMALIZED = "(unnormalized: no verified symbol metadata)"
_ROUNDING = {"nearest": ROUND_HALF_UP, "floor": ROUND_FLOOR, "ceil": ROUND_CEILING}
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _configured_broker_symbol(ticket: Dict[str, Any]) -> Optional[str]:
    """Resolve the exact configured MT5 symbol for a versioned crypto ticket, if present."""
    tag = ticket.get("ticket_config")
    if not isinstance(tag, str):
        return None
    config_id, sep, raw_version = tag.rpartition("@v")
    if not sep or config_id != "AG_V1_CRYPTO_TICKET" or not raw_version.isdigit():
        return None
    version = int(raw_version)
    path = os.path.join(REPO_ROOT, "config", "v1_tickets", f"crypto_ticket_v{version}.yaml")
    try:
        with open(path, encoding="utf-8") as stream:
            config = yaml.safe_load(stream) or {}
    except (OSError, ValueError, yaml.YAMLError):
        return None
    if not isinstance(config, dict):
        return None
    venue = config.get("venue")
    if (config.get("config_id") != config_id or config.get("version") != version
            or not isinstance(venue, dict) or venue.get("kind") != "MT5"):
        return None
    symbols = venue.get("symbols")
    if not isinstance(symbols, dict):
        return None
    broker = symbols.get(ticket.get("symbol"))
    return broker if isinstance(broker, str) and broker else None


def _display_record(symbol: str, broker_symbol: Optional[str] = None):
    """Return verified capture only when its recorded broker name matches the selected mapping."""
    record = load_record(symbol)
    if broker_symbol is None:
        return record
    if record is not None and record.get("broker_symbol") == broker_symbol:
        return record
    record = load_record(broker_symbol)
    return record if record is not None and record.get("broker_symbol") == broker_symbol else None


def _tick_digits(symbol: str, broker_symbol: Optional[str] = None):
    record = _display_record(symbol, broker_symbol)
    if record is None:
        return None, None
    fields = record.get("fields") or {}
    try:
        tick, digits = float(fields.get("trade_tick_size") or 0), int(fields["digits"])
    except (TypeError, ValueError, KeyError):
        return None, None
    return (tick, digits) if tick > 0 and digits >= 0 else (None, None)


def _normalizer(symbol: str, risk: Optional[float], broker_symbol: Optional[str] = None):
    """Display-only conservative tick snap, or None when verified metadata is unavailable."""
    tick, digits = _tick_digits(symbol, broker_symbol)
    if tick is None or (risk is not None and tick >= abs(risk)):
        return None

    def snap(value: Optional[float], mode: str = "nearest") -> Optional[float]:
        if value is None:
            return None
        step = Decimal(repr(tick))
        units = (Decimal(repr(round(float(value), 10))) / step).to_integral_value(rounding=_ROUNDING[mode])
        return round(float(units * step), digits)
    return snap


def _rounding_modes(direction: Optional[str]):
    """(stop, target): conservative display rounding, away from entry for stops."""
    if direction == "LONG":
        return "floor", "floor"
    if direction == "SHORT":
        return "ceil", "ceil"
    return "nearest", "nearest"


def _ticket_id(t: Dict[str, Any]) -> str:
    try:
        return logical_ticket_id(strategy_id=t["strategy_id"], strategy_version=t["strategy_version"],
                                 symbol=t["symbol"], cycle=t["cycle"],
                                 trading_date=dt.date.fromisoformat(t.get("session_date") or t["observation_date"]))
    except (KeyError, TypeError, ValueError):
        return "n/a"


def format_ticket(t: Dict[str, Any]) -> str:
    """Formatting only: values come from the ticket; verified metadata only snaps display prices."""
    sym = t["symbol"]
    raw_entry, raw_stop, engine_risk = t.get("entry"), t.get("stop_loss"), t.get("risk_distance")
    raw_risk = engine_risk or (abs(raw_entry - raw_stop)
                               if raw_entry is not None and raw_stop is not None else None)
    broker_symbol = t.get("display_broker_symbol") or _configured_broker_symbol(t)
    snap = _normalizer(sym, raw_risk, broker_symbol)
    stop_mode, target_mode = _rounding_modes(t.get("direction"))
    if snap is None:
        entry, stop, target = raw_entry, raw_stop, lambda value: value
    else:
        entry, stop = snap(raw_entry), snap(raw_stop, stop_mode)
        target = lambda value: snap(value, target_mode)
    expires = (dt.datetime.fromisoformat(t["signal_close_utc"]) + STALE_AFTER) if t.get("signal_close_utc") else None
    lines = [t.get("label", "INFORMATIONAL TICKET -- NOT A BROKER ORDER"),
             f"{sym} {t.get('direction', '')} ({t.get('cycle', '')})",
             f"{t['strategy_id']} v{t['strategy_version']}  decision={t['decision']}",
             f"ticket_id: {_ticket_id(t)}"]
    if t.get("window"):
        lines.append(f"window: {t['window']}  status: {t.get('ticket_status', '')}")
    elif t.get("cycle"):
        invalidation = f"  time invalidation {t['time_invalidation_gmt']} GMT" if t.get("time_invalidation_gmt") else ""
        lines.append(f"window: {t['cycle']} trade session{invalidation}")
    if t.get("window_label"):
        lines.append(t["window_label"])
    lines += [f"signal close: {_ts(t.get('signal_close_utc'))}", f"expires_at: {_ts(expires)}"]
    risk = abs(entry - stop) if snap and entry is not None and stop is not None else raw_risk
    if entry is not None:
        note = f" {UNNORMALIZED}" if snap is None else ""
        if snap and risk and engine_risk and abs(engine_risk - risk) > 1e-9 * max(abs(risk), 1.0):
            note = f" (engine {_dist(sym, engine_risk, 2)} before rounding)"
        lines.append(f"entry: {entry}  stop: {stop}" + (f"  risk: {_dist(sym, risk)}{note}" if risk else ""))
    sign = -1.0 if t.get("direction") == "SHORT" else 1.0
    r_of = lambda price: f"  = {sign * (price - entry) / risk:+.2f}R" if risk and entry is not None and price is not None else ""  # noqa: E731
    for key in ("tp1", "tp2"):
        if t.get(key) is not None:
            price = target(t[key])
            lines.append(f"{key}: {price}{r_of(price)}")
    for leg in t.get("targets") or ():
        pct = f", {leg['volume_pct']:.0%}" if leg.get("volume_pct") is not None else ""
        price = target(leg["price"])
        lines.append(f"target leg {leg['leg']} ({leg['type']}{pct}): {price}{r_of(price)}")
    if t.get("spread_check"):
        spread_text = ""
        if t.get("spread") is not None:
            spread_text = f"  spread {_dist(sym, t['spread'])}"
            if t.get("spread_risk_fraction") is not None:
                spread_text += f" = {t['spread_risk_fraction']:.1%} of risk (max {t.get('spread_max_risk_fraction', 0.15):.0%})"
        lines.append(f"spread_check: {t['spread_check']}{spread_text}")
    lines.append(f"data source: {t.get('data_source')}")
    lines.append(f"VALID UNTIL {_ts(expires)} -- STALE after; re-check before acting." if expires
                 else "VALID UNTIL: n/a (signal close not recorded) -- re-check before acting.")
    return "\n".join(lines)


TIMEFRAME_CHAIN = "D1 context -> H1 bias + POI -> M5 sweep/CHoCH"


def format_alert(e: Dict[str, Any], price: Optional[float] = None) -> str:
    """Formatting only; tick snapping is based on the exact verified broker-symbol capture."""
    payload = e.get("payload") or {}
    poi, opportunity = payload.get("poi") or {}, payload.get("opportunity") or {}
    symbol = e["symbol"]
    direction = opportunity.get("direction") or poi.get("direction") or payload.get("bias") or "n/a"
    entry_reference, stop_c10 = opportunity.get("entry_reference"), opportunity.get("stop_c10")
    raw_risk = abs(entry_reference - stop_c10) if entry_reference is not None and stop_c10 is not None else None
    broker_symbol = e.get("display_broker_symbol")
    snap = _normalizer(symbol, raw_risk, broker_symbol)
    stop_mode, target_mode = _rounding_modes(direction)
    if snap is None:
        def display(value, _mode="nearest"):
            return None if value is None else round(float(value), 10)
    else:
        def display(value, mode="nearest"):
            return snap(value, mode)

    lines = ["LARGE-SMC ALERT -- INFORMATIONAL -- NOT A BROKER ORDER",
             f"{symbol} {e['to_state']} ({e['alert_level']})  direction: {direction}",
             f"{e['strategy_id']} v{e['strategy_version']}  economic_status=NOT_EVALUATED",
             f"ref: {e.get('reference_id')}",
             f"timeframes: {TIMEFRAME_CHAIN}"]
    low, high = poi.get("low"), poi.get("high")
    if low is not None and high is not None:
        lines.append(f"POI zone ({poi.get('kind', 'H1')}): {display(low)} - {display(high)}")
    if opportunity.get("sweep_extreme") is not None:
        side = "below" if direction == "LONG" else "above"
        lines.append(f"invalidation: M5 close {side} {display(opportunity['sweep_extreme'], stop_mode)}")
    elif low is not None and high is not None:
        far_edge = low if direction == "LONG" else high
        lines.append(f"invalidation: close beyond POI far edge {display(far_edge, stop_mode)}")
    if opportunity:
        target_price = opportunity.get("target_c11")
        lines.append(f"liquidity target: {display(target_price, target_mode)}" if target_price is not None
                     else f"liquidity target: none ({opportunity.get('target_reason')})")
        if stop_c10 is not None:
            lines.append(f"stop (C10): {display(stop_c10, stop_mode)}")
        if entry_reference is not None:
            lines.append(f"entry reference (CHoCH close): {display(entry_reference)}")
    if price is not None:
        shown_price = display(price)
        lines.append(f"current price: {shown_price}")
        if low is not None and high is not None:
            distance = 0.0 if low <= price <= high else (price - high if price > high else low - price)
            lines.append("distance to POI: inside zone" if distance == 0
                         else f"distance to POI: {_dist(symbol, distance)}")
    if snap is None:
        lines.append(f"prices {UNNORMALIZED}")
    lines.append(f"expires_at: {_ts(opportunity.get('expires_at') or payload.get('expires_at'))}")
    return "\n".join(lines)


def validation_proposal(now: Optional[dt.datetime] = None) -> Dict[str, Any]:
    """A clearly simulated READY ticket used to validate the real Telegram render/send path.

    It is never archived and never enters a strategy or execution component.
    """
    at = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    signal_close = at - dt.timedelta(minutes=1)
    return {
        "label": "SIMULATED TELEGRAM DELIVERY VALIDATION -- NOT A MARKET SIGNAL",
        "strategy_id": "TELEGRAM_DELIVERY_VALIDATION",
        "strategy_version": "1.0.0",
        "symbol": "EURUSD",
        "cycle": "ASIAN_LONDON",
        "session_date": at.date().isoformat(),
        "decision": "READY",
        "direction": "LONG",
        "entry_order_type": "MARKET",
        "entry": 1.10000,
        "stop_loss": 1.09900,
        "risk_distance": 0.001,
        "targets": [
            {"leg": 1, "volume_pct": 0.75, "type": "VALIDATION_TARGET", "price": 1.10100},
            {"leg": 2, "volume_pct": 0.25, "type": "VALIDATION_5R", "price": 1.10500},
        ],
        "signal_close_utc": signal_close.isoformat(),
        "time_invalidation_gmt": "15:00",
        "spread_check": "PASS",
        "spread": 0.00010,
        "spread_risk_fraction": 0.10,
        "spread_max_risk_fraction": 0.15,
        "data_source": "SIMULATED_VALIDATION_ONLY",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Validate message-only Telegram delivery.")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--test", action="store_true", help="send a short connectivity message")
    group.add_argument("--test-proposal", action="store_true",
                       help="send a clearly simulated, fully-rendered READY proposal")
    group.add_argument("--status", action="store_true",
                       help="verify local scope configuration and credential presence without sending")
    args = ap.parse_args(argv)
    if args.status:
        cfg = load_mode(os.getcwd())
        credentials = bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))
        scopes_ok = {s for s in cfg["scopes"] if s in SCOPES} == set(SCOPES)   # optional MANUAL_SCOPES ignored
        ok = cfg["mode"] == MESSAGE_DELIVERY and scopes_ok and credentials
        print(f"TELEGRAM_STATUS: {'OK' if ok else 'NOT_READY'} mode={cfg['mode']} "
              f"scopes={','.join(cfg['scopes']) or 'none'} credentials={'PRESENT' if credentials else 'MISSING'}")
        return 0 if ok else 1
    text = (format_ticket(validation_proposal()) if args.test_proposal
            else "AG V1 host go-live: Telegram test message (message-only, no buttons).")
    label = "TELEGRAM_PROPOSAL_TEST" if args.test_proposal else "TELEGRAM_TEST"
    try:
        send_message(text)
    except TelegramSendError as exc:
        print(f"{label}: FAILED {exc}")
        return 1
    print(f"{label}: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
