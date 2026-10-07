# AG V1 — first natural READY tickets: evidence pack and audit follow-up (2026-10-07)

Facts only. Runtime evidence commit: `fc60cdbf603146b1408dba9184e6c146bdcf4ea5` (runtime
`D:\wp3-main-integ`, `git status --porcelain` empty at 2026-10-07T08:17Z after the owner moved two
task-backup XMLs out of the tree). All times UTC unless marked MMT (UTC+6:30). Host paths are
written relative to the runtime root; host name and user are redacted.

Separations: DESIGN ≠ IMPLEMENTED ≠ VALIDATED ≠ AUTHORIZED. A paper-trade record is not demo
evidence. READY is a deterministic engine state, not evidence of edge. No broker action was taken.

## 1. WP7 evidence pack (plan: `docs/plans/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_DELIVERY_V1.md` WP7)

Strategy: `ST_ASIAN_SWEEP_5R_V1` v1.1.1; registry entry: `registered: true, active: true,
research: true, demo_authorized: false, live_authorized: false, ticket_authority: MANUAL_ONLY,
logic_status: NOT_VERIFIED, economic_status: NOT_EVALUATED, demo_order_authority: NONE`.
Scheduler: `AG-V1-FX-Cycles` → `.venv\Scripts\pythonw.exe scripts\host\live_candles_smoke.py --mode fx`.

| Logical ticket id | Archive record (READY) | Paper record | Delivery journal | Telegram log |
|---|---|---|---|---|
| `…\|EURUSD\|ASIAN_LONDON\|2026-10-07` | `journal/ticket_delivery/archive/fx_ticket_archive/ST_ASIAN_SWEEP_5R_V1/EURUSD/ASIAN_LONDON/2026/2026-10-07.correction-001.json` (eval 07:16:08.182) | `journal/paper_trades/ST_ASIAN_SWEEP_5R_V1/EURUSD/ASIAN_LONDON/2026/2026-10-07.json` (opened 07:16:08.182) | `delivery_status/2026-10-07.jsonl`: kind=TICKET value=READY status=SENT ref=`fx:EURUSD:ASIAN_LONDON:2026-10-07` code_sha=`fc60cdbf6031` | `07:16:14.896 TELEGRAM_SENT_OK TICKET=READY` |
| `…\|GBPUSD\|…` | `…/GBPUSD/…/2026-10-07.correction-001.json` | `…/GBPUSD/…/2026-10-07.json` | same, ref `fx:GBPUSD:…` | `07:16:19.047 TELEGRAM_SENT_OK TICKET=READY` |
| `…\|XAUUSD\|…` | `…/XAUUSD/…/2026-10-07.correction-001.json` | `…/XAUUSD/…/2026-10-07.json` | same, ref `fx:XAUUSD:…` | `07:16:25.565 TELEGRAM_SENT_OK TICKET=READY` |

FX log lines: `2026-10-07T07:16:25.56…+00:00 FX {EURUSD|GBPUSD|XAUUSD} (…-VIP) ASIAN_LONDON
data=FRESH decision=READY reason=BOX_DIRECTION_V1 spread_check=PASS metadata=HOST_CAPTURED paper=OPENED ARCHIVED`.

- Each ticket was SENT exactly once (no other TICKET/SENT rows for those refs on 2026-10-07).
- Symbol → Telegram line mapping is **INFERRED** from loop order (EURUSD, GBPUSD, USDJPY, XAUUSD);
  `telegram.log` does not record the symbol.
- **Attempt id: NOT_CAPTURED. Provider response identity (Telegram message_id): NOT_CAPTURED.
  Retry count: n/a.** The live path is `_notify()` in `scripts/host/live_candles_smoke.py`
  (best-effort single attempt). It is not the WP7 `deliver_informational_ticket_with_retry()` /
  `AttemptJournal` path. These WP7 fields cannot be verified from this delivery.
- WP7 scope note: the plan's in-scope pair is EURUSD/GBPUSD. XAUUSD was delivered by the V1 host
  path, which is outside that plan's scope.
