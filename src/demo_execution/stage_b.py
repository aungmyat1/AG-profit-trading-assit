"""Owner-triggered Stage-B MT5 Demo placement. Disabled unless explicitly enabled.

This module is deliberately not imported by schedulers. The caller must inject an MT5-like
object and separately register a one-use approval token for the exact client order id.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
import secrets
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

RISK_FRACTION = 0.005
DAILY_LOSS_FRACTION = 0.02
MAX_TRADES_PER_DAY = 3
APPROVED_SERVER = "VTMarkets-Demo"


class DemoExecutionRefused(RuntimeError):
    """Fail-closed Stage-B refusal."""


@dataclass(frozen=True)
class PreparedTicket:
    status: str
    client_order_id: str
    symbol: str
    direction: str
    entry: float
    stop_loss: float
    take_profit: float

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "PreparedTicket":
        try:
            ticket = cls(
                status=str(raw["status"]), client_order_id=str(raw["client_order_id"]),
                symbol=str(raw["symbol"]), direction=str(raw["direction"]).upper(),
                entry=float(raw["entry"]), stop_loss=float(raw["stop_loss"]),
                take_profit=float(raw["take_profit"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise DemoExecutionRefused("INVALID_TICKET") from exc
        if ticket.status != "PREPARED_ONLY":
            raise DemoExecutionRefused("TICKET_NOT_PREPARED_ONLY")
        if not ticket.client_order_id or ticket.direction not in {"BUY", "SELL"}:
            raise DemoExecutionRefused("INVALID_TICKET")
        if min(ticket.entry, ticket.stop_loss, ticket.take_profit) <= 0:
            raise DemoExecutionRefused("INVALID_GEOMETRY")
        if ticket.direction == "BUY" and not ticket.stop_loss < ticket.entry < ticket.take_profit:
            raise DemoExecutionRefused("INVALID_GEOMETRY")
        if ticket.direction == "SELL" and not ticket.take_profit < ticket.entry < ticket.stop_loss:
            raise DemoExecutionRefused("INVALID_GEOMETRY")
        return ticket


class ApprovalStore:
    """Persistent one-use approval tokens; only salted hashes are written to disk."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def approve(self, client_order_id: str, token: str) -> None:
        if not client_order_id or len(token) < 16:
            raise ValueError("approval token must contain at least 16 characters")
        salt = secrets.token_hex(16)
        record = {"salt": salt, "digest": self._digest(salt, token), "used": False}
        self._write_new(self.root / f"{_safe_id(client_order_id)}.json", record)

    def consume(self, client_order_id: str, token: str) -> None:
        path = self.root / f"{_safe_id(client_order_id)}.json"
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise DemoExecutionRefused("OWNER_APPROVAL_MISSING") from exc
        if record.get("used") or not secrets.compare_digest(record.get("digest", ""), self._digest(record["salt"], token)):
            raise DemoExecutionRefused("OWNER_APPROVAL_INVALID_OR_USED")
        record["used"] = True
        _atomic_json(path, record)

    @staticmethod
    def _digest(salt: str, token: str) -> str:
        return hashlib.sha256(f"{salt}:{token}".encode()).hexdigest()

    @staticmethod
    def _write_new(path: Path, value: Mapping[str, Any]) -> None:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise DemoExecutionRefused("APPROVAL_ALREADY_REGISTERED") from exc
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True)


