# LSMC_SPEC_V1_FROZEN -- ST_LARGE_SMC_V1 strategy-logic freeze

| Field | Value |
|---|---|
| `spec_id` | `LSMC_SPEC_V1_FROZEN` |
| `spec_version` | **`1.0.1`** |
| `supersedes` | `1.0.0`, SHA-256 `94dd0fb9226bd078d0ee8d49125af58692fe595e0f65bc57181354f60e999a7e` |
| `strategy_id` | `ST_LARGE_SMC_V1` |
| `strategy_versions_covered` | `1.0.7` (`strategies/ST_LARGE_SMC_V1.yaml`) and `1.1.0` (`src/large_smc_watch/contract.py`) |
| `status` | `FROZEN_WITH_OPEN_DECISIONS` |
| `authority` | Specification artifact. Confers no proposal, Demo, Live, execution or risk-sizing authority. |
| `mission` | `AG_ARENA_RESET_A1_R1` step A1 |
| `frozen_utc` | 2026-10-07 |
| `owner_decision_applied` | 2026-10-07 batch, closing `LSMC-OD-02/09/10/12/13/14/16/17`. Verbatim text: `verification/AG_ARENA_RESET_A1_R1/OWNER_DECISIONS_2026-10-07_LSMC_SPEC_V1_01.md` |

**What "FROZEN_WITH_OPEN_DECISIONS" means.** Every rule marked `FROZEN` is closed: it is
traceable to an owner-signed decision or to already-merged code on `main`, and it may not
be changed by editing this file. Any change requires a new signed owner decision and a new
spec version.

Every rule marked `OPEN` is **not** decided. It is written as an explicit question in
section 8.2, now with a **recommended default and rationale** for batch sign-off. **No open
item has been resolved silently.** Recommended defaults are proposals only -- they are
**not applied** and carry no authority until signed.

---

## 0. Scope

### 0.1 In scope -- strategy logic only

1. The C10 stop rule (stop construction).
2. Opportunity expiry.
3. The outcome taxonomy.
4. The same-bar stop+target tie rule.
5. Gap handling.
6. Side-correct prices for level resolution.

### 0.2 Explicitly NOT in scope

`LSMC_ACTIONABILITY_POLICY_V1` (owner decisions D1-D8, 2026-10-07) governs **delivery and
actionability**: freshness, remaining-R at send, downtime recovery, send-time state
semantics, price-normalization timing, correlation tagging and Demo gating. Those rules are
**not restated, summarized, amended or re-derived here**.

The boundary this spec uses:

> This spec governs what the *market* did to an opportunity's own levels.
> `LSMC_ACTIONABILITY_POLICY_V1` governs whether, when and how an opportunity is *told to
> the owner*.

An opportunity's strategy-level outcome is resolved **independently of whether it was ever
delivered**. The two vocabularies are disjoint and must never be merged into one field.

### 0.3 Authority and separations

`IMPLEMENTED != VALIDATED != AUTHORIZED`. This spec changes no code, no strategy YAML, no
threshold and no registry entry. `ST_LARGE_SMC_V1` remains `RESEARCH_DRAFT` /
advisory-only with `proposal_generation_authorized = False`. Nothing here is evidence of
edge.

---

## 1. Source pins

