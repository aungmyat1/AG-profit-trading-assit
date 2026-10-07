"""Daily deterministic evaluator (Phase I).

One entry point that, for every required instrument/session pair, produces a canonical
decision record and archives it.  If market data is unavailable it still produces a
deterministic BLOCKED / INSUFFICIENT_DATA / OUT_OF_SESSION record — there is NEVER a
silent session.

Supported data inputs:
  - MT5 read-only candles via `scripts/host/live_eval_smoke.py` (Windows host)
  - injected/pre-canned candles (test/dry-run) for offline determinism

The runner NEVER calls the broker for orders, never changes strategy logic, and never
enables demo/live.
"""
from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from strategy_engine import evaluate as engine_evaluate, load_strategy
from strategy_engine.session import Candle
from v1_tickets import fx as v1_fx
from v1_tickets.canonical_ticket import append_archive, build_canonical_ticket
from v1_tickets.actionability import (
    BLOCKED, EXPIRED, INSUFFICIENT_DATA, NO_TRADE, OUT_OF_SESSION, WATCH_READY,
)
from v1_tickets.policy_loader import ActionabilityPolicy, load_policy

STRATEGY_PATH = v1_fx.STRATEGY_PATH

FX_PAIRS: List[Tuple[str, str]] = [
    (sym, cyc) for cyc in v1_fx.V1_CYCLES for sym in v1_fx.V1_FX_SYMBOLS
]
ARCHIVE_SUBDIR = os.path.join("ticket_delivery", "daily_evaluator")


def __getattr__(name: str):
    # Preserve the public constant without loading crypto's native MT5 dependency
    # when an offline caller needs only the FX evaluator.
    if name == "CRYPTO_SYMBOLS":
        from v1_tickets import crypto
        return list(crypto.V1_CRYPTO_SYMBOLS)
    raise AttributeError(name)


@dataclass
class EvalResult:
    instrument: str
    session: str
    venue: str
    decision: str
    ticket_id: str
    canonical: Dict[str, Any]
    archive_path: str
    rendered_text: str


@dataclass
class CandleBundle:
    """Container for one (symbol, cycle) pair's candles — matches what the engine expects."""
    session_candles: Sequence[Candle]
    expected_bar_count: int
    post_session_candles: Sequence[Candle]
    data_close: Optional[dt.datetime]
    spread: Optional[float]
    current_price: Optional[float]


CandleProvider = Callable[[str, str, dt.date, dt.datetime], Optional[CandleBundle]]


def _expected_bar_count(cycle: str) -> int:
    """Number of M15 bars in the reference window per the frozen contract:
    ASIAN_LONDON ref is 00:00-06:00 -> 24 M15 bars;
    LONDON_NEWYORK ref is 06:00-11:00 -> 20 M15 bars.
    """
    return {"ASIAN_LONDON": 24, "LONDON_NEWYORK": 20}.get(cycle, 24)


def _data_error_provenance(exc: BaseException) -> Dict[str, str]:
    """Keep acquisition failures machine-readable without changing their fail-closed result."""
    code = str(getattr(exc, "code", type(exc).__name__))[:80]
    detail = str(getattr(exc, "detail", str(exc)))[:300]
    if code == "SYMBOL_MAPPING_MISSING":
        layer = "SYMBOL_RESOLUTION"
    elif code in ("DUPLICATE_TIMESTAMP", "NON_MONOTONIC"):
        layer = "BAR_ORDER"
    elif code == "OFF_GRID_TIMESTAMP":
        layer = "BAR_GRID"
    elif code == "CONVERSION_ERROR":
        layer = "TIME_NORMALIZATION"
    elif code == "DATA_MISSING" and "M15_WINDOW_INCOMPLETE" in detail:
        layer = "WINDOW_COMPLETENESS"
    elif code == "DATA_MISSING" and "QUOTE_" in detail:
        layer = "QUOTE_VALIDATION"
    elif code == "DATA_MISSING":
        layer = "MT5_FETCH"
    else:
        layer = "OTHER"
    return {"code": code, "detail": detail, "layer": layer}