class ReconciliationLog:
    """Append-only JSONL audit log with a hash chain."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: str, client_order_id: str, payload: Mapping[str, Any]) -> None:
        previous = self._last_hash()
        body = {
            "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "event": event,
            "client_order_id": client_order_id, "payload": dict(payload), "previous_hash": previous,
        }
        body["record_hash"] = hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(body, sort_keys=True, default=str) + "\n")

    def _last_hash(self) -> str | None:
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
            return json.loads(lines[-1])["record_hash"] if lines else None
        except (OSError, ValueError, KeyError):
            return None


class DemoStageB:
    def __init__(self, mt5: Any, state_dir: Path, *, enabled: bool = False, kill_switch_file: Path | None = None):
        self.mt5 = mt5
        self.enabled = enabled
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.kill_switch_file = Path(kill_switch_file or self.state_dir / "KILL_SWITCH")
        self.approvals = ApprovalStore(self.state_dir / "approvals")
        self.log = ReconciliationLog(self.state_dir / "reconciliation.jsonl")
        (self.state_dir / "orders").mkdir(exist_ok=True)

    def place(self, raw_ticket: Mapping[str, Any], approval_token: str, *, now: dt.datetime | None = None) -> Mapping[str, Any]:
        ticket = PreparedTicket.from_mapping(raw_ticket)
        now = now or dt.datetime.now(dt.timezone.utc)
        if now.tzinfo is None:
            raise DemoExecutionRefused("NOW_MUST_BE_TIMEZONE_AWARE")
        self.log.append("REQUEST_RECEIVED", ticket.client_order_id, {"ticket": asdict(ticket)})
        try:
            self._preflight(ticket, approval_token, now)
            request = self._build_request(ticket)
            self._claim(ticket.client_order_id, request)
            self.log.append("ORDER_SEND_ATTEMPT", ticket.client_order_id, {"request": request})
            result = self.mt5.order_send(request)
            result_data = _public_fields(result)
            self.log.append("ORDER_SEND_RESULT", ticket.client_order_id, result_data)
            done_codes = {getattr(self.mt5, "TRADE_RETCODE_DONE", object()), getattr(self.mt5, "TRADE_RETCODE_DONE_PARTIAL", object())}
            if getattr(result, "retcode", None) not in done_codes:
                self._set_state(ticket.client_order_id, "REJECTED", result_data)
                raise DemoExecutionRefused("ORDER_REJECTED")
            positions = [_public_fields(p) for p in (self.mt5.positions_get(symbol=ticket.symbol) or ())]
            self.log.append("POST_SEND_RECONCILIATION", ticket.client_order_id, {"positions": positions})
            self._set_state(ticket.client_order_id, "CONFIRMED", result_data)
            return {"status": "CONFIRMED", "client_order_id": ticket.client_order_id, "result": result_data}
        except DemoExecutionRefused as exc:
            self.log.append("REFUSED", ticket.client_order_id, {"reason": str(exc)})
            raise

    def _preflight(self, ticket: PreparedTicket, approval_token: str, now: dt.datetime) -> None:
        if not self.enabled:
            raise DemoExecutionRefused("DEMO_STAGE_B_DISABLED")
        if self.kill_switch_file.exists():
            raise DemoExecutionRefused("KILL_SWITCH_ACTIVE")
        account = self.mt5.account_info()
        if account is None:
            raise DemoExecutionRefused("ACCOUNT_UNAVAILABLE")
        if getattr(account, "trade_mode", None) != getattr(self.mt5, "ACCOUNT_TRADE_MODE_DEMO", object()):
            raise DemoExecutionRefused("ACCOUNT_NOT_DEMO")
        if getattr(account, "server", None) != APPROVED_SERVER:
            raise DemoExecutionRefused("SERVER_NOT_APPROVED")
        self._daily_limits(account, now)
        if self._order_path(ticket.client_order_id).exists():
            raise DemoExecutionRefused("DUPLICATE_CLIENT_ORDER_ID")
        self.approvals.consume(ticket.client_order_id, approval_token)

    def _daily_limits(self, account: Any, now: dt.datetime) -> None:
        start = now.astimezone(dt.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        deals = tuple(self.mt5.history_deals_get(start, now) or ())
        entries = [d for d in deals if getattr(d, "entry", None) == getattr(self.mt5, "DEAL_ENTRY_IN", object())]
        if len(entries) >= MAX_TRADES_PER_DAY:
            raise DemoExecutionRefused("MAX_TRADES_PER_DAY_REACHED")
        closed = [d for d in deals if getattr(d, "entry", None) == getattr(self.mt5, "DEAL_ENTRY_OUT", object())]
        realized = sum(float(getattr(d, field, 0.0) or 0.0) for d in closed for field in ("profit", "commission", "swap", "fee"))
        equity = float(getattr(account, "equity", 0.0) or 0.0)
        start_equity = equity - realized
        if start_equity <= 0 or realized <= -(start_equity * DAILY_LOSS_FRACTION):
            raise DemoExecutionRefused("DAILY_LOSS_CAP_REACHED")

    def _build_request(self, ticket: PreparedTicket) -> dict[str, Any]:
        info = self.mt5.symbol_info(ticket.symbol)
        tick = self.mt5.symbol_info_tick(ticket.symbol)
        if info is None or tick is None:
            raise DemoExecutionRefused("SYMBOL_UNAVAILABLE")
        tick_size = float(getattr(info, "trade_tick_size", 0.0) or 0.0)
        tick_value = float(getattr(info, "trade_tick_value", 0.0) or 0.0)
        account = self.mt5.account_info()
        equity = float(getattr(account, "equity", 0.0) or 0.0)
        if tick_size <= 0 or tick_value <= 0 or equity <= 0:
            raise DemoExecutionRefused("SIZING_METADATA_INVALID")
        risk_per_lot = abs(ticket.entry - ticket.stop_loss) / tick_size * tick_value
        raw_volume = equity * RISK_FRACTION / risk_per_lot
        step = float(getattr(info, "volume_step", 0.0) or 0.0)
        minimum = float(getattr(info, "volume_min", 0.0) or 0.0)
        maximum = float(getattr(info, "volume_max", 0.0) or 0.0)
        if step <= 0 or minimum <= 0 or maximum < minimum:
            raise DemoExecutionRefused("SIZING_METADATA_INVALID")
        volume = math.floor((raw_volume + 1e-12) / step) * step
        if volume < minimum:
            raise DemoExecutionRefused("RISK_TOO_SMALL_FOR_MINIMUM_VOLUME")
        volume = min(volume, maximum)
        is_buy = ticket.direction == "BUY"
        return {
            "action": self.mt5.TRADE_ACTION_DEAL, "symbol": ticket.symbol, "volume": round(volume, 8),
            "type": self.mt5.ORDER_TYPE_BUY if is_buy else self.mt5.ORDER_TYPE_SELL,
            "price": float(tick.ask if is_buy else tick.bid), "sl": ticket.stop_loss, "tp": ticket.take_profit,
            "deviation": 10, "magic": 730502, "comment": f"AGB:{ticket.client_order_id}"[:31],
            "type_time": self.mt5.ORDER_TIME_GTC, "type_filling": self.mt5.ORDER_FILLING_IOC,
        }

    def _order_path(self, client_order_id: str) -> Path:
        return self.state_dir / "orders" / f"{_safe_id(client_order_id)}.json"

    def _claim(self, client_order_id: str, request: Mapping[str, Any]) -> None:
        ApprovalStore._write_new(self._order_path(client_order_id), {"state": "SEND_CLAIMED", "request": dict(request)})

    def _set_state(self, client_order_id: str, state: str, result: Mapping[str, Any]) -> None:
        _atomic_json(self._order_path(client_order_id), {"state": state, "result": dict(result)})


def _safe_id(value: str) -> str:
    if not value or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_." for c in value):
        raise DemoExecutionRefused("INVALID_CLIENT_ORDER_ID")
    return value


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, sort_keys=True, default=str), encoding="utf-8")
    os.replace(tmp, path)


def _public_fields(value: Any) -> dict[str, Any]:
    if value is None:
        return {"value": None}
    if hasattr(value, "_asdict"):
        return dict(value._asdict())
    return {k: v for k, v in vars(value).items() if not k.startswith("_")}
