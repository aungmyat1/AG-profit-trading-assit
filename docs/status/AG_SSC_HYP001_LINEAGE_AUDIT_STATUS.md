# AG SSC — HYP_001_EXIT_CAPTURE Lineage Audit

Mission type: **governance/lineage audit**, not an economic evaluation. No new backtests, populations, or holdout access were performed. Full machine-readable record: `artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/HYP_001_LINEAGE_AUDIT/hyp001_lineage_audit.json` (sha256 `ebc7a99f84646362acb7d73367089146bb6d0ecbc4ea7d6bf9612e0554969ba7`).

## Headline finding

`ST_SESSION_SWEEP_CONTINUATION_V1` v1.1.0's candidate spec (`runner_target_r: 1.5`, EXIT-only change vs the frozen v1.0.0 parent) is committed on `main`, but its own cited provenance chain is broken:

- The full hypothesis-creation and grid-evidence lineage (`candidate_hypotheses.json`, the preregistered `{0.5,1.0,1.5,2.0,3.0}R` counterfactual grid, and the P9–P17 candidate-selection reasoning) exists **only** on the unmerged branch `refactor/architecture-boundary-hardening-v3` — not reachable from `main`'s history.
- `candidate_spec.yaml` cites `candidate_manifest.json` for the hash verification and "P4 structural-compromise rationale" behind choosing `1.5R`. **That file does not exist anywhere in the repository**, on either branch.
- The empirically best-performing grid point (GBPUSD population, `net_expectancy_R=-0.330`) was `0.5R`, not `1.5R` — the frozen candidate value is *not* the in-sample optimum (mitigating: argues against naive cherry-picking), but no committed document explains why `1.5R` specifically was chosen instead.
- `candidate_spec.yaml` was added to `main` via commit `53b7215`, whose message ("Add AG SSC Verification Implementation Plan V2 and BTC daily reports...") does not mention HYP_001 or the candidate spec at all.

## Confirmation readiness

**`NEEDS_PREREGISTRATION_REPAIR`**

The treatment itself is cleanly frozen (single EXIT-only semantic change, independently diff-verified against the parent — everything else byte-identical). What's missing before a fresh confirmatory test can run:

1. A committed, on-`main` rationale for the `1.5R` value (or an owner decision to refreeze against a different, justified value).
2. A quantitative PASS / FAIL / INCONCLUSIVE rule and sample-adequacy rule — none exist for HYP_001 anywhere, on either branch (contrast with HYP_002, which had an explicit preregistered PASS rule).
3. Reconciling the branch/main split so the full lineage is auditable from `main` alone.

## Freshness boundary

Latest consumed decision evidence for EURUSD (via the closed HYP_002 GEN_002 population, whose generator scanned every admitted candle through 2026-09-14 looking for setups): **2026-09-14T23:59:59Z**. Any fresh HYP_001 confirmatory data must start **2026-09-15T00:00:00Z** or later, non-overlapping with GEN_001 (2026-05-18–06-19), GEN_002A (GBPUSD, historical), or GEN_002 (2026-08-06–09-11 occurrences). Pre-boundary history may only be used as warmup/indicator context with zero economic contribution.

GBPUSD was not touched by this audit (Phase 14 firewall) beyond reading already-admitted metadata; its 2026-08-03–09-14 admitted window was never consumed by any HYP_001 or HYP_002 population and remains an open question for a future mission.

## Safety

`holdout_run_count=0`, no holdout access, no GBPUSD analysis, no new population generated, no HYP_001/HYP_002 execution, no parameter search, no strategy/runtime file changed, `demo_authorized=false`, `live_authorized=false` — unchanged.

## Next permitted action

Owner review of: (a) whether to author a real `candidate_manifest.json` with a traceable rationale for `1.5R` (or refreeze to a different, justified value), and (b) a proposed sample-adequacy/PASS/FAIL protocol (draft only, not yet authoritative — see the JSON artifact's `phase11_sample_adequacy` and `phase10_existing_decision_protocol_audit` sections). No fresh data may be inspected until that protocol is frozen.
