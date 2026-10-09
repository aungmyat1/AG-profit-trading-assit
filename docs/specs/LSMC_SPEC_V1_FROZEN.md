> # ⛔ SUPERSEDED -- DO NOT USE AS AUTHORITY
>
> **Superseded by [`docs/specs/LSMC_SPEC_V2_FROZEN.md`](LSMC_SPEC_V2_FROZEN.md) v2.0.0**
> on 2026-10-08, per owner decision `LSMC-OD-30`
> (`docs/governance/OWNER_DECISIONS_2026-10-08_LSMC_SPEC_V1_0_2.md`, Batch 3).
> Retained unaltered for history; **not deleted**.
>
> **Signed content hash.** This file was signed by the owner at v1.0.2 with SHA-256
> `ffd003d116c5353521f4d31b900eae27f02dcb9e4e4923fd2d3e828f6413ba3e`. This banner is the
> only change made since, so the file's current hash necessarily differs. The exact signed
> v1.0.2 content is recoverable at git commit `b2f0ca7`:
> `git show b2f0ca7:docs/specs/LSMC_SPEC_V1_FROZEN.md | sha256sum`.
>
> **Known correction.** Section 7.3 of v1.0.0, carried into this file at 3.2 and 7.1,
> claimed `stop_c10` is "BID-comparable in both directions" and that resolving the SHORT
> stop on ask would "double-count" the spread. **That claim is wrong** -- the C10 SHORT
> stop is an ask-scale level. See `LSMC_SPEC_V2_FROZEN.md` 3.2 and the BLOCKING row
> `LSMC-OD-32`.
>
> Change control for this lane now lives in `LSMC_SPEC_V2_FROZEN.md` section 9:
> `OPEN` rows may close in-file; any `FROZEN` change requires a new major file.

# LSMC_SPEC_V1_FROZEN -- ST_LARGE_SMC_V1 strategy-logic freeze (SUPERSEDED)

| Field | Value |
|---|---|
| `spec_id` | `LSMC_SPEC_V1_FROZEN` |
| `spec_version` | **`1.0.2`** |
| `supersedes` | `1.0.1`, SHA-256 `900593d9420d9860907ca8c8460fcd970cd6b25de624d37a977aca7f0ab323a7` |
| `strategy_id` | `ST_LARGE_SMC_V1` |
| `strategy_versions_covered` | `1.0.7` (`strategies/ST_LARGE_SMC_V1.yaml`) and `1.1.0` (`src/large_smc_watch/contract.py`) |
| `status` | `FROZEN_WITH_OPEN_DECISIONS` -- 26 rows closed, **5 open** (`LSMC-OD-27`..`31`) |
| `authority` | Specification artifact. Confers no proposal, Demo, Live, execution or risk-sizing authority. |
| `owner_decisions_applied` | 2026-10-07 batch (`docs/specs` provenance capture) and **2026-10-08 batch** (`docs/governance/OWNER_DECISIONS_2026-10-08_LSMC_SPEC_V1_0_2.md`) |
| `frozen_utc` | 2026-10-08 |

**`FROZEN`** = closed and traceable to an owner-signed decision or merged code on `main`.
**`AMENDED`** = a rule v1.0.1 marked `FROZEN` that the 2026-10-08 owner batch explicitly
replaced or revised; the superseded text is retained inline so nothing is lost.
**`OPEN`** = not decided; stated as a question in section 8.2 with a recommended default
that is **not applied** and carries no authority until signed.

> The procedural conflict created by amending `FROZEN` rules in place, rather than opening
> a new `LSMC_SPEC_V2_...` file as section 9.2 requires, is raised as **`LSMC-OD-30`** and
> is deliberately **not resolved** here.

---

## 0. Scope

### 0.1 In scope -- strategy logic only

C10 stop rule; opportunity expiry; outcome taxonomy; same-bar tie; gap handling;
side-correct prices.

### 0.2 Explicitly NOT in scope

`LSMC_ACTIONABILITY_POLICY_V1` (owner decisions D1-D8, 2026-10-07) governs **delivery and
actionability**. Those rules are **not restated, summarized, amended or re-derived here**.

> This spec governs what the *market* did to an opportunity's own levels.
> `LSMC_ACTIONABILITY_POLICY_V1` governs whether, when and how an opportunity is *told to
> the owner*.

