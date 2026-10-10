"""Manual Trade Ticket V1 Phase 8: daily report, and a static proof that no broker-mutation
call is reachable from the scheduler -> ticket -> report path (owner decision C2)."""
from __future__ import annotations

import ast
import datetime as dt
from pathlib import Path

from v1_tickets import manual_ticket as mt
from v1_tickets.manual_report import build_report, previous_trading_day, render_report
from v1_tickets.outcome import resolve_day
from v1_tickets.owner_decision import ManualTicketDecision, record_decision
from v1_tickets.scan_record import read_jsonl

from test_host_go_live_kit import smoke  # noqa: E402  (adds scripts/host to sys.path)
from test_manual_ticket_build import manual
from test_manual_ticket_logic_gate import CANDLES

ROOT = Path(__file__).resolve().parent.parent
UTC = dt.timezone.utc


def test_daily_report_sections(tmp_path):
    journal = str(tmp_path / "j")
    # Yesterday (2026-06-23, Tuesday): one shadow ticket, skipped by the owner, then resolved.
    t = manual("2026-06-23", "07:20")
    mt.archive_manual_ticket(journal, t)
    stored = read_jsonl(mt.ticket_path(journal, dt.date(2026, 6, 23)))[-1]
    record_decision(journal, stored, ManualTicketDecision(ticket_id=t["ticket_id"], decision="SKIPPED",
                                                          recorded_at="2026-06-23T08:00:00+00:00", skip_reason="NEWS"))
    resolve_day(journal, dt.date(2026, 6, 23), lambda s: CANDLES, now=dt.datetime(2026, 6, 24, 6, tzinfo=UTC),
                tf=dt.timedelta(minutes=15))
    # Today: one scheduled run with no data for any symbol.
    now = dt.datetime(2026, 6, 24, 8, 0, tzinfo=UTC)
    smoke.run_fx(lambda *a: [], now, journal, gated=True, notify=False)
    rep = build_report(journal, now.date(), now=dt.datetime(2026, 6, 24, 15, 30, tzinfo=UTC),
                       expected=smoke.manual_expected())
    assert rep["EDGE_VERIFIED"] is False and rep["orders_sent_by_system"] == 0
    assert rep["system_health"]["scheduled_runs"] == 1 and rep["system_health"]["missing_records"] == []
    assert {"strategy": "ST_ASIAN_SWEEP_5R_V1@1.1.1", "session": "LONDON_NEWYORK"} in \
        rep["system_health"]["sessions_without_any_run"]                    # never ran today -> visible
    st = {(s["strategy"], s["symbol"]): s for s in rep["session_states"]}
    assert st[("SESSION_TRADE_V1@1", "EURUSD-VIP")]["reason"] == "STRATEGY_ADAPTER_NOT_IMPLEMENTED"
    assert st[("ST_ASIAN_SWEEP_5R_V1@1.1.1", "EURUSD")]["state"] == "TICKET_BLOCKED"
    y = rep["yesterday_outcomes"]
    assert y["session_date"] == "2026-06-23" and y["tag"] == "VIRTUAL_FORWARD"
    assert y["not_taken"]["count"] == 1 and y["taken"]["count"] == 0
    text = render_report(rep)
    for line in ("SYSTEM HEALTH:", "SESSIONS:", "TICKETS ISSUED:", "OWNER DECISIONS:", "YESTERDAY (2026-06-23)",
                 "EDGE_VERIFIED FALSE", "Orders sent by system: 0"):
        assert line in text
    assert "London 08:00" in text or "London 07:00" in text                 # local time is display only


def test_previous_trading_day_skips_weekend():
    assert previous_trading_day(dt.date(2026, 10, 5)) == dt.date(2026, 10, 2)


def test_host_report_runs_once_after_last_window(tmp_path):
    journal = str(tmp_path / "j")
    before = dt.datetime(2026, 6, 24, 15, 29, tzinfo=UTC)
    assert not any(ln.startswith("MANUAL_REPORT") for ln in smoke.run_manual_jobs(lambda *a: [], before, journal))
    after = dt.datetime(2026, 6, 24, 15, 30, tzinfo=UTC)
    assert any(ln.startswith("MANUAL_REPORT") for ln in smoke.run_manual_jobs(lambda *a: [], after, journal))
    assert not any(ln.startswith("MANUAL_REPORT") for ln in smoke.run_manual_jobs(lambda *a: [], after, journal))


# --------------------------------------------------------------------------- static boundary

ENTRY_POINTS = [ROOT / "scripts/host/live_candles_smoke.py", ROOT / "scripts/run_fx_cycle_once.py",
                ROOT / "scripts/manual_ticket_decision.py", ROOT / "scripts/run_manual_ticket_report.py"]
SEARCH = [ROOT / "src", ROOT / "scripts/host", ROOT / "scripts"]
FORBIDDEN_CALLS = {"order_send", "order_check", "order_modify", "order_cancel", "positions_get", "orders_get",
                   "position_close", "position_modify", "Close", "Buy", "Sell"}
