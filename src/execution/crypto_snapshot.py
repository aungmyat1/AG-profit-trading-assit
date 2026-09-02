"""Initial-account-snapshot / delta-cleanup primitives (spec item 10). Pure data
structures + a comparison function -- no network call, no cleanup ACTION is taken here,
only the scoping decision a future smoke test's cleanup logic would consult.

Known, documented fact this module is designed against (not re-verified here): a real
Binance USDT-M testnet account used by this project already has pre-existing, unrelated
open positions in BTCUSDT and PAXGUSDT from prior manual activity. Any snapshot-delta
comparison used to decide what a future cleanup step may touch MUST treat those as
PRE_EXISTING_UNRELATED, never as this phase's own exposure -- see cleanup_scope() below,
which only ever returns rows traceable to a command_id this run itself recognizes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, FrozenSet, List, Optional, Tuple

ORIGIN_AG_MANAGED = "AG_MANAGED"
ORIGIN_PRE_EXISTING_UNRELATED = "PRE_EXISTING_UNRELATED"
ORIGIN_UNRECOGNIZED = "UNRECOGNIZED"  # traceable to neither a known command_id nor absent entirely


@dataclass(frozen=True)
class PositionRecord:
    """One symbol's exposure at snapshot time. client_order_id/command_id are None for
    exposure this run did not create (e.g. the pre-existing BTCUSDT/PAXGUSDT positions) --
    never fabricated to make a row look AG-managed."""

    symbol: str
    quantity: float
    client_order_id: Optional[str] = None
    command_id: Optional[str] = None


@dataclass(frozen=True)
class AccountSnapshot:
    taken_at: datetime
    positions: Tuple[PositionRecord, ...]

    def by_symbol(self) -> Dict[str, PositionRecord]:
        return {p.symbol: p for p in self.positions}


@dataclass(frozen=True)
class PositionDelta:
    symbol: str
    before_quantity: float
    after_quantity: float
    client_order_id: Optional[str]
    command_id: Optional[str]
    origin: str  # ORIGIN_AG_MANAGED / ORIGIN_PRE_EXISTING_UNRELATED / ORIGIN_UNRECOGNIZED


def _classify_origin(command_id: Optional[str], known_command_ids: FrozenSet[str]) -> str:
    if command_id is not None and command_id in known_command_ids:
        return ORIGIN_AG_MANAGED
    if command_id is None:
        return ORIGIN_PRE_EXISTING_UNRELATED
    return ORIGIN_UNRECOGNIZED  # has a command_id, but not one this run's own journal knows


def diff_snapshots(
    before: AccountSnapshot, after: AccountSnapshot, known_command_ids: FrozenSet[str],
) -> List[PositionDelta]:
    """Compares two snapshots symbol-by-symbol. known_command_ids should come from THIS
    run's own crypto command journal (execution/crypto_journal.py) -- never inferred from
    the snapshot data itself, so a position the exchange happens to tag with some
    client_order_id-shaped string cannot masquerade as AG-managed."""
    before_by_symbol = before.by_symbol()
    after_by_symbol = after.by_symbol()
    symbols = sorted(set(before_by_symbol) | set(after_by_symbol))

    deltas: List[PositionDelta] = []
    for symbol in symbols:
        before_row = before_by_symbol.get(symbol)
        after_row = after_by_symbol.get(symbol)
        before_qty = before_row.quantity if before_row else 0.0
        after_qty = after_row.quantity if after_row else 0.0
        # Prefer the AFTER row's identity fields (a position that appeared during this run
        # carries them there); fall back to the BEFORE row's for one that only shrank/closed.
        identity_row = after_row or before_row
        client_order_id = identity_row.client_order_id if identity_row else None
        command_id = identity_row.command_id if identity_row else None
        origin = _classify_origin(command_id, known_command_ids)
        deltas.append(PositionDelta(
            symbol=symbol, before_quantity=before_qty, after_quantity=after_qty,
            client_order_id=client_order_id, command_id=command_id, origin=origin,
        ))
    return deltas


def cleanup_scope(deltas: List[PositionDelta], known_command_ids: FrozenSet[str]) -> List[PositionDelta]:
    """Narrow, fail-closed cleanup targeting: only rows classified ORIGIN_AG_MANAGED (a
    command_id THIS run's own journal recognizes) are ever eligible. Pre-existing
    unrelated exposure (no command_id) and unrecognized exposure (a command_id from
    somewhere else) are both excluded -- a future cleanup step must never "flatten
    everything in a symbol"."""
    return [
        d for d in deltas
        if d.origin == ORIGIN_AG_MANAGED and d.command_id is not None and d.command_id in known_command_ids
    ]
