"""Validate generated static-site structure and link integrity."""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

from conversion.common import JsonValue, as_mapping, as_sequence, load_json
from conversion.paths import SOURCE_DOCUMENT_PATH

_ARTICLE_ATTRIBUTE_NAMES = (
    "data-criterion-code",
    "data-severity",
    "data-content-model",
    "data-source-document",
)
_ARIA_ID_REFERENCE_ATTRIBUTES = ("aria-controls", "aria-describedby", "aria-labelledby")
_TABLE_HEADER_SCOPES = {"col", "colgroup", "row", "rowgroup"}
_SEARCH_SCHEMA_VERSION = 2
_SEARCH_STRING_FIELDS = (
    "code",
    "route",
    "title",
    "severityLevel",
    "severitySourceLabel",
    "domainIdentifier",
    "domainLabel",
    "categoryIdentifier",
    "categoryLabel",
    "sourceTargetText",
)
_SEARCH_SECTION_NAMES = {
    "inspection",
    "purpose",
    "threat",
    "judgment",
    "action",
    "impact",
    "guidance",
    "reference",
}
_SEARCH_STRING_LIST_FIELDS = (
    "targetIdentifiers",
    "targetLabels",
    "exactTerms",
)


@dataclass(frozen=True)
class SiteValidationIssue:
    """One deterministic generated-site validation failure."""

    rule_identifier: str
    location: str
    message: str


@dataclass
class _TableFacts:
    """Collected accessibility facts for one table."""

    caption_count: int = 0
    header_scopes: list[str | None] = field(default_factory=list)


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
    link_elements: list[dict[str, str | None]] = field(default_factory=list)
    aria_id_references: list[tuple[str, str | None]] = field(default_factory=list)
    article_attributes: list[dict[str, str | None]] = field(default_factory=list)
    image_count: int = 0
    image_with_alternative_text_count: int = 0
    image_with_dimensions_count: int = 0
    tables: list[_TableFacts] = field(default_factory=list)
    pre_code_counts: list[int] = field(default_factory=list)


class _PageParser(HTMLParser):
    """Collect facts without executing generated JavaScript."""

    def __init__(self) -> None:
        """Initialize an empty fact record."""

        super().__init__()
        self.facts = _PageFacts()
        self._table_stack: list[int] = []
        self._pre_stack: list[int] = []

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
            self.facts.link_elements.append(attributes)
            if href == "#main-content" and "skip-link" in (attributes.get("class") or ""):
                self.facts.skip_link_present = True
        source = attributes.get("src")
        if source is not None:
            self.facts.resources.append(source)
        for attribute_name in _ARIA_ID_REFERENCE_ATTRIBUTES:
            if attribute_name in attributes:
                self.facts.aria_id_references.append(
                    (attribute_name, attributes.get(attribute_name))
                )
        if tag == "article" and "criterion" in (attributes.get("class") or "").split():
            self.facts.article_attributes.append(
                {name: attributes.get(name) for name in _ARTICLE_ATTRIBUTE_NAMES}
            )
        if tag == "img":
            self.facts.image_count += 1
            if attributes.get("alt"):
                self.facts.image_with_alternative_text_count += 1
            if attributes.get("width") and attributes.get("height"):
                self.facts.image_with_dimensions_count += 1
        if tag == "table":
            self.facts.tables.append(_TableFacts())
            self._table_stack.append(len(self.facts.tables) - 1)
        elif tag == "caption" and self._table_stack:
            self.facts.tables[self._table_stack[-1]].caption_count += 1
        elif tag == "th" and self._table_stack:
            self.facts.tables[self._table_stack[-1]].header_scopes.append(attributes.get("scope"))
        if tag == "pre":
            self.facts.pre_code_counts.append(0)
            self._pre_stack.append(len(self.facts.pre_code_counts) - 1)
        elif tag == "code" and self._pre_stack:
            self.facts.pre_code_counts[self._pre_stack[-1]] += 1

    def handle_endtag(self, tag: str) -> None:
        """Track the end of a preformatted region."""

        if tag == "table" and self._table_stack:
            self._table_stack.pop()
        if tag == "pre" and self._pre_stack:
            self._pre_stack.pop()


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
    source_path: Path | None = None,
) -> Path:
    """Resolve one public path relative to its document or the site root."""

    normalized_base_path = "/" + base_path.strip("/") if base_path.strip("/") else ""
    relative_public_path = public_path
    parent_path = site_root
    if public_path.startswith("/"):
        if normalized_base_path and (
            public_path == normalized_base_path
            or public_path.startswith(normalized_base_path + "/")
        ):
            relative_public_path = public_path[len(normalized_base_path) :] or "/"
        is_directory_route = relative_public_path.endswith("/")
        relative_public_path = relative_public_path.lstrip("/")
    else:
        is_directory_route = relative_public_path.endswith("/")
        if source_path is not None:
            parent_path = source_path.parent
    if is_directory_route:
        return (parent_path / relative_public_path / "index.html").resolve()
    return (parent_path / relative_public_path).resolve()


