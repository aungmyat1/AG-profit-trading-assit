"""AG Resource Management Policy V1 -- local resource gate and heavy-job lock.

Authority: docs/governance/AG_RESOURCE_MANAGEMENT_POLICY_V1.md

Standard library only, so this is safe to run on a memory-constrained workstation.
Inspects available RAM, PID existence and the single runtime lock file. It never
terminates, signals or reprioritizes any process, and it has no trading, broker or
strategy surface.

Usage:
    python scripts/resource_guard.py status [--json]
    python scripts/resource_guard.py acquire --agent CODEX_LOCAL --mission C001_R2 --class R3
        [--min-ram-mb N] [--pid PID] [--command-summary TEXT] [--json]
    python scripts/resource_guard.py heartbeat --agent CODEX_LOCAL --mission C001_R2 [--pid PID]
    python scripts/resource_guard.py release --agent CODEX_LOCAL --mission C001_R2 [--pid PID]
    python scripts/resource_guard.py clear-stale [--json]

Exit codes: 0 = OK/acquired/released, 2 = gate BLOCKED_RESOURCE or BUSY,
3 = refused (ownership mismatch, lock not stale, malformed lock), 1 = usage error.

The lock records the PID of the process that owns the workload. `--pid` defaults to
this helper's parent process (the invoking shell). If that shell exits before the
workload ends the lock reads STALE, so a long-running job should pass its own PID.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

LOCK_SCHEMA_VERSION = 1

# Policy V1 section 19 -- initial operational thresholds. Do not change autonomously.
POLICY_THRESHOLDS_MB = {"R0": 0, "R1": 1200, "R2": 2500, "R3": 3000}
HEAVY_CLASSES = ("R2", "R3")
LOCKING_CLASSES = ("R1", "R2", "R3")

# A live PID whose heartbeat is older than this cannot be proven to be the original
# owner (PID reuse, hung job), so the lock is reported UNKNOWN_LOCK, never STALE_LOCK.
HEARTBEAT_MAX_AGE_SECONDS = 900

KNOWN_AGENTS = ("CLAUDE_CODE", "CODEX_LOCAL", "ARENA_WEB", "OWNER")

NO_LOCK = "NO_LOCK"
ACTIVE_LOCK = "ACTIVE_LOCK"
STALE_LOCK = "STALE_LOCK"
UNKNOWN_LOCK = "UNKNOWN_LOCK"

REQUIRED_LOCK_FIELDS = (
    "version", "owner_agent", "mission_id", "resource_class", "pid",
    "started_at_utc", "heartbeat_at_utc",
)

REPO_ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- probes

def _git(args: list[str], cwd: Path) -> Optional[str]:
    try:
        out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                             timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else None


def canonical_lock_path() -> Path:
    """Lock in the MAIN worktree, so every worktree of this repo shares one lock."""
    common = _git(["rev-parse", "--path-format=absolute", "--git-common-dir"], REPO_ROOT)
    root = Path(common).parent if common else REPO_ROOT
    return root / "artifacts" / "runtime" / "resource_lock.json"


def read_memory_mb() -> tuple[Optional[int], Optional[int]]:
    """Return (total_mb, available_mb); None where it cannot be determined."""
    if sys.platform == "win32":
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return None, None
        return stat.ullTotalPhys // 2**20, stat.ullAvailPhys // 2**20
    try:
        info = {}
        with open("/proc/meminfo", encoding="ascii") as fh:
            for line in fh:
                key, _, rest = line.partition(":")
                info[key] = int(rest.split()[0])  # kB
        avail = info.get("MemAvailable")
        return info["MemTotal"] // 1024, (avail // 1024 if avail is not None else None)
    except (OSError, KeyError, ValueError, IndexError):
        return None, None


def pid_alive(pid: int) -> Optional[bool]:
    """True/False when provable, None when existence cannot be determined."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return None
    if sys.platform == "win32":
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        ERROR_ACCESS_DENIED = 5
        ERROR_INVALID_PARAMETER = 87
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.restype = ctypes.c_void_p
        handle = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            err = ctypes.get_last_error()
            if err == ERROR_ACCESS_DENIED:
                return True
            if err == ERROR_INVALID_PARAMETER:
                return False
            return None
        try:
            code = ctypes.c_ulong()
            if not k32.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code)):
                return None
            return code.value == STILL_ACTIVE
        finally:
            k32.CloseHandle(ctypes.c_void_p(handle))
    try:
        os.kill(pid, 0)  # signal 0: existence check only, delivers nothing
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return None
    return True


