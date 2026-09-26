# Strategy Core boundary shell

Future deterministic strategy evaluation consumes `packages.contracts` facts and emits
opportunity contracts. It must not import `apps.owner_edge`, broker adapters, MT5, risk
policy, or execution modules. No strategy implementation is migrated in P0–P2.
