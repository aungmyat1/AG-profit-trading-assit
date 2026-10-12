"""Shared offline fixtures for the C14/S1 guarded execution-boundary tests.

Everything here is synthetic and broker-free: the scope is a tmp copy of the committed S1 scope
with a test-only identity-pinned registry row, the standing authorization is a tmp host-local
record, the live account read is a callable that returns the committed DEMO identity (login
suffix only, never a full login), and owner confirmations are ordinary TICKET_STORE_V1 outcome
rows in the shape the sanctioned confirmation writer produces. No MT5 module is imported here
and no order call site exists in this file.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

import yaml

from demo_execution.admission import MarketEvidence
from demo_execution.authority import (
    AccountIdentity,
    ExecutionAuthority,
    build_authority,
)
from demo_execution.guarded_adapter import GuardedCanonicalAdapter
from demo_execution.risk import RiskSnapshot
from demo_execution.scope import ScopePolicy, load_scope_policy
from mt5.symbol_resolver import SymbolMeta
from ticket_store.store import LIVE, TicketStore, build_outcome

REPO = Path(__file__).resolve().parents[1]
SCOPE_CONFIG = REPO / "config" / "demo_execution_s1.yaml"
BROKER_MAP = REPO / "config" / "broker_symbol_map" / "vt_markets_demo.yaml"
REGISTRY = REPO / "strategies" / "registry.yaml"
HOST_MAGIC_REGISTRY = REPO / "config" / "demo_execution_host_magics.yaml"

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)
# The committed DEMO account pin (config/demo_execution_s1.yaml account_login_suffix).
ACCOUNT = AccountIdentity(login_suffix="999", server="VTMarkets-Demo", trade_mode="DEMO")
DECISION_ID = "TEST_ONLY_NOT_OWNER_AUTHORITY"
CONFIRM_ID = "TEST-ONLY-CONFIRM-0001"
TICKET_ID = "AG-S1-TEST-20261011-GBPUSD-ASIAN_LONDON-001"

# Row kinds written by the sanctioned single-use confirmation path. Pinned here so these
# fixtures keep working whether or not that module is present in this checkout.
OWNER_CONFIRMATION_KIND = "DEMO_OWNER_ORDER_CONFIRM"
OWNER_CONFIRMATION_USED_KIND = "DEMO_OWNER_ORDER_CONFIRM_USED"


def _yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _write_yaml(path: Path, data: Any) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def new_authority_id() -> str:
    """One authority id per guarded call: the guard refuses a reused id."""
    return uuid.uuid4().hex


def fixture_scope(tmp_path: Path, *, enabled: bool = True, ready_on: bool = True,
                  host_magic_registry_path: Optional[Path] = None) -> ScopePolicy:
    """A tmp S1 scope with a test-only identity-pinned registry row (same shape as #142 enforces)."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    config = _yaml(SCOPE_CONFIG)
    config["enabled"] = enabled
    scope_path = tmp_path / "demo_execution_s1.yaml"
    _write_yaml(scope_path, config)

    registry = _yaml(REGISTRY)
    strategy = registry["strategies"]["ST_ASIAN_SWEEP_5R_V1"]
    candidate = strategy["candidate_versions"]["1.1.2"]
    from v1_tickets.authority import logic_identity
    identity = logic_identity("ST_ASIAN_SWEEP_5R_V1", "1.1.2")
    candidate["logic_verified_scopes"] = [{
        "scope_id": "S1", "symbol": "GBPUSD", "session": "ASIAN_LONDON", "branch": "RANGE_SWEEP",
        "engine_setup": "SWEEP", "status": "LOGIC_VERIFIED", "config_source": candidate["config_source"],
        "contract_hash": identity["contract_hash"], "engine_hash": identity["engine_identity"],
        "identity_hash": identity["digest"], "evidence": "TEST_ONLY_PR142_FIXTURE",
    }]
    registry_path = tmp_path / "registry.yaml"
    _write_yaml(registry_path, registry)

    contract_path = REPO / candidate["config_source"]
    contract_hash = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    ready_path = tmp_path / "ready_authority.yaml"
    _write_yaml(ready_path, {"strategies": {"ST_ASIAN_SWEEP_5R_V1": {"ready": "ON" if ready_on else "OFF"}}})
    owner_path = tmp_path / "OWNER_DECISION_REGISTER.md"
    if ready_on:
        owner_yaml = {"ready_authority_records": [{
            "decision_id": DECISION_ID, "strategy_id": "ST_ASIAN_SWEEP_5R_V1", "version": "1.1.2",
            "contract_sha256": contract_hash, "status": "APPROVED", "symbol_scope": ["GBPUSD"],
            "session_scope": ["ASIAN_LONDON"], "date": "2026-10-11",
        }]}
        owner_path.write_text(
            "<!-- READY_AUTHORITY_RECORDS_START -->\n```yaml\n"
            + yaml.safe_dump(owner_yaml, sort_keys=False)
            + "```\n<!-- READY_AUTHORITY_RECORDS_END -->\n", encoding="utf-8",
        )
    else:
        owner_path.write_text("No test READY record.\n", encoding="utf-8")

    return load_scope_policy(
        scope_path,
        repo_root=REPO,
        registry_path=registry_path,
        broker_symbol_map_path=BROKER_MAP,
        ready_authority_config_path=ready_path,
        owner_decision_register_path=owner_path,
        host_magic_registry_path=host_magic_registry_path or HOST_MAGIC_REGISTRY,
    )


def ticket(scope: ScopePolicy, now: datetime = NOW, **updates: Any) -> dict[str, Any]:
    """A READY S1 ticket with the creation/validity window the confirmation binding needs."""
    ticket: dict[str, Any] = {
        "ticket_id": TICKET_ID,
        "strategy_id": scope.strategy_id,
        "strategy_version": scope.strategy_version,
        "logic_identity": scope.logic_identity,
        "symbol": scope.symbol,
        "cycle": scope.session,
        "regime": "RANGE",
        "setup": scope.setup_branch,
        "branch": "SWEEP:TEST_ONLY",
        "direction": "LONG",
        "decision": "READY",
        "reason_code": "SIGNAL",
        "entry": 1.3001,
        "stop_loss": 1.2991,
        "risk_distance": 0.001,
        "spread_check": "PASS",
        "created_at": (now - timedelta(minutes=3)).isoformat(),
        "evaluated_at": (now - timedelta(minutes=2)).isoformat(),
        "signal_close_utc": (now - timedelta(minutes=2)).isoformat(),
        "valid_until": (now + timedelta(minutes=12)).isoformat(),
    }
    ticket.update(updates)
    return ticket


def authorization_file(tmp_path: Path, scope: ScopePolicy, ticket: Mapping[str, Any],
                       now: datetime = NOW, **updates: Any) -> Path:
    """A tmp host-local standing DEMO authorization record. Grants nothing by itself."""
    record = {
        "schema": "AGP_STANDING_DEMO_AUTHORIZATION_V1",
        "strategy": scope.strategy_id,
        "version": scope.strategy_version,
        "symbol": scope.symbol,
        "session": scope.session,
        "branch": scope.setup_branch,
        "direction": ticket["direction"],
        "logic_identity": scope.logic_identity,
        "granted_at": (now - timedelta(days=1)).isoformat(),
        "revoked_at": None,
        "decision_id": DECISION_ID,
        "emergency_stop": False,
    }
    record.update(updates)
    path = tmp_path / "host_local_auth.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def market(scope: ScopePolicy, now: datetime = NOW, **updates: Any) -> MarketEvidence:
    data: dict[str, Any] = {
        "broker_symbol": scope.broker_symbol,
        "bid": 1.3000,
        "ask": 1.3001,
        "observed_at_utc": now - timedelta(seconds=20),
        "data_close_utc": now - timedelta(minutes=1),
    }
    data.update(updates)
    return MarketEvidence(**data)


def risk_snapshot(scope: ScopePolicy, now: datetime = NOW, **updates: Any) -> RiskSnapshot:
    meta = SymbolMeta(
        symbol=scope.broker_symbol, tick_size=0.00001, tick_value=1.0, contract_size=100000.0,
        volume_min=0.01, volume_max=100.0, volume_step=0.01, digits=5, point=0.00001,
        metadata_source="EXCHANGE_VERIFIED",
    )
    data: dict[str, Any] = {
        "observed_at_utc": now - timedelta(seconds=30),
        "server_day": now.date(),
        "demo_equity": 10000.0,
        "strategy_daily_loss_pct": 0.0,
        "account_daily_loss_pct": 0.0,
        "strategy_trades_today": 0,
        "open_positions": [],
        "positions_complete": True,
        "daily_metrics_complete": True,
        "symbol_meta": meta,
        "daily_reset_basis": scope.daily_reset_basis,
    }
    data.update(updates)
    return RiskSnapshot(**data)


class LiveAccountRead:
    """Test double for the host's read-only account_info() read; counts every call it receives."""

    def __init__(self, payload: Optional[Mapping[str, Any]] = None, *, raises: bool = False) -> None:
        # A supplied payload is the whole read, never merged over the valid one: a case that omits
        # `login_suffix` must reach the guard as a read that omits `login_suffix`.
        self.payload: dict[str, Any] = dict(payload) if payload is not None else {
            "login_suffix": ACCOUNT.login_suffix, "server": ACCOUNT.server, "trade_mode": "DEMO",
        }
        self.raises = raises
        self.calls = 0

    def with_observed_at(self, value: Any) -> "LiveAccountRead":
        self.payload["observed_at_utc"] = value
        return self

    def __call__(self) -> Mapping[str, Any]:
        self.calls += 1
        if self.raises:
            raise RuntimeError("terminal unavailable")
        return dict(self.payload)


def append_confirmation(store: TicketStore, scope: ScopePolicy, ticket: Mapping[str, Any], *,
                        confirm_id: str = CONFIRM_ID, confirmed_at: datetime = NOW - timedelta(minutes=1),
                        consumed: bool = False, consumed_at: Optional[datetime] = None,
                        payload_updates: Optional[Mapping[str, Any]] = None,
                        kind: str = OWNER_CONFIRMATION_KIND) -> str:
    """Append a confirmation row in the sanctioned shape (identity + window + confirm_id)."""
    branch = ticket.get("setup")
    if branch is None:
        branch = str(ticket.get("branch") or "").split(":", 1)[0]
    creations = [ticket.get("created_at"), ticket.get("evaluated_at")]
    payload: dict[str, Any] = {
        "ticket_id": ticket["ticket_id"],
        "strategy_id": scope.strategy_id,
        "strategy_version": str(scope.strategy_version),
        "symbol": scope.symbol,
        "session": scope.session,
        "branch": branch,
        "direction": ticket["direction"],
        "ticket_branch": ticket.get("branch"),
        "ticket_setup": ticket.get("setup"),
        "ticket_created_at_utc": max(creations),
        "ticket_valid_until_utc": ticket.get("valid_until"),
        "confirm_id": confirm_id,
        "decision": "CONFIRM",
    }
    payload.update(dict(payload_updates or {}))
    store.append_outcome(build_outcome(
        ticket_id=ticket["ticket_id"], source=LIVE, outcome_kind=kind,
        recorded_at_utc=_iso(confirmed_at), result="CONFIRMED", payload=payload,
        provenance={"writer": "tests._demo_execution_boundary_fixtures.append_confirmation"},
    ))
    if consumed:
        mark_confirmation_consumed(store, ticket, confirm_id=confirm_id, confirmed_at=confirmed_at,
                                   consumed_at=consumed_at)
    return confirm_id


def mark_confirmation_consumed(store: TicketStore, ticket: Mapping[str, Any], *,
                               confirm_id: str = CONFIRM_ID,
                               confirmed_at: datetime = NOW - timedelta(minutes=1),
                               consumed_at: Optional[datetime] = None) -> None:
    """Append only the single-use consumption marker, in the sanctioned writer's shape."""
    store.append_outcome(build_outcome(
        ticket_id=ticket["ticket_id"], source=LIVE, outcome_kind=OWNER_CONFIRMATION_USED_KIND,
        recorded_at_utc=_iso(consumed_at or _as_dt(confirmed_at) + timedelta(seconds=1)),
        result="CONSUMED",
        payload={"confirm_id": confirm_id, "ticket_id": ticket["ticket_id"],
                 "confirmed_at_utc": _iso(confirmed_at)},
        provenance={"writer": "tests._demo_execution_boundary_fixtures.mark_confirmation_consumed"},
    ))


def _as_dt(value: Any) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))


