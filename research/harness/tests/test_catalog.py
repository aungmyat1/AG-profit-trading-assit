import json
import os

import pandas as pd
import pytest

from research.harness import catalog
from research.harness.tests.fixtures import bars


def test_roundtrip_partitions_and_manifest(tmp_path):
    df = pd.concat([bars("2024-01-31T23:00:00Z", n=8, tf="15min")])  # spans Jan -> Feb
    entries = catalog.write_bars(df, str(tmp_path), "DUKASCOPY", "EURUSD", "M15", "imp-1.0", calendar="24x7")
    assert [(e["year"], e["month"]) for e in entries] == [(2024, 1), (2024, 2)]
    assert sum(e["rows"] for e in entries) == 8
    for e in entries:
        catalog.validate_manifest_entry(e)
        assert e["importer_version"] == "imp-1.0" and e["duplicates"] == 0 and e["missing_bars"] == 0
        assert os.path.isfile(tmp_path / e["path"])
        assert e["path"].startswith("venue=DUKASCOPY/symbol=EURUSD/timeframe=M15/year=2024/month=0")
    m = json.load(open(tmp_path / "manifest.json"))
    assert m["partitions"][0]["first_ts"] == "2024-01-31T23:00:00Z"
    got = catalog.read_bars(str(tmp_path), "DUKASCOPY", "EURUSD", "M15")
    assert len(got) == 8 and str(got["ts"].dt.tz) == "UTC"
    assert got["ts"].iloc[0] == pd.Timestamp("2024-01-31T23:00:00Z")
    part = catalog.read_bars(str(tmp_path), "DUKASCOPY", "EURUSD", "M15",
                             start="2024-02-01T00:00:00Z", end="2024-02-01T00:30:00Z")
    assert len(part) == 2


def test_duplicates_and_missing_counted_not_repaired(tmp_path):
    df = bars("2024-01-02T00:00:00Z", n=6, tf="1h")
    df = pd.concat([df.drop(index=[2]), df.iloc[[4]]])  # one gap, one duplicate
    (e,) = catalog.write_bars(df, str(tmp_path), "V", "EURUSD", "H1", "imp", calendar="24x7")
    assert e["duplicates"] == 1 and e["missing_bars"] == 1 and e["rows"] == 6
    assert len(catalog.read_bars(str(tmp_path), "V", "EURUSD", "H1")) == 6


def test_fx_weekend_not_counted_missing():
    ts = pd.Series(list(pd.date_range("2024-01-05T19:00:00Z", "2024-01-05T20:00:00Z", freq="1h"))
                   + list(pd.date_range("2024-01-07T22:00:00Z", "2024-01-07T23:00:00Z", freq="1h")))
    assert catalog.count_missing_bars(ts, "H1", "fx_24x5") == 0
    assert catalog.count_missing_bars(ts, "H1", "24x7") > 0


def test_naive_timestamps_rejected(tmp_path):
    df = bars()
    df["ts"] = df["ts"].dt.tz_localize(None)
    with pytest.raises(ValueError, match="naive"):
        catalog.write_bars(df, str(tmp_path), "V", "EURUSD", "M15", "imp")


def test_hash_drift_detected(tmp_path):
    (e,) = catalog.write_bars(bars(), str(tmp_path), "V", "EURUSD", "M15", "imp")
    assert catalog.verify_catalog(str(tmp_path)) == []
    with open(tmp_path / e["path"], "ab") as fh:
        fh.write(b"x")
    assert catalog.verify_catalog(str(tmp_path)) == [f"SHA256_MISMATCH:{e['path']}"]
    with pytest.raises(ValueError, match="SHA256_MISMATCH"):
        catalog.read_bars(str(tmp_path), "V", "EURUSD", "M15")


def test_rewrite_upserts_manifest(tmp_path):
    catalog.write_bars(bars(), str(tmp_path), "V", "EURUSD", "M15", "imp-1")
    catalog.write_bars(bars(n=4), str(tmp_path), "V", "EURUSD", "M15", "imp-2")
    (e,) = catalog.load_manifest(str(tmp_path))["partitions"]
    assert e["rows"] == 4 and e["importer_version"] == "imp-2"
