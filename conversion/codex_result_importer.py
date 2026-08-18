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


def _page_transcripts(task: dict[str, JsonValue]) -> dict[int, str]:
    """Index immutable task transcripts by physical page."""

    transcripts: dict[int, str] = {}
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
        transcripts[physical_page] = transcript
    return transcripts


def _validate_node_profile(node: dict[str, JsonValue]) -> None:
    """Enforce node-type fields that Structured Outputs cannot express conditionally."""

    node_type = node.get("nodeType")
    required_types: dict[str, tuple[type[object], ...]]
    if node_type == "heading":
        required_types = {"headingLevel": (int,)}
    elif node_type == "listItem":
        required_types = {"listType": (str,), "listDepth": (int,)}
    elif node_type == "codeBlock":
        required_types = {"codeLanguage": (str,), "codeContentType": (str,)}
    elif node_type == "table":
        required_types = {
            "tableCaption": (str,),
            "tableHeaders": (list,),
            "tableRows": (list,),
        }
    elif node_type == "note":
        required_types = {"noteType": (str,)}
    elif node_type == "image":
        required_types = {"assetPath": (str,), "alternativeText": (str,)}
    else:
        required_types = {}
    invalid_fields = [
        field_name
        for field_name, allowed_types in required_types.items()
        if not isinstance(node.get(field_name), allowed_types)
    ]
    if invalid_fields:
        msg = f"{node_type} node has invalid type-specific fields: {', '.join(invalid_fields)}"
        raise ValueError(msg)


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

    transcripts = _page_transcripts(task)
    expected_pages = set(transcripts)
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
        msg = "Codex result must confirm every source page as reviewed"
        raise ValueError(msg)

    nodes = [
        as_mapping(value, location="result.nodes[]")
        for value in as_sequence(result["nodes"], location="result.nodes")
    ]
    node_identifiers = [node.get("nodeIdentifier") for node in nodes]
    if len(node_identifiers) != len(set(node_identifiers)):
        msg = "Codex result contains duplicate node identifiers"
        raise ValueError(msg)
    slug = cast("str", task["criterionSlug"])
    for node in nodes:
        _validate_node_profile(node)
        for span_value in as_sequence(node["sourceSpans"], location="node.sourceSpans"):
            span = as_mapping(span_value, location="node.sourceSpans[]")
            physical_page = span.get("physicalPage")
            source_excerpt = span.get("sourceTextExcerpt")
            if not isinstance(physical_page, int):
                msg = "node source span physical page must be an integer"
                raise TypeError(msg)
            expected_region = f"p{physical_page}-{slug}"
            if physical_page not in expected_pages:
                msg = f"node references page outside the task: {physical_page}"
                raise ValueError(msg)
            if span.get("pageRegionIdentifier") != expected_region:
                msg = (
                    f"node references an unexpected page region: {span.get('pageRegionIdentifier')}"
                )
                raise ValueError(msg)
            if (
                not isinstance(source_excerpt, str)
                or source_excerpt not in transcripts[physical_page]
            ):
                msg = f"node source excerpt is absent from page {physical_page} transcript"
                raise ValueError(msg)

    annotation_identifiers: list[JsonValue] = []
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
    if len(annotation_identifiers) != len(set(annotation_identifiers)):
        msg = "Codex result contains duplicate annotation identifiers"
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
    combined_result_content = "\n".join(
        cast("str", node["content"]) for node in nodes if isinstance(node.get("content"), str)
    )
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
        "schemaVersion": 1,
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
    return parser


def main() -> int:
    """Validate and render one Codex result candidate."""

    arguments = _argument_parser().parse_args()
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
        print(str(error), file=sys.stderr)
        return 1
    print(candidate_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
