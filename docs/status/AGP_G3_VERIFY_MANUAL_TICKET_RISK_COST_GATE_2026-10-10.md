---
class: evidence
state: DESIGN
owner_reviewed: null
review_by: null
---
# AGP-G3-VERIFY — manual-ticket risk/cost gate (G3), 2026-10-10

Focused verification of the FX/gold/crypto **manual-ticket** risk and cost gate
(`src/v1_tickets/manual_ticket.py`, `src/v1_tickets/logic_gate.py::l5_cost`,
`src/v1_tickets/guards.py`, carriers `config/owner_ticket.yaml` and
`config/v1_tickets/crypto_cfd_ticket_policy.yaml`), against Definition-of-Done gate **G3** in
`docs/PROJECT_OBJECTIVE.md` and owner decision **OD1009-D2** in
`docs/governance/OWNER_DECISION_REGISTER.md`.

No strategy rule, level, threshold value, session window, readiness flag, authorization flag,
schedule or broker state is changed by this mission. `strategies/` and `src/strategy_engine/` are
untouched. Two fail-open boundary defects and two fail-closed defects were found and fixed; the
owner's numbers (0.5 / 0.10 / 0.25) are unchanged.

## Authority read

| Source | What it fixes |
|---|---|
| `docs/PROJECT_OBJECTIVE.md` G3 | "Required risk and cost keys are present; missing-key and threshold tests prove the gates fail closed." Evidence artifact: owner ticket configuration plus focused test report. |
| OD1009-D2 (register, Resolved) | `risk_pct: 0.5`, `cost_warn_R: 0.10`, `cost_block_R: 0.25`; cost **at or above 0.25R blocks**; absent required risk/cost keys fail closed. |
| `config/owner_ticket.yaml` | FX/gold carrier. Its own header: no defaults, `config/trading.yaml risk.risk_per_trade_pct` is **NEVER** a fallback, block applies at `cost_in_R >= cost_block_R`, warn "when spread + commission **reaches** this many R". |
| `config/v1_tickets/crypto_cfd_ticket_policy.yaml` | Crypto-CFD carrier (AGP-C12-CRY): the same three values plus the D4 spread percentages. |

No limit, threshold or reason code that these sources do not contain was added.

## Test matrix (key × asset class × verdict)

Suite: `tests/test_g3_manual_ticket_risk_cost_gate.py` — **78 passed** (2026-10-10, Linux container,
Python 3.11.2, MT5 stubbed). Full suite with the new file: **1859 passed, 2 skipped, 0 failed**.
FX = recorded EURUSD (2026-06-23 SHORT, 5.1-pip stop) and recorded
GBPUSD (2026-10-06 LONG, 6.2-pip stop); gold = the same recorded EURUSD session price-scaled to a
$3.00 stop (synthetic gate math, see "Fixtures"); crypto = the frozen
`ST_CRYPTO_CFD_SWEEP_RETEST_V1@1.0.0` BTCUSD fixture (940-point stop).

