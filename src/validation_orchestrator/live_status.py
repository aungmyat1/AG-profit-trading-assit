"""AVO project-control-plane snapshot model (AG_PROJECT_LIVE_CONTROL_PLANE_V1).

This module answers "what is the deterministic, whole-repository live state right
now?" by composing:
  - status.derive_all_status()            (per-strategy validation status, AVO-WP1)
  - git (HEAD, branch, untracked paths)    (repository provenance)
  - reconciliation metadata (see RepositoryProvenance) describing known mixed
    integration commits and the audit that reconciled them

It never re-derives strategy validation logic itself (that stays in status.py) and
never interprets untracked/foreign working-tree content as authoritative evidence --
see ForeignWipEntry. It performs no writes, no git mutation, no broker calls, and no
promotion decisions. Callers needing Markdown output should use render.py; callers
needing a stable identity for stale-detection should use compute_fingerprint(), which
excludes every timestamp field by construction.
"""
from __future__ import annotations

import importlib
import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

import yaml

from post_asian_pilot.fingerprint import fingerprint as _sha256_fingerprint
from validation_orchestrator.status import StrategyValidationStatus, derive_all_status

SCHEMA_VERSION = "AG_LIVE_STATUS_SNAPSHOT_V2"

# Known mixed-scope integration commits and the audit that reconciled them. This is
# reconciliation metadata, not a permanent code dependency on any one SHA -- add a new
# tuple entry (with its own reconciliation artifact) the next time a mixed commit needs
# recording; never delete a historical entry to make the snapshot look cleaner.
KNOWN_MIXED_COMMITS: Tuple[str, ...] = ("873dd68",)
RECONCILIATION_ARTIFACT = "docs/status/RECONCILIATION_AUDIT_POST_BB6AC0F.md"
RECONCILIATION_STATUS = "MIXED_BUT_RECONCILED"


@dataclass(frozen=True)
class RepositoryProvenance:
    head: str
    branch: str
    working_tree_clean: bool
    foreign_wip_paths: Tuple[str, ...]
    mixed_commits: Tuple[str, ...]
    reconciliation_status: str
    reconciliation_artifact: str

    def semantic_tuple(self) -> tuple:
        return (
            self.head,
            self.branch,
            self.working_tree_clean,
            self.foreign_wip_paths,
            self.mixed_commits,
            self.reconciliation_status,
            self.reconciliation_artifact,
        )


@dataclass(frozen=True)
class ProposalPlatformEntry:
    """One strategy's V1.2 proposal-platform posture, resolved from repository authority
    only (strategy YAML `authority` block + StrategyAuthority + adapter importability).
    Purely informational -- never an execution or validation fact, and never derived
    from runtime health."""

    strategy_id: str
    proposal_capable: bool
    proposal_generation_authorized: bool
    economic_edge_established: bool
    execution_eligible: bool
    broker_mutation_blocked: bool

    def semantic_tuple(self) -> tuple:
        return (
            self.strategy_id,
            self.proposal_capable,
            self.proposal_generation_authorized,
            self.economic_edge_established,
            self.execution_eligible,
            self.broker_mutation_blocked,
        )


@dataclass(frozen=True)
class LiveStatusSnapshot:
    schema_version: str
    generated_at_utc: str
    provenance: RepositoryProvenance
    strategies: Tuple[StrategyValidationStatus, ...]
    proposal_platform: Tuple[ProposalPlatformEntry, ...]
    blockers: Tuple[str, ...]
    owner_decisions_required: Tuple[str, ...]
    next_safe_actions: Tuple[str, ...]

    def semantic_tuple(self) -> tuple:
        """Everything except generated_at_utc/updated_at_utc -- the fingerprint basis."""
        return (
            self.schema_version,
            self.provenance.semantic_tuple(),
            tuple(s.semantic_tuple() for s in self.strategies),
            tuple(p.semantic_tuple() for p in self.proposal_platform),
            self.blockers,
            self.owner_decisions_required,
            self.next_safe_actions,
        )


def _run_git(repo_root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=str(repo_root)).decode().strip()


