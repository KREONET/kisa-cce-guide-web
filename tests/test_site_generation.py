"""Static-site generation and link-integrity tests."""

from __future__ import annotations

import hashlib
import json
import shutil
from html.parser import HTMLParser
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

import pytest

from conversion.build_content import build
from conversion.build_site import (
    _TABLE_OF_CONTENTS_MINIMUM_HEADING_COUNT,
    _render_table_of_contents,
)
from conversion.common import JsonValue, as_mapping, as_sequence, load_yaml, repository_root
from conversion.site_validation import validate_site

EXPECTED_CRITERION_COUNT = 382
EXPECTED_HTML_PAGE_COUNT = 468


class PageInspector(HTMLParser):
    """Collect structural facts without executing site JavaScript."""

    def __init__(self) -> None:
        """Initialize collected structural facts."""

        super().__init__()
        self.html_language: str | None = None
        self.h1_count = 0
        self.identifiers: set[str] = set()
        self.links: list[str] = []
        self.tags: list[str] = []
        self.article_attributes: dict[str, str | None] = {}
        self.elements_by_identifier: dict[str, tuple[str, dict[str, str | None]]] = {}
        self.note_attributes: list[dict[str, str | None]] = []
        self.table_header_scopes: list[str | None] = []
        self.skip_link_present = False
        self.table_of_contents_list_depth = 0
        self.maximum_table_of_contents_list_depth = 0
        self.table_of_contents_link_depths: list[tuple[int, str | None, str | None]] = []
        self._inside_table_of_contents = False

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        """Collect element, identifier, link, and landmark information."""

        self.tags.append(tag)
        attribute_map = dict(attrs)
        self._track_table_of_contents_start(tag, attribute_map)
        if tag == "html":
            self.html_language = attribute_map.get("lang")
        if tag == "h1":
            self.h1_count += 1
        identifier = attribute_map.get("id")
        if identifier is not None:
            self.identifiers.add(identifier)
            self.elements_by_identifier[identifier] = (tag, attribute_map)
        link = attribute_map.get("href")
        if link is not None:
            self.links.append(link)
            if link == "#main-content" and "skip-link" in (attribute_map.get("class") or ""):
                self.skip_link_present = True
        if tag == "article" and "criterion" in (attribute_map.get("class") or ""):
            self.article_attributes = {
                key: attribute_map.get(key)
                for key in (
                    "data-criterion-code",
                    "data-severity",
                    "data-content-model",
                    "data-source-document",
                )
            }
        if tag == "aside" and attribute_map.get("role") == "note":
            self.note_attributes.append(attribute_map)
        if tag == "th":
            self.table_header_scopes.append(attribute_map.get("scope"))

    def _track_table_of_contents_start(
        self,
        tag: str,
        attribute_map: dict[str, str | None],
    ) -> None:
        """Collect nested table-of-contents depth and heading metadata."""

        if tag == "nav" and "toc" in (attribute_map.get("class") or "").split():
            self._inside_table_of_contents = True
        if self._inside_table_of_contents and tag == "ul":
            self.table_of_contents_list_depth += 1
            self.maximum_table_of_contents_list_depth = max(
                self.maximum_table_of_contents_list_depth,
                self.table_of_contents_list_depth,
            )
        if self._inside_table_of_contents and tag == "a":
            self.table_of_contents_link_depths.append(
                (
                    self.table_of_contents_list_depth,
                    attribute_map.get("data-toc-heading-level"),
                    attribute_map.get("data-toc-depth"),
                )
            )

    def handle_endtag(self, tag: str) -> None:
        """Track nested table-of-contents list boundaries."""

        if self._inside_table_of_contents and tag == "ul":
            self.table_of_contents_list_depth -= 1
        if self._inside_table_of_contents and tag == "nav":
            self._inside_table_of_contents = False


def _inspect(path: Path) -> PageInspector:
    """Parse one generated HTML page."""

    inspector = PageInspector()
    inspector.feed(path.read_text(encoding="utf-8"))
    return inspector


def _copy_site(generated_site: Path, destination: Path) -> Path:
    """Copy a generated site so a validation test can mutate it in isolation."""

    copied_site = destination / "site"
    shutil.copytree(generated_site, copied_site)
    return copied_site


