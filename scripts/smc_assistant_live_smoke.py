"""One-off, analysis-only live smoke check for the SMC assistant layer (market map,
surveillance, proposals, visual explanation) against real MT5 data. Not a pytest test
(no assertions about market content -- market state is not deterministic), and not
wired into any runtime loop; run manually to sanity-check the chain end to end. Prints
what it found; never places an order, never calls anything under src/execution/.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from daytrading_runtime.conditional_entry_snapshot import build_symbol_conditional_entry_analysis
from mt5.connection import connect
from proposals import explain, generate_proposals
from runtime_state.store import JsonKeyValueStore
from smc_map import build_smc_market_map
from surveillance import compact_line, detailed_report, update_surveillance
from visual_explanation import build_visual_explanation


def main(symbol: str = "EURUSD") -> None:
    connect()

    print(f"=== SMC market map: {symbol} ===")
    market_map = build_smc_market_map(symbol, timeframes=("H4", "H1", "M15"))
    print(f"data_quality={market_map.data_quality} warnings={market_map.warnings}")
    for tf, tf_map in market_map.timeframes.items():
        print(f"  {tf}: structure={'VALID' if tf_map.structure and tf_map.structure.status == 'VALID' else 'N/A'} "
              f"obs={len(tf_map.order_blocks)} fvgs={len(tf_map.fair_value_gaps)} "
              f"liquidity={len(tf_map.liquidity_levels)} evidence_ids={len(tf_map.evidence_index)}")
    if market_map.premium_discount is not None:
        print(f"  premium/discount ({market_map.premium_discount_source}): "
              f"{market_map.premium_discount.current_zone}")

    print(f"\n=== SMC_CONDITIONAL_ENTRY_V2 analysis: {symbol} ===")
    analysis = build_symbol_conditional_entry_analysis(symbol)
    print(f"data_quality={analysis.data_quality} warnings={analysis.warnings}")

    store = JsonKeyValueStore("journal/smc_surveillance_state.json")
    update = update_surveillance(analysis, store)
    print(f"\n=== Surveillance: {symbol} ===")
    print(compact_line(update.record))
    print(f"events this poll: {[e.event_type for e in update.events]}")
    print(detailed_report(update.record))

    proposals = generate_proposals(analysis)
    print(f"\n=== Proposals: {symbol} ===")
    if not proposals:
        print("NO ENTRY READY (a valid, non-failure result)")
    for p in proposals:
        print(explain(p))
        print()
        visual = build_visual_explanation(analysis, p.combination)
        print(f"visual annotations: {len(visual.annotations)}, reason_codes={visual.reason_codes}")
        for a in visual.annotations:
            print(f"  {a.type} {a.semantic_role} label={a.label!r} developing={a.developing}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "EURUSD")
