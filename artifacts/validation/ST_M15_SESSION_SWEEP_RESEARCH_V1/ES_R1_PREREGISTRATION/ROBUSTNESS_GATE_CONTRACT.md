# ES-R1 Robustness Gate Contract (checks required at ES-R4, not performed here)

Passing the development economic floor (`ECONOMIC_GATE_CONTRACT.md`) does **not** automatically accept a candidate. Before any further advancement, ES-R4 must check:

1. **Parameter-neighborhood stability** — does the candidate's edge persist for threshold values adjacent to the one tested, or does it exist only at one isolated point?
2. **Friction sensitivity** — does the edge survive both `FRICTION_SCENARIO_LOW` and `FRICTION_SCENARIO_HIGH`?
3. **Time-slice stability** — does the edge hold across non-overlapping sub-periods of the development window, not just in aggregate?
4. **Session stability** — does the edge generalize across London/New York (diagnostic per R-H04), or is it concentrated in one session?
5. **Direction stability** — does the edge hold for both LONG and SHORT, or only one?
6. **Concentration analysis** — is the edge driven by a small number of outsized winning trades, or broadly distributed?
7. **Trade-count adequacy** — does the candidate still meet `MIN_RESOLVED_TRADES >= 30` within each stability slice it's evaluated on, or are stability claims being made on inadequate sub-samples?

**A candidate whose edge exists only at one isolated threshold, or only in one time slice/session/direction, must fail robustness advancement** — regardless of how strong its aggregate development-population statistics look.
