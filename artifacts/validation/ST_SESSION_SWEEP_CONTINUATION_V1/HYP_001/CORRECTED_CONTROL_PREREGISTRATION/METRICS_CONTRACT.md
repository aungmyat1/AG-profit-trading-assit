# Metrics Contract (preregistered before any corrected-CONTROL result is seen)

## Population
- Total occurrences
- Filled trades
- Unresolved trades (`AMBIGUOUS_SEQUENCE` + any other non-terminal state)
- S1 / S2 / S3 count
- LONG / SHORT count
- Session distribution (ASIAN_LONDON / LONDON_NEWYORK)

## Economics
- Gross R
- Friction R
- Net R
- Gross expectancy (R/trade)
- Net expectancy (R/trade)
- Gross profit factor
- Net profit factor
- Max drawdown R
- Win rate
- Consecutive losses

## Exit behavior
- Initial-stop exits
- Partial activations
- Partial activation rate
- BE transitions
- Runner BE exits
- Runner TP reaches (3R)
- Session exits
- Unresolved outcomes
- MFE/MAE where already supported by existing tooling

No metric may be added after seeing corrected-CONTROL results merely because it highlights a favorable or unfavorable feature. This list is exhaustive for this experiment unless amended by a new preregistration.
