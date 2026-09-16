# AG PROFIT TRADING — AUTO VALIDATION ORCHESTRATOR V1

**Repository:** `aungmyat1/AG-profit-trading-assit`  
**Parent plan:** `docs/validation/AG_ACCELERATED_VALIDATION_PLAN_V1.md`  
**Mode at initial deployment:** `GUIDED_AUTO / OBSERVE_ONLY`  
**Purpose:** Convert the accelerated validation plan into a deterministic, Task-Scheduler-driven validation control plane while preserving evidence integrity, holdout isolation, strategy semantics, and execution authority.

---

# 1. Mission

Build a reusable validation orchestrator that automatically answers:

```text
WHAT IS THE CURRENT VALIDATION STATE?
WHAT EVIDENCE HAS ARRIVED?
WHICH GATE IS READY?
WHAT IS BLOCKING PROGRESS?
WHAT IS THE NEXT SAFE ACTION?
DOES AN AGENT NEED TO RUN?
DOES THE OWNER NEED TO DECIDE?
```

The orchestrator coordinates validation. It does **not** trade and does **not** autonomously authorize strategy promotion.

Target architecture:

```text
WINDOWS TASK SCHEDULER
        │
        ▼
VALIDATION ORCHESTRATOR
        │
        ├── canonical-state reader
        ├── evidence/readiness evaluator
        ├── dependency DAG
        ├── deterministic tests
        ├── state/event ledger
        ├── prompt renderer
        └── mission dispatcher
                 │
       ┌─────────┴─────────┐
       ▼                   ▼
 ROUTINE EVENT        IMPORTANT GATE
 deterministic             │
 scripts only               ▼
                      CLAUDE OPERATOR
                           │
                      evidence packet
                           │
                           ▼
                     DEEPSEEK AUDITOR
                           │
                     PASS/FAIL/BLOCK
                           │
                           ▼
                      ORCHESTRATOR
```

---

# 2. Non-Negotiable Authority Boundary

The orchestrator may automatically calculate readiness such as:

```text
READY_FOR_AGGREGATION
READY_FOR_ECONOMIC_EVALUATION
READY_FOR_ROBUSTNESS
READY_FOR_HOLDOUT_REVIEW
AUDIT_REQUIRED
WAITING_DATA
TERMINAL_FAIL
```

It must never automatically create or imply:

```text
FRICTION_POLICY_SIGNED
HOLDOUT_OPENED
DEMO_AUTHORIZED
LIVE_AUTHORIZED
OWNER_APPROVED
```

Those remain explicit governance decisions under existing repository authority.

The validation orchestrator must not import, call, wrap, or expose order execution functions.

---

# 3. Current Frozen Work Must Remain Untouched

The running Large-SMC campaign `LSMC_EURUSD_FRICTION_WP3A1_V1` remains frozen.

Do not change:

- campaign manifest,
- collection windows,
- sample frequency,
- minimum days,
- C10,
- Large-SMC strategy semantics,
- SSC frozen hypotheses,
- validation thresholds,
- holdout state,
- Demo/Live authorization.

The orchestrator observes these artifacts and schedules around them. It does not rewrite them.

---

# 4. Automation Levels

## LEVEL 0 — MANUAL

```text
scheduler collects evidence
owner invokes agents manually
```

## LEVEL 1 — GUIDED_AUTO — INITIAL PRODUCTION TARGET

```text
scheduler
   ↓
orchestrator detects gate
   ↓
exact agent mission rendered
   ↓
owner launches/approves agent mission
```

## LEVEL 2 — AUTO_RESEARCH

Only after Level 1 has produced clean orchestration evidence:

```text
routine research missions may dispatch automatically
Claude → evidence packet → DeepSeek audit
```

Sensitive transitions remain owner controlled.

No Level 3 autonomous `research → Demo → Live` mode is permitted.

---

# 5. Canonical Validation State Machine

Supported high-level states:

```text
NOT_REGISTERED
REGISTERED
ENGINE_QUALIFIED
WAITING_EVIDENCE
EVIDENCE_ADEQUATE
READY_FOR_ECONOMIC_GATE
ECONOMIC_PASS
READY_FOR_ROBUSTNESS
ROBUSTNESS_PASS
READY_FOR_HOLDOUT_REVIEW
HOLDOUT_PASS
FORWARD_VALIDATION
DEMO_ELIGIBILITY_REVIEW
TERMINAL_FAIL
```

