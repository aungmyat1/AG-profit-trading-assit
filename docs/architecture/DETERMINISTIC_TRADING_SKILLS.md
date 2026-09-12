# Deterministic Trading Skills

The canonical classification is `.agents/skills/SKILL_REGISTRY.yaml` (with its
`.claude/skills/` discovery mirror). It separates five
authority layers without changing existing strategy behavior:

1. **Deterministic Trading Skills** compute reproducible market facts and
   classifications and may emit only `MarketObservation` values.
2. **Strategy Engines** consume market data or observations and remain the sole owner
   of strategy-specific interpretation and trade decisions.
3. **AI Agents** research, diagnose, experiment, and explain. Their output is advisory.
4. **Validation/Governance** consumes evidence and gates lifecycle promotion according
   to policy; skills cannot promote strategies.
5. **Execution** consumes an eligible proposal and acts only through its existing,
   separately authorized execution gates.

```text
Market Data -> Deterministic Trading Skills -> Market Observations
            -> Strategy Engine -> Strategy Decision
            -> Validation/Governance -> Proposal / authorized Execution
```

| Layer | Observe Market | Decide Strategy | Propose Trade | Promote | Execute |
| --- | ---: | ---: | ---: | ---: | ---: |
| Deterministic Trading Skill | YES | NO | NO | NO | NO |
| Strategy Engine | YES/consume | YES | YES | NO | NO |
| Validation/Governance | YES/consume | NO | gate | YES according to policy | NO |
| AI Diagnostic Agent | YES/consume | advisory only | NO | NO | NO |
| Execution Engine | NO | NO | consume | NO | YES when authorized |

`trading_skills.TradingSkill` is the minimal interface and `MarketObservation` its
authority-limited output. Existing deterministic packages remain the implementations;
future adapters may expose this interface without rewriting their behavior. Strategy
IDs, strategy rules, risk rules, replay logic, lifecycle state, and execution logic are
outside this interface and unchanged.
