# AG V1 — LSMC actionability P0/P1 (AG_V1_ACTIONABILITY_P0_P1_R1, 2026-10-07)

Authority: `docs/governance/OWNER_DECISIONS_2026-10-07_LSMC_ACTIONABILITY_V1.md` (canonical, on PR #48 as
256774e, SHA-256 `67bb1a57a7bc38335fdb18d7bdf7880c39331247a44abbc473e35cf1eecb7b56`).
Branch `feat/ag-v1-host-hardening-r1` (draft PR #49, base `audit/v1-followup-2026-10-07` = PR #48).
Separations: IMPLEMENTED ≠ VALIDATED ≠ AUTHORIZED. Unit-tested in CI only; **not deployed to the live
host and not live-verified.** No order path, Demo or strategy rule/threshold/YAML change.

## Implemented

| Item | Where | Notes |
|---|---|---|
| Policy config | `config/lsmc_actionability_policy_v1.yaml` | `LSMC_ACTIONABILITY_POLICY_V1` v1: `min_remaining_r 1.5`, `freshness_max_bars 2`, `trigger_timeframe M5`. Missing/invalid → INFO_ONLY(`POLICY_UNAVAILABLE`). |
| D1/D2/D4 gate | `src/host_delivery/lsmc_actionability.py` | States PENDING_BAR_CLOSE/FRESH/STALE/EXPIRED/MISSED_DOWNTIME → WATCH_READY / INFO_ONLY_STALE / INFO_ONLY(reason) / EXPIRED (not sent) / MISSED_NOT_ACTIONABLE. |
| Persistence | `journal/large_smc_watch/actionability/<date>.jsonl` | reference_price, send_price, send_price_side, trigger_bar_close_ts, send_ts, R_AT_TRIGGER, R_AT_SEND, policy version, confirmation key. |
| D3 digest | runner + `missed_digests.json`, `heartbeat.json` | At most one MISSED - NOT ACTIONABLE digest per run; items never re-digested; a digested confirmation is never re-sent individually. |
| D4 FX | `src/v1_tickets/guards.py`, `fx.py` | entry_1 with the first trade-session bar unclosed → `PENDING_BAR_CLOSE`/`SIGNAL_BAR_NOT_CLOSED` (was STALE; 07:01 case). Archives NO_TRADE; scan record WATCH. |
| T4 resolver | `src/host_delivery/lsmc_outcome.py` | Measurement only, `large_smc_watch/outcomes/<date>.jsonl`. |
| T5 D7 | `correlation()` | CORRELATED_EXPOSURE, CORRELATION_CLUSTER_ID, warning, informational rank. Never suppresses. Crypto UNCLASSIFIED (no owner mapping). |
| T6 | `_notify`, `AttemptJournal.record_host_attempt`, `OwnerCommandIdentity` | attempt_id + Telegram message_id on every attempted send; owner-command identity is a schema only (`execution_authorized` always False). |

Interpretations (owner to confirm): D1 FRESH iff age ≤ 2 × 5 min inclusive; R risk anchor = `stop_c10`
if present else `sweep_extreme`; send price LONG=ask / SHORT=bid; "downtime" = a stale trigger bar that
closed after the previous watch-run heartbeat; outcome target = touch.

## Verification

| Commit | CI run | Result |
|---|---|---|
| base 2fcdd18 (PR #48) | 37597366475 | 1067 passed, 4 skipped |
| a48e7a3 (P0) | 37610703517 | 1083 passed, 4 skipped (+16 new) |
| acfc25e (P1) | 37612106289 | 1090 passed, 4 skipped (+7 new) |

GitHub Actions `ubuntu-latest`, Python 3.12, `pytest -q`. Local runs not performed: resource guard
R1 BLOCKED (273–1038 MB available vs 1200 MB). Three existing LSMC runner tests now seed a
heartbeat (their fixture CHoCH is older than the D1 window).

## Host power (read-only, 2026-10-07T10:35:13Z, re-checked 11:11:20Z, unchanged)

`wake_armed`: HID-compliant mouse. Balanced (only scheme): AC sleep 0x4650 (300 min), AC hibernate
0x2a30 (180 min). The owner-reported mouse-wake disable and AC sleep/hibernate = 0 were **not in
effect** at that check. `/lastwake`: count 0. `/waketimers`: NOT_VERIFIED (needs elevation).

## Owner interpretations (2026-10-07, PR #49 review) — commit 30cc288, policy v2

| Item | Implemented as |
|---|---|
| a | Freshness = 2 x the strategy's trigger timeframe, derived per strategy (ST_LARGE_SMC_V1: M5 CHoCH bar). `trigger_timeframe` removed from config; unmapped strategy → INFO_ONLY(`TRIGGER_TIMEFRAME_UNKNOWN`). |
| b | Risk anchor C10 stop else sweep extreme, persisted with `risk_anchor_status = PROVISIONAL_PENDING_LSMC_SPEC_V1_FROZEN`. |
| c | LONG=ask / SHORT=bid; missing quote → INFO_ONLY(`NO_LIVE_QUOTE`). |
| d | Downtime = heartbeat gap > 2 x `watch_poll_interval_minutes` (5) at run start; stale trigger inside the gap → MISSED_DOWNTIME; stale while up → INFO_ONLY_STALE. |
| e | SUPERSEDED by Arena's LSMC spec — not implemented (awaiting v1.0.1 hash). |
| f | Warn-only `CRYPTO_DIRECTIONAL_<dir>` cluster for BTC/ETH in the same direction. |

Keep-awake (commit ab150d4): `SetThreadExecutionState(ES_CONTINUOUS|ES_SYSTEM_REQUIRED)` held only
for active runs (lsmc, crypto, in-window fx, in-window lsmc-weekend), released after every run.
Idle sleep only; the explicit AG-Sleep-Night suspend is not opposed (Windows documentation; NOT
live-verified). CI run 37618702494: **1099 passed, 4 skipped**.

Existing-test changes: two LSMC runner tests in `tests/test_host_go_live_kit.py` gained a heartbeat
seed (setup) and one added assertion; no assertion was removed or weakened.

## Not done / open

- Decision-record conflict RESOLVED: PR #48 carries the canonical 94-line record (256774e, blob
  identical to the owner-supplied text); this branch was rebased onto it.
- Not deployed to the live host; not live-verified.
- D6 (ST_ASIAN_SWEEP_5R_V1 READY OFF) is handled separately in PR #50 (deployed 2026-10-07 11:34Z).
