"""Apply one validated Codex candidate to the canonical criterion package."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import unicodedata
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import cast

from jsonschema import Draft202012Validator, FormatChecker
from ruamel.yaml import YAML

from conversion.codex_result_importer import validate_codex_result
from conversion.codex_task_builder import (
    DEFAULT_WORK_DIRECTORY,
    load_codex_task,
    verify_codex_task_dependencies,
)
from conversion.common import (
    REQUIRED_ASSESSMENT_LEVEL_THREE_HEADINGS,
    REQUIRED_LEVEL_TWO_HEADINGS,
    REQUIRED_OVERVIEW_LEVEL_THREE_HEADINGS,
    SUPPLEMENTARY_GUIDANCE_HEADING,
    JsonValue,
    LeafBlock,
    as_mapping,
    as_sequence,
    criterion_source_checksum,
    extract_leaf_blocks,
    flatten_block_references,
    heading_identifiers,
    load_criterion,
    load_json,
    load_yaml,
    region_source_checksum,
    repository_root,
    sha256_file,
)
from conversion.runtime_logging import add_logging_arguments, configure_runtime_logging
from conversion.validate_content import validate_repository

MANIFEST_PATH = Path("data/criteria-manifest.yaml")
PAGE_REGION_INVENTORY_PATH = Path("data/page-region-inventory.yaml")
REVIEW_REGISTRY_PATH = Path("data/review-registry.yaml")
TAXONOMY_PATH = Path("data/taxonomy.yaml")
CRITERION_METADATA_SCHEMA_PATH = Path("schemas/criterion-metadata.schema.json")
PROVENANCE_SCHEMA_PATH = Path("schemas/provenance-sidecar.schema.json")
MANIFEST_SCHEMA_PATH = Path("schemas/criteria-manifest.schema.json")
REVIEW_SCHEMA_PATH = Path("schemas/review-registry.schema.json")
TAXONOMY_SCHEMA_PATH = Path("schemas/taxonomy.schema.json")
CANONICAL_VALIDATION_SCHEMA_VERSION = 2
CANONICAL_CONTENT_MODEL_VERSION = 1
MAXIMUM_REPORTED_VALIDATION_ISSUES = 10
MAXIMUM_TAXONOMY_IDENTIFIER_LENGTH = 80
TAXONOMY_IDENTIFIER_DIGEST_LENGTH = 8
FRONT_MATTER_SPACED_KEYS = frozenset(
    {"criterion", "classification", "targetScope", "provenance", "sourceAnnotations"}
)
FIXED_CANONICAL_HEADINGS = frozenset(
    {
        *REQUIRED_LEVEL_TWO_HEADINGS,
        *REQUIRED_OVERVIEW_LEVEL_THREE_HEADINGS,
        *REQUIRED_ASSESSMENT_LEVEL_THREE_HEADINGS,
        SUPPLEMENTARY_GUIDANCE_HEADING,
        "부적절한 비밀번호 유형",
        "비밀번호 관리 방법",
    }
)
DYNAMIC_TAXONOMY_COLLECTIONS = ("targets", "protocols", "productFamilies")
VERSION_QUALIFIER_IDENTIFIERS = {
    "미만": "below",
    "이하": "or-earlier",
    "이상": "or-later",
    "초과": "above",
}


@dataclass(frozen=True)
class CandidateInputs:
    """Validated immutable inputs and their canonical manifest record."""

    task: dict[str, JsonValue]
    result: dict[str, JsonValue]
    validation: dict[str, JsonValue]
    manifest: dict[str, JsonValue]
    manifest_record: dict[str, JsonValue]
    task_path: Path
    result_path: Path
    candidate_path: Path
    validation_path: Path


@dataclass(frozen=True)
class CanonicalRender:
    """Rendered Markdown body, sidecar, and node-to-block mapping."""

    body: str
    provenance: dict[str, JsonValue]
    node_block_references: dict[str, tuple[str, ...]]
    removed_source_crop_paths: tuple[Path, ...]


@dataclass(frozen=True)
class PreparedCanonicalPackage:
    """One staged canonical package and its intended source checksum."""

    inputs: CandidateInputs
    slug: str
    domain_identifier: str
    criterion_path: Path
    provenance_path: Path
    markdown_source: str
    provenance_source: str
    provenance: dict[str, JsonValue]
    annotations: list[JsonValue]
    criterion_checksum: str
    removed_source_crop_paths: tuple[Path, ...]


def _yaml_text(value: dict[str, JsonValue], *, top_level_spacing: bool = False) -> str:
    """Serialize canonical YAML using the repository indentation profile."""

    output = StringIO()
    writer = YAML()
    writer.default_flow_style = False
    writer.allow_unicode = True
    writer.width = 4096
    writer.indent(mapping=2, sequence=4, offset=2)
    writer.dump(value, output)
    source = output.getvalue()
    if not top_level_spacing:
        return source
    lines: list[str] = []
    for line in source.splitlines():
        key = line.partition(":")[0] if line and not line.startswith(" ") else ""
        if lines and key in FRONT_MATTER_SPACED_KEYS:
            lines.append("")
        lines.append(line)
    return "\n".join(lines) + "\n"


def _json_text(value: dict[str, JsonValue]) -> str:
    """Serialize deterministic human-readable JSON."""

    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _schema_errors(
    document: dict[str, JsonValue],
    schema: dict[str, JsonValue],
) -> list[str]:
    """Return deterministic JSON Schema error messages."""

    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        f"{'.'.join(str(part) for part in error.absolute_path) or '$'}: {error.message}"
        for error in sorted(validator.iter_errors(document), key=lambda item: list(item.path))
    ]


def _dynamic_heading_labels(inputs: CandidateInputs) -> list[str]:
    """Return non-fixed H3 and H4 labels in validated result order."""

    labels: list[str] = []
    for value in as_sequence(inputs.result["nodes"], location="result.nodes"):
        node = as_mapping(value, location="result.nodes[]")
        content = node.get("content")
        if (
            node.get("nodeType") == "heading"
            and node.get("headingLevel") in {3, 4}
            and isinstance(content, str)
            and content not in FIXED_CANONICAL_HEADINGS
        ):
            labels.append(content)
    return labels


def _matching_dynamic_term_identifiers(
    taxonomy: dict[str, JsonValue],
    *,
    source_label: str,
) -> set[str]:
    """Return dynamic term identifiers matching an exact label or source label."""

    matches: set[str] = set()
    for collection_name in DYNAMIC_TAXONOMY_COLLECTIONS:
        for value in as_sequence(
            taxonomy[collection_name],
            location=f"taxonomy.{collection_name}",
        ):
            term = as_mapping(value, location=f"taxonomy.{collection_name}[]")
            identifier = term.get("identifier")
            if isinstance(identifier, str) and source_label in {
                term.get("label"),
                term.get("sourceLabel"),
            }:
                matches.add(identifier)
    return matches


def _taxonomy_identifier_base(source_label: str) -> str:
    """Build a readable stable identifier base from one source heading."""

    normalized = unicodedata.normalize("NFKC", source_label).casefold().strip()
    version_match = re.fullmatch(
        r"(?P<version>[0-9]+(?:[._-]?[a-z0-9]+)*)\s*"
        r"(?P<qualifier>미만|이하|이상|초과)\s*버전",
        normalized,
    )
    if version_match is not None:
        version = re.sub(r"[^a-z0-9]+", "-", version_match.group("version")).strip("-")
        qualifier = VERSION_QUALIFIER_IDENTIFIERS[version_match.group("qualifier")]
        return f"version-{version}-{qualifier}"

    translated = normalized
    replacements = (
        ("계열의", " family "),
        ("계열", " family "),
        ("버전", " version "),
        ("이하", " or earlier "),
        ("이상", " or later "),
        ("미만", " below "),
        ("초과", " above "),
        ("또는", " or "),
    )
    for source, replacement in replacements:
        translated = translated.replace(source, replacement)
    tokens = re.findall(r"[a-z0-9]+", translated)
    if not tokens:
        digest = hashlib.sha256(source_label.encode()).hexdigest()[:12]
        return f"heading-{digest}"
    identifier = "-".join(tokens)
    if len(identifier) > MAXIMUM_TAXONOMY_IDENTIFIER_LENGTH:
        digest = hashlib.sha256(source_label.encode()).hexdigest()[
            :TAXONOMY_IDENTIFIER_DIGEST_LENGTH
        ]
        readable_length = MAXIMUM_TAXONOMY_IDENTIFIER_LENGTH - TAXONOMY_IDENTIFIER_DIGEST_LENGTH - 1
        identifier = f"{identifier[:readable_length].rstrip('-')}-{digest}"
    return identifier


def _all_taxonomy_identifiers(taxonomy: dict[str, JsonValue]) -> set[str]:
    """Return identifiers from every taxonomy array for collision checks."""

    identifiers: set[str] = set()
    for collection_name, collection_value in taxonomy.items():
        if collection_name == "schemaVersion" or not isinstance(collection_value, list):
            continue
        for value in collection_value:
            if isinstance(value, dict) and isinstance(value.get("identifier"), str):
                identifiers.add(cast("str", value["identifier"]))
    return identifiers


def _collision_safe_identifier(
    base_identifier: str,
    *,
    source_label: str,
    used_identifiers: set[str],
    base_is_ambiguous: bool,
) -> str:
    """Return a readable identifier with a label-derived suffix when required."""

    if not base_is_ambiguous and base_identifier not in used_identifiers:
        return base_identifier
    digest = hashlib.sha256(source_label.encode()).hexdigest()
    for digest_length in range(8, len(digest) + 1, 2):
        candidate = f"{base_identifier}-{digest[:digest_length]}"
        if candidate not in used_identifiers:
            return candidate
    msg = f"cannot allocate a collision-free taxonomy identifier for {source_label!r}"
    raise ValueError(msg)


def _compile_dynamic_taxonomy(
    inputs_values: list[CandidateInputs],
    *,
    taxonomy: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    """Compile all dynamic result headings into one deterministic taxonomy snapshot."""

    compiled = copy.deepcopy(taxonomy)
    new_labels: list[str] = []
    observed_labels: set[str] = set()
    for inputs in inputs_values:
        for source_label in _dynamic_heading_labels(inputs):
            if source_label in observed_labels:
                continue
            observed_labels.add(source_label)
            matches = _matching_dynamic_term_identifiers(compiled, source_label=source_label)
            if len(matches) > 1:
                msg = (
                    f"dynamic heading {source_label!r} ambiguously matches taxonomy identifiers: "
                    f"{sorted(matches)!r}"
                )
                raise ValueError(msg)
            if not matches:
                new_labels.append(source_label)

    base_counts: dict[str, int] = {}
    bases: dict[str, str] = {}
    for source_label in new_labels:
        base = _taxonomy_identifier_base(source_label)
        bases[source_label] = base
        base_counts[base] = base_counts.get(base, 0) + 1
    used_identifiers = _all_taxonomy_identifiers(compiled)
    product_families = as_sequence(
        compiled["productFamilies"],
        location="taxonomy.productFamilies",
    )
    for source_label in new_labels:
        base = bases[source_label]
        identifier = _collision_safe_identifier(
            base,
            source_label=source_label,
            used_identifiers=used_identifiers,
            base_is_ambiguous=base_counts[base] > 1,
        )
        product_families.append(
            {
                "identifier": identifier,
                "label": source_label,
                "sourceLabel": source_label,
            }
        )
        used_identifiers.add(identifier)
    return compiled


def _unique_record(
    records: list[JsonValue],
    *,
    location: str,
    field_name: str,
    expected_value: str,
) -> dict[str, JsonValue]:
    """Return exactly one registry record matching a scalar identity field."""

    matches = [
        as_mapping(value, location=f"{location}[]")
        for value in records
        if isinstance(value, dict) and value.get(field_name) == expected_value
    ]
    if len(matches) != 1:
        msg = (
            f"expected one {location} record with {field_name}={expected_value!r}, "
            f"got {len(matches)}"
        )
        raise ValueError(msg)
    return matches[0]


def _validate_candidate_inputs(
    slug: str,
    *,
    root: Path,
    work_directory: Path,
) -> CandidateInputs:
    """Validate that task, result, and candidate artifacts describe current source."""

    task_path = work_directory / "tasks" / slug / "task.json"
    result_path = work_directory / "results" / slug / "result.json"
    candidate_directory = work_directory / "candidates" / slug
    candidate_path = candidate_directory / "candidate.md"
    validation_path = candidate_directory / "validation.json"

    task = load_codex_task(task_path, root=root)
    verify_codex_task_dependencies(task, root=root)
    result = validate_codex_result(result_path, task_path, root=root)
    validation = load_json(validation_path)
    if task.get("criterionSlug") != slug or result.get("criterionSlug") != slug:
        msg = f"Codex artifacts do not belong to requested slug {slug}"
        raise ValueError(msg)

    expected_validation: dict[str, JsonValue] = {
        "schemaVersion": CANONICAL_VALIDATION_SCHEMA_VERSION,
        "taskIdentifier": task["taskIdentifier"],
        "taskChecksum": task["taskChecksum"],
        "resultChecksum": sha256_file(result_path),
        "candidateChecksum": sha256_file(candidate_path),
        "validationStatus": "passed",
        "canonicalApplied": False,
    }
    mismatched_fields = [
        field_name
        for field_name, expected_value in expected_validation.items()
        if validation.get(field_name) != expected_value
    ]
    mismatched_fields.extend(sorted(set(validation) - set(expected_validation)))
    if mismatched_fields:
        msg = "candidate validation is stale or ineligible: " + ", ".join(mismatched_fields)
        raise ValueError(msg)

    manifest = load_yaml(root / MANIFEST_PATH)
    manifest_record = _unique_record(
        as_sequence(manifest["criteria"], location="manifest.criteria"),
        location="manifest.criteria",
        field_name="slug",
        expected_value=slug,
    )
    if manifest_record.get("contentModel") != "extractedCriterion":
        msg = f"{slug} is not an extractedCriterion"
        raise ValueError(msg)
    domain_identifier = manifest_record.get("domainIdentifier")
    if not isinstance(domain_identifier, str):
        msg = f"{slug} manifest record has no domainIdentifier"
        raise TypeError(msg)
    current_checksum = criterion_source_checksum(slug, domain_identifier, root=root)
    if task.get("criterionSourceChecksum") != current_checksum:
        msg = f"Codex task source is stale for {slug}"
        raise ValueError(msg)
    if task.get("contentModel") != "extractedCriterion":
        msg = f"Codex task for {slug} was not built from extractedCriterion content"
        raise ValueError(msg)
    if task.get("domainIdentifier") != domain_identifier:
        msg = f"Codex task domain differs from the current manifest for {slug}"
        raise ValueError(msg)
    return CandidateInputs(
        task=task,
        result=result,
        validation=validation,
        manifest=manifest,
        manifest_record=manifest_record,
        task_path=task_path,
        result_path=result_path,
        candidate_path=candidate_path,
        validation_path=validation_path,
    )


def _fence(content: str) -> str:
    """Return a tilde fence that cannot collide with the literal content."""

    maximum_run = max((len(match.group()) for match in re.finditer(r"~+", content)), default=0)
    return "~" * max(3, maximum_run + 1)


def _table_cell(value: str) -> str:
    """Escape one GFM table cell without changing its source value."""

    return value.replace("|", "\\|").replace("\n", "<br>")


def _canonical_asset_path(asset_path: str, *, slug: str) -> str:
    """Normalize one result asset path to the criterion-relative canonical form."""

    normalized = asset_path.lstrip("/")
    if normalized.startswith("../assets/"):
        canonical_path = normalized
    elif normalized.startswith("assets/"):
        canonical_path = f"../{normalized}"
    else:
        msg = f"result asset path must be under assets/{slug}: {asset_path}"
        raise ValueError(msg)
    expected_prefix = f"../assets/{slug}/"
    if not canonical_path.startswith(expected_prefix) or "\\" in canonical_path:
        msg = f"result asset path must be under assets/{slug}: {asset_path}"
        raise ValueError(msg)
    relative_parts = Path(canonical_path.removeprefix(expected_prefix)).parts
    if not relative_parts or any(part in {"", ".", ".."} for part in relative_parts):
        msg = f"result asset path is not canonical: {asset_path}"
        raise ValueError(msg)
    return canonical_path


def _prepare_assets(  # noqa: C901, PLR0912, PLR0915
    nodes: list[dict[str, JsonValue]],
    existing_provenance: dict[str, JsonValue],
    *,
    root: Path,
    domain_identifier: str,
    slug: str,
) -> tuple[list[JsonValue], dict[str, dict[str, JsonValue]], tuple[Path, ...]]:
    """Retain declared meaningful assets and isolate intermediate source-page crops."""

    existing_assets = [
        copy.deepcopy(as_mapping(value, location="provenance.assets[]"))
        for value in as_sequence(existing_provenance["assets"], location="provenance.assets")
    ]
    retained_by_path: dict[str, dict[str, JsonValue]] = {}
    source_crop_paths: list[Path] = []
    criterion_directory = root / domain_identifier
    expected_asset_directory = (root / "assets" / slug).resolve()
    for asset in existing_assets:
        declared_path = asset.get("path")
        if not isinstance(declared_path, str):
            msg = f"{slug} provenance asset has no path"
            raise TypeError(msg)
        resolved_path = (criterion_directory / declared_path).resolve()
        if (
            not resolved_path.is_relative_to(expected_asset_directory)
            or not resolved_path.is_file()
        ):
            msg = (
                f"{slug} provenance asset is missing or outside its asset directory: "
                f"{declared_path}"
            )
            raise ValueError(msg)
        expected_checksum = asset.get("checksumValue")
        if (
            not isinstance(expected_checksum, str)
            or sha256_file(resolved_path) != expected_checksum
        ):
            msg = f"{slug} provenance asset checksum differs: {declared_path}"
            raise ValueError(msg)
        if asset.get("assetType") == "sourcePageCrop":
            source_crop_paths.append(resolved_path)
        else:
            if declared_path in retained_by_path:
                msg = f"{slug} contains duplicate retained asset path: {declared_path}"
                raise ValueError(msg)
            retained_by_path[declared_path] = asset

    result_assets: list[JsonValue] = []
    result_assets_by_node: dict[str, dict[str, JsonValue]] = {}
    observed_paths: set[str] = set()
    for node in nodes:
        if node.get("nodeType") != "image":
            continue
        node_identifier = cast("str", node["nodeIdentifier"])
        raw_path = cast("str", node["assetPath"])
        canonical_path = _canonical_asset_path(raw_path, slug=slug)
        if canonical_path in observed_paths:
            msg = f"Codex result uses an asset more than once: {canonical_path}"
            raise ValueError(msg)
        observed_paths.add(canonical_path)
        asset = retained_by_path.get(canonical_path)
        if asset is None:
            msg = f"Codex result references an unregistered meaningful asset: {canonical_path}"
            raise ValueError(msg)
        alternative_text = node.get("alternativeText")
        if not isinstance(alternative_text, str):
            msg = f"image node {node_identifier} has no alternative text"
            raise TypeError(msg)
        asset["alternativeText"] = alternative_text
        asset["alternativeTextStatus"] = "verificationRequired"
        node["assetPath"] = canonical_path
        result_assets.append(asset)
        result_assets_by_node[node_identifier] = asset
    if observed_paths != set(retained_by_path):
        missing_paths = sorted(set(retained_by_path) - observed_paths)
        msg = f"retained meaningful assets are absent from the Codex result: {missing_paths!r}"
        raise ValueError(msg)
    return result_assets, result_assets_by_node, tuple(source_crop_paths)


def _render_node_lines(  # noqa: PLR0911
    node: dict[str, JsonValue],
    *,
    active_list_depth: int,
) -> tuple[list[str], int]:
    """Render one result node using the canonical Markdown profile."""

    node_type = cast("str", node["nodeType"])
    content = cast("str", node["content"])
    if node_type == "heading":
        return ["#" * cast("int", node["headingLevel"]) + " " + content, ""], 0
    if node_type == "paragraph":
        return [content, ""], 0
    if node_type == "listItem":
        if "\n" in content:
            msg = f"list item {node['nodeIdentifier']} must be one Markdown line"
            raise ValueError(msg)
        list_depth = cast("int", node["listDepth"])
        indentation = "   " * (list_depth - 1)
        marker = "1." if node["listType"] == "ordered" else "-"
        return [f"{indentation}{marker} {content}", ""], list_depth
    if node_type == "codeBlock":
        fence = _fence(content)
        indentation = "   " * active_list_depth
        lines = [
            f"{fence}{node['codeLanguage']} {node['codeContentType']}",
            *content.splitlines(),
            fence,
        ]
        return [*(indentation + line for line in lines), ""], active_list_depth
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
        caption = node.get("tableCaption")
        caption_lines = [f"**{caption}**", ""] if isinstance(caption, str) else []
        return (
            [
                *caption_lines,
                "| " + " | ".join(headers) + " |",
                "| " + " | ".join("---" for _ in headers) + " |",
                *("| " + " | ".join(row) + " |" for row in rows),
                "",
            ],
            0,
        )
    if node_type == "note":
        return (
            [
                f"> **{node['noteType']}**",
                ">",
                *(f"> {line}" for line in content.splitlines()),
                "",
            ],
            0,
        )
    if node_type == "image":
        return [f"![{node['alternativeText']}]({node['assetPath']})", ""], 0
    msg = f"unsupported Codex node type: {node_type}"
    raise ValueError(msg)


def _canonical_source_spans(
    node: dict[str, JsonValue],
    *,
    page_evidence: dict[int, dict[str, JsonValue]],
) -> list[JsonValue]:
    """Reduce validated result spans to canonical provenance locations."""

    spans: list[JsonValue] = []
    observed: set[tuple[int, str]] = set()
    for span_value in as_sequence(node["sourceSpans"], location="node.sourceSpans"):
        span = as_mapping(span_value, location="node.sourceSpans[]")
        physical_page = span.get("physicalPage")
        region_identifier = span.get("pageRegionIdentifier")
        if not isinstance(physical_page, int) or not isinstance(region_identifier, str):
            msg = f"node {node['nodeIdentifier']} has an invalid source span"
            raise TypeError(msg)
        evidence = page_evidence.get(physical_page)
        if evidence is None or evidence.get("pageRegionIdentifier") != region_identifier:
            msg = f"node {node['nodeIdentifier']} has stale page-region provenance"
            raise ValueError(msg)
        key = (physical_page, region_identifier)
        if key in observed:
            continue
        observed.add(key)
        spans.append(
            {
                "physicalPage": physical_page,
                "printedPage": evidence["printedPage"],
                "pageRegionIdentifier": region_identifier,
            }
        )
    return spans


def _render_canonical(  # noqa: PLR0913
    inputs: CandidateInputs,
    existing_provenance: dict[str, JsonValue],
    *,
    root: Path,
    taxonomy: dict[str, JsonValue],
    domain_identifier: str,
    slug: str,
) -> CanonicalRender:
    """Render result nodes and map every parsed leaf back to result provenance."""

    nodes = [
        copy.deepcopy(as_mapping(value, location="result.nodes[]"))
        for value in as_sequence(inputs.result["nodes"], location="result.nodes")
    ]
    assets, _assets_by_node, source_crop_paths = _prepare_assets(
        nodes,
        existing_provenance,
        root=root,
        domain_identifier=domain_identifier,
        slug=slug,
    )
    page_evidence = {
        cast("int", evidence["physicalPage"]): evidence
        for evidence in (
            as_mapping(value, location="task.sourcePageEvidence[]")
            for value in as_sequence(
                inputs.task["sourcePageEvidence"],
                location="task.sourcePageEvidence",
            )
        )
    }
    identifier_mapping = heading_identifiers(taxonomy)
    body_lines: list[str] = []
    previous_blocks: list[LeafBlock] = []
    block_owners: list[dict[str, JsonValue]] = []
    node_block_references: dict[str, tuple[str, ...]] = {}
    active_list_depth = 0
    for node in nodes:
        rendered_lines, active_list_depth = _render_node_lines(
            node,
            active_list_depth=active_list_depth,
        )
        body_lines.extend(rendered_lines)
        body = "\n".join(body_lines).rstrip() + "\n"
        current_blocks = extract_leaf_blocks(
            body,
            criterion_slug=slug,
            heading_identifier_mapping=identifier_mapping,
        )
        if current_blocks[: len(previous_blocks)] != previous_blocks:
            msg = f"node {node['nodeIdentifier']} changed previously rendered Markdown blocks"
            raise ValueError(msg)
        new_blocks = current_blocks[len(previous_blocks) :]
        if not new_blocks:
            msg = f"node {node['nodeIdentifier']} did not render a canonical leaf block"
            raise ValueError(msg)
        node_identifier = cast("str", node["nodeIdentifier"])
        node_block_references[node_identifier] = tuple(
            block.block_reference for block in new_blocks
        )
        block_owners.extend(node for _block in new_blocks)
        previous_blocks = current_blocks

    body = "\n".join(body_lines).rstrip() + "\n"
    block_provenance: list[JsonValue] = []
    for block, owner in zip(previous_blocks, block_owners, strict=True):
        record: dict[str, JsonValue] = {
            "blockReference": block.block_reference,
            "blockType": block.block_type,
        }
        if block.heading_level is not None:
            record["headingLevel"] = block.heading_level
        record["semanticRole"] = block.semantic_role
        publication_disposition = cast("str", owner["publicationDisposition"])
        record["publicationDisposition"] = publication_disposition
        if publication_disposition == "derived":
            record["derivationType"] = "codexSemanticStructure"
        record["sourceSpans"] = _canonical_source_spans(owner, page_evidence=page_evidence)
        block_provenance.append(record)
    provenance: dict[str, JsonValue] = {
        "schemaVersion": 1,
        "criterionSlug": slug,
        "sourceDocumentIdentifier": inputs.result["sourceDocumentIdentifier"],
        "blockProvenance": block_provenance,
        "assets": assets,
    }
    return CanonicalRender(
        body=body,
        provenance=provenance,
        node_block_references=node_block_references,
        removed_source_crop_paths=source_crop_paths,
    )


def _preferred_target_reference(
    node_identifier: str,
    node_block_references: dict[str, tuple[str, ...]],
) -> str:
    """Choose the semantic content block when one result node expands to several leaves."""

    references = node_block_references.get(node_identifier)
    if not references:
        msg = f"annotation target does not map to canonical Markdown: {node_identifier}"
        raise ValueError(msg)
    return references[-1]


def _canonical_annotations(
    inputs: CandidateInputs,
    *,
    node_block_references: dict[str, tuple[str, ...]],
) -> list[JsonValue]:
    """Convert machine annotations without inventing human review or approval."""

    page_evidence = {
        cast("int", evidence["physicalPage"]): evidence
        for evidence in (
            as_mapping(value, location="task.sourcePageEvidence[]")
            for value in as_sequence(
                inputs.task["sourcePageEvidence"],
                location="task.sourcePageEvidence",
            )
        )
    }
    type_mapping = {
        "sourceInconsistency": "sourceInconsistency",
        "sourceTypo": "sourceTypographicalError",
        "sourceDuplication": "sourceDuplication",
        "conversionUncertainty": "conversionDecision",
    }
    annotations: list[JsonValue] = []
    for value in as_sequence(
        inputs.result["sourceAnnotations"],
        location="result.sourceAnnotations",
    ):
        annotation = as_mapping(value, location="result.sourceAnnotations[]")
        target_reference = cast("str", annotation["targetReference"])
        if target_reference.startswith("/"):
            target_type = "metadata"
            canonical_target = target_reference
        else:
            target_type = "astNode"
            canonical_target = _preferred_target_reference(
                target_reference,
                node_block_references,
            )
        physical_pages = cast(
            "list[int]",
            as_sequence(annotation["physicalPages"], location="annotation.physicalPages"),
        )
        physical_page = physical_pages[0]
        evidence = page_evidence[physical_page]
        disposition = annotation["disposition"]
        canonical_disposition = "preserved" if disposition == "preserved" else "unresolved"
        annotations.append(
            {
                "annotationIdentifier": annotation["annotationIdentifier"],
                "annotationType": type_mapping[cast("str", annotation["annotationType"])],
                "targetType": target_type,
                "targetReference": canonical_target,
                "sourceLocation": {
                    "physicalPage": physical_page,
                    "printedPage": evidence["printedPage"],
                    "pageRegionIdentifier": evidence["pageRegionIdentifier"],
                },
                "sourceText": annotation["sourceText"],
                "explanation": annotation["explanation"],
                "disposition": canonical_disposition,
                "reviewStatus": "pending",
                "verificationEvidence": [
                    (
                        f"Validated Codex task {inputs.task['taskIdentifier']} recorded this "
                        f"annotation for physical pages {', '.join(map(str, physical_pages))}."
                    )
                ],
                "reviewedBy": None,
                "reviewedAt": None,
                "approvedBy": None,
                "approvedAt": None,
            }
        )
    return annotations


def _canonical_metadata(
    existing_metadata: dict[str, JsonValue],
    inputs: CandidateInputs,
    annotations: list[JsonValue],
) -> dict[str, JsonValue]:
    """Adapt existing immutable metadata to the validated result recommendation."""

    criterion = copy.deepcopy(
        as_mapping(existing_metadata["criterion"], location="criterion.criterion")
    )
    criterion["title"] = inputs.result["title"]
    return {
        "schemaVersion": 1,
        "contentModel": inputs.result["contentModelRecommendation"],
        "contentModelVersion": CANONICAL_CONTENT_MODEL_VERSION,
        "criterion": criterion,
        "classification": copy.deepcopy(existing_metadata["classification"]),
        "targetScope": inputs.result["targetScope"],
        "targetIdentifiers": copy.deepcopy(inputs.result["targetIdentifiers"]),
        "sourceTargetText": inputs.result["sourceTargetText"],
        "provenance": copy.deepcopy(existing_metadata["provenance"]),
        "sourceAnnotations": annotations,
    }


def _intended_criterion_checksum(  # noqa: PLR0913
    *,
    root: Path,
    domain_identifier: str,
    slug: str,
    markdown_bytes: bytes,
    provenance_bytes: bytes,
    retained_asset_paths: list[Path],
) -> str:
    """Calculate the package checksum for staged bytes at their intended paths."""

    intended: dict[Path, bytes] = {
        Path(domain_identifier) / f"{slug}.md": markdown_bytes,
        Path(domain_identifier) / f"{slug}.provenance.yaml": provenance_bytes,
    }
    table_path = root / domain_identifier / f"{slug}.tables.yaml"
    if table_path.exists():
        intended[table_path.relative_to(root)] = table_path.read_bytes()
    for asset_path in retained_asset_paths:
        intended[asset_path.relative_to(root)] = asset_path.read_bytes()
    records = "".join(
        f"{hashlib.sha256(content).hexdigest()}  {path.as_posix()}\n"
        for path, content in sorted(intended.items(), key=lambda item: item[0].as_posix().encode())
    )
    return hashlib.sha256(records.encode()).hexdigest()


def _prepare_canonical_package(
    inputs: CandidateInputs,
    *,
    root: Path,
    taxonomy: dict[str, JsonValue],
) -> PreparedCanonicalPackage:
    """Render and checksum one package against the compiled taxonomy snapshot."""

    slug = cast("str", inputs.result["criterionSlug"])
    domain_identifier = inputs.manifest_record.get("domainIdentifier")
    if not isinstance(domain_identifier, str):
        msg = f"{slug} manifest record has no domainIdentifier"
        raise TypeError(msg)
    criterion_path = root / domain_identifier / f"{slug}.md"
    provenance_path = root / domain_identifier / f"{slug}.provenance.yaml"
    existing_criterion = load_criterion(criterion_path)
    existing_provenance = load_yaml(provenance_path)
    canonical_render = _render_canonical(
        inputs,
        existing_provenance,
        root=root,
        taxonomy=taxonomy,
        domain_identifier=domain_identifier,
        slug=slug,
    )
    annotations = _canonical_annotations(
        inputs,
        node_block_references=canonical_render.node_block_references,
    )
    metadata = _canonical_metadata(existing_criterion.metadata, inputs, annotations)
    markdown_source = (
        "---\n" + _yaml_text(metadata, top_level_spacing=True) + "---\n\n" + canonical_render.body
    )
    provenance_source = _yaml_text(canonical_render.provenance)
    retained_asset_paths = [
        (root / domain_identifier / cast("str", asset["path"])).resolve()
        for asset in (
            as_mapping(value, location="provenance.assets[]")
            for value in as_sequence(
                canonical_render.provenance["assets"],
                location="provenance.assets",
            )
        )
    ]
    criterion_checksum = _intended_criterion_checksum(
        root=root,
        domain_identifier=domain_identifier,
        slug=slug,
        markdown_bytes=markdown_source.encode(),
        provenance_bytes=provenance_source.encode(),
        retained_asset_paths=retained_asset_paths,
    )
    return PreparedCanonicalPackage(
        inputs=inputs,
        slug=slug,
        domain_identifier=domain_identifier,
        criterion_path=criterion_path,
        provenance_path=provenance_path,
        markdown_source=markdown_source,
        provenance_source=provenance_source,
        provenance=canonical_render.provenance,
        annotations=annotations,
        criterion_checksum=criterion_checksum,
        removed_source_crop_paths=canonical_render.removed_source_crop_paths,
    )


def _reset_review_record(
    record: dict[str, JsonValue],
    *,
    workflow_status: str,
    source_anomaly_count: int,
    force_source_review: bool,
    preserve_visual_evidence: bool,
) -> None:
    """Invalidate stale machine and human state without fabricating new review."""

    record["transcriptionStatus"] = "verificationRequired"
    record["workflowStatus"] = workflow_status
    record["sourceAnomalyStatus"] = (
        "reviewRequired" if source_anomaly_count or force_source_review else "none"
    )
    record["reviewers"] = []
    record["reviewedAt"] = None
    record["automatedValidationResult"] = "notRun"
    record["unresolvedConversionErrorCount"] = 0
    record["unresolvedSourceAnomalyCount"] = source_anomaly_count
    record["validationReportIdentifier"] = None
    if not preserve_visual_evidence:
        record["visualEvidenceIdentifiers"] = []
    record["testProfileVersion"] = None


def _updated_registries(
    packages: list[PreparedCanonicalPackage],
    *,
    root: Path,
) -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
    """Update all manifest and review records against one original registry snapshot."""

    if not packages:
        msg = "canonical apply requires at least one prepared package"
        raise ValueError(msg)
    manifest = copy.deepcopy(packages[0].inputs.manifest)
    review_registry = copy.deepcopy(load_yaml(root / REVIEW_REGISTRY_PATH))
    review_records = as_sequence(review_registry["records"], location="reviewRegistry.records")
    inventory = load_yaml(root / PAGE_REGION_INVENTORY_PATH)
    page_regions = [
        as_mapping(value, location="pageRegionInventory.pageRegions[]")
        for value in as_sequence(
            inventory["pageRegions"],
            location="pageRegionInventory.pageRegions",
        )
    ]
    for package in packages:
        manifest_record = _unique_record(
            as_sequence(manifest["criteria"], location="manifest.criteria"),
            location="manifest.criteria",
            field_name="slug",
            expected_value=package.slug,
        )
        manifest_record["contentModel"] = package.inputs.result["contentModelRecommendation"]
        manifest_record["contentModelVersion"] = CANONICAL_CONTENT_MODEL_VERSION
        manifest_record["technicalLiteralInventoryMode"] = "extractedFromTypedAst"

        criterion_reviews = [
            as_mapping(value, location="reviewRegistry.records[]")
            for value in review_records
            if isinstance(value, dict)
            and value.get("subjectType") == "criterion"
            and value.get("subjectIdentifier") == package.slug
        ]
        if len(criterion_reviews) != 1:
            msg = f"expected one criterion review record for {package.slug}"
            raise ValueError(msg)
        criterion_review = criterion_reviews[0]
        criterion_review["subjectSourceChecksum"] = package.criterion_checksum
        _reset_review_record(
            criterion_review,
            workflow_status="structured",
            source_anomaly_count=len(package.annotations),
            force_source_review=(
                package.inputs.result.get("analysisStatus") == "needsSourceReview"
            ),
            preserve_visual_evidence=False,
        )

        owned_regions = [
            region
            for region in page_regions
            if region.get("ownerType") == "criterion"
            and region.get("ownerIdentifier") == package.slug
            and region.get("publicationDisposition") in {"published", "derived"}
        ]
        if not owned_regions:
            msg = f"no published page regions are owned by {package.slug}"
            raise ValueError(msg)
        for region in owned_regions:
            region_identifier = cast("str", region["pageRegionIdentifier"])
            region_reviews = [
                as_mapping(value, location="reviewRegistry.records[]")
                for value in review_records
                if isinstance(value, dict)
                and value.get("subjectType") == "pageRegion"
                and value.get("subjectIdentifier") == region_identifier
            ]
            if len(region_reviews) != 1:
                msg = f"expected one page-region review record for {region_identifier}"
                raise ValueError(msg)
            region_review = region_reviews[0]
            region_review["subjectSourceChecksum"] = region_source_checksum(
                region,
                owner_source_checksum=package.criterion_checksum,
            )
            existing_anomaly_count = region_review.get("unresolvedSourceAnomalyCount")
            anomaly_count = existing_anomaly_count if isinstance(existing_anomaly_count, int) else 0
            _reset_review_record(
                region_review,
                workflow_status="extracted",
                source_anomaly_count=anomaly_count,
                force_source_review=False,
                preserve_visual_evidence=False,
            )
    return manifest, review_registry


def _validate_staged_shared_documents(
    *,
    root: Path,
    taxonomy: dict[str, JsonValue],
    manifest: dict[str, JsonValue],
    review_registry: dict[str, JsonValue],
) -> None:
    """Validate the shared taxonomy, manifest, and review registry once."""

    schema_checks = (
        (taxonomy, TAXONOMY_SCHEMA_PATH, "taxonomy"),
        (manifest, MANIFEST_SCHEMA_PATH, "criteria manifest"),
        (review_registry, REVIEW_SCHEMA_PATH, "review registry"),
    )
    for document, schema_path, label in schema_checks:
        errors = _schema_errors(document, load_json(root / schema_path))
        if errors:
            msg = f"invalid staged {label}: {'; '.join(errors)}"
            raise ValueError(msg)


def _validate_staged_package(
    package: PreparedCanonicalPackage,
    *,
    root: Path,
    taxonomy: dict[str, JsonValue],
    manifest: dict[str, JsonValue],
) -> None:
    """Validate one staged package and exact parsed-leaf provenance."""

    with tempfile.TemporaryDirectory(
        prefix=f"{package.slug}-canonical-stage-"
    ) as temporary_directory:
        staged_markdown = Path(temporary_directory) / f"{package.slug}.md"
        staged_markdown.write_text(package.markdown_source, encoding="utf-8")
        criterion = load_criterion(staged_markdown)
    schema_checks = (
        (criterion.metadata, CRITERION_METADATA_SCHEMA_PATH, "criterion metadata"),
        (package.provenance, PROVENANCE_SCHEMA_PATH, "criterion provenance"),
    )
    for document, schema_path, label in schema_checks:
        errors = _schema_errors(document, load_json(root / schema_path))
        if errors:
            msg = f"invalid staged {label}: {'; '.join(errors)}"
            raise ValueError(msg)

    blocks = extract_leaf_blocks(
        criterion.body,
        criterion_slug=package.slug,
        heading_identifier_mapping=heading_identifiers(taxonomy),
    )
    generated_references = [block.block_reference for block in blocks]
    declared_references = flatten_block_references(package.provenance)
    if len(generated_references) != len(set(generated_references)):
        msg = "staged canonical Markdown generates duplicate block references"
        raise ValueError(msg)
    if generated_references != declared_references:
        msg = "staged canonical Markdown and provenance block references differ"
        raise ValueError(msg)

    asset_paths = [
        cast("str", asset["path"])
        for asset in (
            as_mapping(value, location="provenance.assets[]")
            for value in as_sequence(
                package.provenance["assets"],
                location="provenance.assets",
            )
        )
    ]
    image_paths = [cast("str", block.asset_path) for block in blocks if block.asset_path]
    if image_paths != asset_paths:
        msg = "staged canonical Markdown and retained asset records differ"
        raise ValueError(msg)
    manifest_record = _unique_record(
        as_sequence(manifest["criteria"], location="manifest.criteria"),
        location="manifest.criteria",
        field_name="slug",
        expected_value=package.slug,
    )
    if (
        criterion.metadata.get("contentModel") != manifest_record.get("contentModel")
        or manifest_record.get("technicalLiteralInventoryMode") != "extractedFromTypedAst"
    ):
        msg = "staged criterion metadata and manifest content model differ"
        raise ValueError(msg)
    classification = as_mapping(criterion.metadata["classification"], location="classification")
    if classification.get("domainIdentifier") != package.domain_identifier:
        msg = "staged criterion domain differs from the manifest"
        raise ValueError(msg)


def _atomic_replace_bytes(path: Path, content: bytes) -> None:
    """Atomically replace one file with flushed bytes in its existing filesystem."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _copy_source_crop_evidence(
    source_crop_paths: tuple[Path, ...],
    *,
    root: Path,
    work_directory: Path,
    slug: str,
) -> tuple[Path, ...]:
    """Copy intermediate page crops into review evidence before canonical removal."""

    asset_root = (root / "assets" / slug).resolve()
    evidence_root = work_directory / "evidence" / slug
    copied: list[Path] = []
    for source_path in source_crop_paths:
        relative_path = source_path.relative_to(asset_root)
        destination = evidence_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if sha256_file(destination) != sha256_file(source_path):
                msg = f"existing review evidence differs from source crop: {destination}"
                raise ValueError(msg)
        else:
            shutil.copy2(source_path, destination)
        if sha256_file(destination) != sha256_file(source_path):
            msg = f"review evidence copy failed checksum verification: {destination}"
            raise ValueError(msg)
        copied.append(destination)
    return tuple(copied)