Additional control states:

```text
BLOCKED
WAITING_DATA
INCONCLUSIVE
AUDIT_REQUIRED
AUDIT_FAILED
REMEDIATION_REQUIRED
OWNER_DECISION_REQUIRED
```

State must be derived from canonical evidence. The orchestrator must not silently edit lifecycle files to make observed state agree with its calculation.

---

# 6. Strategy-Neutral Status Contract

For every registered strategy, expose at minimum:

```yaml
strategy_id: string
strategy_version: string
lifecycle_stage: string
current_gate: string
furthest_verified_gate: string
validation_state: string
blocking_reasons: []
evidence_status: string
dataset_role_status: string
lineage_status: string
holdout_status: string
demo_authorized: false
live_authorized: false
next_safe_action: string
agent_required: NONE|CLAUDE|DEEPSEEK|OWNER
updated_at_utc: timestamp
```

All state snapshots must be reproducible from repository evidence.

---

# 7. Persistent Orchestration Ledger

Create an append-only event ledger separate from strategy evidence.

Suggested location:

```text
artifacts/validation/orchestrator/
    state.json
    events.jsonl
    missions/
    packets/
    reports/
```

Example event:

```json
{
  "event_id": "...",
  "timestamp_utc": "...",
  "strategy_id": "ST_LARGE_SMC_V1",
  "event_type": "READINESS_CHANGED",
  "from_state": "WAITING_EVIDENCE",
  "to_state": "READY_FOR_AGGREGATION",
  "evidence_refs": ["..."],
  "manifest_hash": "...",
  "next_safe_action": "RUN_AGGREGATION",
  "authority_changed": false
}
```

Requirements:

- append-only event history,
- atomic writes,
- deterministic IDs where appropriate,
- restart-safe,
- idempotent repeated evaluation,
- no duplicate mission creation for the same gate/evidence identity.

---

# 8. Evidence-Triggered Readiness

Readiness must be deterministic.

Large-SMC example:

```text
IF
  complete_trading_days >= frozen minimum
  AND valid_windows >= frozen minimum
  AND real_observations >= frozen minimum
  AND manifest_hash == frozen manifest hash
  AND provenance_valid == true
THEN
  READY_FOR_AGGREGATION = true
```

SSC example:

```text
IF
  treatment_N >= frozen minimum
  AND prospective checkpoint reached
  AND lineage_valid == true
  AND data_role == COUNTING
THEN
  READY_FOR_ECONOMIC_EVALUATION = true
```

Readiness predicates must consume frozen contracts rather than duplicate important thresholds as new magic constants where practical.

---

# 9. Dependency DAG

The orchestrator must model gate dependencies explicitly.

```text
ENGINE_QUALIFIED
      ↓
EVIDENCE_ADEQUATE
      ↓
ECONOMIC_GATE
      ↓
ROBUSTNESS
      ↓
HOLDOUT_REVIEW
      ↓
FORWARD_VALIDATION
      ↓
DEMO_ELIGIBILITY_REVIEW
```

A downstream mission cannot run when its prerequisites are not verified.

A failed upstream gate locks downstream gates unless a new separately governed hypothesis/version establishes a new lineage.

---

# 10. Fast-Fail Execution

Run inexpensive gates before expensive gates.

```text
economics
   ↓ PASS
friction stress
   ↓ PASS
parameter neighborhood
   ↓ PASS
cross-period stability
   ↓ PASS
walk-forward/OOS
   ↓ PASS
holdout review
```

On a preregistered terminal failure:

```text
NEXT_SAFE_ACTION = STOP_OR_OPEN_NEW_HYPOTHESIS
```

Do not automatically mutate the failed strategy into a new candidate.

---

# 11. Windows Task Scheduler Design

Keep exact market-evidence collection tasks separate where precise timing matters.

Add a small number of stable orchestration triggers.

Recommended MMT schedule:

