from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "scripts"))

import audit_lsmc_v111_candidate as audit  # noqa: E402
from _lsmc_v111_fixtures import fixture_manifest, fixture_symbols, load_fixture  # noqa: E402


def _price_values(symbol: str) -> set[float]:
    fixture = load_fixture(symbol)
    return {
        getattr(candle, field)
        for timeframe in ("D1", "H1", "M5")
        for candle in fixture[timeframe]
        for field in ("open", "high", "low", "close")
    }


def test_candidate_fixtures_are_per_symbol_and_have_no_reused_ohlc_values() -> None:
    symbols = fixture_symbols()
    assert symbols == ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSDT", "ETHUSDT")
    value_sets = {symbol: _price_values(symbol) for symbol in symbols}
    for index, left in enumerate(symbols):
        for right in symbols[index + 1 :]:
            assert value_sets[left].isdisjoint(value_sets[right]), f"OHLC price reused across {left}/{right}"

    manifest = fixture_manifest()
    classifications = {item["symbol"]: item["classification"] for item in manifest["sources"]}
    assert classifications == {
        "EURUSD": "HOST_CAPTURED_DERIVED",
        "GBPUSD": "MIXED_HOST_CONTEXT_AND_SYNTHETIC",
        "USDJPY": "SYNTHETIC",
        "XAUUSD": "SYNTHETIC",
        "BTCUSDT": "SYNTHETIC",
        "ETHUSDT": "SYNTHETIC",
    }
    assert "GEN_002" not in json.dumps(manifest)
    for record in manifest["fixtures"]:
        fixture_path = ROOT / record["fixture_file"]
        assert hashlib.sha256(fixture_path.read_bytes()).hexdigest() == record["fixture_sha256"]
    gbp = next(item for item in manifest["sources"] if item["symbol"] == "GBPUSD")
    assert gbp["admission_role"] == "WARMUP_CONTEXT_ONLY"
    assert gbp["timeframes"] == {
        "H1": "HOST_CAPTURED_WARMUP_CONTEXT_ONLY",
        "M5": "SYNTHETIC",
        "D1": "SYNTHETIC",
    }


def test_candidate_records_c11_primary_and_h1_fallback_per_ticket() -> None:
    rows = {row["symbol"]: row for row in audit.run()}
    assert rows["EURUSD"]["state"] == "NEAR_POI"
    assert rows["EURUSD"]["C11_source"] == "NO_TICKET"
    assert rows["GBPUSD"]["C11_source"] == "NO_TICKET"
    broker_symbols = {
        "EURUSD": "EURUSD", "GBPUSD": "GBPUSD", "USDJPY": "USDJPY",
        "XAUUSD": "XAUUSD", "BTCUSDT": "BTCUSD", "ETHUSDT": "ETHUSD",
    }
    for symbol, broker_symbol in broker_symbols.items():
        assert rows[symbol]["broker_symbol"] == broker_symbol
        assert rows[symbol]["point_status"] == "HOST_CAPTURED"

    for symbol in ("USDJPY", "BTCUSDT", "ETHUSDT"):
        row = rows[symbol]
        assert row["opportunity_ticket"] is True
        assert row["C11_source"] == audit.C11_PRIMARY
        assert row["C11_selector_tier"] == "PRIMARY_EXTERNAL_LIQUIDITY"
        assert row["C11_target_tier"] == "PRIMARY_EXTERNAL_LIQUIDITY"
        assert row["C11_status_at_selection"] == "UNSWEPT"
        assert row["C11_target_price"] is not None
        assert row["ticket_c11_source"] == row["C11_source"]
        assert row["ticket_signal_timestamp"] is not None

    fallback = rows["XAUUSD"]
    assert fallback["opportunity_ticket"] is True
    assert fallback["C11_source"] == audit.C11_H1_FALLBACK
    assert fallback["C11_target_tier"] == "FALLBACK_H1_SWING"
    assert fallback["C11_target_price"] is not None
    assert fallback["C11_selector_reason"] == "REJECT_NO_TARGET"
    assert fallback["ticket_c11_source"] == audit.C11_H1_FALLBACK
    assert fallback["ticket_signal_timestamp"] is not None


