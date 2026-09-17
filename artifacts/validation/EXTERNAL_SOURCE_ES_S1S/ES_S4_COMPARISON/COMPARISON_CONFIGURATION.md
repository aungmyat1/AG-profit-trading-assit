# ES-S4 Comparison Configuration

**Population A:** `ES_S3_BLIND_GENERATED` — 66 occurrences from commit `24f30326031d275cafe322beafc70e3de2e8804d`, blind replay fingerprint `sha256:becb429ffa0b9f10be84a6b8cf6aa6f792c547ec609c9ed4a2f124243ce91f40`. Not modified.

**Population B:** `EXTERNAL_SOURCE_REFERENCE_18` — 18 rows from the source chat's benchmark table (`reference_table.json`). Not modified.

## P3 — Comparison-only normalizations applied (non-semantic)

1. **Timezone conversion:** reference `broker_time` (Eightcap MT5, GMT+2 winter/GMT+3 summer per source claim) converted to UTC by subtracting 3 hours, for comparison purposes only. Neither the reference table's original values nor the blind replay's UTC timestamps were altered on either side.
2. **Decimal precision:** pip differences rounded to 2 decimals for readability only; underlying float comparisons used full precision.
3. **Field-name mapping:** reference `SL Pips/Price` → compared against blind `initial_stop`; reference `TP Target (5R)` → compared against blind `tp2_5r`; reference `Direction` (`Long`/`Short`) → mapped case-insensitively to blind `LONG`/`SHORT`.
4. **Matching tolerance:** a same-date, same-direction blind occurrence was considered a matching *candidate* regardless of time delta; classification into `EXACT_EVENT_MATCH` (≤30 min AND <2 pips entry diff) / `PROBABLE_EVENT_MATCH` (≤90 min) / `AMBIGUOUS_EVENT_MAPPING` (>90 min) used only for reporting, not to alter either population's data.

No entry logic, signal window, SL, TP, or outcome was altered by any of the above.

## Matching hierarchy applied (P4)

1. Date (UTC, post-normalization)
2. Direction
3. Nearest sweep timestamp (UTC, post-normalization)

No forced same-day match was made — see `mapping_ledger.json` for every `REFERENCE_ONLY_NO_BLIND_MATCH` case and its stated reason.
