# AG TRADETICKET VERTICAL SLICE V1 — INDEPENDENT AUDIT

**Mission:** `AG_TRADETICKET_VERTICAL_SLICE_V1_INDEPENDENT_AUDIT_RESUME`
**Date:** 2026-09-29 (UTC) · **Auditor branch:** `arena/01a0ebe9-ag-profit-trading-assit`
**Method:** isolated detached worktree at `/tmp/auditwt`; candidate never merged, cherry-picked, or modified.
**Independent probes:** 72 auditor-written tests (deleted after use; worktree verified pristine).

```
CLASSIFICATION = TRADETICKET_VERTICAL_SLICE_AUDIT_FAIL
                 (2 BLOCKING_BEFORE_FREEZE findings, both narrow and cheap;
                  13 of 15 audit phases PASS outright)

NEXT_STEP = CLAUDE_BOUNDED_REMEDIATION_OF_EXACT_AUDIT_FINDINGS
```

This is **not** a rejection of the design. The pipeline is well built, the containment is
real and I proved it at runtime, and the reuse discipline is genuine. The classification
turns on one thing: **`AG_TRADE_TICKET_V1` is about to be frozen, and as written it cannot
record how proposal authority was obtained.** Freezing that is expensive to undo. Two small
changes fix it.

---

## A1 — INTEGRITY GATE: **PASS**

| Check | Expected | Observed | |
|---|---|---|---|
| Remote ref SHA | `e7dd985c…f53c6` | `e7dd985c11e00150f18925d993bca6f2f5ef53c6` | PASS |
| Tree | `b2c42287…9de5f` | `b2c42287837d7660c5102f7a534473a34e89de5f` | PASS |
| Parent | `76348c72…de60f` | `76348c728b2229de2ad0a5c22f857bf0263de60f` | PASS |
| Base is ancestor | yes | `merge-base --is-ancestor` → true | PASS |
| `origin/main` unchanged | `4bbba319` | `4bbba3192b2c26245b4e7f0d6d7b15960e0d96c8` | PASS |

All four required files present: `qualification.py` (208L), `sizing.py` (163L),
`ticket.py` (350L), `tests/test_trade_ticket_vertical_slice.py` (427L).

**Diff is purely additive** — 9 files, `1321 insertions(+), 0 deletions(-)`: 4 new production
files (`src/trade_ticket/`), 1 test file, 3 docs, `PROJECT_STATUS.md`. **No existing
production file was modified.** `requirements.txt` untouched.

---

## A2 — PRIOR LINEAGE ASSUMPTION: **RETRACTED. The builder is correct.**

My previous audit reported `1a8e7c5` as being on a disjoint history. **That finding was
wrong, and I am withdrawing it.**

Root cause, found this session: the sandbox clone was **shallow** (`.git/shallow` present,
`git rev-parse --is-shallow-repository` → `true`, `origin/main` at **depth 1**). `git
merge-base` on a shallow clone returns empty for commits whose common ancestor was never
fetched — which is indistinguishable from "unrelated histories" unless you check for
shallowness. I did not check. After `git fetch --unshallow` (`origin/main` depth 1 → 382):

```
1a8e7c5 ANCESTOR_OF_MAIN       = YES
1a8e7c5 ANCESTOR_OF_CANDIDATE  = YES
merge-base(1a8e7c5, origin/main) = 1a8e7c5d922ba48423dca1b7858f8895afe0d66f
```

Continuous ancestry confirmed exactly as reported:
`1a8e7c5 → 3f1f955 → 76348c72 → e7dd985c`, each verified as an ancestor of the next.
`merge-base(candidate, main)` = `4bbba319`, so the candidate descends from current `main`.

**`src/execution/risk.py` deletion traced:**

| | |
|---|---|
| Blob at `1a8e7c5` | `ecda12d2a131c6fdc40c738e79bac79d3a0bd7b4` |
| Deleted by | `3f1f9550dd23740bc5e0fb996e5a281ae0531658` — *"feat: initialize project structure"*, 2026-09-27 |
| Scale of that commit | **1047 files changed, 2767 insertions, 931,870 deletions** (1029 files deleted) — a deliberate mass repo reset, not a targeted removal |
| Present at `3f1f955` / `76348c72` / `e7dd985c` / `4bbba31` | **ABSENT at all four** |

Deletion occurs inside continuous ancestry. The module is genuinely gone from the active
tree; `tests/test_fx_opportunity_containment.py` enforces that absence.

