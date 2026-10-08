from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.docs.check_generated_files import classify
from scripts.docs.generated_files import GENERATED_FILES, normalize_line_endings


def test_generated_file_scope_is_exactly_the_four_authority_outputs():
    assert GENERATED_FILES == (
        "PROJECT_STATUS.md",
        "docs/status/PROJECT_LIVE_STATUS.md",
        "status/facts.json",
        "docs/agents/CONTEXT_PACK.md",
    )


def test_markdown_fingerprint_only_difference_is_warning():
    original = "# Report\ninputs_sha256: `" + "a" * 64 + "`.\nContent\n"
    regenerated = "# Report\ninputs_sha256: `" + "b" * 64 + "`.\nContent\n"
    assert classify("PROJECT_STATUS.md", original, regenerated) == "FINGERPRINT_ONLY"


def test_json_fingerprint_only_difference_is_warning():
    original = json.dumps({"inputs_sha256": "a" * 64, "content": [1, 2]})
    regenerated = json.dumps({"inputs_sha256": "b" * 64, "content": [1, 2]})
    assert classify("status/facts.json", original, regenerated) == "FINGERPRINT_ONLY"


def test_generated_content_difference_stays_blocking():
    original = "# Report\ninputs_sha256: `" + "a" * 64 + "`.\nContent\n"
    regenerated = "# Report\ninputs_sha256: `" + "b" * 64 + "`.\nChanged content\n"
    assert classify("docs/agents/CONTEXT_PACK.md", original, regenerated) == "CONTENT_STALE"


def test_identical_generated_file_is_fresh():
    content = "# Report\n"
    assert classify("docs/status/PROJECT_LIVE_STATUS.md", content, content) == "FRESH"


def test_generated_file_normalization_writes_lf_bytes(tmp_path: Path):
    path = tmp_path / "report.md"
    path.write_bytes(b"one\r\ntwo\r\n")
    assert normalize_line_endings(path) is True
    assert path.read_bytes() == b"one\ntwo\n"
    assert normalize_line_endings(path) is False
