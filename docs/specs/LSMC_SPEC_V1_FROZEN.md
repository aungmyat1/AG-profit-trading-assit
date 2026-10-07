# LSMC_SPEC_V1_FROZEN -- ST_LARGE_SMC_V1 strategy-logic freeze

| Field | Value |
|---|---|
| `spec_id` | `LSMC_SPEC_V1_FROZEN` |
| `spec_version` | `1.0.0` |
| `strategy_id` | `ST_LARGE_SMC_V1` |
| `strategy_versions_covered` | `1.0.7` (`strategies/ST_LARGE_SMC_V1.yaml`) and `1.1.0` (`src/large_smc_watch/contract.py`) |
| `status` | `FROZEN_WITH_OPEN_DECISIONS` |
| `authority` | Specification artifact. Confers no proposal, Demo, Live, execution or risk-sizing authority. |
| `mission` | `AG_ARENA_RESET_A1_R1` step A1 |
| `frozen_utc` | 2026-10-07 |

**What "FROZEN_WITH_OPEN_DECISIONS" means.** Every rule in this document marked `FROZEN`
is closed: it is traceable to an owner-signed decision or to already-merged code on
`main`, and it may not be changed by editing this file. Any change requires a new signed
owner decision and a new spec version (`LSMC_SPEC_V2_...`), never an in-place edit.

Every rule marked `OPEN` is **not** decided. It is written here as an explicit question in
section 8 (`OWNER_DECISION_REQUIRED`), together with the interim fail-closed behaviour that
applies until the owner rules on it. **No open item has been resolved silently in this
document.** Where the commissioning mission asked for a definition that the repository's
evidence does not support, this spec states the boundary of what is decided, states the
interim behaviour, and routes the remainder to section 8.

---

## 0. Scope

### 0.1 In scope -- strategy logic only

1. The C10 stop rule (stop construction).
2. Opportunity expiry.
3. The outcome taxonomy `WIN` / `LOSS` / `EXPIRED` / `INVALIDATED`.
4. The same-bar stop+target tie rule.
5. Gap handling.
6. Side-correct prices for level resolution.

### 0.2 Explicitly NOT in scope

`LSMC_ACTIONABILITY_POLICY_V1` (owner decisions D1-D8, 2026-10-07) governs **delivery and
actionability**: freshness, remaining-R at send, downtime recovery, send-time state
semantics, price-normalization timing, correlation tagging and Demo gating. Those rules are
**not restated, summarized, amended or re-derived here**, per the A1 instruction.

The boundary this spec uses:

> This spec governs what the *market* did to an opportunity's own levels.
> `LSMC_ACTIONABILITY_POLICY_V1` governs whether, when and how an opportunity is *told to
> the owner*.

One consequence is recorded deliberately and is **not** a delivery rule: an opportunity's
strategy-level outcome is resolved **independently of whether it was ever delivered**. A
`MISSED_DOWNTIME` or `INFO_ONLY_STALE` opportunity still has a strategy outcome under this
spec. The two vocabularies are disjoint and must never be merged into one field.

### 0.3 Authority and separations

`IMPLEMENTED != VALIDATED != AUTHORIZED`. This spec is a specification artifact. It changes
no code, no strategy YAML, no threshold and no registry entry. `ST_LARGE_SMC_V1` remains
`RESEARCH_DRAFT` / advisory-only with `proposal_generation_authorized = False`
(`src/large_smc_watch/contract.py`). Nothing here is evidence of edge.

---

## 1. Source pins

Every rule below is pinned to one of these. Nothing else was used as authority.