FORBIDDEN_MODULES = ("execution", "trade_management", "mt5.management_gateway")   # packages, matched exactly


def _module_file(name: str):
    parts = name.split(".")
    for base in SEARCH:
        for cand in (base.joinpath(*parts).with_suffix(".py"), base.joinpath(*parts, "__init__.py")):
            if cand.is_file():
                return cand
    return None


def _reachable():
    seen, todo = set(), list(ENTRY_POINTS)
    while todo:
        path = todo.pop()
        if path in seen:
            continue
        seen.add(path)
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level:
                pkg = path.parent
                for _ in range(node.level - 1):
                    pkg = pkg.parent
                rel = [str(pkg.relative_to(next(b for b in SEARCH if pkg.is_relative_to(b))).as_posix()).replace("/", ".")]
                base = ".".join(p for p in rel + ([node.module] if node.module else []) if p and p != ".")
                names = [base] + [f"{base}.{a.name}" for a in node.names]
            for n in names:
                assert not any(n == m or n.startswith(m + ".") for m in FORBIDDEN_MODULES), f"{path} imports {n}"
                f = _module_file(n)
                if f is not None:
                    todo.append(f)
    return seen


def test_no_broker_mutation_reachable_from_scheduler_ticket_report_path():
    files = _reachable()
    assert ROOT / "src/v1_tickets/manual_ticket.py" in files and ROOT / "src/v1_tickets/manual_report.py" in files
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
                assert name not in FORBIDDEN_CALLS, f"{path}:{node.lineno} calls {name}"
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert "TRADE_ACTION_" not in node.value, f"{path}:{node.lineno}"
            if isinstance(node, ast.Attribute):
                assert not node.attr.startswith("TRADE_ACTION_"), f"{path}:{node.lineno}"


def test_no_order_send_call_site_anywhere_in_repo():
    hits = []
    for base in (ROOT / "src", ROOT / "scripts"):
        for path in base.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and \
                        node.func.attr in ("order_send", "order_check"):
                    hits.append(f"{path}:{node.lineno}")
    assert hits == []


def test_report_counts_data_error_separately_and_not_run(tmp_path):
    journal = str(tmp_path / "j")
    now = dt.datetime(2026, 6, 24, 8, 0, tzinfo=UTC)

    def broken(*a):
        raise RuntimeError("copy_rates failed")
    smoke.run_fx(broken, now, journal, gated=True, notify=False)          # ASIAN_LONDON only (gated)
    rep = build_report(journal, now.date(), now=dt.datetime(2026, 6, 24, 15, 30, tzinfo=UTC),
                       expected=smoke.manual_expected())
    counts = rep["state_counts"]
    assert counts["DATA_ERROR"] == len(smoke.fx_symbols())
    st = {(s["strategy"], s["session"], s["symbol"]): s for s in rep["session_states"]}
    eur = st[("ST_ASIAN_SWEEP_5R_V1@1.1.1", "ASIAN_LONDON", "EURUSD")]
    assert eur["state"] == "TICKET_BLOCKED" and eur["stage"] == "DATA" and eur["reason"].startswith("DATA_ERROR:")
    assert counts["NOT_RUN"] >= len(smoke.fx_symbols())                    # LONDON_NEWYORK never ran
    assert counts["NO_SETUP"] == 0 and "DATA_ERROR " + str(counts["DATA_ERROR"]) in render_report(rep)


def _run_report_cli(tmp_path, *extra):
    import subprocess
    import sys
    journal = tmp_path / "j"
    journal.mkdir()
    import os

    import MetaTrader5
    env = dict(os.environ)
    origin = getattr(MetaTrader5, "__file__", None)
    if origin is None or Path(origin).resolve().parent == ROOT:
        # This process uses a placeholder (repo-root MetaTrader5.py, import-only, raises on use);
        # give the subprocess the same one. A real installed package is never shadowed.
        env["PYTHONPATH"] = os.pathsep.join(p for p in (str(ROOT), env.get("PYTHONPATH")) if p)
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "run_manual_ticket_report.py"), "--date",
                           "2026-06-24", "--journal", str(journal), *extra],
                          capture_output=True, text=True, encoding="utf-8", timeout=120, check=True, env=env)


def test_report_cli_json_stdout_is_exactly_one_json_document(tmp_path):
    """I6: import banners/diagnostics must not reach stdout in --json mode."""
    import json
    proc = _run_report_cli(tmp_path, "--json")
    rep = json.loads(proc.stdout)
    assert rep["report"] == "manual_ticket_daily" and rep["EDGE_VERIFIED"] is False
    assert "archived:" in proc.stderr


def test_report_cli_human_mode_still_renders_report(tmp_path):
    proc = _run_report_cli(tmp_path)
    assert proc.stdout.startswith("AG MANUAL TICKET DAILY REPORT — 2026-06-24")
    assert "EDGE_VERIFIED FALSE" in proc.stdout and "smart-money-concepts" not in proc.stdout
