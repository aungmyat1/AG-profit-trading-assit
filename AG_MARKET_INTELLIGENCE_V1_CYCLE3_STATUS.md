# AG_MARKET_INTELLIGENCE_V1 — Cycle 3 parity and temporal proof

`FINAL_CLASSIFICATION = MI_V1_PARITY_READY`

## Baseline and scope

- Branch: `main`
- HEAD before: `cbb6a43`
- TD-8E `f4a1045`, Cycle-1 design `93586ec`, and Cycle-2 core `cbb6a43` are ancestors.
- HEAD after: the scoped Cycle-3 evidence commit.
- Existing proposal-ledger, validation-session, journal, and gate-log WIP was preserved.
- TD-8E semantics, strategies, parameters, execution authority, Demo/Live gates, and
  validation roles were not changed.

## Evidence

The real complete historical event used the consumed DEV_002 EURUSD files only as
non-economic infrastructure evidence:

- `symbol = EURUSD`
- `T = 2026-06-23T11:00:00Z`
- participating series: H1, M15, M1
- event identity: supplied by `ReplayEvaluationContext`; preserved unchanged in MI
- the replay context admitted closed bars only and no live fallback was permitted

The controlled temporal fixture used the same symbol with H1/M15/M1 and a fixed
`T = 2026-01-02T12:00:00Z`. A second dataset changed only bars after T. MI semantic
quality and lineage stayed equal while the full dataset identity and snapshot ID differed.

## Gates

- Same-event determinism: PASS; equivalent admitted contexts produced equal snapshots
  and snapshot IDs.
- Future-only mutation invariance at T: PASS; post-T mutation did not change MI
  quality or lineage semantics.
- Incomplete evidence: PASS; missing components produce `INCOMPLETE` quality.
- Zero live fallback: PASS; raw `copy_rates_from_pos` and `copy_rates_range` were
  guarded during historical composition and were not called.
- Identity preservation: PASS for event ID, EURUSD symbol, and as-of time.
- H1/M15/M1 lineage: PASS; all three identities and M1 participation were preserved.
- Authority parity: PASS for the represented inputs; MI consumes caller-supplied existing
  authority outputs and does not reimplement detectors.
- Unresolved fields: PASS; cross-strategy regime and repository-wide EMA remain
  explicitly `UNAVAILABLE`.

No live/replay parity claim is made. No equivalent live input was tested.

## Tests

Focused Cycle-3 command:

```text
python -m pytest -q tests/test_market_intelligence_v1_core.py tests/test_market_intelligence_v1_cycle3_parity.py
```

Result: **8 passed**.

Relevant regression command:

```text
python -m pytest -q tests/test_market_intelligence.py tests/test_market_intelligence_v1_core.py tests/test_market_intelligence_v1_cycle3_parity.py tests/test_td8e_evaluation_context.py tests/test_td8e_ssc_reference_completeness.py tests/test_td8d_replay_market_snapshot_bridge.py tests/test_td8c_session_replay_parity.py tests/test_historical_replay_no_lookahead.py tests/test_historical_replay_dataset_identity.py
```

Result: **87 passed**.

## Safety assertions

No SSC migration, new indicator, detector, optimization, economic reuse, holdout/OOS
access, proposal, risk, broker, Demo, Live, or execution-authority change occurred.
The Cycle-3 changes are parity tests and this evidence document only.
