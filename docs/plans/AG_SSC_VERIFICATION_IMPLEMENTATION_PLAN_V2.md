The 5-stage collapse is a good improvement, but I would **not adopt it exactly as written**. It can reduce agent turns substantially, but three parts need correction so speed does not weaken validation.

The best architecture is a **5-stage pipeline with internal hard checkpoints**. In other words, collapse agent sessions and data loading—not scientific gates.

# Updated AG SSC Verification Plan V2

```text
GEN_002 DATA ADMISSION
FULL_PASS
     │
     ▼
┌─────────────────────────────────────┐
│ STAGE 1 — PREREGISTER & FREEZE      │
│ G1                                  │
│ Claude: freeze                      │
│ DeepSeek: audit                     │
└──────────────────┬──────────────────┘
                   │ PASS
                   ▼
┌─────────────────────────────────────┐
│ STAGE 2 — POPULATE & EVALUATE       │
│ G2 → internal checkpoint → G3/G4   │
│ Claude: one deterministic run       │
│ DeepSeek: combined audit            │
└──────────────────┬──────────────────┘
                   │ PASS
                   ▼
┌─────────────────────────────────────┐
│ STAGE 3 — STRESS & CANDIDATE FREEZE │
│ G5 → internal checkpoint → G6      │
│ Claude: robustness + freeze         │
│ DeepSeek: combined audit            │
└──────────────────┬──────────────────┘
                   │ PASS
                   ▼
┌─────────────────────────────────────┐
│ STAGE 4A — HOLDOUT                  │
│ G7                                  │
│ Candidate frozen → holdout ONCE     │
└──────────────────┬──────────────────┘
                   │ PASS
                   ▼
┌─────────────────────────────────────┐
│ STAGE 4B — PRODUCTION VERIFICATION  │
│ G8 → G9                             │
│ semantic parity → economic gate     │
└──────────────────┬──────────────────┘
                   │ PASS
                   ▼
┌─────────────────────────────────────┐
│ STAGE 5 — FINAL READINESS AUDIT     │
│ Complete hash/evidence chain        │
│ → DEMO_ELIGIBLE or NOT ELIGIBLE     │
└─────────────────────────────────────┘
```

This gives you most of the token savings of the proposed 5-stage system while preserving the important boundaries.

## Three changes I recommend

**First, `CURRENT_VALIDATION_STATE.json` should not be the single source of truth.** It should be a small **index/checkpoint**, while immutable manifests remain authoritative. Otherwise a corrupted or accidentally edited state file could rewrite the apparent history.

Use:

```text
Immutable manifest = authority
CURRENT_VALIDATION_STATE.json = pointer/index
Git = change provenance
```

Second, **Stage 2 can load GEN_002 once and perform population + evaluation in one process**, but it must freeze the population artifact/hash **before** evaluating outcomes. This is a very good optimization because you avoid rereading/reparsing M1/M15/H1 data while retaining the G2→G3 boundary.

Third, I would **not execute G7 + G8 + G9 as one uninterrupted operation**. The holdout is your highest-value evidence boundary. Run G7, persist the result, increment `holdout_run_count` from `0 → 1`, then continue to G8/G9 only after G7 passes. This can still happen in one Claude mission with a fail-closed checkpoint.

Also, the claimed “up to 75%” token reduction is not something I'd encode as a project expectation unless you measured it. The architecture should reduce scanning and context use substantially, but the exact percentage is workload-dependent.

---

# 1. Deterministic context anchor

I support adding:

```text
artifacts/validation/
ST_SESSION_SWEEP_CONTINUATION_V1/
CURRENT_VALIDATION_STATE.json
```

But I recommend a stronger schema than the proposed version:

