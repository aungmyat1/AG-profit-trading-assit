# AG Crypto Opportunity Scanner V1 R1 Status

Date: 2026-09-27

Classification: `CRYPTO_OPPORTUNITY_SCANNER_V1_R1_READY_FOR_REAUDIT`

Failed candidate: `24ad2235948c50dcd34e5c7d51d7887dadc3f400`

Foundation: `f42b803e7af6f6b25b372f5b0f00a85248882bc0`

R1 branch: `fix/crypto-opportunity-scanner-v1-r1`

## Remediation

Reproduced the failed candidate's `SyntaxError` with `py_compile` and package import.
Byte inspection found literal backslash-plus-`n` source suffixes in exactly three new
Python files: `src/crypto_opportunity_scanner/__init__.py`,
`src/crypto_opportunity_scanner/constants.py`, and the final line of
`src/crypto_opportunity_scanner/scanner.py`. Removed only those confirmed corrupt
suffixes.

The pre-fix adversarial probe called `_scan_window` with synthetic candles labeled REAL
and `live_feed_verified=True`; it produced one stored candidate with REAL mode and BYBIT
provenance. R1 removes that caller-controlled boolean. A REAL window is now accepted
only while its exact immutable object is registered inside `scan_live_once`, after the
Bybit public feed has returned successfully. The scanner stamps observation time from
its own UTC clock. A direct helper call with a caller-created REAL window fails closed.

No strategy rule, freshness threshold, event identity, Opportunity contract, API route,
FX strategy, Foundation authority, risk policy, execution runtime, or MT5 gateway was
changed. No exchange trading or MT5 order path was added. Crypto execution remains
MT5-only; this scanner has no execution authority.

## Verification

Environment: Windows, Python 3.14.0, pytest 8.3.5.

- `python -m py_compile` over the eight changed/new Python paths — passed.
- `PYTHONPATH=src python -c "import crypto_opportunity_scanner; print('IMPORT_OK')"` — passed.
- `PYTHONPATH=src python -m pytest -q tests/test_crypto_opportunity_scanner.py` — **16 passed**, 0 failed. One Starlette/httpx deprecation warning from `TestClient`.
- `PYTHONPATH=src python -m pytest -q tests/test_opportunity_contracts.py tests/test_opportunity_engine.py tests/test_opportunity_candidate_store.py tests/test_opportunity_import_boundaries.py tests/test_bybit_linear_perp_feed.py tests/test_api_opportunity_analysis.py` — **126 passed**, 0 failed.
- Temporary probes: forged REAL through the direct scanner helper rejected; exact 15-minute closed-bar age accepted; 15 minutes plus one microsecond rejected; forming candle and naive timestamp rejected; unsupported symbol and timeframe rejected; repeated event with later observation time kept the same candidate ID and one store record; later event received a new candidate ID and a second record. The existing suite verifies no-setup behavior, weekend data, API read-only projection, and malformed Bybit payload handling.
- `git diff --check` — passed before commit.

## Public Bybit read

One bounded, credential-free `scan_live_once` request was made to the configured public
endpoint `https://api.bybit.com/v5/market/kline` with category `linear`, symbol
`BTCUSDT`, interval `5`, and limit `721`. The adapter received HTTP **403 Forbidden**;
the scanner returned `VENUE_UNAVAILABLE` / `KLINES_REQUEST_FAILED`, with no candidate.
This is an HTTP/network rejection, not a parsing or strategy result. The evidence does
not distinguish a regional restriction from an egress/proxy policy. No retry was made.
Real closed-candle data and real strategy evaluation remain unverified.

Safety counters: private Bybit calls 0; Bybit order calls 0; MT5 order checks/sends 0;
positions opened 0; Demo/Live orders sent 0.

## External reference

For an MT5-native BTC bot example, see [linuzri/mt5-trading](https://github.com/linuzri/mt5-trading),
an MIT-licensed BTCUSD MT5 sample with a demo/dry-run mode. Treat it as architecture
reference only: its EMA strategy is not adopted or validated here, its broker symbol is
BTCUSD (which may be a CFD rather than spot crypto), and this repository's scanner
remains observation-only. Freqtrade is a mature open-source crypto bot, but it executes
through exchange connectors, so it does not fit the project's MT5-only crypto execution
constraint.

## Next gate

`AG_CRYPTO_OPPORTUNITY_SCANNER_V1_R1_INDEPENDENT_REAUDIT`

The live connectivity blocker is external/unresolved and must be assessed separately
from deterministic scanner engineering.