def default_git_head(repo_root: Path) -> str:
    return _run_git(repo_root, "rev-parse", "HEAD")


def default_git_branch(repo_root: Path) -> str:
    return _run_git(repo_root, "rev-parse", "--abbrev-ref", "HEAD")


def default_untracked_paths(repo_root: Path) -> Tuple[str, ...]:
    """Untracked (foreign/candidate WIP) paths only -- never staged/modified paths,
    since those are ordinary in-progress mission work, not foreign WIP by definition."""
    out = _run_git(repo_root, "ls-files", "--others", "--exclude-standard")
    return tuple(sorted(p for p in out.splitlines() if p))


def default_working_tree_dirty_paths(repo_root: Path) -> Tuple[str, ...]:
    out = _run_git(repo_root, "status", "--porcelain")
    return tuple(sorted(line[3:] for line in out.splitlines() if line))


def _derive_provenance(
    repo_root: Path,
    *,
    git_head: Callable[[Path], str],
    git_branch: Callable[[Path], str],
    untracked_paths: Callable[[Path], Tuple[str, ...]],
    dirty_paths: Callable[[Path], Tuple[str, ...]],
) -> RepositoryProvenance:
    foreign_wip = untracked_paths(repo_root)
    dirty = dirty_paths(repo_root)
    return RepositoryProvenance(
        head=git_head(repo_root),
        branch=git_branch(repo_root),
        working_tree_clean=(len(dirty) == 0),
        foreign_wip_paths=foreign_wip,
        mixed_commits=KNOWN_MIXED_COMMITS,
        reconciliation_status=RECONCILIATION_STATUS,
        reconciliation_artifact=RECONCILIATION_ARTIFACT,
    )


def _aggregate_blockers(strategies: Sequence[StrategyValidationStatus]) -> Tuple[str, ...]:
    seen: List[str] = []
    for status in strategies:
        for reason in status.blocking_reasons:
            item = f"{status.strategy_id}:{reason}"
            if item not in seen:
                seen.append(item)
    return tuple(seen)


def _aggregate_next_safe_actions(strategies: Sequence[StrategyValidationStatus]) -> Tuple[str, ...]:
    seen: List[str] = []
    for status in strategies:
        item = f"{status.strategy_id}:{status.next_safe_action}"
        if item not in seen:
            seen.append(item)
    return tuple(seen)


def _owner_decisions_required(
    strategies: Sequence[StrategyValidationStatus], provenance: RepositoryProvenance
) -> Tuple[str, ...]:
    decisions: List[str] = []
    for status in strategies:
        if status.next_safe_action in ("OWNER_REVIEW_REQUIRED", "OWNER_REVIEW_FOR_NEXT_GATE", "RESOLVE_PROMOTION_BLOCKERS"):
            decisions.append(f"{status.strategy_id}: {status.next_safe_action}")
    if provenance.foreign_wip_paths:
        decisions.append(
            "Foreign/concurrent WIP present -- confirm ownership and freeze/discard "
            "intent before it is treated as authoritative: "
            + ", ".join(provenance.foreign_wip_paths)
        )
    return tuple(decisions)


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_PROPOSAL_PLATFORM_STRATEGIES = ("ST_SESSION_SWEEP_CONTINUATION_V1", "ST_LARGE_SMC_V1")
_ADAPTER_BY_STRATEGY = {
    "ST_SESSION_SWEEP_CONTINUATION_V1": "proposal_envelope.adapters.ssc_adapter",
    "ST_LARGE_SMC_V1": "proposal_envelope.adapters.large_smc_research_adapter",
}


def _adapter_importable(module_name: str) -> bool:
    try:
        importlib.import_module(module_name)
        return True
    except Exception:  # noqa: BLE001 -- adapter absence fails closed to not-capable
        return False


