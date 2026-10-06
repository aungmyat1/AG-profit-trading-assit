"""Code provenance for scan records, manual tickets and delivery-status lines.

`CODE_SHA` is `git rev-parse HEAD` of this checkout, resolved once when the process starts
(first import). Any failure -- no git, not a checkout, timeout, odd output -- gives
"UNKNOWN". Resolution never raises, so it can never stop a scan.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

UNKNOWN = "UNKNOWN"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SHA = re.compile(r"[0-9a-f]{40}")


def resolve_code_sha(root: Path = _REPO_ROOT) -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(root), capture_output=True, text=True,
                             timeout=5, check=False).stdout.strip()
    except Exception:  # noqa: BLE001 -- provenance is best-effort, never fatal
        return UNKNOWN
    return out if _SHA.fullmatch(out) else UNKNOWN


CODE_SHA = resolve_code_sha()


def code_sha() -> str:
    return CODE_SHA
