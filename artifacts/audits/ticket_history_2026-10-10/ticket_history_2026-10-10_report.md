# Ticket history audit — 2026-10-10 (MMT)

**Verdict: PARTIAL_HISTORY_FOUND**

Read-only historical audit. No signals were generated, no broker was contacted, and historical store files were not modified.

## Scope and result

MMT interval: `2026-10-10 00:00:00` inclusive to `2026-10-11 00:00:00` exclusive (`2026-10-09 17:30Z` to `2026-10-10 17:30Z`).

Recovered **10 unique archived tickets** across 10 archived evaluation records. There were 10 additional log-only LSMC state evaluations, including 3 `OPPORTUNITY` states with `alerts=[]`; no ticket ID or archived ticket exists for those rows, so they are not counted as tickets.

## A. Daily totals

| Measure | Count / result |
| --- | ---: |
| Unique archived tickets in MMT interval | 10 |
| Archived ticket evaluation records | 10 |
| Additional log-only state evaluations | 10 |
| Observed evaluation-event lower bound | 20 |
| Archived OPPORTUNITY tickets | 0 |
| BLOCKED tickets | 8 |
| TRADE PROPOSAL tickets | 0 |
| Telegram delivered | 0 evidenced |
| Duplicate-suppressed Telegram messages | 0 evidenced |
| Demo orders linked to these tickets | 0 |
| Verification UNKNOWN | 10 |

All 10 in-window archive records say `delivery_mode=ARCHIVE_ONLY`. No delivery attempt or duplicate-suppression event was found for them.

## B. Strategy breakdown

| Strategy@Version | Symbol | Tickets |
| --- | --- | ---: |
| ST_ASIAN_SWEEP_5R_V1@1.1.1 | EURUSD | 2 |
| ST_ASIAN_SWEEP_5R_V1@1.1.1 | GBPUSD | 2 |
| ST_ASIAN_SWEEP_5R_V1@1.1.1 | USDJPY | 2 |
| ST_ASIAN_SWEEP_5R_V1@1.1.1 | XAUUSD | 2 |
| ST_LARGE_SMC_V1@1.1.0 | BTCUSD | 1 |
| ST_LARGE_SMC_V1@1.1.0 | ETHUSD | 1 |

## C–D. Chronological ticket history

| event_time_mmt | symbol | strategy_at_version | direction | ticket_state | verification_at_generation | block_reason | telegram_status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-10T15:47:06.160724+06:30 | XAUUSD | ST_ASIAN_SWEEP_5R_V1@1.1.1 | — | BLOCKED | UNKNOWN | MARKET_CLOSED | NOT_SENT_ARCHIVE_ONLY |
| 2026-10-10T15:47:06.160724+06:30 | USDJPY | ST_ASIAN_SWEEP_5R_V1@1.1.1 | — | BLOCKED | UNKNOWN | MARKET_CLOSED | NOT_SENT_ARCHIVE_ONLY |
| 2026-10-10T15:47:06.160724+06:30 | GBPUSD | ST_ASIAN_SWEEP_5R_V1@1.1.1 | — | BLOCKED | UNKNOWN | MARKET_CLOSED | NOT_SENT_ARCHIVE_ONLY |
| 2026-10-10T15:47:06.160724+06:30 | EURUSD | ST_ASIAN_SWEEP_5R_V1@1.1.1 | — | BLOCKED | UNKNOWN | MARKET_CLOSED | NOT_SENT_ARCHIVE_ONLY |
| 2026-10-10T20:16:45.185674+06:30 | XAUUSD | ST_ASIAN_SWEEP_5R_V1@1.1.1 | — | BLOCKED | UNKNOWN | MARKET_CLOSED | NOT_SENT_ARCHIVE_ONLY |
| 2026-10-10T20:16:45.185674+06:30 | USDJPY | ST_ASIAN_SWEEP_5R_V1@1.1.1 | — | BLOCKED | UNKNOWN | MARKET_CLOSED | NOT_SENT_ARCHIVE_ONLY |
| 2026-10-10T20:16:45.185674+06:30 | GBPUSD | ST_ASIAN_SWEEP_5R_V1@1.1.1 | — | BLOCKED | UNKNOWN | MARKET_CLOSED | NOT_SENT_ARCHIVE_ONLY |
| 2026-10-10T20:16:45.185674+06:30 | EURUSD | ST_ASIAN_SWEEP_5R_V1@1.1.1 | — | BLOCKED | UNKNOWN | MARKET_CLOSED | NOT_SENT_ARCHIVE_ONLY |
| 2026-10-10T22:30:29.130638+06:30 | ETHUSD | ST_LARGE_SMC_V1@1.1.0 | LONG | WATCH | UNKNOWN |  | NOT_SENT_ARCHIVE_ONLY |
| 2026-10-10T22:30:29.130638+06:30 | BTCUSD | ST_LARGE_SMC_V1@1.1.0 | LONG | WATCH | UNKNOWN |  | NOT_SENT_ARCHIVE_ONLY |