- Execution unreachable:
  (a) `order_send|ORDER_SENT` lines dated 2026-10-06/07 across all `logs/*`: **0**.
  (b) Static AST import closure of `scripts/host/live_candles_smoke.py` (both `--mode fx` and
  `--mode lsmc`; function-local imports included): 100 repo modules, **none** under
  `src/execution/`, `src/trade_management/`, `mt5.management_gateway`, `*executor*` or
  `*mt5_gateway*`. Files containing the literal tokens `order_send`/`order_check` are docstrings
  (`_host_common.py`, `btc_sweep_research/pipeline.py`, `strategy_engine/__init__.py`) and the
  repo-root `MetaTrader5.py` fallback stub, which raises `MT5StubOperationAttempted`. There are no
  call sites. The real `MetaTrader5` package still exposes `order_send`; the guarantee is
  absence of call sites, enforced by `tests/test_host_go_live_kit.py`.

## 2. FX decision reconciliation (ASIAN_LONDON, 2026-10-07)

| Slot (UTC) | EURUSD | GBPUSD | USDJPY | XAUUSD |
|---|---|---|---|---|
| 07:01 | STALE / STALE_SIGNAL (suppressed READY) | STALE (suppr. READY) | NO_TRADE / NO_SETUP_BY_WINDOW_END | STALE (suppr. READY) |
| 07:16 | **READY** / BOX_DIRECTION_V1 | **READY** | NO_TRADE (not re-archived) | **READY** |
| 07:31 | STALE | STALE (spread_check=SPREAD_TOO_WIDE) | NO_TRADE (not re-archived) | STALE |
| 07:46 | STALE | STALE | **SPREAD_TOO_WIDE** (suppr. READY, LONG; spread 0.020 = 51% of 0.039 risk) | STALE |
| 08:01 | STALE | STALE (not re-archived) | STALE | STALE |
| 08:16 | STALE | STALE | STALE | STALE |

Counts over these 6 slots: READY 3, STALE 17, NO_TRADE 3, SPREAD_TOO_WIDE 1. The brief's
"3 slots / STALE 6" figure covered only 07:01–07:31.

- **07:01 STALE (defect, reported, not fixed).** The engine already returned SIGNAL (box-based
  entry_1, `signal_timestamp=null`). `src/v1_tickets/fx.py:162` falls back to the first
  trade-session bar's open. At 07:01 that bar (07:00–07:15) had not closed, so
  `post_session_candles` was empty, so `signal_close=None`. `guards.is_stale(None)` is `True`
  (`src/v1_tickets/guards.py:28`), so the result was STALE with `signal_close_utc=null`. At 07:16
  the same signal (same entry, stop and targets) got `signal_close=07:15` and became READY. It
  expired at 07:31 (07:15 + 15 min). This is case **(b)**: a signal labelled STALE was later
  promoted to READY. The cause is that an *unknown* signal close is labelled STALE; the signal was
  not past freshness. This is ticket-gate behaviour, not strategy logic. Any change to it changes
  decision output, so it is listed as an owner decision.
- **SPREAD_TOO_WIDE is also a decision**, not only a reason: `guards.gate_ready` returns
  decision `SPREAD_TOO_WIDE` when the signal is fresh and the spread exceeds 15% of the stop
  (`guards.py:63-64`). Stale wins over spread (`guards.py:61`), so GBPUSD 07:31 is decision STALE
  with `spread_check=SPREAD_TOO_WIDE`. Both archive as `cycle_state=NO_TRADE` (`fx.py:171`).
- **Archive vs. "exactly one archived decision per symbol/cycle/date":** the archive is base +
  append-only corrections (`post_asian_pilot/report_archive.py:52-83`). Files: EURUSD 1+5,
  GBPUSD 1+4, USDJPY 1+3, XAUUSD 1+5. No slot is missing. Decision-changing corrections: EURUSD
  c001/c002, GBPUSD c001/c002, XAUUSD c001/c002, USDJPY c001/c002. **Spread-only corrections
  (same decision, only `spread`/`evaluated_at` differ): EURUSD c003–c005, GBPUSD c003–c004,
  XAUUSD c003–c005, USDJPY c003 (9 records).** Cause: the runner's `_content_hash` excludes only
  `evaluated_at` (`live_candles_smoke.py:169-171`), so live spread drift creates a new
  correction. Reported, not changed.
