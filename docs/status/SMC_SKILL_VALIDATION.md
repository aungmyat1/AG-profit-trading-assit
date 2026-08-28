# SMC Foundational Skills Validation — Structure / Supply & Demand / Liquidity

2026-08-27. Scope: prove Structure → Supply & Demand → Liquidity are deterministic,
hindsight-free, multi-timeframe, and drawable — not to generate trades. Entry &
Confirmation and Trade Management remain deferred and untouched.

## 1. Scope

In scope: `market_structure/`, `supply_demand/`, `liquidity/`, a new `chart_renderer/`
package, and the three corresponding skills (`.claude/skills/` + `.agents/skills/`,
identical). Out of scope (not touched): `strategy_engine/`, `execution/`,
`trade_management/`, any entry/sizing/SL/TP/order logic.

## 2. Existing-Code Audit (Phase 0)

| Capability | Status found |
|---|---|
| Swing highs/lows, BOS, CHOCH, single-tier structure state | EXISTS (`market_structure/`, frozen Phase 2) — only exposed the *latest* of each |
| HH/HL/LH/LL labeling | MISSING |
| External vs. internal structure (two-tier) | MISSING |
| MSS as distinct from CHOCH | N/A — project never defined MSS; nothing to preserve |
| Order Blocks (PIVOT/SHADOW, lifecycle, mitigation) | EXISTS (`supply_demand/`, `AG_ORDER_BLOCK_V1`, frozen Phase 3) |
| BSL/SSL, EQH/EQL, PDH/PDL, session H/L, sweep state | EXISTS (`liquidity/`, Phase 4) |
| External/internal liquidity scoping | MISSING |
| Inducement Candidate + target relationship | MISSING |
| Engineered / retail liquidity | MISSING |
| Chart renderer | MISSING — no matplotlib/plotly anywhere |
| Walk-forward / no-hindsight / repeatability test harness | MISSING as formal, reusable tests |
| Gold benchmark dataset | MISSING |

No duplicated or conflicting definitions were found anywhere the new work touches.

## 3. Canonical Definitions (frozen this session, confirmed with owner)

- **Internal/external structure tiers**: internal = `swing_length` 5 (unchanged, same
  detector as the existing frozen `analyze_structure()`); external = `swing_length` 50 —
  matches the LuxAlgo Smart Money Concepts reference indicator's own internal/swing
  defaults (`smartmoneyconcepts` is a port of that indicator), not an arbitrary choice.
  `market_structure/tiers.py`.
- **HH/HL/LH/LL tie rule**: reuses `config/liquidity.yaml`'s
  `equal_level_tolerance_points` (converted to price via tick size) instead of a new
  tolerance. A swing within tolerance of the prior same-type swing labels toward
  continuation (HH for highs, LL for lows). First swing of each type is unclassified.
- **Renderer**: matplotlib → PNG, Agg backend, asserted on by artist/coordinate count in
  pytest, not pixel diffing. `chart_renderer/renderer.py`.
- **External/internal liquidity scope**: EXTERNAL = swing liquidity built from the
  EXTERNAL structure tier; INTERNAL = everything `liquidity_result()` already produces
  (its swing-sourced levels already use `swing_length` 5 = the internal tier;
  EQUAL_HIGHS/EQUAL_LOWS/PDH/PDL/session H/L also internal per this freeze).
  `liquidity/hierarchy.py`.
- **Inducement Candidate**: an UNSWEPT INTERNAL level strictly between current price and
  an UNSWEPT EXTERNAL level on the same side (nearer than the target). Deterministic
  relationship, not a standalone label; multiple valid candidates are all returned,
  unranked. `liquidity.hierarchy.find_inducement_candidates()`.
- **Engineered liquidity**: `RESEARCH_ONLY`, always — "inducement pattern"/"engineered"
  have no prior frozen definition. A 0-3 evidence count only, never a probability.
- **Retail liquidity proxy**: `VALIDATED` — this project's existing objective sources
  (EQUAL_HIGHS/LOWS, SWING_HIGH/LOW, PDH/PDL, session H/L) already are the proxies the
  spec asks for; this is a relabeling view, not new detection.

### Discovered defect, not fixed (out of scope — frozen code)

