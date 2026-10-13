"""OD1014-FAST D2 host evidence loader; no broker or network access."""
import datetime as dt
import hashlib
import json
from decimal import Decimal
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
REASON = "C10_PIP_SIZE_NOT_EVIDENCED"

def load_pip(symbol, root=None):
    root = Path(root) if root is not None else REPO_ROOT
    try:
        mapping = yaml.safe_load((root / "config/broker_symbol_map/vt_markets_demo.yaml").read_text())
        entry = mapping["entries"][symbol]
        record = json.loads((root / f"config/symbol_metadata/host_captured/{symbol}.json").read_text())
        payload = {k: v for k, v in record.items() if k != "sha256"}
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
        if (record["schema"] != "AG_HOST_SYMBOL_METADATA_V2" or record["server"] != "VTMarkets-Demo"
                or mapping["server"] != record["server"] or record["canonical_symbol"] != symbol
                or entry["status"] != "MAPPED" or record["broker_symbol"] != entry["broker_symbol"]
                or digest != record["sha256"] or digest != entry["host_capture"]["sha256"]):
            raise ValueError(REASON)
        point = record["fields"]["point"]
        if isinstance(point, bool) or not isinstance(point, (int, float)):
            raise ValueError(REASON)
        value = Decimal(str(point))
        if not value.is_finite() or value <= 0 or point != entry["expected"]["point"]:
            raise ValueError(REASON)
        captured = record["captured_at_utc"]
        stamp = dt.datetime.fromisoformat(captured.replace("Z", "+00:00"))
        if stamp.tzinfo is None or stamp.utcoffset() != dt.timedelta(0):
            raise ValueError(REASON)
        pip = float(value * 10)
        if not Decimal(str(pip)).is_finite() or pip <= 0:
            raise ValueError(REASON)
        return pip, "10*point host_captured " + captured
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError, yaml.YAMLError):
        return None, REASON
