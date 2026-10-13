"""AGP-C18-R2 observational (REPORT_ONLY) evaluation lanes for ASW, LSMC and CCFD.

Every record produced here is a canonical ticket with scope_route REPORT_ONLY and an observational
report_class. Nothing in this package imports an execution, demo-execution or broker-mutation module,
and nothing here can grant READY, demo or live authority (tests/test_report_lanes.py enforces it).
"""
