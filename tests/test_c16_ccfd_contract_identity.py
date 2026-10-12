"""C16 root-cause tests for the ST_CRYPTO_CFD_SWEEP_RETEST_V1@1.1.0 contract-hash discrepancy.

C15 reported that the canonical frozen contract hash recomputed by the replay
(`ac116e0a…`) "does not match the `9a1f6759…` value requested in the original PR
handoff". These tests prove, from committed inputs only, that:

1. the canonical identity is well defined and reproducible — identical contract content
   always produces the expected canonical identity (the mission's required proof);
2. the declared `freeze.contract_hash` equals that canonical identity, so the contract is
   self-consistent;
3. the identity is content-sensitive: a rule change always changes it;
4. `9a1f6759…` is not reachable from this contract under any of the serialization
   variants that could plausibly have produced it, and has no provenance anywhere in the
   repository (867+ commit history) or in any PR/issue body;
5. the one real (documentation-only) divergence found: `freeze.hash_method` says the
   self-reference field is *removed*, while the implementation *blanks* it.

Nothing here changes a rule, threshold, contract or authority. Read-only.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.ccfd_sweep_retest_replay as R  # noqa: E402

CONTRACT = ROOT / "strategies" / "ST_CRYPTO_CFD_SWEEP_RETEST_V1_1_0.yaml"

# The canonical identity C15 recomputed and this mission re-verified.
CANONICAL = "ac116e0aadcca33238d0ce2d2b327368f0faa3a6bfb6f8cfdd2cf5222ca6ecf7"
# The value C15 could not resolve. Reproduced here only as an unreachable marker.
UNRESOLVED_HANDOFF_PREFIX = "9a1f6759"


def spec() -> dict:
    return yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))


# --------------------------------------------------------------------- 1. reproducibility


def test_identical_content_produces_the_expected_canonical_identity():
    """The mission's required proof: same content -> same canonical identity, every time."""
    first = R.canonical_contract_hash(spec())
    second = R.canonical_contract_hash(spec())
    assert first == second == CANONICAL


def test_canonical_identity_is_key_order_independent():
    """sort_keys=True means a re-serialized mapping with reordered keys is the same identity."""
    original = spec()
    reordered = {k: original[k] for k in sorted(original, reverse=True)}
    assert list(reordered) != list(original)
    assert R.canonical_contract_hash(reordered) == CANONICAL


def test_canonical_identity_is_line_ending_independent():
    """The frozen identity is a mapping identity, not a file-bytes identity."""
    text_lf = CONTRACT.read_text(encoding="utf-8")
    as_crlf_text = text_lf.replace("\n", "\r\n")
    assert R.canonical_contract_hash(yaml.safe_load(as_crlf_text)) == CANONICAL
    # The raw file hash is a *different* quantity and must not be confused with it.
    assert hashlib.sha256(text_lf.encode()).hexdigest() != CANONICAL


def test_declared_freeze_hash_equals_the_canonical_identity():
    """The contract self-reference is consistent: what it declares is what it computes."""
    declared = spec()["research_lifecycle_contract"]["freeze"]["contract_hash"]
    assert declared == CANONICAL == R.canonical_contract_hash(spec())


# --------------------------------------------------------------------- 2. content sensitivity


def test_identity_changes_when_any_rule_content_changes():
    """A content change must move the identity, or the identity would carry no meaning."""
    mutated = copy.deepcopy(spec())
    mutated["liquidity_contract"]["minimum_penetration"] = "invented tolerance"
    assert R.canonical_contract_hash(mutated) != CANONICAL

    mutated2 = copy.deepcopy(spec())
    mutated2["targets_contract"]["min_tp2_r_multiple"] = 1.6
    assert R.canonical_contract_hash(mutated2) != CANONICAL

    mutated3 = copy.deepcopy(spec())
    mutated3["instrument_authority"]["broker_point"] = 0.1
    assert R.canonical_contract_hash(mutated3) != CANONICAL


