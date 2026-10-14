# AGP-S1-DEMO-READINESS-HOST-R1 — S1 demo readiness (2026-10-14)

Scope: `ST_ASIAN_SWEEP_5R_V1@1.1.2` GBPUSD × ASIAN_LONDON only.

**Verdict: BLOCKED.**
- Gate 2 passes from read-only and identity evidence.
- Gates 3 and 4 were not started: the host resource gate failed, so `FULL_WORKLOAD_STARTED = FALSE`.

No MT5 call was made by this mission: no `order_check`, no `order_send`, zero broker mutation.
`enabled: false` is unchanged.

## Gate 1 — resources (precondition)

| Item | Value |
|---|---|
| `resource_guard status` (07:21Z) | `AVAILABLE_RAM_MB = 950`, `R1_GATE = BLOCKED_RESOURCE` (needs 1200), `LOCK_STATUS = NO_LOCK` |
| Effect | Gate 3 `LOCAL_LIVE_DATA_ACCEPTANCE` and every Gate 4 block-path run need R1, so they are **NOT_RUN** |

## Gate 2 — identity, symbol, session, READY: PASS

| Check | Result |
|---|---|
| Host tree | `D:\wp3-main-integ` at `50bd6db`. `origin/main` is now `2112b8c`; between them, S1 surfaces (contract, registry, `demo_execution_s1.yaml`, `src/v1_tickets`) differ only by a new, unrelated `lsmc_v113_logic_gate.py` |
| Raw contract SHA256 vs OD1012-S1-READY | `4f936bbe17f4aa4fd3cd9fc85640bed57b6786f43c52e8e2d69aabb7234b14cf`, **match** |
| Registry scope S1 identity | `logic_identity()` recomputed at `50bd6db`: digest `d7a8ebe5…`, contract `941dec55…`, engine `243c4ff1…`, **all match** |
| Runtime binding | Host evaluations at 07:01Z and 07:16Z ran `ST_ASIAN_SWEEP_5R_V1@1.1.2`, `code_sha 50bd6db` |
| VT symbol map | GBPUSD → `GBPUSD-VIP`, VTMarkets-Demo, point `1e-05`, digits 5 (`config/symbol_metadata/host_captured/GBPUSD.json`, captured 2026-09-30) |
| Session / DST | `config/canonical_sessions.yaml`: `dst_policy: fixed_utc`, half-open. Asian reference 00:00–06:00Z; S1 trade session (London_Open) 07:00–11:00Z. The host's first in-window cycle was 07:01Z |
| DST note | UTC windows do not shift. The broker day (server midnight = 17:00 New York) moves by 1 h at the US change on 2026-11-01; UK clocks change 2026-10-25. This matters for any daily-reset rule (owner item 1) |
| READY resolution | `resolve_ticket_scope` → `LOGIC_VERIFIED` (`DEMO_AUTHORIZATION_ABSENT`). Registry `ticket_ready: PAUSED_PENDING_OWNER_CONFIRM`, reported as-is |
| Gates held | `config/demo_execution_s1.yaml` `enabled: false`, suffix `999`; `config/trading.yaml` `mode: ANALYSIS`, `allow_live_trading: false` |

**Observed today:** both AL cycles were BLOCKED `LOGIC_SCOPE_NOT_VERIFIED` with no priced plan.
The archived record does not keep the block `detail`, so it can't be determined whether this was the
identity path or the non-RANGE_SWEEP branch path in `src/v1_tickets/fx.py`. See
`AGP_OD1014_TG_ACCEPT_2026-10-14.md` §3.

## Gate 3 — terminal and live data: PARTIAL / NOT_RUN

| Check | Result |
|---|---|
| Terminal / server / suffix | Scheduled read-only runs log `server="VTMarkets-Demo" login_suffix="999"`, terminal `C:\Program Files\MetaTrader 5` (07:16:30Z FX run). This is evidence from scheduled runs, not this mission's acceptance run |
| trade_mode | **NOT_RUN** (not logged by scheduled runs; needs `account_info().trade_mode`) |
| Quote freshness | Scheduled LSMC runs at 07:03Z and 07:18Z log `data=FRESH` for all six symbols. No S1-specific quote check was run |
| `LOCAL_LIVE_DATA_ACCEPTANCE` in a real AL window | **NOT_RUN**: R1 blocked. The AL trade window is open until 11:00Z today; latest record `AGP_S1_LOCAL_ACCEPTANCE_R1_2026-10-12.md` = `S1_TEST_FIX_BLOCKED` |

