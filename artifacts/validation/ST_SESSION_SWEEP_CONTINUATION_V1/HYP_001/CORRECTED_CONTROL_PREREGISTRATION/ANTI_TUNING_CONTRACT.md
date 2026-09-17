# Anti-Tuning Contract

```
CONTROL_RESULTS_MAY_NOT_CHANGE_TREATMENT = true
```

The future corrected-CONTROL result may NOT be used to:
- change `runner_target_r=1.5` (the frozen HYP_001 treatment value);
- add new HYP_001 filters;
- change entry, stop, or setup-selection logic;
- change the friction model;
- select a different development window;
- inspect CONFIRM_001;
- access holdout.

Any new idea arising from corrected-CONTROL results must become a **separately preregistered future hypothesis** with its own ID — never a silent amendment to HYP_001, and never executed within this experiment.

This carries forward, verbatim in spirit, the amendment's own `escalation_rule`: *"If a future corrected-baseline result motivates consideration of a different runner target, that is NEW_HYPOTHESIS_REQUIRED. HYP_001 must not be amended again to absorb that optimization."*
