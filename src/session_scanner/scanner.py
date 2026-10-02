"""Read-only session scan orchestration.

    Terminal MCP (read-only allowlist)
      -> canonical instrument registry -> time authority -> history sync / quality gate
      -> session engine -> market state -> strategy adapter (strategy_engine.evaluate)
      -> checklist -> READY / NO_TRADE -> proposal builder -> STOP

There is no broker-mutation import or call anywhere in this package.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import yaml

from market_structure.config import load_market_structure_config

from . import market_state as ms
from .checklist import PASS, READY, evaluate_checklist, signal_entry_status, spread_gate
from .proposal import build_ticket
from .quality import FRESH, assess_quote, assess_series, fetch_with_sync, normalize_bars
from .registry import InstrumentRegistryError, load_specs, verify_live
from .sessions import classify, load_canonical_windows, previous_day_levels, window_levels
from .strategy_adapter import AsianSweepAdapter, resolve_proposal_scope, strategy_catalog
from .timebase import TIME_GATE_PASS, derive_time_authority, parse_server_wallclock

SCANNER_CONFIG_PATH = "config/session_scanner_v1.yaml"
TIMEFRAMES = ("D1", "H1", "M15", "M5")


def load_scanner_config(path: str = SCANNER_CONFIG_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _latest_tick(source, broker_symbol: str, server_now: datetime) -> Optional[dict]:
    ticks = source.ticks(broker_symbol, server_now - timedelta(minutes=5), server_now + timedelta(minutes=1))
    return ticks[-1] if ticks else None


def run_scan(source, cfg: Optional[dict] = None, local_utc_now: Optional[datetime] = None) -> dict:
    cfg = cfg or load_scanner_config()
    tcfg, qcfg = cfg["time"], cfg["quality"]
    out = {"scanner_version": cfg["version"], "data_authority": "terminal_mcp", "data_source_degraded": False,
           "execution_authorized": False, "instruments": [], "ready_setups": [], "no_trade": [], "blocked": []}

    specs = load_specs(cfg)
    first_symbol = next(iter(specs.values())).broker_symbol

    # ---- time authority (probe with the first instrument's freshest tick)
    time_info = source.time_information()
    provisional = derive_time_authority(time_info, None, local_utc_now, tcfg["offset_granularity_minutes"],
                                        tcfg["max_server_clock_staleness_seconds"], tcfg["max_local_clock_skew_seconds"])
    probe_tick = None
    if provisional.gate == TIME_GATE_PASS:
        t = _latest_tick(source, first_symbol, provisional.broker_server_now)
        probe_tick = parse_server_wallclock(str(t["time_ms"])) if t else None
    ta = derive_time_authority(time_info, probe_tick, local_utc_now, tcfg["offset_granularity_minutes"],
                               tcfg["max_server_clock_staleness_seconds"], tcfg["max_local_clock_skew_seconds"])
    out["time"] = ta.as_dict()
    if ta.gate != TIME_GATE_PASS:
        out["scan_timestamp_utc"] = time_info.get("utc_time")
        out["session"] = None
        for canonical in specs:
            out["blocked"].append({"canonical_symbol": canonical, "result": "INSUFFICIENT_DATA", "reason": "TIME_GATE_FAIL"})
        return out

    now = ta.utc_now
    server_now = ta.broker_server_now
    out["scan_timestamp_utc"] = now.isoformat()

    adapter_cfg = cfg["strategy_adapters"]["ST_ASIAN_SWEEP_5R_V1"]
    adapter = AsianSweepAdapter(adapter_cfg["contract"], adapter_cfg["proposal_scope"])
    windows = load_canonical_windows()
    sess = classify(now, windows, adapter.cycles())
    out["session"] = sess.as_dict()
    out["strategies"] = strategy_catalog(cfg)
    scan_allowed = next(s for s in out["strategies"] if s["strategy_id"] == adapter.strategy_id)["opportunity_scan_allowed"]
    struct_cfg = load_market_structure_config()

    try:
        account = source.account_info()
    except Exception as exc:  # sizing degrades to NOT_CALCULATED, scan continues
        account = {"error": type(exc).__name__}
    out["account"] = {k: account.get(k) for k in ("type", "currency", "equity", "error") if k in account}

    for canonical, spec in specs.items():
        item = {"canonical_symbol": canonical, "broker_symbol": spec.broker_symbol, "source": "TERMINAL_MCP"}
        try:
            record = verify_live(spec, source.symbol_info(spec.broker_symbol))
        except InstrumentRegistryError as exc:
            item.update(result="INSUFFICIENT_DATA", reason=str(exc))
            out["instruments"].append(item)
            out["blocked"].append({"canonical_symbol": canonical, "result": item["result"], "reason": item["reason"]})
            continue
        item["instrument"] = record.as_dict()

        quote = assess_quote(record.broker_symbol, _latest_tick(source, record.broker_symbol, server_now), ta, now,
                             record.point, record.pip_size, qcfg["tick_max_age_seconds"])
        item["quote"] = quote.as_dict() if quote else None

        series = {}
        for tf in TIMEFRAMES:
            h = qcfg["history"][tf]
            frm = server_now - timedelta(hours=h["lookback_hours"])
            to = server_now + timedelta(minutes=1)
            fetch = lambda tf=tf, frm=frm, to=to: normalize_bars(source.bars(record.broker_symbol, tf, frm, to), ta)  # noqa: E731
            assess = lambda bars, tf=tf, h=h: assess_series(bars, tf, now, ta, record.daily_break_server, h["min_bars"])  # noqa: E731
            series[tf] = fetch_with_sync(fetch, assess, qcfg.get("sync_retry_delay_seconds", 0.0))
        item["data_quality"] = {tf: s.as_dict() for tf, s in series.items()}

        m15c, h1c, d1c, m5c = (series[t].closed for t in ("M15", "H1", "D1", "M5"))
        today = now.date()
        win = {w.name: w for w in windows}
        levels = {}
        for name, w in win.items():
            s, e = w.bounds(today)
            if e <= now:
                levels[name] = window_levels(m15c, s, e, int((e - s) / timedelta(minutes=15)))
        pdl = previous_day_levels(h1c, today)
        item["session_levels"] = {"asian": levels.get("ASIAN"), "london": levels.get("LONDON"),
                                  "new_york": levels.get("NEW_YORK"), "previous_day": pdl}

        # ---- strategy adapter on the active trade cycle
        res = adapter.evaluate_cycle(sess.active_cycle, canonical, today, m15c, now) if sess.active_cycle else None
        sig = res.signal if res else None
        box = {"high": sig.box_high, "low": sig.box_low, "mid": sig.box_mid} if sig else None
        if box is None and res is not None:
            ref_lv = window_levels(m15c, res.reference_window[0], res.reference_window[1], res.expected_reference_bars)
            box = {"high": ref_lv["high"], "low": ref_lv["low"], "mid": None, "complete": ref_lv["complete"]}
        price = quote.bid if quote else (m15c[-1].close if m15c else None)

        liquidity = []
        if res is not None:
            liquidity = ms.sweep_events(res.post_bars, (box or {}).get("high"), (box or {}).get("low"),
                                        "ASIAN" if res.pair_id == "ASIAN_LONDON" else "LONDON")
        liquidity_contract_gaps = [{"event": "PREVIOUS_DAY_HIGH_SWEEP", "status": ms.CONTRACT_INCOMPLETE},
                                   {"event": "PREVIOUS_DAY_LOW_SWEEP", "status": ms.CONTRACT_INCOMPLETE}]

        item["market_state"] = {
            "D1": ms.d1_state(d1c, price, record.pip_size, pdl) if price is not None else {"status": "INSUFFICIENT"},
            "H1": ms.h1_state(h1c, cfg["market_state"]["h1_ema_period"], struct_cfg.swing_length, struct_cfg.close_break),
            "M15": ms.m15_state(m15c, box, res.post_bars if res else (), struct_cfg.swing_length, struct_cfg.close_break),
            "M5": ms.m5_state(m5c, box, res.trade_window[0] if res else None),
            "liquidity_events": liquidity, "liquidity_contract_gaps": liquidity_contract_gaps,
        }

        last_m15 = series["M15"].quality.last_closed_bar_utc
        entry = signal_entry_status(sig, last_m15)
        post_signal = None
        if sig is not None and sig.status == "SIGNAL" and sig.signal_timestamp is not None:
            after = [b for b in m15c if b.time_utc > sig.signal_timestamp]
            tp1 = sig.box_high if sig.direction == "LONG" else sig.box_low
            hit = (lambda b, lvl: b.high >= lvl) if sig.direction == "LONG" else (lambda b, lvl: b.low <= lvl)
            stop = (lambda b: b.low <= sig.stop_loss) if sig.direction == "LONG" else (lambda b: b.high >= sig.stop_loss)
            post_signal = {"label": ms.DESCRIPTIVE, "closed_m15_bars_since_signal": len(after),
                           "stop_touched": any(stop(b) for b in after), "tp1_touched": any(hit(b, tp1) for b in after)}

        scope = resolve_proposal_scope(adapter.strategy, sess.active_cycle, canonical, adapter.pilots) if sess.active_cycle else None
        spread = spread_gate(quote, record.asset_class, adapter.strategy.risk.max_spread_allowed_pips)
        check = evaluate_checklist(
            time_gate=PASS, series_status={tf: s.quality.status for tf, s in series.items()},
            quote_status=quote.status if quote else None, cycle=sess.active_cycle, strategy_scan_allowed=scan_allowed,
            adapter=res, location_events=liquidity, scope=scope, spread=spread, signal_entry=entry)
        item.update(strategy_id=adapter.strategy_id, strategy_version=adapter.strategy.version,
                    cycle=sess.active_cycle, engine={
                        "status": res.status if res else None, "reason": res.reason if res else None,
                        "regime": sig.regime if sig else None, "setup": sig.setup if sig else None,
                        "direction": sig.direction if sig else None,
                        "reference_bars": f"{res.reference_bars}/{res.expected_reference_bars}" if res else None,
                        "post_session_closed_bars": len(res.post_bars) if res else 0,
                        "signal_timestamp_utc": sig.signal_timestamp.isoformat() if sig and sig.signal_timestamp else None,
                        "signal_entry_open": entry[0], "signal_entry_reason": entry[1],
                        "post_signal_path": post_signal},
                    proposal_scope={"authorized": scope.authorized, "reason": scope.reason,
                                    "risk_per_trade_pct": scope.risk_per_trade_pct} if scope else None,
                    **check)

        if check["result"] == READY:
            freshness = {"quote_age_seconds": quote.age_seconds,
                         "last_closed_m15_utc": series["M15"].quality.last_closed_bar_utc.isoformat()}
            item["proposal"] = build_ticket(signal=sig, strategy=adapter.strategy, record=record, quote=quote,
                                            scope=scope, account=account, session=sess.active_cycle, now_utc=now,
                                            market_context={"h1_ema_bias": item["market_state"]["H1"]["ema_bias"]["state"],
                                                            "session": sess.current_session},
                                            data_freshness=freshness)
            out["ready_setups"].append(item["proposal"])
        elif check["result"] in ("INSUFFICIENT_DATA",):
            out["blocked"].append({"canonical_symbol": canonical, "result": check["result"], "reason": check["reason"]})
        else:
            out["no_trade"].append({"canonical_symbol": canonical, "result": check["result"], "reason": check["reason"]})
        out["instruments"].append(item)

    return out
