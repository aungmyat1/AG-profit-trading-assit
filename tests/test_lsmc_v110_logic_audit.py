"""AGP-C17-LSMC Phase A: the committed logic audit is bound to this tree's frozen identities.

The full audit (`scripts/lsmc_v110_logic_audit.py`, four lanes, ~50 s) is not re-run here. This file
follows the pattern of `tests/test_lsmc_c15_symbol_replay.py`: bind the committed evidence to the
bytes in the tree, then reproduce the findings that are cheap and deterministic, so a silent
regression in the engine, the fixtures, the harness or the audit's own conclusions fails a normal
`pytest -q`.

Nothing here grants authority: it asserts that authority stays false.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import lsmc_v110_logic_audit as A  # noqa: E402
from _lsmc_v111_fixtures import (  # noqa: E402
    FIXTURE_DIR,
    check_decision_time,
    decision_time_utc,
    fixture_manifest,
)

from large_smc_watch import contract as C  # noqa: E402
from large_smc_watch import watch as W  # noqa: E402
from v1_tickets import lsmc_logic_gate as G  # noqa: E402
from v1_tickets.logic_gate import FAIL, NOT_APPLICABLE, PASS, WARN  # noqa: E402

REPORT = (ROOT / "artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_0/c15_lsmc_audit_2026-10-13"
          / "lsmc_v110_logic_audit.json")

# Frozen identities this audit ran on. Hardcoded on purpose: editing the frozen 1.1.0 contract or
# engine, or re-pinning the corrected EURUSD fixture, must fail here and force a reviewed re-run.
FROZEN_CONTRACT_SHA256 = "78285f9fabcb20af14de327d010e48684dc12205f4435eff886fcc2373a357b4"
FROZEN_ENGINE_SHA256 = "88dd9f1fb970f7811b437cb3b4c7341e0d1f84320238890eab3381eb0f51b689"
REGISTRY_ENGINE_PIN_SHA256 = "ec0b2f3dc6ed2b02df3f643b38beac1c0e88630413c74e0f55e3d8aa5f5570d4"
CORRECTED_EURUSD_FIXTURE_SHA256 = "2ce91ea1c0eecf2debda0bd6bfb34e37d0f49cd66ccbb00ed199f7f78da6425d"
PRE_CORRECTION_EURUSD_FIXTURE_SHA256 = "b5e1e524e1b912d15032650881edb000906d6d875657332be90fa3997a191c11"


def _instant(text: str) -> dt.datetime:
    return dt.datetime.fromisoformat(text.replace("Z", "+00:00"))


def report() -> dict:
    return json.loads(REPORT.read_text(encoding="utf-8"))


def findings(rep: dict) -> dict:
    return {f["id"]: f for f in rep["findings"]}


def test_committed_report_is_bound_to_the_working_tree():
    """Every hash the report claims is recomputed here from the tree it was committed with."""
    rep, ident = report(), report()["identity"]
    assert ident["strategy"] == f"{C.STRATEGY_ID}@{C.STRATEGY_VERSION}" == "ST_LARGE_SMC_V1@1.1.0"
    assert ident["contract_path"] == "strategies/ST_LARGE_SMC_V1_1_1_0.yaml"
    assert ident["contract_sha256"] == G.file_sha256(ident["contract_path"]) == A.sha256(G.CONTRACT_PATH)
    assert ident["engine_sha256"] == G.engine_sha256()
    assert ident["engine_file_sha256"] == {f: G.file_sha256(f) for f in G.ENGINE_FILES}
    assert ident["dependency_sha256"] == {f: G.file_sha256(f) for f in G.DEPENDENCY_FILES}
    assert ident["gate_file_sha256"] == {f: G.file_sha256(f) for f in ident["gate_file_sha256"]}
    fixtures = ident["fixture_set"]
    assert fixtures["manifest_pins_match_files"] is True
    assert fixtures["every_fixture_evaluated_at_is_the_decision_time"] is True
    assert fixtures["manifest_decision_time_utc"] == decision_time_utc() == "2026-08-03T00:00:00Z"
    assert fixtures["eurusd_fixture_sha256"] == A.sha256(FIXTURE_DIR / "EURUSD.json")
    export = ident["fx_h1_export"]
    assert export["sha256"] == A.sha256(ROOT / export["path"])
    assert export["dataset_manifest_sha256"] == A.sha256(
        ROOT / "data/research/ssc_fresh_dev/SSC_V1_0_1_G2_DEV_001/dataset_manifest.json")
    # Byte-reproducibility claim: the report carries no wall-clock field at any level.
    assert "generated_at_utc" not in rep and "generated_at" not in rep
    assert rep["reproducibility"].startswith("byte-reproducible")
    assert rep["schema"] == "AGP_C15_LSMC_V110_LOGIC_AUDIT_V1"


def test_frozen_strategy_and_data_identities_are_unchanged():
    """Phase A.5: the audit ran on the frozen 1.1.0 contract/engine and the corrected fixture."""
    ident = report()["identity"]
    assert ident["contract_sha256"] == FROZEN_CONTRACT_SHA256
    assert ident["engine_sha256"] == FROZEN_ENGINE_SHA256
    assert G.file_sha256("strategies/ST_LARGE_SMC_V1_1_1_0.yaml") == FROZEN_CONTRACT_SHA256
    assert G.engine_sha256() == FROZEN_ENGINE_SHA256
    assert ident["registry_identity"]["registry_contract_sha256"] == FROZEN_CONTRACT_SHA256
    # D-LSMC-3: the registry engine pin is stale and this PR deliberately left it stale.
    assert ident["registry_identity"]["registry_engine_sha256"] == REGISTRY_ENGINE_PIN_SHA256
    assert ident["registry_identity"]["engine_matches_registry"] is False
    assert A.sha256(FIXTURE_DIR / "EURUSD.json") == CORRECTED_EURUSD_FIXTURE_SHA256
    assert CORRECTED_EURUSD_FIXTURE_SHA256 != PRE_CORRECTION_EURUSD_FIXTURE_SHA256


def test_authority_surfaces_stay_false():
    auth = report()["identity"]["authority_flags"]
    assert auth["all_authority_false"] is True
    assert auth["proposal_generation_authorized"] is False
    assert auth["contract_proposal_generation_authorized"] is False
    assert auth["contract_demo_authorized"] is False
    assert auth["contract_live_authorized"] is False
    assert auth["delivery_mode"] == "ARCHIVE_ONLY" == W.DELIVERY_MODE
    assert auth["economic_status"] == "NOT_EVALUATED"
    assert C.PROPOSAL_GENERATION_AUTHORIZED is False


def test_verdict_is_not_verified_with_exactly_two_blocking_findings():
    rep = report()
    assert rep["verdict"] == "NOT_VERIFIED"
    assert rep["harness_scope_verdict"]["value"] == "LOGIC_VERIFIED"
    blocking = sorted(f["id"] for f in rep["findings"] if f["blocking"])
    assert blocking == ["D-LSMC-1", "D-LSMC-6"]
    assert len(rep["verdict_reasons"]) == 2
    # Both blocking findings are owner decisions, not agent-fixable code defects.
    for fid in blocking:
        assert "owner" in findings(rep)[fid]["resolution"].lower()
    assert set(rep["lane_verdicts"]) == {"A_fixture_harness", "B_eurusd_host_captured_replay",
                                         "C_crypto_recorded_60d_bounded", "D_rule_semantics"}
    assert rep["lane_verdicts"]["A_fixture_harness"] == "LOGIC_VERIFIED"
    assert all(v == PASS for k, v in rep["lane_verdicts"].items() if k != "A_fixture_harness")
    # The only failing property check is the POI-age unit divergence.
    failing = sorted(k for k, v in rep["property_verdicts"].items() if v == FAIL)
    assert failing == ["poi_age_semantics"]


def test_harness_lane_evaluates_the_opportunity_rules_it_once_blanked():
    """D-LSMC-7: a green gate must come with coverage, not NOT_APPLICABLE everywhere."""
    lane = report()["lanes"]["A_fixture_harness"]
    assert lane["verdict"] == "LOGIC_VERIFIED" and lane["cases"] == 18
    assert lane["opportunity_symbols_covered_signal_lane"] == sorted(C.V1_SYMBOLS)
    # The shipped (delivery-gated) state covers none of them off-host: that is the defect.
    assert lane["opportunity_symbols_covered_shipped_state"] == []
    cov = lane["check_coverage"]
    assert cov["never_exercised_checks"] == []
    assert cov["structural_na_markers"] == ["L3.geometry", "L3.stop_geometry", "L6.freshness"]
    counts = cov["check_verdict_counts"]
    for check in ("L2.direction_matches_bias", "L2.entry_by_reference", "L2.sweep_window_measured",
                  "L2.expiry_session_end", "L2.c10_stop", "L2.c11_target", "L3.entry_in_choch_bar",
                  "L3.sweep_extreme_side", "L6.valid_until", "L2.delivery_gate_preserves_detection"):
        assert counts[check].get("PASS", 0) == 10, check
    assert counts["L3.stop_side"] == {"PASS": 2} and counts["L3.stop_beyond_sweep"] == {"PASS": 2}
    assert lane["c10_stop_price_symbols"] == ["EURUSD", "GBPUSD"]


def test_eurusd_lane_b_produced_real_c10_geometry():
    """First FX-side C10 evidence: stops beyond the sweep; one SHORT fails closed on spread."""
    lane = report()["lanes"]["B_eurusd_host_captured_replay"]
    assert lane["verdict"] == PASS, lane["verdict_reasons"]
    assert lane["window"]["scans"] == 575
    assert lane["l4_fail_equals_market_closed"] is True and lane["market_closed_scans"] == 1
    assert lane["check_coverage"]["never_exercised_checks"] == []
    assert lane["point"] == 1e-05 and lane["point_source"] == "HOST_CAPTURED"
    opps = lane["opportunities"]
    assert opps["distinct"] == 3 and opps["with_c10_stop_price"] == 2
    assert opps["by_direction"] == {"LONG": 2, "SHORT": 1}
    pip = C.C10_PIP_SIZE["EURUSD"]
    for item in opps["items"].values():
        if item["stop_c10"] is None:
            # Fail closed with a reason rather than inventing a spread or a stop.
            assert item["stop_reason"] == "MISSING_SPREAD" and item["direction"] == "SHORT"
            continue
        assert item["stop_reason"] is None
        # Compare in pips, not in price: 1.5 * 0.0001 is not exactly representable, and a
        # price-space >= would fail on the last bit of a stop that is exactly at the hard floor.
        if item["direction"] == "LONG":
            assert item["stop_c10"] < item["sweep_extreme"] < item["entry_reference"]
            assert round((item["sweep_extreme"] - item["stop_c10"]) / pip, 9) >= 1.5
        else:
            assert item["stop_c10"] > item["sweep_extreme"] > item["entry_reference"]
            assert round((item["stop_c10"] - item["sweep_extreme"]) / pip, 9) >= 1.5


def test_committed_c16_artifacts_still_rederive_from_their_own_bytes():
    """D-LSMC-9: the C16 headline counts are re-derived here, not trusted."""
    for symbol in ("BTCUSD", "ETHUSD"):
        committed = A.verify_committed_c16(symbol)
        assert committed["all_pass"] is True, committed["checks"]
        assert committed["committed_verdict"] == "NOT_VERIFIED"
        derived = committed["coverage_derived_from_artifact"]
        assert derived["full_d1_scans"] == 8961
        assert derived["opportunities_with_c10_stop"] == 0
        assert derived["l3_stop_geometry_assertions_evaluable"] is False
        assert (derived["opportunity_scans_full_d1"]
                + derived["scans_where_every_opportunity_rule_was_not_applicable"] == 8961)
    lane = report()["lanes"]["C_crypto_recorded_60d_bounded"]
    assert lane["BTCUSD"]["opportunity_scans_signal_lane"] == 0
    assert lane["ETHUSD"]["opportunity_stop_reasons"] == {"C10_PIP_SIZE_NOT_EVIDENCED": 13}
    assert lane["ETHUSD"]["c10_pip_evidenced"] is False
    assert lane["BTCUSD"]["verdict"] == PASS and lane["ETHUSD"]["verdict"] == PASS


def test_poi_age_divergence_reproduces_and_is_conservative():
    """D-LSMC-6: trading days declared, calendar NY-17:00 dates implemented; FX only."""
    poi = A.poi_age_semantics()
    assert poi["verdict"] == FAIL
    eurusd = poi["EURUSD_H1_COMMITTED_EXPORT"]
    assert (eurusd["origins_evaluated"], eurusd["origins_divergent"]) == (723, 600)
    assert eurusd["trading_dates_expired_early_total"] == 1080
    assert eurusd["directions"] == {"ENGINE_EXPIRES_EARLIER": 600}
    # Crypto trades every calendar date on this venue, so both clocks coincide there.
    assert poi["BTCUSD_H1_VT_RECORDED_60D"]["origins_divergent"] == 0
    assert poi["BTCUSD_H1_VT_RECORDED_60D"]["verdict"] == PASS
    synthetic = poi["SYNTHETIC_FX_4WEEKS"]
    assert synthetic["directions"] == {"ENGINE_EXPIRES_EARLIER": synthetic["origins_divergent"]}
    assert poi["dead_code"]["symbol"] == "large_smc_watch.watch._poi_age_days"
    assert poi["dead_code"]["callers_in_repository"] == 0


def test_declared_trading_day_rule_is_what_the_candidate_must_implement():
    """The declared rule, computed independently: 5 distinct NY-17:00 trading dates.

    A POI born on a Monday is valid through the following Monday; one born on a Friday is valid
    through the following Friday. The frozen engine's calendar count expires both earlier
    (D-LSMC-6); this pins the semantics a corrected candidate has to satisfy.
    """
    calendar = A._synthetic_fx_calendar(weeks=4)
    dates = sorted({A.W.trading_date(t) for t in calendar})
    assert len(dates) >= C.POI_MAX_AGE_TRADING_DAYS + 2
    monday = next(t for t in calendar if A.W.trading_date(t) == dates[0] and t.weekday() == 0)
    declared, chain = A._declared_poi_expiry(monday, calendar)
    engine = A._engine_poi_expiry(monday)
    assert chain[:C.POI_MAX_AGE_TRADING_DAYS + 1] == dates[:C.POI_MAX_AGE_TRADING_DAYS + 1]
    assert declared is not None and declared > engine
    # The declared expiry is the start of the trading date AFTER the five valid ones.
    assert declared == A._start_of_trading_date(dates[C.POI_MAX_AGE_TRADING_DAYS + 1])
    assert A.W.trading_date(declared) == dates[C.POI_MAX_AGE_TRADING_DAYS + 1]
    # No weekend date is ever counted as a trading date by the declared rule.
    assert all(d.weekday() < 5 for d in chain[:C.POI_MAX_AGE_TRADING_DAYS + 2])


def test_boundary_check_reaches_the_engine_and_finds_no_transport():
    """D-LSMC-10: no transport/order path; the MT5 broker-API import is recorded, not hidden."""
    boundary = A.no_transport_boundary()
    assert boundary["verdict"] == PASS, boundary["verdict_reasons"]
    assert boundary["static"]["transport_deny_hits"] == []
    assert boundary["static"]["positive_control_reached"] is True
    assert boundary["static"]["positive_control_missing"] == []
    assert boundary["static"]["repo_modules_reachable"] >= len(A.BOUNDARY_POSITIVE_CONTROL)
    assert boundary["runtime"]["transport_deny_loaded_excluding_stdlib_socket"] == []
    assert boundary["runtime"]["modules_loaded_by_import"] > 100   # not a vacuous probe
    assert sorted({h["import"] for h in boundary["static"]["broker_api_imports"]}) == ["MetaTrader5"]
    assert boundary["static"]["broker_api_imports"], "the closure is expected to reach the MT5 API modules"


def test_metadata_fails_closed_and_the_positive_control_still_resolves():
    """D-LSMC-1's fail-closed half: no pip evidence, no stop, no invented point size."""
    metadata = A.fail_closed_metadata()
    assert metadata["verdict"] == PASS
    rows = {r["case"]: r for r in metadata["rows"]}
    for case in ("MISSING_FILE", "MALFORMED_JSON", "HASH_MISMATCH", "WRONG_SCHEMA"):
        assert rows[case]["verdict"] == PASS, case
        assert rows[case]["point"] is None
        assert rows[case]["metadata_source"] == C.METADATA_MISSING
        assert rows[case]["snapshot_reasons"] == ["SYMBOL_METADATA_MISSING"]
        assert rows[case]["snapshot_state"] == "DATA_ERROR"
    control = rows["COMMITTED_CAPTURE"]
    assert control["point"] == 1e-05 and control["metadata_source"] == "HOST_CAPTURED"
    # EURUSD is quoted to five decimals: the evidenced C10 pip is exactly ten broker points.
    assert control["c10_pip_is_10_points"] is True
    assert sorted(metadata["c10_pip_evidenced_symbols"]) == ["EURUSD", "GBPUSD"]
    assert sorted(metadata["c10_not_evaluable_symbols"]) == ["BTCUSD", "ETHUSD", "USDJPY", "XAUUSD"]


