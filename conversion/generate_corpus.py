"""Generate the complete extracted corpus from the authoritative inventory."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Protocol, cast

import pdfplumber
from ruamel.yaml import YAML

from conversion.common import (
    JsonValue,
    as_mapping,
    as_sequence,
    criterion_source_checksum,
    load_json,
    load_yaml,
    region_source_checksum,
    repository_root,
    sha256_file,
)
from conversion.paths import (
    CRITERION_ASSET_REFERENCE_DIRECTORY,
    SOURCE_DOCUMENT_PATH,
    canonical_asset_directory,
    criterion_directory,
)
from conversion.runtime_logging import add_logging_arguments, configure_runtime_logging

SOURCE_DOCUMENT_IDENTIFIER = "kisa-cce-criteria-2026"
SOURCE_DOCUMENT_CHECKSUM = "44fe393981b244147be6af7423d99dc15633c089fad0bcb296cbe2371dde812d"
STRUCTURED_SLUGS = frozenset({"u-01", "u-02"})
HEADER_BOTTOM = 0.10
FOOTER_TOP = 0.95
SOURCE_CROP_RESOLUTION = 96


class RasterImage(Protocol):
    """Required rendered image surface."""

    @property
    def size(self) -> tuple[int, int]:
        """Return pixel width and height."""


class PdfPageImage(Protocol):
    """Required pdfplumber page image surface."""

    original: RasterImage

    def save(
        self,
        destination: str | Path,
        *,
        format: str,
        quantize: bool,
        colors: int,
    ) -> None:
        """Save a deterministic PNG render."""


class PdfPage(Protocol):
    """Required pdfplumber page surface."""

    width: float
    height: float

    def extract_text_lines(
        self,
        *,
        strip: bool,
        return_chars: bool,
    ) -> list[dict[str, object]]:
        """Return positioned text lines."""

    def crop(self, bounding_box: tuple[float, float, float, float]) -> PdfPage:
        """Return a cropped page."""

    def extract_text(
        self,
        *,
        x_tolerance: int,
        y_tolerance: int,
    ) -> str | None:
        """Return text from the page or crop."""

    def to_image(
        self,
        *,
        resolution: int,
        antialias: bool,
    ) -> PdfPageImage:
        """Render the page or crop to a raster image."""


@dataclass(frozen=True)
class CriterionInventory:
    """Authoritative criterion metadata used for corpus generation."""

    order: int
    code: str
    slug: str
    title: str
    severity_level: str
    severity_source_label: str
    domain_identifier: str
    category_identifier: str
    source_start_page: int
    source_end_page: int
    route: str

    @classmethod
    def from_value(cls, value: JsonValue) -> CriterionInventory:
        """Create a typed record from the derived inventory JSON."""

        record = as_mapping(value, location="authoritativeInventory.criteria[]")
        required_values = {
            "order": record.get("order"),
            "code": record.get("code"),
            "slug": record.get("slug"),
            "title": record.get("title"),
            "severityLevel": record.get("severityLevel"),
            "severitySourceLabel": record.get("severitySourceLabel"),
            "domainIdentifier": record.get("domainIdentifier"),
            "categoryIdentifier": record.get("categoryIdentifier"),
            "sourceStartPhysicalPage": record.get("sourceStartPhysicalPage"),
            "sourceEndPhysicalPage": record.get("sourceEndPhysicalPage"),
            "route": record.get("route"),
        }
        if not isinstance(required_values["order"], int):
            msg = "criterion order must be an integer"
            raise TypeError(msg)
        if not isinstance(required_values["sourceStartPhysicalPage"], int) or not isinstance(
            required_values["sourceEndPhysicalPage"],
            int,
        ):
            msg = "criterion page bounds must be integers"
            raise TypeError(msg)
        string_fields = {
            name: field_value
            for name, field_value in required_values.items()
            if name not in {"order", "sourceStartPhysicalPage", "sourceEndPhysicalPage"}
        }
        if not all(isinstance(field_value, str) for field_value in string_fields.values()):
            msg = "criterion inventory contains a non-string field"
            raise TypeError(msg)
        return cls(
            order=required_values["order"],
            code=cast("str", required_values["code"]),
            slug=cast("str", required_values["slug"]),
            title=cast("str", required_values["title"]),
            severity_level=cast("str", required_values["severityLevel"]),
            severity_source_label=cast("str", required_values["severitySourceLabel"]),
            domain_identifier=cast("str", required_values["domainIdentifier"]),
            category_identifier=cast("str", required_values["categoryIdentifier"]),
            source_start_page=required_values["sourceStartPhysicalPage"],
            source_end_page=required_values["sourceEndPhysicalPage"],
            route=cast("str", required_values["route"]),
        )


@dataclass(frozen=True)
class VisualAsset:
    """One deterministic source-page crop linked to an extracted criterion."""

    physical_page: int
    markdown_path: str
    checksum_value: str
    pixel_width: int
    pixel_height: int
    source_crop: tuple[float, float, float, float]


def _yaml_text(value: dict[str, JsonValue]) -> str:
    """Serialize canonical YAML without a document directive."""

    output = StringIO()
    writer = YAML()
    writer.default_flow_style = False
    writer.allow_unicode = True
    # Long scalar lines avoid YAML's space-preserving wrapped lines, which otherwise
    # introduce trailing whitespace into canonical source files.
    writer.width = 4096
    writer.indent(mapping=2, sequence=4, offset=2)
    writer.dump(value, output)
    return output.getvalue()


def _write_yaml(path: Path, value: dict[str, JsonValue]) -> None:
    """Write deterministic human-readable YAML."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_yaml_text(value), encoding="utf-8")


