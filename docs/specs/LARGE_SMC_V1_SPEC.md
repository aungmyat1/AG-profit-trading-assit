# ST_LARGE_SMC_V1 — Research Strategy Specification

Status: **RESEARCH_DRAFT / ADVISORY_ONLY** &nbsp; Version: **1.0.0** &nbsp; Authority: `strategies/ST_LARGE_SMC_V1.yaml`

Specification phase: `ST_LARGE_SMC_V1_STRATEGY_SPECIFICATION` (2026-09-01). This document
extracts, reconciles, and freezes the smallest deterministic Large-SMC contract actually
supported by AG Profit Trading's own evidence and its approved research resource
(`smc-lss-platform`). It is a specification artifact only — no engine, workflow,
candidate ledger, or machine-readable contract change was made in this phase. See
`docs/status/ST_LARGE_SMC_V1_STRATEGY_SPECIFICATION_STATUS.md` for the phase report.

This is a separate strategy family. It does not modify, extend, or operate as a mode of
`ST_ASIAN_SWEEP_5R_V1 v1.1.1`, `SMC_3R_V1`, `ST_LIQUIDITY_SWEEP_RETEST_V1`, or
`ST_HIGH_RR_LIQUIDITY_MSS_V1`. Shared analysis capabilities may supply evidence; they do
not share strategy authority or validation evidence.

## 1. Strategy identity

`strategy_id=ST_LARGE_SMC_V1`, `version=1.0.0`, `family=SMART_MONEY_CONCEPT`,
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

## 7. Timeframe roles (C02) — `PARTIALLY_RESOLVED`, **BLOCKING — primary fork, see UC-001**

`ST_LARGE_SMC_V1.yaml` already signs coarse buckets: `D1=NARRATIVE_AND_EXTERNAL_STRUCTURE`,
`H4=CONTEXT_AND_LOCATION`, `H1=SETUP_CONTEXT`, `M15=CONFIRMATION_CANDIDATE`, `M5` and
`M1=UNSIGNED`. These are role *labels*, not gate-level assignments (no field says which
single timeframe performs bias vs. structure vs. POI vs. liquidity vs. activation vs.
confirmation vs. entry).

**These signed buckets conflict with every candidate implementation available:**

| Source | Authority level | Scheme |
|---|---|---|
| `ST_LARGE_SMC_V1.yaml` (signed) | 2 | D1 (narrative) / H4 (context+location) / H1 (setup) / M15 (confirmation) |
| AG's own frozen E1-E3/M1-M3 (Stage1/Stage2, golden-validated) | 3 | D1 (E1 reference only) / H1 (all structure/location/liquidity) / M5 (all confirmation/entry) — **no H4 role, no M15 role** |
| `smc-lss-platform` ST-C1 v1.1.0 | 4 | H1 (bias/structure/POI) / M5 (trigger/execution) — D1 only as an optional POI origin (`D1_GAP`), **no H4 role** |

No source resolves this. Adopting the AG-frozen E/M pipeline as-is would mean
`ST_LARGE_SMC_V1.yaml`'s own signed H4/M15 roles go unused (`SEMANTIC_MISMATCH`, spec
section 43) — not a simple reuse. Keeping the signed D1/H4/H1/M15 scheme means H4-role
and M15-role logic must be newly built, with no existing AG implementation or external
research source defining what "H4 context and location" or "M15 confirmation" would
concretely mean at gate level. → **UC-001, BLOCKING, `OWNER_DECISION_REQUIRED`** (§16).

## 8. Directional model (C03) — `UNRESOLVED_CONTRACT`, BLOCKING

No field in `ST_LARGE_SMC_V1.yaml` establishes a directional rule at all (the
`location_model.qualification_rule` is `UNSIGNED`, and there is no `directional_model`
key). Two candidates exist:

- `RESEARCH_REFERENCE`: ST-C1 v1.1.0 G1 — bullish requires a confirmed H1 HH *and*
  confirmed H1 HL *and* the most recent H1 break is a bullish BOS/CHoCH through the
  protected low; symmetric for bearish; simultaneous-false-on-both is a hard reject
  (`neutral_bias`), no fallback direction.
- `CANDIDATE_FOR_SPEC` (higher authority, level 3): AG's own `EConditionResult` (emitted
  by E1/E2/E3) already carries a computed `direction` field per event — a working,
  frozen implementation, contingent on UC-001 resolving in favor of the E/M-pipeline
  timeframe scheme.

