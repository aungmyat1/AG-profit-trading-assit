# Third-Party Strategy Dependencies

## smartmoneyconcepts

The project pins `smartmoneyconcepts==0.0.27`. Its output is used only behind project-owned adapters; callers consume normalized project types rather than raw library frames.

The three modules in the integration path are:

- `src/market_structure/smc_adapter.py` directly imports `smc` and calls `swing_highs_lows`, `bos_choch`, and `previous_high_low`. It computes swing points, confirmed BOS/CHOCH events, and previous-period high/low levels.
- `src/supply_demand/smc_adapter.py` directly imports `smc` and calls `swing_highs_lows`, `ob`, and `fvg`. It computes order-block and fair-value-gap candidates and their mitigation state.
- `src/market_structure/analyzer.py` is the public orchestration/caller path into the market-structure adapter. It does not directly import the third-party package.

There are two direct importers in the checked-in source, not three. The third module above is the adapter caller, included to make the complete integration path explicit.

## Upstream-change risk

An upstream release may change result columns, row/index alignment, swing bookend behavior, break confirmation indexes, or mitigation semantics. Such a change could alter market-structure timestamps or candidate-zone outputs without an obvious import or type error. The adapters validate required columns and normalize outputs, but those guards cannot establish semantic equivalence. Keep the exact version pin, review upstream changes before upgrading, and run the focused market-structure and supply/demand regression tests before changing it.