```json
{
  "schema_version": "1.0",
  "strategy_id": "ST_SESSION_SWEEP_CONTINUATION_V1",
  "strategy_version": "1.0.0",
  "hypothesis_id": "HYP_002_SETUP_SELECTIVITY",

  "active_stage": "STAGE_1",
  "active_gate": "G1_PREREGISTRATION",

  "dataset": {
    "package_id": "SSC_FRESH_DEV_GEN_002_MT5_20260801_20260914",
    "fingerprint": "f8108d37448cae8f9fe2f16a9905abdf8991ac916cf4a497b11eaca2debbf5aa",
    "admission_status": "FULL_PASS"
  },

  "artifacts": {
    "preregistration": null,
    "population": null,
    "economic_result": null,
    "robustness": null,
    "candidate": null,
    "holdout": null,
    "parity": null,
    "canonical_economic_gate": null
  },

  "hashes": {
    "preregistration": null,
    "population": null,
    "economic_result": null,
    "robustness": null,
    "candidate": null,
    "holdout": null,
    "parity": null,
    "canonical_economic_gate": null
  },

  "holdout_run_count": 0,

  "status": {
    "demo_eligible": false,
    "demo_authorized": false,
    "live_authorized": false
  }
}
```

One important rule:

```text
CURRENT_VALIDATION_STATE.json MUST NEVER
override an immutable artifact.

If state JSON conflicts with a frozen manifest:
STOP_STATE_CONFLICT
```

That gives both agents a cheap entry point without sacrificing provenance.

---

# STAGE 1 — Preregister, Freeze & Audit

This remains essentially unchanged.

Do not let Claude automatically invent thresholds just to complete the mission.

## Claude Code — Stage 1

AG SSC VERIFICATION V2 — STAGE 1
G1 PREREGISTRATION + FREEZE

ROLE
Sole repository writer.

MISSION

Establish deterministic validation-state tracking and freeze HYP_002_SETUP_SELECTIVITY before GEN_002 receives any SSC setup detection or outcome inspection.

KNOWN VERIFIED INPUT

strategy =
ST_SESSION_SWEEP_CONTINUATION_V1

hypothesis =
HYP_002_SETUP_SELECTIVITY

dataset_package =
SSC_FRESH_DEV_GEN_002_MT5_20260801_20260914

dataset_fingerprint =
f8108d37448cae8f9fe2f16a9905abdf8991ac916cf4a497b11eaca2debbf5aa

admission =
FULL_PASS

Do not redo GEN_002 admission unless contradictory repository evidence is found.

PRECHECK

Check narrowly:

* branch/HEAD
* working tree
* active/conflicting writer
* existing canonical SSC research schemas
* existing hypothesis/preregistration conventions

If another writer owns target paths:
STOP_CONCURRENT_WRITER

STEP 1 — STATE INDEX

Create if absent:

artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/CURRENT_VALIDATION_STATE.json

It is an INDEX, not an independent source of truth.

Immutable manifests remain authoritative.

If state conflicts with an immutable manifest:
STOP_STATE_CONFLICT

Initialize verified GEN_002 identity and authorization=false state.

STEP 2 — PREREGISTRATION

Freeze HYP_002 before setup detection.

Freeze at minimum:

* falsifiable hypothesis
* parent strategy/version/hash
* dataset package/fingerprint
* EURUSD as primary development symbol unless authoritative existing evidence says otherwise
* GBPUSD excluded from pooled development evidence
* control
* treatment
* setup eligibility
* occurrence identity policy
* primary metric
* secondary diagnostics
* cost/friction model
* sample-adequacy rule
* minimum sample requirement
* PASS
* FAIL
* INCONCLUSIVE
* stopping rule
* zero-occurrence behavior
* missing-data policy
* duplicate policy
* multiple-comparison policy
* robustness policy
* GBPUSD replication policy
* holdout selection procedure
* prohibition on post-outcome modification

CRITICAL

Sample adequacy and decision thresholds must exist BEFORE setup counts/outcomes are inspected.

If an essential choice is not established by existing governance and requires owner adjudication:

STOP_OWNER_DECISION_REQUIRED

Do not invent a favorable threshold.

STEP 3 — FREEZE

Persist using canonical repository naming/schema.

Create immutable preregistration manifest/hash.

Update CURRENT_VALIDATION_STATE.json only with pointers/hash/status:

active_stage = STAGE_1
active_gate = G1_AUDIT
preregistration artifact path
preregistration hash

Do not duplicate the entire preregistration into the state index.

COMMIT

If repository governance permits commits and pre-existing unrelated modifications can be safely excluded, commit ONLY Stage-1 artifacts.

Suggested commit message:

validation(ssc): freeze HYP_002 preregistration

Do not require a Git tag unless existing repository governance uses tags for validation gates.

