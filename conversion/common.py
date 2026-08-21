"""Shared parsing, validation, and checksum helpers."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import rfc8785
from markdown_it import MarkdownIt
from markdown_it.token import Token
from ruamel.yaml import YAML

type JsonScalar = bool | int | float | str | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]

ALLOWED_CODE_CONTENT_TYPES = frozenset(
    {"command", "configuration", "output", "literal", "transcription"}
)
# The canonical format contract applies to every content model that represents a completed
# conversion. The Codex result importer and the repository validator must both read these
# constants so that a contract change cannot be applied to only one enforcement layer.
CANONICAL_FORMAT_CONTENT_MODELS = frozenset({"systemCriterion", "webApplicationCriterion"})
REQUIRED_LEVEL_TWO_HEADINGS = (
    "개요",
    "점검 대상 및 판단 기준",
    "점검 및 조치 사례",
)
REQUIRED_OVERVIEW_LEVEL_THREE_HEADINGS = (
    "점검 내용",
    "점검 목적",
    "보안 위협",
    "참고",
)
REQUIRED_ASSESSMENT_LEVEL_THREE_HEADINGS = (
    "대상",
    "판단 기준",
    "조치 방법",
    "조치 시 영향",
)
EXTRACTED_LEVEL_TWO_HEADINGS = ("원문 전사",)
# Supplementary guidance is platform independent, so it must trail the per-target sections
# instead of interrupting them.
SUPPLEMENTARY_GUIDANCE_HEADING = "추가 지침"
ALLOWED_NOTE_LABELS = frozenset({"참고", "주의", "경고", "편집자 주"})
CHECKSUM_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class CriterionDocument:
    """A criterion metadata document and its Markdown body."""

    path: Path
    metadata: dict[str, JsonValue]
    body: str


@dataclass(frozen=True)
class LeafBlock:
    """A machine-readable Markdown leaf block."""

    block_reference: str
    block_type: str
    content: str
    semantic_role: str
    semantic_path: tuple[str, ...]
    parent_block_reference: str | None = None
    heading_level: int | None = None
    list_type: str | None = None
    list_depth: int | None = None
    code_language: str | None = None
    code_content_type: str | None = None
    technical_literals: tuple[str, ...] = ()
    table_headers: tuple[str, ...] | None = None
    table_rows: tuple[tuple[str, ...], ...] | None = None
    asset_path: str | None = None
    alternative_text: str | None = None
    alternative_text_status: str | None = None


@dataclass
class _ListState:
    """Track one Markdown list while deriving semantic references."""

    list_type: str
    item_count: int = 0


@dataclass
class _ListItemState:
    """Track one list item and its continuation paragraphs."""

    list_type: str
    item_number: int
    inline_count: int = 0
    canonical_item_number: int | None = None
    block_reference: str | None = None


@dataclass
class _NoteState:
    """Track a blockquote note and its typed child blocks."""

    note_number: int
    label_seen: bool = False


def repository_root() -> Path:
    """Return the repository root containing the conversion package."""

    return Path(__file__).resolve().parent.parent


def _normalize_loaded_value(value: object, *, location: str) -> JsonValue:
    """Reject YAML values that cannot be represented by the canonical JSON model."""

    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, list):
        return [
            _normalize_loaded_value(item, location=f"{location}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, Mapping):
        normalized_mapping: dict[str, JsonValue] = {}
        for key, nested_value in value.items():
            if not isinstance(key, str):
                msg = f"{location}: YAML mapping key must be a string"
                raise ValueError(msg)
            normalized_mapping[key] = _normalize_loaded_value(
                nested_value,
                location=f"{location}.{key}",
            )
        return normalized_mapping
    msg = f"{location}: unsupported YAML value type {type(value).__name__}"
    raise ValueError(msg)


def _load_yaml_source(source: str, *, location: str) -> dict[str, JsonValue]:
    """Load one canonical YAML source with the repository profile."""

    if "\t" in source:
        msg = f"{location}: tab characters are not allowed in canonical YAML"
        raise ValueError(msg)
    if re.search(r"(^|[\s\[{,])&[A-Za-z0-9_-]+", source, flags=re.MULTILINE):
        msg = f"{location}: YAML anchors are not allowed"
        raise ValueError(msg)
    if re.search(r"(^|[\s\[{,])\*[A-Za-z0-9_-]+", source, flags=re.MULTILINE):
        msg = f"{location}: YAML aliases are not allowed"
        raise ValueError(msg)
    if re.search(r"^\s*<<\s*:", source, flags=re.MULTILINE):
        msg = f"{location}: YAML merge keys are not allowed"
        raise ValueError(msg)

    parser = YAML(typ="safe", pure=True)
    parser.version = (1, 2)
    parser.allow_duplicate_keys = False
    loaded = parser.load(source)
    normalized = _normalize_loaded_value(loaded, location=location)
    if not isinstance(normalized, dict):
        msg = f"{location}: top-level YAML value must be a mapping"
        raise ValueError(msg)
    return normalized


def load_yaml(path: Path) -> dict[str, JsonValue]:
    """Load a YAML 1.2 document while rejecting duplicate keys and aliases."""

    return _load_yaml_source(path.read_text(encoding="utf-8"), location=str(path))


def load_json(path: Path) -> dict[str, JsonValue]:
    """Load a JSON object without permitting a non-object root."""

    loaded = json.loads(path.read_text(encoding="utf-8"))
    normalized = _normalize_loaded_value(loaded, location=str(path))
    if not isinstance(normalized, dict):
        msg = f"{path}: top-level JSON value must be an object"
        raise ValueError(msg)
    return normalized


def load_criterion(path: Path) -> CriterionDocument:
    """Load YAML front matter and Markdown body from a criterion file."""

    source = path.read_text(encoding="utf-8")
    if not source.startswith("---\n"):
        msg = f"{path}: criterion must start with YAML front matter"
        raise ValueError(msg)
    separator_index = source.find("\n---\n", 4)
    if separator_index < 0:
        msg = f"{path}: criterion front matter is not terminated"
        raise ValueError(msg)

    front_matter = source[4:separator_index]
    normalized = _load_yaml_source(front_matter, location=f"{path}:frontMatter")
    body = source[separator_index + 5 :]
    return CriterionDocument(path=path, metadata=normalized, body=body)


def markdown_parser() -> MarkdownIt:
    """Create the constrained CommonMark parser with GFM table support."""

    return MarkdownIt("commonmark").enable("table")


def _table_content(token: Token, body_lines: Sequence[str]) -> str:
    """Recover the source Markdown for a table token."""

    if token.map is None:
        return ""
    start_line, end_line = token.map
    return "\n".join(body_lines[start_line:end_line])


def _inline_plain_text(token: Token) -> str:
    """Return inline text without Markdown emphasis or code delimiters."""

    if token.children is None:
        return token.content
    return "".join(
        child.content
        for child in token.children
        if child.type in {"text", "code_inline", "softbreak", "hardbreak"}
    )


def _inline_technical_literals(token: Token) -> tuple[str, ...]:
    """Return exact inline-code values from one Markdown inline token."""

    if token.children is None:
        return ()
    return tuple(
        child.content for child in token.children if child.type == "code_inline" and child.content
    )


def _inline_image(token: Token) -> tuple[str, str] | None:
    """Return source path and alternative text for an image-only paragraph."""

    if token.children is None or len(token.children) != 1:
        return None
    child = token.children[0]
    if child.type != "image":
        return None
    source_path = child.attrGet("src")
    if not isinstance(source_path, str):
        return None
    return source_path, child.content


def _table_technical_literals(tokens: Sequence[Token], start_index: int) -> tuple[str, ...]:
    """Return exact inline-code values contained in one GFM table."""

    literals: list[str] = []
    depth = 0
    for token in tokens[start_index:]:
        if token.type == "table_open":
            depth += 1
        elif token.type == "table_close":
            depth -= 1
            if depth == 0:
                break
        elif depth > 0 and token.type == "inline":
            literals.extend(_inline_technical_literals(token))
    return tuple(literals)


def _table_structure(
    tokens: Sequence[Token],
    start_index: int,
) -> tuple[tuple[str, ...], tuple[tuple[str, ...], ...]]:
    """Extract GFM table headers and rows without reparsing Markdown later."""

    headers: tuple[str, ...] = ()
    rows: list[tuple[str, ...]] = []
    current_cells: list[str] = []
    in_header = False
    depth = 0
    for token in tokens[start_index:]:
        if token.type == "table_open":
            depth += 1
        elif token.type == "table_close":
            depth -= 1
            if depth == 0:
                break
        elif token.type == "thead_open":
            in_header = True
        elif token.type == "thead_close":
            in_header = False
        elif token.type == "tr_open":
            current_cells = []
        elif token.type == "inline" and depth > 0:
            current_cells.append(token.content)
        elif token.type == "tr_close":
            completed_row = tuple(current_cells)
            if in_header:
                headers = completed_row
            else:
                rows.append(completed_row)
    return headers, tuple(rows)


def _code_technical_literals(content: str) -> tuple[str, ...]:
    """Extract complete configuration lines, setting keys, and paths."""

    literals: list[str] = []
    for source_line in content.splitlines():
        line = source_line.strip()
        if not line:
            continue
        literals.append(line)
        setting_match = re.match(r"^[A-Za-z_][A-Za-z0-9_]*", line)
        if setting_match is not None:
            literals.append(setting_match.group())
        literals.extend(
            match.group()
            for match in re.finditer(
                r"(?<![A-Za-z0-9_])/(?:[A-Za-z0-9_.+-]+/)*[A-Za-z0-9_.+-]+",
                line,
            )
        )
    return tuple(dict.fromkeys(literals))


def heading_identifiers(taxonomy: Mapping[str, JsonValue]) -> dict[str, str]:
    """Build source-heading to stable-identifier mappings."""

    identifiers = {
        "개요": "overview",
        "점검 내용": "inspectionContent",
        "점검 목적": "inspectionPurpose",
        "보안 위협": "securityThreat",
        "참고": "reference",
        "점검 대상 및 판단 기준": "assessment",
        "대상": "target",
        "판단 기준": "judgment",
        "조치 방법": "remediationMethod",
        "조치 시 영향": "remediationImpact",
        "점검 및 조치 사례": "remediation",
        "추가 지침": "supplementaryGuidance",
        "부적절한 비밀번호 유형": "inappropriatePasswordTypes",
        "비밀번호 관리 방법": "passwordManagementMethods",
        "원문 전사": "sourceTranscription",
    }
    for collection_name in ("targets", "protocols", "productFamilies"):
        collection = taxonomy.get(collection_name)
        if not isinstance(collection, list):
            continue
        for item in collection:
            if not isinstance(item, dict):
                continue
            identifier = item.get("identifier")
            if not isinstance(identifier, str):
                continue
            for label_name in ("label", "sourceLabel"):
                label = item.get(label_name)
                if isinstance(label, str):
                    identifiers[label] = identifier
    return identifiers


def _semantic_path(heading_roles: Mapping[int, str]) -> str:
    """Join active heading roles from H2 through the current depth."""

    return ".".join(heading_roles[level] for level in sorted(heading_roles))


def extract_leaf_blocks(
    body: str,
    *,
    criterion_slug: str,
    heading_identifier_mapping: Mapping[str, str],
) -> list[LeafBlock]:
    """Extract typed leaf blocks and generate stable semantic references."""

    tokens = markdown_parser().parse(body)
    body_lines = body.splitlines()
    leaf_blocks: list[LeafBlock] = []
    heading_roles: dict[int, str] = {}
    ordinal_counts: dict[tuple[str, str], int] = {}
    note_counts: dict[str, int] = {}
    note_item_counts: dict[str, int] = {}
    ordered_step_counts: dict[str, int] = {}
    list_stack: list[_ListState] = []
    list_item_stack: list[_ListItemState] = []
    note_stack: list[_NoteState] = []
    table_depth = 0
    token_index = 0

    def append_leaf(
        *,
        semantic_role: str,
        content: str,
        block_type: str,
        forced_ordinal: int | None = None,
        heading_level: int | None = None,
        list_type: str | None = None,
        list_depth: int | None = None,
        code_language: str | None = None,
        code_content_type: str | None = None,
        technical_literals: tuple[str, ...] = (),
        table_headers: tuple[str, ...] | None = None,
        table_rows: tuple[tuple[str, ...], ...] | None = None,
        parent_block_reference: str | None = None,
        asset_path: str | None = None,
        alternative_text: str | None = None,
        alternative_text_status: str | None = None,
    ) -> str:
        path = _semantic_path(heading_roles)
        key = (path, semantic_role)
        ordinal = forced_ordinal
        if ordinal is None:
            ordinal_counts[key] = ordinal_counts.get(key, 0) + 1
            ordinal = ordinal_counts[key]
        reference = f"{criterion_slug}:{path}.{semantic_role}:{ordinal}"
        leaf_blocks.append(
            LeafBlock(
                block_reference=reference,
                block_type=block_type,
                content=content,
                semantic_role=semantic_role,
                semantic_path=tuple(path.split(".")),
                parent_block_reference=parent_block_reference,
                heading_level=heading_level,
                list_type=list_type,
                list_depth=list_depth,
                code_language=code_language,
                code_content_type=code_content_type,
                technical_literals=tuple(dict.fromkeys(technical_literals)),
                table_headers=table_headers,
                table_rows=table_rows,
                asset_path=asset_path,
                alternative_text=alternative_text,
                alternative_text_status=alternative_text_status,
            )
        )
        return reference

    while token_index < len(tokens):
        token = tokens[token_index]
        if token.type == "heading_open":
            heading_level = int(token.tag[1:])
            inline_token = tokens[token_index + 1]
            heading_label = inline_token.content
            heading_role = heading_identifier_mapping.get(heading_label)
            if heading_role is None:
                source_page_match = re.fullmatch(r"PDF 페이지 ([0-9]+)", heading_label)
                if source_page_match is not None:
                    heading_role = f"sourcePage{source_page_match.group(1)}"
            if heading_role is None:
                msg = f"unsupported heading for content model: {heading_label}"
                raise ValueError(msg)
            for level in tuple(heading_roles):
                if level >= heading_level:
                    del heading_roles[level]
            heading_roles[heading_level] = heading_role
            append_leaf(
                semantic_role="heading",
                content=heading_label,
                block_type="heading",
                heading_level=heading_level,
            )
            token_index += 3
            continue
        if token.type == "table_open":
            table_depth += 1
            table_headers, table_rows = _table_structure(tokens, token_index)
            append_leaf(
                semantic_role="table",
                content=_table_content(token, body_lines),
                block_type="table",
                technical_literals=_table_technical_literals(tokens, token_index),
                table_headers=table_headers,
                table_rows=table_rows,
            )
            token_index += 1
            continue
        if token.type == "table_close":
            table_depth -= 1
            token_index += 1
            continue
        if table_depth > 0:
            token_index += 1
            continue
        if token.type == "ordered_list_open":
            list_stack.append(_ListState(list_type="ordered"))
            token_index += 1
            continue
        if token.type == "bullet_list_open":
            list_stack.append(_ListState(list_type="unordered"))
            token_index += 1
            continue
        if token.type in {"ordered_list_close", "bullet_list_close"}:
            list_stack.pop()
            token_index += 1
            continue
        if token.type == "list_item_open":
            list_stack[-1].item_count += 1
            list_item_stack.append(
                _ListItemState(
                    list_type=list_stack[-1].list_type,
                    item_number=list_stack[-1].item_count,
                )
            )
            token_index += 1
            continue
        if token.type == "list_item_close":
            list_item_stack.pop()
            token_index += 1
            continue
        if token.type == "blockquote_open":
            path = _semantic_path(heading_roles)
            note_counts[path] = note_counts.get(path, 0) + 1
            note_stack.append(_NoteState(note_number=note_counts[path]))
            token_index += 1
            continue
        if token.type == "blockquote_close":
            note_stack.pop()
            token_index += 1
            continue
        if token.type == "fence":
            information_parts = token.info.split()
            language = information_parts[0] if information_parts else ""
            content_type = information_parts[1] if len(information_parts) > 1 else ""
            append_leaf(
                semantic_role=content_type or "code",
                content=token.content,
                block_type="codeBlock",
                code_language=language,
                code_content_type=content_type,
                technical_literals=(
                    ()
                    if content_type == "transcription"
                    else _code_technical_literals(token.content)
                ),
                parent_block_reference=(
                    list_item_stack[-1].block_reference if list_item_stack else None
                ),
            )
            token_index += 1
            continue
        if token.type != "inline":
            token_index += 1
            continue

        path = _semantic_path(heading_roles)
        plain_content = _inline_plain_text(token)
        inline_image = _inline_image(token)
        if inline_image is not None and not note_stack and not list_item_stack:
            source_path, alternative_text = inline_image
            append_leaf(
                semantic_role="image",
                content=token.content,
                block_type="image",
                asset_path=source_path,
                alternative_text=alternative_text,
                alternative_text_status="verificationRequired",
            )
            token_index += 1
            continue
        if note_stack:
            note_state = note_stack[-1]
            if not note_state.label_seen and plain_content in ALLOWED_NOTE_LABELS:
                note_state.label_seen = True
                append_leaf(
                    semantic_role="note.label",
                    content=token.content,
                    block_type="noteLabel",
                    forced_ordinal=note_state.note_number,
                    technical_literals=_inline_technical_literals(token),
                )
            elif list_item_stack:
                note_item_counts[path] = note_item_counts.get(path, 0) + 1
                append_leaf(
                    semantic_role="note.item",
                    content=token.content,
                    block_type="listItem",
                    forced_ordinal=note_item_counts[path],
                    list_type="unordered",
                    list_depth=len(list_stack),
                    technical_literals=_inline_technical_literals(token),
                )
            else:
                append_leaf(
                    semantic_role="note.content",
                    content=token.content,
                    block_type="noteContent",
                    technical_literals=_inline_technical_literals(token),
                )
            token_index += 1
            continue

        if list_item_stack:
            item_state = list_item_stack[-1]
            item_state.inline_count += 1
            if item_state.list_type == "ordered":
                semantic_role = "step" if item_state.inline_count == 1 else "step.explanation"
                # Ordered procedures can restart after a table or note in the same semantic
                # section. The canonical reference ordinal follows document order so those
                # separate Markdown lists cannot generate duplicate block references.
                if item_state.canonical_item_number is None:
                    ordered_step_counts[path] = ordered_step_counts.get(path, 0) + 1
                    item_state.canonical_item_number = ordered_step_counts[path]
                forced_ordinal = item_state.canonical_item_number
            elif path.endswith("judgment") and plain_content.startswith("양호"):
                semantic_role = "good"
                forced_ordinal = 1
            elif path.endswith("judgment") and plain_content.startswith("취약"):
                semantic_role = "vulnerable"
                forced_ordinal = 1
            elif path.endswith("passwordManagementMethods") and len(list_stack) > 1:
                semantic_role = "characterClass"
                forced_ordinal = item_state.item_number
            else:
                semantic_role = "item"
                forced_ordinal = item_state.item_number
            parent_block_reference = (
                list_item_stack[-2].block_reference if len(list_item_stack) > 1 else None
            )
            if item_state.inline_count > 1 and item_state.block_reference is not None:
                parent_block_reference = item_state.block_reference
            block_reference = append_leaf(
                semantic_role=semantic_role,
                content=token.content,
                block_type="listItem",
                forced_ordinal=forced_ordinal,
                list_type=item_state.list_type,
                list_depth=len(list_stack),
                technical_literals=_inline_technical_literals(token),
                parent_block_reference=parent_block_reference,
            )
            if item_state.inline_count == 1:
                item_state.block_reference = block_reference
            token_index += 1
            continue

        append_leaf(
            semantic_role="paragraph",
            content=token.content,
            block_type="paragraph",
            technical_literals=_inline_technical_literals(token),
        )
        token_index += 1

    return leaf_blocks


def flatten_block_references(provenance: Mapping[str, JsonValue]) -> list[str]:
    """Expand singular and grouped provenance references in document order."""

    records = provenance.get("blockProvenance")
    if not isinstance(records, list):
        msg = "provenance blockProvenance must be an array"
        raise ValueError(msg)

    references: list[str] = []
    for record_index, record in enumerate(records):
        if not isinstance(record, dict):
            msg = f"blockProvenance[{record_index}] must be an object"
            raise ValueError(msg)
        singular_reference = record.get("blockReference")
        grouped_references = record.get("blockReferences")
        if isinstance(singular_reference, str):
            references.append(singular_reference)
        elif isinstance(grouped_references, list) and all(
            isinstance(reference, str) for reference in grouped_references
        ):
            references.extend(cast("list[str]", grouped_references))
        else:
            msg = f"blockProvenance[{record_index}] has no valid block reference"
            raise ValueError(msg)
    return references


def provenance_by_reference(
    provenance: Mapping[str, JsonValue],
) -> dict[str, list[dict[str, JsonValue]]]:
    """Index source spans by every singular or grouped block reference."""

    records = provenance.get("blockProvenance")
    if not isinstance(records, list):
        msg = "provenance blockProvenance must be an array"
        raise ValueError(msg)

    indexed: dict[str, list[dict[str, JsonValue]]] = {}
    for record in records:
        if not isinstance(record, dict):
            msg = "provenance block record must be an object"
            raise ValueError(msg)
        spans = record.get("sourceSpans")
        if not isinstance(spans, list) or not all(isinstance(span, dict) for span in spans):
            msg = "provenance sourceSpans must contain objects"
            raise ValueError(msg)
        normalized_spans = cast("list[dict[str, JsonValue]]", spans)
        singular_reference = record.get("blockReference")
        grouped_references = record.get("blockReferences")
        if isinstance(singular_reference, str):
            candidate_references = [singular_reference]
        elif isinstance(grouped_references, list):
            candidate_references = cast("list[str]", grouped_references)
        else:
            msg = "provenance block record has no reference"
            raise ValueError(msg)
        for reference in candidate_references:
            if reference in indexed:
                msg = f"duplicate provenance block reference: {reference}"
                raise ValueError(msg)
            indexed[reference] = normalized_spans
    return indexed


def provenance_attributes_by_reference(
    provenance: Mapping[str, JsonValue],
) -> dict[str, dict[str, JsonValue]]:
    """Index block-level publication and derivation attributes."""

    records = provenance.get("blockProvenance")
    if not isinstance(records, list):
        msg = "provenance blockProvenance must be an array"
        raise TypeError(msg)
    indexed: dict[str, dict[str, JsonValue]] = {}
    for record in records:
        if not isinstance(record, dict):
            msg = "provenance block record must be an object"
            raise TypeError(msg)
        singular_reference = record.get("blockReference")
        grouped_references = record.get("blockReferences")
        if isinstance(singular_reference, str):
            candidate_references = [singular_reference]
        elif isinstance(grouped_references, list) and all(
            isinstance(reference, str) for reference in grouped_references
        ):
            candidate_references = cast("list[str]", grouped_references)
        else:
            msg = "provenance block record has no reference"
            raise ValueError(msg)
        attributes: dict[str, JsonValue] = {
            "publicationDisposition": record.get("publicationDisposition", "published"),
        }
        derivation_type = record.get("derivationType")
        if isinstance(derivation_type, str):
            attributes["derivationType"] = derivation_type
        for reference in candidate_references:
            indexed[reference] = attributes
    return indexed


def sha256_file(path: Path) -> str:
    """Return a lowercase SHA-256 checksum for a file."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def region_source_checksum(
    region: Mapping[str, JsonValue],
    *,
    owner_source_checksum: str,
) -> str:
    """Bind one page region review to its inventory and canonical owner bytes."""

    payload: dict[str, JsonValue] = {
        "region": dict(region),
        "ownerSourceChecksum": owner_source_checksum,
    }
    return hashlib.sha256(rfc8785.dumps(payload)).hexdigest()


