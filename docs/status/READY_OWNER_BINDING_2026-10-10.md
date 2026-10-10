---
class: evidence
state: UNIT_TESTED
owner_reviewed: null
review_by: null
---
# READY owner binding (2026-10-10)

READY now requires `ready: ON` plus an approved, structured record in
`docs/governance/OWNER_DECISION_REGISTER.md`. The record binds a decision ID, strategy ID,
exact version, contract SHA256, symbol scope, session scope, and decision date. The FX ticket
path supplies the source path actually loaded; a missing or mismatched field fails closed with
an explicit reason. Existing per-symbol logic-verification remains an additional gate.

The production READY switch remains OFF. The owner decision register was not edited, and no
owner record or strategy authorization was created. No scheduler, strategy rule, risk default,
or broker state changed. The scheduled `AG-V1-Crypto-Daily` job remains
`ST_LIQUIDITY_SWEEP_RETEST_V1@2.0.0`; the separate `AG-V1-LSMC-Watch` crypto summaries consume
Large-SMC `ST_LARGE_SMC_V1@1.1.0` watch evaluations. The summary event schema itself does not
stamp strategy identity; identity follows from its LSMC-only producer.

Validation: `.venv/bin/python -m pytest -q` — 1937 passed, 4 skipped, 45 warnings;
Ruff on the changed Python files — 0 findings. Environment: Linux, Python 3.12; tests use
fixture-only owner records. No broker or execution APIs were called.
