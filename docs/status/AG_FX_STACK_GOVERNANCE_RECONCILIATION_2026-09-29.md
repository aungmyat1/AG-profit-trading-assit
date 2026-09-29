# AG FX Stack — Governance Reconciliation (2026-09-29)

**Classification:** `FX_STACK_INTEGRATION_BLOCKED`

Mission: reconcile repo truth with the independently audited FX stack, integrate it
A→E→B→F→C→D→G, then start prospective EURUSD POST_ASIAN operation. The governance
record is complete. Integration stopped at the ordered gates below. Nothing was merged
to main and nothing was pushed. Prospective operation did not start.

Environment: Windows 10 host, repo `origin/main` = `accf063754b93676e34860dc16ad6b7fcc8e7b10`
(unchanged), MT5 terminal build 6230 on `VTMarkets-Demo`.

## 1. Governance record (Phase 1)

Done in a separate `AUDIT_RECORD_COMMIT` (`0f7021ba`) ahead of any integration:
[`../audit/AG_FX_STACK_AUDIT_RECORD_2026-09-29.md`](../audit/AG_FX_STACK_AUDIT_RECORD_2026-09-29.md).
Five auditor reports copied byte-exact; blob equality verified against the auditor commits.

## 2. Ordered gates

| Gate | Result |
|---|---|
| Lineage A→E→B→F→C→D→G linear (plus `9b185e7` between C/D, `5fc8d1f` between D/G) | PASS |
| Phase 4 main-protection tripwire present on main | **FAIL — absent.** Bounded tripwire built on `ci/main-protection-tripwire-v1` (`37141911`), UNAUDITED, not on main |
| Phase 5 per-unit audit PASS in repo truth: A, E, B | Recorded (A8, PASS_WITH_CAVEATS; bounded-PR merge required) |
| Phase 5 per-unit audit PASS in repo truth: F `76348c7` | **FAIL — no independent audit exists** for delta `6fdc921a..76348c7` (2 commits, 6 files; A8 excluded Collector V2) |
| Phase 5 audit PASS: C, D, G | Recorded, but merge order puts them after F |
| Merges | `NOT_EVALUATED` (not performed) |
| Phase 8 baseline freeze | `NOT_EVALUATED` |
| Phase 9/10 prospective EURUSD POST_ASIAN | `NOT_EVALUATED` — requires the frozen integrated baseline |

### Mechanical merge readiness (informational, throwaway worktree only)

A sequential `--no-ff` dry-run of the original SHAs onto `origin/main` conflicted only in
`PROJECT_STATUS.md` at A; E, B, F, C, D and G merged cleanly with no runtime-path
conflicts. The dry-run commits were never published. The tripwire evaluated
`origin/main..4b450ff` as PASS (2 deletions, 0 protected). Replayed against the
historical wipe `3f1f955`, it TRIPPED (1031 deletions, 2 protected paths).

## 3. Tripwire (Phase 4, bounded prerequisite)

`scripts/governance/main_protection_tripwire.py` + `.github/workflows/main-protection-tripwire.yml`
+ policy `config/governance/main_protection_tripwire.json`. The check fails a PR or push
to main that deletes > 50 files or > 5 % of tracked files, or that deletes or renames
away a protected path present at base. Protected paths: `AGENTS.md`, `config/trading.yaml`,
the strategy registry and ledger, `config/governance/`, `src/trade_ticket/`,
`src/instrument_registry/`, `config/instruments/registry/`, the identity-gated runner,
their focused tests, and the tripwire itself. Policy is read from the base revision.
An unknown or null base fails closed. Test:
`python -m pytest -q tests/test_main_protection_tripwire.py` → 9 passed.
Needs an independent audit and a PR to main.

## 4. Proposal foundation on main (Phase 6)

`0f149c5` (on main, reached via PR #10/#12 ancestry) self-declares
`UNAUDITED_RECOVERY_CANDIDATE`; no independent recovery audit exists in any ref.
Builder-side bounded inspection only (not an independent audit): 16 files, data-only.
It has no execution/MT5/order imports, and `execution_authority` is always `AUTHORITY_NONE`.
Its five focused test files pass on `origin/main`: 75 passed.

`PROPOSAL_FOUNDATION_AUDIT = PASS (builder inspection; independent audit still owed)`.
No owner disposition (revert/remediate) is required by this inspection. A→G is not
invalidated. No history was rewritten.

## 5. Authority (Phase 7)

No authority commit was made. `ST_ASIAN_SWEEP_5R_V1` proposal authority = **NONE**
(unchanged). No registry fingerprint changed.

## 6. trade_mode snapshot (Phase 15, diagnostic only)

Artifact: `artifacts/validation/VT_TRADE_MODE_DIAGNOSTIC/VT_EURUSD_TRADE_MODE_SNAPSHOT_2026-09-29T1553Z.json`.
Calls: `initialize`, `terminal_info`, `account_info`, `symbol_info` ×2, `shutdown`.
There were no `order_check`, `order_send` or `symbol_select` calls, and nothing was
mutated.

| | Account | `EURUSD` | `EURUSD-VIP` |
|---|---|---|---|
| server | `VTMarkets-Demo` | | |
| trade_mode | `0` = **DEMO** (account enum) | `0` = **DISABLED** (symbol enum) | `4` = FULL |
| execution / filling | | exemode 2 (MARKET) / filling 2 (IOC) | exemode 2 / filling 2 |
| visible in Market Watch | | yes | no |

The ambiguity is that `trade_mode = 0` means DEMO on the account enum and DISABLED on
the symbol enum. On the symbol, VT Markets Demo disables trading on plain `EURUSD`, while
`EURUSD-VIP` is FULL. Quotes still flow on `EURUSD`, so read-only Opportunity operation
is not blocked. This is not execution permission. Backlog only.

## 7. Economic track (Phases 12–13)

- **MEASURED:** the WP3A.1 EURUSD friction campaign (VT Markets spread observations)
  holds complete 4-window days for 2026-09-17, 18, 21, 22, 23 and 29, plus partial days
  2026-09-24 and 09-28 (1 window each). 2026-09-29 medians are 0.0–0.1 pip and p95 is
  0.1–0.3 pip, 120 samples per window with 0 missing. The campaign runs through 2026-09-30.
- **UNKNOWN:** commission and realized slippage.
- **DERIVED:** `SPREAD_TO_DEV_STOP_R_SCREEN` = `NOT_COMPUTED` (no implementation in any ref).
- No strategy authority follows from spread evidence. SEALED_OOS was not opened.

## 8. Safety counters

`BROKER_ORDER_CHECK_CALLS = 0`, `BROKER_ORDER_SEND_CALLS = 0`, `OTHER_EXECUTION_MUTATIONS = 0`.

## 9. Next smallest mission

Obtain an independent audit of Unit F: the delta `6fdc921a..76348c7` (2 commits, 6 files: `50460cc` session-gated VT spread collector V2 + `76348c7` status), since A8 covered everything up to `6fdc921a` and
an independent audit of the tripwire (`37141911`). Then land the tripwire on main by PR.
Then integrate A→G as a bounded PR, per A8 caveat 3.
