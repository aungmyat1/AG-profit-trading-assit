# WP-7A R1 — PATH DETERMINISM BOUNDED RE-AUDIT

**Mission:** `WP7A_R1_PATH_DETERMINISM_BOUNDED_RE_AUDIT`
**Date:** 2026-09-29 · **Auditor branch:** `arena/01a0ebe9-ag-profit-trading-assit`
**Scope:** bounded to items R1.1–R1.8. The full 129-probe WP-7A audit was **not** redone —
R1 does not touch any previously audited semantics (see R1.1).
**Independent probes:** 24 auditor-written tests + out-of-process cwd matrices; removed
after use; worktrees verified pristine.

```
CLASSIFICATION = WP7A_R1_REAUDIT_PASS_WITH_NONBLOCKING_FINDING
```

The remediation is minimal, correct, and provably fixes the reported finding. The single
nonblocking finding is the residual import-cwd limitation, which I independently confirmed
is **pre-existing platform behaviour, not WP-7A**, and which **does not affect the planned
live runner**.

---

## R1.1 — Identity and containment

```
AUDITED_SHA   = 471b1c026a04edc8ea34f61b0e6b2fce91c67000   (matches expected)
TREE_HASH     = 138e6e61f298e88bf7abbe31c27d13bc205487be   (matches expected)
LINEAGE_VALID = YES
```

Single non-merge commit; direct parent `9b185e7986e49b960d5b0af686834943723ca0e5` (matches
expected). Frozen ticket `1564769a` is an ancestor. Not merged into `origin/main`.

Diff `9b185e79..471b1c02` — **4 files, +89 / −1**:

| File | Kind |
|---|---|
| `src/instrument_registry/identity.py` | **only production change** (+5/−1) |
| `tests/test_instrument_registry_v1.py` | tests (+27) |
| `tests/_cwd_envelope_probe.py` | new test helper |
| `docs/status/AG_WP7A_..._V1_STATUS.md` | docs |

**No unexpected production change.** Verified unchanged blobs: `gates.py`
(`b85bff19…`) and `config/instruments/registry/instruments-v1.0.0.yaml` (`fecb1b96…`).
No previously audited semantics are touched, so the bounded scope is justified.

## R1.2 — `PATH_RESOLUTION = PACKAGE_ANCHORED_ABSOLUTE`

The entire production change is one line:

```python
-REGISTRY_DIR = os.path.join("config", "instruments", "registry")
+REGISTRY_DIR = str(Path(__file__).resolve().parents[2] / "config" / "instruments" / "registry")
```

This is exactly the design the mission specified. `parents[2]` from
`src/instrument_registry/identity.py` resolves to the repository root. Verified by AST:

- anchored on `__file__` + `resolve()` + `parents` — **not** cwd;
- **no** `os.getcwd` / `os.chdir` anywhere in the module;
- **no** absolute machine path (no string constant starting `/home`, `/Users`, `C:\`, `/opt`, `/mnt`);
- **no** environment-specific fallback (`os.environ` / `getenv` absent);
- **no** arbitrary parent search (zero `while` loops; no `glob`/`rglob`);
- **no duplicate registry copy** — exactly one `instruments-v1.0.0.yaml` in the tree.

`registry_dir` remains an injectable parameter on `load_registry`, `resolve_identity` and
`resolve_many`, so tests can still point at fixtures without touching the default.

## R1.3 — `CWD_OPERATION_DETERMINISM = IDENTICAL_ACROSS_ALL_CWDS`

Out-of-process runs (imports at repo root, then `chdir` to the target before the
registry-dependent **operations**), across repo root, `scripts/`, `src/`, an unrelated temp
directory, and `/`:

| cwd | status | registry version | identity fp | metadata fp | envelope fp |
|---|---|---|---|---|---|
| repo root | RESOLVED | instruments-v1.0.0 | `6a781d60…` | `1455483d…` | `b631a6d0…` |
| `scripts/` | RESOLVED | instruments-v1.0.0 | `6a781d60…` | `1455483d…` | `b631a6d0…` |
| `src/` | RESOLVED | instruments-v1.0.0 | `6a781d60…` | `1455483d…` | `b631a6d0…` |
| `/tmp/elsewhere` | RESOLVED | instruments-v1.0.0 | `6a781d60…` | `1455483d…` | `b631a6d0…` |
| `/` | RESOLVED | instruments-v1.0.0 | `6a781d60…` | `1455483d…` | `b631a6d0…` |

**All four required values are byte-identical in every cwd**, and `REGISTRY_DIR` is
absolute. In-process `chdir` probes over `.`, `scripts`, `src`, `tests`, `config`, a tmp dir
and `/` agree.

The **envelope** column is the load-bearing one: `envelope_for_ticket` calls
`load_registry()` with the default directory, so this confirms nonblocking finding 3 from
the original audit is fixed transitively, without `gates.py` being modified.

## R1.4 — Baseline difference (the remediation is real)

Same probe, same inputs, against the **pre-remediation** commit `9b185e79`:

| cwd | `9b185e79` (baseline) | `471b1c02` (R1) |
|---|---|---|
| repo root | `RESOLVED`, all fingerprints present | `RESOLVED` (identical) |
| `/tmp/elsewhere` | **`UNKNOWN_REGISTRY_VERSION`**, all fingerprints `null`, envelope `null` | `RESOLVED` (identical) |

The finding reproduced exactly as reported, and R1 closes it.

**Worth recording honestly:** the baseline failure mode was **fail-closed**, not unsafe —
outside the repo root the old code simply could not find the registry and refused to
resolve. So the original defect was a *determinism and availability* problem, never a
route to a wrong identity. R1 converts "silently unavailable depending on cwd" into
"always correct".

## R1.5 — `REGISTRY_PIN_UNCHANGED = YES` · `REGISTRY_INTEGRITY = INTACT`

```
registry version : instruments-v1.0.0   (unchanged)
pinned fingerprint: 322468278a4208d3764c96df8e13fc201ed329b2eb61331c2f4aafa8ff05d1b2 (unchanged)
committed file    : recomputes to the same value  ✓
```

- In-place tampering (venue symbol, server, `enabled`, venue `environment` → `LIVE`) still raises `RegistryIntegrityError`.
- Unknown / unpinned versions (`instruments-v1.0.1`, `instruments-test-v1`, `""`, `v1`) still fail closed as `UNKNOWN_REGISTRY_VERSION`.
- **No cwd can select another registry.** I planted a decoy `config/instruments/registry/instruments-v1.0.0.yaml` (with `venue_symbol: EURUSD-VIP`) in the process cwd: it is **ignored**, resolution still returns the canonical `EURUSD`, and the loaded content fingerprint still equals the pin. This is the case that actually improved — under the old relative path such a decoy was precisely what could be picked up.

## R1.6 — `FROZEN_TRADETICKET_IDENTITY = BYTE_IDENTICAL`

```
src/trade_ticket  tree  cd4053727a1acb9b338d11d525087518ecb3a978
  1564769a (frozen) == 471b1c02 (R1)
```

The whole subtree object is unchanged, so no TradeTicket semantics can have changed.

## R1.7 — `RESIDUAL_IMPORT_CWD_LIMITATION = NONBLOCKING_PREEXISTING_PLATFORM_STARTUP_LIMITATION`

Claude's stated limitation is **confirmed, and correctly attributed**:

| Module imported | cwd = repo root | cwd = foreign |
|---|---|---|
| `instrument_registry.identity` | OK | **OK** (cwd-independent) |
| `instrument_registry.gates` | OK | `InstrumentConfigError` |
| `trade_ticket.ticket` (frozen, untouched) | OK | `InstrumentConfigError` |
| `fx_opportunity.instruments` | OK | `InstrumentConfigError` |

Root cause is `src/fx_opportunity/instruments.py:20`,
`INSTRUMENTS_PATH = "config/instruments/fx_opportunity_instruments.yaml"` — a cwd-relative
load at **import** time. `gates.py` only inherits it via the frozen `trade_ticket.ticket`.
I confirmed the identical failure at the **pre-WP-7A baseline**, so this is untouched
platform behaviour, not a WP-7A regression. It is also a **clear, fail-closed error**
(`InstrumentConfigError` naming the missing file), not a silent wrong result.

It is not unique to that module — the same cwd-relative pattern exists in
`fx_opportunity/runner.py`, `post_asian_pilot/pilot_config.py` and
`validation_framework/lifecycle_registry.py`. A platform-wide fix is a separate mission.

### `NEXT_RUNNER_IMPACT = NONE`

The mission's decisive question is whether the next planned runner invocation can start
safely from its intended working directory. **It can.** The live opportunity runner —
`scripts/run_fx_opportunity_once.py`, named in
`AG_FX_OPPORTUNITY_FOUNDATION_V1_STATUS.md` as "the live CLI" — establishes repo root from
`__file__` **before** importing the platform:

```python
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "src"))
os.chdir(_REPO)                       # line 30, precedes all fx_opportunity imports
```

Verified statically (AST: the `chdir` call precedes every `fx_opportunity` import) **and
empirically** — invoked from an unrelated directory, it starts and parses its arguments
normally. `scripts/replay_fx_opportunity.py` and `scripts/replay_outcomes_v2.py` use the
same convention.

**Caveat, reported rather than glossed:** `scripts/run_fx_cycle_once.py` and
`scripts/run_fx_daily_report.py` anchor `sys.path` from `__file__` but do **not** `chdir`,
so they would be exposed to this limitation. I could not settle their behaviour in this
checkout: both fail *identically from repo root and from a foreign cwd* with unrelated
`ModuleNotFoundError`s (`scheduling`, `post_asian_pilot.daily_fx_report` are absent from
this tree). cwd is therefore **not** the differentiator for them, and the evidence is
inconclusive. Since the planned integration target is the opportunity runner, this does not
change the classification — but if the wiring mission later extends to the cycle/daily
scheduler entrypoints, their anchoring should be checked first.

## R1.8 — `EXECUTION_CONTAINMENT = INTACT`

```
BROKER_ORDER_CHECK_REACHABILITY       = NOT_REACHABLE
BROKER_ORDER_SEND_REACHABILITY        = NOT_REACHABLE
POSITIONS_GET_REACHABILITY            = NOT_REACHABLE
OTHER_EXECUTION_MUTATION_REACHABILITY = NOT_REACHABLE
```

Static AST over `src/instrument_registry/`: no executable reference to `order_send`,
`order_check`, `positions_get`, `positions_total`, `symbol_select`, `order_calc_margin`,
`order_calc_profit`, `initialize`, `login`, `shutdown`, `account_info`. Runtime: with all
MT5 entry points replaced by recording stubs, four resolution paths × three working
directories (repo root, tmp, `/`) plus `gate_market_state` and `envelope_for_ticket`
produced **`calls == []`**. No broker connection was required or made at any point.

---

## Findings

```
BLOCKING_FINDINGS = NONE