# --------------------------------------------------------------------------- lock state

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(value: object) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else None


def classify_lock(lock_path: Path, *, pid_probe: Callable[[int], Optional[bool]] = pid_alive,
                  now: Optional[datetime] = None) -> dict:
    """Return {'status', 'lock', 'reason'}; anything uncertain is UNKNOWN_LOCK."""
    if not lock_path.exists():
        return {"status": NO_LOCK, "lock": None, "reason": "lock file absent"}
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"status": UNKNOWN_LOCK, "lock": None, "reason": f"unreadable lock: {exc}"}
    if not isinstance(lock, dict):
        return {"status": UNKNOWN_LOCK, "lock": None, "reason": "lock is not a JSON object"}
    missing = [f for f in REQUIRED_LOCK_FIELDS if f not in lock]
    if missing:
        return {"status": UNKNOWN_LOCK, "lock": lock, "reason": f"missing fields {missing}"}
    if lock.get("version") != LOCK_SCHEMA_VERSION:
        return {"status": UNKNOWN_LOCK, "lock": lock,
                "reason": f"unsupported lock version {lock.get('version')!r}"}
    alive = pid_probe(lock["pid"])
    if alive is None:
        return {"status": UNKNOWN_LOCK, "lock": lock,
                "reason": f"cannot determine whether pid {lock['pid']!r} exists"}
    if alive is False:
        return {"status": STALE_LOCK, "lock": lock,
                "reason": f"owner pid {lock['pid']} no longer exists"}
    heartbeat = _parse_iso(lock.get("heartbeat_at_utc"))
    if heartbeat is None:
        return {"status": UNKNOWN_LOCK, "lock": lock, "reason": "heartbeat unparseable"}
    age = ((now or _utc_now()) - heartbeat).total_seconds()
    if age > HEARTBEAT_MAX_AGE_SECONDS:
        return {"status": UNKNOWN_LOCK, "lock": lock,
                "reason": f"pid {lock['pid']} exists but heartbeat is {int(age)}s old "
                          f"(> {HEARTBEAT_MAX_AGE_SECONDS}s); owner cannot be proven"}
    return {"status": ACTIVE_LOCK, "lock": lock,
            "reason": f"owner pid {lock['pid']} exists, heartbeat {int(age)}s old"}


def required_ram_mb(resource_class: str, experiment_min_mb: Optional[int] = None) -> int:
    """max(policy threshold, experiment threshold) -- never lowers an experiment gate."""
    return max(POLICY_THRESHOLDS_MB[resource_class], experiment_min_mb or 0)


def _other_heavy_job(state: dict) -> str:
    if state["status"] == ACTIVE_LOCK:
        return "TRUE" if state["lock"].get("resource_class") in HEAVY_CLASSES else "FALSE_PER_LOCK"
    if state["status"] == UNKNOWN_LOCK:
        return "UNKNOWN"
    # Unregistered processes are never attributed to an agent without provenance.
    return "NONE_REGISTERED"


# --------------------------------------------------------------------------- operations

def status(lock_path: Path, *, memory_probe=read_memory_mb, pid_probe=pid_alive) -> dict:
    total, avail = memory_probe()
    state = classify_lock(lock_path, pid_probe=pid_probe)
    lock = state["lock"] or {}
    gates = {}
    for cls, need in POLICY_THRESHOLDS_MB.items():
        if need == 0:
            gates[f"{cls}_GATE"] = "PASS"
        elif avail is None:
            gates[f"{cls}_GATE"] = "BLOCKED_RESOURCE (RAM undetermined)"
        else:
            gates[f"{cls}_GATE"] = "PASS" if avail >= need else "BLOCKED_RESOURCE"
    return {
        "TOTAL_RAM_MB": total, "AVAILABLE_RAM_MB": avail, **gates,
        "LOCK_PATH": str(lock_path), "LOCK_STATUS": state["status"],
        "LOCK_REASON": state["reason"], "LOCK_OWNER": lock.get("owner_agent"),
        "LOCK_MISSION": lock.get("mission_id"), "LOCK_RESOURCE_CLASS": lock.get("resource_class"),
        "LOCK_PID": lock.get("pid"), "LOCK_HEARTBEAT_AT_UTC": lock.get("heartbeat_at_utc"),
        "OTHER_HEAVY_JOB_DETECTED": _other_heavy_job(state),
    }


