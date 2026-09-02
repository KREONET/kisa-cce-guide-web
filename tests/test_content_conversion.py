"""Regression tests for the complete initial corpus."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from conversion.build_content import build
from conversion.common import (
    REQUIRED_ASSESSMENT_LEVEL_THREE_HEADINGS,
    REQUIRED_LEVEL_TWO_HEADINGS,
    REQUIRED_OVERVIEW_LEVEL_THREE_HEADINGS,
    extract_leaf_blocks,
    flatten_block_references,
    heading_identifiers,
    load_criterion,
    load_yaml,
    repository_root,
)
from conversion.paths import (
    CRITERIA_DIRECTORY,
    SOURCE_DOCUMENT_PATH,
    criterion_directory,
)
from conversion.validate_content import (
    ValidationIssue,
    _AnnotationOccurrence,
    _CriterionValidationResult,
    _merge_criterion_validation_results,
    _validate_markdown_structure,
    validate_repository,
)

HEADING_LEVEL_TWO = 2
SOLARIS_RECOMMENDATION_ROW_COUNT = 17
EXPECTED_CRITERION_COUNT = 382
MAX_SEARCH_INDEX_BYTES = 1_450_000
SEARCH_SCHEMA_VERSION = 2
CANONICAL_EXEMPLAR_PATH = CRITERIA_DIRECTORY / "unix/u-01.md"


def _canonical_exemplar_body() -> str:
    """Load the canonical exemplar body that defines the repository format contract."""

    return load_criterion(repository_root() / CANONICAL_EXEMPLAR_PATH).body


def _structure_rules(body: str, *, content_model: str = "systemCriterion") -> list[str]:
    """Return the rule identifiers reported for one Markdown body."""

    return [
        issue.rule_identifier
        for issue in _validate_markdown_structure(
            criterion_path=CANONICAL_EXEMPLAR_PATH,
            body=body,
            content_model=content_model,
        )
    ]


def _link_or_copy_file(source: str, destination: str) -> str:
    """Hard-link fixture files when possible and copy across filesystems."""

    try:
        os.link(source, destination)
    except OSError:
        return shutil.copy2(source, destination)
    return destination


def _copy_validation_repository(destination: Path) -> Path:
    """Create a lightweight isolated copy of every canonical validation input."""

    source = repository_root()
    destination.mkdir()
    for directory_name in ("content", "data", "schemas"):
        shutil.copytree(
            source / directory_name,
            destination / directory_name,
            copy_function=_link_or_copy_file,
        )
    manifest_path = destination / "data/criteria-manifest.yaml"
    manifest_path.unlink()
    shutil.copy2(source / "data/criteria-manifest.yaml", manifest_path)
    return destination


def test_scoped_validation_passes() -> None:
    """The complete canonical corpus must validate."""

    sequential_issues = validate_repository(release=False, workers=1)
    parallel_issues = validate_repository(release=False, workers=4)

    assert sequential_issues == parallel_issues == []


def test_parallel_validation_merge_preserves_annotation_issue_order() -> None:
    """Cross-worker annotation duplicates must appear at their source-order offset."""

    first_result = _CriterionValidationResult(
        issues=(),
        annotation_occurrences=(
            _AnnotationOccurrence("annotation-1", 0, "content/criteria/unix/u-01.md"),
        ),
    )
    before_issue = ValidationIssue("before", "u-02", "before annotation")
    after_issue = ValidationIssue("after", "u-02", "after annotation")
    second_result = _CriterionValidationResult(
        issues=(before_issue, after_issue),
        annotation_occurrences=(
            _AnnotationOccurrence("annotation-1", 1, "content/criteria/unix/u-02.md"),
        ),
    )

    assert _merge_criterion_validation_results([first_result, second_result]) == [
        before_issue,
        ValidationIssue(
            "annotation-identifier-unique",
            "content/criteria/unix/u-02.md",
            "duplicate annotation identifier annotation-1",
        ),
        after_issue,
    ]


def test_parallel_validation_preserves_ordered_failures(tmp_path: Path) -> None:
    """Parallel validation must return the exact serial issue sequence for invalid input."""

    repository = _copy_validation_repository(tmp_path / "repository")
    manifest_path = repository / "data/criteria-manifest.yaml"
    manifest = manifest_path.read_text(encoding="utf-8")
    manifest_path.write_text(
        manifest.replace("route: /unix/u-02/", "route: /unix/u-01/", 1),
        encoding="utf-8",
    )

    sequential_issues = validate_repository(root=repository, release=False, workers=1)
    parallel_issues = validate_repository(root=repository, release=False, workers=4)

    assert sequential_issues
    assert sequential_issues == parallel_issues
    assert "manifest-identity-unique" in {issue.rule_identifier for issue in sequential_issues}


def test_release_validation_remains_blocked() -> None:
    """A structured corpus must remain blocked by outstanding release gates."""

    rule_identifiers = {
        issue.rule_identifier for issue in validate_repository(release=True, workers=4)
    }
    assert "release-license-approved" not in rule_identifiers
    assert "release-structured-corpus" not in rule_identifiers
    assert "release-review-approved" in rule_identifiers
    assert "release-test-profile-complete" in rule_identifiers
    assert "release-accessibility-report" in rule_identifiers
    assert "release-responsive-report" in rule_identifiers
    assert "release-print-report" in rule_identifiers


def test_every_markdown_leaf_has_provenance() -> None:
    """Every parsed leaf must have one provenance reference."""

    root = repository_root()
    heading_identifier_mapping = heading_identifiers(load_yaml(root / "data/taxonomy.yaml"))
    # The u-02 reference section uses a note blockquote, which contributes one note label
    # block in addition to its note items.
    expected_counts = {"u-01": 63, "u-02": 90}
    for slug, expected_count in expected_counts.items():
        criterion = load_criterion(criterion_directory(root, "unix") / f"{slug}.md")
        provenance = load_yaml(criterion_directory(root, "unix") / f"{slug}.provenance.yaml")
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


def test_leaf_block_technical_literals_are_unique_in_source_order() -> None:
    """Repeated literals in one source block must retain only their first occurrence."""

    root = repository_root()
    criterion = load_criterion(criterion_directory(root, "unix") / "u-05.md")
    heading_identifier_mapping = heading_identifiers(load_yaml(root / "data/taxonomy.yaml"))
    leaf_blocks = extract_leaf_blocks(
        criterion.body,
        criterion_slug="u-05",
        heading_identifier_mapping=heading_identifier_mapping,
    )
    solaris_table = next(
        block
        for block in leaf_blocks
        if block.block_reference == "u-05:remediation.solaris.table:1"
    )

    assert solaris_table.technical_literals == (
        "Test",
        "x",
        "500",
        "Gen-User",
        "/home/test",
        "/usr/bin/bash",
    )


def test_build_is_deterministic() -> None:
    """Two clean-input builds must produce byte-identical JSON."""

    with TemporaryDirectory() as first_directory, TemporaryDirectory() as second_directory:
        first_root = Path(first_directory)
        second_root = Path(second_directory)
        first_paths = build(output_root=first_root, workers=1)
        first_bytes = {path.relative_to(first_root): path.read_bytes() for path in first_paths}
        second_paths = build(output_root=second_root, workers=4)
        second_bytes = {path.relative_to(second_root): path.read_bytes() for path in second_paths}
    assert first_bytes == second_bytes
    assert [path.relative_to(first_root) for path in first_paths] == [
        path.relative_to(second_root) for path in second_paths
    ]
    assert all(
        not content.endswith(b"\n")
        for path, content in first_bytes.items()
        if path.suffix == ".json"
    )


def test_search_index_contains_exact_terms(tmp_path: Path) -> None:
    """The initial index must retain code, path, and setting literals."""

    build(output_root=tmp_path)
    search_path = tmp_path / "search" / "search-index.json"
    search_index = json.loads(search_path.read_text(encoding="utf-8"))
    assert search_path.stat().st_size <= MAX_SEARCH_INDEX_BYTES
    assert search_index["schemaVersion"] == SEARCH_SCHEMA_VERSION
    assert search_index["tokenizerVersion"] == "unicode-nfc-korean-sections-v2"
    records = {record["code"]: record for record in search_index["records"]}
    assert len(records) == EXPECTED_CRITERION_COUNT
    assert {"U-01", "U-02", "W-01", "CI", "CA-19"} <= set(records)
    assert all("searchableText" not in record for record in records.values())
    assert "/etc/ssh/sshd_config" in records["U-01"]["exactTerms"]
    assert "etc/securetty" in records["U-01"]["exactTerms"]
    assert "#pts/0" in records["U-01"]["exactTerms"]
    assert "root 계정의 원격터미널 접속 차단" in records["U-01"]["searchSections"]["inspection"]
    assert "관리자 계정 탈취" in records["U-01"]["searchSections"]["purpose"]
    assert "root 계정으로 접속할 수 없도록" in records["U-01"]["searchSections"]["action"]
    assert "/etc/security/pwquality.conf" in records["U-02"]["exactTerms"]
    assert "/etc/security/opasswd" in records["U-02"]["exactTerms"]
    assert "PASSWORD_MIN_DIGIT_CHARS= 1" in records["U-02"]["exactTerms"]
    assert "비밀번호 관리 정책 설정 여부" in records["U-02"]["searchSections"]["inspection"]
    assert any("custom_404.html" in term for term in records["EP"]["exactTerms"])


def test_normalized_ast_preserves_semantics(tmp_path: Path) -> None:
    """Typed blocks must retain hierarchy, code profile, and derivation state."""

    build(output_root=tmp_path)
    u_01 = json.loads((tmp_path / "normalized/unix/u-01.json").read_text(encoding="utf-8"))
    u_02 = json.loads((tmp_path / "normalized/unix/u-02.json").read_text(encoding="utf-8"))
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
        root / SOURCE_DOCUMENT_PATH,
        root / "README.md",
        root / "CONVERSION_POLICY.md",
    ]
    assert all(path.is_file() for path in required_paths)


def test_canonical_exemplar_satisfies_format_contract() -> None:
    """The canonical exemplar must report no format issue under either canonical model."""

    body = _canonical_exemplar_body()
    assert _structure_rules(body) == []
    assert _structure_rules(body, content_model="webApplicationCriterion") == []


def test_shared_heading_constants_match_canonical_exemplar() -> None:
    """The shared constants must describe the heading composition of the exemplar."""

    body = _canonical_exemplar_body()
    assert [f"## {heading}" in body for heading in REQUIRED_LEVEL_TWO_HEADINGS] == [True] * 3
    assert all(f"### {heading}" in body for heading in REQUIRED_OVERVIEW_LEVEL_THREE_HEADINGS)
    assert all(f"### {heading}" in body for heading in REQUIRED_ASSESSMENT_LEVEL_THREE_HEADINGS)


def test_extra_level_two_heading_is_rejected() -> None:
    """An appended H2 must fail because the contract requires an exact H2 sequence."""

    body = _canonical_exemplar_body() + "\n## 부록\n\n추가 절입니다.\n"
    assert "markdown-required-headings" in _structure_rules(body)


def test_overview_level_three_order_violation_is_rejected() -> None:
    """Reordering the overview H3 headings must fail the section contract."""

    body = (
        _canonical_exemplar_body()
        .replace("### 점검 목적", "### 임시 제목")
        .replace("### 보안 위협", "### 점검 목적")
        .replace("### 임시 제목", "### 보안 위협")
    )
    assert "markdown-section-headings" in _structure_rules(body)


def test_assessment_level_three_omission_is_rejected() -> None:
    """Dropping one assessment H3 must fail even though the H2 sequence still matches."""

    body = _canonical_exemplar_body().replace(
        "### 조치 시 영향\n\n일반적인 경우 영향 없음\n",
        "",
    )
    rules = _structure_rules(body)
    assert "markdown-section-headings" in rules
    assert "markdown-required-headings" not in rules


def test_judgment_notation_violations_are_rejected() -> None:
    """Judgment items must keep the colon inside the strong span and appear exactly once."""

    body = _canonical_exemplar_body()
    colon_outside_strong = body.replace("- **양호:** ", "- **양호**: ")
    assert "markdown-judgment-notation" in _structure_rules(colon_outside_strong)
    duplicated_label = body.replace(
        "- **취약:** 원격터미널 서비스 사용 시 root 직접 접속을 허용한 경우",
        "- **양호:** 중복된 판정 항목",
    )
    assert "markdown-judgment-notation" in _structure_rules(duplicated_label)


def test_note_blockquote_profile_violations_are_rejected() -> None:
    """Note blockquotes must use an allowed label and a bare quote separator line."""

    body = _canonical_exemplar_body()
    unsupported_label = body.replace("> **참고**\n>\n> CentOS", "> **비고**\n>\n> CentOS")
    assert "markdown-note-profile" in _structure_rules(unsupported_label)
    missing_separator = body.replace(
        "> **참고**\n>\n> CentOS",
        "> **참고**\n> CentOS",
    )
    assert "markdown-note-profile" in _structure_rules(missing_separator)


def test_supplementary_guidance_must_be_the_last_remediation_heading() -> None:
    """추가 지침 must trail the per-target remediation sections."""

    body = _canonical_exemplar_body().replace(
        "### LINUX",
        "### 추가 지침\n\n플랫폼 공통 보충 내용입니다.\n\n### LINUX",
    )
    assert "markdown-section-headings" in _structure_rules(body)


def test_structured_criterion_uses_its_web_application_contract() -> None:
    """Converted documents must leave the intermediate transcription branch."""

    criterion = load_criterion(criterion_directory(repository_root(), "web-application") / "ae.md")
    assert criterion.metadata["contentModel"] == "webApplicationCriterion"
    assert _structure_rules(criterion.body, content_model="webApplicationCriterion") == []
    assert "markdown-required-headings" in _structure_rules(
        criterion.body,
        content_model="extractedCriterion",
    )
