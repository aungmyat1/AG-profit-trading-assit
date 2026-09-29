# AG OSS ADOPTION / REUSE GATE V1

**Mission:** `ARENA_ASSIST_OSS_ADOPTION_REUSE_GATE_V1`
**Role:** independent OSS evaluation + architecture audit. **Non-authorizing.**
**Date:** 2026-09-29 (UTC)
**Audited platform SHA:** `4bbba3192b2c26245b4e7f0d6d7b15960e0d96c8` (branch base of `arena/01a0ebe9-ag-profit-trading-assit`, from `main`)

This document does **not** implement the product, does **not** perform broker
execution, and grants **no** strategy, proposal, or execution authority. It
classifies reuse candidates so that the TradeTicket vertical slice can be built
with the minimum possible new commodity code.

Every license, version, and causality claim below was verified **this session**
against the authoritative registry (PyPI JSON API), the authoritative repository
(GitHub API / raw file contents), or by **executing the package** in an isolated
virtualenv. Claims sourced only from memory or from GitHub availability are
marked `UNKNOWN`.

---

## CLASSIFICATION

```
CLASSIFICATION = OSS_ADOPTION_PLAN_READY
                 (with OSS_SEMANTICS_BLOCKED scoped to SMC signal authority only)
```

Rationale: the commodity-indicator layer (EMA / ATR / volatility) has a verified,
permissively-licensed, causally-clean ADOPT candidate with **bit-level parity to
AG's existing Wilder ATR**. The SMC feature layer has **no** causally-clean OSS
candidate — every SMC package evaluated repaints — so SMC stays AG-owned and the
OSS versions are demoted to `REFERENCE_ONLY / SEMANTIC_ORACLE`. That is a scoped
block on one layer, not a block on the mission: the TradeTicket vertical slice
does not require OSS SMC.

`CLAUDE_VERTICAL_SLICE_AUDIT = NOT_YET_APPLICABLE` — no vertical-slice diff
exists at the audited SHA. Phase 7 is pre-registered below and runs on the diff.

---

## PHASE 0 — REPO GAP INVENTORY

Capability states at `4bbba31`. Evidence is a real path in this repo.

| # | Capability | State | Evidence (this repo) |
|---|---|---|---|
| 1 | Market data normalization | `EXISTING_AG_GOOD` | `research_external/tooling/mt5_capture.py`, `src/mt5/symbol_resolver.py`, `src/execution_runtime/bybit_linear_perp_feed.py`, `src/strategy_engine/session/candles.py`; timestamp authority already proven per `research_external/resource_audit/CAPABILITY_REUSE_MATRIX.json` |
| 2 | Technical indicators (EMA/ATR/vol) | `EXISTING_AG_NEEDS_WRAPPER` | Only `research_external/semantic/wilder_atr.py` (ATR only, list-of-dicts API, 14 LoC of algorithm). No EMA, no stdev, no vol utilities. Research-tier location, not a platform module. |
| 3 | SMC features (BOS/CHoCH/FVG/OB/liquidity) | `MISSING` (as a platform module) | `smartmoneyconcepts==0.0.27` is **declared in `requirements.txt` but imported by zero `.py` files** (verified: grep hits are docs/skills only). SMC semantics currently live as *prose* in `.agents/skills/*/SKILL.md`, not as code. |
| 4 | Session utilities | `EXISTING_AG_GOOD` | `src/session_clock.py`, `src/strategy_engine/session/{candles,classifier,reference_box,router,setups}.py`, `config/session_flow_v2.yaml` (classifier `ER_ONLY_V2`, VALIDATED) |
| 5 | Strategy interface | `EXISTING_AG_GOOD` | `src/strategy_engine/{engine,loader,models}.py`, `src/opportunity/adapter.py::StrategyFunnelAdapter`, `strategies/registry.yaml` |
| 6 | Backtesting / replay | `EXISTING_AG_GOOD` | `src/session_sweep_continuation/replay.py`, `src/historical_replay/`, golden fixture `artifacts/backtests/golden/two_stage_golden_fixture_v1.json`, parity artifacts in `artifacts/backtests/session_sweep_continuation/` |
| 7 | Fill simulation | `EXISTING_AG_NEEDS_WRAPPER` | `src/historical_replay/fill_simulator.py` is **entry-fill only** (WP0 finding). Exit/SL/TP resolution is currently delegated to `research_external/adapters/backtesting_py.py` — an **AGPL-3.0** dependency (see license gate). |
| 8 | Performance statistics | `EXISTING_AG_GOOD` | `src/performance/calculator.py`, `src/performance/cost_model.py`, `.agents/skills/performance-analysis/scripts/metrics.py`, `external_candidate/{oos_evaluator,walk_forward}.py` |
| 9 | Risk / position sizing | `EXISTING_AG_GOOD` (authority-critical, do not outsource) | `execution/risk.py` (owns entry-side sizing per `README.md`), `packages/risk-engine/` shell |
| 10 | Proposal eligibility | `EXISTING_AG_GOOD` | `src/opportunity/proposal_eligibility.py` (239 LoC), `packages/contracts/v1.py::ProposalEligibilityDecision` |
| 11 | **TradeTicket schema** | **`MISSING`** | `packages/contracts/v1.py` defines `MarketState → Opportunity → ProposalEligibilityDecision → Proposal → OwnerDecision → ExecutionRequest → ExecutionResult`. **There is no `TradeTicket` contract class.** "TradeTicket" today exists only as prose in `docs/` and as *informational ticket delivery* (`ticket_delivery/`, `config/ticket_delivery.yaml`, mode `ARCHIVE_ONLY`). |
| 12 | Persistence | `EXISTING_AG_GOOD` | `src/opportunity/candidate_store.py`, `src/proposal_envelope/ledger.py`, `src/runtime_state/store.py`, `research_external/tooling/artifact_io.py` (Parquet + byte-level SHA-256) |
| 13 | Owner-review UI | `EXISTING_AG_NEEDS_WRAPPER` | `apps/web/`, `src/components/`, Owner Analysis tab; `GET /api/canonical-proposals`, `POST /api/canonical-proposals/{id}/owner-decision` behind `require_owner_auth`. Needs a TradeTicket read-model, not a new UI. |
| 14 | Broker abstraction | `EXISTING_AG_GOOD` (deliberately narrow) | `mt5/connection.py`, `assistant.commands.execute_command()` with non-defaulted `user_confirmed=True`, `config/trading.demo.yaml`. Retired route `410 EXECUTION_ROUTE_RETIRED` proves the boundary is enforced. |
| 15 | Crypto abstraction | `DEFER` | `src/crypto_opportunity_scanner/`, `src/execution_runtime/bybit_linear_perp_feed.py` (public read-only). Execution unimplemented and disabled — correct state. |