def test_archive_only_stays_exactly_once():
    archive = A.archive_only_exactly_once()
    assert archive["verdict"] == PASS
    steps = {r["step"]: r for r in archive["rows"]}
    assert steps["duplicate_poll_on_identical_snapshot"]["events"] == 0
    guard = steps["archive_path_matches_the_exactly_once_guard"]
    assert guard["guard_paths"] == guard["archived_files"] and guard["events"] >= 1
    crash = steps["restart_after_crash_between_archive_and_state_save"]
    assert crash["transition_ids_identical"] is True and crash["archive_not_rewritten"] is True
    assert steps["market_closed_emits_nothing_and_preserves_state"]["events"] == 0
    assert archive["alert_level_mapping_matches_contract"] is True
    assert archive["rejected_is_not_a_contract_alert_state"] is True   # D-LSMC-7, second half


def test_harness_defects_stay_pinned():
    regressions = A.harness_regression()
    assert regressions["verdict"] == PASS
    assert regressions["delivery_gate_does_not_blank_the_opportunity_rules"]["verdict"] == PASS
    assert regressions["short_circuit_is_not_reported_as_a_point_source_failure"]["verdict"] == PASS
    guard = regressions["fixture_decision_time_guard"]
    assert guard["verdict"] == PASS and guard["divergent_time_raises"] is True
    assert guard["conformant_time_accepted"] is True