`smartmoneyconcepts` 0.0.27's `swing_highs_lows()` unconditionally force-assigns a
synthetic swing label to **array position 0 and the last position**, regardless of
whether either was actually confirmed (verified from source, `smc.py` lines 197-205) —
a bookend artifact for indicator display. This project's new `full_swings()`
(`market_structure/smc_adapter.py`) excludes both positions to avoid a real hindsight
leak (caught by the walk-forward test below). The existing frozen
`_latest_swing()`/`analyze_structure()` may share this exposure for the *last* row
specifically (its "latest swing" could sometimes be this artifact rather than a real
confirmed swing) — flagged here, **not changed**, since that function is frozen Phase 2
and out of this pass's authority.

## 4. Structure Validation

| Check | Result |
|---|---|
| Swing detection (full sequence, not just latest) | VERIFIED — `market_structure.smc_adapter.full_swings()` |
| HH/HL/LH/LL | VERIFIED — `tiers.label_swings()`, incl. tie rule |
| External structure | VERIFIED — `swing_length` 50 tier, independent computation |
| Internal structure | VERIFIED — `swing_length` 5 tier, byte-identical to existing frozen config |
| BOS | VERIFIED — reuses existing frozen `all_breaks()` |
| CHOCH | VERIFIED — reuses existing frozen `all_breaks()`; MSS N/A (never defined) |
| Multi-timeframe | VERIFIED — `analyze_structure_tiers(symbol, timeframe)` is per-call, no hardcoding |
| Drawing | VERIFIED — `chart_renderer` structure layer, artist-count-checked |
| No hindsight | VERIFIED — walk-forward test caught and fixed the bookend-artifact leak |
| Repeatability | VERIFIED — identical input → identical `StructureTier` (frozen dataclass equality) |

`STRUCTURE_V1 = VERIFIED` (not blocked; both freeze decisions confirmed with owner
before implementation).

## 5. Supply & Demand Validation