| Task | Time | Function | AI |
|---|---:|---|---|
| `AG_VALIDATION_PREFLIGHT` | 12:50 | repo/broker/scheduler/evidence health | No |
| existing LSMC A | 12:00 | exact friction collection | No |
| existing BTC evidence | 13:05 | existing BTC evidence window | No |
| existing LSMC B | 13:20 | exact friction collection | No |
| existing LSMC C | 15:30 | exact friction collection | No |
| existing LSMC D | 19:00 | exact friction collection | No |
| `AG_VALIDATION_CHECKPOINT` | 19:15 | evaluate all strategy readiness | No |
| `AG_VALIDATION_DAILY_REPORT` | 21:35 | combined validation report | No |
| `AG_VALIDATION_GATE_DISPATCH` | 21:40 | render pending gate missions | Conditional |
| `AG_VALIDATION_WEEKLY_AUDIT` | weekend | cross-strategy integrity packet | Claude + DeepSeek only if required |

Scheduler installation must be idempotent and must not overwrite existing campaign tasks unless explicitly intended and verified.

Task failure must be visible in the daily report.

---

# 12. Stable Orchestrator Commands

Prefer a small command surface:

```text
python scripts/run_validation_orchestrator.py --event preflight
python scripts/run_validation_orchestrator.py --event checkpoint
python scripts/run_validation_orchestrator.py --event daily-close
python scripts/run_validation_orchestrator.py --event gate-dispatch
python scripts/run_validation_orchestrator.py --event weekly-audit
```

Optional read-only commands:

```text
python scripts/run_validation_orchestrator.py --status
python scripts/run_validation_orchestrator.py --strategy ST_LARGE_SMC_V1
python scripts/run_validation_orchestrator.py --pending-missions
```

Do not place order/execution commands in this CLI.

---

# 13. Agent Mission Registry

Suggested structure:

```text
docs/validation/agent_prompts/
    00_ORCHESTRATOR_CONTRACT.md
    claude/
        C01_IMPLEMENTATION_OPERATOR.md
        C02_GATE_OPERATOR.md
        C03_AGGREGATION_OPERATOR.md
        C04_ECONOMIC_GATE_OPERATOR.md
        C05_ROBUSTNESS_OPERATOR.md
        C06_HOLDOUT_PREPARATION.md
        C07_FORWARD_EVIDENCE_OPERATOR.md
        C08_REMEDIATION_OPERATOR.md
    deepseek/
        D01_FOUNDATION_AUDITOR.md
        D02_EVIDENCE_AUDITOR.md
        D03_AGGREGATION_AUDITOR.md
        D04_ECONOMIC_AUDITOR.md
        D05_ROBUSTNESS_AUDITOR.md
        D06_HOLDOUT_AUDITOR.md
        D07_FORWARD_AUDITOR.md
        D08_REMEDIATION_AUDITOR.md
```

Prompts should be templates using fields such as:

```text
{{MISSION_ID}}
{{STRATEGY_ID}}
{{STRATEGY_VERSION}}
{{CURRENT_GATE}}
{{CANONICAL_HEAD}}
{{DATASET_ID}}
{{DATASET_HASH}}
{{MANIFEST_PATH}}
{{MANIFEST_HASH}}
{{EVIDENCE_PACKET}}
{{EXPECTED_OUTPUT}}
```

---

# 14. Universal Agent Output Envelope

Every Claude/DeepSeek mission must end with a parseable envelope:

```text
MISSION_ID:
AGENT_ROLE:
STRATEGY_ID:
STRATEGY_VERSION:

REPOSITORY_HEAD_BEFORE:
REPOSITORY_HEAD_AFTER:

CURRENT_GATE:
MISSION_STATUS:

INPUT_MANIFEST_HASH:
OUTPUT_ARTIFACT_HASH:

EVIDENCE_STATUS:
LINEAGE_STATUS:
HOLDOUT_STATUS:

STRATEGY_SEMANTICS_CHANGED:
VALIDATION_CORE_CHANGED:
EXECUTION_AUTHORITY_CHANGED:

TEST_STATUS:

GATE_RESULT:
BLOCKERS:

NEXT_SAFE_ACTION:
OWNER_DECISION_REQUIRED:

STOP.
```

The orchestrator should reject malformed agent results rather than guessing their meaning.

---

# 15. Claude Prompt Pack

## C01 — IMPLEMENTATION OPERATOR