NONBLOCKING_FINDINGS = 2
```

1. **Residual import-cwd limitation** (R1.7) — `instrument_registry.gates` cannot be imported from a non-repo-root cwd because the pre-existing `fx_opportunity.instruments` loads its contract from a cwd-relative path at import time. Pre-existing, fail-closed, platform-wide, **out of WP-7A's scope**, and not on the planned runner's path. Recommend a separate mission to anchor the platform's config paths the same way WP-7A R1 just did.
2. **Scheduler entrypoints unverified** (R1.7 caveat) — `run_fx_cycle_once.py` and `run_fx_daily_report.py` do not `chdir` to repo root; their behaviour under a foreign cwd is inconclusive in this checkout for unrelated reasons. Check before wiring anything beyond the opportunity runner.

Carried forward, unchanged, from the original WP-7A audit: no `verify_envelope()` helper,
and the registry content fingerprint covers parsed YAML rather than raw bytes.

## Tests

```
FOCUSED_TESTS     = 46 passed  (candidate tests/test_instrument_registry_v1.py; was 44, +2 cwd tests)
INDEPENDENT_TESTS = 24 passed  (auditor-written, R1.2/R1.3/R1.5/R1.6/R1.7/R1.8)
                    + out-of-process cwd matrices across 5 directories, and a
                      baseline-vs-R1 differential against 9b185e79
REGRESSION_TESTS  = 818 passed, 4 skipped, 1 failed
```

The single failure is the known pre-existing
`tests/test_crypto_opportunity_scanner.py::test_actual_api_route_is_read_only_candidate_projection`
(`ModuleNotFoundError: No module named 'api.app'`), reproduced in every prior audit.
**Not an R1 regression.** The suite grew 816 → 818 (+2), exactly the new tests.

---

## Verdict

```
CLASSIFICATION = WP7A_R1_REAUDIT_PASS_WITH_NONBLOCKING_FINDING

NEXT_STEP = WIRE_IDENTITY_GATE_INTO_LIVE_OPPORTUNITY_RUNNER_READ_ONLY
```

`NEXT_STEP` is the wiring step, **not** `FIX_PLATFORM_CONFIG_PATHS_BEFORE_WIRING`, because
the planned live runner already establishes repo root from `__file__` before importing —
verified statically and empirically. The residual limitation is real but sits outside both
WP-7A's scope and the runner's startup path.

When wiring begins, do it read-only, and confirm the entrypoint's `chdir(_REPO)` convention
still holds for whatever invokes the gate.

**Constraints honoured.** Candidate not modified, not merged, not cherry-picked; the
residual limitation was diagnosed but **not fixed**; bounded scope respected (no full
re-audit); audit worktrees verified clean and removed; no broker contact; wiring not
started.
This document authorizes nothing.
