# Ticket history audit — 2026-10-10 (MMT)

**Verdict: PARTIAL_HISTORY_FOUND**

Read-only historical audit. No signals were generated, no broker was contacted, and original ticket records were not modified.

## Scope and totals

MMT interval: `2026-10-10 00:00:00` inclusive to `2026-10-11 00:00:00` exclusive (`2026-10-09 17:30Z` to `2026-10-10 17:30Z`).

Recovered **10 unique archived tickets**: eight ASW `BLOCKED / MARKET_CLOSED` and two LSMC `WATCH`. No archived OPPORTUNITY or TRADE PROPOSAL ticket was found in-window. Three LSMC `OPPORTUNITY` log states have `alerts=[]` and no ticket IDs; they are not promoted to tickets.

| Measure | Count / status |
| --- | ---: |
| Unique archived tickets / archive evaluations | 10 |
| Additional log-only state evaluations | 10 |
| Observed evaluation-event lower bound | 20 |
| Archived OPPORTUNITY / BLOCKED / TRADE PROPOSAL | 0 / 8 / 0 |
| Telegram delivered / duplicate suppressed | 0 / 0 evidenced |
| Demo orders linked to audited tickets | 0 |
| Verification at generation | LOGIC_VERIFIED: 0; NOT_VERIFIED: 0; UNKNOWN: 10 |

## Strategy breakdown

| Strategy@Version | Symbol | In-window | UTC Oct 10 outside MMT |
| --- | --- | ---: | ---: |
|  | BTCUSD | 1 | 9 |
|  | BTCUSDT | 0 | 1 |
|  | ETHUSD | 1 | 3 |
|  | ETHUSDT | 0 | 1 |
|  | EURUSD | 2 | 0 |
|  | GBPUSD | 2 | 0 |
|  | USDJPY | 2 | 0 |
|  | XAUUSD | 2 | 0 |

## Chronological tickets in the MMT date

| Time MMT | Symbol | Strategy@Version | Direction | State | Verification | Block reason | Telegram |
| --- | --- | --- | --- | --- | --- | --- | --- |
|  | EURUSD |  | — |  /  |  | — |  |
|  | GBPUSD |  | — |  /  |  | — |  |
|  | USDJPY |  | — |  /  |  | — |  |
|  | XAUUSD |  | — |  /  |  | — |  |
|  | EURUSD |  | — |  /  |  | — |  |
|  | GBPUSD |  | — |  /  |  | — |  |
|  | USDJPY |  | — |  /  |  | — |  |
|  | XAUUSD |  | — |  /  |  | — |  |
|  | BTCUSD |  | LONG |  /  |  | — |  |
|  | ETHUSD |  | LONG |  /  |  | — |  |

### Ticket details

- ** EURUSD** — entry=; SL=; TP=; RR=not recorded; ticket ``; POI not recorded; source ``.
- ** GBPUSD** — entry=; SL=; TP=; RR=not recorded; ticket ``; POI not recorded; source ``.
- ** USDJPY** — entry=; SL=; TP=; RR=not recorded; ticket ``; POI not recorded; source ``.
- ** XAUUSD** — entry=; SL=; TP=; RR=not recorded; ticket ``; POI not recorded; source ``.
- ** EURUSD** — entry=; SL=; TP=; RR=not recorded; ticket ``; POI not recorded; source ``.
- ** GBPUSD** — entry=; SL=; TP=; RR=not recorded; ticket ``; POI not recorded; source ``.
- ** USDJPY** — entry=; SL=; TP=; RR=not recorded; ticket ``; POI not recorded; source ``.
- ** XAUUSD** — entry=; SL=; TP=; RR=not recorded; ticket ``; POI not recorded; source ``.
- ** BTCUSD** — entry=; SL=; TP=; RR=not recorded; ticket ``; POI not recorded; source ``.
- ** ETHUSD** — entry=; SL=; TP=; RR=not recorded; ticket ``; POI not recorded; source ``.

## October 10 UTC records outside the MMT date

Found 14 archive records with Oct 10 UTC event times after 17:30Z; these occurred on Oct 11 MMT and are excluded from daily totals.

