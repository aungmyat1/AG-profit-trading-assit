"""Pure sizing/guard boundary for frozen strategy engines (AG V1 owner decision 1, 2026-09-30).

`risk.py`, `daily_loss_guard.py` and `position_guard.py` are byte-exact copies of
`src/execution/{risk,daily_loss_guard,position_guard}.py` at commit 2b75bbf. They were
moved here so that the frozen ST_LIQUIDITY_SWEEP_RETEST_V1 engine can run while
`src/execution/` stays forbidden on main. Strategy rules and parameters are unchanged; only
the import path moved.

EXECUTION_AUTHORITY = NONE. This package has no broker, MT5 order, network or position-
mutation imports (tests/test_v1_sizing_math_boundary.py enforces that).
"""