An opportunity's outcome is resolved **independently of whether it was ever delivered**.
The two vocabularies are disjoint and must never be merged into one field.

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
| `P10` | Bar type in use | `src/strategy_engine/session/candles.py` -- `Candle(time, open, high, low, close, volume)`. **No spread field.** |
| `P12` | Owner batch 1 | 2026-10-07 -- `verification/AG_ARENA_RESET_A1_R1/OWNER_DECISIONS_2026-10-07_LSMC_SPEC_V1_01.md` |
| `P13` | **Owner batch 2** | **2026-10-08 -- `docs/governance/OWNER_DECISIONS_2026-10-08_LSMC_SPEC_V1_0_2.md`** |
| `P14` | Reachability fixture | `verification/AG_ARENA_RESET_A1_R1/fixtures/LSMC_INVALIDATED_REACHABLE_V1.json` |

Pins `P8` (PR #49 provisional side convention) and `P11` (spread-constant precedent) are
**retired** -- `P13` withdrew ask reconstruction and typical-spread constants from V1.

### 1.1 Governance record used for the scope boundary

`docs/governance/OWNER_DECISIONS_2026-10-07_LSMC_ACTIONABILITY_V1.md`, canonical 94-line
record, SHA-256 `67bb1a57a7bc38335fdb18d7bdf7880c39331247a44abbc473e35cf1eecb7b56`
(`f4ec100`). Used **only** to fix what section 0.2 excludes.

---

## 2. The opportunity object (frozen reference)

`FROZEN` -- from `P5`.

| Field | Meaning |
|---|---|
| `opp_id` | `{poi_id}` + sweep bar time + CHoCH bar time |
| `direction` | `LONG` or `SHORT`; equals the H1 `bias` at emission |
| `sweep_extreme` | sweep bar `low` (LONG) / `high` (SHORT) -- the structural invalidation level |
| `choch_time` | open time of the M5 CHoCH bar (trigger bar) |
| `choch_close` | `choch_time + 5 min` -- the trigger bar's close |
| `entry_reference` | CHoCH bar **close**. A reference price, never an order. |
| `target_c11` | nearest UNSWEPT opposing causal M5 swing strictly beyond `entry_reference`; `None` -> `REJECT_NO_TARGET` |
| `stop` | section 3.3; carries a `STOP_BASIS` stamp |
| `expires_at` | section 4.1 |
| `invalidated_time` | first M5 **close** beyond `sweep_extreme` after the CHoCH bar |

`FROZEN`, load-bearing throughout:

- **Invalidation is a close, not a touch.**
- **Target and stop are touches, not closes.**
- All levels are **bid-derived** and, from v1.0.2, **bid-resolved** (section 7).

---

## 3. Stop construction

### 3.1 FROZEN -- the signed C10 formula

From `P1` / `P2` / `P3`, contract `C10_STRUCTURAL_INVALIDATION_V1`. **Unchanged by any
owner batch.**

```text
C10-A  buffer = max(1.5 pips, 0.35 x ATR14(M5))      DYNAMIC_ATR_WITH_HARD_FLOOR
       ATR14 = Wilder-smoothed, closed M5 candles only, no look-ahead
       ATR missing or < 15 closed M5 bars => FAIL_CLOSED (ATR_NOT_READY)
       The 1.5-pip floor is NEVER used alone as a silent fallback.

C10-B  LONG  : stop = anchor - buffer                 (no spread term)
       SHORT : stop = anchor + buffer + (ask - bid)   (verified live spread)
       Missing bid/ask for a SHORT => FAIL_CLOSED (MISSING_SPREAD)
       ask < bid                   => FAIL_CLOSED (INVALID_SPREAD)
       The spread appears EXACTLY ONCE, on the SHORT side only.

C10-C  broker minimum stop = REJECT. Never WIDEN.
       No broker context => NOT_APPLICABLE (never a silent PASS).

anchor : the structural invalidation price. EXACT_REUSE, never recomputed.
         Missing => FAIL_CLOSED (MISSING_STRUCTURAL_ANCHOR).
```

Reason codes `FROZEN`: `INVALID_DIRECTION`, `MISSING_STRUCTURAL_ANCHOR`,
`MISSING_ATR_DATA`, `ATR_NOT_READY`, `INVALID_ATR`, `MISSING_SPREAD`, `INVALID_SPREAD`,
`MISSING_ENTRY_FOR_MIN_STOP_CHECK`, `MIN_STOP_VIOLATION`.

### 3.2 FROZEN -- the C10-B asymmetry is intentional

`P3`: the LONG side omits the spread because the anchor is "already Bid-side-consistent
with a LONG's own SELL-stop trigger convention ... adding spread here would double-count
what the SHORT side accounts for once." Guarded by `test_short_spread_not_double_counted`.

`stop_c10` is therefore already on a **BID-comparable** scale in both directions -- which
is why section 7 can resolve every level on bid without touching C10.

### 3.3 AMENDED (`P13`, closes `LSMC-OD-01/21/22`; **replaces** the `LSMC-OD-02` ruling) -- `STOP_BASIS`

```text
anchor = sweep_extreme                      (LSMC-OD-01 accepted: one anchor, both bases)

STOP_BASIS = STOP_C10                       EURUSD, GBPUSD  (C10_PIP_SIZE, P4)
  LONG  : anchor - max(1.5 pips, 0.35 x ATR14(M5))
  SHORT : anchor + max(1.5 pips, 0.35 x ATR14(M5)) + (ask - bid)

STOP_BASIS = SWEEP_EXTREME_ATR_BUFFER       USDJPY, XAUUSD, BTCUSDT, ETHUSDT
  LONG  : anchor - 0.35 x ATR14(M5)
  SHORT : anchor + 0.35 x ATR14(M5)
  pip floor NOT applied; no spread term.
```

> **Superseded text (v1.0.1, `LSMC-OD-02` ruling):** `STOP_BASIS = SWEEP_EXTREME`, the stop
> placed exactly at `sweep_extreme` with no buffer.

The ATR term is already in **price units**, so no pip or tick size is required -- which is
precisely what unblocks the four symbols that never had an evidenced pip size.

**`INVALIDATED` is now reachable for all six symbols.** Proof fixture `P14`: a LONG bar
`O 150.020 / H 150.030 / L 149.990 / C 149.995` against `sweep_extreme 150.000`,
`ATR14 0.040`, `buffer 0.014`, `stop 149.986` resolves `INVALIDATED` -- and resolved
`STOP_REACHED` under the replaced basis. Mirrored SHORT case included, plus controls
showing `STOP_REACHED` and `AMBIGUOUS_SAME_BAR` remain reachable.

Stamps carried on every opportunity: `stop_basis`, `anchor_source = SWEEP_EXTREME`,
`atr14_m5`, `buffer`, and (for `STOP_C10` shorts) `spread`.

### 3.4 FROZEN (`P13`, closes `LSMC-OD-03`) -- stop immutability

The stop is **immutable at first publication**. It is persisted with its inputs (ATR value,
spread, anchor) and never recomputed. A recomputed SHORT `STOP_C10` stop would drift with
the live spread, so the same opportunity could resolve `STOP_REACHED` or not purely by
evaluation timing.

### 3.5 FROZEN (`P13`, closes `LSMC-OD-04`) -- C10-C status

C10-C stays `NOT_APPLICABLE` while the strategy is advisory-only, and becomes a **blocking
pre-Demo requirement**. Never a silent `PASS`, never `WIDEN`.

### 3.6 OPEN

`LSMC-OD-27` (ATR `NOT_READY` under `SWEEP_EXTREME_ATR_BUFFER`), `LSMC-OD-28` (no lower
bound on the buffer), `LSMC-OD-29` (SHORT-side bias). See 8.2.

---

## 4. Opportunity expiry

### 4.1 AMENDED (`P13`, closes `LSMC-OD-05/06/07`) -- the computed expiry

```text
choch_close = choch_time + 5 min
M5BAR       = 5 min

FX (EURUSD, GBPUSD, USDJPY, XAUUSD):
  raw        = session_end(choch_close)                      # P5/P6, unchanged
  capped     = min(raw, choch_close + 24 x M5BAR)            # LSMC-OD-05  PROVISIONAL
  expires_at = max(capped, choch_close + 6 x M5BAR)          # LSMC-OD-06  PROVISIONAL

Crypto (BTCUSDT, ETHUSDT):                                   # LSMC-OD-07
  expires_at = choch_close + 24 x M5BAR
  No session boxes. No New York 17:00 boundary.

session_end(t):
  m = UTC hour*60 + minute of t
  for each canonical session [start, end):  if start <= m < end: return UTC-midnight(t) + end
  otherwise: return next 17:00 America/New_York

canonical sessions (UTC, half-open, fixed clock):
  asian 00:00-06:00 | london_am 06:00-11:00 | new_york_am 12:00-15:00
```

> **Superseded text (v1.0.0/v1.0.1):** `expires_at = session_end(choch_close)` for all
> symbols, with no cap and no floor.

**Order of application is normative:** cap first, then floor. The floor **overrides the
session boundary** -- an opportunity triggered at 05:58 UTC now expires at 06:33, not
06:00. That is the floor's purpose, and it is why this amends a v1.0.1 `FROZEN` property.

**Both constants are `PROVISIONAL`** (`24` and `6` M5 bars). They are owner-signed working
values, not evidenced parameters, and are expected to change.

`FROZEN` properties retained: expiry is anchored to `choch_close`, not the sweep bar and
not delivery time; boundaries are **half-open** (`now >= expires_at` is expired); expiry is
**terminal and non-reversible**; expiry and invalidation are independent clocks.

### 4.2 FROZEN -- separate POI expiry

A POI expires after `POI_MAX_AGE_TRADING_DAYS = 5` trading days (`P4`). It governs whether
a *new* opportunity may form.

### 4.3 FROZEN (`P13`, closes `LSMC-OD-08`) -- POI expiry does not terminate an opportunity

Once the CHoCH has fired the structural event is complete. The opportunity keeps its own
clock; both IDs are recorded.

### 4.4 OPEN

`LSMC-OD-31` (the floor is counted in wall-clock bars and can fall entirely inside a market
closure). See 8.2.

---

## 5. Outcome taxonomy

### 5.1 FROZEN (`P12`, closes `LSMC-OD-09`) -- the names

Outcomes are **structural facts, not trade results**. `WIN` / `LOSS` are **rejected** and
must not appear in any LSMC field, message or report.

| Outcome | Meaning |
|---|---|
| `TARGET_REACHED` | `target_c11` touched |
| `STOP_REACHED` | the `STOP_BASIS` stop level touched |
| `INVALIDATED` | M5 **close** beyond `sweep_extreme` |
| `EXPIRED` | `expires_at` passed with none of the above |
| `AMBIGUOUS_SAME_BAR` | a target and a stop/invalidation event on one bar (6.1) |

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

They are different structural facts: a touch of the risk level versus a close beyond the
thesis level. An optional derived rollup `ADVERSE = STOP_REACHED ∪ INVALIDATED` may be
reported for ratios, but never replaces the two underlying counts.

### 5.5 FROZEN (`P13`, closes `LSMC-OD-20`) -- targetless opportunities

An opportunity with `target_c11 = None` (`REJECT_NO_TARGET`) is resolvable for
`STOP_REACHED` / `INVALIDATED` / `EXPIRED` only. It can never be `TARGET_REACHED`, is
excluded from any target-hit-rate denominator, and is counted separately as `NO_TARGET`.

### 5.6 FROZEN (`P12` + `P13`, closes `LSMC-OD-10/22`) -- aggregates

Every aggregate is **stratified by `stop_basis`**. All six symbols are stop-bearing. The
two bases now share the same anchor and the same `0.35 x ATR14` term; they differ only by
the pip floor (when it binds) and the SHORT spread -- a much narrower gap than v1.0.1's
zero-buffer asymmetry, but not zero. See `LSMC-OD-29`.

---

## 6. Same-bar tie, and gap handling

### 6.1 AMENDED (`P13`, closes `LSMC-OD-26`; revises the `LSMC-OD-12` ruling) -- same-bar tie

```text
A bar containing both a target event and a stop/invalidation event resolves to
AMBIGUOUS_SAME_BAR. It is NOT resolved further in V1.
  - persist both competing levels and the full bar OHLC
  - EXCLUDE from every outcome ratio
  - COUNT SEPARATELY and report the count alongside every ratio
  - stamp m1_available = false
```

> **Superseded text (v1.0.1):** "If M1 data covering the bar is available, resolve the
> ordering from M1." **M1 resolution is deferred to v1.1.** The LSMC pipeline carries
> `TIMEFRAME_MINUTES = {D1, H1, M5}` only (`P4`), so that branch was never taken.

A winner is never imputed, and `AMBIGUOUS_SAME_BAR` is never folded into another outcome
for "conservatism" -- that would bias the statistic it feeds.

### 6.2 FROZEN (`P12`, closes `LSMC-OD-17`) -- gap through a level

When the bar triggering a terminal event **opens beyond** the level it triggered, the
outcome is recorded **at the gap open price**, not at the level, stamped
`GAP_THROUGH = true`. Both the level price and the bar open are persisted. A gap carrying
price beyond **both** stop and target is a same-bar tie and 6.1 applies.

### 6.3 FROZEN (`P13`, closes `LSMC-OD-18`) -- data outage vs market gap

```text
Gap spanning an OPEN market        -> DATA_GAP.    Resolution HALTS; outcome stays open.
                                      Never advanced to EXPIRED on absent data.
Gap spanning a SCHEDULED CLOSURE   -> MARKET_GAP.  Resolves at the reopen bar's open,
                                      stamped GAP_THROUGH.
```

The market calendar (`fx_market_closed`, crypto 24/7) is the only independent evidence
distinguishing the two.

### 6.4 FROZEN (`P13`, closes `LSMC-OD-19`) -- expiry inside a scheduled closure

`EXPIRED` at `expires_at`, flagged `EXPIRY_IN_MARKET_CLOSED`. No bar exists in which a
price-based outcome could occur, and deferring to reopen would let a weekend gap decide the
outcome.

---

## 7. Price side

### 7.1 AMENDED (`P13`, closes `LSMC-OD-13/14/16/23/24/25`) -- V1 resolves every level on bid

```text
V1 resolves ALL levels on BID. There is no ask series and no ask reconstruction.

  LONG  target   bid touch
  LONG  stop     bid touch
  SHORT stop     bid touch      (C10-B already embeds the spread -- 3.2)
  SHORT target   bid touch      -> flag SIDE_APPROX_BID
  invalidation   bid close      -> stamp invalidation_basis = BID   (LSMC-OD-15)

No typical-spread constants exist in V1.
v1.1 will adopt empirical per-symbol spreads from host-recorded samples.
```

> **Superseded text (v1.0.1):** SHORT target resolved on a reconstructed ask,
> `ask = bid + bar spread` with a typical-spread fallback flagged `ASK_APPROXIMATED`. The
> flags `ASK_APPROXIMATED` and the proposed `ASK_BAR_SPREAD` are **retired**.

This is internally consistent for the first time: every level is bid-derived (`P5`) **and**
bid-resolved, against bid-based bars (`P9`). The three blockers v1.0.1 recorded are
dissolved rather than worked around -- `Candle` carries no spread field (`P10`), the
exported column is not synchronized bid/ask OHLC, and no typical-spread constant existed
for four of six symbols.

`SIDE_APPROX_BID` is the honest label for what remains: a real short exits at the ask, so
a bid touch of the target is reached **before** a tradeable exit would be. The flag records
that the measurement is optimistic by approximately one spread.

### 7.2 FROZEN (`P13`, closes `LSMC-OD-15`) -- invalidation side

Invalidation stays on **bid**, matching `detect.m5_opportunities`, which already computes
`invalidated_time` in merged code. One definition, owned by detection; the resolver never
disagrees with detection about whether an opportunity is alive.

### 7.3 OPEN

`LSMC-OD-29` (compounding SHORT-side bias, and whether `SIDE_APPROX_BID` should extend
beyond `TARGET_REACHED`). See 8.2.

---

## 8. Owner decisions

### 8.1 Closed (26 rows)

| Ref | Ruling | Batch | Section |
|---|---|---|---|
| `LSMC-OD-01` | `sweep_extreme` accepted as the anchor for both bases | `P13` | 3.3 |
| `LSMC-OD-02` | **REPLACED** by `LSMC-OD-21/22` | `P12` -> `P13` | 3.3 |
| `LSMC-OD-03` | Stop immutable at first publication | `P13` | 3.4 |
| `LSMC-OD-04` | C10-C `NOT_APPLICABLE` now, blocking pre-Demo | `P13` | 3.5 |
| `LSMC-OD-05` | Cap `min(session_end, choch_close + 24 M5)` -- **PROVISIONAL** | `P13` | 4.1 |
| `LSMC-OD-06` | Floor `6 M5 bars` -- **PROVISIONAL** | `P13` | 4.1 |
| `LSMC-OD-07` | Crypto: duration cap only, no session boxes/NY boundary | `P13` | 4.1 |
| `LSMC-OD-08` | POI expiry does not terminate a live opportunity | `P13` | 4.3 |
| `LSMC-OD-09` | `TARGET_REACHED`/`STOP_REACHED`; `WIN`/`LOSS` rejected | `P12` | 5.1 |
| `LSMC-OD-10` | Aggregates stratified by `stop_basis` | `P12` | 5.6 |
| `LSMC-OD-11` | `STOP_REACHED` and `INVALIDATED` stay distinct | `P13` | 5.4 |
| `LSMC-OD-12` | `AMBIGUOUS_SAME_BAR`, counted separately | `P12` | 6.1 |
| `LSMC-OD-13` | **REVISED** -- all levels on bid | `P12` -> `P13` | 7.1 |
| `LSMC-OD-14` | **REVISED** -- no ask reconstruction in V1 | `P12` -> `P13` | 7.1 |
| `LSMC-OD-15` | Invalidation stays bid | `P13` | 7.2 |
| `LSMC-OD-16` | Accepted under the bid + `SIDE_APPROX_BID` rule | `P13` | 7.1 |
| `LSMC-OD-17` | Gap through a level records the gap open price | `P12` | 6.2 |
| `LSMC-OD-18` | `DATA_GAP` halts; `MARKET_GAP` resolves at reopen | `P13` | 6.3 |
| `LSMC-OD-19` | `EXPIRED` at `expires_at`, flagged | `P13` | 6.4 |
| `LSMC-OD-20` | Targetless: never `TARGET_REACHED`, counted `NO_TARGET` | `P13` | 5.5 |
| `LSMC-OD-21` | `SWEEP_EXTREME_ATR_BUFFER`; `INVALIDATED` reachable + fixture | `P13` | 3.3, `P14` |
| `LSMC-OD-22` | Same ruling as 21 | `P13` | 3.3 |
| `LSMC-OD-23` | All levels on bid; no `Candle` spread dependency | `P13` | 7.1 |
| `LSMC-OD-24` | No ask path in V1, so no approximation class to flag | `P13` | 7.1 |
| `LSMC-OD-25` | No typical-spread constants in V1; empirical spreads at v1.1 | `P13` | 7.1 |
| `LSMC-OD-26` | M1 deferred to v1.1; tie stays unresolved | `P13` | 6.1 |

### 8.2 OPEN -- new contradictions created by the 2026-10-08 batch

Raised per the owner's directive *"if applying any ruling creates a new contradiction, add
it as OD-27+ instead of resolving it."* **None is applied.** Recommended defaults are
proposals only.

| Ref | Contradiction | Recommended default | Rationale |
|---|---|---|---|
| `LSMC-OD-27` | **ATR `NOT_READY` now breaks a signed ruling either way.** Dropping the pip floor makes the non-C10 stop depend entirely on ATR14. `compute_atr14_m5` returns `None` below 15 closed M5 bars, and the watch computes ATR from `m5c[: choch_index + 1]`, so an early CHoCH can trigger it. Then: no stop contradicts "no symbol is stopless" (`LSMC-OD-10`), and a bare `sweep_extreme` stop contradicts "INVALIDATED must be reachable" (`LSMC-OD-21`). | **Fail closed: suppress the opportunity entirely**, reason `ATR_NOT_READY`, and count it as a detection-time rejection rather than an outcome | Neither partial behaviour is admissible, so the only consistent option is not to publish the opportunity at all. It is also the existing C10 convention (`ATR_NOT_READY` already fails closed in `compute_c10_stop`), so one rule covers both bases. Cost: a small, countable loss of observations, which is visible rather than silent. |
| `LSMC-OD-28` | **The buffer has no lower bound.** `compute_c10_stop` raises only on `atr < 0`; `atr == 0` is accepted. Buffer `-> 0` closes the reachability window and restores exactly the unreachability `LSMC-OD-21` was raised to fix. The pip floor was the only former lower bound and is now explicitly not applied -- and was never definable for these four symbols anyway, so it cannot simply be restored. | **Add a non-pip minimum: `buffer = max(k x point, 0.35 x ATR14)`** with `k` owner-signed per symbol, using the already-evidenced `EVIDENCED_POINT` / host-captured `point` (`P4`) rather than a pip | `point` is evidenced for every symbol in the universe (repo-evidenced for EURUSD/GBPUSD/BTCUSDT/ETHUSDT, host-captured for USDJPY/XAUUSD), so a point-based floor is definable where a pip floor was not. Alternative -- treat `atr == 0` as `ATR_NOT_READY` and fail closed -- is simpler but discards real low-volatility observations. **`k` needs a signature.** |
| `LSMC-OD-29` | **SHORT-side measurement bias now compounds in one direction.** C10-B embeds the spread in the SHORT `STOP_C10` stop, pushing it further away (fewer `STOP_REACHED`), while `SIDE_APPROX_BID` makes the SHORT target optimistic (more `TARGET_REACHED`). Both biases make shorts look better. `SWEEP_EXTREME_ATR_BUFFER` shorts carry the second bias but not the first, so the two bases are biased by different amounts. Only short `TARGET_REACHED` is flagged; short `STOP_REACHED` is equally bid-approximated and carries no flag. | **Extend the flag to every SHORT terminal event** (`SIDE_APPROX_BID` on short `STOP_REACHED` and `INVALIDATED` too), and **report LONG and SHORT outcome rates separately, never pooled**, until v1.1's empirical spreads allow the bias to be quantified | Flagging only the target implies the other short events are exact; they are not. Separating by direction costs nothing and prevents a compounded bias being read as a short-side edge. Removing C10-B's spread term is **not** proposed -- it is signed, `FROZEN`, and correct for execution. |
| `LSMC-OD-30` | **This version amends rules v1.0.1 marked `FROZEN`** -- sections 3.3, 4.1, 6.1 and 7.1. Spec section 9.2 states a `FROZEN` rule "may not be edited in place" and that changing one "requires a new signed owner decision **and a new file** (`LSMC_SPEC_V2_...`)". The 2026-10-08 batch supplies the signed decision but directs an in-file v1.0.2. The two requirements conflict, and if owner batches can amend `FROZEN` rules in place, the `FROZEN` marker loses its meaning. | **Keep v1.0.2 in place** (superseded text is retained inline, so nothing is lost) and **amend section 9.2** to the rule actually being followed: a `FROZEN` rule may be amended in place by a signed owner batch, provided the superseded text is retained verbatim and the changelog names it; a new **file** is required only for a change of strategy identity or version | The in-file history has so far preserved every superseded rule, which is the property section 9.2 was protecting. Forcing a new file per batch would fragment a single evolving contract across three documents in two days. The alternative -- reissue as `LSMC_SPEC_V2_FROZEN.md` -- is cleaner governance but discards v1.0.x continuity. **Owner must pick one; this spec currently violates its own section 9.2.** |
| `LSMC-OD-31` | **`LSMC-OD-06`'s floor is counted in wall-clock bars, not tradeable bars.** A CHoCH closing Friday 16:55 New York has its entire 30-minute floor fall inside the weekend closure, producing zero resolvable bars and an immediate `EXPIRY_IN_MARKET_CLOSED` (6.4). The floor's stated purpose -- guaranteeing a minimum chance to resolve -- is defeated in exactly the case it was written for. The same applies to the `LSMC-OD-05` cap across any closure. | **Count both the floor and the cap in bars the market is actually open**, skipping scheduled closures; equivalently, suspend both clocks while `fx_market_closed` is true | A timing artifact is what `LSMC-OD-06` was raised to remove; measuring in wall-clock time reintroduces it at the week boundary. Crypto is unaffected (24/7). Cost: expiry becomes calendar-dependent and slightly harder to compute, which is already true of `session_end`. |

---

## 9. Change control

1. Frozen at `spec_version 1.0.2`; SHA-256 in `docs/specs/LSMC_SPEC_V1_FROZEN.sha256.txt`.
2. A `FROZEN` rule may not be edited in place. Changing one requires a new signed owner
   decision and a new file (`LSMC_SPEC_V2_...`). **This clause is currently in conflict with
   the 2026-10-08 batch -- see `LSMC-OD-30`.**
3. Closing an `OWNER_DECISION_REQUIRED` row requires an owner signature, then a new spec
   version. Agents may not close rows, and may not apply a recommended default from 8.2
   without a signature.
4. `PROVISIONAL` constants (`LSMC-OD-05` cap, `LSMC-OD-06` floor) may be revised by the
   owner without a new spec file.
5. This spec grants no authority. `ST_LARGE_SMC_V1` stays `RESEARCH_DRAFT` / advisory-only.
6. Delivery and actionability remain governed solely by `LSMC_ACTIONABILITY_POLICY_V1`
   (section 0.2). Reference it; do not restate it.

---

## 10. Changelog

### 1.0.2 -- 2026-10-08 (supersedes `900593d9420d9860907ca8c8460fcd970cd6b25de624d37a977aca7f0ab323a7`)

Applies the 2026-10-08 owner batch (`P13`). **This version amends rules v1.0.1 marked
`FROZEN`** -- the first version to do so. Every superseded rule is retained inline. The
procedural conflict is `LSMC-OD-30`.

| # | Change | Section |
|---|---|---|
| 1 | `LSMC-OD-02` ruling **REPLACED**. `STOP_BASIS = SWEEP_EXTREME_ATR_BUFFER`: non-C10 stop = `sweep_extreme ± 0.35 x ATR14`, pip floor not applied. | 3.3 |
| 2 | `LSMC-OD-21/22` closed. `INVALIDATED` made reachable for all six symbols; proof fixture `P14` added (LONG + SHORT proofs, plus `STOP_REACHED` and `AMBIGUOUS_SAME_BAR` controls). | 3.3 |
| 3 | `LSMC-OD-01` closed. `sweep_extreme` accepted as the anchor for **both** bases, so the two differ only by the pip floor and the SHORT spread. | 3.3 |
| 4 | `LSMC-OD-03`, `LSMC-OD-04` closed -- stop immutability; C10-C blocking pre-Demo. | 3.4, 3.5 |
| 5 | `LSMC-OD-14` ruling **REVISED**. V1 resolves **all levels on bid**; ask reconstruction withdrawn; `ASK_APPROXIMATED` / `ASK_BAR_SPREAD` retired; short `TARGET_REACHED` carries `SIDE_APPROX_BID`. `LSMC-OD-23/24/25` closed as a consequence. | 7.1 |
| 6 | `LSMC-OD-13` **REVISED** (short target bid, not ask) and `LSMC-OD-16` re-accepted under the bid rule. Pins `P8` and `P11` retired. | 1, 7.1 |
| 7 | `LSMC-OD-26` closed. M1 tie resolution **deferred to v1.1**; the M1 branch is removed from 6.1 and ties always record `AMBIGUOUS_SAME_BAR` with `m1_available = false`. | 6.1 |
| 8 | `LSMC-OD-05`/`06`/`07` closed. Expiry gains a **cap** (`choch_close + 24 M5`) and a **floor** (`choch_close + 6 M5`), both `PROVISIONAL`; crypto drops session boxes and the NY boundary. Order of application (cap, then floor) made normative. | 4.1 |
| 9 | `LSMC-OD-08`, `11`, `15`, `18`, `19`, `20` closed at their recommended defaults. | 4.3, 5.4, 5.5, 6.3, 6.4, 7.2 |
| 10 | Five **new** contradiction rows added, none resolved: `LSMC-OD-27` (ATR `NOT_READY` breaks a signed ruling either way), `LSMC-OD-28` (no lower bound on the buffer), `LSMC-OD-29` (compounding SHORT-side bias), `LSMC-OD-30` (amending `FROZEN` in place violates 9.2), `LSMC-OD-31` (floor counted in wall-clock bars). | 8.2 |
| 11 | Pins `P13` (owner batch 2) and `P14` (reachability fixture) added; `P8`/`P11` retired. | 1 |
| 12 | `AMENDED` status introduced alongside `FROZEN`/`OPEN`; superseded text retained inline in 3.3, 4.1, 6.1, 7.1. | header |

### 1.0.1 -- 2026-10-07 (SHA-256 `900593d9…23a7`)

Applied the 2026-10-07 owner batch: side matrix, ask reconstruction, `AMBIGUOUS_SAME_BAR`,
outcome renaming, gap-open pricing, `STOP_BASIS`. Closed 8 rows, carried 12 forward with
recommended defaults, added 6 new rows. No `FROZEN` rule altered.

### 1.0.0 -- 2026-10-07 (SHA-256 `94dd0fb9…9a7e`)

Initial freeze. 20 `OWNER_DECISION_REQUIRED` rows, none resolved.