```text
AG PROFIT TRADING — CLAUDE IMPLEMENTATION OPERATOR

Mission: {{MISSION_ID}}
Repository: AG-profit-trading-assit
Canonical head expected: {{CANONICAL_HEAD}}
Work package: {{EXPECTED_OUTPUT}}

You are the implementation/operator agent, not promotion authority.

P0 — Preflight
1. Inspect git branch, HEAD, status and relevant frozen contracts.
2. Preserve unrelated working-tree changes.
3. Verify the mission does not modify strategy semantics, holdout authority, Demo/Live authority or active frozen campaign definitions unless the mission explicitly and lawfully requires such a change.
4. STOP on contradictory canonical contracts.

Implementation rules
- Reuse existing validation framework before creating new infrastructure.
- Prefer additive, deterministic, strategy-neutral components.
- All writes must be restart-safe/idempotent where relevant.
- No execution/order paths.
- No threshold tuning from observed results.
- No holdout access unless explicitly authorized by the mission contract.
- Add focused tests.

Verification
- Run narrow tests first, then relevant regression/containment tests.
- Report exact files changed.
- Report strategy semantics diff, validation-core diff and execution-authority diff.
- Produce deterministic evidence artifacts/hashes where applicable.

Finish with the universal agent output envelope.
STOP after the mission. Do not begin the next work package automatically.
```

## C02 — GENERIC GATE OPERATOR

```text
AG PROFIT TRADING — CLAUDE GATE OPERATOR

MISSION_ID={{MISSION_ID}}
STRATEGY={{STRATEGY_ID}} {{STRATEGY_VERSION}}
CURRENT_GATE={{CURRENT_GATE}}
MANIFEST={{MANIFEST_PATH}}
MANIFEST_HASH={{MANIFEST_HASH}}
EVIDENCE_PACKET={{EVIDENCE_PACKET}}

Mission: execute only the deterministic work required by the current gate and produce a reproducible evidence packet.

Rules:
- Verify HEAD/working tree and frozen identity first.
- Verify dataset role, lineage and manifest hash.
- Do not inspect sealed holdout unless CURRENT_GATE explicitly authorizes controlled holdout access.
- Do not change strategy parameters or thresholds.
- Do not promote lifecycle or execution authority.
- If prerequisites are incomplete: return BLOCKED/WAITING_DATA and STOP.
- If a frozen terminal failure occurs: report it without remediation.
- If PASS: report readiness for the next review, not authorization.

Run relevant tests and finish with the universal output envelope.
STOP.
```

## C03 — AGGREGATION OPERATOR

```text
AG PROFIT TRADING — CLAUDE AGGREGATION OPERATOR

MISSION_ID={{MISSION_ID}}
STRATEGY={{STRATEGY_ID}}
EVIDENCE_PACKET={{EVIDENCE_PACKET}}
MANIFEST_HASH={{MANIFEST_HASH}}

Aggregate only already-collected canonical evidence.

Required:
- verify completeness against frozen campaign contract;
- verify raw/session hashes;
- preserve missing observations honestly;
- no backfill, interpolation, adaptive deletion or unfavorable-session exclusion;
- compute per-window, per-day and aggregate descriptive statistics required by the frozen contract;
- produce combined evidence hash/manifest where canonical methodology permits;
- keep commission/slippage unavailable when evidence is unavailable;
- do not sign policy or modify strategy semantics/C10.

If minimum evidence is not satisfied, return NOT_READY and STOP.

Produce a compact DeepSeek audit packet with evidence refs and reproduction commands, not unnecessary raw data.
Finish with universal output envelope.
STOP.
```

## C04 — ECONOMIC GATE OPERATOR

```text
AG PROFIT TRADING — CLAUDE ECONOMIC GATE OPERATOR

MISSION_ID={{MISSION_ID}}
STRATEGY={{STRATEGY_ID}} {{STRATEGY_VERSION}}
DATASET={{DATASET_ID}}
DATASET_HASH={{DATASET_HASH}}
MANIFEST={{MANIFEST_PATH}}

Execute the preregistered economic evaluation only.

Required:
- verify counting data role and lineage;
- apply the authorized friction model exactly;
- compute frozen primary/secondary metrics;
- preserve occurrence identity;
- no parameter search;
- no threshold changes;
- no holdout access;
- run configured stress levels only as robustness descriptors unless the frozen gate says otherwise;
- classify PASS/FAIL/INCONCLUSIVE exactly from preregistered rules.

A FAIL must remain FAIL. Do not propose a parameter modification inside this mission.
Produce evidence packet + universal envelope.
STOP.
```

