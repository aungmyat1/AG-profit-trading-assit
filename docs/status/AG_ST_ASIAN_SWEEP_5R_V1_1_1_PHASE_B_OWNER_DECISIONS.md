# ST_ASIAN_SWEEP_5R_V1@1.1.1 — Phase B owner decisions (template)

Status: **PENDING_OWNER**. Not filled in. Every `Choice` below is `PENDING_OWNER` until the owner
writes it. An agent may not fill, infer or default any field (mission R2 invariant: rules,
thresholds, risk, cost and session anchoring are owner decisions). Phase C starts only when
every required field is filled and signed below.

Packet: `AG_ST_ASIAN_SWEEP_5R_V1_1_1_PHASE_B_RECONCILIATION_2026-10-06.md` (row IDs, options and
consequences). "A" = the YAML wins, "B" = the engine wins, "C" = other (write it out).

## 1. Rows that need a choice

| Row | Options | Choice | Values required if A (or C) |
|---|---|---|---|
| B-REGIME | A sweep only / B declare TREND + range-rejection | PENDING_OWNER | B: geometry for each declared branch |
| B-ENTRY | A sweep candle close / B body edge | PENDING_OWNER | — |
| B-STOP | A 0.25 × reference range / B wick extreme / C other | PENDING_OWNER | C: rule |
| B-TGT-ORDER | A explicit ordering rule / B none (TP1 may pass TP2) | PENDING_OWNER | A: reject, drop leg 1, or merge legs |
| B-EMA | A implement / B remove | PENDING_OWNER | A: timeframe, price, measurement time, gating effect |
| B-RANGECHK | A implement as gate / B remove | PENDING_OWNER | A: effect; value per symbol (EURUSD 25 pips given; GBPUSD, USDJPY, XAUUSD) |
| B-MINRANGE | A add a minimum / B none | PENDING_OWNER | A: minimum stop or range, and unit |
| B-SPREAD | A YAML 2.0-pip cap / B 15 % of stop / C both | PENDING_OWNER | — |
| B-EXPIRY | A declare in spec / B keep 15 min from code | PENDING_OWNER | A: expiry value |
| B-TIMEINV | A global 15:00 / B per-pair session end | PENDING_OWNER | — |
| B-STRUCT | A define "expansion volume" / B drop volume clause / C drop rule | PENDING_OWNER | A: volume source and threshold |

## 2. Rows marked "agree" (confirm only)

| Row | Confirm (YES / NO + note) |
|---|---|
| B-REF | PENDING_OWNER |
| B-TRADE | PENDING_OWNER |
| B-SWEEP | PENDING_OWNER |
| B-DIR | PENDING_OWNER |
| B-SPLIT | PENDING_OWNER |
| B-MAXENTRY | PENDING_OWNER |
| B-INSTR (AUDUSD in spec but not in the ticket universe) | PENDING_OWNER |

## 3. Session anchoring (packet §4)

| Item | Options | Choice |
|---|---|---|
| Anchor | Fixed UTC (current) / London-local / NY-local read as EDT / NY-local read as EST / mixed | PENDING_OWNER |
| Time invalidation anchoring | Fixed 15:00 UTC / re-anchored with the windows / per-pair session end | PENDING_OWNER |

## 4. Phase D carry-in (packet §5)

| Item | Options | Choice |
|---|---|---|
| Rename of the "no setup yet, window open" WATCH | `SETUP_WINDOW_OPEN` / `AWAITING_TRIGGER` / `NO_SETUP_YET` | PENDING_OWNER |

## 5. Sign-off

| Field | Value |
|---|---|
| Owner | PENDING_OWNER |
| Date | PENDING_OWNER |
| Successor version id (e.g. 1.2.0) | PENDING_OWNER |
