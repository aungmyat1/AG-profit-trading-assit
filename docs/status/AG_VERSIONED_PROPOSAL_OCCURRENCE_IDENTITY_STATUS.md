# Versioned Proposal Occurrence Identity — Candidate (2026-09-20)

Mission `AG_VERSIONED_PROPOSAL_OCCURRENCE_IDENTITY_V1`. Prepares and validates a
**versioned candidate** so scheduled M15 observations of the same logical FX setup no
longer inflate opportunity/proposal counts.

**Identity/governance change only.** No strategy economics, qualification rule,
execution authority, Large SMC evidence, BTC evidence, or historical ledger record was
modified. **No demo or live execution authority was granted or exercised.**

`HEAD_BEFORE = 6fafb713714ba6d649b04726f0a1d79a1b6deb82` (worktree clean)

`HEAD_AFTER = accd344b7723d45e13fabda2f93e0ab1644885f0`

Note: a concurrent agent committed SVOS capacity work (`0e013b6`) into the same worktree
during this mission. That work was left entirely untouched; this mission's changes are
isolated in their own commit on top of it.

---

## 1. Identity baseline (P0/P1) — reproduced

Reproduced read-only on the live ledger via the existing audit
(`proposal_envelope.identity_audit.audit_ledger_file`):

| Figure | Value |
|---|---|
| Ledger records | **69** |
| Distinct logical setups | **13** |
| Distinct observations | 67 |
| Duplicate records | **56** |
| Inflation ratio | **5.31×** |

Worst case: **11 records** for one unchanged
`ST_ASIAN_SWEEP_5R_V1:LONDON_NEWYORK:EURUSD:2026-09-15` setup, every one with
byte-identical `direction`/`entry`/`stop`/`targets` and an identical
`liquidity_evidence` tuple `(LIQUIDITY_SWEEP, 1.15397, M15)`.

6 records (5.31× inflation is the FX portion) are `DERIVED_SSC_COMPOSITE` — the
`ssc_adapter` family, which emits no `confirmation_evidence.setup_id`.

### The three-layer distinction (P1)

The defect is a **layer collapse**, not a missing concept. All three layers already
exist canonically:

| Layer | Canonical source | Volatility | Role |
|---|---|---|---|
| 1. Evaluation/decision | `post_asian_pilot.decision._decision_id` (hashes `evaluation_time`) → `source_record_id` | every poll, by design | evidence only — never a persistence key |
| 2. Logical setup occurrence | `confirmation_evidence.setup_id` (`strategy:cycle:symbol:trading_date`) | stable per setup | **the deduplication key** |
| 3. Proposal envelope | `proposal_envelope_id` (WP7 canonical `proposal_id`) | should be per setup | the persisted record key |

`fx_adapter` builds `proposal_envelope_id = f"FX:{decision.decision_id}"`, and
`_decision_id` hashes `evaluation_time`. Because the weekday scheduler polls every M15
close, each poll produces a fresh `decision_id` → fresh `proposal_envelope_id` → a new
ledger record every 15 minutes for an unchanged setup. `ProposalLedger.record_proposal`'s
geometry-match idempotency only fires for the **same** key, so it never triggers.

### `proposals/occurrence_identity.py` is NOT a drop-in solution (confirmed)

The mission's warning is correct, and it was verified rather than assumed. That module's
`candidate_occurrence_id` composes `SETUP_FAMILY_ID + ELIGIBILITY_INTERVAL_ID +
m_candidate_identity` for the **Large-SMC / entry-confirmation** family, whose
`eligibility_intervals` are disjoint *replay* windows
(`historical_replay.stage1.QualifiedEEvent`). The FX `post_asian_pilot` family has **no
authoritative producer** of those inputs at all. Adopting it would require inventing an
FX eligibility interval — a new identity scheme, not a reuse. It is left entirely
untouched (its own docstring already states it is "not wired into either yet").

---

## 2. The versioned candidate (P2)

**`CANDIDATE_VERSION = AG_PROPOSAL_OCCURRENCE_IDENTITY_V1`**
**`OCCURRENCE_IDENTITY_SOURCE = confirmation_evidence.setup_id` (authoritative canonical field only)**

