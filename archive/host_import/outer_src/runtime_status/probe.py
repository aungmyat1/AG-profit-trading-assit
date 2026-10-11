"""Bounded, read-only runtime-status probes (AG_PROJECT_LIVE_CONTROL_PLANE_V2).

GOVERNANCE_STATUS and RUNTIME_STATUS are separate authorities. This module produces
ONLY RUNTIME observations: whether the local runtime services are reachable and whether
the V1.2 proposal-pipeline adapters are importable. It has no knowledge of, and cannot
change, any governance fact (validation_state, lifecycle_stage, demo_authorized,
live_authorized, blockers, next_safe_action) -- and its results are never fed into the
governance state fingerprint (see scripts/generate_live_status.py).

Hard rules:
  - Never imports MetaTrader5, anything under src/execution/, src/mt5/ order paths, or
    any order_check/order_send capability. MT5/broker/market-data are probed only
    through the local read-only API gateway's GET endpoints.
  - Never starts a service. A stopped service is reported as UNAVAILABLE -- never
    "repaired" here to manufacture a PASS.
  - Every network probe is an HTTP GET with a short timeout against the local API
    gateway (127.0.0.1:8000) only. No POSTs, no writes, no order side effects.
  - Every local probe is a file read (proposal ledger, scheduler checkpoint) or an
    importability check (proposal adapters).
"""
from __future__ import annotations

import importlib
import json
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, Tuple

STATUS_AVAILABLE = "AVAILABLE"
STATUS_UNAVAILABLE = "UNAVAILABLE"

DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT_SECONDS = 2.0

_HttpGet = Callable[[str, float], Tuple[int, dict]]


@dataclass(frozen=True)
class RuntimeProbe:
    """One runtime subsystem observation. `detail` is diagnostic only and must never
    carry credentials, order state, or governance conclusions."""

    name: str
    status: str  # STATUS_AVAILABLE | STATUS_UNAVAILABLE
    detail: str


@dataclass(frozen=True)
class RuntimeStatus:
    """Read-only runtime observation set. `governance_impact` is a declarative
    invariant (always NONE): this object is excluded from the governance fingerprint by
    construction in the generator, not by convention."""

    checked_at_utc: str
    probes: Tuple[RuntimeProbe, ...]
    governance_impact: str = "NONE"


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _http_get_json(url: str, timeout: float) -> Tuple[int, dict]:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        return resp.status, body


def _unavailable(name: str, detail: str) -> RuntimeProbe:
    return RuntimeProbe(name=name, status=STATUS_UNAVAILABLE, detail=detail)


def _probe_fastapi(
    api_base_url: str, timeout: float, http_get: _HttpGet = _http_get_json
) -> RuntimeProbe:
    try:
        code, body = http_get(f"{api_base_url}/api/health", timeout)
    except urllib.error.URLError as exc:
        return _unavailable("fastapi", f"API gateway unreachable: {exc.reason}")
    except urllib.error.HTTPError as exc:
        return _unavailable("fastapi", f"GET /api/health -> HTTP {exc.code}")
    except Exception as exc:  # noqa: BLE001 -- bounded probe, never raise to caller
        return _unavailable("fastapi", f"error: {type(exc).__name__}")
    if code == 200 and body.get("status") == "OK":
        return RuntimeProbe(name="fastapi", status=STATUS_AVAILABLE, detail="GET /api/health -> 200 OK")
    return _unavailable("fastapi", f"GET /api/health -> unexpected {code} {body!r}")


def _probe_broker_mt5(
    api_base_url: str, timeout: float, http_get: _HttpGet = _http_get_json
) -> Tuple[RuntimeProbe, RuntimeProbe]:
    try:
        code, body = http_get(f"{api_base_url}/api/broker/status", timeout)
    except urllib.error.URLError as exc:
        detail = f"probed via API gateway; unreachable: {exc.reason}"
        return _unavailable("mt5", detail), _unavailable("broker", detail)
    except urllib.error.HTTPError as exc:
        detail = f"GET /api/broker/status -> HTTP {exc.code}"
        return _unavailable("mt5", detail), _unavailable("broker", detail)
    except Exception as exc:  # noqa: BLE001
        detail = f"error: {type(exc).__name__}"
        return _unavailable("mt5", detail), _unavailable("broker", detail)

    connected = bool(body.get("connected", False))
    if connected:
        environment = body.get("environment", "UNKNOWN")
        mt5 = RuntimeProbe(name="mt5", status=STATUS_AVAILABLE, detail="MT5 terminal reachable via API gateway")
        broker = RuntimeProbe(
            name="broker",
            status=STATUS_AVAILABLE,
            detail=f"connected (environment={environment})",
        )
    else:
        reason = body.get("reason_code", "MT5_NOT_CONNECTED")
        mt5 = _unavailable("mt5", f"reason_code={reason}")
        broker = _unavailable("broker", f"reason_code={reason}")
    return mt5, broker


def _probe_market_data(
    api_base_url: str, timeout: float, http_get: _HttpGet = _http_get_json
) -> RuntimeProbe:
    url = f"{api_base_url}/api/market-data/candles?symbol=EURUSD&timeframe=M15&count=1"
    try:
        code, body = http_get(url, timeout)
    except urllib.error.URLError as exc:
        return _unavailable("market_data", f"probed via API gateway; unreachable: {exc.reason}")
    except urllib.error.HTTPError as exc:
        reason = "unknown"
        try:
            reason = json.loads(exc.read().decode("utf-8")).get("detail", {}).get("reason_code", "unknown")
        except Exception:  # noqa: BLE001
            pass
        return _unavailable("market_data", f"HTTP {exc.code} ({reason})")
    except Exception as exc:  # noqa: BLE001
        return _unavailable("market_data", f"error: {type(exc).__name__}")
    if code == 200:
        candles = body.get("candles") if isinstance(body, dict) else None
        n = len(candles) if isinstance(candles, list) else 0
        return RuntimeProbe(name="market_data", status=STATUS_AVAILABLE, detail=f"{n} EURUSD M15 candle(s) returned")
    return _unavailable("market_data", f"unexpected {code}")


