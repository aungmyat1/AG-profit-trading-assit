# Open-Source Reuse Matrix

Mission: `AG_LOGIC_VERIFIED_SESSION_TICKET_ACCELERATION_R1`  
Assessment date: 2026-10-07. No external runtime package was added.

| Component | Existing AG implementation | External reference | Reuse decision | License | Validation tests | Performance impact | Adoption status |
|---|---|---|---|---|---|---|---|
| Lookahead / prefix isolation | `v1_tickets.logic_gate.l1_determinism`, closed-bar and session-window tests | Freqtrade lookahead-analysis and recursive-analysis concepts | Adapt diagnostic concepts only; do not import crypto lifecycle/execution assumptions | GPL-3.0 | `test_manual_ticket_logic_gate.py`; prefix/future-mutation work remains successor-fixture dependent | None | REFERENCE_ONLY |
| Swing/BOS/CHoCH/FVG/OB features | Existing deterministic session sweep/reference box; Large-SMC research features | `DMK980/smartmoneyconcepts` | Do not bind to frozen strategy. Candidate cross-check only after confirmation-lag parity fixtures exist | MIT | Required: feature-by-feature fixture parity and future-candle mutation isolation | Avoided runtime dependency | DEFERRED |
| Event-driven fill comparison | `historical_replay.fill_simulator`, `v1_tickets.outcome` first-touch resolver | `kernc/backtesting.py` | AG engines remain canonical; use only as independent DEV comparison if needed | AGPL-3.0 | Existing first-touch/ambiguity tests; independent comparison not required for current logic blocker | None now | REJECTED_FOR_RUNTIME; REFERENCE_ONLY |
| Vectorized candidate screening | Existing replay and performance modules | `polakowo/vectorbt` | DEV-only funnel diagnostics; never fill-level certification | Apache-2.0 | Would require event-driven parity before any claim | Heavy optional stack avoided | DEFERRED |
| Session scanner | `src/session_scanner`, `src/v1_tickets/scan_record.py` | None needed | Reuse AG | Repository license/governance | scanner/checklist/cardinality tests | None | ADOPTED_EXISTING |
| Contract/engine identity | `v1_tickets.authority.logic_identity` | Freqtrade provenance concepts | Reuse AG exact normalized hashes | Repository license/governance | `test_manual_ticket_authority.py` | Negligible | ADOPTED_EXISTING |
| Geometry/risk/cost | `v1_tickets.logic_gate`, `sizing_math.risk` | Backtesting.py fill conventions as comparison only | Reuse AG; fail closed on missing owner risk/metadata | Repository license/governance | logic-gate, sizing and ticket-build tests | None | ADOPTED_EXISTING |
| Ticket/archive/delivery | `v1_tickets.manual_ticket`, `ticket_delivery` | None needed | Extend existing renderer only | Repository license/governance | ticket renderer, policy, concurrency and restart tests | Negligible | ADOPTED_EXISTING |

## Provenance and risk decision

External source URLs are the repositories named above. No source file, dependency, or
transitive package from those projects is copied or installed by this change, so no
third-party code is shipped and no version pin is required. Before future adoption,
record an exact release/commit, verify its then-current license and security posture,
and run AG fixture parity. GPL/AGPL components are intentionally reference-only unless
the owner approves the resulting distribution obligations. This decision avoids heavy
runtime dependencies and preserves frozen strategy semantics.
