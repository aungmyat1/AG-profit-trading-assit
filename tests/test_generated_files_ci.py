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


# AGP-REGEN-R5.1: CI generated-file policy (source PR vs regeneration PR vs accidental drift).
from scripts.docs.check_generated_files import decide  # noqa: E402

BASE = "b" * 40
STALE = {"PROJECT_STATUS.md": "FRESH", "docs/status/PROJECT_LIVE_STATUS.md": "FRESH",
         "status/facts.json": "CONTENT_STALE", "docs/agents/CONTEXT_PACK.md": "CONTENT_STALE"}
FRESH = {path: "FRESH" for path in GENERATED_FILES}


def test_source_pr_changing_generator_inputs_is_not_blocked():
    # Previously deadlocked: the source PR could only go green by committing outputs itself.
    failures, warnings = decide("pr", STALE, {"docs/governance/OWNER_DECISION_REGISTER.md"}, "feature/x", BASE)
    assert failures == []
    assert any("REGEN_REQUIRED_AFTER_MERGE" in w for w in warnings)
    assert decide("strict", STALE, set(), "", None)[0]  # the old single policy failed here


def test_accidental_hand_edit_of_an_output_fails_closed():
    failures, _ = decide("pr", STALE, {"status/facts.json", "src/app.py"}, "feature/x", BASE)
    assert failures == ["status/facts.json: changed by this PR but differs from the generators (CONTENT_STALE)"]
    fingerprint = {**FRESH, "status/facts.json": "FINGERPRINT_ONLY"}
    assert decide("pr", fingerprint, {"status/facts.json"}, "feature/x", BASE)[0]


def test_source_pr_that_regenerates_its_outputs_exactly_passes():
    assert decide("pr", FRESH, {"status/facts.json", "strategies/registry.yaml"}, "feature/x", BASE) == ([], [])


def test_regeneration_pr_requires_exact_parity_current_base_and_only_outputs():
    branch = "regen/generated-files-" + BASE
    assert decide("pr", FRESH, {"status/facts.json"}, branch, BASE) == ([], [])
    assert any("REGEN_PR_NOT_EXACT" in f for f in decide("pr", STALE, {"status/facts.json"}, branch, BASE)[0])
    assert any("REGEN_PR_STALE" in f for f in decide("pr", FRESH, {"status/facts.json"}, branch, "c" * 40)[0])
    assert any("REGEN_PR_UNEXPECTED_PATH: src/app.py" in f
               for f in decide("pr", FRESH, {"status/facts.json", "src/app.py"}, branch, BASE)[0])
    assert any("REGEN_PR_BRANCH_INVALID" in f
               for f in decide("pr", FRESH, set(), "regen/generated-files-xyz", BASE)[0])


def test_strict_dispatch_and_advisory_push_modes():
    assert decide("strict", FRESH, set(), "", None) == ([], [])
    assert len(decide("strict", STALE, set(), "", None)[0]) == 2
    failures, warnings = decide("advisory", STALE, set(), "", None)
    assert failures == [] and len(warnings) == 2


def test_ci_selects_policy_by_event():
    import yaml
    ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    job = ci["jobs"]["docs-drift"]
    assert job["steps"][0]["with"]["fetch-depth"] == 2
    gate = next(step for step in job["steps"] if step.get("name") == "Generated-file policy gate")["run"]
    assert "pull_request) python scripts/docs/check_generated_files.py --mode pr" in gate
    assert "workflow_dispatch) python scripts/docs/check_generated_files.py --mode strict" in gate
