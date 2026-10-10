"""AGP-DATA-R2b recorded CCFD cases: build the manifest, or materialize it for the #126 runner.

build        tests/fixtures/ccfd_v100/recorded/manifest.json + <SYM>_provenance.json from the
             committed shared per-TF CSVs (M15 is the PR #128 file, referenced by sha256).
             --dataset recorded_60d builds the same manifest/provenance for the PR #143 60-day
             capture (tests/fixtures/ccfd_v100/recorded_60d, own M15 file); partial days are
             listed in provenance and the manifest, never filled.
             One case per M15 bar close inside the crypto window gate (config/v1_tickets
             crypto_ticket_v2/v3 WEEKDAY/WEEKEND, same rule as v1_tickets.crypto_cfd._window).
materialize  verify every listed sha256, then write per-case CSVs holding only bars closed at
             the case `now` (M15 timestamps converted to aware ISO), per-case provenance JSON
             and a manifest the scripts/ccfd_v100_logic_verification.py runner reads unchanged.
             Any hash mismatch aborts before anything is written.

No broker access. expected_result/expected_direction stay null: they are capture-review
assertions and none has been made.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parents[1]
RECORDED = ROOT / "tests/fixtures/ccfd_v100/recorded"
RECORDED_60D = ROOT / "tests/fixtures/ccfd_v100/recorded_60d"
UTC = timezone.utc
SYMBOLS = ("BTCUSD", "ETHUSD")
STEP = {"d1": timedelta(days=1), "h1": timedelta(hours=1), "m15": timedelta(minutes=15),
        "m5": timedelta(minutes=5)}
COMMISSION_GAP = ("commission_R is null for every case: VT crypto CFD commission was not "
                  "captured (no allowed read-only call exposes it). Explicit gap, never 0.")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def windows() -> list[dict]:
    v2 = yaml.safe_load((ROOT / "config/v1_tickets/crypto_ticket_v2.yaml").read_text(encoding="utf-8"))
    v3 = yaml.safe_load((ROOT / "config/v1_tickets/crypto_ticket_v3.yaml").read_text(encoding="utf-8"))
    weekend = next(w for w in v3["window"]["windows"] if w["name"] == "WEEKEND")
    return [{**v2["window"], "name": "WEEKDAY"}, weekend]


def window_of(now: datetime, wins: list[dict]) -> str | None:
    for w in wins:
        local = now.astimezone(ZoneInfo(w["timezone"]))
        if local.isoweekday() in w["weekdays"] and \
                time.fromisoformat(w["start"]) <= local.time() < time.fromisoformat(w["end"]):
            return w["name"]
    return None


def parse_ts(text: str) -> datetime:
    t = datetime.fromisoformat(text)
    return t if t.tzinfo else t.replace(tzinfo=UTC)  # PR #128 M15 rows are naive UTC


def read_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def shared_paths(sym: str, out_dir: Path = RECORDED) -> dict[str, str]:
    m15 = f"{sym}_M15_recorded.csv" if out_dir == RECORDED_60D else f"../../manual_ticket/{sym}_M15_recorded.csv"
    return {"d1": f"{sym}_d1.csv", "h1": f"{sym}_h1.csv", "m5": f"{sym}_m5.csv", "m15": m15}


def partial_days(out_dir: Path, sym: str) -> dict[str, int]:
    """UTC days whose M5 file holds fewer than 288 bars -> bar count. Listed, never filled."""
    counts: dict[str, int] = {}
    for r in read_rows(out_dir / f"{sym}_m5.csv"):
        day = parse_ts(r["timestamp_utc"]).date().isoformat()
        counts[day] = counts.get(day, 0) + 1
    return {d: n for d, n in sorted(counts.items()) if n != 288}


def provenance_60d(out_dir: Path, sym: str, report: dict, files: dict, paths: dict) -> dict:
    """PR #143 (AGP-HOST-CRYPTO60) provenance, read from its PROVENANCE.md table, never assumed."""
    md_name = f"{sym}_M15_recorded.PROVENANCE.md"
    rows = [line.split("|")[1:-1] for line in (out_dir / md_name).read_text(encoding="utf-8").splitlines()
            if line.startswith("| 20") and line.count("|") == 9]
    offsets = sorted({r[2].strip() for r in rows})
    files[md_name] = sha(out_dir / md_name)
    return {"source": "MT5_VT_MARKETS_DEMO", "mission": "AGP-HOST-CRYPTO60", "symbol": sym,
            "recorded": True, "captured_at_utc": report["captured_at_utc"], "server": report["server"],
            "captured_in": "PR #143 (data/ccfd-recorded-60d)",
            "days": [r[0].strip() for r in rows], "days_kept": sum(r[1].strip() == "yes" for r in rows),
            "server_utc_offset_hours": offsets, "offset_method": "measured on EURUSD per day (17:00 "
            "America/New_York rollover, both edges agree); weekends keep an offset only if Fri and Mon agree",
            "offset_source": md_name, "partial_days_m5_bars": partial_days(out_dir, sym),
            "gap_policy": "missing bars are listed, never filled or interpolated",
            "sha256": {tf: files[rel] for tf, rel in paths.items()},
            "sha256_scope": "shared 60-day files; materialized per-case slices carry their own hashes",
            "commission_R": None, "commission_gap": COMMISSION_GAP}