def test_every_fixture_is_pinned_and_evaluated_at_the_manifest_decision_time():
    """D-LSMC-8's guard, applied to all six fixtures rather than only EURUSD."""
    want = decision_time_utc()
    entries = fixture_manifest()["fixtures"]
    vt_name = A.HARNESS.VT_NAME      # BTCUSDT/ETHUSDT series run under the VT symbols BTCUSD/ETHUSD
    assert sorted(vt_name.get(e["symbol"], e["symbol"]) for e in entries) == sorted(C.V1_SYMBOLS)
    for entry in entries:
        symbol, path = entry["symbol"], ROOT / entry["fixture_file"]
        canonical = vt_name.get(symbol, symbol)
        # The manifest pin is recomputed from the file: no stale hash may ride along.
        assert A.sha256(path) == entry["fixture_sha256"], symbol
        record = json.loads(path.read_text(encoding="utf-8"))
        assert record["symbol"] == symbol
        assert record["evaluated_at_utc"] == want, symbol
        check_decision_time(canonical, record["evaluated_at_utc"])   # must not raise
        assert {tf: len(record[tf]) for tf in ("D1", "H1", "M5")} == entry["bar_counts"], symbol
        # The decision time is inside the fixture's own recorded data window, not after it:
        # the last M5 bar must close at or before the decision instant (for EURUSD it closes
        # exactly on it, which is what makes the oracle's L6 closed-input check boundary-exact).
        last_m5_open = max(bar["time_utc"] for bar in record["M5"])
        last_close = _instant(last_m5_open) + dt.timedelta(minutes=C.TIMEFRAME_MINUTES["M5"])
        assert last_m5_open < want, symbol
        assert last_close <= _instant(want), symbol