No detector changes were needed — `AG_ORDER_BLOCK_V1` (frozen Phase 3) already meets
Sections 19-21's requirements (exact boundaries, displacement/BOS evidence, fresh/
mitigated/invalidated lifecycle, PIVOT/SHADOW split). Added: renderer support
(`chart_renderer`'s zone layer) and walk-forward/repeatability tests.

| Check | Result |
|---|---|
| Supply/Demand/OB detection, boundaries, lifecycle | VERIFIED (pre-existing, frozen) |
| Drawing | VERIFIED — zone rectangles from `ZoneResult`, artist-count-checked |
| Walk-forward (zones don't retroactively change; status only advances) | VERIFIED |
| Repeatability | VERIFIED — identical input → identical `ZoneQueryResult` |

`SUPPLY_DEMAND_SKILL = VERIFIED`.

## 6. Liquidity Validation

### Canonical definitions — see Section 3.

### External / Internal Liquidity

`liquidity.hierarchy.external_swing_liquidity()` (new) + existing
`liquidity_result()` levels, tagged by `scope_liquidity_levels()`. VERIFIED live against
EURUSD H1 (see Section 9) — external and internal levels reported and drawn separately,
never flattened.

### BSL / SSL, EQH / EQL, Swing Liquidity, Previous-Day / Session Liquidity, Sweep Lifecycle, Reclaim

All pre-existing and frozen (`liquidity/status.py`, `liquidity/equal_levels.py`,
`liquidity/analyzer.py`) — VERIFIED (Phase 4's own test suite, still passing, plus new
walk-forward coverage below). `SWEPT` vs. `RECLAIMED`/`CONSUMED` kept as distinct facts,
as required; `RECLAIMED`/`CONSUMED` are **not** monotonic (a level's *current*
relationship can flip between them on later candles per the model's own docstring) —
this is intentional, not a bug; what's immutable is the level's geometry and its first
`sweep_time`, both verified in the walk-forward test.

### Inducement Definition, Inducement → Target Mapping, Negative Cases

Rules 1-6 (target exists/unswept, internal level exists/unswept, correct ordering,
nearer than target, same side, structure-derived not invented) all implemented in
`find_inducement_candidates()`/`classify_roles()`. 15 tests, including the mission's own
Case A (bullish + bearish valid inducement), Case B (internal liquidity, no target →
`NONE`), Case C (swept candidate → inactive), and negative cases (swept target, beyond
target, behind price, candidate==target, no external liquidity, cross-side mismatch,
multiple unranked candidates). All pass. `INDUCEMENT = VERIFIED`.

### Multi-Timeframe Liquidity

Each `LiquidityLevel`/scoped level carries its own `symbol`/`timeframe`; external vs.
internal levels from different structure tiers are never merged into one generic level.
VERIFIED by construction and by the live run in Section 9.

`LIQUIDITY_SKILL = VERIFIED`. `EXTERNAL_INTERNAL_LIQUIDITY = VERIFIED`.
`LIQUIDITY_SWEEP = VERIFIED`. `INDUCEMENT = VERIFIED`.

## 7. Multi-Timeframe Validation

Structure tiers, Order Blocks, and Liquidity levels are all computed per explicit
`(symbol, timeframe)` call — none hardcode EURUSD/M15/H1. Live-verified on EURUSD H1
(Section 9); the existing frozen suites already verify H1/M15 for Structure/Supply-Demand/
Liquidity independently (`PROJECT_STATUS.md`'s Phase 2-4 live examples).

## 8. Walk-Forward / No-Hindsight Validation

`tests/test_smc_walkforward.py` (synthetic, deterministic, offline): grows a candle
window and asserts every previously-confirmed annotation (structure swing/event, OB
zone) is byte-identical when recomputed over a longer window — new bars may only ADD
annotations, never change or remove one already confirmed. This is exactly the check
that caught the `smc` library's bookend-swing artifact (Section 3). Liquidity's
`equal_levels`/`status` cores are checked the same way directly (pure functions); full
`liquidity_result()` orchestration is not independently re-proven here (see Section 12).

## 9. Visual Rendering Validation

Live EURUSD H1 combined render (`chart_renderer.render_chart`), 150 most recent bars:

```
structure status: VALID
external dir: BULLISH   swings: 10  events: 5
internal dir: BEARISH   swings: 120 events: 51
OB status: OK  zones: 8
liquidity status: LIQUIDITY_OK  levels: 10
external swing liquidity: EXTERNAL_SWING_HIGH 1.17108 UNSWEPT, EXTERNAL_SWING_LOW 1.15112 UNSWEPT
inducement candidates: 5 (e.g. EQUAL_HIGHS 1.16744 -> EXTERNAL_SWING_HIGH 1.17108)
rendered: candle_count=150 swing_label_count=120 event_marker_count=51 zone_rect_count=8 liquidity_line_count=10
```

External (BULLISH) and internal (BEARISH) structure legitimately disagreeing on the same
live data is expected behavior (Section 14's requirement — do not force agreement), not
an error. PNG inspected: HH/HL/LH/LL labels, BOS/CHOCH markers, supply/demand rectangles,
and liquidity lines with `[TARGET]`/`[INDUCEMENT_CANDIDATE]` role suffixes all render at
their reported coordinates.

## 10. Repeatability

Structure tiers, Order Blocks, and liquidity scoping/inducement classification all
proven via identical-input-twice tests (frozen dataclasses, value equality) — see
`test_structure_repeatability`, `test_order_blocks_repeatability`,
`test_classification_is_deterministic_across_runs`. No stochastic step exists in any
detector.

## 11. Gold Dataset

**Reduced scope, disclosed**: implemented as deterministic inline synthetic candle
generators inside the test files (`_zigzag_candles()` in `test_structure_tiers.py`/
`test_smc_walkforward.py`) rather than a separate frozen `tests/fixtures/smc_gold_v1/`
artifact with 20-30 hand-reviewed cases. This is functionally deterministic and
git-versioned, but **not yet a standalone, explicitly-frozen `SMC_SKILL_GOLD_V1`
artifact** with the full field set (case_id, symbol, timeframe, per-annotation expected
values) Section 38-39 of the mission describes. Flagging honestly rather than claiming a
freeze that didn't happen — building the full 20-30-case gold set is a follow-up item if
wanted (Section 16).

## 12. Failed / Ambiguous Cases

None outstanding — the one real defect found (bookend swing artifact) was fixed in new
code; the same exposure in frozen Phase 2 code is flagged (Section 3) but not fixed
(out of authority this pass).

## 13. Research-Only Concepts

- `ENGINEERED_LIQUIDITY_CANDIDATE` — `RESEARCH_ONLY` (Section 3/6).
- `RETAIL_LIQUIDITY_PROXY` — `VALIDATED`, not research-only (existing sources already
  qualify as objective proxies).

## 14. Test Results

New this session: 39 tests (`test_structure_tiers.py` 5, `test_chart_renderer.py` 7,
`test_liquidity_proxies.py` 5, `test_smc_walkforward.py` 7,
`test_liquidity_hierarchy.py` 15). Full suite: **252 passed, 0 failed** (213 prior +
39 new; prior count includes the separate Phase-6 trade-management work from earlier
this session).

## 15. Final Capability Matrix

| Capability | Numerical | Visual | Multi-TF | Walk-Forward | Repeatable | Status |
|---|---|---|---|---|---|---|
| External Structure | ✓ | ✓ | ✓ | ✓ | ✓ | VERIFIED |
| Internal Structure | ✓ | ✓ | ✓ | ✓ | ✓ | VERIFIED |
| HH/HL/LH/LL | ✓ | ✓ | ✓ | ✓ | ✓ | VERIFIED |
| BOS | ✓ | ✓ | ✓ | ✓ | ✓ | VERIFIED |
| CHOCH/MSS | ✓ | ✓ | ✓ | ✓ | ✓ | VERIFIED (MSS N/A) |
| Supply | ✓ | ✓ | ✓ | ✓ | ✓ | VERIFIED |
| Demand | ✓ | ✓ | ✓ | ✓ | ✓ | VERIFIED |
| Bullish/Bearish OB | ✓ | ✓ | ✓ | ✓ | ✓ | VERIFIED |
| OB lifecycle | ✓ | ✓ | ✓ | ✓ | ✓ | VERIFIED |
| External BSL/SSL | ✓ | ✓ | ✓ | — | ✓ | VERIFIED |
| Internal BSL/SSL | ✓ | ✓ | ✓ | ✓ | ✓ | VERIFIED |
| EQH/EQL | ✓ | ✓ | ✓ | ✓ | ✓ | VERIFIED |
| Swing liquidity | ✓ | ✓ | ✓ | — | ✓ | VERIFIED |
| Previous Day/Session H/L | ✓ | ✓ | ✓ | — | — | VERIFIED (pre-existing) |
| Swept/Unswept, Reclaim | ✓ | ✓ | ✓ | ✓ | ✓ | VERIFIED |
| Inducement Candidate | ✓ | ✓ | ✓ | — | ✓ | VERIFIED |
| Inducement → Target | ✓ | ✓ | ✓ | — | ✓ | VERIFIED |
| Multiple Candidates | ✓ | — | — | — | ✓ | VERIFIED |
| Engineered Liquidity | ✓ | — | — | — | ✓ | RESEARCH_ONLY |
| Retail Liquidity Proxy | ✓ | — | — | — | ✓ | VALIDATED |

("—" = not separately re-tested this pass; covered by existing frozen suites or not
applicable to that axis.)

## 16. Remaining Gaps

- `SMC_SKILL_GOLD_V1` is not yet a standalone frozen 20-30-case fixture (Section 11).
- The `smc` library's bookend-swing artifact in frozen `_latest_swing()`/
  `analyze_structure()` is flagged, not fixed (Section 3) — a Phase 2 owner decision.
- Liquidity's full `liquidity_result()` orchestration (session/PDH integration) wasn't
  independently re-proven via new synthetic walk-forward tests (only its two
  deterministic cores were); it's covered by the existing, still-passing, live-guarded
  `tests/test_liquidity.py`.
- Inducement ranking (when multiple candidates exist) is explicitly `UNDEFINED`/unranked
  per the mission's own instruction not to invent one.

---

```
STRUCTURE_SKILL          = VERIFIED
SUPPLY_DEMAND_SKILL       = VERIFIED
LIQUIDITY_SKILL           = VERIFIED
EXTERNAL_INTERNAL_LIQUIDITY = VERIFIED
LIQUIDITY_SWEEP           = VERIFIED
INDUCEMENT                = VERIFIED
ENGINEERED_LIQUIDITY      = RESEARCH_ONLY
RETAIL_LIQUIDITY_PROXY    = VALIDATED

ENTRY_CONFIRMATION_PHASE  = DEFERRED
TRADE_MANAGEMENT_PHASE    = DEFERRED
```
