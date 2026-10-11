"""Cross-check committed VT symbol references against the single canonical map."""
from __future__ import annotations

import ast
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = ROOT / "config/broker_symbol_map/vt_markets_demo.yaml"


def _assignments(path: Path) -> dict[str, object]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = {}
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    try:
                        found[target.id] = ast.literal_eval(node.value)
                    except (ValueError, TypeError):
                        pass
    return found


def _assert_broker(mapping: dict[str, str], canonical: str, observed: str) -> None:
    assert observed == mapping[canonical], f"{canonical}: expected {mapping[canonical]!r}, got {observed!r}"


def test_symbol_references_match_vt_map():
    entries = yaml.safe_load(MAP_PATH.read_text(encoding="utf-8"))["entries"]
    mapped = {key: row["broker_symbol"] for key, row in entries.items() if row["status"] == "MAPPED"}

    mt5 = yaml.safe_load((ROOT / "config/mt5.yaml").read_text(encoding="utf-8"))
    assert set(mt5["symbol_suffixes"]) <= set(mapped)
    assert "VT_MARKETS" not in mt5["symbol_map"]  # that broker is resolved only by this map

    for name in ("crypto_ticket_v2.yaml", "crypto_ticket_v3.yaml"):
        config = yaml.safe_load((ROOT / "config/v1_tickets" / name).read_text(encoding="utf-8"))
        for strategy_symbol, canonical in config["venue"]["symbols"].items():
            assert strategy_symbol in ("BTCUSDT", "ETHUSDT")
            _assert_broker(mapped, canonical, mapped[canonical])

    objective_path = ROOT / "scripts/host/verify_objective.py"
    objective = _assignments(objective_path)
    assert objective["EXPECTED_BROKERS"] == mapped
    objective_text = objective_path.read_text(encoding="utf-8")
    assert all(f'"{symbol}"' in objective_text.split("WATCH_UNIVERSE =", 1)[1].splitlines()[0]
               for symbol in ("BTCUSD", "ETHUSD"))
    assert set(objective["FX_MAJORS"] + objective["GOLD"]) <= set(mapped)

    fx = _assignments(ROOT / "src/v1_tickets/fx.py")
    assert set(fx["V1_FX_SYMBOLS"]) == {"EURUSD", "GBPUSD", "USDJPY", "XAUUSD"}
    for canonical, broker in fx["REQUIRED_BROKER_SYMBOL"].items():
        _assert_broker(mapped, canonical, broker)

    strategy = yaml.safe_load((ROOT / "strategies/ST_LARGE_SMC_V1_1_1_1.yaml").read_text(encoding="utf-8"))
    for strategy_symbol, metadata in strategy["symbol_metadata"].items():
        canonical = {"BTCUSDT": "BTCUSD", "ETHUSDT": "ETHUSD"}.get(strategy_symbol, strategy_symbol)
        _assert_broker(mapped, canonical, metadata["broker_symbol"])

    replay = _assignments(ROOT / "scripts/host/replay_pinned_cycle.py")["ORIGINAL_SPREAD"]
    assert set(replay) == {mapped[s] for s in ("EURUSD", "GBPUSD", "USDJPY")}
    probes = _assignments(ROOT / "scripts/host/diagnose_mt5.py")["OFFSET_PROBES"]
    assert probes == (mapped["BTCUSD"], mapped["ETHUSD"], mapped["EURUSD"])


def test_deliberately_wrong_entry_is_rejected():
    deliberately_wrong = {"EURUSD": "EURUSD"}
    try:
        _assert_broker(deliberately_wrong, "EURUSD", "EURUSD-VIP")
    except AssertionError:
        pass
    else:
        raise AssertionError("symbol consistency assertion accepted deliberately wrong EURUSD entry")
