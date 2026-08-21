"""Run Codex as the owner of isolated review-ready criterion conversions."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import rfc8785
from jsonschema import Draft202012Validator, FormatChecker

from conversion.codex_runner import (
    _codex_binary,
    _codex_event_summary,
    _codex_version,
    validate_model_routing,
)
from conversion.codex_task_builder import (
    _manifest_record,
    _page_evidence,
    _source_document_checksum,
    _technical_literals,
)
from conversion.common import (
    JsonValue,
    as_mapping,
    as_sequence,
    criterion_source_checksum,
    extract_leaf_blocks,
    flatten_block_references,
    heading_identifiers,
    load_criterion,
    load_json,
    load_yaml,
    repository_root,
    sha256_file,
)
from conversion.runtime_logging import add_logging_arguments, configure_runtime_logging
from conversion.validate_content import _validate_markdown_structure

AGENT_SCHEMA_VERSION = 1
DEFAULT_AGENT_WORK_DIRECTORY = Path("work/codex-agent")
AGENT_CONTRACT_PATH = Path("codex_prompts/criterion-agent-v1.md")
AGENT_STATUS_SCHEMA_PATH = Path("schemas/codex-agent-status.schema.json")
REFERENCE_CRITERION_PATH = Path("unix/u-01.md")
REFERENCE_PROVENANCE_PATH = Path("codex_prompts/provenance-example-v1.yaml")
CRITERION_METADATA_SCHEMA_PATH = Path("schemas/criterion-metadata.schema.json")
PROVENANCE_SCHEMA_PATH = Path("schemas/provenance-sidecar.schema.json")
MAXIMUM_WORKERS = 16
DEFAULT_WORKERS = 4
FINAL_PROMPT = (
    "Read contract.md and task.json, inspect every attached evidence image, and complete the "
    "criterion conversion. Write only the required files under output/. Return only the bounded "
    "JSON status object."
)
UNSUPPORTED_VISION_ERROR = "view_image is not allowed because you do not support image inputs"


@dataclass(frozen=True)
class AgentJob:
    """Describe one content-addressed isolated Codex workspace."""

    slug: str
    task: dict[str, JsonValue]
    job_directory: Path
    workspace: Path
    task_path: Path
    status_path: Path
    criterion_path: Path
    provenance_path: Path
    events_path: Path
    stderr_path: Path
    run_path: Path


type AgentRunner = Callable[[AgentJob, str | None, bool], dict[str, JsonValue]]


def _schema_errors(
    document: dict[str, JsonValue],
    schema: dict[str, JsonValue],
) -> list[str]:
    """Return stable JSON Schema validation descriptions."""

    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        f"{'.'.join(str(part) for part in error.absolute_path) or '$'}: {error.message}"
        for error in sorted(validator.iter_errors(document), key=lambda item: list(item.path))
    ]


def _task_checksum(task: dict[str, JsonValue]) -> str:
    """Hash the relevant job contract without its self-referential checksum."""

    payload = dict(task)
    payload.pop("taskChecksum", None)
    return hashlib.sha256(rfc8785.dumps(payload)).hexdigest()


def _write_json(path: Path, document: dict[str, JsonValue]) -> None:
    """Write deterministic human-readable JSON with one trailing newline."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _copy_file(source: Path, destination: Path) -> None:
    """Copy one immutable job input while preserving no writable repository linkage."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def _workspace_validator_source(repository: Path) -> str:
    """Build a small workspace entry point that reuses the repository validator read-only."""

    repository_literal = json.dumps(repository.resolve().as_posix())
    # Resolving the executable symlink would discard the active virtual environment and its
    # dependencies when the agent invokes the workspace validator.
    interpreter = Path(sys.executable).absolute().as_posix()
    return (
        f"#!{interpreter}\n"
        "from pathlib import Path\n"
        "import sys\n\n"
        "sys.dont_write_bytecode = True\n"
        f"repository = Path({repository_literal})\n"
        "sys.path.insert(0, str(repository))\n\n"
        "from conversion.codex_agent_pipeline import (\n"
        "    agent_block_references,\n"
        "    validate_agent_workspace,\n"
        ")\n\n"
        "workspace = Path(__file__).resolve().parent\n"
        "if sys.argv[1:] == ['--block-references']:\n"
        "    print('\\n'.join(agent_block_references(workspace, root=repository)))\n"
        "elif not sys.argv[1:]:\n"
        "    validate_agent_workspace(workspace, root=repository)\n"
        "    print('candidate validation passed')\n"
        "else:\n"
        "    raise SystemExit('usage: validate_candidate.py [--block-references]')\n"
    )


def _target_taxonomy_slice(taxonomy: dict[str, JsonValue]) -> list[JsonValue]:
    """Keep only target mapping data needed by the conversion agent."""

    targets: list[JsonValue] = []
    for index, value in enumerate(as_sequence(taxonomy["targets"], location="taxonomy.targets")):
        target = as_mapping(value, location=f"taxonomy.targets[{index}]")
        targets.append(
            {
                name: target[name]
                for name in ("identifier", "label", "sourceLabels")
                if name in target
            }
        )
    return targets


def _agent_job_paths(
    work_directory: Path,
    slug: str,
    semantic_key: str,
) -> dict[str, Path]:
    """Return every path owned by one isolated job."""

    job_directory = work_directory / "jobs" / slug / semantic_key
    workspace = job_directory / "workspace"
    output_directory = workspace / "output"
    return {
        "jobDirectory": job_directory,
        "workspace": workspace,
        "task": workspace / "task.json",
        "status": output_directory / "status.json",
        "criterion": output_directory / "criterion.md",
        "provenance": output_directory / "provenance.yaml",
        "events": job_directory / "events.jsonl",
        "stderr": job_directory / "stderr.log",
        "run": job_directory / "run.json",
    }


def build_agent_job(  # noqa: PLR0915
    slug: str,
    *,
    root: Path | None = None,
    work_directory: Path | None = None,
) -> AgentJob:
    """Build one compact workspace from only criterion-relevant dependencies."""

    repository = (root or repository_root()).resolve()
    output_root = (work_directory or repository / DEFAULT_AGENT_WORK_DIRECTORY).resolve()
    manifest_record = _manifest_record(slug, root=repository)
    if manifest_record.get("contentModel") != "extractedCriterion":
        message = f"{slug} is not an extractedCriterion"
        raise ValueError(message)
    domain_identifier = manifest_record.get("domainIdentifier")
    if not isinstance(domain_identifier, str):
        message = f"{slug} has no domain identifier"
        raise TypeError(message)

    source_criterion_path = repository / domain_identifier / f"{slug}.md"
    source_provenance_path = repository / domain_identifier / f"{slug}.provenance.yaml"
    criterion = load_criterion(source_criterion_path)
    provenance = load_yaml(source_provenance_path)
    evidence = _page_evidence(
        slug=slug,
        domain_identifier=domain_identifier,
        criterion_body=criterion.body,
        provenance=provenance,
        root=repository,
    )
    transcripts = [
        cast("str", as_mapping(value, location="evidence[]")["transcript"]) for value in evidence
    ]
    source_document_identifier, source_document_checksum = _source_document_checksum(
        root=repository
    )
    criterion_metadata = as_mapping(criterion.metadata["criterion"], location="criterion")
    classification = as_mapping(criterion.metadata["classification"], location="classification")
    source_page_ranges = as_sequence(
        as_mapping(criterion.metadata["provenance"], location="provenance")["sourcePageRanges"],
        location="provenance.sourcePageRanges",
    )
    if len(source_page_ranges) != 1:
        message = f"{slug} must have exactly one source page range"
        raise ValueError(message)
    source_page_range = as_mapping(source_page_ranges[0], location="sourcePageRanges[0]")
    taxonomy = load_yaml(repository / "data/taxonomy.yaml")
    expected_content_model = (
        "webApplicationCriterion" if domain_identifier == "web-application" else "systemCriterion"
    )
    workspace_input_checksums = {
        "contract.md": sha256_file(repository / AGENT_CONTRACT_PATH),
        "status.schema.json": sha256_file(repository / AGENT_STATUS_SCHEMA_PATH),
        "reference/criterion.md": sha256_file(repository / REFERENCE_CRITERION_PATH),
        "reference/provenance-example.yaml": sha256_file(repository / REFERENCE_PROVENANCE_PATH),
    }
    workspace_evidence: list[JsonValue] = []
    for value in evidence:
        page = as_mapping(value, location="evidence[]")
        copied_page = dict(page)
        workspace_image_path = f"evidence/page-{page['physicalPage']}.png"
        copied_page["workspaceImagePath"] = workspace_image_path
        workspace_evidence.append(cast("JsonValue", copied_page))
        workspace_input_checksums[workspace_image_path] = cast(
            "str",
            page["imageChecksum"],
        )
    task: dict[str, JsonValue] = {
        "schemaVersion": AGENT_SCHEMA_VERSION,
        "taskIdentifier": f"{slug}-codex-agent-v{AGENT_SCHEMA_VERSION}",
        "taskChecksum": "0" * 64,
        "criterion": {
            "code": criterion_metadata["code"],
            "slug": slug,
            "title": criterion_metadata["title"],
            "severity": criterion_metadata["severity"],
            "domainIdentifier": domain_identifier,
            "categoryIdentifier": classification["categoryIdentifier"],
            "criterionSourceChecksum": criterion_source_checksum(
                slug,
                domain_identifier,
                root=repository,
            ),
            "expectedContentModel": expected_content_model,
        },
        "source": {
            "sourceDocumentIdentifier": source_document_identifier,
            "sourceDocumentChecksum": source_document_checksum,
            "sourcePageRange": source_page_range,
        },
        "evidence": workspace_evidence,
        "requiredTechnicalLiterals": cast("JsonValue", _technical_literals(transcripts)),
        "targetTaxonomy": cast("JsonValue", _target_taxonomy_slice(taxonomy)),
        "contract": {
            "contractChecksum": sha256_file(repository / AGENT_CONTRACT_PATH),
            "statusSchemaChecksum": sha256_file(repository / AGENT_STATUS_SCHEMA_PATH),
            "referenceCriterionChecksum": sha256_file(repository / REFERENCE_CRITERION_PATH),
            "referenceProvenanceChecksum": sha256_file(repository / REFERENCE_PROVENANCE_PATH),
        },
        "workspaceInputChecksums": cast("JsonValue", workspace_input_checksums),
    }
    task["taskChecksum"] = _task_checksum(task)

    semantic_key = task["taskChecksum"]
    if not isinstance(semantic_key, str):
        message = "calculated agent task checksum must be a string"
        raise TypeError(message)
    paths = _agent_job_paths(output_root, slug, semantic_key)
    workspace = paths["workspace"]
    (workspace / "output").mkdir(parents=True, exist_ok=True)
    _write_json(paths["task"], task)
    _copy_file(repository / AGENT_CONTRACT_PATH, workspace / "contract.md")
    _copy_file(repository / AGENT_STATUS_SCHEMA_PATH, workspace / "status.schema.json")
    _copy_file(repository / REFERENCE_CRITERION_PATH, workspace / "reference" / "criterion.md")
    _copy_file(
        repository / REFERENCE_PROVENANCE_PATH,
        workspace / "reference" / "provenance-example.yaml",
    )
    validator_path = workspace / "validate_candidate.py"
    validator_path.write_text(
        _workspace_validator_source(repository),
        encoding="utf-8",
    )
    validator_path.chmod(0o755)
    for value in workspace_evidence:
        page = as_mapping(value, location="evidence[]")
        source_image_path = repository / cast("str", page["imagePath"])
        destination = workspace / cast("str", page["workspaceImagePath"])
        _copy_file(source_image_path, destination)

    return AgentJob(
        slug=slug,
        task=task,
        job_directory=paths["jobDirectory"],
        workspace=workspace,
        task_path=paths["task"],
        status_path=paths["status"],
        criterion_path=paths["criterion"],
        provenance_path=paths["provenance"],
        events_path=paths["events"],
        stderr_path=paths["stderr"],
        run_path=paths["run"],
    )


def build_agent_command(
    job: AgentJob,
    *,
    model: str | None,
    use_user_config: bool,
) -> list[str]:
    """Build a bounded Codex command whose writable root is one job workspace."""

    validate_model_routing(model=model, use_user_config=use_user_config)
    command = [
        str(_codex_binary()),
        "exec",
        "--ephemeral",
    ]
    if not use_user_config:
        command.append("--ignore-user-config")
    command.extend(
        [
            "--sandbox",
            "workspace-write",
            "--color",
            "never",
            "--json",
            "--output-schema",
            str((job.workspace / "status.schema.json").resolve()),
            "--output-last-message",
            str(job.status_path.resolve()),
            "--cd",
            str(job.workspace.resolve()),
            "--skip-git-repo-check",
        ]
    )
    if model is not None:
        command.extend(["--model", model])
    for value in as_sequence(job.task["evidence"], location="task.evidence"):
        evidence = as_mapping(value, location="task.evidence[]")
        command.extend(
            [
                "--image",
                str((job.workspace / cast("str", evidence["workspaceImagePath"])).resolve()),
            ]
        )
    return command


def _validate_status(job: AgentJob, *, root: Path) -> dict[str, JsonValue]:
    """Validate the bounded final response and its binding to the current job."""

    status = load_json(job.status_path)
    errors = _schema_errors(status, load_json(root / AGENT_STATUS_SCHEMA_PATH))
    if errors:
        message = f"invalid agent status for {job.slug}: {'; '.join(errors)}"
        raise ValueError(message)
    if status.get("taskIdentifier") != job.task["taskIdentifier"]:
        message = f"{job.slug} status task identifier differs"
        raise ValueError(message)
    if status.get("taskChecksum") != job.task["taskChecksum"]:
        message = f"{job.slug} status task checksum differs"
        raise ValueError(message)
    expected_pages = sorted(
        cast("int", as_mapping(value, location="task.evidence[]")["physicalPage"])
        for value in as_sequence(job.task["evidence"], location="task.evidence")
    )
    if status.get("reviewedPhysicalPages") != expected_pages:
        message = f"{job.slug} must confirm every evidence page in order"
        raise ValueError(message)
    unresolved_questions = as_sequence(
        status["unresolvedQuestions"],
        location="status.unresolvedQuestions",
    )
    if len(unresolved_questions) != len(set(cast("list[str]", unresolved_questions))):
        message = f"{job.slug} status unresolved questions must be unique"
        raise ValueError(message)
    if status.get("analysisStatus") == "complete" and unresolved_questions:
        message = f"{job.slug} complete status cannot contain unresolved questions"
        raise ValueError(message)
    return status


def _validate_workspace_boundary(job: AgentJob, *, root: Path) -> None:
    """Reject unexpected files, symlinks, or mutations to immutable workspace inputs."""

    expected_input_checksums = as_mapping(
        job.task["workspaceInputChecksums"],
        location="task.workspaceInputChecksums",
    )
    allowed_paths = set(expected_input_checksums) | {
        "task.json",
        "output/criterion.md",
        "output/provenance.yaml",
        "output/status.json",
        "validate_candidate.py",
    }
    actual_paths: set[str] = set()
    for path in job.workspace.rglob("*"):
        if path.is_symlink():
            message = f"{job.slug} workspace contains a symlink: {path}"
            raise ValueError(message)
        if path.is_file():
            actual_paths.add(path.relative_to(job.workspace).as_posix())
    if actual_paths != allowed_paths:
        unexpected = sorted(actual_paths.difference(allowed_paths), key=str.encode)
        missing = sorted(allowed_paths.difference(actual_paths), key=str.encode)
        message = (
            f"{job.slug} workspace file boundary differs; "
            f"unexpected={unexpected}, missing={missing}"
        )
        raise ValueError(message)
    for relative_path, expected_checksum in expected_input_checksums.items():
        if sha256_file(job.workspace / relative_path) != expected_checksum:
            message = f"{job.slug} immutable workspace input changed: {relative_path}"
            raise ValueError(message)
    if load_json(job.task_path) != job.task:
        message = f"{job.slug} task file changed during conversion"
        raise ValueError(message)
    if (job.workspace / "validate_candidate.py").read_text(
        encoding="utf-8"
    ) != _workspace_validator_source(root):
        message = f"{job.slug} workspace validator changed during conversion"
        raise ValueError(message)


def _validate_vision_capability(job: AgentJob) -> None:
    """Reject a run when Codex reports that required image inspection is unavailable."""

    if not job.stderr_path.is_file():
        return
    if UNSUPPORTED_VISION_ERROR in job.stderr_path.read_text(
        encoding="utf-8",
        errors="replace",
    ):
        message = f"{job.slug} Codex run does not support required image inputs"
        raise ValueError(message)


def validate_agent_workspace(
    workspace: Path,
    *,
    root: Path | None = None,
) -> dict[str, JsonValue]:
    """Load and validate a job directly from its isolated workspace."""

    resolved_workspace = workspace.resolve()
    task = load_json(resolved_workspace / "task.json")
    task_criterion = as_mapping(task["criterion"], location="task.criterion")
    slug = task_criterion.get("slug")
    if not isinstance(slug, str):
        message = "agent task criterion slug must be a string"
        raise TypeError(message)
    job_directory = resolved_workspace.parent
    job = AgentJob(
        slug=slug,
        task=task,
        job_directory=job_directory,
        workspace=resolved_workspace,
        task_path=resolved_workspace / "task.json",
        status_path=resolved_workspace / "output" / "status.json",
        criterion_path=resolved_workspace / "output" / "criterion.md",
        provenance_path=resolved_workspace / "output" / "provenance.yaml",
        events_path=job_directory / "events.jsonl",
        stderr_path=job_directory / "stderr.log",
        run_path=job_directory / "run.json",
    )
    return validate_agent_candidate(job, root=root)


def agent_block_references(
    workspace: Path,
    *,
    root: Path | None = None,
) -> tuple[str, ...]:
    """Return the exact ordered references for the current candidate Markdown."""

    repository = (root or repository_root()).resolve()
    resolved_workspace = workspace.resolve()
    task = load_json(resolved_workspace / "task.json")
    task_criterion = as_mapping(task["criterion"], location="task.criterion")
    slug = task_criterion.get("slug")
    if not isinstance(slug, str):
        message = "agent task criterion slug must be a string"
        raise TypeError(message)
    criterion = load_criterion(resolved_workspace / "output" / "criterion.md")
    taxonomy = load_yaml(repository / "data/taxonomy.yaml")
    return tuple(
        block.block_reference
        for block in extract_leaf_blocks(
            criterion.body,
            criterion_slug=slug,
            heading_identifier_mapping=heading_identifiers(taxonomy),
        )
    )


def validate_agent_candidate(  # noqa: C901, PLR0912, PLR0915
    job: AgentJob,
    *,
    root: Path | None = None,
) -> dict[str, JsonValue]:
    """Validate one Codex-written canonical package without rewriting it."""

    repository = (root or repository_root()).resolve()
    _validate_vision_capability(job)
    _validate_workspace_boundary(job, root=repository)
    status = _validate_status(job, root=repository)
    criterion = load_criterion(job.criterion_path)
    provenance = load_yaml(job.provenance_path)
    metadata_errors = _schema_errors(
        criterion.metadata,
        load_json(repository / CRITERION_METADATA_SCHEMA_PATH),
    )
    provenance_errors = _schema_errors(
        provenance,
        load_json(repository / PROVENANCE_SCHEMA_PATH),
    )
    if metadata_errors or provenance_errors:
        message = (
            f"invalid agent candidate for {job.slug}: "
            f"{'; '.join(metadata_errors + provenance_errors)}"
        )
        raise ValueError(message)

    task_criterion = as_mapping(job.task["criterion"], location="task.criterion")
    candidate_identity = as_mapping(criterion.metadata["criterion"], location="criterion")
    candidate_classification = as_mapping(
        criterion.metadata["classification"],
        location="classification",
    )
    expected_identity = {
        "code": task_criterion["code"],
        "slug": task_criterion["slug"],
        "title": task_criterion["title"],
        "severity": task_criterion["severity"],
    }
    actual_identity = {name: candidate_identity.get(name) for name in expected_identity}
    if actual_identity != expected_identity:
        message = f"{job.slug} candidate identity differs from the task"
        raise ValueError(message)
    if (
        candidate_classification.get("domainIdentifier") != task_criterion["domainIdentifier"]
        or candidate_classification.get("categoryIdentifier")
        != task_criterion["categoryIdentifier"]
    ):
        message = f"{job.slug} candidate classification differs from the task"
        raise ValueError(message)
    content_model = criterion.metadata.get("contentModel")
    if content_model != task_criterion["expectedContentModel"]:
        message = f"{job.slug} candidate content model differs from the task"
        raise ValueError(message)
    task_source = as_mapping(job.task["source"], location="task.source")
    candidate_source = as_mapping(criterion.metadata["provenance"], location="provenance")
    if (
        candidate_source.get("sourceDocumentIdentifier") != task_source["sourceDocumentIdentifier"]
        or candidate_source.get("sourcePageRanges") != [task_source["sourcePageRange"]]
        or provenance.get("criterionSlug") != job.slug
        or provenance.get("sourceDocumentIdentifier") != task_source["sourceDocumentIdentifier"]
    ):
        message = f"{job.slug} candidate source identity differs from the task"
        raise ValueError(message)
    task_domain_identifier = cast("str", task_criterion["domainIdentifier"])
    structure_issues = _validate_markdown_structure(
        criterion_path=Path(task_domain_identifier) / f"{job.slug}.md",
        body=criterion.body,
        content_model=cast("str", content_model),
    )
    if structure_issues:
        descriptions = "; ".join(
            f"{issue.rule_identifier}: {issue.message}" for issue in structure_issues
        )
        message = f"{job.slug} candidate violates the Markdown contract: {descriptions}"
        raise ValueError(message)

    candidate_source = job.criterion_path.read_text(encoding="utf-8")
    missing_literals = [
        literal
        for literal in cast(
            "list[str]",
            as_sequence(
                job.task["requiredTechnicalLiterals"],
                location="task.requiredTechnicalLiterals",
            ),
        )
        if literal not in candidate_source
    ]
    if missing_literals:
        message = f"{job.slug} candidate dropped technical literals: {missing_literals!r}"
        raise ValueError(message)

    taxonomy = load_yaml(repository / "data/taxonomy.yaml")
    registered_targets = {
        target.get("identifier")
        for target in (
            as_mapping(value, location="taxonomy.targets[]")
            for value in as_sequence(taxonomy["targets"], location="taxonomy.targets")
        )
    }
    candidate_targets = as_sequence(
        criterion.metadata["targetIdentifiers"],
        location="targetIdentifiers",
    )
    if any(target not in registered_targets for target in candidate_targets):
        message = f"{job.slug} candidate uses an unregistered target identifier"
        raise ValueError(message)
    if "unspecified" in candidate_targets:
        message = f"{job.slug} canonical candidate cannot retain the unspecified target"
        raise ValueError(message)

    blocks = extract_leaf_blocks(
        criterion.body,
        criterion_slug=job.slug,
        heading_identifier_mapping=heading_identifiers(taxonomy),
    )
    generated_references = [block.block_reference for block in blocks]
    declared_references = flatten_block_references(provenance)
    if len(generated_references) != len(set(generated_references)):
        message = f"{job.slug} candidate generates duplicate block references"
        raise ValueError(message)
    if len(declared_references) != len(set(declared_references)):
        message = f"{job.slug} provenance declares duplicate block references"
        raise ValueError(message)
    if generated_references != declared_references:
        message = f"{job.slug} Markdown and provenance block references differ"
        raise ValueError(message)

    evidence_pairs = {
        (
            cast("int", evidence["physicalPage"]),
            cast("str", evidence["pageRegionIdentifier"]),
        )
        for evidence in (
            as_mapping(value, location="task.evidence[]")
            for value in as_sequence(job.task["evidence"], location="task.evidence")
        )
    }
    covered_pages: set[int] = set()
    for record_value in as_sequence(
        provenance["blockProvenance"],
        location="provenance.blockProvenance",
    ):
        record = as_mapping(record_value, location="blockProvenance[]")
        spans = as_sequence(record["sourceSpans"], location="blockProvenance[].sourceSpans")
        if not spans:
            message = f"{job.slug} provenance record has no source span"
            raise ValueError(message)
        for span_value in spans:
            span = as_mapping(span_value, location="sourceSpans[]")
            pair = (span.get("physicalPage"), span.get("pageRegionIdentifier"))
            if pair not in evidence_pairs:
                message = f"{job.slug} provenance references evidence outside the job: {pair!r}"
                raise ValueError(message)
            covered_pages.add(cast("int", span["physicalPage"]))
    expected_pages = {pair[0] for pair in evidence_pairs}
    if covered_pages != expected_pages:
        message = f"{job.slug} provenance must cover every source page"
        raise ValueError(message)
    if as_sequence(provenance["assets"], location="provenance.assets"):
        message = f"{job.slug} agent v1 candidates cannot publish retained assets"
        raise ValueError(message)

    annotations = as_sequence(
        criterion.metadata["sourceAnnotations"],
        location="sourceAnnotations",
    )
    blocks_by_reference = {block.block_reference: block for block in blocks}
    evidence_region_identifiers = {pair[1] for pair in evidence_pairs}
    for annotation_value in annotations:
        annotation = as_mapping(annotation_value, location="sourceAnnotations[]")
        target_type = annotation.get("targetType")
        target_reference = annotation.get("targetReference")
        if target_type == "astNode":
            if not isinstance(target_reference, str) or target_reference not in blocks_by_reference:
                message = f"{job.slug} annotation references an unknown AST target"
                raise ValueError(message)
            source_text = annotation.get("sourceText")
            if (
                isinstance(source_text, str)
                and source_text not in blocks_by_reference[target_reference].content
            ):
                message = f"{job.slug} annotation source text is absent from its AST target"
                raise ValueError(message)
        elif target_type == "pageRegion" and target_reference not in evidence_region_identifiers:
            message = f"{job.slug} annotation references an unknown page region"
            raise ValueError(message)
    if status.get("analysisStatus") == "needsSourceReview" and not (
        annotations or status.get("unresolvedQuestions")
    ):
        message = f"{job.slug} source-review status needs an annotation or unresolved question"
        raise ValueError(message)
    if status.get("analysisStatus") == "complete" and annotations:
        message = f"{job.slug} complete status cannot contain source annotations"
        raise ValueError(message)

    return {
        "schemaVersion": AGENT_SCHEMA_VERSION,
        "taskIdentifier": job.task["taskIdentifier"],
        "taskChecksum": job.task["taskChecksum"],
        "analysisStatus": status["analysisStatus"],
        "criterionChecksum": sha256_file(job.criterion_path),
        "provenanceChecksum": sha256_file(job.provenance_path),
        "statusChecksum": sha256_file(job.status_path),
        "validationStatus": "passed",
        "canonicalApplied": False,
    }


def _run_document(  # noqa: PLR0913
    job: AgentJob,
    *,
    model: str | None,
    use_user_config: bool,
    status: str,
    duration_seconds: float,
    exit_code: int | None,
    validation: dict[str, JsonValue] | None = None,
    error: str | None = None,
) -> dict[str, JsonValue]:
    """Build a stable run record without copying model content into logs."""

    document: dict[str, JsonValue] = {
        "schemaVersion": AGENT_SCHEMA_VERSION,
        "taskIdentifier": job.task["taskIdentifier"],
        "taskChecksum": job.task["taskChecksum"],
        "slug": job.slug,
        "status": status,
        "model": model or "configured-default",
        "userConfigLoaded": use_user_config,
        "durationSeconds": round(max(0.0, duration_seconds), 6),
        "exitCode": exit_code,
    }
    if validation is not None:
        document["validation"] = validation
    if error is not None:
        document["error"] = error
    return document


def _resume_validation(
    job: AgentJob,
    *,
    root: Path,
    model: str | None,
    use_user_config: bool,
) -> dict[str, JsonValue] | None:
    """Return validated current output only when routing and checksums still match."""

    if not job.run_path.is_file():
        return None
    try:
        run = load_json(job.run_path)
        if (
            run.get("status") not in {"completed", "validationFailed"}
            or run.get("taskChecksum") != job.task["taskChecksum"]
            or run.get("model") != (model or "configured-default")
            or run.get("userConfigLoaded") is not use_user_config
        ):
            return None
        validation = validate_agent_candidate(job, root=root)
    except (KeyError, OSError, TypeError, ValueError):
        return None
    if run.get("status") == "validationFailed":
        return validation
    recorded_validation = run.get("validation")
    return validation if recorded_validation == validation else None


def run_agent_job(  # noqa: PLR0913
    job: AgentJob,
    *,
    model: str | None,
    use_user_config: bool,
    root: Path | None = None,
    resume: bool = False,
    dry_run: bool = False,
) -> dict[str, JsonValue]:
    """Run one Codex conversion and validate its complete candidate package."""

    repository = (root or repository_root()).resolve()
    if resume:
        validation = _resume_validation(
            job,
            root=repository,
            model=model,
            use_user_config=use_user_config,
        )
        if validation is not None:
            return _run_document(
                job,
                model=model,
                use_user_config=use_user_config,
                status="skipped",
                duration_seconds=0.0,
                exit_code=0,
                validation=validation,
            )

    command = build_agent_command(job, model=model, use_user_config=use_user_config)
    if dry_run:
        return _run_document(
            job,
            model=model,
            use_user_config=use_user_config,
            status="dryRun",
            duration_seconds=0.0,
            exit_code=None,
        )

    started_at = time.perf_counter()
    job.job_directory.mkdir(parents=True, exist_ok=True)
    with (
        job.events_path.open("w", encoding="utf-8") as events_file,
        job.stderr_path.open("w", encoding="utf-8") as stderr_file,
    ):
        agent_environment = os.environ.copy()
        # Git discovery must stop above the isolated workspace so Codex cannot treat the parent
        # repository as its writable project root.
        agent_environment["GIT_CEILING_DIRECTORIES"] = str(job.workspace.parent.resolve())
        completed_process = subprocess.run(  # noqa: S603
            command,
            cwd=job.workspace,
            env=agent_environment,
            input=FINAL_PROMPT,
            stdout=events_file,
            stderr=stderr_file,
            check=False,
            text=True,
        )
    duration_seconds = time.perf_counter() - started_at
    if completed_process.returncode != 0:
        run = _run_document(
            job,
            model=model,
            use_user_config=use_user_config,
            status="failed",
            duration_seconds=duration_seconds,
            exit_code=completed_process.returncode,
            error="Codex process failed; inspect the criterion-scoped stderr artifact",
        )
        _write_json(job.run_path, run)
        return run
    try:
        validation = validate_agent_candidate(job, root=repository)
    except (KeyError, OSError, TypeError, ValueError) as error:
        run = _run_document(
            job,
            model=model,
            use_user_config=use_user_config,
            status="validationFailed",
            duration_seconds=duration_seconds,
            exit_code=completed_process.returncode,
            error=f"{type(error).__name__}: {error}",
        )
        _write_json(job.run_path, run)
        return run
    run = _run_document(
        job,
        model=model,
        use_user_config=use_user_config,
        status="completed",
        duration_seconds=duration_seconds,
        exit_code=completed_process.returncode,
        validation=validation,
    )
    run["codexVersion"] = _codex_version(Path(command[0]))
    run["eventSummary"] = cast("JsonValue", _codex_event_summary(job.events_path))
    _write_json(job.run_path, run)
    return run


def selected_agent_slugs(*, root: Path) -> tuple[str, ...]:
    """Select every extracted criterion in canonical manifest order."""

    manifest = load_yaml(root / "data/criteria-manifest.yaml")
    return tuple(
        cast("str", record["slug"])
        for record in (
            as_mapping(value, location="manifest.criteria[]")
            for value in as_sequence(manifest["criteria"], location="manifest.criteria")
        )
        if record.get("contentModel") == "extractedCriterion"
    )


def _requested_slugs(available: Sequence[str], requested: Sequence[str]) -> tuple[str, ...]:
    """Filter an optional allowlist without changing manifest order."""

    if not requested:
        return tuple(available)
    if len(requested) != len(set(requested)):
        message = "requested slugs must be unique"
        raise ValueError(message)
    unknown = sorted(set(requested).difference(available), key=str.encode)
    if unknown:
        message = f"requested slugs are not extracted criteria: {', '.join(unknown)}"
        raise ValueError(message)
    requested_set = set(requested)
    return tuple(slug for slug in available if slug in requested_set)


def run_agent_corpus(  # noqa: PLR0913
    *,
    slugs: Sequence[str] = (),
    root: Path | None = None,
    work_directory: Path | None = None,
    workers: int = DEFAULT_WORKERS,
    model: str | None = None,
    use_user_config: bool = False,
    resume: bool = False,
    dry_run: bool = False,
    runner: AgentRunner | None = None,
) -> dict[str, JsonValue]:
    """Run independent Codex-owned jobs with bounded thread scheduling."""

    if isinstance(workers, bool) or not 1 <= workers <= MAXIMUM_WORKERS:
        message = f"workers must be between 1 and {MAXIMUM_WORKERS}"
        raise ValueError(message)
    validate_model_routing(model=model, use_user_config=use_user_config)
    repository = (root or repository_root()).resolve()
    output_root = (work_directory or repository / DEFAULT_AGENT_WORK_DIRECTORY).resolve()
    available = selected_agent_slugs(root=repository)
    selected = _requested_slugs(available, slugs)
    started_at = time.perf_counter()
    jobs = [build_agent_job(slug, root=repository, work_directory=output_root) for slug in selected]
    execute = runner or (
        lambda job, selected_model, selected_user_config: run_agent_job(
            job,
            model=selected_model,
            use_user_config=selected_user_config,
            root=repository,
            resume=resume,
            dry_run=dry_run,
        )
    )
    results: dict[str, dict[str, JsonValue]] = {}
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="codex-agent") as executor:
        futures: dict[Future[dict[str, JsonValue]], AgentJob] = {
            executor.submit(execute, job, model, use_user_config): job for job in jobs
        }
        for future in as_completed(futures):
            job = futures[future]
            try:
                results[job.slug] = future.result()
            except Exception as error:  # noqa: BLE001
                results[job.slug] = _run_document(
                    job,
                    model=model,
                    use_user_config=use_user_config,
                    status="failed",
                    duration_seconds=0.0,
                    exit_code=None,
                    error=f"{type(error).__name__}: {error}",
                )
    ordered_results = [results[slug] for slug in selected]
    counts = {
        status: sum(result.get("status") == status for result in ordered_results)
        for status in ("completed", "skipped", "dryRun", "validationFailed", "failed")
    }
    summary_status = (
        "completedWithFailures"
        if counts["failed"] or counts["validationFailed"]
        else ("dryRun" if dry_run else "completed")
    )
    summary: dict[str, JsonValue] = {
        "schemaVersion": AGENT_SCHEMA_VERSION,
        "status": summary_status,
        "durationSeconds": round(max(0.0, time.perf_counter() - started_at), 6),
        "configuration": {
            "workers": workers,
            "model": model or "configured-default",
            "useUserConfig": use_user_config,
            "resume": resume,
            "dryRun": dry_run,
        },
        "counts": cast("JsonValue", counts),
        "items": cast("JsonValue", ordered_results),
    }
    _write_json(output_root / "summary.json", summary)
    return summary


def _worker_count(argument: str) -> int:
    """Parse the bounded concurrency value for the command line."""

    try:
        value = int(argument)
    except ValueError as error:
        message = "workers must be an integer"
        raise argparse.ArgumentTypeError(message) from error
    if not 1 <= value <= MAXIMUM_WORKERS:
        message = f"workers must be between 1 and {MAXIMUM_WORKERS}"
        raise argparse.ArgumentTypeError(message)
    return value


def _argument_parser() -> argparse.ArgumentParser:
    """Build the Codex-native corpus command-line parser."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slugs", nargs="*", help="optional extracted criterion allowlist")
    parser.add_argument("--work-directory", type=Path)
    parser.add_argument("--workers", type=_worker_count, default=DEFAULT_WORKERS)
    parser.add_argument("--model")
    parser.add_argument("--use-user-config", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    add_logging_arguments(parser)
    return parser


def main() -> int:
    """Run the complete Codex-native conversion command."""

    arguments = _argument_parser().parse_args()
    with configure_runtime_logging(
        "codex_agent_pipeline",
        level=arguments.log_level,
        log_directory=arguments.log_directory,
    ) as logger:
        logger.info(
            "Codex-native conversion started",
            event="command.started",
            item_count=len(arguments.slugs) if arguments.slugs else None,
            workers=arguments.workers,
            dry_run=arguments.dry_run,
            resume=arguments.resume,
        )
        try:
            summary = run_agent_corpus(
                slugs=arguments.slugs,
                work_directory=arguments.work_directory,
                workers=arguments.workers,
                model=arguments.model,
                use_user_config=arguments.use_user_config,
                resume=arguments.resume,
                dry_run=arguments.dry_run,
            )
        except (KeyError, OSError, TypeError, ValueError) as error:
            logger.exception(
                "Codex-native conversion failed",
                event="command.failed",
                error=error,
            )
            sys.stderr.write(f"{error}\n")
            return 1
        logger.info(
            "Codex-native conversion completed",
            event="command.completed",
            status=summary["status"],
            counts=summary["counts"],
        )
        sys.stdout.write(f"{summary['status']}\n")
        return 1 if summary["status"] == "completedWithFailures" else 0


if __name__ == "__main__":
    raise SystemExit(main())
