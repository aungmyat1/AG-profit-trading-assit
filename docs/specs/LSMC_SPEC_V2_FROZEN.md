# LSMC_SPEC_V2_FROZEN -- ST_LARGE_SMC_V1 strategy-logic freeze

| Field | Value |
|---|---|
| `spec_id` | `LSMC_SPEC_V2_FROZEN` |
| `spec_version` | **`2.0.0`** |
| `supersedes` | `docs/specs/LSMC_SPEC_V1_FROZEN.md` v1.0.2, SHA-256 `ffd003d116c5353521f4d31b900eae27f02dcb9e4e4923fd2d3e828f6413ba3e` (retained, marked SUPERSEDED, not deleted) |
| `strategy_id` | `ST_LARGE_SMC_V1` |
| `strategy_versions_covered` | `1.0.7` (`strategies/ST_LARGE_SMC_V1.yaml`) and `1.1.0` (`src/large_smc_watch/contract.py`) |
| `status` | `FROZEN` -- 31 rows closed, **1 BLOCKING open** (`LSMC-OD-32`) |
| `convergence` | **Last pre-verification version.** From this file's hash onward, only logical contradictions block R4A. See 9.4. |
| `authority` | Specification artifact. Confers no proposal, Demo, Live, execution or risk-sizing authority. |
| `owner_decisions_applied` | Batches 1-3 -- `docs/governance/OWNER_DECISIONS_2026-10-08_LSMC_SPEC_V1_0_2.md` |
| `frozen_utc` | 2026-10-08 |

**`FROZEN`** = closed and traceable to an owner-signed decision or merged code on `main`.
A `FROZEN` rule may not be edited in place; changing one requires a new major file (9.2).
**`OPEN`** = not decided; stated in 8.2 with a recommended default that is **not applied**.
**`BACKLOG`** = recorded in section 10, explicitly **non-blocking** for R4A.

> **One BLOCKING row stands: `LSMC-OD-32`.** Applying batch 3 required re-deriving the
> price scale of the C10 SHORT stop, and that derivation contradicts a justification this
> spec has carried since v1.0.0. The measurement rule is left exactly as signed; only the
> false justification is corrected. See 3.2, 7.1 and 8.2.

---

## 0. Scope

### 0.1 In scope -- strategy logic only

Stop construction; publication guards; opportunity expiry; outcome taxonomy; same-bar tie;
gap handling; price side.

### 0.2 Explicitly NOT in scope

`LSMC_ACTIONABILITY_POLICY_V1` (owner decisions D1-D8, 2026-10-07) governs **delivery and
actionability**. Those rules are **not restated, summarized, amended or re-derived here**.

> This spec governs what the *market* did to an opportunity's own levels.
> `LSMC_ACTIONABILITY_POLICY_V1` governs whether, when and how an opportunity is *told to
> the owner*.

An opportunity's outcome is resolved **independently of whether it was ever delivered**.

### 0.3 Authority and separations

`IMPLEMENTED != VALIDATED != AUTHORIZED`. This spec changes no code, no strategy YAML, no
threshold, no registry entry. `ST_LARGE_SMC_V1` stays `RESEARCH_DRAFT` / advisory-only with
`proposal_generation_authorized = False`. Nothing here is evidence of edge.

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
| `P9` | Price convention | MT5 native **BID-based** bar OHLC |
| `P10` | Bar type in use | `src/strategy_engine/session/candles.py` -- `Candle(time, open, high, low, close, volume)`. No spread field. |
| `P12` | Owner batch 1 | 2026-10-07 |
| `P13` | Owner batch 2 | 2026-10-08 |
| `P15` | **Owner batch 3** | **2026-10-08 -- `docs/governance/OWNER_DECISIONS_2026-10-08_LSMC_SPEC_V1_0_2.md` section "Batch 3"** |
| `P14` | Reachability fixture | `verification/AG_ARENA_RESET_A1_R1/fixtures/LSMC_INVALIDATED_REACHABLE_V1.json` |
| `P16` | **Publication-guard fixtures** | **`verification/AG_ARENA_RESET_A1_R1/fixtures/LSMC_PUBLICATION_GUARDS_V1.json`** |

### 1.1 Governance record used for the scope boundary

`docs/governance/OWNER_DECISIONS_2026-10-07_LSMC_ACTIONABILITY_V1.md`, canonical 94-line
record, SHA-256 `67bb1a57a7bc38335fdb18d7bdf7880c39331247a44abbc473e35cf1eecb7b56`
(`f4ec100`). Used **only** to fix what section 0.2 excludes.

---

