"""Tests for execution/crypto_snapshot.py: snapshot/delta primitives, proving cleanup
scope stays narrow even when pre-existing, unrelated positions (the documented real
testnet-account fact: pre-existing BTCUSDT and PAXGUSDT positions from prior manual
activity) are present in both snapshots."""
from __future__ import annotations

from datetime import datetime, timezone

from execution.crypto_snapshot import (
    ORIGIN_AG_MANAGED,
    ORIGIN_PRE_EXISTING_UNRELATED,
    ORIGIN_UNRECOGNIZED,
    AccountSnapshot,
    PositionRecord,
    cleanup_scope,
    diff_snapshots,
)

_NOW = datetime.now(timezone.utc)


def test_pre_existing_positions_are_never_ag_managed():
    """Before AND after snapshots both carry the pre-existing, unrelated BTCUSDT/PAXGUSDT
    positions unchanged -- no command_id in either row."""
    before = AccountSnapshot(_NOW, (
        PositionRecord("BTCUSDT", 0.05),  # pre-existing manual BTCUSDT exposure
        PositionRecord("PAXGUSDT", 1.2),  # pre-existing manual PAXGUSDT exposure
    ))
    after = AccountSnapshot(_NOW, (
        PositionRecord("BTCUSDT", 0.05),
        PositionRecord("PAXGUSDT", 1.2),
    ))
    deltas = diff_snapshots(before, after, known_command_ids=frozenset())
    assert all(d.origin == ORIGIN_PRE_EXISTING_UNRELATED for d in deltas)
    assert cleanup_scope(deltas, known_command_ids=frozenset()) == []


def test_ag_created_exposure_is_scoped_for_cleanup_pre_existing_is_not():
    known = frozenset({"cmd-ag-1"})
    before = AccountSnapshot(_NOW, (
        PositionRecord("BTCUSDT", 0.05),  # pre-existing, unrelated -- no command_id
        PositionRecord("PAXGUSDT", 1.2),  # pre-existing, unrelated -- no command_id
    ))
    after = AccountSnapshot(_NOW, (
        PositionRecord("BTCUSDT", 0.05),                              # unchanged pre-existing
        PositionRecord("PAXGUSDT", 1.2),                              # unchanged pre-existing
        PositionRecord("ETHUSDT", 0.5, client_order_id="AGX-ag-1", command_id="cmd-ag-1"),  # AG-created
    ))
    deltas = diff_snapshots(before, after, known_command_ids=known)
    scoped = cleanup_scope(deltas, known_command_ids=known)

    assert len(scoped) == 1
    assert scoped[0].symbol == "ETHUSDT"
    assert scoped[0].command_id == "cmd-ag-1"

    btc_delta = next(d for d in deltas if d.symbol == "BTCUSDT")
    paxg_delta = next(d for d in deltas if d.symbol == "PAXGUSDT")
    assert btc_delta.origin == ORIGIN_PRE_EXISTING_UNRELATED
    assert paxg_delta.origin == ORIGIN_PRE_EXISTING_UNRELATED
    # Cleanup scope must NEVER include the pre-existing symbols, even though BTCUSDT is
    # also the symbol this phase's own strategy trades -- "flatten everything in a symbol"
    # is exactly the failure mode this test guards against.
    assert all(d.symbol != "BTCUSDT" for d in scoped)
    assert all(d.symbol != "PAXGUSDT" for d in scoped)


def test_unrecognized_command_id_is_not_treated_as_ag_managed():
    """A command_id present on a position but NOT in this run's own known_command_ids
    (e.g. from a different process/run) must not be swept into cleanup scope either."""
    known = frozenset({"cmd-this-run"})
    before = AccountSnapshot(_NOW, ())
    after = AccountSnapshot(_NOW, (
        PositionRecord("ETHUSDT", 0.5, client_order_id="AGX-other", command_id="cmd-other-run"),
    ))
    deltas = diff_snapshots(before, after, known_command_ids=known)
    assert deltas[0].origin == ORIGIN_UNRECOGNIZED
    assert cleanup_scope(deltas, known_command_ids=known) == []


def test_closed_ag_position_still_traceable_via_before_row():
    known = frozenset({"cmd-ag-2"})
    before = AccountSnapshot(_NOW, (
        PositionRecord("ETHUSDT", 0.5, client_order_id="AGX-ag-2", command_id="cmd-ag-2"),
    ))
    after = AccountSnapshot(_NOW, ())  # position fully closed
    deltas = diff_snapshots(before, after, known_command_ids=known)
    assert deltas[0].symbol == "ETHUSDT"
    assert deltas[0].before_quantity == 0.5
    assert deltas[0].after_quantity == 0.0
    assert deltas[0].origin == ORIGIN_AG_MANAGED
