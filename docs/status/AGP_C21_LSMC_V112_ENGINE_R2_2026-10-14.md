---
class: status_evidence
state: NOT_VERIFIED
owner_reviewed: null
---
# C21 Large-SMC 1.1.2 engine R2 — 2026-10-14

Off-host Linux/Python 3.12, committed data only. Base main
`5e686f376b7be06c0372fdadde3c9c6617ef58af` includes PR #200 and report-interface follow-ups.
Proposal-only PR #202 merged before the code push; implementation is on
`feat/lsmc-v112-engine-r2`, draft PR #209.
[Registration proposal](../proposals/C21_LSMC_V112_REGISTRATION.md) contains identity, scope,
D2 convention, declared 74-path diff, R1 replay and unchanged registry proposal.

- Candidate replay: completed R1 / one worker, 18 cases + 575 EURUSD rolling scans + 120 recorded
  full-D1 scans per crypto symbol, zero lane failures. All scopes NOT_VERIFIED; L5 WARN.
- Frozen engine/contract/dependencies/registry/scheduler: re-hashed unchanged.
- Initial full default 1.1.0 audit JSON (historical artifact in commit `d480c23`): 110,526 bytes identical before/after at base code identity;
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

## PR #209 owner-decision continuation (2026-10-14)

Merged current main `e884b8605739b64d229f848c99ed4a23d8b4ae45` with no conflicts. Main's
D4/D5 registry change is retained; this mission has no registry diff against that base.
D6 confirms `rules.reward_risk.minimum_rr: 2.0`, status CONFIRMED and owner provenance
OD1014-FAST D6, 2026-10-14. Exact declared rule diff expands to 77 paths.
D7 selects `strategy_version: '1.1.2'` only in the REPORT_ONLY lane; NOT_VERIFIED remains.
Missing file/key, malformed YAML, null and unknown version are BLOCKED with
`LSMC_REPORT_VERSION_NOT_EVIDENCED`; neither engine is evaluated as fallback.
Continuation: 46 candidate regressions PASS; bounded R1 replay has zero lane failures, exact
77-path declared diff, six priced scopes and L1–L4/L6 PASS, L5 WARN (NOT_VERIFIED).
Current-main/candidate default 1.1.0 audit outputs are 110,526 bytes identical at the same
explicit current-main provenance; SHA-256 `c21e5201163e0c2103753e59fafb733b1d3a2fc5471bd2623d69d89d33ed147a`.
Host/candidate focused suite: `python -m pytest -q tests/test_od1014_opportunity_lanes.py
tests/test_lsmc_v112_engine.py` — 102 passed in 8.23 s (R1, one worker).
Initial continuation full suite: 1 failed, 2920 passed, 6 skipped in 464.37 s. The old host-wiring
test mocked the frozen report adapter; fixed to intercept the selected-version adapter, with
missing/unknown configuration no-event host-path regressions added.
CI-style documentation regeneration in a separate worktree: generated-file policy PASS
(0 failures), authority drift PASS (0 blocking errors). Generated outputs remain deferred under
the source-PR regeneration policy. Changed-Python lint, links and skill mirrors PASS.
Final full suite: `python -m pytest -q` — **2924 passed, 5 skipped**, 550.18 s,
R2 / one worker; lock released. This supersedes the earlier continuation failure.
The validation worktree head is merge commit `932f34dc7be1ce930f339776ea97f70c1703c5fc`;
artifact engine/spec hashes bind the staged continuation source. PR #209 remains draft
until remote CI on the final pushed head is green.
Full 60-day replay, broker/host/demo/live acceptance: NOT_RUN, separate mission.
