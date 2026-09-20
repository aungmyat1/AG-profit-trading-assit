# SVOS Virtual Demo Engine V1 — Cycle 3C canonical SSC bridge

Date: 2026-09-20. Classification: **VD_SSC_BRIDGE_READY**.

## Baseline and evidence

Cycle 3A was frozen first at `3fa107aec51db9d3871a5785c564429adf827623`. Cycle 3B is
`5dde62171ea280dd30cd79b7b62123b56a7d318f`; the temporal foundation is
`04a8d122682e0888d3260b103303576c887d83ee`; MI remains frozen at `415d062`.
HEAD before Cycle 3C was `5dde62171ea280dd30cd79b7b62123b56a7d318f`; the final
implementation commit is recorded by the repository after this status is added.
No unrelated WIP was present. No frozen source was modified.

## SSC consumption map and bridge contract

The bridge consumes `ReplayResult.symbol`, `session_pair`, `campaign`,
`accepted_setups`, `rejected_setups`, and each accepted setup's `setup_model`,
`direction`, `entry_time`, `entry_price`, `stop_price`, `risk_pct`, and canonical
outcome `partial_target_price`. These are direct canonical fields. Decision cutoff is
derived as M15 `entry_time + 15 minutes` only when the caller does not supply the
explicit admitted cutoff. Proposal identity is deterministically derived from dataset,
decision event, campaign, setup index, and canonical setup payload. Strategy ID/version
come from the canonical SSC package constants. Position size/lots, account fields,
margin, currency conversion, costs, and latency are unresolved/not required here.

`SSCToVirtualOrderBridge.build()` returns either explicit `NO_SETUP`/`REJECTED` with
zero intents or actionable `SSCVirtualOrderIntent` objects. It validates dataset/event
identity, campaign presence, setup direction, prices, and cutoff. It never calls the
exchange, fills an order, sizes a trade, or mutates SSC output. `ResearchReferenceEntry`
is retained inside the proposal; it is not executable fill evidence.

## Proofs

The controlled actionable case preserves SSC identity/version, campaign/setup/risk,
direction, reference entry, stop, target, dataset/event IDs, and M1 lineage, then hands
off to Cycle 3B. The exchange ignores the pre-cutoff bar, fills from the first strictly
post-cutoff M1 bar, and records both reference and executable prices. No reference-price
equality is asserted. NO_SETUP and rejected ReplayResults create no virtual order;
incomplete actionable setup and missing identity fail closed. Repeated equivalent
ReplayResults produce the same semantic proposal ID. Symbol/dataset mismatch and
unsupported evidence are rejected by the exchange. No raw/live MT5 path exists.

## Verification

- `python -m pytest -q tests/test_svos_ssc_bridge_cycle3c.py tests/test_svos_virtual_exchange_cycle3b.py` → **14 passed**.
- `python -m pytest -q tests/test_svos_ssc_bridge_cycle3c.py tests/test_svos_virtual_exchange_cycle3b.py tests/test_svos_virtual_time_cycle2.py tests/test_svos_mt5_isolation.py tests/test_svos_context_authority.py tests/test_svos_ssc_adapter.py tests/test_session_sweep_continuation_replay_determinism.py tests/test_session_sweep_continuation_canonical_observations.py tests/test_session_sweep_continuation_v1_0_1_exit_semantic_remediation.py tests/test_session_sweep_continuation_campaign.py tests/test_td8e_evaluation_context.py tests/test_td8e_ssc_reference_completeness.py tests/test_market_intelligence_v1_core.py tests/test_market_intelligence_v1_cycle3_parity.py tests/test_market_intelligence_v1_cycle4_ssc.py` → **108 passed**.

## Readiness and safety

`engineering_ready = true`; `integration_ready = true` for this narrow controlled
bridge-to-exchange handoff; `economic_qualification_ready = false`. Canonical SSC
integration preserves the known legacy research-fill versus causal virtual-fill
distinction. No SSC semantic or parameter change, VirtualAccount, sizing, cost,
latency calibration, economics, protected/holdout/OOS access, campaign, Demo/Live
order, optimization, or execution-authority change occurred.
