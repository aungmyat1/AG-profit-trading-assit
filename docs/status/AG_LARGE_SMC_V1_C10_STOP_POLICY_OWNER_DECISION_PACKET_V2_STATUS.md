# ST_LARGE_SMC_V1 — C10 Broker Stop-Loss Distance: Owner Decision Packet V2 (2026-09-07)

Status: **UNSIGNED — OWNER DECISION REQUIRED**. This is a decision packet, not a
decision. It supersedes nothing in `docs/status/ST_LARGE_SMC_V1_C10_STOP_LOSS_
DECISION_PACKET.md` (2026-09-02, preserved unchanged) — it narrows that packet's three
already-identified open parameters into an explicit, minimal decision matrix, using the
project's own actual, already-signed execution-price conventions where they exist.
`src/large_smc_research/engine.py` continues to return `BLOCKED`
(`reason_code=UNSIGNED_CONTRACT:C10_BROKER_STOP`) for every candidate; nothing here
changes that. `strategies/ST_LARGE_SMC_V1.yaml` is not touched by this packet.

## Baseline

```text
strategy_id      = ST_LARGE_SMC_V1
semantic_version = 1.0.6
current_stage    = OFFLINE_RESEARCH
target_stage     = FORWARD_RESEARCH
sole_promotion_blocker = C10_STOP_POLICY (AG-EGSVF canonical ledger,
  artifacts/validation_ledger/AG_STRATEGY_PORTFOLIO_LEDGER_V1_7d582abef8d1_20260907T061716.109772+0000.json)
```

## Already-resolved rules (verified against `docs/status/ST_LARGE_SMC_V1_C10_STOP_LOSS_
DECISION_PACKET.md` and `strategies/ST_LARGE_SMC_V1.yaml:546-561`; not reopened here)

```text
structural_anchor       = each M-model's own, already-signed SMCEntryCombinationResult.invalidation_price
                          (EXACT_REUSE -- no new detection)