- USDJPY 07:46 engine geometry (report only): LONG entry 158.298, stop 158.259, leg 1 (box)
  158.502 is **beyond** leg 2 (5R) 158.493.

## 3. Large-SMC duplicate and identity drift

- **GBPUSD (identical ref, sent 17:48:10 and 18:38:35 UTC).** Dedup is a state transition in
  `WatchTracker.poll` (`src/large_smc_watch/watch.py:279`). Nothing records that an alert was
  already sent. At 18:34:33 GBPUSD polled `data=STALE` right after the PC resumed from sleep
  (section 5), so the state was saved as `SUSPENDED` (`watch.py:261-264`). At 18:38 the same
  OPPORTUNITY/ref returned, and `SUSPENDED ≠ OPPORTUNITY` emitted a new transition, which was sent.
- **BTCUSDT (new ref, same CHoCH 17:50 bar).** This was not a repaint. `m5_opportunities`
  (`detect.py:160-192`) yields one candidate per sweep, and the 17:05 and 17:30 sweeps both pair
  with the 17:50 CHoCH. `evaluate_snapshot` keeps the **last** valid candidate
  (`watch.py:165-172`), which was 17:30. A later M5 close below the 17:30 sweep low invalidated
  that candidate (archived 18:53:07). The 17:05 candidate, which has a lower low, then became
  active: new ref, invalidation 85526.09, target 85809.26. The same fallback appears for XAUUSD
  01:48, USDJPY 03:58 and EURUSD 05:58 on 2026-10-06. Frozen detection: reported only.
- Large-SMC sends are **not journaled** (`_notify` is called without `journal`), so there is no
  delivery_status row and no price-at-send record.
- Fix (branch, delivery layer only): `src/host_delivery/lsmc_alert_dedup.py` keeps a persistent
  ledger keyed on strategy+version+symbol+direction+POI+CHoCH bar and records only `SENT`.
  Detection, transitions and archive records are unchanged.

## 4. Large-SMC alerts sent in the last 24 h (measured, not thresholds)

Latency = send − CHoCH bar close (open + 5 min). R_ref = |target − entry_ref| ÷ |invalidation − entry_ref|.

| Send (UTC) | Symbol | Dir | Latency (min) | Min to expires_at | R_ref | R remaining at send |
|---|---|---|---|---|---|---|
| 10-06 17:48:10 | GBPUSD | LONG | 3.2 | 191.8 | 1.08 | NOT_VERIFIED |
| 10-06 17:58:29 | BTCUSDT | LONG | 3.5 | 181.5 | 5.08 | NOT_VERIFIED |
| 10-06 17:58:37 | ETHUSDT | LONG | 3.6 | 181.4 | 0.18 | NOT_VERIFIED |
| 10-06 18:38:35 | GBPUSD (dup) | LONG | 53.6 | 141.4 | 0.45 | NOT_VERIFIED (owner: ~0.38) |
| 10-06 18:53:12 | BTCUSDT (re-anchor) | LONG | 58.2 | 126.8 | 0.38 | NOT_VERIFIED |
| 10-06 20:58:05 | USDJPY | SHORT | 3.1 | **1.9** | 0.42 | NOT_VERIFIED |
| 10-07 04:33:42 | EURUSD | SHORT | 18.7 | 86.3 | 2.57 | NOT_VERIFIED |
| 10-07 04:33:50 | XAUUSD | SHORT | **243.8** | 86.2 | 2.39 | NOT_VERIFIED (owner: ~82% to target) |

Sends are paired with archived transitions by run time (send within 120 s after evaluation;
BTC before ETH and EURUSD before XAUUSD by loop order: INFERRED). The price at send is not
persisted, so remaining R cannot be recomputed. Catch-up: `ticket_delivery.policy.CatchUpPolicy`
exists with `CATCH_UP_DURATION = UNSIGNED` and a fail-closed default, but the Large-SMC host path
does not use it. The first run after the 04:27 boot alerted on a 00:25 CHoCH.