def test_candidate_ignores_core_legacy_m5_fallback_and_uses_confirmed_h1(monkeypatch) -> None:
    bars = load_fixture("USDJPY")
    base = audit.evaluate_snapshot("USDJPY", bars["D1"], bars["H1"], bars["M5"], bars["evaluated_at"])
    opportunity = dict(base.opportunity or {})
    opportunity["symbol"] = "USDJPY"
    assert opportunity

    fake_core_fallback = SimpleNamespace(
        found=True,
        target_price=999.0,
        target_tier="FALLBACK_M5_SWING",
        target_source="market_structure.tiers.StructureTier.swings",
        target_source_id="intentionally-ignored-m5-fallback",
        target_status_at_selection="UNSWEPT",
        target_evidence_timestamp=None,
        reason="FALLBACK_TIER_CONFIRMED_M5_SWING_EXTREMUM",
    )
    monkeypatch.setattr(audit, "select_target", lambda **_kwargs: fake_core_fallback)

    spec = yaml.safe_load((ROOT / "strategies/ST_LARGE_SMC_V1_1_1_1.yaml").read_text(encoding="utf-8"))
    result = audit._candidate_target(spec, opportunity, bars["H1"], bars["M5"])
    assert result["c11_source"] == audit.C11_H1_FALLBACK
    assert result["tier"] == "FALLBACK_H1_SWING"
    assert result["price"] != 999.0
    assert result["core_m5_fallback_ignored"] is True


def test_h1_fallback_fails_closed_on_equal_distance_tie(monkeypatch) -> None:
    swings = [
        SimpleNamespace(kind="high", price=1.30, known_at=3, index=1),
        SimpleNamespace(kind="high", price=1.30, known_at=5, index=3),
    ]
    monkeypatch.setattr(audit.F, "swings", lambda _h1, _k: swings)
    result = audit._h1_fallback_target("LONG", 1.20, [object()] * 6)
    assert result["price"] is None
    assert result["reason"] == "AMBIGUOUS_TARGET"


def test_candidate_rr_minimum_is_pending_and_all_pip_sizes_remain_unconfirmed() -> None:
    spec = yaml.safe_load((ROOT / "strategies/ST_LARGE_SMC_V1_1_1_1.yaml").read_text(encoding="utf-8"))
    rr = spec["rules"]["reward_risk"]
    recording = spec["rules"]["targets"]["recording"]
    assert recording["ticket_field"] == "c11_source"
    assert recording["required_for_every_opportunity_ticket"] is True
    assert rr["minimum_rr"] == 2.0
    assert rr["minimum_rr_status"] == "PENDING_OWNER_CONFIRM"
    assert rr["owner_confirmation"] == "PENDING_OWNER_CONFIRM"
    for symbol in fixture_symbols():
        metadata = spec["symbol_metadata"][symbol]
        assert metadata["pip_size"] is None
        assert metadata["pip_size_status"] == "PIP_SIZE_UNCONFIRMED"

    rows = {row["symbol"]: row for row in audit.run()}
    for symbol in ("USDJPY", "XAUUSD", "BTCUSDT", "ETHUSDT"):
        assert rows[symbol]["C10"] == "PIP_SIZE_UNCONFIRMED"
        assert rows[symbol]["RR_minimum"] == 2.0
        assert rows[symbol]["RR_minimum_status"] == "PENDING_OWNER_CONFIRM"
        assert rows[symbol]["RR"] == "RR_UNDEFINED_C10_STOP_UNAVAILABLE"
        assert rows[symbol]["L2"] == "FAIL"
        assert rows[symbol]["L3"] == "FAIL"


