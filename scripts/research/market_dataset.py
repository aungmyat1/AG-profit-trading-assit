"""Strategy-blind BTC/ETH raw M5 parsing, normalization, QA and UTC resampling."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import csv
import io
import json
import re
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

RAW_FIELDS = ("source_timestamp", "timestamp_utc", "open", "high", "low", "close",
              "tick_volume", "spread", "real_volume")
FORBIDDEN_RAW = {"signal", "bias", "setup", "label", "target", "entry", "sl", "tp",
                 "future_return", "profit"}


class DatasetError(ValueError):
    pass


def _parse_ohlc_csv(raw: str) -> list[dict] | None:
    try:
        reader = csv.DictReader(io.StringIO(raw))
        fields = {(f or "").strip().lower() for f in (reader.fieldnames or [])}
        rows = list(reader)
        if {"time", "open", "high", "low", "close"}.issubset(fields) and rows:
            return rows
    except (csv.Error, TypeError):
        pass
    return None


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def vt_server_wall_to_utc(server_wall: datetime) -> pd.Timestamp:
    """Apply the repository's owner-stated VT rule: server midnight is New York 17:00."""
    ny_wall = server_wall.replace(tzinfo=None) - pd.Timedelta(hours=7).to_pytimedelta()
    return pd.Timestamp(ny_wall.replace(tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc))


def parse_candles(payload: Any, *, broker_utc_offset: int | None = None,
                  source_semantics: str = "UTC") -> pd.DataFrame:
    """Parse MCP JSON/text structures without inferring time semantics."""
    if isinstance(payload, dict):
        for key in ("candles", "rates", "rows", "data", "result"):
            if key in payload:
                return parse_candles(payload[key], broker_utc_offset=broker_utc_offset, source_semantics=source_semantics)
        raise DatasetError(f"candle response object has unsupported fields: {sorted(map(str, payload.keys()))[:12]}")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = _parse_ohlc_csv(payload)
            if payload is None:
                raise DatasetError("candle text is neither JSON nor supported OHLC CSV") from None
    if isinstance(payload, list) and payload and isinstance(payload[0], dict) and "text" in payload[0]:
        try:
            return parse_candles(json.loads(payload[0]["text"]), broker_utc_offset=broker_utc_offset, source_semantics=source_semantics)
        except (json.JSONDecodeError, TypeError):
            raise DatasetError("MCP candle text is not JSON") from None
    if not isinstance(payload, list):
        raise DatasetError(f"candle response is not a list (type={type(payload).__name__})")
    rows = []
    for rec in payload:
        if not isinstance(rec, dict):
            raise DatasetError("candle row is not an object")
        ts = next((rec[k] for k in ("time", "timestamp", "date", "datetime") if k in rec), None)
        if ts is None:
            raise DatasetError("candle timestamp is missing")
        source = str(ts)
        try:
            if isinstance(ts, (int, float)):
                unit = "ms" if abs(float(ts)) > 10**11 else "s"
                t = pd.to_datetime(ts, unit=unit, utc=True, errors="raise")
            else:
                t = pd.to_datetime(ts, utc=False, errors="raise")
            if source_semantics == "VT_SERVER_WALL_CLOCK":
                # The proxy may append a UTC marker to fields that are still server wall time.
                wall = t.tz_convert(None).to_pydatetime() if getattr(t, "tzinfo", None) is not None else t.to_pydatetime()
                utc = vt_server_wall_to_utc(wall)
            elif getattr(t, "tzinfo", None) is not None:
                utc = t.tz_convert("UTC")
            elif broker_utc_offset is not None:
                utc = (t - pd.Timedelta(hours=broker_utc_offset)).tz_localize("UTC")
            else:
                raise DatasetError("time authority required for naive source timestamps")
        except DatasetError:
            raise
        except Exception as exc:
            raise DatasetError("invalid candle timestamp") from exc
        row = {"source_timestamp": source, "timestamp_utc": utc}
        aliases = {"tick_volume": ("tick_volume", "tickVolume", "volume"),
                   "real_volume": ("real_volume", "realVolume")}
        for field in ("open", "high", "low", "close", "spread", "tick_volume", "real_volume"):
            keys = aliases.get(field, (field,))
            val = next((rec[k] for k in keys if k in rec), None)
            if val is not None:
                try:
                    row[field] = float(val)
                except (TypeError, ValueError) as exc:
                    raise DatasetError(f"invalid numeric field {field}") from exc
        if not all(k in row for k in ("open", "high", "low", "close")):
            raise DatasetError("candle missing OHLC fields")
        rows.append(row)
    return pd.DataFrame(rows, columns=[c for c in RAW_FIELDS if c in set().union(*(r.keys() for r in rows))])


