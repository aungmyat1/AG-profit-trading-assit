"""WP3 (docs/plans/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_DELIVERY_V1.md) -- per-cycle durable
decision archive, archived immediately after the cycle checkpoint and strictly before
any delivery attempt.

Reuses post_asian_pilot.report_archive.write_report() UNCHANGED -- it already provides
exactly the required semantics (atomic temp-file + os.replace write, idempotent
same-content rerun, append-only numbered correction on genuinely changed content,
original record never overwritten). No new persistence mechanism is introduced here;
this module only supplies the per-(strategy, symbol, cycle) archive path granularity
report_archive's generic `report_type` parameter doesn't itself define, and a thin
record shape.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional

from post_asian_pilot.report_archive import DEFAULT_ARCHIVE_ROOT, write_report

from .identity import logical_ticket_id

# Every cycle result is archived, not only READY (WP3 requirement).
CYCLE_STATE_READY = "READY"
CYCLE_STATE_WATCH = "WATCH"
CYCLE_STATE_NO_TRADE = "NO_TRADE"
CYCLE_STATE_DATA_ERROR = "DATA_ERROR"
CYCLE_STATE_BLOCKED = "BLOCKED"
_VALID_CYCLE_STATES = {
    CYCLE_STATE_READY, CYCLE_STATE_WATCH, CYCLE_STATE_NO_TRADE,
    CYCLE_STATE_DATA_ERROR, CYCLE_STATE_BLOCKED,
}


class ArchiveFailedError(RuntimeError):
    """Archive persistence failed -- callers MUST treat this as fail-closed and never
    proceed to a delivery attempt (WP3: "archive failure prevents delivery")."""


@dataclass(frozen=True)
class CycleDecisionRecord:
    """The strategy-owned facts this layer archives verbatim -- never recomputed,
    never reinterpreted. `cycle_state` is the one field this layer itself classifies
    (from the caller-supplied decision status), everything else is passed through."""

    strategy_id: str
    strategy_version: str
    application_release: str
    symbol: str
    cycle: str
    trading_date: dt.date
    cycle_state: str
    evaluation_time_utc: str
    payload: Dict[str, Any] = field(default_factory=dict)
    reason_codes: tuple = ()

    def __post_init__(self) -> None:
        if self.cycle_state not in _VALID_CYCLE_STATES:
            raise ValueError(f"cycle_state={self.cycle_state!r} not one of {_VALID_CYCLE_STATES}")

    def logical_ticket_id(self) -> str:
        return logical_ticket_id(
            strategy_id=self.strategy_id, strategy_version=self.strategy_version,
            symbol=self.symbol, cycle=self.cycle, trading_date=self.trading_date,
        )

    def to_archive_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["trading_date"] = self.trading_date.isoformat()
        d["logical_ticket_id"] = self.logical_ticket_id()
        d["reason_codes"] = list(self.reason_codes)
        return d


def _report_type(strategy_id: str, symbol: str, cycle: str) -> str:
    # One archive file per (strategy, symbol, cycle, trading_date) -- report_archive's
    # own archive_path() already appends /{year}/{date}.json under this report_type.
    return f"fx_ticket_archive/{strategy_id}/{symbol}/{cycle}"


def archive_cycle_decision(
    record: CycleDecisionRecord, *, root: str = DEFAULT_ARCHIVE_ROOT, correction_reason: Optional[str] = None,
) -> str:
    """Archive-before-send: callers MUST call this and receive a path back before
    attempting any delivery. Raises ArchiveFailedError (never returns a partial/
    ambiguous result) if the underlying write fails -- see report_archive.write_report,
    which itself uses atomic temp-file + os.replace, so a failure here means the write
    genuinely did not happen, not that its outcome is unknown."""
    try:
        return write_report(
            _report_type(record.strategy_id, record.symbol, record.cycle),
            record.trading_date, record.to_archive_dict(),
            root=root, correction_reason=correction_reason,
        )
    except OSError as exc:
        raise ArchiveFailedError(
            f"ARCHIVE_UNAVAILABLE: failed to persist cycle decision for "
            f"{record.logical_ticket_id()}: {exc}"
        ) from exc