---

## A3 — SIZING AUTHORITY: `HISTORICAL_AG_REUSE_ACCEPTABLE`

**Semantic identity — byte-exact, not merely similar.** I extracted the `size_position`
function region from the historical blob and from the candidate and hashed both:

```
historical (ecda12d2)  sha256 = 8d99c657f84eacba2922c25a6c6c9fb3fb7a3adde71a2676834da9e5ee2bad67
candidate  (sizing.py) sha256 = 8d99c657f84eacba2922c25a6c6c9fb3fb7a3adde71a2676834da9e5ee2bad67
BYTE_IDENTICAL = True   (1562 bytes both)   _FLOAT_TOL = 1e-9 both
```

Every item the mission named is preserved identically: `tick_size`/`tick_value`-derived
money-per-lot (no hardcoded pip math), `math.floor(raw/step + 1e-9)` **round-down** step
quantisation, `round(…, 8)` accumulation-noise guard, `volume_min`/`volume_max` tolerance
comparisons, the `max(risk_budget*1e-6, 1e-6)` budget tolerance, and all four reason codes.
JPY geometry is handled by construction rather than by a special case — confirmed
numerically in A9.

**Is there a second source of truth?** No. `src/execution/` **does not exist** in the
candidate tree; there is exactly **one reachable production sizing authority**. This is a
*restoration of a deleted AG-owned function into the only live tree*, not a fork running
alongside an original.

The wrapper (`prepare_sizing`) adds **only validation** — risk-policy presence, equity
validity, open-risk validity and aggregate ceiling, geometry finiteness, symbol/digits/
metadata-source binding, metadata field validity — then calls the verbatim function. It
changes no arithmetic.

Not `DUPLICATED_AUTHORITY` (nothing to duplicate), not `SEMANTIC_DRIFT` (hash-identical),
not `RESTORED_SHARED_COMPONENT_RECOMMENDED` as a blocker — a shared module is worth doing
**if and when** a second consumer appears; today it would be a one-consumer abstraction.
Recorded as a nonblocking watch item.

---

## A4 — OSS-FIRST REUSE GATE: **PASS**

| Component | Verdict |
|---|---|
| `qualification.py` | `JUSTIFIED_CUSTOM`. Ties MarketState provenance + candidate + authority + staleness + look-ahead into one gate. No AG module does this; no OSS component carries AG's authority model. Correctly does **not** re-check geometry — it delegates to the unchanged `opportunity.proposal_eligibility`. |
| `sizing.py` | `EXISTING_AG_REUSE` (verbatim historical restoration) + `JUSTIFIED_CUSTOM` validation wrapper. |
| `ticket.py` | `JUSTIFIED_CUSTOM`. `CanonicalProposal` carries no broker/server/environment/cycle/sizing/instrument-fingerprint/semantic-hash fields. The ticket **embeds** the proposal rather than restating it, and reads direction/entry/stop/targets from it — reuse, not reimplementation. |
| Indicator adapter | **Correctly unnecessary.** The slice computes no indicators; entry/stop/targets are strategy-owned and arrive via `CandidateGeometry`. My earlier `ag_indicators` recommendation does not apply to this slice. Confirmed: no EMA/ATR/stdev code anywhere in `src/trade_ticket/`. |
| Existing AG reused unchanged | `opportunity.proposal_eligibility`, `opportunity.contracts`, `opportunity.registry_binding`, `proposal_envelope.*` (incl. `to_canonical_proposal`), `fx_opportunity.{instruments,market_state,runner}`, `mt5.symbol_resolver`, `post_asian_pilot.fingerprint`. |

**No unnecessary custom build found.** **Zero supply-chain expansion** — `requirements.txt`
is not in the diff; no new third-party import appears in the slice (only `yaml`, already a
dependency).

---

## A5 — QUALIFICATION / AUTHORITY BOUNDARY: **PASS on every legitimate path; one defect**

Verified `REAL_STRATEGY_PROPOSAL_AUTHORITY = NONE`:

- No entry in `strategies/registry.yaml` carries `proposal_authorized` (asserted across all 7 entries).
- `resolve_proposal_authority("ST_ASIAN_SWEEP_5R_V1")` → `(False, "REGISTRY_FIELD_ABSENT")`.
- **REAL and REPLAY both blocked** → `NO_PROPOSAL_AUTHORITY`, `ticket is None`.
- Authority/candidate id mismatch → `AUTHORITY_STRATEGY_MISMATCH`.
- Real strategy in test mode → `REAL_STRATEGY_IN_PIPELINE_TEST_MODE`; test strategy in real mode → `PIPELINE_TEST_STRATEGY_IN_REAL_MODE`.
- Wrong cycle → `MARKET_STATE_CYCLE_MISMATCH`; wrong symbol → `MARKET_STATE_SYMBOL_MISMATCH`; wrong strategy version → different semantic hash.
- Eligibility returning `ELIGIBLE` is **not** sufficient — the authority gate runs first and short-circuits.

### 🔴 BLOCKING-1 — `AUTHORITY_SCHEMA_CONFLICT`: the canonical authority field is ignored

`StrategyBinding` — a **pre-existing canonical contract**, already resolved from the
registry, and **already passed into `prepare_trade_ticket()` as the `binding` argument** —
carries a field `proposal_authority`. Measured:

```
ST_ASIAN_SWEEP_5R_V1 -> binding.proposal_authority = False | execution_authority = NONE
SESSION_TRADE_V1     -> binding.proposal_authority = True  | execution_authority = DEMO_AUTHORIZED
```

The candidate **never reads it**. It introduces a parallel authority model on a *different*
registry key (`proposal_authorized`) that no entry carries. Grep of `qualify()` confirms the
only authority reads are `authority.strategy_id`, `authority.proposal_authorized`, and
`authority.source` (used for a message only — `CHECKS_SOURCE_FIELD = False`).

Consequence, measured: a hand-forged in-memory `ProposalAuthority("ST_ASIAN_SWEEP_5R_V1",
True, "FORGED")` passed in `REAL_STRATEGY_MODE`, **together with the genuine
registry-derived binding whose `proposal_authority` is `False`**, produces:

```
status = PREPARED_ONLY   ticket.strategy_id = ST_ASIAN_SWEEP_5R_V1   market_authoritative = True
```

Mitigating facts, stated plainly: this requires in-process code to construct the object by
hand; `execution_authority` remains `NONE`; no order path exists; and via the registry the
candidate is **stricter** than the canonical binding (it blocks `SESSION_TRADE_V1`, which
the canonical model would authorize). So this is not an execution-safety hole.

It is blocking **because of the freeze**, for two reasons: (a) the free cross-check
`binding.proposal_authority is True` was available on an argument already in hand and was
left unused, and (b) two competing authority schemas that disagree about `SESSION_TRADE_V1`
should not be frozen into a governance contract unresolved. Related: `resolve_proposal_authority`
accepts an arbitrary `registry_path`, and a forged file yields `source="REGISTRY"` —
which matters only because of BLOCKING-2.

```
AUTHORITY_SCHEMA_CLASSIFICATION = AUTHORITY_SCHEMA_CONFLICT
```

---

## A6 — `PREPARED_TEST_ONLY` ISOLATION: **PASS (strong)**

Isolation is **structural, not flag-based** — two independent mechanisms:

1. **Reserved namespace + mode cross-check.** `PIPELINE_TEST_` prefix; `qualify()` rejects
   the cross-product in both directions. `pipeline_test_authority()` raises on any
   non-prefixed id.
2. **Constructor invariant.** `__post_init__` enforces
   `(status == PREPARED_TEST_ONLY) == market_authoritative` as an XOR, rejects any status
   outside `IMPLEMENTED_STATES`, and rejects non-`NONE` execution authority on the ticket
   *and* on the embedded proposal.

Tampering attempts, all fail closed:

| Attack | Result |
|---|---|
| Relabel `status`/`market_authoritative`/`strategy_id` in the dict | `verify_ticket_dict` → `False`; hash changes |
| **Recompute** `semantic_fingerprint` after relabelling | still `False` — `ticket_id` binds the *original* hash (`TKT-<fp[:24]}`), so the attacker must break two bindings |
| `dataclasses.replace(status=PREPARED_ONLY)` | `ValueError` |
| `dataclasses.replace(market_authoritative=True)` | `ValueError` |
| `dataclasses.replace(execution_authority="DEMO")` | `ValueError` |
| `status` = `OWNER_CONFIRMED` / `DEMO_EXECUTION_REQUESTED` | `ValueError` (declared, not implemented) |

