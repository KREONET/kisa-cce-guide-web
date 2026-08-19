"""Validate Codex criterion results and render review-only Markdown candidates."""

from __future__ import annotations

import argparse
import json
import re
import sys
from itertools import pairwise
from pathlib import Path
from typing import cast

from jsonschema import Draft202012Validator, FormatChecker

from conversion.codex_task_builder import (
    DEFAULT_WORK_DIRECTORY,
    RESULT_SCHEMA_PATH,
    load_codex_task,
    verify_codex_task_dependencies,
)
from conversion.common import (
    JsonValue,
    as_mapping,
    as_sequence,
    load_json,
    repository_root,
    sha256_file,
)
from conversion.runtime_logging import add_logging_arguments, configure_runtime_logging

SYSTEM_LEVEL_TWO_HEADINGS = (
    "개요",
    "점검 대상 및 판단 기준",
    "점검 및 조치 사례",
)
SYSTEM_OVERVIEW_LEVEL_THREE_HEADINGS = (
    "점검 내용",
    "점검 목적",
    "보안 위협",
    "참고",
)
SYSTEM_ASSESSMENT_LEVEL_THREE_HEADINGS = (
    "대상",
    "판단 기준",
    "조치 방법",
    "조치 시 영향",
)
LEVEL_TWO = 2
LEVEL_THREE = 3
FORBIDDEN_CATCH_ALL_ROLES = frozenset(
    {
        "rawtranscript",
        "sourceevidence",
        "sourcetranscript",
        "transcript",
        "transcription",
    }
)
NODE_TYPE_FIELDS = frozenset(
    {
        "headingLevel",
        "listType",
        "listDepth",
        "codeLanguage",
        "codeContentType",
        "tableCaption",
        "tableHeaders",
        "tableRows",
        "noteType",
        "assetPath",
        "alternativeText",
    }
)
COMMAND_LINE_PATTERN = re.compile(r"(?m)^#[ \t]+\S.*$")
CONFIGURATION_LINE_PATTERN = re.compile(
    r"(?m)^(?:"
    r"(?:auth|account|password|session)[ \t]+"
    r"(?:required|requisite|sufficient|optional)\b.*|"
    r"[A-Za-z_][A-Za-z0-9_]*[ \t]*(?:=|#)[ \t]*\S.*"
    r")$"
)
CODE_LINE_PATTERN = re.compile(
    r"(?m)^(?:"
    r"#[ \t]+\S.*|"
    r"(?:auth|account|password|session)[ \t]+"
    r"(?:required|requisite|sufficient|optional)\b.*|"
    r"[A-Za-z_][A-Za-z0-9_]*[ \t]*(?:=|#)[ \t]*\S.*"
    r")$"
)


def _require_unique(values: list[JsonValue], *, location: str) -> None:
    """Reject duplicate scalar values outside the Structured Outputs schema subset."""

    serialized_values = [json.dumps(value, ensure_ascii=False, sort_keys=True) for value in values]
    if len(serialized_values) != len(set(serialized_values)):
        msg = f"{location} contains duplicate values"
        raise ValueError(msg)


def _schema_errors(
    document: dict[str, JsonValue],
    schema: dict[str, JsonValue],
) -> list[str]:
    """Return stable JSON Schema error descriptions."""

    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        f"{'.'.join(str(part) for part in error.absolute_path) or '$'}: {error.message}"
        for error in sorted(validator.iter_errors(document), key=lambda item: list(item.path))
    ]


def _page_evidence(task: dict[str, JsonValue]) -> dict[int, dict[str, JsonValue]]:
    """Index immutable task image and navigation evidence by physical page."""

    page_evidence: dict[int, dict[str, JsonValue]] = {}
    for evidence_value in as_sequence(
        task["sourcePageEvidence"],
        location="task.sourcePageEvidence",
    ):
        evidence = as_mapping(evidence_value, location="task.sourcePageEvidence[]")
        physical_page = evidence.get("physicalPage")
        transcript = evidence.get("transcript")
        if not isinstance(physical_page, int) or not isinstance(transcript, str):
            msg = "task page evidence requires a physical page and transcript"
            raise TypeError(msg)
        if physical_page in page_evidence:
            msg = f"task contains duplicate source page evidence: {physical_page}"
            raise ValueError(msg)
        page_evidence[physical_page] = evidence
    return page_evidence