## 5. Overnight power (2026-10-06/07)

`AG-Sleep-Night` (00:45 MMT, `rundll32 powrprof.dll,SetSuspendState 0,1,0`, WakeToRun=False):

- 18:15:08 entered sleep (Kernel-Power 42, "Application API"), so **the sleep ran and succeeded**.
- Resumed about 18:34:15 (Kernel-Power 107; clock resync 18:15:11 → 18:34:15). **Wake source:
  NOT_VERIFIED**: `powercfg /lastwake` shows count 0 after the later reboot, and `/waketimers` and
  `/requests` need elevation (not run).
- 18:35:11 and 18:36:16: sleep "Button or Lid", each resumed within about 3 s.
- Awake 18:34–23:06; this covers the alerts at 01:08, 01:23 and 03:28 MMT.
- 23:06:23: User32 1074, power off initiated by `RuntimeBroker.exe` on behalf of the interactive
  user ("Other (Unplanned)"). This is consistent with a Start-menu power-off.
- OS started 04:27:04 (10:57 MMT). FX lines from 04:31.

Wake-armed devices: `HID-compliant mouse`. "Allow wake timers" on AC is 1 (enabled).
Recommendations (not applied):

- Run `powercfg /waketimers` and `/requests` elevated before 00:45 MMT.
- Disarm the mouse: `powercfg /devicedisablewake "HID-compliant mouse"`.
- Review the AC wake-timers policy against the WakeToRun tasks (`AG-Wake-MT5`, `AG-Wake-Weekend-Crypto`).

## 6. Manual ticket / scan-record writes

`journal/ticket_delivery/manual/tickets/2026-10-07.jsonl` (30 rows) and
`manual/scan_records/2026-10-07.jsonl` (64 rows) are appended by `AG-V1-FX-Cycles`
(`run_fx` → `manual_ticket.archive_manual_ticket`, `live_candles_smoke.py:337`;
`write_scan_record` via `_scan_fx`) on every FX run from 07:01:05. Ticket states: 29
TICKET_BLOCKED, 1 WATCH, **0 READY**. At 07:16 the three legacy READY signals were
TICKET_BLOCKED (`LOGIC_GATE_FAIL:L2`, `L3`, `RISK_CONFIG_MISSING`). These are Manual Trade
Ticket V1 records and **must not be counted as automatic READY tickets**.

## 7. Precision and formatting

- EURUSD: engine `risk_distance` 0.001355 (off-tick). Entry, stop and targets are rounded
  separately after tp2 is computed from the raw values (`fx.py:153-158`). The renderer printed the
  raw risk ("13.5 pips") next to levels 13.6 pips apart. Branch fix (display only): levels are
  normalized to the capture `trade_tick_size`, stop rounds away from entry and targets toward it,
  and R is computed from displayed levels with the engine risk shown. Missing or coarse metadata
  renders raw levels marked `(unnormalized: no symbol metadata)`.
- **Finding, not fixed:** engine and proposal levels are off-tick. Paper-trade records keep the raw
  values (`risk_distance` 0.001354999…), and the display now shows normalized values.
- Large-SMC raw floats (`1.3247499999999999`) are now printed at symbol digits (same normalizer).
- `stop (C10)` appears only for EURUSD/GBPUSD because `C10_PIP_SIZE` is evidenced only for those
  (`src/large_smc_watch/contract.py:61`). Other symbols carry `stop_reason=C10_PIP_SIZE_NOT_EVIDENCED`.
  Adding it elsewhere would be a schema/contract change.
- `.gitignore` (preflight): the `check-ignore -v` output was `.gitignore:45:<TAB>artifacts/task-backup/`,
  meaning an **empty pattern** on blank line 45, matched only for the trailing-slash query.
  `check-ignore` on the file paths exits 1, there is no `task-backup` rule, and core.excludesFile
  is unset. The files were genuinely untracked; there is no `.gitignore` defect.

## 8. Friction samples observed 2026-10-07 07:16 (measured, not thresholds)

EURUSD spread 1.5 pips = 11.1% of risk; GBPUSD 1.4 pips = 12.2%; XAUUSD 0.27 = 1.3%.
