"""Run one generated criterion task through Codex in a read-only sandbox."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from jsonschema import Draft202012Validator, FormatChecker

from conversion.codex_task_builder import (
    DEFAULT_WORK_DIRECTORY,
    PROMPT_TEMPLATE_PATH,
    RESULT_SCHEMA_PATH,
    build_codex_task,
    load_codex_task,
    verify_codex_task_dependencies,
)
from conversion.common import (
    JsonValue,
    as_mapping,
    as_sequence,
    load_json,
    repository_root,
    sha256_file,
)
from conversion.runtime_logging import (
    RuntimeLogger,
    add_logging_arguments,
    configure_runtime_logging,
)

_CODEX_TYPE_NAME_CHARACTERS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
)
_MAXIMUM_CODEX_TYPE_NAME_LENGTH = 64
_MAXIMUM_THREAD_IDENTIFIER_LENGTH = 128


def _codex_binary() -> Path:
    """Resolve the installed Codex CLI without invoking a shell."""

    executable = shutil.which("codex")
    if executable is None:
        msg = "Codex CLI is not installed or is absent from PATH"
        raise FileNotFoundError(msg)
    return Path(executable)


def _codex_version(executable: Path) -> str:
    """Return the exact Codex CLI version used for a run manifest."""

    completed_process = subprocess.run(
        [str(executable), "--version"],
        text=True,
        capture_output=True,
        check=True,
    )
    return completed_process.stdout.strip()


def _safe_codex_type_name(value: object) -> str | None:
    """Return one bounded event or item type without reading adjacent body fields."""

    if (
        not isinstance(value, str)
        or not value
        or len(value) > _MAXIMUM_CODEX_TYPE_NAME_LENGTH
        or any(character not in _CODEX_TYPE_NAME_CHARACTERS for character in value)
    ):
        return None
    return value


def _safe_thread_identifier(value: object) -> str | None:
    """Return a bounded identifier from a thread-started event."""

    if (
        not isinstance(value, str)
        or not value
        or len(value) > _MAXIMUM_THREAD_IDENTIFIER_LENGTH
        or any(character not in _CODEX_TYPE_NAME_CHARACTERS for character in value)
    ):
        return None
    return value


def _codex_event_summary(events_path: Path) -> dict[str, object]:  # noqa: C901
    """Summarize allowlisted metadata without retaining Codex content bodies."""

    event_type_counts: Counter[str] = Counter()
    item_type_counts: Counter[str] = Counter()
    usage_token_counts: Counter[str] = Counter()
    thread_identifier: str | None = None
    total_event_count = 0
    invalid_json_line_count = 0
    if events_path.is_file():
        with events_path.open("r", encoding="utf-8", errors="replace") as events_stream:
            for line in events_stream:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    invalid_json_line_count += 1
                    continue
                if not isinstance(event, dict):
                    continue
                total_event_count += 1
                event_type = _safe_codex_type_name(event.get("type"))
                if event_type is not None:
                    event_type_counts[event_type] += 1
                    if event_type == "thread.started" and thread_identifier is None:
                        thread_identifier = _safe_thread_identifier(event.get("thread_id"))
                item = event.get("item")
                if isinstance(item, dict):
                    item_type = _safe_codex_type_name(item.get("type"))
                    if item_type is not None:
                        item_type_counts[item_type] += 1
                if event_type != "turn.completed":
                    continue
                usage = event.get("usage")
                if not isinstance(usage, dict):
                    continue
                for key, value in usage.items():
                    if (
                        isinstance(key, str)
                        and key.endswith("_tokens")
                        and _safe_codex_type_name(key) is not None
                        and isinstance(value, int)
                        and not isinstance(value, bool)
                        and value >= 0
                    ):
                        usage_token_counts[key] += value
    return {
        "event_type_counts": dict(sorted(event_type_counts.items())),
        "invalid_json_line_count": invalid_json_line_count,
        "item_type_counts": dict(sorted(item_type_counts.items())),
        "thread_id": thread_identifier,
        "total_event_count": total_event_count,
        "usage": dict(sorted(usage_token_counts.items())),
    }


def _duration_seconds(started_at: float) -> float:
    """Return a compact non-negative communication duration."""

    return round(max(0.0, time.perf_counter() - started_at), 6)


def _request_log_fields(  # noqa: PLR0913
    *,
    slug: str,
    model: str | None,
    codex_version: str,
    image_count: int,
    schema_path: Path,
    task_identifier: JsonValue,
    task_checksum: JsonValue,
    result_path: Path,
    events_path: Path,
    error_path: Path,
    run_path: Path,
) -> dict[str, object]:
    """Build the safe metadata shared by Codex request lifecycle records."""

    return {
        "slug": slug,
        "model": model or "configured-default",
        "codex_version": codex_version,
        "image_count": image_count,
        "schema_path": schema_path.resolve().as_posix(),
        "task_identifier": task_identifier,
        "task_checksum": task_checksum,
        "output_paths": {
            "events": events_path.resolve().as_posix(),
            "result": result_path.resolve().as_posix(),
            "run": run_path.resolve().as_posix(),
            "stderr": error_path.resolve().as_posix(),
        },
    }


def _log_response(  # noqa: PLR0913
    runtime_logger: RuntimeLogger | None,
    *,
    completed: bool,
    request_fields: dict[str, object],
    exit_code: int | None,
    duration_seconds: float,
    result_checksum: str | None,
    schema_validation: str,
    event_summary: dict[str, object],
    error_type: str | None = None,
) -> None:
    """Record one terminal response event using only allowlisted metadata."""

    if runtime_logger is None:
        return
    fields = {
        **request_fields,
        **event_summary,
        "exit_code": exit_code,
        "duration_seconds": duration_seconds,
        "result_checksum": result_checksum,
        "schema_validation": schema_validation,
    }
    if error_type is not None:
        fields["error_type"] = error_type
    if completed:
        runtime_logger.info(
            "Codex response completed",
            event="codex.response.completed",
            **fields,
        )
    else:
        runtime_logger.error(
            "Codex response failed",
            event="codex.response.failed",
            **fields,
        )


def _task_image_paths(task: dict[str, JsonValue], *, root: Path) -> list[Path]:
    """Resolve and verify every source image declared by a task."""

    paths: list[Path] = []
    for evidence_value in as_sequence(
        task["sourcePageEvidence"],
        location="task.sourcePageEvidence",
    ):
        evidence = as_mapping(evidence_value, location="task.sourcePageEvidence[]")
        raw_path = evidence.get("imagePath")
        expected_checksum = evidence.get("imageChecksum")
        if not isinstance(raw_path, str) or not isinstance(expected_checksum, str):
            msg = "task image path and checksum must be strings"
            raise TypeError(msg)
        image_path = (root / raw_path).resolve()
        if not image_path.is_relative_to(root.resolve()) or not image_path.is_file():
            msg = f"task image is missing or outside the repository: {raw_path}"
            raise ValueError(msg)
        if sha256_file(image_path) != expected_checksum:
            msg = f"task image checksum mismatch: {raw_path}"
            raise ValueError(msg)
        paths.append(image_path)
    return paths


def build_codex_command(
    *,
    task: dict[str, JsonValue],
    result_path: Path,
    root: Path,
    model: str | None,
) -> list[str]:
    """Build the exact non-interactive Codex command for one task."""

    command = [
        str(_codex_binary()),
        "exec",
        "--ephemeral",
        "--ignore-user-config",
        "--sandbox",
        "read-only",
        "--color",
        "never",
        "--json",
        "--output-schema",
        str((root / RESULT_SCHEMA_PATH).resolve()),
        "--output-last-message",
        str(result_path.resolve()),
        "--cd",
        str(root.resolve()),
    ]
    if model is not None:
        command.extend(["--model", model])
    for image_path in _task_image_paths(task, root=root):
        command.extend(["--image", str(image_path)])
    command.append("-")
    return command


def _prompt(task_path: Path, task: dict[str, JsonValue], *, root: Path) -> str:
    """Bind the versioned prompt template to one immutable task path."""

    template = (root / PROMPT_TEMPLATE_PATH).read_text(encoding="utf-8").rstrip()
    relative_task_path = task_path.resolve().relative_to(root.resolve()).as_posix()
    return (
        f"{template}\n\n"
        "## Assigned task\n\n"
        f"- Task JSON: `{relative_task_path}`\n"
        f"- Task identifier: `{task['taskIdentifier']}`\n"
        f"- Task checksum: `{task['taskChecksum']}`\n"
        f"- Criterion: `{task['criterionCode']}`\n"
    )


def _validate_result_schema(result_path: Path, *, root: Path) -> dict[str, JsonValue]:
    """Validate the model response against the tracked result schema."""

    result = load_json(result_path)
    schema = load_json(root / RESULT_SCHEMA_PATH)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(result), key=lambda item: list(item.path))
    if errors:
        messages = "; ".join(
            f"{'.'.join(str(part) for part in error.absolute_path) or '$'}: {error.message}"
            for error in errors
        )
        msg = f"Codex result does not satisfy the schema: {messages}"
        raise ValueError(msg)
    return result


def run_codex_task(  # noqa: PLR0913, PLR0915
    slug: str,
    *,
    root: Path | None = None,
    work_directory: Path | None = None,
    model: str | None = None,
    dry_run: bool = False,
    runtime_logger: RuntimeLogger | None = None,
) -> Path:
    """Build and run one criterion task, returning its structured result path."""

    repository = root or repository_root()
    output_root = work_directory or repository / DEFAULT_WORK_DIRECTORY
    task_path = output_root / "tasks" / slug / "task.json"
    if not task_path.is_file():
        task_path = build_codex_task(slug, root=repository, work_directory=output_root)
    task = load_codex_task(task_path, root=repository)
    verify_codex_task_dependencies(task, root=repository)
    result_directory = output_root / "results" / slug
    result_directory.mkdir(parents=True, exist_ok=True)
    result_path = result_directory / "result.json"
    events_path = result_directory / "events.jsonl"
    error_path = result_directory / "stderr.log"
    run_path = result_directory / "run.json"
    command = build_codex_command(
        task=task,
        result_path=result_path,
        root=repository,
        model=model,
    )
    codex_version = "not-executed" if dry_run else _codex_version(Path(command[0]))
    request_fields = _request_log_fields(
        slug=slug,
        model=model,
        codex_version=codex_version,
        image_count=len(
            as_sequence(task["sourcePageEvidence"], location="task.sourcePageEvidence")
        ),
        schema_path=repository / RESULT_SCHEMA_PATH,
        task_identifier=task["taskIdentifier"],
        task_checksum=task["taskChecksum"],
        result_path=result_path,
        events_path=events_path,
        error_path=error_path,
        run_path=run_path,
    )
    if runtime_logger is not None:
        runtime_logger.info(
            "Codex request prepared",
            event="codex.request.prepared",
            **request_fields,
        )
    started_at = datetime.now(tz=UTC)
    if dry_run:
        run_document: dict[str, JsonValue] = {
            "schemaVersion": 1,
            "taskIdentifier": task["taskIdentifier"],
            "taskChecksum": task["taskChecksum"],
            "status": "dryRun",
            "model": model or "configured-default",
            "codexVersion": codex_version,
            "command": cast("JsonValue", command),
            "startedAt": started_at.isoformat(),
            "completedAt": started_at.isoformat(),
            "exitCode": None,
            "resultChecksum": None,
        }
        run_path.write_text(
            json.dumps(run_document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if runtime_logger is not None:
            runtime_logger.info(
                "Codex request planned",
                event="codex.request.planned",
                **request_fields,
            )
        return run_path

    prompt = _prompt(task_path, task, root=repository)
    request_started_at = time.perf_counter()
    if runtime_logger is not None:
        runtime_logger.info(
            "Codex request started",
            event="codex.request.started",
            **request_fields,
        )
    try:
        with (
            events_path.open("w", encoding="utf-8") as events_stream,
            error_path.open(
                "w",
                encoding="utf-8",
            ) as error_stream,
        ):
            completed_process = subprocess.run(
                command,
                input=prompt,
                text=True,
                stdout=events_stream,
                stderr=error_stream,
                check=False,
                cwd=repository,
            )
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        _log_response(
            runtime_logger,
            completed=False,
            request_fields=request_fields,
            exit_code=None,
            duration_seconds=_duration_seconds(request_started_at),
            result_checksum=sha256_file(result_path) if result_path.is_file() else None,
            schema_validation="not_run",
            event_summary=_codex_event_summary(events_path),
            error_type=type(error).__name__,
        )
        message = "Codex process could not be started; inspect generated Codex artifacts"
        raise RuntimeError(message) from None
    completed_at = datetime.now(tz=UTC)
    result_checksum = sha256_file(result_path) if result_path.is_file() else None
    event_summary = _codex_event_summary(events_path)
    duration_seconds = _duration_seconds(request_started_at)
    run_document = {
        "schemaVersion": 1,
        "taskIdentifier": task["taskIdentifier"],
        "taskChecksum": task["taskChecksum"],
        "status": "completed" if completed_process.returncode == 0 else "failed",
        "model": model or "configured-default",
        "codexVersion": codex_version,
        "command": cast("JsonValue", command),
        "startedAt": started_at.isoformat(),
        "completedAt": completed_at.isoformat(),
        "exitCode": completed_process.returncode,
        "resultChecksum": result_checksum,
    }
    run_path.write_text(
        json.dumps(run_document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if completed_process.returncode != 0:
        _log_response(
            runtime_logger,
            completed=False,
            request_fields=request_fields,
            exit_code=completed_process.returncode,
            duration_seconds=duration_seconds,
            result_checksum=result_checksum,
            schema_validation="not_run",
            event_summary=event_summary,
            error_type="CodexProcessError",
        )
        message = (
            f"Codex task failed with exit code {completed_process.returncode}; "
            "inspect generated Codex artifacts"
        )
        raise RuntimeError(message)
    try:
        _validate_result_schema(result_path, root=repository)
    except (KeyError, OSError, TypeError, ValueError) as error:
        _log_response(
            runtime_logger,
            completed=False,
            request_fields=request_fields,
            exit_code=completed_process.returncode,
            duration_seconds=duration_seconds,
            result_checksum=result_checksum,
            schema_validation="failed",
            event_summary=event_summary,
            error_type=type(error).__name__,
        )
        message = "Codex result failed schema validation; inspect generated Codex artifacts"
        raise ValueError(message) from None
    _log_response(
        runtime_logger,
        completed=True,
        request_fields=request_fields,
        exit_code=completed_process.returncode,
        duration_seconds=duration_seconds,
        result_checksum=result_checksum,
        schema_validation="passed",
        event_summary=event_summary,
    )
    return result_path


def _argument_parser() -> argparse.ArgumentParser:
    """Build the Codex runner command-line parser."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug", help="criterion slug such as u-03")
    parser.add_argument("--work-directory", type=Path, help="generated Codex work directory")
    parser.add_argument("--model", help="optional Codex model override")
    parser.add_argument("--dry-run", action="store_true", help="write the run plan only")
    add_logging_arguments(parser)
    return parser


def main() -> int:
    """Run one Codex task from the command line."""

    arguments = _argument_parser().parse_args()
    with configure_runtime_logging(
        "codex_runner",
        level=arguments.log_level,
        log_directory=arguments.log_directory,
        context={"slug": arguments.slug},
    ) as logger:
        logger.info(
            "Codex task run started",
            event="command.started",
            dry_run=arguments.dry_run,
            model=arguments.model or "configured-default",
            work_directory=(
                str(arguments.work_directory) if arguments.work_directory is not None else None
            ),
        )
        try:
            output_path = run_codex_task(
                arguments.slug,
                work_directory=arguments.work_directory,
                model=arguments.model,
                dry_run=arguments.dry_run,
                runtime_logger=logger,
            )
        except (FileNotFoundError, RuntimeError, TypeError, ValueError) as error:
            # Exception tracebacks can contain untrusted Codex response details.
            logger.error(  # noqa: TRY400
                "Codex task run failed",
                event="command.failed",
                error_type=type(error).__name__,
                dry_run=arguments.dry_run,
            )
            print(str(error), file=sys.stderr)
            return 1
        logger.info(
            "Codex task run completed",
            event="command.completed",
            dry_run=arguments.dry_run,
            output_path=str(output_path),
        )
        print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
