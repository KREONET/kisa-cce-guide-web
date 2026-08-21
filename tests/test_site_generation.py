"""Static-site generation and link-integrity tests."""

from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

import pytest

from conversion.build_content import build
from conversion.common import JsonValue, as_mapping, as_sequence, load_yaml, repository_root
from conversion.site_validation import validate_site

EXPECTED_CRITERION_COUNT = 382
EXPECTED_HTML_PAGE_COUNT = 469


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

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        """Collect element, identifier, link, and landmark information."""

        self.tags.append(tag)
        attribute_map = dict(attrs)
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


def _inspect(path: Path) -> PageInspector:
    """Parse one generated HTML page."""

    inspector = PageInspector()
    inspector.feed(path.read_text(encoding="utf-8"))
    return inspector


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
        assert attributes["data-code-content-type"] == block["codeContentType"]
        assert attributes["data-code-language"] == block["codeLanguage"]
        code_tag, code_attributes = inspector.elements_by_identifier[f"code-{block_reference}"]
        assert code_tag == "code"
        assert code_attributes["data-code-content-type"] == block["codeContentType"]
        assert code_attributes["data-code-language"] == block["codeLanguage"]
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


def test_detail_pages_expose_machine_attributes_and_block_ids(
    generated_site: Path,
) -> None:
    """Representative detail pages must expose metadata and stable anchors."""

    for relative_path in (
        "unix/u-01/index.html",
        "windows/w-01/index.html",
        "web-application/ci/index.html",
    ):
        inspector = _inspect(generated_site / relative_path)
        assert all(inspector.article_attributes.values())
        assert inspector.article_attributes["data-content-model"] in {
            "systemCriterion",
            "webApplicationCriterion",
        }
        assert any(identifier.endswith(".heading:1") for identifier in inspector.identifiers)
        assert not any(
            identifier.endswith(".transcription:1") for identifier in inspector.identifiers
        )


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


def test_subpath_build_prefixes_links() -> None:
    """A repository-subpath build must prefix public links without changing files."""

    with TemporaryDirectory() as directory:
        output_root = Path(directory)
        build(output_root=output_root, base_path="/kisa-cce-guide-web")
        inspector = _inspect(output_root / "site" / "index.html")
        assert "/kisa-cce-guide-web/search/" in inspector.links
        detail_inspector = _inspect(output_root / "site" / "unix" / "u-01" / "index.html")
        assert "/kisa-cce-guide-web/unix/" in detail_inspector.links
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


@pytest.mark.parametrize(
    ("domain_identifier", "slug"),
    [("unix", "u-02"), ("windows", "w-01")],
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
