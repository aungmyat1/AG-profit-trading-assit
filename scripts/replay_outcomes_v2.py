"""One-shot canonical outcome replay under AG_OUTCOME_RESOLUTION_CONTRACT_V2.

    python scripts/replay_outcomes_v2.py

Verifies the frozen contract hash and both dataset hashes, then builds the Opportunity
population with the unchanged fx_opportunity runner (REPLAY mode, now = each cycle's
window end) and resolves every READY Opportunity with outcome_resolution.v2 against
post-fill M1 bars. The evidence file is write-once: the script refuses to run if it
already exists. No MT5, no proposal, no ticket.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import os
import random
import statistics
import sys
from collections import Counter
from dataclasses import asdict

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "src"))
os.chdir(_REPO)

import yaml  # noqa: E402

from fx_opportunity import CYCLES, evaluate_fx_opportunity  # noqa: E402
from mt5.market_data import MarketDataError  # noqa: E402
from opportunity.registry_binding import resolve_strategy_binding  # noqa: E402
from outcome_resolution.v2 import RESOLVED_STATES, OpportunityInput, resolve_v2  # noqa: E402
from post_asian_pilot.pilot_config import load_pilot_config  # noqa: E402
from strategy_engine.loader import load_strategy  # noqa: E402
from strategy_engine.session import Candle  # noqa: E402

CONTRACT_PATH = "config/governance/AG_OUTCOME_RESOLUTION_CONTRACT_V2.yaml"
CONTRACT_SHA256 = "a5680bb014bff836ebc0536b91fe050cf84060d81d0bdbae6bec2eaf003128aa"  # LF-normalized, as frozen in 0992103
OUT_PATH = "artifacts/validation/AG_FX_OPPORTUNITY_FOUNDATION_V1/ST_ASIAN_SWEEP_5R_V1_1_2_0_CANDIDATE_OUTCOMES_V2.json"
UTC = dt.timezone.utc
M15 = dt.timedelta(minutes=15)


def _sha(path: str, normalize_eol: bool = False) -> str:
    data = open(path, "rb").read()
    return hashlib.sha256(data.replace(b"\r\n", b"\n") if normalize_eol else data).hexdigest()


def _load(path):
    bars = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            t = dt.datetime.strptime(row["timestamp_utc"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
            if t in bars:
                raise SystemExit(f"DUPLICATE_TIMESTAMP {path} {t}")
            bars[t] = Candle(time=t, open=float(row["open"]), high=float(row["high"]),
                             low=float(row["low"]), close=float(row["close"]),
                             volume=float(row.get("tick_volume") or 0))
    return bars


def _metrics(rows, key):
    resolved = [r for r in rows if r["state"] in RESOLVED_STATES]
    vals = [r[key] for r in resolved]
    wins, losses = [v for v in vals if v > 0], [v for v in vals if v < 0]
    out = {
        "n_resolved": len(vals), "n_win": len(wins), "n_loss": len(losses),
        "n_flat": len(vals) - len(wins) - len(losses),
        "win_rate": (len(wins) / len(vals)) if vals else None,
        "expectancy_R": statistics.fmean(vals) if vals else None,
        "total_R": sum(vals),
        "median_R": statistics.median(vals) if vals else None,
        "profit_factor": (sum(wins) / abs(sum(losses))) if losses else None,
    }
    if len(vals) >= 2:
        rng = random.Random(20260928)
        means = sorted(statistics.fmean(rng.choices(vals, k=len(vals))) for _ in range(10_000))
        out["expectancy_R_bootstrap_95ci"] = [means[249], means[9749]]
    return out


def _group(rows):
    states = Counter(r["state"] for r in rows)
    resolved = [r for r in rows if r["state"] in RESOLVED_STATES]
    return {
        "n_opportunities": len(rows),
        "n_filled": sum(1 for r in rows if not r["state"].startswith("EXCLUDED")),
        "n_resolved": len(resolved),
        "n_ambiguous": states.get("AMBIGUOUS_SAME_BAR", 0),
        "n_unresolved": states.get("UNRESOLVED_MISSING_M1", 0),
        "n_excluded": sum(v for k, v in states.items() if k.startswith("EXCLUDED")),
        "states": dict(sorted(states.items())),
        "gross": _metrics(rows, "gross_R"),
        "net": _metrics(rows, "net_R"),
        "friction_drag_R_total": sum(r["friction_R"] for r in resolved),
        "friction_drag_R_mean": statistics.fmean([r["friction_R"] for r in resolved]) if resolved else None,
        "mfe_R_median": statistics.median([r["mfe_R"] for r in resolved]) if resolved else None,
        "mae_R_median": statistics.median([r["mae_R"] for r in resolved]) if resolved else None,
        "holding_minutes_median": statistics.median([r["holding_minutes"] for r in resolved]) if resolved else None,
        "engine_entry_differs_from_close": sum(1 for r in rows if r["engine_entry"] != r["entry"]),
    }


def main() -> int:
    if os.path.exists(OUT_PATH):
        print(json.dumps({"error": "ONE_SHOT_ALREADY_RUN", "evidence": OUT_PATH}))
        return 3
    if _sha(CONTRACT_PATH, normalize_eol=True) != CONTRACT_SHA256:
        print(json.dumps({"error": "CONTRACT_HASH_MISMATCH"}))
        return 2
    contract = yaml.safe_load(open(CONTRACT_PATH, encoding="utf-8"))
    ds = contract["dataset_requirements"]
    for tf in ("m15", "m1"):
        if _sha(ds[tf]["path"]) != ds[tf]["sha256"]:
            print(json.dumps({"error": "DATASET_HASH_MISMATCH", "timeframe": tf}))
            return 2
    m15, m1 = _load(ds["m15"]["path"]), _load(ds["m1"]["path"])
    m15_list = sorted(m15.values(), key=lambda c: c.time)
    m1_list = sorted(m1.values(), key=lambda c: c.time)

    def feed(symbol, timeframe, start, end):
        if symbol != "EURUSD" or timeframe != "M15":
            raise MarketDataError("DATA_MISSING", f"{symbol} {timeframe}")
        out = [b for b in m15_list if start <= b.time < end]
        if not out:
            raise MarketDataError("DATA_MISSING", "no bars")
        return out

    days = sorted({t.date() for t in m15 if t.weekday() < 5})
    source = f"replay:{ds['m15']['path']}@sha256:{ds['m15']['sha256']}"
    rows = []
    for cycle in sorted(CYCLES):
        pilot = load_pilot_config(CYCLES[cycle])
        strategy = load_strategy(pilot.strategy_source_path)
        binding = resolve_strategy_binding(pilot.strategy_id)
        cutoff_t = dt.time.fromisoformat(pilot.execution_window_end_utc)
        for day in days:
            cutoff = dt.datetime.combine(day, cutoff_t, tzinfo=UTC)
            res = evaluate_fx_opportunity(
                cycle=cycle, symbol="EURUSD", trading_date=day, now=cutoff, pilot=pilot,
                strategy=strategy, binding=binding, fetch_candles=feed,
                market_data_mode="REPLAY", source=source)
            assert res.proposal == "NO_PROPOSAL_AUTHORITY" and res.trade_ticket == "NOT_CREATED"
            if res.opportunity != "OPPORTUNITY":
                continue
            sig = res.decision.signal
            sweep = m15[sig.signal_timestamp]
            wick = sweep.low if sig.direction == "LONG" else sweep.high
            if wick != sig.stop_loss:
                raise SystemExit(f"STOP_LINEAGE_MISMATCH {day} {cycle}")
            opp = OpportunityInput(
                opportunity_id=res.candidate.candidate_id, cycle=cycle, trading_date=day,
                direction=sig.direction, sweep_open_time=sig.signal_timestamp, sweep_close=sweep.close,
                stop=sig.stop_loss, box_high=sig.box_high, box_low=sig.box_low,
                session_cutoff=cutoff, engine_entry=sig.entry)
            window = [b for b in m1_list if sig.signal_timestamp <= b.time < cutoff]
            row = asdict(resolve_v2(opp, window))
            row.update(strategy_id=sig.strategy_id, engine_strategy_version=sig.strategy_version,
                       candidate_version="1.2.0-CANDIDATE", reason_code=sig.reason_code,
                       provenance=res.provenance["lineage_fingerprint"])
            rows.append(row)

    report = {
        "schema": "AG_OUTCOME_REPLAY_V2_EVIDENCE",
        "contract": CONTRACT_PATH, "contract_sha256_lf": CONTRACT_SHA256,
        "strategy_id": "ST_ASIAN_SWEEP_5R_V1", "candidate_version": "1.2.0-CANDIDATE",
        "dataset_id": ds["dataset_id"], "m15_sha256": ds["m15"]["sha256"], "m1_sha256": ds["m1"]["sha256"],
        "trading_days": len(days), "first_day": days[0].isoformat(), "last_day": days[-1].isoformat(),
        "friction": {"scenario": "CONTRACT_CEILING", "spread_pips": 2.0, "slippage_pips": 1.0,
                     "commission": "0.0 UNVERIFIED_NO_SIGNED_COMMISSION_RATE"},
        "classification_scope": "EVIDENCE_ONLY -- not ECONOMIC_STRATEGY_QUALIFICATION",
        "authority": {"proposal": "NONE", "demo": "NONE", "live": "NONE", "trade_ticket": "NOT_CREATED"},
        "groups": {
            "POST_ASIAN": _group([r for r in rows if r["cycle"] == "POST_ASIAN"]),
            "POST_LONDON": _group([r for r in rows if r["cycle"] == "POST_LONDON"]),
            "COMBINED": _group(rows),
        },
        "observations": rows,
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "x", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(report, indent=2, default=str) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "observations"}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
