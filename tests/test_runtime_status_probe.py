"""Narrow tests for runtime_status.probe (AG_PROJECT_LIVE_CONTROL_PLANE_V2).

These prove the RUNTIME_STATUS / GOVERNANCE_STATUS separation:
  - an unavailable API gateway reports UNAVAILABLE for the API-proxied probes and never
    cascades into the governance snapshot or fingerprint;
  - runtime probe results are never part of the governance fingerprint;
  - the probe module has no execution/order capability (no MetaTrader5 / order paths).
No test touches the real network: http_get is injected.
"""
from __future__ import annotations

import ast
import sys
import urllib.error
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from runtime_status.probe import (  # noqa: E402
    STATUS_AVAILABLE,
    STATUS_UNAVAILABLE,
    RuntimeStatus,
    probe_runtime,
)
from validation_orchestrator.live_status import (  # noqa: E402
    compute_fingerprint,
    derive_snapshot,
)
from validation_orchestrator.render import render_markdown  # noqa: E402
from validation_orchestrator.status import StrategyValidationStatus  # noqa: E402


def _status(strategy_id="ST_FAKE_V1"):
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
        demo_authorized=False,
        live_authorized=False,
        next_safe_action="OWNER_REVIEW_FOR_NEXT_GATE",
        agent_required="NONE",
        updated_at_utc="2026-01-01T00:00:00+00:00",
    )


def _snapshot():
    return derive_snapshot(
        repo_root=Path("/fake"),
        git_head=lambda root: "deadbeef",
        git_branch=lambda root: "main",
        untracked_paths=lambda root: (),
        dirty_paths=lambda root: (),
        list_strategy_statuses=lambda: [_status()],
    )


def _refused(url, timeout):
    raise urllib.error.URLError("connection refused")


def _up(url, timeout):
    if url.endswith("/api/health"):
        return 200, {"status": "OK"}
    if url.endswith("/api/broker/status"):
        return 200, {"connected": True, "environment": "DEMO", "reason_code": None}
    if "market-data/candles" in url:
        return 200, {"candles": [{"close": 1.0}]}
    return 404, {}


def _probe(name, probes):
    return next(p for p in probes if p.name == name)


def test_runtime_status_is_governance_impact_none():
    runtime = probe_runtime(repo_root=Path("/tmp/absent"), http_get=_refused)
    assert runtime.governance_impact == "NONE"
    assert {p.name for p in runtime.probes} == {
        "fastapi",
        "mt5",
        "broker",
        "market_data",
        "proposal_ledger",
        "scheduler",
        "ssc",
        "lsmc",
    }


def test_api_down_reports_unavailable_for_api_proxied_probes_without_cascade():
    runtime = probe_runtime(repo_root=Path("/tmp/absent"), http_get=_refused)
    assert _probe("fastapi", runtime.probes).status == STATUS_UNAVAILABLE
    assert _probe("mt5", runtime.probes).status == STATUS_UNAVAILABLE
    assert _probe("broker", runtime.probes).status == STATUS_UNAVAILABLE
    assert _probe("market_data", runtime.probes).status == STATUS_UNAVAILABLE
    assert "API gateway unavailable" in _probe("mt5", runtime.probes).detail
    # No exception escapes: file/import probes still run independently.
    assert all(p.status in (STATUS_AVAILABLE, STATUS_UNAVAILABLE) for p in runtime.probes)


def test_api_up_reports_available_for_api_proxied_probes():
    runtime = probe_runtime(repo_root=Path("/tmp/absent"), http_get=_up)
    assert _probe("fastapi", runtime.probes).status == STATUS_AVAILABLE
    assert _probe("mt5", runtime.probes).status == STATUS_AVAILABLE
    assert _probe("broker", runtime.probes).status == STATUS_AVAILABLE
    assert _probe("market_data", runtime.probes).status == STATUS_AVAILABLE


def test_runtime_probe_does_not_change_governance_fingerprint():
    snap = _snapshot()
    fp = compute_fingerprint(snap)
    runtime_up = probe_runtime(repo_root=Path("/tmp/absent"), http_get=_up)
    runtime_down = probe_runtime(repo_root=Path("/tmp/absent"), http_get=_refused)
    # The governance fingerprint is computed only from the snapshot; runtime objects
    # are not part of it, so two different runtime observations cannot change it.
    assert compute_fingerprint(snap) == fp
    # And the renderer embeds that same governance fingerprint regardless of runtime.
    out_up = render_markdown(snap, fp, runtime_status=runtime_up)
    out_down = render_markdown(snap, fp, runtime_status=runtime_down)
    assert f"<!-- LIVE_STATE_FINGERPRINT: {fp} -->" in out_up
    assert f"<!-- LIVE_STATE_FINGERPRINT: {fp} -->" in out_down


def test_renderer_runtime_section_marked_as_separate_authority():
    snap = _snapshot()
    fp = compute_fingerprint(snap)
    runtime = probe_runtime(repo_root=Path("/tmp/absent"), http_get=_refused)
    out = render_markdown(snap, fp, runtime_status=runtime)
    assert "RUNTIME_STATUS is a **separate authority** from GOVERNANCE_STATUS" in out
    assert "| fastapi |" in out
    assert "| proposal_ledger |" in out


def test_renderer_without_runtime_keeps_wp1_placeholder():
    snap = _snapshot()
    fp = compute_fingerprint(snap)
    out = render_markdown(snap, fp)
    assert "No runtime probe is wired into this generator" in out


def test_probe_module_has_no_execution_or_order_capability():
    source = (REPO_ROOT / "src" / "runtime_status" / "probe.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_roots = ("MetaTrader5", "mt5", "execution", "order")
    imported: list = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    for name in imported:
        root = name.split(".")[0]
        assert not root.startswith(forbidden_roots), (
            f"runtime probe must not import execution/order machinery (found {name!r})"
        )
