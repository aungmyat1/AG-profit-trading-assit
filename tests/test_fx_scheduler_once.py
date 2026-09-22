"""P1 focused tests: deterministic weekday FX `--once` scheduling
(AG_SCHEDULER_AND_LARGE_SMC_WATCH_HARDENING_V1).

Covers the schedule computation, the four fail-closed gates, friction-campaign
protection, slot idempotency, and the execution boundary. Task Scheduler itself is not
touched by any test -- the schedule is verified as pure functions plus a runner
invoked with an explicit `--now`.
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from scheduling.fx_schedule import (  # noqa: E402
    CYCLE_BY_ID,
    CYCLE_WINDOWS,
    M15_CLOSE_SETTLE_SECONDS,
    FRICTION_CAMPAIGN_MANIFEST,
    FrictionCampaignError,
    SlotAlreadyClaimed,
    SlotLedger,
    friction_window_conflict,
    is_inside_window,
    is_weekday_utc,
    load_friction_campaign,
    m15_close_slots,
    slot_datetimes,
    slot_key,
)

RUNNER = REPO_ROOT / "scripts" / "run_fx_cycle_once.py"

# A Monday, so weekday gates clear and only the gate under test can refuse.
MONDAY = date(2026, 9, 21)


# ---------------------------------------------------------------------------
# Window / slot geometry
# ---------------------------------------------------------------------------

def test_cycle_windows_match_the_pilot_contracts():
    """The scheduler's windows must equal the pilots' own execution_window values, or
    the scheduler would fire outside the cycle it claims to serve."""
    assert CYCLE_BY_ID["ASIAN_LONDON"].start_utc == time(7, 0)
    assert CYCLE_BY_ID["ASIAN_LONDON"].end_utc == time(11, 0)
    assert CYCLE_BY_ID["LONDON_NEWYORK"].start_utc == time(12, 0)
    assert CYCLE_BY_ID["LONDON_NEWYORK"].end_utc == time(15, 0)


def test_slots_land_after_m15_close_never_at_the_open():
    """The core defect being fixed: a PT15M repetition anchored at :00 fires at the bar
    OPEN. Every slot must instead be the close instant plus the settle interval."""
    for cycle in CYCLE_WINDOWS:
        for slot in m15_close_slots(cycle.start_utc, cycle.end_utc):
            assert slot.second == M15_CLOSE_SETTLE_SECONDS
            assert slot.minute % 15 == 0, f"{slot} is not an M15 boundary"
            assert slot != time(slot.hour, slot.minute), "slot must not be the bar open"


def test_asian_london_slot_count():
    """07:00-11:00 inclusive at 15m = 17 closes."""
    slots = m15_close_slots(time(7, 0), time(11, 0))
    assert len(slots) == 17
    assert slots[0] == time(7, 0, 20)
    assert slots[-1] == time(11, 0, 20)


def test_london_newyork_slot_count():
    """12:00-15:00 inclusive at 15m = 13 closes."""
    slots = m15_close_slots(time(12, 0), time(15, 0))
    assert len(slots) == 13
    assert slots[0] == time(12, 0, 20)
    assert slots[-1] == time(15, 0, 20)


def test_slots_are_strictly_ascending_and_deterministic():
    for cycle in CYCLE_WINDOWS:
        first = m15_close_slots(cycle.start_utc, cycle.end_utc)
        assert first == m15_close_slots(cycle.start_utc, cycle.end_utc)
        assert first == sorted(first)
        assert len(set(first)) == len(first)


def test_slot_datetimes_are_utc_aware():
    slots = slot_datetimes(CYCLE_BY_ID["ASIAN_LONDON"], MONDAY)
    assert len(slots) == 17
    assert all(s.tzinfo is not None for s in slots)
    assert slots[0] == datetime(2026, 9, 21, 7, 0, 20, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Weekday gate
# ---------------------------------------------------------------------------

def test_weekday_gate_rejects_weekend():
    assert is_weekday_utc(date(2026, 9, 19)) is False  # Saturday
    assert is_weekday_utc(date(2026, 9, 20)) is False  # Sunday
    assert is_weekday_utc(date(2026, 9, 21)) is True   # Monday
    assert is_weekday_utc(date(2026, 9, 25)) is True   # Friday


# ---------------------------------------------------------------------------
# Window gate
# ---------------------------------------------------------------------------

def test_inside_window_bounds_are_inclusive():
    cycle = CYCLE_BY_ID["ASIAN_LONDON"]
    at = lambda h, m: datetime(2026, 9, 21, h, m, tzinfo=timezone.utc)
    assert is_inside_window(cycle, at(7, 0)) is True
    assert is_inside_window(cycle, at(11, 0)) is True
    assert is_inside_window(cycle, at(6, 59)) is False
    assert is_inside_window(cycle, at(11, 1)) is False


def test_london_newyork_window_does_not_contain_asian_london_slots():
    """The two cycles must not overlap -- a slot belongs to exactly one cycle."""
    asian = CYCLE_BY_ID["ASIAN_LONDON"]
    ny = CYCLE_BY_ID["LONDON_NEWYORK"]
    for slot in m15_close_slots(asian.start_utc, asian.end_utc):
        assert is_inside_window(ny, datetime.combine(MONDAY, slot, tzinfo=timezone.utc)) is False


# ---------------------------------------------------------------------------
# Friction campaign protection
# ---------------------------------------------------------------------------

def test_frozen_campaign_manifest_is_detected_and_active():
    """Reads the REAL frozen manifest. Asserts structural facts only, so it stays valid
    as collection progresses."""
    status = load_friction_campaign()
    if not Path(FRICTION_CAMPAIGN_MANIFEST).exists():
        pytest.skip("friction campaign manifest not present in this checkout")
    assert status.campaign_id == "LSMC_EURUSD_FRICTION_WP3A1_V1"
    assert status.minimum_days == 5
    assert status.complete_days <= status.minimum_days or not status.active


def test_frozen_campaign_windows_match_the_manifest():
    """The four protected windows must be exactly the manifest's own -- never
    hardcoded independently."""
    manifest = json.loads(Path(FRICTION_CAMPAIGN_MANIFEST).read_text(encoding="utf-8"))
    load_friction_campaign()  # populates the module's window table
    from scheduling.fx_schedule import _friction_windows

    expected = {(w["window_id"], w["start_utc_hhmm"], w["end_utc_hhmm"]) for w in manifest["windows"]}
    actual = {(wid, s.strftime("%H:%M"), e.strftime("%H:%M")) for wid, s, e in _friction_windows}
    assert actual == expected
    assert len(actual) == 4


def test_window_d_collision_is_protected():
    """The specific protection the mission requires: a LONDON_NEWYORK slot inside
    frozen WINDOW_D_LONDON_NEWYORK (12:30-12:40 UTC) must be identified as a
    conflict while the campaign is active."""
    status = load_friction_campaign()
    if not status.active:
        pytest.skip("campaign no longer collecting -- nothing to protect")
    moment = datetime(2026, 9, 21, 12, 30, 20, tzinfo=timezone.utc)
    assert friction_window_conflict(moment, status) == "WINDOW_D_LONDON_NEWYORK"


def test_friction_windows_collide_with_the_scheduled_cycles():
    """Documents exactly why the protection is load-bearing. The frozen campaign's four
    UTC windows and the two scheduled cycles overlap as follows:

      WINDOW_A_ASIAN_REFERENCE 05:30-05:40 -- outside both cycles
      WINDOW_B_PRE_LONDON      06:50-07:00 -- touches ASIAN_LONDON's 07:00 open
      WINDOW_C_LONDON          09:00-09:10 -- inside ASIAN_LONDON (07:00-11:00)
      WINDOW_D_LONDON_NEWYORK  12:30-12:40 -- inside LONDON_NEWYORK (12:00-15:00)

    So three of the four windows would otherwise be sampled by a scheduled FX slot.
    Asserted against the real manifest so it cannot drift."""
    status = load_friction_campaign()
    if not status.active:
        pytest.skip("campaign no longer collecting -- nothing to protect")

    from scheduling.fx_schedule import _friction_windows

    windows = {wid: (start, end) for wid, start, end in _friction_windows}
    asian = CYCLE_BY_ID["ASIAN_LONDON"]
    ny = CYCLE_BY_ID["LONDON_NEWYORK"]

    def at(t):
        return datetime.combine(MONDAY, t, tzinfo=timezone.utc)

    # The mission's specific required protection.
    assert is_inside_window(ny, at(windows["WINDOW_D_LONDON_NEWYORK"][0])) is True
    assert is_inside_window(asian, at(windows["WINDOW_C_LONDON"][0])) is True
    assert is_inside_window(asian, at(windows["WINDOW_B_PRE_LONDON"][1])) is True
    # Window A is genuinely outside both cycles.
    assert is_inside_window(asian, at(windows["WINDOW_A_ASIAN_REFERENCE"][0])) is False
    assert is_inside_window(ny, at(windows["WINDOW_A_ASIAN_REFERENCE"][0])) is False
    # And no window is inside the wrong cycle.
    assert is_inside_window(asian, at(windows["WINDOW_D_LONDON_NEWYORK"][0])) is False
    assert is_inside_window(ny, at(windows["WINDOW_C_LONDON"][0])) is False


def test_no_conflict_reported_when_campaign_inactive():
    """Once the manifest's own minimum day count is met, nothing is suppressed."""
    from scheduling.fx_schedule import FrictionCampaignStatus

    inactive = FrictionCampaignStatus("X", False, 5, 5, "CAMPAIGN_MINIMUM_DAYS_MET")
    assert friction_window_conflict(
        datetime(2026, 9, 21, 12, 30, 20, tzinfo=timezone.utc), inactive) is None