def _line_text(line: dict[str, object]) -> str:
    """Return one positioned line's text."""

    value = line.get("text")
    return value.strip() if isinstance(value, str) else ""


def _line_top(line: dict[str, object]) -> float | None:
    """Return one positioned line's top coordinate."""

    value = line.get("top")
    return float(value) if isinstance(value, int | float) else None


def _criterion_region_top(page: PdfPage, *, first_page: bool) -> float:
    """Locate the first meaningful criterion line below repeated headers."""

    if not first_page:
        return page.height * HEADER_BOTTOM
    for line in page.extract_text_lines(strip=True, return_chars=False)[:24]:
        if _line_text(line) == "개요":
            top = _line_top(line)
            if top is not None:
                return max(page.height * HEADER_BOTTOM, top - 4)
    return page.height * HEADER_BOTTOM


def _transcript(
    page: PdfPage,
    *,
    first_page: bool,
    physical_page: int,
) -> tuple[str, list[float]]:
    """Extract a criterion page transcript and normalized content region."""

    top = _criterion_region_top(page, first_page=first_page)
    bottom = page.height * FOOTER_TOP
    cropped_page = page.crop((page.width * 0.05, top, page.width * 0.95, bottom))
    text = cropped_page.extract_text(x_tolerance=2, y_tolerance=3) or ""
    normalized = unicodedata.normalize("NFC", text.replace("\u00a0", " ").strip())
    transcript_lines = normalized.splitlines()
    if transcript_lines and transcript_lines[-1].strip() == str(physical_page):
        transcript_lines.pop()
    normalized = "\n".join(transcript_lines).rstrip()
    bounding_box = [
        0.05,
        round(top / page.height, 4),
        0.95,
        FOOTER_TOP,
    ]
    return normalized, bounding_box


def _render_source_crop(
    page: PdfPage,
    *,
    criterion: CriterionInventory,
    physical_page: int,
    bounding_box: list[float],
    repository: Path,
) -> VisualAsset:
    """Render one criterion region as source-faithful visual evidence."""

    source_crop = tuple(bounding_box)
    if len(source_crop) != 4:
        msg = f"invalid source crop for {criterion.slug} page {physical_page}"
        raise ValueError(msg)
    x_minimum, y_minimum, x_maximum, y_maximum = source_crop
    cropped_page = page.crop(
        (
            page.width * x_minimum,
            page.height * y_minimum,
            page.width * x_maximum,
            page.height * y_maximum,
        )
    )
    filename = f"{criterion.slug}-page-{physical_page}-source-region.png"
    asset_directory = canonical_asset_directory(repository, criterion.slug)
    asset_directory.mkdir(parents=True, exist_ok=True)
    asset_path = asset_directory / filename
    page_image = cropped_page.to_image(
        resolution=SOURCE_CROP_RESOLUTION,
        antialias=True,
    )
    page_image.save(
        asset_path,
        format="PNG",
        quantize=True,
        colors=256,
    )
    pixel_width, pixel_height = page_image.original.size
    return VisualAsset(
        physical_page=physical_page,
        markdown_path=(CRITERION_ASSET_REFERENCE_DIRECTORY / criterion.slug / filename).as_posix(),
        checksum_value=sha256_file(asset_path),
        pixel_width=pixel_width,
        pixel_height=pixel_height,
        source_crop=(x_minimum, y_minimum, x_maximum, y_maximum),
    )