The dual `ticket_id`/`semantic_fingerprint` binding is a genuinely good design choice —
it defeats the obvious recompute attack. No research attribution to
`ST_ASIAN_SWEEP_5R_V1` is possible from the fixture path. No execution authority arises.

---

## A7 — RISK POLICY LINEAGE: **PASS**

```
pilot policy = 0.5% per trade / 1.0% max aggregate   (ticket.risk_pct == 0.5)
config/trading.demo.yaml = {'risk': {'risk_per_trade_pct': 1.0}}   -- confirmed divergent
```

| Case | Result |
|---|---|
| Correct pilot | ticket at 0.5% |
| Missing policy (`None`) | `SIZING_BLOCKED` / `RISK_POLICY_UNAVAILABLE` |
| Wrong pilot (right numbers, wrong `pilot_id`) | `SIZING_BLOCKED` / `RISK_POLICY_PROVENANCE_MISMATCH` |
| Generic config fallback | **impossible** — AST-level check of executable string literals (docstrings excluded) finds no `trading.demo` / `trading.yaml` reference; the slice performs exactly **one** `open()` and **one** `yaml.safe_load`, both the read-only registry |
| Tampered `risk_policy_fingerprint` | `verify_ticket_dict` → `False` |
| Different policy | different `risk_policy_fingerprint` **and** different semantic hash |

`GENERIC_RISK_FALLBACK = NOT_PRESENT`. There is no loader for the 1.0% default in this
path, so it cannot be reached by configuration alone.

---

## A8 — OPEN RISK: **PASS**

| Input | Result |
|---|---|
| `None` (missing) | `SIZING_BLOCKED` / `AGGREGATE_RISK_UNKNOWN` |
| `NaN`, `+Inf`, `-Inf`, `-0.1` | `AGGREGATE_RISK_UNKNOWN` |
| `True` (bool) | `AGGREGATE_RISK_UNKNOWN` — bool explicitly excluded, a real trap avoided |
| `0.75` (0.75 + 0.5 > 1.0) | `AGGREGATE_RISK_EXCEEDED` |
| `0.5` (exactly at ceiling) | allowed |
| `0.5001` | blocked |

No "assume zero" anywhere: no `open_risk_pct or 0` and no defaulting `getattr`. Absence is
treated as unknown, and unknown is blocked. Correctly, **no broker position query exists**.

---

## A9 — GEOMETRY: **PASS**

Full 6-case matrix (EURUSD/GBPUSD/USDJPY × LONG/SHORT) sized successfully with risk
bounded by the 0.5% budget in every case:

```
EURUSD LONG/SHORT  vol=0.38  risk=49.4000
GBPUSD LONG/SHORT  vol=0.38  risk=49.4000
USDJPY LONG/SHORT  vol=0.49  risk=49.0002     (tick_size 0.001, tick_value 0.66667, digits 3)
```

**USDJPY uses its own tick semantics** — proven by differential, not inspection: an
identical *pip count* (15 pips) gives **0.49 lots on USDJPY vs 0.33 lots on EURUSD**. A
global `0.0001` assumption would have produced identical sizes. No such assumption exists.

Rejections: `NaN`/`±Inf` entry or stop → `NONFINITE_GEOMETRY`; `entry == stop` →
`INVALID_STOP_DISTANCE`; wrong-side stop → `RISK_GEOMETRY_INVALID` (caught by the unchanged
eligibility firewall); wrong-side target → `INVALID_TARGET_GEOMETRY` (a gap the candidate
correctly identified as **not** covered by eligibility, which checks finiteness only);
`tick_size`/`tick_value`/`volume_step`/`volume_min`/`volume_max` zero or NaN →
`SYMBOL_METADATA_INVALID`; volume under minimum → `VOLUME_BELOW_MIN`. Non-standard
`volume_step=0.13` quantises exactly and stays within budget — **rounds down, never up**.

---

## A10 — SYMBOL METADATA BINDING: **PASS**

EURUSD opportunity + GBPUSD metadata → `SYMBOL_METADATA_MISMATCH`; + USDJPY metadata →
`INSTRUMENT_DIGITS_MISMATCH` (digits checked before symbol in the JPY case — both fail
closed). Wrong digits → `INSTRUMENT_DIGITS_MISMATCH`. In `REAL` mode, synthetic metadata →
`SYMBOL_METADATA_NOT_BROKER_VERIFIED`; the requirement is correctly relaxed only for the
fixture path. `symbol_meta_fingerprint` binds the full metadata object into the ticket
hash — altering `tick_value` alone changes both fingerprints.

