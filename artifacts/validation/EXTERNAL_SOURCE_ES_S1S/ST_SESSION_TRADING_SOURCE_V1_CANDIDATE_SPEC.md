# ST_SESSION_TRADING_SOURCE_V1 — CANDIDATE SPECIFICATION

```
identity           = ST_SESSION_TRADING_SOURCE_V1
version            = 0.1.0
status             = SPEC_FROZEN_NOT_IMPLEMENTED
enabled_component  = SWEEP
RANGE_COMPONENT    = SPEC_UNRESOLVED
TREND_COMPONENT    = SPEC_UNRESOLVED
demo_live_authority = NONE (research spec only)
```

Relationship to `ST_ASIAN_SWEEP_5R_V1 v1.1.1`: **`RELATED_LINEAGE_DIFFERENT_EXECUTABLE_SEMANTICS`**, per P1. v1.1.1 is preserved unchanged (`PRESERVED_EXISTING_EXECUTABLE_LINEAGE`) — this document does not modify, repair, rename, or supersede it. The two now knowingly diverge on stop/R-unit geometry; that divergence is recorded, not resolved, by this document.

## Native timeframe contract

`PRIMARY_TIMEFRAME = M15`, `SIGNAL_TIMEFRAME = M15`, `EXECUTION_TIMEFRAME = M15`, `H1_REQUIRED = false`, `M1_REQUIRED = false` — carried forward from ES-S1S unchanged (no new primary-source evidence contradicts it).

## Entry semantic — carried forward, `ENTRY_SEMANTIC_PARITY = SUPPORTED`

Strict boundary penetration (wick beyond Asian High/Low) + candle close back inside the range. Entry price = the qualifying candle's own close (its body edge on the sweep side). No resting/pending order — fill is synchronous with signal detection, at that candle's own close.

## P4 — Source stop model: `SOURCE_STOP_MODEL_STATUS = VERIFIED`

`A = AsianHigh - AsianLow`

```
LONG  (sweep of Asian Low):  SL = Entry − 0.25 × A
SHORT (sweep of Asian High): SL = Entry + 0.25 × A
```

Evidence tier: `SIGNED_SOURCE_SPECIFICATION` / `PRIMARY_FLOWCHART` — the source states, identically and without exception across every independent "official strategy specification" restatement, `SL Distance = Asian Range × 0.25` and `SL = Entry ± SL_dist`. No competing anchor point (Asian boundary itself, or the sweep wick extreme) is ever presented in the source as an alternative "official" formula — those are hypotheses this mission's own prompt raised for evaluation, not variants that actually appear in the source text. The only real variation found was a later `+3.0 pip` buffer, which was explicitly introduced to hit one specific benchmark price and is excluded here as `OUTCOME_DERIVED_INTERPRETATION` per P3.

`TRADE_GENERATION_CRITICAL_BLOCKER = false` for stop geometry.

## P5 — R-unit and 5R target: `VERIFIED`

```
INITIAL_RISK = abs(Entry − SL) = 0.25 × A   (by construction, given P4)

LONG:  TP2 = Entry + 5 × INITIAL_RISK = Entry + 1.25 × A
SHORT: TP2 = Entry − 5 × INITIAL_RISK = Entry − 1.25 × A
```

- `5R_MULTIPLIER_PARITY` (vs. `ST_ASIAN_SWEEP_5R_V1 v1.1.1`): **YES** — both use a ×5 multiplier.
- `R_UNIT_PARITY`: **NO** — v1.1.1's R-unit is the sweep-wick structural distance; this candidate's R-unit is `0.25 × A`. This is the same conflict ES-S1S found, now stated as two independent, separately-named facts rather than one conflated "contract conflict," per this mission's P5 instruction.

## P6 — Partial + BE state machine

Source-supported facts (repeated identically across independent "official flowchart" restatements, evidence tier `PRIMARY_FLOWCHART`):
1. Leg A = 75% of position, target = the **opposite** Asian boundary (short sweep → Asian Low; long sweep → Asian High).
2. Leg A fill is a precondition for the breakeven action — the source states the BE move happens *upon* the partial fill, not independently of it.
3. BE price = the original entry price (stated in the worked mechanics description of the trade breakdown, not the sealed benchmark table itself — evidence tier `SECONDARY_INTERPRETATION`, `STRONGLY_SUPPORTED` not `VERIFIED`).
4. Whether spread/commission adjusts the BE level: **MISSING** — never addressed. Not invented; BE is taken as the raw entry price with no cost adjustment, and this omission is recorded, not silently resolved.
5. Runner (Leg B, 25%) target = the 5R level from P5.
6. Same-candle collision between the partial-target touch and any other exit condition: **MISSING** from source — resolved only via the M15 ambiguity contract below (P9), never invented here.

```
OPEN
  → PARTIAL_ELIGIBLE        (position open, opposite boundary not yet touched)
  → PARTIAL_FILLED           (75% closed at opposite boundary; triggers BE arming)
  → RUNNER_BE_ACTIVE         (25% remains, SL = Entry)
  → RUNNER_EXIT              (RUNNER_BE_STOP  if BE re-touched
                               | RUNNER_TARGET_HIT if 5R level reached)
```

No transition beyond this is source-supported; none invented.

## P7 — Session-window adjudication

The source text, in the specific turn that reframed the strategy around the "official flowchart," explicitly **distinguishes** a new-entry cutoff from a management-end time in the same sentence (*"New entries are restricted to 07:00–16:00 UTC. Open trades continue to be managed through 22:00 UTC"*) — these are not competing versions of one field, they are two different concepts, confirming this mission's own hypothesis in P7.