def _site_url(public_path: str, *, base_path: str) -> str:
    """Return one root-hosted URL under an optional deployment base path."""

    normalized_base_path = "/" + base_path.strip("/") if base_path.strip("/") else ""
    normalized_public_path = "/" + public_path.lstrip("/")
    return normalized_base_path + normalized_public_path


def _has_search_record_schema(record: dict[str, JsonValue]) -> bool:
    """Return whether one public search record satisfies the browser contract."""

    valid = all(
        isinstance(record.get(name), str) and bool(record[name]) for name in _SEARCH_STRING_FIELDS
    )
    order = record.get("order")
    if not isinstance(order, int) or isinstance(order, bool) or order < 1:
        valid = False
    for name in _SEARCH_STRING_LIST_FIELDS:
        value = record.get(name)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            valid = False
            continue
        if name != "exactTerms" and not value:
            valid = False
        if name == "exactTerms" and len(value) != len(set(value)):
            valid = False
    search_sections = record.get("searchSections")
    if (
        not isinstance(search_sections, dict)
        or set(search_sections) != _SEARCH_SECTION_NAMES
        or not all(isinstance(value, str) for value in search_sections.values())
        or not all(
            search_sections.get(name)
            for name in ("inspection", "purpose", "judgment", "action", "guidance")
        )
    ):
        valid = False
    target_identifiers = record.get("targetIdentifiers")
    target_labels = record.get("targetLabels")
    if (
        not isinstance(target_identifiers, list)
        or not isinstance(target_labels, list)
        or len(target_identifiers) != len(target_labels)
    ):
        valid = False
    return valid


