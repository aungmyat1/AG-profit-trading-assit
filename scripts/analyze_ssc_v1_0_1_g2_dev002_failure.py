"""SSC v1.0.1 EVIDENCE-FIRST FAILURE DECOMPOSITION V2 -- read-only diagnostic driver.

Reads the FROZEN G2 population (SSC_V1_0_1_G2_DEV_002_POPULATION_V1) and derives the
full diagnostic decomposition from that immutable evidence only:

  - D0: population identity/hash re-verification (research.session_lifecycle.population_hash)
  - D2: gross-alpha-first metrics (performance.calculator + median/average win/loss)
  - D4/D5/D6: setup / direction / session decomposition + cross-tabs
  - D7: excursion + path mechanics (event-sequence path facts + MFE/MAE derived
        deterministically from the FROZEN M1 candles -- no replay, no re-resolution)
  - D9: regime x direction / regime x setup cross-tabs via the canonical
        session_sweep_continuation.regime.classify_regime (identical logic the replay
        itself used internally -- a recomputation for cross-tabulation only)
  - D10: friction decomposition (mean/median/total, by setup/session/direction,
        friction share of absolute net loss)

This script performs NO replay, NO occurrence regeneration, NO parameter change, and
NO protected-data access. Output is a JSON document printed to stdout and written to
the frozen artifact directory as G2_FAILURE_DECOMPOSITION_V1.json.
"""
from __future__ import annotations

import hashlib
import json
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from performance.calculator import compute_trade_metrics  # noqa: E402
from performance.models import ResolvedTradeSample  # noqa: E402
from research.session_lifecycle import population_hash  # noqa: E402
from session_sweep_continuation.config import load_config  # noqa: E402
from session_sweep_continuation.regime import classify_regime  # noqa: E402
from session_sweep_continuation.sessions import build_reference_session, session_windows_from_config  # noqa: E402
from historical_replay.utc_export_csv_loader import load_utc_export_csv  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
SYMBOL = "EURUSD"
PIP_SIZE = 0.0001
DATASET_ID = "SSC_V1_0_1_G2_DEV_002"
POPULATION_ID = "SSC_V1_0_1_G2_DEV_002_POPULATION_V1"
ARTIFACT_DIR = REPO_ROOT / "artifacts" / "validation" / "ST_SESSION_SWEEP_CONTINUATION_V1" / DATASET_ID
POPULATION_PATH = ARTIFACT_DIR / "G2_POPULATION_V1.json"
M1_CSV = REPO_ROOT / "data" / "research" / "ssc_fresh_dev" / DATASET_ID / "raw" / "EURUSD_M1.csv"
M15_CSV = REPO_ROOT / "data" / "research" / "ssc_fresh_dev" / DATASET_ID / "raw" / "EURUSD_M15.csv"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _net_pf(samples) -> object:
    vals = [s.net_R for s in samples if s.net_R is not None]
    if not vals:
        return "NOT_EVALUATED"
    pos = sum(r for r in vals if r > 0)
    neg = sum(r for r in vals if r < 0)
    if neg == 0 and pos == 0:
        return "NOT_EVALUATED"
    if neg == 0:
        return "UNDEFINED_NO_LOSSES"
    if pos == 0:
        return "UNDEFINED_NO_WINS"
    return pos / abs(neg)


def _metrics(samples):
    m = compute_trade_metrics(samples)
    gross = [s.gross_R for s in samples]
    wins = [r for r in gross if r > 1e-9]
    losses = [r for r in gross if r < -1e-9]
    return {
        "N": m.sample_size,
        "wins": m.wins, "losses": m.losses, "breakevens": m.breakevens,
        "gross_total_R": m.gross_total_R, "gross_expectancy_R": m.gross_expectancy_R,
        "gross_profit_factor": m.profit_factor,
        "net_total_R": m.net_total_R, "net_expectancy_R": m.net_expectancy_R,
        "net_profit_factor": _net_pf(samples),
        "win_rate": m.win_rate,
        "average_win_R": (sum(wins) / len(wins)) if wins else "NOT_EVALUATED",
        "average_loss_R": (sum(losses) / len(losses)) if losses else "NOT_EVALUATED",
        "median_trade_R": statistics.median(gross) if gross else "NOT_EVALUATED",
        "max_drawdown_R": m.max_drawdown_R,
        "cost_status": m.cost_status,
    }


