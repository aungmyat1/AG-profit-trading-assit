"""Subprocess helper for tests/test_instrument_registry_v1.py cwd-determinism tests.

Usage: python _cwd_envelope_probe.py <target_cwd>

Imports happen at the repository root: the platform's fx_opportunity package (reached
through the frozen trade_ticket) loads its instrument contract from a cwd-relative path at
IMPORT time -- a pre-existing platform property outside WP-7A. The registry-dependent
OPERATIONS (resolve_identity, envelope_for_ticket) then run after chdir to <target_cwd>.
"""
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
os.chdir(REPO)
sys.path[:0] = [str(REPO), str(REPO / "src"), str(REPO / "tests")]

import test_instrument_registry_v1 as t  # noqa: E402
from instrument_registry.gates import envelope_for_ticket  # noqa: E402

ticket = t.frozen_ticket()
os.chdir(sys.argv[1])
res = t.resolve()
env, reasons = envelope_for_ticket(ticket, res)
print(json.dumps({
    "status": res.status,
    "registry_version": res.registry_version,
    "identity_fingerprint": res.identity_fingerprint,
    "metadata_fingerprint": res.metadata_fingerprint,
    "envelope": None if env is None else env.__dict__,
    "reasons": list(reasons),
}, sort_keys=True))
