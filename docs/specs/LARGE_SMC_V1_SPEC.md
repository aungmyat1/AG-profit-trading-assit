# ST_LARGE_SMC_V1 — Research Strategy Specification

Status: **RESEARCH_DRAFT / ADVISORY_ONLY** &nbsp; Version: **1.0.6** &nbsp; Authority: `strategies/ST_LARGE_SMC_V1.yaml`

Specification phase: `ST_LARGE_SMC_V1_STRATEGY_SPECIFICATION` (2026-09-01), extended by
`ST_LARGE_SMC_V1_RESOLVE_UC_001_TIMEFRAME_ROLES`, `..._3X3_VARIANT_AUTHORITY_
RECONCILIATION`, `..._RESOLVE_C11_TARGET_MODEL`, `..._C11_CONTRACT_FINALIZATION`,
`..._RESOLVE_C12_EXPIRY`, `..._RESOLVE_C14_DUPLICATE_REENTRY`,
`..._C14A_CANDIDATE_OCCURRENCE_IDENTITY`, and `..._C14B_OCCURRENCE_IDENTITY_HARDENING`
(all 2026-09-01). This document extracts, reconciles, and freezes the smallest
deterministic Large-SMC contract actually supported by AG Profit Trading's own evidence
and its approved research resource (`smc-lss-platform`). It is a specification artifact
only — no engine or workflow exists; `strategies/ST_LARGE_SMC_V1.yaml` carries only
`CONTRACT_ONLY` fields, though `candidate_identity`'s identity layer is now backed by
real, additive, unit-tested code in `src/entry_confirmation/` and `src/proposals/` (not
wired into any engine, proposal, or execution path). See
`docs/status/ST_LARGE_SMC_V1_STRATEGY_SPECIFICATION_STATUS.md`,
`..._3X3_VARIANT_AUTHORITY_RECONCILIATION_STATUS.md`, `..._C11_CONTRACT_FINALIZATION_
STATUS.md`, `..._C12_EXPIRY_CONTRACT_RESOLUTION_STATUS.md`,
`..._C14_DUPLICATE_REENTRY_CONTRACT_RESOLUTION_STATUS.md`,
`..._C14A_CANDIDATE_OCCURRENCE_IDENTITY_STATUS.md`, and
`..._C14B_OCCURRENCE_IDENTITY_HARDENING_STATUS.md` for the phase reports.

This is a separate strategy family. It does not modify, extend, or operate as a mode of
`ST_ASIAN_SWEEP_5R_V1 v1.1.1`, `SMC_3R_V1`, `ST_LIQUIDITY_SWEEP_RETEST_V1`, or
`ST_HIGH_RR_LIQUIDITY_MSS_V1`. Shared analysis capabilities may supply evidence; they do
not share strategy authority or validation evidence.

## 1. Strategy identity

`strategy_id=ST_LARGE_SMC_V1`, `version=1.0.4`, `family=SMART_MONEY_CONCEPT`,
`role=LARGE_SMC_OPPORTUNITY`, `status=RESEARCH_DRAFT`.

## 2. Authority / status

`active=false`, `research=true`, `advisory_only=true`. `proposal_generation_authorized`,
`demo_authorized`, `live_authorized` = `false`. No engine exists (`registry.yaml:
engine=NOT_IMPLEMENTED`); zero references to `ST_LARGE_SMC_V1` exist anywhere in `src/`.

## 3. Objective

The hypothesis: larger FX opportunities may arise when price reaches a predeclared
higher-timeframe SMC location and subsequently produces a causal, lower-timeframe
liquidity-event-to-structure-shift confirmation sequence. "Large" refers to the intended
structural scope of the opportunity (higher-timeframe context), not to position size —
risk sizing remains a separate, downstream authority and is not specified here.

## 4. Source authority (evidence hierarchy used below)

1. Explicit owner-frozen Large-SMC rule (none exist yet).
2. This project's own `ST_LARGE_SMC_V1.yaml` fields that are already signed (not
   `UNSIGNED`).
3. AG's own deterministic implementations with structurally matching semantics —
   principally `src/entry_confirmation/e1_daily_gap_reaction.py`,
   `e2_h1_poi_reaction.py`, `e3_liquidity_sweep.py` (HTF event/location detection) and
   `m1_character_change_inducement.py`, `m2_supply_demand_shift.py`,
   `m3_sweep_drop_pump.py` (LTF confirmation/entry), frozen and golden-validated via
   `src/historical_replay/stage1.py` / `stage2.py` — even though none of these modules
   were built with `ST_LARGE_SMC_V1` cited as their consumer.
4. `smc-lss-platform` (`strategies/candidates/ST-C1_v1.1.0.yaml`, `specs/v3.6.yaml`),
   research reference only.
5. `ST-C3` (state-machine/rejection-code structure only — its H4/M15/M3 timeframe
   scheme and active trading rules are explicitly excluded per the resource map).
6. Related independent strategies (`ST_LIQUIDITY_SWEEP_RETEST_V1`, `SMC_3R_V1`).
7. Generic SMC concepts — lowest authority; never used to silently resolve a conflict.

## 5. Terminology

`context` = HTF narrative/structure evidence a candidate forms within. `location`/`POI`
= the price zone a reaction is expected from. `activation` = the transition from passive
context to an active, tracked candidate. `confirmation` = the LTF evidence required
after activation before an entry array exists. `entry array` = the concrete
price reference an order would be built from. `RESEARCH_QUALIFIED` = the highest
attainable state while `status=RESEARCH_DRAFT`; it is never `READY` in the actionable
sense used by an `ACTIVE` strategy.

## 6. Market universe (C01) — `PARTIALLY_RESOLVED`, non-blocking

`asset_class=FX` is signed in `ST_LARGE_SMC_V1.yaml`. `instruments=UNSIGNED`. The
session-strategy universe (EURUSD/GBPUSD) is not inherited automatically (`AGENTS.md`
authority rule). `smc-lss-platform` ST-C1 v1.1.0 uses `[EURUSD, GBPUSD, XAUUSD]`
(forex+metals) as a research reference only — `RESEARCH_REFERENCE`, not adopted.
Crypto is explicitly out of scope (no venue/data contract). → **UC-016** (non-blocking).

## 7. Timeframe roles (C02) — `RESOLVED_BY_OWNER`

**UC-001 is resolved.** Owner decision (2026-09-01,
`docs/status/ST_LARGE_SMC_V1_UC_001_TIMEFRAME_DECISION.md`): **Option B —
`ADOPT_FROZEN_AG_D1_H1_M5`.** `ST_LARGE_SMC_V1.yaml`'s `timeframe_responsibilities` was
updated accordingly (`D1=MACRO_EVENT_REFERENCE`,
`H1=STRUCTURE_LOCATION_LIQUIDITY_REACTION`, `M5=CONFIRMATION_AND_ENTRY`,
`H4=OPTIONAL_EVIDENCE_ORIGIN_ONLY`, `M15=NOT_REQUIRED`, `M1(timeframe)=UNSIGNED`).

Primary architecture: **D1 / H1 / M5**, matching AG's own frozen, golden-validated
E1/E2/E3 (HTF context) + M1/M2/M3 (LTF confirmation/entry) pipeline
(`src/entry_confirmation/`) exactly — see §32 (3×3 reconciliation) for the full mapping.
H4 is **not** a primary or mandatory layer; it survives only as an optional evidence
origin already supported by E3 (a caller-supplied `LiquidityLevel` may carry
`timeframe="H4"`, copied verbatim — `e3_liquidity_sweep.py:7-11,58`). M15 has no role at
all — no AG or approved-external evidence ever assigned it Large-SMC semantics.

**Naming note:** the yaml's `M1` timeframe key (1-minute candles) is unrelated to the
`M1` confirmation *maneuver* model (`m1_character_change_inducement.py`) referenced
throughout §16 — the names coincide, the concepts do not.

## 8. Directional model (C03) — `RESOLVED_FROM_EXISTING_RESOURCE (E-specific)`

