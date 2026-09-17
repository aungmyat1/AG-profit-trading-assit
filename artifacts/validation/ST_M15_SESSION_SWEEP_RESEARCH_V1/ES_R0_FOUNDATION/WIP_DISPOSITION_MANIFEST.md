# Semantic-Reuse / Partial-WIP Disposition Manifest (ES-R0 P1, P11)

The 6 pre-existing files under `src/m15_session_sweep_research_v1/` were created before the ES-R0A discovery of D:\ interrupted this mission's original flow. Classified `PRE_R0A_PARTIAL_WIP_NONAUTHORITATIVE` at the time; each is now compared against the frozen `BASELINE_STRATEGY_CONTRACT.md` and the parent's own `SEMANTIC_REUSE_MANIFEST.md` (`ST_SESSION_TRADING_SOURCE_V1`, ES-S2) disposition scheme.

| File | Disposition | Reuse classification |
|---|---|---|
| `models.py` | `SEMANTICALLY_ACCEPTABLE` | `FORK_COPY_FROZEN` for `Direction`/`AsianRange`/`SweepStatus`/`SweepEvent`/`OccurrenceState`/`ResolvedOccurrence` (byte-identical to parent); `NEW_RESEARCH_COMPONENT` for `Occurrence` (already correctly dropped the parent's source-replication-specific `occurrence_classification`/`uncertainty_reasons` fields, which don't apply to a strategy making no replication claim) |
| `asian_range.py` | `SEMANTICALLY_ACCEPTABLE` | `FORK_COPY_FROZEN`, byte-identical logic to parent |
| `sweep.py` | `SEMANTICALLY_ACCEPTABLE` | `FORK_COPY_FROZEN`, byte-identical logic to parent |
| `stop_target.py` | `SEMANTICALLY_ACCEPTABLE` | `FORK_COPY_FROZEN`, byte-identical logic to parent |
| `partial_be.py` | `SEMANTICALLY_ACCEPTABLE` | `FORK_COPY_FROZEN`, byte-identical logic to parent — already correctly uses `INTRABAR_ORDER_UNRESOLVED`, never `STOP_FIRST` (confirmed by `test_dual_collision_intrabar_order_unresolved_not_stop_first`) |
| `__init__.py` | `REQUIRED_EDIT` (minor) | Applied during ES-R0: added the second provenance parent (D:\), `PROVENANCE_PARENTS` tuple, and `ECONOMIC_STATUS` field, which had not yet been added when this file was first drafted (before the D:\ discovery) |
| `occurrence.py` | `NOT_PRESENT_AT_INTERRUPTION` | Newly written during ES-R0 (`NEW_RESEARCH_COMPONENT`) — ties the forked modules together with no eligibility filtering, per the frozen baseline |

No code was copied from D:\ into any of the above — every module is either a `FORK_COPY_FROZEN` of AG's own already-tested parent code, or a `NEW_RESEARCH_COMPONENT` written for this mission. Should code ever be reused/copied from D:\ in a future mission, exact provenance and licensing/ownership constraints must be recorded at that time — not assumed here.
