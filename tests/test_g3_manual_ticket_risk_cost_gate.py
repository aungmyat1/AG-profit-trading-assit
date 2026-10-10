"""AGP-G3-VERIFY: the manual-ticket risk/cost gate of Definition-of-Done gate G3.

Authority read (nothing else is reinterpreted here):
- `docs/PROJECT_OBJECTIVE.md` G3 -- "Required risk and cost keys are present; missing-key and
  threshold tests prove the gates fail closed."
- `docs/governance/OWNER_DECISION_REGISTER.md` OD1009-D2 -- `risk_pct: 0.5`, `cost_warn_R: 0.10`,
  `cost_block_R: 0.25`; cost at or above 0.25R blocks; absent required risk/cost keys fail closed.
- Carriers: `config/owner_ticket.yaml` (FX/gold) and `config/v1_tickets/crypto_cfd_ticket_policy.yaml`
  (crypto CFD, AGP-C12-CRY). `config/trading.yaml risk.risk_per_trade_pct` is NOT a carrier and is
  never a fallback -- stated in the header of `config/owner_ticket.yaml` itself.

Offline and read-only (NO_BROKER_MUTATION): no terminal, no network, no order module. Balance and
symbol metadata are injected values and volume comes from the broker-free `sizing_math.risk`
boundary; `tests/conftest.py` additionally makes every real MT5 operation raise, so a broker call
anywhere in this path would fail loudly instead of passing. Symbol metadata is read from the
AGP-C1-HOST read-only capture (`status/evidence/host_symbol_info_2026-10-09.json`), never invented.

Fixtures: the recorded EURUSD M15 session (`tests/fixtures/manual_ticket/`), a price-scaled gold
geometry derived from that same recorded session (see `gold_candles`), and the frozen crypto-CFD
contract fixtures. No market-data claim is made here: G2 symbol_info acceptance is a separate gate,
and the gold fixture is synthetic gate math, not XAUUSD evidence.

D6/D3 note: production `config/v1_tickets/ready_authority.yaml` keeps `ST_ASIAN_SWEEP_5R_V1` READY
OFF, so a fully conforming FX/gold ticket is TICKET_BLOCKED with READY_AUTHORITY_OFF_D6 whatever the
cost gate says; the crypto CFD contract is not admitted (OD1009-D3), so its ticket is BLOCKED with
LOGIC_STATUS_NOT_VERIFIED. G3 verdicts are therefore asserted on the risk/cost gate's own outputs
(`block_reasons[]`, `warnings[]`, `risk`, `cost_in_R`), never on the ticket state alone.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import re
from decimal import Decimal
from pathlib import Path

import pytest
import yaml
from test_crypto_cfd_strategy_contract_v1 import (  # frozen CFD contract fixtures
    BTC_H1_BEARISH,
    BTC_REF_SHORT,
    BTC_SHORT_DAY,
    _run,
)

from mt5.symbol_resolver import SymbolMeta
from sizing_math import risk as sizing_risk
from strategy_engine.session import Candle
from v1_tickets import guards, logic_gate, ready_authority
from v1_tickets import manual_ticket as mt
from v1_tickets.crypto_cfd_policy import POLICY_PATH, load_ticket_policy
from v1_tickets.fx import session_windows_utc
from v1_tickets.logic_gate import PASS, WARN
from v1_tickets.scan_record import TICKET_BLOCKED

UTC = dt.timezone.utc
REPO_ROOT = Path(mt.REPO_ROOT)
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "manual_ticket"
BALANCE = 10000.0
# Recorded sessions with a conforming L3 geometry and a live signal at 07:20 UTC.
FX_DAY, FX_AT = "2026-06-23", "07:20"          # EURUSD SHORT
GBP_DAY = "2026-10-06"                          # GBPUSD LONG
# OD1009-D2 values: asserted against the carriers below, never assumed.
D2_RISK_PCT, D2_WARN_R, D2_BLOCK_R = 0.5, 0.10, 0.25
# VT Markets demo deal evidence (status/evidence/host_deal_commission_2026-10-09.json) records
# commission 0.0 per deal; 0.0R is therefore an evidenced commission, not an invented one. Using it
# makes the L5 cost complete, so the matrix below isolates the threshold and not the missing-commission
# warning (that one is already pinned by tests/test_manual_ticket_build.py).
EVIDENCED_COMMISSION_R = 0.0


def _candles(name: str) -> list[Candle]:
    with (FIXTURE_DIR / f"{name}_M15_recorded.csv").open(encoding="utf-8") as f:
        return [Candle(dt.datetime.fromisoformat(r["timestamp_utc"]).replace(tzinfo=UTC), float(r["open"]),
                       float(r["high"]), float(r["low"]), float(r["close"])) for r in csv.DictReader(f)]


CANDLES = _candles("EURUSD")
GBP_CANDLES = _candles("GBPUSD")


def host_meta(broker_symbol: str) -> SymbolMeta:
    """SymbolMeta from the AGP-C1-HOST read-only capture -- evidenced values only."""
    fields = json.loads((REPO_ROOT / "status" / "evidence" / "host_symbol_info_2026-10-09.json")
                        .read_text(encoding="utf-8"))["symbols"][broker_symbol]
    return SymbolMeta(symbol=broker_symbol, tick_size=fields["trade_tick_size"],
                      tick_value=fields["trade_tick_value"], contract_size=fields["trade_contract_size"],
                      volume_min=fields["volume_min"], volume_max=fields["volume_max"],
                      volume_step=fields["volume_step"], digits=fields["digits"], point=fields["point"])


EUR_META, GBP_META, GOLD_META = host_meta("EURUSD-VIP"), host_meta("GBPUSD-VIP"), host_meta("XAUUSD-VIP")
BTC_META = host_meta("BTCUSD")


@pytest.fixture(autouse=True)
def _no_repo_evidence(tmp_path, monkeypatch):
    """No host capture is reachable, so metadata is only ever the injected value (fail closed)."""
    monkeypatch.setenv("AG_EVIDENCE_ROOT", str(tmp_path / "no_evidence"))


@pytest.fixture
def l2_conforming(monkeypatch):
    """Test-only isolation of the OD1009-D2 gate.

    The real L2 fails on the frozen v1.1.1 contract/engine divergences (pinned by
    tests/test_manual_ticket_build.py); left in place, LOGIC_GATE_FAIL:L2 outranks every risk/cost
    reason and hides the verdict G3 has to prove. No rule, level or threshold is changed.
    """
    monkeypatch.setattr(mt, "l2_rule_conformance", lambda *a, **k: {"gate": "L2", "status": PASS, "checks": []})


@pytest.fixture
def sizing_spy(monkeypatch):
    """Records every (risk_pct, balance) that actually reaches the broker-free sizing boundary."""
    calls: list[dict] = []
    real = mt.size_position

    def spy(entry, sl, balance, risk_pct, meta):
        calls.append({"entry": entry, "sl": sl, "balance": balance, "risk_pct": risk_pct, "meta": meta})
        return real(entry, sl, balance, risk_pct, meta)

    monkeypatch.setattr(mt, "size_position", spy)
    return calls


def ticket(symbol, candles, *, meta, spread, owner=None, balance=BALANCE, commission_r=None,
           day=FX_DAY, at=FX_AT):
    """One manual ticket from recorded candles; `owner` defaults to the real repo carrier."""
    d = dt.date.fromisoformat(day)
    w = session_windows_utc(d)["ASIAN_LONDON"]
    now = dt.datetime.fromisoformat(f"{day}T{at}:00+00:00")
    session = [c for c in candles if w["ref"][0] <= c.time < w["ref"][1]]
    post = [c for c in candles if w["trade"][0] <= c.time < w["trade"][1]
            and c.time + dt.timedelta(minutes=15) <= now]
    return mt.build_manual_ticket(symbol, "ASIAN_LONDON", d, session, 24, post, now=now, data_close=now,
                                  spread=spread, owner=mt.load_owner_config() if owner is None else owner,
                                  balance=balance, meta=meta, commission_r=commission_r, data_source="FIXTURE")


# --------------------------------------------------------------------- gold geometry (scaled fixture)

SCALE = 2000.0      # recorded EURUSD geometry reused at a USD/oz price scale
GOLD_STOP = 3.00    # round $3.00 stop, so the owner's decimal cost boundaries are exact decimals


@pytest.fixture(scope="module")
def gold_candles():
    """Price-scaled gold geometry: recorded EURUSD M15 x 2000, quoted to cents, sweep wick extended
    so the engine's own stop distance is exactly $3.00 (entry 2286.00 / SL 2289.00, SHORT).

    Synthetic offline gate math derived from recorded data -- not gold market evidence and no XAUUSD
    data claim. It exists because the owner's thresholds are decimal values (0.10R / 0.25R) and a
    2-decimal $3.00 stop is the realistic gold case that exercises them exactly.
    """
    scaled = [Candle(c.time, round(c.open * SCALE, 2), round(c.high * SCALE, 2), round(c.low * SCALE, 2),
                     round(c.close * SCALE, 2)) for c in CANDLES]
    probe = ticket("XAUUSD", scaled, meta=GOLD_META, spread=0.20)
    assert probe["direction"] == "SHORT" and probe["stop_distance"] > 0
    wick = round(probe["entry"] + GOLD_STOP, 2)
    mutated = [Candle(c.time, c.open, wick if c.high == probe["sl"] else c.high, c.low, c.close)
               for c in scaled]
    assert sum(1 for a, b in zip(scaled, mutated) if a.high != b.high) == 1        # the sweep wick only
    check = ticket("XAUUSD", mutated, meta=GOLD_META, spread=0.20)
    assert check["direction"] == "SHORT" and check["stop_distance"] == GOLD_STOP
    assert check["logic_gate"]["L3"]["status"] == PASS and check["logic_gate"]["L4"]["status"] == PASS
    return mutated



@pytest.fixture
def gold_ticket(l2_conforming, gold_candles):
    """Gold ticket builder at an absolute 2-decimal broker spread on the exact $3.00 stop."""
    def build(spread, *, commission_r=EVIDENCED_COMMISSION_R, owner=None):
        return ticket("XAUUSD", gold_candles, meta=GOLD_META, spread=spread, commission_r=commission_r,
                      owner=owner)
    return build


# ------------------------------------------------------------------------- crypto CFD (BTCUSD) fixture

# 00:45 UTC is 15 min after the 00:30 retest close: inside the contract's own validity window.
CRYPTO_NOW = dt.datetime(2026, 1, 7, 0, 45, tzinfo=UTC)
CRYPTO_POLICY_BODY = (REPO_ROOT / POLICY_PATH).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def btc_result():
    result = _run("BTCUSD", BTC_REF_SHORT, BTC_SHORT_DAY, BTC_H1_BEARISH, now=CRYPTO_NOW)
    assert result["result"] == "ENTRY_VALID"
    assert result["evidence"]["target_plan"]["risk_distance"] == 940.0        # entry 84180 / SL 85120
    return result


def crypto_ticket(result, *, spread, commission_r=None, balance=BALANCE, meta=BTC_META, policy=None):
    return mt.build_crypto_cfd_manual_ticket(
        result, now=CRYPTO_NOW, window="WEEKDAY", spread=spread, balance=balance, meta=meta,
        commission_r=commission_r, quote_time=CRYPTO_NOW - dt.timedelta(minutes=1),
        policy=load_ticket_policy() if policy is None else policy)


def carrier_without(tmp_path: Path, rel: str, key: str) -> dict:
    """A real carrier file with exactly one required key removed; no other value is touched."""
    body = "\n".join(line for line in (REPO_ROOT / rel).read_text(encoding="utf-8").splitlines()
                     if not line.split("#")[0].strip().startswith(f"{key}:"))
    assert f"{key}:" not in body
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return mt.load_owner_config(tmp_path) if rel == mt.OWNER_CONFIG else load_ticket_policy(path)


# =====================================================================================  1. carriers

def test_repo_carriers_hold_the_d2_values():
    """OD1009-D2 as written into both carriers: 0.5 / 0.10 / 0.25, status SET, nothing open."""
    if (REPO_ROOT / mt.OWNER_CONFIG_LOCAL).exists():
        pytest.skip("host-local config/local/owner_ticket.yaml present; it wins by design")
    owner = mt.load_owner_config()
    assert (owner["risk_pct"], owner["cost_warn_R"], owner["cost_block_R"]) == (D2_RISK_PCT, D2_WARN_R,
                                                                               D2_BLOCK_R)
    assert owner["risk_status"] == "SET" and owner["warn_status"] == "SET"
    crypto = load_ticket_policy()
    assert (crypto["risk_pct"], crypto["cost_warn_R"], crypto["cost_block_R"]) == (D2_RISK_PCT, D2_WARN_R,
                                                                                  D2_BLOCK_R)
    assert crypto["open_authorities"] == []


def test_host_local_carrier_wins_and_is_never_merged(tmp_path):
    config = tmp_path / "config"
    (config / "local").mkdir(parents=True)
    (config / "owner_ticket.yaml").write_text("owner_ticket:\n  risk_pct: 0.5\n  cost_warn_R: 0.10\n"
                                             "  cost_block_R: 0.25\n", encoding="utf-8")
    (config / "local" / "owner_ticket.yaml").write_text("owner_ticket:\n  risk_pct: 0.25\n", encoding="utf-8")
    local = mt.load_owner_config(tmp_path)
    assert local["risk_pct"] == 0.25                       # host-local file wins
    assert local["cost_warn_R"] is None and local["cost_block_R"] is None       # never merged upward
    assert local["risk_status"] == mt.RISK_CONFIG_MISSING  # and a partial local file fails closed


# ========================================================================  2. risk_pct reaches sizing

def test_owner_risk_pct_reaches_sizing_fx(l2_conforming, sizing_spy):
    """The carrier's 0.5 -- not config/trading.yaml's 1.0 -- is the number sizing receives."""
    t = ticket("EURUSD", CANDLES, meta=EUR_META, spread=0.00002, commission_r=EVIDENCED_COMMISSION_R)
    assert t["risk"]["risk_pct"] == D2_RISK_PCT and t["risk_status"] == "OK"
    assert [c["risk_pct"] for c in sizing_spy] == [D2_RISK_PCT]                  # one call, at 0.5%
    assert sizing_spy[0]["balance"] == BALANCE and sizing_spy[0]["meta"] is EUR_META
    # 0.5% of 10k = $50 budget on a 5.1-pip stop -> 0.98 lots / $49.98 at risk; the trading.yaml
    # account default (1.0%) would size 1.96 lots, so these values also disprove a silent fallback.
    assert t["lot_size"] == pytest.approx(0.98) and t["risk"]["risk_amount"] == pytest.approx(49.98)
    assert t["lot_size"] != pytest.approx(1.96)
    assert t["risk"]["risk_amount"] <= BALANCE * D2_RISK_PCT / 100.0
    assert t["block_reasons"] == [ready_authority.READY_AUTHORITY_OFF]           # D6 only, not risk/cost


def test_owner_risk_pct_reaches_sizing_gbpusd(l2_conforming, sizing_spy):
    """Second FX symbol, second recorded session: the same carrier value, a different lot."""
    t = ticket("GBPUSD", GBP_CANDLES, meta=GBP_META, spread=0.00002, day=GBP_DAY, commission_r=EVIDENCED_COMMISSION_R)
    assert t["risk"]["risk_pct"] == D2_RISK_PCT and [c["risk_pct"] for c in sizing_spy] == [D2_RISK_PCT]
    # 0.5% of 10k = $50 on a 6.2-pip stop -> 0.80 lots / $49.60. The 1.0% account default: 1.60 lots.
    assert t["lot_size"] == pytest.approx(0.80) and t["risk"]["risk_amount"] == pytest.approx(49.6)
    assert t["lot_size"] != pytest.approx(1.60)
    assert t["block_reasons"] == [ready_authority.READY_AUTHORITY_OFF]


def test_owner_risk_pct_reaches_sizing_gold(sizing_spy, gold_ticket):
    t = gold_ticket(0.30)
    assert t["risk"]["risk_pct"] == D2_RISK_PCT and [c["risk_pct"] for c in sizing_spy] == [D2_RISK_PCT]
    # $3.00 stop with the XAUUSD-VIP capture (tick 0.01 / tick value 1.0) -> $300 per lot;
    # 0.5% of 10k = $50 -> 0.16 lots / $48 at risk. trading.yaml's 1.0% would size 0.33 lots.
    assert t["lot_size"] == pytest.approx(0.16) and t["risk"]["risk_amount"] == pytest.approx(48.0)
    assert t["lot_size"] != pytest.approx(0.33)
    assert t["risk"]["risk_amount"] <= BALANCE * D2_RISK_PCT / 100.0


def test_crypto_policy_risk_pct_reaches_sizing(sizing_spy, btc_result):
    t = crypto_ticket(btc_result, spread=94.0)
    assert t["risk_pct"] == D2_RISK_PCT and [c["risk_pct"] for c in sizing_spy] == [D2_RISK_PCT]
    # 940-point stop with the BTCUSD capture (tick 0.01 / tick value 0.01) -> $940 per lot;
    # 0.5% of 10k = $50 -> 0.05 lots. A 1.0% account default would size 0.10 lots.
    assert t["volume"] == pytest.approx(0.05)
    assert t["decision"] == "BLOCKED" and "LOGIC_STATUS_NOT_VERIFIED" in t["reason_codes"]   # OD1009-D3
    assert t["execution_authorized"] is False and t["owner_accept_allowed"] is False


# ============================================================  3. every required key missing -> BLOCK

@pytest.mark.parametrize("key", ["risk_pct", "cost_warn_R", "cost_block_R"])
def test_missing_fx_owner_key_blocks(l2_conforming, key, tmp_path, sizing_spy):
    """Each required key on its own: absent -> TICKET_BLOCKED, RISK_CONFIG_MISSING primary."""
    owner = carrier_without(tmp_path, mt.OWNER_CONFIG, key)
    assert owner["risk_status"] == mt.RISK_CONFIG_MISSING
    t = ticket("EURUSD", CANDLES, meta=EUR_META, spread=0.00002, owner=owner)
    assert t["state"] == TICKET_BLOCKED and t["primary_block_reason"] == mt.RISK_CONFIG_MISSING
    assert t["risk_status"] == mt.RISK_CONFIG_MISSING
    assert t["owner_accept_allowed"] is False and t["ticket_status"] == "BLOCKED"
    assert mt.COST_ABOVE_BLOCK_R not in t["block_reasons"]        # a config gap, not a cost hit
    if key == "risk_pct":
        assert t["lot_size"] == mt.RISK_NOT_SET_TEXT and sizing_spy == []        # never sized at all
    else:
        assert t["risk"]["risk_pct"] == D2_RISK_PCT and sizing_spy               # sizing keeps 0.5
    if key == "cost_warn_R":
        assert t["cost_warn_R"] == mt.WARN_NOT_SET_TEXT and mt.L5_WARN in t["warnings"]
    if key == "cost_block_R":
        assert t["cost_block_R"] == mt.RISK_CONFIG_MISSING


@pytest.mark.parametrize("key", ["risk_pct", "cost_warn_R", "cost_block_R"])
def test_missing_gold_owner_key_blocks(key, tmp_path, gold_ticket, sizing_spy):
    owner = carrier_without(tmp_path, mt.OWNER_CONFIG, key)
    t = gold_ticket(0.30, owner=owner)
    assert t["state"] == TICKET_BLOCKED and t["primary_block_reason"] == mt.RISK_CONFIG_MISSING
    assert t["risk_status"] == mt.RISK_CONFIG_MISSING and t["owner_accept_allowed"] is False
    if key == "risk_pct":
        assert t["lot_size"] == mt.RISK_NOT_SET_TEXT and sizing_spy == []
    else:
        assert t["lot_size"] == pytest.approx(0.16)


@pytest.mark.parametrize("body,risk_usable", [
    ("", False),                                                          # empty file
    ("owner_ticket:\n", False),                                           # block present, keys absent
    ("owner_ticket: {}\n", False),
    ("owner_ticket:\n  risk_pct: 0.5\n", True),                          # both cost keys absent
    ("owner_ticket:\n  cost_warn_R: 0.10\n  cost_block_R: 0.25\n", False),   # risk key absent
    ("owner_ticket:\n  risk_pct: null\n  cost_warn_R: 0.10\n  cost_block_R: 0.25\n", False),
    ("owner_ticket:\n  risk_pct: 0\n  cost_warn_R: 0.10\n  cost_block_R: 0.25\n", False),
    ("owner_ticket:\n  risk_pct: -0.5\n  cost_warn_R: 0.10\n  cost_block_R: 0.25\n", False),
    ("owner_ticket:\n  risk_pct: '0.5'\n  cost_warn_R: 0.10\n  cost_block_R: 0.25\n", False),
    ("owner_ticket:\n  risk_pct: true\n  cost_warn_R: 0.10\n  cost_block_R: 0.25\n", False),
    ("owner_ticket: [0.5, 0.10, 0.25]\n", False),                         # wrong shape
    (":::not yaml", False),                                                # malformed
])
def test_unusable_fx_carrier_blocks(l2_conforming, body, risk_usable, tmp_path, sizing_spy):
    """No default exists: an unusable carrier blocks, and sizing is attempted only where the owner's
    risk_pct itself is usable -- a missing cost key never becomes a missing risk value."""
    config = tmp_path / "config"
    config.mkdir(exist_ok=True)
    (config / "owner_ticket.yaml").write_text(body, encoding="utf-8")
    owner = mt.load_owner_config(tmp_path)
    assert owner["risk_status"] == mt.RISK_CONFIG_MISSING
    assert (owner["risk_pct"] is not None) is risk_usable
    t = ticket("EURUSD", CANDLES, meta=EUR_META, spread=0.00002, owner=owner)
    assert t["state"] == TICKET_BLOCKED and t["primary_block_reason"] == mt.RISK_CONFIG_MISSING
    assert t["risk_status"] == mt.RISK_CONFIG_MISSING and t["owner_accept_allowed"] is False
    if risk_usable:
        assert t["lot_size"] == pytest.approx(0.98) and [c["risk_pct"] for c in sizing_spy] == [D2_RISK_PCT]
        assert t["cost_warn_R"] == mt.WARN_NOT_SET_TEXT or t["cost_block_R"] == mt.RISK_CONFIG_MISSING
    else:
        assert t["lot_size"] == mt.RISK_NOT_SET_TEXT and sizing_spy == []


def test_absent_carrier_files_block(tmp_path, l2_conforming, sizing_spy):
    """No carrier file at all (repo or host-local) -> BLOCK; nothing is inferred."""
    owner = mt.load_owner_config(tmp_path)
    assert owner == {"risk_pct": None, "risk_status": mt.RISK_CONFIG_MISSING, "cost_warn_R": None,
                     "cost_block_R": None, "warn_status": "NOT_SET", "policy_status": "OK"}
    t = ticket("EURUSD", CANDLES, meta=EUR_META, spread=0.00002, owner=owner)
    assert t["state"] == TICKET_BLOCKED and t["primary_block_reason"] == mt.RISK_CONFIG_MISSING
    assert sizing_spy == []


@pytest.mark.parametrize("key", ["risk_pct", "cost_warn_R", "cost_block_R"])
def test_missing_crypto_policy_key_blocks(key, tmp_path, sizing_spy, btc_result):
    """The crypto carrier fails closed per key: RISK_POLICY_AMBIGUOUS, BLOCKED, no volume."""
    policy = carrier_without(tmp_path, POLICY_PATH, key)
    assert policy["risk_pct"] is None and policy["cost_warn_R"] is None and policy["cost_block_R"] is None
    assert "RISK_POLICY_AMBIGUOUS" in policy["open_authorities"]
    t = crypto_ticket(btc_result, spread=94.0, policy=policy)
    assert t["decision"] == "BLOCKED" and "RISK_POLICY_AMBIGUOUS" in t["reason_codes"]
    assert t["volume"] is None and t["risk_pct"] is None and sizing_spy == []
    assert t["owner_accept_allowed"] is False


@pytest.mark.parametrize("owner", [{}, {"risk_pct": D2_RISK_PCT}, {"cost_warn_R": D2_WARN_R},
                                   {"cost_block_R": D2_BLOCK_R},
                                   {"risk_pct": D2_RISK_PCT, "cost_warn_R": D2_WARN_R}])
def test_owner_mapping_missing_a_required_key_blocks_instead_of_raising(l2_conforming, owner, sizing_spy):
    """A required key absent from the owner mapping itself still ends in the canonical BLOCK reason,
    not in a KeyError that would leave a scheduled cycle without a terminal outcome."""
    t = ticket("EURUSD", CANDLES, meta=EUR_META, spread=0.00002, owner=owner)
    assert t["state"] == TICKET_BLOCKED and mt.RISK_CONFIG_MISSING in t["block_reasons"]
    assert t["owner_accept_allowed"] is False and t["ticket_status"] == "BLOCKED"
    if owner.get("risk_pct") is None:
        assert t["lot_size"] == mt.RISK_NOT_SET_TEXT and sizing_spy == []


# ================================================================================  4. cost boundaries

def l5_verdict(t) -> str:
    return {c["id"]: c["verdict"] for c in t["logic_gate"]["L5"]["checks"]}["L5.cost_vs_warn_level"]


def assert_cost_verdict(t, *, cost_r, expect_block, expect_warn):
    """One shared reading of the gate outputs for a cost_in_R value."""
    assert t["cost_in_R"] == pytest.approx(cost_r, abs=5e-5)
    assert t["cost_warn_R"] == D2_WARN_R and t["cost_block_R"] == D2_BLOCK_R
    assert (mt.COST_ABOVE_BLOCK_R in t["block_reasons"]) is expect_block
    if expect_block:
        # severity tier 2: the owner's cost block outranks spread/D6 reasons and is the primary
        assert t["primary_block_reason"] == mt.COST_ABOVE_BLOCK_R
        assert t["state"] == TICKET_BLOCKED and t["owner_accept_allowed"] is False
    assert (mt.L5_WARN in t["warnings"]) is expect_warn
    assert mt.L5_WARN not in t["block_reasons"]                  # advisory is never a block reason
    assert l5_verdict(t) == (PASS if not expect_warn else WARN)


# (cost in R, spread as a fraction of the engine's own stop, commission in R, verdict)
FX_ROWS = [
    (0.09, 0.09, EVIDENCED_COMMISSION_R, "BELOW_WARN"),
    (0.10, 0.10, EVIDENCED_COMMISSION_R, "AT_WARN"),       # 0.10R boundary -> WARN, never a block
    (0.11, 0.11, EVIDENCED_COMMISSION_R, "ABOVE_WARN"),
    (0.2499, 0.2499, EVIDENCED_COMMISSION_R, "BELOW_BLOCK"),
    (0.25, 0.25, EVIDENCED_COMMISSION_R, "AT_BLOCK"),      # 0.25R boundary -> BLOCK
    (0.25, 0.23, 0.02, "AT_BLOCK"),                        # spread 0.23R + commission 0.02R
]


FX_CASES = [
    pytest.param("EURUSD", CANDLES, EUR_META, FX_DAY, id="EURUSD"),
    pytest.param("GBPUSD", GBP_CANDLES, GBP_META, GBP_DAY, id="GBPUSD"),
]


@pytest.mark.parametrize("symbol,candles,meta,day", FX_CASES)
@pytest.mark.parametrize("cost_r,spread_fraction,commission,verdict", FX_ROWS)
def test_fx_cost_thresholds(l2_conforming, symbol, candles, meta, day, cost_r, spread_fraction, commission,
                            verdict):
    risk = ticket(symbol, candles, meta=meta, spread=0.00002, day=day)["stop_distance"]
    t = ticket(symbol, candles, meta=meta, spread=risk * spread_fraction, commission_r=commission, day=day)
    assert_cost_verdict(t, cost_r=cost_r, expect_block=verdict == "AT_BLOCK",
                        expect_warn=verdict in ("AT_WARN", "ABOVE_WARN", "BELOW_BLOCK", "AT_BLOCK"))
    if verdict == "BELOW_WARN":
        assert t["warnings"] == [] and t["block_reasons"] == [ready_authority.READY_AUTHORITY_OFF]


# (spread USD, commission R, cost in R, verdict) on the exact $3.00 gold stop
GOLD_ROWS = [
    (0.27, EVIDENCED_COMMISSION_R, 0.09, "BELOW_WARN"),
    (0.30, EVIDENCED_COMMISSION_R, 0.10, "AT_WARN"),       # 0.30/3.00: decimal 0.10R, float 1 ulp below
    (0.45, 0.05, 0.20, "ABOVE_WARN"),
    (0.74, EVIDENCED_COMMISSION_R, 0.2467, "BELOW_BLOCK"),
    (0.75, EVIDENCED_COMMISSION_R, 0.25, "AT_BLOCK"),      # 0.75/3.00 == 0.25R exactly
    (0.69, 0.02, 0.25, "AT_BLOCK"),                        # 0.23R + 0.02R: decimal 0.25R, float 1 ulp below
    (0.57, 0.06, 0.25, "AT_BLOCK"),                        # 0.19R + 0.06R: decimal 0.25R, float 1 ulp below
]


@pytest.mark.parametrize("spread,commission,cost_r,verdict", GOLD_ROWS)
def test_gold_cost_thresholds(gold_ticket, spread, commission, cost_r, verdict):
    t = gold_ticket(spread, commission_r=commission)
    assert_cost_verdict(t, cost_r=cost_r, expect_block=verdict == "AT_BLOCK",
                        expect_warn=verdict in ("AT_WARN", "ABOVE_WARN", "BELOW_BLOCK", "AT_BLOCK"))
    if verdict == "BELOW_WARN":
        assert t["warnings"] == [] and t["block_reasons"] == [ready_authority.READY_AUTHORITY_OFF]
    if verdict == "AT_WARN":
        # 10% of the stop is inside the legacy 15% spread guard: the warn adds no block reason at all
        assert t["block_reasons"] == [ready_authority.READY_AUTHORITY_OFF]


# (spread USD, commission R, cost in R, expected warnings, expected cost reasons) on the 940-point stop
CRYPTO_ROWS = [
    (84.6, None, 0.09, ["COMMISSION_UNKNOWN"], []),
    (94.0, None, 0.10, ["COMMISSION_UNKNOWN", "SPREAD_WARN", "COST_WARN"], []),      # AT 0.10R
    (94.0, EVIDENCED_COMMISSION_R, 0.10, ["SPREAD_WARN", "COST_WARN"], []),
    (188.0, 0.05, 0.25, ["SPREAD_WARN"], ["COST_TOO_HIGH"]),                         # AT 0.25R
    (235.0, None, 0.25, ["COMMISSION_UNKNOWN"], ["SPREAD_TOO_WIDE", "COST_TOO_HIGH"]),
    (216.2, 0.02, 0.25, [], ["SPREAD_TOO_WIDE", "COST_TOO_HIGH"]),      # 0.23R + 0.02R, 1 ulp below
    (216.2, None, 0.23, ["COMMISSION_UNKNOWN", "COST_WARN"], ["SPREAD_TOO_WIDE"]),      # just below
]


@pytest.mark.parametrize("spread,commission,cost_r,warnings,reasons", CRYPTO_ROWS)
def test_crypto_cost_thresholds(btc_result, spread, commission, cost_r, warnings, reasons):
    """The crypto carrier's D2/D4 gate on a real BTCUSD contract result (940-point stop)."""
    t = crypto_ticket(btc_result, spread=spread, commission_r=commission)
    assert t["cost_in_R"] == pytest.approx(cost_r, abs=5e-5)
    assert t["warnings"] == warnings
    for reason in reasons:
        assert reason in t["reason_codes"]
    assert ("COST_TOO_HIGH" in t["reason_codes"]) is ("COST_TOO_HIGH" in reasons)
    assert t["decision"] == "BLOCKED"                    # OD1009-D3: the contract is not admitted
    assert t["execution_authorized"] is False and t["owner_accept_allowed"] is False


