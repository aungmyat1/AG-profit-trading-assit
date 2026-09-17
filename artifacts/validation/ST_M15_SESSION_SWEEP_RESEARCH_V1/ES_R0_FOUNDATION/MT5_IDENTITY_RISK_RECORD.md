# MT5 Identity Risk Record (ES-R0 P13)

```
MT5_MAGIC_NUMBER_COLLISION_RISK = OPEN
```

**Finding (ES-R0A, re-recorded here, not re-investigated):** `D:\ddev\Session Trade Codex` has a connected MT5 account with an open position and pending limit orders using magic number `777001`. AG's own `strategies/ST_ASIAN_SWEEP_5R_V1.yaml` declares the identical `magic_number: 777001`.

**Action taken in this mission:** none. The magic number was not changed, D:\'s orders were not inspected further, closed, cancelled, or assumed to be owned by AG.

**Requirement before any future Demo integration of `ST_M15_SESSION_SWEEP_RESEARCH_V1`:**
```
UNIQUE_MAGIC_ASSIGNMENT_REQUIRED = true
```
The eventual new research strategy must receive its own unique, AG-owned magic number before any execution authority can be considered — no exceptions, and this must be verified again at that time, not assumed resolved by this record.