The candidate binds the metadata available in its **current** contract safely and does not
claim a Canonical Instrument Registry. WP-7A remains correctly future work.

---

## A11 — SEMANTIC HASH MUTATION MATRIX: **PASS on-ticket; one provenance gap**

All **40** authority-relevant ticket fields mutated individually
(`status`, `pipeline_mode`, `market_authoritative`, `execution_authority`, `opportunity_id`,
`candidate_id`, `proposal_envelope_id`, `symbol`, `broker`, `broker_symbol`, `server`,
`environment`, `cycle`, `reference_session`, `direction`, `entry`, `stop_loss`, `targets`,
`risk_pct`, `risk_amount`, `position_size_lots`, `account_currency`, `account_equity`,
`aggregate_risk_policy`, `strategy_id`, `strategy_version`, `strategy_config_hash`,
`pilot_config_hash`, `risk_policy_fingerprint`, `risk_policy_source`, `policy_fingerprint`,
`market_state_fingerprint`, `market_data_fingerprint`, `market_data_mode`,
`instrument_fingerprint`, `symbol_meta_fingerprint`, `evidence`, `created_at`, `expires_at`,
`expiry_source`, `proposal`):

```
UNHASHED AUTHORITY FIELDS (on-ticket) = []      ← every one changes the hash
ticket_id == "TKT-" + semantic_fingerprint[:24] ← verified
```

Only `ticket_id` and `semantic_fingerprint` are excluded, which is correct and documented.

### 🔴 BLOCKING-2 — authority-relevant inputs that never reach the ticket

```
OPEN_RISK_ON_TICKET             = False
aggregate_risk_policy           = "NOT_AVAILABLE"   (hardcoded literal)
HASH_DIFFERS_ACROSS_OPEN_RISK   = False
```

Two tickets sized under `open_risk_pct = 0.0` and `open_risk_pct = 0.4` are
**hash-identical**. The open-risk value gated the authorization decision (A8 proves the
gate works) but is absent from the record, so the ticket cannot reconstruct the risk
context that authorized it.

Combined with BLOCKING-1, the same is true of proposal authority: the ticket records **no**
`authority.source` and **no** authority fingerprint, so a registry-authorized ticket and a
forged-authority ticket are **byte-indistinguishable** in the frozen contract.

The mission says a read-only `OpenRiskSnapshot` is future work and must not be counted as a
current failure — and I agree the *sourcing* is future work. What is blocking is narrower
and is a **freeze** concern: `AG_TRADE_TICKET_V1` has no field in which that snapshot's
identity, or the authority source, can later be recorded without a schema break. The
candidate is honest about this (`"NOT_AVAILABLE"`, not a false claim), which is why the
remediation is a placeholder field, not a feature.

---

## A12 — DETERMINISM / RESTART PARITY: **PASS**

| Property | Result |
|---|---|
| Same input → same hash | identical |
| **Fresh interpreter** (`subprocess`, new process) → same hash | identical |
| JSON round trip | verifies |
| Tampering (any field) | detected |
| Duplicate identical request | `DUPLICATE` / `TICKET_ALREADY_PREPARED`, returns the **existing** ticket unchanged (idempotent) |
| Conflicting duplicate (same `proposal_envelope_id`, different hash) | `DUPLICATE_CONFLICT`, `ticket is None` |

`created_at` and `expires_at` are deterministic **inputs** (`evaluated_at`, execution-window
end), not wall-clock reads — so no timestamp exclusion is needed and restart parity is
genuine rather than an artifact of excluded fields.

---

## A13 — IMPORT GRAPH / CAPABILITY ZERO: **PASS (proved, not inferred)**

**Static.** No occurrence of `order_send`, `order_check`, `positions_get`,
`position_modify`, `MetaTrader5`, or `mt5.initialize` anywhere in `src/trade_ticket/`.
`src/execution/`, `src/authorization/`, `src/ticket_delivery/`, `src/owner_decision/`,
`src/strategy_manager/` **do not exist** in the tree.

**Transitive, fresh interpreter.** Importing `trade_ticket.ticket` in a clean process loads
176 modules; screened against `backtesting`, `smartmoneyconcepts`, `vectorbt`, `freqtrade`,
`execution`, `authorization`, `ticket_delivery`, `owner_decision`, `strategy_manager`:

