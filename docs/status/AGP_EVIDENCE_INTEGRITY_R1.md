---
class: evidence
state: DESIGN
owner_reviewed: null
review_by: null
---
# AGP Evidence Integrity R1 — MT5 Market-Data Contract R2 (2026-10-08)

**Disposition: `UNRESOLVED`; the four tracked artifacts are quarantined for provenance claims.**
The artifacts remain byte-for-byte in their existing paths. They were not deleted, moved, or
rewritten, and the original manifest values were not silently corrected.

## Scope and finding

This review covers the four files cited by
[`AG_MARKET_DATA_CONTRACT_R2_2026-10-08.md`](AG_MARKET_DATA_CONTRACT_R2_2026-10-08.md):
three market-data diagnostics and one live-evaluator report. The SHA-256 values written in
that document do **not** match the bytes currently tracked at those paths.

The four files first appear in merge commit
`942913eb820a3e3b91f8f0a4504a861263f3a8d5`; its parent
`f49cff5cdb12fcc8616c316483dfa54777972255` contains none of the four paths. Their Git blob
IDs are identical at that introducing commit and at current `main`
(`ed0252dbf21da73231e7a1f89f13e0ccc5e6210b`). Thus the repository establishes that the
present bytes have not changed since their first tracked addition; it does **not** establish
what the bytes were before that addition or authenticate the capture that produced them.
No independent signed manifest, pre-add source bytes, or independently authenticated host
record was found in the repository. This cannot be resolved by choosing the manifest hash or
the current file hash without external evidence.

## Hash reconciliation

`Manifest SHA256` below means the value printed in the existing R2 status document; it is
retained as an unreconciled claim. `Current SHA256` is recomputed from the preserved working
copy on 2026-10-08.

| Artifact | Manifest SHA256 (unreconciled) | Current SHA256 | Match |
|---|---|---|---|
| `artifacts/validation/live_market_data_contract_r2/2026-10-07_raw_m15_diagnostic.json` | `73e7913b9de2f9ab108c0caf46421d942a9f04932d5582cbc979cf85738e084c` | `744cb48aceb025cf7862296f827980237b1209163bb361170012c4fd55632492` | No |
| `artifacts/validation/live_market_data_contract_r2/2026-10-07_quote_diagnostic.json` | `8b7028beaf3d93789e5a22f847398822d04bc397d85fd553a3ffd0938830241a` | `5e6d16e1cf84e1b1cb3d2ca1234cd6673ef5b5a73f087fdab1891f64986192c2` | No |
| `artifacts/validation/live_market_data_contract_r2/2026-10-07_paired_live_quotes.json` | `482cdf0faf7726dbe002e24716f16d40e88168934518b31f0a54ff2cf7ac4b56` | `8829d13ce89b838d5d5f06b7af5797ba11ed5a3255610ac29ed62a7d0e0f23bc` | No |
| `artifacts/validation/live_evaluator_r1/2026-10-07_live_evaluator_report.json` | `5a675b06f6386751029ace1bde2a4174fbd2b72e94d7a9bf1c21c797edba98e3` | `b3d53ff96516918d4ec9ba51efb610853359cc8aba7b0b04057c199f2d06a2b3` | No |

## Mission-label reconciliation

The preserved evaluator report says `mission: AG_OBJECTIVE_INTEGRATION_R1_OFFLINE`, while its
rows say `data_source: MT5_VT_MARKETS_DEMO`; its header also records eight evaluations and
zero refused MT5 calls. The checked-in smoke entrypoint has a separate path that labels the
TICKET_STORE source `LIVE` only after the read-only MT5 guard and Demo-account check. These
statements are not sufficient to prove which exact invocation generated this particular
report, and the `OFFLINE` mission label is inconsistent with the report's other fields.

The source report label is being corrected to the neutral mission identifier
`AG_OBJECTIVE_INTEGRATION_R1`, with the data-store source and host-acceptance status recorded
as separate fields. The historical JSON artifact is intentionally left untouched. This
correction fixes the reporting ambiguity; it does not authenticate the old artifact.

## Quarantine and use restrictions

Until independent reconciliation or a fresh authorized host capture:

- Preserve the four files and the original manifest claims exactly as tracked.
- Treat the four files as **quarantined for provenance-dependent claims**. They may be
  described only as repository artifacts whose payloads make the stated claims; do not cite
  them as authenticated live-market evidence or as proof of Windows host acceptance.
- Do not use their prices, timestamps, or conclusions as strategy inputs, evaluation fixtures,
  thresholds, or promotion evidence.
- Do not repair the manifest by substituting the current file hashes. Record a new evidence
  manifest for any future capture, generated from the captured bytes and tied to the run's
  source revision and host procedure.

A future resolution requires a newly authorized Windows MT5 Demo run in the correct open
session, with read-only-call audit, explicit run/source labels, a post-capture SHA-256
manifest, and preserved host logs sufficient to link the artifacts to that run. Linux fixtures
or replay tests cannot substitute for that evidence.

## Review trace

- Introducing merge: `942913eb820a3e3b91f8f0a4504a861263f3a8d5` (PR #59); parent:
  `f49cff5cdb12fcc8616c316483dfa54777972255` (no artifact paths).
- Subsequent merge/current main: `e99107cc241a34622778bdb90f034348ef60a2b1` /
  `ed0252dbf21da73231e7a1f89f13e0ccc5e6210b`; the four artifact blobs are unchanged.
- Integrity result: `UNRESOLVED`; no independent source bytes available to adjudicate the
  mismatch.
