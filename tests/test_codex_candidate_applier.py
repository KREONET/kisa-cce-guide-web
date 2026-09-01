"""Regression tests for deterministic canonical Codex candidate application."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

from conversion import codex_candidate_applier
from conversion.codex_candidate_applier import (
    CandidateInputs,
    apply_all_codex_candidates,
    apply_codex_candidate,
)
from conversion.codex_result_importer import render_codex_candidate
from conversion.codex_task_builder import (
    build_codex_task,
    calculate_codex_task_checksum,
    load_codex_task,
)
from conversion.common import (
    ALLOWED_NOTE_LABELS,
    JsonValue,
    as_mapping,
    as_sequence,
    criterion_source_checksum,
    extract_leaf_blocks,
    flatten_block_references,
    heading_identifiers,
    load_criterion,
    load_yaml,
    region_source_checksum,
    repository_root,
    sha256_file,
)
from conversion.paths import (
    CRITERIA_DIRECTORY,
    canonical_asset_directory,
    criterion_directory,
)
from conversion.validate_content import ValidationIssue, _valid_system_semantic_path
from tests.codex_transition_fixtures import create_codex_transition_repository
from tests.test_codex_pipeline import _fake_result

APPLICATION_SLUG = "u-03"
APPLICATION_DOMAIN = "unix"
EXPECTED_SOURCE_CROP_COUNT = 4
EXPECTED_NOTE_BLOCK_COUNT = 2
DYNAMIC_HEADING_PHYSICAL_PAGE = 21


@dataclass(frozen=True)
class PreparedApplication:
    """One isolated repository and its current candidate artifacts."""

    repository: Path
    work_directory: Path
    source_crop_checksums: dict[str, str]


@dataclass(frozen=True)
class PreparedBatchApplication:
    """Two isolated current candidates sharing one original taxonomy snapshot."""

    repository: Path
    work_directory: Path
    slugs: tuple[str, str]


def _copy_repository(destination: Path) -> Path:
    """Create an isolated repository at the U-03 and U-04 transition boundary."""

    return create_codex_transition_repository(
        repository_root(),
        destination,
        slugs=(APPLICATION_SLUG, "u-04"),
    )


def _add_dynamic_heading(
    result: dict[str, JsonValue],
    *,
    content: str,
    node_identifier: str,
) -> None:
    """Insert one source-backed U-03 environment heading into a fake result."""

    nodes = as_sequence(result["nodes"], location="result.nodes")
    insertion_index = next(
        index
        for index, value in enumerate(nodes)
        if isinstance(value, dict) and value.get("nodeIdentifier") == "remediation.solaris.step-1"
    )
    heading: JsonValue = {
        "nodeIdentifier": node_identifier,
        "nodeType": "heading",
        "sourceContentType": "pageText",
        "semanticRole": "environmentHeading",
        "content": content,
        "headingLevel": 4,
        "listType": None,
        "listDepth": None,
        "sourceMarker": "[ ]",
        "codeLanguage": None,
        "codeContentType": None,
        "tableCaption": None,
        "tableHeaders": None,
        "tableRows": None,
        "noteType": None,
        "assetPath": None,
        "alternativeText": None,
        "sourceSpans": [
            {
                "physicalPage": DYNAMIC_HEADING_PHYSICAL_PAGE,
                "pageRegionIdentifier": "p21-u-03",
                "sourceTextExcerpt": content,
                "evidenceOrigin": "pageImage",
                "transcriptAlignment": "exact",
                "recognitionStatus": "clear",
                "uncertaintyDescription": None,
            }
        ],
        "publicationDisposition": "published",
    }
    nodes.insert(insertion_index, heading)
    inspections = as_sequence(
        result["sourcePageInspections"],
        location="result.sourcePageInspections",
    )
    inspection = next(
        as_mapping(value, location="sourcePageInspections[]")
        for value in inspections
        if isinstance(value, dict) and value.get("physicalPage") == DYNAMIC_HEADING_PHYSICAL_PAGE
    )
    observed_identifiers = as_sequence(
        inspection["observedNodeIdentifiers"],
        location="sourcePageInspection.observedNodeIdentifiers",
    )
    observed_identifiers.append(node_identifier)


def _write_result_candidate(
    task: dict[str, JsonValue],
    *,
    repository: Path,
    work_directory: Path,
    dynamic_heading: str | None,
) -> None:
    """Write and import one valid fake result for a prepared task."""

    slug = cast("str", task["criterionSlug"])
    result = _fake_result(task)
    if dynamic_heading is not None:
        _add_dynamic_heading(
            result,
            content=dynamic_heading,
            node_identifier=f"{slug}.dynamic-heading",
        )
    result_path = work_directory / "results" / slug / "result.json"
    result_path.parent.mkdir(parents=True)
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    render_codex_candidate(
        result_path,
        work_directory / "tasks" / slug / "task.json",
        root=repository,
        work_directory=work_directory,
    )


def _prepare_application(
    tmp_path: Path,
    *,
    dynamic_heading: str | None = None,
) -> PreparedApplication:
    """Build a current task, result, and candidate in an isolated repository."""

    repository = _copy_repository(tmp_path / "repository")
    work_directory = (tmp_path / "work").resolve()
    task_path = build_codex_task(
        APPLICATION_SLUG,
        root=repository,
        work_directory=work_directory,
    )
    task = load_codex_task(task_path, root=repository)
    _write_result_candidate(
        task,
        repository=repository,
        work_directory=work_directory,
        dynamic_heading=dynamic_heading,
    )
    source_crop_checksums = {
        path.name: sha256_file(path)
        for path in sorted(canonical_asset_directory(repository, APPLICATION_SLUG).glob("*.png"))
    }
    assert len(source_crop_checksums) == EXPECTED_SOURCE_CROP_COUNT
    return PreparedApplication(
        repository=repository,
        work_directory=work_directory,
        source_crop_checksums=source_crop_checksums,
    )


def _prepare_batch_application(tmp_path: Path) -> PreparedBatchApplication:
    """Prepare two extracted candidates whose tasks share the original taxonomy checksum."""

    prepared = _prepare_application(
        tmp_path,
        dynamic_heading="5.9 미만 버전",
    )
    repository = prepared.repository
    work_directory = prepared.work_directory
    second_slug = "u-04"

    manifest_path = repository / "data/criteria-manifest.yaml"
    manifest = load_yaml(manifest_path)
    manifest_records = [
        as_mapping(value, location="manifest.criteria[]")
        for value in as_sequence(manifest["criteria"], location="manifest.criteria")
    ]
    for record in manifest_records:
        if record.get("slug") not in {APPLICATION_SLUG, second_slug}:
            record["contentModel"] = "systemCriterion"
            record["technicalLiteralInventoryMode"] = "extractedFromTypedAst"
    codex_candidate_applier._atomic_replace_bytes(  # noqa: SLF001
        manifest_path,
        codex_candidate_applier._yaml_text(manifest).encode(),  # noqa: SLF001
    )

    first_task_path = work_directory / "tasks" / APPLICATION_SLUG / "task.json"
    first_task = load_codex_task(first_task_path, root=repository)
    second_manifest = next(
        record for record in manifest_records if record.get("slug") == second_slug
    )
    second_criterion = load_criterion(
        criterion_directory(repository, APPLICATION_DOMAIN) / f"{second_slug}.md"
    )
    second_criterion_metadata = as_mapping(
        second_criterion.metadata["criterion"],
        location="criterion.criterion",
    )
    second_task = copy.deepcopy(first_task)
    second_task.update(
        {
            "taskIdentifier": "u-04-codex-structure-v3",
            "taskChecksum": "0" * 64,
            "criterionCode": second_criterion_metadata["code"],
            "criterionSlug": second_slug,
            "criterionTitle": second_criterion_metadata["title"],
            "domainIdentifier": second_manifest["domainIdentifier"],
            "categoryIdentifier": second_manifest["categoryIdentifier"],
            "criterionSourceChecksum": criterion_source_checksum(
                second_slug,
                APPLICATION_DOMAIN,
                root=repository,
            ),
        }
    )
    second_paths = as_mapping(second_task["paths"], location="task.paths")
    second_paths["criterionMarkdown"] = (
        CRITERIA_DIRECTORY / "unix" / f"{second_slug}.md"
    ).as_posix()
    second_paths["criterionProvenance"] = (
        CRITERIA_DIRECTORY / "unix" / f"{second_slug}.provenance.yaml"
    ).as_posix()
    second_task["taskChecksum"] = calculate_codex_task_checksum(second_task)
    second_task_path = work_directory / "tasks" / second_slug / "task.json"
    second_task_path.parent.mkdir(parents=True)
    second_task_path.write_text(
        json.dumps(second_task, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    validated_second_task = load_codex_task(second_task_path, root=repository)
    _write_result_candidate(
        validated_second_task,
        repository=repository,
        work_directory=work_directory,
        dynamic_heading="5.9 이상 버전",
    )
    return PreparedBatchApplication(
        repository=repository,
        work_directory=work_directory,
        slugs=(APPLICATION_SLUG, second_slug),
    )


def _review_record(
    review_registry: dict[str, JsonValue],
    *,
    subject_type: str,
    subject_identifier: str,
) -> dict[str, JsonValue]:
    """Return one review fixture record by its compound identity."""

    matches = [
        as_mapping(value, location="reviewRegistry.records[]")
        for value in as_sequence(
            review_registry["records"],
            location="reviewRegistry.records",
        )
        if isinstance(value, dict)
        and value.get("subjectType") == subject_type
        and value.get("subjectIdentifier") == subject_identifier
    ]
    assert len(matches) == 1
    return matches[0]


def test_ordered_step_references_continue_across_separated_lists() -> None:
    """Separated procedure lists in one semantic path must not reuse step ordinals."""

    body = """## 점검 및 조치 사례

