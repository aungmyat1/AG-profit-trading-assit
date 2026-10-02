"""Read-only local HTTP adapter (launched by scripts/run_api.py).

Exposes only owner-readable projections. It has no execution, broker, authorization,
Telegram or order path: every route is a GET over durable advisory state.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query

from api.crypto_opportunities import list_crypto_opportunities

app = FastAPI(title="AG Profit Trading -- Read-only API", version="0.2.0")


@app.get("/api/opportunities")
def opportunities(
    symbol: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
) -> list[dict[str, Any]]:
    try:
        return list_crypto_opportunities(symbol=symbol, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