PROHIBITED

* setup detection
* population generation
* outcome inspection
* optimization
* parent strategy modification
* Track-A/V1.1.0 work
* holdout access
* execution-authority changes
* demo/live authorization
* broad test suite

TESTING

Focused manifest/schema/hash/state-index tests only.

TOKEN RULES

Do not restate project history.
Do not rescan already verified GEN_002.
Use canonical artifact references.
Use narrow searches/tests.
Stop when G1 is frozen.

OUTPUT ONLY

AG_SSC_STAGE1_FREEZE_STATUS

REPOSITORY
branch =
head_before =
head_after =
commit =

STATE_INDEX
path =
valid =
conflict =

PREREGISTRATION
artifact =
hash =
parent_hash =
dataset_fingerprint =
primary_symbol =
sample_rule =
primary_metric =
decision_rule =

LEAKAGE
setup_detection_executed =
population_generated =
outcomes_inspected =
holdout_accessed =

SAFETY
parent_changed =
execution_authority_changed =
demo_authorized =
live_authorized =

TESTS =

FINAL_VERDICT =
NEXT_SINGLE_ACTION =

Expected success:
NEXT_SINGLE_ACTION = INDEPENDENT_STAGE1_AUDIT

## DeepSeek — Stage 1 audit

AG SSC VERIFICATION V2 — STAGE 1 INDEPENDENT AUDIT

ROLE
READ-ONLY independent gatekeeper.

MISSION

Verify G1 preregistration sufficiently freezes HYP_002 before first GEN_002 strategy exposure.

START

Read:

CURRENT_VALIDATION_STATE.json

Then follow ONLY its referenced immutable artifacts plus relevant Git diff/commit.

Do not broadly re-index repository unless a concrete inconsistency requires it.

EXPECTED DATASET FINGERPRINT

f8108d37448cae8f9fe2f16a9905abdf8991ac916cf4a497b11eaca2debbf5aa

VERIFY

* state index agrees with immutable manifests
* preregistration hash reproduces
* dataset fingerprint matches
* parent frozen
* EURUSD development policy frozen
* GBPUSD not pooled
* control deterministic
* treatment deterministic
* sample adequacy precommitted
* primary metric precommitted
* costs precommitted
* PASS/FAIL/INCONCLUSIVE deterministic
* stopping rule deterministic
* robustness policy defined
* holdout procedure defined
* setup counts/outcomes not inspected
* parent unchanged
* execution authority unchanged

FAIL CLOSED

Any choice still selectable after observing GEN_002 = BLOCKER.

Do not repair anything.

OUTPUT ONLY

AG_SSC_STAGE1_INDEPENDENT_AUDIT

STATE_CONSISTENT =
HASH_VALID =
DATASET_MATCH =
PARENT_FROZEN =
SAMPLE_RULE_PRECOMMITTED =
METRICS_PRECOMMITTED =
DECISION_RULE_PRECOMMITTED =
SYMBOL_POLICY_VALID =
HOLDOUT_POLICY_FROZEN =
LEAKAGE_DETECTED =

BLOCKERS =
NON_BLOCKING =

FINAL_VERDICT =
PERMIT_STAGE_2 = true/false
NEXT_SINGLE_ACTION =

If PASS:
GENERATE_AND_EVALUATE_FROZEN_HYP002

---

# STAGE 2 — Population + Economic Evaluation

This is where your proposed optimization has the greatest value.

Instead of:

```text
load dataset
→ population
→ exit
→ reload dataset
→ economic evaluation
```

use:

```text
load GEN_002 ONCE
       ↓
setup detection
       ↓
WRITE + HASH POPULATION       ← HARD CHECKPOINT
       ↓
verify population manifest
       ↓
control/treatment evaluation
       ↓
WRITE + HASH ECONOMIC RESULT
```

The population must exist as a frozen artifact **before the evaluator receives its outcomes**.

## Claude — Stage 2

AG SSC VERIFICATION V2 — STAGE 2
G2 POPULATION + G3/G4 ECONOMIC EVALUATION

PRECONDITION

Stage-1 independent audit:
PERMIT_STAGE_2 = true

ROLE
Sole executor/writer.

START

Read CURRENT_VALIDATION_STATE.json and referenced immutable manifests.

