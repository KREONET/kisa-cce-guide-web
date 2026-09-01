"""Regression tests for the Codex-native criterion conversion pipeline."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest

from conversion import codex_agent_pipeline
from conversion.common import JsonValue, as_mapping, as_sequence, repository_root, sha256_file
from conversion.paths import criterion_directory
from tests.codex_transition_fixtures import create_codex_transition_repository

EXPECTED_U_03_PAGE_COUNT = 4
SELECTED_TEST_SLUG_COUNT = 3


@pytest.fixture(scope="module", autouse=True)
def _codex_transition_repository(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[None]:
    """Route agent pipeline tests through isolated extracted U-03 to U-05 packages."""

    source = repository_root()
    repository = create_codex_transition_repository(
        source,
        tmp_path_factory.mktemp("codex-agent-transition") / "repository",
        slugs=("u-03", "u-04", "u-05"),
    )
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(codex_agent_pipeline, "repository_root", lambda: repository)
    monkeypatch.setitem(globals(), "repository_root", lambda: repository)
    yield
    monkeypatch.undo()


def _workspace_files(job: codex_agent_pipeline.AgentJob) -> set[str]:
    """Return every regular file in one generated agent workspace."""

    return {
        path.relative_to(job.workspace).as_posix()
        for path in job.workspace.rglob("*")
        if path.is_file()
    }


def _write_status(
    job: codex_agent_pipeline.AgentJob,
    *,
    task_checksum: str | None = None,
    analysis_status: str = "complete",
) -> None:
    """Write the smallest complete status record for one generated job."""

    reviewed_pages = [
        as_mapping(value, location="task.evidence[]")["physicalPage"]
        for value in as_sequence(job.task["evidence"], location="task.evidence")
    ]
    status = {
        "schemaVersion": 1,
        "taskIdentifier": job.task["taskIdentifier"],
        "taskChecksum": task_checksum or job.task["taskChecksum"],
        "status": "candidateWritten",
        "analysisStatus": analysis_status,
        "reviewedPhysicalPages": reviewed_pages,
        "unresolvedQuestions": [],
    }
    job.status_path.write_text(
        json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_job_generation_is_deterministic_and_content_addressed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stable semantic inputs must reuse one compact checksum-addressed workspace."""

    root = repository_root()
    work_directory = tmp_path / "agent-work"
    first_job = codex_agent_pipeline.build_agent_job(
        "u-03",
        root=root,
        work_directory=work_directory,
    )
    first_task_bytes = first_job.task_path.read_bytes()
    second_job = codex_agent_pipeline.build_agent_job(
        "u-03",
        root=root,
        work_directory=work_directory,
    )

    assert second_job.job_directory == first_job.job_directory
    assert second_job.task_path.read_bytes() == first_task_bytes
    assert first_job.job_directory == (
        work_directory.resolve() / "jobs" / "u-03" / cast("str", first_job.task["taskChecksum"])
    )
    expected_inputs = set(
        as_mapping(
            first_job.task["workspaceInputChecksums"],
            location="task.workspaceInputChecksums",
        )
    )
    assert _workspace_files(first_job) == expected_inputs | {
        "task.json",
        "validate_candidate.py",
    }
    assert len(as_sequence(first_job.task["evidence"], location="task.evidence")) == (
        EXPECTED_U_03_PAGE_COUNT
    )

    monkeypatch.setattr(
        codex_agent_pipeline,
        "criterion_source_checksum",
        lambda *_arguments, **_keywords: "f" * 64,
    )
    changed_job = codex_agent_pipeline.build_agent_job(
        "u-03",
        root=root,
        work_directory=work_directory,
    )
    assert changed_job.task["taskChecksum"] != first_job.task["taskChecksum"]
    assert changed_job.job_directory != first_job.job_directory


