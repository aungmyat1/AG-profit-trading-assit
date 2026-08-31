# Live Status Documentation Maintenance

This document defines how AG Profit Trading's operational documentation stays aligned
with code, configuration, strategy authority, broker/exchange validation, and tests.
It is a maintenance contract, not execution authorization.

## Source roles

| Source | Role | Update policy |
|---|---|---|
| Strategy YAML | Signed deterministic strategy behavior | Change only with an intentional strategy revision |
| `config/trading.yaml` | Runtime execution and live-management gates | Never change merely to make documentation agree |
| `strategies/registry.yaml` | Registration and demo/live authorization | Update only from explicit strategy authority |
| `PROJECT_STATUS.md` | Current rolling operational snapshot | Update for every material status change |
| `README.md` | User-facing purpose, safety, quick start, and capability summary | Update when the visible product surface changes |
| `AGENTS.md` | Mandatory repository working and safety rules | Update when agent workflow or authority changes |
| `docs/status/*.md` | Dated milestone and validation evidence | Preserve historical facts; add a new record when superseded |
| `docs/README.md` | Documentation index and authority guide | Update when documentation is added, moved, or superseded |

## Events that require a status update

Update related documentation in the same change set when any of these changes:

- a runtime path becomes reachable, disabled, or removed;
- analysis, proposal, order-check, order-send, or management capability changes;
- demo or live authorization changes for an account, strategy, cycle, venue, or symbol;
- a strategy is registered, activated, frozen, superseded, or retired;
- a previously documented gap is closed or a new material gap is discovered;
- a broker or exchange path is tested live, loses validation, or changes venue semantics;
- default risk, circuit breakers, confirmation requirements, or fail-closed behavior changes;
- the full regression baseline changes at a milestone;
- a user-facing command, configuration path, or operational procedure changes.

## Required update sequence

1. Inspect the authoritative code, configuration, strategy contract, and narrow tests.
2. State the capability precisely: `NOT_IMPLEMENTED`, `INTERFACE_ONLY`, `UNIT_TESTED`,
   `DEMO_VERIFIED`, or `LIVE_VERIFIED`. Do not collapse these states into "supported."
3. Update the rolling snapshot and known gaps in `PROJECT_STATUS.md`.
4. Update `README.md` if users can observe or operate the changed capability.
5. If strategy authority changed, update `strategies/registry.yaml` and
   `strategies/STRATEGY_LEDGER.md` together. Code existence never grants authorization.
6. Add a dated evidence document under `docs/status/` for a material milestone or live
   validation. Link it from `docs/README.md` and from the relevant rolling status entry.
7. Run the narrowest relevant tests. Run the full suite for a milestone or when the
   rolling regression baseline is changed.
8. Record exact evidence: date, command, pass/fail/skip totals, environment, account
   class, venue, symbols, and deferred checks. Redact credentials and sensitive account
   information.
9. Search for stale claims before finishing:

   ```powershell
   rg -n "NOT_IMPLEMENTED|INTERFACE_ONLY|PAUSED|no runtime|no orchestrator|LIVE_VERIFIED|passed|skipped|failed" README.md PROJECT_STATUS.md AGENTS.md docs strategies
   ```

10. Confirm documentation changes did not alter execution configuration or authorize a
    strategy unintentionally.

## Evidence rules

- Unit tests prove deterministic behavior under their fixtures; they are not live
  broker or exchange validation.
- Demo verification must name the account class and preserve the relevant broker result
  without exposing secrets.
- Live verification must identify the exact path exercised. Market-data validation does
  not imply order-send validation.
- A skipped live test is a deferred check, not a pass and not a reason to weaken stale
  data protection.
- Old test totals in dated status documents remain unchanged. Only the rolling snapshot
  carries the current baseline.
- If evidence is unavailable or contradictory, record the capability as unverified and
  fail closed operationally.

## FX and crypto status separation

Report FX/MT5 and crypto venue status independently. In particular, the presence of a
crypto strategy profile or adapter interface does not mean a live candle feed, verified
instrument metadata, paper execution, testnet execution, or live order submission
exists. Track those capabilities separately for each venue.

## Proposal and broker-ticket terminology

Use **proposal ID** or **entry proposal** before execution. Use **broker ticket** only for
an identifier confirmed by MT5 or a crypto venue after order submission. A scheduled
daily report may guarantee a decision state, but it must never promise that market
conditions will qualify for a trade or that execution will succeed.
