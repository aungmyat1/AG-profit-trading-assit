# SESSION_TRADE_V1 — Strategy Spec

Registered here by reference (`strategies/session_trade/contract.yaml`). Authoritative
implementation: `D:\ddev\Session Trade Codex`, `strategy_id: ASIAN_SESSION_V1`,
`config/strategy.yaml` + `session_strategy/engine.py`. Every field below is sourced from that
repo's actual signed config/code, read directly for this spec — not inferred from the
SessionBoxes indicator, chat history, or hypothesized rules. Fields with no signed source are
marked `UNSIGNED`, per instruction, rather than filled with an implementation default.

```
strategy_version:              1.0 (contract_version in source config)
strategy_status:                PARTIAL_DEMO_AUTHORIZED (ASIAN_LONDON signed; LONDON_NEWYORK UNSIGNED)
required_assistant_capabilities: MARKET_DATA, SESSION_BOX, LIQUIDITY (strategy-specific), TRADE_MANAGEMENT
canonical_reference_session:    NOT canonical -- own legacy-frozen window, see below
supported_execution_cycles:     ASIAN_LONDON (ACTIVE), LONDON_NEWYORK (UNSIGNED)
demo_authority:                 ASIAN_LONDON only
live_authority:                 NONE, either cycle, unconditional hard block
```

## Reference session (ASIAN_LONDON cycle)

- Window: `00:00–07:00 UTC`, 28 M15 candles. **SIGNED** (`config/strategy.yaml` `session_start_utc`/
  `session_end_utc`/`session_candles`).
- This is *not* the canonical Asian window (`00:00–06:00`, 24 candles, `CANONICAL_SESSION_WINDOWS_V1`
  in the source repo). Deliberately frozen non-canonical — the trader-confirmed truth-source
  window for the golden fixtures; rewriting it would fabricate unverified "truth." Documented as
  a `LEGACY_SESSION_WINDOW` in that repo's own `config/canonical_sessions.yaml`.
- Execution window: `07:00–16:00 UTC`, up to 36 M15 candles. **SIGNED**.

## Reference session (LONDON_NEWYORK cycle) — UNSIGNED

- Reference window: **UNSIGNED**. No config or governance record defines a London reference box
  for this strategy. The source repo's own canonical config states plainly: "execution window
  07:00-16:00 has no separate London/NY boxes."
- The `07:00–12:00` / `12:00–20:00` figures currently used by `scripts/execute_session_signal.py`'s
  `SESSION_PAIRS["LONDON_NEWYORK"]` are borrowed from the `SessionBoxes_V1` MT5 indicator's
  cosmetic display defaults — not strategy authority (authority precedence: owner-signed
  contract > canonical config > implementation > indicator > display default). They
  coincidentally match two *unrelated*, execution-never-authorized research strategies'
  legacy windows (`SESSION_FLOW_V2_SIMPLE`, `SESSION_STRATEGY_V2_RESEARCH`), which is not
  evidence for this strategy either.
- **Status: execution-blocked independent of every other gate** until the owner signs an actual
  window. Analysis/`--check` (order_check only, no order_send) remains available.

## Trend/Range classifier — audit (Section 12)

