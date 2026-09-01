# ST_LARGE_SMC_V1 — C11 Target Model Resolution (2026-09-01)

Status: **OWNER_DECISION_REQUIRED**. C11 remains `UNRESOLVED_CONTRACT`; no target logic
was implemented, no strategy YAML field was signed, no backtest was run.

## The question

What defines the target for `ST_LARGE_SMC_V1`? Kept explicitly separate from setup
invalidation, trade stop-loss, R:R filtering, position management, and partial profit —
none of those are resolved or touched here.

## AG existing implementation check

`SMCEntryCombinationResult` (composer output) and `composer.py` — confirmed, no target
field exists anywhere in either. `AG_TARGET_IMPLEMENTATION = MISSING` at the
Large-SMC/composer level, as expected from the prior reconciliation phase.

However, two closely-matching, unadopted pieces exist elsewhere in AG:

- `src/liquidity/hierarchy.py::InducementCandidate` — already computes an EXTERNAL-tier,
  `UNSWEPT`, same-side liquidity level beyond current price, named `target`/`target_id`
  in the code itself (`hierarchy.py:117-122`, `classify_roles` → `ROLE_TARGET`). Built to
  validate M1's inducement candidates, not as a strategy-level profit target — but the
  underlying concept (next unswept external liquidity, on-side, beyond current price) is
  exactly what both external research sources describe. The module's own docstring
  states it deliberately does not rank/select a single best target when several qualify
  (`hierarchy.py:106-107`).