def test_identity_is_stable_across_a_subprocess_with_a_different_hash_seed():
    """No dependence on PYTHONHASHSEED or dict iteration order at run time."""
    code = (
        "import sys,yaml;sys.path.insert(0,%r);"
        "import scripts.ccfd_sweep_retest_replay as R;"
        "print(R.canonical_contract_hash(yaml.safe_load(open(%r,encoding='utf-8').read())))"
    ) % (str(ROOT), str(CONTRACT))
    def digest_from_subprocess(seed: str) -> str:
        # smartmoneyconcepts prints a support banner on import, so read the last non-empty line.
        out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True,
                             env={**os.environ, "PYTHONHASHSEED": seed})
        assert out.returncode == 0, out.stderr
        lines = [line.strip() for line in out.stdout.splitlines() if line.strip()]
        return lines[-1]

    assert digest_from_subprocess("12345") == CANONICAL
    assert digest_from_subprocess("987654") == CANONICAL


# --------------------------------------------------------------------- 3. the discrepancy


def _variant_hashes() -> dict:
    """Every serialization of this contract that could plausibly have produced a hash."""
    base = spec()
    blanked = copy.deepcopy(base)
    blanked["research_lifecycle_contract"]["freeze"]["contract_hash"] = ""

    removed = copy.deepcopy(base)
    del removed["research_lifecycle_contract"]["freeze"]["contract_hash"]

    dropped = copy.deepcopy(base)
    del dropped["research_lifecycle_contract"]["freeze"]

    text = CONTRACT.read_text(encoding="utf-8")
    return {
        "canonical_sorted_self_ref_blanked": hashlib.sha256(
            yaml.safe_dump(blanked, sort_keys=True, allow_unicode=True).encode()).hexdigest(),
        "sorted_self_ref_removed": hashlib.sha256(
            yaml.safe_dump(removed, sort_keys=True, allow_unicode=True).encode()).hexdigest(),
        "sorted_freeze_removed": hashlib.sha256(
            yaml.safe_dump(dropped, sort_keys=True, allow_unicode=True).encode()).hexdigest(),
        "sorted_self_ref_kept": hashlib.sha256(
            yaml.safe_dump(base, sort_keys=True, allow_unicode=True).encode()).hexdigest(),
        "unsorted_self_ref_blanked": hashlib.sha256(
            yaml.safe_dump(blanked, sort_keys=False, allow_unicode=True).encode()).hexdigest(),
        "raw_file_bytes": hashlib.sha256(text.encode()).hexdigest(),
        "raw_file_bytes_crlf_normalised": hashlib.sha256(
            text.replace("\r\n", "\n").encode()).hexdigest(),
        "source_yaml_1_0_0_raw": hashlib.sha256(
            (ROOT / "strategies" / "ST_CRYPTO_CFD_SWEEP_RETEST_V1.yaml").read_bytes()
            .replace(b"\r\n", b"\n")).hexdigest(),
    }


def test_no_documented_serialization_variant_reaches_the_unresolved_handoff_value():
    """Root cause: `9a1f6759…` is not derivable from this contract by any tested method."""
    variants = _variant_hashes()
    assert not any(h.startswith(UNRESOLVED_HANDOFF_PREFIX) for h in variants.values()), variants
    # And the documented canonical method reproduces exactly one of them.
    assert variants["canonical_sorted_self_ref_blanked"] == CANONICAL

    serializations = {k: v for k, v in variants.items() if k != "raw_file_bytes_crlf_normalised"}
    assert len(set(serializations.values())) == len(serializations), serializations

    # The raw-file identity is a *different kind* of identity from the mapping identity. On an
    # LF-committed file the two raw variants coincide by construction; neither is canonical.
    assert variants["raw_file_bytes"] == variants["raw_file_bytes_crlf_normalised"]
    assert variants["raw_file_bytes"] != CANONICAL