New module `src/proposal_envelope/occurrence_identity_v1.py`. Additive; nothing imports
it. `WIRED_INTO_RUNTIME = False` is an explicit module constant asserted by test — wiring
it in is a promotion decision requiring validation plus registry/ledger authorization,
not a code change alone (AGENTS.md).

### Occurrence composition

```
occurrence_id = H(strategy_id | strategy_version | logical_setup_id | structural_reference)
```

- `logical_setup_id` — the authoritative canonical `confirmation_evidence.setup_id`.
  Session and trading-date separation are therefore **structural properties of the key**,
  not extra rules bolted on.
- `strategy_version` — for the same demonstrated reason
  `ticket_delivery.identity.logical_ticket_id` documents: the canonical `setup_id` has no
  version component, so a version bump on the same date/cycle/symbol would otherwise
  collide with the prior version's occurrence.
- `structural_reference` — the signed structural anchor, reusing
  `proposals.identity.reference_key_for`'s **existing** convention
  (`type|low|high|level`) rather than inventing a fourth key scheme. For FX this is the
  `liquidity_evidence` trigger triple, verified byte-stable across all 11 duplicate
  records of the worst-case real setup.

`evaluation_time`, `detected_at`, `data_version`, and `market_data_asof` are **absent by
construction** — including any of them would reproduce the collapse. A test asserts this
structurally, not just behaviorally.

### Persistence semantics (all deliberate, all tested)

| Case | Behavior |
|---|---|
| Geometry-stable repetition | **idempotent** — provenance appended, `version` unchanged, record untouched |
| Genuinely new setup | **new occurrence record** |
| Geometry change within one occurrence | **linked correction** (`version`+1, `correction_of` set, prior kept in `history`) — mirroring `ProposalLedger`'s existing tested convention, not a second one |
| Restart | same identity, no duplicate (`runtime_state.store.JsonKeyValueStore` reused verbatim) |
| Historical evidence | never rewritten or dropped; every observation's full provenance preserved in `observations` |

### Fail-closed rule — deliberately stricter than the audit

Logical setup identity is taken **only** from the authoritative
`confirmation_evidence.setup_id`. Any other family raises
`OccurrenceIdentityUnavailable` — never a guessed or derived key, never a synthetic
"unknown" bucket.

This is intentionally **stricter** than the read-only audit's documented
`DERIVED_SSC_COMPOSITE` fallback. Deriving an identity is acceptable for *measuring* an
audit; it is **not** acceptable for creating an authoritative persistence key. The
candidate therefore does **not** silently promote the derived SSC composite to
authoritative identity. `ssc_adapter` reports `OCCURRENCE_IDENTITY_UNAVAILABLE` and is
excluded from occurrence counts rather than mis-keyed.

### Governed boundary — what was NOT changed

`_decision_id`, `fx_adapter`'s `proposal_envelope_id`, `ProposalLedger`'s keying, and
every adapter's field mapping are **unchanged** — all frozen canonical behavior with
historical evidence attributed to them. A test proves the frozen path still returns all
69 records as `PROPOSAL_READY`, so the candidate demonstrably did not alter it.

---

## 3. Expiry lifecycle audit (P3) — a real defect, confirmed

**Confirmed defect:** the frozen `ProposalLedger.list_active_proposals()` returns all
**69** persisted records as `PROPOSAL_READY`, while **63 of them have already passed their
strategy-owned expiry** (`plan_expires_at` / `timestamps.expires_at`). `/api/canonical-proposals`
serves that list directly, so expired proposals remained operationally presented as
current `PROPOSAL_READY`.

**Candidate remediation (read-time only, unwired):**

- `is_expired()` / `expiry_of()` — reads only the strategy-owned field; a record with **no**
  expiry evidence is never reported expired (that would invent a lifecycle rule the source
  strategy never defined).
- `with_presentation_state()` — narrows `PROPOSAL_READY` → `PROPOSAL_EXPIRED` **only**.
  Never upgrades, never touches direction/entry/stop/targets, cannot grant authority.
- `current_proposals()` / `expired_proposals()` — the sanctioned "what is currently
  presented" views, partitioning the population.
- `mark_expired_at_presentation()` — **flags** expiry on the occurrence record; the
  persisted `current` record stays byte-identical (asserted). Immutable/auditable history
  fully preserved.

---

## 4. Reporting semantics (P5)