def validate_site(
    *,
    site_root: Path,
    manifest: dict[str, JsonValue],
    expected_html_page_count: int,
    base_path: str = "",
) -> list[SiteValidationIssue]:
    """Validate semantic HTML, public resources, anchors, and search fixtures."""

    site_root = site_root.resolve()
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
        if any(
            table.caption_count != 1
            or not table.header_scopes
            or any(scope not in _TABLE_HEADER_SCOPES for scope in table.header_scopes)
            for table in facts.tables
        ):
            issues.append(
                SiteValidationIssue(
                    "site-table-accessibility",
                    location,
                    "each table must have one caption and scoped headers",
                )
            )
        if any(code_count != 1 for code_count in facts.pre_code_counts):
            issues.append(
                SiteValidationIssue(
                    "site-pre-code",
                    location,
                    "each preformatted region must contain exactly one code element",
                )
            )
        identifier_set = set(facts.identifiers)
        for attribute_name, reference_value in facts.aria_id_references:
            reference_identifiers = reference_value.split() if reference_value else []
            if not reference_identifiers or any(
                reference_identifier not in identifier_set
                for reference_identifier in reference_identifiers
            ):
                issues.append(
                    SiteValidationIssue(
                        "site-aria-reference",
                        location,
                        f"{attribute_name} must resolve to identifiers in the same page",
                    )
                )

        for reference in [*facts.links, *facts.resources]:
            parsed = urlsplit(reference)
            if parsed.scheme or parsed.netloc:
                continue
            normalized_base_path = "/" + base_path.strip("/") if base_path.strip("/") else ""
            if (
                normalized_base_path
                and parsed.path.startswith("/")
                and parsed.path != normalized_base_path
                and not parsed.path.startswith(normalized_base_path + "/")
            ):
                issues.append(
                    SiteValidationIssue(
                        "site-base-path",
                        location,
                        f"absolute local reference omits deployment base path: {reference}",
                    )
                )
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
                source_path=html_path,
            )
            try:
                resolved_path.relative_to(site_root)
            except ValueError:
                issues.append(
                    SiteValidationIssue(
                        "site-link",
                        location,
                        f"internal reference escapes the site root: {reference}",
                    )
                )
                continue
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
        if facts is None:
            issues.append(
                SiteValidationIssue(
                    "site-criterion-route",
                    route,
                    "manifest criterion route is missing",
                )
            )
            continue

        domain_identifier = record.get("domainIdentifier")
        slug = record.get("slug")
        dataset_path = (
            site_root / "dataset" / "criteria" / domain_identifier / f"{slug}.json"
            if isinstance(domain_identifier, str) and isinstance(slug, str)
            else None
        )
        normalized = (
            load_json(dataset_path) if dataset_path is not None and dataset_path.is_file() else {}
        )
        provenance_value = normalized.get("provenance") if isinstance(normalized, dict) else None
        provenance = provenance_value if isinstance(provenance_value, dict) else {}
        expected_article_attributes = {
            "data-criterion-code": record.get("code"),
            "data-severity": record.get("severityLevel"),
            "data-content-model": record.get("contentModel"),
            "data-source-document": provenance.get("sourceDocumentIdentifier"),
        }
        if (
            len(facts.article_attributes) != 1
            or facts.article_attributes[0] != expected_article_attributes
        ):
            issues.append(
                SiteValidationIssue(
                    "site-criterion-attributes",
                    route,
                    "criterion article attributes do not match canonical metadata",
                )
            )

        if isinstance(domain_identifier, str) and isinstance(slug, str):
            expected_dataset_url = _site_url(
                f"/dataset/criteria/{domain_identifier}/{slug}.json",
                base_path=base_path,
            )
            alternate_links = [
                attributes
                for attributes in facts.link_elements
                if attributes.get("href") == expected_dataset_url
                and "alternate" in (attributes.get("rel") or "").split()
                and attributes.get("type") == "application/json"
            ]
            if not alternate_links:
                issues.append(
                    SiteValidationIssue(
                        "site-criterion-alternate",
                        route,
                        "criterion must expose an exact JSON alternate link",
                    )
                )

    search_path = site_root / "dataset" / "search-index.json"
    if search_path.is_file():
        search_index = load_json(search_path)
        if (
            search_index.get("schemaVersion") != _SEARCH_SCHEMA_VERSION
            or not isinstance(search_index.get("tokenizerVersion"), str)
            or not isinstance(search_index.get("caseFoldingVersion"), str)
            or not isinstance(search_index.get("canonicalCorpusChecksum"), str)
        ):
            issues.append(
                SiteValidationIssue(
                    "site-search-schema",
                    "dataset/search-index.json",
                    "search index metadata does not satisfy the public contract",
                )
            )
        search_values = search_index.get("records")
        if not isinstance(search_values, list):
            issues.append(
                SiteValidationIssue(
                    "site-search-schema",
                    "dataset/search-index.json",
                    "records must be an array",
                )
            )
            search_values = []
        search_records = [value for value in search_values if isinstance(value, dict)]
        if len(search_records) != len(search_values) or any(
            not _has_search_record_schema(record) for record in search_records
        ):
            issues.append(
                SiteValidationIssue(
                    "site-search-schema",
                    "dataset/search-index.json",
                    "search records do not satisfy the browser field contract",
                )
            )
        records_by_code = {
            record["code"]: record
            for record in search_records
            if isinstance(record.get("code"), str)
        }
        manifest_records = [
            as_mapping(value, location="manifest.criteria[]") for value in manifest_values
        ]
        manifest_codes = [record.get("code") for record in manifest_records]
        search_codes = [record.get("code") for record in search_records]
        valid_search_codes = [code for code in search_codes if isinstance(code, str)]
        manifest_by_code = {
            record["code"]: record
            for record in manifest_records
            if isinstance(record.get("code"), str)
        }
        search_record_mismatch = False
        for record_order, search_record in enumerate(search_records, start=1):
            code = search_record.get("code")
            manifest_record = manifest_by_code.get(code) if isinstance(code, str) else None
            if manifest_record is None:
                continue
            expected_search_values = {
                "order": record_order,
                "code": manifest_record.get("code"),
                "route": manifest_record.get("route"),
                "title": manifest_record.get("title"),
                "severityLevel": manifest_record.get("severityLevel"),
                "severitySourceLabel": manifest_record.get("severitySourceLabel"),
                "domainIdentifier": manifest_record.get("domainIdentifier"),
                "categoryIdentifier": manifest_record.get("categoryIdentifier"),
            }
            if any(
                search_record.get(name) != value for name, value in expected_search_values.items()
            ):
                search_record_mismatch = True
        if (
            len(valid_search_codes) != len(search_records)
            or len(valid_search_codes) != len(set(valid_search_codes))
            or search_codes != manifest_codes
            or search_record_mismatch
        ):
            issues.append(
                SiteValidationIssue(
                    "site-search-completeness",
                    "dataset/search-index.json",
                    "search records must uniquely match manifest records and order",
                )
            )
        u_01 = records_by_code.get("U-01")
        u_02 = records_by_code.get("U-02")
        u_01_exact_terms_value = u_01.get("exactTerms") if u_01 is not None else None
        u_01_exact_terms = (
            u_01_exact_terms_value if isinstance(u_01_exact_terms_value, list) else []
        )
        u_01_sections = u_01.get("searchSections") if u_01 is not None else None
        u_02_sections = u_02.get("searchSections") if u_02 is not None else None
        u_01_action = u_01_sections.get("action") if isinstance(u_01_sections, dict) else ""
        u_02_inspection = u_02_sections.get("inspection") if isinstance(u_02_sections, dict) else ""
        if (
            len(search_records) != len(manifest_values)
            or u_01 is None
            or u_02 is None
            or "/etc/ssh/sshd_config" not in u_01_exact_terms
            or "PermitRootLogin No" not in u_01_exact_terms
            or not isinstance(u_01_action, str)
            or "root 계정으로 접속할 수 없도록" not in u_01_action
            or not isinstance(u_02_inspection, str)
            or "비밀번호 관리 정책 설정 여부" not in u_02_inspection
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
                issues.append(
                    SiteValidationIssue(
                        "site-search-route",
                        route,
                        "search result route does not resolve",
                    )
                )
                continue
    else:
        issues.append(
            SiteValidationIssue(
                "site-search-index",
                "dataset/search-index.json",
                "public search index is missing",
            )
        )
    public_source_document_path = Path("source") / SOURCE_DOCUMENT_PATH.name
    if (site_root / public_source_document_path).exists():
        issues.append(
            SiteValidationIssue(
                "site-unapproved-source-copy",
                public_source_document_path.as_posix(),
                "source PDF must not be copied into the site artifact",
            )
        )
    return issues