def acquire(lock_path: Path, *, agent: str, mission: str, resource_class: str,
            pid: int, command_summary: str = "", experiment_min_mb: Optional[int] = None,
            memory_probe=read_memory_mb, pid_probe=pid_alive,
            repo: Optional[str] = None, branch: Optional[str] = None) -> dict:
    total, avail = memory_probe()
    need = required_ram_mb(resource_class, experiment_min_mb)
    before = classify_lock(lock_path, pid_probe=pid_probe)
    out = {
        "AGENT": agent, "MISSION": mission, "RESOURCE_CLASS": resource_class,
        "TOTAL_RAM_MB": total, "AVAILABLE_RAM_MB": avail, "REQUIRED_RAM_MB": need,
        "LOCK_STATUS_BEFORE": before["status"], "LOCK_REASON": before["reason"],
        "RESOURCE_GATE": None, "ACQUIRED": False, "LOCK_PATH": str(lock_path),
    }
    if resource_class == "R0":
        out.update(RESOURCE_GATE="PASS", NOTE="R0 needs no lock; none written")
        return out
    if avail is None:
        out.update(RESOURCE_GATE="BLOCKED_RESOURCE", NOTE="available RAM undetermined; fail closed")
        return out
    if avail < need:
        out["RESOURCE_GATE"] = "BLOCKED_RESOURCE"
        return out
    if before["status"] != NO_LOCK:
        note = {
            STALE_LOCK: "existing lock is STALE; record evidence and run clear-stale first",
            UNKNOWN_LOCK: "existing lock state is UNKNOWN; fail closed",
            ACTIVE_LOCK: "another workload holds the lock",
        }[before["status"]]
        out.update(RESOURCE_GATE="BUSY", NOTE=note, LOCK_OWNER=(before["lock"] or {}).get("owner_agent"),
                   LOCK_MISSION=(before["lock"] or {}).get("mission_id"))
        return out
    now = _iso(_utc_now())
    lock = {
        "version": LOCK_SCHEMA_VERSION, "owner_agent": agent, "mission_id": mission,
        "resource_class": resource_class,
        "repo": repo if repo is not None else _git(["rev-parse", "--show-toplevel"], REPO_ROOT),
        "branch": branch if branch is not None else _git(["rev-parse", "--abbrev-ref", "HEAD"], REPO_ROOT),
        "pid": pid, "started_at_utc": now, "heartbeat_at_utc": now,
        "command_summary": command_summary[:200],
        "required_ram_mb": need, "available_ram_mb_at_acquire": avail,
    }
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        # O_EXCL: atomic create-if-absent; the loser of a race gets FileExistsError.
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        out.update(RESOURCE_GATE="BUSY", NOTE="lost acquisition race; existing lock untouched")
        return out
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(lock, fh, indent=2, sort_keys=True)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    out.update(RESOURCE_GATE="PASS", ACQUIRED=True, LOCK_PID=pid)
    return out


def _check_owner(lock_path: Path, agent: str, mission: str, pid: Optional[int]) -> tuple[Optional[dict], str]:
    if not lock_path.exists():
        return None, "no lock present"
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"unreadable lock: {exc}; refusing"
    if not isinstance(lock, dict):
        return None, "lock is not a JSON object; refusing"
    if lock.get("owner_agent") != agent or lock.get("mission_id") != mission:
        return None, (f"ownership mismatch: lock held by {lock.get('owner_agent')!r}/"
                      f"{lock.get('mission_id')!r}")
    if pid is not None and lock.get("pid") != pid:
        return None, f"pid mismatch: lock pid {lock.get('pid')!r} != {pid}"
    return lock, "owner verified"


def release(lock_path: Path, *, agent: str, mission: str, pid: Optional[int] = None) -> dict:
    lock, reason = _check_owner(lock_path, agent, mission, pid)
    out = {"AGENT": agent, "MISSION": mission, "LOCK_PATH": str(lock_path), "REASON": reason}
    if lock is None:
        out["RELEASED"] = False
        return out
    lock_path.unlink()
    out["RELEASED"] = True
    return out


