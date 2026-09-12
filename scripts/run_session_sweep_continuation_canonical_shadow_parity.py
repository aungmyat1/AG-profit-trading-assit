"""AG_PLAN2_GOLDEN_STRATEGY_CANONICAL_OBSERVATION_MIGRATION_V1 -- dual-path shadow
parity + golden replay reproduction for ST_SESSION_SWEEP_CONTINUATION_V1.

Runs the LEGACY path (h1_bias.resolve_h1_market_bias -> run_replay, exactly as
scripts/run_first_canonical_session_sweep_continuation_replay.py already does) and the
CANONICAL SHADOW path (session_sweep_continuation.canonical_consumer.
run_canonical_shadow_cycle: the same bias resolution wrapped in a MarketObservation,
unwrapped, and passed through the same run_replay) side by side against the SAME
loaded data, once, to avoid a second expensive full data load/replay.

Writes artifacts/backtests/session_sweep_continuation/PLAN2_CANONICAL_OBSERVATION_
PARITY_20260911.json -- a SEPARATE artifact; FIRST_CANONICAL_REPLAY_20260911.json (the
frozen golden baseline) is never opened for writing by this script.

RESEARCH ONLY. Places no orders, changes no strategy parameter, no lifecycle field.
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from historical_replay.candle_store import HistoricalCandleStore  # noqa: E402
from historical_replay.mt5_export_loader import load_mt5_export_csv  # noqa: E402
from historical_replay.symbol_metadata_manifest import (  # noqa: E402
    compute_dataset_fingerprint,
    load_symbol_metadata_manifest,
    validate_manifest_for_dataset,
)
from performance.calculator import compute_trade_metrics  # noqa: E402
from performance.models import ResolvedTradeSample  # noqa: E402
from session_sweep_continuation.canonical_consumer import run_canonical_shadow_cycle  # noqa: E402
from session_sweep_continuation.config import load_config  # noqa: E402
from session_sweep_continuation.h1_bias import resolve_h1_market_bias  # noqa: E402
from session_sweep_continuation.replay import run_replay  # noqa: E402
from session_sweep_continuation.sessions import session_windows_from_config  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
SYMBOL = "EURUSD"
PIP_SIZE = 0.0001
PIP_VALUE_PER_LOT = 10.0
STRUCTURE_WARMUP_H1_BARS = 1000

H1_CSV = Path(r"D:\EURUSD_H1_202501020000_202607310000.csv")
M15_CSV = Path(r"D:\EURUSD_M15_202501020000_202606192345.csv")
M1_CSV = Path(r"D:\EURUSD_M1_202605180946_202607312356.csv")

H1_MANIFEST_PATH = REPO_ROOT / "config" / "historical_datasets" / "EURUSD_H1_symbol_metadata.yaml"

EXPECTED_SHA256 = {
    H1_CSV: "f1b456e4b50215ad23370949f15faaa8548f9c03053a20d8974d6e9fd480a060",
    M15_CSV: "7f7502938862f4a3779f018caab468fe4445a4d8c676c8393dc29ca57fc43a65",
    M1_CSV: "55422a1ccdf4ca76fd25451fbf849d559bed45d839891a3ada7a37f9f7dd6a23",
}


def _git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except Exception:
        return "UNKNOWN"


def _verify_fingerprint(path: Path) -> str:
    if not path.exists():
        raise SystemExit(f"DATASET_MISSING: {path}")
    actual = compute_dataset_fingerprint(path).split("sha256:", 1)[1]
    expected = EXPECTED_SHA256[path]
    if actual != expected:
        raise SystemExit(f"FINGERPRINT_MISMATCH: {path}: actual={actual} expected={expected}")
    return actual


def _effective_date_range(h1_report, m15_report, m1_report, config: dict):
    windows = session_windows_from_config(config)
    raw_start = max(m15_report.start_utc, m1_report.start_utc, h1_report.start_utc)
    raw_end = min(m15_report.end_utc, m1_report.end_utc, h1_report.end_utc)
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
        d = d + timedelta(days=1)
    return covered


def _aggregate(samples):
    if not samples:
        return None
    return compute_trade_metrics(samples)


def main():
    config = load_config(repo_root=str(REPO_ROOT))
    git_commit = _git_commit()

    _verify_fingerprint(H1_CSV)
    _verify_fingerprint(M15_CSV)
    _verify_fingerprint(M1_CSV)

    h1_manifest = load_symbol_metadata_manifest(H1_MANIFEST_PATH)
    if h1_manifest.authority != "OWNER_APPROVED_DATASET_MANIFEST":
        raise SystemExit(f"H1_METADATA_NOT_AUTHORIZED: authority={h1_manifest.authority!r}")
    validate_manifest_for_dataset(h1_manifest, H1_CSV, SYMBOL)

    print("Loading H1...", file=sys.stderr)
    h1_candles, h1_report = load_mt5_export_csv(str(H1_CSV), SYMBOL, "H1")
    print("Loading M15...", file=sys.stderr)
    m15_candles, m15_report = load_mt5_export_csv(str(M15_CSV), SYMBOL, "M15")
    print("Loading M1...", file=sys.stderr)
    m1_candles, m1_report = load_mt5_export_csv(str(M1_CSV), SYMBOL, "M1")

    h1_store = HistoricalCandleStore()
    h1_store.load_series(SYMBOL, "H1", h1_candles)

    dates = _effective_date_range(h1_report, m15_report, m1_report, config)
    if not dates:
        raise SystemExit("EFFECTIVE_REPLAY_WINDOW_EMPTY")

    session_pairs = [p["pair_id"] for p in config.get("session_pairs", ())]
    windows = session_windows_from_config(config)

    decision_cycles = 0
    semantic_mismatches = []
    regime_observation_mismatches = []
    legacy_samples = []
    canonical_samples = []
    input_fingerprint_samples = []

    print(f"Running dual-path across {len(dates)} dates x {len(session_pairs)} session pairs...", file=sys.stderr)

    for d in dates:
        for pair_id in session_pairs:
            decision_cycles += 1
            ref_end = windows[pair_id]["reference"].bounds_for_date(d)[1]

            # LEGACY PATH (byte-identical to the golden script)
            legacy_bias = resolve_h1_market_bias(h1_store, h1_manifest, SYMBOL, ref_end, pair_id)
            legacy_result = run_replay(
                m15_candles, config, SYMBOL, pair_id, d, PIP_SIZE, PIP_VALUE_PER_LOT,
                bias_result=legacy_bias, m1_candles=m1_candles,
            )

            # CANONICAL SHADOW PATH
            cycle = run_canonical_shadow_cycle(
                h1_store=h1_store, manifest=h1_manifest, m15_candles=m15_candles, config=config,
                symbol=SYMBOL, session_pair_id=pair_id, trading_date=d, decision_time=ref_end,
                pip_size=PIP_SIZE, pip_value_per_lot=PIP_VALUE_PER_LOT, m1_candles=m1_candles,
            )
            canonical_result = cycle.replay_result

            if len(input_fingerprint_samples) < 3:
                bias_obs = next((o for o in cycle.observations if o.skill_id == "H1_MARKET_BIAS_V1"), None)
                regime_obs = next((o for o in cycle.observations if o.skill_id == "M15_MARKET_REGIME_V1"), None)
                input_fingerprint_samples.append({
                    "date": str(d), "pair": pair_id,
                    "bias_input_fingerprint": bias_obs.input_fingerprint if bias_obs else None,
                    "regime_input_fingerprint": regime_obs.input_fingerprint if regime_obs else None,
                })

            if legacy_result.regime != canonical_result.regime:
                regime_observation_mismatches.append({
                    "date": str(d), "pair": pair_id,
                    "legacy_regime": legacy_result.regime, "canonical_regime": canonical_result.regime,
                })

            # SEMANTIC_PARITY fields (P9): regime, campaign presence/direction/status,
            # accepted/rejected setup counts and identities.
            legacy_view = {
                "regime": legacy_result.regime,
                "campaign_direction": legacy_result.campaign.direction if legacy_result.campaign else None,
                "campaign_status": legacy_result.campaign.status.value if legacy_result.campaign else None,
                "accepted_count": len(legacy_result.accepted_setups),
                "rejected_count": len(legacy_result.rejected_setups),
                "accepted_entry_prices": [a["entry_price"] for a in legacy_result.accepted_setups],
                "accepted_stop_prices": [a["stop_price"] for a in legacy_result.accepted_setups],
                "accepted_net_R": [a["outcome"].get("net_R") for a in legacy_result.accepted_setups],
            }
            canonical_view = {
                "regime": canonical_result.regime,
                "campaign_direction": canonical_result.campaign.direction if canonical_result.campaign else None,
                "campaign_status": canonical_result.campaign.status.value if canonical_result.campaign else None,
                "accepted_count": len(canonical_result.accepted_setups),
                "rejected_count": len(canonical_result.rejected_setups),
                "accepted_entry_prices": [a["entry_price"] for a in canonical_result.accepted_setups],
                "accepted_stop_prices": [a["stop_price"] for a in canonical_result.accepted_setups],
                "accepted_net_R": [a["outcome"].get("net_R") for a in canonical_result.accepted_setups],
            }
            if legacy_view != canonical_view:
                semantic_mismatches.append({"date": str(d), "pair": pair_id, "legacy": legacy_view, "canonical": canonical_view})

            for entry_dict in legacy_result.accepted_setups:
                outcome = entry_dict["outcome"]
                if outcome["terminal_state"] == "AMBIGUOUS_SEQUENCE" or outcome["gross_R"] is None:
                    continue
                legacy_samples.append(ResolvedTradeSample(
                    source_record_id=f"L_{pair_id}_{d}_{entry_dict['entry_time']}_{entry_dict['setup_model']}",
                    source_path="legacy_dual_path", strategy_id="ST_SESSION_SWEEP_CONTINUATION_V1",
                    strategy_version=config.get("version", "1.0.0"),
                    symbol=SYMBOL, cycle=pair_id, resolved_at=entry_dict["entry_time"],
                    gross_R=outcome["gross_R"], net_R=outcome["net_R"],
                    cost_status=outcome["cost_status"], outcome=outcome["terminal_state"],
                ))
            for entry_dict in canonical_result.accepted_setups:
                outcome = entry_dict["outcome"]
                if outcome["terminal_state"] == "AMBIGUOUS_SEQUENCE" or outcome["gross_R"] is None:
                    continue
                canonical_samples.append(ResolvedTradeSample(
                    source_record_id=f"C_{pair_id}_{d}_{entry_dict['entry_time']}_{entry_dict['setup_model']}",
                    source_path="canonical_dual_path", strategy_id="ST_SESSION_SWEEP_CONTINUATION_V1",
                    strategy_version=config.get("version", "1.0.0"),
                    symbol=SYMBOL, cycle=pair_id, resolved_at=entry_dict["entry_time"],
                    gross_R=outcome["gross_R"], net_R=outcome["net_R"],
                    cost_status=outcome["cost_status"], outcome=outcome["terminal_state"],
                ))

    legacy_metrics = _aggregate(legacy_samples)
    canonical_metrics = _aggregate(canonical_samples)

    report = {
        "report_id": "AG_PLAN2_CANONICAL_OBSERVATION_PARITY",
        "migration_slice": "AG_PLAN2_GOLDEN_CANONICAL_COMPLETION_V1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit,
        "strategy_id": "ST_SESSION_SWEEP_CONTINUATION_V1",
        "strategy_version": "1.0.0",
        "references_frozen_baseline": "artifacts/backtests/session_sweep_continuation/FIRST_CANONICAL_REPLAY_20260911.json",
        "observations": {
            "MARKET_BIAS": "FULLY_INJECTED",
            "MARKET_REGIME": "FULLY_INJECTED",
            "remaining_coupling_debt": "NONE",
        },
        "decision_cycles": decision_cycles,
        "semantic_parity": {
            "fields_compared": ["regime", "campaign_direction", "campaign_status", "accepted_count",
                                 "rejected_count", "accepted_entry_prices", "accepted_stop_prices", "accepted_net_R"],
            "mismatches": semantic_mismatches,
            "matches": decision_cycles - len(semantic_mismatches),
            "status": "PASS" if not semantic_mismatches else "FAIL",
        },
        "regime_injection_verification": {
            "description": "legacy path's internally-computed regime (classify_regime called directly) vs canonical path's injected regime_result (unwrapped from the MARKET_REGIME MarketObservation, passed into run_replay's regime_result parameter)",
            "mismatches": regime_observation_mismatches,
            "matches": decision_cycles - len(regime_observation_mismatches),
            "status": "PASS" if not regime_observation_mismatches else "FAIL",
        },
        "input_fingerprint_samples": input_fingerprint_samples,
        "legacy_sample_size": len(legacy_samples),
        "canonical_sample_size": len(canonical_samples),
        "legacy_metrics": asdict(legacy_metrics) if legacy_metrics else None,
        "canonical_metrics": asdict(canonical_metrics) if canonical_metrics else None,
        "economic_parity": "PASS" if (legacy_metrics and canonical_metrics and asdict(legacy_metrics) == asdict(canonical_metrics)) else "FAIL",
    }
    print(json.dumps(report, indent=2, default=str))

    out_path = REPO_ROOT / "artifacts" / "backtests" / "session_sweep_continuation" / "PLAN2_CANONICAL_OBSERVATION_PARITY_20260911.json"
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"Written: {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