def _repository_error_message(issues: list[object], *, stage: str) -> str:
    """Summarize repository validation failures without hiding the affected rules."""

    descriptions: list[str] = []
    for issue in issues[:MAXIMUM_REPORTED_VALIDATION_ISSUES]:
        rule_identifier = getattr(issue, "rule_identifier", "unknown")
        location = getattr(issue, "location", "unknown")
        message = getattr(issue, "message", str(issue))
        descriptions.append(f"{rule_identifier} ({location}): {message}")
    suffix = (
        ""
        if len(issues) <= MAXIMUM_REPORTED_VALIDATION_ISSUES
        else f"; and {len(issues) - MAXIMUM_REPORTED_VALIDATION_ISSUES} more"
    )
    return f"repository validation {stage}: {'; '.join(descriptions)}{suffix}"


def _validate_applied_state(
    packages: list[PreparedCanonicalPackage],
    *,
    root: Path,
) -> None:
    """Reject replaced packages unless every checksum and repository validation pass."""

    for package in packages:
        applied_checksum = criterion_source_checksum(
            package.slug,
            package.domain_identifier,
            root=root,
        )
        if applied_checksum != package.criterion_checksum:
            msg = f"applied criterion checksum differs for {package.slug}"
            raise RuntimeError(msg)
    applied_issues = cast("list[object]", validate_repository(root=root, release=False))
    if applied_issues:
        raise ValueError(
            _repository_error_message(applied_issues, stage="failed after staged replacement")
        )