def heartbeat(lock_path: Path, *, agent: str, mission: str, pid: Optional[int] = None) -> dict:
    lock, reason = _check_owner(lock_path, agent, mission, pid)
    out = {"AGENT": agent, "MISSION": mission, "LOCK_PATH": str(lock_path), "REASON": reason}
    if lock is None:
        out["HEARTBEAT_UPDATED"] = False
        return out
    lock["heartbeat_at_utc"] = _iso(_utc_now())
    tmp = lock_path.with_name(lock_path.name + ".tmp")
    tmp.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, lock_path)
    out.update(HEARTBEAT_UPDATED=True, HEARTBEAT_AT_UTC=lock["heartbeat_at_utc"])
    return out


def clear_stale(lock_path: Path, *, pid_probe=pid_alive) -> dict:
    state = classify_lock(lock_path, pid_probe=pid_probe)
    out = {"LOCK_PATH": str(lock_path), "LOCK_STATUS": state["status"], "REASON": state["reason"],
           "STALE_LOCK_EVIDENCE": state["lock"], "CLEARED": False}
    if state["status"] != STALE_LOCK:
        out["NOTE"] = "only a STALE_LOCK may be cleared; nothing removed"
        return out
    # Re-read immediately before removal: refuse if the file changed under us.
    try:
        unchanged = json.loads(lock_path.read_text(encoding="utf-8")) == state["lock"]
    except (OSError, ValueError):
        unchanged = False
    if not unchanged:
        out["NOTE"] = "lock changed or vanished during check; nothing removed"
        return out
    lock_path.unlink()
    out["CLEARED"] = True
    return out


# --------------------------------------------------------------------------- CLI

def _emit(result: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2, sort_keys=False, default=str))
        return
    for key, value in result.items():
        if isinstance(value, dict):
            value = json.dumps(value, sort_keys=True)
        print(f"{key} = {'NONE' if value is None else value}")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lock-path", type=Path, default=None,
                        help="override the canonical lock path (tests only)")
    sub = parser.add_subparsers(dest="op", required=True)

    p_status = sub.add_parser("status")
    p_status.add_argument("--json", action="store_true")

    p_acq = sub.add_parser("acquire")
    p_acq.add_argument("--agent", required=True, choices=KNOWN_AGENTS)
    p_acq.add_argument("--mission", required=True)
    p_acq.add_argument("--class", dest="resource_class", required=True, choices=list(POLICY_THRESHOLDS_MB))
    p_acq.add_argument("--min-ram-mb", type=int, default=None,
                       help="experiment-specific RAM gate; the stricter of this and policy applies")
    p_acq.add_argument("--pid", type=int, default=None, help="owning workload PID (default: parent PID)")
    p_acq.add_argument("--command-summary", default="")
    p_acq.add_argument("--json", action="store_true")

    for name in ("release", "heartbeat"):
        p = sub.add_parser(name)
        p.add_argument("--agent", required=True, choices=KNOWN_AGENTS)
        p.add_argument("--mission", required=True)
        p.add_argument("--pid", type=int, default=None, help="additionally require this lock pid")
        p.add_argument("--json", action="store_true")

    p_clear = sub.add_parser("clear-stale")
    p_clear.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    lock_path = args.lock_path or canonical_lock_path()

    if args.op == "status":
        result = status(lock_path)
        code = 0
    elif args.op == "acquire":
        if args.min_ram_mb is not None and args.min_ram_mb < 0:
            parser.error("--min-ram-mb must be >= 0")
        result = acquire(lock_path, agent=args.agent, mission=args.mission,
                         resource_class=args.resource_class,
                         pid=args.pid if args.pid is not None else os.getppid(),
                         command_summary=args.command_summary,
                         experiment_min_mb=args.min_ram_mb)
        code = 0 if result["RESOURCE_GATE"] == "PASS" else 2
    elif args.op == "release":
        result = release(lock_path, agent=args.agent, mission=args.mission, pid=args.pid)
        code = 0 if result["RELEASED"] else 3
    elif args.op == "heartbeat":
        result = heartbeat(lock_path, agent=args.agent, mission=args.mission, pid=args.pid)
        code = 0 if result["HEARTBEAT_UPDATED"] else 3
    else:
        result = clear_stale(lock_path)
        code = 0 if result["CLEARED"] or result["LOCK_STATUS"] == NO_LOCK else 3
    _emit(result, args.json)
    return code


if __name__ == "__main__":
    sys.exit(main())
