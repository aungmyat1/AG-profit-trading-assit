"""Tests for the SSC v1.0.1 G2 H1-warmup remediation (DEV_002).

Proves: DEV_001 fails the canonical H1 warmup requirement, DEV_002 passes it, warmup
cannot generate occurrences, the DEVELOPMENT decision interval is unchanged, M15/M1
development evidence is byte-identical, the protected-data firewall holds, and the
historical/forward strategy authority remains identical. No replay executed.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEV001_RAW = REPO / "data" / "research" / "ssc_fresh_dev" / "SSC_V1_0_1_G2_DEV_001" / "raw"
DEV002_RAW = REPO / "data" / "research" / "ssc_fresh_dev" / "SSC_V1_0_1_G2_DEV_002" / "raw"
PREREG = json.load(open(REPO / "artifacts" / "validation" / "ST_SESSION_SWEEP_CONTINUATION_V1" / "SSC_V1_0_1_G2_DEV_002" / "G2_POPULATION_PREREGISTRATION.json", encoding="utf-8"))

FIRST_DECISION = datetime(2026, 6, 22, 6, 0, tzinfo=timezone.utc)
REQUIRED = 1000


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _closed_h1(path: Path, as_of: datetime) -> int:
    from historical_replay.utc_export_csv_loader import load_utc_export_csv
    from historical_replay.warmup_readiness import closed_h1_bar_count

    candles, report = load_utc_export_csv(str(path), "EURUSD", "H1")
    assert report.normalized_timezone == "UTC"
    return closed_h1_bar_count(candles, as_of)


def test_dev001_fails_warmup():
    assert _closed_h1(DEV001_RAW / "EURUSD_H1.csv", FIRST_DECISION) < REQUIRED


def test_dev002_passes_warmup():
    assert _closed_h1(DEV002_RAW / "EURUSD_H1.csv", FIRST_DECISION) >= REQUIRED


def test_dev002_passes_every_decision():
    from historical_replay.utc_export_csv_loader import load_utc_export_csv
    from historical_replay.warmup_readiness import closed_h1_bar_count

    candles, _ = load_utc_export_csv(str(DEV002_RAW / "EURUSD_H1.csv"), "EURUSD", "H1")
    d = datetime(2026, 6, 22, tzinfo=timezone.utc)
    end = datetime(2026, 8, 3, tzinfo=timezone.utc)
    import datetime as _dt
    while d < end:
        for hour in (6, 11):  # ASIAN_LONDON ref_end 06:00, LONDON_NEWYORK ref_end 11:00
            ref_end = d.replace(hour=hour)
            assert closed_h1_bar_count(candles, ref_end) >= REQUIRED
        d += _dt.timedelta(days=1)


def test_m15_m1_unchanged_from_parent():
    for tf in ("M15", "M1"):
        assert _sha(DEV002_RAW / f"EURUSD_{tf}.csv") == _sha(DEV001_RAW / f"EURUSD_{tf}.csv")


def test_dev001_dev_segment_preserved():
    dev001_h1 = [l for l in (DEV001_RAW / "EURUSD_H1.csv").read_text().splitlines()[1:] if l]
    dev002_h1 = [l for l in (DEV002_RAW / "EURUSD_H1.csv").read_text().splitlines()[1:] if l]
    # DEV_002 must END with exactly DEV_001's H1 development segment (byte-identical tail)
    assert dev002_h1[-len(dev001_h1):] == dev001_h1


def test_warmup_cannot_generate_occurrences():
    w = PREREG["warmup_role"]
    assert w["WARMUP_CONTEXT_ONLY"] is True
    assert w["may_generate_decision_occurrence"] is False
    assert w["may_contribute_trade"] is False
    assert w["may_contribute_pnl"] is False
    assert w["may_contribute_economic_sample_N"] is False
    assert w["may_extend_development_decision_window"] is False
    assert w["may_be_used_for_optimization"] is False


def test_decision_interval_unchanged():
    assert PREREG["development_decision_interval"] == {
        "start": "2026-06-21T21:00:00Z",
        "end": "2026-08-02T23:59:59Z",
    }


def test_protected_data_clear():
    assert PREREG["protected_data_clear"] is True
    assert PREREG["prior_consumption"] == "NONE"
    assert PREREG["replay_count"] == 0
    assert PREREG["outcome_not_evaluated"] is True


def test_historical_forward_authority_identical():
    from svos.adapters.ssc import forward_decision_entrypoint, historical_replay_entrypoint

    assert historical_replay_entrypoint() is forward_decision_entrypoint()


def test_preregistration_hash_binds():
    body = {k: v for k, v in PREREG.items() if k != "preregistration_hash"}
    import hashlib as _h

    recomputed = _h.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert PREREG["preregistration_hash"] == recomputed
