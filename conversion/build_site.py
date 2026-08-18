"""Build the dependency-free static website from normalized JSON."""

from __future__ import annotations

import html
import shutil
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

import rfc8785
from markdown_it import MarkdownIt

from conversion.common import JsonValue, as_mapping, as_sequence


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


def _html_document(
    *,
    title: str,
    description: str,
    body: str,
    base_path: str,
    extra_scripts: Sequence[str] = (),
) -> str:
    """Wrap one page in the shared accessible site shell."""

    script_tags = "\n".join(
        f'<script src="{html.escape(_site_url(script, base_path=base_path), quote=True)}" defer></script>'
        for script in ["/assets/site.js", *extra_scripts]
    )
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="{html.escape(description, quote=True)}">
  <meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'self'; base-uri 'self'">
  <title>{html.escape(title)}</title>
  <link rel="stylesheet" href="{html.escape(_site_url("/assets/styles.css", base_path=base_path), quote=True)}">
</head>
<body>
  <a class="skip-link" href="#main-content">본문으로 바로가기</a>
  <header class="site-header">
    <div class="site-header__inner">
      <a class="site-brand" href="{html.escape(_site_url("/", base_path=base_path), quote=True)}">KISA CCE 가이드 2026</a>
      <button class="nav-toggle" type="button" aria-expanded="false" aria-controls="site-navigation" data-navigation-toggle>메뉴</button>
      <nav id="site-navigation" class="site-nav" aria-label="주요 메뉴" data-site-navigation data-open="false">
        <a href="{html.escape(_site_url("/", base_path=base_path), quote=True)}">분야</a>
        <a href="{html.escape(_site_url("/search/", base_path=base_path), quote=True)}">검색</a>
        <a href="{html.escape(_site_url("/anomalies/", base_path=base_path), quote=True)}">원문 이상</a>
      </nav>
    </div>
  </header>
  {body}
  <footer class="site-footer">원문을 대체하지 않는 비공식 변환본 · KISA CCE 가이드 2026</footer>
  <div class="visually-hidden" aria-live="polite" data-copy-status></div>
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


def _render_sidebar(
    *,
    domains: Mapping[str, dict[str, JsonValue]],
    current_domain: str | None,
    base_path: str,
) -> str:
    """Render domain navigation."""

    items = []
    for domain_identifier, domain in sorted(
        domains.items(),
        key=lambda item: int(cast("int", item[1]["order"])),
    ):
        current = ' aria-current="page"' if domain_identifier == current_domain else ""
        label = _text(domain["label"], location="taxonomy.domain.label")
        route = _site_url(f"/{domain_identifier}/", base_path=base_path)
        items.append(
            f'<li><a href="{html.escape(route, quote=True)}"{current}>{html.escape(label)}</a></li>'
        )
    return (
        '<aside class="sidebar" aria-label="분야 탐색">'
        '<details class="sidebar-disclosure" open><summary>분야 탐색</summary>'
        '<p class="sidebar__title">분야</p><ul>' + "".join(items) + "</ul></details></aside>"
    )


def _block_identifier(block: Mapping[str, JsonValue]) -> str:
    """Return one normalized block reference."""

    return _text(block["blockReference"], location="block.blockReference")


