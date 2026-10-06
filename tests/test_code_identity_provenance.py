"""code_sha provenance on scan records, archived manual tickets and delivery-status lines.
Resolution never raises; "UNKNOWN" never blocks scanning. Offline, no MT5."""
from __future__ import annotations

import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

import pytest

from v1_tickets import code_identity, manual_ticket as mt
from v1_tickets.scan_record import read_jsonl, scan_path

from test_manual_ticket_build import manual  # noqa: E402  (recorded-session fixture)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "host"))
import live_candles_smoke as smoke  # noqa: E402

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 6, 8, 0, tzinfo=UTC)
SHA = re.compile(r"[0-9a-f]{40}")


@pytest.fixture(autouse=True)
def _no_repo_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("AG_EVIDENCE_ROOT", str(tmp_path / "no_evidence"))


def _all_records(journal: Path):
    scans = read_jsonl(scan_path(str(journal), NOW.date()))
    delivery = read_jsonl(str(journal / smoke.DELIVERY_DIR / f"{NOW.date().isoformat()}.jsonl"))
    return scans, delivery


def test_resolved_sha_is_a_full_git_sha_or_unknown():
    sha = code_identity.resolve_code_sha()
    assert sha == code_identity.UNKNOWN or SHA.fullmatch(sha)
    assert code_identity.code_sha() == code_identity.CODE_SHA


def test_field_present_on_scan_record_manual_ticket_and_delivery_line(tmp_path, monkeypatch):
    monkeypatch.setattr(code_identity, "CODE_SHA", "a" * 40)
    journal = tmp_path / "j"
    monkeypatch.setattr(smoke.tg, "should_send", lambda *a, **k: False)
    smoke._notify("TICKET", "READY", "text", ".", journal=str(journal), ref="x", now=NOW)
    smoke.run_fx(lambda *a: [], NOW, str(journal), gated=False, notify=False)
    scans, delivery = _all_records(journal)
    assert scans and all(r["code_sha"] == "a" * 40 for r in scans)
    assert delivery and all(r["code_sha"] == "a" * 40 for r in delivery)
    t = manual()
    path = mt.archive_manual_ticket(str(journal), t)
    stored = read_jsonl(path)[-1]
    assert stored["code_sha"] == "a" * 40
    assert stored["content_hash"] == mt.content_hash(t)            # provenance is outside the content hash


@pytest.mark.parametrize("failure", [FileNotFoundError("git"), subprocess.TimeoutExpired("git", 5), OSError("x")])
def test_git_failure_resolves_unknown_and_never_raises(monkeypatch, failure):
    def boom(*a, **k):
        raise failure
    monkeypatch.setattr(code_identity.subprocess, "run", boom)
    assert code_identity.resolve_code_sha() == code_identity.UNKNOWN


@pytest.mark.parametrize("stdout", ["", "fatal: not a git repository", "abc123", "A" * 40])
def test_non_sha_output_resolves_unknown(monkeypatch, stdout):
    monkeypatch.setattr(code_identity.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 128, stdout=stdout, stderr=""))
    assert code_identity.resolve_code_sha() == code_identity.UNKNOWN


def test_unknown_sha_does_not_block_scanning(tmp_path, monkeypatch):
    known, unknown = tmp_path / "known", tmp_path / "unknown"
    monkeypatch.setattr(code_identity, "CODE_SHA", "b" * 40)
    smoke.run_fx(lambda *a: [], NOW, str(known), gated=False, notify=False)
    monkeypatch.setattr(code_identity, "CODE_SHA", code_identity.UNKNOWN)
    smoke.run_fx(lambda *a: [], NOW, str(unknown), gated=False, notify=False)
    a, b = read_jsonl(scan_path(str(known), NOW.date())), read_jsonl(scan_path(str(unknown), NOW.date()))
    assert len(b) == len(a) > 0 and all(r["code_sha"] == "UNKNOWN" for r in b)
    strip = lambda rows: [{k: v for k, v in r.items() if k != "code_sha"} for r in rows]  # noqa: E731
    assert strip(a) == strip(b)                                   # same records, only provenance differs
    t = manual()
    assert read_jsonl(mt.archive_manual_ticket(str(unknown), t))[-1]["code_sha"] == "UNKNOWN"