def _issue_rule_identifiers(site_root: Path) -> set[str]:
    """Validate one mutated full site and return its failed rule identifiers."""

    manifest = load_yaml(repository_root() / "data/criteria-manifest.yaml")
    return {
        issue.rule_identifier
        for issue in validate_site(
            site_root=site_root,
            manifest=manifest,
            expected_html_page_count=EXPECTED_HTML_PAGE_COUNT,
        )
    }


def _source_attribute_values(block: dict[str, JsonValue]) -> tuple[str, str, str]:
    """Return ordered source-region, physical-page, and printed-page tokens."""

    source_spans = [
        as_mapping(value, location="block.sourceSpans[]")
        for value in as_sequence(block["sourceSpans"], location="block.sourceSpans")
    ]
    source_region_identifiers: list[str] = []
    source_physical_pages: list[str] = []
    source_printed_pages: list[str] = []
    for span in source_spans:
        region_identifier = span["pageRegionIdentifier"]
        physical_page = span["physicalPage"]
        printed_page = span["printedPage"]
        assert isinstance(region_identifier, str)
        assert isinstance(physical_page, int)
        assert isinstance(printed_page, str)
        source_region_identifiers.append(region_identifier)
        source_physical_pages.append(str(physical_page))
        source_printed_pages.append(printed_page)
    return (
        " ".join(dict.fromkeys(source_region_identifiers)),
        " ".join(dict.fromkeys(source_physical_pages)),
        " ".join(dict.fromkeys(source_printed_pages)),
    )


def _assert_highlight_contract(
    *,
    block: dict[str, JsonValue],
    pre_attributes: dict[str, str | None],
    code_attributes: dict[str, str | None],
) -> None:
    """Assert that syntax highlighting remains an optional explicit enhancement."""

    if block["codeContentType"] == "transcription" or block["codeLanguage"] in {
        "text",
        "plaintext",
    }:
        assert "data-highlight-language" not in pre_attributes
        assert "data-highlight-language" not in code_attributes
    else:
        assert pre_attributes["data-highlight-language"]
        assert code_attributes["data-highlight-language"]


def _assert_code_block_contract(
    *,
    inspector: PageInspector,
    block: dict[str, JsonValue],
    pre_attributes: dict[str, str | None],
) -> None:
    """Assert code metadata and optional highlighting attributes."""

    assert pre_attributes["data-code-content-type"] == block["codeContentType"]
    assert pre_attributes["data-code-language"] == block["codeLanguage"]
    code_tag, code_attributes = inspector.elements_by_identifier[f"code-{block['blockReference']}"]
    assert code_tag == "code"
    assert code_attributes["data-code-content-type"] == block["codeContentType"]
    assert code_attributes["data-code-language"] == block["codeLanguage"]
    _assert_highlight_contract(
        block=block,
        pre_attributes=pre_attributes,
        code_attributes=code_attributes,
    )


