"""Scheduler-facing call-site integration (AG_STAGE1_EXACTLY_ONCE_FX_TICKET_DELIVERY_V1
Stage 1 final pre-operational slice). Connects an already-computed
post_asian_pilot.pipeline.PilotCycleResult (produced by scripts/run_post_asian_pilot.py's
existing --once path, unchanged) to fx_cycle_integration.process_pair_result() under an
explicit, config-controlled mode.

Modes:
  DISABLED         -- no ticket_delivery call at all. One-line rollback: setting/
                       reverting `mode: DISABLED` returns to exactly today's unmodified
                       scheduler behavior, regardless of whether the signed `policy:`
                       block below it is valid -- DISABLED never reads or requires it.
  ARCHIVE_ONLY      -- ACTIVATED 2026-09-08 (see PROJECT_STATUS.md / the Stage 1 plan
                       doc's dated entry) as the shipped repository default. Archives
                       every completed cycle decision (READY/WATCH/NO_TRADE/DATA_ERROR/
                       BLOCKED) and registers READY ticket identity, gated by the
                       signed CatchUpPolicy below. Zero network calls -- structural, not
                       merely config-gated: this module never constructs a deliver()
                       closure for ANY mode.
  MESSAGE_DELIVERY  -- STILL NOT AUTHORIZED IN THE SHIPPED config/ticket_delivery.yaml
                       (mode remains ARCHIVE_ONLY there -- see that file's own history
                       comment). WP7 (docs/status/AG_STAGE1_WP7_MESSAGE_DELIVERY_
                       PREFLIGHT_AND_AUTHORIZATION_PACKET_V1.md) implemented the runtime
                       so a SEPARATELY-authorized future config change can activate it
                       with no further code change: this mode now lazily constructs a
                       real deliver() closure over
                       telegram_adapter.deliver_informational_ticket_with_retry()
                       (WP7's chosen retry design (A): in-process wait-and-retry, sleep
                       [30, 60] seconds, 3 total attempts, per the signed policy) --
                       but ONLY when TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID are both set
                       AND the resolved chat_id is present in this config's
                       `telegram_destination.authorized_chat_ids` allow-list AND the
                       resulting TelegramDestinationConfig validates; any failure of
                       that chain falls closed to the same `deliver is None` ->
                       TRANSPORT_NOT_CONFIGURED path ARCHIVE_ONLY already has. This
                       construction is reachable ONLY from the `config.mode ==
                       MODE_MESSAGE_DELIVERY` branch inside process_cycle_result() --
                       ARCHIVE_ONLY/DISABLED never call it, so they remain provably
                       unable to construct the network adapter.

Signed operational policy (OWNER_APPROVED 2026-09-08 -- see
docs/status/AG_STAGE1_CATCHUP_AND_RETRY_POLICY_DECISION_PACKET_V1.md's approval
addendum): `config/ticket_delivery.yaml`'s `policy:` block is REQUIRED and strictly
validated whenever `mode != DISABLED` -- see `_parse_policy()`. It is never required,
and never read, when `mode == DISABLED`.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import yaml

from notifications.telegram_client import TelegramClient
from post_asian_pilot.report import render_entry_ticket

from .attempt_journal import AttemptJournal
from .delivery_store import TicketDeliveryStore
from .fx_cycle_integration import process_pair_result
from .policy import CatchUpPolicy, RetryPolicy
from .telegram_adapter import (
    TelegramConfigError,
    TelegramDestinationConfig,
    deliver_informational_ticket_with_retry,
)

MODE_DISABLED = "DISABLED"
MODE_ARCHIVE_ONLY = "ARCHIVE_ONLY"
MODE_MESSAGE_DELIVERY = "MESSAGE_DELIVERY"
_VALID_MODES = (MODE_DISABLED, MODE_ARCHIVE_ONLY, MODE_MESSAGE_DELIVERY)
_ARCHIVING_MODES = (MODE_ARCHIVE_ONLY, MODE_MESSAGE_DELIVERY)  # both archive-before-send; only MESSAGE_DELIVERY may also construct a deliver() closure -- see module docstring

DEFAULT_CONFIG_PATH = "config/ticket_delivery.yaml"
DEFAULT_ARCHIVE_ROOT = "journal/ticket_delivery/archive"
DEFAULT_DELIVERY_STATE_DIR = "journal/ticket_delivery/state"

_REQUIRED_POLICY_FIELDS = (
    "fx_max_catch_up_age_minutes", "delivery_max_attempts",
    "delivery_retry_base_delay_seconds", "delivery_retry_max_delay_seconds",
)

REASON_POLICY_BLOCK_MISSING = "POLICY_BLOCK_MISSING"
REASON_POLICY_VALUE_MISSING = "POLICY_VALUE_MISSING"
REASON_POLICY_VALUE_INVALID_TYPE = "POLICY_VALUE_INVALID_TYPE"
REASON_POLICY_VALUE_NOT_POSITIVE = "POLICY_VALUE_NOT_POSITIVE"
REASON_POLICY_UNKNOWN_FIELD = "POLICY_UNKNOWN_FIELD"
REASON_POLICY_RETRY_DELAY_BOUNDS_INVALID = "POLICY_RETRY_DELAY_BOUNDS_INVALID"
REASON_TELEGRAM_DESTINATION_BLOCK_INVALID = "TELEGRAM_DESTINATION_BLOCK_INVALID"


class TicketDeliveryConfigError(Exception):
    """Raised by load_integration_config() ONLY when mode != DISABLED and the signed
    `policy:` block is missing, malformed, or fails validation. Deliberately NOT raised
    for a missing config file, malformed top-level YAML, or an unrecognized `mode`
    value -- those retain the pre-existing, already-tested fail-closed-to-DISABLED
    behavior (the caller cannot even determine what was requested, so the safest
    response is an implicit no-op). A syntactically valid ARCHIVE_ONLY/MESSAGE_DELIVERY
    request with an invalid policy block is different in kind: the operator has
    unambiguously asked to activate ticket delivery with a broken policy, which must be
    visible (a nonzero scheduler exit, via scripts/run_post_asian_pilot.py's existing
    broad exception handling in _process_ticket_delivery()), not silently disabled."""

    def __init__(self, reason_code: str, message: str):
        super().__init__(message)
        self.reason_code = reason_code


@dataclass(frozen=True)
class TicketDeliveryIntegrationConfig:
    mode: str
    archive_root: str
    delivery_state_dir: str
    catch_up_policy: CatchUpPolicy
    retry_policy: RetryPolicy
    # WP7: the explicit destination allow-list -- NEVER inferred from TELEGRAM_CHAT_ID
    # itself (see telegram_adapter.TelegramDestinationConfig.from_env()'s docstring).
    # Defaults to an empty frozenset (== "no destination authorized") so every
    # pre-WP7 caller/test that constructs this dataclass without the new field keeps
    # working unchanged, and MESSAGE_DELIVERY fails closed to TRANSPORT_NOT_CONFIGURED
    # whenever it is absent.
    authorized_chat_ids: frozenset = field(default_factory=frozenset)


def _require_numeric(raw_policy: Dict[str, Any], field: str, *, integer: bool) -> float:
    if field not in raw_policy:
        raise TicketDeliveryConfigError(REASON_POLICY_VALUE_MISSING, f"required policy field '{field}' is missing")
    value = raw_policy[field]
    # bool is a subclass of int in Python -- explicitly excluded so `true`/`false`
    # can never silently pass as 1/0.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TicketDeliveryConfigError(REASON_POLICY_VALUE_INVALID_TYPE, f"policy field '{field}' must be numeric, got {type(value).__name__}")
    if integer and not isinstance(value, int):
        raise TicketDeliveryConfigError(REASON_POLICY_VALUE_INVALID_TYPE, f"policy field '{field}' must be an integer, got {type(value).__name__}")
    if value <= 0:
        raise TicketDeliveryConfigError(REASON_POLICY_VALUE_NOT_POSITIVE, f"policy field '{field}' must be positive, got {value}")
    return value


def _parse_policy(raw_policy: Optional[Dict[str, Any]]) -> "_SignedPolicyValues":
    """Strict validation of the signed policy contract (OWNER_APPROVED 2026-09-08):
    every required field must be present, numeric, and positive; base retry delay must
    not exceed max retry delay; no unrecognized field is tolerated. Never silently
    substitutes a default for an invalid or missing value -- raises
    TicketDeliveryConfigError with a specific reason_code instead.

    Attempt-semantics interpretation (documented per this task's own instruction not to
    silently choose one): `delivery_max_attempts` is the TOTAL number of attempts,
    INCLUDING the initial attempt -- this is the existing, already-implemented
    interpretation in `RetryPolicy.should_retry()` (`attempt_number >= max_attempts`
    refuses a further retry), not a new choice made here. Under the approved
    max_attempts=3, base=30s, max=300s contract this yields exactly: attempt 1
    (initial) -> attempt 2 after a 30s delay -> attempt 3 after a 60s delay -> exhausted
    (no attempt 4), matching the approved contract verbatim -- see
    tests/test_ticket_delivery_policy.py's signed-contract-specific test."""
    if raw_policy is None:
        raise TicketDeliveryConfigError(REASON_POLICY_BLOCK_MISSING, "mode is not DISABLED but the 'policy:' block is missing")
    if not isinstance(raw_policy, dict):
        raise TicketDeliveryConfigError(REASON_POLICY_BLOCK_MISSING, "the 'policy:' block must be a mapping")

    unknown = set(raw_policy) - set(_REQUIRED_POLICY_FIELDS)
    if unknown:
        raise TicketDeliveryConfigError(REASON_POLICY_UNKNOWN_FIELD, f"unrecognized policy field(s): {sorted(unknown)}")

    catch_up_minutes = _require_numeric(raw_policy, "fx_max_catch_up_age_minutes", integer=True)
    max_attempts = _require_numeric(raw_policy, "delivery_max_attempts", integer=True)
    base_delay = _require_numeric(raw_policy, "delivery_retry_base_delay_seconds", integer=False)
    max_delay = _require_numeric(raw_policy, "delivery_retry_max_delay_seconds", integer=False)

    if base_delay > max_delay:
        raise TicketDeliveryConfigError(
            REASON_POLICY_RETRY_DELAY_BOUNDS_INVALID,
            f"delivery_retry_base_delay_seconds ({base_delay}) must not exceed delivery_retry_max_delay_seconds ({max_delay})",
        )

    return _SignedPolicyValues(
        fx_max_catch_up_age_minutes=int(catch_up_minutes), delivery_max_attempts=int(max_attempts),
        delivery_retry_base_delay_seconds=float(base_delay), delivery_retry_max_delay_seconds=float(max_delay),
    )


