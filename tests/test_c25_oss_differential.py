"""AGP-C25: committed OSS differential report invariants + pure divergence classifier (no oracle package needed)."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "artifacts/oss_differential/c25_report.json"


def _script():
    spec = importlib.util.spec_from_file_location("c25_oss_differential", ROOT / "scripts/c25_oss_differential.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def report():
    return json.loads(REPORT.read_text(encoding="utf-8"))


def test_l3_fuzz_owner_definition(report):
    """Owner L3 definition: truncation and future perturbation never change a signal (no look-ahead); the ASW
    signal-bar perturbation FAILs are recorded as such, and every one keeps direction and signal time (only levels
    the contract derives from the perturbed bar move)."""
    fuzz = report["summary"]["l3_fuzz"]
    for fam in ("ASW", "CCFD"):
        assert fuzz[fam]["truncation_not_identical"] == 0 and fuzz[fam]["future_perturbation_not_identical"] == 0
    assert fuzz["CCFD"]["fail"] == 0
    fails = [f for f in report["asw"]["fuzz"] if f["verdict"] == "FAIL"]
    assert len(fails) == fuzz["ASW"]["fail"] == fuzz["ASW"]["signal_bar_perturbation"].get("CHANGED", 0)
    assert all(f["signal_bar_perturbation"] == "CHANGED" and f["signal_bar_changed_fields"]
               and not {"direction", "signal_timestamp"} & set(f["signal_bar_changed_fields"]) for f in fails)


def test_asw_excluded_tickets_are_unique_geometry_blocked_signals(report):
    asw = report["summary"]["asw_emitted_signals"]
    assert asw["signals"] == asw["unique_signals"] == len(report["asw"]["rows"]) + asw["geometry_invalid"]
    assert sum(asw["geometry_invalid_by_guard_reason"].values()) == asw["geometry_invalid"]
    assert set(asw["geometry_invalid_oracle_supplementary"]) <= {"AGREE", "SPEC_DIFFERENCE"}


def test_every_divergence_is_classified_and_none_is_a_defect(report):
    classes = [r["comparison"]["class"] for fam in ("asw", "ccfd") for r in report[fam]["rows"]]
    assert classes and set(classes) <= {"AGREE", "SPEC_DIFFERENCE"}


def test_data_insufficient_scopes_recorded(report):
    assert report["summary"]["data_insufficient_60d"] == _script().DATA_INSUFFICIENT_60D
    assert {d["scope"] for d in report["summary"]["data_insufficient_60d"]} == {
        "USDJPY x ASIAN_LONDON/LONDON_NEWYORK", "XAUUSD x ASIAN_LONDON/LONDON_NEWYORK", "BTCUSD LONG"}


def test_compare_classifier():
    cmp = _script().compare
    assert cmp({"result": "TP1", "gross_R": 2.0}, {"result": "TP1", "gross_R": 2.0})["class"] == "AGREE"
    assert cmp({"result": "SL", "gross_R": -1.0}, {"result": "TP1", "gross_R": 2.0})["class"] == \
        "UNCLASSIFIED_DIVERGENCE"
    assert cmp({"result": "AMBIGUOUS"}, {"result": "SL"})["class"] == "SPEC_DIFFERENCE"
    assert cmp({"result": "DATA_INSUFFICIENT", "reason": "BARS_END_BEFORE_HORIZON"},
               {"result": "EXPIRY"})["class"] == "SPEC_DIFFERENCE"
    assert cmp({"result": "TP1"}, {"result": "ORACLE_REJECT"})["class"] == "ORACLE_DEFECT"
    gap = cmp({"result": "TP1", "bar": "2026-08-26T12:45:00+00:00"},
              {"result": "EXPIRY", "exit_time": "2026-08-26T12:45:00+00:00", "exit_price": 1.2},
              direction="LONG", tp=1.1)
    assert gap["class"] == "SPEC_DIFFERENCE"



def test_oracle_packages_are_research_only():
    """backtesting.py (AGPL) and pandas-ta appear only in research_external/requirements-oracle.txt: never in a
    runtime requirement and never imported by src/."""
    import re

    import tomllib
    pins = (ROOT / "research_external/requirements-oracle.txt").read_text(encoding="utf-8")
    assert "backtesting==" in pins and "pandas-ta==" in pins
    req = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    deps = list(project.get("dependencies") or []) + [
        d for group in (project.get("optional-dependencies") or {}).values() for d in group]
    names = {re.split(r"[=<>!~;\[ ]", d, maxsplit=1)[0].strip().lower().replace("_", "-") for d in deps}
    for pkg in ("backtesting", "pandas-ta"):
        assert pkg not in names
        assert not re.search(rf"(?m)^\s*{re.escape(pkg)}\b", req.replace("_", "-"))
    pattern = re.compile(r"(?m)^\s*(?:from|import)\s+(?:backtesting|pandas_ta)\b")
    offenders = [str(p.relative_to(ROOT)) for p in (ROOT / "src").rglob("*.py")
                 if pattern.search(p.read_text(encoding="utf-8", errors="ignore"))]
    assert offenders == []
