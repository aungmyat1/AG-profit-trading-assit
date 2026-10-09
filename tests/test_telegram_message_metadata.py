import pytest

from host_delivery import telegram_message as tg


def record(broker_symbol, tick=0.25, digits=2):
    return {
        "canonical_symbol": broker_symbol,
        "broker_symbol": broker_symbol,
        "fields": {"trade_tick_size": tick, "digits": digits},
    }


def ticket(version=3):
    return {
        "label": "INFORMATIONAL TICKET -- NOT A BROKER ORDER",
        "strategy_id": "ST_LIQUIDITY_SWEEP_RETEST_V1",
        "strategy_version": "2.0.0",
        "symbol": "BTCUSDT",
        "ticket_config": f"AG_V1_CRYPTO_TICKET@v{version}",
        "cycle": "DAILY_WINDOW",
        "session_date": "2026-10-08",
        "decision": "READY",
        "direction": "LONG",
        "entry": 65000.13,
        "stop_loss": 64999.81,
        "risk_distance": 0.32,
        "tp1": 65001.13,
        "signal_close_utc": "2026-10-08T10:00:00+00:00",
        "data_source": "MT5_VT_MARKETS_DEMO",
    }


@pytest.mark.parametrize("version", [2, 3])
def test_crypto_ticket_uses_versioned_broker_symbol_metadata(version, monkeypatch):
    requested = []

    def load(symbol, root=None):
        requested.append(symbol)
        return record("BTCUSD") if symbol == "BTCUSD" else None

    monkeypatch.setattr(tg, "load_record", load)
    text = tg.format_ticket(ticket(version))
    assert requested[:2] == ["BTCUSDT", "BTCUSD"]
    assert "entry: 65000.25  stop: 64999.75  risk: 0.5 (price units)" in text
    assert "tp1: 65001.0  = +1.50R" in text
    assert "engine 0.32 (price units) before rounding" in text
    assert tg.UNNORMALIZED not in text


def test_public_crypto_ticket_without_mt5_metadata_remains_unnormalized(monkeypatch):
    monkeypatch.setattr(tg, "load_record", lambda *_args, **_kwargs: None)
    public_ticket = ticket()
    public_ticket.pop("ticket_config")
    public_ticket["data_source"] = "BYBIT_LINEAR_PERP"
    text = tg.format_ticket(public_ticket)
    assert "entry: 65000.13  stop: 64999.81" in text
    assert tg.UNNORMALIZED in text


def test_lsmc_crypto_alert_uses_exact_configured_broker_symbol(monkeypatch):
    requested = []

    def load(symbol, root=None):
        requested.append(symbol)
        return record("BTCUSD") if symbol == "BTCUSD" else None

    monkeypatch.setattr(tg, "load_record", load)
    event = {
        "symbol": "BTCUSDT", "display_broker_symbol": "BTCUSD", "to_state": "OPPORTUNITY",
        "alert_level": "OPPORTUNITY", "strategy_id": "ST_LARGE_SMC_V1", "strategy_version": "1.1.0",
        "reference_id": "ref-1",
        "payload": {
            "poi": {"kind": "H1", "low": 65000.11, "high": 65000.61},
            "opportunity": {"direction": "LONG", "entry_reference": 65000.13,
                            "stop_c10": 64999.81, "sweep_extreme": 64999.91,
                            "target_c11": 65001.13, "expires_at": "2026-10-08T11:00:00+00:00"},
        },
    }
    text = tg.format_alert(event, price=65000.4)
    assert requested[:2] == ["BTCUSDT", "BTCUSD"]
    assert "POI zone (H1): 65000.0 - 65000.5" in text
    assert "invalidation: M5 close below 64999.75" in text
    assert "liquidity target: 65001.0" in text
    assert "entry reference (CHoCH close): 65000.25" in text
    assert "current price: 65000.5" in text
    assert tg.UNNORMALIZED not in text


def test_mismatched_broker_metadata_is_not_used(monkeypatch):
    monkeypatch.setattr(tg, "load_record", lambda symbol, **_kwargs: record("ETHUSD") if symbol == "BTCUSD" else None)
    text = tg.format_ticket(ticket())
    assert "entry: 65000.13  stop: 64999.81" in text
    assert tg.UNNORMALIZED in text
