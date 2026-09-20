# SVOS Virtual Demo Engine V1 — Cycle 2 freeze and Cycle 3A adjudication

Date: 2026-09-20. Final classification: **VD_EXCHANGE_INPUTS_READY** (engineering fixtures only; integrated exchange and economic qualification blocked).

## Phase A: temporal foundation freeze

HEAD at start: `415d0622b82a8bedbabdc620d018969cec51c2cb`. Preflight found only the 13 mission-owned Cycle 1/2 paths: eight design/contract artifacts, clock/feed implementation, focused test, Cycle 2 status, and rolling/index edits. No proposal ledger, validation session, journal, or other unrelated WIP was present or staged. All Cycle 1/2 files and the two tracked diffs were reviewed. `VD_COMPONENT_AUTHORITY_MAP.json` parsed; `git diff --check` passed. MI manifest ancestry (`f4a1045`, `93586ec`, `cbb6a43`, `2597547`, `c435dba`) was verified. No MI/TD-8E/SSC source changed.

Freeze regression: `python -m pytest -q tests/test_svos_virtual_time_cycle2.py tests/test_td8e_evaluation_context.py tests/test_td8e_ssc_reference_completeness.py tests/test_td8e_shared_consumer_integration.py tests/test_market_intelligence_v1_core.py tests/test_market_intelligence_v1_cycle3_parity.py tests/test_market_intelligence_v1_cycle4_ssc.py` → **39 passed** (Windows PowerShell, local Python, controlled fixtures; no broker calls). Explicit path staging and `git diff --cached --check` preceded commit. **VD_TEMPORAL_FOUNDATION_FROZEN = `04a8d122682e0888d3260b103303576c887d83ee`**. Worktree clean immediately after freeze.

## Phase B: input authority

The machine-readable inventory is `docs/svos/VD_EXECUTION_INPUT_AUTHORITY.json`; the draft profile is `docs/svos/VD_EXECUTION_PROFILE_V1_DRAFT.json`. Their values are dated repository evidence, not a current broker re-query or a broker specification for a future sealed dataset. EURUSD broker observations establish digits 5, point/tick size 0.00001, 100,000 EUR/lot, and USD 1/tick/lot. Pip size 0.0001 is derived from this five-digit contract. A historical Vantage Demo account was USD; the future VD account currency remains unselected. EUR/USD base/quote and USD linear P&L are instrument derivations that require profile binding before cash accounting. EUR is the observed broker margin currency; margin rate, min/max volume, and volume step lack bound authority and remain unavailable. A USD VD profile would need no cross-currency conversion for quote-currency P&L; other account currencies require an admitted conversion source. No conversion rate is assumed.

Current intended SSC M1 source is MT5 native **bid-based OHLCV** (`OHLC_M1`). Its CSV includes a spread column, but that is not synchronized bid/ask OHLC, is not carried by TD-8E `Candle`, and lacks a frozen point-in-time interpretation for exchange pricing. A limited tick export has unverified provenance and does not cover the cited missing one-year interval. Neither `REAL_TICK` nor `BID_ASK_M1` is admitted.

## Timing and ambiguity adjudication

`run_replay` steps at each M15 close (`candle.time + 15 minutes`). S1/S2/S3 use that candle's close as `entry_price`, then `apply_entry` stores `candle.time` (bar open) as `entry_time`. The canonical outcome resolver marks an accepted entry `ORDER_FILLED` at signal close by construction; it has no pending-order phase. With M1 input, `_m1_subsequent_candles` filters M1 **open** strictly after `entry_time`, not strictly after M15 decision close. Thus canonical research results can include M1 bars inside the trigger M15 candle for outcome resolution. This is a genuine semantic mismatch with the Cycle 1 causal VirtualExchange contract, which prohibits a trigger-bar fill or pre-decision stop/target evaluation. The exchange must preserve the `run_replay` decision and record the legacy fill/outcome separately; it cannot reuse the legacy fill as an executable virtual order. Future integrated decision/economic parity requires an explicit separate bridge adjudication and test vectors. No SSC rule was altered here.

For VirtualExchange, proposal creation is no earlier than the admitted M15 close. The first eligible M1 interval must start strictly after that cutoff and after frozen latency; executable side price is still unresolved because only bid OHLC exists. Stops and targets start only after a verified virtual fill. SSC already resolves a bar touching both SL and partial target, or runner BE and runner target, to `AMBIGUOUS_SEQUENCE`; the draft exchange profile preserves explicit ambiguity and leaves cash/R outcome unresolved. It does not choose the favorable path or claim tick ordering.

## Friction and readiness

SSC YAML's EURUSD defaults are 1.0 spread, 0.2 commission, 0.3 slippage pips, all **PROJECT_CANONICAL MODELED** research parameters under `estimate_friction`; they are not broker observations. Separate Large-SMC EURUSD read-only spread evidence has 12 available session summaries across 2026-09-16 to 2026-09-18, 120 samples each, with window medians roughly 1.30–1.40 pips. This is **EMPIRICALLY_OBSERVED** Vantage Demo spread evidence and an empirical proxy, not an SSC historical executable spread series or a completed five-day campaign. No EURUSD broker commission schedule is established; one computable favorable slippage observation is insufficient for a distribution. Their broker-specific classifications remain **UNAVAILABLE**, never zero. The Large-SMC proposed friction policy is not transplanted into SSC.

`engineering_ready = true` only for isolated, deterministic exchange-model fixtures with explicit unknowns, rejection, and ambiguity behavior. `integration_ready = false`; `economic_qualification_ready = false`. Required next inputs are a causal SSC proposal/legacy-fill bridge, frozen latency and executable bid/ask/spread model, broker volume constraints, fee/slippage authority or expressly preregistered assumptions, account/currency/margin profile, and sealed-data/economic preregistration. No sealed dataset was chosen or opened.

## Safety

Cycle 3A adds adjudication documents only. No VirtualExchange/VirtualAccount implementation, optimization, protected-data access, holdout/OOS access, economic campaign, Demo/Live order, MI/TD-8E/SSC change, or execution-authority change.
