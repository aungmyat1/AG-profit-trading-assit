from __future__ import annotations

import ast
import inspect
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import crypto_opportunity_scanner.scanner as scanner
import execution_runtime.bybit_linear_perp_feed as bybit_feed
from crypto_opportunity_scanner.scanner import (
    CryptoMarketWindow,
    ScannerInputError,
    _evaluate_sweep,
    _form_offline_opportunity,
    _marketstate,
    _scan_window,
    _validate_window,
    scan_live_once,
    scan_window,
)
from opportunity.candidate_store import CandidateStore
from execution_runtime.bybit_linear_perp_feed import BybitFeedRequestError
from strategy_engine.session import Candle


def _window(*, mode="REAL", source="BYBIT_LINEAR_PERP", observed_at=None, sweep=True):
    # 288 closed bars on Sep 25, followed by the first current-day M5 bar.
    day = datetime(2026, 9, 25, tzinfo=timezone.utc)
    candles = [
        Candle(day + timedelta(minutes=5 * i), 100.0, 105.0, 95.0, 100.0, 1.0)
        for i in range(288)
    ]
    candles[0] = Candle(candles[0].time, 100.0, 110.0, 90.0, 100.0, 1.0)
    candles.append(Candle(day + timedelta(days=1), 100.0,
                          111.0 if sweep else 105.0, 95.0, 109.0 if sweep else 100.0, 1.0))
    observed = observed_at or candles[-1].time + timedelta(minutes=5, seconds=2)
    return CryptoMarketWindow(tuple(candles), observed, mode, source)


def test_closed_previous_day_sweep_creates_observation_only_candidate(tmp_path):
    store = CandidateStore(str(tmp_path / "candidates.json"))
    result = scan_window(_window(mode="SYNTHETIC", source="TEST_FIXTURE"), store=store)
    assert result.status == "OPPORTUNITY_UPDATED"
    assert result.candidate is not None and result.candidate.direction is None
    assert result.candidate.geometry is None
    assert result.candidate.market_data_mode == "SYNTHETIC"
    assert result.candidate.context_evidence["classification"] == "RESEARCH / OBSERVATION"
    assert result.marketstate.facts["sweep"]["detected"] is True
    assert result.marketstate.facts["provenance"]["provider"] == "TEST_FIXTURE"
    assert result.candidate.context_evidence["economic_validation"] == "NOT_ESTABLISHED"
    assert all(candidate.market_data_mode != "REAL" for candidate in store.all_candidates())


def test_no_sweep_returns_no_candidate():
    result = scan_window(_window(mode="SYNTHETIC", source="TEST_FIXTURE", sweep=False))
    assert result.status == "NO_OPPORTUNITY" and result.candidate is None


@pytest.mark.parametrize(("mode", "source", "expected"), [
    ("SYNTHETIC", "TEST_FIXTURE", "SYNTHETIC"),
    ("REPLAY", "ARCHIVED_CAPTURE", "REPLAY"),
])
def test_fixture_provenance_is_not_promoted(mode, source, expected, tmp_path):
    store = CandidateStore(str(tmp_path / f"{expected.lower()}-candidates.json"))
    result = scan_window(_window(mode=mode, source=source), store=store)
    assert result.candidate.market_data_mode == expected
    assert result.marketstate.facts["provenance"]["provider"] == source
    assert all(candidate.market_data_mode != "REAL" for candidate in store.all_candidates())


def test_stale_and_forming_windows_fail_closed(tmp_path):
    window = _window(mode="SYNTHETIC", source="TEST_FIXTURE",
                     observed_at=datetime(2026, 9, 26, 0, 4, tzinfo=timezone.utc))
    with pytest.raises(ScannerInputError, match="FORMING_CANDLE_REJECTED"):
        scan_window(window, store=CandidateStore(str(tmp_path / "forming.json")))
    stale = _window(mode="SYNTHETIC", source="TEST_FIXTURE")
    stale = CryptoMarketWindow(stale.candles, stale.observed_at, stale.market_data_mode,
                               stale.source, freshness="STALE")
    with pytest.raises(ScannerInputError, match="MARKET_WINDOW_NOT_FRESH"):
        scan_window(stale, store=CandidateStore(str(tmp_path / "stale.json")))


