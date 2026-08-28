from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class Candle:
    time: datetime  # bar-open time, UTC
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None  # tick volume; optional so existing positional callers are unaffected
