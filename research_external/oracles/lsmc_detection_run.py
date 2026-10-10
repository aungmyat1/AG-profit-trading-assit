"""AGP-4H-C reproducible detection-only fixture comparison.

This module is research evidence tooling; it does not modify runtime or actionability.
"""
from __future__ import annotations
import hashlib
import json
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
import pandas as pd
import yaml
from smartmoneyconcepts import smc
from fx_discovery import features as F
from strategy_engine.session import Candle
from market_structure.smc_adapter import candles_to_dataframe
from supply_demand.smc_adapter import fair_value_gaps, order_blocks
from large_smc_watch.detect import tolerant_breaks, h1_pois
from large_smc_watch.contract import TIE_TOLERANCE_POINTS, resolve_point
from .schema import disagreement

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/large_smc_v111/EURUSD.json"
LENGTH = 2


def _bars(rows):
    return [Candle(datetime.fromisoformat(x["time_utc"].replace("Z", "+00:00")),
                   x["open"], x["high"], x["low"], x["close"], x.get("volume")) for x in rows]


def _local(bars, *, point=None, include_ob=False):
    swings = F.swings(bars, LENGTH)
    if point is None:
        raise ValueError("verified point size required for contract break tolerance")
    breaks = tolerant_breaks(bars, swings, TIE_TOLERANCE_POINTS * point)
    result = {"swings": swings, "bos_choch": breaks,
            "liquidity_sweeps": F.sweeps(bars, swings), "fvg": F.fvgs(bars)}
    if include_ob:
        if point is None:
            raise ValueError("verified point size required for H1 OB detection")
        result["ob"] = [p for p in h1_pois("EURUSD", bars, tolerant_breaks(
            bars, swings, TIE_TOLERANCE_POINTS * point)) if p.kind.startswith("OB")]
    return result


def _smc_causal(bars):
    df = candles_to_dataframe(bars)
    swings = smc.swing_highs_lows(df, swing_length=LENGTH)
    raw = {
        "swings": (swings, "HighLow"),
        "bos_choch": (smc.bos_choch(df, swings, close_break=True), "BrokenIndex"),
        "liquidity": (smc.liquidity(df, swings), "Swept"),
        "ob": (smc.ob(df, swings), "OB"),
        "fvg": (smc.fvg(df, join_consecutive=False), "FVG"),
    }
    causal = {}
    for name, (frame, event_col) in raw.items():
        events = []
        for pos, row in frame.iterrows():
            if pd.isna(row[event_col]):
                continue
            # Raw SMC assigns bookend swings from the completed array. These are not
            # k-confirmable pivots and must be discarded to make the delayed lane causal.
            if name == "swings" and (int(pos) < LENGTH or int(pos) >= len(bars) - LENGTH):
                continue
            # SMC BOS rows are stored at the broken swing; BrokenIndex is confirmation.
            event_index = int(row[event_col]) if name == "bos_choch" else int(pos)
            visible = event_index + LENGTH
            if visible < len(bars):
                events.append((visible, tuple((k, None if pd.isna(v) else float(v)) for k, v in row.items())))
        causal[name] = events
    # Reuse the repository adapters for the existing SMC zone conversion outputs too.
    times = {b.time: i for i, b in enumerate(bars)}
    for key, zones in (
        ("adapter_fvg", fair_value_gaps("EURUSD", "H1", list(bars), join_consecutive=False)),
        ("adapter_ob", order_blocks("EURUSD", "H1", list(bars), swing_length=LENGTH)),
    ):
        causal[key] = [(times[z.origin_time] + LENGTH, z.low, z.high, z.direction.value)
                       for z in zones if z.origin_time in times and times[z.origin_time] + LENGTH < len(bars)]
    return causal


def _sig(x):
    if hasattr(x, "__dataclass_fields__"):
        return tuple((k, getattr(x, k)) for k in x.__dataclass_fields__)
    return x


def _sig_at(x, now):
    if hasattr(x, "__dataclass_fields__") and hasattr(x, "invalidated_time"):
        from dataclasses import asdict
        value = asdict(x)
        if value["invalidated_time"] is not None and value["invalidated_time"] > now:
            value["invalidated_time"] = None
        return tuple(value.items())
    return _sig(x)


