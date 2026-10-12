---
class: status_evidence
state: C16_LOGIC_VERIFICATION_COMPLETE
owner_reviewed: null
review_by: 2026-11-12
---

# C16 → PR #181 repopulation (owner action required, one step)

PR #181 (`codex/c16-blocked-verification-evidence`, head `666035d7…`) currently carries the
**blocked-state** deliverables: a report that says `C16_LOGIC_VERIFICATION_BLOCKED —
BLOCKED_RESOURCE_AUTHORITY`, an empty scope matrix (`scopes: []`, `pass_claims: 0`), a
zero-count reproducibility report, and a defect register whose only entry is
`RESOURCE-AUTHORITY-01`.

Those files stay in git history — they are not rewritten. The repopulated versions live on the
session branch `arena/359b163e-ag-profit-trading-assit` in `docs/status/c16_2026-10-12/`, and
the tree-to-tree patch in this directory applies them on top of the PR #181 tip.

**Why the agent did not push it.** This session is pinned to
`arena/359b163e-ag-profit-trading-assit` and must not push to any other branch. Nothing was
merged, no duplicate evidence PR was created, and no force-push was performed.

## Apply (owner)

```bash
cd <repo>
git fetch origin codex/c16-blocked-verification-evidence
git fetch origin arena/359b163e-ag-profit-trading-assit   # for the patch file
git switch -c c16/pr181-repopulate FETCH_HEAD             # or: git checkout codex/...

# take the patch from the session branch
git show origin/arena/359b163e-ag-profit-trading-assit:docs/status/c16_2026-10-12/C16_PR181_REPOPULATION.patch \
  > /tmp/C16_PR181_REPOPULATION.patch
git apply --check /tmp/C16_PR181_REPOPULATION.patch && git apply /tmp/C16_PR181_REPOPULATION.patch

git add docs/status/c16_2026-10-12
git commit -m "evidence(c16): populate the five C16 deliverables with the completed verification"
git push origin HEAD:codex/c16-blocked-verification-evidence
```

Then update the PR title/description and let CI run. Do not merge automatically.

## What the patch contains

Five files in `docs/status/c16_2026-10-12/`, all generated from committed artifacts by the
scripts recorded in the reproducibility report:

| File | Content |
|---|---|
| `C16_FINAL_VERIFICATION_REPORT.md` | sections A–F, one row per scope, explicit PASS/FAIL/INSUFFICIENT |
| `C16_FINAL_SCOPE_MATRIX.json` | the 24-scope Cartesian matrix with identity, dataset, emissions, L1–L6, verdict, reason, evidence path |
| `C16_REPRODUCIBILITY_REPORT.json` | commands, exit codes, wall-clock, hashes, determinism, skipped reproductions, safety counters, test results |
| `C16_RESOURCE_REPORT.json` | R3 classification and gate, lock provenance, per-lane timing, merged-governance state |
| `C16_DEFECT_REGISTER.md` | `GOVERNANCE-180` + 12 defects + `OBS-CCFD-1` with severity, cause, status |

## Two things to read before applying

1. **The blocked-state verdict was correct at the time and is preserved as history.** The C16
   campaign ran only after resource authority was established; the report explains how.
2. **The blocked-state `C16_RESOURCE_REPORT.json` described a different host** (3 vCPU /
   9,968 MB / `policy_on_main ABSENT`). The repopulated file describes the host that actually
   ran the campaign (2 vCPU / 3,939 MB / authority pinned at PR #180 head, since merged) and
   keeps the historical values only where they are still true.