Four distinct metrics, never collapsed into one number:

```
OBSERVATION_COUNT              = raw persisted records
DISTINCT_SETUP_COUNT           = distinct logical setups
CURRENT_ACTIVE_PROPOSAL_COUNT  = occurrences not expired at `now`  (= opportunity count)
EXPIRED_PROPOSAL_COUNT         = occurrences expired at `now`
IDENTITY_UNAVAILABLE_COUNT     = records with insufficient authoritative identity
```

`opportunity_count` is exposed **only** as `CURRENT_ACTIVE_PROPOSAL_COUNT`. `render()`
states explicitly that `OBSERVATION_COUNT` is *not* a trade-opportunity count, so a raw
ledger record count cannot be presented as one.

### 69-record reconciliation

| Figure | Frozen path (today) | Candidate |
|---|---|---|
| OBSERVATION_COUNT | 69 records | **69** |
| DISTINCT_SETUP_COUNT | (not computed) | **9** authoritative + 6 unavailable |
| Distinct occurrences | 69 keys (the collapse) | **10** |
| CURRENT_ACTIVE_PROPOSAL_COUNT | 69 presented active | **0** |
| EXPIRED_PROPOSAL_COUNT | 0 | **63** |
| IDENTITY_UNAVAILABLE_COUNT | 0 | **6** (SSC) |

Note the two setup counts are honestly different and both are reported: the audit's
**13** logical setups includes the 6 SSC records under a *derived, non-authoritative*
composite; the candidate's **9** counts only setups with *authoritative* identity and
reports the 6 as unavailable rather than mis-keying them. No number is silently dropped.

---

## 5. Tests (P4)

`tests/test_proposal_occurrence_identity_v1.py` — **49 tests**, covering every required
case:

| Requirement | Test |
|---|---|
| Same setup across repeated M15 evaluations → one occurrence | `test_repeated_m15_evaluations_of_one_setup_resolve_to_one_occurrence` |
| Geometry-stable repetition → idempotent | `test_geometry_stable_repetition_is_idempotent_and_preserves_every_observation` |
| Genuine new setup → new occurrence | `test_genuine_new_setup_produces_new_occurrence` |
| Restart → same identity | `test_restart_produces_the_same_identity_and_does_not_duplicate` |
| EURUSD and GBPUSD | `test_eurusd_and_gbpusd_occurrences_are_distinct_and_each_deduplicate` |
| Session separation | `test_session_separation_holds`, `..._survives_identical_geometry_and_timestamps` |
| Trading-date separation | `test_trading_date_separation_holds`, `..._within_one_cycle_and_symbol` |
| Expiry | 8 tests incl. `test_expired_proposal_is_not_presented_as_ready`, `test_expired_record_is_flagged_not_rewritten` |
| Unknown/insufficient identity → fail closed | 7 tests |
| Historical records unchanged | `test_frozen_ledger_file_is_byte_identical_after_all_read_only_operations`, `test_frozen_ledger_records_are_still_all_reported_ready_by_the_frozen_path` |
| P5 metrics distinct | 6 tests |
| No execution import / candidate unwired | `test_candidate_module_has_no_execution_import`, `test_candidate_is_versioned_and_not_wired_into_runtime` |

### Results

| Command | Result |
|---|---|
| `pytest tests/test_proposal_occurrence_identity_v1.py -q` | **49 passed** |
| Identity/proposal/ledger/ticket-delivery regression surface (12 files) | **129 passed** |
| Full suite `pytest tests -q` | **3625 passed, 4 failed, 7 skipped, 1 deselected** in 23:10 |

**All 4 full-suite failures are pre-existing and unrelated to this change set.** None is
in a file this mission touched, and all 4 reproduce at `HEAD_BEFORE`:

| Failure | Cause | Evidence |
|---|---|---|
| `test_large_smc_eurusd_admission_wp2.py::test_strategy_semantics_files_unchanged_by_this_mission` | Byte-freeze test asserting `git diff e596507` is empty for `src/large_smc_research/`; the prior scheduler mission (`64675c6`) added `live_watch.py` + `watch_lifecycle.py` there | Both files exist at `HEAD_BEFORE` (`git cat-file -e 6fafb71:src/large_smc_research/live_watch.py` succeeds); `git diff HEAD -- src/large_smc_research/` is **empty** |
| `test_large_smc_eurusd_friction_campaign_wp3a1.py::test_c10_and_strategy_semantics_unchanged_by_this_mission` | Same byte-freeze invariant | Same |
| `test_large_smc_eurusd_friction_evidence_wp3a.py::test_strategy_semantics_files_unchanged_by_this_mission` | Same byte-freeze invariant | Same |
| `test_validation_framework.py::test_btc_adapter_reconciles_against_registry_and_yaml` | Documented environmental failure: the scheduled BTC daily task accrues `observed_count` 0→1 while the test hard-codes 0 | Already classified pre-existing in `AG_SCHEDULER_AND_LARGE_SMC_WATCH_HARDENING_STATUS.md` §"Full suite"; `git diff HEAD -- src/validation_framework/adapters/btc_adapter.py tests/test_validation_framework.py` is **empty** |

The three Large-SMC byte-freeze failures are a **pre-existing invariant-scope defect**
introduced by the prior mission (a whole-directory byte-freeze that its own new files
trip), not a regression from this mission. They are reported here rather than silently
repaired, because fixing them would mean editing a frozen-evidence test outside this
mission's scope.

**No WP3A.1 friction evidence, Large SMC watcher scheduling, or BTC campaign state was
modified by this mission** — verified by empty `git diff HEAD` over those paths.

---

## 6. Safety statement

| Item | State |
|---|---|
| DEMO_AUTHORITY | **unchanged** (`NONE`) |
| LIVE_AUTHORITY | **unchanged** (`NONE`) |
| Entries / stops / targets / setup filters | **unchanged** — no test or code path computes or adjusts geometry |
| Strategy economics | **unchanged** — no strategy YAML touched |
| WP3A.1 friction evidence | **unchanged** — not read, not written |
| Large SMC watcher scheduling | **unchanged** — not touched |
| BTC campaign state | **unchanged** — not touched |
| Historical ledger records | **unchanged** — byte-identical after all read-only operations (asserted) |
| Frozen canonical behavior | **unchanged** — `_decision_id`, `fx_adapter` envelope id, `ProposalLedger` keying all untouched |
| Candidate wired into runtime | **NO** — `WIRED_INTO_RUNTIME = False` |

---

## 7. Promotion recommendation

**Do not promote yet.** The candidate is `UNIT_TESTED` and `WIRED_INTO_RUNTIME = False`.
It is validated and ready to be the basis of a promotion decision, but promotion requires
separately-scoped work this mission did not perform:

1. **Authoritative identity inputs for non-FX families.** `ssc_adapter` (and the other
   families that emit no `confirmation_evidence.setup_id`) currently fail closed. Each
   family needs an authoritative setup-identity field before it can be counted at all.
2. **Ledger migration/reconciliation policy.** The candidate writes a **new**
   occurrence-scoped ledger and deliberately never rewrites the frozen 69-record ledger.
   Promoting requires an explicit, separately-authorized reconciliation of the existing
   records — including how the 63 already-expired records are represented historically.
3. **Wiring decision + expiry enforcement at the presentation boundary.** Expiry
   enforcement is read-time and unwired; wiring it changes `/api/canonical-proposals`
   behavior and must land with its own validation.
4. **Registry/ledger authorization.** AGENTS.md requires promotion to be recorded in
   `strategies/registry.yaml` and `strategies/STRATEGY_LEDGER.md` — no strategy
   registration or authorization changed here.

`OCCURRENCE_IDENTITY_SOURCE = confirmation_evidence.setup_id` is the recommended basis
for any such promotion, because it is the only **authoritative** input and already exists
in every FX record.

---

## 8. Files changed

| File | Change |
|---|---|
| `src/proposal_envelope/occurrence_identity_v1.py` | **new** — versioned candidate (identity + occurrence ledger + expiry presentation + metrics) |
| `tests/test_proposal_occurrence_identity_v1.py` | **new** — 49 focused tests |
| `docs/status/AG_VERSIONED_PROPOSAL_OCCURRENCE_IDENTITY_STATUS.md` | **new** — this document |
| `PROJECT_STATUS.md` | rolling snapshot updated |
| `docs/README.md` | document index updated |

No frozen strategy, configuration, adapter, ledger, campaign, or scheduler file was
modified.
