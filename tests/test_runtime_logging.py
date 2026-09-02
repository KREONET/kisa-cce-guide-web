"""Tests for shared conversion runtime logging and progress reporting."""

from __future__ import annotations

import argparse
import io
import json
import multiprocessing
import os
import sys
import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import IO

import pytest

from conversion import runtime_logging
from conversion.paths import WORK_DIRECTORY
from conversion.runtime_logging import (
    LOG_DIRECTORY_ENVIRONMENT_VARIABLE,
    LOG_LEVEL_ENVIRONMENT_VARIABLE,
    ProgressReporter,
    add_logging_arguments,
    configure_runtime_logging,
)

FIXED_TIME = datetime(2026, 8, 19, 1, 2, 3, 456000, tzinfo=UTC)
TEST_PROCESS_ID = 4321
THREAD_COUNT = 4
UPDATES_PER_THREAD = 5
TTY_REPAINT_COUNT = 2


class _TerminalStream(io.StringIO):
    """Provide a controllable terminal flag around an in-memory text stream."""

    def __init__(self, *, terminal: bool) -> None:
        """Initialize an empty stream with one fixed terminal state."""

        super().__init__()
        self._terminal = terminal

    def isatty(self) -> bool:
        """Return the configured terminal state."""

        return self._terminal


class _NumberClock:
    """Return deterministic monotonic values for progress tests."""

    def __init__(self, values: Iterator[float]) -> None:
        """Store a finite sequence consumed by reporter operations."""

        self._values = values

    def __call__(self) -> float:
        """Return the next configured monotonic value."""

        return next(self._values)


def _fixed_clock() -> datetime:
    """Return the shared deterministic wall-clock fixture."""

    return FIXED_TIME


def _multiprocess_log_worker(log_directory: str, marker: str) -> None:
    """Write one isolated child-process log without polluting test stderr."""

    with (
        Path(os.devnull).open("w", encoding="utf-8") as console_stream,
        configure_runtime_logging(
            "multiprocess-test",
            log_directory=Path(log_directory),
            run_identifier="shared-run",
            console_stream=console_stream,
        ) as logger,
    ):
        logger.info("Worker record", event="worker.record", marker=marker)


def _raise_runtime_error(message: str) -> None:
    """Raise a runtime error from a dedicated traceback frame."""

    raise RuntimeError(message)


def _read_json_lines(path: Path) -> list[dict[str, object]]:
    """Read every non-empty JSON object from a UTF-8 JSONL file."""

    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_logging_arguments_accept_environment_defaults_and_cli_override(tmp_path: Path) -> None:
    """Shared arguments must normalize env defaults and prefer explicit CLI values."""

    assert runtime_logging.DEFAULT_LOG_DIRECTORY == WORK_DIRECTORY / "logs"
    parser = argparse.ArgumentParser()
    environment = {
        LOG_LEVEL_ENVIRONMENT_VARIABLE: "debug",
        LOG_DIRECTORY_ENVIRONMENT_VARIABLE: str(tmp_path / "environment-logs"),
    }
    add_logging_arguments(parser, environment=environment)

    environment_arguments = parser.parse_args([])
    assert environment_arguments.log_level == "DEBUG"
    assert environment_arguments.log_directory == tmp_path / "environment-logs"

    cli_arguments = parser.parse_args(
        ["--log-level", "error", "--log-directory", str(tmp_path / "cli-logs")]
    )
    assert cli_arguments.log_level == "ERROR"
    assert cli_arguments.log_directory == tmp_path / "cli-logs"


