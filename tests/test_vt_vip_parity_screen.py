"""VT EURUSD / EURUSD-VIP parity collector + preregistered spread screen (research only)."""
from __future__ import annotations

import ast
import datetime as dt
import hashlib
import importlib.util
import json
import os
import runpy
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
UTC = dt.timezone.utc
PREREG = REPO / "artifacts/research/VT_EURUSD_VIP_PARITY_SPREAD_SCREEN_V1/PREREGISTRATION.yaml"
COLLECTOR = REPO / "scripts/research/capture_vt_vip_parity.py"
ANALYZER = REPO / "scripts/research/analyze_vt_vip_parity_screen.py"

_spec = importlib.util.spec_from_file_location("vip_analyzer", ANALYZER)
an = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(an)


# --- preregistration is frozen and consistent with the analyzer ---------------------------

def test_preregistration_threshold_and_criteria_match_analyzer():
    p = yaml.safe_load(PREREG.read_text(encoding="utf-8"))
    assert p["owner_decision"]["max_friction_to_risk"] == 0.25
    assert p["owner_decision"]["tuning_after_results"] == "FORBIDDEN"
    assert p["parity_criteria"]["price"]["pass"] == "median <= 0.2 AND p95 <= 0.5"
    assert p["parity_criteria"]["m1"]["close_diff_pips_pass"] == "median <= 0.2 AND p95 <= 0.5"
    assert p["parity_criteria"]["m1"]["high_low_diff_pips_pass"] == "median <= 0.3 AND p95 <= 1.0"
    assert p["boundary"] == {"SPREAD_ONLY_SCREEN": True, "COMMISSION_INCLUDED": False, "SLIPPAGE_INCLUDED": False,
                             "FULL_FRICTION_ESTIMATE": False, "ECONOMIC_QUALIFICATION": False,
                             "screen_pass_grants_authority": False}
    assert p["sealed_oos"] == "NOT_ACCESSED"


# --- synthetic captures ----------------------------------------------------------------------

STATIC = {"digits": 5, "point": 1e-05, "trade_tick_size": 1e-05, "trade_contract_size": 100000.0,
          "trade_tick_value": 1.0, "currency_base": "EUR", "currency_profit": "USD", "currency_margin": "EUR",
          "trade_mode": 0, "trade_exemode": 2, "filling_mode": 2, "volume_min": 0.01, "volume_max": 100.0,
          "volume_step": 0.01, "description": "Euro vs US Dollar", "path": "Forex Major\\EURUSD"}


def _row(symbol, k, session, bid, ask, day, validity="VALID"):
    return {"round": k, "validity": validity, "bid": bid, "ask": ask, "spread_pips": round((ask - bid) / 0.0001, 6),
            "session_classification": session, "timestamp_utc": f"{day}T08:00:{k % 60:02d}+00:00",
            "tick_time_msc_broker_clock": 1000 * k}


def _write_capture(root: Path, cid, session, day, vip_spread=0.2, mid_shift=0.0, vip_static=None, rounds=144,
                   vip_invalid=0):
    d = root / cid
    d.mkdir(parents=True)
    rows = {"EURUSD": [], "EURUSD-VIP": []}
    for k in range(rounds):
        base = 1.17 + k * 1e-5
        rows["EURUSD"].append(_row("EURUSD", k, session, base, base + 0.00001, day))
        v = base + mid_shift * 0.0001 - (vip_spread - 0.1) / 2 * 0.0001   # same mid as EURUSD unless shifted
        rows["EURUSD-VIP"].append(_row("EURUSD-VIP", k, session, v, v + vip_spread * 0.0001, day,
                                       "STALE_TICK" if k < vip_invalid else "VALID"))
    files = {}
    for s, rs in rows.items():
        data = ("\n".join(json.dumps(r, sort_keys=True) for r in rs) + "\n").encode()
        (d / f"{s}_raw.jsonl").write_bytes(data)
        files[s] = {"sha256": hashlib.sha256(data).hexdigest()}
    bars = {s: [{"open_utc": f"{day}T08:{m:02d}:00+00:00", "open": 1.17, "high": 1.1702 + (mid_shift * 1e-4 if s != "EURUSD" else 0),
                 "low": 1.1698, "close": 1.17 + (mid_shift * 1e-4 if s != "EURUSD" else 0)} for m in range(11)]
            for s in rows}
    (d / "m1_bars.json").write_text(json.dumps(bars))
    manifest = {"capture_id": cid, "requested_session": session, "session_classification": [session],
                "sampling": {"rounds_planned": rounds}, "files": files,
                "symbol_metadata": {"start": {"EURUSD": dict(STATIC), "EURUSD-VIP": {**STATIC, **(vip_static or {})}}}}
    (d / "manifest.json").write_text(json.dumps(manifest))


