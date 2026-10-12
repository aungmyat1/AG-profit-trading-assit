"""The execution-authority object and its re-validation inside the guarded boundary.

A caller's own gate results are never authority. Every guarded call in
``demo_execution.guarded_adapter`` must carry an :class:`ExecutionAuthority`, and the guard
re-validates it here from primary sources rather than trusting the claim:

* identity -- the authority's ticket id, strategy id/version, symbol, session, setup branch,
  direction, logic identity and reserved magic must equal both the committed scope and the
  ticket being executed;
* DEMO account identity -- login suffix + server + trade_mode, pinned by the committed scope
  and re-read live from the host at the guarded step itself;
* authorization -- the host-local standing authorization record is re-read and re-validated,
  and its decision id must equal the one the authority names;
* per-order confirmation -- while required, a bound, in-window, single-use owner confirmation
  must exist in the append-only ticket ledger (consumed before a send is authorized);
* READY / risk / freshness evidence -- each evidence id must be present, current, and equal to
  the digest recomputed here from the very facts the guard re-validated.

An authority is a short-lived, single-use claim: it expires, it is bound to exactly one ticket,
and each guarded transition consumes its id. Nothing here calls a broker.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional, Sequence

from demo_execution.admission import MarketEvidence, check_account_mode
from demo_execution.authorization import resolve_authorization_path

# The sanctioned single-use owner-confirmation writer/validator owns the binding, window and
# reuse rules. This module re-validates through it rather than restating them.
from demo_execution.confirmation import (
    OWNER_CONFIRMATION_USED_KIND,
    check_and_consume_owner_confirmation,
)
from demo_execution.risk import RiskSnapshot
from demo_execution.scope import ScopePolicy
from ticket_store.store import (
    OUTCOME_FIELDS,
    TicketStore,
    TicketStoreError,
    build_outcome,
)

EVIDENCE_READY = "READY"
EVIDENCE_RISK = "RISK"
EVIDENCE_FRESHNESS = "FRESHNESS"
EVIDENCE_KINDS = (EVIDENCE_READY, EVIDENCE_RISK, EVIDENCE_FRESHNESS)

# A live account read is by definition seconds old. A reader that reports its own observation
# time and hands back anything older than this returned a cached snapshot, not a live read.
ACCOUNT_READ_MAX_AGE = timedelta(seconds=30)
ACCOUNT_LOGIN_SUFFIX_MIN_LENGTH = 3
_DEMO_TRADE_MODES = frozenset({0, "0", "DEMO", "ACCOUNT_TRADE_MODE_DEMO"})
# MetaTrader5 ACCOUNT_TRADE_MODE_*: 0 DEMO, 1 CONTEST, 2 REAL.
_MT5_TRADE_MODE_NAMES = {0: "DEMO", 1: "CONTEST", 2: "REAL"}
_CONFIRM_BINDING_KEYS = (
    "ticket_id", "strategy_id", "strategy_version", "symbol", "session", "branch", "direction",
)

EXECUTION_AUTHORITY_MISSING = "EXECUTION_AUTHORITY_MISSING"
EXECUTION_AUTHORITY_INVALID = "EXECUTION_AUTHORITY_INVALID"
AUTHORITY_TIMESTAMP_INVALID = "AUTHORITY_TIMESTAMP_INVALID"
AUTHORITY_EXPIRED = "AUTHORITY_EXPIRED"
AUTHORITY_NOT_YET_VALID = "AUTHORITY_NOT_YET_VALID"
AUTHORITY_REUSED = "AUTHORITY_REUSED"
AUTHORITY_TICKET_MISMATCH = "AUTHORITY_TICKET_MISMATCH"
AUTHORITY_SCOPE_MISMATCH = "AUTHORITY_SCOPE_MISMATCH"
AUTHORIZATION_PATH_MISMATCH = "AUTHORIZATION_PATH_MISMATCH"
AUTHORIZATION_DECISION_ID_MISMATCH = "AUTHORIZATION_DECISION_ID_MISMATCH"
ACCOUNT_IDENTITY_UNAVAILABLE = "ACCOUNT_IDENTITY_UNAVAILABLE"
ACCOUNT_IDENTITY_TIMESTAMP_INVALID = "ACCOUNT_IDENTITY_TIMESTAMP_INVALID"
ACCOUNT_READ_STALE = "ACCOUNT_READ_STALE"
ACCOUNT_LOGIN_SUFFIX_MISMATCH = "ACCOUNT_LOGIN_SUFFIX_MISMATCH"
ACCOUNT_SERVER_MISMATCH = "ACCOUNT_SERVER_MISMATCH"
OWNER_CONFIRM_REQUIRED = "OWNER_CONFIRM_REQUIRED"
OWNER_CONFIRM_STORE_UNAVAILABLE = "OWNER_CONFIRM_STORE_UNAVAILABLE"
OWNER_CONFIRM_MISSING = "OWNER_CONFIRM_MISSING"
OWNER_CONFIRM_ID_MISMATCH = "OWNER_CONFIRM_ID_MISMATCH"
OWNER_CONFIRM_REUSED = "OWNER_CONFIRM_REUSED"
OWNER_CONFIRM_TICKET_INVALID = "OWNER_CONFIRM_TICKET_INVALID"
OWNER_CONFIRM_NOT_CONSUMED = "OWNER_CONFIRM_NOT_CONSUMED"
TICKET_EXPIRED = "TICKET_EXPIRED"


@dataclass(frozen=True)
class AccountIdentity:
    """The DEMO account the order is authorized for. Login SUFFIX only, never a full login."""

    login_suffix: str
    server: str
    trade_mode: str = "DEMO"


@dataclass(frozen=True)
class EvidenceRef:
    """One named piece of gate evidence: an id derived from the facts, and when it was observed."""

    kind: str
    evidence_id: str
    observed_at_utc: datetime


@dataclass(frozen=True)
class ExecutionAuthority:
    """Single-use, ticket-bound authority claim. Every field is required; none is defaulted."""

    authority_id: str
    issued_at_utc: datetime
    ticket_id: str
    strategy_id: str
    strategy_version: str
    symbol: str
    session: str
    setup_branch: str
    direction: str
    logic_identity: str
    magic_number: int
    account: AccountIdentity
    authorization_path: str
    authorization_decision_id: str
    owner_confirmation_id: Optional[str]
    ready_evidence: EvidenceRef
    risk_evidence: EvidenceRef
    freshness_evidence: EvidenceRef

    @property
    def evidence_refs(self) -> tuple[EvidenceRef, ...]:
        return (self.ready_evidence, self.risk_evidence, self.freshness_evidence)

    def identity_payload(self) -> dict[str, Any]:
        """The identity tuple recorded with every lifecycle transition (no secrets, no login)."""
        return {
            "ticket_id": self.ticket_id,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "symbol": self.symbol,
            "session": self.session,
            "setup_branch": self.setup_branch,
            "direction": self.direction,
            "logic_identity": self.logic_identity,
            "magic_number": self.magic_number,
            "account_login_suffix": self.account.login_suffix if isinstance(self.account, AccountIdentity) else None,
            "account_server": self.account.server if isinstance(self.account, AccountIdentity) else None,
            "account_trade_mode": self.account.trade_mode if isinstance(self.account, AccountIdentity) else None,
            "authorization_decision_id": self.authorization_decision_id,
            "owner_confirmation_id": self.owner_confirmation_id,
        }


def _digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def evidence_digest(payload: Any) -> str:
    """Stable sha256 of a canonical JSON structure; the id every evidence ref is bound to."""
    return _digest(payload)


def _as_utc(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _non_empty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_sha256(value: Any) -> bool:
    return _non_empty(value) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _structure(value: Any) -> Any:
    """Canonical, JSON-serializable structure of an evidence object (None when not derivable)."""
    if value is None:
        return None
    if is_dataclass(value) and not isinstance(value, type):
        try:
            return asdict(value)
        except (TypeError, ValueError):
            return None
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Sequence):
        return [_structure(item) for item in value]
    return None


def ready_evidence_id(ticket: Mapping[str, Any], scope: ScopePolicy) -> str:
    """Digest of the exact READY facts the scope/ticket binding gate re-verified."""
    return _digest({
        "kind": EVIDENCE_READY,
        "ticket_id": ticket.get("ticket_id"),
        "decision": ticket.get("decision"),
        "reason_code": ticket.get("reason_code"),
        "strategy_id": scope.strategy_id,
        "strategy_version": scope.strategy_version,
        "symbol": scope.symbol,
        "session": scope.session,
        "setup_branch": scope.setup_branch,
        "direction": ticket.get("direction"),
        "logic_identity": scope.logic_identity,
    })


def risk_evidence_id(risk_snapshot: Any) -> str:
    """Digest of the complete host risk snapshot the C14 caps were evaluated on."""
    return _digest({"kind": EVIDENCE_RISK, "snapshot": _structure(risk_snapshot)})


def freshness_evidence_id(ticket: Mapping[str, Any], market: Any) -> str:
    """Digest of the quote/bar facts and ticket timestamps the freshness gate used."""
    return _digest({
        "kind": EVIDENCE_FRESHNESS,
        "ticket_id": ticket.get("ticket_id"),
        "signal_close_utc": ticket.get("signal_close_utc"),
        "evaluated_at": ticket.get("evaluated_at"),
        "market": _structure(market),
    })


def build_authority(
    *,
    ticket: Mapping[str, Any],
    scope: ScopePolicy,
    market: Optional[MarketEvidence],
    risk_snapshot: Optional[RiskSnapshot],
    now_utc: datetime,
    authority_id: str,
    account: AccountIdentity,
    authorization_path: str,
    authorization_decision_id: str,
    owner_confirmation_id: Optional[str] = None,
) -> ExecutionAuthority:
    """Assemble an authority claim whose evidence ids are derived from the facts themselves.

    This is the sanctioned constructor: the guard recomputes each id from the evidence it
    re-validates, so an id invented anywhere else can never match.
    """
    observed = _as_utc(now_utc)
    if observed is None:
        raise ValueError("now_utc must be an aware UTC timestamp")
    return ExecutionAuthority(
        authority_id=authority_id,
        issued_at_utc=observed,
        ticket_id=str(ticket.get("ticket_id") or ""),
        strategy_id=scope.strategy_id,
        strategy_version=scope.strategy_version,
        symbol=scope.symbol,
        session=scope.session,
        setup_branch=scope.setup_branch,
        direction=str(ticket.get("direction") or ""),
        logic_identity=scope.logic_identity,
        magic_number=scope.magic_number,
        account=account,
        authorization_path=authorization_path,
        authorization_decision_id=authorization_decision_id,
        owner_confirmation_id=owner_confirmation_id,
        ready_evidence=EvidenceRef(EVIDENCE_READY, ready_evidence_id(ticket, scope), observed),
        risk_evidence=EvidenceRef(EVIDENCE_RISK, risk_evidence_id(risk_snapshot), observed),
        freshness_evidence=EvidenceRef(EVIDENCE_FRESHNESS, freshness_evidence_id(ticket, market), observed),
    )


def evidence_id_map(authority: ExecutionAuthority) -> dict[str, Any]:
    """The three evidence ids (and their observation times) recorded with every transition."""
    recorded: dict[str, Any] = {}
    for ref in authority.evidence_refs:
        if not isinstance(ref, EvidenceRef) or ref.kind not in EVIDENCE_KINDS:
            continue
        key = ref.kind.lower()
        observed = _as_utc(ref.observed_at_utc)
        recorded[f"{key}_evidence_id"] = ref.evidence_id
        recorded[f"{key}_evidence_observed_at_utc"] = observed.isoformat() if observed else None
    return recorded


def account_identity_payload(live_read: Any, now_utc: Any) -> dict[str, Any]:
    """Redacted live account facts for an evidence row: login suffix only, never a full login."""
    read = live_read if isinstance(live_read, Mapping) else {}
    observed = _as_utc(read.get("observed_at_utc"))
    taken_at = _as_utc(now_utc)
    return {
        "login_suffix": str(read.get("login_suffix")) if _non_empty(read.get("login_suffix")) else None,
        "server": read.get("server") if _non_empty(read.get("server")) else None,
        "trade_mode": normalize_trade_mode(read.get("trade_mode", read.get("trade_mode_name"))),
        "observed_at_utc": observed.isoformat() if observed else None,
        "read_at_utc": taken_at.isoformat() if taken_at else None,
    }


def per_order_confirm_required(scope: Any) -> bool:
    """True unless the committed scope explicitly retired the per-order confirmation gate.

    C14 drops per-order confirmation only once the separately reviewed executor change and the
    matching AGENTS.md update land together; an absent or non-boolean value stays required.
    """
    value = getattr(scope, "per_order_confirm_required", True)
    return value if type(value) is bool else True


def authority_window(scope: ScopePolicy) -> timedelta:
    """One contract-sourced window bounds the authority, its authorization and its evidence."""
    return timedelta(minutes=scope.signal_expiry_minutes)


def validate_authority_shape(authority: Any) -> tuple[str, ...]:
    """Structural validation only; every field must be present and of its declared type."""
    if not isinstance(authority, ExecutionAuthority):
        return (EXECUTION_AUTHORITY_MISSING,)
    reasons: list[str] = []
    text_fields = (
        "authority_id", "ticket_id", "strategy_id", "strategy_version", "symbol", "session",
        "setup_branch", "direction", "logic_identity", "authorization_path",
        "authorization_decision_id",
    )
    if any(not _non_empty(getattr(authority, name)) for name in text_fields):
        reasons.append(EXECUTION_AUTHORITY_INVALID)
    if isinstance(authority.magic_number, bool) or not isinstance(authority.magic_number, int):
        reasons.append(EXECUTION_AUTHORITY_INVALID)
    if not isinstance(authority.account, AccountIdentity) \
            or not _non_empty(authority.account.login_suffix) or not _non_empty(authority.account.server):
        reasons.append(EXECUTION_AUTHORITY_INVALID)
    for ref, kind in ((authority.ready_evidence, EVIDENCE_READY), (authority.risk_evidence, EVIDENCE_RISK),
                      (authority.freshness_evidence, EVIDENCE_FRESHNESS)):
        if not isinstance(ref, EvidenceRef) or ref.kind != kind or not _is_sha256(ref.evidence_id) \
                or _as_utc(ref.observed_at_utc) is None:
            reasons.append(EXECUTION_AUTHORITY_INVALID)
    if _as_utc(authority.issued_at_utc) is None:
        reasons.append(AUTHORITY_TIMESTAMP_INVALID)
    return tuple(dict.fromkeys(reasons))


def validate_authority_binding(
    authority: ExecutionAuthority,
    scope: ScopePolicy,
    ticket: Optional[Mapping[str, Any]],
    *,
    now_utc: datetime,
) -> tuple[str, ...]:
    """Bind the claim to the committed scope, to the ticket, and to a fresh issuance time."""
    reasons: list[str] = []
    now = _as_utc(now_utc)
    issued = _as_utc(authority.issued_at_utc)
    if now is None or issued is None:
        reasons.append(AUTHORITY_TIMESTAMP_INVALID)
    else:
        window = authority_window(scope)
        if issued > now:
            reasons.append(AUTHORITY_NOT_YET_VALID)
        elif now - issued > window:
            reasons.append(AUTHORITY_EXPIRED)

    expected_scope = {
        "strategy_id": scope.strategy_id,
        "strategy_version": scope.strategy_version,
        "symbol": scope.symbol,
        "session": scope.session,
        "setup_branch": scope.setup_branch,
        "logic_identity": scope.logic_identity,
        "magic_number": scope.magic_number,
    }
    if any(getattr(authority, name) != value for name, value in expected_scope.items()):
        reasons.append(AUTHORITY_SCOPE_MISMATCH)
    if authority.direction not in scope.directions:
        reasons.append(AUTHORITY_SCOPE_MISMATCH)

    expected_account = {
        "login_suffix": scope.account_login_suffix,
        "server": scope.broker_server,
        "trade_mode": "DEMO",
    }
    if any(getattr(authority.account, name) != value for name, value in expected_account.items()):
        reasons.append(ACCOUNT_IDENTITY_UNAVAILABLE)

    if ticket is not None:
        if not isinstance(ticket, Mapping):
            reasons.append(AUTHORITY_TICKET_MISMATCH)
        else:
            branch = ticket.get("setup")
            if branch is None:
                branch = str(ticket.get("branch") or "").split(":", 1)[0]
            expected_ticket = {
                "ticket_id": authority.ticket_id,
                "strategy_id": authority.strategy_id,
                "direction": authority.direction,
            }
            if any(ticket.get(name) != value for name, value in expected_ticket.items()):
                reasons.append(AUTHORITY_TICKET_MISMATCH)
            if str(ticket.get("strategy_version")) != authority.strategy_version \
                    or ticket.get("symbol") != authority.symbol \
                    or ticket.get("cycle", ticket.get("session")) != authority.session \
                    or branch != authority.setup_branch \
                    or ticket.get("logic_identity") != authority.logic_identity:
                reasons.append(AUTHORITY_TICKET_MISMATCH)
    return tuple(dict.fromkeys(reasons))


def validate_authorization_path(authority: ExecutionAuthority, scope: ScopePolicy,
                                configured_path: Optional[str]) -> tuple[str, ...]:
    """The authority must name the same host-local record the guard itself was given."""
    try:
        expected = resolve_authorization_path(configured_path, env_var=scope.authorization_path_env)
        claimed = resolve_authorization_path(authority.authorization_path,
                                             env_var=scope.authorization_path_env)
    except (TypeError, ValueError, OSError):
        return (AUTHORIZATION_PATH_MISMATCH,)
    return () if claimed == expected else (AUTHORIZATION_PATH_MISMATCH,)


def normalize_trade_mode(raw: Any) -> Optional[str]:
    """Map a live terminal trade_mode onto DEMO / a non-DEMO name / None when unusable.

    MT5 reports `trade_mode` as an int (0 DEMO, 1 CONTEST, 2 REAL). An int is always
    classifiable, so a REAL account is reported as non-DEMO rather than as "mode unavailable":
    both refuse, but only one names the actual reason.
    """
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return _MT5_TRADE_MODE_NAMES.get(raw, f"MODE_{raw}")
    if _non_empty(raw):
        text = str(raw).strip()
        if text.lstrip("-").isdigit():
            return normalize_trade_mode(int(text))
        return "DEMO" if text.upper() in _DEMO_TRADE_MODES else text.upper()
    return None


def validate_live_account(
    live_read: Any,
    authority: ExecutionAuthority,
    scope: ScopePolicy,
    *,
    now_utc: datetime,
) -> tuple[str, ...]:
    """Validate the account read the guard took itself, immediately before the broker step."""
    if not isinstance(live_read, Mapping):
        return (ACCOUNT_IDENTITY_UNAVAILABLE,)
    reasons: list[str] = []
    now = _as_utc(now_utc)
    observed = _as_utc(live_read.get("observed_at_utc"))
    if observed is not None:
        if now is None:
            reasons.append(ACCOUNT_IDENTITY_TIMESTAMP_INVALID)
        elif observed > now:
            reasons.append(ACCOUNT_IDENTITY_TIMESTAMP_INVALID)
        elif now - observed > ACCOUNT_READ_MAX_AGE:
            reasons.append(ACCOUNT_READ_STALE)

    suffix = live_read.get("login_suffix")
    if not _non_empty(suffix) or not str(suffix).isascii() or not str(suffix).isdigit() \
            or len(str(suffix)) < ACCOUNT_LOGIN_SUFFIX_MIN_LENGTH:
        reasons.append(ACCOUNT_IDENTITY_UNAVAILABLE)
    elif str(suffix) != scope.account_login_suffix or str(suffix) != authority.account.login_suffix:
        reasons.append(ACCOUNT_LOGIN_SUFFIX_MISMATCH)

    server = live_read.get("server")
    if not _non_empty(server):
        reasons.append(ACCOUNT_IDENTITY_UNAVAILABLE)
    elif server != scope.broker_server or server != authority.account.server:
        reasons.append(ACCOUNT_SERVER_MISMATCH)

    mode = normalize_trade_mode(live_read.get("trade_mode", live_read.get("trade_mode_name")))
    account_reason = check_account_mode(mode)
    if account_reason is not None:
        reasons.append(account_reason)
    elif authority.account.trade_mode != "DEMO":
        reasons.append(ACCOUNT_IDENTITY_UNAVAILABLE)
    return tuple(dict.fromkeys(reasons))


def validate_evidence_refs(
    authority: ExecutionAuthority,
    scope: ScopePolicy,
    ticket: Optional[Mapping[str, Any]],
    market: Optional[MarketEvidence],
    risk_snapshot: Optional[RiskSnapshot],
    *,
    now_utc: datetime,
    check_currency: bool = True,
) -> tuple[str, ...]:
    """Require all three evidence ids to be present, current, and bound to the facts given."""
    reasons: list[str] = []
    now = _as_utc(now_utc)
    window = authority_window(scope)
    facts = {
        EVIDENCE_READY: ready_evidence_id(ticket, scope) if isinstance(ticket, Mapping) else None,
        EVIDENCE_RISK: risk_evidence_id(risk_snapshot) if risk_snapshot is not None else None,
        EVIDENCE_FRESHNESS: (freshness_evidence_id(ticket, market)
                             if isinstance(ticket, Mapping) and market is not None else None),
    }
    for ref in authority.evidence_refs:
        kind = ref.kind if isinstance(ref, EvidenceRef) else None
        if kind not in EVIDENCE_KINDS:
            reasons.append(EXECUTION_AUTHORITY_INVALID)
            continue
        if not isinstance(ref, EvidenceRef) or not _is_sha256(ref.evidence_id):
            reasons.append(f"{kind}_EVIDENCE_MISSING")
            continue
        observed = _as_utc(ref.observed_at_utc)
        if observed is None or now is None:
            reasons.append(f"{kind}_EVIDENCE_MISSING")
        elif check_currency:
            if observed > now:
                reasons.append(f"{kind}_EVIDENCE_TIMESTAMP_IN_FUTURE")
            elif now - observed > window:
                reasons.append(f"{kind}_EVIDENCE_STALE")
        expected = facts.get(kind)
        if expected is None or ref.evidence_id != expected:
            reasons.append(f"{kind}_EVIDENCE_ID_MISMATCH")
    return tuple(dict.fromkeys(reasons))


def validate_evidence_against_trail(authority: ExecutionAuthority,
                                    recorded_evidence: Mapping[str, Any]) -> tuple[str, ...]:
    """Post-trade steps must cite the same evidence ids that authorized the order."""
    reasons: list[str] = []
    for ref in authority.evidence_refs:
        kind = ref.kind if isinstance(ref, EvidenceRef) else None
        if kind not in EVIDENCE_KINDS:
            reasons.append(EXECUTION_AUTHORITY_INVALID)
            continue
        recorded = recorded_evidence.get(f"{kind.lower()}_evidence_id")
        if not _non_empty(recorded) or recorded != ref.evidence_id:
            reasons.append(f"{kind}_EVIDENCE_ID_MISMATCH")
    return tuple(dict.fromkeys(reasons))


def _seal_is_intact(record: Any, kind: str) -> bool:
    if not isinstance(record, dict) or set(record) != set(OUTCOME_FIELDS):
        return False
    if record.get("outcome_kind") != kind:
        return False
    try:
        rebuilt = build_outcome(**{key: record[key] for key in OUTCOME_FIELDS})
    except (TicketStoreError, TypeError, ValueError):
        return False
    return rebuilt == record


def consumed_confirmation_ids(store: TicketStore, ticket_id: str) -> frozenset[str]:
    """The confirm ids the ledger records as consumed for this ticket, seal intact.

    A tampered or unbound consumption marker is not a consumption: it is skipped, so the send
    that depends on it fails closed instead of trusting a rewritten row.
    """
    try:
        rows = store.outcomes(ticket_id)
    except (OSError, ValueError, TypeError, KeyError, TicketStoreError):
        return frozenset()
    consumed: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or row.get("outcome_kind") != OWNER_CONFIRMATION_USED_KIND:
            continue
        if not _seal_is_intact(row, OWNER_CONFIRMATION_USED_KIND):
            continue
        payload = row.get("payload")
        if isinstance(payload, dict) and _non_empty(payload.get("confirm_id")) \
                and payload.get("ticket_id") == ticket_id:
            consumed.add(str(payload["confirm_id"]))
    return frozenset(consumed)


def validate_confirmation_evidence(
    store: Optional[TicketStore],
    authority: ExecutionAuthority,
    ticket: Optional[Mapping[str, Any]],
    *,
    now_utc: datetime,
    require_consumed: bool,
) -> tuple[str, ...]:
    """Re-verify the single-use owner confirmation from the ledger, never from a caller's word.

    Binding, window, duplication and reuse are judged by the sanctioned validator
    (:func:`demo_execution.confirmation.check_and_consume_owner_confirmation`), read-only here:
    this function never writes a row. Consumption is performed by the canonical admission gates,
    which the guard runs itself. What the guard adds is the authority's own claim -- the
    confirmation id the authority names must be the confirmation the ledger holds for this
    ticket -- and the send-time rule that the confirmation was consumed before a send.
    """
    if not _non_empty(authority.owner_confirmation_id):
        return (OWNER_CONFIRM_REQUIRED,)
    if store is None:
        return (OWNER_CONFIRM_STORE_UNAVAILABLE,)
    if not isinstance(ticket, Mapping):
        return (OWNER_CONFIRM_TICKET_INVALID,)
    now = _as_utc(now_utc)
    if now is None:
        return (AUTHORITY_TIMESTAMP_INVALID,)
    try:
        check = check_and_consume_owner_confirmation(store, ticket, now_utc=now, consume=False)
    except (OSError, ValueError, TypeError, KeyError, TicketStoreError):
        return (OWNER_CONFIRM_STORE_UNAVAILABLE,)

    if check.allowed:
        # Bound, in window and not yet consumed: it must be the confirmation the authority names.
        if check.confirmation_id != authority.owner_confirmation_id:
            return (OWNER_CONFIRM_ID_MISMATCH,)
        return (OWNER_CONFIRM_NOT_CONSUMED,) if require_consumed else ()

    if OWNER_CONFIRM_REUSED in check.reason_codes:
        # Already consumed -- by the gates inside this very call, or before it. That is what a
        # send requires; what must still hold is that the consumed one is the claimed one.
        if authority.owner_confirmation_id in consumed_confirmation_ids(store, authority.ticket_id):
            return ()
        return (OWNER_CONFIRM_REUSED, OWNER_CONFIRM_MISSING)

    # The sanctioned validator prefixes every refusal with OWNER_CONFIRM_REQUIRED, so a ledger
    # with no confirmation for this ticket at all arrives with no diagnostic of its own.
    diagnostics = tuple(code for code in check.reason_codes if code != OWNER_CONFIRM_REQUIRED)
    if not diagnostics and check.status == "MISSING_OR_INVALID":
        return (OWNER_CONFIRM_MISSING,)
    return tuple(check.reason_codes)