def validate(frame: pd.DataFrame, timeframe_minutes=5) -> dict:
    required = {"source_timestamp", "timestamp_utc", "open", "high", "low", "close"}
    if not required.issubset(frame.columns):
        raise DatasetError(f"schema missing {sorted(required - set(frame.columns))}")
    t = pd.to_datetime(frame.timestamp_utc, utc=True, errors="coerce")
    if t.isna().any():
        raise DatasetError("invalid UTC timestamp")
    deltas = t.diff().dropna()
    dup = int(t.duplicated().sum())
    nonmonotonic = bool((deltas < pd.Timedelta(0)).any())
    numeric = frame[["open", "high", "low", "close"]].apply(pd.to_numeric, errors="coerce")
    invalid_mask = ((numeric.high < numeric.low) | (numeric.high < numeric.open) |
                    (numeric.high < numeric.close) | (numeric.low > numeric.open) |
                    (numeric.low > numeric.close) | ~numeric.notna().all(axis=1))
    invalid = int(invalid_mask.sum())
    expected = pd.Timedelta(minutes=timeframe_minutes)
    gaps = []
    for i in deltas[deltas > expected].index:
        gap = t.loc[i] - t.loc[i - 1]
        # Crypto CFDs can trade through weekends; absent verified venue hours, do not
        # relabel a long weekend gap as an expected closure.
        category = "UNEXPECTED_GAP" if gap <= pd.Timedelta(minutes=15) else "UNKNOWN_GAP"
        gaps.append({"after": t.loc[i - 1].isoformat(), "before": t.loc[i].isoformat(),
                     "delta_seconds": gap.total_seconds(), "classification": category})
    return {"row_count": len(frame), "duplicates": dup, "nonmonotonic": nonmonotonic,
            "invalid_ohlc": invalid, "gaps": gaps,
            "unexpected_gaps": sum(g["classification"] == "UNEXPECTED_GAP" for g in gaps),
            "unknown_gaps": sum(g["classification"] == "UNKNOWN_GAP" for g in gaps),
            "first_timestamp_utc": t.min().isoformat() if len(t) else None,
            "last_timestamp_utc": t.max().isoformat() if len(t) else None,
            "utc_normalized": True, "closed_bar_status": "CLOSED_EXCLUDING_FORMING_BAR"}


def closed_rows(frame: pd.DataFrame, now_utc: datetime | None = None) -> pd.DataFrame:
    now = pd.Timestamp(now_utc or datetime.now(timezone.utc))
    # M5 candle timestamp denotes its opening time; remove the currently forming bar.
    cutoff = now.floor("5min")
    return frame.loc[pd.to_datetime(frame.timestamp_utc, utc=True) < cutoff].reset_index(drop=True)


