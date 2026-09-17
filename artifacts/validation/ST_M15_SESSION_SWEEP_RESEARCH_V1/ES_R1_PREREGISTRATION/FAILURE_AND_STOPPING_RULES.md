# ES-R1 Failure and Stopping Rules (frozen before any result is seen)

- If **R-H01** has no candidate clearing the economic floor: record `R-H01 = VALIDATED_NEGATIVE_OR_INCONCLUSIVE`. Do not retune it immediately within this experiment.
- Same rule independently for **R-H02** and **R-H03**.
- If **all three** fail: preserve the deterministic baseline result as-is and reconsider the strategy architecture through a **new**, separately preregistered research cycle — do not widen parameter ranges post hoc within this same experiment.
- No candidate's threshold may be adjusted, added, or removed after economic results are seen, for any of H01/H02/H03, in this experiment.
- Interaction search (`H01×H02×H03` or any pairwise combination) requires a new experiment ID and separate preregistration (`P13`), authorized only after at least two individual hypotheses show sufficient independent evidence under the gates above — never as a silent fallback when individual hypotheses fail.
