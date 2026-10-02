# AG Crypto Scanner V1 — BTCUSD / ETHUSD Observation Status

**Date:** 2026-10-03
**Classification:** `DEMO_VERIFIED` for read-only market-data observation only
**Authorization:** Informational status. This document grants no strategy, proposal,
risk-sizing, Demo-order, or Live-order authority.

## Frozen merge lineage

PR [#28](https://github.com/aungmyat1/AG-profit-trading-assit/pull/28) merged the
observation-only implementation. The frozen post-merge `main` snapshot at merge was:

```text
MAIN_SHA_AT_CRYPTO_SCANNER_MERGE = 5fa46102aabac97773ef66aa3f0ed10561ad66b1
PR_HEAD_SHA = e9d6d608369b24de3849575790c82f2bc7d96045
PR_PARENT_SHA = e64e887c063cca4ae911762037e70c04a380455c
```

The current branch containing this status document is based on that frozen merge SHA.
The crypto observation layer is additive to Scanner V1 and Checklist V1.1.

## Authority and result

The live VT Markets Demo symbol search independently found exactly one matching full-
trade symbol for each canonical instrument:

| Canonical symbol | Broker symbol | Description | Trade mode | Digits / point | Tick size / value | Contract size |
|---|---|---|---|---|---|---|
| BTCUSD | BTCUSD | Bitcoin | full | 2 / 0.01 | 0.0 / 0.0 | 1.0 |
| ETHUSD | ETHUSD | Ethereum | full | 2 / 0.01 | 0.0 / 0.0 | 1.0 |

Terminal MCP returned zero for tick size and tick value on both symbols. Those values
are recorded as returned; no older capture or USDT-perpetual tick assumption was used
to fill them. The observed CFD contract metadata is therefore incomplete for any
position sizing use.

The registered `ST_LIQUIDITY_SWEEP_RETEST_V1` crypto profile covers BTCUSDT/ETHUSDT
perpetuals, not these USD CFDs. It was not reused. For both CFDs:

```text
STRATEGY_CONTRACT = STRATEGY_CONTRACT_INCOMPLETE
RISK_POLICY = RISK_POLICY_AMBIGUOUS
POSITION_SIZE = NOT_CALCULATED
SETUP_VALID = FALSE
PROPOSAL_ELIGIBLE = FALSE
EXECUTION_AUTHORIZED = FALSE
```

Checklist context passed when the runtime session label was `OFF_SESSION`, with
`fx_session_gate_applied=false`. Location and trigger remain incomplete-contract
observations; the scanner did not claim a valid setup. D1 bars passed the data series
gate, but the available D1 structural history was insufficient for D1 structure
classification. H1 structure was available for descriptive context.

## Read-only runtime evidence

Environment: Windows host, account type `demo`, server `VTMarkets-Demo`, Terminal MCP
listener `127.0.0.1:22346`. No credentials or account balances were included in output.
Quotes below were retrieved through the scanner's read-only tick-history path on
2026-10-02 UTC.

| Instrument | Bid | Ask | Spread points | Spread price | Spread percent |
|---|---:|---:|---:|---:|---:|
| BTCUSD | 84413.43 | 84430.45 | 1702 | 17.02 | 0.02016267% |
| ETHUSD | 2667.58 | 2670.08 | 250 | 2.50 | 0.09371790% |

Cost reporting uses native broker point, price, and percentage units. No FX pip
conversion or spread threshold is applied; `SPREAD_POLICY_UNDEFINED` remains expected.

All eight symbol/timeframe checks returned `VALID`, with last-closed timestamps equal
to the scanner's expected timestamps and no reported OHLC/order/duplicate/gap issues.
No history retry was needed in this capture.

| Instrument | D1 last closed UTC | H1 last closed UTC | M15 last closed UTC | M5 last closed UTC |
|---|---|---|---|---|
| BTCUSD | 2026-09-30 21:00 | 2026-10-02 19:00 | 2026-10-02 20:15 | 2026-10-02 20:30 |
| ETHUSD | 2026-09-30 21:00 | 2026-10-02 19:00 | 2026-10-02 20:15 | 2026-10-02 20:30 |

The D1 timestamp reflects the broker's current server-day closure expectation and passed
the scanner's freshness gate. Data support means deterministic read and quality-gate
coverage only; it does not certify D1 structure sufficiency or authorize a trade.

## Regression and safety evidence

On validation SHA `e9d6d608369b24de3849575790c82f2bc7d96045`:

```text
pytest tests/test_session_scanner_v1.py tests/test_session_scanner_sources.py \
  tests/test_session_scanner_data_quality_aggregate.py \
  tests/test_session_scanner_checklist_v1_1.py \
  tests/test_session_scanner_crypto_v1.py -q
84 passed

python -m compileall -q src/session_scanner scripts/run_session_scan.py \
  tests/test_session_scanner_crypto_v1.py
PASS

Static mutation scan across crypto/scanner/checklist/registry/quality paths
0 matches
```

`MUTATING_TOOLS_EXECUTED=0`, `BROKER_ORDERS_SENT=0`, and
`EXECUTION_AUTHORITY_ADDED=FALSE`. The scanner remains informational and fail-closed
for the crypto CFDs.

## Remaining authority gap

Define and separately validate a BTCUSD/ETHUSD CFD strategy contract and risk policy
before considering strategy-valid setups, proposal eligibility, or size calculation.
That work is outside this status record. Preserve the perpetual strategy and all frozen
FX strategy/risk behavior unchanged.
