"""Venue-aware WP3A.1 aggregation wrapper: VT rows can never enter the Vantage campaign."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("wp3a1_vf", REPO / "scripts/research/aggregate_wp3a1_venue_filtered.py")
vf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vf)

CID, VANTAGE, VT = "LSMC_EURUSD_FRICTION_WP3A1_V1", "VantageMarkets-Demo", "VTMarkets-Demo"
WINDOWS = ["WINDOW_A_ASIAN_REFERENCE", "WINDOW_B_PRE_LONDON", "WINDOW_C_LONDON", "WINDOW_D_LONDON_NEWYORK"]


def _campaign(tmp_path, tamper=False):
    manifest = {"broker": VANTAGE, "campaign_id": CID, "symbol": "EURUSD", "minimum_trading_days": 2,
                "samples_per_window_minimum": 3,
                "required_minimum_population": {"total_minimum_observations": 24},
                "windows": [{"window_id": w} for w in WINDOWS]}
    h = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if tamper:
        manifest["broker"] = VT
    (tmp_path / "campaign_manifest.json").write_text(json.dumps(manifest))
    (tmp_path / "campaign_manifest_hash.json").write_text(json.dumps({"campaign_manifest_hash": h}))
    (tmp_path / "sessions").mkdir()
    return tmp_path


def _session(root, day, window, server=VANTAGE, n=3, spread=0.5, missing=0, campaign=CID, symbol="EURUSD"):
    rows = [{"broker_server": server, "campaign_id": campaign, "symbol": symbol, "spread_pips": spread,
             "missing_reason": None} for _ in range(n)]
    rows += [{"broker_server": None, "campaign_id": campaign, "symbol": symbol, "spread_pips": None,
              "missing_reason": "MISSING_SOURCE"} for _ in range(missing)]
    p = root / "sessions" / f"{day}_{window}_raw.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return p


def _full_day(root, day, server=VANTAGE, spread=0.5):
    for w in WINDOWS:
        _session(root, day, w, server=server, spread=spread)


def test_vt_rows_excluded_with_reason_and_counts_preserved(tmp_path):
    root = _campaign(tmp_path)
    _full_day(root, "2026-09-16")
    _full_day(root, "2026-09-17")
    _full_day(root, "2026-09-29", server=VT, spread=0.1)          # later VT lineage in the same directory
    before = {p.name: p.read_bytes() for p in (root / "sessions").iterdir()}
    r = vf.aggregate(root)
    assert r["WP3A1_VANTAGE_VALID_DAYS"] == ["2026-09-16", "2026-09-17"]
    assert r["WP3A1_VANTAGE_VALID_OBSERVATIONS"] == 24 and r["minimum_met"] is True
    assert r["row_exclusions"] == {"BROKER_SERVER_MISMATCH": 12}
    assert r["VT_ROWS_EXCLUDED_FROM_WP3A1"] == 12
    assert {s["status"] for s in r["excluded_sessions"]} == {"EXCLUDED_MIXED_OR_FOREIGN_VENUE"}
    assert r["spread_pips_complete_days"]["median"] == 0.5           # no VT spread leaked into statistics
    assert {p.name: p.read_bytes() for p in (root / "sessions").iterdir()} == before   # read-only


def test_mixed_session_is_excluded_whole(tmp_path):
    root = _campaign(tmp_path)
    _full_day(root, "2026-09-16")
    p = _session(root, "2026-09-16", WINDOWS[0])
    p.write_text(p.read_text() + json.dumps({"broker_server": VT, "campaign_id": CID, "symbol": "EURUSD",
                                             "spread_pips": 0.0, "missing_reason": None}) + "\n")
    r = vf.aggregate(root)
    assert r["WP3A1_VANTAGE_VALID_DAYS"] == []
    assert r["incomplete_days"]["2026-09-16"][WINDOWS[0]] == "ABSENT"


@pytest.mark.parametrize("kwargs,reason", [
    ({"server": None}, "BROKER_IDENTITY_MISSING"),
    ({"server": ""}, "BROKER_IDENTITY_MISSING"),
    ({"campaign": "OTHER_CAMPAIGN"}, "CAMPAIGN_ID_MISMATCH"),
    ({"symbol": "EURUSD-VIP"}, "SYMBOL_MISMATCH"),
])
def test_unknown_identity_fails_closed(tmp_path, kwargs, reason):
    root = _campaign(tmp_path)
    _full_day(root, "2026-09-16")
    _session(root, "2026-09-16", WINDOWS[1], **kwargs)              # overwrite one window
    r = vf.aggregate(root)
    assert r["row_exclusions"] == {reason: 3}
    assert r["WP3A1_VANTAGE_VALID_DAYS"] == []


def test_missing_gap_rows_are_counted_not_filled(tmp_path):
    root = _campaign(tmp_path)
    _full_day(root, "2026-09-16")
    _session(root, "2026-09-16", WINDOWS[0], n=1, missing=2)        # like 2026-09-21 Window A (6/120)
    r = vf.aggregate(root)
    assert r["row_exclusions"] == {"BROKER_IDENTITY_MISSING": 2}
    assert r["incomplete_days"]["2026-09-16"][WINDOWS[0]] == 1


def test_altered_manifest_voids_the_campaign(tmp_path):
    root = _campaign(tmp_path, tamper=True)
    with pytest.raises(ValueError, match="manifest hash mismatch"):
        vf.aggregate(root)
