# STEP 1 -- branch cleanup runbook (NOT EXECUTED -- blocked, hand-off)

Mission: `AG_ARENA_RESET_A1_R1`, STEP 1 (a/b/c).
Status: **NOT EXECUTED.** Every operation below has been **dry-run verified** to apply
cleanly. None was committed, pushed, or branched in the real repository.

## Why it was not executed

Two blockers, one environmental and one internal to the mission brief.

### Blocker 1 -- this session is pinned to one branch

This Arena session is bound to `arena/cc31c23d-ag-profit-trading-assit`. The session may
only commit and push to that branch; it cannot create, switch to, or push to
`arena/crypto-logic-verify-r1`, `arena/reference-actionability-impl`, or
`arena/d1cea83b-ag-profit-trading-assit`. Work pushed to any other branch is not tracked
against the session. STEP 1 requires four branches, three of which are out of reach.

### Blocker 2 -- STEP 1a contradicts the mission's own hard rule

- STEP 1a: *"On PR #46's branch: `git revert ccb9db3` and `a630a41`"* -- this requires a
  push to PR #46's branch.
- HARD RULES: *"Never push to PR #46 again."*

These cannot both hold. Not resolved here; see Decision 1 below.

### Finding -- STEP 1a as written does not achieve its stated goal

STEP 1a's goal is *"so PR #46 = Candidate Factory R1 only."* Reverting `ccb9db3` and
`a630a41` does **not** achieve that. PR #46 carries **12** commits. Removing those two
leaves **10**, of which only `9bb5560` is Candidate Factory R1:

| Commit | Subject | Covered by STEP 1a? |
|---|---|---|
| `9bb5560` | AG_OSS_STRATEGY_CANDIDATE_FACTORY_R1 (**the keeper**) | n/a |
| `9d83e68` | T1: AG readiness facts snapshot (R3) | **no** |
| `fb8dd5e` | T2: three-target readiness matrix (R3) | **no** |
| `899ffe0` | T3: Asian Sweep v1.1.1->v1.2.0 cutover readiness (R3) | **no** |
| `82a207d` | T4: crypto CFD readiness unblock chain (R3) | **no** |
| `12953a9` | T5: ST_MTF_CONTROL_SHIFT_V1 sample adequacy (R3) | **no** |
| `5ce32b8` | T6: Large-SMC logic-verification lane plan (R3) | **no** |
| `79507e6` | T7: owner decision packets (R3) | **no** |
| `d50913d` | T8: ranked next-mission queue (R3) | **no** |
| `c4c9b1b` | AG_INT_MTF_CONTROL_SHIFT_V1_LONGER_DEV_SAMPLE_R1 | **no** |
| `ccb9db3` | AG_CRYPTO_LOGIC_VERIFY_R1 | yes -- revert |
| `a630a41` | AG_V1_HOST_HARDENING_R1 | yes -- revert |

Dry-run confirmation: after both reverts the tree still differs from `9bb5560` by
**29 files / +12,498 lines** -- the nine R3/diagnostic commits above. Not reverted here,
because the brief did not authorize it. See Decision 2.

## Dry-run verification

Performed in a throwaway clone outside the repository. No ref in this repository was
created or modified.

| Step | Operation | Result |
|---|---|---|
| 1a | `git revert a630a41` on PR #46 head | **CLEAN** |
| 1a | `git revert ccb9db3` on PR #46 head | **CLEAN** |
| 1b | `git cherry-pick ccb9db3` onto `origin/main` | **CLEAN** (31 files, +1,936) |
| 1c | `git cherry-pick a630a41` onto `origin/main` | **CLEAN** |

No conflicts anywhere. The commands below are safe to run as written.

---

## Decisions required before execution

| # | Decision |
|---|---|
| 1 | STEP 1a vs "never push to PR #46 again": authorize exactly one final push to PR #46 carrying only the two reverts, **or** close PR #46 and re-open Candidate Factory R1 on a fresh branch. |
| 2 | Scope: revert only the two named commits (PR #46 keeps the nine R3/diagnostic commits), **or** reduce PR #46 to `9bb5560` alone (needs nine further reverts, listed above). |
| 3 | Base branch for 1b and 1c. The runbook below uses `origin/main`, which is verified clean. If `arena/reference-actionability-impl` is meant to sit on PR #49's branch instead, say so -- that base was not dry-run. |

---

## Commands (verified, not run)

### 1a -- revert on PR #46's branch

Reverts newest-first so each revert applies against the tree that produced it. No
force-push; both are additive commits.

```bash
git fetch origin
git checkout -B arena/d1cea83b-ag-profit-trading-assit origin/arena/d1cea83b-ag-profit-trading-assit

git revert --no-edit a630a41   # AG_V1_HOST_HARDENING_R1  (superseded by PR #49)
git revert --no-edit ccb9db3   # AG_CRYPTO_LOGIC_VERIFY_R1 (moves to its own PR, 1b)

git push origin arena/d1cea83b-ag-profit-trading-assit   # final push to PR #46
```

### 1b -- crypto logic verify on its own branch, new draft PR

```bash
git checkout -B arena/crypto-logic-verify-r1 origin/main
git cherry-pick ccb9db3
git push -u origin arena/crypto-logic-verify-r1

gh pr create --draft \
  --base main --head arena/crypto-logic-verify-r1 \
  --title "AG_CRYPTO_LOGIC_VERIFY_R1: crypto candidate logic-verification prep (T1-T5)" \
  --body "Moved off PR #46 by AG_ARENA_RESET_A1_R1 STEP 1b. Cherry-pick of ccb9db3, no content change.

Draft. Do not merge. No strategy registry change, no demo/live authority change, no broker activity.

Known upstream gaps carried over unchanged: the VT Markets BTCUSD/ETHUSD data pack does not exist (HOST_DATA_NOT_VERIFIED, fixtures only), and R4B was not run."
```

### 1c -- reference-only branch, NO PR

```bash
git checkout -B arena/reference-actionability-impl origin/main
git cherry-pick a630a41
git push -u origin arena/reference-actionability-impl
# Deliberately no `gh pr create`. Reference only. Never merged.
```

Record alongside it: `a630a41` was built against the **superseded 54-line** governance
record (`ce1b0d48...`), not the canonical 94-line `67bb1a57...eb7b56`, and pinned no input
hash -- see `STEP0_GOVERNANCE_PROVENANCE.md`. It is superseded by PR #49. Keep it
reference-only.

## Post-execution checks

```bash
git log --oneline origin/main..origin/arena/d1cea83b-ag-profit-trading-assit   # 2 revert commits on top
gh pr view 46 --json state,isDraft
gh pr list --state open --head arena/crypto-logic-verify-r1                    # exactly one draft PR
gh pr list --state all  --head arena/reference-actionability-impl              # MUST be empty
```