def _read_proposal_generation_authorized(repo_root: Path, strategy_id: str) -> bool:
    """Read strategies/<id>.yaml `authority.proposal_generation_authorized`. An absent
    key means 'not explicitly denied' (informational proposal generation permitted); an
    explicit False (e.g. ST_LARGE_SMC_V1) denies it. Unreadable config fails closed to
    False."""
    path = repo_root / "strategies" / f"{strategy_id}.yaml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return False
    if not isinstance(data, dict):
        return False
    authority = data.get("authority")
    if isinstance(authority, dict) and "proposal_generation_authorized" in authority:
        return bool(authority["proposal_generation_authorized"])
    return True


def derive_proposal_platform(
    repo_root: Path, strategies: Sequence[StrategyValidationStatus]
) -> Tuple[ProposalPlatformEntry, ...]:
    """Resolve the V1.2 proposal-platform posture for the strategies that have a
    canonical proposal adapter, from repository authority only -- never from runtime
    health. Only strategies present in `strategies` are reported."""
    from proposal_envelope.strategy_authority import resolve_strategy_authority

    by_id = {s.strategy_id: s.strategy_version for s in strategies}
    entries: List[ProposalPlatformEntry] = []
    for strategy_id in _PROPOSAL_PLATFORM_STRATEGIES:
        if strategy_id not in by_id:
            continue
        authority = resolve_strategy_authority(
            strategy_id, by_id[strategy_id] or "", repo_root=str(repo_root)
        )
        entries.append(
            ProposalPlatformEntry(
                strategy_id=strategy_id,
                proposal_capable=_adapter_importable(_ADAPTER_BY_STRATEGY[strategy_id]),
                proposal_generation_authorized=_read_proposal_generation_authorized(
                    repo_root, strategy_id
                ),
                economic_edge_established=authority.economic_edge_established,
                execution_eligible=authority.execution_eligible,
                broker_mutation_blocked=authority.broker_mutation_blocked,
            )
        )
    return tuple(entries)


def derive_snapshot(
    *,
    repo_root: Optional[Path] = None,
    git_head: Callable[[Path], str] = default_git_head,
    git_branch: Callable[[Path], str] = default_git_branch,
    untracked_paths: Callable[[Path], Tuple[str, ...]] = default_untracked_paths,
    dirty_paths: Callable[[Path], Tuple[str, ...]] = default_working_tree_dirty_paths,
    list_strategy_statuses: Callable[[], Sequence[StrategyValidationStatus]] = derive_all_status,
    proposal_platform_resolver: Callable[
        [Path, Sequence[StrategyValidationStatus]], Tuple[ProposalPlatformEntry, ...]
    ] = derive_proposal_platform,
) -> LiveStatusSnapshot:
    """Derives the current deterministic LiveStatusSnapshot.

    All repository/git access and strategy-status derivation is delegated to
    injectable collaborators (real defaults shown above) so tests can exercise every
    branch -- clean tree, dirty tree, foreign WIP, unknown strategy, missing evidence --
    without touching the real repository or git."""
    root = repo_root or Path(__file__).resolve().parents[2]
    strategies = tuple(list_strategy_statuses())
    provenance = _derive_provenance(
        root,
        git_head=git_head,
        git_branch=git_branch,
        untracked_paths=untracked_paths,
        dirty_paths=dirty_paths,
    )
    proposal_platform = proposal_platform_resolver(root, strategies)
    return LiveStatusSnapshot(
        schema_version=SCHEMA_VERSION,
        generated_at_utc=_now_utc_iso(),
        provenance=provenance,
        strategies=strategies,
        proposal_platform=proposal_platform,
        blockers=_aggregate_blockers(strategies),
        owner_decisions_required=_owner_decisions_required(strategies, provenance),
        next_safe_actions=_aggregate_next_safe_actions(strategies),
    )


def compute_fingerprint(snapshot: LiveStatusSnapshot) -> str:
    """Stable identity of a snapshot's meaningful state, excluding every timestamp.
    Two snapshots derived from unchanged evidence must fingerprint identically; any
    change to HEAD, a registry/lifecycle value, a validation state, an authorization
    flag, a campaign/evidence state, or a blocker must change this value."""
    return _sha256_fingerprint(snapshot.semantic_tuple())