- `src/entry_confirmation/entry_array.py` / `engine_v2_1.py` (M3's engine) —
  `EntryArrayContext.target_liquidity_reference: Optional[float] = None`: a caller-
  supplied, never-computed, never-gated pass-through field. A pre-existing seam waiting
  for exactly this kind of value, not new capability.
- M1's own confirmation logic (`m1_character_change_inducement.py`) consumes
  `InducementCandidate` but only for inducement *validation*, not for surfacing
  `target` onward as its own output.
- M2 (`m2_supply_demand_shift.py`) — no target-shaped field found at all.

## E-model / M-model target evidence

| Model | Target evidence | Classification |
|---|---|---|
| E1 | none — D1 gap reference + H1 reaction only | NONE |
| E2 | none — H1 POI reference + reaction only | NONE |
| E3 | none — liquidity *swept*, not a forward destination | NONE (context/location only, not a target) |
| M1 | `InducementCandidate.target` present but used only for candidate *validation*, not surfaced as M1's own output field | TARGET_CANDIDATE (indirect, via `liquidity.hierarchy`) |
| M2 | none | NONE |
| M3 | `target_liquidity_reference` slot exists on `EntryArrayContext`, unused (`None` unless caller supplies it) | TARGET_CANDIDATE (unused seam) |

No E-model or M-model computes or emits a target today. `liquidity.hierarchy` is the
one AG module that already computes the right *shape* of value, generically (not tied
to any specific E or M), which is why the recommended candidate below treats target as
a **global**, not variant-specific, rule.

## Liquidity capability reuse

AG's `liquidity` package already provides deterministic `EXTERNAL`/`INTERNAL` tier
classification, `BUY_SIDE`/`SELL_SIDE` sides, and `UNSWEPT`/`SWEPT`/`RECLAIMED`/
`CONSUMED` status (`liquidity/hierarchy.py`, `liquidity/status.py`) — this is precisely
the deterministic liquidity output C11 needs to *consume*, not a new liquidity model to
build. No new liquidity detector is proposed anywhere in this resolution.

## Inducement vs. target liquidity (preserved)

`liquidity.hierarchy` already keeps this distinction structurally: `ROLE_INDUCEMENT_CANDIDATE`
(internal, gets swept first) vs. `ROLE_TARGET` (external, the destination) are
mutually-exclusive role assignments on the same `scoped_levels` set
(`hierarchy.py:126-139`). Nothing in this resolution collapses that distinction; it is
the evidentiary basis for keeping "target" and "inducement" as separate concepts here.

## Research evidence (smc-lss-platform, reused from the prior UC-001 phase, not re-fetched)

`ST_C1_TARGET_MODEL` (G9): priority 1 = nearest unswept external liquidity beyond entry;
priority 2 = nearest unswept M5 swing extremum; `REJECT_NO_TARGET` otherwise; never a
synthetic fixed-R substitute. `V3_6_TARGET_MODEL`: primary = nearest unswept external
liquidity beyond entry (`primary_search_lookback_h1_bars=100`); fallback = nearest
unswept M5 swing extremum; `no_target_found: REJECT_NO_TARGET`; `tp1: entry +/- 1R` is a
*management* checkpoint (BE-move trigger), not the target itself — kept separate per the
C11/partial-profit distinction (spec section 30). Convergence = `CONVERGENT`. Authority =
`RESEARCH_REFERENCE` (both), not `AG_STRATEGY_RULE` — owner adoption still required per
this project's evidence hierarchy even though the two sources agree completely.

## Target evidence matrix

| Source | Target concept | Authority level | Deterministic | Implemented | Large-SMC-specific | Conflict | Reuse status |
|---|---|---|---|---|---|---|---|
| Current Large-SMC spec | none signed | 2 | — | — | yes | — | `MISSING` |
| `ST_LARGE_SMC_V1.yaml` | `profit_targets: UNSIGNED` | 2 | — | — | yes | — | `MISSING` |
| E1/E2/E3 | none | 3 | — | — | no | — | `MISSING` |
| M1 | `InducementCandidate.target` (indirect) | 3 | yes | yes (as inducement validator, not target emitter) | no (generic liquidity) | no | `ADAPTER_CANDIDATE` |
| M2 | none | 3 | — | — | no | — | `MISSING` |
| M3 | `target_liquidity_reference` slot (unused) | 3 | n/a (pass-through only) | partially (field exists, never computed) | no (generic entry-array) | no | `ADAPTER_CANDIDATE` |
| AG liquidity capability (`hierarchy.py`, `status.py`) | EXTERNAL/UNSWEPT same-side liquidity | 3 | yes | yes | no (generic) | no | `ADAPTER_CANDIDATE` (strongest) |
| AG market-structure capability | swing highs/lows, generic | 3 | yes | yes | no (generic) | no | `ADAPTER_CANDIDATE` (fallback-tier only) |
| Stage1/Stage2 | no target concept (research pipeline is entry-only) | 3 | — | — | no | — | `MISSING` |
| Previous AG Large-SMC research | none beyond the prior spec drafts | 2 | — | — | yes | — | `MISSING` |
| ST-C1 v1.1.0 G9 | nearest unswept external, fallback nearest M5 swing | 4 | yes | n/a (external repo) | yes (for ST-C1, not AG) | no (converges with v3.6) | `RESEARCH_REFERENCE` |
| `v3.6` | same shape as ST-C1 | 4 | yes | n/a (external repo) | yes (for v3.6, not AG) | no | `RESEARCH_REFERENCE` |

## Candidate matrix

**CANDIDATE_1 — `MINIMAL_AG_ONLY`**
- TARGET_TYPE: `OPPOSING_EXTERNAL_LIQUIDITY`
- TARGET_SOURCE: `liquidity.hierarchy`-style EXTERNAL-tier, `UNSWEPT` liquidity level
- LONG_RULE: nearest qualifying `BUY_SIDE` `EXTERNAL`/`UNSWEPT` liquidity level above
  entry
- SHORT_RULE: nearest qualifying `SELL_SIDE` `EXTERNAL`/`UNSWEPT` liquidity level below
  entry
- SELECTION_RULE: nearest (only rule any source states explicitly; AG's own code does
  not rank, so this piece would still be adopted from the external convergence, not
  invented)
- STATIC_OR_DYNAMIC: `STATIC` (selected at qualification; no evidence anywhere supports
  dynamic re-targeting — spec section 26's default when no evidence exists)
- NO_TARGET_BEHAVIOR: `NO_TRADE` (reusing the existing public state vocabulary; maps
  onto external sources' `REJECT_NO_TARGET`)
- AG_IMPLEMENTATION_REUSE: HIGH — `liquidity.hierarchy`'s existing role-classification
  logic generalizes directly; would need a `THIN_ADAPTER` to call it independent of
  M1's inducement-candidate framing
- NEW_CAPABILITY_REQUIRED: LOW
- SOURCE_AUTHORITY: AG (level 3) for the mechanism; convergent with ST-C1/`v3.6`'s
  primary tier
- CONFLICTS: none
- OWNER_DECISION_REQUIRED: yes (adoption, not invention)

**CANDIDATE_2 — `HYBRID_WITH_STRUCTURAL_FALLBACK`** (superset of Candidate 1)
- Same primary tier as Candidate 1, plus: when no qualifying external liquidity exists,
  fall back to the nearest LTF (M5) structural swing extremum beyond entry — matching
  both ST-C1 G9 and `v3.6` exactly, which *both* specify this fallback rather than
  treating primary-tier failure as immediately terminal.
- NO_TARGET_BEHAVIOR: `NO_TRADE`, only after *both* tiers fail (matches
  `REJECT_NO_TARGET` precisely)
- AG_IMPLEMENTATION_REUSE: MEDIUM — primary tier as Candidate 1; fallback tier needs a
  new (but small) query against AG's already-generic swing-detection capability
  (`market_structure`), not new SMC theory
- NEW_CAPABILITY_REQUIRED: LOW-MEDIUM
- SOURCE_AUTHORITY: AG (primary tier) + `CONVERGENT_RESEARCH_CANDIDATE` (fallback tier,
  ST-C1 + `v3.6` agree completely)
- CONFLICTS: none
- OWNER_DECISION_REQUIRED: yes

**Rejected without a candidate row** (per spec section 9/21, no evidence supports
these for `ST_LARGE_SMC_V1`): `FIXED_R_MULTIPLE`, any imported Session `5R`/`3R`/
`40:60`/`75:25` ratio, any ATR-distance or fixed-pip target. None appear in any AG or
approved-research Large-SMC source.

## Recommendation

**Evidence favors Candidate 2 (Hybrid)** if the owner wants the fuller, externally-
validated model; **Candidate 1 (Minimal)** if the owner prefers adopting only what AG
itself already computes, deferring the fallback tier to a later increment. Both are
legitimate; this is not resolved automatically per spec section 39 (neither candidate is
an *existing, explicitly Large-SMC* AG contract — both require adoption of a generic
capability, which is exactly the case section 39 reserves for owner decision).

1. Candidate 2 is the complete model both independent external sources actually specify
   — adopting only the primary tier (Candidate 1) would diverge from *either* source's
   own definition of "done," not converge with them.
2. Both candidates reuse AG's own deterministic liquidity capability for the primary
   (and highest-confidence) tier — no new liquidity or structure detector is proposed.
3. Direction rules (`LONG`→`BUY_SIDE` above entry, `SHORT`→`SELL_SIDE` below entry) are
   grounded directly in `LiquiditySide` and `_is_between`'s existing logic, not invented.
4. Target selection ("nearest") is stated identically by both external sources — a
   genuine convergence, not a single-source guess.
5. Global (not E/M-variant-specific) scope is supported: the mechanism only needs
   direction + current price, independent of which E or M produced the candidate.

## Dependencies

- `C11_DEPENDS_ON_C10`: **NO** — both candidates are structurally independent of stop
  distance; entry price, direction, and liquidity levels are sufficient inputs.
- `C12_FOLLOWUP_REQUIRED`: **YES** — if the target liquidity is itself swept/consumed
  before or during activation, that plausibly affects candidate expiry/invalidation;
  not resolved here, flagged for the C12 residual-semantics phase.
- `C14_duplicate_followup`: target identity (which external level was selected) may or
  may not matter for future duplicate/re-entry comparison; not resolved here, flagged
  for the C14 phase.

## Non-regression / authority

`AG_TRADE_ASSISTANT_V1_0_2`, `ST_ASIAN_SWEEP_5R_V1 v1.1.1`, `src/entry_confirmation/`,
`composer.py`, Stage1, Stage2, liquidity engine, market structure, supply/demand, trade
management, portfolio, risk, execution, and MT5 code were all read-only this phase —
none modified. `strategies/ST_LARGE_SMC_V1.yaml` was **not** touched (C11 ends
`OWNER_DECISION_REQUIRED`, so nothing was written into it as authority, per phase
policy). `actionable_READY/portfolio/risk_sizing/proposal/execution` all remain
`BLOCKED`; `order_check=0`, `order_send=0`.

## Files changed

- `docs/specs/LARGE_SMC_V1_SPEC.md` §16 — evidence and candidate summary recorded;
  status remains `UNRESOLVED_CONTRACT`/`OWNER_DECISION_REQUIRED`, not resolved.
- `docs/status/ST_LARGE_SMC_V1_C11_TARGET_MODEL_RESOLUTION_STATUS.md` — this document.

`strategies/ST_LARGE_SMC_V1.yaml` unchanged (no legitimate resolution occurred; the
stale `purpose:` narrative-sync from the prior phase's `STALE_NARRATIVE_CLEANUP_DEFERRED`
note remains deferred for the same reason — nothing else in the file was touched to
justify bundling it in).

## Tests

None run — no production code or YAML changed this phase.
