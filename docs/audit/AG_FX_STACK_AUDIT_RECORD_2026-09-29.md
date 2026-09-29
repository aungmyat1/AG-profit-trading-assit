# AG FX Stack — Independent Audit Record (2026-09-29)

Governance record only. It stores already-completed independent audit results in repo
truth **before** any integration, so no merge commit is the only proof that its code
passed audit. Recording an audit grants no strategy, proposal, Demo, or live authority.

The five reports in `docs/audit/` listed below are **byte-exact copies** of the auditor
commits (blob hashes verified equal). The auditor branches remain the primary source.

| Record | Verdict (verbatim) | Audited SHA | Auditor report commit | Report blob |
|---|---|---|---|---|
| TradeTicket vertical slice R1 re-audit | `TRADETICKET_VERTICAL_SLICE_AUDIT_PASS` | `1564769ac3bd43a3b5aceaa37aa85cc662906e95` | `2bf8d90c2be540850f2d99705aea3c0507959132` | `2223c12b3f6d8acaa44bc1af5d48efbe0e7fdd7a` |
| WP-7A canonical instrument registry V1 | `CANONICAL_INSTRUMENT_REGISTRY_V1_AUDIT_PASS` | `9b185e7986e49b960d5b0af686834943723ca0e5` | `8e12a87178ca1deefda2125162c70dced6d47308` | `4207d0cbe08ad0a99b30f613ddd8db8978d20e61` |
| WP-7A R1 path-determinism re-audit | `WP7A_R1_REAUDIT_PASS_WITH_NONBLOCKING_FINDING` | `471b1c026a04edc8ea34f61b0e6b2fce91c67000` | `59c86b481ee47d7512dd6b358d572136a32e2648` | `df16c5ba8cab426e0068eec2a92eb329ce49b708` |
| WP-7B identity-gated live Opportunity | `WP7B_IDENTITY_GATED_LIVE_OPPORTUNITY_AUDIT_PASS_WITH_NONBLOCKING_FINDINGS` | `4b450ff36d9dc0940b0940613426d6e85e7c4450` | `18d36cc670db0712cdbe976ea730165682d20464` | `d1e89278d15fdd93f3f32e1d62857684e97bc12f` |
| A8 FX Opportunity Platform V2 freeze audit | `FX_OPPORTUNITY_PLATFORM_V2_AUDIT_PASS_WITH_CAVEATS` | `6fdc921a` (candidate) | `8af69ec599b73624802ec7b5e0d6b676ff5e6b82` | `7ca9d73c5d288c4f30c3dcc21c7ec540d3f165c0` |

Auditor branches: `origin/arena/01a0ebe9-ag-profit-trading-assit` (first four),
`origin/arena/01a0e8f7-ag-profit-trading-assit` (A8). The A8 report was published at
`runs/VT_A8_AUDIT/AG_FX_OPPORTUNITY_PLATFORM_V2_FREEZE_AUDIT.md` and is copied here to
`docs/audit/AG_FX_OPPORTUNITY_PLATFORM_V2_FREEZE_AUDIT.md`.

## Unit → audit coverage

Integration units (linear lineage, each an ancestor of the next):

| Unit | Boundary SHA | Independent audit covering this exact boundary |
|---|---|---|
| A | `3474b13` | A8 — covered as an ancestor of audited candidate `6fdc921a` |
| E | `6c57430` | A8 — covered as an ancestor of `6fdc921a` |
| B | `1e26533` | A8 — covered as an ancestor of `6fdc921a` |
| F | `76348c7` | **NONE.** A8 explicitly excluded Collector V2 `76348c72` ("unfetchable") |
| C | `1564769` | TradeTicket R1 re-audit (PASS) |
| D | `471b1c0` | WP-7A audit (`9b185e7`) + WP-7A R1 re-audit (PASS, nonblocking finding) |
| G | `4b450ff` | WP-7B audit (PASS, 3 nonblocking findings) |

Unit G = WP-7B identity-gated live Opportunity integration. Exact lineage
`471b1c0 → 5fc8d1f → 4b450ff` (base / code / evidence tip): `5fc8d1f` adds
`src/instrument_registry/fx_gated_scan.py`, `tests/test_fx_identity_gated_scan.py` and
live wiring in `scripts/run_fx_opportunity_once.py`; `4b450ff` adds the live read-only
evidence artifact and status docs. G contains no strategy, TradeTicket, registry-version,
execution, or scheduler change.

## Carried findings and caveats (non-blocking, not remediated here)

- **A8 caveat 3 — branch commingling:** A8 requires a *bounded PR*, not a wholesale merge,
  for the audited platform range. Integration of A/E/B must honor this.
- **A8 caveat 1:** `ST_ASIAN_SWEEP_5R_V1` `instruments:` still lists USDJPY; NO_COMPATIBLE
  holds only because pilot universes are `[EURUSD, GBPUSD]`.
- **A8 caveat 4:** VT capture `ZERO_SPREAD = OBSERVED_UNEXPLAINED`.
- **WP-7A R1:** residual import-cwd limitation (confirmed non-blocking).
- **WP-7B 1:** `test_live_runner_starts_safely_from_a_foreign_cwd` needs MetaTrader5; not a
  reliable CI gate.
- **WP-7B 2:** `scripts/capture_vt_spread_evidence.py` still calls `check_broker_spec`.
- **WP-7B 3:** evidence filename drift (`AG_` prefix in status doc vs committed file).

## Gaps that block integration

1. **Unit F (`76348c7`) has no independent audit.** Required before merging F, and thus
   before C, D, G, since each is a descendant of F.
2. The main-protection tripwire (Phase-4 precondition) is not yet on main.