def test_gate_integrity_proves_no_gate_was_weakened_and_no_emission_suppressed():
    """Phase B.7: the claim is computed from the run, not asserted in prose."""
    gi = report()["property_checks"]["gate_integrity"]
    assert gi["verdict"] == PASS, gi["verdict_reasons"]
    assert all(gi["checks"].values()), sorted(k for k, v in gi["checks"].items() if not v)
    # The blocking gate set is read from the gate module: L5 stays advisory exactly as OD1011-L5 signed.
    assert G.BLOCKING == ("L1", "L2", "L3", "L4")
    l5 = gi["l5_check_status_counts"]
    assert set(l5) == {"L5.commission_R", "L5.cost_vs_warn_level", "L5.spread_R"}
    assert sum(v["WARN"] for v in l5.values()) > 0            # still emitted
    assert not any(v.get(PASS) or v.get(FAIL) for v in l5.values())   # never invented, never blocking
    # Emissions survive in every lane, and every emitted transition is archived exactly once.
    assert all(v > 0 for v in gi["shipped_state_counts_per_lane"].values())
    assert gi["opportunity_rule_checks_exercised"] == len(gi["opportunity_rule_checks"]) == 6
    assert min(gi["opportunity_rule_checks_with_a_pass"].values()) == 10
    assert gi["coverage_now"]["checks_evaluated"] > gi["pre_fix_baseline"]["checks_evaluated"]
    assert gi["coverage_now"]["never_exercised_checks"] == []