def _iso(value: Any) -> str:
    if isinstance(value, str):
        return value
    return value.astimezone(timezone.utc).isoformat()


def boundary(tmp_path: Path, *, enabled: bool = True, ready_on: bool = True,
             account_read: Optional[LiveAccountRead] = None, now: datetime = NOW,
             confirm: bool = True, consumed: bool = False,
             ticket_updates: Optional[Mapping[str, Any]] = None,
             auth_updates: Optional[Mapping[str, Any]] = None,
             host_magic_registry_path: Optional[Path] = None) -> dict[str, Any]:
    """A complete, admitted, broker-free boundary fixture: scope + ticket + guard + authority."""
    scope = fixture_scope(tmp_path, enabled=enabled, ready_on=ready_on,
                          host_magic_registry_path=host_magic_registry_path)
    ready_ticket = ticket(scope, now, **(dict(ticket_updates or {})))
    auth_path = authorization_file(tmp_path, scope, ready_ticket, now, **(dict(auth_updates or {})))
    quote = market(scope, now)
    risk = risk_snapshot(scope, now)
    store = TicketStore(str(tmp_path / "ticket_store"))
    from _s1_notice_fixture import append_notice
    append_notice(store, ready_ticket, now)
    reader = account_read or LiveAccountRead()
    if confirm:
        append_confirmation(store, scope, ready_ticket, consumed=consumed)
    guard = GuardedCanonicalAdapter(
        ticket_store=store,
        live_account_reader=reader,
        scope_config_path=str(tmp_path / "demo_execution_s1.yaml"),
        repo_root=REPO,
        registry_path=str(tmp_path / "registry.yaml"),
        broker_symbol_map_path=BROKER_MAP,
        ready_authority_config_path=str(tmp_path / "ready_authority.yaml"),
        owner_decision_register_path=str(tmp_path / "OWNER_DECISION_REGISTER.md"),
        host_magic_registry_path=host_magic_registry_path or HOST_MAGIC_REGISTRY,
        authorization_path=str(auth_path),
    )
    authority = build_authority(
        ticket=ready_ticket, scope=scope, market=quote, risk_snapshot=risk, now_utc=now,
        authority_id=new_authority_id(), account=ACCOUNT, authorization_path=str(auth_path),
        authorization_decision_id=DECISION_ID,
        owner_confirmation_id=CONFIRM_ID if confirm else None,
    )
    return {
        "scope": scope, "ticket": ready_ticket, "auth_path": auth_path, "market": quote,
        "risk_snapshot": risk, "store": store, "reader": reader, "guard": guard,
        "authority": authority, "now": now, "tmp_path": tmp_path,
    }


def authority_for(fixture: Mapping[str, Any], *, now: Optional[datetime] = None,
                  authority_id: Optional[str] = None, **updates: Any) -> ExecutionAuthority:
    """A fresh single-use authority for the next guarded call, optionally mutated for a refusal test."""
    from dataclasses import replace

    authority = replace(fixture["authority"], authority_id=authority_id or new_authority_id(),
                        issued_at_utc=now or fixture["now"])
    return replace(authority, **updates) if updates else authority
