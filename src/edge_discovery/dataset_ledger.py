"""Phase 12 -- append-only dataset-access ledger with role enforcement (holdout hygiene).

Every access REQUEST is recorded, granted or denied. Rules (fail closed):

  1. The requested role must be inside the candidate manifest's dataset_roles_allowed.
  2. HOLDOUT / FINAL_OOS access additionally requires an explicit, non-empty
     governance_approval_id. No approval -> DENIED (and the denial is itself recorded).
  3. A repeated GRANTED access of the same (candidate, dataset, restricted role) is
     never silently "independent OOS" again: a repeat with the SAME approval id is
     DENIED (HOLDOUT_REUSE_REQUIRES_NEW_GOVERNANCE_APPROVAL); a repeat with a new
     approval id is granted but permanently labeled NOT_INDEPENDENT_REPEAT_ACCESS with
     the running repeat count.

The ledger is JSON-lines, append-only; records are DatasetAccessRecord dataclasses.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from .models import (CandidateManifest, DatasetAccessRecord, DatasetRole, RESTRICTED_ROLES)

ROLE_NOT_ALLOWED_FOR_CANDIDATE = "ROLE_NOT_ALLOWED_FOR_CANDIDATE"
GOVERNANCE_APPROVAL_REQUIRED = "GOVERNANCE_APPROVAL_REQUIRED"
HOLDOUT_REUSE_REQUIRES_NEW_GOVERNANCE_APPROVAL = "HOLDOUT_REUSE_REQUIRES_NEW_GOVERNANCE_APPROVAL"
# The fast screen is a DEV-only falsification stage.  This remains true even if a
# caller constructs a mutated manifest and supplies a governance approval id.
FAST_SCREEN_ROLE_FORBIDDEN = "FAST_SCREEN_ROLE_FORBIDDEN"
C001_FAST_SCREEN_STAGE = "C001_FAST_SCREEN"

INDEPENDENT_FIRST_ACCESS = "INDEPENDENT_FIRST_ACCESS"
NOT_INDEPENDENT_REPEAT_ACCESS = "NOT_INDEPENDENT_REPEAT_ACCESS"


class DatasetAccessDenied(PermissionError):
    """Raised by callers (e.g. the replay adapter) when a required access is denied."""

    def __init__(self, record: DatasetAccessRecord):
        super().__init__(f"{record.denial_reason}: {record.candidate_id} -> "
                         f"{record.dataset_id} [{record.dataset_role}]")
        self.record = record


class DatasetAccessLedger:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ reading
    def records(self) -> List[DatasetAccessRecord]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            doc = json.loads(line)
            doc.pop("ledger_event", None)
            if doc.get("candidate_id") == "__GENESIS__":
                continue
            out.append(DatasetAccessRecord(**doc))
        return out

    def granted_count(self, candidate_id: str, dataset_id: str, role: str) -> int:
        return sum(1 for r in self.records()
                   if r.granted and r.candidate_id == candidate_id
                   and r.dataset_id == dataset_id and r.dataset_role == role)

    # ------------------------------------------------------------------ writing
    def _append(self, record: DatasetAccessRecord) -> DatasetAccessRecord:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(record.as_json_line() + "\n")
        return record

    def request_access(self, manifest: CandidateManifest, dataset_id: str, role: str,
                       access_reason: str, result_visibility: str,
                       governance_approval_id: Optional[str] = None,
                       now: Optional[datetime] = None,
                       access_stage: str = "UNSPECIFIED") -> DatasetAccessRecord:
        ts = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
        prior = self.granted_count(manifest.candidate_id, dataset_id, role)
        restricted = role in tuple(r.value for r in RESTRICTED_ROLES)

        def deny(reason: str) -> DatasetAccessRecord:
            return self._append(DatasetAccessRecord(
                candidate_id=manifest.candidate_id, dataset_id=dataset_id,
                dataset_role=role, access_reason=access_reason, timestamp_utc=ts,
                result_visibility="DENIED", granted=False, denial_reason=reason,
                governance_approval_id=governance_approval_id,
                repeat_access_count=prior,
                independence_claim="NOT_APPLICABLE", access_stage=access_stage))

        if role not in [r.value for r in DatasetRole]:
            return deny(f"UNKNOWN_DATASET_ROLE:{role}")
        if role not in manifest.dataset_roles_allowed:
            return deny(ROLE_NOT_ALLOWED_FOR_CANDIDATE)
        if restricted and not governance_approval_id:
            return deny(GOVERNANCE_APPROVAL_REQUIRED)
        if restricted and prior > 0:
            used_ids = {r.governance_approval_id for r in self.records()
                        if r.granted and r.candidate_id == manifest.candidate_id
                        and r.dataset_id == dataset_id and r.dataset_role == role}
            if governance_approval_id in used_ids:
                return deny(HOLDOUT_REUSE_REQUIRES_NEW_GOVERNANCE_APPROVAL)

        independence = "NOT_APPLICABLE"
        if restricted:
            independence = (INDEPENDENT_FIRST_ACCESS if prior == 0
                            else NOT_INDEPENDENT_REPEAT_ACCESS)
        return self._append(DatasetAccessRecord(
            candidate_id=manifest.candidate_id, dataset_id=dataset_id, dataset_role=role,
            access_reason=access_reason, timestamp_utc=ts,
            result_visibility=result_visibility, granted=True, denial_reason=None,
            governance_approval_id=governance_approval_id,
            repeat_access_count=prior, independence_claim=independence,
            access_stage=access_stage))

    def request_fast_screen_access(self, manifest: CandidateManifest, dataset_id: str,
                                   role: str, access_reason: str,
                                   now: Optional[datetime] = None) -> DatasetAccessRecord:
        """The only C001 fast-screen access entry point.  It has a hard DEV-only
        firewall before normal manifest/governance logic, records both grants and
        denials, and deliberately accepts no governance override."""
        if role != DatasetRole.DEV.value:
            ts = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
            prior = self.granted_count(manifest.candidate_id, dataset_id, role)
            return self._append(DatasetAccessRecord(
                candidate_id=manifest.candidate_id, dataset_id=dataset_id, dataset_role=role,
                access_reason=access_reason, timestamp_utc=ts, result_visibility="DENIED",
                granted=False, denial_reason=FAST_SCREEN_ROLE_FORBIDDEN,
                governance_approval_id=None, repeat_access_count=prior,
                independence_claim="NOT_APPLICABLE", access_stage=C001_FAST_SCREEN_STAGE,
            ))
        return self.request_access(
            manifest, dataset_id, role, access_reason, result_visibility="METRICS_VISIBLE",
            governance_approval_id=None, now=now, access_stage=C001_FAST_SCREEN_STAGE,
        )

    def holdout_accessed_by_c001_fast_screen(self) -> bool:
        """A denied request is evidence the firewall worked, not an access.  Any granted
        C001 fast-screen HOLDOUT record is a release-blocking invariant violation."""
        return any(
            record.granted
            and record.candidate_id == "CRYPTO_CFD_C001"
            and record.dataset_role == DatasetRole.HOLDOUT.value
            and (record.access_stage == C001_FAST_SCREEN_STAGE
                 or record.access_reason.startswith("FAST_SCREEN"))
            for record in self.records()
        )