def _normalized_text(value: str) -> str:
    """Normalize whitespace only for declared transcript-alignment checks."""

    return " ".join(value.split())


def _node_searchable_content(node: dict[str, JsonValue]) -> str:
    """Return all source-bearing text represented by one semantic node."""

    values: list[str] = []
    content = node.get("content")
    if isinstance(content, str):
        values.append(content)
    for field_name in ("tableCaption", "alternativeText"):
        value = node.get(field_name)
        if isinstance(value, str):
            values.append(value)
    table_headers = node.get("tableHeaders")
    if isinstance(table_headers, list):
        values.extend(value for value in table_headers if isinstance(value, str))
    table_rows = node.get("tableRows")
    if isinstance(table_rows, list):
        for row in table_rows:
            if isinstance(row, list):
                values.extend(value for value in row if isinstance(value, str))
    return "\n".join(values)


def _node_observed_content_types(node: dict[str, JsonValue]) -> set[str]:
    """Map one node profile to the visual content types it represents."""

    node_type = node.get("nodeType")
    if node_type == "heading":
        content_types = {"heading"}
    elif node_type == "listItem":
        content_types = {"procedure"} if node.get("listType") == "ordered" else {"prose"}
    elif node_type == "codeBlock":
        content_type = node.get("codeContentType")
        content_types = {content_type} if isinstance(content_type, str) else set()
    elif node_type == "table":
        content_types = {"table"}
    elif node_type == "image":
        content_types = {"meaningfulVisual"}
    else:
        content_types = {"prose"}
    if node.get("sourceContentType") == "embeddedImageText":
        content_types.add("embeddedImageText")
    return content_types


def _validate_node_profile(
    node: dict[str, JsonValue],
    *,
    typed_code_contents: tuple[str, ...],
) -> None:
    """Enforce exclusive typed-node fields and reject flattened technical content."""

    node_type = node.get("nodeType")
    required_types: dict[str, tuple[type[object], ...]]
    allowed_non_null_fields: set[str]
    if node_type == "heading":
        required_types = {"headingLevel": (int,)}
        allowed_non_null_fields = {"headingLevel"}
    elif node_type == "listItem":
        required_types = {"listType": (str,), "listDepth": (int,)}
        allowed_non_null_fields = {"listType", "listDepth"}
    elif node_type == "codeBlock":
        required_types = {"codeLanguage": (str,), "codeContentType": (str,)}
        allowed_non_null_fields = {"codeLanguage", "codeContentType"}
    elif node_type == "table":
        required_types = {
            "tableCaption": (str,),
            "tableHeaders": (list,),
            "tableRows": (list,),
        }
        allowed_non_null_fields = {"tableCaption", "tableHeaders", "tableRows"}
    elif node_type == "note":
        required_types = {"noteType": (str,)}
        allowed_non_null_fields = {"noteType"}
    elif node_type == "image":
        required_types = {"assetPath": (str,), "alternativeText": (str,)}
        allowed_non_null_fields = {"assetPath", "alternativeText"}
    else:
        required_types = {}
        allowed_non_null_fields = set()
    invalid_fields = [
        field_name
        for field_name, allowed_types in required_types.items()
        if not isinstance(node.get(field_name), allowed_types)
    ]
    if invalid_fields:
        msg = f"{node_type} node has invalid type-specific fields: {', '.join(invalid_fields)}"
        raise ValueError(msg)
    unexpected_fields = sorted(
        field_name
        for field_name in NODE_TYPE_FIELDS - allowed_non_null_fields
        if node.get(field_name) is not None
    )
    if unexpected_fields:
        msg = (
            f"{node_type} node has non-null fields for another node type: "
            f"{', '.join(unexpected_fields)}"
        )
        raise ValueError(msg)

    content = node.get("content")
    if not isinstance(content, str):
        msg = f"{node_type} node content must be a string"
        raise TypeError(msg)
    if node_type in {"table", "image"}:
        if content:
            msg = f"{node_type} node content must be empty; use its typed fields"
            raise ValueError(msg)
    elif not content:
        msg = f"{node_type} node content must not be empty"
        raise ValueError(msg)

    if node_type == "table":
        headers = cast("list[JsonValue]", node["tableHeaders"])
        rows = cast("list[JsonValue]", node["tableRows"])
        if not rows:
            msg = "table node must contain at least one row"
            raise ValueError(msg)
        header_count = len(headers)
        if any(not isinstance(row, list) or len(row) != header_count for row in rows):
            msg = "table node rows must have the same column count as its headers"
            raise ValueError(msg)

    source_content_type = node.get("sourceContentType")
    if node_type == "image" and source_content_type != "meaningfulVisual":
        msg = "image node must represent a meaningfulVisual"
        raise ValueError(msg)
    if node_type != "image" and source_content_type == "meaningfulVisual":
        msg = "meaningfulVisual content must use an image node"
        raise ValueError(msg)
    if node_type == "image" and source_content_type == "embeddedImageText":
        msg = "embedded image text must use a typed text, code, or table node"
        raise ValueError(msg)
    if (
        source_content_type == "derivedStructure"
        and node.get("publicationDisposition") != "derived"
    ):
        msg = "derivedStructure node must have a derived publication disposition"
        raise ValueError(msg)

    semantic_role = node.get("semanticRole")
    normalized_role = (
        re.sub(r"[^a-z]", "", semantic_role.casefold()) if isinstance(semantic_role, str) else ""
    )
    if normalized_role in FORBIDDEN_CATCH_ALL_ROLES:
        msg = f"Codex result uses a forbidden transcript catch-all role: {semantic_role}"
        raise ValueError(msg)

    if node_type != "codeBlock":
        for match in CODE_LINE_PATTERN.finditer(content):
            matched_line = match.group(0)
            if not any(code_content in matched_line for code_content in typed_code_contents):
                msg = (
                    f"{node_type} node contains command or configuration text "
                    "that requires codeBlock"
                )
                raise ValueError(msg)
    if node_type != "table" and "옵션 설명" in content and len(content.splitlines()) > 1:
        msg = f"{node_type} node flattens visually tabular option text"
        raise ValueError(msg)