def _apply_validated_inputs(  # noqa: C901, PLR0912
    inputs_values: list[CandidateInputs],
    *,
    root: Path,
    work_directory: Path,
    taxonomy: dict[str, JsonValue],
) -> tuple[Path, ...]:
    """Stage and apply prevalidated inputs in one rollback-capable transaction."""

    baseline_issues = cast("list[object]", validate_repository(root=root, release=False))
    if baseline_issues:
        raise ValueError(_repository_error_message(baseline_issues, stage="failed before apply"))
    packages = [
        _prepare_canonical_package(inputs, root=root, taxonomy=taxonomy) for inputs in inputs_values
    ]
    manifest, review_registry = _updated_registries(packages, root=root)
    _validate_staged_shared_documents(
        root=root,
        taxonomy=taxonomy,
        manifest=manifest,
        review_registry=review_registry,
    )
    for package in packages:
        _validate_staged_package(
            package,
            root=root,
            taxonomy=taxonomy,
            manifest=manifest,
        )

    replacements: dict[Path, bytes] = {}
    for package in packages:
        replacements[package.criterion_path] = package.markdown_source.encode()
        replacements[package.provenance_path] = package.provenance_source.encode()
    replacements[root / MANIFEST_PATH] = _yaml_text(manifest).encode()
    replacements[root / REVIEW_REGISTRY_PATH] = _yaml_text(review_registry).encode()
    replacements[root / TAXONOMY_PATH] = _yaml_text(taxonomy).encode()
    for package in packages:
        updated_validation = copy.deepcopy(package.inputs.validation)
        updated_validation["canonicalApplied"] = True
        replacements[package.inputs.validation_path] = _json_text(updated_validation).encode()

    originals = {path: path.read_bytes() for path in replacements}
    deleted_asset_bytes: dict[Path, bytes] = {}
    for package in packages:
        for asset_path in package.removed_source_crop_paths:
            if asset_path in deleted_asset_bytes:
                msg = f"source crop belongs to more than one applied package: {asset_path}"
                raise ValueError(msg)
            deleted_asset_bytes[asset_path] = asset_path.read_bytes()
        _copy_source_crop_evidence(
            package.removed_source_crop_paths,
            root=root,
            work_directory=work_directory,
            slug=package.slug,
        )
    for path, original in originals.items():
        if path.read_bytes() != original:
            msg = f"file changed while staging canonical apply: {path}"
            raise RuntimeError(msg)
    for asset_path, original in deleted_asset_bytes.items():
        if asset_path.read_bytes() != original:
            msg = f"source crop changed while staging canonical apply: {asset_path}"
            raise RuntimeError(msg)

    try:
        for path, content in replacements.items():
            _atomic_replace_bytes(path, content)
        for asset_path in deleted_asset_bytes:
            asset_path.unlink()
        _validate_applied_state(packages, root=root)
    except BaseException:
        for path, content in originals.items():
            _atomic_replace_bytes(path, content)
        for asset_path, content in deleted_asset_bytes.items():
            _atomic_replace_bytes(asset_path, content)
        raise
    return tuple(package.criterion_path for package in packages)


