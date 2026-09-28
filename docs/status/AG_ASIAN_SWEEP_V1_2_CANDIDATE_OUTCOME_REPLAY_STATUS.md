# ST_ASIAN_SWEEP_5R_V1@1.2.0-CANDIDATE — Contract Freeze + One-Shot Outcome Replay

**Date:** 2026-09-28
**Classification:** `V1_2_OUTCOME_EVIDENCE_READY`. This is evidence only. It is **not** ECONOMIC_STRATEGY_QUALIFICATION.
**Base:** `3474b132121345f604e8a0f57bb3b7dc1771489b` (identity verified)
**Contract freeze commit:** `0992103c3197a6ece56c1fb70692e79cdaf19a5c`. It was committed before the resolver was written or any outcome computed.
**Resolver + replay script commit:** `8a5e26705610fc6d6b8a23e955c4d930d88a3461`. It was committed before the replay was run.
**Authority:** PROPOSAL/DEMO/LIVE = NONE; TradeTicket NOT_CREATED. ST_ASIAN_SWEEP_5R_V1@1.1.1 semantics, registry, lifecycle and evidence are unchanged.

## Contract

- **File:** `config/governance/AG_OUTCOME_RESOLUTION_CONTRACT_V2.yaml`. Blob `1ce91a11`; sha256 (LF, as committed) `a5680bb014bff836ebc0536b91fe050cf84060d81d0bdbae6bec2eaf003128aa`. The replay re-verifies this hash.
- **Entry:** `SWEEP_CONFIRMATION_CANDLE_CLOSE`. The order is MARKET at the M15 sweep candle's **close price**, at its close time (`signal_timestamp + 15m`).
- **Resolution start:** `POST_FILL`. Only M1 bars that open at or after the fill participate.
- **Stop:** `SWEEP_WICK_EXTREME`. TP1 is the opposite box boundary for 75% of the position; the runner's stop then moves to entry, armed from the next bar. TP2 is 5R for the remaining 25%, with no trailing.
- **Session exit:** 11:00 UTC for POST_ASIAN and 15:00 UTC for POST_LONDON, as owner-signed in P1A.
- **Disabled:** structural invalidation, the EMA50 filter and the 25-pip range ceiling are all OFF.
- **Same-bar policy:** the existing signed conservative rule applies. A bar touching both SL and TP1, or both BE and TP2, is `AMBIGUOUS_SAME_BAR`: unscored and reported.
- **Missing M1** after the fill makes the observation `UNRESOLVED_MISSING_M1`; there is no M15 fallback.
- **Pre-registered exclusions:** `NO_POST_FILL_WINDOW`, `INVALID_RISK`, `TP1_NOT_BEYOND_ENTRY`.
- **Friction:** the `CONTRACT_CEILING` scenario: 2.0-pip spread + 1.0-pip slippage per trade. Commission is 0.0 and **UNVERIFIED**, not a confirmed broker fact. `friction_R = 3 pips / risk_distance`.

### V1.1.1 specification/implementation divergences (recorded, not repaired)

1. The engine's entry is `min/max(open, close)` (the body extreme), but the YAML and the ledger say the entry is the close. The engine value differs from the close in 26 of 38 Opportunities. V2 uses the close.
2. The YAML declares `stop_loss_mode: PERCENT_OF_SESSION_RANGE 0.25`, but it is loaded and never applied. V2 uses the wick extreme, which is what the engine produces.
3. The EMA_50 trend filter and the 25-pip range ceiling are declared but not implemented. They are OFF in V2.
4. `structural_invalidation` ("expansion volume") has no deterministic definition. It is OFF in V2.

## Historical V1 evidence

`artifacts/outcome_resolution/records/` (13 files) is **preserved unchanged**. Its content digest `5fcbd6dc…e3b1` is pinned by a test. The files remain attributed to `AG_OUTCOME_RESOLUTION_CONTRACT_V1_SIGNED`.

All 13 records are contaminated by pre-fill resolution: each one stops out inside the sweep candle's own 15 minutes. They are not V2 economic evidence.

## Dataset

- **ID:** `SSC_V1_0_1_G2_DEV_001` (VantageMarkets-Demo MT5, MetaTrader5 5.0.5735). Role DEVELOPMENT; not a holdout; not quarantined. GEN_002 was not used.
- **Hashes:**
  - M15 `cefed9705bf9609329183c9bc44b7536eafdf070950ff6bcd45b759623ccd063`
  - M1 `b760a2a65f8f453d121500657e824daec63579bfa4e67895e4501454dedc7458`
  - Both match the manifest's combined-fingerprint inputs.
- **M1 lineage:**
  - all 2,843 M15 bars that have a full set of 15 M1 bars aggregate exactly from M1, with 0 OHLC mismatches;
  - 0 missing M1 minutes across 12,600 trade-window minutes;
  - no duplicate or unordered timestamps;
  - timestamps are true UTC.