## 2. The opportunity object

`FROZEN` -- from `P5`.

| Field | Meaning |
|---|---|
| `opp_id` | `{poi_id}` + sweep bar time + CHoCH bar time |
| `direction` | `LONG` or `SHORT`; equals the H1 `bias` at emission |
| `sweep_extreme` | sweep bar `low` (LONG) / `high` (SHORT) -- the structural invalidation level |
| `choch_time` | open time of the M5 CHoCH bar (trigger bar) |
| `choch_close` | `choch_time + 5 min` |
| `entry_reference` | CHoCH bar **close**. A reference price, never an order. |
| `target_c11` | nearest UNSWEPT opposing causal M5 swing strictly beyond `entry_reference`; `None` -> `REJECT_NO_TARGET` |
| `stop` | section 3.3; carries a `stop_basis` stamp |
| `expires_at` | section 4.1 |
| `invalidated_time` | first M5 **close** beyond `sweep_extreme` after the CHoCH bar |

`FROZEN`, load-bearing throughout:

- **Invalidation is a close, not a touch.**
- **Target and stop are touches, not closes.**
- All levels are **bid-derived** (`P5`) and **bid-resolved** (section 7).

---

## 3. Stop construction and publication guards

### 3.1 FROZEN -- the signed C10 formula

From `P1` / `P2` / `P3`, contract `C10_STRUCTURAL_INVALIDATION_V1`. **Unchanged by any
owner batch.**

```text
C10-A  buffer = max(1.5 pips, 0.35 x ATR14(M5))      DYNAMIC_ATR_WITH_HARD_FLOOR
       ATR14 = Wilder-smoothed, closed M5 candles only, no look-ahead
       ATR missing or < 15 closed M5 bars => FAIL_CLOSED (ATR_NOT_READY)

C10-B  LONG  : stop = anchor - buffer                 (no spread term)
       SHORT : stop = anchor + buffer + (ask - bid)   (verified live spread)
       Missing bid/ask for a SHORT => FAIL_CLOSED (MISSING_SPREAD)
       ask < bid                   => FAIL_CLOSED (INVALID_SPREAD)
       The spread appears EXACTLY ONCE, on the SHORT side only.

C10-C  broker minimum stop = REJECT. Never WIDEN.
       No broker context => NOT_APPLICABLE (never a silent PASS).

anchor : the structural invalidation price. EXACT_REUSE, never recomputed.
```

### 3.2 FROZEN -- the C10-B asymmetry, and the price scale of each stop

C10-B is **side-aware**: each stop is expressed on the side that actually triggers it.

```text
LONG  stop = anchor - buffer                  a BID-scale level
      a long's stop triggers when BID falls to it; the anchor is bid-derived,
      so the structural distance `buffer` is preserved directly.

SHORT stop = anchor + buffer + spread         an ASK-scale level
      a short's stop triggers when ASK rises to it. At that moment
      bid = anchor + buffer -- the same structural distance, mirrored.
      The spread term exists to preserve that symmetry, which is what `P3`
      means by "protects the Bid-derived structural anchor from Ask-side
      stop-trigger effects".
```

> **CORRECTION.** v1.0.0 section 7.3 -- carried forward into v1.0.1 and v1.0.2 -- asserted
> that `stop_c10` was "already on a BID-comparable scale in both directions" and that
> resolving the SHORT stop on ask "would double-count the spread". **That assertion was
> wrong.** The derivation above shows the SHORT stop is an ask-scale level, so measuring it
> against the **bid** requires the bid itself to reach `anchor + buffer + spread` -- one
> full spread wider than the designed stop, breaking LONG/SHORT symmetry.
>
> `LSMC-OD-13` ("short stop = bid (C10-B embeds spread)") rests on that wrong assertion.
> The rule is **left exactly as signed** in 7.1; the consequence is raised as the BLOCKING
> row `LSMC-OD-32` (8.2) and is **not resolved here**.

`test_short_spread_not_double_counted` (`P1`) guards the *construction* of the stop -- that
the formula adds the spread once. It says nothing about which side the level is compared
against, so it neither supports nor contradicts the above.

### 3.3 FROZEN (`P13` + `P15`, closes `LSMC-OD-01/21/22/28`) -- `STOP_BASIS`

