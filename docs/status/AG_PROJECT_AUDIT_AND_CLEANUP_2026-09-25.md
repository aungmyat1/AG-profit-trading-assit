# AG Project Audit and Cleanup — 2026-09-25

Branch: `claude/stoic-feynman-4kczs6` (from `main` @ `8dea18e`, PR #2 merge).
Scope: repository health audit, root-level cleanup, and a prioritized restructure
recommendation. **No strategy, execution, risk, scheduler, broker, config, or
authorization behavior changed.** Documentation/layout only; this record authorizes
nothing.

## 1. Current position (from existing authorities, not re-derived)

| Item | State | Source |
|---|---|---|
| Roadmap gates R0–R4 | `READY` / `PASS` (2026-09-11) | `docs/PROJECT_ROADMAP.md` readiness matrix |
| R5–R6 economic edge | `NOT_PASS / NOT_ESTABLISHED` | same |
| R7–R9 Demo/Live | `BLOCKED` | same |
| V2 engineering | V2-2A, V2-2B verified; V2-3A/3B + Parity #1 pass; V2-3C, WP-2 planned | same |
| Latest merged work | PANEL R5A–R5C-R2 execution hardening (auth, durable idempotency, lifecycle, reconciliation) | `PROJECT_STATUS.md` top |
| `SAFE_TO_FREEZE_R5C` | `NO` — awaiting independent re-audit | `PROJECT_STATUS.md` |
| Strategy registry | Only `SESSION_TRADE_V1` is `demo_authorized` (ASIAN_LONDON); nothing `live_authorized` | `strategies/registry.yaml` |

Observation: the last ~20 commits (2026-09-22 → 09-24) are all execution/panel
hardening (R5A–R5C). The roadmap's critical path to value is R5/R6 **edge evidence**,
which no commit in that window advanced.

## 2. Running processes

This audit ran in a cloud Linux container, so it cannot see the owner's Windows
MT5 box, scheduler, or pilot processes. The committed `journal/` snapshot shows the
last FX daily report on 2026-09-04 and the last BTC daily report on 2026-09-19. Whether
the V1.0.2 pilot, the shadow-validation series, and `ag_scheduler_v2` are still running
has to be checked on the owner machine (`scripts/validate_readiness.ps1`, scheduler
checkpoint `journal/ag_scheduler_v2/checkpoint.json`).

## 3. Test baseline (this environment)

Command: `python -m pytest -q -p no:cacheprovider` (default markers, `-m 'not slow'`),
Python 3.11.15, Linux, no MetaTrader5 package, full git history (`git fetch --unshallow`).

Result: **4050 passed, 48 failed, 48 skipped, 3 errors in ~35 s.** On a shallow clone,
5 more fail (history-diff tests cannot resolve old commits). The owner's last recorded Windows run
(`full_suite2.txt`, removed below) was 3662 passed / 4 failed in 34 min.

| Class | Count | Tests | Cause | Real defect? |
|---|---|---|---|---|
| A. MT5 reached from "offline" code | ~21 | `test_topdown_composer_replay` (7), `test_raw_prospective_archive_partitions` (5), `test_five_skill_runtime` (5), `test_historical_replay_no_lookahead::test_stage2_entry_only_reuses_historical_data_not_live_mt5`, `test_td6_*`, `test_td8e_*`, `test_ticket_delivery_fx_cycle_overlap`, `test_post_asian_pilot::test_end_report_data_error_day_*` | `liquidity/analyzer.py:45` calls `mt5.symbol_resolver.get_symbol_meta()` → live `mt5.symbol_info()` even under historical replay / stage2 | **Yes, for replay (see F1)** |
| B. CRLF-bound dataset hashes | 3 + 3 errors | `test_ssc_dev002_h1_metadata_manifest` (3), `test_ssc_one_year_warmup_convergence` (3 errors, also `D:\` path) | Evidence SHA-256 was computed on a Windows `core.autocrlf` checkout; repo blobs are LF | **Yes (see F2)** |
| C. Tests bound to mutable runtime state | 8 | `test_fx_occurrence_identity_promotion` (5), `test_proposal_occurrence_identity_v1` (3) | Read the live `state/proposal_ledger/proposal_ledger.json` (now 99 records, tests pin 69) | Test design defect |
| D. "Unchanged since commit X" scope tests | 7 | `test_large_smc_eurusd_*_wp2/wp3a/wp3a1`, `test_lsmc_frozen_core_scope` | Directory-scoped `git diff <sha>` now sees additive `large_smc_research/live_watch.py` + `watch_lifecycle.py` (9dec294) and later execution work | Test design defect — **no Large-SMC semantic change found** |
| E. Windows-only paths / MT5 import in subprocess | 6 | `test_market_data_readiness_scanner` (2, `D:\…` + `os.path.basename`), `test_m15_session_sweep_research_v1_parity` (`D:\ddev\…` cwd), `test_fx_session_daytrade_eurusd` (2, script imports `MetaTrader5` before argparse), `test_proposal_envelope_execution_boundary` | Platform assumptions | Portability only |
| F. Known pre-existing | 3 | `test_execution_mt5_gateway::test_order_check_failure_blocks_order_send`, `test_proposal_envelope_adapters::test_fx_repeated_same_setup_*` (proposal dedup), `test_validation_framework::test_btc_adapter_reconciles_*` | Already recorded in `PROJECT_STATUS.md` | Yes, already tracked |
| G. Docs index link | 1 → **fixed** | `test_docs_links::test_current_repository_documentation_is_integrity_clean` | `docs/README.md` linked `AG_SSC_V1_0_1_SEMANTIC_…`; file is `SSC_V1_0_1_SEMANTIC_…` | Fixed in this change |

## 4. Findings

**F1 — Historical replay is not hermetic (HIGH, research integrity).**
`historical_replay/stage2.py:156` and `mtf_context/topdown_composer.py:313` reach
`liquidity/analyzer.py:45` → `get_symbol_meta()` → live `mt5.symbol_info()`. On a
connected Windows box, replay silently uses **today's** broker tick size. On a
disconnected box, `SymbolMetaError` is swallowed and equal-high/low levels are skipped.
Either way, replay output depends on terminal state, not only on the dataset. That
contradicts the test named `test_stage2_entry_only_reuses_historical_data_not_live_mt5`.
The test passes on the Windows box only because the real terminal answers.
Recommended fix: inject symbol metadata (from `docs/svos/VD_BROKER_REALITY_AUTHORITY.json`
or the dataset's `symbol_metadata_manifest`) into the analyzer, and fail closed when it
is absent in replay mode. This changes replay behavior, so it needs its own mission and
evidence re-run.

**F2 — Dataset fingerprints depend on line endings (HIGH, reproducibility).**
`data/research/ssc_fresh_dev/SSC_V1_0_1_G2_DEV_002/raw/EURUSD_H1.csv`: LF bytes hash to
`9cb7c2da…`, and CRLF bytes hash to `93d27d8c…`, the value pinned in
`dataset_manifest.json` and the tests. Every hash-bound dataset is therefore valid only on
a Windows `autocrlf=true` checkout. No `.gitattributes` exists. Recommended fix, which
preserves the evidence: add `.gitattributes` with `data/** -text` and
`research_external/datasets/** -text`, then re-commit the affected CSVs **with the CRLF
bytes the manifests were computed on**, so the hashes match on every OS. Do this on the
owner's Windows box after verifying each manifest's hash locally. Do not re-hash
manifests, because that would rewrite evidence.

**F3 — Runtime state is committed despite `.gitignore` (MEDIUM, safety).**
`/journal/` is ignored, yet 27 `journal/` files are tracked. They include execution
`.claim` files and an execution `.jsonl`, which are idempotency state. `state/` (proposal
ledger, FX slot ledger) and `artifacts/diagnostics/` (3 files, also ignored) are
tracked too. **Do not simply `git rm --cached` these on a branch.** When the owner pulls,
git deletes the working-tree copies, which would erase live idempotency claims on the MT5
box. Safe procedure on the owner machine: back up `journal/` and `state/`, run
`git rm -r --cached journal state artifacts/diagnostics`, commit, pull elsewhere, and
restore the backup. Keep `journal/.gitkeep`.

**F4 — Tests coupled to mutable/one-shot facts (MEDIUM, velocity).**
Classes C and D fail as a normal result of the project advancing, not because of
regressions. Each false-red run costs a triage cycle. Recommendation: move ledger-based
assertions onto a frozen fixture copy under `tests/fixtures/`. Convert
"unchanged since `<sha>`" checks into content-hash pins of the specific frozen files, not
of whole directories. Alternatively, retire them to their dated evidence documents once
the mission closes.

**F5 — No automated CI (MEDIUM).** `.github/` holds only `copilot-instructions.md`; there is no `.github/workflows/`. The ~35 s Linux
run shown here would work as a free, per-PR regression gate once classes A–E are skipped
or fixed on non-Windows platforms. The 34-minute Windows run stays the release gate.

**F6 — Repository weight (LOW).** 79 MB working tree. The largest tracked files are ~44 MB
of M1 CSVs under `data/research/ssc_fresh_dev/`. Consider Git LFS, but only together
with F2, because LFS also stores exact bytes.

**F7 — Structure sprawl (LOW, already planned).** 61 flat packages under `src/`.
`docs/plans/AG_SRC_RESTRUCTURE_TRADE_ASSIST_RESEARCH_SPLIT_PLAN.md` (PROPOSED,
2026-09-14) is still the right target (`shared/`, `trade_assist/`, `research/`). Its
Phase 0 requires a green baseline, so it is **blocked on F1–F4**. Do not start it
before then.

## 5. Changes made in this record

Non-hidden root entries reduced from 37 to 18. All moves use `git mv`, so history is preserved:

| From (repo root) | To |
|---|---|
| `AG_MARKET_INTELLIGENCE_V1_{CYCLE1_DESIGN,CYCLE2..4_STATUS,FREEZE_STATUS}.md`, `MI_V1_{CONTRACT,INVARIANTS,MIGRATION_PLAN}.md`, `MI_AUTHORITY_INVENTORY.json`, `MI_V1_RELEASE_MANIFEST.json` | `docs/market_intelligence/` |
| `AG_V2_BASELINE_MANIFEST_V1.json` | `docs/v2/` |
| `AG_VALIDATION_SYSTEM_ASSURANCE_V1.md` | `docs/validation/` |
| `DEEPSEEK_REVIEW_PACKET.md`, `EXP_EXPOSURE_EFFICIENCY_V1_GEN_001.md` | `docs/status/` |
| `EXTERNAL_SOURCE_STRATEGY_SPEC_DRAFT.md` | `docs/specs/` |
| `PROJECT_IMPLEMENTATION_PLAN.md` | `docs/plans/` (relative links fixed) |
| `SSC_external_strategy_validation_files.zip` | `artifacts/validation/` |
| `full_suite2.txt` (stale test log), `package-lock.json` (empty; `web/` has its own) | removed |

The moved files' contents are unchanged, apart from relative links in
`PROJECT_IMPLEMENTATION_PLAN.md`. Inbound references were updated in `docs/README.md`,
`docs/v2/README.md`, `docs/v2/AG_V2_IMPLEMENTATION_ROADMAP.md`, and `PROJECT_STATUS.md`.
Dated `docs/status/*` records and machine-readable manifests keep their original
wording, because they are historical evidence. No code, test, config, or data file
references any moved path; a grep over `src tests scripts config web .agents .claude`
confirmed this.

Verification: `pytest -q tests/test_docs_links.py` → 4 passed. That test previously
failed. The full default suite afterwards: 4051–4052 passed, 46–47 failed, 3 errors
across two consecutive runs. This is the pre-change failure set minus the docs-link
fix. `test_ticket_delivery_fx_cycle_overlap` (class A list) passed in one run and failed
in the other with no code change, so it is **nondeterministic** and needs its own
root-cause fix. It must not be re-run until it passes.

## 6. Recommended order to reach the objective fastest

The roadmap's own principle applies: *engineering completion is not edge evidence.*

1. **Fix F2 (CRLF evidence binding)** on the Windows box. Small, and it unblocks portable
   reproduction of every dataset-bound result.
2. **Fix F1 (hermetic replay)** as its own mission, then re-run the affected replay
   evidence. Every R5/R6 number produced by replay depends on this.
3. **Apply F3** (untrack runtime state safely) and **F4** (de-couple tests), so the Linux
   suite is green except for `live_mt5`-marked tests.
4. **Add F5 CI** (Linux, `-m 'not slow and not live_mt5'`) as a PR gate.
5. **Close R5C** with the pending independent re-audit, then **pause further
   execution-panel work** (R5D+). R7 Demo execution stays `BLOCKED` until R5/R6 pass,
   so more execution hardening now does not shorten the path.
6. **Point engineering time at R5/R6**: complete outcome evidence and economic
   qualification (V2-13/V2-14) for `SESSION_TRADE_V1` and `ST_LARGE_SMC_V1`
   (FORWARD_RESEARCH) first.
7. Only after steps 1–4 are green: execute the `src/` split plan (F7) in its own
   worktree, per that plan.
