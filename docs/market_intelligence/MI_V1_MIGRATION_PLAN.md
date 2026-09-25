# MI V1 migration plan

## Phase 1 — contract and adapters

Implement only the immutable snapshot types, serializers, quality states, and thin
adapters around the authorities in `MI_AUTHORITY_INVENTORY.json`. Add focused tests and
import guards. No strategy calls MI yet.

## Phase 2 — read-only builder

Build from a TD-8E event/context. Compose existing TopDownContext, session facts,
market structure, liquidity, regime, and volatility observations. Require explicit
feature versions and timeframe lineage. Fail closed on missing required evidence.

## Phase 3 — shadow consumers

Expose MI as an optional observation alongside current inputs. Run SSC, Large SMC, and
liquidity/sweep paths in shadow mode and compare provenance, timing, and component
semantics. Do not replace SSC inputs or alter strategy outputs.

## Phase 4 — authority review

Resolve the repository-wide EMA owner and cross-strategy regime contract. Review parity
fixtures, future-mutation tests, and quality semantics. Record a dated status artifact.

## Phase 5 — separately authorized migration

Only after review may a later mission propose consumer migration. Each strategy keeps
its current canonical behavior and receives an explicit compatibility adapter. No
parameter optimization, validation population change, Demo order, Live order, or
execution-authority change is part of Cycle 1.

Rollback is deletion of the optional MI read path; current strategy consumers remain
the authority throughout.