```text
anchor = sweep_extreme                       (one anchor, both bases)

STOP_BASIS = STOP_C10                        EURUSD, GBPUSD  (C10_PIP_SIZE, P4)
  buffer = max(1.5 pips, 0.35 x ATR14(M5))
  LONG  : anchor - buffer
  SHORT : anchor + buffer + (ask - bid)

STOP_BASIS = SWEEP_EXTREME_ATR_BUFFER        USDJPY, XAUUSD, BTCUSDT, ETHUSDT
  buffer = max(0.35 x ATR14(M5), 1 x point)      <- 1-point floor, PROVISIONAL (OD-28)
  LONG  : anchor - buffer
  SHORT : anchor + buffer                        (no spread term)
```

The ATR term is in **price units**, so no pip or tick size is required -- which is what
unblocks the four symbols that never had an evidenced pip size. The 1-point floor uses
`point`, which `resolve_point` (`P4`) guarantees for every published opportunity: if
`point` is unresolvable the watch returns `DATA_ERROR` / `SYMBOL_METADATA_MISSING` and no
opportunity exists.

The 1-point floor is **non-binding for `STOP_C10`**: at 5-digit quoting, C10-A's own floor
of 1.5 pips equals 15 points, which always dominates 1 point. Stating it here keeps one
rule across both bases without altering C10-A.

`INVALIDATED` is reachable for all six symbols -- the reachability window width equals
`buffer`, now bounded below by 1 point (`SWEEP_EXTREME_ATR_BUFFER`) or 1.5 pips
(`STOP_C10`). Proof fixtures: `P14`, `P16`.

Stamps on every opportunity: `stop_basis`, `anchor_source = SWEEP_EXTREME`, `atr14_m5`,
`buffer`, `buffer_floor_applied`, `point`, `point_source`, and for `STOP_C10` shorts
`spread`.

### 3.4 FROZEN (`P13`, closes `LSMC-OD-03`) -- stop immutability

The stop is **immutable at first publication**, persisted with its inputs (ATR value,
spread, anchor, point) and never recomputed.

### 3.5 FROZEN (`P13`, closes `LSMC-OD-04`) -- C10-C status

`NOT_APPLICABLE` while advisory-only; a **blocking pre-Demo requirement**. Never a silent
`PASS`, never `WIDEN`.

### 3.6 FROZEN (`P15`, closes `LSMC-OD-27/28/31`) -- publication guards

An opportunity that fails a guard is **not published**. A guard result is a
**publication decision, not an outcome**: it never enters the section 5 taxonomy, and each
reason is **counted separately** from outcomes.

```text
GUARD 1  ATR14 warm-up
  The watch must supply >= 15 closed M5 bars before the CHoCH bar, so that
  ATR14(M5) over m5[: choch_index + 1] is computable.
  Not satisfied            -> SKIPPED_ATR_NOT_READY (sub-reason INSUFFICIENT_WARMUP)

GUARD 2  ATR14 validity
  ATR14 <= 0               -> SKIPPED_ATR_NOT_READY (sub-reason NON_POSITIVE_ATR)
  This is stricter than c10_stop_policy, which raises only on atr < 0.

GUARD 3  Pre-closure
  Let `tradable_m5_remaining` = the count of M5 bars between choch_close and the
  next scheduled closure, counting only bars the market is open.
  tradable_m5_remaining < 6  -> SKIPPED_PRE_CLOSURE

  Scheduled closure, FX     : the weekly close, Friday 17:00 America/New_York
                              (watch.fx_market_closed, the only closure modelled).
  Scheduled closure, crypto : broker maintenance closures only. No maintenance
                              calendar exists in this repository, so for BTCUSDT and
                              ETHUSDT this guard currently never fires -- see BACKLOG
                              B2, which records that it therefore fails OPEN.
```

**Boundary convention for Guard 3:** the test is `< 6`, not `<= 6`, so exactly 6 remaining
tradable bars publishes. This is the reading that makes the `LSMC-OD-06` floor exactly
satisfiable in tradable bars, which is the guard's stated purpose. Recorded as BACKLOG B7
in case the owner intended the inclusive boundary.

### 3.7 OPEN

`LSMC-OD-32` -- BLOCKING. See 8.2.

---

## 4. Opportunity expiry

### 4.1 FROZEN (`P13`, closes `LSMC-OD-05/06/07`) -- the computed expiry

```text
choch_close = choch_time + 5 min ;  M5BAR = 5 min

FX (EURUSD, GBPUSD, USDJPY, XAUUSD):
  raw        = session_end(choch_close)
  capped     = min(raw, choch_close + 24 x M5BAR)       # LSMC-OD-05  PROVISIONAL
  expires_at = max(capped, choch_close + 6 x M5BAR)     # LSMC-OD-06  PROVISIONAL

Crypto (BTCUSDT, ETHUSDT):                              # LSMC-OD-07
  expires_at = choch_close + 24 x M5BAR
  No session boxes. No New York 17:00 boundary.

session_end(t):
  m = UTC hour*60 + minute of t
  for each canonical session [start, end):  if start <= m < end: return UTC-midnight(t) + end
  otherwise: return next 17:00 America/New_York

canonical sessions (UTC, half-open, fixed clock):
  asian 00:00-06:00 | london_am 06:00-11:00 | new_york_am 12:00-15:00
```