### Available price and identity fields

| event_time_mmt | symbol | entry | stop_loss | take_profit | risk_reward | ticket_id | source_reference |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-10T15:47:06.160724+06:30 | XAUUSD | — | — | — | — | ST_ASIAN_SWEEP_5R_V1\|1.1.1\|XAUUSD\|ASIAN_LONDON\|2026-10-10 | <HOST_SCRATCHPAD>/journal/ticket_delivery/archive/fx_ticket_archive/ST_ASIAN_SWEEP_5R_V1/XAUUSD/ASIAN_LONDON/2026/2026-10-10.json |
| 2026-10-10T15:47:06.160724+06:30 | USDJPY | — | — | — | — | ST_ASIAN_SWEEP_5R_V1\|1.1.1\|USDJPY\|ASIAN_LONDON\|2026-10-10 | <HOST_SCRATCHPAD>/journal/ticket_delivery/archive/fx_ticket_archive/ST_ASIAN_SWEEP_5R_V1/USDJPY/ASIAN_LONDON/2026/2026-10-10.json |
| 2026-10-10T15:47:06.160724+06:30 | GBPUSD | — | — | — | — | ST_ASIAN_SWEEP_5R_V1\|1.1.1\|GBPUSD\|ASIAN_LONDON\|2026-10-10 | <HOST_SCRATCHPAD>/journal/ticket_delivery/archive/fx_ticket_archive/ST_ASIAN_SWEEP_5R_V1/GBPUSD/ASIAN_LONDON/2026/2026-10-10.json |
| 2026-10-10T15:47:06.160724+06:30 | EURUSD | — | — | — | — | ST_ASIAN_SWEEP_5R_V1\|1.1.1\|EURUSD\|ASIAN_LONDON\|2026-10-10 | <HOST_SCRATCHPAD>/journal/ticket_delivery/archive/fx_ticket_archive/ST_ASIAN_SWEEP_5R_V1/EURUSD/ASIAN_LONDON/2026/2026-10-10.json |
| 2026-10-10T20:16:45.185674+06:30 | XAUUSD | — | — | — | — | ST_ASIAN_SWEEP_5R_V1\|1.1.1\|XAUUSD\|LONDON_NEWYORK\|2026-10-10 | <HOST_SCRATCHPAD>/journal/ticket_delivery/archive/fx_ticket_archive/ST_ASIAN_SWEEP_5R_V1/XAUUSD/LONDON_NEWYORK/2026/2026-10-10.json |
| 2026-10-10T20:16:45.185674+06:30 | USDJPY | — | — | — | — | ST_ASIAN_SWEEP_5R_V1\|1.1.1\|USDJPY\|LONDON_NEWYORK\|2026-10-10 | <HOST_SCRATCHPAD>/journal/ticket_delivery/archive/fx_ticket_archive/ST_ASIAN_SWEEP_5R_V1/USDJPY/LONDON_NEWYORK/2026/2026-10-10.json |
| 2026-10-10T20:16:45.185674+06:30 | GBPUSD | — | — | — | — | ST_ASIAN_SWEEP_5R_V1\|1.1.1\|GBPUSD\|LONDON_NEWYORK\|2026-10-10 | <HOST_SCRATCHPAD>/journal/ticket_delivery/archive/fx_ticket_archive/ST_ASIAN_SWEEP_5R_V1/GBPUSD/LONDON_NEWYORK/2026/2026-10-10.json |
| 2026-10-10T20:16:45.185674+06:30 | EURUSD | — | — | — | — | ST_ASIAN_SWEEP_5R_V1\|1.1.1\|EURUSD\|LONDON_NEWYORK\|2026-10-10 | <HOST_SCRATCHPAD>/journal/ticket_delivery/archive/fx_ticket_archive/ST_ASIAN_SWEEP_5R_V1/EURUSD/LONDON_NEWYORK/2026/2026-10-10.json |
| 2026-10-10T22:30:29.130638+06:30 | ETHUSD | — | — | — | — | ST_LARGE_SMC_V1\|1.1.0\|ETHUSD\|LSMC_WATCH-c7fd7bdfa0cac52b1192021b\|2026-10-10 | <HOST_SCRATCHPAD>/journal/ticket_delivery/archive/fx_ticket_archive/ST_LARGE_SMC_V1/ETHUSD/LSMC_WATCH-c7fd7bdfa0cac52b1192021b/2026/2026-10-10.json |
| 2026-10-10T22:30:29.130638+06:30 | BTCUSD | — | — | — | — | ST_LARGE_SMC_V1\|1.1.0\|BTCUSD\|LSMC_WATCH-2ca10b1ba8bb8faecca2c620\|2026-10-10 | <HOST_SCRATCHPAD>/journal/ticket_delivery/archive/fx_ticket_archive/ST_LARGE_SMC_V1/BTCUSD/LSMC_WATCH-2ca10b1ba8bb8faecca2c620/2026/2026-10-10.json |

