# FX Occurrence Identity Promotion Readiness (2026-09-20)

Mission `AG_FX_OCCURRENCE_IDENTITY_PROMOTION_READINESS_V1`. Determines whether
`AG_PROPOSAL_OCCURRENCE_IDENTITY_V1` is safe to promote **specifically for the currently
operational `ST_ASIAN_SWEEP_5R_V1` FX proposal path**.

**Scope discipline:** SSC and unrelated strategy-family identity were NOT solved. No
strategy entry/stop/target/filter/economics, BTC, Large SMC evidence, demo authority, or
live authority was modified. The candidate was **not wired** into the FX proposal
production path.

`HEAD_BEFORE = a180fab5d550262f8b4ed899dd9a32715527d785`

`HEAD_AFTER = <recorded at commit time>`

Note: a concurrent agent's SVOS capacity WIP was present in the worktree throughout and
was left entirely untouched.

---

## 1. P1 — `setup_id` authority: PROVEN

### The producer chain (traced, not assumed)

```
strategy_engine/engine.py::evaluate()
    signal_id = f"{strategy_id}:{pair_id}:{symbol}:{session_date.isoformat()}"
        -> execution/intent_builder.py::build_intent()   signal_id=signal.signal_id
        -> execution/adapter.py::TradeProposal.from_trade_intent()   setup_id=intent.signal_id
        -> post_asian_pilot/proposal.py::build_entry_proposal()      setup_id=trade_proposal.setup_id
        -> proposal_envelope/adapters/fx_adapter.py
               confirmation_evidence=dict(setup_id=trade_proposal.setup_id)
```

Every hop is the **same string**, verified end to end through the real producers.

### Why it is structural, not an evaluation timestamp

`signal_id` is composed from `strategy_id`, `pair_id`, `symbol`, and `session_date` — a
`datetime.date`, so the key has **no time component at all**. `evaluation_time` enters
only `post_asian_pilot.decision._decision_id`, which is the *observation* layer.

Proven adversarially: two different evaluation instants for the same signal produce
**different** `decision_id`s but the **same** `signal_id`.

### Structural reference

`liquidity_evidence.trigger_level = signal.entry = decision.entry_reference` — the swept
structural price level the setup qualified on, not a timestamp. The candidate reuses
`proposals.identity.reference_key_for`'s existing convention
(`LIQUIDITY_SWEEP|<level>|None|M15`).

### Parity results (all through the real chain)

| Requirement | Result |
|---|---|
| Repeated M15 observations of unchanged setup | 8 polls → **1** occurrence, **8** distinct evaluation ids |
| Changed market-data timestamp only | same occurrence |
| Restart (fresh engine load) | identical occurrence identity |
| EURUSD vs GBPUSD | distinct occurrences |
| ASIAN_LONDON vs LONDON_NEWYORK | distinct occurrences |
| New structural setup (different swept level) | **new** occurrence |
| Next trading date | **new** occurrence |
| Session/date separation with identical geometry | still distinct (separation is structural, not coincidental) |
| Occurrence key excludes observation-layer fields | asserted structurally |

**P1 gate: PASSED.** The identity is provably structural, so the mission did not stop.

---

## 2. P2 — Cutover design: forward-only, no reattribution

Two ledgers coexist; nothing is migrated.

| | LEGACY | V1 |
|---|---|---|
| Path | `state/proposal_ledger/proposal_ledger.json` | `state/proposal_ledger/proposal_occurrence_ledger.json` |
| Key | `FX:{decision_id}` (observation-derived) | `FXOCC:{strategy_id}:{occurrence_id}` |
| Treatment | **IMMUTABLE_RAW_OBSERVATION** | **OCCURRENCE_AWARE** |
| Written | never again | only from the cutover instant forward |

**Exact version marker.** Every V1 record carries
`schema_version = "AG_PROPOSAL_OCCURRENCE_LEDGER_V1"`; `generation_of(record)` reads that
marker so a reader never guesses from shape or timestamp. Anything without it is LEGACY.

