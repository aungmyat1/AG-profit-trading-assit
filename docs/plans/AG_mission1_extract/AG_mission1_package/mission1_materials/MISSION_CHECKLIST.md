# MISSION 1 CHECKLIST — SSC ONE-YEAR REPLAY DATA AUTHORITY + WARMUP READINESS

Copy this file into the working branch and fill every `< >` field during execution.
Do not advance a phase until the previous phase's boxes are all checked.

## P0 — Preflight
- [ ] AGENTS.md read
- [ ] branch: `< >` · HEAD_BEFORE: `< >`
- [ ] `git status` recorded: `< >`
- [ ] concurrent-writer state: `< >`
- [ ] environment: Windows/MT5 dev box | Linux (portability patch present: YES/NO)
- [ ] authoritative status docs identified (SSC_V1_0_1_ONE_YEAR_HISTORICAL_{BACKTEST,REPLAY}_STATUS.md, AG_VALIDATION_SYSTEM_ASSURANCE_V1.md)

## P1 — DEV002 remediation
- [ ] hashes recomputed from bytes (values/DEV002_VERIFIED_VALUES.md re-verified)
- [ ] remediation still required at current HEAD? YES → apply `patches/P1_dev002_remediation.patch` (verify it applies cleanly; if HEAD moved, reconcile by hand against the same intent)
- [ ] `templates/DEV002_H1_MANIFEST_REMEDIATION_V1.json` filled and committed to `artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/V1_0_1_REMEDIATION/`
- [ ] runtime references dispositioned: `scripts/run_ssc_v1_0_1_g2_dev002_population.py` = `<UPDATED|COMMENT_ONLY>`, `src/data_archive/lineage_audit.py` = `<UPDATED|COMMENT_ONLY>`
- [ ] immutable records untouched (blocker, preregistration, registry, coverage audit)
- [ ] focused: `pytest -q tests/test_ssc_dev002_h1_metadata_manifest.py` → 3 PASS

## P1.5 — Governance test reconciliation
- [ ] apply `patches/P1_5_governance_test_fix.patch` (constructs the unsigned-contract scenario explicitly; adds signed-gate no-bypass assertion)
- [ ] `pytest -q tests/test_external_candidate_governance_invariance.py` → PASS (both tests)

## P2 — One-year replay stack
- [ ] M1/M15/H1/warmup identities verified FROM BYTES (never from this checklist)
- [ ] warmup context packaged as WARMUP_CONTEXT_ONLY (candidate: EXTERNAL_D_ROOT H1 2025-01-02→2026-07-31, +0h DST-consistent)
- [ ] `scripts/build_ssc_v1_0_1_one_year_replay_stack.py` created from `code/` draft, `--check` exits 0
- [ ] GEN_002 absent from all legs; DEV_002 absent from all legs

## P3 — Cross-leg timebase gate
- [ ] `code/cross_leg_timebase_arbiter.py` placed (suggested: `src/historical_replay/timebase_arbiter.py`)
- [ ] `tests/test_cross_leg_timebase_gate.py` → 6 PASS
- [ ] arbiter wired into `scripts/audit_ssc_v1_0_1_one_year_data_coverage.py` (extend, never compete)
- [ ] gate asserts: best_shift=+0h ∧ DST CONSISTENT ∧ cross-timeframe parity 1.0 (same-source parity rejected by API shape)

## P4 — Warmup convergence
- [ ] `code/test_warmup_convergence_gate.py` finalized (decision enumeration + stack manifest binding)
- [ ] classification achieved: WARMUP_STABLE (else STOP: INSUFFICIENT/UNSTABLE are blocking verdicts)
- [ ] per-decision closed-bar counts ≥ 1,000 recorded

## P5 — GEN_002 quarantine
- [ ] internal inconsistency re-verified at current HEAD
- [ ] `templates/GEN_002_QUARANTINE_RECORD_V1.json` filled, committed alongside the package
- [ ] admission gate fails closed on GEN_002 as a stack input

## P6 — Protected-data firewall
- [ ] CONFIRM_001 access_count = `< >` (must be 0)
- [ ] HOLDOUT access_count = `< >` (must be 0)
- [ ] OOS access_count = `< >` (must be 0; SSC1D_WP1_OOS_EURUSD_2024Q1 historically 0)

## P7 — Verification
- [ ] focused set green: manifest ×3, governance ×2, arbiter ×6, warmup ×3
- [ ] fingerprint-chain status on this machine: composer_replay/td8e = `< PASS on Windows | residual runtime-MT5 category on Linux — dispositioned per WP0.2 >`
- [ ] broad suite: `< exact command + result >` — unrelated failures NOT repaired for greenness
- [ ] known out-of-scope failures recorded, not fixed: `< list >`

## P8 — Freeze
- [ ] all P2–P6 gates PASS
- [ ] `ONE_YEAR_REPLAY_STACK_V1.json` written with status FROZEN + manifest_sha256 `< >`
- [ ] dated status doc written + docs/README.md index updated
- [ ] PROJECT_STATUS.md dated delta per LIVE_STATUS_MAINTENANCE.md
- [ ] R5/R6 NOT created or executed in this mission

## Final classification (exactly one)
```
ONE_YEAR_REPLAY_DATA_AUTHORITY_READY
```
or
```
BLOCKED_ONE_YEAR_REPLAY_DATA_AUTHORITY — first falsified gate: < >
```

### READY report fields
| Field | Value |
|---|---|
| HEAD_BEFORE / HEAD_AFTER / commit | `< >` |
| M1 dataset / hash / rows / range | SSC_V1_0_1_HIST_1Y_M1_001 / `50beb42a…` / 373,421 / 2025-09-14T21:02Z→2026-09-15T21:00Z |
| M15 dataset / hash / rows / range | `< >` |
| H1 dataset / hash / rows / range | DERIVED_001::H1 / `4eb52294…` / 6,241 / `< >` |
| warmup source / hash / bars | `< >` |
| DATA_COVERAGE / TIMEBASE / WARMUP | `< >` |
| protected access counts | 0 / 0 / 0 |
| focused / broad test results | `< >` |
| stale governance test reconciled | YES |
| strategy files changed | NONE |
| economic replay executed | NO |
| Demo/Live authority changed | NO |
