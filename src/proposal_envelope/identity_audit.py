"""Proposal identity layering -- READ-ONLY audit + deterministic resolution
(AG_SCHEDULER_AND_LARGE_SMC_WATCH_HARDENING_V1, P2).

WHY THIS MODULE EXISTS (the defect it names, without changing any frozen behavior)
-----------------------------------------------------------------------------------
`state/proposal_ledger/proposal_ledger.json` currently holds 69 records for only 10
distinct logical setups. That is not a ledger bug: `ProposalLedger.record_proposal`
keys on `proposal_envelope_id` and its geometry-match idempotency only fires for the
SAME key, while `proposal_envelope.adapters.fx_adapter.to_canonical_proposal` builds
`proposal_envelope_id = f"FX:{decision.decision_id}"` and
`post_asian_pilot.decision._decision_id` hashes `evaluation_time` into its digest.
Because the weekday scheduler polls every M15 close, the SAME logical setup is
re-observed with a fresh `evaluation_time` each poll, producing a fresh
`decision_id` -> a fresh `proposal_envelope_id` -> a NEW ledger record every 15
minutes for an unchanged setup (11 records for one EURUSD LONDON_NEWYORK occurrence
on 2026-09-15 alone, all with byte-identical direction/entry/stop/targets).

THREE LAYERS, kept distinct (this module names them; it does NOT redefine them)
-------------------------------------------------------------------------------
  LOGICAL SETUP IDENTITY   -- "which underlying setup is this". Already canonical and
                              already present in every persisted record as
                              `confirmation_evidence.setup_id`
                              (`f"{strategy_id}:{cycle}:{symbol}:{trading_date}"`, the
                              shape `ticket_delivery.identity.logical_ticket_id`
                              documents and extends with one `strategy_version` field).
                              Stable across every poll of the same setup.
  OBSERVATION IDENTITY     -- "which single analysis observation produced this". Already
                              canonical as `snapshot_id`
                              (`proposals.identity.snapshot_id`), materialized on the
                              envelope as `data_provenance.data_version`
                              (`SNAPSHOT-<symbol>-<hash>`) plus
                              `data_provenance.market_data_asof` and
                              `timestamps.detected_at`. Varies every poll BY DESIGN --
                              that is exactly what it is for.
  PROPOSAL IDENTITY        -- "which persisted canonical proposal record". Canonical as
                              `proposal_envelope_id`, adopted by
                              `docs/status/AG_CANONICAL_R2_R4_WP0_BASELINE_RECONCILIATION_STATUS.md`
                              as WP7's canonical `proposal_id`.

The defect is a LAYER COLLAPSE, not a missing concept: the FX adapter derives
PROPOSAL identity from OBSERVATION identity, so the most volatile layer becomes the
persistence key and LOGICAL SETUP identity is never used for deduplication.

GOVERNED BOUNDARY -- what this module deliberately does NOT do
--------------------------------------------------------------
It does not change `_decision_id`, the FX adapter's `proposal_envelope_id`, or
`ProposalLedger`'s keying. Those are frozen canonical behavior with existing evidence
attributed to them (AGENTS.md "Frozen strategy version preservation"), and a
behavior-changing correction must land as a new versioned candidate promoted only
after validation. This module is additive and read-only: it resolves the three layers
deterministically for already-persisted records so the duplication is measurable and
testable, and so any future remediation has an authoritative, already-tested resolver
to key on instead of inventing a fourth scheme.

`resolve_identity_layers` is a PURE function of a `CanonicalProposal` -- no wall clock,
no randomness, no I/O -- so it is safe to call from replay, restart, or an audit.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

LAYER_LOGICAL_SETUP = "LOGICAL_SETUP_IDENTITY"
LAYER_OBSERVATION = "OBSERVATION_IDENTITY"
LAYER_PROPOSAL = "PROPOSAL_IDENTITY"

# The three layers, and the canonical field each is sourced from. Machine-checkable so
# a status report or test can assert the mapping without re-deriving it from prose.
IDENTITY_LAYER_SOURCES: Dict[str, str] = {
    LAYER_LOGICAL_SETUP: "confirmation_evidence.setup_id",
    LAYER_OBSERVATION: "data_provenance.data_version (proposals.identity.snapshot_id)",
    LAYER_PROPOSAL: "proposal_envelope_id (WP7 canonical proposal_id)",
}


class IdentityResolutionError(RuntimeError):
    """Raised when a record's persisted fields cannot yield a deterministic layer
    identity. Fail closed: an unresolvable record is reported, never silently bucketed
    into a synthetic 'unknown' key that would hide the gap."""


# How a record's LOGICAL SETUP identity was obtained. Recorded per record so a reader
# (or a test) can never mistake a derived key for the canonical field -- the two are
# deliberately NOT treated as interchangeable.
SOURCE_CANONICAL_SETUP_ID = "CANONICAL_SETUP_ID"
SOURCE_DERIVED_SSC_COMPOSITE = "DERIVED_SSC_COMPOSITE"


@dataclass(frozen=True)
class IdentityLayers:
    """The three layers for one persisted canonical proposal record."""

    logical_setup_id: str
    observation_id: str
    proposal_envelope_id: str
    market_data_asof: Optional[datetime]
    identity_source: str = SOURCE_CANONICAL_SETUP_ID

    @property
    def logical_identity_is_authoritative(self) -> bool:
        return self.identity_source == SOURCE_CANONICAL_SETUP_ID


def _observation_id(logical_setup_id: str, data_version: Optional[str],
                    market_data_asof: Optional[str]) -> str:
    """Deterministic observation identity. Composed from the SAME inputs the envelope
    already carries (`data_provenance.data_version` / `market_data_asof`) so this
    never disagrees with `proposals.identity.snapshot_id`'s own intent -- it names
    'this specific analysis observation', not a new concept. Falls back to
    `data_version` alone when no asof is present rather than failing, because a record
    with a data_version but no asof is still unambiguously one observation."""
    digest = hashlib.blake2b(
        f"{logical_setup_id}|{data_version or 'NONE'}|{market_data_asof or 'NONE'}".encode("utf-8"),
        digest_size=8,
    ).hexdigest()
    return f"OBSERVATION-{digest}"


def resolve_identity_layers(record: Dict[str, Any]) -> IdentityLayers:
    """Resolve the three layers from one persisted ledger record (the `current` dict of
    a `ProposalLedger` entry, or a `CanonicalProposal` serialized via
    `dataclasses.asdict`). Pure and deterministic.

    LOGICAL SETUP identity is read from the canonical field when present. The SSC
    adapter (`proposal_envelope.adapters.ssc_adapter`) is the ONE family that does not
    emit `confirmation_evidence.setup_id` -- its `setup_evidence` carries
    `campaign_id`/`session_pair`/`setup_model`/`trading_date` instead, and its
    `proposal_envelope_id` is already the fully composite
    `SSC:<symbol>|<session_pair>|<date>|<campaign>|<model>|<entry_time>` string. Those
    records therefore get a DERIVED key, explicitly flagged as such
    (`identity_source=SOURCE_DERIVED_SSC_COMPOSITE`) so it is never confused with the
    canonical field. The derivation is lossless here (the composite is already
    per-setup, so it yields 1 record per setup rather than hiding duplication), but it
    is still reported as non-authoritative.
    """
    envelope_id = record.get("proposal_envelope_id")
    if not envelope_id:
        raise IdentityResolutionError(
            "UNRESOLVABLE_PROPOSAL_IDENTITY: record has no proposal_envelope_id")

    confirmation = record.get("confirmation_evidence") or {}
    setup_evidence = record.get("setup_evidence") or {}
    logical = confirmation.get("setup_id") or setup_evidence.get("setup_id")
    identity_source = SOURCE_CANONICAL_SETUP_ID

    if not logical:
        logical = _derive_logical_setup_id(envelope_id, setup_evidence)
        identity_source = SOURCE_DERIVED_SSC_COMPOSITE
    if not logical:
        raise IdentityResolutionError(
            f"UNRESOLVABLE_LOGICAL_SETUP_IDENTITY: {envelope_id!r} carries neither "
            "confirmation_evidence.setup_id nor setup_evidence.setup_id, and no "
            "documented family composite could be derived from it")

    provenance = record.get("data_provenance") or {}
    data_version = provenance.get("data_version")
    asof_raw = provenance.get("market_data_asof")
    asof: Optional[datetime] = None
    if asof_raw:
        try:
            asof = datetime.fromisoformat(str(asof_raw))
        except ValueError:
            asof = None

    return IdentityLayers(
        logical_setup_id=logical,
        observation_id=_observation_id(logical, data_version, str(asof_raw) if asof_raw else None),
        proposal_envelope_id=envelope_id,
        market_data_asof=asof,
        identity_source=identity_source,
    )


def _derive_logical_setup_id(envelope_id: str, setup_evidence: Dict[str, Any]) -> Optional[str]:
    """Documented, family-scoped fallback for the ONE adapter that emits no
    `setup_id` (`ssc_adapter`). Returns None for any family whose composite is not
    explicitly listed here -- this function must never guess a key shape.

    `ssc_adapter.to_canonical_proposal` builds
    `f"SSC:{symbol}|{session_pair_id}|{trading_date}|{campaign_id}|{setup_model}|{entry_time}"`.
    The logical-setup key is that same composite with the volatile `entry_time` field
    dropped -- `entry_time` is what varies between two records of the same setup, so
    including it would reproduce the very collapse this module exists to expose. The
    campaign_id already pins symbol+session_pair+trading_date; setup_model pins the
    model. Requires exactly the documented field count so a future shape change fails
    loudly (returns None -> reported unresolvable) instead of silently mis-keying."""
    if not envelope_id.startswith("SSC:"):
        return None
    fields = envelope_id[len("SSC:"):].split("|")
    if len(fields) != 6:
        return None
    symbol, session_pair, trading_date, campaign_id, setup_model, _entry_time = fields
    if not all((symbol, session_pair, trading_date, setup_model)):
        return None
    return f"SSC:{symbol}:{session_pair}:{trading_date}:{campaign_id}:{setup_model}"


@dataclass(frozen=True)
class LogicalSetupSummary:
    logical_setup_id: str
    proposal_records: int
    distinct_observations: int
    distinct_geometries: int
    first_asof: Optional[datetime]
    last_asof: Optional[datetime]
    identity_source: str = SOURCE_CANONICAL_SETUP_ID

    @property
    def duplicate_records(self) -> int:
        """Records beyond the first for this logical setup -- the inflation figure."""
        return max(0, self.proposal_records - 1)

    @property
    def logical_identity_is_authoritative(self) -> bool:
        return self.identity_source == SOURCE_CANONICAL_SETUP_ID


@dataclass(frozen=True)
class LedgerIdentityAudit:
    total_records: int
    distinct_logical_setups: int
    distinct_observations: int
    duplicate_records: int
    unresolvable: Tuple[str, ...]
    per_setup: Tuple[LogicalSetupSummary, ...]
    derived_identity_records: int = 0

    @property
    def duplication_ratio(self) -> float:
        if self.distinct_logical_setups == 0:
            return 0.0
        return self.total_records / self.distinct_logical_setups

    @property
    def duplicate_proposal_problem_reproduced(self) -> bool:
        """The reported defect, as a machine-checkable predicate: more persisted
        proposal records than distinct logical setups, with every extra record for a
        setup sharing that setup's geometry (i.e. genuinely the same setup re-recorded,
        not a legitimate new setup)."""
        return self.duplicate_records > 0 and self.distinct_observations > self.distinct_logical_setups


def _geometry(record: Dict[str, Any]) -> Tuple[Any, Any, Any, Any]:
    return (record.get("direction"), record.get("entry"), record.get("stop"),
            tuple(record.get("targets") or ()))


def audit_ledger_records(records: List[Dict[str, Any]]) -> LedgerIdentityAudit:
    """Group persisted records by each of the three layers and quantify the collapse.
    Pure: takes records, returns a summary, performs no I/O and writes nothing."""
    per_setup: Dict[str, List[IdentityLayers]] = {}
    geometry_by_setup: Dict[str, set] = {}
    source_by_setup: Dict[str, str] = {}
    unresolvable: List[str] = []

    for record in records:
        try:
            layers = resolve_identity_layers(record)
        except IdentityResolutionError as exc:
            unresolvable.append(str(exc))
            continue
        per_setup.setdefault(layers.logical_setup_id, []).append(layers)
        geometry_by_setup.setdefault(layers.logical_setup_id, set()).add(_geometry(record))
        source_by_setup[layers.logical_setup_id] = layers.identity_source

    observations = {l.observation_id for layers in per_setup.values() for l in layers}

    summaries = []
    for setup_id, layers in per_setup.items():
        asofs = sorted(l.market_data_asof for l in layers if l.market_data_asof is not None)
        summaries.append(LogicalSetupSummary(
            logical_setup_id=setup_id,
            proposal_records=len(layers),
            distinct_observations=len({l.observation_id for l in layers}),
            distinct_geometries=len(geometry_by_setup[setup_id]),
            first_asof=asofs[0] if asofs else None,
            last_asof=asofs[-1] if asofs else None,
            identity_source=source_by_setup[setup_id],
        ))
    summaries.sort(key=lambda s: (-s.proposal_records, s.logical_setup_id))

    total = sum(s.proposal_records for s in summaries)
    return LedgerIdentityAudit(
        total_records=total,
        distinct_logical_setups=len(summaries),
        distinct_observations=len(observations),
        duplicate_records=sum(s.duplicate_records for s in summaries),
        unresolvable=tuple(unresolvable),
        per_setup=tuple(summaries),
        derived_identity_records=sum(
            s.proposal_records for s in summaries
            if s.identity_source == SOURCE_DERIVED_SSC_COMPOSITE),
    )


def audit_ledger_file(path: str = "state/proposal_ledger/proposal_ledger.json") -> LedgerIdentityAudit:
    """Read-only audit of a persisted `ProposalLedger` JSON file. Never writes."""
    import json

    ledger_path = Path(path)
    if not ledger_path.exists():
        return LedgerIdentityAudit(0, 0, 0, 0, (), ())
    raw = json.loads(ledger_path.read_text(encoding="utf-8"))
    records = [entry["current"] for entry in raw.values()
               if isinstance(entry, dict) and "current" in entry]
    return audit_ledger_records(records)