```
FORBIDDEN IMPORTS REACHED = []
research_external / execution modules loaded = []
```

**Runtime.** I monkeypatched `MetaTrader5.order_send`, `order_check`, `positions_get`,
`initialize`, `login`, `shutdown` with recording stubs and ran the full pipeline on both
success and failure paths:

```
BROKER_ORDER_CHECK_CALLS        = 0
BROKER_ORDER_SEND_CALLS         = 0
OTHER_EXECUTION_MUTATION_CALLS  = 0   (positions_get / initialize / login / shutdown)
```

`TradeTicket`'s only public methods are `to_dict` and `semantic_fingerprint` — no order
method, no MT5 mutation, no callback hook.

Honest caveat: `MetaTrader5` **is** transitively imported (via `mt5.symbol_resolver`, for
the `SymbolMeta` type). In this environment that resolves to the repo-root stub, which
raises on any real broker operation. On a Windows box it would be the real package.
Containment therefore rests on *never called* — which I proved at runtime — rather than on
*never imported*. Recorded as a nonblocking observation.

**`BACKTESTING_PY_RUNTIME_REACHABILITY = NOT_REACHABLE`.** `backtesting` is not installed,
is imported only under `research_external/`, and appears nowhere under `src/`.
`smartmoneyconcepts` remains pinned in `requirements.txt` and is used only by
`scripts/research/` — **not** product-runtime reachable; unchanged by this candidate.
`vectorbt` `NOT_PRESENT`.

---

## A14 — OWNER VIEW: **PASS**

`owner_view()` builds a fresh plain `dict`. Mutating the returned view — `entry = 9.99`,
`position_size_lots = 99.0`, `ai_explanation.text = "BUY NOW"`,
`execution_authority = "DEMO"` — leaves the ticket's `semantic_fingerprint`, `entry`, and
`execution_authority` unchanged, and `verify_ticket_dict` still passes. The ticket is a
frozen dataclass (`FrozenInstanceError` on attribute assignment). `owner_view` is
deterministic (`view == view`). `ai_explanation` is hard-labelled
`{"authority": "ADVISORY_ONLY", "text": None}` and carries no path to entry, stop, targets,
risk, size, authority, or identity.

---

## A15 — `DEMO_TEST_EXECUTION_V1` COMPATIBILITY: **COMPATIBLE — nothing blocks clean separation**

`DECLARED_TRANSITIONS` already separates the two worlds structurally:

```
PREPARED_ONLY      -> (OWNER_CONFIRMED,)
OWNER_CONFIRMED    -> (DEMO_EXECUTION_REQUESTED,)
PREPARED_TEST_ONLY -> ()          # terminal: a fixture ticket never reaches owner-confirm
```

An ephemeral grant (single-use, `DEMO_ONLY`, `FIXTURE_ONLY`, `strategy_id = NONE`, owner
confirmation, explicit expiry, bounded symbol/volume/order count, LIVE forbidden) attaches
naturally at `OWNER_CONFIRMED` without touching prepared-state semantics. `IMPLEMENTED_STATES`
is enforced, so unimplemented states cannot be constructed today.

One design note, not a defect: because `PREPARED_TEST_ONLY` is terminal, a future
fixture-only demo execution would need to **add** a transition from it. That is additive and
explicit — arguably the right shape, since it forces the grant to be declared rather than
inherited.

---

## TEST EVIDENCE

| Suite | Result |
|---|---|
| Candidate's own focused tests | **42 passed** |
| Full repository regression at candidate | **702 passed, 4 skipped, 1 failed** |
| That 1 failure at **base** `76348c72` | **also fails** → pre-existing, environment-only (`No module named 'api.app'` / `fastapi`), **not a candidate regression** |
| **Auditor-written independent probes** | **72 passed** (A5–A14) |

The two initial red results in my own probe run were bugs in my probes (an invalid pilot key,
and a substring match that hit a docstring); both were fixed and neither indicated a
candidate defect.

---

## REQUIRED FINAL REPORT

