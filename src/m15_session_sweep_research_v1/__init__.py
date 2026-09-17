"""ST_M15_SESSION_SWEEP_RESEARCH_V1 -- independent SOURCE_INSPIRED_RESEARCH lineage.

Established by ES-R0 as the governance-approved Path B outcome of
EXTERNAL_SOURCE_ES_S6 (SOURCE_ELIGIBILITY_COMPLETENESS=INSUFFICIENT,
SOURCE_INSPIRED_RESEARCH_LINEAGE_VIABLE=true). See
artifacts/validation/ST_M15_SESSION_SWEEP_RESEARCH_V1/ES_R0_FOUNDATION/ for the
full lineage manifest, contamination registry, and dataset-role contract.

This package is a FORK_COPY_FROZEN of the deterministic Detection + Management
core of ST_SESSION_TRADING_SOURCE_V1 v0.1.0 (provenance parent 1) -- copied,
not imported, so this lineage is fully independent and cannot drift if the
parent package changes. Behavioral parity with the parent is proven by
tests/test_m15_session_sweep_research_v1_parity.py, not assumed.

Provenance parent 2 (corroborating evidence, ES-R0A/OPTION_C_CONTROLLED_FORK_
FROM_D_DRIVE): D:/ddev/Session Trade Codex's documented strategy family
(STRATEGY_TRUTH_SOURCE.md v3.0), whose formalized Sweep/stop/target/management
formulas independently corroborate this package's baseline almost exactly.
That project is NOT a runtime dependency or execution authority for AG -- no
code is imported from it, no network/file call reaches it, and it continues to
evolve independently outside this lineage. See
artifacts/validation/ST_M15_SESSION_SWEEP_RESEARCH_V1/ES_R0_FOUNDATION/D_DRIVE_PROVENANCE_MANIFEST.md.

This is NOT a source-replication strategy. It makes no claim to reproduce the
external presenter's actual eligibility/trade-selection rules -- ES-S6 found
those rules SOURCE_ELIGIBILITY_COMPLETENESS=INSUFFICIENT. This package
generates every structurally valid Sweep occurrence with NO eligibility
filtering at all (no range/wick/cutoff/max-entries gate of any kind) --
eligibility hypotheses are a matter for a future, separately preregistered
ES-R1+ mission, never silently reintroduced here.
"""
from __future__ import annotations

STRATEGY_ID = "ST_M15_SESSION_SWEEP_RESEARCH_V1"
VERSION = "0.1.0"
LINEAGE_TYPE = "SOURCE_INSPIRED_RESEARCH"
STATUS = "RESEARCH_ONLY"

PROVENANCE_PARENTS = (
    "ST_SESSION_TRADING_SOURCE_V1 v0.1.0",
    "D:\\ddev\\Session Trade Codex (documented strategy family, HEAD d026f09a6fc79b5f0eabfd438252d0a545cb4d05)",
)
ECONOMIC_STATUS = "NOT_EVALUATED"
SOURCE_REPLICATION_CLAIM = False
SOURCE_SEMANTIC_PARITY_CLAIM = False
ECONOMIC_EDGE_CLAIM = False

NATIVE_TIMEFRAME = "M15"
H1_REQUIRED = False
M1_REQUIRED = False

DEMO_AUTHORIZED = False
LIVE_AUTHORIZED = False