def test_phase_b_classification_covers_every_finding_with_a_mission_class():
    phb, findings = report()["phase_b"], report()["findings"]
    assert phb["verdict"] == PASS, phb["verdict_reasons"]
    assert all(phb["checks"].values())
    assert set(phb["rows"]) == {f["id"] for f in findings}
    assert set(phb["mission_classes"]) == {"IMPLEMENTATION", "STRATEGY_CONTRACT", "DATA", "METADATA",
                                           "VERIFICATION_HARNESS"}
    assert sum(phb["class_counts"].values()) == len(findings)
    rows = phb["rows"]
    # The two blocking defects are owner/host routes, never agent fixes.
    assert rows["D-LSMC-6"]["class"] == "IMPLEMENTATION"
    assert rows["D-LSMC-6"]["route"] == "CANDIDATE_1_1_2_RULE_DIFF"
    assert rows["D-LSMC-6"]["owner_decision_required"] is True
    assert rows["D-LSMC-1"]["class"] == "METADATA"
    assert rows["D-LSMC-1"]["route"] == "OWNER_DECISION_REQUIRED_AND_HOST_CAPTURE"
    # The two harness defects were fixed in this PR, with the engine untouched.
    for fid in ("D-LSMC-7", "D-LSMC-8"):
        assert rows[fid]["class"] == "VERIFICATION_HARNESS"
        assert rows[fid]["route"] == "FIX_APPLIED_IN_THIS_PR"
        assert rows[fid]["owner_decision_required"] is False
    # Every row names the regression test that pins it.
    assert all("tests/test_lsmc_v110_logic_audit.py::" in r["regression_test"] for r in rows.values())