| Key / condition | FX (EURUSD, GBPUSD) | Gold (XAUUSD) | Crypto CFD (BTCUSD) | Verdict proven |
|---|---|---|---|---|
| `risk_pct: 0.5` present | reaches `size_position` as 0.5 → 0.98 lots / $49.98 and 0.80 lots / $49.60 | 0.5 → 0.16 lots / $48.00 | 0.5 → 0.05 lots | PASS — carrier value reaches sizing |
| `risk_pct` absent | `TICKET_BLOCKED`, primary `RISK_CONFIG_MISSING`, lot `OWNER RISK % NOT SET`, sizing never called | same | `BLOCKED`, `RISK_POLICY_AMBIGUOUS`, `volume: null`, sizing never called | BLOCK |
| `cost_warn_R` absent | `TICKET_BLOCKED`, primary `RISK_CONFIG_MISSING`, ticket shows `WARN LEVEL NOT SET`, `L5_WARN` | same | `BLOCKED`, `RISK_POLICY_AMBIGUOUS`, no volume | BLOCK |
| `cost_block_R` absent | `TICKET_BLOCKED`, primary `RISK_CONFIG_MISSING`, ticket shows `RISK_CONFIG_MISSING` for the block level | same | `BLOCKED`, `RISK_POLICY_AMBIGUOUS`, no volume | BLOCK |
| all keys absent / 12 unusable carrier shapes (empty, `null`, `0`, `-0.5`, `'0.5'`, `true`, wrong shape, malformed YAML, …) | `TICKET_BLOCKED`, primary `RISK_CONFIG_MISSING`; no lot unless `risk_pct` itself is usable | same | `BLOCKED` | BLOCK — no default exists |
| required key absent from the owner mapping itself | canonical `RISK_CONFIG_MISSING`, not a `KeyError` | n/a (same builder) | n/a | BLOCK (was a crash — defect G3-D4) |
| cost 0.09R | no warning, no cost block (`warnings == []`) | no warning | no `COST_WARN` | silent below the warn level |
| **cost 0.10R (boundary)** | `L5_WARN` in `warnings`, `L5.cost_vs_warn_level = WARN`, **no** block reason | `L5_WARN`, no block reason (10% is inside the legacy 15% spread guard) | `COST_WARN`, no `COST_TOO_HIGH` | **WARN** (was silent — defects G3-D1/D3) |
| cost 0.11R / 0.20R | `L5_WARN`, no block | `L5_WARN`, no block | `COST_WARN` | WARN |
| cost 0.2467R / 0.2499R / 0.23R | `L5_WARN`, `COST_ABOVE_BLOCK_R` **absent** | absent | `COST_TOO_HIGH` absent | just below the block level stays unblocked |
| **cost 0.25R (boundary)** | `COST_ABOVE_BLOCK_R` present and **primary** (outranks `SPREAD_TOO_WIDE` / D6 in its tier) | same | `COST_TOO_HIGH` present | **BLOCK** |
| cost 0.25R reached as spread + commission (0.23R + 0.02R; 0.19R + 0.06R) | `COST_ABOVE_BLOCK_R` primary | same | `COST_TOO_HIGH` | BLOCK (was fail-open — defect G3-D2) |
| decimal-exact boundary that binary division puts 1 ulp low (0.69/3.00 + 0.02; 0.30/3.00; 102.3/1023; 216.20/940 + 0.02; 1.13/5.65 + 0.05) | blocks at 0.25R, warns at 0.10R | same | same | BLOCK / WARN (was fail-open — G3-D2/D3) |
| displayed `cost_in_R` vs the decision | a ticket displaying 0.25R is blocked; one displaying 0.24R is not | same | same | no display/decision split |
| `config/trading.yaml` present with a 7.5% sentinel account default and **no** owner carrier | `TICKET_BLOCKED`, primary `RISK_CONFIG_MISSING`, `risk_pct: null`, no `risk_amount`, sizing never called | n/a | n/a | BLOCK — no silent fallback |
| repo `config/trading.yaml` default really is 1.0 | sized lot 0.98 ≠ the 1.96 lots a 1.0% budget would give | 0.16 ≠ 0.33 | 0.05 ≠ 0.10 | the lots above are evidence, not coincidence |
| structural: no edge to the execution config | `manual_ticket`, `sizing_math.risk`, `logic_gate`, `guards`, `ready_authority` contain no `trading.yaml` read and no `execution` import | — | — | PASS |

Verdicts are read from the gate's own outputs (`block_reasons[]`, `warnings[]`, `risk`, `cost_in_R`),
not from the ticket state: production `config/v1_tickets/ready_authority.yaml` keeps
`ST_ASIAN_SWEEP_5R_V1` READY **OFF** (D6), so a fully conforming FX/gold ticket is `TICKET_BLOCKED`
with `READY_AUTHORITY_OFF_D6` whatever the cost gate says, and the crypto contract is not admitted
(OD1009-D3), so its ticket is `BLOCKED` with `LOGIC_STATUS_NOT_VERIFIED`. Both floors are asserted in
the suite rather than stubbed away.

## Defects found and fixed