Do not rediscover completed gates.

Verify:
dataset fingerprint
preregistration hash
parent hash

MISSION

Perform G2 and G3/G4 efficiently in ONE process/data-load where practical while preserving a mandatory immutable checkpoint between population generation and outcome evaluation.

STEP A — LOAD

Load frozen EURUSD GEN_002 evidence once.

Do not load GBPUSD into the development population.

STEP B — G2 POPULATION

Execute frozen parent setup detector exactly once.

Generate canonical occurrence identities/provenance.

Before ANY economic treatment comparison:

1. persist population;
2. persist population manifest;
3. compute population hash;
4. validate deterministic IDs;
5. validate duplicates;
6. validate causal candle access;
7. validate symbol policy;
8. apply frozen sample-adequacy rule.

HARD CIRCUIT BREAKER

If population integrity fails:
STOP_G2_FAIL

If frozen sample rule returns INCONCLUSIVE:
persist result and STOP_STAGE2_INCONCLUSIVE

Do not lower minimum sample requirement.

STEP C — G3/G4 EVALUATION

Only after successful G2 checkpoint:

Evaluate frozen CONTROL vs frozen HYP_002 TREATMENT.

Apply exactly frozen:

* primary metric
* costs/friction
* decision thresholds
* exclusions
* stopping rule

Calculate relevant diagnostics including:

N
accepted/rejected
wins/losses/BE
gross expectancy R
net expectancy R
total net R
profit factor
max drawdown R
MFE/MAE where supported
S1/S2/S3
long/short
opportunity retention
control-treatment delta

Do NOT search thresholds or retune.

Persist immutable economic-result artifact/hash.

Apply PASS/FAIL/INCONCLUSIVE mechanically.

STEP D — STATE

Update CURRENT_VALIDATION_STATE.json with pointers/hashes only.

If PASS:
active_stage = STAGE_2
active_gate = STAGE_2_AUDIT

If FAIL/INCONCLUSIVE:
record terminal experiment status.
Do not continue.

SAFETY

No holdout.
No GBPUSD tuning.
No parent modification.
No execution changes.

TESTS

Focused deterministic population/economic tests only.

OUTPUT ONLY

AG_SSC_STAGE2_STATUS

IDENTITY
dataset_hash =
preregistration_hash =
parent_hash =

G2
population_id =
count =
population_hash =
sample_adequate =
duplicates =
causality_pass =
lookahead_detected =

CONTROL
n =
net_expectancy_R =
profit_factor =
max_drawdown_R =

HYP002
n =
net_expectancy_R =
profit_factor =
max_drawdown_R =

COMPARISON
delta_net_expectancy_R =
opportunity_retention =
primary_metric_result =
hypothesis_status =

ARTIFACTS
population =
economic_result =
economic_result_hash =

SAFETY
rules_changed =
optimization_performed =
holdout_accessed =
parent_changed =

FINAL_VERDICT =
NEXT_SINGLE_ACTION =

PASS → INDEPENDENT_STAGE2_AUDIT
FAIL/INCONCLUSIVE → STOP

## DeepSeek — Stage 2 combined audit

DeepSeek can audit G2 and G4 in one pass because the immutable population checkpoint now exists.

AG SSC VERIFICATION V2 — STAGE 2 INDEPENDENT AUDIT

ROLE
READ-ONLY gatekeeper.

START

Read CURRENT_VALIDATION_STATE.json.
Follow population/economic manifests and relevant Git diff only.

MISSION

Audit G2 population integrity AND G3/G4 economic result in one review.

VERIFY G2

dataset hash
preregistration hash
parent hash
population hash
deterministic IDs
duplicates
causality
lookahead
EURUSD-only policy
sample rule
population frozen before economic evaluation

VERIFY G3/G4

control definition
treatment definition
cost/friction application
primary metric
trade/outcome calculations
sample adequacy
PASS/FAIL/INCONCLUSIVE decision
no threshold search
no post-result tuning
no holdout access

Recompute critical metrics where practical.

Do not modify files.

OUTPUT ONLY

AG_SSC_STAGE2_INDEPENDENT_AUDIT

