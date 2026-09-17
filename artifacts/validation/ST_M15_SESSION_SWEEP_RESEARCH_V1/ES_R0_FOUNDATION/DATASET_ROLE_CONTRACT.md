# Dataset Role Contract (ES-R0 P9)

Required roles for the future economic validation chain:

| Role | Definition |
|---|---|
| `DEVELOPMENT` | Fresh M15 data, independent of the consumed Oct-2022 reconstruction evidence, used for initial hypothesis exploration (ES-R2+) |
| `REPLICATION` | Independent re-confirmation of any development finding on a second, non-overlapping window |
| `ROBUSTNESS` | Friction/neighborhood/regime stability checks (ES-R4) |
| `FINAL_HOLDOUT` | Sealed until all candidate selection and robustness work is frozen; accessed at most once (ES-R5) |
| `FORWARD_DEMO` | Live-forward observation only, post-holdout |

**No dataset may occupy conflicting roles.** No actual date window is selected in this mission — ES-R0 only defines the role architecture; window assignment requires a governed, uncontaminated inventory (a future mission), not decided here. Final holdout was not, and will not be, accessed in this mission.