def _render_table(
    block: Mapping[str, JsonValue],
    *,
    parser: MarkdownIt,
) -> str:
    """Render a typed accessible table."""

    identifier = _block_identifier(block)
    headers = as_sequence(block["tableHeaders"], location="block.tableHeaders")
    rows = as_sequence(block["tableRows"], location="block.tableRows")
    header_html = "".join(
        f'<th scope="col">{_inline_html(_text(value, location="table.header"), parser=parser)}</th>'
        for value in headers
    )
    row_html = []
    for row_value in rows:
        row = as_sequence(row_value, location="table.row")
        cells = "".join(
            f"<td>{_inline_html(_text(value, location='table.cell'), parser=parser)}</td>"
            for value in row
        )
        row_html.append(f"<tr>{cells}</tr>")
    label = f"원문 표 {_text(block['semanticRole'], location='block.semanticRole')}"
    return (
        f'<div class="table-scroll" id="{html.escape(identifier, quote=True)}" '
        f'role="region" aria-label="{html.escape(label, quote=True)}" tabindex="0">'
        f"<table><caption>{html.escape(label)}</caption><thead><tr>{header_html}</tr></thead>"
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
    transcription_class = " code-block--transcription" if content_type == "transcription" else ""
    return (
        f'<div class="code-block{transcription_class}" id="{html.escape(identifier, quote=True)}">'
        f'<button class="copy-button" type="button" data-copy-button="{html.escape(code_identifier, quote=True)}" '
        f'aria-label="{html.escape(content_type)} 복사">복사</button>'
        f'<pre tabindex="0" aria-label="{html.escape(content_type, quote=True)} 내용"><code '
        f'id="{html.escape(code_identifier, quote=True)}" class="language-{html.escape(language, quote=True)}">'
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
    return (
        f'<figure class="source-visual" id="{html.escape(identifier, quote=True)}">'
        f'<a href="{html.escape(asset_url, quote=True)}" aria-label="{html.escape(alternative_text, quote=True)} 원본 크기로 보기">'
        f'<img src="{html.escape(asset_url, quote=True)}" alt="{html.escape(alternative_text, quote=True)}" '
        f'width="{pixel_width}" height="{pixel_height}" '
        'loading="lazy" decoding="async"></a>'
        f"<figcaption>{html.escape(caption)} {review_status}</figcaption></figure>"
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
        content = _inline_html(
            _text(block["content"], location="block.content"),
            parser=parser,
        )
        child_values = children.get(identifier, [])
        child_html = render_sequence(child_values)
        return f'<li id="{html.escape(identifier, quote=True)}">{content}{child_html}</li>'

    def render_single(block: dict[str, JsonValue]) -> str:
        identifier = _block_identifier(block)
        block_type = _text(block["blockType"], location="block.blockType")
        content = _text(block["content"], location="block.content")
        if block_type == "heading":
            heading_level = int(cast("int", block["headingLevel"]))
            return (
                f'<h{heading_level} id="{html.escape(identifier, quote=True)}">'
                f"{_inline_html(content, parser=parser)}</h{heading_level}>"
            )
        if block_type == "paragraph":
            return (
                f'<p id="{html.escape(identifier, quote=True)}">'
                f"{_inline_html(content, parser=parser)}</p>"
            )
        if block_type == "codeBlock":
            return _render_code(block)
        if block_type == "table":
            return _render_table(block, parser=parser)
        if block_type == "image":
            return _render_image(block, base_path=base_path)
        if block_type == "listItem":
            return render_list_item(block)
        if block_type == "noteContent":
            return (
                f'<p id="{html.escape(identifier, quote=True)}">'
                f"{_inline_html(content, parser=parser)}</p>"
            )
        if block_type == "noteLabel":
            return (
                f'<span class="note__label" id="{html.escape(identifier, quote=True)}">'
                f"{_inline_html(content, parser=parser)}</span>"
            )
        return (
            f'<p id="{html.escape(identifier, quote=True)}">'
            f"{_inline_html(content, parser=parser)}</p>"
        )

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
                parts.append(
                    f"<{tag}>" + "".join(render_list_item(item) for item in grouped) + f"</{tag}>"
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
                parts.append(
                    '<aside class="note" aria-label="'
                    + html.escape(
                        _text(note_blocks[0]["content"], location="noteLabel.content"),
                        quote=True,
                    )
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
    heading_blocks = [
        as_mapping(block, location="normalized.blocks[]")
        for block in blocks
        if isinstance(block, dict) and block.get("blockType") == "heading"
    ]
    toc = ""
    if len(heading_blocks) >= 6:
        links = "".join(
            '<li><a href="#'
            + html.escape(_block_identifier(block), quote=True)
            + '">'
            + html.escape(_text(block["content"], location="block.content"))
            + "</a></li>"
            for block in heading_blocks
        )
        toc = (
            '<nav class="toc" aria-label="문서 목차"><strong>목차</strong><ul>'
            + links
            + "</ul></nav>"
        )
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
    article_attributes = (
        f'data-criterion-code="{html.escape(code, quote=True)}" '
        f'data-severity="{html.escape(severity_level, quote=True)}" '
        f'data-content-model="{html.escape(content_model, quote=True)}" '
        f'data-source-document="{html.escape(_text(provenance["sourceDocumentIdentifier"], location="provenance.sourceDocumentIdentifier"), quote=True)}"'
    )
    annotations = as_sequence(normalized["annotations"], location="normalized.annotations")
    annotation_html = ""
    if annotations:
        entries = []
        for annotation_value in annotations:
            annotation = as_mapping(annotation_value, location="normalized.annotations[]")
            target = _text(annotation["targetReference"], location="annotation.targetReference")
            target_link = (
                f'<a href="#{html.escape(target, quote=True)}">대상 블록</a>'
                if annotation.get("targetType") == "astNode"
                else "metadata"
            )
            entries.append(
                '<div class="annotation"><strong>'
                + html.escape(
                    _text(annotation["annotationType"], location="annotation.annotationType")
                )
                + "</strong><p>"
                + html.escape(_text(annotation["explanation"], location="annotation.explanation"))
                + "</p><p>"
                + target_link
                + "</p></div>"
            )
        annotation_html = (
            '<section class="annotations"><h2>원문 이상 및 확인 필요</h2>'
            + "".join(entries)
            + "</section>"
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
    sidebar = _render_sidebar(
        domains=domains,
        current_domain=domain_identifier,
        base_path=base_path,
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
    body = (
        '<main id="main-content" class="page-shell">'
        + sidebar
        + '<div class="content">'
        + breadcrumb
        + f'<article class="criterion" {article_attributes}>'
        + '<header class="criterion__header">'
        + f"<h1>{html.escape(code)} {html.escape(title)}</h1>"
        + '<div class="criterion-meta">'
        + f'<span class="badge badge--{html.escape(severity_level)}">중요도 {html.escape(severity_source)}</span>'
        + f'<span class="badge">{html.escape(domain_label)}</span>'
        + f'<span class="badge">{html.escape(category_label)}</span>'
        + f'<span class="badge badge--review">{html.escape(review_label)}</span>'
        + "</div>"
        + f"<p>대상: {html.escape(', '.join(target_labels))} · 원문 페이지: {first_page}-{last_page}</p>"
        + f'<a class="visually-hidden" rel="alternate" type="application/json" href="{html.escape(dataset_url, quote=True)}">JSON 데이터</a>'
        + "</header>"
        + toc
        + _render_blocks(blocks, base_path=base_path)
        + annotation_html
        + '<section class="provenance"><h2>원문 및 출처</h2>'
        + f'<p><a href="{html.escape(pdf_url, quote=True)}">KISA 원문 게시물 보기</a></p>'
        + f"<p>{html.escape(_text(source_document['title'], location='source.title'))} · {html.escape(_text(source_document['publisher'], location='source.publisher'))}</p>"
        + "</section></article>"
        + '<nav class="pager" aria-label="이전 및 다음 항목">'
        + "".join(pager_links)
        + "</nav></div></main>"
    )
    return _html_document(
        title=f"{code} {title} · KISA CCE 가이드 2026",
        description=f"{code} {title} 점검항목",
        body=body,
        base_path=base_path,
    )


def build_site(
    *,
    repository: Path,
    output_root: Path,
    manifest: dict[str, JsonValue],
    taxonomy: dict[str, JsonValue],
    source_registry: dict[str, JsonValue],
    source_annotations: dict[str, JsonValue],
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
    for asset_name in ("styles.css", "site.js", "search.js"):
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
        '<main id="main-content" class="page-shell page-shell--single"><section class="surface hero">'
        "<h1>KISA CCE 가이드 2026</h1>"
        "<p>382개 보안 점검항목을 분야별로 탐색하고, 코드·제목·본문·설정값으로 검색할 수 있는 비공식 웹 변환본입니다.</p>"
        '<form class="search-form" action="'
        + html.escape(_site_url("/search/", base_path=base_path), quote=True)
        + '"><label><span class="visually-hidden">검색어</span><input name="q" type="search" placeholder="U-01, PermitRootLogin, 비밀번호 정책"></label>'
        '<button class="primary-button" type="submit">검색</button></form>'
        '<div class="card-grid">' + "".join(domain_cards) + "</div></section></main>"
    )
    root_path = site_root / "index.html"
    root_path.write_text(
        _html_document(
            title="KISA CCE 가이드 2026",
            description="KISA CCE 2026 점검항목 검색 및 탐색",
            body=root_body,
            base_path=base_path,
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

    search_body = (
        '<main id="main-content" class="page-shell page-shell--single"><section class="surface" '
        'data-search-root data-base-path="'
        + html.escape("/" + base_path.strip("/") if base_path.strip("/") else "", quote=True)
        + '" data-search-index-url="'
        + html.escape(_site_url("/dataset/search-index.json", base_path=base_path), quote=True)
        + '"><h1>전체 점검항목 검색</h1>'
        '<label>검색어<input type="search" data-search-query placeholder="코드, 제목, 본문, 설정값"></label>'
        '<div class="filters"><label>분야<select data-domain-filter><option value="">전체</option></select></label>'
        '<label>분류<select data-category-filter><option value="">전체</option></select></label>'
        '<label>중요도<select data-severity-filter><option value="">전체</option><option value="high">상</option><option value="medium">중</option><option value="low">하</option></select></label>'
        '<label>대상<select data-target-filter><option value="">전체</option></select></label></div>'
        '<p aria-live="polite" data-search-status>검색 색인을 불러오는 중입니다.</p>'
        '<ul class="search-results" data-search-results></ul></section></main>'
    )
    search_path = site_root / "search" / "index.html"
    search_path.parent.mkdir()
    search_path.write_text(
        _html_document(
            title="검색 · KISA CCE 가이드 2026",
            description="KISA CCE 점검항목 검색",
            body=search_body,
            base_path=base_path,
            extra_scripts=("/assets/search.js",),
        ),
        encoding="utf-8",
    )
    generated_paths.append(search_path)

    routes_by_code = {
        _text(record["code"], location="manifest.code"): _text(
            record["route"],
            location="manifest.route",
        )
        for record in manifest_records
    }
    anomaly_entries: list[str] = []
    anomaly_keys: set[tuple[str, str, str]] = set()
    global_annotation_values = as_sequence(
        source_annotations["annotations"],
        location="sourceAnnotations.annotations",
    )
    for annotation_value in global_annotation_values:
        annotation = as_mapping(
            annotation_value,
            location="sourceAnnotations.annotations[]",
        )
        source_text = _text(annotation["sourceText"], location="annotation.sourceText")
        explanation = _text(annotation["explanation"], location="annotation.explanation")
        target_reference = _text(
            annotation["targetReference"],
            location="annotation.targetReference",
        )
        anomaly_keys.add((source_text, explanation, target_reference))
        route = routes_by_code.get(target_reference)
        target_html = (
            f'<a href="{html.escape(_site_url(route, base_path=base_path), quote=True)}"><strong>{html.escape(target_reference)}</strong></a>'
            if route is not None
            else f"<strong>{html.escape(target_reference)}</strong>"
        )
        anomaly_entries.append(
            '<li class="anomaly-record">'
            + target_html
            + f"<p>원문: {html.escape(source_text)}</p>"
            + f"<p>{html.escape(explanation)}</p>"
            + f"<p>PDF 페이지 {int(cast('int', annotation['physicalPage']))} · "
            + html.escape(_text(annotation["disposition"], location="annotation.disposition"))
            + " · "
            + html.escape(_text(annotation["reviewStatus"], location="annotation.reviewStatus"))
            + "</p></li>"
        )
    for normalized in normalized_documents:
        criterion = as_mapping(normalized["criterion"], location="normalized.criterion")
        for annotation_value in as_sequence(
            normalized["annotations"],
            location="normalized.annotations",
        ):
            annotation = as_mapping(annotation_value, location="normalized.annotations[]")
            source_text = _text(annotation["sourceText"], location="annotation.sourceText")
            explanation = _text(annotation["explanation"], location="annotation.explanation")
            code = _text(criterion["code"], location="criterion.code")
            anomaly_key = (source_text, explanation, code)
            if anomaly_key in anomaly_keys:
                continue
            anomaly_keys.add(anomaly_key)
            route = routes_by_code[code]
            source_location = as_mapping(
                annotation["sourceLocation"],
                location="annotation.sourceLocation",
            )
            anomaly_entries.append(
                '<li class="anomaly-record"><a href="'
                + html.escape(_site_url(route, base_path=base_path), quote=True)
                + '"><strong>'
                + html.escape(code)
                + "</strong></a>"
                + f"<p>원문: {html.escape(source_text)}</p>"
                + f"<p>{html.escape(explanation)}</p>"
                + f"<p>PDF 페이지 {int(cast('int', source_location['physicalPage']))} · "
                + html.escape(_text(annotation["disposition"], location="annotation.disposition"))
                + " · "
                + html.escape(_text(annotation["reviewStatus"], location="annotation.reviewStatus"))
                + "</p></li>"
            )
    anomaly_body = (
        '<main id="main-content" class="page-shell page-shell--single"><section class="surface">'
        "<h1>원문 이상 및 확인 필요</h1>"
        "<p>원문 내부의 코드, 중요도, 제목, 분류, 기술 표기 차이를 자동 수정하지 않고 검토 대기 상태로 공개합니다.</p>"
        '<ul class="anomaly-list">' + "".join(anomaly_entries) + "</ul></section></main>"
    )
    anomaly_path = site_root / "anomalies" / "index.html"
    anomaly_path.parent.mkdir()
    anomaly_path.write_text(
        _html_document(
            title="원문 이상 · KISA CCE 가이드 2026",
            description="원문 이상 및 검토 대기 항목",
            body=anomaly_body,
            base_path=base_path,
        ),
        encoding="utf-8",
    )
    generated_paths.append(anomaly_path)

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
        ),
        encoding="utf-8",
    )
    generated_paths.append(not_found_path)
    return generated_paths