**Exact cutover marker.** A separate, explicit, auditable file
`state/proposal_ledger/proposal_occurrence_ledger.cutover.json` written by
`write_cutover_marker(cutover_at=...)`, carrying `marker_version`, `cutover_at`, and the
full `CUTOVER_POLICY`. Deliberately **not** inferred from "the newest legacy record",
which would silently reclassify history.

`CUTOVER_POLICY` is machine-readable and asserts `retroactive_rewrite: False`,
`reattribution: False`, `migration: NONE`.

**Verified:** the frozen ledger is byte-identical after every candidate API is exercised
(read-only metrics, current/expired views, cutover-marker write, and a V1 occurrence
write). The 69 legacy records remain 63 observation-derived FX keys + 6 SSC keys.

---

## 3. P3 — Expiry presentation: promoted at the operational status surface

**Confirmed defect (unchanged frozen behavior):** `ProposalLedger.list_active_proposals()`
returns all **69** persisted records as `PROPOSAL_READY`, while **63** had already passed
their strategy-owned expiry.

**Promoted (read-time only, no historical rewrite):**

- `with_presentation_state()` narrows `PROPOSAL_READY` → `PROPOSAL_EXPIRED` only; never
  upgrades, never touches entry/stop/targets, cannot grant authority.
- `current_proposals()` / `expired_proposals()` / `identity_unavailable_proposals()` —
  three complementary views that partition the population.
- `presentation_ready_count()` — the expiry-corrected count.
- **`runtime_status/probe.py::_probe_proposal_ledger` now reports the expiry-corrected
  count** instead of the raw record count. Live output:

  ```
  0 current canonical proposal(s); 69 persisted observation record(s)
  (raw count, not an opportunity count)
  ```

  The raw count is still reported, explicitly labelled as observation records, so neither
  figure is hidden. Still a pure file read + importability check — no execution/order
  machinery, no writes, no governance impact.

**No expiry is invented.** `is_expired()` returns False when the strategy supplies no
expiry; a record with no expiry evidence stays `PROPOSAL_READY`.

**Not promoted:** `GET /api/canonical-proposals` still returns the frozen
`list_active_proposals()` list. Changing that route's response shape is a separate,
explicitly-scoped API decision this mission did not take.

---

## 4. P4 — Metrics: six distinct figures

```
OBSERVATION_COUNT                   = 69
DISTINCT_AUTHORITATIVE_SETUP_COUNT  =  9
DISTINCT_OCCURRENCE_COUNT           = 10
IDENTITY_UNAVAILABLE_COUNT          =  6
CURRENT_ACTIVE_PROPOSAL_COUNT       =  0
EXPIRED_PROPOSAL_COUNT              = 63
```

`opportunity_count` is exposed as `CURRENT_ACTIVE_PROPOSAL_COUNT` **only**. `render()`
states explicitly that `OBSERVATION_COUNT` is *not* a trade-opportunity count.

**One identity gate, applied consistently.** A record whose authoritative identity is
unavailable is counted only in `IDENTITY_UNAVAILABLE_COUNT` and excluded from every other
figure — the same gate `presentation_ready_count` and the current/expired views apply, so
no two metrics can disagree about scope. The buckets are mutually exclusive and account
for `OBSERVATION_COUNT` exactly once (0 + 63 + 6 = 69).

---

## 5. P5 — Scope boundaries

- **SSC remains FAIL_CLOSED / IDENTITY_UNAVAILABLE.** No SSC setup ID was invented. The 6
  SSC records are reported through `IDENTITY_UNAVAILABLE_COUNT` and
  `identity_unavailable_proposals()`, never mis-keyed.
- No strategy entry, stop, target, filter, or economics touched.
- BTC, Large SMC evidence, demo authority, and live authority untouched.

---

## 6. P6 — Verification

| Command | Result |
|---|---|
| `pytest tests/test_fx_occurrence_identity_promotion.py -q` | **35 passed** |
| `pytest tests/test_proposal_occurrence_identity_v1.py -q` | **49 passed** |
| Both identity suites together | **84 passed** |
| Affected regression surface (12 files incl. probe, API, pipeline, both pilots) | **190 passed** |
| Full suite `pytest tests -q` | see §7 |

### Known failures — reported, NOT silently repaired

