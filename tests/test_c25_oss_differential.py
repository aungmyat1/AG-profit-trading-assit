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


def test_l3_fuzz_has_no_fail(report):
    fuzz = report["summary"]["l3_fuzz"]
    assert fuzz["ASW"]["fail"] == 0 and fuzz["CCFD"]["fail"] == 0
    assert fuzz["ASW"]["cases"] == len(report["asw"]["fuzz"]) > 0
    assert all(f["verdict"] == "PASS" for f in report["asw"]["fuzz"])


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
