# AG TradeTicket Vertical Slice V1 — R1 audit remediation status

Date: 2026-09-29. Classification: **TRADETICKET_VERTICAL_SLICE_R1_READY_FOR_REAUDIT** (audit
closure is Arena's decision only).

| Item | Value |
|---|---|
| Audited base | `e7dd985c11e00150f18925d993bca6f2f5ef53c6` (tree `b2c42287837d7660c5102f7a534473a34e89de5f`, parent `76348c728b2229de2ad0a5c22f857bf0263de60f`) |
| Audit report | `afbcc97` `docs/audit/AG_TRADETICKET_VERTICAL_SLICE_AUDIT_V1.md` — `TRADETICKET_VERTICAL_SLICE_AUDIT_FAIL` |
| Branch | `fix/tradeticket-vertical-slice-v1-r1` (worktree `D:/ddev/AG-tradeticket-slice-v1-r1`) |

## Arena blocking findings (verbatim from `afbcc97`)

**BLOCKING-1 — `AUTHORITY_SCHEMA_CONFLICT`: canonical `binding.proposal_authority` ignored.**
`qualify()` trusts a caller-supplied `ProposalAuthority` and never cross-checks
`binding.proposal_authority`, though the binding is already an argument. Measured: a forged
authority object plus the *genuine* binding (`proposal_authority=False`) yields
`PREPARED_ONLY`, `market_authoritative=True` for `ST_ASIAN_SWEEP_5R_V1`. Two authority
schemas now coexist and disagree about `SESSION_TRADE_V1`.

**BLOCKING-2 — authority-relevant inputs absent from the frozen contract.**
`open_risk_pct` and `authority.source` are not ticket fields; `aggregate_risk_policy` is the
hardcoded literal `"NOT_AVAILABLE"`. A registry-authorized ticket and a forged-authority
ticket are byte-indistinguishable, and the open-risk context that gated sizing is
unreconstructible. Blocking only because the schema is about to be frozen with no field to
carry them later.

## Remediation

**BLOCKING-1.** `qualify()` now takes the `StrategyBinding`. In REAL_STRATEGY_MODE it collects every denial, in a fixed order, and returns them all. Neither representation can override the other.

The checks are:

- **Binding:** it must be for the same strategy, and `binding.proposal_authority` must be `True`.
- **Authority object:** it must exist, be for the same strategy, and have `source == "REGISTRY"`.
- **Registry lineage:** `registry_path` must be the canonical `strategies/registry.yaml`. `registry_fingerprint` (SHA-256 of the registry bytes) must equal the caller's `expected_registry_fingerprint`.
- **Authorisation:** `resolution` must be `AUTHORIZED`.
- **Scope:** the scope must permit the exact `strategy_version`, `symbol`, `cycle` and `market_data_mode`.

The registry schema for authority is a `proposal_authorization` block with `authorized`, `strategy_version`, `symbols`, `cycles` and `market_data_modes`. No registry entry carries it, so REAL authority remains NONE for every strategy.

PIPELINE_TEST_MODE accepts **no** authority object, and it rejects a fixture binding that claims proposal or execution authority. `pipeline_test_authority()` is removed.

**BLOCKING-2.** `AG_TRADE_TICKET_V1` fields, all hashed, validated on construction and re-validated by `verify_ticket_dict`:

- `proposal_authority_source`. For a PREPARED_ONLY ticket this is registry source, resolution, registry path and fingerprint, scope, and `binding_proposal_authority: true`. For a PREPARED_TEST_ONLY ticket it is exactly `{"source": "PIPELINE_TEST_FIXTURE", "strategy_authority": "NONE"}`.
- `open_risk_pct`: caller-supplied, finite and ≥ 0. Missing open risk still blocks sizing.
- `max_aggregate_open_risk_pct`: the pilot value actually applied. It replaces the `aggregate_risk_policy = "NOT_AVAILABLE"` literal. The existing `risk_pct`, `risk_policy_fingerprint` and `risk_policy_source` fields are retained.
- `open_risk_snapshot_fingerprint = "NOT_AVAILABLE"`: the placeholder slot for the future OpenRiskSnapshot, per Arena remediation 2.

The owner view shows all of these as provenance only. The schema name is unchanged because V1 was never frozen. The qualification policy version is now `AG_TICKET_QUALIFICATION_V1_R1`, so `policy_fingerprint` changes.

**Canonical authority resolution (Arena remediation 1).** Neither `StrategyBinding.proposal_authority` nor the registry block is canonical on its own; authority is their **conjunction**:

- `StrategyBinding.proposal_authority` is the canonical runtime-capability gate. It is derived from dispatchability, and today it is True only for `SESSION_TRADE_V1`.
- The registry `proposal_authorization` block is the owner-signed scope.

The disagreement about `SESSION_TRADE_V1` therefore resolves by narrowing: it has a True binding but no registry block, so it is denied.

**Not changed:**

- sizing mathematics (`sizing.py` byte-identical to `e7dd985`; historical parity hash test retained);
- pilot risk values;
- strategies and registry;
- config;
- MT5, Opportunity, eligibility and proposal modules;
- execution.

There is no generic risk fallback.

## Tests (2026-09-29, Windows dev box, fixtures only, no MT5 contact)

- `python -m pytest tests/test_trade_ticket_vertical_slice.py -q` → 112 passed. This covers:
  - the original 42, adapted to the new authority API;
  - the authority cross-check matrix, including Arena's exact forged case;
  - scope, strategy, source, path and lineage negatives;
  - fixture isolation;
  - open-risk and aggregate provenance;
  - R1 field mutations;
  - full-field mutation matrices on both a PREPARED_TEST_ONLY and a PREPARED_ONLY ticket.
- `python -m pytest tests/test_opportunity_*.py tests/test_proposal_*.py tests/test_fx_opportunity_*.py -q` → 318 passed.

The PREPARED_ONLY positive path runs against a **temporary** registry copy (`tmp_path`, with the module registry path monkeypatched), plus a test-supplied target, because ST_ASIAN emits no targets. The real registry grants nothing. With genuine inputs, `ST_ASIAN_SWEEP_5R_V1` returns `NO_PROPOSAL_AUTHORITY` with reasons `BINDING_PROPOSAL_AUTHORITY_FALSE` and `PROPOSAL_AUTHORITY_FIELD_ABSENT`.
