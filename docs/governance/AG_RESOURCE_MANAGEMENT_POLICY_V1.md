# AG Resource Management Policy V1

| Field | Value |
|---|---|
| Status | ACTIVE: owner-issued 2026-10-05 |
| Applies to | `CLAUDE_CODE`, `CODEX_LOCAL`, `ARENA_WEB`, in AG Profit Trading and AG EdgeLab |
| Helper | [`scripts/resource_guard.py`](../../scripts/resource_guard.py) |
| Runtime lock | `artifacts/runtime/resource_lock.json`, in the main worktree, git-ignored |
| Trading authority | NONE. This policy never creates, widens or implies execution authority. |

**Purpose.** Stop competing AI-agent workloads from exhausting the owner's workstation, while keeping research and verification deterministic.

The thresholds in this document are operational gates, not strategy rules. Only the owner may change them (see §13).

---

## 1. Machine constraint

- The workstation has about 7.4 GB of physical RAM (7379 MB observed on 2026-10-05). Treat it as resource-constrained.
- Never assume the machine belongs to the current agent alone. Other agents, editors, browsers, MT5, MCP services, Python workers and owner applications may be running.

## 2. Workload classes and RAM gates

| Class | Meaning | Examples | Required available RAM |
|---|---|---|---|
| **R0** | Lightweight | git status/log/diff, hashing, small file reads, manifest inspection, code review, static analysis, report generation | No minimum |
| **R1** | Moderate | Focused unit tests, a small replay fixture, small dataframe work, a bounded parity slice, a single-symbol diagnostic | `R1_AVAILABLE_RAM_MIN_MB = 1200` |
| **R2** | Heavy | Large DEV replay, large historical-data processing, full strategy backtest, large resampling, large parity replay, multi-symbol historical analysis | `R2_AVAILABLE_RAM_MIN_MB = 2500` |
| **R3** | Critical / experiment | Authoritative experiment, full verification campaign, large walk-forward, multi-symbol long-history replay, large multiprocessing experiment | `R3_AVAILABLE_RAM_MIN_MB = 3000`, and `NO_COMPETING_HEAVY_LOCAL_AGENT = TRUE` |

Before any substantial work, classify it into one of these classes. When unsure, pick the higher class.

These resource classes R0–R3 have nothing to do with the R0–R9 capability gates in `docs/PROJECT_ROADMAP.md`. When the context is ambiguous, write "resource class R2", not "R2".

**Experiment gates are never weakened.** If an experiment's frozen contract sets a higher requirement, that requirement applies:

```text
required_ram = max(policy_threshold, experiment_specific_threshold)
```

This policy and its helper can never lower an experiment gate.

## 3. Agent roles

| Agent | Primary role | Preferred work |
|---|---|---|
| `CLAUDE_CODE` | **Builder** | Implementation, refactoring, unit tests, bug fixes, small validation, documentation |
| `CODEX_LOCAL` | **Verifier / experiment runner** | Repository identity, artifact hashing, parity, data quality, causality, regression, acceptance, large replay, authoritative experiments |
| `ARENA_WEB` | **Remote analyst / reviewer** | Architecture, research, open-source discovery, algorithm and strategy review, test design, failure analysis, result critique, mission planning |

- **Claude** normally stops after implementing, running focused tests, committing or freezing, and reporting. It does not launch an expensive full verification campaign unless that campaign was explicitly assigned to it.
- **Codex Local** holds exclusive local heavy-compute authority for R2/R3 missions.
- **Arena** is preferred whenever local execution isn't needed. It must not claim local-runtime verification unless it was given the actual evidence.

## 4. One-heavy-job invariant

```text
LOCAL_R2_R3_ACTIVE_COUNT <= 1
```

Claude and Codex must never deliberately run separate R2/R3 workloads at the same time. If another heavy job is detected, set `RESOURCE_GATE = BUSY` and stop before starting a new one.

## 5. Resource lock

### Location and schema

The canonical lock is `artifacts/runtime/resource_lock.json`. It is runtime state and is never committed. The ignore rule covers only this one file, so evidence elsewhere under `artifacts/` can still be committed. Every worktree of this repository resolves to the main worktree's lock.

