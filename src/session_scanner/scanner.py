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
from .checklist_v1_1 import attach_checklist_v1_1
from .proposal import build_ticket
from .quality import FRESH, assess_quote, assess_series, fetch_with_sync, normalize_bars
from .registry import InstrumentRegistryError, load_specs, verify_live
from .sessions import classify, load_canonical_windows, previous_day_levels, window_levels
from .strategy_adapter import AsianSweepAdapter, resolve_proposal_scope, strategy_catalog
from .timebase import TIME_GATE_PASS, derive_time_authority, parse_server_wallclock

SCANNER_CONFIG_PATH = "config/session_scanner_v1.yaml"
TIMEFRAMES = ("D1", "H1", "M15", "M5")
RECONCILIATION_TIMESTAMP_TOLERANCE_SECONDS = 60


def _source_name(source) -> str:
    return str(getattr(source, "source_name", "TERMINAL_MCP"))


def load_scanner_config(path: str = SCANNER_CONFIG_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _latest_tick(source, broker_symbol: str, server_now: datetime) -> Optional[dict]:
    ticks = source.ticks(broker_symbol, server_now - timedelta(minutes=5), server_now + timedelta(minutes=1))
    return ticks[-1] if ticks else None


def _aggregate_data_quality_gate(time_authority: dict, instruments: list, mandatory_instrument_count: int) -> str:
    """Aggregate only final mandatory instrument gates and the final time gate.

    ``TimeAuthority.as_dict()`` exposes ``time_gate``; accepting only that canonical
    field prevents a diagnostic/legacy key from silently turning a valid scan into FAIL.
    Missing instruments remain fail-closed.
    """
    if time_authority.get("time_gate") != TIME_GATE_PASS:
        return "FAIL"
    if len(instruments) != mandatory_instrument_count:
        return "FAIL"
    return "PASS" if all(item.get("data_quality_gate") == "PASS" for item in instruments) else "FAIL"


def _run_source_scan(source, cfg: Optional[dict] = None, local_utc_now: Optional[datetime] = None,
                     source_label: Optional[str] = None) -> dict:
    cfg = cfg or load_scanner_config()
    source_label = source_label or _source_name(source)
    tcfg, qcfg = cfg["time"], cfg["quality"]
    out = {"scanner_version": cfg["version"], "data_authority": source_label.lower(), "source": source_label,
           "data_source_degraded": False, "data_quality_gate": "FAIL",
           "execution_authorized": False, "instruments": [], "ready_setups": [], "no_trade": [], "blocked": []}

    all_specs = load_specs(cfg)
    crypto_cfg = {**cfg, "instruments": {k: v for k, v in cfg["instruments"].items()
                                          if v.get("asset_class") == "CRYPTO"}}
    crypto_specs = load_specs(crypto_cfg, include_crypto=True) if crypto_cfg["instruments"] else {}
    # Frozen Scanner V1 evaluates only its original four FX/metal instruments. Crypto
    # is evaluated additively by Checklist V1.1 below, with its own registered adapter.
    v1_specs = all_specs
    first_symbol = next(iter(v1_specs.values())).broker_symbol

    # ---- time authority (probe with the first instrument's freshest tick)
    time_info = source.time_information()
    out["source_timestamp"] = time_info.get("utc_time")
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
        for canonical in v1_specs:
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

    facts_by_symbol = {}  # Checklist V1.1 fact bundles (JSON-safe; V1 outputs untouched)
    for canonical, spec in v1_specs.items():
        item = {"canonical_symbol": canonical, "broker_symbol": spec.broker_symbol, "asset_class": spec.asset_class,
                "source": source_label}
        try:
            record = verify_live(spec, source.symbol_info(spec.broker_symbol), price_source=source_label)
        except InstrumentRegistryError as exc:
            item.update(result="INSUFFICIENT_DATA", reason=str(exc))
            out["instruments"].append(item)
            out["blocked"].append({"canonical_symbol": canonical, "result": item["result"], "reason": item["reason"]})
            facts_by_symbol[canonical] = None
            continue
        item["instrument"] = record.as_dict()

        quote = assess_quote(record.broker_symbol, _latest_tick(source, record.broker_symbol, server_now), ta, now,
                             record.point, record.pip_size, qcfg["tick_max_age_seconds"],
                             source=f"{source_label}.get_chart_ticks_history")
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
        item["data_quality_gate"] = ("PASS" if quote is not None and quote.status == FRESH
                                      and all(s.quality.status == "VALID" for s in series.values()) else "FAIL")

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
        if scope is not None and not scope.authorized and scope.reason.startswith("RISK_POLICY_AMBIGUOUS"):
            check = dict(check)
            check["reason"] = "RISK_POLICY_AMBIGUOUS"
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
                    risk_policy=("RISK_POLICY_AMBIGUOUS" if scope is not None and not scope.authorized else
                                 ("PILOT_SCOPE" if scope is not None else None)),
                    position_size=("NOT_CALCULATED" if scope is not None and not scope.authorized else None),
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

        # Checklist V1.1 fact bundle (captured only; the V1 item above is unchanged).
        facts_by_symbol[canonical] = {
            "scan_allowed": scan_allowed,
            "strategy_id": adapter.strategy_id,
            "strategy_version": adapter.strategy.version,
            "strategy_timeframe": adapter.strategy.timeframe,
            "adapter_status": res.status if res else None,
            "adapter_reason": res.reason if res else None,
            "reference_bars": res.reference_bars if res else None,
            "expected_reference_bars": res.expected_reference_bars if res else None,
            "signal": {"status": sig.status, "regime": sig.regime, "setup": sig.setup,
                       "direction": sig.direction, "reason_code": sig.reason_code,
                       "entry": sig.entry, "stop_loss": sig.stop_loss, "risk_distance": sig.risk_distance,
                       "box_high": sig.box_high, "box_low": sig.box_low, "box_mid": sig.box_mid,
                       "strategy_id": sig.strategy_id, "strategy_version": sig.strategy_version,
                       "signal_timestamp_utc": sig.signal_timestamp.isoformat() if sig.signal_timestamp else None}
            if sig is not None else None,
            "scope": {"authorized": scope.authorized, "reason": scope.reason,
                      "risk_per_trade_pct": scope.risk_per_trade_pct, "pilot_id": scope.pilot_id}
            if scope is not None else None,
            "spread": spread,
            "last_closed_m15_utc": (series["M15"].quality.last_closed_bar_utc.isoformat()
                                    if series["M15"].quality.last_closed_bar_utc else None),
            "d1_structure": ms.structure(d1c, struct_cfg.swing_length, struct_cfg.close_break),
            "contract_targets": {"total_target_r": adapter.strategy.total_target_r,
                                 "legs": [{"leg_id": leg.leg_id, "volume_pct": leg.volume_pct,
                                           "target_type": leg.target_type,
                                           "fixed_r_multiple": leg.fixed_r_multiple}
                                          for leg in adapter.strategy.legs],
                                 "time_invalidation": adapter.strategy.time_invalidation,
                                 "structural_invalidation": adapter.strategy.structural_invalidation},
            "account": {"equity": account.get("equity"), "currency": account.get("currency")},
        }
        out["instruments"].append(item)

    out["data_quality_gate"] = _aggregate_data_quality_gate(
        out.get("time", {}), out["instruments"], len(v1_specs)
    )
    # Source doubles from frozen four-symbol regressions explicitly contain their
    # configured FX universe and no listing API. Only add configured crypto when the
    # source implements the existing read-only Terminal listing call.
    if crypto_specs and callable(getattr(source, "call", None)):
        from .crypto_adapter import scan_crypto_instruments
        crypto_items, crypto_facts = scan_crypto_instruments(source, crypto_cfg, ta, now, server_now,
                                                              source_label, struct_cfg)
        out["instruments"].extend(crypto_items)
        facts_by_symbol.update(crypto_facts)
    return attach_checklist_v1_1(out, facts_by_symbol)



def _source_failure(cfg: dict, source_label: str, exc: Exception) -> dict:
    """Return a safe failed candidate; never expose transport details or credentials."""
    return {
        "scanner_version": cfg["version"], "data_authority": source_label.lower(), "source": source_label,
        "data_source_degraded": False, "data_quality_gate": "FAIL", "source_timestamp": None,
        "scan_timestamp_utc": None, "session": None, "instruments": [], "ready_setups": [],
        "no_trade": [],
        "blocked": [{"canonical_symbol": symbol, "result": "INSUFFICIENT_DATA",
                     "reason": f"DATA_QUALITY_GATE_FAIL:{type(exc).__name__}"}
                    for symbol in cfg.get("instruments", {})],
        "source_error": f"{type(exc).__name__}", "execution_authorized": False,
    }


def _candidate_quality_pass(candidate: dict, expected_symbols: int) -> bool:
    return (candidate.get("data_quality_gate") == "PASS"
            and len(candidate.get("instruments", [])) == expected_symbols
            and not candidate.get("source_error"))


def _index_instruments(candidate: dict) -> dict:
    return {i.get("canonical_symbol"): i for i in candidate.get("instruments", [])}


def _reconcile_sources(primary: dict, secondary: Optional[dict], cfg: dict) -> list:
    if secondary is None:
        return []
    pidx, sidx = _index_instruments(primary), _index_instruments(secondary)
    rows = []
    for canonical in sorted(set(pidx) | set(sidx)):
        p, s = pidx.get(canonical), sidx.get(canonical)
        if primary.get("data_quality_gate", "PASS") != "PASS" or secondary.get("data_quality_gate", "PASS") != "PASS":
            rows.append({"canonical_symbol": canonical, "status": "SOURCE_STALE",
                         "reason": "SOURCE_DATA_QUALITY_GATE_FAIL"})
            continue
        if p is None or s is None:
            rows.append({"canonical_symbol": canonical, "status": "SOURCE_MISMATCH",
                         "reason": "SYMBOL_MISSING_FROM_SOURCE"})
            continue
        if p.get("data_quality_gate") != "PASS" or s.get("data_quality_gate") != "PASS":
            rows.append({"canonical_symbol": canonical, "status": "SOURCE_STALE",
                         "reason": "SOURCE_DATA_QUALITY_GATE_FAIL"})
            continue
        pi, si = p.get("instrument") or {}, s.get("instrument") or {}
        pq, sq = p.get("quote") or {}, s.get("quote") or {}
        pquality, squality = p.get("data_quality", {}).get("M15", {}), s.get("data_quality", {}).get("M15", {})
        fields = {
            "primary_symbol": pi.get("broker_symbol", p.get("broker_symbol")),
            "secondary_symbol": si.get("broker_symbol", s.get("broker_symbol")),
            "primary_timeframe": pquality.get("timeframe"), "secondary_timeframe": squality.get("timeframe"),
            "primary_latest_closed_bar": pquality.get("last_closed_bar_utc"),
            "secondary_latest_closed_bar": squality.get("last_closed_bar_utc"),
            "primary_bid": pq.get("bid"), "secondary_bid": sq.get("bid"),
            "primary_ask": pq.get("ask"), "secondary_ask": sq.get("ask"),
            "primary_timestamp": pq.get("timestamp_utc"), "secondary_timestamp": sq.get("timestamp_utc"),
        }
        if fields["primary_symbol"] != fields["secondary_symbol"]:
            status = "SYMBOL_ALIAS_DIFFERENCE"
            reason = "BROKER_SYMBOL_ALIAS"
        elif fields["primary_timeframe"] != fields["secondary_timeframe"]:
            status, reason = "SOURCE_MISMATCH", "TIMEFRAME_MISMATCH"
        elif fields["primary_latest_closed_bar"] != fields["secondary_latest_closed_bar"]:
            try:
                from datetime import datetime as _dt
                a = _dt.fromisoformat(fields["primary_latest_closed_bar"])
                b = _dt.fromisoformat(fields["secondary_latest_closed_bar"])
                delta = abs((a - b).total_seconds())
            except Exception:
                delta = float("inf")
            status = ("MINOR_TIMESTAMP_DIFFERENCE" if delta <= RECONCILIATION_TIMESTAMP_TOLERANCE_SECONDS
                      else "SOURCE_MISMATCH")
            reason = "LATEST_CLOSED_BAR_TIMESTAMP_DIFFERENCE"
        elif any(fields[a] != fields[b] for a, b in (("primary_bid", "secondary_bid"), ("primary_ask", "secondary_ask"))):
            status, reason = "SOURCE_MISMATCH", "QUOTE_DIFFERENCE"
        elif fields["primary_timestamp"] != fields["secondary_timestamp"]:
            try:
                from datetime import datetime as _dt
                delta = abs((_dt.fromisoformat(fields["primary_timestamp"])
                             - _dt.fromisoformat(fields["secondary_timestamp"])).total_seconds())
            except Exception:
                delta = float("inf")
            status = ("MINOR_TIMESTAMP_DIFFERENCE" if delta <= RECONCILIATION_TIMESTAMP_TOLERANCE_SECONDS
                      else "SOURCE_MISMATCH")
            reason = "QUOTE_TIMESTAMP_DIFFERENCE"
        else:
            status, reason = "SOURCE_MATCH", "ALL_RECONCILED_FIELDS_MATCH"
        rows.append({"canonical_symbol": canonical, "status": status, "reason": reason, **fields})
    return rows


def run_scan(source, cfg: Optional[dict] = None, local_utc_now: Optional[datetime] = None,
             secondary_source=None) -> dict:
    """Run atomic primary/secondary source selection without mixing source data."""
    cfg = cfg or load_scanner_config()
    primary_label = _source_name(source)
    try:
        primary = _run_source_scan(source, cfg, local_utc_now, primary_label)
    except Exception as exc:
        primary = _source_failure(cfg, primary_label, exc)
    secondary = None
    if secondary_source is not None:
        secondary_label = _source_name(secondary_source)
        try:
            secondary = _run_source_scan(secondary_source, cfg, local_utc_now, secondary_label)
        except Exception as exc:
            secondary = _source_failure(cfg, secondary_label, exc)
    expected = len(cfg.get("instruments", {}))
    primary_ok = _candidate_quality_pass(primary, expected)
    secondary_ok = secondary is not None and _candidate_quality_pass(secondary, expected)
    if primary_ok:
        selected, actual, fallback_reason, degraded = primary, primary_label, "PRIMARY_QUALITY_GATE_PASS", False
    elif secondary_ok:
        selected, actual, fallback_reason, degraded = secondary, _source_name(secondary_source), "PRIMARY_QUALITY_GATE_FAIL", True
    else:
        selected, actual, fallback_reason, degraded = primary, primary_label, (
            "PRIMARY_AND_SECONDARY_QUALITY_GATE_FAIL" if secondary is not None else "SECONDARY_NOT_CONFIGURED"), False
    selected = dict(selected)
    selected.update(primary_source=primary_label, actual_source=actual, fallback_reason=fallback_reason,
                   data_source_degraded=degraded,
                   source_timestamp=selected.get("source_timestamp") or selected.get("scan_timestamp_utc"),
                   source_reconciliation=_reconcile_sources(primary, secondary, cfg))
    return selected