def _navigation_semantic_hints(transcript: str) -> set[str]:
    """Return conservative structure hints from the non-authoritative transcript."""

    hints: set[str] = set()
    if re.search(r"(?m)^Step[ \t]+[0-9]+\)", transcript):
        hints.add("procedure")
    if "옵션 설명" in transcript:
        hints.add("table")
    if CONFIGURATION_LINE_PATTERN.search(transcript):
        hints.add("configuration")
    if COMMAND_LINE_PATTERN.search(transcript):
        hints.add("command")
    if re.search(r"(?m)^(?:Profile ID|Enabled features):", transcript):
        hints.add("output")
    return hints


def _validate_no_transcript_dump(
    nodes: list[dict[str, JsonValue]],
    page_evidence: dict[int, dict[str, JsonValue]],
    node_pages: dict[str, set[int]],
) -> None:
    """Reject raw transcript publication and missing conservative semantic structure."""

    for physical_page, evidence in page_evidence.items():
        transcript = cast("str", evidence["transcript"])
        normalized_transcript = _normalized_text(transcript)
        page_nodes = [
            node
            for node in nodes
            if physical_page in node_pages[cast("str", node["nodeIdentifier"])]
        ]
        for node in page_nodes:
            if node.get("nodeType") in {"codeBlock", "table", "image"}:
                continue
            if _normalized_text(_node_searchable_content(node)) == normalized_transcript:
                msg = f"page {physical_page} transcript was emitted as one untyped node"
                raise ValueError(msg)
        paragraph_text = "\n".join(
            cast("str", node["content"])
            for node in page_nodes
            if node.get("nodeType") == "paragraph"
            and node.get("sourceContentType") != "derivedStructure"
        )
        if paragraph_text and _normalized_text(paragraph_text) == normalized_transcript:
            msg = f"page {physical_page} transcript was split only into paragraphs"
            raise ValueError(msg)

        represented_types: set[str] = set()
        for node in page_nodes:
            represented_types.update(_node_observed_content_types(node))
        missing_hints = _navigation_semantic_hints(transcript) - represented_types
        if missing_hints:
            msg = (
                f"page {physical_page} lacks typed nodes for conservative transcript navigation "
                f"hints: {sorted(missing_hints)!r}"
            )
            raise ValueError(msg)


