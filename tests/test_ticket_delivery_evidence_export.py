"""Tests for scripts/ticket_delivery_evidence.py -- the runtime-journal evidence
export/restore-verification capability (AG_STAGE1_GOVERNANCE_RECONCILIATION_AND_WP7_PREFLIGHT_V1
M0C). Never touches the real journal/ticket_delivery/ directory -- every test builds
its own synthetic source directory under tmp_path.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "ticket_delivery_evidence.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("ticket_delivery_evidence_under_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def ev(monkeypatch):
    module = _load_module()
    return module


def _make_source(tmp_path, files):
    source = tmp_path / "journal_source"
    for rel, content in files.items():
        p = source / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return source


def test_export_creates_manifest_with_correct_sha256_and_size(tmp_path, ev):
    source = _make_source(tmp_path, {"archive/a.json": '{"x": 1}', "state/records.json": "{}"})
    export_dir = ev.export(source_dir=source, export_root=tmp_path / "exports")
    manifest = json.loads((export_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["file_count"] == 2
    for entry in manifest["files"]:
        exported = export_dir / entry["export_path"]
        assert exported.exists()
        assert entry["size_bytes"] == exported.stat().st_size
        assert entry["sha256"] == ev._sha256_of(exported)


def test_export_never_mutates_the_source_directory(tmp_path, ev):
    source = _make_source(tmp_path, {"archive/a.json": '{"x": 1}'})
    original_content = (source / "archive" / "a.json").read_bytes()
    ev.export(source_dir=source, export_root=tmp_path / "exports")
    assert (source / "archive" / "a.json").read_bytes() == original_content
    # Only the one file exists in source -- export created nothing new there.
    assert sum(1 for _ in source.rglob("*") if _.is_file()) == 1


def test_export_fails_closed_on_missing_source_directory(tmp_path, ev):
    with pytest.raises(ev.EvidenceExportError):
        ev.export(source_dir=tmp_path / "does_not_exist", export_root=tmp_path / "exports")


def test_export_fails_closed_on_empty_source_directory(tmp_path, ev):
    empty = tmp_path / "empty_source"
    empty.mkdir()
    with pytest.raises(ev.EvidenceExportError):
        ev.export(source_dir=empty, export_root=tmp_path / "exports")


def test_export_manifest_carries_provenance_fields(tmp_path, ev):
    source = _make_source(tmp_path, {"archive/a.json": "{}"})
    export_dir = ev.export(source_dir=source, export_root=tmp_path / "exports")
    manifest = json.loads((export_dir / "manifest.json").read_text(encoding="utf-8"))
    for key in ("export_id", "export_timestamp_utc", "application_release", "repository_head", "ticket_delivery"):
        assert key in manifest
    assert "policy" in manifest["ticket_delivery"]


def test_export_never_contains_secret_looking_fields(tmp_path, ev):
    source = _make_source(tmp_path, {"archive/a.json": "{}"})
    export_dir = ev.export(source_dir=source, export_root=tmp_path / "exports")
    manifest_text = (export_dir / "manifest.json").read_text(encoding="utf-8")
    assert "TELEGRAM_BOT_TOKEN" not in manifest_text
    assert "bot_token" not in manifest_text.lower()


def test_verify_restore_passes_on_an_uncorrupted_export(tmp_path, ev):
    source = _make_source(tmp_path, {"archive/a.json": '{"x": 1}', "state/records.json": "{}"})
    export_dir = ev.export(source_dir=source, export_root=tmp_path / "exports")
    result = ev.verify_restore(export_dir)
    assert result["passed"] is True
    assert result["file_count"] == 2
    assert result["checksum_mismatches"] == []
    assert result["missing_files"] == []


def test_verify_restore_never_writes_into_the_original_export_or_source(tmp_path, ev):
    source = _make_source(tmp_path, {"archive/a.json": '{"x": 1}'})
    export_dir = ev.export(source_dir=source, export_root=tmp_path / "exports")
    before = {p: p.read_bytes() for p in export_dir.rglob("*") if p.is_file()}
    ev.verify_restore(export_dir)
    after = {p: p.read_bytes() for p in export_dir.rglob("*") if p.is_file()}
    assert before == after


def test_verify_restore_uses_an_isolated_temp_directory_by_default(tmp_path, ev):
    source = _make_source(tmp_path, {"archive/a.json": "{}"})
    export_dir = ev.export(source_dir=source, export_root=tmp_path / "exports")
    result = ev.verify_restore(export_dir)
    restore_dir = Path(result["restore_dir"])
    assert str(restore_dir) != str(export_dir)
    assert str(restore_dir) != str(source)
    # Cleaned up afterward (cleanup_temp=True path).
    assert not restore_dir.exists()


def test_verify_restore_detects_a_corrupted_exported_file(tmp_path, ev):
    source = _make_source(tmp_path, {"archive/a.json": '{"x": 1}'})
    export_dir = ev.export(source_dir=source, export_root=tmp_path / "exports")
    exported_file = next((export_dir / "files").rglob("*.json"))
    exported_file.write_text("CORRUPTED", encoding="utf-8")

    result = ev.verify_restore(export_dir)
    assert result["passed"] is False
    assert len(result["checksum_mismatches"]) == 1


def test_verify_restore_detects_a_missing_exported_file(tmp_path, ev):
    source = _make_source(tmp_path, {"archive/a.json": '{"x": 1}'})
    export_dir = ev.export(source_dir=source, export_root=tmp_path / "exports")
    exported_file = next((export_dir / "files").rglob("*.json"))
    exported_file.unlink()

    result = ev.verify_restore(export_dir)
    assert result["passed"] is False
    assert len(result["missing_files"]) == 1


def test_verify_restore_reports_missing_manifest(tmp_path, ev):
    empty_export = tmp_path / "no_manifest_here"
    empty_export.mkdir()
    result = ev.verify_restore(empty_export)
    assert result["passed"] is False
    assert result["reason"] == "MANIFEST_MISSING"


def test_repeated_export_at_the_same_timestamp_never_overwrites_a_prior_export(tmp_path, ev, monkeypatch):
    """Immutability: two export() calls that resolve to the identical timestamped
    directory name (forced here by freezing the module's clock) must never silently
    overwrite each other -- the second call raises, and the first export's files are
    untouched."""
    import datetime as real_datetime

    class _FrozenDatetime(real_datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime.datetime(2026, 9, 8, 9, 0, 0, 0, tzinfo=tz)

    monkeypatch.setattr(ev, "datetime", _FrozenDatetime)

    source = _make_source(tmp_path, {"archive/a.json": '{"x": 1}'})
    export_root = tmp_path / "exports"
    first = ev.export(source_dir=source, export_root=export_root)
    first_file_content = next((first / "files").rglob("*.json")).read_bytes()

    with pytest.raises(ev.EvidenceExportError):
        ev.export(source_dir=source, export_root=export_root)

    # The first export's content is untouched by the failed second attempt.
    assert next((first / "files").rglob("*.json")).read_bytes() == first_file_content


def test_no_real_network_calls_anywhere_in_this_module():
    import inspect

    module = _load_module()
    source = inspect.getsource(module)
    for forbidden in ("requests.", "urllib.request", "socket.socket", "http.client"):
        assert forbidden not in source