UC-001 resolved to Model B, so the contingency is lifted. AG's `EConditionResult`
(emitted by each of E1/E2/E3) already carries a computed `direction` field — a working,
frozen, `REUSE_EXISTING_AG` implementation. Per §32, direction is **E-specific, not
global**: each E-model derives it from its own detector (E1 from the D1 gap's implied
bias, E2 from the H1 POI's bullish/bearish role, E3 from the swept liquidity side), and
the composer requires `E.direction == M.direction` before a combination forms
(`composer.py:64`) — M-models never independently invent a direction. ST-C1 G1's
unified HH/HL+BOS/CHoCH rule (`RESEARCH_REFERENCE`) was not adopted; it is not needed
now that a working AG implementation exists. → **UC-002, RESOLVED** (superseded by
reconciliation; see §32).

## 9. Structural context (C04) — `RESOLVED_FROM_EXISTING_RESOURCE (E-specific)`

Contingency lifted. AG's E1/E2/E3 already implement concrete structural-context
detectors — D1-gap-reaction (E1), H1-POI-reaction (E2), H1-sweep-reclaim (E3) — each
with its own structural evidence, not a single global rule. `location_model`'s signed
`CANDIDATE_INPUT` category list (external/internal liquidity, premium/discount, OB, FVG,
supply/demand, protected highs/lows) maps onto these E-specific implementations rather
than a uniform qualification rule; ST-C1 G2/G3's dealing-range model was not adopted.
→ **UC-003, RESOLVED** (E-specific; see §32).

## 10. Location / POI (C05) — `RESOLVED_FROM_EXISTING_RESOURCE (E-specific)`

Contingency lifted. E1's location = the D1 gap zone; E2's location = the H1 POI from
`src/entry_confirmation/poi.py`'s already-signed inventory; E3's location = the swept
liquidity level (caller-supplied, any of H1/H4/D1 origin). Each E-model owns its own
location definition — `poi.py` is `REUSE_EXISTING_AG` for E2 specifically, not a
strategy-wide POI rule. ST-C1 G5's ATR-sized FVG/OB/D1-gap definition
(`RESEARCH_REFERENCE`) was not adopted. → **UC-004, RESOLVED** (E-specific; see §32).

## 11. Liquidity requirement (C06) — `PARTIALLY_RESOLVED (variant-specific)`

Mandatory-yes remains signed at the strategy level, but liquidity's role is
**variant-specific, not global**: E3 requires a liquidity sweep with `RECLAIMED` status
(`src/liquidity/status.py`, `REUSE_EXISTING_AG`) as its core structural test; M1 requires
an inducement sweep (`src/liquidity/hierarchy.py::InducementCandidate`,
`REUSE_EXISTING_AG`) distinct from E3's target-liquidity sweep; E1/E2/M2/M3 do not
require a liquidity sweep at all (E1/E2 gate on a displacement-qualifying reaction
candle instead, M2 gates on zone invalidation, M3 requires its own HTF sweep+reclaim).
Exact wick-ratio thresholds remain `v3.6`-only (`RESEARCH_REFERENCE`,
`sweep_wick_ratio_min=0.5`/`reaction_wick_ratio_min=0.4`), not yet AG-coded as explicit
parameters. → **UC-005, PARTIALLY_RESOLVED** (which cells require liquidity is now
known; exact thresholds remain open — see §32).

## 12. Activation event (C07) — `RESOLVED_FROM_EXISTING_RESOURCE (E-specific)`

Contingency lifted. AG's `EntryModelState` enum (`entry_models_v1.py:88-103`) gives an
explicit, already-implemented activation pathway per E-model:
`SCANNING_CONTEXT → WAITING_HTF_TOUCH → WAITING_H1_REACTION → HTF_QUALIFIED`.
`HTF_QUALIFIED` (equivalently, `EConditionResult.eligible_for_confirmation == True`) is
the activation boundary the prior draft asked for — it is the precise point where
"context exists" becomes "candidate is active and eligible for LTF confirmation."
→ **UC-006, RESOLVED** (see §32).

## 13. Entry confirmation (C08) — `RESOLVED_FROM_EXISTING_RESOURCE (M-specific)`

Contingency lifted. The signed mandatory pair (MSS/CHoCH, displacement) is implemented,
**M-specifically**, by all three maneuvers: M1 = inducement sweep → CHoCH →
displacement → entry array → retracement; M2 = opposing-zone invalidation → new zone →
displacement → entry array; M3 = HTF sweep+reclaim → CHoCH → displacement → IFVG → 50%
pullback. `EntryModelState`'s `WAITING_M5_CONFIRMATION → WAITING_M5_ENTRY → READY` path
is the shared lifecycle shape across all three, with model-specific evidence underneath.
Entry-array requirement (`entry_array` was `UNSIGNED`) is now resolved: every M-model
requires one (FVG/OB for M1, FVG-or-OB "Gold Zone" for M2, IFVG for M3).
→ **UC-007, RESOLVED** (M-specific; see §32).

## 14. Entry model (C09) — `RESOLVED_FROM_EXISTING_RESOURCE (M-specific)`

Contingency lifted; **UC-008 is resolved** (owner selected Model B for UC-001, and the
prior spec's recommendation for UC-008 was contingent on exactly that choice — see §31).
Entry timeframe = M5 (`CONFIRMATION_TIMEFRAME = EXECUTION_TIMEFRAME = "M5"`,
`entry_models_v1.py:56-57`); entry reference is M-specific:
M1 = pullback/entry-array midpoint (`(entry_array_low + entry_array_high) / 2`), M2 =
FVG-or-OB midpoint ("Gold Zone"), M3 = the IFVG gap's own reference level
(`m3.gap`/`m3.entry_level`). ST-C1's single next-bar-open market-entry model was not
adopted. → **UC-008, RESOLVED** (M-specific; see §32).

## 15. Invalidation / stop (C10) — `PARTIALLY_RESOLVED`

The *candidate-invalidation* half is resolved and reused: `SMCEntryCombinationResult`
(`entry_models_v1.py:161-169`) carries `invalidation` (`INVALIDATED`/`EXPIRED` state),
`invalidation_price`, `invalidation_source_type`, `invalidation_reason`, and
`invalidation_trigger`, copied verbatim from the underlying M-model's own fields —
`REUSE_EXISTING_AG`. Per spec section 29, **this is research-candidate invalidation,
not a broker stop-loss distance** — the two remain explicitly distinct here; no project
resource defines an actionable SL. ST-C1 G7's unified stop rule and `v3.6`'s per-model
stop formulas (both `RESEARCH_REFERENCE`) remain un-adopted candidates for the
*SL-distance* half specifically. → **UC-009, PARTIALLY_RESOLVED** (invalidation
mechanism reused; SL-distance formula still open).

## 16. Target model (C11) — `RESOLVED_BY_OWNER`, `C11_IMPLEMENTATION_SPEC=COMPLETE`

**Owner decision (2026-09-01): Candidate 2, `HYBRID_WITH_STRUCTURAL_FALLBACK`.** Full
deterministic derivation:
`docs/status/ST_LARGE_SMC_V1_C11_CONTRACT_FINALIZATION_STATUS.md`; contract recorded in
`strategies/ST_LARGE_SMC_V1.yaml`'s `target_model:` block (`CONTRACT_ONLY`,
`implementation: NOT_IMPLEMENTED`). Strategy version bumped `1.0.0 → 1.0.1`
(`docs/VERSION_HISTORY.md`: "targets" is an explicit strategy-version-bump trigger).

Frozen, all by reuse of already-existing AG mechanisms — no new detector, no new swing
algorithm:

- **Anchor**: `SELECTED_M_MODEL_CANDIDATE_ENTRY_PRICE` (`SMCEntryCombinationResult.
  entry_price`), decision timestamp reuses the M-model's own entry-availability timing —
  no lookahead, no new field.
- **Primary tier** — `OPPOSING_EXTERNAL_UNSWEPT_LIQUIDITY` on **M5** (not H1 — confirmed
  from `historical_replay/stage2.py:158`'s own
  `external_swing_liquidity(symbol, "M5", tiers.external, m5_candles)` wiring, the exact
  timeframe the frozen research pipeline already uses). Candidate universe =
  `market_structure.tiers.StructureTier`'s `latest_swing_high`/`latest_swing_low`
  (EXTERNAL tier) via `liquidity.hierarchy.external_swing_liquidity()` — structurally at
  most one candidate per side, so `tie_break=NOT_APPLICABLE` by construction, not by
  invented rule. Required status = `UNSWEPT` (`liquidity.status.compute_status`).
- **Fallback tier** — `CONFIRMED_M5_SWING_EXTREMUM`, drawing from `StructureTier.swings`
  (all confirmed EXTERNAL-tier M5 swings, chronological — the same list `latest_swing_
  high/low` are themselves reduced from), filtered to `UNSWEPT` + correct side. Tie-break
  = most recent `origin_time` wins, reusing `market_structure/tiers.py::_build_tier`'s
  own `reversed(...) + next(...)` "most-recent-match-wins" reduction convention verbatim
  (`tiers.py:111-112`) — not an invented rule, the same principle the tier already
  applies to select `latest_swing_high`/`latest_swing_low` from `swings`.
- **Priority**: tier 1 wins outright if any candidate exists; no cross-tier comparison.
- **No target**: `NO_TRADE` / `REJECT_NO_TARGET`; `READY` with a null target is
  `PROHIBITED`.
- **Mode**: `STATIC` — selected once at qualification, no dynamic retargeting.
- **Scope**: `GLOBAL` — identical across all 9 E×M cells (needs only direction + anchor
  price, independent of which E or M produced the candidate).
- Explicitly excluded from C11's scope (unchanged, separately tracked):
  `SETUP_INVALIDATION`, `BROKER_STOP_LOSS` (C10), `FIXED_R_TARGET`, `TP1`/`TP2`/
  partials/runner/breakeven/trailing (trade management).

Prior evidence background, retained for provenance:

- `src/liquidity/hierarchy.py`'s `InducementCandidate` already computes an
  EXTERNAL-tier, `UNSWEPT`, same-side liquidity level beyond current price, literally
  named `target`/`target_id` in the code — today used only to validate M1's inducement
  candidates (`find_inducement_candidates`, `classify_roles` → `ROLE_TARGET`), never
  wired as a strategy-level profit-target output. Its own docstring records that it
  deliberately does *not* rank/select a single best target when several qualify
  (`hierarchy.py:106-107`, "spec section 32").
- `src/entry_confirmation/entry_array.py` / `engine_v2_1.py` (M3's engine) already carry
  an unused `target_liquidity_reference: Optional[float] = None` slot on
  `EntryArrayContext` — caller-supplied, never computed, never used for gating; a
  pre-existing seam, not new capability, for exactly this kind of value.
- M2 has no target-shaped field at all.

Both external documents converge, more precisely than previously recorded: ST-C1 G9 —
priority 1 = nearest unswept external liquidity beyond entry, priority 2 = nearest
unswept M5 swing extremum, `REJECT_NO_TARGET` otherwise; `v3.6` — primary = nearest
unswept external liquidity beyond entry, fallback = nearest unswept M5 swing extremum,
`REJECT_NO_TARGET` otherwise; both explicitly reject a synthetic fixed-R substitute. This
matches AG's own `liquidity.hierarchy` concept almost exactly for the primary tier.

Full candidate/evidence matrices (superseded as *decision* material, retained as
provenance): `docs/status/ST_LARGE_SMC_V1_C11_TARGET_MODEL_RESOLUTION_STATUS.md`.
→ **UC-010, RESOLVED_BY_OWNER.**

## 17. Expiry (C12) — `RESOLVED_BY_REUSE`, `C12_IMPLEMENTATION_SPEC=COMPLETE`

Full derivation: `docs/status/ST_LARGE_SMC_V1_C12_EXPIRY_CONTRACT_RESOLUTION_STATUS.md`;
contract recorded in `strategies/ST_LARGE_SMC_V1.yaml`'s `candidate_lifecycle:` block
(`CONTRACT_ONLY`). Strategy version bumped `1.0.1 → 1.0.2`
(`docs/VERSION_HISTORY.md`: "intrinsic trade eligibility logic" is an explicit
strategy-version-bump trigger).

The prior draft's assumption — that `EntryModelState.EXPIRED` is "reused end-to-end"
with only its exact trigger left open — did not survive direct verification. Grepping
`m1_character_change_inducement.py`, `m2_supply_demand_shift.py`,
`m3_sweep_drop_pump.py`, `entry_array.py`, `engine_v2_1.py`, and `composer.py` for
`EXPIRED`/`expir`/`max_bars`/`timeout`/`window`/`age` found **zero hits outside the enum
declaration itself** — no M-model, the composer, or Stage2 ever transitions anything
into `EXPIRED`. It is a declared-but-unused enum value, not an implemented mechanism.

The reason: `historical_replay/stage2.py::evaluate_entry_stage()` — the frozen research
entry point — re-derives `m5_candles`/`m5_fvg`/`m5_obs`/`m2_zones`/
`inducement_candidates` fresh from current market data on **every call**
(`stage2.py:211-217`); AG has no persisted candidate object that "waits" across
evaluation timestamps and could time out. The only real, already-coded validity clock
found anywhere is `historical_replay/stage1.py::QualifiedEEvent.is_eligible_at(t)`
(`stage1.py:51-57`: `return any(start <= t < end for start, end in
self.eligibility_intervals)`), which Stage2's own docstring says gates *all* M-model
evaluation: *"Stage 2 must not evaluate M1/M2/M3 for an event outside its real
eligibility window."* Since this gate is identical for E1, E2, and E3 and none of
M1/M2/M3 has an independent clock anywhere in the code, C12 resolves to
**`SHARED_EXPIRY_DEPENDENCY`**: candidate validity is governed entirely by the shared
E-context eligibility window, not by per-M-model bar counts. This is a discovery from
tracing the actual call graph, not an invented rule — flagged transparently in case the
owner intended independent M-specific timers that were simply never built.

Frozen, by reuse:

- **Boundary/same-bar precedence**: half-open `[start, end)`, already coded verbatim —
  at `t == end`, `is_eligible_at` is already `False`, so `EXPIRY_FIRST` at the exact
  boundary bar is forced by construction, not chosen.
- **Non-monotonic**: eligibility can go `FALSE → TRUE → FALSE → TRUE`
  (`stage1.py:11`) — a later interval is a *new* evaluation, not a revived one.
- **Terminal semantics**: `EXPIRED` is non-actionable; revival of the *same* combination
  instance is prohibited — citing this project's own architecture-audit-phase invariant
  ("...must eventually prevent...resurrecting invalidated candidates"), not reinventing
  it.
- **Structural invalidation** (distinct from time-based expiry): `entry_confirmation/
  invalidation.py`'s `ManeuverInvalidation` (`EXACT_REUSE`, already wired for M1/M2;
  M3's IFVG-specific invalidation remains repo-wide `PARTIAL`, flagged not assumed).
- **Target consumed before activation** (new composition, not yet wired anywhere):
  `INVALIDATED` for either tier — reusing `liquidity.status.compute_status` (the same
  function used once at target selection) re-invoked at a later evaluation timestamp;
  classified `INVALIDATED` rather than `EXPIRED` because it is a structural/liquidity-
  status change, not a time/interval boundary; explicitly does **not** trigger
  reselection — C11's `TARGET_MODE=STATIC` is preserved unmodified.
- **Data-quality failure**: `INSUFFICIENT_DATA` (existing value), never fabricated as
  `EXPIRED` from unprovable chronology.
- **No C15 dependency**: `is_eligible_at`'s intervals are reconstructed from market/
  structural evidence (gap-fill/POI-reaction/sweep-reclaim windows), not from
  session/trading-hour definitions.

→ **UC-011, RESOLVED_BY_REUSE.**

## 18. Candidate lifecycle (C13) — `RESOLVED_FROM_EXISTING_RESOURCE`

Both halves are now resolved. The external `decision_states` vocabulary was already
`REUSE_EXISTING_AG`. The *internal* lifecycle the prior draft asked for already exists,
verbatim, as `EntryModelState` (`entry_models_v1.py:88-103`): `NOT_APPLICABLE →
SCANNING_CONTEXT → WAITING_HTF_TOUCH → WAITING_H1_REACTION → HTF_QUALIFIED →
WAITING_M5_CONFIRMATION → WAITING_M5_ENTRY → READY`, with `INVALIDATED`, `EXPIRED`,
`INSUFFICIENT_DATA`, and `NO_VALID_COMBINATION` as terminal/exception states. This maps
directly onto the prior draft's proposed `CONTEXT_FOUND → LOCATION_ACTIVE →
WAITING_LIQUIDITY_EVENT → WAITING_CONFIRMATION → RESEARCH_QUALIFIED →
INVALIDATED/EXPIRED` shape (spec section 33-34) without inventing new names — per spec
section 40-41, this document treats the existing `READY` state as
`RESEARCH_QUALIFIED` evidence *for ST_LARGE_SMC_V1's purposes only*; the underlying
oracle's own `READY` terminology and historical output are not renamed or altered.
`QualifiedEEvent.is_eligible_at(t)`'s time-varying eligibility remains available as
supporting evidence for E-side eligibility windows specifically. → **UC-012, RESOLVED**
(see §32).

## 19. Duplicate / re-entry (C14) — `PARTIALLY_RESOLVED`
(`setup_family_identity=RESOLVED_BY_REUSE`, `candidate_occurrence_identity=
DETERMINISTIC_AND_TESTED`, live lifecycle-store migration `SHARED_CHANGE_REQUIRED`,
post-fill re-entry `DEFERRED`)

**Correction (2026-09-01, `ST_LARGE_SMC_V1_C14A_CANDIDATE_OCCURRENCE_IDENTITY`
phase):** the prior version of this section claimed `RESOLVED_BY_REUSE` for all of
C14. That overclaimed. Full derivation of both the original findings and this
correction: `docs/status/ST_LARGE_SMC_V1_C14_DUPLICATE_REENTRY_CONTRACT_RESOLUTION_
STATUS.md` and `docs/status/ST_LARGE_SMC_V1_C14A_CANDIDATE_OCCURRENCE_IDENTITY_
STATUS.md`. Contract recorded in `strategies/ST_LARGE_SMC_V1.yaml`'s
`candidate_identity:` block, `authority:` downgraded from `RESOLVED_BY_REUSE` to
`PARTIALLY_RESOLVED`. **No version bump for this correction** — no new semantics were
frozen, an overclaim was corrected; version remains `1.0.3`.

**What remains correctly resolved (setup-family layer):**

- **Setup-family key** = `setup_id(symbol, combination, direction, reference_key)`
  (`proposals/identity.py:29-35`) — a pure `blake2b` hash with zero transient/wall-clock
  input. `EXACT_REUSE`, still valid.
- **Same E, different M** and **different E, same/different M**: `DISTINCT_CANDIDATE`
  at the setup-family level, guaranteed by construction (verified against the golden
  setup IDs). Still valid.
- **Target is not identity-bearing**: confirmed from the hash formula. Still valid.
- **Multi-candidate output is deliberate architecture** (`composer.py`'s own
  docstring); `selected_combination=None` is `OPTIONAL_PORTFOLIO_HANDOFF`. Still valid.
- **Post-fill re-entry**: `DEFERRED`. Still valid, unchanged.

**What was wrong — the occurrence layer:**

The claim that `setup_id` alone provides everything needed for duplicate suppression
conflated two distinct layers. Verified directly:
`QualifiedEEvent.eligibility_intervals: Tuple[Tuple[datetime, datetime], ...]`
(`stage1.py:47`) — **one `event_id`/`setup_id` legitimately spans multiple, disjoint
eligibility intervals** (non-monotonic per C12: `FALSE→TRUE→FALSE→TRUE`,
`stage1.py:11`). `setup_id` is therefore a **setup-family** identity, not a
per-occurrence identity — section 8's completion requirement ("two distinct
occurrences under the same setup family must be deterministically distinguishable")
was not actually satisfied.

Worse, no canonical **M-candidate structural identifier** exists anywhere: `M1Result`,
`M2Result`, `M3Result`, `ZoneResult`, and `ValidatedOrderBlock` were all inspected —
none has an `id`/`source_id`/`origin_id` field. `M1Result` has *zero* timestamp fields
at all (only `entry_array_low`/`entry_array_high`/`entry_array_type`, all price/type,
no time); `M2Result`/`M3Result` have partial timestamps (`structural_break_time`,
`zone_failure_time`, `choch_time`) plus `ZoneResult`/`ValidatedOrderBlock.origin_time`,
but still no id field.

The prior "terminality"/"revival" claims were not actually grounded in enforcement:
`proposals/lifecycle.py::update_proposal_lifecycle`'s `store` is keyed **only** by
`setup_id` (`store.get(proposal.setup_id)` / `store.put(proposal.setup_id, ...)`,
`lifecycle.py:69,80`). When a prior record is terminal (`_TERMINAL =
(LIFECYCLE_INVALIDATED, LIFECYCLE_EXPIRED)`, `lifecycle.py:34`) and new evidence
arrives for the *same* `setup_id`, the code transitions to `CREATED`
(`lifecycle.py:72-73`) but **overwrites** the old terminal record rather than
preserving it alongside a distinguishable new occurrence. This is
`SETUP_FAMILY_STATE_OVERWRITE`, not `OCCURRENCE_HISTORY` — confirmed by code, not
inferred. `OCCURRENCE_IDENTITY_GAP = YES`.

**C14B (2026-09-01, owner-selected Option B) — closed by implementation, not just
composition.** Full derivation:
`docs/status/ST_LARGE_SMC_V1_C14B_OCCURRENCE_IDENTITY_HARDENING_STATUS.md`. Strategy
version bumped `1.0.3 → 1.0.4`.

- `eligibility_interval_id(event_id, interval_start, interval_end)` — implemented,
  `src/proposals/occurrence_identity.py`, same `blake2b` convention as
  `proposals/identity.py::setup_id`, market-time-only, restart-stable, unit-tested.
- `M_candidate_identity` — **Option B implemented**: additive `source_id` field on
  `M1Result`/`M2Result`/`M3Result` (`src/entry_confirmation/`), computed from
  already-existing structural evidence, no new detection:
  - **M1**: `hash(InducementCandidate.candidate_id [existing liquidity.hierarchy.
    level_id], choch_point.time_utc)` — set once `choch_confirmed=True`.
  - **M2**: `hash(supply_demand.zone_id(opposing_zone), zone_failure_time)` —
    `zone_id()` is a small, new, additive helper in `supply_demand/models.py`
    mirroring `liquidity.hierarchy.level_id()`'s exact construction; set once
    `zone_failure=True`.
  - **M3**: `hash(liquidity.level_id(liquidity_level), choch_point.time_utc)` — set
    once the M5 structural failure is found. Inherits the pre-existing, unrelated
    `inverted_gap_policy=PARTIAL` caveat unchanged.
  - Stability and separation proven for all three models in
    `tests/test_candidate_occurrence_identity.py` (16 new tests): same evidence →
    same `source_id`; different inducement/zone/liquidity-level or confirming bar →
    different `source_id`; `None` before a concrete candidate exists (not fabricated).
- `candidate_occurrence_id(setup_family_id, eligibility_interval_id, m_candidate_
  identity)` — implemented, composes the three layers; repeated-poll idempotence,
  new-interval separation, multiple-independent-M-candidate separation, and 3×3
  coexistence preservation all unit-tested.
- **The live lifecycle store was deliberately NOT migrated.**
  `proposals/lifecycle.py::update_proposal_lifecycle` remains keyed only by
  `setup_id` — it is shared with the live `SMC_CONDITIONAL_ENTRY_V2` watcher
  (`daily_routine/m5_execution.py`), not just Large-SMC research, so changing its
  store key is a live-behavior change requiring its own, separately-authorized
  regression scope (`SHARED_CHANGE_REQUIRED`). A test reproduces the exact defect
  against the real, unmodified function (a terminal record is overwritten, not
  preserved, when new evidence arrives under the same `setup_id`) and separately
  proves `candidate_occurrence_id` would distinguish what that defect conflates —
  the identity layer is ready for that migration whenever it is authorized.
- Full regression proof of backward compatibility: 172 pre-existing tests (M1/M2/M3,
  `entry_confirmation`, `proposals`, `supply_demand`), 21 Stage1/Stage2 identity
  tests, and the 7-test golden vertical slice all pass unchanged.

→ **UC-013, PARTIALLY_RESOLVED — identity layer complete, live storage migration
deferred (`SHARED_CHANGE_REQUIRED`).** The distinction matters: every deterministic
question C14 needed to answer (what makes two candidates the same, when they may
coexist, what is terminal) now has a computable, tested answer; only *wiring that
answer into the live, shared lifecycle store* remains open, and deliberately so.

## 20. Time restrictions (C15) — `UNRESOLVED_CONTRACT`, non-blocking

No session/time field exists. The signed D1/H4/H1-heavy framing is more consistent with
session-independence than with a fixed London/NY window, but that is an inference, not
an owner decision. ST-C1/ST-C3 restrict to London/NY sessions (`RESEARCH_REFERENCE`
only). `ST_ASIAN_SWEEP_5R_V1`'s Asian 00:00-06:00 reference / 07:00-11:00 execution
window is explicitly **not** inherited (spec section 36). → **UC-014, non-blocking** (a
filter parameter, not a core trade-outcome semantic per spec section 57).

## 21. Data quality (C16) — `PARTIALLY_RESOLVED`, non-blocking

`timezone=UTC`, `closed_bars_only=true`, `source=MT5_FX_RESEARCH`, and
`availability_and_staleness=USE_EXISTING_FAIL_CLOSED_MARKET_DATA_CONTRACT` are all
signed (`REUSE_EXISTING_AG` — reuses the same fail-closed market-data boundary every
other strategy uses). Only `warmup` (minimum history per timeframe) is `UNSIGNED`. With
UC-001 resolved, the E1/E2/E3 lookback constants AG already uses operationally elsewhere
(`historical_replay/resampler.py:146`: `D1=60, H1=50, M5=200` candles) are available as
a `CANDIDATE_FOR_SPEC` warmup reference, though not yet formally adopted for
`ST_LARGE_SMC_V1` specifically.

## 22. Multi-symbol behavior (C17) — `RESOLVED`

No cross-symbol/correlation evidence exists anywhere in the contract or research
sources. Per spec section 39, absent evidence the default is single-symbol-independent
evaluation; portfolio/correlation policy remains out of scope and downstream
(`NOT_REQUIRED` here).

## 23. Conflicting evidence (C18) — `PARTIALLY_RESOLVED`, downstream-blocking (narrowed)

C02/C03/C04 are now resolved, which narrows this contract considerably: with H4 not a
primary layer, the classic "D1 bullish vs. H4 bearish" conflict shape no longer applies
— D1 and H1 are each scoped to specific E-models rather than both voting on every
candidate independently, and `composer.py`'s `E.direction == M.direction` gate already
resolves *E-vs-M* direction conflicts deterministically (mismatch → no combination, not
an ambiguous state). What remains open: whether multiple simultaneously-active
combinations for the same symbol (e.g. E1M2 and E3M3 both reaching `HTF_QUALIFIED` at
once, as the golden baseline shows actually happened on 2025-09-15) should be treated as
independent research variants (current behavior, no conflict) or require an explicit
priority/selection rule — this is the same gap identified in UC-013 (§19), not a new
one. → **UC-015, PARTIALLY_RESOLVED**, remaining scope merged with UC-013.

## 24. Evidence requirements summary

Once UC-001 (timeframe scheme) is resolved, the remaining evidence requirements
(liquidity distinguishing target vs. inducement, POI freshness/mitigation state,
structure BOS/CHoCH/MSS classification, displacement) are all things AG's shared skills
(`market-structure-analysis`, `supply-demand-analysis`, `liquidity-analysis`,
`entry-confirmation-analysis`) already produce as typed evidence — no new skill
capability is anticipated, only a strategy-level interpretation decision.

## 25. AG capability reuse mapping

| Requirement | AG capability | Module | Reuse status |
|---|---|---|---|
| Directional model | E1/E2/E3 `direction` field | `src/entry_confirmation/e{1,2,3}_*.py` | `CANDIDATE_FOR_SPEC`, contingent on UC-001 |
| Structural context (BOS/CHoCH/MSS) | market-structure-analysis | `src/market_structure/` | `CANDIDATE_FOR_SPEC` |
| Location/POI | E2's H1 POI + `poi.py` | `src/entry_confirmation/poi.py`, `e2_h1_poi_reaction.py` | `CANDIDATE_FOR_SPEC`, contingent on UC-001 |
| Liquidity (target vs. inducement) | `liquidity.status`, `liquidity.hierarchy` | `src/liquidity/status.py`, `hierarchy.py` | `CANDIDATE_FOR_SPEC` |
| Activation boundary | `EConditionResult.eligible_for_confirmation` | `src/entry_confirmation/e{1,2,3}_*.py` | `CANDIDATE_FOR_SPEC`, contingent on UC-001 |
| Confirmation + entry array | M1/M2/M3 | `src/entry_confirmation/m{1,2,3}_*.py` | `CANDIDATE_FOR_SPEC`, contingent on UC-001/UC-008 |
| Candidate time-varying eligibility | `QualifiedEEvent.is_eligible_at(t)` | `src/historical_replay/stage1.py` | `CANDIDATE_FOR_SPEC` |
| Data quality / fail-closed access | existing MT5 market-data contract | `src/mt5/market_data.py`, `src/assistant/market_data.py` | `REUSE_EXISTING_AG` (signed) |
| Invalidation/stop, target, expiry, duplicate policy | none — no AG implementation exists for these as Large-SMC-specific rules | — | `NEW_CAPABILITY_NEEDED` once frozen, or adapted from `RESEARCH_REFERENCE` |

No `SEMANTIC_MISMATCH` reuse was accepted silently: the AG E/M pipeline is offered only
as a *candidate*, not treated as already-adopted, precisely because its timeframe scheme
does not match the yaml's currently-signed D1/H4/H1/M15 buckets (UC-001).

## 26. Research model mapping (E1/E2/E3, M1/M2/M3)

E1 = `PRICE_FILL_AND_REACT_D1_GAP` (D1 gap reference, H1 reaction). E2 =
`PRICE_REACT_H1_POI` (H1 POI reference, H1/M5 reaction). E3 =
`PRICE_SWEEP_HTF_LIQUIDITY` (caller-supplied H1/H4/D1 liquidity level, requires
`RECLAIMED` status specifically). M1 = inducement sweep → CHoCH → displacement → entry
array → retracement. M2 = opposing-zone invalidation → new zone → displacement → entry
array. M3 = HTF sweep+reclaim → M5 CHoCH → displacement → FVG/OB → 50% pullback. All six
are frozen, `AG_NATIVE`, and reproduced against a golden oracle
(`events=18, setups=54, arrays=9, ready=3`,
`docs/status/TRUE_STAGE2_ORACLE_RECONCILIATION_STATUS.md`). That baseline proves the
existing entry-confirmation research pipeline's internal consistency; it is **not**
evidence for `ST_LARGE_SMC_V1`'s own profitability or correctness (spec section 29) —
`ST_LARGE_SMC_V1` does not currently reference any of these six modules.

## 27. Unresolved contract register

Numbering preserved from the prior draft for traceability (spec section 39); resolved
entries are kept with `RESOLVED` status rather than removed.

| ID | Contract | Status | Summary |
|---|---|---|---|
| UC-001 | C02 Timeframe roles | **RESOLVED_BY_OWNER** | Owner selected Model B (D1/H1/M5), matching AG's frozen E/M pipeline. See §7, §32. |
| UC-002 | C03 Directional model | RESOLVED | E-specific direction via `EConditionResult.direction`; composer gates on `E.direction==M.direction`. |
| UC-003 | C04 Structural context | RESOLVED | E-specific structural detectors (E1/E2/E3), not one global rule. |
| UC-004 | C05 Location/POI | RESOLVED | E-specific location (D1 gap / H1 POI / swept liquidity level). |
| UC-005 | C06 Liquidity requirement | PARTIALLY_RESOLVED | Which cells require liquidity is now known (variant-specific); exact wick-ratio thresholds still `v3.6`-only. |
| UC-006 | C07 Activation event | RESOLVED | `HTF_QUALIFIED` / `eligible_for_confirmation` is the activation boundary. |
| UC-007 | C08 Entry confirmation | RESOLVED | M-specific confirmation sequences (M1/M2/M3), entry-array required by all three. |
| UC-008 | C09 Entry model | RESOLVED | M-specific entry reference (M5, per-model formula); resolved as a consequence of UC-001=Model B. |
| UC-009 | C10 Invalidation/stop | PARTIALLY_RESOLVED | Candidate-invalidation mechanism reused; broker SL-distance formula still open — see UC-009b below (was the secondary owner decision). |
| UC-010 | C11 Target model | RESOLVED_BY_OWNER | Candidate 2 (Hybrid) frozen 2026-09-01, `strategies/ST_LARGE_SMC_V1.yaml` `target_model:` block, v1.0.1. See §16. |
| UC-011 | C12 Expiry | RESOLVED_BY_REUSE | No independent M1/M2/M3 clock exists; validity is shared via `QualifiedEEvent.is_eligible_at()`. v1.0.2. See §17. |
| UC-012 | C13 Candidate lifecycle (internal) | RESOLVED | `EntryModelState` is the internal state machine, reused verbatim. |
| UC-013 | C14 Duplicate/re-entry | PARTIALLY_RESOLVED | Identity layer `DETERMINISTIC_AND_TESTED` (C14B, v1.0.4); live lifecycle-store migration `SHARED_CHANGE_REQUIRED`, deferred. See §19. |
| UC-014 | C15 Time restrictions | Non-blocking | No session field; plausible session-independence is an inference, not a decision. |
| UC-015 | C18 Conflicting evidence | PARTIALLY_RESOLVED | E-vs-M conflicts resolved by the composer's direction gate; remaining scope merged into UC-013 (multi-combination selection policy). |
| UC-016 | C01 Instrument list | Non-blocking | Asset class (FX) signed; exact instrument list unsigned. |

## 28. Research safety gates

`actionable_READY=BLOCKED`, `risk_sizing=BLOCKED`, `portfolio_claim=BLOCKED`,
`proposal_generation=BLOCKED`, `order_check=0`, `order_send=0`. `RESEARCH_QUALIFIED` (or
equivalent) is the highest attainable state while `status=RESEARCH_DRAFT`; it is never
`READY` in the actionable sense.

## 29. Promotion requirements

Unchanged from the prior draft: promotion requires an owner-approved frozen revision
resolving every `UNSIGNED` field (starting with UC-001), deterministic engine tests,
causal replay, robustness validation, independent registry authorization, and separately
evidenced demo validation. Registration alone never grants execution permission.

## 30. UC-001 — resolution record

**RESOLVED_BY_OWNER (2026-09-01).** Selected: **Option B —
`ADOPT_FROZEN_AG_D1_H1_M5`.** Full decision packet:
`docs/status/ST_LARGE_SMC_V1_UC_001_TIMEFRAME_DECISION.md`. `strategies/
ST_LARGE_SMC_V1.yaml`'s `timeframe_responsibilities` was updated accordingly (§7). This
single decision cascaded to resolve or partially resolve UC-002 through UC-012 and
UC-015 by adoption of AG's own frozen E1-E3/M1-M3 research pipeline — see §32-35 for the
full reconciliation this phase performed.

## 31. UC-008 / UC-009 — resolved as a consequence of UC-001

Both were flagged in the prior draft as secondary owner decisions "contingent on
UC-001." With UC-001 = Model B, the evidence that made Model B the recommendation
(AG's own frozen, golden-validated M1/M2/M3) is the same evidence that resolves these:

- **UC-008 (C09 entry model): RESOLVED** — AG's own M1/M2/M3 entry references (§14),
  not ST-C1's single linear gate.
- **UC-009 (C10 invalidation/stop): PARTIALLY_RESOLVED** — the *invalidation* mechanism
  is AG's own (`SMCEntryCombinationResult.invalidation*` fields, §15); the *SL-distance*
  formula (ST-C1's unified rule vs. `v3.6`'s per-model formulas) remains an open,
  genuinely un-adopted choice — this is now the residual scope of UC-009, not a full
  re-decision.

## 32. 3×3 E×M research architecture reconciliation

Full reconciliation phase: `docs/status/
ST_LARGE_SMC_V1_3X3_VARIANT_AUTHORITY_RECONCILIATION_STATUS.md`. Summary:

**E-model matrix**

| Model | Timeframes (ref → check) | Location/context | Direction | Activation boundary | Golden coverage | Large-SMC fit |
|---|---|---|---|---|---|---|
| E1 | D1 → H1 | D1 gap zone | derived from gap's implied bias | `HTF_QUALIFIED` after a displacement-qualifying H1 reaction candle | Yes — feeds 2 of 3 golden READY setups (E1M2, E1M3) | `EXACT_REUSE` |
| E2 | H1 → H1 (+M5 reaction candle) | H1 POI (`poi.py`) | derived from POI's bullish/bearish role | `HTF_QUALIFIED` after a qualifying M5 reaction | No golden READY in either sampled window | `EXACT_REUSE` |
| E3 | H1/H4/D1 (caller-supplied) → H1 | swept liquidity level, `RECLAIMED` status required | derived from swept-side direction | `HTF_QUALIFIED` after sweep+reclaim confirmed | Yes — feeds 1 of 3 golden READY setups (E3M3) | `EXACT_REUSE` |

**M-model matrix**

| Model | Timeframe | Event sequence | Entry array | Entry reference | Invalidation | Golden coverage | Large-SMC fit |
|---|---|---|---|---|---|---|---|
| M1 | M5 | inducement sweep → CHoCH → displacement → entry array → retracement | FVG/OB | array midpoint | `INVALIDATED`/`EXPIRED` states, reused verbatim | Zero entry arrays formed in either sampled window (`ENTRY_ARRAY_CREATED=0`) despite 5/5 confirmations in the 2-week sample | `EXACT_REUSE` (interface); `INSUFFICIENT_EVIDENCE` (empirical) |
| M2 | M5 | opposing-zone invalidation → new zone → displacement → entry array | FVG or OB ("Gold Zone") | zone midpoint | same mechanism | 1 golden READY (E1M2) | `EXACT_REUSE` |
| M3 | M5 | HTF sweep+reclaim → CHoCH → displacement → IFVG → ≥50% pullback | IFVG | gap/entry-level | same mechanism | 2 golden READY (E1M3, E3M3) | `EXACT_REUSE` |

**3×3 variant matrix** (interface validity confirmed via `composer.py`'s generic,
symmetric cross-join — `compose(e, m)` applies identically to every E/M pair, gated only
on `eligible_for_confirmation`, `m.state` not in `{NOT_APPLICABLE, NO_VALID_COMBINATION}`,
and `e.direction == m.direction`; no per-pair special-casing exists anywhere in the
composer):

| | M1 | M2 | M3 |
|---|---|---|---|
| **E1** | VALID_RESEARCH_VARIANT (interface confirmed; `INSUFFICIENT_EVIDENCE` empirically — never formed an array in either sampled window) | VALID_RESEARCH_VARIANT (golden `READY`, 2025-09-23) | VALID_RESEARCH_VARIANT (golden `READY`, 2025-09-15) |
| **E2** | VALID_RESEARCH_VARIANT (interface confirmed; `INSUFFICIENT_EVIDENCE` empirically) | VALID_RESEARCH_VARIANT (interface confirmed; `INSUFFICIENT_EVIDENCE` empirically) | VALID_RESEARCH_VARIANT (interface confirmed; `INSUFFICIENT_EVIDENCE` empirically) |
| **E3** | VALID_RESEARCH_VARIANT (interface confirmed; `INSUFFICIENT_EVIDENCE` empirically) | VALID_RESEARCH_VARIANT (interface confirmed; `INSUFFICIENT_EVIDENCE` empirically) | VALID_RESEARCH_VARIANT (golden `READY` ×2 total across windows, 2025-09-15 + 2-week sample) |

All nine cells are structurally `VALID_RESEARCH_VARIANT` — the composer treats E and M
as genuinely orthogonal (spec section 21/22 in the module's own docstring: "no priority
or routing invented... every valid combination is returned"). No cell is
`SEMANTIC_CONFLICT` or `NOT_SUPPORTED`. Six of nine cells lack empirical (golden or
sampled) evidence of ever reaching an entry array — this is `INSUFFICIENT_EVIDENCE`, not
a defect (`docs/status/SMC_3X3_HISTORICAL_VALIDATION_V1_STATUS.md:197-202`: "a low/zero
READY count from a correctly running pipeline is a valid research result, not a defect
to fix"). `THREE_BY_THREE_STATUS = PARTIAL_3X3_REUSE` — reuse is confirmed at the
interface/mechanism level for all nine cells; empirical support currently exists for
three.

**Variant identity already exists** — no new naming was invented.
`SMCEntryCombinationResult.combination` is literally `"E1M1".."E3M3"`
(`entry_models_v1.py:144`), deterministic and unique per (E, M) pair.
`REGISTRY_VARIANT_SUPPORT = NOT_REQUIRED_YET`: `strategies/registry.yaml` continues to
register `ST_LARGE_SMC_V1` as a single strategy family (unchanged, per spec section
16-17); the nine variants are documented here, in the canonical specification, not as
separate registry rows — avoiding registry explosion as instructed.

## 33. Composition contract

Evidence supports the compositional model spec section 27 proposed:

```
ST_LARGE_SMC_V1_VARIANT(E, M) = GLOBAL_RULES + E_CONTEXT_RULES + M_ENTRY_RULES
```

`GLOBAL_RULES` = direction-match gating (`composer.py:64`), the shared
`EntryModelState` lifecycle shape, `M5` as the fixed confirmation/execution timeframe.
`E_CONTEXT_RULES` = C03 (direction)/C04 (structure)/C05 (location)/C07 (activation),
each E-specific (§8-§12 above). `M_ENTRY_RULES` = C08 (confirmation)/C09 (entry model),
each M-specific (§13-§14 above). `C06` (liquidity) splits across both dimensions
(E3-specific and M1-specific, §11). This composition held for all nine cells with no
exceptions found — no forced flattening was required.

## 34. Reuse matrix

| Component | Existing AG resource | Large-SMC role | Reuse status |
|---|---|---|---|
| D1 context | E1 (`e1_daily_gap_reaction.py`) | macro event reference | `EXACT_REUSE` |
| H1 structure | E1/E2/E3 shared `CHECK_TIMEFRAME` | structure/reaction check | `EXACT_REUSE` |
| H1 POI | `poi.py` (via E2) | location for E2 | `EXACT_REUSE` |
| H1 reaction | `AG_ENTRY_DISPLACEMENT_V1` (`displacement.py`, via E1/E2) | activation-qualifying reaction | `EXACT_REUSE` |
| H1 liquidity | `liquidity.status` (`RECLAIMED`, via E3) | location/liquidity for E3 | `EXACT_REUSE` |
| H4 optional evidence | E3's caller-supplied `LiquidityLevel.timeframe` | optional liquidity-level origin only | `EXACT_REUSE` (narrow, not a primary layer) |
| M5 liquidity | `liquidity.hierarchy.InducementCandidate` (via M1) | inducement sweep for M1 | `EXACT_REUSE` |
| M5 CHoCH/MSS | shared structure-shift detection (via M1/M3) | confirmation for M1/M3 | `EXACT_REUSE` |
| M5 displacement | `AG_ENTRY_DISPLACEMENT_V1` (shared across M1/M2/M3) | confirmation for all M-models | `EXACT_REUSE` |
| M5 FVG/OB | shared zone detection (via M1/M2) | entry array for M1/M2 | `EXACT_REUSE` |
| M5 IFVG | `gap.py::evaluate_inverted_gap_context` (via M3) | entry array for M3 | `EXACT_REUSE`, though the inverted-gap policy itself is repo-wide `PARTIAL` (unsigned elsewhere) |
| M5 entry array | M1/M2/M3 entry-reference fields | C09 | `EXACT_REUSE` |
| Candidate invalidation | `SMCEntryCombinationResult.invalidation*` | C10 (invalidation half only) | `EXACT_REUSE` |
| Expiry | `EntryModelState.EXPIRED` | C12 (mechanism only) | `THIN_ADAPTER` (mechanism exists; per-model trigger/value needs confirming) |
| Lifecycle | `EntryModelState` (full enum) | C13 | `EXACT_REUSE` |
| Broker stop-loss distance | none | C10 (SL half) | `MISSING` |
| Profit target | none | C11 | `MISSING` |
| Duplicate/re-entry policy | none (`selected_combination` always `None`) | C14 | `MISSING` |

Reuse tally: `EXACT_REUSE=13`, `THIN_ADAPTER=1`, `MISSING=3`, `PARTIAL=0` (the IFVG
policy note is a caveat on an `EXACT_REUSE` row, not its own row),
`SEMANTIC_MISMATCH=0`.

## 35. Remaining contracts and next blocking item

Updated completeness (post C14B, 2026-09-01): `RESOLVED=11` (C02, C03, C04, C05, C07,
C08, C09, C11, C12, C13, C17), `PARTIALLY_RESOLVED=6` (C01, C06, C10, C14, C16, C18),
`UNRESOLVED_CONTRACT=1` (C15), `NOT_REQUIRED=0`. (11+6+1=18.) The top-level tally is
unchanged from the C14A correction — C14 remains `PARTIALLY_RESOLVED`, deliberately —
but its internal composition changed substantially: `candidate_occurrence_identity`
moved from `OWNER_DECISION_REQUIRED` to `DETERMINISTIC_AND_TESTED`; the only remaining
open piece is the live lifecycle-store migration, explicitly classified
`SHARED_CHANGE_REQUIRED` rather than an unresolved contract question (§19).

Two open items remain for "first remaining blocker":

- **C14's live-storage migration** (`SHARED_CHANGE_REQUIRED`) — the identity layer is
  ready; wiring `candidate_occurrence_id` into `proposals/lifecycle.py`'s store key
  requires its own, separately-authorized regression scope, since that module is
  shared with the live `SMC_CONDITIONAL_ENTRY_V2` watcher, not just Large-SMC
  research.
- **C10's residual SL-distance formula** (UC-009) — earlier in spec section 58's
  minimum-core ordering (invalidation precedes duplicate/re-entry), deliberately left
  open across the C11 and C12 phases, and still not revisited.

C16 (data quality, `warmup` value) and C18 (residual multi-combination conflict
policy) are secondary. C01 (instrument list) and C15 (session/time) remain open but
non-blocking.

→ **FIRST_REMAINING_BLOCKER = UC-009 (C10 SL-distance residual)** — the earliest item
in strict minimum-core sequence; C14's remaining piece is a deferred infrastructure
decision (`SHARED_CHANGE_REQUIRED`), not a contract question blocking further
specification work.

## 36. RESEARCH_ONLY_FUNNEL_V1 (2026-09-02) — the two-part funnel engine

Full evidence: `docs/status/ST_LARGE_SMC_V1_RESEARCH_FUNNEL_V1_STATUS.md`. Strategy
version bumped `1.0.4 → 1.0.5` (targets/intrinsic-eligibility-logic bump triggers).

Implements the smallest research-only engine answering: *does ST_LARGE_SMC_V1 produce
enough causal, executable, unambiguous historical occurrences to justify full
validation?* — organized as the universal funnel:

```
DATA COLLECTION:  MT5/broker data -> closed D1/H1/M5 candles -> market structure,
                  liquidity, OB/FVG -> E1/E2/E3 context -> M1/M2/M3 confirmation ->
                  deterministic E*M candidate occurrences
                  (entirely historical_replay.stage1/stage2 + entry_confirmation/*,
                  all pre-existing, zero redetection)

DECISION MAKING:  candidate validity -> simultaneous-combination resolution (C18) ->
                  entry (M-model's own entry_price) -> broker stop (C10, BLOCKED) ->
                  target (C11, IMPLEMENTED) -> pending-entry expiry (BLOCKED) ->
                  explicit research decision
                  (src/large_smc_research/engine.py -- new, thin)
```

New code: `src/large_smc_research/decision.py` (the `LargeSMCResearchDecision` output
shape and decision-state vocabulary), `target_model.py` (C11 adapter), `engine.py`
(`LargeSMCResearchEngine.evaluate()`). New script:
`scripts/run_large_smc_discovery.py` (Phase B driver, reuses
`historical_replay.orchestrator.run_replay` unchanged).

**C01 (instrument list), RESOLVED:** `[EURUSD]` only (task default recommendation).
GBPUSD explicitly deferred. Enforced in code
(`large_smc_research.engine.FROZEN_INSTRUMENT_UNIVERSE`) — no dynamic/inferred
inclusion.

**C16 (warmup), RESOLVED_BY_REUSE:** `D1=60/H1=50/M5=200`, the same constants
`historical_replay/orchestrator.py` already uses operationally. No new number invented.

**C11 (target model) adapter, IMPLEMENTED:** `target_model.py::select_target` — formula
unchanged from §16's frozen contract; primary tier via
`liquidity.hierarchy.external_swing_liquidity`, fallback via
`market_structure.tiers.StructureTier.swings` + `liquidity.status.compute_status` (the
same status function the primary tier itself uses). No new detector.

**C18 (simultaneous-combination selection), RESOLVED_BY_REUSE:** not a new decision —
formalizes what §19's `candidate_identity.selection`/`coexistence` already established
(`strategy_level_single_winner_required: NO`, `multi_candidate_output: CONFIRMED`,
`portfolio_selection_boundary: DOWNSTREAM_FUTURE_AUTHORITY`). `engine.evaluate()`
returns one independent `LargeSMCResearchDecision` per composed E×M combination, each
with its own `candidate_occurrence_id` (wiring C14B's previously-unwired
`proposals/occurrence_identity.py` into this engine's own output only — not into the
shared `proposals/lifecycle.py` store, so the `SHARED_CHANGE_REQUIRED` migration stays
exactly as deferred). Never narrowed by list order.

**Decision-state vocabulary:** dropped the placeholder `READY` (an actionable trading
state; per this task's explicit instruction, never emitted here) for
`RESEARCH_QUALIFIED` (the ceiling under `RESEARCH_DRAFT`) and added `INVALIDATED`
(structural invalidation, distinct from time-based `EXPIRED`, per C12).
`strategies/ST_LARGE_SMC_V1.yaml`'s `decision_states:` updated to match.

**C10 (broker stop-loss) and post-READY pending-entry expiry — deliberately left
`UNSIGNED`, by owner decision (2026-09-01):** no formula or clock invented. Any
candidate whose M-model reaches its entry-available state returns `BLOCKED`
(`UNSIGNED_CONTRACT:C10_BROKER_STOP` and/or `UNSIGNED_CONTRACT:PENDING_ENTRY_EXPIRY`)
rather than a fabricated actionable state. Two decision-packet documents record
candidate options from research references, none selected:
`docs/status/ST_LARGE_SMC_V1_C10_STOP_LOSS_DECISION_PACKET.md` and
`docs/status/ST_LARGE_SMC_V1_PENDING_ENTRY_EXPIRY_DECISION_PACKET.md`. Consequently,
fill simulation, invalidated-before-fill, expired-unfilled, intrabar ambiguity, and
completed-outcome resolution are **not attempted** this phase (Phase B's discovery
report states this honestly rather than fabricating zeros).

**Updated unresolved-contract register:** C01 and C16 move from non-blocking-open to
`RESOLVED`; C18's residual (§23) moves from `PARTIALLY_RESOLVED` to `RESOLVED_BY_REUSE`
(merged fully into C14's already-settled selection policy — see §19). `RESOLVED` count
rises from 11 to 14 (C01, C02, C03, C04, C05, C07, C08, C09, C11-adapter, C12, C13,
C16, C17, C18); `PARTIALLY_RESOLVED` narrows to C06, C10, C14 (its own residual,
`SHARED_CHANGE_REQUIRED`, unchanged); `UNRESOLVED_CONTRACT` remains C15 only,
non-blocking. → **FIRST_REMAINING_BLOCKER = UC-009 (C10 SL-distance)**, unchanged —
now the *only* thing standing between this funnel and outcome simulation, alongside
the pending-entry-expiry decision packet.

## 37. OUTCOME_LIFECYCLE_V1 (2026-09-02) — pending-entry lifecycle and a discovered gap

Full evidence: `docs/status/ST_LARGE_SMC_V1_OUTCOME_LIFECYCLE_V1_STATUS.md` and
`docs/status/ST_LARGE_SMC_V1_MT5_SYMBOL_METADATA_REPLAY_GAP.md`. Strategy version
bumped `1.0.5 → 1.0.6` ("intrinsic trade eligibility logic" bump trigger).

**Post-READY pending-entry expiry, RESOLVED_BY_REUSE:** the previously-open question
(§27's §35 "next remaining blocker" companion) is answered by exact reuse of
`historical_replay/fill_simulator.py` — a pre-existing, already-tested module built for
exactly this E/M pipeline that had simply never been wired to `ST_LARGE_SMC_V1`. Its
own module docstring already states "ENTRY_EXPIRY = UNDEFINED... does NOT invent one":
a pending candidate is terminal only via `FILLED` or structural
`INVALIDATED_BEFORE_FILL`; `UNFILLED_AS_OF_DATA_END` is an honest data-boundary
statement, and `INTRABAR_AMBIGUOUS` fails closed rather than assuming a favorable fill
order. New `src/large_smc_research/pending_entry.py` composes this verbatim, preserving
full occurrence identity (`candidate_occurrence_id`, `setup_family_id`,
`eligibility_interval_id`) end to end. This is a separate lifecycle stage from C12
(pre-activation E-context eligibility) — the two are not conflated.

**C10 (broker stop-loss) remains genuinely UNSIGNED and BLOCKED** — nothing this phase
resolves it; a new AG-native precedent was found and added to the decision packet
(`strategy_engine.sweep_retest.targets.forex_sl_buffer_price`'s structural-anchor +
pip-buffer pattern) but not adopted, since its numeric buffer is
`ST_LIQUIDITY_SWEEP_RETEST_V1`-specific and would need its own justification for
Large-SMC. `TARGET_HIT`/`STOP_HIT` outcome resolution and R-multiples remain
unimplemented and unattempted.

**Discovered, disclosed gap (not fixed):** the first real wiring of
`LargeSMCResearchEngine` into historical replay (targeted at the three known September
2025 occurrences, via the existing `artifacts/backtests/stage1/
qualified_e_events_2025-08-01_2025-10-01.json` + `directional_liquidity_timeline.json`
artifacts — no full-month re-run needed) revealed that C11's target-model adapter, and
project-wide the pre-existing M1 inducement-candidate detection in
`historical_replay/stage2.py`, both depend on
`market_structure.tiers.analyze_structure_tiers`, which requires a *live* MT5 terminal
for symbol metadata (`mt5.symbol_resolver.get_symbol_meta`) that
`historical_replay/data_source_patch.py` has never patched. This silently starves M1's
inducement detection in *every* historical replay this project has ever run — directly
explaining §32's "M1: zero entry arrays formed... despite 5/5 confirmations" finding,
previously classified `INSUFFICIENT_EVIDENCE` (a valid research result). That
classification is now known to be at least partly a data-source-patching artifact, not
purely a strategy-evidence finding. `src/large_smc_research/engine.py` was fixed during
this same phase to fail closed to `DATA_ERROR` when this happens, rather than silently
reporting the legitimate-looking `NO_TRADE:REJECT_NO_TARGET`. Fixing the underlying gap
itself would mean changing shared `historical_replay/data_source_patch.py` (touches the
live `SMC_CONDITIONAL_ENTRY_V2` watcher) — `SHARED_CHANGE_REQUIRED`, deliberately
deferred, same class as C14B's lifecycle-store migration.

**Consequence:** none of the three known September 2025 occurrences (E1M2, E1M3, E3M3)
currently reach `BLOCKED` when replayed through the new engine — all three now
correctly report `DATA_ERROR` (previously, before the fix, they misreported
`NO_TRADE`). The pending-entry lifecycle mechanism itself is implemented and unit-tested
against synthetic fixtures shaped exactly like a real `BLOCKED` decision, but has not
yet been exercised end-to-end against real replay-derived decisions, pending the
separate MT5-symbol-metadata fix. **Recommendation: `HOLD`** — not `NO_GO` (no evidence
against the strategy itself; both open items are infrastructure/authorization gaps, not
causal defects) and not `GO_TO_LARGER_DISCOVERY`/`CONDITIONAL_GO` (nothing would be
gained by a larger replay while target-model calls resolve to `DATA_ERROR` throughout).