def evaluate_fx_pair(
    symbol: str,
    cycle: str,
    *,
    now: dt.datetime,
    day: dt.date,
    candle_provider: CandleProvider,
    archive_root: str,
    data_source: str = "MT5_VT_MARKETS_DEMO",
    policy=None,
) -> EvalResult:
    """Evaluate one FX (symbol, cycle) deterministically. On missing data returns a
    BLOCKED/INSUFFICIENT_DATA record rather than raising."""
    now = now if now.tzinfo else now.replace(tzinfo=dt.timezone.utc)
    strategy = load_strategy(STRATEGY_PATH)
    windows = v1_fx.session_windows_utc(day)[cycle]
    trade_end = windows["trade"][1]
    try:
        bundle = candle_provider(symbol, cycle, day, now)
    except Exception as exc:  # noqa: BLE001
        ticket = v1_fx.build_fx_error_ticket(
            symbol, cycle, day, evaluated_at=now, reason_code=type(exc).__name__,
            detail=str(exc)[:300], decision="DATA_ERROR", data_source=data_source,
        )
        ticket["data_error"] = _data_error_provenance(exc)
        return _finalize(ticket, now=now, current_price=None, window_end=trade_end,
                         archive_root=archive_root, venue=data_source, policy=policy, exc=exc)

    if bundle is None:
        # No data available but we still produce a deterministic archived decision.
        ticket = v1_fx.build_fx_error_ticket(
            symbol, cycle, day, evaluated_at=now, reason_code="NO_CANDLE_DATA",
            detail="candle provider returned no data", decision="BLOCKED",
            data_source=data_source,
        )
        return _finalize(ticket, now=now, current_price=None, window_end=trade_end,
                         archive_root=archive_root, venue=data_source, policy=policy)

    ticket = v1_fx.build_fx_ticket(
        symbol, cycle, day, list(bundle.session_candles), bundle.expected_bar_count,
        list(bundle.post_session_candles), data_source=data_source,
        evaluated_at=now, data_close=bundle.data_close, spread=bundle.spread,
    )
    return _finalize(ticket, now=now, current_price=bundle.current_price,
                     window_end=trade_end, archive_root=archive_root, venue=data_source, policy=policy)