All four were exposed by the tests above; each is a gate defect, not a policy change. With the three
source files reverted to base `5b67199`, the suite reports **19 failed, 59 passed**; with the fixes,
**78 passed**.

| ID | Defect (as found) | As-found evidence | Fix |
|---|---|---|---|
| **G3-D1** | The FX/gold warn boundary was **exclusive**: `l5_cost` passed when `cost_in_R == cost_warn_R` (`"cost_in_R <= owner_ticket.cost_warn_R"`), so a cost exactly at the owner's 0.10R raised no `L5_WARN`, while the crypto carrier warned at `>= 0.10`. One owner threshold gave two different verdicts per asset class, against the carrier's own wording ("warn when spread + commission **reaches** this many R"). | `assert ('L5_WARN' in []) is True` (EURUSD, GBPUSD, gold at 0.10R); `assert 'PASS' == 'WARN'` | `l5_cost` passes only while the cost is **below** the warn level, via the shared predicate; check rule text updated to `cost_in_R < owner_ticket.cost_warn_R`. Threshold value unchanged; L5 stays advisory and never blocks. |
| **G3-D2** | The **block** boundary failed open on decimal-exact costs: `cost_at_or_above_block` compared raw binary floats, so a cost whose exact decimal value **is** 0.25R could land 1 ulp below and not block — while the ticket displayed `cost_in_R 0.25`. Reachable with ordinary 2-decimal broker values (XAUUSD $0.69 spread on a $3.00 stop + 0.02R commission → `0.24999999999999997`; BTCUSD 216.20 on a 940-point stop + 0.02R). The block was then attributed only to the legacy spread guard. | `assert 'COST_ABOVE_BLOCK_R' in ['SPREAD_TOO_WIDE']` (gold ×2, and displayed-vs-decided); crypto `assert ['COST_WARN'] == []` | New shared `guards.cost_at_or_above(cost_r, threshold_r)` with a **relative** tolerance of `1e-9` — five orders of magnitude tighter than the 4-decimal `cost_in_R` the owner is shown, so no ticket-visible decision changes. `cost_at_or_above_block` delegates to it; the crypto block and warn comparisons use it. |
| **G3-D3** | The same float-noise fail-open at the **warn** boundary: `0.30/3.00`, `102.3/1023`, `0.21/2.10` all equal 0.10R in decimal and evaluate 1 ulp low, so no `COST_WARN` / `L5_WARN` was raised. | `test_decimal_boundary_cost_is_never_missed_by_float_noise` (5 cases), gold `AT_WARN` row | Same shared predicate (one boundary rule for FX, gold and crypto). |
| **G3-D4** | A required key **absent from the owner mapping** raised `KeyError` instead of ending in the canonical block reason (`manual_ticket.py:252` `owner["cost_warn_R"]`, `:147` `owner["risk_pct"]`). Not reachable from a config file today (`load_owner_config` always returns the full shape), but reachable from any caller supplying its own mapping — and a `KeyError` in a scheduled cycle is not a canonical terminal outcome. | 4 × `KeyError: 'cost_warn_R' / 'risk_pct'` | The three required keys are read with `.get()`; absent is treated exactly like present-and-unusable → `RISK_CONFIG_MISSING`, no sizing. |

Changed paths: `src/v1_tickets/guards.py` (+17), `src/v1_tickets/logic_gate.py` (+12/−3),
`src/v1_tickets/manual_ticket.py` (+33/−15 comments included), new
`tests/test_g3_manual_ticket_risk_cost_gate.py`. No config file changed: both carriers already held
the OD1009-D2 values.

## Recorded, deliberately not changed (no new policy)

- The FX/gold loader accepts `cost_warn_R >= cost_block_R`; the crypto loader rejects it
  (`warn >= block` → all three values `None`). OD1009-D2 states no ordering rule for the FX/gold
  carrier, so no validation was added. The asymmetry is recorded for the owner.
- The FX path does not validate a caller-supplied `commission_r` (a negative or non-finite value would
  lower `cost_in_R`); the crypto path already rejects both. No repo caller passes a commission to the
  FX path today (production passes `None`; MT5 `symbol_info` exposes no commission), so nothing was
  changed.
