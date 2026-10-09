import json
import queue
import threading
import time

import pandas as pd
import pytest

from scripts.research.mt5_readonly_client import ALLOWED_TOOLS, MCPError, ReadonlyMT5Client
from scripts.research.mt5_readonly_client import read_mt5_env_file, verified_vt_demo_configuration
from scripts.research.market_dataset import (DatasetError, aggregate, parse_candles, sha256_file,
                                               validate, decode_tool_result)
from scripts.research.export_mt5_history import export_symbol
from scripts.research.probe_history_depth import candle_args
from scripts.research.market_dataset import resolve_broker_crypto_symbols


class _Stdout:
    def __init__(self, q): self.q = q
    def __iter__(self):
        while True:
            item = self.q.get()
            if item is None: return
            yield item


class _Stdin:
    def __init__(self, proc): self.proc = proc
    def write(self, line):
        msg = json.loads(line)
        method, req_id = msg.get("method"), msg.get("id")
        if method == "notifications/initialized": return
        if method == "initialize": result = {"protocolVersion": "2025-06-18"}
        elif method == "tools/list":
            toolset = ([{"name": "readonly_mt5_setup_status", "inputSchema": {"properties": {}}}]
                       if self.proc.mode == "setup" else [
                {"name": "readonly_get_candles_latest", "inputSchema": {"properties": {"symbol": {}, "timeframe": {}, "count": {}}, "required": ["symbol", "timeframe", "count"]}},
                {"name": "place_order", "inputSchema": {"properties": {}}},
            ])
            result = {"tools": [
                *toolset,
            ]}
        elif method == "tools/call": result = {"content": [{"type": "text", "text": "{}"}]}
        else: result = {}
        if self.proc.mode == "timeout" and method == "tools/call": return
        if self.proc.mode == "malformed" and method == "tools/list":
            self.proc.q.put("{not-json\n")
            return
        def emit():
            self.proc.q.put(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result}) + "\n")
        threading.Timer(self.proc.delay, emit).start()
    def flush(self): pass
    def close(self):
        self.proc.closed = True
        self.proc.q.put(None)


class _Proc:
    def __init__(self, delay=0, mode="ok"):
        self.q, self.delay, self.mode = queue.Queue(), delay, mode
        self.stdin, self.stdout, self.closed = _Stdin(self), _Stdout(self.q), False
    def poll(self): return None
    def wait(self, timeout=None): return 0
    def terminate(self): pass
    def kill(self): pass


def _client(proc, **kwargs):
    return ReadonlyMT5Client(process_factory=lambda *a, **k: proc,
                             root=__import__("pathlib").Path(__file__).resolve().parents[1], **kwargs)


def _fixture_rows(start="2026-09-30 00:00:00", n=288):
    ts = pd.date_range(start, periods=n, freq="5min", tz="UTC")
    return pd.DataFrame({"source_timestamp": ts.astype(str), "timestamp_utc": ts,
                         "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.5,
                         "tick_volume": 2.0})


def test_client_tolerates_launcher_startup_delay_and_filters_tools():
    proc = _Proc(delay=0.08)
    with _client(proc, startup_timeout=2, request_timeout=1) as c:
        assert set(c.tools) == {"readonly_get_candles_latest"}
        assert all(name in ALLOWED_TOOLS for name in c.tools)
        assert c.call("readonly_get_candles_latest", {"symbol": "BTCUSD"})["content"]


def test_client_rejects_forbidden_tool_before_sending_call():
    proc = _Proc()
    with _client(proc, startup_timeout=1, request_timeout=1) as c:
        with pytest.raises(MCPError, match="allowlist"):
            c.call("place_order", {})


def test_client_fails_closed_on_malformed_response_and_timeout():
    with pytest.raises(MCPError, match="malformed"):
        with _client(_Proc(mode="malformed"), startup_timeout=1, request_timeout=0.1): pass
    proc = _Proc(mode="timeout")
    with _client(proc, startup_timeout=1, request_timeout=0.1) as c:
        with pytest.raises(MCPError, match="timeout"):
            c.call("readonly_get_candles_latest", {})


def test_client_fails_fast_when_launcher_only_exposes_setup_status():
    with pytest.raises(MCPError, match="setup is incomplete"):
        with _client(_Proc(mode="setup"), startup_timeout=1, request_timeout=0.1): pass