## C05 — ROBUSTNESS OPERATOR

```text
AG PROFIT TRADING — CLAUDE ROBUSTNESS OPERATOR

Run only robustness tests authorized by the frozen validation profile.

Order inexpensive tests first:
1. friction sensitivity;
2. parameter-neighborhood stability;
3. cross-period stability;
4. walk-forward/OOS;
5. cross-symbol/venue replication only where methodologically justified.

Stop at a preregistered terminal failure.
Do not open final holdout.
Do not search until a passing configuration appears.
Record every tested candidate/neighborhood required by the protocol.
Produce reproducible artifacts and universal output envelope.
STOP.
```

## C06 — HOLDOUT PREPARATION

```text
AG PROFIT TRADING — CLAUDE HOLDOUT PREPARATION

This mission prepares a candidate for owner-controlled final holdout review.

Do NOT access holdout contents.

Verify:
- economic PASS;
- robustness prerequisites PASS;
- candidate semantic hash frozen;
- parameter/config hash frozen;
- dataset-role firewall intact;
- holdout access count unchanged;
- exact one-shot/frozen holdout evaluation command can be constructed without executing it.

Output READY_FOR_HOLDOUT_REVIEW or BLOCKED.
OWNER_DECISION_REQUIRED must be TRUE when ready.
STOP.
```

## C07 — FORWARD EVIDENCE OPERATOR

```text
AG PROFIT TRADING — CLAUDE FORWARD EVIDENCE OPERATOR

Inspect only prospective/forward evidence allowed by the strategy contract.

Do not manufacture occurrences to meet a calendar target.
Do not loosen setup criteria.
Verify occurrence lineage, timestamps, provenance, completeness and frozen minimum-N/session/regime requirements.
Report WAITING_DATA until adequacy is genuinely reached.
No Demo/Live authorization changes.
Finish with universal envelope.
STOP.
```

## C08 — REMEDIATION OPERATOR

```text
AG PROFIT TRADING — CLAUDE REMEDIATION OPERATOR

Use only after an audit or gate reports a concrete defect.

Fix the smallest reproducible implementation/infrastructure defect without changing the scientific question.
Do not remediate a negative economic result by tuning parameters.
Do not reopen terminal hypotheses.
Preserve original evidence and document supersession rather than deleting failed artifacts.
Run regression and containment tests.
Return to independent audit after remediation.
STOP.
```

---

# 16. DeepSeek Prompt Pack

## D01 — FOUNDATION AUDITOR

```text
AG PROFIT TRADING — DEEPSEEK FOUNDATION AUDITOR

MISSION_ID={{MISSION_ID}}
TARGET_HEAD={{CANONICAL_HEAD}}

Read-only independent audit.
Do not trust Claude's summary as evidence.
Reproduce claims from repository artifacts/code/tests.

Verify:
- commit scope;
- deterministic behavior;
- state-machine fail-closed properties;
- no execution authority introduced;
- no strategy-semantic contamination;
- no holdout weakening;
- idempotency/restart behavior;
- relevant tests independently.

Classify findings P0/P1/P2/P3.
Return AUDIT_PASS, AUDIT_FAIL or AUDIT_BLOCKED.
Finish with universal output envelope.
Do not modify repository.
STOP.
```

## D02 — EVIDENCE AUDITOR

```text
AG PROFIT TRADING — DEEPSEEK EVIDENCE AUDITOR

Independently verify the evidence packet against raw/canonical repository evidence.

Check:
- manifest identity/hash;
- provenance;
- expected vs completed observations/windows/occurrences;
- missing gaps;
- duplicate semantics;
- lineage/data role;
- no backfill/interpolation/deletion;
- scheduler opportunity where relevant;
- strategy/validation/execution diffs.

Do not infer missing evidence.
Return VERIFIED / CONTRADICTED / NOT_VERIFIED per material claim.
Finish with universal envelope.
Read-only. STOP.
```

## D03 — AGGREGATION AUDITOR

