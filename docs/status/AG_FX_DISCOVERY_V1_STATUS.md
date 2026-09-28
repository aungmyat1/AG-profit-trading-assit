# Asian Sweep Research Closure + OSS-First FX Strategy Discovery V1 — Status

**Date:** 2026-09-28
**Classification:** `NO_DEVELOPMENT_CANDIDATE`. No candidate was frozen, and SEALED_OOS remains **closed**.
**Base:** `ba8d3feb926f26f0b2c746bdc8250e6a22055a06` (identity verified)
**Authority:** PROPOSAL/DEMO/LIVE = NONE; TradeTicket NOT_CREATED. Broker `order_check`/`order_send`/mutations = 0; there was no MT5 contact and no execution module was involved.

## Governance (commit `557b2c9`)

- `ST_ASIAN_SWEEP_5R_V1@1.2.0-CANDIDATE`: TECHNICAL_PIPELINE VALIDATED / ECONOMIC_RESULT NEGATIVE_BASELINE; authority NONE.
- `ST_ASIAN_SWEEP_5R_V1@1.3.0-CANDIDATE`: TERMINATED_BEFORE_EVALUATION (THRESHOLD_PREREGISTRATION_REQUIRED). `MAX_FRICTION_TO_RISK` was never set, and the draft is kept as `TERMINATED_UNSIGNED`.
- **SEALED_OOS** is recorded in `config/governance/AG_SEALED_OOS_REGISTRY.yaml`:
  - datasets `SSC_V1_0_1_HIST_1Y_M1_001` (M1 `50beb42a…`, broker export `3fdd97cf…`) and `SSC_V1_0_1_HIST_1Y_H1M15_DERIVED_001` (M15 `c9833427…`, H1 `4eb52294…`);
  - sealed period 2025-09-14T21:00Z → 2026-09-15T21:00Z, which extends to every file covering it;
  - `opened: false`.
- The agent's earlier scratch copy of the sealed M1 file (used only for lineage checks in V1.3) was deleted. The sealed M15/H1 hashes are unchanged, and nothing under `src`, `scripts/research` or `tests` references them.

## Phase 1 — development data inventory

| Source | Classification | Note |
|---|---|---|
| `SSC_V1_0_1_HIST_1Y_M1_001` / `…_H1M15_DERIVED_001` | SEALED_OOS | reserved |
| `D:\EURUSD_M1_*` (6 files, May–Jul 2026) | OVERLAPS_SEALED_OOS | |
| `D:\EURUSD_M5/M15/H1/Daily` 2025→2026 | OVERLAPS_SEALED_OOS from 2025-09-14 | These reproduce the sealed prices exactly (SSC remediation evidence). |
| ↳ their pre-sealed portion (2025-01-02 → 2025-09-12) | **DEVELOPMENT_ELIGIBLE** (M5 from 2025-04-21) | See the timezone note below. |
| `D:\EURUSD_M15_202210…` (3 weeks, 2022) | INSUFFICIENT_TIMEFRAME | no M1/M5 |
| `SSC1D_WP1_OOS_EURUSD_2024Q1` | INSUFFICIENT_TIMEFRAME | M15/H1 only |
| `SSC_V1_0_1_G2_DEV_001` | **DEVELOPMENT_ELIGIBLE** | M1+M15, 30 days; already consumed by Asian Sweep (a different family) |
| `SSC_V1_0_1_G2_DEV_002` | duplicate of G2_DEV_001 | byte-identical M1/M15 |
| `SSC_FRESH_DEV_GEN_002` | QUARANTINED | unchanged |

