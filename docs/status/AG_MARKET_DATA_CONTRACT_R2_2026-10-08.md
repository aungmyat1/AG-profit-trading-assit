# AG Market Data Contract R2 — Demo Verification (2026-10-08)

STATUS_EVIDENCE: bounded read-only Windows validation against the connected VT
Markets Demo terminal. It does not authorize trading, promote a strategy, or
establish an economic edge.

## Result

The read-only M15 candle and quote data path passed bounded Demo validation.
The quote adapter now converts the raw broker-server timestamp with the existing
DST-aware `host_evidence.symbol_metadata.server_time_to_utc` authority. No fixed
UTC offset or second time authority was added.

The accepted symbol metadata mapped EURUSD, GBPUSD, USDJPY and XAUUSD to their
exact `-VIP` broker symbols. The raw M15 check returned all **16/16** requested
reference and completed trade windows on the expected UTC timestamp grids, with
zero missing and zero extra opens. The earlier pre-fix quote capture showed all
four raw values about three hours ahead when interpreted as UTC. The post-fix
paired capture normalized all four into the current UTC interval and passed the
existing 15-minute freshness and bid/ask validity gates.

The exact eight-evaluation smoke emitted **8/8** terminal records, with no quote
time failure, no refused MT5 call and zero broker mutations. Outcomes were seven
`INSUFFICIENT_DATA / TRIGGER_TIMEFRAME_UNKNOWN` and one
`EXPIRED / TRADE_WINDOW_CLOSED`. These are explicit evaluator/actionability
outcomes; no trade opportunity was established. The owner actionability policy
remains unresolved, and every canonical record remains unauthorized for Demo or
Live execution.

## Focused verification

Environment: Windows host, Python 3.14, connected VT Markets Demo terminal.

The previous single-test recovery passed:

```text
python -m pytest -q tests/test_mt5_provider_integration.py::test_real_adapter_shaped_rates_reach_evaluator
1 passed
```

The focused suite passed:

```text
python -m pytest -q tests/test_mt5_provider_integration.py tests/test_mt5_candles_readonly.py tests/test_actionability_and_canonical_ticket.py
66 passed, 0 failed
```

The suite covers DST-aware quote timestamp conversion and freshness, stale and
future/invalid quote fail-closed behavior, exact provider error preservation,
stable ticket identity/actionability, and the read-only execution firewall.
No full test suite, economic backtest, strategy/session/risk change, or trade
execution was performed.

## Live evidence

All evidence files below are sanitized and contain no login or account identifier.
Their timestamps are UTC on 2026-10-07; the host-local verification date was
2026-10-08.

| Evidence | SHA256 | Result |
|---|---|---|
| `artifacts/validation/live_market_data_contract_r2/2026-10-07_raw_m15_diagnostic.json` | `73e7913b9de2f9ab108c0caf46421d942a9f04932d5582cbc979cf85738e084c` | 16/16 exact M15 windows; zero missing/extra opens |
| `artifacts/validation/live_market_data_contract_r2/2026-10-07_quote_diagnostic.json` | `8b7028beaf3d93789e5a22f847398822d04bc397d85fd553a3ffd0938830241a` | Pre-fix raw quote timestamp mismatch evidence |
| `artifacts/validation/live_market_data_contract_r2/2026-10-07_paired_live_quotes.json` | `482cdf0faf7726dbe002e24716f16d40e88168934518b31f0a54ff2cf7ac4b56` | All four post-fix normalized quotes usable; ages 7.7–11.7 seconds |
| `artifacts/validation/live_evaluator_r1/2026-10-07_live_evaluator_report.json` | `5a675b06f6386751029ace1bde2a4174fbd2b72e94d7a9bf1c21c797edba98e3` | 8/8 records; `EXPIRED=1`, `INSUFFICIENT_DATA=7`; refused calls `[]`; mutations `0` |

## Authority and scope

Changed implementation is limited to quote timestamp normalization through the
existing converter and structured acquisition-error provenance through the
canonical ticket and sanitized smoke report. The diagnostic shape is
`data_error = {code, detail, layer}`; it leaves the fail-closed decision and
logical ticket identity unchanged. Strategy behavior, actionability thresholds,
session windows, candle range semantics, risk, execution authority, and Demo/Live
authorization are unchanged.

Branch: `codex/market-data-contract-r2`, based on
`f49cff5cdb12fcc8616c316483dfa54777972255`. No merge was performed.
