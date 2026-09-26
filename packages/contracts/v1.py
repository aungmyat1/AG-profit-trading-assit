"""Version 1 immutable contracts. Standard-library only; no runtime or broker access."""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime, timezone
import hashlib
import json
import math
import re
from types import MappingProxyType
from typing import Any, ClassVar, Mapping


SCHEMA_VERSION = "1.0"
_PROVENANCE_FIELDS = {"event_id", "created_at", "source", "correlation_id"}
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,199}$")


class ContractError(ValueError):
    """Malformed, unsupported, or internally inconsistent contract data."""


def _freeze(value: Any, path: str = "data") -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContractError(f"{path} must contain only finite numbers")
        return value
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise ContractError(f"{path} keys must be strings")
        return MappingProxyType({key: _freeze(item, f"{path}.{key}") for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item, f"{path}[{index}]") for index, item in enumerate(value))
    raise ContractError(f"{path} contains unsupported value type {type(value).__name__}")


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


def _freeze_mapping(value: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    frozen = _freeze(value, name)
    if not isinstance(frozen, Mapping):
        raise ContractError(f"{name} must be an object")
    return frozen


def _timestamp(value: str | datetime) -> str:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
        except ValueError as exc:
            raise ContractError("created_at must be an ISO-8601 timestamp with timezone") from exc
    else:
        raise ContractError("created_at must be an ISO-8601 string or aware datetime")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractError("created_at must include an explicit timezone")
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _identifier(name: str, value: str) -> None:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise ContractError(f"{name} must be a non-empty stable identifier")


@dataclass(frozen=True, kw_only=True)
class Contract:
    """Shared immutable provenance. AccountState and SemanticError may omit symbol."""

    schema_version: str
    event_id: str
    created_at: str | datetime
    source: str
    correlation_id: str
    symbol: str | None = None

    KIND: ClassVar[str] = "Contract"

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ContractError(f"unsupported schema_version {self.schema_version!r}; expected {SCHEMA_VERSION}")
        _identifier("event_id", self.event_id)
        _identifier("source", self.source)
        _identifier("correlation_id", self.correlation_id)
        if self.symbol is not None:
            if not isinstance(self.symbol, str) or not self.symbol.strip():
                raise ContractError("symbol must be a non-empty string when provided")
            object.__setattr__(self, "symbol", self.symbol.strip().upper())
        object.__setattr__(self, "created_at", _timestamp(self.created_at))

    def semantic_fields(self) -> dict[str, Any]:
        return {
            field.name: _plain(getattr(self, field.name))
            for field in fields(self)
            if field.name not in _PROVENANCE_FIELDS
        }

    @property
    def semantic_hash(self) -> str:
        canonical = json.dumps(
            {"kind": self.KIND, "schema_version": self.schema_version, "semantic": self.semantic_fields()},
            sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = {
            field.name: (_plain(getattr(self, field.name)) if field.name != "created_at" else self.created_at)
            for field in fields(self)
        }
        result["semantic_hash"] = self.semantic_hash
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> Contract:
        if not isinstance(raw, Mapping):
            raise ContractError("contract input must be an object")
        if raw.get("schema_version") != SCHEMA_VERSION:
            raise ContractError(f"unsupported schema_version {raw.get('schema_version')!r}; expected {SCHEMA_VERSION}")
        known = {field.name for field in fields(cls)}
        unknown = set(raw) - known - {"semantic_hash"}
        missing = known - set(raw)
        if unknown:
            raise ContractError(f"unknown {cls.__name__} fields: {', '.join(sorted(unknown))}")
        if missing:
            raise ContractError(f"missing {cls.__name__} fields: {', '.join(sorted(missing))}")
        values = dict(raw)
        supplied_hash = values.pop("semantic_hash", None)
        instance = cls(**values)
        if supplied_hash is not None and supplied_hash != instance.semantic_hash:
            raise ContractError("semantic_hash does not match canonical semantic content")
        return instance


@dataclass(frozen=True, kw_only=True)
class MarketState(Contract):
    facts: Mapping[str, Any]
    KIND: ClassVar[str] = "MarketState"
    _FORBIDDEN_FACT_KEYS: ClassVar[set[str]] = {
        "action", "approved_volume", "broker_command", "command", "decision",
        "direction", "execution_command", "owner_approval", "risk_approval",
        "side", "signal", "trade_action", "volume",
    }

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.symbol is None:
            raise ContractError("MarketState requires symbol")
        frozen = _freeze(self.facts, "facts")
        if not isinstance(frozen, Mapping):
            raise ContractError("facts must be an object")
        fact_symbol = frozen.get("symbol")
        if fact_symbol is not None and (not isinstance(fact_symbol, str) or fact_symbol.strip().upper() != self.symbol):
            raise ContractError("MarketState facts symbol does not match contract symbol")
        fact_source = frozen.get("source")
        if fact_source is not None and fact_source != self.source:
            raise ContractError("MarketState facts source does not match contract source")
        forbidden = _keys_recursively(frozen).intersection(self._FORBIDDEN_FACT_KEYS)
        if forbidden:
            raise ContractError(f"MarketState facts cannot encode authority fields: {', '.join(sorted(forbidden))}")
        object.__setattr__(self, "facts", frozen)


@dataclass(frozen=True, kw_only=True)
class Opportunity(Contract):
    opportunity_id: str
    strategy_id: str
    strategy_version: str
    details: Mapping[str, Any]
    KIND: ClassVar[str] = "Opportunity"

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.symbol is None:
            raise ContractError("Opportunity requires symbol")
        for name in ("opportunity_id", "strategy_id", "strategy_version"):
            _identifier(name, getattr(self, name))
        object.__setattr__(self, "details", _freeze_mapping(self.details, "details"))


@dataclass(frozen=True, kw_only=True)
class ProposalEligibilityDecision(Contract):
    opportunity_id: str
    eligible: bool
    reason_codes: tuple[str, ...]
    details: Mapping[str, Any]
    KIND: ClassVar[str] = "ProposalEligibilityDecision"

    def __post_init__(self) -> None:
        super().__post_init__()
        _identifier("opportunity_id", self.opportunity_id)
        if not isinstance(self.eligible, bool):
            raise ContractError("eligible must be boolean")
        _reason_codes(self.reason_codes)
        object.__setattr__(self, "reason_codes", tuple(self.reason_codes))
        object.__setattr__(self, "details", _freeze_mapping(self.details, "details"))
        if not self.eligible and not self.reason_codes:
            raise ContractError("rejected eligibility decision requires explicit reason_codes")


@dataclass(frozen=True, kw_only=True)
class Proposal(Contract):
    opportunity_id: str
    strategy_id: str
    strategy_version: str
    details: Mapping[str, Any]
    KIND: ClassVar[str] = "Proposal"

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.symbol is None:
            raise ContractError("Proposal requires symbol")
        for name in ("opportunity_id", "strategy_id", "strategy_version"):
            _identifier(name, getattr(self, name))
        object.__setattr__(self, "details", _freeze_mapping(self.details, "details"))


@dataclass(frozen=True, kw_only=True)
class OwnerDecision(Contract):
    proposal_id: str
    action: str
    owner_id: str
    reason_codes: tuple[str, ...]
    KIND: ClassVar[str] = "OwnerDecision"

    def __post_init__(self) -> None:
        super().__post_init__()
        _identifier("proposal_id", self.proposal_id)
        _identifier("owner_id", self.owner_id)
        if self.action not in {"APPROVE_DEMO", "REJECT"}:
            raise ContractError("action must be APPROVE_DEMO or REJECT")
        _reason_codes(self.reason_codes)
        object.__setattr__(self, "reason_codes", tuple(self.reason_codes))


@dataclass(frozen=True, kw_only=True)
class ExecutionRequest(Contract):
    proposal_id: str
    owner_decision_id: str
    account_id: str
    mode: str
    idempotency_key: str
    request: Mapping[str, Any]
    KIND: ClassVar[str] = "ExecutionRequest"

    def __post_init__(self) -> None:
        super().__post_init__()
        for name in ("proposal_id", "owner_decision_id", "account_id", "idempotency_key"):
            _identifier(name, getattr(self, name))
        if self.mode not in {"DEMO", "LIVE"}:
            raise ContractError("mode must be DEMO or LIVE")
        object.__setattr__(self, "request", _freeze_mapping(self.request, "request"))


@dataclass(frozen=True, kw_only=True)
class ExecutionResult(Contract):
    request_id: str
    status: str
    reason_codes: tuple[str, ...]
    result: Mapping[str, Any]
    KIND: ClassVar[str] = "ExecutionResult"

    def __post_init__(self) -> None:
        super().__post_init__()
        _identifier("request_id", self.request_id)
        if self.status not in {"ACCEPTED", "REJECTED", "SUBMITTED", "FILLED", "FAILED", "UNKNOWN"}:
            raise ContractError("unsupported ExecutionResult status")
        _reason_codes(self.reason_codes)
        object.__setattr__(self, "reason_codes", tuple(self.reason_codes))
        object.__setattr__(self, "result", _freeze_mapping(self.result, "result"))
        if self.status in {"REJECTED", "FAILED", "UNKNOWN"} and not self.reason_codes:
            raise ContractError("non-success ExecutionResult requires explicit reason_codes")


@dataclass(frozen=True, kw_only=True)
class AccountState(Contract):
    account_id: str
    broker: str
    currency: str
    state: Mapping[str, Any]
    KIND: ClassVar[str] = "AccountState"

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.symbol is not None:
            raise ContractError("AccountState is account-scoped and must omit symbol")
        for name in ("account_id", "broker", "currency"):
            _identifier(name, getattr(self, name))
        object.__setattr__(self, "state", _freeze_mapping(self.state, "state"))


@dataclass(frozen=True, kw_only=True)
class SemanticError(Contract):
    """Versioned fail-closed outcome; carries explicit reason codes and no authority."""

    code: str
    message: str
    reason_codes: tuple[str, ...]
    details: Mapping[str, Any]
    KIND: ClassVar[str] = "SemanticError"

    def __post_init__(self) -> None:
        super().__post_init__()
        _identifier("code", self.code)
        if not isinstance(self.message, str) or not self.message.strip():
            raise ContractError("message must be non-empty")
        _reason_codes(self.reason_codes)
        object.__setattr__(self, "reason_codes", tuple(self.reason_codes))
        if not self.reason_codes:
            raise ContractError("SemanticError requires explicit reason_codes")
        object.__setattr__(self, "details", _freeze_mapping(self.details, "details"))


def _reason_codes(codes: tuple[str, ...]) -> None:
    if not isinstance(codes, (tuple, list)) or any(not isinstance(code, str) or not code.strip() for code in codes):
        raise ContractError("reason_codes must be a sequence of non-empty strings")
    if len(set(codes)) != len(codes):
        raise ContractError("reason_codes must be unique")


def _keys_recursively(value: Any) -> set[str]:
    if isinstance(value, Mapping):
        return {key.lower() for key in value}.union(*(_keys_recursively(item) for item in value.values()))
    if isinstance(value, tuple):
        return set().union(*(_keys_recursively(item) for item in value))
    return set()
