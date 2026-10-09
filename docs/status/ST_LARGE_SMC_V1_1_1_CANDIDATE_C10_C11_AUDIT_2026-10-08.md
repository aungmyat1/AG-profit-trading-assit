# ST_LARGE_SMC_V1 1.1.1 candidate — per-symbol C10/C11 audit

> **NOT_EVIDENCE — historical draft from a dirty worktree.** Its cited baseline SHA-256
> `68a7b7f4fe9e405ba002e631272b384439ff7d1e3b6d3bad53bc51d3748027b0` was dirty-worktree
> 1.1.0 bytes, not the committed baseline. The committed 1.1.0 SHA-256 is
> `15e13a628752eabb01b8072973bede4974feec918a0def71755ce76570591ebd`. Synthetic/mixed
> fixture outputs, gate totals, and historical verification below are not market evidence,
> replay evidence, qualification evidence, owner confirmation, or a 1.1.0 non-regression claim.

**Status:** historical spec-only candidate audit; all six strategy instruments remain
`PENDING_OWNER_CONFIRM`. The candidate is
not registered, active, runtime-wired, proposal-authorized, demo-authorized, or live-authorized.
No production, order, execution, delivery, or broker path was changed.

## 1.1.0 pre-existing diff and disposition

Before syncing the session branch, the preserved worktree patch for
`strategies/ST_LARGE_SMC_V1_1_1_0.yaml` was the following (base blob `42f4a27`, patched blob
`46d67cc`):

```diff
diff --git a/strategies/ST_LARGE_SMC_V1_1_1_0.yaml b/strategies/ST_LARGE_SMC_V1_1_1_0.yaml
index 42f4a27..46d67cc 100644
--- a/strategies/ST_LARGE_SMC_V1_1_1_0.yaml
+++ b/strategies/ST_LARGE_SMC_V1_1_1_0.yaml
@@ -17,6 +17,8 @@ live_authorized: false
 economic_status: NOT_EVALUATED       # D30

 instruments: [EURUSD, GBPUSD, USDJPY, XAUUSD, BTCUSDT, ETHUSDT]
+# VT Markets watch aliases; the frozen CRYPTO_PERP strategy names above remain unchanged.
+broker_symbol_aliases: {BTCUSD: BTCUSDT, ETHUSD: ETHUSDT}
 timeframes:                          # D00: keep D1/H1/M5
@@ -35,7 +37,7 @@ rules:
   stop: C10                          # large_smc_core.c10_stop_policy (byte-exact from 2b75bbf)
   targets: C11                       # structural-fallback semantics on causal M5 swings
   day_boundary: {time: "17:00", tz: America/New_York, dst: IANA}
-  opportunity_expiry: SESSION_END    # config/canonical_sessions.yaml; outside sessions -> next day boundary
+  opportunity_expiry: SESSION_END    # FX: canonical sessions; crypto: active VT crypto-ticket window end
   stale: SUSPEND_THEN_EXPIRE
@@ -51,14 +53,17 @@ implementation_choices_flagged:      # not in the owner-stated rules; conservati
   - "C11 primary external-liquidity tier needs smartmoneyconcepts structure tiers and is NOT_EVALUATED; the fallback (nearest unswept opposing M5 swing strictly beyond entry) is computed on causal swings."
   - "Stale = no closed M5 bar for more than 15 minutes; FX market closed Fri 17:00 to Sun 17:00 New York."
   - "POI age = distinct NY-17:00 trading dates since the POI origin (valid while <= 5)."
+  - "FX opportunity expiry uses config/canonical_sessions.yaml; BTC/ETH expiry uses the active crypto ticket-window config and, when triggered outside a configured window, the next configured window end."
@@ -61,8 +64,11 @@ symbol_metadata:
-  EURUSD: {point: 0.00001, source: config/historical_datasets/EURUSD_*_symbol_metadata.yaml}
-  GBPUSD: {point: 0.00001, source: "config/historical_datasets/GBPUSD_H1_symbol_metadata.yaml @ 2b75bbf"}
-  BTCUSDT: {point: 0.1, source: src/strategy_engine/sweep_retest/crypto_symbols.py}
-  ETHUSDT: {point: 0.01, source: src/strategy_engine/sweep_retest/crypto_symbols.py}
-  USDJPY: {point: null, status: FIXTURE_ONLY}   # host must capture MT5 symbol_info()
-  XAUUSD: {point: null, status: FIXTURE_ONLY}
+  EURUSD: {point: 0.00001, source: config/symbol_metadata/host_captured/EURUSD.json, status: HOST_CAPTURED}
+  GBPUSD: {point: 0.00001, source: config/symbol_metadata/host_captured/GBPUSD.json, status: HOST_CAPTURED}
+  BTCUSDT: {point: 0.1, source: src/strategy_engine/sweep_retest/crypto_symbols.py, fallback_only_without_vt_capture: true}
+  ETHUSDT: {point: 0.01, source: src/strategy_engine/sweep_retest/crypto_symbols.py, fallback_only_without_vt_capture: true}
+  USDJPY: {point: 0.001, source: config/symbol_metadata/host_captured/USDJPY.json, status: HOST_CAPTURED}
+  XAUUSD: {point: 0.01, source: config/symbol_metadata/host_captured/XAUUSD.json, status: HOST_CAPTURED}
+  BTCUSD: {point: 0.01, source: config/symbol_metadata/host_captured/BTCUSD.json, status: HOST_CAPTURED, alias_of: BTCUSDT}
+  ETHUSD: {point: 0.01, source: config/symbol_metadata/host_captured/ETHUSD.json, status: HOST_CAPTURED, alias_of: ETHUSDT}
```

