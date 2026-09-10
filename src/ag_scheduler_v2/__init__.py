"""AG_DAILY_OPPORTUNITY_SCHEDULER_V2 -- orchestration layer for market observation and
research workloads. Not a strategy, not lifecycle authority, not trade authorization.

See config/ag_scheduler_v2.yaml for the versioned owner-specified schedule/thresholds
this package implements, and docs/status/ for the reconciliation note explaining why
SESSION_TRADE_V1 is used as the working target for the "ST_SESSION_SWEEP_CONTINUATION_V1"
strategy-integration point (that strategy_id does not exist in this repository).
"""

SCHEDULER_ID = "AG_DAILY_OPPORTUNITY_SCHEDULER_V2"
SCHEDULER_VERSION = "1.0.0"
