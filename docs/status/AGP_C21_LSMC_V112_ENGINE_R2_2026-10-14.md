---
class: status_evidence
state: NOT_VERIFIED
owner_reviewed: null
---
# C21 Large-SMC 1.1.2 engine R2 — 2026-10-14

Off-host Linux/Python 3.12, committed data only. Base main
`5e686f376b7be06c0372fdadde3c9c6617ef58af` includes PR #200 and report-interface follow-ups.
Proposal-only PR #202 merged before the code push; implementation is on
`feat/lsmc-v112-engine-r2`, with a new PR to follow verified results.
[Registration proposal](../proposals/C21_LSMC_V112_REGISTRATION.md) contains identity, scope,
D2 convention, declared 74-path diff, R1 replay and unchanged registry proposal.

- Candidate replay: completed R1 / one worker, 18 cases + 575 EURUSD rolling scans + 120 recorded
  full-D1 scans per crypto symbol, zero lane failures. All scopes NOT_VERIFIED; L5 WARN.
- Frozen engine/contract/dependencies/registry/scheduler: re-hashed unchanged.
- Full default 1.1.0 audit JSON: 110,526 bytes identical before/after at base code identity;
  SHA-256 `36538131735c3a6011b07da0afaebda89511ec83456bd225a5b82cf5b704fc03`.
- Focused regression command: `python -m pytest -q tests/test_lsmc_v112_engine.py
  tests/test_lsmc_v110_logic_audit.py::test_report_doc_cites_the_hashes_of_the_files_it_cites`:
  33 passed (prior to two final artifact-binding regressions, covered by full suite below).
- Pre-rebase suite: `python -m pytest -q`, R2 lock / one worker: **2874 passed, 6 skipped**, 809.87 s.
- Latest-main shared-interface regression suite: **128 passed**. The host-call conflict was resolved
  retaining account/sizing inputs; `lsmc_lane.py` still adds only version selection.
- Full suite on latest main: `python -m pytest -q`, R2 / one worker: **2909 passed, 6 skipped**,
  589.68 s. All **37** candidate regressions pass; real host checks skipped off-host.
- Lint: `python -m ruff check` on changed Python files — PASS.
- Documentation links / skill mirrors: PASS; final documentation check PASS.
- Slow, real host, broker, demo/live acceptance and full 60-day re-execution: NOT_RUN.

No broker contact, READY/registry/scheduler/authorization change or promotion. R1 replay lock released;
latest-main full-suite R2 lock also released successfully. No mission-owned heavy process remains.
