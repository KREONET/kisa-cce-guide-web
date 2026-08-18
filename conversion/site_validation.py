"""Validate generated static-site structure and link integrity."""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

from conversion.common import JsonValue, as_mapping, as_sequence, load_json


@dataclass(frozen=True)
class SiteValidationIssue:
    """One deterministic generated-site validation failure."""

    rule_identifier: str
    location: str
    message: str


@dataclass
class _PageFacts:
    """Collected semantic facts for one HTML page."""

    html_language: str | None = None
    h1_count: int = 0
    tags: list[str] = field(default_factory=list)
    identifiers: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    resources: list[str] = field(default_factory=list)
    skip_link_present: bool = False
    article_attributes: dict[str, str | None] = field(default_factory=dict)
    image_count: int = 0
    image_with_alternative_text_count: int = 0
    image_with_dimensions_count: int = 0
    table_count: int = 0
    table_caption_count: int = 0
    table_header_count: int = 0
    pre_depth: int = 0
    pre_code_count: int = 0


class _PageParser(HTMLParser):
    """Collect facts without executing generated JavaScript."""

    def __init__(self) -> None:
        """Initialize an empty fact record."""

        super().__init__()
        self.facts = _PageFacts()

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        """Collect one start tag and relevant attributes."""

        attributes = dict(attrs)
        self.facts.tags.append(tag)
        if tag == "html":
            self.facts.html_language = attributes.get("lang")
        if tag == "h1":
            self.facts.h1_count += 1
        identifier = attributes.get("id")
        if identifier is not None:
            self.facts.identifiers.append(identifier)
        href = attributes.get("href")
        if href is not None:
            self.facts.links.append(href)
            if href == "#main-content" and "skip-link" in (attributes.get("class") or ""):
                self.facts.skip_link_present = True
        source = attributes.get("src")
        if source is not None:
            self.facts.resources.append(source)
        if tag == "article" and "criterion" in (attributes.get("class") or ""):
            self.facts.article_attributes = {
                name: attributes.get(name)
                for name in (
                    "data-criterion-code",
                    "data-severity",
                    "data-content-model",
                    "data-source-document",
                )
            }
        if tag == "img":
            self.facts.image_count += 1
            if attributes.get("alt"):
                self.facts.image_with_alternative_text_count += 1
            if attributes.get("width") and attributes.get("height"):
                self.facts.image_with_dimensions_count += 1
        if tag == "table":
            self.facts.table_count += 1
        if tag == "caption":
            self.facts.table_caption_count += 1
        if tag == "th":
            self.facts.table_header_count += 1
        if tag == "pre":
            self.facts.pre_depth += 1
        if tag == "code" and self.facts.pre_depth:
            self.facts.pre_code_count += 1

    def handle_endtag(self, tag: str) -> None:
        """Track the end of a preformatted region."""

        if tag == "pre" and self.facts.pre_depth:
            self.facts.pre_depth -= 1


def _page_facts(path: Path) -> _PageFacts:
    """Parse one generated HTML page."""

    parser = _PageParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser.facts


def _resolved_site_path(
    site_root: Path,
    public_path: str,
    *,
    base_path: str,
) -> Path:
    """Resolve one root-hosted public path to a generated file."""

    normalized_base_path = "/" + base_path.strip("/") if base_path.strip("/") else ""
    relative_public_path = public_path
    if normalized_base_path and (
        public_path == normalized_base_path or public_path.startswith(normalized_base_path + "/")
    ):
        relative_public_path = public_path[len(normalized_base_path) :] or "/"
    if relative_public_path.endswith("/"):
        return site_root / relative_public_path.lstrip("/") / "index.html"
    return site_root / relative_public_path.lstrip("/")