def _assert_block_contract(
    inspector: PageInspector,
    block: dict[str, JsonValue],
) -> None:
    """Assert one normalized block's semantic element and machine attributes."""

    block_reference = block["blockReference"]
    block_type = block["blockType"]
    semantic_role = block["semanticRole"]
    publication_disposition = block["publicationDisposition"]
    assert isinstance(block_reference, str)
    assert isinstance(block_type, str)
    assert isinstance(semantic_role, str)
    assert isinstance(publication_disposition, str)
    semantic_path = as_sequence(block["semanticPath"], location="block.semanticPath")
    semantic_path_values = [value for value in semantic_path if isinstance(value, str)]
    source_regions, source_physical_pages, source_printed_pages = _source_attribute_values(block)

    tag, attributes = inspector.elements_by_identifier[block_reference]
    expected_tag = {
        "paragraph": "p",
        "listItem": "li",
        "noteLabel": "p",
        "noteContent": "p",
        "codeBlock": "pre",
        "table": "table",
        "image": "figure",
    }.get(block_type)
    if block_type == "heading":
        heading_level = block["headingLevel"]
        assert isinstance(heading_level, int)
        expected_tag = f"h{heading_level}"
        assert attributes["data-heading-level"] == str(heading_level)
    assert tag == expected_tag
    assert attributes["data-block-reference"] == block_reference
    assert attributes["data-block-type"] == block_type
    assert attributes["data-semantic-role"] == semantic_role
    assert attributes["data-semantic-path"] == "/".join(semantic_path_values)
    assert attributes["data-publication-disposition"] == publication_disposition
    assert attributes["data-source-region-identifiers"] == source_regions
    assert attributes["data-source-physical-pages"] == source_physical_pages
    assert attributes["data-source-printed-pages"] == source_printed_pages

    parent_reference = block.get("parentBlockReference")
    if isinstance(parent_reference, str):
        assert attributes["data-parent-block-reference"] == parent_reference
    else:
        assert "data-parent-block-reference" not in attributes

    if block_type == "listItem":
        assert attributes["data-list-type"] == block["listType"]
        assert attributes["data-list-depth"] == str(block["listDepth"])
    if block_type == "codeBlock":
        _assert_code_block_contract(
            inspector=inspector,
            block=block,
            pre_attributes=attributes,
        )
    if block_type in {"table", "image"}:
        caption_tag, _ = inspector.elements_by_identifier[f"caption-{block_reference}"]
        assert caption_tag == ("caption" if block_type == "table" else "figcaption")
    if block_type == "image":
        assert attributes["data-asset-type"] == block["assetType"]
        assert attributes["data-rendering-profile"] == block["renderingProfileIdentifier"]
        assert attributes["data-alternative-text-status"] == block["alternativeTextStatus"]


