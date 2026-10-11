"""Domain-aware crypto command journal (spec item 7). Follows the SAME two established
conventions this repo already uses for command safety-state, rather than inventing a
third:

  1. Atomic, cross-process, restart-safe claim files via os.O_CREAT | os.O_EXCL -- the
     exact pattern execution/journal.py::claim_command() already uses for FX commands
     (verified by reading that file). Re-implemented here (not imported) because FX's
     claim_command() is keyed by command_id ALONE, which is exactly the collision this
     module exists to avoid -- see _safety_key() below.
  2. Append-only per-command event log -- same shape as execution/journal.py's
     record_event()/read_events(), one JSON object per line, never rewritten.

Composite safety-context key: every claim/record/read in this module is keyed by
(execution_domain, account_environment, command_id) -- NEVER command_id alone. This is
deliberate: a command_id literal string reused across FX-DEMO and BINANCE_USDTM-DEMO (or
DEMO vs REAL within the same domain) must never be treated as the same claim or the same
journal history. See tests/test_crypto_journal.py for the isolation proof.

Recorded fields (spec item 7): command_id, execution_domain, account_environment, symbol,
side, quantity, order_type, validation_state, exchange_order_id (nullable), timestamps,
result. NEVER any credential/signature field -- this module never reads or stores an API
key, secret, or signature, and never touches the process environment or a dotenv file.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import List, Optional

from execution.crypto_models import CryptoTradeCommand

DEFAULT_BASE_DIR = "journal"
_EVENT_CLAIMED = "CRYPTO_COMMAND_CLAIMED"
_EVENT_RECORDED = "CRYPTO_COMMAND_RECORDED"


def _safety_key(execution_domain: str, account_environment: str, command_id: str) -> str:
    """The ONE composite identity every function in this module keys off of. Never expose
    a code path that keys off command_id alone."""
    return f"{execution_domain}:{account_environment}:{command_id}"


def _digest(execution_domain: str, account_environment: str, command_id: str) -> str:
    return hashlib.sha256(_safety_key(execution_domain, account_environment, command_id).encode("utf-8")).hexdigest()


def _claim_path(execution_domain: str, account_environment: str, command_id: str, base_dir: str) -> str:
    digest = _digest(execution_domain, account_environment, command_id)
    return os.path.join(base_dir, f"crypto_execution_{digest}.claim")


def _journal_path(execution_domain: str, account_environment: str, command_id: str, base_dir: str) -> str:
    digest = _digest(execution_domain, account_environment, command_id)
    return os.path.join(base_dir, f"crypto_execution_{digest}.jsonl")


def claim_command(
    execution_domain: str, account_environment: str, command_id: str, base_dir: str = DEFAULT_BASE_DIR,
) -> bool:
    """Atomically reserve one (execution_domain, account_environment, command_id) triple.
    Returns False if that exact triple is already claimed -- the SAME command_id claimed
    under a different domain/environment is a DIFFERENT claim and succeeds independently
    (see test_crypto_journal.py::test_same_command_id_different_domain_is_not_confused)."""
    os.makedirs(base_dir, exist_ok=True)
    path = _claim_path(execution_domain, account_environment, command_id, base_dir)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "execution_domain": execution_domain,
        "account_environment": account_environment,
        "command_id": command_id,
        "state": "CLAIMED",
    }
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())
    return True


def is_claimed(execution_domain: str, account_environment: str, command_id: str, base_dir: str = DEFAULT_BASE_DIR) -> bool:
    return os.path.exists(_claim_path(execution_domain, account_environment, command_id, base_dir))


def record_event(
    execution_domain: str, account_environment: str, command_id: str, event: str,
    base_dir: str = DEFAULT_BASE_DIR, **payload,
) -> None:
    """Append-only. Rejects (raises) rather than silently accepting any key literally
    named 'api_key', 'secret', 'signature', or 'password' in payload -- belt-and-suspenders
    against a future caller accidentally journaling a credential."""
    _forbidden = {"api_key", "apikey", "secret", "signature", "password"}
    lowered = {str(k).lower() for k in payload}
    leaked = lowered & _forbidden
    if leaked:
        raise ValueError(f"refusing to journal forbidden credential-shaped field(s): {sorted(leaked)}")

    os.makedirs(base_dir, exist_ok=True)
    path = _journal_path(execution_domain, account_environment, command_id, base_dir)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "execution_domain": execution_domain,
        "account_environment": account_environment,
        "command_id": command_id,
        "event": event,
    }
    entry.update(payload)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True, default=str) + "\n")


def read_events(
    execution_domain: str, account_environment: str, command_id: str, base_dir: str = DEFAULT_BASE_DIR,
) -> List[dict]:
    path = _journal_path(execution_domain, account_environment, command_id, base_dir)
    if not os.path.exists(path):
        return []
    events = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def record_command(
    command: CryptoTradeCommand, *, validation_state: str,
    exchange_order_id: Optional[str] = None, result: Optional[str] = None,
    base_dir: str = DEFAULT_BASE_DIR,
) -> None:
    """Convenience wrapper: records one CryptoTradeCommand's current state, using its own
    execution_domain/account_environment/command_id as the safety-context key. Only the
    fields spec item 7 names are ever written -- never sl/tp price fields duplicated as a
    second source of truth, never anything credential-shaped."""
    record_event(
        command.execution_domain, command.account_environment, command.command_id,
        _EVENT_RECORDED, base_dir=base_dir,
        symbol=command.symbol, side=command.side, quantity=command.quantity,
        order_type=command.order_type, client_order_id=command.client_order_id,
        validation_state=validation_state, exchange_order_id=exchange_order_id, result=result,
    )
