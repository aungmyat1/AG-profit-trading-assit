"""C14 risk snapshot builder: per-scope and account daily metrics for the current VT server day.

Read-only. The injected MT5 module is asked for exactly three things -- account_info,
history_deals_get over the server day and positions_get -- once per build, so every scope sees the
same broker state. Nothing here sends, checks, modifies or closes anything. The built
`RiskSnapshot` is what the caller hands to the guarded boundary (GuardedCanonicalAdapter /
evaluate_pre_send_gates); `evaluate_risk_caps` then applies the C14 caps unchanged.

Fail closed: an unknown server-day rule, a missing account/deal/position read, a deal or position
the snapshot cannot attribute or price, or a broker timestamp ahead of the server clock yields
status BLOCKED with no snapshot -- admission then refuses with RISK_SNAPSHOT_MISSING. Staleness of a
built snapshot is enforced at admission (risk.evaluate_risk_caps, STALE_AFTER).

Conventions (to be host-verified, like the margin mode):
* MT5 deal/position times are server-clock epoch seconds; the day window is
  [server midnight, server now] on that clock (vt_day).
* Realized P&L = profit + swap + commission + fee of BUY/SELL deals in the window (balance,
  credit and other non-trade deals are excluded); open P&L = profit + swap of open positions.
* Carried positions (conservative approximation): the server-midnight mark of a position opened
  before the day start is unknown, so only adverse movement is counted. An open carried position
  contributes min(0, profit + swap); a closing deal today whose position has no entry-IN deal in
  today's window (opened before the day start, or unknown -> treated as carried) contributes
  min(0, pnl). Carried gains are never counted and nothing offsets a carried loss:
  daily loss = max(0, -(today realized + today open)) + |carried adverse|.
* Equity basis = current equity (conservative: after a loss it is smaller than the day-start
  basis, so the loss % is larger). Loss % = daily loss / current equity x 100, the same DEMO-equity
  basis risk.evaluate_risk_caps sizes against. 1R = MAX_RISK_PER_TRADE_PCT of that equity.
* Trades today (per scope) = distinct position ids among entry-IN BUY/SELL deals carrying the
  scope's magic number (two fills of one trade count once).
* Account metrics include every deal and position (own, foreign or manual).
* Scope magic numbers must be distinct; a duplicate blocks (deals could not be attributed).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Mapping, Optional, Sequence

from demo_execution import vt_day
from demo_execution.risk import MAX_RISK_PER_TRADE_PCT, OpenPosition, RiskSnapshot

OK = "OK"
BLOCKED = "BLOCKED"
SERVER_DAY_UNAVAILABLE = "RISK_SERVER_DAY_UNAVAILABLE"
ACCOUNT_UNAVAILABLE = "RISK_BROKER_ACCOUNT_UNAVAILABLE"
EQUITY_INVALID = "RISK_DEMO_EQUITY_UNAVAILABLE"
DEALS_UNAVAILABLE = "RISK_BROKER_DEALS_UNAVAILABLE"
POSITIONS_UNAVAILABLE = "RISK_BROKER_POSITIONS_UNAVAILABLE"
DATA_INVALID = "RISK_BROKER_DATA_INVALID"
CLOCK_AHEAD = "RISK_BROKER_TIME_AHEAD_OF_SERVER_CLOCK"
SCOPES_MISSING = "RISK_SCOPES_MISSING"
MAGIC_DUPLICATE = "RISK_SCOPE_MAGIC_DUPLICATE"

DEAL_TYPE_BUY, DEAL_TYPE_SELL = 0, 1
DEAL_ENTRY_IN = 0
_EPOCH = datetime(1970, 1, 1)


@dataclass(frozen=True)
class RiskSnapshotBuild:
    status: str
    reason_code: Optional[str]
    server_day: Optional[date] = None
    observed_at_utc: Optional[datetime] = None
    account: Mapping[str, Any] = field(default_factory=dict)
    scopes: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)

    def snapshot_for(self, scope: Any) -> Optional[RiskSnapshot]:
        """The scope's RiskSnapshot, or None (admission blocks: RISK_SNAPSHOT_MISSING)."""
        if self.status != OK:
            return None
        return (self.scopes.get(scope_key(scope)) or {}).get("snapshot")