def test_candidate_1_1_2_carries_exactly_the_rule_change_diff_it_declares():
    """Phase B.5: a genuine strategy defect goes to a new candidate, never into frozen 1.1.0."""
    cand = report()["property_checks"]["candidate_rule_change_diff"]
    assert cand["verdict"] == PASS, cand["verdict_reasons"]
    assert all(cand["checks"].values()), sorted(k for k, v in cand["checks"].items() if not v)
    assert cand["candidate_contract"] == "strategies/ST_LARGE_SMC_V1_1_1_2.yaml"
    assert cand["candidate_contract_sha256"] == A.sha256(ROOT / cand["candidate_contract"])
    # The candidate chain is bound byte-for-byte: 1.1.2 -> committed 1.1.1 -> frozen 1.1.0.
    assert cand["based_on_candidate_sha256"] == A.sha256(A.CANDIDATE_1_1_1_PATH)
    assert A.sha256(G.CONTRACT_PATH) == FROZEN_CONTRACT_SHA256
    assert cand["undeclared_rule_drift"] == [] and cand["stale_declared_paths"] == []
    assert len(cand["computed_structural_diff_1_1_1_to_1_1_2"]) == len(cand["declared_diff_paths"]) >= 10
    spec = A.yaml.safe_load(A.CANDIDATE_1_1_2_PATH.read_text(encoding="utf-8"))
    assert spec["version"] == "1.1.2" and spec["rules"]["poi"]["max_age_trading_days"] == 5
    assert spec["rules"]["poi"]["max_age_unit"] == "DISTINCT_NY1700_TRADING_DATES"
    assert spec["registered"] is False and spec["active"] is False
    assert spec["implementation"] == "SPEC_ONLY_NOT_WIRED"
    assert spec["economic_status"] == "NOT_EVALUATED"
    # The declared unit is what the audit computes independently, and it excludes weekend dates.
    assert A._declared_poi_expiry_is_trading_date_based() is True