```text
AG PROFIT TRADING — DEEPSEEK AGGREGATION AUDITOR

Recompute aggregation independently from canonical evidence.

Verify:
- included session set;
- hashes;
- minimum evidence contract;
- descriptive statistics;
- missing-data treatment;
- combined hash if defined;
- commission/slippage classification;
- no policy/C10/strategy mutation.

Do not merely inspect Claude's generated aggregate.
Return AUDIT_PASS/FAIL/BLOCKED and exact disagreements.
Read-only. STOP.
```

## D04 — ECONOMIC AUDITOR

```text
AG PROFIT TRADING — DEEPSEEK ECONOMIC AUDITOR

Independently reproduce the economic gate from frozen candidate + counting dataset + authorized friction model.

Verify:
- dataset hash/role;
- candidate identity;
- occurrence count;
- metric calculations;
- friction application;
- preregistered thresholds;
- PASS/FAIL/INCONCLUSIVE classification;
- no hidden parameter search;
- holdout untouched.

Do not rank or rescue candidates.
Read-only. STOP.
```

## D05 — ROBUSTNESS AUDITOR

```text
AG PROFIT TRADING — DEEPSEEK ROBUSTNESS AUDITOR

Reproduce the required robustness claims independently.
Check tested neighborhood/search scope against preregistration.
Detect cherry-picking, omitted failures, adaptive threshold changes and data-role leakage.
Verify fast-fail stopping was applied correctly.
Do not open holdout.
Read-only. STOP.
```

## D06 — HOLDOUT AUDITOR

```text
AG PROFIT TRADING — DEEPSEEK HOLDOUT AUDITOR

Before holdout execution, verify the candidate is truly frozen and all prerequisites are satisfied.
Do not inspect holdout contents unless the owner-controlled holdout mission explicitly authorizes access.
Verify access counters/firewalls and candidate/config hashes.
Return READY_FOR_OWNER_HOLDOUT_DECISION or BLOCKED.
Read-only. STOP.
```

## D07 — FORWARD AUDITOR

```text
AG PROFIT TRADING — DEEPSEEK FORWARD EVIDENCE AUDITOR

Independently audit prospective evidence.
Verify timestamps are after the frozen boundary, occurrence identity is valid, no historical/synthetic evidence is counted as forward, no setup criteria were loosened, and minimum-N/session/regime rules are satisfied.
Return WAITING_DATA until the frozen adequacy rule is met.
No execution authority changes. Read-only. STOP.
```

## D08 — REMEDIATION AUDITOR

```text
AG PROFIT TRADING — DEEPSEEK REMEDIATION AUDITOR

Audit a remediation commit against the original defect.
Verify the defect is fixed with minimum scope and no scientific-semantic drift.
Check original failed evidence remains preserved.
Reproduce relevant tests.
Return AUDIT_PASS/FAIL/BLOCKED.
Read-only. STOP.
```

---

# 17. Agent Dispatch Policy

Routine events do not require an LLM.

```text
new scheduled row
new session file
no readiness change
same WAITING_DATA state
```

→ deterministic processing only.

Agent mission required when, for example:

```text
first complete campaign day
campaign reaches frozen adequacy
new economic gate becomes ready
robustness gate becomes ready
candidate becomes holdout-ready
material integrity failure occurs
remediation requires implementation
weekly integrity checkpoint is due
```

Claude normally acts first for implementation/aggregation/evaluation. DeepSeek audits important gate output independently.

---

# 18. Mission Identity and Idempotency

Mission identity should include enough immutable context to prevent duplicate execution, for example:

```text
sha256(
  strategy_id
  + strategy_version
  + gate
  + evidence_identity
  + manifest_hash
  + mission_type
)
```

If an identical successful mission already exists, gate dispatch should report it rather than creating another mission.

A changed evidence set creates a new mission identity only when the gate protocol allows reevaluation.

Final holdout must have stricter one-shot/access-count governance than ordinary missions.

---

# 19. Failure and Retry Rules

Differentiate:

```text
INFRA_FAILURE
DATA_NOT_DUE
DATA_MISSING
SCIENTIFIC_FAIL
AUDIT_FAIL
OWNER_DECISION_REQUIRED
```

Infrastructure retry must never become scientific rerun permission.

Examples:

- MT5 disconnected → infrastructure failure; retry collection only if frozen campaign rules permit it. Never fabricate missed market evidence.
- economic gate FAIL → scientific fail; do not rerun until PASS.
- malformed agent output → mission failure; may rerun same mission because scientific evidence did not change.
- holdout executed successfully → never rerun merely because result was unfavorable.