**Order of application is normative:** cap first, then floor. The floor **overrides the
session boundary** -- a CHoCH closing at 05:58 UTC expires at 06:33, not 06:00.

**Both constants are `PROVISIONAL`** (24 and 6 M5 bars): owner-signed working values, not
evidenced parameters.

Guard 3 (3.6) and the floor are complementary: the floor guarantees a minimum life in
wall-clock bars *within* a trading period, and Guard 3 prevents that life from being
consumed by a scheduled closure.

`FROZEN` properties: expiry is anchored to `choch_close`; boundaries are **half-open**
(`now >= expires_at` is expired); expiry is **terminal and non-reversible**; expiry and
invalidation are independent clocks.

### 4.2 FROZEN -- separate POI expiry

A POI expires after `POI_MAX_AGE_TRADING_DAYS = 5` trading days (`P4`). It governs whether
a *new* opportunity may form.

### 4.3 FROZEN (`P13`, closes `LSMC-OD-08`) -- POI expiry does not terminate an opportunity

Once the CHoCH has fired the structural event is complete. The opportunity keeps its own
clock; both IDs are recorded.

---

## 5. Outcome taxonomy

### 5.1 FROZEN (`P12`, closes `LSMC-OD-09`) -- the names

Outcomes are **structural facts, not trade results**. `WIN` / `LOSS` are **rejected** and
must not appear in any LSMC field, message or report.

| Outcome | Meaning |
|---|---|
| `TARGET_REACHED` | `target_c11` touched |
| `STOP_REACHED` | the `stop_basis` stop level touched |
| `INVALIDATED` | M5 **close** beyond `sweep_extreme` |
| `EXPIRED` | `expires_at` passed with none of the above |
| `AMBIGUOUS_SAME_BAR` | a target and a stop/invalidation event on one bar (6.1) |

Distinct from outcomes, and never mixed into them: the **publication reasons**
`SKIPPED_ATR_NOT_READY` and `SKIPPED_PRE_CLOSURE` (3.6), each counted separately.

No fill, slippage, cost or sizing is modelled. **Not evidence of edge.**

### 5.2 FROZEN -- terminal-state structure

Exactly **one** terminal outcome per opportunity; first qualifying event wins; bars scanned
forward from `choch_close`, **closed bars only**; never resolved past `expires_at`; until a
terminal event occurs the outcome is `None` (open), never a default; resolution is pure
measurement and never feeds back into detection or construction.

### 5.3 FROZEN -- the terminal events and their precedence

```text
AMBIGUOUS_SAME_BAR  if target_hit and (stopped or invalidated)
TARGET_REACHED      elif target_hit
STOP_REACHED        elif stopped
INVALIDATED         elif invalidated
OPEN                otherwise
```

| Event | Condition (all on **bid**, section 7) |
|---|---|
| `TARGET_REACHED` | `high >= target_c11` (LONG) / `low <= target_c11` (SHORT) -- touch |
| `STOP_REACHED` | `low <= stop` (LONG) / `high >= stop` (SHORT) -- touch |
| `INVALIDATED` | `close < sweep_extreme` (LONG) / `close > sweep_extreme` (SHORT) |
| `EXPIRED` | `expires_at` passed, nothing above fired |

### 5.4 FROZEN (`P13`, closes `LSMC-OD-11`) -- `STOP_REACHED` and `INVALIDATED` stay distinct

Different structural facts: a touch of the risk level versus a close beyond the thesis
level. An optional derived rollup `ADVERSE = STOP_REACHED ∪ INVALIDATED` may be reported,
but never replaces the two underlying counts.

### 5.5 FROZEN (`P13`, closes `LSMC-OD-20`) -- targetless opportunities

`target_c11 = None` (`REJECT_NO_TARGET`) is resolvable for `STOP_REACHED` / `INVALIDATED` /
`EXPIRED` only, excluded from any target-hit-rate denominator, counted separately as
`NO_TARGET`.

### 5.6 FROZEN (`P12` + `P13` + `P15`, closes `LSMC-OD-10/22/29`) -- reporting