| Pin | Source | Identity |
|---|---|---|
| `P1` | Owner decision packet, C10 | `docs/status/AG_LARGE_SMC_V1_C10_STOP_POLICY_OWNER_DECISION_PACKET_V3_STATUS.md`, `SIGNED_AND_LOCKED` 2026-09-07, `C10_STRUCTURAL_INVALIDATION_V1` |
| `P2` | Strategy contract | `strategies/ST_LARGE_SMC_V1.yaml` v1.0.7, `stop_loss_contract` block |
| `P3` | C10 implementation | `src/large_smc_core/c10_stop_policy.py` (on `main` @ `fc60cdb`) |
| `P4` | Watch contract constants | `src/large_smc_watch/contract.py` (`ST_LARGE_SMC_V1@1.1.0`) |
| `P5` | Watch detection + expiry | `src/large_smc_watch/detect.py`, `src/large_smc_watch/watch.py` (on `main` @ `fc60cdb`) |
| `P6` | Session windows | `config/canonical_sessions.yaml`, `CANONICAL_SESSION_WINDOWS_V1`, half-open, fixed UTC |
| `P7` | Provisional outcome resolver | `src/host_delivery/lsmc_outcome.py` @ `acfc25e`, branch `feat/ag-v1-host-hardening-r1` (**draft PR #49, unmerged**) |
| `P8` | Provisional side convention | PR #49 body, "Interpretations to confirm" |
| `P9` | Price convention | MT5 native **BID-based** bar OHLC (`docs/status/SSC_V1_0_1_ONE_YEAR_M1_ACQUISITION_STATUS.md`; `scripts/acquire_ssc_one_year_m1_mt5.py`) |

`P7` and `P8` are **unmerged draft** material. They are cited as the provisional baseline the
A1 instruction named, never as settled authority.

### 1.1 Governance record used for the scope boundary

`docs/governance/OWNER_DECISIONS_2026-10-07_LSMC_ACTIONABILITY_V1.md`, canonical 94-line
record, SHA-256 `67bb1a57a7bc38335fdb18d7bdf7880c39331247a44abbc473e35cf1eecb7b56`
(commit `f4ec100`, branch `feat/ag-v1-host-hardening-r1`). Used **only** to determine what
section 0.2 excludes. No rule from it is reproduced here.

---

## 2. The opportunity object (frozen reference)

`FROZEN` -- from `P5`. An LSMC opportunity is emitted when state `OPPORTUNITY` is reached.
These are the only fields this spec's rules operate on.

| Field | Meaning | Source |
|---|---|---|
| `opp_id` | `{poi_id}\|{sweep_bar_time}\|{choch_bar_time}` | `detect.m5_opportunities` |
| `direction` | `LONG` or `SHORT` | must equal the H1 `bias` at emission |
| `sweep_extreme` | sweep bar `low` (LONG) / `high` (SHORT) | the structural invalidation level |
| `choch_time` | open time of the M5 CHoCH bar | trigger bar |
| `entry_reference` | CHoCH bar **close**. A reference price, never an order. | `detect.m5_opportunities` |
| `target_c11` | nearest UNSWEPT opposing causal M5 swing strictly beyond `entry_reference`; `None` -> `REJECT_NO_TARGET` | `detect.c11_causal_target` |
| `stop_c10` | C10 stop price, or `None` with a `stop_reason` | section 3 |
| `expires_at` | section 4 | `watch.session_end` |
| `invalidated_time` | first M5 **close** beyond `sweep_extreme` after the CHoCH bar | `detect.m5_opportunities` |

Two properties are `FROZEN` and load-bearing for everything below:

- **Invalidation is a close, not a touch.** `close < sweep_extreme` (LONG) /
  `close > sweep_extreme` (SHORT), evaluated only on bars after the CHoCH bar (`P5`).
- **The target is a touch, not a close** (`P7`, `P8`). See section 7 for which price side
  the touch is measured on.

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

`P3` states the reason explicitly: the LONG side omits the spread because
"`invalidation_price` is treated as already Bid-side-consistent with a LONG's own SELL-stop
trigger convention ... adding spread here would double-count what the SHORT side accounts
for once."

**Therefore the published `stop_c10` is already expressed on a BID-comparable scale for
both directions.** Any downstream rule that adds a spread again when testing whether the
stop was reached double-counts it. This is the direct cause of `LSMC-OD-13` (section 7.3).

### 3.3 OPEN -- C10 items this spec does not close

| Ref | Issue |
|---|---|
| `LSMC-OD-01` | Anchor substitution: `P1`/`P2` sign the anchor as `SMCEntryCombinationResult.invalidation_price`; the 1.1.0 watch path (`P5`) passes `o.sweep_extreme`. Different object, never signed as equivalent. |
| `LSMC-OD-02` | Symbol coverage: `C10_PIP_SIZE` (`P4`) holds EURUSD and GBPUSD only. USDJPY, XAUUSD, BTCUSDT, ETHUSDT emit `stop_c10 = None`, `stop_reason = C10_PIP_SIZE_NOT_EVIDENCED`, and the opportunity is still published stopless. |
| `LSMC-OD-03` | Stop immutability: the watch computes the stop from `m5c[: choch_index + 1]` and the bid/ask at evaluation time. Whether the stop is frozen at first publication or recomputed per evaluation is undefined. Outcome resolution is not well-posed until this is fixed. |
| `LSMC-OD-04` | C10-C is permanently `NOT_APPLICABLE` at the watch call site (no replay-safe broker-metadata seam, per `P2`). |

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

next_day_boundary: 17:00 America/New_York (IANA, DST-aware)
```

`FROZEN` properties:

- Expiry is anchored to the **CHoCH bar close** (`choch_time + 5m`), not to the sweep bar
  and not to delivery time.
- Boundaries are **half-open**: an opportunity is expired when `now >= expires_at`.
- Expiry is a **terminal, non-reversible** state for the opportunity.
- Expiry and invalidation are independent: invalidation is structural (a close beyond
  `sweep_extreme`), expiry is temporal.

### 4.2 FROZEN -- separate POI expiry

A POI expires after `POI_MAX_AGE_TRADING_DAYS = 5` trading days (`P4`), at the trading-day
boundary following that age. POI expiry governs whether a *new* opportunity may form from
that POI. It is a distinct clock from opportunity expiry.

### 4.3 OPEN -- expiry items this spec does not close

The frozen formula above has three consequences that are mechanical facts of the code, not
owner decisions. They are recorded as OPEN because the formula was never reviewed against
them.

| Ref | Issue |
|---|---|
| `LSMC-OD-05` | **Uncovered-hours cliff.** `P6` leaves 11:00-12:00 and 15:00-24:00 UTC outside every canonical session. A CHoCH at 10:55 UTC expires at 11:00 (~5 min of life); a CHoCH at 11:05 UTC falls through to the NY 17:00 boundary (~10 h of life). A 10-minute shift in trigger time changes the lifetime by two orders of magnitude. |
| `LSMC-OD-06` | **No minimum lifetime.** A CHoCH closing at 05:58 UTC expires at 06:00. No floor exists. |
| `LSMC-OD-07` | **Crypto uses the FX calendar.** `BTCUSDT`/`ETHUSDT` are in `V1_SYMBOLS` (`P4`) and trade continuously, but their expiry is computed from FX session boxes and the NY 17:00 FX trading-day boundary. |
| `LSMC-OD-08` | **POI expiry vs a live opportunity.** Undefined whether a POI reaching `POI_MAX_AGE_TRADING_DAYS` terminates an opportunity already derived from it, or whether the opportunity survives on its own clock. |

---

## 5. Outcome taxonomy

### 5.1 The requested four-state taxonomy

The A1 instruction requires `WIN` / `LOSS` / `EXPIRED` / `INVALIDATED`. The only existing
resolver (`P7`, unmerged draft) emits a different five-state set, and declares itself
**measurement only**: "not a trade result, not a fill and not evidence of edge".

### 5.2 FROZEN -- terminal-state structure

Independent of naming, these are `FROZEN`:

- An opportunity has **exactly one** terminal outcome. Outcomes are mutually exclusive and
  the first qualifying event wins.
- Bars are scanned forward from the CHoCH bar close, in time order, **closed bars only**.
- Resolution never looks past `expires_at`.
- Until a terminal event occurs the outcome is `None` (open), never a default.
- Resolution is pure measurement. It never feeds back into detection, stop/target
  construction, or any later opportunity.

### 5.3 FROZEN -- the three unambiguous terminal events

| Event | Condition | Side | Status |
|---|---|---|---|
| target reached | bar `high >= target_c11` (LONG) / bar `low <= target_c11` (SHORT) -- a **touch** | section 7 | `FROZEN` |
| stop reached | `stop_c10` exists and bar `low <= stop_c10` (LONG) / bar `high >= stop_c10` (SHORT) -- a **touch** | section 7 | `FROZEN` |
| invalidation | bar **close** beyond `sweep_extreme` (`close < extreme` LONG / `close > extreme` SHORT) | section 7.4 | `FROZEN` |
| expiry | `expires_at` passed with none of the above | n/a | `FROZEN` |

### 5.4 OPEN -- naming and precedence

| Ref | Issue |
|---|---|
| `LSMC-OD-09` | **`WIN`/`LOSS` is a claim upgrade.** `P7` is explicitly *not* a trade result (no fill, no slippage, no costs, no sizing). Relabelling "price touched the target level" as `WIN` asserts a realized outcome the measurement cannot support, and would be read as edge evidence. Proposed mapping (**not applied**): `TARGET_REACHED -> WIN`, `STOP_TOUCHED -> LOSS`, `INVALIDATED -> INVALIDATED`, `EXPIRED -> EXPIRED`. |
| `LSMC-OD-10` | **Stopless opportunities cannot produce `LOSS`.** Per `LSMC-OD-02`, four of six symbols publish `stop_c10 = None`. For those, `LOSS` is unreachable and every adverse path resolves as `INVALIDATED` or `EXPIRED`, which silently biases any WIN/LOSS ratio computed across symbols. |
| `LSMC-OD-11` | **Stop vs invalidation precedence on different bars.** `P7` resolves first-qualifying-bar-wins, so whichever occurs earlier terminates. Undefined whether `STOP_TOUCHED` and `INVALIDATED` should remain distinct outcomes or both collapse into `LOSS`. For a LONG, `stop_c10 = sweep_extreme - buffer` sits *below* the invalidation level, so a touch-based stop and a close-based invalidation routinely compete. |

---

## 6. Same-bar stop+target tie rule, and gap handling

### 6.1 OPEN -- same-bar tie

A single M5 bar whose `high >= target` **and** `low <= stop` (LONG; mirrored for SHORT)
contains both events. OHLC does not record their order. The same applies to a bar that
reaches the target and closes beyond `sweep_extreme`.

**This spec does not resolve the tie.** `P7` records `AMBIGUOUS_SAME_BAR`, which has no
home in the requested four-state taxonomy.

**Interim behaviour until `LSMC-OD-12` is decided (fail-closed):** record the terminal
outcome as `AMBIGUOUS_SAME_BAR`, persist both competing levels and the full bar OHLC, and
**exclude the opportunity from every WIN/LOSS aggregate**. Never impute a winner. Never
silently fold it into `LOSS` for conservatism -- that is itself an unapproved decision and
biases the statistic it feeds.

### 6.2 OPEN -- gap handling

`P7` contains no gap logic. The inequalities it uses (`high >= target`, `low <= stop`) are
satisfied by a gap that jumps *over* a level, so a gap is currently recorded as a touch
**at the level**, implying a price that never traded. Four distinct cases exist and none is
decided:

1. **Gap through one level** -- the bar opens already beyond the stop or the target.
2. **Gap through both** -- the bar opens beyond one level having gapped past the other;
   this is a same-bar tie created entirely by the gap.
3. **Weekend / session gap** -- FX closes Friday 17:00 NY and reopens Sunday 17:00 NY
   (`P4`, `fx_market_closed`). An opportunity whose `expires_at` falls inside the closed
   window has no bars in which to resolve.
4. **Missing bars vs a true market gap** -- a data outage and a real price gap are
   indistinguishable in the bar series. `P4` treats >15 min of missing M5 as `M5_DATA_STALE`
   for detection, but no equivalent rule exists for outcome resolution.

**Interim behaviour until `LSMC-OD-14`/`LSMC-OD-15` are decided (fail-closed):** when the
bar that triggers a terminal event **opens beyond** the level it triggered, record the
outcome with `gap_flag = true`, persist both the level price and the bar open, and exclude
the opportunity from any aggregate that depends on the realized price. When a required bar
is absent, resolution **halts** and the outcome stays open; it is never advanced to
`EXPIRED` on absent data.

---

## 7. Side-correct prices

### 7.1 Provisional baseline (`P8`)

From PR #49, "Interpretations to confirm":

- Send/entry side: `LONG` uses **ask**, `SHORT` uses **bid**.
- Exit side, as named in the A1 instruction: **long target = bid touch, short target = ask
  touch**.

These are consistent: a long is entered at the ask and exited at the bid; a short is
entered at the bid and exited at the ask.

### 7.2 FROZEN -- the blocking data fact

`P9`: this repository's bar data is **MT5 native BID-based OHLC**. Therefore:

| Level | Required side (`P8`) | Observable in bid bars? |
|---|---|---|
| LONG target | bid touch | **yes**, directly |
| SHORT target | ask touch | **no** -- requires an ask series that does not exist |
| LONG stop | bid touch (implied) | **yes**, directly |
| SHORT stop | ask touch (implied) | **no** -- but see 7.3 |

Half of the required comparisons cannot be evaluated from the data the strategy actually
has. No spread series is carried by the bar type in use.

### 7.3 FROZEN finding -- applying an ask touch to the SHORT stop double-counts the spread

This is the most consequential interaction in this spec and it is a hard inconsistency, not
a preference.

C10-B (section 3.1, `FROZEN`) already defines the SHORT stop as
`anchor + buffer + (ask - bid)`. `P3` states the spread term exists precisely to protect a
bid-derived anchor from ask-side trigger effects, and that it must appear **exactly once**.
The repository carries a unit test for this (`test_short_spread_not_double_counted`, `P1`).

Consequently, testing the SHORT stop against a reconstructed **ask** series would add the
spread a second time, widening the effective SHORT stop by one full spread and
systematically under-reporting `LOSS` on shorts.

**The correct SHORT-stop comparison under the current frozen C10 contract is a BID touch**,
because the spread is already inside `stop_c10`. This is stated as a FROZEN consequence of
C10-B, not as a new decision -- but it means the A1 instruction's exit-side convention
**cannot be applied uniformly to stops and targets**. The target side has no such
compensation and genuinely does need an ask series. Routed to `LSMC-OD-13`.

### 7.4 OPEN -- side items this spec does not close

| Ref | Issue |
|---|---|
| `LSMC-OD-13` | **Stop side vs target side conflict.** SHORT target needs an ask touch; SHORT stop must stay a bid touch or C10-B's spread is double-counted (7.3). An opportunity would be resolved against two different price series. |
| `LSMC-OD-14` | **Ask reconstruction.** No ask series exists (`P9`). Options: (a) `ask = bid + live spread` -- unavailable historically; (b) `ask = bid + frozen per-symbol spread constant` -- needs an owner-signed constant per symbol and is wrong under news conditions; (c) export MT5's per-bar `spread` column and freeze its interpretation; (d) do not reconstruct -- SHORT targets are `UNRESOLVABLE` and SHORT opportunities are excluded from outcome statistics. |
| `LSMC-OD-15` | **Invalidation side.** Invalidation is a close beyond `sweep_extreme`. Undefined whether that close is bid (as recorded) or side-corrected. Side-correcting it would change the detection-time `invalidated_time` already produced by `P5`, which is merged code. |
| `LSMC-OD-16` | **`sweep_extreme` is bid-derived.** Both `stop_c10` and `target_c11` are built from bid-based structure (`P5`). Mixing a bid-derived level with an ask-side touch test is internally inconsistent regardless of which option `LSMC-OD-14` selects. |

---

## 8. OWNER_DECISION_REQUIRED

Nothing in this table is decided. Each row blocks the item named in "Blocks". No row may be
closed by an agent; each needs an owner signature recorded in
`docs/governance/`, after which this spec is superseded by a new version.

| Ref | Decision required | Blocks | Interim (fail-closed) behaviour |
|---|---|---|---|
| `LSMC-OD-01` | Is `sweep_extreme` an authorized C10 anchor for the 1.1.0 watch path, or must the signed `invalidation_price` anchor be wired? | C10 validity on the live watch path | Record the anchor source on every stop; treat 1.1.0 stops as `ANCHOR_SUBSTITUTED`, not as C10-signed. |
| `LSMC-OD-02` | For symbols with no evidenced pip size (USDJPY, XAUUSD, BTCUSDT, ETHUSDT): publish the opportunity stopless, or suppress it? | 4 of 6 `V1_SYMBOLS` | Current code publishes stopless with `stop_reason`. No outcome requiring a stop may be resolved for them. |
| `LSMC-OD-03` | Is `stop_c10` immutable at first publication, or recomputed at each evaluation? | All stop-based outcomes | Treat the stop as immutable at first publication; persist it with the opportunity and never recompute. |
| `LSMC-OD-04` | Does C10-C (`REJECT`) stay permanently `NOT_APPLICABLE` on the watch path, or is a replay-safe broker-metadata seam required before Demo? | Demo readiness | Remains `NOT_APPLICABLE`; never a silent `PASS`, never `WIDEN`. |
| `LSMC-OD-05` | Is the 11:00-12:00 / 15:00-24:00 UTC fall-through to the NY 17:00 boundary intended, or should expiry use a fixed duration? | Every expiry outside a canonical session | Current formula stands; flag every opportunity resolved via the fall-through branch as `EXPIRY_UNCOVERED_HOURS`. |
| `LSMC-OD-06` | Is there a minimum opportunity lifetime? | Late-in-session triggers | None applied. Flag opportunities with lifetime < 1 trigger bar as `EXPIRY_DEGENERATE`. |
| `LSMC-OD-07` | Should crypto use a continuous-market expiry instead of FX session boxes and the NY boundary? | BTCUSDT, ETHUSDT | FX calendar applies; flag crypto expiries as `EXPIRY_CALENDAR_MISMATCH`. |
| `LSMC-OD-08` | Does POI expiry terminate an opportunity already derived from that POI? | Long-lived opportunities | Opportunity keeps its own clock; record both. |
| `LSMC-OD-09` | Adopt `WIN`/`LOSS`, or keep measurement-only names (`TARGET_REACHED`/`STOP_TOUCHED`)? | The entire outcome vocabulary | Keep `P7` measurement names. Do not emit `WIN`/`LOSS` until signed. |
| `LSMC-OD-10` | How are stopless symbols handled in WIN/LOSS aggregates? | Cross-symbol statistics | Report per-symbol only; never aggregate stopless and stopped symbols into one ratio. |
| `LSMC-OD-11` | Do `STOP_TOUCHED` and `INVALIDATED` stay distinct, or both map to `LOSS`? | Outcome cardinality | Keep distinct; persist both. |
| `LSMC-OD-12` | **Same-bar stop+target tie:** (a) conservative `LOSS`; (b) keep `AMBIGUOUS_SAME_BAR` as a terminal state excluded from statistics; (c) resolve sub-bar from M1 data; (d) resolve from bar direction. | All tie bars | (b). Record `AMBIGUOUS_SAME_BAR`, persist full OHLC, exclude from aggregates. |
| `LSMC-OD-13` | Reconcile side-correct exit prices with C10-B: SHORT stop on bid (no double-count) while SHORT target needs ask (7.3). | Every SHORT outcome | Resolve SHORT stops on **bid** (C10-B already contains the spread). Mark SHORT targets `UNRESOLVABLE` pending `LSMC-OD-14`. |
| `LSMC-OD-14` | How is the ask series obtained -- live spread, frozen per-symbol constant, exported MT5 spread column, or not at all? | All ask-side touches | Option (d): no reconstruction. SHORT targets are `UNRESOLVABLE`; SHORT opportunities are excluded from target statistics. |
| `LSMC-OD-15` | Is the invalidation close side-corrected, or left bid as detection already records it? | `INVALIDATED` outcomes | Left bid, matching merged detection code. |
| `LSMC-OD-16` | Is a bid-derived level tested against an ask-side touch acceptable, or must levels be re-derived on the matching side? | Internal consistency of 7.x | Not acceptable silently; blocked behind `LSMC-OD-14`. |
| `LSMC-OD-17` | Gap through a level: record the outcome at the level price, at the bar open, or `UNRESOLVABLE`? | Gap bars | Record the level, set `gap_flag = true`, persist the bar open, exclude from realized-price aggregates. |
| `LSMC-OD-18` | Missing bars vs a true market gap -- what staleness rule applies to outcome resolution? | Data outages | Resolution halts; the outcome stays open. Never advance to `EXPIRED` on absent data. |
| `LSMC-OD-19` | If `expires_at` falls inside the FX weekend close, is the outcome `EXPIRED` at the boundary or deferred to the reopen? | Friday-evening opportunities | `EXPIRED` at `expires_at`, flagged `EXPIRY_IN_MARKET_CLOSED`. |
| `LSMC-OD-20` | Is an opportunity with `target_c11 = None` (`REJECT_NO_TARGET`) resolvable at all? | Targetless opportunities | Not resolvable for `WIN`; may still resolve `STOP_TOUCHED`, `INVALIDATED` or `EXPIRED`. Recorded as `NO_TARGET`. |

---

## 9. Change control

1. This file is frozen at `spec_version 1.0.0`. Its SHA-256 is recorded in
   `docs/specs/LSMC_SPEC_V1_FROZEN.sha256.txt`.
2. A `FROZEN` rule may not be edited in place. Changing one requires a new signed owner
   decision and a new file (`LSMC_SPEC_V2_...`).
3. Closing an `OWNER_DECISION_REQUIRED` row requires an owner signature recorded under
   `docs/governance/`, then a new spec version. Agents may not close rows.
4. This spec grants no authority. `ST_LARGE_SMC_V1` stays `RESEARCH_DRAFT` / advisory-only.
5. Delivery and actionability remain governed solely by `LSMC_ACTIONABILITY_POLICY_V1`
   (section 0.2). Should a future revision need to reference it, reference it -- do not
   restate it.