```
SETUP_DETECTION_START   = 07:00 UTC   (STRONGLY_SUPPORTED — Asian session close; consistent throughout)
SETUP_DETECTION_END     = not separately stated; folds into NEW_ENTRY_CUTOFF (MISSING as a distinct concept)
NEW_ENTRY_START          = 07:00 UTC   (VERIFIED — consistent across every turn)
NEW_ENTRY_CUTOFF         = AMBIGUOUS   (candidate value 16:00 UTC was introduced framed as a flowchart re-alignment, tier SECONDARY_INTERPRETATION not a verbatim flowchart quote, then later moved to 18:00 UTC for explicitly outcome-derived reasons — excluded per P3. No non-outcome-derived, source-verified clock value survives.)
POSITION_MANAGEMENT_END  = 22:00 UTC   (STRONGLY_SUPPORTED — stated identically across multiple independent turns)
FORCED_EXIT_TIME         = 22:00 UTC   (STRONGLY_SUPPORTED — same value, same evidence)
```

`NEW_ENTRY_CUTOFF = AMBIGUOUS` is `TRADE_GENERATION_CRITICAL` (see governance list below) — preregistered unresolved, not defaulted.

## P8 — Remaining occurrence-generation rules

| Field | Status | Criticality | Note |
|---|---|---|---|
| `ENTRY_EXPIRY` | MISSING | NONCRITICAL | Not applicable under the verified entry model — entry is a synchronous fill at candle close, not a resting order, so no expiry window is needed for this rule to be deterministic. |
| `MAX_ENTRIES_PER_SESSION` / `MAX_ENTRIES_PER_DAY` | MISSING | **TRADE_GENERATION_CRITICAL** | Every numeric value in the source (1, then 3) was introduced explicitly to chase the benchmark's trade count (`OUTCOME_DERIVED_INTERPRETATION`) — excluded. No non-outcome-derived value exists. **Preregistered unresolved**, governance required before implementation. |
| `REPEATED_SAME_SIDE_SWEEP_POLICY` | MISSING | Folds into the item above | Not separately addressed by source. |
| `OPPOSITE_SIDE_SWEEP_POLICY` | MISSING | Folds into the item above | Sequential (non-same-candle) opposite sweeps within one day are never addressed; distinct from the existing `v1.1.1` same-*candle*-only dual-sweep handling. |
| `TIGHT_RANGE_FILTER` (existence) | STRONGLY_SUPPORTED | **TRADE_GENERATION_CRITICAL** | Citing this program's own prior committed finding (`EXTERNAL_SOURCE_STRATEGY_SPEC_DRAFT.md` rule #17, established before this mission's benchmark firewall reiteration, not re-derived here): the source's own sealed benchmark evidence independently confirms a genuine too-tight-range no-trade condition exists. Existence only — not re-inspected in this mission. |
| `TIGHT_RANGE_FILTER_THRESHOLD` | MISSING | **TRADE_GENERATION_CRITICAL** | Both candidate numeric thresholds found in the source (15 pips, 10 pips) were introduced/changed explicitly to change how many benchmark trades qualified — both `OUTCOME_DERIVED_INTERPRETATION`, both excluded. **Preregistered unresolved.** |
| `END_OF_SESSION_POSITION_POLICY` | MISSING | OUTCOME_RESOLUTION_CRITICAL | The "mark-to-close at window end" behavior found in the source is self-described as the backtesting *agent's own* engine design, never attributed to the presenter/video directly — downgraded from an earlier, too-generous reading. Preregistered unresolved for outcome resolution; does not block occurrence generation itself. |

## P9 — M15-native ambiguity contract

`NATIVE_EXECUTION_TIMEFRAME = M15`, `M1_REQUIRED = false` — permanent, not to be repaired by introducing M1.

| Scenario | Resolution | Justification |
|---|---|---|
| `ENTRY_SL_SAME_BAR` | **DETERMINISTIC** | No position exists until the candle closes (entry is defined as that close); pre-close wick action is not a stop-hit against an open position. Structural, not an assumption. |
| `ENTRY_TP_SAME_BAR` | **DETERMINISTIC** | Same reasoning — the entry candle's own high/low cannot be used to evaluate an exit against a position that did not yet exist during that candle's formation. Addresses the exact gap ES-S1S left `UNHANDLED`, explicitly resolved here rather than silently inherited. |
| `SL_TP_SAME_BAR` (initial stop vs. Leg-A opposite-boundary target, later candle) | **INTRABAR_ORDER_UNRESOLVED** | No source evidence defines sequencing; no stop-first/target-first assumption is made. |
| `PARTIAL_SL_SAME_BAR` | **INTRABAR_ORDER_UNRESOLVED** | Same as above (same underlying collision). |
| `PARTIAL_TP2_SAME_BAR` (opposite-boundary partial and full 5R runner target touched before the partial has separately registered) | **INTRABAR_ORDER_UNRESOLVED** | Not addressed by source; not assumed. |
| `BE_TP2_SAME_BAR` (post-partial: breakeven stop and 5R runner target touched in the same later candle) | **INTRABAR_ORDER_UNRESOLVED** | Not addressed by source; not assumed. |

No hidden stop-first or target-first assumption is used anywhere in this table.

## Governance-required items before implementation (preregistered, not blocking this freeze)

1. `NEW_ENTRY_CUTOFF` — no source-verified clock value.
2. `MAX_ENTRIES_PER_SESSION` / `MAX_ENTRIES_PER_DAY` and the repeated/opposite-sweep policies that depend on it.
3. `TIGHT_RANGE_FILTER_THRESHOLD` — existence confirmed, numeric value not.
4. `END_OF_SESSION_POSITION_POLICY` — for outcome resolution only, not generation.
5. Whether spread/commission adjusts the breakeven level.

Each is recorded as an **explicit unresolved state**, per this mission's P11 second allowed path — none has been given an invented default.