```text
Every LSMC statistic is reported separately for LONG and SHORT. Never pooled.
Every statistic is additionally stratified by stop_basis.
Counted separately and never folded into any ratio:
  AMBIGUOUS_SAME_BAR, NO_TARGET, SKIPPED_ATR_NOT_READY, SKIPPED_PRE_CLOSURE.
```

The two bases now share the same anchor and the same `0.35 x ATR14` term, differing only
by the floor magnitude (1.5 pips vs 1 point) and the SHORT spread term. Unifying them is
**DEFERRED to V3, after R4B** (`P15`); recorded as BACKLOG B1.

---

## 6. Same-bar tie, and gap handling

### 6.1 FROZEN (`P13`, closes `LSMC-OD-12/26`) -- same-bar tie

```text
A bar containing both a target event and a stop/invalidation event resolves to
AMBIGUOUS_SAME_BAR. It is NOT resolved further in V2.
  - persist both competing levels and the full bar OHLC
  - EXCLUDE from every outcome ratio
  - COUNT SEPARATELY and report the count alongside every ratio
  - stamp m1_available = false
```

M1 resolution is **deferred to v1.1 of the measurement lane**; the LSMC pipeline carries
`TIMEFRAME_MINUTES = {D1, H1, M5}` only (`P4`). A winner is never imputed, and
`AMBIGUOUS_SAME_BAR` is never folded into another outcome for "conservatism".

### 6.2 FROZEN (`P12`, closes `LSMC-OD-17`) -- gap through a level

When the bar triggering a terminal event **opens beyond** the level it triggered, the
outcome is recorded **at the gap open price**, stamped `GAP_THROUGH = true`. Both the level
price and the bar open are persisted. A gap carrying price beyond **both** stop and target
is a same-bar tie and 6.1 applies.

### 6.3 FROZEN (`P13`, closes `LSMC-OD-18`) -- data outage vs market gap

```text
Gap spanning an OPEN market      -> DATA_GAP.   Resolution HALTS; outcome stays open.
                                    Never advanced to EXPIRED on absent data.
Gap spanning a SCHEDULED CLOSURE -> MARKET_GAP. Resolves at the reopen bar's open,
                                    stamped GAP_THROUGH.
```

### 6.4 FROZEN (`P13`, closes `LSMC-OD-19`) -- expiry inside a scheduled closure

`EXPIRED` at `expires_at`, flagged `EXPIRY_IN_MARKET_CLOSED`. Guard 3 (3.6) now prevents
most such cases at publication time.

---

## 7. Price side

### 7.1 FROZEN (`P13` + `P15`, closes `LSMC-OD-13/14/15/16/23/24/25/29`) -- bid resolution

```text
V2 resolves ALL levels on BID. There is no ask series and no ask reconstruction.

  LONG  target   bid touch
  LONG  stop     bid touch
  SHORT target   bid touch   -> flag SIDE_APPROX_BID
  SHORT stop     bid touch   -> flag SIDE_APPROX_BID
  invalidation   bid close   -> stamp invalidation_basis = BID
  SHORT AMBIGUOUS_SAME_BAR inherits SIDE_APPROX_BID from its constituent events.

All statistics are reported separately for LONG and SHORT (5.6).
No typical-spread constants exist in V2.
v1.1 of the measurement lane will adopt empirical per-symbol spreads from
host-recorded samples.
```

`INVALIDATED` carries **no** `SIDE_APPROX_BID` flag, and this is deliberate: invalidation
is a bid close tested against a bid-derived level, computed by merged detection code
(`detect.m5_opportunities`). It is bid by definition, not bid by approximation.

> **Known bias, not resolved here.** `SIDE_APPROX_BID` marks two errors that point in
> **opposite directions**. A real short exits at the ask, so a bid touch of the *target* is
> reached **early** (optimistic). A real short stop triggers on the ask, so a bid touch of
> the *stop* is reached **late** (conservative). Additionally, for `STOP_C10` shorts the
> stop is an ask-scale level (3.2), so bid measurement widens it by a further full spread.
> The first point is BACKLOG B3; the second is the BLOCKING row `LSMC-OD-32`.

### 7.2 FROZEN (`P13`, closes `LSMC-OD-15`) -- invalidation side

Invalidation stays on **bid**, matching merged detection code. One definition, owned by
detection; the resolver never disagrees with detection about whether an opportunity is
alive.

---

## 8. Owner decisions

### 8.1 Closed (31 rows)