def test_candidate_host_point_sources_and_pip_rules_remain_pending() -> None:
    from host_evidence.symbol_metadata import HOST_CAPTURED, load_record

    spec = yaml.safe_load((ROOT / "strategies/ST_LARGE_SMC_V1_1_1_1.yaml").read_text(encoding="utf-8"))
    provenance = spec["candidate_provenance"]
    port_source = "ported from uncommitted 1.1.0 worktree diff 3673bad3"
    assert provenance["broker_symbol_aliases"] == port_source
    assert provenance["host_captured_metadata_status"] == port_source
    assert spec["broker_symbol_aliases"] == {"BTCUSD": "BTCUSDT", "ETHUSD": "ETHUSDT"}
    assert spec["parameter_provenance"] == (
        "assistant-recommended under owner delegation, PENDING_OWNER_CONFIRM, 2026-10-08"
    )

    broker_symbols = {
        "EURUSD": "EURUSD",
        "GBPUSD": "GBPUSD",
        "USDJPY": "USDJPY",
        "XAUUSD": "XAUUSD",
        "BTCUSDT": "BTCUSD",
        "ETHUSDT": "ETHUSD",
    }
    for symbol, broker_symbol in broker_symbols.items():
        record = load_record(broker_symbol)
        assert record is not None, broker_symbol
        metadata = spec["symbol_metadata"][symbol]
        if symbol in {"BTCUSDT", "ETHUSDT"}:
            assert metadata["broker_metadata_status"] == HOST_CAPTURED
            assert metadata["broker_point_source"] == (
                f"config/symbol_metadata/host_captured/{broker_symbol}.json"
            )
            assert metadata["broker_metadata_record_sha256"] == record["sha256"]
            captured_point = metadata["broker_point"]
        else:
            assert metadata["point_status"] == HOST_CAPTURED
            assert metadata["status"] == HOST_CAPTURED
            assert metadata["point_source"] == (
                f"config/symbol_metadata/host_captured/{broker_symbol}.json"
            )
            assert metadata["point_record_sha256"] == record["sha256"]
            captured_point = metadata["point"]
        assert captured_point == record["fields"]["point"], symbol
        assert metadata["pip_size"] is None
        assert metadata["pip_size_status"] == "PIP_SIZE_UNCONFIRMED"

    for broker_symbol in ("BTCUSD", "ETHUSD"):
        assert spec["symbol_metadata"][broker_symbol]["status"] == HOST_CAPTURED
        assert spec["symbol_metadata"][broker_symbol]["point_record_sha256"] == (
            load_record(broker_symbol)["sha256"]
        )

    proposed = spec["pip_size_rules"]["proposals"]
    assert spec["pip_size_rules"]["status"] == "PENDING_OWNER_CONFIRM"
    assert proposed["FX_5_OR_3_DIGIT"]["proposed_formula"] == (
        "pip_size = 10 * host_captured_point"
    )
    assert all(item["status"] == "PENDING_OWNER_CONFIRM" for item in proposed.values())
    assert proposed["XAUUSD"]["proposed_pip_size"] == 0.1
    assert proposed["BTCUSD"]["proposed_price_unit"] == 1.0
    assert proposed["ETHUSD"]["proposed_price_unit"] == 0.1


def test_candidate_host_point_resolver_is_scoped_to_the_read_only_audit() -> None:
    spec = yaml.safe_load((ROOT / "strategies/ST_LARGE_SMC_V1_1_1_1.yaml").read_text(encoding="utf-8"))
    bars = load_fixture("USDJPY")
    resolver = audit.C.resolve_point
    audit._evaluate_with_captured_points(
        spec, "USDJPY", bars["D1"], bars["H1"], bars["M5"], bars["evaluated_at"],
    )
    assert audit.C.resolve_point is resolver


def test_c10_distinguishes_missing_capture_from_pending_pip_rule(monkeypatch) -> None:
    spec = yaml.safe_load((ROOT / "strategies/ST_LARGE_SMC_V1_1_1_1.yaml").read_text(encoding="utf-8"))
    bars = load_fixture("USDJPY")
    base = audit.evaluate_snapshot("USDJPY", bars["D1"], bars["H1"], bars["M5"], bars["evaluated_at"])
    opportunity = dict(base.opportunity or {})
    opportunity["symbol"] = "USDJPY"
    assert audit._candidate_stop(spec, "USDJPY", opportunity, bars["M5"]) == (
        None, "PIP_SIZE_UNCONFIRMED",
    )

    monkeypatch.setattr(audit, "load_host_symbol_metadata", lambda _symbol: None)
    assert audit._candidate_stop(spec, "USDJPY", opportunity, bars["M5"]) == (
        None, "C10_PIP_SIZE_NOT_EVIDENCED",
    )