def _parse_authorized_chat_ids(raw_block: Optional[Dict[str, Any]]) -> frozenset:
    """WP7: `telegram_destination:` is a SIBLING block to `policy:`, deliberately kept
    out of the strictly-validated `policy:` block (which rejects any unrecognized
    field) so this can be added additively without touching the already-signed policy
    contract. Absent block -> empty allow-list (never inferred, never fabricated) --
    this is NOT an error even when mode != DISABLED, unlike a missing `policy:` block:
    an operator may legitimately run ARCHIVE_ONLY (or even MESSAGE_DELIVERY, though
    unauthorized without this) without ever configuring a destination."""
    if raw_block is None:
        return frozenset()
    if not isinstance(raw_block, dict):
        raise TicketDeliveryConfigError(REASON_TELEGRAM_DESTINATION_BLOCK_INVALID, "the 'telegram_destination:' block must be a mapping")
    ids = raw_block.get("authorized_chat_ids", [])
    if not isinstance(ids, list) or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
        raise TicketDeliveryConfigError(
            REASON_TELEGRAM_DESTINATION_BLOCK_INVALID, "'telegram_destination.authorized_chat_ids' must be a list of integers",
        )
    return frozenset(ids)


@dataclass(frozen=True)
class _SignedPolicyValues:
    fx_max_catch_up_age_minutes: int
    delivery_max_attempts: int
    delivery_retry_base_delay_seconds: float
    delivery_retry_max_delay_seconds: float


