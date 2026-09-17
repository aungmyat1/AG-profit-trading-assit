"""Deterministic Markdown renderer for LiveStatusSnapshot.

Pure function of (snapshot, fingerprint) -> str. No I/O, no git, no evidence reads --
everything it needs is already on the snapshot. This keeps render output reproducible
for a given snapshot, independent of when or how many times it is called.
"""
from __future__ import annotations

from validation_orchestrator.live_status import LiveStatusSnapshot

_HEADER = "<!-- GENERATED FILE — DO NOT MANUALLY EDIT. Regenerate with scripts/generate_live_status.py -->"


def _fence(rows, columns):
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join(["---"] * len(columns)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def render_markdown(snapshot: LiveStatusSnapshot, fingerprint: str) -> str:
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
        "- No runtime probe is wired into this generator (AVO-WP1 scope). "
        "Runtime/broker/feed status is out of scope for this snapshot.",
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
        "## 6. Campaign / Evidence State",
        "",
        "- Campaign-level evidence (observation counts, friction-campaign day counts) "
        "is not yet tracked by AVO-WP1 (`dataset_role_status`/`lineage_status`/"
        "`holdout_status` are reported as `NOT_TRACKED_BY_WP1` per strategy above). "
        "See `docs/status/RECONCILIATION_AUDIT_POST_BB6AC0F.md` section 6 for the "
        "point-in-time campaign snapshot until a canonical multi-strategy reader "
        "exists.",
        "",
        "## 7. Active Blockers",
        "",
    ]
    if snapshot.blockers:
        lines += [f"- {b}" for b in snapshot.blockers]
    else:
        lines.append("- None reported.")
    lines += [
        "",
        "## 8. Concurrent / Foreign WIP",
        "",
    ]
    if p.foreign_wip_paths:
        for path in p.foreign_wip_paths:
            lines.append(f"- `{path}` — UNCOMMITTED / NOT YET AUTHORITATIVE")
    else:
        lines.append("- None detected.")
    lines += [
        "",
        "## 9. Owner Decisions Required",
        "",
    ]
    if snapshot.owner_decisions_required:
        lines += [f"- {d}" for d in snapshot.owner_decisions_required]
    else:
        lines.append("- None.")
    lines += [
        "",
        "## 10. Next Safe Actions",
        "",
    ]
    if snapshot.next_safe_actions:
        lines += [f"- {a}" for a in snapshot.next_safe_actions]
    else:
        lines.append("- None.")
    lines += [
        "",
        "## 11. Execution Authority",
        "",
    ]
    auth_rows = [(s.strategy_id, s.demo_authorized, s.live_authorized) for s in snapshot.strategies]
    lines.append(_fence(auth_rows, ["strategy_id", "demo_authorized", "live_authorized"]))
    lines += [
        "",
        "## 12. Generator Provenance",
        "",
        f"- Generator: `scripts/generate_live_status.py` (schema `{snapshot.schema_version}`)",
        f"- State fingerprint: `{fingerprint}`",
        "- Fingerprint excludes `generated_at_utc` and every per-strategy "
        "`updated_at_utc`; it changes only when meaningful state changes.",
        "",
    ]
    return "\n".join(lines)
