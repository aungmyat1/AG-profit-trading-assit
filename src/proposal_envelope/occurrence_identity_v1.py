"""AG_PROPOSAL_OCCURRENCE_IDENTITY_V1 -- versioned CANDIDATE occurrence identity for
canonical proposals (AG_VERSIONED_PROPOSAL_OCCURRENCE_IDENTITY_V1).

WHAT THIS SOLVES
----------------
`state/proposal_ledger/proposal_ledger.json` holds 69 records for only 13 distinct
logical setups (56 duplicate records, 5.31x inflation), because the weekday scheduler
re-observes the SAME unchanged setup at every M15 close:

  `post_asian_pilot.decision._decision_id` hashes `evaluation_time`
    -> a fresh `decision_id` every poll
    -> `proposal_envelope.adapters.fx_adapter` builds `proposal_envelope_id =
       f"FX:{decision.decision_id}"` -- a fresh envelope id every poll
    -> `ProposalLedger.record_proposal` keys on that envelope id, and its geometry-match
       idempotency only fires for the SAME key, so it never triggers across polls
    -> ONE NEW LEDGER RECORD EVERY 15 MINUTES for an unchanged setup.

That is a LAYER COLLAPSE: PROPOSAL identity was derived from OBSERVATION identity, so
the most volatile layer became the persistence key and LOGICAL SETUP identity (already
canonical, already persisted as `confirmation_evidence.setup_id`) was never used for
deduplication.

THREE LAYERS, KEPT DISTINCT (P1)
--------------------------------
  1. EVALUATION / DECISION IDENTITY -- `evaluation_id`. "Which single deterministic
     analysis pass produced this." Varies every poll BY DESIGN. Never a persistence key.
  2. LOGICAL SETUP OCCURRENCE IDENTITY -- `occurrence_id`. "Which underlying setup
     occurrence is this." Stable across every poll of the same unchanged structural
     setup; a genuinely new setup yields a new occurrence.
  3. PROPOSAL-ENVELOPE IDENTITY -- `proposal_envelope_id`. "Which persisted canonical
     proposal record." Today derived from (1); this candidate derives it from (2).

OCCURRENCE COMPOSITION -- and what is deliberately NOT in it
-----------------------------------------------------------
`occurrence_id = H(strategy_id | strategy_version | logical_setup_id | structural_reference)`

  * `logical_setup_id` is the AUTHORITATIVE canonical field
    (`confirmation_evidence.setup_id`, shape `strategy:cycle:symbol:trading_date`). The
    session and trading-date separations required by this mission are therefore
    structural properties of the key, not extra rules.
  * `strategy_version` is included for the same demonstrated reason
    `ticket_delivery.identity.logical_ticket_id` documents: the canonical `setup_id` has
    no version component, so a strategy-version bump on the same calendar date for the
    same cycle/symbol would otherwise collide with the prior version's occurrence.
  * `structural_reference` is the signed structural anchor the setup qualified on --
    reusing `proposals.identity.reference_key_for`'s EXISTING convention verbatim
    (`reference_type|reference_low|reference_high|reference_level`) rather than inventing
    a fourth key scheme. For the FX adapter this is the `liquidity_evidence`
    trigger_type/level/timeframe triple, which is verified byte-stable across all 11
    duplicate records of the worst-case real setup.
  * `evaluation_time` / `detected_at` / `data_version` / `market_data_asof` are ABSENT BY
    CONSTRUCTION. They are observation-layer fields; including any of them would
    reproduce the very collapse this module exists to remove. A test asserts this.

This module deliberately does NOT adopt `proposals/occurrence_identity.py`'s
`candidate_occurrence_id`, which the mission warns against assuming is a drop-in
solution: that contract composes `SETUP_FAMILY_ID + ELIGIBILITY_INTERVAL_ID +
m_candidate_identity` for the Large-SMC/entry-confirmation family (whose
`eligibility_intervals` are disjoint replay windows) and has no authoritative producer
for the FX `post_asian_pilot` family at all. It is left entirely untouched.

GOVERNED BOUNDARY -- what this module does NOT do
-------------------------------------------------
Additive only. It does NOT modify `_decision_id`, `fx_adapter`'s `proposal_envelope_id`,
`ProposalLedger`'s keying, or any adapter's field mapping. Those are frozen canonical
behavior with historical evidence attributed to them (AGENTS.md "Frozen strategy version
preservation"); a behavior-changing correction must land as a new versioned candidate
promoted only after explicit validation. Nothing here is imported by any runtime path
yet -- see `WIRED_INTO_RUNTIME`, which is False and asserted by test.

It changes NO strategy economics: no entry, stop, target, risk, sizing, setup filter, or
strategy-YAML value is read for a decision here. It carries `execution_authority` through
verbatim and can never grant one (it is a pure identity/persistence layer).

It never rewrites historical evidence: `record_observation` appends to a NEW
occurrence-scoped ledger; it does not touch, migrate, or reattribute
`state/proposal_ledger/proposal_ledger.json`.

FAIL-CLOSED RULE
-----------------
Logical setup identity is taken ONLY from the authoritative `confirmation_evidence.setup_id`
field. A record whose family does not emit that field raises
`OccurrenceIdentityUnavailable` -- it is never given a guessed or derived key, and it is
never silently folded into a synthetic "unknown" bucket. This is deliberately STRICTER
than the read-only audit's documented `DERIVED_SSC_COMPOSITE` fallback: deriving an
identity is acceptable for measuring an audit, but NOT for creating an authoritative
persistence key. `proposal_envelope.adapters.ssc_adapter` (which emits no
`confirmation_evidence.setup_id`) therefore reports
`OCCURRENCE_IDENTITY_UNAVAILABLE` and is excluded from occurrence counts rather than
being mis-keyed.

Every function here is PURE with respect to identity: no wall clock, no randomness, no
I/O. `now` is an explicit parameter wherever time matters. Same inputs -> same ids across
repeated evaluation, process restart, and replay.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from runtime_state.store import JsonKeyValueStore

from .models import (
    PROPOSAL_EXPIRED,
    PROPOSAL_READY,
    CanonicalProposal,
)

CANDIDATE_VERSION = "AG_PROPOSAL_OCCURRENCE_IDENTITY_V1"
OCCURRENCE_LEDGER_SCHEMA_VERSION = "AG_PROPOSAL_OCCURRENCE_LEDGER_V1"
DEFAULT_OCCURRENCE_LEDGER_PATH = "state/proposal_ledger/proposal_occurrence_ledger.json"

# --------------------------------------------------------------- P2 CUTOVER DESIGN
# Forward-only versioned cutover. The frozen ledger is NEVER migrated, rewritten, or
# reattributed -- its 69 records remain byte-identical historical evidence forever.
#
#   LEGACY  : `state/proposal_ledger/proposal_ledger.json`
#             keyed by `proposal_envelope_id = f"FX:{decision_id}"` (observation-derived).
#             Read-only from here on. Every record is an IMMUTABLE RAW OBSERVATION.
#   V1      : `state/proposal_ledger/proposal_occurrence_ledger.json`
#             keyed by `FXOCC:{strategy_id}:{occurrence_id}` (occurrence-derived).
#             Written only from the cutover instant forward.
#
# The two ledgers coexist; nothing reads LEGACY as an occurrence population, and nothing
# writes V1 into LEGACY. The cutover instant is an explicit, persisted, auditable marker
# -- never inferred from "the newest record", which would silently reclassify history.
LEDGER_GENERATION_LEGACY = "LEGACY"
LEDGER_GENERATION_V1 = "V1"
LEDGER_GENERATION_MARKER_FILENAME = "proposal_occurrence_ledger.cutover.json"
DEFAULT_CUTOVER_MARKER_PATH = f"state/proposal_ledger/{LEDGER_GENERATION_MARKER_FILENAME}"

# The exact, machine-readable version marker written on every V1 record. A reader can
# always answer "which generation produced this?" from the record alone.
CUTOVER_POLICY = {
    "legacy_path": "state/proposal_ledger/proposal_ledger.json",
    "legacy_generation": LEDGER_GENERATION_LEGACY,
    "legacy_treatment": "IMMUTABLE_RAW_OBSERVATION",
    "v1_path": DEFAULT_OCCURRENCE_LEDGER_PATH,
    "v1_generation": LEDGER_GENERATION_V1,
    "v1_treatment": "OCCURRENCE_AWARE",
    "retroactive_rewrite": False,
    "reattribution": False,
    "migration": "NONE",
}


# Explicit, machine-checkable: this candidate is NOT wired into any runtime path. Flipping
# this to True is a promotion decision that requires validation + registry/ledger
# authorization, not a code change alone (AGENTS.md).
WIRED_INTO_RUNTIME = False

REASON_IDENTITY_UNAVAILABLE = "OCCURRENCE_IDENTITY_UNAVAILABLE"
REASON_EXPIRED_AT_PRESENTATION = "EXPIRED_AT_PRESENTATION"
REASON_MISSING_EXPIRY = "MISSING_EXPIRY_EVIDENCE"


class OccurrenceIdentityUnavailable(RuntimeError):
    """The record's family does not supply the authoritative logical-setup identity
    input. Fail closed: report, never guess and never bucket into a synthetic key."""


# --------------------------------------------------------------------------- identity


def structural_reference_from_evidence(
    liquidity_evidence: Optional[Dict[str, Any]] = None,
    setup_evidence: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """The signed structural anchor, using `proposals.identity.reference_key_for`'s
    EXISTING convention (`type|low|high|level`) -- one reference-key convention in this
    repo, not two.

    Resolution order is family-scoped and explicit; nothing is guessed:
      1. `liquidity_evidence` trigger_type/trigger_level/trigger_timeframe (the FX
         adapter's shape -- the swept liquidity level a `LIQUIDITY_SWEEP` setup
         qualified on);
      2. `setup_evidence` reference_type/reference_low/reference_high/reference_level
         (the shape `proposals.identity.reference_key_for` already defines).
    Returns None when neither shape is present -- the caller then has an
    incomplete identity input and must fail closed, not compose a partial key."""
    from proposals.identity import reference_key_for

    if liquidity_evidence:
        trigger_type = liquidity_evidence.get("trigger_type")
        trigger_level = liquidity_evidence.get("trigger_level")
        trigger_timeframe = liquidity_evidence.get("trigger_timeframe")
        if trigger_type is not None or trigger_level is not None:
            return reference_key_for(trigger_type, trigger_level, None, trigger_timeframe)

    if setup_evidence:
        fields = ("reference_type", "reference_low", "reference_high", "reference_level")
        if any(setup_evidence.get(f) is not None for f in fields):
            return reference_key_for(*(setup_evidence.get(f) for f in fields))

    return None


def occurrence_id(
    *, strategy_id: str, strategy_version: str, logical_setup_id: str,
    structural_reference: Optional[str],
) -> str:
    """LAYER 2. Deterministic and stable across every poll of the same unchanged
    structural setup; a new setup (different cycle, symbol, trading date, strategy
    version, or structural reference) produces a new occurrence.

    Fails closed on any missing input rather than composing a weaker key: a partially
    identified occurrence is exactly the failure mode this candidate removes."""
    for name, value in (("strategy_id", strategy_id), ("strategy_version", strategy_version),
                        ("logical_setup_id", logical_setup_id)):
        if not value:
            raise OccurrenceIdentityUnavailable(
                f"{REASON_IDENTITY_UNAVAILABLE}: {name} is required to compose an "
                "occurrence identity and was empty")
    if structural_reference is None:
        raise OccurrenceIdentityUnavailable(
            f"{REASON_IDENTITY_UNAVAILABLE}: no structural reference could be resolved "
            "from liquidity_evidence or setup_evidence -- refusing to compose a "
            "time-varying or partial occurrence key")

    digest = hashlib.blake2b(
        f"{strategy_id}|{strategy_version}|{logical_setup_id}|{structural_reference}".encode("utf-8"),
        digest_size=10,
    ).hexdigest()
    return f"OCCURRENCE-{digest}"


def evaluation_id(envelope: CanonicalProposal) -> str:
    """LAYER 1. "Which single deterministic analysis pass produced this."

    Read from the envelope's OWN persisted fields -- never recomputed, never a new
    hashing scheme. The FX adapter sets `source_record_id = decision.decision_id` (which
    hashes `evaluation_time`, so it varies every poll BY DESIGN) and
    `data_provenance.data_version = decision.session_snapshot_id`; those are exactly the
    observation-layer fields this layer is supposed to expose."""
    provenance = getattr(envelope, "data_provenance", None)
    data_version = getattr(provenance, "data_version", None)
    parts = [p for p in (getattr(envelope, "source_record_id", None), data_version) if p]
    if not parts:
        raise OccurrenceIdentityUnavailable(
            f"{REASON_IDENTITY_UNAVAILABLE}: envelope {envelope.proposal_envelope_id!r} "
            "carries neither source_record_id nor data_provenance.data_version, so its "
            "evaluation identity cannot be resolved")
    return "EVALUATION-" + hashlib.blake2b("|".join(parts).encode("utf-8"), digest_size=8).hexdigest()


def proposal_envelope_id_for(*, strategy_id: str, occurrence_id_: str) -> str:
    """LAYER 3. Occurrence-scoped proposal-envelope identity: one logical occurrence ->
    one canonical proposal record, regardless of how many M15 observations produced it.

    Namespaced by `strategy_id` so two strategies can never collide on a shared
    occurrence key, and prefixed `FXOCC:` (a distinct namespace from the frozen
    `FX:{decision_id}` form) so a candidate-produced id can never be mistaken for a
    frozen-path id when the two coexist during validation."""
    if not strategy_id or not occurrence_id_:
        raise OccurrenceIdentityUnavailable(
            f"{REASON_IDENTITY_UNAVAILABLE}: strategy_id and occurrence_id are both "
            "required to compose a proposal-envelope identity")
    return f"FXOCC:{strategy_id}:{occurrence_id_}"


@dataclass(frozen=True)
class OccurrenceIdentity:
    """The three layers resolved for one persisted canonical proposal."""

    evaluation_id: str
    occurrence_id: str
    proposal_envelope_id: str
    logical_setup_id: str
    structural_reference: str
    strategy_version: str
    observed_at: Optional[str] = None  # observation-layer timestamp, carried but never keyed


def resolve_occurrence_identity(envelope: CanonicalProposal) -> OccurrenceIdentity:
    """Pure: one envelope -> its three layers. Raises `OccurrenceIdentityUnavailable`
    (fail closed) for any family that does not supply an authoritative
    `confirmation_evidence.setup_id`."""
    confirmation = envelope.confirmation_evidence or {}
    logical_setup_id = confirmation.get("setup_id")
    if not logical_setup_id:
        raise OccurrenceIdentityUnavailable(
            f"{REASON_IDENTITY_UNAVAILABLE}: {envelope.proposal_envelope_id!r} "
            f"(source_module={envelope.source_module!r}) emits no "
            "confirmation_evidence.setup_id -- the authoritative logical-setup identity "
            "input. Refusing to derive a persistence key; this family is excluded from "
            "occurrence identity until it supplies one.")

    reference = structural_reference_from_evidence(
        envelope.liquidity_evidence, envelope.setup_evidence)
    occurrence = occurrence_id(
        strategy_id=envelope.strategy_id, strategy_version=envelope.strategy_version,
        logical_setup_id=logical_setup_id, structural_reference=reference)

    return OccurrenceIdentity(
        evaluation_id=evaluation_id(envelope),
        occurrence_id=occurrence,
        proposal_envelope_id=proposal_envelope_id_for(
            strategy_id=envelope.strategy_id, occurrence_id_=occurrence),
        logical_setup_id=logical_setup_id,
        structural_reference=reference,
        strategy_version=envelope.strategy_version,
        observed_at=envelope.timestamps.detected_at,
    )


# ----------------------------------------------------------------------------- expiry


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def expiry_of(envelope: CanonicalProposal) -> Optional[datetime]:
    """The strategy-owned lifecycle expiry. `plan_expires_at` is the canonical field
    (both the FX and BTC adapters populate it from the source strategy's own
    `valid_until` / `expiry`); `timestamps.expires_at` is the same value on the
    occurrence timeline. Never invented -- None when the source strategy defined none."""
    return _parse_iso(envelope.plan_expires_at) or _parse_iso(envelope.timestamps.expires_at)


def is_expired(envelope: CanonicalProposal, now: datetime) -> bool:
    """True only when a strategy-owned expiry EXISTS and has passed. A record with no
    expiry evidence is never reported expired (that would be inventing a lifecycle rule
    the source strategy never defined)."""
    expiry = expiry_of(envelope)
    return expiry is not None and now >= expiry


def with_presentation_state(
    envelope: CanonicalProposal, now: datetime,
) -> CanonicalProposal:
    """P3 -- presentation-time lifecycle enforcement.

    A PROPOSAL_READY record whose strategy-owned expiry has passed must not remain
    operationally presented as a current READY proposal. This downgrades the PRESENTED
    state only; the persisted record is never modified (see
    `ProposalOccurrenceLedger`, which keeps it immutable and flags `expired_at_presentation`
    instead).

    Only ever narrows READY -> EXPIRED -- it never upgrades any state, and it never
    touches direction/entry/stop/targets, so no strategy economics are altered by an
    expiry check."""
    if envelope.proposal_state != PROPOSAL_READY or not is_expired(envelope, now):
        return envelope
    return dataclasses.replace(
        envelope, proposal_state=PROPOSAL_EXPIRED,
        reasons=envelope.reasons + (REASON_EXPIRED_AT_PRESENTATION,),
    )


# ----------------------------------------------------------------- occurrence ledger


def _observation_record(envelope: CanonicalProposal, identity: OccurrenceIdentity,
                        now: Optional[datetime]) -> Dict[str, Any]:
    """Every observation's provenance, preserved in full -- the mission requires that
    repeated observations resolve to one occurrence WITHOUT losing any observation's
    evidence. Nothing here is summarized away."""
    return {
        "evaluation_id": identity.evaluation_id,
        "proposal_envelope_id": envelope.proposal_envelope_id,
        "observed_at": identity.observed_at,
        "last_evaluated_at": envelope.timestamps.last_evaluated_at,
        "data_version": envelope.data_provenance.data_version,
        "market_data_asof": envelope.data_provenance.market_data_asof,
        "market_data_mode": envelope.data_provenance.market_data_mode,
        "market_data_fingerprint": envelope.data_provenance.market_data_fingerprint,
        "direction": envelope.direction, "entry": envelope.entry, "stop": envelope.stop,
        "targets": list(envelope.targets),
        "watcher_state": envelope.watcher_state,
        "recorded_at": now.isoformat() if now is not None else None,
    }


def _geometry(envelope: CanonicalProposal) -> Tuple[Any, Any, Any, Tuple[Any, ...]]:
    return (envelope.direction, envelope.entry, envelope.stop, tuple(envelope.targets))


class OccurrenceLedgerError(RuntimeError):
    pass


class ProposalOccurrenceLedger:
    """Occurrence-scoped persistence for canonical proposals (candidate; unwired).

    One logical occurrence -> ONE proposal record, however many M15 observations produced
    it, with every observation's provenance preserved in `observations`.

    Semantics, all deliberate:
      * geometry-stable repetition is IDEMPOTENT -- an observation whose geometry matches
        the current record appends provenance only and leaves the record byte-identical
        apart from that provenance. No version bump, no correction, no duplicate record;
      * a genuinely NEW setup produces a NEW occurrence record (different occurrence key);
      * geometry CHANGE within one occurrence is a LINKED CORRECTION (`version`
        incremented, `correction_of` set, prior record kept in `history`) -- mirroring
        `ProposalLedger`'s existing, already-tested convention exactly rather than
        inventing a second one;
      * restart-safety comes from `runtime_state.store.JsonKeyValueStore` verbatim (the
        repo's established atomic, path-locked persistence primitive) -- no new storage
        mechanism;
      * the record is IMMUTABLE with respect to historical evidence: existing observation
        entries and history entries are never rewritten or dropped.
    """

    def __init__(self, path: str = DEFAULT_OCCURRENCE_LEDGER_PATH):
        self._store = JsonKeyValueStore(path)

    def record_observation(
        self, envelope: CanonicalProposal, now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        if envelope.proposal_state != PROPOSAL_READY:
            raise OccurrenceLedgerError(
                f"OCCURRENCE_LEDGER_REJECTED_NON_READY: proposal_state="
                f"{envelope.proposal_state!r} -- only PROPOSAL_READY envelopes are "
                "recorded, matching ProposalLedger's own rule so evaluation evidence "
                "never inflates the proposal population")

        identity = resolve_occurrence_identity(envelope)  # raises -> fail closed
        key = identity.proposal_envelope_id
        observation = _observation_record(envelope, identity, now)
        entry = self._store.get(key)

        if entry is None:
            record = {
                "schema_version": OCCURRENCE_LEDGER_SCHEMA_VERSION,
                "occurrence_id": identity.occurrence_id,
                "proposal_envelope_id": key,
                "logical_setup_id": identity.logical_setup_id,
                "structural_reference": identity.structural_reference,
                "strategy_id": envelope.strategy_id,
                "strategy_version": envelope.strategy_version,
                "symbol": envelope.symbol,
                "version": 1,
                "correction_of": None,
                "plan_expires_at": envelope.plan_expires_at,
                "expires_at": envelope.timestamps.expires_at,
                "expired_at_presentation": False,
                "observation_count": 1,
                "first_observed_at": observation["observed_at"],
                "last_observed_at": observation["observed_at"],
                "current": dataclasses.asdict(envelope),
                "observations": [observation],
                "history": [],
            }
            self._store.put(key, record)
            return record

        record = dict(entry)
        record["observations"] = list(entry["observations"])
        record["history"] = list(entry["history"])

        if _geometry(_from_current(entry["current"])) == _geometry(envelope):
            # Geometry-stable repetition: idempotent. Provenance is appended; the record
            # (and its version/history) is otherwise untouched.
            record["observations"].append(observation)
            record["observation_count"] = len(record["observations"])
            record["last_observed_at"] = observation["observed_at"]
            self._store.put(key, record)
            return record

        # Geometry changed within the SAME occurrence -> linked correction.
        corrected = dataclasses.replace(
            envelope, version=int(entry.get("version", 1)) + 1, correction_of=key,
        )
        record["history"] = list(entry["history"]) + [entry["current"]]
        record["observations"].append(observation)
        record["observation_count"] = len(record["observations"])
        record["last_observed_at"] = observation["observed_at"]
        record["version"] = corrected.version
        record["correction_of"] = corrected.correction_of
        record["plan_expires_at"] = corrected.plan_expires_at
        record["expires_at"] = corrected.timestamps.expires_at
        record["current"] = dataclasses.asdict(corrected)
        self._store.put(key, record)
        return record

    def mark_expired_at_presentation(self, proposal_envelope_id: str, now: datetime) -> bool:
        """Flag (never rewrite) that a persisted READY record has passed its
        strategy-owned expiry. Returns True when the flag was set. The `current` record
        itself is left exactly as persisted -- historical evidence is immutable."""
        entry = self._store.get(proposal_envelope_id)
        if entry is None:
            return False
        if entry.get("expired_at_presentation"):
            return False
        record = dict(entry)
        if not is_expired(_from_current(entry["current"]), now):
            return False
        record["expired_at_presentation"] = True
        self._store.put(proposal_envelope_id, record)
        return True

    def get_occurrence(self, proposal_envelope_id: str) -> Optional[Dict[str, Any]]:
        return self._store.get(proposal_envelope_id)

    def all_occurrences(self) -> List[Dict[str, Any]]:
        return list(self._store.all().values())


def _from_current(record: Dict[str, Any]) -> CanonicalProposal:
    """Rebuild just enough of the envelope to compare geometry and read expiry. Only the
    fields this module reads are reconstructed; the persisted dict is the source of
    truth and is never mutated."""
    from .models import CostAssumptions, DataProvenance, WatcherOccurrenceTimestamps

    data = dict(record)
    data["data_provenance"] = DataProvenance(**(data.get("data_provenance") or {}))
    data["cost_assumptions"] = CostAssumptions(**(data.get("cost_assumptions") or {}))
    data["timestamps"] = WatcherOccurrenceTimestamps(**(data.get("timestamps") or {}))
    data["targets"] = tuple(data.get("targets") or ())
    data["reasons"] = tuple(data.get("reasons") or ())
    return CanonicalProposal(**data)


# ----------------------------------------------------------------- reporting metrics


@dataclass(frozen=True)
class OccurrenceReportingMetrics:
    """P4 -- six distinct reporting metrics. Deliberately separate fields, never one
    number:

      OBSERVATION_COUNT                  -- every persisted analysis observation (the raw
                                            record count)
      DISTINCT_AUTHORITATIVE_SETUP_COUNT -- distinct logical setups whose identity came
                                            from the authoritative `setup_id` field
      DISTINCT_OCCURRENCE_COUNT          -- distinct logical occurrences
      IDENTITY_UNAVAILABLE_COUNT         -- records with no authoritative identity input
      CURRENT_ACTIVE_PROPOSAL_COUNT      -- occurrences NOT expired at `now`
      EXPIRED_PROPOSAL_COUNT             -- occurrences expired at `now`

    `opportunity_count` is exposed as `CURRENT_ACTIVE_PROPOSAL_COUNT` ONLY -- a raw
    record count must never be presented as a trade-opportunity count."""

    observation_count: int
    distinct_authoritative_setup_count: int
    distinct_occurrence_count: int
    current_active_proposal_count: int
    expired_proposal_count: int
    identity_unavailable_count: int = 0
    presentation_ready_count: int = 0

    @property
    def distinct_setup_count(self) -> int:
        """Alias kept for callers written against the earlier field name -- the same
        number, never a second computation."""
        return self.distinct_authoritative_setup_count

    @property
    def opportunity_count(self) -> int:
        """The only sanctioned "how many trade opportunities" figure."""
        return self.current_active_proposal_count

    def as_dict(self) -> Dict[str, int]:
        return {
            "OBSERVATION_COUNT": self.observation_count,
            "DISTINCT_AUTHORITATIVE_SETUP_COUNT": self.distinct_authoritative_setup_count,
            "DISTINCT_OCCURRENCE_COUNT": self.distinct_occurrence_count,
            "CURRENT_ACTIVE_PROPOSAL_COUNT": self.current_active_proposal_count,
            "EXPIRED_PROPOSAL_COUNT": self.expired_proposal_count,
            "IDENTITY_UNAVAILABLE_COUNT": self.identity_unavailable_count,
        }

    def render(self) -> str:
        """Human-readable rendering that states explicitly what is NOT the opportunity
        count, so a reader cannot mistake the raw record count for it."""
        return (
            f"OBSERVATION_COUNT={self.observation_count} (raw persisted records -- NOT a "
            f"trade-opportunity count)\n"
            f"DISTINCT_AUTHORITATIVE_SETUP_COUNT={self.distinct_authoritative_setup_count}\n"
            f"DISTINCT_OCCURRENCE_COUNT={self.distinct_occurrence_count}\n"
            f"CURRENT_ACTIVE_PROPOSAL_COUNT={self.current_active_proposal_count} "
            f"(= opportunity count)\n"
            f"EXPIRED_PROPOSAL_COUNT={self.expired_proposal_count}\n"
            f"IDENTITY_UNAVAILABLE_COUNT={self.identity_unavailable_count}"
        )


def reporting_metrics(
    envelopes: Iterable[CanonicalProposal], now: datetime,
) -> OccurrenceReportingMetrics:
    """Pure. Counts each layer separately; never collapses them into one figure.

    `observation_count` is one per supplied record (each persisted record IS one
    observation). `distinct_authoritative_setup_count` / `distinct_occurrence_count`
    group by the authoritative logical setup id and the occurrence id respectively.

    IDENTITY GATE, applied once and consistently: a record whose authoritative identity
    is unavailable is counted ONLY in `identity_unavailable_count` and is excluded from
    every other figure. This is the single gate -- `presentation_ready_count` and
    `current_proposals`/`expired_proposals` apply the same rule, so no metric can
    disagree with another about which records are in scope.

    `current_active_proposal_count` counts in-scope occurrences NOT expired at `now`;
    `expired_proposal_count` counts those that ARE. The two are complementary and
    together with `identity_unavailable_count` account for `observation_count` exactly
    once."""
    observations = 0
    setups = set()
    occurrences = set()
    active = 0
    expired = 0
    unavailable = 0
    ready_presented = 0

    for envelope in envelopes:
        observations += 1
        try:
            identity = resolve_occurrence_identity(envelope)
        except OccurrenceIdentityUnavailable:
            unavailable += 1
            continue
        setups.add(identity.logical_setup_id)
        occurrences.add(identity.occurrence_id)
        if is_expired(envelope, now):
            expired += 1
        else:
            active += 1
        if with_presentation_state(envelope, now).proposal_state == PROPOSAL_READY:
            ready_presented += 1

    return OccurrenceReportingMetrics(
        observation_count=observations,
        distinct_authoritative_setup_count=len(setups),
        distinct_occurrence_count=len(occurrences),
        current_active_proposal_count=active,
        expired_proposal_count=expired,
        identity_unavailable_count=unavailable,
        presentation_ready_count=ready_presented,
    )


def reporting_metrics_from_ledger_file(
    path: str = "state/proposal_ledger/proposal_ledger.json", now: Optional[datetime] = None,
) -> OccurrenceReportingMetrics:
    """Read-only metrics over an existing `ProposalLedger` JSON file. Never writes."""
    now = now or datetime.now(timezone.utc)
    return reporting_metrics(_read_envelopes(path), now)


def presentation_ready_count(
    envelopes: Iterable[CanonicalProposal], now: datetime,
) -> int:
    """How many records are STILL presented as `PROPOSAL_READY` after read-time expiry is
    applied. This is the number an operational status surface must report -- never
    `len(list_active_proposals())`, which counts expired records as active.

    Applies the same identity gate as `reporting_metrics`, so it can never disagree with
    `CURRENT_ACTIVE_PROPOSAL_COUNT` about scope."""
    return sum(
        1 for e in _in_scope(envelopes)
        if with_presentation_state(e, now).proposal_state == PROPOSAL_READY
    )


def presentation_ready_count_from_ledger_file(
    path: str = "state/proposal_ledger/proposal_ledger.json", now: Optional[datetime] = None,
) -> int:
    """Read-only: the expiry-corrected current-proposal count for an existing
    `ProposalLedger` JSON file. Never writes."""
    now = now or datetime.now(timezone.utc)
    return presentation_ready_count(_read_envelopes(path), now)


def _read_envelopes(path: str) -> List[CanonicalProposal]:
    ledger_path = Path(path)
    if not ledger_path.exists():
        return []
    raw = json.loads(ledger_path.read_text(encoding="utf-8"))
    return [
        _from_current(entry["current"]) for entry in raw.values()
        if isinstance(entry, dict) and "current" in entry
    ]


def _in_scope(envelopes: Iterable[CanonicalProposal]) -> List[CanonicalProposal]:
    """The ONE identity gate every presentation/reporting view shares: a record is in
    scope only when its authoritative logical-setup identity resolves. Records that fail
    closed are never silently presented as current, and never counted as setups or
    occurrences -- they are reported through `identity_unavailable_count` alone."""
    in_scope: List[CanonicalProposal] = []
    for envelope in envelopes:
        try:
            resolve_occurrence_identity(envelope)
        except OccurrenceIdentityUnavailable:
            continue
        in_scope.append(envelope)
    return in_scope


def current_proposals(
    envelopes: Iterable[CanonicalProposal], now: datetime,
) -> List[CanonicalProposal]:
    """P3 -- the ONLY sanctioned "what is currently presented" list.

    Returns in-scope occurrences that are NOT expired at `now`, with the presentation
    state applied. An expired proposal is excluded, so it can never remain operationally
    presented as a current `PROPOSAL_READY` (the confirmed defect: the frozen
    `ProposalLedger.list_active_proposals()` returns all 69 persisted records, 63 of
    which had already passed their strategy-owned expiry).

    A record whose authoritative identity is unavailable is excluded here too -- the same
    gate `reporting_metrics` applies -- so an unresolvable record can never be presented
    as a current proposal. `expired_proposals()` and `identity_unavailable_proposals()`
    are the complementary views, so nothing is hidden.

    This is a read-time VIEW over immutable persisted records -- it rewrites nothing, so
    historical/auditable history is fully preserved and remains available via
    `ProposalLedger.get_history()`."""
    return [
        with_presentation_state(e, now) for e in _in_scope(envelopes)
        if not is_expired(e, now)
    ]


def expired_proposals(
    envelopes: Iterable[CanonicalProposal], now: datetime,
) -> List[CanonicalProposal]:
    """The complementary, explicitly-separated expired view -- expired records stay
    auditable and are never deleted or rewritten, they are simply not presented as
    current."""
    return [e for e in _in_scope(envelopes) if is_expired(e, now)]


def identity_unavailable_proposals(
    envelopes: Iterable[CanonicalProposal],
) -> List[CanonicalProposal]:
    """The third, explicitly-separated view: records excluded because their authoritative
    identity is unavailable (e.g. the `ssc_adapter` family). Exposed so the exclusion is
    auditable rather than invisible -- this mission does NOT invent an identity for them."""
    out: List[CanonicalProposal] = []
    for envelope in envelopes:
        try:
            resolve_occurrence_identity(envelope)
        except OccurrenceIdentityUnavailable:
            out.append(envelope)
    return out


def current_proposals_from_ledger_file(
    path: str = "state/proposal_ledger/proposal_ledger.json", now: Optional[datetime] = None,
) -> List[CanonicalProposal]:
    """Read-only: the current (non-expired) proposal population from an existing
    `ProposalLedger` JSON file. Never writes."""
    now = now or datetime.now(timezone.utc)
    return current_proposals(_read_envelopes(path), now)


def expired_proposals_from_ledger_file(
    path: str = "state/proposal_ledger/proposal_ledger.json", now: Optional[datetime] = None,
) -> List[CanonicalProposal]:
    """Read-only: the expired proposal population from an existing `ProposalLedger` JSON
    file. Never writes."""
    now = now or datetime.now(timezone.utc)
    return expired_proposals(_read_envelopes(path), now)


# ----------------------------------------------------------------- cutover marker


def read_cutover_marker(path: str = DEFAULT_CUTOVER_MARKER_PATH) -> Optional[Dict[str, Any]]:
    """The persisted, auditable cutover marker, or None when no cutover has been
    recorded. Read-only -- never creates the file."""
    marker_path = Path(path)
    if not marker_path.exists():
        return None
    try:
        return json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_cutover_marker(
    *, cutover_at: datetime, path: str = DEFAULT_CUTOVER_MARKER_PATH,
    note: Optional[str] = None,
) -> Dict[str, Any]:
    """Record the forward-only cutover instant. Explicit and auditable -- deliberately
    NOT inferred from "the newest legacy record", which would silently reclassify
    history.

    Does NOT migrate, rewrite, or reattribute any legacy record: the legacy ledger is
    left byte-identical and is henceforth read as immutable raw observations only."""
    marker = {
        "marker_version": CANDIDATE_VERSION,
        "cutover_at": cutover_at.isoformat(),
        "policy": dict(CUTOVER_POLICY),
        "note": note,
    }
    marker_path = Path(path)
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text(json.dumps(marker, indent=2, sort_keys=True), encoding="utf-8")
    return marker


def generation_of(record: Dict[str, Any]) -> str:
    """Which generation produced a persisted record. Reads the record's own marker, so a
    reader never has to guess from shape or timestamp. A record carrying the V1
    occurrence schema is V1; anything else is treated as LEGACY raw observation."""
    if record.get("schema_version") == OCCURRENCE_LEDGER_SCHEMA_VERSION:
        return LEDGER_GENERATION_V1
    return LEDGER_GENERATION_LEGACY
