# AG V2-2A / V2-2B Implementation Status

Date: 2026-09-21  
Classification: **IMPLEMENTED_NOT_RUNTIME_VERIFIED**

## Objective

Close Audit #1 remediation for candidate authority continuity and implement the V2-2B candidate store + transition ledger using existing repository persistence primitives.

## V2-2A remediation

`src/opportunity/engine.py` now fails closed when an existing `OpportunityCandidate` is reused under incompatible authority. Continuity checks cover strategy id/version, engine version, symbol, market, venue, and market-data mode.

Focused tests were extended for strategy, version, symbol, and market-data-mode drift.

## V2-2B implementation

Added:

- `src/opportunity/candidate_store.py`
- `tests/test_opportunity_candidate_store.py`

The implementation reuses `runtime_state.store.JsonKeyValueStore`; it does not create a second low-level persistence primitive and does not reuse the CanonicalProposal ledger schema/keyspace.

One atomic JSON value per candidate contains the current candidate materialization plus append-only transition records. This makes the candidate revision + transition history update one `JsonKeyValueStore.put()` atomic unit.

Implemented gates:

- candidate/proposal domain separation;
- deterministic candidate identity supplied by the upstream funnel engine;
- exact-transition idempotence;
- contiguous revision enforcement;
- append-only transition history;
- restart reconstruction;
- occurrence/strategy/symbol/market/venue/data-mode continuity;
- fail-closed conflict handling.

## Authority

No strategy semantics changed. No proposal authority, Demo authority, Live authority, broker execution, Telegram delivery, or frontend authority is granted by this implementation.

## Verification state

Code and tests are committed to the remote repository, but this ChatGPT GitHub execution environment cannot run the repository pytest suite. Therefore this status is deliberately **IMPLEMENTED_NOT_RUNTIME_VERIFIED**, not VERIFIED.

Required local/CI verification:

```bash
python -m pytest tests/test_opportunity_engine.py tests/test_opportunity_candidate_store.py -q
python -m pytest tests/ -k "opportunity" -q
```

Only after those commands pass should V2-2A/V2-2B be classified VERIFIED and Audit #1 be re-run/closed.

## Next gate

After runtime verification and independent Audit #1 closure:

1. V2-3A Large-SMC shadow adapter
2. V2-3B SSC shadow/replay adapter
3. semantic parity checkpoint

Do not advance strategy adapters on the basis of this document alone.
