# ST_LARGE_SMC_V1 Registration Status (2026-09-01)

## Change

Registered `ST_LARGE_SMC_V1 v1.0.0` as a separate Large-SMC strategy family and added
its research contract. `ST_ASIAN_SWEEP_5R_V1 v1.1.1` remains unchanged and retains sole
Session Day Trading authority.

## Operational state

```text
CONTRACT              RESEARCH_DRAFT
REGISTRY              REGISTERED / INACTIVE
ENGINE                NOT_IMPLEMENTED
PROPOSAL AUTHORITY    FALSE
DEMO AUTHORIZATION    FALSE
LIVE AUTHORIZATION    FALSE
AUTOMATIC EXECUTION   FALSE
```

The strategy may reuse advisory evidence from Market Structure, Supply/Demand,
Liquidity, Entry Confirmation, and Trade Management. It cannot inherit another
strategy's rules, authorization, replay results, or validation evidence.

## Deliberately unresolved

Instrument eligibility, exact location rules, confirmation timing, entry array,
order/fill assumptions, exits, holding period, risk limits, costs, data partitions,
benchmarks, acceptance criteria, and falsification tests remain `UNSIGNED`. No engine
work or parameter invention was performed.

## Verification

This registration is documentation/configuration only. Targeted registry tests verify
the separate identity and fail-closed authorization state. No MT5 call, order check,
order send, strategy evaluation, replay, or live validation is claimed.