### LINUX

1. 첫 번째 절차

| 옵션 | 설명 |
| --- | --- |
| one | first |

1. 두 번째 절차
"""
    blocks = extract_leaf_blocks(
        body,
        criterion_slug="u-99",
        heading_identifier_mapping={"점검 및 조치 사례": "remediation", "LINUX": "linux"},
    )
    step_references = [block.block_reference for block in blocks if block.semantic_role == "step"]
    assert step_references == [
        "u-99:remediation.linux.step:1",
        "u-99:remediation.linux.step:2",
    ]


@pytest.mark.parametrize("note_label", sorted(ALLOWED_NOTE_LABELS))
def test_every_allowed_note_label_has_a_distinct_label_block(note_label: str) -> None:
    """Every policy note label must parse separately from its content."""

    body = f"""## 개요

### 참고

> **{note_label}**
>
> 확인할 내용
"""
    blocks = extract_leaf_blocks(
        body,
        criterion_slug="u-99",
        heading_identifier_mapping={"개요": "overview", "참고": "reference"},
    )
    note_blocks = [block for block in blocks if block.block_type.startswith("note")]
    assert [(block.block_type, block.content) for block in note_blocks] == [
        ("noteLabel", f"**{note_label}**"),
        ("noteContent", "확인할 내용"),
    ]
    assert len({block.block_reference for block in note_blocks}) == EXPECTED_NOTE_BLOCK_COUNT


def test_note_paragraph_references_are_unique_within_one_blockquote() -> None:
    """Multiple paragraphs in one note must receive distinct canonical references."""

    body = """## 개요