def _fence_for_text(text: str) -> str:
    """Choose a tilde fence longer than every source tilde run."""

    maximum_run = max((len(match.group()) for match in re.finditer(r"~+", text)), default=0)
    return "~" * max(3, maximum_run + 1)


def _anomaly_values_for_code(
    code: str,
    anomalies: list[JsonValue],
) -> list[dict[str, JsonValue]]:
    """Return inventory anomalies that affect one criterion code."""

    results: list[dict[str, JsonValue]] = []
    for anomaly_value in anomalies:
        anomaly = as_mapping(anomaly_value, location="inventoryAnomalies.anomalies[]")
        affected_codes = anomaly.get("affectedCodes")
        direct_match = anomaly.get("code") == code
        grouped_match = isinstance(affected_codes, list) and code in affected_codes
        if direct_match or grouped_match:
            results.append(anomaly)
    return results


def _annotation_source_text(anomaly: dict[str, JsonValue]) -> str:
    """Select a source-preserving value from a derived anomaly record."""

    for field_name in (
        "detailHeaderCode",
        "detailHeaderSeveritySourceLabel",
        "detailHeaderCategorySourceLabel",
        "detailHeaderTitle",
        "summaryTitle",
        "detail",
    ):
        value = anomaly.get(field_name)
        if isinstance(value, str) and value:
            return value
    return json.dumps(anomaly, ensure_ascii=False, sort_keys=True)


def _criterion_annotations(
    criterion: CriterionInventory,
    anomalies: list[JsonValue],
) -> list[JsonValue]:
    """Convert inventory conflicts into pending criterion annotations."""

    annotations: list[JsonValue] = []
    for annotation_number, anomaly in enumerate(
        _anomaly_values_for_code(criterion.code, anomalies),
        start=1,
    ):
        anomaly_type = anomaly.get("anomalyType")
        target_reference = "/criterion"
        if anomaly_type == "detailHeaderCodeMismatch":
            target_reference = "/criterion/code"
        elif anomaly_type == "detailHeaderSeverityMismatch":
            target_reference = "/criterion/severity/sourceLabel"
        elif anomaly_type == "detailHeaderCategoryMismatch":
            target_reference = "/classification/categoryIdentifier"
        elif anomaly_type == "detailHeaderTitleMismatch":
            target_reference = "/criterion/title"
        physical_page_value = anomaly.get("physicalPage")
        physical_page = (
            physical_page_value
            if isinstance(physical_page_value, int)
            else criterion.source_start_page
        )
        evidence = (
            anomaly.get("resolution")
            if isinstance(anomaly.get("resolution"), str)
            else "장별 항목표와 상세 머리글의 원문 값을 대조했다."
        )
        annotations.append(
            {
                "annotationIdentifier": (f"{criterion.slug}-inventory-{annotation_number:03d}"),
                "annotationType": "sourceInconsistency",
                "targetType": "metadata",
                "targetReference": target_reference,
                "sourceLocation": {
                    "physicalPage": physical_page,
                    "printedPage": str(physical_page),
                    "pageRegionIdentifier": f"p{physical_page}-{criterion.slug}",
                },
                "sourceText": _annotation_source_text(anomaly),
                "explanation": json.dumps(anomaly, ensure_ascii=False, sort_keys=True),
                "disposition": "unresolved",
                "reviewStatus": "pending",
                "verificationEvidence": [evidence],
                "reviewedBy": None,
                "reviewedAt": None,
                "approvedBy": None,
                "approvedAt": None,
            }
        )
    return annotations


def _criterion_metadata(
    criterion: CriterionInventory,
    annotations: list[JsonValue],
) -> dict[str, JsonValue]:
    """Create extractedCriterion front matter."""

    return {
        "schemaVersion": 1,
        "contentModel": "extractedCriterion",
        "contentModelVersion": 1,
        "criterion": {
            "code": criterion.code,
            "slug": criterion.slug,
            "title": criterion.title,
            "severity": {
                "level": criterion.severity_level,
                "sourceLabel": criterion.severity_source_label,
            },
        },
        "classification": {
            "domainIdentifier": criterion.domain_identifier,
            "categoryIdentifier": criterion.category_identifier,
        },
        "targetScope": "nonExhaustive",
        "targetIdentifiers": ["unspecified"],
        "sourceTargetText": "자동 전사본에서 확인 필요",
        "provenance": {
            "sourceDocumentIdentifier": SOURCE_DOCUMENT_IDENTIFIER,
            "sourcePageRanges": [
                {
                    "physicalPageStart": criterion.source_start_page,
                    "physicalPageEnd": criterion.source_end_page,
                    "printedPageStart": str(criterion.source_start_page),
                    "printedPageEnd": str(criterion.source_end_page),
                }
            ],
        },
        "sourceAnnotations": annotations,
    }


