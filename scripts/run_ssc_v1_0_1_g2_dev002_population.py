"""SSC v1.0.1 SVOS G2 ONE-SHOT HISTORICAL REPLAY -- DEV_002 population driver.

Executes the ONE canonical G2 historical population replay for
ST_SESSION_SWEEP_CONTINUATION_V1 v1.0.1 over the frozen development dataset
SSC_V1_0_1_G2_DEV_002, using the SAME established canonical mechanism as the GEN_001 /
HYP_002 population drivers (reused, not reimplemented):

  historical_replay.utc_export_csv_loader.load_utc_export_csv (DEV_002 raw CSVs are
    already-UTC MetaTrader5 copy_rates_* native exports -- no offset detection)
  historical_replay.candle_store.HistoricalCandleStore (H1 closed-bar store)
  historical_replay.symbol_metadata_manifest.load_symbol_metadata_manifest +
    validate_manifest_for_dataset (DEV_002 H1 metadata binding, OWNER_APPROVED)
  session_sweep_continuation.h1_bias.resolve_h1_market_bias (H1 -> MarketBiasResult)
  session_sweep_continuation.replay.run_replay (M15 setup + M1 fill/outcome)
  research.session_lifecycle (lifecycle_record / population_hash / compare_lifecycle_records)
  performance.calculator.compute_trade_metrics (economics)

Gates executed here: G1 (dataset identity), G2 (metadata + warmup admission + H1 bias
preflight), G3 (strategy authority), G4 (protected-data firewall), G5 (replay identity
-- no prior population), G6 (the ONE replay), G7 (freeze population), G8 (determinism
-- second run is verification only, never a second authoritative population), G9
(descriptive metrics + decomposition), G10 (failure diagnosis), G11 (economic gate =
NOT_EVALUATED_UNSIGNED_CONTRACT), G12 (optimization admission = false).

RESEARCH ONLY. Places no orders, touches no demo/live authorization, changes no
strategy parameter, and accesses no confirmation/holdout/OOS/H2 evidence.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from historical_replay.candle_store import HistoricalCandleStore  # noqa: E402
from historical_replay.symbol_metadata_manifest import (  # noqa: E402
    load_symbol_metadata_manifest,
    validate_manifest_for_dataset,
)
from historical_replay.utc_export_csv_loader import load_utc_export_csv  # noqa: E402
from performance.calculator import compute_trade_metrics  # noqa: E402
from performance.models import ResolvedTradeSample  # noqa: E402
from research.session_lifecycle import (  # noqa: E402
    compare_lifecycle_records,
    lifecycle_record,
    population_hash,
)
from session_sweep_continuation import STRATEGY_ID, STRATEGY_VERSION  # noqa: E402
from session_sweep_continuation.config import compute_config_hash, load_config  # noqa: E402
from session_sweep_continuation.h1_bias import resolve_h1_market_bias  # noqa: E402
from session_sweep_continuation.replay import run_replay  # noqa: E402
from session_sweep_continuation.sessions import (  # noqa: E402
    build_reference_session,
    session_windows_from_config,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SYMBOL = "EURUSD"
PIP_SIZE = 0.0001
PIP_VALUE_PER_LOT = 10.0
STRUCTURE_WARMUP_H1_BARS = 1000  # market_structure.tiers.EXTERNAL_SWING_LENGTH(50)*20

DATASET_ID = "SSC_V1_0_1_G2_DEV_002"
POPULATION_ID = "SSC_V1_0_1_G2_DEV_002_POPULATION_V1"
CANONICAL_REPLAY_AUTHORITY = "session_sweep_continuation.replay.run_replay"

RAW_DIR = REPO_ROOT / "data" / "research" / "ssc_fresh_dev" / DATASET_ID / "raw"
H1_CSV = RAW_DIR / "EURUSD_H1.csv"
M15_CSV = RAW_DIR / "EURUSD_M15.csv"
M1_CSV = RAW_DIR / "EURUSD_M1.csv"
H1_MANIFEST_PATH = (
    REPO_ROOT / "config" / "historical_datasets" / "EURUSD_H1_SSC_G2_DEV_002_symbol_metadata.yaml"
)
ARTIFACT_DIR = REPO_ROOT / "artifacts" / "validation" / "ST_SESSION_SWEEP_CONTINUATION_V1" / DATASET_ID
PREREG_PATH = ARTIFACT_DIR / "G2_POPULATION_PREREGISTRATION.json"
DATASET_MANIFEST_PATH = RAW_DIR.parent / "dataset_manifest.json"

EXPECTED_SHA256 = {
    H1_CSV: "93d27d8cbeb85c0b595ece7d18a43ac66219ae9fbb137e23a9826b84fc191c79",
    M15_CSV: "cefed9705bf9609329183c9bc44b7536eafdf070950ff6bcd45b759623ccd063",
    M1_CSV: "b760a2a65f8f453d121500657e824daec63579bfa4e67895e4501454dedc7458",
}
EXPECTED_DATASET_FINGERPRINT = "05b059720a7457d15a7fbc4cd7f0c15e62df86b7857c1f122edc49a0d3a2baf5"
EXPECTED_PREREGISTRATION_HASH = "d40fca49b2ff92768cafd45cdb5d48de96d53ad68449af68d41f8a348d4b0952"


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except Exception:
        return "UNKNOWN"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _verify_identity() -> dict:
    """G1: independently recompute DEV_002 identities and compare to frozen values."""
    actual = {}
    for p in (H1_CSV, M15_CSV, M1_CSV):
        if not p.exists():
            raise SystemExit(f"BLOCKED_DATASET_IDENTITY: missing {p.name}")
        actual[p.name] = _sha256_file(p)
    h1, m15, m1 = actual["EURUSD_H1.csv"], actual["EURUSD_M15.csv"], actual["EURUSD_M1.csv"]

    combined_input = (
        f"EURUSD|H1|{h1}\nEURUSD|M15|{m15}\nEURUSD|M1|{m1}"
    )
    combined_fingerprint = hashlib.sha256(combined_input.encode("utf-8")).hexdigest()

    prereg = _read_json(PREREG_PATH)
    body = {k: v for k, v in prereg.items() if k != "preregistration_hash"}
    prereg_recomputed = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    result = {
        "H1_SHA256": h1, "M15_SHA256": m15, "M1_SHA256": m1,
        "DATASET_FINGERPRINT": combined_fingerprint,
        "PREREGISTRATION_HASH": prereg_recomputed,
        "H1_MATCH": h1 == EXPECTED_SHA256[H1_CSV],
        "M15_MATCH": m15 == EXPECTED_SHA256[M15_CSV],
        "M1_MATCH": m1 == EXPECTED_SHA256[M1_CSV],
        "FINGERPRINT_MATCH": combined_fingerprint == EXPECTED_DATASET_FINGERPRINT,
        "PREREG_MATCH": prereg_recomputed == EXPECTED_PREREGISTRATION_HASH,
    }
    if not all(
        (
            result["H1_MATCH"], result["M15_MATCH"], result["M1_MATCH"],
            result["FINGERPRINT_MATCH"], result["PREREG_MATCH"],
        )
    ):
        print(json.dumps(result, indent=2), file=sys.stderr)
        raise SystemExit("BLOCKED_DATASET_IDENTITY")
    return result


def _effective_date_range(h1_report, m15_report, m1_report, config, dev_interval) -> list:
    """Calendar dates inside the DEVELOPMENT decision interval for which, for EVERY
    configured session_pair, (a) M15 covers [ref_start, trade_end), (b) M1 covers
    [trade_start, trade_end), and (c) >= STRUCTURE_WARMUP_H1_BARS H1 bars close before
    ref_end. Warmup H1 bars before the decision interval are context-only and can never
    generate an occurrence -- this function simply never admits a date outside the
    development decision interval."""
    windows = session_windows_from_config(config)
    dev_start = datetime.fromisoformat(dev_interval["start"])
    dev_end = datetime.fromisoformat(dev_interval["end"])

    raw_start = max(m15_report.start_utc, m1_report.start_utc, h1_report.start_utc, dev_start)
    raw_end = min(m15_report.end_utc, m1_report.end_utc, h1_report.end_utc, dev_end)

    covered = []
    d = raw_start.date()
    while datetime.combine(d, datetime.min.time(), tzinfo=timezone.utc) <= raw_end:
        ok = True
        for pair_id, w in windows.items():
            ref_start, ref_end = w["reference"].bounds_for_date(d)
            trade_start, trade_end = w["trade"].bounds_for_date(d)
            if not (m15_report.start_utc <= ref_start and trade_end <= m15_report.end_utc):
                ok = False
                break
            if not (m1_report.start_utc <= trade_start and trade_end <= m1_report.end_utc):
                ok = False
                break
            if not (h1_report.start_utc + timedelta(hours=STRUCTURE_WARMUP_H1_BARS) <= ref_end):
                ok = False
                break
        if ok:
            covered.append(d)
        d += timedelta(days=1)
    return covered


def _setup_key(model: str) -> str:
    return "S1" if model.startswith("S1") else "S2" if model.startswith("S2") else "S3"


def _metrics_dict(m) -> dict:
    return {
        "N": m.sample_size, "wins": m.wins, "losses": m.losses, "breakevens": m.breakevens,
        "gross_total_R": m.gross_total_R, "gross_expectancy_R": m.gross_expectancy_R,
        "net_total_R": m.net_total_R, "net_expectancy_R": m.net_expectancy_R,
        "win_rate": m.win_rate, "profit_factor": m.profit_factor,
        "max_drawdown_R": m.max_drawdown_R, "max_consecutive_losses": m.max_consecutive_losses,
        "cost_status": m.cost_status,
    }


def _net_profit_factor(samples) -> object:
    """Descriptive net profit factor over net_R (canonical calculator only exposes
    gross profit_factor; this mirrors its own positive/negative-sum convention over
    net_R so G9's net_profit_factor requirement is met honestly)."""
    net_values = [s.net_R for s in samples if s.net_R is not None]
    if not net_values:
        return "NOT_EVALUATED"
    positive_sum = sum(r for r in net_values if r > 0)
    negative_sum = sum(r for r in net_values if r < 0)
    if negative_sum == 0 and positive_sum == 0:
        return "NOT_EVALUATED"
    if negative_sum == 0:
        return "UNDEFINED_NO_LOSSES"
    if positive_sum == 0:
        return "UNDEFINED_NO_WINS"
    return positive_sum / abs(negative_sum)


def _diagnose(m) -> dict:
    """G10: descriptive failure classification from evidence, never a search."""
    n = m.sample_size
    if n == 0:
        return {"PRIMARY": "NO_OCCURRENCES", "SECONDARY": "LOW_SAMPLE",
                "OBSERVED_FACTS": ["sample_size == 0"], "POSSIBLE_HYPOTHESES": []}
    facts, hypotheses = [], []
    primary = secondary = "OTHER_EVIDENCED_MECHANISM"

    net = m.net_expectancy_R
    gross = m.gross_expectancy_R
    friction_total = (m.gross_total_R - m.net_total_R) if (
        isinstance(m.net_total_R, float) and isinstance(m.gross_total_R, float)
    ) else None

    if isinstance(net, float) and net <= 0:
        facts.append(f"net_expectancy_R={net:.6f} <= 0")
        primary = "WEAK_GROSS_EDGE" if isinstance(gross, float) and gross <= 0 else primary
        if isinstance(gross, float) and gross > 0 and friction_total is not None and friction_total > 0:
            secondary = "FRICTION_DOMINANT"
            facts.append(f"gross_expectancy_R={gross:.6f} > 0 but friction_total_R={friction_total:.6f} flips net negative")
            hypotheses.append("HYPOTHESIS: modeled friction (spread+commission+slippage) consumes the gross edge")
        if n < 10:
            secondary = "LOW_SAMPLE"
            facts.append(f"sample_size={n} < performance_attribution.min_sample_size=10")
            hypotheses.append("HYPOTHESIS: sample too small for stable expectancy")
    if isinstance(net, float) and net > 0:
        facts.append(f"net_expectancy_R={net:.6f} > 0")
        primary = "NONE_OBSERVED"
        secondary = "NONE_OBSERVED"
    return {"PRIMARY": primary, "SECONDARY": secondary,
            "OBSERVED_FACTS": facts, "POSSIBLE_HYPOTHESES": hypotheses}


def main() -> int:
    config = load_config(repo_root=str(REPO_ROOT))
    if config.get("version") != STRATEGY_VERSION:
        raise SystemExit(f"BLOCKED_STRATEGY_AUTHORITY: config version {config.get('version')} != {STRATEGY_VERSION}")
    config_hash = compute_config_hash(config)
    git_commit = _git_commit()

    # --- G1: dataset identity ------------------------------------------------------
    identity = _verify_identity()

    # --- G3: strategy authority ----------------------------------------------------
    from session_sweep_continuation import replay as replay_mod
    from svos.adapters.ssc import forward_decision_entrypoint, historical_replay_entrypoint

    authority_parity = (
        historical_replay_entrypoint() is forward_decision_entrypoint()
        and forward_decision_entrypoint() is replay_mod.run_replay
    )
    exit_mode = config.get("trade_management", {}).get("partial_target_mode")
    if not authority_parity:
        raise SystemExit("BLOCKED_STRATEGY_AUTHORITY: historical/forward replay entrypoints diverge")
    if exit_mode != "NEXT_LIQUIDITY_TARGET":
        raise SystemExit(f"BLOCKED_STRATEGY_AUTHORITY: partial_target_mode={exit_mode!r} != NEXT_LIQUIDITY_TARGET")
    authority = {
        "STRATEGY": STRATEGY_ID, "VERSION": STRATEGY_VERSION,
        "CANONICAL_REPLAY": CANONICAL_REPLAY_AUTHORITY,
        "HISTORICAL_FORWARD_PARITY": "PASS",
        "EXIT_SEMANTICS": "OPPOSITE_SESSION_BOUNDARY",
        "partial_target_mode": exit_mode,
    }

    # --- G2: metadata + warmup admission + H1 bias preflight ------------------------
    h1_manifest = load_symbol_metadata_manifest(H1_MANIFEST_PATH)
    if h1_manifest.authority != "OWNER_APPROVED_DATASET_MANIFEST":
        raise SystemExit(f"BLOCKED_STRATEGY_AUTHORITY: H1 manifest authority={h1_manifest.authority!r}")
    validate_manifest_for_dataset(h1_manifest, H1_CSV, SYMBOL)
    metadata_manifest_hash = _sha256_file(H1_MANIFEST_PATH)

    h1_candles, h1_report = load_utc_export_csv(str(H1_CSV), SYMBOL, "H1")
    m15_candles, m15_report = load_utc_export_csv(str(M15_CSV), SYMBOL, "M15")
    m1_candles, m1_report = load_utc_export_csv(str(M1_CSV), SYMBOL, "M1")
    for report, label in ((h1_report, "H1"), (m15_report, "M15"), (m1_report, "M1")):
        if report.normalized_timezone != "UTC":
            raise SystemExit(f"{label}_TIMEZONE_NOT_UTC: {report.normalized_timezone}")

    h1_store = HistoricalCandleStore()
    h1_store.load_series(SYMBOL, "H1", h1_candles)

    # H1 bias preflight at the first decision point the warmup readiness already proved
    # (dataset_manifest.json minimum_at = 2026-06-22 06:00:00+00:00) -- ONE resolution.
    first_decision = datetime(2026, 6, 22, 6, 0, tzinfo=timezone.utc)
    preflight = resolve_h1_market_bias(h1_store, h1_manifest, SYMBOL, first_decision, "ASIAN_LONDON")
    bias_preflight_ok = (
        preflight.bias in ("BULLISH", "BEARISH", "NEUTRAL")
        and not ("SYMBOL_METADATA_MISSING" in "".join(preflight.reason_codes))
    )
    if not bias_preflight_ok:
        raise SystemExit(
            f"BIAS_PREFLIGHT_FAIL: bias={preflight.bias} confidence={preflight.confidence} "
            f"codes={preflight.reason_codes}"
        )

    # --- G4: protected-data firewall (asserted, never accessed) --------------------
    prereg = _read_json(PREREG_PATH)
    dataset_manifest = _read_json(DATASET_MANIFEST_PATH)
    firewall = {
        "CONFIRMATION_ACCESSED": False, "HOLDOUT_ACCESSED": False, "OOS_ACCESSED": False,
        "CONFIRM_001_CONSUMED": False, "H2_CONSUMED": False,
        "prereg_protected_data_clear": prereg.get("protected_data_clear") is True,
        "prereg_prior_consumption": prereg.get("prior_consumption"),
        "prereg_h2_broker_evidence_consumed": prereg.get("h2_broker_evidence_consumed") is False,
        "dataset_role": dataset_manifest.get("data_role"),
    }

    # --- G5: replay identity -- no prior authoritative population -------------------
    existing_population = ARTIFACT_DIR / "G2_POPULATION_V1.json"
    if existing_population.exists():
        print(json.dumps({
            "FINAL_STATUS": "ALREADY_EXECUTED",
            "POPULATION_ID": POPULATION_ID,
            "POPULATION_SHA256": _sha256_file(existing_population),
        }, indent=2))
        return 0

    dev_interval = prereg["development_decision_interval"]
    dates = _effective_date_range(h1_report, m15_report, m1_report, config, dev_interval)
    if not dates:
        raise SystemExit("BLOCKED_REPLAY_ERROR: EFFECTIVE_REPLAY_WINDOW_EMPTY")

    session_pairs = [p["pair_id"] for p in config.get("session_pairs", ())]
    windows = session_windows_from_config(config)

    def run_all_cycles(run_label: str):
        records = []
        geometry = []
        decision_cycles = 0
        bias_counts = {"BULLISH": 0, "BEARISH": 0, "NEUTRAL": 0}
        regime_counts = {}
        setup_counts = {"S1": 0, "S2": 0, "S3": 0}
        rejected_direction = 0
        rejected_friction = 0
        rejected_alloc = 0
        samples = []
        session_samples = {p: [] for p in session_pairs}
        direction_samples = {"LONG": [], "SHORT": []}
        setup_samples = {"S1": [], "S2": [], "S3": []}
        steps_log = []

        for d in dates:
            for pair_id in session_pairs:
                decision_cycles += 1
                ref_window = windows[pair_id]["reference"]
                ref_start, ref_end = ref_window.bounds_for_date(d)
                reference = build_reference_session(m15_candles, ref_window, d, ref_end, PIP_SIZE)

                bias = resolve_h1_market_bias(h1_store, h1_manifest, SYMBOL, ref_end, pair_id)
                bias_counts[bias.bias] = bias_counts.get(bias.bias, 0) + 1

                result = run_replay(
                    m15_candles, config, SYMBOL, pair_id, d, PIP_SIZE, PIP_VALUE_PER_LOT,
                    bias_result=bias, m1_candles=m1_candles,
                )
                steps_log.append({"date": str(d), "pair": pair_id, "regime": result.regime,
                                  "bias": bias.bias, "confidence": bias.confidence})

                if result.regime is None or result.regime == "UNKNOWN":
                    regime_counts["UNKNOWN"] = regime_counts.get("UNKNOWN", 0) + 1
                    continue
                regime_counts[result.regime] = regime_counts.get(result.regime, 0) + 1

                for rej in result.rejected_setups:
                    reason = rej.get("reason", "")
                    if reason in ("BIAS_MISSING", "BIAS_SYMBOL_MISMATCH", "BIAS_DIRECTION_MISMATCH"):
                        rejected_direction += 1
                    elif reason == "STOP_BELOW_FRICTION_FLOOR":
                        rejected_friction += 1
                    elif reason in (
                        "MAX_TOTAL_ENTRIES_PER_CAMPAIGN_REACHED", "SETUP_MAX_OCCURRENCES_REACHED",
                        "RISK_CAP_EXHAUSTED", "MIN_MEANINGFUL_RISK_UNAVAILABLE",
                        "CAMPAIGN_NOT_ACCEPTING_ENTRIES",
                    ):
                        rejected_alloc += 1

                for entry_dict in result.accepted_setups:
                    model = entry_dict["setup_model"]
                    key = _setup_key(model)
                    setup_counts[key] += 1
                    outcome = entry_dict["outcome"]
                    if outcome.get("terminal_state") == "AMBIGUOUS_SEQUENCE":
                        continue
                    if outcome.get("gross_R") is None or outcome.get("net_R") is None:
                        continue
                    trade_id = f"{pair_id}_{d}_{entry_dict['entry_time']}_{model}"
                    record = lifecycle_record(
                        entry_dict, trade_id=trade_id, strategy_id=STRATEGY_ID,
                        strategy_version=STRATEGY_VERSION, symbol=SYMBOL,
                    )
                    records.append(record)
                    geometry.append({
                        "trade_id": trade_id, "symbol": SYMBOL, "trading_date": str(d),
                        "session_pair": pair_id, "setup": key, "direction": entry_dict["direction"],
                        "entry": entry_dict["entry_price"], "initial_stop": entry_dict["stop_price"],
                        "initial_risk": record["initial_risk"],
                        "reference_high": reference.high, "reference_low": reference.low,
                        "gross_R": record["gross_R"], "friction_R": record["friction_R"],
                        "net_R": record["net_R"], "exit_reason": record["final_state"],
                    })
                    sample = ResolvedTradeSample(
                        source_record_id=trade_id,
                        source_path=CANONICAL_REPLAY_AUTHORITY,
                        strategy_id=STRATEGY_ID,
                        strategy_version=STRATEGY_VERSION,
                        symbol=SYMBOL, cycle=pair_id, resolved_at=entry_dict["entry_time"],
                        gross_R=record["gross_R"], net_R=record["net_R"],
                        cost_status=outcome["cost_status"], outcome=record["final_state"],
                    )
                    samples.append(sample)
                    session_samples[pair_id].append(sample)
                    direction_samples[entry_dict["direction"]].append(sample)
                    setup_samples[key].append(sample)

        return {
            "decision_cycles": decision_cycles, "bias_counts": bias_counts,
            "regime_counts": regime_counts, "setup_counts": setup_counts,
            "rejected_direction": rejected_direction, "rejected_friction": rejected_friction,
            "rejected_alloc": rejected_alloc, "records": records, "geometry": geometry,
            "samples": samples, "session_samples": session_samples,
            "direction_samples": direction_samples, "setup_samples": setup_samples,
            "steps_log": steps_log,
        }

    total_cycles = len(dates) * len(session_pairs)
    print(f"RUN_1: {total_cycles} cycles over {len(dates)} dates...", file=sys.stderr, flush=True)
    run1 = run_all_cycles("RUN_1")
    print("RUN_2 (determinism verification)...", file=sys.stderr, flush=True)
    run2 = run_all_cycles("RUN_2")

    # --- G8: determinism proof -----------------------------------------------------
    comp = compare_lifecycle_records(run1["records"], run2["records"])
    ph1 = population_hash(run1["records"])
    ph2 = population_hash(run2["records"])
    comp["population_hash_equal"] = ph1 == ph2
    comp["run_1_hash"] = ph1
    comp["run_2_hash"] = ph2
    comp["final_verdict"] = (
        "DETERMINISM_PASS"
        if comp["trade_count_equal"] and comp["occurrence_ids_equal"]
        and comp["occurrence_order_equal"] and comp["field_level_equal"]
        and comp["population_hash_equal"]
        else "BLOCKED_NONDETERMINISTIC_REPLAY"
    )
    if comp["final_verdict"] != "DETERMINISM_PASS":
        print(json.dumps(comp, indent=2), file=sys.stderr)
        raise SystemExit("BLOCKED_NONDETERMINISTIC_REPLAY")

    # --- G9: descriptive performance + decomposition --------------------------------
    overall = compute_trade_metrics(run1["samples"])
    by_setup = {k: compute_trade_metrics(v) for k, v in run1["setup_samples"].items()}
    by_direction = {k: compute_trade_metrics(v) for k, v in run1["direction_samples"].items()}
    by_session = {k: compute_trade_metrics(v) for k, v in run1["session_samples"].items()}
    # decompose by exit path (relevant exit paths, never weak subgroups removed)
    exit_buckets = {}
    for s in run1["samples"]:
        exit_buckets.setdefault(s.outcome, []).append(s)
    by_exit = {k: compute_trade_metrics(v) for k, v in sorted(exit_buckets.items())}

    diagnosis = _diagnose(overall)
    net_pf = _net_profit_factor(run1["samples"])

    # --- G11: economic gate contract (unsigned -> not evaluable) --------------------
    g11 = {
        "ECONOMIC_CONTRACT_STATUS": "PROPOSED / unsigned / inactive",
        "CANONICAL_VERDICT": "NOT_EVALUATED_UNSIGNED_CONTRACT",
        "NON_AUTHORITATIVE_DIAGNOSTIC": "NON_AUTHORITATIVE_DIAGNOSTIC_ONLY",
    }

    # --- G12: optimization admission ------------------------------------------------
    g12 = {
        "OPTIMIZATION_RUN": False, "NEW_CANDIDATE_CREATED": False, "PARAMETER_SEARCH": False,
        "OPTIMIZATION_ELIGIBLE": False,
    }

    generated_at = datetime.now(timezone.utc).isoformat()

    population = {
        "population_id": POPULATION_ID, "strategy_id": STRATEGY_ID,
        "strategy_version": STRATEGY_VERSION, "dataset_id": DATASET_ID,
        "dataset_fingerprint": identity["DATASET_FINGERPRINT"],
        "preregistration_hash": identity["PREREGISTRATION_HASH"],
        "population_count": len(run1["records"]),
        "population_sha256": ph1,
        "generated_at": generated_at,
        "canonical_replay_authority": CANONICAL_REPLAY_AUTHORITY,
        "config_hash": config_hash,
        "metadata_manifest": str(H1_MANIFEST_PATH.relative_to(REPO_ROOT)),
        "metadata_manifest_hash": metadata_manifest_hash,
        "git_commit": git_commit,
        "occurrences": run1["records"],
        "occurrence_geometry": run1["geometry"],
    }

    manifest = {
        "population_id": POPULATION_ID, "strategy_id": STRATEGY_ID,
        "strategy_version": STRATEGY_VERSION, "dataset_id": DATASET_ID,
        "dataset_fingerprint": identity["DATASET_FINGERPRINT"],
        "preregistration_hash": identity["PREREGISTRATION_HASH"],
        "population_count": len(run1["records"]),
        "population_sha256": ph1,
        "generated_at": generated_at,
        "canonical_replay_authority": CANONICAL_REPLAY_AUTHORITY,
        "config_hash": config_hash,
        "metadata_manifest": str(H1_MANIFEST_PATH.relative_to(REPO_ROOT)),
        "metadata_manifest_hash": metadata_manifest_hash,
        "coverage": {
            "development_decision_interval": dev_interval,
            "effective_start": str(dates[0]), "effective_end": str(dates[-1]),
            "effective_days": len(dates), "decision_cycles": run1["decision_cycles"],
        },
    }

    determinism_evidence = {
        "population_id": POPULATION_ID, "generated_at": generated_at,
        "note": "RUN_2 is determinism verification only; it is NOT a second authoritative population.",
        "comparison": comp,
    }

    performance = {
        "population_id": POPULATION_ID, "generated_at": generated_at,
        "overall": _metrics_dict(overall),
        "net_profit_factor": net_pf,
        "by_setup": {k: _metrics_dict(v) for k, v in by_setup.items()},
        "by_direction": {k: _metrics_dict(v) for k, v in by_direction.items()},
        "by_session": {k: _metrics_dict(v) for k, v in by_session.items()},
        "by_exit_path": {k: _metrics_dict(v) for k, v in by_exit.items()},
        "setup_counts": run1["setup_counts"],
        "bias_counts": run1["bias_counts"],
        "regime_counts": run1["regime_counts"],
        "rejections": {
            "direction_blocked": run1["rejected_direction"],
            "friction_rejected": run1["rejected_friction"],
            "alloc_rejected": run1["rejected_alloc"],
        },
        "failure_diagnosis": diagnosis,
    }

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / "G2_POPULATION_V1.json").write_text(
        json.dumps(population, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    (ARTIFACT_DIR / "G2_POPULATION_MANIFEST_V1.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    (ARTIFACT_DIR / "G2_DETERMINISM_V1.json").write_text(
        json.dumps(determinism_evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    (ARTIFACT_DIR / "G2_DESCRIPTIVE_PERFORMANCE_V1.json").write_text(
        json.dumps(performance, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )

    report = {
        "SSC_V1_0_1_SVOS_G2_HISTORICAL_REPLAY_STATUS": {
            "REPOSITORY": {"HEAD_BEFORE": git_commit, "HEAD_AFTER": git_commit, "COMMIT": git_commit,
                            "FOREIGN_WIP_STAGED": "NONE (foreign Large-SMC/BTC/proposal-ledger WIP left unstaged)"},
            "AUTHORITY": authority,
            "DATASET": {
                "DATASET_ID": DATASET_ID, "H1_SHA256": identity["H1_SHA256"],
                "M15_SHA256": identity["M15_SHA256"], "M1_SHA256": identity["M1_SHA256"],
                "DATASET_FINGERPRINT": identity["DATASET_FINGERPRINT"],
                "PREREGISTRATION_HASH": identity["PREREGISTRATION_HASH"],
                "METADATA_BINDING": "PASS", "WARMUP_CONTAINMENT": "PASS",
            },
            "REPLAY": {
                "POPULATION_ID": POPULATION_ID, "RESEARCH_REPLAY_COUNT": 1,
                "OCCURRENCE_COUNT": len(run1["records"]),
                "OCCURRENCE_POPULATION_HASH": ph1, "DETERMINISM": "PASS",
            },
            "PERFORMANCE": {
                "N": overall.sample_size, "WINS": overall.wins, "LOSSES": overall.losses,
                "BREAKEVEN": overall.breakevens, "GROSS_R": overall.gross_total_R,
                "FRICTION_R": (overall.gross_total_R - overall.net_total_R)
                if isinstance(overall.net_total_R, float) else None,
                "NET_R": overall.net_total_R, "GROSS_EXPECTANCY_R": overall.gross_expectancy_R,
                "NET_EXPECTANCY_R": overall.net_expectancy_R, "GROSS_PF": overall.profit_factor,
                "NET_PF": net_pf, "MAX_DRAWDOWN_R": overall.max_drawdown_R,
                "WIN_RATE": overall.win_rate,
            },
            "SETUPS": {k: _metrics_dict(v)["N"] for k, v in by_setup.items()},
            "SESSIONS": {k: _metrics_dict(v)["N"] for k, v in by_session.items()},
            "DIRECTIONS": {k: _metrics_dict(v)["N"] for k, v in by_direction.items()},
            "FAILURE_DIAGNOSIS": diagnosis,
            "G2": {"STATUS": "POPULATION_FROZEN", "EVIDENCE_FROZEN": True},
            "G3": {
                "ECONOMIC_CONTRACT_STATUS": g11["ECONOMIC_CONTRACT_STATUS"],
                "CANONICAL_VERDICT": g11["CANONICAL_VERDICT"],
                "NON_AUTHORITATIVE_DIAGNOSTIC": g11["NON_AUTHORITATIVE_DIAGNOSTIC"],
            },
            "OPTIMIZATION": {"ELIGIBLE": False, "RUN": False, "NEW_CANDIDATE_CREATED": False},
            "PROTECTED_DATA": {"CONFIRMATION_ACCESSED": False, "HOLDOUT_ACCESSED": False,
                                "OOS_ACCESSED": False},
            "H2": {"CONSUMED": False, "MODIFIED": False},
            "FORWARD": {"VIRTUAL_BROKER_STARTED": False, "FORWARD_STARTED": False},
            "EXECUTION": {"BROKER_MUTATION": False, "DEMO_ORDER": False, "LIVE_ORDER": False,
                           "EXECUTION_AUTHORITY_CHANGED": False},
            "FINAL_STATUS": "G2_POPULATION_FROZEN",
            "NEXT_SINGLE_ACTION": "None (one-shot population generated; G3 remains NOT_EVALUATED_UNSIGNED_CONTRACT)",
        }
    }
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
