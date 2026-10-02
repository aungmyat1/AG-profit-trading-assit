# AG_CRYPTO_CFD_STRATEGY_CONTRACT_V1 — BTCUSD / ETHUSD CFD Strategy Contract

**Date:** 2026-10-02
**Classification:** Deterministic strategy contract, RESEARCH_ONLY.
**Authorization:** This document grants no edge claim, no proposal authority, no
risk-sizing authority, and no Demo/Live execution authority.

## Base authority

Built directly on current `origin/main`:

```text
BASE_SHA  = eb834dbd6f5eec23a05f2cda8ad6e19d5d32a3ec
BASE_TREE = 9d435bd9db1b1270eb70f60ddbd759a9afa34249
```

Frozen authorities verified present at BASE_SHA and left unchanged:

- Checklist V1.1 — `src/session_scanner/checklist_v1_1.py`
- Crypto observation layer — `src/session_scanner/crypto_adapter.py` +
  `docs/status/AG_CRYPTO_SCANNER_V1_OBSERVATION_STATUS.md` (PR #28)
- Message Router V1 — `src/session_scanner/message_router.py` (PR #27, merged at BASE_SHA)

## Objective and scope

The frozen crypto observation layer fails closed for the VT Markets **BTCUSD/ETHUSD
CFDs** with `STRATEGY_CONTRACT_INCOMPLETE`, because the only registered crypto strategy
profile covers **BTCUSDT/ETHUSDT USDT perpetuals**. This contract closes that gap with a
dedicated CFD contract:

```text
instruments  = BTCUSD, ETHUSD
asset_class  = CRYPTO_CFD
contract_id  = ST_CRYPTO_CFD_SWEEP_RETEST_V1 (v1.0.0)
```

Explicitly **not reused** (hard separation, enforced by tests):

- BTCUSDT/ETHUSDT identities, USDT-perpetual funding assumptions
- perp tick model (`strategy_engine/sweep_retest/crypto_symbols.py`)
- perp strategy-activity window (13:30–16:00 UTC)
- perp risk contract (0.5% fixed risk)
- FX session gating, FX execution windows, FX pip conventions

**Reused** (asset-independent primitives, documented as shared across asset classes by
`strategy_engine/sweep_retest/profile.py` — this is capability reuse, not perp-contract
reuse): `sweep.find_qualified_sweep`, `mss.find_mss`, `retest.find_retest`,
`targets.build_target_plan`, `market_structure.structural_breaks_for_candles`, and the
generic reference-box formula.

## Authorities

| Artifact | Role |
|---|---|
| `strategies/ST_CRYPTO_CFD_SWEEP_RETEST_V1.yaml` | Machine-readable contract (authoritative) |
| `src/crypto_cfd_contract/contract.py` | Frozen constants, status vocabulary |
| `src/crypto_cfd_contract/rules.py` | Pure deterministic evaluation (`evaluate()`) |
| `tests/test_crypto_cfd_strategy_contract_v1.py` | Mission test matrix (30 tests) |
| `strategies/registry.yaml` + `strategies/STRATEGY_LEDGER.md` | Registration, no authority change |

## Frozen deterministic rules

Every predicate is an exact machine-testable rule — no "strong CHoCH", "good POI",
"clear sweep", or "nice retest" anywhere.

| Rule | Frozen definition |
|---|---|
| D1 context | Direction of most recent CONFIRMED D1 structural break (`structural_breaks_for_candles`, swing_length 5, close_break true): BULLISH / BEARISH / UNRESOLVED. Context record + veto input only, never an entry. |
| H1 bias | Same rule on closed H1 candles. BULLISH → `LONG_ALLOWED` (LOW sweeps only); BEARISH → `SHORT_ALLOWED` (HIGH sweeps only); UNRESOLVED → `NO_DIRECTION`. |
| Direction permission | Confirmed D1 opposing H1 → `NO_DIRECTION` (`HTF_DIRECTION_CONFLICT`); UNRESOLVED D1 → H1 governs alone (observed live: D1 structural history can be insufficient for these CFDs). |
| Liquidity reference | `PREV_UTC_DAY_HIGH/LOW/MID` from the previous UTC calendar day `[D-1 00:00, D 00:00)`. Completeness: exactly 288 closed M5 bars (CRYPTO_24H_OBSERVATION declares no daily break) else `REFERENCE_INCOMPLETE`, fail-closed. Maximum age: one UTC day (rotates at UTC midnight). Minimum penetration: strict float inequality (broker quantum 0.01 = 1 point). Close-back: same candle must close back inside. |
| POI | Allowed: `PREV_UTC_DAY_EXTREME` (sweep location) and `BROKEN_M5_SWING` (most recent confirmed M5 swing via `full_swings`, swing_length 5, located strictly from current-day candles up to and including the sweep candle). FVG / order block / range boundary: **NOT_AUTHORIZED** (no supporting detection rule exists for these CFDs — `fvg_or_order_block_alternative=false` family evidence). Discretionary POI selection forbidden. |
| M15 | Observation-only structure record; gates nothing in V1 (deterministically declared, not silently ignored). |
| M5 sweep | Closed M5 candle: `high > PDH AND close < PDH` (short) / `low < PDL AND close > PDL` (long), current UTC day only, H1-permission side only; dual-side candle skipped as ambiguous. |
| CHoCH/MSS | A SUBSEQUENT closed M5 candle with `close` strictly beyond the located swing. Intrabar wick penetration explicitly insufficient. Bounded by UTC-day rotation. |
| Retest | First closed M5 candle strictly after the MSS candle whose wick reaches the broken swing (`high >= swing` short / `low <= swing` long). Tolerance 0.00. Window: 3 completed M5 bars (`ENTRY_TTL_M5_BARS`). |
| Entry timing | `AT_FIRST_VALID_RETEST_TOUCH`; entry price = broken swing price (limit level known at MSS confirmation). No displacement-candle chase. |
| Signal expiry | No retest within 3 completed M5 bars, or UTC-day rotation → `SIGNAL_ENTRY_WINDOW_PASSED` (Checklist V1.1 reason code). |
| Stop loss | Short: sweep candle high + buffer; Long: sweep candle low − buffer. `STOP_BUFFER_POLICY_V1 = ZERO_PRICE_BUFFER`, a **PREREGISTERED_RESEARCH_HYPOTHESIS**: zero is the only buffer that adds no invented number — it is NOT a claim of economic correctness. The broker's `tick_size=0.0` is insufficient metadata, not justification; whether the exact sweep extreme survives real spread/wick noise is a research question. Any non-zero buffer = new candidate/version. Non-positive stop distance → `INVALID_STOP_DISTANCE`. |
| Targets | Partial + runner via the shared frozen target-plan path: TP1 = previous-day mid (50%, move remainder to breakeven), TP2 = opposing day extreme (opposing liquidity), minimum TP2 R = 1.5 (contractual family value — generic RR ≥ 2 deliberately NOT imposed). Invalid geometry → `NO_TRADE_TARGET_GEOMETRY`, no substitute target invented. |
| Session/time policy | `BROKER_DEFINED / 24H_OBSERVATION`. `fx_session_gate_applied=false`, `execution_windows=[]`. Intraday time-of-day ideas remain research hypotheses outside proposal authority. |
| Spread/cost policy | Native broker units only (points / price / percent; observed 2026-10-02: BTCUSD 1702 points, ETHUSD 250 points — informational). No validated threshold exists → `SPREAD_POLICY_UNDEFINED`, proposal authority stays BLOCKED. |
| Risk policy interface | `RISK_POLICY_AMBIGUOUS` — no governance-authorized risk percent exists and none is invented. Required sizing inputs are defined (equity, authorized risk %, stop distance, tick_size/tick_value, volume constraints); broker tick_size/tick_value currently 0.0 → sizing not computable regardless. `position_size = NOT_CALCULATED`. |

## Status classification

```text
BTCUSD = CONTRACT_COMPLETE
ETHUSD = CONTRACT_COMPLETE
```

`CONTRACT_COMPLETE` means every rule above is deterministic and reproducible — nothing
more. Research separation is explicit and independent:

```text
STRATEGY_CONTRACT_VALID = TRUE   (reproducible logic only)
EDGE_VERIFIED           = FALSE
RISK_AUTHORIZED         = FALSE
```

Open authorities keeping proposal eligibility BLOCKED: `SPREAD_POLICY_UNDEFINED`,
`RISK_POLICY_AMBIGUOUS`, sizing metadata incomplete (broker tick_size/tick_value 0.0).
`execution_authorized` is a constant `False` throughout the package. Wiring this
contract into the session scanner / Checklist V1.1 adapters is a separate, future
authority decision — this change alters no scanner behavior.

## Evidence

- `pytest tests/test_crypto_cfd_strategy_contract_v1.py` → 30 passed (mission matrix:
  four instrument examples, valid/invalid sweep, valid/invalid MSS, valid retest,
  expired setup, invalidation, target construction, no FX-session leakage, no
  perp-contract leakage including a static source scan of the package).
- Frozen-surface regression: scanner V1 / checklist V1.1 / crypto observation /
  message router / sweep-retest test suites unchanged and passing.
- `python -m compileall` over the new package and test: PASS.
- Static mutation scan of `src/crypto_cfd_contract/`: no broker-mutating import, no
  `order_send`, no execution path. `BROKER_ORDERS_SENT = 0`.
