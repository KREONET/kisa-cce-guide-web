"""Static-site generation and link-integrity tests."""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

import pytest

from conversion.build_content import build
from conversion.common import as_mapping, as_sequence, load_yaml, repository_root
from conversion.site_validation import validate_site

EXPECTED_CRITERION_COUNT = 382
EXPECTED_HTML_PAGE_COUNT = 469
EXPECTED_SOURCE_IMAGE_COUNT = 815


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


def _inspect(path: Path) -> PageInspector:
    """Parse one generated HTML page."""

    inspector = PageInspector()
    inspector.feed(path.read_text(encoding="utf-8"))
    return inspector


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
        assert any(identifier.endswith(".heading:1") for identifier in inspector.identifiers)
        assert any(
            identifier.endswith(".transcription:1") for identifier in inspector.identifiers
        ) or (relative_path == "unix/u-01/index.html")


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


def test_structured_tables_and_code_are_semantic(generated_site: Path) -> None:
    """Structured detail pages must retain table and code semantics."""

    inspector = _inspect(generated_site / "unix" / "u-02" / "index.html")
    assert {"table", "thead", "tbody", "th", "pre", "code", "button"} <= set(inspector.tags)


def test_extracted_source_images_are_published_without_source_pdf(
    generated_site: Path,
) -> None:
    """Source crops must resolve while the unapproved PDF remains excluded."""

    source_images = sorted((generated_site / "assets").rglob("*-source-region.png"))
    assert len(source_images) == EXPECTED_SOURCE_IMAGE_COUNT
    assert (generated_site / "assets" / "w-01" / "w-01-page-177-source-region.png").is_file()
    assert not (generated_site / "source" / "kisa-cce-criteria-2026.pdf").exists()
    inspector = _inspect(generated_site / "windows" / "w-01" / "index.html")
    assert "figure" in inspector.tags
    assert "img" in inspector.tags