def _validate_source_page_inspections(
    result: dict[str, JsonValue],
    page_evidence: dict[int, dict[str, JsonValue]],
    nodes: list[dict[str, JsonValue]],
    node_pages: dict[str, set[int]],
) -> set[int]:
    """Bind one vision-inspection attestation to every image and its semantic nodes."""

    nodes_by_identifier = {cast("str", node["nodeIdentifier"]): node for node in nodes}
    inspections: dict[int, dict[str, JsonValue]] = {}
    uncertain_pages: set[int] = set()
    for inspection_value in as_sequence(
        result["sourcePageInspections"],
        location="result.sourcePageInspections",
    ):
        inspection = as_mapping(
            inspection_value,
            location="result.sourcePageInspections[]",
        )
        physical_page = inspection.get("physicalPage")
        if not isinstance(physical_page, int):
            msg = "source page inspection physical page must be an integer"
            raise TypeError(msg)
        if physical_page in inspections:
            msg = f"Codex result contains duplicate source page inspection: {physical_page}"
            raise ValueError(msg)
        inspections[physical_page] = inspection
        expected_evidence = page_evidence.get(physical_page)
        if expected_evidence is None:
            msg = f"source page inspection references a page outside the task: {physical_page}"
            raise ValueError(msg)
        for field_name in ("pageRegionIdentifier", "imagePath", "imageChecksum"):
            if inspection.get(field_name) != expected_evidence.get(field_name):
                msg = (
                    f"source page inspection {physical_page} {field_name} "
                    "differs from task evidence"
                )
                raise ValueError(msg)

        observed_identifiers = as_sequence(
            inspection["observedNodeIdentifiers"],
            location="sourcePageInspection.observedNodeIdentifiers",
        )
        _require_unique(
            observed_identifiers,
            location="sourcePageInspection.observedNodeIdentifiers",
        )
        expected_identifiers = {
            node_identifier
            for node_identifier, physical_pages in node_pages.items()
            if physical_page in physical_pages
        }
        if set(cast("list[str]", observed_identifiers)) != expected_identifiers:
            msg = (
                f"source page inspection {physical_page} observed nodes differ from node provenance"
            )
            raise ValueError(msg)

        observed_content_types = as_sequence(
            inspection["observedContentTypes"],
            location="sourcePageInspection.observedContentTypes",
        )
        _require_unique(
            observed_content_types,
            location="sourcePageInspection.observedContentTypes",
        )
        expected_content_types: set[str] = set()
        for node_identifier in expected_identifiers:
            expected_content_types.update(
                _node_observed_content_types(nodes_by_identifier[node_identifier])
            )
        if set(cast("list[str]", observed_content_types)) != expected_content_types:
            msg = f"source page inspection {physical_page} content types differ from typed nodes"
            raise ValueError(msg)

        inspection_status = inspection.get("inspectionStatus")
        uncertainty_description = inspection.get("uncertaintyDescription")
        if inspection_status == "visionInspected":
            if uncertainty_description is not None:
                msg = f"source page inspection {physical_page} is clear but describes uncertainty"
                raise ValueError(msg)
        elif not isinstance(uncertainty_description, str):
            msg = f"source page inspection {physical_page} must describe its uncertainty"
            raise ValueError(msg)
        else:
            uncertain_pages.add(physical_page)

    if set(inspections) != set(page_evidence):
        msg = "Codex result must include one vision inspection for every source page image"
        raise ValueError(msg)
    return uncertain_pages