G2_HASH_VALID =
G2_DETERMINISTIC =
G2_CAUSAL =
LOOKAHEAD =
SAMPLE_RULE_RESPECTED =
POPULATION_PRECEDES_EVALUATION =

CONTROL_REPRODUCED =
TREATMENT_REPRODUCED =
FRICTION_VALID =
PRIMARY_METRIC_REPRODUCED =
RESULT_REPRODUCED =

CLAIMED_STATUS =
VERIFIED_STATUS =

BLOCKERS =
NON_BLOCKING =

FINAL_VERDICT =
PERMIT_STAGE_3 = true/false
NEXT_SINGLE_ACTION =

PASS → RUN_STRESS_AND_FREEZE_CANDIDATE

---

# STAGE 3 — Robustness + Candidate Freeze

Your proposed collapse is appropriate here.

Run:

```text
Frozen HYP002
    ↓
robustness suite
    ↓
HARD CHECKPOINT
    ↓
PASS?
 ├─ NO → stop
 └─ YES
      ↓
candidate freeze
```

Do not freeze a candidate first and then discover robustness failure.

The robustness suite should not become another optimization loop.

## Claude — Stage 3

AG SSC VERIFICATION V2 — STAGE 3
G5 ROBUSTNESS + G6 CANDIDATE FREEZE

PRECONDITION
Stage-2 independent audit PASS.

START
Read CURRENT_VALIDATION_STATE.json and referenced immutable evidence only.

STEP A — G5

Run ONLY preregistered/governance-authorized robustness tests.

Where authorized, evaluate:

* higher friction/slippage
* execution delay
* temporal stability
* regime stability
* S1/S2/S3 stability
* direction stability
* outlier sensitivity
* parameter-neighborhood stability

This is stress testing, NOT parameter selection.

Persist robustness artifact/hash.

HARD BREAK

If robustness FAIL:
STOP_G5_FAIL

If decision rule cannot be applied without inventing a post-result threshold:
STOP_OWNER_DECISION_REQUIRED

STEP B — G6

Only after G5 PASS:

Freeze immutable candidate identity including:

strategy/version/hash
parent lineage
hypothesis/preregistration hash
dataset fingerprint
population hash
economic-result hash
robustness hash
cost-model hash
parameter/config hash
symbol policy

Candidate freeze MUST NOT modify strategy semantics.

Persist candidate specification + manifest + candidate hash.

STEP C — STATE

Update index with robustness and candidate pointers/hashes.

Set:
active_stage = STAGE_3
active_gate = STAGE_3_AUDIT

Do not access holdout.

OUTPUT ONLY

AG_SSC_STAGE3_STATUS

ROBUSTNESS
artifact =
hash =
tests =
status =

CANDIDATE
candidate_id =
spec =
manifest =
candidate_hash =
reproducible =

SAFETY
optimization_performed =
rules_changed =
holdout_accessed =
execution_authority_changed =

FINAL_VERDICT =
NEXT_SINGLE_ACTION =

PASS → INDEPENDENT_STAGE3_AUDIT

DeepSeek can audit both in one mission: reproduce critical robustness evidence and verify the candidate's complete hash lineage.

---

# Optional replication checkpoint — GBPUSD

I would keep this **optional**, not automatically insert it into the critical path.

If the purpose is fastest EURUSD strategy readiness:

```text
do not block EURUSD candidate
on GBPUSD portability
```

If you want stronger generalization evidence, run:

```text
Frozen candidate
     ↓
GBPUSD
NO RETUNING
     ↓
REPLICATION_SUPPORTED
or
REPLICATION_NOT_SUPPORTED
```

Do not combine GBPUSD's result with EURUSD's primary development metric.

---

# STAGE 4 — Holdout → Parity → Canonical Economic Gate

This is where I modify the proposed plan most.

One Claude mission is fine.

One uninterrupted calculation is not.

Use three internal checkpoints:

```text
G7 HOLDOUT
     ↓
WRITE/HASH
     ↓
PASS?
     │
     ▼
G8 SEMANTIC PARITY
     ↓
WRITE/HASH
     ↓
PASS?
     │
     ▼
G9 CANONICAL ECONOMIC GATE
```

This preserves scientific boundaries while avoiding three separate Claude sessions.

## Claude — Stage 4

