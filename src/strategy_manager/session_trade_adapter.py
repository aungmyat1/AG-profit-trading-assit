"""The ONLY module that knows about the separate `Session Trade Codex` repository.
Invokes its existing, already-governed `scripts/execute_session_signal.py` as a
subprocess with mode-appropriate flags, reads back its `analysis.json` artifact
(`AnalysisResult.to_dict()`) plus the final JSON object it prints to stdout, and maps
both into this repo's StrategyResult (assistant/models.py).

Deliberately does NOT re-derive analyze()'s own inputs (news calendar, account
snapshot, drawdown, journal-healthy, etc.) or reimplement risk/duplicate/governance
logic -- all of that stays exactly where strategies/session_trade/contract.yaml says it
lives: "This repo does not duplicate the strategy's classifier/setup/risk logic."

Verified against scripts/execute_session_signal.py as of 2026-08-27 (Session Trade
Codex commit d026f09a). If that script's CLI/output shape changes, this adapter is the
one place to update -- see the flag/JSON mapping below.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from datetime import date as date_cls
from pathlib import Path
from typing import Optional

from assistant.models import (
    MODE_ANALYZE_ONLY,
    MODE_DEMO_EXECUTION,
    MODE_SHADOW_DEMO,
    STATUS_INVALID_CONTEXT,
    STATUS_NO_SETUP,
    STATUS_TRADE_READY,
    StrategyResult,
)

SESSION_TRADE_CODEX_ROOT = Path(r"D:\ddev\Session Trade Codex")
SCRIPT_RELATIVE_PATH = Path("scripts") / "execute_session_signal.py"
SUBPROCESS_TIMEOUT_SECONDS = 120

# Execution outcomes this adapter recognizes from the script's final stdout JSON block
# (see execute_session_signal.py's main(), verified 2026-08-27) -- exposed on
# AdapterRunResult.execution_outcome for strategy_manager/manager.py to map into an
# AssistantDecision status; not reinterpreted here.
OUTCOME_DRY_RUN = "DRY_RUN"
OUTCOME_DUPLICATE_BLOCKED = "DUPLICATE_BLOCKED"
OUTCOME_REFUSED = "REFUSED"
OUTCOME_ATTEMPTED = "ATTEMPTED"
OUTCOME_NOT_ATTEMPTED = "NOT_ATTEMPTED"
OUTCOME_NO_TRADE = "NO_TRADE"
OUTCOME_ERROR = "ERROR"

SUCCESSFUL_SUBMIT_OUTCOMES = frozenset({"CONFIRMED", "CONFIRMED_VIA_DEAL_HISTORY", "PENDING_ORDER_CONFIRMED"})


class SessionTradeAdapterError(RuntimeError):
    pass


class AdapterRunResult:
    def __init__(self, execution_outcome: str, payload: dict, exit_code: int, analysis: Optional[dict] = None):
        self.execution_outcome = execution_outcome
        self.payload = payload
        self.exit_code = exit_code
        self.analysis = analysis


def _flags_for_mode(mode: str) -> list:
    if mode == MODE_ANALYZE_ONLY:
        return []
    if mode == MODE_SHADOW_DEMO:
        return ["--check"]
    if mode == MODE_DEMO_EXECUTION:
        return ["--check", "--confirm"]
    raise SessionTradeAdapterError(f"UNSUPPORTED_MODE_FOR_ADAPTER: {mode!r}")


def _env_for_mode(mode: str) -> dict:
    env = dict(os.environ)
    if mode == MODE_DEMO_EXECUTION:
        env["ALLOW_ORDER_SUBMISSION"] = "true"
        env["ALLOW_ONE_DEMO_ORDER"] = "true"
    return env


def extract_last_json_object(text: str) -> Optional[dict]:
    """Session Trade Codex's script prints an optional markdown block, then exactly one
    pretty-printed JSON object. Scans every top-level (line-start) `{` for a
    brace-balanced span and keeps the LAST one that parses -- robust to the markdown
    block preceding it without needing a stricter delimiter the source script doesn't
    provide."""
    candidates = []
    lines = text.split("\n")
    offsets = []
    pos = 0
    for line in lines:
        offsets.append(pos)
        pos += len(line) + 1

    for line_idx, line in enumerate(lines):
        if not line.startswith("{"):
            continue
        start = offsets[line_idx]
        depth = 0
        end = None
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end is None:
            continue
        chunk = text[start:end]
        try:
            candidates.append(json.loads(chunk))
        except json.JSONDecodeError:
            continue

    return candidates[-1] if candidates else None


def _find_analysis_json(output_dir: Path) -> Optional[dict]:
    matches = sorted(output_dir.glob("*/*/analysis.json"))
    if not matches:
        return None
    try:
        with open(matches[-1], "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise SessionTradeAdapterError(f"SESSION_TRADE_ANALYSIS_INVALID: {exc}") from exc


def run_session_trade_v1(symbol: str, cycle: str, mode: str) -> AdapterRunResult:
    """Invokes execute_session_signal.py --symbol {symbol} --pair {cycle} with the
    mode-appropriate flags. Raises SessionTradeAdapterError only for infrastructure
    failures (script missing, timeout, unparseable output) -- ordinary trading-state
    outcomes (no setup, duplicate, refused) are returned, not raised."""
    script_path = SESSION_TRADE_CODEX_ROOT / SCRIPT_RELATIVE_PATH
    if not script_path.exists():
        raise SessionTradeAdapterError(f"SESSION_TRADE_CODEX_SCRIPT_NOT_FOUND: {script_path}")

    with tempfile.TemporaryDirectory(prefix="ag_assistant_run_") as tmp_dir:
        args = [
            "python", str(script_path), "--symbol", symbol, "--pair", cycle,
            "--output", tmp_dir, *_flags_for_mode(mode),
        ]
        try:
            proc = subprocess.run(
                args, cwd=str(SESSION_TRADE_CODEX_ROOT), capture_output=True, text=True,
                timeout=SUBPROCESS_TIMEOUT_SECONDS, env=_env_for_mode(mode),
            )
        except subprocess.TimeoutExpired as exc:
            raise SessionTradeAdapterError(f"SESSION_TRADE_CODEX_TIMEOUT: {exc}") from exc

        payload = extract_last_json_object(proc.stdout) or {}
        analysis = _find_analysis_json(Path(tmp_dir))

        if "execution" in payload:
            outcome = payload["execution"]
        elif payload.get("status") == "NO_TRADE":
            outcome = OUTCOME_NO_TRADE
        elif "error" in payload:
            outcome = OUTCOME_ERROR
        elif not payload and proc.returncode != 0:
            raise SessionTradeAdapterError(
                f"SESSION_TRADE_CODEX_UNPARSEABLE_OUTPUT: exit={proc.returncode} stdout={proc.stdout[-500:]!r} stderr={proc.stderr[-500:]!r}"
            )
        else:
            outcome = OUTCOME_NOT_ATTEMPTED

        return AdapterRunResult(execution_outcome=outcome, payload=payload, exit_code=proc.returncode, analysis=analysis)


def to_strategy_result(result: AdapterRunResult, symbol: str, cycle: str) -> StrategyResult:
    """Maps the adapter's raw run result into this repo's normalized StrategyResult.
    Copies setup/direction/entry/SL/TP verbatim from analysis.json -- never
    recomputed."""
    analysis = result.analysis
    if analysis is not None and not isinstance(analysis, dict):
        raise SessionTradeAdapterError("SESSION_TRADE_ANALYSIS_INVALID: expected a JSON object")
    if not analysis:
        if result.execution_outcome in (OUTCOME_NO_TRADE, OUTCOME_ERROR):
            analysis = {}
        else:
            raise SessionTradeAdapterError("SESSION_TRADE_ANALYSIS_MISSING: analysis.json was not produced")
    strategy_id = analysis.get("strategy_id", "SESSION_TRADE_V1")
    strategy_version = str(analysis.get("contract_version", "unknown"))
    trading_date_raw = analysis.get("trading_date")
    session_date = date_cls.fromisoformat(trading_date_raw) if trading_date_raw else date_cls.today()

    accepted = bool(analysis.get("accepted"))
    reason_codes = tuple(analysis.get("reason_codes") or ())

    if result.execution_outcome in (OUTCOME_NO_TRADE, OUTCOME_ERROR):
        return StrategyResult(
            strategy_id=strategy_id, strategy_version=strategy_version, symbol=symbol, cycle=cycle,
            session_date=session_date, status=STATUS_INVALID_CONTEXT,
            reason_codes=reason_codes or (result.payload.get("error") or result.payload.get("reason", "UNKNOWN"),),
            metadata=analysis,
        )

    if not accepted:
        return StrategyResult(
            strategy_id=strategy_id, strategy_version=strategy_version, symbol=symbol, cycle=cycle,
            session_date=session_date, status=STATUS_NO_SETUP, reason_codes=reason_codes, metadata=analysis,
        )

    risk_fraction = analysis.get("risk_fraction")
    return StrategyResult(
        strategy_id=strategy_id, strategy_version=strategy_version, symbol=symbol, cycle=cycle,
        session_date=session_date, status=STATUS_TRADE_READY,
        setup=analysis.get("setup"), direction=analysis.get("direction"),
        entry=analysis.get("entry"), stop_loss=analysis.get("stop_loss"), target=analysis.get("tp2_5r"),
        risk_percent=(risk_fraction * 100 if risk_fraction is not None else None),
        signal_id=result.payload.get("signal_id"), reason_codes=reason_codes, metadata=analysis,
    )
