# AG OSS-First TradeTicket Vertical Slice V1 (R2) — status

Date: 2026-09-29. Classification: **TRADETICKET_PIPELINE_READY_NO_STRATEGY_AUTHORITY**.
Base: `platform/fx-opportunity-v2` @ `76348c7` (tree `5f27bf5e`). Branch: `feat/oss-first-tradeticket-slice-v1`.
Plan / component map: `docs/plans/AG_OSS_FIRST_TRADETICKET_VERTICAL_SLICE_V1.md`.

## What exists now

`src/trade_ticket/` (new, capability zero):

- `qualification.py`: StrategyQualification. It checks gates in this order: proposal authority and mode namespace, supported symbol and cycle, MarketState↔candidate consistency, look-ahead, staleness and expiry, strategy-owned setup, and strategy-owned targets.
- `ticket.py`: the single `TradeTicket` model, `AG_TRADE_TICKET_V1`, with status `PREPARED_ONLY | PREPARED_TEST_ONLY` and `execution_authority = NONE`. It embeds the unmodified `CanonicalProposal`. The module also holds:
  - the owner-confirm lifecycle, declared but not implemented;
  - the owner view, with an advisory-only AI slot;
  - `prepare_from_fx_opportunity`.
- `sizing.py`: `size_position`, restored verbatim from `1a8e7c5:src/execution/risk.py` (the function-body hash is pinned in a test). The risk policy comes only from the cycle's pilot config (`risk_policy_from_pilot`, 0.5% per trade, 1.0% aggregate). There is no loader for `config/trading.demo.yaml` (1.0%) and no fallback between the two.

Reused unchanged: MarketState, OpportunityCandidate, the funnel, ProposalEligibility, `to_canonical_proposal`, the instrument/broker contract, `SymbolMeta`, and the fingerprint helper. The live runner, scanner, eligibility and bridge are not modified.

## Proven outcomes

| Path | Result |
|---|---|
| EURUSD frozen fixture (`PIPELINE_TEST_` namespace) → qualify → eligibility → proposal → ticket | `PREPARED_TEST_ONLY`, 0.38 lots / $49.40 at 0.5% of $10k, `market_authoritative=false` |
| ST_ASIAN_SWEEP_5R_V1 Opportunity (real runner, REAL- and REPLAY-labelled) | `NO_PROPOSAL_AUTHORITY` (`REGISTRY_FIELD_ABSENT`), no eligibility call, no ticket. The existing eligibility gate alone would have returned ELIGIBLE. |
| GBPUSD fixture | `PREPARED_TEST_ONLY` via the same contracts (configuration only) |
| USDJPY | no strategy binding for either cycle; sizing geometry only |

Fail-closed coverage:

- **Geometry:** NaN or Inf entry, stop or target; wrong-side stop; entry equal to stop; wrong-side target; missing targets; missing geometry.
- **Symbol and session:** wrong symbol or MarketState symbol; symbol not in the contract; unsupported cycle.
- **Time:** stale MarketState; expired Opportunity; look-ahead.
- **Data mode:** synthetic data; data-mode mismatch.
- **Provenance and account:** missing provenance; broker server or environment mismatch.
- **Risk:** missing risk policy, or a policy from a foreign pilot; aggregate risk unknown or exceeded; NaN equity.
- **Symbol metadata:** metadata symbol or digits mismatch; invalid metadata; synthetic metadata in REAL mode.
- **Duplicates:** an identical duplicate is idempotent; a conflicting duplicate is blocked.

Determinism: identical same-process results, an identical fresh-process fingerprint, and restart parity via JSON round-trip (tampering is detected). The semantic hash covers every field except `ticket_id` and itself; `created_at` is the deterministic evaluation instant, so no timestamps are excluded.

## OSS

- **Adopted:** none. No indicator is needed on this path, so `pandas-ta-classic` is not required and ATR parity was not evaluated.
- **Reference only:** `smartmoneyconcepts`, not imported by `src/`. The `requirements.txt` pin is used only by `scripts/run_discovery_backtest.py` and `scripts/research/fx_discovery_parity_harness.py`, so it can move to a research-only requirements file later.
- **Rejected:** vectorbt.
- **Backtesting.py (AGPL):** `PRODUCT_RUNTIME_REACHABILITY = NOT_REACHABLE`. It is imported only by `research_external/adapters/backtesting_py.py`, and a static plus fresh-interpreter boundary test now guards this.

## Containment

`BROKER_ORDER_CHECK_CALLS = 0`, `BROKER_ORDER_SEND_CALLS = 0`, `OTHER_EXECUTION_MUTATIONS = 0`. This is proven three ways:

- **Statically:** AST scan of calls and imports.
- **Transitively:** fresh interpreter, with no execution, authorization, ticket_delivery, owner_decision or scheduler modules loaded.
- **At runtime:** MT5 mutation APIs trapped.

`src/execution` remains absent. No Demo or Live authority. No scheduler. No registry authorization change.

## Tests (2026-09-29, Windows dev box, Python venv, fixtures only)

- `python -m pytest tests/test_trade_ticket_vertical_slice.py -q` → 42 passed
- `python -m pytest tests/test_opportunity_*.py tests/test_proposal_*.py tests/test_fx_opportunity_*.py -q` → 318 passed

Deferred / NOT_EVALUATED:

- A live MT5 run of the ticket pipeline. The MT5 MCP failed to connect this session, and the real result is determined by registry authority regardless.
- An owner-decision bridge, which is not on this lineage.
- The aggregate open-risk snapshot source. The caller must supply `open_risk_pct`; `None` blocks.