AG SSC VERIFICATION V2 — STAGE 4
G7 HOLDOUT → G8 PARITY → G9 CANONICAL ECONOMIC GATE

PRECONDITION
Stage-3 independent audit PASS.
Frozen candidate exists.

START

Read CURRENT_VALIDATION_STATE.json and candidate manifest.

Verify candidate hash before any operation.

=========================
CHECKPOINT A — G7 HOLDOUT
=========================

Verify:

holdout_run_count = 0

Select/identify holdout ONLY according to the frozen holdout-selection procedure.

Freeze holdout identity/fingerprint BEFORE outcomes.

If:

* holdout already consumed
* candidate changed
* selection procedure ambiguous
* decision rule missing

STOP BEFORE RUN.

Execute candidate against holdout exactly ONCE.

Persist immutable holdout result/hash.

Atomically transition:

holdout_run_count: 0 → 1

Apply frozen PASS/FAIL rule.

If FAIL:
STOP_G7_FAIL

Never rerun same holdout after candidate modification.

=========================
CHECKPOINT B — G8 PARITY
========================

Only after G7 PASS:

Compare validated research candidate with canonical AG implementation on designated parity evidence.

Compare at minimum:

occurrence identity
S1/S2/S3
direction
signal/entry timestamps
entry geometry
SL
TP
rejection reasons
session boundaries
market-state inputs
economic inputs

Persist mismatch artifact/hash.

Any unexplained economically meaningful mismatch:
STOP_G8_FAIL

Do not silently patch canonical implementation to make parity pass.

=========================
CHECKPOINT C — G9 ECONOMIC
==========================

Only after G8 PASS:

Run canonical AG economic gate using existing canonical infrastructure.

Include canonical:

spread
commission
slippage
precision
volume/lot rounding where applicable
stop constraints
session timing
execution-delay assumptions

Apply frozen canonical economic rule.

Persist G9 artifact/hash.

No optimization.

=========================
STATE
=====

Update state index after EACH successful checkpoint, not only at end.

State file remains an index.

Immutable G7/G8/G9 artifacts are authoritative.

SAFETY

demo_authorized = false
live_authorized = false
execution authority unchanged

OUTPUT ONLY

AG_SSC_STAGE4_STATUS

CANDIDATE
hash =

G7
holdout_id =
holdout_hash =
run_count_before =
run_count_after =
decision =
artifact_hash =

G8
cases =
matches =
mismatches =
meaningful_mismatches =
parity_status =
artifact_hash =

G9
n =
net_expectancy_R =
profit_factor =
max_drawdown_R =
economic_gate =
artifact_hash =

SAFETY
candidate_changed =
optimization_performed =
execution_authority_changed =
demo_authorized =
live_authorized =

FINAL_VERDICT =
NEXT_SINGLE_ACTION =

ALL PASS → INDEPENDENT_STAGE4_AUDIT

Otherwise STOP at first failed checkpoint.

## DeepSeek — Stage 4 audit

DeepSeek should now inspect the complete chain but especially G7.

AG SSC VERIFICATION V2 — STAGE 4 INDEPENDENT AUDIT

ROLE
READ-ONLY independent gatekeeper.

START

Read CURRENT_VALIDATION_STATE.json.
Follow candidate/G7/G8/G9 immutable manifests.

Do not broadly re-index repository unless evidence conflicts.

VERIFY G7

candidate hash unchanged
holdout selection followed frozen procedure
holdout fingerprint frozen pre-outcome
run_count 0 → 1 exactly
no previous consumption
result reproducible
decision rule correctly applied
no post-result candidate change

VERIFY G8

research/canonical identities correct
parity calculations valid
all economically meaningful fields compared
mismatches accurately reported
no silent repair/change to candidate

VERIFY G9

canonical implementation used
canonical friction used
economic calculations reproducible
economic acceptance rule correctly applied
no optimization

VERIFY SAFETY

execution authority unchanged
demo_authorized=false
live_authorized=false

OUTPUT ONLY

AG_SSC_STAGE4_INDEPENDENT_AUDIT

CANDIDATE_CHAIN_VALID =

G7
HOLDOUT_FRESH =
RUN_TRANSITION_VALID =
RESULT_REPRODUCED =
DECISION_VALID =

G8
PARITY_REPRODUCED =
MEANINGFUL_MISMATCHES =

