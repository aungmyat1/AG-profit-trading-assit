"""SMC_CONDITIONAL watcher (DUAL_DAYTRADING_WORKFLOW_V1 spec sections 12-27): a
condition-watch alert engine for E1 (daily gap fill+reaction), E2 (H1 POI reaction), and
E3 (liquidity sweep). These three conditions already exist in this repo as
entry_confirmation.route.ConfirmationRoute.DAILY_GAP_REACTION/H1_POI_REACTION/
LIQUIDITY_SWEEP -- this package never redefines gap/POI/sweep semantics, it only adds
the alerting concerns that route.py/engine_v2.py deliberately do not own: OR-consolidated
alerting across simultaneously-true conditions (engine_v2 evaluates only a single
matching route and reports INDETERMINATE on MULTIPLE, which is correct for its own
entry-confirmation purpose but wrong for alerting), alert deduplication, and lifecycle
state. execution_eligible is always False -- this package never authorizes a trade.
"""
from .models import (
    ALERT_STATE_VALUES,
    CONDITION_E1,
    CONDITION_E2,
    CONDITION_E3,
    SMCConditionAlert,
    SMCConditionResult,
)
from .conditions import evaluate_e1_condition, evaluate_e2_condition, evaluate_e3_condition
from .watcher import SMCConditionWatcher, request_m5_confirmation

__all__ = [
    "CONDITION_E1", "CONDITION_E2", "CONDITION_E3", "ALERT_STATE_VALUES",
    "SMCConditionResult", "SMCConditionAlert",
    "evaluate_e1_condition", "evaluate_e2_condition", "evaluate_e3_condition",
    "SMCConditionWatcher", "request_m5_confirmation",
]