@pytest.fixture(scope="module")
def generated_site(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build one complete site for structural tests."""

    output_root = tmp_path_factory.mktemp("site-build")
    build(output_root=output_root)
    return output_root / "site"


def test_every_manifest_route_and_dataset_exist(generated_site: Path) -> None:
    """Every criterion must have an HTML route and JSON alternate."""

    manifest = load_yaml(repository_root() / "data/criteria-manifest.yaml")
    records = as_sequence(manifest["criteria"], location="manifest.criteria")
    assert len(records) == EXPECTED_CRITERION_COUNT
    for record_value in records:
        record = as_mapping(record_value, location="manifest.criteria[]")
        route = record["route"]
        domain_identifier = record["domainIdentifier"]
        slug = record["slug"]
        assert isinstance(route, str)
        assert isinstance(domain_identifier, str)
        assert isinstance(slug, str)
        assert (generated_site / route.strip("/") / "index.html").is_file()
        assert (
            generated_site / "dataset" / "criteria" / domain_identifier / f"{slug}.json"
        ).is_file()


def test_all_html_pages_have_required_landmarks(generated_site: Path) -> None:
    """Every route must expose Korean language, one H1, and core landmarks."""

    html_paths = sorted(generated_site.rglob("*.html"))
    assert len(html_paths) == EXPECTED_HTML_PAGE_COUNT
    for html_path in html_paths:
        inspector = _inspect(html_path)
        assert inspector.html_language == "ko", html_path
        assert inspector.h1_count == 1, html_path
        assert inspector.skip_link_present, html_path
        assert {"header", "nav", "main", "footer"} <= set(inspector.tags), html_path


def test_source_anomaly_pages_and_ui_are_not_published(generated_site: Path) -> None:
    """Source-review records must not be rendered in public HTML."""

    assert not (generated_site / "anomalies").exists()
    for html_path in generated_site.rglob("*.html"):
        html_text = html_path.read_text(encoding="utf-8")
        assert "/anomalies/" not in html_text, html_path
        assert "원문 이상" not in html_text, html_path
        assert 'class="annotations"' not in html_text, html_path


def test_source_attribution_section_is_not_rendered(generated_site: Path) -> None:
    """Criterion pages must not render the redundant source-attribution section."""

    for dataset_path in (generated_site / "dataset" / "criteria").rglob("*.json"):
        domain_identifier = dataset_path.parent.name
        detail_path = generated_site / domain_identifier / dataset_path.stem / "index.html"
        detail_html = detail_path.read_text(encoding="utf-8")
        assert "원문 및 출처" not in detail_html, detail_path
        assert "KISA 원문 게시물 보기" not in detail_html, detail_path
        assert 'class="provenance"' not in detail_html, detail_path


def test_mobile_menu_contains_domain_exploration(generated_site: Path) -> None:
    """Detail pages must move domain exploration into the mobile primary menu."""

    detail_html = (generated_site / "unix" / "u-01" / "index.html").read_text(
        encoding="utf-8"
    )
    navigation_html = detail_html.partition('<nav id="site-navigation"')[2].partition(
        "</nav>"
    )[0]
    assert '<details class="site-nav__domains"><summary>분야 탐색</summary>' in navigation_html
    assert '<aside class="sidebar" aria-label="분야 탐색">' in detail_html

    taxonomy = load_yaml(repository_root() / "data/taxonomy.yaml")
    domain_values = as_sequence(taxonomy["domains"], location="taxonomy.domains")
    for domain_value in domain_values:
        domain = as_mapping(domain_value, location="taxonomy.domains[]")
        domain_identifier = domain["identifier"]
        assert isinstance(domain_identifier, str)
        assert f'href="/{domain_identifier}/"' in navigation_html

    stylesheet = (generated_site / "assets" / "styles.css").read_text(encoding="utf-8")
    base_styles = stylesheet.partition("@media (max-width: 1080px) {")[0]
    assert ".site-nav__domains { display: none; }" in base_styles
    mobile_styles = stylesheet.partition("@media (max-width: 768px) {")[2].partition(
        "@media (max-width: 480px) {"
    )[0]
    assert ".sidebar { display: none; }" in mobile_styles
    assert ".site-nav__domains { display: block;" in mobile_styles
    assert "max-height: calc(100vh - var(--header-height) - 16px);" in mobile_styles
    assert "max-height: calc(100dvh - var(--header-height) - 16px);" in mobile_styles


def test_table_of_contents_preserves_heading_hierarchy(generated_site: Path) -> None:
    """Every criterion TOC must reproduce its complete normalized heading tree."""

    normalized_root = generated_site.parent / "normalized"
    table_of_contents_page_count = 0
    for normalized_path in sorted(normalized_root.rglob("*.json")):
        normalized = as_mapping(
            json.loads(normalized_path.read_text(encoding="utf-8")),
            location=str(normalized_path),
        )
        heading_blocks = [
            as_mapping(block, location=f"{normalized_path}.blocks[]")
            for block in as_sequence(normalized["blocks"], location=f"{normalized_path}.blocks")
            if isinstance(block, dict) and block.get("blockType") == "heading"
        ]
        classification = as_mapping(
            normalized["classification"],
            location=f"{normalized_path}.classification",
        )
        criterion = as_mapping(
            normalized["criterion"],
            location=f"{normalized_path}.criterion",
        )
        domain_identifier = classification["domainIdentifier"]
        slug = criterion["slug"]
        assert isinstance(domain_identifier, str)
        assert isinstance(slug, str)
        inspector = _inspect(generated_site / domain_identifier / slug / "index.html")

        if len(heading_blocks) < _TABLE_OF_CONTENTS_MINIMUM_HEADING_COUNT:
            assert inspector.table_of_contents_link_depths == []
            continue

        table_of_contents_page_count += 1
        ancestor_levels: list[int] = []
        expected_links: list[tuple[int, str, str]] = []
        for block in heading_blocks:
            heading_level = block["headingLevel"]
            assert isinstance(heading_level, int)
            while ancestor_levels and heading_level <= ancestor_levels[-1]:
                ancestor_levels.pop()
            ancestor_levels.append(heading_level)
            depth = len(ancestor_levels)
            expected_links.append((depth, str(heading_level), str(depth)))

        assert inspector.table_of_contents_link_depths == expected_links, normalized_path
        assert inspector.maximum_table_of_contents_list_depth == max(
            depth for depth, _, _ in expected_links
        )

    assert table_of_contents_page_count == EXPECTED_CRITERION_COUNT


def test_table_of_contents_collapses_skipped_heading_levels() -> None:
    """Skipped levels must nest below the nearest lower heading without placeholders."""

    heading_levels = [2, 4, 5, 3, 2, 3]
    heading_blocks: list[dict[str, JsonValue]] = [
        {
            "blockReference": f"heading-{index}",
            "content": f"Heading {index}",
            "headingLevel": heading_level,
        }
        for index, heading_level in enumerate(heading_levels, start=1)
    ]
    inspector = PageInspector()
    inspector.feed(_render_table_of_contents(heading_blocks))

    assert inspector.table_of_contents_link_depths == [
        (1, "2", "1"),
        (2, "4", "2"),
        (3, "5", "3"),
        (2, "3", "2"),
        (1, "2", "1"),
        (2, "3", "2"),
    ]


def test_github_pages_marker_is_generated(generated_site: Path) -> None:
    """GitHub Pages must bypass Jekyll processing for generated static assets."""

    assert (generated_site / ".nojekyll").is_file()


def test_generated_site_passes_static_validation(generated_site: Path) -> None:
    """The complete site must pass semantic, link, image, and search checks."""

    manifest = load_yaml(repository_root() / "data/criteria-manifest.yaml")
    assert (
        validate_site(
            site_root=generated_site,
            manifest=manifest,
            expected_html_page_count=EXPECTED_HTML_PAGE_COUNT,
        )
        == []
    )
    assert not any(
        '<th scope="col"></th>' in path.read_text(encoding="utf-8")
        for path in generated_site.rglob("*.html")
    )


def test_search_page_keeps_a_script_independent_fallback(generated_site: Path) -> None:
    """Search must retain a visible criterion list when scripts or fetch fail."""

    search_html = (generated_site / "search" / "index.html").read_text(encoding="utf-8")
    assert "data-search-fallback" in search_html
    assert "<noscript>" not in search_html
    assert search_html.count('<li><a href="/') >= EXPECTED_CRITERION_COUNT


def test_highlight_assets_are_self_hosted_and_checksum_pinned(generated_site: Path) -> None:
    """The approved Highlight.js distribution must be copied without alteration."""

    expected_checksums = {
        "highlight.min.js": "8ab71eb09c51f501e5e25157d9cff100e46cc29bcbfc744d0b746d451fca7f53",
        "github-dark.min.css": "9f208d022102b1d0c7aebfecd8e42ca7997d5de636649d2b31ea63093d809019",
        "LICENSE": "6c081431591d9df696c82dc598fe1423765b8a299b200ed00b281afd0f64c490",
        "languages/apache.min.js": (
            "9dc53948535832b25d4eb23d40fef70510317398fdaf15f8a3fcc3ae7e0c490c"
        ),
        "languages/dos.min.js": "e184a6f9cead550b7b39b6114d17cafd08904557317622d7ea488aed01cf31ee",
        "languages/http.min.js": "b09b4afc1ce71f37f4434baccae5800e0812c6eb1db2cb8978fe9e4d668f45a6",
        "languages/nginx.min.js": (
            "8c53cc63ce0cf4ec0ad80b77273de23dec6974ab069d46d14d5c75febe880e1f"
        ),
        "languages/powershell.min.js": (
            "fc298b3e0db362e531e6d58988b7a78f83da19df6b5d74db75bc961b2bfbfd3d"
        ),
        "languages/properties.min.js": (
            "8a987022cc566fa5bfcd79058ec4ba010920d576fff809b92317295827402590"
        ),
    }
    vendor_directory = generated_site / "assets" / "vendor" / "highlight.js"
    for relative_path, expected_checksum in expected_checksums.items():
        assert hashlib.sha256((vendor_directory / relative_path).read_bytes()).hexdigest() == (
            expected_checksum
        )


def test_highlighting_is_explicit_and_progressively_enhanced(generated_site: Path) -> None:
    """Only eligible explicit languages may load the self-hosted highlighter."""

    criterion_html = (generated_site / "web-application" / "ci" / "index.html").read_text(
        encoding="utf-8"
    )
    core_script = "/assets/vendor/highlight.js/highlight.min.js"
    http_script = "/assets/vendor/highlight.js/languages/http.min.js"
    initializer_script = "/assets/highlight-init.js"
    assert core_script in criterion_html
    assert http_script in criterion_html
    assert initializer_script in criterion_html
    assert criterion_html.index(core_script) < criterion_html.index(http_script)
    assert criterion_html.index(http_script) < criterion_html.index(initializer_script)
    assert "/assets/vendor/highlight.js/github-dark.min.css" in criterion_html
    assert 'data-code-language="html" data-highlight-language="xml"' in criterion_html
    assert 'data-code-language="velocity" data-highlight-language="xml"' in criterion_html

    plaintext_html = (generated_site / "unix" / "u-01" / "index.html").read_text(encoding="utf-8")
    assert core_script not in plaintext_html
    assert initializer_script not in plaintext_html
    assert "data-highlight-language" not in plaintext_html


def test_every_code_block_follows_the_highlighting_policy(generated_site: Path) -> None:
    """Every generated code block must opt in or remain untouched by policy."""

    for dataset_path in sorted((generated_site / "dataset" / "criteria").rglob("*.json")):
        normalized = json.loads(dataset_path.read_text(encoding="utf-8"))
        code_blocks = [
            as_mapping(value, location="normalized.blocks[]")
            for value in as_sequence(normalized["blocks"], location="normalized.blocks")
            if isinstance(value, dict) and value.get("blockType") == "codeBlock"
        ]
        if not code_blocks:
            continue
        domain_identifier = dataset_path.parent.name
        detail_path = generated_site / domain_identifier / dataset_path.stem / "index.html"
        detail_html = detail_path.read_text(encoding="utf-8")
        inspector = _inspect(detail_path)
        highlighted_block_count = 0
        for block in code_blocks:
            block_reference = block["blockReference"]
            assert isinstance(block_reference, str)
            _, pre_attributes = inspector.elements_by_identifier[block_reference]
            _, code_attributes = inspector.elements_by_identifier[f"code-{block_reference}"]
            _assert_highlight_contract(
                block=block,
                pre_attributes=pre_attributes,
                code_attributes=code_attributes,
            )
            highlighted_block_count += int("data-highlight-language" in code_attributes)
        if highlighted_block_count:
            assert "/assets/vendor/highlight.js/highlight.min.js" in detail_html
            assert "/assets/highlight-init.js" in detail_html
        else:
            assert "/assets/vendor/highlight.js/highlight.min.js" not in detail_html
            assert "/assets/highlight-init.js" not in detail_html


def test_static_validation_rejects_page_contract_regressions(
    generated_site: Path,
    tmp_path: Path,
) -> None:
    """Static validation must reject inaccessible or stale detail-page contracts."""

    site_root = _copy_site(generated_site, tmp_path)
    u_01_path = site_root / "unix" / "u-01" / "index.html"
    u_01_html = u_01_path.read_text(encoding="utf-8")
    assert 'data-criterion-code="U-01"' in u_01_html
    assert 'rel="alternate" type="application/json"' in u_01_html
    assert "<code " in u_01_html
    u_01_html = u_01_html.replace(
        'data-criterion-code="U-01"',
        'data-criterion-code="U-02"',
        1,
    ).replace(
        'rel="alternate" type="application/json"',
        'rel="related" type="application/json"',
    )
    u_01_html = u_01_html.replace("<code ", "<span ", 1).replace(
        "</code>",
        "</span>",
        1,
    )
    u_01_html = u_01_html.replace(
        "</article>",
        "<table><caption>보조 표</caption><tbody><tr><td>값</td></tr></tbody></table></article>",
        1,
    )
    u_01_path.write_text(u_01_html, encoding="utf-8")

    u_02_path = site_root / "unix" / "u-02" / "index.html"
    u_02_html = u_02_path.read_text(encoding="utf-8")
    assert "/dataset/criteria/unix/u-02.json" in u_02_html
    u_02_path.write_text(
        u_02_html.replace(
            "/dataset/criteria/unix/u-02.json",
            "/dataset/criteria/unix/u-01.json",
        ),
        encoding="utf-8",
    )

    home_path = site_root / "index.html"
    home_html = home_path.read_text(encoding="utf-8")
    assert 'aria-controls="site-navigation"' in home_html
    home_path.write_text(
        home_html.replace(
            'aria-controls="site-navigation"',
            'aria-controls="missing-navigation"',
            1,
        ),
        encoding="utf-8",
    )
    (site_root / "unix" / "u-03" / "index.html").unlink()

    rule_identifiers = _issue_rule_identifiers(site_root)
    assert {
        "site-aria-reference",
        "site-criterion-alternate",
        "site-criterion-attributes",
        "site-criterion-route",
        "site-pre-code",
        "site-table-accessibility",
    } <= rule_identifiers


def test_static_validation_rejects_search_index_contract_regressions(
    generated_site: Path,
    tmp_path: Path,
) -> None:
    """Search validation must reject stale, duplicate, and malformed records."""

    site_root = _copy_site(generated_site, tmp_path)
    search_path = site_root / "dataset" / "search-index.json"
    search_index = json.loads(search_path.read_text(encoding="utf-8"))
    records = search_index["records"]
    records[2]["route"] = "/missing/"
    records[3]["code"] = records[2]["code"]
    records[4].pop("exactTerms")
    records[5]["targetLabels"] = records[5]["targetLabels"][:-1]
    search_path.write_text(
        json.dumps(search_index, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    rule_identifiers = _issue_rule_identifiers(site_root)
    assert {
        "site-search-completeness",
        "site-search-route",
        "site-search-schema",
    } <= rule_identifiers


def test_detail_pages_expose_machine_attributes_and_block_ids(
    generated_site: Path,
) -> None:
    """Representative detail pages must expose metadata and stable anchors."""

    for relative_path in (
        "unix/u-01/index.html",
        "windows/w-01/index.html",
        "web-application/ci/index.html",
    ):
        detail_path = generated_site / relative_path
        detail_html = detail_path.read_text(encoding="utf-8")
        inspector = _inspect(detail_path)
        assert all(inspector.article_attributes.values())
        assert inspector.article_attributes["data-content-model"] in {
            "systemCriterion",
            "webApplicationCriterion",
        }
        assert any(identifier.endswith(".heading:1") for identifier in inspector.identifiers)
        assert not any(
            identifier.endswith(".transcription:1") for identifier in inspector.identifiers
        )
        assert '<link rel="canonical" href="/' in detail_html
        assert '<link rel="alternate" type="application/json" href="/' in detail_html
        assert '<dl class="criterion-meta">' in detail_html
        structured_data_text = detail_html.partition('<script type="application/ld+json">')[
            2
        ].partition("</script>")[0]
        structured_data = json.loads(structured_data_text)
        assert structured_data["@type"] == "TechArticle"
        assert structured_data["identifier"] == inspector.article_attributes["data-criterion-code"]
        assert structured_data["mainEntityOfPage"] == structured_data["url"]
        assert "additionalProperty" not in structured_data
        assert structured_data["articleSection"]
        assert structured_data["keywords"]
        assert structured_data["pagination"]


def test_internal_links_resolve(generated_site: Path) -> None:
    """All generated root-hosting links must resolve to a file or block."""

    for html_path in sorted(generated_site.rglob("*.html")):
        inspector = _inspect(html_path)
        for link in inspector.links:
            parsed = urlsplit(link)
            if parsed.scheme or parsed.netloc:
                continue
            if not parsed.path:
                if parsed.fragment:
                    assert parsed.fragment in inspector.identifiers, (html_path, link)
                continue
            target_path = parsed.path
            if target_path.endswith("/"):
                resolved = generated_site / target_path.lstrip("/") / "index.html"
            else:
                resolved = generated_site / target_path.lstrip("/")
            assert resolved.exists(), (html_path, link)
            if parsed.fragment and resolved.suffix == ".html":
                target_inspector = _inspect(resolved)
                assert parsed.fragment in target_inspector.identifiers, (html_path, link)


def test_static_validation_resolves_relative_links_from_the_current_page(
    generated_site: Path,
    tmp_path: Path,
) -> None:
    """Relative links must resolve from the source page without escaping the site."""

    site_root = _copy_site(generated_site, tmp_path)
    detail_path = site_root / "unix" / "u-01" / "index.html"
    detail_html = detail_path.read_text(encoding="utf-8")
    detail_path.write_text(
        detail_html.replace("</article>", '<a href="../">분야</a></article>', 1),
        encoding="utf-8",
    )
    assert _issue_rule_identifiers(site_root) == set()

    root_path = site_root / "index.html"
    root_html = root_path.read_text(encoding="utf-8")
    root_path.unlink()
    assert "site-link" in _issue_rule_identifiers(site_root)
    root_path.write_text(root_html, encoding="utf-8")

    outside_path = tmp_path / "outside.html"
    outside_path.write_text("<h1>outside</h1>", encoding="utf-8")
    detail_path.write_text(
        detail_html.replace(
            "</article>",
            '<a href="../../../outside.html">외부 파일</a></article>',
            1,
        ),
        encoding="utf-8",
    )
    assert "site-link" in _issue_rule_identifiers(site_root)


def test_subpath_build_prefixes_links() -> None:
    """A repository-subpath build must prefix public links without changing files."""

    with TemporaryDirectory() as directory:
        output_root = Path(directory)
        build(output_root=output_root, base_path="/kisa-cce-guide-web")
        inspector = _inspect(output_root / "site" / "index.html")
        assert "/kisa-cce-guide-web/search/" in inspector.links
        detail_inspector = _inspect(output_root / "site" / "unix" / "u-01" / "index.html")
        assert "/kisa-cce-guide-web/unix/" in detail_inspector.links
        detail_html = (
            output_root / "site" / "unix" / "u-01" / "index.html"
        ).read_text(encoding="utf-8")
        mobile_navigation_html = detail_html.partition('<nav id="site-navigation"')[2].partition(
            "</nav>"
        )[0]
        assert 'href="/kisa-cce-guide-web/windows/"' in mobile_navigation_html
        manifest = load_yaml(repository_root() / "data/criteria-manifest.yaml")
        assert (
            validate_site(
                site_root=output_root / "site",
                manifest=manifest,
                expected_html_page_count=EXPECTED_HTML_PAGE_COUNT,
                base_path="/kisa-cce-guide-web",
            )
            == []
        )
        index_path = output_root / "site" / "index.html"
        index_html = index_path.read_text(encoding="utf-8")
        assert "/kisa-cce-guide-web/search/" in index_html
        index_path.write_text(
            index_html.replace("/kisa-cce-guide-web/search/", "/search/", 1),
            encoding="utf-8",
        )
        issues = validate_site(
            site_root=output_root / "site",
            manifest=manifest,
            expected_html_page_count=EXPECTED_HTML_PAGE_COUNT,
            base_path="/kisa-cce-guide-web",
        )
        assert "site-base-path" in {issue.rule_identifier for issue in issues}


@pytest.mark.parametrize(
    ("domain_identifier", "slug"),
    [("unix", "u-02"), ("windows", "w-01"), ("web-application", "ci")],
)
def test_typed_blocks_expose_semantic_elements_and_machine_attributes(
    generated_site: Path,
    domain_identifier: str,
    slug: str,
) -> None:
    """Structured blocks must retain semantic and provenance contracts."""

    inspector = _inspect(generated_site / domain_identifier / slug / "index.html")
    normalized = json.loads(
        (generated_site / "dataset" / "criteria" / domain_identifier / f"{slug}.json").read_text(
            encoding="utf-8"
        )
    )
    blocks = [
        as_mapping(value, location="normalized.blocks[]")
        for value in as_sequence(normalized["blocks"], location="normalized.blocks")
    ]
    assert {block["blockReference"] for block in blocks} <= inspector.identifiers
    for block in blocks:
        _assert_block_contract(inspector, block)

    if slug == "u-02":
        assert {"ol", "ul", "li", "aside", "table", "thead", "tbody", "th", "pre", "code"} <= set(
            inspector.tags
        )
        assert inspector.note_attributes
        assert all(attributes.get("aria-labelledby") for attributes in inspector.note_attributes)
        assert inspector.table_header_scopes
        assert set(inspector.table_header_scopes) == {"col"}
    else:
        assert {"ol", "li", "aside"} <= set(inspector.tags)
        assert inspector.note_attributes


def test_legacy_source_images_and_source_pdf_are_not_published(
    generated_site: Path,
) -> None:
    """A structured corpus must not publish obsolete source crops or the source PDF."""

    source_images = sorted((generated_site / "assets").rglob("*-source-region.png"))
    assert source_images == []
    assert not (generated_site / "source" / "kisa-cce-criteria-2026.pdf").exists()
    inspector = _inspect(generated_site / "windows" / "w-01" / "index.html")
    assert "figure" not in inspector.tags
    assert "img" not in inspector.tags
