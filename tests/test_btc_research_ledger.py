"""btc_sweep_research.ledger.BTCResearchLedger -- new uncapped, occurrence_id-deduplicated
research observation ledger (spec section 21/22). Distinct from any position/trade
ledger -- tested here purely as a JsonKeyValueStore-backed dedup store."""
from __future__ import annotations

import datetime as dt

from btc_sweep_research.ledger import BTCResearchLedger
from btc_sweep_research.proposal import AUTHORITY_RESEARCH_ONLY, BTCSweepResearchProposal

UTC = dt.timezone.utc


def _proposal(occurrence_id="BTC-OCC-abc123", **overrides):
    kwargs = dict(
        strategy="ST_LIQUIDITY_SWEEP_RETEST_V1", strategy_version="2.0.0", authority=AUTHORITY_RESEARCH_ONLY,
        exchange="BINANCE_USDT_M_PERP", instrument="BTCUSDT", direction="SHORT",
        reference_day=dt.date(2026, 1, 4), reference_high=42000.0, reference_low=40700.0,
        sweep={"level": 42000.0, "extreme": 42150.0, "time": dt.datetime(2026, 1, 5, 13, 45, tzinfo=UTC)},
        confirmation={"broken_swing_price": 41600.0, "mss_time": dt.datetime(2026, 1, 5, 14, 0, tzinfo=UTC)},
        entry=41620.0, stop=42151.0, target={"tp1": 41350.0, "tp2": 40700.0}, RR=1.6,
        estimated_fees=1.23, funding_assumption={"note": "placeholder"},
        data_timestamp=dt.datetime(2026, 1, 5, 14, 15, tzinfo=UTC),
        expiry=dt.datetime(2026, 1, 5, 16, 0, tzinfo=UTC), occurrence_id=occurrence_id,
    )
    kwargs.update(overrides)
    return BTCSweepResearchProposal(**kwargs)


def test_record_new_occurrence_returns_true(tmp_path):
    ledger = BTCResearchLedger(str(tmp_path / "occ.json"))
    assert ledger.record(_proposal()) is True
    assert ledger.has("BTC-OCC-abc123")
    assert ledger.count() == 1


def test_record_duplicate_occurrence_is_noop(tmp_path):
    ledger = BTCResearchLedger(str(tmp_path / "occ.json"))
    assert ledger.record(_proposal()) is True
    assert ledger.record(_proposal(entry=99999.0)) is False  # same occurrence_id, different payload
    stored = ledger.get("BTC-OCC-abc123")
    assert stored["entry"] == 41620.0  # first observation preserved, never overwritten
    assert ledger.count() == 1


def test_distinct_occurrences_both_preserved(tmp_path):
    ledger = BTCResearchLedger(str(tmp_path / "occ.json"))
    ledger.record(_proposal(occurrence_id="BTC-OCC-aaa"))
    ledger.record(_proposal(occurrence_id="BTC-OCC-bbb"))
    assert ledger.count() == 2
    assert ledger.has("BTC-OCC-aaa")
    assert ledger.has("BTC-OCC-bbb")


def test_datetimes_serialized_to_iso(tmp_path):
    ledger = BTCResearchLedger(str(tmp_path / "occ.json"))
    ledger.record(_proposal())
    stored = ledger.get("BTC-OCC-abc123")
    assert stored["reference_day"] == "2026-01-04"
    assert stored["data_timestamp"] == "2026-01-05T14:15:00+00:00"
    assert stored["sweep"]["time"] == "2026-01-05T13:45:00+00:00"
