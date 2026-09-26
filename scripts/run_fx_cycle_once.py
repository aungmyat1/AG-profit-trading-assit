"""Fail-closed `--once` FX cycle runner for the weekday scheduler
(AG_SCHEDULER_AND_LARGE_SMC_WATCH_HARDENING_V1, P1).

One invocation == at most one bounded proposal cycle for one cycle/slot. Ordered,
fail-closed gates are evaluated BEFORE anything is delegated, and the first failure
stops the run without invoking the pilot at all:

  1. WEEKDAY           -- Sat/Sun UTC refuses (market closed; a run can only produce
                          DATA_ERROR noise, observed 2026-09-20).
  2. INSIDE WINDOW     -- outside the cycle's own execution window refuses.
  3. FRICTION WINDOW   -- while the frozen WP3A.1 campaign is still collecting, a slot
                          colliding with one of its four frozen UTC windows refuses, so
                          scheduled FX polling cannot perturb spread evidence governed
                          by a frozen manifest.
  4. SLOT IDEMPOTENCY  -- the same (cycle, trading date, slot) refuses a second run.

`--watch` is explicitly REJECTED, not ignored: this runner exists precisely to avoid a
continuous process, so silently accepting the flag would defeat it.

Exit codes (deliberate -- a refusal is a correct outcome, not a failure):
  0  cycle executed
  2  REFUSED by a gate (fail closed, nothing ran)
  1  operational error

Never executes a trade: the delegated pilot is `PROPOSAL_ONLY` with
`automatic_execution: false` / `live_execution: false`, and this module imports no
order path.

Usage:
    python scripts/run_fx_cycle_once.py --cycle ASIAN_LONDON [--json] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from scheduling.fx_schedule import (  # noqa: E402
    CYCLE_BY_ID,
    CYCLE_WINDOWS,
    FrictionCampaignError,
    SlotAlreadyClaimed,
    SlotLedger,
    friction_window_conflict,
    is_inside_window,
    is_weekday_utc,
    load_friction_campaign,
    m15_close_slots,
)

EXIT_OK = 0
EXIT_REFUSED = 2
EXIT_ERROR = 1

REFUSED_WEEKEND = "REFUSED_WEEKEND_MARKET_CLOSED"
REFUSED_OUTSIDE_WINDOW = "REFUSED_OUTSIDE_EXECUTION_WINDOW"
REFUSED_FRICTION_WINDOW = "REFUSED_FRICTION_CAMPAIGN_WINDOW_ACTIVE"
REFUSED_SLOT_CLAIMED = "REFUSED_SLOT_ALREADY_EXECUTED"


def _current_slot(cycle, now: datetime):
    """The M15 close slot this invocation corresponds to: the most recent slot at or
    before `now`. Used for slot idempotency -- two triggers landing in the same bar
    map to the same slot and the second refuses."""
    candidates = [s for s in _slot_times(cycle, now.date()) if s <= now]
    return candidates[-1] if candidates else None


def _slot_times(cycle, day):
    from scheduling.fx_schedule import slot_datetimes

    return slot_datetimes(cycle, day)


def evaluate_gates(cycle_id: str, now: datetime, ledger: SlotLedger,
                   friction_status=None) -> tuple[str, str]:
    """Return (gate_name, reason). gate_name == "PASS" when every gate cleared."""
    cycle = CYCLE_BY_ID[cycle_id]

    if not is_weekday_utc(now.date()):
        return "weekday", REFUSED_WEEKEND

    if not is_inside_window(cycle, now):
        return "inside_window", REFUSED_OUTSIDE_WINDOW

    window_id = friction_window_conflict(now, friction_status)
    if window_id:
        return "friction_window", f"{REFUSED_FRICTION_WINDOW}:{window_id}"

    slot = _current_slot(cycle, now)
    if slot is not None and ledger.has_claimed(cycle_id, now.date(), slot):
        return "slot_idempotency", f"{REFUSED_SLOT_CLAIMED}:{slot.isoformat()}"

    return "PASS", ""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AG fail-closed --once FX cycle runner (PROPOSAL_ONLY)")
    parser.add_argument("--cycle", required=True,
                        choices=sorted(CYCLE_BY_ID),
                        help="which session cycle to evaluate")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--dry-run", action="store_true",
                        help="evaluate gates only; never invoke the pilot, never claim a slot")
    parser.add_argument("--now", default=None,
                        help="ISO-8601 UTC override for gate evaluation (testing only)")
    parser.add_argument("--watch", action="store_true",
                        help="REJECTED -- this runner is one bounded cycle by design")
    args = parser.parse_args()

    if args.watch:
        print("REFUSED_WATCH_NOT_SUPPORTED: this runner performs one bounded --once cycle; "
              "use scripts/run_post_asian_pilot.py --watch directly if continuous "
              "observation is genuinely required", file=sys.stderr)
        sys.exit(EXIT_ERROR)

    now = (datetime.fromisoformat(args.now) if args.now else datetime.now(timezone.utc))
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    cycle = CYCLE_BY_ID[args.cycle]

    try:
        friction_status = load_friction_campaign()
    except FrictionCampaignError as exc:
        # Fail closed: an unreadable campaign manifest must never be treated as
        # "no campaign in progress".
        print(f"REFUSED_FRICTION_CAMPAIGN_UNREADABLE: {exc}", file=sys.stderr)
        sys.exit(EXIT_ERROR)

    ledger = SlotLedger()
    gate, reason = evaluate_gates(args.cycle, now, ledger, friction_status)

    report = {
        "CYCLE": args.cycle,
        "EVALUATED_AT_UTC": now.isoformat(),
        "WINDOW_UTC": [cycle.start_utc.strftime("%H:%M"), cycle.end_utc.strftime("%H:%M")],
        "SLOTS_PER_DAY": len(m15_close_slots(cycle.start_utc, cycle.end_utc)),
        "GATE": gate,
        "REASON": reason,
        "FRICTION_CAMPAIGN": {
            "campaign_id": friction_status.campaign_id,
            "active": friction_status.active,
            "complete_days": friction_status.complete_days,
            "minimum_days": friction_status.minimum_days,
            "reason": friction_status.reason,
        },
        "PILOT_CONFIG": cycle.pilot_config,
        "EXECUTION_AUTHORITY": "NONE (PROPOSAL_ONLY)",
    }

    if gate != "PASS":
        report["RESULT"] = "REFUSED"
        _emit(report, args.json)
        sys.exit(EXIT_REFUSED)

    if args.dry_run:
        report["RESULT"] = "PASS_DRY_RUN"
        _emit(report, args.json)
        sys.exit(EXIT_OK)

    slot = _current_slot(cycle, now)
    if slot is None:
        report["RESULT"] = "REFUSED_NO_SLOT"
        report["REASON"] = REFUSED_OUTSIDE_WINDOW
        _emit(report, args.json)
        sys.exit(EXIT_REFUSED)

    # Claim BEFORE delegating: if the pilot crashes we must still not re-run this bar
    # automatically. A missed bar is visible evidence; a double-evaluated bar silently
    # inflates the proposal population.
    try:
        ledger.claim(args.cycle, now.date(), slot)
    except SlotAlreadyClaimed as exc:
        report["RESULT"] = "REFUSED"
        report["GATE"] = "slot_idempotency"
        report["REASON"] = str(exc)
        _emit(report, args.json)
        sys.exit(EXIT_REFUSED)

    report["SLOT_UTC"] = slot.isoformat()

    python_exe = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
    if not python_exe.exists():
        python_exe = Path(sys.executable)

    cmd = [
        str(python_exe), str(REPO_ROOT / "scripts" / "run_post_asian_pilot.py"),
        "--once", "--json", "--pilot-config", cycle.pilot_config,
    ]
    completed = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)

    report["PILOT_EXIT_CODE"] = completed.returncode
    report["RESULT"] = "EXECUTED" if completed.returncode == 0 else "PILOT_FAILED"

    if args.json:
        _emit(report, True)
        if completed.stdout:
            print(completed.stdout, end="")
    else:
        _emit(report, False)
        if completed.stdout:
            print(completed.stdout, end="")

    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)

    sys.exit(EXIT_OK if completed.returncode == 0 else EXIT_ERROR)


def _emit(report: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print("AG_FX_CYCLE_ONCE")
        for key, value in report.items():
            print(f"{key} = {value}")


if __name__ == "__main__":
    main()