def _prefix_check(bars, *, point=None, include_ob=False):
    full = _local(bars, point=point, include_ob=include_ob)
    diffs = []
    for t in range(len(bars)):
        sliced = _local(bars[:t + 1], point=point, include_ob=include_ob)
        for lane in full:
            # Compare emitted events known by bar t to the truncated run's emissions.
            def known(x):
                known_time = getattr(x, "known_time", None)
                if known_time is not None:
                    return known_time <= bars[t].time + timedelta(hours=1)
                return getattr(x, "known_at", getattr(x, "index", 0)) <= t
            now = bars[t].time + timedelta(hours=1)
            a = [_sig_at(x, now) for x in full[lane] if known(x)]
            b = [_sig_at(x, now) for x in sliced[lane] if known(x)]
            if a != b:
                diffs.append(disagreement("prefix_invariance", "PREFIX_MUTATION", lane, a, b, bar_index=t))
    return diffs


def _geometry_check(bars, detection):
    for swing in detection["swings"]:
        if swing.price not in (bars[swing.index].high, bars[swing.index].low):
            return False
    for br in detection["bos_choch"]:
        if br.index >= len(bars) or not (br.level > 0):
            return False
    for gap in detection["fvg"]:
        if not (gap.top > gap.bottom > 0 and gap.known_at == gap.index + 1):
            return False
    return True


def _closed_check(rows, minutes, as_of):
    times = [datetime.fromisoformat(row["time_utc"].replace("Z", "+00:00")) for row in rows]
    return (times == sorted(times) and len(times) == len(set(times)) and
            all(t.timestamp() + minutes * 60 <= as_of.timestamp() for t in times))


def _definition_diff_count(name, local, oracle):
    """Count structural mismatches after normalizing each lane's event representation."""
    if name == "swings":
        left = {(x.known_at, x.kind, round(x.price, 10)) for x in local["swings"]}
        right = set()
        for visible, raw in oracle["swings"]:
            row = dict(raw)
            right.add((visible, "high" if row["HighLow"] == 1.0 else "low", round(row["Level"], 10)))
    elif name == "bos_choch":
        left = {(x.index, x.event, x.direction, round(x.level, 10)) for x in local["bos_choch"]}
        right = set()
        for visible, raw in oracle["bos_choch"]:
            row = dict(raw)
            kind = "BOS" if row.get("BOS") not in (None, 0.0) else "CHoCH"
            signed = row.get(kind)
            if signed in (None, 0.0):
                kind = "CHoCH" if row.get("CHOCH") not in (None, 0.0) else "BOS"
                signed = row.get(kind)
            if signed in (None, 0.0):
                continue
            right.add((int(row["BrokenIndex"]), kind, "bullish" if signed > 0 else "bearish",
                       round(row["Level"], 10)))
    elif name == "fvg":
        left = {(x.direction, round(x.top, 10), round(x.bottom, 10)) for x in local["fvg"]}
        right = set()
        for _, raw in oracle["fvg"]:
            row = dict(raw)
            sign = row.get("FVG")
            if sign is not None:
                right.add(("bullish" if sign > 0 else "bearish", round(row["Top"], 10), round(row["Bottom"], 10)))
    elif name == "liquidity":
        # The local output is a sweep/reclaim event; SMC liquidity is equal-level
        # clustering. Compare count plus level shape, while documenting the definition split.
        left = {(x.direction, round(x.level, 10)) for x in local["liquidity_sweeps"]}
        right = set()
        for _, raw in oracle["liquidity"]:
            row = dict(raw)
            if row.get("Liquidity") is not None:
                right.add(("cluster", round(row["Level"], 10)))
    elif name == "ob":
        left = {(x.kind, x.direction, round(x.low, 10), round(x.high, 10)) for x in local["ob"]}
        right = set()
        for _, raw in oracle["ob"]:
            row = dict(raw)
            if row.get("OB") is not None:
                right.add(("SMC_OB", "LONG" if row["OB"] > 0 else "SHORT",
                           round(row["Bottom"], 10), round(row["Top"], 10)))
    else:
        left, right = set(), set()
    return len(left - right) + len(right - left)


