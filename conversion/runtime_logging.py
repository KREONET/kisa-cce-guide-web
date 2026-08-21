"""Dependency-free runtime logging and progress reporting for conversion commands."""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import re
import sys
import threading
import traceback as traceback_module
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import IO, Self

DEFAULT_LOG_DIRECTORY = Path("work/logs")
DEFAULT_LOG_LEVEL = "INFO"
LOG_LEVEL_ENVIRONMENT_VARIABLE = "KISA_CCE_LOG_LEVEL"
LOG_DIRECTORY_ENVIRONMENT_VARIABLE = "KISA_CCE_LOG_DIRECTORY"
LOG_LEVEL_NAMES = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
REDACTED_VALUE = "[REDACTED]"

_LOG_LEVEL_VALUES = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}
_LOG_LEVEL_ALIASES = {"WARN": "WARNING", "FATAL": "CRITICAL"}
_SENSITIVE_KEY_NAMES = frozenset(
    {
        "api_key",
        "apikey",
        "token",
        "access_token",
        "refresh_token",
        "auth_token",
        "authorization",
        "proxy_authorization",
        "password",
        "passwd",
        "secret",
        "client_secret",
        "credential",
        "credentials",
        "cookie",
        "set_cookie",
        "private_key",
    }
)
_SENSITIVE_KEY_SUFFIXES = (
    "_api_key",
    "_token",
    "_access_token",
    "_refresh_token",
    "_auth_token",
    "_password",
    "_passwd",
    "_secret",
    "_credential",
    "_credentials",
    "_private_key",
)
_SENSITIVE_TEXT_KEY = (
    r"(?:[A-Za-z0-9]+[_-])*(?:api[_-]?key|access[_-]?token|refresh[_-]?token|"
    r"auth[_-]?token|token|authorization|proxy[_-]?authorization|password|passwd|"
    r"client[_-]?secret|secret|credentials?|cookie|set[_-]?cookie|private[_-]?key)"
)
_URL_CREDENTIAL_PATTERN = re.compile(
    r"(?P<scheme>\b[a-z][a-z0-9+.-]*://)(?P<credentials>[^/@\s]+@)",
    flags=re.IGNORECASE,
)
_AUTH_SCHEME_PATTERN = re.compile(
    r"\b(?P<scheme>Bearer|Basic)\s+(?P<value>[A-Za-z0-9._~+/=-]+)",
    flags=re.IGNORECASE,
)
_SENSITIVE_ASSIGNMENT_PATTERN = re.compile(
    rf"(?P<prefix>\b{_SENSITIVE_TEXT_KEY}\s*(?:=|:)\s*)"
    r"(?P<value>\"[^\"]*\"|'[^']*'|[^\s&,;]+)",
    flags=re.IGNORECASE,
)
_SENSITIVE_OPTION_PATTERN = re.compile(
    rf"(?P<prefix>--{_SENSITIVE_TEXT_KEY})(?P<separator>=|\s+)"
    r"(?P<value>\"[^\"]*\"|'[^']*'|[^\s,;]+)",
    flags=re.IGNORECASE,
)
_KNOWN_CREDENTIAL_PATTERN = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{10,}|gh[pousr]_[A-Za-z0-9]{10,}|AKIA[A-Z0-9]{16})\b"
)
_FILENAME_COMPONENT_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")
_CONSOLE_WRITE_LOCK = threading.Lock()
_MAXIMUM_CONTEXT_DEPTH = 12

type TimestampClock = Callable[[], datetime]
type MonotonicClock = Callable[[], float]


def _default_timestamp_clock() -> datetime:
    """Return the current timezone-aware UTC time."""

    return datetime.now(tz=UTC)


def _is_sensitive_key(key: object) -> bool:
    """Return whether a structured field name commonly contains credentials."""

    normalized_key = re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")
    return normalized_key in _SENSITIVE_KEY_NAMES or normalized_key.endswith(
        _SENSITIVE_KEY_SUFFIXES
    )


def _is_sensitive_option(value: str) -> bool:
    """Return whether a command argument expects a credential as its next value."""

    if not value.startswith("--") or "=" in value:
        return False
    return _is_sensitive_key(value[2:])


