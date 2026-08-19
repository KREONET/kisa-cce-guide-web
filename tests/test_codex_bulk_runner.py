"""Regression tests for the bounded Codex bulk conversion runner."""

from __future__ import annotations

import inspect
import io
import json
import sys
import threading
from concurrent.futures import Executor, ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from conversion import codex_bulk_runner
from conversion.common import (
    JsonValue,
    as_mapping,
    as_sequence,
    repository_root,
    sha256_file,
)
from conversion.runtime_logging import LOG_DIRECTORY_ENVIRONMENT_VARIABLE, RuntimeLogger

if TYPE_CHECKING:
    from conversion.codex_bulk_runner import BulkItemRequest

CONCURRENCY_WAIT_SECONDS = 2.0
TEST_WORKER_COUNT = 2
BOUND_TEST_ITEM_COUNT = 6
ISOLATED_SUCCESS_COUNT = 2
CANCELLED_ITEM_COUNT = 2
MIXED_SUCCESS_COUNT = 3
DRY_RUN_ITEM_COUNT = 2
PIPELINE_STAGE_COUNT = 3


@pytest.fixture(autouse=True)
def _isolate_runtime_logs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep default runtime logs inside each test's temporary directory."""

    monkeypatch.setenv(LOG_DIRECTORY_ENVIRONMENT_VARIABLE, str(tmp_path / "logs"))


def _write_manifest(root: Path, criteria: list[tuple[str, str]]) -> None:
    """Write the smallest manifest needed to exercise bulk selection."""

    data_directory = root / "data"
    data_directory.mkdir(parents=True, exist_ok=True)
    document = {
        "criteria": [
            {"slug": slug, "contentModel": content_model} for slug, content_model in criteria
        ]
    }
    (data_directory / "criteria-manifest.yaml").write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    schema_directory = root / codex_bulk_runner.SUMMARY_SCHEMA_PATH.parent
    schema_directory.mkdir(parents=True, exist_ok=True)
    schema_path = repository_root() / codex_bulk_runner.SUMMARY_SCHEMA_PATH
    (root / codex_bulk_runner.SUMMARY_SCHEMA_PATH).write_bytes(schema_path.read_bytes())


def _worker_item(request: BulkItemRequest, *, outcome: str) -> dict[str, JsonValue]:
    """Build a schema-valid deterministic item returned by a fake worker."""

    path_prefix = f"work/{request.slug}"
    paths: dict[str, JsonValue] = {
        "task": f"{path_prefix}/task.json",
        "result": f"{path_prefix}/result.json",
        "run": f"{path_prefix}/run.json",
        "events": f"{path_prefix}/events.jsonl",
        "stderr": f"{path_prefix}/stderr.log",
        "candidate": f"{path_prefix}/candidate.md",
        "validation": f"{path_prefix}/validation.json",
    }
    stage_statuses = {
        "completed": ("completed", "completed"),
        "resumedImport": ("skipped", "completed"),
        "skipped": ("skipped", "skipped"),
        "dryRun": ("dryRun", "notRun"),
    }
    vision_status, importer_status = stage_statuses[outcome]
    stages: dict[str, JsonValue] = {
        "taskBuild": {
            "status": "completed",
            "durationSeconds": 0.0,
            "path": paths["task"],
        },
        "visionRun": {
            "status": vision_status,
            "durationSeconds": 0.0,
            "path": paths["result"],
        },
        "importer": {
            "status": importer_status,
            "durationSeconds": 0.0,
            "path": paths["candidate"],
        },
    }
    resume_verification = {
        "resumedImport": "verifiedResult",
        "skipped": "verifiedCandidate",
    }.get(outcome, "notRequested")
    return {
        "slug": request.slug,
        "outcome": outcome,
        "durationSeconds": 0.0,
        "resumeVerification": resume_verification,
        "paths": paths,
        "stages": stages,
        "error": None,
    }