def aggregate(frame: pd.DataFrame, rule: str) -> pd.DataFrame:
    if rule not in {"15min", "1h", "1D"}:
        raise ValueError("unsupported UTC aggregation rule")
    quality = validate(frame)
    if not quality["row_count"]:
        return pd.DataFrame()
    if (quality["duplicates"] or quality["nonmonotonic"] or quality["invalid_ohlc"] or
            any(g["classification"] != "EXPECTED_CLOSURE" for g in quality["gaps"])
            or quality["unknown_gaps"] or quality["unexpected_gaps"]):
        raise DatasetError("derived timeframe blocked by unresolved source quality issue")
    df = frame.copy()
    df["timestamp_utc"] = pd.to_datetime(df.timestamp_utc, utc=True)
    df = df.set_index("timestamp_utc").sort_index()
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    for c in ("tick_volume", "real_volume"):
        if c in df.columns:
            agg[c] = "sum"
    out = df.resample(rule, origin="epoch", label="left", closed="left").agg(agg).dropna(subset=["open"])
    # Incomplete edge buckets are excluded; full constituent count required.
    expected = int(pd.Timedelta(rule) / pd.Timedelta(minutes=5))
    counts = df["close"].resample(rule, origin="epoch", label="left", closed="left").count()
    out = out.loc[counts[counts == expected].index]
    out.insert(0, "source_timestamp", out.index.astype(str))
    return out.reset_index()


def decode_tool_result(result: dict):
    if not isinstance(result, dict) or result.get("isError") is True:
        raise DatasetError("MCP tool response malformed or in error")
    if "structuredContent" in result:
        return result["structuredContent"]
    content = result.get("content")
    if not isinstance(content, list) or not content or not isinstance(content[0], dict) or "text" not in content[0]:
        raise DatasetError("MCP tool response has no candle content")
    try:
        return json.loads(content[0]["text"])
    except json.JSONDecodeError:
        raw = content[0]["text"]
        rows = _parse_ohlc_csv(raw)
        if rows is not None:
            return rows
        raise DatasetError("MCP tool content is neither JSON nor supported OHLC CSV") from None


def decode_symbol_listing(result: dict) -> Any:
    """Keep a symbol-list response local; it may be JSON or plain text from the MCP tool."""
    if not isinstance(result, dict) or result.get("isError") is True:
        raise DatasetError("MCP symbol-list response malformed or in error")
    if "structuredContent" in result:
        return result["structuredContent"]
    content = result.get("content")
    if not isinstance(content, list):
        raise DatasetError("MCP symbol-list response has no content")
    texts = [x["text"] for x in content if isinstance(x, dict) and isinstance(x.get("text"), str)]
    if not texts:
        raise DatasetError("MCP symbol-list response has no text")
    joined = "\n".join(texts)
    try:
        return json.loads(joined)
    except json.JSONDecodeError:
        return joined


def resolve_broker_crypto_symbols(listing: Any) -> dict[str, str]:
    """Resolve only exact broker-listed BTCUSD/ETHUSD tokens (optionally n-prefixed)."""
    found = {}
    token_re = re.compile(r"(?:n)?(?:BTCUSD|ETHUSD)", re.I)
    def add_token(token):
        if not isinstance(token, str) or not token_re.fullmatch(token):
            return
        canonical = token.upper().removeprefix("N")
        prior = found.get(canonical)
        if prior is None or token.upper() == canonical:
            found[canonical] = token.upper()
    def walk(value):
        if isinstance(value, str):
            add_token(value.strip())
        elif isinstance(value, dict):
            for key, child in value.items():
                if key.lower() in {"name", "symbol", "ticker", "broker_symbol", "broker_symbol_name"}:
                    if isinstance(child, str):
                        add_token(child.strip())
                    elif isinstance(child, list):
                        for item in child:
                            add_token(item)
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    if isinstance(listing, str):
        for match in token_re.finditer(listing):
            # Confirm symbol token boundaries in free-form tool text.
            if ((match.start() == 0 or not listing[match.start() - 1].isalnum()) and
                    (match.end() == len(listing) or not listing[match.end()].isalnum())):
                add_token(match.group())
    else:
        walk(listing)
    return found

