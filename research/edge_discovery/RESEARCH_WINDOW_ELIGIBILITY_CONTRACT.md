# Crypto-CFD Research Window Eligibility Contract R1

**Scope:** strategy-blind local evidence quarantine for immutable BTCUSD/ETHUSD
Crypto-CFD M5 exports. This contract does not change C001, friction, promotion, risk,
execution, timestamp authority, or the raw-data quality finding.

## Non-collapsible distinction

```text
RAW_DATA_QUALITY          = BLOCKED_UNKNOWN_GAPS
RESEARCH_WINDOW_ELIGIBILITY = independently proven per reference day/window
```

Unknown gaps are never called expected, filled, interpolated, sorted away, or removed
from provenance. A clean local interval can be eligible only if every required M5 source
bar is present and valid. A later C001/EdgeLab process must still preserve the raw
quality finding and use only the frozen manifest population.

## Reference-day rule

A date can serve as a reference day only when it has exactly 288 source M5 bars at
`[00:00, 24:00)` UTC, exact five-minute cadence, no duplicate timestamp, valid OHLC,
no source-marked synthetic/filled/interpolated bar, and no unknown gap dependency.

A partial source-edge date is `SOURCE_HISTORY_LIMIT`. An interior missing source bar is
an `UNKNOWN_GAP_REFERENCE_DAY`; it remains quarantined. The implementation records all
applicable typed reasons rather than selecting a favourable interpretation.

## Observation windows

`ResearchWindowEligibility.observation_window(start, end)` verifies the complete M5
sequence required by an explicitly supplied, UTC-aligned observation interval. Its
end-point is inclusive by default because it represents the last consumed closed M5 bar;
a caller can explicitly request half-open semantics. Missing interval bars return
`UNKNOWN_GAP_OBSERVATION_WINDOW`; source bounds return `SOURCE_HISTORY_LIMIT`.

`observation_day(date)` is a conservative, strategy-blind population helper. It requires
the whole current UTC day plus the preceding eligible reference day. It does not inspect
whether C001 would emit a signal.

## Stable typed taxonomy

`ELIGIBLE`, `SOURCE_HISTORY_LIMIT`, `INCOMPLETE_REFERENCE_DAY`,
`UNKNOWN_GAP_REFERENCE_DAY`, `UNKNOWN_GAP_OBSERVATION_WINDOW`,
`DUPLICATE_TIMESTAMP`, `INVALID_OHLC`, `NON_CONTIGUOUS_M5`, `INSUFFICIENT_DATA`, plus
`SYNTHETIC_OR_FILLED_BAR` and `RAW_HASH_MISMATCH` for explicit source exclusions.

## Reproducible quarantine artifacts

Each per-symbol canonical JSON manifest contains source dataset ID/SHA-256 and, for each
UTC date, bar count, first/last timestamp, gap dependency, reference-day decision, and
conservative observation-day decision. File bytes are canonical/hashable and an existing
manifest path cannot be overwritten with a different result.

`eligible_observation_m5()` exposes only original bars from manifest-eligible days as an
R2 `DerivedDataset` with an independent ID, parent ID, transform ID, and SHA-256. It is
therefore consumable by R2's existing chronological partition freezer without weakening
its provenance gate, raw quality gate, or holdout firewall. This R1 command deliberately
does **not** create a partition.

## Higher timeframes

Authoritative aggregation operates only on eligible original bars:

- M15: exactly 3 consecutive M5 bars;
- H1: exactly 12 consecutive M5 bars;
- D1: exactly 288 valid M5 bars in the UTC day.

An incomplete bucket is omitted. No synthetic OHLC, interpolation, or fill is produced.

## Local runner

```bash
python scripts/run_crypto_cfd_research_eligibility.py \
  --input-dir data/research/raw/crypto_cfd
```

It verifies the immutable SHA-256 values specified for this mission through the PR #32
export adapter, writes only eligibility manifests/reports, and exits before C001,
partitions, HOLDOUT access, profitability, or broker activity.