def validate_site(
    *,
    site_root: Path,
    manifest: dict[str, JsonValue],
    expected_html_page_count: int,
    base_path: str = "",
) -> list[SiteValidationIssue]:
    """Validate semantic HTML, public resources, anchors, and search fixtures."""

    issues: list[SiteValidationIssue] = []
    html_paths = sorted(site_root.rglob("*.html"))
    if len(html_paths) != expected_html_page_count:
        issues.append(
            SiteValidationIssue(
                "site-html-count",
                "site",
                f"expected {expected_html_page_count} HTML pages, got {len(html_paths)}",
            )
        )
    facts_by_path = {path: _page_facts(path) for path in html_paths}
    for html_path, facts in facts_by_path.items():
        location = html_path.relative_to(site_root).as_posix()
        if facts.html_language != "ko":
            issues.append(SiteValidationIssue("site-language", location, "lang must be ko"))
        if facts.h1_count != 1:
            issues.append(
                SiteValidationIssue("site-heading", location, "page must contain exactly one H1")
            )
        if not facts.skip_link_present:
            issues.append(SiteValidationIssue("site-skip-link", location, "skip link is missing"))
        if not {"header", "nav", "main", "footer"} <= set(facts.tags):
            issues.append(
                SiteValidationIssue("site-landmarks", location, "required landmarks are missing")
            )
        if len(facts.identifiers) != len(set(facts.identifiers)):
            issues.append(SiteValidationIssue("site-anchor-unique", location, "duplicate ID"))
        if facts.image_count != facts.image_with_alternative_text_count:
            issues.append(
                SiteValidationIssue("site-image-alt", location, "image alternative text is missing")
            )
        if facts.image_count != facts.image_with_dimensions_count:
            issues.append(
                SiteValidationIssue("site-image-size", location, "image dimensions are missing")
            )
        if facts.table_count != facts.table_caption_count or (
            facts.table_count and facts.table_header_count == 0
        ):
            issues.append(
                SiteValidationIssue(
                    "site-table-accessibility",
                    location,
                    "table caption or header is missing",
                )
            )

        for reference in [*facts.links, *facts.resources]:
            parsed = urlsplit(reference)
            if parsed.scheme or parsed.netloc:
                continue
            if not parsed.path:
                if parsed.fragment and parsed.fragment not in facts.identifiers:
                    issues.append(
                        SiteValidationIssue(
                            "site-fragment",
                            location,
                            f"fragment does not resolve: {reference}",
                        )
                    )
                continue
            resolved_path = _resolved_site_path(
                site_root,
                parsed.path,
                base_path=base_path,
            )
            if not resolved_path.exists():
                issues.append(
                    SiteValidationIssue(
                        "site-link",
                        location,
                        f"internal reference does not resolve: {reference}",
                    )
                )
                continue
            if parsed.fragment and resolved_path.suffix == ".html":
                target_facts = facts_by_path.get(resolved_path) or _page_facts(resolved_path)
                if parsed.fragment not in target_facts.identifiers:
                    issues.append(
                        SiteValidationIssue(
                            "site-fragment",
                            location,
                            f"fragment does not resolve: {reference}",
                        )
                    )

    manifest_values = as_sequence(manifest["criteria"], location="manifest.criteria")
    for manifest_value in manifest_values:
        record = as_mapping(manifest_value, location="manifest.criteria[]")
        route = record.get("route")
        if not isinstance(route, str):
            continue
        detail_path = _resolved_site_path(site_root, route, base_path="")
        facts = facts_by_path.get(detail_path)
        if (
            facts is None
            or not facts.article_attributes
            or not all(facts.article_attributes.values())
        ):
            issues.append(
                SiteValidationIssue(
                    "site-criterion-attributes",
                    route,
                    "criterion article attributes are missing",
                )
            )

    search_path = site_root / "dataset" / "search-index.json"
    if search_path.is_file():
        search_index = load_json(search_path)
        search_values = as_sequence(search_index["records"], location="searchIndex.records")
        search_records = [
            as_mapping(value, location="searchIndex.records[]") for value in search_values
        ]
        records_by_code = {
            record["code"]: record
            for record in search_records
            if isinstance(record.get("code"), str)
        }
        u_01 = records_by_code.get("U-01")
        u_02 = records_by_code.get("U-02")
        u_01_exact_terms = (
            as_sequence(u_01.get("exactTerms"), location="U-01.exactTerms")
            if u_01 is not None
            else []
        )
        u_01_searchable_value = u_01.get("searchableText") if u_01 is not None else None
        u_02_searchable_value = u_02.get("searchableText") if u_02 is not None else None
        u_01_searchable_text = (
            u_01_searchable_value if isinstance(u_01_searchable_value, str) else ""
        )
        u_02_searchable_text = (
            u_02_searchable_value if isinstance(u_02_searchable_value, str) else ""
        )
        if (
            len(search_records) != len(manifest_values)
            or u_01 is None
            or u_02 is None
            or "/etc/ssh/sshd_config" not in u_01_exact_terms
            or "PermitRootLogin No" not in u_01_searchable_text
            or "비밀번호 관리정책 설정" not in u_02_searchable_text
        ):
            issues.append(
                SiteValidationIssue(
                    "site-search-fixtures",
                    "dataset/search-index.json",
                    "required code, Korean text, or exact literal fixture failed",
                )
            )
        for record in search_records:
            route = record.get("route")
            if not isinstance(route, str):
                continue
            detail_path = _resolved_site_path(site_root, route, base_path="")
            facts = facts_by_path.get(detail_path)
            if facts is None:
                continue
            for anchor_value in as_sequence(
                record.get("headingAnchors"),
                location="searchIndex.records[].headingAnchors",
            ):
                if isinstance(anchor_value, str) and anchor_value not in facts.identifiers:
                    issues.append(
                        SiteValidationIssue(
                            "site-search-anchor",
                            route,
                            f"search anchor does not resolve: {anchor_value}",
                        )
                    )
    else:
        issues.append(
            SiteValidationIssue(
                "site-search-index",
                "dataset/search-index.json",
                "public search index is missing",
            )
        )
    if (site_root / "source" / "kisa-cce-criteria-2026.pdf").exists():
        issues.append(
            SiteValidationIssue(
                "site-unapproved-source-copy",
                "source/kisa-cce-criteria-2026.pdf",
                "source PDF must not be copied into the site artifact before license approval",
            )
        )
    return issues