def test_closed_candle_age_is_checked_independently_of_fx_sessions():
    stale_observation_time = datetime(2026, 9, 26, 0, 21, tzinfo=timezone.utc)
    with pytest.raises(ScannerInputError, match="LATEST_CLOSED_CANDLE_EXCEEDS_AGE_LIMIT"):
        scan_window(_window(mode="SYNTHETIC", source="TEST_FIXTURE",
                            observed_at=stale_observation_time))


def test_fixture_cannot_claim_real_bybit_provenance(tmp_path):
    store = CandidateStore(str(tmp_path / "caller-real-window.json"))
    with pytest.raises(ScannerInputError, match="REAL_MODE_REQUIRES_LIVE_FEED_ENTRYPOINT"):
        scan_window(_window(mode="REAL", source="BYBIT_LINEAR_PERP"), store=store)
    assert not store.all_candidates()


@pytest.mark.parametrize("source", ["TEST_FIXTURE", "ARCHIVED_CAPTURE", "TEST_SYNTHETIC"])
def test_direct_scanner_helper_cannot_forge_real_provenance(source, tmp_path):
    window = _window(mode="REAL", source=source)
    store = CandidateStore(str(tmp_path / f"forged-{source}.json"))
    with pytest.raises(ScannerInputError, match="REAL_MODE_REQUIRES_PUBLIC_FEED_ENTRYPOINT"):
        _scan_window(window, store=store)
    assert not store.all_candidates()
    bybit_labeled = _window(mode="REAL", source="BYBIT_LINEAR_PERP")
    evaluation = _evaluate_sweep(bybit_labeled, _validate_window(bybit_labeled))
    with pytest.raises(ScannerInputError, match="REAL_MARKETSTATE_REQUIRES_PUBLIC_FEED_ENTRYPOINT"):
        _marketstate(bybit_labeled, evaluation.latest, evaluation.sweep)
    with pytest.raises(ScannerInputError, match="REAL_MODE_REQUIRES_PUBLIC_FEED_ENTRYPOINT"):
        _form_offline_opportunity(bybit_labeled, evaluation, None)


def test_public_production_entrypoint_owns_feed_acquisition_and_rejects_window_injection(tmp_path):
    assert "window" not in inspect.signature(scan_live_once).parameters
    store = CandidateStore(str(tmp_path / "window-injection.json"))
    with pytest.raises(TypeError):
        scan_live_once(window=_window(mode="REAL", source="BYBIT_LINEAR_PERP"), store=store)
    assert not store.all_candidates()
    assert not hasattr(scanner, "_LIVE_FEED_WINDOWS")