def _validate_inputs_against_original_taxonomy(
    slugs: list[str],
    *,
    root: Path,
    work_directory: Path,
    expected_manifest_bytes: bytes,
    expected_taxonomy_bytes: bytes,
) -> list[CandidateInputs]:
    """Prevalidate all inputs before any taxonomy or canonical mutation."""

    inputs_values = [
        _validate_candidate_inputs(slug, root=root, work_directory=work_directory) for slug in slugs
    ]
    if (root / MANIFEST_PATH).read_bytes() != expected_manifest_bytes:
        msg = "criteria manifest changed during candidate prevalidation"
        raise RuntimeError(msg)
    if (root / TAXONOMY_PATH).read_bytes() != expected_taxonomy_bytes:
        msg = "taxonomy changed during candidate prevalidation"
        raise RuntimeError(msg)
    return inputs_values


def apply_codex_candidate(
    slug: str,
    *,
    root: Path | None = None,
    work_directory: Path | None = None,
) -> Path:
    """Apply one current validated candidate with rollback on validation failure."""

    repository = (root or repository_root()).resolve()
    output_root = (work_directory or repository / DEFAULT_WORK_DIRECTORY).resolve()
    manifest_bytes = (repository / MANIFEST_PATH).read_bytes()
    taxonomy_bytes = (repository / TAXONOMY_PATH).read_bytes()
    original_taxonomy = load_yaml(repository / TAXONOMY_PATH)
    inputs_values = _validate_inputs_against_original_taxonomy(
        [slug],
        root=repository,
        work_directory=output_root,
        expected_manifest_bytes=manifest_bytes,
        expected_taxonomy_bytes=taxonomy_bytes,
    )
    taxonomy = _compile_dynamic_taxonomy(inputs_values, taxonomy=original_taxonomy)
    return _apply_validated_inputs(
        inputs_values,
        root=repository,
        work_directory=output_root,
        taxonomy=taxonomy,
    )[0]


