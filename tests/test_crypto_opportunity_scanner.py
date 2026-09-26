from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from crypto_opportunity_scanner.scanner import CryptoMarketWindow, ScannerInputError, scan_window
from opportunity.candidate_store import CandidateStore
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
    result = scan_window(_window(mode="SYNTHETIC", source="TEST_FIXTURE"),
                         store=CandidateStore(str(tmp_path / "candidates.json")))
    assert result.status == "OPPORTUNITY_UPDATED"
    assert result.candidate is not None and result.candidate.direction is None
    assert result.candidate.geometry is None
    assert result.candidate.market_data_mode == "SYNTHETIC"
    assert result.candidate.context_evidence["classification"] == "RESEARCH / OBSERVATION"
    assert result.marketstate.facts["sweep"]["detected"] is True
    assert result.marketstate.facts["provenance"]["provider"] == "TEST_FIXTURE"
    assert result.candidate.context_evidence["economic_validation"] == "NOT_ESTABLISHED"


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


def test_fixture_cannot_claim_real_bybit_provenance():
    with pytest.raises(ScannerInputError, match="REAL_MODE_REQUIRES_LIVE_FEED_ENTRYPOINT"):
        scan_window(_window(mode="REAL", source="BYBIT_LINEAR_PERP"))


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
