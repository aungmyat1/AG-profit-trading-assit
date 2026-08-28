# TRADE_MANAGEMENT_V1 Spec — 2026-08-28

Package: `trade_management/` (new modules: `geometry.py`, `sizing.py`,
`position_state.py`, `pretrade_engine.py`; extended: `models.py`, `__init__.py`).
Public entry point: `evaluate_trade_management()`. Agent skill:
`.claude/skills/trade-management-analysis/` (mirrored in `.agents/skills/`). Registry:
`.claude/skills/SKILL_REGISTRY.yaml`.

## Objective

Answer, deterministically: *given a proposed direction, entry, SL, optional TP,
account risk policy, and broker symbol specifications, what is the valid risk,
position size, broker-normalized volume, R geometry, and management state?*

## Non-objectives

- Not a strategy: never changes a supplied entry/SL/TP because "another setup is
  better," never invents SL/TP/risk defaults.
- Not an entry engine: does not decide whether to take a trade.
- Not an MT5 execution gateway: never calls `order_send`, `order_check`, or any
  position-modify path (`execution/` and `mt5.management_gateway` own that).
- Not a portfolio/AI discretionary manager: no trailing optimization, no
  cross-position portfolio risk, no ML-adjusted sizing.

## Architecture boundary

```
Strategy / Manual Candidate
        |
        v
Proposed Trade -> TradeManagementRequest
        |
        v
Trade Management (trade_management.evaluate_trade_management)
        |
        v
TradeManagementResult
        |
        v
TradeIntent, if the caller chooses (execution/intent_builder.py, unchanged)
        |
        v
Execution -> MT5 (unchanged, project-wide paused)
```

`READY` in the result means *Trade Management's calculations are valid* -- it is never
a synonym for "execute this trade." Execution authority stays entirely in `execution/`
and `mt5.management_gateway`, unchanged and independently gated by this pass.

## Audit performed before coding

Searched `trade_management/`, `execution/`, `mt5/symbol_resolver.py`, `config/*.yaml`,
and every relevant skill for existing risk/sizing/geometry/normalization code.

