#!/usr/bin/env python3
"""Audit a simple OHLCV CSV without changing it. Uses the Python standard library."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path


def args_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", type=Path)
    parser.add_argument("--timestamp", default="timestamp", help="Timestamp column name")
    parser.add_argument("--open", dest="open_col", default="open")
    parser.add_argument("--high", dest="high_col", default="high")
    parser.add_argument("--low", dest="low_col", default="low")
    parser.add_argument("--close", dest="close_col", default="close")
    parser.add_argument("--volume", dest="volume_col", default="volume")
    parser.add_argument("--max-examples", type=int, default=10)
    parser.add_argument("--output", type=Path, help="Optional JSON output path")
    return parser


def parse_timestamp(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d", "%Y/%m/%d %H:%M:%S"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                pass
    raise ValueError(f"unsupported timestamp: {value!r}")


def main() -> int:
    args = args_parser().parse_args()
    required = [args.timestamp, args.open_col, args.high_col, args.low_col, args.close_col, args.volume_col]
    issues: Counter[str] = Counter()
    examples: dict[str, list[dict[str, object]]] = {}
    timestamps: list[datetime] = []
    timestamp_texts: list[str] = []
    row_count = 0

    def flag(kind: str, row_number: int, detail: str) -> None:
        issues[kind] += 1
        bucket = examples.setdefault(kind, [])
        if len(bucket) < args.max_examples:
            bucket.append({"row": row_number, "detail": detail})

    with args.csv_file.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        missing = [name for name in required if name not in fields]
        if missing:
            report = {
                "status": "fail",
                "file": str(args.csv_file),
                "row_count": 0,
                "missing_columns": missing,
                "available_columns": fields,
            }
            payload = json.dumps(report, indent=2)
            print(payload)
            if args.output:
                args.output.write_text(payload + "\n", encoding="utf-8")
            return 2

        for row_number, row in enumerate(reader, start=2):
            row_count += 1
            raw_ts = (row.get(args.timestamp) or "").strip()
            timestamp_texts.append(raw_ts)
            try:
                timestamps.append(parse_timestamp(raw_ts))
            except ValueError as exc:
                flag("invalid_timestamp", row_number, str(exc))

            values: dict[str, float] = {}
            for label, column in (
                ("open", args.open_col),
                ("high", args.high_col),
                ("low", args.low_col),
                ("close", args.close_col),
                ("volume", args.volume_col),
            ):
                try:
                    number = float(row[column])
                    if not math.isfinite(number):
                        raise ValueError("not finite")
                    values[label] = number
                except (TypeError, ValueError):
                    flag("invalid_numeric", row_number, f"{column}={row.get(column)!r}")

            if len(values) != 5:
                continue
            o, h, low, c, volume = (values[k] for k in ("open", "high", "low", "close", "volume"))
            if min(o, h, low, c) <= 0:
                flag("nonpositive_price", row_number, f"O/H/L/C={o}/{h}/{low}/{c}")
            if volume < 0:
                flag("negative_volume", row_number, f"volume={volume}")
            if h < low:
                flag("high_below_low", row_number, f"high={h}, low={low}")
            if h < max(o, c):
                flag("high_below_open_or_close", row_number, f"O/H/C={o}/{h}/{c}")
            if low > min(o, c):
                flag("low_above_open_or_close", row_number, f"O/L/C={o}/{low}/{c}")

    duplicate_count = sum(count - 1 for count in Counter(timestamp_texts).values() if count > 1)
    if duplicate_count:
        issues["duplicate_timestamp"] = duplicate_count
        duplicates = [value for value, count in Counter(timestamp_texts).items() if count > 1]
        examples["duplicate_timestamp"] = [
            {"timestamp": value, "occurrences": timestamp_texts.count(value)}
            for value in duplicates[: args.max_examples]
        ]

    if len(timestamps) >= 2:
        unsorted = sum(current <= previous for previous, current in zip(timestamps, timestamps[1:]))
        if unsorted:
            issues["non_increasing_timestamp"] = unsorted

    status = "pass" if not issues else "warn"
    if any(name in issues for name in ("invalid_timestamp", "invalid_numeric", "high_below_low")):
        status = "fail"
    report = {
        "status": status,
        "file": str(args.csv_file),
        "row_count": row_count,
        "issue_counts": dict(sorted(issues.items())),
        "examples": examples,
        "notes": [
            "This structural audit does not know the instrument's calendar or expected sampling frequency.",
            "Review timezone, corporate actions, rolls, funding, outliers, and point-in-time integrity separately.",
            "No input rows were modified.",
        ],
    }
    payload = json.dumps(report, indent=2, default=str)
    print(payload)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