**Timezone finding.** The `D:\` dataset registrations state a *constant* broker offset of +3h. Every pre-sealed week, winter included, opens Monday 00:00 broker time. That means the server tracks the New York close (**+2h in winter**, +3h in summer), so the registered UTC conversion is wrong for 2025-01-02 → 2025-03-08. Those registrations were not edited. Winter data was not used.

**New development dataset (commit `aedb4f8`):** `data/research/fx_discovery_v1/EURUSD_DEV2025_M5_UTC.csv` (sha256 LF `aad5e7d7…`).
- It is the pre-sealed M5 from 2025-04-21 to 2025-09-12, entirely within US-DST summer, converted as broker − 3h.
- The source sha256 `0c269b9a…` matches its owner-authorized registration.
- It aggregates exactly to the independent `D:\` M15 export (10,008/10,008) and H1 export (2,502/2,502).
- It covers 105 weekdays; the only gap is the partial first day.

## Phase 2 / 3 — OSS and semantic parity (commit `c38f53b`)

See `docs/research/FX_DISCOVERY_V1_SEMANTIC_PARITY.md`.

| Project | Commit / version | License | Decision |
|---|---|---|---|
| smart-money-concepts | `1b62fd6c…` / 0.0.27 | MIT | Rejected for signals. It is non-causal: centered swings, synthetic endpoint swings, repainting; the future-mutation test fails. |
| smc-mcp | `719862b4…` / 0.1.0 | MIT | Semantic reference. Its swing and BOS/CHoCH logic is re-implemented in AG. Its sweep has a look-ahead defect that AG corrects. |
| pandas-ta-classic | `8afeec22…` / 0.8.33.dev171 | MIT | Indicator oracle. AG's EMA is identical; ATR differs only by seeding (≤3.9e-10 after warmup). |

No OSS package was added to the project environment. Canonical semantics were fixed in `src/fx_discovery/features.py` **before** any outcome existed.

## Phase 4 / 5 — candidate families and development run

- **Hypothesis ledger:** `config/research/FX_DISCOVERY_V1_HYPOTHESIS_LEDGER.yaml`, frozen in `b34ceca` before any outcome. It records 3 hypotheses, each a single fixed specification.
- **Implementation:** committed in `9e17b89` before the run. It includes a truncation look-ahead proof: every plan reproduces from data cut at its decision time.
- **Evidence:** `artifacts/research/FX_DISCOVERY_V1/DEVELOPMENT_RUN_V1.json`, **IN_SAMPLE / DEVELOPMENT**. Friction is 3.0 pips per trade (2.0 spread + 1.0 slippage; commission UNVERIFIED).

| Family | Resolved | Mean gross R | **Mean net R** | Net PF | Leave-top-3-out | Bootstrap 95% CI (net) | DEV2025 / G2 net | Pass |
|---|---|---|---|---|---|---|---|---|
| A_SSR: Asian sweep → M15 structural reclaim | 27 (24 time exits, 3 SL) | +0.153 | **−0.008** | 0.97 | −0.135 | (−0.271, +0.249) | +0.012 / −0.063 | no (N<40, net, PF, L3O) |
| B_HSF: H1 bias → M15 sweep → FVG limit retrace | 43 (+11 not filled, 1 ambiguous) | +0.211 | **−0.065** | 0.90 | −0.203 | (−0.451, +0.311) | +0.015 / −0.297 | no (net, PF, L3O) |
| C_LBR: London breakout → retest | 33 | −0.273 | **−0.705** | 0.35 | −0.947 | (−1.132, −0.242) | −0.555 / −1.262 | no (all criteria) |

What these results say, without changing any rule:
- **A and B have small positive gross expectancy** (+0.15R and +0.21R), which the 3-pip friction ceiling fully erases (it costs 0.16R and 0.28R per trade). Their confidence intervals straddle zero, so there is no evidence of an edge.
- **A rarely reaches its 2R target before 12:00 UTC**: 24 of 27 trades ended on the time exit.
- **C is negative even before friction.**

The pre-registered rule applies: no candidate is frozen, and SEALED_OOS is not consumed. Any follow-up variant (for example, a longer time exit for A, or a lower-friction scenario) would be a new ledger entry, bringing the hypothesis count to 4 or more, evaluated on development data only.
