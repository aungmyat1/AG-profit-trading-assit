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
| `docs/<domain>/README.md` | Domain navigation | Must remain discoverable from `docs/README.md` |
| Machine-readable manifests | Structured frozen evidence | Do not treat as authorization unless the governing authority explicitly says so |

## Documentation authority invariants

The documentation system uses these non-collapsible distinctions:

```text
DESIGN != IMPLEMENTED
IMPLEMENTED != VALIDATED
VALIDATED != STRATEGY_AUTHORIZED
PROPOSAL != RISK_APPROVAL
RISK_APPROVAL != EXECUTION_AUTHORIZATION
```

A design, roadmap, status narrative, generated report, or machine-readable manifest
must never silently upgrade strategy, proposal, Demo, Live, broker-send, or external
message-delivery authority. When sources disagree, use the authoritative source for the
specific claim and fail closed until the conflict is reconciled.

## Documentation classes

Use these conceptual classes when creating or reviewing documentation. Existing files
do not need mass renaming or front-matter migration.

| Class | Meaning |
|---|---|
| `CURRENT` | Rolling current truth, normally `PROJECT_STATUS.md` |
| `DESIGN` | Architecture or contract intent; non-authorizing by itself |
| `ROADMAP` | Planned sequence, gates, and stop conditions |
| `STATUS_EVIDENCE` | Dated implementation, validation, or operational evidence |
| `AUTHORITY` | Explicit governing source for a bounded decision |
| `OPERATIONS` | Setup, runtime, maintenance, or runbook guidance |
| `HISTORICAL` | Retained evidence that may have been superseded |

Every important document should make it reasonably clear what it is, whether it can
authorize behavior, whether it is current or historical, and where newer truth lives.

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

## Domain discoverability and link integrity

When a new documentation domain introduces `docs/<domain>/README.md`, add a navigation
entry to `docs/README.md` in the same change set. The root documentation index should
route readers to the domain index; it should not duplicate the domain's entire contents.

When documentation is moved or renamed, check inbound relative Markdown links before
finishing. Prefer correcting stale links over renaming historical evidence solely to
match an incorrect index entry.

Repository-relative links are preferred for internal documentation. A documentation
integrity check should fail on broken relative links and on primary documentation-domain
indexes that are not discoverable from `docs/README.md`.

## Current versus historical truth

`PROJECT_STATUS.md` is the rolling whole-project current-status authority. Dated status
records under `docs/status/` are evidence of what was established at a particular time;
they should not be silently rewritten simply because the project later changed.

When a historical document contains a materially stale placeholder or recording error,
prefer a clearly dated `Documentation correction` or `Addendum` that preserves the
original historical context while pointing to the authoritative newer evidence.

Use explicit temporal language where useful: `Current as of`, `Historical evidence`,
`At the time of this status`, `Superseded by`, and `Documentation correction`.

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
