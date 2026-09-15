# Large SMC EURUSD Friction Policy -- WP3A Empirical Friction Evidence (2026-09-16)

Read-only evidence-gathering mission against the WP2-frozen admission contracts. No
order placed, no Demo/Live execution, no strategy change, no G0+, no holdout access,
no instrument expansion, no authorization change.

## P0 -- freeze audit

`WP2_COMMIT_SHA = 7581c421fffa90ccc0df2c5aafc5ee23008c6467` (already HEAD at mission
start; nothing new needed committing for WP2 itself). The only pending working-tree
changes at mission start were `.vscode/settings.json` and `pyrightconfig.json` --
neither is included in any commit made by this mission.

## P1 -- source inventory (Vantage/MT5, read-only, no order placed)

| Item | Classification | Source |
|---|---|---|
| pip_size / tick_size | BROKER_SPECIFIED | live `symbol_info('EURUSD')`, this session |
| trade_tick_value / contract_size | BROKER_SPECIFIED | live `symbol_info('EURUSD')`, this session |
| bid / ask (live) | BROKER_SPECIFIED (point-in-time) | live `symbol_info_tick('EURUSD')` |
| spread (multi-sample) | EMPIRICALLY_OBSERVED (narrow window) | new collector, see P2 |
| commission | UNAVAILABLE (EURUSD-specific) | see P3 |
| slippage | UNAVAILABLE (n=1, insufficient) | see P4 |
| historical spread (multi-session) | UNAVAILABLE | not attempted -- would require a longer-running capture than one session permits |

MT5 connection was live and read-only queryable this session: account 26088035,
server `VantageMarkets-Demo`, `trade_mode=0` (demo).

## P2 -- spread capture (new, read-only)

Added `src/fx_friction_research/spread_evidence.py` (capture/summarize/hash) and
`scripts/collect_eurusd_spread_evidence.py` (CLI runner). Both call only
`mt5.market_data.get_tick` / `mt5.account.account` -- never `order_send`/`order_check`;
enforced by `tests/test_large_smc_eurusd_friction_evidence_wp3a.py`'s static AST scan.

Ran once this mission: 12 samples, 5s apart, EURUSD, 2026-09-15T20:12:28Z --
2026-09-15T20:13:23Z (~55s window). Raw observations:
`artifacts/validation/ST_LARGE_SMC_V1/EURUSD_ADMISSION_CONTRACTS/spread_evidence/wp3a_2026-09-16_session1_raw.jsonl`.
Summary: sample_count=12, min=1.30 pips, median=1.30 pips, mean=1.325 pips, p90/p95/max=1.40
pips. `raw_observations_hash = b8d171c3207329672e785815b9840e2d5bb5a709a536889ca75697a80278299e`.

**Scope caveat (deliberately not overstated):** a single ~55-second window at one time
of day on one calendar day is not a sample across this strategy's relevant trading
periods (Asian/London/NY sessions). It is real evidence -- and notably runs higher than
the existing 0.8-pip ASSUMED figure -- but it is not sufficient by itself to replace
that assumption with a signed empirical value.

## P3 -- commission

