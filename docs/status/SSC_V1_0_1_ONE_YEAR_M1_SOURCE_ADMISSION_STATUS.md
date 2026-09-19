# SSC_V1_0_1_ONE_YEAR_M1_SOURCE_ADMISSION_STATUS

ST_SESSION_SWEEP_CONTINUATION_V1 v1.0.1 — admission status for the missing EURUSD M1
fill-resolution leg needed by the one-year `HISTORICAL_RESEARCH_ONLY` backtest.
Date: 2026-09-19. Environment: local Windows workstation, `.venv`, branch `main`.
**No SSC replay was executed.**

## Result

| Field | Value |
| --- | --- |
| `HEAD` | `cace99e15e21bec16e9fa9ebf072a5083877cfa0` (mission preflight HEAD; contains `cace99e`) |
| `TARGET_MISSING_INTERVAL` | `2025-09-15T00:00:00Z` → `2026-05-18T06:46:00Z` (245.282 days, 176 FX weekdays) |
| `LOCAL_SOURCE_FOUND` | **NO** — no local source contains M1 (or tick) data anywhere inside the target interval |
| `SOURCE_CLASSIFICATION` | tick export = **`UNVERIFIED_TICK_DATA`** (content-consistent with the Vantage feed, but no acquisition/provenance record); and it does not overlap the target interval |
| `SOURCE_SHA256` | `2a844b807086896d25ec57627350d23b80e088aec122b51af1e8357b0b56abd3` (`D:\EURUSD_202606182200_202608241902.csv`, 228.5 MB, 5 890 232 rows) |
| `SOURCE_COVERAGE` | tick export covers `2026-06-18T22:00Z` → `2026-08-24T19:02Z` (broker wall clock) — **zero overlap with the target interval** |
| `TIMEZONE_STATUS` | broker bridge: server wall clock, `BROKER_OFFSET_CONFIRMED` (+3 h) family; tick export convention **measured** as bid @ +3 h (P3) |
| `PARITY_STATUS` | **`PASS_EXACT`** — 1.000000 exact OHLC on 43 292 / 43 292 bars (P4) |
| `DERIVATION_STATUS` | `NOT_EXECUTED` — no admissible source, so no derivation contract was frozen and no M1 was derived |
| `DERIVED_M1_SHA256` | `NOT_CREATED` |
| `ONE_YEAR_COVERAGE_STATUS` | `BLOCKED_INCOMPLETE_ONE_YEAR_DATA` (unchanged; P7 recheck did not reach `DATA_COVERAGE_COMPLETE`) |
| `PROTECTED_DATA_CLEAR` | **YES** — CONFIRM_001 / HOLDOUT / OOS / SSC1D OOS pilot untouched (`access_count` 0 preserved) |
| `FINAL_STATUS` | **`F. NO_SUITABLE_LOCAL_SOURCE`** → stop code **`OWNER_EXTERNAL_SOURCE_AUTHORIZATION_REQUIRED`** |
| `NEXT_SINGLE_ACTION` | owner decision on an external/broker M1 source (see P8) — no local path exists |

---

## P0 — Preflight

| Check | Result |
| --- | --- |
| HEAD contains `cace99e` | **YES** (`cace99e` is HEAD; `git merge-base --is-ancestor cace99e HEAD` → true) |
| Strategy authority | `ST_SESSION_SWEEP_CONTINUATION_V1` v1.0.1, `OFFLINE_RESEARCH` (unchanged) |
| `DATA_COVERAGE_AUDIT_V1` status | `BLOCKED_INCOMPLETE_ONE_YEAR_DATA` |
| H1 coverage | **PASS** — `2025-09-15T00:00:00Z` → `2026-09-15T00:00:00Z` |
| M15 coverage | **PASS** — `2025-09-15T00:00:00Z` → `2026-09-15T00:00:00Z` |
| H1 warmup | **PASS** — 4 473 / 4 478 closed H1 bars before the first decision (requirement 1 000) |
| Only blocker | **CONFIRMED** — missing M1 `FILL_RESOLUTION_INPUT` coverage |
| Concurrent/foreign WIP | **preserved** — `src/mtf_context/*`, `src/historical_replay/*`, `state/proposal_ledger/*`, `tests/test_topdown_*`, `docs/status/TD8_*` all left unstaged and unmodified |

## P1 — Search of existing authorities

Four source families were inventoried read-only. No provider was introduced and nothing
was downloaded.