## One-shot replay

- **Command:** `python scripts/replay_outcomes_v2.py`. It ran once.
- **Output:** `artifacts/validation/AG_FX_OPPORTUNITY_FOUNDATION_V1/ST_ASIAN_SWEEP_5R_V1_1_2_0_CANDIDATE_OUTCOMES_V2.json`, which is write-once.
- **Coverage:** 30 trading days, 2026-06-22 → 2026-07-31.
- **Determinism:** an in-memory re-run to a scratch path produced a byte-for-byte identical report.

| | POST_ASIAN | POST_LONDON | COMBINED |
|---|---|---|---|
| Opportunities / filled / resolved | 21 / 21 / 21 | 17 / 16 / 16 | 38 / 37 / 37 |
| Ambiguous / unresolved / excluded | 0 / 0 / 0 | 0 / 0 / 1 (`NO_POST_FILL_WINDOW`) | 0 / 0 / 1 |
| States | SL 14, session exit 6, TP1→BE 1 | SL 11, session exit 4, TP1→BE 1 | SL 25, session exit 10, TP1→BE 2, TP2 0 |
| Gross win / loss / flat | 5 / 15 / 1 | 5 / 11 / 0 | 10 / 26 / 1 |
| Gross expectancy R (95% bootstrap CI) | −0.292 (−0.754, +0.246) | +0.780 (−0.776, +3.400) | +0.171 (−0.605, +1.444) |
| Gross profit factor | 0.567 | 2.135 | 1.252 |
| **Net win / loss** | 4 / 17 | 5 / 11 | 9 / 28 |
| **Net expectancy R (95% CI)** | **−1.141** (−1.728, −0.497) | **−0.472** (−1.985, +1.753) | **−0.852** (−1.622, +0.213) |
| **Net profit factor** | **0.193** | **0.689** | **0.416** |
| Total net R | −23.96 | −7.56 | −31.51 |
| Median net R | −1.600 | −1.404 | −1.517 |
| Friction drag R (total / mean per trade) | 17.82 / 0.848 | 20.04 / 1.252 | 37.86 / 1.023 |
| Median MFE / MAE R | +0.696 / −1.065 | +0.502 / −1.057 | +0.667 / −1.062 |
| Median holding (min) | 27.0 | 12.5 | 19.0 |

### Observations for the governance decision (no rule was changed)

- **Stops are very small relative to the friction ceiling.** Risk distance is a median 4.8 pips (range 0.6–23.9), and 13 of 37 trades are at or below 3 pips. The 3-pip friction ceiling therefore costs about 1.0R per trade on average.
- **POST_LONDON's positive gross result depends on one observation.** A session exit on 2026-07-08 with a sub-pip-scale stop scored +18.83R gross; without it, POST_LONDON gross is negative. The bootstrap CIs are correspondingly wide.
- **No trade reached TP2 (5R).** 25 of 37 resolved trades stopped out.
- **The sample is small:** N=37 resolved, one 30-day development window. That is insufficient for qualification under `config/governance/economic_gate_contract.yaml`, which requires walk-forward (≥3 windows), friction stress and a signed cost scenario.

These results reflect the currently implemented v1.1.1 detection plus the V2 outcome contract. Any change suggested by them (a stop floor, the EMA50 or range filter, etc.) must be a new, separately preregistered candidate. It must not be an edit to this contract.

## Tests and negative proof

- `tests/test_outcome_resolution_v2.py` (19 tests) passes. It covers:
  - **the reproduction of the historical defect:** a sweep-candle wick that touches the future stop before the close cannot resolve SL, and pre-fill bars are irrelevant to the result;
  - positive controls: an SL after entry, an SL on the first post-fill bar, TP1→BE, TP1→TP2, a session exit, and a SHORT symmetry case;
  - the same-bar ambiguity cases (both phases), missing M1, exclusions and friction;
  - future-mutation and determinism checks;
  - consistency between the contract and the resolver constants;
  - that the V1 records are untouched.
- `tests/test_fx_opportunity_runner.py`: 21 passed.
- Branch suite `pytest -q tests`: 520 passed, 4 skipped, 1 failed. The failure is the pre-existing `api.app` test, the same as the base.
- **Execution:** broker `order_check` = 0, `order_send` = 0, other mutations = 0.
  - In a fresh interpreter, importing `outcome_resolution.v2` and `fx_opportunity.runner` loads no module from `execution*`, `authorization`, `ticket_delivery`, `notifications`, `proposal_envelope`, `mt5.connection`, `mt5.account` or `mt5.management_gateway`.
  - `strategies/`, `strategy_lifecycle.yaml`, `proposal_eligibility.py` and the V1 records have a zero diff against the base.
- **Live MT5:** not retried during this mission, per Phase 8. It remains a separate runtime gate (`LIVE_MT5_AUTH_BLOCKED` as of 15:58 UTC).