| Time UTC | Time MMT | Symbol | Strategy@Version | State | Reason | Entry | SL | TP | Ticket ID |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | --- |
|  |  | BTCUSD |  | / | — |  |  |  | `` |
|  |  | ETHUSD |  | / | — | 2508.19 |  |  | `` |
|  |  | BTCUSDT |  | / | — |  |  |  | `` |
|  |  | ETHUSDT |  | / | — |  |  |  | `` |
|  |  | BTCUSD |  | / | — |  |  |  | `` |
|  |  | ETHUSD |  | / | — |  |  |  | `` |
|  |  | BTCUSD |  | / | — |  |  |  | `` |
|  |  | BTCUSD |  | / | — |  |  |  | `` |
|  |  | BTCUSD |  | / | — |  |  |  | `` |
|  |  | BTCUSD |  | / | — |  |  |  | `` |
|  |  | BTCUSD |  | / | — |  |  |  | `` |
|  |  | BTCUSD |  | / | — |  |  |  | `` |
|  |  | BTCUSD |  | / | — |  |  |  | `` |
|  |  | ETHUSD |  | / | — | 2508.62 |  |  | `` |

## Log-only evaluations, not tickets

| Time MMT | Symbol | State | Alerts |
| --- | --- | --- | --- |
| 10/10/2026 00:03:22 | EURUSD | OPPORTUNITY | [] |
| 10/10/2026 00:03:22 | GBPUSD | OPPORTUNITY | [] |
| 10/10/2026 00:03:23 | USDJPY | DEVELOPING | [] |
| 10/10/2026 00:03:23 | XAUUSD | DEVELOPING | [] |
| 10/10/2026 00:03:23 | BTCUSDT | OPPORTUNITY | [] |
| 10/10/2026 00:03:23 | ETHUSDT | NEAR_POI | [] |
| 10/10/2026 22:30:46 | EURUSD | MARKET_CLOSED | [] |
| 10/10/2026 22:30:46 | GBPUSD | MARKET_CLOSED | [] |
| 10/10/2026 22:30:46 | USDJPY | MARKET_CLOSED | [] |
| 10/10/2026 22:30:46 | XAUUSD | MARKET_CLOSED | [] |

Six LSMC checks occurred at 00:03 MMT; EURUSD, GBPUSD, and BTCUSDT showed OPPORTUNITY but emitted no alert and have no ticket ID. Four more FX checks at 22:30 MMT showed MARKET_CLOSED; BTCUSD/ETHUSD WATCH events from that cycle are archived.

## Verification, Telegram, and orders

- Exact runtime verification is UNKNOWN for all ten in-window records. A dated Oct 9 LSMC v1.1.0 fixture verification report states version-level LOGIC_VERIFIED, but no host runtime code SHA binds it to these records. No exact contemporaneous ASW v1.1.1 verification evidence was found.
- All ten archive records say `ARCHIVE_ONLY`. `canonical_fx/delivery.sqlite` was queried read-only: zero rows in the MMT interval and zero rows from 17:30Z through 24:00Z Oct 10 UTC. The Telegram log has no send during the target period; no duplicate suppression was evidenced.
- No order event links to audited ticket IDs. Separate `status/evidence/host_s1_contain_2026-10-11.json` mentions owner-placed SMC SHORT IOC orders and SL fills during Oct 10/11; no link to these tickets is recorded, so they are not counted as system-submitted orders.

## Evidence coverage and limits

- Deployed store: `<HOST_SCRATCHPAD>/journal/ticket_store`; only evaluation files for Oct 11–14 exist. `index.sqlite` is missing, so `scripts/ticket_history.py query` could not run. Reindexing was skipped to preserve read-only scope; archives and logs were queried directly.
- Inspected 176 base archive JSON files with archive path dates Oct 9–11; selection used original event timestamps. No in-window correction wrapper was found.
- Logs inspected: `ag_v1_lsmc.log`, `ag_v1_lsmc-weekend.log`, `ag_v1_crypto.log`, `ag_v1_fx.log`, `telegram.log`, the canonical FX delivery SQLite database, and the host ticket archive. Log-only rows lack stable evaluation IDs. Original host paths are redacted as `<HOST_SCRATCHPAD>`.
- **History remains partial:** canonical ticket-store data starts Oct 11; state logs are not a complete evaluation ledger; delivery records are absent for the target date.

## Next action

For completeness, recover any missing Oct 10 evaluation cohorts and the host LSMC delivery/dedupe journal. Keep log-only OPPORTUNITY states unpromoted unless their original ticket records are recovered.