def apply_all_codex_candidates(
    *,
    root: Path | None = None,
    work_directory: Path | None = None,
) -> tuple[Path, ...]:
    """Apply every extracted manifest candidate as one atomic corpus transaction."""

    repository = (root or repository_root()).resolve()
    output_root = (work_directory or repository / DEFAULT_WORK_DIRECTORY).resolve()
    manifest_path = repository / MANIFEST_PATH
    taxonomy_path = repository / TAXONOMY_PATH
    manifest_bytes = manifest_path.read_bytes()
    taxonomy_bytes = taxonomy_path.read_bytes()
    manifest = load_yaml(manifest_path)
    original_taxonomy = load_yaml(taxonomy_path)
    slugs: list[str] = []
    for value in as_sequence(manifest["criteria"], location="manifest.criteria"):
        record = as_mapping(value, location="manifest.criteria[]")
        if record.get("contentModel") != "extractedCriterion":
            continue
        slug = record.get("slug")
        if not isinstance(slug, str):
            msg = "extracted manifest record has no slug"
            raise TypeError(msg)
        slugs.append(slug)
    if not slugs:
        msg = "manifest contains no extractedCriterion candidates to apply"
        raise ValueError(msg)
    inputs_values = _validate_inputs_against_original_taxonomy(
        slugs,
        root=repository,
        work_directory=output_root,
        expected_manifest_bytes=manifest_bytes,
        expected_taxonomy_bytes=taxonomy_bytes,
    )
    taxonomy = _compile_dynamic_taxonomy(inputs_values, taxonomy=original_taxonomy)
    return _apply_validated_inputs(
        inputs_values,
        root=repository,
        work_directory=output_root,
        taxonomy=taxonomy,
    )