| Ref | Ruling | Batch | Section |
|---|---|---|---|
| `LSMC-OD-01` | `sweep_extreme` is the anchor for both bases | `P13` | 3.3 |
| `LSMC-OD-02` | REPLACED by `LSMC-OD-21/22` | `P12`->`P13` | 3.3 |
| `LSMC-OD-03` | Stop immutable at first publication | `P13` | 3.4 |
| `LSMC-OD-04` | C10-C `NOT_APPLICABLE` now, blocking pre-Demo | `P13` | 3.5 |
| `LSMC-OD-05` | Cap `choch_close + 24 M5` -- PROVISIONAL | `P13` | 4.1 |
| `LSMC-OD-06` | Floor `choch_close + 6 M5` -- PROVISIONAL | `P13` | 4.1 |
| `LSMC-OD-07` | Crypto: duration cap only | `P13` | 4.1 |
| `LSMC-OD-08` | POI expiry does not terminate an opportunity | `P13` | 4.3 |
| `LSMC-OD-09` | `TARGET_REACHED`/`STOP_REACHED`; `WIN`/`LOSS` rejected | `P12` | 5.1 |
| `LSMC-OD-10` | Aggregates stratified by `stop_basis` | `P12` | 5.6 |
| `LSMC-OD-11` | `STOP_REACHED` and `INVALIDATED` stay distinct | `P13` | 5.4 |
| `LSMC-OD-12` | `AMBIGUOUS_SAME_BAR`, counted separately | `P12` | 6.1 |
| `LSMC-OD-13` | All levels on bid | `P12`->`P13` | 7.1 |
| `LSMC-OD-14` | REVISED -- no ask reconstruction | `P12`->`P13` | 7.1 |
| `LSMC-OD-15` | Invalidation stays bid | `P13` | 7.2 |
| `LSMC-OD-16` | Accepted under the bid + `SIDE_APPROX_BID` rule | `P13` | 7.1 |
| `LSMC-OD-17` | Gap through a level records the gap open price | `P12` | 6.2 |
| `LSMC-OD-18` | `DATA_GAP` halts; `MARKET_GAP` resolves at reopen | `P13` | 6.3 |
| `LSMC-OD-19` | `EXPIRED` at `expires_at`, flagged | `P13` | 6.4 |
| `LSMC-OD-20` | Targetless: never `TARGET_REACHED`, counted `NO_TARGET` | `P13` | 5.5 |
| `LSMC-OD-21` | `SWEEP_EXTREME_ATR_BUFFER`; `INVALIDATED` reachable | `P13` | 3.3, `P14` |
| `LSMC-OD-22` | Same ruling as 21 | `P13` | 3.3 |
| `LSMC-OD-23` | All levels on bid; no `Candle` spread dependency | `P13` | 7.1 |
| `LSMC-OD-24` | No ask path, so no approximation class to flag | `P13` | 7.1 |
| `LSMC-OD-25` | No typical-spread constants; empirical spreads later | `P13` | 7.1 |
| `LSMC-OD-26` | M1 deferred; tie stays unresolved | `P13` | 6.1 |
| `LSMC-OD-27` | ATR14 warm-up guard -> `SKIPPED_ATR_NOT_READY` | **`P15`** | 3.6 |
| `LSMC-OD-28` | `buffer = max(0.35 x ATR14, 1 x point)`; `ATR14 <= 0` -> skip | **`P15`** | 3.3, 3.6 |
| `LSMC-OD-29` | `SIDE_APPROX_BID` on SHORT target and stop; LONG/SHORT reported separately | **`P15`** | 5.6, 7.1 |
| `LSMC-OD-30` | New major file V2; V1 marked SUPERSEDED | **`P15`** | 9.2, this file |
| `LSMC-OD-31` | `SKIPPED_PRE_CLOSURE` guard | **`P15`** | 3.6 |

### 8.2 BLOCKING -- 1 open row

Classified **BLOCKING** under the convergence rule (9.4) as a **self-contradiction**. Not
resolved; the signed measurement rule in 7.1 is unchanged.

