"""Focused tests for scripts/resource_guard.py (AG Resource Management Policy V1).

All probes are injected; no real lock, RAM reading, or process is touched.
"""
import importlib.util
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "resource_guard.py"
_spec = importlib.util.spec_from_file_location("resource_guard", _PATH)
rg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rg)


def mem(avail, total=7379):
    return lambda: (total, avail)


def alive(_pid):
    return True


def dead(_pid):
    return False


def unknown(_pid):
    return None


def _acquire(lock, avail=4000, cls="R2", agent="CODEX_LOCAL", mission="M1", pid=111,
             pid_probe=alive, **kw):
    return rg.acquire(lock, agent=agent, mission=mission, resource_class=cls, pid=pid,
                      memory_probe=mem(avail), pid_probe=pid_probe, repo="r", branch="b", **kw)


@pytest.fixture
def lock(tmp_path):
    return tmp_path / "artifacts" / "runtime" / "resource_lock.json"


def test_policy_thresholds_are_frozen():
    assert rg.POLICY_THRESHOLDS_MB == {"R0": 0, "R1": 1200, "R2": 2500, "R3": 3000}


def test_experiment_gate_is_never_lowered():
    assert rg.required_ram_mb("R3", 5000) == 5000
    assert rg.required_ram_mb("R3", 100) == 3000
    assert rg.required_ram_mb("R2", None) == 2500


def test_r1_blocked_below_gate_writes_nothing(lock):
    out = _acquire(lock, avail=433, cls="R1")
    assert out["RESOURCE_GATE"] == "BLOCKED_RESOURCE"
    assert out["ACQUIRED"] is False
    assert out["REQUIRED_RAM_MB"] == 1200
    assert not lock.exists()


def test_experiment_specific_gate_blocks_even_when_policy_passes(lock):
    out = _acquire(lock, avail=3500, cls="R3", experiment_min_mb=4000)
    assert out["RESOURCE_GATE"] == "BLOCKED_RESOURCE"
    assert not lock.exists()


def test_undetermined_ram_fails_closed(lock):
    out = rg.acquire(lock, agent="CODEX_LOCAL", mission="M1", resource_class="R1", pid=1,
                     memory_probe=lambda: (None, None), pid_probe=alive, repo="r", branch="b")
    assert out["RESOURCE_GATE"] == "BLOCKED_RESOURCE"
    assert not lock.exists()


def test_r0_needs_no_lock(lock):
    out = _acquire(lock, avail=10, cls="R0")
    assert out["RESOURCE_GATE"] == "PASS"
    assert out["ACQUIRED"] is False
    assert not lock.exists()


def test_acquire_writes_schema_and_second_acquire_is_busy(lock):
    first = _acquire(lock)
    assert first["ACQUIRED"] is True and first["RESOURCE_GATE"] == "PASS"
    data = json.loads(lock.read_text())
    for field in ("version", "owner_agent", "mission_id", "resource_class", "repo", "branch",
                  "pid", "started_at_utc", "heartbeat_at_utc", "command_summary"):
        assert field in data
    assert data["owner_agent"] == "CODEX_LOCAL" and data["resource_class"] == "R2"

    second = _acquire(lock, agent="CLAUDE_CODE", mission="M2", cls="R3")
    assert second["RESOURCE_GATE"] == "BUSY" and second["ACQUIRED"] is False
    assert json.loads(lock.read_text()) == data  # untouched


def test_lost_race_does_not_overwrite(lock, monkeypatch):
    lock.parent.mkdir(parents=True)
    # Lock appears between classification and atomic create.
    monkeypatch.setattr(rg, "classify_lock",
                        lambda *a, **k: {"status": rg.NO_LOCK, "lock": None, "reason": "x"})
    lock.write_text('{"winner": true}')
    out = _acquire(lock)
    assert out["RESOURCE_GATE"] == "BUSY" and out["ACQUIRED"] is False
    assert json.loads(lock.read_text()) == {"winner": True}


