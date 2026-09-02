"""Test helpers for exercising the extracted-to-structured Codex transition."""

from __future__ import annotations

import base64
import errno
import os
import shutil
import tempfile
from io import StringIO
from pathlib import Path
from typing import cast

from ruamel.yaml import YAML

from conversion.common import (
    JsonValue,
    as_mapping,
    as_sequence,
    criterion_source_checksum,
    load_yaml,
    region_source_checksum,
)
from conversion.paths import (
    CANONICAL_ASSET_DIRECTORY,
    criterion_directory,
)

TRANSITION_FIXTURE_DIRECTORY = Path("tests/fixtures/codex-transition")
TRANSITION_FIXTURE_DOMAIN_IDENTIFIERS = {
    "u-03": "unix",
    "u-04": "unix",
    "u-05": "unix",
}
EXPECTED_EXTRACTED_PACKAGE_CHECKSUMS = {
    "u-03": "e24d5bf5aa79b7a736159e73fce9c514c7b4c258741fecce8614af58b33677be",
    "u-04": "464b4ac21280d8969702362b956ae52c9ed8a5c8c01f56e534f5ea40ecf76201",
    "u-05": "554bd667d90a52ff11a3ef6d71beac8c1ef71d24831947871fa0b373bfaf0a3a",
}


def _yaml_text(document: dict[str, JsonValue]) -> str:
    """Serialize a fixture registry with the repository YAML profile."""

    output = StringIO()
    writer = YAML()
    writer.default_flow_style = False
    writer.allow_unicode = True
    writer.width = 4096
    writer.indent(mapping=2, sequence=4, offset=2)
    writer.dump(document, output)
    return output.getvalue()


def _atomic_replace(path: Path, content: bytes) -> None:
    """Replace a hard-linked fixture file without mutating the source repository."""

    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _link_or_copy(source: str, destination: str) -> str:
    """Prefer hard links while supporting temporary directories on another filesystem."""

    try:
        os.link(source, destination)
    except OSError as error:
        if error.errno != errno.EXDEV:
            raise
        shutil.copy2(source, destination)
    return destination


def _restore_extracted_packages(
    repository: Path,
    slugs: tuple[str, ...],
) -> dict[str, tuple[str, ...]]:
    """Restore checksum-pinned extracted snapshots without platform-specific rendering."""

    missing_slugs = sorted(set(slugs) - set(EXPECTED_EXTRACTED_PACKAGE_CHECKSUMS))
    if missing_slugs:
        message = f"transition fixture contains no packages for: {', '.join(missing_slugs)}"
        raise RuntimeError(message)

    fixture_directory = repository / TRANSITION_FIXTURE_DIRECTORY
    assets_by_slug: dict[str, tuple[str, ...]] = {}
    for slug in slugs:
        domain_identifier = TRANSITION_FIXTURE_DOMAIN_IDENTIFIERS[slug]
        criterion_source_directory = criterion_directory(repository, domain_identifier)
        fixture_criterion_directory = fixture_directory / "criteria" / domain_identifier
        for suffix in (".md", ".provenance.yaml"):
            source_path = fixture_criterion_directory / f"{slug}{suffix}"
            _atomic_replace(
                criterion_source_directory / f"{slug}{suffix}",
                source_path.read_bytes(),
            )

        asset_directory = repository / CANONICAL_ASSET_DIRECTORY / slug
        # The copied repository uses hard links, so replacing the directory prevents
        # fixture restoration from mutating files in the source checkout.
        if asset_directory.is_symlink():
            asset_directory.unlink()
        elif asset_directory.is_dir():
            shutil.rmtree(asset_directory)
        else:
            asset_directory.unlink(missing_ok=True)
        asset_directory.mkdir(parents=True)

        fixture_assets = sorted(
            (fixture_directory / "assets" / slug).glob("*.png.base64"),
            key=lambda path: path.name.encode(),
        )
        if not fixture_assets:
            message = f"transition fixture contains no assets for: {slug}"
            raise RuntimeError(message)
        asset_paths: list[str] = []
        for source_path in fixture_assets:
            asset_name = source_path.name.removesuffix(".base64")
            destination_path = asset_directory / asset_name
            encoded_asset = b"".join(source_path.read_bytes().split())
            _atomic_replace(
                destination_path,
                base64.b64decode(encoded_asset, validate=True),
            )
            asset_paths.append((CANONICAL_ASSET_DIRECTORY / slug / asset_name).as_posix())
        assets_by_slug[slug] = tuple(asset_paths)

        actual_checksum = criterion_source_checksum(
            slug,
            domain_identifier,
            root=repository,
        )
        expected_checksum = EXPECTED_EXTRACTED_PACKAGE_CHECKSUMS[slug]
        if actual_checksum != expected_checksum:
            message = (
                f"transition fixture checksum differs for {slug}: "
                f"expected {expected_checksum}, got {actual_checksum}"
            )
            raise RuntimeError(message)
    return assets_by_slug