def test_shared_cost_predicate_boundary_semantics():
    """One predicate, both carriers: the boundary itself triggers; a visibly lower cost does not."""
    assert mt.cost_at_or_above_block(D2_BLOCK_R, D2_BLOCK_R) is True
    assert guards.cost_at_or_above(D2_WARN_R, D2_WARN_R) is True
    assert guards.cost_at_or_above(0.2499, D2_BLOCK_R) is False
    assert guards.cost_at_or_above(0.0999, D2_WARN_R) is False
    # Unknown cost or unknown threshold never triggers and is never treated as zero.
    assert guards.cost_at_or_above(None, D2_BLOCK_R) is False
    assert guards.cost_at_or_above(D2_BLOCK_R, None) is False


@pytest.mark.parametrize("distance,spread,commission", [
    (3.00, 0.69, 0.02),      # gold: 0.23R + 0.02R = 0.25R in decimal
    (3.00, 0.30, None),      # gold: 0.10R in decimal
    (5.65, 1.13, 0.05),      # 0.20R + 0.05R = 0.25R in decimal
    (1023.0, 102.3, None),   # 0.10R in decimal
    (940.0, 216.2, 0.02),    # BTC: 0.23R + 0.02R = 0.25R in decimal
])
def test_decimal_boundary_cost_is_never_missed_by_float_noise(distance, spread, commission):
    """A cost whose exact decimal value IS the owner threshold must trigger it: binary division noise
    (0.69/3.00 + 0.02 == 0.24999999999999997) must not turn an owner BLOCK into a pass or an owner
    WARN into silence. The tolerance is relative and orders of magnitude tighter than the 4-decimal
    cost_in_R the owner is shown, so no ticket-visible decision changes."""
    exact = Decimal(str(spread)) / Decimal(str(distance)) + (Decimal(str(commission)) if commission
                                                             else Decimal(0))
    assert exact in (Decimal("0.25"), Decimal("0.10"))
    cost = spread / distance + (commission or 0.0)
    assert cost != float(exact), "fixture no longer exercises the noise it exists for"
    assert round(cost, 4) == float(exact)                       # the owner is shown the boundary value
    assert guards.cost_at_or_above(cost, float(exact)) is True
    assert mt.cost_at_or_above_block(cost, D2_BLOCK_R) is (exact == Decimal("0.25"))
    blocks, warns, _, gate_cost = mt.crypto_cfd_cost_gate(distance, spread, commission, load_ticket_policy())
    assert gate_cost == pytest.approx(cost)
    assert ("COST_TOO_HIGH" in blocks) is (exact == Decimal("0.25"))
    assert ("COST_WARN" in warns) is (exact == Decimal("0.10"))
    assert logic_gate.l5_cost(spread, distance, commission_r=commission,
                              warn_r=D2_WARN_R)["status"] == WARN


