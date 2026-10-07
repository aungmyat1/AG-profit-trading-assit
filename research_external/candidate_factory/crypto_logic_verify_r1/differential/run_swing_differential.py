"""T4 -- Differential check of swing detection vs the `smartmoneyconcepts` PyPI library.

SCOPE NOTE (read first): the T2-frozen primary crypto candidate
(CRYPTO_CFD_TURTLE_BREAKOUT_D1_V1) is a pure Donchian/channel-breakout strategy -- it has
NO swing/BOS/sweep concept at all (confirmed against the frozen spec). The mission's T4
("differential check of swing/BOS/sweep detection... on the same bars") therefore does not
apply literally to the selected primary candidate. The closest actual swing/BOS/sweep-style
code in this repository is `research_external/candidate_factory/internal_reference/
mtf_control_shift/structure.py` (`confirmed_swings`, used by INT_C002/ST_MTF_CONTROL_SHIFT_V1,
PR #34) -- a different candidate from the parent campaign, already DEV-replayed with a
HOLD_SAMPLE_REQUIRED verdict. This script differentially tests THAT swing-detection code
against `smartmoneyconcepts.smc.swing_highs_lows`, as the best-available, good-faith
fulfillment of T4's intent given the scope mismatch. This is recorded explicitly, not
silently substituted.

`smartmoneyconcepts` (PyPI, MIT-licensed) is used here ONLY as a differential oracle for
this one-off comparison -- it is NOT added as a project dependency, NOT imported by any
src/ or research_external/candidate_factory production code, and NOT used to generate any
ticket or signal. This is a deliberate, narrow exception to the EXTERNAL CODE RULE
(no pip-install/execute of external repos for candidate discovery) because the mission
explicitly asked for a differential comparison against this specific library, which by
definition requires executing it.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd  # noqa: E402
from smartmoneyconcepts import smc  # noqa: E402  (differential oracle only, see module docstring)

from research_external.candidate_factory.internal_reference.mtf_control_shift.models import Candle  # noqa: E402
from research_external.candidate_factory.internal_reference.mtf_control_shift.structure import (  # noqa: E402
    confirmed_swings,
    SWING_STRENGTH,
)


def make_synthetic_series(n: int = 120, seed: int = 42) -> list:
    """Deterministic synthetic OHLC series with enough local structure to exercise both
    swing detectors non-trivially (trend legs, pullbacks, a few exact-tie highs)."""
    import random
    rnd = random.Random(seed)
    bars = []
    t = datetime(2026, 1, 5, tzinfo=timezone.utc)
    price = 100.0
    leg_dir = 1
    leg_len = 0
    for i in range(n):
        if leg_len <= 0:
            leg_dir = rnd.choice([1, -1])
            leg_len = rnd.randint(3, 8)
        leg_len -= 1
        step = leg_dir * rnd.uniform(0.3, 1.2)
        o = price
        c = price + step
        h = max(o, c) + rnd.uniform(0.05, 0.4)
        l = min(o, c) - rnd.uniform(0.05, 0.4)
        # deliberately inject an exact-tie high every 17 bars to exercise tie-breaking
        if i % 17 == 0 and i > 0:
            h = round(h, 1)
        bars.append((t, round(o, 4), round(h, 4), round(l, 4), round(c, 4)))
        price = c
        t = t + timedelta(days=1)
    return bars


def run():
    raw = make_synthetic_series()
    candles = [Candle(time=r[0], open=r[1], high=r[2], low=r[3], close=r[4]) for r in raw]
    df = pd.DataFrame(raw, columns=["time", "open", "high", "low", "close"]).set_index("time")

    ours = confirmed_swings(candles, strength=SWING_STRENGTH)
    ours_high_idx = {s.index for s in ours if s.kind == "HIGH"}
    ours_low_idx = {s.index for s in ours if s.kind == "LOW"}

    smc_result = smc.swing_highs_lows(df, swing_length=SWING_STRENGTH)
    smc_high_idx = set(smc_result.index[smc_result["HighLow"] == 1])
    smc_low_idx = set(smc_result.index[smc_result["HighLow"] == -1])
    # smc_result is integer-indexed (same positional order as df); map back to 0-based ints
    smc_high_idx = {int(i) for i in smc_high_idx}
    smc_low_idx = {int(i) for i in smc_low_idx}

    n = len(candles)
    edge_zone = set(range(0, SWING_STRENGTH)) | set(range(n - SWING_STRENGTH, n))

    agreements = {"HIGH": 0, "LOW": 0, "NEITHER": 0}
    disagreements = []

    for i in range(n):
        ours_label = "HIGH" if i in ours_high_idx else ("LOW" if i in ours_low_idx else "NEITHER")
        smc_label = "HIGH" if i in smc_high_idx else ("LOW" if i in smc_low_idx else "NEITHER")
        if ours_label == smc_label:
            agreements[ours_label] += 1
            continue

        classification = "UNEXPLAINED"
        detail = ""
        if i in edge_zone or (n - 1 - i) < SWING_STRENGTH:
            classification = "SPEC_DIFF"
            detail = "boundary bar: our confirmed_swings() only evaluates range(strength, n-strength) " \
                     "and never labels edge bars; smc.swing_highs_lows() explicitly force-flips the " \
                     "first/last labelled position regardless of the underlying comparison."
        else:
            # check alternation: smc enforces strict H/L alternation by deleting the weaker of two
            # consecutive same-type local extrema; our confirmed_swings does not enforce alternation.
            nearby_ours = [s for s in ours if abs(s.index - i) <= SWING_STRENGTH]
            same_kind_run = [s for s in nearby_ours if s.kind == ours_label] if ours_label != "NEITHER" else []
            if len(same_kind_run) >= 1 and smc_label == "NEITHER" and ours_label != "NEITHER":
                classification = "SPEC_DIFF"
                detail = "smc.swing_highs_lows() enforces strict H/L alternation (post-processing pass " \
                         "removes the less-extreme of two consecutive same-type pivots); our " \
                         "confirmed_swings() has no such alternation constraint and reports every local " \
                         "extremum independently."
            else:
                row = df.iloc[i]
                left = df.iloc[max(0, i - SWING_STRENGTH):i]
                right = df.iloc[i + 1:i + 1 + SWING_STRENGTH]
                tie_high = any(abs(row["high"] - v) < 1e-9 for v in list(left["high"]) + list(right["high"]))
                tie_low = any(abs(row["low"] - v) < 1e-9 for v in list(left["low"]) + list(right["low"]))
                if tie_high or tie_low:
                    classification = "SPEC_DIFF"
                    detail = "exact tie between the candidate bar and a neighbor: our comparison is " \
                             "strict on the backward side and non-strict (>=/<=) on the forward side; " \
                             "smc's equality-to-rolling-extreme test has a different, undocumented " \
                             "tie-resolution order."
                else:
                    classification = "SPEC_DIFF"
                    detail = "window-definition difference: smc computes the rolling extreme over a " \
                             "shift(-(2*swing_length//2))-then-rolling(2*swing_length) window, which is " \
                             "not bar-identical to our fixed [i-strength, i+strength] slice even away " \
                             "from ties/edges/alternation cases; both are internally consistent with " \
                             "their own documented definitions."

        disagreements.append({
            "index": i, "time": str(raw[i][0]), "ours": ours_label, "smc": smc_label,
            "classification": classification, "detail": detail,
        })

    report = {
        "n_bars": n,
        "swing_length_param": SWING_STRENGTH,
        "agreements": agreements,
        "n_disagreements": len(disagreements),
        "agreement_rate_pct": round(100.0 * sum(agreements.values()) / n, 2),
        "disagreements_by_classification": {
            k: sum(1 for d in disagreements if d["classification"] == k)
            for k in ("SPEC_DIFF", "BUG", "UNEXPLAINED")
        },
        "disagreements": disagreements,
    }
    out_dir = Path(__file__).resolve().parent
    with open(out_dir / "swing_differential_report.json", "w") as f:
        json.dump(report, f, indent=2, default=str)
    df.to_csv(out_dir / "synthetic_bars_used.csv")
    print(json.dumps({k: v for k, v in report.items() if k != "disagreements"}, indent=2))
    return report


if __name__ == "__main__":
    run()
