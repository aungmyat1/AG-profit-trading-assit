# AG V1 — LSMC actionability P0/P1 (AG_V1_ACTIONABILITY_P0_P1_R1, 2026-10-07)

Authority: `docs/governance/OWNER_DECISIONS_2026-10-07_LSMC_ACTIONABILITY_V1.md` (committed unchanged
as f4ec100, SHA-256 `67bb1a57a7bc38335fdb18d7bdf7880c39331247a44abbc473e35cf1eecb7b56`).
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

## Not done / open

- MT5 BTCUSD/ETHUSD history + symbol_info data pack: NOT_STARTED (resource guard < 1200 MB).
- Two different signed versions of the decision record exist: 00caa9c on PR #48 (54 lines) and
  f4ec100 here (94 lines, includes "Canonical names"). Owner to choose; branches conflict on that file.
- D6: on the live host, `TICKET_READY` scope sent three ST_ASIAN_SWEEP_5R_V1 READY tickets at
  2026-10-07 07:16 UTC. D6 sets READY authority OFF; this PR does not change that path.
