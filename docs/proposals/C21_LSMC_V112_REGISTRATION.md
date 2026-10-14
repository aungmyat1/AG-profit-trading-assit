---
class: design
state: SUPERSEDED
verification_state: NOT_VERIFIED
superseded_by: AGP-C24-LSMC-VERSION-SELECTION
owner_reviewed: null
---
# C21 Large-SMC 1.1.2 registration proposal

**Status: SUPERSEDED** — owner Aung, 2026-10-14, `AGP-OD1014-RATIFY-R1` step 4;
[owner decision register](../governance/OWNER_DECISION_REGISTER.md),
`AGP-C24-LSMC-VERSION-SELECTION`. The next registration candidate is **1.1.3**
([PR #216](https://github.com/aungmyat1/AG-profit-trading-assit/pull/216)).
1.1.2 remains REPORT_ONLY observation, never LOGIC_VERIFIED or execution-eligible.
Frozen identities and the historical evidence below are retained; no verification
status transfers to 1.1.3. A DEMO ORDER PROPOSAL requires 1.1.3 LOGIC_VERIFIED and
separate scope READY approval; broker execution remains disabled pending separate authorization.

Mission `AGP-C21-LSMC-V112-ENGINE-R2`, 2026-10-14. Base main:
`e884b8605739b64d229f848c99ed4a23d8b4ae45`, which contains PR #200 and the newer report interfaces.
Branch `feat/lsmc-v112-engine-r2`; implementation draft PR #209. Proposal-only PR #202 was merged before the implementation push; its merged branch is not reused. No merge or registration is proposed by this mission.

## Identity and wiring

`ST_LARGE_SMC_V1@1.1.2` is an append-only, REPORT_ONLY candidate at `src/large_smc_v112/`.
The frozen detector, C10 calculation and structure/target selectors are reused; the separate watch
implements trading-date FX POI expiry and candidate C11 primary/H1 fallback. C11 is selected from
candles closed at the trigger, so later bars cannot retarget. Crypto POI expiry retains the frozen
seven-day calendar behavior; opportunity expiry follows the candidate's committed crypto windows.
`config/lsmc_report_lane.yaml` selects the observational engine; OD1014-FAST D7 selects `1.1.2` (REPORT_ONLY only).
Missing, malformed or unknown version configuration returns a BLOCKED, NOT_VERIFIED report (`LSMC_REPORT_VERSION_NOT_EVIDENCED`), with no engine fallback.
Candidate tracker/journal paths are separate from the frozen watch. Every candidate observation is
stamped `NOT_VERIFIED`. `lsmc_lane.py` only adds version selection; mapping/formatting remain unchanged.
OD1014-FAST D6 confirms the RR minimum of 2.0; below-minimum RR blocks report qualification, never pricing
geometry or the six-symbol evidence below. No READY, broker, registry, scheduler or authorization change.

Contract SHA-256: `1f9b6cace2e1be33e5b3572e2c13e3e526b992478f91c8f09955b0f44b73024f`.
Candidate engine SHA-256: `7f218a9001cb7ffa069e02a101accd53ab86b2b2c8989c73939671fb624f0d7a` (ordered path + file-hash identity, including metadata/targets/windows).
Detailed per-file identity is in [the audit](../../artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_2/c21_r2/audit.json).

## OD1014-FAST D2 amended owner convention

For **all six symbols**, `pip = 10 × fields.point` from
`config/symbol_metadata/host_captured/<CANONICAL>.json`. This is an owner convention over host-evidenced
point, not a claim that the host captured a `pip` field. Decimal multiplication avoids a binary-float
mismatch on the FX equality gate. The loader validates `AG_HOST_SYMBOL_METADATA_V2`, `VTMarkets-Demo`,
canonical/broker names against `config/broker_symbol_map/vt_markets_demo.yaml`, positive finite numeric
point, the map's expected point, UTC capture time and both payload/map hash pins. A missing, malformed,
mismatched or tampered record fails closed as `C10_PIP_SIZE_NOT_EVIDENCED`; no EURUSD or asset-class default.
Every stop records `pip_source = "10*point host_captured <captured_at_utc>"`, retained in report observations.
EURUSD and GBPUSD are tested for exact equality to the frozen `C10_PIP_SIZE` values (`0.0001`); mismatch
would stop the mission. USDJPY is `0.01`; XAUUSD, BTCUSD and ETHUSD are each `0.1`.

## Scope matrix and replay

All rows remain **NOT_VERIFIED**. Priced counts here refer to the 18-case committed fixture lane,
not trades, economic edge, live verification or qualification. The BTCUSDT/ETHUSDT synthetic fixture
series retain their original names/provenance and are explicitly evaluated as VT BTCUSD/ETHUSD.

| VT symbol | Derived pip | Priced fixture cases | L1 / L2 / L3 / L4 / L5 / L6 (active market) | Fixture provenance |
|---|---:|---:|---|---|
| BTCUSD | 0.1 | 2 | PASS / PASS / PASS / PASS / WARN / PASS | SYNTHETIC |
| ETHUSD | 0.1 | 2 | PASS / PASS / PASS / PASS / WARN / PASS | SYNTHETIC |
| EURUSD | 0.0001 | 1 | PASS / PASS / PASS / PASS / WARN / PASS | HOST_CAPTURED |
| GBPUSD | 0.0001 | 1 | PASS / PASS / PASS / PASS / WARN / PASS | MIXED_HOST_CONTEXT_AND_SYNTHETIC |
| USDJPY | 0.01 | 2 | PASS / PASS / PASS / PASS / WARN / PASS | SYNTHETIC |
| XAUUSD | 0.1 | 2 | PASS / PASS / PASS / PASS / WARN / PASS | SYNTHETIC |

The R1 replay runs one worker: 18 shipped cases, every EURUSD M5 close (575 scans), and the first
120 full-D1 recorded scans each for BTCUSD and ETHUSD. EURUSD has 6 distinct rolling opportunities.
Its raw L4 result includes **1 FAIL / 574 PASS**: the FAIL is the documented MARKET_CLOSED precondition;
that closed scan is explicitly excluded from the active-market scope above, never relabelled PASS.
The bounded BTC recorded slice contains **0 opportunities**; opportunity checks there are NOT_APPLICABLE,
so its priced geometry proof is synthetic only. ETH has 37 recorded opportunity scans: 24 computed
C10 stops, 13 `MISSING_SPREAD` failures. Missing spread is never manufactured. L5 remains WARN because
accepted commission/spread cost evidence is absent. This is a bounded replay of committed data;
full 60-day re-execution and new host acceptance are **NOT_RUN**.

Command: `python scripts/lsmc_v110_logic_audit.py --version 1.1.2 --out
artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_2/c21_r2/audit.json` (on one shell line).
The candidate CLI acquires/releases the canonical R1 resource lock fail-closed. It writes a
`NOT_RUN_RESOURCE` marker before starting; an interrupted/sandbox-killed run cannot retain stale PASS.
The completed audit records zero lane failures, exact rule declaration match and re-hashed frozen bytes.
New regression tests cover missing/tampered/mismatched metadata, exact pip values, trading-day expiry
in the actual snapshot, unchanged crypto POI expiry, static C11, report isolation/stamping, interrupted
replay, undeclared drift, engine/spec artifact binding and the frozen hash manifest.

## Declared rule diff and frozen audit

The pre-D2 15-path declaration did not cover the pip-source change. It is expanded to **77 paths**,
including D2 source/metadata provenance, report-only wiring and explicit runtime fixture-symbol aliases;
[the audit](../../artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_2/c21_r2/audit.json) recomputes the exact structural diff from 1.1.1 and rejects any
undeclared or stale path. The 1.1.1 source hash remains pinned. D6 confirms RR status/owner provenance (included in the exact declared diff); other pending owner decisions remain
pending; no validation or authority state is promoted.

The default 1.1.0 audit uses a byte-preserved pre-D2 candidate snapshot at
`tests/fixtures/c21/v112_pre_d2.yaml`, retaining its original 15-path historical output. Only
`--version 1.1.2` reads the amended candidate. Full default before/after runs (120 crypto scans,
every EURUSD M5 close) were compared at the same base code identity with git provenance explicitly set to the same current-main identity (only `identity.code_sha` normalized):
**110526 bytes identical**, SHA-256 `c21e5201163e0c2103753e59fafb733b1d3a2fc5471bd2623d69d89d33ed147a`.
[Parity record](../../artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_2/c21_r2/v110_parity.json) and
[unaltered 1.1.0 baseline output](../../artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_2/c21_r2/v110_baseline.json) retain that identity explicitly;
the comparison runner normalizes only `identity.code_sha`; all runtime results remain unmodified. No old evidence is rewritten
or attributed to 1.1.2. The dated C15 document only adds a historical-input pointer. The re-hash manifest
also pins the frozen watch/core dependencies, contract, gate and scheduler configuration. The registry pin is updated only to the current-main D4/D5 bytes; the mission makes no registry edit.

## Registry diff (proposal only; none applied)

Current registry stays registered version **1.1.0**, `active: false`, with its existing historical evidence
and pins. `strategies/registry.yaml` is byte-identical to current main; its upstream D4/D5 change is preserved. A future owner-reviewed registration could add
an independently attributed candidate record with these values, **without replacing 1.1.0**:

```yaml
version: '1.1.2'
config_source: strategies/ST_LARGE_SMC_V1_1_1_2.yaml
engine: src/large_smc_v112/ (REPORT_ONLY)
contract_sha256: 1f9b6cace2e1be33e5b3572e2c13e3e526b992478f91c8f09955b0f44b73024f
engine_sha256: 7f218a9001cb7ffa069e02a101accd53ab86b2b2c8989c73939671fb624f0d7a
status: NOT_VERIFIED
active: false
proposal_generation_authorized: false
demo_authorized: false
live_authorized: false
```

This is a reviewable proposed record, not an edit or authorization to apply it. The registry's actual
versioning schema and any promotion require a separate owner decision after missing scope evidence.

## Checks and open questions

Final local suite result is recorded in [the dated status](../status/AGP_C21_LSMC_V112_ENGINE_R2_2026-10-14.md).
Host/broker/live checks and slow tests excluded by the shipped default pytest profile are NOT_RUN.
D6 closes owner confirmation of the candidate RR minimum. Open: accepted cost evidence (L5); broader real per-symbol
geometry evidence, especially the vacuous recorded BTC slice. No host or broker contact occurred.

| Component | OSS candidate | Decision | Reason |
|---|---|---|---|
| C10 + point convention | Existing signed C10 + stdlib Decimal | REUSED/WRAPPED | Keep signed geometry, explicit host point convention |
| POI age | Existing `_poi_age_days` and NY boundary helpers | REUSED/FIXED | Count observed closed H1 trading dates, preserve crypto calendar |
| C11 | Committed 1.1.1 audit adapter/core selectors; pinned smartmoneyconcepts 0.0.27 | REUSED | No new swing/target algorithm; local spec retains authority |