No entry/SL/TP/RR plan was recorded on any in-window archive ticket. For LSMC WATCH rows, available POI context is listed in the JSON export. ASW records are `MARKET_CLOSED` blocks.

### Log-only evaluations, not counted as tickets

| event_time_mmt | symbol | observed_state | alerts | classification | source_reference |
| --- | --- | --- | --- | --- | --- |
| 2026-10-10T00:03:22.964553+06:30 | EURUSD | OPPORTUNITY | [] | LOG_ONLY_STATE_NO_ARCHIVED_TICKET | <HOST_SCRATCHPAD>/logs/ag_v1_lsmc.log |
| 2026-10-10T00:03:22.986762+06:30 | GBPUSD | OPPORTUNITY | [] | LOG_ONLY_STATE_NO_ARCHIVED_TICKET | <HOST_SCRATCHPAD>/logs/ag_v1_lsmc.log |
| 2026-10-10T00:03:23.009747+06:30 | USDJPY | DEVELOPING | [] | LOG_ONLY_STATE_NO_ARCHIVED_TICKET | <HOST_SCRATCHPAD>/logs/ag_v1_lsmc.log |
| 2026-10-10T00:03:23.012939+06:30 | XAUUSD | DEVELOPING | [] | LOG_ONLY_STATE_NO_ARCHIVED_TICKET | <HOST_SCRATCHPAD>/logs/ag_v1_lsmc.log |
| 2026-10-10T00:03:23.016520+06:30 | BTCUSDT | OPPORTUNITY | [] | LOG_ONLY_STATE_NO_ARCHIVED_TICKET | <HOST_SCRATCHPAD>/logs/ag_v1_lsmc.log |
| 2026-10-10T00:03:23.020072+06:30 | ETHUSDT | NEAR_POI | [] | LOG_ONLY_STATE_NO_ARCHIVED_TICKET | <HOST_SCRATCHPAD>/logs/ag_v1_lsmc.log |
| 2026-10-10T22:30:46.144329+06:30 | EURUSD | MARKET_CLOSED | [] | LOG_ONLY_STATE_NO_ARCHIVED_TICKET | <HOST_SCRATCHPAD>/logs/ag_v1_lsmc.log |
| 2026-10-10T22:30:46.149675+06:30 | GBPUSD | MARKET_CLOSED | [] | LOG_ONLY_STATE_NO_ARCHIVED_TICKET | <HOST_SCRATCHPAD>/logs/ag_v1_lsmc.log |
| 2026-10-10T22:30:46.154169+06:30 | USDJPY | MARKET_CLOSED | [] | LOG_ONLY_STATE_NO_ARCHIVED_TICKET | <HOST_SCRATCHPAD>/logs/ag_v1_lsmc.log |
| 2026-10-10T22:30:46.157762+06:30 | XAUUSD | MARKET_CLOSED | [] | LOG_ONLY_STATE_NO_ARCHIVED_TICKET | <HOST_SCRATCHPAD>/logs/ag_v1_lsmc.log |

Three states (EURUSD, GBPUSD, BTCUSDT) read `OPPORTUNITY` at 00:03 MMT but the host log records `alerts=[]`; the ticket archive has no matching logical ticket IDs. Four additional FX states at 22:30 MMT were `MARKET_CLOSED` with no alert; two crypto watch states at the same cycle are archived above.

## UTC October 10 records outside the MMT day

These event timestamps are on October 10 UTC but convert to October 11 MMT, so they are excluded from daily totals.

