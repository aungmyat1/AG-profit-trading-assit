"""Read-only loader for the FROZEN ST_SESSION_SWEEP_CONTINUATION_V1 v1.0.1 engine.

`src/session_sweep_continuation/` was removed from `main` by commit 3f1f955
("feat: initialize project structure"). The frozen engine therefore lives only in git
history. This module materializes that exact tree (pinned commit + verified git tree
hash) into a private cache directory and imports it. It never edits, copies into the
repository, or re-implements any rule.

Must run in its own process: the materialized `src/` is prepended to `sys.path` and
would shadow the current `src/` packages of the same name.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# Parent of 3f1f955 -- the last commit containing the frozen v1.0.1 engine.
FROZEN_COMMIT = "2b75bbf0d290cbf3b52684f87770396442790639"
FROZEN_ENGINE_TREE = "a11a9e49d4d4932191eac9217cf279cf52ec6700"  # src/session_sweep_continuation
FROZEN_CONFIG_BLOB = "2ad318c4e1da07b577b3b0c5a775cd552feaccd9"  # strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml
STRATEGY_ID = "ST_SESSION_SWEEP_CONTINUATION_V1"
STRATEGY_VERSION = "1.0.1"
CONFIG_PATH = os.path.join("strategies", "ST_SESSION_SWEEP_CONTINUATION_V1.yaml")


class FrozenEngineError(Exception):
    """Fail closed: the frozen engine cannot be proven byte-identical."""


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, check=True, capture_output=True,
                          text=True).stdout.strip()


def semantic_check() -> dict:
    """Verifies engine tree + config blob against the pinned hashes. Never raises;
    returns a PASS/FAIL record for the admission report."""
    record = {"frozen_commit": FROZEN_COMMIT, "strategy_id": STRATEGY_ID,
              "strategy_version": STRATEGY_VERSION}
    try:
        engine_tree = _git("rev-parse", f"{FROZEN_COMMIT}:src/session_sweep_continuation")
        frozen_cfg = _git("rev-parse", f"{FROZEN_COMMIT}:{CONFIG_PATH}")
        current_cfg = _git("hash-object", CONFIG_PATH)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        return {**record, "status": "FAIL", "reason": f"FROZEN_COMMIT_UNAVAILABLE: {exc}"}
    record.update(engine_tree=engine_tree, frozen_config_blob=frozen_cfg,
                  current_config_blob=current_cfg)
    if engine_tree != FROZEN_ENGINE_TREE:
        return {**record, "status": "FAIL", "reason": "ENGINE_TREE_HASH_MISMATCH"}
    if not (frozen_cfg == current_cfg == FROZEN_CONFIG_BLOB):
        return {**record, "status": "FAIL", "reason": "CONFIG_BLOB_MISMATCH"}
    return {**record, "status": "PASS", "reason": "ENGINE_AND_CONFIG_BYTE_IDENTICAL"}


def materialize(cache_root: str | None = None) -> str:
    """Extracts the frozen `src/` tree once per commit; returns the extracted src dir."""
    check = semantic_check()
    if check["status"] != "PASS":
        raise FrozenEngineError(check["reason"])
    root = os.path.join(cache_root or tempfile.gettempdir(), f"ag_frozen_ssc_{FROZEN_COMMIT[:12]}")
    src = os.path.join(root, "src")
    if not os.path.isdir(os.path.join(src, "session_sweep_continuation")):
        os.makedirs(root, exist_ok=True)
        archive = subprocess.run(["git", "archive", FROZEN_COMMIT, "src"], cwd=REPO_ROOT,
                                 check=True, capture_output=True).stdout
        subprocess.run(["tar", "-x", "-C", root], input=archive, check=True)
    return src


def load(cache_root: str | None = None):
    """Imports and returns the frozen `session_sweep_continuation.replay` module."""
    src = materialize(cache_root)
    for path in (REPO_ROOT, src):  # REPO_ROOT supplies the offline MetaTrader5 stub only
        if path not in sys.path:
            sys.path.insert(0, path)
    import session_sweep_continuation.replay as replay  # noqa: E402

    if os.path.dirname(os.path.dirname(replay.__file__)) != src:
        raise FrozenEngineError("imported engine is not the materialized frozen tree")
    return replay


def load_config() -> dict:
    import yaml

    with open(os.path.join(REPO_ROOT, CONFIG_PATH), "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)
