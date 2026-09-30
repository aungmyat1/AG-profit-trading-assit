"""Parquet + DuckDB bar catalog, partitioned venue/symbol/timeframe/year/month.

Layout: <root>/venue=<V>/symbol=<S>/timeframe=<TF>/year=<YYYY>/month=<MM>/bars.parquet
plus <root>/manifest.json (one entry per partition). Timestamps are UTC bar-open times;
naive timestamps are rejected. Data is never repaired: duplicates and gaps are counted
in the manifest, not removed or filled.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

import duckdb
import pandas as pd

SCHEMA_VERSION = "harness.catalog.v1"
UTC_CONVENTION = "UTC; ts = bar OPEN time"
COLUMNS = ["ts", "open", "high", "low", "close", "volume"]
TF_SECONDS = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "H4": 14400, "D1": 86400}
MANIFEST_KEYS = ("schema_version", "venue", "symbol", "timeframe", "year", "month", "path", "rows",
                 "first_ts", "last_ts", "duplicates", "missing_bars", "calendar", "utc_convention",
                 "sha256", "importer_version")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _utc(ts: pd.Series) -> pd.Series:
    ts = pd.to_datetime(ts)
    if ts.dt.tz is None:
        raise ValueError("naive timestamps rejected: catalog requires tz-aware UTC bar-open times")
    return ts.dt.tz_convert("UTC")


def _market_open(t: pd.Timestamp, calendar: str) -> bool:
    """fx_24x5 excludes Fri>=21:00 .. Sun<22:00 UTC (covers both DST offsets, so a closed
    hour is never flagged missing; a DST-edge open hour may go unflagged)."""
    if calendar == "24x7":
        return True
    if calendar != "fx_24x5":
        raise ValueError(f"unknown calendar {calendar!r}")
    wd, h = t.weekday(), t.hour
    return not (wd == 5 or (wd == 4 and h >= 21) or (wd == 6 and h < 22))


def count_missing_bars(ts: pd.Series, timeframe: str, calendar: str) -> int:
    if len(ts) == 0:
        return 0
    uniq = pd.DatetimeIndex(ts.drop_duplicates().sort_values())
    expected = pd.date_range(uniq[0], uniq[-1], freq=pd.Timedelta(seconds=TF_SECONDS[timeframe]))
    expected = [t for t in expected if _market_open(t, calendar)]
    return int(len(pd.DatetimeIndex(expected).difference(uniq)))


def partition_path(root: str, venue: str, symbol: str, timeframe: str, year: int, month: int) -> str:
    return os.path.join(root, f"venue={venue}", f"symbol={symbol}", f"timeframe={timeframe}",
                        f"year={year:04d}", f"month={month:02d}", "bars.parquet")


def build_manifest_entry(df: pd.DataFrame, path: str, root: str, venue: str, symbol: str, timeframe: str,
                         year: int, month: int, importer_version: str, calendar: str) -> dict:
    ts = df["ts"]
    return {"schema_version": SCHEMA_VERSION, "venue": venue, "symbol": symbol, "timeframe": timeframe,
            "year": year, "month": month, "path": os.path.relpath(path, root).replace(os.sep, "/"),
            "rows": int(len(df)),
            "first_ts": ts.min().strftime("%Y-%m-%dT%H:%M:%SZ") if len(df) else None,
            "last_ts": ts.max().strftime("%Y-%m-%dT%H:%M:%SZ") if len(df) else None,
            "duplicates": int(ts.duplicated().sum()),
            "missing_bars": count_missing_bars(ts, timeframe, calendar), "calendar": calendar,
            "utc_convention": UTC_CONVENTION, "sha256": sha256_file(path),
            "importer_version": importer_version}


def validate_manifest_entry(entry: dict) -> None:
    missing = [k for k in MANIFEST_KEYS if k not in entry]
    if missing:
        raise ValueError(f"manifest entry missing keys: {missing}")
    if entry["schema_version"] != SCHEMA_VERSION or entry["utc_convention"] != UTC_CONVENTION:
        raise ValueError("manifest schema_version/utc_convention mismatch")


def load_manifest(root: str) -> dict:
    p = os.path.join(root, "manifest.json")
    if not os.path.isfile(p):
        return {"schema_version": SCHEMA_VERSION, "partitions": []}
    with open(p, encoding="utf-8") as fh:
        m = json.load(fh)
    for e in m["partitions"]:
        validate_manifest_entry(e)
    return m


def write_bars(df: pd.DataFrame, root: str, venue: str, symbol: str, timeframe: str,
               importer_version: str, calendar: str = "fx_24x5") -> list[dict]:
    """Write bars into monthly partitions (overwriting those partitions) and upsert the manifest."""
    if timeframe not in TF_SECONDS:
        raise ValueError(f"unknown timeframe {timeframe!r}")
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"missing columns: {missing}")
    df = df[COLUMNS].copy()
    df["ts"] = _utc(df["ts"]).astype("datetime64[us, UTC]")
    df = df.sort_values("ts", kind="stable").reset_index(drop=True)
    manifest = load_manifest(root)
    entries = []
    for (y, m), part in df.groupby([df["ts"].dt.year, df["ts"].dt.month], sort=True):
        path = partition_path(root, venue, symbol, timeframe, int(y), int(m))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        part.reset_index(drop=True).to_parquet(path, engine="pyarrow", index=False)
        entries.append(build_manifest_entry(part, path, root, venue, symbol, timeframe, int(y), int(m),
                                            importer_version, calendar))
    keys = {(e["venue"], e["symbol"], e["timeframe"], e["year"], e["month"]) for e in entries}
    kept = [e for e in manifest["partitions"]
            if (e["venue"], e["symbol"], e["timeframe"], e["year"], e["month"]) not in keys]
    manifest["partitions"] = sorted(kept + entries, key=lambda e: (e["venue"], e["symbol"], e["timeframe"],
                                                                   e["year"], e["month"]))
    manifest["updated_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(os.path.join(root, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
    return entries


def verify_catalog(root: str) -> list[str]:
    """Return problems (missing file / sha256 mismatch); empty list means the catalog matches."""
    problems = []
    for e in load_manifest(root)["partitions"]:
        p = os.path.join(root, e["path"])
        if not os.path.isfile(p):
            problems.append(f"MISSING:{e['path']}")
        elif sha256_file(p) != e["sha256"]:
            problems.append(f"SHA256_MISMATCH:{e['path']}")
    return problems


def read_bars(root: str, venue: str, symbol: str, timeframe: str, start=None, end=None,
              verify: bool = True) -> pd.DataFrame:
    """Read [start, end) bars via DuckDB. With verify=True, refuses a partition whose hash drifted."""
    entries = [e for e in load_manifest(root)["partitions"]
               if (e["venue"], e["symbol"], e["timeframe"]) == (venue, symbol, timeframe)]
    if verify:
        for e in entries:
            if sha256_file(os.path.join(root, e["path"])) != e["sha256"]:
                raise ValueError(f"SHA256_MISMATCH:{e['path']}")
    paths = [os.path.join(root, e["path"]) for e in entries]
    if not paths:
        return pd.DataFrame(columns=COLUMNS)
    where, params = [], [paths]
    if start is not None:
        where.append("ts >= ?")
        params.append(pd.Timestamp(start).tz_convert("UTC").to_pydatetime())
    if end is not None:
        where.append("ts < ?")
        params.append(pd.Timestamp(end).tz_convert("UTC").to_pydatetime())
    sql = ("SELECT ts, open, high, low, close, volume FROM read_parquet(?)"
           + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY ts")
    con = duckdb.connect()
    try:
        con.execute("SET TimeZone='UTC'")
        out = con.execute(sql, params).df()
    finally:
        con.close()
    out["ts"] = pd.to_datetime(out["ts"], utc=True)
    return out