def test_agent_command_is_compact_and_workspace_scoped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The command must expose only the isolated writable workspace and its evidence."""

    job = codex_agent_pipeline.build_agent_job(
        "u-03",
        root=repository_root(),
        work_directory=tmp_path / "agent-work",
    )
    codex_binary = Path("/usr/bin/codex-test")
    monkeypatch.setattr(codex_agent_pipeline, "_codex_binary", lambda: codex_binary)

    command = codex_agent_pipeline.build_agent_command(
        job,
        model="native-test-model",
        use_user_config=False,
    )

    assert command[:4] == [
        str(codex_binary),
        "exec",
        "--ephemeral",
        "--ignore-user-config",
    ]
    sandbox_index = command.index("--sandbox")
    assert command[sandbox_index : sandbox_index + 2] == ["--sandbox", "workspace-write"]
    directory_index = command.index("--cd")
    assert command[directory_index : directory_index + 2] == [
        "--cd",
        str(job.workspace.resolve()),
    ]
    assert command[command.index("--output-schema") + 1] == str(
        (job.workspace / "status.schema.json").resolve()
    )
    assert command[command.index("--output-last-message") + 1] == str(job.status_path.resolve())
    assert command.count("--image") == EXPECTED_U_03_PAGE_COUNT
    command_text = "\n".join(command)
    assert "CONVERSION_POLICY.md" not in command_text
    assert "codex-criterion-result.schema.json" not in command_text
    for image_index, value in enumerate(command):
        if value == "--image":
            assert Path(command[image_index + 1]).is_relative_to(job.workspace)


def test_corpus_schedules_requested_slugs_in_manifest_order_with_fake_runner(
    tmp_path: Path,
) -> None:
    """An allowlist must not replace canonical manifest order during scheduling."""

    observed_slugs: list[str] = []

    def fake_runner(
        job: codex_agent_pipeline.AgentJob,
        model: str | None,
        use_user_config: bool,  # noqa: FBT001
    ) -> dict[str, JsonValue]:
        """Record deterministic single-worker submission without invoking Codex."""

        assert model == "native-test-model"
        assert use_user_config is False
        observed_slugs.append(job.slug)
        return {
            "schemaVersion": 1,
            "taskIdentifier": job.task["taskIdentifier"],
            "taskChecksum": job.task["taskChecksum"],
            "slug": job.slug,
            "status": "completed",
            "model": model,
            "userConfigLoaded": use_user_config,
            "durationSeconds": 0.0,
            "exitCode": 0,
        }

    summary = codex_agent_pipeline.run_agent_corpus(
        slugs=("u-05", "u-03", "u-04"),
        root=repository_root(),
        work_directory=tmp_path / "agent-work",
        workers=1,
        model="native-test-model",
        runner=fake_runner,
    )

    expected_order = ["u-03", "u-04", "u-05"]
    assert observed_slugs == expected_order
    items = [
        as_mapping(value, location="summary.items[]")
        for value in as_sequence(summary["items"], location="summary.items")
    ]
    assert [item["slug"] for item in items] == expected_order
    counts = as_mapping(summary["counts"], location="summary.counts")
    assert counts["completed"] == SELECTED_TEST_SLUG_COUNT
    assert summary["status"] == "completed"


def test_status_and_immutable_workspace_mutations_are_rejected(tmp_path: Path) -> None:
    """Status bindings and copied inputs must fail closed when either changes."""

    root = repository_root()
    job = codex_agent_pipeline.build_agent_job(
        "u-03",
        root=root,
        work_directory=tmp_path / "agent-work",
    )
    _write_status(job, task_checksum="0" * 64)
    with pytest.raises(ValueError, match="status task checksum differs"):
        codex_agent_pipeline._validate_status(job, root=root)  # noqa: SLF001

    _write_status(job)
    job.criterion_path.write_text("candidate\n", encoding="utf-8")
    job.provenance_path.write_text("provenance\n", encoding="utf-8")
    immutable_input = job.workspace / "contract.md"
    immutable_input.write_text(
        immutable_input.read_text(encoding="utf-8") + "\nmutation\n",
        encoding="utf-8",
    )
    with pytest.raises(
        ValueError,
        match=r"immutable workspace input changed: contract\.md",
    ):
        codex_agent_pipeline._validate_workspace_boundary(job, root=root)  # noqa: SLF001


def _canonical_candidate_job(tmp_path: Path) -> tuple[codex_agent_pipeline.AgentJob, Path, Path]:
    """Build a complete checksum-bound canonical package for validator tests."""

    root = repository_root()
    source_criterion = criterion_directory(root, "unix") / "u-01.md"
    source_provenance = criterion_directory(root, "unix") / "u-01.provenance.yaml"
    job_directory = tmp_path / "jobs" / "u-01" / "isolated-success"
    workspace = job_directory / "workspace"
    output_directory = workspace / "output"
    output_directory.mkdir(parents=True)

    immutable_sources = {
        "contract.md": root / codex_agent_pipeline.AGENT_CONTRACT_PATH,
        "status.schema.json": root / codex_agent_pipeline.AGENT_STATUS_SCHEMA_PATH,
        "input/criterion.md": source_criterion,
        "input/provenance.yaml": source_provenance,
        "reference/criterion.md": source_criterion,
        "reference/provenance.yaml": source_provenance,
    }
    workspace_input_checksums: dict[str, JsonValue] = {}
    for relative_path, source_path in immutable_sources.items():
        destination = workspace / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source_path.read_bytes())
        workspace_input_checksums[relative_path] = sha256_file(destination)

    task: dict[str, JsonValue] = {
        "schemaVersion": 1,
        "taskIdentifier": "u-01-codex-agent-v1-isolated-success",
        "taskChecksum": "0" * 64,
        "criterion": {
            "code": "U-01",
            "slug": "u-01",
            "title": "root 계정 원격 접속 제한",
            "severity": {"level": "high", "sourceLabel": "상"},
            "domainIdentifier": "unix",
            "categoryIdentifier": "unix-account-management",
            "expectedContentModel": "systemCriterion",
        },
        "source": {
            "sourceDocumentIdentifier": "kisa-cce-criteria-2026",
            "sourcePageRange": {
                "physicalPageStart": 12,
                "physicalPageEnd": 14,
                "printedPageStart": "12",
                "printedPageEnd": "14",
            },
        },
        "evidence": [
            {"physicalPage": 12, "pageRegionIdentifier": "p12-u-01"},
            {"physicalPage": 13, "pageRegionIdentifier": "p13-u-01"},
            {"physicalPage": 14, "pageRegionIdentifier": "p14-u-01"},
        ],
        "requiredTechnicalLiterals": [],
        "workspaceInputChecksums": workspace_input_checksums,
    }
    task["taskChecksum"] = codex_agent_pipeline._task_checksum(task)  # noqa: SLF001
    task_path = workspace / "task.json"
    task_path.write_text(
        json.dumps(task, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    validator_path = workspace / "validate_candidate.py"
    validator_path.write_text(
        codex_agent_pipeline._workspace_validator_source(root),  # noqa: SLF001
        encoding="utf-8",
    )
    criterion_path = output_directory / "criterion.md"
    provenance_path = output_directory / "provenance.yaml"
    criterion_path.write_bytes(source_criterion.read_bytes())
    provenance_path.write_bytes(source_provenance.read_bytes())
    job = codex_agent_pipeline.AgentJob(
        slug="u-01",
        task=task,
        job_directory=job_directory,
        workspace=workspace,
        task_path=task_path,
        status_path=output_directory / "status.json",
        criterion_path=criterion_path,
        provenance_path=provenance_path,
        events_path=job_directory / "events.jsonl",
        stderr_path=job_directory / "stderr.log",
        run_path=job_directory / "run.json",
    )
    _write_status(job, analysis_status="needsSourceReview")

    return job, source_criterion, source_provenance


def test_validate_agent_candidate_accepts_a_canonical_isolated_package(tmp_path: Path) -> None:
    """The production validator must accept a complete checksum-bound canonical package."""

    job, source_criterion, source_provenance = _canonical_candidate_job(tmp_path)
    task = job.task

    validation = codex_agent_pipeline.validate_agent_candidate(job, root=repository_root())

    assert validation == {
        "schemaVersion": 1,
        "taskIdentifier": task["taskIdentifier"],
        "taskChecksum": task["taskChecksum"],
        "analysisStatus": "needsSourceReview",
        "criterionChecksum": sha256_file(source_criterion),
        "provenanceChecksum": sha256_file(source_provenance),
        "statusChecksum": sha256_file(job.status_path),
        "validationStatus": "passed",
        "canonicalApplied": False,
    }


def test_candidate_validation_rejects_an_unsupported_vision_run(tmp_path: Path) -> None:
    """A successful process cannot pass when its stderr reports no image-input support."""

    job, _source_criterion, _source_provenance = _canonical_candidate_job(tmp_path)
    job.stderr_path.write_text(
        f"tool error: {codex_agent_pipeline.UNSUPPORTED_VISION_ERROR}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="does not support required image inputs"):
        codex_agent_pipeline.validate_agent_candidate(job, root=repository_root())


def test_candidate_validation_rejects_an_unknown_annotation_target(tmp_path: Path) -> None:
    """A schema-valid annotation must still reference a generated candidate block."""

    job, _source_criterion, _source_provenance = _canonical_candidate_job(tmp_path)
    source = job.criterion_path.read_text(encoding="utf-8")
    job.criterion_path.write_text(
        source.replace(
            'targetReference: "u-01:remediation.hp-ux.telnet.step:1"',
            'targetReference: "u-01:unknown.paragraph:1"',
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="annotation references an unknown AST target"):
        codex_agent_pipeline.validate_agent_candidate(job, root=repository_root())


def test_resume_revalidates_vision_capability_before_skipping(tmp_path: Path) -> None:
    """Resume must rerun a previously valid candidate after an unsupported-vision error."""

    job, _source_criterion, _source_provenance = _canonical_candidate_job(tmp_path)
    root = repository_root()
    validation = codex_agent_pipeline.validate_agent_candidate(job, root=root)
    run = {
        "schemaVersion": 1,
        "taskIdentifier": job.task["taskIdentifier"],
        "taskChecksum": job.task["taskChecksum"],
        "slug": job.slug,
        "status": "completed",
        "model": "native-test-model",
        "userConfigLoaded": False,
        "durationSeconds": 0.0,
        "exitCode": 0,
        "validation": validation,
    }
    job.run_path.write_text(
        json.dumps(run, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    job.stderr_path.write_text(
        codex_agent_pipeline.UNSUPPORTED_VISION_ERROR,
        encoding="utf-8",
    )

    assert (
        codex_agent_pipeline._resume_validation(  # noqa: SLF001
            job,
            root=root,
            model="native-test-model",
            use_user_config=False,
        )
        is None
    )


def test_corpus_dry_run_never_starts_live_codex(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dry-run planning must produce a summary without starting a Codex process."""

    def unexpected_subprocess(*_arguments: object, **_keywords: object) -> object:
        """Fail if dry-run execution reaches the subprocess boundary."""

        pytest.fail("dry-run unexpectedly started Codex")

    monkeypatch.setattr(codex_agent_pipeline, "_codex_binary", lambda: Path("/usr/bin/codex-test"))
    monkeypatch.setattr(codex_agent_pipeline.subprocess, "run", unexpected_subprocess)
    work_directory = tmp_path / "agent-work"

    summary = codex_agent_pipeline.run_agent_corpus(
        slugs=("u-03",),
        root=repository_root(),
        work_directory=work_directory,
        workers=1,
        model="native-test-model",
        dry_run=True,
    )

    assert summary["status"] == "dryRun"
    items = as_sequence(summary["items"], location="summary.items")
    item = as_mapping(items[0], location="summary.items[0]")
    assert item["status"] == "dryRun"
    assert item["exitCode"] is None
    job_directories = list((work_directory / "jobs" / "u-03").iterdir())
    assert len(job_directories) == 1
    assert not (job_directories[0] / "events.jsonl").exists()
    assert not (job_directories[0] / "stderr.log").exists()
    assert not (job_directories[0] / "run.json").exists()
