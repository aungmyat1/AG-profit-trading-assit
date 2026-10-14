"""AGP-C24: the independent C11 target-stability checker flags any drift and never passes missing shards."""
import csv
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("stability", ROOT / "scripts/lsmc_v113_target_stability.py")
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)
COLS = ["symbol", "m5_row", "closed_at_utc", "opp_id", "target", "c11_source", "creation_target_sha256"]


def _write(root, symbol, shard, rows):
    path = root / symbol / f"shard_{shard:02d}" / "scans.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)


def _row(symbol, i, opp, target, sha="a"):
    return {"symbol": symbol, "m5_row": i, "closed_at_utc": f"2026-08-01T00:{i:02d}:00+00:00", "opp_id": opp,
            "target": target, "c11_source": "M5", "creation_target_sha256": sha}


def _all(tmp, drift_at=None):
    for sym in S.SYMBOLS:
        for shard in range(S.SHARDS):
            rows = [_row(sym, 1, "o1", "100"), _row(sym, 2, "o1", "100"), _row(sym, 3, "", "")]
            if drift_at == (sym, shard):
                rows.append(_row(sym, 4, "o1", "101", "b"))
            _write(tmp, sym, shard, rows)


def test_stable_targets_pass(tmp_path):
    _all(tmp_path)
    assert S.check(tmp_path)["verdict"] == "PASS"


def test_drift_across_shards_fails_with_case(tmp_path):
    _all(tmp_path, drift_at=("ETHUSD", 5))
    r = S.check(tmp_path)
    assert r["verdict"] == "FAIL" and r["symbols"]["ETHUSD"]["drift_cases"][0]["opp_id"] == "o1"


def test_missing_shard_is_not_pass(tmp_path):
    _all(tmp_path)
    (tmp_path / "BTCUSD" / "shard_03" / "scans.csv").unlink()
    assert S.check(tmp_path)["symbols"]["BTCUSD"]["verdict"] == "INCOMPLETE"
