"""Candidate-occurrence identity composition (ST_LARGE_SMC_V1 C14B,
docs/status/ST_LARGE_SMC_V1_C14B_OCCURRENCE_IDENTITY_HARDENING_STATUS.md).

Additive only -- does not modify proposals/identity.py or proposals/lifecycle.py, and
is not wired into either yet. Nothing in this module is called by any existing runtime
path (Session Trading, the live SMC_CONDITIONAL_ENTRY_V2 watcher in
daily_routine/m5_execution.py, or historical_replay/orchestrator.py's replay
bookkeeping) -- it exists so candidate-occurrence identity is deterministic and
testable ahead of a future, separately-scoped decision about whether/how to migrate
proposals/lifecycle.py's store keying from setup_id (setup-family-scoped) to
candidate_occurrence_id (occurrence-scoped).

Three identity layers, kept distinct (do not collapse them):

  SETUP_FAMILY_ID        = proposals.identity.setup_id(...) -- reused unchanged.
  ELIGIBILITY_INTERVAL_ID = eligibility_interval_id() below -- one of possibly several
                            disjoint [start, end) windows a single setup family can have
                            (historical_replay.stage1.QualifiedEEvent.eligibility_intervals).
  CANDIDATE_OCCURRENCE_ID = candidate_occurrence_id() below -- composes the above two
                            with the M-model's own structural source_id (see
                            entry_confirmation's M1Result/M2Result/M3Result.source_id).

All three use the same deterministic-hash convention already established by
proposals/identity.py::setup_id and historical_replay/stage1.py::_make_event_id
(blake2b, no transient/wall-clock/random input) -- no new hashing infrastructure.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Optional


def eligibility_interval_id(event_id: str, interval_start: datetime, interval_end: datetime) -> str:
    """One of a QualifiedEEvent's (possibly several, disjoint, non-monotonic per C12)
    eligibility_intervals, identified by its own [start, end) bounds -- market/event
    timestamps only, never wall-clock or poll time. Deterministic: same event_id +
    same interval bounds always produce the same id, across continuous evaluation,
    restart, and replay."""
    digest = hashlib.blake2b(
        f"{event_id}|{interval_start.isoformat()}|{interval_end.isoformat()}".encode("utf-8"),
        digest_size=8,
    ).hexdigest()
    return f"INTERVAL-{digest}"


def candidate_occurrence_id(
    setup_family_id: str, eligibility_interval_id_: str, m_candidate_identity: Optional[str],
) -> str:
    """Composes the three identity layers. `m_candidate_identity` is the M-model's own
    structural source_id (M1Result/M2Result/M3Result.source_id) -- None only when no
    concrete M-candidate has formed yet (e.g. still WAITING_HTF_TOUCH), in which case
    this still produces a deterministic id scoped to "no candidate yet" rather than
    colliding with a later, real candidate under the same family+interval.

    setup_family_id already encodes symbol/combination/direction/reference_key
    (proposals.identity.setup_id) -- not duplicated here."""
    digest = hashlib.blake2b(
        f"{setup_family_id}|{eligibility_interval_id_}|{m_candidate_identity or 'NONE'}".encode("utf-8"),
        digest_size=10,
    ).hexdigest()
    return f"OCCURRENCE-{digest}"