def scope_key(scope: Any) -> str:
    return f"{scope.strategy_id}@{scope.strategy_version}:{scope.symbol}:{scope.session}"


def _get(obj: Any, name: str) -> Any:
    return obj.get(name) if isinstance(obj, Mapping) else getattr(obj, name, None)


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        return None
    return float(value)


def _integer(value: Any) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _blocked(reason: str, **kwargs: Any) -> RiskSnapshotBuild:
    return RiskSnapshotBuild(BLOCKED, reason, **kwargs)


def _clock(seconds: Any) -> Optional[datetime]:
    value = _integer(seconds)
    return None if value is None or value < 0 else _EPOCH + timedelta(seconds=value)


def _metrics(book: Mapping[str, float], equity: float, trades: Optional[int] = None) -> dict[str, Any]:
    realized, open_pnl, carried = book["realized"], book["open"], book["carried_adverse"]
    total = realized + open_pnl + carried
    loss = max(0.0, -(realized + open_pnl)) - carried          # carried is <= 0 and never offset
    one_r = equity * MAX_RISK_PER_TRADE_PCT / 100
    out = {"realized_pnl": round(realized, 8), "open_pnl": round(open_pnl, 8),
           "carried_adverse_pnl": round(carried, 8), "total_pnl": round(total, 8),
           "realized_R": round(realized / one_r, 6), "open_R": round(open_pnl / one_r, 6),
           "carried_adverse_R": round(carried / one_r, 6), "total_R": round(total / one_r, 6),
           "total_pct": round(total / equity * 100, 6), "daily_loss_R": round(loss / one_r, 6),
           "daily_loss_pct": round(loss / equity * 100, 6)}
    if trades is not None:
        out["trades_today"] = trades
    return out