| event_time_utc | event_time_mmt | symbol | strategy_at_version | ticket_state | decision_state | block_reason | telegram_status | ticket_id |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-10T20:48:08.950372+00:00 | 2026-10-11T03:18:08.950372+06:30 | ETHUSD | ST_LARGE_SMC_V1@1.1.0 | NO_TRADE | REJECTED | REJECT_NO_STOP;D30_BADGE_ECONOMICS_NOT_EVALUATED | NOT_SENT_ARCHIVE_ONLY | ST_LARGE_SMC_V1\|1.1.0\|ETHUSD\|LSMC_WATCH-f28fb8035c62b4c88daf5513\|2026-10-10 |
| 2026-10-10T20:48:08.950372+00:00 | 2026-10-11T03:18:08.950372+06:30 | BTCUSD | ST_LARGE_SMC_V1@1.1.0 | WATCH | DEVELOPING |  | NOT_SENT_ARCHIVE_ONLY | ST_LARGE_SMC_V1\|1.1.0\|BTCUSD\|LSMC_WATCH-507b4736d90781236c67d6f6\|2026-10-10 |
| 2026-10-10T21:02:05.780600+00:00 | 2026-10-11T03:32:05.780600+06:30 | ETHUSDT | ST_LIQUIDITY_SWEEP_RETEST_V1@2.0.0 | WATCH | WATCH | NO_QUALIFIED_SWEEP_YET | NOT_SENT_ARCHIVE_ONLY | ST_LIQUIDITY_SWEEP_RETEST_V1\|2.0.0\|ETHUSDT\|DAILY_WINDOW\|2026-10-09 |
| 2026-10-10T21:02:05.780600+00:00 | 2026-10-11T03:32:05.780600+06:30 | BTCUSDT | ST_LIQUIDITY_SWEEP_RETEST_V1@2.0.0 | WATCH | WATCH | NO_QUALIFIED_SWEEP_YET | NOT_SENT_ARCHIVE_ONLY | ST_LIQUIDITY_SWEEP_RETEST_V1\|2.0.0\|BTCUSDT\|DAILY_WINDOW\|2026-10-09 |
| 2026-10-10T21:03:04.165347+00:00 | 2026-10-11T03:33:04.165347+06:30 | ETHUSD | ST_LARGE_SMC_V1@1.1.0 | WATCH | NEAR_POI |  | NOT_SENT_ARCHIVE_ONLY | ST_LARGE_SMC_V1\|1.1.0\|ETHUSD\|LSMC_WATCH-3de4a5a872c31bbe7e564523\|2026-10-11 |
| 2026-10-10T21:03:04.165347+00:00 | 2026-10-11T03:33:04.165347+06:30 | BTCUSD | ST_LARGE_SMC_V1@1.1.0 | WATCH | NEAR_POI |  | NOT_SENT_ARCHIVE_ONLY | ST_LARGE_SMC_V1\|1.1.0\|BTCUSD\|LSMC_WATCH-b9048c7b73d31bd1b905fa9e\|2026-10-11 |
| 2026-10-10T21:08:03.457891+00:00 | 2026-10-11T03:38:03.457891+06:30 | BTCUSD | ST_LARGE_SMC_V1@1.1.0 | WATCH | DEVELOPING |  | NOT_SENT_ARCHIVE_ONLY | ST_LARGE_SMC_V1\|1.1.0\|BTCUSD\|LSMC_WATCH-29153c3de2f9cdc2697053e7\|2026-10-11 |
| 2026-10-10T21:13:03.192386+00:00 | 2026-10-11T03:43:03.192386+06:30 | BTCUSD | ST_LARGE_SMC_V1@1.1.0 | WATCH | NEAR_POI |  | NOT_SENT_ARCHIVE_ONLY | ST_LARGE_SMC_V1\|1.1.0\|BTCUSD\|LSMC_WATCH-d1aba3f450ab73cfd623ec01\|2026-10-11 |
| 2026-10-10T21:23:05.415381+00:00 | 2026-10-11T03:53:05.415381+06:30 | BTCUSD | ST_LARGE_SMC_V1@1.1.0 | WATCH | DEVELOPING |  | NOT_SENT_ARCHIVE_ONLY | ST_LARGE_SMC_V1\|1.1.0\|BTCUSD\|LSMC_WATCH-97746f07ba2a2bddd77aba0e\|2026-10-11 |
| 2026-10-10T22:13:06.271404+00:00 | 2026-10-11T04:43:06.271404+06:30 | BTCUSD | ST_LARGE_SMC_V1@1.1.0 | WATCH | NEAR_POI |  | NOT_SENT_ARCHIVE_ONLY | ST_LARGE_SMC_V1\|1.1.0\|BTCUSD\|LSMC_WATCH-04582e93bfeeaed96e56841d\|2026-10-11 |
| 2026-10-10T22:33:09.978323+00:00 | 2026-10-11T05:03:09.978323+06:30 | BTCUSD | ST_LARGE_SMC_V1@1.1.0 | WATCH | DEVELOPING |  | NOT_SENT_ARCHIVE_ONLY | ST_LARGE_SMC_V1\|1.1.0\|BTCUSD\|LSMC_WATCH-056fd162e054c66e8254e006\|2026-10-11 |
| 2026-10-10T22:53:03.972551+00:00 | 2026-10-11T05:23:03.972551+06:30 | BTCUSD | ST_LARGE_SMC_V1@1.1.0 | WATCH | NEAR_POI |  | NOT_SENT_ARCHIVE_ONLY | ST_LARGE_SMC_V1\|1.1.0\|BTCUSD\|LSMC_WATCH-321f79f819fc72796196242a\|2026-10-11 |
| 2026-10-10T22:58:05.390523+00:00 | 2026-10-11T05:28:05.390523+06:30 | BTCUSD | ST_LARGE_SMC_V1@1.1.0 | WATCH | DEVELOPING |  | NOT_SENT_ARCHIVE_ONLY | ST_LARGE_SMC_V1\|1.1.0\|BTCUSD\|LSMC_WATCH-a838103b9cec98a5d6c844eb\|2026-10-11 |
| 2026-10-10T23:03:03.803056+00:00 | 2026-10-11T05:33:03.803056+06:30 | ETHUSD | ST_LARGE_SMC_V1@1.1.0 | NO_TRADE | REJECTED | REJECT_NO_STOP;D30_BADGE_ECONOMICS_NOT_EVALUATED | NOT_SENT_ARCHIVE_ONLY | ST_LARGE_SMC_V1\|1.1.0\|ETHUSD\|LSMC_WATCH-c8c8a3d02bfbfdf147913ee4\|2026-10-11 |