- `cost_in_R` is displayed rounded to 4 decimals while the decision uses the exact value, so a cost
  within 5e-5 R below the block level can display as `0.25` and correctly not block. Display
  granularity unchanged.

## Fixtures and their limits

- **FX**: recorded `tests/fixtures/manual_ticket/EURUSD_M15_recorded.csv` and
  `GBPUSD_M15_recorded.csv` (offline replay, `data_source="FIXTURE"`).
- **Gold**: the recorded EURUSD session ×2000, quoted to cents, with the sweep wick extended so the
  engine's own stop is exactly $3.00 (entry 2286.00 / SL 2289.00). This is **synthetic gate math**,
  not XAUUSD market evidence: it exists because the owner's thresholds are decimal values and a
  2-decimal $3.00 stop exercises them exactly. G2 (`symbol_info` evidence per traded broker symbol) is
  a separate gate and is not touched here. Symbol metadata for XAUUSD-VIP, GBPUSD-VIP, EURUSD-VIP and
  BTCUSD is read from the AGP-C1-HOST read-only capture
  (`status/evidence/host_symbol_info_2026-10-09.json`), never invented.
- **Crypto**: the frozen contract fixtures of `tests/test_crypto_cfd_strategy_contract_v1.py`
  (BTCUSD SHORT, entry 84180 / SL 85120).
- **L2** is stubbed to PASS in the FX/gold ticket-level cases only, because the real L2 fails on the
  frozen v1.1.1 contract/engine divergences (pinned by `tests/test_manual_ticket_build.py`) and
  `LOGIC_GATE_FAIL:L2` outranks every risk/cost reason. No rule, level or threshold is altered by the
  stub. L1/L3/L4/L5/L6 run for real.
- USDJPY has no recorded session fixture and no host capture in this repository, so it is not
  exercised; the gate is symbol-agnostic and the 2-decimal scale is covered by the gold case.

## NO_BROKER_MUTATION

`broker_mutations = 0`. The suite is offline and read-only: no terminal, no network, no order module.
Balance and symbol metadata are injected values, volume comes from the broker-free
`sizing_math.risk` boundary, and `tests/conftest.py` makes every real MT5 operation raise
`MT5StubOperationAttempted`, so a broker call anywhere in this path would fail loudly instead of
passing. Every ticket asserted here keeps `order_ready: false`, `broker_authorized: false`,
`edge_verified: false`, `orders_sent_by_system: 0`, `execution_authorized: false`, the
`MANUAL — no automatic order` authority text and a `NOT A BROKER ORDER` label
(`test_risk_cost_gate_stays_read_only`). No demo/live flag, readiness value, registry entry or host
task was read for mutation or changed.

## G3 verdict

**G3 = PASS** for the manual-ticket risk/cost gate (FX + gold + crypto-CFD carriers), evidenced by
`config/owner_ticket.yaml` + `config/v1_tickets/crypto_cfd_ticket_policy.yaml` and this report with
`tests/test_g3_manual_ticket_risk_cost_gate.py` (78 passed).

What this does **not** imply:

- **G1 is not established here.** The frozen v1.1.1 L2 divergences are unchanged, and OD1009-D6 needs
  G1 **and** G3 before `ST_ASIAN_SWEEP_5R_V1` READY may be ON. `config/v1_tickets/ready_authority.yaml`
  stays `ready: OFF`; no READY authority was turned on.
- G2, G4, G5, G6 are untouched; no host acceptance, soak cycle or demo round trip is claimed.
- Crypto admission is unchanged (OD1009-D3): `ST_CRYPTO_CFD_SWEEP_RETEST_V1` is still not admitted and
  its ticket still blocks with `LOGIC_STATUS_NOT_VERIFIED`.
- `LOGIC_VERIFIED != EDGE_VERIFIED != DEMO_AUTHORIZED != LIVE_AUTHORIZED`. Every `demo_authorized`
  stays `false`; nothing here authorizes a demo or live order, and `EDGE_VERIFIED=FALSE` is unchanged.
- Unit-tested offline only: **not** live-verified and **not** host-verified.