def validate_codex_result(
    result_path: Path,
    task_path: Path,
    *,
    root: Path | None = None,
) -> dict[str, JsonValue]:
    """Validate schema, identity, page coverage, and exact literal preservation."""

    repository = root or repository_root()
    task = load_codex_task(task_path, root=repository)
    verify_codex_task_dependencies(task, root=repository)
    result = load_json(result_path)
    schema = load_json(repository / RESULT_SCHEMA_PATH)
    schema_errors = _schema_errors(result, schema)
    if schema_errors:
        msg = f"invalid Codex result {result_path}: {'; '.join(schema_errors)}"
        raise ValueError(msg)

    identity_fields = (
        "taskIdentifier",
        "taskChecksum",
        "criterionCode",
        "criterionSlug",
        "sourceDocumentIdentifier",
        "sourceDocumentChecksum",
        "sourcePageStart",
        "sourcePageEnd",
    )
    mismatched_fields = [
        field_name
        for field_name in identity_fields
        if result.get(field_name) != task.get(field_name)
    ]
    if mismatched_fields:
        msg = f"Codex result identity differs from task: {', '.join(mismatched_fields)}"
        raise ValueError(msg)

    _require_unique(
        as_sequence(result["targetIdentifiers"], location="result.targetIdentifiers"),
        location="result.targetIdentifiers",
    )

    page_evidence = _page_evidence(task)
    expected_pages = set(page_evidence)
    quality = as_mapping(result["quality"], location="result.quality")
    for quality_field in (
        "reviewedPhysicalPages",
        "preservedTechnicalLiterals",
        "unresolvedQuestions",
    ):
        _require_unique(
            as_sequence(quality[quality_field], location=f"result.quality.{quality_field}"),
            location=f"result.quality.{quality_field}",
        )
    reviewed_pages = set(
        cast(
            "list[int]",
            as_sequence(
                quality["reviewedPhysicalPages"],
                location="result.quality.reviewedPhysicalPages",
            ),
        )
    )
    if reviewed_pages != expected_pages:
        msg = "Codex result must confirm every source page image as vision inspected"
        raise ValueError(msg)

    nodes = [
        as_mapping(value, location="result.nodes[]")
        for value in as_sequence(result["nodes"], location="result.nodes")
    ]
    typed_code_contents = tuple(
        cast("str", node["content"])
        for node in nodes
        if node.get("nodeType") == "codeBlock" and isinstance(node.get("content"), str)
    )
    node_identifiers = [node.get("nodeIdentifier") for node in nodes]
    if len(node_identifiers) != len(set(node_identifiers)):
        msg = "Codex result contains duplicate node identifiers"
        raise ValueError(msg)
    node_pages: dict[str, set[int]] = {}
    uncertain_node_identifiers: set[str] = set()
    uncertain_span_pages: set[int] = set()
    for node in nodes:
        _validate_node_profile(node, typed_code_contents=typed_code_contents)
        node_identifier = cast("str", node["nodeIdentifier"])
        node_pages[node_identifier] = set()
        evidence_origins: set[str] = set()
        for span_value in as_sequence(node["sourceSpans"], location="node.sourceSpans"):
            span = as_mapping(span_value, location="node.sourceSpans[]")
            physical_page = span.get("physicalPage")
            source_excerpt = span.get("sourceTextExcerpt")
            if not isinstance(physical_page, int):
                msg = "node source span physical page must be an integer"
                raise TypeError(msg)
            if physical_page not in expected_pages:
                msg = f"node references page outside the task: {physical_page}"
                raise ValueError(msg)
            evidence = page_evidence[physical_page]
            expected_region = evidence["pageRegionIdentifier"]
            if span.get("pageRegionIdentifier") != expected_region:
                msg = (
                    f"node references an unexpected page region: {span.get('pageRegionIdentifier')}"
                )
                raise ValueError(msg)
            if not isinstance(source_excerpt, str):
                msg = "node source excerpt must be a string"
                raise TypeError(msg)
            transcript = cast("str", evidence["transcript"])
            transcript_alignment = span.get("transcriptAlignment")
            if transcript_alignment == "exact" and source_excerpt not in transcript:
                msg = f"node exact source excerpt is absent from page {physical_page} transcript"
                raise ValueError(msg)
            if transcript_alignment == "notPresent" and _normalized_text(
                source_excerpt
            ) in _normalized_text(transcript):
                msg = (
                    f"node source excerpt on page {physical_page} is present in the transcript but "
                    "declared notPresent"
                )
                raise ValueError(msg)

            evidence_origin = span.get("evidenceOrigin")
            if isinstance(evidence_origin, str):
                evidence_origins.add(evidence_origin)
            recognition_status = span.get("recognitionStatus")
            uncertainty_description = span.get("uncertaintyDescription")
            if recognition_status == "clear":
                if uncertainty_description is not None:
                    msg = f"clear source span for {node_identifier} describes uncertainty"
                    raise ValueError(msg)
            elif not isinstance(uncertainty_description, str):
                msg = f"uncertain source span for {node_identifier} needs a description"
                raise ValueError(msg)
            else:
                uncertain_node_identifiers.add(node_identifier)
                uncertain_span_pages.add(physical_page)
            node_pages[node_identifier].add(physical_page)

        source_content_type = node.get("sourceContentType")
        if source_content_type == "embeddedImageText" and not evidence_origins.intersection(
            {"embeddedImage", "mixed"}
        ):
            msg = f"embedded image text node {node_identifier} lacks embedded-image provenance"
            raise ValueError(msg)
        if source_content_type == "pageText" and "embeddedImage" in evidence_origins:
            msg = f"page text node {node_identifier} has embedded-image-only provenance"
            raise ValueError(msg)

    referenced_pages = set().union(*node_pages.values()) if node_pages else set()
    if referenced_pages != expected_pages:
        msg = "Codex result must emit semantic nodes from every source page image"
        raise ValueError(msg)

    inspection_uncertain_pages = _validate_source_page_inspections(
        result,
        page_evidence,
        nodes,
        node_pages,
    )
    _validate_no_transcript_dump(nodes, page_evidence, node_pages)

    annotation_identifiers: list[JsonValue] = []
    review_annotation_pages: set[int] = set()
    vision_uncertain_annotation_pages: set[int] = set()
    uncertain_annotation_targets: set[str] = set()
    for annotation_value in as_sequence(
        result["sourceAnnotations"],
        location="result.sourceAnnotations",
    ):
        annotation = as_mapping(annotation_value, location="result.sourceAnnotations[]")
        annotation_identifiers.append(annotation["annotationIdentifier"])
        target_reference = annotation.get("targetReference")
        if target_reference not in node_identifiers and not (
            isinstance(target_reference, str) and target_reference.startswith("/")
        ):
            msg = f"annotation target does not resolve: {target_reference}"
            raise ValueError(msg)
        annotation_pages = set(
            cast(
                "list[int]",
                as_sequence(annotation["physicalPages"], location="annotation.physicalPages"),
            )
        )
        _require_unique(
            as_sequence(annotation["physicalPages"], location="annotation.physicalPages"),
            location="annotation.physicalPages",
        )
        if not annotation_pages <= expected_pages:
            msg = f"annotation references pages outside the task: {sorted(annotation_pages)}"
            raise ValueError(msg)
        if annotation.get("annotationType") == "conversionUncertainty":
            vision_uncertain_annotation_pages.update(annotation_pages)
            review_annotation_pages.update(annotation_pages)
            if isinstance(target_reference, str):
                uncertain_annotation_targets.add(target_reference)
        elif annotation.get("disposition") in {"unresolved", "reviewRequired"}:
            review_annotation_pages.update(annotation_pages)
            if isinstance(target_reference, str):
                uncertain_annotation_targets.add(target_reference)
    if len(annotation_identifiers) != len(set(annotation_identifiers)):
        msg = "Codex result contains duplicate annotation identifiers"
        raise ValueError(msg)

    unresolved_questions = as_sequence(
        quality["unresolvedQuestions"],
        location="result.quality.unresolvedQuestions",
    )
    uncertainty_pages = uncertain_span_pages | inspection_uncertain_pages | review_annotation_pages
    if (uncertain_span_pages | vision_uncertain_annotation_pages) - inspection_uncertain_pages:
        msg = "pages with uncertain OCR or annotations need uncertain vision inspections"
        raise ValueError(msg)
    if (
        (uncertain_node_identifiers or inspection_uncertain_pages)
        and not unresolved_questions
        and not uncertain_annotation_targets
    ):
        msg = "vision or OCR uncertainty needs an annotation or unresolved question"
        raise ValueError(msg)
    has_uncertainty = bool(uncertainty_pages or unresolved_questions)
    analysis_status = result.get("analysisStatus")
    semantic_coverage_status = quality.get("semanticCoverageStatus")
    if analysis_status == "complete":
        if has_uncertainty or semantic_coverage_status != "complete":
            msg = "complete analysis cannot contain unresolved vision or OCR uncertainty"
            raise ValueError(msg)
    elif not has_uncertainty or semantic_coverage_status != "completeWithUncertainty":
        msg = "needsSourceReview requires explicit uncertainty and incomplete certainty coverage"
        raise ValueError(msg)
    if has_uncertainty and quality.get("confidenceLevel") == "high":
        msg = "vision or OCR uncertainty cannot have high confidence"
        raise ValueError(msg)

    required_literals = set(
        cast(
            "list[str]",
            as_sequence(
                task["requiredTechnicalLiterals"],
                location="task.requiredTechnicalLiterals",
            ),
        )
    )
    preserved_literals = set(
        cast(
            "list[str]",
            as_sequence(
                quality["preservedTechnicalLiterals"],
                location="result.quality.preservedTechnicalLiterals",
            ),
        )
    )
    combined_result_content = "\n".join(_node_searchable_content(node) for node in nodes)
    combined_result_content += "\n" + "\n".join(
        cast("str", annotation["sourceText"])
        for annotation in (
            as_mapping(value, location="result.sourceAnnotations[]")
            for value in as_sequence(
                result["sourceAnnotations"],
                location="result.sourceAnnotations",
            )
        )
        if isinstance(annotation.get("sourceText"), str)
    )
    missing_literal_declarations = required_literals - preserved_literals
    missing_literal_content = {
        literal for literal in required_literals if literal not in combined_result_content
    }
    if missing_literal_declarations or missing_literal_content:
        msg = (
            "Codex result did not preserve every required technical literal; "
            f"declarations={sorted(missing_literal_declarations)!r}, "
            f"content={sorted(missing_literal_content)!r}"
        )
        raise ValueError(msg)

    heading_nodes = [node for node in nodes if node.get("nodeType") == "heading"]
    heading_levels = [cast("int", node["headingLevel"]) for node in heading_nodes]
    if heading_levels and heading_levels[0] != LEVEL_TWO:
        msg = "Codex result must start its heading hierarchy at level 2"
        raise ValueError(msg)
    if any(
        current_level > previous_level + 1
        for previous_level, current_level in pairwise(heading_levels)
    ):
        msg = "Codex result heading hierarchy skips a level"
        raise ValueError(msg)
    if result.get("contentModelRecommendation") == "systemCriterion":
        level_two_headings = tuple(
            cast("str", node["content"])
            for node in heading_nodes
            if node.get("headingLevel") == LEVEL_TWO
        )
        if level_two_headings != SYSTEM_LEVEL_TWO_HEADINGS:
            msg = f"systemCriterion H2 sequence differs: {level_two_headings!r}"
            raise ValueError(msg)
        current_level_two_heading: str | None = None
        level_three_headings_by_section: dict[str, list[str]] = {
            heading: [] for heading in SYSTEM_LEVEL_TWO_HEADINGS
        }
        for heading_node in heading_nodes:
            heading_level = heading_node.get("headingLevel")
            heading_content = cast("str", heading_node["content"])
            if heading_level == LEVEL_TWO:
                current_level_two_heading = heading_content
            elif (
                heading_level == LEVEL_THREE
                and current_level_two_heading in level_three_headings_by_section
            ):
                level_three_headings_by_section[current_level_two_heading].append(heading_content)
        overview_headings = tuple(level_three_headings_by_section["개요"])
        assessment_headings = tuple(level_three_headings_by_section["점검 대상 및 판단 기준"])
        remediation_headings = tuple(level_three_headings_by_section["점검 및 조치 사례"])
        if overview_headings != SYSTEM_OVERVIEW_LEVEL_THREE_HEADINGS:
            msg = f"systemCriterion overview H3 sequence differs: {overview_headings!r}"
            raise ValueError(msg)
        if assessment_headings != SYSTEM_ASSESSMENT_LEVEL_THREE_HEADINGS:
            msg = f"systemCriterion assessment H3 sequence differs: {assessment_headings!r}"
            raise ValueError(msg)
        if not remediation_headings:
            msg = "systemCriterion remediation requires at least one target H3"
            raise ValueError(msg)
    return result