## Historical verification

Every recovered record is `VERIFICATION_AT_GENERATION=UNKNOWN` at the exact runtime-record level. The LSMC v1.1.0 verification report dated Oct 9 records version-level `LOGIC_VERIFIED` on fixture cases, but archived host rows do not bind their runtime code SHA to that verification identity. No exact contemporaneous v1.1.1 verification record was found for ASW. No current registry status was used to backfill history.

## Telegram and order reconciliation

The in-window archive records are `ARCHIVE_ONLY`; the host Telegram log contains no send during the target UTC interval. No ticket-linked delivery record or duplicate-suppression event was found. The current canonical ticket store has no `order_events` cohort, so no audited ticket can be tied to a demo order. Separate host evidence (`status/evidence/host_s1_contain_2026-10-11.json`) describes owner-placed manual SMC SHORT IOC orders and SL fills during Oct 10/11; it does not link them to these ticket IDs and they are not counted as system-submitted orders.

## Evidence coverage and limitations

- Deployed host path was identified from the Oct 14 acceptance record and inspected read-only: `<HOST_SCRATCHPAD>/journal/ticket_store` and `<HOST_SCRATCHPAD>/journal/ticket_delivery/archive/fx_ticket_archive`.
- The canonical ticket store has only `evaluations/2026-10-11.jsonl` through `2026-10-14.jsonl`; no Oct 10 evaluation cohort exists there. `index.sqlite` is missing. `scripts/ticket_history.py query` requires that index, so it was not run. Reindexing was skipped because it writes the store and direct archives were available.
- The archive search scanned 1516 base JSON records; 10 were in the MMT interval and 14 fell on UTC Oct 10 outside the MMT interval. No in-window correction wrappers were found.
- Host logs inspected: `ag_v1_lsmc.log`, `ag_v1_lsmc-weekend.log`, `ag_v1_crypto.log`, `ag_v1_fx.log`, and `telegram.log`. The logs support the log-only LSMC observations but do not provide stable evaluation IDs.
- Original host paths are redacted to `<HOST_SCRATCHPAD>` in this report. Local contemporaneous verification reference: `docs/status/AGP_C1_LSMC_V110_LOGIC_VERIFICATION_2026-10-09.md`.
- This is **partial history**: the canonical ticket store starts after the target date, Telegram evidence is log-only for the period, and log-only state checks lack ticket IDs. The recovered archive files are immutable historical reports, not an exhaustive per-cycle evaluation ledger.

## Recommended next action

If a complete audit is required, export the dated host archive, raw scheduler logs, and delivery database/journal for Oct 9–10 with event timestamps and IDs. Keep the ten log-only states unpromoted unless original ticket records are recovered.