def load_integration_config(path: Optional[str] = None) -> TicketDeliveryIntegrationConfig:
    """Fail-closed to DISABLED (silently, exit 0) on any missing file, malformed
    top-level YAML, or unrecognized `mode` value -- unchanged from the original design:
    a request this function cannot even parse is safest treated as an implicit no-op,
    never crashing the scheduler run or altering the strategy cycle report.

    A DIFFERENT failure mode -- mode is validly ARCHIVE_ONLY/MESSAGE_DELIVERY but the
    signed `policy:` block is missing/invalid -- is NOT silently absorbed: it RAISES
    TicketDeliveryConfigError, which scripts/run_post_asian_pilot.py's existing
    exception handling turns into a nonzero scheduler exit (see
    _process_ticket_delivery()). This is a deliberate asymmetry: an operator who wrote
    `mode: ARCHIVE_ONLY` has unambiguously asked to activate ticket delivery, so a
    broken policy under that request must be visible, not swallowed.

    `path` defaults to the module-level DEFAULT_CONFIG_PATH, read dynamically at call
    time (not bound as a Python default-argument value at definition time) so tests can
    monkeypatch the module attribute and have it actually take effect."""
    path = path or DEFAULT_CONFIG_PATH
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        return TicketDeliveryIntegrationConfig(MODE_DISABLED, DEFAULT_ARCHIVE_ROOT, DEFAULT_DELIVERY_STATE_DIR, CatchUpPolicy(), RetryPolicy())

    mode = raw.get("mode", MODE_DISABLED)
    archive_root = raw.get("archive_root", DEFAULT_ARCHIVE_ROOT)
    delivery_state_dir = raw.get("delivery_state_dir", DEFAULT_DELIVERY_STATE_DIR)
    if mode not in _VALID_MODES:
        mode = MODE_DISABLED

    if mode == MODE_DISABLED:
        return TicketDeliveryIntegrationConfig(mode, archive_root, delivery_state_dir, CatchUpPolicy(), RetryPolicy())

    signed = _parse_policy(raw.get("policy"))
    catch_up_policy = CatchUpPolicy(max_catch_up_age=dt.timedelta(minutes=signed.fx_max_catch_up_age_minutes))
    retry_policy = RetryPolicy(
        max_attempts=signed.delivery_max_attempts, base_delay_seconds=signed.delivery_retry_base_delay_seconds,
        max_delay_seconds=signed.delivery_retry_max_delay_seconds,
    )
    authorized_chat_ids = _parse_authorized_chat_ids(raw.get("telegram_destination"))
    return TicketDeliveryIntegrationConfig(mode, archive_root, delivery_state_dir, catch_up_policy, retry_policy, authorized_chat_ids)