---

# 20. Daily Report Contract

Produce a compact report around 21:35 MMT:

```text
AG VALIDATION DAILY STATUS
DATE:
HEAD:

STRATEGY | STATE | EVIDENCE | CURRENT GATE | BLOCKER | NEXT SAFE ACTION

SCHEDULER HEALTH:
BROKER/DATA HEALTH:
NEW EVIDENCE:
NEW GATE TRANSITIONS:
PENDING CLAUDE MISSIONS:
PENDING DEEPSEEK AUDITS:
OWNER DECISIONS REQUIRED:
EXECUTION AUTHORITY CHANGED: false
```

The daily report is informational and cannot itself promote strategies.

---

# 21. API / Dashboard Integration

After core orchestration is proven, expose read-only endpoints such as:

```text
GET /api/validation/status
GET /api/validation/strategies/{strategy_id}
GET /api/validation/missions
GET /api/validation/events
```

Frontend may display:

```text
Strategy
Lifecycle
Current gate
Evidence progress
Blocker
Next safe action
Agent/audit status
```

No Demo/Live execution controls are part of this work package.

---

# 22. Implementation Work Packages

## AVO-WP1 — State Model + Read-Only Orchestrator

Implement canonical status derivation without scheduler or agent dispatch.

Acceptance:

- all active strategies visible;
- state derived from existing evidence;
- no canonical strategy mutation;
- deterministic repeated output;
- focused tests.

## AVO-WP2 — Readiness Predicates + Dependency DAG

Implement explicit gate prerequisites and blockers.

Acceptance:

- downstream gates fail closed;
- thresholds sourced from frozen contracts where possible;
- no promotion authority.

## AVO-WP3 — Persistent State/Event Ledger

Acceptance:

- append-only events;
- atomic/restart-safe state;
- idempotent evaluation;
- deterministic event/mission identity.

## AVO-WP4 — Task Scheduler Integration

Implement idempotent PowerShell/install tooling for the stable orchestrator tasks.

Acceptance:

- existing LSMC campaign tasks preserved;
- exact task inventory reported;
- task commands point only to validation orchestration/collection paths;
- no order execution paths.

## AVO-WP5 — Prompt Registry + Renderer

Implement parameterized prompt templates and deterministic mission packet generation.

Acceptance:

- no strategy-specific prompt duplication where avoidable;
- rendered prompt records all immutable context/hashes;
- malformed/missing context fails closed.

## AVO-WP6 — Agent Handoff Packets

Standardize compact Claude→DeepSeek evidence packets.

Acceptance:

- evidence refs + reproduction commands;
- hashes;
- exact commit/diff scope;
- no need to dump bulk raw ticks into prompts.

## AVO-WP7 — Gate Dispatcher

Initially implement `GUIDED_AUTO` only.

Acceptance:

- detects new mission requirement;
- renders mission;
- does not execute sensitive mission automatically;
- no duplicate mission generation.

## AVO-WP8 — Failure/Retry/Idempotency

Acceptance:

- infrastructure failure distinguished from scientific fail;
- safe retry semantics;
- final holdout protected from rerun;
- restart tests.

## AVO-WP9 — Read-Only API/Dashboard

Acceptance:

- status/events/missions visible;
- no execution mutation route;
- frontend authority remains UI-only.

## AVO-WP10 — End-to-End Dry Run

Use synthetic orchestration fixtures, not fabricated strategy evidence, to prove state transitions.

Test scenarios:

```text
WAITING_DATA stays waiting
new evidence makes aggregation ready
malformed evidence blocks
Claude packet awaits DeepSeek
DeepSeek pass unlocks next readiness
DeepSeek fail enters remediation/audit-failed
terminal economic fail locks downstream
owner-decision state cannot self-approve
restart does not duplicate events/missions
```

Only after WP10 passes may Level 1 be considered production-ready.

---

# 23. Rollout

```text
PHASE A
AVO-WP1–WP3
OBSERVE_ONLY

PHASE B
AVO-WP4–WP6
scheduler + prompt preparation

PHASE C
AVO-WP7–WP10
GUIDED_AUTO

PHASE D
collect orchestration evidence

PHASE E
independent audit

PHASE F
optionally authorize AUTO_RESEARCH for explicitly whitelisted non-sensitive mission types
```

