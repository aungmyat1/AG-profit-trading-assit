"""Combined FX daily decision report: aggregates the existing, unchanged per-cycle
end-of-window report (report.render_pilot_end_report) for ASIAN_LONDON and
LONDON_NEWYORK into one canonical daily artifact. Adds no new strategy/decision logic --
reads only what pipeline.py/report.py/store.py already compute and persist.

Release-identity is reported honestly: whatever pilot_config.DEFAULT_RELEASE_CONFIG_PATH
currently resolves to is what gets written here. This module never fabricates a V1.0.3
label ahead of the separately-tracked release-identity remediation -- see
docs/status/AG_TRADE_ASSISTANT_V1_0_3_RELEASE_QUALIFICATION_BLOCKERS_STATUS.md.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, Optional

from strategy_engine.loader import load_strategy

from .pilot_config import DEFAULT_RELEASE_CONFIG_PATH, load_pilot_config, load_raw_yaml
from .report import render_pilot_end_report
from .store import DEFAULT_STATE_DIR, PilotStores

SCHEMA_VERSION = "AG_FX_DAILY_REPORT_V1"
REPORT_TYPE = "FX_DAILY"

ASIAN_LONDON_PILOT_PATH = "config/pilot/AG_POST_ASIAN_LONDON_PILOT_V1_0_1.yaml"
LONDON_NEWYORK_PILOT_PATH = "config/pilot/AG_POST_LONDON_NEWYORK_PILOT_V1_0_1.yaml"


def _cycle_report(pilot_path: str, trading_date: dt.date, release_id: str) -> Dict[str, Any]:
    pilot = load_pilot_config(pilot_path)
    strategy = load_strategy(pilot.strategy_source_path)
    stores = PilotStores.default(pilot.strategy_id, pilot.state_dir or DEFAULT_STATE_DIR)
    return render_pilot_end_report(pilot, strategy, release_id, trading_date, stores)


def build_fx_daily_report(
    trading_date: dt.date,
    asian_london_pilot_path: str = ASIAN_LONDON_PILOT_PATH,
    london_newyork_pilot_path: str = LONDON_NEWYORK_PILOT_PATH,
    release_config_path: str = DEFAULT_RELEASE_CONFIG_PATH,
    generated_at: Optional[dt.datetime] = None,
) -> Dict[str, Any]:
    """Read-only: never claims a ledger slot, never mutates a snapshot, never calls
    order_send. Combines two already-persisted, independent cycle reports -- never
    merges their ledgers/state (ASIAN_LONDON and LONDON_NEWYORK stay isolated, each
    read from its own pilot config's state_dir)."""
    release_id = load_raw_yaml(release_config_path).get("release_id", "UNKNOWN")
    generated_at = generated_at or dt.datetime.now(dt.timezone.utc)

    asian_london = _cycle_report(asian_london_pilot_path, trading_date, release_id)
    london_newyork = _cycle_report(london_newyork_pilot_path, trading_date, release_id)

    return {
        "schema_version": SCHEMA_VERSION,
        "application_release": release_id,
        "report_type": REPORT_TYPE,
        "trading_date": trading_date.isoformat(),
        "generated_at_utc": generated_at.isoformat(),
        "cycles": {
            "ASIAN_LONDON": asian_london,
            "LONDON_NEWYORK": london_newyork,
        },
        "execution_authority": {
            "proposal_only": True,
            "automatic_execution": "DISABLED",
            "fx_live_execution": "DISABLED",
        },
        "daily_proposal_required": False,
        "daily_decision_required": True,
    }


def human_readable_fx_daily_report(report: Dict[str, Any]) -> str:
    lines = [
        "AG PROFIT TRADING -- FX DAILY REPORT",
        report["application_release"],
        f"Trading date: {report['trading_date']}",
        f"Generated: {report['generated_at_utc']}",
        "",
    ]
    for cycle_name in ("ASIAN_LONDON", "LONDON_NEWYORK"):
        cycle = report["cycles"][cycle_name]
        lines.append(cycle_name)
        for symbol, pair in cycle["pairs"].items():
            state_line = f"  {symbol}: {pair['final_strategy_state']}"
            if pair.get("final_reason"):
                state_line += f"  ({pair['final_reason']})"
            lines.append(state_line)
            if pair.get("proposal_id"):
                lines.append(f"    proposal_id: {pair['proposal_id']}")
        lines.append(f"  slots_used: {cycle['portfolio']['slots_used']}/{cycle['portfolio']['max_slots']}")
        lines.append(f"  result: {cycle['result']}")
        lines.append("")
    lines.append("EXECUTION")
    lines.append(f"automatic_execution = {report['execution_authority']['automatic_execution']}")
    lines.append(f"fx_live_execution = {report['execution_authority']['fx_live_execution']}")
    return "\n".join(lines)