Investigated whether Vantage/MT5 exposes a real EURUSD commission schedule. MT5 deal
rows do carry a real `commission` field on this account (`src/api/broker_service.py`
already reads it) -- confirmed by querying this account's actual deal history: only 3
deals exist in the last 30 days, all BTCUSD, `commission=0.0` for each. **No EURUSD deal
exists in this account's retrievable history** (`history_deals_get` over 30 days returns
0 EURUSD rows -- the 3 real EURUSD fills recorded in `journal/execution_*.jsonl` from
2026-08-28 are outside what this account's broker-side history now returns). Per this
mission's explicit instruction, the BTCUSD-observed value was **not** carried over to
EURUSD (different asset class, no basis to assume the same schedule). Classification:
**UNAVAILABLE** (EURUSD-specific); contract's `commission_pips` stays `ASSUMED`
(unchanged 0.7 pip-equivalent, WP2's literature figure).

## P4 -- slippage

No trade was placed to measure this. Searched existing legitimate Demo execution
records (`journal/execution_*.jsonl`) for real EURUSD requested-vs-filled prices.
Found exactly **one** usable record: `command_id=ag-safety-v1-open-1`,
`ticket=1880608563`, 2026-08-28, `slippage_points=-1.0` (= -0.1 pip on this 5-digit
broker -- a favorable fill). A second EURUSD fill (`ag-demo-v1-open-2`) has no matching
requested-price record, so no slippage is computable for it. This account's current MT5
deal history no longer covers either fill, so neither could be independently
re-verified this session. **n=1 is not a distribution** -- per this mission's explicit
instruction, this was not turned into a fabricated "empirically observed" slippage
figure. Classification: **UNAVAILABLE**; contract's `slippage_pips` stays `ASSUMED`
(unchanged 0.3 pip, WP2's literature figure).

## P5 -- stop/friction relationship

C10 (`strategies/ST_LARGE_SMC_V1.yaml`, `C10_STRUCTURAL_INVALIDATION_V1`) was not
touched. `min_buffer_pips=1.5` is an ATR-derived **floor**, not a typical stop
distance. Combining this mission's own real spread sample (median 1.30, max 1.40 pips)
with the unchanged ASSUMED commission (0.7) and slippage (0.3) gives a total
ASSUMED-scenario friction of roughly 1.8-2.4 pips -- already close to or above that
1.5-pip floor. Whether that floor case occurs often enough to matter, and what
friction-to-stop ratio is acceptable, is a strategy-risk-tolerance call this mission is
not authorized to make. Recorded as `minimum_stop_friction_relationship.status =
OWNER_ADJUDICATION_REQUIRED` in the contract. No threshold was tuned against historical
profitability.

## P6 -- contract update

`artifacts/validation/ST_LARGE_SMC_V1/EURUSD_ADMISSION_CONTRACTS/friction_policy_contract.json`
updated in place: every value now carries `value`/`unit`/`classification`/`source`/
`evidence_ref` (and `measurement_window` for the spread evidence). Remains `status:
PROPOSED`, `owner_signature: REQUIRED` -- this mission does not self-sign.

## P7 -- safety

No order placed. No Demo or Live execution. No strategy file changed
(`git diff 7581c42 -- strategies/ST_LARGE_SMC_V1.yaml src/large_smc_research/
src/validation_framework/adapters/large_smc_adapter.py` is empty). No frozen validation
core file changed. No holdout access. No instrument expansion (EURUSD only, unchanged).
No authorization change (`execution_authority_metadata` unchanged:
`demo_authorized=False, live_authorized=False, proposal_generation_authorized=False`).

## P8 -- tests

`tests/test_large_smc_eurusd_friction_evidence_wp3a.py` (new, 17 tests) plus the
existing `tests/test_large_smc_eurusd_admission_wp2.py` (14 tests) -- all pass. Covers:
collector is read-only (AST scan for order-placement names/imports); missing MT5
connection fails closed; spread conversion arithmetic; commission/slippage absence
stays absence (not silently upgraded); raw-observation hash is deterministic and
order-independent; summary is reproducible; strategy semantics unchanged (git-diff
against `7581c42`); frozen validation core unchanged (git-diff against `7581c42`);
execution/gateway files unchanged (git-diff against `7581c42`); execution authority
metadata unchanged; VALIDATION_ADMISSION still blocks EURUSD on exactly the same three
reasons as WP2.

## Output

```text
REPOSITORY_STATE: clean except this mission's additive changes (see FILES_CHANGED); .vscode/settings.json and pyrightconfig.json left untouched/uncommitted per P0
WP2_COMMIT_SHA: 7581c421fffa90ccc0df2c5aafc5ee23008c6467
MT5_CONNECTION_STATUS: CONNECTED (read-only queries only)
BROKER_IDENTITY: VantageMarkets-Demo, account 26088035, trade_mode=DEMO
FRICTION_SOURCE_INVENTORY: pip_size/tick_size/trade_tick_value/contract_size = BROKER_SPECIFIED (live); spread = EMPIRICALLY_OBSERVED (narrow single-window sample); commission = UNAVAILABLE (EURUSD-specific); slippage = UNAVAILABLE (n=1, insufficient); historical multi-session spread = UNAVAILABLE (not attempted this session)
SPREAD_EVIDENCE: 12 samples, ~55s window, 2026-09-15T20:12:28Z-20:13:23Z, median 1.30 pips / max 1.40 pips -- higher than the existing 0.8-pip ASSUMED figure; raw+summary stored under artifacts/validation/ST_LARGE_SMC_V1/EURUSD_ADMISSION_CONTRACTS/spread_evidence/
COMMISSION_EVIDENCE: UNAVAILABLE for EURUSD -- real commission field confirmed queryable via 3 BTCUSD deals (commission=0.0 each), but 0 EURUSD deals retrievable in 30-day history; not cross-inferred from BTCUSD
SLIPPAGE_EVIDENCE: UNAVAILABLE -- exactly one real EURUSD fill with computed slippage (-1.0 points/-0.1 pip); n=1 insufficient, not fabricated into a distribution
STOP_FRICTION_STATUS: OWNER_ADJUDICATION_REQUIRED -- ASSUMED-scenario total friction (~1.8-2.4 pips) is close to/above the 1.5-pip C10 stop-buffer floor; C10 itself unchanged
UPDATED_FRICTION_POLICY: artifacts/validation/ST_LARGE_SMC_V1/EURUSD_ADMISSION_CONTRACTS/friction_policy_contract.json -- status still PROPOSED, owner_signature REQUIRED
FRICTION_POLICY_SIGNABILITY: INSUFFICIENT_EVIDENCE
VALIDATION_CORE_DIFF: empty (git diff 7581c42 -- validation_framework core files + config/governance/strategy_lifecycle.yaml)
STRATEGY_SEMANTICS_DIFF: empty (git diff 7581c42 -- strategies/ST_LARGE_SMC_V1.yaml, src/large_smc_research/, large_smc_adapter.py)
TEST_RESULTS: 29/29 passed (tests/test_large_smc_eurusd_friction_evidence_wp3a.py + tests/test_large_smc_eurusd_admission_wp2.py)
EXECUTION_BOUNDARY: no order placed; execution/*, mt5.management_gateway, mt5.mt5_gateway all git-diff-empty against 7581c42; execution_authority_metadata unchanged (all False)
FILES_CHANGED:
  M  artifacts/validation/ST_LARGE_SMC_V1/EURUSD_ADMISSION_CONTRACTS/friction_policy_contract.json
  A  artifacts/validation/ST_LARGE_SMC_V1/EURUSD_ADMISSION_CONTRACTS/spread_evidence/wp3a_2026-09-16_session1_raw.jsonl
  A  artifacts/validation/ST_LARGE_SMC_V1/EURUSD_ADMISSION_CONTRACTS/spread_evidence/wp3a_2026-09-16_session1_summary.json
  A  src/fx_friction_research/spread_evidence.py
  A  scripts/collect_eurusd_spread_evidence.py
  A  tests/test_large_smc_eurusd_friction_evidence_wp3a.py
  A  docs/status/AG_LARGE_SMC_EURUSD_FRICTION_EVIDENCE_WP3A_STATUS.md
  (not touched/not committed: .vscode/settings.json, pyrightconfig.json)
BLOCKERS: commission/slippage remain UNAVAILABLE for EURUSD specifically on this account's currently retrievable history; spread evidence is real but session-narrow; C10-vs-friction adequacy is an owner risk-tolerance decision, not derivable from existing governance semantics alone
NEXT_SAFE_ACTION: owner either (a) signs off on a longer, session-spanning spread-only capture run (same read-only collector, run across Asian/London/NY windows over multiple days) before this contract can be considered SIGNED, or (b) explicitly accepts the current ASSUMED commission/slippage figures alongside the real spread evidence and adjudicates the C10 stop-buffer-vs-friction floor question -- this mission takes neither action itself
```
