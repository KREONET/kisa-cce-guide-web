"""Apply validated Codex-native candidates as one canonical transaction."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from conversion import codex_agent_pipeline
from conversion import codex_candidate_applier as legacy_applier
from conversion.common import (
    JsonValue,
    as_mapping,
    as_sequence,
    criterion_source_checksum,
    load_criterion,
    load_json,
    load_yaml,
    region_source_checksum,
    repository_root,
    sha256_file,
)
from conversion.paths import WORK_DIRECTORY, criterion_directory
from conversion.runtime_logging import add_logging_arguments, configure_runtime_logging
from conversion.validate_content import validate_repository

DEFAULT_WORK_DIRECTORY = WORK_DIRECTORY / "codex-agent-sol-release"


@dataclass(frozen=True)
class PreparedAgentCandidate:
    """Hold one validated native output and its intended canonical state."""

    job: codex_agent_pipeline.AgentJob
    validation: dict[str, JsonValue]
    run: dict[str, JsonValue]
    slug: str
    domain_identifier: str
    content_model: str
    content_model_version: int
    criterion_path: Path
    provenance_path: Path
    criterion_bytes: bytes
    provenance_bytes: bytes
    criterion_checksum: str
    source_annotation_count: int
    force_source_review: bool
    source_crop_paths: tuple[Path, ...]


def _json_bytes(document: dict[str, JsonValue]) -> bytes:
    """Serialize stable human-readable JSON."""

    return (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _manifest_records(manifest: dict[str, JsonValue]) -> list[dict[str, JsonValue]]:
    """Return mutable manifest criterion records."""

    return [
        as_mapping(value, location="manifest.criteria[]")
        for value in as_sequence(manifest["criteria"], location="manifest.criteria")
    ]


def _manifest_record(
    manifest: dict[str, JsonValue],
    *,
    slug: str,
) -> dict[str, JsonValue]:
    """Return one uniquely identified manifest record."""

    matches = [record for record in _manifest_records(manifest) if record.get("slug") == slug]
    if len(matches) != 1:
        message = f"expected one manifest record for {slug}"
        raise ValueError(message)
    return matches[0]


def _job_from_workspace(workspace: Path) -> codex_agent_pipeline.AgentJob:
    """Load an existing job without rewriting immutable workspace inputs."""

    task = load_json(workspace / "task.json")
    criterion = as_mapping(task["criterion"], location="task.criterion")
    slug = criterion.get("slug")
    if not isinstance(slug, str):
        message = f"agent task has no criterion slug: {workspace / 'task.json'}"
        raise TypeError(message)
    job_directory = workspace.parent
    return codex_agent_pipeline.AgentJob(
        slug=slug,
        task=task,
        job_directory=job_directory,
        workspace=workspace,
        task_path=workspace / "task.json",
        status_path=workspace / "output/status.json",
        criterion_path=workspace / "output/criterion.md",
        provenance_path=workspace / "output/provenance.yaml",
        events_path=job_directory / "events.jsonl",
        stderr_path=job_directory / "stderr.log",
        run_path=job_directory / "run.json",
    )


def _current_job(
    slug: str,
    *,
    root: Path,
    work_directory: Path,
    manifest_record: dict[str, JsonValue],
) -> codex_agent_pipeline.AgentJob:
    """Find the unique checksum-addressed job bound to current canonical input."""

    if manifest_record.get("contentModel") != "extractedCriterion":
        message = f"{slug} is not an extractedCriterion"
        raise ValueError(message)
    domain_identifier = manifest_record.get("domainIdentifier")
    if not isinstance(domain_identifier, str):
        message = f"{slug} manifest record has no domain identifier"
        raise TypeError(message)
    source_checksum = criterion_source_checksum(slug, domain_identifier, root=root)
    source_document_checksum_loader = (
        codex_agent_pipeline._source_document_checksum  # noqa: SLF001
    )
    source_identifier, source_document_checksum = source_document_checksum_loader(root=root)
    taxonomy = load_yaml(root / legacy_applier.TAXONOMY_PATH)
    expected_target_taxonomy = codex_agent_pipeline._target_taxonomy_slice(taxonomy)  # noqa: SLF001
    expected_contract = {
        "contractChecksum": sha256_file(root / codex_agent_pipeline.AGENT_CONTRACT_PATH),
        "statusSchemaChecksum": sha256_file(root / codex_agent_pipeline.AGENT_STATUS_SCHEMA_PATH),
        "referenceCriterionChecksum": sha256_file(
            root / codex_agent_pipeline.REFERENCE_CRITERION_PATH
        ),
        "referenceProvenanceChecksum": sha256_file(
            root / codex_agent_pipeline.REFERENCE_PROVENANCE_PATH
        ),
    }
    jobs_directory = work_directory / "jobs" / slug
    if not jobs_directory.is_dir():
        message = f"no Codex-native candidate job exists for {slug}: {jobs_directory}"
        raise FileNotFoundError(message)

    matches: list[codex_agent_pipeline.AgentJob] = []
    for job_directory in sorted(jobs_directory.iterdir(), key=lambda path: path.name.encode()):
        task_path = job_directory / "workspace/task.json"
        if not job_directory.is_dir() or not task_path.is_file():
            continue
        try:
            job = _job_from_workspace(task_path.parent)
            task_criterion = as_mapping(job.task["criterion"], location="task.criterion")
            task_source = as_mapping(job.task["source"], location="task.source")
            calculated_checksum = codex_agent_pipeline._task_checksum(job.task)  # noqa: SLF001
        except (KeyError, OSError, TypeError, ValueError):
            continue
        if (
            job.slug == slug
            and job.task.get("taskChecksum") == job_directory.name == calculated_checksum
            and task_criterion.get("criterionSourceChecksum") == source_checksum
            and task_criterion.get("domainIdentifier") == domain_identifier
            and task_source.get("sourceDocumentIdentifier") == source_identifier
            and task_source.get("sourceDocumentChecksum") == source_document_checksum
            and job.task.get("targetTaxonomy") == expected_target_taxonomy
            and job.task.get("contract") == expected_contract
        ):
            matches.append(job)
    if len(matches) != 1:
        message = (
            f"expected one current Codex-native candidate job for {slug}, found {len(matches)}"
        )
        raise ValueError(message)
    return matches[0]


def _validated_run(
    job: codex_agent_pipeline.AgentJob,
    validation: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    """Load a completed run whose recorded validation equals fresh validation."""

    run = load_json(job.run_path)
    if run.get("status") != "completed":
        message = f"{job.slug} Codex-native run is not completed"
        raise ValueError(message)
    if (
        run.get("taskIdentifier") != job.task["taskIdentifier"]
        or run.get("taskChecksum") != job.task["taskChecksum"]
        or run.get("validation") != validation
    ):
        message = f"{job.slug} run record differs from fresh candidate validation"
        raise ValueError(message)
    return run


def _source_crop_paths(
    slug: str,
    *,
    root: Path,
    domain_identifier: str,
) -> tuple[Path, ...]:
    """Select checksum-verified legacy source crops and reject orphaned assets."""

    provenance = load_yaml(criterion_directory(root, domain_identifier) / f"{slug}.provenance.yaml")
    _assets, _assets_by_node, source_crop_paths = legacy_applier._prepare_assets(  # noqa: SLF001
        [],
        provenance,
        root=root,
        domain_identifier=domain_identifier,
        slug=slug,
    )
    return source_crop_paths


def _prepare_candidate(
    slug: str,
    *,
    root: Path,
    work_directory: Path,
    manifest_record: dict[str, JsonValue],
) -> PreparedAgentCandidate:
    """Validate one existing job and prepare byte-exact canonical replacements."""

    job = _current_job(
        slug,
        root=root,
        work_directory=work_directory,
        manifest_record=manifest_record,
    )
    validation = codex_agent_pipeline.validate_agent_candidate(job, root=root)
    run = _validated_run(job, validation)
    criterion = load_criterion(job.criterion_path)
    task_criterion = as_mapping(job.task["criterion"], location="task.criterion")
    domain_identifier = cast("str", task_criterion["domainIdentifier"])
    content_model = criterion.metadata.get("contentModel")
    content_model_version = criterion.metadata.get("contentModelVersion")
    if not isinstance(content_model, str) or not isinstance(content_model_version, int):
        message = f"{slug} candidate has no content model version"
        raise TypeError(message)
    if content_model_version != legacy_applier.CANONICAL_CONTENT_MODEL_VERSION:
        message = (
            f"{slug} candidate content model version must be "
            f"{legacy_applier.CANONICAL_CONTENT_MODEL_VERSION}"
        )
        raise ValueError(message)
    criterion_bytes = job.criterion_path.read_bytes()
    provenance_bytes = job.provenance_path.read_bytes()
    annotations = as_sequence(criterion.metadata["sourceAnnotations"], location="sourceAnnotations")
    source_crop_paths = _source_crop_paths(
        slug,
        root=root,
        domain_identifier=domain_identifier,
    )
    checksum = legacy_applier._intended_criterion_checksum(  # noqa: SLF001
        root=root,
        domain_identifier=domain_identifier,
        slug=slug,
        markdown_bytes=criterion_bytes,
        provenance_bytes=provenance_bytes,
        retained_asset_paths=[],
    )
    return PreparedAgentCandidate(
        job=job,
        validation=validation,
        run=run,
        slug=slug,
        domain_identifier=domain_identifier,
        content_model=content_model,
        content_model_version=content_model_version,
        criterion_path=criterion_directory(root, domain_identifier) / f"{slug}.md",
        provenance_path=criterion_directory(root, domain_identifier) / f"{slug}.provenance.yaml",
        criterion_bytes=criterion_bytes,
        provenance_bytes=provenance_bytes,
        criterion_checksum=checksum,
        source_annotation_count=len(annotations),
        force_source_review=validation.get("analysisStatus") == "needsSourceReview",
        source_crop_paths=source_crop_paths,
    )


def _review_record(
    records: list[JsonValue],
    *,
    subject_type: str,
    subject_identifier: str,
) -> dict[str, JsonValue]:
    """Return one review record by its compound identity."""

    matches = [
        as_mapping(value, location="reviewRegistry.records[]")
        for value in records
        if isinstance(value, dict)
        and value.get("subjectType") == subject_type
        and value.get("subjectIdentifier") == subject_identifier
    ]
    if len(matches) != 1:
        message = f"expected one {subject_type} review record for {subject_identifier}"
        raise ValueError(message)
    return matches[0]


def _updated_shared_documents(
    packages: list[PreparedAgentCandidate],
    *,
    root: Path,
    manifest: dict[str, JsonValue],
) -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
    """Update manifest and invalidate every review owned by changed packages."""

    updated_manifest = copy.deepcopy(manifest)
    review_registry = copy.deepcopy(load_yaml(root / legacy_applier.REVIEW_REGISTRY_PATH))
    review_records = as_sequence(review_registry["records"], location="reviewRegistry.records")
    inventory = load_yaml(root / legacy_applier.PAGE_REGION_INVENTORY_PATH)
    page_regions = [
        as_mapping(value, location="pageRegionInventory.pageRegions[]")
        for value in as_sequence(
            inventory["pageRegions"],
            location="pageRegionInventory.pageRegions",
        )
    ]
    for package in packages:
        record = _manifest_record(updated_manifest, slug=package.slug)
        record["contentModel"] = package.content_model
        record["contentModelVersion"] = package.content_model_version
        record["technicalLiteralInventoryMode"] = "extractedFromTypedAst"

        criterion_review = _review_record(
            review_records,
            subject_type="criterion",
            subject_identifier=package.slug,
        )
        criterion_review["subjectSourceChecksum"] = package.criterion_checksum
        legacy_applier._reset_review_record(  # noqa: SLF001
            criterion_review,
            workflow_status="structured",
            source_anomaly_count=package.source_annotation_count,
            force_source_review=package.force_source_review,
            preserve_visual_evidence=False,
        )

        owned_regions = [
            region
            for region in page_regions
            if region.get("ownerType") == "criterion"
            and region.get("ownerIdentifier") == package.slug
            and region.get("publicationDisposition") in {"published", "derived"}
        ]
        if not owned_regions:
            message = f"no published page regions are owned by {package.slug}"
            raise ValueError(message)
        for region in owned_regions:
            identifier = cast("str", region["pageRegionIdentifier"])
            region_review = _review_record(
                review_records,
                subject_type="pageRegion",
                subject_identifier=identifier,
            )
            region_review["subjectSourceChecksum"] = region_source_checksum(
                region,
                owner_source_checksum=package.criterion_checksum,
            )
            existing_count = region_review.get("unresolvedSourceAnomalyCount")
            anomaly_count = existing_count if isinstance(existing_count, int) else 0
            legacy_applier._reset_review_record(  # noqa: SLF001
                region_review,
                workflow_status="extracted",
                source_anomaly_count=anomaly_count,
                force_source_review=False,
                preserve_visual_evidence=False,
            )
    return updated_manifest, review_registry


def _updated_run_bytes(package: PreparedAgentCandidate) -> bytes:
    """Mark the existing checksum-bound run validation as canonically applied."""

    run = copy.deepcopy(package.run)
    validation = copy.deepcopy(package.validation)
    validation["canonicalApplied"] = True
    run["validation"] = validation
    return _json_bytes(run)


def _validate_final_state(packages: list[PreparedAgentCandidate], *, root: Path) -> None:
    """Require exact package checksums and full repository validation."""

    for package in packages:
        checksum = criterion_source_checksum(package.slug, package.domain_identifier, root=root)
        if checksum != package.criterion_checksum:
            message = f"applied criterion checksum differs for {package.slug}"
            raise RuntimeError(message)
    issues = cast("list[object]", validate_repository(root=root, release=False))
    if issues:
        raise ValueError(
            legacy_applier._repository_error_message(  # noqa: SLF001
                issues,
                stage="failed after staged replacement",
            )
        )


def _stage_transaction(
    packages: list[PreparedAgentCandidate],
    *,
    root: Path,
    manifest: dict[str, JsonValue],
) -> tuple[dict[Path, bytes], tuple[Path, ...]]:
    """Build and schema-validate all canonical replacement bytes."""

    if not packages:
        message = "Codex-native apply requires at least one candidate"
        raise ValueError(message)
    issues = cast("list[object]", validate_repository(root=root, release=False))
    if issues:
        raise ValueError(
            legacy_applier._repository_error_message(issues, stage="failed before apply")  # noqa: SLF001
        )
    updated_manifest, review_registry = _updated_shared_documents(
        packages,
        root=root,
        manifest=manifest,
    )
    taxonomy = load_yaml(root / legacy_applier.TAXONOMY_PATH)
    legacy_applier._validate_staged_shared_documents(  # noqa: SLF001
        root=root,
        taxonomy=taxonomy,
        manifest=updated_manifest,
        review_registry=review_registry,
    )
    replacements = {
        root / legacy_applier.MANIFEST_PATH: legacy_applier._yaml_text(updated_manifest).encode(),  # noqa: SLF001
        root / legacy_applier.REVIEW_REGISTRY_PATH: legacy_applier._yaml_text(  # noqa: SLF001
            review_registry
        ).encode(),
    }
    crop_paths: list[Path] = []
    for package in packages:
        replacements[package.criterion_path] = package.criterion_bytes
        replacements[package.provenance_path] = package.provenance_bytes
        replacements[package.job.run_path] = _updated_run_bytes(package)
        crop_paths.extend(package.source_crop_paths)
    if len(crop_paths) != len(set(crop_paths)):
        message = "a source crop belongs to more than one Codex-native candidate"
        raise ValueError(message)
    return replacements, tuple(crop_paths)


def _apply_transaction(  # noqa: C901
    packages: list[PreparedAgentCandidate],
    *,
    root: Path,
    work_directory: Path,
    manifest: dict[str, JsonValue],
    dry_run: bool,
) -> tuple[Path, ...]:
    """Validate or apply all packages with rollback after any replacement failure."""

    replacements, crop_paths = _stage_transaction(packages, root=root, manifest=manifest)
    output_paths = tuple(package.criterion_path for package in packages)
    if dry_run:
        return output_paths

    originals = {path: path.read_bytes() for path in replacements}
    original_crops = {path: path.read_bytes() for path in crop_paths}
    for package in packages:
        legacy_applier._copy_source_crop_evidence(  # noqa: SLF001
            package.source_crop_paths,
            root=root,
            work_directory=work_directory,
            slug=package.slug,
        )
    for path, content in originals.items():
        if path.read_bytes() != content:
            message = f"file changed while staging Codex-native apply: {path}"
            raise RuntimeError(message)
    for path, content in original_crops.items():
        if path.read_bytes() != content:
            message = f"source crop changed while staging Codex-native apply: {path}"
            raise RuntimeError(message)

    try:
        for path, content in replacements.items():
            legacy_applier._atomic_replace_bytes(path, content)  # noqa: SLF001
        for path in crop_paths:
            path.unlink()
        _validate_final_state(packages, root=root)
    except BaseException:
        for path, content in originals.items():
            legacy_applier._atomic_replace_bytes(path, content)  # noqa: SLF001
        for path, content in original_crops.items():
            legacy_applier._atomic_replace_bytes(path, content)  # noqa: SLF001
        raise
    return output_paths


def _selected_slugs(manifest: dict[str, JsonValue]) -> list[str]:
    """Return extracted criteria in manifest order."""

    slugs: list[str] = []
    for record in _manifest_records(manifest):
        if record.get("contentModel") != "extractedCriterion":
            continue
        slug = record.get("slug")
        if not isinstance(slug, str):
            message = "extracted manifest record has no slug"
            raise TypeError(message)
        slugs.append(slug)
    return slugs


def _prepare_selected(
    slugs: list[str],
    *,
    root: Path,
    work_directory: Path,
    dry_run: bool,
) -> tuple[Path, ...]:
    """Prevalidate all candidates against one unchanged canonical snapshot."""

    tracked_paths = (
        root / legacy_applier.MANIFEST_PATH,
        root / legacy_applier.REVIEW_REGISTRY_PATH,
        root / legacy_applier.TAXONOMY_PATH,
        root / legacy_applier.PAGE_REGION_INVENTORY_PATH,
    )
    tracked_bytes = {path: path.read_bytes() for path in tracked_paths}
    manifest = load_yaml(root / legacy_applier.MANIFEST_PATH)
    packages = [
        _prepare_candidate(
            slug,
            root=root,
            work_directory=work_directory,
            manifest_record=_manifest_record(manifest, slug=slug),
        )
        for slug in slugs
    ]
    for path, content in tracked_bytes.items():
        if path.read_bytes() != content:
            message = f"shared canonical input changed during candidate validation: {path}"
            raise RuntimeError(message)
    for package in packages:
        task_criterion = as_mapping(package.job.task["criterion"], location="task.criterion")
        current_checksum = criterion_source_checksum(
            package.slug,
            package.domain_identifier,
            root=root,
        )
        if current_checksum != task_criterion["criterionSourceChecksum"]:
            message = f"canonical source changed during candidate validation: {package.slug}"
            raise RuntimeError(message)
    return _apply_transaction(
        packages,
        root=root,
        work_directory=work_directory,
        manifest=manifest,
        dry_run=dry_run,
    )


def apply_agent_candidate(
    slug: str,
    *,
    root: Path | None = None,
    work_directory: Path | None = None,
    dry_run: bool = False,
) -> Path:
    """Validate or transactionally apply one native candidate."""

    repository = (root or repository_root()).resolve()
    output_root = (work_directory or repository / DEFAULT_WORK_DIRECTORY).resolve()
    return _prepare_selected(
        [slug],
        root=repository,
        work_directory=output_root,
        dry_run=dry_run,
    )[0]


def apply_all_agent_candidates(
    *,
    root: Path | None = None,
    work_directory: Path | None = None,
    dry_run: bool = False,
) -> tuple[Path, ...]:
    """Validate or transactionally apply every extracted native candidate."""

    repository = (root or repository_root()).resolve()
    output_root = (work_directory or repository / DEFAULT_WORK_DIRECTORY).resolve()
    manifest = load_yaml(repository / legacy_applier.MANIFEST_PATH)
    slugs = _selected_slugs(manifest)
    if not slugs:
        message = "manifest contains no extractedCriterion candidates to apply"
        raise ValueError(message)
    return _prepare_selected(
        slugs,
        root=repository,
        work_directory=output_root,
        dry_run=dry_run,
    )


def _argument_parser() -> argparse.ArgumentParser:
    """Build the native candidate-applier command-line parser."""

    parser = argparse.ArgumentParser(description=__doc__)
    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument("slug", nargs="?", help="criterion slug such as u-03")
    target_group.add_argument("--all", action="store_true", dest="apply_all")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--work-directory", type=Path)
    add_logging_arguments(parser)
    return parser


def main() -> int:
    """Run one logged native candidate validation or apply transaction."""

    arguments = _argument_parser().parse_args()
    with configure_runtime_logging(
        "codex_agent_candidate_applier",
        level=arguments.log_level,
        log_directory=arguments.log_directory,
        context={"slug": arguments.slug if arguments.slug is not None else "all"},
    ) as logger:
        logger.info(
            "Codex-native candidate apply started",
            event="command.started",
            dry_run=arguments.dry_run,
        )
        try:
            if arguments.apply_all:
                paths = apply_all_agent_candidates(
                    work_directory=arguments.work_directory,
                    dry_run=arguments.dry_run,
                )
            else:
                paths = (
                    apply_agent_candidate(
                        cast("str", arguments.slug),
                        work_directory=arguments.work_directory,
                        dry_run=arguments.dry_run,
                    ),
                )
        except (
            KeyError,
            FileNotFoundError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as error:
            logger.exception(
                "Codex-native candidate apply failed",
                event="command.failed",
                error=error,
            )
            sys.stderr.write(f"{error}\n")
            return 1
        logger.info(
            "Codex-native candidate apply completed",
            event="command.completed",
            dry_run=arguments.dry_run,
            output_paths=[str(path) for path in paths],
        )
        for path in paths:
            sys.stdout.write(f"{path}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