def _reset_review_state(
    record: dict[str, JsonValue],
    *,
    subject_source_checksum: str,
    visual_evidence_identifiers: list[str],
) -> None:
    """Reset review state to the machine-generated extracted-corpus boundary."""

    record["subjectSourceChecksum"] = subject_source_checksum
    record["transcriptionStatus"] = "verificationRequired"
    record["workflowStatus"] = "extracted"
    record["sourceAnomalyStatus"] = "none"
    record["reviewers"] = []
    record["reviewedAt"] = None
    record["automatedValidationResult"] = "notRun"
    record["unresolvedConversionErrorCount"] = 0
    record["unresolvedSourceAnomalyCount"] = 0
    record["validationReportIdentifier"] = None
    record["visualEvidenceIdentifiers"] = cast("JsonValue", visual_evidence_identifiers)
    record["testProfileVersion"] = None


def create_codex_transition_repository(
    source: Path,
    destination: Path,
    *,
    slugs: tuple[str, ...],
) -> Path:
    """Create an isolated repository at the legacy Codex transition boundary.

    Repository-owned snapshots preserve the selected extracted packages without invoking
    platform-specific PDF rendering during the test run.
    """

    ignored = shutil.ignore_patterns(
        ".git",
        ".artifacts",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
    )
    shutil.copytree(source, destination, copy_function=_link_or_copy, ignore=ignored)

    assets_by_slug = _restore_extracted_packages(destination, slugs)
    manifest_path = destination / "data/criteria-manifest.yaml"
    manifest = load_yaml(manifest_path)
    manifest_records = [
        as_mapping(value, location="manifest.criteria[]")
        for value in as_sequence(manifest["criteria"], location="manifest.criteria")
    ]
    for slug in slugs:
        record = next(value for value in manifest_records if value.get("slug") == slug)
        record["contentModel"] = "extractedCriterion"
        record["contentModelVersion"] = 1
        record["technicalLiteralInventoryMode"] = "sourceTranscriptSearchableText"
    _atomic_replace(manifest_path, _yaml_text(manifest).encode())

    inventory = load_yaml(destination / "data/page-region-inventory.yaml")
    page_regions = [
        as_mapping(value, location="pageRegionInventory.pageRegions[]")
        for value in as_sequence(
            inventory["pageRegions"],
            location="pageRegionInventory.pageRegions",
        )
    ]
    review_path = destination / "data/review-registry.yaml"
    review_registry = load_yaml(review_path)
    review_records = [
        as_mapping(value, location="reviewRegistry.records[]")
        for value in as_sequence(review_registry["records"], location="reviewRegistry.records")
    ]
    for slug in slugs:
        manifest_record = next(value for value in manifest_records if value.get("slug") == slug)
        domain_identifier = cast("str", manifest_record["domainIdentifier"])
        criterion_checksum = criterion_source_checksum(
            slug,
            domain_identifier,
            root=destination,
        )
        criterion_review = next(
            value
            for value in review_records
            if value.get("subjectType") == "criterion" and value.get("subjectIdentifier") == slug
        )
        _reset_review_state(
            criterion_review,
            subject_source_checksum=criterion_checksum,
            visual_evidence_identifiers=list(assets_by_slug[slug]),
        )

        owned_regions = [
            region
            for region in page_regions
            if region.get("ownerType") == "criterion"
            and region.get("ownerIdentifier") == slug
            and region.get("publicationDisposition") in {"published", "derived"}
        ]
        for region in owned_regions:
            region_identifier = cast("str", region["pageRegionIdentifier"])
            region_review = next(
                value
                for value in review_records
                if value.get("subjectType") == "pageRegion"
                and value.get("subjectIdentifier") == region_identifier
            )
            physical_page = cast("int", region["physicalPage"])
            visual_evidence = [
                path
                for path in assets_by_slug[slug]
                if f"page-{physical_page}-source-region.png" in path
            ]
            _reset_review_state(
                region_review,
                subject_source_checksum=region_source_checksum(
                    region,
                    owner_source_checksum=criterion_checksum,
                ),
                visual_evidence_identifiers=visual_evidence,
            )
    _atomic_replace(review_path, _yaml_text(review_registry).encode())
    return destination.resolve()
