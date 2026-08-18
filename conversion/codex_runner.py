"""Run one generated criterion task through Codex in a read-only sandbox."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
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


def _last_event_error(events_path: Path) -> str | None:
    """Return the final structured Codex error when a run fails."""

    if not events_path.is_file():
        return None
    for line in reversed(events_path.read_text(encoding="utf-8").splitlines()):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type") == "error":
            message = event.get("message")
            return message if isinstance(message, str) else None
    return None


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


def run_codex_task(
    slug: str,
    *,
    root: Path | None = None,
    work_directory: Path | None = None,
    model: str | None = None,
    dry_run: bool = False,
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
        return run_path

    with (
        events_path.open("w", encoding="utf-8") as events_stream,
        error_path.open(
            "w",
            encoding="utf-8",
        ) as error_stream,
    ):
        completed_process = subprocess.run(
            command,
            input=_prompt(task_path, task, root=repository),
            text=True,
            stdout=events_stream,
            stderr=error_stream,
            check=False,
            cwd=repository,
        )
    completed_at = datetime.now(tz=UTC)
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
        "resultChecksum": sha256_file(result_path) if result_path.is_file() else None,
    }
    run_path.write_text(
        json.dumps(run_document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if completed_process.returncode != 0:
        event_error = _last_event_error(events_path)
        error_tail = error_path.read_text(encoding="utf-8")[-2000:]
        failure_detail = event_error or error_tail
        msg = f"Codex task failed with exit code {completed_process.returncode}: {failure_detail}"
        raise RuntimeError(msg)
    _validate_result_schema(result_path, root=repository)
    return result_path


def _argument_parser() -> argparse.ArgumentParser:
    """Build the Codex runner command-line parser."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug", help="criterion slug such as u-03")
    parser.add_argument("--work-directory", type=Path, help="generated Codex work directory")
    parser.add_argument("--model", help="optional Codex model override")
    parser.add_argument("--dry-run", action="store_true", help="write the run plan only")
    return parser


def main() -> int:
    """Run one Codex task from the command line."""

    arguments = _argument_parser().parse_args()
    try:
        output_path = run_codex_task(
            arguments.slug,
            work_directory=arguments.work_directory,
            model=arguments.model,
            dry_run=arguments.dry_run,
        )
    except (FileNotFoundError, RuntimeError, TypeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