def _criterion_markdown(
    criterion: CriterionInventory,
    metadata: dict[str, JsonValue],
    transcripts: dict[int, str],
    visual_assets: dict[int, VisualAsset],
) -> str:
    """Create readable extractedCriterion Markdown."""

    body_parts = ["## 원문 전사", ""]
    for physical_page in range(
        criterion.source_start_page,
        criterion.source_end_page + 1,
    ):
        text = transcripts[physical_page]
        fence = _fence_for_text(text)
        body_parts.extend(
            [
                f"### PDF 페이지 {physical_page}",
                "",
                f"{fence}text transcription",
                text,
                fence,
                "",
            ]
        )
        visual_asset = visual_assets[physical_page]
        alternative_text = f"PDF 페이지 {physical_page}의 원문 점검항목 영역"
        body_parts.extend(
            [
                f"![{alternative_text}]({visual_asset.markdown_path})",
                "",
            ]
        )
    return f"---\n{_yaml_text(metadata)}---\n\n" + "\n".join(body_parts).rstrip() + "\n"


def _criterion_provenance(
    criterion: CriterionInventory,
    visual_assets: dict[int, VisualAsset],
) -> dict[str, JsonValue]:
    """Create complete block provenance for an extracted criterion."""

    records: list[JsonValue] = [
        {
            "blockReference": f"{criterion.slug}:sourceTranscription.heading:1",
            "publicationDisposition": "derived",
            "derivationType": "structuralHeading",
            "sourceSpans": [
                {
                    "physicalPage": criterion.source_start_page,
                    "printedPage": str(criterion.source_start_page),
                    "pageRegionIdentifier": (f"p{criterion.source_start_page}-{criterion.slug}"),
                }
            ],
        }
    ]
    for physical_page in range(
        criterion.source_start_page,
        criterion.source_end_page + 1,
    ):
        page_path = f"sourceTranscription.sourcePage{physical_page}"
        source_span: JsonValue = {
            "physicalPage": physical_page,
            "printedPage": str(physical_page),
            "pageRegionIdentifier": f"p{physical_page}-{criterion.slug}",
        }
        records.extend(
            [
                {
                    "blockReference": f"{criterion.slug}:{page_path}.heading:1",
                    "publicationDisposition": "derived",
                    "derivationType": "sourcePageHeading",
                    "sourceSpans": [source_span],
                },
                {
                    "blockReference": f"{criterion.slug}:{page_path}.transcription:1",
                    "publicationDisposition": "published",
                    "sourceSpans": [dict(source_span)],
                },
                {
                    "blockReference": f"{criterion.slug}:{page_path}.image:1",
                    "publicationDisposition": "derived",
                    "derivationType": "pdfPageSourceCrop",
                    "sourceSpans": [
                        {
                            **dict(source_span),
                            "sourceBoundingBox": list(visual_assets[physical_page].source_crop),
                        }
                    ],
                },
            ]
        )
    assets: list[JsonValue] = []
    for physical_page in range(
        criterion.source_start_page,
        criterion.source_end_page + 1,
    ):
        visual_asset = visual_assets[physical_page]
        alternative_text = f"PDF 페이지 {physical_page}의 원문 점검항목 영역"
        assets.append(
            {
                "path": visual_asset.markdown_path,
                "assetType": "sourcePageCrop",
                "renderingProfileIdentifier": "pdfium-png-indexed-96-v1",
                "checksumAlgorithm": "sha256",
                "checksumValue": visual_asset.checksum_value,
                "alternativeText": alternative_text,
                "alternativeTextStatus": "verificationRequired",
                "caption": f"PDF 페이지 {physical_page} 원문 점검항목 영역",
                "originalPixelDimensions": [
                    visual_asset.pixel_width,
                    visual_asset.pixel_height,
                ],
                "outputPixelDimensions": [
                    visual_asset.pixel_width,
                    visual_asset.pixel_height,
                ],
                "sourceCrop": list(visual_asset.source_crop),
                "sourceSpans": [
                    {
                        "physicalPage": physical_page,
                        "printedPage": str(physical_page),
                        "pageRegionIdentifier": f"p{physical_page}-{criterion.slug}",
                        "sourceBoundingBox": list(visual_asset.source_crop),
                    }
                ],
            }
        )
    return {
        "schemaVersion": 1,
        "criterionSlug": criterion.slug,
        "sourceDocumentIdentifier": SOURCE_DOCUMENT_IDENTIFIER,
        "blockProvenance": records,
        "assets": assets,
    }