def aggregate_checksum(paths: Iterable[Path], *, root: Path) -> str:
    """Calculate the policy-defined aggregate checksum for canonical files."""

    normalized_paths = sorted(
        (path.resolve() for path in paths),
        key=lambda path: path.relative_to(root.resolve()).as_posix().encode(),
    )
    records = "".join(
        f"{sha256_file(path)}  {path.relative_to(root).as_posix()}\n" for path in normalized_paths
    )
    return hashlib.sha256(records.encode()).hexdigest()


def criterion_source_checksum(
    slug: str,
    domain_identifier: str,
    *,
    root: Path,
) -> str:
    """Calculate a criterion package checksum without generated files."""

    criterion_paths = [
        root / domain_identifier / f"{slug}.md",
        root / domain_identifier / f"{slug}.provenance.yaml",
    ]
    optional_table_path = root / domain_identifier / f"{slug}.tables.yaml"
    if optional_table_path.exists():
        criterion_paths.append(optional_table_path)
    asset_directory = root / "assets" / slug
    if asset_directory.exists():
        criterion_paths.extend(path for path in asset_directory.rglob("*") if path.is_file())
    return aggregate_checksum(criterion_paths, root=root)


def canonical_corpus_checksum(
    criteria: Sequence[Mapping[str, JsonValue]],
    *,
    root: Path,
) -> str:
    """Calculate the checksum of canonical criterion, registry, and schema files."""

    canonical_paths = [
        *root.glob("data/*.yaml"),
        *root.glob("data/derived/*.json"),
        *root.glob("schemas/*.json"),
    ]
    for criterion in criteria:
        slug = criterion.get("slug")
        domain_identifier = criterion.get("domainIdentifier")
        if not isinstance(slug, str) or not isinstance(domain_identifier, str):
            msg = "criterion manifest record requires slug and domainIdentifier"
            raise TypeError(msg)
        criterion_directory = root / domain_identifier
        canonical_paths.extend(
            [
                criterion_directory / f"{slug}.md",
                criterion_directory / f"{slug}.provenance.yaml",
            ]
        )
        optional_table_path = criterion_directory / f"{slug}.tables.yaml"
        if optional_table_path.exists():
            canonical_paths.append(optional_table_path)
        asset_directory = root / "assets" / slug
        if asset_directory.exists():
            canonical_paths.extend(path for path in asset_directory.rglob("*") if path.is_file())
    return aggregate_checksum((path for path in canonical_paths if path.is_file()), root=root)


def is_nfc(value: str) -> bool:
    """Return whether a string uses Unicode NFC normalization."""

    return unicodedata.is_normalized("NFC", value)


def as_mapping(value: JsonValue, *, location: str) -> dict[str, JsonValue]:
    """Narrow a JSON value to a mapping or raise a contextual error."""

    if not isinstance(value, dict):
        msg = f"{location} must be an object"
        raise ValueError(msg)
    return value


def as_sequence(value: JsonValue, *, location: str) -> list[JsonValue]:
    """Narrow a JSON value to an array or raise a contextual error."""

    if not isinstance(value, list):
        msg = f"{location} must be an array"
        raise ValueError(msg)
    return value