```json
{
  "version": 1,
  "owner_agent": "CODEX_LOCAL",
  "mission_id": "C001_R2",
  "resource_class": "R3",
  "repo": "<repo top-level path>",
  "branch": "<branch>",
  "pid": 12345,
  "started_at_utc": "2026-10-05T00:00:00Z",
  "heartbeat_at_utc": "2026-10-05T00:00:00Z",
  "command_summary": "<short, non-secret summary>",
  "required_ram_mb": 3000,
  "available_ram_mb_at_acquire": 3400
}
```

The lock must never contain credentials, tokens, account numbers or broker secrets.

### Lock states

| State | Meaning |
|---|---|
| `NO_LOCK` | The lock file is absent. |
| `ACTIVE_LOCK` | The schema is valid, the owner PID exists, and the heartbeat is no older than 900 s. |
| `STALE_LOCK` | The schema is valid and the owner PID provably no longer exists. |
| `UNKNOWN_LOCK` | Anything else: unreadable or malformed JSON, an unsupported version, PID existence can't be determined, or the PID exists but the heartbeat is older than 900 s (so PID reuse or a hung owner can't be ruled out). |

### Acquisition sequence (R1–R3)

```text
CHECK LOCK → CHECK PID → CHECK HEARTBEAT → CHECK RAM → ACQUIRE (atomic) → RUN → RELEASE
```

- Acquisition creates the lock atomically (`O_CREAT | O_EXCL`). If another process wins the race, the result is `RESOURCE_GATE = BUSY`, `ACQUIRED = FALSE`, and the existing lock is left untouched.
- **Fail closed.** Any existing lock blocks acquisition: `ACTIVE_LOCK`, `UNKNOWN_LOCK`, and also `STALE_LOCK` until it has been cleared explicitly. If available RAM can't be determined, the result is `BLOCKED_RESOURCE`.
- An active lock is never overwritten. A stale lock is never cleared silently: `clear-stale` confirms that the lock is stale, reports the reason, emits the lock contents as evidence, and removes only that runtime file. It never removes an `ACTIVE_LOCK` or `UNKNOWN_LOCK`.
- **Release** requires a matching `owner_agent` and `mission_id`, plus a matching `pid` when one is supplied. A release by a non-owner fails closed.
- Long-running owners refresh `heartbeat_at_utc`, using `resource_guard.py heartbeat`, at intervals well under 900 s.
- R0 work needs no lock.

### Helper commands

```text
python scripts/resource_guard.py status [--json]
python scripts/resource_guard.py acquire --agent CODEX_LOCAL --mission <id> --class R3 [--min-ram-mb N] [--pid PID] [--command-summary TEXT]
python scripts/resource_guard.py heartbeat --agent CODEX_LOCAL --mission <id> [--pid PID]
python scripts/resource_guard.py release --agent CODEX_LOCAL --mission <id> [--pid PID]
python scripts/resource_guard.py clear-stale
```

The helper uses only the standard library. Exit codes: `0` OK, `2` BLOCKED_RESOURCE or BUSY, `3` refused (ownership mismatch, lock not stale, or malformed lock).

**`--pid`.** Pass the PID of the process that runs the workload. The default is the PID of the invoking shell, and the lock reads stale once that shell exits.

**Known limit.** The lock covers this repository and its worktrees only. A heavy job started from another repository, such as AG EdgeLab, isn't visible to it unless that repository resolves to the same lock path. Until then, agents must also report heavy jobs they know of in other repositories.

## 6. Process ownership

Never kill a process just because it uses memory. Classify each process as `MISSION_OWNED`, `OTHER_AGENT`, `OWNER_APPLICATION` or `UNKNOWN`.

An agent may automatically terminate only a process it can prove it started and no longer needs. It must never automatically terminate any of these:

- Chrome
- VS Code
- MT5
- MCP services
- owner terminals
- unknown Python processes
- another agent
- databases
- system processes

Report them to the owner as candidates for manual closure instead. `resource_guard.py` has no process-termination capability. It only checks whether a PID exists.

Never attribute an unrelated process to a specific agent unless provenance proves it.

## 7. Python worker policy