The patch is preserved as `artifacts/AGP_LSMC_LOGIC_03/ST_LARGE_SMC_V1_1_1_0_preexisting.diff`
(SHA-256 `3673bad3e3ee77612f32fad912b6be0db577983a578674f541405f1450371ce6`). It describes
uncommitted worktree bytes only. The 1.1.0 YAML was restored unchanged to the committed SHA-256
`15e13a628752eabb01b8072973bede4974feec918a0def71755ce76570591ebd`; the saved patch is
ported selectively into the 1.1.1 candidate with explicit provenance, not into 1.1.0.

## C10 — captured point provenance; pip rules still pending

The six broker point captures are read from `config/symbol_metadata/host_captured/*.json` on
main. Candidate metadata records each source point and captured-record digest. BTCUSDT and
ETHUSDT retain their strategy-symbol fallback point only as fallback metadata; the candidate's
broker aliases resolve C10 evidence to captured BTCUSD/ETHUSD records.

The proposed FX 5/3-digit `10 * point` rule, XAUUSD `0.1` rule, BTCUSD price unit `1.0`, and
ETHUSD price unit `0.1` are all `PENDING_OWNER_CONFIRM`. They do not populate any `pip_size`
field and are not applied by C10. A missing/invalid host point capture returns
`C10_PIP_SIZE_NOT_EVIDENCED`; a present capture with an unconfirmed pip rule returns
`PIP_SIZE_UNCONFIRMED`. No point, digit, asset-class, broker-convention, or fixture-price
conversion is performed pending owner confirmation.

## C11 — core primary wired into the candidate adapter

For each opportunity ticket, the candidate-only adapter calls the existing
`large_smc_core.target_model.select_target` using the existing EXTERNAL market-structure tier
and closed M5 candles. It accepts only `PRIMARY_EXTERNAL_LIQUIDITY` with an opposing,
strictly beyond, `UNSWEPT` level. The structure tier's existing equal-level tolerance is
expressed in captured tick-size units; this C11 structure input is not used or converted as a
pip size.

