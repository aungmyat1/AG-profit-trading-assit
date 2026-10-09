# AGP-C1-LSMC — ST_LARGE_SMC_V1@1.1.0 VT-only + logic verification (2026-10-09)

**LOGIC_VERIFICATION_REPORT:** `ST_LARGE_SMC_V1@1.1.0` → **LOGIC_VERIFIED** (rule conformance
and internal consistency only). Not EDGE_VERIFIED; proposal, demo and live authority remain
`false`. Full machine report: [`AGP_C1_LSMC_V110_LOGIC_VERIFICATION_2026-10-09.json`](AGP_C1_LSMC_V110_LOGIC_VERIFICATION_2026-10-09.json).

| Identity | Value |
|---|---|
| Contract | `strategies/ST_LARGE_SMC_V1_1_1_0.yaml` sha256 `78285f9fabcb20af14de327d010e48684dc12205f4435eff886fcc2373a357b4` |
| Engine (`src/large_smc_watch/{__init__,contract,detect,watch}.py`, sha256 over path+file sha) | `ec0b2f3dc6ed2b02df3f643b38beac1c0e88630413c74e0f55e3d8aa5f5570d4` |
| Dependencies | `large_smc_core/c10_stop_policy.py` `383143bc…dc641da`; `fx_discovery/features.py` `c6ef0063…d496731` |
| Code commit | `ce6f0f895d43016108f195c4d2a0708a221ed8d7` |
| Gate | `src/v1_tickets/lsmc_logic_gate.py` (pattern of `v1_tickets/logic_gate.py`); L1–L4 block, L5/L6 advisory |
| Command | `python scripts/lsmc_v110_logic_verification.py --out <json>` (exit 0 = LOGIC_VERIFIED) |

## Changes in this mission

1. **VT-only universe.** `instruments` / `V1_SYMBOLS`: BTCUSDT/ETHUSDT → VT MT5 **BTCUSD/ETHUSD**.
   Points come only from the sha256-verified host `symbol_info()` capture
   (`config/symbol_metadata/host_captured/`); missing or tampered → `DATA_ERROR
   SYMBOL_METADATA_MISSING`. The repo point constants and the caller-supplied point were removed.
   Behavior delta: crypto tie tolerance now uses the VT point 0.01 (was exchange tick 0.1).
   This is an owner-directed in-place edit of 1.1.0; pre-edit bytes stay identified by sha256
   `15e13a62…0591ebd` (cited by the 1.1.1 candidate).
2. **Actionability (PR #48 decision).** The post-signal layer exists (`v1_tickets/actionability.py`,
   via #55) but had no correlated-READY handling. Added `v1_tickets/correlation_guard.py`:
   READYs with same-sign exposure to a shared currency/asset leg get a non-blocking
   `CORRELATED_READY` warning; decisions are never changed. Not yet wired into delivery.
3. **Logic gate** as above.

## Cases (18; all L1–L4 PASS, L5 WARN = no spread/commission in fixtures)

| Set | Symbols | States |
|---|---|---|
| 1.1.0 synthetic (`tests/_lsmc_v110_fixtures.py`, scaled) | all six | OPPORTUNITY + NEAR_POI each |
| 1.1.1 per-symbol fixtures (EURUSD host-derived; GBPUSD mixed; rest synthetic; BTCUSDT/ETHUSDT series run as BTCUSD/ETHUSD) | all six | EURUSD NEAR_POI, GBPUSD DEVELOPING, others OPPORTUNITY |

Coverage limits (recorded, not hidden): only LONG opportunities occur in the fixtures; C10 stop
geometry is verifiable only for EURUSD/GBPUSD (elsewhere the contract's
`C10_PIP_SIZE_NOT_EVIDENCED` fail-closed path is verified); C11 target direction is exercised on
the four 1.1.1 OPPORTUNITY fixtures (synthetic opportunities resolve `REJECT_NO_TARGET`); no
live VT candles were evaluated (cloud environment, MT5 not reachable).

## Tests (2026-10-09, Linux cloud container, Python 3.13)

`pytest -q tests/test_lsmc_v110_logic_gate.py tests/test_v1_large_smc_110_watch.py tests/test_lsmc_v111_candidate_audit.py tests/test_host_go_live_kit.py tests/test_v1_large_smc_import_boundary.py tests/test_lsmc_alert_dedup.py tests/test_host_heartbeat.py tests/test_v1_tickets.py …` → 280 passed, 1 skipped. Full suite `pytest -q` → 1671 passed, 3 skipped.
Host acceptance (live VT BTCUSD/ETHUSD watch on the Windows host): NOT_EVALUATED.