def _fence(content: str) -> str:
    """Return a tilde fence that cannot collide with code content."""

    maximum_run = max((len(match.group()) for match in re.finditer(r"~+", content)), default=0)
    return "~" * max(3, maximum_run + 1)


def _table_cell(value: str) -> str:
    """Escape one GFM table cell without altering its source value."""

    return value.replace("|", "\\|").replace("\n", "<br>")


def _render_node(node: dict[str, JsonValue]) -> list[str]:
    """Render one validated Codex node into review Markdown."""

    node_type = cast("str", node["nodeType"])
    content = cast("str", node["content"])
    if node_type == "heading":
        return ["#" * cast("int", node["headingLevel"]) + " " + content, ""]
    if node_type == "paragraph":
        return [content, ""]
    if node_type == "listItem":
        indentation = "  " * (cast("int", node["listDepth"]) - 1)
        marker = "1." if node["listType"] == "ordered" else "-"
        return [f"{indentation}{marker} {content}", ""]
    if node_type == "codeBlock":
        fence = _fence(content)
        return [
            f"{fence}{node['codeLanguage']} {node['codeContentType']}",
            content,
            fence,
            "",
        ]
    if node_type == "table":
        headers = [
            _table_cell(cast("str", value))
            for value in as_sequence(node["tableHeaders"], location="node.tableHeaders")
        ]
        rows = [
            [
                _table_cell(cast("str", value))
                for value in as_sequence(row_value, location="node.tableRows[]")
            ]
            for row_value in as_sequence(node["tableRows"], location="node.tableRows")
        ]
        return [
            f"**{node['tableCaption']}**",
            "",
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
            *("| " + " | ".join(row) + " |" for row in rows),
            "",
        ]
    if node_type == "note":
        return [
            f"> **{node['noteType']}**",
            ">",
            *(f"> {line}" for line in content.splitlines()),
            "",
        ]
    if node_type == "image":
        asset_path = cast("str", node["assetPath"])
        return [f"![{node['alternativeText']}](../../../../{asset_path.lstrip('/')})", ""]
    msg = f"unsupported Codex node type: {node_type}"
    raise ValueError(msg)


