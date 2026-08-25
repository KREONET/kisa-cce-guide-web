"""Build the self-contained static website from normalized JSON."""

from __future__ import annotations

import html
import json
import shutil
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import rfc8785
from markdown_it import MarkdownIt

from conversion.common import JsonValue, as_mapping, as_sequence

_HIGHLIGHT_LANGUAGE_ALIASES = {
    "asp": "xml",
    "batch": "dos",
    "console": "shell",
    "csh": "bash",
    "freemarker": "xml",
    "html": "xml",
    "sh": "bash",
    "shell": "bash",
    "velocity": "xml",
}
_HIGHLIGHT_COMMON_LANGUAGES = frozenset(
    {
        "bash",
        "c",
        "cpp",
        "csharp",
        "css",
        "diff",
        "go",
        "graphql",
        "ini",
        "java",
        "javascript",
        "json",
        "kotlin",
        "less",
        "lua",
        "makefile",
        "markdown",
        "objectivec",
        "perl",
        "php",
        "php-template",
        "plaintext",
        "python",
        "python-repl",
        "r",
        "ruby",
        "rust",
        "scss",
        "shell",
        "sql",
        "swift",
        "typescript",
        "vbnet",
        "wasm",
        "xml",
        "yaml",
    }
)
_HIGHLIGHT_ADDITIONAL_LANGUAGE_SCRIPTS = {
    language: f"/assets/vendor/highlight.js/languages/{language}.min.js"
    for language in ("apache", "dos", "http", "nginx", "powershell", "properties")
}
_HIGHLIGHT_SUPPORTED_LANGUAGES = _HIGHLIGHT_COMMON_LANGUAGES | frozenset(
    _HIGHLIGHT_ADDITIONAL_LANGUAGE_SCRIPTS
)
_TABLE_OF_CONTENTS_MINIMUM_HEADING_COUNT = 6


@dataclass(slots=True)
class _TableOfContentsNode:
    """Represent one heading and its ordered descendants."""

    block: dict[str, JsonValue]
    heading_level: int
    children: list[_TableOfContentsNode] = field(default_factory=list)


def _text(value: JsonValue, *, location: str) -> str:
    """Narrow a JSON value to text."""

    if not isinstance(value, str):
        msg = f"{location} must be a string"
        raise TypeError(msg)
    return value


def _site_url(path: str, *, base_path: str) -> str:
    """Prefix a canonical route with an optional hosting base path."""

    normalized_base = "/" + base_path.strip("/") if base_path.strip("/") else ""
    normalized_path = "/" + path.lstrip("/")
    return normalized_base + normalized_path


def _inline_renderer() -> MarkdownIt:
    """Create a raw-HTML-disabled CommonMark inline renderer."""

    return MarkdownIt("commonmark", {"html": False})


def _inline_html(value: str, *, parser: MarkdownIt) -> str:
    """Render constrained inline Markdown."""

    return parser.renderInline(value)


def _highlight_language(block: Mapping[str, JsonValue]) -> str | None:
    """Return the explicit Highlight.js language for one eligible code block."""

    if block.get("blockType") != "codeBlock":
        return None
    content_type = _text(
        block.get("codeContentType", "literal"),
        location="block.codeContentType",
    )
    language = _text(block.get("codeLanguage", "text"), location="block.codeLanguage")
    if content_type == "transcription" or language in {"text", "plaintext"}:
        return None
    highlight_language = _HIGHLIGHT_LANGUAGE_ALIASES.get(language, language)
    return highlight_language if highlight_language in _HIGHLIGHT_SUPPORTED_LANGUAGES else None


