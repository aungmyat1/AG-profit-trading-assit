---
class: status
state: DESIGN
owner_reviewed: null
review_by: 2026-11-07
---
# AGP-LSMC-TICKET-DIAGNOSTICS-R2

PR: [#241](https://github.com/aungmyat1/AG-profit-trading-assit/pull/241).
Base: d7a5d5ef552240c839eae6f66086740d1e1e9796.
Original head: 5bc988742c4389de39df50103e13cb5d74af0d6c.
R2 continues the existing branch; no strategy or authority changes.

## Baseline audit

Fetched main and PR branch: remote heads match the above SHAs; clean worktree,
0 commits behind / 2 ahead of main; PR open, draft, mergeable. No code review
findings were posted: CodeRabbit skipped draft review. Prior PR CI run
38848901845: Python failed (2 failed, 3239 passed, 6 skipped), frontend and docs-drift
passed; lint was skipped after Python failure. Both failures were legacy rendered
text assertions, not strategy failures. Docs-hygiene and merge-readiness passed.

Related open drafts inspected again: #239 manual READY (frozen CCFD identity issue),
#232 owner authority proposals, #231 read-only history tooling. None incorporated.
Current registry remains inactive/research-only for LSMC; detection-only verification
is EURUSD 1.1.0, not entry authorization. LSMC 1.1.2 remains unregistered/unverified
for entry; no READY/AUTO_DEMO authority. S1 authority and behavior unchanged.

## Fixes and regression evidence

| Issue / root cause | Fix | Regression |
|---|---|---|
| Unchecked .get on untyped payload/opportunity/POI | Mapping validation and display-only copies | Null/scalar/list events and nested evidence; original inputs unchanged |
| Boolean/nonfinite/unbounded prices and inverted zones | Positive finite numeric validation, ordered zones | All candidate price fields, NaN/inf/bool/huge integer, zero/negative, reversed bounds |
| Unvalidated reason iteration allowed character splitting, Unicode and injected lines | Bounded typed ASCII code list; invalid evidence becomes NOT_AVAILABLE without truncation | Strings/dicts/mixed lists/Unicode/control/oversized codes |
| Local-offset timestamps and impossible chronology | Normalize aware timestamps to UTC; require signal <= evaluation and signal < expiry; known sweep <= signal | UTC/MMT/mixed offsets, naive/invalid times, equality, future signals/sweeps, expiry before signal |
| Direction lookup could fail on unhashable values; R:R could overflow | Validate direction and directional levels; reject nonfinite derived R:R | LONG/SHORT, missing/bad levels, zero risk and overflow |
| New section could be cut by shared sender's existing text[:4000] policy | Check full LSMC text in UTF-16 units at the 4000 budget, BLOCKED before sending if exceeded | Exact boundary and one-unit overflow; authority lines never silently sliced |
| Legacy rendered-text tests did not account for intended diagnostics | Update explicit expected additions and ASCII separators | Original historical golden bytes retained; compare old text plus only intended additions |

No transport splitting/truncation policy or delivery-ledger identity was changed.
No diagnostics modify evaluation, tracker state, archives or authorization.
Missing displacement/BOS/cost evidence remains NOT_AVAILABLE; gross R:R never
claims economic qualification, and net R:R remains NOT_AVAILABLE. Freshness is
AT_EVALUATION_ONLY, never current execution eligibility.

## Validation (Linux cloud, 2026-10-16)

Pinned Ruff 0.16.10 installed in the existing repository venv. Focused tests use
resource class R1 with guard acquisition/release, one worker, no heavy process left.

Commands (P=/workspace/AG-profit-trading-assit/.venv/bin):

```text
PATH="$P:$PATH" PYTHONPATH="$PWD/src" $P/python -m pytest -q tests/test_lsmc_ticket_diagnostics_r1.py tests/test_lsmc_ticket_diagnostics_r2.py tests/test_lsmc_actionability.py tests/test_crypto_strategy_summary.py tests/test_telegram_message_format.py tests/test_telegram_message_metadata.py tests/test_lsmc_alert_dedup.py tests/test_v1_large_smc_110_watch.py tests/test_ticket_delivery_identity_and_archive.py tests/test_ticket_delivery_execution_boundary.py tests/test_telegram_delivery_adapter.py tests/test_telegram_delivery_readiness.py tests/test_ticket_delivery_concurrency_and_restart.py tests/test_docs_live.py tests/test_context_pack.py tests/test_generated_files_ci.py
$P/ruff check src/host_delivery/lsmc_diagnostics.py src/host_delivery/telegram_message.py tests/test_lsmc_ticket_diagnostics_r1.py tests/test_lsmc_ticket_diagnostics_r2.py tests/test_crypto_strategy_summary.py tests/test_lsmc_actionability.py
$P/python scripts/check_docs_links.py
$P/python scripts/check_skill_mirror_drift.py
```

Final focused result: 364 passed in 9.05s, exit 0. The PR description binds this
result to the pushed SHA.
Ruff, links, mirror drift and git diff --check: exit 0. Documentation generators
(collect_facts, generate_live_status, cog, build_context_pack, generated_files),
then check_drift and check_prose_drift: all exit 0; 0 blocking drift errors.
Existing advisory stale anchors/routes remain. Generated outputs were backed up
and restored byte-exact; no generated authority files were committed.
Direct check_drift before collection failed on stale committed facts; the workflow's
required regeneration sequence passed. An intermediate test run found an inconsistent
synthetic sweep timestamp and missing cog on PATH; fixture/PATH corrected.
Full default suite and frontend checks are delegated to the existing final-head CI;
final run IDs and results belong in the PR description, not inferred from old runs.

## Historical evidence and follow-up

Rechecked approved committed October 15-16 evidence paths; no new files since R1.
The six original alerts remain unavailable. USDJPY NEAR_POI -> DEVELOPING has no
attributed cause; price/ATR/POI replacement are hypotheses only. No facts fabricated.
Distinct consecutive GBPUSD/XAUUSD FVG reference IDs, state transitions, repeated
poll/delivery suppression and immutable prior archive bytes are regression-tested.

Proposed separate mission **AGP-LSMC-LIFECYCLE-R2** (not implemented here):
per-reference persistence; explicit replacement/supersession; invalidation and expiry;
historical transition provenance; immutable terminal events; identity-aware deduplication
and delivery; backward-compatible migration/restart handling. Must review frozen
identity impact and validate a candidate before changing the tracker model.

Host and live Telegram acceptance: NOT_RUN (no host connection or live delivery).
No standalone local full-suite run; final-head GitHub CI provides that evidence.
OSS-FIRST: reporting hardening | existing adapter + Python stdlib | REUSED |
no new indicator, trading rules or external data source.

ORDER_API_CALLS=0; BROKER_MUTATION_COUNT=0; AUTHORITY_CHANGES=0.
No merge or deployment. See PR #241 for final HEAD, CI and review verdict.