def build(out_dir: Path = RECORDED) -> Path:
    report = json.loads((out_dir / "capture_report.json").read_text(encoding="utf-8"))
    wins = windows()
    files = {p.name: sha(p) for p in sorted(out_dir.glob("*.csv"))}
    files["capture_report.json"] = sha(out_dir / "capture_report.json")
    cases = []
    for sym in SYMBOLS:
        paths = shared_paths(sym, out_dir)
        files[paths["m15"]] = sha(out_dir / paths["m15"])
        prov = provenance_60d(out_dir, sym, report, files, paths) if out_dir == RECORDED_60D else {"source": "MT5_VT_MARKETS_DEMO", "mission": "AGP-DATA-R2", "symbol": sym,
                "recorded": True, "captured_at_utc": report["captured_at_utc"],
                "m15_captured_in": "PR #128 (AGP-DATA-R2)", "other_tfs_captured_in": "AGP-DATA-R2b",
                "sha256": {tf: files[rel] for tf, rel in paths.items()},
                "sha256_scope": "shared 14-day files; materialized per-case slices carry their own hashes",
                "commission_R": None, "commission_gap": COMMISSION_GAP}
        prov_name = f"{sym}_provenance.json"
        (out_dir / prov_name).write_text(json.dumps(prov, indent=2) + "\n", encoding="utf-8", newline="\n")
        files[prov_name] = sha(out_dir / prov_name)
        m15 = read_rows(out_dir / paths["m15"])
        m5_meta = {parse_ts(r["timestamp_utc"]): r for r in read_rows(out_dir / f"{sym}_m5_meta.csv")}
        for r in m15:
            now = parse_ts(r["timestamp_utc"]) + STEP["m15"]
            name = window_of(now, wins)
            if name is None:
                continue
            quote_bar = now - STEP["m5"]
            meta = m5_meta.get(quote_bar)
            if meta is None:
                raise SystemExit(f"{sym} {now}: no M5 bar for the case spread; refusing to invent one")
            cases.append({"id": f"{sym}_{name}_{now:%Y%m%dT%H%M}Z", "symbol": sym, "window": name,
                          "now": now.isoformat(), "paths": paths, "provenance": prov_name,
                          "spread": float(meta["spread_price"]), "commission_R": None,
                          "quote_time": quote_bar.isoformat(), "expected_result": None,
                          "expected_direction": None})
    manifest = {"source": "MT5_VT_MARKETS_DEMO", "mission": "AGP-DATA-R2", "cases": cases,
                "gaps": {"commission_R": COMMISSION_GAP},
                "files": dict(sorted(files.items()))}
    if out_dir == RECORDED_60D:
        manifest["mission"] = "AGP-HOST-CRYPTO60"
        manifest["gaps"]["partial_days_m5_bars"] = {sym: partial_days(out_dir, sym) for sym in SYMBOLS}
        manifest["gaps"]["policy"] = "missing bars are listed, never filled or interpolated"
    path = out_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


def verify(manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    bad = [rel for rel, digest in manifest["files"].items()
           if sha(manifest_path.parent / rel) != digest]
    if bad:
        raise SystemExit(f"sha256 mismatch, nothing materialized: {bad}")
    return manifest


def materialize(manifest_path: Path, out_dir: Path, limit: int | None = None) -> Path:
    manifest = verify(manifest_path)
    base = manifest_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    cache: dict[str, list[dict]] = {}
    cases = []
    for case in manifest["cases"][:limit]:
        now = datetime.fromisoformat(case["now"])
        prov = json.loads((base / case["provenance"]).read_text(encoding="utf-8"))
        new_paths, hashes = {}, {}
        for tf, rel in case["paths"].items():
            rows = cache.setdefault(rel, read_rows(base / rel))
            keep = [r for r in rows if parse_ts(r["timestamp_utc"]) + STEP[tf] <= now]
            name = f"{case['id']}_{tf}.csv"
            with (out_dir / name).open("w", encoding="utf-8", newline="\n") as f:
                f.write("timestamp_utc,open,high,low,close\n")
                for r in keep:
                    f.write(",".join([parse_ts(r["timestamp_utc"]).isoformat(), r["open"], r["high"],
                                      r["low"], r["close"]]) + "\n")
            new_paths[tf] = name
            hashes[tf] = sha(out_dir / name)
        case_prov = {**prov, "sha256": hashes, "derived_from_sha256": prov["sha256"],
                     "sha256_scope": "per-case slice materialized from the verified shared files"}
        prov_name = f"{case['id']}_provenance.json"
        (out_dir / prov_name).write_text(json.dumps(case_prov, indent=2) + "\n", encoding="utf-8")
        cases.append({**case, "paths": new_paths, "provenance": prov_name})
    out = out_dir / "manifest.json"
    out.write_text(json.dumps({"source": manifest["source"], "mission": manifest["mission"],
                               "cases": cases}, indent=2) + "\n", encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--dataset", choices=("recorded", "recorded_60d"), default="recorded")
    m = sub.add_parser("materialize")
    m.add_argument("--manifest", type=Path, default=RECORDED / "manifest.json")
    m.add_argument("--out-dir", type=Path, required=True)
    m.add_argument("--limit", type=int, default=None)
    args = p.parse_args(argv)
    if args.cmd == "build":
        path = build(RECORDED_60D if args.dataset == "recorded_60d" else RECORDED)
        data = json.loads(path.read_text(encoding="utf-8"))
        print("MANIFEST", path.relative_to(ROOT), "cases", len(data["cases"]), "sha256", sha(path))
    else:
        print("MATERIALIZED", materialize(args.manifest, args.out_dir, args.limit))
    return 0


if __name__ == "__main__":
    sys.exit(main())
