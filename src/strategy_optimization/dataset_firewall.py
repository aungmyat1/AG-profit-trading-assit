"""Role-enforcing, pre-read dataset access ledger for optimization experiments.

A caller must route dataset-consuming readers through this facade. Candidate state and
strategy identity are resolved from the verified experiment registry; a caller-provided
state is only an assertion and must match. Protected OOS, final-holdout, replication, and
forward-shadow roles have no optimizer mapping; their reads are stage-gated and journaled
before the callback can touch data. Dataset records are immutable and cannot be relabeled
in place.
"""
from __future__ import annotations

import json
import os
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, TypeVar

from post_asian_pilot.fingerprint import fingerprint
from .admission import evaluate_repository_admission_snapshot, evaluate_stored_admission_evidence
from .hashchain import HashChainError, append_chained_event, read_chained_events
from .models import DatasetManifest, DatasetRole, to_jsonable, to_legacy_dataset_role
from .state_machine import CandidateState

T = TypeVar("T")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,159}$")
_PROTECTED_SINGLE_USE_ROLES = frozenset({
    DatasetRole.REPLICATION,
    DatasetRole.OOS,
    DatasetRole.FINAL_HOLDOUT,
})
_PROTECTED_OPTIMIZATION_ROLES = _PROTECTED_SINGLE_USE_ROLES | frozenset({DatasetRole.FORWARD_SHADOW})
_PURPOSES = {
    DatasetRole.DEVELOPMENT: frozenset({
        "BASELINE_REPRODUCTION", "DATA_INTEGRITY_CHECK", "ECONOMIC_DIAGNOSIS",
        "DEVELOPMENT_EVALUATION",
    }),
    DatasetRole.DEVELOPMENT_REUSED: frozenset({
        "DATA_INTEGRITY_CHECK", "ECONOMIC_DIAGNOSIS", "DEVELOPMENT_EVALUATION",
        "ROBUSTNESS_DIAGNOSTIC",
    }),
    DatasetRole.REPLICATION: frozenset({"INDEPENDENT_REPLICATION"}),
    DatasetRole.OOS: frozenset({"OOS_EVALUATION"}),
    DatasetRole.FINAL_HOLDOUT: frozenset({"FINAL_HOLDOUT_EVALUATION"}),
    DatasetRole.FORWARD_SHADOW: frozenset({"FORWARD_OBSERVATION"}),
}
_ALLOWED_STATES = {
    DatasetRole.DEVELOPMENT: frozenset({CandidateState.DRAFT, CandidateState.PREREGISTERED, CandidateState.DEVELOPMENT_TESTED}),
    DatasetRole.DEVELOPMENT_REUSED: frozenset({CandidateState.DRAFT, CandidateState.PREREGISTERED, CandidateState.DEVELOPMENT_TESTED}),
    DatasetRole.REPLICATION: frozenset({CandidateState.CANDIDATE_FROZEN}),
    DatasetRole.OOS: frozenset({CandidateState.REPLICATION_PASS}),
    DatasetRole.FINAL_HOLDOUT: frozenset({CandidateState.OOS_PASS}),
    DatasetRole.FORWARD_SHADOW: frozenset({CandidateState.PARITY_PASS, CandidateState.FORWARD_RESEARCH}),
}


class DatasetAccessDenied(PermissionError):
    pass


class DatasetRegistryError(RuntimeError):
    pass


