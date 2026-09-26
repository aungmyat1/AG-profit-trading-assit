"""Run one bounded, public-only BTCUSDT opportunity scan."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from crypto_opportunity_scanner.scanner import scan_live_once


def main() -> int:
    result = scan_live_once()
    print(json.dumps({
        "status": result.status,
        "reason_code": result.reason_code,
        "candidate_id": result.candidate.candidate_id if result.candidate else None,
        "strategy_id": result.candidate.strategy_id if result.candidate else None,
        "market_data_mode": result.candidate.market_data_mode if result.candidate else None,
        "deduplicated": result.deduplicated,
    }, sort_keys=True))
    return 0 if result.status in {"NO_OPPORTUNITY", "OPPORTUNITY_UPDATED", "UNCHANGED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
