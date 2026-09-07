"""AG_EGSVF_V1_CROSS_STRATEGY_DETERMINISM_EVIDENCE_RECONCILIATION -- immutable
determinism evidence generator.

Drives each strategy's real, offline, version-bound semantic pipeline over a fixed
fixture N times, hashes the canonical semantic payload of each run with the existing
post_asian_pilot.fingerprint.fingerprint() serializer (sort_keys, stable separators,
sha256 -- not a new serializer), and writes one immutable evidence record per strategy
under artifacts/validation_evidence/determinism/. This exists so
validation_framework adapters never have to (a) re-run an expensive pipeline (the
Large-SMC case takes ~1 minute even against a cached fixture) just to answer
"is DETERMINISM proven", or (b) infer PASS merely from a test file's existence -- the
adapter reads this artifact's own recorded `result` and `payload_digests_equal` fields,
which are only ever set by an actual execution captured here.

Evidence is permanently bound to (strategy_id, semantic_version) -- see
_write_record's filename and the `strategy_version` field; an adapter must never read
a record whose strategy_version does not match the strategy's current authoritative
version (strategies/<ID>.yaml).

Excluded (documented, non-semantic) fields -- see NORMALIZATION_CONTRACT below.
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Sequence

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))
sys.path.insert(0, str(_REPO_ROOT / "tests"))

from post_asian_pilot.fingerprint import fingerprint  # noqa: E402

FRAMEWORK_ID = "AG_EGSVF_V1"
EVIDENCE_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "validation_evidence" / "determinism"

NORMALIZATION_CONTRACT = (
    "Canonical semantic payload = the full dataclass output of the pipeline call "
    "(TradeSignal+PostAsianDecision for FX; SetupState+BTCSweepResearchProposal for "
    "BTC; tuple of LargeSMCResearchDecision for Large-SMC), serialized via "
    "post_asian_pilot.fingerprint.fingerprint() (sort_keys=True, stable separators, "
    "default=str for datetimes). No field is excluded -- every run used a fixed, "
    "explicitly-injected timestamp/session context (no wall-clock, no randomness, no "
    "network), so there is no run-specific field (generated_at/run_id/etc.) to strip."
)


def _to_jsonable(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: _to_jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    return obj


def _git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parent.parent).decode().strip()


def _write_record(strategy_id: str, strategy_version: str, fixture_ref: str, test_ref: str, runs: int, digests: Sequence[str]) -> Path:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    result = "PASS" if len(set(digests)) == 1 else "FAIL"
    record = {
        "framework_id": FRAMEWORK_ID,
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "evaluation_head": _git_head(),
        "fixture_ref": fixture_ref,
        "test_ref": test_ref,
        "runs": runs,
        "normalization_contract": NORMALIZATION_CONTRACT,
        "result": result,
        "payload_digests": list(digests),
        "payload_digests_equal": len(set(digests)) == 1,
        "evaluated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    ts = record["evaluated_at"].replace(":", "").replace("-", "")
    path = EVIDENCE_DIR / f"{strategy_id}_{strategy_version}_{ts}.json"
    suffix = 1
    while path.exists():
        path = EVIDENCE_DIR / f"{strategy_id}_{strategy_version}_{ts}-{suffix}.json"
        suffix += 1
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return path


def generate_fx_evidence(runs: int = 3) -> Path:
    from strategy_engine.engine import evaluate as evaluate_strategy
    from strategy_engine.loader import load_strategy
    from strategy_engine.session import Candle
    from post_asian_pilot.decision import map_trade_signal_to_decision

    UTC = dt.timezone.utc
    strategy = load_strategy("strategies/ST_ASIAN_SWEEP_5R_V1.yaml")
    session_date = dt.date(2026, 1, 5)
    session_candles = [
        Candle(dt.datetime(2026, 1, 5, 0, 0, tzinfo=UTC), 1.1000, 1.1050, 1.0950, 1.1010),
        Candle(dt.datetime(2026, 1, 5, 0, 15, tzinfo=UTC), 1.1010, 1.1040, 1.0960, 1.1005),
    ]
    sweep_candle = Candle(dt.datetime(2026, 1, 5, 6, 0, tzinfo=UTC), 1.1005, 1.1060, 1.1000, 1.1048)

    digests = []
    for _ in range(runs):
        signal = evaluate_strategy(strategy, "ASIAN_LONDON", "EURUSD", session_date, session_candles, 2, [sweep_candle])
        decision = map_trade_signal_to_decision(
            signal,
            session_snapshot_id="DETERMINISM-EVIDENCE-SNAPSHOT",
            evaluation_time=dt.datetime(2026, 1, 5, 7, 0, tzinfo=UTC),
            window_end_utc=dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC),
        )
        payload = {"signal": _to_jsonable(signal), "decision": _to_jsonable(decision)}
        digests.append(fingerprint(payload))

    return _write_record(
        strategy_id="ST_ASIAN_SWEEP_5R_V1",
        strategy_version=strategy.version,
        fixture_ref="scripts/generate_determinism_evidence.py::generate_fx_evidence (inline fixed candle fixture, same shape as tests/test_session_router.py::test_range_with_sweep_routes_to_entry_2)",
        test_ref="tests/test_post_asian_pilot.py::test_fx_full_pipeline_is_deterministic_for_fixed_fixture",
        runs=runs,
        digests=digests,
    )


def generate_btc_evidence(runs: int = 3, tmp_dir: str = None) -> Path:
    """Reuses tests/test_btc_sweep_research_pipeline.py's own fixture builders
    (_build_fixture/_FixtureFeed/_fresh_runtime_and_guards/_run) rather than
    re-deriving the H1/M5 candle-shape construction here -- same evidence source the
    passing test itself exercises, not a second implementation of it."""
    import tempfile

    import test_btc_sweep_research_pipeline as btc_test

    strategy_version = "2.0.0"  # strategies/ST_LIQUIDITY_SWEEP_RETEST_V1.yaml:4
    h1, m5 = btc_test._build_fixture([(13, 30)])

    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td)
        digests = []
        for i in range(runs):
            feed = btc_test._FixtureFeed(h1, m5)
            runtime, ledger, daily_loss_guard, open_position_guard = btc_test._fresh_runtime_and_guards(tmp_path, suffix=f"_ev{i}")
            report = btc_test._run(feed, runtime, ledger, daily_loss_guard, open_position_guard)
            payload = {
                "occurrences": [
                    {"setup_state": _to_jsonable(o.setup_state), "proposal": _to_jsonable(o.proposal), "ledger_new_row": o.ledger_new_row}
                    for o in report.occurrences
                ],
                "container_state": _to_jsonable(report.container_state),
            }
            digests.append(fingerprint(payload))

    return _write_record(
        strategy_id="ST_LIQUIDITY_SWEEP_RETEST_V1",
        strategy_version=strategy_version,
        fixture_ref="tests/test_btc_sweep_research_pipeline.py::_build_fixture([(13, 30)]) (cached, offline H1/M5 candles, no network)",
        test_ref="tests/test_btc_sweep_research_pipeline.py::test_btc_research_pipeline_is_deterministic_for_cached_fixture",
        runs=runs,
        digests=digests,
    )


def generate_large_smc_evidence(runs: int = 2) -> Path:
    """Reuses tests/test_golden_vertical_slice.py's own module-scoped dataset/store
    fixtures (the frozen golden two-stage fixture + cached historical CSV store) --
    building `store` here calls the same CSV-load/resample path the test module's own
    pytest fixture does, at the same one-time cost."""
    import datetime as _dt

    import test_golden_vertical_slice as smc_test
    from historical_replay.data_source_patch import historical_data_context
    from large_smc_research.engine import LargeSMCResearchEngine

    strategy_version = "1.0.6"  # strategies/ST_LARGE_SMC_V1.yaml:4
    dataset = smc_test.load_stage1_dataset(smc_test.EVENTS_PATH, smc_test.LIQUIDITY_PATH)
    golden = json.loads(Path(smc_test.GOLDEN_FIXTURE_PATH).read_text(encoding="utf-8"))
    case = next(c for c in golden["cases"] if c["case_id"] == "CASE_A_E1M3_RESTORED_READY")
    as_of = _dt.datetime.fromisoformat(case["evaluation_timestamp"])

    candles, rep = smc_test.load_mt5_export_csv(smc_test.CSV_PATH, "EURUSD", "M5")
    store = smc_test.HistoricalCandleStore()
    store.load_series("EURUSD", "M5", candles)
    for tf in ("M15", "H1"):
        store.load_series("EURUSD", tf, smc_test.resample(candles, "M5", tf))
    for tf in ("H4", "D1"):
        store.load_series("EURUSD", tf, smc_test.resample_broker_aligned(candles, rep.broker_times, "M5", tf))

    engine = LargeSMCResearchEngine()
    digests = []
    for _ in range(runs):
        with historical_data_context(store, as_of):
            decisions = engine.evaluate("EURUSD", as_of, dataset)
        digests.append(fingerprint([_to_jsonable(d) for d in decisions]))

    return _write_record(
        strategy_id="ST_LARGE_SMC_V1",
        strategy_version=strategy_version,
        fixture_ref=f"{smc_test.GOLDEN_FIXTURE_PATH} + {smc_test.EVENTS_PATH} (frozen golden two-stage fixture, CASE_A_E1M3_RESTORED_READY)",
        test_ref="tests/test_golden_vertical_slice.py::test_large_smc_discovery_is_deterministic_for_golden_fixture",
        runs=runs,
        digests=digests,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", choices=["fx", "btc", "large_smc", "all"], default="all")
    args = parser.parse_args()

    generators = {
        "fx": generate_fx_evidence,
        "btc": generate_btc_evidence,
        "large_smc": generate_large_smc_evidence,
    }
    targets = generators if args.strategy == "all" else {args.strategy: generators[args.strategy]}
    for name, gen in targets.items():
        path = gen()
        print(f"{name}: wrote {path}")