## Gate 4 — guard block paths: NOT_RUN

Every guard below is **NOT_RUN** because the R1 resource gate failed. No guard is inferred to pass.

| Guard (synthetic input → expected block) | Result |
|---|---|
| Risk 0.5% per trade | NOT_RUN |
| 1 position per instrument | NOT_RUN |
| 5 trades per day | NOT_RUN |
| Daily loss 1% / 2% | NOT_RUN |
| Spread/cost 0.10R / 0.25R | NOT_RUN |
| Margin | NOT_RUN |
| Duplicate / idempotency | NOT_RUN |
| `mt5.order_check` dry-run | NOT_RUN (no MT5 order-path call made) |
| Reconciliation | NOT_RUN |
| Emergency stop | NOT_RUN |
| BLOCK_NEW_ORDERS on Telegram failure | NOT_RUN |

## Owner items (not decided here)

1. Confirm the daily-reset boundary, given the broker-day DST shift on 2026-11-01.
2. Lift READY from `PAUSED_PENDING_OWNER_CONFIRM` (OD1012-S1-READY).
3. A separate, revocable, strategy-specific standing DEMO authorization (`demo_authorized` is false).
4. Per-order confirmation policy under C14 for this scope.
5. Broker round-trip acceptance test (needs order authority; out of scope here).
6. Whether a BLOCKED S1 cycle must be delivered per cycle rather than `summary_only`, and whether to persist the block `detail`.

## Resume

When `resource_guard` R1 passes inside an AL trade window (07:00–11:00Z), run the following in this
order, each under an R1 lock:
1. Gate 3: `scripts/host/s1_readonly_acceptance.py` (read-only).
2. Gate 4: the guard block-path tests.

Record each gate as PASS or FAIL with its evidence.


## Status since this record (as of merge)

Append-only update, 2026-10-14, `CODEX-AGP-PR219-FIX-R1`; integrated main
`8416817f972d4238674742b26c56c2fc9caac98e`. The dated findings above are retained.
The verdict remains **BLOCKED**, with no host acceptance or order authority granted.

- **#220 merged:** distinct S1 block reasons and no summary-only S1 cycle address
  the recorded 07:01Z/07:16Z observation. This is a code correction, not evidence
  that those historical deliveries occurred or that a host re-run passed.
- **A' N-scope admission boundary merged** in #220; historical scope findings above
  remain attributed to their original baseline.
- **B1 canonical adapter = #225 (merged, inert).** Gate 4 re-run must target
  `guarded_adapter -> mt5_canonical_adapter`, not the previous adapter path.
  The adapter's existence does not authorize an order or establish host acceptance.
- **Runtime risk snapshot builder: MISSING.** `admission.py:319` consumes a supplied
  snapshot; `scripts/host/s1_readonly_acceptance.py:56` passes `None`. Gate 4 must
  include the builder once D' lands; an unwired date helper is not that builder.
- **Host RAM gate: 1200 MB** remains the Gate 3–4 blocker. Managed-sandbox tests
  do not satisfy the host RAM gate, clock/data checks or host acceptance.

No dated finding above is rewritten. No engine, contract, registry, READY, flag,
schedule, runtime code, broker or Telegram operation changes in this update.
Validation is reported on this PR's exact head; unrun host gates remain NOT_RUN.

Validation of this appendix (managed Linux sandbox, 2026-10-14): `python -m pytest -q
 tests/test_docs_live.py tests/test_context_pack.py tests/test_generated_files_ci.py`:
**37 passed in 34.31s**; R1 lock acquired and released. Documentation generators plus
`python scripts/docs/check_drift.py`: **zero blocking errors**, four existing
allowlist advisories. Untouched generated outputs follow normal regeneration.
Original dated findings remain a byte-identical prefix. Host Gates 3–4 remain
NOT_RUN/BLOCKED; exact-head PR CI must pass before handoff.