@pytest.mark.parametrize("spread,risk,commission,warn_verdict", [
    (0.21, 2.1, 0.0, WARN),      # 0.21/2.10 IS 0.10R in decimal; binary gives 1 ulp less -> still WARN
    (0.2079, 2.1, 0.0, PASS),    # 0.099R: visibly below the warn level -> PASS
    (0.24, 3.00, 0.02, WARN),    # 0.08R + 0.02R = 0.10R exactly
    (0.24, 3.00, 0.01, PASS),    # 0.08R + 0.01R = 0.09R
])
def test_fx_warn_boundary_with_a_known_commission(spread, risk, commission, warn_verdict):
    """L5 with complete cost evidence: the owner's warn level triggers when the cost reaches it."""
    gate = logic_gate.l5_cost(spread, risk, commission_r=commission, warn_r=D2_WARN_R)
    checks = {c["id"]: c for c in gate["checks"]}
    assert checks["L5.cost_vs_warn_level"]["verdict"] == warn_verdict
    assert checks["L5.spread_R"]["verdict"] == PASS and checks["L5.commission_R"]["verdict"] == PASS
    assert gate["status"] == warn_verdict


def test_displayed_cost_and_block_decision_agree_at_the_boundary(gold_ticket):
    """The owner-visible cost_in_R and the block decision are the same number at the boundary."""
    blocked = gold_ticket(0.69, commission_r=0.02)
    assert blocked["cost_in_R"] == 0.25 and blocked["cost_block_R"] == D2_BLOCK_R
    assert mt.COST_ABOVE_BLOCK_R in blocked["block_reasons"]
    below = gold_ticket(0.72)
    assert below["cost_in_R"] == 0.24 and mt.COST_ABOVE_BLOCK_R not in below["block_reasons"]