def test_test_double_production_composition_forms_real_only_after_feed_success(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc)
    latest_open = now.replace(second=0, microsecond=0, minute=(now.minute // 5) * 5) - timedelta(minutes=5)
    start = latest_open - timedelta(minutes=5 * 719)
    candles = [
        Candle(start + timedelta(minutes=5 * index), 100.0, 105.0, 95.0, 100.0, 1.0)
        for index in range(720)
    ]
    candles[-1] = Candle(latest_open, 100.0, 111.0, 95.0, 100.0, 1.0)
    rows = [
        [str(int(c.time.timestamp() * 1000)), str(c.open), str(c.high), str(c.low), str(c.close), str(c.volume), "0"]
        for c in candles
    ]
    payload = {
        "retCode": 0, "retMsg": "OK",
        "result": {"category": "linear", "symbol": "BTCUSDT", "list": list(reversed(rows))},
        "time": 0,
    }

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return payload

    class FakeSession:
        def __init__(self):
            self.calls = []

        def get(self, url, params=None, timeout=None):
            self.calls.append((url, params, timeout))
            return FakeResponse()

    session = FakeSession()

    def fake_feed_init(self):
        self._http = session
        self._clock = lambda: now
        self._base_url = "https://offline.invalid"
        self._timeout = 1

    monkeypatch.setattr(scanner.BybitLinearPerpFeed, "__init__", fake_feed_init)
    store = CandidateStore(str(tmp_path / "test-double-live.json"))
    result = scan_live_once(store=store)

    assert session.calls[0][1]["symbol"] == "BTCUSDT"
    assert session.calls[0][1]["interval"] == "5"
    assert result.status == "OPPORTUNITY_UPDATED"
    assert result.candidate.market_data_mode == "REAL"
    assert result.marketstate.facts["provenance"]["provider"] == "BYBIT"
    assert len(store.all_candidates()) == 1


def test_scanner_rejects_unverified_or_mismatched_feed_identity(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc)
    latest_open = now.replace(second=0, microsecond=0, minute=(now.minute // 5) * 5) - timedelta(minutes=5)
    rows = [
        [str(int((latest_open - timedelta(minutes=5 * (4 - i))).timestamp() * 1000)), "100", "105", "95", "100", "1", "0"]
        for i in range(5)
    ]
    payload = {
        "retCode": 0, "retMsg": "OK",
        "result": {"category": "linear", "symbol": "BTCUSDT", "list": list(reversed(rows))},
        "time": 0,
    }

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return payload

    class FakeSession:
        def get(self, url, params=None, timeout=None):
            return FakeResponse()

    batch = bybit_feed.BybitLinearPerpFeed(session=FakeSession(), clock=lambda: now).get_latest_candles(
        "BTCUSDT", "M5", 5,
    )
    monkeypatch.setattr(bybit_feed.BybitCandleBatch, "symbol", property(lambda self: "ETHUSDT"))
    store = CandidateStore(str(tmp_path / "wrong-feed-identity.json"))
    evaluated = []
    monkeypatch.setattr(scanner.BybitLinearPerpFeed, "get_latest_candles", lambda *args: batch)
    monkeypatch.setattr(scanner, "_evaluate_sweep", lambda *args: evaluated.append(args))
    result = scan_live_once(store=store)

    assert result.status == "INVALID_RESPONSE"
    assert result.reason_code == "KLINES_IDENTITY_MISMATCH"
    assert result.candidate is None and result.marketstate is None
    assert not evaluated
    assert not store.all_candidates()


def test_scanner_rejects_plain_candle_list_without_feed_identity(monkeypatch, tmp_path):
    candles = list(_window(mode="SYNTHETIC", source="TEST_FIXTURE").candles)
    store = CandidateStore(str(tmp_path / "unverified-feed-identity.json"))
    monkeypatch.setattr(
        scanner.BybitLinearPerpFeed,
        "get_latest_candles",
        lambda self, symbol, timeframe, count: candles,
    )
    result = scan_live_once(store=store)
    assert result.status == "INVALID_RESPONSE"
    assert result.reason_code == "KLINES_IDENTITY_UNVERIFIED"
    assert result.candidate is None and result.marketstate is None
    assert not store.all_candidates()


@pytest.mark.parametrize(
    ("response_symbol", "remove_symbol", "response_category", "remove_category", "expected_reason"),
    [
        ("ETHUSDT", False, "linear", False, "KLINES_SYMBOL_MISMATCH"),
        ("", False, "linear", False, "KLINES_SYMBOL_MISSING"),
        (None, False, "linear", False, "KLINES_SYMBOL_MISSING"),
        (None, True, "linear", False, "KLINES_SYMBOL_MISSING"),
        ("btcUsdt", False, "linear", False, "KLINES_SYMBOL_MISMATCH"),
        ("BTCUSDT", False, "spot", False, "KLINES_CATEGORY_MISMATCH"),
        ("BTCUSDT", False, None, True, "KLINES_CATEGORY_MISSING"),
    ],
)
def test_untrusted_http_identity_stops_before_strategy_or_persistence(
    monkeypatch, tmp_path, response_symbol, remove_symbol, response_category, remove_category, expected_reason,
):
    now = datetime.now(timezone.utc)
    latest_open = now.replace(second=0, microsecond=0, minute=(now.minute // 5) * 5)
    rows = []
    for index in range(5):
        opened = latest_open - timedelta(minutes=5 * (4 - index))
        rows.append([
            str(int(opened.timestamp() * 1000)), "100", "105", "95", "100", "1", "0",
        ])
    payload = {
        "retCode": 0,
        "retMsg": "OK",
        "result": {
            "category": response_category,
            "symbol": response_symbol,
            "list": list(reversed(rows)),
        },
        "time": 0,
    }
    if remove_symbol:
        del payload["result"]["symbol"]
    if remove_category:
        del payload["result"]["category"]

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return payload

    class FakeSession:
        def get(self, url, params=None, timeout=None):
            assert params["symbol"] == "BTCUSDT"
            return FakeResponse()

    session = FakeSession()
    def fake_feed_init(self):
        self._http = session
        self._clock = lambda: now
        self._base_url = "https://offline.invalid"
        self._timeout = 1

    monkeypatch.setattr(scanner.BybitLinearPerpFeed, "__init__", fake_feed_init)
    evaluated = []
    monkeypatch.setattr(scanner, "_evaluate_sweep", lambda *args: evaluated.append(args))
    store = CandidateStore(str(tmp_path / "wrong-symbol-http.json"))

    result = scan_live_once(store=store)

    assert result.status == "INVALID_RESPONSE"
    assert result.reason_code == expected_reason
    assert result.candidate is None and result.marketstate is None
    assert not evaluated
    assert not store.all_candidates()


def test_failed_public_feed_acquisition_cannot_create_real_opportunity(monkeypatch, tmp_path):
    def fail_public_feed(self, symbol, timeframe, count):
        raise BybitFeedRequestError("KLINES_REQUEST_FAILED", "HTTP 403 Forbidden")

    monkeypatch.setattr(scanner.BybitLinearPerpFeed, "get_latest_candles", fail_public_feed)
    store = CandidateStore(str(tmp_path / "failed-feed.json"))
    result = scan_live_once(store=store)
    assert result.status == "VENUE_UNAVAILABLE"
    assert result.candidate is None
    assert result.marketstate is None
    assert not store.all_candidates()


def test_repeat_event_is_deduplicated_and_new_bar_gets_new_identity(tmp_path):
    store = CandidateStore(str(tmp_path / "candidates.json"))
    window = _window(mode="SYNTHETIC", source="TEST_FIXTURE")
    first = scan_window(window, store=store)
    repeated = scan_window(window, store=store)
    assert repeated.status == "UNCHANGED" and repeated.deduplicated is True
    assert repeated.candidate.candidate_id == first.candidate.candidate_id
    candles = list(window.candles)
    stamp = candles[-1].time + timedelta(minutes=5)
    candles.append(Candle(stamp, 100.0, 111.0, 95.0, 109.0, 1.0))
    later = scan_window(CryptoMarketWindow(tuple(candles), stamp + timedelta(minutes=5, seconds=2),
                                           "SYNTHETIC", "TEST_FIXTURE"), store=store)
    assert later.candidate.candidate_id != first.candidate.candidate_id


def test_observation_time_does_not_change_identity(tmp_path):
    store = CandidateStore(str(tmp_path / "observation-time.json"))
    first_window = _window(mode="SYNTHETIC", source="TEST_FIXTURE")
    first = scan_window(first_window, store=store)
    repeated = scan_window(
        CryptoMarketWindow(
            first_window.candles,
            first_window.observed_at + timedelta(minutes=1),
            "SYNTHETIC",
            "TEST_FIXTURE",
        ),
        store=store,
    )
    assert repeated.candidate.candidate_id == first.candidate.candidate_id
    assert repeated.status == "UNCHANGED" and repeated.deduplicated is True
    assert len(store.all_candidates()) == 1


def test_incomplete_prior_day_fails_closed():
    window = _window(mode="SYNTHETIC", source="TEST_FIXTURE")
    with pytest.raises(ScannerInputError):
        scan_window(CryptoMarketWindow(window.candles[1:], window.observed_at,
                                       window.market_data_mode, window.source))


def test_fresh_weekend_market_data_is_allowed(tmp_path):
    saturday = datetime(2026, 9, 26, tzinfo=timezone.utc)
    window = _window()
    candles = list(window.candles)
    candles = [
        Candle(saturday + timedelta(minutes=5 * i), 100.0, 105.0, 95.0, 100.0, 1.0)
        for i in range(288)
    ]
    candles[0] = Candle(candles[0].time, 100.0, 110.0, 90.0, 100.0, 1.0)
    sunday = saturday + timedelta(days=1)
    candles.append(Candle(sunday, 100.0, 105.0, 95.0, 100.0, 1.0))
    result = scan_window(CryptoMarketWindow(
        tuple(candles), sunday + timedelta(minutes=5, seconds=1),
        "SYNTHETIC", "TEST_FIXTURE",
    ), store=CandidateStore(str(tmp_path / "weekend.json")))
    assert result.status == "NO_OPPORTUNITY"


def test_owner_readable_api_lists_observation_without_execution_authority(tmp_path):
    from api.crypto_opportunities import list_crypto_opportunities

    store_path = str(tmp_path / "api-candidates.json")
    store = CandidateStore(store_path)
    scan_window(_window(mode="SYNTHETIC", source="TEST_FIXTURE"), store=store)
    rows = list_crypto_opportunities(symbol="btcusdt", store_path=store_path)
    assert len(rows) == 1
    assert rows[0]["symbol"] == "BTCUSDT"
    assert rows[0]["venue"] == "BYBIT_LINEAR_PERP"
    assert rows[0]["strategy_id"] == "CRYPTO_PREVIOUS_DAY_SWEEP_OBSERVATION_V1"
    assert rows[0]["market_data_mode"] == "SYNTHETIC"
    assert rows[0]["geometry"] is None
    assert "execution_authority" not in rows[0]


def test_naive_timestamp_fails_closed():
    window = _window()
    candles = list(window.candles)
    candles[-1] = Candle(candles[-1].time.replace(tzinfo=None), 100.0, 105.0, 95.0, 100.0, 1.0)
    with pytest.raises(ScannerInputError, match="MUST_BE_TIMEZONE_AWARE"):
        scan_window(CryptoMarketWindow(tuple(candles), window.observed_at, "SYNTHETIC", "TEST_FIXTURE"))


def test_malformed_ohlc_fails_closed():
    window = _window(mode="SYNTHETIC", source="TEST_FIXTURE")
    candles = list(window.candles)
    item = candles[-1]
    candles[-1] = Candle(item.time, item.open, item.high, item.high + 1, item.close, item.volume)
    with pytest.raises(ScannerInputError, match="INVALID_CANDLE_OHLC_OR_VOLUME"):
        scan_window(CryptoMarketWindow(tuple(candles), window.observed_at, "SYNTHETIC", "TEST_FIXTURE"))


def test_actual_api_route_is_read_only_candidate_projection(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import api.app as api_module
    from api.crypto_opportunities import list_crypto_opportunities

    store_path = str(tmp_path / "route-candidates.json")
    scan_window(_window(mode="SYNTHETIC", source="TEST_FIXTURE"),
                store=CandidateStore(store_path))
    monkeypatch.setattr(
        api_module,
        "list_crypto_opportunities",
        lambda symbol=None, limit=50: list_crypto_opportunities(
            symbol=symbol, store_path=store_path, limit=limit,
        ),
    )
    response = TestClient(api_module.app).get("/api/opportunities?symbol=btcusdt")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1 and body[0]["symbol"] == "BTCUSDT"
    assert body[0]["strategy_id"] == "CRYPTO_PREVIOUS_DAY_SWEEP_OBSERVATION_V1"
    assert body[0]["geometry"] is None
    assert "execution_authority" not in body[0]


def test_scanner_has_no_proposal_execution_or_private_broker_imports():
    tree = ast.parse(Path("src/crypto_opportunity_scanner/scanner.py").read_text(encoding="utf-8"))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.add(node.module or "")
    forbidden = ("proposal_envelope", "proposals", "execution.executor", "execution.risk",
                 "mt5.management_gateway", "broker")
    assert not [module for module in modules if any(item in module for item in forbidden)]