| Ref | Contradiction | Options (owner to choose) |
|---|---|---|
| **`LSMC-OD-32`** | **The C10 SHORT stop is an ask-scale level, so bid-measuring it is one spread too wide.** `stop_c10_short = anchor + buffer + spread` is built so that when the **ask** reaches it, the bid sits at `anchor + buffer` -- symmetric with the LONG stop. Measuring it against the **bid** requires the bid to reach `anchor + buffer + spread`, a full spread beyond the designed distance. Worked example (`P3` values): `anchor 1.10000`, `buffer 0.00020`, `spread 0.00010` -> LONG stop `1.09980` triggers at `buffer` from the anchor; SHORT stop `1.10030` triggers at `buffer` from the anchor on **ask**, but at `buffer + spread` on **bid**. **Consequence:** SHORT `STOP_REACHED` is systematically under-reported for `STOP_C10` symbols, and LONG/SHORT stop geometry is not equivalent. **This also means v1.0.0 section 7.3 was wrong** -- it claimed an ask comparison would "double-count" the spread -- and `LSMC-OD-13` was decided on that wrong premise. `SWEEP_EXTREME_ATR_BUFFER` is unaffected: it has no spread term, so its SHORT stop is already a bid-scale level. | **(a)** Keep bid measurement, accept the bias as known and flagged (`SIDE_APPROX_BID` + separate LONG/SHORT reporting already in force). Zero rule change; the one-spread widening stays in the numbers. **(b)** Compare the `STOP_C10` SHORT stop against `stop_c10 - spread` (its bid-equivalent), restoring LONG/SHORT symmetry without touching C10 or introducing an ask series. Requires the construction-time `spread`, which 3.4 already persists. **(c)** Reinstate an ask series for `STOP_C10` shorts only -- rejected in batch 3 as `LSMC-OD-23/24/25`; listed for completeness. |

**Why BLOCKING rather than BACKLOG.** The convergence rule reserves blocking status for
unreachable states, self-contradictions and unevaluable rules. This is a self-contradiction
between two `FROZEN` statements -- 3.1's side-aware construction and the (now corrected)
bid-comparability claim that justified 7.1 -- and it changes the meaning of a core measured
quantity, `STOP_REACHED`, for half the direction space on the two symbols with the most
history. Option (a) closes it with no rule change, so the fix may be a single ruling.

---

## 9. Change control

1. Frozen at `spec_version 2.0.0`; SHA-256 in `docs/specs/LSMC_SPEC_V2_FROZEN.sha256.txt`.
2. **`OPEN` rows may be closed in-file**, at a new minor version, provided the superseded
   text is retained and the changelog names it. **Any change to a `FROZEN` rule requires a
   new major file** (`LSMC_SPEC_V3_...`); it may never be edited in place. (`LSMC-OD-30`.)
3. Closing an `OPEN` row requires an owner signature. Agents may not close rows, and may
   not apply a recommended default or a listed option without a signature.
4. **CONVERGENCE RULE.** V2 is the **last pre-verification version**. From this file's
   SHA-256 onward, only **logical contradictions** block R4A:
   - an **unreachable state** (a defined outcome or state that no input can produce),
   - a **self-contradiction** (two rules that cannot both hold),
   - an **unevaluable rule** (a rule that cannot be computed from available inputs).

   Everything else -- missing evidence, unevidenced constants, comparability concerns,
   naming, ergonomics, deferred scope -- goes to section 10 `V2.1_BACKLOG` and is
   **non-blocking**.
5. `PROVISIONAL` constants (`LSMC-OD-05` cap, `LSMC-OD-06` floor, `LSMC-OD-28` 1-point
   floor) may be revised by the owner without a new major file.
6. This spec grants no authority. `ST_LARGE_SMC_V1` stays `RESEARCH_DRAFT` / advisory-only.
7. Delivery and actionability remain governed solely by `LSMC_ACTIONABILITY_POLICY_V1`
   (section 0.2). Reference it; do not restate it.

---

## 10. V2.1_BACKLOG

Non-blocking for R4A per 9.4. Recorded so none of it is rediscovered as a surprise.

