"""Build deterministic criterion evidence packages for read-only Codex runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import cast

import rfc8785
from jsonschema import Draft202012Validator, FormatChecker

from conversion.common import (
    JsonValue,
    as_mapping,
    as_sequence,
    criterion_source_checksum,
    extract_leaf_blocks,
    heading_identifiers,
    load_criterion,
    load_json,
    load_yaml,
    provenance_by_reference,
    repository_root,
    sha256_file,
)

PROMPT_VERSION = 1
DEFAULT_WORK_DIRECTORY = Path("work/codex")
PROMPT_TEMPLATE_PATH = Path("codex_prompts/criterion-structure-v1.md")
RESULT_SCHEMA_PATH = Path("schemas/codex-criterion-result.schema.json")
TASK_SCHEMA_PATH = Path("schemas/codex-criterion-task.schema.json")
CONVERSION_POLICY_PATH = Path("CONVERSION_POLICY.md")
PATH_LITERAL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])/?(?:etc|var|usr|lib|tcb)(?:/[A-Za-z0-9.*_+~-]+)+"
)
UPPERCASE_LITERAL_PATTERN = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")
MODULE_LITERAL_PATTERN = re.compile(r"\bpam_[a-z0-9_.-]+\b")
LOWERCASE_OPTION_PATTERN = re.compile(
    r"\b(?:audit|deny|no_magic_root|reset|silent|unlock_time|with-faillock)\b"
)


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


def calculate_codex_task_checksum(document: dict[str, JsonValue]) -> str:
    """Calculate the checksum of a task without its self-referential field."""

    checksum_payload = dict(document)
    checksum_payload.pop("taskChecksum", None)
    return hashlib.sha256(rfc8785.dumps(checksum_payload)).hexdigest()


def load_codex_task(path: Path, *, root: Path | None = None) -> dict[str, JsonValue]:
    """Load and validate one generated Codex task package."""

    repository = root or repository_root()
    document = load_json(path)
    schema = load_json(repository / TASK_SCHEMA_PATH)
    errors = _schema_errors(document, schema)
    if errors:
        msg = f"invalid Codex task {path}: {'; '.join(errors)}"
        raise ValueError(msg)
    expected_checksum = calculate_codex_task_checksum(document)
    if document.get("taskChecksum") != expected_checksum:
        msg = f"Codex task checksum mismatch: {path}"
        raise ValueError(msg)
    return document


def verify_codex_task_dependencies(
    task: dict[str, JsonValue],
    *,
    root: Path | None = None,
) -> None:
    """Reject a task when policy, prompt, or result schema changed after export."""

    repository = root or repository_root()
    expected_files = (
        (PROMPT_TEMPLATE_PATH, "promptTemplateChecksum"),
        (RESULT_SCHEMA_PATH, "resultSchemaChecksum"),
        (CONVERSION_POLICY_PATH, "conversionPolicyChecksum"),
    )
    for relative_path, checksum_field in expected_files:
        expected_checksum = task.get(checksum_field)
        if (
            not isinstance(expected_checksum, str)
            or sha256_file(repository / relative_path) != expected_checksum
        ):
            msg = f"task dependency changed: {relative_path}"
            raise ValueError(msg)


def _manifest_record(slug: str, *, root: Path) -> dict[str, JsonValue]:
    """Return the unique manifest record for one criterion slug."""

    manifest = load_yaml(root / "data/criteria-manifest.yaml")
    matches = [
        as_mapping(value, location="manifest.criteria[]")
        for value in as_sequence(manifest["criteria"], location="manifest.criteria")
        if isinstance(value, dict) and value.get("slug") == slug
    ]
    if len(matches) != 1:
        msg = f"expected one manifest record for {slug}, got {len(matches)}"
        raise ValueError(msg)
    return matches[0]


def _source_document_checksum(*, root: Path) -> tuple[str, str]:
    """Return the canonical source document identifier and checksum."""

    registry = load_yaml(root / "data/source-registry.yaml")
    documents = as_sequence(registry["documents"], location="sourceRegistry.documents")
    if len(documents) != 1:
        msg = "Codex task builder requires exactly one source document"
        raise ValueError(msg)
    document = as_mapping(documents[0], location="sourceRegistry.documents[0]")
    identifier = document.get("sourceDocumentIdentifier")
    checksum = document.get("checksumValue")
    if not isinstance(identifier, str) or not isinstance(checksum, str):
        msg = "source registry identifier and checksum must be strings"
        raise TypeError(msg)
    return identifier, checksum


def _technical_literals(transcripts: list[str]) -> list[str]:
    """Extract conservative exact literals that Codex must preserve."""

    joined_text = "\n".join(transcripts)
    literals = {
        match.group(0)
        for pattern in (
            PATH_LITERAL_PATTERN,
            UPPERCASE_LITERAL_PATTERN,
            MODULE_LITERAL_PATTERN,
            LOWERCASE_OPTION_PATTERN,
        )
        for match in pattern.finditer(joined_text)
    }
    return sorted(literals, key=lambda value: value.encode())


def _page_evidence(
    *,
    slug: str,
    domain_identifier: str,
    criterion_body: str,
    provenance: dict[str, JsonValue],
    root: Path,
) -> list[JsonValue]:
    """Join transcription blocks and visual assets by physical page."""

    taxonomy = load_yaml(root / "data/taxonomy.yaml")
    leaf_blocks = extract_leaf_blocks(
        criterion_body,
        criterion_slug=slug,
        heading_identifier_mapping=heading_identifiers(taxonomy),
    )
    source_spans = provenance_by_reference(provenance)
    transcripts_by_page: dict[int, tuple[str, dict[str, JsonValue]]] = {}
    for block in leaf_blocks:
        if block.code_content_type != "transcription":
            continue
        spans = source_spans[block.block_reference]
        if len(spans) != 1 or not isinstance(spans[0].get("physicalPage"), int):
            msg = f"{block.block_reference} must reference one physical page"
            raise ValueError(msg)
        physical_page = cast("int", spans[0]["physicalPage"])
        transcripts_by_page[physical_page] = (block.content, spans[0])

    assets_by_page: dict[int, dict[str, JsonValue]] = {}
    for asset_value in as_sequence(provenance["assets"], location="provenance.assets"):
        asset = as_mapping(asset_value, location="provenance.assets[]")
        asset_spans = as_sequence(asset["sourceSpans"], location="asset.sourceSpans")
        if len(asset_spans) != 1 or not isinstance(asset_spans[0], dict):
            msg = f"asset {asset.get('path')} must reference one source span"
            raise ValueError(msg)
        physical_page = asset_spans[0].get("physicalPage")
        if not isinstance(physical_page, int):
            msg = f"asset {asset.get('path')} has no physical page"
            raise TypeError(msg)
        assets_by_page[physical_page] = asset

    if set(transcripts_by_page) != set(assets_by_page):
        msg = f"{slug} transcription pages and source images differ"
        raise ValueError(msg)

    evidence: list[JsonValue] = []
    for physical_page in sorted(transcripts_by_page):
        transcript, source_span = transcripts_by_page[physical_page]
        asset = assets_by_page[physical_page]
        raw_asset_path = asset.get("path")
        if not isinstance(raw_asset_path, str):
            msg = f"{slug} page {physical_page} asset path must be a string"
            raise TypeError(msg)
        asset_path = (root / domain_identifier / raw_asset_path).resolve()
        evidence.append(
            {
                "physicalPage": physical_page,
                "printedPage": cast("str", source_span["printedPage"]),
                "pageRegionIdentifier": cast("str", source_span["pageRegionIdentifier"]),
                "transcript": transcript,
                "imagePath": asset_path.relative_to(root).as_posix(),
                "imageChecksum": sha256_file(asset_path),
            }
        )
    return evidence


def build_codex_task(
    slug: str,
    *,
    root: Path | None = None,
    work_directory: Path | None = None,
) -> Path:
    """Build one deterministic task JSON file for an extracted criterion."""

    repository = root or repository_root()
    manifest_record = _manifest_record(slug, root=repository)
    if manifest_record.get("contentModel") != "extractedCriterion":
        msg = f"{slug} is not an extractedCriterion"
        raise ValueError(msg)
    domain_identifier = manifest_record.get("domainIdentifier")
    if not isinstance(domain_identifier, str):
        msg = f"{slug} has no domain identifier"
        raise TypeError(msg)
    criterion_path = repository / domain_identifier / f"{slug}.md"
    provenance_path = repository / domain_identifier / f"{slug}.provenance.yaml"
    criterion = load_criterion(criterion_path)
    provenance = load_yaml(provenance_path)
    evidence = _page_evidence(
        slug=slug,
        domain_identifier=domain_identifier,
        criterion_body=criterion.body,
        provenance=provenance,
        root=repository,
    )
    transcripts = [
        cast("str", as_mapping(value, location="sourcePageEvidence[]")["transcript"])
        for value in evidence
    ]
    source_identifier, source_checksum = _source_document_checksum(root=repository)
    page_ranges = as_sequence(
        as_mapping(criterion.metadata["provenance"], location="criterion.provenance")[
            "sourcePageRanges"
        ],
        location="criterion.provenance.sourcePageRanges",
    )
    if len(page_ranges) != 1:
        msg = f"{slug} must have one source page range"
        raise ValueError(msg)
    page_range = as_mapping(page_ranges[0], location="sourcePageRanges[0]")
    criterion_metadata = as_mapping(criterion.metadata["criterion"], location="criterion.criterion")
    paths: dict[str, JsonValue] = {
        "criterionMarkdown": criterion_path.relative_to(repository).as_posix(),
        "criterionProvenance": provenance_path.relative_to(repository).as_posix(),
        "conversionPolicy": CONVERSION_POLICY_PATH.as_posix(),
        "promptTemplate": PROMPT_TEMPLATE_PATH.as_posix(),
        "resultSchema": RESULT_SCHEMA_PATH.as_posix(),
        "structuredExemplars": ["unix/u-01.md", "unix/u-02.md"],
    }
    task: dict[str, JsonValue] = {
        "schemaVersion": 1,
        "taskIdentifier": f"{slug}-codex-structure-v{PROMPT_VERSION}",
        "taskChecksum": "0" * 64,
        "promptVersion": PROMPT_VERSION,
        "promptTemplateChecksum": sha256_file(repository / PROMPT_TEMPLATE_PATH),
        "resultSchemaChecksum": sha256_file(repository / RESULT_SCHEMA_PATH),
        "conversionPolicyChecksum": sha256_file(repository / CONVERSION_POLICY_PATH),
        "criterionCode": criterion_metadata["code"],
        "criterionSlug": slug,
        "criterionTitle": criterion_metadata["title"],
        "domainIdentifier": domain_identifier,
        "categoryIdentifier": as_mapping(
            criterion.metadata["classification"],
            location="criterion.classification",
        )["categoryIdentifier"],
        "contentModel": "extractedCriterion",
        "criterionSourceChecksum": criterion_source_checksum(
            slug,
            domain_identifier,
            root=repository,
        ),
        "sourceDocumentIdentifier": source_identifier,
        "sourceDocumentChecksum": source_checksum,
        "sourcePageStart": page_range["physicalPageStart"],
        "sourcePageEnd": page_range["physicalPageEnd"],
        "sourcePageEvidence": evidence,
        "requiredTechnicalLiterals": cast("JsonValue", _technical_literals(transcripts)),
        "paths": paths,
    }
    task["taskChecksum"] = calculate_codex_task_checksum(task)
    output_root = work_directory or repository / DEFAULT_WORK_DIRECTORY
    task_path = output_root / "tasks" / slug / "task.json"
    task_path.parent.mkdir(parents=True, exist_ok=True)
    task_path.write_text(
        json.dumps(task, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    load_codex_task(task_path, root=repository)
    return task_path


def _argument_parser() -> argparse.ArgumentParser:
    """Build the task-builder command-line parser."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug", help="criterion slug such as u-03")
    parser.add_argument("--work-directory", type=Path, help="generated Codex work directory")
    return parser


def main() -> int:
    """Build one Codex task package."""

    arguments = _argument_parser().parse_args()
    task_path = build_codex_task(
        arguments.slug,
        work_directory=arguments.work_directory,
    )
    print(task_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
