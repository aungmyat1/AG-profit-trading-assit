# AGP-OD1013-D2/D3 — host acceptance and deployment of `cc14adc` (2026-10-13)

Owner decision AGP-OD1013-D2/D3 (2026-10-13). Host: Windows MT5 host, live tree `D:/wp3-main-integ`,
VTMarkets-Demo `login_suffix=999`. No order authority was granted or used.

## Verdict: `HOST_PARTIAL`

Deployment and the first post-deploy cycles passed. The new ASW report-lane and TQ-D1 geometry
paths and the CCFD lane have not yet run in an open window on `cc14adc` (FX: NOTHING_IN_WINDOW;
crypto: AFTER_WINDOW). Pending: first Asian-London and crypto weekday windows on 2026-10-14.

## Heads

| Item | Value |
|---|---|
| Previous host HEAD (rollback point) | `6ebe5b9` |
| Deployed host HEAD | `cc14adc34056a431bdf755ee7b5d2fed04fb4eb3` (`git pull --ff-only origin main`, 16:38:34 UTC) |
| Delta | 6 commits (#193–#198), 36 files; no config / risk / registry / `ready_authority` change; v1.1.3 YAML comment-only; `demo_execution/admission.py` gains the stricter TQ-D1 geometry gate only |
| Rollback | not executed (no critical failure) |

## Baseline acceptance on `6ebe5b9` (log/journal window 00:00–16:20 UTC)

| Check | Result |
|---|---|
| MT5 read-only guard | 121 runs (fx 26, lsmc 84, crypto 11); all `COMPLETE`; prohibited order-API attempts 0; broker mutations forwarded 0; broker history `CLEAN` 121/121 |
| Account identity | every attached run since the 08:31 terminal pin: `VTMarkets-Demo` / `…999`; one `…985` at 08:17 UTC predates the pin |
| Telegram report lane | 126 RESULT events: 24 `sent` (msg 12749–12777), 102 `duplicate`, 0 `failed`, 0 `uncertain` |
| ASW Asian-London summary | `COMPLETE` 4/4, sent msg 12767 (11:31 UTC) |
| Crypto catch-up summaries 10/11/12 Oct | one INTENT + one RESULT each (once-only held) |
| Crypto CFD window 13:00–16:00 UTC | 11 of 12 runs, 22 observations, all `NO_OPPORTUNITY` (`NO_TRADE`), v1.0.0, `STALE_IDENTITY`; missing 14:02 slot = `TIMEOUT run exceeded 120s; self-exit` |
| LSMC attach failures | 2 (`MT5_INITIALIZE_FAILED -10005 IPC timeout`, 13:56 and 15:25 UTC); fail-closed, no report |
| S1 last decision | 11:16 UTC `INSUFFICIENT_DATA` / `QUOTE_INVALID_OR_STALE` (known host quote issue) |

## Preflight gates (16:35–16:38 UTC)

| Gate | Result |
|---|---|
| Host tree | `main`, HEAD `6ebe5b9`, 0 tracked changes; untracked `work/` (not ours) untouched |
| Target | `origin/main` = `cc14adc`, fast-forward |
| No active run | 0 `pythonw` processes |
| Resource | R0 PASS (deploy is R0); R1 was `BLOCKED_RESOURCE` at 515 MB available (15:2x UTC) |
| Flags | mode `ANALYSIS`; `allow_live_trading=false`; demo S1 `enabled=false`, `per_order_confirm_required=true` |
| Telegram scope | `TICKET_READY, LSMC_OPPORTUNITY, REPORT_CANDIDATE, REPORT_BLOCKED, REPORT_WATCH` |
| Terminal pin | user env `MT5_TERMINAL_PATH=C:\Program Files\MetaTrader 5\terminal64.exe` |

## Post-deploy verification

| Check | Result |
|---|---|
| Identities on `cc14adc` | S1 v1.1.2 `d7a8ebe5` (unchanged); CCFD v1.0.0 `7a0946e4` (unchanged); v1.1.3 `7e232429` (as recorded by #193; unregistered) |
| FX 16:46 / 17:03 | `NOTHING_IN_WINDOW`; guard COMPLETE, 0 prohibited; `…999` |
| Crypto 16:47 | `OUTSIDE_WINDOW (AFTER_WINDOW)`, no MT5 attach |
| LSMC 16:48 | guard clean, `…999`; BTCUSD/ETHUSD WATCH sent (msg 12779, 12780) |
| LSMC 17:03 | guard clean, `…999`; all six symbols `data=FRESH`; EURUSD and XAUUSD NEAR_POI WATCH sent; BTCUSD/ETHUSD not re-sent |
| Layout | archived 16:48 BTCUSD row re-rendered with the deployed renderer shows the owner layout (header, transition, MMT/UTC, `REPORT ONLY - NOT AN ORDER | EXECUTION: DISABLED`); re-render, not the transmitted bytes |

Observation: `cc14adc` changes the LSMC WATCH delivery identity from a per-day state key to a
per-setup key, so the first transition per setup after deploy is delivered once under the new key
(12779/12780 re-announce setups first reported 08:38–09:08 under the old key).

## Scheduler

- `AG-V1-LSMC-Watch` repetition changed `PT5M` -> `PT15M` on owner instruction (2026-10-13);
  StartBoundary `2026-10-01T00:03:00+06:30`, Mon–Fri, action unchanged. Installer aligned in PR #199.
- FX and crypto tasks unchanged (15 min). No scan-cadence change for crypto (deferred to OD1012,
  including the 2026-11-01 New York DST shift of the weekday window).

## Decision 2

`fix/crypto-ticket-window-v4` (`d576a2e`): no PR, no workflow reference, no worktree; its two unique
commits are the rejected v4 window change. Remote branch deleted; local ref kept as recovery.

## Remaining blockers

1. First in-window ASW and CCFD cycles on `cc14adc` (2026-10-14).
2. Host MT5 IPC timeouts and a 120 s run timeout under low available RAM.
3. Owner decisions TQ-D2 (LSMC transition reason) and TQ-D3 (C10 pip evidence) remain open.