def test_scope_matrix_records_a_gate_and_scope_verdict_per_symbol():
    """Phase C: no scope is LOGIC_VERIFIED, and 1.1.0 evidence is not reused for the candidate."""
    matrix, scopes = report()["scope_matrix"], report()["scope_matrix"]["scopes"]
    assert set(scopes) == set(C.V1_SYMBOLS) | {"_candidate_1_1_2"}
    assert matrix["logic_verified_scopes"] == []
    assert sorted(matrix["not_verified_scopes"]) == sorted(C.V1_SYMBOLS)
    for symbol in C.V1_SYMBOLS:
        sc = scopes[symbol]
        assert sc["scope_verdict"] == "NOT_VERIFIED"
        assert set(sc["gates"]) == {"L1", "L2", "L3", "L4", "L5", "L6"}
        assert sc["gates"]["L5"] == WARN and sc["required_gates"] == ["L1", "L2", "L3", "L4", "L6"]
        assert sc["emissions"]["delivery_mode"] == "ARCHIVE_ONLY"
        assert sc["emissions"]["transport_or_order_path_reachable"] is False
        assert sc["scope_verdict_reasons"], symbol
        assert sc["poi_age_unit_divergent"] is (symbol in A.FX_SYMBOLS)
        # The matrix is stricter than the shipped gate (which blocks on L1-L4 only) and says so.
        assert "L6" in sc["required_gate_note"] and G.BLOCKING == ("L1", "L2", "L3", "L4")
        assert sc["c10_pip_evidenced"] is (symbol in C.C10_PIP_SIZE)
        # A blocking finding applies to every scope: FX -> the POI-age unit, the rest -> no pip evidence.
        if symbol in A.FX_SYMBOLS:
            assert "D-LSMC-6" in sc["blocking_findings_applying_to_this_scope"]
        else:
            assert "D-LSMC-1" in sc["blocking_findings_applying_to_this_scope"]
    # EURUSD fails closed on the gate too: the single MARKET_CLOSED L4 FAIL is disclosed, not excused.
    eurusd = scopes["EURUSD"]
    assert eurusd["gates"]["L4"] == FAIL and eurusd["required_gates_pass"] is False
    assert eurusd["l4_note"] and "MARKET_CLOSED" in eurusd["l4_note"]
    assert any(e["lane"] == "B_eurusd_host_captured_replay" for e in eurusd["evidence"])
    for symbol in C.CRYPTO_SYMBOLS:
        lanes = [e["lane"] for e in scopes[symbol]["evidence"]]
        assert "C_crypto_recorded_60d_bounded" in lanes and "C_committed_c16_rederivation" in lanes
    cand = scopes["_candidate_1_1_2"]
    assert cand["scope_verdict"] == "NOT_VERIFIED" and cand["implementation"] == "SPEC_ONLY_NOT_WIRED"
    assert set(cand["gates"].values()) == {NOT_APPLICABLE}
    assert cand["authority"]["registered"] is False and cand["authority"]["live_authorized"] is False
    assert any("must not be reused" in r for r in cand["scope_verdict_reasons"])


