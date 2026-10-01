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
from typing import Any, Dict, Optional

import yaml

from ticket_delivery.identity import logical_ticket_id
from v1_tickets.guards import STALE_AFTER

OVERRIDE_PATH = os.path.join("config", "local", "delivery_override.yaml")
MESSAGE_DELIVERY = "MESSAGE_DELIVERY"
ARCHIVE_ONLY = "ARCHIVE_ONLY"
SCOPES = ("TICKET_READY", "LSMC_OPPORTUNITY")
API = "https://api.telegram.org"


class TelegramSendError(RuntimeError):
    pass


def load_mode(root: str = ".") -> Dict[str, Any]:
    try:
        with open(os.path.join(root, OVERRIDE_PATH), encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except (OSError, ValueError):
        return {"mode": ARCHIVE_ONLY, "scopes": ()}
    if raw.get("mode") != MESSAGE_DELIVERY:
        return {"mode": ARCHIVE_ONLY, "scopes": ()}
    return {"mode": MESSAGE_DELIVERY, "scopes": tuple(s for s in raw.get("scopes", ()) if s in SCOPES)}


def should_send(kind: str, value: str, root: str = ".") -> bool:
    cfg = load_mode(root)
    if cfg["mode"] != MESSAGE_DELIVERY:
        return False
    if kind == "TICKET":
        return value == "READY" and "TICKET_READY" in cfg["scopes"]
    if kind == "LSMC":
        return value == "OPPORTUNITY" and "LSMC_OPPORTUNITY" in cfg["scopes"]
    return False


def send_message(text: str, session: Optional[Any] = None) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        raise TelegramSendError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set in the environment")
    if session is None:
        import requests as session  # noqa: N813
    try:
        resp = session.post(f"{API}/bot{token}/sendMessage", timeout=10,
                            data={"chat_id": chat_id, "text": text[:4000], "disable_web_page_preview": True})
        ok = getattr(resp, "status_code", 0) == 200 and bool((resp.json() or {}).get("ok"))
    except Exception as exc:  # noqa: BLE001 -- sanitize: never surface the URL/token
        raise TelegramSendError(f"send failed ({type(exc).__name__})") from None
    if not ok:
        raise TelegramSendError(f"send failed (HTTP {getattr(resp, 'status_code', '?')})")


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


def _dist(symbol: str, value: float) -> str:
    pip = _PIP.get(symbol)
    return f"{value / pip:.1f} pips" if pip else f"{value:g} (price units)"


def _ticket_id(t: Dict[str, Any]) -> str:
    try:
        return logical_ticket_id(strategy_id=t["strategy_id"], strategy_version=t["strategy_version"],
                                 symbol=t["symbol"], cycle=t["cycle"],
                                 trading_date=dt.date.fromisoformat(t.get("session_date") or t["observation_date"]))
    except (KeyError, TypeError, ValueError):
        return "n/a"


def format_ticket(t: Dict[str, Any]) -> str:
    """Formatting only: every value is read from the ticket or derived from guards.STALE_AFTER."""
    sym, entry, stop = t["symbol"], t.get("entry"), t.get("stop_loss")
    expires = (dt.datetime.fromisoformat(t["signal_close_utc"]) + STALE_AFTER) if t.get("signal_close_utc") else None
    lines = [t.get("label", "INFORMATIONAL TICKET -- NOT A BROKER ORDER"),
             f"{sym} {t.get('direction', '')} ({t.get('cycle', '')})",
             f"{t['strategy_id']} v{t['strategy_version']}  decision={t['decision']}",
             f"ticket_id: {_ticket_id(t)}"]
    if t.get("window"):
        lines.append(f"window: {t['window']}  status: {t.get('ticket_status', '')}")
    elif t.get("cycle"):
        inv = f"  time invalidation {t['time_invalidation_gmt']} GMT" if t.get("time_invalidation_gmt") else ""
        lines.append(f"window: {t['cycle']} trade session{inv}")
    if t.get("window_label"):
        lines.append(t["window_label"])
    lines += [f"signal close: {_ts(t.get('signal_close_utc'))}", f"expires_at: {_ts(expires)}"]
    risk = t.get("risk_distance") or (abs(entry - stop) if entry is not None and stop is not None else None)
    if entry is not None:
        lines.append(f"entry: {entry}  stop: {stop}" + (f"  risk: {_dist(sym, risk)}" if risk else ""))
    sign = -1.0 if t.get("direction") == "SHORT" else 1.0
    r_of = lambda p: f"  = {sign * (p - entry) / risk:+.2f}R" if risk and entry is not None and p is not None else ""  # noqa: E731
    for key in ("tp1", "tp2"):
        if t.get(key) is not None:
            lines.append(f"{key}: {t[key]}{r_of(t[key])}")
    for leg in t.get("targets") or ():
        pct = f", {leg['volume_pct']:.0%}" if leg.get("volume_pct") is not None else ""
        lines.append(f"target leg {leg['leg']} ({leg['type']}{pct}): {leg['price']}{r_of(leg['price'])}")
    if t.get("spread_check"):
        sp = ""
        if t.get("spread") is not None:
            sp = f"  spread {_dist(sym, t['spread'])}"
            if t.get("spread_risk_fraction") is not None:
                sp += f" = {t['spread_risk_fraction']:.1%} of risk (max {t.get('spread_max_risk_fraction', 0.15):.0%})"
        lines.append(f"spread_check: {t['spread_check']}{sp}")
    lines.append(f"data source: {t.get('data_source')}")
    lines.append(f"VALID UNTIL {_ts(expires)} -- STALE after; re-check before acting." if expires
                 else "VALID UNTIL: n/a (signal close not recorded) -- re-check before acting.")
    return "\n".join(lines)


TIMEFRAME_CHAIN = "D1 context -> H1 bias + POI -> M5 sweep/CHoCH"


def format_alert(e: Dict[str, Any], price: Optional[float] = None) -> str:
    """Formatting only. `price` is the latest M5 close the runner already holds (display, not a rule input)."""
    p = e.get("payload") or {}
    poi, opp = p.get("poi") or {}, p.get("opportunity") or {}
    sym = e["symbol"]
    direction = opp.get("direction") or poi.get("direction") or p.get("bias") or "n/a"
    lines = ["LARGE-SMC ALERT -- INFORMATIONAL -- NOT A BROKER ORDER",
             f"{sym} {e['to_state']} ({e['alert_level']})  direction: {direction}",
             f"{e['strategy_id']} v{e['strategy_version']}  economic_status=NOT_EVALUATED",
             f"ref: {e.get('reference_id')}",
             f"timeframes: {TIMEFRAME_CHAIN}"]
    lo, hi = poi.get("low"), poi.get("high")
    if lo is not None and hi is not None:
        lines.append(f"POI zone ({poi.get('kind', 'H1')}): {lo} - {hi}")
    if opp.get("sweep_extreme") is not None:
        side = "below" if direction == "LONG" else "above"
        lines.append(f"invalidation: M5 close {side} {opp['sweep_extreme']}")
    elif lo is not None and hi is not None:
        lines.append(f"invalidation: close beyond POI far edge {lo if direction == 'LONG' else hi}")
    if opp:
        tgt = opp.get("target_c11")
        lines.append(f"liquidity target: {tgt}" if tgt is not None else f"liquidity target: none ({opp.get('target_reason')})")
        if opp.get("stop_c10") is not None:
            lines.append(f"stop (C10): {opp['stop_c10']}")
        if opp.get("entry_reference") is not None:
            lines.append(f"entry reference (CHoCH close): {opp['entry_reference']}")
    if price is not None:
        lines.append(f"current price: {price}")
        if lo is not None and hi is not None:
            d = 0.0 if lo <= price <= hi else (price - hi if price > hi else lo - price)
            lines.append("distance to POI: inside zone" if d == 0 else f"distance to POI: {_dist(sym, d)}")
    lines.append(f"expires_at: {_ts(opp.get('expires_at') or p.get('expires_at'))}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Send one Telegram test message (message-only).")
    ap.add_argument("--test", action="store_true", required=True)
    ap.parse_args(argv)
    try:
        send_message("AG V1 host go-live: Telegram test message (message-only, no buttons).")
    except TelegramSendError as exc:
        print(f"TELEGRAM_TEST: FAILED {exc}")
        return 1
    print("TELEGRAM_TEST: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