→ **UC-002, BLOCKING.**

## 9. Structural context (C04) — `PARTIALLY_RESOLVED`, BLOCKING

`location_model` enumerates `external_liquidity`, `internal_liquidity`,
`premium_discount`, `order_block`, `fair_value_gap`, `supply_demand`,
`protected_highs_lows` as `CANDIDATE_INPUT` — the *category list* is signed;
`qualification_rule` (which are mandatory vs. advisory, exact definitions) is
`UNSIGNED`. ST-C1 G2/G3 (`RESEARCH_REFERENCE`) defines a concrete dealing-range +
BOS/CHoCH/MSS model with an ATR close-buffer (`close_buffer_atr_mult=0.10`). AG's own
E1/E2/E3 already implement concrete D1-gap-reaction, H1-POI-reaction, and
H1-sweep-reclaim detectors (`CANDIDATE_FOR_SPEC`, level 3, contingent on UC-001).
→ **UC-003, BLOCKING.**

## 10. Location / POI (C05) — `PARTIALLY_RESOLVED`, BLOCKING

Same candidate-input enumeration as C04; `qualification_rule=UNSIGNED`. AG's own
`src/entry_confirmation/poi.py` (used by E2) is a `CANDIDATE_FOR_SPEC` reuse candidate
for an H1 POI definition. ST-C1 G5 (`RESEARCH_REFERENCE`) gives a precise, ATR-sized
3-candle FVG / order-block / D1-gap POI definition with freshness (`FRESH` /
`MITIGATED` / `INVALIDATED`) and max-age gating — more precise than anything AG has
signed, but external-authority only. → **UC-004, BLOCKING.**

## 11. Liquidity requirement (C06) — `PARTIALLY_RESOLVED`, BLOCKING

`confirmation_sequence.liquidity_event=REQUIRED_CANDIDATE` — a liquidity event being
*mandatory* is signed. Its exact definition (external vs. internal, wick-only vs.
close-back reclaim, which levels qualify) is `UNSIGNED`. AG's own
`src/liquidity/status.py` (`RECLAIMED` semantics, used by E3) and
`src/liquidity/hierarchy.py` (`InducementCandidate`, used by M1) already distinguish
target liquidity from inducement/engineered liquidity — `CANDIDATE_FOR_SPEC`, directly
satisfies the C22 requirement to keep those concepts separate. `v3.6.yaml`
(`RESEARCH_REFERENCE`) gives explicit wick-ratio thresholds (`sweep_wick_ratio_min=0.5`
for E3-style events, `reaction_wick_ratio_min=0.4` for E1/E2-style events) that neither
AG's own code nor ST-C1 v1.1.0 states inline. → **UC-005, BLOCKING.**

## 12. Activation event (C07) — `UNRESOLVED_CONTRACT`, BLOCKING

`ST_LARGE_SMC_V1.yaml` does not separate "context exists" from "candidate activated" —
`confirmation_sequence` bundles liquidity event, MSS/CHoCH, and displacement into one
undifferentiated required set with no ordering. AG's own E1/E2/E3
`eligible_for_confirmation` flag is structurally an activation boundary already
(`CANDIDATE_FOR_SPEC`, level 3, contingent on UC-001). ST-C1 G6's
`price_enters_fresh_htf_poi` step is a comparable `RESEARCH_REFERENCE`.
→ **UC-006, BLOCKING.**

## 13. Entry confirmation (C08) — `PARTIALLY_RESOLVED`, BLOCKING

`confirmation_sequence` signs `market_structure_shift_or_choch=REQUIRED_CANDIDATE` and
`displacement=REQUIRED_CANDIDATE` (both mandatory). `entry_array=UNSIGNED`; event
ordering/timing/bar limits = `UNSIGNED`. AG's own M1/M2/M3 already implement exactly
this shape end-to-end (inducement→CHoCH→displacement→entry-array for M1;
zone-invalidation→displacement→entry-array for M2; sweep-reclaim→CHoCH→displacement→
entry-array for M3) — frozen, `AG_NATIVE`, golden-validated (`CANDIDATE_FOR_SPEC`,
level 3, contingent on UC-001). → **UC-007, BLOCKING.**

## 14. Entry model (C09) — `UNRESOLVED_CONTRACT`, BLOCKING, fork — see UC-008

