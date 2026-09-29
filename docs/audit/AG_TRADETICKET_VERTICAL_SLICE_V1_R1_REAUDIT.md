# AG TRADETICKET VERTICAL SLICE V1 — R1 INDEPENDENT RE-AUDIT

**Mission:** `AG_TRADETICKET_VERTICAL_SLICE_V1_R1_INDEPENDENT_RE_AUDIT`
**Date:** 2026-09-29 (UTC) · **Auditor branch:** `arena/01a0ebe9-ag-profit-trading-assit`
**Method:** isolated detached worktree; candidate never modified, merged, or cherry-picked.
**Independent probes:** 79 auditor-written tests (74 + 5), removed after use; worktree verified pristine.

```
CLASSIFICATION = TRADETICKET_VERTICAL_SLICE_AUDIT_PASS

BLOCKING_1_CLOSED = YES
BLOCKING_2_CLOSED = YES
```

Both original blockers are independently closed, and every previously passing gate still
passes. One nonblocking limitation and one lineage observation are recorded below.

---

## A1 — IDENTITY AND LINEAGE: **PASS**

| Check | Expected | Observed | |
|---|---|---|---|
| R1 SHA | `1564769a…906e95` | `1564769ac3bd43a3b5aceaa37aa85cc662906e95` | PASS |
| Tree | `54fa8e69…405f0e` | `54fa8e696e04be404414a9a8c366341091405f0e` | PASS |
| Parent | `e7dd985c…f53c6` | `e7dd985c11e00150f18925d993bca6f2f5ef53c6` | PASS |
| R0 is ancestor of R1 | yes | yes | PASS |
| Remote ref | `audit/tradeticket-vertical-slice-v1-r1` | resolves to the expected SHA | PASS |