# ================================================  5. no fallback to config/trading.yaml's default

TRADING_YAML_SENTINEL = ("mode: ANALYSIS\nexecution:\n  allow_order_send: false\n"
                         "account:\n  allow_live_trading: false\nrisk:\n  risk_per_trade_pct: 7.5\n")


def test_trading_yaml_account_default_is_never_a_fallback(tmp_path, l2_conforming, sizing_spy):
    """An execution config in the same root with an unmistakable 7.5% account default and no owner
    carrier: the ticket blocks and sizing is never attempted at any percentage."""
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "trading.yaml").write_text(TRADING_YAML_SENTINEL, encoding="utf-8")
    assert (REPO_ROOT / "config" / "trading.yaml").is_file()                # the real default exists too
    owner = mt.load_owner_config(tmp_path)
    assert owner["risk_pct"] is None and owner["risk_status"] == mt.RISK_CONFIG_MISSING
    t = ticket("EURUSD", CANDLES, meta=EUR_META, spread=0.00002, owner=owner)
    assert t["state"] == TICKET_BLOCKED and t["primary_block_reason"] == mt.RISK_CONFIG_MISSING
    assert t["lot_size"] == mt.RISK_NOT_SET_TEXT and t["risk"]["risk_pct"] is None
    assert "risk_amount" not in t["risk"] and sizing_spy == []