`entry.timeframe/trigger/order_type/expiry` are all `UNSIGNED`. Two non-converging
candidate families exist: ST-C1 G6 (one linear gate → market entry at next-bar-open
after the M5 confirmation close) vs. AG's own frozen M1/M2/M3 (three parallel models
with distinct entry references — pullback/FVG midpoint, OB∩FVG "Gold Zone" midpoint,
post-≥50%-retrace IFVG midpoint). → **UC-008, BLOCKING, `OWNER_DECISION_REQUIRED`.**

## 15. Invalidation / stop (C10) — `UNRESOLVED_CONTRACT`, BLOCKING, fork

`exit_and_lifecycle.initial_stop=UNSIGNED`. ST-C1 G7 (`RESEARCH_REFERENCE`) gives one
unified stop rule (closest of protected-swing-opposite / POI-far-boundary /
displacement-origin, plus an ATR buffer). `v3.6` gives three distinct per-M-model stop
formulas instead. These do not converge. → **UC-009, BLOCKING.**

## 16. Target model (C11) — `UNRESOLVED_CONTRACT`, BLOCKING, high-confidence candidate

`exit_and_lifecycle.profit_targets=UNSIGNED`. Unlike C09/C10, both independent external
documents *converge*: nearest unswept external liquidity beyond entry (primary),
fallback to nearest LTF swing extremum, `REJECT_NO_TARGET` if neither exists, never a
synthetic fixed-R substitute (`RESEARCH_REFERENCE`, cross-source agreement raises
confidence but does not by itself constitute AG adoption). No 3R/5R/40:60/75:25 ratio
from any other AG strategy is inherited. → **UC-010, BLOCKING but lower-priority given
convergence.**

## 17. Expiry (C12) — `UNRESOLVED_CONTRACT`, BLOCKING

`maximum_holding_period=UNSIGNED`; no separate context/activation/confirmation expiry
exists. `v3.6` (`RESEARCH_REFERENCE`) offers `ttl_bars=1` for signal-level expiry and
horizon-based time-stops (12h/24h/120h by E×M combination) plus weekend close. No AG-
signed value exists at any granularity. → **UC-011, BLOCKING.**

## 18. Candidate lifecycle (C13) — `PARTIALLY_RESOLVED`, BLOCKING (engine-level)

`decision_states=[READY, WATCH, NO_TRADE, DATA_ERROR, EXPIRED, BLOCKED]` is signed and
identical to the vocabulary used by every other AG strategy — `RESOLVED` /
`REUSE_EXISTING_AG` for the *external* result vocabulary. The *internal* candidate
lifecycle (context found → location active → waiting-liquidity → waiting-confirmation →
research-qualified → invalidated/expired) has no signed field. AG's own
`QualifiedEEvent.is_eligible_at(t)` time-varying eligibility model (Stage1) is a
`CANDIDATE_FOR_SPEC` reference of higher authority than `v3.6`'s 9-state
`WAIT_HTF→…→COOLDOWN/NO_GO/ERROR` machine. → **UC-012, blocking for a future engine, not
for this document.**

## 19. Duplicate / re-entry (C14) — `UNRESOLVED_CONTRACT`, BLOCKING

No field addresses this at all. `v3.6` (`RESEARCH_REFERENCE`) offers
`one_signal_per_structure`, a `structure_key=[symbol, variant, structure_type,
creation_index]` identity, and `ttl_bars`. Not yet AG-adopted. Persistence/ledger design
is out of scope for this phase (spec section 35/38) but the *policy* itself is core
semantics needed before any ledger is designed. → **UC-013, BLOCKING.**

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
other strategy uses). Only `warmup` (minimum history per timeframe) is `UNSIGNED`, and
is genuinely contingent on UC-001 (timeframe roles) resolving first.

## 22. Multi-symbol behavior (C17) — `RESOLVED`

No cross-symbol/correlation evidence exists anywhere in the contract or research
sources. Per spec section 39, absent evidence the default is single-symbol-independent
evaluation; portfolio/correlation policy remains out of scope and downstream
(`NOT_REQUIRED` here).

## 23. Conflicting evidence (C18) — `UNRESOLVED_CONTRACT`, downstream-blocking

No AG-signed conflict-resolution rule exists (e.g. D1 bullish vs. H4 bearish). This
contract cannot be meaningfully resolved before C02/C03/C04 are frozen — it is blocking
only in the sense that it inherits UC-001/UC-002/UC-003's blocking status.
→ **UC-015.**

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