**Observation (nonblocking) — `origin/main` advanced during the remediation.**
It moved `4bbba319 → accf0637` (PR #12, *"Merge pull request #12 from
aungmyat1/claude/exciting-gates-lsfdgf"*). I verified the substance: the change is
**unrelated** to this slice — `web/scripts/*` MCP launcher work, `mt5_demo_credentials.mjs`,
`README.md`, `docs/setup/MT5_MCP_SETUP.md`. Critically:

```
1564769a (R1) in main: NO
e7dd985c (R0) in main: NO
```

**No candidate content was merged into `main`.** The audit requirement — candidate not
merged — holds. I record the drift because R1 was branched from `4bbba319`, so a later
rebase onto `accf0637` is a separate (and, on this evidence, trivially non-conflicting) step.

---

## A2 — DIFF CONTAINMENT: **PASS**

`e7dd985..1564769` — 7 files, `516 insertions(+), 44 deletions(-)`:

| File | Kind |
|---|---|
| `src/trade_ticket/qualification.py` | **expected production** |
| `src/trade_ticket/ticket.py` | **expected production** |
| `tests/test_trade_ticket_vertical_slice.py` | tests |
| `PROJECT_STATUS.md`, `docs/README.md`, `docs/plans/AG_OSS_FIRST_…_V1.md`, `docs/status/…_R1_REMEDIATION_STATUS.md` | docs |

**No unexpected production expansion.** Verified `UNCHANGED` by path-scoped diff:

```
src/trade_ticket/sizing.py   blob febaee7dc49e37c4571b8bd3aaccdd03f7707614 (identical R0 -> R1)
strategies/registry.yaml     UNCHANGED      config/trading.demo.yaml   UNCHANGED
src/opportunity              UNCHANGED      src/proposal_envelope      UNCHANGED
src/mt5                      UNCHANGED      src/fx_opportunity         UNCHANGED
src/strategy_engine          UNCHANGED      src/post_asian_pilot       UNCHANGED
src/execution, src/authorization, src/ticket_delivery, src/owner_decision,
src/strategy_manager                        ABSENT (all five)
```

**`strategies/registry.yaml` is untouched** — the new `proposal_authorization` schema is
*consumed* but never *written*, so no real strategy gained authority. `SEALED_OOS`
untouched; no economic access.

---

## A3 — BLOCKING-1 RE-AUDIT: **CLOSED**

R1 replaces the single trusted-input check with `_real_authority_denials()`, a conjunction
evaluated in fixed order that collects *every* disagreement. I wrote independent probes for
the full matrix; all behave as required:

| Probe | Result | Denial code |
|---|---|---|
| binding=False + **forged** authority=True | **BLOCK** | `BINDING_PROPOSAL_AUTHORITY_FALSE` |
| binding=False + **genuinely registry-resolved** authorized object | **BLOCK** | `BINDING_PROPOSAL_AUTHORITY_FALSE` |
| binding=True + authority=False (canonical registry) | **BLOCK** | `PROPOSAL_AUTHORITY_FIELD_ABSENT` |
| both False | **BLOCK** | both codes present |
| authority missing (`None`) | **BLOCK** | `AUTHORITY_MISSING` |
| wrong strategy | **BLOCK** | `BINDING_STRATEGY_MISMATCH` + `AUTHORITY_STRATEGY_MISMATCH` |
| wrong strategy_version | **BLOCK** | `AUTHORITY_STRATEGY_VERSION_MISMATCH` |
| wrong symbol | **BLOCK** | `AUTHORITY_SYMBOL_NOT_PERMITTED` |
| wrong cycle | **BLOCK** | `AUTHORITY_CYCLE_NOT_PERMITTED` |
| wrong market-data mode (REPLAY candidate vs REAL scope) | **BLOCK** | `AUTHORITY_DATA_MODE_NOT_PERMITTED` |
| wrong registry fingerprint | **BLOCK** | `AUTHORITY_REGISTRY_LINEAGE_MISMATCH` |
| **missing** expected fingerprint (`None`) | **BLOCK** | `AUTHORITY_REGISTRY_LINEAGE_MISMATCH` |
| wrong `source` (hand-made) | **BLOCK** | `AUTHORITY_SOURCE_NOT_REGISTRY` |
| non-canonical registry path (authorized off-path file) | **BLOCK** | `AUTHORITY_REGISTRY_PATH_NOT_CANONICAL` |

**Positive control (essential — otherwise the blocks could be vacuous).** With
`REGISTRY_PATH` monkeypatched so an authorized fixture registry *is* the canonical path,
and binding + authority + version + symbol + cycle + data mode + fingerprint all in
agreement:

```
FULL_AGREEMENT_RESULT: PREPARED_ONLY ()
```

The gate genuinely passes when it should. The R0 exploit — forged in-memory
`ProposalAuthority` yielding `PREPARED_ONLY` — is dead: the binding now has to agree, and
the binding is *derived* from the registry, not supplied.

```
BLOCKING_1_CLOSED = YES
```

---

## A4 — AUTHORITY SCHEMA CONSISTENCY: `CONSISTENT_SINGLE_CHAIN`

The three representations are now one chain with a single writable root:

```
strategies/registry.yaml            <- the ONLY writable authorization truth
        |                              (proposal_authorization block; owner-edited)
        |-- resolve_strategy_binding() ---> StrategyBinding.proposal_authority   (derived)
        |-- resolve_proposal_authority() -> ProposalAuthority + registry_fingerprint (derived)
                                    \
                                     qualify() requires BOTH to agree, plus scope
                                     and file-lineage match
```

Verified independently:

- **Deterministic derivation** — `resolve_proposal_authority()` is pure over the file bytes; two calls are equal, and its `registry_fingerprint` equals an independent `sha256` of the file.
- **`StrategyBinding.proposal_authority` is derived, not free input** — `resolve_strategy_binding(ST_ASIAN_SWEEP_5R_V1)` → `False` from the real registry.
- **Legacy path is dead** — a registry carrying only the old `proposal_authorized: true` key resolves to `(False, FIELD_ABSENT)`. The R0 key grants nothing.
- **Absence fails closed** — no block → `FIELD_ABSENT`; `authorized: false` → `NOT_AUTHORIZED`.
- **Malformed fails closed** — all 7 malformed shapes I tried (`{}`, partial scope, empty `symbols` list, non-str `strategy_version`, str instead of list, non-dict block) → `MALFORMED` or `FIELD_ABSENT`, never authorized.
- **Caller cannot manufacture equivalent authority** — an off-path authorized registry is rejected by `AUTHORITY_REGISTRY_PATH_NOT_CANONICAL`, and a tampered canonical file changes the fingerprint recorded on the ticket.

This is **not** three independently writable authorities. It is one persisted truth with two
derived views that must agree.

---

## A5 — BLOCKING-2, AUTHORITY PROVENANCE: `AUTHORITY_PROVENANCE_COMPLETE = YES`

The ticket now carries `proposal_authority_source` (hashed), and `__post_init__` plus
`verify_ticket_dict` enforce `_provenance_problem()` on it.

**`PREPARED_ONLY`** (from the authorized fixture registry) records the real lineage:

```json
{"source": "REGISTRY", "resolution": "AUTHORIZED", "registry_path": "…/registry.yaml",
 "registry_fingerprint": "483fe116…bf1059" (64 hex), "strategy_version": "0.0.0",
 "symbols": ["EURUSD"], "cycles": ["POST_ASIAN"], "market_data_modes": ["REAL"],
 "binding_proposal_authority": true}
```

`PREPARED_ONLY` structurally **requires** `source=REGISTRY`, `resolution=AUTHORIZED`,
`binding_proposal_authority=True`, and a 64-char fingerprint.

**`PREPARED_TEST_ONLY`** is pinned to exactly
`{"source": "PIPELINE_TEST_FIXTURE", "strategy_authority": "NONE"}` — an equality check, so
it cannot carry registry fields at all.

Mutation results (all mutations either fail verification or change the hash, as required):

| Mutation | Result |
|---|---|
| fixture source → `REGISTRY` | `verify` **False** + hash change |
| `strategy_authority` → `REGISTRY` | `verify` **False** |
| fixture provenance → full registry-shaped dict | `verify` **False**; constructor raises `ValueError` |
| `registry_fingerprint` tampered (fixture and real) | `verify` **False** |
| `proposal_authority_source` → `{}` / `None` / `"string"` | `verify` **False** |
| real ticket downgraded to fixture provenance | constructor raises `ValueError` |

### Nonblocking limitation — tamper-**evident**, not tamper-**proof**

For a `PREPARED_ONLY` ticket, an actor who can rewrite the *whole* record — mutate
`registry_fingerprint`, then recompute `semantic_fingerprint` **and** `ticket_id` — passes
`verify_ticket_dict` (measured: `RECOMPUTED_TAMPER_ACCEPTED: True`). `_provenance_problem`
can only check the fingerprint is 64 hex chars; it has no external anchor to compare the
*value* against.

Notably the **fixture** path is immune to the same attack, because its provenance rule is
semantic (a fixture source is invalid on `PREPARED_ONLY`) rather than merely structural.

This does not reopen BLOCKING-2. The mission's A5 criterion is "each mutation must
invalidate verification **or change the semantic hash**" — every mutation changes the hash.
The property is inherent to any unsigned self-describing record: full re-forgery requires
code execution, whereas the realistic threat (editing a stored JSON field) is caught.
**Recommended for a later WP, not before freeze:** give `verify_ticket_dict` an optional
`expected_registry_fingerprint`, or sign the ticket.

---

## A6 — OPEN-RISK PROVENANCE: `OPEN_RISK_PROVENANCE_COMPLETE = YES`

`aggregate_risk_policy = "NOT_AVAILABLE"` (the R0 hardcoded literal) is **gone**, replaced by
four real hashed fields.

The decisive R0 defect is fixed — measured on both paths:

```
PREPARED_TEST_ONLY  open_risk 0.0 vs 0.4 -> DIFFERENT semantic hashes
PREPARED_ONLY       open_risk 0.0 -> TKT-54f3e7b37b627f0234a55fdb
                    open_risk 0.4 -> TKT-7ebdbe170ec535b619ec777a
```

| Property | Result |
|---|---|
| `risk_pct`, `max_aggregate_open_risk_pct`, `open_risk_pct`, `risk_policy_fingerprint`, `risk_policy_source` persisted | all present, all hashed |
| Finite validation in the contract | `NaN`, `+Inf`, `-0.1` → `ValueError` on construction |
| Aggregate constraint `open_risk + risk_pct <= max_aggregate` | enforced in `__post_init__` **and** `verify_ticket_dict` |
| Boundary: `open_risk = 0.5` (0.5+0.5 = 1.0) | allowed |
| Boundary: `open_risk = 0.5001` | blocked |
| Mutate `open_risk_pct` post-serialization | `verify` **False**; recompute attempt still **False** (`ticket_id` binds original) |
| Forge `open_risk = 0.9` with fully recomputed hash + ticket_id | **rejected on the provenance rule**, not just the hash — the ceiling is re-checked at verify time |
| Missing `open_risk_pct` (`None`) | `SIZING_BLOCKED` / `AGGREGATE_RISK_UNKNOWN`, no ticket |

That last row is the strongest result: the aggregate ceiling is re-derived during
verification, so a forged over-limit ticket fails even with a perfectly recomputed hash.

```
BLOCKING_2_CLOSED = YES
```

---

## A7 — `OPEN_RISK_SNAPSHOT` PLACEHOLDER: `NOT_IMPLEMENTED_EXPLICITLY`

`open_risk_snapshot_fingerprint = "NOT_AVAILABLE"`, hashed, with the inline comment
*"Caller-supplied open risk; no OpenRiskSnapshot source exists yet (future WP)."*

- **Cannot imply a broker/account query.** AST-level scan of `src/trade_ticket/` finds **no executable reference** to `positions_get`, `positions_total`, `account_info`, `order_send`, or `order_check` (the only textual hits are docstrings describing the *caller's* data source).
- **Grants no authority** — `execution_authority` stays `NONE`.
- **Does not bypass a missing value** — with `open_risk_pct=None` the pipeline still blocks; the placeholder rescues nothing.
- **Owner view distinguishes the two.** The risk block reads `{'risk_pct': 0.5, …, 'open_risk_pct': 0.0, 'open_risk_snapshot_fingerprint': 'NOT_AVAILABLE'}` — the literal sits directly beside the value, so no reader can mistake it for an authoritative snapshot.

No false provenance. Implementation correctly **not** required in this audit.

---

## A8 — PILOT RISK LINEAGE: **PASS (unchanged)**

`risk_pct = 0.5` and `max_aggregate_open_risk_pct = 1.0`, both equal to the cycle pilot
policy (asserted against `risk_policy_from_pilot(PILOTS["POST_ASIAN"])`, not hardcoded).
`config/trading.demo.yaml` confirmed at `risk.risk_per_trade_pct = 1.0` and **unreachable**:
AST check over executable string literals finds no `trading.demo` / `trading.yaml`
reference. Wrong pilot → `RISK_POLICY_PROVENANCE_MISMATCH`; missing policy →
`RISK_POLICY_UNAVAILABLE`.

```
GENERIC_RISK_FALLBACK = NONE
```

---

## A9 — SEMANTIC HASH: **PASS**

- All 7 named R1 authority/risk fields individually mutated → hash changes on every one.
- **Full sweep** over every ticket field except `ticket_id` / `semantic_fingerprint` → `unhashed == []`.
- Same inputs → same hash. **Fresh process** (`subprocess`) → same hash. JSON round trip → verifies.
- Tampering detected on every field; `ticket_id = "TKT-" + fp[:24]` forces an attacker to break two bindings.

---

## A10 — `PREPARED_TEST_ONLY` ISOLATION: **PASS (strengthened in R1)**

R1 inverts the fixture contract, which is a genuine improvement: the test path now **refuses
to accept an authority object at all**.

| Probe | Result |
|---|---|
| Fixture path given a registry authority object | `AUTHORITY_NOT_ALLOWED_IN_PIPELINE_TEST` |
| Fixture binding with `proposal_authority=True` | `FIXTURE_BINDING_CLAIMS_AUTHORITY` |
| Fixture binding with `execution_authority="DEMO_AUTHORIZED"` | `FIXTURE_BINDING_CLAIMS_AUTHORITY` |
| Relabel fixture → `PREPARED_ONLY` (replace / dict / full hash+id recompute) | all rejected — the provenance rule forbids fixture source on `PREPARED_ONLY` |
| Real registry inspection | no entry carries `proposal_authorization`; `ST_ASIAN_SWEEP_5R_V1` remains `demo_authorized: false`, `live_authorized: false` |

No test authority implies `proposal_authorized`, `demo_authorized`, or `live_authorized` for
any real strategy, and no research attribution to `ST_ASIAN_SWEEP_5R_V1` is possible.

---

## A11 — CAPABILITY ZERO: **NOT_REACHABLE (all four)**

- **Fresh-interpreter import graph:** importing `trade_ticket.ticket` reaches none of `backtesting`, `smartmoneyconcepts`, `vectorbt`, `freqtrade`, `execution`, `authorization`, `ticket_delivery`, `owner_decision`, `strategy_manager`.
- **Runtime instrumentation** — `order_send`, `order_check`, `positions_get`, `positions_total`, `account_info`, `initialize`, `login`, `shutdown` all replaced with recording stubs, then four paths exercised (success, sizing failure, policy failure, authority failure): **`calls == []`**.
- `TradeTicket`'s only public members remain `semantic_fingerprint` and `to_dict`.
- `PREPARED_ONLY` remains non-executable: `execution_authority = "NONE"` is a constructor invariant, and proposal authority is explicitly *not* execution authority (verified on the authorized ticket).

---

## A12 — SIZING REGRESSION: **NONE**

`src/trade_ticket/sizing.py` blob is **identical** R0 → R1 (`febaee7dc49e37c4571b8bd3aaccdd03f7707614`),
so the R0 conclusion carries over unchanged, including byte-identity with historical
`1a8e7c5:src/execution/risk.py`. Geometry re-confirmed, numerically identical to R0:

```
EURUSD LONG/SHORT  vol=0.38  risk=49.4000
GBPUSD LONG/SHORT  vol=0.38  risk=49.4000
USDJPY LONG/SHORT  vol=0.49  risk=49.0002
```

```
SIZING_REGRESSION = NONE   (HISTORICAL_AG_REUSE_ACCEPTABLE preserved)
```

---

## A13 — REAL STRATEGY NEGATIVE PATH: **PASS**

With the **genuine** current registry and the **genuine** resolved binding:

```
REAL_STRATEGY_DENIAL: NO_PROPOSAL_AUTHORITY
  ('BINDING_PROPOSAL_AUTHORITY_FALSE', 'PROPOSAL_AUTHORITY_FIELD_ABSENT')
```

Both halves of the conjunction deny independently — the fail-closed behaviour does not
depend on either one alone. No `PREPARED_ONLY` ticket is produced.

In an **isolated test-only registry fixture**, an authorized `ST_ASIAN_SWEEP_5R_V1` with no
strategy-owned targets gives exactly the expected later denial:

```
AUTHORIZED_NO_TARGETS: INCOMPLETE_TRADE_PLAN ('TARGETS_NOT_STRATEGY_OWNED',)
```

This is the proof the mission asked for: the authority remediation is demonstrably
functional (it can pass) while **no real economic authority was granted** — the real
registry is untouched and the strategy is still stopped by its own open contract gap. Not
"fixed", correctly.

---

## A14 — REGRESSION

| Suite | Count | Classification |
|---|---|---|
| Candidate focused tests | **112 passed** (R0 was 42; +70) | — |
| Auditor independent R1 probes | **79 passed** (74 + 5) | — |
| Full repository regression at R1 | **772 passed, 4 skipped, 1 failed** | — |
| The 1 failure: `test_crypto_opportunity_scanner.py::test_actual_api_route_is_read_only_candidate_projection` | `ModuleNotFoundError: No module named 'api.app'` | **pre-existing baseline / environment** — reproduced identically at parent `e7dd985c` and, in the prior audit, at `76348c72` |

**No R1 regression.** No failure hidden. Two initial red results in my own probe runs were
bugs in my probes (a substring match hitting a docstring); both fixed, neither indicated a
candidate defect.

---

## A15 — FINAL CLASSIFICATION

```
CLASSIFICATION = TRADETICKET_VERTICAL_SLICE_AUDIT_PASS

AUDITED_SHA  = 1564769ac3bd43a3b5aceaa37aa85cc662906e95
AUDITED_TREE = 54fa8e696e04be404414a9a8c366341091405f0e
PARENT_SHA   = e7dd985c11e00150f18925d993bca6f2f5ef53c6

BLOCKING_1_CLOSED = YES  (binding AND registry authority must agree on strategy, version,
                          symbol, cycle, market-data mode, source, canonical path and
                          registry fingerprint; 14/14 negative probes block; positive
                          control reaches PREPARED_ONLY, so the gate is not vacuous)
BLOCKING_2_CLOSED = YES  (proposal_authority_source + risk_pct +
                          max_aggregate_open_risk_pct + open_risk_pct +
                          open_risk_snapshot_fingerprint all persisted, hashed and
                          re-validated; open_risk 0.0 vs 0.4 now yields different hashes
                          on BOTH the fixture and the real PREPARED_ONLY path)

AUTHORITY_SCHEMA               = CONSISTENT_SINGLE_CHAIN
AUTHORITY_PROVENANCE_COMPLETE  = YES
OPEN_RISK_PROVENANCE_COMPLETE  = YES
OPEN_RISK_SNAPSHOT             = NOT_IMPLEMENTED_EXPLICITLY
GENERIC_RISK_FALLBACK          = NONE
PREPARED_TEST_ONLY_ISOLATION   = PASS (strengthened: fixture path refuses any authority
                                 object, and a fixture binding claiming authority is denied)
SIZING_REGRESSION              = NONE (sizing.py blob identical; EURUSD/GBPUSD/USDJPY
                                 geometry numerically unchanged)
CAPABILITY_ZERO                = INTACT
REAL_STRATEGY_PROPOSAL_AUTHORITY = NONE (registry untouched; ST_ASIAN_SWEEP_5R_V1 denied by
                                 BINDING_PROPOSAL_AUTHORITY_FALSE + PROPOSAL_AUTHORITY_FIELD_ABSENT)

BROKER_ORDER_CHECK_REACHABILITY       = NOT_REACHABLE
BROKER_ORDER_SEND_REACHABILITY        = NOT_REACHABLE
POSITIONS_GET_REACHABILITY            = NOT_REACHABLE
OTHER_EXECUTION_MUTATION_REACHABILITY = NOT_REACHABLE
  (static AST + fresh-interpreter import graph + runtime stubs across 4 paths; calls == [])

FOCUSED_TESTS     = 112 passed (candidate)
INDEPENDENT_TESTS = 79 passed (auditor-written, A3-A13)
REGRESSION_TESTS  = 772 passed, 4 skipped, 1 pre-existing environment failure
                    (reproduced at parent e7dd985c -> NOT an R1 regression)

SEALED_OOS_ECONOMIC_ACCESS = NONE (untouched; not opened)
DEMO_TRADE_AUTHORITY       = NONE
LIVE_AUTHORITY             = NONE
```

### Nonblocking findings (record; do not fix before freeze)

1. **Tamper-evident, not tamper-proof.** A full re-forge of a `PREPARED_ONLY` record
   (mutate `registry_fingerprint`, recompute hash *and* `ticket_id`) passes
   `verify_ticket_dict`, because verification has no external anchor for the fingerprint
   value. Meets the A5 criterion (the hash does change) and is inherent to unsigned
   self-describing records; the fixture path is immune by construction. Future WP: optional
   `expected_registry_fingerprint` argument to `verify_ticket_dict`, or ticket signing.
2. **`origin/main` advanced to `accf0637`** (unrelated MCP work) while R1 was branched from
   `4bbba319`. No candidate content merged; a rebase before freeze is a routine, apparently
   conflict-free step.
3. `proposal_authority_source.registry_path` records the path string. Under canonical
   operation this is the relative `strategies/registry.yaml` (enforced by
   `AUTHORITY_REGISTRY_PATH_NOT_CANONICAL`); only monkeypatched test runs record an
   absolute path. Provenance hygiene note only.
4. `OpenRiskSnapshot` sourcing, Canonical Instrument Registry, owner-confirm state machine,
   Demo and Live execution remain correctly unimplemented and unclaimed.

---

## A16 — RECOMMENDATION

**FREEZE `AG_TRADE_TICKET_V1`** at `1564769ac3bd43a3b5aceaa37aa85cc662906e95`.

The contract now carries everything needed to reconstruct *what authorized it* and *under
what risk context* — the two gaps that blocked the freeze. Do **not** add further TradeTicket
features first; every nonblocking item above is additive and none requires a schema break.

The next mission, **separate and after the freeze**, should be
**`CANONICAL_INSTRUMENT_REGISTRY_V1`** — starting with **EURUSD on VT Markets Demo**, and
explicitly designed to extend to GBPUSD, USDJPY and crypto instruments. Not started here.

---

**Constraints honoured.** Candidate not modified, not merged, not cherry-picked; audit
worktrees verified pristine and removed; `origin/main` not merged and not written by me;
no fixes implemented; no strategy authority granted; no architecture redesign; no strategy
research; `SEALED_OOS` not opened economically; no broker contact.
This document authorizes nothing.