def test_lock_states(lock):
    assert rg.classify_lock(lock)["status"] == rg.NO_LOCK
    _acquire(lock)
    assert rg.classify_lock(lock, pid_probe=alive)["status"] == rg.ACTIVE_LOCK
    assert rg.classify_lock(lock, pid_probe=dead)["status"] == rg.STALE_LOCK
    assert rg.classify_lock(lock, pid_probe=unknown)["status"] == rg.UNKNOWN_LOCK
    later = datetime.now(timezone.utc) + timedelta(seconds=rg.HEARTBEAT_MAX_AGE_SECONDS + 60)
    assert rg.classify_lock(lock, pid_probe=alive, now=later)["status"] == rg.UNKNOWN_LOCK


def test_malformed_lock_is_unknown_and_blocks_heavy(lock):
    lock.parent.mkdir(parents=True)
    lock.write_text("not json")
    assert rg.classify_lock(lock)["status"] == rg.UNKNOWN_LOCK
    out = _acquire(lock, cls="R3")
    assert out["RESOURCE_GATE"] == "BUSY" and out["ACQUIRED"] is False
    assert lock.read_text() == "not json"


def test_stale_lock_blocks_until_explicitly_cleared(lock):
    _acquire(lock)
    out = _acquire(lock, agent="CLAUDE_CODE", mission="M2", pid_probe=dead)
    assert out["RESOURCE_GATE"] == "BUSY" and out["LOCK_STATUS_BEFORE"] == rg.STALE_LOCK


def test_clear_stale_refuses_active_and_unknown(lock):
    _acquire(lock)
    for probe in (alive, unknown):
        out = rg.clear_stale(lock, pid_probe=probe)
        assert out["CLEARED"] is False
        assert lock.exists()


def test_clear_stale_removes_only_stale_and_reports_evidence(lock):
    _acquire(lock)
    out = rg.clear_stale(lock, pid_probe=dead)
    assert out["CLEARED"] is True
    assert out["STALE_LOCK_EVIDENCE"]["mission_id"] == "M1"
    assert "no longer exists" in out["REASON"]
    assert not lock.exists()


def test_non_owner_release_fails_closed(lock):
    _acquire(lock)
    assert rg.release(lock, agent="CLAUDE_CODE", mission="M1")["RELEASED"] is False
    assert rg.release(lock, agent="CODEX_LOCAL", mission="OTHER")["RELEASED"] is False
    assert rg.release(lock, agent="CODEX_LOCAL", mission="M1", pid=999)["RELEASED"] is False
    assert lock.exists()


def test_owner_release(lock):
    _acquire(lock)
    out = rg.release(lock, agent="CODEX_LOCAL", mission="M1", pid=111)
    assert out["RELEASED"] is True
    assert not lock.exists()


def test_heartbeat_owner_only(lock):
    _acquire(lock)
    assert rg.heartbeat(lock, agent="CLAUDE_CODE", mission="M1")["HEARTBEAT_UPDATED"] is False
    assert rg.heartbeat(lock, agent="CODEX_LOCAL", mission="M1")["HEARTBEAT_UPDATED"] is True


def test_status_reports_gates_and_lock(lock):
    out = rg.status(lock, memory_probe=mem(433), pid_probe=alive)
    assert out["AVAILABLE_RAM_MB"] == 433
    assert out["R0_GATE"] == "PASS"
    assert out["R1_GATE"] == out["R2_GATE"] == out["R3_GATE"] == "BLOCKED_RESOURCE"
    assert out["LOCK_STATUS"] == rg.NO_LOCK
    assert out["OTHER_HEAVY_JOB_DETECTED"] == "NONE_REGISTERED"
    _acquire(lock, cls="R3")
    out = rg.status(lock, memory_probe=mem(433), pid_probe=alive)
    assert out["LOCK_STATUS"] == rg.ACTIVE_LOCK and out["LOCK_OWNER"] == "CODEX_LOCAL"
    assert out["OTHER_HEAVY_JOB_DETECTED"] == "TRUE"


def test_current_process_is_alive():
    assert rg.pid_alive(os.getpid()) is True
    assert rg.pid_alive(0) is None


def test_no_process_termination_surface():
    src = _PATH.read_text(encoding="utf-8")
    for forbidden in ("TerminateProcess", "taskkill", "os.killpg", "SIGKILL", "SIGTERM",
                      ".terminate(", "order_send", "order_check"):
        assert forbidden not in src
    # The only kill call is the signal-0 existence probe.
    assert src.count(".kill(") == src.count("os.kill(pid, 0)") == 1
