"""Read-only MT5 observation path for crypto CFDs, attached to Checklist V1.1.

The registered crypto strategy is explicitly BTCUSDT/ETHUSDT USDT perpetuals. These
scanner instruments are BTCUSD/ETHUSD CFDs. Until a matching CFD strategy contract and
risk authority are registered, this path reports data and structure and fails closed at
location/trigger/risk/proposal.
"""
from __future__ import annotations

from datetime import timedelta

from host_evidence.symbol_metadata import DstHourError
from market_structure import structural_breaks_for_candles
from market_structure.models import STATE_BEARISH, STATE_BULLISH

from .market_state import structure, to_engine_candles
from .quality import assess_series, fetch_with_sync, normalize_bars
from .registry import InstrumentRegistryError, load_specs, verify_live
from .timebase import parse_server_wallclock

TIMEFRAMES = ("D1", "H1", "M15", "M5")


def _symbol_candidates(source, canonical: str) -> list:
    result = source.call("get_marketwatch_symbols", {"symbol": canonical,
        "include_hidden": True, "limit": 100})
    return list(result.get("symbols", []))


def scan_crypto_instruments(source, cfg: dict, ta, now, server_now, source_label: str,
                            struct_cfg) -> tuple[list, dict]:
    items, facts_by_symbol = [], {}
    qcfg = cfg["quality"]
    for canonical, spec in load_specs(cfg, include_crypto=True).items():
        item = {"canonical_symbol": canonical, "broker_symbol": spec.broker_symbol,
                "asset_class": "CRYPTO", "session_policy": "BROKER_DEFINED / 24H_OBSERVATION",
                "source": source_label}
        facts_by_symbol[canonical] = None
        try:
            candidates = _symbol_candidates(source, canonical)
            item["broker_symbol_candidates"] = sorted({x.get("symbol") for x in candidates if x.get("symbol")})
            info = source.symbol_info(spec.broker_symbol)
            if info is None:
                item["symbol_authority"] = "AMBIGUOUS"
                raise InstrumentRegistryError(f"FAIL_CLOSED: no unique {canonical} broker symbol")
            candidate_names = item["broker_symbol_candidates"]
            if len(candidate_names) > 1:
                item["symbol_authority"] = "AMBIGUOUS"
                raise InstrumentRegistryError(f"FAIL_CLOSED: multiple {canonical} broker aliases")
            item["symbol_authority"] = "VERIFIED"
            record = verify_live(spec, info, price_source=source_label)
            item["instrument"] = record.as_dict()

            ticks = source.ticks(record.broker_symbol, server_now - timedelta(minutes=5),
                                 server_now + timedelta(minutes=1))
            tick = ticks[-1] if ticks else None
            tick_time = None
            if tick:
                try:
                    tick_time = ta.server_to_utc(parse_server_wallclock(str(tick["time_ms"])))
                except DstHourError:  # repeated/skipped server hour: treat as no quote
                    tick = None
            if tick:
                bid, ask = float(tick["bid"]), float(tick["ask"])
                spread = ask - bid
                tick_age = (now - tick_time).total_seconds()
                quote = {"bid": bid, "ask": ask, "spread_points": int(round(spread / record.point)),
                         "spread_price": spread, "spread_pct": spread / bid * 100 if bid else None,
                         "timestamp": tick_time.isoformat(), "age_seconds": tick_age,
                         "status": "FRESH" if -5 <= tick_age <= qcfg["tick_max_age_seconds"] else "STALE"}
            else:
                bid = None
                quote = {"bid": None, "ask": None, "spread_points": None, "spread_price": None,
                         "spread_pct": None, "timestamp": None, "age_seconds": None, "status": "MISSING"}
            item["quote"] = quote

            synced_by_tf, closed_by_tf = {}, {}
            for tf in TIMEFRAMES:
                h = qcfg["history"][tf]
                frm, to = server_now - timedelta(hours=h["lookback_hours"]), server_now + timedelta(minutes=1)
                fetch = lambda tf=tf, frm=frm, to=to: normalize_bars(source.bars(record.broker_symbol, tf, frm, to), ta)
                assess = lambda bars, tf=tf, h=h: assess_series(bars, tf, now, ta,
                                                                  spec.daily_break_server, h["min_bars"])
                synced = fetch_with_sync(fetch, assess, qcfg.get("sync_retry_delay_seconds", 0.0))
                synced_by_tf[tf] = synced.as_dict()
                closed_by_tf[tf] = synced.closed
            item["data_quality"] = synced_by_tf
            quality_pass = quote["status"] == "FRESH" and all(
                synced_by_tf[tf]["status"] == "VALID" for tf in TIMEFRAMES)
            item["data_quality_gate"] = "PASS" if quality_pass else "FAIL"

            if quality_pass:
                price = bid if bid is not None else closed_by_tf["M5"][-1].close
                states = {tf: structure(closed_by_tf[tf], struct_cfg.swing_length, struct_cfg.close_break)
                          for tf in TIMEFRAMES}
                item["market_state"] = {tf: {"status": "VALID", "structure": states[tf],
                    "last_closed_bar_utc": synced_by_tf[tf]["last_closed_bar_utc"]} for tf in TIMEFRAMES}
                d1_bars, h1_bars = to_engine_candles(closed_by_tf["D1"]), to_engine_candles(closed_by_tf["H1"])
                d1_events = structural_breaks_for_candles(d1_bars, struct_cfg)
                d1_direction = (STATE_BULLISH if d1_events and "BULLISH" in
                                max(d1_events, key=lambda event: event.time_utc).kind.value else
                                STATE_BEARISH if d1_events else "UNRESOLVED")
                h1_events = structural_breaks_for_candles(h1_bars, struct_cfg)
                h1_direction = (STATE_BULLISH if h1_events and "BULLISH" in
                                max(h1_events, key=lambda event: event.time_utc).kind.value else
                                STATE_BEARISH if h1_events else "UNRESOLVED")
                item["market_state"].update({"D1": {**item["market_state"]["D1"], "last_closed_direction": d1_direction,
                                                        "last_closed_close": d1_bars[-1].close,
                                                        "price_vs_last_closed_range":
                                                        "ABOVE" if price > d1_bars[-1].high else
                                                        "BELOW" if price < d1_bars[-1].low else "INSIDE"},
                                             "H1": {**item["market_state"]["H1"], "trend_direction": h1_direction,
                                                        "structure": {**states["H1"], "state": h1_direction}}})
                facts_by_symbol[canonical] = {
                    "data_gate": "PASS", "series_gates": {tf: synced_by_tf[tf]["status"] for tf in TIMEFRAMES},
                    "d1_structure": {**states["D1"], "state": d1_direction},
                    "h1_trend_direction": h1_direction,
                    "strategy_id": None, "strategy_version": None,
                    "contract_gap": "No registered scanner strategy authorizes BTCUSD/ETHUSD CFDs; "
                                    "ST_LIQUIDITY_SWEEP_RETEST_V1 covers BTCUSDT/ETHUSDT perpetuals.",
                    "spread": {"status": "OBSERVED_ONLY", **quote},
                    "risk_policy": "RISK_POLICY_AMBIGUOUS", "position_size": "NOT_CALCULATED"}
                item["strategy_id"] = None
                item["strategy_version"] = None
                item["setup_valid"] = False
                item["proposal_eligible"] = False
                item["execution_authorized"] = False
                item["result"] = "STRATEGY_CONTRACT_INCOMPLETE"
                item["reason_codes"] = ["STRATEGY_CONTRACT_INCOMPLETE", "RISK_POLICY_AMBIGUOUS",
                                         "SPREAD_POLICY_UNDEFINED"]
            else:
                item["result"] = "INSUFFICIENT_DATA"
                item["reason_codes"] = ["DATA_QUALITY_GATE_FAIL"]
            item["execution_authorized"] = False
        except Exception as exc:
            item["result"] = "INSUFFICIENT_DATA"
            item["reason_codes"] = ["DATA_QUALITY_GATE_FAIL"]
            item["error_type"] = type(exc).__name__
            if item.get("symbol_authority") == "AMBIGUOUS":
                item["result"] = "BLOCKED_SYMBOL_AUTHORITY"
            item["data_quality_gate"] = "FAIL"
        items.append(item)
    return items, facts_by_symbol
