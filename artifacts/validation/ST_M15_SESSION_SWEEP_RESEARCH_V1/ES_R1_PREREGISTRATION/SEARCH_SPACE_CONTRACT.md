# ES-R1 Search Space Contract

## Isolation structure (P4)

Each hypothesis is evaluated independently against the shared baseline:

```
BASELINE  vs  H01_C1, H01_C2, H01_C3
BASELINE  vs  H02_C1, H02_C2, H02_C3, H02_C4
BASELINE  vs  H03_C1, H03_C2, H03_C3, H03_C4
```

No `H01 × H02 × H03` Cartesian combination is authorized in ES-R1. Interaction search requires a new experiment ID and separate preregistration (P13), and only after at least two individual hypotheses show sufficient independent evidence.

## Search method

- Fixed, named candidate list per hypothesis (above) — no Optuna, no Bayesian optimization, no genetic optimization, no unrestricted grid search, no adaptive threshold generation after seeing results.
- All threshold values are fixed at preregistration time, before any economic population is generated (ES-R2+).
- No candidate may be added, removed, or re-thresholded after seeing economic results within the same experiment.

## Budget ceiling

`H01 <= 4` (3 candidates + baseline), `H02 <= 5` (4 + baseline), `H03 <= 5` (4 + baseline). **Total <= 14.** Baseline is one shared, cached population, not recomputed per hypothesis.