def cycle_label_from_pilot_path(pilot_path: Optional[str]) -> str:
    """Derived from the --pilot-config argument scripts/run_post_asian_pilot.py already
    receives -- no pilot config YAML file was modified to add a new field. `None`
    matches the scheduled Asian->London task's own no-argument convention
    (scripts/scheduled/run_asian_london_once.bat)."""
    if not pilot_path:
        return "ASIAN_LONDON"
    upper = pilot_path.upper()
    if "LONDON_NEWYORK" in upper:
        return "LONDON_NEWYORK"
    if "ASIAN_LONDON" in upper:
        return "ASIAN_LONDON"
    raise ValueError(f"cannot derive a cycle label from pilot_path={pilot_path!r} -- no ASIAN_LONDON/LONDON_NEWYORK marker found")


def _build_message_delivery_closure(
    *, config: TicketDeliveryIntegrationConfig, store: TicketDeliveryStore,
) -> Optional[Callable[[str, str], Any]]:
    """WP7: constructs a real `(logical_ticket_id, message_text) -> DeliveryOutcome`
    closure over telegram_adapter.deliver_informational_ticket_with_retry() -- called
    ONLY from process_cycle_result()'s MODE_MESSAGE_DELIVERY branch, never from
    ARCHIVE_ONLY/DISABLED. Fails closed to None (never raises out of this integration
    call site) on ANY of: missing TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID env var, a
    malformed TELEGRAM_CHAT_ID, or a chat_id outside config.authorized_chat_ids --
    delegated entirely to TelegramDestinationConfig.from_env(), no parallel
    validation. A `None` return here makes fx_cycle_integration.process_pair_result()
    take its existing, already-tested `deliver is None` -> TRANSPORT_NOT_CONFIGURED
    path -- the archived decision is preserved, only the network step is skipped."""
    try:
        destination = TelegramDestinationConfig.from_env(authorized_chat_ids=config.authorized_chat_ids)
    except TelegramConfigError:
        return None

    client = TelegramClient(destination.bot_token)
    journal = AttemptJournal(path=f"{config.delivery_state_dir}/attempt_journal.jsonl")

    def _deliver(logical_ticket_id: str, message_text: str):
        return deliver_informational_ticket_with_retry(
            store=store, logical_ticket_id=logical_ticket_id, message_text=message_text,
            client=client, destination=destination, retry_policy=config.retry_policy,
            attempt_journal=journal,
        )

    return _deliver


