# Project Status — AG Profit Trading

AG Profit Trading is a **Trading Assistant + Strategy Execution Platform**. See
`README.md` for the folder map. Git history has the how-we-got-here; this file is
current state only.

## Repository reorganization (2026-08-28)

All 11 Python packages + `session_clock.py` moved from repo root into `src/` (flat --
package names unchanged, so no import statement anywhere needed to change; see
`pyproject.toml`'s `pythonpath`/packaging config). 14 of 17 root-level `.md` docs moved
into `docs/{architecture,specs,status,setup}/`; `README.md`/`AGENTS.md`/
`PROJECT_STATUS.md` stay at root. `cleanup_mbt.ps1`/`setup_mbt.ps1` moved into
`scripts/`. Fixed three real `__file__`-relative config-path bugs this move exposed
(`execution/mt5_gateway.py`, `mt5/management_gateway.py`, `session_clock.py` all
assumed a fixed distance to repo root that changed by one level) plus five hardcoded
test-fixture paths (`tests/test_five_skill_runtime.py`,
`tests/test_entry_confirmation.py`, `tests/test_trade_management_pretrade.py`).
`config/`, `scripts/`, `tests/`, `strategies/`, `journal/`, `.claude/`, `.agents/` are
unchanged in place. First-ever git commits made as part of this pass (repo previously
had zero history). 448 passed / 0 failed, unchanged from pre-move baseline.

## Authority order (permanent project principle)

```
Strategy YAML -> Strategy Engine -> Execution Engine -> MT5
Agent skills / Trading Assistant capabilities -> ADVISORY ONLY
```

Trading Assistant capabilities (market-data, structure, supply/demand, liquidity,
entry-confirmation, trade-management) advise, inspect, explain. They have no
*independent* execution authority and never call `execution.executor`/
`execution.mt5_gateway`/`order_check`/`order_send` directly, and never override a
`strategy_engine.evaluate()` result — if a capability's read disagrees with the engine,
the engine's result stands; the capability may explain the disagreement, not act on it.
Actual broker execution is delegated to the central Trade Assistant execution layer
(`execution/executor.py`, reached only via `assistant/commands.py`) and requires
explicit user authorization every time — see "Execution authority restructure" below.

Exception, added 2026-08-27: `trade_management/` (Phase 6, manual-entry only) is a
third pathway, independent of both the above. It manages a position a human already
opened by hand and explicitly claimed by ticket — it never opens a position itself, and
its writes go only through `mt5.management_gateway` (modify SL / partial close / close),
gated by `config/trading.yaml`'s own `trade_management:` block, separate from
`execution/`'s gates.

## Execution authority restructure (2026-08-28)

```
EXECUTION DEVELOPMENT   = ACTIVE (entry-side OPEN, explicit-command-gated)
ANALYSIS                = AVAILABLE
ORDER_CHECK              = IMPLEMENTED (execution/mt5_gateway.py)
ORDER_SEND               = ENABLED for DEMO accounts, gated by config/trading.yaml AND
                            a required, non-defaulted user_confirmed=True per call
LIVE TRADING             = DISABLED (config/trading.yaml account.allow_live_trading: false)
```

`execution/mt5_gateway.py` and `execution/executor.py` (previously `NotImplementedError`
stubs) now implement OPEN for a new position, modeled directly on
`mt5.management_gateway.py`'s existing dry-run/live pattern. `execution/intent_builder.py`,
`risk.py`, `validator.py` are unchanged (still the strategy-signal path). CLOSE routes
through the existing, unmodified `mt5.management_gateway.close_position()` — no second
MT5 gateway.

Two `ExecutionSource`s (`execution/models.py`):
- `USER_EXPLICIT_ORDER` — a fully user-specified order (e.g. "sell EURUSD 0.31 lots SL
  ... TP ..."). Validated for geometry/sizing/broker constraints only
  (`trade_management.pretrade_engine.evaluate_trade_management()`) — never blocked for
  lacking a strategy signal or entry-confirmation.
- `ASSISTANT_PROPOSAL` — a `TradeProposal` the assistant generated from its own
  analysis, executed only on a later, separate explicit user command; refreshed and
  re-validated against live price at execution time, rejected as `PROPOSAL_STALE` if
  price/age has drifted past a documented tolerance rather than silently reused.

Both paths require `execution.executor.execute(command, user_confirmed=True)` — a
Python-level invariant, not a config flag: no code path reaches `order_send` without the
caller having just received an explicit user instruction that turn. Duplicate protection
via `execution/journal.py` (append-only `journal/execution_<command_id>.jsonl`, mirroring
`trade_management/journal.py`'s existing convention) blocks re-sending an already-
`EXECUTED` `command_id`. CLI: `scripts/execute_trade.py open|close ... [--confirm]`
(omit `--confirm` for a dry-run report of the exact broker request).

**AG_DEMO_EXECUTION_V1 (2026-08-28): PASSED.** One real, explicit-user-command DEMO
round trip verified live: order_check -> order_send -> broker-confirmed open (ticket
1879685149) -> live duplicate-command rejection -> close -> broker/deal-history-confirmed
closure -> config restored to safe defaults. Found and fixed one real defect during this
pass: MARKET-order geometry validation was defaulting `entry_price` to `0.0` instead of
resolving a fresh tick when `--entry` was omitted (`execution/executor.py::
_resolve_entry_price`). Full suite: 412 passed, 0 failed, unchanged count (bugfix, not
new functionality).

**AG_ASSISTANT_PROPOSAL_EXECUTION_V1 + AG_RISK_PERCENT_SIZING_LIVE_V1 (2026-08-28):
PASSED.** `TradeProposal` (`assistant/analysis_models.py`) is now execution-linked: an
`ASSISTANT_PROPOSAL` `TradeCommand` resolves side/SL/TP/risk_percent FROM the stored
proposal (never re-typed by the caller), and `assistant.commands.resolve_active_proposal()`
gives deterministic "execute it" resolution (`NO_ACTIVE_PROPOSAL` / `AMBIGUOUS_PROPOSAL`
/ resolved). Risk-percent sizing now actually works end-to-end: `execution/executor.py`
fetches fresh equity + symbol_meta at execution time (previously never populated at all --
every risk_percent order would have failed `ACCOUNT_DATA_MISSING`) and adds a defensive
final-risk-revalidation check before `order_open`. An already-`EXECUTED` proposal now
blocks re-execution by proposal identity, independent of `command_id` — closes a real gap
where a fresh CLI invocation ("execute it again") would have bypassed the command_id-keyed
journal check and sent a genuine second order. Also fixed: the default order comment
(`f"AG_TRADE_ASSISTANT:{source}"`, 38 chars) exceeded MT5's ~31-char comment limit and
would have rejected every unlabeled order — found live via a real `order_check` failure.
Live-verified: real analysis -> proposal -> "Execute it" -> risk-percent-derived volume
(0.5% of $997.06 equity -> raw 0.0997 lots -> floored to 0.09, actual risk 0.4513%) ->
real order_send (ticket 1880212783) -> live duplicate-proposal rejection -> real close ->
deal-history-confirmed -> config restored. Full suite: 427 passed (412 + 15 new), 0 failed.

## ASSISTANT_RUNTIME_V1 (2026-08-27)

`strategy_manager/` + `assistant/runtime.py` now let the Trade Assistant coordinate
`SESSION_TRADE_V1` / `ASIAN_LONDON` end-to-end in three explicit modes (`ANALYZE_ONLY`
live-verified; `SHADOW_DEMO`/`DEMO_EXECUTION` gating unit-tested, not yet exercised
live). `LONDON_NEWYORK` and `LIVE` both hard-blocked, independent of any flag. Full
architecture: `docs/status/ASSISTANT_RUNTIME_V1.md`; live evidence: `docs/status/ASSISTANT_RUNTIME_V1_STATUS.md`.
278 passed / 0 failed (was 252 before this pass).

## SMC foundational skills validation pass (2026-08-27)

A dedicated validation pass added external/internal structure tiers
(`market_structure/tiers.py`, `swing_length` 5/50), HH/HL/LH/LL labeling, a matplotlib
`chart_renderer/` package, external/internal liquidity scoping + Inducement Candidate
detection (`liquidity/hierarchy.py`), and engineered/retail liquidity classification
(`liquidity/proxies.py`) on top of Phases 2-4 below — all additive, nothing here changed
or broke the frozen `analyze_structure()`/`AG_ORDER_BLOCK_V1`/existing `liquidity/`
behavior. Full results, capability matrix, and verdicts: `docs/status/SMC_SKILL_VALIDATION.md`.
252 passed / 0 failed (was 213 before this pass).

## Trading Assistant capability roadmap

```
PHASE 1 — MARKET DATA          COMPLETE / VERIFIED (AG_TIME_NORMALIZATION_V1, 2026-08-27)
PHASE 2 — STRUCTURE            COMPLETE / FROZEN
PHASE 3 — SUPPLY & DEMAND      COMPLETE / FROZEN (AG_ORDER_BLOCK_V1, frozen 2026-08-26, verified 2026-08-27)
ORDER BLOCK CONTRACT           AG_ORDER_BLOCK_V1 FROZEN -- L1/L2 + inside-bar still UNSIGNED
PHASE 4 — LIQUIDITY            COMPLETE / FROZEN (AG_LIQUIDITY_V1, frozen 2026-08-27)
PHASE 5 — ENTRY & CONFIRMATION NOT STARTED
PHASE 6 — TRADE MANAGEMENT     BUILT (manual-entry only, 2026-08-27) -- see below      <- current
```

### PHASE 6 — TRADE MANAGEMENT (manual-entry only): BUILT (2026-08-27)

Owner-requested, out of the bottom-up phase order above: manages *already open,
manually entered* MT5 positions -- it does not depend on Phase 5 and does not resume
the paused entry-side `execution/` package. New top-level `trade_management/` package
(`models.py`, `claims.py`, `state.py`, `risk.py`, `rules.py`, `validator.py`,
`journal.py`, `manager.py`, `position_monitor.py`), plus `mt5.account.positions()`
(implemented; was `NotImplementedError`), `mt5/deals.py` (new), and
`mt5/management_gateway.py` (new -- the only module allowed to call
order_check/order_send for modify/partial-close/close on an existing position).

**Authority addendum (extends, does not replace, the section below):** this subsystem
is a third, independently-gated pathway -- distinct from both the advisory-only skills
and the paused entry-side `execution/`. It never opens a position (structurally: every
gateway function requires an existing ticket) and is gated by
`config/trading.yaml`'s own `trade_management: {mode, allow_live_management}` block,
default `DRY_RUN`/`false`. `.claude/skills/trade_management/*` /
`.agents/skills/trade_management/*` (`position-monitor`, `risk-manager`,
`partial-profit-manager`, `breakeven-manager`, `exit-manager`) are thin advisory
wrappers that delegate to `trade_management.rules`, not reimplementations.

Baseline V1 rules (frozen, not user-configurable without a new owner-signed rule): 75%
partial close at an explicitly-supplied TP1, breakeven only after that partial is
broker-confirmed, 25% runner closed at 5R from the frozen initial risk distance. Never
enlarges risk or volume; fails closed (`MANAGEMENT_BLOCKED`) on any ambiguity,
including a manual SL/volume change made outside this system.

Workflow: `python scripts/manage_trade.py claim <ticket> --tp1 X --final-r 5`, then
`python scripts/manage_positions.py --once` or `--watch`.

Tests: `tests/test_trade_management_*.py`, `tests/test_management_gateway.py` -- 56
passed, all offline (mocked MT5 positions/ticks, no live connection needed except the
gateway's own live-mode integration is monkeypatched too). Full suite: 211 passed, 0
failed (155 prior + 56 new).

**Not done in this pass (deferred, needs an explicit follow-up request):** live DEMO
validation against a real manually-opened position (spec's own "one intentionally small
DEMO trade" controlled-progression requirement) -- `allow_live_management` stays `false`
until that's explicitly run. Netting-vs-hedging broker mechanics
(`mt5.account.Account.is_hedging_account`) is wired but not yet exercised live.

See `docs/status/PHASE_1_4_FREEZE_STATUS.md` for the 2026-08-27 stabilization pass: root-caused and
fixed a generic (not symbol-specific) tie-break defect in `mt5.broker_time`'s weekly-
reopen-gap detection, established `AG_TIME_NORMALIZATION_V1` (`mt5/time_contract.py`),
and validated all four phases as a regression baseline (154 passed / 1 skipped / 0
failed) before Phase 5 begins. `FROZEN` means no silent semantic changes to
`AG_ORDER_BLOCK_V1` / `AG_LIQUIDITY_V1` going forward -- a behavior change requires a new
contract version or explicit owner instruction.

Each phase implemented bottom-up; owner approves before the next one starts.

### PHASE 1 — MARKET DATA: COMPLETE

Implemented in `mt5/`:
- `connection.py` — `connect()`/`is_connected()`, real, live-tested
- `broker_time.py` — UTC-offset detection via weekly-reopen-gap
- `market_data.py` — `get_candles()` (range), `get_latest_candles()` (position-based),
  `get_tick()` (Bid/Ask), `check_freshness()`; canonical `Candle` now carries `volume`
- `account.py` — `account()` (login/server/equity/demo flag)
- `symbol_resolver.py` — `get_symbol_meta()` (tick/contract/volume-step, generic across
  symbol types), `available_symbols()`

Fail-closed reason codes in use: `MT5_NOT_CONNECTED`, `SYMBOL_NOT_FOUND`, `DATA_MISSING`,
`INSUFFICIENT_CANDLES`, `STALE_DATA`, `DUPLICATE_TIMESTAMPS`, `NON_MONOTONIC_TIMESTAMPS`,
`SESSION_INCOMPLETE`, `TIME_NORMALIZATION_ERROR`, `UNSUPPORTED_TIMEFRAME`.

Report tool: `scripts/check_mt5.py --symbol X [--candles N] [--session asian] [--json]`.

Tests: `tests/test_broker_time.py` (7), `tests/test_market_data.py` (7, live-guarded).

**Fixed a real bug found live:** `get_candles()` passed naive datetimes to
`copy_rates_range`; MT5 silently reinterpreted them via this host's own system timezone
(UTC+6:30), shifting every session query by 6.5h. Fixed by passing epoch integers
instead — see `market_data.py`'s `_to_broker_epoch()`.

**Live examples (2026-08-26, VantageMarkets-Demo):**
- EURUSD: tick 1.16499/1.16512, 24/24 Asian bars, session high/low correct, freshness OK
- XAUUSD: tick 4592.92/4593.21, 24/24 Asian bars, freshness correctly flagged `STALE_DATA`

**Known gap:** `symbol_resolver.resolve()` (broker-suffix resolution, e.g.
`XAUUSD.crp`) still `NotImplementedError` — not hit yet since the connected account's
symbols are unsuffixed; revisit if a broker/symbol needs it.

### PHASE 2 — MARKET STRUCTURE: COMPLETE

`market_structure/` (new top-level package): `analyzer.py` (`analyze_structure()`,
public entry point), `smc_adapter.py` (the ONLY module allowed to import
`smartmoneyconcepts`; verified against installed v0.0.27's actual API, not an assumed
one), `models.py` (`StructureResult`, `StructurePoint`), `config.py` (reads
`config/market_structure.yaml`: `swing_length: 5`, `close_break: true`).

Capabilities: swing highs/lows, BOS, CHoCH, previous high/low, and a deterministic
`state` (`BULLISH`/`BEARISH`/`STRUCTURE_STATE_UNDEFINED` — no invented `RANGE`; see
`analyzer._structure_state()`'s docstring for why). Explicit per-call timeframe
(M1/M5/M15/M30/H1/H4/D1 — `mt5/market_data.py`'s `_TIMEFRAMES` extended beyond M1/M5/M15
for this). Closed candles only (`get_latest_candles` excludes the forming bar).
Warm-up (`max(swing_length*20, 100)` extra candles) fetched but not exposed as separate
"requested vs. total" ranges — reported provenance is the full fetched range.

**Dependency verification (required before coding against it):** `smartmoneyconcepts`
0.0.27's `swing_highs_lows`/`bos_choch` ignore the input DataFrame's own index and
return a fresh positional `RangeIndex`; `previous_high_low` instead calls
`pd.to_datetime(ohlc.index)` internally, so a positional `RangeIndex` there would be
silently reinterpreted as epoch-nanosecond garbage. Resolved by standardizing on one
canonical DataFrame (real UTC `DatetimeIndex`) for all three calls — verified live that
all three tolerate it correctly. Documented in `smc_adapter.py`'s module docstring.

Report tool: `scripts/analyze_structure.py --symbol X --timeframe Y [--count N] [--json]`.

Tests: `tests/test_market_structure.py` — 3 synthetic fixtures (ascending zigzag ->
BULLISH, descending -> BEARISH, range oscillation -> swings present but
`STRUCTURE_STATE_UNDEFINED`, no invented break), 1 adapter-shape test, 2 live EURUSD
(H1, M15) — all real data, both returned `BEARISH` with a live-confirmed BOS.

Added `requirements.txt` (didn't exist before) pinning the verified versions.

### Market Data Assistant layer: COMPLETE

`assistant/market_data.py` — the five user-facing capabilities on top of `mt5/` and
`market_structure/`, each returning a compact dataclass (never raw candle dumps to an
LLM): `market_snapshot()`, `historical_candles()` (UTC range or count), `session_snapshot()`
(open/high/low/close/range/midpoint/completeness), `data_health()` (per-check reason
codes, including new gap detection — `UNEXPECTED_DATA_GAP` vs. weekend closures, which
are not flagged), `multi_timeframe_snapshot()` (reuses `StructureResult` per timeframe).

Tests: `tests/test_assistant_market_data.py` — 10 passed (4 pure gap-logic, 6 live).

### PHASE 3 — SUPPLY & DEMAND: COMPLETE

New top-level package `supply_demand/`: `smc_adapter.py` (ONLY module here allowed to
import `smartmoneyconcepts`; reuses `market_structure.smc_adapter.candles_to_dataframe`),
`native_zones.py` (no smc import), `analyzer.py` (fail-closed batch entry points),
`models.py` (`ZoneResult`, `ZoneQueryResult`).

- **Order Blocks / FVG** (`order_blocks_for()`, `fair_value_gaps_for()`): bullish →
  `ZoneRole.DEMAND`, bearish → `ZoneRole.SUPPLY`. `MitigatedIndex == 0` verified from
  `smc` 0.0.27's own source to be an unambiguous "not mitigated" sentinel (never a real
  position) → `FRESH`; nonzero → `MITIGATED`. A fully invalidated OB is *deleted* from
  the library's internal state and never appears as an output row at all — this adapter
  therefore never reports `INVALIDATED` for these two families (not guessed). `Percentage`
  (OB) exposed only as `raw_strength_metric`, documented as a volume-symmetry ratio, not
  a probability/confidence.
- **Native session zones** (`session_zone()`): wraps `assistant.market_data.session_snapshot()`
  — no new session math. `status` is always `UNKNOWN` here (reason code
  `STATUS_LIFECYCLE_NOT_MODELED_IN_SUPPLY_DEMAND_PHASE`) — sweep/reclaim is a Liquidity-
  phase question.
- **Previous Day High/Low** (`previous_day_high_low()`): project-owned, no smc — the
  last CLOSED D1 bar via `mt5.market_data.get_latest_candles(symbol, "D1", 1)`.
  `TOUCHED` only reflects the *current* tick vs. the level, not the whole day's path
  (reason code names this limitation explicitly).
- **Premium/Equilibrium/Discount** (`dealing_range_zones()`): pure function, takes an
  **explicit** low/high + a caller-named `source` string — never picks a range itself.
  `premium_discount_from_previous_day()` / `premium_discount_from_session()` are the
  only two named convenience sources wired up so far.

Tests: `tests/test_supply_demand.py` — 8 passed (2 real-`smc.fvg()` fixtures for
bullish-fresh/bearish-mitigated, 1 mocked-`smc.ob()` fixture for OB mapping — `smc.ob()`'s
own trigger conditions are too stateful to hand-construct reliably, so its *output* is
mocked to test our mapping, which is the boundary we own; 1 pure premium/discount test;
4 live).

**Live examples (EURUSD, 2026-08-26):** H1 — 9 order blocks (mix of FRESH/MITIGATED),
36 FVGs; M15 — 3 order blocks, 28 FVGs; previous-day H/L 1.16506/1.16790 (`FRESH`);
premium/discount from both previous-day and Asian-session ranges classified current
price as `DISCOUNT`.

### PHASE 4 — LIQUIDITY: BUILT, PAUSED (2026-08-26)

Built and tested (below), then paused by owner request — no further liquidity work
until Order Blocks are resolved. Nothing here changed or broken; simply not being
extended further right now.

New top-level package `liquidity/`: `status.py` (pure sweep/reclaim state machine, no
MT5/smc import — see its module docstring for exact UNSWEPT/SWEPT/RECLAIMED/CONSUMED
semantics, deliberately independent of `strategy_engine.session.setups.entry_2_sweep`'s
strategy-specific strict-penetration contract), `equal_levels.py` (own local-extreme +
tolerance-clustering method, independent of `market_structure`'s smc-swing detection),
`analyzer.py` (`liquidity_result()`, reuses `market_structure.analyze_structure()`,
`supply_demand.session_zone()`, `supply_demand.previous_day_high_low()` rather than
recalculating any of them), `models.py` (`LiquidityLevel`, `LiquidityResult`).

Sources: structural swings (from `StructureResult`), session highs/lows (Asian/London/
New York), PDH/PDL, equal highs/lows (`config/liquidity.yaml`:
`equal_level_tolerance_points: 5`, symbol-tick-size-based, explicit default — no prior
project authority defined one). `SWEPT` is reported only for a live-tick penetration not
yet confirmed by a closed candle; closed-candle history always resolves to `RECLAIMED`
or `CONSUMED`.

Tests: `tests/test_liquidity.py` — 12 passed (7 pure state-machine, 3 pure equal-level
clustering, 2 live).

**Live examples (EURUSD, 2026-08-26):** H1 — 13 levels across all 4 sources; swing high
UNSWEPT, Asian High RECLAIMED, Asian Low CONSUMED, PDH UNSWEPT, PDL CONSUMED, one
EQUAL_HIGHS cluster. M15 — swing high caught mid-sweep as `SWEPT` (live tick trading
through it, not yet closed-candle-confirmed) — a real, not simulated, demonstration of
that status.

### ORDER BLOCK CONTRACT: AG_ORDER_BLOCK_V1 FROZEN AND IMPLEMENTED (2026-08-27)

The owner froze the baseline contract `AG_ORDER_BLOCK_V1` (superseding the prior
"everything stays CANDIDATE forever" placeholder from 2026-08-26). `supply_demand/ob_contract.py`
now implements it fully:

- **PIVOT_OB** (zone = full candle high/low) vs. **SHADOW_OB** (zone = wick tip to body
  edge): split by the origin candle's body-to-range ratio (≥0.5 → PIVOT, <0.5 → SHADOW)
  — an explicit, documented interpretation of the owner's wording, not a frozen number;
  flagged in `ob_contract.py`'s module docstring for confirmation.
- **FLIP_OB** (zone = full candle) is frozen but **never assigned** — its identification
  rule needs a lookback/proximity definition the contract doesn't give (unlike FVG's
  explicit `MAX_CANDLES_TO_FVG=3`). Every candidate resolves to PIVOT_OB or SHADOW_OB.
- **STRUCTURE**: requires a matching-direction BOS or CHoCH confirmed at/after the OB's
  origin — reuses `market_structure`'s real `bos_choch` output via a new
  `market_structure.structural_breaks_for_candles()` (exposes ALL confirmed breaks, not
  just the latest, so a batch of historical OB candidates can each find their own).
  `source=INTERNAL_OR_EXTERNAL` preserved as a placeholder field (`structure_source`) —
  `market_structure/` has one swing-length classifier, no internal/external tiering yet.
- **FVG**: requires a same-direction FVG within `MAX_CANDLES_TO_FVG=3` candles of the OB
  (positional distance, computed from the same fetched candle set as the OB — added
  `validated_order_blocks_for()` fetches OB+FVG candidates together for this reason). No
  literal price overlap required, per the frozen contract.
- **MITIGATION** (`WICK_TOUCH_BOUNDARY`) and **INVALIDATION** (close beyond the zone,
  bullish=below-low / bearish=above-high) scanned forward candle-by-candle; a wick that
  pierces the whole zone but closes back on the original side is `MITIGATED`, not
  `INVALIDATED` — verified live and by a dedicated test.

Lifecycle now real: `CANDIDATE` / `VALID` / `MITIGATED` / `INVALIDATED` / `REJECTED`, all
reachable. Reason codes: `VALID_OB`, `REQUIRED_STRUCTURE_MISSING`, `REQUIRED_FVG_MISSING`,
`FVG_DIRECTION_MISMATCH`, `FVG_TOO_LATE`, `INVALID_OB_GEOMETRY`, `OB_MITIGATED`,
`OB_INVALIDATED`.

**Still explicitly UNSIGNED** (owner instruction — not inferred from the reference
image): `supply_demand.L1_L2_CLASSIFICATION`, `supply_demand.INSIDE_BAR_FLIP_RULE`. See
`supply_demand.ORDER_BLOCK_CONTRACT_GAPS` for the remaining open items (FLIP_OB
identification, the PIVOT/SHADOW split interpretation, structure internal/external
tiering).

Existing generic OB/FVG functionality (`order_blocks_for()`, `fair_value_gaps_for()`) is
unchanged — `validated_order_blocks_for()` is additive.

Tests: `tests/test_ob_contract.py` — 13 passed (valid bullish/bearish PIVOT+FVG, missing
FVG, opposite-direction FVG, FVG too late, missing structure, SHADOW_OB wick-zone
geometry, mitigation by touch, bullish/bearish invalidation, wick-without-invalidation,
contract-gap coverage, 1 live). Full suite: 122 passed.

**Live examples (EURUSD, 2026-08-27):** H1 — 9 candidates, real mix of `VALID`
(2×SHADOW_OB bullish), `MITIGATED` (4), `INVALIDATED` (3, all SHADOW_OB); M15 — 3
candidates, all `MITIGATED` (2×PIVOT_OB, 1×SHADOW_OB). No `FLIP_OB` ever assigned, as
designed.

`supply-demand-analysis` skill updated for `SMC_CANDIDATE_OB` vs. `AG_VALID_ORDER_BLOCK`
terminology and the full lifecycle — see that skill's revised section.

## Strategy-config gaps (found building Phase B, still open)

See `strategies/STRATEGY_LEDGER.md`: `ST_ASIAN_SWEEP_5R_V1`'s `entry_order_type:
MARKET_OR_LIMIT` is ambiguous (blocks `READY_FOR_ORDER_CHECK`) and
`risk_and_money_management` never states an actual risk-per-trade percentage (a
`config/trading.yaml` account-wide default is used instead). Strategy-authorship
decisions, not something to invent while building the Assistant.

## Next owner decision

AG_ORDER_BLOCK_V1 and AG_LIQUIDITY_V1 are both implemented, validated, and now FROZEN
(see `docs/status/PHASE_1_4_FREEZE_STATUS.md`, 2026-08-27). Remaining open items (not blocking, but
unresolved): confirm/replace the PIVOT/SHADOW body-ratio split interpretation; decide
FLIP_OB's identification rule (lookback + proximity to a prior failed zone); L1/L2 and
inside-bar D2S/S2D remain explicitly UNSIGNED, not to be inferred; liquidity's
SWING_HIGH/SWING_LOW scope (latest-only) and its reuse of `equal_level_tolerance_points`
as the cross-source dedup tolerance are documented, non-blocking V1 gaps. Phase 5 — Entry
& Confirmation is the current phase, not yet started.
