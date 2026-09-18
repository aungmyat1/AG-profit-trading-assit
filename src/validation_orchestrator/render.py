"""Deterministic Markdown renderer for LiveStatusSnapshot.

Pure function of (snapshot, fingerprint[, runtime_status]) -> str. No I/O, no git, no
evidence reads -- everything it needs is already on the snapshot (and the optional
runtime-status object, which is a separate read-only observation layer, never part of
the governance fingerprint). This keeps render output reproducible for a given input,
independent of when or how many times it is called.
"""
from __future__ import annotations

from typing import Optional

from validation_orchestrator.live_status import LiveStatusSnapshot

_HEADER = "<!-- GENERATED FILE — DO NOT MANUALLY EDIT. Regenerate with scripts/generate_live_status.py -->"


def _fence(rows, columns):
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join(["---"] * len(columns)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def render_markdown(
    snapshot: LiveStatusSnapshot, fingerprint: str, runtime_status: Optional["object"] = None
) -> str:
    p = snapshot.provenance
    lines = [
        _HEADER,
        f"<!-- LIVE_STATE_FINGERPRINT: {fingerprint} -->",
        "",
        "# Project Live Status",
        "",
        f"Schema: `{snapshot.schema_version}`  ",
        f"Generated: {snapshot.generated_at_utc}",
        "",
        "## 1. Repository Identity",
        "",
        f"- Branch: `{p.branch}`",
        f"- HEAD: `{p.head}`",
        f"- Working tree clean: `{p.working_tree_clean}`",
        "",
        "## 2. Repository Provenance",
        "",
        f"- Reconciled through: `{p.reconciliation_artifact}`",
        f"- Reconciliation status: `{p.reconciliation_status}`",
        "- Known mixed integration commits: " + (", ".join(f"`{c}`" for c in p.mixed_commits) or "none"),
        "",
        "## 3. Runtime Status",
        "",
    ]
    if runtime_status is None:
        lines.append(
            "- No runtime probe is wired into this generator (AVO-WP1 scope). "
            "Runtime/broker/feed status is out of scope for this snapshot."
        )
    else:
        lines += [
            "- RUNTIME_STATUS is a **separate authority** from GOVERNANCE_STATUS. A probe "
            "result here never changes `validation_state`, `demo_authorized`, "
            "`live_authorized`, blockers, or next-safe-actions (sections 5/8/11/12), and "
            "is excluded from the governance state fingerprint below.",
            f"- Checked at: `{runtime_status.checked_at_utc}`",
            "",
        ]
        probe_rows = [
            (probe.name, probe.status, probe.detail) for probe in runtime_status.probes
        ]
        lines.append(_fence(probe_rows, ["subsystem", "status", "detail"]))
    lines += [
        "",
        "## 4. Project Readiness Gates",
        "",
        "- Readiness gates (R0-R9) are owned by `docs/PROJECT_ROADMAP.md`; this "
        "generator does not duplicate that matrix. See the roadmap for current gate "
        "definitions.",
        "",
        "## 5. Strategy Validation Matrix",
        "",
    ]
    rows = [
        (
            s.strategy_id,
            s.strategy_version or "-",
            s.lifecycle_stage or "-",
            s.validation_state,
            s.current_gate or "-",
            s.furthest_verified_gate or "-",
            s.demo_authorized,
            s.live_authorized,
            s.next_safe_action,
        )
        for s in snapshot.strategies
    ]
    lines.append(
        _fence(
            rows,
            [
                "strategy_id",
                "version",
                "lifecycle_stage",
                "validation_state",
                "current_gate",
                "furthest_verified_gate",
                "demo_authorized",
                "live_authorized",
                "next_safe_action",
            ],
        )
    )
    lines += [
        "",
        "## 6. Proposal Platform Status (V1.2)",
        "",
        "- Informational proposal capability (`proposal_capable`) is independent of "
        "economic edge (`economic_edge_established`) and execution eligibility "
        "(`execution_eligible`): a `proposal_capable = true` entry can still be "
        "`economic_edge_established = false` and `execution_eligible = false`. "
        "Proposal generation is OBSERVATION ONLY and grants no validation or "
        "execution authority.",
    ]
    if snapshot.proposal_platform:
        lines.append("")
        lines.append(
            _fence(
                [
                    (
                        e.strategy_id,
                        e.proposal_capable,
                        e.proposal_generation_authorized,
                        e.economic_edge_established,
                        e.execution_eligible,
                        e.broker_mutation_blocked,
                    )
                    for e in snapshot.proposal_platform
                ],
                [
                    "strategy_id",
                    "proposal_capable",
                    "proposal_generation_authorized",
                    "economic_edge_established",
                    "execution_eligible",
                    "broker_mutation_blocked",
                ],
            )
        )
    else:
        lines.append("- No V1.2 proposal-platform entries resolved.")
    lines += [
        "",
        "## 7. Campaign / Evidence State",
        "",
        "- Campaign-level evidence (observation counts, friction-campaign day counts) "
        "is not yet tracked by AVO-WP1 (`dataset_role_status`/`lineage_status`/"
        "`holdout_status` are reported as `NOT_TRACKED_BY_WP1` per strategy above). "
        "See `docs/status/RECONCILIATION_AUDIT_POST_BB6AC0F.md` section 6 for the "
        "point-in-time campaign snapshot until a canonical multi-strategy reader "
        "exists.",
        "",
        "## 8. Active Blockers",
        "",
    ]
    if snapshot.blockers:
        lines += [f"- {b}" for b in snapshot.blockers]
    else:
        lines.append("- None reported.")
    lines += [
        "",
        "## 9. Concurrent / Foreign WIP",
        "",
    ]
    if p.foreign_wip_paths:
        for path in p.foreign_wip_paths:
            lines.append(f"- `{path}` — UNCOMMITTED / NOT YET AUTHORITATIVE")
    else:
        lines.append("- None detected.")
    lines += [
        "",
        "## 10. Owner Decisions Required",
        "",
    ]
    if snapshot.owner_decisions_required:
        lines += [f"- {d}" for d in snapshot.owner_decisions_required]
    else:
        lines.append("- None.")
    lines += [
        "",
        "## 11. Next Safe Actions",
        "",
    ]
    if snapshot.next_safe_actions:
        lines += [f"- {a}" for a in snapshot.next_safe_actions]
    else:
        lines.append("- None.")
    lines += [
        "",
        "## 12. Execution Authority",
        "",
    ]
    auth_rows = [(s.strategy_id, s.demo_authorized, s.live_authorized) for s in snapshot.strategies]
    lines.append(_fence(auth_rows, ["strategy_id", "demo_authorized", "live_authorized"]))
    lines += [
        "",
        "## 13. Generator Provenance",
        "",
        f"- Generator: `scripts/generate_live_status.py` (schema `{snapshot.schema_version}`)",
        f"- State fingerprint: `{fingerprint}`",
        "- Fingerprint excludes `generated_at_utc` and every per-strategy "
        "`updated_at_utc`; it changes only when meaningful state changes.",
        "",
    ]
    return "\n".join(lines)