def test_synthetic_labelled_fixtures_are_blocked_from_qualification_and_evidence() -> None:
    """Fixture loading is permitted for the isolated logic audit only. Carry each
    manifest label into the production qualification/proposal boundary and prove
    non-live fixtures cannot become qualifying or complete-candle evidence."""
    from opportunity.contracts import (
        ELIGIBILITY_BLOCKED,
        MARKET_DATA_MODE_REPLAY,
        MARKET_DATA_MODE_SYNTHETIC,
        CandidateGeometry,
        OpportunityCandidate,
        REPLAY_DATA_NOT_BROKER_EXECUTABLE,
        SYNTHETIC_DATA_NOT_PROPOSAL_ELIGIBLE,
    )
    from opportunity.proposal_eligibility import evaluate_proposal_eligibility
    from opportunity.registry_binding import StrategyBinding
    from opportunity.stages import OUTCOME_ACTIVE, STAGE_ENTRY_CONFIRMED
    from proposal_envelope.adapters.opportunity_adapter import to_canonical_proposal
    from proposal_envelope.models import PROPOSAL_BLOCKED, WATCHER_DATA_BLOCKED

    manifest = fixture_manifest()
    synthetic_symbols: set[str] = set()
    replay_symbols: set[str] = set()
    for source in manifest["sources"]:
        symbol = source["symbol"]
        has_synthetic_component = (
            source["classification"] == "SYNTHETIC"
            or any(label == "SYNTHETIC" for label in source.get("timeframes", {}).values())
        )
        mode = MARKET_DATA_MODE_SYNTHETIC if has_synthetic_component else MARKET_DATA_MODE_REPLAY
        expected_reason = (
            SYNTHETIC_DATA_NOT_PROPOSAL_ELIGIBLE
            if has_synthetic_component
            else REPLAY_DATA_NOT_BROKER_EXECUTABLE
        )
        (synthetic_symbols if has_synthetic_component else replay_symbols).add(symbol)

        fixture = load_fixture(symbol)
        now = fixture["evaluated_at"]
        last_m5 = fixture["M5"][-1]
        stop = last_m5.low if last_m5.low < last_m5.close else last_m5.close - 1.0
        candidate = OpportunityCandidate(
            candidate_id=f"fixture:{symbol}",
            occurrence_id=f"fixture-occurrence:{symbol}",
            strategy_id="ST_LARGE_SMC_V1",
            strategy_version="1.1.1",
            strategy_engine_version=None,
            symbol=symbol,
            market=("FX" if symbol in {"EURUSD", "GBPUSD", "USDJPY"} else
                    "METALS" if symbol == "XAUUSD" else "CRYPTO"),
            venue="LSMC_TEST_FIXTURE",
            direction="BUY",
            detected_at=now,
            last_evaluated_at=now,
            expires_at=None,
            stage=STAGE_ENTRY_CONFIRMED,
            outcome=OUTCOME_ACTIVE,
            revision=1,
            geometry=CandidateGeometry(
                direction="BUY", entry=last_m5.close, invalidation=stop,
            ),
            market_data_mode=mode,
            data_lineage=f"{manifest['schema']}:{source['classification']}:{symbol}",
        )
        binding = StrategyBinding(
            strategy_id="ST_LARGE_SMC_V1",
            semantic_version="1.1.1",
            engine_id="large_smc_core",
            engine_version=None,
            adapter_id=None,
            adapter_version=None,
            dispatchable=False,
            opportunity_authority=True,
            proposal_authority=False,
            execution_authority="NONE",
            replay_supported=True,
            live_observation_supported=True,
        )

        decision = evaluate_proposal_eligibility(candidate, binding, evaluated_at=now)
        assert decision.status == ELIGIBILITY_BLOCKED, symbol
        assert expected_reason in decision.reason_codes, symbol

        proposal = to_canonical_proposal(candidate, decision)
        assert proposal.proposal_state == PROPOSAL_BLOCKED, symbol
        assert proposal.watcher_state == WATCHER_DATA_BLOCKED, symbol
        assert proposal.data_provenance.source == candidate.data_lineage, symbol
        assert proposal.data_provenance.market_data_mode == mode, symbol
        assert proposal.data_provenance.complete_candle_evidence is False, symbol
        assert proposal.direction == "BUY", symbol  # informational only on a blocked proposal
        assert proposal.entry is None and proposal.stop is None, symbol

    assert synthetic_symbols == {"GBPUSD", "USDJPY", "XAUUSD", "BTCUSDT", "ETHUSDT"}
    assert replay_symbols == {"EURUSD"}