def render_codex_candidate(
    result_path: Path,
    task_path: Path,
    *,
    root: Path | None = None,
    work_directory: Path | None = None,
) -> Path:
    """Validate a result and render a non-canonical Markdown candidate."""

    repository = root or repository_root()
    result = validate_codex_result(result_path, task_path, root=repository)
    slug = cast("str", result["criterionSlug"])
    output_root = work_directory or repository / DEFAULT_WORK_DIRECTORY
    candidate_directory = output_root / "candidates" / slug
    candidate_directory.mkdir(parents=True, exist_ok=True)
    candidate_path = candidate_directory / "candidate.md"
    lines = [
        f"# {result['criterionCode']} {result['title']}",
        "",
        "> **편집자 주**",
        ">",
        "> Codex가 생성한 검토용 후보입니다. Canonical 콘텐츠나 사람 승인 상태가 아닙니다.",
        "",
    ]
    for node_value in as_sequence(result["nodes"], location="result.nodes"):
        lines.extend(_render_node(as_mapping(node_value, location="result.nodes[]")))
    annotation_values = as_sequence(
        result["sourceAnnotations"],
        location="result.sourceAnnotations",
    )
    if annotation_values:
        lines.extend(["## 원문 이상 및 확인 필요", ""])
        for annotation_value in annotation_values:
            annotation = as_mapping(annotation_value, location="result.sourceAnnotations[]")
            lines.extend(
                [
                    f"- **{annotation['annotationType']}**: {annotation['explanation']}",
                    f"  - 원문: `{annotation['sourceText']}`",
                    f"  - 상태: `{annotation['disposition']}`",
                ]
            )
        lines.append("")
    candidate_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    report = {
        "schemaVersion": 2,
        "taskIdentifier": result["taskIdentifier"],
        "taskChecksum": result["taskChecksum"],
        "resultChecksum": sha256_file(result_path),
        "candidateChecksum": sha256_file(candidate_path),
        "validationStatus": "passed",
        "canonicalApplied": False,
    }
    (candidate_directory / "validation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return candidate_path


def _argument_parser() -> argparse.ArgumentParser:
    """Build the result-importer command-line parser."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug", help="criterion slug such as u-03")
    parser.add_argument("--work-directory", type=Path, help="generated Codex work directory")
    add_logging_arguments(parser)
    return parser


def main() -> int:
    """Validate and render one Codex result candidate."""

    arguments = _argument_parser().parse_args()
    with configure_runtime_logging(
        "codex_result_importer",
        level=arguments.log_level,
        log_directory=arguments.log_directory,
        context={"slug": arguments.slug},
    ) as logger:
        logger.info(
            "Codex result import started",
            event="command.started",
            work_directory=(
                str(arguments.work_directory) if arguments.work_directory is not None else None
            ),
        )
        repository = repository_root()
        output_root = arguments.work_directory or repository / DEFAULT_WORK_DIRECTORY
        task_path = output_root / "tasks" / arguments.slug / "task.json"
        result_path = output_root / "results" / arguments.slug / "result.json"
        try:
            candidate_path = render_codex_candidate(
                result_path,
                task_path,
                root=repository,
                work_directory=output_root,
            )
        except (FileNotFoundError, TypeError, ValueError) as error:
            logger.exception(
                "Codex result import failed",
                event="command.failed",
                error=error,
                result_path=str(result_path),
                task_path=str(task_path),
            )
            print(str(error), file=sys.stderr)
            return 1
        logger.info(
            "Codex result import completed",
            event="command.completed",
            output_path=str(candidate_path),
        )
        print(candidate_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
