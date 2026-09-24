"""Immutable, per-experiment registry with append-only hash-chained events."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from post_asian_pilot.fingerprint import fingerprint
from .admission import evaluate_repository_admission_snapshot, evaluate_stored_admission_evidence
from .dataset_firewall import DatasetAccessFirewall, DatasetRegistryError
from .hashchain import HashChainError, append_chained_event, read_chained_events
from .models import (
    Arm,
    ExperimentManifest,
    ExperimentHypothesis,
    ExperimentMetrics,
    ExperimentResult,
    PromotionDecision,
    PromotionDisposition,
    to_jsonable,
)
from .state_machine import CandidateState, TERMINAL_STATES, validate_transition

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,159}$")


class RegistryError(RuntimeError):
    pass


class ImmutableRecordExists(RegistryError):
    pass


class CorruptRegistry(RegistryError):
    pass


class TransitionRejected(RegistryError):
    def __init__(self, blockers: Sequence[str]):
        self.blockers = tuple(blockers)
        super().__init__(", ".join(self.blockers))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_id(value: str, name: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise ValueError(f"invalid {name}: {value!r}")
    return value


def _normalize_evidence_refs(evidence_refs: Mapping[str, Sequence[str]]) -> Dict[str, Tuple[str, ...]]:
    if not isinstance(evidence_refs, Mapping):
        raise ValueError("evidence_refs must be a mapping")
    normalized: Dict[str, Tuple[str, ...]] = {}
    for key, refs in evidence_refs.items():
        if (
            not isinstance(key, str)
            or not key
            or isinstance(refs, (str, bytes, Mapping))
            or not isinstance(refs, Sequence)
        ):
            raise ValueError("evidence references must use string keys and sequences of strings")
        values = tuple(refs)
        if any(not isinstance(ref, str) or not ref for ref in values):
            raise ValueError("evidence references must contain nonempty strings")
        normalized[key] = values
    return normalized


def _write_once_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, sort_keys=True, indent=2, default=str) + "\n"
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise ImmutableRecordExists(f"immutable record already exists: {path}") from exc


class ExperimentRegistry:
    """Write-once experiment manifests, immutable results, and verified state ledgers.

    Directory layout: `<root>/experiments/<experiment_id>/manifest.json`,
    `events.jsonl`, and `results/<arm>_<run>.json`. Existing records are never
    overwritten. The registry does not touch strategies/registry.yaml or lifecycle
    authority files.
    """

    def __init__(self, root: str | Path, *, repo_root: Optional[str | Path] = None):
        self.root = Path(root)
        self.repo_root = Path(repo_root) if repo_root is not None else None
        self.experiments_root = self.root / "experiments"

    def _experiment_dir(self, experiment_id: str) -> Path:
        return self.experiments_root / _safe_id(experiment_id, "experiment id")

    @staticmethod
    def _manifest_envelope(manifest: ExperimentManifest) -> Dict[str, Any]:
        payload = to_jsonable(manifest)
        return {
            "schema_version": manifest.schema_version,
            "manifest": payload,
            "manifest_sha256": fingerprint(payload),
        }

    def register(
        self,
        manifest: ExperimentManifest,
        *,
        actor: str,
        at_utc: Optional[str] = None,
    ) -> str:
        """Create a new experiment in DRAFT. Reusing an ID is a hard error."""
        if not isinstance(actor, str) or not actor:
            raise ValueError("registry actor is required")
        _safe_id(manifest.experiment_id, "experiment id")
        _safe_id(manifest.strategy_id, "strategy id")
        experiment_dir = self._experiment_dir(manifest.experiment_id)
        experiment_dir.parent.mkdir(parents=True, exist_ok=True)
        try:
            experiment_dir.mkdir(exist_ok=False)
        except FileExistsError as exc:
            raise ImmutableRecordExists(
                f"experiment ID is immutable and already registered: {manifest.experiment_id}"
            ) from exc

        envelope = self._manifest_envelope(manifest)
        manifest_path = experiment_dir / "manifest.json"
        _write_once_json(manifest_path, envelope)
        manifest_sha256 = envelope["manifest_sha256"]
        append_chained_event(
            experiment_dir / "events.jsonl",
            manifest_sha256,
            {
                "event_type": "REGISTERED",
                "actor": actor,
                "at_utc": at_utc or _utc_now(),
                "state_before": None,
                "state_after": CandidateState.DRAFT.value,
                "evidence_refs": {"manifest": ["manifest.json"]},
                "details": {"schema_version": manifest.schema_version},
            },
        )
        return manifest_sha256

    def load_manifest(self, experiment_id: str) -> Mapping[str, Any]:
        path = self._experiment_dir(experiment_id) / "manifest.json"
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CorruptRegistry(f"cannot read manifest for {experiment_id}") from exc
        payload = envelope.get("manifest")
        expected = envelope.get("manifest_sha256")
        if not isinstance(payload, dict) or expected != fingerprint(payload):
            raise CorruptRegistry(f"manifest hash mismatch for {experiment_id}")
        if envelope.get("schema_version") != "AG_STRATEGY_OPTIMIZATION_FRAMEWORK_V1":
            raise CorruptRegistry(f"unsupported manifest schema for {experiment_id}")
        # Return the immutable raw mapping through a deliberately small loader instead of
        # reconstructing nested dataclasses from untrusted disk data. Callers wanting the
        # typed object should retain it at registration time.
        return payload  # type: ignore[return-value]

    def manifest_sha256(self, experiment_id: str) -> str:
        path = self._experiment_dir(experiment_id) / "manifest.json"
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CorruptRegistry(f"cannot read manifest for {experiment_id}") from exc
        payload = envelope.get("manifest")
        expected = envelope.get("manifest_sha256")
        if not isinstance(payload, dict) or expected != fingerprint(payload):
            raise CorruptRegistry(f"manifest hash mismatch for {experiment_id}")
        return expected

    def events(self, experiment_id: str) -> Tuple[Mapping[str, Any], ...]:
        experiment_dir = self._experiment_dir(experiment_id)
        genesis = self.manifest_sha256(experiment_id)
        try:
            events = read_chained_events(experiment_dir / "events.jsonl", genesis)
        except (OSError, HashChainError) as exc:
            raise CorruptRegistry(f"event chain invalid for {experiment_id}: {exc}") from exc
        if not events or events[0].get("event_type") != "REGISTERED":
            raise CorruptRegistry(f"missing registration event for {experiment_id}")
        if events[0].get("state_after") != CandidateState.DRAFT.value:
            raise CorruptRegistry(f"invalid initial state for {experiment_id}")
        current = CandidateState.DRAFT
        owner_decision_recorded = False
        for index, event in enumerate(events[1:], start=2):
            event_type = event.get("event_type")
            before = event.get("state_before")
            after = event.get("state_after")
            if before != current.value:
                raise CorruptRegistry(f"state chain mismatch at event {index}")
            if event_type == "TRANSITION":
                try:
                    target = CandidateState(after)
                except (TypeError, ValueError) as exc:
                    raise CorruptRegistry(f"unknown state at event {index}") from exc
                admission_flag = event.get("optimization_admission_passed", False)
                if type(admission_flag) is not bool:
                    raise CorruptRegistry(f"invalid optimization-admission flag at event {index}")
                admission_passed = admission_flag
                transition_details = event.get("details") or {}
                transition_refs = event.get("evidence_refs") or {}
                if not isinstance(transition_details, Mapping) or not isinstance(transition_refs, Mapping):
                    raise CorruptRegistry(f"transition evidence schema invalid at event {index}")
                if any(
                    not isinstance(key, str)
                    or not isinstance(refs, list)
                    or any(not isinstance(ref, str) or not ref for ref in refs)
                    for key, refs in transition_refs.items()
                ):
                    raise CorruptRegistry(f"transition evidence references invalid at event {index}")
                if target in {CandidateState.DEVELOPMENT_TESTED, CandidateState.ROBUSTNESS_PASS}:
                    admission = transition_details.get("optimization_admission", {})
                    if not isinstance(admission, Mapping):
                        raise CorruptRegistry(f"missing signed optimization-admission evidence at event {index}")
                    conditions = admission.get("conditions")
                    if not isinstance(conditions, Mapping):
                        raise CorruptRegistry(f"missing signed optimization-admission evidence at event {index}")
                    verified_admission = evaluate_stored_admission_evidence(
                        admission.get("contract_snapshot_utf8"),
                        admission.get("contract_sha256"),
                        admission.get("contract_status"),
                        conditions,
                        admission.get("conditions_sha256"),
                    )
                    if not (
                        admission_passed
                        and admission.get("eligible") is True
                        and admission.get("status") == verified_admission.status
                        and admission.get("contract_ref") == "config/governance/optimization_admission_contract.yaml"
                        and verified_admission.eligible
                    ):
                        raise CorruptRegistry(f"missing signed optimization-admission evidence at event {index}")
                elif admission_passed:
                    raise CorruptRegistry(f"unexpected optimization-admission flag at event {index}")
                if target is CandidateState.PREREGISTERED:
                    try:
                        self._validate_preregistration(experiment_id)
                    except TransitionRejected as exc:
                        raise CorruptRegistry(f"invalid preregistration at event {index}: {exc}") from exc
                decision = validate_transition(
                    current,
                    target,
                    transition_refs,
                    optimization_admission_passed=admission_passed,
                )
                if not decision.allowed:
                    raise CorruptRegistry(f"illegal transition at event {index}: {decision.blockers}")
                current = target
            elif event_type == "RESULT_RECORDED":
                if current in TERMINAL_STATES or current is CandidateState.OWNER_REVIEW:
                    raise CorruptRegistry(f"result was recorded after the active experiment stage at event {index}")
                if after != current.value:
                    raise CorruptRegistry(f"result event changed state at event {index}")
                recorded_result_refs = event.get("evidence_refs") or {}
                details = event.get("details") or {}
                if not isinstance(recorded_result_refs, Mapping) or not isinstance(details, Mapping):
                    raise CorruptRegistry(f"result event schema invalid at event {index}")
                refs = recorded_result_refs.get("experiment_result", [])
                if not isinstance(refs, list) or len(refs) != 1 or not isinstance(refs[0], str):
                    raise CorruptRegistry(f"result event has invalid artifact reference at event {index}")
                result_path = (experiment_dir / refs[0]).resolve()
                if experiment_dir.resolve() not in result_path.parents:
                    raise CorruptRegistry(f"result artifact escapes experiment directory at event {index}")
                try:
                    envelope = json.loads(result_path.read_text(encoding="utf-8"))
                    result_payload = envelope["result"]
                    result_sha = envelope["result_sha256"]
                except (OSError, KeyError, json.JSONDecodeError, TypeError) as exc:
                    raise CorruptRegistry(f"result artifact unavailable at event {index}") from exc
                if (
                    not isinstance(result_payload, dict)
                    or result_sha != fingerprint(result_payload)
                    or result_sha != details.get("result_sha256")
                    or details.get("result_path") != refs[0]
                    or result_payload.get("experiment_id") != experiment_id
                    or result_payload.get("strategy_id") != self.load_manifest(experiment_id)["strategy_id"]
                    or result_payload.get("arm") != details.get("arm")
                ):
                    raise CorruptRegistry(f"result artifact hash/identity mismatch at event {index}")
                try:
                    metric_payload = result_payload["metrics"]
                    if not isinstance(metric_payload, Mapping):
                        raise TypeError("metrics payload is not a mapping")
                    normalized_result = ExperimentResult(
                        experiment_id=result_payload["experiment_id"],
                        strategy_id=result_payload["strategy_id"],
                        arm=result_payload["arm"],
                        metrics=ExperimentMetrics(**metric_payload),
                        dataset_id=result_payload.get("dataset_id"),
                        dataset_sha256=result_payload.get("dataset_sha256"),
                        dataset_role=result_payload.get("dataset_role"),
                        population_hash=result_payload.get("population_hash"),
                        friction_profile_sha256=result_payload.get("friction_profile_sha256"),
                        candidate_config_sha256=result_payload.get("candidate_config_sha256"),
                        run_id=result_payload.get("run_id"),
                        evidence_refs=tuple(result_payload.get("evidence_refs", ())),
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    raise CorruptRegistry(f"result artifact schema invalid at event {index}") from exc
                if normalized_result.result_sha256 != result_sha:
                    raise CorruptRegistry(f"result artifact canonical hash mismatch at event {index}")
                try:
                    manifest_payload = self.load_manifest(experiment_id)
                    expected_config_sha = (
                        manifest_payload["baseline"]["canonical_config_sha256"]
                        if normalized_result.arm is Arm.CONTROL
                        else manifest_payload["candidate"]["candidate_config_sha256"]
                    )
                    if (
                        normalized_result.strategy_id != manifest_payload["strategy_id"]
                        or (
                            normalized_result.metrics.status.value == "EVALUATED"
                            and normalized_result.candidate_config_sha256 != expected_config_sha
                        )
                        or normalized_result.candidate_config_sha256 not in (None, expected_config_sha)
                    ):
                        raise RegistryError("result arm/config identity mismatch")
                    event_refs = recorded_result_refs
                    if normalized_result.metrics.status.value == "EVALUATED" and current is CandidateState.DRAFT and not (
                        normalized_result.arm is Arm.CONTROL
                        and normalized_result.dataset_role.value == "DEVELOPMENT"
                    ):
                        raise RegistryError("only baseline control reproduction may be evaluated before preregistration")
                    self._verify_result_provenance(normalized_result, current, event_refs)
                except RegistryError as exc:
                    raise CorruptRegistry(f"result provenance invalid at event {index}: {exc}") from exc
            elif event_type == "OWNER_DECISION_RECORDED":
                if owner_decision_recorded:
                    raise CorruptRegistry("multiple owner decisions were recorded for one experiment")
                if current is not CandidateState.OWNER_REVIEW:
                    raise CorruptRegistry("owner decision was recorded before OWNER_REVIEW")
                details = event.get("details") or {}
                if not isinstance(details, Mapping):
                    raise CorruptRegistry("owner decision event schema invalid")
                decision_payload = details.get("decision")
                if not isinstance(decision_payload, dict):
                    raise CorruptRegistry("owner decision record hash/identity mismatch")
                try:
                    decision_record = PromotionDecision(**decision_payload)
                except (TypeError, ValueError) as exc:
                    raise CorruptRegistry("owner decision record schema invalid") from exc
                if (
                    decision_record.decision_sha256 != details.get("decision_sha256")
                    or decision_record.experiment_id != experiment_id
                    or decision_record.strategy_id != self.load_manifest(experiment_id)["strategy_id"]
                    or decision_record.execution_authority_changed is not False
                    or event.get("actor") != decision_record.decided_by
                ):
                    raise CorruptRegistry("owner decision record hash/identity mismatch")
                recorded_refs = event.get("evidence_refs") or {}
                if not isinstance(recorded_refs, Mapping):
                    raise CorruptRegistry("owner decision evidence references are invalid")
                owner_refs = recorded_refs.get("owner_authority", [])
                if owner_refs != [decision_payload.get("authority_ref")]:
                    raise CorruptRegistry("owner decision authority reference mismatch")
                owner_decision_recorded = True
                if decision_record.disposition is PromotionDisposition.REJECT:
                    rejection_refs = recorded_refs.get("owner_rejection_record", [])
                    if (
                        after != CandidateState.REJECTED_OWNER_DECISION.value
                        or rejection_refs != [decision_record.authority_ref]
                    ):
                        raise CorruptRegistry("owner rejection did not close the candidate terminally")
                    current = CandidateState.REJECTED_OWNER_DECISION
                else:
                    if recorded_refs.get("owner_rejection_record") or after != current.value:
                        raise CorruptRegistry(f"non-rejection owner decision changed state at event {index}")
            else:
                raise CorruptRegistry(f"unknown event type at event {index}: {event_type!r}")
        return tuple(events)

    def state(self, experiment_id: str) -> CandidateState:
        events = self.events(experiment_id)
        return CandidateState(events[-1]["state_after"])

    def _verify_result_provenance(
        self,
        result: ExperimentResult,
        current_state: CandidateState,
        evidence_refs: Optional[Mapping[str, Any]] = None,
    ) -> None:
        """Bind evaluated metrics to the exact registered dataset and successful read."""
        expected_manifest_refs: list[str] = []
        expected_access_refs: list[str] = []
        if result.metrics.status.value == "EVALUATED":
            try:
                firewall = DatasetAccessFirewall(self.root, repo_root=self.repo_root)
                dataset = firewall.load(result.dataset_id or "")
                access_events = firewall.access_events(result.dataset_id or "")
            except (DatasetRegistryError, ValueError) as exc:
                raise RegistryError(f"evaluated result has no valid dataset/access provenance: {exc}") from exc
            if (
                dataset.strategy_id != result.strategy_id
                or dataset.dataset_sha256 != result.dataset_sha256
                or dataset.role is not result.dataset_role
            ):
                raise RegistryError("result dataset identity/role does not match registered dataset manifest")
            if result.dataset_role.value == "DEVELOPMENT" and current_state is CandidateState.DRAFT:
                if result.arm is not Arm.CONTROL:
                    raise RegistryError("only the control arm may be evaluated for baseline reproduction")
                expected_purpose = "BASELINE_REPRODUCTION"
            elif (
                result.dataset_role.value == "DEVELOPMENT_REUSED"
                and current_state is CandidateState.DEVELOPMENT_TESTED
            ):
                expected_purpose = "ROBUSTNESS_DIAGNOSTIC"
            else:
                expected_purpose = {
                    "DEVELOPMENT": "DEVELOPMENT_EVALUATION",
                    "DEVELOPMENT_REUSED": "DEVELOPMENT_EVALUATION",
                    "REPLICATION": "INDEPENDENT_REPLICATION",
                    "OOS": "OOS_EVALUATION",
                    "FINAL_HOLDOUT": "FINAL_HOLDOUT_EVALUATION",
                    "FORWARD_SHADOW": "FORWARD_OBSERVATION",
                }[result.dataset_role.value]
            authorizations = {
                event["access_attempt"]: event
                for event in access_events
                if event.get("event_type") == "ACCESS_AUTHORIZED_BEFORE_READ"
                and event.get("experiment_id") == result.experiment_id
                and event.get("strategy_id") == result.strategy_id
                and event.get("role") == result.dataset_role.value
                and event.get("purpose") == expected_purpose
                and event.get("dataset_sha256") == result.dataset_sha256
            }
            completed = {
                event.get("access_attempt")
                for event in access_events
                if event.get("event_type") == "READ_OUTCOME" and event.get("outcome") == "READ_COMPLETED"
            }
            if not set(authorizations).intersection(completed):
                raise RegistryError("evaluated result lacks a completed pre-read firewall access record")
            expected_manifest_refs = [f"datasets/{result.dataset_id}.json"]
            expected_access_refs = [f"dataset_access/{result.dataset_id}.jsonl"]
        if evidence_refs is not None:
            if not isinstance(evidence_refs, Mapping):
                raise RegistryError("result evidence references are invalid")
            if evidence_refs.get("dataset_manifest", []) != expected_manifest_refs:
                raise RegistryError("result dataset-manifest reference does not match its evaluation status")
            if evidence_refs.get("dataset_access_ledger", []) != expected_access_refs:
                raise RegistryError("result access-ledger reference does not match its evaluation status")

    def _validate_preregistration(self, experiment_id: str) -> None:
        """Require a reproduced control identity and verified canonical SVOS hypothesis."""
        manifest = self.load_manifest(experiment_id)
        baseline = manifest.get("baseline")
        dataset = manifest.get("dataset")
        hypothesis_payload = manifest.get("hypothesis")
        if not isinstance(baseline, Mapping) or baseline.get("baseline_status") != "REPRODUCIBLE":
            raise TransitionRejected(("BASELINE_NOT_REPRODUCIBLE",))
        if not isinstance(dataset, Mapping) or dataset.get("role") != "DEVELOPMENT":
            raise TransitionRejected(("BASELINE_DEVELOPMENT_DATASET_IDENTITY_REQUIRED",))
        if (
            baseline.get("dataset_id") != dataset.get("dataset_id")
            or baseline.get("dataset_sha256") != dataset.get("dataset_sha256")
            or baseline.get("strategy_id") != manifest.get("strategy_id")
            or dataset.get("strategy_id") != manifest.get("strategy_id")
        ):
            raise TransitionRejected(("BASELINE_DATASET_IDENTITY_MISMATCH",))
        if not isinstance(hypothesis_payload, Mapping):
            raise TransitionRejected(("HYPOTHESIS_PREREGISTRATION_MISSING",))
        try:
            hypothesis = ExperimentHypothesis(
                hypothesis_id=hypothesis_payload["hypothesis_id"],
                strategy_id=hypothesis_payload["strategy_id"],
                parent_version=hypothesis_payload["parent_version"],
                statement=hypothesis_payload["statement"],
                mechanism=hypothesis_payload["mechanism"],
                permitted_delta=tuple(hypothesis_payload["permitted_delta"]),
                forbidden_deltas=tuple(hypothesis_payload["forbidden_deltas"]),
                status=hypothesis_payload["status"],
                development_dataset_id=hypothesis_payload.get("development_dataset_id"),
                protected_dataset_ids=tuple(hypothesis_payload.get("protected_dataset_ids", ())),
                evaluation_metric=hypothesis_payload.get("evaluation_metric"),
                acceptance_rule=tuple(tuple(pair) for pair in hypothesis_payload.get("acceptance_rule", ())),
                frozen_dimensions=tuple(tuple(pair) for pair in hypothesis_payload.get("frozen_dimensions", ())),
                max_candidates=hypothesis_payload.get("max_candidates"),
                max_search_budget=hypothesis_payload.get("max_search_budget"),
                preregistration_sha256=hypothesis_payload.get("preregistration_sha256"),
            )
            if hypothesis.development_dataset_id != dataset.get("dataset_id"):
                raise ValueError("hypothesis development dataset mismatch")
            if dataset.get("dataset_id") in hypothesis.protected_dataset_ids:
                raise ValueError("development dataset is also declared protected")
            hypothesis.to_svos_contract()
        except (KeyError, TypeError, ValueError) as exc:
            raise TransitionRejected((f"HYPOTHESIS_PREREGISTRATION_INVALID:{exc}",)) from exc

    def transition(
        self,
        experiment_id: str,
        requested_state: CandidateState,
        *,
        actor: str,
        evidence_refs: Mapping[str, Sequence[str]],
        details: Optional[Mapping[str, Any]] = None,
        optimization_conditions: Optional[Mapping[str, Any]] = None,
        at_utc: Optional[str] = None,
    ) -> Mapping[str, Any]:
        """Append a valid monotonic transition, checking state again under the file lock.

        Entering DEVELOPMENT_TESTED or ROBUSTNESS_PASS is coupled to the repository's
        signed admission contract. Callers cannot assert admission with a boolean; the
        registry evaluates the canonical contract itself and stores its hash/evidence.
        """
        if not isinstance(actor, str) or not actor:
            raise ValueError("registry actor is required")
        _safe_id(experiment_id, "experiment id")
        try:
            requested_state = CandidateState(requested_state)
        except (TypeError, ValueError) as exc:
            raise ValueError("requested candidate state is invalid") from exc
        normalized_refs = _normalize_evidence_refs(evidence_refs)
        if details is not None and not isinstance(details, Mapping):
            raise ValueError("transition details must be a mapping")
        if optimization_conditions is not None and not isinstance(optimization_conditions, Mapping):
            raise ValueError("optimization conditions must be a mapping")
        experiment_dir = self._experiment_dir(experiment_id)
        genesis = self.manifest_sha256(experiment_id)
        current = self.state(experiment_id)
        if requested_state is CandidateState.PREREGISTERED and current not in TERMINAL_STATES:
            self._validate_preregistration(experiment_id)
        admission_passed = False
        transition_details = dict(details or {})
        if requested_state in {CandidateState.DEVELOPMENT_TESTED, CandidateState.ROBUSTNESS_PASS}:
            if self.repo_root is None:
                raise TransitionRejected(("OPTIMIZATION_ADMISSION_REPOSITORY_ROOT_REQUIRED",))
            conditions = dict(optimization_conditions or {})
            try:
                actual_protected_access_count = DatasetAccessFirewall(
                    self.root, repo_root=self.repo_root
                ).protected_access_count(experiment_id)
            except (DatasetRegistryError, ValueError) as exc:
                raise TransitionRejected((f"PROTECTED_ACCESS_LEDGER_INVALID:{exc}",)) from exc
            declared_protected_access_count = conditions.get("protected_data_access_count")
            if "protected_data_access_count" in conditions and (
                type(declared_protected_access_count) is not int
                or declared_protected_access_count != actual_protected_access_count
            ):
                raise TransitionRejected(("PROTECTED_DATA_ACCESS_COUNT_MISMATCH",))
            admission_result, contract_sha256, contract_status, contract_snapshot = evaluate_repository_admission_snapshot(
                self.repo_root, conditions
            )
            if not admission_result.eligible:
                raise TransitionRejected(admission_result.blockers)
            if not contract_sha256 or contract_status != "SIGNED" or contract_snapshot is None:
                raise TransitionRejected(("OPTIMIZATION_ADMISSION_CONTRACT_NOT_SIGNED",))
            transition_details["optimization_admission"] = {
                "eligible": True,
                "status": admission_result.status,
                "contract_ref": "config/governance/optimization_admission_contract.yaml",
                "contract_status": contract_status,
                "contract_sha256": contract_sha256,
                "contract_snapshot_utf8": contract_snapshot,
                "conditions": conditions,
                "conditions_sha256": fingerprint(conditions),
            }
            admission_passed = True
        decision = validate_transition(
            current,
            requested_state,
            normalized_refs,
            optimization_admission_passed=admission_passed
        )
        if not decision.allowed:
            raise TransitionRejected(decision.blockers)

        def precondition(existing: list[dict[str, Any]]) -> None:
            if not existing:
                raise CorruptRegistry("registration event is missing")
            live_state = CandidateState(existing[-1]["state_after"])
            if live_state is not current:
                raise TransitionRejected(("CONCURRENT_STATE_CHANGE_RETRY_WITH_NEW_EVENT",))
            live_decision = validate_transition(
                live_state,
                requested_state,
                normalized_refs,
                optimization_admission_passed=admission_passed,
            )
            if not live_decision.allowed:
                raise TransitionRejected(live_decision.blockers)

        payload = {
            "event_type": "TRANSITION",
            "actor": actor,
            "at_utc": at_utc or _utc_now(),
            "state_before": current.value,
            "state_after": requested_state.value,
            "evidence_refs": to_jsonable(normalized_refs),
            "details": to_jsonable(transition_details),
            "optimization_admission_passed": admission_passed,
        }
        try:
            return append_chained_event(
                experiment_dir / "events.jsonl", genesis, payload, precondition=precondition
            )
        except (OSError, HashChainError) as exc:
            raise CorruptRegistry(f"could not append transition for {experiment_id}: {exc}") from exc

    def record_result(
        self,
        result: ExperimentResult,
        *,
        actor: str,
        at_utc: Optional[str] = None,
    ) -> Path:
        """Persist a per-arm result once and append its immutable hash to the ledger."""
        if not isinstance(actor, str) or not actor:
            raise ValueError("registry actor is required")
        _safe_id(result.experiment_id, "experiment id")
        _safe_id(result.strategy_id, "strategy id")
        experiment_dir = self._experiment_dir(result.experiment_id)
        if not (experiment_dir / "manifest.json").exists():
            raise RegistryError("result experiment is not registered")
        manifest = self.load_manifest(result.experiment_id)
        if result.strategy_id != manifest["strategy_id"]:
            raise RegistryError("result strategy does not match experiment manifest")
        expected_config_sha = (
            manifest["baseline"]["canonical_config_sha256"]
            if result.arm is Arm.CONTROL
            else manifest["candidate"]["candidate_config_sha256"]
        )
        if result.candidate_config_sha256 and result.candidate_config_sha256 != expected_config_sha:
            raise RegistryError("result config hash does not match its experiment arm")
        if result.metrics.status.value == "EVALUATED" and result.candidate_config_sha256 != expected_config_sha:
            raise RegistryError("evaluated result must carry its arm's config hash")
        state_before = self.state(result.experiment_id)
        if state_before in TERMINAL_STATES or state_before is CandidateState.OWNER_REVIEW:
            raise RegistryError("results cannot be added after a terminal state or owner review")
        if result.metrics.status.value == "EVALUATED" and state_before is CandidateState.DRAFT and not (
            result.arm is Arm.CONTROL
            and result.dataset_role.value == "DEVELOPMENT"
        ):
            raise RegistryError("only baseline control reproduction may be evaluated before preregistration")
        self._verify_result_provenance(result, state_before)
        result_sha = result.result_sha256
        run_part = _safe_id(result.run_id or result_sha[:16], "result run id")
        filename = f"{result.arm.value}_{run_part}.json"
        result_path = experiment_dir / "results" / filename
        payload = {"result": to_jsonable(result), "result_sha256": result_sha}
        _write_once_json(result_path, payload)
        genesis = self.manifest_sha256(result.experiment_id)

        def precondition(existing: list[dict[str, Any]]) -> None:
            if not existing or CandidateState(existing[-1]["state_after"]) is not state_before:
                raise TransitionRejected(("CONCURRENT_STATE_CHANGE_RESULT_NOT_INDEXED",))

        try:
            append_chained_event(
                experiment_dir / "events.jsonl",
                genesis,
                {
                    "event_type": "RESULT_RECORDED",
                    "actor": actor,
                    "at_utc": at_utc or _utc_now(),
                    "state_before": state_before.value,
                    "state_after": state_before.value,
                    "evidence_refs": {
                        "experiment_result": [str(result_path.relative_to(experiment_dir))],
                        "dataset_manifest": [f"datasets/{result.dataset_id}.json"]
                        if result.metrics.status.value == "EVALUATED" else [],
                        "dataset_access_ledger": [f"dataset_access/{result.dataset_id}.jsonl"]
                        if result.metrics.status.value == "EVALUATED" else [],
                    },
                    "details": {
                        "arm": result.arm.value,
                        "result_sha256": result_sha,
                        "result_path": str(result_path.relative_to(experiment_dir)),
                    },
                },
                precondition=precondition,
            )
        except (OSError, HashChainError) as exc:
            raise CorruptRegistry(f"could not index result for {result.experiment_id}: {exc}") from exc
        return result_path

    def record_promotion_decision(
        self,
        decision: PromotionDecision,
        *,
        actor: str,
        at_utc: Optional[str] = None,
    ) -> Mapping[str, Any]:
        """Append an owner-authored decision without changing any strategy authority."""
        if not isinstance(actor, str) or not actor:
            raise ValueError("registry actor is required")
        _safe_id(decision.experiment_id, "experiment id")
        _safe_id(decision.strategy_id, "strategy id")
        if actor != decision.decided_by:
            raise RegistryError("owner decision actor must match the recorded decision author")
        if self.state(decision.experiment_id) is not CandidateState.OWNER_REVIEW:
            raise RegistryError("promotion decision can only be recorded at OWNER_REVIEW")
        manifest = self.load_manifest(decision.experiment_id)
        if manifest["strategy_id"] != decision.strategy_id:
            raise RegistryError("decision strategy does not match experiment manifest")
        if any(event.get("event_type") == "OWNER_DECISION_RECORDED" for event in self.events(decision.experiment_id)):
            raise RegistryError("an owner decision is already immutably recorded")
        experiment_dir = self._experiment_dir(decision.experiment_id)
        genesis = self.manifest_sha256(decision.experiment_id)

        def precondition(existing: list[dict[str, Any]]) -> None:
            if any(event.get("event_type") == "OWNER_DECISION_RECORDED" for event in existing):
                raise TransitionRejected(("OWNER_DECISION_ALREADY_RECORDED",))
            if not existing or CandidateState(existing[-1]["state_after"]) is not CandidateState.OWNER_REVIEW:
                raise TransitionRejected(("OWNER_REVIEW_STATE_CHANGED",))

        rejected = decision.disposition is PromotionDisposition.REJECT
        resulting_state = (
            CandidateState.REJECTED_OWNER_DECISION if rejected else CandidateState.OWNER_REVIEW
        )
        evidence_refs = {"owner_authority": [decision.authority_ref]}
        if rejected:
            evidence_refs["owner_rejection_record"] = [decision.authority_ref]
        return append_chained_event(
            experiment_dir / "events.jsonl",
            genesis,
            {
                "event_type": "OWNER_DECISION_RECORDED",
                "actor": actor,
                "at_utc": at_utc or _utc_now(),
                "state_before": CandidateState.OWNER_REVIEW.value,
                "state_after": resulting_state.value,
                "evidence_refs": evidence_refs,
                "details": {"decision": to_jsonable(decision), "decision_sha256": decision.decision_sha256},
            },
            precondition=precondition,
        )

    def experiment_ids(self) -> Tuple[str, ...]:
        if not self.experiments_root.exists():
            return ()
        ids = []
        for child in self.experiments_root.iterdir():
            if not child.is_dir():
                continue
            if not (child / "manifest.json").exists():
                raise CorruptRegistry(f"incomplete experiment directory: {child.name}")
            self.events(child.name)
            ids.append(child.name)
        return tuple(sorted(ids))


__all__ = [
    "CorruptRegistry", "ExperimentRegistry", "ImmutableRecordExists", "RegistryError",
    "TransitionRejected",
]
