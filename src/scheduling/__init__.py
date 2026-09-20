"""Operational FX session scheduling (AG_SCHEDULER_AND_LARGE_SMC_WATCH_HARDENING_V1).

See `fx_schedule.py` for the schedule/gate authority and its reconciliation note
explaining the relationship to the pre-existing, RESEARCH-status, unwired
`ag_scheduler_v2` package.

This package decides WHEN a bounded FX proposal cycle runs and WHETHER it is allowed
to. It never decides trades and never imports an order path.
"""
