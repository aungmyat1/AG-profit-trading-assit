#!/usr/bin/env python
"""Return sanitized open MT5 positions in the web frontend's position shape."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from mt5.account import positions
from mt5.connection import MT5ConnectionError, connect_configured
from trade_management.claims import load_claims


def main() -> int:
    try:
        connect_configured()
    except MT5ConnectionError as exc:
        print(json.dumps({"status": "MT5_NOT_CONNECTED", "reason_code": str(exc)}))
        return 1

    claims = load_claims(str(ROOT / "journal" / "claims.json"))
    payload = []
    for item in positions():
        ticket = int(item.ticket)
        claim = claims.get(ticket)
        side = "BUY" if int(item.type) == 0 else "SELL"
        entry = float(item.price_open)
        current = float(item.price_current)
        sl = float(item.sl or 0.0)
        risk_distance = abs(entry - sl) if sl else 0.0
        current_r = ((current - entry) if side == "BUY" else (entry - current)) / risk_distance if risk_distance else 0.0
        payload.append({
            "ticket": ticket,
            "symbol": str(item.symbol),
            "strategyId": claim.strategy if claim and claim.strategy else "MT5_MANUAL",
            "side": side,
            "volume": float(item.volume),
            "entryPrice": entry,
            "currentPrice": current,
            "stopLoss": sl,
            "takeProfit1": float(claim.tp1) if claim and claim.tp1 is not None else float(item.tp or 0.0),
            "takeProfit2": float(item.tp or 0.0),
            "openTime": int(item.time),
            "pnl": float(item.profit),
            "pnlR": round(current_r, 3),
            "status": "OPEN",
            "claimed": claim is not None,
            "isBreakevenMoved": bool(sl and abs(sl - entry) < 1e-12),
            "tp1Filled": False,
            "journalNotes": [],
        })
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
