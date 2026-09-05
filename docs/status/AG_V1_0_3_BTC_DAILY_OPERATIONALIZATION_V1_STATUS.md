# AG V1.0.3 BTC Daily Operationalization V1 — Status (2026-09-05)

## Result

`BTC_PRODUCTION_DATA_PATH_PASS_SCHEDULER_READY`

The frozen Bybit qualification lineage (`692c040` → `705a790` → `0c5cda1` →
`fb23f39`) was merged into `main`. The seven protected FX behavioral paths remain
byte-equivalent to baseline `3b2eeed`; this milestone changes no FX strategy, session,
risk, quota, proposal, or execution behavior.

## Implemented operational surface

- `scripts/run_btc_daily_report.py`: strict read-only daily CLI. Defaults to the previous
  UTC observation date and accepts normal archival runs only in the frozen 00:05-00:15
  UTC next-day window.
- `scripts/install_btc_daily_task.ps1`: optional Windows Task Scheduler installer for
  06:37 MMT (00:07 UTC).
- Complete evidence gate: 24 previous-day H1 candles and all 288 observation-day M5
  candles must exist, be closed, ordered, unique, UTC-normalized, and adapter-valid.
- Scheduled/backfill evaluation is pinned to the requested observation date. H1/M5
  candles newer than that date are excluded to prevent lookahead.
- `READY` prints an informational entry-proposal ticket; it is explicitly not a broker
  ticket and always carries `execution_authority=DISABLED`.
- `--allow-outside-window --no-archive` provides a live diagnostic using disposable
  runtime/ledger/guard state. It cannot create qualification evidence.

## Live production validation

Environment: this Windows development host, no VPN/proxy/circumvention, no credentials,
public Bybit V5 production endpoints only.

```text
2026-09-05T15:11:23Z
/v5/market/time               HTTP 200, retCode 0
/v5/market/instruments-info   HTTP 200, retCode 0
/v5/market/kline              HTTP 200, retCode 0

live adapter diagnostic for observation date 2026-09-04
instrument                    BTCUSDT LinearPerpetual, settle USDT
H1 reference candles          24/24
M5 observation candles        288/288
duplicates/missing            0/0
closed candles only           YES
data quality                  PASS
decision                      WATCH
reason                        NO_QUALIFIED_SWEEP_YET
proposal count                0
report window                 AFTER_WINDOW
qualification eligible        NO
archive written               NO
diagnostic persistent state   NONE
execution                     DISABLED
```

The diagnostic proves production connectivity, metadata parsing, full candle retrieval,
data-quality validation, deterministic strategy evaluation, and clean JSON output. It
does not count toward the 30-observation campaign because it ran outside the frozen
report window.

## Tests

Focused command:

```powershell
python -m pytest -q tests/test_btc_daily_report.py tests/test_btc_daily_cli.py tests/test_btc_sweep_research_pipeline.py tests/test_bybit_linear_perp_feed.py tests/test_btc_strategy_registration.py tests/test_btc_proposal_execution_boundary.py
```

Result: `74 passed, 0 failed` on 2026-09-05, Windows, Python 3.14.

Full regression result is recorded in the rolling snapshot after completion.

## Remaining qualification gate

The first normal in-window execution/archive is pending. The 30-observation campaign
has not been separately authorized and remains `0/30`. No historical or diagnostic
result is counted retroactively. Crypto order submission, account access, wallet access,
and position management remain unimplemented and unauthorized.
