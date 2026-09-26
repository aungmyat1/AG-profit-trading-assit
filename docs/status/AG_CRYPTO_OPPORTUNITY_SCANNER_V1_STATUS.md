# AG Crypto Opportunity Scanner V1 Status

Date: 2026-09-27
Classification: `CRYPTO_OPPORTUNITY_SCANNER_V1_READY_FOR_INDEPENDENT_AUDIT`
Capability: `UNIT_TESTED`; live Bybit observation blocked
Base: `f42b803e7af6f6b25b372f5b0f00a85248882bc0`
Branch: `feature/crypto-opportunity-scanner-v1`

## Scope and authority

The one-shot scanner is bounded to `BTCUSDT` on Bybit linear perpetual public market
data and M5. It normalizes UTC bar times, rejects a forming final bar and stale closed
data, and checks a deterministic previous-UTC-day high/low wick rejection. A qualifying
observation becomes an early-stage `OpportunityCandidate` and is persisted using the
existing CandidateStore. `GET /api/opportunities` is a read-only projection.

The observer's code-defined identity is
`CRYPTO_PREVIOUS_DAY_SWEEP_OBSERVATION_V1`, version `1.0.0`, classified
`RESEARCH / OBSERVATION`. It reuses the closed-bar sweep/rejection semantics from
`ST_LIQUIDITY_SWEEP_RETEST_V1` v2.0.0, whose registry status remains research-only,
inactive for live/demo authorization, and not economically validated by this scanner.
This observer is not a registered or execution-dispatchable trading strategy. It omits
trade direction and geometry and does not create proposal eligibility, risk sizing,
CanonicalProposal, OwnerDecision, or broker instructions.

Crypto execution remains MT5-only. This change adds no MT5 or Bybit order route, no
private Bybit API, no credentials, no AI calls, and no position/account mutation. The
scanner ends at Opportunity.

## Verification

Environment: Windows, `C:\Python314\python.exe`, Python 3.14.0, pytest 8.3.5.

- `python -m pytest -q tests/test_crypto_opportunity_scanner.py` — **15 passed**, 0
  failed, 0 skipped (plugin autoload disabled for this deterministic run; test semantics
  unchanged). A Starlette/httpx deprecation warning is emitted by the API TestClient.
- Bounded regression command over Opportunity contracts/engine/store/import boundaries,
  Bybit feed, and opportunity-analysis API tests — **126 passed**, 0 failed, 0 skipped.
- `git diff --check` — passed.
- One read-only `scan_live_once` observation — `VENUE_UNAVAILABLE`, feed reason
  `KLINES_REQUEST_FAILED`. No MarketState or candidate was returned. No retry was made.

The live failure is recorded separately from deterministic engineering verification.
There is no claim that BTCUSDT data was reachable/current, that the strategy evaluated
real data, or that a real opportunity existed. Fixture input remains SYNTHETIC/REPLAY;
the public scan path alone can mark input REAL after fetching from the Bybit feed.

## Safety results

`PUBLIC_DATA_ONLY=YES`; private Bybit/account/position/order endpoints and credentials are
absent from the scanner path. `BYBIT_ORDER_CALLS=0`, `MT5_ORDER_CALLS=0`,
`POSITIONS_OPENED=0`, `CANONICAL_PROPOSAL_CREATED=NO`, and `OWNER_DECISION_CREATED=NO`.
`CRYPTO_EXECUTION_AUTHORITY=MT5_ONLY`. No weekend FX gate is applied to this crypto
observer. Repeated identical event identity deduplicates; a later bar has a distinct
identity. No-setup input creates no candidate.

## Changed paths

The candidate changes are limited to scanner implementation, its one-shot script, the
read-only API/schema projection, focused tests, and this milestone/status documentation.
No strategy YAML/registry, risk, execution, MT5 gateway, FX R1.1, or Foundation file was
changed.

Next gate: `AG_CRYPTO_OPPORTUNITY_SCANNER_V1_INDEPENDENT_AUDIT`.
