from types import SimpleNamespace


from research.harness.fills import delay_entry, resolve_exit
from research.harness.tests.fixtures import bars

O = 1.1000


def _b(rows):
    return bars(n=len(rows), rows=rows)


def test_same_bar_stop_and_target_takes_stop_long():
    b = _b([(O, O + 0.0005, O - 0.0005, O), (O, O + 0.0030, O - 0.0030, O)])
    r = resolve_exit(b, 0, "LONG", stop=O - 0.0010, target=O + 0.0020)
    assert r["exit_reason"] == "STOP" and r["exit_idx"] == 1 and r["same_bar_conflict"]
    assert r["exit_price"] == O - 0.0010


def test_same_bar_stop_and_target_takes_stop_short():
    b = _b([(O, O + 0.0030, O - 0.0030, O)])
    r = resolve_exit(b, 0, "SHORT", stop=O + 0.0010, target=O - 0.0020)
    assert r["exit_reason"] == "STOP" and r["same_bar_conflict"]


def test_target_only_and_gap_through_stop():
    b = _b([(O, O + 0.0025, O - 0.0002, O)])
    assert resolve_exit(b, 0, "LONG", O - 0.0010, O + 0.0020)["exit_reason"] == "TARGET"
    g = _b([(O, O + 0.0002, O - 0.0002, O), (O - 0.0020, O - 0.0015, O - 0.0025, O - 0.0020)])
    r = resolve_exit(g, 0, "LONG", O - 0.0010, O + 0.0020)
    assert r["exit_reason"] == "STOP" and r["exit_price"] == O - 0.0020  # filled at gap open


def test_no_touch_ends_at_data_or_time():
    b = _b([(O, O + 0.0002, O - 0.0002, O + 0.0001)] * 3)
    assert resolve_exit(b, 0, "LONG", O - 0.001, O + 0.002)["exit_reason"] == "END_OF_DATA"
    assert resolve_exit(b, 0, "LONG", O - 0.001, O + 0.002, max_bars=2)["exit_idx"] == 1


def test_delay_entry_refills_at_later_open_and_skips_invalid():
    rows = [(O, O + 0.0002, O - 0.0002, O), (O + 0.0005, O + 0.0006, O + 0.0004, O + 0.0005),
            (O + 0.0025, O + 0.0026, O + 0.0024, O + 0.0025)]
    b = _b(rows)
    t = SimpleNamespace(trade_id="T1", entry_time=b["ts"][0], direction="LONG",
                        stop_price=O - 0.0010, target_price=O + 0.0020)
    d1 = delay_entry(t, b, 1)
    assert d1["entry_price"] == O + 0.0005 and abs(d1["risk_price"] - 0.0015) < 1e-12
    assert delay_entry(t, b, 2) is None  # opens beyond target: no valid fill