def _manifest_record(
    criterion: CriterionInventory,
    *,
    structured: bool,
) -> dict[str, JsonValue]:
    """Create one canonical manifest record."""

    return {
        "code": criterion.code,
        "slug": criterion.slug,
        "title": criterion.title,
        "severityLevel": criterion.severity_level,
        "severitySourceLabel": criterion.severity_source_label,
        "domainIdentifier": criterion.domain_identifier,
        "categoryIdentifier": criterion.category_identifier,
        "contentModel": "systemCriterion" if structured else "extractedCriterion",
        "contentModelVersion": 1,
        "sourceStartRegionIdentifier": (f"p{criterion.source_start_page}-{criterion.slug}"),
        "sourceEndRegionIdentifier": f"p{criterion.source_end_page}-{criterion.slug}",
        "route": criterion.route,
        "technicalLiteralInventoryMode": (
            "extractedFromTypedAst" if structured else "sourceTranscriptSearchableText"
        ),
    }


def _page_region(
    criterion: CriterionInventory,
    *,
    physical_page: int,
    bounding_box: list[float],
) -> dict[str, JsonValue]:
    """Create one criterion-owned page region."""

    return {
        "pageRegionIdentifier": f"p{physical_page}-{criterion.slug}",
        "physicalPage": physical_page,
        "printedPage": str(physical_page),
        "boundingBox": cast("JsonValue", bounding_box),
        "role": "criterion",
        "ownerType": "criterion",
        "ownerIdentifier": criterion.slug,
        "publicationDisposition": "published",
    }


def _excluded_header_region(physical_page: int) -> dict[str, JsonValue]:
    """Create one repeated-header exclusion region."""

    return {
        "pageRegionIdentifier": f"p{physical_page}-header",
        "physicalPage": physical_page,
        "printedPage": str(physical_page),
        "boundingBox": [0.0, 0.0, 1.0, HEADER_BOTTOM],
        "role": "excludedDecoration",
        "ownerType": "document",
        "ownerIdentifier": SOURCE_DOCUMENT_IDENTIFIER,
        "publicationDisposition": "excluded",
        "exclusionReason": "반복 문서 머리말 또는 기관 표기로 웹 본문에서 제외",
    }


def _excluded_footer_region(physical_page: int) -> dict[str, JsonValue]:
    """Create one repeated-page-number exclusion region."""

    return {
        "pageRegionIdentifier": f"p{physical_page}-footer",
        "physicalPage": physical_page,
        "printedPage": str(physical_page),
        "boundingBox": [0.0, FOOTER_TOP, 1.0, 1.0],
        "role": "navigation",
        "ownerType": "navigation",
        "ownerIdentifier": "printed-page-number",
        "publicationDisposition": "excluded",
        "exclusionReason": "반복 인쇄 페이지 번호로 웹 본문에서 제외",
    }


def _noncriterion_region(physical_page: int) -> dict[str, JsonValue]:
    """Classify one page outside criterion content ranges."""

    if physical_page == 1:
        role = "frontMatter"
        exclusion_reason = "원본 표지로 초기 점검항목 웹 변환 범위에서 제외"
    elif physical_page == 873:
        role = "backMatter"
        exclusion_reason = "원본 뒤표지로 초기 점검항목 웹 변환 범위에서 제외"
    elif physical_page == 2:
        role = "frontMatter"
        exclusion_reason = "발간 유의사항은 초기 점검항목 웹 변환 범위에서 제외"
    else:
        role = "navigation"
        exclusion_reason = "목차, 장 표지 또는 요약표로 초기 점검항목 웹 변환 범위에서 제외"
    region: dict[str, JsonValue] = {
        "pageRegionIdentifier": f"p{physical_page}-source",
        "physicalPage": physical_page,
        "printedPage": str(physical_page),
        "boundingBox": [0.0, 0.0, 1.0, 1.0],
        "role": role,
        "ownerType": "document",
        "ownerIdentifier": SOURCE_DOCUMENT_IDENTIFIER,
        "publicationDisposition": "excluded",
        "exclusionReason": exclusion_reason,
    }
    return region


