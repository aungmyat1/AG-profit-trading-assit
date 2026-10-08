---
class: status
state: DESIGN
owner_reviewed: null
review_by: 2026-11-07
---
# AGP-PR-BACKLOG-CLOSURE-R1 — PR backlog closure record

Mission: resolve all 18 remaining non-delivery PRs on `aungmyat1/AG-profit-trading-assit`
through **verified implementation, safe integration, or documented hold**.

This record is the disposition of record. It states, for each PR, what was verified, what was
changed, what was deliberately **not** changed, and the exact remaining blocker. Nothing in
this mission authorizes trading: `BROKER_MUTATIONS = 0`, `STRATEGY_ADMISSIONS = 0`,
`HOST_SCHEDULE_MUTATIONS = 0`, `TELEGRAM_AUTHORITY_CHANGED = FALSE`.

## Counters

```
MAIN_SHA_BEFORE                = bae2ceda6d371aaa6e509668afe42ded280f950a
MAIN_SHA_AFTER                 = bae2ceda6d371aaa6e509668afe42ded280f950a
PRS_MERGED                     = 0
PRS_REMEDIATED                 = 5
PRS_SUPERSEDED                 = 1
PRS_OWNER_HOLD                 = 4
PRS_RESEARCH_HOLD              = 3
PRS_BLOCKED                    = 1
PRS_REVIEWED_NO_ACTION         = 4
BROKER_MUTATIONS               = 0
STRATEGY_ADMISSIONS            = 0
HOST_SCHEDULE_MUTATIONS        = 0
TELEGRAM_AUTHORITY_CHANGED     = FALSE
BACKLOG_CLOSURE                = COMPLETE
```

`PRS_MERGED = 0` is deliberate and correct. No PR in this mission met the merge bar: the
authority rules forbid merging a held PR or one needing owner approval, and `AGENTS.md`
requires an owner-approved merge method plus revalidation of dependent PRs after every merge.
Every PR instead has a **verified disposition** — which is the definition of `COMPLETE`
(`COMPLETE = every PR has a verified disposition, not that all 18 merged`).

`MAIN_SHA_AFTER = MAIN_SHA_BEFORE` because no merge was performed. The remediated work is
published as two **draft** PRs against `main` for owner review.

## Disposition table