| ID | Contract | Blocking | Summary |
|---|---|---|---|
| UC-001 | C02 Timeframe roles | **BLOCKING — primary fork** | Signed D1/H4/H1/M15 conflicts with AG's own frozen D1/H1/M5 E/M pipeline and with ST-C1's H1/M5 scheme. See §16. |
| UC-002 | C03 Directional model | BLOCKING | No signed rule; candidates from ST-C1 G1 and AG's own E-condition `direction` field, contingent on UC-001. |
| UC-003 | C04 Structural context | BLOCKING | Candidate-input list signed; qualification rule unsigned. |
| UC-004 | C05 Location/POI | BLOCKING | Candidate-input list signed; exact POI definition unsigned. |
| UC-005 | C06 Liquidity requirement | BLOCKING | Mandatory-yes signed; exact sweep/reclaim criteria unsigned. |
| UC-006 | C07 Activation event | BLOCKING | No context-vs-activated boundary defined. |
| UC-007 | C08 Entry confirmation | BLOCKING | MSS/CHoCH+displacement mandatory signed; entry-array requirement and ordering unsigned. |
| UC-008 | C09 Entry model | BLOCKING — fork | ST-C1 single-gate market entry vs. AG's own M1/M2/M3 multi-model limit-style entries. |
| UC-009 | C10 Invalidation/stop | BLOCKING — fork | ST-C1 unified stop rule vs. v3.6 per-model stop formulas. |
| UC-010 | C11 Target model | BLOCKING (lower priority) | Two sources converge on nearest-unswept-liquidity-then-LTF-swing; not yet AG-adopted. |
| UC-011 | C12 Expiry | BLOCKING | No signed value at any granularity. |
| UC-012 | C13 Candidate lifecycle (internal) | BLOCKING (engine-level) | Result vocabulary resolved; internal state machine unresolved. |
| UC-013 | C14 Duplicate/re-entry | BLOCKING | No policy signed; v3.6 offers a candidate. |
| UC-014 | C15 Time restrictions | Non-blocking | No session field; plausible session-independence is an inference, not a decision. |
| UC-015 | C18 Conflicting evidence | Downstream-blocking | Inherits UC-001/002/003's unresolved status. |
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

## 30. Owner decision required — UC-001 (primary)

**CONTRACT:** C02 — which timeframes perform bias/structure/location/liquidity/
activation/confirmation/entry for `ST_LARGE_SMC_V1`?

**CURRENT EVIDENCE:** `ST_LARGE_SMC_V1.yaml` signs D1(narrative)/H4(context+location)/
H1(setup)/M15(confirmation), with M5/M1 unsigned. No AG implementation or research
source defines H4-role or M15-role logic at gate level.

**OPTION A — keep the signed D1/H4/H1/M15 scheme.** Requires new capability for H4
context/location and M15 confirmation logic; no existing AG code or external research
source to adapt from at that granularity; `NEW_CAPABILITY_NEEDED` throughout.

**OPTION B — revise to D1/H1/M5, matching AG's own frozen E1-E3/M1-M3 pipeline.**
Reuses six already-implemented, golden-validated modules end-to-end
(`CANDIDATE_FOR_SPEC` per §25); requires a formal spec revision to the yaml's
`timeframe_responsibilities` field (H4 and M15 roles would be retired, not merely left
unsigned) plus explicit provenance recording that the reused modules were not originally
built "for" this strategy.

**IMPACT:** Option B resolves UC-002 through UC-007 in large part by adoption rather
than new design; Option A leaves them fully open with no implementation path evident in
either AG or the approved research source.

**RECOMMENDATION IF EVIDENCE SUPPORTS ONE:** Option B — the only path with a concrete,
already-frozen, already-validated implementation; Option A has no such implementation
anywhere in scope.

**OWNER_DECISION_REQUIRED.**

## 31. Secondary owner decisions (contingent on UC-001)

**UC-008 (C09 entry model):** Option A = ST-C1's single linear gate (next-bar-open
market entry). Option B = AG's own frozen M1/M2/M3 (three parallel limit-style entry
references). Recommendation if UC-001 resolves to Option B above: adopt M1/M2/M3
(reuse, already validated); otherwise `UNRESOLVED_CONTRACT` stands. `OWNER_DECISION_REQUIRED`, deferred until UC-001 is settled.

**UC-009 (C10 invalidation/stop):** Option A = ST-C1's unified stop-selection rule.
Option B = per-M-model stop formulas from `v3.6`, consistent with adopting M1/M2/M3 for
UC-008. Same dependency; `OWNER_DECISION_REQUIRED`, deferred until UC-001/UC-008 are
settled.
