"""Run every extracted criterion through the Codex pipeline in bounded parallelism."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
import time
from collections import deque
from collections.abc import Callable, Sequence
from concurrent.futures import FIRST_COMPLETED, Executor, Future, ProcessPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from jsonschema import Draft202012Validator, FormatChecker

from conversion.codex_result_importer import render_codex_candidate, validate_codex_result
from conversion.codex_runner import run_codex_task
from conversion.codex_task_builder import DEFAULT_WORK_DIRECTORY, build_codex_task
from conversion.common import JsonValue, as_mapping, as_sequence, load_json, load_yaml, sha256_file
from conversion.common import repository_root as default_repository_root

MAXIMUM_WORKERS = 16
MAXIMUM_RETRIES = 5
MAXIMUM_RETRY_BACKOFF_SECONDS = 300.0
SUMMARY_SCHEMA_VERSION = 1
SUMMARY_FILENAME = "bulk-summary.json"
SUMMARY_SCHEMA_PATH = Path("schemas/codex-bulk-summary.schema.json")
ITEM_OUTCOMES = frozenset(
    {"completed", "resumedImport", "skipped", "dryRun", "failed", "cancelled"}
)


@dataclass(frozen=True)
class BulkItemRequest:
    """Serializable configuration for one isolated worker process."""

    slug: str
    repository: str
    work_directory: str
    model: str | None
    dry_run: bool
    resume: bool
    retries: int
    retry_backoff_seconds: float


type WorkerCallable = Callable[[BulkItemRequest], dict[str, JsonValue]]
type ExecutorFactory = Callable[..., Executor]


def default_worker_count(cpu_count: int | None = None) -> int:
    """Return a conservative CPU-derived worker count within the hard limit."""

    available_cpu_count = cpu_count if cpu_count is not None else os.cpu_count()
    normalized_cpu_count = max(1, available_cpu_count or 1)
    return min(2, normalized_cpu_count)


def selected_extracted_criterion_slugs(*, root: Path | None = None) -> tuple[str, ...]:
    """Return every extracted criterion slug in deterministic manifest order."""

    repository = (root or default_repository_root()).resolve()
    manifest = load_yaml(repository / "data/criteria-manifest.yaml")
    criteria = as_sequence(manifest["criteria"], location="manifest.criteria")
    selected_slugs: list[str] = []
    for index, criterion_value in enumerate(criteria):
        criterion = as_mapping(criterion_value, location=f"manifest.criteria[{index}]")
        if criterion.get("contentModel") != "extractedCriterion":
            continue
        slug = criterion.get("slug")
        if not isinstance(slug, str) or not slug:
            message = f"manifest.criteria[{index}].slug must be a non-empty string"
            raise ValueError(message)
        selected_slugs.append(slug)
    seen_slugs: set[str] = set()
    duplicate_slugs: set[str] = set()
    for slug in selected_slugs:
        if slug in seen_slugs:
            duplicate_slugs.add(slug)
        seen_slugs.add(slug)
    if duplicate_slugs:
        ordered_duplicates = sorted(duplicate_slugs, key=str.encode)
        message = f"duplicate extracted criterion slugs: {', '.join(ordered_duplicates)}"
        raise ValueError(message)
    return tuple(selected_slugs)


def _validate_configuration(
    *,
    workers: int,
    retries: int,
    retry_backoff_seconds: float,
) -> None:
    """Reject unbounded or ambiguous parallel and retry settings."""

    if isinstance(workers, bool) or not 1 <= workers <= MAXIMUM_WORKERS:
        message = f"workers must be between 1 and {MAXIMUM_WORKERS}"
        raise ValueError(message)
    if isinstance(retries, bool) or not 0 <= retries <= MAXIMUM_RETRIES:
        message = f"retries must be between 0 and {MAXIMUM_RETRIES}"
        raise ValueError(message)
    if (
        not math.isfinite(retry_backoff_seconds)
        or not 0 <= retry_backoff_seconds <= MAXIMUM_RETRY_BACKOFF_SECONDS
    ):
        message = f"retry backoff seconds must be between 0 and {MAXIMUM_RETRY_BACKOFF_SECONDS:g}"
        raise ValueError(message)


def _artifact_paths(work_directory: Path, slug: str) -> dict[str, Path]:
    """Return the paths exclusively owned by one criterion worker."""

    return {
        "task": work_directory / "tasks" / slug / "task.json",
        "result": work_directory / "results" / slug / "result.json",
        "run": work_directory / "results" / slug / "run.json",
        "events": work_directory / "results" / slug / "events.jsonl",
        "stderr": work_directory / "results" / slug / "stderr.log",
        "candidate": work_directory / "candidates" / slug / "candidate.md",
        "validation": work_directory / "candidates" / slug / "validation.json",
    }


def _summary_path_value(path: Path, *, root: Path) -> str:
    """Prefer a stable repository-relative path in generated manifests."""

    resolved_path = path.resolve()
    try:
        return resolved_path.relative_to(root.resolve()).as_posix()
    except ValueError:
        return resolved_path.as_posix()


def _paths_document(paths: dict[str, Path], *, root: Path) -> dict[str, JsonValue]:
    """Convert artifact paths into JSON-compatible stable strings."""

    return {name: _summary_path_value(path, root=root) for name, path in sorted(paths.items())}


def _duration_seconds(started_at: float) -> float:
    """Return a compact non-negative monotonic duration."""

    return round(max(0.0, time.perf_counter() - started_at), 6)


def _stage_document(  # noqa: PLR0913
    status: str,
    *,
    path: Path,
    root: Path,
    duration_seconds: float = 0.0,
    reason: str | None = None,
    attempts: int | None = None,
    retry_delays_seconds: Sequence[float] = (),
) -> dict[str, JsonValue]:
    """Build one consistent stage record for the summary manifest."""

    document: dict[str, JsonValue] = {
        "status": status,
        "durationSeconds": duration_seconds,
        "path": _summary_path_value(path, root=root),
    }
    if reason is not None:
        document["reason"] = reason
    if attempts is not None:
        document["attempts"] = attempts
        document["retryDelaysSeconds"] = list(retry_delays_seconds)
    return document


def _new_item_document(
    request: BulkItemRequest,
) -> tuple[
    dict[str, JsonValue],
    dict[str, Path],
    Path,
]:
    """Create an item summary before any stage mutates its isolated paths."""

    repository = Path(request.repository)
    paths = _artifact_paths(Path(request.work_directory), request.slug)
    stages: dict[str, JsonValue] = {
        "taskBuild": _stage_document("notRun", path=paths["task"], root=repository),
        "visionRun": _stage_document("notRun", path=paths["result"], root=repository),
        "importer": _stage_document("notRun", path=paths["candidate"], root=repository),
    }
    item: dict[str, JsonValue] = {
        "slug": request.slug,
        "outcome": "failed",
        "durationSeconds": 0.0,
        "resumeVerification": "notRequested" if not request.resume else "none",
        "paths": _paths_document(paths, root=repository),
        "stages": stages,
        "error": None,
    }
    return item, paths, repository


def _stages(item: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """Return the mutable stage mapping from one item document."""

    return as_mapping(item["stages"], location="item.stages")


def _finish_item(
    item: dict[str, JsonValue],
    *,
    outcome: str,
    started_at: float,
) -> dict[str, JsonValue]:
    """Finalize one successful, skipped, dry-run, or failed item record."""

    item["outcome"] = outcome
    item["durationSeconds"] = _duration_seconds(started_at)
    return item


def _result_is_valid(*, result_path: Path, task_path: Path, root: Path) -> bool:
    """Return whether a result remains valid for the freshly built task."""

    try:
        validate_codex_result(result_path, task_path, root=root)
    except (KeyError, OSError, TypeError, ValueError):
        return False
    return True


def _candidate_is_verified(
    *,
    candidate_path: Path,
    validation_path: Path,
    result_path: Path,
    task_path: Path,
) -> bool:
    """Verify the importer report and every checksum needed to skip an item."""

    if not candidate_path.is_file() or not validation_path.is_file():
        return False
    try:
        task = load_json(task_path)
        report = load_json(validation_path)
        expected_fields: dict[str, JsonValue] = {
            "schemaVersion": 2,
            "taskIdentifier": task.get("taskIdentifier"),
            "taskChecksum": task.get("taskChecksum"),
            "resultChecksum": sha256_file(result_path),
            "candidateChecksum": sha256_file(candidate_path),
            "validationStatus": "passed",
            "canonicalApplied": False,
        }
    except (KeyError, OSError, TypeError, ValueError):
        return False
    return all(report.get(name) == value for name, value in expected_fields.items())


def _resume_state(
    *,
    paths: dict[str, Path],
    root: Path,
) -> str:
    """Return the deepest verified stage reusable by a resumed item."""

    if not _result_is_valid(
        result_path=paths["result"],
        task_path=paths["task"],
        root=root,
    ):
        return "none"
    if _candidate_is_verified(
        candidate_path=paths["candidate"],
        validation_path=paths["validation"],
        result_path=paths["result"],
        task_path=paths["task"],
    ):
        return "verifiedCandidate"
    return "verifiedResult"


def _run_vision_with_retries(
    request: BulkItemRequest,
    *,
    root: Path,
    work_directory: Path,
) -> tuple[Path, int, list[float]]:
    """Run Codex with only the explicitly requested deterministic retries."""

    attempts = 0
    retry_delays_seconds: list[float] = []
    while True:
        attempts += 1
        try:
            output_path = run_codex_task(
                request.slug,
                root=root,
                work_directory=work_directory,
                model=request.model,
                dry_run=request.dry_run,
            )
        except Exception:
            if attempts > request.retries:
                raise
            delay_seconds = _retry_delay_seconds(request, failed_attempt=attempts)
            retry_delays_seconds.append(delay_seconds)
            if delay_seconds:
                time.sleep(delay_seconds)
        else:
            return output_path, attempts, retry_delays_seconds


def _retry_delay_seconds(request: BulkItemRequest, *, failed_attempt: int) -> float:
    """Return one explicitly configured, deterministic, capped retry delay."""

    return min(
        MAXIMUM_RETRY_BACKOFF_SECONDS,
        request.retry_backoff_seconds * (2 ** (failed_attempt - 1)),
    )


def _process_item(request: BulkItemRequest) -> dict[str, JsonValue]:
    """Run one isolated task-build, vision, and importer pipeline in a worker process."""

    item_started_at = time.perf_counter()
    item, paths, repository = _new_item_document(request)
    stages = _stages(item)
    output_root = Path(request.work_directory)
    active_stage = "taskBuild"
    vision_attempts = 0
    retry_delays_seconds: list[float] = []
    try:
        stage_started_at = time.perf_counter()
        task_path = build_codex_task(
            request.slug,
            root=repository,
            work_directory=output_root,
        )
        stages["taskBuild"] = _stage_document(
            "completed",
            path=task_path,
            root=repository,
            duration_seconds=_duration_seconds(stage_started_at),
        )

        resume_state = _resume_state(paths=paths, root=repository) if request.resume else "none"
        item["resumeVerification"] = resume_state if request.resume else "notRequested"
        if resume_state == "verifiedCandidate":
            stages["visionRun"] = _stage_document(
                "skipped",
                path=paths["result"],
                root=repository,
                reason="verifiedCandidate",
                attempts=0,
            )
            stages["importer"] = _stage_document(
                "skipped",
                path=paths["candidate"],
                root=repository,
                reason="verifiedCandidate",
            )
            return _finish_item(item, outcome="skipped", started_at=item_started_at)

        if resume_state == "verifiedResult":
            stages["visionRun"] = _stage_document(
                "skipped",
                path=paths["result"],
                root=repository,
                reason="verifiedResult",
                attempts=0,
            )
            active_stage = "importer"
            if request.dry_run:
                stages["importer"] = _stage_document(
                    "dryRun",
                    path=paths["candidate"],
                    root=repository,
                    reason="wouldResumeImport",
                )
                return _finish_item(item, outcome="dryRun", started_at=item_started_at)
            stage_started_at = time.perf_counter()
            candidate_path = render_codex_candidate(
                paths["result"],
                task_path,
                root=repository,
                work_directory=output_root,
            )
            stages["importer"] = _stage_document(
                "completed",
                path=candidate_path,
                root=repository,
                duration_seconds=_duration_seconds(stage_started_at),
                reason="resumedFromVerifiedResult",
            )
            return _finish_item(item, outcome="resumedImport", started_at=item_started_at)

        active_stage = "visionRun"
        stage_started_at = time.perf_counter()
        vision_output_path, vision_attempts, retry_delays_seconds = _run_vision_with_retries(
            request,
            root=repository,
            work_directory=output_root,
        )
        stages["visionRun"] = _stage_document(
            "dryRun" if request.dry_run else "completed",
            path=vision_output_path,
            root=repository,
            duration_seconds=_duration_seconds(stage_started_at),
            attempts=vision_attempts,
            retry_delays_seconds=retry_delays_seconds,
        )
        if request.dry_run:
            stages["importer"] = _stage_document(
                "notRun",
                path=paths["candidate"],
                root=repository,
                reason="visionDryRun",
            )
            return _finish_item(item, outcome="dryRun", started_at=item_started_at)

        active_stage = "importer"
        stage_started_at = time.perf_counter()
        candidate_path = render_codex_candidate(
            vision_output_path,
            task_path,
            root=repository,
            work_directory=output_root,
        )
        stages["importer"] = _stage_document(
            "completed",
            path=candidate_path,
            root=repository,
            duration_seconds=_duration_seconds(stage_started_at),
        )
    except Exception as error:  # noqa: BLE001
        stage_path = {
            "taskBuild": paths["task"],
            "visionRun": paths["result"],
            "importer": paths["candidate"],
        }[active_stage]
        stage_arguments: dict[str, JsonValue] = {
            "status": "failed",
            "durationSeconds": _duration_seconds(stage_started_at),
            "path": _summary_path_value(stage_path, root=repository),
        }
        if active_stage == "visionRun":
            stage_arguments["attempts"] = vision_attempts or request.retries + 1
            failed_retry_delays = retry_delays_seconds or [
                _retry_delay_seconds(request, failed_attempt=attempt)
                for attempt in range(1, request.retries + 1)
            ]
            stage_arguments["retryDelaysSeconds"] = cast("JsonValue", failed_retry_delays)
        stages[active_stage] = stage_arguments
        item["error"] = {
            "stage": active_stage,
            "type": type(error).__name__,
            "message": str(error),
        }
        return _finish_item(item, outcome="failed", started_at=item_started_at)
    return _finish_item(item, outcome="completed", started_at=item_started_at)


def _cancelled_item(request: BulkItemRequest, *, reason: str) -> dict[str, JsonValue]:
    """Build a stable record for work that did not finish."""

    item, _paths, _repository = _new_item_document(request)
    item["outcome"] = "cancelled"
    item["error"] = {"stage": "scheduler", "type": "Cancelled", "message": reason}
    return item


def _worker_failure_item(
    request: BulkItemRequest,
    *,
    error: BaseException,
) -> dict[str, JsonValue]:
    """Isolate an executor or worker-process failure to its assigned item."""

    item, _paths, _repository = _new_item_document(request)
    item["outcome"] = "failed"
    item["error"] = {
        "stage": "workerProcess",
        "type": type(error).__name__,
        "message": str(error),
    }
    return item


def _normalize_worker_result(
    request: BulkItemRequest,
    result: object,
) -> dict[str, JsonValue]:
    """Validate the identity and outcome returned by an injected worker."""

    if not isinstance(result, dict):
        message = "worker result must be a JSON object"
        raise TypeError(message)
    normalized_result = cast("dict[str, JsonValue]", result)
    if normalized_result.get("slug") != request.slug:
        message = f"worker returned a mismatched slug for {request.slug}"
        raise ValueError(message)
    if normalized_result.get("outcome") not in ITEM_OUTCOMES:
        message = f"worker returned an invalid outcome for {request.slug}"
        raise ValueError(message)
    return normalized_result


def _validated_worker_result(
    request: BulkItemRequest,
    future: Future[object],
) -> dict[str, JsonValue]:
    """Convert one future into a validated JSON item or an isolated failure."""

    if future.cancelled():
        return _cancelled_item(request, reason="cancelled before worker execution")
    try:
        normalized_result = _normalize_worker_result(request, future.result())
    except BaseException as error:
        if isinstance(error, KeyboardInterrupt):
            raise
        return _worker_failure_item(request, error=error)
    return normalized_result


def _cancel_pending_requests(
    pending_requests: deque[BulkItemRequest],
    results: dict[str, dict[str, JsonValue]],
    *,
    reason: str,
) -> None:
    """Record every request that was never submitted."""

    while pending_requests:
        request = pending_requests.popleft()
        results[request.slug] = _cancelled_item(request, reason=reason)


def _cancel_queued_futures(
    active_futures: dict[Future[object], BulkItemRequest],
    results: dict[str, dict[str, JsonValue]],
    *,
    reason: str,
) -> None:
    """Cancel executor work that has not started and retain running futures."""

    for future, request in list(active_futures.items()):
        if future.cancel():
            active_futures.pop(future)
            results[request.slug] = _cancelled_item(request, reason=reason)


def _submit_available_requests(  # noqa: PLR0913
    *,
    executor: Executor,
    worker_callable: WorkerCallable,
    pending_requests: deque[BulkItemRequest],
    active_futures: dict[Future[object], BulkItemRequest],
    results: dict[str, dict[str, JsonValue]],
    workers: int,
    stop_after_failure: bool,
) -> bool:
    """Fill the bounded executor queue and report whether submission failed."""

    submission_failed = False
    while pending_requests and len(active_futures) < workers:
        request = pending_requests.popleft()
        try:
            future = executor.submit(worker_callable, request)
        except Exception as error:  # noqa: BLE001
            results[request.slug] = _worker_failure_item(request, error=error)
            submission_failed = True
            if stop_after_failure:
                return submission_failed
        else:
            active_futures[cast("Future[object]", future)] = request
    return submission_failed


def _execute_requests(  # noqa: C901, PLR0912
    requests: Sequence[BulkItemRequest],
    *,
    workers: int,
    fail_fast: bool,
    executor_factory: ExecutorFactory,
    worker_callable: WorkerCallable,
) -> tuple[dict[str, dict[str, JsonValue]], bool, bool]:
    """Execute requests with bounded submission, isolation, and cancellation."""

    results: dict[str, dict[str, JsonValue]] = {}
    if not requests:
        return results, False, False
    pending_requests = deque(requests)
    active_futures: dict[Future[object], BulkItemRequest] = {}
    fail_fast_triggered = False
    interrupted = False
    try:
        executor = executor_factory(max_workers=workers)
    except Exception as error:  # noqa: BLE001
        for request in requests:
            results[request.slug] = _worker_failure_item(request, error=error)
        return results, fail_fast, False

    try:
        while pending_requests or active_futures:
            if not fail_fast_triggered:
                submission_failed = _submit_available_requests(
                    executor=executor,
                    worker_callable=worker_callable,
                    pending_requests=pending_requests,
                    active_futures=active_futures,
                    results=results,
                    workers=workers,
                    stop_after_failure=fail_fast,
                )
                fail_fast_triggered = fail_fast and submission_failed
            if fail_fast_triggered:
                _cancel_pending_requests(
                    pending_requests,
                    results,
                    reason="not started after fail-fast",
                )
                _cancel_queued_futures(
                    active_futures,
                    results,
                    reason="cancelled after fail-fast",
                )
            if not active_futures:
                continue
            completed_futures, _remaining_futures = wait(
                active_futures,
                return_when=FIRST_COMPLETED,
            )
            ordered_futures = sorted(
                completed_futures,
                key=lambda future: active_futures[future].slug.encode(),
            )
            for future in ordered_futures:
                request = active_futures.pop(future)
                result = _validated_worker_result(request, future)
                results[request.slug] = result
                if fail_fast and result.get("outcome") == "failed":
                    fail_fast_triggered = True
    except KeyboardInterrupt:
        interrupted = True
        _cancel_pending_requests(
            pending_requests,
            results,
            reason="not started after keyboard interrupt",
        )
        _cancel_queued_futures(
            active_futures,
            results,
            reason="cancelled after keyboard interrupt",
        )
        for request in active_futures.values():
            results[request.slug] = _cancelled_item(
                request,
                reason="interrupted while worker was running",
            )
    finally:
        try:
            executor.shutdown(wait=True, cancel_futures=True)
        except KeyboardInterrupt:
            interrupted = True
            executor.shutdown(wait=False, cancel_futures=True)
    return results, fail_fast_triggered, interrupted


def _summary_counts(items: Sequence[dict[str, JsonValue]]) -> dict[str, JsonValue]:
    """Count every mutually exclusive item outcome."""

    counts = dict.fromkeys(sorted(ITEM_OUTCOMES), 0)
    for item in items:
        outcome = item.get("outcome")
        if isinstance(outcome, str) and outcome in counts:
            counts[outcome] += 1
    successful_count = counts["completed"] + counts["resumedImport"] + counts["skipped"]
    return {
        "total": len(items),
        "successful": successful_count,
        **counts,
    }


def _overall_status(
    counts: dict[str, JsonValue],
    *,
    dry_run: bool,
    fail_fast_triggered: bool,
    interrupted: bool,
) -> str:
    """Derive the run status from item outcomes and scheduler state."""

    if interrupted:
        return "interrupted"
    if fail_fast_triggered:
        return "failedFast"
    if counts["failed"] or counts["cancelled"]:
        return "completedWithFailures"
    if dry_run:
        return "dryRun"
    return "completed"


def _write_summary(path: Path, document: dict[str, JsonValue]) -> None:
    """Atomically replace the summary after all worker writes have settled."""

    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".temporary",
            delete=False,
        ) as temporary_file:
            temporary_file.write(serialized)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def validate_bulk_summary(
    document: dict[str, JsonValue],
    *,
    root: Path | None = None,
) -> None:
    """Validate a bulk summary against its tracked machine-readable contract."""

    repository = (root or default_repository_root()).resolve()
    schema = load_json(repository / SUMMARY_SCHEMA_PATH)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(document),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        messages = "; ".join(
            f"{'.'.join(str(part) for part in error.absolute_path) or '$'}: {error.message}"
            for error in errors
        )
        message = f"bulk summary does not satisfy its schema: {messages}"
        raise ValueError(message)


def _selected_requested_slugs(
    available_slugs: Sequence[str],
    requested_slugs: Sequence[str] | None,
) -> tuple[str, ...]:
    """Validate a requested allowlist and filter it in manifest order."""

    if not requested_slugs:
        return tuple(available_slugs)
    requested_slug_set = set(requested_slugs)
    if len(requested_slug_set) != len(requested_slugs):
        message = "requested criterion slugs must be unique"
        raise ValueError(message)
    unavailable_slugs = sorted(requested_slug_set.difference(available_slugs), key=str.encode)
    if unavailable_slugs:
        message = f"requested slugs are not extracted criteria: {', '.join(unavailable_slugs)}"
        raise ValueError(message)
    return tuple(slug for slug in available_slugs if slug in requested_slug_set)


def run_bulk_conversion(  # noqa: PLR0913
    *,
    slugs: Sequence[str] | None = None,
    root: Path | None = None,
    work_directory: Path | None = None,
    workers: int | None = None,
    model: str | None = None,
    dry_run: bool = False,
    resume: bool = False,
    fail_fast: bool = False,
    retries: int = 0,
    retry_backoff_seconds: float = 0.0,
    summary_path: Path | None = None,
    executor_factory: ExecutorFactory = ProcessPoolExecutor,
    worker_callable: WorkerCallable = _process_item,
) -> dict[str, JsonValue]:
    """Run all extracted criteria and write a deterministic ordered summary."""

    started_at = time.perf_counter()
    repository = (root or default_repository_root()).resolve()
    output_root = (work_directory or repository / DEFAULT_WORK_DIRECTORY).resolve()
    worker_count = workers if workers is not None else default_worker_count()
    _validate_configuration(
        workers=worker_count,
        retries=retries,
        retry_backoff_seconds=retry_backoff_seconds,
    )
    available_slugs = selected_extracted_criterion_slugs(root=repository)
    selected_slugs = _selected_requested_slugs(available_slugs, slugs)
    requests = [
        BulkItemRequest(
            slug=slug,
            repository=repository.as_posix(),
            work_directory=output_root.as_posix(),
            model=model,
            dry_run=dry_run,
            resume=resume,
            retries=retries,
            retry_backoff_seconds=retry_backoff_seconds,
        )
        for slug in selected_slugs
    ]
    results, fail_fast_triggered, interrupted = _execute_requests(
        requests,
        workers=worker_count,
        fail_fast=fail_fast,
        executor_factory=executor_factory,
        worker_callable=worker_callable,
    )
    items = [results[slug] for slug in selected_slugs]
    counts = _summary_counts(items)
    output_summary_path = (summary_path or output_root / SUMMARY_FILENAME).resolve()
    configuration: dict[str, JsonValue] = {
        "workers": worker_count,
        "model": model or "configured-default",
        "dryRun": dry_run,
        "resume": resume,
        "failFast": fail_fast,
        "retries": retries,
        "retryBackoffSeconds": retry_backoff_seconds,
        "workDirectory": _summary_path_value(output_root, root=repository),
    }
    summary: dict[str, JsonValue] = {
        "schemaVersion": SUMMARY_SCHEMA_VERSION,
        "status": _overall_status(
            counts,
            dry_run=dry_run,
            fail_fast_triggered=fail_fast_triggered,
            interrupted=interrupted,
        ),
        "durationSeconds": _duration_seconds(started_at),
        "configuration": configuration,
        "counts": counts,
        "items": cast("JsonValue", items),
        "summaryPath": _summary_path_value(output_summary_path, root=repository),
    }
    validate_bulk_summary(summary, root=repository)
    _write_summary(output_summary_path, summary)
    return summary


def _bounded_integer(argument: str, *, minimum: int, maximum: int, name: str) -> int:
    """Parse one bounded integer for argparse."""

    try:
        value = int(argument)
    except ValueError as error:
        message = f"{name} must be an integer"
        raise argparse.ArgumentTypeError(message) from error
    if not minimum <= value <= maximum:
        message = f"{name} must be between {minimum} and {maximum}"
        raise argparse.ArgumentTypeError(message)
    return value


def _worker_argument(argument: str) -> int:
    """Parse a positive bounded worker count."""

    return _bounded_integer(argument, minimum=1, maximum=MAXIMUM_WORKERS, name="workers")


def _retry_argument(argument: str) -> int:
    """Parse a bounded explicit retry count."""

    return _bounded_integer(argument, minimum=0, maximum=MAXIMUM_RETRIES, name="retries")


def _backoff_argument(argument: str) -> float:
    """Parse a finite bounded deterministic retry backoff."""

    try:
        value = float(argument)
    except ValueError as error:
        message = "retry backoff seconds must be a number"
        raise argparse.ArgumentTypeError(message) from error
    if not math.isfinite(value) or not 0 <= value <= MAXIMUM_RETRY_BACKOFF_SECONDS:
        message = f"retry backoff seconds must be between 0 and {MAXIMUM_RETRY_BACKOFF_SECONDS:g}"
        raise argparse.ArgumentTypeError(message)
    return value


def _argument_parser() -> argparse.ArgumentParser:
    """Build the bounded bulk-runner command-line parser."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "slugs",
        nargs="*",
        help="optional extracted criterion allowlist; manifest order is preserved",
    )
    parser.add_argument("--work-directory", type=Path, help="generated Codex work directory")
    parser.add_argument(
        "--workers",
        type=_worker_argument,
        default=default_worker_count(),
        help=f"parallel worker processes, 1-{MAXIMUM_WORKERS}",
    )
    parser.add_argument("--model", help="optional Codex model override")
    parser.add_argument("--dry-run", action="store_true", help="write plans without importing")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="reuse only currently verified results and candidates",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="stop scheduling new criteria after the first failure",
    )
    parser.add_argument(
        "--retries",
        type=_retry_argument,
        default=0,
        help=f"explicit Codex retries after the first attempt, 0-{MAXIMUM_RETRIES}",
    )
    parser.add_argument(
        "--retry-backoff-seconds",
        type=_backoff_argument,
        default=0.0,
        help="deterministic exponential retry backoff base in seconds",
    )
    parser.add_argument("--summary-path", type=Path, help="bulk summary JSON output path")
    return parser


def main() -> int:
    """Run the bulk conversion command and return a machine-friendly exit code."""

    arguments = _argument_parser().parse_args()
    try:
        summary = run_bulk_conversion(
            slugs=arguments.slugs,
            work_directory=arguments.work_directory,
            workers=arguments.workers,
            model=arguments.model,
            dry_run=arguments.dry_run,
            resume=arguments.resume,
            fail_fast=arguments.fail_fast,
            retries=arguments.retries,
            retry_backoff_seconds=arguments.retry_backoff_seconds,
            summary_path=arguments.summary_path,
        )
    except (KeyError, OSError, TypeError, ValueError) as error:
        sys.stderr.write(f"{error}\n")
        return 1
    sys.stdout.write(f"{summary['summaryPath']}\n")
    if summary["status"] == "interrupted":
        return 130
    counts = as_mapping(summary["counts"], location="summary.counts")
    return 1 if counts["failed"] or counts["cancelled"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