- The default is `workers = 1`. Never size workers automatically from CPU count.
- Raise the worker count only after measurements show there's headroom.
- Before launching multiprocessing, report `WORKER_COUNT`, `ESTIMATED_OR_MEASURED_MEMORY_PER_WORKER` and `AVAILABLE_RAM`.
- On this workstation, avoid running multi-worker experiments at the same time unless there's an explicit justification.

## 8. Memory-aware design and caches

**Preferred patterns:**

- streaming
- chunking
- bounded slices
- lazy loading
- memory mapping (where semantically safe)
- one symbol at a time
- one partition at a time

**Patterns to avoid:**

- loading everything at once
- copying large dataframes
- replaying symbols in parallel
- unbounded caches
- large multiprocessing pools

Optimizations must preserve deterministic semantics. Never trade correctness for lower memory use.

Caches must be bounded, versioned, identity-aware, causally safe and reproducible. Never reuse cached strategy or structure output across different dataset, strategy, parameter or partition hashes unless the cache contract explicitly proves they're equivalent.

## 9. Before and during substantial execution

Before substantial execution, report:

```text
AGENT =
MISSION =
RESOURCE_CLASS =
TOTAL_RAM_MB =
AVAILABLE_RAM_MB =
RESOURCE_LOCK =
OTHER_HEAVY_JOB_DETECTED =
PLANNED_WORKERS =
RESOURCE_GATE =
```

If the gate fails, set `FULL_WORKLOAD_STARTED = FALSE`. Only lightweight (R0) diagnostics may continue.

During R2/R3 jobs, periodically record:

- `elapsed_time`
- `process_RSS`
- `available_system_RAM`
- `worker_count`
- `progress`

Never add workers because progress seems slow. If memory gets close to unsafe levels:

1. Stop cleanly where possible.
2. Preserve partial diagnostics.
3. Never classify a partial result as authoritative.

## 10. Artifact discipline

Classify artifacts as `CANONICAL_EVIDENCE`, `INTERMEDIATE`, `CACHE`, `TEMPORARY` or `UNKNOWN`. Avoid keeping unnecessary duplicates of large generated artifacts, but never delete evidence automatically.

Only temporary or cache artifacts owned by the mission may be cleaned up automatically. Never delete canonical evidence, owner files, frozen datasets, manifests, sealed data or unknown artifacts.

## 11. Handoff

An agent that completes substantial work reports:

```text
AGENT =
MISSION =
RESOURCE_CLASS =
HEAVY_PROCESS_LEFT_RUNNING =
PID_IF_ANY =
RESOURCE_LOCK_RELEASED =
GENERATED_ARTIFACTS =
COMMIT_SHA =
NEXT_AGENT =
NEXT_ACTION =
```

Preferred handoff flows:

- **Claude → Codex:** Claude implements, runs focused tests, freezes a commit and releases resources. Codex then verifies independently. Claude must not leave test or replay workers running during the handoff.
- **Codex → Arena:** Codex produces the evidence and Arena reviews it remotely, analyzing the artifacts instead of repeating expensive computation.
- **Arena → Claude:** Arena does the research, design or review, then Claude implements. External or open-source ideas remain candidate inputs, never verification authority.

## 12. Safety and integrity invariants

**Trading safety.** Resource management never weakens trading governance. Unless a separately authorized governance process changes them, these values stay as they are:

```text
DEMO_AUTHORIZED = FALSE
LIVE_AUTHORIZED = FALSE
BROKER_MUTATION = FALSE
```

A resource optimization never creates execution authority.

**Experiment integrity.** Resource pressure is never permission to:

- shrink a dataset quietly
- change strategy parameters
- drop expensive losing periods
- change friction
- open SEALED_OOS
- change eligibility
- skip verification gates

If resources can't support an authoritative experiment, the verdict is `BLOCKED_RESOURCE`. That is an acceptable outcome.

## 13. Threshold governance

The R1/R2/R3 thresholds in §2 are the initial operational gates. After successful profiling, agents may recommend revised thresholds based on measured peak RSS plus a reserve for the OS and applications. Agents never change the thresholds on their own; only the owner does.

## 14. Core invariant

Optimize resource usage before adding concurrency. On this workstation:

```text
ONE CORRECT HEAVY EXPERIMENT  >  THREE COMPETING FAST AGENTS
```

Correctness, reproducibility, data integrity and the stability of the owner's machine take priority over finishing quickly.