def test_symbol_authority_and_candle_argument_shape():
    symbols = {"symbols": [{"name": "BTCUSD"}, {"symbol": "ETHUSD"}, {"name": "EURUSD"}]}
    assert resolve_broker_crypto_symbols({"symbols": [{"name": "nBTCUSD"}, {"symbol": "nETHUSD"}]}) == {
        "BTCUSD": "NBTCUSD", "ETHUSD": "NETHUSD"}
    tool = {"inputSchema": {"properties": {"symbol": {}, "timeframe": {}, "count": {}},
                            "required": ["symbol", "timeframe", "count"]}}
    assert candle_args(tool, "BTCUSD", 5000) == {"symbol": "BTCUSD", "timeframe": "M5", "count": 5000}


def test_env_file_loader_only_passes_mt5_keys_without_echoing_values(tmp_path):
    path = tmp_path / ".env"
    path.write_text("MT5_ENVIRONMENT=DEMO\nMT5_PASSWORD=sample-secret\nVTMARKET-DEMO-LOGIN=123\nBYBIT_API_KEY=unrelated\n", encoding="utf-8")
    values = read_mt5_env_file(path)
    assert values == {"MT5_ENVIRONMENT": "DEMO", "MT5_PASSWORD": "sample-secret", "VTMARKETS-DEMO-LOGIN": "123"}
    assert verified_vt_demo_configuration({"MT5_ENVIRONMENT": "DEMO", "VTMARKETS-DEMO_SERVER": "VTMarkets-Demo"})
    assert not verified_vt_demo_configuration({"MT5_ENVIRONMENT": "LIVE", "VTMARKETS-DEMO_SERVER": "VTMarkets-Demo"})


def test_history_parse_preserves_source_and_normalizes_vt_rule():
    frame = parse_candles([{"time": "2026-07-01 12:00:00", "open": 1, "high": 2,
                            "low": 0, "close": 1, "tick_volume": 3, "bias": "BUY"}],
                          source_semantics="VT_SERVER_WALL_CLOCK")
    assert frame.source_timestamp.iloc[0] == "2026-07-01 12:00:00"
    assert frame.timestamp_utc.iloc[0] == pd.Timestamp("2026-07-01T09:00:00Z")
    assert "bias" not in frame.columns
    with pytest.raises(DatasetError, match="time authority"):
        parse_candles([{"time": "2026-07-01 12:00:00", "open": 1, "high": 2, "low": 0, "close": 1}])


def test_vectorized_timestamp_parser_large_fixture_and_vt_equivalence(monkeypatch):
    from scripts.research import market_dataset
    from datetime import datetime

    samples = [
        "2026-07-01 12:00:00", "2026-01-15 12:00:00Z",
        "2026-11-01 05:30:00", "2026-03-08 09:30:00",
    ]
    records = [{"time": stamp, "open": 1, "high": 2, "low": 0, "close": 1,
                "tick_volume": 3, "spread": 5, "real_volume": 7} for stamp in samples]
    actual = parse_candles(records, source_semantics="VT_SERVER_WALL_CLOCK")
    expected = [market_dataset.vt_server_wall_to_utc(
        pd.to_datetime(stamp, utc=False).tz_convert(None).to_pydatetime()
        if stamp.endswith("Z") else pd.to_datetime(stamp).to_pydatetime()) for stamp in samples]
    assert list(actual.timestamp_utc) == expected
    assert list(actual.source_timestamp) == samples
    assert actual[["open", "high", "low", "close", "tick_volume", "spread", "real_volume"]].values.tolist() == [[1., 2., 0., 1., 3., 5., 7.]] * 4

    def forbidden(_):
        raise AssertionError("legacy per-row timestamp helper invoked")
    monkeypatch.setattr(market_dataset, "vt_server_wall_to_utc", forbidden)
    base = pd.date_range("2026-07-01", periods=50_000, freq="5min")
    large = [{"time": t.strftime("%Y-%m-%d %H:%M:%S"), "open": 1, "high": 2,
              "low": 0, "close": 1} for t in base]
    parsed = parse_candles(large, source_semantics="VT_SERVER_WALL_CLOCK")
    assert len(parsed) == 50_000
    assert parsed.source_timestamp.iloc[0] == "2026-07-01 00:00:00"
    assert parsed.timestamp_utc.is_monotonic_increasing


def test_vectorized_parser_fails_closed_for_mixed_bad_timestamps():
    rows = [{"time": "2026-07-01T12:00:00Z", "open": 1, "high": 2, "low": 0, "close": 1},
            {"time": "not-a-time", "open": 1, "high": 2, "low": 0, "close": 1}]
    with pytest.raises(DatasetError, match="invalid candle timestamp"):
        parse_candles(rows, source_semantics="VT_SERVER_WALL_CLOCK")