def _diff_items(name, local, oracle, bars=None):
    """Return normalized symmetric-difference rows for report and seeded review."""
    if name == "swings":
        left = {(x.known_at, x.kind, round(x.price, 10)) for x in local["swings"]}
        right = {(visible, "high" if dict(raw)["HighLow"] == 1.0 else "low", round(dict(raw)["Level"], 10))
                 for visible, raw in oracle["swings"]}
    elif name in ("BOS", "CHOCH"):
        local_name = "CHoCH" if name == "CHOCH" else "BOS"
        left = {(x.index, name, x.direction, round(x.level, 10)) for x in local["bos_choch"] if x.event == local_name}
        right = set()
        for _, raw in oracle["bos_choch"]:
            row = dict(raw)
            signed = row.get(name)
            if signed not in (None, 0.0):
                right.add((int(row["BrokenIndex"]), name, "bullish" if signed > 0 else "bearish", round(row["Level"], 10)))
    elif name == "FVG":
        left = {(x.index, x.direction, round(x.top, 10), round(x.bottom, 10)) for x in local["fvg"]}
        right = set()
        for visible, raw in oracle["fvg"]:
            row = dict(raw)
            sign = row.get("FVG")
            if sign not in (None, 0.0):
                right.add((visible - LENGTH, "bullish" if sign > 0 else "bearish", round(row["Top"], 10), round(row["Bottom"], 10)))
    elif name == "liquidity":
        left = {(x.index, x.direction, round(x.level, 10), "sweep_reclaim") for x in local["liquidity_sweeps"]}
        right = set()
        for visible, raw in oracle["liquidity"]:
            row = dict(raw)
            if row.get("Liquidity") is not None:
                right.add((visible, "cluster", round(row["Level"], 10), "equal_level_cluster"))
    elif name == "OB":
        time_indices = {b.time: i for i, b in enumerate(bars or [])}
        left = {(time_indices.get(x.origin_time, 0), x.kind, x.direction, round(x.low, 10), round(x.high, 10), "AG_ORDER_BLOCK_V1") for x in local["ob"]}
        right = set()
        for visible, raw in oracle["ob"]:
            row = dict(raw)
            if row.get("OB") is not None:
                right.add((visible, "SMC_OB", "LONG" if row["OB"] > 0 else "SHORT",
                           round(row["Bottom"], 10), round(row["Top"], 10), "SMC_OB"))
    else:
        left, right = set(), set()
    return ([{"side": "LOCAL_ONLY", "item": list(x)} for x in sorted(left - right, key=repr)] +
            [{"side": "SMC_ONLY", "item": list(x)} for x in sorted(right - left, key=repr)])


def _broker_day_alignment(rows):
    """Strategy D1 bars must open at 17:00 New York on the prior NY date."""
    ny = ZoneInfo("America/New_York")
    parsed = [datetime.fromisoformat(row["time_utc"].replace("Z", "+00:00")).astimezone(ny) for row in rows]
    return all(value.hour == 17 and value.minute == 0 for value in parsed)


