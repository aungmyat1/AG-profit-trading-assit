"""Read-only per-scope verification status for Telegram status reporting (OD1012-ROUTING).

Reports, for every relevant strategy family x pair x session scope, the scope's current
`verification_status` and its `execution_route`. This module never grants anything: the route
is always REPORT_ONLY here, and every value comes from strategies/registry.yaml plus the
existing identity checks (authority.logic_identity, ready_authority.logic_scope_verified,
ready_authority.ready_authority). Missing, unknown or malformed inputs fail closed to
UNVERIFIED / REGISTRY_ENTRY_MISSING; nothing here raises into a runner.

The family -> pair map mirrors docs/schemas/ticket_verification_routing.yaml in PR #177
(SPEC ONLY, owner-stated 2026-10-12); it is pinned here as constants, never read from the spec.
AUDUSD is outside the target universe and is not a reported scope.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple

SESSION_FX_GOLD, CRYPTO_CFD, LARGE_SMC = "session_fx_gold", "crypto_cfd", "large_smc"
CRYPTO_DAY, CRYPTO_WEEKEND = "CRYPTO_DAY", "CRYPTO_WEEKEND"
WATCH = "WATCH"

FAMILIES: Dict[str, Dict[str, Any]] = {
    # strategy_version = the version each family's status is read for (ASW: the scoped runtime
    # candidate fx.SCOPED_CANDIDATE_PATH; CCFD: its registered candidate; LSMC: registry version).
    SESSION_FX_GOLD: {"strategy_id": "ST_ASIAN_SWEEP_5R_V1", "strategy_version": "1.1.2",
                      "pairs": ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD"),
                      "sessions": ("ASIAN_LONDON", "LONDON_NEWYORK")},
    CRYPTO_CFD: {"strategy_id": "ST_CRYPTO_CFD_SWEEP_RETEST_V1", "strategy_version": "1.0.0",
                 "pairs": ("BTCUSD", "ETHUSD"), "sessions": (CRYPTO_DAY, CRYPTO_WEEKEND)},
    LARGE_SMC: {"strategy_id": "ST_LARGE_SMC_V1", "strategy_version": "1.1.0",
                "pairs": ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD", "ETHUSD"),
                "sessions": (WATCH,)},
}
EXCLUDED_FROM_REPORTING = ("AUDUSD",)

UNVERIFIED, IN_VERIFICATION, LOGIC_VERIFIED = "UNVERIFIED", "IN_VERIFICATION", "LOGIC_VERIFIED"
STALE_IDENTITY, SUSPENDED = "STALE_IDENTITY", "SUSPENDED"
REPORT_ONLY = "REPORT_ONLY"          # the only route this module can produce
REPORT_ONLY_HEADER = "REPORT ONLY — NON-ACTIONABLE"

REGISTRY_ENTRY_MISSING = "REGISTRY_ENTRY_MISSING"
LOGIC_NOT_VERIFIED = "LOGIC_NOT_VERIFIED"
ENTRY_LOGIC_NOT_VERIFIED = "ENTRY_LOGIC_NOT_VERIFIED"
DEMO_AUTHORIZATION_ABSENT = "DEMO_AUTHORIZATION_ABSENT"

# The only ASW branch with recorded VT verification evidence (OD1011-SCOPE); others fail closed.
_ASW_SETUP, _ASW_BRANCH = "SWEEP", "RANGE_SWEEP"


@dataclass(frozen=True)
class ScopeStatus:
    family: str
    strategy_id: str
    strategy_version: str
    symbol: str
    session: str
    verification_status: str
    route: str
    route_reason: str
    detail: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _candidate(entry: Dict[str, Any], version: str) -> Dict[str, Any]:
    candidate = (entry.get("candidate_versions") or {}).get(version)
    if not isinstance(candidate, dict):
        raise KeyError("candidate_version")
    return candidate


def _verified_route_reason(strategy_id: str, entry: Dict[str, Any], version: str, symbol: str,
                           session: str) -> str:
    """Why a verified scope still routes REPORT_ONLY: READY authority first, then demo authority."""
    import hashlib
    from pathlib import Path

    from v1_tickets.ready_authority import ready_authority

    source = _candidate(entry, version).get("config_source")
    try:
        root = Path(__file__).resolve().parents[2]
        raw_hash = hashlib.sha256((root / source).read_bytes()).hexdigest()
    except (OSError, TypeError):
        return "OWNER_DECISION_RECORD_MISSING"
    ready_on, reason = ready_authority(strategy_id, strategy_version=version,
                                       contract_sha256=raw_hash, symbol=symbol, session=session)
    if not ready_on:
        return reason
    return DEMO_AUTHORIZATION_ABSENT if entry.get("demo_authorized") is not True else REGISTRY_ENTRY_MISSING


def _asw(entry: Dict[str, Any], strategy_id: str, version: str, symbol: str,
         session: str) -> Tuple[str, str, str]:
    from v1_tickets.ready_authority import logic_scope_verified
    candidate = _candidate(entry, version)
    for item in candidate.get("logic_suspended_scopes") or []:
        if isinstance(item, dict) and item.get("symbol") == symbol and item.get("session", session) == session:
            return SUSPENDED, str(item.get("reason") or "SUSPENDED"), str(item.get("evidence") or "")
    if logic_scope_verified(strategy_id, version, symbol, cycle=session, setup=_ASW_SETUP, branch=_ASW_BRANCH):
        return LOGIC_VERIFIED, _verified_route_reason(strategy_id, entry, version, symbol, session), f"branch={_ASW_BRANCH}"
    listed = [item for item in candidate.get("logic_verified_scopes") or []
              if isinstance(item, dict) and item.get("symbol") == symbol and item.get("session") == session]
    if listed:   # recorded for this scope, but the current contract/engine identity no longer matches
        return STALE_IDENTITY, STALE_IDENTITY, f"branch={listed[0].get('branch')}"
    return UNVERIFIED, LOGIC_NOT_VERIFIED, ""


def _ccfd(entry: Dict[str, Any], strategy_id: str, version: str, symbol: str, session: str) -> Tuple[str, str, str]:
    from v1_tickets.authority import logic_identity
    candidate = _candidate(entry, version)
    listed = [item for item in candidate.get("logic_verified_symbols") or []
              if isinstance(item, dict) and item.get("symbol") == symbol]
    if not listed:
        return UNVERIFIED, LOGIC_NOT_VERIFIED, ""
    branches = ",".join(str(b) for b in listed[0].get("branches") or []) or "NONE"
    status = candidate.get("logic_status")
    identity = logic_identity(strategy_id, version)
    if (status == LOGIC_VERIFIED and identity is not None
            and candidate.get("logic_verified_identity") == identity["digest"]
            and listed[0].get("logic_identity") == identity["digest"]):
        return LOGIC_VERIFIED, _verified_route_reason(strategy_id, entry, version, symbol, session), f"branches={branches}"
    if status in (LOGIC_VERIFIED, STALE_IDENTITY):
        return STALE_IDENTITY, STALE_IDENTITY, f"branches={branches}"
    return UNVERIFIED, LOGIC_NOT_VERIFIED, ""


def _lsmc(entry: Dict[str, Any], symbol: str) -> Tuple[str, str, str]:
    """Detection verification is not entry verification: entry stays UNVERIFIED."""
    detection = entry.get("detection_logic_verification") or {}
    identity = str(detection.get("identity") or "")
    parts = identity.split("/")
    detected = (detection.get("status") == LOGIC_VERIFIED and len(parts) >= 3 and parts[1] == symbol
                and parts[2] == "DETECTION_ONLY")
    return UNVERIFIED, ENTRY_LOGIC_NOT_VERIFIED, f"detection={LOGIC_VERIFIED if detected else 'NOT_VERIFIED'}"


def scope_status(family: str, symbol: str, session: str, *,
                 registry: Optional[Dict[str, Any]] = None) -> ScopeStatus:
    """Fail-closed status for one scope. Unknown family/pair/session raises ValueError (caller bug);
    every registry/identity problem returns UNVERIFIED / REGISTRY_ENTRY_MISSING instead."""
    spec = FAMILIES.get(family)
    if spec is None or symbol not in spec["pairs"] or session not in spec["sessions"]:
        raise ValueError(f"unknown scope {family}/{symbol}/{session}")
    strategy_id, version = spec["strategy_id"], spec["strategy_version"]
    try:
        if registry is None:
            from v1_tickets.authority import load_registry
            registry = load_registry()
        entry = registry.get(strategy_id)
        if not isinstance(entry, dict) or entry.get("registered") is not True:
            raise KeyError(strategy_id)
        if family == SESSION_FX_GOLD:
            status, reason, detail = _asw(entry, strategy_id, version, symbol, session)
        elif family == CRYPTO_CFD:
            status, reason, detail = _ccfd(entry, strategy_id, version, symbol, session)
        else:
            status, reason, detail = _lsmc(entry, symbol)
    except Exception:  # noqa: BLE001 -- status display fails closed, never raises into a runner
        status, reason, detail = UNVERIFIED, REGISTRY_ENTRY_MISSING, ""
    return ScopeStatus(family, strategy_id, version, symbol, session, status, REPORT_ONLY,
                       reason or REGISTRY_ENTRY_MISSING, detail)


def family_statuses(family: str, session: str, *,
                    registry: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """One status dict per pair of `family` for `session`, in the pinned pair order."""
    if registry is None:
        try:
            from v1_tickets.authority import load_registry
            registry = load_registry()
        except Exception:  # noqa: BLE001 -- every scope then reports REGISTRY_ENTRY_MISSING
            registry = {}
    return [scope_status(family, symbol, session, registry=registry).as_dict()
            for symbol in FAMILIES[family]["pairs"]]