Default remains `GUIDED_AUTO` until explicitly changed.

---

# 24. Security / Safety Invariants

The following must remain true after every AVO work package:

```text
strategy semantics unchanged unless explicitly scoped
G0–G10 authority unchanged
holdout firewall intact
active campaign definitions unchanged
Demo authority unchanged
Live authority unchanged
no order_send/order execution reachable from orchestrator
no agent can self-sign owner decisions
no failed evidence deleted
no missing evidence fabricated
no validation threshold adapted after seeing judged evidence
```

Any violation is P0 and implementation must stop.

---

# 25. First Claude Implementation Mission

Use the following after this specification is available locally:

```text
AG PROFIT TRADING — AVO-WP1 IMPLEMENTATION

Read first:
- docs/validation/AG_ACCELERATED_VALIDATION_PLAN_V1.md
- docs/validation/AG_AUTO_VALIDATION_ORCHESTRATOR_V1.md
- current G0–G10 validation contracts
- current strategy registry/lifecycle files

Mission: implement AVO-WP1 only — State Model + Read-Only Orchestrator.

Do not implement Task Scheduler integration, agent dispatch, API mutation, WP2+, or any execution capability in this mission.

Requirements:
1. Preflight branch/HEAD/status and preserve unrelated .vscode/settings.json / pyrightconfig.json changes if still present.
2. Inventory existing validation status/readiness code and reuse it.
3. Implement a strategy-neutral read-only state model for all registered validation strategies.
4. Derive status from canonical repository artifacts; do not mutate lifecycle or strategy files.
5. Expose deterministic CLI status for all strategies and one selected strategy.
6. Include blockers, current gate, furthest verified gate, evidence state, lineage/data-role/holdout state, Demo/Live flags and NEXT_SAFE_ACTION.
7. Fail closed on contradictory/missing canonical evidence.
8. Add focused deterministic tests including repeated-run equality and execution-containment checks.
9. Do not touch the running WP3A.1 campaign definition or C10.
10. Do not access sealed holdout contents.

Before commit, prove strategy semantics diff, validation authority diff and execution authority diff are empty except additive orchestrator infrastructure explicitly required by WP1.

Produce a compact DeepSeek audit packet with reproduction commands.
Commit only WP1 if tests pass.
Finish with the universal agent output envelope from the orchestrator specification.
STOP.
```

---

# 26. First DeepSeek Audit Mission

Run only after Claude completes AVO-WP1:

```text
AG PROFIT TRADING — AVO-WP1 INDEPENDENT AUDIT

Read:
- docs/validation/AG_ACCELERATED_VALIDATION_PLAN_V1.md
- docs/validation/AG_AUTO_VALIDATION_ORCHESTRATOR_V1.md
- Claude's AVO-WP1 commit and audit packet

Mission: independently audit AVO-WP1 in read-only mode.

Do not trust Claude's packet as evidence. Reproduce from repository state.

Verify:
1. commit scope is limited to WP1;
2. state model is read-only;
3. all registered strategies are represented correctly;
4. status is derived from canonical evidence rather than invented mutable state;
5. repeated evaluation is deterministic;
6. contradictory/missing evidence fails closed;
7. strategy semantics are unchanged;
8. active WP3A.1 campaign and C10 are unchanged;
9. holdout firewall is unchanged;
10. Demo/Live authority is unchanged;
11. no order/execution path is reachable/imported;
12. independently reproduce relevant tests.

Classify findings P0/P1/P2/P3.
Return AUDIT_PASS_WP1, AUDIT_FAIL_WP1 or AUDIT_BLOCKED_WP1.
No repository modifications.
Finish with the universal agent output envelope.
STOP.
```

---

# 27. Definition of Success

The orchestrator succeeds when validation becomes mostly self-organizing without becoming self-authorizing:

```text
market evidence arrives automatically
        ↓
state updates deterministically
        ↓
ready gates detected automatically
        ↓
correct mission prepared automatically
        ↓
Claude executes bounded work
        ↓
DeepSeek independently audits important gates
        ↓
owner is asked only when a real governance decision exists
```

This is the intended fastest safe operating model for the current AG Profit Trading validation program.
