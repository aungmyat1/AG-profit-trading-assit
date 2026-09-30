# Independent audit — PR #16 host kit and PR #17 research/attribution-v1

**Audit date:** 2026-09-30
**Scope:** merged PR #16 (`3fd14fe`, implementation `4ed1e60`) and research/attribution-v1 changes through `91cd907`.
**Method:** source/diff review and focused mocked/unit tests.
**Disposition:** report only. No fixes, activation, merge, or broker calls.

## Findings

| Severity | File:line | Description | Suggested fix |
|---|---|---|---|
| **CRITICAL** | `scripts/host/_host_common.py:158-163`; `src/host_evidence/symbol_metadata.py:44-47` | `rates[*]["time"]` is converted from its Unix timestamp to UTC, stripped to a naive datetime, and then reinterpreted as broker-server wall time. The second conversion shifts closed bars by two or three hours depending on US DST. Bars can enter the wrong UTC session/reference day and can make a ticket consume information unavailable at its reported decision time. This affects host FX, Large-SMC, and MT5-crypto tickets. | Treat the MT5 epoch as UTC exactly once. Remove the server-wall-clock conversion from `host_fetch`, then add fixed epoch fixtures around both DST transitions proving bar timestamps, session membership, and decision cutoffs. Do not resume counting evidence until corrected output is independently compared with raw MT5 timestamps. |
| **HIGH** | `config/v1_tickets/crypto_ticket_v2.yaml:1-20`; `src/v1_tickets/crypto.py:158-164`; `src/btc_sweep_research/pipeline.py:163-169`; `src/btc_sweep_research/costs.py:19-52,106-117,155-159` | Active V2 tickets use VT Markets MT5 BTCUSD/ETHUSD CFDs, but the research pipeline still applies Binance USDT-M taker fees, an assumed eight-hour perpetual-funding schedule, and placeholder slippage. Actual CFD spread, swap/financing, commission, and measured friction are omitted, so the ticket is not venue-correct economic evidence. | Introduce a versioned, venue-specific cost authority selected explicitly by source/instrument class. For VT Markets CFDs, use captured bid/ask spread and broker-confirmed commission/swap rules; fail closed as `COST_DATA_UNAVAILABLE` when any required component is unavailable. Preserve the Binance model only for Binance perpetual attribution. |
| **HIGH** | `config/v1_tickets/crypto_ticket_v2.yaml:1-20`; `src/v1_tickets/crypto.py:14-18,53,69-81`; `src/btc_sweep_research/pipeline.py:227-240` | The default input changes from public crypto perpetuals in the frozen daily window to MT5 CFDs during 09:00–12:00 America/New_York, while strategy day/reference/execution semantics remain UTC-based. The engine source is not edited, but instrument class, venue, and observation window change the population around the frozen engine without parity evidence. | Keep V2 classified as a new unvalidated data/attribution profile. Freeze an explicit profile/version for CFD symbol mapping, reference day, decision window, and source authority; run causal replay and side-by-side parity/impact analysis before counting its observations toward existing CRYPTO_PERP evidence. Do not reattribute prior evidence. |
| **MEDIUM** | `src/strategy_engine/sweep_retest/engine.py:250-295`; `src/v1_tickets/crypto.py:167-173` | The audited path emits entry/stop/TP geometry and exposes externally invoked lifecycle transitions, but has no candle-based resolution rule for a bar touching stop and target. OHLC research attribution is ambiguous in this case. | Before outcome evidence is counted, define a frozen conservative precedence rule or require finer-grained data. Implement it only in a new candidate outcome-attribution version with same-bar tests for long/short, TP1/stop, and TP2/breakeven cases. |
| **LOW** | `scripts/host/capture_symbol_metadata.py:58-70`; `src/host_evidence/symbol_metadata.py:83-103` | Captured metadata records the account server, trade mode, and time rule, but verification checks only the hash and selected numeric fields. Metadata from another server/account mode can pass as `HOST_CAPTURED`. | Bind the evidence schema to exact approved broker/server, Demo trade mode, capture rule/version, and canonical-to-broker symbol mapping. Reject mismatches during both capture and load. |

## Required categories with no finding

| Category | Result |
|---|---|
| Frozen-engine source drift | No behavioral diff found in `src/strategy_engine/sweep_retest/engine.py` against the preserved lineage. Its only diff is the approved import move from `execution.*` to byte-equivalent `sizing_math.*`. Symbol parameterization occurs in the wrapper and is covered above as input-contract risk. |
| Secrets | No tracked `.env`, credential, private-key, or secret file found. Host credentials are read from environment variables and reviewed logging applies value redaction. Telegram strings are placeholders. |
| Order capability | No `order_send`, `order_check`, position mutation, or execution-gateway import chain found in the audited host/ticket/research paths. Host MT5 access is limited to initialization, account/symbol inspection, symbol selection, and candle copying. |

## Verification evidence

- `PYTHONPATH=src python -m pytest -q tests/test_host_go_live_kit.py tests/test_v1_tickets.py tests/test_btc_costs.py tests/test_liquidity_sweep_retest_strategy.py` — **113 passed, 1 skipped** during the audit.
- Static searches covered order and position APIs, credentials, time conversion, costs, stop/target handling, and frozen-engine diffs.
- Broker calls: **0**.