def _classify_subgroup(n: int) -> str:
    if n < 5:
        return "INSUFFICIENT_SUBGROUP_SAMPLE"
    if n < 10:
        return "LOW_SAMPLE_EXPLORATORY"
    return "REPORTABLE"


def main() -> int:
    config = load_config(repo_root=str(REPO_ROOT))
    windows = session_windows_from_config(config)

    pop = json.load(open(POPULATION_PATH, encoding="utf-8"))
    occurrences = pop["occurrences"]
    geometry = {g["trade_id"]: g for g in pop["occurrence_geometry"]}
    if len(occurrences) != len(geometry):
        raise SystemExit(f"BLOCKED_POPULATION_IDENTITY: occurrences {len(occurrences)} != geometry {len(geometry)}")

    # --- D0: identity re-verification ----------------------------------------------
    recomputed_hash = population_hash(occurrences)
    recorded_hash = pop["population_sha256"]
    identity = {
        "population_id": pop["population_id"],
        "reported_hash": recorded_hash,
        "recomputed_hash": recomputed_hash,
        "hash_match": recomputed_hash == recorded_hash,
        "dataset_fingerprint_recorded": pop["dataset_fingerprint"],
        "preregistration_hash_recorded": pop["preregistration_hash"],
        "strategy_id": pop["strategy_id"],
        "strategy_version": pop["strategy_version"],
    }
    if not identity["hash_match"] or pop["population_id"] != POPULATION_ID:
        print(json.dumps(identity, indent=2), file=sys.stderr)
        raise SystemExit("BLOCKED_POPULATION_IDENTITY")

    # --- Build samples (independent recomputation from frozen records) -------------
    samples = []
    for rec in occurrences:
        g = geometry[rec["trade_id"]]
        samples.append(ResolvedTradeSample(
            source_record_id=rec["trade_id"],
            source_path="frozen:G2_POPULATION_V1.json",
            strategy_id=rec["strategy_id"],
            strategy_version=rec["strategy_version"],
            symbol=rec["symbol"],
            cycle=g["session_pair"],
            resolved_at=rec["entry_time"],
            gross_R=rec["gross_R"],
            net_R=rec["net_R"],
            cost_status="MODELED",
            outcome=rec["final_state"],
        ))

    by_setup = {"S1": [], "S2": [], "S3": []}
    by_direction = {"LONG": [], "SHORT": []}
    by_session = {"ASIAN_LONDON": [], "LONDON_NEWYORK": []}
    by_exit = {}
    for s in samples:
        g = geometry[s.source_record_id]
        by_setup[g["setup"]].append(s)
        by_direction[g["direction"]].append(s)
        by_session[g["session_pair"]].append(s)
        by_exit.setdefault(s.outcome, []).append(s)

    overall = _metrics(samples)
    setup_metrics = {k: _metrics(v) for k, v in by_setup.items()}
    direction_metrics = {k: _metrics(v) for k, v in by_direction.items()}
    session_metrics = {k: _metrics(v) for k, v in by_session.items()}
    exit_metrics = {k: _metrics(v) for k, v in sorted(by_exit.items())}

    subgroup_classification = {
        "LONG": _classify_subgroup(len(by_direction["LONG"])),
        "SHORT": _classify_subgroup(len(by_direction["SHORT"])),
        "S1": _classify_subgroup(len(by_setup["S1"])),
        "S2": _classify_subgroup(len(by_setup["S2"])),
        "S3": _classify_subgroup(len(by_setup["S3"])),
        "ASIAN_LONDON": _classify_subgroup(len(by_session["ASIAN_LONDON"])),
        "LONDON_NEWYORK": _classify_subgroup(len(by_session["LONDON_NEWYORK"])),
    }

    # --- D10: friction decomposition ------------------------------------------------
    friction_total = sum(rec["friction_R"] for rec in occurrences)
    friction_values = [rec["friction_R"] for rec in occurrences]
    friction_by_setup = {"S1": [], "S2": [], "S3": []}
    friction_by_direction = {"LONG": [], "SHORT": []}
    friction_by_session = {"ASIAN_LONDON": [], "LONDON_NEWYORK": []}
    for rec in occurrences:
        g = geometry[rec["trade_id"]]
        friction_by_setup[g["setup"]].append(rec["friction_R"])
        friction_by_direction[g["direction"]].append(rec["friction_R"])
        friction_by_session[g["session_pair"]].append(rec["friction_R"])
    net_loss_abs = abs(overall["net_total_R"]) if isinstance(overall["net_total_R"], float) else None
    friction = {
        "total_friction_R": friction_total,
        "mean_friction_R": statistics.mean(friction_values),
        "median_friction_R": statistics.median(friction_values),
        "min_friction_R": min(friction_values),
        "max_friction_R": max(friction_values),
        "friction_by_setup": {k: {"total": sum(v), "mean": statistics.mean(v) if v else None}
                              for k, v in friction_by_setup.items()},
        "friction_by_direction": {k: {"total": sum(v), "mean": statistics.mean(v) if v else None}
                                  for k, v in friction_by_direction.items()},
        "friction_by_session": {k: {"total": sum(v), "mean": statistics.mean(v) if v else None}
                                for k, v in friction_by_session.items()},
        "friction_share_of_absolute_net_loss": (friction_total / net_loss_abs) if net_loss_abs else None,
    }

    # --- D7: path mechanics from frozen event sequences ----------------------------
    stop_first = sum(1 for rec in occurrences if rec["final_state"] == "RESOLVED_SL")
    partial_active = sum(
        1 for rec in occurrences if any(e["event"] == "PARTIAL_TARGET" for e in rec["events"])
    )
    runner_active = sum(
        1 for rec in occurrences
        if any(e["event"] in ("RUNNER_BE_STOP", "RUNNER_TARGET_HIT", "SESSION_EXIT_RUNNER") for e in rec["events"])
    )
    full_pos_session_exit = sum(
        1 for rec in occurrences
        if any(e["event"] == "SESSION_EXIT_FULL_POSITION" for e in rec["events"])
    )

    # --- D7: excursion derived deterministically from FROZEN M1 candles -------------
    m1_candles, _m1_report = load_utc_export_csv(str(M1_CSV), SYMBOL, "M1")
    m15_candles, _m15_report = load_utc_export_csv(str(M15_CSV), SYMBOL, "M15")
    m1_times = [c.time for c in m1_candles]

    def trade_end_for(pair_id: str, trading_date: str) -> datetime:
        d = datetime.fromisoformat(trading_date).date()
        return windows[pair_id]["trade"].bounds_for_date(d)[1]

    excursions = []
    regime_by_occurrence = {}
    for rec in occurrences:
        g = geometry[rec["trade_id"]]
        entry_time = datetime.fromisoformat(rec["entry_time"])
        entry_price = rec["entry_price"]
        risk = rec["initial_risk"]
        direction = rec["direction"]
        trade_end = trade_end_for(g["session_pair"], g["trading_date"])

        # canonical regime recomputation (identical inputs replay used internally)
        ref_window = windows[g["session_pair"]]["reference"]
        ref_end = ref_window.bounds_for_date(datetime.fromisoformat(g["trading_date"]).date())[1]
        reference = build_reference_session(m15_candles, ref_window,
                                            datetime.fromisoformat(g["trading_date"]).date(),
                                            ref_end, PIP_SIZE)
        ref_closes = [c.close for c in m15_candles if c.time < ref_end]
        reg = classify_regime(ref_closes, reference.range_pips, reference.candle_count, config)
        regime_by_occurrence[rec["trade_id"]] = reg.regime.value

        # scan M1 candles strictly after entry, closing by trade_end
        post = [c for c in m1_candles if c.time > entry_time and c.time + timedelta(minutes=1) <= trade_end]
        if direction == "LONG":
            mfe = max(((c.high - entry_price) / risk) for c in post) if post else 0.0
            mae = max(((entry_price - c.low) / risk) for c in post) if post else 0.0
        else:
            mfe = max(((entry_price - c.low) / risk) for c in post) if post else 0.0
            mae = max(((c.high - entry_price) / risk) for c in post) if post else 0.0

        # partial target R from frozen geometry (reference boundary == first target)
        if direction == "LONG":
            partial_r = ((g["reference_high"] - entry_price) / risk) if g["reference_high"] > entry_price else None
        else:
            partial_r = ((entry_price - g["reference_low"]) / risk) if g["reference_low"] < entry_price else None

        # MFE before stop, for SL-resolved occurrences
        mfe_before_stop = None
        if rec["final_state"] == "RESOLVED_SL":
            sl_time = next((e["time"] for e in rec["events"] if e["event"] == "SL"), None)
            if sl_time:
                sl_dt = datetime.fromisoformat(sl_time)
                pre = [c for c in post if c.time < sl_dt]
                if direction == "LONG":
                    mfe_before_stop = max(((c.high - entry_price) / risk) for c in pre) if pre else 0.0
                else:
                    mfe_before_stop = max(((entry_price - c.low) / risk) for c in pre) if pre else 0.0

        excursions.append({
            "trade_id": rec["trade_id"], "setup": g["setup"], "direction": direction,
            "session_pair": g["session_pair"], "final_state": rec["final_state"],
            "gross_R": rec["gross_R"], "MFE_R": round(mfe, 6), "MAE_R": round(mae, 6),
            "partial_target_R": (round(partial_r, 6) if partial_r is not None else None),
            "mfe_before_stop_R": (round(mfe_before_stop, 6) if mfe_before_stop is not None else None),
            "capture_efficiency": (round(rec["gross_R"] / mfe, 6) if mfe > 1e-6 else None),
        })

    def _mean(xs):
        return statistics.mean(xs) if xs else None

    sl_exc = [e for e in excursions if e["final_state"] == "RESOLVED_SL"]
    non_sl_exc = [e for e in excursions if e["final_state"] != "RESOLVED_SL"]
    excursion_summary = {
        "stop_first_rate": stop_first / len(occurrences),
        "partial_activation_rate": partial_active / len(occurrences),
        "runner_activation_rate": runner_active / len(occurrences),
        "full_position_session_exit_count": full_pos_session_exit,
        "mean_MFE_R": _mean([e["MFE_R"] for e in excursions]),
        "mean_MAE_R": _mean([e["MAE_R"] for e in excursions]),
        "mean_MFE_R_losers": _mean([e["MFE_R"] for e in excursions if e["gross_R"] < -1e-9]),
        "mean_MFE_R_winners": _mean([e["MFE_R"] for e in excursions if e["gross_R"] > 1e-9]),
        "mean_mfe_before_stop_R": _mean([e["mfe_before_stop_R"] for e in sl_exc if e["mfe_before_stop_R"] is not None]),
        "mean_partial_target_R": _mean([e["partial_target_R"] for e in excursions if e["partial_target_R"] is not None]),
        "mean_capture_efficiency_winners": _mean([e["capture_efficiency"] for e in excursions
                                                  if e["gross_R"] > 1e-9 and e["capture_efficiency"] is not None]),
    }

    # --- D9: regime x direction / regime x setup cross-tabs -------------------------
    regime_x_direction = {}
    regime_x_setup = {}
    for e in excursions:
        reg = regime_by_occurrence[e["trade_id"]]
        regime_x_direction.setdefault(reg, {}).setdefault(e["direction"], 0)
        regime_x_direction[reg][e["direction"]] += 1
        regime_x_setup.setdefault(reg, {}).setdefault(e["setup"], 0)
        regime_x_setup[reg][e["setup"]] += 1
    # regime x direction economics
    regime_direction_econ = {}
    for e in excursions:
        reg = regime_by_occurrence[e["trade_id"]]
        key = f"{reg}::{e['direction']}"
        regime_direction_econ.setdefault(key, []).append(e["gross_R"])
    regime_direction_econ = {k: {"N": len(v), "gross_total_R": sum(v),
                                 "gross_expectancy_R": statistics.mean(v)}
                             for k, v in sorted(regime_direction_econ.items())}

    # --- D6: cross-tabs -------------------------------------------------------------
    session_x_setup = {}
    session_x_direction = {}
    for e in excursions:
        session_x_setup.setdefault(e["session_pair"], {}).setdefault(e["setup"], 0)
        session_x_setup[e["session_pair"]][e["setup"]] += 1
        session_x_direction.setdefault(e["session_pair"], {}).setdefault(e["direction"], 0)
        session_x_direction[e["session_pair"]][e["direction"]] += 1

    result = {
        "schema": "AG_SSC_V1_0_1_G2_FAILURE_DECOMPOSITION_V1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "identity": identity,
        "overall": overall,
        "friction": friction,
        "subgroup_classification": subgroup_classification,
        "by_setup": setup_metrics,
        "by_direction": direction_metrics,
        "by_session": session_metrics,
        "by_exit_path": exit_metrics,
        "session_x_setup": session_x_setup,
        "session_x_direction": session_x_direction,
        "regime_x_direction": regime_x_direction,
        "regime_x_setup": regime_x_setup,
        "regime_x_direction_economics": regime_direction_econ,
        "excursion_summary": excursion_summary,
        "excursions": excursions,
    }

    (ARTIFACT_DIR / "G2_FAILURE_DECOMPOSITION_V1.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    print(json.dumps({k: v for k, v in result.items() if k != "excursions"}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
