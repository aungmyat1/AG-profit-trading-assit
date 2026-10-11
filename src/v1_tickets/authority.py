"""Manual Trade Ticket V1 -- registry authority for manual tickets (Phase 1). Read-only.

Reads the explicit manual-ticket fields of strategies/registry.yaml and fails closed:
a missing, unknown or malformed value makes the strategy ticket-ineligible (zero
TICKET_READY). Only `ticket_authority: MANUAL_ONLY` with an in-repo adapter can emit
TICKET_READY, and that never means an order: `demo_order_authority` must be NONE.

`logic_identity` binds a LOGIC_VERIFIED claim to the exact strategy id/version, engine
source and contract bytes. If any of them changes, the stored claim no longer matches
and the effective logic status falls back to NOT_VERIFIED (never carried forward).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = "strategies/registry.yaml"

MANUAL_ONLY = "MANUAL_ONLY"
LOGIC_VERIFIED = "LOGIC_VERIFIED"
NOT_VERIFIED = "NOT_VERIFIED"
ALLOWED = {
    "ticket_authority": {MANUAL_ONLY, "NONE"},
    "logic_status": {NOT_VERIFIED, LOGIC_VERIFIED},
    "economic_status": {"NOT_EVALUATED"},
    "demo_order_authority": {"NONE"},      # this path never carries order authority
}

# Registry flags that must be present and exactly `false` on any ticket strategy (missing,
# true or any non-bool value fails closed). Read only; never written here.
NO_ORDER_FLAGS = ("demo_authorized", "live_authorized")
REASON_NOT_REGISTERED = "STRATEGY_NOT_REGISTERED"
REASON_AUTHORITY_INVALID = "REGISTRY_TICKET_AUTHORITY_INVALID"
REASON_NOT_MANUAL_ONLY = "TICKET_AUTHORITY_NOT_MANUAL_ONLY"
REASON_ADAPTER_NOT_IMPLEMENTED = "STRATEGY_ADAPTER_NOT_IMPLEMENTED"

# In-repo ticket adapters: strategy_id -> (contract path, engine source files). Only
# strategies whose engine lives in this repository can be logic-evaluated here.
_ENGINE_FILES = ("__init__.py", "engine.py", "loader.py", "models.py", "session/__init__.py",
                 "session/candles.py", "session/classifier.py", "session/reference_box.py",
                 "session/router.py", "session/setups.py")
ADAPTERS: Dict[str, Tuple[str, Tuple[str, ...]]] = {
    "ST_ASIAN_SWEEP_5R_V1": ("strategies/ST_ASIAN_SWEEP_5R_V1.yaml",
                             tuple(f"src/strategy_engine/{f}" for f in _ENGINE_FILES)),
    "ST_CRYPTO_CFD_SWEEP_RETEST_V1": (
        "strategies/ST_CRYPTO_CFD_SWEEP_RETEST_V1.yaml",
        ("src/crypto_cfd_contract/contract.py", "src/crypto_cfd_contract/rules.py",
         "src/v1_tickets/crypto_cfd.py", "src/v1_tickets/crypto_cfd_policy.py",
         "config/v1_tickets/crypto_cfd_ticket_policy.yaml", "src/v1_tickets/manual_ticket.py",
         "src/strategy_engine/sweep_retest/sweep.py", "src/strategy_engine/sweep_retest/mss.py",
         "src/strategy_engine/sweep_retest/retest.py", "src/strategy_engine/sweep_retest/targets.py")),
}


# Registered candidate versions whose contract lives in its own file (the frozen authority
# file above is never edited in place). Identity only: a candidate never changes which
# contract the runtime loads, so it cannot by itself make a ticket READY.
CANDIDATE_CONTRACTS: Dict[Tuple[str, str], str] = {
    ("ST_ASIAN_SWEEP_5R_V1", "1.1.2"): "strategies/ST_ASIAN_SWEEP_5R_V1_1_1_2.yaml",
}


def _sha256_text(paths, root: Path) -> str:
    """Line-ending-normalized so a Windows (CRLF) checkout hashes like a Linux one."""
    h = hashlib.sha256()
    for rel in paths:
        h.update(rel.encode() + b"\0" + (root / rel).read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()


def logic_identity(strategy_id: str, strategy_version: str, root: Path = REPO_ROOT) -> Optional[Dict[str, str]]:
    """None when no in-repo adapter exists (identity cannot be established)."""
    if strategy_id not in ADAPTERS:
        return None
    contract, engine_files = ADAPTERS[strategy_id]
    contract = CANDIDATE_CONTRACTS.get((strategy_id, strategy_version), contract)
    parts = {"strategy_id": strategy_id, "strategy_version": strategy_version,
             "engine_identity": _sha256_text(engine_files, root),
             "contract_hash": _sha256_text((contract,), root)}
    parts["digest"] = hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()
    return parts


@dataclass(frozen=True)
class TicketAuthority:
    strategy_id: str
    registry_visible: bool
    scanner_visible: bool
    logic_evaluable: bool
    ticket_eligible: bool
    reason: Optional[str]
    ticket_authority: Optional[str] = None
    logic_status: Optional[str] = None            # as stored in the registry
    logic_status_effective: str = NOT_VERIFIED    # after the identity check
    economic_status: Optional[str] = None
    demo_order_authority: Optional[str] = None
    logic_identity: Optional[Dict[str, str]] = None

    def as_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


def load_registry(root: Path = REPO_ROOT) -> Dict[str, Any]:
    data = yaml.safe_load((root / REGISTRY_PATH).read_text(encoding="utf-8"))
    return (data or {}).get("strategies") or {}


def registry_display_status(strategy_id: str, strategy_version: Optional[str], *,
                            registry: Optional[Dict[str, Any]] = None,
                            root: Path = REPO_ROOT) -> str:
    """Return a fail-closed output label based only on registry admission metadata."""
    try:
        entry = (registry if registry is not None else load_registry(root)).get(strategy_id)
    except Exception:  # noqa: BLE001 -- a broken/missing registry must suppress READY rendering
        return "RESEARCH"
    if not isinstance(entry, dict) or entry.get("registered") is not True:
        return "RESEARCH"
    status = str(entry.get("status", "")).upper()
    if "SHADOW" in status:
        return "SHADOW"
    if entry.get("research") is True or status in {"RESEARCH_ONLY", "RESEARCH_DRAFT", "ACTIVE_INCUBATION"}:
        return "RESEARCH"
    version = entry.get("version")
    if version is None and entry.get("config_source"):
        try:
            contract = yaml.safe_load((root / str(entry["config_source"])).read_text(encoding="utf-8"))
            version = contract.get("version") if isinstance(contract, dict) else None
        except (OSError, ValueError, yaml.YAMLError):
            return "RESEARCH"
    if strategy_version is None or version is None or str(version) != str(strategy_version):
        return "RESEARCH"
    if entry.get("admitted") is True or status in {"ADMITTED", "DEMO_ADMITTED", "LIVE_ADMITTED"}:
        return "ADMITTED"
    return "RESEARCH"


def resolve_ticket_authority(strategy_id: str, strategy_version: Optional[str] = None, *,
                             registry: Optional[Dict[str, Any]] = None, root: Path = REPO_ROOT) -> TicketAuthority:
    entry = (registry if registry is not None else load_registry(root)).get(strategy_id)
    if not isinstance(entry, dict) or entry.get("registered") is not True:
        return TicketAuthority(strategy_id, False, False, False, False, REASON_NOT_REGISTERED)
    visible = dict(registry_visible=True, scanner_visible=entry.get("active") is True)
    fields = {k: entry.get(k) for k in ALLOWED}
    invalid = sorted([k for k, v in fields.items() if v not in ALLOWED[k]]
                     # Order authority is expressed only as demo_order_authority NONE: a ticket
                     # strategy must also carry explicit demo/live flags that are exactly false.
                     + [k for k in NO_ORDER_FLAGS if entry.get(k) is not False])
    if invalid:
        return TicketAuthority(strategy_id, **visible, logic_evaluable=False, ticket_eligible=False,
                               reason=f"{REASON_AUTHORITY_INVALID}:{','.join(invalid)}", **fields)
    identity = logic_identity(strategy_id, strategy_version) if strategy_version else None
    effective = (LOGIC_VERIFIED if fields["logic_status"] == LOGIC_VERIFIED and identity is not None
                 and entry.get("logic_verified_identity") == identity["digest"] else NOT_VERIFIED)
    if strategy_id not in ADAPTERS:
        return TicketAuthority(strategy_id, **visible, logic_evaluable=False, ticket_eligible=False,
                               reason=REASON_ADAPTER_NOT_IMPLEMENTED, **fields)
    if fields["ticket_authority"] != MANUAL_ONLY:
        return TicketAuthority(strategy_id, **visible, logic_evaluable=True, ticket_eligible=False,
                               reason=REASON_NOT_MANUAL_ONLY, logic_status_effective=effective,
                               logic_identity=identity, **fields)
    return TicketAuthority(strategy_id, **visible, logic_evaluable=True, ticket_eligible=True, reason=None,
                           logic_status_effective=effective, logic_identity=identity, **fields)