| Capability | Current implementation | Owner | Status | Reusable? | Target owner | Action |
|---|---|---|---|---|---|---|
| Trade geometry validation (LONG/SHORT SL/TP sign checks) | `execution/validator.py::validate_geometry()` | `execution` (strategy-signal-typed) | SIGNED, EXECUTION_SPECIFIC (works on `strategy_engine.TradeSignal`, not a plain request) | ADAPT (same rule, generic input type) | `trade_management.geometry` | Reimplemented generically; same sign-check rule |
| Account/config/symbol-metadata sanity | `execution/validator.py::validate_account_and_config()` | `execution` | SIGNED, EXECUTION_SPECIFIC | ADAPT (same reason-code vocabulary reused verbatim: `ACCOUNT_DATA_MISSING`, `INVALID_RISK_CONFIG`, `SYMBOL_METADATA_MISSING`) | `trade_management.sizing` | Reimplemented, same codes |
| Position sizing (risk budget / tick-based loss-per-lot / floor-to-step) | `execution/risk.py::size_position()` | `execution` (informally called "RiskSupervisor" in `docs/status/ASSISTANT_RUNTIME_V1.md` prose -- **no such class exists**, verified by `grep -rn "class RiskSupervisor"` returning nothing) | SIGNED, EXECUTION_SPECIFIC | ADAPT (same formula; not imported -- see `sizing.py`'s docstring for why trade_management does not depend on execution/) | `trade_management.sizing` | Reimplemented; same formula, same floor-only rounding |
| R-multiple from a frozen initial risk distance | `trade_management/risk.py::current_r()` | `trade_management` (Phase 6) | SIGNED, IMPLEMENTED, generic already | YES | `trade_management.position_state` | REUSE_DIRECTLY (imported, not duplicated) |
| Partial-close broker-legal volume normalization | `trade_management/risk.py::normalize_partial_close_volume()` | `trade_management` (Phase 6) | SIGNED, IMPLEMENTED | N/A for V1 (single-target sizing only; this handles an already-open position's partial, a different question) | `trade_management` (Phase 6, unchanged) | Preserved, not touched |
| Open-position advisory state machine (partial/breakeven/exit) | `trade_management/{rules,state,position_monitor,claims}.py` | `trade_management` (Phase 6) | SIGNED (frozen 75%/25% policy), IMPLEMENTED, READY | N/A (answers "what should happen to an already-claimed position," not "how should a proposed trade be sized") | `trade_management` (Phase 6, unchanged) | Preserved, not touched |
| Multi-asset broker metadata (tick_size, tick_value, contract_size, volume_min/max/step, digits, point) | `mt5/symbol_resolver.py::SymbolMeta` | `mt5` | SIGNED, IMPLEMENTED | YES | consumed as-is | REUSE_DIRECTLY (no new symbol-meta type) |
| Generic pip conversion (as opposed to points) | -- (searched, not found: no `pip_size`/pip-conversion function anywhere in code) | -- | MISSING | N/A | -- | NOT IMPLEMENTED -- see "Known limitations" |
| Duplicate/quota protection | `Session Trade Codex`'s own `ExecutionLedger` (per-strategy, cross-repo) | Strategy-specific | STRATEGY_SPECIFIC | NO | -- | Out of scope; not a Trade Management concern in V1 |

## Request contract — `TradeManagementRequest`

```python
TradeManagementRequest(
    symbol: str, direction: str,            # "LONG" / "SHORT"
    entry_price: float, stop_loss: float, take_profit: Optional[float] = None,
    risk_percent: Optional[float] = None,    # 0 < x <= 100
    risk_amount: Optional[float] = None,     # explicit currency amount, takes priority if both given
    equity: Optional[float] = None,
    symbol_meta: Optional[SymbolMeta] = None,        # mt5.symbol_resolver.SymbolMeta, unchanged
    current_price: Optional[float] = None,           # position_state advisory only
    management_policy: Optional[ManagementPolicy] = None,
)
```

No strategy is required: a caller may supply only `symbol`/`direction`/`entry_price`/
`stop_loss`/`take_profit` for a pure geometry/RR check.

## `ManagementPolicy` — caller-owned, never a Trade Management default

```python
ManagementPolicy(
    max_risk_percent: Optional[float] = None,     # signed ceiling; rejected against, never clamped
    breakeven_trigger_r: Optional[float] = None,
    policy_source: Optional[str] = None,           # e.g. "SESSION_TRADE_V1", "MANUAL"
    strategy_id: Optional[str] = None,
    strategy_version: Optional[str] = None,
)
```

A strategy's own risk %, TP structure, partial targets, or BE rule are recorded via
this policy, not converted into a Trade Management default. No field of it is used
unless the caller supplies it.

## Result contract — `TradeManagementResult`

```python
TradeManagementResult(
    symbol, direction, overall_status,                       # READY / BLOCKED
    geometry: TradeGeometry,
    sizing: PositionSizing,
    position_state: PositionStateAdvisory,
    reasons: Tuple[str, ...], contract_version="TRADE_MANAGEMENT_V1",
)
```

`TradeGeometry`: `status`, `stop_distance_price`, `stop_distance_points`,
`reward_distance_price`, `rr_multiple`. `PositionSizing`: `status`,
`requested_risk_percent`/`_amount`, `risk_budget`, `loss_per_lot`, `raw_volume`,
`normalized_volume`, `actual_risk_amount`/`_percent`. `PositionStateAdvisory`:
`status`, `current_r`.

## Trade geometry

LONG requires `stop_loss < entry < take_profit`; SHORT requires the reverse. Zero stop
distance, a non-finite price, or an invalid direction string are separate reason codes
(`ZERO_STOP_DISTANCE`, `INVALID_PRICE`, `INVALID_DIRECTION`). Invalid geometry is never
auto-repaired — the caller gets the specific violated rule
(`INVALID_LONG_STOP`/`INVALID_LONG_TARGET`/`INVALID_SHORT_STOP`/`INVALID_SHORT_TARGET`).
`take_profit` is optional; when absent, geometry is still `VALID` and `rr_multiple`/
`reward_distance_price` are `None`.

## Stop distance and multi-asset conventions

`stop_distance_price = abs(entry - stop_loss)`, always computed. `stop_distance_points
= stop_distance_price / symbol_meta.point` when `symbol_meta` is supplied — this works
identically for FX, JPY pairs, and metals because it only uses the broker's own `point`
field, never a hardcoded per-symbol table (verified against synthetic EURUSD/USDJPY/
XAUUSD `SymbolMeta` fixtures in the tests). **Pip conversion is not implemented**: no
generic pip-size convention exists anywhere in this repo's code (only prose in the
`multi-asset-conventions` skill) and inventing one would be exactly the kind of hidden,
unsigned per-symbol table this capability must not create.

## Risk budget

`requested_risk_amount = risk_amount if risk_amount is not None else equity *
(risk_percent / 100)`. Missing/non-finite/non-positive equity fails closed
(`ACCOUNT_DATA_MISSING`) rather than guessing account size. `risk_percent` outside
`(0, 100]` or a non-positive `risk_amount` is `INVALID_RISK_CONFIG`.

## Risk authority (requested vs. maximum)

If `management_policy.max_risk_percent` is supplied and `risk_percent` exceeds it, the
result is `RISK_LIMIT_EXCEEDED` — an explicit rejection, never a silent clamp down to
the policy ceiling. No global maximum-risk policy is invented when the caller does not
supply one.

## Position sizing (tick-based, broker-realistic)

```
value_per_price_unit = symbol_meta.tick_value / symbol_meta.tick_size
loss_per_lot          = stop_distance_price * value_per_price_unit
raw_volume            = requested_risk_amount / loss_per_lot
```

Uses `tick_size`/`tick_value` from broker-supplied `SymbolMeta`, never a `$10/pip per
standard lot` FX shortcut — verified against a synthetic gold (`XAUUSD`, `contract_size
100`) fixture in the tests, which resolves correctly through the same formula. This is
the same formula as `execution/risk.py::size_position()` (see the audit table above for
why it is reimplemented, not imported).

## Broker volume normalization

`normalized_volume = floor(raw_volume / volume_step) * volume_step` — floor only, never
rounds up (tested explicitly:
`test_normalization_rounds_down_never_up`/`test_normalization_exact_valid_step`). If
the normalized volume is below `volume_min`, the result is `VOLUME_BELOW_MIN` /
`SIZE_UNAVAILABLE` rather than forcing the broker minimum through (which could exceed
the requested risk budget) — fail-closed, per the mission's explicit instruction. If
raw volume exceeds `volume_max`, the result is `VOLUME_ABOVE_MAX` — **rejected, not
capped**, mirroring `execution/risk.py::size_position()`'s own existing behavior; no
signed policy anywhere authorizes silently capping to a cheaper size.

## Actual risk after normalization

`actual_risk_amount = normalized_volume * loss_per_lot`; `actual_risk_percent =
actual_risk_amount / equity * 100`. Both are always reported on a `READY` result so the
caller can see the (small) difference from the requested risk caused by step rounding.
No risk-tolerance threshold is invented for this difference — none exists in any signed
config, so none is enforced.

## R-multiple / RR geometry

`stop_distance = abs(entry - stop_loss)` (1R), `reward_distance = abs(take_profit -
entry)`, `rr_multiple = reward_distance / stop_distance`. Computed from price distances
first; no pip conversion is applied to RR (RR is a dimensionless ratio, unaffected by
unit). Only a single TP is supported in V1 — no existing generic (non-strategy)
multi-target infrastructure was found to preserve, and the mission scoped V1 to a
single TP.

## Position-state advisory

Two independent things already answer "what state is a trade in":

1. **Phase 6** (`trade_management.rules`/`state`/`position_monitor`, unchanged) — the
   authoritative, broker-reconciled state machine for an already-open,
   manually-claimed MT5 ticket, with its own signed 75%/25% partial+breakeven policy.
2. **`position_state.py`** (new) — a lightweight, non-broker-coupled advisory for a
   *proposed or informally-tracked* candidate that has no broker ticket/claim yet.
   Reuses `trade_management.risk.current_r()` directly (not reimplemented). Reports
   `NOT_REQUESTED` (no `current_price` supplied), `INSUFFICIENT_DATA` (invalid
   direction/zero stop distance), `HOLD`, `BREAKEVEN_ELIGIBLE` (only when
   `management_policy.breakeven_trigger_r` is supplied and reached), or
   `TARGET_REACHED` (objective fact, independent of any policy). Never modifies
   anything — advisory only, matching Phase 6's own authority chain.

## Status vocabulary

```
Geometry : VALID / INVALID_DIRECTION / INVALID_PRICE / ZERO_STOP_DISTANCE /
           INVALID_LONG_STOP / INVALID_LONG_TARGET /
           INVALID_SHORT_STOP / INVALID_SHORT_TARGET
Sizing   : READY / NOT_REQUESTED / ACCOUNT_DATA_MISSING / INVALID_RISK_CONFIG /
           SYMBOL_METADATA_MISSING / RISK_LIMIT_EXCEEDED /
           VOLUME_BELOW_MIN / VOLUME_ABOVE_MAX / SIZE_UNAVAILABLE
Advisory : NOT_REQUESTED / INSUFFICIENT_DATA / HOLD / BREAKEVEN_ELIGIBLE / TARGET_REACHED
Overall  : READY / BLOCKED
```

`INDETERMINATE`/`PARTIAL`/`UNSIGNED_POLICY` (listed as possible vocabulary in the
mission brief) are reserved but not produced by V1's fully-deterministic geometry/
sizing pipeline — see "Known limitations."

## Overall status aggregation

```
geometry invalid                                -> BLOCKED
geometry valid, sizing not requested            -> READY
geometry valid, sizing READY                     -> READY
geometry valid, sizing failed (any other reason) -> BLOCKED
```

Sizing is "not requested" only when the caller supplies none of
`equity`/`risk_percent`/`risk_amount`/`symbol_meta` — i.e. a pure geometry/RR check.
Supplying any of them commits to a sizing attempt; a resulting failure blocks the
overall result (sizing was asked for and could not complete).

## Strategy boundary

A strategy (e.g. a future `SESSION_TRADE_V1` candidate) builds the same
`TradeManagementRequest` with its own `entry`/`SL`/`TP` and an `ManagementPolicy`
carrying its `strategy_id`/`max_risk_percent`/`breakeven_trigger_r`, then applies its
own sufficiency rule to the result. `SESSION_TRADE_V1` and `ST_ASIAN_SWEEP_5R_V1`'s
existing signed contracts were not modified by this pass and do not yet declare such a
policy — this spec does not add one on their behalf.

## Execution boundary

Verified by two tests in `tests/test_trade_management_pretrade.py`: an AST import scan
(no `trade_management/*.py` file imports `execution`) and an AST call scan (no file
calls a function literally named `order_send`/`order_check`). `SymbolMeta` (a
read-only data type) remains the only broker-adjacent dependency, unchanged from Phase 6.

## Examples

**Example 1 — manual entry, no strategy required** (see
`test_engine_manual_entry_no_strategy_required_example_1`):

```
EURUSD, equity $10,000, risk 1%, LONG, entry 1.17000, SL 1.16750, TP 1.18000
Stop: 0.0025 price / 250 points   Risk Budget: $100   Loss/Lot: $250
Raw Volume: 0.40   Normalized Volume: 0.40   Actual Risk: $100   RR: 4.00R
Status: READY
```

**Example 2 — fail-closed, no unsafe rounding** (see
`test_engine_fail_closed_example_2_size_unavailable`):

```
Tiny equity forces raw_volume below broker volume_min.
Result: VOLUME_BELOW_MIN / SIZE_UNAVAILABLE, overall_status = BLOCKED.
No 0.01-lot trade is forced through.
```

**Example 3 — position-state advisory** (see
`test_position_state_breakeven_eligible`):

```
LONG, entry 1.1700, SL 1.1675, current 1.1725, policy breakeven_trigger_r=1.0
current_r = 1.0R -> status = BREAKEVEN_ELIGIBLE (advisory only, no modification performed)
```

## Unsigned policies

`max_risk_percent` and `breakeven_trigger_r` are unsigned in the sense that no global
default exists — they are only ever evaluated when a caller explicitly supplies them.
This is intentional per the mission's "risk authority" requirement, not a gap to close.

## Known limitations

1. Generic pip conversion is not implemented (only price distance and points) — no
   signed pip-size convention exists anywhere in this repo's code.
2. Multi-target (TP1/TP2/TP3) sizing is not implemented in V1 — no existing generic
   (non-strategy) infrastructure was found to preserve, and V1 was scoped to a single TP.
3. `OverallState.PARTIAL`/`INDETERMINATE` and `SIZING`'s `UNSIGNED_POLICY` are reserved
   vocabulary, not produced by the current deterministic pipeline — would apply if a
   future primitive introduces its own unsigned gap (mirroring
   `docs/specs/ENTRY_CONFIRMATION_V1_SPEC.md`'s `UNSIGNED_RULE` pattern).
4. `position_state.py`'s advisory is intentionally minimal (current R, breakeven
   eligibility, target-reached) and does not replace or extend Phase 6's broker-
   reconciled state machine.