def test_repo_default_differs_from_the_owner_value_so_the_lots_are_evidence(l2_conforming, sizing_spy):
    """config/trading.yaml really carries a different number (1.0), so the sized lots above prove the
    owner carrier reached sizing rather than coinciding with the account default."""
    trading = yaml.safe_load((REPO_ROOT / "config" / "trading.yaml").read_text(encoding="utf-8"))
    account_default = trading["risk"]["risk_per_trade_pct"]
    assert account_default == 1.0 != D2_RISK_PCT
    t = ticket("EURUSD", CANDLES, meta=EUR_META, spread=0.00002)
    fallback_lot = sizing_risk.size_position(t["entry"], t["sl"], BALANCE, account_default, EUR_META)[0]
    assert t["lot_size"] == pytest.approx(0.98) and fallback_lot == pytest.approx(1.96)
    assert [c["risk_pct"] for c in sizing_spy] == [D2_RISK_PCT]


@pytest.mark.parametrize("module", [mt, sizing_risk, logic_gate, guards, ready_authority])
def test_risk_cost_chain_has_no_edge_to_the_execution_config(module):
    """Structural proof: the manual-ticket risk/cost chain neither reads config/trading.yaml nor
    imports the execution risk authority."""
    source = Path(module.__file__).read_text(encoding="utf-8")
    assert "trading.yaml" not in source
    assert "from execution" not in source and "import execution" not in source