| Ref | Item | Why non-blocking |
|---|---|---|
| **B1** | **`STOP_BASIS` unification -- DEFERRED to V3, after R4B** (`P15`). The two bases now differ only by floor magnitude (1.5 pips vs 1 point) and the SHORT spread term. | Owner-directed deferral. Both bases are fully specified and evaluable today. |
| **B2** | **Closure calendar is incomplete.** The only modelled closure is the FX weekly close (Friday 17:00 NY). No broker maintenance window exists anywhere in the repository for BTCUSDT/ETHUSDT, and no daily rollover closure is modelled for FX. Guard 3 therefore **fails open** for those cases: an opportunity may publish inside an unmodelled closure. | Guard 3 is evaluable -- an empty closure set simply never fires. The failure mode mis-measures an outcome; it cannot cause a trade (no execution authority). |
| **B3** | **`SIDE_APPROX_BID` conflates two opposite error directions.** Short target on bid fires **early** (optimistic); short stop on bid fires **late** (conservative). One flag name covers both. Consider `SIDE_APPROX_BID_EARLY` / `_LATE`. | A labelling refinement. Both events are flagged and LONG/SHORT are reported separately, so the bias is visible. |
| **B4** | **The 1-point floor inherits `point` provenance.** `resolve_point` returns `REPO_EVIDENCED`, `HOST_CAPTURED` or `CALLER_SUPPLIED`; USDJPY and XAUUSD have no repo-evidenced point, so their stop geometry depends on a host capture or a fixture value. | Fully evaluable, and `point_source` is stamped on every opportunity (3.3). Affects interpretation, not computability. |
| **B5** | **ATR14 warm-up truncates replay windows.** Guard 1 drops any CHoCH with fewer than 15 preceding M5 bars, so `SKIPPED_ATR_NOT_READY` counts are structurally higher in a replay (window start) than in live operation (continuous history). | Counted separately by design, so the effect is measurable rather than hidden. |
| **B6** | **`PROVISIONAL` constants remain unevidenced:** 24-bar cap, 6-bar floor, 1-point buffer floor. | Owner-signed working values, revisable under 9.5 without a new major file. |
| **B7** | **Guard 3 boundary convention.** This spec reads "within 6 tradable M5 bars" as `remaining < 6`, so exactly 6 publishes, making the `LSMC-OD-06` floor exactly satisfiable. If the inclusive reading was intended, flip to `<= 6`. | A one-symbol change with no structural consequence; the convention is stated explicitly in 3.6. |

---

## 11. Changelog

### 2.0.0 -- 2026-10-08

New major file, created per `LSMC-OD-30` to comply with section 9.2.
Supersedes `docs/specs/LSMC_SPEC_V1_FROZEN.md` v1.0.2
(`ffd003d116c5353521f4d31b900eae27f02dcb9e4e4923fd2d3e828f6413ba3e`), which is retained and
marked SUPERSEDED.

| # | Change | Section |
|---|---|---|
| 1 | `LSMC-OD-27` closed. Guard 1: >= 15 closed M5 bars before the CHoCH bar, else `SKIPPED_ATR_NOT_READY` (`INSUFFICIENT_WARMUP`), counted separately. | 3.6 |
| 2 | `LSMC-OD-28` closed. `SWEEP_EXTREME_ATR_BUFFER` buffer becomes `max(0.35 x ATR14, 1 x point)`, 1-point floor PROVISIONAL. Guard 2: `ATR14 <= 0` -> `SKIPPED_ATR_NOT_READY` (`NON_POSITIVE_ATR`), stricter than `c10_stop_policy`. Floor noted non-binding for `STOP_C10` (1.5 pips = 15 points). | 3.3, 3.6 |
| 3 | `LSMC-OD-29` closed. `SIDE_APPROX_BID` extended to SHORT `STOP_REACHED` as well as SHORT `TARGET_REACHED`; `INVALIDATED` deliberately excluded (bid by definition). All statistics reported separately for LONG and SHORT. | 5.6, 7.1 |
| 4 | `LSMC-OD-30` closed. This new major file created; V1 marked SUPERSEDED, not deleted. Section 9.2 rewritten: OPEN rows may close in-file, any FROZEN change requires a new major file. | 9.2 |
| 5 | `LSMC-OD-31` closed. Guard 3: `tradable_m5_remaining < 6` before a scheduled closure -> `SKIPPED_PRE_CLOSURE`. Crypto limited to broker maintenance closures. Boundary convention stated. | 3.6 |
| 6 | **CONVERGENCE RULE added.** V2 is the last pre-verification version; only unreachable states, self-contradictions and unevaluable rules block R4A. | 9.4 |
| 7 | **`V2.1_BACKLOG` section added** with 7 non-blocking items, including the owner-directed `STOP_BASIS` unification deferral to V3. | 10 |
| 8 | **`LSMC-OD-32` raised, BLOCKING, not resolved.** The C10 SHORT stop is an ask-scale level; bid-measuring it is one spread too wide. v1.0.0 section 7.3's "double-count" claim is **corrected** -- it was wrong, and `LSMC-OD-13` rests on it. Three options put to the owner; the signed bid rule is unchanged. | 3.2, 7.1, 8.2 |
| 9 | Publication reasons (`SKIPPED_*`) defined as a vocabulary distinct from outcomes, never mixed into the section 5 taxonomy. | 3.6, 5.1 |
| 10 | Pins `P15` (owner batch 3) and `P16` (publication-guard fixtures) added. | 1 |

### Inherited history

`LSMC_SPEC_V1_FROZEN.md` v1.0.0 (`94dd0fb9…9a7e`), v1.0.1 (`900593d9…23a7`), v1.0.2
(`ffd003d1…ba3e`). Full changelog retained in that file.