**Hypothesis in the request** ("owner recently simplified... mid = (high+low)/2; open/close same
side of mid → RANGE, opposite sides → TREND, with direction from which side each is on") —
**checked against every current authoritative source in the implementing repo and not found
anywhere**: not in `config/strategy.yaml`'s `classification:` block, not in
`session_strategy/engine.py`'s `classify_session()`, not in `STRATEGY_SPEC.md`,
`SESSION_FLOW_V1_SPEC.md`, or `STRATEGY_LEDGER.md`-equivalent history in that repo. **Not
implemented.** Per instruction ("do not blindly implement this text... first locate
current owner-authorized evidence"), this spec does not adopt it.

**Actual signed classifier** (`config/strategy.yaml` `classification:` block,
`session_strategy/engine.py::classify_session()`):

```
RANGE            if efficiency_ratio <= 0.35
BULLISH_TREND    elif close_location >= 0.65 AND close > open
BEARISH_TREND    elif close_location <= 0.35 AND close < open
UNCERTAIN        otherwise (not traded -- trade_uncertain_sessions: false)

efficiency_ratio = |close - open| / range
close_location   = (close - low) / range
```

This is a **different classifier from this repo's `ER_ONLY_V2`**
(`strategy_engine/session/classifier.py`, threshold 0.40, path-length-based, no close-location
term, no directional bias output) used by `ST_ASIAN_SWEEP_5R_V1`. They are not meant to agree —
see `ARCHITECTURE_CONFLICT_AUDIT.md`. Do not merge them; each is a separately signed rule for a
separately signed strategy.

## Sweep logic — audit (Section 13)

- **Box inspected:** the locked Asian reference box (00:00–07:00), never a later/growing window.
- **Sweep must occur inside the completed session:** no — sweep detection runs over
  **execution-window candles** (07:00–16:00, closed candles only), checked against the *already
  locked* reference box's high/low. The box itself never changes after 07:00.
- **Penetration threshold:** `sweep_buffer_fraction: 0.02` × reference range (asymmetric per
  side, `config/strategy.yaml`).
- **Open-location condition:** candle must open on the *inside* of the level being swept
  (`candle.open >= low` for a low-sweep, `candle.open <= high` for a high-sweep).
- **Close/reclaim condition:** candle must close back inside the range (`close > low` /
  `close < high`) — "sweep and reclaim on the same candle," not a separate later reclaim.
- **Wick/body requirement:** rejection quality filter — the close must be inside the candle's
  own body by at least `rejection_quality_fraction: 0.50` of that candle's range (a shallow
  reclaim wick fails).
- **Dual-side behavior:** a single candle sweeping *both* boundaries is rejected outright
  (directionally contradictory) — `detect_sweep()` returns `None`.
- **Direction:** low-sweep → `LONG`; high-sweep → `SHORT`.
- **Setup priority if multiple could apply:** fixed order `SWEEP > RANGE_REJECTION >
  TREND_CONTINUATION`, first match wins, evaluated candle-by-candle in time order across the
  execution window (first qualifying candle in time, not "best" candle).
- **No post-session observation lifecycle:** confirmed — the engine scans the fixed, already-
  fetched execution-candle list once per invocation; there is no persistent watcher, no
  multi-sweep cooldown, no "wait for a future candidate" state machine. Matches the
  instruction not to reintroduce that.

Generic `liquidity.status` (this repo's `UNSWEPT/SWEPT/RECLAIMED/CONSUMED` state machine) is
explicitly **independent** of this strategy's sweep qualification — both packages document this
separation already (`liquidity-analysis` skill: "deliberately independent of
`strategy_engine.session.setups.entry_2_sweep`'s strategy-specific strict-penetration
contract"). No change needed; already correctly separated.

## Setup contract audit (Section 14)

| Field | TREND (`TREND_CONTINUATION`) | SWEEP | RANGE (`RANGE_REJECTION`) | Status |
|---|---|---|---|---|
| Eligibility | session classified TREND (either direction) | session classified RANGE | session classified RANGE, no sweep already claimed this candle-scan | SIGNED |
| Direction | same as trend bias | opposite the swept side | opposite the touched boundary | SIGNED |
| Entry | session midpoint | near edge of sweep candle's real body | the touched session boundary itself | SIGNED |
| SL | 25% of reference range from entry (`stop_range_fraction`), fixed | same 25%-of-range rule; additionally must clear the sweep extreme by `stop_buffer_fraction` or the signal is **rejected** (not widened) | same 25%-of-range rule | SIGNED |
| TP | 5R fixed ceiling (`tp2_5r`); 4R partial (`tp1_4r`, opposite boundary for SWEEP/RANGE, fixed-R for TREND) | same | same | SIGNED |
| Partial close | 75% at 4R/opposite-boundary, runner to 5R | same | same | SIGNED |
| Runner behavior | move stop to breakeven after partial, run to 5R | same | same | SIGNED |
| Breakeven | `ACTUAL_WEIGHTED_ENTRY` basis | same | same | SIGNED |
| Order type | LIMIT at the computed entry price | same | same | IMPLEMENTED (`execute_session_signal.py::build_intent`, `entry_type="LIMIT"`) |
| Expiry | `EXECUTION_WINDOW_EXPIRED` once execution candles exhausted with no setup | same | same | SIGNED |
| Invalidation | trading through the *opposite* quartile cancels a pending TREND setup | structural-stop-not-beyond-sweep rejects at detection, not after | none beyond normal SL | SIGNED (TREND); IMPLEMENTED_BUT_IMPLICIT (RANGE has no separate invalidation rule stated) |
| Timeframe | M15, all three | | | SIGNED |
| Same-bar ambiguity | fixed priority order (SWEEP > RANGE_REJECTION > TREND_CONTINUATION) resolves it | | | SIGNED |
| 4R partial-close automation | **NOT automated** — `execute_session_signal.py` submits only the 5R-ceiling order; 4R partial/breakeven step is manual (`sspf.py monitor`) | | | LEGACY / deliberate scope limit, documented in source repo |

No execution-critical field found `MISSING` or `CONFLICTING` for `ASIAN_LONDON`. Per Section 14's
rule, since every field the cycle needs to place an order is `SIGNED`, `ASIAN_LONDON` itself is
**FROZEN** for execution purposes (consistent with the source repo's own
`DEMO_EXECUTION_INFRASTRUCTURE_VALIDATED_V1` milestone). `LONDON_NEWYORK` fails this test on the
reference/execution window fields alone (see above) — **`SESSION_TRADE_V1` as a whole strategy
is `NOT_FROZEN`** while that cycle stays unsigned, and that cycle fails closed by design.

## Risk / management (both cycles, where each applies)

- Risk basis: lower of balance/equity. Risk per trade: **0.5%** (`risk_percent_per_trade`).
- Daily risk limit: 2.0%. Max drawdown: 15.0% (disables new signals, does not close positions).
- Max trades: **1 per symbol per trading_date per cycle** (per-cycle quota, via a distinct magic
  number per cycle — not a single global "one trade per day" rule; see
  `strategies/session_trade/contract.yaml`).
- Spread/range plausibility bounds are per-symbol (`config.symbols`), shared by both cycles —
  a known simplification since they were tuned against the Asian (7h) box, not re-tuned for a
  5h London box.