# =================================================================================  6. read-only

def test_risk_cost_gate_stays_read_only(l2_conforming, sizing_spy, btc_result, gold_ticket):
    """NO_BROKER_MUTATION: every asset class keeps the informational stamps, and the only numeric
    boundary crossed is the broker-free sizing_math.risk call recorded by the spy."""
    fx_t = ticket("EURUSD", CANDLES, meta=EUR_META, spread=0.00002)
    gold_t = gold_ticket(0.30)
    crypto_t = crypto_ticket(btc_result, spread=94.0)
    for t in (fx_t, gold_t):
        assert t["invariants"] == {"order_ready": False, "broker_authorized": False, "edge_verified": False,
                                   "orders_sent_by_system": 0}
        assert t["authority"] == mt.AUTHORITY_TEXT and t["edge_status"] == mt.EDGE_STATUS
        # D6 READY authority is OFF, so the label is the shadow one; both are non-executing.
        assert t["label"].endswith("NOT A BROKER ORDER")
        assert mt.render_text(t)                                  # renders without a broker field
    assert crypto_t["label"].startswith("INFORMATIONAL PROPOSAL")
    assert crypto_t["execution_authorized"] is False and crypto_t["edge_verified"] is False
    assert {c["meta"] for c in sizing_spy} <= {EUR_META, GOLD_META, BTC_META}
    assert all(c["risk_pct"] == D2_RISK_PCT for c in sizing_spy)


