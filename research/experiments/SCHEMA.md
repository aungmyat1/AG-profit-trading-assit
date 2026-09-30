# Experiment Record Schema

Write-once. One file per experiment run. Filename: `<experiment_id>_<run_id>.yaml`.

## Governance rules

- **Write-once**: once a result file exists it is never edited or deleted.
- **HOLDOUT guard**: a run against `data_role: HOLDOUT` is only permitted when
  the experiment's preregistration file exists in `preregistrations/` AND
  `holdout_runs_completed: 0` in that preregistration file. The first run flips
  the count; no further HOLDOUT runs on the same `(experiment_id, hypothesis_id)`
  are allowed without a new, versioned preregistration.
- **DEV / FORWARD**: unrestricted; use freely during development and forward
  monitoring. Results from these roles never count as OOS evidence.

---

## Record fields

```yaml
# ── Identity ────────────────────────────────────────────────────────────────
experiment_id:        string          # E1, E2, E3, … — must match preregistration
run_id:               string          # <experiment_id>_R<seq>, e.g. E1_R01
strategy_id:          string          # canonical strategy ID from strategies/registry.yaml
version:              string          # semantic_version of the strategy under test
hypothesis_id:        string          # H-<N> — must match preregistration hypothesis list
code_hash:            string          # git SHA of the engine commit used
dataset_hash:         string          # SHA-256 of the data file(s) consumed (hex)
recorded_utc:         string          # ISO-8601 datetime when result was written

# ── Scope ────────────────────────────────────────────────────────────────────
symbol:               string          # e.g. EURUSD
sessions:             list[string]    # e.g. [LONDON, NEW_YORK]
date_range_start:     string          # YYYY-MM-DD inclusive
date_range_end:       string          # YYYY-MM-DD inclusive
data_role:            enum            # DEV | HOLDOUT | FORWARD

# ── Costs (itemised) ─────────────────────────────────────────────────────────
costs:
  spread_pips:        float           # average spread applied per trade
  commission_pips:    float           # per-side commission in pips-equivalent
  slippage_pips:      float           # average slippage assumption
  funding_pips:       float | null    # overnight/swap cost per trade (null if intraday-only)
  total_rt_pips:      float           # sum of all round-trip cost components

# ── Results ──────────────────────────────────────────────────────────────────
N:                    int             # total trades in the run
wins:                 int
losses:               int
win_rate:             float           # wins / N
expectancy_gross:     float           # mean R gross of costs
expectancy_net:       float           # mean R net of costs
profit_factor_gross:  float
profit_factor_net:    float
max_drawdown_pct:     float           # peak-to-trough equity drawdown %
mae_mean:             float           # mean Maximum Adverse Excursion in R
mae_p95:              float           # 95th-percentile MAE in R
mfe_mean:             float           # mean Maximum Favourable Excursion in R
mfe_p95:              float           # 95th-percentile MFE in R

# ── Verdict ──────────────────────────────────────────────────────────────────
verdict:              enum            # PASS | FAIL | INCONCLUSIVE
verdict_notes:        string          # free text — must reference acceptance thresholds
```

## Preregistration file fields (see `preregistrations/`)

```yaml
experiment_id:        string
preregistered_utc:    string          # ISO-8601; frozen on creation
strategy_id:          string
version:              string
hypotheses:
  - id:               string          # H-1, H-2, …
    description:      string
acceptance_thresholds:
  expectancy_net_min: float | "OWNER_DECISION_REQUIRED"
  profit_factor_min:  float | "OWNER_DECISION_REQUIRED"
  win_rate_min:       float | "OWNER_DECISION_REQUIRED"
  max_drawdown_max:   float | "OWNER_DECISION_REQUIRED"
scope:
  symbol:             string
  sessions:           list[string]
  date_range_start:   string
  date_range_end:     string
  data_role:          "HOLDOUT"
holdout_runs_completed: 0             # frozen at 0; incremented by result file, not this doc
status:               "PREREGISTERED" # frozen; never edited
```