### 참고

> **참고**
>
> 첫 번째 문단
>
> 두 번째 문단
"""
    blocks = extract_leaf_blocks(
        body,
        criterion_slug="u-99",
        heading_identifier_mapping={"개요": "overview", "참고": "reference"},
    )
    note_content_references = [
        block.block_reference for block in blocks if block.block_type == "noteContent"
    ]
    assert note_content_references == [
        "u-99:overview.reference.note.content:1",
        "u-99:overview.reference.note.content:2",
    ]


def test_machine_annotation_maps_to_pending_canonical_annotation(tmp_path: Path) -> None:
    """Applying a result annotation must not fabricate review or approval fields."""

    inputs = CandidateInputs(
        task={
            "taskIdentifier": "u-99-codex-structure-v3",
            "sourcePageEvidence": [
                {
                    "physicalPage": 99,
                    "printedPage": "99",
                    "pageRegionIdentifier": "p99-u-99",
                }
            ],
        },
        result={
            "sourceAnnotations": [
                {
                    "annotationIdentifier": "u-99-source-001",
                    "annotationType": "sourceTypo",
                    "targetReference": "remediation.linux.step-1",
                    "physicalPages": [99],
                    "sourceText": "etc/securiy/faillock.conf",
                    "explanation": "The source spelling requires verification.",
                    "disposition": "reviewRequired",
                }
            ]
        },
        validation={},
        manifest={},
        manifest_record={},
        task_path=tmp_path / "task.json",
        result_path=tmp_path / "result.json",
        candidate_path=tmp_path / "candidate.md",
        validation_path=tmp_path / "validation.json",
    )
    annotations = codex_candidate_applier._canonical_annotations(  # noqa: SLF001
        inputs,
        node_block_references={"remediation.linux.step-1": ("u-99:remediation.linux.step:1",)},
    )
    assert annotations == [
        {
            "annotationIdentifier": "u-99-source-001",
            "annotationType": "sourceTypographicalError",
            "targetType": "astNode",
            "targetReference": "u-99:remediation.linux.step:1",
            "sourceLocation": {
                "physicalPage": 99,
                "printedPage": "99",
                "pageRegionIdentifier": "p99-u-99",
            },
            "sourceText": "etc/securiy/faillock.conf",
            "explanation": "The source spelling requires verification.",
            "disposition": "unresolved",
            "reviewStatus": "pending",
            "verificationEvidence": [
                (
                    "Validated Codex task u-99-codex-structure-v3 recorded this annotation "
                    "for physical pages 99."
                )
            ],
            "reviewedBy": None,
            "reviewedAt": None,
            "approvedBy": None,
            "approvedAt": None,
        }
    ]


def test_asset_preparation_removes_crops_and_preserves_declared_visual(
    tmp_path: Path,
) -> None:
    """Only source-page crops move to evidence; declared meaningful assets remain canonical."""

    asset_directory = canonical_asset_directory(tmp_path, "u-99")
    asset_directory.mkdir(parents=True)
    meaningful_path = asset_directory / "diagram.png"
    source_crop_path = asset_directory / "page-99.png"
    meaningful_path.write_bytes(b"meaningful visual")
    source_crop_path.write_bytes(b"intermediate page crop")
    provenance: dict[str, JsonValue] = {
        "assets": [
            {
                "path": "../../assets/u-99/page-99.png",
                "assetType": "sourcePageCrop",
                "checksumValue": sha256_file(source_crop_path),
            },
            {
                "path": "../../assets/u-99/diagram.png",
                "assetType": "sourceImage",
                "checksumValue": sha256_file(meaningful_path),
                "alternativeText": "Old description",
                "alternativeTextStatus": "reviewed",
            },
        ]
    }
    nodes: list[dict[str, JsonValue]] = [
        {
            "nodeIdentifier": "remediation.linux.diagram",
            "nodeType": "image",
            "assetPath": "assets/u-99/diagram.png",
            "alternativeText": "Meaningful configuration flow",
        }
    ]
    assets, assets_by_node, source_crop_paths = codex_candidate_applier._prepare_assets(  # noqa: SLF001
        nodes,
        provenance,
        root=tmp_path,
        domain_identifier="unix",
        slug="u-99",
    )
    assert source_crop_paths == (source_crop_path,)
    assert [asset["path"] for asset in cast("list[dict[str, JsonValue]]", assets)] == [
        "../../assets/u-99/diagram.png"
    ]
    retained = assets_by_node["remediation.linux.diagram"]
    assert retained["alternativeText"] == "Meaningful configuration flow"
    assert retained["alternativeTextStatus"] == "verificationRequired"
    assert nodes[0]["assetPath"] == "../../assets/u-99/diagram.png"


def test_dynamic_taxonomy_registers_u03_versions_and_reuses_existing_terms(
    tmp_path: Path,
) -> None:
    """Version headings need readable IDs while exact labels reuse registered terms."""

    heading_labels = [
        "SOLARIS",
        "Redhat",
        "Red Hat",
        "Appliance 9",
        "5.9 미만 버전",
        "5.9 이상 버전",
        "11.v2 이하 버전",
        "11.v3 이상 버전",
    ]
    inputs = CandidateInputs(
        task={},
        result={
            "nodes": [
                {
                    "nodeType": "heading",
                    "headingLevel": 4,
                    "content": label,
                }
                for label in heading_labels
            ]
        },
        validation={},
        manifest={},
        manifest_record={},
        task_path=tmp_path / "task.json",
        result_path=tmp_path / "result.json",
        candidate_path=tmp_path / "candidate.md",
        validation_path=tmp_path / "validation.json",
    )
    original = load_yaml(repository_root() / "data/taxonomy.yaml")
    compiled = codex_candidate_applier._compile_dynamic_taxonomy(  # noqa: SLF001
        [inputs],
        taxonomy=original,
    )
    product_families = [
        as_mapping(value, location="taxonomy.productFamilies[]")
        for value in as_sequence(
            compiled["productFamilies"],
            location="taxonomy.productFamilies",
        )
    ]
    identifiers_by_source_label = {
        cast("str", term["sourceLabel"]): cast("str", term["identifier"])
        for term in product_families
    }
    assert identifiers_by_source_label["Redhat"] == "red-hat"
    assert "Red Hat" not in identifiers_by_source_label
    assert identifiers_by_source_label["Appliance 9"] == "appliance-9"
    assert _valid_system_semantic_path(
        ("remediation", "appliance-9"),
        taxonomy=compiled,
    )
    expected_version_identifiers = {
        "5.9 미만 버전": "version-5-9-below",
        "5.9 이상 버전": "version-5-9-or-later",
        "11.v2 이하 버전": "version-11-v2-or-earlier",
        "11.v3 이상 버전": "version-11-v3-or-later",
    }
    for source_label, identifier in expected_version_identifiers.items():
        assert identifiers_by_source_label[source_label] == identifier


def test_applier_updates_canonical_package_and_preserves_crop_evidence(tmp_path: Path) -> None:
    """A validated candidate must update every checksum without claiming human review."""

    prepared = _prepare_application(
        tmp_path,
        dynamic_heading="5.9 미만 버전",
    )
    output_path = apply_codex_candidate(
        APPLICATION_SLUG,
        root=prepared.repository,
        work_directory=prepared.work_directory,
    )
    assert output_path == (
        criterion_directory(prepared.repository, APPLICATION_DOMAIN) / f"{APPLICATION_SLUG}.md"
    )

    criterion = load_criterion(output_path)
    assert criterion.metadata["contentModel"] == "systemCriterion"
    assert criterion.metadata["targetIdentifiers"] == ["solaris", "linux", "aix", "hp-ux"]
    provenance = load_yaml(
        criterion_directory(prepared.repository, APPLICATION_DOMAIN)
        / f"{APPLICATION_SLUG}.provenance.yaml"
    )
    blocks = extract_leaf_blocks(
        criterion.body,
        criterion_slug=APPLICATION_SLUG,
        heading_identifier_mapping=heading_identifiers(
            load_yaml(prepared.repository / "data/taxonomy.yaml")
        ),
    )
    references = flatten_block_references(provenance)
    assert references == [block.block_reference for block in blocks]
    assert len(references) == len(set(references))
    assert provenance["assets"] == []

    application_asset_directory = canonical_asset_directory(prepared.repository, APPLICATION_SLUG)
    assert not list(application_asset_directory.glob("*.png"))
    evidence_directory = prepared.work_directory / "evidence" / APPLICATION_SLUG
    assert {
        path.name: sha256_file(path) for path in sorted(evidence_directory.glob("*.png"))
    } == prepared.source_crop_checksums

    manifest = load_yaml(prepared.repository / "data/criteria-manifest.yaml")
    manifest_record = next(
        value
        for value in as_sequence(manifest["criteria"], location="manifest.criteria")
        if isinstance(value, dict) and value.get("slug") == APPLICATION_SLUG
    )
    assert manifest_record["contentModel"] == "systemCriterion"
    assert manifest_record["technicalLiteralInventoryMode"] == "extractedFromTypedAst"
    taxonomy = load_yaml(prepared.repository / "data/taxonomy.yaml")
    version_term = next(
        as_mapping(value, location="taxonomy.productFamilies[]")
        for value in as_sequence(
            taxonomy["productFamilies"],
            location="taxonomy.productFamilies",
        )
        if isinstance(value, dict) and value.get("sourceLabel") == "5.9 미만 버전"
    )
    assert version_term == {
        "identifier": "version-5-9-below",
        "label": "5.9 미만 버전",
        "sourceLabel": "5.9 미만 버전",
    }

    checksum = criterion_source_checksum(
        APPLICATION_SLUG,
        APPLICATION_DOMAIN,
        root=prepared.repository,
    )
    reviews = load_yaml(prepared.repository / "data/review-registry.yaml")
    criterion_review = _review_record(
        reviews,
        subject_type="criterion",
        subject_identifier=APPLICATION_SLUG,
    )
    assert criterion_review["subjectSourceChecksum"] == checksum
    assert criterion_review["workflowStatus"] == "structured"
    assert criterion_review["transcriptionStatus"] == "verificationRequired"
    assert criterion_review["reviewers"] == []
    assert criterion_review["reviewedAt"] is None
    assert criterion_review["automatedValidationResult"] == "notRun"
    assert criterion_review["validationReportIdentifier"] is None

    inventory = load_yaml(prepared.repository / "data/page-region-inventory.yaml")
    owned_regions = [
        as_mapping(value, location="pageRegionInventory.pageRegions[]")
        for value in as_sequence(
            inventory["pageRegions"],
            location="pageRegionInventory.pageRegions",
        )
        if isinstance(value, dict)
        and value.get("ownerType") == "criterion"
        and value.get("ownerIdentifier") == APPLICATION_SLUG
    ]
    assert owned_regions
    for region in owned_regions:
        region_identifier = cast("str", region["pageRegionIdentifier"])
        region_review = _review_record(
            reviews,
            subject_type="pageRegion",
            subject_identifier=region_identifier,
        )
        assert region_review["subjectSourceChecksum"] == region_source_checksum(
            region,
            owner_source_checksum=checksum,
        )
        assert region_review["workflowStatus"] == "extracted"
        assert region_review["transcriptionStatus"] == "verificationRequired"
        assert region_review["reviewers"] == []
        assert region_review["visualEvidenceIdentifiers"] == []

    validation = load_yaml(prepared.work_directory / "candidates/u-03/validation.json")
    assert validation["canonicalApplied"] is True


def test_applier_rolls_back_every_canonical_change_on_validation_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A post-replacement validation failure must restore files, assets, and candidate state."""

    prepared = _prepare_application(tmp_path)
    application_criterion_directory = criterion_directory(
        prepared.repository,
        APPLICATION_DOMAIN,
    )
    tracked_paths = [
        application_criterion_directory / f"{APPLICATION_SLUG}.md",
        application_criterion_directory / f"{APPLICATION_SLUG}.provenance.yaml",
        prepared.repository / "data/criteria-manifest.yaml",
        prepared.repository / "data/review-registry.yaml",
        prepared.work_directory / "candidates/u-03/validation.json",
    ]
    original_bytes = {path: path.read_bytes() for path in tracked_paths}
    original_assets = {
        path: path.read_bytes()
        for path in canonical_asset_directory(prepared.repository, APPLICATION_SLUG).glob("*.png")
    }
    validation_failure = ValidationIssue(
        "forced-test-failure",
        "content/criteria/unix/u-03.md",
        "The post-replacement repository validation failed.",
    )
    validation_call_count = 0

    def forced_validation(**_arguments: object) -> list[ValidationIssue]:
        """Pass baseline validation and fail the post-replacement validation."""

        nonlocal validation_call_count
        validation_call_count += 1
        return [] if validation_call_count == 1 else [validation_failure]

    monkeypatch.setattr(
        codex_candidate_applier,
        "validate_repository",
        forced_validation,
    )
    with pytest.raises(ValueError, match="forced-test-failure"):
        apply_codex_candidate(
            APPLICATION_SLUG,
            root=prepared.repository,
            work_directory=prepared.work_directory,
        )

    assert {path: path.read_bytes() for path in tracked_paths} == original_bytes
    assert {path: path.read_bytes() for path in original_assets} == original_assets
    validation = json.loads(
        (prepared.work_directory / "candidates/u-03/validation.json").read_text(encoding="utf-8")
    )
    assert validation["canonicalApplied"] is False
    evidence_paths = list((prepared.work_directory / "evidence" / APPLICATION_SLUG).glob("*.png"))
    assert len(evidence_paths) == EXPECTED_SOURCE_CROP_COUNT


