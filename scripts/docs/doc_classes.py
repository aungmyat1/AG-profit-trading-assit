"""DOCS-LIVE-2 document classification rules (shared by apply_frontmatter.py and stale_check.py).

Scope: docs/**/*.md and root *.md. Front-matter keys:
  class: authority | status | design | evidence | archive   (from the path rules below)
  state: DESIGN | IMPLEMENTED | VALIDATED | AUTHORIZED
  owner_reviewed: YYYY-MM-DD | null
  review_by: YYYY-MM-DD | null

Fail-closed defaults (DOCUMENTATION_GOVERNANCE.md: never infer a stronger state):
- `state: DESIGN` until the owner reviews the document and records a stronger state;
- `owner_reviewed: null` -- no agent may claim an owner review happened;
- `review_by`: authority/status +30 days, design +90 days; evidence/archive null (immutable
  history is not re-reviewed).
EXCLUDED files stay byte-identical: generated files that a generator rewrites, raw captured
evidence, and an extracted third-party package mirrored by its zip.
"""
from __future__ import annotations

import datetime as dt
import fnmatch
from typing import Optional

CLASSES = ("authority", "status", "design", "evidence", "archive")
STATES = ("DESIGN", "IMPLEMENTED", "VALIDATED", "AUTHORIZED")
BASE_DATE = dt.date(2026, 10, 8)
REVIEW_DAYS = {"authority": 30, "status": 30, "design": 90, "evidence": None, "archive": None}

EXCLUDED = (
    "README.md",                                   # root README: front-matter renders on the repo page (owner, DOCS-LIVE-2-FIX)
    "docs/status/PROJECT_LIVE_STATUS.md",          # rewritten by scripts/generate_live_status.py
    "docs/status/evidence/*",                      # raw captured evidence (byte-for-byte)
    "docs/plans/AG_mission1_extract/*",            # extracted copy of docs/plans/AG_mission1_package.zip
)

# First matching rule wins.
RULES = (
    ("docs/archive/*", "archive"),
    ("AGENTS.md", "authority"), ("docs/README.md", "authority"),
    ("docs/DOCUMENTATION_GOVERNANCE.md", "authority"), ("docs/PROJECT_OBJECTIVE.md", "authority"),
    ("docs/PROJECT_ROADMAP.md", "authority"), ("docs/governance/*", "authority"),
    ("docs/status/LIVE_STATUS_MAINTENANCE.md", "authority"),
    ("PROJECT_STATUS.md", "status"), ("docs/PROJECT_CAPABILITY_COMPLETENESS.md", "status"),
    ("docs/VERSION_HISTORY.md", "status"), ("docs/agents/CONTEXT_PACK.md", "status"),
    ("docs/status/*", "evidence"), ("docs/validation/*", "evidence"),
    ("docs/market_intelligence/*_STATUS.md", "evidence"), ("docs/REPO_STRUCTURE_AUDIT.md", "evidence"),
    ("docs/*", "design"),
)


def is_excluded(path: str) -> bool:
    return any(fnmatch.fnmatch(path, p) for p in EXCLUDED)


def classify(path: str) -> Optional[str]:
    if is_excluded(path):
        return None
    return next((cls for pattern, cls in RULES if fnmatch.fnmatch(path, pattern)), None)


def default_frontmatter(cls: str) -> dict:
    days = REVIEW_DAYS[cls]
    return {"class": cls, "state": "DESIGN", "owner_reviewed": None,
            "review_by": (BASE_DATE + dt.timedelta(days=days)).isoformat() if days else None}