def evaluate_crypto_symbol(
    symbol: str,
    *,
    now: dt.datetime,
    day: dt.date,
    feed_provider: Callable[..., Any],
    state_dir: str,
    archive_root: str,
    config_path: Optional[str] = None,
    policy: Optional[ActionabilityPolicy] = None,
) -> EvalResult:
    """Evaluate one crypto symbol deterministically.  feed_provider must return a
    FallbackPublicCryptoFeed-compatible feed (or None, which yields a BLOCKED record)."""
    from v1_tickets import crypto as v1_crypto
    import yaml
    now = now if now.tzinfo else now.replace(tzinfo=dt.timezone.utc)
    cfg = None
    if config_path is not None:
        with open(config_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
    feed = None
    try:
        feed = feed_provider(symbol, now=now, cfg=cfg) if feed_provider else None
    except Exception as exc:  # noqa: BLE001
        # Build a synthetic error ticket via v1_crypto by raising inside the call.
        return _eval_crypto_with_error(symbol, now=now, day=day, state_dir=state_dir,
                                       archive_root=archive_root, cfg=cfg, exc=exc)
    if feed is None:
        # Build a BLOCKED ticket manually matching the v1_crypto shape.
        ticket = {
            "label": "INFORMATIONAL TICKET -- NOT A BROKER ORDER",
            "strategy_id": v1_crypto.daily_report.STRATEGY_ID,
            "strategy_version": v1_crypto.daily_report.STRATEGY_VERSION,
            "profile": "CRYPTO_PERP", "symbol": symbol,
            "symbol_status": v1_crypto.SYMBOL_STATUS[symbol], "cycle": v1_crypto.CYCLE,
            "observation_date": day.isoformat(),
            "evaluated_at": now.isoformat(), "delivery_mode": "ARCHIVE_ONLY",
            "data_source": "NONE", "primary_failure_reason": "NO_FEED_CONFIGURED",
            "decision": "BLOCKED", "reason_codes": ["NO_FEED_CONFIGURED"],
        }
        w = v1_crypto.window_status(cfg, day, now)
        if w != "IN_WINDOW":
            ticket["window_status"] = w
            ticket["reason_codes"] = ["OUTSIDE_CONFIG_WINDOW"]
        return _finalize(ticket, now=now, current_price=None, window_end=None,
                         archive_root=archive_root, venue=ticket["data_source"], policy=policy)
    try:
        ticket = v1_crypto.build_crypto_ticket(symbol, day, now, feed=feed, state_dir=state_dir, config=cfg)
    except Exception as exc:  # noqa: BLE001
        return _eval_crypto_with_error(symbol, now=now, day=day, state_dir=state_dir,
                                       archive_root=archive_root, cfg=cfg, exc=exc)
    current = None
    m5 = []
    try:
        bundle = feed.fetch_bundle(symbol, [("M5", v1_crypto.pipeline.M5_LOOKBACK_COUNT)])
        m5 = bundle.candles.get("M5") or []
    except Exception:  # noqa: BLE001
        pass
    if m5:
        last = m5[-1]
        current = float(last.close)
    venue = ticket.get("data_source") or "CRYPTO_PERP"
    return _finalize(ticket, now=now, current_price=current, window_end=None,
                     archive_root=archive_root, venue=venue, policy=policy)


def _eval_crypto_with_error(symbol, *, now, day, state_dir, archive_root, cfg, exc, policy=None):
    from v1_tickets import crypto as v1_crypto
    ticket = {
        "label": "INFORMATIONAL TICKET -- NOT A BROKER ORDER",
        "strategy_id": v1_crypto.daily_report.STRATEGY_ID,
        "strategy_version": v1_crypto.daily_report.STRATEGY_VERSION,
        "profile": "CRYPTO_PERP", "symbol": symbol,
        "symbol_status": v1_crypto.SYMBOL_STATUS[symbol], "cycle": v1_crypto.CYCLE,
        "observation_date": day.isoformat(),
        "evaluated_at": now.isoformat(), "delivery_mode": "ARCHIVE_ONLY",
        "data_source": "NONE", "primary_failure_reason": type(exc).__name__,
        "decision": "DATA_ERROR", "reason_codes": [type(exc).__name__],
        "detail": str(exc)[:300],
    }
    if cfg is not None:
        ticket["ticket_config"] = f"{cfg['config_id']}@v{cfg['version']}"
    return _finalize(ticket, now=now, current_price=None, window_end=None,
                     archive_root=archive_root, venue="NONE", policy=policy)


def _finalize(ticket: Dict[str, Any], *, now: dt.datetime, current_price: Optional[float],
              window_end: Optional[dt.datetime], archive_root: str, venue: str,
              policy=None, exc: Optional[BaseException] = None) -> EvalResult:
    canonical = build_canonical_ticket(ticket, now=now, current_price=current_price,
                                       window_end=window_end, policy=policy)
    from v1_tickets.canonical_ticket import render_canonical
    text = render_canonical(canonical)
    sym = canonical["instrument"]
    session = canonical["session"]
    day = (canonical.get("session_date") or now.date().isoformat())[:10]
    path = os.path.join(archive_root, ARCHIVE_SUBDIR, f"{day}_{sym}_{session}.jsonl")
    append_archive(path, canonical)
    return EvalResult(instrument=sym, session=session, venue=venue,
                      decision=canonical["decision"], ticket_id=canonical["ticket_id"],
                      canonical=canonical, archive_path=path, rendered_text=text)


def run_daily_evaluation(
    *,
    now: Optional[dt.datetime] = None,
    day: Optional[dt.date] = None,
    candle_provider: Optional[CandleProvider] = None,
    crypto_feed_provider: Optional[Callable] = None,
    archive_root: str = ".",
    state_dir: str = os.path.join("artifacts", "crypto_state"),
    include_crypto: bool = True,
    fx_data_source: str = "MT5_VT_MARKETS_DEMO",
    policy: Optional[ActionabilityPolicy] = None,
    policy_root: str = ".",
    policy_override_path: Optional[str] = None,
    policy_override_dict: Optional[Dict] = None,
) -> List[EvalResult]:
    """Run every required (instrument, session) pair deterministically.

    Always returns one EvalResult per configured pair; never raises data errors to the
    caller (they become INSUFFICIENT_DATA records).  This guarantees NO SILENT SESSION.

    Policy is loaded once and threaded to every pair; DI via `policy` (preloaded
    ActionabilityPolicy) or override path/dict is supported for tests.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    now = now if now.tzinfo else now.replace(tzinfo=dt.timezone.utc)
    day = day or now.date()
    if policy is None:
        policy = load_policy(policy_root, override_path=policy_override_path,
                             override_dict=policy_override_dict)
    results: List[EvalResult] = []
    provider = candle_provider or _null_candle_provider
    for sym, cyc in FX_PAIRS:
        try:
            results.append(evaluate_fx_pair(sym, cyc, now=now, day=day,
                                            candle_provider=provider,
                                            archive_root=archive_root,
                                            data_source=fx_data_source,
                                            policy=policy))
        except Exception as exc:  # noqa: BLE001 — emergency fail-closed: still produce a record
            ticket = v1_fx.build_fx_error_ticket(
                sym, cyc, day, evaluated_at=now, reason_code="EVALUATION_EXCEPTION",
                detail=f"{type(exc).__name__}: {exc!s}"[:300], decision="DATA_ERROR",
                data_source=fx_data_source)
            results.append(_finalize(ticket, now=now, current_price=None, window_end=None,
                                     archive_root=archive_root, venue=fx_data_source,
                                     policy=policy, exc=exc))
    if include_crypto:
        from v1_tickets import crypto as v1_crypto
        for sym in v1_crypto.V1_CRYPTO_SYMBOLS:
            try:
                results.append(evaluate_crypto_symbol(
                    sym, now=now, day=day, feed_provider=crypto_feed_provider,
                    state_dir=state_dir, archive_root=archive_root,
                    config_path=v1_crypto.ACTIVE_CONFIG, policy=policy,
                ))
            except Exception as exc:  # noqa: BLE001
                results.append(_eval_crypto_with_error(
                    sym, now=now, day=day, state_dir=state_dir, archive_root=archive_root,
                    cfg=None, exc=exc, policy=policy))
    return results


def _null_candle_provider(symbol: str, cycle: str, day: dt.date, now: dt.datetime) -> Optional[CandleBundle]:
    """Default provider: no data, yields deterministic BLOCKED records."""
    return None


def fixture_candle_provider(session_candles: Sequence[Candle], expected_bar_count: int,
                            post_candles: Sequence[Candle], *, spread: Optional[float] = None,
                            current_price: Optional[float] = None,
                            data_close: Optional[dt.datetime] = None) -> CandleProvider:
    """Build a CandleProvider that returns the same canned candles for every (sym, cycle)
    pair (useful for tests / offline dry-runs)."""
    def _p(symbol: str, cycle: str, day: dt.date, now: dt.datetime) -> CandleBundle:
        dc = data_close
        if dc is None and post_candles:
            dc = post_candles[-1].time + dt.timedelta(minutes=15)
        cp = current_price
        if cp is None and post_candles:
            cp = float(post_candles[-1].close)
        return CandleBundle(list(session_candles), expected_bar_count, list(post_candles),
                            data_close=dc, spread=spread, current_price=cp)
    return _p