@pytest.fixture
def dev(tmp_path):
    # Synthetic development file: stops 2, 4, 8, 16 pips per session; outcome fields absent on purpose.
    obs = [{"opportunity_id": f"{c}-{i}", "cycle": c, "risk_distance": s * 0.0001}
           for c in ("POST_ASIAN", "POST_LONDON") for i, s in enumerate((2.0, 4.0, 8.0, 16.0))]
    obs += [{"cycle": "OTHER", "risk_distance": 0.0005}, {"cycle": "POST_ASIAN", "risk_distance": float("nan")}]
    data = json.dumps({"observations": obs}).encode()
    path = tmp_path / "dev.json"
    path.write_bytes(data)
    return path, hashlib.sha256(data).hexdigest()


def _prereg_copy(tmp_path, dev_path, dev_sha):
    p = yaml.safe_load(PREREG.read_text(encoding="utf-8"))
    p["screen"]["development_source"] = {"path": str(dev_path), "sha256": dev_sha}
    out = tmp_path / "prereg.yaml"
    out.write_text(yaml.safe_dump(p), encoding="utf-8")
    return out


def _analyze(tmp_path, dev):
    return an.analyze(_prereg_copy(tmp_path, *dev), tmp_path / "caps", repo=Path("/"))


def test_insufficient_evidence_without_both_sessions_never_opens_dev_file(tmp_path, dev, monkeypatch):
    _write_capture(tmp_path / "caps", "A1", "POST_ASIAN", "2026-09-30")
    monkeypatch.setattr(an, "run_screen", lambda *a, **k: pytest.fail("dev file must not be opened"))
    r = _analyze(tmp_path, dev)
    assert r["parity"]["EURUSD_VIP_PARITY"] == "INSUFFICIENT_EVIDENCE"
    assert r["spread_authority"] == "NOT_ESTABLISHED"
    assert r["SPREAD_TO_DEV_STOP_R_SCREEN"] == "NOT_EVALUATED_PARITY_INSUFFICIENT_EVIDENCE"


def test_known_differences_pass_and_screen_math(tmp_path, dev):
    for cid, s in (("A1", "POST_ASIAN"), ("L1", "POST_LONDON")):
        _write_capture(tmp_path / "caps", cid, s, "2026-09-30", vip_spread=1.0,
                       vip_static={"trade_mode": 4, "path": "VT\\Forex-VIP\\EURUSD-VIP"})
    r = _analyze(tmp_path, dev)
    assert r["parity"]["EURUSD_VIP_PARITY"] == "PASS_WITH_KNOWN_DIFFERENCES"
    assert r["parity"]["known_difference_fields"] == ["path", "trade_mode"]
    assert r["vip_spread_pips"]["POST_ASIAN"]["median"] == pytest.approx(1.0)
    assert r["vip_spread_pips"]["POST_ASIAN"]["reported_as"] == "INITIAL"
    s = r["screen"]
    assert (s["population"], s["excluded"], s["threshold"]) == (8, 2, 0.25)
    # spread 1.0 pip: 1/2=0.5 F, 1/4=0.25 P (boundary inclusive), 1/8 P, 1/16 P -> 3 of 4 per session
    for sc in ("median", "p90", "p95"):
        assert s["scenarios"][sc]["pass"]["COMBINED"] == {"N": 8, "pass": 6, "pass_rate": 0.75}
        assert s["scenarios"][sc]["implied_min_stop_pips"]["POST_ASIAN"] == pytest.approx(4.0)


def test_identical_metadata_is_plain_pass(tmp_path, dev):
    for cid, s in (("A1", "POST_ASIAN"), ("L1", "POST_LONDON")):
        _write_capture(tmp_path / "caps", cid, s, "2026-09-30")
    assert _analyze(tmp_path, dev)["parity"]["EURUSD_VIP_PARITY"] == "PASS"


