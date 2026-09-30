# AG V1 — Two Goals: Owner Decisions

- Recorded: 2026-09-29 (owner authorization dated 2026-09-30, mission AG-V1-CLOUD)
- Scope: the code-only (cloud) part of "AG V1 - Two Goals"
- Branch: `v1/two-goals-cloud` (cut from `origin/main` @ `ce09e8d`); main is never pushed or merged by this mission
- Authority: this is a governance record. It does not authorize trading, change a safety gate,
  or promote a strategy. The registry, the strategy contracts, and `config/trading.yaml`
  stay authoritative for runtime behavior.

## Decisions

| ID | Decision |
|----|----------|
| D1 | V1 means two goals. **Goal 1** is informational session tickets: EURUSD, GBPUSD, USDJPY and XAUUSD for Asian→London and London→NY; BTCUSDT and ETHUSDT in the frozen daily window. **Goal 2** is Large-SMC watch/alerts for the same instruments. Tickets need **logical** verification only, not R6. Demo and live are out of scope. |
| D2 | Telegram is **DEFERRED**. Do not change the ticket-delivery `mode` or transport. |
| D3 | `SESSION_TRADE_V1` `demo_authorized` = **false**. Update tests that assert the old value. |
| D4 | FX/gold use `ST_ASIAN_SWEEP_5R_V1@1.1.1` exactly as frozen. If the frozen config has no London→NY window, report that; do not invent one. Crypto uses `ST_LIQUIDITY_SWEEP_RETEST_V1@2.0.0` `CRYPTO_PERP`, with ETHUSDT as a new symbol profile on the same engine at status `SHADOW`. Large-SMC is `ST_LARGE_SMC_V1@1.1.0`, a new version; `v1.0.7` is preserved unchanged. |
| D5 | Crypto data: Bybit public is primary, Binance public is the fallback, and the source is printed on every ticket. |
| D6 | Large-SMC produces alerts only; `proposal_generation_authorized=false`. |
| D8 | Do not wait for missing audits. Do not merge unaudited branches. |

(D7 was not issued in the mission text.)

## ST_LARGE_SMC_V1@1.1.0 — rules as stated by the owner

Source of the option catalogue: `docs/specs/ST_LARGE_SMC_V1_RULE_OPTIONS.md` (branch
`spec/large-smc-rule-options-v1` @ `9ed8135`), adopting RMR-A with the `(rec)` option for
every D00–D34.

**That branch and commit are not reachable** from this repository. Git fetch finds no such
ref, `9ed8135` is not a known object, and the GitHub API returns 404 for the branch. Only
the rules the owner stated explicitly below are therefore recorded. Any D-item whose
`(rec)` option is only in the unreachable catalogue is listed and skipped individually, as
the mission instructs ("D without (rec): list and skip that item only").

| Item | Owner-stated rule |
|------|-------------------|
| D00 timeframes | Keep D1 / H1 / M5 |
| Swings | SW-A strict fractal, causal. `smartmoneyconcepts` is **not** signal authority. |
| POI | Order block (`AG_ORDER_BLOCK_V1`) or FVG |
| Sweep | Option A |
| Break | By close; tie tolerance 5 points; MSS = CHoCH |
| Displacement | `AG_ENTRY_DISPLACEMENT_V1` |
| Entry / stop / targets | Entry by reference; stop C10; targets C11 |
| Day boundary | New York 17:00, IANA time zone with DST |
| Opportunity expiry | Session end. A stale state is suspended first, then expires. |
| D30 | Badged `OPPORTUNITY`, `economic_status = NOT_EVALUATED` |
| Alert mapping | DEVELOPING→INFO, NEAR_POI→WATCH, OPPORTUNITY→OPPORTUNITY, INVALIDATED/EXPIRED→INFO |
| Parameters | `POI_MAX_AGE` = 5 trading days; `SWEEP_TO_CHOCH_WINDOW` = 12 M5 bars; `NEAR_POI_BAND` = 0.5 × ATR(H1,14) |

Skipped because their `(rec)` text is only in the unreachable catalogue: every D00–D34 item
not listed in the table above.

## Invariants

- `order_send` = 0, `order_check` = 0, position mutations = 0.
- No private exchange APIs.
- No strategy rule or parameter changes except the new 1.1.0 version.
- No new SMC engine; no Telegram changes; no scheduler installs.
- No sealed, out-of-sample or holdout data. Public data must end before 2025-09-14.
- Never manufacture setups.

## Round 2 owner decisions (approved 2026-09-30)

1. **Baseline: narrow exception.** Main's capability-zero forbidden-package test is amended
   to allow `src/ticket_delivery` only in ARCHIVE_ONLY / message-only form (no Telegram change).
   `execution`, `trade_management`, `authorization`, `owner_decision` and `svos` stay forbidden.
   The frozen engines' sizing/guard imports (e.g. `execution.risk.size_position`) move behind
   a pure-math boundary module outside the forbidden packages. Strategy rules and parameters
   are unchanged, and a test proves the boundary has no broker/order imports.
2. **`features.py`:** approved; byte-exact copy from the audit branch (blob `f16baab`).
3. **Rule spec:** the branch is unpushed; the 1.1.0 rules written in the mission are
   authoritative.
4. **Permissions:** restoring files from `2b75bbf` (e.g. `strategies/`) is approved.

Nothing is merged into main. The work stays on `v1/two-goals-cloud` (PR #15, draft).

## Implementation status

This record is data only. For what was and was not implemented on the branch, and why, see
`docs/status/AG_V1_TWO_GOALS_CLOUD_STATUS.md`.
