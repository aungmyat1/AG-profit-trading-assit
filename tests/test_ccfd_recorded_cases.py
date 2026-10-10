"""AGP-DATA-R2b: read-only capture surface, manifest integrity and materialized slices."""
import ast
import csv
import importlib.util
import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / "scripts" / "capture_recorded_ccfd_tfs.py"
RECORDED = ROOT / "tests" / "fixtures" / "ccfd_v100" / "recorded"
# Case keys of tests/fixtures/ccfd_v100/synthetic/manifest.json (PR #126) plus the recorded
# `provenance` pointer its README requires.
CASE_KEYS = {"id", "symbol", "window", "now", "paths", "spread", "commission_R", "quote_time",
             "expected_result", "expected_direction", "provenance"}
ALLOWED = {"initialize", "copy_rates_range", "symbol_info", "shutdown", "TIMEFRAME_M1",
           "TIMEFRAME_M5", "TIMEFRAME_M15", "TIMEFRAME_H1", "TIMEFRAME_D1"}


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_capture_uses_only_read_only_mt5_attributes():
    src = CAPTURE.read_text(encoding="utf-8")
    for word in ("order", "position", "trade_request"):
        assert word not in src.lower(), word
    used = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute) \
                and node.value.attr == "mt5":
            used.add(node.attr)
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) in {"getattr", "eval", "exec"}:
            raise AssertionError("dynamic attribute access is not allowed")
    assert used and used <= ALLOWED, used - ALLOWED


def test_manifest_lists_every_file_hash_and_matches_schema():
    m = _load(ROOT / "scripts" / "ccfd_recorded_cases.py", "ccfd_recorded_cases")
    manifest = m.verify(RECORDED / "manifest.json")
    assert manifest["source"] == "MT5_VT_MARKETS_DEMO" and manifest["mission"] == "AGP-DATA-R2"
    listed = set(manifest["files"])
    on_disk = {p.name for p in RECORDED.iterdir()} - {"manifest.json", "README.md"}
    assert on_disk <= listed
    assert {f"../../manual_ticket/{s}_M15_recorded.csv" for s in ("BTCUSD", "ETHUSD")} <= listed
    assert len(manifest["cases"]) == 304
    for case in manifest["cases"]:
        assert set(case) == CASE_KEYS
        assert case["commission_R"] is None and case["expected_result"] is None
        assert case["window"] == m.window_of(datetime.fromisoformat(case["now"]), m.windows())
        for rel in list(case["paths"].values()) + [case["provenance"]]:
            assert rel in listed


def test_tampered_file_aborts_before_writing(tmp_path):
    m = _load(ROOT / "scripts" / "ccfd_recorded_cases.py", "ccfd_recorded_cases")
    copy = tmp_path / "recorded"
    shutil.copytree(RECORDED, copy)
    (tmp_path / "manual_ticket").mkdir()
    for s in ("BTCUSD", "ETHUSD"):
        shutil.copy(ROOT / f"tests/fixtures/manual_ticket/{s}_M15_recorded.csv", tmp_path / "manual_ticket")
    data = json.loads((copy / "manifest.json").read_text())
    for c in data["cases"]:
        c["paths"]["m15"] = c["paths"]["m15"].replace("../../", "../")
    data["files"] = {k.replace("../../", "../"): v for k, v in data["files"].items()}
    (copy / "manifest.json").write_text(json.dumps(data))
    with (copy / "BTCUSD_h1.csv").open("a") as f:
        f.write("2026-10-09T23:00:00+00:00,1,1,1,1\n")
    out = tmp_path / "out"
    with pytest.raises(SystemExit, match="sha256 mismatch"):
        m.materialize(copy / "manifest.json", out)
    assert not out.exists()


def test_materialized_cases_hold_only_closed_aware_bars(tmp_path):
    m = _load(ROOT / "scripts" / "ccfd_recorded_cases.py", "ccfd_recorded_cases")
    out = m.materialize(RECORDED / "manifest.json", tmp_path, limit=3)
    data = json.loads(out.read_text())
    step = {"d1": timedelta(days=1), "h1": timedelta(hours=1), "m15": timedelta(minutes=15),
            "m5": timedelta(minutes=5)}
    for case in data["cases"]:
        now = datetime.fromisoformat(case["now"])
        prov = json.loads((tmp_path / case["provenance"]).read_text())
        for tf, rel in case["paths"].items():
            rows = list(csv.DictReader((tmp_path / rel).open()))
            assert rows and all(datetime.fromisoformat(r["timestamp_utc"]).tzinfo for r in rows)
            assert all(datetime.fromisoformat(r["timestamp_utc"]) + step[tf] <= now for r in rows)
            assert prov["sha256"][tf] == m.sha(tmp_path / rel)