```
AUDITED_SHA   = e7dd985c11e00150f18925d993bca6f2f5ef53c6
AUDITED_TREE  = b2c42287837d7660c5102f7a534473a34e89de5f
BASE_SHA      = 76348c728b2229de2ad0a5c22f857bf0263de60f
LINEAGE_VALID = YES (sha/tree/parent/ancestor all verified; origin/main unchanged 4bbba319;
                additive-only diff, 9 files, 1321(+) / 0(-))

SIZING_LINEAGE = 1a8e7c5:src/execution/risk.py blob ecda12d2a131c6fdc40c738e79bac79d3a0bd7b4
                 deleted by 3f1f955 ("feat: initialize project structure", 1029 files
                 deleted) within CONTINUOUS ancestry 1a8e7c5 -> 3f1f955 -> 76348c72 ->
                 e7dd985c. Prior DISJOINT_HISTORY finding RETRACTED (shallow-clone artifact).
SIZING_AUTHORITY_CLASSIFICATION = HISTORICAL_AG_REUSE_ACCEPTABLE
                 (exactly ONE reachable production sizing authority; src/execution absent)
SIZING_SEMANTIC_PARITY = BYTE_IDENTICAL (sha256 8d99c657...2bad67 both sides, 1562 bytes);
                 wrapper adds validation only, no arithmetic change

OSS_REUSE_GATE = PASS. No unnecessary custom build. Indicator adapter correctly
                 unnecessary (slice computes no indicators). Zero supply-chain expansion.

REAL_STRATEGY_PROPOSAL_AUTHORITY = NONE (verified: no registry entry carries
                 proposal_authorized; REAL and REPLAY both blocked; eligibility alone
                 insufficient; wrong version/pilot/cycle/symbol all blocked)
PREPARED_TEST_ONLY_ISOLATION = PASS (structural: reserved namespace + mode cross-check +
                 constructor XOR invariant + dual ticket_id/hash binding defeats recompute)
AUTHORITY_SCHEMA_CLASSIFICATION = AUTHORITY_SCHEMA_CONFLICT
                 (canonical StrategyBinding.proposal_authority exists, is already passed in,
                 disagrees about SESSION_TRADE_V1, and is never read)

RISK_POLICY_LINEAGE   = PASS (pilot-only, 0.5% / 1.0%; wrong/missing pilot and tampered
                        fingerprint all fail closed)
GENERIC_RISK_FALLBACK = NOT_PRESENT (AST-verified: no trading.demo/trading.yaml in
                        executable code; exactly one open() and one yaml.safe_load, the
                        read-only registry). config/trading.demo.yaml confirmed at 1.0%.

OPEN_RISK_FAIL_CLOSED = PASS (None / NaN / +-Inf / negative / bool -> AGGREGATE_RISK_UNKNOWN;
                        ceiling breach -> AGGREGATE_RISK_EXCEEDED; boundary exact at 0.5;
                        no assume-zero path)

GEOMETRY_MATRIX = PASS 6/6 (EURUSD/GBPUSD/USDJPY x LONG/SHORT). USDJPY proven to use its
                  own tick semantics by differential: 0.49 lots vs EURUSD 0.33 lots for an
                  identical pip count. All NaN/Inf/zero-distance/wrong-side/invalid-tick/
                  volume-step edge cases fail closed; step quantisation rounds DOWN.
SYMBOL_METADATA_BINDING = PASS (cross-symbol and wrong-digit forgeries blocked; REAL mode
                  requires broker-verified metadata; metadata fingerprint bound into hash)

SEMANTIC_HASH_COVERAGE = COMPLETE for all 40 on-ticket authority fields (zero unhashed).
                  GAP: open_risk_pct and authority.source are NOT ticket fields at all --
                  aggregate_risk_policy is the literal "NOT_AVAILABLE"; tickets sized under
                  0.0% vs 0.4% open risk are hash-identical.
DETERMINISM     = PASS
RESTART_PARITY  = PASS (fresh-interpreter subprocess hash match; JSON round trip verifies)
DUPLICATE_POLICY = PASS (identical -> DUPLICATE, returns existing ticket, idempotent;
                  conflicting -> DUPLICATE_CONFLICT, no ticket)
PROVENANCE      = PASS for opportunity / MarketState / market data / strategy+version /
                  strategy config / pilot policy / instrument / risk policy.
                  INCOMPLETE for open-risk context and authority source (see BLOCKING-2).

IMPORT_GRAPH_CONTAINMENT = PASS (static + transitive fresh-interpreter + runtime)
BACKTESTING_PY_RUNTIME_REACHABILITY   = NOT_REACHABLE
SMARTMONEYCONCEPTS_RUNTIME_REACHABILITY = NOT_REACHABLE (scripts/research only; unchanged)
VECTORBT_RUNTIME_REACHABILITY         = NOT_PRESENT

OWNER_VIEW_AUTHORITY = PROJECTION_ONLY (mutating the view changes nothing; ticket frozen;
                       ai_explanation ADVISORY_ONLY with no path to any authority field)

BROKER_ORDER_CHECK_REACHABILITY      = 0 calls (runtime-instrumented, success + failure paths)
BROKER_ORDER_SEND_REACHABILITY       = 0 calls (runtime-instrumented)
OTHER_EXECUTION_MUTATION_REACHABILITY = 0 calls (positions_get / initialize / login / shutdown)

FOCUSED_TESTS    = 42 candidate + 72 independent auditor probes = 114 passed
REGRESSION_TESTS = 702 passed, 4 skipped, 1 pre-existing env-only failure (fails at base too)
```

