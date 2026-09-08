"""AG_STAGE1_GOVERNANCE_RECONCILIATION_AND_WP7_PREFLIGHT_V1 -- minimal, safe evidence
export/restore-verification for the ticket_delivery runtime journal.

`journal/ticket_delivery/` (archive + delivery state) is intentionally .gitignored --
Git is not the evidence-retention layer for mutable runtime state. This script is the
smallest safe capability that turns that mutable state into a point-in-time IMMUTABLE
export with a SHA-256 manifest, without ever mutating the live journal, plus a
restore-verification path that never writes into production state.

Read-only relative to the source journal; never sends network requests; never reads or
persists any secret (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID are never inspected here).

Usage:
    python scripts/ticket_delivery_evidence.py export
    python scripts/ticket_delivery_evidence.py verify-restore <export_dir>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE_DIR = REPO_ROOT / "journal" / "ticket_delivery"
DEFAULT_EXPORT_ROOT = REPO_ROOT / "artifacts" / "ticket_delivery_evidence_exports"
CONFIG_PATH = REPO_ROOT / "config" / "ticket_delivery.yaml"

MANIFEST_NAME = "manifest.json"


class EvidenceExportError(Exception):
    """Raised on any condition that would otherwise produce a partial/corrupt export.
    export() always cleans up a partially-written export directory before re-raising or
    returning a failure -- there is no code path that leaves a half-written export on
    disk."""


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_head() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip() if out.returncode == 0 else "UNKNOWN"
    except Exception:  # noqa: BLE001 -- evidence metadata only, never blocks the export itself
        return "UNKNOWN"


def _release_id() -> str:
    try:
        raw = yaml.safe_load((REPO_ROOT / "config" / "releases" / "AG_TRADE_ASSISTANT_V1_0_3.yaml").read_text(encoding="utf-8"))
        return raw.get("release_id", "UNKNOWN")
    except Exception:  # noqa: BLE001 -- evidence metadata only
        return "UNKNOWN"


def _ticket_delivery_config_summary() -> Dict[str, Any]:
    """Mode + policy VALUES only -- never any secret (this config file has never held
    one; TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID live in environment variables, not here,
    and this function does not read the environment at all)."""
    try:
        raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001 -- evidence metadata only
        return {"mode": "UNKNOWN", "policy": None}
    return {"mode": raw.get("mode", "UNKNOWN"), "policy": raw.get("policy")}


def export(source_dir: Path = DEFAULT_SOURCE_DIR, export_root: Path = DEFAULT_EXPORT_ROOT) -> Path:
    """Creates ONE new, immutable, timestamped export directory under `export_root`
    containing a byte-for-byte copy of every file currently under `source_dir`, plus a
    manifest.json with provenance + a SHA-256 + size per file. Fails closed (raises
    EvidenceExportError, removes any partial export) if the source directory is
    missing, empty, or any individual file cannot be read mid-walk -- never produces a
    manifest describing files that were not actually, verifiably copied."""
    if not source_dir.exists():
        raise EvidenceExportError(f"source directory does not exist: {source_dir}")

    source_files = sorted(p for p in source_dir.rglob("*") if p.is_file())
    if not source_files:
        raise EvidenceExportError(f"source directory contains no files -- refusing to write an empty, misleading export: {source_dir}")

    export_ts = datetime.now(timezone.utc)
    export_dir_name = export_ts.strftime("%Y%m%dT%H%M%S%fZ")
    export_dir = export_root / export_dir_name
    if export_dir.exists():
        raise EvidenceExportError(f"export directory already exists (would violate immutability): {export_dir}")

    files_dir = export_dir / "files"
    entries: List[Dict[str, Any]] = []
    try:
        files_dir.mkdir(parents=True, exist_ok=False)
        for src in source_files:
            rel = src.relative_to(source_dir)
            dest = files_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(src, dest)
                sha256 = _sha256_of(dest)
                size = dest.stat().st_size
            except OSError as exc:
                raise EvidenceExportError(f"failed to read/copy source file {src}: {exc}") from exc
            entries.append({
                "source_path": str(rel).replace("\\", "/"), "export_path": str((Path("files") / rel)).replace("\\", "/"),
                "size_bytes": size, "sha256": sha256,
            })

        manifest = {
            "export_id": export_dir_name,
            "export_timestamp_utc": export_ts.isoformat(),
            "application_release": _release_id(),
            "repository_head": _git_head(),
            "source_root": str(source_dir),
            "ticket_delivery": _ticket_delivery_config_summary(),
            "file_count": len(entries),
            "files": entries,
        }
        (export_dir / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    except Exception:
        if export_dir.exists():
            shutil.rmtree(export_dir, ignore_errors=True)
        raise

    return export_dir


def verify_restore(export_dir: Path, restore_into: Path = None) -> Dict[str, Any]:
    """Restores an export into an ISOLATED temporary directory (never the live
    journal), recomputes every file's SHA-256, and compares against the manifest.
    Returns a result dict with an overall `passed` bool and itemized mismatches --
    never mutates `export_dir` or any production runtime state."""
    manifest_path = export_dir / MANIFEST_NAME
    if not manifest_path.exists():
        return {"passed": False, "reason": "MANIFEST_MISSING", "export_dir": str(export_dir)}

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cleanup_temp = restore_into is None
    restore_dir = restore_into or Path(tempfile.mkdtemp(prefix="ag_ticket_delivery_restore_"))

    mismatches: List[Dict[str, Any]] = []
    missing: List[str] = []
    try:
        for entry in manifest["files"]:
            src = export_dir / entry["export_path"]
            dst = restore_dir / entry["source_path"]
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not src.exists():
                missing.append(entry["export_path"])
                continue
            shutil.copy2(src, dst)
            actual_sha256 = _sha256_of(dst)
            actual_size = dst.stat().st_size
            if actual_sha256 != entry["sha256"] or actual_size != entry["size_bytes"]:
                mismatches.append({
                    "source_path": entry["source_path"], "expected_sha256": entry["sha256"],
                    "actual_sha256": actual_sha256, "expected_size": entry["size_bytes"], "actual_size": actual_size,
                })
        passed = not mismatches and not missing
        return {
            "passed": passed, "export_dir": str(export_dir), "restore_dir": str(restore_dir),
            "file_count": manifest["file_count"], "missing_files": missing, "checksum_mismatches": mismatches,
        }
    finally:
        if cleanup_temp:
            shutil.rmtree(restore_dir, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ticket-delivery runtime evidence export/restore-verify")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("export")
    verify_parser = sub.add_parser("verify-restore")
    verify_parser.add_argument("export_dir", type=Path)
    args = parser.parse_args()

    if args.command == "export":
        try:
            path = export()
        except EvidenceExportError as exc:
            print(f"EVIDENCE_EXPORT_FAILED: {exc}", file=sys.stderr)
            sys.exit(1)
        print(json.dumps({"export_dir": str(path)}, indent=2))
    elif args.command == "verify-restore":
        result = verify_restore(args.export_dir)
        print(json.dumps(result, indent=2, default=str))
        sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
