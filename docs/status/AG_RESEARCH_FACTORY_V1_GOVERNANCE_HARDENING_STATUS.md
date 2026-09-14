# AG Research Factory V1 Governance Hardening — Status

Recorded: 2026-09-14

Implemented a filesystem-only governance layer in
`src/external_candidate/research_factory.py`: strict versioned schemas, immutable
freezing/export, two-pass physical persistence verification, SHA256SUMS authority,
cross-file evidence binding, one-shot Holdout identity consumption, independent
canonical-import verification, exact semantic-parity comparison, and explicit Demo/Live
separation.

No strategy economics, execution gateway, authorization flag, Holdout dataset, or broker
surface was touched. The missing external candidate was not recreated.

Focused evidence: `tests/test_research_factory_governance.py`. Capability classification:
`UNIT_TESTED`; no real candidate package or Holdout was executed.