def _review_record(
    *,
    subject_type: str,
    subject_identifier: str,
    subject_source_checksum: str,
    source_anomaly_count: int,
    workflow_status: str,
    visual_evidence_identifiers: list[str],
) -> dict[str, JsonValue]:
    """Create one unreviewed criterion or page-region record."""

    return {
        "subjectType": subject_type,
        "subjectIdentifier": subject_identifier,
        "subjectSourceChecksum": subject_source_checksum,
        "sourceDocumentIdentifier": SOURCE_DOCUMENT_IDENTIFIER,
        "sourceDocumentChecksum": SOURCE_DOCUMENT_CHECKSUM,
        "transcriptionStatus": "verificationRequired",
        "workflowStatus": workflow_status,
        "sourceAnomalyStatus": ("reviewRequired" if source_anomaly_count else "none"),
        "reviewers": [],
        "reviewedAt": None,
        "automatedValidationResult": "notRun",
        "unresolvedConversionErrorCount": 0,
        "unresolvedSourceAnomalyCount": source_anomaly_count,
        "validationReportIdentifier": None,
        "visualEvidenceIdentifiers": cast("JsonValue", visual_evidence_identifiers),
        "testProfileVersion": None,
    }


def _global_annotations(
    anomalies: list[JsonValue],
    criteria_by_code: dict[str, CriterionInventory],
) -> dict[str, JsonValue]:
    """Create document-level annotations for inventory conflicts."""

    records: list[JsonValue] = []
    for anomaly_number, anomaly_value in enumerate(anomalies, start=1):
        anomaly = as_mapping(
            anomaly_value,
            location="inventoryAnomalies.anomalies[]",
        )
        code = anomaly.get("code")
        affected_codes = anomaly.get("affectedCodes")
        physical_page_value = anomaly.get("physicalPage")
        if isinstance(physical_page_value, int):
            physical_page = physical_page_value
        elif isinstance(code, str) and code in criteria_by_code:
            physical_page = criteria_by_code[code].source_start_page
        elif (
            isinstance(affected_codes, list)
            and affected_codes
            and isinstance(affected_codes[0], str)
            and affected_codes[0] in criteria_by_code
        ):
            physical_page = criteria_by_code[affected_codes[0]].source_start_page
        else:
            physical_page = 1
        records.append(
            {
                "annotationIdentifier": f"inventory-anomaly-{anomaly_number:03d}",
                "annotationType": "sourceInconsistency",
                "targetType": "document",
                "targetReference": (code if isinstance(code, str) else SOURCE_DOCUMENT_IDENTIFIER),
                "sourceDocumentIdentifier": SOURCE_DOCUMENT_IDENTIFIER,
                "physicalPage": physical_page,
                "sourceText": _annotation_source_text(anomaly),
                "explanation": json.dumps(
                    anomaly,
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "disposition": "unresolved",
                "reviewStatus": "pending",
                "verificationEvidence": ["장별 항목표와 상세 머리글 또는 목차 원문을 대조했다."],
                "reviewedBy": None,
                "reviewedAt": None,
                "approvedBy": None,
                "approvedAt": None,
            }
        )
    return {"schemaVersion": 1, "annotations": records}


def generate(*, root: Path | None = None) -> None:
    """Generate all extracted packages and corpus-wide registries."""

    repository = root or repository_root()
    inventory = load_json(repository / "data/derived/authoritative-inventory.json")
    anomalies_document = load_json(repository / "data/derived/inventory-anomalies.json")
    criteria = [
        CriterionInventory.from_value(value)
        for value in as_sequence(
            inventory["criteria"],
            location="authoritativeInventory.criteria",
        )
    ]
    if len(criteria) != 382:
        msg = f"expected 382 inventory criteria, got {len(criteria)}"
        raise ValueError(msg)
    anomalies = as_sequence(
        anomalies_document["anomalies"],
        location="inventoryAnomalies.anomalies",
    )
    criteria_by_code = {criterion.code: criterion for criterion in criteria}
    existing_page_inventory = load_yaml(repository / "data/page-region-inventory.yaml")
    existing_regions = {
        region["pageRegionIdentifier"]: region
        for region_value in as_sequence(
            existing_page_inventory["pageRegions"],
            location="pageRegionInventory.pageRegions",
        )
        if isinstance(region_value, dict)
        and isinstance(
            (region := region_value).get("pageRegionIdentifier"),
            str,
        )
    }

    transcripts_by_slug: dict[str, dict[int, str]] = {}
    visual_assets_by_slug: dict[str, dict[int, VisualAsset]] = {}
    criterion_regions: list[dict[str, JsonValue]] = []
    page_owner: dict[int, CriterionInventory] = {}
    with pdfplumber.open(repository / SOURCE_DOCUMENT_PATH) as document:
        pages = cast("list[PdfPage]", document.pages)
        if len(pages) != 873:
            msg = f"expected 873 PDF pages, got {len(pages)}"
            raise ValueError(msg)
        for criterion in criteria:
            transcripts: dict[int, str] = {}
            visual_assets: dict[int, VisualAsset] = {}
            if criterion.slug not in STRUCTURED_SLUGS:
                asset_directory = canonical_asset_directory(repository, criterion.slug)
                if asset_directory.is_dir():
                    for stale_asset in asset_directory.glob(
                        f"{criterion.slug}-page-*-source-region.png"
                    ):
                        stale_asset.unlink()
                    if not any(asset_directory.iterdir()):
                        asset_directory.rmdir()
            for physical_page in range(
                criterion.source_start_page,
                criterion.source_end_page + 1,
            ):
                if physical_page in page_owner:
                    msg = f"physical page {physical_page} has multiple criterion owners"
                    raise ValueError(msg)
                page_owner[physical_page] = criterion
                page = pages[physical_page - 1]
                transcript, bounding_box = _transcript(
                    page,
                    first_page=physical_page == criterion.source_start_page,
                    physical_page=physical_page,
                )
                transcripts[physical_page] = transcript
                if criterion.slug not in STRUCTURED_SLUGS:
                    visual_assets[physical_page] = _render_source_crop(
                        page,
                        criterion=criterion,
                        physical_page=physical_page,
                        bounding_box=bounding_box,
                        repository=repository,
                    )
                region_identifier = f"p{physical_page}-{criterion.slug}"
                preserved_region = (
                    existing_regions.get(region_identifier)
                    if criterion.slug in STRUCTURED_SLUGS
                    else None
                )
                criterion_regions.append(
                    preserved_region
                    or _page_region(
                        criterion,
                        physical_page=physical_page,
                        bounding_box=bounding_box,
                    )
                )
            transcripts_by_slug[criterion.slug] = transcripts
            visual_assets_by_slug[criterion.slug] = visual_assets

    annotations_by_slug: dict[str, list[JsonValue]] = {}
    manifest_records: list[JsonValue] = []
    for criterion in criteria:
        structured = criterion.slug in STRUCTURED_SLUGS
        annotations = (
            as_sequence(
                load_criterion_metadata(
                    criterion_directory(repository, criterion.domain_identifier)
                    / f"{criterion.slug}.md"
                )["sourceAnnotations"],
                location=f"{criterion.slug}.sourceAnnotations",
            )
            if structured
            else _criterion_annotations(criterion, anomalies)
        )
        annotations_by_slug[criterion.slug] = annotations
        if not structured:
            metadata = _criterion_metadata(criterion, annotations)
            criterion_source_directory = criterion_directory(
                repository, criterion.domain_identifier
            )
            criterion_source_directory.mkdir(parents=True, exist_ok=True)
            (criterion_source_directory / f"{criterion.slug}.md").write_text(
                _criterion_markdown(
                    criterion,
                    metadata,
                    transcripts_by_slug[criterion.slug],
                    visual_assets_by_slug[criterion.slug],
                ),
                encoding="utf-8",
            )
            _write_yaml(
                criterion_source_directory / f"{criterion.slug}.provenance.yaml",
                _criterion_provenance(
                    criterion,
                    visual_assets_by_slug[criterion.slug],
                ),
            )
        manifest_records.append(_manifest_record(criterion, structured=structured))

    _write_yaml(
        repository / "data/criteria-manifest.yaml",
        {
            "schemaVersion": 1,
            "completionStatus": "complete",
            "expectedCriterionCount": 382,
            "registeredCriterionCount": 382,
            "criteria": manifest_records,
        },
    )

    noncriterion_pages = sorted(set(range(1, 874)) - set(page_owner))
    page_regions: list[dict[str, JsonValue]] = list(criterion_regions)
    for physical_page in sorted(page_owner):
        page_regions.extend(
            [
                _excluded_header_region(physical_page),
                _excluded_footer_region(physical_page),
            ]
        )
    page_regions.extend(_noncriterion_region(physical_page) for physical_page in noncriterion_pages)
    page_regions.sort(
        key=lambda region: (
            cast("int", region["physicalPage"]),
            cast("str", region["pageRegionIdentifier"]),
        )
    )
    page_inventory: dict[str, JsonValue] = {
        "schemaVersion": 1,
        "completionStatus": "complete",
        "sourceDocumentIdentifier": SOURCE_DOCUMENT_IDENTIFIER,
        "expectedPhysicalPageCount": 873,
        "registeredPhysicalPageCount": 873,
        "unclassifiedContentBlockCount": 0,
        "coordinateSystem": {
            "origin": "topLeft",
            "unit": "normalizedPage",
        },
        "pageRegions": cast("JsonValue", page_regions),
    }
    _write_yaml(repository / "data/page-region-inventory.yaml", page_inventory)

    checksums_by_slug = {
        criterion.slug: criterion_source_checksum(
            criterion.slug,
            criterion.domain_identifier,
            root=repository,
        )
        for criterion in criteria
    }
    review_records: list[JsonValue] = [
        _review_record(
            subject_type="criterion",
            subject_identifier=criterion.slug,
            subject_source_checksum=checksums_by_slug[criterion.slug],
            source_anomaly_count=len(annotations_by_slug[criterion.slug]),
            workflow_status=("structured" if criterion.slug in STRUCTURED_SLUGS else "extracted"),
            visual_evidence_identifiers=[
                visual_asset.markdown_path.removeprefix("../")
                for visual_asset in visual_assets_by_slug[criterion.slug].values()
            ],
        )
        for criterion in criteria
    ]
    for region in page_regions:
        if region["publicationDisposition"] not in {"published", "derived"}:
            continue
        owner_identifier = region["ownerIdentifier"]
        owner_source_checksum = (
            checksums_by_slug[owner_identifier]
            if isinstance(owner_identifier, str) and owner_identifier in checksums_by_slug
            else SOURCE_DOCUMENT_CHECKSUM
        )
        review_records.append(
            _review_record(
                subject_type="pageRegion",
                subject_identifier=cast(
                    "str",
                    region["pageRegionIdentifier"],
                ),
                subject_source_checksum=region_source_checksum(
                    region,
                    owner_source_checksum=owner_source_checksum,
                ),
                source_anomaly_count=0,
                workflow_status="extracted",
                visual_evidence_identifiers=(
                    [
                        visual_assets_by_slug[owner_identifier][
                            cast("int", region["physicalPage"])
                        ].markdown_path.removeprefix("../")
                    ]
                    if isinstance(owner_identifier, str)
                    and owner_identifier in visual_assets_by_slug
                    and cast("int", region["physicalPage"])
                    in visual_assets_by_slug[owner_identifier]
                    else []
                ),
            )
        )
    _write_yaml(
        repository / "data/review-registry.yaml",
        {
            "schemaVersion": 1,
            "completionStatus": "complete",
            "records": review_records,
        },
    )
    _write_yaml(
        repository / "data/source-annotations.yaml",
        _global_annotations(anomalies, criteria_by_code),
    )


def load_criterion_metadata(path: Path) -> dict[str, JsonValue]:
    """Load existing structured front matter without importing the renderer."""

    source = path.read_text(encoding="utf-8")
    if not source.startswith("---\n"):
        msg = f"{path}: missing front matter"
        raise ValueError(msg)
    separator_index = source.find("\n---\n", 4)
    if separator_index < 0:
        msg = f"{path}: unterminated front matter"
        raise ValueError(msg)
    parser = YAML(typ="safe", pure=True)
    parser.version = (1, 2)
    loaded = parser.load(source[4:separator_index])
    if not isinstance(loaded, dict):
        msg = f"{path}: invalid front matter"
        raise TypeError(msg)
    return cast("dict[str, JsonValue]", loaded)


def _argument_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""

    parser = argparse.ArgumentParser(description=__doc__)
    add_logging_arguments(parser)
    return parser


def main() -> int:
    """Generate the complete extracted corpus."""

    arguments = _argument_parser().parse_args()
    with configure_runtime_logging(
        "generate_corpus",
        level=arguments.log_level,
        log_directory=arguments.log_directory,
    ) as logger:
        logger.info("Corpus generation started", event="command.started")
        generate()
        logger.info(
            "Corpus generation completed",
            event="command.completed",
            criterion_count=382,
            physical_page_count=873,
        )
        print("generated 382 criterion packages and the 873-page inventory")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