If that core primary result is absent, the adapter ignores the selector's legacy
`FALLBACK_M5_SWING` tier and uses the nearest confirmed, opposing H1 SW-A swing (`k=2`) beyond
the entry. The fallback is causal on closed H1 bars; an equal-distance tie and no-target case
fail closed. The selected source is copied onto each ticket as `ticket.c11_source` and into
the per-symbol JSON audit row. A regression test forces a core `FALLBACK_M5_SWING` response and
verifies that only the H1 fallback is accepted.

The existing 1.1.0 watch/runtime remains unchanged: it does not call the core primary selector
and continues to use its own M5 fallback behavior. This is candidate-only wiring.

## Candidate RR minimum

The candidate now explicitly declares `minimum_rr: 2.0` with
`minimum_rr_status: PENDING_OWNER_CONFIRM`. This is the owner-provided candidate value, not a
claim that 1.1.0 already specified it. A below-minimum computed RR fails closed. If stop/target
is unavailable, RR is undefined and also fails closed. All candidate rows remain pending owner
confirmation.

## Per-symbol fixture provenance

Fixture files are under `tests/fixtures/large_smc_v111/`; their hashes and per-timeframe source
labels are in `manifest.json`. The new test verifies that no OHLC price value is reused across
the six symbol fixtures. Timestamps are aligned intentionally.

- **EURUSD — `HOST_CAPTURED_DERIVED`:** admitted `SSC_V1_0_1_G2_DEV_001` H1/M1 data with
  `cross_timeframe_status: PASS`; closed M1 bars are resampled to complete M5 and complete UTC
  H1 days form D1. Audit result at 2026-08-03 00:00 UTC: `NEAR_POI`, LONG bias, no opportunity.
- **GBPUSD — `MIXED_HOST_CONTEXT_AND_SYNTHETIC`:** captured H1 is from the recorded
  `WARMUP_CONTEXT_ONLY` package and is not decision-window evidence; D1 and M5 are explicitly
  `SYNTHETIC` logic probes. It is not represented as a coherent host-market replay. Result:
  `DEVELOPING`, no opportunity.
- **USDJPY, XAUUSD, BTCUSDT, ETHUSDT — `SYNTHETIC`:** each has its own separately stored,
  non-overlapping OHLC fixture. The OHLC levels are deterministic test inputs only, not
  observed prices, pips, sizing data, or economic evidence. USDJPY/BTCUSDT/ETHUSDT retain a
  synthetic unswept external level; XAUUSD's synthetic external level is reclaimed to exercise
  the H1 fallback.
- The quarantined `SSC_FRESH_DEV_GEN_002_MT5_20260801_20260914` package is not referenced or
  used.

## L1–L6 candidate audit

L1–L6 were evaluated for each of the six symbols. Where the frozen signal pipeline produced no
opportunity, ticket-specific L2/L3/L6/C10/C11/RR are correctly reported as
`NOT_APPLICABLE_NO_TICKET`; this is not counted as a ticket-gate pass. L5 remains advisory
`WARN` because no spread/commission inputs are present. All candidate rows are
`PENDING_OWNER_CONFIRM`.