**Gap conclusion:** for the TradeTicket vertical slice, exactly **two** things are
genuinely missing — the **TradeTicket contract** (#11) and an **indicator
adapter** (#2). Everything else on the path is already AG-owned and proven.
Anything beyond those two in Claude's diff is a candidate
`UNNECESSARY_CUSTOM_BUILD`.

---

## PHASE 1 + PHASE 4 — OSS CANDIDATES (maturity, verified)

All figures retrieved 2026-09-29 from the GitHub and PyPI APIs.

| Candidate | Authoritative repo | Version verified | Created | Last push | Stars | Open issues | Releases | Maturity read |
|---|---|---|---|---|---|---|---|---|
| pandas-ta-classic | `xgboosted/pandas-ta-classic` | PyPI `0.8.32` (wheel 2026-09-14) | 2025-06-17 | 2026-09-26 | 447 | 16 | 13 | Active, but **young (15 months) and fast-versioning** — `0.3.14b1 → 0.8.32` in 14 months. API-stability risk: **PIN EXACTLY**. |
| smart-money-concepts | `joshyattridge/smart-money-concepts` | PyPI `smartmoneyconcepts 0.0.27` (2026-04-03) | 2023-09-21 | 2026-04-03 | 2033 | 29 | 27 | Popular but **`0.0.x` forever**, ~6 months since last push, 29 open issues. Stars ≠ correctness — see Phase 3. |
| smc-mcp | `AkhileshSelvan/smc-mcp` | `v0.1.0`, **2 commits, both on 2026-06-14** | 2026-06-14 | 2026-06-14 | 2 | 0 | 0 | **Abandoned-at-birth.** 7 tests, no releases, no PyPI presence, 1 fork. Not a dependency under any circumstance. |
| Freqtrade | `freqtrade/freqtrade` | PyPI `2026.8` | 2017-05-17 | 2026-09-29 | 54895 | 30 | monthly CalVer | Excellent maturity. Blocked on license, not quality. |
| CCXT | `ccxt/ccxt` | PyPI `4.5.84` | 2017-05-14 | 2026-09-29 | 44202 | 713 | continuous | Excellent. High issue count is scale, not rot. |
| NautilusTrader | `nautechsystems/nautilus_trader` | PyPI `1.231.0` | 2018-06-25 | 2026-09-29 | 29486 | 153 | frequent | Excellent, but `1.x` with ongoing breaking changes + Rust/Cython build weight. |
| Backtesting.py | `kernc/backtesting.py` | PyPI `0.6.6` | 2019-01-02 | 2026-08-05 | 9005 | 86 | slow | Maintained but slow. **Already in AG's tree** via `research_external/adapters/backtesting_py.py`. |
| vectorbt | `polakowo/vectorbt` | PyPI `1.1.1` | 2017-11-14 | 2026-09-26 | 9209 | 140 | active | Active. **Blocked on license — see Phase 2.** |

Star counts are recorded for completeness and were **not** used as a decision
input. The two decisions that actually moved (`pandas-ta-classic` ADOPT,
`smart-money-concepts` REFERENCE_ONLY) both went *against* the star ranking.

---

## PHASE 2 — LICENSE GATE

AG repo itself has **no `LICENSE` file** and no `license` field in
`pyproject.toml`/`package.json` — it is a private, all-rights-reserved commercial
codebase. That makes every copyleft obligation below a real constraint, and it
also means **AG cannot currently distribute anything it links GPL/AGPL code
into**, because it has no compatible outbound license to offer.

| Candidate | License (verified source) | Classification | Commercial implication |
|---|---|---|---|
| **pandas-ta-classic 0.8.32** | `MIT` — GitHub API `license.spdx_id=MIT`; PyPI `info.license="MIT"` | **`COMMERCIAL_SAFE_PERMISSIVE`** | None beyond attribution. Copy of MIT text + copyright notice in AG's third-party notices file. |
| **smartmoneyconcepts 0.0.27** | Repo `MIT` (GitHub API). **PyPI metadata `license` field is empty/`None`** — a metadata defect, not a license change. | **`COMMERCIAL_SAFE_PERMISSIVE`** (repo-authoritative) with a recorded caveat | Safe, but because the installed artifact carries no license metadata, AG must vendor the upstream `LICENSE` text alongside any pinned copy for its own audit trail. Moot under the Phase-3 outcome (not adopted). |
| **smc-mcp v0.1.0** | `MIT` (LICENSE file fetched and read; "Copyright (c) 2026 Akhilesh") | `COMMERCIAL_SAFE_PERMISSIVE` | License is fine; the *project* is rejected on maturity/supply-chain grounds, not license. |
| **Freqtrade 2026.8** | `GPL-3.0` (GitHub API + PyPI classifier `GNU General Public License v3`) | **`COMMERCIAL_REVIEW_REQUIRED`** | Strong copyleft. Importing Freqtrade into AG's process would make AG's distributed combined work GPL-3.0. **Safe use = read the docs/source as a design reference and write AG code; never import, never vendor, never copy code blocks.** Note it also transitively depends on `ccxt`, `python-telegram-bot`, `SQLAlchemy`. |
| **CCXT 4.5.84** | `MIT` (GitHub API; PyPI `license_expression=MIT`) | **`COMMERCIAL_SAFE_PERMISSIVE`** | None beyond attribution. Note heavy pinned deps (`cryptography`, `aiohttp`, `coincurve`, `uvloop`) — a supply-chain, not license, concern. |
| **NautilusTrader 1.231.0** | `LGPL-3.0-or-later` (GitHub API + PyPI classifier) | **`COMMERCIAL_REVIEW_REQUIRED`** | Weak copyleft. Dynamic linking/unmodified-import use is generally acceptable for a closed product, **but** LGPL §4 relinking obligations plus Nautilus's Rust/Cython static components make "is this really dynamic linking?" a genuine legal question. Not worth answering for a *reference* read. **Reference only = zero obligation.** |
| **Backtesting.py 0.6.6** | `AGPL-3.0` (GitHub API + PyPI classifier `AGPLv3+`) | **`REJECT_LICENSE` for product code; `COMMERCIAL_REVIEW_REQUIRED` for internal research** | **This is a live finding, not hypothetical.** `research_external/adapters/backtesting_py.py` already does `from backtesting import Backtest, Strategy`. AGPL §13 triggers on *network interaction* with a modified/combined work — AG runs a FastAPI service (`src/api/`) and a web workspace. If any AGPL-linked code path ever becomes reachable from `api.app`, AG owes complete corresponding source to every network user. Today it is confined to `research_external/` (offline research), which is defensible, but the boundary is one careless import away from failing. |
| **vectorbt 1.1.1** | **`Apache-2.0` WITH `Commons Clause` v1.0** — LICENSE.md fetched and read in full this session. GitHub API reports `NOASSERTION`. | **`REJECT_LICENSE`** | The mission's instruction not to assume permissive status was correct. Commons Clause removes the right to *Sell*: to "provide to third parties, for a fee… a product or service whose value derives, entirely or substantially, from the functionality of the Software." AG is a commercial trading product. **Not usable. Not OSI-open-source. Do not install.** |
| `vectorbtpro` | commercial/proprietary, not evaluated | `UNKNOWN` | Out of scope; would be a paid licence negotiation, not an OSS adoption. |

### License findings summary

1. **vectorbt is not permissive.** Apache-2.0 + Commons Clause. `REJECT_LICENSE`.
   GitHub's own license detector says `NOASSERTION` — anyone relying on the
   GitHub badge alone would have gotten this wrong.
2. **Backtesting.py AGPL-3.0 is already in the tree.** Highest-priority license
   action item. See `BLOCKERS`.
3. **Freqtrade GPL-3.0 / Nautilus LGPL-3.0** → reference-read only; this costs
   AG nothing because both were only ever candidates for *ideas*.
4. **AG has no LICENSE file**, which is the correct posture for a private
   commercial repo but must be a deliberate, recorded decision — and it is the
   reason copyleft is a hard gate rather than a soft one.
5. **pandas-ta-classic MIT and CCXT MIT are clean.** Both need only attribution.

---

## PHASE 3 — CAUSALITY / LOOK-AHEAD GATE

**This is the decisive phase.** Gate protocol, executed (not reasoned about):

> For bar `T`, compute the feature on the truncated series `bars[0:T+1]`
> ("knowable at T") and on the full series. If they differ, the value at `T`
> depends on bars after `T` → look-ahead / repaint. `settle_lag(T)` = the number
> of additional bars required before bar `T`'s value reaches its final value and
> never changes again.

Harness: isolated venv (`pandas 3.0.6`, `numpy 2.4.6`, `numba 0.67.0`),
synthetic 300–400-bar M5 GBM OHLCV series, deterministic seed, 33 cut points,
settle-lag probed to 25 bars forward.

### 3.1 `smartmoneyconcepts 0.0.27` — **FAILS. Repaints. Structurally.**

Measured `max_settle_lag` in bars (swing_length = 5):

| Feature | Column | Max settle lag | Verdict |
|---|---|---:|---|
| `swing_highs_lows` | `HighLow`, `Level` | **5** | REPAINTS |
| `bos_choch` | `BOS` | 0 | causal *given* swings — but swings repaint |
| `bos_choch` | `CHOCH`, `Level`, `BrokenIndex` | **14** | REPAINTS |
| `fvg` | `FVG`, `Top`, `Bottom` | 1 | near-causal (needs the 3rd bar) |
| `fvg` | `MitigatedIndex` | **26** (unbounded by construction) | REPAINTS |
| `ob` | all columns | 0 at settle, but **30/33 mismatch vs full series at T**, max lag 13 in the wider probe | REPAINTS |
| `liquidity` | `Liquidity`, `Level`, `End`, `Swept` | **never settled within 25 bars (99)** in the wider probe | REPAINTS |
| `retracements` | `Direction`, `CurrentRetracement%`, `DeepestRetracement%` | **14** | REPAINTS |
| `previous_high_low` | all | 0, 0 mismatches | **CAUSAL** |

**Root cause is in the source, not an artifact of my harness.** From
`smartmoneyconcepts/smc.py::swing_highs_lows`:

```python
swing_length *= 2
swing_highs_lows = np.where(
    ohlc["high"] == ohlc["high"].shift(-(swing_length // 2)).rolling(swing_length).max(),
    ...
```

`shift(-(swing_length // 2))` is an **explicit negative (forward) shift**: the
label for bar `i` is computed from a window *centred* on `i`, i.e. it reads
`swing_length/2` bars into the future. This is a centred fractal, which is the
correct definition for *drawing a chart* and an invalid one for *deciding at T*.

Worse, the same function then force-overwrites the series endpoints:

```python
if swing_highs_lows[positions[-1]] == -1: swing_highs_lows[-1] = 1
if swing_highs_lows[positions[-1]] == 1:  swing_highs_lows[-1] = -1
```

The **last bar is unconditionally relabelled** so the swing sequence alternates.
In a live loop the last bar is *the current bar*, so the most recent swing label
is guaranteed to be synthetic and guaranteed to change on the next tick. Every
downstream consumer (`bos_choch`, `ob`, `liquidity`, `retracements` all take
`swing_highs_lows` as an input argument) inherits both defects.

**Verdict:** `REFERENCE_ONLY / SEMANTIC_ORACLE`. **Signal authority DENIED.**
Not because it is wrong about what an order block *is* — its definitions are
reasonable and widely used — but because it answers "where were the swings?"
rather than "what was knowable at T?". `previous_high_low` is the sole causal
export and is not worth a `numba` dependency.

### 3.2 `smc-mcp v0.1.0` — same class of defect, plus fatal immaturity

`src/smc_mcp/smc/structure.py::find_swings` (read this session):

```python
for i in range(lookback, n - lookback):
    is_high = all(highs[i] > highs[i-j] and highs[i] > highs[i+j] ...)
```

`highs[i + j]` is a forward read, and the loop terminates at `n - lookback`, so
the most recent `lookback` bars are *structurally unlabelable*. Same centred
fractal, same causality failure, honestly documented as "symmetric fractal".

**Verdict:** `REFERENCE_ONLY / SEMANTIC_ORACLE`. Its clean, dependency-light,
pure-Python dataclass formulation (`SwingPoint`, `StructureEvent` with
`index = candle index where the break was confirmed`) is a genuinely good
*shape* for AG's own causal implementation to imitate. It is a **reading**, not a
dependency: 2 commits, 2 stars, no release, no PyPI package, no maintenance.

### 3.3 `pandas-ta-classic 0.8.32` — **PASSES**

| Indicator | Mismatches vs truncated (34 cuts) | Max abs drift |
|---|---:|---:|
| `ema(14)` | 0 | 0.0 |
| `atr(14, mamode="rma")` (Wilder) | 0 | 0.0 |
| `atr(14, mamode="sma")` | 0 | 0.0 |
| `stdev(20)` | 0 | 0.0 |
| `bbands(20)` | 0 | 0.0 |
| `true_range()` | 0 | 0.0 |

Bit-identical under truncation. **Signal-feature causality: PASS.**

Two adapter-mandatory caveats, both measured:

**(a) `offset` is a look-ahead switch.** `ta.ema(close, 14, offset=-2)` at bar
100 returns exactly the un-offset value at bar 102 — verified `True`. A negative
`offset` shifts future values backwards. The AG adapter **must reject any
non-zero `offset`** and must not expose the parameter.

**(b) Recursive indicators are warmup-sensitive — a determinism/provenance
risk, not a causality risk.** Same final bar, different history start:

| Indicator | start=0 | start=10 | start=40 | start=100 |
|---|---:|---:|---:|---:|
| `sma(14)` | 0.0 | 0.0 | 0.0 | 0.0 |
| `ema(14)` | 0.0 | 0.0 | 2.2e-16 | 1.7e-12 |
| `atr(14, rma)` | 0.0 | 8.8e-12 | 1.3e-11 | **9.5e-10** |

Economically irrelevant; **provenance-fatal** for a platform that hashes
contracts (`packages/contracts/v1.py` `_freeze` rejects non-finite floats and the
Contract carries a semantic hash). Two runs over the same event with different
buffer lengths would produce different `MarketState` hashes. The adapter **must
pin a warmup bar count** (recommend `>= 10 * period`, minimum 200 bars for
`period=14`) into the strategy contract and record it in provenance, and should
round derived features to a declared precision before hashing.

### 3.4 ATR parity: OSS vs existing AG code — **exact match**

`pandas_ta_classic.atr(..., mamode="rma")` vs
`research_external/semantic/wilder_atr.py::wilder_atr` (itself adapted from the
owner-owned `session-smc-trading-bot` donor at commit `e179fe2`):

| bar | AG `wilder_atr` | pandas-ta-classic `rma` | abs diff |
|---:|---|---|---:|
| 13 | `None` | `NaN` | — (agree) |
| 14 | 0.0010992240629800515 | 0.0010992240629800515 | **0.0** |
| 15 | 0.0010489304834181954 | 0.0010489304834181954 | **0.0** |
| 20 | 0.0009293148788315456 | 0.0009293148788315458 | 2.2e-19 |
| 120 | 0.0012015430461963944 | 0.0012015430461963950 | 6.5e-19 |
| 249 | 0.0010840208808549780 | 0.0010840208808549784 | 4.3e-19 |

Max abs diff over bars 60–249: **1.08e-18** (float64 ULP). Both agree the first
valid value is at index `period` (= 14), both omit `TR[0]`, both seed with
`mean(TR[1..period])`.

This is the strongest single result in the audit. It means:
- AG can adopt `pandas-ta-classic` for ATR **without any semantic change** to
  existing signed behaviour; and
- `wilder_atr.py` should be **retained as the golden semantic oracle** in a
  parity test that runs in CI, not deleted. Keeping it costs 14 lines and buys
  permanent protection against an upstream `0.9.x` semantic drift.

### 3.5 Causality gate summary

```
LOOKAHEAD_GATE_PASS  = pandas-ta-classic (EMA, ATR/rma, ATR/sma, stdev, bbands,
                       true_range) — with offset=0 enforced and warmup pinned
LOOKAHEAD_GATE_FAIL  = smartmoneyconcepts (swings 5b, CHoCH 14b, FVG
                       mitigation 26b+, OB, liquidity, retracements 14b)
LOOKAHEAD_GATE_FAIL  = smc-mcp (centred fractal, last `lookback` bars unlabelable)
NOT_EVALUATED        = Freqtrade / Nautilus / Backtesting.py / CCXT feature
                       semantics — none is a candidate for signal authority, so
                       the gate does not apply
```

---

## PHASE 5 — BUILD-VS-BUY MATRIX

`Adapter?` = does AG need a thin wrapper. `Migration cost` = effort to get to the
decision. `Replacement difficulty` = effort to swap the choice out later (lower
is better — it is the reversibility of the bet).

| Capability | Existing AG implementation | OSS candidate | Decision | Reason | License | Adapter? | Migration cost | Replacement difficulty | Recommended owner |
|---|---|---|---|---|---|---|---|---|---|
| **EMA** | none | pandas-ta-classic `overlap.ema` | **ADOPT (via wrapper)** | Causality PASS, 0 drift; writing another EMA is pure waste | MIT | **Yes** — `ag_indicators` facade | XS (~30 LoC) | **Low** — facade is one file | Claude |
| **ATR** | `research_external/semantic/wilder_atr.py` | pandas-ta-classic `volatility.atr(mamode="rma")` | **ADOPT (via wrapper) + keep AG as oracle** | **Bit-parity 1e-18 with existing signed AG semantics**; zero behavioural risk | MIT | **Yes** | XS | **Low** | Claude |
| **Volatility (stdev, TR, bbands, NATR)** | none | pandas-ta-classic `volatility.*`, `statistics.stdev` | **ADOPT (via wrapper)** | Causality PASS; commodity maths | MIT | Yes (same facade) | XS | Low | Claude |
| **Swing detection** | prose only (`.agents/skills/market-swing-structure-analysis/`) | smartmoneyconcepts `swing_highs_lows`; smc-mcp `find_swings` | **REJECT for authority / REFERENCE_ONLY** | **Measured 5-bar repaint + forced last-bar relabel**; centred window is definitionally non-causal | MIT (irrelevant) | n/a | S — AG must write a **confirmed-at-T+N** swing detector (~60 LoC) | Medium | **AG-owned** (Claude, against the existing skill contract) |
| **BOS / CHoCH** | prose only (`market-structure-analysis/SKILL.md`) | smartmoneyconcepts `bos_choch`; smc-mcp `detect_structure` | **REFERENCE_ONLY** | CHoCH settle lag **14 bars**; inherits repainting swings | MIT | n/a | S–M | Medium | **AG-owned** |
| **FVG** | prose only | smartmoneyconcepts `fvg` | **REFERENCE_ONLY** | Formation is near-causal (lag 1) but `MitigatedIndex` lag **26+ and unbounded** — mitigation is a *forward scan* | MIT | n/a | S (formation is ~15 LoC and trivially causal) | Low | **AG-owned** |
| **Liquidity sweep** | `.agents/skills/sweep-detection-range-v2/`, `src/strategy_engine/session/setups.py` (`ST_ASIAN_SWEEP_5R_V1` is live) | smartmoneyconcepts `liquidity` | **EXISTING_AG_REUSE** | AG's sweep detector is signed, backtested (`artifacts/backtests/`) and causal by construction; OSS version **never settled** in 25 bars | MIT (irrelevant) | n/a | **None** | n/a | **AG-owned (already done)** |
| **Order blocks** | prose only (`supply-demand-analysis/SKILL.md`) | smartmoneyconcepts `ob` | **REFERENCE_ONLY** | Repaints; also `OBVolume` needs a volume series MT5 only gives as tick volume | MIT | n/a | M | Medium | **AG-owned**, and **DEFER** — not needed for the vertical slice |
| **Session slicing** | `src/session_clock.py`, `src/strategy_engine/session/*`, `config/session_flow_v2.yaml` | smartmoneyconcepts `sessions`; Freqtrade timeframe utils | **EXISTING_AG_REUSE** | `ER_ONLY_V2` is VALIDATED and owner-signed; OSS session helpers are naive UTC windows with no DST/broker-offset authority | n/a | n/a | **None** | n/a | **AG-owned (already done)** |
| **Backtesting / replay** | `src/session_sweep_continuation/replay.py`, `src/historical_replay/`, golden fixture | Freqtrade; Nautilus; Backtesting.py | **EXISTING_AG_REUSE** (+ `REFERENCE_ONLY` for Nautilus event model) | AG's replay is parity-tested against a frozen golden fixture. Migration = re-proving every signed artifact. **Demonstrably longer, not shorter.** | GPL / LGPL / AGPL — all blocked anyway | n/a | **None** | n/a | **AG-owned (already done)** |
| **Fill simulation** | `src/historical_replay/fill_simulator.py` (**entry-only**) | Backtesting.py (currently used in `research_external/adapters/backtesting_py.py`) | **WRAP now / PLAN REPLACEMENT** | The one real gap. AGPL makes the current adapter a containment liability, not a product option | **AGPL-3.0 → `REJECT_LICENSE` for product** | Yes (exists) | S — an OHLC first-touch SL/TP resolver with a declared same-bar tie policy is ~80 LoC | **Low** | **AG-owned**; keep AGPL strictly in `research_external/` |
| **Performance statistics** | `src/performance/calculator.py`, `metrics.py`, `external_candidate/*` | Freqtrade analytics; QuantStats | **EXISTING_AG_REUSE** | Already built, already produces signed artifacts | n/a | n/a | None | n/a | **AG-owned (already done)** |
| **Risk sizing** | `execution/risk.py` | Freqtrade `stake_amount`; Nautilus sizing | **EXISTING_AG_REUSE — never outsource** | Authority-critical. An OSS sizing bug is an owner-capital bug. | n/a | n/a | None | n/a | **AG-owned, owner-reviewed** |
| **Exchange API (FX)** | `mt5/connection.py`, `assistant.commands.execute_command()` | none (CCXT has no MT5/FX broker) | **EXISTING_AG_REUSE** | No OSS candidate exists for the MT5 path | n/a | n/a | None | n/a | **AG-owned** |
| **Exchange API (crypto, future)** | `src/execution_runtime/bybit_linear_perp_feed.py` (public read-only) | **CCXT** | **ADOPT — DEFERRED (Phase 9)** | MIT, mature, 100+ venues; would delete bespoke feed code | MIT | Yes — behind the same broker-adapter boundary | M, **not now** | Low | Deferred |
| **TradeTicket schema** | **none** | none (Freqtrade `Trade`, Nautilus `Order` are *execution* records, not *pre-authorization governance* records) | **BUILD — AG-owned, small** | AG's ticket is a governance artifact carrying provenance, eligibility linkage and owner-confirmation state. No OSS equivalent exists because no OSS project has this authority model. | n/a | n/a | XS–S (~80 LoC in `packages/contracts/v1.py`, matching the 7 existing Contract classes) | n/a | **AG-owned (Claude)** |
| **Proposal eligibility** | `src/opportunity/proposal_eligibility.py` + `ProposalEligibilityDecision` | none | **EXISTING_AG_REUSE** | Already implemented; extend, do not rewrite | n/a | n/a | None | n/a | **AG-owned (already done)** |
| **Event orchestration** | `src/opportunity/engine.py` (Safety Invariants #8/#9), `transitions.py`, `runtime_state/store.py` | Nautilus event/message bus | **EXISTING_AG_REUSE** (+ `REFERENCE_ONLY` for Nautilus patterns) | AG's funnel engine already enforces idempotence and terminal-outcome stickiness — the properties a message bus would *not* give for free | LGPL (blocked) | n/a | None | n/a | **AG-owned (already done)** |

**Matrix totals:** `ADOPT` 3 (all pandas-ta-classic) · `ADOPT-deferred` 1 (CCXT) ·
`WRAP` 1 (fill simulation) · `REFERENCE_ONLY` 6 · `REJECT` 2
(vectorbt license, Backtesting.py-in-product) · `EXISTING_AG_REUSE` 9 ·
`BUILD` 1 (TradeTicket).

**Nine of twenty capabilities are already built in AG.** That is the headline.

---

## PHASE 6 — RECOMMENDED TARGET ARCHITECTURE

```
┌─ OSS commodity layer ─ BROKER_ACCESS=NONE  EXECUTION_AUTHORITY=NONE  PROPOSAL_AUTHORITY=NONE ─┐
│  pandas-ta-classic 0.8.32 (MIT)  —  ema / atr(rma) / stdev / true_range / bbands             │
│  [future, deferred] ccxt (MIT)   —  crypto market data + venue metadata only                 │
└───────────────────────────────────────────────────────────────────────────────────────────────┘
                                          ↓  (import boundary: pure Series in → Series out)
┌─ thin AG adapters ─ AG-OWNED ────────────────────────────────────────────────────────────────┐
│  ag_indicators/  — offset forbidden · warmup pinned · precision declared · parity-tested      │
│                    against research_external/semantic/wilder_atr.py (golden oracle)           │
└───────────────────────────────────────────────────────────────────────────────────────────────┘
                                          ↓
   AG MarketState            ── AG-OWNED ── packages/contracts/v1.py (final, non-subclassable)
                                          ↓
   AG SMC features           ── AG-OWNED ── causal swing/BOS/CHoCH/FVG, confirmed-at-T+N,
                                            semantics cross-checked (not sourced) against
                                            smartmoneyconcepts / smc-mcp as oracles
                                          ↓
   AG Opportunity            ── AG-OWNED ── src/opportunity/engine.py (invariants #8, #9)
                                          ↓
   AG strategy qualification ── AG-OWNED ── src/strategy_engine/, strategies/registry.yaml
                                          ↓
   AG ProposalEligibility    ── AG-OWNED ── src/opportunity/proposal_eligibility.py
                                          ↓
   AG TradeTicket            ── AG-OWNED ── ** NEW — the only new contract **
                                          ↓
   AG owner authorization    ── AG-OWNED ── require_owner_auth, per-ticket user_confirmed=True
                                          ↓
   broker adapter            ── AG-OWNED ── assistant.commands.execute_command() → MT5
```

### Boxes that must remain AG-owned (confirmed, no OSS substitution permitted)

| AG-owned concern | Why no OSS may hold it |
|---|---|
| **Authority** | No imported package may decide that something is tradeable. |
| **Risk policy** | Owner capital. `execution/risk.py` only. |
| **Provenance** | Contract hashing + `event_id`/`correlation_id` lineage is AG-specific and is why warmup must be pinned. |
| **ProposalEligibility** | Encodes AG's governance gates (R0–R9, lifecycle stage, economic gate). Has no OSS analogue. |
| **TradeTicket governance** | A pre-trade governance object, not a broker order. Freqtrade's `Trade` and Nautilus's `Order` are post-authorization records — adopting either would smuggle execution semantics into a pre-authorization boundary. |
| **Owner confirmation** | Non-defaulted, per-instruction `user_confirmed=True`. |
| **Broker execution boundary** | Single choke point; `410 EXECUTION_ROUTE_RETIRED` proves it is enforced. |
| **Causal SMC semantics** | Every OSS SMC implementation evaluated repaints. Causality *is* AG's edge here. |

### The one architectural rule this audit adds

> **OSS may compute numbers over a closed bar series. OSS may never see an
> account, an order, a ticket, or the owner.** The `ag_indicators` facade is the
> membrane: `pandas.Series` in, `pandas.Series` out. Nothing above `MarketState`
> imports an OSS trading package.

---

## PHASE 7 — CLAUDE CHANGE REVIEW (pre-registered)

`CLAUDE_VERTICAL_SLICE_AUDIT = NOT_YET_APPLICABLE` — no vertical-slice diff
exists at `4bbba31`. The criteria are fixed **now**, before the diff, so they
cannot be retrofitted to whatever gets written.

When the TradeTicket vertical-slice candidate lands, each new subsystem in the
diff is marked `UNNECESSARY_CUSTOM_BUILD` unless it carries a valid rejection
record. Pre-registered expectations:

| If the diff contains… | Expected mark | Because |
|---|---|---|
| A new EMA / ATR / stdev / true-range implementation | **`UNNECESSARY_CUSTOM_BUILD`** | pandas-ta-classic is MIT, causality-PASS, and **bit-identical to AG's own `wilder_atr`** |
| A new candle/session-window utility | **`UNNECESSARY_CUSTOM_BUILD`** | `src/session_clock.py` + `session/` + `ER_ONLY_V2` already exist and are VALIDATED |
| A new eligibility evaluator | **`UNNECESSARY_CUSTOM_BUILD`** | `src/opportunity/proposal_eligibility.py` exists |
| A new persistence/ledger/store | **`UNNECESSARY_CUSTOM_BUILD`** | `candidate_store.py`, `proposal_envelope/ledger.py`, `runtime_state/store.py`, `artifact_io.py` |
| A new performance/metrics module | **`UNNECESSARY_CUSTOM_BUILD`** | `src/performance/calculator.py` + `metrics.py` |
| A second contract/provenance/hashing scheme | **`UNNECESSARY_CUSTOM_BUILD` (severe)** | `packages/contracts/v1.py` is deliberately final and non-subclassable; a parallel scheme breaks lineage |
| A new owner-decision or auth path | **`UNNECESSARY_CUSTOM_BUILD` (severe)** | `require_owner_auth` + `/api/canonical-proposals/{id}/owner-decision` exist and are the authority |
| A new broker/order path | **`REJECT` — out of mission scope** | Single choke point only |
| A **`TradeTicket` contract** in `packages/contracts/v1.py` | **`JUSTIFIED_NEW_BUILD`** | Genuinely missing; no OSS equivalent; must reuse the existing `Contract` base, `_freeze`, `_timestamp`, `_identifier` |
| An **`ag_indicators` adapter** over pandas-ta-classic | **`JUSTIFIED_NEW_BUILD`** | This is the adopted-reuse mechanism |
| A **causal SMC feature module** (swings/BOS/FVG, confirmed-at-T+N) | **`JUSTIFIED_NEW_BUILD`** | Only if the slice actually needs it — otherwise `DEFER`; every OSS option failed the causality gate |
| An **OHLC first-touch SL/TP resolver** | **`JUSTIFIED_NEW_BUILD`** | Removes the AGPL dependency; must declare its same-bar SL/TP tie policy explicitly |

**Valid rejection record** = a written note naming the specific OSS/AG candidate
considered, the specific disqualifying property, and the evidence. "I didn't
find one" is not a rejection record.

I will **audit** the diff and return an exact recommendation. I will **not**
rewrite it.

---

## PHASE 8 — SECURITY / SUPPLY CHAIN

Inspected by installing each package into an isolated venv and reading what it
actually does.

| Check | pandas-ta-classic 0.8.32 | smartmoneyconcepts 0.0.27 | smc-mcp |
|---|---|---|---|
| Install scripts / build hooks | None. Pure `py3-none-any` wheel, 418 KB. No sdist build step. | None. Wheel 13.7 KB + sdist. | n/a (not installable) |
| Runtime deps | `numpy>=2.0`, `pandas>=2.0` — **both already AG deps** | `pandas`, `numpy`, **`numba>=0.58.1`** | `mcp`, `pandas` |
| Installed footprint | **3.3 MB** | 92 KB — **but pulls `numba` 35 MB + `llvmlite`** | n/a |
| Network at import | **`pandas_ta_classic.utils.data.{yahoofinance,alphavantage}` ARE imported at package import** — verified. `requests` not installed and import still succeeded ⇒ the HTTP import is lazy/guarded inside the functions. No connection is opened. | None | n/a |
| Network at runtime | Only if `ta.df.ta.ticker()` / `av()` / `yf()` are called. **Never call these.** | None | MCP server = a network service by design |
| Filesystem access | None in indicator paths | None | reads/writes per MCP tool |
| Subprocess execution | None in indicator paths | None | n/a |
| Broker access | **None** | **None** | **None** |
| Import-time side effects | Logging config only | **Prints a coloured "⭐ please star us" banner to stdout on every import** | n/a |
| Dependency-confusion / typosquat risk | Distinct name, own GitHub org, consistent metadata | Package name (`smartmoneyconcepts`) ≠ repo name (`smart-money-concepts`) — a mild pinning footgun | Not on PyPI at all |

### Supply-chain findings

1. **`smartmoneyconcepts` is a declared-but-unused dependency.** It is pinned in
   `requirements.txt` at `0.0.27` and imported by **zero** `.py` files in the
   repo. It drags in `numba` + `llvmlite` (~50 MB, a JIT compiler) for no
   executed code. Given the Phase-3 causality failure it will never gain signal
   authority. **Recommendation: remove it from `requirements.txt`.** If retained
   for oracle/cross-check use, move it to a `[research]` extra so it is absent
   from the runtime environment.
2. **`smartmoneyconcepts` prints to stdout at import.** For a platform whose CLIs
   emit machine-read JSON and whose artifacts are byte-hashed, an unconditional
   ANSI-coloured banner on `import` is a real contamination risk. Another reason
   to keep it out of the runtime environment.
3. **`pandas-ta-classic` loads network-capable data fetchers at package
   import**, and importing a leaf module (`pandas_ta_classic.volatility.atr`)
   does **not** avoid this — the package `__init__` runs either way. No socket is
   opened and `requests` is not required, so residual risk is **LOW**, but the
   adapter should be the *only* module in AG that imports
   `pandas_ta_classic`, and the runtime should keep an egress denylist.
4. **`smc-mcp` must never be installed.** It is an MCP *server* — a
   network-listening process with tool-call semantics — with 2 commits and 2
   stars. Read the file, close the tab.
5. **Pin exactly.** `pandas-ta-classic` went `0.3.14b1 → 0.8.32` in 14 months.
   Pin `==0.8.32`, add a hash, and let the `wilder_atr` parity test be the
   upgrade gate.

### Mandatory authority labels for every adopted OSS package

```
pandas-ta-classic:   BROKER_ACCESS = NONE   EXECUTION_AUTHORITY = NONE   PROPOSAL_AUTHORITY = NONE
ccxt (future):       BROKER_ACCESS = NONE   EXECUTION_AUTHORITY = NONE   PROPOSAL_AUTHORITY = NONE
                     (market data only; any execution use is a separate, owner-authorized gate)
smartmoneyconcepts:  BROKER_ACCESS = NONE   EXECUTION_AUTHORITY = NONE   PROPOSAL_AUTHORITY = NONE
                     + SIGNAL_AUTHORITY = NONE  (causality gate FAIL)
```

---

## PHASE 9 — CRYPTO FORWARD PLAN (mapping only — NOT implemented)

VT Markets offers crypto on MT5, and AG already has a public read-only Bybit
BTCUSDT linear-perp feed. Two viable future paths:

```
                       BTCUSD/BTCUSDT MarketState
                                 ↓
                        Crypto Opportunity          ← src/crypto_opportunity_scanner/ (exists)
                                 ↓
                         Crypto Strategy            ← same strategy_engine interface
                                 ↓
                            Proposal                ← same ProposalEligibility
                                 ↓
                           TradeTicket              ← SAME contract, symbol-class aware
                                 ↓
                       owner authorization          ← SAME
                                 ↓
                         broker adapter             ← MT5 (VT) | CCXT (native venue)
```

| Path | Work saved | Work added | Assessment |
|---|---|---|---|
| **A — VT/MT5 crypto (recommended first)** | Reuses the entire existing MT5 connection, symbol resolver, authorization boundary, and demo gating. Crypto becomes **a symbol-class change, not an architecture change**. | Contract-size/tick/funding/24×7-session conventions (`.agents/skills/multi-asset-conventions/`), weekend-bar handling, no daily rollover | **Lowest marginal cost by a wide margin.** Do this first. |
| **B — CCXT native venue** | MIT; one API for 100+ venues; would replace the bespoke `bybit_linear_perp_feed.py` with a maintained abstraction; real orderbook/funding/OHLCV normalization | New auth/key custody, a second execution boundary to govern, heavy deps (`cryptography`, `aiohttp`, `coincurve`) | **Adopt for market data when crypto research widens beyond Bybit. Defer execution indefinitely** — a second execution path is a governance cost, not a code cost. |
| **C — Freqtrade** | Would give a crypto lifecycle for free | **GPL-3.0** + wholesale architecture migration + it owns the decision loop AG must own | **REJECT.** The license alone ends it; the authority model would end it anyway. |

Crypto-specific causality note: 24×7 markets remove the session-boundary anchor
that AG's FX `ER_ONLY_V2` classifier depends on. The causal-SMC work done for FX
transfers; the **session** work does not. Budget for that, not for plumbing.

**Nothing in Phase 9 is to be implemented in the current mission.**

---

## FINAL REPORT

```
CLASSIFICATION = OSS_ADOPTION_PLAN_READY
                 (OSS_SEMANTICS_BLOCKED scoped to the SMC feature layer only;
                  the TradeTicket vertical slice is not blocked by it)

AUDITED_PLATFORM_SHA = 4bbba3192b2c26245b4e7f0d6d7b15960e0d96c8
```

**AG_COMPONENTS_REUSE** (reuse as-is; do not reimplement)
```
src/opportunity/engine.py                    funnel orchestration, invariants #8/#9
src/opportunity/proposal_eligibility.py      eligibility evaluation
src/opportunity/contracts.py                 MarketEvent / OpportunityCandidate
src/opportunity/candidate_store.py           candidate persistence
packages/contracts/v1.py                     Contract base, _freeze/_timestamp/_identifier,
                                             MarketState … ExecutionResult  (EXTEND, never fork)
src/proposal_envelope/{models,ledger,strategy_authority}.py
src/strategy_engine/**                       strategy interface + loader + registry binding
src/strategy_engine/session/**               session slicing, ER_ONLY_V2 (VALIDATED)
src/session_clock.py                         session authority
src/performance/{calculator,cost_model}.py   performance + friction
execution/risk.py                            risk sizing — AUTHORITY-CRITICAL, never outsource
src/historical_replay/**, src/session_sweep_continuation/replay.py   replay (golden-fixture parity)
src/runtime_state/store.py                   runtime state
research_external/tooling/artifact_io.py     Parquet + byte-level SHA-256
research_external/semantic/wilder_atr.py     RETAIN as the ATR golden semantic oracle
mt5/connection.py + assistant.commands.execute_command()   broker boundary
apps/web owner-decision surface + require_owner_auth       owner authorization
```

**OSS_ADOPT**
```
pandas-ta-classic == 0.8.32   MIT   (xgboosted/pandas-ta-classic)
  scope: ema, atr(mamode="rma"), atr(mamode="sma"), stdev, true_range, bbands
  conditions: (1) accessed ONLY through the ag_indicators adapter
              (2) offset parameter forbidden (verified look-ahead switch)
              (3) warmup bar count pinned in the strategy contract and recorded
                  in provenance (measured drift up to 9.5e-10 on ATR)
              (4) CI parity test vs research_external/semantic/wilder_atr.py
              (5) pinned exactly + hash; upgrades gated on the parity test
              (6) never call ta.ticker()/av()/yf()
  authority:  BROKER=NONE  EXECUTION=NONE  PROPOSAL=NONE
```

**OSS_WRAP**
```
ag_indicators facade over pandas-ta-classic     (the adapter above)
Backtesting.py 0.6.6 — WRAP RETAINED ONLY INSIDE research_external/, AGPL-contained,
  with a scheduled replacement by an AG OHLC first-touch SL/TP resolver
ccxt — WRAP, DEFERRED to the crypto phase (MIT, market data only)
```

**OSS_REFERENCE_ONLY**
```
smart-money-concepts (smartmoneyconcepts 0.0.27, MIT)  SEMANTIC_ORACLE for SMC definitions
                                                        SIGNAL_AUTHORITY = NONE (causality FAIL)
smc-mcp v0.1.0 (MIT)          SEMANTIC_ORACLE / API-shape reference. Never install.
Freqtrade 2026.8 (GPL-3.0)    read-only design reference: strategy interface, dry-run,
                              config patterns, trade lifecycle. NEVER import or copy code.
NautilusTrader 1.231.0 (LGPL) read-only design reference: event-driven architecture.
                              No migration — AG's replay is already golden-fixture parity-tested.
Backtesting.py                reference for fill-resolution semantics (order at next bar's open)
```

**OSS_REJECT**
```
vectorbt 1.1.1        REJECT_LICENSE — Apache-2.0 WITH Commons Clause (LICENSE.md read in full).
                      The Commons Clause forbids selling a product whose value derives
                      substantially from the software. AG is commercial. Not OSI-open-source.
                      GitHub reports NOASSERTION — the badge would have misled.
Backtesting.py        REJECT for product/runtime code (AGPL-3.0 + AG runs a network service).
                      Research-only containment in research_external/ is tolerated, not blessed.
Freqtrade             REJECT as a dependency or migration target (GPL-3.0 + wrong authority model).
smc-mcp               REJECT as a dependency (2 commits, 2 stars, MCP network server, non-causal).
smartmoneyconcepts    REJECT for signal authority (measured repaint). Also: remove the unused
                      pin from requirements.txt — it costs ~50 MB of numba/llvmlite for zero
                      executed code and prints a banner to stdout on import.
```

**LICENSE_FINDINGS**
```
COMMERCIAL_SAFE_PERMISSIVE : pandas-ta-classic (MIT), ccxt (MIT), smc-mcp (MIT),
                             smartmoneyconcepts (MIT per repo; PyPI metadata blank — caveat)
COMMERCIAL_REVIEW_REQUIRED : Freqtrade (GPL-3.0), NautilusTrader (LGPL-3.0-or-later),
                             Backtesting.py (AGPL-3.0) for any non-research use
REJECT_LICENSE             : vectorbt (Apache-2.0 + Commons Clause — NOT permissive),
                             Backtesting.py for product/runtime code
UNKNOWN                    : vectorbtpro (proprietary, not evaluated)
AG repo itself             : NO LICENSE FILE — private/all-rights-reserved. This is the
                             correct posture but it is what makes copyleft a HARD gate:
                             AG has no compatible outbound license to satisfy GPL/AGPL with.
```

**LOOKAHEAD_FINDINGS**
```
PASS  pandas-ta-classic: ema/atr(rma)/atr(sma)/stdev/bbands/true_range —
      0 mismatches over 34 truncation cuts, max drift 0.0 (bit-identical)
PASS  ATR parity vs AG wilder_atr: max abs diff 1.08e-18 over bars 60-249 (float64 ULP)
RISK  pandas-ta-classic offset=-2 verified to inject future values -> adapter MUST forbid offset
RISK  recursive warmup sensitivity: ATR(rma) drifts up to 9.5e-10 with history start —
      determinism/hash risk for a provenance platform -> pin warmup, declare precision

FAIL  smartmoneyconcepts 0.0.27, measured max settle lag in bars:
        swing_highs_lows  5   (+ last bar UNCONDITIONALLY relabelled every call)
        bos_choch CHOCH   14
        fvg MitigatedIndex 26+ (unbounded — forward scan)
        ob                13
        liquidity         never settled within 25 bars
        retracements      14
        previous_high_low 0   <- the only causal export
      Root cause in source: `ohlc["high"].shift(-(swing_length // 2)).rolling(...)` —
      an explicit forward shift (centred window). Every other SMC function takes
      swing_highs_lows as an input and inherits the defect.
FAIL  smc-mcp find_swings: `highs[i + j]` forward read; loop stops at n - lookback,
      so the most recent `lookback` bars are structurally unlabelable.
N/A   Freqtrade / Nautilus / Backtesting.py / CCXT — not candidates for signal authority.
```

**SUPPLY_CHAIN_FINDINGS**
```
pandas-ta-classic 0.8.32  no install scripts; 418 KB wheel / 3.3 MB installed;
                          deps numpy+pandas (already AG deps);
                          yahoofinance+alphavantage modules ARE loaded at package import
                          (leaf imports do not avoid it) but open no socket and do not
                          require `requests`. Residual risk LOW. Fast version churn
                          (0.3.14b1 -> 0.8.32 in 14 months) -> PIN EXACTLY + hash.
smartmoneyconcepts 0.0.27 declared in requirements.txt, imported by ZERO .py files;
                          pulls numba + llvmlite (~50 MB JIT) for no executed code;
                          prints an ANSI banner to stdout on import (artifact/stdout
                          contamination risk). ACTION: remove from requirements.txt or
                          move to a [research] extra.
smc-mcp                   an MCP network server with 2 commits. Never install.
ccxt (future)             MIT but heavy pinned deps (cryptography, aiohttp, coincurve,
                          uvloop) — review before any runtime adoption.
All adopted packages      BROKER_ACCESS=NONE  EXECUTION_AUTHORITY=NONE  PROPOSAL_AUTHORITY=NONE
                          enforced structurally: nothing above MarketState imports an OSS
                          trading package.
```

**BUILD_VS_BUY_MATRIX** — see Phase 5.
`ADOPT 3 · ADOPT-deferred 1 · WRAP 1 · REFERENCE_ONLY 6 · REJECT 2 ·
EXISTING_AG_REUSE 9 · BUILD 1`

**UNNECESSARY_CUSTOM_BUILD** (findings against the current tree, `4bbba31`)
```
1. research_external/semantic/wilder_atr.py — NOT unnecessary as an oracle, but it is
   the ONLY indicator AG owns, and it lives in the research tier with a list-of-dicts
   API. Reclassify: keep as the golden parity oracle; route production ATR through the
   pandas-ta-classic adapter (bit-parity proven).
2. requirements.txt pins smartmoneyconcepts==0.0.27 with zero importers — an unnecessary
   ~50 MB dependency and an unnecessary supply-chain surface.
3. research_external/adapters/backtesting_py.py imports AGPL-3.0 code. Not "unnecessary
   custom build" — the opposite, a reuse that is now a license liability. Contain, then
   replace with an ~80 LoC AG OHLC first-touch SL/TP resolver.
No other unnecessary custom build was found in the audited tree. AG's existing
funnel/eligibility/replay/performance/session modules are all justified: each is either
authority-critical or has no causally-acceptable, license-acceptable OSS substitute.
```

**CLAUDE_VERTICAL_SLICE_AUDIT**
```
NOT_YET_APPLICABLE — no TradeTicket vertical-slice diff exists at 4bbba31.
Phase 7 criteria are pre-registered above and will be applied to the diff verbatim.
Pre-registered JUSTIFIED_NEW_BUILD allowance: (a) the TradeTicket contract,
(b) the ag_indicators adapter, (c) a causal SMC module ONLY if the slice needs it,
(d) an OHLC first-touch SL/TP resolver. Everything else is presumed reusable.
```

**RECOMMENDED_TARGET_ARCHITECTURE** — see Phase 6.
OSS commodity numerics → thin AG adapter → AG MarketState → AG Opportunity →
AG qualification → AG ProposalEligibility → **AG TradeTicket (new)** → AG owner
authorization → AG broker adapter. AG-owned: authority, risk policy, provenance,
eligibility, TradeTicket governance, owner confirmation, execution boundary, and
— on this audit's evidence — **causal SMC semantics**.

**FX_RECOMMENDATION**
```
Stay on the current FX/MT5 architecture. Do NOT migrate to Freqtrade or Nautilus:
both are license-blocked, both would own the decision loop AG must own, and AG's
replay is already parity-tested against a frozen golden fixture, so migration means
re-proving every signed artifact — demonstrably longer, not shorter.

Adopt pandas-ta-classic behind ag_indicators for EMA/ATR/volatility. Keep
wilder_atr.py as the CI parity oracle. Add the TradeTicket contract to
packages/contracts/v1.py, reusing the existing Contract base and hashing.
Build causal SMC features AG-side only when a strategy actually needs them.
Keep AGPL strictly inside research_external/ and schedule its replacement.
```

**CRYPTO_FUTURE_RECOMMENDATION**
```
Phase 1 (lowest cost): VT Markets crypto over the EXISTING MT5 path. Crypto becomes
  a symbol-class problem (contract size, tick, funding, 24x7 sessions), not an
  architecture problem. Zero new execution boundary.
Phase 2 (when research widens beyond Bybit): adopt CCXT (MIT) for crypto MARKET DATA
  behind the same adapter membrane; retire the bespoke bybit_linear_perp_feed.
Phase 3: CCXT execution — a SEPARATE, explicitly owner-authorized gate. Not now.
Never: Freqtrade (GPL-3.0 + wrong authority model).
Watch item: 24x7 markets remove the session anchor ER_ONLY_V2 depends on; causal-SMC
  work transfers, session work does not.
NOT IMPLEMENTED IN THIS MISSION.
```

**BLOCKERS**
```
B1  LICENSE (HIGH) — AGPL-3.0 Backtesting.py is already imported by
    research_external/adapters/backtesting_py.py while AG runs a FastAPI network
    service. Today it is confined to offline research; one import away from an
    AGPL 13 disclosure obligation. OWNER DECISION REQUIRED: (a) accept and
    formally fence research_external/ with an import guard + CI check, or
    (b) fund the ~80 LoC AG first-touch SL/TP resolver and drop the dependency.
    Recommendation: (b), with (a) as the interim control.
B2  LICENSE (MEDIUM) — AG has no LICENSE file / license metadata. Record the
    all-rights-reserved posture explicitly so the copyleft gate is documented,
    not merely implicit.
B3  SEMANTICS (MEDIUM) — no causally-clean OSS SMC exists. If the vertical slice
    needs BOS/CHoCH/FVG, AG must write them with an explicit
    "confirmed at T+N" contract. This audit denies signal authority to every OSS
    SMC option; it does not block the slice, which needs none of them.
B4  DETERMINISM (MEDIUM) — recursive-indicator warmup sensitivity (up to 9.5e-10)
    will perturb contract hashes unless warmup length and output precision are
    pinned in the strategy contract. Must be settled inside the adapter, before
    first use.
B5  HYGIENE (LOW) — unused smartmoneyconcepts pin (+numba/llvmlite, +stdout
    banner) in requirements.txt.
B6  SCOPE (INFO) — Phase 7 cannot complete until Claude produces the diff.
```

**NEXT_SMALLEST_MISSION**
```
AG_TRADETICKET_CONTRACT_AND_INDICATOR_ADAPTER_V1  (single, small, reversible)

Exactly two new artifacts, nothing else:

 1. packages/contracts/v1.py :: TradeTicket
      - subclass the EXISTING Contract base; reuse _freeze/_timestamp/_identifier
        and the existing semantic-hash mechanism — do NOT introduce a second scheme
      - carries: proposal_id linkage, eligibility_decision_id, symbol, direction,
        entry/stop/target, risk reference, owner_confirmation state, provenance
      - a pre-authorization GOVERNANCE record, explicitly NOT a broker order
      - no broker fields, no order ids, no execution authority
 2. src/ag_indicators/__init__.py  (thin adapter, ~30-60 LoC)
      - re-exports ema / atr / stdev / true_range from pandas-ta-classic
      - offset forbidden; warmup_bars required and recorded; precision declared
      - the ONLY module in AG permitted to import pandas_ta_classic

Proof required (all small, all focused):
 a. a round-trip + immutability + hash-stability test for TradeTicket, matching the
    style of tests/test_edge_ai_contracts_v1.py
 b. a CI parity test: ag_indicators.atr  ==  research_external/semantic/wilder_atr
    (tolerance 1e-15) — the upgrade gate for pandas-ta-classic
 c. a truncation causality test for every ag_indicators export, reusing this
    audit's Phase-3 protocol
 d. pin pandas-ta-classic==0.8.32 in requirements.txt; remove the unused
    smartmoneyconcepts pin (or move it to a [research] extra)

Explicitly OUT of scope: SMC features, fill simulation, owner-review UI changes,
any broker path, crypto, and any change to eligibility, risk, or execution authority.
```

---

### Appendix — reproducing the causality evidence

```bash
python3 -m venv /tmp/ossaudit
/tmp/ossaudit/bin/pip install pandas numpy smartmoneyconcepts pandas-ta-classic
/tmp/ossaudit/bin/python causality.py   # truncation mismatch counts
/tmp/ossaudit/bin/python settle.py      # per-bar settle lags + indicator causality
/tmp/ossaudit/bin/python parity.py      # AG wilder_atr vs pandas-ta-classic rma,
                                        # warmup sensitivity, negative-offset probe
```

Environment used: `pandas 3.0.6`, `numpy 2.4.6`, `numba 0.67.0`,
`pandas-ta-classic 0.8.32`, `smartmoneyconcepts 0.0.27`, Python 3.11.
Synthetic GBM OHLCV, `default_rng(3/7/11)`, 250–400 bars, M5 UTC index.
The Phase-3 protocol is worth promoting into AG's CI as a reusable gate for any
future feature module, OSS or AG-written.

**This document authorizes nothing.** It classifies reuse. Strategy, proposal,
demo, and live authority remain exactly where `AGENTS.md`, `strategies/registry.yaml`
and `config/trading.yaml` place them.
