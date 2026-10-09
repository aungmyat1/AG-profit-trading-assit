# Blind Reference Task

Implement a small pure deterministic reference evaluator using only:

- `contract.yaml`
- `owner_decisions.md`
- `schema.json`

Do not access the AG GitHub repository, pull requests, repository source, repository tests,
existing reference implementations, production evaluator information, prior AG
conversations, project memory, or any connector.

## Isolation declaration

Before work, report these exact fields:

```text
PRODUCTION_SOURCE_VIEWED = FALSE
PRODUCTION_RESULTS_VIEWED = FALSE
EXISTING_REFERENCE_VIEWED = FALSE
AG_REPOSITORY_VIEWED = FALSE
PR_IMPLEMENTATION_VIEWED = FALSE
```

Stop if any field would be true.

## Mandatory freeze order

1. Read `contract.yaml`, `owner_decisions.md`, and `schema.json` only.
2. Implement the evaluator without opening `dataset.json`.
3. Write evaluator self-tests without opening `dataset.json`.
4. Write `AMBIGUITY_LOG.md`.
5. Calculate `REFERENCE_SOURCE_SHA256` over the completed evaluator source.
6. Assign and record a `REFERENCE_FREEZE_ID`; make the source read-only or commit it.
7. Report the source hash and self-test result.
8. Only after steps 1–7 are complete, open and run `dataset.json` without changing it.
9. Produce `blind_reference_results.json` following `schema.json`.

No evaluator code edits are permitted after dataset execution. A code correction requires
a new source hash, freeze identity, and clean run from the beginning.

## Required ambiguity log

Produce `AMBIGUITY_LOG.md`. Each entry must contain:

```text
ambiguity_id
spec_location
question
interpretation_chosen
reason
semantic_impact
```

`semantic_impact` must be one of `NONE`, `REPRESENTATION_ONLY`, or
`STRATEGY_SEMANTIC`. Do not silently guess. If there are no ambiguities, state that
explicitly.

## Required deliverables

```text
reference evaluator source
reference evaluator self-tests
AMBIGUITY_LOG.md
REFERENCE_SOURCE_SHA256
REFERENCE_FREEZE_ID
REFERENCE_TEST_RESULTS
blind_reference_results.json
```

Do not perform comparison against any other evaluator and do not claim strategy
verification. Return the dataset and contract identities with the deliverables.

## External isolation

Use a genuinely fresh private/incognito session or a new standalone agent chat with no
connectors, project memory, or prior AG context. A safe fallback is a new repository
containing only this package. Do not provide the AG repository URL.