| Pin | Source | Identity |
|---|---|---|
| `P1` | Owner decision packet, C10 | `docs/status/AG_LARGE_SMC_V1_C10_STOP_POLICY_OWNER_DECISION_PACKET_V3_STATUS.md`, `SIGNED_AND_LOCKED` 2026-09-07 |
| `P2` | Strategy contract | `strategies/ST_LARGE_SMC_V1.yaml` v1.0.7, `stop_loss_contract` |
| `P3` | C10 implementation | `src/large_smc_core/c10_stop_policy.py` (`main` @ `fc60cdb`) |
| `P4` | Watch contract constants | `src/large_smc_watch/contract.py` (`ST_LARGE_SMC_V1@1.1.0`) |
| `P5` | Watch detection + expiry | `src/large_smc_watch/detect.py`, `watch.py` (`main` @ `fc60cdb`) |
| `P6` | Session windows | `config/canonical_sessions.yaml`, half-open, fixed UTC |
| `P7` | Provisional outcome resolver | `src/host_delivery/lsmc_outcome.py` @ `acfc25e` (**draft PR #49, unmerged**) |
| `P8` | Provisional side convention | PR #49 body, "Interpretations to confirm" |
| `P9` | Price convention | MT5 native **BID-based** bar OHLC (`docs/status/SSC_V1_0_1_ONE_YEAR_M1_ACQUISITION_STATUS.md`) |
| `P10` | Bar type in use | `src/strategy_engine/session/candles.py` -- `Candle(time, open, high, low, close, volume)`. **No spread field.** |
| `P11` | Spread-constant precedent | `strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml` `friction.default_spread_pips` (EURUSD 1.0, GBPUSD 1.4), "documented research defaults, not broker-verified" |
| `P12` | Owner ruling, this version | 2026-10-07 batch -- see `owner_decision_applied` above |

### 1.1 Governance record used for the scope boundary

`docs/governance/OWNER_DECISIONS_2026-10-07_LSMC_ACTIONABILITY_V1.md`, canonical 94-line
record, SHA-256 `67bb1a57a7bc38335fdb18d7bdf7880c39331247a44abbc473e35cf1eecb7b56`
(commit `f4ec100`). Used **only** to fix what section 0.2 excludes.

---

## 2. The opportunity object (frozen reference)

`FROZEN` -- from `P5`.

| Field | Meaning |
|---|---|
| `opp_id` | `{poi_id}` + sweep bar time + CHoCH bar time |
| `direction` | `LONG` or `SHORT`; equals the H1 `bias` at emission |
| `sweep_extreme` | sweep bar `low` (LONG) / `high` (SHORT) -- the structural invalidation level |
| `choch_time` | open time of the M5 CHoCH bar (trigger bar) |
| `entry_reference` | CHoCH bar **close**. A reference price, never an order. |
| `target_c11` | nearest UNSWEPT opposing causal M5 swing strictly beyond `entry_reference`; `None` -> `REJECT_NO_TARGET` |
| `stop_c10` | C10 stop price, or `None` with a `stop_reason` (see 3.4) |
| `expires_at` | section 4 |
| `invalidated_time` | first M5 **close** beyond `sweep_extreme` after the CHoCH bar |

Two `FROZEN` properties, load-bearing throughout:

- **Invalidation is a close, not a touch** (`close < sweep_extreme` LONG /
  `close > sweep_extreme` SHORT), on bars after the CHoCH bar.
- **Target and stop are touches, not closes.** Price side: section 7.

---

## 3. C10 stop rule

### 3.1 FROZEN -- the signed formula

From `P1` / `P2` / `P3`, contract `C10_STRUCTURAL_INVALIDATION_V1`:

```text
C10-A  structural buffer = DYNAMIC_ATR_WITH_HARD_FLOOR
       buffer = max(1.5 pips, 0.35 x ATR14(M5))
       ATR14  = Wilder-smoothed, closed M5 candles only, no look-ahead
       ATR missing or insufficient (< 15 closed M5 bars) => FAIL_CLOSED (ATR_NOT_READY)
       The 1.5-pip floor is NEVER used alone as a silent fallback.

C10-B  spread treatment = SIDE_AWARE
       LONG  : stop = anchor - buffer                      (no spread term)
       SHORT : stop = anchor + buffer + (ask - bid)        (verified live spread)
       Missing bid/ask for a SHORT => FAIL_CLOSED (MISSING_SPREAD)
       ask < bid                   => FAIL_CLOSED (INVALID_SPREAD)
       The spread appears EXACTLY ONCE, on the SHORT side only.

C10-C  broker minimum stop = REJECT
       Never WIDEN. WIDEN is not implemented and must not be implemented.
       No broker context supplied => NOT_APPLICABLE (never a silent PASS).

anchor  : the structural invalidation price. EXACT_REUSE -- never recomputed.
          Missing anchor => FAIL_CLOSED (MISSING_STRUCTURAL_ANCHOR).
          Never substituted with entry price or current price.
direction: LONG stop below the anchor, SHORT stop above it.
```

Fail-closed reason codes are `FROZEN`: `INVALID_DIRECTION`, `MISSING_STRUCTURAL_ANCHOR`,
`MISSING_ATR_DATA`, `ATR_NOT_READY`, `INVALID_ATR`, `MISSING_SPREAD`, `INVALID_SPREAD`,
`MISSING_ENTRY_FOR_MIN_STOP_CHECK`, `MIN_STOP_VIOLATION`.

### 3.2 FROZEN -- the C10-B asymmetry is intentional and load-bearing

`P3` states the reason: the LONG side omits the spread because `invalidation_price` is
"already Bid-side-consistent with a LONG's own SELL-stop trigger convention ... adding
spread here would double-count what the SHORT side accounts for once." Guarded by
`test_short_spread_not_double_counted` (`P1`).

**The published `stop_c10` is therefore already on a BID-comparable scale in both
directions.** Confirmed and adopted by the owner in `P12` (section 7.1).

### 3.3 FROZEN (`P12`, closes `LSMC-OD-02`) -- `STOP_BASIS`

Every opportunity carries a `STOP_BASIS` stamp:

| `STOP_BASIS` | Symbols | Stop level |
|---|---|---|
| `STOP_C10` | EURUSD, GBPUSD (`C10_PIP_SIZE`, `P4`) | the C10 formula, 3.1 |
| `SWEEP_EXTREME` | USDJPY, XAUUSD, BTCUSDT, ETHUSDT | `sweep_extreme` itself, no buffer |

`SWEEP_EXTREME` is consistent with the `R_AT_SEND` risk-anchor basis already used by the
delivery path (`risk_anchor()` falls back to `INVALIDATION_SWEEP_EXTREME`). Opportunities
are **no longer published stopless**; `STOP_REACHED` is reachable for all six symbols.

> **Derived consequence, not silently accepted.** With `STOP_BASIS = SWEEP_EXTREME`, the
> stop level equals the invalidation level. Because the stop is a *touch* and invalidation
> is a *close beyond*, any bar closing beyond the level must first have touched it --
> `STOP_REACHED` therefore fires on the same bar or earlier, in every case. `INVALIDATED`
> becomes **structurally unreachable** for those four symbols. Routed to `LSMC-OD-21`.
> The zero-buffer asymmetry against `STOP_C10` symbols is routed to `LSMC-OD-22`.

### 3.4 OPEN -- remaining C10 items

`LSMC-OD-01` (anchor substitution), `LSMC-OD-03` (stop immutability), `LSMC-OD-04` (C10-C
permanently `NOT_APPLICABLE`). See 8.2.

---

## 4. Opportunity expiry

### 4.1 FROZEN -- the computed expiry

From `P5` / `P6`:

```text
expires_at = session_end( choch_time + 5 minutes )

session_end(t):
  let m = UTC hour*60 + minute of t
  for each canonical session [start, end) in config/canonical_sessions.yaml:
      if start <= m < end:  return (UTC midnight of t) + end minutes
  otherwise:                return next_day_boundary(t)      # next 17:00 America/New_York

canonical sessions (UTC, half-open, fixed clock, no DST shift):
  asian       00:00 - 06:00
  london_am   06:00 - 11:00
  new_york_am 12:00 - 15:00
```

`FROZEN` properties: expiry is anchored to the **CHoCH bar close**, not the sweep bar and
not delivery time; boundaries are **half-open** (`now >= expires_at` is expired); expiry is
**terminal and non-reversible**; expiry and invalidation are independent clocks.

### 4.2 FROZEN -- separate POI expiry

A POI expires after `POI_MAX_AGE_TRADING_DAYS = 5` trading days (`P4`), at the trading-day
boundary following that age. It governs whether a *new* opportunity may form.

### 4.3 OPEN -- expiry items

`LSMC-OD-05` (uncovered-hours cliff), `LSMC-OD-06` (no minimum lifetime), `LSMC-OD-07`
(crypto on the FX calendar), `LSMC-OD-08` (POI expiry vs a live opportunity). See 8.2.

---

## 5. Outcome taxonomy

### 5.1 FROZEN (`P12`, closes `LSMC-OD-09`) -- the names

Outcomes are **structural facts, not trade results**. `WIN` / `LOSS` are **rejected** and
must not appear in any LSMC field, message or report.

| Outcome | Meaning |
|---|---|
| `TARGET_REACHED` | `target_c11` touched (side per section 7) |
| `STOP_REACHED` | the `STOP_BASIS` stop level touched (side per section 7) |
| `INVALIDATED` | M5 **close** beyond `sweep_extreme` |
| `EXPIRED` | `expires_at` passed with none of the above |
| `AMBIGUOUS_SAME_BAR` | both a target and a stop/invalidation event on one bar (section 6.1) |

No fill, slippage, cost or sizing is modelled. These outcomes are **not evidence of edge**.

### 5.2 FROZEN -- terminal-state structure

- Exactly **one** terminal outcome per opportunity; first qualifying event wins.
- Bars are scanned forward from the CHoCH bar close, in time order, **closed bars only**.
- Resolution never looks past `expires_at`.
- Until a terminal event occurs the outcome is `None` (open), never a default.
- Resolution is pure measurement; it never feeds back into detection, stop/target
  construction, or any later opportunity.

### 5.3 FROZEN -- the terminal events

| Event | Condition |
|---|---|
| `TARGET_REACHED` | bar `high >= target_c11` (LONG) / bar `low <= target_c11` (SHORT) -- a **touch** |
| `STOP_REACHED` | bar `low <= stop` (LONG) / bar `high >= stop` (SHORT) -- a **touch** |
| `INVALIDATED` | bar `close < sweep_extreme` (LONG) / `close > sweep_extreme` (SHORT) |
| `EXPIRED` | `expires_at` passed, nothing above fired |

### 5.4 FROZEN (`P12`, closes `LSMC-OD-10`) -- aggregates

Every aggregate is stratified by `STOP_BASIS`. All six symbols are now stop-bearing, so no
symbol is excluded for lacking a stop. The buffer asymmetry between the two bases remains
a comparability hazard -- `LSMC-OD-22`.

### 5.5 OPEN

`LSMC-OD-11` (keep `STOP_REACHED` and `INVALIDATED` distinct?), `LSMC-OD-20` (targetless
opportunities), `LSMC-OD-21` (`INVALIDATED` unreachable under `SWEEP_EXTREME`). See 8.2.

---

## 6. Same-bar tie, and gap handling

### 6.1 FROZEN (`P12`, closes `LSMC-OD-12`) -- same-bar tie

A bar whose `high >= target` **and** `low <= stop` (LONG; mirrored for SHORT) contains both
events; OHLC cannot order them. Same for a bar that reaches the target and closes beyond
`sweep_extreme`.

```text
1. If M1 data covering the bar is available, resolve the ordering from M1
   and emit the resulting terminal outcome, stamped tie_resolved_by = M1.
2. Otherwise the outcome is AMBIGUOUS_SAME_BAR:
     - persist both competing levels and the full bar OHLC
     - EXCLUDE from every outcome ratio
     - COUNT SEPARATELY and report the count alongside every ratio
```

A winner is never imputed. `AMBIGUOUS_SAME_BAR` is never folded into another outcome for
"conservatism" -- that would bias the statistic it feeds.

> **Current reality.** The LSMC pipeline carries `TIMEFRAME_MINUTES = {D1, H1, M5}` only
> (`P4`); no M1 source is wired. Branch 1 is therefore **never taken today**. Routed to
> `LSMC-OD-26`.

### 6.2 FROZEN (`P12`, closes `LSMC-OD-17`) -- gap through a level

When the bar that triggers a terminal event **opens beyond** the level it triggered, the
outcome is recorded **at the gap open price**, not at the level, and stamped
`GAP_THROUGH = true`. Both the level price and the bar open are persisted.

This corrects the prior behaviour, where `high >= target` was satisfied by a gap *over* the
level and recorded a price that never traded.

If a single gap carries price beyond **both** the stop and the target, it is a same-bar tie
and 6.1 applies, with `GAP_THROUGH = true` on both legs.

### 6.3 OPEN -- gap residuals

The 6.2 ruling fixes **pricing**. It does not determine:

- `LSMC-OD-18` -- distinguishing a **data outage** from a **true market gap** (the bar
  series cannot tell them apart; one is a measurement failure, the other a market fact).
- `LSMC-OD-19` -- an `expires_at` that falls **inside a scheduled market closure**, where
  no bar exists in which to resolve.

Interim until signed: a missing-bar span over an **open** market halts resolution with the
outcome left open; it is never advanced to `EXPIRED` on absent data. See 8.2.

---

## 7. Side-correct prices

### 7.1 FROZEN (`P12`, closes `LSMC-OD-13` and `LSMC-OD-16`) -- the side matrix

| Level | Side | Observable in bid bars (`P9`)? |
|---|---|---|
| LONG target | **bid** | yes, directly |
| LONG stop | **bid** | yes, directly |
| SHORT stop | **bid** | yes, directly -- C10-B already embeds the spread (3.2) |
| SHORT target | **ask** | no -- requires the reconstruction in 7.2 |

The SHORT stop stays on **bid** precisely because `stop_c10` already contains the spread
once; testing it against a reconstructed ask would add the spread a second time, widening
the effective SHORT stop by one full spread and systematically under-reporting
`STOP_REACHED` on shorts. This was the v1.0.0 §7.3 finding and the owner has adopted it.

`LSMC-OD-16` (a bid-derived level tested against an ask-side touch) is closed by the same
ruling: `target_c11` is bid-derived and the SHORT target is nonetheless resolved on ask.
Every level carries `level_basis = BID` so the asymmetry is always visible in the record.

### 7.2 FROZEN (`P12`, closes `LSMC-OD-14`) -- ask reconstruction

```text
PRIMARY   ask = bid + (MT5 per-bar spread field)
FALLBACK  ask = bid + (symbol typical spread)   ->  flag ASK_APPROXIMATED
```

The fallback is used whenever the per-bar spread field is unavailable for the bar being
tested.

> **Two blocking facts, not silently absorbed.**
>
> 1. **The primary path is not available to this pipeline today.** `Candle` (`P10`) carries
>    only `time/open/high/low/close/volume` -- there is no spread field. The column is
>    exported by `scripts/acquire_ssc_one_year_m1_mt5.py`, but the repository's own record
>    states it "is not synchronized bid/ask OHLC, is not carried by TD-8E `Candle`, and
>    lacks a frozen point-in-time interpretation." Routed to `LSMC-OD-23`.
> 2. **No typical-spread constant exists for this universe.** The only precedent (`P11`)
>    covers EURUSD and GBPUSD only, and is labelled "not broker-verified". USDJPY, XAUUSD,
>    BTCUSDT and ETHUSDT have none. Routed to `LSMC-OD-25`.
>
> A third point: even the primary path is an approximation -- MT5's per-bar spread is a
> single value, not a synchronized ask OHLC, so applying it to an intra-bar high or low
> prices an extreme with a spread observed at a different instant. Routed to
> `LSMC-OD-24`.

Until `LSMC-OD-23` / `LSMC-OD-25` are closed, SHORT targets on symbols with no constant
remain `UNRESOLVABLE` and are counted separately, never silently dropped.

### 7.3 OPEN

`LSMC-OD-15` (invalidation side). See 8.2.

---

## 8. Owner decisions

### 8.1 Closed by the 2026-10-07 owner batch (`P12`)

| Ref | Ruling | Applied in |
|---|---|---|
| `LSMC-OD-02` | Non-C10 symbols use `STOP_BASIS = SWEEP_EXTREME` | 3.3 |
| `LSMC-OD-09` | Outcomes are `TARGET_REACHED` / `STOP_REACHED` -- structural, not trade results. `WIN`/`LOSS` rejected. | 5.1 |
| `LSMC-OD-10` | All symbols stop-bearing; aggregates stratified by `STOP_BASIS` | 5.4 |
| `LSMC-OD-12` | `AMBIGUOUS_SAME_BAR`; resolve from M1 if available, else excluded from ratios and counted separately | 6.1 |
| `LSMC-OD-13` | long stop/target = bid; short stop = bid; short target = ask | 7.1 |
| `LSMC-OD-14` | `ask = bid + bar spread`; fallback typical spread, flag `ASK_APPROXIMATED` | 7.2 |
| `LSMC-OD-16` | Closed by `LSMC-OD-13` -- a bid-derived level resolved on ask is accepted, stamped `level_basis` | 7.1 |
| `LSMC-OD-17` | Gap through a level records the **gap open price**, flag `GAP_THROUGH` | 6.2 |

### 8.2 Remaining OWNER_DECISION_REQUIRED -- recommended defaults for batch sign-off

**Nothing below is applied.** Each row is a proposal awaiting signature. `LSMC-OD-21`
through `LSMC-OD-26` are **new**, arising directly from the 8.1 rulings.

| Ref | Decision required | Recommended default | Rationale |
|---|---|---|---|
| `LSMC-OD-01` | Is `sweep_extreme` an authorized C10 anchor on the 1.1.0 watch path, or must the signed `invalidation_price` anchor be wired? | **Accept `sweep_extreme`**, stamped `anchor_source = SWEEP_EXTREME` | It *is* the structural invalidation level for the 1.1.0 path (invalidation is defined as a close beyond it), so it is semantically the object the signed contract names. `SMCEntryCombinationResult.invalidation_price` belongs to the 1.0.7 research engine, which the watch path does not run. `LSMC-OD-02` has already adopted `SWEEP_EXTREME` as a stop basis -- accepting it here keeps **one** definition instead of two. |
| `LSMC-OD-03` | Is `stop_c10` immutable at first publication, or recomputed each evaluation? | **Immutable at first publication**; persist the stop with its inputs (ATR value, spread, anchor) | Outcome resolution is not well-posed against a moving stop. The SHORT stop embeds a live spread, so a recomputed stop drifts and the same opportunity could resolve `STOP_REACHED` or not purely by evaluation timing. Immutability matches the frozen-identity principle in section 9. |
| `LSMC-OD-04` | Does C10-C (`REJECT`) stay permanently `NOT_APPLICABLE` on the watch path? | **Stays `NOT_APPLICABLE` while advisory-only; becomes a blocking pre-Demo requirement** | It is an execution-capability check with no meaning while `proposal_generation_authorized = False`. It must not be quietly forgotten, so tie it to the pre-Demo gate. Never a silent `PASS`, never `WIDEN`. |
| `LSMC-OD-05` | Is the 11:00-12:00 / 15:00-24:00 UTC fall-through to the NY 17:00 boundary intended? | **Cap lifetime: `expires_at = min(session_end(...), choch_close + 24 M5 bars)`** (owner-signed constant) | Today a 10-minute shift in trigger time swings the lifetime from ~5 minutes to ~10 hours. A single cap bounds the asymmetry without inventing new session boxes or editing `config/canonical_sessions.yaml`, which is canonical and shared with other strategies. **The 24-bar value is unevidenced and needs an owner signature.** |
| `LSMC-OD-06` | Is there a minimum opportunity lifetime? | **Floor of 6 M5 bars (30 min)**; extend `expires_at` to the floor when `session_end` would give less (owner-signed constant) | An opportunity expiring 2 minutes after its trigger records a timing artifact, not a market fact, and inflates `EXPIRED`. 6 bars is the smallest window in which the C11 target could plausibly be reached. Alternative: suppress sub-floor opportunities entirely -- statistically cleaner, loses observations. **Value needs a signature.** |
| `LSMC-OD-07` | Should crypto use a continuous-market expiry? | **Yes -- crypto uses the `LSMC-OD-05` duration cap only; no session boxes, no NY boundary** | BTCUSDT/ETHUSDT trade continuously. FX session boxes and the 17:00 NY roll are FX market-structure artifacts with no meaning for them. A duration cap avoids inventing crypto session boxes with no evidence behind them. |
| `LSMC-OD-08` | Does POI expiry terminate an opportunity already derived from that POI? | **No -- the opportunity keeps its own clock**; record both IDs | The POI clock governs *formation*. Once the CHoCH has fired the structural event is complete; terminating on POI age would make outcomes depend on a level that has already done its job. |
| `LSMC-OD-11` | Do `STOP_REACHED` and `INVALIDATED` stay distinct, or collapse? | **Keep distinct**; offer an optional derived rollup `ADVERSE = STOP_REACHED ∪ INVALIDATED` for ratios | They are different structural facts -- a touch of the risk level versus a close beyond the thesis level. Collapsing them destroys the only signal separating "stopped by noise" from "thesis broken". A derived rollup gives the simple ratio without losing the distinction. |
| `LSMC-OD-15` | Is the invalidation close side-corrected, or left bid? | **Left bid, unchanged**; stamp `invalidation_basis = BID` | `invalidated_time` is already computed at detection time by merged code (`detect.m5_opportunities`). Side-correcting it in the resolver would make the resolver and detection disagree about whether an opportunity is still alive. One definition, owned by detection. |
| `LSMC-OD-18` | Data outage vs true market gap -- which staleness rule applies to resolution? | **Classify by market calendar**: gap spanning an *open* market -> `DATA_GAP`, resolution halts, outcome stays open. Gap spanning a *scheduled closure* -> `MARKET_GAP`, resolves at the reopen bar's open with `GAP_THROUGH`. | The calendar (`fx_market_closed`, crypto 24/7) is the only independent evidence available. Without it a data outage is silently recorded as a real market move, which is the worst failure mode for a measurement-only resolver. |
| `LSMC-OD-19` | `expires_at` inside a scheduled market closure -- `EXPIRED` at the boundary or deferred to reopen? | **`EXPIRED` at `expires_at`**, flagged `EXPIRY_IN_MARKET_CLOSED` | No bar exists in which a price-based outcome could occur. Deferring to reopen silently extends the opportunity past its signed expiry and lets a weekend gap decide the outcome. |
| `LSMC-OD-20` | Is an opportunity with `target_c11 = None` (`REJECT_NO_TARGET`) resolvable? | **Resolvable for `STOP_REACHED` / `INVALIDATED` / `EXPIRED` only**; never `TARGET_REACHED`; excluded from any target-hit-rate denominator, counted separately as `NO_TARGET` | Mirrors the `LSMC-OD-12` treatment: counted, not silently dropped, and not allowed to bias a ratio it cannot contribute to. |
| **`LSMC-OD-21`** *(new)* | `STOP_BASIS = SWEEP_EXTREME` places the stop exactly at the invalidation level, so `INVALIDATED` is **structurally unreachable** for USDJPY, XAUUSD, BTCUSDT, ETHUSDT. Accept, or separate the levels? | **Accept, and suppress the separate outcome for those symbols**: record `STOP_REACHED` with `invalidation_coincident = true`; publish **no** `INVALIDATED` rate for `SWEEP_EXTREME` symbols | A close beyond the level implies a touch of it on the same bar, so `STOP_REACHED` always fires first. Reporting a near-zero `INVALIDATED` rate would be an artifact of level coincidence, not market behaviour. The alternative -- adding a buffer -- requires the signed pip/tick sizes those symbols lack (`LSMC-OD-22`). |
| **`LSMC-OD-22`** *(new)* | `STOP_C10` symbols get `max(1.5 pips, 0.35 x ATR14)` of buffer; `SWEEP_EXTREME` symbols get **zero**. How are the two compared? | **Never pool them in one ratio -- always stratify by `stop_basis`** (as 5.4 already requires). Revisit only if the owner signs pip/tick sizes for the other four symbols | Zero-buffer stops will show a structurally higher `STOP_REACHED` rate for reasons unrelated to setup quality. The ruling changed the mechanism but not the comparability problem the original `LSMC-OD-10` identified. |
| **`LSMC-OD-23`** *(new)* | The MT5 per-bar spread field is **not carried** by `Candle` (`P10`) and the repo records it as "not synchronized bid/ask OHLC ... lacks a frozen point-in-time interpretation". Wire it, or stay on the fallback? | **Until `Candle` carries a spread field with a frozen interpretation, the primary path is unavailable and every ask-side resolution uses the fallback with `ASK_APPROXIMATED`** | Fail closed rather than claim a precision the data does not have. Wiring it is a data-pipeline change (acquisition + bar type + a frozen interpretation), not a spec change, and should be authorized separately. |
| **`LSMC-OD-24`** *(new)* | The **primary** path is also approximate -- one spread value per bar applied to an intra-bar extreme observed at a different instant. Flag it? | **Flag both paths**: `ASK_BAR_SPREAD` on the primary, `ASK_APPROXIMATED` on the fallback. Neither is an exact ask touch. | The 8.1 ruling flags only the fallback, which implies the primary path is exact. It is not. Distinct flags keep the two approximation classes separable in analysis. |
| **`LSMC-OD-25`** *(new)* | Typical-spread constants do not exist for this universe. Which values, for which symbols? | **Reuse `P11` for EURUSD (1.0 pip) and GBPUSD (1.4 pips) under the same `cost_status` convention. The other four symbols get no constant -- their SHORT targets stay `UNRESOLVABLE`.** | Reuses an existing signed precedent instead of inventing numbers, and fails closed where none exists. Note `P11` is itself labelled "not broker-verified", so these are modelled, not known, costs. |
| **`LSMC-OD-26`** *(new)* | M1 is not in the LSMC pipeline (`TIMEFRAME_MINUTES = {D1, H1, M5}`), so `LSMC-OD-12`'s M1 tie-resolution branch is never taken. | **Treat M1 tie-resolution as inactive**: every tie records `AMBIGUOUS_SAME_BAR` with `m1_available = false`, until an M1 source is wired and frozen | States the real current behaviour instead of implying ties are usually resolved. Wiring M1 is a separate data-pipeline authorization. |

---

## 9. Change control

1. This file is frozen at `spec_version 1.0.1`. Its SHA-256 is recorded in
   `docs/specs/LSMC_SPEC_V1_FROZEN.sha256.txt`.
2. A `FROZEN` rule may not be edited in place. Changing one requires a new signed owner
   decision and a new file (`LSMC_SPEC_V2_...`).
3. Closing an `OWNER_DECISION_REQUIRED` row requires an owner signature, then a new spec
   version. Agents may not close rows, and may not apply a recommended default from 8.2
   without a signature.
4. This spec grants no authority. `ST_LARGE_SMC_V1` stays `RESEARCH_DRAFT` / advisory-only.
5. Delivery and actionability remain governed solely by `LSMC_ACTIONABILITY_POLICY_V1`
   (section 0.2). Reference it; do not restate it.

---

## 10. Changelog

### 1.0.1 -- 2026-10-07 (supersedes `94dd0fb9226bd078d0ee8d49125af58692fe595e0f65bc57181354f60e999a7e`)

Applies the 2026-10-07 owner batch. **No `FROZEN` rule from 1.0.0 was altered** -- this
version only closes `OPEN` rows and records the consequences, per section 9.3.

| # | Change | Section |
|---|---|---|
| 1 | `LSMC-OD-13` applied. Side matrix frozen: long stop/target = bid, short stop = bid, short target = ask. The v1.0.0 §7.3 double-count finding is adopted as the reason the short stop stays on bid. | 7.1 |
| 2 | `LSMC-OD-14` applied. Ask reconstruction frozen: `bid + bar spread`, fallback typical spread with `ASK_APPROXIMATED`. | 7.2 |
| 3 | `LSMC-OD-16` closed by the `LSMC-OD-13` ruling; `level_basis = BID` stamp added. | 7.1 |
| 4 | `LSMC-OD-12` applied. `AMBIGUOUS_SAME_BAR`; M1 resolution when available; otherwise excluded from ratios and **counted separately**. | 6.1 |
| 5 | `LSMC-OD-09` applied. Outcome set renamed to `TARGET_REACHED` / `STOP_REACHED` / `INVALIDATED` / `EXPIRED` / `AMBIGUOUS_SAME_BAR`. `WIN`/`LOSS` rejected repo-wide. | 5.1 |
| 6 | `LSMC-OD-17` applied. Gap through a level records the **gap open price** with `GAP_THROUGH`; replaces the v1.0.0 interim that recorded the level price. | 6.2 |
| 7 | `LSMC-OD-02` + `LSMC-OD-10` applied. `STOP_BASIS` introduced (`STOP_C10` / `SWEEP_EXTREME`); no symbol is stopless; aggregates stratified by `stop_basis`. | 3.3, 5.4 |
| 8 | Remaining 12 rows carried forward, each gaining a **recommended default + rationale** for batch sign-off. None applied. | 8.2 |
| 9 | Six **new** rows added (`LSMC-OD-21`..`26`), arising from the rulings above: `INVALIDATED` unreachable under `SWEEP_EXTREME`; zero-buffer comparability; `Candle` carries no spread field; the primary ask path is itself approximate; no typical-spread constants exist for four of six symbols; M1 is absent from the pipeline. | 8.2 |
| 10 | Source pins `P10` (bar type), `P11` (spread-constant precedent), `P12` (this owner batch) added. | 1 |
| 11 | v1.0.0 §7.3 (the double-count finding) folded into 3.2 and 7.1 now that the owner has ruled on it; retained verbatim in substance. | 3.2, 7.1 |

### 1.0.0 -- 2026-10-07

Initial freeze. SHA-256 `94dd0fb9226bd078d0ee8d49125af58692fe595e0f65bc57181354f60e999a7e`.
20 `OWNER_DECISION_REQUIRED` rows, none resolved.