## Tests

```
python -m pytest tests/test_g3_manual_ticket_risk_cost_gate.py -q          -> 78 passed
python -m pytest tests/test_manual_ticket_build.py tests/test_manual_ticket_logic_gate.py \
  tests/test_manual_ticket_authority.py tests/test_manual_ticket_report_and_boundary.py \
  tests/test_manual_ticket_scan_records.py tests/test_crypto_cfd_proposal_policy.py \
  tests/test_crypto_cfd_strategy_contract_v1.py \
  tests/test_asian_sweep_v1_1_2_logic_gate_both_cycles.py tests/test_asian_sweep_v1_1_2_l2_closure.py \
  tests/test_v1_tickets.py tests/test_d6_ready_authority.py \
  tests/test_d6_per_symbol_verification.py tests/test_d6_actionability_suppressed.py -q
                                                                            -> 311 passed
python -m pytest -q                                                       -> 1859 passed, 2 skipped
```

Environment: Linux cloud container (not the Windows MT5 host), Python 3.11.2, PyYAML 6.0.3,
pandas 2.3.3, numpy 2.2.6, smartmoneyconcepts 0.0.27, requests 2.34.2, fastapi 0.135.1, httpx 0.28.1,
pyarrow 25.0.1, cogapp, pytest 8.3.5, ruff 0.16.10 (clean on every changed file). MetaTrader5 is the
repository's collection-time stub; no terminal was connected. `cog` must be on PATH for
`tests/test_docs_live.py` (as in CI); without it that one docs test errors on a subprocess call, which
is an environment gap, not a regression — with it the run is 0 failed. Also run clean locally:
`scripts/check_docs_links.py` (0 broken links), `scripts/check_skill_mirror_drift.py` (no drift),
`scripts/docs/check_drift.py` (0 blocking errors).
Defect-detection control: with `src/v1_tickets/{guards,logic_gate,manual_ticket}.py` reverted to base
`5b67199`, the new suite reports **19 failed, 59 passed**.

## Base movement during the mission

`main` advanced from `5b67199` to `cd3d201` (PR #110) while this mission ran. It added the proposed
AGP-C6 successor objective and register row **OD1010-C6-RISK** (`APPROVED_LIMITS_ONLY`: 0.5% risk per
trade, position/trade/daily-loss ceilings for a future DEMO execution path). None of it changes this
mission's scope or authority: the **G3 row text is unchanged**, OD1009-D2 is unchanged, and OD1010-C6-RISK
grants no execution authorization and is not a manual-ticket carrier value — the numbers verified here stay
the ones OD1009-D2 and the two carriers contain. The base was merged into this branch (no force-push) and
the cog-generated `inputs_sha256` line in `PROJECT_STATUS.md` was refreshed, because the generated-file
policy gate requires an output this PR changes to be byte-exact FRESH. The other three generated outputs
are left to the post-merge regeneration PR per AG_REGEN_OUTCOME_V1 (their drift is pre-existing on `main`:
committed `pending_decisions: 14` vs 13 regenerated).

## OSS-FIRST

| COMPONENT | OSS_CANDIDATE | DECISION | REASON |
|---|---|---|---|
| Test runner / fixtures | `pytest` 8.3.5 (already pinned in `pyproject.toml` dev extras) | REUSED | Existing repo authority; no new dependency added. |
| Recorded session fixtures | repo `tests/fixtures/manual_ticket/*.csv` | REUSED | No external market data downloaded; no new egress. |
| Symbol metadata | repo AGP-C1-HOST capture (`status/evidence/host_symbol_info_2026-10-09.json`) | REUSED | VT Markets MT5 evidence, per the data-provenance rule; no invented values. |
| Decimal boundary arithmetic (test oracle) | Python stdlib `decimal` | REUSED | Independent exact-decimal oracle for the float-noise cases; no OSS package needed. |
| Position sizing / cost gate | none (repo `sizing_math.risk`, `v1_tickets.guards`) | REJECTED (external) | Sizing and thresholds are local authority; an OSS risk library could never supply the owner's values. |