def test_committed_lane_a_artifact_matches_a_fresh_in_process_run():
    """The committed 18-case artifact and the audit's lane A describe the same run."""
    art = json.loads((ROOT / "artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_0/c15_lsmc_audit_2026-10-13"
                      / "lsmc_v110_logic_verification_18case.json").read_text(encoding="utf-8"))
    lane = report()["lanes"]["A_fixture_harness"]
    assert art["verdict"] == lane["verdict"] == G.LOGIC_VERIFIED
    assert len(art["cases"]) == lane["cases"] == 18
    assert art["contract_sha256"] == FROZEN_CONTRACT_SHA256 and art["engine_sha256"] == FROZEN_ENGINE_SHA256
    assert art["check_coverage"]["checks_evaluated"] == lane["check_coverage"]["checks_evaluated"]
    assert art["check_coverage"]["never_exercised_checks"] == lane["check_coverage"]["never_exercised_checks"] == []
    assert sorted(art["opportunity_symbols_covered"]) == lane["opportunity_symbols_covered_signal_lane"]
    # The only field a fresh run of the shipped producer changes is its own wall-clock stamp.
    assert "generated_at_utc" in art


def test_report_doc_cites_the_hashes_of_the_files_it_cites():
    """Phase A.7: every full sha256 in the report document is re-checked against the tree."""
    doc = (ROOT / "docs/status/AGP_C15_LSMC_V110_LOGIC_AUDIT_2026-10-13.md").read_text(encoding="utf-8")
    section = doc.split("### Full SHA-256 reconciliation (Phase A.7)", 1)[1].split("\n## 1. ", 1)[0]
    checked = 0
    for line in section.splitlines():
        if not line.startswith("| ") or line.startswith("|---") or "SHA-256" in line:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        path, cited = cells[1].strip("`"), cells[2].strip("`")
        if "git rev-parse" in path:                # the report's code_sha is a git SHA-1, not a sha256
            assert re.fullmatch(r"[0-9a-f]{40}", cited), f"{path}: cited git sha is not 40-hex"
            assert report()["identity"]["code_sha"] == cited
        else:
            assert re.fullmatch(r"[0-9a-f]{64}", cited), f"{path}: cited sha is not a full 64-hex digest"
            target = ROOT / path
            if target.is_file():
                assert A.sha256(target) == cited, f"stale sha256 cited for {path}"
            else:                                  # the engine composite is a directory
                assert target.is_dir() and path == "src/large_smc_watch/"
                assert G.engine_sha256() == cited, f"stale engine sha256 cited for {path}"
        checked += 1
    assert checked >= 20, f"only {checked} hash rows were checked: the table shrank or was reformatted"


def test_positive_risk_geometry_is_measured_and_not_assumed():
    """Phase C: entry/stop/target as distances, with RR recorded rather than gated."""
    prg = report()["lanes"]["B_eurusd_host_captured_replay"]["positive_risk_geometry"]
    assert prg["verdict"] == PASS, prg["verdict_reasons"]
    assert all(prg["checks"].values()), sorted(k for k, v in prg["checks"].items() if not v)
    assert (prg["opportunities"], prg["evaluable"], prg["not_evaluable"]) == (3, 1, 2)
    pip = C.C10_PIP_SIZE["EURUSD"]
    evaluable = [r for r in prg["rows"] if r["evaluable"]]
    assert len(evaluable) == 1
    row = evaluable[0]
    assert row["direction"] == "LONG"
    assert row["stop_c10"] < row["entry_reference"] < row["target_c11"]
    assert row["risk_pips"] == round(abs(row["entry_reference"] - row["stop_c10"]) / pip, 6) > 0
    assert row["reward_pips"] == round(abs(row["target_c11"] - row["entry_reference"]) / pip, 6) > 0
    assert abs(row["reward_risk"] - row["reward_pips"] / row["risk_pips"]) < 1e-6
    assert row["stop_at_least_the_c10_floor_beyond_the_sweep"] is True
    assert prg["min_buffer_pips"] == 1.5
    # 1.1.0 declares no RR minimum, so the candidate's proposed 2.0 is measured, never gated.
    assert row["meets_candidate_minimum_rr_2_0"] is False
    assert prg["opportunities_meeting_candidate_minimum_rr_2_0"] == 0
    assert "PENDING_OWNER_CONFIRM" in prg["candidate_rr_status"]
    for r in prg["rows"]:
        if not r["evaluable"]:
            # Not evaluable means the engine produced no level, and its own reason is carried.
            assert r["reason"] and (r["stop_c10"] is None or r["target_c11"] is None)
            assert "reward_risk" not in r