def _redact_text(value: str) -> str:
    """Redact recognizable credential forms without changing neutral text."""

    redacted = _URL_CREDENTIAL_PATTERN.sub(
        lambda match: f"{match.group('scheme')}{REDACTED_VALUE}@",
        value,
    )
    redacted = _AUTH_SCHEME_PATTERN.sub(
        lambda match: f"{match.group('scheme')} {REDACTED_VALUE}",
        redacted,
    )
    redacted = _SENSITIVE_OPTION_PATTERN.sub(
        lambda match: f"{match.group('prefix')}{match.group('separator')}{REDACTED_VALUE}",
        redacted,
    )
    redacted = _SENSITIVE_ASSIGNMENT_PATTERN.sub(
        lambda match: f"{match.group('prefix')}{REDACTED_VALUE}",
        redacted,
    )
    return _KNOWN_CREDENTIAL_PATTERN.sub(REDACTED_VALUE, redacted)


def _sanitize_sequence(
    values: list[object] | tuple[object, ...],
    *,
    seen: set[int],
    depth: int,
) -> list[object]:
    """Sanitize a sequence while recognizing split command credential options."""

    sanitized_values: list[object] = []
    redact_next_value = False
    for value in values:
        if redact_next_value:
            sanitized_values.append(REDACTED_VALUE)
            redact_next_value = False
            continue
        if isinstance(value, str) and _is_sensitive_option(value):
            sanitized_values.append(_redact_text(value))
            redact_next_value = True
            continue
        sanitized_values.append(_sanitize_value(value, seen=seen, depth=depth + 1))
    return sanitized_values


def _sanitize_value(  # noqa: C901, PLR0911, PLR0912
    value: object,
    *,
    seen: set[int],
    depth: int = 0,
) -> object:
    """Convert one value to a bounded, redacted JSON-compatible representation."""

    if depth > _MAXIMUM_CONTEXT_DEPTH:
        return "[TRUNCATED]"
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, bytes):
        return _redact_text(value.decode("utf-8", errors="replace"))
    if isinstance(value, Path):
        return _redact_text(str(value))
    if isinstance(value, datetime):
        return _timestamp_text(value)
    if isinstance(value, BaseException):
        return _redact_text(str(value))

    value_identifier = id(value)
    if value_identifier in seen:
        return "[RECURSIVE]"
    if isinstance(value, Mapping):
        seen.add(value_identifier)
        try:
            sanitized_mapping: dict[str, object] = {}
            for key, nested_value in sorted(value.items(), key=lambda item: str(item[0])):
                key_text = _redact_text(str(key))
                sanitized_mapping[key_text] = (
                    REDACTED_VALUE
                    if _is_sensitive_key(key)
                    else _sanitize_value(nested_value, seen=seen, depth=depth + 1)
                )
            return sanitized_mapping
        finally:
            seen.remove(value_identifier)
    if isinstance(value, list | tuple):
        seen.add(value_identifier)
        try:
            return _sanitize_sequence(value, seen=seen, depth=depth)
        finally:
            seen.remove(value_identifier)
    if isinstance(value, set | frozenset):
        seen.add(value_identifier)
        try:
            sanitized_items = [_sanitize_value(item, seen=seen, depth=depth + 1) for item in value]
            return sorted(sanitized_items, key=lambda item: json.dumps(item, sort_keys=True))
        finally:
            seen.remove(value_identifier)
    return _redact_text(str(value))


def redact_sensitive_data(value: object) -> object:
    """Return a redacted JSON-compatible copy of a log value."""

    return _sanitize_value(value, seen=set())


def _timestamp_text(value: datetime) -> str:
    """Return a deterministic ISO 8601 UTC timestamp with millisecond precision."""

    normalized_value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return normalized_value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _clock_value(clock: TimestampClock) -> datetime:
    """Read and validate one injected wall-clock value."""

    value = clock()
    if not isinstance(value, datetime):
        message = "runtime logging clock must return datetime values"
        raise TypeError(message)
    return value


