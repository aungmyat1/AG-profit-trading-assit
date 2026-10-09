# STEP 0 -- governance-doc provenance for commit `a630a41`

Mission: `AG_ARENA_RESET_A1_R1`. Question asked: *which governance-doc SHA-256 did the
previous run build against in `a630a41`?*

## Answer

**`a630a41` was NOT built against the canonical 94-line record.**

It was built against the **54-line** version of
`docs/governance/OWNER_DECISIONS_2026-10-07_LSMC_ACTIONABILITY_V1.md` that lives on PR
**#48**'s branch (`audit/v1-followup-2026-10-07`) at commit `00caa9c`.

| | Version used by `a630a41` | Canonical |
|---|---|---|
| Commit | `00caa9c` | `f4ec100` |
| Branch | `audit/v1-followup-2026-10-07` (PR #48) | `feat/ag-v1-host-hardening-r1` (PR #49) |
| Lines | **54** | **94** |
| SHA-256 | `ce1b0d48338f2c48ff0d22e1e1fdfbedda6acde7842bde4beda67e9ce3fff626` | `67bb1a57a7bc38335fdb18d7bdf7880c39331247a44abbc473e35cf1eecb7b56` |
| Matches the canonical named in the mission? | **NO** | yes (`67bb1a57...eb7b56`) |

## Second, separate finding: no hash was pinned at all

`a630a41` **never recorded a SHA-256 for the governance record**. It identified its
authority by branch and prose only. Its spec header states:

> Source of authority: `docs/governance/OWNER_DECISIONS_2026-10-07_LSMC_ACTIONABILITY_V1.md`
> (PR #48, signed 2026-10-07, status SIGNED) decisions D1, D2, D3, D4, D7. That file lives
> only on PR #48's branch (`audit/v1-followup-2026-10-07`), which is open/unmerged as of
> this writing -- this mission's own branch does not carry it, so it is cited here by
> content (fetched and read directly from that branch), not reproduced in this repo tree.

So the provenance was unverifiable by hash at the time it was written. The only SHA-256
`a630a41` emitted was for **its own output**, not its input:

```
cb6649bd61cf6364161f7400da359959ef0ec14216aba96d7986ba2211753fb4  docs/specs/LSMC_ACTIONABILITY_POLICY_V1_SPEC.md
```

Confirmed by inspection: `git ls-tree -r a630a41` contains **no**
`docs/governance/OWNER_DECISIONS_2026-10-07_LSMC_ACTIONABILITY_V1.md`. The governance
record was not vendored into the tree it was built in.

## Third finding: the 54-line version is materially thinner

The canonical 94-line record adds a **"Canonical names"** block that the 54-line version
does not contain. Among the fields it introduces:

```
- Price fields: reference_price, send_price, plus send_price_side
  (state which of bid/ask/mid is used)
```

`send_price_side` -- the side-correctness concept that A1 depends on -- **exists only in
the canonical 94-line record**. A build against the 54-line version had no instruction to
record a price side at all. The decisions D1-D8 themselves agree in substance between the
two versions; the 94-line version is a fuller, renamed, canonicalized restatement.

## Status of the conflict

PR #49's own status document already flags this as unresolved:

> Two different signed versions of the decision record exist: `00caa9c` on PR #48
> (54 lines) and `f4ec100` here (94 lines, includes "Canonical names"). Owner to choose;
> branches conflict on that file.

That remains open. It is an owner decision and is not resolved by this mission.

## Reproduction

```bash
F=docs/governance/OWNER_DECISIONS_2026-10-07_LSMC_ACTIONABILITY_V1.md
git show 00caa9c:$F | wc -l && git show 00caa9c:$F | sha256sum   # 54, ce1b0d48...
git show f4ec100:$F | wc -l && git show f4ec100:$F | sha256sum   # 94, 67bb1a57...
git ls-tree -r a630a41 -- $F                                     # (no output: absent)
git show a630a41:docs/specs/LSMC_ACTIONABILITY_POLICY_V1_SPEC.sha256.txt
```

## Bearing on this run

`a630a41` is being removed from PR #46 and retained as reference-only (STEP 1c). This
provenance gap is one reason that is the right call: the work was built against a
superseded, unhashed input and was in any case superseded by PR #49.

The A1 spec (`docs/specs/LSMC_SPEC_V1_FROZEN.md`) cites the **canonical 94-line record,
`67bb1a57...eb7b56`**, and cites it only to fix the scope boundary in section 0.2 -- no
delivery rule from it is restated.
