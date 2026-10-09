---
class: design
state: DESIGN
owner_reviewed: null
review_by: 2027-01-06
---
# L2 absence semantics (proposal)

**Status: OWNER_DECISION_PENDING.** Nothing in the repository implements this proposal. The
verifier (`scripts/asw_v112_logic_verification.py`) keeps the old rule until the owner decides.

## Question

How should Logic Gate L2 (contract↔engine equivalence) report a symbol and window where the recorded
data contains **no conforming ticket**? This is about missing evidence, not a divergence.

## Old rule (in force)

L2 PASS for a symbol requires both of:

1. no undeclared or NOT_EVALUABLE L2 check on any recorded case, **and**
2. a conforming sweep that passes L1–L4 in **both** windows (ASIAN_LONDON and LONDON_NEWYORK).

If (1) fails, L2 is FAIL. If (1) holds but a window has no conforming ticket, that window is
**NOT_EVIDENCED** and the symbol verdict is **PARTIAL**. It is never PASS.

## Proposed rule

L2 PASS for a symbol requires only (1). A window with no conforming ticket is recorded as
NOT_EVIDENCED **coverage**, but it no longer affects the L2 verdict. The symbol verdict is
LOGIC_VERIFIED if every other gate passes.

## Results on the committed fixtures (2026-10-09)

| Symbol | Data | Undeclared L2 checks | Conforming windows | Old rule | Proposed rule |
|---|---|---|---|---|---|
| EURUSD | `EURUSD_M15_recorded.csv`, 5 days | 0 | ASIAN_LONDON, LONDON_NEWYORK | L2 PASS → LOGIC_VERIFIED | L2 PASS → LOGIC_VERIFIED |
| GBPUSD | `GBPUSD_M15_recorded.csv` (#114), 10 days | 0 | ASIAN_LONDON only | L2 NOT_EVIDENCED (LONDON_NEWYORK) → PARTIAL | L2 PASS → LOGIC_VERIFIED |

Source: `docs/status/AGP_C3_ASW_V112_GBPUSD_LOGIC_VERIFICATION_2026-10-09.json`
(`checks.L2_specification_engine_equivalence.evidence`, `gates_by_symbol`, `verdicts`).

## Risk

Under the proposed rule, **a symbol can pass L2 without ever producing a ticket.** The extreme case is a
symbol whose recorded days yield no conforming ticket at all. It has zero undeclared checks only
because nothing was checked, so L2 would read PASS on no evidence. The old rule needs at least one
conforming ticket per window. That is a positive demonstration that the contract and engine agree on a
case that actually reaches a ticket.

The cost of the old rule: a symbol with a short fixture stays PARTIAL until enough recorded days
include a conforming ticket in every window (for GBPUSD, a longer capture).

## Options for the owner

1. Keep the old rule (status quo). GBPUSD stays PARTIAL until its fixture contains a conforming
   LONDON_NEWYORK ticket.
2. Adopt the proposed rule, with an added minimum (for example, at least one conforming ticket per
   symbol in any window) so a symbol cannot pass L2 with zero tickets.
3. Adopt the proposed rule as written (accepting the risk above).

A decision is recorded as a row in `docs/governance/OWNER_DECISION_REGISTER.md`; any code change follows
in a separate PR.
