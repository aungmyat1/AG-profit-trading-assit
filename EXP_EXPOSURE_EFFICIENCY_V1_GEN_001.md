# EXP_EXPOSURE_EFFICIENCY_V1 / GEN_001

## Purpose and authority

This offline, research-only evaluator asks whether fixed maximum holding durations improve cost-adjusted expectancy for one frozen historical entry population. It cannot create entries, place orders, change strategy parameters, or confer demo/live authority.

## Inputs

The trade CSV requires `trade_id,symbol,side,entry_time,entry_price,stop_loss,original_exit_time,original_exit_price,spread_cost_r,commission_cost_r,slippage_cost_r`; `take_profit,strategy_id,strategy_version` are optional. The M1 CSV requires `symbol,timestamp,open,high,low,close`. Timestamps must carry timezone offsets and are normalized to UTC. Invalid OHLC, ambiguous time, duplicates, ordering errors, symbol mismatches, negative costs, invalid stops, and insufficient coverage fail closed.

## Replay semantics

The frozen policies are `CONTROL,30,45,60,90,120`. CONTROL preserves the authoritative original exit time and price. A duration policy ends at the earlier original exit or cap, while an earlier supplied SL/TP takes precedence. An M1 bar touching both SL and TP is rejected because intrabar order is unknowable. There is no entry generation. `1R=abs(entry-stop)`; direction controls P&L, MFE, and MAE signs. Net R subtracts the three supplied per-trade friction components.

Maximum drawdown is peak-to-trough on cumulative net R ordered by entry time. Profit factor is positive net R divided by absolute negative net R and is null when no losses exist. R per position hour is secondary and is never sufficient alone to select a policy.

## Run

```text
python -m research.exposure_efficiency --trades trades.csv --candles m1.csv --output artifacts/research/EXP_EXPOSURE_EFFICIENCY_V1/GEN_001
```

Artifacts include frozen hashes/manifests, per-trade telemetry, policy metrics, JSON results, and a Markdown report. CONTROL must reconcile with the historical authority before duration results are interpreted. GEN_001 does not establish profitability, R6 status, or deployment eligibility. Final holdout evidence must not be supplied to this experiment.