### BLOCKING_FINDINGS (both `BLOCKING_BEFORE_FREEZE`, both small)

**BLOCKING-1 — `AUTHORITY_SCHEMA_CONFLICT`: canonical `binding.proposal_authority` ignored.**
`qualify()` trusts a caller-supplied `ProposalAuthority` and never cross-checks
`binding.proposal_authority`, though the binding is already an argument. Measured: a forged
authority object plus the *genuine* binding (`proposal_authority=False`) yields
`PREPARED_ONLY`, `market_authoritative=True` for `ST_ASIAN_SWEEP_5R_V1`. Two authority
schemas now coexist and disagree about `SESSION_TRADE_V1`.

**BLOCKING-2 — authority-relevant inputs absent from the frozen contract.**
`open_risk_pct` and `authority.source` are not ticket fields; `aggregate_risk_policy` is the
hardcoded literal `"NOT_AVAILABLE"`. A registry-authorized ticket and a forged-authority
ticket are byte-indistinguishable, and the open-risk context that gated sizing is
unreconstructible. Blocking only because the schema is about to be frozen with no field to
carry them later.

### NONBLOCKING_FINDINGS (`NONBLOCKING_FUTURE_WP`)

1. `MetaTrader5` is transitively imported via `mt5.symbol_resolver`; containment rests on
   *never called* (proved) rather than *never imported*. A type-only import boundary would
   make it structural.
2. `resolve_proposal_authority(registry_path=…)` accepts an arbitrary path; a forged file
   yields `source="REGISTRY"`. Harmless once BLOCKING-2 records an authority fingerprint.
3. A shared neutral sizing module is unnecessary today (one consumer) but becomes the right
   move the moment a second consumer appears. Watch item only.
4. `PREPARED_TEST_ONLY` is terminal, so `DEMO_TEST_EXECUTION_V1` will need to add a
   transition — additive and arguably correct.
5. Canonical Instrument Registry (WP-7A), `OpenRiskSnapshot` sourcing, owner-confirm state
   machine, Demo and Live execution — all correctly future work; the candidate claims none
   of them.

### REMEDIATIONS_REQUIRED (exact, bounded — do not broaden)

1. In `qualify()`, REAL mode: additionally require `binding.proposal_authority is True`
   **and** `authority.source == "REGISTRY"`. Do not grant authority to anything; this only
   narrows. Resolve, in the plan doc, whether `proposal_authorized` or
   `StrategyBinding.proposal_authority` is canonical.
2. Add to `TradeTicket` (hashed): `proposal_authority_source` and an
   `open_risk_snapshot_fingerprint` placeholder (e.g. `"NOT_AVAILABLE"` today), so the
   frozen schema can carry both without a future break. Replace the hardcoded
   `aggregate_risk_policy` literal with the policy's actual aggregate value.
3. Re-run the 42 candidate tests + full regression. No other change.

```
NEXT_STEP = CLAUDE_BOUNDED_REMEDIATION_OF_EXACT_AUDIT_FINDINGS
            then re-audit, then FREEZE_AG_TRADE_TICKET_V1, then WP7A_CANONICAL_INSTRUMENT_REGISTRY
```

---

**Constraints honoured.** Candidate not modified, not merged, not cherry-picked;
`origin/main` unchanged at `4bbba319`; audit worktree verified pristine and removed.
No owner-confirm implemented, no open-risk source implemented, no proposal authority
granted, no strategy optimization run, no broker contact, `SEALED_OOS` untouched.
This document authorizes nothing.
