# SVOS Virtual Demo Engine V1 — Cycle 1 design

Date: 2026-09-20. Classification: **VD_V1_DESIGN_READY** (contracts only; implementation and qualification are pending).

## Baseline and authority

HEAD before design: `415d0622b82a8bedbabdc620d018969cec51c2cb`; clean worktree. This is the `MI_V1_FROZEN` release commit. `MI_V1_RELEASE_MANIFEST.json` pins TD-8E `f4a1045`, MI design `93586ec`, core `cbb6a43`, parity `2597547`, and compatibility `c435dba`; all are HEAD ancestors. TD-8E final integration status records its own frozen scope. The compatibility target is `ST_SESSION_SWEEP_CONTINUATION_V1@1.0.1`; `session_sweep_continuation.replay.run_replay` remains the sole SSC decision authority. MI snapshot/composer and `market_intelligence.ssc_adapter` supply immutable, provenance-bearing inputs. No virtual component can reinterpret a decision or grant execution authority.

## Architecture

`Frozen dataset → VirtualMarketFeed/VirtualClock → TD-8E admitted event → MI V1 snapshot → SSC compatibility adapter → run_replay decision → proposal adapter → VirtualExchange → VirtualAccount → immutable ledger/outcome`.

The orchestrator processes one event at a time in a canonical order, with a checkpoint containing feed cursor, clock, order/position/account states, ledger head hash, and all bound contract hashes. Playback rate only controls wall-clock delay. The exchange and account are separate state machines; neither imports MT5, execution gateways, or broker order functions. Existing `src/svos/virtual_broker.py` is useful as a reference and adapter source, but its R-only account, integrated fills/account, and single conservative intrabar rule do not satisfy the complete V1 contracts. Existing `src/svos/forward.py` is a research precedent, not a sealed campaign runner.

The component classification and exact reuse boundaries are in `VD_COMPONENT_AUTHORITY_MAP.json`. Time, exchange, account, ledger, governance, and gates have separate contracts alongside this document. These contracts add no running campaign, economic threshold, or strategy qualification.

## Required implementation sequence after this cycle

1. Freeze execution, account, data-quality, and ledger schema versions and test vectors.
2. Implement isolated feed/clock and deterministic exchange/account adapters without modifying MI, TD-8E, SSC rules, or execution authority.
3. Verify causal and semantic parity on development fixtures only; preregister economic thresholds and access policy before any sealed VD data is opened.
4. Admit a separately authorized sealed campaign only after all non-economic admission gates pass.

## Open design decisions before implementation freeze

- Choose the sealed VD dataset and establish its independent identity, availability timestamps, timezone, and permitted execution-quality class. No sealed data was opened here.
- Specify instrument contract metadata, base currency conversion source, and whether margin is supported; until then, unsupported sizing/margin cases reject.
- Preregister latency distributions or deterministic fixed values, spread/slippage/fee sources, and the exact conservative or ambiguity-rejection policy per execution profile.
- Set starting balance, exposure limits, and maximum open positions in a frozen account profile without changing SSC's canonical risk rules.
- Preregister economic thresholds, stress cases, and access count before qualification data access.

## Safety assertion

Design files only. No MI, TD-8E, SSC, registry, execution config, population, campaign, Demo/Live order, DEV_002 economic reuse, or holdout/OOS access. `VD_V1_DESIGN_READY` means the interface and governance design is ready for review, not that an engine or strategy is qualified.
