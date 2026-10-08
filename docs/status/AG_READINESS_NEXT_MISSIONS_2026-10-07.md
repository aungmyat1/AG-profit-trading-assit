# AG Readiness — Next Mission Queue (R3)

Ranked from already-evidenced blockers only (T1–T6); no new implementation work invented.

| PRIORITY | MISSION | INPUT | BLOCKER_REMOVED | OWNER_DECISION_REQUIRED |
|---|---|---|---|---|
| P0 | Asian Sweep R4B isolated blind logic verification | PR #45 `AG_ASIAN_SWEEP_V1_2_BLIND_HANDOFF_001` package (`PACKAGE_SHA256=cfc8309d...`) | Resolves `blind_reference_isolation=BLOCKED_SEPARATE_AGENT_CONTEXT_UNAVAILABLE`; unblocks `CUTOVER_READY` evaluation | None to start (mechanical); owner decides if/when to act on a pass/fail result |
| P0 | Crypto venue/data decision | `docs/decisions/D_CRYPTO_VENUE.md` | Unblocks the entire T4 dependency chain (historical-data acquisition cannot be targeted correctly without this) | YES — D_CRYPTO_VENUE |
| P0 | LSMC signed-rule / blind-verification apparatus closure | `docs/plans/AG_LSMC_LOGIC_VERIFICATION_LANE.md` | Produces the first `LOGIC_VERIFIED` path for `ST_LARGE_SMC_V1` (neither 1.0.7 nor 1.1.0 has one today) | YES — D_LSMC_LANE (joint vs separate lanes) |
| P1 | Crypto historical-data acquisition | Output of the P0 venue decision | Removes `HOST_DATA_NOT_VERIFIED` for BTCUSD/ETHUSD (or the exchange-venue equivalent) | No (follows from venue decision) |
| P1 | MTF sample-adequacy experiment | `docs/plans/AG_MTF_CONTROL_SHIFT_SAMPLE_ADEQUACY_R1.md`, same prereg identity or a new campaign | Resolves `ST_MTF_CONTROL_SHIFT_V1`'s `HOLD_SAMPLE_REQUIRED` into one of A–F | No (diagnostic only; new PREREG_ID if scope changes) |
| P1 | Telegram host acceptance re-verification | `src/host_delivery/`, `src/ticket_delivery/` | Resolves `NOT_VERIFIED` host/connectivity cells in T2's matrix | No |
| P2 | Demo execution qualification | `docs/decisions/D_EXEC_DEMO.md` checklist | N/A until P0/P1 above close — every checklist item is currently unmet | YES — D_EXEC_DEMO (and D_ASIAN_TICKETS_WHILE_NEGATIVE if Asian Sweep is in scope) |

Ordering follows the evidence found this mission (no `LOGIC_VERIFIED` exists anywhere;
Asian Sweep is closest to a verification apparatus, LSMC has none, crypto is blocked
upstream at the venue decision). The owner may reorder.
