# AG Crypto Opportunity Scanner V1 R2 Status

Date: 2026-09-27

Classification: `CRYPTO_OPPORTUNITY_SCANNER_V1_R2_READY_FOR_REAUDIT`

Base: `f42b803e7af6f6b25b372f5b0f00a85248882bc0`

Failed V1: `24ad2235948c50dcd34e5c7d51d7887dadc3f400`

R1: `2da5ee153242f61bde850b186ac0c1b9de7cb9bd`

Branch: `fix/crypto-opportunity-scanner-v1-r2`

## Remediation

Reproduced the R1 defect before editing: adding a caller-created REAL/BYBIT window to
`_LIVE_FEED_WINDOWS` and invoking `_scan_window` returned `OPPORTUNITY_UPDATED` and
persisted one candidate with `market_data_mode=REAL` and provider `BYBIT`.

R2 removes `_LIVE_FEED_WINDOWS`. Offline `scan_window`, `_scan_window`,
`_form_offline_opportunity`, and `_marketstate` reject REAL windows. The pure
`_evaluate_sweep` helper returns strategy facts only; it does not form an Opportunity
or provenance-bearing MarketState. The one production entrypoint, `scan_live_once`,
accepts a store but no caller-supplied window. It acquires Bybit candles itself, validates
the normalized M5 series and freshness, evaluates the strategy, and forms/stores REAL
MarketState and Opportunity only after acquisition succeeds.

The test-double composition test replaces only the feed acquisition boundary, confirms
the entrypoint requests BTCUSDT/M5/720 candles, and proves successful composition can
produce a REAL candidate. It is explicitly an offline test double, not live Bybit proof.
The failure test simulates HTTP 403 and confirms no REAL MarketState, candidate, or store
record is produced. Fixture/replay behavior remains deterministic and non-REAL.

## Verification

Environment: Windows, Python 3.14.0, pytest 8.3.5.

- Compiled all changed Python paths and imported `crypto_opportunity_scanner` — passed.
- `PYTHONPATH=src python -m pytest -q tests/test_crypto_opportunity_scanner.py` — **22 passed**, 0 failed. One Starlette/httpx `TestClient` deprecation warning.
- Bounded selection over scanner, Opportunity contracts/engine/store/import boundaries, Bybit feed, API, and architecture checks — **152 passed, 1 deselected**. The deselected test is `test_production_runtime_and_authority_files_match_frozen_base`; its hard-coded base predates the scanner feature and its whole-repository snapshot check fails on the already-existing V1/API additions. The other four architecture tests passed.
- The candidate-path diffs from R1 contain only scanner code, scanner tests, rolling status, README, docs index, and this R2 status record. Foundation, FX R1.1, risk config, execution runtime, and MT5 gateway paths are unchanged.
- No Bybit network request was made in R2 remediation, per scope. Connectivity remains a separate follow-up gate.
- `git diff --check` — passed before commit.

## Preserved behavior and safety

The focused scanner suite covers closed/forming and stale candles, weekend crypto,
no-setup behavior, candidate deduplication, a distinct later event, and read-only API
projection. An explicit observation-time test confirms the same event keeps the same
candidate ID and one store record when observed one minute later. The Bybit feed suite
covers normalized oldest-first closed data, malformed/empty payloads, symbol/timeframe
scope, stale/forming-only responses, and absence of auth headers/credentials.

No private Bybit, Bybit order, MT5 order-check/send, position, CanonicalProposal, or
OwnerDecision action was invoked. Crypto execution remains MT5-only in the wider system;
this scanner has no execution authority.

## Next gate

`AG_CRYPTO_OPPORTUNITY_SCANNER_V1_R2_INDEPENDENT_REAUDIT`
