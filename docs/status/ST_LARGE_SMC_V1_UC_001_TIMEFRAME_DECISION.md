# ST_LARGE_SMC_V1 — UC-001 Timeframe Roles: Owner Decision Packet (2026-09-01)

Status: **OWNER_DECISION_REQUIRED**. This document does not resolve UC-001. No file
under `strategies/`, no registry entry, and no production code changed. See
`docs/specs/LARGE_SMC_V1_SPEC.md` §7/§16/§30 for the contract this narrows.

## 1. The conflict

| | Model A — signed contract | Model B — frozen AG pipeline | Model C — hybrid |
|---|---|---|---|
| D1 | YES | YES | YES |
| H4 | YES | NO (see caveat, §7) | YES |
| H1 | YES | YES | YES |
| M15 | YES | NO | NO |
| M5 | NO | YES | YES |

## 2. Model A — signed contract (D1/H4/H1/M15)

| Timeframe | Role (source) | Semantics resolved? | AG implementation exists? | Golden-validated? | New logic required? |
|---|---|---|---|---|---|
| D1 | `NARRATIVE_AND_EXTERNAL_STRUCTURE` (`ST_LARGE_SMC_V1.yaml:26`) | NO — label only, no qualification rule | Partial: E1 uses D1 as a gap *reference* timeframe, but that's Model B's D1, not a narrative-role D1 | Only via E1 (different role) | YES |
| H4 | `CONTEXT_AND_LOCATION` (`yaml:27`) | NO — label only | NO strategy-specific H4 qualification anywhere in `src/`; only generic H4 candle/resampling support exists (`historical_replay/resampler.py`, `mt5/market_data.py`) | NO | YES |
| H1 | `SETUP_CONTEXT` (`yaml:28`) | NO — label only | Partial: H1 is used throughout E1/E2/E3 (reaction/POI/sweep check timeframe) and by `market_structure`/`daytrading.decision.market_bias` generally, but not tied to a "setup context" rule specific to this label | Via E1/E2/E3 (different framing) | YES |
| M15 | `CONFIRMATION_CANDIDATE` (`yaml:29`) | NO — label only | NO — no Large-SMC or E/M-pipeline confirmation logic operates on M15; confirmation in the frozen pipeline is M5 (M1/M2/M3) | NO | YES |

**Verified: H4 and M15 appear in the signed contract but have no proven AG
implementation at gate level for the Large-SMC roles the contract assigns them.**

## 3. Model B — frozen AG pipeline (D1/H1/M5)

| Timeframe | Role | Component | Deterministic? | Frozen? | Golden-validated? |
|---|---|---|---|---|---|
| D1 | Event reference (gap existence) | E1 (`REFERENCE_TIMEFRAME_E1="D1"`, `entry_models_v1.py:58`) | YES | YES | YES (via Stage1/Stage2) |
| H1 | Structure/POI/liquidity reference + reaction check | E1 reaction check, E2 POI+check, E3 check (`CHECK_TIMEFRAME="H1"`, `entry_models_v1.py:55`) | YES | YES | YES |
| M5 | Confirmation + entry array | M1/M2/M3 (`m1_character_change_inducement.py:1`: "one of three interchangeable M5 confirmation [maneuvers]") | YES | YES | YES |