# ============================================  6. follow-up: fail-closed boundary, unknowns, display

def test_near_boundary_float_slack_is_decided_as_the_boundary():
    """cost = 0.25 - 5e-10 is inside the 1e-9 relative slack -> BLOCK; 0.10 - 5e-10 -> WARN (never PASS).

    The predicate: cost >= threshold - COST_R_TOL * max(1, |threshold|), with COST_R_TOL = 1e-9.
    """
    cost_block, cost_warn = 0.25 - 5e-10, 0.10 - 5e-10
    assert mt.cost_at_or_above_block(cost_block, D2_BLOCK_R) is True
    assert mt.cost_at_or_above_block(cost_warn, D2_BLOCK_R) is False
    assert guards.cost_at_or_above(cost_warn, D2_WARN_R) is True
    # the same verdict in the crypto carrier path
    blocks, _, _, _ = mt.crypto_cfd_cost_gate(1.0, cost_block, None, load_ticket_policy())
    assert "COST_TOO_HIGH" in blocks
    blocks, warns, _, _ = mt.crypto_cfd_cost_gate(1.0, cost_warn, None, load_ticket_policy())
    assert "COST_TOO_HIGH" not in blocks and "COST_WARN" in warns


def test_unknown_cost_is_not_a_pass_and_blocks_the_ticket(gold_ticket):
    """Predicate: None -> False (no owner trigger, never zero). Ticket: an unknown cost BLOCKS."""
    assert guards.cost_at_or_above(None, D2_BLOCK_R) is False
    t = gold_ticket(None)                                   # spread unknown -> cost unknown
    assert t["cost_in_R"] is None                           # never 0
    assert "SPREAD_NOT_EVALUATED" in t["block_reasons"] and t["state"] == TICKET_BLOCKED


