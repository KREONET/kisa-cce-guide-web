"""Test helpers for exercising the extracted-to-structured Codex transition."""

from __future__ import annotations

import os
import shutil
import subprocess
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


def _git_output(source: Path, *arguments: str) -> bytes:
    """Read one committed legacy fixture artifact with a clear checkout requirement."""

    git_binary = shutil.which("git")
    if git_binary is None:
        message = "Codex transition tests require Git to read the legacy fixture snapshot"
        raise RuntimeError(message)
    try:
        process = subprocess.run(  # noqa: S603
            [git_binary, *arguments],
            cwd=source,
            check=True,
            capture_output=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as error:
        message = (
            "Codex transition tests require a Git checkout whose HEAD contains the "
            "legacy extracted criterion corpus"
        )
        raise RuntimeError(message) from error
    return process.stdout


def _restore_committed_package(source: Path, repository: Path, slug: str) -> tuple[str, ...]:
    """Restore one extracted criterion package from the pre-transition HEAD snapshot."""

    manifest = load_yaml(source / "data/criteria-manifest.yaml")
    manifest_record = next(
        as_mapping(value, location="manifest.criteria[]")
        for value in as_sequence(manifest["criteria"], location="manifest.criteria")
        if isinstance(value, dict) and value.get("slug") == slug
    )
    domain_identifier = cast("str", manifest_record["domainIdentifier"])
    package_paths = (
        f"{domain_identifier}/{slug}.md",
        f"{domain_identifier}/{slug}.provenance.yaml",
    )
    for relative_path in package_paths:
        destination = repository / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        _atomic_replace(destination, _git_output(source, "show", f"HEAD:{relative_path}"))

    asset_paths = tuple(
        line
        for line in _git_output(
            source,
            "ls-tree",
            "-r",
            "--name-only",
            "HEAD",
            "--",
            f"assets/{slug}",
        )
        .decode()
        .splitlines()
        if line
    )
    if not asset_paths:
        message = f"HEAD contains no legacy source-crop assets for {slug}"
        raise RuntimeError(message)
    for relative_path in asset_paths:
        destination = repository / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        _atomic_replace(destination, _git_output(source, "show", f"HEAD:{relative_path}"))
    return asset_paths


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

    Git HEAD supplies the legacy extracted packages because the working tree represents
    the completed canonical conversion. This avoids shipping duplicate binary source crops
    while keeping production eligibility rules strict.
    """

    ignored = shutil.ignore_patterns(
        ".git",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "dist",
        "site",
        "work",
    )
    shutil.copytree(source, destination, copy_function=os.link, ignore=ignored)

    assets_by_slug = {slug: _restore_committed_package(source, destination, slug) for slug in slugs}
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