class _OneShotConsumed(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_dataset_id(value: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise ValueError(f"invalid dataset id: {value!r}")
    return value


def _safe_identity_id(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise ValueError(f"invalid {field_name}: {value!r}")
    return value


@contextmanager
def _catalog_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as handle:
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def optimizer_role(role: DatasetRole):
    """Return the legacy optimization role only for explicit development roles."""
    legacy = to_legacy_dataset_role(role)
    if role not in {DatasetRole.DEVELOPMENT, DatasetRole.DEVELOPMENT_REUSED} or legacy is None:
        raise DatasetAccessDenied(f"PROTECTED_ROLE_CANNOT_ENTER_OPTIMIZER:{role.value}")
    return legacy


def _load_manifest(path: Path, expected_id: str) -> DatasetManifest:
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
        payload = envelope["manifest"]
        stored_hash = envelope["manifest_sha256"]
    except (OSError, KeyError, json.JSONDecodeError, TypeError) as exc:
        raise DatasetRegistryError(f"invalid dataset manifest: {expected_id}") from exc
    if fingerprint(payload) != stored_hash or payload.get("dataset_id") != expected_id:
        raise DatasetRegistryError(f"dataset manifest hash/identity mismatch: {expected_id}")
    try:
        manifest = DatasetManifest(
            strategy_id=payload["strategy_id"],
            dataset_id=payload["dataset_id"],
            role=DatasetRole(payload["role"]),
            source_ref=payload["source_ref"],
            dataset_sha256=payload.get("dataset_sha256"),
            symbols=tuple(payload.get("symbols", ())),
            utc_start=payload.get("utc_start"),
            utc_end=payload.get("utc_end"),
            reused_from_experiment_id=payload.get("reused_from_experiment_id"),
            reused_from_dataset_id=payload.get("reused_from_dataset_id"),
            description=payload.get("description", ""),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise DatasetRegistryError(f"invalid dataset fields: {expected_id}") from exc
    if manifest.manifest_sha256 != stored_hash:
        raise DatasetRegistryError(f"dataset canonical fingerprint mismatch: {expected_id}")
    return manifest


class DatasetAccessFirewall:
    """Immutable catalog plus hash-chained access journal with role/state policy."""

    def __init__(self, root: str | Path, *, repo_root: Optional[str | Path] = None):
        self.root = Path(root)
        self.repo_root = Path(repo_root) if repo_root is not None else None
        self.catalog = self.root / "datasets"
        self.access_logs = self.root / "dataset_access"

    def register(self, manifest: DatasetManifest, *, actor: str = "dataset-catalog") -> str:
        """Pin a dataset manifest once; role/hash changes require a new dataset ID."""
        _safe_identity_id(manifest.strategy_id, "strategy id")
        if not isinstance(actor, str) or not actor:
            raise ValueError("dataset registration actor is required")
        dataset_id = _safe_dataset_id(manifest.dataset_id)
        path = self.catalog / f"{dataset_id}.json"
        with _catalog_lock(self.root / ".dataset-catalog.lock"):
            if path.exists():
                raise DatasetRegistryError(f"dataset ID is write-once: {dataset_id}")
            self._check_content_hash_role(manifest)
            payload = to_jsonable(manifest)
            envelope = {"manifest": payload, "manifest_sha256": fingerprint(payload)}
            path.parent.mkdir(parents=True, exist_ok=True)
            encoded = json.dumps(envelope, sort_keys=True, indent=2) + "\n"
            try:
                with path.open("x", encoding="utf-8", newline="\n") as handle:
                    handle.write(encoded)
                    handle.flush()
                    os.fsync(handle.fileno())
            except FileExistsError as exc:
                raise DatasetRegistryError(f"dataset ID is write-once: {dataset_id}") from exc
            append_chained_event(
                self.access_logs / f"{dataset_id}.jsonl",
                manifest.manifest_sha256,
                {
                    "event_type": "DATASET_REGISTERED",
                    "actor": actor,
                    "at_utc": _utc_now(),
                    "dataset_id": dataset_id,
                    "strategy_id": manifest.strategy_id,
                    "dataset_sha256": manifest.dataset_sha256,
                    "role": manifest.role.value,
                },
            )
            return envelope["manifest_sha256"]

    def _check_content_hash_role(self, manifest: DatasetManifest) -> None:
        """Prevent a protected content hash from being relabeled as development data."""
        if manifest.dataset_sha256 is None or not self.catalog.exists():
            return
        development_roles = {DatasetRole.DEVELOPMENT, DatasetRole.DEVELOPMENT_REUSED}
        original_reuse_source = None
        if manifest.role is DatasetRole.DEVELOPMENT_REUSED:
            try:
                original_reuse_source = self.load(manifest.reused_from_dataset_id or "")
            except DatasetRegistryError as exc:
                raise DatasetRegistryError("DEVELOPMENT_REUSED_SOURCE_DATASET_NOT_REGISTERED") from exc
            if (
                original_reuse_source.role is not DatasetRole.DEVELOPMENT
                or original_reuse_source.strategy_id != manifest.strategy_id
                or original_reuse_source.dataset_sha256 != manifest.dataset_sha256
                or not manifest.reused_from_experiment_id
            ):
                raise DatasetRegistryError("DEVELOPMENT_REUSED_SOURCE_IDENTITY_MISMATCH")

        matching_hash_found = False
        for path in self.catalog.glob("*.json"):
            existing = _load_manifest(path, path.stem)
            if existing.dataset_sha256 != manifest.dataset_sha256:
                continue
            matching_hash_found = True
            if existing.strategy_id != manifest.strategy_id:
                raise DatasetRegistryError("DATASET_HASH_CROSS_STRATEGY_ALIAS_FORBIDDEN")
            is_explicit_reuse = (
                manifest.role is DatasetRole.DEVELOPMENT_REUSED
                and existing.role in development_roles
                and (
                    existing.dataset_id == original_reuse_source.dataset_id
                    or existing.reused_from_dataset_id == original_reuse_source.dataset_id
                )
            )
            if not is_explicit_reuse:
                raise DatasetRegistryError(
                    f"DATASET_HASH_ALREADY_PINNED_TO_ROLE:{existing.role.value}"
                )
        if manifest.role is DatasetRole.DEVELOPMENT_REUSED and not matching_hash_found:
            raise DatasetRegistryError("DEVELOPMENT_REUSED_HASH_MUST_MATCH_REGISTERED_DEVELOPMENT_DATA")

    def load(self, dataset_id: str) -> DatasetManifest:
        safe_id = _safe_dataset_id(dataset_id)
        return _load_manifest(self.catalog / f"{safe_id}.json", safe_id)

    def _authoritative_experiment_state(
        self,
        experiment_id: str,
        strategy_id: str,
    ) -> CandidateState:
        """Resolve state from the verified experiment registry, never caller input alone."""
        from .registry import CorruptRegistry, ExperimentRegistry, RegistryError

        registry = ExperimentRegistry(self.root, repo_root=self.repo_root)
        try:
            experiment = registry.load_manifest(experiment_id)
            if experiment.get("strategy_id") != strategy_id:
                raise DatasetAccessDenied("CROSS_STRATEGY_EXPERIMENT_ACCESS_FORBIDDEN")
            return registry.state(experiment_id)
        except DatasetAccessDenied:
            raise
        except (CorruptRegistry, RegistryError, OSError, ValueError) as exc:
            raise DatasetAccessDenied("EXPERIMENT_REGISTRY_STATE_UNAVAILABLE_FAIL_CLOSED") from exc

    def access(
        self,
        dataset_id: str,
        *,
        experiment_id: str,
        strategy_id: str,
        state: CandidateState,
        purpose: str,
        actor: str,
        reader: Callable[[DatasetManifest], T],
        optimization_conditions: Optional[Mapping[str, Any]] = None,
        at_utc: Optional[str] = None,
    ) -> T:
        """Journal intent before calling `reader`; denied requests never invoke it.

        `state` must equal the current state read from the verified experiment registry;
        the caller cannot self-authorize a later stage. Replication, OOS, and final-holdout
        each allow a single authorized read attempt.
        Failed readers still consume that attempt because the payload may have been
        exposed. Development-evaluation and robustness reads additionally require the
        canonical signed optimization-admission contract. All protected and forward
        roles remain unavailable to the optimizer.
        """
        if not isinstance(actor, str) or not actor:
            raise ValueError("dataset access needs an actor identity")
        _safe_identity_id(experiment_id, "experiment id")
        _safe_identity_id(strategy_id, "strategy id")
        if not isinstance(purpose, str) or not purpose:
            raise ValueError("dataset access purpose is required")
        try:
            state = CandidateState(state)
        except (TypeError, ValueError) as exc:
            raise ValueError("dataset access candidate state is invalid") from exc
        manifest = self.load(dataset_id)
        log_path = self.access_logs / f"{_safe_dataset_id(dataset_id)}.jsonl"
        genesis = manifest.manifest_sha256
        if not log_path.is_file():
            raise DatasetRegistryError("DATASET_ACCESS_LEDGER_MISSING_FAIL_CLOSED")
        try:
            current_events = read_chained_events(log_path, genesis)
        except (OSError, HashChainError) as exc:
            raise DatasetRegistryError(f"DATASET_ACCESS_LEDGER_INVALID_FAIL_CLOSED:{exc}") from exc
        if not current_events or current_events[0].get("event_type") != "DATASET_REGISTERED":
            raise DatasetRegistryError("DATASET_ACCESS_LEDGER_UNINITIALIZED_FAIL_CLOSED")
        if (
            current_events[0].get("dataset_id") != manifest.dataset_id
            or current_events[0].get("strategy_id") != manifest.strategy_id
            or current_events[0].get("role") != manifest.role.value
            or current_events[0].get("dataset_sha256") != manifest.dataset_sha256
        ):
            raise DatasetRegistryError("DATASET_ACCESS_LEDGER_IDENTITY_MISMATCH_FAIL_CLOSED")
        timestamp = at_utc or _utc_now()
        denial_reason = None
        try:
            authoritative_state = self._authoritative_experiment_state(experiment_id, strategy_id)
        except DatasetAccessDenied as exc:
            denial_reason = str(exc)
        if denial_reason is None and state is not authoritative_state:
            denial_reason = "CALLER_CANDIDATE_STATE_MISMATCH"
        elif denial_reason is None and manifest.strategy_id != strategy_id:
            denial_reason = "CROSS_STRATEGY_DATA_ACCESS_FORBIDDEN"
        elif denial_reason is None and purpose not in _PURPOSES[manifest.role]:
            denial_reason = "PURPOSE_NOT_PERMITTED_FOR_DATASET_ROLE"
        elif denial_reason is None and state not in _ALLOWED_STATES[manifest.role]:
            denial_reason = "DATASET_ROLE_NOT_AVAILABLE_AT_CANDIDATE_STATE"

        admission_evidence = None
        optimization_purpose = purpose in {"DEVELOPMENT_EVALUATION", "ROBUSTNESS_DIAGNOSTIC"}
        if denial_reason is None and purpose == "DEVELOPMENT_EVALUATION" and state is not CandidateState.PREREGISTERED:
            denial_reason = "DEVELOPMENT_EVALUATION_REQUIRES_PREREGISTERED_STATE"
        elif denial_reason is None and purpose == "ROBUSTNESS_DIAGNOSTIC" and state is not CandidateState.DEVELOPMENT_TESTED:
            denial_reason = "ROBUSTNESS_DIAGNOSTIC_REQUIRES_DEVELOPMENT_TESTED_STATE"
        if denial_reason is None and optimization_purpose:
            if self.repo_root is None:
                denial_reason = "OPTIMIZATION_ADMISSION_REPOSITORY_ROOT_REQUIRED"
            else:
                conditions = dict(optimization_conditions or {})
                try:
                    actual_protected_access_count = self.protected_access_count(experiment_id)
                except DatasetRegistryError as exc:
                    denial_reason = f"PROTECTED_ACCESS_LEDGER_INVALID:{exc}"
                declared_protected_access_count = conditions.get("protected_data_access_count")
                if denial_reason is None and "protected_data_access_count" in conditions and (
                    type(declared_protected_access_count) is not int
                    or declared_protected_access_count != actual_protected_access_count
                ):
                    denial_reason = "PROTECTED_DATA_ACCESS_COUNT_MISMATCH"
                if denial_reason is None:
                    admission, contract_sha256, contract_status, contract_snapshot = evaluate_repository_admission_snapshot(
                        self.repo_root, conditions
                    )
                    if not admission.eligible:
                        denial_reason = "OPTIMIZATION_ADMISSION_BLOCKED:" + ";".join(admission.blockers)
                    elif not contract_sha256 or contract_status != "SIGNED" or contract_snapshot is None:
                        denial_reason = "OPTIMIZATION_ADMISSION_CONTRACT_NOT_SIGNED"
                    else:
                        admission_evidence = {
                            "eligible": True,
                            "status": admission.status,
                            "contract_ref": "config/governance/optimization_admission_contract.yaml",
                            "contract_status": contract_status,
                            "contract_sha256": contract_sha256,
                            "contract_snapshot_utf8": contract_snapshot,
                            "conditions": conditions,
                            "conditions_sha256": fingerprint(conditions),
                        }

        if denial_reason:
            append_chained_event(
                log_path,
                genesis,
                {
                    "event_type": "ACCESS_DENIED_NO_READ",
                    "actor": actor,
                    "at_utc": timestamp,
                    "dataset_id": manifest.dataset_id,
                    "experiment_id": experiment_id,
                    "strategy_id": strategy_id,
                    "role": manifest.role.value,
                    "state": state.value,
                    "purpose": purpose,
                    "reason": denial_reason,
                    "optimization_admission": admission_evidence,
                },
            )
            raise DatasetAccessDenied(denial_reason)

        access_attempt = 0
        authorization_payload: dict[str, Any] = {
            "event_type": "ACCESS_AUTHORIZED_BEFORE_READ",
            "actor": actor,
            "at_utc": timestamp,
            "dataset_id": manifest.dataset_id,
            "dataset_sha256": manifest.dataset_sha256,
            "experiment_id": experiment_id,
            "strategy_id": strategy_id,
            "role": manifest.role.value,
            "state": state.value,
            "purpose": purpose,
            "access_attempt": access_attempt,
            "optimization_admission": admission_evidence,
        }

        def precondition(existing: list[dict[str, Any]]) -> None:
            nonlocal access_attempt
            count = sum(event.get("event_type") == "ACCESS_AUTHORIZED_BEFORE_READ" for event in existing)
            if manifest.role in _PROTECTED_SINGLE_USE_ROLES and count >= 1:
                raise _OneShotConsumed("PROTECTED_DATASET_ALREADY_EXPOSED")
            access_attempt = count + 1
            authorization_payload["access_attempt"] = access_attempt

        try:
            append_chained_event(log_path, genesis, authorization_payload, precondition=precondition)
        except _OneShotConsumed as exc:
            append_chained_event(
                log_path,
                genesis,
                {
                    "event_type": "ACCESS_DENIED_NO_READ",
                    "actor": actor,
                    "at_utc": timestamp,
                    "dataset_id": manifest.dataset_id,
                    "experiment_id": experiment_id,
                    "strategy_id": strategy_id,
                    "role": manifest.role.value,
                    "state": state.value,
                    "purpose": purpose,
                    "reason": str(exc),
                },
            )
            raise DatasetAccessDenied(str(exc)) from exc
        except HashChainError as exc:
            raise DatasetRegistryError(f"dataset access chain invalid: {exc}") from exc

        try:
            result = reader(manifest)
        except Exception as exc:
            append_chained_event(
                log_path,
                genesis,
                {
                    "event_type": "READ_OUTCOME",
                    "actor": actor,
                    "at_utc": _utc_now(),
                    "dataset_id": manifest.dataset_id,
                    "experiment_id": experiment_id,
                    "access_attempt": access_attempt,
                    "outcome": "READER_FAILED_AFTER_AUTHORIZATION",
                    "exception_type": type(exc).__name__,
                },
            )
            raise
        append_chained_event(
            log_path,
            genesis,
            {
                "event_type": "READ_OUTCOME",
                "actor": actor,
                "at_utc": _utc_now(),
                "dataset_id": manifest.dataset_id,
                "experiment_id": experiment_id,
                "access_attempt": access_attempt,
                "outcome": "READ_COMPLETED",
            },
        )
        return result

    def access_events(self, dataset_id: str):
        """Return a validated access history bound to the immutable dataset manifest."""
        manifest = self.load(dataset_id)
        log_path = self.access_logs / f"{_safe_dataset_id(dataset_id)}.jsonl"
        if not log_path.is_file():
            raise DatasetRegistryError("DATASET_ACCESS_LEDGER_MISSING_FAIL_CLOSED")
        try:
            events = read_chained_events(log_path, manifest.manifest_sha256)
        except (OSError, HashChainError) as exc:
            raise DatasetRegistryError(f"DATASET_ACCESS_LEDGER_INVALID_FAIL_CLOSED:{exc}") from exc
        if not events or events[0].get("event_type") != "DATASET_REGISTERED":
            raise DatasetRegistryError("DATASET_ACCESS_LEDGER_UNINITIALIZED_FAIL_CLOSED")
        registered = events[0]
        if (
            registered.get("dataset_id") != manifest.dataset_id
            or registered.get("strategy_id") != manifest.strategy_id
            or registered.get("role") != manifest.role.value
            or registered.get("dataset_sha256") != manifest.dataset_sha256
        ):
            raise DatasetRegistryError("DATASET_ACCESS_LEDGER_IDENTITY_MISMATCH_FAIL_CLOSED")
        authorized = {}
        outcome_seen = set()
        for event in events[1:]:
            if event.get("dataset_id") != manifest.dataset_id:
                raise DatasetRegistryError("DATASET_ACCESS_EVENT_IDENTITY_MISMATCH_FAIL_CLOSED")
            event_type = event.get("event_type")
            if event_type != "DATASET_REGISTERED" and not event.get("experiment_id"):
                raise DatasetRegistryError("DATASET_ACCESS_EVENT_MISSING_EXPERIMENT_ID")
            if event_type == "ACCESS_AUTHORIZED_BEFORE_READ":
                attempt = event.get("access_attempt")
                if type(attempt) is not int or attempt != len(authorized) + 1:
                    raise DatasetRegistryError("DATASET_ACCESS_ATTEMPT_SEQUENCE_INVALID")
                if (
                    event.get("dataset_sha256") != manifest.dataset_sha256
                    or event.get("role") != manifest.role.value
                    or event.get("strategy_id") != manifest.strategy_id
                    or event.get("purpose") not in _PURPOSES[manifest.role]
                ):
                    raise DatasetRegistryError("DATASET_ACCESS_EVENT_ROLE_OR_IDENTITY_MISMATCH")
                try:
                    event_state = CandidateState(event.get("state"))
                except (ValueError, TypeError) as exc:
                    raise DatasetRegistryError("DATASET_ACCESS_EVENT_STATE_INVALID") from exc
                if event_state not in _ALLOWED_STATES[manifest.role]:
                    raise DatasetRegistryError("DATASET_ACCESS_EVENT_STATE_NOT_PERMITTED")
                if event.get("purpose") == "DEVELOPMENT_EVALUATION" and event_state is not CandidateState.PREREGISTERED:
                    raise DatasetRegistryError("DEVELOPMENT_EVALUATION_STATE_INVALID")
                if event.get("purpose") == "ROBUSTNESS_DIAGNOSTIC" and event_state is not CandidateState.DEVELOPMENT_TESTED:
                    raise DatasetRegistryError("ROBUSTNESS_DIAGNOSTIC_STATE_INVALID")
                if event.get("purpose") in {"DEVELOPMENT_EVALUATION", "ROBUSTNESS_DIAGNOSTIC"}:
                    admission = event.get("optimization_admission") or {}
                    conditions = admission.get("conditions") if isinstance(admission, Mapping) else None
                    if not isinstance(conditions, Mapping):
                        raise DatasetRegistryError("UNSIGNED_OPTIMIZATION_ACCESS_PRESENT_IN_LEDGER")
                    verified = evaluate_stored_admission_evidence(
                        admission.get("contract_snapshot_utf8"),
                        admission.get("contract_sha256"),
                        admission.get("contract_status"),
                        conditions,
                        admission.get("conditions_sha256"),
                    )
                    if not (
                        admission.get("eligible") is True
                        and admission.get("status") == verified.status
                        and admission.get("contract_ref") == "config/governance/optimization_admission_contract.yaml"
                        and verified.eligible
                    ):
                        raise DatasetRegistryError("UNSIGNED_OPTIMIZATION_ACCESS_PRESENT_IN_LEDGER")
                authorized[attempt] = event
            elif event_type == "READ_OUTCOME":
                attempt = event.get("access_attempt")
                if type(attempt) is not int or attempt not in authorized or attempt in outcome_seen:
                    raise DatasetRegistryError("DATASET_READ_OUTCOME_WITHOUT_UNIQUE_AUTHORIZATION")
                if event.get("experiment_id") != authorized[attempt].get("experiment_id"):
                    raise DatasetRegistryError("DATASET_READ_OUTCOME_EXPERIMENT_MISMATCH")
                outcome_seen.add(attempt)
                if event.get("outcome") not in {"READ_COMPLETED", "READER_FAILED_AFTER_AUTHORIZATION"}:
                    raise DatasetRegistryError("DATASET_READ_OUTCOME_INVALID")
            elif event_type != "ACCESS_DENIED_NO_READ":
                raise DatasetRegistryError(f"UNKNOWN_DATASET_ACCESS_EVENT:{event_type}")
        if manifest.role in _PROTECTED_SINGLE_USE_ROLES and len(authorized) > 1:
            raise DatasetRegistryError("PROTECTED_DATASET_SINGLE_USE_INVARIANT_BROKEN")
        return tuple(events)

    def protected_access_count(self, experiment_id: str) -> int:
        """Count every authorized protected-role read for one experiment.

        Any missing/corrupt protected dataset ledger fails closed rather than being
        interpreted as zero exposure.
        """
        _safe_identity_id(experiment_id, "experiment id")
        if not self.catalog.exists():
            return 0
        count = 0
        for path in self.catalog.glob("*.json"):
            manifest = _load_manifest(path, path.stem)
            if manifest.role not in _PROTECTED_OPTIMIZATION_ROLES:
                continue
            events = self.access_events(manifest.dataset_id)
            count += sum(
                event.get("event_type") == "ACCESS_AUTHORIZED_BEFORE_READ"
                and event.get("experiment_id") == experiment_id
                for event in events
            )
        return count

    @staticmethod
    def optimizer_role(role: DatasetRole):
        """Role conversion only; admission and dataset access must still be checked."""
        return optimizer_role(role)


__all__ = [
    "DatasetAccessDenied", "DatasetAccessFirewall", "DatasetRegistryError", "optimizer_role",
]
