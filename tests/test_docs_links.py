from __future__ import annotations

from pathlib import Path

from scripts import check_docs_links as checker


def test_normalize_target_ignores_non_relative_links_and_strips_metadata() -> None:
    assert checker.normalize_target("https://example.com/doc") is None
    assert checker.normalize_target("#section") is None
    assert checker.normalize_target("file.md#section") == "file.md"
    assert checker.normalize_target("<file%20name.md> \"title\"") == "file name.md"


def test_broken_relative_links_detects_missing_and_outside_targets(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "repo"
    docs = root / "docs"
    docs.mkdir(parents=True)
    (docs / "present.md").write_text("present\n", encoding="utf-8")
    (docs / "README.md").write_text(
        "[present](present.md) [missing](missing.md) [outside](../../outside.md)\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(checker, "ROOT", root)
    assert checker.broken_relative_links() == [
        (Path("docs/README.md"), "missing.md"),
        (Path("docs/README.md"), "../../outside.md"),
    ]


def test_undiscoverable_domains_reports_primary_indexes_not_in_root_index(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "repo"
    docs = root / "docs"
    (docs / "v2").mkdir(parents=True)
    (docs / "architecture").mkdir(parents=True)
    (docs / "README.md").write_text("v2/README.md\n", encoding="utf-8")
    (docs / "v2" / "README.md").write_text("# V2\n", encoding="utf-8")
    (docs / "architecture" / "README.md").write_text("# Architecture\n", encoding="utf-8")

    monkeypatch.setattr(checker, "ROOT", root)
    monkeypatch.setattr(checker, "DOCS_ROOT", docs)
    monkeypatch.setattr(checker, "DOCS_INDEX", docs / "README.md")

    assert checker.undiscoverable_domains() == [
        Path("docs/architecture/README.md")
    ]


def test_current_repository_documentation_is_integrity_clean() -> None:
    assert checker.broken_relative_links() == []
    assert checker.undiscoverable_domains() == []