def _argument_parser() -> argparse.ArgumentParser:
    """Build the canonical candidate-applier command-line parser."""

    parser = argparse.ArgumentParser(description=__doc__)
    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument("slug", nargs="?", help="criterion slug such as u-03")
    target_group.add_argument(
        "--all",
        action="store_true",
        dest="apply_all",
        help="apply every extracted criterion in manifest order",
    )
    parser.add_argument("--work-directory", type=Path, help="generated Codex work directory")
    add_logging_arguments(parser)
    return parser


def main() -> int:
    """Apply one candidate and report the canonical criterion path."""

    arguments = _argument_parser().parse_args()
    with configure_runtime_logging(
        "codex_candidate_applier",
        level=arguments.log_level,
        log_directory=arguments.log_directory,
        context={"slug": arguments.slug if arguments.slug is not None else "all"},
    ) as logger:
        logger.info(
            "Codex candidate apply started",
            event="command.started",
            work_directory=(
                str(arguments.work_directory) if arguments.work_directory is not None else None
            ),
        )
        try:
            if arguments.apply_all:
                criterion_paths = apply_all_codex_candidates(
                    work_directory=arguments.work_directory,
                )
            else:
                criterion_paths = (
                    apply_codex_candidate(
                        cast("str", arguments.slug),
                        work_directory=arguments.work_directory,
                    ),
                )
        except (FileNotFoundError, OSError, RuntimeError, TypeError, ValueError) as error:
            logger.exception(
                "Codex candidate apply failed",
                event="command.failed",
                error=error,
            )
            print(str(error), file=sys.stderr)  # noqa: T201
            return 1
        logger.info(
            "Codex candidate apply completed",
            event="command.completed",
            output_paths=[str(path) for path in criterion_paths],
        )
        for criterion_path in criterion_paths:
            print(criterion_path)  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