def build_risk_snapshots(mt5: Any, scopes: Sequence[Any], *, metadata: Mapping[str, Any], now_utc: datetime,
                         symbol_meta: Optional[Mapping[str, Any]] = None) -> RiskSnapshotBuild:
    """One read-only broker read set -> a RiskSnapshot per scope plus account metrics.

    `metadata` is the committed host symbol metadata carrying the server-day rule;
    `symbol_meta` maps scope_key -> verified SymbolMeta (passed through for sizing)."""
    if not scopes:
        return _blocked(SCOPES_MISSING)
    magic_list = [s.magic_number for s in scopes]
    if len(set(magic_list)) != len(magic_list):
        return _blocked(MAGIC_DUPLICATE)
    now = now_utc.astimezone(timezone.utc) if isinstance(now_utc, datetime) and now_utc.tzinfo else None
    day = vt_day.server_day(now, metadata) if now else None
    clock_now = vt_day.server_clock(now, metadata) if now else None
    if day is None or clock_now is None or any(s.daily_reset_basis != "VT_SERVER_DAY" for s in scopes):
        return _blocked(SERVER_DAY_UNAVAILABLE)
    day_start = datetime.combine(day, datetime.min.time())
    base = {"server_day": day, "observed_at_utc": now}

    account = mt5.account_info()
    if account is None:
        return _blocked(ACCOUNT_UNAVAILABLE, **base)
    equity = _number(_get(account, "equity"))
    if equity is None or equity <= 0:
        return _blocked(EQUITY_INVALID, **base)
    # Server-clock wall times, tz-tagged UTC so the MT5 package applies no local-zone conversion.
    deals = mt5.history_deals_get(day_start.replace(tzinfo=timezone.utc), clock_now.replace(tzinfo=timezone.utc))
    if deals is None:
        return _blocked(DEALS_UNAVAILABLE, **base)
    positions = mt5.positions_get()
    if positions is None:
        return _blocked(POSITIONS_UNAVAILABLE, **base)

    magics = {scope_key(s): s.magic_number for s in scopes}
    books = {key: {"realized": 0.0, "open": 0.0, "carried_adverse": 0.0} for key in [*magics, None]}
    positions_by = {key: set() for key in magics}
    rows = []
    for deal in deals:
        at, kind, magic = _clock(_get(deal, "time")), _integer(_get(deal, "type")), _integer(_get(deal, "magic"))
        if at is None or kind is None or magic is None:
            return _blocked(DATA_INVALID, **base)
        if at > clock_now:
            return _blocked(CLOCK_AHEAD, **base)
        if at < day_start or kind not in (DEAL_TYPE_BUY, DEAL_TYPE_SELL):
            continue
        parts = [_number(_get(deal, k) or 0) for k in ("profit", "swap", "commission", "fee")]
        entry, position_id = _integer(_get(deal, "entry")), _integer(_get(deal, "position_id"))
        if any(p is None for p in parts) or entry is None or position_id is None:
            return _blocked(DATA_INVALID, **base)
        rows.append((magic, entry, position_id, sum(parts)))
    opened_today = {position_id for _, entry, position_id, _ in rows if entry == DEAL_ENTRY_IN}

    def book(magic: int, pnl: float, *, carried: bool, field_: str) -> None:
        keys = [None] + [key for key, scope_magic in magics.items() if magic == scope_magic]
        for key in keys:
            if carried:
                books[key]["carried_adverse"] += min(0.0, pnl)
            else:
                books[key][field_] += pnl

    for magic, entry, position_id, pnl in rows:
        # A closing deal of a position with no entry-IN deal today was opened before the day start
        # (or cannot be shown to be today's): carried, adverse movement only.
        book(magic, pnl, carried=entry != DEAL_ENTRY_IN and position_id not in opened_today, field_="realized")
        if entry == DEAL_ENTRY_IN:
            for key, scope_magic in magics.items():
                if magic == scope_magic:
                    positions_by[key].add(position_id)
    open_positions = []
    for position in positions:
        symbol, magic = _get(position, "symbol"), _integer(_get(position, "magic"))
        profit, swap = _number(_get(position, "profit")), _number(_get(position, "swap") or 0)
        opened = _clock(_get(position, "time"))
        if not isinstance(symbol, str) or not symbol.strip() or magic is None or None in (profit, swap) or opened is None:
            return _blocked(DATA_INVALID, **base)
        if opened > clock_now:
            return _blocked(CLOCK_AHEAD, **base)
        book(magic, profit + swap, carried=opened < day_start, field_="open")
        open_positions.append(OpenPosition(symbol=symbol, magic_number=magic))
    trades_by = {key: len(ids) for key, ids in positions_by.items()}

    account_metrics = {**_metrics(books[None], equity), "equity": equity,
                       "open_positions": len(open_positions)}
    per_scope = {}
    for scope in scopes:
        key = scope_key(scope)
        metrics = _metrics(books[key], equity, trades_by[key])
        per_scope[key] = {**metrics, "magic_number": scope.magic_number, "snapshot": RiskSnapshot(
            observed_at_utc=now, server_day=day, demo_equity=equity,
            strategy_daily_loss_pct=metrics["daily_loss_pct"],
            account_daily_loss_pct=account_metrics["daily_loss_pct"],
            strategy_trades_today=trades_by[key], open_positions=tuple(open_positions),
            positions_complete=True, daily_metrics_complete=True,
            symbol_meta=(symbol_meta or {}).get(key), daily_reset_basis=scope.daily_reset_basis)}
    return RiskSnapshotBuild(OK, None, account=account_metrics, scopes=per_scope, **base)