def process_cycle_result(
    result, *, pilot_path: Optional[str], config: Optional[TicketDeliveryIntegrationConfig] = None,
    ledger: Any = None, release_fingerprint: Optional[str] = None, strategy_fingerprint: Optional[str] = None,
    now: Optional[dt.datetime] = None,
) -> List[Dict[str, Any]]:
    """The single call site scripts/run_post_asian_pilot.py (and its tests) use.
    `result` is the UNMODIFIED PilotCycleResult run_pilot_cycle() already returned --
    this function never re-evaluates or mutates it. `ledger`/`release_fingerprint`/
    `strategy_fingerprint` are the same optional, best-effort context
    scripts/run_post_asian_pilot.py's existing `_entry_ticket_context()` already builds
    for report rendering -- reused verbatim, not rebuilt.

    `now`: injectable clock (real wall-clock when omitted, a fixed value in tests --
    never a real sleep anywhere in this call chain) forwarded to
    fx_cycle_integration.process_pair_result()'s catch-up gate and delivery-journal
    timestamps.

    Returns a list of plain-dict outcomes (one per PairResult), always -- an archive
    failure, catch-up rejection, or render-block for one pair is reported in that
    pair's own dict, never raised, so one pair's operational failure never prevents the
    loop from completing for the others (requirement: never cause strategy
    reevaluation, never abort the cycle report)."""
    config = config or load_integration_config()
    if config.mode == MODE_DISABLED:
        return []

    cycle = cycle_label_from_pilot_path(pilot_path)
    store = TicketDeliveryStore(state_dir=config.delivery_state_dir)

    def render_dict(pair):
        if ledger is None or release_fingerprint is None or strategy_fingerprint is None:
            return {}  # renderer reports MISSING_MANDATORY_FIELDS honestly -- never fabricated
        return render_entry_ticket(
            pair.proposal, pair.decision, result.strategy, result.release_id,
            release_fingerprint, strategy_fingerprint, ledger, result.trading_date,
        )

    # ARCHIVE_ONLY: `deliver` stays None, unconditionally, for the entire function body
    # -- this line is the ONLY assignment reachable on that path, so ARCHIVE_ONLY is
    # PROVABLY unable to construct the network adapter (not merely config-gated).
    # MESSAGE_DELIVERY (WP7): a real deliver() closure is constructed LAZILY, and only
    # inside this one guarded branch, only when the mode is exactly MESSAGE_DELIVERY --
    # _build_message_delivery_closure() itself fails closed to None (falling back to
    # this same TRANSPORT_NOT_CONFIGURED behavior ARCHIVE_ONLY already has) on any
    # missing/malformed/unauthorized destination or invalid client construction.
    deliver = None
    if config.mode == MODE_MESSAGE_DELIVERY:
        deliver = _build_message_delivery_closure(config=config, store=store)
    assert config.mode in _ARCHIVING_MODES  # exhaustiveness guard -- DISABLED already returned above

    outcomes: List[Dict[str, Any]] = []
    for pair in result.pairs:
        outcome = process_pair_result(
            pair, strategy_id=result.strategy.strategy_id, strategy_version=result.strategy.version,
            application_release=result.release_id, cycle=cycle, trading_date=result.trading_date,
            delivery_store=store, render_entry_ticket_dict=render_dict, deliver=deliver,
            archive_root=config.archive_root, now=now, catch_up_policy=config.catch_up_policy,
        )
        outcomes.append({
            "symbol": outcome.symbol, "cycle_state": outcome.cycle_state,
            "logical_ticket_id": outcome.logical_ticket_id, "archived": outcome.archived,
            "delivery_state": outcome.delivery_state, "reason_code": outcome.reason_code,
        })
    return outcomes
