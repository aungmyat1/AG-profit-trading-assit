"""Tests for scripts/generate_live_status.py and validation_orchestrator.render.

Exercises renderer determinism and the generator's write-if-changed / --check /
stale-detection behavior against a temp directory -- never the real repository's
docs/status/PROJECT_LIVE_STATUS.md.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from validation_orchestrator.live_status import compute_fingerprint, derive_snapshot  # noqa: E402
from validation_orchestrator.render import render_markdown  # noqa: E402
from validation_orchestrator.status import StrategyValidationStatus  # noqa: E402


def _load_generator_module():
    spec = importlib.util.spec_from_file_location(
        "generate_live_status", REPO_ROOT / "scripts" / "generate_live_status.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _status(strategy_id="ST_FAKE_V1", demo_authorized=False):
    return StrategyValidationStatus(
        strategy_id=strategy_id,
        strategy_version="1.0.0",
        lifecycle_stage="OFFLINE_RESEARCH",
        current_gate=None,
        furthest_verified_gate="G1",
        validation_state="GATES_ALL_PASS_NO_BLOCKERS",
        blocking_reasons=(),
        evidence_status="GATES_ALL_PASS",
        dataset_role_status="NOT_TRACKED_BY_WP1",
        lineage_status="NOT_TRACKED_BY_WP1",
        holdout_status="NOT_TRACKED_BY_WP1",
        demo_authorized=demo_authorized,
        live_authorized=False,
        next_safe_action="OWNER_REVIEW_FOR_NEXT_GATE",
        agent_required="NONE",
        updated_at_utc="2026-01-01T00:00:00+00:00",
    )


def _snapshot(**overrides):
    kwargs = dict(
        repo_root=Path("/fake"),
        git_head=lambda root: "deadbeef",
        git_branch=lambda root: "main",
        untracked_paths=lambda root: (),
        dirty_paths=lambda root: (),
        list_strategy_statuses=lambda: [_status()],
    )
    kwargs.update(overrides)
    return derive_snapshot(**kwargs)


def test_renderer_is_deterministic_for_a_fixed_snapshot():
    snap = _snapshot()
    fp = compute_fingerprint(snap)
    out1 = render_markdown(snap, fp)
    out2 = render_markdown(snap, fp)
    assert out1 == out2


def test_renderer_embeds_fingerprint_comment():
    snap = _snapshot()
    fp = compute_fingerprint(snap)
    out = render_markdown(snap, fp)
    assert f"<!-- LIVE_STATE_FINGERPRINT: {fp} -->" in out


def test_renderer_marks_foreign_wip_as_not_authoritative():
    snap = _snapshot(untracked_paths=lambda root: ("artifacts/ES_S4_COMPARISON/x.json",))
    fp = compute_fingerprint(snap)
    out = render_markdown(snap, fp)
    assert "ES_S4_COMPARISON/x.json" in out
    assert "NOT YET AUTHORITATIVE" in out


def test_freshness_missing_when_file_absent(tmp_path):
    module = _load_generator_module()
    path = tmp_path / "PROJECT_LIVE_STATUS.md"
    assert module.freshness(path, "abc123") == "LIVE_STATUS_MISSING"


def test_freshness_stale_on_fingerprint_mismatch(tmp_path):
    module = _load_generator_module()
    path = tmp_path / "PROJECT_LIVE_STATUS.md"
    path.write_text("<!-- LIVE_STATE_FINGERPRINT: " + "0" * 64 + " -->\nold content\n", encoding="utf-8")
    assert module.freshness(path, "1" * 64) == "LIVE_STATUS_STALE"


def test_freshness_fresh_on_fingerprint_match(tmp_path):
    module = _load_generator_module()
    path = tmp_path / "PROJECT_LIVE_STATUS.md"
    fp = "2" * 64
    path.write_text(f"<!-- LIVE_STATE_FINGERPRINT: {fp} -->\ncontent\n", encoding="utf-8")
    assert module.freshness(path, fp) == "LIVE_STATUS_FRESH"


def test_timestamp_only_change_does_not_mark_stale(tmp_path):
    """Two snapshots differing only in generated_at_utc/updated_at_utc must produce the
    same fingerprint and therefore the same freshness verdict against a written file."""
    module = _load_generator_module()
    snap_a = _snapshot(list_strategy_statuses=lambda: [_status()])
    fp_a = compute_fingerprint(snap_a)
    rendered_a = render_markdown(snap_a, fp_a)
    path = tmp_path / "PROJECT_LIVE_STATUS.md"
    path.write_text(rendered_a, encoding="utf-8")

    snap_b = _snapshot(list_strategy_statuses=lambda: [_status()])  # re-derived "later"
    fp_b = compute_fingerprint(snap_b)
    assert fp_a == fp_b
    assert module.freshness(path, fp_b) == "LIVE_STATUS_FRESH"


def test_authorization_change_marks_existing_file_stale(tmp_path):
    module = _load_generator_module()
    snap_a = _snapshot(list_strategy_statuses=lambda: [_status(demo_authorized=False)])
    fp_a = compute_fingerprint(snap_a)
    path = tmp_path / "PROJECT_LIVE_STATUS.md"
    path.write_text(render_markdown(snap_a, fp_a), encoding="utf-8")

    snap_b = _snapshot(list_strategy_statuses=lambda: [_status(demo_authorized=True)])
    fp_b = compute_fingerprint(snap_b)
    assert module.freshness(path, fp_b) == "LIVE_STATUS_STALE"