G9
ECONOMIC_RESULT_REPRODUCED =
ECONOMIC_GATE_VALID =

POST_HOLDOUT_MODIFICATION =
EXECUTION_AUTHORITY_CHANGED =

BLOCKERS =
NON_BLOCKING =

FINAL_VERDICT =
PERMIT_STAGE_5 = true/false
NEXT_SINGLE_ACTION =

PASS → FINAL_READINESS_AUDIT

---

# STAGE 5 — Final readiness package

I recommend **DeepSeek own the actual final eligibility judgment**, because Claude created most of the evidence.

Claude only assembles an index/package.

DeepSeek judges it.

```text
Claude
   ↓
assemble evidence index
NO reinterpretation
   ↓
DeepSeek
   ↓
independent chain verification
   ↓
DEMO_ELIGIBLE
or
NOT_DEMO_ELIGIBLE
```

## Claude — Stage 5 assembly

AG SSC VERIFICATION V2 — STAGE 5
FINAL EVIDENCE PACKAGE ASSEMBLY

ROLE
Evidence assembler only.

MISSION

Assemble a compact final readiness manifest referencing existing immutable evidence.

Do NOT rerun experiments.
Do NOT reinterpret failed gates.
Do NOT modify candidate.
Do NOT change authorization.

Reference:

G1 preregistration
G1 audit
G2 population
G3/G4 economic result
Stage-2 audit
G5 robustness
G6 candidate
Stage-3 audit
G7 holdout
G8 parity
G9 economic gate
Stage-4 audit

Include all authoritative hashes and paths.

Verify the candidate hash remains identical through G6→G9.

Persist final evidence-chain manifest/hash.

Update CURRENT_VALIDATION_STATE.json:

active_stage = STAGE_5
active_gate = FINAL_INDEPENDENT_AUDIT

Do NOT set demo_eligible=true yourself unless repository governance explicitly assigns that judgment to the implementation agent.

Keep:

demo_authorized=false
live_authorized=false

OUTPUT ONLY

AG_SSC_STAGE5_ASSEMBLY_STATUS

EVIDENCE_CHAIN =
CHAIN_HASH =
CANDIDATE_HASH =
MISSING_ARTIFACTS =
HASH_CONFLICTS =
HOLDOUT_RUN_COUNT =
EXECUTION_AUTHORITY_CHANGED =

FINAL_VERDICT =
NEXT_SINGLE_ACTION = FINAL_INDEPENDENT_READINESS_AUDIT

## DeepSeek — Final audit

AG SSC VERIFICATION V2 — FINAL INDEPENDENT READINESS AUDIT

ROLE
READ-ONLY final gatekeeper.

MISSION

Determine whether the frozen ST_SESSION_SWEEP_CONTINUATION_V1 HYP_002 candidate is DEMO_ELIGIBLE.

Start from:

CURRENT_VALIDATION_STATE.json
+
final evidence-chain manifest.

Follow referenced immutable artifacts only.

Verify complete chain:

GEN_002 admission PASS
→ G1 preregistration PASS
→ G1 independent audit PASS
→ G2 population PASS
→ G3/G4 economic PASS
→ Stage-2 audit PASS
→ G5 robustness PASS
→ G6 candidate freeze PASS
→ Stage-3 audit PASS
→ G7 untouched holdout PASS
→ G8 semantic parity PASS
→ G9 canonical economic gate PASS
→ Stage-4 audit PASS

Verify SAME candidate identity throughout.

Verify:

* hash chain complete
* no missing authority artifact
* holdout_run_count = 1
* no post-holdout candidate modification
* no hidden rerun
* no optimization after holdout
* no unexplained parity mismatch
* canonical economic edge passes frozen rule
* execution authority unchanged
* demo_authorized=false
* live_authorized=false

IMPORTANT

DEMO_ELIGIBLE is evidence status only.

Do NOT set:
demo_authorized=true

Do NOT set:
live_authorized=true

OUTPUT ONLY

AG_SSC_FINAL_READINESS

STRATEGY =
CANDIDATE =
CANDIDATE_HASH =

DATA_ADMISSION =
G1 =
G2 =
G3_G4 =
G5 =
G6 =
G7 =
G8 =
G9 =