| Failure | Status |
|---|---|
| `test_large_smc_eurusd_admission_wp2.py::test_strategy_semantics_files_unchanged_by_this_mission` | **Pre-existing.** Byte-freeze test asserting `git diff e596507` is empty for `src/large_smc_research/`; the prior scheduler mission (`64675c6`) added `live_watch.py` + `watch_lifecycle.py` there. Both files exist at `HEAD_BEFORE`. `git diff HEAD -- src/large_smc_research/` is empty. |
| `test_large_smc_eurusd_friction_campaign_wp3a1.py::test_c10_and_strategy_semantics_unchanged_by_this_mission` | **Pre-existing.** Same byte-freeze invariant. |
| `test_large_smc_eurusd_friction_evidence_wp3a.py::test_strategy_semantics_files_unchanged_by_this_mission` | **Pre-existing.** Same byte-freeze invariant. |
| `test_validation_framework.py::test_btc_adapter_reconciles_against_registry_and_yaml` | **Pre-existing / environmental.** BTC daily task accrues `observed_count` 0→1 while the test hard-codes 0. |

The three Large-SMC byte-freeze failures are a pre-existing **invariant-scope defect**
introduced by the prior mission (a whole-directory byte-freeze its own new files trip).
Repairing them would mean editing a frozen-evidence test outside this mission's scope, so
they are reported rather than fixed.

---

## 7. Safety statement

| Item | State |
|---|---|
| DEMO_AUTHORITY | **unchanged** (`NONE`) |
| LIVE_AUTHORITY | **unchanged** (`NONE`) |
| Strategy entry / stop / target / filters / economics | **unchanged** |
| BTC | **unchanged** |
| Large SMC evidence | **unchanged** |
| Historical ledger records | **unchanged** — byte-identical, verified after every candidate API |
| Frozen FX producer/adapter/ledger behavior | **unchanged** — `_decision_id`, `FX:{decision_id}` envelope id, and `ProposalLedger` keying all untouched |
| Candidate wired into FX proposal production | **NO** — `WIRED_INTO_RUNTIME = False` |
| SSC identity | **FAIL_CLOSED** — no invented setup ID |

---

## 8. Promotion decision

**PROMOTION_DECISION = `FX_IDENTITY_PROMOTION_READY_FOR_SCOPED_WIRING`**

Every promotion gate this mission was asked to evaluate **passed**:

1. `setup_id` authority proven structural end to end through the real producers.
2. Occurrence parity proven for all nine required cases.
3. Forward-only cutover designed with an explicit, auditable version marker.
4. Expiry presentation promoted at the operational status surface, with no invented
   expiry and no historical rewrite.
5. Six metrics exposed separately with one consistent identity gate.
6. SSC correctly left fail-closed.

**What "ready" does and does not mean.** The candidate is proven safe and correct for the
FX path, and the read-time expiry correction is now live in the runtime status probe. The
candidate is **still not wired into FX proposal production** — `WIRED_INTO_RUNTIME`
remains `False`, and the FX adapter's `proposal_envelope_id` is unchanged. Wiring it is a
separate, explicitly-scoped change that must land with its own validation and with
registry/ledger authorization recorded per AGENTS.md.

---

## 9. Files changed

| File | Change |
|---|---|
| `src/proposal_envelope/occurrence_identity_v1.py` | P2 cutover policy + marker API + `generation_of`; P4 six metrics; one consistent identity gate across all views; `presentation_ready_count` |
| `src/runtime_status/probe.py` | P3 — operational probe reports the expiry-corrected count, raw count labelled as observations |
| `tests/test_fx_occurrence_identity_promotion.py` | **new** — 35 end-to-end promotion-readiness tests through the real producers |
| `tests/test_proposal_occurrence_identity_v1.py` | updated for the P4 metric rename |
| `docs/status/AG_FX_OCCURRENCE_IDENTITY_PROMOTION_READINESS_STATUS.md` | **new** — this document |
| `PROJECT_STATUS.md`, `docs/README.md` | rolling snapshot + index |

No frozen strategy, configuration, adapter, ledger, campaign, or scheduler file was
modified.