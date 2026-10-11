"""Load the repository-owned S1 scope without turning it into execution authority.

The logic identity, candidate contract, magic number, spread limits and broker
symbol are all resolved from the current registry/contracts/maps. No strategy
identity or broker symbol is duplicated as a runtime literal here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

import yaml

from mt5.canonical_broker_map import SymbolMapError, load_map

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCOPE_CONFIG = _REPO_ROOT / "config" / "demo_execution_s1.yaml"
_IDENTITY_RE = re.compile(r"^[0-9a-f]{64}$")


class ScopePolicyError(ValueError):
    """Invalid or unavailable admission scope; `reason_code` is safe to surface."""

    def __init__(self, reason_code: str, detail: str = "") -> None:
        super().__init__(f"{reason_code}{': ' + detail if detail else ''}")
        self.reason_code = reason_code


@dataclass(frozen=True)
class ScopePolicy:
    enabled: bool
    strategy_id: str
    strategy_version: str
    symbol: str
    broker_symbol: str
    session: str
    setup_branch: str
    directions: tuple[str, ...]
    logic_identity: str
    magic_number: int
    pip_size: float
    point_size: float
    max_spread_allowed_pips: float
    max_spread_fraction_of_stop: float
    slippage_limit_points: float
    signal_expiry_minutes: float
    daily_reset_basis: str
    daily_reset_owner_confirm: bool
    notification_failure_policy: str
    authorization_path_env: str
    evidence_pull_request: int
    registry_path: Path
    contract_path: Path
    broker_symbol_map_path: Path
    ready_authority_config_path: Path
    owner_decision_register_path: Path
    per_order_confirm_required: bool = True


def _as_path(value: str | Path, root: Path) -> Path:
    path = Path(value).expanduser()
    return (path if path.is_absolute() else root / path).resolve()


def _load_yaml(path: Path, reason: str) -> Mapping[str, Any]:
    try:
        with path.open(encoding="utf-8") as stream:
            raw = yaml.safe_load(stream)
    except (OSError, yaml.YAMLError) as exc:
        raise ScopePolicyError(reason, str(exc)) from None
    if not isinstance(raw, dict):
        raise ScopePolicyError(reason, "expected a YAML mapping")
    return raw


def _finite_positive(raw: Any, field: str) -> float:
    if isinstance(raw, bool):
        raise ScopePolicyError("EXECUTION_SCOPE_INVALID", f"{field} must be positive and finite")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ScopePolicyError("EXECUTION_SCOPE_INVALID", f"{field} must be positive and finite") from None
    if not (value > 0 and value < float("inf")):
        raise ScopePolicyError("EXECUTION_SCOPE_INVALID", f"{field} must be positive and finite")
    return value


def _under_root(path: Path, root: Path, field: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        raise ScopePolicyError("EXECUTION_SCOPE_INVALID", f"{field} must stay inside the repository") from None
    return resolved


def _selected_path(config_value: str, root: Path, field: str,
                   override: Optional[str | Path]) -> Path:
    # Explicit absolute paths are used only for isolated tests/host injection. Committed
    # production paths remain repo-relative and are constrained beneath the repository.
    if override is not None:
        return Path(override).expanduser().resolve()
    return _under_root(_as_path(config_value, root), root, field)


def load_scope_policy(
    config_path: Optional[str | Path] = None,
    *,
    repo_root: Optional[str | Path] = None,
    registry_path: Optional[str | Path] = None,
    broker_symbol_map_path: Optional[str | Path] = None,
    ready_authority_config_path: Optional[str | Path] = None,
    owner_decision_register_path: Optional[str | Path] = None,
) -> ScopePolicy:
    """Resolve the narrow S1 scope and fail closed on missing or inconsistent inputs.

    Path overrides are dependency-injection seams for isolated tests and future host
    integration; production defaults come only from the committed scope YAML.
    """
    root = Path(repo_root).resolve() if repo_root is not None else _REPO_ROOT
    cfg_path = _as_path(config_path or _SCOPE_CONFIG, root)
    raw = _load_yaml(cfg_path, "EXECUTION_SCOPE_UNREADABLE")
    if raw.get("schema") != "AGP_C14_DEMO_SCOPE_V1" or type(raw.get("enabled")) is not bool:
        raise ScopePolicyError("EXECUTION_SCOPE_INVALID", "schema/enabled missing or malformed")
    confirm_required_value = raw.get("per_order_confirm_required", True)
    per_order_confirm_required = (
        confirm_required_value if type(confirm_required_value) is bool else True
    )
    scope = raw.get("scope")
    if not isinstance(scope, dict):
        raise ScopePolicyError("EXECUTION_SCOPE_INVALID", "scope mapping missing")

    required = (
        "strategy_id", "strategy_version", "symbol", "session", "setup_branch", "directions",
        "registry_path", "broker_symbol_map_path", "ready_authority_config_path",
        "owner_decision_register_path", "authorization_path_env", "daily_reset_basis",
        "daily_reset_owner_confirm", "notification_failure_policy", "evidence_pull_request",
    )
    if any(scope.get(key) in (None, "") for key in required):
        raise ScopePolicyError("EXECUTION_SCOPE_INVALID", "one or more scope fields are missing")
    strategy_id = scope["strategy_id"]
    version = str(scope["strategy_version"])
    symbol = scope["symbol"]
    session = scope["session"]
    branch = scope["setup_branch"]
    directions = scope["directions"]
    if (not all(isinstance(x, str) and x.strip() for x in (strategy_id, version, symbol, session, branch))
            or not isinstance(directions, list)
            or not directions
            or any(x not in ("LONG", "SHORT") for x in directions)
            or len(set(directions)) != len(directions)):
        raise ScopePolicyError("EXECUTION_SCOPE_INVALID", "scope identifiers/directions are malformed")

    registry_file = _selected_path(scope["registry_path"], root, "registry_path", registry_path)
    registry = _load_yaml(registry_file, "STRATEGY_REGISTRY_UNREADABLE")
    registry_strategies = registry.get("strategies")
    strategy = registry_strategies.get(strategy_id) if isinstance(registry_strategies, dict) else None
    candidate_versions = strategy.get("candidate_versions") if isinstance(strategy, dict) else None
    candidate = candidate_versions.get(version) if isinstance(candidate_versions, dict) else None
    if not isinstance(candidate, dict):
        raise ScopePolicyError("STRATEGY_VERSION_NOT_REGISTERED", f"{strategy_id}@{version}")
    identity = candidate.get("logic_verified_identity")
    if candidate.get("logic_status") != "LOGIC_VERIFIED" or not isinstance(identity, str) \
            or not _IDENTITY_RE.fullmatch(identity):
        raise ScopePolicyError("LOGIC_IDENTITY_UNAVAILABLE", "candidate identity is not LOGIC_VERIFIED")
    contract_source = candidate.get("config_source")
    if not isinstance(contract_source, str) or not contract_source:
        raise ScopePolicyError("STRATEGY_CONTRACT_UNAVAILABLE")
    contract_file = _under_root(_as_path(contract_source, root), root, "strategy config_source")
    contract = _load_yaml(contract_file, "STRATEGY_CONTRACT_UNREADABLE")
    if str(contract.get("version")) != version:
        raise ScopePolicyError("STRATEGY_CONTRACT_VERSION_MISMATCH")
    magic_number = contract.get("magic_number")
    if isinstance(magic_number, bool) or not isinstance(magic_number, int) or magic_number <= 0:
        raise ScopePolicyError("STRATEGY_MAGIC_NUMBER_UNAVAILABLE")
    cost = contract.get("risk_and_money_management")
    if not isinstance(cost, dict):
        raise ScopePolicyError("STRATEGY_COST_POLICY_UNAVAILABLE")
    max_spread_pips = _finite_positive(cost.get("max_spread_allowed_pips"), "max_spread_allowed_pips")
    max_spread_fraction = _finite_positive(cost.get("max_spread_fraction_of_stop"),
                                           "max_spread_fraction_of_stop")
    slippage_points = _finite_positive(cost.get("slippage_limit_points"), "slippage_limit_points")
    expiry_minutes = _finite_positive(cost.get("signal_expiry_minutes"), "signal_expiry_minutes")

    map_file = _selected_path(scope["broker_symbol_map_path"], root, "broker_symbol_map_path",
                              broker_symbol_map_path)
    try:
        symbol_map = load_map(str(map_file))
        broker_symbol = symbol_map.resolve(symbol)
    except (OSError, SymbolMapError, ValueError, yaml.YAMLError) as exc:
        raise ScopePolicyError("BROKER_SYMBOL_MAP_UNAVAILABLE", str(exc)) from None
    if symbol_map.broker != "VT_MARKETS" or "demo" not in symbol_map.server.lower():
        raise ScopePolicyError("BROKER_SYMBOL_MAP_NOT_DEMO")
    map_entry = symbol_map.entries[symbol]
    expected = map_entry.expected
    try:
        digits = int(expected["digits"])
        point_size = _finite_positive(expected["point"], "symbol point")
    except (KeyError, TypeError, ValueError):
        raise ScopePolicyError("BROKER_SYMBOL_METADATA_UNAVAILABLE") from None
    if digits not in (2, 3, 4, 5):
        raise ScopePolicyError("BROKER_SYMBOL_METADATA_UNAVAILABLE", "unsupported FX precision")
    # The mapped GBPUSD host capture pins five digits and a 1e-5 point; standard
    # three/five-digit FX quotes use ten points per pip, otherwise one.
    pip_size = point_size * (10.0 if digits in (3, 5) else 1.0)

    ready_file = _selected_path(scope["ready_authority_config_path"], root,
                                "ready_authority_config_path", ready_authority_config_path)
    owner_file = _selected_path(scope["owner_decision_register_path"], root,
                                "owner_decision_register_path", owner_decision_register_path)

    if scope["daily_reset_basis"] != "VT_SERVER_DAY" or scope["daily_reset_owner_confirm"] is not True:
        raise ScopePolicyError("DAILY_RESET_POLICY_UNCONFIRMED")
    if scope["notification_failure_policy"] != "PENDING_OWNER":
        raise ScopePolicyError("NOTIFICATION_FAILURE_POLICY_UNSUPPORTED")
    auth_env = scope["authorization_path_env"]
    if not isinstance(auth_env, str) or not auth_env.isidentifier():
        raise ScopePolicyError("EXECUTION_SCOPE_INVALID", "authorization path environment key is invalid")
    evidence_pr = scope["evidence_pull_request"]
    if isinstance(evidence_pr, bool) or not isinstance(evidence_pr, int) or evidence_pr <= 0:
        raise ScopePolicyError("EXECUTION_SCOPE_INVALID", "evidence_pull_request must be a positive integer")

    return ScopePolicy(
        enabled=raw["enabled"],
        per_order_confirm_required=per_order_confirm_required,
        strategy_id=strategy_id,
        strategy_version=version,
        symbol=symbol,
        broker_symbol=broker_symbol,
        session=session,
        setup_branch=branch,
        directions=tuple(directions),
        logic_identity=identity,
        magic_number=magic_number,
        pip_size=pip_size,
        point_size=point_size,
        max_spread_allowed_pips=max_spread_pips,
        max_spread_fraction_of_stop=max_spread_fraction,
        slippage_limit_points=slippage_points,
        signal_expiry_minutes=expiry_minutes,
        daily_reset_basis=scope["daily_reset_basis"],
        daily_reset_owner_confirm=scope["daily_reset_owner_confirm"],
        notification_failure_policy=scope["notification_failure_policy"],
        authorization_path_env=auth_env,
        evidence_pull_request=evidence_pr,
        registry_path=registry_file,
        contract_path=contract_file,
        broker_symbol_map_path=map_file,
        ready_authority_config_path=ready_file,
        owner_decision_register_path=owner_file,
    )