def test_runtime_logger_creates_utf8_jsonl_and_keeps_stdout_untouched(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Runtime logs must use stderr and a stable structured per-process file."""

    console_stream = io.StringIO()
    logger = configure_runtime_logging(
        "sample tool",
        level="INFO",
        log_directory=tmp_path / "nested" / "logs",
        context={"criterion": "u-03"},
        console_stream=console_stream,
        clock=_fixed_clock,
        process_id=TEST_PROCESS_ID,
        run_identifier="test run",
    )
    logger.debug("Filtered record", event="record.filtered")
    logger.info("변환 완료", event="record.completed", artifact="결과.md")
    sys.stdout.write("machine-result.json\n")
    logger.close()

    captured_output = capsys.readouterr()
    assert captured_output.out == "machine-result.json\n"
    assert captured_output.err == ""
    assert console_stream.getvalue() == "INFO     sample tool: 변환 완료\n"
    assert logger.level == "INFO"
    assert logger.log_directory == tmp_path / "nested" / "logs"
    assert logger.run_identifier == "test-run"
    assert logger.log_path.name == "sample-tool-test-run-p4321.jsonl"

    records = _read_json_lines(logger.log_path)
    assert records == [
        {
            "context": {
                "artifact": "결과.md",
                "criterion": "u-03",
            },
            "event": "record.completed",
            "level": "INFO",
            "message": "변환 완료",
            "process_id": TEST_PROCESS_ID,
            "run_id": "test-run",
            "schema_version": 1,
            "thread": "MainThread",
            "timestamp": "2026-08-19T01:02:03.456Z",
            "tool": "sample tool",
        }
    ]


def test_runtime_logger_uses_cli_over_environment_and_environment_over_default(
    tmp_path: Path,
) -> None:
    """Effective configuration must follow explicit, environment, then default precedence."""

    environment_directory = tmp_path / "environment"
    environment = {
        LOG_LEVEL_ENVIRONMENT_VARIABLE: "warning",
        LOG_DIRECTORY_ENVIRONMENT_VARIABLE: str(environment_directory),
    }
    environment_logger = configure_runtime_logging(
        "environment-test",
        environment=environment,
        console_stream=io.StringIO(),
        clock=_fixed_clock,
        process_id=1,
    )
    try:
        assert environment_logger.level == "WARNING"
        assert environment_logger.log_directory == environment_directory
    finally:
        environment_logger.close()

    explicit_directory = tmp_path / "explicit"
    explicit_logger = configure_runtime_logging(
        "explicit-test",
        level="ERROR",
        log_directory=explicit_directory,
        environment=environment,
        console_stream=io.StringIO(),
        clock=_fixed_clock,
        process_id=2,
    )
    try:
        assert explicit_logger.level == "ERROR"
        assert explicit_logger.log_directory == explicit_directory
    finally:
        explicit_logger.close()


def test_runtime_logger_redacts_messages_context_commands_and_console(tmp_path: Path) -> None:
    """Credential indicators and adjacent command values must never reach either sink."""

    console_stream = io.StringIO()
    logger = configure_runtime_logging(
        "redaction-test",
        log_directory=tmp_path,
        console_stream=console_stream,
        clock=_fixed_clock,
        process_id=3,
    )
    logger.info(
        "Request Authorization: Bearer bearer-value with api_key=message-value "
        "at https://person:url-password@example.test",
        event="request.sent",
        command=[
            "client",
            "--api-key",
            "command-value",
            "--refresh-token=inline-value",
        ],
        headers={"Authorization": "Bearer header-value"},
        password="field-value",  # noqa: S106
        safe_value="retained",
    )
    logger.close()

    combined_output = console_stream.getvalue() + logger.log_path.read_text(encoding="utf-8")
    for credential in (
        "bearer-value",
        "message-value",
        "person",
        "url-password",
        "command-value",
        "inline-value",
        "header-value",
        "field-value",
    ):
        assert credential not in combined_output
    assert "retained" in combined_output
    assert runtime_logging.REDACTED_VALUE in combined_output

    record = _read_json_lines(logger.log_path)[0]
    context = record["context"]
    assert isinstance(context, dict)
    assert context["command"] == [
        "client",
        "--api-key",
        runtime_logging.REDACTED_VALUE,
        f"--refresh-token={runtime_logging.REDACTED_VALUE}",
    ]
    assert context["headers"] == {"Authorization": runtime_logging.REDACTED_VALUE}
    assert context["password"] == runtime_logging.REDACTED_VALUE


def test_exception_logging_records_redacted_type_message_and_traceback(tmp_path: Path) -> None:
    """Exception records must retain diagnostic structure without retaining credentials."""

    console_stream = io.StringIO()
    logger = configure_runtime_logging(
        "exception-test",
        log_directory=tmp_path,
        console_stream=console_stream,
        clock=_fixed_clock,
        process_id=4,
    )
    try:
        message = "token=exception-value"
        _raise_runtime_error(message)
    except RuntimeError as error:
        logger.exception("Conversion failed", event="conversion.failed", error=error)
    logger.close()

    record = _read_json_lines(logger.log_path)[0]
    exception = record["exception"]
    assert isinstance(exception, dict)
    assert exception["type"] == "RuntimeError"
    assert exception["message"] == f"token={runtime_logging.REDACTED_VALUE}"
    assert "Traceback (most recent call last)" in str(exception["traceback"])
    assert "exception-value" not in json.dumps(record)
    assert "exception-value" not in console_stream.getvalue()


def test_context_manager_logs_an_escaping_exception_and_preserves_it(tmp_path: Path) -> None:
    """Context-managed logging must record but never suppress an unhandled error."""

    logger = configure_runtime_logging(
        "context-test",
        log_directory=tmp_path,
        console_stream=io.StringIO(),
        clock=_fixed_clock,
        process_id=5,
    )
    failure_message = "fixture failure"
    with pytest.raises(ValueError, match=failure_message), logger:
        raise ValueError(failure_message)

    record = _read_json_lines(logger.log_path)[0]
    assert record["event"] == "runtime.unhandled_exception"
    assert record["level"] == "ERROR"


def test_processes_write_distinct_complete_jsonl_files(tmp_path: Path) -> None:
    """Workers sharing a run identifier must write only to process-owned files."""

    context = multiprocessing.get_context("spawn")
    processes = [
        context.Process(
            target=_multiprocess_log_worker,
            args=(str(tmp_path), marker),
        )
        for marker in ("first", "second")
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=10)
        assert process.exitcode == 0

    log_paths = sorted(tmp_path.glob("multiprocess-test-shared-run-p*.jsonl"))
    assert len(log_paths) == len(processes)
    process_identifiers: set[int] = set()
    markers: set[object] = set()
    for log_path in log_paths:
        records = _read_json_lines(log_path)
        assert len(records) == 1
        process_identifier = records[0]["process_id"]
        assert isinstance(process_identifier, int)
        process_identifiers.add(process_identifier)
        context_document = records[0]["context"]
        assert isinstance(context_document, dict)
        markers.add(context_document["marker"])
    assert len(process_identifiers) == len(processes)
    assert markers == {"first", "second"}


def test_non_tty_progress_writes_newlines_and_deduplicates_unchanged_finish() -> None:
    """Captured output must use complete lines without duplicating an unchanged terminal state."""

    stream = _TerminalStream(terminal=False)
    clock = _NumberClock(iter([0.0, 1.0, 2.0, 2.0]))
    reporter = ProgressReporter(2, description="Convert", stream=stream, clock=clock)

    reporter.update(outcome="completed")
    final_snapshot = reporter.update(outcome="failed")
    finished_snapshot = reporter.finish()

    assert final_snapshot == finished_snapshot
    assert stream.getvalue().splitlines() == [
        "Convert 1/2 (50.0%) elapsed=1.0s rate=1.00/s outcomes=completed:1",
        "Convert 2/2 (100.0%) elapsed=2.0s rate=1.00/s outcomes=completed:1,failed:1",
    ]


def test_tty_progress_uses_in_place_updates_and_finishes_with_newline() -> None:
    """Interactive output must repaint one line and terminate it exactly once."""

    stream = _TerminalStream(terminal=True)
    clock = _NumberClock(iter([0.0, 1.0, 1.0]))
    reporter = ProgressReporter(
        1,
        description="Convert",
        stream=stream,
        clock=clock,
        environment={},
    )

    reporter.update(outcome="completed")
    reporter.finish()

    output = stream.getvalue()
    assert output.count("\r") == TTY_REPAINT_COUNT
    assert output.count("\n") == 1
    assert output.endswith("outcomes=completed:1\n")


def test_ci_disables_in_place_progress_even_for_a_tty() -> None:
    """Continuous integration output must remain line-oriented for durable logs."""

    stream = _TerminalStream(terminal=True)
    clock = _NumberClock(iter([0.0, 1.0, 1.0]))
    reporter = ProgressReporter(
        1,
        stream=stream,
        clock=clock,
        environment={"CI": "true"},
    )

    reporter.update(outcome="completed")
    reporter.finish()

    assert "\r" not in stream.getvalue()
    assert stream.getvalue().count("\n") == 1


def test_progress_clear_and_refresh_coordinate_with_other_tty_writers() -> None:
    """Interactive callers must be able to clear and restore progress around logs."""

    stream = _TerminalStream(terminal=True)
    clock = _NumberClock(iter([0.0, 1.0, 2.0, 2.0]))
    reporter = ProgressReporter(1, stream=stream, clock=clock, environment={})

    reporter.update(outcome="completed")
    reporter.clear()
    refreshed_snapshot = reporter.refresh()
    reporter.finish()

    assert refreshed_snapshot.completed == 1
    assert "\r" in stream.getvalue()
    assert " " * 10 in stream.getvalue()
    assert stream.getvalue().endswith("outcomes=completed:1\n")


def test_progress_updates_are_thread_safe() -> None:
    """Concurrent parent threads must not lose increments or outcome counts."""

    total = THREAD_COUNT * UPDATES_PER_THREAD
    stream = _TerminalStream(terminal=False)
    clock_values = iter(float(value) for value in range(total + 2))
    reporter = ProgressReporter(total, stream=stream, clock=_NumberClock(clock_values))

    def update_progress() -> None:
        """Record a fixed number of successful units from one thread."""

        for _index in range(UPDATES_PER_THREAD):
            reporter.update(outcome="completed")

    threads = [threading.Thread(target=update_progress) for _index in range(THREAD_COUNT)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    snapshot = reporter.finish()

    assert snapshot.completed == total
    assert snapshot.outcomes == {"completed": total}
    assert len(stream.getvalue().splitlines()) == total


def test_progress_updates_from_a_different_process_are_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A forked copy must not mutate or render its inherited parent reporter."""

    stream = _TerminalStream(terminal=False)
    clock = _NumberClock(iter([0.0, 1.0, 2.0]))
    reporter = ProgressReporter(1, stream=stream, clock=clock)
    owner_process_id = os.getpid()
    monkeypatch.setattr(runtime_logging.os, "getpid", lambda: owner_process_id + 1)

    snapshot = reporter.update(outcome="completed")

    assert snapshot.completed == 0
    assert reporter.completed == 0
    assert stream.getvalue() == ""


def test_invalid_log_level_and_progress_bounds_are_rejected(tmp_path: Path) -> None:
    """Invalid operational controls must fail before producing ambiguous output."""

    with pytest.raises(ValueError, match="unsupported log level"):
        configure_runtime_logging(
            "invalid-level",
            level="verbose",
            log_directory=tmp_path,
            console_stream=io.StringIO(),
        )
    with pytest.raises(ValueError, match="non-negative integer"):
        ProgressReporter(-1)

    reporter = ProgressReporter(
        1,
        stream=io.StringIO(),
        clock=_NumberClock(iter([0.0])),
        enabled=False,
    )
    with pytest.raises(ValueError, match="exceeds"):
        reporter.update(2)


def test_logger_uses_only_text_stream_protocol(tmp_path: Path) -> None:
    """The public stream injection accepts the standard text I/O protocol."""

    stream: IO[str] = io.StringIO()
    with configure_runtime_logging(
        "stream-test",
        log_directory=tmp_path,
        console_stream=stream,
        clock=_fixed_clock,
        process_id=6,
    ) as logger:
        logger.warning("Warning record", event="warning.record")
    assert stream.getvalue() == "WARNING  stream-test: Warning record\n"