def test_batch_prevalidates_original_taxonomy_before_one_compiled_apply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A taxonomy addition from the first item must not stale a later current task."""

    prepared = _prepare_batch_application(tmp_path)
    original_taxonomy_checksum = sha256_file(prepared.repository / "data/taxonomy.yaml")
    task_taxonomy_checksums = {
        cast(
            "str",
            load_codex_task(
                prepared.work_directory / "tasks" / slug / "task.json",
                root=prepared.repository,
            )["taxonomyChecksum"],
        )
        for slug in prepared.slugs
    }
    assert task_taxonomy_checksums == {original_taxonomy_checksum}
    monkeypatch.setattr(codex_candidate_applier, "validate_repository", lambda **_arguments: [])

    output_paths = apply_all_codex_candidates(
        root=prepared.repository,
        work_directory=prepared.work_directory,
    )
    application_criterion_directory = criterion_directory(
        prepared.repository,
        APPLICATION_DOMAIN,
    )
    assert output_paths == tuple(
        application_criterion_directory / f"{slug}.md" for slug in prepared.slugs
    )
    assert sha256_file(prepared.repository / "data/taxonomy.yaml") != original_taxonomy_checksum
    taxonomy = load_yaml(prepared.repository / "data/taxonomy.yaml")
    product_families = [
        as_mapping(value, location="taxonomy.productFamilies[]")
        for value in as_sequence(
            taxonomy["productFamilies"],
            location="taxonomy.productFamilies",
        )
    ]
    assert {(term.get("identifier"), term.get("sourceLabel")) for term in product_families} >= {
        ("version-5-9-below", "5.9 미만 버전"),
        ("version-5-9-or-later", "5.9 이상 버전"),
    }
    for slug in prepared.slugs:
        validation = json.loads(
            (prepared.work_directory / "candidates" / slug / "validation.json").read_text(
                encoding="utf-8"
            )
        )
        assert validation["canonicalApplied"] is True


def test_batch_rolls_back_all_packages_and_taxonomy_together(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Any batch post-validation failure must restore every package and shared registry."""

    prepared = _prepare_batch_application(tmp_path)
    application_criterion_directory = criterion_directory(
        prepared.repository,
        APPLICATION_DOMAIN,
    )
    tracked_paths = [
        *(
            application_criterion_directory / f"{slug}{suffix}"
            for slug in prepared.slugs
            for suffix in (".md", ".provenance.yaml")
        ),
        prepared.repository / "data/criteria-manifest.yaml",
        prepared.repository / "data/review-registry.yaml",
        prepared.repository / "data/taxonomy.yaml",
        *(
            prepared.work_directory / "candidates" / slug / "validation.json"
            for slug in prepared.slugs
        ),
    ]
    original_bytes = {path: path.read_bytes() for path in tracked_paths}
    original_assets = {
        path: path.read_bytes()
        for slug in prepared.slugs
        for path in canonical_asset_directory(prepared.repository, slug).glob("*.png")
    }
    validation_call_count = 0

    def forced_validation(**_arguments: object) -> list[ValidationIssue]:
        """Pass the batch baseline and fail its single post-replacement validation."""

        nonlocal validation_call_count
        validation_call_count += 1
        if validation_call_count == 1:
            return []
        return [
            ValidationIssue(
                "forced-batch-failure",
                "data/taxonomy.yaml",
                "The staged corpus validation failed.",
            )
        ]

    monkeypatch.setattr(codex_candidate_applier, "validate_repository", forced_validation)
    with pytest.raises(ValueError, match="forced-batch-failure"):
        apply_all_codex_candidates(
            root=prepared.repository,
            work_directory=prepared.work_directory,
        )

    assert {path: path.read_bytes() for path in tracked_paths} == original_bytes
    assert {path: path.read_bytes() for path in original_assets} == original_assets
    for slug in prepared.slugs:
        validation = json.loads(
            (prepared.work_directory / "candidates" / slug / "validation.json").read_text(
                encoding="utf-8"
            )
        )
        assert validation["canonicalApplied"] is False
