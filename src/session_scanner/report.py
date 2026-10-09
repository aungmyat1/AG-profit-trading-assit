"""Owner-facing text rendering of a scan result. Formatting only -- it reads the
deterministic scan dict and never changes a result."""
from __future__ import annotations


def _fmt(v, nd=5):
    return "n/a" if v is None else (f"{v:.{nd}f}" if isinstance(v, float) else str(v))


def render_text(scan: dict) -> str:
    t = scan.get("time", {})
    s = scan.get("session") or {}
    lines = ["FX SESSION SCAN (READ-ONLY -- no orders)",
             f"SOURCE: primary={scan.get('primary_source', scan.get('source'))} actual={scan.get('actual_source', scan.get('source'))} "
             f"degraded={scan.get('data_source_degraded')} gate={scan.get('data_quality_gate')} "
             f"fallback={scan.get('fallback_reason')}",
             f"UTC: {scan.get('scan_timestamp_utc')}   broker: {t.get('broker_time')} ({t.get('broker_utc_offset')}, "
             f"{t.get('offset_confidence')})",
             f"SESSION: {s.get('current_session')}  cycle: {s.get('active_cycle') or 'NONE'}  "
             f"closes in {s.get('minutes_to_close')} min  next: {s.get('next_session')}", ""]
    for it in scan.get("instruments", []):
        rec = it.get("instrument") or {}
        nd = rec.get("digits", 5)
        lines.append(f"{it['broker_symbol']}  ({it['canonical_symbol']})")
        if "market_state" not in it:
            lines += [f"  Result: {it.get('result')}  ({it.get('reason')})", ""]
            continue
        q = it.get("quote") or {}
        lv = it.get("session_levels", {})
        a, ldn, pd = lv.get("asian") or {}, lv.get("london") or {}, lv.get("previous_day") or {}
        h1 = it["market_state"]["H1"]
        dq = " ".join(f"{tf}={d['status']}" + ("*" if d["retry_performed"] else "") for tf, d in it["data_quality"].items())
        lines += [
            f"  Quote: {_fmt(q.get('bid'), nd)}/{_fmt(q.get('ask'), nd)}  spread {q.get('spread_points')} pts "
            f"({_fmt(q.get('spread_pips'), 2)} pips)  [{q.get('status')}]",
            f"  Data: {dq}",
            f"  H1: structure {h1['structure'].get('state')}, {h1['ema_bias']['indicator']} {h1['ema_bias']['state']}",
            f"  Asian H/L: {_fmt(a.get('high'), nd)}/{_fmt(a.get('low'), nd)}   London H/L: "
            f"{_fmt(ldn.get('high'), nd)}/{_fmt(ldn.get('low'), nd)}   PDH/PDL: {_fmt(pd.get('high'), nd)}/{_fmt(pd.get('low'), nd)}",
            f"  Liquidity: {', '.join(e['event'] for e in it['market_state']['liquidity_events']) or 'no reference sweep'}",
            f"  Engine: {it['engine']['status']} ({it['engine']['reason']}), regime {it['engine']['regime']}"
            + (f", signal bar {it['engine']['signal_timestamp_utc']}, entry "
               f"{'OPEN' if it['engine']['signal_entry_open'] else it['engine']['signal_entry_reason']}"
               if it['engine'].get('signal_timestamp_utc') else ""),
            "  Checklist: " + " ".join(f"{k}={v}" for k, v in it["checklist"].items()),
            f"  Result: {it['result']}  ({it['reason']})"]
        ck11 = it.get("checklist_v1_1")
        if ck11:
            ph = " ".join(f"{k}={v['status']}" for k, v in ck11["phases"].items())
            lines += [f"  ChecklistV1.1: {ph}",
                      f"  V1.1: {ck11['result']}  (setup_valid={ck11['setup_valid']}  "
                      f"proposal_eligible={ck11['proposal_eligible']}  execution_authorized=False)"]
        lines += [""]
    lines += [f"READY SETUPS: {len(scan.get('ready_setups', []))}",
              f"NO_TRADE: {len(scan.get('no_trade', []))}",
              f"BLOCKED_DATA: {len(scan.get('blocked', []))}"]
    for p in scan.get("ready_setups", []):
        lines += ["", f"PROPOSAL {p['ticket_id']} (execution_authorized=False)",
                  f"  {p['direction']} {p['broker_symbol']} {p['entry_type']} @ {p['entry_price']}  SL {p['stop_loss']}  "
                  f"TP1 {p['take_profit_1']} ({p['rr_tp1']}R)  TP2 {p['take_profit_2']} ({p['rr_tp2']}R)",
                  f"  risk {p['risk_pct']}%  size {p['position_size']} {p['position_size_note'] or ''}"]
    return "\n".join(lines)