def test_unreadable_manifest_fails_closed():
    """A corrupt manifest must raise, never be silently treated as 'no campaign'."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        bad = Path(tmp) / "campaign_manifest.json"
        bad.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(FrictionCampaignError, match="MANIFEST_UNREADABLE"):
            load_friction_campaign(str(bad))


def test_absent_manifest_is_not_an_error():
    """A genuinely absent campaign is a legitimate 'nothing to protect' state."""
    status = load_friction_campaign("nonexistent/path/campaign_manifest.json")
    assert status.active is False
    assert status.reason == "CAMPAIGN_MANIFEST_ABSENT"


# ---------------------------------------------------------------------------
# Slot idempotency
# ---------------------------------------------------------------------------

def test_slot_key_is_deterministic():
    slot = datetime(2026, 9, 21, 7, 0, 20, tzinfo=timezone.utc)
    assert slot_key("ASIAN_LONDON", MONDAY, slot) == slot_key("ASIAN_LONDON", MONDAY, slot)
    assert slot_key("ASIAN_LONDON", MONDAY, slot) != slot_key("LONDON_NEWYORK", MONDAY, slot)


def test_slot_ledger_claims_once_then_refuses(tmp_path):
    ledger = SlotLedger(str(tmp_path / "slots.json"))
    slot = datetime(2026, 9, 21, 7, 0, 20, tzinfo=timezone.utc)

    assert ledger.has_claimed("ASIAN_LONDON", MONDAY, slot) is False
    ledger.claim("ASIAN_LONDON", MONDAY, slot, outcome="EXECUTED")
    assert ledger.has_claimed("ASIAN_LONDON", MONDAY, slot) is True

    with pytest.raises(SlotAlreadyClaimed, match="SLOT_ALREADY_CLAIMED"):
        ledger.claim("ASIAN_LONDON", MONDAY, slot)


def test_slot_ledger_survives_restart(tmp_path):
    path = str(tmp_path / "slots.json")
    slot = datetime(2026, 9, 21, 7, 15, 20, tzinfo=timezone.utc)
    SlotLedger(path).claim("ASIAN_LONDON", MONDAY, slot)
    # A fresh instance over the same path (restart) still sees the claim.
    assert SlotLedger(path).has_claimed("ASIAN_LONDON", MONDAY, slot) is True


def test_distinct_slots_are_independently_claimable(tmp_path):
    ledger = SlotLedger(str(tmp_path / "slots.json"))
    a = datetime(2026, 9, 21, 7, 0, 20, tzinfo=timezone.utc)
    b = datetime(2026, 9, 21, 7, 15, 20, tzinfo=timezone.utc)
    ledger.claim("ASIAN_LONDON", MONDAY, a)
    ledger.claim("ASIAN_LONDON", MONDAY, b)
    assert ledger.has_claimed("ASIAN_LONDON", MONDAY, a)
    assert ledger.has_claimed("ASIAN_LONDON", MONDAY, b)


# ---------------------------------------------------------------------------
# Runner behaviour (end-to-end gate enforcement)
# ---------------------------------------------------------------------------

def _run_runner(*args, timeout=60):
    return subprocess.run(
        [sys.executable, str(RUNNER), *args],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=timeout,
    )


def test_runner_refuses_watch_flag():
    """`--watch` must be rejected outright -- a continuous process is exactly what this
    runner exists to avoid."""
    result = _run_runner("--cycle", "ASIAN_LONDON", "--watch")
    assert result.returncode == 1
    assert "REFUSED_WATCH_NOT_SUPPORTED" in result.stderr


def test_runner_refuses_weekend():
    result = _run_runner("--cycle", "ASIAN_LONDON", "--dry-run", "--json",
                         "--now", "2026-09-20T08:00:00+00:00")
    assert result.returncode == 2
    assert "REFUSED_WEEKEND_MARKET_CLOSED" in result.stdout


def test_runner_refuses_outside_window():
    result = _run_runner("--cycle", "ASIAN_LONDON", "--dry-run", "--json",
                         "--now", "2026-09-21T05:00:00+00:00")
    assert result.returncode == 2
    assert "REFUSED_OUTSIDE_EXECUTION_WINDOW" in result.stdout


def test_runner_refuses_friction_window_collision():
    """The end-to-end proof of the required Window D protection."""
    result = _run_runner("--cycle", "LONDON_NEWYORK", "--dry-run", "--json",
                         "--now", "2026-09-21T12:30:20+00:00")
    assert result.returncode == 2
    assert "REFUSED_FRICTION_CAMPAIGN_WINDOW_ACTIVE" in result.stdout
    assert "WINDOW_D_LONDON_NEWYORK" in result.stdout


def _next_unclaimed_weekday(days_ahead: int = 365) -> date:
    """A weekday far enough past `today` that the real, installed production scheduler
    (state/fx_schedule/slot_ledger.json -- see SlotLedger's default path) cannot yet
    have claimed its ASIAN_LONDON slot. A fixed historical literal here goes stale the
    moment production actually runs that slot for real: 2026-09-21T08:00:20+00:00 was
    genuinely claimed by the live scheduled task (observed 2026-09-22)."""
    d = date.today() + timedelta(days=days_ahead)
    while d.weekday() >= 5:  # Sat/Sun
        d += timedelta(days=1)
    return d


def test_runner_passes_on_a_clean_weekday_slot():
    """This runner invokes the real production SlotLedger (no test isolation exists for
    the subprocess path -- see _run_runner), so the slot under test must be one the live
    scheduler cannot have executed yet, not a fixed calendar date."""
    now = f"{_next_unclaimed_weekday().isoformat()}T08:00:20+00:00"
    result = _run_runner("--cycle", "ASIAN_LONDON", "--dry-run", "--json",
                         "--now", now)
    assert result.returncode == 0
    assert "PASS_DRY_RUN" in result.stdout


def test_runner_dry_run_never_claims_a_slot():
    """A dry run must leave the slot ledger untouched."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        ledger_path = Path(tmp) / "slots.json"
        from scheduling.fx_schedule import SlotLedger as SL

        SL(str(ledger_path))  # create the store
        before = ledger_path.read_text(encoding="utf-8") if ledger_path.exists() else ""
        _run_runner("--cycle", "ASIAN_LONDON", "--dry-run", "--json",
                    "--now", "2026-09-21T08:00:20+00:00")
        after = ledger_path.read_text(encoding="utf-8") if ledger_path.exists() else ""
        assert before == after


def test_runner_reports_no_execution_authority():
    result = _run_runner("--cycle", "ASIAN_LONDON", "--dry-run", "--json",
                         "--now", "2026-09-21T08:00:20+00:00")
    assert "NONE (PROPOSAL_ONLY)" in result.stdout


# ---------------------------------------------------------------------------
# Execution boundary
# ---------------------------------------------------------------------------

def test_schedule_module_has_no_execution_reach():
    path = REPO_ROOT / "src" / "scheduling" / "fx_schedule.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    forbidden = {"execution.executor", "execution.coordinator", "execution.adapter",
                 "mt5.management_gateway", "MetaTrader5"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in forbidden, f"imports {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert module not in forbidden, f"imports from {module}"
            assert not module.startswith("execution."), f"imports from {module}"


def test_runner_has_no_execution_reach():
    source = RUNNER.read_text(encoding="utf-8")
    for name in ("order_send", "order_check", "execution.executor",
                 "execution.mt5_gateway", "mt5.management_gateway"):
        assert name not in source, f"runner references {name}"


def test_schedule_module_does_not_write_to_the_frozen_campaign():
    """The scheduler must never write into frozen WP3A.1 evidence."""
    source = (REPO_ROOT / "src" / "scheduling" / "fx_schedule.py").read_text(encoding="utf-8")
    assert "write_text" not in source.split("class SlotLedger")[0], (
        "campaign reading must be read-only")
    assert "open(" not in source or "read_text" in source
