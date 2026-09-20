# Strategy Capacity VD — Cycle 1 status

Date: 2026-09-20. Classification: `VD_STRATEGY_CAPACITY_SIMULATOR_NOT_READY`.
Mode: `STRATEGY_CAPACITY_VALIDATION`. Initial strategy:
`ST_SESSION_SWEEP_CONTINUATION_V1` v1.0.1.

## Implemented and verified

`VirtualDemoRunner` can require a decision source receiving an admitted
`ReplayEvaluationContext` at virtual time T. In capacity mode it rejects fixture
decision maps. It checks replay event identity and requires a `ReplayResult`.
The fixture path remains available for isolated engineering tests. This is a
boundary only: a caller-supplied function is not proof that the canonical SSC
evaluator produced the result.

Focused check: `PYTHONPATH=src python -m pytest tests/test_svos_virtual_demo_runner_cycle5.py -q`
passed 4 tests on Windows/Python, with fixture data only. This check does not
prove economic, restart, or full campaign behavior.

## Gate blockers and shortest repairs

1. Bind the context source to the existing MI/SSC compatibility adapter and
   canonical `run_replay`, with unique decision-cycle identity and no future
   outcome visibility. Prove output parity against the canonical replay.
2. Process submitted virtual orders against subsequent M1 events; preserve
   position and ambiguous-path outcomes. The current runner processes only
   bars accumulated at decision time and does not retain pending orders.
3. Restore feed, orders, account, and ledger from a checkpoint. The existing
   `checkpoint()` is an audit summary, not a restart mechanism.
4. Freeze and hash the capacity-specific risk, friction, metric, qualification,
   and manifest contracts before any new campaign results are inspected.
5. Prove temporal, repeat, speed, restart, ledger, risk, friction, and ambiguity
   parity on permitted development evidence before a capacity campaign.

No strategy parameters, registration, execution gates, MT5 margin work, or
broker authority changed. Development campaign access: 0. Protected, holdout,
and OOS access: 0. Demo and Live orders: 0. Existing unrelated WIP was left
untouched. Broker margin, leverage, and rejection parity remain outside this
strategy-capacity mode. Commission, slippage, and latency remain unavailable
as broker-observed capacity evidence.