def _summary_counts(summary: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """Return a narrowed summary count mapping for assertions."""

    return as_mapping(summary["counts"], location="summary.counts")


def _summary_items(summary: dict[str, JsonValue]) -> list[dict[str, JsonValue]]:
    """Return narrowed summary item mappings for assertions."""

    return [
        as_mapping(value, location="summary.items[]")
        for value in as_sequence(summary["items"], location="summary.items")
    ]


def _completed_worker(request: BulkItemRequest) -> dict[str, JsonValue]:
    """Return a minimal valid worker result without invoking Codex."""

    return _worker_item(request, outcome="completed")


def _read_log_records(log_directory: Path, pattern: str) -> list[dict[str, JsonValue]]:
    """Load every JSONL record matching one runtime log filename pattern."""

    records: list[dict[str, JsonValue]] = []
    for log_path in sorted(log_directory.glob(pattern)):
        records.extend(
            json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line
        )
    return records


def test_extracted_slug_selection_is_filtered_ordered_and_unique(tmp_path: Path) -> None:
    """Selection must ignore canonical items and preserve deterministic manifest order."""

    _write_manifest(
        tmp_path,
        [
            ("z-02", "extractedCriterion"),
            ("a-10", "systemCriterion"),
            ("a-02", "extractedCriterion"),
            ("a-01", "extractedCriterion"),
        ],
    )

    assert codex_bulk_runner.selected_extracted_criterion_slugs(root=tmp_path) == (
        "z-02",
        "a-02",
        "a-01",
    )

    observed_slugs: list[str] = []

    def selected_worker(request: BulkItemRequest) -> dict[str, JsonValue]:
        """Record the public allowlist order without invoking Codex."""

        observed_slugs.append(request.slug)
        return _worker_item(request, outcome="completed")

    codex_bulk_runner.run_bulk_conversion(
        slugs=["a-01", "z-02"],
        root=tmp_path,
        work_directory=tmp_path / "work",
        workers=1,
        executor_factory=ThreadPoolExecutor,
        worker_callable=selected_worker,
    )
    assert observed_slugs == ["z-02", "a-01"]

    _write_manifest(
        tmp_path,
        [
            ("a-01", "extractedCriterion"),
            ("a-01", "extractedCriterion"),
        ],
    )
    with pytest.raises(ValueError, match="duplicate extracted criterion slugs: a-01"):
        codex_bulk_runner.selected_extracted_criterion_slugs(root=tmp_path)


def test_executor_injection_enforces_the_worker_bound(tmp_path: Path) -> None:
    """The scheduler must never have more active tasks than requested workers."""

    _write_manifest(
        tmp_path,
        [(f"u-{index:02d}", "extractedCriterion") for index in range(3, 9)],
    )
    state_lock = threading.Lock()
    concurrent_workers_reached = threading.Event()
    active_workers = 0
    peak_workers = 0

    def measured_worker(request: BulkItemRequest) -> dict[str, JsonValue]:
        """Hold the first worker until a second worker proves concurrency."""

        nonlocal active_workers, peak_workers
        with state_lock:
            active_workers += 1
            peak_workers = max(peak_workers, active_workers)
            if active_workers == TEST_WORKER_COUNT:
                concurrent_workers_reached.set()
        try:
            assert concurrent_workers_reached.wait(CONCURRENCY_WAIT_SECONDS)
            return _worker_item(request, outcome="completed")
        finally:
            with state_lock:
                active_workers -= 1

    summary = codex_bulk_runner.run_bulk_conversion(
        root=tmp_path,
        work_directory=tmp_path / "work",
        workers=TEST_WORKER_COUNT,
        executor_factory=ThreadPoolExecutor,
        worker_callable=measured_worker,
    )

    assert peak_workers == TEST_WORKER_COUNT
    assert summary["status"] == "completed"
    assert _summary_counts(summary)["completed"] == BOUND_TEST_ITEM_COUNT


def test_worker_failure_is_isolated_when_fail_fast_is_disabled(tmp_path: Path) -> None:
    """One broken worker must not prevent unrelated criteria from completing."""

    _write_manifest(
        tmp_path,
        [
            ("u-03", "extractedCriterion"),
            ("u-04", "extractedCriterion"),
            ("u-05", "extractedCriterion"),
        ],
    )

    def partly_failing_worker(request: BulkItemRequest) -> dict[str, JsonValue]:
        """Raise only for the middle criterion."""

        if request.slug == "u-04":
            message = "fixture failure"
            raise RuntimeError(message)
        return _worker_item(request, outcome="completed")

    summary = codex_bulk_runner.run_bulk_conversion(
        root=tmp_path,
        work_directory=tmp_path / "work",
        workers=TEST_WORKER_COUNT,
        executor_factory=ThreadPoolExecutor,
        worker_callable=partly_failing_worker,
    )

    assert summary["status"] == "completedWithFailures"
    counts = _summary_counts(summary)
    assert counts["completed"] == ISOLATED_SUCCESS_COUNT
    assert counts["failed"] == 1
    items = {item["slug"]: item for item in _summary_items(summary)}
    assert items["u-03"]["outcome"] == "completed"
    assert items["u-05"]["outcome"] == "completed"
    assert items["u-04"]["error"] == {
        "stage": "workerProcess",
        "type": "RuntimeError",
        "message": "fixture failure",
    }


def test_fail_fast_stops_submitting_after_the_first_failure(tmp_path: Path) -> None:
    """Fail-fast must cancel every item not yet submitted to the executor."""

    _write_manifest(
        tmp_path,
        [
            ("u-03", "extractedCriterion"),
            ("u-04", "extractedCriterion"),
            ("u-05", "extractedCriterion"),
        ],
    )
    called_slugs: list[str] = []

    def first_worker_fails(request: BulkItemRequest) -> dict[str, JsonValue]:
        """Record execution before raising on the first sorted item."""

        called_slugs.append(request.slug)
        message = "stop here"
        raise RuntimeError(message)

    summary = codex_bulk_runner.run_bulk_conversion(
        root=tmp_path,
        work_directory=tmp_path / "work",
        workers=1,
        fail_fast=True,
        executor_factory=ThreadPoolExecutor,
        worker_callable=first_worker_fails,
    )

    assert called_slugs == ["u-03"]
    assert summary["status"] == "failedFast"
    counts = _summary_counts(summary)
    assert counts["failed"] == 1
    assert counts["cancelled"] == CANCELLED_ITEM_COUNT
    assert [item["outcome"] for item in _summary_items(summary)] == [
        "failed",
        "cancelled",
        "cancelled",
    ]


def test_resume_reuses_only_current_validated_artifacts(  # noqa: PLR0915
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resume must distinguish a verified candidate, result, and stale result."""

    slug = "u-03"
    expected_work_directory = tmp_path / "work"
    task_path = expected_work_directory / "tasks" / slug / "task.json"
    result_path = expected_work_directory / "results" / slug / "result.json"
    candidate_path = expected_work_directory / "candidates" / slug / "candidate.md"
    validation_path = expected_work_directory / "candidates" / slug / "validation.json"
    for path in (task_path, result_path, candidate_path, validation_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    task_document = {"taskIdentifier": "u-03-task", "taskChecksum": "current-task"}
    task_path.write_text(json.dumps(task_document) + "\n", encoding="utf-8")
    result_path.write_text('{"result": "current"}\n', encoding="utf-8")
    candidate_path.write_text("# Candidate\n", encoding="utf-8")
    validation_document = {
        "schemaVersion": 2,
        "taskIdentifier": task_document["taskIdentifier"],
        "taskChecksum": task_document["taskChecksum"],
        "resultChecksum": sha256_file(result_path),
        "candidateChecksum": sha256_file(candidate_path),
        "validationStatus": "passed",
        "canonicalApplied": False,
    }
    validation_path.write_text(
        json.dumps(validation_document, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_manifest(tmp_path, [(slug, "extractedCriterion")])
    calls = {"vision": 0, "importer": 0}

    def fake_build_task(
        _slug: str,
        *,
        root: Path,
        work_directory: Path,
    ) -> Path:
        """Preserve the current task fixture as a deterministic rebuild."""

        assert root == tmp_path
        assert work_directory == expected_work_directory.resolve()
        return task_path

    def accept_result(
        _result_path: Path,
        _task_path: Path,
        *,
        root: Path,
    ) -> dict[str, JsonValue]:
        """Represent a schema-valid result without loading production fixtures."""

        assert root == tmp_path
        return {}

    def fake_run_task(
        _slug: str,
        *,
        root: Path,
        work_directory: Path,
        model: str | None,
        dry_run: bool,
        runtime_logger: RuntimeLogger | None,
    ) -> Path:
        """Record when stale result validation requires a new vision run."""

        assert root == tmp_path
        assert work_directory == expected_work_directory.resolve()
        assert model is None
        assert not dry_run
        assert runtime_logger is not None
        assert runtime_logger.tool_name == "codex_bulk_worker"
        calls["vision"] += 1
        return result_path

    def fake_render_candidate(
        _result_path: Path,
        _task_path: Path,
        *,
        root: Path,
        work_directory: Path,
    ) -> Path:
        """Record when a current result requires importer execution."""

        assert root == tmp_path
        assert work_directory == expected_work_directory.resolve()
        calls["importer"] += 1
        return candidate_path

    monkeypatch.setattr(codex_bulk_runner, "build_codex_task", fake_build_task)
    monkeypatch.setattr(codex_bulk_runner, "validate_codex_result", accept_result)
    monkeypatch.setattr(codex_bulk_runner, "run_codex_task", fake_run_task)
    monkeypatch.setattr(codex_bulk_runner, "render_codex_candidate", fake_render_candidate)

    def run_resumed_conversion() -> dict[str, JsonValue]:
        """Execute the public runner with the in-process production worker."""

        return codex_bulk_runner.run_bulk_conversion(
            root=tmp_path,
            work_directory=expected_work_directory,
            workers=1,
            resume=True,
            executor_factory=ThreadPoolExecutor,
            worker_callable=codex_bulk_runner._process_item,  # noqa: SLF001
        )

    verified_summary = run_resumed_conversion()
    verified_item = _summary_items(verified_summary)[0]
    assert verified_item["outcome"] == "skipped"
    assert verified_item["resumeVerification"] == "verifiedCandidate"
    assert calls == {"vision": 0, "importer": 0}

    validation_document["taskChecksum"] = "stale-task"
    validation_path.write_text(
        json.dumps(validation_document, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    result_only_summary = run_resumed_conversion()
    result_only_item = _summary_items(result_only_summary)[0]
    assert result_only_item["outcome"] == "resumedImport"
    assert result_only_item["resumeVerification"] == "verifiedResult"
    assert calls == {"vision": 0, "importer": 1}

    def reject_result(
        _result_path: Path,
        _task_path: Path,
        *,
        root: Path,
    ) -> dict[str, JsonValue]:
        """Represent a result that no longer validates for the rebuilt task."""

        assert root == tmp_path
        message = "stale result"
        raise ValueError(message)

    monkeypatch.setattr(codex_bulk_runner, "validate_codex_result", reject_result)
    stale_summary = run_resumed_conversion()
    stale_item = _summary_items(stale_summary)[0]
    assert stale_item["outcome"] == "completed"
    assert stale_item["resumeVerification"] == "none"
    assert calls == {"vision": 1, "importer": 2}


def test_summary_manifest_is_deterministic_and_status_is_derived(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stable inputs and outcomes must produce identical ordered summary bytes."""

    _write_manifest(
        tmp_path,
        [
            ("z-01", "extractedCriterion"),
            ("a-01", "extractedCriterion"),
            ("m-01", "extractedCriterion"),
        ],
    )
    outcomes = {"a-01": "completed", "m-01": "resumedImport", "z-01": "skipped"}

    def mixed_success_worker(request: BulkItemRequest) -> dict[str, JsonValue]:
        """Return each successful terminal outcome once."""

        return _worker_item(request, outcome=outcomes[request.slug])

    monkeypatch.setattr(codex_bulk_runner, "_duration_seconds", lambda _started_at: 0.0)
    first_summary = codex_bulk_runner.run_bulk_conversion(
        root=tmp_path,
        work_directory=tmp_path / "work",
        workers=TEST_WORKER_COUNT,
        executor_factory=ThreadPoolExecutor,
        worker_callable=mixed_success_worker,
    )
    summary_path = tmp_path / "work" / codex_bulk_runner.SUMMARY_FILENAME
    first_bytes = summary_path.read_bytes()
    second_summary = codex_bulk_runner.run_bulk_conversion(
        root=tmp_path,
        work_directory=tmp_path / "work",
        workers=TEST_WORKER_COUNT,
        executor_factory=ThreadPoolExecutor,
        worker_callable=mixed_success_worker,
    )

    assert summary_path.read_bytes() == first_bytes
    assert first_summary == second_summary
    assert second_summary["status"] == "completed"
    assert _summary_counts(second_summary)["successful"] == MIXED_SUCCESS_COUNT
    assert [item["slug"] for item in _summary_items(second_summary)] == [
        "z-01",
        "a-01",
        "m-01",
    ]
    assert json.loads(first_bytes) == second_summary


def test_dry_run_is_forwarded_without_invoking_codex(tmp_path: Path) -> None:
    """Every dry-run request must remain a plan-only item in the summary."""

    _write_manifest(
        tmp_path,
        [
            ("u-03", "extractedCriterion"),
            ("u-04", "extractedCriterion"),
        ],
    )
    observed_requests: list[BulkItemRequest] = []

    def dry_run_worker(request: BulkItemRequest) -> dict[str, JsonValue]:
        """Verify dry-run propagation without executing the production worker."""

        observed_requests.append(request)
        assert request.dry_run
        return _worker_item(request, outcome="dryRun")

    summary = codex_bulk_runner.run_bulk_conversion(
        root=tmp_path,
        work_directory=tmp_path / "work",
        workers=1,
        dry_run=True,
        executor_factory=ThreadPoolExecutor,
        worker_callable=dry_run_worker,
    )

    assert [request.slug for request in observed_requests] == ["u-03", "u-04"]
    assert summary["status"] == "dryRun"
    counts = _summary_counts(summary)
    assert counts["dryRun"] == DRY_RUN_ITEM_COUNT
    assert counts["completed"] == 0


def test_process_pool_executor_is_the_production_default() -> None:
    """Normal invocations must isolate workers in bounded child processes."""

    signature = inspect.signature(codex_bulk_runner.run_bulk_conversion)
    assert signature.parameters["executor_factory"].default is ProcessPoolExecutor


@pytest.mark.parametrize("workers", [0, codex_bulk_runner.MAXIMUM_WORKERS + 1, True])
def test_workers_outside_the_hard_bound_are_rejected(
    tmp_path: Path,
    workers: int,
) -> None:
    """Invalid worker counts must fail before the manifest or executor is touched."""

    def unexpected_executor_factory(*, max_workers: int) -> Executor:
        """Fail if invalid configuration reaches executor construction."""

        pytest.fail(f"executor unexpectedly created with {max_workers} workers")

    with pytest.raises(
        ValueError,
        match=rf"workers must be between 1 and {codex_bulk_runner.MAXIMUM_WORKERS}",
    ):
        codex_bulk_runner.run_bulk_conversion(
            root=tmp_path,
            workers=workers,
            executor_factory=unexpected_executor_factory,
            worker_callable=_completed_worker,
        )


def test_parent_progress_reports_every_terminal_outcome_without_stdout(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Non-TTY progress must advance once per item and never write to stdout."""

    _write_manifest(
        tmp_path,
        [
            ("u-03", "extractedCriterion"),
            ("u-04", "extractedCriterion"),
            ("u-05", "extractedCriterion"),
        ],
    )
    outcomes = {"u-03": "completed", "u-04": "dryRun", "u-05": "skipped"}

    def terminal_outcome_worker(request: BulkItemRequest) -> dict[str, JsonValue]:
        """Return one deterministic terminal outcome for each selected item."""

        return _worker_item(request, outcome=outcomes[request.slug])

    summary = codex_bulk_runner.run_bulk_conversion(
        root=tmp_path,
        work_directory=tmp_path / "work",
        workers=1,
        log_directory=tmp_path / "logs",
        executor_factory=ThreadPoolExecutor,
        worker_callable=terminal_outcome_worker,
    )

    captured = capsys.readouterr()
    progress_lines = [
        line for line in captured.err.splitlines() if line.startswith("Codex bulk conversion ")
    ]
    assert captured.out == ""
    assert [line.split()[3] for line in progress_lines[:3]] == ["1/3", "2/3", "3/3"]
    assert "completed:1" in progress_lines[0]
    assert "dryRun:1" in progress_lines[1]
    assert "skipped:1" in progress_lines[2]
    configuration = as_mapping(summary["configuration"], location="summary.configuration")
    assert configuration["progressEnabled"] is True


def test_progress_can_be_disabled_and_runtime_configuration_remains_valid(
    tmp_path: Path,
) -> None:
    """The opt-out must suppress progress and remain represented in the summary schema."""

    _write_manifest(tmp_path, [("u-03", "extractedCriterion")])
    progress_stream = io.StringIO()
    summary = codex_bulk_runner.run_bulk_conversion(
        root=tmp_path,
        work_directory=tmp_path / "work",
        workers=1,
        progress_enabled=False,
        progress_stream=progress_stream,
        log_directory=tmp_path / "custom-logs",
        log_level="debug",
        executor_factory=ThreadPoolExecutor,
        worker_callable=_completed_worker,
    )

    assert progress_stream.getvalue() == ""
    configuration = as_mapping(summary["configuration"], location="summary.configuration")
    assert configuration["logDirectory"] == "custom-logs"
    assert configuration["logLevel"] == "DEBUG"
    assert configuration["progressEnabled"] is False
    codex_bulk_runner.validate_bulk_summary(summary, root=tmp_path)


def test_parent_log_captures_scheduler_lifecycle_and_failure_events(
    tmp_path: Path,
) -> None:
    """Parent logs must explain submission, outcome, fail-fast, and summary state."""

    _write_manifest(
        tmp_path,
        [
            ("u-03", "extractedCriterion"),
            ("u-04", "extractedCriterion"),
        ],
    )
    log_directory = tmp_path / "logs"

    def failing_worker(_request: BulkItemRequest) -> dict[str, JsonValue]:
        """Raise immediately so the parent records a worker-process failure."""

        message = "logged fixture failure"
        raise RuntimeError(message)

    summary = codex_bulk_runner.run_bulk_conversion(
        root=tmp_path,
        work_directory=tmp_path / "work",
        workers=1,
        fail_fast=True,
        progress_enabled=False,
        log_directory=log_directory,
        executor_factory=ThreadPoolExecutor,
        worker_callable=failing_worker,
    )

    records = _read_log_records(log_directory, "codex_bulk_runner-*.jsonl")
    events = [record["event"] for record in records]
    assert events[0:2] == ["command.started", "bulk.configuration"]
    assert {
        "item.submitted",
        "item.completed",
        "item.outcome",
        "item.failed",
        "scheduler.fail_fast",
        "summary.written",
        "command.completed",
    }.issubset(events)
    summary_record = next(record for record in records if record["event"] == "summary.written")
    summary_context = as_mapping(summary_record["context"], location="log.context")
    assert summary_context["counts"] == summary["counts"]
    assert summary_context["summary_path"] == str(tmp_path / "work" / "bulk-summary.json")


def test_worker_log_is_isolated_and_records_pipeline_stages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The production worker must write item and stage events to its own JSONL log."""

    slug = "u-03"
    work_directory = tmp_path / "work"
    task_path = work_directory / "tasks" / slug / "task.json"
    result_path = work_directory / "results" / slug / "result.json"
    candidate_path = work_directory / "candidates" / slug / "candidate.md"
    log_directory = tmp_path / "logs"

    def fake_build_task(
        _slug: str,
        *,
        root: Path,
        work_directory: Path,
    ) -> Path:
        """Return the worker-owned task path without exercising task generation."""

        assert root == tmp_path
        assert work_directory == tmp_path / "work"
        return task_path

    def fake_run_task(
        _slug: str,
        *,
        root: Path,
        work_directory: Path,
        model: str | None,
        dry_run: bool,
        runtime_logger: RuntimeLogger | None,
    ) -> Path:
        """Return the worker-owned result path without invoking Codex."""

        assert root == tmp_path
        assert work_directory == tmp_path / "work"
        assert model is None
        assert not dry_run
        assert runtime_logger is not None
        assert runtime_logger.tool_name == "codex_bulk_worker"
        return result_path

    def fake_render_candidate(
        _result_path: Path,
        _task_path: Path,
        *,
        root: Path,
        work_directory: Path,
    ) -> Path:
        """Return the worker-owned candidate path without importing content."""

        assert root == tmp_path
        assert work_directory == tmp_path / "work"
        return candidate_path

    monkeypatch.setattr(codex_bulk_runner, "build_codex_task", fake_build_task)
    monkeypatch.setattr(codex_bulk_runner, "run_codex_task", fake_run_task)
    monkeypatch.setattr(codex_bulk_runner, "render_codex_candidate", fake_render_candidate)
    request = codex_bulk_runner.BulkItemRequest(
        slug=slug,
        repository=tmp_path.as_posix(),
        work_directory=work_directory.as_posix(),
        model=None,
        dry_run=False,
        resume=False,
        retries=0,
        retry_backoff_seconds=0.0,
        log_directory=log_directory.as_posix(),
        log_level="DEBUG",
        log_run_identifier="isolated-worker-test",
    )

    result = codex_bulk_runner._process_item(request)  # noqa: SLF001

    assert result["outcome"] == "completed"
    records = _read_log_records(log_directory, "codex_bulk_worker-*.jsonl")
    events = [record["event"] for record in records]
    assert events[0] == "item.started"
    assert events.count("stage.started") == PIPELINE_STAGE_COUNT
    assert events.count("stage.completed") == PIPELINE_STAGE_COUNT
    assert events[-2:] == ["item.completed", "item.outcome"]
    assert not list(log_directory.glob("codex_bulk_runner-*.jsonl"))


def test_main_forwards_progress_and_logging_options_without_changing_stdout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The CLI must preserve the one-line summary path contract on stdout."""

    observed_arguments: dict[str, object] = {}

    def fake_bulk_conversion(**arguments: object) -> dict[str, JsonValue]:
        """Capture CLI forwarding and return the minimal result consumed by main."""

        observed_arguments.update(arguments)
        return {
            "summaryPath": "work/codex/bulk-summary.json",
            "status": "completed",
            "counts": {"failed": 0, "cancelled": 0},
        }

    log_directory = tmp_path / "cli-logs"
    monkeypatch.setattr(codex_bulk_runner, "run_bulk_conversion", fake_bulk_conversion)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "codex_bulk_runner.py",
            "--no-progress",
            "--log-directory",
            str(log_directory),
            "--log-level",
            "debug",
        ],
    )

    exit_code = codex_bulk_runner.main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == "work/codex/bulk-summary.json\n"
    assert captured.err == ""
    assert observed_arguments["progress_enabled"] is False
    assert observed_arguments["log_directory"] == log_directory
    assert observed_arguments["log_level"] == "DEBUG"