| # | Family | Format | Earliest | Latest | Rows | Timezone | Broker identity |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Registered repository EURUSD M1 datasets (`SSC_V1_0_1_G2_DEV_00{1,2}/raw/EURUSD_M1.csv`, `SSC_FRESH_DEV_GEN_002.../raw/EURUSD_M1.csv`) | UTC `timestamp_utc` CSV | `2026-06-21T21:02:00Z` | `2026-09-14T23:57:00Z` | 43 292 + 43 292 + 44 546 | UTC (native `copy_rates_range`) | Vantage `VantageMarkets-Demo`, account 26088035 |
| 2 | Owner-authorized `D:\` exports (`EURUSD_M1_202605180946_...` and 5 siblings) | MT5 Export tab-delimited, broker-local | **`2026-05-18T06:46:00Z`** | `2026-08-01T03:26:00Z` | 78 444 (largest) | `BROKER_OFFSET_CONFIRMED` (+3 h) | Vantage (owner blanket `D:\` FX authorization 2026-09-10) |
| 3 | MT5/Vantage history still reachable through the live terminal (`MetaTrader5` bridge, account 26088035) | live `copy_rates_range` probe | M1: **`2026-07-01`** (probed boundary); M5/M15/H1: back through the target interval | — | — | broker wall clock | Vantage `VantageMarkets-Demo` |
| 4 | `D:\EURUSD_202606182200_202608241902.csv` | raw bid/ask tick export (228.5 MB) | `2026-06-18T22:00` (broker) | `2026-08-24T19:02` (broker) | see P2 | determined in P2/P4 | filename-implied only — authority not assumed |

**Family 3 is the decisive new measurement.** The live bridge returns real M5/M15/H1
bars for weekday dates inside the target interval, but a **degenerate one-bar response**
for every M1 request outside its current retention window:

| Same-date probe (weekday, inside target interval) | M1 | M5 | M15 | H1 | D1 |
| --- | --- | --- | --- | --- | --- |
| `2025-12-15` | **1** (degenerate) | 211 | 71 | 18 | 1 |
| `2026-04-15` | **1** (degenerate) | 289 | 97 | 24 | 1 |

M1 availability boundary (first-of-month probes, M15 measured on identical dates as the control):

| Probe date | M1 bars | M15 bars |
| --- | --- | --- |
| `2026-03-01` (Sunday) | 1 (degenerate) | 0 (market closed) |
| `2026-04-01` | 1 (degenerate) | 97 |
| `2026-05-01` | 1 (degenerate) | 97 |
| `2026-06-01` | 1 (degenerate) | 71 |
| `2026-07-01` | 1 438 (real) | 97 |
| `2026-08-01` | 387 (real) | 26 |
| `2026-09-01` | 1 439 (real) | 97 |

Read together: **the blocker is M1-specific**. Price history for the target interval
exists at M5/M15/H1 granularity on the same broker, but M1 does not — the M1 retention
window has already rolled forward past `2026-05-18`. This is a broker/terminal M1
history limitation, not a broken request (the same calls return real data on the
control dates and on M5/M15/H1).

Terminal facts recorded with the probe: build 6182, `maxbars` setting 100 000,
data path `...\MetaQuotes\Terminal\8EFB2DF501EAEF188AB46828829DBF78`, company
`Vantage Markets (Pty) Ltd`, server `VantageMarkets-Demo`, login `26088035` — the same
account/server every owner-authorized SSC dataset came from.

`MISSING_INTERVAL_COVERAGE`: **no** candidate covers any part of
`2025-09-15 → 2026-05-18`. The nearest M1 start is `2026-05-18T06:46:00Z`, which is
*after* the interval ends.

## P2 — Raw tick export adjudication

Source: `D:\EURUSD_202606182200_202608241902.csv`, 228.5 MB
(239 602 849 bytes), SHA-256
`2a844b807086896d25ec57627350d23b80e088aec122b51af1e8357b0b56abd3`.

| Property | Measurement |
| --- | --- |
| Format | tab-separated MT5 **ticks** export, 7 columns: `<DATE> <TIME> <BID> <ASK> <LAST> <VOLUME> <FLAGS>` |
| Rows | 5 890 232 (parse failures **0**) |
| Span (broker wall clock) | `2026-06-18T22:00:00.095` → `2026-08-24T19:02:01.361` |
| Ordering | **monotonic** — 0 non-monotonic rows; 84 exact duplicate timestamps |
| Prices | 0 invalid / non-positive / non-finite; 0 crossed quotes (ask < bid) |
| Record shape | **one side per record**: FLAGS bitfield `2` = bid-only (1 863 863 rows), `4` = ask-only (1 772 943), `6` = both sides (2 253 426). A blank bid or ask column is this format's normal shape, **not** a bad price |
| Distinct minutes | bid 67 365 · ask 67 299 · mid 65 748 |
| Gaps / weekend behaviour | weekends absent (broker market closure), consistent with the same broker calendar as the canonical exports |
| Quality | `PASS` |

**Classification: `UNVERIFIED_TICK_DATA`.**

Rationale: content is *demonstrably* consistent with the Vantage feed (see P4 — exact
parity with canonical Vantage M1), but **provenance is not established**: the file has no
acquisition record anywhere in the repository naming a broker, account, venue, export
interval or authorization, and this mission's P2 rule is explicit that authority must not
be inferred from a filename. Promoting it to `BROKER_AUTHORITATIVE_TICK_DATA` requires an
owner-authorized acquisition record binding it to the same broker/account family the
owner-approved datasets use. It is **not** `NOT_TICK_DATA` (it is genuine bid/ask tick
data) and not `INSUFFICIENT_METADATA` in the sense of being unreadable — it parses
cleanly; it is the *authorization/provenance* metadata that is absent.

Independently of provenance, this file **cannot resolve the mission**: it covers
`2026-06-18 → 2026-08-24`, which does not overlap the target interval
(`2025-09-15 → 2026-05-18`) at all.

## P3 — Tick → M1 feasibility, price-stream determination

Performed on the already-consumed overlap, and — deliberately — the timezone offset and
price stream were **measured, not assumed**: 15 candidate conventions (5 offsets
`{-3,-2,0,+2,+3}` × 3 streams `{bid, ask, mid}`) were scored against canonical M1.

| Convention | Bars compared | Exact all-four OHLC rate | Max deviation | Mean deviation |
| --- | --- | --- | --- | --- |
| **bid @ +3 h** | **43 292** | **1.000000** | **0.0** | **0.0** |
| mid @ +2 h | 41 819 | 0.000096 | 0.00651 | 0.0005284 |
| ask @ −3 h | 40 846 | 0.000024 | 0.00930 | 0.0013921 |
| bid @ +2 h | 42 811 | 0.000023 | 0.00658 | 0.0005172 |

Determined convention: **bid price stream, broker wall clock at +3 h to UTC** — the same
offset the owner-authorized `D:\` export family resolves to
(`BROKER_OFFSET_CONFIRMED`). Aggregation would be the canonical
`open = first tick`, `high = max`, `low = min`, `close = last` over the minute.

## P4 — Overlap parity test

Overlap used: **canonical `SSC_V1_0_1_G2_DEV_002` M1** (already consumed DEVELOPMENT
evidence, 43 292 bars, `2026-06-21T21:02:00Z → 2026-08-02T23:59:00Z`) against tick-derived
M1 over the identical minutes. Source/derivation validation only — **no new strategy
evidence, no replay**.

| Metric | Result |
| --- | --- |
| `PARITY_STATUS` | **`PASS_EXACT`** |
| Timestamp coverage | overlap `2026-06-21T21:02:00Z → 2026-08-02T23:59:00Z`; **43 292 / 43 292** canonical minutes present in the tick file |
| Missing bars (`canonical_minutes_not_in_tick`) | **0** |
| Extra bars (`tick_minutes_not_in_canonical`) | 24 073 — the tick export is a **superset**: it also covers periods the canonical DEVELOPMENT export never contained (`2026-06-18 → 2026-06-21` and `2026-08-03 → 2026-08-24`) plus minutes canonical itself omits |
| OHLC exact-match rate | `open` 1.000000 · `high` 1.000000 · `low` 1.000000 · `close` 1.000000 — **exact on every bar** |
| Tick-normalized differences | max absolute deviation **0.0**, mean absolute deviation **0.0** (price units, not pips) |
| Session-boundary differences | none — exact rate 1.000000 inside ASIAN_LONDON (7 200 bars), 1.000000 inside LONDON_NEWYORK (5 400 bars), 1.000000 outside all trade windows (30 692 bars) |

**Interpretation:** bid-tick → M1 derivation is *exactly* faithful to canonical MT5 M1 on
this broker's feed, including at session boundaries. The derivation path itself is
therefore **not** the obstacle — the obstacle is that no admitted local source contains
tick *or* M1 data for the target interval.


## P5 — Admission decision

**`F. NO_SUITABLE_LOCAL_SOURCE`.**

Reasons, each independently sufficient:

1. No local M1 source begins before `2026-05-18T06:46:00Z`; the target interval ends
   exactly there. Coverage of the interval is 0 %.
2. The broker bridge cannot fetch it either: M1 returns its degenerate one-bar answer
   for every date before ~`2026-06-30`, while M5/M15/H1 on the same dates return real
   bars — so this is not a fixable request/proxy problem, it is the broker's M1
   retention horizon.
3. `E. BLOCKED_INCOMPLETE_COVERAGE` also applies to candidate 4 in isolation (the tick
   export covers only `2026-06-18 → 2026-08-24`), but F is the operative classification
   because **no** local source of any kind reaches the interval.

Standards were not lowered to obtain a one-year result: M5 was not promoted to M1, no
M1 was synthesized from tick data, and no second provider was introduced. A
part-year run was **not** substituted for the requested one-year window (and would in
any case be a re-analysis of already-consumed evidence — see
`SSC_V1_0_1_ONE_YEAR_HISTORICAL_BACKTEST_STATUS.md` P2).

## P6 — Derivation

`NOT_EXECUTED`. Because P5 returned F rather than A, no derivation contract was frozen
and no M1 dataset was derived. `DATA_ROLE` for any future derived leg remains
`HISTORICAL_RESEARCH_INPUT_ONLY`; `run_replay` was not called.

## P7 — Coverage recheck

`python scripts/audit_ssc_v1_0_1_one_year_data_coverage.py` → `FINAL_STATUS =
BLOCKED_INCOMPLETE_ONE_YEAR_DATA` (exit code 1). The gate requires
`DATA_COVERAGE_COMPLETE`, which was not reached, so the mission **STOPS** here and no
further stage (P6 derivation, backtest execution) is entered.

## P8 — External provider: owner authorization required

**`OWNER_EXTERNAL_SOURCE_AUTHORIZATION_REQUIRED`**

No local authoritative source qualifies. Nothing was downloaded, mixed, or admitted.

Candidate source requirements (for the owner's decision — recorded, not executed):

1. **Same broker first.** Re-request Vantage EURUSD M1 for
   `2025-09-15 → 2026-05-18` from a terminal/account whose M1 retention still reaches
   that period (e.g. a second Vantage terminal whose history has not rolled forward, or
   a broker-side history request). This keeps the single-provider lineage intact and is
   the cheapest path to a canonical M1 leg.
2. If (1) is impossible, an **external M1 provider** would require, at minimum:
   - written owner authorization naming the provider and the exact interval;
   - broker/provider identity + account/export identity recorded per file;
   - explicit timezone authority proven (weekend-reopen evidence), not inferred from a filename;
   - raw M1 (not tick-derived, not M5-derived) unless a tick source is separately admitted under 3;
   - an overlap parity test against canonical Vantage M1 on an already-consumed interval
     with a pre-declared acceptance threshold (the same test shape as P4 below);
   - `DATA_ROLE = HISTORICAL_RESEARCH_INPUT_ONLY`, a frozen derivation/acquisition
     contract, and a recorded SHA-256 — no relabeling as counting evidence.
3. If a **raw tick** source is proposed instead, P4's result is the important enabling
   fact: bid-tick → M1 derivation already reproduces canonical MT5 M1 **exactly**
   (1.000000 over 43 292 bars, sessions included), so a same-broker tick export covering
   the gap would be *sufficient* for a frozen derivation contract — provided its
   provenance is owner-authorized (`UNVERIFIED_TICK_DATA` must not simply be relabelled
   `BROKER_AUTHORITATIVE`). The existing local tick export cannot serve: it is
   unprovenanced **and** covers the wrong period.

## P9 — Safety

```
STRATEGY_CHANGED=false            PARAMETERS_CHANGED=false
SSC_REPLAY_EXECUTED=false         OPTIMIZATION_RUN=false
CONFIRMATION_ACCESSED=false       HOLDOUT_ACCESSED=false
OOS_ACCESSED=false                BROKER_MUTATION=false
DEMO_ORDER=false                  LIVE_ORDER=false
```

No order was placed or checked; no position, SL/TP or account state was modified; the
only broker interaction was read-only history/rates probing of the already-connected
terminal. No protected evidence was read. No strategy YAML or parameter was edited.

## Evidence

- `artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/SSC_V1_0_1_HIST_1Y_001/M1_SOURCE_ADMISSION_V1.json`
- `scripts/adjudicate_ssc_1y_m1_gap_source.py`
- `artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/SSC_V1_0_1_HIST_1Y_001/DATA_COVERAGE_AUDIT_V1.json`
  (produced by the prior mission; unchanged)