HASH_CHAIN =
HOLDOUT_RUN_COUNT =
POST_HOLDOUT_MODIFICATION =
PARITY_STATUS =
CANONICAL_ECONOMIC_STATUS =

BLOCKERS =

DEMO_ELIGIBLE = true/false
DEMO_AUTHORIZED = false
LIVE_AUTHORIZED = false

FINAL_VERDICT =
NEXT_SINGLE_ACTION =

If all evidence passes:

FINAL_VERDICT = DEMO_ELIGIBLE
NEXT_SINGLE_ACTION = OWNER_REVIEW_FOR_FORWARD_DEMO_AUTHORIZATION

Do not modify repository.
Do not rerun experiments.

# Optimized stop conditions

The pipeline should stop as early as possible.

| Stage    | Continue only when                   | Stop when                      |
| -------- | ------------------------------------ | ------------------------------ |
| **1**    | Preregistration independently passes | Leakage/ambiguity              |
| **2/G2** | Population valid + adequate          | Invalid or inadequate sample   |
| **2/G4** | HYP_002 passes frozen economic rule  | FAIL/INCONCLUSIVE              |
| **3/G5** | Robustness passes                    | Edge fragile                   |
| **3/G6** | Candidate reproducibly frozen        | Hash/lineage problem           |
| **4/G7** | Untouched holdout passes             | Holdout FAIL                   |
| **4/G8** | Semantic parity passes               | Meaningful mismatch            |
| **4/G9** | Canonical economics passes           | Edge disappears after friction |
| **5**    | Complete evidence chain              | Any unresolved blocker         |

This is where most of the speed gain comes from: **failed hypotheses don't consume downstream verification work.**

# Token reduction protocol

Put this at the bottom of every agent mission:

```text
CONTEXT / TOKEN POLICY

CURRENT_VALIDATION_STATE.json is the navigation index.
Immutable referenced manifests are authoritative.

Do not:
- rediscover completed gates
- restate project history
- broadly scan repo without evidence-driven need
- rerun upstream PASS tests
- rerun GEN_002 admission
- run full suite by default
- propose unrelated architecture
- fix outside mission scope

Use:
1. state index
2. referenced manifests
3. narrow Git diff
4. targeted source inspection only if required
5. focused tests

If index and immutable evidence disagree:
STOP_STATE_CONFLICT

Return only the required status contract.
Stop at the first circuit breaker.
```

There is one refinement to the proposal's “DeepSeek only reads JSON manifests and Git diffs”: **don't prohibit source inspection absolutely.** If DeepSeek needs to establish that the actual setup detector is causal or that canonical parity uses the correct implementation, it should be allowed to inspect the small relevant source path. Otherwise an incorrect implementation could produce perfectly consistent JSON.

## Updated execution schedule

You have reduced approximately twelve agent handoffs to this:

```text
STAGE 1
Claude → G1 freeze
DeepSeek → G1 audit
             ↓

STAGE 2
Claude → G2 population
         HARD FREEZE
         → G3/G4 evaluation
DeepSeek → combined audit
             ↓

STAGE 3
Claude → G5 robustness
         HARD CHECKPOINT
         → G6 candidate freeze
DeepSeek → combined audit
             ↓

STAGE 4
Claude → G7 holdout
         HARD CHECKPOINT
         → G8 parity
         HARD CHECKPOINT
         → G9 canonical economic gate
DeepSeek → combined audit
             ↓

STAGE 5
Claude → evidence-chain assembly
DeepSeek → final readiness audit
             ↓

       DEMO_ELIGIBLE
             ↓
     OWNER AUTHORIZATION
             ↓
       FORWARD DEMO
```

So the proposed optimization is worth adopting, with one principle preserved throughout:

> **Collapse execution sessions, not validation boundaries.**

For your current state, don't send Stage 2 yet. **Execute the updated Stage-1 Claude prompt first.** If Claude reports `STOP_OWNER_DECISION_REQUIRED`, resolve only that decision. If it reports a clean freeze, send the Stage-1 DeepSeek prompt; only `PERMIT_STAGE_2=true` unlocks the combined population/economic run. This is the shortest defensible path from your already-verified GEN_002 evidence toward `DEMO_ELIGIBLE`.