def test_mcp_csv_history_parsing(tmp_path):
    raw = ",time,open,high,low,close,tick_volume,spread,real_volume\n0,2026-07-01 12:00:00,1,2,0,1,3,5,0\n"
    result = {"content": [{"type": "text", "text": raw}]}
    frame = parse_candles(decode_tool_result(result), source_semantics="VT_SERVER_WALL_CLOCK")
    assert len(frame) == 1
    assert frame.timestamp_utc.iloc[0] == pd.Timestamp("2026-07-01T09:00:00Z")
    assert frame.loc[0, "tick_volume"] == 3


def test_duplicate_and_invalid_ohlc_detection():
    frame = _fixture_rows(n=3)
    frame.loc[1, "timestamp_utc"] = frame.loc[0, "timestamp_utc"]
    frame.loc[2, "high"] = 8
    report = validate(frame)
    assert report["duplicates"] == 1
    assert report["invalid_ohlc"] == 1
    frame["open"] = frame["open"].astype(object)
    frame.loc[0, "open"] = "bad"
    assert validate(frame)["invalid_ohlc"] == 2


def test_m5_aggregation_m15_h1_and_utc_d1_boundary():
    frame = _fixture_rows("2026-09-30 00:00:00+00:00", 576)
    m15, h1, d1 = aggregate(frame, "15min"), aggregate(frame, "1h"), aggregate(frame, "1D")
    assert len(m15) == 192 and len(h1) == 48
    assert d1.timestamp_utc.iloc[0] == pd.Timestamp("2026-09-30T00:00:00Z")
    assert len(d1) == 2


def test_gap_detection_and_derivation_block():
    frame = _fixture_rows(n=30).drop(index=10).reset_index(drop=True)
    report = validate(frame)
    assert report["unexpected_gaps"] == 1
    with pytest.raises(DatasetError, match="blocked"):
        aggregate(frame, "15min")


def test_unverified_weekend_closure_remains_unknown():
    idx = pd.to_datetime(["2026-09-04T20:00:00Z", "2026-09-07T00:00:00Z"])
    frame = pd.DataFrame({"source_timestamp": idx.astype(str), "timestamp_utc": idx,
                          "open": [1., 1.], "high": [2., 2.], "low": [0., 0.], "close": [1., 1.]})
    assert validate(frame)["gaps"][0]["classification"] == "UNKNOWN_GAP"


def test_hash_and_provenance_inputs_are_strategy_blind(tmp_path):
    frame = parse_candles([{"time": "2026-07-01T12:00:00Z", "open": 1, "high": 2,
                            "low": 0, "close": 1, "target": 99, "profit": 4}])
    assert not ({"target", "profit", "signal", "bias"} & set(frame.columns))
    path = tmp_path / "raw.parquet"
    frame.to_parquet(path, index=False)
    digest = sha256_file(path)
    assert len(digest) == 64 and digest == sha256_file(path)
    # The launcher command and all observable call arguments contain no credential fields.
    proc = _Proc()
    with _client(proc, startup_timeout=1, request_timeout=1) as c:
        assert "password" not in str(c.tools).lower()


def test_export_provenance_sha_and_strategy_blind_fields(tmp_path):
    class FakeClient:
        tools = {"readonly_get_candles_latest": {}}
        def call(self, name, args):
            assert args == {"symbol_name": "BTCUSD", "timeframe": "M5", "count": 10}
            return {"structuredContent": ",time,open,high,low,close,tick_volume,spread,real_volume\n" +
                    "0,2026-07-01 12:00:00,1,2,0,1,3,5,0\n"}
    client = FakeClient()
    client.tools["readonly_get_candles_latest"] = {"inputSchema": {"properties": {"symbol_name": {}, "timeframe": {}, "count": {}}, "required": ["symbol_name", "timeframe", "count"]}}
    path, meta, frame = export_symbol(client, "BTCUSD", 10, output_dir=tmp_path)
    assert meta["broker"] == "VT Markets" and meta["environment"] == "Demo"
    assert meta["broker_symbol"] == "BTCUSD"
    assert meta["sha256"] == sha256_file(path) and len(meta["sha256"]) == 64
    assert meta["row_count"] == 1
    assert not ({"signal", "bias", "setup", "label", "target", "entry", "sl", "tp", "profit"} & set(frame.columns))

