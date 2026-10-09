from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.research.market_dataset import aggregate, sha256_file, validate


def main():
    ap = argparse.ArgumentParser(description="Validate strategy-blind normalized market Parquet")
    ap.add_argument("dataset", type=Path)
    ap.add_argument("--timeframe-minutes", type=int, default=5)
    ap.add_argument("--derive", action="store_true", help="write UTC M15/H1/D1 only after raw QA passes")
    ap.add_argument("--symbol", choices=("BTCUSD", "ETHUSD"))
    args = ap.parse_args()
    frame = pd.read_parquet(args.dataset)
    report = validate(frame, args.timeframe_minutes)
    report["file"] = str(args.dataset)
    report["sha256"] = sha256_file(args.dataset)
    report["derived_files"] = []
    hard_fail = bool(report["duplicates"] or report["nonmonotonic"] or report["invalid_ohlc"] or report["unexpected_gaps"])
    if args.derive and not hard_fail and not report["unknown_gaps"]:
        symbol = args.symbol or args.dataset.name.split("_")[0]
        out_dir = ROOT / "data/research/derived/crypto_cfd"
        out_dir.mkdir(parents=True, exist_ok=True)
        for rule, suffix in (("15min", "M15"), ("1h", "H1"), ("1D", "D1")):
            out = out_dir / f"{symbol}_{suffix}_DERIVED.parquet"
            derived = aggregate(frame, rule)
            derived.to_parquet(out, index=False)
            report["derived_files"].append(str(out))
    print(json.dumps(report, indent=2))
    return 2 if hard_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())