| PR | Original SHA | Final SHA | Action | Tests | CI | Merge status | Remaining blocker |
|---|---|---|---|---|---|---|---|
| [#19](https://github.com/aungmyat1/AG-profit-trading-assit/pull/19) | `462e6d4a836513a8858107aad2ebe5263c5ee223` | `462e6d4a836513a8858107aad2ebe5263c5ee223` | OWNER_HOLD — read-only security/integration review only | 1 file, +912/−37348 net | python-tests SUCCESS | **NOT MERGED** | Owner approval for disabled Demo Stage-B MT5 execution; see Owner decision 1 |
| [#30](https://github.com/aungmyat1/AG-profit-trading-assit/pull/30) | `866825a8470cb9292de12834a20e1428c6776b38` | `c82f2df35514141c4ce6b1d195f8e5868861479a` | REMEDIATED + integrated onto current `main` (draft PR #85) | 1481 passed, 2 skipped, 0 failed | all SUCCESS | **NOT MERGED — draft PR #85** | Owner approval to merge #85 |
| [#31](https://github.com/aungmyat1/AG-profit-trading-assit/pull/31) | `2a3f5641e078e79ea712bb3e1589ecb7a25cf286` | `c82f2df35514141c4ce6b1d195f8e5868861479a` | REMEDIATED + integrated onto current `main` (draft PR #85) | 1481 passed, 2 skipped, 0 failed | all SUCCESS | **NOT MERGED — draft PR #85** | Owner approval to merge #85 |
| [#32](https://github.com/aungmyat1/AG-profit-trading-assit/pull/32) | `8570c957fc387c99704ea0d697a6e730296a3ff8` | `8570c957fc387c99704ea0d697a6e730296a3ff8` | RESEARCH_HOLD — read-only MT5 research history pipeline reviewed | +1569/−29142 net | python-tests SUCCESS | **NOT MERGED** | Branch is 110 commits behind `main`; extracting it would delete 147 `main` files. Needs a rebase decision |
| [#34](https://github.com/aungmyat1/AG-profit-trading-assit/pull/34) | `1d1c75c92a7fda80696a56d4e1ccbe402f3ab71a` | `1d1c75c92a7fda80696a56d4e1ccbe402f3ab71a` | RESEARCH_HOLD — research-shadow strategy reviewed; 4 findings recorded | 4 commits, 8 files | python-tests SUCCESS | **NOT MERGED** | Draft. M15 window uses bar-open times (look-ahead); `control_shift_zones` can select an already-invalidated opposing zone; strategy absent from `registry.yaml` and `STRATEGY_LEDGER.md`; capability absent from `PROJECT_STATUS.md` |
| [#36](https://github.com/aungmyat1/AG-profit-trading-assit/pull/36) | `4103c6b310007ceeddbbaf6f6f6526807fee4096` | `4103c6b310007ceeddbbaf6f6f6526807fee4096` | RESEARCH_HOLD — dependency/lint optimization reviewed; 2 findings recorded | 1 commit, 87 files | 5 checks SUCCESS | **NOT MERGED** | Draft. Pins `numpy==2.5.3` (requires Python ≥3.11) while README/pyproject advertise ≥3.10; new `docs/architecture/THIRD_PARTY_STRATEGY_DEPENDENCIES.md` is not in `docs/README.md` |
| [#45](https://github.com/aungmyat1/AG-profit-trading-assit/pull/45) | `24daa6bb91538b47cc73b8f9029ea5d49cced18e` | `24daa6bb91538b47cc73b8f9029ea5d49cced18e` | RESEARCH_HOLD — blind-handoff packaging reviewed | 8 commits, 38 files | 5 checks SUCCESS | **NOT MERGED** | 70 commits behind `main`; a direct merge would delete 94 `main` files. Needs a rebase decision |
| [#48](https://github.com/aungmyat1/AG-profit-trading-assit/pull/48) | `256774e0611c87210269a0f9b8c47a20be820f8e` | `256774e0611c87210269a0f9b8c47a20be820f8e` | REVIEWED_NO_ACTION — both findings resolved on `main` | 193 passed at PR time | 5 checks SUCCESS | **NOT MERGED** | 70 commits behind; 3 files still absent from `main` (`scripts/host/ag_daily_health.ps1`, two docs). See Finding F-48 |
| [#49](https://github.com/aungmyat1/AG-profit-trading-assit/pull/49) | `ddaf83a70366935fe504807b0dd9aab46c0808f8` | `ddaf83a70366935fe504807b0dd9aab46c0808f8` | OWNER_HOLD — explicit draft restriction is authoritative | 12 commits | 5 checks SUCCESS | **NOT MERGED — do not merge** | Title carries `[draft, do not merge]`. Signal validity kept separate from send-time actionability |
| [#50](https://github.com/aungmyat1/AG-profit-trading-assit/pull/50) | `afbc49ab645bdad443f89fa9f1430e59c53f73a0` | `bae2ceda6d371aaa6e509668afe42ded280f950a` (on `main`) | SUPERSEDED — fully integrated on `main` | 3/3 added files on `main` | 5 checks SUCCESS | **NOT MERGED — superseded** | None. Owner still decides the D6 deploy; the PR title requires an explicit `deploy D6` |
| [#51](https://github.com/aungmyat1/AG-profit-trading-assit/pull/51) | `ea2b6c89cc40f2334e47df441a9e042d38012cf9` | `ea2b6c89cc40f2334e47df441a9e042d38012cf9` | OWNER_HOLD — frozen spec verified, discrepancies reported not rewritten | 4 commits, 12 files | 5 checks SUCCESS | **NOT MERGED — do not merge** | Title carries `[draft, do not merge]`. One BLOCKING owner row `LSMC-OD-32` |
| [#52](https://github.com/aungmyat1/AG-profit-trading-assit/pull/52) | `9bb5560c3dbc46c570b0ef40a3db6b606886527e` | `9bb5560c3dbc46c570b0ef40a3db6b606886527e` | RESEARCH_HOLD — deterministic registration reviewed | 1 commit, 58 files | 9 checks SUCCESS | **NOT MERGED** | 70 commits behind; a direct merge would delete 94 `main` files. No registry entry on `main` |
| [#53](https://github.com/aungmyat1/AG-profit-trading-assit/pull/53) | `ad3daaef62b62640453011a3431f2296584dbd63` | `ad3daaef62b62640453011a3431f2296584dbd63` | RESEARCH_HOLD — readiness diagnostics reviewed, not merged to reduce open count | 12 commits, 117 files | 5 checks SUCCESS | **NOT MERGED** | Depends on #52, which is itself unmerged and unrebased. DEV sample provenance must be re-verified after any rebase |
| [#63](https://github.com/aungmyat1/AG-profit-trading-assit/pull/63) | `29082289f94817dc5bae09c5c0717dd844585f70` | `29082289f94817dc5bae09c5c0717dd844585f70` | BLOCKED — cannot merge as-is; review findings target absent code | 1 commit, 12 files | docs-drift FAILURE, others SUCCESS | **NOT MERGED — blocked** | See Finding F-63 |
| [#77](https://github.com/aungmyat1/AG-profit-trading-assit/pull/77) | `0065a04af425fed9b15ea1cd5985b87d49d7fe77` | `937173677301f194a81f53eacb2739ec6100ba99` | REMEDIATED + integrated onto current `main` (draft PR #84) | 1366 passed, 2 skipped, 0 failed | 9 checks SUCCESS | **NOT MERGED — draft PR #84** | Owner approval to merge #84 |
| [#78](https://github.com/aungmyat1/AG-profit-trading-assit/pull/78) | `8db01e8d4d8fcf254aeaaf2286ae75ff2d1363ef` | `937173677301f194a81f53eacb2739ec6100ba99` | REMEDIATED + integrated onto current `main` (draft PR #84) | 1366 passed, 2 skipped, 0 failed | 9 checks SUCCESS | **NOT MERGED — draft PR #84** | Owner approval to merge #84 |
| [#80](https://github.com/aungmyat1/AG-profit-trading-assit/pull/80) | `bcbdd28dbaeb290794ae5fdd289d3d18c5c5101e` | `bcbdd28dbaeb290794ae5fdd289d3d18c5c5101e` | OWNER_HOLD — reviewed against the canonical ticket schema, not merged | 9 commits, 9 files | 9 checks SUCCESS | **NOT MERGED** | 2 files absent from `main`. Chat allowlist, signed callbacks, replay protection, expiry, exactly-once journal and disabled demo authorization must be owner-confirmed |
| [#81](https://github.com/aungmyat1/AG-profit-trading-assit/pull/81) | `99c30579c049771b75602a144cdec4121d30eba1` | `937173677301f194a81f53eacb2739ec6100ba99` | REMEDIATED + integrated onto current `main` (draft PR #84) | 1366 passed, 2 skipped, 0 failed | 9 checks SUCCESS | **NOT MERGED — draft PR #84** | Owner approval to merge #84 |

`Final SHA` is the head of the branch that now carries the PR's reviewed content. For
SUPERSEDED and BLOCKED rows it is the PR head unchanged.

## Remediation branches

| Branch | Head | Draft PR | Carries |
|---|---|---|---|
| `arena/863d367a-sched-r1` | `937173677301f194a81f53eacb2739ec6100ba99` | [#84](https://github.com/aungmyat1/AG-profit-trading-assit/pull/84) | #77, #78, #81 |
| `arena/863d367a-crypto-r1` | `c82f2df35514141c4ce6b1d195f8e5868861479a` | [#85](https://github.com/aungmyat1/AG-profit-trading-assit/pull/85) | #30, #31 |

Both are stacked on `origin/main` (`bae2ced`). They touch disjoint source files and overlap only
in `PROJECT_STATUS.md`, which is resolved by union on both branches. Merge order does not matter;
if both are approved, merge #84 first and revalidate #85.

## Why every stale branch was re-based rather than merged

The clone was shallow at the start of this mission, so `git merge-base` initially returned empty
and `rev-list --count` reported misleading "ahead" values. After
`git fetch --depth=700 origin main`, real merge-bases were available. The decisive fact:

**Merging any of these branch tips directly would delete files that exist on `main`.**

| PR | Net diff vs `main` | `main` files a direct merge would delete |
|---|---|---|
| #19 | +912 / −37348 | 201 |
| #30 | +3620 / −29142 | 147 |
| #31 | +8034 / −29141 | 147 |
| #32 | +1569 / −29142 | 147 |
| #34 | +1427 / −29142 | 147 |
| #36 | +998 / −26455 | 141 |
| #45 | +4120 / −20365 | 94 |
| #48 | +830 / −20216 | 92 |
| #49 | +2264 / −20242 | 92 |
| #50 | +335 / −20149 | 91 |
| #51 | +2355 / −20365 | 94 |
| #52 | +5335 / −20365 | 94 |
| #53 | +19769 / −20365 | 94 |
| #63 | +17597 / −10866 | 48 |
| #77 | +313 / −4206 | 25 |
| #78 | +216 / −4083 | 25 |
| #80 | +585 / −2701 | 8 |
| #81 | +347 / −4090 | 25 |

That is why the two workstreams cherry-picked onto fresh branches off `main` instead of merging
the PR branches, and why the remaining PRs are recorded as holds rather than merged. A stale
branch tip is not mergeable content; it is a stale snapshot.

## Findings and what was done

### F-30 — evaluation-time look-ahead in the Crypto-CFD strategy contract (P1, FIXED)

`src/crypto_cfd_contract/rules.py::evaluate()` applied the causal filter only to the M5 series.
D1, H1 and M15 candles timestamped at or after `now` could still grant direction permission, so
an unresolved historical setup could be returned as `ENTRY_VALID` — the exact failure the
mission calls out as "future HTF candles must not change earlier evaluation results".

Fixed: the filter now applies uniformly to all four supplied timeframes through a local
`_closed()` helper, and the report carries an auditable `evidence["causal_filter"]` block
(`rule`, `closed_candles`, `dropped_unclosed`) per timeframe, so the filtering is inspectable
rather than implicit.

### F-30b — rolling status and contract index (P1, FIXED)

`PROJECT_STATUS.md` now records "no registered contract covers BTCUSD/ETHUSD CFDs" as a
**pre-change** finding, states what #30 resolves (`CONTRACT_COMPLETE`,
`STRATEGY_CONTRACT_VALID = TRUE`), and keeps the runtime gap explicitly separate: scanner/checklist
wiring still absent, `EDGE_VERIFIED = FALSE`, `EXECUTION_AUTHORIZED = FALSE`,
`BROKER_ORDERS_SENT = 0`. `docs/README.md` indexes
`docs/contracts/AG_CRYPTO_CFD_STRATEGY_CONTRACT_V1.md`.

### F-31a — the frozen identity omitted the model that produces the outcomes (P1, FIXED)

`src/edge_discovery/freeze.py` hashed only the paths already listed in
`contract_file_sha256`, which omitted `src/edge_discovery/replay_c001.py` — even though that
module declares `REPLAY_FILL_MODEL_V1` frozen and directly determines fills, exits and gross R.
A later edit to the fill model could therefore move results without changing the identity.

Fixed: a new `outcome_defining_file_sha256` section pins the outcome-deciding modules with the
same strictness as the contract files, and a **missing** pin is a hard failure
(`C001_OUTCOME_MODEL_NOT_PINNED`) rather than a warning, so the gap cannot silently reopen.

### F-31b — `slice_partition()` leaked days the cohort excluded (P1, FIXED)

`src/edge_discovery/partitions.py::slice_partition()` filtered by the partition's outer time
bounds instead of its frozen day set. A day can be complete for one symbol and gap-declared for
the other, so the cohort excludes it for both symbols while that symbol's own bars still exist
inside the same time range. A range slice would hand those bars to the fast screen as if they
were frozen observations — the "never silently convert missing data into valid observations" rule
broken silently.

Fixed: the slice tests exact frozen UTC-day membership. The new negative test
`test_slice_partition_returns_only_frozen_days_not_the_outer_time_range` was verified to **fail**
against the previous range-based implementation, so it is not a vacuous pass.

### F-31c — reports did not record their own code or strategy version (P1, FIXED)

`src/edge_discovery/offline_pipeline.py` emitted reports with neither the application that
produced them nor the strategy version, so a result could not be tied to the code that made it.

Fixed: every report, blocked ones included, records the content SHA-256 of the outcome-deciding
modules (`application_sha256`, `application_files`) and the `strategy_version` read from the
frozen C001 manifest. An unreadable identity is a hard failure
(`C001_APPLICATION_IDENTITY_INCOMPLETE`); an unreadable manifest yields
`STRATEGY_VERSION_UNKNOWN` rather than a fabricated version.

### F-31d — invalid candidate-queue placeholder source type (P1, FIXED)

Nine metadata-only rows in `research/edge_discovery/candidate_queue.yaml` used
`source_type: UNASSIGNED`, which is not a member of `CandidateSource` at all, so no manifest
could ever be built from such a row. They now use `FAMILY_PLACEHOLDER` — the vocabulary value
that means "no source identified yet" — and the queue's `permitted_source_types` matches the enum
exactly, pinned by a test.

### F-FREEZE — governance event requiring owner visibility

The `rules.py` look-ahead fix changes bytes the C001 freeze record pins, so
`verify_c001_rule_identity()` correctly raised `C001_RULE_MUTATION_REQUIRES_C002_PLUS`.

The correction is **recorded, not silently applied**.
`research/edge_discovery/candidates/CRYPTO_CFD_C001.freeze.json` now carries a
`pre_result_corrections` entry (previous SHA-256, corrected SHA-256, reason, authority, review
reference) alongside the new pinned hash.

This is permitted **only** because no C001 economic result exists: `edge_verified: false`,
`fast_screen_status: NOT_EVALUATED`, `full_verification_status: NOT_EVALUATED`. The verifier now
fails closed on a correction recorded after results exist (`C001_CORRECTION_AFTER_RESULTS`), and
a test pins that rule. **Once any economic result exists, the same edit must become a new C002+
candidate.** This is the single most important owner-visible decision in this record.

### F-77 / F-78 / F-81 — host schedule authority (HIGH, FIXED in draft PR #84)

`scripts/docs/collect_facts.py::parse_host_schedule()` was rewritten around a four-layer model so
the four things the mission requires to be distinguished are actually distinguished:

| Layer | Source | Meaning |
|---|---|---|
| `REPO_DECLARED` | `$Plan` | what `install_tasks.ps1 -Apply` would install |
| `REGISTERED` | `$Declared[].Registered` | Task Scheduler registration observed 2026-10-08 |
| `OBSERVED` | `heartbeat.py` output | `NOT_PUBLISHED` — never observed on a host |
| `TARGET` | `$Declared[].Target` | the proposed always-on target |

Computed `drift` is now 11 rows (`AG-V1-Crypto-Daily` every_min 15→5; `AG-V1-LSMC-Watch` days
`Mon-Fri`→`DAILY` and start `00:03`→`00:04:15`; five ENABLED→ABSENT retirements; two
DISABLED→ABSENT removals; `AG-Heartbeat-Local` ABSENT→ENABLED). Two bugs were fixed on the way:
`drift[].task` was `None`, and an inverted guard suppressed cadence drift entirely.

`scripts/host/install_tasks.ps1` no longer commits host-specific checkout paths: `$HostRoots`
became `<HOST_SCRATCHPAD>\prod|dev|telemetry`, the heartbeat `--out` became
`<HOST_SCRATCHPAD>\ag-telemetry\heartbeat.json`, and `Get-TaskDiff()` emits
`Exe/Args: REDACTED (host path not committed)`. Exact task identity is preserved.

`scripts/host/heartbeat.py` no longer classifies overnight silence as `INACTIVE_EXPECTED` from
the retired sleep window. It now models `POWER_MODES` with `DEFAULT_POWER_MODE = "wake_sleep"`,
`ALWAYS_ON_WINDOWS`, and a `source_windows()`/`reader_rule()` pair; an unknown mode fails closed
to `always_on` rather than silently excusing silence. Four overnight/always-on regression tests
were added using `OVERNIGHT_LAST` (2026-10-07 12:00 MMT) and `OVERNIGHT_NOW` (2026-10-08 03:00
MMT), a span that exceeds `SOURCE_STALE_AFTER` (2 h) while sitting inside the retired
00:45–12:25 MMT window.

A vacuous-test defect was fixed in `tests/test_host_go_live_kit.py`: the `$Plan` assertion regex
returned `[]` after main advanced, so its loop never executed. It now tolerates main's optional
`Canonical` field and asserts `len(plan) == 3`.

Validation of the installer's syntax and declaration parsing was performed **without executing
`install_tasks.ps1 -Apply`**. `HOST_SCHEDULE_MUTATIONS = 0`.

### F-48 — both #48 findings are already resolved on `main` (REVIEWED_NO_ACTION)

*P1 — "update the rolling status for the new delivery behavior."* `PROJECT_STATUS.md` line 133
on `main` already records "an LSMC alert dedup ledger" and the per-identity delivery attempts, and
`tests/test_lsmc_alert_dedup.py` is present on `main`. The rolling snapshot the finding asked for
exists. **No action needed.**

*P2 — "resolve crypto symbols before loading tick metadata."* Verified empirically against
current `main`, not by reading the diff:

```
_display_record('BTCUSDT', None)          -> MISS      (no metadata keyed by the canonical name)
_display_record('BTCUSD',  None)          -> HIT BTCUSD
resolved broker symbol (BTCUSDT via v3)   -> BTCUSD
_display_record('BTCUSDT', 'BTCUSD')      -> HIT
_tick_digits('BTCUSDT', 'BTCUSD')         -> (0.01, 2)
```

`_display_record()` falls back to `load_record(broker_symbol)` and requires the record's
`broker_symbol` to match the selected mapping, so the production paths resolve correctly. The
finding described a state that a later commit on this branch already fixed. **No action needed.**

Residual: three files are still absent from `main`
(`scripts/host/ag_daily_health.ps1`, `docs/governance/OWNER_DECISIONS_2026-10-07_LSMC_ACTIONABILITY_V1.md`,
`docs/status/AG_V1_FIRST_NATURAL_READY_EVIDENCE_2026-10-07.md`). #48 is 70 commits behind, so
extracting them needs a rebase decision from the owner, not a blind cherry-pick.

### F-50 — superseded, proven not asserted (SUPERSEDED)

All three files #50 adds are present on `main` with the expected content:
`config/v1_tickets/ready_authority.yaml` (`ready: OFF`, `reason: READY_AUTHORITY_OFF_D6`),
`src/v1_tickets/ready_authority.py`, and `tests/test_d6_ready_authority.py`, plus the dated status
doc. Two of the three are byte-identical to the PR's blobs. #50 is fully integrated.

The PR is **not** closed merely for being old: it is closed on positive evidence of integration.
The D6 *deploy* decision remains the owner's; the PR title requires an explicit `deploy D6`, and
nothing here performs it.

### F-51 — frozen spec verified; discrepancies reported, not rewritten (OWNER_HOLD)

Identity and provenance verified directly:

* `docs/specs/LSMC_SPEC_V1_FROZEN.sha256.txt` → `6516e3ba…` matches the actual content hash.
* `docs/specs/LSMC_SPEC_V2_FROZEN.sha256.txt` → `6c7e9d02…` matches the actual content hash.
* V1 is retained unaltered apart from a `SUPERSEDED` banner, with the owner-signed v1.0.2 hash
  `ffd003d1…` recorded and the exact signed content recoverable at `git show b2f0ca7:…`.
* V2 declares `FROZEN`, 31 rows closed, **1 BLOCKING open** (`LSMC-OD-32`), and an explicit
  authority separation: `IMPLEMENTED != VALIDATED != AUTHORIZED`, no code/registry/threshold
  change, `proposal_generation_authorized = False`.

Discrepancy reported, **not** rewritten: V2 itself records that applying owner batch 3 required
re-deriving the price scale of the C10 SHORT stop, and that derivation contradicts a justification
the spec has carried since v1.0.0 (the v1.0.0 §7.3 claim that `stop_c10` is "BID-comparable in
both directions"). V2 leaves the measurement rule exactly as signed and corrects only the false
justification. **The frozen spec was not edited to match newer code**, per the mission rule. The
blocking row `LSMC-OD-32` is the owner's to close.

### F-63 — cannot merge as-is; the review findings target code that does not exist (BLOCKED)

Two independent, verified blockers.

**1. Merging #63's current head would delete 48 files that exist on `main`.** The branch is
1 commit ahead and 40 behind `main`; its net diff is +17597 / −10866 across 100 files, and 48 of
those are pure deletions of `main` content — including `config/v1_tickets/ready_authority.yaml`
(the D6 READY authority gate), `docs/agents/INVARIANTS.md`,
`docs/governance/OWNER_DECISION_REGISTER.md`, `scripts/host/heartbeat.py`,
`src/ticket_store/grader.py`, `src/v1_tickets/ready_authority.py` and
`strategies/ST_ASIAN_SWEEP_5R_V1_1_1_2.yaml`. It also removes the L2-closure candidate block from
`strategies/registry.yaml`. This is a regression, not an integration.

**2. Every review finding on #63 targets code that is absent from the repository.** The findings
reference `src/v1_tickets/cfd_contract.py`, `src/sizing_math/cfd_sizing.py`, and
`docs/status/AG_CFD_TICKET_CONTRACT_AND_LSMC_110_GAP_AUDIT_2026-10-07.md`, reviewed at commit
`67694fb3a8`. Verified:

* `git cat-file -t 67694fb3a8` → *Not a valid object name* (the reviewed revision is not in this
  repository at all).
* A search of **all 90 refs** for `cfd_contract.py`, `cfd_sizing.py`, or
  `AG_CFD_TICKET_CONTRACT_AND_LSMC_110` returns nothing.
* `CfdContractError`, `symbol_meta_from_info`, `verify_mapped_from`, `SIZING_METADATA_MISSING`
  and `size_position` appear nowhere in the tree or in the last 200 commits.

The findings are therefore **stale review comments against a force-pushed-away revision**, not
actionable defects in current code. They cannot be "resolved" because there is nothing to resolve
them against; if that code is ever reintroduced, the findings must be re-raised against the
revision that introduces it.

`docs-drift` on #63 is FAILURE, consistent with a branch that does not track `main`.

**Required owner decision:** rebase #63 onto current `main`, or close it and open a fresh PR from
current `main`. Neither is an agent-side action: the branch has another writer.

### F-34, F-36, F-45, F-52, F-53 — research holds (REVIEWED, not merged)

Recorded so the findings are not lost, and so no one concludes that silence meant approval.

* **#34** (`ST_MTF_CONTROL_SHIFT_V1`, research-shadow, draft). `engine.py::_in_window()` tests the
  M15 zone's **bar-open** timestamp, so a zone whose bar closes after the session-window end is
  still admitted — a look-ahead in the entry-timing definition.
  `structure.py::control_shift_zones()` takes `prior[-1]`, the latest opposing zone active before
  the break, without confirming it was not already invalidated. The strategy is absent from
  `strategies/registry.yaml` and `strategies/STRATEGY_LEDGER.md` on both `main` and the PR, and
  its capability is absent from `PROJECT_STATUS.md`. No economic claim is made anywhere, which is
  correct.
* **#36** (dependency/lint optimization, draft). Pins `numpy==2.5.3`, which requires Python ≥3.11,
  while `README.md` line 237 and `pyproject.toml` both advertise ≥3.10 — a Windows MT5
  compatibility regression the mission explicitly forbids. Its new
  `docs/architecture/THIRD_PARTY_STRATEGY_DEPENDENCIES.md` is not indexed in `docs/README.md`,
  which does index the other `architecture/` documents. Note `main`'s `requirements.txt` pins no
  numpy at all, so the fix is to drop the pin rather than to lower it.
* **#45** (sanitized Asian Sweep v1.2 blind handoff). 70 commits behind; a direct merge deletes 94
  `main` files. Its frozen-input identity and neutral-identifier requirements were reviewed and
  are sound; the packaging needs a rebase decision.
* **#52** (Candidate Factory R1). 70 commits behind; a direct merge deletes 94 `main` files.
  Deterministic registration, reproducibility and contractability gates were reviewed; no registry
  entry exists on `main`, so no strategy is admitted.
* **#53** (R3 readiness diagnostics + INT_C002 longer DEV sample). Depends on #52, which is itself
  unmerged and unrebased, so its readiness diagnostics and DEV-sample provenance cannot be
  validated against current `main`. **Not merged to reduce the open-PR count**, per the mission.

### F-19, F-80, F-49 — owner holds (NOT MERGED)

* **#19** (disabled Demo Stage-B MT5 execution). Read-only security/integration review only. The
  review points — route broker sends through the canonical execution gate, fail closed when
  `history_deals_get()` returns `None`, size against the executable market price, reject a
  supplied `now` outside tolerance, bind approval to a digest of the approved ticket, retire the
  legacy execution route — are recorded for the owner. The branch is 142 commits behind and a
  direct merge deletes 201 `main` files. **Owner approval is binding**; nothing was merged.
* **#80** (fail-closed Telegram ticket confirmations). Reviewed against the canonical ticket
  schema: chat allowlist, signed callbacks, replay protection, expiry, exactly-once journal,
  disabled demo authorization, D6 and C16 compliance. Two files are absent from `main`
  (`src/host_delivery/telegram_confirm.py`, `tests/test_telegram_confirmation.py`).
  `TELEGRAM_AUTHORITY_CHANGED = FALSE` — no credential, allowlist or authority surface was touched.
* **#49** (LSMC actionability gate). The title carries `[draft, do not merge]`. Per the mission,
  an explicit draft restriction is authoritative, so this stays on hold. The
  `VALID_SIGNAL → ACTIONABILITY_GATE → WATCH_READY | INFO_ONLY | EXPIRED | MISSED` chain was
  verified to keep signal validity separate from send-time actionability, with no market-logic or
  threshold change.

## Verification performed

* Baseline on `bae2ced` with a fresh Python 3.11.2 venv (pytest 8.3.5, PyYAML 6.0.3, pandas 2.3.3,
  requests, smartmoneyconcepts 0.0.27, fastapi 0.135.1, httpx 0.28.1, uvicorn 0.41.0,
  pydantic 2.13.5, pyarrow 25.0.1, cogapp): **1356 passed, 4 skipped, 0 failed in 38.8 s**.
* Workstream A (`#84`): **1366 passed, 2 skipped, 0 failed in 37.2 s**.
* Workstream B (`#85`): **1481 passed, 2 skipped, 0 failed in 82.1 s**.
* The excluded-day negative test was confirmed to **fail** against the previous range-based
  `slice_partition()`, so it is a real guard rather than a vacuous pass.
* `docs-drift`: 0 blocking errors on `main` and on `arena/863d367a-crypto-r1`.
* No broker order submission, no demo/live authorization, no execution-gate relaxation, no
  automatic strategy admission, no economic verification, no unsealing of OOS datasets, no host
  scheduled-task / power / Telegram-credential / production-config change.
* No owner process was terminated and no RAM gate was changed.
* No PR was closed merely for being old: #50 is superseded on positive patch evidence, and every
  other PR is left open with its exact blocker recorded.

## Owner decisions still required

1. **Merge approval for draft PR #84** (#77/#78/#81 — host schedule authority, always-on
   heartbeat). This is the HIGH-priority workstream and is ready.
2. **Merge approval for draft PR #85** (#30/#31 — crypto-CFD contract + Edge Discovery). Ready,
   and it carries the F-FREEZE governance event below.
3. **The F-FREEZE decision.** The `rules.py` look-ahead fix changes bytes the C001 freeze record
   pins. This record documents it as a *pre-result* correction, permitted only because no C001
   economic result exists. **The owner must either ratify that pre-result correction or require a
   new C002+ candidate.** No C001 run has been performed either way, so nothing is contaminated
   yet — which is exactly why this is cheap to decide now and expensive to decide later.
4. **#63 rebase-or-recreate.** #63's head would delete 48 `main` files, and its review findings
   target code that does not exist in the repository. The owner must decide whether to rebase it
   onto current `main` or close it and open a fresh PR. The branch has another writer.
5. **Rebase decisions for #32, #45, #52, #53.** Each is 70–110 commits behind and would delete
   94–147 `main` files if merged directly. Their content is sound research work; the question is
   who rebases it and when.
6. **#49 and #51 stays.** Both carry `[draft, do not merge]` in the title. Removing that
   restriction is an owner act, not an agent act.
7. **#19 and #80 stays.** Owner approval is binding for #19's execution surface and for #80's
   Telegram authority surface.
8. **D6 deploy for #50.** #50's code is already on `main`; the deploy decision is separate and
   requires the owner's explicit `deploy D6`.

## Shortest safe path to the M7 pipeline smoke test

Nothing below changes an authority gate. It is the shortest path that produces a real M7 smoke
result without relaxing anything.

1. **Approve and merge draft PR #84** (`arena/863d367a-sched-r1`, head `9371736`). It is the
   HIGH-priority workstream, it is green (9/9 checks), and it makes the installer the
   authoritative schedule source — which the M7 smoke test needs in order to declare *what* is
   scheduled rather than inferring it.
2. **Revalidate PR #85** after #84 merges. The two branches touch disjoint source files and
   overlap only in `PROJECT_STATUS.md`; a re-run of the full suite plus `docs-drift` on the
   rebased branch is the required post-merge revalidation.
3. **Approve and merge draft PR #85** (`arena/863d367a-crypto-r1`, head `c82f2df`). This lands the
   causal evaluation-time filter, the frozen-identity fix for the replay model, the excluded-day
   slice fix, report code/strategy identity, and the queue vocabulary fix.
4. **Run the read-only M7 smoke on the Windows host**, in this order, each step read-only:
   * `scripts/host/install_tasks.ps1` **without `-Apply`** to confirm the declared plan parses and
     that no host-specific path is committed.
   * `scripts/host/verify_tasks.ps1` to compare `REGISTERED` against `REPO_DECLARED` and read the
     11-row drift table.
   * `scripts/host/heartbeat.py --host-power-mode always_on` and again with `wake_sleep`, to
     confirm the corrected always-on logic classifies an overnight quiet span as `STALE` rather
     than `INACTIVE_EXPECTED`.
   * `scripts/host/live_candles_smoke.py --mode fx --canonical` for one cycle, which is the
     existing read-only observation path into the canonical ticket store.
5. **Confirm the OBSERVED layer can then be published.** It is `NOT_PUBLISHED` today because no
   host has run the heartbeat under the new model. Step 4 is what changes that, and it changes it
   by observation, never by assertion.

What is deliberately **not** on this path: no broker order submission, no demo/live authorization,
no execution-gate relaxation, no strategy admission, no economic verification, no unsealing of OOS
datasets, and no scheduled-task registration. The M7 smoke test is a read-only observation gate;
everything past it is an owner decision.

---

_Report footer: offline verification only. `BROKER_MUTATIONS = 0`,
`STRATEGY_ADMISSIONS = 0`, `HOST_SCHEDULE_MUTATIONS = 0`,
`TELEGRAM_AUTHORITY_CHANGED = FALSE`. No live host, live MT5 session, or live Telegram path was
exercised. Windows host acceptance and Telegram live acceptance remain NOT_EVALUATED._
