# AG V1 host kit — audit 2 fixes (2026-09-30)

Branch `fix/audit2-v1` from `main` 421ec9d. Host: Windows, VT Markets demo MT5
(`VTMarkets-Demo`, DEMO), repo `.venv` Python 3.14.0. Read-only throughout: there are no
order_send/order_check/position calls, and the frozen engines are unchanged
(ST_ASIAN_SWEEP_5R_V1@1.1.1, ST_LIQUIDITY_SWEEP_RETEST_V1@2.0.0).

| # | Finding | Verdict / fix | Test |
|---|---------|---------------|------|
| 1 | Codex CRITICAL (audit 818e3cd): MT5 bar/tick times treated as broker server time | **NOT_APPLICABLE.** Live evidence on the host (2026-09-30 15:2x UTC): `tick.time - time.time() = +10798 s` (BTCUSD) → measured UTC+3, which equals the rule offset UTC+3 (NY EDT −4 + 7). MT5 returns broker SERVER time, and the single conversion `server_time_to_utc` (UTC = server − rule offset) is correct. `diagnose_mt5.py` now runs a live `server_time_offset` check: the measured offset must equal the rule offset, otherwise FAIL (a stale tick counts as FAIL too) | `test_diagnose_server_offset_live_check`; live `diagnose_mt5.py` → `[OK ] server_time_offset: probe=BTCUSD ... measured=UTC+3 rule=UTC+3` |
| 2 | Crypto DATA_ERROR was generic (`MT5_FEED_ERROR`); evidence looked up from the CWD; BTCUSD/ETHUSD captures had no swap fields | Reason codes METADATA_MISSING, SWAP_FIELDS_MISSING, SYMBOL_NOT_FOUND, INCOMPLETE_CANDLES, CWD_LOOKUP, CONVERSION_ERROR (`host_evidence.symbol_metadata.HostDataError`) are now logged. Evidence is resolved from the absolute repo root, and a relative `AG_EVIDENCE_ROOT` gives CWD_LOOKUP. BTCUSD/ETHUSD were recaptured with swaps (BTCUSD −20/0, ETHUSD −25/0, 3-day rollover on day 5) | `test_crypto_v2_specific_reason_codes`, `..._evidence_never_resolves_from_cwd`, `..._missing_swap_fields_is_data_error`, `test_host_fetch_reason_codes` |
| 3 | EURUSD/GBPUSD ran as REPO_EVIDENCED and fell back to plain symbols | These tickets now resolve only to the `-VIP` HOST_CAPTURED record. There is no plain-symbol fallback: without the record, `broker_symbol()` raises METADATA_MISSING and nothing is fetched | `test_fx_never_falls_back_to_plain_symbols` |
| 4 | READY tickets were re-emitted from signals that were hours old; the spread was never checked | `v1_tickets.guards`: data or signal older than 15 min → STALE. A spread above 15% of the stop distance → SPREAD_TOO_WIDE. No live quote → NO_TRADE with reason SPREAD_NOT_EVALUATED. None of these can be READY. The live bid/ask comes from `symbol_info_tick` (read-only) | `test_fx_ready_is_withheld_when_stale_or_spread_fails`, `test_fx_mode_ready_requires_fresh_signal_and_spread`, `test_crypto_v2_stale_data_is_never_ready` |
| 5 | The UI showed fixture broker status and P&L as real | Navbar, BrokerDiagnostic and ExecutionCockpit label these SIMULATED in mock mode. In real mode they show "no backend data" and none of the fixture values. The UI lives in the root Vite `src/`; `web/` holds only scripts. **Not type-checked**: no TypeScript toolchain is installed on this host | none (manual review) |

## Live evidence

- Crypto was rerun once manually at 15:17 UTC, inside the V2 window. Result:
  `CRYPTO BTCUSDT decision=WATCH reason=NO_QUALIFIED_SWEEP_YET source=MT5_VT_MARKETS_DEMO`
  (ETHUSDT gave the same). Before the fix, every run in the window was DATA_ERROR.
- FX, first scheduled run on the new code: the four LONDON_NEWYORK READY tickets from 15:00
  UTC (morning signals re-emitted) became `decision=STALE`.

## Tests

`.venv/Scripts/python.exe -m pytest tests/test_v1_tickets.py tests/test_host_go_live_kit.py tests/test_v1_large_smc_110_watch.py tests/test_v1_large_smc_import_boundary.py -q`
→ 111 passed, 1 failed. The failure is `test_restored_core_is_byte_exact_with_2b75bbf`. It already
failed on main (CRLF checkout vs LF blob, recorded in 91cd907) and this change does not touch it.

## Open

- The crypto signal age uses the MSS bar close, because the frozen SetupState records no retest
  time. A late retest can therefore be withheld as STALE, which fails closed.
- Same-bar stop/target precedence is still OPEN/DEFERRED. The frozen engine is untouched.
