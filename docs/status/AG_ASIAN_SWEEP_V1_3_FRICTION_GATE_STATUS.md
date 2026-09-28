# ST_ASIAN_SWEEP_5R_V1 V1.3 — Friction-to-Risk Admission Experiment

**Date:** 2026-09-28
**Classification:** `THRESHOLD_PREREGISTRATION_REQUIRED`
**Base:** `8e09daf122ab3ebf96f8057b8c0121d21c7bf300` (identity verified)
**Authority:** PROPOSAL/DEMO/LIVE = NONE; TradeTicket NOT_CREATED. No execution module was restored. Broker `order_check`/`order_send`/mutations = 0; no MT5 contact at all.

No V1.3 outcome, stop-distance distribution or friction-ratio distribution was computed.

## V1.2 governance freeze

`ST_ASIAN_SWEEP_5R_V1@1.2.0-CANDIDATE` is recorded as follows:
- TECHNICAL_PIPELINE = **VALIDATED**
- ECONOMIC_RESULT = **NEGATIVE_BASELINE** (combined N=37, gross +0.171R, net −0.852R, net PF 0.416)
- PROPOSAL/DEMO/LIVE authority = **NONE**

The following are preserved unchanged:
- the V1 contract and the 13 V1 records;
- the V2 contract (`a5680bb0…`);
- the V1.2 evidence JSON;
- the dataset hashes.

`SSC_V1_0_1_G2_DEV_001` is **closed to further optimization**.

## Why V1.3 stopped

The mission requires exactly one `MAX_FRICTION_TO_RISK` value, with a rationale independent of G2_DEV_001.

- **Repository search.** The branch and the `2b75bbf` lineage were searched: `src/`, `config/`, `strategies/` and the Large-SMC friction research. No per-trade friction-to-risk threshold exists.
  - `fx_friction_research/c10_friction_ratios.py` is explicitly descriptive and sets no threshold.
  - `economic_gate_contract.yaml`'s `maximum_friction_degradation_pct: 50` is scoped to SSC and is portfolio-level (net vs gross expectancy). Mapping it onto a per-trade stop ratio would need an assumed per-trade gross expectancy, and the only available figure is G2's, which is forbidden.
- **Agent contamination.** The agent running this mission has already observed G2's stop-distance distribution (median 4.8 pips, 13 of 37 at or below 3 pips) alongside its outcomes. Any value it chose would not be independent.

The threshold must therefore be preregistered by the owner. For reference, the implied minimum stop at the frozen 3.0-pip friction is `3.0 / MAX_FRICTION_TO_RISK` pips: 0.10 → 30 pips, 0.25 → 12, 0.50 → 6. This is pure arithmetic, not a recommendation.

## Work completed without contamination: OOS dataset qualified

The details are recorded in `config/governance/AG_ASIAN_SWEEP_V1_3_FRICTION_GATE_CONTRACT_DRAFT.yaml` (status `PROPOSED_UNSIGNED`, threshold `null`).

- **M1:** `SSC_V1_0_1_HIST_1Y_M1_001`, sha256 `50beb42a…2f8a`, which matches its manifest.
  - Native VantageMarkets-Demo MT5 `copy_rates_range`, owner-authorized 2026-09-19, UTC-normalized across 53 offset segments.
  - The file exists only in `2b75bbf` (blob `ef5e2470`). It was verified from a scratch extraction and is not yet restored into the tree.
- **M15:** `SSC_V1_0_1_HIST_1Y_H1M15_DERIVED_001`, sha256 `c9833427…6956`, which matches its manifest. It is a deterministic aggregation of that M1.
- **OOS period:** weekdays from 2025-09-15 to 2026-09-15, excluding G2's `[2026-06-20, 2026-08-03)`. That is 232 weekdays.
- **Checks:**
  - M1→M15: 21,666/21,666 full buckets exact; 0 mismatches.
  - UTC: Sunday opens consistent across DST.
  - Coverage: 1,710 missing minutes. Two holidays account for 1,680; 30 minutes are spread over 6 days. The V2 missing-data policy covers them.
  - Not quarantined: the GEN_002 quarantine names this package the canonical one-year M1 authority.
- **Rejected sources:**
  - `SSC_V1_0_1_G2_DEV_002`: its M1 and M15 are byte-identical to DEV_001, so it is not OOS.
  - GEN_002: quarantined.
  - `SSC1D_WP1_OOS_EURUSD_2024Q1`: no M1.
- **Optional, not yet evaluated:** the WP3A.1 friction campaign's Vantage Demo EURUSD spread observations predate this experiment and could serve as an additional preregistered friction scenario.

## To resume

1. The owner sets `max_friction_to_risk` and `threshold_rationale` in the draft and signs it; that commit is the contract freeze.
2. Restore the one-year M1 file byte-exact from `2b75bbf` (blob `ef5e2470`), verifying its hash against the contract.
3. Run the one-shot CONTROL (V1.2) vs TREATMENT (V1.3) replay over the identical OOS Opportunity population.
