"""Phase D1: the real, authoritative TradeProposal source for the Telegram gateway --
replaces Phase C's placeholder JSON-file lookup.

Read-only consumer of post_asian_pilot's own durable evidence (journal/post_asian_pilot/
proposal.json, journal/post_london_newyork_pilot/proposal.json -- one file per pilot
cycle, see post_asian_pilot.pilot_config.PilotConfig.state_dir). This module never calls
post_asian_pilot.pipeline.run_pilot_cycle / build_entry_proposal / save_proposal, never
imports strategy_engine, and never recomputes a signal, decision, or risk-sized
proposal -- it only re-reads what that pipeline has already, independently, persisted.
This is the same posture as post_asian_pilot.store.get_proposal_record (a read helper
already living in that package), applied from outside the package instead of inside it,
so FX Series 002's protected surfaces (post_asian_pilot/*, strategy_engine/*) need no
edit at all (verified separately by an empty git diff against the FX baseline).

Only a record whose `actionable` field is True is ever returned -- a proposal that lost
the daily-slot claim, or that was never eligible past risk/portfolio gating, is
evidence-only and must never reach a Telegram ticket (spec section 10: "READY / WATCH /
NO_TRADE / DATA_ERROR / EXPIRED / BLOCKED should not produce executable approval
tickets unless the canonical contract explicitly says otherwise" -- `actionable` IS that
canonical contract's own signal for "this exact proposal won its daily slot").

Reconstructs execution.adapter.TradeProposal directly from the persisted
`trade_proposal` sub-record's own fields (dataclasses.asdict output, round-tripped
through JSON) -- never from a report's rendered/display text, and never from anything
Telegram-supplied (spec section 6/9).
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from execution.adapter import TradeProposal
from post_asian_pilot.pilot_config import load_pilot_config
from runtime_state.store import JsonKeyValueStore

# The two pilot cycles currently registered for ST_ASIAN_SWEEP_5R_V1 (AG Trade Assistant
# V1.0.3 FX Series 002) -- see scripts/run_post_asian_pilot.py's own --pilot-config
# default/override and strategies/registry.yaml's ST_ASIAN_SWEEP_5R_V1 entry. Resolved
# via load_pilot_config() (the same loader post_asian_pilot.pipeline itself uses) rather
# than hardcoding each cycle's state_dir string a second time, so a future pilot-config
# edit to state_dir cannot silently desync this module from the real journal layout.
_ASIAN_LONDON_PILOT_CONFIG_PATH = "config/pilot/AG_POST_ASIAN_LONDON_PILOT_V1_0_1.yaml"
_LONDON_NEWYORK_PILOT_CONFIG_PATH = "config/pilot/AG_POST_LONDON_NEWYORK_PILOT_V1_0_1.yaml"


def default_pilot_state_dirs() -> Tuple[str, ...]:
    paths = (_ASIAN_LONDON_PILOT_CONFIG_PATH, _LONDON_NEWYORK_PILOT_CONFIG_PATH)
    return tuple(load_pilot_config(path).state_dir or "journal/post_asian_pilot" for path in paths)


def _trade_proposal_from_record(record: dict) -> Optional[TradeProposal]:
    if not record.get("actionable"):
        return None
    tp_record = record.get("trade_proposal")
    if not isinstance(tp_record, dict):
        return None
    return TradeProposal(**tp_record)


def load_actionable_trade_proposal(
    setup_id: str, state_dirs: Sequence[str] = (),
) -> Optional[TradeProposal]:
    """Resolves approval.setup_id -> the persisted, actionable TradeProposal, searching
    every known pilot cycle's proposal store (setup_id is already globally unique -- it
    is intent.signal_id, derived from strategy_id+symbol+session+date -- so at most one
    store will ever hold a match). Returns None if the setup_id is unknown OR exists but
    never became actionable -- callers (authorization.telegram_gateway) already treat a
    None lookup as REASON_PROPOSAL_NOT_FOUND, which is the correct fail-closed outcome
    for a non-actionable proposal too: no `additional NOT_ACTIONABLE branch is invented.
    """
    dirs = tuple(state_dirs) or default_pilot_state_dirs()
    for state_dir in dirs:
        store = JsonKeyValueStore(f"{state_dir}/proposal.json")
        record = store.get(setup_id)
        if record is not None:
            return _trade_proposal_from_record(record)
    return None


def find_actionable_setup_ids(state_dirs: Sequence[str] = ()) -> List[str]:
    """Scans every known pilot cycle's proposal store for setup_ids currently marked
    actionable -- used only by the CLI's publish step to discover which real proposals
    are eligible for a Telegram ticket (a strategy-engine READY decision that has already
    won its daily slot). Read-only: never writes to a post_asian_pilot store."""
    dirs = tuple(state_dirs) or default_pilot_state_dirs()
    found: List[str] = []
    for state_dir in dirs:
        store = JsonKeyValueStore(f"{state_dir}/proposal.json")
        for setup_id, record in store.all().items():
            if record.get("actionable"):
                found.append(setup_id)
    return found
