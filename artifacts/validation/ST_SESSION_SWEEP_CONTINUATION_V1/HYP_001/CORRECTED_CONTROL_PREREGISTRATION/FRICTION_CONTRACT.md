# Friction Contract (canonical, resolved from the existing v1.0.1 strategy config — no new assumption introduced)

Source: `strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml:105-118` (byte-identical to v1.0.0; `friction_logic_change=false` per `V1_0_1_REMEDIATION_MANIFEST.json`), computed via `src/session_sweep_continuation/friction.py::estimate_friction`.

| Component | EURUSD | GBPUSD | Status |
|---|---|---|---|
| Spread | 1.0 pips | 1.4 pips | `APPROXIMATED` — documented research default, not broker-verified live quote (`cost_status=MODELED`, per `friction.py`'s own contract) |
| Commission | 0.2 pips | 0.2 pips | `APPROXIMATED` (`MODELED`) |
| Slippage | 0.3 pips | 0.4 pips | `APPROXIMATED` (`MODELED`) |

`minimum_stop_multiple: 3.0` (unchanged, gates stop acceptance, not an exit-cost component).

`cost_status` is stamped per-computation (`KNOWN`/`MODELED`/`UNAVAILABLE`) by the existing `friction.py` machinery — never silently assumed `KNOWN`/zero-cost. This is the repository's own existing canonical bounded-scenario method (a single `MODELED` scenario per symbol, not a two-sided low/high bound) — preserved exactly as-is, no new favorable assumption introduced.

```
CONTROL_FRICTION_FINGERPRINT = sha256(strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml `friction:` block, canonical byte range)
                              = c92311c3c1789a2ea01495a82a1fbcba1d877a8fb4d9ac46732f39e0b81970a9 (whole-file hash, since the friction block cannot be independently hashed without the rest of the file — recorded as the whole-file strategy_yaml_sha256, already cited in STRATEGY_IDENTITY_MANIFEST.md)
```