| Symbol | Fixture source | State / ticket | C10 | C11 source recorded per ticket | Selected target | RR | L1 | L2 | L3 | L4 | L5 | L6 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| EURUSD | HOST_CAPTURED_DERIVED | NEAR_POI / none | N/A | NO_TICKET | N/A | N/A | PASS | N/A | N/A | PASS | WARN | N/A |
| GBPUSD | MIXED_HOST_CONTEXT_AND_SYNTHETIC | DEVELOPING / none | N/A | NO_TICKET | N/A | N/A | PASS | N/A | N/A | PASS | WARN | N/A |
| USDJPY | SYNTHETIC | OPPORTUNITY / LONG | PIP_SIZE_UNCONFIRMED | PRIMARY_EXTERNAL_LIQUIDITY | PRIMARY_EXTERNAL_LIQUIDITY 151.5 (UNSWEPT) | RR_UNDEFINED_C10_STOP_UNAVAILABLE | PASS | FAIL | FAIL | PASS | WARN | PASS |
| XAUUSD | SYNTHETIC | OPPORTUNITY / LONG | PIP_SIZE_UNCONFIRMED | CONFIRMED_OPPOSING_H1_SWING | FALLBACK_H1_SWING 2702.5 | RR_UNDEFINED_C10_STOP_UNAVAILABLE | PASS | FAIL | FAIL | PASS | WARN | PASS |
| BTCUSDT | SYNTHETIC | OPPORTUNITY / LONG | PIP_SIZE_UNCONFIRMED | PRIMARY_EXTERNAL_LIQUIDITY | PRIMARY_EXTERNAL_LIQUIDITY 62000.0 (UNSWEPT) | RR_UNDEFINED_C10_STOP_UNAVAILABLE | PASS | FAIL | FAIL | PASS | WARN | PASS |
| ETHUSDT | SYNTHETIC | OPPORTUNITY / LONG | PIP_SIZE_UNCONFIRMED | PRIMARY_EXTERNAL_LIQUIDITY | PRIMARY_EXTERNAL_LIQUIDITY 3735.0 (UNSWEPT) | RR_UNDEFINED_C10_STOP_UNAVAILABLE | PASS | FAIL | FAIL | PASS | WARN | PASS |

**Gate totals (36 cells):** PASS 16, FAIL 8, WARN 6, NOT_APPLICABLE_NO_TICKET 6.
L1 PASS 6/6; L2 FAIL 4 and no-ticket N/A 2; L3 FAIL 4 and no-ticket N/A 2; L4 PASS 6/6;
L5 WARN 6/6; L6 PASS 4 and no-ticket N/A 2. C11 selected the core primary for three
synthetic tickets and the H1 fallback for one; the two no-opportunity symbols have no ticket
source to record. All four opportunity tickets fail C10/L2 and RR/L3 closed gates while the
pip sizes and RR minimum remain pending owner confirmation.

## Historical audit output — NOT_EVIDENCE

The gate table and all earlier 1.1.0 comparison/output hashes above are retained as a historical
record only. They were produced against a dirty-worktree 1.1.0 baseline (`68a7b7f4…`) and
synthetic/mixed logic fixtures. They do not establish market performance, replay qualification,
C10 approval, or 1.1.0 non-regression. The actual committed 1.1.0 baseline is
`15e13a628752eabb01b8072973bede4974feec918a0def71755ce76570591ebd`.

## Amendment 2 implementation record — specification and unit tests only

- Captured point sources are the six `config/symbol_metadata/host_captured/{EURUSD,GBPUSD,USDJPY,XAUUSD,BTCUSD,ETHUSD}.json` records on main commit `7060e33b0a62f39b9faf7d506b32801b6463a64c`.
- Candidate-only aliases are `BTCUSD -> BTCUSDT` and `ETHUSD -> ETHUSDT`; both aliases and host-captured status were ported from saved worktree diff `3673bad3`.
- The proposed FX `10 * point`, XAUUSD `0.1`, BTCUSD `1.0`, and ETHUSD `0.1` pip rules are all `PENDING_OWNER_CONFIRM`; no `pip_size` is populated or computed.
- C10 reports `C10_PIP_SIZE_NOT_EVIDENCED` when the host capture is missing or invalid and `PIP_SIZE_UNCONFIRMED` when the capture exists but its pip rule remains pending.
- This document remains `NOT_EVIDENCE`; its fixture table is not a qualification/replay result. Amendment 2 code verification: `tests/test_lsmc_v111_candidate_audit.py` **9 passed**; repository suite **1,171 passed, 5 skipped, 0 failed** (one Starlette/httpx deprecation warning). These tests validate code behavior only, not strategy performance or evidence qualification.
