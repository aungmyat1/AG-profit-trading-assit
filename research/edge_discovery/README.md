# research/edge_discovery/ — Candidate Factory V0 artifacts

Created by AG_EDGE_DISCOVERY_ACCELERATION_R1 (2026-10-02/03). Research-only; grants no
proposal, risk, or execution authority. Code authority: `src/edge_discovery/`.

Pipeline: `CANDIDATE → CONTRACTABILITY → DEV FAST REPLAY → FRICTION SCREEN →
PROMOTE/REJECT → FREEZE SURVIVOR → existing full-verification authority`.

| Artifact | Meaning |
|---|---|
| `candidates/CRYPTO_CFD_C001.yaml` | Frozen candidate manifest (immutable; created before results) |
| `candidates/CRYPTO_CFD_C001.freeze.json` | Byte-level freeze record (manifest + contract file sha256, contract commit SHA/tree) |
| `datasets.yaml` | Data authority inventory + role classification (Phase 3) |
| `candidate_queue.yaml` | Family placeholders C002–C010 (no rules; FX-compatible schema) |
| `dataset_access_ledger.jsonl` | Append-only dataset-access ledger (holdout hygiene, Phase 12) |

Invariants: `FAST_SCREEN_PASS ≠ EDGE_VERIFIED`; candidates are immutable after economic
results exist (improvements become C002+); perpetual data (BTCUSDT/ETHUSDT) never
substitutes for CFD data (BTCUSD/ETHUSD) without an approved cross-instrument contract;
HOLDOUT/FINAL_OOS access requires an explicit governance approval id and repeat access
is never relabeled independent.

Current state: `BLOCKED_INSUFFICIENT_RESEARCH_DATA` — no BTCUSD/ETHUSD CFD historical
dataset exists in this repository, so C001's economic fast screen has not run and
`fast_screen_status = NOT_EVALUATED`. The factory, contractability gate, replay
adapter, friction scenarios, promotion policy, and ledger are implemented and tested
and apply unchanged once a provenance-verified CFD dataset lands.