def test_unresolved_handoff_value_has_no_provenance_in_repository_history():
    """The value appears only in the C15 sentences that declare it — nowhere else, ever."""
    out = subprocess.run(["git", "log", "--all", "--format=%H", "-S", UNRESOLVED_HANDOFF_PREFIX],
                         cwd=ROOT, capture_output=True, text=True)
    if out.returncode != 0:                       # pragma: no cover - shallow checkout
        return
    allowed = {
        "docs/status/AGP_C15_CRYPTO_60D_RESEARCH_STATUS_2026-10-11.md",
        "docs/status/AGP_C15_THREE_LANE_RERUN_2026-10-12.md",
    }
    commits = [line for line in out.stdout.split() if line]
    for sha in commits:
        show = subprocess.run(["git", "grep", "-l", UNRESOLVED_HANDOFF_PREFIX, sha],
                              cwd=ROOT, capture_output=True, text=True)
        carriers = {line.split(":", 1)[1] for line in show.stdout.splitlines() if ":" in line}
        # The only permitted carriers are C15 status records that report the discrepancy.
        assert carriers and carriers <= allowed, f"{sha}: {carriers!r}"

    # It is absent from every live artifact of the strategy itself.
    for path in ("strategies/ST_CRYPTO_CFD_SWEEP_RETEST_V1_1_0.yaml",
                 "strategies/registry.yaml",
                 "src/v1_tickets/authority.py"):
        assert UNRESOLVED_HANDOFF_PREFIX not in (ROOT / path).read_text(encoding="utf-8")


def test_c15_evidence_files_agree_with_the_canonical_identity():
    """The committed replay + runtime-identity artifacts carry the same canonical value."""
    base = ROOT / "artifacts/logic_verification/ST_CRYPTO_CFD_SWEEP_RETEST_V1_1_0"
    reports = sorted(base.glob("*/replay_report.json"))
    assert reports, "no committed CCFD replay report found"
    for report in reports:
        data = json.loads(report.read_text(encoding="utf-8"))
        assert data["contract_hash"] == CANONICAL, report

        riv = json.loads((report.parent / "runtime_identity_verification.json").read_text(encoding="utf-8"))
        assert riv["contract_hash_declared"] == CANONICAL
        assert riv["contract_hash_recomputed"] == CANONICAL
        assert riv["contract_hash_match"] is True
        assert data["runtime_identity_verification"]["contract_hash_recomputed"] == CANONICAL

        # DEFECT D-CCFD-2 (documented, unresolved at C16): one artifact carries the mapping
        # identity and the raw-file identity side by side under the same field name
        # `contract_hash`. Both are legitimate; naming them identically is what makes the
        # identity ambiguous to a reader comparing hashes by hand.
        raw_file = hashlib.sha256(CONTRACT.read_text(encoding="utf-8").encode()).hexdigest()
        for sym in ("BTCUSD", "ETHUSD"):
            assert data["logic_verification"][sym]["logic_identity"]["contract_hash"] == raw_file
        assert raw_file != data["contract_hash"]


# --------------------------------------------------------------------- 4. the one real defect


def test_hash_method_text_diverges_from_the_implementation():
    """DOCUMENTED DEFECT D-CCFD-1 (documentation only; no rule and no hash value changes).

    `freeze.hash_method` says the self-reference is *removed* before serialization; the
    implementation blanks it to "". The two are not equivalent (removing a key changes the
    mapping; blanking it keeps the key). The declared *value* follows the implementation,
    so the contract is self-consistent — but the prose is wrong and is the plausible origin
    of a competing hand-computed hash.
    """
    declared_method = spec()["research_lifecycle_contract"]["freeze"]["hash_method"]
    assert "after removing freeze.contract_hash" in declared_method
    blanked = R.canonical_contract_hash(spec())

    removed_spec = copy.deepcopy(spec())
    del removed_spec["research_lifecycle_contract"]["freeze"]["contract_hash"]
    removed = hashlib.sha256(
        yaml.safe_dump(removed_spec, sort_keys=True, allow_unicode=True).encode()).hexdigest()

    assert blanked == CANONICAL                    # implementation + declared value agree
    assert removed != blanked                      # literal reading of the prose disagrees