@pytest.mark.parametrize("commission,reason", [
    (None, "COMMISSION_INSUFFICIENT"),
    (-0.01, "COMMISSION_INVALID"),
    (float("nan"), "COMMISSION_INVALID"),
    (float("inf"), "COMMISSION_INVALID"),
])
def test_fx_commission_missing_or_invalid_blocks_and_is_never_zero(gold_ticket, commission, reason):
    t = gold_ticket(0.27, commission_r=commission)
    assert reason in t["block_reasons"] and t["state"] == TICKET_BLOCKED
    assert t["cost_in_R"] is None                           # never the spread alone, never 0
    assert t["owner_accept_allowed"] is False


def test_fx_zero_commission_is_a_real_value_not_missing(gold_ticket):
    t = gold_ticket(0.27, commission_r=0.0)
    assert t["cost_in_R"] == pytest.approx(0.09, abs=5e-5)
    assert not {"COST_UNKNOWN", "COMMISSION_INSUFFICIENT", "COMMISSION_INVALID"} & set(t["block_reasons"])


def test_fx_warn_not_below_block_is_ambiguous_like_crypto(tmp_path, l2_conforming, sizing_spy):
    """cost_warn_R >= cost_block_R: FX/gold use RISK_POLICY_AMBIGUOUS, the same code crypto raises."""
    cfg = tmp_path / mt.OWNER_CONFIG
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text("owner_ticket:\n  risk_pct: 0.5\n  cost_warn_R: 0.25\n  cost_block_R: 0.25\n", encoding="utf-8")
    owner = mt.load_owner_config(tmp_path)
    t = ticket("EURUSD", CANDLES, meta=EUR_META, spread=0.00002, owner=owner, commission_r=EVIDENCED_COMMISSION_R)
    assert "RISK_POLICY_AMBIGUOUS" in t["block_reasons"] and t["primary_block_reason"] == "RISK_POLICY_AMBIGUOUS"
    assert t["state"] == TICKET_BLOCKED and sizing_spy == []
    # crypto carrier with the same inverted pair: the loader raises the same open authority
    inverted = re.sub(r"(cost_warn_R:\s*)[0-9.]+", r"\g<1>0.25", CRYPTO_POLICY_BODY)
    inverted = re.sub(r"(cost_block_R:\s*)[0-9.]+", r"\g<1>0.25", inverted)
    crypto_path = tmp_path / "crypto_cfd_ticket_policy.yaml"
    crypto_path.write_text(inverted, encoding="utf-8")
    assert "RISK_POLICY_AMBIGUOUS" in load_ticket_policy(crypto_path)["open_authorities"]


def test_displayed_cost_names_the_decision_side_at_the_boundary(gold_ticket):
    """4dp shows 0.2500 but the exact cost is below the 0.25R block -> WARN side, stated explicitly."""
    below = gold_ticket(0.7499)                             # exact 0.249966... -> shown 0.2500
    assert below["cost_in_R"] == 0.25
    assert mt.COST_ABOVE_BLOCK_R not in below["block_reasons"]
    assert below["cost_in_R_display"] == "0.2500 (<0.25, WARN)"
    assert "0.2500 (<0.25, WARN)" in mt.render_text(below)
    at = gold_ticket(0.69, commission_r=0.02)              # exact 0.25 -> BLOCK side
    assert at["cost_in_R_display"] == "0.2500 (>=0.25, BLOCK)"
    plain = gold_ticket(0.27)                              # 0.09R: no threshold shown -> bare value
    assert plain["cost_in_R_display"] == "0.0900"
