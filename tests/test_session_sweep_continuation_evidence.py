from session_sweep_continuation.config import compute_config_hash, load_config
from session_sweep_continuation.evidence import build_canonical_setup_record, compute_dataset_hash, resolve_git_commit
from session_sweep_continuation.friction import FrictionEstimate
from session_sweep_continuation.stop_engine import StopResult
from strategy_engine.session.candles import Candle
from datetime import datetime, timezone


def test_config_hash_deterministic_and_changes_with_content():
    cfg = load_config(repo_root=".")
    h1 = compute_config_hash(cfg)
    h2 = compute_config_hash(cfg)
    assert h1 == h2
    mutated = dict(cfg)
    mutated["fvg"] = dict(cfg["fvg"])
    mutated["fvg"]["min_pips"] = 999.0
    assert compute_config_hash(mutated) != h1


def test_dataset_hash_deterministic():
    candles = [Candle(datetime(2026, 9, 10, 7, 0, tzinfo=timezone.utc), 1.1, 1.101, 1.099, 1.1005)]
    h1 = compute_dataset_hash(candles)
    h2 = compute_dataset_hash(candles)
    assert h1 == h2
    assert len(h1) == 64


def test_canonical_record_includes_required_identity_fields():
    cfg = load_config(repo_root=".")
    config_hash = compute_config_hash(cfg)
    candles = [Candle(datetime(2026, 9, 10, 7, 0, tzinfo=timezone.utc), 1.1, 1.101, 1.099, 1.1005)]
    dataset_hash = compute_dataset_hash(candles)
    git_commit = resolve_git_commit(".")

    stop_result = StopResult(
        accepted=True, reason="OK", entry_price=1.1000, anchor_price=1.0950, anchor_source="S1_SWEEP_EXTREME",
        structural_stop_distance=0.0006, atr_buffer=0.0002, friction_floor=0.00045,
        final_stop_distance=0.0006, stop_price=1.0994,
    )
    friction = FrictionEstimate(
        symbol="EURUSD", spread_pips=1.0, commission_pips=0.2, slippage_pips=0.3,
        total_pips=1.5, total_price=0.00015, total_cash=1.5, total_r=None, cost_status="MODELED",
    )

    record = build_canonical_setup_record(
        application_release="TEST_RELEASE",
        campaign_id="EURUSD-ASIAN_LONDON-20260910-LONG",
        setup_model="S1_SWEEP_REVERSAL",
        symbol="EURUSD",
        session_pair="ASIAN_LONDON",
        direction="LONG",
        entry_time="2026-09-10T07:00:00+00:00",
        entry_price=1.1000,
        stop_result=stop_result,
        targets={"partial": 1.1030, "runner_r": 3.0},
        risk_pct=0.40,
        regime="RANGE",
        bos_evidence={},
        fvg_evidence={},
        confirmation_score=None,
        friction=friction,
        config_hash=config_hash,
        dataset_hash=dataset_hash,
        git_commit=git_commit,
    )

    d = record.to_dict()
    for field in ("strategy_id", "version", "application_release", "campaign_id", "setup_model",
                  "symbol", "session_pair", "direction", "decision_timeframe", "entry_time",
                  "entry_price", "stop_price", "stop_distance", "targets", "risk_pct", "regime",
                  "bos_evidence", "fvg_evidence", "confirmation_score", "transaction_friction",
                  "config_hash", "dataset_hash", "git_commit"):
        assert field in d, field
    assert d["strategy_id"] == "ST_SESSION_SWEEP_CONTINUATION_V1"
    assert d["version"] == "1.0.1"  # session_sweep_continuation.STRATEGY_VERSION, post SSC_V1_0_1 rollover
    assert d["demo_eligible"] is False
    assert d["demo_authorized"] is False
    assert d["lifecycle_stage"] == "OFFLINE_RESEARCH"
    # JSON round-trips deterministically
    assert record.to_json() == record.to_json()