long_direction           = stop placed below the structural invalidation anchor
short_direction          = stop placed above the structural invalidation anchor
missing_anchor_behavior  = FAIL_CLOSED (never substitute entry price, current price, or
                          another model's sweep extreme)
buffer_unit              = pip (frozen EURUSD-only universe, C01)
buffer_range_narrowed    = 1.0-2.0 pips (owner-supplied SMC workflow reference, 2026-09-03:
                          "beyond the extreme structural pivot ... with an additional
                          1-2 pip/tick buffer" -- REQUIREMENTS_REFERENCE_PARTIAL, not a
                          single signed value)
```

## Genuinely unresolved parameters (verified: none of these are settled anywhere in
`strategies/ST_LARGE_SMC_V1.yaml`, `STRATEGY_LEDGER.md`, or any `docs/status/` C10
document)

1. Exact structural buffer value (a single number, or a rule, from within/around the
   1.0-2.0 pip reference range).
2. Spread/bid-ask treatment for the buffer.
3. Broker minimum-stop-distance behavior (WIDEN vs REJECT).

No additional parameter is introduced here beyond these three plus the buffer's *form*
(static vs. volatility-scaled), which is a genuine sub-question of parameter 1 raised by
this task's own instructions.

---

## DECISION 1 — Structural buffer

| | Option A: `STATIC_BUFFER` | Option B: `VOLATILITY_SCALED` |
|---|---|---|
| Formula | fixed N pips beyond the anchor (e.g. 1.5 pips) | `k × ATR(14, M5)` beyond the anchor (e.g. `k=0.35`) |
| Benefit | matches the owner's own reference almost exactly; trivial to audit per-candidate | adapts buffer to instantaneous volatility regime |
| Risk | may be too tight in high-volatility windows, too loose in quiet ones | introduces a second unsigned parameter (`k`) and a volatility-estimator dependency C10 doesn't currently have |
| Determinism impact | none — pure constant, already proven deterministic by every other C10-adjacent computation | ATR itself is deterministic given fixed inputs, but adds a new signed dependency (window length, price series) to freeze |
| Backtest comparability | directly comparable across the 13 existing FX outcome-resolution records (once cost-inclusion is separately signed) and any future Large-SMC replay | not comparable without also freezing the ATR window/config, which does not exist as a signed C10 input today |
| Broker dependence | none beyond pip size (already frozen, EURUSD-only) | none additional |
| Implementation complexity | trivial (one constant) | requires wiring an ATR calculation into the C10 stop-computation path — new code, not just a new constant |
| Effect on invalidation semantics | none — buffer is applied outside/after the already-signed `invalidation_price` anchor, never redefines it | same, but the buffer's *magnitude* becomes runtime-dependent, which changes reproducibility of any single historical candidate's exact stop price across re-runs at different times unless the ATR snapshot is itself pinned to the same evaluation_timestamp already used for the anchor (a real, addressable no-lookahead question, not yet specified) |

**Recommended: `STATIC_BUFFER`, 1.5 pips** (midpoint of the owner's own 1.0-2.0 pip
reference range). Reasoning: simple, deterministic, audit-friendly, gives every
historical candidate an unambiguous, reproducible stop price, and does not inject a
second unsigned parameter (ATR window/multiplier) into an already-open decision.
`VOLATILITY_SCALED` is not rejected — it is deferred as a possible future refinement
once `STATIC_BUFFER` evidence exists to compare against.

`owner_decision = PENDING`

---

## DECISION 2 — Spread / bid-ask treatment

Reconciled against the project's own **already-signed** execution price convention
(`src/execution/executor.py:478`, `:119`, `src/execution/mt5_gateway.py:145`): a BUY
fills at `tick.ask`, a SELL fills at `tick.bid` — confirmed, unchanged, not reopened
here.

```text
current_price_model    = tick.bid / tick.ask (MT5 standard two-sided quote); the
                          structural anchor invalidation_price itself is CANDLE-DERIVED
                          (a wick/close level from the M-model's own structural
                          reference), not a live bid/ask snapshot.
long_stop_trigger_side  = a LONG position's protective stop is a SELL order --
                          standard MT5/broker mechanics trigger it off the BID price
                          falling to the stop level (mirrors the already-signed SELL=bid
                          fill convention above; not a new choice).
short_stop_trigger_side = a SHORT position's protective stop is a BUY order --
                          triggers off the ASK price rising to the stop level (mirrors
                          the already-signed BUY=ask fill convention).
```

The bid/ask *trigger side* is therefore **not** an open question — it falls out of the
already-signed entry-fill convention plus standard broker stop-order mechanics, and is
recorded here as **RESOLVED**, not decision 2's actual open content.

**What remains genuinely open** is narrower than "which side": *whether the pip buffer
from Decision 1 must itself separately account for the bid/ask spread, or whether it is
applied directly to `invalidation_price` as a candle-derived (already spread-neutral)
level.* Two candidate formulas, adapted from the project's own existing, structurally
identical (but explicitly non-authoritative for position sizing) advisory convention in
`src/entry_confirmation/spread.py` (`evaluate_spread_context`: for LONG,
`invalidation = anchor - spread`; for SHORT, `invalidation = anchor + spread` — i.e.
spread pushes the stop *further* from price, in the adverse direction, for both sides):

```text
Formula A (buffer only, no separate spread term):
  LONG stop  = invalidation_price - buffer_pips
  SHORT stop = invalidation_price + buffer_pips

Formula B (buffer + explicit spread, entry_confirmation/spread.py's own convention):
  LONG stop  = invalidation_price - buffer_pips - spread
  SHORT stop = invalidation_price + buffer_pips + spread
```

`double_count_risk`: if the 1.0-2.0 pip reference the owner supplied was already
intended to cover typical EURUSD spread (frequently ~0.1-0.5 pips on major ECN/STP
feeds), Formula B would double-count spread inside an already-spread-inclusive buffer.
The owner's own reference text ("an additional 1–2 pip/tick buffer") does not state
whether spread is already folded in.

`recommended`: cannot be recommended without the owner clarifying whether the 1.0-2.0
pip reference already includes spread. Marking this parameter `SPREAD_TREATMENT =
OWNER_DECISION_REQUIRED` per this task's own instruction rather than guessing.

`owner_decision = PENDING`

---

## DECISION 3 — Broker minimum-stop-distance behavior

| | Option A: `REJECT` | Option B: `WIDEN` |
|---|---|---|
| Behavior | candidate fails closed (no order geometry produced) if the computed stop violates the broker's minimum stop distance | the stop is pushed out to the broker's minimum distance and the candidate proceeds |
| Effect on R:R | none — geometry is either produced as computed, or not produced at all | changes realized risk distance (and therefore R-multiple/target-reachability) versus what the strategy's own structural anchor + buffer computed |
| Semantic classification | broker-capability normalization only | **a strategy-economics change**, not broker normalization -- it silently alters the stop the strategy itself determined |

**Recommended: `REJECT`.** Fail-closed, preserves the strategy's own computed geometry
and intended R:R exactly, and does not require a second, separate sign-off on how much
widening is acceptable. `WIDEN` is explicitly classified here as a strategy-semantic
change per this task's own instruction (section 11) and is not implemented anywhere in
this packet or in `large_smc_research`.

`owner_decision = PENDING`

---

## Implementation

```text
authorized            = NO
strategy_yaml_changed = NO
engine_changed         = NO (src/large_smc_research/engine.py continues to return
                          BLOCKED / UNSIGNED_CONTRACT:C10_BROKER_STOP for every candidate)
```

## Classification

`AG_LARGE_SMC_V1_C10_OWNER_DECISION_PACKET_READY`

C10 remains `UNSIGNED`. `ST_LARGE_SMC_V1` remains blocked at `OFFLINE_RESEARCH ->
FORWARD_RESEARCH` on `C10_STOP_POLICY` until the owner records a decision for all three
items above (Decision 1's buffer value, Decision 2's spread-inclusion clarification,
Decision 3's REJECT/WIDEN choice — Decision 3 has a strong recommendation but still
requires explicit sign-off, since it is a fail-closed vs. semantic-altering choice).