@pytest.mark.parametrize("kwargs,check", [
    ({"vip_static": {"trade_contract_size": 10000.0}}, "static"),
    ({"vip_static": {"digits": 3}}, "static"),
    ({"mid_shift": 1.0}, "price"),
    ({"vip_invalid": 10}, "availability"),
])
def test_parity_fail_stops_before_screen(tmp_path, dev, monkeypatch, kwargs, check):
    for cid, s in (("A1", "POST_ASIAN"), ("L1", "POST_LONDON")):
        _write_capture(tmp_path / "caps", cid, s, "2026-09-30", **kwargs)
    monkeypatch.setattr(an, "run_screen", lambda *a, **k: pytest.fail("dev file must not be opened"))
    r = _analyze(tmp_path, dev)
    assert r["parity"]["EURUSD_VIP_PARITY"] == "FAIL" and r["parity"]["checks"][check] is False
    assert r["SPREAD_TO_DEV_STOP_R_SCREEN"] == "NOT_EVALUATED_PARITY_FAIL"


def test_raw_hash_mismatch_fails_closed(tmp_path, dev):
    _write_capture(tmp_path / "caps", "A1", "POST_ASIAN", "2026-09-30")
    p = tmp_path / "caps" / "A1" / "EURUSD-VIP_raw.jsonl"
    p.write_bytes(p.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        _analyze(tmp_path, dev)


def test_dev_source_hash_mismatch_fails_closed(tmp_path, dev):
    path, _sha = dev
    with pytest.raises(ValueError, match="development source hash mismatch"):
        an.run_screen(path, "0" * 64, {"POST_ASIAN": {"median": 1}, "POST_LONDON": {"median": 1}}, 0.25)


def test_distribution_statistics():
    d = an.describe([0.0, 0.1, 0.2, 0.3, 1.0])
    assert (d["N"], d["min"], d["median"], d["max"], d["zero_fraction"]) == (5, 0.0, 0.2, 1.0, 0.2)
    assert d["p75"] == pytest.approx(0.3) and d["p90"] == pytest.approx(0.72)


# --- collector: containment and read-only -------------------------------------------------

def _fake_mt5(calls):
    fake = types.ModuleType("MetaTrader5")
    fake.__file__ = os.path.join(os.sep, "site-packages", "MetaTrader5", "__init__.py")
    fake.ACCOUNT_TRADE_MODE_DEMO = 0
    for i, tf in enumerate(("M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1"), start=1):
        setattr(fake, f"TIMEFRAME_{tf}", i)   # read at import by mt5.market_data

    def rec(name, result=None):
        def _f(*a, **k):
            calls.append(name)
            return result(*a) if callable(result) else result
        return _f

    fake.initialize = rec("initialize", True)
    fake.shutdown = rec("shutdown", True)
    fake.last_error = rec("last_error", (0, "ok"))
    fake.account_info = rec("account_info", SimpleNamespace(server="VTMarkets-Demo", trade_mode=0))
    fake.symbol_info = rec("symbol_info", lambda name: SimpleNamespace(name=name, **STATIC))
    fake.symbol_info_tick = rec("symbol_info_tick", None)
    fake.copy_rates_range = rec("copy_rates_range", [])
    return fake


class _Clock:
    def __init__(self, *instants):
        self.instants, self.reads = list(instants), 0

    def __call__(self):
        i = min(self.reads, len(self.instants) - 1)
        self.reads += 1
        return self.instants[i]


def _run(monkeypatch, tmp_path, session, clock, calls):
    monkeypatch.setitem(sys.modules, "MetaTrader5", _fake_mt5(calls))
    cwd = os.getcwd()
    try:
        ns = runpy.run_path(str(COLLECTOR), run_name="vip_collector_under_test")
    finally:
        os.chdir(cwd)
    g = ns["main"].__globals__
    monkeypatch.setitem(g, "_utcnow", clock)
    monkeypatch.setitem(g, "_lineage", lambda: "b" * 40)
    monkeypatch.setitem(g, "OUT_ROOT", str(tmp_path / "ev"))
    monkeypatch.setitem(g, "server_time_timeline",
                        lambda *a: SimpleNamespace(at_utc=lambda t: SimpleNamespace(utc_offset_hours=0)))
    monkeypatch.setattr(sys, "argv", ["capture", "--session", session])
    monkeypatch.chdir(REPO)
    return ns, g


@pytest.mark.parametrize("session", ["OTHER", "LONDON", ""])
def test_collector_unsupported_session_makes_no_broker_call(monkeypatch, tmp_path, capsys, session):
    calls = []
    ns, _ = _run(monkeypatch, tmp_path, session, _Clock(dt.datetime(2026, 9, 30, 8, 0, tzinfo=UTC)), calls)
    assert ns["main"]() == 2 and json.loads(capsys.readouterr().out)["status"] == "UNSUPPORTED_CAPTURE_SESSION"
    assert calls == [] and not (tmp_path / "ev").exists()


@pytest.mark.parametrize("session,now", [("POST_ASIAN", dt.datetime(2026, 9, 30, 10, 48, 1, tzinfo=UTC)),
                                         ("POST_LONDON", dt.datetime(2026, 9, 30, 11, 59, tzinfo=UTC)),
                                         ("POST_ASIAN", dt.datetime(2026, 10, 3, 8, 0, tzinfo=UTC))])
def test_collector_precheck_blocks_before_initialize(monkeypatch, tmp_path, capsys, session, now):
    calls = []
    ns, _ = _run(monkeypatch, tmp_path, session, _Clock(now), calls)
    assert ns["main"]() == 2 and json.loads(capsys.readouterr().out)["status"] == "TARGET_SESSION_NOT_ACTIVE"
    assert calls == []


def test_collector_second_gate_after_setup(monkeypatch, tmp_path, capsys):
    calls = []
    t = dt.datetime(2026, 9, 30, 14, 47, 50, tzinfo=UTC)
    ns, _ = _run(monkeypatch, tmp_path, "POST_LONDON", _Clock(t, t + dt.timedelta(seconds=15)), calls)
    out = json.loads(capsys.readouterr().out) if ns["main"]() == 2 else pytest.fail("expected stop")
    assert out["status"] == "TARGET_SESSION_WINDOW_EXPIRED_DURING_SETUP"
    assert calls.count("initialize") == 1 and "symbol_info_tick" not in calls and calls[-1] == "shutdown"
    assert set(out["broker_mutation_calls"].values()) == {0} and not (tmp_path / "ev").exists()


def test_collector_valid_capture_writes_pinned_evidence(monkeypatch, tmp_path, capsys):
    calls = []
    t = dt.datetime(2026, 9, 30, 8, 0, tzinfo=UTC)
    ns, g = _run(monkeypatch, tmp_path, "POST_ASIAN", _Clock(t, t, t), calls)
    monkeypatch.setitem(g, "time", SimpleNamespace(monotonic=lambda: 0.0, sleep=lambda s: None))
    epoch = dt.datetime(1970, 1, 1, tzinfo=UTC)
    ms = int((t - epoch).total_seconds() * 1000)
    fake = sys.modules["MetaTrader5"]
    fake.symbol_info_tick = lambda s: calls.append("tick") or SimpleNamespace(
        bid=1.17, ask=1.17 if s == "EURUSD" else 1.17002, time_msc=ms, flags=6)
    try:
        rc = ns["main"]()
    finally:
        for p in (tmp_path / "ev").rglob("*"):
            os.chmod(p, 0o666)
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["status"] == "VT_VIP_PARITY_CAPTURE_COMPLETE"
    assert calls.count("tick") == 288 and calls.count("initialize") == 1 and calls[-1] == "shutdown"
    assert out["per_symbol"]["EURUSD"]["zero_spread_samples"] == 144
    assert out["per_symbol"]["EURUSD-VIP"]["spread_max_pips"] == pytest.approx(0.2)
    assert set(out["broker_mutation_calls"].values()) == {0}
    m = json.loads(Path(out["manifest"]).read_text(encoding="utf-8"))
    assert m["symbols"] == {"EURUSD": "ANALYSIS_FEED_REFERENCE", "EURUSD-VIP": "EXECUTION_FRICTION_CANDIDATE"}
    assert m["authority"]["proposal"] == "NONE" and m["commission_status"] == "UNKNOWN"
    for s in ("EURUSD", "EURUSD-VIP"):
        raw = (Path(out["manifest"]).parent / f"{s}_raw.jsonl").read_bytes()
        assert hashlib.sha256(raw).hexdigest() == m["files"][s]["sha256"]
    assert "login" not in json.dumps(m).lower()


@pytest.mark.parametrize("path", [COLLECTOR, ANALYZER], ids=lambda p: p.name)
def test_no_execution_capability(path):
    forbidden_calls = {"order_send", "order_check", "positions_get", "orders_get", "symbol_select",
                       "trade_buy", "trade_sell", "trade_close", "trade_modify", "trade_cancel"}
    forbidden_imports = {"execution", "execution_runtime", "authorization", "strategy_engine", "proposal_envelope",
                         "trade_ticket", "opportunity", "strategy_manager"}
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call):
            f = node.func
            assert (f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")) not in forbidden_calls
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            assert not {n.split(".")[0] for n in names} & forbidden_imports
