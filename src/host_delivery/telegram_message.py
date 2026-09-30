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
import os
import sys
from typing import Any, Dict, Optional

import yaml

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


def format_ticket(t: Dict[str, Any]) -> str:
    lines = [t.get("label", "INFORMATIONAL TICKET -- NOT A BROKER ORDER"),
             f"{t['symbol']} {t.get('direction', '')} ({t.get('cycle', '')})",
             f"{t['strategy_id']} v{t['strategy_version']}  decision={t['decision']}"]
    if t.get("window"):
        lines.append(f"window: {t['window']}  status: {t.get('ticket_status', '')}")
    if t.get("window_label"):
        lines.append(t["window_label"])
    for key in ("entry", "stop_loss", "tp1", "tp2"):
        if t.get(key) is not None:
            lines.append(f"{key}: {t[key]}")
    for leg in t.get("targets") or ():
        lines.append(f"target leg {leg['leg']} ({leg['type']}): {leg['price']}")
    lines.append(f"data source: {t.get('data_source')}")
    return "\n".join(lines)


def format_alert(e: Dict[str, Any]) -> str:
    return "\n".join([
        "LARGE-SMC ALERT -- INFORMATIONAL, NOT A BROKER ORDER",
        f"{e['symbol']} {e['to_state']} ({e['alert_level']})",
        f"{e['strategy_id']} v{e['strategy_version']}  economic_status=NOT_EVALUATED",
        f"ref: {e.get('reference_id')}",
    ])


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