def _html_document(
    *,
    title: str,
    description: str,
    body: str,
    base_path: str,
    extra_scripts: Sequence[str] = (),
    extra_stylesheets: Sequence[str] = (),
    canonical_url: str | None = None,
    current_navigation: str | None = None,
    domain_navigation: str,
    json_alternate_url: str | None = None,
    structured_data: Mapping[str, JsonValue] | None = None,
) -> str:
    """Wrap one page in the shared accessible site shell."""

    def navigation_current(identifier: str) -> str:
        return ' aria-current="page"' if identifier == current_navigation else ""

    script_tags = "\n".join(
        f'<script src="{html.escape(_site_url(script, base_path=base_path), quote=True)}" defer></script>'
        for script in ["/assets/site.js", *extra_scripts]
    )
    stylesheet_tags = "\n".join(
        f'  <link rel="stylesheet" href="{html.escape(_site_url(stylesheet, base_path=base_path), quote=True)}">'
        for stylesheet in extra_stylesheets
    )
    if stylesheet_tags:
        stylesheet_tags += "\n"
    alternate_link = ""
    if json_alternate_url is not None:
        alternate_link = (
            '  <link rel="alternate" type="application/json" href="'
            + html.escape(json_alternate_url, quote=True)
            + '">\n'
        )
    canonical_link = ""
    if canonical_url is not None:
        canonical_link = (
            '  <link rel="canonical" href="' + html.escape(canonical_url, quote=True) + '">\n'
        )
    structured_data_script = ""
    if structured_data is not None:
        serialized_structured_data = json.dumps(
            structured_data,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        serialized_structured_data = (
            serialized_structured_data.replace("&", "\\u0026")
            .replace("<", "\\u003c")
            .replace(">", "\\u003e")
        )
        structured_data_script = (
            '  <script type="application/ld+json">' + serialized_structured_data + "</script>\n"
        )
    domain_navigation_markup = domain_navigation
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="{html.escape(description, quote=True)}">
  <meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'self'; base-uri 'self'">
  <title>{html.escape(title)}</title>
{canonical_link}{alternate_link}{structured_data_script}{stylesheet_tags}  <link rel="stylesheet" href="{html.escape(_site_url("/assets/styles.css", base_path=base_path), quote=True)}">
</head>
<body>
  <a class="skip-link" href="#main-content">본문으로 바로가기</a>
  <header class="site-header">
    <div class="site-header__inner">
      <a class="site-brand" href="{html.escape(_site_url("/", base_path=base_path), quote=True)}" aria-label="KISA CCE 가이드 2026 홈">
        <span class="site-brand__mark" aria-hidden="true"></span>
        <span class="site-brand__name">KISA CCE</span>
        <span class="site-brand__edition">GUIDE 2026</span>
      </a>
      <button class="nav-toggle" type="button" aria-expanded="true" aria-controls="site-navigation" data-navigation-toggle hidden>메뉴</button>
      <nav id="site-navigation" class="site-nav" aria-label="주요 메뉴" data-site-navigation data-open="true">
        {domain_navigation_markup}
        <a href="{html.escape(_site_url("/search/", base_path=base_path), quote=True)}"{navigation_current("search")}>검색</a>
      </nav>
    </div>
  </header>
  {body}
  <footer class="site-footer">
    <div class="site-footer__inner">
      <p class="site-footer__brand"><span aria-hidden="true"></span>KISA CCE GUIDE</p>
    </div>
  </footer>
  <div class="visually-hidden" role="status" aria-live="polite" aria-atomic="true" data-copy-status></div>
  {script_tags}
</body>
</html>
"""


def _taxonomy_maps(
    taxonomy: Mapping[str, JsonValue],
) -> tuple[
    dict[str, dict[str, JsonValue]],
    dict[tuple[str, str], dict[str, JsonValue]],
    dict[str, str],
]:
    """Create domain, category, and target lookup maps."""

    domains = {
        _text(record["identifier"], location="taxonomy.domain.identifier"): record
        for record_value in as_sequence(taxonomy["domains"], location="taxonomy.domains")
        if isinstance(record_value, dict) and (record := record_value)
    }
    categories = {
        (
            _text(record["domainIdentifier"], location="taxonomy.category.domainIdentifier"),
            _text(record["identifier"], location="taxonomy.category.identifier"),
        ): record
        for record_value in as_sequence(
            taxonomy["categories"],
            location="taxonomy.categories",
        )
        if isinstance(record_value, dict) and (record := record_value)
    }
    targets = {
        _text(record["identifier"], location="taxonomy.target.identifier"): _text(
            record["label"],
            location="taxonomy.target.label",
        )
        for record_value in as_sequence(taxonomy["targets"], location="taxonomy.targets")
        if isinstance(record_value, dict) and (record := record_value)
    }
    return domains, categories, targets


def _render_domain_navigation_items(
    *,
    domains: Mapping[str, dict[str, JsonValue]],
    current_domain: str | None,
    base_path: str,
) -> str:
    """Render the shared ordered domain navigation items."""

    items = []
    for domain_identifier, domain in sorted(
        domains.items(),
        key=lambda item: int(cast("int", item[1]["order"])),
    ):
        current = ' aria-current="location"' if domain_identifier == current_domain else ""
        label = _text(domain["label"], location="taxonomy.domain.label")
        route = _site_url(f"/{domain_identifier}/", base_path=base_path)
        items.append(
            f'<li><a href="{html.escape(route, quote=True)}"{current}>{html.escape(label)}</a></li>'
        )
    return "".join(items)


def _render_header_domain_navigation(
    *,
    domains: Mapping[str, dict[str, JsonValue]],
    current_domain: str | None,
    current: bool,
    base_path: str,
) -> str:
    """Render domain navigation inside the primary header menu."""

    items = _render_domain_navigation_items(
        domains=domains,
        current_domain=current_domain,
        base_path=base_path,
    )
    all_domains_route = html.escape(_site_url("/", base_path=base_path), quote=True)
    current_attribute = ' data-current-navigation="true"' if current else ""
    return (
        f'<details class="site-nav__domains"{current_attribute}>'
        '<summary>분야</summary><ul>'
        f'<li><a href="{all_domains_route}">전체 분야</a></li>'
        + items
        + "</ul></details>"
    )


def _block_identifier(block: Mapping[str, JsonValue]) -> str:
    """Return one normalized block reference."""

    return _text(block["blockReference"], location="block.blockReference")


def _render_table_of_contents_outline(
    heading_blocks: Sequence[dict[str, JsonValue]],
) -> str:
    """Render the document heading outline as valid nested lists."""

    if len(heading_blocks) < _TABLE_OF_CONTENTS_MINIMUM_HEADING_COUNT:
        return ""

    roots: list[_TableOfContentsNode] = []
    ancestors: list[_TableOfContentsNode] = []
    for block in heading_blocks:
        heading_level = int(cast("int", block["headingLevel"]))
        node = _TableOfContentsNode(block=block, heading_level=heading_level)
        while ancestors and heading_level <= ancestors[-1].heading_level:
            ancestors.pop()
        if ancestors:
            ancestors[-1].children.append(node)
        else:
            roots.append(node)
        ancestors.append(node)

    def render_nodes(
        nodes: Sequence[_TableOfContentsNode],
        *,
        depth: int = 1,
        root: bool = False,
    ) -> str:
        list_class = "toc__list toc__list--root" if root else "toc__list"
        items = []
        for node in nodes:
            block_identifier = html.escape(_block_identifier(node.block), quote=True)
            heading_text = html.escape(_text(node.block["content"], location="block.content"))
            child_list = render_nodes(node.children, depth=depth + 1) if node.children else ""
            items.append(
                f'<li class="toc__item" data-toc-depth="{depth}" '
                f'data-toc-heading-level="{node.heading_level}">'
                f'<a href="#{block_identifier}" data-toc-depth="{depth}" '
                f'data-toc-heading-level="{node.heading_level}">'
                f"{heading_text}</a>{child_list}</li>"
            )
        return f'<ul class="{list_class}" data-toc-depth="{depth}">' + "".join(items) + "</ul>"

    return render_nodes(roots, root=True)


def _render_table_of_contents(heading_blocks: Sequence[dict[str, JsonValue]]) -> str:
    """Render the collapsible in-content document outline."""

    outline = _render_table_of_contents_outline(heading_blocks)
    if not outline:
        return ""
    return (
        '<nav class="toc" aria-label="문서 목차" data-table-of-contents>'
        '<button class="toc__toggle" type="button" aria-expanded="true" '
        'aria-controls="table-of-contents-content" data-table-of-contents-toggle hidden>목차</button>'
        '<strong class="toc__title" id="table-of-contents-title">목차</strong>'
        '<div id="table-of-contents-content" data-table-of-contents-content>'
        + outline
        + "</div></nav>"
    )


def _html_attributes(attributes: Mapping[str, str]) -> str:
    """Serialize deterministic escaped HTML attributes."""

    return " ".join(
        f'{name}="{html.escape(value, quote=True)}"' for name, value in attributes.items()
    )


def _block_attributes(
    block: Mapping[str, JsonValue],
    *,
    extra: Mapping[str, str] | None = None,
) -> str:
    """Expose normalized identity, semantics, hierarchy, and provenance on one element."""

    identifier = _block_identifier(block)
    semantic_path = as_sequence(block["semanticPath"], location="block.semanticPath")
    source_spans = as_sequence(block["sourceSpans"], location="block.sourceSpans")
    source_region_identifiers: list[str] = []
    source_physical_pages: list[str] = []
    source_printed_pages: list[str] = []
    for span_value in source_spans:
        span = as_mapping(span_value, location="block.sourceSpans[]")
        region_identifier = _text(
            span["pageRegionIdentifier"],
            location="block.sourceSpans[].pageRegionIdentifier",
        )
        physical_page = str(int(cast("int", span["physicalPage"])))
        printed_page = _text(
            span["printedPage"],
            location="block.sourceSpans[].printedPage",
        )
        if region_identifier not in source_region_identifiers:
            source_region_identifiers.append(region_identifier)
        if physical_page not in source_physical_pages:
            source_physical_pages.append(physical_page)
        if printed_page not in source_printed_pages:
            source_printed_pages.append(printed_page)

    attributes = {
        "id": identifier,
        "data-block-reference": identifier,
        "data-block-type": _text(block["blockType"], location="block.blockType"),
        "data-semantic-role": _text(block["semanticRole"], location="block.semanticRole"),
        "data-semantic-path": "/".join(
            _text(value, location="block.semanticPath[]") for value in semantic_path
        ),
        "data-publication-disposition": _text(
            block["publicationDisposition"],
            location="block.publicationDisposition",
        ),
        "data-source-region-identifiers": " ".join(source_region_identifiers),
        "data-source-physical-pages": " ".join(source_physical_pages),
        "data-source-printed-pages": " ".join(source_printed_pages),
    }
    parent_reference = block.get("parentBlockReference")
    if isinstance(parent_reference, str):
        attributes["data-parent-block-reference"] = parent_reference
    if extra is not None:
        attributes.update(extra)
    return _html_attributes(attributes)


def _render_table(
    block: Mapping[str, JsonValue],
    *,
    parser: MarkdownIt,
) -> str:
    """Render a typed accessible table."""

    identifier = _block_identifier(block)
    headers = as_sequence(block["tableHeaders"], location="block.tableHeaders")
    rows = as_sequence(block["tableRows"], location="block.tableRows")
    header_cells = []
    for column_index, value in enumerate(headers, start=1):
        header_text = _text(value, location="table.header")
        header_content = (
            _inline_html(header_text, parser=parser)
            if header_text
            else f'<span class="visually-hidden">{column_index}번째 열</span>'
        )
        header_cells.append(f'<th scope="col">{header_content}</th>')
    header_html = "".join(header_cells)
    row_html = []
    for row_value in rows:
        row = as_sequence(row_value, location="table.row")
        if len(row) != len(headers):
            msg = f"{identifier} table row has {len(row)} cells; expected {len(headers)} cells"
            raise ValueError(msg)
        cells = "".join(
            f"<td>{_inline_html(_text(value, location='table.cell'), parser=parser)}</td>"
            for value in row
        )
        row_html.append(f"<tr>{cells}</tr>")
    caption_value = block.get("caption")
    label = (
        caption_value
        if isinstance(caption_value, str) and caption_value
        else f"원문 표 {_text(block['semanticRole'], location='block.semanticRole')}"
    )
    caption_identifier = f"caption-{identifier}"
    table_attributes = _block_attributes(
        block,
        extra={
            "data-table-column-count": str(len(headers)),
            "data-table-row-count": str(len(rows)),
        },
    )
    return (
        '<div class="table-scroll" role="region" '
        f'aria-labelledby="{html.escape(caption_identifier, quote=True)}" tabindex="0">'
        f'<table {table_attributes}><caption id="{html.escape(caption_identifier, quote=True)}">'
        f"{html.escape(label)}</caption><thead><tr>{header_html}</tr></thead>"
        f"<tbody>{''.join(row_html)}</tbody></table>"
        "</div>"
    )


def _render_code(block: Mapping[str, JsonValue]) -> str:
    """Render a typed code or transcription block."""

    identifier = _block_identifier(block)
    code_identifier = f"code-{identifier}"
    language = _text(block.get("codeLanguage", "text"), location="block.codeLanguage")
    content_type = _text(
        block.get("codeContentType", "literal"),
        location="block.codeContentType",
    )
    content = _text(block["content"], location="block.content")
    highlight_language = _highlight_language(block)
    rendered_language = highlight_language or language
    transcription_class = " code-block--transcription" if content_type == "transcription" else ""
    content_label = {
        "command": "명령",
        "configuration": "설정",
        "output": "출력",
        "literal": "리터럴",
        "transcription": "원문 전사",
    }.get(content_type, content_type)
    code_profile_attributes = {
        "data-code-content-type": content_type,
        "data-code-language": language,
    }
    if highlight_language is not None:
        code_profile_attributes["data-highlight-language"] = highlight_language
    pre_attributes = _block_attributes(block, extra=code_profile_attributes)
    code_attributes = _html_attributes(code_profile_attributes)
    return (
        f'<div class="code-block{transcription_class}">'
        f'<button class="copy-button" type="button" data-copy-button="{html.escape(code_identifier, quote=True)}" hidden '
        f'aria-controls="{html.escape(code_identifier, quote=True)}" '
        f'aria-label="{html.escape(content_label)} 복사">복사</button>'
        f'<pre {pre_attributes} aria-label="{html.escape(content_label, quote=True)} 내용"><code '
        f'id="{html.escape(code_identifier, quote=True)}" class="language-{html.escape(rendered_language, quote=True)}" '
        f"{code_attributes}>"
        f"{html.escape(content)}</code></pre></div>"
    )


def _render_image(
    block: Mapping[str, JsonValue],
    *,
    base_path: str,
) -> str:
    """Render a source image with a keyboard-accessible full-size link."""

    identifier = _block_identifier(block)
    asset_path = _text(block["assetPath"], location="block.assetPath")
    alternative_text = _text(block["alternativeText"], location="block.alternativeText")
    alternative_text_status = _text(
        block["alternativeTextStatus"],
        location="block.alternativeTextStatus",
    )
    pixel_dimensions = as_sequence(
        block["outputPixelDimensions"],
        location="block.outputPixelDimensions",
    )
    pixel_width = int(cast("int", pixel_dimensions[0]))
    pixel_height = int(cast("int", pixel_dimensions[1]))
    caption_value = block.get("caption")
    caption = caption_value if isinstance(caption_value, str) else alternative_text
    asset_url = _site_url("/" + asset_path.lstrip("/"), base_path=base_path)
    review_status = (
        '<span class="badge badge--review">대체 텍스트 검토 필요</span>'
        if alternative_text_status == "verificationRequired"
        else '<span class="badge">대체 텍스트 검토 완료</span>'
    )
    caption_identifier = f"caption-{identifier}"
    figure_attributes = _block_attributes(
        block,
        extra={
            "data-asset-type": _text(block["assetType"], location="block.assetType"),
            "data-rendering-profile": _text(
                block["renderingProfileIdentifier"],
                location="block.renderingProfileIdentifier",
            ),
            "data-alternative-text-status": alternative_text_status,
        },
    )
    return (
        f'<figure class="source-visual" {figure_attributes} '
        f'aria-labelledby="{html.escape(caption_identifier, quote=True)}">'
        f'<a href="{html.escape(asset_url, quote=True)}" aria-label="{html.escape(alternative_text, quote=True)} 원본 크기로 보기">'
        f'<img src="{html.escape(asset_url, quote=True)}" alt="{html.escape(alternative_text, quote=True)}" '
        f'width="{pixel_width}" height="{pixel_height}" '
        'loading="lazy" decoding="async"></a>'
        f'<figcaption id="{html.escape(caption_identifier, quote=True)}">'
        f"{html.escape(caption)} {review_status}</figcaption></figure>"
    )


def _render_blocks(block_values: list[JsonValue], *, base_path: str) -> str:
    """Render typed blocks while preserving list and parent ownership."""

    parser = _inline_renderer()
    blocks = [
        as_mapping(block_value, location="normalized.blocks[]") for block_value in block_values
    ]
    children: dict[str, list[dict[str, JsonValue]]] = defaultdict(list)
    top_level: list[dict[str, JsonValue]] = []
    for block in blocks:
        parent = block.get("parentBlockReference")
        if isinstance(parent, str):
            children[parent].append(block)
        else:
            top_level.append(block)

    def render_list_item(block: dict[str, JsonValue]) -> str:
        identifier = _block_identifier(block)
        list_type = _text(block["listType"], location="block.listType")
        list_depth = str(int(cast("int", block["listDepth"])))
        content = _inline_html(
            _text(block["content"], location="block.content"),
            parser=parser,
        )
        child_values = children.get(identifier, [])
        child_html = render_sequence(child_values)
        attributes = _block_attributes(
            block,
            extra={"data-list-type": list_type, "data-list-depth": list_depth},
        )
        return f"<li {attributes}>{content}{child_html}</li>"

    def render_single(block: dict[str, JsonValue]) -> str:
        block_type = _text(block["blockType"], location="block.blockType")
        content = _text(block["content"], location="block.content")
        if block_type == "heading":
            heading_level = int(cast("int", block["headingLevel"]))
            attributes = _block_attributes(
                block,
                extra={"data-heading-level": str(heading_level)},
            )
            return (
                f"<h{heading_level} {attributes}>"
                f"{_inline_html(content, parser=parser)}</h{heading_level}>"
            )
        if block_type == "paragraph":
            return f"<p {_block_attributes(block)}>{_inline_html(content, parser=parser)}</p>"
        if block_type == "codeBlock":
            return _render_code(block)
        if block_type == "table":
            return _render_table(block, parser=parser)
        if block_type == "image":
            return _render_image(block, base_path=base_path)
        if block_type == "listItem":
            return render_list_item(block)
        if block_type == "noteContent":
            return f"<p {_block_attributes(block)}>{_inline_html(content, parser=parser)}</p>"
        if block_type == "noteLabel":
            return (
                f'<p class="note__label" {_block_attributes(block)}>'
                f"{_inline_html(content, parser=parser)}</p>"
            )
        msg = f"unsupported normalized block type: {block_type}"
        raise ValueError(msg)

    def render_sequence(sequence: Sequence[dict[str, JsonValue]]) -> str:
        parts: list[str] = []
        index = 0
        while index < len(sequence):
            block = sequence[index]
            block_type = block.get("blockType")
            if block_type == "listItem":
                list_type = block.get("listType")
                semantic_path = block.get("semanticPath")
                grouped = []
                while index < len(sequence):
                    candidate = sequence[index]
                    if (
                        candidate.get("blockType") != "listItem"
                        or candidate.get("listType") != list_type
                        or candidate.get("semanticPath") != semantic_path
                    ):
                        break
                    grouped.append(candidate)
                    index += 1
                tag = "ol" if list_type == "ordered" else "ul"
                first_list_depth = str(int(cast("int", grouped[0]["listDepth"])))
                parts.append(
                    f'<{tag} data-list-type="{html.escape(_text(list_type, location="block.listType"), quote=True)}" '
                    f'data-list-depth="{html.escape(first_list_depth, quote=True)}">'
                    + "".join(render_list_item(item) for item in grouped)
                    + f"</{tag}>"
                )
                continue
            if block_type == "noteLabel":
                note_blocks = [block]
                index += 1
                while index < len(sequence) and sequence[index].get("blockType") not in {
                    "heading",
                    "noteLabel",
                }:
                    note_blocks.append(sequence[index])
                    index += 1
                note_label_identifier = _block_identifier(note_blocks[0])
                parts.append(
                    '<aside class="note" role="note" aria-labelledby="'
                    + html.escape(note_label_identifier, quote=True)
                    + '" data-note-label-reference="'
                    + html.escape(note_label_identifier, quote=True)
                    + '">'
                    + render_single(note_blocks[0])
                    + render_sequence(note_blocks[1:])
                    + "</aside>"
                )
                continue
            parts.append(render_single(block))
            index += 1
        return "".join(parts)

    return render_sequence(top_level)


def _criterion_list(
    records: Sequence[Mapping[str, JsonValue]],
    *,
    base_path: str,
) -> str:
    """Render a static criterion list."""

    items = []
    for record in records:
        code = _text(record["code"], location="manifest.code")
        title = _text(record["title"], location="manifest.title")
        route = _text(record["route"], location="manifest.route")
        severity = _text(record["severitySourceLabel"], location="manifest.severity")
        items.append(
            '<li><a href="'
            + html.escape(_site_url(route, base_path=base_path), quote=True)
            + '"><strong>'
            + html.escape(code)
            + "</strong><span>"
            + html.escape(title)
            + '</span><span class="badge">'
            + html.escape(severity)
            + "</span></a></li>"
        )
    return '<ul class="criterion-list">' + "".join(items) + "</ul>"


def _detail_page(
    *,
    normalized: dict[str, JsonValue],
    previous_record: dict[str, JsonValue] | None,
    next_record: dict[str, JsonValue] | None,
    domains: Mapping[str, dict[str, JsonValue]],
    categories: Mapping[tuple[str, str], dict[str, JsonValue]],
    targets: Mapping[str, str],
    source_document: Mapping[str, JsonValue],
    base_path: str,
) -> str:
    """Render one criterion detail page."""

    criterion = as_mapping(normalized["criterion"], location="normalized.criterion")
    classification = as_mapping(
        normalized["classification"],
        location="normalized.classification",
    )
    provenance = as_mapping(
        normalized["provenance"],
        location="normalized.provenance",
    )
    code = _text(criterion["code"], location="criterion.code")
    title = _text(criterion["title"], location="criterion.title")
    severity = as_mapping(criterion["severity"], location="criterion.severity")
    severity_level = _text(severity["level"], location="severity.level")
    severity_source = _text(severity["sourceLabel"], location="severity.sourceLabel")
    domain_identifier = _text(
        classification["domainIdentifier"],
        location="classification.domainIdentifier",
    )
    category_identifier = _text(
        classification["categoryIdentifier"],
        location="classification.categoryIdentifier",
    )
    domain = domains[domain_identifier]
    category = categories[(domain_identifier, category_identifier)]
    domain_label = _text(domain["label"], location="domain.label")
    category_label = _text(category["label"], location="category.label")
    target_identifiers = as_sequence(
        normalized["targetIdentifiers"],
        location="normalized.targetIdentifiers",
    )
    target_labels = [
        targets.get(_text(value, location="targetIdentifier"), "확인 필요")
        for value in target_identifiers
    ]
    blocks = as_sequence(normalized["blocks"], location="normalized.blocks")
    highlight_languages = sorted(
        {
            language
            for block_value in blocks
            if isinstance(block_value, dict)
            and (language := _highlight_language(block_value)) is not None
        }
    )
    highlight_scripts: tuple[str, ...] = ()
    highlight_stylesheets: tuple[str, ...] = ()
    if highlight_languages:
        highlight_scripts = (
            "/assets/vendor/highlight.js/highlight.min.js",
            *(
                _HIGHLIGHT_ADDITIONAL_LANGUAGE_SCRIPTS[language]
                for language in highlight_languages
                if language in _HIGHLIGHT_ADDITIONAL_LANGUAGE_SCRIPTS
            ),
            "/assets/highlight-init.js",
        )
        highlight_stylesheets = ("/assets/vendor/highlight.js/github-dark.min.css",)
    heading_blocks = [
        as_mapping(block, location="normalized.blocks[]")
        for block in blocks
        if isinstance(block, dict) and block.get("blockType") == "heading"
    ]
    toc = _render_table_of_contents(heading_blocks)
    document_class = "criterion__document criterion__document--with-toc" if toc else "criterion__document"
    content_model = _text(normalized["contentModel"], location="normalized.contentModel")
    review_label = (
        "자동 전사 · 검토 필요" if content_model == "extractedCriterion" else "구조화 문서"
    )
    source_ranges = as_sequence(
        provenance["sourcePageRanges"],
        location="provenance.sourcePageRanges",
    )
    source_range = as_mapping(source_ranges[0], location="provenance.sourcePageRanges[0]")
    first_page = int(cast("int", source_range["physicalPageStart"]))
    last_page = int(cast("int", source_range["physicalPageEnd"]))
    pdf_url = _text(
        source_document["sourceUrl"],
        location="source.sourceUrl",
    )
    source_title = _text(source_document["title"], location="source.title")
    source_publisher = _text(source_document["publisher"], location="source.publisher")
    article_attributes = (
        f'data-criterion-code="{html.escape(code, quote=True)}" '
        f'data-severity="{html.escape(severity_level, quote=True)}" '
        f'data-content-model="{html.escape(content_model, quote=True)}" '
        f'data-source-document="{html.escape(_text(provenance["sourceDocumentIdentifier"], location="provenance.sourceDocumentIdentifier"), quote=True)}"'
    )
    pager_links = []
    if previous_record is not None:
        pager_links.append(
            '<a rel="prev" href="'
            + html.escape(
                _site_url(
                    _text(previous_record["route"], location="previous.route"), base_path=base_path
                ),
                quote=True,
            )
            + '">← '
            + html.escape(_text(previous_record["code"], location="previous.code"))
            + "</a>"
        )
    else:
        pager_links.append("<span></span>")
    if next_record is not None:
        pager_links.append(
            '<a rel="next" href="'
            + html.escape(
                _site_url(_text(next_record["route"], location="next.route"), base_path=base_path),
                quote=True,
            )
            + '">'
            + html.escape(_text(next_record["code"], location="next.code"))
            + " →</a>"
        )
    breadcrumb = (
        '<nav class="breadcrumb" aria-label="분류 경로"><ol>'
        f'<li><a href="{html.escape(_site_url("/", base_path=base_path), quote=True)}">홈</a></li>'
        f'<li><a href="{html.escape(_site_url(f"/{domain_identifier}/", base_path=base_path), quote=True)}">{html.escape(domain_label)}</a></li>'
        f'<li><a href="{html.escape(_site_url(f"/{domain_identifier}/{category_identifier}/", base_path=base_path), quote=True)}">{html.escape(category_label)}</a></li>'
        f"<li>{html.escape(code)}</li></ol></nav>"
    )
    dataset_url = _site_url(
        f"/dataset/criteria/{domain_identifier}/{_text(criterion['slug'], location='criterion.slug')}.json",
        base_path=base_path,
    )
    criterion_url = _site_url(
        f"/{domain_identifier}/{_text(criterion['slug'], location='criterion.slug')}/",
        base_path=base_path,
    )
    structured_data: dict[str, JsonValue] = {
        "@context": "https://schema.org",
        "@type": "TechArticle",
        "identifier": code,
        "name": f"{code} {title}",
        "description": f"{code} {title} 점검항목",
        "mainEntityOfPage": criterion_url,
        "url": criterion_url,
        "about": [domain_label, category_label, *target_labels],
        "isPartOf": {
            "@type": "CreativeWork",
            "name": "KISA CCE 가이드 2026",
        },
        "isBasedOn": {
            "@type": "CreativeWork",
            "name": source_title,
            "publisher": {
                "@type": "Organization",
                "name": source_publisher,
            },
            "url": pdf_url,
        },
        "articleSection": f"{domain_label} / {category_label}",
        "keywords": [severity_source, *target_labels],
        "pagination": f"{first_page}-{last_page}",
    }
    body = (
        '<main id="main-content" class="page-shell page-shell--detail">'
        '<div class="content">'
        + breadcrumb
        + f'<article class="criterion" {article_attributes}>'
        + '<header class="criterion__header">'
        + f"<h1>{html.escape(code)} {html.escape(title)}</h1>"
        + '<dl class="criterion-meta">'
        + '<dt class="visually-hidden">중요도</dt>'
        + f'<dd class="badge badge--{html.escape(severity_level)}"><span aria-hidden="true">중요도 </span>{html.escape(severity_source)}</dd>'
        + '<dt class="visually-hidden">분야</dt>'
        + f'<dd class="badge">{html.escape(domain_label)}</dd>'
        + '<dt class="visually-hidden">분류</dt>'
        + f'<dd class="badge">{html.escape(category_label)}</dd>'
        + '<dt class="visually-hidden">문서 상태</dt>'
        + f'<dd class="badge badge--review">{html.escape(review_label)}</dd>'
        + '<dt class="visually-hidden">대상</dt>'
        + f'<dd><span aria-hidden="true">대상: </span>{html.escape(", ".join(target_labels))}</dd>'
        + '<dt class="visually-hidden">원문 페이지</dt>'
        + f'<dd><span aria-hidden="true">원문 페이지: </span>{first_page}-{last_page}</dd>'
        + "</dl>"
        + f'<p><a type="application/json" href="{html.escape(dataset_url, quote=True)}">JSON 데이터 보기</a></p>'
        + "</header>"
        + f'<div class="{document_class}">'
        + toc
        + '<div class="criterion__body">'
        + _render_blocks(blocks, base_path=base_path)
        + "</div></div></article>"
        + '<nav class="pager" aria-label="이전 및 다음 항목">'
        + "".join(pager_links)
        + "</nav></div></main>"
    )
    return _html_document(
        title=f"{code} {title} · KISA CCE 가이드 2026",
        description=f"{code} {title} 점검항목",
        body=body,
        base_path=base_path,
        extra_scripts=highlight_scripts,
        extra_stylesheets=highlight_stylesheets,
        canonical_url=criterion_url,
        current_navigation="domains",
        domain_navigation=_render_header_domain_navigation(
            domains=domains,
            current_domain=domain_identifier,
            current=True,
            base_path=base_path,
        ),
        json_alternate_url=dataset_url,
        structured_data=structured_data,
    )


def build_site(
    *,
    repository: Path,
    output_root: Path,
    manifest: dict[str, JsonValue],
    taxonomy: dict[str, JsonValue],
    source_registry: dict[str, JsonValue],
    normalized_documents: Sequence[dict[str, JsonValue]],
    search_index: dict[str, JsonValue],
    base_path: str = "",
) -> list[Path]:
    """Build every static route and public dataset."""

    site_root = output_root / "site"
    if site_root.exists():
        shutil.rmtree(site_root)
    site_root.mkdir(parents=True)
    nojekyll_path = site_root / ".nojekyll"
    nojekyll_path.write_text("", encoding="utf-8")
    domains, categories, targets = _taxonomy_maps(taxonomy)
    manifest_values = as_sequence(manifest["criteria"], location="manifest.criteria")
    manifest_records = [
        as_mapping(value, location="manifest.criteria[]") for value in manifest_values
    ]
    source_documents = as_sequence(
        source_registry["documents"],
        location="sourceRegistry.documents",
    )
    source_document = as_mapping(
        source_documents[0],
        location="sourceRegistry.documents[0]",
    )
    generated_paths: list[Path] = [nojekyll_path]

    asset_directory = site_root / "assets"
    asset_directory.mkdir()
    for asset_name in ("styles.css", "site.js", "search.js", "highlight-init.js"):
        source_path = repository / "site_assets" / asset_name
        target_path = asset_directory / asset_name
        shutil.copy2(source_path, target_path)
        generated_paths.append(target_path)
    canonical_asset_directory = repository / "assets"
    if canonical_asset_directory.is_dir():
        shutil.copytree(
            canonical_asset_directory,
            asset_directory,
            dirs_exist_ok=True,
        )
        generated_paths.extend(
            path
            for child_directory in asset_directory.iterdir()
            if child_directory.is_dir()
            for path in child_directory.rglob("*")
            if path.is_file()
        )
    vendor_asset_source = repository / "site_assets" / "vendor"
    vendor_asset_target = asset_directory / "vendor"
    shutil.copytree(vendor_asset_source, vendor_asset_target)
    generated_paths.extend(
        path for path in sorted(vendor_asset_target.rglob("*")) if path.is_file()
    )

    dataset_root = site_root / "dataset"
    criteria_dataset_root = dataset_root / "criteria"
    for normalized in normalized_documents:
        criterion = as_mapping(normalized["criterion"], location="normalized.criterion")
        classification = as_mapping(
            normalized["classification"],
            location="normalized.classification",
        )
        domain_identifier = _text(
            classification["domainIdentifier"],
            location="classification.domainIdentifier",
        )
        slug = _text(criterion["slug"], location="criterion.slug")
        dataset_path = criteria_dataset_root / domain_identifier / f"{slug}.json"
        dataset_path.parent.mkdir(parents=True, exist_ok=True)
        dataset_path.write_bytes(rfc8785.dumps(normalized))
        generated_paths.append(dataset_path)
    search_dataset_path = dataset_root / "search-index.json"
    search_dataset_path.parent.mkdir(parents=True, exist_ok=True)
    search_dataset_path.write_bytes(rfc8785.dumps(search_index))
    taxonomy_dataset_path = dataset_root / "taxonomy.json"
    taxonomy_dataset_path.write_bytes(rfc8785.dumps(taxonomy))
    generated_paths.extend([search_dataset_path, taxonomy_dataset_path])

    records_by_domain: dict[str, list[dict[str, JsonValue]]] = defaultdict(list)
    records_by_category: dict[tuple[str, str], list[dict[str, JsonValue]]] = defaultdict(list)
    for record in manifest_records:
        domain_identifier = _text(record["domainIdentifier"], location="manifest.domain")
        category_identifier = _text(record["categoryIdentifier"], location="manifest.category")
        records_by_domain[domain_identifier].append(record)
        records_by_category[(domain_identifier, category_identifier)].append(record)

    domain_cards = []
    for domain_identifier, domain in sorted(
        domains.items(),
        key=lambda item: int(cast("int", item[1]["order"])),
    ):
        label = _text(domain["label"], location="domain.label")
        count = len(records_by_domain[domain_identifier])
        domain_cards.append(
            '<a class="card" href="'
            + html.escape(_site_url(f"/{domain_identifier}/", base_path=base_path), quote=True)
            + '"><strong>'
            + html.escape(label)
            + "</strong><span>"
            + str(count)
            + "개 점검항목</span></a>"
        )
    root_body = (
        '<main id="main-content" class="page-shell page-shell--single page-shell--home">'
        '<section class="hero" aria-labelledby="hero-heading">'
        '<p class="hero__eyebrow">2026 SECURITY CHECKLIST</p>'
        '<h1 id="hero-heading">KISA CCE 가이드</h1>'
        '<p class="hero__lede">382개 보안 점검항목을 분야별로 탐색하고, 코드·제목·본문·설정값으로 검색할 수 있는 비공식 웹 변환본입니다.</p>'
        '<form class="search-form" action="'
        + html.escape(_site_url("/search/", base_path=base_path), quote=True)
        + '"><label><span class="visually-hidden">검색어</span><input name="q" type="search" placeholder="U-01, PermitRootLogin, 비밀번호 정책"></label>'
        '<button class="primary-button" type="submit">점검항목 검색</button></form>'
        '<dl class="hero__stats" aria-label="가이드 현황">'
        '<div><dt>점검항목</dt><dd>382</dd></div>'
        '<div><dt>기술 분야</dt><dd>12</dd></div>'
        '<div><dt>데이터 형식</dt><dd>HTML + JSON</dd></div>'
        '</dl></section>'
        '<section class="surface domain-directory" aria-labelledby="domain-directory-heading">'
        '<div class="section-heading"><div><p class="section-heading__eyebrow">TECHNICAL DOMAINS</p>'
        '<h2 id="domain-directory-heading">분야별 점검항목</h2></div>'
        '<p>운영 환경을 선택해 분류와 세부 점검항목을 확인하세요.</p></div>'
        '<div class="card-grid">' + "".join(domain_cards) + "</div></section></main>"
    )
    root_path = site_root / "index.html"
    root_path.write_text(
        _html_document(
            title="KISA CCE 가이드 2026",
            description="KISA CCE 2026 점검항목 검색 및 탐색",
            body=root_body,
            base_path=base_path,
            canonical_url=_site_url("/", base_path=base_path),
            current_navigation="domains",
            domain_navigation=_render_header_domain_navigation(
                domains=domains,
                current_domain=None,
                current=True,
                base_path=base_path,
            ),
        ),
        encoding="utf-8",
    )
    generated_paths.append(root_path)

    for domain_identifier in records_by_domain:
        domain = domains[domain_identifier]
        domain_label = _text(domain["label"], location="domain.label")
        sections = []
        domain_categories = [
            (category_identifier, category)
            for (candidate_domain, category_identifier), category in categories.items()
            if candidate_domain == domain_identifier
        ]
        for category_identifier, category in sorted(
            domain_categories,
            key=lambda item: int(cast("int", item[1]["order"])),
        ):
            category_records = records_by_category[(domain_identifier, category_identifier)]
            category_label = _text(category["label"], location="category.label")
            category_route = _site_url(
                f"/{domain_identifier}/{category_identifier}/",
                base_path=base_path,
            )
            sections.append(
                f'<section><h2><a href="{html.escape(category_route, quote=True)}">{html.escape(category_label)}</a></h2>'
                + _criterion_list(category_records, base_path=base_path)
                + "</section>"
            )
            category_body = (
                '<main id="main-content" class="page-shell page-shell--single"><section class="surface">'
                f"<h1>{html.escape(domain_label)} · {html.escape(category_label)}</h1>"
                + _criterion_list(category_records, base_path=base_path)
                + "</section></main>"
            )
            category_path = site_root / domain_identifier / category_identifier / "index.html"
            category_path.parent.mkdir(parents=True, exist_ok=True)
            category_path.write_text(
                _html_document(
                    title=f"{category_label} · {domain_label}",
                    description=f"{domain_label} {category_label} 점검항목",
                    body=category_body,
                    base_path=base_path,
                    canonical_url=category_route,
                    current_navigation="domains",
                    domain_navigation=_render_header_domain_navigation(
                        domains=domains,
                        current_domain=domain_identifier,
                        current=True,
                        base_path=base_path,
                    ),
                ),
                encoding="utf-8",
            )
            generated_paths.append(category_path)
        domain_body = (
            '<main id="main-content" class="page-shell page-shell--single"><section class="surface">'
            f"<h1>{html.escape(domain_label)}</h1>" + "".join(sections) + "</section></main>"
        )
        domain_path = site_root / domain_identifier / "index.html"
        domain_path.parent.mkdir(parents=True, exist_ok=True)
        domain_path.write_text(
            _html_document(
                title=f"{domain_label} · KISA CCE 가이드 2026",
                description=f"{domain_label} 점검항목",
                body=domain_body,
                base_path=base_path,
                canonical_url=_site_url(f"/{domain_identifier}/", base_path=base_path),
                current_navigation="domains",
                domain_navigation=_render_header_domain_navigation(
                    domains=domains,
                    current_domain=domain_identifier,
                    current=True,
                    base_path=base_path,
                ),
            ),
            encoding="utf-8",
        )
        generated_paths.append(domain_path)

    for record_index, (record, normalized) in enumerate(
        zip(manifest_records, normalized_documents, strict=True)
    ):
        previous_record = manifest_records[record_index - 1] if record_index > 0 else None
        next_record = (
            manifest_records[record_index + 1] if record_index + 1 < len(manifest_records) else None
        )
        route = _text(record["route"], location="manifest.route")
        detail_path = site_root / route.strip("/") / "index.html"
        detail_path.parent.mkdir(parents=True, exist_ok=True)
        detail_path.write_text(
            _detail_page(
                normalized=normalized,
                previous_record=previous_record,
                next_record=next_record,
                domains=domains,
                categories=categories,
                targets=targets,
                source_document=source_document,
                base_path=base_path,
            ),
            encoding="utf-8",
        )
        generated_paths.append(detail_path)

    search_fallback = (
        '<section aria-labelledby="search-fallback-heading" data-search-fallback>'
        '<h2 id="search-fallback-heading">전체 점검항목</h2>'
        "<p>브라우저 검색 기능을 사용할 수 없어, 전체 점검항목을 표시합니다.</p>"
        + _criterion_list(manifest_records, base_path=base_path)
        + "</section>"
    )
    search_body = (
        '<main id="main-content" class="page-shell page-shell--single"><section class="surface" '
        'role="search" aria-labelledby="search-heading" data-search-root data-base-path="'
        + html.escape("/" + base_path.strip("/") if base_path.strip("/") else "", quote=True)
        + '" data-search-index-url="'
        + html.escape(_site_url("/dataset/search-index.json", base_path=base_path), quote=True)
        + '"><h1 id="search-heading">전체 점검항목 검색</h1>'
        '<form id="criterion-search-form" class="search-form" data-search-form action="'
        + html.escape(_site_url("/search/", base_path=base_path), quote=True)
        + '"><label><span class="visually-hidden">검색어</span><input name="q" type="search" data-search-query '
        'aria-controls="search-results" aria-describedby="search-status" '
        'placeholder="코드, 제목, 본문, 설정값"></label>'
        '<button class="primary-button" type="submit">검색</button></form>'
        '<div class="filters"><label>분야<select form="criterion-search-form" name="domain" data-domain-filter><option value="">전체</option></select></label>'
        '<label>분류<select form="criterion-search-form" name="category" data-category-filter><option value="">전체</option></select></label>'
        '<label>중요도<select form="criterion-search-form" name="severity" data-severity-filter><option value="">전체</option><option value="high">상</option><option value="medium">중</option><option value="low">하</option></select></label>'
        '<label>대상<select form="criterion-search-form" name="target" data-target-filter><option value="">전체</option></select></label></div>'
        '<p id="search-status" role="status" aria-live="polite" aria-atomic="true" '
        "data-search-status>검색어와 필터를 입력하세요.</p>"
        '<ul id="search-results" class="search-results" data-search-results></ul>'
        + search_fallback
        + "</section></main>"
    )
    search_path = site_root / "search" / "index.html"
    search_path.parent.mkdir()
    search_path.write_text(
        _html_document(
            title="검색 · KISA CCE 가이드 2026",
            description="KISA CCE 점검항목 검색",
            body=search_body,
            base_path=base_path,
            canonical_url=_site_url("/search/", base_path=base_path),
            extra_scripts=("/assets/search.js",),
            current_navigation="search",
            domain_navigation=_render_header_domain_navigation(
                domains=domains,
                current_domain=None,
                current=False,
                base_path=base_path,
            ),
        ),
        encoding="utf-8",
    )
    generated_paths.append(search_path)

    not_found_body = (
        '<main id="main-content" class="page-shell page-shell--single"><section class="surface">'
        "<h1>페이지를 찾을 수 없습니다</h1><p>주소를 확인하거나 전체 검색을 이용해 주세요.</p>"
        f'<p><a href="{html.escape(_site_url("/search/", base_path=base_path), quote=True)}">전체 검색</a></p>'
        "</section></main>"
    )
    not_found_path = site_root / "404.html"
    not_found_path.write_text(
        _html_document(
            title="페이지를 찾을 수 없습니다",
            description="404",
            body=not_found_body,
            base_path=base_path,
            domain_navigation=_render_header_domain_navigation(
                domains=domains,
                current_domain=None,
                current=False,
                base_path=base_path,
            ),
        ),
        encoding="utf-8",
    )
    generated_paths.append(not_found_path)
    return generated_paths
