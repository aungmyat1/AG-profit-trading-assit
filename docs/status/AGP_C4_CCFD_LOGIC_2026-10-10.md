---
class: status_evidence
state: SYNTHETIC_ONLY
owner_reviewed: null
review_by: 2026-11-07
---
# AGP-C4-CCFD-LOGIC — 2026-10-10

Draft PR: https://github.com/aungmyat1/AG-profit-trading-assit/pull/126
Base: `5b671996ef91934f2e8b58f9748ee78b1804a099`.
Final head and exact normalized contract/engine identity are delivered in the PR
and the standalone `LOGIC_VERIFICATION_REPORT.json` from the final checkout.

`ST_CRYPTO_CFD_SWEEP_RETEST_V1@1.0.0`: **SYNTHETIC_ONLY**, no recorded VT claim.
The runner reads a manifest of fixture paths; the offline `v1_tickets` gate reuses
the existing evidence model, CFD evaluator and shared `crypto_cfd_cost_gate`.
Production swing length 5 and close-break=true are used. Frozen strategy files
are untouched. Shared ticket spread comparison now accepts exactly 10% (cost
still WARN at 0.10R); 10–20% spread warns, >20% blocks, and cost >=0.25R blocks.
Missing or malformed required policy keys block even direct cost-gate callers.

| Gate | Synthetic result | Evidence |
|---|---|---|
| L1 | PASS | Contract/version, normalized contract+engine hashes, repeated replay identity |
| L2 | PASS | Contract structure parameters, direction permission, reconstructed sweep/MSS/retest, zero-buffer stop, reference targets, 50% split |
| L3 | PASS | Closed UTC OHLC, ordered bars, exact 288-bar previous-day grid, future invariance, pre-retest rejection, configured window |
| L4 | PASS | Directional SL/entry/TP ordering, positive risk, computed RR and contract minimum |
| L5 | PASS | Shared D2/D4 friction gate, fresh synthetic quote, explicitly synthetic commission=0 |
| L6 | PASS | Shared freshness fields, retest-close + 15-minute expiry and signal age |

Synthetic coverage: eight BTCUSD/ETHUSD × LONG/SHORT × WEEKDAY/WEEKEND cases.
Uncovered recorded cases: **all eight combinations**, pending AGP-DATA-R2.
D1-confirmed/conflicting-context and invalid/expired/no-setup branches have
contract/unit-test coverage, not recorded fixture coverage. Recorded sizing and
weekend execution/cost reality remain unverified. L1–L6 never establish edge,
risk sizing authority, READY admission or demo/live execution authority.

Verification (Linux offline, 2026-10-10):

```sh
python -m pytest -q tests/test_ccfd_v100_logic_verification.py tests/test_crypto_cfd_proposal_policy.py tests/test_crypto_cfd_strategy_contract_v1.py
python scripts/ccfd_v100_logic_verification.py --out-dir work/ccfd-synthetic
```

Result: 69 tests pass; synthetic runner L1–L6 PASS, verdict SYNTHETIC_ONLY.
The environment's existing repo `.venv` supplies the pinned dependencies.
Optional lint executable was unavailable; `git diff --check` passes.

One-command recorded rerun:

```sh
python scripts/ccfd_v100_logic_verification.py --fixtures /path/to/AGP-DATA-R2/manifest.json --out-dir work/ccfd-recorded
```

Fixture/provenance schema: [synthetic corpus README](../../tests/fixtures/ccfd_v100/synthetic/README.md).
A recorded claim requires separate DATA-R2 capture provenance, matching raw-file
SHA256s, every gate PASS and all eight coverage combinations. Unknown commission
is WARN and cannot qualify. Bundled synthetic bytes cannot be relabelled as recorded.
Provenance is an integrity-checked capture assertion; it is not venue authentication.

OSS-FIRST:

| COMPONENT | OSS_CANDIDATE | DECISION | REASON |
|---|---|---|---|
| Strategy replay | Existing crypto_cfd_contract evaluator and sweep/MSS/retest primitives | REUSED | Exact local authority; no new trading logic |
| Structure | Repo wrapper over pinned smartmoneyconcepts==0.0.27 | REUSED | Production detection and config; no copied OSS implementation |
| Verification and cost | Existing ASW runner pattern, logic_gate evidence, crypto_cfd_cost_gate | REUSED/WRAPPED | CFD-specific evidence only; no cost fork or new dependency |
| Fixtures | Existing synthetic contract tests | WRAPPED | Production-lookback expansion; not broker evidence |

Registry active/demo/live/readiness, scheduler and generated status files are
unchanged. The generated rolling status is intentionally not edited under the
mission's explicit restriction; this hand-authored evidence is indexed in docs.

**NO_BROKER_MUTATION** — ORDER_API_CALLS=0, BROKER_MUTATION_COUNT=0.