**Caveat (verified, not previously stated precisely): E3's `reference_timeframe` is NOT
hardcoded to H1** — it copies whatever timeframe the caller-supplied `LiquidityLevel`
carries (`e3_liquidity_sweep.py:7-11,58`: *"a caller-supplied `liquidity.LiquidityLevel`
may originate on H1, H4, or D1... E3 never forces every liquidity level to originate on
H1"*). E3's mechanical sweep+reclaim *check* logic is always H1-scale, but an H4-origin
liquidity level can already be passed in as a reference without new code. This means
Model B is not strictly H4-free — H4 already has a narrow, optional entry point as a
liquidity-level origin, just not a primary structural/context role.

**Golden validation scope, verified:** the `events=18, setups=54, arrays=9, ready=3`
baseline (`docs/status/TRUE_STAGE2_ORACLE_RECONCILIATION_STATUS.md:37`) proves E1/E2/E3
+ M1/M2/M3 reproduce a frozen oracle deterministically — it validates the *research
pipeline's internal consistency*, not trading profitability, and not that this pipeline
is "the" Large-SMC strategy.

## 4. Model C — hybrid (D1/H4/H1/M5), not an existing authority

Treated as a candidate only; nothing in AG or the external research source specifies
this exact combination.

- Evidence for keeping H4: none direct — `ST_LARGE_SMC_V1.yaml` assigns H4 a role, but
  as shown in §2 that role has no implemented semantics; keeping H4 would carry forward
  the *label*, not a working rule.
- Evidence for replacing M15 with M5: strong — M5 is the only LTF confirmation
  timeframe with a frozen, validated AG implementation (M1/M2/M3); M15 has none.
- New integration logic needed: an H4 qualification rule (what H4 evidence, exactly,
  gates or informs a candidate) does not exist anywhere and would need to be newly
  specified and built — Model C does not inherit one "for free" from either Model A or
  Model B.
- H4 would be advisory or mandatory: **undetermined** — this itself would need to become
  a new signed field; recording it as `UNRESOLVED_CONTRACT` rather than assuming either.
- Does H4 create a new, unvalidated strategy semantic: YES — combining a still-undefined
  H4 layer with the frozen D1/H1/M5 pipeline is a semantic not validated by the existing
  golden oracle (which contains no H4 evidence at all).

## 5. Timeframe role matrix

| Role | Model A | Model B | Model C |
|---|---|---|---|
| macro context | D1 (label only, unresolved) | D1 (E1 gap reference, resolved) | D1 (as Model B) |
| HTF structure | H4 (label only, unresolved) / H1 (label only) | H1 (E1/E2/E3, resolved) | H1 (as Model B) + H4 (UNRESOLVED) |
| POI/location | H4 (label only, unresolved) | H1 (E2/`poi.py`, resolved) | H1 (as Model B) + H4 (UNRESOLVED) |
| liquidity event | UNRESOLVED (no timeframe named for this role at all in the yaml) | H1 primary, H4-origin optional input (E3, resolved+caveat) | as Model B |
| activation | UNRESOLVED | H1/M5 boundary (`eligible_for_confirmation`, resolved) | as Model B |
| confirmation | M15 (label only, unresolved) | M5 (M1/M2/M3, resolved) | M5 (as Model B) |
| entry | UNRESOLVED (entry.timeframe=`UNSIGNED`) | M5 (M1/M2/M3 entry arrays, resolved) | M5 (as Model B) |

## 6. Direct comparison

| Factor | Model A | Model B | Model C |
|---|---|---|---|
| SIGNED_CONTRACT_PRESERVATION | HIGH (as-written) | LOW (H4/M15 fields would need revision) | MEDIUM (H4 kept, M15 dropped) |
| AG_EXISTING_REUSE | LOW (only generic candle/resampling support) | HIGH (6 frozen modules directly applicable) | MEDIUM (D1/H1/M5 core reused, H4 layer new) |
| GOLDEN_RESEARCH_COVERAGE | NONE (oracle contains no H4/M15 Large-SMC evidence) | FULL for D1/H1/M5 mechanics (research-consistency only, not profitability) | PARTIAL (core covered, H4 layer uncovered) |
| PRIMARY_EXTERNAL_RESEARCH_SUPPORT | NONE — ST-C1/v3.6 use H1/M5 (D1 optional), never H4, never M15 | STRONG — matches ST-C1's H1/M5 core exactly, plus D1 as v3.6's E1 does | PARTIAL — D1/H1/M5 supported, H4 layer has no external precedent either |
| NEW_CAPABILITY_REQUIRED | HIGH — H4 context/location rule and M15 confirmation rule both from scratch | LOW — adapters only (see §8) | MEDIUM — H4 rule from scratch, M5 core reused |
| NEW_ADAPTERS_REQUIRED | N/A — new capability, not adapters (nothing to adapt from) | LOW — typed wrappers around E1-E3/M1-M3 outputs | LOW for D1/H1/M5, N/A (new capability) for H4 |
| IMPLEMENTATION_COMPLEXITY | HIGH | LOW | MEDIUM |
| SEMANTIC_CHANGE_REQUIRED | NONE to the yaml; HIGH in practice to make the labels real | HIGH to the yaml (H4/M15 fields retired) | MEDIUM (M15 dropped, H4 kept but redefined from label to rule) |
| REPLAY_IMPACT | Would eventually need a new, separate research pipeline for H4/M15 evidence — Stage1/Stage2 stay untouched either way in this phase | Stage1/Stage2 remain the natural fit, no new pipeline implied | Would need a new parallel path for H4 evidence alongside the existing Stage1/Stage2 D1/H1/M5 flow |
| FUTURE_BACKTEST_COMPLEXITY | HIGH (two under-specified timeframes to first define, then test) | LOW (mechanics already exercised by golden oracle) | MEDIUM |
| NO_LOOKAHEAD_RISK | MEDIUM — H4 close-availability/broker-day anchoring must be handled correctly if H4 is ever implemented (see §9); not yet exercised for Large-SMC | LOW — D1/H1/M5 closed-bar handling already exercised by the golden oracle | MEDIUM — same H4 risk as Model A, isolated to the new layer |
| STRATEGY_SPEC_REWORK_REQUIRED | LOW to the document itself, HIGH to give the existing labels real meaning | HIGH — `timeframe_responsibilities` fields would be revised, not merely filled in | MEDIUM — M15 role retired, H4 role redefined from label to concrete rule |

## 7. Model A — verified consequences

- Signed strategy contract preserved: YES, structurally — the field names/labels stay.
- H4 logic required: YES, confirmed — none exists.
- M15 logic required: YES, confirmed — none exists.
- Frozen D1/H1/M5 E/M pipeline becomes research reference only: YES — it would inform
  design by analogy but could not be wired in directly under Model A's role labels
  without first redefining what "H4 context and location" and "M15 confirmation" mean.
- New Stage1/adapter semantics potentially required: YES — a new context-production
  stage would eventually be needed for H4/M15 evidence; Stage1/Stage2 as they exist
  today do not produce it.
- Existing golden oracle not directly representative of the final strategy: YES,
  confirmed — the oracle exercises D1/H1/M5 mechanics only.

## 8. Model B — verified consequences

- Maximum reuse of frozen AG research: YES.
- Reuse of E1/E2/E3: YES, directly — `EConditionResult` already typed and provenance-
  bearing.
- Reuse of M1/M2/M3: YES, directly — entry arrays and displacement checks already
  implemented.
- Existing golden oracle remains relevant to research behavior: YES, for the mechanics;
  NOT as profitability or Large-SMC-authority evidence (repeated from §3, deliberately
  not softened).
- Signed H4/M15 strategy fields require revision: YES, confirmed — `yaml:27,29` would
  change from `CONTEXT_AND_LOCATION`/`CONFIRMATION_CANDIDATE` to `NOT_USED` or be
  removed, which is a strategy-semantic edit, not a documentation formality.
- Strategy semantics change from the currently signed contract: YES — this is precisely
  why owner authorization is required rather than treating Model B as an obvious
  cleanup.
- Owner authorization required: YES.

## 9. Model C — verified consequences

- H4 retained: YES, as a field/label; not as a working rule (same gap as Model A's H4).
- M5 entry pipeline reusable: YES (identical to Model B for that layer).
- M15 role removed: YES — this alone is a smaller, more contained semantic edit than
  Model B's full H4+M15 removal.
- New H4 integration contract required: YES — Model C does not avoid the work Model A
  defers; it isolates it to one timeframe instead of two.
- Existing golden validation only partial: YES, confirmed (§3/§6).
- New semantic combination not currently frozen anywhere: YES — no source (AG or
  external) specifies D1+H4+H1+M5 together.

## 10. Primary external research support (smc-lss-platform)

| Timeframe | ST-C1 v1.1.0 | specs/v3.6.yaml | ST-C3 (reference only) |
|---|---|---|---|
| D1 | OPTIONAL — `poi_origin: D1_GAP` is one of three POI origins, not mandatory (`ST-C1_v1.1.0.yaml` G5) | MANDATORY for E1 (`gap_max_age_d1_bars`) | NOT_USED |
| H4 | NOT_USED | NOT_USED | MANDATORY (bias/macro structure/sweep context) — but ST-C3 is excluded from Large-SMC authority per the resource map |
| H1 | MANDATORY (bias, external_structure, htf_poi) | MANDATORY (E1 reaction check, E2, E3 all H1-scale) | NOT_USED (ST-C3 uses H4/M15/M3, not H1) |
| M15 | NOT_USED | NOT_USED | MANDATORY (sweep/displacement/BOS/dealing range/OTE/FVG-OB) — excluded, same reason |
| M5 | MANDATORY (m5_trigger, execution) | MANDATORY (M1/M2/M3) | NOT_USED |

No approved external source supports H4 or M15 as Large-SMC-authority timeframes; only
the explicitly-excluded ST-C3 lineage uses them, and it is excluded specifically because
"its active v1.x lineage uses H4/M15/M3 and deliberately excludes material stages"
(`docs/architecture/STRATEGY_WORKFLOW_RESOURCE_MAP.md:40-42`).

## 11. Signed-contract provenance (Model A)

`strategies/ST_LARGE_SMC_V1.yaml` and its D1/H4/H1/M15 fields were introduced in a
single commit, `e9487bc` ("feat: register ST_LARGE_SMC_V1 v1.0.0 as an independent
research strategy", 2026-09-01T14:46:08+06:30) — there is no separate prior commit,
research note, or design doc establishing why D1/H4/H1/M15 specifically was chosen; the
scheme was written as initial registration scaffolding alongside the rest of the
`UNSIGNED` contract. **The contract is signed structurally (it is the frozen
`ST_LARGE_SMC_V1.yaml` on record, level-2 authority) but its H4/M15 semantics were never
implemented or independently derived from research — it reads as draft scaffolding for
where evidence was anticipated to matter, not as an owner ruling that H4/M15
specifically must be used.** This distinction does not weaken the document's formal
authority; it explains why "signed" and "semantically resolved" diverge here.

## 12. AG frozen pipeline provenance (Model B)

The golden vertical slice regression lock (`AG_TWO_STAGE_GOLDEN_VERTICAL_SLICE_V1`,
commit `47ed991`, 2026-09-01T02:10:15+06:30) froze Stage1/Stage2 and the E1-E3/M1-M3
pipeline **roughly 12.5 hours before** `ST_LARGE_SMC_V1` was registered the same day.
The pipeline is part of `SMC_CONDITIONAL_ENTRY_V2`, the general entry-confirmation
skill's research infrastructure — its docstrings and module names give no indication it
was built "for" Large-SMC specifically; it evolved as generic SMC entry-confirmation
research reusable by any consumer. This matters for the owner decision: Model B's
strength is reuse-of-proven-mechanics, not "this is what Large-SMC was always meant to
be" — that link would be established by the owner's adoption decision, not by prior
intent.

## 13. Exact E/M timeframe mapping

| Component | Reference timeframe | Check/reaction timeframe | Role |
|---|---|---|---|
| E1 (`e1_daily_gap_reaction.py`) | D1 (gap existence) | H1 (reaction check) | HTF event: D1 gap fill/reaction |
| E2 (`e2_h1_poi_reaction.py`) | H1 (POI, via `poi.py`) | H1 (touch) + M5 (reaction candle passed to displacement check) | HTF event: H1 POI reaction |
| E3 (`e3_liquidity_sweep.py`) | caller-supplied — H1, H4, or D1 (`LiquidityLevel.timeframe`, verbatim) | H1 (sweep+reclaim state machine, always) | HTF event: liquidity sweep+reclaim, requires `RECLAIMED` status |
| M1 (`m1_character_change_inducement.py`) | — | M5 | LTF confirmation: inducement sweep → CHoCH → displacement → entry array |
| M2 (`m2_supply_demand_shift.py`) | — | M5 | LTF confirmation: opposing-zone invalidation → new zone → displacement → entry array |
| M3 (`m3_sweep_drop_pump.py`) | — | M5 | LTF confirmation: HTF sweep+reclaim → CHoCH → displacement → IFVG → 50% pullback entry |

## 14. Downstream contract impact (explanatory only — not resolved here)

| Contract | Model A | Model B | Model C |
|---|---|---|---|
| C03 Directional model | NEW_CONTRACT_REQUIRED | SUPPORTED_BY_EXISTING_RESEARCH (E-condition `direction` field) | SUPPORTED (D1/H1/M5 core), PARTIAL if H4 must also vote on direction |
| C04 Structural context | NEW_CONTRACT_REQUIRED | SUPPORTED_BY_EXISTING_RESEARCH | PARTIAL (H1 core supported, H4 layer new) |
| C05 Location/POI | NEW_CONTRACT_REQUIRED | SUPPORTED_BY_EXISTING_RESEARCH (`poi.py`, E2) | PARTIAL (H1 POI supported, H4 POI new) |
| C06 Liquidity requirement | PARTIAL (E3 already accepts H4-origin liquidity levels as an input, even though the yaml's H4 role is currently labeled differently) | SUPPORTED_BY_EXISTING_RESEARCH | SUPPORTED (as Model B, plus optional H4-origin input already available) |
| C07 Activation | NEW_CONTRACT_REQUIRED | SUPPORTED_BY_EXISTING_RESEARCH (`eligible_for_confirmation`) | SUPPORTED (as Model B) |
| C08 Entry confirmation | NEW_CONTRACT_REQUIRED | SUPPORTED_BY_EXISTING_RESEARCH (M1/M2/M3) | SUPPORTED (as Model B) |
| C09 Entry model | NEW_CONTRACT_REQUIRED | SUPPORTED_BY_EXISTING_RESEARCH (M1/M2/M3 entry arrays) — still requires the separate UC-008 owner decision vs. ST-C1's model | SUPPORTED (as Model B) |
| C10 Invalidation/stop | NEW_CONTRACT_REQUIRED | PARTIAL — `v3.6` gives per-model formulas as research reference, not yet AG-coded | PARTIAL (as Model B) |
| C11 Target model | NEW_CONTRACT_REQUIRED | PARTIAL — convergent external candidate, not yet AG-adopted | PARTIAL (as Model B) |
| C12 Expiry | NEW_CONTRACT_REQUIRED | PARTIAL — `QualifiedEEvent.is_eligible_at(t)` gives a partial mechanism; explicit expiry values still research-reference only | PARTIAL (as Model B) |
| C13 Candidate lifecycle | NEW_CONTRACT_REQUIRED | PARTIAL — time-varying eligibility exists; full state machine still unresolved | PARTIAL (as Model B) |
| C18 Conflicting evidence | NEW_CONTRACT_REQUIRED, largest surface (D1 vs H4 vs H1 can each disagree) | NEW_CONTRACT_REQUIRED, smaller surface (only D1 vs H1) | NEW_CONTRACT_REQUIRED, largest surface (same as A, D1/H4/H1 can each disagree) |

## 15. New capability analysis

- **Model A:** H4 structure adapter, H4 context/location qualification rule, M15
  confirmation qualification rule, M15 FVG/entry-array logic, a new cross-timeframe
  (D1→H4→H1→M15) state transition model, and (eventually) a new Stage1-equivalent
  context-production stage for H4/M15 evidence. Nothing reusable as-is.
- **Model B:** none beyond typed adapters (§16) — no new qualification rule needed for
  the timeframe roles themselves; remaining gaps (C10-C13) are about specific
  thresholds/formulas, not new timeframe capability.
- **Model C:** H4 structure adapter and H4 context/location qualification rule (same gap
  as Model A, isolated to one timeframe); M5 side needs none (reused from Model B).

## 16. Adapter vs. new engine

- Wrapping `EConditionResult`/M1-M3 outputs into `ST_LARGE_SMC_V1`'s own
  `StrategyDecision`-shaped result = **ADAPTER_REQUIRED** (Model B, Model C's M5 side).
- Defining what H4 "context and location" or M15 "confirmation" concretely means =
  **STRATEGY_CONTRACT/NEW_CAPABILITY REQUIRED** (Model A entirely, Model C's H4 layer) —
  AG's generic H4 candle support (resampling, generic `market_structure` analysis on any
  timeframe) does not supply Large-SMC-specific semantics, exactly as spec section 20
  warns ("existing generic M15 candle support does NOT mean Large-SMC M15 entry
  semantics already exist" — the same reasoning applies to H4 here).

## 17. Replay impact

Stage1/Stage2 and the golden oracle are not modified in this phase and were not
touched. For a *future* implementation phase (not this one):

- Model B: Stage1/Stage2 can very plausibly remain unchanged and be reused/adapted
  directly; no separate research pipeline is implied by the evidence gathered here.
- Model A: would very plausibly require a **separate future research pipeline** for
  H4/M15 evidence production, since Stage1's `QualifiedEEvent` model is D1/H1-scoped and
  Stage2 only consumes M1/M2/M3 (M5-scoped) — neither currently has an H4 or M15
  concept.
- Model C: would require a new, additional H4 evidence-production path alongside the
  existing D1/H1/M5 Stage1/Stage2 flow, not a replacement of it.

No suggestion to change the frozen oracle is made or implied.

## 18. No-lookahead / timing impact

Not implemented in this phase; noted for future reference only.

- D1/H1/M5 close availability: already exercised end-to-end by the golden oracle
  (closed-bar-only, no fabricated bars — `resampler.py:4-5`).
- H4 close availability: **not naive UTC-midnight-aligned** — `historical_replay/
  resampler.py:172-203` documents a previously found-and-fixed bug: MT5's D1/H4 candles
  are anchored to the broker's own calendar day/4h boundary, not UTC buckets: *"a real
  bug found and fixed via cross-validation... MT5's D1 (and H4) candles are anchored to
  the broker's own calendar day/4h boundary... the [naive] bucket boundary is simply the
  wrong boundary for D1/H4"* — the fix, `resample_broker_aligned`, already exists and is
  validated (`SMC_3X3_HISTORICAL_VALIDATION_V1`). This is **existing, reusable**
  infrastructure for Models A/C's H4 layer, not a new problem to solve — it lowers, but
  does not eliminate, the implementation cost of retaining H4 (the semantic qualification
  rule is still the larger gap, per §15).
  - Do not reopen or re-validate this here (spec section 23) — cited as-is.
  - Per section 23, this consequence is recorded but not solved in this phase.
- M15 close availability: no bug/finding on record either way; M15 candles are
  generically supported (`resampler.py:31-32`), but as with H4, generic candle support
  is not Large-SMC-specific semantics.

## 19. Decision matrix

**UC-001 TIMEFRAME DECISION MATRIX**

| FACTOR | OPTION A | OPTION B | OPTION C |
|---|---|---|---|
| D1 | YES | YES | YES |
| H4 | YES | NO (caveat: optional E3 liquidity-origin input) | YES |
| H1 | YES | YES | YES |
| M15 | YES | NO | NO |
| M5 | NO | YES | YES |
| signed_contract_preserved | HIGH | LOW | MEDIUM |
| AG_frozen_reuse | LOW | HIGH | MEDIUM |
| golden_research_coverage | NONE | FULL (mechanics only) | PARTIAL |
| external_research_support | NONE | STRONG | PARTIAL |
| new_logic_required | HIGH | LOW | MEDIUM |
| adapter_work | N/A (new capability, not adapters) | LOW | LOW (M5 side) + N/A (H4 side) |
| semantic_change | NONE (nominal) / HIGH (functional) | HIGH | MEDIUM |
| replay_impact | new pipeline likely needed | none needed | new H4 evidence path needed |
| future_backtest_complexity | HIGH | LOW | MEDIUM |
| implementation_risk | HIGH | LOW | MEDIUM |

## 20. UC-001 owner decision required

**CURRENT CONFLICT:** `ST_LARGE_SMC_V1.yaml`'s signed `timeframe_responsibilities`
(D1/H4/H1/M15) has no implemented semantics for its H4 or M15 roles anywhere in AG or
the approved external research source. AG's own frozen, golden-validated
entry-confirmation pipeline (E1/E2/E3 + M1/M2/M3) implements a working D1/H1/M5 scheme
instead, built as generic research infrastructure roughly 12.5 hours before
`ST_LARGE_SMC_V1` was registered — not authored for this strategy.

**OPTION A — `PRESERVE_SIGNED_D1_H4_H1_M15`**
- timeframes: D1, H4, H1, M15
- benefits: no edit to the currently signed contract; H4/D1 broker-time handling already
  solved and reusable if H4 is ever built
- costs: H4 and M15 qualification rules must be designed and implemented from nothing;
  no AG or external evidence to adapt from; likely needs a new, separate research
  pipeline alongside Stage1/Stage2
- risks: HIGH implementation risk, HIGH future-backtest complexity, largest
  conflicting-evidence surface (D1/H4/H1 can each disagree)

**OPTION B — `ADOPT_FROZEN_AG_D1_H1_M5`**
- timeframes: D1, H1, M5
- benefits: reuses 6 already-implemented, golden-validated modules directly; matches the
  approved external research source's own H1/M5 core; lowest implementation risk
- costs: requires formally revising `ST_LARGE_SMC_V1.yaml`'s signed H4/M15 fields — a
  strategy-semantic edit, not a documentation cleanup
- risks: the reused pipeline was not built "for" Large-SMC — its fit must still be
  affirmatively adopted, not assumed; golden validation covers research-pipeline
  consistency only, never profitability or strategy authority

**OPTION C — `HYBRID_D1_H4_H1_M5`**
- timeframes: D1, H4, H1, M5
- benefits: retains H4 as a field without discarding the frozen D1/H1/M5 core; M15
  (the more clearly unused role — no external or internal evidence supports it at all)
  is dropped
- costs: still requires a new H4 qualification rule from scratch (same core gap as
  Option A, isolated to one timeframe instead of two); no source anywhere specifies this
  exact four-timeframe combination
- risks: MEDIUM across most factors; introduces a semantic combination the golden oracle
  does not cover at all

**EVIDENCE-BASED RECOMMENDATION = B**

**RECOMMENDATION_REASON:**
- Only Option B has a concrete, already-implemented, already golden-validated mechanism
  for every timeframe role it uses (§3, §8).
- Options A and C both require inventing an H4 qualification rule with zero AG or
  approved-external precedent (§2, §4, §10) — precisely the kind of invention this
  specification process is meant to avoid (spec section 78: "AVAILABLE CAPABILITY !=
  MANDATORY RULE", but the inverse gap here is "NO AVAILABLE CAPABILITY" for H4/M15).
- The approved external research source itself (`smc-lss-platform`) never uses H4 or
  M15 for Large-SMC — only the explicitly-excluded ST-C3 lineage does (§10).
- Option B's downstream contract impact is the most favorable across C03-C09 (§14),
  reducing — not eliminating — the remaining specification effort.
- Adopting Option B is still a strategy-semantic decision requiring explicit revision of
  already-signed yaml fields — it is a recommendation, not a fait accompli.

**OWNER DECISION REQUIRED = A / B / C**