def _probe_proposal_ledger(repo_root: Path) -> RuntimeProbe:
    """Read-only. Reports the EXPIRY-CORRECTED current-proposal count, not the raw
    persisted record count.

    `ProposalLedger.list_active_proposals()` returns EVERY persisted record as
    `PROPOSAL_READY`, including records whose strategy-owned expiry has already passed
    (63 of 69 at the time of writing), so using its length as the operational count
    overstates current proposals. The raw count is still reported, explicitly labelled
    as observation records rather than opportunities, so neither figure is hidden.

    Still a pure file read plus an importability check -- no execution/order machinery,
    no writes, no governance impact (see this module's own hard rules)."""
    try:
        from proposal_envelope.ledger import ProposalLedger
        from proposal_envelope.occurrence_identity_v1 import (
            presentation_ready_count_from_ledger_file,
        )

        path = str(repo_root / "state" / "proposal_ledger" / "proposal_ledger.json")
        ledger = ProposalLedger(path=path)
        persisted = len(ledger.list_active_proposals())
        current = presentation_ready_count_from_ledger_file(path=path)
        return RuntimeProbe(
            name="proposal_ledger",
            status=STATUS_AVAILABLE,
            detail=(
                f"{current} current canonical proposal(s); {persisted} persisted "
                "observation record(s) (raw count, not an opportunity count)"
            ),
        )
    except FileNotFoundError:
        return _unavailable("proposal_ledger", "ledger file missing")
    except Exception as exc:  # noqa: BLE001
        return _unavailable("proposal_ledger", f"error: {type(exc).__name__}")


def _probe_scheduler(repo_root: Path) -> RuntimeProbe:
    path = repo_root / "journal" / "ag_scheduler_v2" / "checkpoint.json"
    if not path.exists():
        # Fail closed: no persisted checkpoint means the scheduler has not started, not
        # that it is "available with no state" -- load_checkpoint() would otherwise
        # return a synthetic default and misreport AVAILABLE.
        return _unavailable("scheduler", "checkpoint not yet created (scheduler not started)")
    try:
        from ag_scheduler_v2.scheduler import AGDailyOpportunitySchedulerV2

        checkpoint = AGDailyOpportunitySchedulerV2(checkpoint_path=str(path)).load_checkpoint()
        state = checkpoint.get("current_state")
        return RuntimeProbe(
            name="scheduler",
            status=STATUS_AVAILABLE,
            detail=f"checkpoint readable; current_state={state}",
        )
    except Exception as exc:  # noqa: BLE001
        return _unavailable("scheduler", f"error: {type(exc).__name__}")


def _probe_adapter(name: str, module_name: str) -> RuntimeProbe:
    try:
        module = importlib.import_module(module_name)
        source = getattr(module, "SOURCE_MODULE", "unknown")
        return RuntimeProbe(
            name=name,
            status=STATUS_AVAILABLE,
            detail=f"adapter importable ({source})",
        )
    except ImportError:
        return _unavailable(name, f"adapter module not importable: {module_name}")
    except Exception as exc:  # noqa: BLE001
        return _unavailable(name, f"error importing adapter: {type(exc).__name__}")


def probe_runtime(
    *,
    repo_root: Optional[Path] = None,
    api_base_url: str = DEFAULT_API_BASE_URL,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    now_utc: Optional[str] = None,
    http_get: _HttpGet = _http_get_json,
) -> RuntimeStatus:
    """Compose all bounded, read-only runtime probes into one RuntimeStatus.

    `repo_root` defaults to this repository root. No service is started here: if the
    API gateway is not running, fastapi/mt5/broker/market_data all report UNAVAILABLE
    (those three are probed through the gateway), while proposal_ledger/scheduler/ssc/
    lsmc remain independently observable from local files/imports. `http_get` is
    injectable so tests can exercise every branch without network access.
    """
    root = repo_root or Path(__file__).resolve().parents[2]

    fastapi_probe = _probe_fastapi(api_base_url, timeout, http_get=http_get)
    if fastapi_probe.status == STATUS_AVAILABLE:
        mt5_probe, broker_probe = _probe_broker_mt5(api_base_url, timeout, http_get=http_get)
        market_probe = _probe_market_data(api_base_url, timeout, http_get=http_get)
    else:
        via_gateway = "probed via API gateway; API gateway unavailable"
        mt5_probe = _unavailable("mt5", via_gateway)
        broker_probe = _unavailable("broker", via_gateway)
        market_probe = _unavailable("market_data", via_gateway)

    proposal_ledger_probe = _probe_proposal_ledger(root)
    scheduler_probe = _probe_scheduler(root)
    ssc_probe = _probe_adapter("ssc", "proposal_envelope.adapters.ssc_adapter")
    lsmc_probe = _probe_adapter("lsmc", "proposal_envelope.adapters.large_smc_research_adapter")

    return RuntimeStatus(
        checked_at_utc=now_utc or _now_utc_iso(),
        probes=(
            fastapi_probe,
            mt5_probe,
            broker_probe,
            market_probe,
            proposal_ledger_probe,
            scheduler_probe,
            ssc_probe,
            lsmc_probe,
        ),
    )


def runtime_status_as_dict(runtime_status: RuntimeStatus) -> dict:
    """JSON-friendly representation (used by scripts/generate_live_status.py --json)."""
    return asdict(runtime_status)