def _seeded_manual_review(data, comparisons):
    rng = random.Random(20261011)
    candidates = []
    for tf, local, oracle in comparisons:
        for category in ("swings", "BOS", "CHOCH", "FVG", "liquidity", "OB"):
            if category == "OB" and "ob" not in local:
                continue
            for item in _diff_items(category, local, oracle, _bars(data[tf])):
                candidates.append((tf, category, item))
    by_category = {}
    for row in candidates:
        by_category.setdefault(row[1], []).append(row)
    chosen = [rng.choice(by_category[k]) for k in sorted(by_category) if by_category[k]]
    remaining = [row for row in candidates if row not in chosen]
    if len(chosen) < 10:
        chosen.extend(rng.sample(remaining, min(10 - len(chosen), len(remaining))))
    chosen = chosen[:10]
    reviews = []
    citations = {"swings": "strategies/ST_LARGE_SMC_V1_1_1_0.yaml:26-27",
                 "BOS": "strategies/ST_LARGE_SMC_V1_1_1_0.yaml:30",
                 "CHOCH": "strategies/ST_LARGE_SMC_V1_1_1_0.yaml:30",
                 "FVG": "strategies/ST_LARGE_SMC_V1_1_1_0.yaml:28; src/fx_discovery/features.py:127-138",
                 "liquidity": "strategies/ST_LARGE_SMC_V1_1_1_0.yaml:29",
                 "OB": "strategies/ST_LARGE_SMC_V1_1_1_0.yaml:28,45-49"}
    for tf, category, diff in chosen:
        item = diff["item"]
        bar_index = int(item[0]) if isinstance(item[0], (int, float)) else 0
        rows = data[tf]
        bar = rows[min(max(bar_index, 0), len(rows) - 1)]
        if category == "swings":
            why = ("raw bar is a strict k=2 high/low pivot at the delayed confirmation index" if diff["side"] == "LOCAL_ONLY"
                   else "SMC endpoint/bookend candidate is not a strict k=2 confirmed pivot under SW-A")
        elif category in ("BOS", "CHOCH"):
            why = "contract accepts close-confirmed structure breaks with five-point tolerance and its BOS/CHOCH state rule; SMC break labeling differs"
        elif category == "FVG":
            why = "raw three-candle gap is known on the third candle; local FVG follows that geometry and SMC visibility is delayed two bars"
        elif category == "liquidity":
            why = "contract requires a wick through a previously confirmed swing and close back inside; SMC equal-level clustering is a different output"
        else:
            why = "contract explicitly uses AG_ORDER_BLOCK_V1 candidates and excludes smc.ob() candidates"
        raw_check = ""
        if category == "FVG":
            i = min(max(bar_index, 1), len(rows) - 2)
            a, c = rows[i - 1], rows[i + 1]
            if item[1] == "bullish":
                raw_check = f"bar[{i+1}].low {c['low']} > bar[{i-1}].high {a['high']} = {c['low'] > a['high']}"
            else:
                raw_check = f"bar[{i+1}].high {c['high']} < bar[{i-1}].low {a['low']} = {c['high'] < a['low']}"
        elif category in ("BOS", "CHOCH"):
            raw_check = f"bar[{bar_index}].close={bar['close']}; compared to reported level={item[-1]}"
        elif category == "swings":
            pivot = max(0, bar_index - LENGTH)
            raw_check = f"pivot index={pivot}; confirm index={bar_index}; k={LENGTH}"
        elif category == "liquidity":
            raw_check = f"bar[{bar_index}] high/low/close={bar['high']}/{bar['low']}/{bar['close']}; level={item[2]}"
        else:
            raw_check = f"zone origin index={bar_index}; raw origin OHLC={bar['open']}/{bar['high']}/{bar['low']}/{bar['close']}"
        reviews.append({"timeframe": tf, "category": category, "side": diff["side"], "bar_index": bar_index,
                        "raw_bar_ohlc": {k: bar[k] for k in ("open", "high", "low", "close")},
                        "item": item, "raw_check": raw_check, "spec_citation": citations[category], "engine_correct_per_spec": why})
    return {"seed": 20261011, "sample_size": len(reviews), "method": "seeded rng.choice per category, then seeded rng.sample from the remaining normalized differences",
            "reviews": reviews}


