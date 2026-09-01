# ST_LARGE_SMC_V1 Strategy Specification — Status (2026-09-01)

## Scope

Read-only discovery and specification-only synthesis. No strategy engine, workflow,
candidate ledger, or machine-readable contract (`strategies/ST_LARGE_SMC_V1.yaml`) was
built or modified. No backtest was run. No AG_TRADE_ASSISTANT_V1_0_2 or
ST_ASIAN_SWEEP_5R_V1 behavior was touched. The only artifact changed is
`docs/specs/LARGE_SMC_V1_SPEC.md` (rewritten with the reconciled contract) plus this
status document.

## Method

Two parallel read-only research passes: (1) AG's own existing Large-SMC artifacts —
`strategies/ST_LARGE_SMC_V1.yaml`, the prior `docs/specs/LARGE_SMC_V1_SPEC.md`, E1/E2/E3
and M1/M2/M3 entry-confirmation modules, Stage1/Stage2 research architecture, the golden
research baseline, and sibling strategy contracts; (2) targeted extraction from the
approved external research source `smc-lss-platform` (`ST-C1_v1.1.0.yaml`,
`specs/v3.6.yaml`, and ST-C3's state-machine/rejection-code structure only, per the
resource map's precedence rule). Findings were reconciled against AG's own evidence
hierarchy (owner-frozen > AG-signed contract fields > AG deterministic implementations >
approved external research > related strategies > generic SMC knowledge).

## Central finding

`ST_LARGE_SMC_V1.yaml` already signs a coarse D1/H4/H1/M15 timeframe scheme. AG's own
frozen, golden-validated E1/E2/E3 + M1/M2/M3 entry-confirmation pipeline
(`src/entry_confirmation/`, `src/historical_replay/stage1.py`/`stage2.py`) — the single
most reusable candidate implementation available — actually operates on D1/H1/M5, with
no H4 or M15 role at all. The external research source (`ST-C1 v1.1.0`) uses a third
scheme (H1/M5, D1 only as an optional POI origin). None of the three converge. This
conflict (UC-001, `docs/specs/LARGE_SMC_V1_SPEC.md` §7/§16) is the first blocking gate:
nearly every other contract (direction, structural context, location, liquidity,
activation, confirmation, entry, stop) depends on which timeframe performs which role,
and the strongest reuse candidate (AG's own frozen code) cannot be adopted without
revising the yaml's already-signed H4/M15 fields.

## Completeness

18 contracts evaluated (C01-C18): 1 `RESOLVED` (C17 multi-symbol, resolved by absence of
evidence per spec section 39), 8 `PARTIALLY_RESOLVED` (C01, C02, C04, C05, C06, C08,
C13, C16), 9 `UNRESOLVED_CONTRACT` (C03, C07, C09, C10, C11, C12, C14, C15, C18), 0
`NOT_REQUIRED`. 16 unresolved-contract register entries (UC-001 through UC-016) were
recorded, each with source citations and, where applicable, explicit
`OWNER_DECISION_REQUIRED` options (UC-001 primary; UC-008/UC-009 secondary, contingent
on UC-001).

Because the minimum deterministic core (direction, activation, entry, invalidation,
target, expiry) is not resolved, `SPEC_STATUS=PARTIAL_RESEARCH_DRAFT`, not
`READY_FOR_MULTI_ASSET_CONVENTIONS`.

## What was deliberately not done

No rule was invented to fill an `UNSIGNED` field. No timeframe scheme was silently
chosen between the three candidates. No machine-readable contract update was made
(`strategies/ST_LARGE_SMC_V1.yaml` is unchanged) — per spec section 50, inventing
placeholder values merely to satisfy a schema was explicitly avoided. No registry change
was made. `ST_LIQUIDITY_SWEEP_RETEST_V1`'s separate registry-coverage gap (noted in the
prior architecture-audit phase) was left untouched, as instructed.

## Tests

None run. No production code or configuration changed this phase (spec section 64).

## Next step

Owner decision on UC-001 (`docs/specs/LARGE_SMC_V1_SPEC.md` §30): adopt AG's own frozen
D1/H1/M5 E1-E3/M1-M3 pipeline (requires revising the yaml's signed H4/M15 timeframe
roles) or keep the signed D1/H4/H1/M15 scheme (requires new capability with no existing
implementation to adapt from). Recommendation, if evidence is allowed to break the tie:
adopt the frozen pipeline — it is the only option with concrete, validated
implementation. Until that decision is made, `NEXT_PHASE=RESOLVE_STRATEGY_CONTRACT`.