def _normalize_level(value: str | int) -> tuple[str, int]:
    """Normalize one supported standard logging level."""

    if isinstance(value, bool):
        message = "log level must be a name or a standard logging integer"
        raise ValueError(message)
    if isinstance(value, int):
        matching_names = [
            name for name, numeric_value in _LOG_LEVEL_VALUES.items() if value == numeric_value
        ]
        if not matching_names:
            message = f"unsupported log level: {value}"
            raise ValueError(message)
        name = matching_names[0]
        return name, value
    normalized_name = value.strip().upper()
    normalized_name = _LOG_LEVEL_ALIASES.get(normalized_name, normalized_name)
    if normalized_name not in _LOG_LEVEL_VALUES:
        supported_names = ", ".join(LOG_LEVEL_NAMES)
        message = f"unsupported log level {value!r}; expected one of {supported_names}"
        raise ValueError(message)
    return normalized_name, _LOG_LEVEL_VALUES[normalized_name]


def _level_argument(value: str) -> str:
    """Parse and normalize one command-line log level."""

    try:
        name, _numeric_value = _normalize_level(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error
    return name


def add_logging_arguments(
    parser: argparse.ArgumentParser,
    *,
    environment: Mapping[str, str] | None = None,
) -> None:
    """Add shared log level and directory options to one command parser."""

    selected_environment = os.environ if environment is None else environment
    parser.add_argument(
        "--log-level",
        type=_level_argument,
        default=selected_environment.get(LOG_LEVEL_ENVIRONMENT_VARIABLE),
        metavar="LEVEL",
        help=(
            "console and file log level "
            f"({', '.join(LOG_LEVEL_NAMES)}; env {LOG_LEVEL_ENVIRONMENT_VARIABLE})"
        ),
    )
    parser.add_argument(
        "--log-directory",
        type=Path,
        default=selected_environment.get(LOG_DIRECTORY_ENVIRONMENT_VARIABLE),
        metavar="PATH",
        help=f"UTF-8 JSONL log directory (env {LOG_DIRECTORY_ENVIRONMENT_VARIABLE})",
    )


def _safe_filename_component(value: str, *, fallback: str) -> str:
    """Return a portable non-empty filename component."""

    component = _FILENAME_COMPONENT_PATTERN.sub("-", value.strip()).strip(".-_")
    return component or fallback


def _run_identifier(value: datetime) -> str:
    """Derive a sortable UTC run identifier from one clock reading."""

    normalized_value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return normalized_value.strftime("%Y%m%dT%H%M%S.%fZ")


def _environment_value(
    environment: Mapping[str, str],
    variable_name: str,
) -> str | None:
    """Return a non-empty environment setting."""

    value = environment.get(variable_name)
    if value is None or not value.strip():
        return None
    return value


class RuntimeLogger:
    """Write concise stderr logs and redacted per-process JSONL records."""

    def __init__(  # noqa: PLR0913
        self,
        *,
        tool_name: str,
        level: str,
        numeric_level: int,
        log_directory: Path,
        log_path: Path,
        run_identifier: str,
        process_id: int,
        context: Mapping[str, object],
        console_stream: IO[str],
        clock: TimestampClock,
    ) -> None:
        """Initialize a configured logger around an already selected path."""

        self.tool_name = tool_name
        self.level = level
        self.log_directory = log_directory
        self.log_path = log_path
        self.run_identifier = run_identifier
        self.process_id = process_id
        self._numeric_level = numeric_level
        sanitized_context = redact_sensitive_data(context)
        self._context = sanitized_context if isinstance(sanitized_context, dict) else {}
        self._console_stream = console_stream
        self._clock = clock
        self._lock = threading.Lock()
        self._closed = False
        self._file_stream = log_path.open("a", encoding="utf-8", newline="\n")

    def __enter__(self) -> Self:
        """Return this logger for context-managed use."""

        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        exception_traceback: TracebackType | None,
    ) -> bool:
        """Log an escaping exception, close both outputs, and preserve propagation."""

        if exception is not None:
            self._log_exception(
                "Unhandled exception",
                event="runtime.unhandled_exception",
                error=exception,
                exception_traceback=exception_traceback,
                fields={},
            )
        self.close()
        return False

    def is_enabled_for(self, level: str | int) -> bool:
        """Return whether a level would be emitted by this logger."""

        _level_name, numeric_level = _normalize_level(level)
        return numeric_level >= self._numeric_level

    def log(
        self,
        level: str | int,
        message: str,
        *,
        event: str = "message",
        **fields: object,
    ) -> None:
        """Emit one redacted record when its level passes the configured threshold."""

        level_name, numeric_level = _normalize_level(level)
        if numeric_level < self._numeric_level:
            return
        if not isinstance(message, str):
            error_message = "log message must be a string"
            raise TypeError(error_message)
        if not isinstance(event, str) or not event.strip():
            error_message = "log event must be a non-empty string"
            raise ValueError(error_message)
        sanitized_message = _redact_text(message)
        sanitized_event = _redact_text(event.strip())
        record_context = {**self._context, **fields}
        sanitized_context = redact_sensitive_data(record_context)
        record: dict[str, object] = {
            "schema_version": 1,
            "timestamp": _timestamp_text(_clock_value(self._clock)),
            "level": level_name,
            "tool": _redact_text(self.tool_name),
            "event": sanitized_event,
            "message": sanitized_message,
            "run_id": self.run_identifier,
            "process_id": self.process_id,
            "thread": threading.current_thread().name,
            "context": sanitized_context,
        }
        self._write_record(record, console_message=sanitized_message)

    def debug(self, message: str, *, event: str = "message", **fields: object) -> None:
        """Emit a DEBUG record."""

        self.log("DEBUG", message, event=event, **fields)

    def info(self, message: str, *, event: str = "message", **fields: object) -> None:
        """Emit an INFO record."""

        self.log("INFO", message, event=event, **fields)

    def warning(self, message: str, *, event: str = "message", **fields: object) -> None:
        """Emit a WARNING record."""

        self.log("WARNING", message, event=event, **fields)

    def error(self, message: str, *, event: str = "message", **fields: object) -> None:
        """Emit an ERROR record."""

        self.log("ERROR", message, event=event, **fields)

    def critical(self, message: str, *, event: str = "message", **fields: object) -> None:
        """Emit a CRITICAL record."""

        self.log("CRITICAL", message, event=event, **fields)

    def exception(
        self,
        message: str,
        *,
        event: str = "exception",
        error: BaseException | None = None,
        **fields: object,
    ) -> None:
        """Emit an ERROR record with a redacted exception and traceback."""

        selected_error = error if error is not None else sys.exc_info()[1]
        self._log_exception(
            message,
            event=event,
            error=selected_error,
            exception_traceback=(
                selected_error.__traceback__ if selected_error is not None else None
            ),
            fields=fields,
        )

    def _log_exception(
        self,
        message: str,
        *,
        event: str,
        error: BaseException | None,
        exception_traceback: TracebackType | None,
        fields: Mapping[str, object],
    ) -> None:
        """Build one exception record without changing exception propagation."""

        if self._numeric_level > logging.ERROR:
            return
        if not isinstance(message, str):
            error_message = "log message must be a string"
            raise TypeError(error_message)
        if not isinstance(event, str) or not event.strip():
            error_message = "log event must be a non-empty string"
            raise ValueError(error_message)
        sanitized_message = _redact_text(message)
        record_context = {**self._context, **fields}
        sanitized_context = redact_sensitive_data(record_context)
        record: dict[str, object] = {
            "schema_version": 1,
            "timestamp": _timestamp_text(_clock_value(self._clock)),
            "level": "ERROR",
            "tool": _redact_text(self.tool_name),
            "event": _redact_text(event.strip()),
            "message": sanitized_message,
            "run_id": self.run_identifier,
            "process_id": self.process_id,
            "thread": threading.current_thread().name,
            "context": sanitized_context,
        }
        console_message = sanitized_message
        if error is not None:
            traceback_text = "".join(
                traceback_module.format_exception(type(error), error, exception_traceback)
            ).rstrip()
            exception_document = {
                "type": type(error).__name__,
                "message": _redact_text(str(error)),
                "traceback": _redact_text(traceback_text),
            }
            record["exception"] = exception_document
            console_message = (
                f"{sanitized_message} ({exception_document['type']}: "
                f"{exception_document['message']})"
            )
        self._write_record(record, console_message=console_message)

    def _write_record(self, record: Mapping[str, object], *, console_message: str) -> None:
        """Write one whole JSON line and one whole console line under locks."""

        serialized_record = json.dumps(
            record,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        console_line = f"{record['level']:<8} {record['tool']}: {console_message}\n"
        with self._lock:
            if self._closed:
                message = "runtime logger is closed"
                raise RuntimeError(message)
            self._file_stream.write(f"{serialized_record}\n")
            self._file_stream.flush()
            with _CONSOLE_WRITE_LOCK:
                self._console_stream.write(console_line)
                self._console_stream.flush()

    def close(self) -> None:
        """Flush and close the JSONL stream without emitting a lifecycle event."""

        with self._lock:
            if self._closed:
                return
            self._file_stream.flush()
            self._file_stream.close()
            self._closed = True


def configure_runtime_logging(  # noqa: PLR0913
    tool_name: str,
    *,
    level: str | int | None = None,
    log_directory: Path | str | None = None,
    context: Mapping[str, object] | None = None,
    environment: Mapping[str, str] | None = None,
    console_stream: IO[str] | None = None,
    clock: TimestampClock | None = None,
    process_id: int | None = None,
    run_identifier: str | None = None,
) -> RuntimeLogger:
    """Configure stderr and a UTF-8 JSONL file for one CLI process."""

    if not isinstance(tool_name, str) or not tool_name.strip():
        message = "tool name must be a non-empty string"
        raise ValueError(message)
    selected_environment = os.environ if environment is None else environment
    configured_level: str | int = (
        level
        if level is not None
        else (
            _environment_value(selected_environment, LOG_LEVEL_ENVIRONMENT_VARIABLE)
            or DEFAULT_LOG_LEVEL
        )
    )
    level_name, numeric_level = _normalize_level(configured_level)

    configured_directory = log_directory
    if configured_directory is None:
        configured_directory = (
            _environment_value(selected_environment, LOG_DIRECTORY_ENVIRONMENT_VARIABLE)
            or DEFAULT_LOG_DIRECTORY
        )
    selected_log_directory = Path(configured_directory)
    selected_log_directory.mkdir(parents=True, exist_ok=True)

    selected_process_id = os.getpid() if process_id is None else process_id
    if isinstance(selected_process_id, bool) or selected_process_id < 0:
        message = "process ID must be a non-negative integer"
        raise ValueError(message)
    selected_clock = _default_timestamp_clock if clock is None else clock
    initial_time = _clock_value(selected_clock)
    selected_run_identifier = _safe_filename_component(
        run_identifier if run_identifier is not None else _run_identifier(initial_time),
        fallback="run",
    )
    filename_tool_name = _safe_filename_component(tool_name, fallback="conversion")
    log_path = selected_log_directory / (
        f"{filename_tool_name}-{selected_run_identifier}-p{selected_process_id}.jsonl"
    )
    selected_console_stream = sys.stderr if console_stream is None else console_stream
    return RuntimeLogger(
        tool_name=tool_name.strip(),
        level=level_name,
        numeric_level=numeric_level,
        log_directory=selected_log_directory,
        log_path=log_path,
        run_identifier=selected_run_identifier,
        process_id=selected_process_id,
        context={} if context is None else context,
        console_stream=selected_console_stream,
        clock=selected_clock,
    )


@dataclass(frozen=True)
class ProgressSnapshot:
    """One immutable view of progress state."""

    completed: int
    total: int
    percentage: float
    elapsed_seconds: float
    rate_per_second: float
    outcomes: dict[str, int]


class ProgressReporter:
    """Render thread-safe parent-process progress exclusively to stderr."""

    def __init__(  # noqa: PLR0913
        self,
        total: int,
        *,
        description: str = "Progress",
        stream: IO[str] | None = None,
        clock: MonotonicClock | None = None,
        enabled: bool = True,
        min_interval_seconds: float = 0.0,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        """Initialize progress state without writing an initial update."""

        if isinstance(total, bool) or not isinstance(total, int) or total < 0:
            message = "progress total must be a non-negative integer"
            raise ValueError(message)
        if not math.isfinite(min_interval_seconds) or min_interval_seconds < 0:
            message = "progress minimum interval must be a non-negative finite number"
            raise ValueError(message)
        self.total = total
        self.description = _redact_text(description.strip() or "Progress")
        self._stream = sys.stderr if stream is None else stream
        self._clock = __import__("time").monotonic if clock is None else clock
        self._enabled = enabled
        self._minimum_interval_seconds = min_interval_seconds
        self._environment = os.environ if environment is None else environment
        self._owner_process_id = os.getpid()
        self._completed = 0
        self._outcomes: Counter[str] = Counter()
        self._lock = threading.Lock()
        self._started_at = self._read_clock()
        self._last_rendered_at: float | None = None
        self._last_rendered_line: str | None = None
        self._last_rendered_state: tuple[int, int, tuple[tuple[str, int], ...]] | None = None
        self._last_render_width = 0
        self._finished = False
        self._interactive = self._is_interactive_stream()

    def __enter__(self) -> Self:
        """Return this reporter for context-managed use."""

        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        exception_traceback: TracebackType | None,
    ) -> bool:
        """Render a terminal state and preserve any escaping exception."""

        del exception_type, exception_traceback
        self.finish(outcome="failed" if exception is not None else None)
        return False

    @property
    def completed(self) -> int:
        """Return the number of completed units."""

        with self._lock:
            return self._completed

    @property
    def outcome_counts(self) -> dict[str, int]:
        """Return a stable copy of the observed outcome counts."""

        with self._lock:
            return dict(sorted(self._outcomes.items()))

    def _read_clock(self) -> float:
        """Read and validate the injected monotonic clock."""

        value = self._clock()
        if (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(value)
        ):
            message = "progress clock must return a finite number"
            raise TypeError(message)
        return float(value)

    def _is_interactive_stream(self) -> bool:
        """Use in-place output only for a TTY outside continuous integration."""

        continuous_integration = self._environment.get("CI", "").strip().lower()
        in_continuous_integration = continuous_integration not in {"", "0", "false", "no", "off"}
        try:
            stream_is_terminal = self._stream.isatty()
        except (AttributeError, OSError):
            stream_is_terminal = False
        return bool(stream_is_terminal) and not in_continuous_integration

    def _snapshot(self, current_time: float) -> ProgressSnapshot:
        """Build a progress snapshot while the state lock is held."""

        elapsed_seconds = max(0.0, current_time - self._started_at)
        percentage = 100.0 if self.total == 0 else self._completed / self.total * 100.0
        rate_per_second = self._completed / elapsed_seconds if elapsed_seconds > 0 else 0.0
        return ProgressSnapshot(
            completed=self._completed,
            total=self.total,
            percentage=percentage,
            elapsed_seconds=elapsed_seconds,
            rate_per_second=rate_per_second,
            outcomes=dict(sorted(self._outcomes.items())),
        )

    @property
    def snapshot(self) -> ProgressSnapshot:
        """Return the current progress state without rendering it."""

        with self._lock:
            return self._snapshot(self._read_clock())

    def update(self, advance: int = 1, *, outcome: str | None = None) -> ProgressSnapshot:
        """Advance completed work, count its outcome, and render one update."""

        if os.getpid() != self._owner_process_id:
            return self.snapshot
        if isinstance(advance, bool) or not isinstance(advance, int) or advance < 0:
            message = "progress advance must be a non-negative integer"
            raise ValueError(message)
        sanitized_outcome: str | None = None
        if outcome is not None:
            if not isinstance(outcome, str) or not outcome.strip():
                message = "progress outcome must be a non-empty string"
                raise ValueError(message)
            sanitized_outcome = _redact_text(outcome.strip())
        with self._lock:
            if self._finished:
                message = "progress reporter is finished"
                raise RuntimeError(message)
            if self._completed + advance > self.total:
                message = "progress update exceeds the configured total"
                raise ValueError(message)
            self._completed += advance
            if sanitized_outcome is not None and advance:
                self._outcomes[sanitized_outcome] += advance
            current_time = self._read_clock()
            snapshot = self._snapshot(current_time)
            self._render(snapshot, current_time=current_time, final=False)
            return snapshot

    def finish(self, *, outcome: str | None = None) -> ProgressSnapshot:
        """Render a newline-terminated final state and optionally classify remaining work."""

        if os.getpid() != self._owner_process_id:
            return self.snapshot
        sanitized_outcome: str | None = None
        if outcome is not None:
            if not isinstance(outcome, str) or not outcome.strip():
                message = "progress outcome must be a non-empty string"
                raise ValueError(message)
            sanitized_outcome = _redact_text(outcome.strip())
        with self._lock:
            current_time = self._read_clock()
            if self._finished:
                return self._snapshot(current_time)
            remaining = self.total - self._completed
            if sanitized_outcome is not None and remaining:
                self._completed = self.total
                self._outcomes[sanitized_outcome] += remaining
            snapshot = self._snapshot(current_time)
            self._render(snapshot, current_time=current_time, final=True)
            self._finished = True
            return snapshot

    def close(self) -> None:
        """Finish progress output without assigning an outcome."""

        self.finish()

    def clear(self) -> None:
        """Clear an active in-place line before another stderr writer runs."""

        if os.getpid() != self._owner_process_id or not self._enabled or not self._interactive:
            return
        with self._lock, _CONSOLE_WRITE_LOCK:
            if not self._last_render_width:
                return
            self._stream.write(f"\r{' ' * self._last_render_width}\r")
            self._stream.flush()

    def refresh(self) -> ProgressSnapshot:
        """Force a repaint of the current state without changing its counts."""

        if os.getpid() != self._owner_process_id:
            return self.snapshot
        with self._lock:
            current_time = self._read_clock()
            snapshot = self._snapshot(current_time)
            if self._enabled and self._interactive and not self._finished:
                self._last_rendered_at = None
                self._render(snapshot, current_time=current_time, final=False)
            return snapshot

    def _render(
        self,
        snapshot: ProgressSnapshot,
        *,
        current_time: float,
        final: bool,
    ) -> None:
        """Render one update using terminal-aware line discipline."""

        if not self._enabled:
            return
        if (
            not final
            and self._last_rendered_at is not None
            and current_time - self._last_rendered_at < self._minimum_interval_seconds
        ):
            return
        outcomes = ",".join(f"{name}:{count}" for name, count in sorted(snapshot.outcomes.items()))
        outcome_text = outcomes or "-"
        line = (
            f"{self.description} {snapshot.completed}/{snapshot.total} "
            f"({snapshot.percentage:.1f}%) elapsed={snapshot.elapsed_seconds:.1f}s "
            f"rate={snapshot.rate_per_second:.2f}/s outcomes={outcome_text}"
        )
        rendered_state = (
            snapshot.completed,
            snapshot.total,
            tuple(sorted(snapshot.outcomes.items())),
        )
        if final and not self._interactive and rendered_state == self._last_rendered_state:
            self._last_rendered_at = current_time
            return
        with _CONSOLE_WRITE_LOCK:
            if self._interactive:
                padding = " " * max(0, self._last_render_width - len(line))
                terminator = "\n" if final else ""
                self._stream.write(f"\r{line}{padding}{terminator}")
                self._last_render_width = len(line)
            else:
                self._stream.write(f"{line}\n")
            self._stream.flush()
        self._last_rendered_at = current_time
        self._last_rendered_line = line
        self._last_rendered_state = rendered_state


__all__ = [
    "DEFAULT_LOG_DIRECTORY",
    "DEFAULT_LOG_LEVEL",
    "LOG_DIRECTORY_ENVIRONMENT_VARIABLE",
    "LOG_LEVEL_ENVIRONMENT_VARIABLE",
    "LOG_LEVEL_NAMES",
    "REDACTED_VALUE",
    "ProgressReporter",
    "ProgressSnapshot",
    "RuntimeLogger",
    "add_logging_arguments",
    "configure_runtime_logging",
    "redact_sensitive_data",
]
