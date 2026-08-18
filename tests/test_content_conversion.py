"""Regression tests for the complete initial corpus."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from conversion.build_content import build
from conversion.common import (
    extract_leaf_blocks,
    flatten_block_references,
    heading_identifiers,
    load_criterion,
    load_yaml,
    repository_root,
)
from conversion.validate_content import validate_repository

HEADING_LEVEL_TWO = 2
SOLARIS_RECOMMENDATION_ROW_COUNT = 17
EXPECTED_CRITERION_COUNT = 382


def test_scoped_validation_passes() -> None:
    """The complete canonical corpus must validate."""

    assert validate_repository(release=False) == []


def test_release_validation_remains_blocked() -> None:
    """Initial transcriptions must not be mistaken for a publishable release."""

    rule_identifiers = {issue.rule_identifier for issue in validate_repository(release=True)}
    assert "release-license-approved" in rule_identifiers
    assert "release-structured-corpus" in rule_identifiers
    assert "release-review-approved" in rule_identifiers
    assert "release-test-profile-complete" in rule_identifiers
    assert "release-accessibility-report" in rule_identifiers
    assert "release-responsive-report" in rule_identifiers
    assert "release-print-report" in rule_identifiers


def test_every_markdown_leaf_has_provenance() -> None:
    """Every parsed leaf must have one provenance reference."""

    root = repository_root()
    heading_identifier_mapping = heading_identifiers(load_yaml(root / "data/taxonomy.yaml"))
    expected_counts = {"u-01": 63, "u-02": 89}
    for slug, expected_count in expected_counts.items():
        criterion = load_criterion(root / "unix" / f"{slug}.md")
        provenance = load_yaml(root / "unix" / f"{slug}.provenance.yaml")
        leaf_blocks = extract_leaf_blocks(
            criterion.body,
            criterion_slug=slug,
            heading_identifier_mapping=heading_identifier_mapping,
        )
        references = flatten_block_references(provenance)
        assert len(leaf_blocks) == expected_count
        assert len(references) == expected_count
        assert len(references) == len(set(references))
        assert [block.block_reference for block in leaf_blocks] == references


def test_build_is_deterministic() -> None:
    """Two clean-input builds must produce byte-identical JSON."""

    with TemporaryDirectory() as first_directory, TemporaryDirectory() as second_directory:
        first_root = Path(first_directory)
        second_root = Path(second_directory)
        first_paths = build(output_root=first_root)
        first_bytes = {path.relative_to(first_root): path.read_bytes() for path in first_paths}
        second_paths = build(output_root=second_root)
        second_bytes = {path.relative_to(second_root): path.read_bytes() for path in second_paths}
    assert first_bytes == second_bytes
    assert all(
        not content.endswith(b"\n")
        for path, content in first_bytes.items()
        if path.suffix == ".json"
    )


def test_search_index_contains_exact_terms() -> None:
    """The initial index must retain code, path, and setting literals."""

    build()
    search_path = repository_root() / "build" / "search" / "search-index.json"
    search_index = json.loads(search_path.read_text(encoding="utf-8"))
    records = {record["code"]: record for record in search_index["records"]}
    assert len(records) == EXPECTED_CRITERION_COUNT
    assert {"U-01", "U-02", "W-01", "CI", "CA-19"} <= set(records)
    assert "/etc/ssh/sshd_config" in records["U-01"]["exactTerms"]
    assert "etc/securetty" in records["U-01"]["exactTerms"]
    assert "#pts/0" in records["U-01"]["exactTerms"]
    assert "PermitRootLogin No" in records["U-01"]["searchableText"]
    assert "/etc/security/pwquality.conf" in records["U-02"]["exactTerms"]
    assert "/etc/security/opasswd" in records["U-02"]["exactTerms"]
    assert "PASSWORD_MIN_DIGIT_CHARS= 1" in records["U-02"]["exactTerms"]
    assert "비밀번호 관리정책 설정" in records["U-02"]["searchableText"]
    assert "custom_404.html" in records["EP"]["searchableText"]


def test_normalized_ast_preserves_semantics() -> None:
    """Typed blocks must retain hierarchy, code profile, and derivation state."""

    build()
    root = repository_root()
    u_01 = json.loads((root / "build/normalized/unix/u-01.json").read_text(encoding="utf-8"))
    u_02 = json.loads((root / "build/normalized/unix/u-02.json").read_text(encoding="utf-8"))
    u_01_blocks = {block["blockReference"]: block for block in u_01["blocks"]}
    u_02_blocks = {block["blockReference"]: block for block in u_02["blocks"]}
    assert u_01_blocks["u-01:overview.heading:1"]["headingLevel"] == HEADING_LEVEL_TWO
    assert (
        u_01_blocks["u-01:remediation.solaris.telnet.configuration:1"]["codeContentType"]
        == "configuration"
    )
    assert (
        u_01_blocks["u-01:remediation.solaris.telnet.configuration:1"]["parentBlockReference"]
        == "u-01:remediation.solaris.telnet.step:1"
    )
    assert (
        u_02_blocks["u-02:remediation.supplementaryGuidance.heading:1"]["publicationDisposition"]
        == "derived"
    )
    assert (
        u_02_blocks["u-02:remediation.supplementaryGuidance.inappropriatePasswordTypes.heading:1"][
            "publicationDisposition"
        ]
        == "published"
    )
    solaris_table = u_02_blocks["u-02:remediation.solaris.table:1"]
    assert solaris_table["tableHeaders"] == ["권고값", "기능", "설명"]
    assert len(solaris_table["tableRows"]) == SOLARIS_RECOMMENDATION_ROW_COUNT
    assert (
        u_02_blocks[
            "u-02:remediation.supplementaryGuidance.passwordManagementMethods.characterClass:1"
        ]["parentBlockReference"]
        == "u-02:remediation.supplementaryGuidance.passwordManagementMethods.step:1"
    )


def test_internal_source_links_exist() -> None:
    """Policy and README source references must resolve in the repository."""

    root = repository_root()
    required_paths = [
        root / "kisa-cce-criteria-2026.pdf",
        root / "README.md",
        root / "CONVERSION_POLICY.md",
    ]
    assert all(path.is_file() for path in required_paths)
