"""Scheduler-facing call-site integration (AG_STAGE1_EXACTLY_ONCE_FX_TICKET_DELIVERY_V1
Stage 1 final pre-operational slice). Connects an already-computed
post_asian_pilot.pipeline.PilotCycleResult (produced by scripts/run_post_asian_pilot.py's
existing --once path, unchanged) to fx_cycle_integration.process_pair_result() under an
explicit, config-controlled mode.

Modes:
  DISABLED         -- no ticket_delivery call at all. The only mode this repository's
                       shipped config/ticket_delivery.yaml ships with. Instant rollback:
                       deleting/reverting that one file's `mode` line returns to exactly
                       today's unmodified scheduler behavior.
  ARCHIVE_ONLY      -- archive every cycle decision, register READY ticket identity.
                       Zero network calls -- structural, not merely config-gated: this
                       module never constructs a deliver() closure for ANY mode.
  MESSAGE_DELIVERY  -- NOT ACTIVATED this pass. As of this commit, MESSAGE_DELIVERY is
                       handled IDENTICALLY to ARCHIVE_ONLY (deliver=None) -- the actual
                       Telegram client/destination construction is deliberately not
                       wired into this integration function yet, so setting
                       `mode: MESSAGE_DELIVERY` in config today has no effect beyond
                       what ARCHIVE_ONLY already does. Activating real delivery is a
                       separate, later change (WP7), gated on the owner-signed catch-up
                       and retry policy values -- see
                       docs/status/AG_STAGE1_CATCHUP_AND_RETRY_POLICY_DECISION_PACKET_V1.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import yaml

from post_asian_pilot.report import render_entry_ticket

from .delivery_store import TicketDeliveryStore
from .fx_cycle_integration import process_pair_result

MODE_DISABLED = "DISABLED"
MODE_ARCHIVE_ONLY = "ARCHIVE_ONLY"
MODE_MESSAGE_DELIVERY = "MESSAGE_DELIVERY"
_VALID_MODES = (MODE_DISABLED, MODE_ARCHIVE_ONLY, MODE_MESSAGE_DELIVERY)
_ARCHIVING_MODES = (MODE_ARCHIVE_ONLY, MODE_MESSAGE_DELIVERY)  # both currently behave identically -- see module docstring

DEFAULT_CONFIG_PATH = "config/ticket_delivery.yaml"
DEFAULT_ARCHIVE_ROOT = "journal/ticket_delivery/archive"
DEFAULT_DELIVERY_STATE_DIR = "journal/ticket_delivery/state"


@dataclass(frozen=True)
class TicketDeliveryIntegrationConfig:
    mode: str
    archive_root: str
    delivery_state_dir: str


def load_integration_config(path: Optional[str] = None) -> TicketDeliveryIntegrationConfig:
    """Fail-closed to DISABLED on any missing file, malformed YAML, or unrecognized
    mode value -- a configuration problem must never crash the scheduler run or alter
    the strategy cycle report; it can only ever result in the safest (no-op) behavior.

    `path` defaults to the module-level DEFAULT_CONFIG_PATH, read dynamically at call
    time (not bound as a Python default-argument value at definition time) so tests can
    monkeypatch the module attribute and have it actually take effect."""
    path = path or DEFAULT_CONFIG_PATH
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        return TicketDeliveryIntegrationConfig(MODE_DISABLED, DEFAULT_ARCHIVE_ROOT, DEFAULT_DELIVERY_STATE_DIR)

    mode = raw.get("mode", MODE_DISABLED)
    archive_root = raw.get("archive_root", DEFAULT_ARCHIVE_ROOT)
    delivery_state_dir = raw.get("delivery_state_dir", DEFAULT_DELIVERY_STATE_DIR)
    if mode not in _VALID_MODES:
        mode = MODE_DISABLED
    return TicketDeliveryIntegrationConfig(mode=mode, archive_root=archive_root, delivery_state_dir=delivery_state_dir)


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


def process_cycle_result(
    result, *, pilot_path: Optional[str], config: Optional[TicketDeliveryIntegrationConfig] = None,
    ledger: Any = None, release_fingerprint: Optional[str] = None, strategy_fingerprint: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """The single call site scripts/run_post_asian_pilot.py (and its tests) use.
    `result` is the UNMODIFIED PilotCycleResult run_pilot_cycle() already returned --
    this function never re-evaluates or mutates it. `ledger`/`release_fingerprint`/
    `strategy_fingerprint` are the same optional, best-effort context
    scripts/run_post_asian_pilot.py's existing `_entry_ticket_context()` already builds
    for report rendering -- reused verbatim, not rebuilt.

    Returns a list of plain-dict outcomes (one per PairResult), always -- an archive
    failure or render-block for one pair is reported in that pair's own dict, never
    raised, so one pair's operational failure never prevents the loop from completing
    for the others (requirement: never cause strategy reevaluation, never abort the
    cycle report)."""
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

    # Both ARCHIVE_ONLY and (this pass's still-inert) MESSAGE_DELIVERY pass deliver=None:
    # zero network reachability is enforced structurally here, not by config alone.
    deliver = None
    assert config.mode in _ARCHIVING_MODES  # exhaustiveness guard -- DISABLED already returned above

    outcomes: List[Dict[str, Any]] = []
    for pair in result.pairs:
        outcome = process_pair_result(
            pair, strategy_id=result.strategy.strategy_id, strategy_version=result.strategy.version,
            application_release=result.release_id, cycle=cycle, trading_date=result.trading_date,
            delivery_store=store, render_entry_ticket_dict=render_dict, deliver=deliver,
            archive_root=config.archive_root,
        )
        outcomes.append({
            "symbol": outcome.symbol, "cycle_state": outcome.cycle_state,
            "logical_ticket_id": outcome.logical_ticket_id, "archived": outcome.archived,
            "delivery_state": outcome.delivery_state, "reason_code": outcome.reason_code,
        })
    return outcomes
