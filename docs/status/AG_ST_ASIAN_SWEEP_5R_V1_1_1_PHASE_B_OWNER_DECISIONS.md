---
class: evidence
state: DESIGN
owner_reviewed: 2026-10-09
review_by: null
---
# ST_ASIAN_SWEEP_5R_V1@1.1.1 — Phase B owner decisions (template)

Status: **OWNER_CONFIRMED** (OD1009-D1, Aung, 2026-10-09). Every Phase B row below is
`CONFIRMED_AS_RECOMMENDED`; the session anchor is fixed UTC, the Phase D carry-in accepts the
packet proposal, and successor version is v1.1.2. This records the owner decision only; it does
not change the current strategy authority or READY authorization.

Packet: `AG_ST_ASIAN_SWEEP_5R_V1_1_1_PHASE_B_RECONCILIATION_2026-10-06.md` (row IDs, options and
consequences). "A" = the YAML wins, "B" = the engine wins, "C" = other (write it out).

## 1. Rows that need a choice

| Row | Options | Choice | Values required if A (or C) |
|---|---|---|---|
| B-REGIME | A sweep only / B declare TREND + range-rejection | CONFIRMED_AS_RECOMMENDED | B: geometry for each declared branch |
| B-ENTRY | A sweep candle close / B body edge | CONFIRMED_AS_RECOMMENDED | — |
| B-STOP | A 0.25 × reference range / B wick extreme / C other | CONFIRMED_AS_RECOMMENDED | C: rule |
| B-TGT-ORDER | A explicit ordering rule / B none (TP1 may pass TP2) | CONFIRMED_AS_RECOMMENDED | A: reject, drop leg 1, or merge legs |
| B-EMA | A implement / B remove | CONFIRMED_AS_RECOMMENDED | A: timeframe, price, measurement time, gating effect |
| B-RANGECHK | A implement as gate / B remove | CONFIRMED_AS_RECOMMENDED | A: effect; value per symbol (EURUSD 25 pips given; GBPUSD, USDJPY, XAUUSD) |
| B-MINRANGE | A add a minimum / B none | CONFIRMED_AS_RECOMMENDED | A: minimum stop or range, and unit |
| B-SPREAD | A YAML 2.0-pip cap / B 15 % of stop / C both | CONFIRMED_AS_RECOMMENDED | — |
| B-EXPIRY | A declare in spec / B keep 15 min from code | CONFIRMED_AS_RECOMMENDED | A: expiry value |
| B-TIMEINV | A global 15:00 / B per-pair session end | CONFIRMED_AS_RECOMMENDED | — |
| B-STRUCT | A define "expansion volume" / B drop volume clause / C drop rule | CONFIRMED_AS_RECOMMENDED | A: volume source and threshold |

## 2. Rows marked "agree" (confirm only)

| Row | Confirm (YES / NO + note) |
|---|---|
| B-REF | CONFIRMED_AS_RECOMMENDED |
| B-TRADE | CONFIRMED_AS_RECOMMENDED |
| B-SWEEP | CONFIRMED_AS_RECOMMENDED |
| B-DIR | CONFIRMED_AS_RECOMMENDED |
| B-SPLIT | CONFIRMED_AS_RECOMMENDED |
| B-MAXENTRY | CONFIRMED_AS_RECOMMENDED |
| B-INSTR (AUDUSD in spec but not in the ticket universe) | CONFIRMED_AS_RECOMMENDED |

## 3. Session anchoring (packet §4)

| Item | Options | Choice |
|---|---|---|
| Anchor | Fixed UTC (current) / London-local / NY-local read as EDT / NY-local read as EST / mixed | CONFIRMED_AS_RECOMMENDED — fixed UTC |
| Time invalidation anchoring | Fixed 15:00 UTC / re-anchored with the windows / per-pair session end | CONFIRMED_AS_RECOMMENDED — fixed UTC |

## 4. Phase D carry-in (packet §5)

| Item | Options | Choice |
|---|---|---|
| Rename of the "no setup yet, window open" WATCH | `SETUP_WINDOW_OPEN` / `AWAITING_TRIGGER` / `NO_SETUP_YET` | CONFIRMED_AS_RECOMMENDED — accept packet proposal: `SETUP_WINDOW_OPEN` |

## 5. Sign-off

| Field | Value |
|---|---|
| Owner | Aung |
| Date | 2026-10-09 |
| Successor version id (e.g. 1.2.0) | v1.1.2 |