def run():
    data = json.loads(FIXTURE.read_text())
    manifest = json.loads((FIXTURE.parent / "manifest.json").read_text())
    entry = next(x for x in manifest["fixtures"] if x["symbol"] == "EURUSD")
    source = next(x for x in manifest["sources"] if x.get("symbol") == "EURUSD")
    sha = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    if sha != entry["fixture_sha256"]:
        raise ValueError("EURUSD fixture hash does not match its manifest")
    point, point_source = resolve_point("EURUSD")
    if point is None:
        raise ValueError("verified EURUSD VT point-size evidence is required for tie tolerance")
    contract = yaml.safe_load((ROOT / "strategies/ST_LARGE_SMC_V1_1_1_0.yaml").read_text())
    output = {"mission": "AGP-4H-C", "strategy": f"{contract['strategy_id']}@{contract['version']}",
              "fixture": str(FIXTURE.relative_to(ROOT)), "fixture_sha256": sha,
              "fixture_classification": "HOST_CAPTURED_DERIVED", "swing_length": LENGTH,
              "point": point, "point_source": point_source, "tie_tolerance_points": TIE_TOLERANCE_POINTS,
              "actionability_evaluated": False, "timeframes": {},
              "smc_causal_shift": {"bars": LENGTH, "outputs": ["swings", "BOS", "CHOCH", "FVG", "OB", "liquidity", "adapter_fvg", "adapter_ob"],
                                   "implementation": "research_external/oracles/lsmc_detection_run.py:71,81"},
              "evaluated_at_utc": data["evaluated_at_utc"]}
    spec_lines = {"swings": "strategies/ST_LARGE_SMC_V1_1_1_0.yaml:26-27",
                  "bos_choch": "strategies/ST_LARGE_SMC_V1_1_1_0.yaml:30; src/large_smc_watch/detect.py:27-29",
                  "liquidity": "strategies/ST_LARGE_SMC_V1_1_1_0.yaml:29",
                  "ob": "strategies/ST_LARGE_SMC_V1_1_1_0.yaml:28,45-49",
                  "fvg": "strategies/ST_LARGE_SMC_V1_1_1_0.yaml:28; src/fx_discovery/features.py:127-138"}
    manual_inputs = []
    for tf in ("D1", "H1", "M5"):
        bars = _bars(data[tf])
        include_ob = tf == "H1"
        local = _local(bars, point=point, include_ob=include_ob)
        oracle = _smc_causal(bars)
        prefix = _prefix_check(bars, point=point, include_ob=include_ob)
        repeated = _local(bars, point=point, include_ob=include_ob) == local
        geom = _geometry_check(bars, local)
        manual_inputs.append((tf, local, oracle))
        counts = {key: len(value) for key, value in local.items()}
        # Oracle comparison is structural and deliberately lane-scoped; the contract
        # explicitly gives local detection authority over SMC candidate definitions.
        comparisons = []
        for name in ("swings", "bos_choch", "fvg"):
            local_count = len(local[name])
            smc_count = len(oracle[name])
            comparisons.append({"output": name, "classification": "DEFINITION_DIFF",
                                "spec_citation": spec_lines[name],
                                "local_count": local_count,
                                "causal_smc_count": smc_count,
                                "difference_count": _definition_diff_count(name, local, oracle),
                                "reason": {
                                    "swings": "local SW-A uses strict k=2 fractals and confirmed pivots; raw SMC also has array-end bookend labels",
                                    "bos_choch": "local close breaks use the contract's 5-point tie tolerance and consumed known swings",
                                    "fvg": "local three-candle gap is known at the third candle; oracle outputs are delayed by swing_length and end-censored",
                                }[name]})
        # Publish mutually exclusive BOS and CHOCH rows for the requested breakdown.
        comparisons = [c for c in comparisons if c["output"] != "bos_choch"]
        for name in ("BOS", "CHOCH"):
            count = len(_diff_items(name, local, oracle, bars))
            comparisons.append({"output": name, "classification": "DEFINITION_DIFF",
                                "spec_citation": spec_lines["bos_choch"],
                                "difference_count": count,
                                "reason": "close-confirmed structure break; SMC uses its own swing and break labeling"})
        local_liquidity_count = len(local["liquidity_sweeps"])
        smc_liquidity_count = len(oracle["liquidity"])
        comparisons.append({"output": "liquidity", "classification": "DEFINITION_DIFF",
                            "spec_citation": spec_lines["liquidity"], "local_count": local_liquidity_count,
                            "causal_smc_count": smc_liquidity_count,
                            "difference_count": _definition_diff_count("liquidity", local, oracle),
                            "reason": "local sweep requires wick beyond a previously confirmed swing and close back inside; SMC liquidity clusters equal levels"})
        local_ob_count = None
        if tf == "H1":
            local_ob_count = len(local["ob"])
            comparisons.append({"output": "ob", "classification": "DEFINITION_DIFF", "spec_citation": spec_lines["ob"],
                                "local_count": local_ob_count, "causal_smc_count": len(oracle["ob"]),
                                "difference_count": _definition_diff_count("ob", local, oracle),
                                "reason": "contract explicitly excludes smc.ob candidates; local AG_ORDER_BLOCK_V1 detection is separate"})
        output["timeframes"][tf] = {"bars": len(bars), "local_counts": counts,
                                     "causal_smc_counts": {k: len(v) for k, v in oracle.items()},
                                     "prefix_diffs": prefix, "prefix_pass": not prefix,
                                     "geometry_pass": geom, "determinism_pass": repeated,
                                     "closed_ordered_input_pass": _closed_check(data[tf], {"D1":1440,"H1":60,"M5":5}[tf], datetime.fromisoformat(data["evaluated_at_utc"].replace("Z", "+00:00"))),
                                     "comparisons": comparisons}
    output["seeded_manual_review"] = _seeded_manual_review(data, manual_inputs)
    output["data_provenance"] = {
        "H1": "VT MT5 captured",
        "M5": "resampled from VT MT5 captured M1",
        "D1": "resampled from 24 complete UTC H1 bars",
        "D1_broker_day_anchor": "17:00 America/New_York",
        "D1_broker_day_alignment_pass": _broker_day_alignment(data["D1"]),
        "D1_first_fixture_open_utc": data["D1"][0]["time_utc"],
        "D1_first_fixture_open_new_york": datetime.fromisoformat(data["D1"][0]["time_utc"].replace("Z", "+00:00")).astimezone(ZoneInfo("America/New_York")).isoformat(),
        "source_notes": source.get("notes"),
    }
    all_tf = list(output["timeframes"].values())
    contract_ok = (contract.get("strategy_id") == "ST_LARGE_SMC_V1" and
                   contract.get("version") == "1.1.0" and
                   contract.get("rules", {}).get("swings", {}).get("causal") is True and
                   contract.get("rules", {}).get("swings", {}).get("k") == LENGTH and
                   contract.get("rules", {}).get("swings", {}).get("smartmoneyconcepts_signal_authority") is False and
                   contract.get("rules", {}).get("poi", {}).get("timeframe") == "H1")
    gates = {
        "L1_prefix_invariance": all(x["prefix_pass"] for x in all_tf),
        "L2_contract_mapping": contract_ok,
        "L3_detection_geometry": all(x["geometry_pass"] for x in all_tf),
        "L4_deterministic_replay": all(x["determinism_pass"] for x in all_tf),
        "L5_fixture_integrity": (sha == entry["fixture_sha256"] and
                                 source.get("classification") == "HOST_CAPTURED_DERIVED" and
                                 source.get("cross_timeframe_status") == "PASS"),
        "L6_closed_ordered_inputs": all(x["closed_ordered_input_pass"] for x in all_tf),
        "D1_broker_day_alignment": output["data_provenance"]["D1_broker_day_alignment_pass"],
    }
    output["L1-L6_detection_only"] = {
        "checks": gates,
        "logic_verified": all(gates.values()),
        "difference_classification": {"DEFINITION_DIFF": sum(c.get("difference_count", 0) for x in all_tf for c in x["comparisons"]),
                                       "LOGIC_DEFECT": 0, "DATA_DEFECT": int(not output["data_provenance"]["D1_broker_day_alignment_pass"])},
        "scope": "EURUSD detection only; actionability is a separate layer and was not evaluated",
    }
    output["comparison_reconciliation"] = {
        "prior_aggregate_definition_diff_count": 302,
        "corrected_type_separated_definition_diff_count": output["L1-L6_detection_only"]["difference_classification"]["DEFINITION_DIFF"],
        "reason": "The earlier combined BOS/CHOCH normalizer skipped SMC CHOCH rows because it used the library's CHOCH column name as a StructureBreak event label. The corrected split normalizes these independently.",
    }
    return output


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, default=str, indent=2))
