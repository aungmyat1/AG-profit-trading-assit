# research/attribution — rule attribution for the frozen SSC engine

This is research only. It has no broker calls, no live or demo code, and no access to
holdout, OOS, or CONFIRM data. Status: `docs/status/AG_RULE_ATTRIBUTION_V1_STATUS.md`.

```
python -m research.attribution.run_attribution   # ordered gates; the report goes to reports/
python -m research.attribution.parity_check      # frozen-engine parity on synthetic candles
```

| File | Role |
|---|---|
| `ADMISSION.yaml` | Eligibility (owner directive). SSC GEN_001 is eligible. ST_ASIAN_SWEEP_5R_V1 gets checks only |
| `frozen_engine.py` | Loads SSC v1.0.1 read-only from git (`2b75bbf0`), after checking its tree and config hashes |
| `ledger.py` | Candidate ledger. Wraps 4 frozen gates (`G_BIAS`, `G_STOP_FLOOR`, `G_RISK_ALLOC`, `G_S3_SCORE`), records the real verdict for each, and gives counterfactual outcomes (TP1_FIRST/STOP_FIRST/EXPIRED/NEITHER). Also has the rule-swap and variant `exclude` layers |
| `costs.py` | VT Markets cost table. **PLACEHOLDER**, flagged on every row |
| `analysis.py` | Category table (cells with N<30 are INSUFFICIENT), ablation deltas, top-3 diagnosis (N≥30 cells only) |
| `validation.py` | Walk-forward, CPCV, PBO (CSCV), deflated Sharpe (counts all trials), and the verdict rule |
| `PREREGISTRATION.yaml` | The one-hypothesis slot. It stays empty until a diagnosis exists |

Ablation re-runs the engine for each relaxation, because filtering the ledger would ignore
campaign path dependence. Variants are new-version layers applied to the frozen engine.
Frozen rules are never edited.
